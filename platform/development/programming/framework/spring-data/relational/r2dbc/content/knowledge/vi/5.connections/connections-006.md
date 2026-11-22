# Mở, sử dụng và giải phóng kết nối theo vòng đời luồng phản ứng

Trong Spring Data R2DBC, làm việc với cơ sở dữ liệu không chỉ là gửi một câu SQL rồi nhận kết quả. Ứng dụng còn phải quản lý vòng đời của kết nối: lấy kết nối khi cần, giữ kết nối trong lúc câu lệnh và kết quả đang được xử lý, sau đó giải phóng đúng lúc khi luồng hoàn tất, phát sinh lỗi hoặc bị hủy.

Điểm quan trọng của mô hình reactive là các thao tác này gắn với **vòng đời subscription của Publisher**. Việc tạo một Mono hoặc Flux thường chỉ xây dựng pipeline; kết nối chưa nhất thiết được lấy ngay tại thời điểm đó. Khi có subscriber, pipeline mới thực thi và bắt đầu sử dụng tài nguyên. Vì vậy, cách mở và đóng kết nối phải tương thích với cả ba tín hiệu kết thúc của luồng: hoàn tất, lỗi và hủy.

## 1. Vòng đời cơ bản của một kết nối R2DBC

R2DBC định nghĩa API reactive để ứng dụng làm việc với cơ sở dữ liệu quan hệ. Các abstraction quan trọng gồm:

- **ConnectionFactory:** tạo kết nối tới database hoặc cung cấp kết nối từ connection pool.
- **Connection:** đại diện cho một kết nối đang được ứng dụng sử dụng.
- **Statement:** biểu diễn câu lệnh SQL cần thực thi.
- **Result:** biểu diễn kết quả thực thi statement.
- **Publisher:** phát kết quả và tín hiệu bất đồng bộ theo Reactive Streams.

Một vòng đời điển hình:

~~~text
Subscriber đăng ký vào Mono / Flux
             |
             v
Acquire Connection từ ConnectionFactory
             |
             v
Tạo Statement và bind tham số
             |
             v
Execute Statement
             |
             v
Consume Result / Row trong reactive pipeline
             |
             v
Luồng kết thúc?
             |
             v
       Complete / Error / Cancel
             |
             v
        Release Connection
             |
             v
     Connection sẵn sàng được tái sử dụng
~~~

Ba nguyên tắc cần giữ:

1. Kết nối phải được lấy trước khi sử dụng statement.
2. Kết nối phải còn được giữ trong suốt thời gian kết quả cần được đọc hoặc xử lý.
3. Kết nối phải được giải phóng ở mọi đường kết thúc: hoàn tất bình thường, lỗi và hủy subscription.

Nếu giải phóng quá sớm, ứng dụng có thể gặp lỗi khi đọc kết quả. Nếu quên giải phóng, kết nối bị giữ lại và pool có thể cạn. Nếu chỉ xử lý trường hợp hoàn tất mà bỏ qua lỗi hoặc hủy, tài nguyên có thể bị rò rỉ khi tải thực tế tăng.

## 2. ConnectionFactory và thao tác acquire

Trong R2DBC SPI, phương thức create() của ConnectionFactory trả về một Publisher<Connection>. Vì vậy, việc lấy kết nối được biểu diễn dưới dạng một thao tác reactive:

~~~java
Publisher<Connection> connectionPublisher =
    connectionFactory.create();
~~~

Trong ứng dụng Reactor, có thể chuyển publisher này thành Mono:

~~~java
Mono<Connection> connectionMono =
    Mono.from(connectionFactory.create());
~~~

Mono.from(...) không tự lấy kết nối ngay. Nó mô tả nguồn dữ liệu để lấy một kết nối khi có subscription. Cách tổ chức này cho phép quá trình acquire tham gia vào pipeline reactive, thay vì chặn thread để chờ kết nối.

ConnectionFactory có thể được cấu hình để tạo kết nối vật lý mới hoặc được bọc bởi connection pool. Khi dùng pool, thao tác acquire thường lấy một kết nối đang rảnh hoặc chờ đến khi có kết nối phù hợp. Ứng dụng làm việc với API Connection như bình thường; pool quản lý việc phân phối và tái sử dụng tài nguyên bên dưới.

Không nên gọi subscribe() bên trong service chỉ để lấy kết nối rồi tiếp tục xử lý ở một luồng khác. Làm vậy tách thao tác acquire khỏi pipeline của caller, khiến việc quản lý lỗi, hủy và thứ tự thực thi khó kiểm soát.

