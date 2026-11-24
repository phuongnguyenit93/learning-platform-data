# Tạo nguồn

## Trì hoãn việc tạo nguồn cho đến khi có đăng ký

Trong lập trình reactive, việc khai báo một pipeline và việc thực sự tạo dữ liệu cho pipeline là hai thời điểm khác nhau. Nếu lời gọi truy vấn, đọc cấu hình hoặc tạo giá trị xảy ra ngay khi lắp ghép pipeline, ứng dụng có thể thực hiện công việc dù chưa có subscriber nào cần kết quả. Ta cũng có thể vô tình dùng lại một giá trị cũ cho nhiều lần đăng ký.

Trì hoãn việc tạo nguồn (deferred source creation) nghĩa là chỉ gọi hàm tạo dữ liệu khi có subscription đi đến nguồn. Với Project Reactor, **Mono.defer** và **Flux.defer** nhận một factory để tạo Publisher trong thời điểm đăng ký. Các API như **Mono.fromSupplier** và **Mono.fromCallable** cũng trì hoãn việc gọi supplier hoặc callable, phù hợp khi bản thân thao tác tạo ra một giá trị thay vì một Publisher khác.

### 1. Assembly time và subscription time

Reactor phân biệt hai thời điểm:

- **Assembly time:** chương trình gọi các toán tử để lắp ghép Publisher. Ta mô tả các bước cần thực hiện.
- **Subscription time:** một Subscriber đăng ký. Publisher bắt đầu quá trình tiêu thụ theo ngữ nghĩa của nguồn và các factory được trì hoãn mới được gọi.

Ví dụ:

~~~java
import reactor.core.publisher.Mono;

Mono<String> greeting =
    Mono.just("Xin chào")
        .map(String::toUpperCase);

greeting.subscribe(System.out::println);
~~~

Ở đây, giá trị truyền vào **Mono.just** đã được tạo trước khi pipeline được subscribe. Bản thân các toán tử vẫn được lắp ghép trước subscription, nhưng nguồn **just** giữ sẵn giá trị đã có.

Nếu cần tạo giá trị tại thời điểm mỗi subscriber đăng ký, hãy dùng factory trì hoãn:

~~~java
import java.time.Instant;

import reactor.core.publisher.Mono;

Mono<String> greeting =
    Mono.defer(() -> Mono.just("Xin chào " + Instant.now()));

greeting.subscribe(System.out::println);
greeting.subscribe(System.out::println);
~~~

Mỗi subscription gọi lại supplier trong **defer**, vì vậy thời điểm được đọc tại từng lần đăng ký. Hai subscriber có thể nhận hai giá trị khác nhau. Đây là cách biểu diễn rõ ràng khi dữ liệu cần phụ thuộc vào thời điểm thực thi, cấu hình hiện tại hoặc trạng thái tại lúc consumer bắt đầu.

### 2. Vấn đề khi tạo dữ liệu quá sớm

Xét một dịch vụ đọc thông tin khách hàng:

~~~java
import reactor.core.publisher.Mono;

Mono<Customer> customer =
    Mono.just(repository.findById(customerId));
~~~

Lệnh **repository.findById** được gọi ngay khi biểu thức tạo Publisher được thực thi. Nếu chưa có subscriber, truy vấn vẫn đã chạy. Nếu nhiều thành phần cùng giữ biến **customer**, tất cả có thể nhận cùng một đối tượng đã được tải trước đó, kể cả khi dữ liệu trong cơ sở dữ liệu đã thay đổi.

Một vấn đề khác là ngoại lệ đồng bộ. Nếu **findById** ném lỗi ngay lúc gọi, ngoại lệ có thể thoát ra trước khi một Mono được tạo. Khi đó, subscriber không nhận được tín hiệu **onError** từ pipeline vì lỗi xảy ra bên ngoài pipeline.

Có thể trì hoãn lời gọi bằng **Mono.defer**:

~~~java
import reactor.core.publisher.Mono;

Mono<Customer> customer =
    Mono.defer(() -> Mono.just(repository.findById(customerId)));
