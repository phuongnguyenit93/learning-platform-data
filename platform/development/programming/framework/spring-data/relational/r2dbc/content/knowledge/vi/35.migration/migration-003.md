# Chuyển hợp đồng dịch vụ từ giá trị trực tiếp sang Publisher

Khi chuyển một ứng dụng Spring Data Relational R2DBC từ cách truy cập dữ liệu đồng bộ sang reactive, thay đổi quan trọng không chỉ nằm ở repository. Hợp đồng của service và toàn bộ caller cũng cần biểu diễn rằng kết quả sẽ được cung cấp bất đồng bộ qua một publisher.

Một service đồng bộ có thể trả trực tiếp một entity, danh sách, boolean hoặc không trả giá trị. Với R2DBC, repository thường trả về **Mono<T>** hoặc **Flux<T>**. Service cần giữ publisher đó trong chuỗi xử lý, kết hợp các bước bằng operator reactive và để framework ở ranh giới phù hợp subscribe.

Ví dụ, hợp đồng cũ:

~~~java
Customer findById(Long id);
~~~

có thể trở thành:

~~~java
Mono<Customer> findById(Long id);
~~~

Thay đổi này ảnh hưởng đến controller, service khác, test, transaction, exception handling và cách biểu diễn dữ liệu rỗng. Không thể chỉ đổi kiểu trả về rồi giữ nguyên cách gọi đồng bộ.

Bài học này giải thích ý nghĩa của Publisher trong hợp đồng service, cách chọn Mono/Flux, chuyển đổi từng loại kết quả, viết lại caller bằng reactive composition, xử lý lỗi và kết quả rỗng, giữ transaction/context, tích hợp HTTP, duy trì tương thích với code cũ và kiểm thử quá trình chuyển đổi.

## 1. Hợp đồng đồng bộ và hợp đồng reactive khác nhau thế nào?

Trong mô hình đồng bộ, một phương thức thường trả kết quả ngay khi phương thức kết thúc:

~~~java
public Customer getCustomer(Long id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

Caller nhận một Customer hoặc exception ngay trong luồng gọi. Nếu repository phải truy cập database, thread gọi thường chờ I/O hoàn tất.

Trong mô hình reactive, phương thức trả về một publisher mô tả kết quả sẽ được phát khi có subscription:

~~~java
public Mono<Customer> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Lời gọi service trả về Mono<Customer>. Kết quả có thể được phát sau đó, hoàn tất rỗng hoặc phát lỗi. Việc thực thi thường được kích hoạt khi publisher được subscribe.

| Hợp đồng đồng bộ | Hợp đồng reactive thường dùng |
|---|---|
| Customer | Mono<Customer> |
| Optional<Customer> | Mono<Customer> |
| List<Customer> | Flux<Customer> hoặc Mono<List<Customer>> |
| boolean | Mono<Boolean> |
| long / Long | Mono<Long> |
| void | Mono<Void> |
| T có thể không tồn tại | Mono<T> |
| Nhiều kết quả dạng stream | Flux<T> |

Sự khác biệt cốt lõi:

- Giá trị trực tiếp là kết quả đã có.
- Publisher là một mô tả computation có thể phát dữ liệu, hoàn tất hoặc phát lỗi trong tương lai.
- Caller không thể đọc giá trị bên trong publisher như đọc một object bình thường.
- Caller phải nối publisher với các bước tiếp theo hoặc subscribe ở ranh giới ứng dụng phù hợp.

Một publisher không phải là một giá trị được bọc trong hộp. Nó là một phần của hợp đồng thực thi.

## 2. Publisher, Mono và Flux

Reactive Streams định nghĩa interface Publisher<T>. Publisher phát từ 0 tới nhiều phần tử, có thể hoàn tất hoặc kết thúc bằng lỗi, đồng thời tuân theo giao thức subscription và backpressure.

Reactor cung cấp hai kiểu phổ biến:

- **Mono<T>:** phát tối đa một phần tử rồi hoàn tất, hoặc hoàn tất rỗng, hoặc phát lỗi.
- **Flux<T>:** phát từ 0 tới nhiều phần tử, rồi hoàn tất hoặc phát lỗi.

~~~text
Publisher<T>
    |
    +-- Mono<T>  : 0 hoặc 1 phần tử
    |
    +-- Flux<T>  : 0 đến N phần tử
~~~

Ví dụ:

~~~java
Mono<Customer> oneCustomer =
        customerRepository.findById(42L);

Flux<Customer> manyCustomers =
        customerRepository.findAll();
~~~

### 2.1. Chọn Mono hay Flux theo ngữ nghĩa

Chọn kiểu trả về theo cardinality của use case, không chỉ theo kiểu dữ liệu cũ.

| Use case | Kiểu trả về gợi ý |
|---|---|
| Tìm một customer theo ID | Mono<Customer> |
| Tìm customer theo email, tối đa một hàng | Mono<Customer> |
| Liệt kê customer | Flux<Customer> |
| Kiểm tra customer tồn tại | Mono<Boolean> |
| Đếm số customer | Mono<Long> |
| Lưu một customer | Mono<Customer> |
| Xóa một customer | Mono<Void> |
| Tạo báo cáo cần gom toàn bộ hàng | Mono<Report> hoặc Mono<List<T>> |
| Phát các event theo thời gian | Flux<Event> |

Nếu nghiệp vụ cần một danh sách hoàn chỉnh để tính toán, Mono<List<T>> có thể phù hợp. Nếu caller có thể xử lý từng phần tử, Flux<T> thường giữ được lợi ích streaming và backpressure.

Không chuyển mọi List<T> thành Mono<List<T>> theo thói quen. Cũng không chuyển mọi danh sách thành Flux nếu use case cần biết toàn bộ tập hợp trước khi tiếp tục.

### 2.2. Publisher có thể hoàn tất rỗng

Mono<T> không đảm bảo luôn có một T. Nó có thể:

1. Phát một phần tử rồi complete.
2. Complete mà không phát phần tử nào.
3. Phát error.

Flux<T> có thể phát không phần tử nào hoặc nhiều phần tử.

Vì vậy, Mono<T> không giống T nullable một cách hoàn toàn. Trường hợp không có kết quả được biểu diễn bằng Mono.empty(), không phải null.

## 3. Chuyển đổi hợp đồng service theo từng loại kết quả

### 3.1. Từ entity trực tiếp sang Mono<Entity>

Trước:

~~~java
public Customer findCustomer(Long id) {
    return customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

Sau:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

switchIfEmpty chỉ phát lỗi khi repository complete rỗng. Nó không bắt lỗi database; lỗi từ repository vẫn được truyền xuống subscriber.

### 3.2. Từ Optional<T> sang Mono<T>

Trước:

~~~java
public Optional<Customer> findByEmail(String email) {
    return customerRepository.findByEmail(email);
}
~~~

Sau:

~~~java
public Mono<Customer> findByEmail(String email) {
    return customerRepository.findByEmail(email);
}
~~~

Nếu đang có một Optional trong bộ nhớ và muốn chuyển thành publisher:

~~~java
Optional<Customer> result = findInCache(email);

return Mono.justOrEmpty(result);
~~~

Không dùng Mono.just(optional.orElse(null)), vì Mono.just(null) không hợp lệ.

### 3.3. Từ List<T> sang Flux<T>

Trước:

~~~java
public List<Customer> findActiveCustomers() {
    return customerRepository.findAllActive();
}
~~~

Sau:

~~~java
public Flux<Customer> findActiveCustomers() {
    return customerRepository.findAllActive();
}
~~~

Nếu dữ liệu hiện có trong bộ nhớ:

~~~java
List<Customer> customers = loadInMemory();

return Flux.fromIterable(customers);
~~~

Đoạn này chỉ biến một collection đã có thành Flux; nó không biến thao tác tạo collection đồng bộ trước đó thành non-blocking.

### 3.4. Từ List<T> sang Mono<List<T>>

Nếu caller thực sự cần toàn bộ danh sách:

~~~java
public Mono<List<Customer>> findActiveCustomers() {
    return customerRepository.findAllActive()
            .collectList();
}
~~~

collectList() chờ Flux hoàn tất rồi phát một List. Điều này tiêu thụ bộ nhớ tỷ lệ với số hàng. Không dùng cho kết quả có thể rất lớn nếu caller có thể xử lý từng phần tử.

### 3.5. Từ boolean sang Mono<Boolean>

Trước:

~~~java
public boolean emailExists(String email) {
    return customerRepository.existsByEmail(email);
}
~~~

Sau:

~~~java
public Mono<Boolean> emailExists(String email) {
    return customerRepository.existsByEmail(email);
}
~~~

Caller phải dùng flatMap, filter, map hoặc toán tử khác để xử lý giá trị boolean sau khi nó được phát:

~~~java
return customerService.emailExists(command.email())
        .flatMap(exists -> {
            if (exists) {
                return Mono.error(
                        new EmailAlreadyRegisteredException(
                                command.email()));
            }

            return customerService.create(command);
        });
~~~

Không viết if (customerService.emailExists(email)), vì biểu thức đó là Mono<Boolean>, không phải boolean.

### 3.6. Từ void sang Mono<Void>

Trước:

~~~java
public void deleteCustomer(Long id) {
    customerRepository.deleteById(id);
}
~~~

Sau:

~~~java
public Mono<Void> deleteCustomer(Long id) {
    return customerRepository.deleteById(id);
}
~~~

Mono<Void> biểu diễn thao tác chỉ quan tâm hoàn tất hay lỗi. Nó thường không phát một giá trị dữ liệu.

Nếu muốn xác nhận hàng tồn tại trước khi xóa:

~~~java
public Mono<Void> deleteCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .flatMap(customer ->
                    customerRepository.delete(customer));
}
~~~

### 3.7. Từ count hoặc aggregate sang Mono

Trước:

~~~java
public long countActiveCustomers() {
    return customerRepository.countActive();
}
~~~

Sau:

~~~java
public Mono<Long> countActiveCustomers() {
    return customerRepository.countActive();
}
~~~

Các phép tổng hợp database thường được biểu diễn bằng Mono vì chúng phát một giá trị duy nhất.

## 4. Đổi service interface và các caller

Giả sử hợp đồng cũ:

~~~java
public interface CustomerService {
    Customer getById(Long id);
    List<Customer> findAll();
    Customer create(CreateCustomerCommand command);
    void delete(Long id);
}
~~~

Hợp đồng reactive:

~~~java
public interface CustomerService {
    Mono<Customer> getById(Long id);
    Flux<Customer> findAll();
    Mono<Customer> create(CreateCustomerCommand command);
    Mono<Void> delete(Long id);
}
~~~

Việc đổi return type là thay đổi contract. Tất cả caller cần được cập nhật theo.

Một caller cũ:

~~~java
Customer customer = customerService.getById(id);
return customer.getEmail();
~~~

Caller reactive:

~~~java
return customerService.getById(id)
        .map(Customer::getEmail);
~~~

Caller không đọc property ngay. Nó khai báo phép biến đổi sẽ áp dụng khi customer được phát.

### 4.1. Đổi return type là thay đổi API

Trong Java, return type không phải thành phần để overload method. Không thể khai báo hai method cùng tên và cùng parameter chỉ khác kiểu trả về:

~~~java
// Không hợp lệ trong cùng một class/interface.
Customer getById(Long id);
Mono<Customer> getById(Long id);
~~~

Nếu cần giai đoạn chuyển tiếp, dùng tên method hoặc interface khác:

~~~java
public interface LegacyCustomerService {
    Customer getById(Long id);
}

public interface ReactiveCustomerService {
    Mono<Customer> getById(Long id);
}
~~~

Hoặc dùng tên method phân biệt tạm thời như getByIdReactive, nhưng nên tránh duy trì hai contract lâu dài nếu không cần.

Thay đổi interface công khai cũng có thể phá source compatibility và binary compatibility của module phụ thuộc. Kiểm tra các implementation, mock, test, controller, event listener và consumer bên ngoài module.

### 4.2. Chuyển đổi bottom-up

Một thứ tự thường dễ quản lý:

1. Chuyển repository sang R2DBC reactive API.
2. Chuyển service trực tiếp gọi repository sang Mono/Flux.
3. Chuyển các service gọi service đó.
4. Chuyển controller hoặc message handler.
5. Chuyển test và fixture.
6. Xóa các blocking bridge cũ khi không còn caller.

Nếu chuyển top-down trước khi tầng dưới có reactive contract, dễ tạo ra các đoạn block hoặc wrapper không cần thiết.

## 5. map và flatMap khi caller dùng service reactive

Đây là thay đổi quan trọng nhất trong code gọi service.

### 5.1. Dùng map khi phép biến đổi đồng bộ

map nhận một giá trị T và trả về R:

~~~java
return customerService.getById(id)
        .map(Customer::getEmail);
~~~

Kết quả là Mono<String>.

Dùng map cho phép biến đổi thuần, nhanh, không trả một publisher khác.

### 5.2. Dùng flatMap khi bước tiếp theo cũng reactive

Nếu bước tiếp theo gọi một service/repository trả publisher, dùng flatMap:

~~~java
return customerService.getById(id)
        .flatMap(customer ->
                orderService.findLatestOrder(customer.getId()));
~~~

Kết quả là Mono<Order>, không phải Mono<Mono<Order>>.

Sai:

~~~java
return customerService.getById(id)
        .map(customer ->
                orderService.findLatestOrder(customer.getId()));
~~~

Kết quả của biểu thức sai là Mono<Mono<Order>>: publisher bên trong chưa được nối vào luồng ngoài.

Quy tắc nhớ:

- map: T thành R.
- flatMap: T thành Publisher<R>, rồi làm phẳng publisher.

### 5.3. Nối nhiều bước phụ thuộc nhau

Ví dụ tạo customer rồi tạo profile dùng ID vừa sinh:

~~~java
public Mono<CustomerProfile> register(
        RegisterCustomerCommand command) {

    return customerRepository.save(
                    Customer.from(command))
            .flatMap(customer ->
                    profileRepository.save(
                            CustomerProfile.forCustomer(
                                    customer.getId(),
                                    command.profileName())));
}
~~~

Bước thứ hai chỉ chạy sau khi bước thứ nhất phát customer đã lưu.

Không gọi subscribe() ở giữa hai bước. Làm như vậy tách hai execution flow và không bảo đảm thứ tự hoàn tất.

## 6. Chuyển đổi các chuỗi logic đồng bộ sang reactive

### 6.1. Từ if/else sang flatMap

Đồng bộ:

~~~java
public Customer register(RegisterCommand command) {
    if (customerRepository.existsByEmail(command.email())) {
        throw new EmailAlreadyRegisteredException();
    }

    return customerRepository.save(Customer.from(command));
}
~~~

Reactive:

~~~java
public Mono<Customer> register(RegisterCommand command) {
    return customerRepository.existsByEmail(command.email())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(
                            new EmailAlreadyRegisteredException());
                }

                return customerRepository.save(
                        Customer.from(command));
            });
}
~~~

