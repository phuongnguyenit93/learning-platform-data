# Đưa tác vụ chặn ra khỏi luồng xử lý phản ứng

Trong Spring Messaging với RSocket, handler thường trả về **Mono** hoặc **Flux** để mô tả kết quả sẽ đến bất đồng bộ. Pipeline phản ứng có thể xử lý nhiều request mà không cần giữ một thread riêng trong suốt thời gian chờ I/O. Lợi ích này mất đi nếu handler gọi trực tiếp một API chặn như JDBC/JPA đồng bộ, RestTemplate, đọc file đồng bộ hoặc một SDK cũ.

Cách xử lý đúng là cô lập phần blocking trên scheduler dành cho tác vụ chặn, thường là **Schedulers.boundedElastic()**, rồi tiếp tục trả về publisher cho Spring quản lý. Điều này giữ cho các thread phục vụ pipeline và I/O không phải đứng chờ một lời gọi đồng bộ.

## 1. Tác vụ chặn ảnh hưởng đến pipeline RSocket như thế nào?

Một thao tác blocking giữ thread hiện tại cho đến khi thao tác hoàn tất. Trong khi thread đó đang chờ, nó không thể xử lý công việc khác. Với hệ thống phản ứng, một số thread có thể phục vụ nhiều kết nối và nhiều tín hiệu. Nếu một handler chặn thread đang chạy pipeline, các request khác có thể bị chậm theo.

Ví dụ, một handler nhận request RSocket rồi gọi dịch vụ JDBC đồng bộ:

~~~java
@MessageMapping("customers.find")
Mono<Customer> find(CustomerRequest request) {
    Customer customer = jdbcCustomerService.findById(request.customerId());
    return Mono.just(customer);
}
~~~

Lời gọi **findById** chạy ngay khi phương thức handler được gọi. Publisher chỉ được tạo sau khi truy vấn đã hoàn tất. Vì vậy, việc trả về **Mono** ở cuối phương thức không làm cho truy vấn trở thành non-blocking.

Hậu quả có thể gồm:

- Thread đang xử lý request bị giữ trong suốt thời gian chờ database hoặc dịch vụ bên ngoài.
- Độ trễ tăng khi số request đồng thời tăng.
- Thread pool hoặc hàng đợi tích lũy công việc, làm hệ thống giảm thông lượng.
- Một dịch vụ chậm có thể gây ảnh hưởng dây chuyền đến nhiều request khác.
- Hệ thống mất lợi ích về khả năng mở rộng mà mô hình reactive cung cấp.

Không nên giả định mọi handler RSocket luôn chạy trên một loại thread cố định. Thread thực tế phụ thuộc transport, cấu hình và vị trí scheduler trong pipeline. Nguyên tắc cần giữ là: không thực hiện tác vụ blocking trên thread đang phục vụ luồng xử lý reactive hoặc I/O.

## 2. Nhận diện tác vụ blocking và non-blocking

Các thao tác thường có tính blocking:

- JDBC, JPA/Hibernate đồng bộ và các repository trả kết quả trực tiếp.
- RestTemplate hoặc HTTP client đồng bộ.
- Đọc/ghi file bằng API đồng bộ như **Files.readString**.
- Gọi SDK cũ chỉ cung cấp phương thức đồng bộ.
- Chờ bằng **Thread.sleep**, **Future.get** hoặc **CountDownLatch.await**.
- Gọi tiến trình ngoài rồi chờ kết quả.
- Chờ lock hoặc tài nguyên đồng bộ trong thời gian không xác định.

Các API thường được thiết kế theo hướng non-blocking:

- WebClient với Reactor Netty.
- R2DBC và reactive repository.
- Reactor Netty hoặc RSocket client reactive.
- Các API trả về **Mono** hoặc **Flux** và không chặn thread khi chờ I/O.

Cần phân biệt I/O blocking với tính toán CPU. Một phép tính mã hóa hoặc xử lý dữ liệu nặng có thể tiêu tốn CPU nhưng không nhất thiết chờ I/O. **boundedElastic** dành cho tác vụ blocking; **parallel** dành cho công việc CPU-bound ngắn và không blocking.

