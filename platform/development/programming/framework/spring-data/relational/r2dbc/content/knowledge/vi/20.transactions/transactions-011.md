# Tránh tác vụ song song không phù hợp trên cùng kết nối giao dịch

Trong Spring Data Relational R2DBC, các thao tác database nằm trong cùng reactive transaction thường dùng chung một connection được transaction manager gắn vào Reactor Context. Vì vậy, nếu một reactive pipeline phát nhiều câu SQL đồng thời bằng flatMap, zip hoặc when, các thao tác đó có thể cùng truy cập một connection transaction-bound.

Không nên mặc định rằng một R2DBC Connection có thể thực thi nhiều statement đồng thời an toàn. Khả năng xử lý đồng thời phụ thuộc driver và database; một số driver từ chối thao tác chồng lấn, một số có thể xếp hàng hoặc có giới hạn riêng. Ngay cả khi driver chấp nhận, thứ tự thực thi và trạng thái transaction vẫn cần được kiểm soát.

**Nếu nhiều câu SQL phải tham gia cùng một transaction trên cùng connection, hãy nối chúng tuần tự bằng then, flatMap theo chuỗi hoặc concatMap.** Chỉ chạy song song khi các công việc thực sự độc lập và được cấp connection/transaction riêng, đồng thời nghiệp vụ chấp nhận khả năng commit hoặc rollback độc lập.

## 1. Vì sao các thao tác trong cùng transaction dùng chung connection?

R2dbcTransactionManager quản lý transaction cho một ConnectionFactory. Khi transaction reactive bắt đầu, Spring lấy một Connection, bắt đầu transaction và bind tài nguyên vào Reactor Context. Các thao tác DatabaseClient hoặc repository sử dụng cùng ConnectionFactory trong reactive chain có thể lấy lại connection đã được bind đó.

Luồng khái quát:

~~~text
Reactive transaction bắt đầu
             |
             v
Acquire một R2DBC Connection
             |
             v
Bind Connection vào Reactor Context
             |
       +-----+------+
       |            |
       v            v
 Repository A   DatabaseClient B
       |            |
       +-----+------+
             |
             v
 Cùng tham gia transaction trên connection đó
             |
             v
       Commit / Rollback
             |
             v
        Release Connection
~~~

Đây là điều giúp nhiều thao tác ở các repository khác nhau cùng commit hoặc rollback. Nhưng nó cũng có nghĩa các thao tác không tự có một connection riêng chỉ vì chúng được đặt trong những nhánh reactive khác nhau.

Reactor Context được truyền theo subscription, không phụ thuộc một thread cố định. Chuyển scheduler bằng publishOn hoặc subscribeOn không tự tạo transaction mới hay connection mới.

## 2. Vì sao phát SQL đồng thời trên cùng connection có thể gây vấn đề?

R2DBC Connection là một tài nguyên có trạng thái: nó có transaction hiện tại, isolation, auto-commit và các hoạt động protocol đang diễn ra. Một số driver không cho phép nhiều statement cùng chạy đồng thời trên một connection. Một số driver có thể tuần tự hóa nội bộ, nhưng không nên dựa vào hành vi riêng đó như một bảo đảm portable.

Khi nhiều nhánh phát lệnh đồng thời trên cùng connection, ứng dụng có thể gặp:

- Driver báo lỗi vì connection đang bận hoặc có một exchange khác chưa hoàn tất.
- Statement thứ hai phải chờ statement thứ nhất trong hàng đợi nội bộ, khiến concurrency trong code không tạo ra lợi ích.
- Thứ tự hoàn tất khác thứ tự nghiệp vụ mong muốn.
- Một nhánh lỗi hoặc bị cancel trong khi nhánh khác vẫn đang thực thi.
- Khó xác định thao tác nào đã chạy trước khi transaction rollback.
- Tải lên connection và database tăng mà không tăng throughput thực tế.

Lỗi cụ thể phụ thuộc driver. Có thể thấy thông báo về concurrent statement, connection busy, protocol exchange hoặc transaction state. Không có một thông điệp lỗi duy nhất áp dụng cho mọi R2DBC driver.

Điểm cốt lõi là: các nhánh reactive có thể được subscribe đồng thời, nhưng chúng không vì thế mà nhận được các connection transaction độc lập.

