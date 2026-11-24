# Phân biệt cấu hình Hystrix cũ với Spring Cloud CircuitBreaker

## Mục tiêu của bài học

Nhiều ứng dụng Spring Cloud đời cũ dùng Netflix Hystrix để cô lập lời gọi từ xa, giới hạn thời gian chờ, mở mạch khi phụ thuộc liên tục lỗi và trả fallback. Khi chuyển sang Spring Cloud CircuitBreaker, nhóm phát triển thường gặp các file cấu hình cũ vẫn còn trong repository nhưng không còn được đọc bởi runtime mới. Việc đổi tên một vài property không đủ để hoàn tất migration vì hai hệ thống có mô hình API, cách cô lập thread, cách tính sliding window và cách xuất metric khác nhau.

Spring Cloud CircuitBreaker cung cấp abstraction thống nhất cho circuit breaker. Resilience4j là một implementation phổ biến, có các module riêng cho CircuitBreaker, TimeLimiter, Bulkhead và Retry. Khi chuyển đổi, cần xác định rõ hành vi đang được ứng dụng sử dụng, ánh xạ từng trách nhiệm sang cơ chế mới và kiểm thử trước khi xóa cấu hình Hystrix cũ.

Sau bài học, bạn có thể:

- Nhận biết cấu hình Hystrix cũ và hiểu vì sao nó không tự động áp dụng cho Spring Cloud CircuitBreaker.
- Phân biệt command key, group key và thread-pool key của Hystrix với id và groupName của factory mới.
- Ánh xạ ngưỡng mở mạch, cửa sổ thống kê, timeout và isolation sang Resilience4j.
- Chọn SemaphoreBulkhead hoặc ThreadPoolBulkhead thay cho chiến lược isolation cũ.
- Chuyển fallback từ HystrixCommand sang API CircuitBreakerFactory hoặc Feign fallback.
- Nhận diện các tính năng Hystrix không có thay thế trực tiếp.
- Xây dựng kế hoạch migration có thể kiểm chứng và rollback an toàn.

## 1. Vì sao cấu hình Hystrix cũ không tự áp dụng?

Netflix Hystrix đã được đưa vào chế độ bảo trì và hệ sinh thái Spring Cloud Netflix đời mới không còn cung cấp tích hợp Hystrix như các release train cũ. Spring Cloud CircuitBreaker được xây dựng như một abstraction cho các implementation hiện đại, trong đó có Resilience4j.

Một ứng dụng có thể vẫn chứa cấu hình như:

    hystrix:
      command:
        default:
          execution:
            isolation:
              thread:
                timeoutInMilliseconds: 1000
          circuitBreaker:
            requestVolumeThreshold: 20
            errorThresholdPercentage: 50
            sleepWindowInMilliseconds: 10000

Việc giữ block YAML này trong application.yml không khiến Spring Cloud CircuitBreaker tự đọc và chuyển nó thành cấu hình Resilience4j. Hai namespace và mô hình cấu hình khác nhau. Nếu runtime mới không còn Hystrix integration, các property Hystrix cũ có thể chỉ còn là cấu hình không được sử dụng.

Trước khi sửa, hãy xác định:

- Ứng dụng đang chạy release train Spring Cloud nào.
- Dependency Hystrix còn xuất hiện trong runtime classpath hay chỉ còn trong file cấu hình.
- Lời gọi được bảo vệ bằng HystrixCommand, annotation, Feign integration hay wrapper tự viết.
- Các command đang dùng timeout, thread isolation, semaphore isolation, fallback, request cache, collapser hoặc dashboard nào.
- Có cấu hình Hystrix ở profile riêng, biến môi trường hoặc deployment manifest hay không.

Không xóa dependency và property cũ chỉ dựa trên tên file. Hãy xác nhận đường gọi thực tế và những tính năng đang được sử dụng.

## 2. So sánh mô hình Hystrix và Spring Cloud CircuitBreaker

Hystrix tổ chức bảo vệ quanh command. Mỗi command thường có command key, group key và có thể có thread-pool key. Spring Cloud CircuitBreaker cung cấp factory để tạo breaker theo id; với Resilience4j, có thể truyền thêm groupName để chọn cấu hình nhóm.

