# Kiểm tra thay đổi mặc định của TimeLimiter, Bulkhead và quy tắc đặt tên

Khi nâng cấp Spring Cloud CircuitBreaker hoặc Resilience4j, ứng dụng có thể tiếp tục khởi động thành công nhưng hành vi bảo vệ dependency đã thay đổi. Một cấu hình không khai báo TimeLimiter hoặc Bulkhead có thể dựa vào giá trị mặc định của provider. Nếu mặc định về thời gian chờ, loại bulkhead hoặc cách phân giải tên instance khác với điều đội phát triển đang giả định, request có thể bị timeout sớm hơn, chạy trên thread pool khác hoặc không nhận được cấu hình riêng như mong muốn.

Một lần migration an toàn cần kiểm tra cả ba lớp: phiên bản thư viện thực tế, cấu hình hiệu lực sau khi Spring bind properties và hành vi runtime khi có tải hoặc lỗi. Không nên chỉ so sánh file YAML trước và sau nâng cấp. Cần xác nhận tên ID mà code truyền vào factory, tên instance trong cấu hình Resilience4j và group name nếu ứng dụng sử dụng cấu hình theo nhóm.

Bài học hướng dẫn cách kiểm tra TimeLimiter, lựa chọn Bulkhead mặc định, quy tắc đặt tên ID/group, độ ưu tiên giữa properties và Java Customizer, cùng một quy trình kiểm chứng trước khi đưa phiên bản mới vào production.

## 1. Vì sao cần kiểm tra mặc định khi migration?

Spring Cloud CircuitBreaker là abstraction cho phép ứng dụng dùng Circuit Breaker provider như Resilience4j. Provider chịu trách nhiệm tạo và kết hợp các policy cụ thể. Khi nâng cấp Spring Cloud release train, Spring Boot hoặc Resilience4j, các lớp cấu hình và mặc định có thể được điều chỉnh.

Những thay đổi có tác động rõ đến runtime gồm:

- **TimeLimiter:** thời gian tối đa chờ kết quả, cách hủy Future và đường thực thi mà TimeLimiter bao quanh.
- **Bulkhead:** dùng semaphore trên thread gọi hay dùng thread pool và queue riêng.
- **Tên instance:** ID truyền vào CircuitBreakerFactory có khớp với khóa cấu hình Circuit Breaker, TimeLimiter và Bulkhead hay không.
- **Group configuration:** group name có được truyền vào factory và có cấu hình tương ứng hay không.
- **Cấu hình Java và properties:** giá trị từ application.yml có thể được ưu tiên hơn customizer trong code.
- **Vòng đời instance:** thay đổi cấu hình có được áp dụng lúc khởi động hay cần tạo lại instance/restart ứng dụng.

Một ứng dụng có thể không có lỗi biên dịch nhưng vẫn gặp các vấn đề như request timeout sau một giây, thread pool bulkhead đầy, MDC bị mất khi chuyển thread hoặc cấu hình inventory không được áp dụng vì code dùng một ID khác.

## 2. Lập bảng phiên bản trước khi thay đổi

Trước khi sửa cấu hình, hãy ghi lại phiên bản thực tế của các thành phần liên quan. Phiên bản khai báo trong file build không phải lúc nào cũng là phiên bản cuối cùng trên runtime vì BOM, dependency management hoặc dependency bắc cầu có thể ghi đè.

| Thành phần | Cần ghi nhận | Lý do |
| --- | --- | --- |
| Java | JDK đang build và chạy | Kiểm tra tương thích bytecode và API |
| Spring Boot | Phiên bản từ dependency management | Xác định Actuator, Micrometer và cấu hình auto-configuration |
| Spring Cloud | Release train/BOM | Xác định API CircuitBreakerFactory và provider integration |
| Spring Cloud CircuitBreaker | Phiên bản artifact Resilience4j | Xác định default provider, customizer và property binding |
| Resilience4j | Phiên bản các module core, Spring Boot và Micrometer | Xác định TimeLimiter, Bulkhead và state API |
| HTTP client | WebClient, RestClient hoặc client khác | Xác định connect/response timeout và cancellation |