## 3. Những operator dễ tạo truy vấn đồng thời

### flatMap

flatMap subscribe vào inner publisher khi phần tử nguồn được phát ra. Mặc định nó có thể xử lý nhiều inner publisher cùng lúc:

~~~java
@Transactional
public Mono<Void> processOrder(Order order) {
    return Mono.when(
        inventoryRepository.reserve(order),
        orderRepository.save(order),
        auditRepository.save(toAudit(order))
    ).then();
}
~~~

Trong ví dụ trên, Mono.when subscribe các publisher đầu vào để chờ tất cả hoàn tất. Nếu chúng cùng dùng ConnectionFactory được transaction manager quản lý, chúng có thể cùng sử dụng connection transaction-bound.

Một ví dụ khác:

~~~java
@Transactional
public Flux<CustomerView> loadViews() {
    return customerRepository.findAll()
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerView(customer, orders)
                )
        );
}
~~~

flatMap có thể phát nhiều truy vấn con cùng lúc. Nếu pipeline nằm trong một transaction, những truy vấn đó có thể cùng dùng connection đã bind.

### zip

Mono.zip cần subscribe vào các nguồn để lấy kết quả của chúng:

~~~java
@Transactional
public Mono<TransferView> loadTransferData(Long fromId, Long toId) {
    return Mono.zip(
        accountRepository.findById(fromId),
        accountRepository.findById(toId)
    ).map(tuple ->
        new TransferView(tuple.getT1(), tuple.getT2())
    );
}
~~~

Hai truy vấn có thể được subscribe đồng thời. Nếu chúng tham gia cùng reactive transaction, không nên giả định mỗi truy vấn được cấp một connection khác nhau.

### parallel và runOn

~~~java
@Transactional
public Mono<Void> updateAll(List<Long> ids) {
    return Flux.fromIterable(ids)
        .parallel()
        .runOn(Schedulers.parallel())
        .flatMap(id -> customerRepository.refreshStatus(id))
        .sequential()
        .then();
}
~~~

parallel() chia dữ liệu thành nhiều rail và runOn() điều phối việc xử lý trên scheduler. Chúng không tự tạo transaction hoặc connection riêng cho từng rail. Nếu các thao tác database dùng transaction context hiện tại, chúng vẫn có thể cạnh tranh trên cùng connection.

### flatMapSequential

flatMapSequential giữ thứ tự phát kết quả theo nguồn, nhưng vẫn có thể subscribe và chạy inner publisher đồng thời. Nó chỉ điều chỉnh thứ tự phát kết quả; không bảo đảm SQL được thực thi tuần tự trên cùng connection.

### concatMap

concatMap chỉ subscribe inner publisher tiếp theo sau khi publisher hiện tại hoàn tất. Đây là lựa chọn phù hợp khi cần thực thi từng thao tác database lần lượt:

~~~java
return Flux.fromIterable(ids)
    .concatMap(id -> customerRepository.refreshStatus(id))
    .then();
~~~

## 4. Cách viết an toàn: nối thao tác bằng then và flatMap

Nếu nghiệp vụ yêu cầu nhiều thao tác database cùng transaction, hãy nối chúng theo đúng thứ tự cần thiết:

~~~java
@Transactional
public Mono<Void> placeOrder(Order order) {
    return inventoryRepository.reserve(order)
        .then(orderRepository.save(order))
        .flatMap(savedOrder ->
            orderLineRepository.saveAll(savedOrder.getLines())
                .then()
                .thenReturn(savedOrder)
        )
        .flatMap(savedOrder ->
            auditRepository.save(toAudit(savedOrder))
        )
        .then();
}
~~~

Trong pipeline này:

1. reserve hoàn tất trước khi save order bắt đầu.
2. Order được lưu trước khi lưu các dòng hàng.
3. Các dòng hàng hoàn tất trước khi ghi audit.
4. Toàn bộ publisher được trả về để Spring quản lý trong cùng transaction.

then() bỏ qua giá trị của publisher trước và chỉ subscribe publisher kế tiếp khi publisher trước hoàn tất thành công. flatMap tiếp tục bằng publisher được tạo từ kết quả trước đó.

Nếu một bước phát lỗi, lỗi tiếp tục đi ra khỏi reactive chain và transaction mặc định rollback với RuntimeException hoặc Error. Không nên tự subscribe bên trong service.