| Hystrix | Spring Cloud CircuitBreaker / Resilience4j | Ý nghĩa khi chuyển đổi |
| --- | --- | --- |
| commandKey | id truyền vào factory | Định danh breaker instance và phạm vi thống kê. |
| groupKey | Không tương đương trực tiếp; groupName của factory chủ yếu chọn cấu hình nhóm | Không giả định groupName mới có cùng vai trò nhóm service, metrics hoặc thread pool như Hystrix. |
| threadPoolKey | Cấu hình ThreadPoolBulkhead hoặc executor riêng | Cần thiết kế lại pool và giới hạn hàng đợi. |
| HystrixCommand | CircuitBreakerFactory và Supplier được bảo vệ | Thường cần chuyển code gọi command sang API mới. |
| fallbackMethod / getFallback | Hàm fallback của run hoặc Feign fallback/FallbackFactory | Cần giữ đúng semantics và phân loại lỗi. |
| execution.isolation.thread.timeoutInMilliseconds | TimeLimiter, timeout của HTTP client hoặc Reactor timeout | Chọn cơ chế phù hợp với kiểu thực thi; không phải một property thay tên. |
| execution.isolation.strategy | SemaphoreBulkhead hoặc ThreadPoolBulkhead | Cần chọn lại mô hình concurrency và thread ownership. |
| circuitBreaker.* | resilience4j.circuitbreaker.instances.* | Ngưỡng và sliding window có cách diễn đạt khác. |
| Hystrix Dashboard / Turbine | Micrometer, Actuator, Prometheus và dashboard tập trung | Xây lại metric, tag, event và cách tổng hợp nhiều instance. |

Các khái niệm có thể tương tự về mục đích nhưng không nhất thiết tương đương từng dòng. Hãy chuyển theo hành vi quan sát được, không chuyển cơ học tên property.

## 3. Ánh xạ command key, group key và thread-pool key

Trong Hystrix, command key nhận diện một command và thường được dùng để gắn cấu hình cùng metric. Group key gom command theo nhóm dịch vụ. Thread-pool key xác định pool được dùng cho command khi chạy ở THREAD isolation.

Trong Spring Cloud CircuitBreaker:

- id là tên breaker instance. Các lời gọi dùng cùng id thường dùng chung trạng thái và sliding window của breaker đó.
- groupName là thông tin bổ sung để factory phân giải cấu hình nhóm khi implementation hỗ trợ.
- ThreadPoolBulkhead có cấu hình và vòng đời riêng; không nên xem groupName là thread-pool key.

Ví dụ hai thao tác cùng dùng chính sách inventory nhưng cần thống kê riêng:

    CircuitBreaker readBreaker =
        circuitBreakerFactory.create("inventory-read", "inventory");

    CircuitBreaker reserveBreaker =
        circuitBreakerFactory.create("inventory-reserve", "inventory");

Hai id khác nhau tạo hai breaker độc lập. Cùng groupName có thể giúp dùng chung chính sách cấu hình, nhưng không hợp nhất trạng thái CLOSED, OPEN, HALF_OPEN hoặc sliding window.

Khi chuyển từ Hystrix, hãy lập bảng cho từng command:

| Command cũ | Phụ thuộc | Isolation/pool cũ | Breaker id mới | Nhóm cấu hình |
| --- | --- | --- | --- | --- |
| InventoryReadCommand | inventory-service | inventory-read-pool | inventory-read | inventory |
| InventoryReserveCommand | inventory-service | inventory-write-pool | inventory-reserve | inventory |
| PricingCommand | pricing-service | pricing-pool | pricing-quote | pricing |

Bảng trên chỉ là ví dụ. Không nên gộp read và reserve vào một id chỉ vì chúng gọi cùng service ID. Hãy xem xét SLO, timeout, lỗi nghiệp vụ, lưu lượng và fallback của từng thao tác.

## 4. Ánh xạ ngưỡng circuit breaker

