# Tách truy vấn đọc và ghi với lưu ý về độ trễ bản sao

Khi một ứng dụng Spring Data R2DBC có nhiều kết nối tới cùng một cụm database, có thể phân luồng thao tác ghi tới node chính (primary/writer) và một phần thao tác đọc tới các node bản sao (replica/reader). Mục tiêu là giảm tải đọc trên primary và tăng khả năng mở rộng. Tuy nhiên, bản sao thường được cập nhật bất đồng bộ, vì vậy dữ liệu trên replica có thể chậm hơn primary. Một truy vấn đọc ngay sau khi ghi có thể chưa nhìn thấy thay đổi vừa commit.

Read/write splitting vì thế không chỉ là chọn một `ConnectionFactory` cho SELECT và một factory cho UPDATE. Ứng dụng phải quyết định truy vấn nào cần tính nhất quán mạnh, giữ một transaction trên đúng node, xử lý read-after-write, quan sát replication lag và có chính sách fallback rõ ràng. Spring Data R2DBC cung cấp các abstraction để định tuyến kết nối, nhưng việc chọn primary hay replica vẫn là quyết định kiến trúc của ứng dụng.

## 1. Mô hình primary và read replicas

Một cấu hình phổ biến có một primary nhận ghi và một hoặc nhiều replica nhận đọc:

~~~mermaid
flowchart TD
    APP[Spring WebFlux / Spring Data R2DBC]
    ROUTER[Read-write connection routing]
    PRIMARY[(Primary / Writer)]
    REPLICA1[(Read replica 1)]
    REPLICA2[(Read replica 2)]
    PRIMARY -->|Replication stream| REPLICA1
    PRIMARY -->|Replication stream| REPLICA2
    APP --> ROUTER
    ROUTER -->|INSERT / UPDATE / DELETE| PRIMARY
    ROUTER -->|Eligible SELECT| REPLICA1
    ROUTER -->|Eligible SELECT| REPLICA2
~~~

Primary là nơi nhận thay đổi dữ liệu. Replica nhận các thay đổi được sao chép từ primary. Tùy hệ quản trị và cấu hình, replication có thể đồng bộ hoặc bất đồng bộ; nhiều hệ thống đọc mở rộng dùng replication bất đồng bộ để giảm độ trễ ghi.

Trong mô hình bất đồng bộ:

1. Ứng dụng gửi UPDATE đến primary.
2. Primary commit transaction và trả thành công.
3. Thay đổi được ghi vào log replication.
4. Replica nhận và áp dụng thay đổi sau đó.
5. Trong khoảng thời gian chờ, replica vẫn có thể trả về dữ liệu cũ.

Khoảng chênh giữa thời điểm primary commit và thời điểm replica áp dụng xong thay đổi được gọi là replication lag.

## 2. Read/write splitting đem lại lợi ích gì?

Nếu workload có nhiều truy vấn đọc hơn ghi, replica có thể phân tán tải:

- Primary tập trung xử lý ghi và các truy vấn đọc cần dữ liệu mới nhất.
- Replica phục vụ danh sách, báo cáo hoặc truy vấn chấp nhận độ trễ.
- Có thể thêm replica để tăng năng lực đọc khi database hỗ trợ.
- Tách quyền kết nối giúp tài khoản đọc chỉ có quyền SELECT.
- Có thể chọn topology khác nhau cho từng môi trường.

Ví dụ một hệ thống thương mại điện tử có thể đọc danh sách sản phẩm từ replica, nhưng cần đọc số dư hoặc trạng thái đơn hàng vừa cập nhật từ primary.

Read/write splitting không làm một câu SELECT tự nhiên nhanh hơn trong mọi trường hợp. Replica vẫn có giới hạn CPU, I/O, cache, network và khả năng áp dụng log. Truy vấn nặng có thể làm replica lag tăng hoặc làm chậm các truy vấn đọc khác.

## 3. Replication lag và dữ liệu cũ

Giả sử người dùng cập nhật địa chỉ giao hàng:

| Thời điểm | Primary | Replica |
| --- | --- | --- |
| T0 | Địa chỉ cũ | Địa chỉ cũ |
| T1 | UPDATE và COMMIT địa chỉ mới | Địa chỉ cũ |
| T2 | Địa chỉ mới | Đang nhận/apply log |
| T3 | Địa chỉ mới | Địa chỉ mới |

Nếu ứng dụng đọc từ replica ở T1 hoặc T2, người dùng có thể nhìn thấy địa chỉ cũ dù UPDATE đã trả thành công.

Đây là hiện tượng eventual consistency: các bản sao sẽ hội tụ nếu replication tiếp tục hoạt động bình thường, nhưng không nhất thiết đồng nhất ngay sau mỗi commit.

Không nên diễn giải “replica có độ trễ thấp” thành “replica luôn trả dữ liệu mới nhất”. Lag có thể tăng khi primary ghi nhiều, replica quá tải, network gián đoạn, transaction lớn hoặc replication bị lỗi.

## 4. Read-after-write consistency

Read-after-write là yêu cầu một client nhìn thấy thay đổi mà chính nó vừa ghi. Đây là một yêu cầu nhất quán quan trọng trong các luồng tương tác:

1. Người dùng đổi tên hồ sơ.
2. API trả về thành công.
3. Frontend gọi API đọc hồ sơ ngay sau đó.
4. Nếu truy vấn được định tuyến sang replica chưa bắt kịp, tên cũ xuất hiện.

Một số cách xử lý:

- Đọc từ primary sau thao tác ghi.
- Dùng sticky routing: trong một khoảng hoặc một phiên logic sau khi ghi, tiếp tục định tuyến các lần đọc liên quan tới primary.
- Dùng token/position replication để đợi replica áp dụng đến vị trí commit cần thiết, nếu database và kiến trúc hỗ trợ.
- Trả dữ liệu vừa ghi từ kết quả của lệnh ghi, tránh truy vấn lại ngay.
- Chấp nhận eventual consistency ở những màn hình không yêu cầu read-after-write.

Chọn chiến lược theo yêu cầu nghiệp vụ. Không phải mọi truy vấn đọc đều cần primary, nhưng những luồng hiển thị kết quả ghi ngay lập tức cần chính sách rõ ràng.

## 5. Phân loại truy vấn trước khi định tuyến

Không nên chỉ phân loại theo từ khóa SQL SELECT/UPDATE. Một truy vấn SELECT vẫn có thể cần primary:

- SELECT FOR UPDATE hoặc truy vấn lấy khóa bi quan.
- Đọc dữ liệu ngay sau khi vừa ghi.
- Đọc trạng thái dùng để quyết định một thao tác tài chính hoặc nghiệp vụ nhạy cảm.
- Đọc dữ liệu trong transaction cần cùng snapshot với các thao tác ghi.
- Đọc dữ liệu từ bảng hoặc view chưa được replica áp dụng đầy đủ.

Ngược lại, một số truy vấn đọc có thể chạy trên replica:

- Danh sách sản phẩm hoặc nội dung công khai.
- Báo cáo chấp nhận độ trễ.
- Tìm kiếm và thống kê không yêu cầu dữ liệu mới tức thời.
- Các truy vấn đọc độc lập với một thao tác ghi vừa xảy ra.

Quyết định route nên xuất phát từ consistency requirement của use case, không chỉ từ loại câu SQL.

## 6. Hai cách triển khai phổ biến trong Spring Data R2DBC

Có hai hướng thường dùng:

**Cách A — tách rõ read/write client hoặc template**

- Tạo connection factory và `R2dbcEntityTemplate` riêng cho primary và replica.
- Service chọn đúng template theo use case.
- Dễ hiểu, dễ kiểm thử, không cần router động.
- Phải quản lý repository/template cho từng phía nếu dùng repository.

**Cách B — dùng routing ConnectionFactory**

