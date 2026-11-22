# Kiểm soát thời gian chờ xuyên suốt HTTP, pool và truy vấn

Trong ứng dụng Spring WebFlux dùng Spring Data R2DBC, một request có thể phải chờ qua nhiều lớp: client gửi request, reverse proxy chuyển tiếp, WebFlux xử lý pipeline, connection pool cấp connection, driver mở hoặc sử dụng connection, database thực thi SQL và các dịch vụ HTTP phụ trợ trả kết quả. Nếu chỉ đặt một timeout ở controller hoặc chỉ cấu hình timeout cho database, request vẫn có thể chờ quá lâu ở một lớp khác.

Kiểm soát timeout cần bắt đầu từ **ngân sách thời gian end-to-end** của request. Mỗi lớp nhận một phần ngân sách phù hợp, timeout của dependency nên nhỏ hơn deadline của caller, và toàn bộ retry/cleanup phải nằm trong giới hạn chung. Cần phân biệt thời gian chờ connection, thời gian mở connection, thời gian thực thi statement, thời gian chờ response HTTP và thời gian tối đa của toàn pipeline.

Một timeout ở phía ứng dụng cũng không tự chứng minh rằng database đã dừng query hoặc transaction đã rollback. Reactive timeout thường hủy subscription upstream; khả năng driver gửi cancellation và database dừng statement phụ thuộc driver, giao thức và hệ quản trị. Với query quan trọng, nên có timeout phía database hoặc statement timeout được hỗ trợ, đồng thời kiểm thử hành vi cancellation thực tế.

## 1. Timeout là nhiều giới hạn khác nhau

Không có một timeout duy nhất bao phủ mọi giai đoạn. Một hệ thống R2DBC/WebFlux thường cần xem xét:

| Lớp | Timeout kiểm soát điều gì? | Ví dụ vấn đề |
| --- | --- | --- |
| Client | Thời gian caller chờ response | Người dùng không chờ vô hạn |
| Load balancer/reverse proxy | Thời gian chờ upstream hoặc kết nối | Proxy đóng request bị treo |
| HTTP server | Kết nối, đọc request hoặc ghi response theo cấu hình server | Client gửi request quá chậm hoặc kết nối idle |
| Application pipeline | Thời gian tối đa của use case | Service không hoàn tất trong deadline |
| WebClient | TCP connect, response read hoặc toàn bộ publisher | Service phụ trợ chậm |
| R2DBC pool | Chờ lấy connection từ pool | Pool hết connection |
| R2DBC connection creation | Thời gian tạo connection mới | Database không nhận kết nối |
| SQL statement | Thời gian database được phép thực thi câu lệnh | Query chạy quá lâu hoặc lock wait |
| Transaction | Thời gian nghiệp vụ database được phép kéo dài | Transaction giữ connection quá lâu |

Các giới hạn này có phạm vi khác nhau. Ví dụ, maxAcquireTime của pool không phải thời gian SQL chạy; responseTimeout của HTTP client không nhất thiết là tổng thời gian của request; timeout của một Mono không phải cam kết database đã ngừng xử lý.

### 1.1. Phân biệt timeout với idle timeout

Một số cấu hình giới hạn thời gian không có hoạt động trên connection, chẳng hạn HTTP connection idle timeout hoặc pool max idle time. Chúng giúp thu hồi tài nguyên không được sử dụng, nhưng không đặt deadline cho một request đang chạy.

Tương tự, thời gian sống tối đa của connection trong pool (maxLifeTime) không phải query timeout. Đừng dùng một cấu hình có chữ “timeout” hoặc “time” rồi giả định nó bảo vệ mọi giai đoạn.

### 1.2. Timeout không giống cancellation hoàn tất

Khi caller hết thời gian chờ, ứng dụng có thể phát TimeoutException và gửi cancellation upstream. Từ đó:

- Publisher có thể ngừng phát dữ liệu.
- Driver có thể gửi lệnh cancel hoặc đóng/loại connection.
- Database có thể dừng statement, hoặc cần thêm thời gian để xử lý cancellation.
- Transaction có thể rollback nếu chưa commit và transaction manager xử lý cancellation đúng.
- Nếu connection mất đúng lúc commit, kết quả commit có thể không xác định.

Vì vậy, timeout là tín hiệu rằng caller không nhận được kết quả đúng hạn. Nó không luôn chứng minh thao tác ghi chưa xảy ra.

## 2. Thiết kế ngân sách thời gian end-to-end

Hãy bắt đầu bằng câu hỏi: API này được phép mất tối đa bao lâu từ lúc server nhận request đến khi trả response?

Ví dụ một API có ngân sách ứng dụng 2,5 giây:

| Thành phần | Giới hạn minh họa |
| --- | ---: |
| Client chờ response | 3.200 ms |
| Gateway/reverse proxy | 3.000 ms |
| Toàn bộ application pipeline | 2.700 ms |
| Một lời gọi HTTP phụ trợ | 700 ms |
| Chờ R2DBC pool acquire | 250 ms |
| Tạo connection mới | 500 ms |
| SQL statement | 1.200 ms |
| Phần còn lại cho validation, mapping, response và cleanup | Phần ngân sách còn lại |

Đây chỉ là ví dụ minh họa. Các bước có thể chạy tuần tự hoặc song song; nếu chạy tuần tự, tổng thời gian của chúng phải nằm trong ngân sách. Nếu chạy song song, deadline tổng vẫn bao phủ thời gian chờ của cả nhóm.

### 2.1. Timeout bên trong nên ngắn hơn timeout bên ngoài

Một nguyên tắc hữu ích:

~~~text
Database statement timeout
          <
Transaction budget
          <
Application deadline
          <
