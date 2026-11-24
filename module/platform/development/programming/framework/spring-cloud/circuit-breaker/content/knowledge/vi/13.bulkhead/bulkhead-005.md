# Tích hợp tự động khi resilience4j-bulkhead có trên classpath

## Mục tiêu của bài học

Spring Cloud CircuitBreaker có thể tự tích hợp Bulkhead của Resilience4j khi thư viện resilience4j-bulkhead xuất hiện trên classpath. Nhờ cơ chế này, các lời gọi được tạo qua CircuitBreaker factory có thể được giới hạn số lượng thực thi đồng thời mà không cần tự trang trí từng Supplier bằng Bulkhead ở mọi vị trí.

Tuy nhiên, tích hợp tự động không có nghĩa ứng dụng tự biết giới hạn phù hợp. Nhóm phát triển vẫn cần chọn kiểu bulkhead, đặt giới hạn thread hoặc số lời gọi đồng thời, quyết định cách xử lý khi bị từ chối và quan sát tải thực tế.

Sau bài học, bạn có thể:

- Giải thích điều kiện classpath kích hoạt tích hợp Bulkhead của Spring Cloud CircuitBreaker.
- Nhận biết hành vi mặc định FixedThreadPoolBulkhead và cách chọn SemaphoreBulkhead.
- Tắt tích hợp tự động khi ứng dụng không muốn dùng Bulkhead do Spring Cloud cung cấp.
- Cấu hình SemaphoreBulkhead và ThreadPoolBulkhead bằng application.yml.
- Tùy chỉnh cấu hình mặc định hoặc riêng từng breaker bằng Resilience4jBulkheadProvider.
- Phân biệt tích hợp Bulkhead cho lời gọi đồng bộ và pipeline reactive.
- Xử lý tình huống bulkhead từ chối lời gọi và theo dõi hiệu quả cô lập tài nguyên.

## 1. Điều kiện kích hoạt tích hợp tự động

Spring Cloud CircuitBreaker hỗ trợ Bulkhead của Resilience4j. Khi dependency resilience4j-bulkhead có trên classpath, Spring Cloud CircuitBreaker tự động bọc các lời gọi qua implementation Resilience4j bằng một Bulkhead.

Dependency Maven có thể được khai báo như sau nếu dự án chưa có thư viện này thông qua dependency khác:

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-bulkhead</artifactId>
    </dependency>

Với Gradle:

    implementation("io.github.resilience4j:resilience4j-bulkhead")

Ví dụ giả định phiên bản dependency được quản lý bởi BOM phù hợp với Spring Boot, Spring Cloud và Resilience4j của dự án. Nếu chưa có dependency management, hãy chọn một bộ phiên bản tương thích và quản lý tập trung thay vì tự thêm một phiên bản tùy ý.

Spring Cloud CircuitBreaker có starter Resilience4j cho ứng dụng đồng bộ và reactive:

| Mô hình ứng dụng | Starter |
| --- | --- |
| Lời gọi không reactive | spring-cloud-starter-circuitbreaker-resilience4j |
| Lời gọi reactive với Reactor | spring-cloud-starter-circuitbreaker-reactor-resilience4j |

Không nên kết luận rằng chỉ khai báo starter là Bulkhead chắc chắn đã được bật trong mọi cấu hình. Điều kiện tích hợp được tài liệu Spring Cloud nêu rõ là resilience4j-bulkhead có trên classpath. Hãy kiểm tra dependency tree hoặc runtime classpath để biết thư viện có thực sự được nạp hay không.

Ví dụ một lời gọi qua factory:

    CircuitBreaker breaker = circuitBreakerFactory.create("inventory");

    InventoryResponse response = breaker.run(
        () -> inventoryClient.find(sku),
        error -> InventoryResponse.unknown(sku)
    );