Đây là chuyển đổi cơ học của luồng. Tuy nhiên, kiểm tra exists trước insert không ngăn được race condition khi hai request đồng thời. Unique constraint ở database vẫn phải bảo vệ dữ liệu; service cần chuyển lỗi constraint thành lỗi nghiệp vụ phù hợp.

### 6.2. Kết hợp hai nguồn độc lập bằng zip

Nếu hai truy vấn độc lập và cần cả hai kết quả:

~~~java
return customerRepository.findById(customerId)
        .zipWith(addressRepository.findByCustomerId(customerId))
        .map(tuple ->
                CustomerSummary.from(
                        tuple.getT1(),
                        tuple.getT2()));
~~~

zipWith chỉ phát khi cả hai publisher đều phát một phần tử. Nếu một publisher empty, kết quả zip cũng empty.

Nếu một nguồn có thể rỗng nhưng nghiệp vụ vẫn tiếp tục, cần xử lý empty trước hoặc dùng chiến lược combine phù hợp.

### 6.3. Chờ nhiều thao tác không cần kết quả bằng when

Nếu cần thực hiện hai thao tác độc lập và chỉ quan tâm cả hai hoàn tất:

~~~java
return Mono.when(
        auditRepository.save(auditRecord),
        notificationStateRepository.save(notificationState))
        .then();
~~~

Mono.when subscribe các publisher được cung cấp và hoàn tất khi chúng hoàn tất; lỗi từ một publisher làm luồng kết hợp lỗi. Đây không tự động bảo đảm hai thao tác atomic trong cùng transaction trừ khi cả hai tham gia cùng reactive transaction context.

### 6.4. Xử lý nhiều phần tử với flatMap, concatMap và flatMapSequential

Với Flux:

~~~java
return customerRepository.findAllActive()
        .flatMap(customer ->
                riskService.calculateScore(customer));
~~~

flatMap có thể chạy các inner publisher đồng thời và phát kết quả theo thứ tự hoàn tất. Nếu cần xử lý tuần tự:

~~~java
return customerRepository.findAllActive()
        .concatMap(customer ->
                riskService.calculateScore(customer));
~~~

Nếu muốn xử lý đồng thời nhưng giữ thứ tự nguồn khi phát kết quả:

~~~java
return customerRepository.findAllActive()
        .flatMapSequential(customer ->
                riskService.calculateScore(customer));
~~~

Chọn concurrency có giới hạn khi downstream/database có tài nguyên hữu hạn. Không dùng flatMap vô hạn trên một Flux rất lớn mà không cân nhắc áp lực lên connection pool và service phụ thuộc.

## 7. Publisher là lazy: thời điểm thực thi thay đổi

Trong Reactor, nhiều publisher là cold và lazy: tạo publisher chưa thực thi database query. Query được kích hoạt khi có subscription.

Ví dụ:

~~~java
Mono<Customer> customerMono =
        customerRepository.findById(42L);
~~~

Đoạn này mới tạo publisher. Nó không bảo đảm đã truy cập database.

Nếu không ai subscribe, thao tác có thể không chạy. Trong WebFlux, framework subscribe khi xử lý response publisher. Trong StepVerifier, verifier subscribe khi test chạy.