### Nhiều thao tác cùng loại: dùng concatMap

Nếu phải lưu từng dòng theo thứ tự:

~~~java
public Mono<Void> saveLines(List<OrderLine> lines) {
    return Flux.fromIterable(lines)
        .concatMap(orderLineRepository::save)
        .then();
}
~~~

concatMap bảo đảm mỗi lần save hoàn tất trước khi bắt đầu save tiếp theo. Nếu số lượng dòng rất lớn, cần cân nhắc batch insert hoặc API saveAll phù hợp thay vì tạo một publisher cho từng dòng; tuy nhiên vẫn phải hiểu semantics và cách driver thực thi của phiên bản đang dùng.

## 5. Vì sao không dùng zip hoặc when cho các câu SQL trong cùng transaction?

zip và when rất hữu ích khi các nguồn có thể chạy độc lập. Nhưng khi chúng phát nhiều câu SQL trên cùng connection transaction-bound, chúng tạo ra cạnh tranh không cần thiết.

Ví dụ không nên dùng cho các thao tác ghi cùng transaction:

~~~java
@Transactional
public Mono<Void> createCustomer(Customer customer) {
    return Mono.when(
        customerRepository.save(customer),
        auditRepository.save(toAudit(customer)),
        notificationRecordRepository.save(toNotification(customer))
    ).then();
}
~~~

Nếu ba thao tác phải cùng commit, hãy nối tuần tự:

~~~java
@Transactional
public Mono<Void> createCustomer(Customer customer) {
    return customerRepository.save(customer)
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .then(notificationRecordRepository.save(
                    toNotification(saved)
                ))
        )
        .then();
}
~~~

Ví dụ này cũng giúp dùng ID do database tạo ở bước đầu cho các bước sau.

Nếu các thao tác thật sự độc lập và không cần cùng transaction, có thể chạy song song ở ngoài transaction chung hoặc mỗi công việc có transaction riêng. Khi làm vậy, cần chấp nhận rằng một công việc có thể commit trong khi công việc khác thất bại.

## 6. Phân biệt tuần tự hóa thao tác và giữ thứ tự kết quả

Các operator sau có semantics khác nhau:

| Operator | Cách xử lý inner publisher | Có bảo đảm không chạy đồng thời? |
|---|---|---|
| flatMap | Có thể subscribe nhiều inner publisher cùng lúc | Không |
| flatMapSequential | Có thể chạy inner publisher đồng thời, giữ thứ tự phát kết quả | Không |
| concatMap | Chờ inner publisher hiện tại hoàn tất rồi mới subscribe publisher tiếp | Có, theo chuỗi đó |
| then | Chạy publisher sau khi publisher trước hoàn tất | Có, theo chuỗi đó |
| Mono.zip | Kết hợp kết quả nhiều nguồn được subscribe | Không |
| Mono.when | Chờ nhiều nguồn hoàn tất | Không |

Nếu mục tiêu là giữ thứ tự hiển thị kết quả, flatMapSequential có thể hữu ích. Nếu mục tiêu là không phát SQL đồng thời trên cùng connection, cần concatMap hoặc nối publisher bằng then/flatMap theo chuỗi.

Đừng chọn operator chỉ dựa trên thứ tự phần tử được phát ra. Cần xem thời điểm các inner publisher được subscribe và thời gian chúng thực hiện I/O.

## 7. Khi nào có thể chạy song song?

Song song phù hợp khi các công việc độc lập về dữ liệu và không cần chia sẻ một transaction-bound connection.

Ví dụ:

- Tính toán CPU trên dữ liệu đã tải về, không thực hiện SQL.
- Gọi các dịch vụ độc lập bên ngoài database khi không giữ transaction mở.
- Xử lý các message độc lập, mỗi message có transaction riêng.
- Chạy các batch độc lập, mỗi batch dùng một transaction/connection riêng và nghiệp vụ cho phép commit độc lập.

Điều kiện quan trọng là mỗi nhánh database cần một transaction context và connection phù hợp riêng. Chỉ đổi scheduler không đủ để đạt điều đó.

### Các tác vụ CPU độc lập

Sau khi đã tải dữ liệu cần thiết, có thể thực hiện phép tính thuần CPU song song nếu lợi ích đáng kể:

~~~java
return customerRepository.findAll()
    .collectList()
    .flatMapMany(customers ->
        Flux.fromIterable(customers)
            .parallel()
            .runOn(Schedulers.parallel())
            .map(this::calculateScore)
            .sequential()
    );
~~~

calculateScore trong ví dụ phải là phép tính trên dữ liệu có sẵn và không gọi repository hoặc DatabaseClient. Nếu nó thực hiện SQL, các nhánh có thể lại truy cập cùng transaction context.

Với tác vụ CPU nặng, hãy cân nhắc kích thước tập dữ liệu và bộ nhớ khi collectList(). Không cần đưa một phép tính nhỏ lên parallel scheduler nếu chi phí điều phối lớn hơn lợi ích.

## 8. Chạy nhiều công việc database độc lập bằng transaction riêng

Nếu từng item có thể commit hoặc rollback độc lập, có thể xử lý nhiều item đồng thời và bao từng item bằng một transaction riêng:

~~~java
public Flux<ProcessedResult> processIndependentItems(
        List<Command> commands) {

    return Flux.fromIterable(commands)
        .flatMap(
            command -> transactionalOperator.transactional(
                processOne(command)
            ),
            8
        );
}
~~~

Trong cách tổ chức này:

- Không đặt toàn bộ phương thức bên ngoài trong một @Transactional chung.
- Mỗi inner publisher được bọc bởi TransactionalOperator.
- Mỗi subscription độc lập có thể bắt đầu transaction và lấy connection riêng.
- Concurrency 8 giới hạn số transaction chạy đồng thời trong ví dụ.
- Một item thất bại có thể rollback transaction của chính item đó; các item khác có thể đã commit.

Đây là chiến lược phù hợp chỉ khi nghiệp vụ cho phép tính độc lập. Nếu toàn bộ danh sách phải thành công hoặc thất bại như một đơn vị, không thể chia thành các transaction riêng mà vẫn giữ nguyên tính nguyên tử toàn bộ. Khi đó, hãy thực hiện tuần tự trong một transaction hoặc thiết kế quy trình bù trừ/saga phù hợp.

Nếu một transaction bên ngoài đã tồn tại, propagation mặc định REQUIRED của TransactionalOperator có thể khiến các thao tác bên trong tham gia transaction hiện tại thay vì tạo transaction độc lập. Cần đặt boundary đúng và chỉ dùng REQUIRES_NEW khi thật sự muốn tách transaction, transaction manager hỗ trợ và nghiệp vụ chấp nhận tính độc lập đó.

## 9. Giới hạn concurrency không biến một transaction thành nhiều connection

Có thể truyền concurrency cho flatMap:

~~~java
return Flux.fromIterable(commands)
    .flatMap(this::processCommand, 4);
~~~

Điều này giới hạn số inner publisher đang hoạt động. Nó không có nghĩa Spring sẽ cấp bốn connection cho bốn nhánh nếu chúng cùng nằm trong một reactive transaction.

Nếu processCommand thực hiện SQL trong transaction context hiện tại, các nhánh vẫn có thể dùng cùng connection. Concurrency limit hữu ích để bảo vệ hệ thống trước tải quá lớn, nhưng không thay thế việc thiết kế transaction boundary.

Để có nhiều connection độc lập, mỗi nhánh phải thực sự chạy trong transaction/subscription độc lập và không kế thừa một transaction context bên ngoài đang bind connection dùng chung.

## 10. Không dùng scheduler để chữa vấn đề connection

Các thao tác R2DBC được thiết kế non-blocking. Thông thường, không cần bọc repository call bằng Schedulers.parallel() hoặc subscribeOn chỉ để “chạy database trên thread khác”.

Ví dụ không giải quyết concurrency trên connection:

~~~java
@Transactional
public Mono<Void> update(Long id) {
    return customerRepository.findById(id)
        .subscribeOn(Schedulers.parallel())
        .flatMap(customer ->
            customerRepository.save(customer)
                .subscribeOn(Schedulers.parallel())
        )
        .then();
}
~~~

subscribeOn điều phối việc subscription, nhưng transaction resource được truyền qua Reactor Context. Thay đổi thread không tự tách transaction hay tạo connection riêng.

