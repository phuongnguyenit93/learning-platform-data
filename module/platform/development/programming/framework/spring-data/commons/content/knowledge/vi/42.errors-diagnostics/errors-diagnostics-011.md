# Stream bị đóng sớm hoặc reactive mất phạm vi ngữ cảnh

## 1. Đối tượng còn tồn tại không có nghĩa tài nguyên còn hợp lệ

Một service trả về `Stream<Customer>` nhưng controller chỉ đọc được khi đang debug. Một API reactive tạo được `Mono`, nhưng lúc thực thi lại thiếu tenant, auditor hoặc transaction. Hai tình huống có điểm chung: công việc thực sự diễn ra ở thời điểm hoặc phạm vi khác với nơi mã được viết.

Tuy nhiên, cần phân biệt hai mô hình:

- **Java Stream từ repository imperative** có thể gắn với cursor, connection hoặc session. Việc tiêu thụ cần nằm trong vòng đời tài nguyên và giao dịch phù hợp.
- **Reactive publisher** như `Mono` hoặc `Flux` mô tả công việc được thực hiện khi subscribe. Transaction reactive và ngữ cảnh nghiệp vụ phải thuộc pipeline/subscription mà công việc sử dụng.

Spring Data Commons cung cấp các abstraction repository dùng chung, nhưng không bảo đảm mọi store hỗ trợ streaming hoặc reactive transaction giống nhau. Cần xác định Spring Data module, driver và transaction manager thực tế trước khi suy luận về lỗi.

## 2. Nhận diện đúng triệu chứng

| Triệu chứng | Nguyên nhân cần phân biệt |
| --- | --- |
| Stream báo đã được sử dụng hoặc đóng | Stream đã có terminal operation, đã close hoặc bị tái sử dụng |
| Cursor, result set hoặc connection không còn dùng được | Phạm vi tài nguyên kết thúc, timeout, lỗi mạng hoặc đóng bởi thành phần khác |
| Lỗi truy cập quan hệ lazy | Entity cần persistence context ở thời điểm truy cập, không nhất thiết stream Java đã bị close |
| Thiếu tenant hoặc auditor trong reactive | Đọc sai nguồn ngữ cảnh, đọc quá sớm hoặc công việc tách khỏi subscription |
| Không có transaction reactive như mong muốn | Sai manager, sai ranh giới pipeline hoặc tạo một subscription riêng |
| Không có query thực thi dù method đã được gọi | Publisher chưa được subscribe hoặc nhánh thực thi không được ghép vào kết quả |
| Query chạy hai lần | Nhiều subscription, retry/repeat hoặc nhiều nhánh kích hoạt lại nguồn |

Không phải mọi lỗi cursor đều do `try-with-resources` đóng sớm. Cần đối chiếu thời điểm mở/đóng, timeout và lỗi driver. Tương tự, đổi thread không tự chứng minh Reactor Context đã mất.

## 3. Java Stream có nhiều mốc vòng đời khác nhau

### 3.1. Nhận stream, duyệt stream và đóng stream

Một phương thức repository có thể trả một stream mà phần dữ liệu còn lại được đọc khi duyệt. Tùy module, một phần công việc cũng có thể bắt đầu ngay khi gọi method.

```text
Gọi repository
    -> nhận Stream
    -> thêm filter/map
    -> terminal operation tiêu thụ dữ liệu
    -> đóng Stream
```

Các thao tác trung gian không đồng nghĩa toàn bộ kết quả đã được materialize. Các terminal operation cũng không tự bảo đảm stream tài nguyên được đóng.

Ví dụ, `findFirst()` có thể dừng sau một phần kết quả. Tài nguyên phía dưới vẫn cần được giải phóng theo hợp đồng của stream. Dùng `try-with-resources` để xác định rõ chủ sở hữu thay vì chờ garbage collector.

### 3.2. Bẫy trả stream khỏi khối `try`

