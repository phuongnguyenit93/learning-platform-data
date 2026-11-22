# Dùng map, flatMap và concatMap quanh thao tác truy cập dữ liệu

Trong Spring Data Relational R2DBC, repository và DatabaseClient trả về các reactive publisher như Mono hoặc Flux. Khi ghép những publisher này với Reactor, ba operator thường gặp nhất là map, flatMap và concatMap.

Chúng đều biến đổi dữ liệu trong một reactive pipeline, nhưng cách xử lý publisher được trả về khác nhau:

- **map** biến đổi một giá trị thành một giá trị khác bằng hàm đồng bộ.
- **flatMap** biến đổi một giá trị thành một Publisher rồi subscribe và làm phẳng kết quả của Publisher đó; các inner Publisher có thể chạy đồng thời.
- **concatMap** cũng biến đổi một giá trị thành Publisher, nhưng subscribe và chờ từng inner Publisher hoàn tất theo thứ tự nguồn trước khi xử lý phần tử tiếp theo.

Khi truy cập database, chọn sai operator có thể tạo ra kiểu lồng Mono<Mono<T>>, vô tình gọi nhiều truy vấn đồng thời, làm sai thứ tự cập nhật hoặc khiến code blocking trong reactive pipeline. Hiểu đúng semantics giúp ghép các bước đọc/ghi rõ ràng và kiểm soát được thứ tự thực thi.

## 1. Reactive repository trả về Publisher

Một repository R2DBC thường trả Mono hoặc Flux:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
~~~

- Mono<T> phát tối đa một giá trị T, hoặc hoàn tất rỗng, hoặc phát lỗi.
- Flux<T> phát từ 0 đến nhiều giá trị T, hoặc phát lỗi.

Các publisher này mô tả công việc truy cập dữ liệu. Thông thường câu SQL chỉ được thực thi khi publisher được subscribe. Vì vậy, việc gọi findById() để tạo publisher không đồng nghĩa database đã trả kết quả ngay tại dòng code đó.

Ví dụ:

~~~java
Mono<Customer> customerPublisher =
    customerRepository.findById(42L);
~~~

Biến customerPublisher giữ một publisher. Khi publisher được subscribe bởi tầng web, service hoặc một operator khác, công việc R2DBC mới được thực thi.

Trong reactive code, nên compose publisher và trả nó về cho caller. Không tự gọi subscribe() hoặc block() trong service chỉ để lấy dữ liệu đồng bộ.

## 2. map: biến đổi đồng bộ một giá trị

map nhận một giá trị đã được publisher phát ra và biến đổi nó thành một giá trị khác. Hàm mapper phải trả về dữ liệu trực tiếp, không phải một Publisher mới.

Ví dụ chuyển Customer thành DTO:

~~~java
public Mono<CustomerSummary> findSummary(Long id) {
    return customerRepository.findById(id)
        .map(customer -> new CustomerSummary(
            customer.getId(),
            customer.getName(),
            customer.getStatus()
        ));
}
~~~

Luồng dữ liệu:

~~~text
Mono<Customer>
      |
      v
     map
      |
      v
Mono<CustomerSummary>
~~~

map phù hợp với những thao tác đồng bộ, nhanh và không cần chờ một Publisher khác:

- Chuyển entity thành DTO.
- Lấy một thuộc tính.
- Chuẩn hóa hoặc định dạng dữ liệu.
- Tính một giá trị từ object đã có trong bộ nhớ.
- Ánh xạ một row database thành record Java.

### map khi ánh xạ row của DatabaseClient

Đây là một trường hợp dùng map rất phổ biến:

~~~java
Flux<CustomerSummary> customers =
    databaseClient.sql(
            "SELECT id, name, status FROM customer WHERE active = :active"
        )
        .bind("active", true)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("status", String.class)
        ))
        .all();
~~~

DatabaseClient đọc từng row từ kết quả SQL. Hàm map chuyển row thành CustomerSummary ngay trong pipeline. Không có truy vấn database thứ hai bên trong mapper, nên map là lựa chọn đúng.