### 7.1. Không gọi subscribe() bên trong service

Không nên:

~~~java
public void createCustomer(CreateCustomerCommand command) {
    customerRepository.save(Customer.from(command))
            .subscribe();
}
~~~

Method trả về ngay, lỗi không được truyền tới caller, caller không biết lúc nào thao tác hoàn tất và transaction/context có thể bị tách khỏi request.

Nên:

~~~java
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    return customerRepository.save(Customer.from(command));
}
~~~

Caller quyết định cách nối publisher. Framework ở ranh giới HTTP hoặc message consumer sẽ subscribe theo lifecycle của nó.

### 7.2. Dùng defer khi cần tạo computation cho mỗi subscription

~~~java
public Mono<String> nextReference() {
    return Mono.defer(() -> {
        String reference = referenceGenerator.next();
        return Mono.just(reference);
    });
}
~~~

defer gọi supplier khi subscribe, tạo giá trị mới cho từng subscription.

Nếu dùng Mono.just(referenceGenerator.next()), generator chạy ngay lúc method được gọi, không phải lúc subscribe.

### 7.3. Side effect cần nằm trong publisher

Đồng bộ:

~~~java
public void recordAccess(Long customerId) {
    accessLogRepository.save(new AccessLog(customerId));
}
~~~

Reactive:

~~~java
public Mono<Void> recordAccess(Long customerId) {
    return accessLogRepository.save(new AccessLog(customerId))
            .then();
}
~~~

Nếu chỉ tạo publisher mà không trả về hoặc nối nó, thao tác sẽ không được kích hoạt.

## 8. Chuyển giá trị trực tiếp thành publisher đúng cách

Các factory Reactor có semantics khác nhau:

| Factory | Khi nào dùng | Lưu ý |
|---|---|---|
| Mono.just(value) | Giá trị đã có và không null | Phát ngay giá trị đó khi subscribe |
| Mono.justOrEmpty(value) | Giá trị có thể null hoặc Optional | Null/Optional.empty trở thành empty |
| Mono.fromSupplier(supplier) | Tạo một giá trị đồng bộ khi subscribe | Supplier trả null thì complete empty |
| Mono.fromCallable(callable) | Gọi một tác vụ có thể ném exception | Exception trở thành onError; null thành empty |
| Mono.fromRunnable(runnable) | Chạy tác vụ không có kết quả | Hoàn tất bằng Mono<Void> |
| Flux.fromIterable(values) | Chuyển collection có sẵn thành Flux | Collection đã được tạo trước đó |
| Flux.defer(supplier) | Tạo Flux riêng cho mỗi subscription | Supplier phải trả Publisher/Flux phù hợp |

Ví dụ:

~~~java
return Mono.justOrEmpty(customerCache.get(id));
~~~

~~~java
return Mono.fromSupplier(() -> calculateDisplayName(customer));
~~~

~~~java
return Mono.fromRunnable(() -> localAuditBuffer.record(event));
~~~

Các factory trên không biến một API blocking thành non-blocking. Nếu supplier gọi JDBC, file I/O hoặc HTTP client blocking, nó vẫn chặn thread đang thực thi supplier trừ khi được schedule phù hợp.

## 9. Tích hợp service blocking cũ trong giai đoạn chuyển tiếp

Một hệ thống lớn có thể chưa chuyển được tất cả dependency cùng lúc. Có thể đặt adapter reactive quanh một API blocking như bước chuyển tiếp.

Ví dụ:

~~~java
public Mono<Customer> findLegacyCustomer(Long id) {
    return Mono.fromCallable(() ->
                    legacyCustomerService.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

boundedElastic phù hợp hơn event-loop thread cho một số tác vụ blocking vì nó dùng scheduler dành cho công việc blocking có giới hạn. Tuy vậy:

- Đây vẫn là thao tác blocking.
- Thread pool có giới hạn và có thể bị bão hòa.
- Timeout và cancellation có thể không dừng được lời gọi blocking bên dưới.
- Không nên coi wrapper là giải pháp thay thế driver reactive.
- Cần đo tải và lập kế hoạch loại bỏ adapter nếu mục tiêu là stack non-blocking.

Không bọc JDBC bằng Mono.fromCallable rồi tuyên bố ứng dụng đã chuyển sang R2DBC. Nó chỉ cô lập blocking call khỏi event loop.

### 9.1. Nếu caller imperative cần kết quả từ service reactive

Có thể cần một facade đồng bộ trong giai đoạn chuyển tiếp:

~~~java
public Customer findCustomerBlocking(Long id) {
    return reactiveCustomerService.findById(id)
            .block(Duration.ofSeconds(3));
}
~~~

Chỉ dùng ở ranh giới imperative được kiểm soát, có timeout, thread phù hợp và xử lý empty/error rõ ràng. Không gọi phương thức này từ WebFlux event loop, reactive transaction hoặc một publisher đang chạy.

Tốt hơn là giữ hai adapter ở hai ranh giới rõ ràng, thay vì để service reactive bên trong tự block khi có caller cũ.

## 10. Không block để lấy giá trị từ Mono/Flux

Một anti-pattern phổ biến:

~~~java
public String getCustomerEmail(Long id) {
    Customer customer =
            customerRepository.findById(id).block();

    return customer.getEmail();
}
~~~

Cách này:

- Chặn thread cho tới khi database trả kết quả.
- Có thể gây deadlock hoặc làm cạn event-loop thread nếu gọi từ reactive pipeline.
- Mất lợi ích backpressure và composition.
- Có thể ném lỗi hoặc trả null khi publisher empty tùy cách gọi.
- Làm ranh giới đồng bộ/reactive khó nhận diện.

Nên trả publisher:

~~~java
public Mono<String> getCustomerEmail(Long id) {
    return customerRepository.findById(id)
            .map(Customer::getEmail);
}
~~~

Không dùng blockOptional() như một cách né vấn đề; nó vẫn là blocking.

## 11. Empty, null và Optional khi đổi contract

Trong code đồng bộ, một phương thức có thể trả null hoặc Optional.empty. Trong reactive contract, nên biểu diễn không có kết quả bằng Mono.empty().

Ví dụ:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Nếu nghiệp vụ bắt buộc có customer:

~~~java
public Mono<Customer> requireCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Không trả Mono.just(null). Reactor không cho phép phát null như một phần tử.

### 11.1. Không biến mọi empty thành error

Một truy vấn tìm kiếm có thể hợp lệ khi không có kết quả:

~~~java
public Flux<Customer> search(String keyword) {
    return customerRepository.search(keyword);
}
~~~

Flux.empty() là danh sách kết quả rỗng, không phải lỗi.

Chỉ dùng switchIfEmpty khi hợp đồng nghiệp vụ yêu cầu phải có một kết quả. Nếu không, chuyển empty thành lỗi sẽ làm sai semantics API.

### 11.2. Optional lồng trong Mono thường không cần thiết

Tránh:

~~~java
Mono<Optional<Customer>> findCustomer(Long id);
~~~

Thông thường Mono<Customer> đã biểu diễn cả có và không có customer. Dùng Mono<Optional<T>> chỉ khi Optional là một phần dữ liệu thực sự cần phát, không phải cách mã hóa not-found lần thứ hai.

## 12. Chuyển exception đồng bộ sang tín hiệu onError

Trong code đồng bộ:

~~~java
public Customer getCustomer(Long id) {
    try {
        return repository.findById(id)
                .orElseThrow(() ->
                        new CustomerNotFoundException(id));
    } catch (DataAccessException ex) {
        throw new CustomerPersistenceException(ex);
    }
}
~~~

Trong reactive flow, exception xảy ra khi publisher được thực thi phải được xử lý bằng operator:

~~~java
public Mono<Customer> getCustomer(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .onErrorMap(
                    DataAccessException.class,
                    CustomerPersistenceException::new);
}
~~~

try/catch quanh việc tạo publisher thường không bắt được lỗi xảy ra sau đó khi subscribe.

Dùng:

- doOnError: ghi log/metric nhưng giữ nguyên lỗi.
- onErrorMap: chuyển loại lỗi.
- onErrorResume: thay publisher lỗi bằng một publisher khác khi có fallback hợp lệ.
- retryWhen: retry có điều kiện và giới hạn.

Không biến mọi lỗi thành Mono.empty(), vì như vậy database failure có thể bị hiểu nhầm thành not-found.

### 12.1. Giữ cause khi chuyển lỗi

~~~java
public class CustomerPersistenceException extends RuntimeException {
    public CustomerPersistenceException(Throwable cause) {
        super("Unable to access customer data", cause);
    }
}
~~~

Giữ cause giúp log và tracing có thể truy ngược lỗi R2DBC gốc. Không trả thông điệp SQL hoặc stack trace nội bộ trực tiếp cho client.

## 13. Chuyển logic điều khiển và vòng lặp

### 13.1. Không dùng for-each để chờ publisher

Sai:

~~~java
for (Customer customer : customers) {
    orderRepository.findByCustomerId(customer.getId())
            .subscribe();
}
~~~

Các subscription độc lập không được kết hợp vào một kết quả duy nhất, lỗi bị tách rời và không có điều phối backpressure rõ ràng.

Nên:

~~~java
return Flux.fromIterable(customers)
        .concatMap(customer ->
                orderRepository.findByCustomerId(customer.getId()));
~~~

Hoặc nếu dữ liệu customer cũng đến từ repository:

~~~java
return customerRepository.findAll()
        .concatMap(customer ->
                orderRepository.findByCustomerId(customer.getId()));
~~~

### 13.2. Khi cần tuần tự và khi có thể song song

concatMap xử lý lần lượt và giữ thứ tự. flatMap cho phép nhiều inner publisher chạy đồng thời. flatMapSequential cho phép chạy đồng thời nhưng phát theo thứ tự nguồn.

Chọn theo nghiệp vụ:

- Cập nhật trạng thái phụ thuộc thứ tự: cân nhắc concatMap.
- Gọi dịch vụ độc lập và có concurrency giới hạn: flatMap với concurrency rõ ràng.
- Cần kết quả đúng thứ tự nhưng vẫn cho phép xử lý đồng thời: flatMapSequential.

Không chuyển vòng lặp tuần tự thành flatMap mặc định mà chưa kiểm tra race condition, thứ tự và giới hạn connection pool.

## 14. Chuyển transaction sang reactive contract

Spring hỗ trợ reactive transaction cho R2DBC qua reactive transaction manager và Reactor Context. Service cần trả về publisher thuộc cùng chuỗi thực thi để transaction manager quản lý lifecycle.

Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return customerRepository.findById(command.customerId())
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(
                            command.customerId())))
            .flatMap(customer ->
                    orderRepository.save(Order.from(customer, command)))
            .flatMap(order ->
                    orderLineRepository.saveAll(
                                    command.lines().stream()
                                            .map(line ->
                                                    OrderLine.from(order, line))
                                            .toList())
                            .then(Mono.just(order)));
}
~~~

Ví dụ giả định @Transactional được xử lý bởi reactive transaction manager của Spring và tất cả repository dùng cùng cấu hình transaction-aware ConnectionFactory.

Các điểm cần lưu ý:

- Method phải trả publisher để transaction boundary bao trùm việc subscribe và terminal signal.
- Không gọi subscribe() bên trong method.
- Không block giữa các bước.
- Không nuốt lỗi bằng fallback nếu nghiệp vụ yêu cầu rollback.
- Các thao tác phải tham gia cùng reactive transaction context.
- External side effect như gửi email không tự rollback cùng database.

Nếu cần điều khiển transaction tường minh, dùng TransactionalOperator và trả publisher được bọc:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work = performOrderCreation(command);

    return transactionalOperator.transactional(work);
}
~~~

### 14.1. Không giữ @Transactional trên method trả giá trị trực tiếp rồi gọi repository reactive

Một method đồng bộ trả Order không thể tự chờ một R2DBC operation hoàn tất mà vẫn giữ reactive transaction đúng cách. Nếu method gọi block(), nó quay lại mô hình blocking và có thể phá execution context.

Chuyển cả contract và transaction boundary sang publisher.

