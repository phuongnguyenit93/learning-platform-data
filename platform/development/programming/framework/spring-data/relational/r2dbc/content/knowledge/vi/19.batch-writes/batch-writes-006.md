# Kiểm soát thứ tự ghi và mức đồng thời

Khi ghi nhiều bản ghi bằng Spring Data R2DBC, hai câu hỏi quan trọng là **các thao tác phải chạy theo thứ tự nào** và **bao nhiêu thao tác được phép chạy đồng thời**. Chọn sai Reactor operator có thể làm thay đổi thứ tự hoàn tất, tạo tải quá lớn lên connection pool, gây lock contention hoặc khiến một phần dữ liệu đã được ghi dù một phần khác thất bại.

Reactive không có nghĩa mọi thao tác nên chạy song song. Nếu bản ghi B phụ thuộc bản ghi A, cần bảo đảm A hoàn tất trước khi ghi B. Nếu các bản ghi độc lập, có thể tăng concurrency để tận dụng I/O bất đồng bộ, nhưng phải giới hạn theo khả năng của database và pool. Nếu toàn bộ batch cần atomic, tất cả thao tác phải nằm trong cùng reactive transaction boundary và dùng đúng `ConnectionFactory`.

Một cách nhìn hữu ích là tách bốn khái niệm thường bị nhầm lẫn:

- **Thứ tự đầu vào:** thứ tự các phần tử xuất hiện trong `Flux` hoặc collection nguồn.
- **Thứ tự bắt đầu thực thi:** thao tác database nào được gửi trước.
- **Thứ tự hoàn tất/commit:** thao tác nào hoàn tất hoặc commit trước.
- **Thứ tự kết quả đọc:** thứ tự hàng được trả về khi query dữ liệu.

Các thứ tự này không tự động giống nhau. `flatMap` có thể giữ thứ tự nguồn khi lấy dữ liệu đầu vào nhưng cho phép các thao tác con hoàn tất không theo thứ tự. Ngay cả khi insert được gửi tuần tự, database cũng không bảo đảm một query `SELECT` sau đó trả hàng theo thứ tự insert nếu không có `ORDER BY`.

## 1. Vì sao thứ tự ghi và concurrency quan trọng?

Giả sử một import cần ghi ba nhóm dữ liệu:

1. Tạo đơn hàng.
2. Ghi các dòng hàng tham chiếu đến đơn hàng.
3. Ghi lịch sử xử lý tham chiếu đến đơn hàng và dòng hàng.

Các bước có quan hệ phụ thuộc khóa ngoại. Nếu ghi dòng hàng trước khi đơn hàng tồn tại, database có thể từ chối vì foreign key. Nếu lịch sử cần ID được sinh từ thao tác trước, bước sau phải đợi ID đó.

Ngược lại, nếu import 1.000 bản ghi khách hàng độc lập, không có quan hệ phụ thuộc và không cần thứ tự nghiệp vụ, chạy một số thao tác đồng thời có thể tăng throughput đáng kể so với tuần tự từng hàng.

Mức concurrency quá thấp làm giảm khả năng tận dụng I/O. Mức quá cao có thể gây:

- Connection pool cạn và nhiều publisher chờ acquire connection.
- Database phải xử lý quá nhiều statement cùng lúc.
- Lock contention, deadlock và serialization failure.
- Tăng memory do prefetch, queue và kết quả chờ được phát ra.
- Tăng thời gian phản hồi do CPU, disk hoặc network bị bão hòa.
- Khó xác định phần dữ liệu nào đã ghi khi một nhóm thao tác thất bại.

Vì vậy, cần chọn operator dựa trên quan hệ phụ thuộc, yêu cầu atomicity và giới hạn tài nguyên, không chỉ dựa trên việc code nào ngắn hơn.

## 2. Các Reactor operator thường dùng khi ghi nhiều bản ghi

| Operator | Cách thực thi publisher con | Thứ tự phát kết quả | Khi phù hợp |
|---|---|---|---|
| `concatMap` | Subscribe publisher con lần lượt; chờ publisher hiện tại kết thúc rồi mới đến publisher kế tiếp | Theo thứ tự nguồn | Các thao tác phụ thuộc hoặc cần tuần tự hóa. |
| `flatMap` | Cho phép nhiều publisher con chạy đồng thời, giới hạn bằng `concurrency` nếu khai báo | Không bảo đảm theo thứ tự nguồn | Các thao tác độc lập, cần tăng throughput. |
| `flatMapSequential` | Subscribe nhiều publisher con đồng thời nhưng giữ thứ tự phát kết quả theo nguồn | Theo thứ tự nguồn | Cần concurrency nhưng downstream cần nhận kết quả theo thứ tự. |
| `concatMapDelayError` | Tuần tự như `concatMap`, nhưng trì hoãn phát lỗi theo cấu hình | Theo thứ tự nguồn | Cần thu thập thêm kết quả trước khi báo lỗi; phải cân nhắc partial write. |
| `buffer` | Gom phần tử thành nhóm trước khi xử lý | Theo thứ tự phần tử trong từng nhóm | Ghi theo batch/chunk. |

Điểm quan trọng: thứ tự phát kết quả của `flatMapSequential` không có nghĩa các side effect database được thực hiện hoặc commit tuần tự. Các publisher con vẫn có thể chạy đồng thời; operator chỉ đệm kết quả để phát theo thứ tự nguồn. Nếu thao tác ghi B chỉ được bắt đầu sau khi thao tác ghi A hoàn tất, dùng `concatMap` hoặc chain `then`.

## 3. Dùng concatMap khi thứ tự ghi là bắt buộc

Ví dụ ghi từng bản ghi theo đúng thứ tự đầu vào:

```java
Mono<Void> saveInOrder(Flux<Customer> customers) {
    return customers
        .concatMap(customerRepository::save)
        .then();
}
```

`concatMap` chỉ subscribe publisher `save` tiếp theo sau khi publisher hiện tại hoàn tất. Vì vậy, thao tác ghi được compose tuần tự theo thứ tự nguồn.

Đây là lựa chọn phù hợp khi:

- Bản ghi sau phụ thuộc ID hoặc trạng thái do bản ghi trước tạo ra.
- Có ràng buộc nghiệp vụ yêu cầu xử lý theo thứ tự sự kiện.
- Các thao tác cùng cập nhật một aggregate và cần giữ thứ tự.
- Muốn giảm số connection/statement đồng thời trong một luồng import.
- Muốn cách ly lỗi theo thứ tự và dừng khi gặp lỗi đầu tiên.