Nếu có thể thay thư viện blocking bằng một driver hoặc client non-blocking phù hợp, đó thường là giải pháp tốt hơn về lâu dài. Offload là cách tích hợp an toàn hơn khi chưa thể thay thế API đồng bộ.

## 3. Mẫu chuẩn: Mono.fromCallable kết hợp subscribeOn

Reactor cung cấp **Mono.fromCallable** để trì hoãn việc gọi một hàm đồng bộ cho đến khi publisher được subscribe. Kết hợp nó với **subscribeOn(Schedulers.boundedElastic())** để chạy lời gọi đó trên scheduler dành cho blocking.

~~~java
Mono<Customer> customerMono = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Điều quan trọng là lời gọi blocking nằm bên trong **fromCallable**. Nó chưa chạy khi tạo publisher; nó chạy khi có subscription và được scheduler chỉ định thực thi.

Ví dụ trong một RSocket controller:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class CustomerRSocketController {

    private final LegacyCustomerService customerService;

    CustomerRSocketController(LegacyCustomerService customerService) {
        this.customerService = customerService;
    }

    @MessageMapping("customers.find")
    Mono<CustomerView> find(CustomerRequest request) {
        return Mono.fromCallable(
                () -> customerService.findById(request.customerId())
            )
            .subscribeOn(Schedulers.boundedElastic())
            .map(CustomerView::from);
    }
}

record CustomerRequest(String customerId) {}

record CustomerView(String id, String displayName) {
    static CustomerView from(Customer customer) {
        return new CustomerView(customer.id(), customer.displayName());
    }
}
~~~

Trong ví dụ này, **customerService.findById** vẫn là API đồng bộ. Reactor thực thi lời gọi trên bounded elastic worker. Khi kết quả có mặt, các bước tiếp theo trong pipeline tiếp tục xử lý và Spring gửi kết quả qua RSocket.

Một số điểm cần nhớ:

1. **fromCallable** giúp trì hoãn lời gọi và chuyển exception thành tín hiệu lỗi của publisher.
2. **subscribeOn** đặt quá trình subscribe và thực thi source trên scheduler được chọn.
3. Handler vẫn trả về **Mono**. Không tự gọi subscribe hoặc block trong handler.
4. Nếu hàm đồng bộ trả về null, **Mono.fromCallable** phát ra Mono rỗng. Nếu null là trạng thái không hợp lệ, hãy kiểm tra và phát sinh lỗi rõ ràng.
5. Chỉ bọc đúng phần blocking. Các bước reactive còn lại nên giữ nguyên tính non-blocking.

Với thao tác blocking không trả về giá trị, có thể dùng **Mono.fromRunnable**:

~~~java
Mono<Void> saveAuditRecord(AuditRecord record) {
    return Mono.fromRunnable(() -> legacyAuditClient.save(record))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Nếu thao tác có thể phát sinh exception, exception đó sẽ trở thành tín hiệu onError và có thể được xử lý bằng các operator như **onErrorMap** hoặc **onErrorResume**.

## 4. Vì sao subscribeOn phù hợp hơn publishOn cho source blocking?

Hai operator đều liên quan đến scheduler nhưng tác động ở những vị trí khác nhau.

- **subscribeOn(scheduler)** điều khiển scheduler dùng để subscribe source. Với source blocking như **Mono.fromCallable**, nó khiến callable được thực thi trên scheduler đó.
- **publishOn(scheduler)** chuyển việc xử lý các tín hiệu và operator nằm phía sau nó sang scheduler được chỉ định. Nó không tự di chuyển một lời gọi blocking đã chạy trước vị trí publishOn.

Ví dụ sau không an toàn:

~~~java
Mono<Customer> wrong = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .publishOn(Schedulers.boundedElastic());
~~~

Source callable có thể chạy trên thread subscribe ban đầu. **publishOn** nằm sau source nên không bảo vệ lời gọi JDBC.

Mẫu phù hợp:

~~~java
Mono<Customer> correct = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

**publishOn** vẫn hữu ích khi muốn chuyển các bước phía sau một điểm cụ thể. Ví dụ, nếu cần chạy một phép biến đổi CPU-bound sau khi đã nhận kết quả, có thể chuyển sang **Schedulers.parallel()** tại vị trí thích hợp:

~~~java
Mono<Result> result = Mono
    .fromCallable(() -> blockingClient.load(id))
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::computeResult);
~~~

