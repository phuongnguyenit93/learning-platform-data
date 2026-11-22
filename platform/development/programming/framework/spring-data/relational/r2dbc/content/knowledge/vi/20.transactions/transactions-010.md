# Hủy đăng ký, thời gian chờ và tác động đến giao dịch

Trong ứng dụng Spring Data R2DBC, các thao tác database được biểu diễn bằng publisher reactive như Mono và Flux. Publisher có thể kết thúc bình thường, phát lỗi hoặc nhận tín hiệu hủy (cancellation) từ subscriber. Một thao tác cũng có thể vượt quá thời gian chờ mà ứng dụng cho phép.

Cancellation và timeout có thể ảnh hưởng trực tiếp đến transaction đang mở. Với reactive transaction được quản lý đúng cách, Spring có thể rollback khi publisher bị hủy hoặc phát lỗi trước khi commit. Tuy nhiên, hủy subscription không thể đảo ngược một transaction đã commit, và tín hiệu timeout ở ứng dụng không phải lúc nào cũng chứng minh database đã dừng câu SQL ngay lập tức.

Muốn xử lý đúng, cần phân biệt thời điểm hủy, ranh giới transaction, loại timeout và khả năng hỗ trợ của driver/database.

## 1. Vòng đời của một publisher reactive

Một thao tác R2DBC thường trả về Mono hoặc Flux. Publisher mô tả công việc; thao tác thường chỉ được thực thi khi có subscriber đăng ký.

Ví dụ:

~~~java
Mono<Long> update = databaseClient.sql("""
        UPDATE customer
        SET active = FALSE
        WHERE id = :id
        """)
    .bind("id", customerId)
    .fetch()
    .rowsUpdated();
~~~

Tại thời điểm tạo biến update, câu SQL chưa nhất thiết được gửi xuống database. Khi publisher được subscribe, quá trình lấy connection, gửi SQL và nhận kết quả mới diễn ra.

Theo Reactive Streams, subscription có ba tín hiệu kết thúc đáng chú ý:

- **onComplete**: publisher hoàn tất bình thường.
- **onError**: publisher kết thúc do lỗi.
- **cancel**: subscriber yêu cầu publisher dừng phát dữ liệu và ngừng công việc nếu có thể.

Cancellation là tín hiệu điều khiển từ subscriber, không phải một giá trị được phát tới downstream và cũng không phải một lỗi onError. Vì vậy, code chỉ xử lý onError sẽ không tự động quan sát được mọi trường hợp hủy.

### 1.1. Những tình huống có thể phát sinh cancellation

Cancellation có thể xuất hiện khi:

- Client HTTP ngắt kết nối hoặc hủy request.
- Người dùng rời khỏi màn hình và ứng dụng hủy tác vụ.
- Một publisher phía trên không còn cần dữ liệu.
- Code gọi dispose() trên subscription.
- Dùng các toán tử chỉ lấy một phần dữ liệu như take(), next() hoặc first().
- Một timeout operator hủy publisher nguồn khi hết thời gian.
- Một tác vụ tổng hợp bị hủy vì một nhánh khác đã đủ kết quả hoặc đã thất bại.

Không phải mọi cancellation đều là lỗi. Ví dụ, client đóng kết nối có thể khiến request không còn cần kết quả. Nhưng nếu publisher đang nằm trong transaction ghi dữ liệu, cancellation cần được xử lý theo đúng ranh giới transaction.

## 2. Phân biệt cancellation, timeout và lỗi database

Ba khái niệm này liên quan nhưng không giống nhau:

| Tình huống | Điều gì xảy ra | Tín hiệu ứng dụng thường thấy |
|---|---|---|
| Cancellation | Subscriber yêu cầu dừng subscription | Tín hiệu cancel, không phải onError |
| Reactive timeout | Hết deadline của Reactor operator | TimeoutException tới downstream và cancellation tới upstream |
| Database/driver timeout | Driver hoặc database dừng thao tác quá thời gian cho phép | Thường phát lỗi do driver/database |
| Connection acquire timeout | Không lấy được connection từ pool đúng hạn | Lỗi timeout khi chờ pool |
| Connect timeout | Không thiết lập được kết nối tới database đúng hạn | Lỗi kết nối |
| Transaction timeout | Transaction vượt giới hạn mà transaction manager hoặc hệ thống hỗ trợ | Hành vi phụ thuộc transaction manager/driver/database |

