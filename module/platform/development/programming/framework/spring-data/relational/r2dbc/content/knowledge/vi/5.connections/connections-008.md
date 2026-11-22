# Phân biệt nhiều lần đăng ký với việc tái sử dụng một kết nối

## 1. Vì sao cần phân biệt hai khái niệm này?

Trong Spring Data Relational R2DBC, các thao tác truy cập database được biểu diễn bằng các publisher reactive như Mono và Flux. Một publisher mô tả công việc cần thực hiện; công việc thường chỉ bắt đầu khi có subscriber đăng ký nhận kết quả.

Điều này tạo ra hai khái niệm dễ bị nhầm lẫn:

- **Nhiều lần đăng ký (multiple subscriptions):** cùng một publisher được đăng ký nhiều lần. Với publisher truy vấn database dạng cold, mỗi lần đăng ký thường thực hiện lại thao tác truy vấn và đi qua quy trình lấy một connection.
- **Tái sử dụng một connection:** nhiều câu lệnh database cùng dùng một connection trong một phạm vi có chủ đích, thường là trong một transaction reactive. Các thao tác đó chia sẻ cùng trạng thái transaction và cùng phiên làm việc với database.

Ngoài ra còn có connection pool, cơ chế cho phép tái sử dụng các kết nối vật lý đã được mở sau khi một lượt sử dụng kết thúc. Connection pool và việc dùng chung một connection trong transaction giải quyết hai vấn đề khác nhau.

Nếu không phân biệt ba cơ chế này, bạn có thể vô tình chạy một câu SQL nhiều lần, tạo thêm tải lên pool, mất tính nhất quán giữa các câu lệnh, hoặc tưởng rằng hai thao tác đang dùng chung transaction trong khi thực tế chúng dùng hai connection độc lập.

## 2. Publisher, subscription và connection là ba thứ khác nhau

### 2.1. Publisher chỉ mô tả công việc

Ví dụ:

~~~java
Mono<Long> totalOrders =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();
~~~

Đoạn code trên tạo một publisher mô tả truy vấn đếm số đơn hàng. Với cách sử dụng reactive thông thường của DatabaseClient, câu SQL chưa được thực thi chỉ vì biến totalOrders được tạo ra. Việc thực thi diễn ra khi publisher được subscribe.

Publisher là mô tả của một luồng xử lý. Nó không phải connection và cũng không phải một phiên database đang được giữ mở.

### 2.2. Subscription kích hoạt một lần thực thi

Khi subscriber đăng ký, publisher cold thường bắt đầu một lần thực thi mới. Với thao tác database, quy trình thường có dạng:

~~~text
Tạo publisher
     |
     v
Subscriber đăng ký
     |
     v
Lấy connection từ ConnectionFactory
     |
     v
Thực thi câu SQL
     |
     v
Đọc kết quả và phát tín hiệu
     |
     v
Đóng hoặc trả connection về pool
~~~

Vòng đời cụ thể phụ thuộc vào abstraction đang dùng và transaction context. DatabaseClient, R2dbcEntityTemplate và Spring Data repositories quản lý vòng đời connection cho các thao tác thông thường. Khi thao tác kết thúc, connection được giải phóng theo cơ chế của ConnectionFactory; nếu dùng pool, connection thường được trả về pool để lượt sử dụng sau có thể mượn lại.

### 2.3. Connection là tài nguyên giao tiếp với database

R2DBC SPI định nghĩa ConnectionFactory để cung cấp connection. Phương thức create() trả về một Publisher của Connection. Vì vậy, việc gọi create() và việc thật sự nhận được connection cũng tách biệt theo mô hình reactive: subscriber cần đăng ký để publisher cung cấp tài nguyên.

Một connection đại diện cho một phiên làm việc logic với database. Nó có thể mang trạng thái như transaction hiện tại, isolation level, schema đang chọn hoặc một số thiết lập cấp phiên. Connection phải được quản lý vòng đời đúng cách và được giải phóng khi không còn sử dụng.

Không nên nhầm một publisher với một connection. Cũng không nên giữ một connection làm biến dùng chung toàn ứng dụng.

## 3. Cùng một publisher được đăng ký nhiều lần có thể chạy truy vấn nhiều lần

Các publisher truy vấn do DatabaseClient tạo ra thường là cold publisher. Mỗi subscription độc lập có thể kích hoạt một lần thực thi database.