```java
public Stream<Customer> openCustomers(String tenantId) {
    try (Stream<Customer> stream = customers.streamByTenantId(tenantId)) {
        return stream;
    }
}
```

Khi method trả về, khối `try` đã đóng stream. Caller nhận đúng một tham chiếu Java, nhưng tham chiếu đó không còn đại diện cho nguồn có thể tiêu thụ hợp lệ.

Xóa `try` có thể tránh lỗi đóng ngay tại đây nhưng lại làm trách nhiệm đóng không rõ. Cần sửa hợp đồng sở hữu, không chỉ xóa câu lệnh gây triệu chứng.

### 3.3. Một stream không phải nguồn có thể chạy lại tùy ý

```java
long count = stream.count();
stream.forEach(this::process);
```

Stream đã được tiêu thụ ở terminal operation đầu tiên không được dùng lại theo cách trên. Nếu cần nhiều kết quả, có thể tính trong một lần duyệt, materialize dữ liệu có giới hạn hoặc thực hiện truy vấn riêng theo yêu cầu.

Retry trên cùng một stream đã được sử dụng cũng không tạo ra nguồn mới. Việc mở lại phải thuộc một lần thử mới có vòng đời tài nguyên phù hợp.

## 4. Transaction imperative có thể kết thúc trước khi caller duyệt

Ví dụ sau thường có hợp đồng không đầy đủ khi method tự mở transaction:

```java
@Transactional(readOnly = true)
public Stream<Customer> customersForReport(String tenantId) {
    return customers.streamByTenantId(tenantId);
}
```

Trong quản lý transaction imperative qua proxy, transaction do method mở thường hoàn tất khi method trả về. Controller hoặc serializer tiêu thụ stream sau đó có thể đã ở ngoài phạm vi tài nguyên cần thiết.

Nếu có transaction ngoài bao quanh cả lời gọi và việc tiêu thụ, kết quả có thể khác. Điểm cần xác định là transaction nào thực sự sở hữu tài nguyên, không chỉ method nào có annotation.

Một số yếu tố khác cần kiểm tra:

- Lời gọi có đi qua transaction proxy không?
- Có gọi nội bộ trong cùng đối tượng khiến annotation không được áp dụng theo cơ chế proxy thông thường không?
- Transaction manager được chọn có quản lý đúng tài nguyên của repository không?
- Getter hoặc serializer có truy cập dữ liệu lazy sau khi method đã trả về không?

`readOnly = true` không kéo dài transaction đến khi caller đóng stream. Nó thể hiện mục đích và có thể được manager/provider sử dụng theo khả năng tương ứng.

## 5. Tiêu thụ trong phạm vi sở hữu rồi trả dữ liệu độc lập

Ví dụ sau dành cho một ứng dụng JPA có repository streaming được hỗ trợ. Mã dùng Java có `record` và `Stream.toList()`, lược bỏ import cùng entity mapping:

```java
record CustomerView(String id, String displayName) {
}

interface CustomerStreamRepository extends Repository<Customer, String> {
    Stream<Customer> streamByTenantId(String tenantId);
}
```

```java
@Service
class CustomerBatchReader {

    private final CustomerStreamRepository customers;

    CustomerBatchReader(CustomerStreamRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public List<CustomerView> readFirstBatch(String tenantId) {
        try (Stream<Customer> stream = customers.streamByTenantId(tenantId)) {
            return stream.limit(100)
                .map(customer -> new CustomerView(
                    customer.getId(),
                    customer.getDisplayName()
                ))
                .toList();
        }
    }
}
```

Giả định method được gọi qua bean proxy và transaction manager đúng. Dữ liệu được đọc và chuyển thành các giá trị DTO trong phạm vi method; stream được đóng trước khi method kết thúc.

Giới hạn Java `limit(100)` trong ví dụ không cam kết datastore chỉ xử lý 100 bản ghi. Trong ứng dụng thực, nếu cần một lô có thứ tự và giới hạn tại store, nên chọn query/phân trang phù hợp với module rồi xác nhận query thực tế.