### map không subscribe Publisher được trả về

Đây là lỗi thường gặp:

~~~java
Mono<Mono<Customer>> result =
    customerRepository.findById(42L)
        .map(customer ->
            customerRepository.findByEmail(customer.getEmail())
        );
~~~

Hàm map trả về Mono<Customer>. Vì map chỉ xem Publisher đó như một giá trị Java, kết quả trở thành Mono<Mono<Customer>>. Publisher bên trong chưa được làm phẳng và không tự được subscribe.

Nếu muốn truy vấn thứ hai và nhận trực tiếp Customer cuối cùng, hãy dùng flatMap:

~~~java
Mono<Customer> result =
    customerRepository.findById(42L)
        .flatMap(customer ->
            customerRepository.findByEmail(customer.getEmail())
        );
~~~

### Không đặt thao tác blocking trong map

Không nên gọi JDBC, block(), đọc file blocking hoặc gọi HTTP đồng bộ bên trong map:

~~~java
return customerRepository.findById(id)
    .map(customer -> blockingClient.loadProfile(customer.getId()));
~~~

Hàm map chạy trên thread đang phát tín hiệu onNext. Nếu nó thực hiện I/O blocking, thread có thể bị giữ trong lúc chờ. Với một client reactive, hãy dùng flatMap để nối Publisher. Với thư viện blocking bắt buộc phải dùng, hãy cô lập phần blocking trên scheduler phù hợp và không giữ transaction/connection R2DBC trong lúc chờ lâu.

## 3. flatMap: nối một thao tác bất đồng bộ khác

flatMap dùng khi bước tiếp theo trả về một Publisher, ví dụ sau khi đọc Customer cần truy vấn thêm Order.

~~~java
public Mono<CustomerDetail> findDetail(Long id) {
    return customerRepository.findById(id)
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerDetail(customer, orders)
                )
        );
}
~~~

Luồng:

~~~text
findById(id)
     |
     v
 Mono<Customer>
     |
     v
  flatMap
     |
     +----> findByCustomerId(customerId)
                    |
                    v
               Flux<Order>
                    |
                collectList()
                    |
                    v
               Mono<List<Order>>
                    |
                 map(...)
                    |
                    v
            Mono<CustomerDetail>
~~~

flatMap làm ba việc:

1. Nhận Customer từ publisher nguồn.
2. Gọi hàm mapper để tạo Publisher truy vấn Order.
3. Subscribe vào Publisher bên trong và làm phẳng kết quả vào pipeline ngoài.

Vì vậy, kiểu kết quả không bị lồng thành Mono<Mono<CustomerDetail>>.

### flatMap trên Mono

Với một Mono nguồn, tối đa chỉ có một giá trị để chuyển tiếp. Do đó flatMap thường dùng để nối một bước bất đồng bộ phụ thuộc vào kết quả trước:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        addressRepository.findById(customer.getAddressId())
            .map(address ->
                new CustomerDetail(customer, address)
            )
    );
~~~

Truy vấn địa chỉ chỉ có thể được tạo sau khi đã có Customer và address ID. Đây là luồng phụ thuộc dữ liệu nên flatMap phù hợp.

### flatMap trên Flux

Với Flux có nhiều phần tử, flatMap có thể subscribe nhiều inner Publisher đồng thời:

~~~java
Flux<CustomerDetail> details =
    customerRepository.findByStatus("ACTIVE")
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerDetail(customer, orders)
                )
        );
~~~

Nếu Flux phát ra nhiều Customer, nhiều truy vấn Order có thể được thực thi đồng thời. Kết quả có thể phát ra theo thứ tự hoàn tất của inner Publisher, không nhất thiết theo thứ tự Customer ban đầu.

Điều này hữu ích khi các tác vụ độc lập và có thể chạy đồng thời. Nhưng nếu các truy vấn dùng chung connection trong một reactive transaction hoặc cần giữ thứ tự ghi, phải cân nhắc kỹ.