### 14.2. Retry ở ngoài transaction boundary phù hợp

Nếu cần retry transaction, thường đặt retry quanh publisher transaction để mỗi lần subscribe lại có thể mở transaction mới:

~~~java
return transactionalOperator.transactional(
                performOrderCreation(command))
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isRetryable));
~~~

Chỉ retry lỗi phù hợp và thao tác có thể thực hiện lại an toàn. Không retry mù khi không rõ transaction đã commit hay chưa hoặc có external side effect.

## 15. Context propagation và security khi service trở thành reactive

Trong WebFlux, SecurityContext và các metadata reactive thường được truyền qua Reactor Context. Khi service trả publisher và caller nối publisher trong cùng chain, context có thể được duy trì qua các operator được hỗ trợ.

Ví dụ đọc auditor hoặc authentication theo reactive context cần dùng API reactive tương ứng, chẳng hạn ReactiveSecurityContextHolder.

Không chuyển sang kiểu lấy thông tin người dùng từ ThreadLocal hoặc SecurityContextHolder imperative trong service reactive. Thread thực thi có thể thay đổi.

Cũng tránh:

~~~java
repository.save(entity).subscribe();
~~~

Subscription tách rời có thể không còn nằm trong request context và transaction ban đầu. Hãy nối publisher vào chuỗi đang xử lý.

## 16. Controller và HTTP contract sau khi service reactive

Khi service chuyển sang Mono/Flux, WebFlux controller có thể trả trực tiếp publisher.

Ví dụ GET:

~~~java
@GetMapping("/customers/{id}")
public Mono<CustomerResponse> getById(@PathVariable Long id) {
    return customerService.getById(id)
            .map(CustomerResponse::from);
}
~~~

Ví dụ danh sách:

~~~java
@GetMapping("/customers")
public Flux<CustomerResponse> findAll() {
    return customerService.findAll()
            .map(CustomerResponse::from);
}
~~~

Ví dụ POST:

~~~java
@PostMapping("/customers")
public Mono<ResponseEntity<CustomerResponse>> create(
        @RequestBody @Valid CreateCustomerRequest request) {

    return customerService.create(request.toCommand())
            .map(CustomerResponse::from)
            .map(response ->
                    ResponseEntity.created(
                            URI.create("/api/customers/" + response.id()))
                            .body(response));
}
~~~

WebFlux framework subscribe publisher để tạo HTTP response. Controller không cần gọi block() hoặc subscribe().

### 16.1. Xác định not-found response rõ ràng

Nếu service trả Mono.empty(), cần quyết định API muốn trả response gì. Có thể để controller chuyển empty thành 404:

~~~java
@GetMapping("/customers/{id}")
public Mono<ResponseEntity<CustomerResponse>> getById(
        @PathVariable Long id) {

    return customerService.findById(id)
            .map(CustomerResponse::from)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Hoặc service có thể phát CustomerNotFoundException bằng switchIfEmpty, sau đó @RestControllerAdvice ánh xạ sang 404.

Chọn một contract rõ ràng. Không để empty bất ngờ biến thành 200 với body rỗng nếu API yêu cầu 404.

### 16.2. Flux có thể được encode thành collection response

Controller trả Flux<T> có thể được WebFlux encode theo media type và codec. Nếu API contract yêu cầu pagination metadata như total count, page number và page size, thường cần một DTO chứa page data, không chỉ trả Flux thuần.

Ví dụ:

~~~java
public Mono<CustomerPageResponse> findPage(PageRequest request) {
    return customerRepository.findByPage(request)
            .collectList()
            .zipWith(customerRepository.count())
            .map(tuple ->
                    new CustomerPageResponse(
                            tuple.getT1(),
                            request.page(),
                            request.size(),
                            tuple.getT2()));
}
~~~

Đây là minh họa. Cần bảo đảm truy vấn dữ liệu và count nhất quán nếu dữ liệu thay đổi đồng thời, và không collect một tập kết quả không giới hạn.

## 17. Chuyển message handler và tác vụ nền

Không chỉ controller là caller của service. Một service đồng bộ có thể được gọi bởi:

- Scheduler.
- Message consumer.
- Application event listener.
- Command-line runner.
- Batch job.
- Một service khác trong module.

Khi chuyển sang reactive, mỗi adapter cần nối publisher với lifecycle mà framework quản lý.

Ví dụ một consumer reactive:

~~~java
public Mono<Void> handle(OrderCreated event) {
    return orderService.process(event.orderId())
            .then();
}
~~~

Nếu framework consumer yêu cầu method trả Mono<Void>, hãy trả publisher để framework điều phối acknowledgment theo lifecycle tương ứng.

Nếu callback của thư viện là imperative void, cần kiểm tra API có hỗ trợ reactive handler không. Không tạo subscribe() tách rời rồi acknowledge message ngay lập tức; message có thể được xác nhận trước khi database commit.

Với scheduler, có thể trả Mono<Void> cho scheduler tích hợp reactive. Nếu scheduler chỉ gọi Runnable, cần adapter có quản lý subscription và lỗi, đồng thời bảo đảm không chạy chồng các job ngoài ý muốn.

## 18. Chuyển test từ giá trị trực tiếp sang StepVerifier

Test đồng bộ thường assert trực tiếp:

~~~java
Customer customer = service.getById(42L);

assertThat(customer.getId()).isEqualTo(42L);
~~~

Test reactive nên dùng StepVerifier:

~~~java
StepVerifier.create(service.getById(42L))
        .assertNext(customer ->
                assertThat(customer.getId()).isEqualTo(42L))
        .verifyComplete();
~~~

### 18.1. Test empty

~~~java
StepVerifier.create(service.findById(999L))
        .verifyComplete();
~~~

### 18.2. Test error

~~~java
StepVerifier.create(service.getRequiredById(999L))
        .expectError(CustomerNotFoundException.class)
        .verify();
~~~

### 18.3. Test Flux nhiều phần tử

~~~java
StepVerifier.create(service.findAll())
        .expectNextCount(2)
        .verifyComplete();
~~~

### 18.4. Test timeout

~~~java
StepVerifier.create(service.findById(42L))
        .expectNextCount(1)
        .verifyComplete(Duration.ofSeconds(3));
~~~

Không dùng block() để test mọi publisher vì StepVerifier có thể kiểm tra thứ tự, empty, error, completion và cancellation một cách tường minh.

### 18.5. Mock repository cần trả publisher

Ví dụ với Mockito:

~~~java
when(customerRepository.findById(42L))
        .thenReturn(Mono.just(customer));
~~~

Không mock một entity trực tiếp nếu method thực tế trả Mono<Customer>.

Test error:

~~~java
when(customerRepository.findById(42L))
        .thenReturn(Mono.error(
                new DataAccessResourceFailureException("database unavailable")));
~~~

Test empty:

~~~java
when(customerRepository.findById(42L))
        .thenReturn(Mono.empty());
~~~

Cần có integration test với database thật cho SQL, mapping, transaction và driver; unit test mock publisher không chứng minh persistence thực tế.

## 19. Giữ tương thích với caller đồng bộ trong giai đoạn chuyển đổi

Nếu có module chưa thể chuyển ngay, có thể giữ một adapter đồng bộ ở biên module.

Một lựa chọn:

~~~java
@Component
public class BlockingCustomerFacade {

    private final ReactiveCustomerService reactiveService;

    public Customer findById(Long id) {
        return reactiveService.findById(id)
                .block(Duration.ofSeconds(3));
    }
}
~~~

Facade này chỉ dành cho caller imperative có kiểm soát. Không inject nó vào WebFlux controller hoặc reactive service khác.

Một lựa chọn khác là duy trì hai implementation tách biệt:

- Adapter blocking dùng JDBC cho module legacy.
- Adapter reactive dùng R2DBC cho module mới.

Cách này tăng chi phí duy trì hai đường persistence, nên chỉ giữ khi có lý do chuyển đổi rõ ràng và thời hạn loại bỏ.

### 19.1. Không tạo overload chỉ khác return type

Như đã nêu, Java không cho overload cùng method signature chỉ khác return type. Đừng cố dùng generic trick hoặc cast để né giới hạn này.

Dùng tên hoặc interface khác trong thời gian chuyển đổi, rồi thống nhất contract sau khi mọi caller đã được cập nhật.

### 19.2. Xác định ranh giới blocking

Nếu cần gọi thư viện blocking từ reactive service, cô lập trong adapter:

~~~java
public Mono<LegacyResult> callLegacy(LegacyCommand command) {
    return Mono.fromCallable(() ->
                    legacyClient.execute(command))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đặt timeout, giới hạn concurrency và metric cho adapter. Không để blocking call chiếm event-loop.

## 20. Backpressure và giới hạn tài nguyên sau khi chuyển sang Flux

Một service cũ trả List<T> thường đã tải toàn bộ dữ liệu trước khi trả cho caller. Khi chuyển sang Flux, caller có thể tiêu thụ từng phần tử, nhưng chỉ khi các tầng dưới thực sự hỗ trợ streaming.

Các câu hỏi cần xác nhận:

- Repository/driver có phát từng hàng hay buffer toàn bộ result?
- Caller có thể xử lý chậm không?
- Query có giữ connection trong suốt thời gian Flux được tiêu thụ không?
- collectList() có làm tăng memory không?
- flatMap có concurrency giới hạn không?
- Client HTTP có hủy subscription khi ngắt kết nối không?

Flux không tự đảm bảo database không buffer. Hành vi thực tế phụ thuộc driver, fetch strategy, query và cách consume.

Với tập kết quả lớn, cân nhắc pagination hoặc stream có giới hạn. Không giữ transaction mở lâu chỉ để truyền một tập dữ liệu rất lớn qua HTTP nếu có phương án phân trang phù hợp.

## 21. Các lỗi thường gặp khi chuyển contract

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ đổi T thành Mono<T> nhưng giữ caller cũ | Caller không thể truy cập thuộc tính của T | Chuyển caller sang map/flatMap |
| Dùng map cho method trả publisher | Tạo Mono<Mono<T>> | Dùng flatMap |
| Gọi block() trong service/controller WebFlux | Chặn event loop và làm mất lợi ích reactive | Trả publisher xuyên suốt |
| Gọi subscribe() trong service | Tách lifecycle, lỗi và context khỏi caller | Trả và nối publisher |
| Chuyển mọi List<T> thành Mono<List<T>> | Buffer toàn bộ dữ liệu, mất streaming | Dùng Flux nếu caller xử lý từng hàng |
| Chuyển mọi empty thành exception | Tìm kiếm không có kết quả bị coi là lỗi | Chỉ dùng switchIfEmpty theo contract |
| Trả Mono.just(null) | Reactor từ chối null | Dùng Mono.empty hoặc justOrEmpty |
| Dùng Optional bên trong Mono | Biểu diễn empty hai lần | Dùng Mono<T> |
| Đoán kết quả ngay khi gọi method | Publisher chưa được thực thi | Kiểm tra qua subscriber/StepVerifier |
| Dùng flatMap không giới hạn | Tăng concurrency, cạn pool hoặc quá tải downstream | Giới hạn concurrency hoặc dùng concatMap |
| Nuốt lỗi bằng onErrorResume thành empty | Che lỗi database thành not-found | Chỉ fallback khi nghiệp vụ cho phép |
| Dùng try/catch quanh lời gọi tạo Mono | Không bắt được lỗi phát khi subscribe | Dùng onErrorMap/onErrorResume/doOnError |
| Giữ @Transactional trên method blocking rồi gọi reactive | Transaction không bao trùm reactive lifecycle | Chuyển contract và boundary sang reactive |
| Gửi email trực tiếp trong transaction | Email không rollback khi DB rollback | Dùng outbox/after-commit strategy |
| Dùng ThreadLocal cho security context | Mất context khi chuyển thread | Dùng Reactor Context/reactive API |
| Chỉ sửa controller mà bỏ qua scheduler/message consumer | Caller cũ vẫn không xử lý publisher | Tìm và chuyển tất cả call site |
| Tạo blocking facade không timeout | Thread có thể chờ vô hạn | Chỉ dùng ở biên imperative và có timeout |
| Dùng Mono.fromCallable rồi gọi JDBC trên event loop | Vẫn blocking | subscribeOn boundedElastic hoặc thay bằng R2DBC |
| Mock entity thay vì Mono/Flux | Test không phản ánh service contract | Mock publisher tương ứng |

## 22. Quy trình chuyển đổi một module service

Một quy trình thực tế giúp thay đổi có kiểm soát:

1. Liệt kê tất cả service method, kiểu trả về và caller.
2. Phân loại kết quả: một hàng, nhiều hàng, optional, boolean, count, command hoặc stream.
3. Xác định repository nào đã dùng R2DBC reactive API.
4. Đổi contract service thành Mono/Flux/Mono<Void> theo cardinality.
5. Chuyển logic gọi service bằng map, flatMap, zip, then hoặc concatMap.
6. Chuyển lỗi đồng bộ sang onError và phân biệt empty với error.
7. Giữ toàn bộ thao tác database trong cùng reactive chain/transaction context.
8. Chuyển controller, message handler, scheduler và event listener.
9. Cô lập caller blocking còn tồn tại trong adapter có timeout và scheduler phù hợp.
10. Chuyển unit test sang StepVerifier và thêm integration test cho database thật.
11. Kiểm tra cancellation, concurrency, backpressure và pool capacity.
12. Xóa subscribe/block bridge không còn cần thiết sau khi mọi caller đã reactive.

### 22.1. Ví dụ chuyển đổi đầy đủ

Hợp đồng cũ:

~~~java
public interface OrderService {
    Order getById(Long id);
    List<Order> findByCustomer(Long customerId);
    Order create(CreateOrderCommand command);
    void cancel(Long id);
}
~~~

Hợp đồng mới:

~~~java
public interface OrderService {
    Mono<Order> getById(Long id);
    Flux<Order> findByCustomer(Long customerId);
    Mono<Order> create(CreateOrderCommand command);
    Mono<Void> cancel(Long id);
}
~~~

Implementation:

~~~java
@Service
public class OrderServiceImpl implements OrderService {

    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderServiceImpl(
            OrderRepository orderRepository,
            CustomerRepository customerRepository) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Override
    public Mono<Order> getById(Long id) {
        return orderRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(id)));
    }

    @Override
    public Flux<Order> findByCustomer(Long customerId) {
        return orderRepository.findByCustomerId(customerId);
    }

    @Override
    @Transactional
    public Mono<Order> create(CreateOrderCommand command) {
        return customerRepository.findById(command.customerId())
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(
                                command.customerId())))
                .flatMap(customer ->
                        orderRepository.save(
                                Order.create(customer, command)));
    }

    @Override
    @Transactional
    public Mono<Void> cancel(Long id) {
        return orderRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(id)))
                .flatMap(order -> {
                    order.cancel();
                    return orderRepository.save(order);
                })
                .then();
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public Mono<OrderResponse> getById(@PathVariable Long id) {
        return orderService.getById(id)
                .map(OrderResponse::from);
    }

    @GetMapping
    public Flux<OrderResponse> findByCustomer(
            @RequestParam Long customerId) {
        return orderService.findByCustomer(customerId)
                .map(OrderResponse::from);
    }

    @PostMapping
    public Mono<ResponseEntity<OrderResponse>> create(
            @RequestBody @Valid CreateOrderRequest request) {
        return orderService.create(request.toCommand())
                .map(OrderResponse::from)
                .map(response ->
                        ResponseEntity
                                .created(URI.create(
                                        "/api/orders/" + response.id()))
                                .body(response));
    }

    @PostMapping("/{id}/cancel")
    public Mono<ResponseEntity<Void>> cancel(@PathVariable Long id) {
        return orderService.cancel(id)
                .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

Ví dụ giả định các repository là reactive, transaction manager là reactive R2DBC transaction manager, và exception handler ánh xạ OrderNotFoundException/CustomerNotFoundException sang HTTP status phù hợp. DTO, entity và query phải được thay bằng kiểu của dự án.

Điểm cần quan sát là không có block() hoặc subscribe() trong service/controller. Publisher được trả xuyên suốt đến WebFlux, và lỗi có thể truyền qua cùng execution chain.

## 23. Ghi nhớ

- Chuyển service sang reactive là thay đổi contract và caller, không chỉ thay kiểu trả về.
- Publisher<T> là abstraction Reactive Streams; Reactor thường dùng Mono<T> cho 0..1 và Flux<T> cho 0..N phần tử.
- Chọn Mono/Flux theo cardinality và cách caller tiêu thụ dữ liệu.
- Mono.empty() biểu diễn không có phần tử; không dùng null hoặc Mono.just(null).
- Chuyển Optional<T> thành Mono<T>, List<T> thành Flux<T> hoặc Mono<List<T>> tùy nhu cầu, void thành Mono<Void>.
- Dùng map cho phép biến đổi đồng bộ và flatMap cho bước trả publisher.
- Dùng zip cho nguồn độc lập cần đủ kết quả, then cho bước chỉ quan tâm hoàn tất và concatMap khi cần thứ tự.
- Publisher thường lazy; gọi method tạo Mono chưa có nghĩa database query đã chạy.
- Không gọi subscribe() hoặc block() trong service/controller reactive.
- Chỉ dùng blocking adapter ở ranh giới imperative được kiểm soát, có timeout và scheduler phù hợp.
- Dùng switchIfEmpty theo quy tắc nghiệp vụ; phân biệt empty với lỗi database.
- Dùng onErrorMap, onErrorResume và doOnError thay cho try/catch quanh publisher.
- Reactive transaction phải bao trùm publisher lifecycle và giữ cùng Reactor Context.
- WebFlux controller có thể trả trực tiếp Mono/Flux; framework quản lý subscription.
- Scheduler, message consumer và event listener cũng là caller cần chuyển contract.
- Dùng StepVerifier để kiểm tra value, empty, error, completion và cancellation.
- Kiểm soát concurrency/backpressure để không làm cạn R2DBC connection pool.
- Java không cho overload chỉ khác return type; thay đổi interface cần kế hoạch tương thích cho caller.