`concatMap` có thể làm throughput thấp hơn vì mỗi thao tác phải chờ thao tác trước hoàn tất. Hãy dùng nó khi thứ tự thực sự cần thiết; với các hàng độc lập, có thể dùng concurrency giới hạn.

### 3.1 concatMap không tự tạo transaction

Code sau tuần tự hóa thao tác nhưng không tự bảo đảm tất cả cùng commit/rollback:

```java
return Flux.fromIterable(customers)
    .concatMap(customerRepository::save)
    .then();
```

Nếu mỗi `save` tự thực thi ngoài một transaction bao quanh, các lần ghi trước có thể đã commit khi bản ghi tiếp theo thất bại. Nếu yêu cầu all-or-nothing, cần transaction boundary rõ ràng:

```java
Mono<Void> saveAllAtomically(List<Customer> customers) {
    return transactionalOperator.transactional(
        Flux.fromIterable(customers)
            .concatMap(customerRepository::save)
            .then());
}
```

`TransactionalOperator` phải được tạo từ `ReactiveTransactionManager` gắn với cùng `ConnectionFactory` mà repository sử dụng. Nếu repository dùng một factory khác, thao tác đó có thể không tham gia transaction dự kiến.

## 4. Dùng flatMap khi các thao tác độc lập

Nếu mỗi bản ghi độc lập, có thể cho một số thao tác chạy đồng thời:

```java
Mono<Void> saveConcurrently(Flux<Customer> customers) {
    return customers
        .flatMap(customerRepository::save, 8)
        .then();
}
```

Tham số `8` là concurrency tối đa của các publisher con do `flatMap` quản lý trong subscription này. Khi một thao tác hoàn tất, operator có thể subscribe thao tác tiếp theo. Kết quả được phát theo thời điểm publisher con hoàn tất, nên không bảo đảm thứ tự giống nguồn.

Chỉ dùng cách này khi:

- Các bản ghi không phụ thuộc thứ tự nhau.
- Không có invariant bị phá vỡ bởi cập nhật đồng thời.
- Database và connection pool chịu được mức tải được chọn.
- Cách xử lý lỗi/partial success đã được xác định.
- Không cần kết quả phát ra theo thứ tự đầu vào.

Không nên dựa vào concurrency mặc định của `flatMap` trong code persistence. Hãy khai báo rõ giá trị để người đọc thấy giới hạn được chủ động lựa chọn và có thể điều chỉnh theo cấu hình hệ thống.

## 5. flatMapSequential giữ thứ tự kết quả, không tuần tự hóa ghi

Ví dụ:

```java
Flux<Customer> saved = customers
    .flatMapSequential(customerRepository::save, 8);
```

Các thao tác `save` có thể được subscribe đồng thời tối đa 8 publisher. Nếu save thứ hai hoàn tất trước save thứ nhất, kết quả của save thứ hai có thể phải chờ trong queue để được phát sau kết quả thứ nhất.

Operator này hữu ích nếu downstream cần nhận các kết quả theo thứ tự nguồn, ví dụ tạo một file report theo đúng thứ tự đầu vào sau khi các thao tác độc lập đã hoàn tất. Tuy nhiên, không dùng `flatMapSequential` khi bản ghi sau chỉ được phép ghi sau bản ghi trước. Hai câu lệnh database vẫn có thể đang chạy đồng thời và thứ tự commit không được bảo đảm.

| Nhu cầu | Lựa chọn |
|---|---|
| Ghi A xong mới bắt đầu ghi B | `concatMap` |
| Ghi A và B đồng thời, kết quả có thể về bất kỳ thứ tự nào | `flatMap` |
| Ghi A và B đồng thời, nhưng downstream nhận kết quả theo thứ tự nguồn | `flatMapSequential` |

## 6. Thứ tự đầu vào không phải thứ tự SELECT

Database không bảo đảm thứ tự hàng nếu query không có `ORDER BY`. Việc insert A rồi B không có nghĩa `SELECT * FROM table` luôn trả A trước B.

Nếu ứng dụng cần đọc theo thứ tự nghiệp vụ, hãy lưu cột thứ tự/timestamp/sequence phù hợp và truy vấn rõ:

```sql
SELECT id, event_type, created_at
FROM account_event
WHERE aggregate_id = :aggregateId
ORDER BY aggregate_version ASC;
```

`ORDER BY created_at` có thể chưa đủ nếu nhiều bản ghi có cùng timestamp. Thêm khóa duy nhất hoặc aggregate version làm tie-breaker để tạo thứ tự xác định.

Không dùng thứ tự vật lý của hàng, thứ tự trả về tình cờ, thứ tự identity hoặc thứ tự kết quả batch làm hợp đồng nghiệp vụ nếu database không bảo đảm.

## 7. Ghi các bản ghi có quan hệ phụ thuộc

Với parent/child, ghi parent trước rồi mới ghi child:

```java
Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = Order.from(command);

    return orderRepository.save(order)
        .flatMap(savedOrder ->
            Flux.fromIterable(command.lines())
                .map(line -> line.withOrderId(savedOrder.getId()))
                .concatMap(orderLineRepository::save)
                .then(Mono.just(savedOrder)));
}
```

Parent phải được lưu thành công và ID được lấy từ entity trả về trước khi tạo child. Các child ở ví dụ được ghi tuần tự; nếu chúng độc lập sau khi parent đã tồn tại, có thể dùng concurrency giới hạn, nhưng chỉ khi transaction/driver hỗ trợ và không có ràng buộc thứ tự giữa child.

Để tất cả cùng atomic:

```java
Mono<Order> createOrderAtomically(CreateOrderCommand command) {
    return transactionalOperator.transactional(createOrder(command));
}
```

Nếu một child vi phạm constraint, transaction rollback parent và các child đã ghi trước đó. Nếu không có transaction, parent và một phần child có thể còn lại trong database.

## 8. Tuần tự hóa theo từng aggregate key

Đôi khi các bản ghi thuộc nhiều aggregate độc lập, nhưng các bản ghi của cùng một aggregate phải được ghi đúng thứ tự. Ví dụ, sự kiện cho tài khoản A phải xử lý tuần tự, trong khi sự kiện của tài khoản B có thể chạy song song.

Có thể nhóm theo key rồi dùng `concatMap` trong từng nhóm:

```java
Mono<Void> processEvents(Flux<AccountEvent> events) {
    return events
        .groupBy(AccountEvent::accountId)
        .flatMap(group ->
            group.concatMap(event -> eventRepository.save(event)),
            16)
        .then();
}
```