Một request có thể gặp nhiều lớp timeout. Ví dụ, request có deadline 3 giây nhưng pool cần 4 giây mới cấp được connection. Ứng dụng có thể timeout trước khi câu SQL được gửi xuống database.

### 2.1. Cancellation không tự động có nghĩa SQL đã dừng

Khi subscriber cancel, tín hiệu được truyền ngược qua chuỗi reactive. Driver có thể cố gắng hủy statement đang chạy hoặc giải phóng tài nguyên liên quan, nhưng khả năng và thời điểm dừng câu SQL phụ thuộc R2DBC driver, database và trạng thái thao tác.

Vì vậy, không nên suy luận rằng:

- Subscriber đã cancel thì database chắc chắn chưa thực hiện câu SQL.
- Mono.timeout() đã phát TimeoutException thì server đã dừng xử lý ngay lập tức.
- Client không nhận response nghĩa là transaction chắc chắn rollback.

Nếu lệnh DML đã được database thực thi và transaction đã commit, cancellation đến sau đó không thể hoàn tác dữ liệu đã commit.

## 3. Cancellation tác động đến reactive transaction như thế nào?

Reactive transaction được quản lý quanh một chuỗi publisher. Với Spring, transaction thường bắt đầu khi publisher được subscribe, các thao tác database tham gia cùng transaction context, sau đó transaction được commit khi chuỗi hoàn tất bình thường hoặc rollback khi chuỗi kết thúc theo cách cần rollback.

Spring Framework hỗ trợ rollback khi reactive transactional publisher bị cancellation. Từ Spring Framework 5.3, cancellation signal trong reactive transaction được xử lý như một lý do để rollback transaction đang hoạt động. Điều này quan trọng vì cancellation không đi qua nhánh onError thông thường.

Ví dụ service dùng @Transactional:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Order> createOrder(Order order) {
        return orderRepository.save(order)
            .flatMap(saved ->
                auditRepository.recordCreated(saved.id())
                    .thenReturn(saved)
            );
    }
}
~~~

Giả sử thao tác lưu order đã chạy nhưng publisher bị hủy trước khi transaction commit. Spring transaction infrastructure có thể rollback transaction đang mở. Khi đó các thay đổi thuộc cùng transaction được hoàn tác theo semantics của database.

Điều kiện quan trọng:

- Phương thức phải thực sự chạy trong reactive transaction.
- Repository/template/DatabaseClient phải tham gia cùng transaction manager và ConnectionFactory.
- Publisher phải được trả về và duy trì trong cùng reactive chain.
- Cancellation phải đến trước khi transaction đã commit xong.
- Driver và database phải hỗ trợ transaction/rollback cho thao tác đó.

### 3.1. Transaction commit khi nào?

Với reactive transaction, commit thường xảy ra khi publisher trong transaction hoàn tất bình thường. Nếu publisher phát lỗi và lỗi không bị xử lý thành một kết quả thành công, transaction manager có thể rollback theo rollback rules.

Cancellation trước commit khiến transaction manager thực hiện rollback. Nhưng nếu commit đã hoàn tất, một cancellation đến sau đó không thể đảo ngược kết quả.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Subscribe publisher"]
    B["Bắt đầu transaction"]
    C["Thực thi SQL trong transaction"]
    D{"Publisher kết thúc thế nào?"}
    E["onComplete"]
    F["Commit"]
    G["onError"]
    H["Rollback"]
    I["cancel"]
    J["Rollback transaction đang mở"]
    K["Kết quả transaction"]

    A --> B --> C --> D
    D --> E --> F --> K
    D --> G --> H --> K
    D --> I --> J --> K
~~~

Đây là mô hình khái niệm. Thời điểm chính xác của commit/rollback và việc driver hủy statement đang chạy còn phụ thuộc implementation.

### 3.2. Dùng TransactionalOperator

Nếu muốn xác định transaction bằng chương trình, dùng TransactionalOperator:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PaymentService {

    private final TransactionalOperator transactionalOperator;
    private final PaymentRepository paymentRepository;
    private final LedgerRepository ledgerRepository;

    public PaymentService(
            TransactionalOperator transactionalOperator,
            PaymentRepository paymentRepository,
            LedgerRepository ledgerRepository) {
        this.transactionalOperator = transactionalOperator;
        this.paymentRepository = paymentRepository;
        this.ledgerRepository = ledgerRepository;
    }

    public Mono<Payment> pay(Payment payment) {
        Mono<Payment> work =
            paymentRepository.save(payment)
                .flatMap(saved ->
                    ledgerRepository.record(saved)
                        .thenReturn(saved)
                );

        return transactionalOperator.transactional(work);
    }
}
~~~