Không nên dùng block() hoặc blockFirst() để tuần tự hóa các thao tác R2DBC. Cách đó chặn thread, phá vỡ reactive flow và có thể gây deadlock hoặc lỗi khi chạy trên non-blocking scheduler.

Nếu có thư viện blocking, hãy cô lập phần blocking khỏi transaction R2DBC và không giữ connection/transaction trong khi chờ công việc blocking lâu. Việc chuyển scheduler không biến JDBC hoặc I/O blocking thành reactive.

## 11. Giữ transaction ngắn và tránh gọi dịch vụ ngoài trong transaction

Một transaction giữ connection và có thể giữ lock cho tới khi commit hoặc rollback. Nếu gọi HTTP service, gửi email hoặc chờ xử lý lâu trong transaction, connection bị giữ lâu hơn dù database không thực hiện câu SQL nào.

Ví dụ không nên:

~~~java
@Transactional
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            paymentClient.charge(saved)
                .thenReturn(saved)
        );
}
~~~

Lệnh gọi payment có thể chậm hoặc timeout trong khi transaction database vẫn mở. Nếu payment thành công nhưng transaction database rollback, hai hệ thống có thể ở trạng thái không nhất quán.

Một cách tổ chức thường tốt hơn là:

1. Ghi order và một outbox event trong cùng database transaction.
2. Commit transaction.
3. Một worker riêng đọc outbox và gọi payment/notification theo chính sách retry.
4. Ghi nhận kết quả hoặc thực hiện quy trình bù trừ khi cần.

Outbox không tự làm một dịch vụ ngoài trở thành thành viên của database transaction; nó giúp lưu ý định phát sự kiện một cách bền vững cùng dữ liệu nghiệp vụ.

## 12. Ví dụ chuyển khoản cần thứ tự

Một nghiệp vụ chuyển tiền cần trừ tài khoản nguồn, cộng tài khoản đích và ghi giao dịch. Nếu tất cả phải cùng commit hoặc rollback, không nên chạy ba câu SQL song song:

~~~java
@Transactional
public Mono<Void> transfer(
        Long fromId,
        Long toId,
        BigDecimal amount) {

    return accountRepository.debit(fromId, amount)
        .flatMap(debited ->
            accountRepository.credit(toId, amount)
        )
        .flatMap(credited ->
            transferRepository.record(
                fromId, toId, amount
            )
        )
        .then();
}
~~~

Mỗi thao tác bắt đầu sau khi thao tác trước hoàn tất. Transaction manager giữ cùng transaction context xuyên suốt pipeline. Nếu bất kỳ thao tác nào phát lỗi phù hợp với rollback policy, transaction rollback.

Trong nghiệp vụ tài chính, thứ tự còn liên quan đến kiểm tra số dư, optimistic/pessimistic locking và isolation. Việc tuần tự hóa câu lệnh trên một connection không tự giải quyết mọi race condition giữa các transaction khác nhau. Cần dùng điều kiện update nguyên tử, version, lock hoặc isolation phù hợp với quy tắc nghiệp vụ.

## 13. Ví dụ đọc hai bản ghi rồi kết hợp kết quả

Nếu hai truy vấn cần cùng transaction vì phải đọc một snapshot hoặc phục vụ quyết định nghiệp vụ, có thể thực hiện tuần tự:

~~~java
@Transactional
public Mono<TransferView> loadAccounts(Long fromId, Long toId) {
    return accountRepository.findById(fromId)
        .switchIfEmpty(Mono.error(
            new AccountNotFoundException(fromId)
        ))
        .flatMap(from ->
            accountRepository.findById(toId)
                .switchIfEmpty(Mono.error(
                    new AccountNotFoundException(toId)
                ))
                .map(to -> new TransferView(from, to))
        );
}
~~~

Truy vấn thứ hai chỉ bắt đầu sau khi truy vấn thứ nhất trả về. Cả hai có thể tham gia cùng transaction và cùng connection mà không cần phát SQL đồng thời.

Nếu không cần cùng transaction hoặc cùng snapshot, và hai truy vấn thật sự độc lập, có thể cân nhắc chạy song song ngoài transaction chung. Quyết định phải dựa trên yêu cầu nhất quán dữ liệu, không chỉ dựa trên mong muốn giảm latency.

## 14. Xử lý lỗi và cancellation khi các bước chạy tuần tự