Trong ví dụ, các event của cùng `accountId` được xử lý tuần tự; tối đa 16 group được xử lý đồng thời qua `flatMap`. Các group khác nhau có thể chạy song song.

`groupBy` cần được dùng cẩn thận với số key rất lớn hoặc không giới hạn. Các group phải được subscribe/drain; nếu tạo nhiều group và không tiêu thụ chúng, buffer có thể tăng. Với luồng rất lớn, cân nhắc partition/shard có số lượng hữu hạn, hàng đợi theo key hoặc cơ chế serialization ở tầng database.

Nếu nhiều instance ứng dụng cùng xử lý sự kiện của một aggregate, `groupBy` chỉ tuần tự hóa trong một subscription/process. Nó không khóa các worker khác. Cần partition broker theo key, distributed lock/lease hoặc optimistic version/conditional update trong database để bảo vệ giữa nhiều instance.

## 9. Giới hạn concurrency của flatMap

`flatMap` có overload cho concurrency và prefetch:

```java
source.flatMap(this::writeOne, 8, 1);
```

- `8` là số publisher con tối đa được subscribe đồng thời trong subscription này.
- `1` là prefetch cho publisher nguồn trong ví dụ; giá trị prefetch ảnh hưởng lượng phần tử được yêu cầu/đệm, không phải giới hạn số connection toàn ứng dụng.

Chọn concurrency dựa trên đo đạc:

- Pool size và số connection dành cho các request khác.
- Database max connections và tải của các ứng dụng khác.
- Chi phí mỗi statement, lock và index.
- Kích thước payload và thời gian query.
- Số request bulk có thể chạy đồng thời.
- Timeout và backlog của pool.

Không đặt concurrency bằng pool max size một cách máy móc. Pool cần chỗ cho request nghiệp vụ, health check, job khác và thao tác quản trị. Nếu 20 request cùng chạy batch với concurrency 10, tổng số publisher con có thể lên đến khoảng 200, dù mỗi request riêng lẻ chỉ có concurrency 10.

## 10. Concurrency của một request không phải concurrency toàn hệ thống

Tham số `flatMap(..., concurrency)` chỉ giới hạn publisher con trong subscription hiện tại. Nó không tạo một semaphore toàn cục cho tất cả request của ứng dụng.

Ví dụ, một endpoint có concurrency 8 nhưng có 100 request bulk đồng thời vẫn có thể tạo tới 800 thao tác con đang hoạt động hoặc chờ tài nguyên. Connection pool có thể giới hạn số connection được cấp, nhưng phần còn lại sẽ nằm trong hàng chờ và có thể timeout.

Nếu cần giới hạn tải toàn hệ thống, có thể dùng:

- Admission control hoặc bulkhead ở service layer.
- Hàng đợi công việc có giới hạn và worker count cố định.
- Giới hạn số job bulk đồng thời.
- Rate limit theo tenant hoặc người gọi.
- Pool acquire timeout và giới hạn pending acquire.
- Cấu hình concurrency theo workload và database capacity.

`limitRate` điều chỉnh demand upstream theo từng đợt; nó không phải một semaphore toàn cục và không tự giới hạn số query đang chạy ở mọi request.

## 11. Connection pool và concurrency

R2DBC connection pool thường có giới hạn số connection tối đa và hàng đợi chờ acquire. Khi concurrency của bulk write lớn hơn số connection khả dụng, thao tác có thể chờ pool. Nếu thời gian chờ vượt acquire timeout, publisher phát lỗi.

Một số nguyên tắc:

- Đặt pool max size theo giới hạn database và tổng số replica.
- Trừ phần connection dành cho workload khác, migration, monitoring và admin.
- Theo dõi active, idle, pending acquire, acquire latency và timeout.
- Không tăng pool size chỉ để che query chậm hoặc transaction dài.
- Giới hạn số bulk job đồng thời ở cấp ứng dụng.
- Dùng timeout hợp lý cho acquire và query.

Ví dụ nếu database cho phép 200 connections và ứng dụng có 4 replica, đặt `maxSize=100` cho mỗi replica có thể vượt giới hạn khi tất cả cùng đạt đỉnh. Hãy tính tổng connection trên toàn bộ replica và các service khác, không chỉ xem cấu hình một pod.

## 12. Không mặc định concurrent statement an toàn trong cùng transaction

Reactive transaction của Spring thường gắn một connection với transaction context. Nếu bên trong transaction dùng `flatMap` để phát nhiều statement đồng thời trên cùng connection, driver có thể không hỗ trợ nhiều statement đang chạy đồng thời trên một connection; một số driver có thể báo lỗi, một số có thể serialize hoặc có behavior riêng.

Ví dụ cần thận trọng:

```java
transactionalOperator.transactional(
    Flux.fromIterable(rows)
        .flatMap(repository::save, 8)
        .then());
```

Đoạn code này có thể tạo các thao tác save đồng thời trong cùng reactive transaction. Không nên giả định nó luôn được driver hỗ trợ hoặc nhanh hơn. Với transaction all-or-nothing, lựa chọn an toàn và dễ dự đoán thường là tuần tự hóa statement bằng `concatMap`, trừ khi đã xác minh rõ driver/database hỗ trợ concurrency trên cùng transaction connection.

Nếu muốn chạy nhiều transaction độc lập đồng thời, mỗi transaction cần connection/resource riêng và phải cân nhắc pool capacity, isolation, deadlock, partial success và idempotency. Không thể có một transaction atomic duy nhất chỉ bằng cách chạy nhiều transaction song song.

## 13. Ghi batch bằng buffer

Nếu nguồn có nhiều bản ghi, có thể gom thành chunk:

```java
Mono<Void> saveInChunks(Flux<Customer> customers) {
    return customers
        .buffer(500)
        .concatMap(batch -> saveBatch(batch))
        .then();
}
```

`buffer(500)` gom tối đa 500 phần tử thành một `List` trước khi phát batch. `concatMap` xử lý batch tuần tự, do đó batch sau chỉ bắt đầu sau khi batch trước hoàn tất.

Chunking giúp:

- Giới hạn số phần tử giữ trong bộ nhớ.
- Giảm overhead điều phối so với thao tác từng phần tử nếu `saveBatch` thực sự dùng batch SQL.
- Tạo ranh giới checkpoint/commit nếu mỗi chunk có transaction riêng.
- Điều chỉnh kích thước theo giới hạn bind parameter và payload.

Nhưng `buffer(500)` tự nó không biến 500 lần `save` thành một câu SQL. Nếu `saveBatch` lại dùng `concatMap(repository::save)`, vẫn có thể tạo 500 statement; lợi ích chính khi đó là quản lý batch/checkpoint chứ không nhất thiết giảm round-trip.