Khi tích hợp Bulkhead được bật, Spring Cloud CircuitBreaker áp dụng cơ chế bulkhead cho lời gọi được thực hiện qua factory. Điều này không có nghĩa mọi phương thức Java trong ứng dụng đều tự động bị chặn hoặc giới hạn. Một phương thức chỉ được bảo vệ nếu nó đi qua đường thực thi CircuitBreaker tương ứng.

## 2. Hành vi mặc định và hai kiểu Bulkhead

Resilience4j cung cấp hai implementation chính:

| Kiểu | Cơ chế | Tác động |
| --- | --- | --- |
| FixedThreadPoolBulkhead | Dùng thread pool cố định và hàng đợi có giới hạn. | Cô lập công việc trong pool riêng; giới hạn số thread và số tác vụ chờ. |
| SemaphoreBulkhead | Dùng semaphore để cấp quyền thực thi. | Giới hạn số lời gọi đồng thời; không tự chuyển công việc sang thread pool riêng. |

Với tích hợp Spring Cloud CircuitBreaker Resilience4j cho lời gọi không reactive, mặc định là FixedThreadPoolBulkhead. Nó sử dụng pool và queue có giới hạn để kiểm soát lượng công việc có thể chạy hoặc chờ.

Nếu muốn dùng SemaphoreBulkhead làm mặc định cho lời gọi không reactive, đặt:

    spring:
      cloud:
        circuitbreaker:
          resilience4j:
            enableSemaphoreDefaultBulkhead: true

SemaphoreBulkhead kiểm tra số permit còn lại. Khi có permit, lời gọi được thực thi trên thread hiện tại trong phạm vi cơ chế semaphore. Khi hết permit, lời gọi có thể bị từ chối ngay hoặc chờ tối đa thời gian được cấu hình.

Không nhầm SemaphoreBulkhead với FixedThreadPoolBulkhead. Semaphore chỉ giới hạn concurrency; nó không tạo pool thread để offload tác vụ blocking. Nếu cần cô lập thread và hàng đợi, chọn thread-pool bulkhead và cấu hình pool phù hợp.

## 3. Tắt tích hợp Bulkhead tự động

Nếu ứng dụng không muốn Spring Cloud CircuitBreaker tự áp dụng Bulkhead, có thể tắt tính năng này bằng property:

    spring:
      cloud:
        circuitbreaker:
          bulkhead:
            resilience4j:
              enabled: false

Property này tắt tích hợp Bulkhead Resilience4j của Spring Cloud CircuitBreaker. Nó không tắt toàn bộ circuit breaker và cũng không xóa dependency khỏi classpath. Circuit breaker vẫn có thể tiếp tục bảo vệ lời gọi nếu auto-configuration CircuitBreaker còn được bật.

Việc tắt Bulkhead tự động có thể phù hợp khi ứng dụng đã có cơ chế giới hạn concurrency riêng hoặc đang chuyển đổi cách cấu hình. Trước khi tắt, hãy xác nhận có lớp bảo vệ khác thay thế và kiểm tra số lời gọi đồng thời thực tế. Nếu không có cơ chế thay thế, một phụ thuộc chậm có thể chiếm nhiều thread hoặc kết nối hơn dự kiến.

Để tắt toàn bộ auto-configuration Resilience4j CircuitBreaker, có property riêng là spring.cloud.circuitbreaker.resilience4j.enabled=false. Không dùng property này nếu mục tiêu chỉ là tắt Bulkhead.

## 4. Cấu hình SemaphoreBulkhead bằng properties

SemaphoreBulkhead phù hợp khi muốn giới hạn số lời gọi đồng thời mà không cần tạo pool thread riêng. Cấu hình instance trong application.yml:

    resilience4j:
      bulkhead:
        instances:
          inventory:
            maxConcurrentCalls: 12
            maxWaitDuration: 0

Trong đó:

- maxConcurrentCalls là số lời gọi tối đa được phép thực thi đồng thời qua bulkhead inventory.
- maxWaitDuration là thời gian tối đa chờ permit khi đã đạt giới hạn. Giá trị 0 có nghĩa là không chờ; lời gọi không lấy được permit sẽ bị từ chối ngay.