Gateway timeout
          <
Client timeout
~~~

Thứ tự này tạo khoảng trống để ứng dụng nhận lỗi từ dependency, rollback/cleanup, tạo response và gửi response trước khi caller hoặc gateway đóng kết nối.

Không phải mọi timeout đều có quan hệ lồng nhau hoàn toàn. Ví dụ WebClient và R2DBC có thể là hai dependency tuần tự trong cùng service; khi đó cần chia ngân sách cho từng dependency và giữ deadline tổng cho cả pipeline.

### 2.2. Để lại thời gian cho cleanup và trả response

Nếu gateway đóng request sau 2 giây và application cũng timeout đúng 2 giây, ứng dụng có thể không còn đủ thời gian xử lý lỗi, rollback, ghi log hoặc gửi response. Hãy đặt deadline application thấp hơn gateway một khoảng hợp lý.

Khoảng dự phòng phụ thuộc latency thực tế, network và cách gateway xử lý response. Không có một giá trị cố định phù hợp cho mọi hệ thống.

### 2.3. Không cộng timeout một cách máy móc

Giả sử pipeline có:

1. Chờ pool tối đa 250 ms.
2. Query tối đa 1.200 ms.
3. Gọi service phụ trợ tối đa 700 ms.

Nếu ba bước tuần tự, tổng giới hạn giai đoạn có thể gần 2.150 ms, chưa tính mapping và cleanup. Nếu hai dependency chạy song song, thời gian chờ của nhóm phụ thuộc vào nhánh chậm nhất, không phải tổng hai timeout.

Timeout tổng vẫn cần bao phủ cả pipeline. Các timeout từng giai đoạn giúp xác định bottleneck; deadline tổng bảo vệ caller.

## 3. Đặt timeout cho toàn bộ reactive pipeline

Reactor cung cấp toán tử timeout. Với Mono, nếu nguồn không phát kết quả trong khoảng thời gian quy định, publisher phát TimeoutException và hủy nguồn upstream.

~~~java
public Mono<OrderResponse> getOrder(Long orderId) {
    return orderService.findOrder(orderId)
            .map(OrderResponse::from)
            .timeout(Duration.ofSeconds(2));
}
~~~

Timeout này giới hạn thời gian của publisher được bọc, tính từ lúc subscription bắt đầu. Nó có thể bao gồm thời gian chờ pool, query và các bước được nối bên trong orderService.

### 3.1. Đặt timeout ở application/service boundary

Thường nên đặt deadline ở ranh giới use case hoặc request, nơi có thể nhìn thấy toàn bộ công việc:

~~~java
public Mono<OrderResponse> handle(GetOrderQuery query) {
    return orderService.getOrder(query.orderId())
            .flatMap(this::loadCustomer)
            .map(OrderResponse::from)
            .timeout(Duration.ofMillis(2500));
}
~~~

Nếu chỉ đặt timeout quanh repository query, phần authorization, service phụ trợ hoặc mapping phía sau vẫn có thể tiếp tục kéo dài.

### 3.2. Timeout cho một giai đoạn cụ thể

Cũng có thể đặt giới hạn riêng cho một dependency:

~~~java
public Mono<Customer> loadCustomer(Long customerId) {
    return customerRepository.findById(customerId)
            .timeout(Duration.ofMillis(1200));
}
~~~

Nếu giai đoạn này hết thời gian, lỗi có thể được xử lý riêng hoặc truyền lên deadline tổng. Hãy tránh đặt nhiều timeout giống nhau ở mọi layer mà không có ngân sách rõ ràng; điều đó làm khó xác định timeout nào thực sự kích hoạt.

### 3.3. Mono.timeout và Flux.timeout có semantics khác nhau

Với Mono, timeout thường giới hạn thời gian chờ một kết quả hoặc completion. Với Flux.timeout(Duration), timer được áp dụng giữa các tín hiệu: nếu không có phần tử tiếp theo trong khoảng thời gian, nó timeout. Đây thường là **idle/inter-signal timeout**, không phải tổng thời lượng tối đa của toàn stream.

Ví dụ:

~~~java
return orderRepository.findAllByCustomerId(customerId)
        .timeout(Duration.ofSeconds(3));
~~~

Nếu mỗi hàng được phát cách nhau dưới 3 giây, stream có thể kéo dài hơn 3 giây mà không timeout. Nếu cần giới hạn tổng thời lượng stream, phải thiết kế deadline tổng riêng. take(Duration) có thể kết thúc stream sau một khoảng thời gian nhưng hoàn tất bình thường; nó không tự biểu diễn lỗi timeout. Hãy chọn semantics theo hợp đồng API.

### 3.4. Không dùng timeout để cắt dữ liệu một cách âm thầm

Nếu API trả danh sách và timeout giữa stream, không nên tự động trả một phần kết quả như thể truy vấn hoàn tất đầy đủ. Cần xác định API có hỗ trợ partial result hay không. Với dữ liệu cần tính đầy đủ, hãy phát lỗi và để response không bị hiểu nhầm là danh sách hoàn chỉnh.

## 4. Dùng deadline thay vì reset lại toàn bộ thời gian ở mỗi layer

Một lỗi thiết kế là mỗi service đặt timeout 2 giây riêng:

~~~text
HTTP handler: 2 giây
    -> Order service: 2 giây
        -> Customer service: 2 giây
            -> Repository: 2 giây
~~~

Các timeout này không tạo thành deadline 2 giây cho request. Nếu các bước chạy tuần tự, tổng thời gian có thể vượt xa 2 giây.

Nên tạo một deadline ở request boundary và truyền phần thời gian còn lại xuống các dependency. Trong một process, có thể dùng đồng hồ monotonic System.nanoTime() để tránh sai lệch khi đồng hồ hệ thống được điều chỉnh.