## 3. Sử dụng kết nối và tiêu thụ kết quả

Sau khi có Connection, ứng dụng tạo Statement, bind tham số và thực thi. Ví dụ truy vấn trực tiếp bằng R2DBC SPI:

~~~java
Mono<List<String>> customerNames =
    Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection ->
            Flux.from(
                connection
                    .createStatement(
                        "SELECT name FROM customer WHERE active = $1"
                    )
                    .bind(0, true)
                    .execute()
            )
            .flatMap(result ->
                result.map((row, metadata) ->
                    row.get("name", String.class)
                )
            )
            .collectList(),
        Connection::close,
        (connection, error) -> connection.close(),
        Connection::close
    );
~~~

Ví dụ trên minh họa cách dùng Mono.usingWhen để quản lý một kết nối:

- Đối số đầu tiên là publisher cung cấp tài nguyên, ở đây là Connection.
- Hàm thứ hai mô tả công việc thực hiện khi đã có kết nối.
- Hàm thứ ba giải phóng kết nối khi công việc hoàn tất bình thường.
- Hàm thứ tư giải phóng kết nối khi công việc phát sinh lỗi.
- Hàm thứ năm giải phóng kết nối khi subscriber hủy.

Phần Result.map(...) chuyển từng dòng kết quả thành giá trị Java. Kết quả được tiêu thụ trong pipeline trước khi usingWhen chạy cleanup. Ví dụ dùng collectList() để trả về một danh sách, phù hợp với tập dữ liệu nhỏ; với dữ liệu lớn, có thể xử lý theo luồng bằng Flux để tránh giữ toàn bộ kết quả trong bộ nhớ.

Trong thực tế, placeholder và cách bind phụ thuộc R2DBC driver. Ví dụ dùng $1 và chỉ số 0 minh họa kiểu bind của một số driver như PostgreSQL; không nên sao chép nguyên cú pháp đó sang mọi database.

## 4. Vì sao phải dùng usingWhen?

Với tài nguyên đồng bộ, Java có try-with-resources để tự động đóng tài nguyên khi thoát khỏi khối lệnh. Kết nối R2DBC là tài nguyên bất đồng bộ: Connection.close() trả về một Publisher<Void>. Do đó, không thể chỉ gọi close() rồi bỏ qua publisher mà mong đợi quá trình giải phóng đã hoàn tất.

Reactor cung cấp usingWhen để quản lý tài nguyên có thao tác cleanup bất đồng bộ. Nó gắn cleanup với các kết quả kết thúc của publisher sử dụng tài nguyên:

| Kết quả của pipeline | Cleanup được gọi |
|---|---|
| Hoàn tất bình thường | Hàm cleanup hoàn tất |
| Phát sinh lỗi | Hàm cleanup khi lỗi |
| Subscriber hủy | Hàm cleanup khi hủy |

Điểm này rất quan trọng với các luồng database. Một request HTTP có thể bị client ngắt kết nối, một operator có thể hủy upstream, hoặc timeout có thể khiến subscription bị cancel. Khi đó, ứng dụng vẫn phải giải phóng kết nối.

Không nên dùng cách sau:

~~~java
connectionFactory.create()
    .subscribe(connection -> {
        // Thực hiện truy vấn ở một subscription tách rời
        connection.close();
    });
~~~

Đoạn code này tự tạo subscription riêng, không nối kết quả truy vấn với lifecycle của caller, và không bảo đảm xử lý đúng mọi đường lỗi hoặc hủy. Nó cũng dễ làm mất ngữ cảnh transaction. Hãy trả về một Mono hoặc Flux để caller điều khiển subscription và dùng cơ chế quản lý tài nguyên reactive.

## 5. Spring Data R2DBC tự quản lý kết nối như thế nào?

Trong ứng dụng thông thường, không cần tự gọi ConnectionFactory.create() cho từng repository method. Spring cung cấp DatabaseClient để thực thi SQL và quản lý việc lấy, sử dụng, giải phóng kết nối. Spring Data R2DBC xây dựng các thao tác repository và mapping trên những abstraction này.

Ví dụ dùng DatabaseClient:

~~~java
Mono<Customer> customer =
    databaseClient.sql(
            "SELECT id, name FROM customer WHERE email = :email"
        )
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .one();
~~~

Ứng dụng chỉ mô tả câu SQL, bind giá trị và cách chuyển dòng dữ liệu thành Customer. DatabaseClient phối hợp với cơ chế quản lý kết nối của Spring để acquire và release connection theo lifecycle của thao tác.