## 14. Chọn kích thước batch

Batch quá nhỏ tạo nhiều round-trip và overhead. Batch quá lớn có thể:

- Vượt giới hạn bind parameter của driver/database.
- Tạo SQL rất dài.
- Tăng bộ nhớ cho input, bind values và result.
- Giữ transaction/lock lâu.
- Làm retry một batch tốn kém.
- Tăng thời gian rollback và áp lực log database.

Không có một kích thước batch phù hợp mọi hệ thống. Hãy đo theo số cột, kích thước dữ liệu, giới hạn driver, query plan, network và transaction duration. Có thể bắt đầu với một batch vừa phải rồi điều chỉnh qua benchmark/metrics.

Nếu payload có một cột JSON hoặc binary lớn, số hàng trong batch nên nhỏ hơn so với bảng chỉ có vài cột số/ngắn. Batch size nên được cấu hình và giới hạn, không nhận một giá trị tùy ý rất lớn từ request client.

## 15. Transaction cho toàn bộ batch hay từng chunk?

Hai mô hình có semantics khác nhau:

**Một transaction cho toàn bộ tập dữ liệu**

```java
Mono<Void> importAtomically(List<Customer> customers) {
    return transactionalOperator.transactional(
        Flux.fromIterable(customers)
            .concatMap(customerRepository::save)
            .then());
}
```

Nếu một bản ghi lỗi, toàn bộ transaction rollback. Cách này phù hợp khi số lượng vừa phải và yêu cầu all-or-nothing. Với import rất lớn, transaction dài có thể giữ lock, connection và transaction log lâu.

**Một transaction cho mỗi chunk**

```java
Mono<Void> importByChunks(Flux<Customer> customers) {
    return customers
        .buffer(500)
        .concatMap(batch -> transactionalOperator.transactional(
            saveBatch(batch)))
        .then();
}
```

Mỗi chunk commit độc lập. Nếu chunk thứ 4 thất bại, ba chunk trước có thể đã commit. Cần checkpoint, trạng thái import, idempotency và khả năng resume để tránh ghi trùng khi chạy lại.

Không mô tả chunked import là atomic cho toàn bộ file. Hãy làm rõ hợp đồng: toàn bộ batch hay từng chunk được xem là đơn vị thành công.

## 16. Dùng Statement.add khi driver hỗ trợ batch

R2DBC SPI có `Statement.add()` để thêm bộ binding hiện tại vào batch statement. Cách hỗ trợ và hiệu quả phụ thuộc driver. Ví dụ khái niệm với positional bind marker:

```java
Mono<Void> insertBatch(List<CustomerRow> rows) {
    return Mono.usingWhen(
        connectionFactory.create(),
        connection -> {
            Statement statement = connection.createStatement(
                "INSERT INTO customer (id, display_name) VALUES ($1, $2)");

            for (int i = 0; i < rows.size(); i++) {
                CustomerRow row = rows.get(i);
                statement.bind(0, row.id())
                    .bind(1, row.displayName());

                if (i < rows.size() - 1) {
                    statement.add();
                }
            }

            return Flux.from(statement.execute())
                .flatMap(Result::getRowsUpdated)
                .then();
        },
        Connection::close);
}
```

Đây là ví dụ dùng placeholder kiểu PostgreSQL (`$1`, `$2`) và index bind bắt đầu từ 0; marker phải đổi theo driver/database. `Statement.add()` thêm bộ binding hiện tại vào batch và cho phép thiết lập bộ binding tiếp theo theo semantics R2DBC SPI.

Trước khi dùng trong production, cần xác nhận driver hỗ trợ `add()` cho statement đó, hiểu cách driver trả `Result`/rows updated, và kiểm thử khi một phần tử trong batch vi phạm constraint. Không phải mọi driver đều thực thi batch giống nhau hoặc mang lại hiệu năng như nhau.

`DatabaseClient` là abstraction tiện cho SQL và mapping, nhưng không nên giả định mọi API `DatabaseClient` đều tự biến danh sách binding thành một batch statement. Nếu cần batch SPI, có thể dùng `Connection`/`Statement` trực tiếp trong adapter với cleanup rõ ràng và transaction manager phù hợp.

## 17. Multi-row INSERT

Một cách khác là insert nhiều bộ giá trị trong một câu lệnh nếu database hỗ trợ:

```sql
INSERT INTO customer (id, display_name, status)
VALUES
    (:id1, :name1, :status1),
    (:id2, :name2, :status2),
    (:id3, :name3, :status3);
```

Ưu điểm là giảm round-trip và parse/execute overhead so với nhiều statement riêng. Tuy nhiên:

- Cú pháp và giới hạn số value/bind marker phụ thuộc database.
- Số lượng cột nhân số hàng làm tăng số bind parameter.
- Generated values có thể cần cách trả về đặc thù.
- Thứ tự các hàng trong result của `RETURNING`/`OUTPUT` không nên được giả định nếu database không cam kết.
- Một lỗi constraint có thể làm cả statement thất bại; semantics cụ thể cần kiểm tra.

Nếu cần liên kết generated ID với input, hãy dùng khóa client-generated hoặc một correlation key ổn định được trả về cùng hàng. Không ghép kết quả theo vị trí nếu database/driver không bảo đảm thứ tự tương ứng.

## 18. Set-based UPDATE thay cho nhiều UPDATE riêng

Nếu nhiều hàng cần cùng một thay đổi theo điều kiện, một câu SQL set-based thường hiệu quả hơn nhiều lệnh update:

```sql
UPDATE customer
SET status = :newStatus,
    modified_at = :modifiedAt
WHERE tenant_id = :tenantId
  AND status = :oldStatus;
```

Database cập nhật mọi hàng phù hợp trong một statement. Dùng `rowsUpdated()` để biết số hàng bị ảnh hưởng và kiểm tra xem nó có nằm trong giới hạn nghiệp vụ mong đợi không.

Nếu mỗi hàng có giá trị mới khác nhau, có thể dùng batch statement, staging table rồi join update, hoặc một câu `CASE`/`VALUES` theo khả năng database. Chọn cách phù hợp dialect và kích thước tập dữ liệu.

Không dùng một update set-based nếu mỗi hàng cần validation/authorization khác nhau mà câu SQL không thể biểu diễn. Hiệu năng không được đánh đổi bằng cách bỏ qua quy tắc nghiệp vụ.

## 19. Thứ tự khi có khóa ngoại và constraint

Nếu bảng con tham chiếu bảng cha, cần bảo đảm parent tồn tại trước child trừ khi database hỗ trợ deferred constraint và transaction được thiết kế tương ứng.