TransactionalOperator bao quanh publisher work. Nếu publisher hoàn tất bình thường, transaction được commit; nếu publisher phát lỗi hoặc bị hủy trước commit, transaction manager xử lý rollback.

Không tạo transaction bằng cách tự gọi subscribe() bên trong service. Khi tự subscribe, publisher có thể chạy tách khỏi transaction context của caller và caller không còn điều khiển được thời điểm hoàn tất.

## 4. Dùng timeout trong reactive pipeline

Reactor cung cấp toán tử timeout để giới hạn thời gian chờ tín hiệu từ publisher.

Ví dụ:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<Order> result =
    orderRepository.findById(orderId)
        .timeout(Duration.ofSeconds(3));
~~~

Nếu publisher không phát tín hiệu phù hợp trong thời gian cho phép, timeout operator phát TimeoutException xuống downstream và cancel publisher nguồn.

Với thao tác ghi trong transaction, có thể đặt timeout quanh công việc transaction:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.recordCreated(saved.id())
                .thenReturn(saved)
        )
        .timeout(Duration.ofSeconds(5));
}
~~~

Nếu timeout xảy ra trước khi transaction commit, lỗi timeout truyền qua publisher và transaction có thể rollback. Nếu timeout được đặt ở phía caller bên ngoài phương thức transactional, nó cancel publisher được transaction interceptor quản lý; Spring có thể nhận cancellation và rollback transaction còn mở.

Timeout operator là một deadline ở tầng reactive. Nó không tự cấu hình server-side statement timeout và không bảo đảm database đã dừng xử lý câu SQL đúng tại thời điểm TimeoutException được phát ra.

### 4.1. Chọn timeout fallback cẩn thận

Reactor cho phép cung cấp publisher thay thế khi timeout:

~~~java
Mono<Order> result =
    orderRepository.findById(orderId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.error(new RequestTimedOutException())
        );
~~~

Một điểm quan trọng là cách xử lý lỗi timeout bên trong transaction. Nếu ứng dụng dùng onErrorResume để thay timeout bằng một kết quả bình thường trước khi transaction manager quan sát publisher kết thúc, transaction có thể được xem là hoàn tất thành công và commit.

Ví dụ cần thận trọng:

~~~java
@Transactional
public Mono<String> updateWithFallback(Long id) {
    return updateOrder(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.just("Timed out")
        );
}
~~~

Trong ví dụ này, timeout đã được chuyển thành một giá trị bình thường. Transaction manager có thể thấy publisher hoàn tất bình thường, không còn lỗi để kích hoạt rollback. Nếu timeout phải khiến transaction rollback, hãy để lỗi đi qua ranh giới transaction hoặc đánh dấu transaction rollback-only bằng cơ chế phù hợp.

Không nuốt lỗi timeout nếu nghiệp vụ yêu cầu rollback.

### 4.2. Timeout toàn request và timeout một thao tác

Timeout toàn request giới hạn tổng thời gian của chuỗi xử lý. Timeout từng thao tác database giới hạn thời gian chờ của một publisher cụ thể.

Ví dụ:

~~~java
Mono<OrderSummary> response =
    orderRepository.findById(orderId)
        .timeout(Duration.ofSeconds(2))
        .flatMap(order ->
            paymentRepository.findByOrderId(order.id())
                .timeout(Duration.ofSeconds(2))
                .map(payment -> toSummary(order, payment))
        )
        .timeout(Duration.ofSeconds(5));
~~~

Hai timeout 2 giây áp dụng riêng cho từng thao tác; timeout 5 giây giới hạn toàn chuỗi. Tổng thời gian không đơn giản luôn bằng 4 giây vì các thao tác có thể chạy tuần tự, có thể có thời gian mapping hoặc scheduling và timeout tổng thể có thể hết trước timeout con.

Đặt timeout theo yêu cầu latency của từng tầng, tránh đặt nhiều timeout mâu thuẫn hoặc quá ngắn khiến request thường xuyên bị hủy.

## 5. Các lớp timeout trong kết nối R2DBC