Dùng dependency tree hoặc dependency insight của công cụ build để tìm phiên bản thực tế. Ví dụ với Maven:

~~~bash
mvn dependency:tree
~~~

Có thể lọc kết quả theo các artifact liên quan như spring-cloud-starter-circuitbreaker-resilience4j, resilience4j-circuitbreaker, resilience4j-timelimiter, resilience4j-bulkhead và resilience4j-spring-boot3.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Không nâng riêng một module Resilience4j lên phiên bản khác với BOM của Spring Cloud nếu chưa kiểm tra ma trận tương thích. Các module Resilience4j thường cần cùng một dòng phiên bản để tránh lỗi API hoặc hành vi không nhất quán.

## 3. Kiểm tra TimeLimiter mặc định

TimeLimiter giới hạn thời gian một tác vụ được phép chạy trước khi caller nhận timeout. Trong cấu hình mặc định của Resilience4j, TimeLimiterConfig thường có timeoutDuration một giây và cancelRunningFuture bật. Spring Cloud CircuitBreaker Resilience4j có thể dùng cấu hình TimeLimiter mặc định này khi provider tạo Circuit Breaker.

Tuy nhiên, cần xác minh TimeLimiter có được áp dụng trên đường thực thi cụ thể của ứng dụng hay không. Cách bao một supplier đồng bộ, Future/CompletionStage và reactive publisher có thể khác nhau theo API và phiên bản provider. Không suy ra rằng mọi HTTP request đều được hủy hoàn toàn chỉ vì TimeLimiter đã phát timeout.

Các khái niệm cần tách biệt:

| Cơ chế | Giới hạn điều gì? |
| --- | --- |
| TimeLimiter | Thời gian chờ hoàn tất của tác vụ được bọc |
| HTTP connect timeout | Thời gian thiết lập kết nối |
| HTTP response/read timeout | Thời gian chờ phản hồi từ server |
| Caller deadline | Tổng thời gian nghiệp vụ cho phép từ đầu đến cuối |
| Circuit Breaker slow-call threshold | Ngưỡng phân loại lời gọi là chậm để thống kê |
| Bulkhead | Số lời gọi đồng thời hoặc năng lực thực thi dành cho dependency |

TimeLimiter không thay thế timeout của HTTP client. Nếu client đang chờ socket hoặc thư viện I/O không phản ứng với interrupt/cancellation, tác vụ phía dưới có thể tiếp tục tiêu thụ tài nguyên sau khi caller đã nhận timeout. Hãy cấu hình timeout tại HTTP client và kiểm tra khả năng hủy thực tế của client.

### 3.1. Khai báo TimeLimiter tường minh

Không nên để ứng dụng production phụ thuộc vào timeout mặc định nếu latency budget của dependency đã được xác định. Có thể khai báo cấu hình dùng chung và cấu hình riêng cho instance:

~~~yaml
resilience4j:
  timelimiter:
    configs:
      default:
        timeoutDuration: 2s
        cancelRunningFuture: true

    instances:
      inventory:
        baseConfig: default
        timeoutDuration: 800ms

      payment:
        baseConfig: default
        timeoutDuration: 1500ms
        cancelRunningFuture: true
~~~

Trong ví dụ, inventory có timeout 800 ms, payment có timeout 1.500 ms và các instance còn lại có thể kế thừa cấu hình default. Các con số chỉ là ví dụ; phải chọn theo SLO, p95/p99 latency và thời gian còn lại của request tổng thể.

Tên instance TimeLimiter cần được liên kết với ID Circuit Breaker theo cách provider đang phân giải cấu hình. Khi code tạo Circuit Breaker ID inventory, kiểm tra cấu hình TimeLimiter có đúng instance inventory hoặc group mà factory được yêu cầu sử dụng.

### 3.2. Hiểu đúng cancelRunningFuture

cancelRunningFuture xác định TimeLimiter có yêu cầu hủy Future khi timeout hay không. Lệnh hủy Future thường dựa trên cơ chế Future.cancel và có thể gửi interrupt đến thread đang chạy.

Điều đó không bảo đảm mọi công việc bên dưới dừng ngay lập tức:

- HTTP client có thể không hủy socket hoặc request đang chạy khi thread bị interrupt.
- Server đích có thể đã nhận và tiếp tục xử lý request.
- Một tác vụ đang ở trong thư viện native hoặc I/O không hỗ trợ interruption có thể vẫn chiếm tài nguyên.
- Nếu request đã ghi dữ liệu, timeout phía caller không chứng minh thao tác phía server chưa được commit.

Vì vậy, timeout cần phối hợp với timeout của HTTP client, cancellation của reactive publisher nếu có, và idempotency cho các thao tác ghi có thể được retry.

## 4. Kiểm tra Bulkhead mặc định của Resilience4j provider

Bulkhead giới hạn tài nguyên mà một dependency có thể chiếm dụng. Trong Spring Cloud CircuitBreaker Resilience4j, cấu hình mặc định thường dùng FixedThreadPoolBulkhead khi bulkhead integration được bật. FixedThreadPoolBulkhead thực thi supplier trên thread pool riêng và có queue hữu hạn.

Có thể chọn SemaphoreBulkhead làm mặc định bằng property:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Khi bật tùy chọn này, provider sử dụng semaphore bulkhead mặc định thay cho fixed thread pool bulkhead. Cần kiểm tra đúng phiên bản Spring Cloud CircuitBreaker đang chạy và xác nhận property được bind, đặc biệt khi migration qua nhiều release train.

Hai chiến lược có hành vi khác nhau:

| Tiêu chí | FixedThreadPoolBulkhead | SemaphoreBulkhead |
| --- | --- | --- |
| Thread thực thi | Thread của pool riêng | Thread gọi hiện tại |
| Queue công việc | Có queue hữu hạn | Không có queue task riêng |
| Giới hạn | Số thread, queue capacity | Số permit/concurrent calls |
| Kiểu xử lý | Thường trả kết quả bất đồng bộ | Giữ cách thực thi đồng bộ của caller |
| ThreadLocal | Cần context propagation sang pool | Thường giữ context trên thread hiện tại |
| Từ chối khi đầy | Pool và queue không nhận thêm task | Không lấy được permit trong giới hạn chờ |
| Chi phí | Quản lý thread và queue | Nhẹ hơn, ít thành phần hơn |

Việc thay đổi mặc định từ thread pool sang semaphore hoặc ngược lại có thể ảnh hưởng đến latency, thread usage, context propagation và cách fallback được thực thi. Không xem hai loại bulkhead là tương đương chỉ vì cùng giới hạn concurrency.

## 5. Cấu hình đúng loại Bulkhead

Nếu dùng SemaphoreBulkhead, cấu hình theo resilience4j.bulkhead:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true

resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
~~~

maxConcurrentCalls giới hạn số lời gọi đồng thời. maxWaitDuration bằng 0 nghĩa là không chờ permit khi đã hết slot; request vượt giới hạn bị từ chối nhanh.

Nếu dùng FixedThreadPoolBulkhead mặc định, cấu hình theo resilience4j.thread-pool-bulkhead:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

Trong ví dụ, tối đa tám thread thực thi và queue chứa tối đa 16 task đang chờ. Hãy chọn kích thước pool và queue theo latency, CPU, giới hạn connection và khả năng chịu tải của dependency.

Không nên khai báo cấu hình semaphore rồi giả định nó sẽ điều khiển FixedThreadPoolBulkhead. Khi provider dùng thread pool, các thuộc tính của resilience4j.bulkhead không thay thế cấu hình thread-pool-bulkhead. Ngược lại, khi bật semaphore default, cần kiểm tra cấu hình instance của semaphore được bind đúng.

### 5.1. Xác nhận bulkhead thực sự đang hoạt động

Không chỉ đọc YAML để kết luận. Hãy kiểm tra runtime bằng một dependency giả lập có thời gian xử lý cố định:

1. Đặt giới hạn concurrency thấp, ví dụ 2.
2. Cho mỗi lời gọi giữ tài nguyên trong một khoảng thời gian đủ dài.
3. Gửi đồng thời nhiều request vượt giới hạn.
4. Quan sát thread thực thi, số task trong queue và số request bị từ chối.
5. Bật semaphore default rồi lặp lại cùng tải.
6. So sánh thread name, latency, rejection và context log.

