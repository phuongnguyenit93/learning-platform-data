# Tránh block trên event loop và chọn scheduler cho tác vụ blocking

## Mục tiêu của bài học

Trong ứng dụng Spring WebFlux, Reactor xử lý nhiều yêu cầu bằng các luồng event loop có số lượng giới hạn. Mỗi luồng cần quay lại xử lý nhanh để tiếp nhận sự kiện mạng và chuyển tiếp tín hiệu reactive. Nếu một thao tác blocking chiếm event loop trong thời gian dài, những yêu cầu khác dùng chung luồng đó cũng phải chờ. Hệ thống có thể tăng độ trễ trên diện rộng dù chỉ một phụ thuộc đang chậm.

Circuit breaker giúp ngừng gửi lời gọi mới đến một phụ thuộc đang gặp sự cố, nhưng nó không tự biến lời gọi đồng bộ thành non-blocking và cũng không tự chọn scheduler. Ứng dụng phải giữ các thao tác reactive trên luồng phù hợp, đồng thời chuyển những API blocking không thể thay thế sang scheduler dành cho tác vụ blocking.

Sau bài học, bạn có thể:

- Giải thích vai trò của event loop và tác động của việc block một luồng xử lý reactive.
- Nhận biết các thao tác blocking thường gặp trong controller và chuỗi Reactor.
- Dùng subscribeOn và Schedulers.boundedElastic() để chạy API blocking trên worker phù hợp.
- Phân biệt subscribeOn với publishOn và chọn scheduler theo loại công việc.
- Kết hợp lời gọi blocking đã được offload với reactive circuit breaker mà vẫn giữ đúng ranh giới bảo vệ.
- Phối hợp scheduler, timeout và bulkhead để giới hạn ảnh hưởng của phụ thuộc chậm.

## 1. Event loop cần được giải phóng nhanh

WebFlux sử dụng mô hình xử lý bất đồng bộ dựa trên Reactor và một số event loop của runtime mạng. Thay vì cấp một thread riêng cho mỗi request và giữ thread đó trong suốt thời gian chờ I/O, event loop xử lý nhiều kết nối bằng cách tiếp nhận sự kiện, thực thi phần việc ngắn rồi chuyển sang việc khác.

Một luồng event loop có thể phục vụ nhiều request. Khi code trên luồng này gọi một phương thức blocking, luồng không thể tiếp tục xử lý các sự kiện khác cho đến khi phương thức trả về.

Ví dụ, nếu một handler gọi một HTTP client đồng bộ và dịch vụ phụ thuộc mất 3 giây để phản hồi, event loop đang thực thi handler có thể bị giữ trong suốt thời gian đó. Các request khác được gán cho cùng event loop cũng bị trì hoãn. Khi số lời gọi blocking tăng, độ trễ và hàng đợi có thể tăng nhanh.

Luồng xử lý reactive lý tưởng:

    Request
       |
       v
    Event loop
       |
       +-- tạo publisher
       |
       +-- gửi request bất đồng bộ
       |
       +-- trả luồng về event loop
       |
       +-- nhận tín hiệu khi có dữ liệu
       |
       +-- tiếp tục xử lý ngắn và không block

Khi I/O hoàn tất, thư viện reactive phát tín hiệu để chuỗi xử lý tiếp tục. Event loop không cần đứng chờ một thread phản hồi mạng.

Điểm quan trọng: reactive không có nghĩa mọi đoạn code trong chuỗi đều tự động non-blocking. Nếu một operator gọi JDBC đồng bộ, RestTemplate, đọc file đồng bộ hoặc Thread.sleep, đoạn code đó vẫn block thread đang chạy nó.

## 2. Nhận biết các thao tác blocking

Một số thao tác dễ vô tình block event loop:

- Gọi HTTP đồng bộ bằng RestTemplate hoặc một HTTP client có API chờ kết quả trực tiếp.
- Truy vấn cơ sở dữ liệu qua JDBC hoặc JPA đồng bộ.
- Gọi Future.get(), CompletableFuture.join() hoặc chờ semaphore/latch.
- Gọi Mono.block(), Flux.blockFirst() hoặc Flux.blockLast() trong request flow reactive.
- Dùng Thread.sleep() để chờ hoặc retry.
- Đọc/ghi file bằng API đồng bộ.
- Gọi thư viện bên thứ ba mà phương thức chỉ trả kết quả sau khi I/O hoàn tất.