### Giới hạn concurrency của flatMap

Có thể giới hạn số inner Publisher hoạt động đồng thời:

~~~java
return customerRepository.findByStatus("ACTIVE")
    .flatMap(
        customer -> orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders)),
        8
    );
~~~

Tham số 8 giới hạn số inner Publisher được subscribe đồng thời tại một thời điểm. Nó giúp kiểm soát tải khi có nhiều phần tử.

Giới hạn này không biến nhiều truy vấn thành một truy vấn batch và không tự tạo connection riêng cho từng nhánh nếu các nhánh cùng tham gia một transaction context. Nếu mục tiêu là giảm N+1, cần dùng JOIN hoặc batch query thay vì chỉ chỉnh concurrency.

## 4. concatMap: xử lý từng Publisher theo thứ tự

concatMap cũng nhận một hàm trả về Publisher, nhưng nó chỉ subscribe inner Publisher tiếp theo sau khi Publisher hiện tại hoàn tất. Điều này giữ thứ tự xử lý theo thứ tự phần tử nguồn.

Ví dụ cập nhật từng khách hàng:

~~~java
public Mono<Void> deactivateCustomers(List<Long> ids) {
    return Flux.fromIterable(ids)
        .concatMap(id ->
            customerRepository.findById(id)
                .flatMap(customer -> {
                    customer.deactivate();
                    return customerRepository.save(customer);
                })
        )
        .then();
}
~~~

Với ids = [10, 20, 30], concatMap xử lý:

1. Đọc và cập nhật customer 10; chờ hoàn tất.
2. Đọc và cập nhật customer 20; chờ hoàn tất.
3. Đọc và cập nhật customer 30; chờ hoàn tất.

Không có inner Publisher tiếp theo được subscribe trước khi bước hiện tại hoàn tất.

### concatMap phù hợp khi nào?

- Các thao tác ghi cần chạy theo thứ tự.
- Mỗi thao tác phụ thuộc kết quả hoặc side effect của thao tác trước.
- Các câu SQL cùng tham gia một transaction và cần tránh phát đồng thời trên một connection.
- Cần giữ thứ tự đầu vào trong quá trình xử lý.
- Cần giới hạn số inner Publisher đang hoạt động xuống một.

Đổi lại, concatMap không tận dụng concurrency giữa các phần tử. Nếu từng tác vụ độc lập và có thể chạy song song trên connection riêng, concatMap có thể làm tổng thời gian lâu hơn cần thiết.

## 5. So sánh map, flatMap và concatMap

| Operator | Hàm mapper trả về | Xử lý Publisher lồng | Thứ tự kết quả | Inner Publisher đồng thời |
|---|---|---|---|---|
| map | Giá trị T | Không làm phẳng | Giữ thứ tự nguồn | Không áp dụng |
| flatMap | Publisher<R> | Subscribe và làm phẳng | Không bảo đảm thứ tự nguồn | Có thể có |
| concatMap | Publisher<R> | Subscribe và làm phẳng | Giữ thứ tự nguồn | Không; xử lý lần lượt |

Ví dụ ngắn:

~~~java
// Biến đổi đồng bộ: Customer -> CustomerSummary
Mono<CustomerSummary> a =
    customerRepository.findById(id)
        .map(CustomerSummary::from);

// Nối truy vấn bất đồng bộ: Customer -> Mono<Address>
Mono<Address> b =
    customerRepository.findById(id)
        .flatMap(customer ->
            addressRepository.findById(customer.getAddressId())
        );

// Xử lý lần lượt từng customer ID
Flux<Customer> c =
    Flux.fromIterable(ids)
        .concatMap(customerRepository::findById);
~~~

Một cách nhớ:

- map: có dữ liệu rồi, chuyển nó thành dữ liệu khác.
- flatMap: có dữ liệu rồi, từ nó khởi chạy một công việc reactive khác và làm phẳng kết quả.
- concatMap: làm như flatMap nhưng chờ từng công việc hoàn tất theo thứ tự.