~~~

Bây giờ lời gọi repository chỉ xảy ra khi có subscription. Nếu factory ném ngoại lệ trong lúc tạo Publisher, Reactor chuyển ngoại lệ đó thành tín hiệu lỗi cho subscriber. Tuy nhiên, nếu phương thức repository có thể trả về **null**, việc truyền giá trị null vào **Mono.just** vẫn tạo lỗi. Với một lời gọi đồng bộ có thể trả về null, **Mono.fromCallable** thường diễn đạt ý định tốt hơn.

### 3. Mono.defer và Flux.defer

**Mono.defer** nhận một supplier tạo ra một Mono mới cho mỗi subscription:

~~~java
import reactor.core.publisher.Mono;

Mono<Order> order =
    Mono.defer(() -> orderClient.findOrder(currentOrderId()));
~~~

Mỗi subscriber gọi factory để lấy Publisher tương ứng. Điều này hữu ích khi phương thức **findOrder** trả về Mono và việc gọi phương thức đó cần được trì hoãn đến subscription time.

**Flux.defer** hoạt động tương tự với luồng nhiều phần tử:

~~~java
import java.util.Set;

import reactor.core.publisher.Flux;

Flux<String> enabledFeatures =
    Flux.defer(() -> {
        Set<String> features = featureRepository.loadEnabledFeatures();
        return Flux.fromIterable(features);
    });
~~~

Mỗi subscription tải lại danh sách feature và tạo một Flux từ kết quả mới. Nếu nguồn dữ liệu thay đổi giữa hai lần đăng ký, subscriber thứ hai có thể nhận danh sách mới. Nếu **loadEnabledFeatures** là lời gọi blocking, cần bọc và điều phối nó trên scheduler phù hợp; **defer** chỉ trì hoãn thời điểm gọi, không tự biến thao tác blocking thành non-blocking.

Factory phải trả về một Publisher hợp lệ. **defer** không tự biến một publisher nóng thành publisher lạnh. Nếu factory luôn trả về cùng một nguồn nóng được chia sẻ, các subscriber vẫn tham gia nguồn nóng đó và có thể bỏ lỡ những tín hiệu đã phát trước khi đăng ký.

### 4. Chọn giữa just, defer, fromSupplier và fromCallable

Các API này khác nhau ở loại đầu vào và thời điểm đánh giá:

| API | Đầu vào | Thời điểm gọi công việc | Cách biểu diễn kết quả |
| --- | --- | --- | --- |
| **Mono.just(value)** | Một giá trị đã có | Giá trị được tạo trước khi gọi just | Phát đúng giá trị đó cho mỗi subscriber |
| **Mono.defer(factory)** | Factory trả về Mono | Factory chạy khi mỗi subscriber đăng ký | Dùng Publisher được factory tạo ra |
| **Flux.defer(factory)** | Factory trả về Publisher/Flux | Factory chạy khi mỗi subscriber đăng ký | Dùng luồng được factory tạo ra |
| **Mono.fromSupplier(supplier)** | Supplier trả về một giá trị | Supplier chạy khi có subscription | Phát một giá trị; nếu trả null thì hoàn tất rỗng |
| **Mono.fromCallable(callable)** | Callable trả về một giá trị và có thể ném checked exception | Callable chạy khi có subscription | Phát giá trị, hoàn tất rỗng nếu null, hoặc phát onError nếu ném lỗi |

Ví dụ với một giá trị được tạo lười:

~~~java
import java.util.UUID;

import reactor.core.publisher.Mono;

Mono<String> requestId =
    Mono.fromSupplier(() -> UUID.randomUUID().toString());
~~~

Supplier được gọi cho từng subscription, vì vậy mỗi subscriber nhận một request ID mới. Nếu muốn factory trả về một Mono phức tạp hơn, chẳng hạn gọi một client reactive, dùng **Mono.defer**:

~~~java
import reactor.core.publisher.Mono;

Mono<Response> response =
    Mono.defer(() -> apiClient.fetch(buildRequest()));