Ví dụ:

~~~java
Mono<Long> totalOrders =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();

return Mono.zip(totalOrders, totalOrders);
~~~

Mono.zip cần đăng ký vào cả hai publisher đầu vào. Vì totalOrders là publisher cold, việc dùng cùng một biến hai lần không có nghĩa là chỉ chạy một câu SQL. Trong ví dụ này, truy vấn đếm có thể được thực thi hai lần. Nếu hai subscription diễn ra đồng thời và không nằm trong cùng một transaction, mỗi lần thực thi có thể mượn một connection riêng.

Đây là điểm quan trọng: **tái sử dụng biến publisher không đồng nghĩa với tái sử dụng kết quả hoặc connection**.

Một cách khác cũng có thể gây ra nhiều lần thực thi là subscribe hai lần:

~~~java
Mono<Long> totalOrders =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();

totalOrders.subscribe(value -> log.info("Lần đọc thứ nhất: {}", value));
totalOrders.subscribe(value -> log.info("Lần đọc thứ hai: {}", value));
~~~

Hai lần subscribe là hai yêu cầu thực thi độc lập. Cách viết này chỉ nhằm minh họa hành vi của subscription; trong code dịch vụ, controller hoặc repository, thông thường nên trả publisher cho framework quản lý thay vì tự subscribe.

Các thao tác như retry và repeat cũng có thể đăng ký lại publisher. Vì vậy, một truy vấn có side effect hoặc một lệnh ghi có thể chạy lại sau lỗi nếu pipeline được cấu hình retry. Hãy xem xét tính idempotent và ranh giới transaction trước khi retry thao tác ghi.

### 3.1. Muốn dùng một kết quả trong nhiều bước, hãy nối pipeline

Nếu chỉ cần chạy truy vấn một lần rồi dùng kết quả ở các bước tiếp theo, hãy xử lý kết quả trong cùng pipeline:

~~~java
return databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
    .map((row, metadata) -> row.get("total", Long.class))
    .one()
    .flatMap(total -> {
        log.info("Tổng số đơn hàng: {}", total);
        return createReportFor(total);
    });
~~~

Trong ví dụ này, publisher truy vấn được đăng ký một lần trong pipeline. Giá trị total được chuyển sang bước kế tiếp bằng flatMap. Không cần tạo một subscription thứ hai chỉ để đọc lại cùng giá trị.

Nếu cần dùng kết quả ở nhiều nhánh, hãy phát triển các nhánh từ giá trị đã nhận trong một pipeline. Chẳng hạn:

~~~java
return loadCustomer(customerId)
    .flatMap(customer ->
        Mono.zip(
            loadOrderSummary(customer.getId()),
            loadRewardSummary(customer.getId())
        ).map(summaries -> buildCustomerView(customer, summaries))
    );
~~~

Hai truy vấn trong zip vẫn là hai thao tác database độc lập. Tuy nhiên, dữ liệu khách hàng chỉ được tải một lần trong pipeline này. Nếu cả hai truy vấn summary phải nằm trong cùng một transaction, hãy đặt toàn bộ chuỗi trong transaction reactive.

### 3.2. cache() lưu tín hiệu kết quả, không lưu connection

Reactor cung cấp các toán tử chia sẻ hoặc lưu tín hiệu, ví dụ cache():

~~~java
Mono<Long> cachedTotalOrders = totalOrders.cache();
~~~

Với publisher này, lần đăng ký đầu tiên kích hoạt nguồn và tín hiệu kết quả được lưu để subscriber sau nhận lại. Đây là cơ chế cache tín hiệu của publisher. Nó không giữ connection mở để subscriber sau dùng lại.

Cần phân biệt:

- Cache kết quả: subscriber sau nhận lại giá trị hoặc tín hiệu đã được lưu.
- Tái sử dụng connection: một thao tác database tiếp theo dùng cùng connection đang được quản lý trong một phạm vi hợp lệ.
- Connection pooling: một connection vật lý được trả về pool sau lượt dùng và có thể được cấp lại cho một lượt dùng khác.

Không dùng cache() chỉ để tránh lấy connection. Cache kết quả có thể khiến dữ liệu cũ được trả lại, giữ cả tín hiệu lỗi đã xảy ra, hoặc khiến dữ liệu không phản ánh transaction hiện tại. Chỉ dùng cache khi chính sách cache dữ liệu đã được xác định rõ về thời hạn, tính nhất quán và cách làm mới.