Repository Spring Data R2DBC cũng có cùng mục tiêu:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByActiveTrue();
}
~~~

Khi gọi repository, ứng dụng nhận về Mono hoặc Flux. Việc thực thi truy vấn diễn ra khi publisher được subscribe. Spring quản lý tài nguyên cần thiết trong lúc thao tác chạy và giải phóng khi luồng kết thúc.

Vì vậy, khi dùng DatabaseClient, R2dbcEntityTemplate hoặc Spring Data repository theo cách thông thường, không nên tự acquire một connection khác chỉ để chạy cùng thao tác. Hãy để abstraction của Spring quản lý connection, đặc biệt khi ứng dụng dùng transaction.

## 6. Connection pool và việc tái sử dụng kết nối

Tạo kết nối vật lý tới database có chi phí: thiết lập socket, xác thực, khởi tạo trạng thái session và trao đổi protocol. Nếu mỗi truy vấn đều tạo rồi đóng một kết nối vật lý mới, ứng dụng có thể lãng phí tài nguyên và tăng độ trễ.

**Connection pool** giữ một tập kết nối có thể tái sử dụng. Khi ứng dụng acquire, pool cấp một kết nối đang rảnh. Khi ứng dụng release, kết nối được trả về pool để request khác có thể sử dụng.

Với R2DBC, thư viện r2dbc-pool cung cấp ConnectionPool. Ví dụ cấu hình trực tiếp:

~~~java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(5)
        .maxSize(20)
        .maxAcquireTime(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofMinutes(30))
        .build();

ConnectionPool connectionPool =
    new ConnectionPool(configuration);
~~~

Các giá trị trong ví dụ chỉ minh họa. Kích thước pool và timeout cần được chọn dựa trên số kết nối database cho phép, số instance ứng dụng, mức độ đồng thời và thời gian truy vấn thực tế.

Khi dùng connection pool:

- close() trên kết nối được pool quản lý thường có nghĩa là trả lease về pool, không nhất thiết đóng socket vật lý ngay lập tức.
- Kết nối đã release có thể được cấp cho một thao tác khác.
- Nếu tất cả kết nối đang được sử dụng, thao tác acquire có thể phải chờ hoặc thất bại khi vượt thời gian chờ.
- Kết nối nhàn rỗi hoặc không còn hợp lệ có thể được pool kiểm tra và loại bỏ theo cấu hình.

Pool không làm cho kết nối có thể được dùng đồng thời tùy ý bởi nhiều request. Mỗi lần acquire cần được xem như một lease có phạm vi sử dụng rõ ràng. Sau khi release, code không được tiếp tục dùng connection hoặc statement cũ.

Pool cũng không thay thế việc giải phóng đúng cách. Nếu pipeline quên release, pool không biết rằng ứng dụng đã xong việc; kết nối vẫn bị giữ và các thao tác sau có thể chờ đến timeout.

## 7. Release không đồng nghĩa lúc nào cũng đóng kết nối vật lý

Có hai khái niệm cần phân biệt:

- **Release:** ứng dụng kết thúc việc sử dụng kết nối và trả quyền sở hữu tài nguyên về thành phần quản lý.
- **Physical close:** đóng kết nối vật lý tới database, ví dụ đóng socket hoặc kết thúc session.

Khi không dùng pool, Connection.close() thường đóng kết nối theo cách driver hiện thực. Khi dùng pool, close() thường trả kết nối về pool. Pool quyết định giữ lại để tái sử dụng hay loại bỏ kết nối dựa trên trạng thái và chính sách quản lý.

Vì vậy, code ứng dụng vẫn phải gọi cleanup đúng lúc kể cả khi có pool. Không nên bỏ qua close() với lý do pool sẽ tự thu hồi kết nối.

Khi ứng dụng shutdown, pool cũng cần được dispose theo lifecycle của ứng dụng để ngừng nhận acquire mới và giải phóng tài nguyên. Trong Spring Boot, nên để bean/lifecycle quản lý pool được đóng cùng application context; tránh tự dispose pool sau mỗi request.

## 8. Kết nối trong reactive transaction

Transaction làm cho vòng đời connection có thêm một lớp quản lý. Khi dùng R2dbcTransactionManager, Spring lấy connection và gắn connection đó với reactive transaction context. Các thao tác database tham gia transaction sẽ sử dụng connection đã được bind trong context.

Luồng khái quát:

~~~text
Reactive transaction bắt đầu
             |
             v
Acquire Connection
             |
             v
Bind Connection vào Reactor Context
             |
             v
Các thao tác DatabaseClient / Repository
             |
             v
       Thành công hoặc lỗi
             |
             v
       Commit hoặc Rollback
             |
             v
       Release Connection
~~~

Ví dụ dùng @Transactional:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final AuditRepository auditRepository;

    @Transactional
    public Mono<Void> updateCustomer(Customer customer) {
        return customerRepository.save(customer)
            .then(auditRepository.recordUpdate(customer.getId()))
            .then();
    }
}
~~~

Vì phương thức trả về Mono, Spring có thể bao quanh subscription bằng reactive transaction nếu ứng dụng đã cấu hình ReactiveTransactionManager phù hợp. Các repository phải dùng cùng ConnectionFactory được transaction manager quản lý để tham gia cùng transaction.

Có thể dùng TransactionalOperator khi muốn bao transaction bằng code:

~~~java
Mono<Void> operation =
    customerRepository.save(customer)
        .then(auditRepository.recordUpdate(customer.getId()))
        .then();

return operation.as(transactionalOperator::transactional);
~~~

Trong reactive transaction, context được truyền qua Reactor Context thay vì dựa vào ThreadLocal như mô hình imperative truyền thống. Vì vậy, không nên tách thao tác database bằng cách tự gọi subscribe() bên trong phương thức transactional. Khi đó, subscription mới có thể chạy ngoài transaction context ban đầu.

Không nên tự gọi close() trên connection do Spring transaction manager đang quản lý. Transaction manager chịu trách nhiệm commit hoặc rollback rồi release connection khi transaction kết thúc. Nếu code tự đóng connection quá sớm, các thao tác tiếp theo trong cùng transaction có thể thất bại.

Nếu cần truy cập R2DBC SPI trực tiếp nhưng vẫn muốn tham gia Spring transaction, hãy dùng cơ chế lấy và release connection có nhận biết transaction của Spring, chẳng hạn ConnectionFactoryUtils, thay vì gọi thẳng connectionFactory.create() và tạo một connection độc lập.

Ví dụ khung quản lý connection trực tiếp theo cơ chế của Spring:

~~~java
Mono<List<String>> names =
    Mono.usingWhen(
        ConnectionFactoryUtils.getConnection(connectionFactory),
        connection -> executeQuery(connection),
        connection ->
            ConnectionFactoryUtils.releaseConnection(
                connection, connectionFactory
            ),
        (connection, error) ->
            ConnectionFactoryUtils.releaseConnection(
                connection, connectionFactory
            ),
        connection ->
            ConnectionFactoryUtils.releaseConnection(
                connection, connectionFactory
            )
    );
~~~

ConnectionFactoryUtils có thể trả về connection đã được bind với transaction hiện tại. Khi release một connection transaction-bound, Spring giữ quyền quản lý nó cho đến khi transaction commit hoặc rollback. Cách này chỉ nên dùng khi thật sự cần thao tác SPI trực tiếp; với truy vấn thông thường, DatabaseClient hoặc repository dễ sử dụng và ít sai sót hơn.

## 9. Cancellation, timeout và lỗi

Trong reactive system, không phải mọi request đều đi đến onComplete. Một subscriber có thể hủy subscription; timeout có thể hủy upstream; một bước mapping có thể ném lỗi; database có thể từ chối kết nối hoặc trả lỗi SQL.

Các tình huống thường gặp:

| Tình huống | Điều xảy ra với pipeline | Yêu cầu đối với kết nối |
|---|---|---|
| Query trả hết dữ liệu | Publisher phát onComplete | Release sau khi kết quả được tiêu thụ |
| Database trả lỗi | Publisher phát onError | Cleanup rồi truyền lỗi về caller |
| Client HTTP ngắt kết nối | Subscription có thể bị cancel | Cleanup để trả connection về pool |
| Timeout | Operator timeout có thể hủy upstream | Cleanup cả khi timeout xảy ra giữa lúc đọc dữ liệu |
| Mapping lỗi | Pipeline kết thúc bằng error | Không để connection bị giữ lại |
| Acquire timeout | Không lấy được connection | Trả lỗi phù hợp; không có connection để release |

usingWhen giúp xử lý cleanup bất đồng bộ cho các trường hợp hoàn tất, lỗi và hủy. Khi dùng DatabaseClient hoặc Spring Data repository, Spring đảm nhiệm phần lifecycle tương ứng. Ứng dụng cần để tín hiệu hủy truyền qua pipeline, không nuốt tín hiệu bằng một subscription tách rời.