## 6. flatMapSequential khác concatMap thế nào?

Reactor còn có flatMapSequential. Operator này có thể subscribe inner Publisher đồng thời như flatMap, nhưng giữ thứ tự phát kết quả theo thứ tự phần tử nguồn.

| Operator | Inner Publisher | Thứ tự phát kết quả |
|---|---|---|
| flatMap | Có thể chạy đồng thời | Theo thứ tự hoàn tất |
| flatMapSequential | Có thể chạy đồng thời | Theo thứ tự nguồn |
| concatMap | Tuần tự | Theo thứ tự nguồn |

Ví dụ:

~~~java
return Flux.fromIterable(ids)
    .flatMapSequential(
        id -> customerRepository.findById(id)
    );
~~~

Nếu truy vấn ID thứ hai hoàn tất trước ID thứ nhất, flatMapSequential vẫn giữ kết quả theo thứ tự ID đầu vào. Tuy nhiên, các inner Publisher vẫn có thể thực thi đồng thời.

Vì vậy, flatMapSequential không phải lựa chọn thay thế concatMap khi yêu cầu là không phát các truy vấn đồng thời trên cùng transaction-bound connection.

## 7. Kết hợp các operator quanh một truy vấn đọc

Một use case đọc chi tiết có thể gồm các bước:

1. Tìm Customer theo ID.
2. Nếu không có, phát lỗi not-found.
3. Tìm Address theo address ID.
4. Chuyển hai object thành DTO.

~~~java
public Mono<CustomerDetail> findDetail(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer ->
            addressRepository.findById(customer.getAddressId())
                .map(address ->
                    new CustomerDetail(
                        customer.getId(),
                        customer.getName(),
                        address.getCity()
                    )
                )
        );
}
~~~

Ở đây:

- switchIfEmpty xử lý trường hợp không có Customer.
- flatMap nối truy vấn Address.
- map chuyển Address cùng Customer thành CustomerDetail.

Không cần flatMap cho bước cuối vì tạo DTO là phép biến đổi đồng bộ, không phát sinh một Publisher khác.

### map sau khi truy vấn hoàn tất

Nếu truy vấn đã trả đủ dữ liệu cần thiết, chỉ cần map:

~~~java
return customerRepository.findById(id)
    .map(CustomerDetail::from);
~~~

Không cần tạo một flatMap chỉ để bọc Mono.just(...):

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        Mono.just(CustomerDetail.from(customer))
    );
~~~

Hai cách có thể cho kết quả tương đương, nhưng cách dùng map thể hiện đúng ý định hơn và ít tạo thêm Publisher.

## 8. Kết hợp các operator quanh truy vấn ghi

Giả sử cần:

1. Tìm Customer.
2. Kiểm tra trạng thái.
3. Cập nhật Customer.
4. Ghi audit record.

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            if ("CLOSED".equals(customer.getStatus())) {
                return Mono.error(
                    new IllegalStateException(
                        "Closed customer cannot be changed"
                    )
                );
            }

            customer.changeStatus(newStatus);
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .thenReturn(saved)
        );
}
~~~

flatMap cần thiết ở bước save vì repository trả về Mono<Customer>. Bước ghi audit cũng là một thao tác reactive nên tiếp tục dùng flatMap. thenReturn(saved) giữ lại Customer đã lưu sau khi audit hoàn tất.

Các publisher được nối theo quan hệ phụ thuộc: không thể ghi audit với trạng thái mới trước khi biết kết quả lưu Customer. Toàn bộ pipeline được trả về để @Transactional quản lý.

Không viết:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    customerRepository.findById(id)
        .subscribe(customer -> {
            customer.changeStatus(newStatus);
            customerRepository.save(customer).subscribe();
        });

    return Mono.empty();
}
~~~

Đoạn code này tạo các subscription độc lập, không nối lỗi và completion vào publisher được Spring quản lý. Phương thức có thể hoàn tất trước khi thao tác database kết thúc, và các thao tác có thể không tham gia cùng transaction.