## 4. Connection pool tái sử dụng kết nối vật lý theo thời gian

### 4.1. ConnectionFactory và ConnectionPool

ConnectionFactory là điểm cung cấp connection cho ứng dụng. Nếu dùng một factory trực tiếp, mỗi lần acquire có thể cần tạo một kết nối vật lý mới tùy cách triển khai.

Trong ứng dụng thực tế, có thể bọc factory bằng connection pool, chẳng hạn R2DBC Connection Pool. Pool duy trì một nhóm connection vật lý và cấp chúng cho các thao tác khi cần.

Vòng đời thường gặp:

~~~text
Thao tác A cần connection
        |
        v
Pool cấp connection vật lý P1
        |
        v
A thực thi SQL và giải phóng connection
        |
        v
P1 trở về pool
        |
        v
Thao tác B cần connection
        |
        v
Pool có thể cấp lại P1 cho B
~~~

Pool cũng có thể cấp một connection khác nếu P1 đang bận, không còn hợp lệ hoặc chính sách pool yêu cầu. Do đó, hai thao tác độc lập không có bảo đảm sẽ nhận cùng một connection vật lý.

### 4.2. Đóng connection trong pool thường là trả về pool

Khi ứng dụng dùng connection được quản lý bởi pool, thao tác close() trên connection đã mượn thường giải phóng lượt mượn và trả connection về pool. Pool có thể tái sử dụng connection vật lý đó sau khi hoàn tất các bước kiểm tra và reset cần thiết.

Vì vậy, không nên hiểu rằng mỗi lần một thao tác kết thúc thì database luôn phải đóng socket vật lý. Cũng không nên hiểu rằng connection được trả về pool sẽ được giữ riêng cho cùng một request ở lần sau.

### 4.3. Pool không bảo đảm trạng thái phiên được chia sẻ giữa các thao tác

Giả sử thao tác A thiết lập một biến cấp phiên hoặc tạo temporary table trên connection P1 rồi kết thúc. Sau đó thao tác B được cấp connection P2. B sẽ không nhìn thấy trạng thái riêng của P1.

Ngay cả khi B tình cờ nhận lại P1, ứng dụng cũng không nên dựa vào sự trùng hợp đó để bảo đảm tính đúng đắn. Pool có thể reset connection, cấp một connection khác hoặc thay thế connection lỗi.

Nếu nhiều câu lệnh cần dùng chung transaction, temporary table, session variable hoặc trạng thái phiên, hãy giữ chúng trong một transaction hoặc một phạm vi connection được quản lý rõ ràng.

### 4.4. Pool và transaction giải quyết hai nhu cầu khác nhau

| Cơ chế | Connection được dùng như thế nào? | Mục tiêu |
|---|---|---|
| Nhiều subscription độc lập | Mỗi lần thực thi thường acquire một connection; có thể được pool cấp connection vật lý khác nhau hoặc tái sử dụng sau khi trả về | Thực thi nhiều yêu cầu độc lập |
| Connection pool | Cấp và thu hồi các connection vật lý cho nhiều lượt sử dụng theo thời gian | Giảm chi phí tạo kết nối và giới hạn số connection |
| Một transaction reactive | Các thao tác tham gia cùng transaction được Spring gắn với cùng connection trong transaction context | Bảo đảm các câu lệnh cùng transaction và cùng trạng thái phiên |
| Quản lý connection thủ công | Code giữ một connection trong phạm vi được xác định và tự giải phóng | Các tình huống đặc biệt cần kiểm soát phiên hoặc vòng đời tài nguyên |

## 5. Tái sử dụng cùng connection trong một reactive transaction

### 5.1. Transaction manager gắn connection vào Reactor Context

Khi dùng R2dbcTransactionManager, Spring quản lý transaction bằng connection của ConnectionFactory đã cấu hình. Connection được ràng buộc với transaction context của reactive pipeline.

Các thao tác database dùng abstraction tích hợp của Spring như DatabaseClient, R2dbcEntityTemplate hoặc Spring Data repositories có thể tham gia transaction đó. Khi thao tác tiếp theo chạy trong cùng reactive transaction context, Spring lấy lại connection đã được ràng buộc thay vì mượn một connection độc lập cho mỗi câu lệnh.