Trong pipeline này, lời gọi blocking chạy trên bounded elastic; phép tính phía sau publishOn chạy trên parallel. Không chuyển toàn bộ pipeline sang một scheduler chỉ vì một bước có tính blocking.

## 5. Tránh gọi blocking trước khi tạo publisher

Một lỗi thường gặp là đặt lời gọi blocking làm đối số của **Mono.just**:

~~~java
Mono<Customer> wrong = Mono.just(
    jdbcCustomerService.findById(customerId)
);
~~~

Java đánh giá đối số trước khi gọi **Mono.just**, vì vậy truy vấn đã chạy ngay trên thread hiện tại. Publisher không thể trì hoãn một lời gọi đã xảy ra.

Hãy dùng:

~~~java
Mono<Customer> correct = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Một lỗi khác là gọi **block()** trong handler:

~~~java
@MessageMapping("customers.find")
Mono<Customer> wrong(CustomerRequest request) {
    Customer customer = customerService.findById(request.customerId());
    return Mono.just(customer);
}
~~~

Cách viết đúng là trả về publisher chứa lời gọi đồng bộ đã được offload:

~~~java
@MessageMapping("customers.find")
Mono<Customer> find(CustomerRequest request) {
    return Mono.fromCallable(
            () -> customerService.findById(request.customerId())
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Trong controller reactive, tránh các thao tác như **block()**, **blockOptional()**, **toIterable()**, **toStream()** và việc gọi **subscribe()** thủ công để lấy kết quả. Những thao tác này có thể làm mất tính bất đồng bộ, khiến handler kết thúc sai thời điểm hoặc làm đứt luồng truyền lỗi và cancellation.

Spring quản lý subscription cho publisher mà handler trả về. Handler nên mô tả công việc bằng **Mono** hoặc **Flux**, sau đó trả publisher đó cho framework.

## 6. Offload tác vụ blocking trong Flux và luồng nhiều phần tử

Nếu một request cần xử lý nhiều phần tử bằng một API đồng bộ, cần offload từng thao tác và giới hạn số tác vụ chạy đồng thời.

~~~java
Flux<Product> products = Flux.fromIterable(productIds)
    .flatMap(
        id -> Mono.fromCallable(() -> blockingProductClient.load(id))
            .subscribeOn(Schedulers.boundedElastic()),
        16
    );
~~~

Tham số **16** giới hạn số inner publisher được flatMap subscribe đồng thời trong ví dụ này. Giới hạn concurrency giúp tránh tạo quá nhiều lời gọi blocking cùng lúc khi danh sách đầu vào lớn.

Nếu API blocking trả về cả một collection, có thể trì hoãn việc tải collection rồi chuyển nó thành Flux:

~~~java
Flux<Product> products = Mono
    .fromCallable(() -> legacyProductClient.loadAll())
    .subscribeOn(Schedulers.boundedElastic())
    .flatMapMany(Flux::fromIterable);
~~~

Nếu chính thao tác duyệt iterator cũng blocking, cần kiểm tra nơi việc duyệt diễn ra và bảo đảm toàn bộ phần blocking được thực thi trên scheduler phù hợp. Không phải mọi API trả về **Iterable** đều chỉ tốn thời gian ở bước lấy collection; một số iterator thực hiện I/O trong mỗi lần next.

Backpressure giúp điều tiết việc phát và tiêu thụ tín hiệu trong pipeline, nhưng không tự biến API blocking thành non-blocking. Hãy kết hợp backpressure với giới hạn concurrency, giới hạn hàng đợi và giới hạn thời gian của client blocking.

## 7. Chọn scheduler đúng mục đích

| Scheduler | Mục đích | Có phù hợp với blocking I/O? |
|---|---|---|
| **Schedulers.boundedElastic()** | Tác vụ blocking, chờ I/O hoặc API đồng bộ | Có; đây là lựa chọn mặc định thường dùng |
| **Schedulers.parallel()** | Tính toán CPU-bound, không blocking | Không |
| **Schedulers.single()** | Công việc tuần tự trên một worker | Không nên dùng cho tác vụ blocking |
| **Schedulers.immediate()** | Thực thi ngay trên thread hiện tại | Không |
| **Schedulers.fromExecutor(...)** | Dùng executor do ứng dụng quản lý | Có thể, nếu executor được thiết kế và giới hạn phù hợp |

### Vì sao boundedElastic?

Bounded elastic được thiết kế để cô lập công việc blocking bằng một pool có giới hạn. Nó cho phép worker được tạo khi cần nhưng vẫn có giới hạn về tài nguyên và số tác vụ chờ. Cơ chế giới hạn này giúp tránh việc mỗi request tạo một thread mới vô hạn.

Tuy vậy, bounded elastic không phải tài nguyên vô hạn:

- Nếu blocking call kéo dài, worker bị chiếm lâu hơn.
- Nếu số tác vụ vượt khả năng xử lý, tác vụ có thể phải chờ trong hàng đợi.
- Khi pool hoặc hàng đợi quá tải, độ trễ tăng và có thể phát sinh lỗi từ scheduler.
- Một hệ thống có quá nhiều blocking call vẫn có thể cạn tài nguyên.

Không tạo **Schedulers.newBoundedElastic(...)** cho từng request. Nếu cần pool riêng để cô lập một nhóm API có đặc tính tải khác biệt, hãy tạo scheduler ở cấp ứng dụng, cấu hình giới hạn thread và hàng đợi rõ ràng, rồi dispose scheduler khi ứng dụng dừng.

Không dùng **Schedulers.parallel()** cho JDBC hoặc HTTP client đồng bộ. Các worker của parallel được tối ưu cho tính toán CPU-bound; chặn chúng có thể làm các tác vụ reactive khác bị đói thread.

## 8. Timeout, cancellation và giới hạn tài nguyên

Có thể đặt timeout cho publisher:

~~~java
Mono<Customer> customer = Mono
    .fromCallable(() -> blockingCustomerClient.find(customerId))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(3));
~~~

Timeout giới hạn thời gian mà subscriber chờ kết quả. Tuy nhiên, không nên giả định timeout luôn dừng ngay lời gọi blocking đang chạy. Khi subscriber hủy subscription, hiệu quả dừng tác vụ phụ thuộc scheduler và API đồng bộ bên dưới. Một số thư viện tiếp tục chạy cho đến khi thao tác trả về hoặc timeout nội bộ xảy ra.

Vì vậy, cần cấu hình timeout ngay trong client blocking:

- Connection timeout để giới hạn thời gian thiết lập kết nối.
- Read/response timeout để giới hạn thời gian chờ dữ liệu.
- Timeout cho truy vấn database hoặc statement.
- Cơ chế hủy hoặc interrupt nếu thư viện hỗ trợ và ứng dụng có thể sử dụng an toàn.

Đồng thời, hãy cân nhắc:

- Giới hạn số request đồng thời đi vào dịch vụ blocking.
- Giới hạn số phần tử được flatMap xử lý đồng thời.
- Đặt giới hạn kích thước hàng đợi nếu dùng executor riêng.
- Tránh retry vô hạn. Retry một thao tác ghi không idempotent có thể tạo dữ liệu trùng.
- Giải phóng connection, stream và tài nguyên trong finally hoặc cơ chế quản lý tài nguyên phù hợp.

Offload bảo vệ thread phục vụ reactive khỏi việc phải chờ trực tiếp. Nó không làm cho thao tác blocking nhanh hơn và không thay thế timeout, bulkhead hay giới hạn tải.

## 9. Giữ đúng vòng đời request RSocket

Việc chuyển scheduler không nên làm thay đổi interaction model của RSocket:

- Request-Response tiếp tục trả về **Mono<T>**.
- Request-Stream tiếp tục trả về **Flux<T>**.
- Fire-and-Forget có thể dùng publisher hoàn tất mà không trả dữ liệu.
- Channel vẫn phải xử lý luồng hai chiều theo hợp đồng đã thiết kế.

Ví dụ một handler Request-Response:

~~~java
@MessageMapping("inventory.lookup")
Mono<InventoryItem> lookup(InventoryRequest request) {
    return Mono.fromCallable(
            () -> blockingInventoryClient.lookup(request.sku())
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Ví dụ handler trả về một luồng:

~~~java
@MessageMapping("inventory.watch")
Flux<InventoryItem> watch(InventoryWatchRequest request) {
    return Flux.fromIterable(request.skus())
        .flatMap(
            sku -> Mono.fromCallable(
                    () -> blockingInventoryClient.lookup(sku)
                )
                .subscribeOn(Schedulers.boundedElastic()),
            8
        );
}
~~~

Ở ví dụ thứ hai, tối đa tám lookup được subscribe đồng thời cho mỗi subscription của pipeline này. Nếu có nhiều client và nhiều subscription cùng hoạt động, cần tính tổng tải lên dịch vụ blocking, không chỉ nhìn vào giới hạn của một request.

Khi client hủy request hoặc ngắt kết nối, publisher có thể nhận cancellation. Tác vụ blocking đang chạy có thể không dừng tức thì. Vì vậy, timeout nội bộ và cơ chế hủy của thư viện vẫn cần thiết.

Không gọi **subscribe()** bên trong handler để tự chạy tác vụ rồi trả về một publisher khác. Cách đó tách tác vụ khỏi vòng đời request RSocket: lỗi có thể không được gửi về requester, cancellation không còn điều khiển được tác vụ và framework không biết khi nào công việc hoàn tất.

## 10. Context, transaction và ThreadLocal

Khi pipeline chuyển từ thread này sang thread khác, không nên dựa vào giả định rằng mọi **ThreadLocal** sẽ tự động giữ nguyên giá trị. Những giá trị như request context, tracing hoặc security context có thể cần cơ chế truyền context phù hợp.

Trong ứng dụng reactive của Spring, **Reactor Context** là nơi phù hợp để lưu context gắn với subscription. Nếu một thư viện blocking chỉ đọc ThreadLocal, cần cấu hình cơ chế context propagation tương thích với phiên bản Spring/Reactor đang dùng.

Cũng cần phân biệt transaction imperative và reactive:

- Transaction imperative thường gắn với thread thông qua ThreadLocal.
- Reactive transaction được truyền theo Reactor Context và cần reactive transaction manager.
- Một lời gọi JDBC blocking không tự trở thành reactive transaction chỉ vì nó nằm trong Mono.

Nếu gọi service imperative có transaction, hãy để ranh giới transaction được quản lý bởi đúng transaction manager và bảo đảm lời gọi được thực thi trong phạm vi transaction đó. Không chia một transaction imperative thành nhiều scheduler hop rồi giả định trạng thái thread-bound sẽ tự theo publisher.

## 11. Quan sát và kiểm thử

Một triển khai offload tốt cần được kiểm tra cả hành vi lẫn tài nguyên.

### Quan sát trong môi trường chạy

Theo dõi:

- Độ trễ của handler RSocket và từng lời gọi blocking.
- Số lượng request đồng thời và số tác vụ chờ.
- Thread name khi thực hiện lời gọi blocking.
- Timeout, cancellation, lỗi kết nối và lỗi từ scheduler.
- Tình trạng pool của client JDBC/HTTP và mức sử dụng tài nguyên.
- Sự khác biệt độ trễ khi tải tăng.

Có thể thêm **doOnNext**, **doOnError** hoặc tracing để quan sát pipeline. Tránh ghi toàn bộ payload nhạy cảm vào log.

### Kiểm thử

Nên có các kiểm thử sau:

1. Handler trả publisher ngay và lời gọi blocking chỉ xảy ra khi subscription bắt đầu.
2. Lời gọi blocking chạy trên bounded elastic worker, không chạy trên thread non-blocking của pipeline.
3. Lỗi từ API đồng bộ được chuyển thành onError và xử lý đúng.
4. Timeout và cancellation có hành vi phù hợp với khả năng của thư viện blocking.
5. Khi nhiều request đồng thời, giới hạn concurrency và pool được giữ đúng.
6. Request-Response và Request-Stream vẫn tuân thủ đúng interaction model.

**BlockHound** có thể giúp phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking trong môi trường phát triển hoặc kiểm thử. Khi tích hợp, cần dùng phiên bản tương thích với Reactor và các thư viện đang chạy; chỉ cho phép ngoại lệ có chủ đích sau khi đã hiểu rõ tác động.

Một kiểm thử đơn giản cho thấy lời gọi được thực thi khi subscribe:

~~~java
AtomicBoolean invoked = new AtomicBoolean(false);

Mono<String> source = Mono.fromCallable(() -> {
    invoked.set(true);
    return "loaded";
}).subscribeOn(Schedulers.boundedElastic());

assertFalse(invoked.get());

String value = source.block();

assertEquals("loaded", value);
assertTrue(invoked.get());
~~~

Ví dụ này dùng **block()** để chờ kết quả trong test hoặc mã chạy độc lập. Không áp dụng cách chờ đồng bộ này bên trong handler reactive. Trong bài kiểm thử tích hợp, có thể dùng **StepVerifier** để kiểm tra tín hiệu mà không cần tự quản lý subscription bằng tay.

## 12. Những lỗi thường gặp

| Lỗi | Vì sao không đúng | Cách sửa |
|---|---|---|
| Gọi JDBC trực tiếp rồi trả Mono.just | Truy vấn chạy trước khi publisher được tạo | Dùng Mono.fromCallable và subscribeOn |
| Dùng Mono.just(blockingCall()) | Java đánh giá lời gọi ngay lập tức | Đưa lời gọi vào fromCallable |
| Đặt publishOn sau source blocking | Source có thể đã chạy trên thread subscribe ban đầu | Dùng subscribeOn cho source |
| Gọi block() trong handler | Chặn thread và phá vỡ pipeline | Trả Mono hoặc Flux |
| Gọi subscribe() trong handler | Tách tác vụ khỏi vòng đời request | Trả publisher cho Spring |
| Dùng parallel cho I/O blocking | Chiếm worker dành cho CPU-bound | Dùng boundedElastic |
| Tạo scheduler mới cho từng request | Tạo nhiều pool và khó quản lý tài nguyên | Tái sử dụng scheduler cấp ứng dụng |
| Không đặt timeout cho client | Một lời gọi có thể giữ worker quá lâu | Cấu hình timeout ở thư viện blocking |
| Retry thao tác ghi không idempotent | Có thể thực hiện nghiệp vụ nhiều lần | Thiết kế idempotency và retry có kiểm soát |
| Cho phép concurrency không giới hạn | Có thể làm cạn connection pool hoặc hàng đợi | Đặt giới hạn concurrency và admission control |

## 13. Checklist trước khi đưa vào production

- [ ] Đã xác định chính xác thao tác blocking và thời gian chờ dự kiến.
- [ ] Đã kiểm tra xem có API non-blocking thay thế hay không.
- [ ] Lời gọi blocking được trì hoãn bằng fromCallable hoặc fromRunnable.
- [ ] Source blocking được chạy bằng subscribeOn với boundedElastic hoặc scheduler chuyên dụng phù hợp.
- [ ] Không gọi block, toIterable, toStream hoặc subscribe thủ công trong handler.
- [ ] Handler tiếp tục trả đúng Mono/Flux theo interaction model RSocket.
- [ ] Có timeout ở cấp client và xử lý cancellation phù hợp.
- [ ] Có giới hạn concurrency và giới hạn tài nguyên downstream.
- [ ] Đã xem xét transaction, security context và ThreadLocal khi chuyển thread.
- [ ] Đã đo độ trễ, số tác vụ chờ và mức sử dụng pool khi tải tăng.
- [ ] Đã kiểm thử lỗi, timeout, cancellation và nhiều request đồng thời.

## 14. Tài liệu tham khảo

- [Project Reactor Reference: Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) — cách dùng subscribeOn, publishOn và các scheduler.
- [Project Reactor API: Schedulers](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html) — boundedElastic, parallel và cách tạo scheduler.
- [Project Reactor Reference: Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) — hành vi subscription và việc trì hoãn thực thi publisher.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — mô hình requester, responder và handler reactive trong Spring.
- [BlockHound](https://github.com/reactor/BlockHound) — công cụ phát hiện blocking call trên thread non-blocking trong quá trình phát triển và kiểm thử.