## 9. Xử lý trường hợp Mono.empty()

Repository findById() trả Mono.empty() khi không tìm thấy entity. Khi publisher nguồn hoàn tất rỗng:

- map không gọi mapper.
- flatMap không gọi mapper.
- concatMap không gọi mapper cho phần tử không tồn tại.

Ví dụ:

~~~java
Mono<CustomerSummary> result =
    customerRepository.findById(id)
        .map(CustomerSummary::from);
~~~

Nếu không tìm thấy customer, result cũng hoàn tất rỗng. Nếu API cần trả not-found, dùng switchIfEmpty:

~~~java
Mono<CustomerSummary> result =
    customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .map(CustomerSummary::from);
~~~

Với Flux, nếu nguồn không phát phần tử nào, mapper trong flatMap hoặc concatMap không được gọi và kết quả cũng hoàn tất rỗng.

Không nhầm Mono.empty() với giá trị Java null. Reactive Streams không cho phép publisher phát null như một phần tử. Nếu một mapper trả null, Reactor phát lỗi thay vì phát một giá trị null.

## 10. Xử lý lỗi trong map, flatMap và concatMap

Nếu hàm mapper ném RuntimeException, hoặc inner Publisher phát onError, lỗi đi tiếp trong reactive pipeline.

~~~java
return customerRepository.findById(id)
    .map(customer -> {
        if (customer.getName() == null) {
            throw new IllegalStateException("Customer name is missing");
        }
        return CustomerSummary.from(customer);
    });
~~~

Lỗi từ map trở thành tín hiệu onError. Với flatMap:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders))
    );
~~~

Nếu truy vấn order lỗi, lỗi được truyền ra publisher ngoài.

Với concatMap, nếu một inner Publisher lỗi, các phần tử sau thường không tiếp tục được xử lý; lỗi kết thúc pipeline. Trong một transaction, lỗi phù hợp rollback policy có thể làm transaction rollback.

### Đổi lỗi nhưng vẫn giữ onError

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
    )
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerReadException(error)
    );
~~~

onErrorMap chuyển loại lỗi nhưng vẫn phát onError. Caller và transaction boundary vẫn nhận được tín hiệu lỗi.

### Cẩn thận khi recover lỗi

~~~java
return customerRepository.findById(id)
    .flatMap(customer -> orderRepository.findByCustomerId(customer.getId())
        .collectList()
    )
    .onErrorResume(error -> Mono.just(List.of()));
~~~

Đoạn code biến lỗi database thành danh sách rỗng. Caller sẽ không phân biệt được khách hàng không có order với truy vấn order thất bại. Nếu nằm trong transaction, việc recover thành giá trị bình thường còn có thể khiến transaction commit.

Chỉ dùng fallback khi nghiệp vụ thật sự quy định lỗi đó có thể được xem như một kết quả thay thế. Nếu chỉ cần ghi log, dùng doOnError và để lỗi tiếp tục đi ra.

## 11. Backpressure và concurrency

Với Flux có nhiều phần tử, flatMap có thể tạo nhiều inner Publisher. Điều này có thể làm nhiều truy vấn database cùng hoạt động và tăng tải lên connection pool hoặc database.

Ví dụ:

~~~java
return customerRepository.findAll()
    .flatMap(
        customer -> orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders)),
        16
    );
~~~

Concurrency 16 giới hạn số inner Publisher hoạt động cùng lúc. Giá trị nên được chọn dựa trên:

- Kích thước connection pool.
- Khả năng xử lý đồng thời của database.
- Thời gian thực thi truy vấn.
- Số request đồng thời trong hệ thống.
- Tài nguyên bộ nhớ và kích thước kết quả.

Không nên tăng concurrency chỉ vì muốn request nhanh hơn. Nếu connection pool có ít connection, nhiều truy vấn có thể phải chờ. Nếu các nhánh nằm trong cùng một transaction, chúng còn có thể cùng dùng connection đã bind thay vì lấy connection riêng.