Điều này cho phép nhiều câu SQL cùng thực hiện trên một connection và cùng transaction:

~~~text
Bắt đầu reactive transaction
        |
        v
Acquire connection C1 và gắn vào Reactor Context
        |
        +--> UPDATE orders trên C1
        |
        +--> INSERT audit_log trên C1
        |
        +--> UPDATE inventory trên C1
        |
        v
Commit hoặc rollback transaction
        |
        v
Giải phóng C1 về ConnectionFactory / pool
~~~

Nếu một câu lệnh thất bại và lỗi được truyền ra khỏi transaction, transaction manager có thể rollback toàn bộ transaction theo quy tắc đã cấu hình. Đây là khác biệt quan trọng so với hai thao tác độc lập chỉ tình cờ được pool cấp cùng một connection vật lý ở hai thời điểm khác nhau.

### 5.2. Dùng TransactionalOperator

TransactionalOperator cho phép bao bọc một reactive pipeline trong transaction:

~~~java
@Service
public class OrderService {

    private final DatabaseClient databaseClient;
    private final TransactionalOperator transactionalOperator;

    public OrderService(
            DatabaseClient databaseClient,
            TransactionalOperator transactionalOperator) {
        this.databaseClient = databaseClient;
        this.transactionalOperator = transactionalOperator;
    }

    public Mono<Void> confirmOrder(Long orderId) {
        Mono<Void> updateOrder =
            databaseClient.sql("""
                UPDATE orders
                SET status = :status
                WHERE id = :orderId
                """)
                .bind("status", "CONFIRMED")
                .bind("orderId", orderId)
                .fetch()
                .rowsUpdated()
                .then();

        Mono<Void> insertAudit =
            databaseClient.sql("""
                INSERT INTO order_audit(order_id, action)
                VALUES (:orderId, :action)
                """)
                .bind("orderId", orderId)
                .bind("action", "CONFIRMED")
                .fetch()
                .rowsUpdated()
                .then();

        return transactionalOperator.transactional(
            updateOrder.then(insertAudit)
        );
    }
}
~~~

Hai thao tác được nối bằng then(), vì vậy thao tác ghi audit chỉ chạy sau khi cập nhật đơn hàng hoàn tất. Khi pipeline được thực thi trong transaction, cả hai thao tác tham gia cùng transaction context và dùng connection do transaction manager quản lý.

Nếu insert audit thất bại, lỗi được truyền ra ngoài transaction và transaction có thể rollback cả cập nhật trạng thái đơn hàng. Điều này giúp tránh trường hợp đơn hàng đã chuyển trạng thái nhưng lịch sử xác nhận không được ghi, nếu cả hai bảng và thao tác hỗ trợ transaction theo cấu hình database.

Trong code thực tế, cần cấu hình R2dbcTransactionManager và TransactionalOperator với đúng ConnectionFactory mà DatabaseClient sử dụng. Nếu chúng dùng các factory khác nhau, thao tác có thể không tham gia cùng transaction.

### 5.3. Dùng @Transactional với phương thức trả về Publisher

Spring cũng hỗ trợ khai báo transaction bằng @Transactional cho phương thức reactive:

~~~java
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
    public Mono<Void> confirmOrder(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Không tìm thấy đơn hàng")
            ))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orderRepository.save(order);
            })
            .flatMap(order ->
                auditRepository.save(
                    new OrderAudit(order.getId(), "CONFIRMED")
                )
            )
            .then();
    }
}
~~~

Đối với transaction reactive, phương thức cần trả về Publisher để Spring thiết lập transaction context khi publisher được thực thi. Spring sử dụng reactive transaction manager phù hợp để mở, commit hoặc rollback transaction.

Cần lưu ý rằng proxy transaction của Spring phải thực sự được áp dụng. Gọi một phương thức @Transactional từ một phương thức khác trong cùng instance có thể bỏ qua proxy theo cách cấu hình proxy thông thường. Hãy đặt ranh giới transaction ở bean và lời gọi phù hợp.

### 5.4. Những điều kiện để các thao tác thật sự dùng cùng connection

Để các thao tác cùng tham gia một reactive transaction:

1. Dùng cùng ConnectionFactory trong transaction manager và các abstraction truy cập dữ liệu.
2. Bao bọc các thao tác trong cùng reactive transaction bằng TransactionalOperator hoặc @Transactional được cấu hình đúng.
3. Trả và nối publisher để Spring truyền Reactor Context xuyên suốt pipeline.
4. Dùng DatabaseClient, R2dbcEntityTemplate hoặc repository tích hợp với cơ chế quản lý connection của Spring.
5. Không tự mở một subscription tách rời hoặc lấy connection trực tiếp từ factory nếu mục tiêu là tham gia transaction hiện tại.

Nếu code tự gọi ConnectionFactory.create() trong transaction, connection đó có thể là một connection mới và không được gắn với transaction context hiện tại. Khi cần thao tác ở mức R2DBC SPI, hãy dùng ConnectionFactoryUtils để lấy và giải phóng connection theo cơ chế quản lý tài nguyên của Spring.

## 6. Không tự subscribe hoặc block bên trong transaction

Reactor Context gắn với subscriber, không phải ThreadLocal truyền thống. Transaction reactive phụ thuộc context này để tìm connection đã được ràng buộc.

Đoạn code sau có vấn đề:

~~~java
@Transactional
public Mono<Void> confirmOrder(Long orderId) {
    orderRepository.updateStatus(orderId, "CONFIRMED")
        .subscribe();

    return auditRepository.writeConfirmation(orderId).then();
}
~~~

Lời gọi subscribe() khởi động một luồng subscription riêng. Subscription đó có thể chạy ngoài transaction context mà Spring đang quản lý cho publisher được trả về. Phương thức cũng trả về trước khi công việc đã subscribe thủ công hoàn tất, khiến ranh giới commit/rollback không còn bao phủ toàn bộ công việc như mong muốn.

Hãy nối publisher vào chuỗi được trả về:

~~~java
@Transactional
public Mono<Void> confirmOrder(Long orderId) {
    return orderRepository.updateStatus(orderId, "CONFIRMED")
        .then(auditRepository.writeConfirmation(orderId))
        .then();
}
~~~

Tương tự, không gọi block() để chờ kết quả database bên trong một reactive transaction. block() tạo subscription và chặn thread hiện tại; việc đó có thể làm mất ngữ cảnh cần thiết, phá vỡ cách quản lý tài nguyên reactive và gây nguy cơ deadlock hoặc giảm thông lượng.

Trong ứng dụng reactive, hãy để framework hoặc thành phần ở biên ứng dụng đăng ký publisher. Code nghiệp vụ nên trả và kết hợp publisher thay vì tự điều khiển subscription.

## 7. Một connection không nên bị dùng đồng thời tùy tiện

Khi nhiều thao tác tham gia cùng một transaction, chúng thường dùng chung một connection. Connection là tài nguyên có trạng thái; nhiều driver/database không hỗ trợ việc gửi các thao tác độc lập đồng thời trên cùng connection theo cách tùy ý.

Ví dụ, trong transaction, đoạn sau có thể tạo các thao tác đồng thời:

~~~java
return transactionalOperator.transactional(
    Mono.when(
        updateOrderStatus(orderId),
        updateInventory(productId),
        insertAudit(orderId)
    )
);
~~~

Mono.when đăng ký các publisher đầu vào và chờ tất cả hoàn tất. Nếu các publisher cùng dùng một connection trong transaction, các thao tác có thể cạnh tranh trên cùng connection. Hành vi phụ thuộc driver và cách các thao tác được thực thi; không nên mặc định rằng connection sẽ xử lý mọi lệnh đồng thời an toàn.

Nếu thứ tự thực thi cần được bảo đảm hoặc các thao tác dùng chung connection, hãy nối chúng tuần tự:

~~~java
return transactionalOperator.transactional(
    updateOrderStatus(orderId)
        .then(updateInventory(productId))
        .then(insertAudit(orderId))
);
~~~

Khi xử lý một collection trong transaction, cân nhắc concatMap để thực thi tuần tự:

~~~java
return transactionalOperator.transactional(
    Flux.fromIterable(items)
        .concatMap(this::saveItem)
        .then()
);
~~~

flatMap có thể cho phép nhiều publisher con chạy đồng thời tùy concurrency. Chỉ dùng song song khi thiết kế connection, transaction, driver và giới hạn pool cho phép; không giả định một connection dùng chung có thể nhận mọi truy vấn đồng thời.