- Một `AbstractRoutingConnectionFactory` chọn factory đích theo route key.
- Route key được truyền trong Reactor Context hoặc một cơ chế context-aware khác.
- Có thể dùng một nhóm repository/template dựa trên routing factory.
- Cần đặc biệt chú ý thời điểm lấy connection và ranh giới transaction.

Không có lựa chọn đúng cho mọi ứng dụng. Tách client tường minh thường dễ vận hành ở hệ thống có ít loại use case. Routing factory có thể hữu ích khi muốn giữ một API persistence chung và có quy tắc route rõ ràng.

## 7. Tách hai ConnectionFactory và hai R2dbcEntityTemplate

Với cách tách tường minh, có thể cấu hình hai kết nối:

~~~java
@Configuration
public class DatabaseConfiguration {

    @Bean
    @Qualifier("writerConnectionFactory")
    ConnectionFactory writerConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://writer-host:5432/shop"
        );
    }

    @Bean
    @Qualifier("readerConnectionFactory")
    ConnectionFactory readerConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://reader-host:5432/shop"
        );
    }

    @Bean
    @Qualifier("writerTemplate")
    R2dbcEntityTemplate writerTemplate(
            @Qualifier("writerConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean
    @Qualifier("readerTemplate")
    R2dbcEntityTemplate readerTemplate(
            @Qualifier("readerConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

Đây là ví dụ khung. Trong ứng dụng thực tế, nên cấu hình pool, credentials, timeout, converter và mapping context phù hợp cho từng factory. Không tạo connection mới cho mỗi request bằng cách gọi `ConnectionFactories.get(...)` trong service.

Service có thể chọn rõ nơi đọc:

~~~java
@Service
public class ProductQueryService {

    private final R2dbcEntityTemplate readerTemplate;
    private final R2dbcEntityTemplate writerTemplate;

    public ProductQueryService(
            @Qualifier("readerTemplate") R2dbcEntityTemplate readerTemplate,
            @Qualifier("writerTemplate") R2dbcEntityTemplate writerTemplate) {
        this.readerTemplate = readerTemplate;
        this.writerTemplate = writerTemplate;
    }

    public Flux<Product> browseProducts() {
        return readerTemplate.select(Product.class).all();
    }

    public Mono<Product> findFreshProduct(Long id) {
        return writerTemplate.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Product.class
        );
    }
}
~~~

Phương thức browse chấp nhận eventual consistency nên dùng replica. findFreshProduct cần dữ liệu mới nhất nên dùng primary. Tên phương thức và lựa chọn template làm rõ yêu cầu nhất quán.

## 8. Ghi luôn đi qua primary

Các thao tác thay đổi dữ liệu phải đi đến primary hoặc node có quyền ghi theo topology:

~~~java
public Mono<Product> updatePrice(Long id, BigDecimal price) {
    return writerTemplate.selectOne(
                    Query.query(Criteria.where("id").is(id)),
                    Product.class
            )
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
            .map(product -> new Product(
                    product.id(),
                    product.name(),
                    price
            ))
            .flatMap(writerTemplate::update);
}
~~~

Ví dụ trên minh họa chọn writer template cho toàn bộ thao tác đọc-sửa-ghi. Nếu nghiệp vụ cần bảo vệ đồng thời, hãy đặt cả chuỗi trong transaction của writer connection factory. Không đọc từ replica rồi dùng dữ liệu có thể cũ để cập nhật primary nếu logic cần trạng thái mới nhất.

Trong hệ thống thực tế, một câu UPDATE có điều kiện thường tốt hơn đọc entity rồi ghi lại khi có thể biểu đạt quy tắc nghiệp vụ trong SQL. Điều đó giảm round trip và thu hẹp khoảng thời gian cạnh tranh.

## 9. Routing ConnectionFactory với AbstractRoutingConnectionFactory

Spring Framework cung cấp `AbstractRoutingConnectionFactory` trong module Spring R2DBC. Class này chọn một `ConnectionFactory` đích theo lookup key được xác định tại thời điểm tạo connection.

Có thể định nghĩa route:

~~~java
public enum DatabaseRoute {
    WRITE,
    READ
}
~~~

Router có thể lấy route key từ Reactor Context:

~~~java
public class ReadWriteRoutingConnectionFactory
        extends AbstractRoutingConnectionFactory {

    public static final String ROUTE_CONTEXT_KEY =
            ReadWriteRoutingConnectionFactory.class.getName() + ".ROUTE";

    @Override
    protected Mono<Object> determineCurrentLookupKey() {
        return Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(
                        ROUTE_CONTEXT_KEY,
                        DatabaseRoute.WRITE
                ))
        );
    }
}
~~~

Mặc định chọn WRITE để những thao tác không chỉ định route vẫn đi tới primary. Đây là lựa chọn an toàn hơn việc mặc định mọi truy vấn sang replica.

Đăng ký các factory đích:

~~~java
@Bean
@Primary
ConnectionFactory routingConnectionFactory(
        @Qualifier("writerConnectionFactory")
        ConnectionFactory writer,
        @Qualifier("readerConnectionFactory")
        ConnectionFactory reader) {

    ReadWriteRoutingConnectionFactory routing =
            new ReadWriteRoutingConnectionFactory();

    routing.setTargetConnectionFactories(Map.of(
            DatabaseRoute.WRITE, writer,
            DatabaseRoute.READ, reader
    ));
    routing.setDefaultTargetConnectionFactory(writer);
    routing.setLenientFallback(false);

    return routing;
}
~~~

`AbstractRoutingConnectionFactory` là abstraction của Spring; chữ ký và cách cấu hình chi tiết cần đối chiếu với phiên bản Spring Framework trong dự án. Mỗi factory đích nên được tạo và quản lý như bean riêng, có pool và driver phù hợp.

## 10. Đặt route key trong Reactor Context

Với router ở trên, có thể chỉ định một thao tác đọc:

~~~java
public Flux<Product> browseProducts() {
    return productRepository.findAll()
            .contextWrite(context -> context.put(
                    ReadWriteRoutingConnectionFactory.ROUTE_CONTEXT_KEY,
                    DatabaseRoute.READ
            ));
}
~~~

Context được truyền theo hướng upstream khi subscription diễn ra. Router đọc route key trong context lúc cần tạo connection. Nếu không có key, router dùng WRITE theo cấu hình mặc định.

Đối với một truy vấn đơn lẻ không nằm trong transaction, route key cần nằm trong context của publisher thực thi truy vấn. Với transaction, route key phải được thiết lập trước khi transaction manager lấy connection.

Không dùng ThreadLocal để lưu route trong ứng dụng reactive. Một pipeline có thể chạy trên nhiều thread; ThreadLocal không tự đi theo Reactor Context và có thể gây rò route giữa các request.

## 11. Định tuyến transaction: chọn node trước khi bắt đầu

Một transaction thường lấy một connection và giữ connection đó đến commit/rollback. Vì vậy, route được quyết định khi transaction manager lấy connection. Không thể bắt đầu transaction trên replica rồi đổi sang primary giữa chừng chỉ bằng cách thay route key.

Với `TransactionalOperator`, đặt context route ở bên ngoài operator:

~~~java
public Mono<Product> readProductInReadTransaction(Long id) {
    Mono<Product> work = productRepository.findById(id);

    return readOnlyTransactionalOperator.transactional(work)
            .contextWrite(context -> context.put(
                    ReadWriteRoutingConnectionFactory.ROUTE_CONTEXT_KEY,
                    DatabaseRoute.READ
            ));
}
~~~

Ở cấu trúc này, route key nằm trong context mà transaction operator sử dụng khi yêu cầu connection. Transaction manager dùng routing factory; router chọn replica ngay lúc connection được cấp. Các truy vấn tiếp theo trong transaction tiếp tục dùng connection đã gắn với transaction đó.

Đừng thay route key giữa các thao tác trong cùng transaction và kỳ vọng connection sẽ chuyển node. Khi transaction đã bắt đầu, connection được transaction manager giữ cố định.

## 12. @Transactional(readOnly = true) không tự bảo đảm route sang replica

`@Transactional(readOnly = true)` thể hiện transaction có ý định chỉ đọc. Thuộc tính read-only có thể được transaction manager/database sử dụng như một hint hoặc thiết lập transaction, nhưng nó không tự động có nghĩa là Spring Data R2DBC sẽ chọn một replica.

Muốn định tuyến dựa trên read-only transaction metadata, cần triển khai routing strategy phù hợp với vòng đời transaction của phiên bản Spring Framework đang dùng. Cần kiểm tra thời điểm `AbstractRoutingConnectionFactory` gọi `determineCurrentLookupKey()` so với thời điểm transaction manager thiết lập transaction synchronization context. Không nên sao chép một ví dụ dựa trên ThreadLocal hoặc giả định metadata đã có sẵn trước khi connection được tạo.

Một lựa chọn dễ kiểm soát hơn là đặt route key tường minh trong Reactor Context trước khi gọi `TransactionalOperator`, như ví dụ ở phần trước, hoặc inject read/write template riêng.

Nếu chọn routing tự động theo annotation, hãy viết integration test chứng minh:

- Transaction read-only thực sự lấy connection từ replica.
- Transaction ghi lấy connection từ primary.
- Một transaction chỉ dùng một node từ đầu đến cuối.
- Các luồng có route khác nhau không rò context sang nhau.
- Proxy/AOP và thứ tự advice không làm route key được thiết lập quá muộn.

## 13. Không chuyển SELECT FOR UPDATE sang replica

Một câu SELECT có thể giữ khóa:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE;
~~~

Truy vấn này là một phần của workflow ghi và cần chạy trên primary. Replica read-only thường không cho phép khóa hàng theo cách này hoặc không thể cung cấp semantics khóa tương đương với primary.

Tương tự, các thao tác cần đọc dữ liệu mới nhất để quyết định ghi, kiểm tra số dư, kiểm tra tồn kho hoặc xác minh trạng thái thanh toán nên dùng primary hoặc một cơ chế consistency rõ ràng.

Không định tuyến mọi câu SELECT sang replica. SQL verb không đủ để xác định yêu cầu consistency.

## 14. Sticky routing sau khi ghi

Một chiến lược đơn giản để hỗ trợ read-after-write là sticky routing: sau khi một request hoặc phiên logic ghi thành công, các lần đọc liên quan tiếp theo được định tuyến tới primary trong một khoảng thời gian hoặc cho đến khi kết thúc workflow.

Ví dụ khái niệm:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderService.create(command)
            .doOnSuccess(order ->
                    consistencyState.markWriterRequired(
                            command.sessionId()
                    )
            );
}
~~~