concatMap xử lý một inner Publisher tại một thời điểm, nên giới hạn concurrency của nhánh xử lý xuống một. Nó giúp kiểm soát thứ tự nhưng có thể làm tăng thời gian hoàn tất khi từng truy vấn chậm.

## 12. map, flatMap và concatMap trong cùng một luồng

Ví dụ lấy các customer ACTIVE, truy vấn order theo từng customer lần lượt và tạo DTO:

~~~java
public Flux<CustomerDetail> findActiveCustomerDetails() {
    return customerRepository.findByStatus("ACTIVE")
        .concatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerDetail(
                        customer.getId(),
                        customer.getName(),
                        orders
                    )
                )
        );
}
~~~

Trong ví dụ:

- Repository đầu tiên trả Flux<Customer>.
- concatMap gọi truy vấn order cho từng customer và chờ hoàn tất theo thứ tự.
- collectList gom các order của một customer.
- map tạo CustomerDetail từ customer và danh sách order.

Nếu mỗi customer có một truy vấn order riêng, đây vẫn có thể là mẫu N+1. concatMap chỉ làm các truy vấn con tuần tự; nó không giảm số lượng truy vấn. Nếu cần giảm N+1, hãy cân nhắc JOIN hoặc batch query bằng IN.

Nếu truy vấn order độc lập và được chạy ngoài transaction chung, flatMap với concurrency phù hợp có thể tăng throughput. Nếu nằm trong cùng transaction-bound connection hoặc cần thứ tự, concatMap thường an toàn và dễ hiểu hơn.

## 13. Khi nào nên dùng then()?

then() không phải một mapper tổng quát như map/flatMap. Nó chờ Publisher trước hoàn tất rồi mới subscribe Publisher sau và bỏ qua giá trị của Publisher trước.

Ví dụ:

~~~java
return auditRepository.save(auditRecord)
    .then(notificationRecordRepository.save(notificationRecord))
    .then();
~~~

Thao tác lưu notification chỉ bắt đầu sau khi lưu audit hoàn tất. Nếu cần giữ lại kết quả của bước trước, dùng flatMap kết hợp thenReturn:

~~~java
return customerRepository.save(customer)
    .flatMap(saved ->
        auditRepository.save(toAudit(saved))
            .thenReturn(saved)
    );
~~~

Nếu cần biến đổi chính giá trị vừa lưu, dùng map:

~~~java
return customerRepository.save(customer)
    .map(CustomerSummary::from);
~~~

## 14. N+1 không được giải quyết chỉ bằng cách đổi operator

Giả sử có 100 customer và mỗi customer cần danh sách order:

~~~java
return customerRepository.findAll()
    .flatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders))
    );
~~~

Đổi flatMap thành concatMap:

~~~java
return customerRepository.findAll()
    .concatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders))
    );
~~~

Cả hai cách vẫn có một truy vấn lấy customer và một truy vấn order cho mỗi customer. Khác biệt là flatMap có thể chạy nhiều truy vấn con đồng thời, còn concatMap chạy lần lượt.

Muốn giảm số round trip, hãy batch:

~~~java
return customerRepository.findByStatus("ACTIVE")
    .collectList()
    .flatMapMany(customers -> {
        if (customers.isEmpty()) {
            return Flux.empty();
        }

        List<Long> ids = customers.stream()
            .map(Customer::getId)
            .toList();

        return orderRepository.findByCustomerIdIn(ids)
            .collectMultimap(PurchaseOrder::getCustomerId)
            .flatMapMany(ordersByCustomer ->
                Flux.fromIterable(customers)
                    .map(customer ->
                        new CustomerDetail(
                            customer.getId(),
                            customer.getName(),
                            List.copyOf(
                                ordersByCustomer.getOrDefault(
                                    customer.getId(),
                                    List.of()
                                )
                            )
                        )
                    )
            );
    });
~~~