## 8. Khi nào cần tự quản lý một connection?

Với các truy vấn thông thường, hãy ưu tiên DatabaseClient, R2dbcEntityTemplate và Spring Data repositories. Những abstraction này tích hợp với vòng đời connection, pool và transaction manager.

Một số tình huống chuyên biệt có thể cần giữ một connection xuyên suốt nhiều thao tác:

- Tạo và sử dụng temporary table gắn với một phiên database.
- Thiết lập session variable rồi chạy các truy vấn phụ thuộc biến đó.
- Dùng advisory lock hoặc cơ chế khóa cấp phiên của một hệ quản trị.
- Thực hiện một chuỗi lệnh đặc thù mà API cấp cao không biểu diễn được.
- Tích hợp trực tiếp với R2DBC SPI.

Khi tự acquire connection ngoài transaction, cần bảo đảm connection được đóng hoặc trả về pool trong mọi trường hợp: thành công, lỗi và hủy subscription. Reactor có usingWhen để quản lý tài nguyên bất đồng bộ:

~~~java
private Mono<Void> runWithOneConnection() {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> executeStatements(connection),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
~~~

Trong ví dụ này, executeStatements(connection) là phương thức thực hiện các câu lệnh trên connection được cấp. Ba callback cleanup xử lý lần lượt khi publisher hoàn tất thành công, phát sinh lỗi hoặc bị cancel. Với connection pool, close() thường trả connection về pool.

Đoạn code trên minh họa cách quản lý một connection thủ công trong một phạm vi subscription. Nó không tự động tham gia transaction do Spring quản lý. Nếu cần tham gia transaction hiện tại, hãy lấy connection qua ConnectionFactoryUtils thay vì gọi trực tiếp ConnectionFactory.create().

Không lưu connection vào field static, singleton service hoặc biến dùng chung giữa các request. Connection có trạng thái, có giới hạn thời gian sử dụng và phải được trả về đúng nơi quản lý. Giữ connection quá lâu sẽ chiếm slot của pool, khiến các request khác phải chờ hoặc timeout.

## 9. Các lỗi thường gặp và cách hiểu đúng

| Cách hiểu hoặc cách làm sai | Điều thực sự xảy ra | Cách xử lý |
|---|---|---|
| Tạo một biến Mono rồi dùng hai lần nghĩa là truy vấn chỉ chạy một lần | Publisher cold có thể được subscribe hai lần và chạy truy vấn hai lần | Dùng kết quả trong cùng pipeline nếu chỉ cần một lần đọc |
| Gọi subscribe() hai lần để lấy lại kết quả | Tạo hai subscription độc lập | Trả publisher và để framework quản lý subscription |
| Cùng dùng một biến publisher nghĩa là dùng cùng connection | Publisher không đại diện cho connection | Dùng transaction context nếu các câu lệnh cần cùng connection |
| Pool luôn trả cùng một connection cho một request | Pool có thể cấp bất kỳ connection phù hợp nào | Không dựa vào trạng thái phiên giữa hai lần acquire |
| Đóng connection nghĩa là luôn đóng socket vật lý | Với pool, close() thường trả connection về pool | Để pool quản lý connection vật lý |
| Dùng cache() là tái sử dụng connection | cache() lưu tín hiệu kết quả, không giữ connection | Chỉ cache khi có chính sách cache dữ liệu rõ ràng |
| Gọi ConnectionFactory.create() trong transaction chắc chắn lấy connection transaction | Có thể lấy một connection mới ngoài transaction context | Dùng abstraction Spring hoặc ConnectionFactoryUtils |
| Gọi subscribe() bên trong phương thức @Transactional là vẫn cùng transaction | Subscription mới có thể không mang transaction context hiện tại | Nối publisher vào publisher được trả về |
| Dùng Mono.when cho nhiều lệnh trên cùng transaction connection luôn an toàn | Các lệnh có thể chạy cạnh tranh trên cùng connection | Tuần tự hóa bằng then() hoặc concatMap khi cần |
| Giữ connection trong field để dùng lại giữa request | Connection có thể bị dùng đồng thời, hết hạn hoặc làm cạn pool | Giới hạn connection theo subscription/transaction và giải phóng đúng cách |

## 10. Cách quan sát và chẩn đoán

Khi nghi ngờ một luồng đang tạo quá nhiều connection hoặc thực thi truy vấn lặp lại, hãy phân biệt số lần thực thi SQL với số connection vật lý đang mở.

### 10.1. Quan sát số lần truy vấn

Dùng log SQL hoặc log ở tầng repository/DatabaseClient để xác định một thao tác nghiệp vụ tạo ra bao nhiêu lần thực thi. Nếu cùng câu SQL xuất hiện nhiều lần, kiểm tra:

- Publisher có được dùng trong nhiều nhánh khiến nó bị subscribe nhiều lần không?
- Có subscribe() thủ công ở nhiều nơi không?
- Có retry(), repeat() hoặc vòng lặp reactive nào kích hoạt lại truy vấn không?
- Có phải nhiều request riêng biệt đang gọi cùng endpoint không?

Một publisher được tạo một lần không có nghĩa câu SQL chỉ được gửi một lần. Hãy đếm số lần thực thi thực tế.

### 10.2. Quan sát connection pool

Nếu dùng pool, theo dõi các chỉ số mà pool cung cấp, chẳng hạn số connection đang được cấp, số connection đang chờ, số connection tối đa và số connection nhàn rỗi. Tên metric cụ thể phụ thuộc phiên bản thư viện và cách cấu hình.

- Số connection đang được cấp cao có thể phản ánh nhiều thao tác đang chạy hoặc connection bị giữ quá lâu.
- Số lượt chờ tăng có thể cho thấy pool đã chạm giới hạn hoặc truy vấn/transaction giữ connection lâu.
- Connection nhàn rỗi nhiều không tự nó là lỗi; pool có thể giữ connection sẵn sàng để giảm chi phí mở mới.
- Một số lần acquire tăng không đồng nghĩa số connection vật lý tăng tương ứng, vì pool có thể tái sử dụng connection đã mở.

Không tăng kích thước pool chỉ để che một pipeline tạo subscription lặp lại hoặc transaction kéo dài. Hãy tìm nguyên nhân trước, sau đó mới điều chỉnh pool theo tải và giới hạn của database.

### 10.3. Kiểm tra transaction boundary

Nếu hai câu lệnh được kỳ vọng phải commit hoặc rollback cùng nhau, hãy xác nhận:

- Transaction manager dùng đúng ConnectionFactory.
- Các repository/DatabaseClient tham gia cùng transaction reactive.
- Phương thức trả về Mono hoặc Flux và publisher được nối liên tục.
- Không có subscribe(), block() hoặc luồng xử lý tách rời ở giữa.
- Lỗi của thao tác sau được truyền ra khỏi transaction để transaction manager có thể rollback.
- Không có code tự acquire connection trực tiếp làm tách thao tác khỏi transaction.

## 11. Chọn cơ chế phù hợp theo tình huống

| Tình huống | Cách phù hợp |
|---|---|
| Một truy vấn đọc độc lập | Tạo publisher và để framework subscribe; connection được quản lý tự động |
| Dùng kết quả truy vấn ở nhiều bước trong một request | Dùng flatMap/map để truyền kết quả trong cùng pipeline |
| Hai câu lệnh phải cùng thành công hoặc cùng thất bại | Dùng reactive transaction với TransactionalOperator hoặc @Transactional |
| Nhiều request độc lập cần chia sẻ hạ tầng connection | Cấu hình connection pool |
| Cần giữ temporary table hoặc trạng thái cấp phiên giữa các câu lệnh | Giữ cùng connection trong transaction hoặc phạm vi connection được quản lý rõ |
| Cần dùng lại giá trị truy vấn trong một khoảng thời gian | Thiết kế cache dữ liệu có chính sách hết hạn/làm mới; không cache connection |
| Cần dùng trực tiếp R2DBC SPI trong code Spring có transaction | Dùng ConnectionFactoryUtils để tham gia và giải phóng connection đúng cách |

## 12. Bài tập tự kiểm tra

### Bài 1: Một publisher, hai subscription

Đoạn code sau thường thực thi bao nhiêu lần truy vấn khi pipeline ngoài được subscribe một lần?

~~~java
Mono<Long> total =
    databaseClient.sql("SELECT COUNT(*) AS total FROM orders")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();

return Mono.zip(total, total);
~~~

Gợi ý: Mono.zip đăng ký vào cả hai nguồn. Với publisher truy vấn cold, nguồn có thể được thực thi hai lần. Cùng một biến total không làm publisher tự động chia sẻ kết quả.

### Bài 2: Dùng kết quả một lần

Bạn cần đọc số đơn hàng, ghi log và tạo báo cáo từ số đó. Hãy viết pipeline để truy vấn chỉ được thực thi một lần.

Gợi ý:

~~~java
return loadOrderCount()
    .flatMap(total -> {
        log.info("Total orders: {}", total);
        return createReport(total);
    });
~~~

### Bài 3: Hai thao tác phải cùng transaction

Một nghiệp vụ cập nhật trạng thái đơn hàng và ghi audit log. Nếu ghi audit thất bại, trạng thái đơn hàng cũng phải được rollback. Bạn sẽ đặt ranh giới transaction ở đâu?

Gợi ý: Nối hai publisher bằng then() rồi bao bọc toàn bộ chuỗi bằng TransactionalOperator hoặc đặt trong phương thức @Transactional trả về Publisher. Dùng cùng ConnectionFactory trong transaction manager và DatabaseClient/repository.

### Bài 4: Vì sao không nên gọi subscribe() bên trong service?

Một service gọi repository.save(entity).subscribe() rồi trả về Mono<Void> khác. Vì sao việc này có thể làm thao tác save nằm ngoài transaction của phương thức?

Gợi ý: subscribe() tạo một subscription riêng. Subscription đó có thể không mang Reactor Context của transaction đang được quản lý cho publisher trả về. Hãy nối thao tác save vào pipeline thay vì subscribe thủ công.

### Bài 5: Pool có bảo đảm temporary table tồn tại ở truy vấn tiếp theo không?

Một thao tác tạo temporary table rồi kết thúc. Một thao tác khác sau đó truy vấn temporary table qua cùng ConnectionFactory có chắc chắn nhìn thấy bảng không?

Gợi ý: Không. Pool có thể cấp một connection vật lý khác, và trạng thái temporary table thường gắn với phiên. Cần giữ các câu lệnh trong cùng transaction/phạm vi connection thích hợp.

### Bài 6: Khi nào dùng cache()?

Bạn gọi một publisher đọc số dư tài khoản và muốn dùng lại giá trị trong nhiều request. Có nên chỉ thêm cache() vào publisher không?

Gợi ý: cache() lưu tín hiệu của publisher, có thể giữ giá trị cũ hoặc lỗi. Cần thiết kế cache theo chính sách dữ liệu, quyền sở hữu, thời hạn và invalidation. Nó không phải cơ chế tái sử dụng connection hay bảo đảm nhất quán transaction.

## 13. Ghi nhớ khi làm việc với Spring Data Relational R2DBC

- Subscription kích hoạt thực thi publisher. Nhiều subscription vào một publisher truy vấn cold có thể làm câu SQL chạy nhiều lần.
- Tạo hoặc tái sử dụng cùng một biến Mono/Flux không tự động chia sẻ kết quả hay connection.
- Connection pool tái sử dụng connection vật lý qua nhiều lượt acquire/release; nó không bảo đảm hai thao tác độc lập dùng cùng một connection hoặc cùng trạng thái phiên.
- Reactive transaction gắn connection với Reactor Context để các thao tác tham gia cùng transaction dùng chung connection.
- Dùng TransactionalOperator hoặc @Transactional với publisher reactive, cùng ConnectionFactory phù hợp.
- Không tự subscribe() hoặc block() bên trong reactive service/transaction; hãy nối các publisher.
- Khi nhiều thao tác cùng dùng một connection, tuần tự hóa các lệnh nếu driver không hỗ trợ thực thi đồng thời trên connection đó.
- Nếu tự quản lý connection, phải giải phóng tài nguyên khi hoàn tất, lỗi hoặc cancel. Trong Spring transaction, dùng ConnectionFactoryUtils nếu cần truy cập mức thấp.
- cache() lưu tín hiệu kết quả, không lưu connection; chỉ dùng khi có chính sách cache dữ liệu rõ ràng.

Khi thiết kế một luồng R2DBC, hãy xác định rõ publisher được subscribe bao nhiêu lần, connection được acquire và release ở đâu, và các câu lệnh có cần cùng transaction hay không. Ba câu hỏi đó giúp bạn kiểm soát số lần thực thi SQL, sử dụng connection pool hiệu quả và giữ dữ liệu nhất quán.