Tên instance inventory cần khớp với id mà ứng dụng truyền vào factory.create("inventory"). Nếu dùng id inventory-read, cấu hình phải nằm dưới instances.inventory-read.

Ví dụ cấu hình chung và instance riêng:

    resilience4j:
      bulkhead:
        configs:
          default:
            maxConcurrentCalls: 8
            maxWaitDuration: 0
          inventory-policy:
            maxConcurrentCalls: 12
            maxWaitDuration: 100ms
        instances:
          inventory:
            baseConfig: inventory-policy
            maxConcurrentCalls: 10
          pricing:
            baseConfig: default

Cấu hình instances cho từng bulkhead cho phép tinh chỉnh theo phụ thuộc. inventory có tối đa 10 lời gọi đồng thời; pricing kế thừa giới hạn mặc định là 8. Các giá trị này chỉ để minh họa và cần được chọn dựa trên năng lực dịch vụ phụ thuộc, số instance ứng dụng và ngân sách tài nguyên.

## 5. Cấu hình FixedThreadPoolBulkhead bằng properties

FixedThreadPoolBulkhead sử dụng thread pool cố định cùng hàng đợi có giới hạn. Ví dụ:

    resilience4j:
      thread-pool-bulkhead:
        instances:
          inventory:
            coreThreadPoolSize: 2
            maxThreadPoolSize: 4
            queueCapacity: 10
            keepAliveDuration: 20ms

Các thuộc tính chính:

- coreThreadPoolSize: số thread lõi của pool.
- maxThreadPoolSize: số thread tối đa.
- queueCapacity: số tác vụ tối đa có thể chờ trong hàng đợi.
- keepAliveDuration: thời gian giữ thread dư khi pool có thể thu hẹp theo cấu hình.

Khi số thread đang bận và hàng đợi đã đầy, tác vụ mới bị từ chối. Hàng đợi không nên đặt quá lớn chỉ để tránh từ chối: queue dài làm tăng thời gian chờ và có thể khiến yêu cầu hết hạn trước khi được thực thi.

Chọn pool dựa trên thời gian blocking, năng lực dịch vụ phụ thuộc và số instance của ứng dụng. Ví dụ, nếu mỗi pod có 4 thread dành cho inventory và chạy 6 pod, tổng số lời gọi có thể đồng thời đến inventory có thể xấp xỉ 24, chưa tính các nguồn gọi khác. Hãy tính tổng tải ở cấp hệ thống thay vì chỉ nhìn cấu hình của một pod.

SemaphoreBulkhead và ThreadPoolBulkhead có cấu hình properties riêng. Đừng đặt maxConcurrentCalls trong nhánh thread-pool-bulkhead hoặc đặt maxThreadPoolSize trong nhánh bulkhead; các thuộc tính phải nằm đúng loại instance.

## 6. Tùy chỉnh cấu hình mặc định bằng Java Customizer

Spring Cloud CircuitBreaker cung cấp Resilience4jBulkheadProvider để tùy chỉnh Bulkhead và ThreadPoolBulkhead. Có thể định nghĩa cấu hình mặc định cho các breaker:

    @Bean
    public Customizer<Resilience4jBulkheadProvider> defaultBulkheadCustomizer() {
        return provider -> provider.configureDefault(id ->
            new Resilience4jBulkheadConfigurationBuilder()
                .bulkheadConfig(
                    BulkheadConfig.custom()
                        .maxConcurrentCalls(4)
                        .build()
                )
                .threadPoolBulkheadConfig(
                    ThreadPoolBulkheadConfig.custom()
                        .coreThreadPoolSize(1)
                        .maxThreadPoolSize(2)
                        .build()
                )
                .build()
        );
    }