Một block Hystrix thường có các property như:

    hystrix:
      command:
        inventory:
          circuitBreaker:
            requestVolumeThreshold: 20
            errorThresholdPercentage: 50
            sleepWindowInMilliseconds: 10000
          metrics:
            rollingStats:
              timeInMilliseconds: 10000
              numBuckets: 10

Resilience4j có thể diễn đạt chính sách tương ứng như sau:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-read:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

Các trường có ý nghĩa:

- slidingWindowType chọn cửa sổ theo số lượng lời gọi hoặc theo thời gian.
- slidingWindowSize là số mẫu với COUNT_BASED hoặc kích thước cửa sổ thời gian theo giây với TIME_BASED.
- minimumNumberOfCalls quy định số mẫu tối thiểu trước khi tính failure rate.
- failureRateThreshold là tỷ lệ lỗi để chuyển breaker sang OPEN.
- waitDurationInOpenState là thời gian chờ trước khi cho phép thử phục hồi.
- permittedNumberOfCallsInHalfOpenState giới hạn số lời gọi thử trong HALF_OPEN.

Ánh xạ cần chú ý:

| Hystrix property | Resilience4j gợi ý | Lưu ý |
| --- | --- | --- |
| requestVolumeThreshold | minimumNumberOfCalls | Cả hai liên quan số mẫu tối thiểu, nhưng cần kiểm tra semantics của phiên bản và cửa sổ. |
| errorThresholdPercentage | failureRateThreshold | Gần tương đương về tỷ lệ, nhưng tập mẫu và cách ghi nhận exception phải được xác minh. |
| sleepWindowInMilliseconds | waitDurationInOpenState | Chuyển đơn vị sang duration; hành vi HALF_OPEN và automatic transition cần kiểm tra. |
| metrics.rollingStats.timeInMilliseconds | slidingWindowType: TIME_BASED và slidingWindowSize | TIME_BASED dùng kích thước cửa sổ tính bằng giây; không chỉ đổi đơn vị rồi giả định bucket giống Hystrix. |
| metrics.rollingStats.numBuckets | Không có property tương đương trực tiếp trong cấu hình Resilience4j thông dụng | Resilience4j quản lý bucket của cửa sổ thời gian theo cách riêng. |
| forceOpen / forceClosed | Các trạng thái điều khiển hoặc cấu hình đặc biệt của Resilience4j | Không chuyển thành threshold giả; xác định quy trình vận hành và API quản trị phù hợp. |

Ví dụ Hystrix đặt requestVolumeThreshold bằng 20 không có nghĩa luôn phải đặt minimumNumberOfCalls bằng 20. Hãy kiểm tra lượng traffic, kiểu cửa sổ và cách Hystrix/Resilience4j tính mẫu. Một cửa sổ COUNT_BASED 20 và minimumNumberOfCalls 10 có thể bắt đầu đánh giá sau 10 mẫu, trong khi các tham số Hystrix cũ có thể được hiểu khác trong phiên bản đang chạy.

## 5. Chuyển timeout: không chỉ đổi tên property

Hystrix có thể giới hạn thời gian thực thi command bằng:

    hystrix:
      command:
        default:
          execution:
            isolation:
              thread:
                timeoutInMilliseconds: 1000

Trong hệ thống mới, timeout cần được đặt ở đúng tầng:

- HTTP client connect timeout giới hạn thời gian thiết lập kết nối.
- HTTP response/read timeout giới hạn thời gian chờ dữ liệu phản hồi theo khả năng client.
- Resilience4j TimeLimiter giới hạn CompletionStage/Future được hỗ trợ.
- Reactor timeout giới hạn thời gian publisher không phát tín hiệu.
- CircuitBreaker slowCallDurationThreshold phân loại lời gọi chậm, không tự hủy lời gọi.

Ví dụ TimeLimiter:

    resilience4j:
      timelimiter:
        instances:
          inventory-read:
            timeoutDuration: 1s
            cancelRunningFuture: true

TimeLimiter phù hợp với tác vụ bất đồng bộ dựa trên Future hoặc CompletionStage. Nó không tự biến một phương thức blocking thành non-blocking. Nếu client đồng bộ vẫn chạy trên request thread, cần đưa nó sang executor phù hợp và cấu hình timeout thực tế ở HTTP client.