Một thao tác query có thể bị hủy trong lúc đang đọc dữ liệu. Do đó, nếu code tự thao tác với R2DBC SPI, không được release ngay sau khi gọi execute(). Phải chờ publisher kết quả được tiêu thụ hoặc bị hủy để cleanup xảy ra đúng thời điểm.

## 10. Backpressure và thời gian giữ connection

R2DBC trả dữ liệu theo publisher, cho phép downstream điều tiết nhu cầu thông qua backpressure. Tuy nhiên, điều đó không có nghĩa connection được trả về pool sau mỗi row. Khi một truy vấn đang phát dữ liệu, connection thường vẫn cần được giữ cho tới khi kết quả được tiêu thụ xong hoặc subscription bị hủy.

Ví dụ:

~~~java
Flux<Customer> customers =
    databaseClient.sql("SELECT id, name FROM customer")
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all();
~~~

Nếu downstream xử lý từng phần tử chậm, subscription có thể tồn tại lâu và giữ connection lâu hơn. Nếu nhiều request cùng giữ connection trong thời gian dài, pool có thể cạn dù số truy vấn tại một thời điểm không quá lớn.

Một số cách giảm thời gian giữ connection:

- Chỉ chọn các cột cần thiết, tránh truy vấn dữ liệu lớn không cần dùng.
- Dùng điều kiện lọc và giới hạn dữ liệu hợp lý.
- Tránh thực hiện xử lý CPU nặng hoặc gọi dịch vụ HTTP chậm trong khi đang giữ kết quả database.
- Nếu cần gọi dịch vụ ngoài, cân nhắc lấy dữ liệu cần thiết rồi kết thúc thao tác database trước khi gọi dịch vụ đó, nếu yêu cầu nhất quán cho phép.
- Theo dõi thời gian acquire, thời gian giữ connection và thời gian query để tìm điểm nghẽn.

Không phải lúc nào cũng nên collectList(). Nó giúp tiêu thụ hết kết quả trong một thao tác và trả về collection, nhưng có thể dùng nhiều bộ nhớ nếu tập dữ liệu lớn. Ngược lại, streaming một luồng rất dài có thể giữ connection lâu. Cần cân bằng kích thước dữ liệu, bộ nhớ và thời gian giữ connection.

## 11. Lazy execution và nhiều subscription

Mono và Flux thường là các publisher lazy. Tạo publisher không đồng nghĩa truy vấn đã chạy:

~~~java
Mono<Customer> customerMono =
    customerRepository.findById(10L);
~~~

Ở thời điểm này, biến customerMono mô tả một thao tác. Khi có subscription, Spring mới thực hiện truy vấn và lấy tài nguyên cần thiết.

Nếu subscribe hai lần vào một publisher lạnh, thao tác có thể được thực thi hai lần và mỗi lần có thể acquire một connection riêng:

~~~java
Mono<Customer> customerMono =
    customerRepository.findById(10L);

customerMono.subscribe();
customerMono.subscribe();
~~~

Đoạn code trên thường không phải cách sử dụng phù hợp trong service. Nó tạo hai subscription độc lập, không bảo đảm chỉ truy vấn một lần. Hãy trả publisher cho tầng gọi hoặc kết hợp các thao tác bằng operator như flatMap, zip hay then.

Retry cũng có thể subscribe lại upstream. Vì vậy, thao tác database có thể chạy lại và acquire connection mới. Chỉ retry khi chính sách lỗi và tính idempotent của nghiệp vụ cho phép; không giả định rằng retry chỉ tiếp tục trên connection cũ hoặc transaction cũ.

## 12. Những lỗi quản lý connection thường gặp