~~~

Nếu cần bọc một lời gọi đồng bộ có thể ném lỗi:

~~~java
import reactor.core.publisher.Mono;

Mono<Customer> customer =
    Mono.fromCallable(() -> legacyRepository.findCustomer(customerId));
~~~

**fromCallable** chuyển ngoại lệ được ném trong callable thành **onError**. Nếu callable trả về null, Mono hoàn tất mà không phát phần tử. Với thao tác blocking, cần thêm scheduler phù hợp, như **subscribeOn(Schedulers.boundedElastic())**, để không chặn thread xử lý sự kiện:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer =
    Mono.fromCallable(() -> legacyRepository.findCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Scheduler xử lý vị trí thực thi; **fromCallable** xử lý việc trì hoãn và chuyển ngoại lệ thành tín hiệu. Hai trách nhiệm này bổ trợ nhau.

### 5. Factory chạy một lần cho mỗi subscription, không phải mỗi request

Một factory của **defer** được gọi khi subscription đi đến nguồn. Nó không được gọi lại mỗi khi Subscriber gọi **request(n)**. Demand điều khiển số phần tử Publisher được phép phát; subscription điều khiển một lần tiêu thụ; factory tạo nguồn cho lần tiêu thụ đó.

Ví dụ:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;

AtomicInteger creations = new AtomicInteger();

Flux<Integer> numbers =
    Flux.defer(() -> {
        creations.incrementAndGet();
        return Flux.range(1, 5);
    });
~~~

Nếu một subscriber yêu cầu hai phần tử rồi yêu cầu thêm ba phần tử, factory vẫn chỉ chạy một lần trong subscription đó. Nếu một subscriber thứ hai đăng ký, factory chạy thêm một lần. Phân biệt này rất quan trọng khi factory mở kết nối, tạo cursor hoặc khởi tạo một tác vụ tốn kém.

### 6. Mỗi subscription có thể nhận một nguồn độc lập

Một ứng dụng có thể giữ một biến Publisher rồi dùng ở nhiều nơi:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

AtomicInteger loads = new AtomicInteger();

Mono<Configuration> configuration =
    Mono.defer(() -> {
        loads.incrementAndGet();
        return configurationClient.fetchCurrent();
    });

configuration.subscribe(this::configureDashboard);
configuration.subscribe(this::configureWorker);
~~~

Với nguồn cold được tạo lại trong factory, mỗi subscription gọi **fetchCurrent** riêng. Điều này phù hợp nếu mỗi consumer cần đọc trạng thái mới nhất tại thời điểm nó bắt đầu. Tuy nhiên, nếu hai consumer phải dùng cùng một kết quả hoặc truy vấn nguồn tốn kém, việc thực thi hai lần có thể không mong muốn.

Trong trường hợp cần chia sẻ một kết quả, có thể cache Publisher:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;

Mono<Configuration> cachedConfiguration =
    Mono.defer(() -> configurationClient.fetchCurrent())
        .cache(Duration.ofMinutes(1));
~~~

Subscriber đầu tiên kích hoạt factory và nguồn; subscriber tiếp theo trong thời gian cache hợp lệ nhận lại tín hiệu đã lưu. Chính sách này thay đổi ngữ nghĩa từ một lần đọc mới cho mỗi subscriber sang dùng chung kết quả được lưu. Cần chọn TTL theo yêu cầu độ mới và hiểu rằng cache có thể lưu cả tín hiệu lỗi hoặc hoàn tất.

### 7. Defer và retry: mỗi lần thử lại có thể tạo nguồn mới

Retry thực hiện subscription lại upstream khi có lỗi. Nếu nguồn được tạo bằng **defer**, factory được gọi lại ở mỗi lần subscription mới:

~~~java
import java.util.UUID;

import reactor.core.publisher.Mono;

Mono<String> result =
    Mono.defer(() -> {
        String attemptId = UUID.randomUUID().toString();
        return remoteClient.call(attemptId);
    })
    .retry(2);
~~~

Trong ví dụ, mỗi lần thử có thể tạo một attempt ID mới. Điều đó hữu ích khi ID dùng để theo dõi từng lần thử. Nhưng nếu ID là khóa idempotency phải giữ nguyên cho cùng một yêu cầu nghiệp vụ, hãy tạo ID bên ngoài **defer** rồi dùng lại trong factory:

~~~java
import java.util.UUID;

import reactor.core.publisher.Mono;

String idempotencyKey = UUID.randomUUID().toString();

Mono<Receipt> receipt =
    Mono.defer(() -> remoteClient.submit(order, idempotencyKey))
        .retry(2);
~~~

Retry có thể lặp lại tác dụng phụ. Chỉ dùng khi thao tác an toàn để lặp, có khóa idempotency hoặc có cơ chế đối soát. **defer** giúp tạo lại Publisher ở mỗi lần thử, nhưng không tự bảo đảm yêu cầu được thực thi an toàn nhiều lần.

### 8. Đọc dữ liệu theo ngữ cảnh của từng subscriber

Trong một dịch vụ đa tenant, cùng một pipeline có thể được đăng ký trong những ngữ cảnh khác nhau. **deferContextual** cho phép đọc Reactor Context tại thời điểm subscription và tạo Publisher dựa trên ngữ cảnh đó:

~~~java
import reactor.util.context.Context;
import reactor.core.publisher.Mono;

Mono<String> tenantName =
    Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
    );