Customizer mặc định hữu ích khi muốn dùng một chính sách chung cho nhiều breaker. Nếu các phụ thuộc có năng lực khác nhau, có thể cấu hình riêng theo id:

    @Bean
    public Customizer<Resilience4jBulkheadProvider> inventoryBulkheadCustomizer() {
        return provider -> provider.configure(
            builder -> builder
                .bulkheadConfig(
                    BulkheadConfig.custom()
                        .maxConcurrentCalls(10)
                        .build()
                )
                .threadPoolBulkheadConfig(
                    ThreadPoolBulkheadConfig.custom()
                        .coreThreadPoolSize(2)
                        .maxThreadPoolSize(4)
                        .build()
                ),
            "inventory"
        );
    }

Đây là ví dụ cấu hình cả hai loại bulkhead cho id inventory. Việc implementation nào được sử dụng phụ thuộc loại factory và cấu hình lựa chọn bulkhead. Không cần tạo cả hai loại nếu ứng dụng chỉ sử dụng một kiểu.

Khi cấu hình bằng properties và Java Customizer cùng tồn tại, properties có độ ưu tiên cao hơn Customizer. Riêng với cấu hình instance và nhóm, tài liệu Bulkhead Properties Configuration nêu thứ tự ưu tiên:

1. Properties của instances.
2. Cấu hình từ Resilience4JBulkheadProvider Customizer.
3. Properties của configs dùng chung.

Vì vậy, thay đổi Java Customizer có thể không ảnh hưởng đến instance đã có cấu hình properties. Khi cần chẩn đoán, hãy kiểm tra cả hai nơi và xác định nguồn cấu hình đang thắng.

## 7. Tích hợp tự động trong pipeline reactive

Với Spring Cloud CircuitBreaker reactive, Bulkhead được áp dụng thông qua ReactiveResilience4jBulkheadProvider để trang trí Mono và Flux. Tích hợp reactive của Spring Cloud CircuitBreaker Resilience4j chỉ sử dụng SemaphoreBulkhead.

Điều này có nghĩa:

- Pipeline reactive vẫn giữ kiểu publisher Mono hoặc Flux.
- Semaphore giới hạn số subscription hoặc lời gọi đồng thời theo bulkhead đã cấu hình.
- Bulkhead không chuyển pipeline sang một fixed thread pool riêng.
- Nếu property enableSemaphoreDefaultBulkhead=false, reactive provider vẫn sử dụng SemaphoreBulkhead và sẽ ghi log cảnh báo theo tài liệu.

Có thể tùy chỉnh bulkhead reactive bằng Customizer:

    @Bean
    public Customizer<ReactiveResilience4jBulkheadProvider> reactiveBulkheadCustomizer() {
        return provider -> provider.configureDefault(id ->
            new Resilience4jBulkheadConfigurationBuilder()
                .bulkheadConfig(
                    BulkheadConfig.custom()
                        .maxConcurrentCalls(4)
                        .build()
                )
                .build()
        );
    }

Để cấu hình một id riêng:

    @Bean
    public Customizer<ReactiveResilience4jBulkheadProvider> inventoryReactiveBulkheadCustomizer() {
        return provider -> provider.configure(builder ->
            builder.bulkheadConfig(
                BulkheadConfig.custom()
                    .maxConcurrentCalls(2)
                    .build()
            ),
            "inventory"
        );
    }

Trong pipeline reactive, không cần tự gọi block() để chờ lấy permit. Provider tích hợp operator vào publisher. Khi số lời gọi đang hoạt động đạt giới hạn, lời gọi mới có thể bị từ chối theo chính sách bulkhead.

Nếu cần xử lý một API blocking trong pipeline reactive, SemaphoreBulkhead không tự giải phóng event loop. Hãy offload API blocking bằng subscribeOn(Schedulers.boundedElastic()) như đã học, đồng thời dùng bulkhead để giới hạn concurrency. Hai cơ chế có vai trò riêng.

## 8. Kết hợp Bulkhead với CircuitBreaker và fallback