Một ứng dụng có thể có nhiều loại timeout độc lập. Cần cấu hình đúng tầng thay vì dùng một giá trị duy nhất cho mọi vấn đề.

| Loại timeout | Giới hạn điều gì? | Ví dụ nguyên nhân |
|---|---|---|
| Pool acquire timeout | Thời gian chờ mượn connection từ pool | Pool hết connection |
| Connect timeout | Thời gian thiết lập kết nối mới | Mạng/DNS/database không phản hồi |
| Statement/query timeout | Thời gian database/driver cho phép câu SQL chạy | Query chậm hoặc lock lâu |
| Transaction timeout | Thời gian transaction được phép tồn tại | Transaction giữ lock quá lâu |
| Reactive timeout | Thời gian chờ publisher phát tín hiệu | Ứng dụng không nhận kết quả trong deadline |
| HTTP/request timeout | Tổng thời gian xử lý request | Toàn bộ pipeline vượt SLA |

### 5.1. Pool acquire timeout

Nếu dùng r2dbc-pool, có thể cấu hình thời gian chờ lấy connection. Trong Spring Boot, một cấu hình thường gặp là:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      max-size: 20
      max-acquire-time: 3s
~~~

max-acquire-time giới hạn thời gian chờ lấy connection từ pool. Nó không giới hạn thời gian câu SQL chạy sau khi connection đã được cấp.

Tên và khả năng cấu hình phụ thuộc phiên bản Spring Boot và r2dbc-pool. Hãy kiểm tra property reference đúng phiên bản dự án.

### 5.2. Connect timeout

Connect timeout giới hạn thời gian thiết lập connection mới tới database. Nó có thể được cấu hình qua option của driver hoặc ConnectionFactoryOptions nếu driver hỗ trợ.

Connect timeout không thay thế pool acquire timeout. Nếu pool đã có connection nhàn rỗi, thao tác có thể không cần tạo kết nối mới; ngược lại, nếu pool cần tạo connection, connect timeout mới có ý nghĩa.

### 5.3. Statement/query timeout

Statement timeout nhằm giới hạn thời gian database hoặc driver xử lý một câu SQL. Khả năng cấu hình phụ thuộc R2DBC driver và hệ quản trị.

Một số database cung cấp cấu hình ở cấp session, role hoặc câu lệnh. Ví dụ PostgreSQL có setting statement_timeout. Cách cấu hình cụ thể cần dựa vào tài liệu PostgreSQL và driver đang dùng.

Không có một cách cấu hình statement timeout duy nhất có thể áp dụng giống nhau cho mọi R2DBC driver. Hãy xác định rõ:

- Driver có hỗ trợ timeout ở cấp statement hay không.
- Database có setting server-side nào.
- Timeout có áp dụng khi chờ lock hay không.
- Khi timeout, driver phát lỗi gì và connection còn sử dụng được không.
- Transaction hiện tại có cần rollback hay được đánh dấu lỗi hay không.

### 5.4. Reactive timeout không phải statement timeout

Ví dụ:

~~~java
databaseClient.sql("SELECT * FROM large_table")
    .fetch()
    .all()
    .timeout(Duration.ofSeconds(2));
~~~

Đoạn code giới hạn thời gian publisher được phép chờ tín hiệu theo Reactor. Khi hết hạn, Reactor phát TimeoutException và cancel upstream. Nó không phải cấu hình portable để yêu cầu database server dừng query sau đúng 2 giây.

Nếu cần bảo vệ database khỏi query chạy quá lâu, hãy dùng statement timeout ở driver/database khi có hỗ trợ, đồng thời có reactive deadline ở tầng ứng dụng để giới hạn thời gian request.

## 6. Cancellation khi thao tác ghi nằm ngoài transaction

Nếu một câu lệnh DML chạy ở chế độ auto-commit hoặc không nằm trong transaction do ứng dụng quản lý, cancellation không cung cấp cùng bảo đảm rollback như một transaction đang mở.

Ví dụ:

~~~java
Mono<Long> update =
    databaseClient.sql("""
            UPDATE account
            SET balance = balance - :amount
            WHERE id = :id
            """)
        .bind("amount", amount)
        .bind("id", accountId)
        .fetch()
        .rowsUpdated();
~~~

Nếu câu lệnh được database thực thi và commit theo chế độ auto-commit trước khi cancellation được xử lý, dữ liệu đã thay đổi. Subscriber có thể không nhận được count, nhưng điều đó không chứng minh thao tác chưa xảy ra.