tenantName
    .contextWrite(Context.of("tenantId", "tenant-a"))
    .subscribe(System.out::println);
~~~

Factory đọc **tenantId** từ Context của subscription hiện tại. Subscriber khác có thể cung cấp tenant khác mà không cần lưu tenant ID vào một biến mutable dùng chung. Cách này phù hợp với metadata như tenant, correlation ID hoặc thông tin định tuyến được quản lý trong Reactor Context.

Context không phải một kho lưu trữ toàn cục và không tự truyền sang mọi API callback bên ngoài Reactor. Khi rời pipeline reactive để gọi thư viện không tích hợp Context, cần truyền metadata theo cơ chế mà thư viện đó hỗ trợ.

### 9. Trì hoãn tạo nguồn và quản lý tài nguyên

Factory trì hoãn có thể tạo tài nguyên như kết nối, cursor hoặc listener. Nếu nguồn giữ tài nguyên, cần gắn việc giải phóng với vòng đời subscription để xử lý cả hoàn tất, lỗi và cancellation.

Với tài nguyên đồng bộ, Reactor có **using**; với việc mở hoặc đóng tài nguyên bất đồng bộ, có **usingWhen**. Ví dụ khái quát:

~~~java
import reactor.core.publisher.Mono;

Mono<Result> result =
    Mono.usingWhen(
        connectionFactory.create(),
        connection -> connection.queryReactive(),
        connection -> connection.closeReactive()
    );
~~~

Factory của tài nguyên chỉ được kích hoạt khi có subscription. Reactor điều phối việc đóng tài nguyên theo các nhánh hoàn tất, lỗi và hủy. Tên và kiểu trả về trong ví dụ đại diện cho API kết nối của ứng dụng; khi triển khai cần dùng đúng kiểu Publisher mà connection factory và phương thức close cung cấp.

Không nên mở kết nối ngay ở assembly time rồi chỉ trì hoãn việc sử dụng nó. Nếu subscriber không bao giờ đăng ký, tài nguyên đã mở có thể không được dùng nhưng vẫn bị giữ. Cũng không nên dùng một đối tượng tài nguyên mutable chung cho nhiều subscription nếu nó không được thiết kế để chia sẻ đồng thời.

### 10. Kiểm thử thời điểm tạo nguồn

Có thể dùng **AtomicInteger** để xác minh factory chưa chạy ở assembly time và chỉ chạy khi subscribe:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

AtomicInteger factoryCalls = new AtomicInteger();

Mono<Integer> deferred =
    Mono.defer(() -> {
        factoryCalls.incrementAndGet();
        return Mono.just(42);
    });