Với semaphore, supplier thường chạy trên thread gọi. Với fixed thread pool, supplier chạy trên thread thuộc pool. Đây là dấu hiệu thực nghiệm hữu ích để xác nhận loại bulkhead, nhưng nên kết hợp với metrics hoặc cấu hình runtime thay vì chỉ dựa vào tên thread.

## 6. Quy tắc đặt tên ID và group name

Spring Cloud CircuitBreaker dùng ID để xác định Circuit Breaker instance. Ví dụ:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerFactory.create("inventory");
~~~

ID inventory là tên định danh của instance. Khi dùng property-based configuration, tên này cần khớp với khóa instance tương ứng:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 800ms
~~~

Nếu provider sử dụng Bulkhead instance theo cùng ID, cấu hình tương ứng cũng cần dùng inventory dưới nhóm bulkhead đang hoạt động:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
~~~

Quy tắc thực hành là giữ ID ổn định theo dependency hoặc thao tác được bảo vệ. Tránh tạo ID động chứa user ID, order ID, request ID hoặc tenant ID. ID động có thể tạo ra số lượng instance, state machine và meter không kiểm soát.

### 6.1. Phân biệt ID với group name

Một số phiên bản API cho phép tạo Circuit Breaker với hai tham số:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerFactory.create("inventory", "critical-services");
~~~

Trong cách gọi này:

- inventory là ID của Circuit Breaker instance.
- critical-services là group name dùng để chọn cấu hình nhóm mà provider hỗ trợ.

Không thay ID bằng group name. ID xác định instance cụ thể; group name bổ sung ngữ cảnh cấu hình. Cách provider phân giải instance config và group config có thể khác theo phiên bản, vì vậy cần kiểm tra tài liệu của release train đang dùng và xác nhận cấu hình hiệu lực.

Một cách tổ chức phổ biến là dùng ID cho dependency cụ thể, group cho nhóm chính sách có chung đặc tính:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      critical-services:
        slidingWindowSize: 40
        minimumNumberOfCalls: 20
        failureRateThreshold: 40

    instances:
      inventory:
        baseConfig: default

  timelimiter:
    configs:
      default:
        timeoutDuration: 2s
      critical-services:
        timeoutDuration: 1s

    instances:
      inventory:
        baseConfig: default
~~~

Khi dùng group name, không giả định rằng mọi thuộc tính của Circuit Breaker, TimeLimiter và Bulkhead đều được phân giải từ group theo cùng một quy tắc. Hãy kiểm tra cấu hình provider và version cụ thể, sau đó ghi lại giá trị thực tế cho từng instance.

## 7. Quy tắc tên khi dùng annotation Resilience4j trực tiếp

Cần phân biệt API Spring Cloud CircuitBreaker với annotation AOP của Resilience4j.

Ví dụ annotation:

~~~java
@CircuitBreaker(name = "inventory")
public InventoryResponse getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Ở đây name là tên instance trong Resilience4j registry. Nó thường liên kết với:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        failureRateThreshold: 40
~~~

Annotation trực tiếp không nhận group name theo cách gọi create(id, groupName) của Spring Cloud factory. Không nên áp dụng quy tắc group của factory cho thuộc tính name trong annotation.

Nếu cùng một ứng dụng sử dụng cả hai kiểu tích hợp, hãy ghi rõ đường gọi nào dùng factory và đường gọi nào dùng annotation. Không bọc cùng một lời gọi qua cả hai lớp chỉ để “chắc chắn” cấu hình được áp dụng; việc đó có thể tạo hai Circuit Breaker với state và metrics riêng.

## 8. Cấu hình properties và Java Customizer

Spring Cloud CircuitBreaker Resilience4j cho phép cấu hình bằng application.yml và bằng Java Customizer. Khi cùng một thuộc tính được khai báo ở cả hai nơi, cấu hình properties thường có độ ưu tiên cao hơn Java configuration trong cơ chế property-based configuration của Spring Cloud CircuitBreaker.