Ví dụ không phù hợp trong WebFlux:

    @RestController
    public class InventoryController {

        private final RestTemplate restTemplate;

        @GetMapping("/inventory/{sku}")
        public InventoryResponse find(@PathVariable String sku) {
            return restTemplate.getForObject(
                "http://inventory-service/inventory/" + sku,
                InventoryResponse.class
            );
        }
    }

Phương thức find thực hiện HTTP request đồng bộ ngay trong lúc xử lý request. Nếu controller chạy trên event loop, thread đó phải chờ kết quả từ inventory-service.

Một ví dụ khác là tạo publisher nhưng gọi block để lấy dữ liệu:

    @GetMapping("/inventory/{sku}")
    public Mono<InventoryResponse> find(@PathVariable String sku) {
        InventoryResponse response = webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class)
            .block();

        return Mono.just(response);
    }

Đoạn code trên đã biến lời gọi WebClient thành thao tác chờ đồng bộ. Hãy trả trực tiếp publisher:

    @GetMapping("/inventory/{sku}")
    public Mono<InventoryResponse> find(@PathVariable String sku) {
        return webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class);
    }

Không gọi block() trong luồng xử lý WebFlux để lấy một giá trị rồi bọc lại bằng Mono hoặc Flux. Hãy để publisher được compose và subscribe bởi runtime reactive.

## 3. Ưu tiên API non-blocking khi có thể

Nếu thư viện đã cung cấp API reactive hoặc bất đồng bộ thực sự, hãy dùng API đó. Ví dụ:

| Nhu cầu | API nên ưu tiên trong luồng reactive | API cần thận trọng |
| --- | --- | --- |
| Gọi HTTP | WebClient | RestTemplate hoặc HTTP client đồng bộ |
| Truy vấn cơ sở dữ liệu | R2DBC và reactive repository tương ứng | JDBC, JPA blocking |
| Xử lý một kết quả | Mono | Gọi block() để lấy kết quả |
| Xử lý nhiều kết quả | Flux | Thu thập dữ liệu lớn thành List chỉ để chờ hoàn tất |
| Chờ thời gian | Mono.delay hoặc operator thời gian | Thread.sleep |
| Kết hợp tác vụ async | then, flatMap, zip và các operator Reactor | Future.get hoặc join |

Ví dụ dùng WebClient trả về Mono:

    public Mono<InventoryResponse> find(String sku) {
        return webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class);
    }

WebClient thực hiện I/O theo mô hình non-blocking. Không cần chuyển lời gọi này sang boundedElastic chỉ vì nó truy cập mạng. Việc thêm scheduler không làm API tốt hơn và có thể tạo thêm chuyển luồng không cần thiết.

Nếu cơ sở dữ liệu đã có reactive driver, dùng reactive repository và giữ toàn bộ chuỗi xử lý reactive. Chuyển một truy vấn JDBC sang boundedElastic có thể giúp tránh block event loop, nhưng thao tác đó vẫn là blocking và vẫn tiêu thụ một worker trong lúc chờ.

## 4. Offload API blocking bằng boundedElastic

Khi chưa thể thay API blocking, hãy cô lập nó khỏi event loop. Reactor cung cấp Schedulers.boundedElastic() dành cho những tác vụ blocking có thời gian thực thi thay đổi.

Với Mono, có thể dùng Mono.fromCallable để trì hoãn việc gọi API cho đến khi có subscription, sau đó đặt subscribeOn:

    Mono<InventoryResponse> request = Mono.fromCallable(() ->
        restTemplate.getForObject(
            "http://inventory-service/inventory/{sku}",
            InventoryResponse.class,
            sku
        )
    ).subscribeOn(Schedulers.boundedElastic());

fromCallable tạo publisher từ một Callable. Callable chỉ chạy khi publisher được subscribe. subscribeOn(Schedulers.boundedElastic()) đưa quá trình subscribe và việc thực thi nguồn này lên worker của boundedElastic, vì vậy lời gọi RestTemplate không chiếm event loop.

