# Trình điều khiển dữ liệu phản ứng và giới hạn của bộ chuyển đổi

Một ứng dụng reactive chỉ giữ được lợi ích về khả năng mở rộng nếu các thao tác I/O quan trọng không chặn thread xử lý tín hiệu. Khi làm việc với cơ sở dữ liệu, khác biệt giữa một driver reactive thực sự và một adapter bọc API đồng bộ rất quan trọng. Cả hai có thể trả về **Mono** hoặc **Flux**, nhưng chỉ driver có API I/O bất đồng bộ mới tránh việc giữ worker trong lúc chờ database phản hồi.

Bài học thuộc chương **Dữ liệu và giao dịch** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài này tập trung vào driver dữ liệu reactive, đặc biệt là R2DBC trong hệ sinh thái Java, đồng thời làm rõ những gì một bộ chuyển đổi từ JDBC có thể và không thể cung cấp.

## Driver reactive thực sự khác adapter blocking ở đâu?

JDBC cung cấp API đồng bộ. Khi gọi **executeQuery()** hoặc đọc kết quả từ **ResultSet**, thread gọi phương thức phải chờ driver hoàn thành I/O. Bọc lời gọi đó trong **Mono.fromCallable()** và chạy bằng **Schedulers.boundedElastic()** giúp cô lập việc chờ khỏi event loop, nhưng thao tác bên dưới vẫn blocking.

Một driver reactive cung cấp API bất đồng bộ và trả về Publisher theo hợp đồng Reactive Streams. Khi ứng dụng subscribe, driver có thể gửi lệnh qua giao thức mạng và tiếp tục xử lý khi dữ liệu hoặc tín hiệu hoàn tất đến. Thread gọi không phải ngồi chờ đồng bộ cho từng thao tác I/O. Driver có thể quản lý socket, bộ đệm và việc đọc dữ liệu bằng cơ chế bất đồng bộ của nó.

| Đặc điểm | JDBC được bọc bằng adapter | Driver database reactive |
|---|---|---|
| API ở tầng ứng dụng | Có thể trả về **Mono** hoặc **Flux** | Trả về Publisher theo API reactive |
| I/O bên dưới | Vẫn đồng bộ và blocking | Được triển khai theo cơ chế I/O bất đồng bộ của driver |
| Scheduler | Thường cần **boundedElastic** để cô lập blocking | Thường không cần chuyển thao tác I/O sang pool blocking |
| Thread khi chờ database | Worker bị giữ trong lúc lời gọi đồng bộ chờ | Không cần giữ thread gọi chỉ để chờ phản hồi mạng |
| Backpressure | Adapter phải tự kiểm soát việc đọc và bộ đệm; JDBC không có demand protocol | Có thể tích hợp demand và phát dữ liệu theo Reactive Streams, tùy khả năng driver |
| Cancellation | Không bảo đảm lời gọi JDBC đang chạy dừng ngay | Driver có thể hỗ trợ hủy thao tác; hiệu lực thực tế tùy driver và giao thức |
| Transaction | Thường theo cơ chế imperative, có thể gắn với thread | Có thể quản lý theo reactive context nếu framework và driver hỗ trợ |

Điểm quan trọng là kiểu trả về không chứng minh hành vi I/O. Một phương thức trả về **Mono<Customer>** vẫn có thể gọi JDBC đồng bộ ngay trong quá trình tạo Publisher hoặc bên trong một worker blocking. Cần xem cách triển khai của driver và adapter, không chỉ xem chữ ký phương thức.

## R2DBC và hợp đồng truy cập dữ liệu reactive

R2DBC (Reactive Relational Database Connectivity) định nghĩa SPI để truy cập cơ sở dữ liệu quan hệ bằng API reactive. Các thành phần chính gồm:

- **ConnectionFactory**: tạo Publisher cung cấp connection.
- **Connection**: đại diện kết nối và hỗ trợ thao tác transaction.
- **Statement**: mô tả câu lệnh cần thực thi.
- **Result**: biểu diễn kết quả thực thi và các hàng dữ liệu.

Driver R2DBC triển khai SPI cho một hệ quản trị cơ sở dữ liệu cụ thể. Framework như Spring Data R2DBC hoặc Spring Framework **DatabaseClient** cung cấp lớp trừu tượng tiện dụng hơn để tạo câu lệnh, bind tham số và ánh xạ hàng dữ liệu.