DTO cũng chỉ độc lập nếu các field đã là giá trị cần thiết. Đặt nguyên một entity hoặc lazy collection vào bên trong DTO không tự loại bỏ phụ thuộc persistence context.

Nếu thiết kế cố ý trả stream ra ngoài, hợp đồng phải chỉ rõ caller giữ tài nguyên nào, transaction nào bao quanh việc duyệt và ai đóng stream ở mọi đường thành công/lỗi. Đây là một API quản lý tài nguyên, không chỉ một kiểu trả về tiện dụng.

## 6. Thread khác không tự giữ được tài nguyên imperative

```java
try (Stream<Customer> stream = customers.streamByTenantId(tenantId)) {
    stream.forEach(customer ->
        executor.submit(() -> process(customer))
    );
}
```

Các tác vụ có thể chưa chạy xong khi khối `try` kết thúc. Nếu `process()` truy cập quan hệ lazy hoặc tài nguyên gắn với transaction của thread gọi, lỗi có thể chỉ xuất hiện ngẫu nhiên theo lịch thực thi.

Không mặc định connection, cursor hoặc persistence context là thread-safe. Trong mô hình imperative phổ biến, transaction context gắn với thread và không tự lan sang executor.

Khi cần song song, có thể đọc ID hoặc DTO độc lập rồi để mỗi tác vụ truy cập dữ liệu trong phạm vi riêng nếu cần. Phải giới hạn số tác vụ theo tài nguyên và giữ rõ điều kiện nghiệp vụ. Đổi sang `.parallel()` trên stream repository không phải cách sửa chung cho vấn đề này.

## 7. Reactive có ba thời điểm cần tách biệt

| Thời điểm | Điều đang xảy ra |
| --- | --- |
| Assembly | Xây dựng mô tả pipeline và các operator |
| Subscription | Subscriber bắt đầu thực hiện nguồn và cung cấp ngữ cảnh tương ứng |
| Termination hoặc cancellation | Pipeline hoàn tất, lỗi hoặc bị hủy; tài nguyên cần được xử lý theo cơ chế quản lý |

Một giá trị lấy ở assembly time có thể không còn đúng với subscriber thực sự sử dụng pipeline. Đặc biệt, một pipeline được tái sử dụng cho nhiều request không nên chụp tenant hoặc actor của request đầu tiên vào một field dùng chung.

### Reactor Context không phải ThreadLocal

Trong Reactor, Context gắn với subscription và được truyền qua chuỗi operator theo quy tắc của nó. Việc chuyển scheduler bằng `publishOn` hoặc `subscribeOn` trong một pipeline Reactor thông thường không tự làm Context biến mất.

Nếu một giá trị chỉ được đặt vào thread-local imperative, việc xử lý trên thread khác có thể không nhìn thấy nó. Đây là khác biệt giữa hai nguồn ngữ cảnh, không phải bằng chứng rằng Reactor Context bị scheduler xóa.

Các cơ chế tích hợp có thể hỗ trợ truyền ngữ cảnh trong những cấu hình nhất định, nhưng không nên mặc định mọi thread-local, thư viện hoặc executor đều được tự động nối vào Reactor Context.

## 8. Đọc ngữ cảnh khi subscribe bằng `deferContextual`

Ví dụ sau dùng một repository reactive của module hỗ trợ derived query tương ứng:

```java
interface ReactiveCustomerRepository
        extends ReactiveCrudRepository<Customer, String> {

    Mono<Customer> findByIdAndTenantId(String id, String tenantId);
}
```