Có thể dùng cách tương tự với JDBC hoặc thư viện blocking:

    Mono<Customer> customer = Mono.fromCallable(() ->
        jdbcCustomerRepository.findById(customerId)
            .orElseThrow(() -> new CustomerNotFoundException(customerId))
    ).subscribeOn(Schedulers.boundedElastic());

Với một tác vụ không trả kết quả, dùng fromRunnable:

    Mono<Void> writeAudit = Mono.fromRunnable(() ->
        blockingAuditClient.write(event)
    ).subscribeOn(Schedulers.boundedElastic());

Không gọi phương thức blocking trước khi tạo publisher. Ví dụ sau vẫn sai:

    Customer customer = jdbcCustomerRepository.findById(customerId)
        .orElseThrow();

    Mono<Customer> result = Mono.just(customer)
        .subscribeOn(Schedulers.boundedElastic());

Truy vấn JDBC đã chạy trước khi Mono được tạo. subscribeOn không thể di chuyển công việc đã thực hiện sang scheduler khác. Đưa chính lời gọi vào trong fromCallable hoặc fromRunnable để nó chỉ thực thi khi subscribe.

## 5. Chọn đúng vị trí của subscribeOn và publishOn

subscribeOn và publishOn đều liên quan đến scheduler nhưng có vai trò khác nhau.

| Operator | Tác động | Khi nào dùng |
| --- | --- | --- |
| subscribeOn(scheduler) | Điều khiển scheduler dùng để subscribe nguồn và thực thi phần nguồn đồng bộ khi subscription bắt đầu. | Đưa một nguồn blocking như fromCallable sang boundedElastic. |
| publishOn(scheduler) | Chuyển việc xử lý các tín hiệu tiếp theo và các operator phía sau sang scheduler đã chọn. | Chuyển một đoạn xử lý downstream sang scheduler khác. |

Ví dụ dùng subscribeOn đúng chỗ:

    Mono<Customer> customer = Mono.fromCallable(() ->
        jdbcCustomerRepository.findById(customerId).orElseThrow()
    ).subscribeOn(Schedulers.boundedElastic());

Ví dụ publishOn để chuyển một bước xử lý phía sau:

    Mono<CustomerView> view = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .publishOn(Schedulers.parallel())
        .map(this::calculateCpuIntensiveView);

WebClient vẫn thực hiện I/O non-blocking. Sau khi có kết quả, publishOn chuyển các tín hiệu và operator map phía sau sang scheduler parallel để thực hiện phép tính CPU.

Không dùng publishOn ở phía sau một lời gọi blocking để cố chuyển chính lời gọi đó:

    Mono<Customer> wrong = Mono.fromCallable(() ->
        jdbcCustomerRepository.findById(customerId).orElseThrow()
    ).publishOn(Schedulers.boundedElastic());

Nguồn fromCallable có thể được thực thi trước khi publishOn chuyển tín hiệu downstream. Vì vậy, truy vấn JDBC vẫn có nguy cơ chạy trên thread thực hiện subscription, chẳng hạn event loop. Hãy dùng subscribeOn để đặt nguồn blocking lên boundedElastic.

Quy tắc thực hành:

- Đặt subscribeOn gần nguồn blocking, thường ngay sau fromCallable hoặc fromRunnable.
- Dùng publishOn khi cần đổi scheduler cho các bước xử lý tiếp theo.
- Không thêm nhiều lần chuyển scheduler nếu không có lý do đo được.
- Không giả định publishOn làm thay đổi scheduler của các bước nằm trước nó.

## 6. Chọn scheduler theo loại công việc

Reactor cung cấp một số scheduler thường dùng:

| Scheduler | Mục đích | Ví dụ |
| --- | --- | --- |
| Schedulers.parallel() | Công việc CPU-bound, chia sẻ pool có số worker phù hợp với số lõi xử lý. | Chuyển đổi dữ liệu, tính toán thuần, xử lý không chờ I/O. |
| Schedulers.boundedElastic() | Tác vụ blocking có thời gian chờ thay đổi, với số worker và hàng đợi được giới hạn. | JDBC, RestTemplate, đọc file đồng bộ, SDK blocking. |
| Schedulers.single() | Một worker tuần tự dùng chung. | Tác vụ nhẹ cần chạy tuần tự khi có chủ đích. |
| Schedulers.immediate() | Thực thi ngay trên thread hiện tại. | Trường hợp đặc biệt cần giữ execution context hiện tại; không dùng để offload blocking. |

Không chạy JDBC, RestTemplate hoặc Thread.sleep trên Schedulers.parallel(). Pool này dành cho công việc CPU-bound; một worker bị block sẽ làm giảm khả năng xử lý các tác vụ khác.

boundedElastic phù hợp hơn với API blocking vì số worker có giới hạn và các tác vụ vượt khả năng xử lý sẽ phải chờ trong hàng đợi có giới hạn. Tuy nhiên, boundedElastic không phải tài nguyên vô hạn. Nếu dịch vụ phụ thuộc bị treo, worker có thể bị chiếm lâu và hàng đợi có thể tăng. Cần kết hợp timeout ở client, giới hạn concurrency và circuit breaker.

Với một loại công việc blocking có yêu cầu cô lập riêng, có thể tạo scheduler riêng từ Schedulers.newBoundedElastic(...) và quản lý vòng đời của nó. Khi ứng dụng dừng, cần dispose scheduler đã tạo. Không tạo một scheduler mới cho từng request vì việc đó làm tăng tài nguyên và khó kiểm soát.

## 7. Kết hợp boundedElastic với reactive circuit breaker

Circuit breaker không tự chọn scheduler và không làm cho RestTemplate trở thành non-blocking. Hãy tạo publisher blocking, offload nguồn sang boundedElastic, rồi đưa publisher đó qua reactive circuit breaker.