### 4.1. Kiểu deadline cục bộ

~~~java
public record RequestDeadline(long expiresAtNanos) {

    public static RequestDeadline after(Duration budget) {
        return new RequestDeadline(
                System.nanoTime() + budget.toNanos());
    }

    public Duration remaining() {
        long nanos = expiresAtNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    public Duration requireRemaining() {
        Duration remaining = remaining();
        if (remaining.isZero() || remaining.isNegative()) {
            throw new DeadlineExceededException();
        }
        return remaining;
    }
}
~~~

Deadline này chỉ có ý nghĩa trong cùng process vì giá trị nanoTime không thể gửi sang máy khác.

### 4.2. Lưu deadline trong Reactor Context

~~~java
public final class DeadlineContext {

    public static final String KEY = "requestDeadline";

    private DeadlineContext() {
    }

    public static Mono<RequestDeadline> current() {
        return Mono.deferContextual(context -> {
            if (!context.hasKey(KEY)) {
                return Mono.error(new IllegalStateException(
                        "Request deadline is missing"));
            }
            return Mono.just(context.get(KEY));
        });
    }

    public static <T> Mono<T> withDeadline(
            Duration budget,
            Mono<T> work) {
        RequestDeadline deadline = RequestDeadline.after(budget);
        return work
                .timeout(deadline.requireRemaining())
                .contextWrite(context -> context.put(KEY, deadline));
    }
}
~~~

Ví dụ trên minh họa deadline trong một pipeline đơn. Trong triển khai thực tế, cần tạo deadline trước khi thực hiện công việc và dùng cùng deadline cho mọi stage. Không tạo deadline mới ở mỗi service nếu muốn bảo toàn ngân sách ban đầu.

### 4.3. Tính timeout còn lại cho từng dependency

~~~java
public Mono<Customer> loadCustomer(Long id) {
    return DeadlineContext.current()
            .flatMap(deadline -> {
                Duration stageLimit = Duration.ofMillis(700);
                Duration remaining = deadline.requireRemaining();
                Duration timeout = remaining.compareTo(stageLimit) < 0
                        ? remaining
                        : stageLimit;

                return customerClient.getCustomer(id)
                        .timeout(timeout);
            });
}
~~~

Stage có giới hạn riêng 700 ms nhưng không được vượt thời gian còn lại của request. Nếu chỉ còn 150 ms, nó nhận tối đa 150 ms.

### 4.4. Truyền deadline qua service khác

System.nanoTime() chỉ dùng trong process hiện tại. Khi gọi HTTP service khác, có thể truyền một remaining budget qua header do hệ thống định nghĩa hoặc dùng deadline mechanism của giao thức đang dùng.

Nếu truyền thời điểm tuyệt đối, hai máy có thể lệch clock. Nếu truyền duration còn lại, thời gian trên network vẫn tiêu thụ ngân sách; service nhận cần trừ thêm phần đã trôi qua hoặc dùng một quy ước deadline thống nhất. Không để mỗi service tự khởi tạo một timeout đầy đủ mới.

## 5. Timeout khi lấy connection từ R2DBC pool

R2DBC pool quản lý connection được tái sử dụng. Khi pool không còn connection khả dụng, request phải chờ connection được trả về hoặc chờ pool tạo connection mới.

R2DBC Pool cho phép cấu hình các giới hạn như:

- maxAcquireTime: thời gian tối đa chờ acquire connection.
- maxCreateConnectionTime: thời gian tối đa tạo connection mới.
- maxIdleTime: thời gian connection idle trước khi bị thu hồi.
- maxLifeTime: tuổi thọ tối đa của connection.
- maxValidationTime: thời gian tối đa kiểm tra connection.

Hai giới hạn đầu ảnh hưởng trực tiếp đến thời gian một request có thể chờ để bắt đầu query. Các giới hạn idle/lifetime phục vụ quản lý vòng đời connection, không phải deadline query.

### 5.1. Cấu hình ConnectionPool

Ví dụ với r2dbc-pool:

~~~java
ConnectionPoolConfiguration configuration =
        ConnectionPoolConfiguration.builder(connectionFactory)
                .initialSize(5)
                .maxSize(30)
                .maxAcquireTime(Duration.ofMillis(250))
                .maxCreateConnectionTime(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofMinutes(5))
                .maxLifeTime(Duration.ofMinutes(30))
                .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

Các giá trị chỉ là ví dụ. API builder và cách khai báo bean phụ thuộc phiên bản r2dbc-pool/Spring Boot. Nếu Spring Boot đã tự cấu hình pool, nên đặt thuộc tính tương ứng qua cấu hình được phiên bản đang dùng hỗ trợ thay vì tạo thêm một pool song song.

### 5.2. maxAcquireTime bảo vệ thời gian chờ pool

Nếu pool có 30 connection và tất cả đang được sử dụng, request mới phải chờ. Khi vượt maxAcquireTime, thao tác acquire thất bại thay vì chờ vô hạn.

Đây là tín hiệu pool đang bão hòa hoặc connection bị giữ quá lâu. Tăng maxAcquireTime có thể chỉ làm queue dài hơn và khiến request timeout ở lớp ngoài.

### 5.3. maxCreateConnectionTime bảo vệ việc mở connection mới

Khi pool cần tạo connection, driver phải kết nối tới database. Nếu database không phản hồi hoặc network có vấn đề, việc tạo connection có thể kéo dài. Giới hạn này khác với thời gian chờ một connection sẵn có trong pool.

Ngoài ra, driver có thể có connection timeout riêng cho TCP/network handshake. Hãy kiểm tra driver và phiên bản đang dùng; không giả định một thuộc tính pool bao phủ mọi giai đoạn DNS, TCP, TLS và authentication.

### 5.4. Theo dõi pool thay vì chỉ tăng giới hạn

Khi gặp acquire timeout, kiểm tra:

- Active/acquired connection có thường xuyên chạm maxSize không?
- Pending acquire có tăng không?
- Connection hold time trung bình và p95 là bao nhiêu?
- Query hoặc transaction nào giữ connection lâu?
- Có gọi HTTP service hoặc thực hiện công việc CPU trong lúc giữ transaction không?
- Tổng pool size của tất cả replica có vượt khả năng database không?

Pool lớn hơn có thể tăng tải lên database và làm mọi query chậm hơn. Hãy điều chỉnh sau khi hiểu nguyên nhân.

## 6. Timeout khi tạo kết nối database

Connection creation có thể bao gồm DNS lookup, TCP connect, TLS handshake, xác thực và khởi tạo session. Một số phần được điều khiển bởi driver hoặc hệ điều hành, không phải tất cả đều nằm trong maxAcquireTime.

Hãy kiểm tra các connection options mà R2DBC driver hỗ trợ, ví dụ connect timeout. Tên option, kiểu dữ liệu và phạm vi hiệu lực phụ thuộc driver. Không sao chép một cấu hình JDBC như socketTimeout sang R2DBC nếu driver không hỗ trợ option đó.

### 6.1. Tách lỗi tạo connection khỏi lỗi query

Nếu connection chưa được tạo, database chưa nhận statement của request đó. Nếu connection đã có và query bắt đầu, lỗi có thể xuất hiện trong lúc thực thi hoặc đọc kết quả. Hai trường hợp cần metric và xử lý khác nhau.

Log/trace nên ghi nhận phase:

- Pool acquire.
- Connection creation.
- Statement execution.
- Result consumption.
- Transaction commit/rollback.

Không log credential hoặc URL chứa password.

### 6.2. Timeout connection không thay thế health check

Connection timeout bảo vệ request khỏi chờ vô hạn. Health check giúp phát hiện dependency không khỏe và điều phối traffic. Hai cơ chế bổ sung cho nhau; health check không nên mở quá nhiều connection mới hoặc chạy query nặng liên tục.

## 7. Giới hạn thời gian thực thi SQL

Một query có thể chậm do execution plan, lock wait, I/O, dữ liệu lớn hoặc database quá tải. Nếu chỉ dùng Mono.timeout, ứng dụng có thể ngừng chờ nhưng database chưa chắc đã dừng statement.

Nên có giới hạn phía database/statement khi driver hỗ trợ, đặc biệt với query có thể chạy lâu hoặc endpoint có deadline chặt.

### 7.1. Statement timeout trong R2DBC SPI

R2DBC SPI 1.0 có API Connection.setStatementTimeout(Duration) ở các driver hỗ trợ. Mức hỗ trợ và thời điểm áp dụng phụ thuộc driver/database; cần kiểm tra tài liệu driver thực tế và kiểm thử thay vì giả định mọi implementation đều có cùng hành vi.

Nếu dùng connection-level timeout, hãy thiết lập trên connection đang thực hiện statement và bảo đảm giá trị được áp dụng đúng phạm vi. Với pooled connection, cần tránh để timeout của request trước rò sang request sau; reset hoặc quản lý scope theo transaction/connection lifecycle.

### 7.2. PostgreSQL statement_timeout

PostgreSQL hỗ trợ cấu hình statement_timeout. Có thể đặt giá trị transaction-local để chỉ áp dụng trong transaction hiện tại:

~~~sql
SET LOCAL statement_timeout = '1200ms';
~~~

Hoặc dùng set_config:

~~~sql
SELECT set_config('statement_timeout', '1200ms', true);
~~~

Tham số cuối true yêu cầu setting có hiệu lực trong transaction hiện tại. Lệnh thiết lập và query cần chạy trên cùng transaction/connection.

### 7.3. Thiết lập PostgreSQL timeout trong reactive transaction

Ví dụ với DatabaseClient và TransactionalOperator:

~~~java
public Mono<Order> findWithStatementBudget(Long orderId) {
    Mono<Void> setStatementTimeout = databaseClient
            .sql("SET LOCAL statement_timeout = '1200ms'")
            .fetch()
            .rowsUpdated()
            .then();

    Mono<Order> query = orderRepository.findById(orderId);

    return transactionalOperator.transactional(
            setStatementTimeout.then(query));
}
~~~

Đây là ví dụ PostgreSQL-specific. SET LOCAL chỉ có ý nghĩa trong transaction. Hãy xác nhận transaction manager sử dụng cùng ConnectionFactory và tất cả statement được thực hiện trên connection gắn với transaction. Không chạy lệnh SET trong một publisher độc lập ngoài transaction rồi kỳ vọng connection pool giữ nguyên setting cho query kế tiếp.

### 7.4. Lock timeout khác statement timeout

Một query có thể không tốn CPU nhiều nhưng chờ lock. Database thường có cấu hình lock wait timeout riêng. Ví dụ PostgreSQL có lock_timeout, trong khi statement_timeout giới hạn thời gian toàn statement.

Nếu chỉ giảm statement timeout, query chờ lock vẫn có thể chiếm phần lớn ngân sách trước khi bị hủy. Có thể đặt lock timeout thấp hơn statement timeout nếu nghiệp vụ không chấp nhận chờ lock lâu.

~~~sql
SET LOCAL lock_timeout = '300ms';
SET LOCAL statement_timeout = '1200ms';
~~~

Các giá trị cần dựa trên SLO và hành vi database. Không dùng lock timeout quá thấp nếu workload có transaction cạnh tranh hợp lệ và thường xuyên.

### 7.5. Query timeout ở database phải được kiểm tra thực tế

Integration test nên chạy một query có thời gian biết trước hoặc cố ý chờ, xác nhận database hủy statement theo giới hạn đã đặt và connection vẫn có thể được tái sử dụng an toàn sau đó.

Không chỉ assert rằng WebFlux trả timeout. Cần kiểm tra query phía database có còn chạy, connection có bị loại khỏi pool và transaction có rollback đúng không.

## 8. Timeout cho transaction

Transaction dài giữ connection và có thể giữ lock, làm giảm capacity của pool/database. Hãy đặt giới hạn transaction phù hợp với nghiệp vụ.

Spring transaction definition có thuộc tính timeout; có thể khai báo trên method:

~~~java
@Transactional(timeout = 3)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(Order.from(command))
            .flatMap(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId()))
                    .thenReturn(saved));
}
~~~