Khi xử lý request đọc:

~~~java
if (consistencyState.requiresWriter(sessionId)) {
    return writerTemplate.selectOne(query, Order.class);
}

return readerTemplate.selectOne(query, Order.class);
~~~

Đây là pseudocode cho state manager; cách lưu state có thể là session store, token trong request context hoặc một cơ chế nhất quán khác. Không dùng biến mutable singleton chung để đánh dấu một user vừa ghi vì nhiều request đồng thời có thể ảnh hưởng lẫn nhau.

Sticky routing theo thời gian chỉ là heuristic nếu không có tín hiệu replica đã áp dụng commit. Nếu lag vượt khoảng sticky window, đọc vẫn có thể stale. Với yêu cầu mạnh, giữ route primary cho đến khi workflow kết thúc hoặc dùng cơ chế xác nhận replication position.

## 15. Trả dữ liệu vừa ghi thay vì đọc lại

Một cách đơn giản để tránh read-after-write qua replica là trả về kết quả của thao tác ghi:

~~~java
public Mono<Customer> updateProfile(
        Long id,
        UpdateProfileCommand command) {

    return writerTemplate.selectOne(
                    Query.query(Criteria.where("id").is(id)),
                    Customer.class
            )
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .map(customer -> new Customer(
                    customer.id(),
                    command.name(),
                    command.email()
            ))
            .flatMap(writerTemplate::update);
}
~~~