Giải pháp batch dùng một truy vấn customer và một truy vấn order cho danh sách ID (hoặc mỗi batch ID), sau đó map/group dữ liệu trong bộ nhớ. Với tập dữ liệu lớn, nên phân trang customer và giới hạn kích thước batch thay vì collect toàn bộ bảng.

## 15. Kết hợp với @Transactional

Khi một phương thức reactive được đánh dấu @Transactional, các thao tác database tham gia cùng transaction context nếu dùng transaction manager và ConnectionFactory tương ứng.

Nếu nhiều thao tác phải cùng commit hoặc rollback, hãy nối chúng tuần tự:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            orderLineRepository.saveAll(saved.getLines())
                .then()
                .thenReturn(saved)
        )
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
        )
        .then();
}
~~~

Tránh:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    return Mono.when(
        orderRepository.save(order),
        auditRepository.save(toAudit(order)),
        notificationRepository.save(toNotification(order))
    ).then();
}
~~~

Mono.when subscribe các publisher đầu vào để chờ tất cả. Nếu chúng dùng chung transaction-bound connection, các câu SQL có thể bị phát đồng thời trên cùng connection. Khả năng này phụ thuộc driver và không nên được giả định là an toàn.

Đổi scheduler bằng subscribeOn hoặc publishOn không tạo connection mới. Nếu nghiệp vụ cho phép mỗi công việc commit độc lập, có thể thiết kế transaction riêng cho từng công việc. Không tách transaction nếu toàn bộ thao tác phải atomic như một đơn vị.

## 16. Lưu ý với dữ liệu được phát từ Flux

Một số thao tác cần gom dữ liệu trước khi truy vấn tiếp:

~~~java
return customerRepository.findByStatus("ACTIVE")
    .collectList()
    .flatMapMany(customers -> {
        // Có toàn bộ danh sách customer để tạo danh sách ID.
        return loadOrdersFor(customers);
    });
~~~

collectList() chuyển Flux thành Mono<List<T>>. Nó hữu ích khi cần tạo một truy vấn IN từ danh sách ID, nhưng giữ toàn bộ phần tử trong bộ nhớ cho đến khi nguồn hoàn tất.

Với dữ liệu lớn:

- Phân trang nguồn.
- Batch theo số ID giới hạn.
- Xử lý từng trang rồi phát kết quả.
- Tránh collectList() trên toàn bộ bảng.

Nếu chỉ cần xử lý từng phần tử một, concatMap cho phép tuần tự hóa mà không cần gom tất cả phần tử vào list.

## 17. Những lỗi thường gặp

| Cách viết | Vấn đề | Cách xử lý |
|---|---|---|
| map trả về Mono/Flux | Tạo Mono<Mono<T>> hoặc Flux<Publisher<T>> | Dùng flatMap hoặc concatMap |
| flatMap cho các ghi cần thứ tự | Inner Publisher có thể chạy đồng thời và kết quả đảo thứ tự | Dùng concatMap hoặc nối bằng then |
| flatMapSequential để tránh SQL đồng thời | Vẫn có thể chạy inner Publisher đồng thời | Dùng concatMap |
| concatMap cho tác vụ độc lập cần throughput cao | Xử lý tuần tự, có thể chậm | Cân nhắc flatMap với concurrency phù hợp và connection riêng |
| Gọi block() trong map | Chặn thread reactive | Nối Publisher bằng flatMap |
| Gọi subscribe() trong mapper/service | Tạo luồng độc lập, mất kiểm soát lỗi và transaction | Trả Publisher và compose |
| Dùng map chỉ để bọc Mono.just | Tạo Publisher thừa | Trả giá trị trực tiếp bằng map |
| Nghĩ concatMap loại bỏ N+1 | Chỉ tuần tự hóa, không giảm query count | JOIN hoặc batch IN |
| Nuốt lỗi bằng onErrorResume | Có thể che giấu lỗi database hoặc làm transaction commit | Chỉ recover theo chính sách nghiệp vụ |
| Dùng flatMap không giới hạn với nhiều truy vấn | Tăng áp lực pool/database | Giới hạn concurrency hoặc batch |
| Nghĩ đổi scheduler tạo connection mới | Reactor Context vẫn mang transaction resource | Thiết kế transaction boundary riêng |
| collectList() trên tập dữ liệu lớn | Tốn bộ nhớ | Pagination hoặc batching |