Bulkhead và CircuitBreaker bảo vệ hai giới hạn khác nhau:

- Bulkhead giới hạn số tác vụ đồng thời hoặc số worker/queue được phép dùng.
- CircuitBreaker theo dõi kết quả, tỷ lệ lỗi và lời gọi chậm để chuyển trạng thái CLOSED, OPEN, HALF_OPEN.

Một lời gọi có thể bị từ chối vì hết permit bulkhead ngay cả khi circuit breaker đang CLOSED. Ngược lại, breaker có thể OPEN dù bulkhead vẫn còn permit. Hãy phân biệt nguyên nhân từ chối khi xử lý lỗi.

Ví dụ với CircuitBreakerFactory:

    CircuitBreaker breaker = circuitBreakerFactory.create("inventory");

    InventoryResponse response = breaker.run(
        () -> inventoryClient.find(sku),
        error -> {
            if (error instanceof BulkheadFullException) {
                return InventoryResponse.busy(sku);
            }
            if (error instanceof CallNotPermittedException) {
                return InventoryResponse.unavailable(sku);
            }
            return InventoryResponse.unknown(sku);
        }
    );

InventoryResponse.busy, unavailable và unknown là các trạng thái do ứng dụng định nghĩa. Ví dụ này phân biệt việc phụ thuộc đang quá tải ở mức concurrency với trường hợp circuit breaker đang mở. Trong thực tế, hãy xác nhận loại exception mà implementation và phiên bản Resilience4j đang sử dụng phát ra.

Fallback cần nhanh và không thực hiện lại lời gọi đến cùng phụ thuộc đang bị giới hạn. Nếu bulkhead từ chối do quá tải, fallback có thể trả trạng thái bận, dùng cache còn hợp lệ hoặc yêu cầu thử lại sau. Không nên tự retry ngay lập tức trong fallback vì điều đó có thể tạo thêm tải vào đúng thời điểm hệ thống đang thiếu năng lực xử lý.

## 9. Bulkhead không thay thế timeout hoặc giới hạn tải tổng thể

Bulkhead kiểm soát số công việc đồng thời, nhưng không đảm bảo từng công việc hoàn tất trong thời gian hợp lý. Một pool có 4 thread vẫn có thể bị chiếm lâu nếu HTTP client không có timeout. Hãy kết hợp:

| Cơ chế | Trách nhiệm |
| --- | --- |
| Bulkhead | Giới hạn concurrency và tài nguyên dành cho phụ thuộc. |
| Timeout / TimeLimiter | Giới hạn thời gian chờ của từng lời gọi hoặc tác vụ được hỗ trợ. |
| CircuitBreaker | Ngừng gửi lời gọi mới khi phụ thuộc có dấu hiệu lỗi kéo dài. |
| Retry | Thử lại có giới hạn với lỗi thoáng qua và có backoff. |

Khi tính giới hạn, cần xem xét số pod, số thread, queue capacity, connection pool và giới hạn phía dịch vụ nhận. Nếu có 8 pod, mỗi pod cho phép 10 lời gọi inventory đồng thời, tổng tải tiềm năng từ ứng dụng có thể lên đến 80 lời gọi. Một giới hạn phù hợp ở từng pod vẫn có thể vượt quá năng lực tổng thể của inventory-service.

Không dùng queue capacity lớn để giữ tất cả request. Hàng đợi dài làm tăng latency, giữ tài nguyên và có thể khiến request hết hạn trước khi được xử lý. Từ chối sớm với một fallback phù hợp thường dễ kiểm soát hơn việc tích lũy một lượng công việc không thể xử lý kịp.

## 10. Quan sát và xác minh tích hợp tự động

Sau khi thêm dependency và cấu hình, hãy xác minh ứng dụng thực sự tạo Bulkhead cho đúng id:

- Kiểm tra dependency tree hoặc runtime classpath có resilience4j-bulkhead.
- Xác nhận Spring Cloud CircuitBreaker Resilience4j auto-configuration đang bật.
- Kiểm tra property bulkhead.resilience4j.enabled không bị đặt false.
- Xác nhận kiểu bulkhead đang sử dụng: FixedThreadPoolBulkhead hay SemaphoreBulkhead.
- Kiểm tra cấu hình instance có cùng id với factory.create(id).
- Tạo tải vượt giới hạn và quan sát số lời gọi bị từ chối.
- Kiểm tra fallback và log để phân biệt BulkheadFullException với CallNotPermittedException.

Resilience4j cung cấp event publisher để quan sát sự kiện của Bulkhead. Spring Cloud CircuitBreaker cho phép gắn customizer sau khi bulkhead được tạo, ví dụ:

    @Bean
    public Customizer<Resilience4jBulkheadProvider> bulkheadEventCustomizer() {
        return provider -> provider.addBulkheadCustomizer(
            bulkhead -> bulkhead.getEventPublisher()
                .onCallRejected(event -> log.warn("Bulkhead rejected: {}", event))
                .onCallFinished(event -> log.debug("Bulkhead finished: {}", event)),
            "inventory"
        );
    }

Theo dõi thêm số lời gọi đang chạy, số lời gọi bị từ chối, queue utilization đối với thread-pool bulkhead, thời gian chờ và độ trễ của phụ thuộc. Nếu bulkhead từ chối thường xuyên trong điều kiện tải bình thường, giới hạn có thể quá thấp hoặc phụ thuộc đang xử lý chậm. Nếu queue thường xuyên đầy, hãy xem lại timeout, concurrency và năng lực dịch vụ nhận.

## 11. Bài thực hành: bật tích hợp bằng classpath

Tạo một gateway gọi inventory-service thông qua Spring Cloud CircuitBreaker và thực hiện các bước:

1. Kiểm tra resilience4j-bulkhead có trên classpath. Nếu chưa có, thêm dependency và để BOM tương thích quản lý phiên bản.
2. Tạo breaker bằng id inventory.
3. Chạy ứng dụng với cấu hình mặc định và xác định implementation bulkhead được chọn.
4. Thêm cấu hình SemaphoreBulkhead với maxConcurrentCalls bằng 4 và maxWaitDuration bằng 0.
5. Tạo tải đồng thời lớn hơn 4 và quan sát các lời gọi vượt giới hạn bị từ chối.
6. Thử cấu hình FixedThreadPoolBulkhead với pool 2 thread và queue capacity 5 trong ứng dụng không reactive.
7. Bật enableSemaphoreDefaultBulkhead để chuyển mặc định đồng bộ sang SemaphoreBulkhead.
8. Tắt property bulkhead.resilience4j.enabled và xác nhận Bulkhead tự động không còn được áp dụng.
9. Với ứng dụng reactive, dùng ReactiveResilience4jBulkheadProvider và xác nhận pipeline vẫn dùng SemaphoreBulkhead.
10. Bật CircuitBreaker và tạo lỗi liên tiếp để quan sát Bulkhead và CircuitBreaker từ chối lời gọi vì hai nguyên nhân khác nhau.

Khi hoàn thành, bạn cần giải thích được vì sao classpath kích hoạt tích hợp, kiểu bulkhead mặc định của lời gọi đồng bộ, hành vi semaphore trong reactive pipeline và cách cấu hình riêng theo id. Bạn cũng cần phân biệt Bulkhead với CircuitBreaker, timeout và retry để lựa chọn giới hạn phù hợp với năng lực thực tế của từng phụ thuộc.

## Tài liệu tham khảo

- Spring Cloud CircuitBreaker — Bulkhead pattern supporting: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/bulkhead-pattern-supporting.html
- Spring Cloud CircuitBreaker — Bulkhead properties configuration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/bulkhead-properties-configuration.html
- Spring Cloud CircuitBreaker — Configuring Resilience4J Circuit Breakers: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html