Một trình tự thường gặp:

```java
Mono<Void> saveAggregate(Order order, List<OrderLine> lines) {
    return orderRepository.save(order)
        .flatMap(saved ->
            Flux.fromIterable(lines)
                .map(line -> line.withOrderId(saved.getId()))
                .concatMap(orderLineRepository::save)
                .then());
}
```

Nếu nhiều parent độc lập, có thể xử lý từng aggregate bằng concurrency giới hạn:

```java
Mono<Void> saveAggregates(Flux<OrderWithLines> aggregates) {
    return aggregates.flatMap(aggregate ->
        transactionalOperator.transactional(
            saveAggregate(aggregate.order(), aggregate.lines())),
        4);
}
```

Mỗi aggregate có transaction riêng trong ví dụ, và tối đa bốn aggregate được xử lý đồng thời. Điều này cho phép các aggregate độc lập chạy song song trong khi các thao tác parent/child bên trong mỗi aggregate vẫn tuần tự.

Nếu yêu cầu atomic cho toàn bộ danh sách aggregate, không dùng transaction riêng cho từng aggregate; cần một transaction bao trùm toàn bộ chuỗi, đồng thời cân nhắc thời gian giữ transaction và khả năng chạy tuần tự.

## 20. Ghi nhiều bảng theo thứ tự bằng then

Khi các bước là một chuỗi phụ thuộc rõ, `then` diễn đạt thứ tự tốt:

```java
Mono<Void> createOrderGraph(Order order,
                            List<OrderLine> lines,
                            OrderAudit audit) {
    return orderRepository.save(order)
        .flatMap(saved ->
            saveLines(saved.getId(), lines)
                .then(saveAudit(saved.getId(), audit)))
        .then();
}
```

`saveLines` phải hoàn tất trước `saveAudit`. Nếu `saveLines` phát lỗi, `saveAudit` không được thực thi. Đặt toàn bộ chain trong transaction nếu mọi bảng phải cùng commit/rollback.

Không dùng `Mono.when` cho các bước có quan hệ phụ thuộc vì `when` subscribe các publisher cùng lúc. `Mono.when` phù hợp khi các tác vụ độc lập và cần đợi tất cả hoàn tất, nhưng concurrency trên cùng transaction connection vẫn cần được xem xét.

## 21. Xử lý lỗi với concatMap và flatMap

Mặc định, khi một inner publisher phát lỗi, `concatMap` hoặc `flatMap` sẽ kết thúc chuỗi và hủy subscription liên quan theo semantics của Reactor. Tuy nhiên, các thao tác database khác có thể đã hoàn tất hoặc đang được xử lý; cancellation không thể đảo ngược một transaction đã commit.

**Tuần tự ngoài transaction:** nếu bản ghi thứ 5 lỗi, các bản ghi 1–4 có thể đã commit. Bản ghi 6 trở đi không được xử lý sau lỗi terminal.

**Đồng thời ngoài transaction:** khi một inner publisher lỗi, một số thao tác khác có thể đã commit, một số đang chạy hoặc bị cancel. Không giả định mọi thao tác khác đều được rollback.

**Trong một transaction chung:** nếu lỗi được truyền ra khỏi transaction publisher, transaction có thể rollback tất cả thao tác tham gia transaction đó. Điều này phụ thuộc các thao tác thực sự dùng cùng transaction context/connection.

Vì vậy, hãy quyết định rõ all-or-nothing hay partial success trước khi chọn operator.

## 22. Không dùng onErrorContinue để bỏ qua lỗi ghi một cách tùy tiện

`onErrorContinue` có semantics phụ thuộc operator và có thể khiến code khó biết phần tử nào thất bại. Với persistence, bỏ qua một lỗi có thể để lại dữ liệu thiếu mà pipeline vẫn báo hoàn tất.

Nếu nghiệp vụ cho phép từng bản ghi thành công/thất bại độc lập, hãy biểu diễn kết quả rõ:

```java
Flux<WriteResult> results = records.flatMap(record ->
    repository.save(record)
        .map(saved -> WriteResult.success(record.id()))
        .onErrorResume(error -> Mono.just(
            WriteResult.failure(record.id(), classify(error)))),
    8);
```

Ví dụ này biến lỗi từng record thành `WriteResult` để pipeline có thể tiếp tục. Nó phù hợp khi mỗi record có transaction/commit độc lập và partial success được chấp nhận. Không đặt `onErrorResume` bên trong transaction all-or-nothing nếu việc biến lỗi thành success sẽ khiến transaction commit dữ liệu dở dang.

Hãy lưu danh sách record lỗi, mã lỗi ổn định và cơ chế retry/resume. Không ghi dữ liệu nhạy cảm của record vào log lỗi.

## 23. Retry và idempotency khi ghi nhiều bản ghi

Retry một write có thể tạo bản ghi trùng nếu lần đầu đã commit nhưng phản hồi bị mất. Điều này đặc biệt quan trọng khi lỗi xảy ra sau khi database đã thực hiện lệnh hoặc connection bị ngắt trước khi client nhận kết quả.

Các biện pháp:

- Dùng khóa nghiệp vụ/unique constraint để ngăn duplicate.
- Dùng idempotency key cho mỗi lệnh hoặc batch/chunk.
- Thiết kế thao tác upsert/insert theo semantics database và kiểm thử concurrency.
- Lưu checkpoint sau khi chunk commit.
- Retry transaction toàn bộ khi lỗi transaction tạm thời, không retry riêng một bước phụ thuộc trạng thái cũ.
- Không retry lỗi validation, foreign key hoặc permission như thể chúng tạm thời.

Nếu retry toàn bộ transaction, dùng `Mono.defer` để mỗi lần retry tạo một publisher/transaction mới:

```java
Mono<Void> writeTransaction(List<Row> batch) {
    return Mono.defer(() ->
        transactionalOperator.transactional(
            Flux.fromIterable(batch)
                .concatMap(repository::save)
                .then()))
        .retryWhen(retryTransientTransactionFailure());
}
```

Retry phải có giới hạn, backoff và bộ lọc lỗi. Với chunk đã commit trước đó, idempotency/checkpoint phải bảo đảm chạy lại không ghi trùng.

## 24. Deadlock và thứ tự khóa

Concurrency cao có thể làm nhiều transaction cập nhật cùng tập hàng theo thứ tự khác nhau. Ví dụ transaction T1 khóa account A rồi B, trong khi T2 khóa B rồi A; hai transaction có thể chờ nhau và database phát hiện deadlock.