Giá trị timeout ở annotation được tính bằng giây. Hành vi thực thi cụ thể phụ thuộc reactive transaction manager, R2DBC driver và cách transaction timeout được áp dụng. Không nên coi annotation này là thay thế cho statement timeout phía database hoặc deadline tổng của request.

### 8.1. Transaction không nên chờ service HTTP chậm

Tránh:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(Order.from(command))
            .flatMap(saved -> paymentWebClient.authorize(saved)
                    .thenReturn(saved));
}
~~~

Ví dụ này giữ transaction database trong lúc chờ HTTP payment. Nếu payment service chậm, connection và transaction có thể bị giữ lâu.

Hãy cân nhắc lưu order cùng outbox event trong transaction, sau đó xử lý payment bằng workflow/outbox worker. Nếu nghiệp vụ cần đồng bộ, phải đặt timeout ngắn, giới hạn concurrency và thiết kế compensation/idempotency phù hợp.

### 8.2. Timeout/cancellation trong transaction

Khi pipeline bị timeout, cancellation có thể làm transaction manager rollback nếu transaction chưa commit. Nhưng nếu lỗi xảy ra đúng lúc commit hoặc connection bị đứt, caller có thể không biết commit đã thành công hay chưa.

Với thao tác ghi quan trọng, dùng idempotency key hoặc business reference ổn định để caller có thể tra cứu/retry an toàn. Không tạo một lệnh insert mới với key khác chỉ vì request đầu bị timeout.