```java
@Service
class ReactiveCustomerReader {

    private final ReactiveCustomerRepository customers;

    ReactiveCustomerReader(ReactiveCustomerRepository customers) {
        this.customers = customers;
    }

    public Mono<CustomerView> loadView(String id) {
        return Mono.deferContextual(context -> {
            String tenantId = context.getOrDefault("tenantId", "");

            if (tenantId.isBlank()) {
                return Mono.error(
                    new IllegalStateException("Thiếu tenant trong ngữ cảnh")
                );
            }

            return customers.findByIdAndTenantId(id, tenantId)
                .map(customer -> new CustomerView(
                    customer.getId(),
                    customer.getDisplayName()
                ));
        });
    }
}
```

Caller cung cấp ngữ cảnh cho subscription:

```java
return reader.loadView(customerId)
    .contextWrite(context -> context.put("tenantId", authenticatedTenant));
```

`authenticatedTenant` phải đến từ ngữ cảnh đã được xác thực/ủy quyền theo thiết kế ứng dụng. Không dùng một tenant tùy ý do client gửi để thay thế kiểm tra quyền.

Ví dụ thiếu tenant thì trả lỗi rõ ràng. Không nên tự chuyển sang query không có tenant chỉ để pipeline chạy được.

### Vị trí `contextWrite` có ý nghĩa

Context được cung cấp cho các operator upstream theo phạm vi subscription tương ứng. Nó không phải một biến toàn cục mà mọi operator ở mọi nhánh đều thấy.

```java
Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
    )
    .contextWrite(context -> context.put("tenantId", "tenant-a"));
```

Ví dụ này đặt giá trị cho nguồn đọc ở phía upstream. Nếu đặt phần ghi context trong một nhánh con, không nên suy ra nó tự thay đổi context của toàn bộ pipeline bên ngoài.

Khi chẩn đoán, vẽ vị trí nguồn đọc context, vị trí ghi context và các nhánh được tạo. Không chỉ kiểm tra xem trong mã có xuất hiện `contextWrite` hay không.

## 9. `subscribe()` thủ công có thể tách công việc khỏi phạm vi dự kiến

Mẫu dễ sai:

```java
public Mono<Void> updateCustomer(Customer customer) {
    customers.save(customer).subscribe();
    return Mono.empty();
}
```

Caller nhận một publisher đã hoàn tất độc lập với thao tác lưu bên trong. Lỗi, cancellation, transaction và ngữ cảnh của thao tác lưu không còn được ghép vào hợp đồng mà caller đang chờ theo cách mong muốn.

Nếu framework ở biên ứng dụng quản lý subscription, service nên trả pipeline để công việc được compose:

```java
public Mono<Void> updateCustomer(Customer customer) {
    return customers.save(customer).then();
}
```

Điều này không tự bổ sung kiểm tra tenant hoặc transaction, nhưng giữ thao tác lưu trong cùng đường kết quả và lỗi mà caller quan sát.

Những nơi cần kiểm tra tương tự gồm callback tạo subscription riêng, `CompletableFuture` chạy trên executor ngoài, custom publisher hoặc thư viện callback chưa được tích hợp ngữ cảnh. Không khẳng định mọi adapter đều mất context; cần xem chính đoạn nối giữa các mô hình.

## 10. Transaction reactive phải bao quanh pipeline thực sự chạy

Với reactive transaction manager phù hợp, một phương thức trả publisher có thể được quản lý transaction theo vòng đời reactive. Không áp nguyên kết luận “method trả về là transaction kết thúc” của mô hình imperative cho trường hợp này.

Một cấu trúc dùng `TransactionalOperator` có thể là:

```java
return Mono.deferContextual(context -> {
    String tenantId = context.get("tenantId");

    Mono<Customer> work = customers.findByIdAndTenantId(id, tenantId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Không tìm thấy khách hàng")
        ))
        .flatMap(customer -> {
            customer.setDisplayName(newName);
            return customers.save(customer);
        });

    return transactionalOperator.transactional(work);
});
```

Ví dụ lược bỏ phần khai báo service và giả định `Customer` mutable, repository cùng operator dùng đúng store, tenant đã được kiểm tra ở biên phù hợp. Không phải mọi datastore hoặc deployment đều hỗ trợ cùng phạm vi transaction.