Sau khi save/update, publisher thường trả về entity được ghi. Controller có thể dùng giá trị đó để trả response mà không gọi thêm một SELECT qua replica.

Với DML tùy chỉnh, có thể dùng `RETURNING` trên database hỗ trợ để nhận giá trị mới trong cùng câu lệnh. Đây là cách giảm round trip và tránh đọc một bản sao chưa bắt kịp.

## 16. Chờ replica bắt kịp bằng replication position

Một số hệ quản trị cung cấp vị trí log hoặc token để so sánh tiến độ replication. Ý tưởng tổng quát:

1. Sau commit trên primary, lấy một replication position/token.
2. Chuyển token cho bước đọc hoặc lưu trong request/session.
3. Trên replica, đợi đến khi vị trí đã áp dụng đạt hoặc vượt token.
4. Chỉ sau đó mới thực hiện truy vấn cần read-your-writes.

Ví dụ PostgreSQL có các hàm liên quan WAL LSN như `pg_current_wal_lsn()` và `pg_last_wal_replay_lsn()`; có thể kiểm tra tiến độ replay trên replica. Tên hàm, quyền truy cập và semantics cần đối chiếu phiên bản PostgreSQL. Các database khác có cơ chế replication position riêng.

Không có một API Spring Data R2DBC portable để đợi mọi loại replica đạt cùng một commit token. Đây là logic đặc thù database và thường cần một thành phần consistency coordinator.