## 9. Timeout cho HTTP client trong WebFlux

Ứng dụng WebFlux thường gọi service khác bằng WebClient. Cần phân biệt:

- TCP connect timeout: thời gian mở kết nối.
- TLS handshake timeout: thời gian hoàn tất TLS, tùy client/config.
- Response timeout/read timeout: thời gian chờ dữ liệu response theo semantics của client.
- Reactive publisher timeout: thời gian tối đa của toàn thao tác được bọc.

### 9.1. Cấu hình Reactor Netty HttpClient

Ví dụ:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
        .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Connect timeout chỉ giới hạn giai đoạn connect. responseTimeout của Reactor Netty là giới hạn đọc response theo semantics của Reactor Netty, không nên tự động xem nó là tổng deadline cho mọi bước của request.

### 9.2. Thêm timeout tổng cho WebClient publisher

~~~java
public Mono<CustomerResponse> getCustomer(Long customerId) {
    return webClient.get()
            .uri("/customers/{id}", customerId)
            .retrieve()
            .bodyToMono(CustomerResponse.class)
            .timeout(Duration.ofMillis(900));
}
~~~

Timeout tổng này bao phủ publisher từ lúc subscribe, bao gồm các giai đoạn của HTTP exchange nằm trong publisher. Nó không thay thế connect/read timeout vì các timeout riêng giúp phát hiện đúng giai đoạn bị treo.

### 9.3. Timeout của WebClient cần nằm trong deadline request cha

Nếu request cha chỉ còn 200 ms, không nên gọi WebClient với timeout mới 900 ms. Hãy dùng remaining deadline, có thể lấy minimum giữa stage limit và thời gian còn lại.

### 9.4. Retry HTTP cũng tiêu thụ ngân sách

Nếu WebClient retry hai lần, mỗi lần connect/response timeout đều tiêu thụ thời gian. Đặt timeout tổng bao quanh cả retry chain; không reset một deadline đầy đủ cho từng attempt.

Với request ghi hoặc gọi payment, chỉ retry khi operation có semantics idempotent hoặc provider hỗ trợ idempotency key. Timeout không chứng minh server đích chưa xử lý request.

## 10. Timeout ở HTTP server, gateway và client

Timeout inbound có nhiều cấu hình khác nhau:

- Reverse proxy có thể giới hạn thời gian chờ upstream response.
- Load balancer có thể có idle timeout hoặc request timeout.
- HTTP server có thể giới hạn connection, đọc request, ghi response hoặc thời gian idle.
- Application pipeline cần deadline cho use case.
- Client có thể ngừng chờ trước khi server hoàn tất.

Một server connection idle timeout không nhất thiết là tổng thời gian xử lý request. Hãy đọc đúng semantics của server/runtime đang dùng, ví dụ Reactor Netty, Tomcat hoặc Jetty.

### 10.1. Đặt deadline ở request boundary

Có thể dùng filter để gắn deadline vào reactive context hoặc bọc pipeline theo chính sách ứng dụng. Cần cẩn thận vì filter có thể bao gồm cả quá trình ghi response; hãy test với response streaming và cancellation.

Ví dụ minh họa deadline ở application service:

~~~java
public Mono<ServerResponse> handle(ServerRequest request) {
    Mono<OrderResponse> result = orderService.getOrder(
            Long.valueOf(request.pathVariable("id")));

    return result.timeout(Duration.ofMillis(2500))
            .flatMap(body -> ServerResponse.ok().bodyValue(body));
}
~~~

Đây là giới hạn cho publisher nghiệp vụ. Reverse proxy và server vẫn cần cấu hình riêng.

### 10.2. HTTP status khi hết thời gian

Không có một status duy nhất cho mọi timeout:

| Tình huống | Status thường cân nhắc |
| --- | --- |
| Client không gửi request đầy đủ trong thời gian cho phép | 408 Request Timeout |
| Gateway chờ upstream quá lâu | 504 Gateway Timeout |
| Application không thể phục vụ do dependency/capacity tạm thời | 503 Service Unavailable theo API contract |
| Lỗi nội bộ không phân loại được | 500 Internal Server Error |
| Client gửi điều kiện HTTP không còn đúng | 412 Precondition Failed, không phải timeout |

Nếu ứng dụng đóng vai trò gateway tới service khác và dependency timeout, 504 có thể phù hợp. Nếu service tạm thời không khả dụng hoặc quá tải, 503 có thể phù hợp. Hãy dùng một error contract nhất quán và không trả stack trace.

## 11. Kết hợp timeout với retry

Retry có thể giúp vượt qua lỗi tạm thời, nhưng cũng có thể làm request kéo dài hơn deadline và tạo thêm tải trong lúc hệ thống đang quá tải.

Ví dụ retry có giới hạn:

~~~java
Mono<Order> attempt = orderRepository.findById(orderId);

return attempt
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(400))
                .filter(this::isTransientFailure))
        .timeout(Duration.ofSeconds(2));
~~~

Timeout đặt ngoài retry chain giới hạn tổng thời gian của tất cả attempt và backoff. Nếu đặt timeout mới bên trong mỗi lần retry mà không có deadline tổng, tổng thời gian có thể vượt ngân sách.

### 11.1. Không retry mọi timeout

Một timeout có thể là dấu hiệu database hoặc pool đã bão hòa. Retry ngay có thể tạo thêm request chờ và làm tình hình xấu hơn.

Chỉ retry khi:

- Lỗi được phân loại là tạm thời.
- Còn đủ deadline.
- Số lần retry có giới hạn.
- Backoff có giới hạn và có thể thêm jitter.
- Thao tác an toàn khi thực hiện lại.

### 11.2. Không retry pool saturation một cách mù quáng

Nếu pool đã hết connection, retry acquire liên tục làm hàng đợi lớn hơn. Thường nên fail sớm, trả lỗi service unavailable phù hợp và để load shedding/backpressure bảo vệ hệ thống.

### 11.3. Ghi dữ liệu cần idempotency

Nếu timeout xảy ra sau khi database commit nhưng trước khi ứng dụng nhận response, retry một INSERT có thể tạo bản ghi thứ hai. Dùng idempotency key ổn định, unique constraint hoặc business reference để request lặp trả lại kết quả cũ.

Với HTTP provider, truyền cùng idempotency key qua các lần retry nếu provider hỗ trợ. Một reactive timeout không phải bằng chứng request chưa tới service đích.

## 12. Cancellation và resource cleanup

Reactor timeout hủy upstream subscription khi deadline hết. Driver có thể nhận cancellation và dừng truy vấn, nhưng hành vi cụ thể cần được kiểm chứng.

### 12.1. Không nuốt cancellation

Tránh tạo publisher phụ rồi tự subscribe:

~~~java
public Mono<Order> load(Long id) {
    orderRepository.findById(id).subscribe();
    return Mono.just(new Order());
}
~~~

Đường code này tách thao tác database khỏi lifecycle của request. Caller timeout hoặc disconnect không kiểm soát được subscription độc lập.

Hãy trả publisher trong cùng chain để cancellation có thể truyền upstream:

~~~java
public Mono<Order> load(Long id) {
    return orderRepository.findById(id);
}
~~~

### 12.2. Kiểm tra connection sau query timeout

Sau khi statement timeout/cancellation:

- Connection còn hợp lệ hay đã bị đóng?
- Pool có loại connection hỏng không?
- Transaction đã rollback chưa?
- Có query còn chạy trên database không?
- Request tiếp theo có acquire và sử dụng connection bình thường không?

Nếu driver không thể bảo đảm connection ở trạng thái an toàn sau cancellation, nó cần loại connection khỏi pool theo hành vi của driver. Hãy kiểm thử trên database/driver thật.

### 12.3. Client disconnect

Khi client đóng kết nối, server có thể nhận cancellation tùy runtime và thời điểm. Hãy bảo đảm publisher không tiếp tục thực hiện công việc không cần thiết. Với write đã commit, client disconnect không thể đảo ngược dữ liệu; idempotency và trạng thái nghiệp vụ vẫn cần được thiết kế.

## 13. Quan sát timeout trong production

Một metric tổng request_timeout_total chưa đủ để biết bottleneck. Nên phân loại theo phase:

| Metric/log category | Ý nghĩa |
| --- | --- |
| http_request_deadline_exceeded | Deadline end-to-end đã hết |
| webclient_connect_timeout | Không kết nối được service đích đúng hạn |
| webclient_response_timeout | Chờ response quá lâu theo cấu hình client |
| r2dbc_pool_acquire_timeout | Pool không cấp connection đúng hạn |
| r2dbc_connection_create_timeout | Không tạo được connection đúng hạn |
| r2dbc_statement_timeout | Statement vượt giới hạn |
| transaction_timeout | Transaction vượt budget |
| request_cancelled | Request bị hủy do client disconnect hoặc upstream cancellation |