Khi các publisher được nối bằng then hoặc concatMap:

- Bước sau chỉ bắt đầu khi bước trước hoàn tất thành công.
- Nếu một bước phát onError, các bước tiếp theo không được thực hiện.
- Lỗi đi ra transaction boundary để Spring áp dụng rollback policy.
- Nếu subscriber cancel, upstream bị hủy và reactive transaction được rollback theo lifecycle transaction.

Không nên bắt lỗi rồi chuyển thành Mono.empty() giữa các bước nếu nghiệp vụ yêu cầu rollback:

~~~java
return debit()
    .onErrorResume(error -> Mono.empty())
    .then(credit());
~~~

Đoạn code này có thể tiếp tục credit dù debit thất bại. Publisher đã biến lỗi thành completion bình thường, nên transaction có thể commit một trạng thái không đúng nghiệp vụ.

Nếu muốn ghi log, dùng doOnError và để lỗi tiếp tục đi ra. Nếu cần chuyển lỗi thành lỗi domain, dùng onErrorMap nhưng vẫn giữ tín hiệu onError.

## 15. Theo dõi dấu hiệu sử dụng connection không phù hợp

Khi gặp lỗi hoặc hiệu năng kém trong transaction reactive, nên quan sát:

- SQL statement nào được thực thi trong cùng request/transaction.
- Có nhiều statement bắt đầu trước khi statement trước hoàn tất không.
- Driver có báo connection busy, concurrent request hoặc protocol exchange error không.
- Thời gian giữ connection và thời gian chờ acquire.
- Số connection active/idle trong pool.
- Thời gian transaction và số statement trong transaction.
- Có publisher nào bị cancel hoặc timeout khi transaction đang chạy không.

Tracing có thể cho thấy nhiều database span chồng thời gian trong một transaction. Log SQL và metric của connection pool giúp phân biệt vấn đề concurrency với vấn đề query chậm hoặc pool thiếu connection.

Không nên bật logging tham số nhạy cảm ở production chỉ để kiểm tra concurrency. Dùng query fingerprint, trace ID và thông tin thời gian đã được che dữ liệu phù hợp.

## 16. Kiểm thử để phát hiện truy cập đồng thời trên cùng transaction

Nên có integration test sử dụng R2DBC driver và database thực tế hoặc Testcontainers:

1. Mở một reactive transaction.
2. Thực hiện nhiều thao tác repository trên cùng ConnectionFactory.
3. Xác nhận các thao tác tuần tự bằng then/concatMap hoàn tất đúng thứ tự.
4. Kiểm tra trường hợp một thao tác lỗi thì toàn bộ thay đổi trong transaction rollback.
5. Kiểm tra code dùng flatMap/zip có phát sinh lỗi hoặc hành vi khác với driver đang triển khai không.
6. Nếu xử lý song song bằng transaction riêng, xác nhận mỗi item có transaction độc lập và kết quả commit/rollback đúng yêu cầu.
7. Đo số connection được sử dụng và số statement đồng thời nếu có instrumentation.

Không nên dựa vào một mock repository để chứng minh driver cho phép hoặc từ chối concurrent statement trên cùng connection. Semantics này cần được xác nhận với driver thực tế.

## 17. Bảng chọn cách tổ chức

| Nhu cầu | Cách làm phù hợp |
|---|---|
| Nhiều câu SQL phải cùng atomic transaction | Nối tuần tự bằng then/flatMap/concatMap |
| Lưu nhiều phần tử theo thứ tự | Flux.concatMap hoặc batch API phù hợp |
| Chỉ cần giữ thứ tự kết quả nhưng tác vụ độc lập | Có thể dùng flatMapSequential, sau khi xác nhận connection/transaction riêng |
| Nhiều tác vụ độc lập, mỗi tác vụ được commit riêng | Mỗi tác vụ có transaction và connection riêng; giới hạn concurrency |
| Tính toán CPU trên dữ liệu đã tải | Có thể parallelize phần tính toán, không gọi SQL trong các rail |
| Gọi HTTP hoặc gửi email | Tránh giữ database transaction mở; cân nhắc outbox |
| Cần tất cả item thành công hoặc thất bại cùng nhau | Một transaction chung với các thao tác SQL tuần tự |
| Muốn giảm thời gian query | Tối ưu SQL/index hoặc batch query; không phát nhiều statement đồng thời trên cùng connection |