Với WebClient, có thể dùng Reactor timeout:

    Mono<InventoryResponse> request = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(1));

Nếu dùng Resilience4j Reactor CircuitBreakerOperator, hãy đặt timeout trước operator để breaker quan sát TimeoutException, rồi đặt fallback sau operator:

    Mono<InventoryResponse> protectedRequest = request
        .timeout(Duration.ofSeconds(1))
        .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.just(InventoryResponse.unknown(sku))
        );

Timeout ở caller không bảo đảm server từ xa đã dừng xử lý. Với thao tác ghi như giữ hàng hoặc thanh toán, hãy kiểm tra idempotency và khả năng tra cứu trạng thái sau timeout.

## 6. Chuyển isolation THREAD và SEMAPHORE

Hystrix hỗ trợ hai chiến lược isolation phổ biến:

- THREAD: chạy command trên thread pool riêng, giúp cô lập tác vụ blocking và giới hạn concurrency.
- SEMAPHORE: giới hạn số lời gọi đồng thời bằng semaphore trên thread gọi hiện tại.

Resilience4j cung cấp hai loại Bulkhead có mục tiêu gần tương tự:

| Hystrix | Resilience4j | Hành vi |
| --- | --- | --- |
| THREAD isolation | ThreadPoolBulkhead | Chạy công việc trong pool riêng với giới hạn thread và queue. |
| SEMAPHORE isolation | SemaphoreBulkhead | Giới hạn số lời gọi đồng thời, không tự chuyển sang pool riêng. |

Cấu hình SemaphoreBulkhead:

    resilience4j:
      bulkhead:
        instances:
          inventory-read:
            maxConcurrentCalls: 20
            maxWaitDuration: 0

Cấu hình ThreadPoolBulkhead:

    resilience4j:
      thread-pool-bulkhead:
        instances:
          inventory-read:
            coreThreadPoolSize: 4
            maxThreadPoolSize: 8
            queueCapacity: 20
            keepAliveDuration: 20ms

Các con số chỉ minh họa. ThreadPoolBulkhead có pool và hàng đợi riêng; SemaphoreBulkhead chỉ cấp permit. Trong tích hợp Spring Cloud CircuitBreaker Resilience4j, khi resilience4j-bulkhead có trên classpath, Bulkhead có thể được áp dụng tự động; kiểu mặc định cho lời gọi đồng bộ thường là FixedThreadPoolBulkhead. Property enableSemaphoreDefaultBulkhead có thể chọn SemaphoreBulkhead làm mặc định cho lời gọi đồng bộ. Reactive integration dùng SemaphoreBulkhead.

Không giả định thread pool mới có cùng tên, kích thước, queue policy hoặc rejection behavior với Hystrix. Hãy tính tổng concurrency trên tất cả pod và giới hạn của dịch vụ nhận. Một pool 8 thread trên mỗi pod với 10 pod có thể tạo tải đồng thời lớn hơn nhiều so với một pool Hystrix cũ chỉ chạy trên một tiến trình.

Nếu ứng dụng dùng WebFlux, không đưa lời gọi WebClient non-blocking sang thread pool chỉ vì Hystrix trước đây dùng THREAD isolation. Với API blocking chưa thể thay thế, hãy offload bằng scheduler/executor phù hợp và đặt bulkhead để giới hạn concurrency.

## 7. Chuyển fallback và cách xử lý exception

Hystrix thường khai báo fallback qua getFallback(), fallbackMethod hoặc cơ chế tương ứng của command. Với Spring Cloud CircuitBreaker, có thể truyền fallback trực tiếp vào run:

    InventoryResponse result = circuitBreakerFactory
        .create("inventory-read")
        .run(
            () -> inventoryClient.find(sku),
            error -> InventoryResponse.unknown(sku)
        );