Nếu lấy `work` ra để gọi `subscribe()` riêng, phạm vi transaction ở pipeline khác không tự bao phủ nó. Nếu dùng manager imperative cho một đường truy cập reactive hoặc ngược lại, annotation cùng tên cũng không khắc phục được sự không tương thích.

Cancellation và lỗi cần được xét theo semantics của operator, manager và driver. Không dùng một `onNext` hay log “đã gọi save” làm bằng chứng chung rằng toàn bộ transaction đã commit.

Khi retry, cần bảo đảm lần thử mới thực sự đọc lại và có phạm vi transaction phù hợp, thay vì tiếp tục một phạm vi đã lỗi hoặc tái dùng mutable state từ lần trước. Tác dụng phụ ngoài store vẫn cần chính sách idempotency riêng.

## 11. Auditing có thể mất actor dù query vẫn chạy

Nếu code reactive lấy actor từ một thread-local chỉ được đặt ở thread nhận request, auditing có thể không thấy actor khi thực thi trên thread khác. Query vẫn có thể chạy nên triệu chứng đôi khi chỉ là field audit thiếu hoặc sai.

Với module hỗ trợ auditing reactive, có thể cung cấp `ReactiveAuditorAware` theo nguồn ngữ cảnh phù hợp:

```java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> Mono.deferContextual(context ->
        Mono.justOrEmpty(context.<String>getOrEmpty("actorId"))
    );
}
```

Ví dụ dùng `org.springframework.data.domain.ReactiveAuditorAware`, giả định field auditor là `String`. Module phải được bật auditing và đi qua đường lifecycle hỗ trợ; một bean riêng chưa đủ để mọi store tự dùng nó.

Ví dụ trả rỗng khi actor không có trong context. Nếu nghiệp vụ bắt buộc actor, cần đặt chính sách lỗi hoặc chủ thể kỹ thuật rõ ràng cho các tác vụ tương ứng. Không âm thầm gán một người dùng mặc định cho mọi request.

Nếu ứng dụng dùng hệ thống bảo mật reactive, nguồn actor nên được tích hợp với ngữ cảnh bảo mật tương ứng. Dùng một key Context tùy chỉnh chỉ là ví dụ cơ chế, không tự xác nhận danh tính.

## 12. Nối repository imperative sang reactive cần giữ phạm vi đọc riêng

Một mẫu nguy hiểm là:

```java
public Flux<Customer> loadCustomers(String tenantId) {
    try (Stream<Customer> stream = customers.streamByTenantId(tenantId)) {
        return Flux.fromStream(stream);
    }
}
```

Khi subscriber bắt đầu duyệt, stream đã bị đóng ở method trên. Đổi sang một supplier có thể giúp tạo nguồn cho từng subscription, nhưng vẫn chưa tự bảo đảm transaction imperative bao quanh toàn bộ việc duyệt.

Nếu cần tích hợp một thành phần blocking có sẵn, một hướng dễ kiểm soát là materialize một lô DTO có giới hạn trong service imperative, rồi đưa kết quả độc lập vào pipeline:

```java
return Mono.fromCallable(() ->
        blockingReader.readFirstBatch(tenantId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .flatMapMany(Flux::fromIterable);
```

`blockingReader` ở đây là bean có ranh giới transaction imperative phù hợp, tiêu thụ và đóng stream bên trong method, như ví dụ trước. Toàn bộ dữ liệu của lô phải độc lập với lazy resource khi trả về.

Scheduler này chuyển công việc blocking sang nơi phù hợp hơn để thực thi, không biến driver blocking thành non-blocking. Cần giới hạn kích thước lô và mức đồng thời theo pool/tài nguyên.

Tenant được truyền tường minh trong ví dụ. Nếu logic blocking còn cần actor hoặc ngữ cảnh khác, phải thiết kế việc chuyển thông tin đó có chủ đích; Reactor Context không tự trở thành mọi thread-local mà service imperative sử dụng.