## 18. Chọn operator theo mục đích

| Mục đích | Operator thường phù hợp | Ví dụ |
|---|---|---|
| Chuyển entity thành DTO | map | Customer → CustomerSummary |
| Lấy một thuộc tính từ kết quả query | map | Customer → customer.getEmail() |
| Ánh xạ row DatabaseClient | map | Row → record Java |
| Truy vấn tiếp dựa trên kết quả vừa đọc | flatMap | Customer → findByCustomerId() |
| Lưu một entity rồi dùng kết quả đã lưu | flatMap | save() → ghi audit |
| Chạy nhiều công việc độc lập có thể đồng thời | flatMap có concurrency giới hạn | Xử lý từng command độc lập |
| Xử lý từng ID theo thứ tự | concatMap | ID → findById/save |
| Nhiều thao tác SQL phải tuần tự trong transaction | then/flatMap/concatMap | reserve → save order → audit |
| Giữ thứ tự kết quả nhưng chấp nhận inner concurrency | flatMapSequential | Tải nhiều dữ liệu độc lập |

## 19. Quy trình đọc một reactive database pipeline

Khi đọc hoặc viết một pipeline R2DBC, hãy lần lượt xác định:

1. Publisher nguồn là Mono hay Flux?
2. Hàm mapper trả về một giá trị hay một Publisher?
3. Nếu trả Publisher, có cần subscribe và làm phẳng kết quả không?
4. Có nhiều phần tử nguồn để các inner Publisher chạy đồng thời không?
5. Thứ tự thực thi SQL có quan trọng không?
6. Các thao tác có tham gia cùng transaction và connection không?
7. Trường hợp nguồn rỗng sẽ được xử lý ra sao?
8. Lỗi được truyền ra, chuyển đổi hay bị recover?
9. Có giới hạn concurrency và kích thước dữ liệu không?
10. Có đang tạo N+1 bằng một truy vấn con cho mỗi phần tử không?

Đừng chọn operator chỉ theo thói quen. Hãy nhìn kiểu dữ liệu của mapper, số publisher được tạo, thứ tự nghiệp vụ và transaction boundary.

## 20. Ghi nhớ

- map dùng cho biến đổi đồng bộ một giá trị; nó không subscribe Publisher được trả về.
- flatMap dùng khi bước tiếp theo trả về Mono/Flux và cần làm phẳng Publisher lồng.
- flatMap trên Flux có thể chạy nhiều inner Publisher đồng thời và không bảo đảm thứ tự kết quả nguồn.
- concatMap cũng làm phẳng Publisher nhưng chờ từng inner hoàn tất, giữ thứ tự và chỉ có một inner Publisher hoạt động tại một thời điểm.
- flatMapSequential giữ thứ tự phát kết quả nhưng vẫn có thể chạy inner Publisher đồng thời.
- Dùng map để ánh xạ row hoặc entity thành DTO; dùng flatMap để nối truy vấn database phụ thuộc kết quả trước.
- Dùng concatMap hoặc then khi các thao tác SQL cần chạy tuần tự, đặc biệt trong cùng transaction-bound connection.
- Mono.empty() không gọi mapper của map/flatMap; dùng switchIfEmpty nếu cần xử lý not-found.
- Không gọi block() hoặc subscribe() trong service để điều khiển luồng; hãy compose và trả Publisher.
- Giới hạn concurrency giúp kiểm soát tải nhưng không tự biến N+1 thành batch query.
- concatMap không giảm số lượng truy vấn; JOIN hoặc batch IN mới giảm round trip.
- Luôn xem xét lỗi, cancellation, backpressure và transaction context khi ghép các thao tác truy cập dữ liệu.