Với Feign, có thể bật tích hợp circuit breaker và dùng fallback hoặc FallbackFactory:

    @FeignClient(
        name = "inventory-service",
        fallbackFactory = InventoryFallbackFactory.class
    )
    public interface InventoryClient {
        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

FallbackFactory cho phép xem Throwable gây ra lỗi và chọn phản hồi theo nguyên nhân. Cần phân biệt ít nhất:

- Breaker OPEN: lời gọi bị từ chối, thường là CallNotPermittedException.
- Timeout: caller hết thời gian chờ; kết quả nghiệp vụ có thể chưa xác định.
- Bulkhead từ chối: không lấy được permit hoặc pool/queue đã đầy.
- Lỗi HTTP 5xx hoặc connection failure: phụ thuộc có thể không khả dụng.
- Lỗi nghiệp vụ 4xx: có thể là kết quả hợp lệ, không nhất thiết cần fallback.

Hystrix và Resilience4j có hệ exception khác nhau. Không giữ nguyên điều kiện bắt HystrixRuntimeException rồi giả định nó sẽ bắt được CallNotPermittedException hoặc BulkheadFullException. Hãy kiểm tra cause chain và phân loại exception theo HTTP client cùng implementation thực tế.

Fallback phải giữ semantics nghiệp vụ. Không trả quantity = 0 để biểu thị không truy vấn được tồn kho, và không trả thành công giả cho lệnh giữ hàng đã timeout. Có thể trả UNKNOWN, UNAVAILABLE hoặc PENDING cùng operation ID để caller tra cứu trạng thái.

Đặt fallback ở ngoài thao tác được bảo vệ. Nếu bắt exception bên trong Supplier và trả giá trị bình thường, circuit breaker có thể ghi nhận thành công thay vì failure.

## 8. Chuyển cấu hình Hystrix sang Resilience4j

Một cấu hình Hystrix cũ có thể trông như sau:

    hystrix:
      command:
        default:
          execution:
            isolation:
              strategy: THREAD
              thread:
                timeoutInMilliseconds: 1000
          circuitBreaker:
            requestVolumeThreshold: 20
            errorThresholdPercentage: 50
            sleepWindowInMilliseconds: 10000
        inventory:
          execution:
            isolation:
              strategy: SEMAPHORE
              semaphore:
                maxConcurrentRequests: 15

Cấu hình Resilience4j có thể được tổ chức thành nhiều phần độc lập:

    resilience4j:
      circuitbreaker:
        configs:
          inventory-policy:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3
        instances:
          inventory-read:
            baseConfig: inventory-policy
          inventory-reserve:
            baseConfig: inventory-policy

      timelimiter:
        instances:
          inventory-read:
            timeoutDuration: 1s
            cancelRunningFuture: true

      bulkhead:
        instances:
          inventory-read:
            maxConcurrentCalls: 15
            maxWaitDuration: 0

Cấu hình mới tách CircuitBreaker, TimeLimiter và Bulkhead thành các policy độc lập. Không đưa timeout hoặc concurrency vào nhánh circuitbreaker. Nếu dùng ThreadPoolBulkhead, cấu hình nằm trong resilience4j.thread-pool-bulkhead.instances.

Một policy có thể được dùng chung qua baseConfig, trong khi mỗi id giữ trạng thái và sliding window riêng. Cách này thường giúp giữ được mục tiêu vận hành chung mà không trộn thống kê của các thao tác khác nhau.

## 9. Những tính năng Hystrix không có thay thế một-một

Migration không hoàn tất nếu chỉ chuyển command và threshold. Hãy kiểm kê các tính năng Hystrix thực sự đang dùng:

| Tính năng cũ | Hướng xử lý trong kiến trúc mới |
| --- | --- |
| Hystrix Dashboard / Turbine | Xuất metric bằng Micrometer/Actuator, scrape tập trung bằng Prometheus và dựng dashboard mới. |
| Hystrix request cache | Thiết kế cache ứng dụng bằng Spring Cache, Caffeine hoặc Redis; xác định key và request scope rõ ràng. |
| Hystrix request collapser | Dùng batching, DataLoader hoặc cơ chế gom request phù hợp với API; không có thay thế tự động trong CircuitBreaker. |
| Hystrix concurrency strategy | Xem lại truyền context qua executor, TaskDecorator, Reactor Context hoặc Micrometer Context Propagation. |
| Hystrix command hooks/plugins | Dùng event publisher, customizer, observation và interceptor phù hợp với từng integration. |
| Thread pool metrics | Theo dõi executor/ThreadPoolBulkhead riêng cùng queue, active threads và rejection. |
| Hystrix properties | Chuyển từng hành vi sang cấu hình CircuitBreaker, TimeLimiter, Bulkhead, Retry hoặc HTTP client. |

Không giữ một tính năng cũ chỉ vì file cấu hình còn tồn tại. Hãy xác định code có thực sự gọi request cache, collapser hoặc plugin hay không. Nếu không dùng, có thể loại bỏ sau khi xác minh. Nếu đang dùng, phải thiết kế lại trước khi xóa dependency.

## 10. Chuyển metric và cảnh báo

Hystrix Dashboard thường tập trung vào command metrics và thread-pool metrics. Với Resilience4j, các metric có thể được xuất qua Micrometer khi dependency và auto-configuration phù hợp được bật.

Những nhóm metric nên dựng lại:

- Trạng thái CLOSED, OPEN và HALF_OPEN theo breaker name.
- Số lời gọi thành công, thất bại, ignored và bị từ chối.
- Failure rate và slow call rate.
- Thời lượng lời gọi và phân bố latency.
- Số lần chuyển trạng thái và thời gian giữ OPEN.
- Bulkhead active calls, rejected calls, queue và thread-pool utilization.
- TimeLimiter timeout và tỷ lệ fallback.

Metric names và tag có thể khác giữa các phiên bản Resilience4j/Micrometer. Hãy truy vấn endpoint metrics hoặc Prometheus của ứng dụng sau migration để lấy tên thực tế. Không sao chép dashboard Hystrix rồi chỉ đổi tên series.

Giữ breaker name, service và pod làm dimension có kiểm soát. Tránh tag bằng request ID, SKU hoặc exception message vì cardinality tăng rất nhanh. Dùng log và trace có correlation ID để điều tra từng request.

## 11. Kế hoạch migration theo từng bước

Một migration an toàn nên diễn ra theo từng command hoặc nhóm lời gọi:

1. **Kiểm kê:** liệt kê HystrixCommand, command key, group key, thread-pool key, property, fallback và metric đang dùng.
2. **Xác định ranh giới:** quyết định breaker id theo phụ thuộc và thao tác; không gộp các lỗi nghiệp vụ khác nhau vào cùng window.
3. **Chọn implementation:** xác nhận starter Spring Cloud CircuitBreaker và Resilience4j tương thích với Spring Boot/release train.
4. **Ánh xạ policy:** chuyển sliding window, failure threshold, wait duration, timeout và bulkhead sang đúng namespace.
5. **Chuyển code:** thay HystrixCommand bằng factory hoặc Feign integration; chuyển fallback và exception mapping.
6. **Chuyển observability:** dựng metric, event, dashboard và alert mới trước khi loại dashboard cũ.
7. **Kiểm thử:** mô phỏng success, HTTP 5xx, timeout, slow call, breaker OPEN, HALF_OPEN, bulkhead rejection và fallback.
8. **Triển khai có kiểm soát:** rollout một nhóm service hoặc một thao tác, theo dõi latency, rejection, lỗi và tài nguyên.
9. **Loại cấu hình cũ:** chỉ xóa Hystrix dependency/property sau khi xác nhận không còn code hoặc profile nào sử dụng.
10. **Đánh giá rollback:** giữ artifact và cấu hình triển khai cũ trong khoảng thời gian rollback đã thống nhất.

Không bật đồng thời hai lớp breaker cho cùng một lời gọi nếu chưa có thiết kế rõ. Breaker lồng nhau có thể tạo hai sliding window, hai timeout và hai fallback khác nhau, khiến request bị chặn ở lớp không mong muốn.

## 12. Ma trận kiểm thử sau migration

| Kịch bản | Hành vi cần xác minh |
| --- | --- |
| Phụ thuộc trả thành công nhanh | Kết quả chính được trả; breaker ghi nhận success. |
| Phụ thuộc trả HTTP 5xx | Exception được phân loại đúng; fallback chạy theo policy; breaker ghi nhận failure. |
| Phụ thuộc timeout | Caller hết hạn theo deadline; breaker nhìn thấy timeout nếu được cấu hình record. |
| Lời gọi chậm nhưng vẫn thành công | Slow call rate tăng; không nhầm slow threshold với timeout. |
| Breaker OPEN | Supplier không chạy; lời gọi bị từ chối nhanh và fallback phù hợp. |
| HALF_OPEN | Chỉ số lời gọi thử được phép chạy; kết quả quyết định đóng hoặc mở lại. |
| Bulkhead đầy | Lời gọi bị từ chối theo policy; phân biệt với breaker OPEN. |
| Lỗi nghiệp vụ như hết hàng | Không làm breaker mở nếu exception được xác định là kết quả nghiệp vụ cần ignore. |
| Tác vụ blocking | Không chiếm event loop; timeout và cancellation được kiểm tra ở tầng client/executor. |
| Nhiều pod | Trạng thái breaker và metric cục bộ được tổng hợp đúng, không giả định state chia sẻ giữa JVM. |

Ngoài response cuối cùng, hãy xác nhận số HTTP attempt, trạng thái breaker, số lần fallback, số tác vụ còn chạy sau timeout và mức dùng thread/queue. Một migration chỉ đúng khi hành vi vận hành tương đương với mục tiêu đã định, không chỉ khi ứng dụng biên dịch thành công.

## 13. Bài thực hành: chuyển một Hystrix command sang Resilience4j

Giả sử ứng dụng cũ có InventoryCommand dùng THREAD isolation, timeout 1 giây, mở mạch khi failure rate đạt 50% sau đủ mẫu và trả fallback UNKNOWN.

**Phần A — Ghi nhận hành vi cũ**

1. Ghi lại command key, group key, thread-pool key và toàn bộ property đang áp dụng.
2. Xác định command gọi endpoint nào và lỗi nào được tính vào failure rate.
3. Đo concurrency, queue, timeout, fallback và metric trong môi trường test.
4. Xác định có dùng request cache, collapser hoặc custom concurrency strategy không.

**Phần B — Tạo cấu hình mới**

1. Thêm Spring Cloud CircuitBreaker Resilience4j starter tương thích.
2. Tạo breaker id inventory-read.
3. Khai báo sliding window, minimumNumberOfCalls, failureRateThreshold và waitDurationInOpenState.
4. Chọn ThreadPoolBulkhead nếu cần cô lập blocking work; chọn SemaphoreBulkhead nếu chỉ cần giới hạn concurrency.
5. Cấu hình HTTP client timeout hoặc TimeLimiter phù hợp với kiểu lời gọi.
6. Đăng ký metric và event cho breaker mới.

**Phần C — Chuyển code và so sánh**

1. Thay HystrixCommand bằng CircuitBreakerFactory hoặc Feign integration.
2. Đưa fallback UNKNOWN ra ngoài Supplier được bảo vệ.
3. Kiểm tra exception timeout, lỗi HTTP và lỗi nghiệp vụ.
4. Mô phỏng đủ lỗi để breaker OPEN; xác nhận lời gọi tiếp theo không gọi server.
5. Mô phỏng phục hồi để xác nhận HALF_OPEN và CLOSED.
6. So sánh latency, throughput, concurrency, số lần từ chối và fallback với hệ thống cũ.
7. Kiểm tra không còn request cache/collapser hoặc plugin Hystrix nào bị bỏ quên.

Khi hoàn thành, bạn cần giải thích được vì sao Hystrix property không tự áp dụng cho Resilience4j, id khác groupName ở đâu, timeout khác slow-call threshold thế nào và vì sao THREAD isolation cần được thiết kế lại bằng executor hoặc ThreadPoolBulkhead. Hãy hoàn tất kiểm kê và kiểm thử hành vi trước khi xóa cấu hình cũ.

## Tài liệu tham khảo

- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
- Spring Cloud CircuitBreaker — Reference: https://docs.spring.io/spring-cloud-circuitbreaker/reference/index.html
- Resilience4j — CircuitBreaker: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Bulkhead: https://resilience4j.readme.io/docs/bulkhead
- Resilience4j — TimeLimiter: https://resilience4j.readme.io/docs/timeout