Nếu hệ thống không có cơ chế token, route các lần đọc nhạy cảm về primary là phương án đơn giản và dễ hiểu hơn.

## 17. Load balancing giữa nhiều replica

Khi có nhiều replica, router có thể chọn một factory trong nhóm reader. Các chiến lược phổ biến:

- Round robin.
- Random.
- Weighted routing dựa trên capacity.
- Chọn replica theo vùng hoặc độ gần network.
- Chọn replica có lag thấp và health tốt.

Không nên chỉ phân phối đều mà không theo dõi tình trạng node. Một replica đang apply log chậm hoặc quá tải có thể trả dữ liệu stale và làm truy vấn tăng latency.

Một hệ thống production thường cần health check, connection pool riêng, metric lag, circuit breaker và chính sách loại replica lỗi khỏi nhóm. Việc health check chỉ xác nhận TCP connection mở không chứng minh replica đã bắt kịp dữ liệu.

## 18. Fallback từ replica sang primary

Nếu replica không sẵn sàng, có thể fallback đọc sang primary, nhưng cần giới hạn rõ:

- Chỉ fallback các truy vấn đọc được phép chạy trên primary.
- Giới hạn concurrency và tải fallback để không làm primary quá tải.
- Không tự chuyển một transaction đang mở từ replica sang primary.
- Phân biệt lỗi kết nối replica với lỗi query/data/schema.
- Không retry mọi lỗi SQL trên primary vì lỗi cú pháp hoặc quyền sẽ tiếp tục xảy ra.

Fallback có thể cải thiện availability nhưng làm tăng tải writer. Khi nhiều replica cùng lỗi, toàn bộ read traffic dồn vào primary có thể gây cascading failure. Cần circuit breaker, bulkhead hoặc giới hạn lưu lượng.

Với truy vấn cần dữ liệu mới nhất, route thẳng tới primary từ đầu thường rõ ràng hơn việc thử replica rồi fallback sau khi phát hiện dữ liệu cũ.

## 19. Read/write splitting và transaction manager

Nếu dùng hai connection factory độc lập, transaction manager phải được gắn với đúng factory:

| Use case | ConnectionFactory | Transaction manager |
| --- | --- | --- |
| Transaction ghi | Primary | Writer R2dbcTransactionManager |
| Transaction đọc trên replica | Replica được chọn | Reader R2dbcTransactionManager tương ứng |
| Read không cần transaction dài | Reader | Có thể không cần transaction tường minh |