Tên metric là quy ước minh họa; hãy dùng tên phù hợp với instrumentation của dự án.

### 13.1. Ghi thời gian từng giai đoạn

Trace hoặc observation có thể ghi:

- Thời gian acquire connection.
- Thời gian statement execute và consume result.
- Thời gian transaction.
- Thời gian WebClient connect/response.
- Tổng thời gian use case.

Tách biệt thời gian chờ pool và thời gian query giúp tránh tối ưu nhầm thành phần.

### 13.2. Tránh cardinality cao

Không dùng request ID, user ID hoặc tenant ID riêng lẻ làm metric tag nếu số lượng lớn. Dùng trace/log cho từng request và metric tag có tập giá trị giới hạn như operation, dependency, outcome và timeout phase.

### 13.3. Log deadline còn lại

Khi timeout, log deadline/budget ban đầu, remaining time tại dependency, phase thất bại và correlation ID. Không log token, password hoặc dữ liệu nhạy cảm.

## 14. Kiểm thử timeout và cancellation

Nên kiểm tra cả logic reactive lẫn hành vi driver/database. Một unit test timeout không chứng minh database thật sự hủy query.

### 14.1. Unit test Mono.timeout bằng virtual time

~~~java
@Test
void shouldTimeoutWhenPublisherDoesNotRespond() {
    StepVerifier.withVirtualTime(() ->
                    Mono.<String>never()
                            .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

Virtual time phù hợp với operator dựa trên Reactor scheduler. Publisher bên ngoài hoặc driver thật có thể không dùng virtual scheduler, vì vậy không thay thế integration test.

### 14.2. Test timeout tổng bao quanh retry

Tạo publisher attempt có độ trễ xác định và retry theo policy. Xác nhận tổng thời gian bị giới hạn bởi deadline ngoài, không phải timeout được reset cho mỗi attempt.

Kiểm tra cả số lần attempt thực tế để bảo đảm retry không chạy sau khi request đã hết deadline.

### 14.3. Test pool acquire timeout

Với pool nhỏ, giữ tất cả connection bằng các operation test có kiểm soát, sau đó thực hiện một acquire mới. Xác nhận acquire thất bại trong giới hạn đã cấu hình và metric pending/acquire timeout được ghi nhận.

Không để test treo vô hạn; luôn có timeout bảo vệ cho chính test.

### 14.4. Test statement timeout với database thật

Với PostgreSQL, có thể dùng một câu lệnh chờ như SELECT pg_sleep(2) trong transaction có statement_timeout ngắn hơn. Xác nhận:

1. Statement bị hủy theo giới hạn database.
2. Application nhận lỗi timeout tương ứng.
3. Transaction được rollback hoặc kết thúc đúng.
4. Connection sau đó không bị trả về pool trong trạng thái lỗi.
5. Query tiếp theo trên pool vẫn chạy bình thường.

Đây là test đặc thù PostgreSQL. Với database khác, dùng công cụ/query phù hợp của hệ quản trị đó.

### 14.5. Test cancellation khi client disconnect

Tạo endpoint streaming hoặc query có thể kéo dài, sau đó hủy request từ WebTestClient hoặc HTTP client test. Quan sát publisher cancellation, database statement và connection pool. Xác nhận không còn subscription độc lập tiếp tục làm việc.

### 14.6. Test deadline propagation

Gắn deadline ngắn vào request context và tạo nhiều dependency giả lập. Xác nhận dependency sau chỉ nhận phần thời gian còn lại, không nhận lại toàn bộ timeout ban đầu. Chạy test với các nhánh tuần tự và song song.

## 15. Những lỗi thường gặp khi cấu hình timeout

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request chờ lâu dù SQL timeout ngắn | Thời gian chờ pool hoặc service khác không được giới hạn | Đặt timeout riêng cho từng phase và deadline tổng |
| Pool acquire timeout xảy ra trước query | Pool hết connection hoặc connection bị giữ lâu | Theo dõi pending/hold time và tối ưu transaction |
| Tăng acquire timeout làm API chậm hơn | Queue dài hơn thay vì tăng capacity | Giữ budget ngắn, tìm bottleneck và load shed |
| WebClient chờ lâu hơn dự kiến | Chỉ cấu hình connect timeout, thiếu response/overall timeout | Cấu hình connect, response và publisher deadline |
| Mono timeout nhưng database vẫn chạy query | Cancellation không dừng server statement ngay | Dùng statement timeout phía database và kiểm thử driver |
| Flux không timeout dù tổng thời gian dài | Flux.timeout(Duration) là inter-signal timeout | Thiết kế deadline tổng riêng cho stream |
| Retry làm request vượt deadline | Mỗi attempt reset timeout đầy đủ | Bao timeout tổng quanh retry chain và dùng remaining budget |
| Timeout ghi dữ liệu rồi retry tạo bản ghi trùng | Commit có thể thành công dù acknowledgement mất | Idempotency key/unique business key |
| Transaction giữ connection khi gọi HTTP | External call nằm trong transaction | Rút ngắn transaction, outbox/saga hoặc timeout riêng |
| Connection pool có hành vi lạ sau timeout | Connection/session setting hoặc cancellation chưa được reset | Kiểm tra driver và pool lifecycle |
| Gateway trả 504 trước ứng dụng | Gateway timeout ngắn hơn app deadline | Sắp xếp budget và dành thời gian cleanup |
| HTTP server idle timeout bị hiểu là request deadline | Cấu hình chỉ quản lý connection inactivity | Đặt deadline ở application pipeline |
| Database lock wait kéo dài | Chỉ có statement timeout lớn hoặc không có lock timeout | Đặt lock timeout phù hợp với nghiệp vụ |
| Test timeout pass nhưng production vẫn treo | Unit test không chạy driver/database thật | Integration test bằng database production-like |

## 16. Quy trình thiết kế timeout cho một endpoint

1. Xác định SLO và thời gian tối đa caller chờ.
2. Chọn application deadline thấp hơn gateway/client timeout để còn thời gian cleanup.
3. Liệt kê các dependency và xác định bước nào chạy tuần tự, bước nào chạy song song.
4. Chia ngân sách cho HTTP client, pool acquire, connection creation, SQL và transaction.
5. Dùng timeout tổng bao quanh toàn bộ use case.
6. Truyền remaining deadline thay vì tạo timeout mới ở từng layer.
7. Cấu hình statement/lock timeout phía database nếu được hỗ trợ.
8. Đảm bảo retry có giới hạn, nằm trong deadline và an toàn về idempotency.
9. Theo dõi timeout theo phase, pool metrics và database health.
10. Kiểm thử timeout, cancellation, rollback và connection reuse bằng driver/database thật.

## 17. Ví dụ cấu hình timeout theo một ngân sách thống nhất

Giả sử endpoint đọc order có application budget 2.500 ms:

~~~text
Client timeout:                3.200 ms
Gateway upstream timeout:     3.000 ms
Application deadline:         2.500 ms
  |
  +-- R2DBC pool acquire:       250 ms
  |
  +-- Database transaction:   1.600 ms
  |     |
  |     +-- Statement timeout: 1.200 ms
  |     +-- Lock timeout:       300 ms
  |
  +-- WebClient dependency:     700 ms
  |
  +-- Mapping/response/cleanup: phần ngân sách còn lại
~~~

Trong ví dụ này, R2DBC và WebClient có thể chạy tuần tự hoặc song song tùy use case. Nếu chạy tuần tự, cần điều chỉnh các stage limit để tổng worst-case không vượt application deadline. Nếu chạy song song, deadline tổng vẫn giới hạn toàn bộ nhóm.

Không sao chép các số này vào production mà chưa đo. Hãy lấy p95/p99, SLO và capacity thực tế để chọn giới hạn.

## 18. Checklist vận hành

- [ ] Có deadline end-to-end cho từng nhóm API quan trọng.
- [ ] Gateway/proxy/client timeout được sắp xếp với application deadline.
- [ ] Timeout từng dependency không reset lại ngân sách đầy đủ.
- [ ] Có giới hạn R2DBC pool acquire.
- [ ] Có giới hạn connection creation theo khả năng driver.
- [ ] Pool idle/lifetime được hiểu đúng là quản lý connection, không phải query deadline.
- [ ] Có statement timeout phía database hoặc driver khi phù hợp.
- [ ] Có lock timeout nếu nghiệp vụ không chấp nhận chờ lock lâu.
- [ ] Transaction ngắn và không chờ service ngoài không cần thiết.
- [ ] WebClient có connect, response và overall timeout phù hợp.
- [ ] Retry có giới hạn và nằm trong deadline tổng.
- [ ] Write retry có idempotency/business key.
- [ ] Cancellation được truyền trong cùng reactive chain.
- [ ] Có metric phân biệt pool, connect, SQL, HTTP và application timeout.
- [ ] Có integration test với driver/database thật.
- [ ] Có test connection reuse sau statement timeout/cancellation.

## 19. Sơ đồ xử lý timeout xuyên suốt

~~~mermaid
flowchart TD
    A[Client gửi HTTP request] --> B[Gateway timeout budget]
    B --> C[Application tạo deadline]
    C --> D[Reactive service]
    D --> E[Acquire R2DBC connection]
    E --> F{Có connection đúng hạn?}
    F -->|Không| G[Pool acquire timeout]
    F -->|Có| H[Thực thi SQL]
    H --> I{Statement hoàn tất đúng hạn?}
    I -->|Không| J[Statement timeout/cancel]
    I -->|Có| K[Gọi dependency nếu cần]
    K --> L{Dependency đúng hạn?}
    L -->|Không| M[HTTP dependency timeout]
    L -->|Có| N[Mapping và tạo response]
    G --> O[Rollback/cleanup và ánh xạ lỗi]
    J --> O
    M --> O
    N --> P[Trả response trước gateway deadline]
    O --> Q[Trả lỗi trước gateway deadline nếu còn kết nối]
~~~

## 20. Kết luận

Kiểm soát timeout trong Spring Data R2DBC không chỉ là gọi Mono.timeout. Một request đi qua HTTP, application, connection pool, connection creation, SQL, transaction và có thể nhiều service phụ trợ. Mỗi giai đoạn cần giới hạn đúng semantics; deadline tổng phải bao phủ toàn bộ use case và có khoảng dự phòng cho cleanup/response.

Hãy phân biệt pool acquire timeout, connection creation timeout, statement timeout, transaction timeout, HTTP connect/read timeout và application deadline. Dùng Reactor timeout để giới hạn publisher, cấu hình pool để tránh chờ connection vô hạn, dùng statement/lock timeout phía database khi driver hỗ trợ và kiểm tra cancellation thực tế. Với Flux, phân biệt idle timeout giữa các phần tử với tổng thời lượng stream.

Retry phải nằm trong deadline chung, chỉ áp dụng cho lỗi tạm thời và dùng lại idempotency key cho thao tác ghi. Timeout không chứng minh database chưa commit hoặc service đích chưa xử lý request. Cuối cùng, theo dõi timeout theo từng phase và kiểm thử bằng database/driver thật để bảo đảm query được dừng, transaction được xử lý đúng và connection có thể tái sử dụng an toàn.