Ví dụ truy vấn bằng Spring **DatabaseClient**:

~~~java
DatabaseClient database = DatabaseClient.create(connectionFactory);

Flux<Customer> customers = database.sql("""
        select id, name
        from customer
        where active = :active
        order by id
        """)
    .bind("active", true)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class)
    ))
    .all();
~~~

**all()** trả về một **Flux<Customer>**, phù hợp khi truy vấn có thể trả nhiều hàng. Publisher được tiêu thụ khi có subscription; ứng dụng không cần gọi **block()** để chờ kết quả. Driver và framework chịu trách nhiệm thực thi câu lệnh, đọc kết quả và chuyển các hàng thành phần tử downstream.

Với truy vấn kỳ vọng một kết quả, có thể dùng **one()** hoặc API tương ứng của phiên bản Spring đang sử dụng. Cần chọn đúng hợp đồng:

- **one()** phù hợp khi kết quả phải có tối đa một hàng; nhiều hàng là lỗi.
- **first()** lấy hàng đầu tiên nếu có và không yêu cầu xác nhận rằng truy vấn chỉ trả một hàng.
- **all()** phát các hàng dưới dạng luồng.

Hãy dùng **ORDER BY** nếu nghiệp vụ phụ thuộc vào thứ tự hàng. Cơ sở dữ liệu không bảo đảm thứ tự kết quả khi truy vấn không chỉ định thứ tự.

## Đọc hàng dữ liệu theo luồng

Một lợi ích quan trọng của API reactive là có thể tiêu thụ kết quả tăng dần thay vì buộc phải tải toàn bộ dữ liệu vào một collection. Với **Flux**, downstream có thể biến đổi, lọc, giới hạn hoặc ghi từng hàng vào một pipeline khác:

~~~java
Flux<CustomerSummary> summaries = database.sql("""
        select id, name
        from customer
        where active = :active
        """)
    .bind("active", true)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class)
    ))
    .all()
    .map(CustomerSummary::from);
~~~

Tránh gọi **collectList()** chỉ để dễ xử lý nếu tập kết quả có thể lớn. **collectList()** giữ mọi phần tử trong bộ nhớ cho đến khi nguồn hoàn tất. Nếu downstream chỉ cần tổng hợp, có thể dùng các phép gộp như **reduce**, hoặc xử lý theo từng lô có giới hạn.

Tuy nhiên, **Flux** phát hàng theo luồng không có nghĩa database chỉ tạo đúng một hàng mỗi lần downstream yêu cầu. Driver có thể đọc trước, giữ dữ liệu trong buffer hoặc dùng cơ chế fetch theo lô tùy giao thức và cấu hình. Một số driver hỗ trợ fetch size hoặc cursor; một số khác có giới hạn riêng. Hãy kiểm tra tài liệu driver và đo bộ nhớ khi xử lý tập dữ liệu lớn.

Backpressure điều phối demand giữa Subscriber và Publisher trong pipeline. Nó có thể giúp giới hạn số phần tử được yêu cầu từ upstream, nhưng không đảm bảo mọi tầng bên dưới đều có cùng một cơ chế điều tiết. Khả năng truyền demand đến socket, giao thức database và quá trình thực thi truy vấn phụ thuộc driver. Không nên giả định một lời gọi **request(10)** luôn tương đương database chỉ đọc đúng 10 hàng từ đĩa.

## Backpressure không thay thế thiết kế truy vấn

Ngay cả khi driver hỗ trợ Reactive Streams, truy vấn vẫn có thể tiêu tốn nhiều tài nguyên ở database:

- Truy vấn quét toàn bảng vẫn tốn CPU và I/O ở phía server.
- **ORDER BY** hoặc phép join lớn có thể cần bộ nhớ và thao tác sắp xếp.
- Một truy vấn thiếu index có thể chậm dù downstream yêu cầu dữ liệu từ từ.
- Driver có thể buffer nhiều hàng trước khi phát chúng.

Vì vậy, hãy kết hợp backpressure với thiết kế truy vấn:

1. Chỉ chọn các cột cần dùng.
2. Dùng điều kiện lọc và index phù hợp.
3. Dùng phân trang hoặc keyset pagination cho tập dữ liệu rất lớn.
4. Chọn fetch size nếu driver hỗ trợ và xác minh tác dụng thực tế.
5. Tránh gom toàn bộ luồng thành collection khi không cần thiết.
6. Theo dõi thời gian truy vấn, số hàng đọc, buffer và độ trễ downstream.

Backpressure điều tiết việc tiêu thụ phần tử trong pipeline. Nó không làm truy vấn kém hiệu quả trở nên hiệu quả và không thay thế giới hạn tài nguyên ở database.

## Transaction reactive phải nằm trong reactive pipeline

Transaction JDBC imperative thường dựa vào connection gắn với thread hoặc transaction context của framework. R2DBC có thể hỗ trợ transaction reactive, trong đó connection được quản lý theo subscription context thay vì giả định toàn bộ pipeline luôn chạy trên một thread.

Với Spring, **R2dbcTransactionManager** và **TransactionalOperator** cho phép bao một chuỗi Publisher trong transaction:

~~~java
TransactionalOperator transactional =
    TransactionalOperator.create(r2dbcTransactionManager);

Mono<Void> updateOrder = database.sql("""
        update orders
        set status = :status
        where id = :orderId
        """)
    .bind("status", "PAID")
    .bind("orderId", orderId)
    .fetch()
    .rowsUpdated()
    .then(database.sql("""
        update inventory
        set reserved = reserved + 1
        where product_id = :productId
        """)
        .bind("productId", productId)
        .fetch()
        .rowsUpdated())
    .then()
    .as(transactional::transactional);
~~~

**TransactionalOperator** bao cả chuỗi thao tác để chúng tham gia cùng transaction reactive. Nếu Publisher hoàn tất bình thường, transaction được commit; nếu Publisher kết thúc bằng lỗi, transaction manager thực hiện rollback theo cơ chế của nó.

Không gọi **subscribe()** hoặc **block()** ở giữa một transaction reactive. Làm vậy có thể tạo subscription độc lập, tách thao tác khỏi transaction context mà **TransactionalOperator** đang quản lý. Hãy trả Publisher về cho tầng gọi và để framework điều khiển subscription.

Không nên mở transaction reactive rồi gọi JDBC imperative bên trong và mong JDBC tự tham gia. JDBC transaction manager và R2DBC transaction manager quản lý các loại connection khác nhau. Nếu một nghiệp vụ cần cập nhật cả JDBC và R2DBC, phải thiết kế rõ ranh giới nhất quán dữ liệu; không giả định một transaction manager đơn lẻ tự động tạo distributed transaction cho cả hai.

## Connection pool vẫn cần giới hạn

Driver reactive không làm cho connection trở thành tài nguyên vô hạn. Mỗi connection có chi phí ở database, driver và pool. Nếu ứng dụng tạo quá nhiều truy vấn đồng thời, pool có thể cạn, các request phải chờ lấy connection và độ trễ tăng.

Khi xử lý một luồng yêu cầu, giới hạn concurrency ở tầng ứng dụng:

~~~java
Flux<OrderSummary> summaries = orderIds
    .flatMap(orderId -> orderRepository.findSummary(orderId),
        maxConcurrent);
~~~

**maxConcurrent** cần được chọn dựa trên kích thước pool, năng lực database và lưu lượng của các endpoint khác dùng chung pool. Không nên đặt concurrency bằng toàn bộ số connection tối đa nếu hệ thống còn cần connection cho giao dịch quan trọng khác.

Một số điểm cần theo dõi:

- Số connection đang hoạt động và đang chờ.
- Thời gian chờ lấy connection từ pool.
- Số truy vấn đồng thời và thời gian chạy truy vấn.
- Số lần timeout, lỗi kết nối và cancellation.
- Mức buffer hoặc prefetch mà driver sử dụng.

Nếu nguồn dữ liệu phát nhanh hơn downstream, hãy xác định pipeline có hỗ trợ backpressure và hàng đợi có giới hạn hay không. Tránh dùng **onBackpressureBuffer()** không giới hạn như một cách chữa quá tải; nó có thể chuyển áp lực thành lỗi hết bộ nhớ.

## Cancellation và truy vấn đang chạy