Một `R2dbcTransactionManager` quản lý một `ConnectionFactory`. Không thể dùng một transaction manager writer để rollback các lệnh đã chạy trên một connection factory replica độc lập.

Với routing factory, transaction manager quản lý routing factory và route được chọn lúc cấp connection. Sau khi connection được bind vào Reactor Context, mọi thao tác trong transaction dùng connection đó.

Nếu một use case cần đọc replica rồi ghi primary, hãy xem đây là hai giai đoạn khác nhau. Không giả định chúng là một transaction nguyên tử khi dùng hai database connection độc lập. Nếu cần tính nhất quán mạnh, thực hiện đọc và ghi trên primary trong cùng transaction.

## 20. Read-your-writes và các mức consistency

Có thể phân loại use case:

| Yêu cầu | Route đề xuất |
| --- | --- |
| Đọc ngay sau khi người dùng vừa ghi | Primary hoặc token-based replica wait |
| Kiểm tra tồn kho/số dư trước ghi | Primary trong transaction |
| SELECT FOR UPDATE | Primary |
| Trang danh sách công khai chấp nhận trễ | Replica |
| Báo cáo tổng hợp không cần tức thời | Replica/warehouse tùy tải |
| Đọc cấu hình nhạy cảm cần mới nhất | Primary |
| Luồng chỉ đọc lâu và cần snapshot | Một transaction/connection replica với isolation phù hợp, nếu cần |

Một yêu cầu “đọc mới nhất” cần được định nghĩa cụ thể: mới nhất tại thời điểm truy vấn, mới nhất sau commit của chính request, hay nhất quán giữa nhiều truy vấn trong cùng workflow. Các yêu cầu này có thể cần chiến lược khác nhau.

## 21. Độ trễ bản sao và vận hành

Các chỉ số nên theo dõi:

- Replication lag theo thời gian hoặc vị trí log.
- Thời gian apply/replay log.
- Số lượng transaction chưa được replica áp dụng.
- Reader connection pool: active, idle, pending acquire.
- Query latency và error rate từng replica.
- Số truy vấn fallback sang primary.
- Tỷ lệ request phải sticky route về primary.

Không nên chỉ dựa trên một con số lag trung bình. Một replica có thể có lag thấp nhưng đột nhiên tăng cao khi có transaction lớn. Có thể đặt ngưỡng loại replica khỏi read pool hoặc chuyển một số workload về primary.

Metric và câu lệnh quan sát lag khác nhau giữa PostgreSQL, MySQL, SQL Server và các dịch vụ managed database. Dùng công cụ giám sát chính thức của hệ quản trị/nhà cung cấp.

## 22. Bảo mật kết nối read replica

Nên tạo tài khoản database riêng cho reader:

- Chỉ cấp SELECT trên schema/bảng cần đọc.
- Không cấp quyền DDL.
- Không cấp INSERT/UPDATE/DELETE nếu không cần.
- Hạn chế quyền đọc dữ liệu nhạy cảm theo yêu cầu bảo mật.

Tài khoản writer có quyền ghi cần được quản lý riêng. Không dùng chung một tài khoản superuser cho cả primary và replica.

Tuy nhiên, quyền read-only không thay thế route policy. Một truy vấn SELECT có thể cần primary vì yêu cầu consistency hoặc khóa. Ngược lại, một lỗi route nhầm UPDATE sang replica nên bị database từ chối thay vì âm thầm chuyển đổi.

## 23. Kiểm thử read/write routing

Integration test nên chứng minh route thực sự đến node mong muốn, không chỉ kiểm tra giá trị route key trong Reactor Context:

1. Cấu hình primary và replica test riêng hoặc dùng hai endpoint mô phỏng có thể quan sát.
2. Ghi một bản ghi qua writer.
3. Xác nhận câu ghi được thực hiện ở primary.
4. Đọc một use case eventual-consistent và xác nhận route đến reader.
5. Đọc ngay sau ghi và xác nhận route đến primary hoặc đợi replica theo policy.
6. Bắt đầu transaction và xác nhận mọi câu lệnh trong transaction dùng cùng node.
7. Mô phỏng replica lag và kiểm tra stale-read policy.
8. Mô phỏng reader unavailable và kiểm tra fallback/limiter.
9. Chạy các request đọc/ghi đồng thời để xác nhận Reactor Context không rò giữa subscription.