Để giảm deadlock:

- Lấy lock theo thứ tự khóa ổn định, ví dụ sắp xếp account ID tăng dần.
- Dùng index hỗ trợ predicate update để tránh scan/lock phạm vi rộng.
- Giữ transaction ngắn.
- Không gọi HTTP/broker hoặc chờ người dùng khi đang giữ transaction/lock.
- Giới hạn số thao tác đồng thời trên cùng key/aggregate.
- Retry có chọn lọc lỗi deadlock/serialization với backoff.

Không thể loại bỏ hoàn toàn deadlock chỉ bằng cách dùng `concatMap` trong một request; các request khác và service khác vẫn có thể cạnh tranh cùng dữ liệu. Database constraints và concurrency strategy phải bảo vệ invariant toàn hệ thống.

## 25. Chia concurrency theo key thay vì toàn cục

Một số workload cần giữ thứ tự cho từng customer/account nhưng vẫn muốn xử lý nhiều customer đồng thời. Có thể partition dữ liệu theo key ổn định rồi tuần tự hóa bên trong từng partition.

Ví dụ ý tưởng:

```java
events.groupBy(Event::accountId)
    .flatMap(group -> group.concatMap(eventRepository::save), 12);
```

Điều này giữ thứ tự trong một group ở một subscription. Nhưng nếu hai pod cùng nhận event của account đó, mỗi pod vẫn có thể xử lý một phần luồng song song. Để bảo đảm toàn hệ thống, partition message broker theo account ID hoặc dùng optimistic version/conditional update và unique constraint trong database.

Không nên dùng `groupBy` trên một key cardinality vô hạn mà không đánh giá lifecycle và buffering. Với số lượng aggregate rất lớn, fixed partition count hoặc broker partition thường dễ kiểm soát hơn.

## 26. Batch và thứ tự generated values

Khi insert nhiều hàng và database trả generated IDs, không nên giả định ID thứ nhất tương ứng phần tử đầu tiên, ID thứ hai tương ứng phần tử thứ hai, trừ khi database/driver API cam kết rõ thứ tự đó.

Các giải pháp:

- Tạo ID ở ứng dụng trước khi insert nếu domain cho phép.
- Gửi một `client_reference`/correlation key duy nhất và nhận lại cùng ID.
- Dùng `RETURNING`/`OUTPUT` với cột khóa tham chiếu rõ ràng nếu engine hỗ trợ.
- Truy vấn lại theo unique business key/correlation key.
- Không ghép kết quả chỉ bằng vị trí trong một list nếu thứ tự trả về không được bảo đảm.

Ngay cả khi sequence/identity tăng theo thời gian, giá trị ID không phải hợp đồng thứ tự nghiệp vụ. Rollback và concurrency có thể tạo khoảng trống hoặc thứ tự quan sát khác mong đợi.

## 27. Backpressure và lượng dữ liệu đang chờ

Reactive Streams điều phối demand, nhưng operator vẫn có thể buffer phần tử. `flatMap` có concurrency và prefetch; `buffer` giữ một nhóm; `collectList` giữ toàn bộ kết quả. Nếu nguồn phát nhanh hơn database ghi, queue/buffer có thể tăng và tiêu thụ bộ nhớ.

Các nguyên tắc:

- Dùng nguồn có thể phát theo demand khi có thể.
- Đặt concurrency và prefetch tường minh.
- Dùng `buffer(n)` với kích thước hữu hạn.
- Tránh `collectList()` trên nguồn lớn không giới hạn.
- Không dùng `onBackpressureBuffer()` không giới hạn để che việc database chậm.
- Theo dõi số phần tử đang chờ, queue depth và thời gian xử lý.

Backpressure giúp truyền tín hiệu demand trong pipeline; nó không thay thế giới hạn số job bulk đồng thời hoặc giới hạn tài nguyên toàn hệ thống.

## 28. Tách CPU work khỏi database write

Nếu mỗi record cần chuyển đổi/validate tốn CPU, đừng mặc định chạy tất cả công việc trên cùng một luồng hoặc dùng `parallel()` rồi gọi database tùy tiện. R2DBC driver có scheduler/connection behavior riêng; không nên đưa JDBC blocking vào reactive chain.

Có thể thực hiện validation thuần trước khi mở transaction hoặc dùng scheduler phù hợp cho CPU work, nhưng phải giữ thứ tự và context cần thiết. Khi chuyển scheduler, Reactor Context thường được truyền qua operator Reactor, nhưng các cơ chế tự viết dựa vào `ThreadLocal` có thể không hoạt động như mong muốn.

Không dùng `parallel()` như cách tự động tăng throughput database. Parallel rails không làm database có thêm connection hoặc CPU; chúng chỉ thay đổi cách xử lý trong pipeline. Với I/O, `flatMap` có concurrency giới hạn thường biểu đạt ý định rõ hơn.

## 29. Cân nhắc saveAll và cách triển khai thực tế

Repository có thể cung cấp `saveAll(Iterable)` hoặc `saveAll(Publisher)`. Đây là API tiện để gửi nhiều entity, nhưng không nên mặc định rằng một lời gọi `saveAll` luôn trở thành một SQL batch duy nhất hoặc có thứ tự thực thi giống nhau giữa mọi phiên bản Spring Data/driver.

Hãy xác định:

- Implementation đang dùng có gọi `concatMap`, `flatMap` hay cơ chế khác không?
- Driver có hỗ trợ batch statement không?
- Generated values được trả về thế nào?
- Transaction boundary nằm ở đâu?
- Nếu một entity lỗi, các entity trước đó đã commit chưa?
- Thứ tự kết quả có được bảo đảm không?

Nếu yêu cầu cụ thể về thứ tự hoặc batch behavior, hãy compose rõ trong service/adapter hoặc dùng API driver được kiểm chứng. Không dựa vào tên `saveAll` để suy ra semantics hiệu năng.

## 30. Một mẫu import theo chunk có giới hạn concurrency

Ví dụ import nhiều customer độc lập, mỗi chunk được xử lý trong một transaction riêng, và tối đa ba chunk chạy đồng thời:

```java
Mono<Void> importCustomers(Flux<Customer> source) {
    return source
        .buffer(250)
        .flatMap(batch ->
            transactionalOperator.transactional(
                saveBatchSequentially(batch)),
            3)
        .then();
}

Mono<Void> saveBatchSequentially(List<Customer> batch) {
    return Flux.fromIterable(batch)
        .concatMap(customerRepository::save)
        .then();
}
```

Trong ví dụ:

- Mỗi chunk có tối đa 250 phần tử.
- Các phần tử trong cùng chunk được ghi tuần tự.
- Mỗi chunk có transaction riêng.
- Tối đa ba transaction chunk được subscribe đồng thời.
- Một chunk lỗi có thể rollback chunk đó; chunk khác có thể đã commit hoặc vẫn đang chạy.

Mẫu này chỉ phù hợp khi các chunk độc lập và partial success giữa các chunk được chấp nhận. Nếu tất cả 10.000 bản ghi phải cùng thành công hoặc cùng rollback, cần một transaction chung và phải cân nhắc chi phí transaction dài; không dùng transaction riêng từng chunk.

Trong một reactive transaction, driver có thể giới hạn khả năng concurrent statement trên cùng connection. Ở ví dụ, các thao tác bên trong từng chunk được tuần tự hóa. Các chunk có transaction/connection độc lập mới được chạy đồng thời, tùy transaction manager, pool và driver.

## 31. Mẫu ghi có thứ tự và dừng ngay khi lỗi

Nếu một batch cần thứ tự tuyệt đối và all-or-nothing:

```java
Mono<Void> writeOrderedAtomically(List<ImportRow> rows) {
    return transactionalOperator.transactional(
        Flux.fromIterable(rows)
            .concatMap(row -> validate(row)
                .then(repository.save(mapToEntity(row))))
            .then());
}
```

`concatMap` đảm bảo row sau chỉ được xử lý sau khi row trước hoàn tất. Nếu validation hoặc save phát lỗi, chuỗi kết thúc và transaction rollback. Hãy giữ transaction ngắn và giới hạn kích thước import để tránh giữ connection/lock quá lâu.

Nếu validation có thể thực hiện hoàn toàn trước transaction, có thể validate trước để tránh giữ transaction trong lúc kiểm tra thuần túy. Tuy nhiên, điều kiện phụ thuộc database vẫn phải được kiểm tra lại trong transaction.

## 32. Mẫu ghi độc lập với concurrency có thể cấu hình

Concurrency có thể lấy từ cấu hình ứng dụng, nhưng phải có min/max validation:

```yaml
app:
  bulk-write:
    concurrency: 6
    batch-size: 250
```

```java
@ConfigurationProperties(prefix = "app.bulk-write")
public record BulkWriteProperties(int concurrency, int batchSize) {
    public BulkWriteProperties {
        if (concurrency < 1 || concurrency > 32) {
            throw new IllegalArgumentException("Invalid bulk concurrency");
        }
        if (batchSize < 1 || batchSize > 2000) {
            throw new IllegalArgumentException("Invalid batch size");
        }
    }
}
```

Giới hạn `32` và `2000` chỉ là ví dụ minh họa, không phải giá trị tối ưu chung. Cần đặt theo pool, database, workload và benchmark. Không cho phép client gửi concurrency tùy ý vì có thể trở thành cách làm cạn tài nguyên.

Sử dụng cấu hình:

```java
Mono<Void> saveAll(Flux<Customer> source) {
    return source
        .flatMap(customerRepository::save,
            properties.concurrency())
        .then();
}
```

Nếu cần giới hạn toàn hệ thống, cấu hình per-subscription vẫn chưa đủ; cần bulkhead/queue ở service hoặc job runner.

## 33. Đo throughput và chọn mức đồng thời

Đừng chọn concurrency chỉ bằng cảm giác. Có thể chạy thử với các mức nhỏ tăng dần, ví dụ 1, 2, 4, 8, 16, trong cùng điều kiện dữ liệu.

Theo dõi:

- Tổng thời gian ghi batch và records/second.
- p50/p95/p99 thời gian mỗi thao tác.
- Connection pool active/idle/pending và acquire timeout.
- Database CPU, I/O, lock waits và deadlock count.
- Số lỗi constraint/timeout/serialization.
- Heap, GC và số phần tử được buffer.
- Thời gian transaction và số hàng bị ảnh hưởng.

Nếu tăng concurrency mà throughput không tăng nhưng lock wait, pending acquire hoặc timeout tăng, đã vượt điểm có lợi. Nếu database còn dư capacity nhưng pool quá nhỏ, có thể cần điều chỉnh pool; nếu database bão hòa, tăng pool/concurrency sẽ làm tình hình xấu hơn.

## 34. Quan sát thứ tự và lỗi trong production

Khi bulk write có vấn đề, log/metric nên giúp trả lời:

- Batch/import ID nào đang chạy?
- Chunk số mấy, kích thước bao nhiêu?
- Concurrency cấu hình hiện tại là bao nhiêu?
- Bao nhiêu record thành công/thất bại?
- Thời gian chờ connection và thời gian query là bao nhiêu?
- Có deadlock, lock timeout hoặc serialization failure không?
- Checkpoint cuối cùng đã commit là gì?
- Có retry không và retry bao nhiêu lần?

Không log toàn bộ record hoặc bind values nếu có dữ liệu nhạy cảm. Dùng batch ID, record ID an toàn, operation name và error category đã phân loại.

## 35. Kiểm thử thứ tự bằng StepVerifier

Với publisher giả, có thể chứng minh `concatMap` phát kết quả theo thứ tự:

```java
StepVerifier.create(
        Flux.just(1, 2, 3)
            .concatMap(value -> Mono.delay(Duration.ofMillis(10))
                .thenReturn(value)))
    .expectNext(1, 2, 3)
    .verifyComplete();
```

Với `flatMap`, không nên viết test giả định kết quả luôn theo thứ tự nguồn khi inner publisher có thời gian hoàn tất khác nhau. Nếu cần kiểm tra concurrency, dùng publisher điều khiển được thời điểm hoàn tất, ví dụ `TestPublisher`, và xác nhận số inner subscription tối đa theo yêu cầu.

Test publisher chỉ kiểm tra semantics Reactor. Nó không chứng minh database commit theo cùng thứ tự; điều đó cần integration test với database/driver và quan sát trạng thái cuối.

## 36. Kiểm thử concurrency có giới hạn

Có thể dùng counter trong test để xác nhận không quá N publisher con hoạt động cùng lúc:

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxActive = new AtomicInteger();

Flux<Integer> work = Flux.range(1, 100)
    .flatMap(value -> Mono.defer(() -> {
        int current = active.incrementAndGet();
        maxActive.accumulateAndGet(current, Math::max);

        return Mono.delay(Duration.ofMillis(5))
            .thenReturn(value)
            .doFinally(signal -> active.decrementAndGet());
    }), 4);

StepVerifier.create(work)
    .expectNextCount(100)
    .verifyComplete();