Ví dụ customizer mặc định:

~~~java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer() {
    return factory -> factory.configureDefault(id ->
        new Resilience4JConfigBuilder(id)
            .timeLimiterConfig(
                TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofSeconds(2))
                    .cancelRunningFuture(true)
                    .build()
            )
            .circuitBreakerConfig(
                CircuitBreakerConfig.custom()
                    .slidingWindowSize(20)
                    .failureRateThreshold(50)
                    .build()
            )
            .build()
    );
}
~~~

Có thể cấu hình riêng theo ID:

~~~java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryCustomizer() {
    return factory -> factory.configure(
        builder -> builder
            .timeLimiterConfig(
                TimeLimiterConfig.custom()
                    .timeoutDuration(Duration.ofMillis(800))
                    .build()
            ),
        "inventory"
    );
}
~~~

Nếu application.yml cũng khai báo timeout cho inventory, hãy xác nhận giá trị nào thực sự có hiệu lực theo phiên bản. Không nên để cùng một tham số xuất hiện ở nhiều nguồn mà không có tài liệu về nguồn có quyền ưu tiên.

Trong migration, nên chọn một nguồn cấu hình chính cho mỗi nhóm tham số. Có thể dùng properties cho cấu hình theo môi trường và customizer cho logic tạo cấu hình dùng chung, nhưng phải kiểm tra thứ tự áp dụng và không dựa vào thứ tự khởi tạo ngẫu nhiên.

## 9. Phối hợp TimeLimiter với Bulkhead

TimeLimiter và Bulkhead bảo vệ hai giới hạn khác nhau. Khi dùng FixedThreadPoolBulkhead, task có thể nằm trong queue trước khi được thực thi. Thời gian chờ queue, thời gian chạy và cách TimeLimiter bọc task có thể ảnh hưởng đến thời điểm caller nhận timeout.

Cần trả lời các câu hỏi:

- Timeout bắt đầu tính từ lúc submit task hay khi task bắt đầu thực thi?
- Task đang nằm trong queue có thể bị hủy khi timeout không?
- Khi Future bị cancel, thread đang chạy có nhận interrupt không?
- HTTP client có thực sự hủy request hoặc giải phóng connection không?
- Task bị timeout có tiếp tục chiếm thread pool không?
- Queue có thể đầy dù caller đã nhận timeout từ trước hay không?

Các câu trả lời phụ thuộc đường tích hợp và phiên bản. Hãy đo trong staging bằng task có thời gian chờ và thời gian thực thi có thể điều khiển.

Với SemaphoreBulkhead, supplier thường chạy trên thread gọi nên không có queue riêng của bulkhead. Tuy nhiên, request vẫn có thể giữ thread caller cho đến khi HTTP client trả kết quả hoặc timeout. Semaphore không thay thế timeout.

Cấu hình ví dụ:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 800ms
        cancelRunningFuture: true

  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
~~~

Nếu dùng thread pool bulkhead, chuyển cấu hình instance sang resilience4j.thread-pool-bulkhead và xác nhận provider đang dùng đúng chiến lược. Không để timeout quá ngắn khiến nhiều task liên tục bị cancel trong khi công việc phía dưới vẫn chạy, vì điều đó có thể làm cạn pool mà caller không nhìn thấy.

## 10. Kiểm tra cấu hình hiệu lực sau migration

Cấu hình trong repository chỉ là đầu vào. Cần kiểm tra cấu hình thực tế sau khi Spring bind properties và provider tạo instance.

Một bảng kiểm tra có thể gồm:

| Thuộc tính | Cấu hình mong muốn | Bằng chứng runtime |
| --- | --- | --- |
| Circuit Breaker ID | inventory | State/metrics có tag instance inventory |
| TimeLimiter | 800 ms | Task quá thời hạn trả timeout theo đường thực thi đã chọn |
| cancelRunningFuture | true | Kiểm tra Future cancellation và tác động đến worker |
| Bulkhead type | Semaphore hoặc FixedThreadPool | Quan sát thread, queue và rejection |
| Bulkhead limit | 10 permit hoặc pool/queue cụ thể | Tải đồng thời không vượt giới hạn |
| Group name | critical-services | Cấu hình group được áp dụng theo provider |
| Failure threshold | 50% hoặc giá trị riêng | Gây lỗi có kiểm soát và quan sát state |
| Slow-call threshold | Theo latency budget | Lời gọi chậm được ghi nhận đúng |
| Fallback | Kết quả suy giảm đã định nghĩa | Xác nhận chỉ chạy ở ranh giới mong muốn |