Ví dụ dùng Spring Cloud ReactiveCircuitBreakerFactory:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.client.RestTemplate;
    import reactor.core.publisher.Mono;
    import reactor.core.scheduler.Schedulers;

    @Service
    public class ReactiveInventoryGateway {

        private final RestTemplate restTemplate;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                RestTemplate restTemplate,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.restTemplate = restTemplate;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> find(String sku) {
            Mono<InventoryResponse> blockingRequest = Mono.fromCallable(() ->
                restTemplate.getForObject(
                    "http://inventory-service/inventory/{sku}",
                    InventoryResponse.class,
                    sku
                )
            ).subscribeOn(Schedulers.boundedElastic());

            return circuitBreakerFactory.create("inventory-read").run(
                blockingRequest,
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

Ở đây có hai trách nhiệm riêng:

- subscribeOn(boundedElastic()) bảo đảm RestTemplate chạy trên worker phù hợp, không chiếm event loop.
- Reactive circuit breaker theo dõi kết quả publisher và có thể từ chối lời gọi mới khi phụ thuộc đang gặp sự cố. Hàm fallback trả về Mono cùng kiểu dữ liệu.

Nếu breaker chuyển OPEN, publisher chính không được thực thi và fallback có thể trả về trạng thái UNKNOWN. Nếu publisher chạy, lỗi hoặc thời gian thực thi của lời gọi được dùng theo cấu hình breaker. Việc offload không làm thay đổi ranh giới bảo vệ: thao tác được theo dõi vẫn là lời gọi đến inventory-service.

Nếu dùng Resilience4j Reactor operator trực tiếp, có thể trang trí publisher tương tự:

    Mono<InventoryResponse> protectedRequest = Mono.fromCallable(() ->
        restTemplate.getForObject(
            "http://inventory-service/inventory/{sku}",
            InventoryResponse.class,
            sku
        )
    )
    .subscribeOn(Schedulers.boundedElastic())
    .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
    .onErrorResume(
        CallNotPermittedException.class,
        error -> Mono.just(InventoryResponse.unknown(sku))
    );

Đặt circuit breaker operator trước onErrorResume để breaker nhận được lỗi của nguồn trước khi lỗi được chuyển thành fallback. Nếu xử lý lỗi thành kết quả thành công trước khi breaker quan sát, thống kê failure rate có thể không phản ánh đúng tình trạng phụ thuộc.

## 8. Giới hạn thời gian và số tác vụ blocking đồng thời

Offload giúp giải phóng event loop, nhưng không làm lời gọi blocking hoàn tất nhanh hơn. Nếu inventory-service không phản hồi, một worker boundedElastic vẫn có thể bị giữ cho đến khi HTTP client timeout hoặc thao tác kết thúc.

Cần phối hợp các cơ chế:

- **HTTP client timeout:** giới hạn thời gian kết nối và chờ phản hồi của RestTemplate hoặc client đồng bộ đang dùng.
- **Circuit breaker:** dùng failure rate và slow call rate để ngừng gửi các lời gọi mới khi phụ thuộc có vấn đề.
- **Bulkhead:** giới hạn số lời gọi đồng thời đến một phụ thuộc để tránh chiếm hết worker hoặc tài nguyên.
- **Scheduler:** cô lập các tác vụ blocking khỏi event loop và đặt giới hạn worker/hàng đợi phù hợp.

Ví dụ cấu hình bulkhead Resilience4j:

    resilience4j:
      bulkhead:
        instances:
          inventory-read:
            maxConcurrentCalls: 20
            maxWaitDuration: 0ms

Giới hạn này minh họa số lời gọi đồng thời tối đa theo instance bulkhead. Nếu ứng dụng chạy nhiều pod, tổng số lời gọi đến inventory-service có thể cao hơn giới hạn của một pod. Hãy tính tổng tải từ các instance khi chọn giá trị.

Có thể thêm timeout ở tầng Reactor:

    Mono<InventoryResponse> request = Mono.fromCallable(() ->
        restTemplate.getForObject(
            "http://inventory-service/inventory/{sku}",
            InventoryResponse.class,
            sku
        )
    )
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));

timeout của Reactor phát tín hiệu lỗi và hủy subscription khi quá thời gian. Tuy nhiên, việc hủy subscription không bảo đảm một lời gọi blocking bên dưới đã dừng ngay hoặc thread worker đã được giải phóng. Hãy cấu hình timeout thực tế trên HTTP client; không dựa riêng vào Mono.timeout để dừng I/O đồng bộ.

Nếu có nhiều request chờ trong boundedElastic, hãy xem xét concurrency và queueing. Một bulkhead đặt trước thao tác blocking có thể từ chối sớm thay vì để hàng loạt công việc xếp hàng chiếm tài nguyên. Circuit breaker giúp chặn phụ thuộc đang lỗi kéo dài; bulkhead giới hạn số tác vụ đang chạy; timeout giới hạn thời gian chờ. Ba cơ chế bổ sung cho nhau.

## 9. Tránh tạo subscription và chuyển luồng ngoài ý muốn

Reactor publisher thường là lazy. Việc tạo Mono hoặc Flux không đồng nghĩa tác vụ đã chạy. Tác vụ được thực thi khi có subscription.

Không gọi subscribe() thủ công bên trong controller hoặc service chỉ để bắt đầu công việc rồi trả một publisher khác. Điều đó tách công việc khỏi vòng đời request, khiến lỗi và cancellation khó được truyền về đúng nơi.

Ví dụ không nên dùng:

    public Mono<InventoryResponse> find(String sku) {
        Mono<InventoryResponse> request = createBlockingRequest(sku);

        request.subscribe();

        return Mono.just(InventoryResponse.unknown(sku));
    }

Đoạn code này tạo một subscription riêng và trả kết quả fallback ngay lập tức, trong khi request thật vẫn chạy độc lập. Hãy trả publisher đã bảo vệ để framework quản lý subscription:

    public Mono<InventoryResponse> find(String sku) {
        return createBlockingRequest(sku)
            .subscribeOn(Schedulers.boundedElastic());
    }

Cũng tránh subscribe nhiều lần vào cùng một publisher lạnh nếu không muốn gửi nhiều request đến dịch vụ phụ thuộc. Nếu cần dùng cùng một kết quả cho nhiều nhánh, cân nhắc các operator chia sẻ hoặc kết hợp publisher thay vì tạo subscription thủ công.

Cancellation từ client có thể hủy chuỗi reactive và các thao tác hỗ trợ cancellation. Tuy nhiên, API blocking có thể tiếp tục chạy cho đến khi nó tự kết thúc hoặc timeout ở tầng client. Vì vậy, việc giới hạn thời gian và số tác vụ blocking vẫn cần thiết ngay cả khi dùng Reactor.

## 10. Kiểm tra event loop và scheduler trong thực tế

Có thể xác minh lựa chọn scheduler bằng cách quan sát thread thực thi. Trong một publisher thử nghiệm, in tên thread ở nguồn và ở bước xử lý tiếp theo:

    Mono<String> sample = Mono.fromCallable(() -> {
        System.out.println("blocking source: " + Thread.currentThread().getName());
        return "done";
    })
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(value -> {
        System.out.println("cpu stage: " + Thread.currentThread().getName());
        return value.toUpperCase();
    });

Kết quả mong đợi:

- blocking source chạy trên worker có tên thuộc boundedElastic.
- cpu stage chạy trên worker thuộc parallel.
- event loop không bị giữ trong lúc nguồn blocking đang chờ.

Tên thread cụ thể phụ thuộc runtime và phiên bản Reactor; hãy xác nhận loại scheduler và đường đi thực tế, không phụ thuộc vào một chuỗi tên thread cố định trong kiểm thử.

Các dấu hiệu event loop bị block:

- Độ trễ tăng đồng loạt trên nhiều endpoint reactive.
- Số event loop thread ít nhưng thời gian xử lý hoặc chờ tăng cao.
- Log cảnh báo blocking call trên thread không cho phép blocking.
- Một endpoint gọi thư viện đồng bộ làm các endpoint khác dùng chung runtime cũng chậm.

BlockHound có thể được tích hợp trong môi trường phát triển hoặc kiểm thử để phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking. Công cụ này hỗ trợ phát hiện sớm, nhưng không thay thế việc hiểu API của thư viện và kiểm tra tải thực tế.

## 11. Bài thực hành: bảo vệ một thư viện HTTP blocking

Giả sử order-service hiện đang dùng RestTemplate để gọi inventory-service, nhưng phần còn lại của ứng dụng dùng WebFlux.

1. Tạo một phương thức gateway trả về Mono<InventoryResponse>.
2. Đưa lời gọi RestTemplate vào Mono.fromCallable để nó chỉ chạy khi subscribe.
3. Dùng subscribeOn(Schedulers.boundedElastic()) ngay sau nguồn blocking.
4. Bọc publisher bằng ReactiveCircuitBreakerFactory với id inventory-read.
5. Cấu hình connect timeout và response timeout trên HTTP client.
6. Thêm fallback biểu diễn trạng thái tồn kho chưa xác định.
7. Tạo tải thử trong khi inventory-service phản hồi chậm; quan sát event loop vẫn xử lý endpoint khác.
8. Giới hạn số lời gọi đồng thời bằng bulkhead và quan sát các request vượt giới hạn.
9. Làm inventory-service trả lỗi liên tiếp để breaker chuyển OPEN, rồi phục hồi để quan sát HALF_OPEN.
10. Kiểm tra log thread để xác nhận RestTemplate không chạy trên event loop.

Thử thêm một phiên bản dùng WebClient. So sánh hai cách: WebClient thực hiện I/O non-blocking và không cần boundedElastic; RestTemplate vẫn blocking dù đã offload sang boundedElastic. Cả hai có thể được bảo vệ bằng circuit breaker, nhưng chỉ offload không làm API blocking trở thành reactive.

Khi hoàn thành, bạn cần xác định được đoạn code nào block, thread nào đang chạy đoạn code đó, vì sao subscribeOn cần đặt gần nguồn blocking và khi nào publishOn phù hợp. Bạn cũng cần giải thích vì sao scheduler, timeout, bulkhead và circuit breaker có trách nhiệm riêng. Kết hợp đúng các cơ chế này giúp event loop luôn sẵn sàng xử lý request và giới hạn tác động khi phụ thuộc từ xa chậm hoặc không khả dụng.