| Cách làm sai | Hậu quả có thể gặp | Cách xử lý |
|---|---|---|
| Acquire connection nhưng không release | Rò rỉ connection, pool cạn | Dùng usingWhen hoặc API Spring quản lý lifecycle |
| Chỉ release khi complete | Lỗi hoặc cancel làm connection bị giữ | Cấu hình cleanup cho cả complete, error và cancel |
| Gọi close() nhưng không consume publisher cleanup | Release bất đồng bộ có thể chưa hoàn tất | Nối publisher cleanup vào pipeline |
| Close ngay sau execute() | Kết quả chưa được đọc xong | Giữ connection đến khi tiêu thụ xong Result |
| Tự gọi subscribe() trong service | Tách lifecycle, lỗi và transaction context | Trả Mono/Flux cho caller |
| Dùng connection sau khi đã release | Lỗi trạng thái hoặc truy cập tài nguyên đã được cấp cho request khác | Không sử dụng connection ngoài phạm vi lease |
| Dùng connectionFactory.create() bên trong transaction Spring | Có thể tạo connection khác, không tham gia transaction hiện tại | Dùng DatabaseClient, repository hoặc ConnectionFactoryUtils |
| Đóng connection do transaction manager quản lý | Transaction có thể thất bại trước khi hoàn tất | Để transaction manager commit/rollback và release |
| Stream dữ liệu quá lâu | Connection bị giữ lâu, pool thiếu tài nguyên | Rút ngắn thao tác, lọc dữ liệu và tránh xử lý chậm trong lúc giữ connection |

## 13. Quan sát và cấu hình vòng đời kết nối

Khi vận hành ứng dụng, cần theo dõi các chỉ số liên quan đến pool và query:

- Số connection đang được sử dụng và số connection đang rảnh.
- Số yêu cầu acquire đang chờ.
- Thời gian chờ acquire và số lần acquire timeout.
- Thời gian một connection được giữ trước khi release.
- Số lần tạo connection mới, connection bị loại bỏ và lỗi kết nối.
- Thời gian query và số lượng bản ghi được đọc.

Nếu pool thường xuyên ở mức tối đa, tăng maxSize chưa chắc là giải pháp đúng. Có thể ứng dụng đang giữ connection quá lâu, truy vấn chậm, downstream tiêu thụ dữ liệu chậm hoặc có connection leak. Cần so sánh với giới hạn connection của database và tổng số instance ứng dụng.

Timeout acquire giúp thao tác thất bại có giới hạn khi không còn connection rảnh. Timeout query hoặc timeout ở tầng request cũng cần được thiết kế đồng bộ để tránh giữ tài nguyên lâu hơn mức nghiệp vụ cho phép. Sau timeout hoặc cancel, cleanup phải được thực thi để connection được trả lại pool.

Khi shutdown ứng dụng, cần cho các thao tác đang chạy thời gian kết thúc theo chính sách của hệ thống và dispose pool thông qua lifecycle bean. Không tạo pool mới cho từng request và không dispose pool sau một truy vấn.

## 14. Cách chọn abstraction phù hợp

| Nhu cầu | Cách tiếp cận nên dùng |
|---|---|
| CRUD và mapping entity thông thường | Spring Data R2DBC repository |
| Viết SQL tùy chỉnh nhưng vẫn muốn Spring quản lý kết nối | DatabaseClient |
| Cần mapping và thao tác aggregate qua API template | R2dbcEntityTemplate |
| Cần transaction reactive cho nhiều thao tác | R2dbcTransactionManager cùng @Transactional hoặc TransactionalOperator |
| Thực sự cần API R2DBC SPI cấp thấp | ConnectionFactory kết hợp usingWhen |
| Dùng SPI cấp thấp nhưng cần tham gia Spring transaction | ConnectionFactoryUtils và cleanup tương ứng |
| Cần tái sử dụng kết nối và giới hạn số kết nối | R2DBC connection pool |

Ưu tiên abstraction ở mức cao nhất vẫn đáp ứng được yêu cầu. Repository và DatabaseClient giảm đáng kể nguy cơ quên cleanup. Chỉ quản lý Connection trực tiếp khi cần tính năng mà abstraction cao hơn không cung cấp.

## 15. Ghi nhớ

- ConnectionFactory.create() cung cấp kết nối dưới dạng reactive publisher; việc acquire gắn với subscription.
- Connection phải tồn tại trong suốt thời gian statement và result còn được sử dụng.
- Connection.close() là thao tác bất đồng bộ; cần consume publisher cleanup.
- usingWhen quản lý cleanup khi luồng complete, error hoặc cancel.
- DatabaseClient, R2dbcEntityTemplate và Spring Data repository quản lý connection cho các thao tác thông thường.
- Connection pool tái sử dụng kết nối; release thường trả lease về pool thay vì đóng socket vật lý.
- Reactive transaction bind connection vào Reactor Context; cần dùng đúng ConnectionFactory và không tự subscribe tách rời.
- Khi stream dữ liệu lâu, connection có thể bị giữ lâu; backpressure không tự trả connection sau mỗi row.
- Không dùng connection sau khi release, không bỏ qua cleanup và không tự đóng connection mà transaction manager đang quản lý.