Không nên expose endpoint cấu hình nhạy cảm ra công khai chỉ để kiểm tra. Dùng log khởi tạo, Actuator được bảo vệ, metrics, integration test hoặc kiểm tra trực tiếp bean trong môi trường staging.

## 11. Quy trình migration theo từng bước

Có thể áp dụng quy trình sau khi nâng cấp Spring Cloud CircuitBreaker hoặc Resilience4j:

1. **Chụp baseline:** ghi lại dependency tree, timeout, bulkhead type, thread usage, rejection, latency và fallback count của phiên bản hiện tại.
2. **Kiểm tra release train:** xác nhận Spring Boot, Spring Cloud và Resilience4j tương thích.
3. **Liệt kê instance ID:** đối chiếu mọi lời gọi create(id), annotation name và khóa YAML.
4. **Liệt kê group name:** kiểm tra các lời gọi create(id, groupName) và cấu hình group tương ứng.
5. **Khai báo timeout tường minh:** không để timeout quan trọng phụ thuộc giá trị mặc định.
6. **Chọn Bulkhead tường minh:** xác nhận dùng semaphore hay fixed thread pool và cấu hình đúng prefix.
7. **Kiểm tra nguồn cấu hình:** xác định properties hay Java Customizer có quyền ưu tiên.
8. **Kiểm thử timeout:** dùng task nhanh, task chậm, task treo và task bị cancel.
9. **Kiểm thử bulkhead:** tạo tải vượt giới hạn và quan sát queue, permit, thread cùng rejection.
10. **Kiểm thử naming:** xác nhận đúng instance và group được chọn.
11. **Kiểm thử fallback và context:** kiểm tra MDC, SecurityContext và trace context nếu có chuyển thread.
12. **So sánh với baseline:** đối chiếu latency, throughput, timeout count và tài nguyên.
13. **Triển khai từng giai đoạn:** canary hoặc rolling deployment, theo dõi metrics và chuẩn bị rollback.

Nên thay đổi từng nhóm mặc định một lần. Nếu đồng thời đổi timeout, bulkhead type và ID naming, khi hành vi thay đổi sẽ khó xác định yếu tố gây ra khác biệt.

## 12. Bộ kịch bản kiểm thử tối thiểu

| Kịch bản | Cách tạo | Kết quả cần xác nhận |
| --- | --- | --- |
| Lời gọi nhanh | Dependency trả trong 100 ms | Không bị TimeLimiter timeout |
| Lời gọi chậm | Dependency trả sau timeout đã cấu hình | Caller nhận timeout đúng giới hạn |
| Future bị timeout | Task chạy trên executor có thể quan sát | Kiểm tra cancellation và task còn chạy hay không |
| Bulkhead đầy | Gửi nhiều request hơn giới hạn concurrency | Request vượt giới hạn bị từ chối hoặc chờ đúng chính sách |
| Thread pool queue đầy | Giữ worker bận và lấp queue | Rejection xảy ra đúng lúc, không tăng queue vô hạn |
| Semaphore default | Bật enableSemaphoreDefaultBulkhead | Supplier chạy trên thread gọi và permit được giới hạn |
| Fixed thread pool default | Tắt lựa chọn semaphore hoặc dùng cấu hình mặc định theo release | Supplier chạy trên pool riêng và queue có giới hạn |
| Sai ID | Code dùng inventory nhưng YAML khai báo inventory-api | Phát hiện cấu hình instance không được áp dụng như mong muốn |
| Group config | Gọi create với ID và group name | Xác nhận đúng cấu hình instance/group theo phiên bản |
| Properties và Customizer | Cùng khai báo một giá trị ở hai nơi | Xác định nguồn có độ ưu tiên cao hơn |
| Nhiều replica | Chạy nhiều instance ứng dụng | Đánh giá state, pool và metrics cục bộ từng replica |