## 13. Cache và nhiều subscription có thể làm ngữ cảnh sai mà không ném lỗi

Một publisher cold thường thực hiện lại công việc cho mỗi subscription. Nếu nó đọc tenant qua `deferContextual`, các subscriber có thể cung cấp tenant riêng.

Nếu cache một publisher hoặc kết quả phụ thuộc tenant rồi tái sử dụng toàn cục, subscriber sau có thể nhận dữ liệu của subscriber trước. Đây có thể là lỗi cách ly dữ liệu dù pipeline không báo “mất context”.

Cần kiểm tra:

- Publisher được tạo cho mỗi request hay lưu trong một field dùng chung?
- Có `cache`, replay hoặc chia sẻ nguồn không?
- Cache key có bao phủ tenant, quyền và các tham số liên quan không?
- Kết quả đang được tái sử dụng hay công việc thực sự được thực hiện lại?

Tương tự, cache một `Stream` đã mở không tạo nguồn dữ liệu tái sử dụng an toàn. Cache giá trị đã materialize với phạm vi đúng và chia sẻ tài nguyên đang mở là hai thiết kế khác nhau.

## 14. Cách truy vết vòng đời và phạm vi

### Đối với stream imperative

Ghi nhận nơi mở stream, nơi thực hiện terminal operation, nơi đóng stream và transaction thực sự bao quanh từng mốc. Đối chiếu thread nếu có executor hoặc xử lý song song.

Nếu lỗi xuất hiện trong serializer, kiểm tra getter nào kích hoạt truy cập lazy. Nếu lỗi là cursor timeout, cần xem thời gian giữ nguồn, tốc độ tiêu thụ và cấu hình driver/store thay vì chỉ tìm câu lệnh `close()`.

### Đối với reactive

Đánh dấu assembly, subscription, nguồn đọc context, vị trí `contextWrite` và mọi subscription thủ công. Các hook như `doOnSubscribe`, `doOnError` hoặc `doFinally` có thể giúp quan sát đường chạy.

`doFinally` cho biết một dạng kết thúc của chuỗi tại vị trí được gắn, không tự chứng minh commit thành công. Nếu cần đọc context trong instrumentation, đặt việc đọc ở nguồn có khả năng truy cập Context, chẳng hạn bên trong `deferContextual`.

Không chỉ log tên thread rồi suy ra ngữ cảnh. Cùng thread chưa chắc cùng subscriber; khác thread chưa chắc mất Reactor Context. Nên ghi định danh tương quan và trạng thái ngữ cảnh tối thiểu, tránh đưa thông tin xác thực hoặc dữ liệu cá nhân đầy đủ vào log.

## 15. Kiểm thử đường thành công, lỗi và hủy

### 15.1. Stream cần được đóng ở mọi đường kết thúc

Các tình huống hữu ích gồm:

- Duyệt hết dữ liệu.
- Dừng sớm bằng thao tác như `findFirst()`.
- Exception trong hàm xử lý phần tử.
- Caller trả về trước khi công việc ở executor hoàn tất.
- Cố tái dùng stream sau terminal operation.

Có thể dùng nguồn test với callback đóng hoặc spy để xác nhận trách nhiệm close. Test bằng stream trong bộ nhớ chỉ chứng minh cấu trúc quản lý nguồn của fixture; cần integration test để kiểm tra transaction, cursor và lazy access của module thực tế.

### 15.2. Reactive cần được subscribe trong test

Ví dụ dùng Reactor Test, giả định fixture có khách hàng `c-a` thuộc `tenant-a`:

```java
StepVerifier.create(
        reader.loadView("c-a")
            .contextWrite(context -> context.put("tenantId", "tenant-a"))
    )
    .expectNextMatches(view -> view.id().equals("c-a"))
    .verifyComplete();
```

```java
StepVerifier.create(reader.loadView("c-a"))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().contains("Thiếu tenant")
    )
    .verify();
```