## 18. Các lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Mono.when nhiều repository call trong một transaction | Nhiều SQL có thể chạy đồng thời trên cùng connection | Nối bằng then/flatMap tuần tự |
| Mono.zip hai query trong transaction | Hai nguồn được subscribe đồng thời | Thực hiện query thứ hai sau query thứ nhất nếu dùng cùng connection |
| flatMap query con theo từng entity | Tạo nhiều truy vấn đồng thời và có thể là N+1 | Batch query hoặc concatMap nếu phải tuần tự |
| flatMapSequential rồi cho rằng SQL tuần tự | Inner publisher vẫn có thể chạy đồng thời | Dùng concatMap |
| parallel()/runOn() để tách DB connection | Scheduler không tạo transaction/connection mới | Thiết kế transaction riêng rõ ràng |
| Giới hạn flatMap concurrency và cho rằng đã tách connection | Các nhánh vẫn có thể chia sẻ transaction context | Dùng transaction độc lập nếu nghiệp vụ cho phép |
| subscribe() trong service | Tạo subscription ngoài lifecycle của caller | Trả publisher và compose |
| block() để đợi từng câu SQL | Chặn thread và phá reactive flow | Dùng then/concatMap |
| Gọi HTTP trong transaction | Giữ connection/lock trong lúc chờ mạng | Tách side effect, cân nhắc outbox |
| Tách transaction cho nghiệp vụ cần atomic toàn bộ | Một phần có thể commit dù phần khác lỗi | Giữ một transaction và chạy tuần tự |

## 19. Quy trình quyết định

Trước khi dùng operator có concurrency trong một service R2DBC, hãy xác định:

1. Những thao tác nào thực sự cần nằm trong cùng transaction?
2. Các thao tác có dùng cùng ConnectionFactory và transaction manager không?
3. Operator có subscribe nhiều inner publisher đồng thời không?
4. Các inner publisher có thực hiện SQL trên transaction-bound connection không?
5. Thứ tự SQL có ý nghĩa với nghiệp vụ không?
6. Nếu tách thành transaction riêng, nghiệp vụ có chấp nhận commit một phần không?
7. Có cần giới hạn concurrency để bảo vệ pool và database không?
8. Driver thực tế có hỗ trợ concurrent statement trên một connection không, và có lý do nào để dựa vào khả năng đó không?
9. Có thể thay N+1 bằng JOIN hoặc batch query không?
10. Đã kiểm thử commit, rollback, cancellation và kết quả cuối cùng trên driver thực tế chưa?

Nếu nhiều thao tác phải cùng atomic trên một transaction, mặc định hãy chạy SQL tuần tự. Nếu muốn tăng concurrency, hãy tách công việc thành các đơn vị độc lập với transaction/connection riêng và thiết kế rõ semantics khi một đơn vị thất bại.

## 20. Ghi nhớ

- R2dbcTransactionManager bind một connection vào Reactor Context cho reactive transaction.
- Các repository và DatabaseClient dùng cùng ConnectionFactory trong transaction thường tham gia cùng transaction-bound connection.
- Không mặc định nhiều statement có thể chạy đồng thời an toàn trên cùng connection; hành vi cụ thể phụ thuộc driver.
- flatMap, zip, when và parallel có thể tạo subscription hoặc I/O đồng thời.
- flatMapSequential giữ thứ tự phát kết quả nhưng không bảo đảm inner SQL chạy tuần tự.
- then và concatMap giúp nối các thao tác database lần lượt trên cùng transaction.
- Đổi scheduler không tự tạo connection hoặc transaction mới.
- Giới hạn concurrency giảm số nhánh hoạt động cùng lúc nhưng không tự tách connection nếu chúng chia sẻ transaction context.
- Chạy song song database work chỉ khi mỗi nhánh có transaction/connection riêng và nghiệp vụ chấp nhận tính độc lập.
- Không gọi subscribe() hoặc block() trong service để điều khiển thứ tự.
- Giữ transaction ngắn; tránh chờ HTTP, email hoặc tác vụ ngoài trong lúc giữ connection.
- Kiểm thử với R2DBC driver thực tế để xác nhận hành vi connection, thứ tự, rollback và cancellation.