Các phép thử timeout nên dùng clock và test fixture có thể điều khiển khi phù hợp. Tránh dùng sleep dài hoặc timing quá sát khiến kết quả chập chờn. Với tải đồng thời, đo số lời gọi đang chạy bằng bộ đếm thread-safe ở test dependency.

## 13. Các lỗi thường gặp khi migration

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request timeout sau khoảng một giây | TimeLimiter đang dùng giá trị mặc định | Khai báo timeoutDuration tường minh theo dependency |
| Caller timeout nhưng task vẫn chiếm thread | Future cancellation không dừng được I/O bên dưới | Cấu hình timeout HTTP client và kiểm tra cancellation |
| Mất MDC hoặc SecurityContext sau nâng cấp | Bulkhead chuyển sang thread pool hoặc execution path đổi thread | Kiểm tra loại bulkhead và cấu hình context propagation |
| Thread pool cạn dù caller đã timeout | Task đã timeout nhưng vẫn tiếp tục chạy | Kiểm tra cancellation, queue và timeout tầng HTTP |
| Semaphore config không có tác dụng | Provider vẫn dùng FixedThreadPoolBulkhead | Kiểm tra enableSemaphoreDefaultBulkhead và prefix cấu hình |
| Bulkhead rejection tăng mạnh | Giới hạn concurrency hoặc queue thấp hơn lưu lượng thực | Đo concurrency và điều chỉnh theo ngân sách tài nguyên |
| YAML không được áp dụng | ID code khác tên instance hoặc sai prefix | Đồng bộ ID và cấu hình theo provider |
| Group config không có hiệu lực | Không truyền group name hoặc hiểu nhầm group là ID | Kiểm tra create(id, groupName) và quy tắc phân giải của phiên bản |
| Customizer không thắng YAML | Properties có độ ưu tiên cao hơn | Chọn một nguồn cấu hình chính và kiểm tra giá trị hiệu lực |
| Metrics có nhiều instance bất thường | ID được tạo động theo request | Dùng ID ổn định ở cấp dependency hoặc thao tác |

## 14. Checklist trước khi phát hành

Trước khi triển khai phiên bản mới, hãy xác nhận:

- Spring Boot, Spring Cloud release train và Resilience4j tương thích.
- Dependency tree cho thấy đúng phiên bản runtime.
- TimeLimiter timeout được khai báo tường minh cho dependency quan trọng.
- HTTP client có connect/response timeout riêng.
- cancelRunningFuture được hiểu đúng và đã kiểm thử cancellation.
- Bulkhead type được xác định rõ, không dựa vào giả định về mặc định.
- Prefix cấu hình khớp loại bulkhead đang sử dụng.
- ID trong factory khớp với tên instance cấu hình.
- Group name được truyền đúng và có cấu hình hợp lệ.
- Annotation name được phân biệt với factory ID/group name.
- Properties và Java Customizer không ghi đè nhau ngoài dự kiến.
- Thread pool, queue, semaphore và rejection được đo dưới tải.
- Fallback, context propagation và metrics được kiểm chứng.
- Có baseline, canary, rollback và người chịu trách nhiệm theo dõi.

Khi migration Spring Cloud CircuitBreaker, TimeLimiter, Bulkhead và quy tắc đặt tên cần được kiểm tra như một phần của hành vi runtime. Khai báo timeout và loại bulkhead tường minh giúp ứng dụng ít phụ thuộc vào mặc định của phiên bản. ID ổn định, group name được hiểu đúng và cấu hình hiệu lực được xác nhận giúp tránh trường hợp ứng dụng chạy với policy khác điều đội phát triển mong đợi. Kiểm thử timeout, cancellation, saturation và naming trước khi phát hành sẽ giảm rủi ro thay đổi hành vi bảo vệ dependency sau nâng cấp.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html)
- [Resilience4j TimeLimiter](https://resilience4j.readme.io/docs/timeout)
- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)