Đây là tình huống quan trọng với API HTTP: client có thể timeout hoặc ngắt kết nối trong khi database đã hoàn tất ghi. Client thấy request thất bại, nhưng server có thể đã thực hiện nghiệp vụ.

Nếu nhiều thao tác phải cùng thành công hoặc cùng rollback, hãy đặt chúng trong transaction. Tuy nhiên, ngay cả với transaction, nếu commit đã hoàn tất trước khi client nhận response, cancellation đến sau commit vẫn không thể hoàn tác.

## 7. Timeout và trạng thái kết quả không chắc chắn

Một timeout ở client có thể tạo ra trạng thái “không biết kết quả”:

1. Ứng dụng gửi lệnh ghi.
2. Database thực thi và có thể commit.
3. Response bị chậm hoặc mất trên đường về.
4. Client hết thời gian chờ.
5. Client không biết lệnh đã commit hay chưa.

Đây không giống một lỗi xác nhận chắc chắn rằng lệnh không thực hiện. Vì vậy, retry mù một thao tác không idempotent có thể tạo dữ liệu trùng hoặc thực hiện nghiệp vụ hai lần.

Ví dụ, nếu client gửi lệnh “trừ 100 khỏi số dư” và timeout, gửi lại lệnh có thể trừ thêm 100 nếu lần đầu đã commit.

### 7.1. Thiết kế thao tác idempotent

Một thao tác idempotent có thể được lặp lại mà không làm thay đổi kết quả nghiệp vụ ngoài lần thực hiện đầu tiên.

Một số cách thiết kế:

- Dùng idempotency key duy nhất cho request tạo thanh toán/đơn hàng.
- Tạo unique constraint trên mã nghiệp vụ.
- Lưu request key và kết quả xử lý trong cùng transaction.
- Dùng câu lệnh cập nhật có điều kiện để ngăn áp dụng một trạng thái nhiều lần.
- Truy vấn lại trạng thái theo ID/idempotency key trước khi quyết định retry.

Ví dụ schema lưu idempotency key:

~~~sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

Khi request được gửi lại với cùng idempotency key, unique constraint ngăn tạo hai bản ghi cho cùng yêu cầu. Ứng dụng có thể đọc lại trạng thái đã lưu và trả về kết quả trước đó.

### 7.2. Retry cần đặt đúng ranh giới transaction

Reactor có retry operators, nhưng vị trí retry ảnh hưởng số lần subscription và transaction.

Ví dụ khái niệm:

~~~java
Mono<Order> work =
    orderRepository.save(order)
        .flatMap(saved -> reserveInventory(saved));

return transactionalOperator.transactional(work)
    .retryWhen(retrySpec);
~~~

Retry đặt bên ngoài publisher transaction thường có thể subscribe lại toàn bộ đơn vị transaction, tùy cách publisher và transaction manager được cấu hình. Nếu đặt retry bên trong transaction, thao tác có thể được thử lại trong cùng transaction sau một lỗi mà database/driver đã khiến transaction không còn hợp lệ.

Không retry tự động mọi lỗi. Chỉ retry lỗi tạm thời được xác định rõ, bảo đảm thao tác idempotent và hiểu transaction boundary. Timeout cũng không luôn chứng minh thao tác chưa commit, vì vậy retry sau timeout cần chính sách riêng.

## 8. Quan sát cancellation và timeout

Cancellation không đi qua onError. Để ghi nhận cả completion, error và cancel, có thể dùng doFinally:

~~~java
import reactor.core.publisher.SignalType;

return orderRepository.findById(orderId)
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            log.info("Order lookup was cancelled");
        }
    });
~~~

Hoặc dùng doOnCancel nếu chỉ cần hành động khi upstream nhận cancel:

~~~java
return repository.findById(id)
    .doOnCancel(() -> log.debug("Lookup cancelled"));
~~~

Những callback này phù hợp cho logging hoặc metrics. Không dùng chúng làm cơ chế rollback thủ công thay cho Spring transaction manager.

Nên theo dõi:

- Số lượng cancellation theo endpoint và loại thao tác.
- Số timeout theo pool acquire, connect, query và request.
- Thời gian lấy connection và thời gian thực thi SQL.
- Số transaction rollback do lỗi và do cancellation.
- Pool active/idle/pending acquire.
- Các request timeout nhưng thao tác ghi có thể đã commit.
- Lỗi driver và database sau khi cancellation.