assertThat(maxActive.get()).isLessThanOrEqualTo(4);
```

Đây là test Reactor pipeline, không gọi database. Nó xác nhận giới hạn concurrency trong một subscription. Cần integration test riêng để đo connection pool và database load.

## 37. Kiểm thử atomicity và partial success

Với all-or-nothing transaction:

1. Chuẩn bị nhiều hàng hợp lệ và một hàng cố ý vi phạm constraint.
2. Chạy batch trong một transaction.
3. Xác nhận publisher phát lỗi.
4. Query lại database bằng transaction độc lập.
5. Xác nhận không có hàng nào trong batch đã commit.

Với chunk transaction:

1. Chuẩn bị nhiều chunk và tạo lỗi trong một chunk xác định.
2. Chạy import theo thứ tự/chính sách concurrency đã chọn.
3. Xác định chunk nào đã commit và chunk nào rollback.
4. Xác nhận checkpoint phản ánh đúng các chunk commit.
5. Chạy lại job và bảo đảm không tạo duplicate.

Không dùng mock repository để kết luận rollback database thật. Cần integration test trên đúng R2DBC driver và database engine.

## 38. Kiểm thử thứ tự phụ thuộc parent/child

Tạo test trong đó child tham chiếu ID parent được sinh khi insert. Xác nhận:

- Parent được ghi trước child.
- Child nhận đúng parent ID từ entity trả về.
- Nếu parent insert lỗi, không có child nào được ghi.
- Nếu một child lỗi trong transaction chung, parent và các child trước đó rollback.
- Nếu mỗi child/aggregate có transaction riêng, kết quả partial success đúng hợp đồng.

Không chỉ kiểm tra danh sách kết quả trả về có thứ tự. Query lại database bằng `ORDER BY`/foreign key để xác nhận trạng thái thực.

## 39. Các anti-pattern cần tránh

| Anti-pattern | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng `flatMap` mặc định cho mọi bulk write | Concurrency và thứ tự không rõ | Chọn operator và concurrency tường minh. |
| Dùng `flatMapSequential` để bắt buộc thứ tự ghi | Side effect vẫn có thể chạy đồng thời | Dùng `concatMap`. |
| Tăng concurrency đến rất lớn | Pool cạn, lock contention và memory tăng | Đo và giới hạn theo capacity. |
| Cho rằng concurrency 8 là giới hạn toàn ứng dụng | Mỗi request có subscription riêng | Dùng bulkhead/queue toàn cục nếu cần. |
| Concurrent statement trong một transaction mà chưa kiểm tra driver | Driver có thể không hỗ trợ cùng connection | Tuần tự hóa hoặc xác minh support bằng integration test. |
| Dùng `buffer` rồi nghĩ đã batch SQL | Buffer chỉ gom phần tử | Dùng multi-row SQL/`Statement.add` nếu driver hỗ trợ. |
| Một transaction khổng lồ cho import lớn | Lock, log và connection giữ lâu | Chunk transaction và checkpoint nếu partial commit được phép. |
| Chunk transaction nhưng tuyên bố all-or-nothing | Chunk trước có thể đã commit | Nêu rõ partial success hoặc dùng transaction chung. |
| Retry từng statement không idempotent | Có thể ghi trùng | Retry toàn transaction và dùng idempotency. |
| Dựa vào thứ tự SELECT tự nhiên | Database không bảo đảm | Dùng `ORDER BY` xác định. |
| Ghép generated IDs theo vị trí batch | Result order có thể không được bảo đảm | Dùng correlation key ổn định. |
| `onErrorContinue` để che lỗi ghi | Dữ liệu thiếu nhưng job có thể báo thành công | Trả kết quả từng record rõ ràng. |
| `collectList()` trên nguồn lớn | Tốn heap | Dùng buffer có giới hạn/streaming. |

## 40. Quy trình chọn operator và mức đồng thời

Trước khi viết bulk persistence, hãy trả lời theo thứ tự:

1. Các bản ghi có độc lập hay có quan hệ phụ thuộc parent/child/aggregate?
2. Thứ tự nào là bắt buộc: bắt đầu, hoàn tất, commit hay chỉ thứ tự phát kết quả?
3. Toàn bộ batch cần atomic hay từng record/chunk được phép commit độc lập?
4. Có thể dùng set-based SQL, multi-row insert hoặc batch statement thay cho nhiều round-trip không?
5. Nếu cần tuần tự, dùng `concatMap`/`then`; nếu độc lập, dùng `flatMap` với concurrency rõ ràng.
6. Nếu cần output theo thứ tự nhưng thao tác độc lập, cân nhắc `flatMapSequential` và hiểu rằng nó không tuần tự hóa side effect.
7. Nếu cần thứ tự theo key, tuần tự hóa trong từng aggregate và bảo vệ giữa nhiều instance bằng database/broker.
8. Chọn batch size, concurrency và prefetch theo pool/database capacity.
9. Xác định lỗi, retry, idempotency, checkpoint và partial success.
10. Kiểm thử thứ tự, concurrency, rollback và generated values trên driver/database thực tế.

## 41. Kết luận triển khai

Trong Spring Data R2DBC, `concatMap` là lựa chọn rõ ràng khi thao tác ghi sau phải đợi thao tác trước hoàn tất; `flatMap` phù hợp với các ghi độc lập khi có giới hạn concurrency; `flatMapSequential` chỉ giữ thứ tự phát kết quả trong khi các side effect vẫn có thể chạy đồng thời. `buffer` giúp chia dữ liệu thành chunk nhưng không tự tạo SQL batch. Muốn batch thực sự, hãy dùng multi-row SQL hoặc R2DBC `Statement.add()` khi driver hỗ trợ.

Concurrency cần được kiểm soát ở cả cấp subscription và toàn hệ thống. Trong một reactive transaction, các statement thường chia sẻ connection context; không giả định nhiều statement có thể chạy song song an toàn trên cùng connection. Nếu cần atomicity, compose các thao tác trong một transaction đúng `ConnectionFactory`, thường tuần tự hóa các statement phụ thuộc. Nếu chia transaction theo chunk, phải chấp nhận partial commit và có checkpoint/idempotency để resume. Cuối cùng, database không bảo đảm thứ tự hàng khi đọc nếu không có `ORDER BY`; hãy lưu khóa thứ tự nghiệp vụ và truy vấn theo thứ tự xác định. Kết hợp operator phù hợp, batch có giới hạn, transaction rõ ràng và kiểm thử concurrency trên database thực tế sẽ giúp bulk write vừa có throughput tốt vừa giữ đúng bất biến dữ liệu.