Khi downstream hủy subscription, tín hiệu cancellation được truyền ngược qua pipeline. Driver reactive có thể hỗ trợ hủy truy vấn hoặc dừng việc đọc kết quả, nhưng mức độ hỗ trợ phụ thuộc driver, giao thức và database. Có trường hợp driver dừng phát dữ liệu cho ứng dụng nhưng truy vấn phía server vẫn tiếp tục một thời gian.

Không nên đồng nhất cancellation với rollback:

- Hủy việc đọc kết quả không nhất thiết hoàn tác một câu lệnh ghi đã được thực hiện.
- Hủy subscription không chứng minh server đã dừng truy vấn ngay lập tức.
- Transaction manager có thể thực hiện rollback khi subscription bị hủy trong phạm vi transaction, nhưng hành vi cụ thể cần được kiểm chứng với driver và framework.

Với thao tác ghi, cần thiết kế idempotency và khả năng đối soát. Nếu client mất kết nối sau khi gửi lệnh, ứng dụng có thể không biết database đã commit hay chưa. Hãy dùng mã giao dịch, khóa duy nhất hoặc trạng thái nghiệp vụ để xác định kết quả thay vì tự động gửi lại mọi lệnh.

## Adapter JDBC có thể làm gì và giới hạn ở đâu?

Khi chưa thể thay JDBC, có thể cô lập lời gọi đồng bộ bằng **Mono.fromCallable()** và **Schedulers.boundedElastic()**:

~~~java
Mono<Customer> findCustomerWithJdbc(String customerId) {
    return Mono.fromCallable(() ->
            jdbcTemplate.queryForObject(
                "select id, name from customer where id = ?",
                customerRowMapper,
                customerId
            ))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Cách này có giá trị thực tế:

- Không để event loop trực tiếp chờ JDBC.
- Tích hợp API đồng bộ vào chữ ký **Mono**/**Flux** của service.
- Chuyển exception thành tín hiệu **onError**.
- Có thể đặt timeout reactive, giới hạn concurrency và quan sát thời gian thực thi.

Nhưng adapter không thay đổi bản chất của JDBC:

- Worker **boundedElastic** vẫn bị giữ trong lúc truy vấn chờ.
- JDBC không cung cấp Reactive Streams demand cho từng hàng.
- Cancellation không bảo đảm lời gọi driver đang chạy dừng ngay.
- Transaction imperative vẫn cần được giữ trong phạm vi thực thi đồng bộ phù hợp.
- Nếu adapter tải toàn bộ **ResultSet** vào **List**, bộ nhớ vẫn tăng theo kích thước kết quả.

Vì vậy, adapter là giải pháp cô lập và tương thích, không phải driver reactive. Nó phù hợp khi cần chuyển đổi dần một hệ thống cũ hoặc khi tải và độ trễ vẫn nằm trong giới hạn chấp nhận được. Nếu mục tiêu là xử lý nhiều kết nối đồng thời mà không giữ thread chờ I/O, cần cân nhắc driver reactive native.

## Kiểm thử driver và transaction reactive

Kiểm thử đơn vị có thể xác nhận pipeline phát dữ liệu và lỗi như mong đợi:

~~~java
StepVerifier.create(customerRepository.findActiveCustomers())
    .expectNextMatches(customer ->
        customer.id() != null && customer.active())
    .expectNextCount(2)
    .verifyComplete();
~~~

Với truy vấn có kết quả lớn, kiểm tra rằng pipeline có thể tiêu thụ từng phần tử mà không bắt buộc gom tất cả vào một collection. Có thể dùng **take(n)** để xác minh luồng phát đúng số hàng cần thiết và subscription được hủy sau đó:

~~~java
StepVerifier.create(customerRepository.findAll().take(3))
    .expectNextCount(3)
    .verifyComplete();
~~~

Kiểm thử transaction cần xác nhận cả commit và rollback. Một integration test có thể:

1. Chạy chuỗi cập nhật thành công và xác nhận dữ liệu được commit.
2. Cố ý phát lỗi ở bước thứ hai và xác nhận thay đổi bước đầu được rollback.
3. Hủy subscription trong một thao tác dài và quan sát hành vi cleanup/rollback của transaction manager.
4. Chạy với driver và database thực tế trong môi trường kiểm thử, vì mock Publisher không mô phỏng đầy đủ protocol, pool hoặc cancellation phía server.

Không nên chỉ kiểm thử bằng mock **Mono.just(...)** rồi kết luận driver không blocking hoặc hỗ trợ backpressure đúng. Các đặc tính đó cần được kiểm chứng ở integration test, đo thời gian và quan sát thread thực thi.

## Khi nào nên chọn driver reactive?

Driver reactive phù hợp khi ứng dụng cần xử lý nhiều I/O đồng thời, muốn tránh giữ thread trong lúc chờ database và cần tích hợp transaction vào pipeline reactive. Trước khi chuyển đổi, cần xác nhận:

- Database có driver reactive được hỗ trợ và đủ ổn định không?
- Những tính năng SQL, kiểu dữ liệu, stored procedure và dialect cần dùng có được hỗ trợ không?
- Transaction, isolation level và locking có đáp ứng yêu cầu nghiệp vụ không?
- Connection pool và observability có tương thích không?
- Đội ngũ có thể vận hành và gỡ lỗi stack công nghệ mới không?

Nếu hệ thống chủ yếu dùng JDBC, tải không cao và việc thay driver có chi phí lớn, adapter blocking được giới hạn tốt có thể là lựa chọn hợp lý trong giai đoạn chuyển tiếp. Hãy đo hiệu năng và xác định ngưỡng cần chuyển đổi, thay vì coi reactive driver là mục tiêu bắt buộc cho mọi ứng dụng.

## Những lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Cho rằng trả về **Mono** nghĩa là driver non-blocking | Adapter có thể vẫn gọi JDBC đồng bộ | Kiểm tra implementation và thread thực thi |
| Dùng JDBC trong event loop | Chặn thread phục vụ nhiều request | Cô lập bằng **fromCallable** và **boundedElastic** khi chưa thể thay driver |
| Dùng **collectList()** cho tập dữ liệu lớn | Giữ toàn bộ kết quả trong bộ nhớ | Xử lý theo luồng, trang hoặc lô có giới hạn |
| Cho rằng backpressure giới hạn mọi buffer trong database | Driver và protocol có thể prefetch hoặc buffer | Kiểm tra fetch behavior và cấu hình của driver |
| Gọi **subscribe()** trong transaction reactive | Tạo subscription ngoài transaction context | Kết hợp Publisher và để tầng gọi subscribe |
| Cho rằng cancellation luôn dừng query hoặc rollback | Driver/server có thể vẫn đang thực thi | Kiểm thử driver, cấu hình timeout và đối soát side effect |
| Tăng concurrency theo số request mà không xét pool | Connection pool và database có thể quá tải | Giới hạn **flatMap** và theo dõi pool |
| Dùng adapter JDBC như giải pháp non-blocking lâu dài | Worker vẫn bị giữ khi chờ I/O | Cân nhắc driver reactive native khi yêu cầu tải đòi hỏi |

## Nguyên tắc lựa chọn và tích hợp

Trước khi chọn driver hoặc adapter cho một pipeline dữ liệu, hãy xác định:

1. API bên dưới có thực sự dùng I/O bất đồng bộ hay chỉ bọc lời gọi blocking?
2. Dữ liệu được phát theo luồng hay bị gom toàn bộ trước khi trả về?
3. Backpressure có được driver hỗ trợ đến mức nào và còn buffer/prefetch ở đâu?
4. Transaction được quản lý theo thread hay reactive context?
5. Connection pool, concurrency và timeout đã được đặt theo năng lực database chưa?
6. Cancellation có dừng việc đọc, hủy truy vấn hoặc rollback theo mức nào?
7. Integration test có chạy với driver và database thật để xác minh các hành vi này không?

Driver reactive cung cấp nền tảng I/O bất đồng bộ và có thể phối hợp demand, transaction cùng vòng đời subscription trong một pipeline. Adapter JDBC giúp tích hợp hệ thống cũ và bảo vệ event loop, nhưng worker vẫn chờ I/O và các giới hạn của JDBC vẫn còn. Phân biệt đúng hai cách tiếp cận giúp chọn kiến trúc dữ liệu phù hợp với tải, yêu cầu nhất quán và khả năng vận hành của ứng dụng.