Log cần có correlation/request ID để nối request với truy vấn và transaction. Tránh ghi credentials hoặc dữ liệu nhạy cảm vào log.

## 9. Giải phóng connection và tài nguyên

Khi dùng DatabaseClient, Spring quản lý việc lấy và giải phóng connection theo vòng đời thao tác và transaction. Khi publisher bị cancel, hạ tầng quản lý tài nguyên được thông báo để giải phóng connection hoặc trả nó về pool theo khả năng driver.

Nếu dùng trực tiếp R2DBC SPI, ứng dụng phải bảo đảm connection được đóng trong cả ba trường hợp: hoàn tất bình thường, lỗi và cancellation. Có thể dùng Reactor usingWhen:

~~~java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

Mono<Integer> ping(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Mono.from(
                connection.createStatement("SELECT 1").execute()
            )
            .flatMap(result ->
                Mono.from(result.map((row, metadata) ->
                    row.get(0, Integer.class)
                ))
            ),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
~~~

usingWhen có nhánh cleanup cho hoàn tất, lỗi và cancellation. Đây là ví dụ truy cập SPI trực tiếp; khi dùng DatabaseClient hoặc Spring Data repository, thông thường không cần tự quản lý connection như vậy.

Không giữ Connection trong singleton service hoặc chia sẻ connection giữa nhiều request. Hãy để framework hoặc resource operator quản lý vòng đời.

## 10. Những toán tử dễ gây cancellation ngoài dự kiến

Một số toán tử chỉ cần một phần dữ liệu có thể cancel publisher nguồn sau khi đã lấy đủ kết quả:

~~~java
Flux<Customer> source = repository.findAll();

Mono<Customer> firstCustomer = source.next();
~~~

next() lấy phần tử đầu tiên rồi cancel nguồn vì không cần các phần tử còn lại. Nếu source đang nằm trong reactive transaction, cancellation có thể làm transaction rollback theo quy tắc reactive transaction của Spring.

Tương tự, take(n) có thể cancel upstream sau khi lấy đủ n phần tử. Nếu transaction được thiết kế để đọc toàn bộ dữ liệu và thực hiện ghi sau đó, việc cắt publisher sớm có thể làm transaction bị rollback ngoài dự kiến.

Từ Spring Framework 5.3, cancellation signal trong reactive transaction khiến transaction rollback. Do đó, tránh dùng next(), take() hoặc các toán tử cắt nguồn trong phạm vi transactional publisher nếu ý định thực sự là commit sau khi lấy một phần kết quả. Hãy thiết kế ranh giới transaction phù hợp với số dữ liệu cần đọc.

Không phải mọi use case đều cần transaction bao quanh một luồng đọc dài. Với truy vấn đọc chỉ cần phần tử đầu, hãy cân nhắc không mở transaction rộng nếu không cần tính nhất quán nhiều thao tác.

## 11. Transaction và timeout của HTTP request

Trong ứng dụng WebFlux, request có thể bị hủy khi client ngắt kết nối. Server có thể truyền cancellation xuống controller publisher và các thao tác repository bên dưới.

Nếu controller gọi service có reactive transaction:

~~~java
@PostMapping("/orders")
public Mono<Order> create(@RequestBody Order order) {
    return orderService.createOrder(order);
}
~~~

Nếu client ngắt kết nối trước khi transaction hoàn tất, cancellation có thể truyền qua chuỗi publisher và làm transaction đang mở rollback.

Tuy nhiên, nếu transaction đã commit xong rồi client mới ngắt kết nối trước khi nhận response, dữ liệu vẫn được lưu. Client có thể không biết kết quả. Đây là lý do các API tạo thanh toán/đơn hàng nên hỗ trợ idempotency key hoặc endpoint tra cứu trạng thái.

Không nên giữ transaction mở trong khi chờ thao tác ngoài database kéo dài như gọi HTTP service, tải file hoặc người dùng xác nhận. Transaction lâu có thể giữ connection và lock, tăng nguy cơ pool exhaustion và deadlock. Hãy giữ transaction ngắn, chỉ bao quanh các thao tác cần tính nguyên tử trong database.

## 12. Các lỗi thường gặp

### 12.1. Nghĩ cancel luôn rollback mọi thứ

Cancellation chỉ có thể dẫn tới rollback transaction còn mở được quản lý đúng. Nó không đảo ngược transaction đã commit hoặc thao tác đã commit trong auto-commit mode.

### 12.2. Nghĩ Mono.timeout là server-side query timeout

timeout operator giới hạn thời gian publisher phát tín hiệu và cancel upstream. Muốn giới hạn thời gian SQL ở database, cần cấu hình driver/database phù hợp.

### 12.3. Dùng onErrorResume và vô tình commit

Nếu timeout/error được chuyển thành giá trị bình thường bên trong transaction boundary, transaction manager có thể thấy publisher hoàn tất thành công. Hãy để lỗi đi qua transaction manager hoặc đánh dấu rollback-only khi cần.

### 12.4. Retry ngay sau timeout

Timeout có thể xảy ra sau khi database đã commit nhưng response chưa tới. Retry thao tác không idempotent có thể thực hiện nghiệp vụ hai lần.

### 12.5. Dùng next()/take() trong transaction mà không hiểu cancellation

Các toán tử này có thể cancel upstream khi đã lấy đủ dữ liệu. Trong reactive transaction, cancellation có thể dẫn tới rollback.

### 12.6. Gọi subscribe() trong service

Tự subscribe tạo một luồng thực thi tách khỏi publisher mà caller đang quản lý, có thể làm mất transaction context, khả năng hủy và xử lý lỗi nhất quán. Hãy trả publisher hoặc kết hợp bằng flatMap/then.

### 12.7. Dùng một timeout cho tất cả tầng

Pool acquire timeout, connect timeout, statement timeout, transaction timeout và request timeout kiểm soát các giai đoạn khác nhau. Cần đặt giới hạn phù hợp với từng tầng.

### 12.8. Không giải phóng connection khi dùng SPI trực tiếp

Khi tự dùng ConnectionFactory/Connection, phải xử lý cleanup cho success, error và cancel. Nếu không, pool có thể cạn connection.

## 13. Nguyên tắc thiết kế thực tế

- Giữ reactive publisher trong cùng chuỗi từ controller/service đến repository.
- Dùng @Transactional hoặc TransactionalOperator để quản lý transaction reactive.
- Hiểu rằng cancellation trước commit có thể rollback transaction đang mở; cancellation sau commit không thể hoàn tác.
- Không coi client timeout là bằng chứng chắc chắn database chưa ghi dữ liệu.
- Dùng timeout ở tầng ứng dụng để giới hạn thời gian request và cấu hình timeout riêng cho pool/connect/query khi driver/database hỗ trợ.
- Phân biệt pool acquire timeout với statement timeout.
- Không nuốt TimeoutException bên trong transaction nếu nghiệp vụ yêu cầu rollback.
- Tránh next()/take() trong transactional publisher nếu việc cancel upstream sẽ làm transaction rollback ngoài ý muốn.
- Không gọi block() hoặc subscribe() tùy tiện trong service reactive.
- Chỉ retry lỗi tạm thời đã xác định và bảo đảm thao tác idempotent.
- Dùng idempotency key hoặc unique constraint cho thao tác ghi có thể được gửi lại sau timeout.
- Giữ transaction ngắn và tránh gọi dịch vụ bên ngoài trong khi đang giữ transaction/connection.
- Dùng doFinally(CANCEL) hoặc metrics để quan sát cancellation; không dùng callback đó thay cho transaction cleanup.
- Khi dùng R2DBC SPI trực tiếp, giải phóng connection trong mọi đường success/error/cancel.
- Kiểm thử cancellation, timeout và rollback trên đúng database/driver của production.

## 14. Ghi nhớ

Cancellation là tín hiệu subscriber yêu cầu dừng publisher; timeout ở Reactor thường phát TimeoutException và cancel publisher nguồn. Trong reactive transaction do Spring quản lý, cancellation trước commit có thể làm transaction rollback, nhưng không thể đảo ngược dữ liệu đã commit. Cancellation cũng không bảo đảm driver/database dừng câu SQL ngay lập tức.

Timeout cần được cấu hình theo tầng: chờ connection từ pool, tạo kết nối, thực thi statement, transaction và deadline toàn request. Reactive timeout không thay thế server-side statement timeout. Nếu client timeout trong lúc ghi, kết quả có thể không chắc chắn; dùng idempotency và kiểm tra trạng thái trước khi retry. Giữ publisher trong cùng transaction chain, không nuốt lỗi cần rollback và không tự subscribe trong service để transaction cùng tài nguyên được quản lý đúng.