assertEquals(0, factoryCalls.get());

StepVerifier.create(deferred)
    .expectNext(42)
    .verifyComplete();

assertEquals(1, factoryCalls.get());
~~~

Kiểm thử này xác nhận việc khai báo deferred chưa gọi factory; subscription mới kích hoạt nó. Nếu subscribe lần thứ hai, số lần gọi sẽ tăng lên hai đối với nguồn cold được tạo mới cho từng subscriber.

Có thể kiểm tra hành vi nhiều subscription:

~~~java
StepVerifier.create(deferred)
    .expectNext(42)
    .verifyComplete();

assertEquals(2, factoryCalls.get());
~~~

Trong một bài kiểm thử đầy đủ, hãy đặt phần kiểm tra này sau lần verify đầu tiên và bảo đảm không có subscription nào khác dùng chung biến đếm. Với nguồn có thời gian hoặc scheduler, có thể dùng virtual time khi cần xác minh thời điểm phát mà không phải chờ thật.

### 11. Các lỗi thiết kế thường gặp

| Cách viết hoặc giả định | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi truy vấn trong đối số của **Mono.just** | Truy vấn chạy ở assembly time | Dùng **fromCallable** hoặc **defer** |
| Dùng **defer** nhưng factory trả về cùng một hot publisher | Không tạo nguồn cold mới; subscriber vẫn tham gia nguồn nóng chung | Xác định rõ có cần chia sẻ hay cần nguồn riêng |
| Nghĩ factory chạy mỗi lần **request(n)** | Hiểu sai vòng đời subscription | Factory chạy khi subscription đến nguồn; demand chỉ điều khiển số phần tử |
| Dùng **fromCallable** cho I/O blocking trên event loop | Thread xử lý sự kiện vẫn có thể bị chặn | Dùng **subscribeOn(Schedulers.boundedElastic())** hoặc API non-blocking |
| Dùng retry mà tạo lại khóa idempotency | Một nghiệp vụ có thể bị xem như nhiều yêu cầu khác nhau | Tạo khóa ổn định ngoài factory nếu nghiệp vụ yêu cầu |
| Trì hoãn tạo tài nguyên nhưng không quản lý cleanup | Có thể rò rỉ tài nguyên khi lỗi hoặc cancellation | Dùng **using** hoặc **usingWhen** phù hợp |

### 12. Nguyên tắc lựa chọn

Khi thiết kế nguồn, hãy xác định:

- Giá trị đã có sẵn ở assembly time hay phải đọc tại subscription time?
- Mỗi subscriber cần nguồn độc lập hay cần chia sẻ cùng một lần thực thi?
- Factory tạo ra một giá trị hay một Publisher khác?
- Lời gọi đồng bộ có thể ném lỗi hoặc trả null không?
- Thao tác có blocking và cần scheduler nào?
- Retry có tạo lại dữ liệu định danh hoặc lặp tác dụng phụ không?
- Nguồn có mở tài nguyên cần đóng khi hoàn tất, lỗi hoặc bị hủy không?

Với một giá trị đã có, **Mono.just** là lựa chọn đơn giản. Với một giá trị cần tạo lười, cân nhắc **fromSupplier** hoặc **fromCallable**. Khi cần factory trả về Publisher, dùng **Mono.defer** hoặc **Flux.defer**. Nếu nguồn phụ thuộc Context của từng subscriber, dùng **deferContextual**. Sau đó xác định rõ chính sách chia sẻ, retry, scheduler và cleanup.

Trong module REACTIVE_PROGRAMMING, trì hoãn tạo nguồn là nền tảng để hiểu cold publisher và subscription. Nó giúp pipeline chỉ tạo dữ liệu khi có consumer, tạo lại nguồn theo từng lần đăng ký khi cần, chuyển lỗi vào đúng kênh tín hiệu và gắn vòng đời tài nguyên với subscription. Kết hợp đúng các cơ chế này giúp những pipeline **Mono**/**Flux** dễ dự đoán và kiểm soát hơn.