Không nên dùng một database đơn rồi giả định hai connection factory trỏ cùng node đã kiểm tra được replication lag. Cần môi trường có primary/replica thật hoặc test harness mô phỏng độ trễ.

## 24. Các lỗi thường gặp

1. **Định tuyến mọi SELECT sang replica.** SELECT FOR UPDATE và read-after-write có thể cần primary.
2. **Cho rằng replica luôn mới nhất sau commit.** Replication bất đồng bộ tạo cửa sổ dữ liệu stale.
3. **Dùng @Transactional(readOnly = true) và kỳ vọng tự chọn replica.** Read-only không tự định tuyến connection.
4. **Đổi route key giữa transaction.** Connection đã được transaction manager giữ cố định.
5. **Dùng ThreadLocal trong reactive routing.** Thread thay đổi giữa các operator; dùng Reactor Context hoặc route tường minh.
6. **Đặt context route quá muộn.** Transaction manager có thể đã lấy connection trước khi route key được nhìn thấy.
7. **Đọc replica rồi dùng dữ liệu cũ để ghi primary.** Kiểm tra và cập nhật có thể dựa trên trạng thái lỗi thời.
8. **Fallback mọi lỗi replica sang primary.** Có thể che lỗi SQL và làm writer quá tải.
9. **Không theo dõi replication lag.** Replica chậm vẫn tiếp tục nhận traffic.
10. **Dùng chung tài khoản quyền cao cho reader và writer.** Tăng rủi ro bảo mật.
11. **Giả định hai factory độc lập cùng transaction.** Mỗi transaction manager quản lý resource riêng.
12. **Không có sticky/read-your-writes policy.** Người dùng có thể thấy dữ liệu cũ ngay sau thao tác ghi.

## Quy tắc lựa chọn nhanh

- Gửi INSERT, UPDATE, DELETE và các thao tác cần khóa tới primary.
- Chỉ gửi SELECT sang replica khi use case chấp nhận eventual consistency.
- Dùng read/write template riêng nếu muốn route tường minh, dễ kiểm soát.
- Dùng `AbstractRoutingConnectionFactory` khi cần chọn factory theo Reactor Context và đã kiểm thử thời điểm lấy connection.
- Đặt route key trước khi transaction bắt đầu; transaction đã lấy connection thì không đổi node giữa chừng.
- Không xem `@Transactional(readOnly = true)` là cơ chế tự động chuyển sang replica.
- Trả entity từ thao tác ghi hoặc dùng primary cho read-after-write.
- Dùng sticky routing hoặc replication-position token khi cần đọc từ replica nhưng vẫn bảo đảm thấy commit trước đó.
- Theo dõi replication lag, health, pool và fallback rate.
- Giới hạn fallback để bảo vệ primary khi replica lỗi.
- Kiểm thử trên topology primary/replica thực tế.

Tách truy vấn đọc và ghi có thể tăng khả năng mở rộng của hệ thống Spring Data R2DBC, nhưng nó đưa thêm một yêu cầu vào thiết kế: xác định mức nhất quán mà từng use case cần. Primary là nơi phù hợp cho ghi, khóa và các lần đọc cần thấy dữ liệu mới nhất; replica phù hợp với truy vấn chấp nhận độ trễ. Khi dùng routing connection factory, route phải được chọn trước lúc transaction lấy connection và giữ ổn định trong toàn bộ transaction. Kết hợp read/write splitting với read-after-write policy, theo dõi replication lag, fallback có giới hạn và kiểm thử nhiều node giúp ứng dụng tận dụng replica mà không làm người dùng thấy dữ liệu cũ ở những luồng quan trọng.