Ví dụ đầu cần fixture và repository/adapter tương ứng. Ví dụ sau kiểm tra chính sách thiếu ngữ cảnh của service, không tự chứng minh transaction của datastore.

Nên kiểm thử cùng một pipeline được subscribe với các tenant khác nhau khi thiết kế cho phép tái sử dụng. Chẳng hạn, khách hàng thuộc tenant A không được xuất hiện khi subscriber cung cấp tenant B. Test này giúp phát hiện việc chụp giá trị ở assembly time hoặc cache sai scope.

Với luồng giữ tài nguyên, bổ sung tình huống cancellation và lỗi giữa chừng, rồi xác nhận giải phóng theo cơ chế driver/transaction manager. Không dùng thời gian chờ tùy ý làm bằng chứng duy nhất rằng tác vụ đã kết thúc.

## 16. Những cách sửa chỉ chuyển lỗi đi nơi khác

| Cách sửa | Điều vẫn chưa được giải quyết |
| --- | --- |
| Xóa `try-with-resources` để stream không đóng sớm | Ai đóng tài nguyên khi thành công, lỗi hoặc dừng sớm? |
| Thêm `@Transactional` lên method trả stream | Transaction có còn mở lúc caller duyệt không? |
| Thêm `.parallel()` hoặc executor | Tài nguyên và transaction có dùng được giữa thread không? |
| Gọi `subscribe()` để “chắc chắn query chạy” | Caller có còn quan sát đúng lỗi, context và completion không? |
| Đổi mọi thao tác sang `block()` | Có phá mô hình reactive, giới hạn thread và ranh giới transaction không? |
| Bỏ `publishOn` vì thấy thread thay đổi | Nguồn ngữ cảnh thật sự là Reactor Context hay thread-local? |
| Khi thiếu tenant thì dùng query không lọc | Cách ly dữ liệu đã bị phá vỡ |
| Cache publisher để tránh chạy lại | Kết quả có phụ thuộc tenant, actor hoặc quyền không? |

Cách sửa phải làm rõ chủ sở hữu tài nguyên và subscription, không chỉ khiến một lần gọi hết ném exception.

## 17. Bài tập vận dụng

Một service JPA trả `Stream<Customer>` từ bên trong khối `try`. Controller chuyển nó thành `Flux` và subscribe sau khi method kết thúc. Một service reactive khác lấy tenant từ thread-local, gọi `save().subscribe()` bên trong method có annotation transaction, rồi trả `Mono.empty()`.

Hãy phân tích:

1. Stream bị đóng tại mốc nào và transaction nào thực sự bao quanh việc duyệt?
2. Vì sao chuyển stream sang `Flux` không tự sửa vòng đời tài nguyên?
3. Công việc lưu reactive đã bị tách khỏi kết quả trả cho caller ở đâu?
4. Cách đọc tenant tại subscription time và giữ chính sách khi thiếu tenant.
5. Cách kiểm thử lỗi, cancellation, actor auditing và việc không trả dữ liệu chéo tenant.

Một phương án tốt cần nêu rõ cả đường thành công lẫn đường thất bại. Chỉ thêm annotation hoặc đổi scheduler chưa đủ nếu phạm vi sở hữu vẫn không rõ.

## 18. Điểm cần nhớ

Stream Java có thể sống lâu hơn tài nguyên phía dưới, nên việc tiêu thụ và đóng phải nằm trong phạm vi truy cập store phù hợp. Reactive publisher cần được compose vào subscription mà caller quản lý, với ngữ cảnh được đọc tại thời điểm và vị trí đúng.

Reactor Context khác thread-local, transaction reactive khác transaction imperative và không phải mọi đổi thread đều làm mất ngữ cảnh. Chẩn đoán đúng cần nối vòng đời tài nguyên, pipeline và khả năng của module/datastore thực tế trước khi thay đổi cách xử lý.
