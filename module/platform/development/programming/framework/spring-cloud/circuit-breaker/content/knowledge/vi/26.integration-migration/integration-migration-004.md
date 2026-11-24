# Chuyển từ API nhà cung cấp trực tiếp sang abstraction khi phù hợp

Khi ứng dụng dùng Resilience4j trực tiếp, service thường phụ thuộc vào các kiểu như CircuitBreakerRegistry, CircuitBreaker và các API thực thi của Resilience4j. Cách làm này cho phép kiểm soát sâu cấu hình, state, event và metrics. Tuy nhiên, nó cũng khiến mã nghiệp vụ phụ thuộc trực tiếp vào một thư viện cụ thể. Spring Cloud CircuitBreaker cung cấp một abstraction chung để ứng dụng gọi cơ chế bảo vệ qua factory và interface, trong khi implementation bên dưới có thể là Resilience4j hoặc một provider được Spring Cloud hỗ trợ.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, chuyển từ API provider trực tiếp sang abstraction phù hợp khi muốn thống nhất cách gọi giữa các service, tận dụng tích hợp của Spring Cloud với OpenFeign hoặc giảm phụ thuộc của lớp nghiệp vụ vào Resilience4j. Việc chuyển đổi cần có chủ đích: abstraction cung cấp bề mặt API chung, nhưng không tự động chuyển mọi cấu hình, annotation, event và tính năng đặc thù của provider thành tính năng trung lập.

## 1. Phân biệt API trực tiếp và Spring Cloud abstraction

Hai cách tiếp cận có ranh giới phụ thuộc khác nhau:

| Tiêu chí | API Resilience4j trực tiếp | Spring Cloud CircuitBreaker abstraction |
| --- | --- | --- |
| Kiểu được inject | CircuitBreakerRegistry, CircuitBreaker | CircuitBreakerFactory và interface CircuitBreaker của Spring Cloud |
| Tạo instance | Tra cứu trong Resilience4j registry | Gọi factory.create(name) |
| Thực thi lời gọi | executeSupplier, executeCallable hoặc decorator | run với supplier và fallback |
| Cấu hình | Resilience4j config, registry và API riêng | Cấu hình theo factory abstraction; có thể dùng properties của implementation |
| Phụ thuộc provider | Mã gọi biết trực tiếp Resilience4j | Mã gọi phụ thuộc interface của Spring Cloud |
| Truy cập tính năng nâng cao | Trực tiếp state, metrics, event và registry API | Chỉ có phần chung; tính năng riêng cần integration hoặc API provider |
| Tích hợp Spring Cloud | Tự kết nối hoặc dùng các integration riêng | Là điểm tích hợp chung cho các client và service trong hệ sinh thái Spring Cloud |

Ví dụ, code dùng Resilience4j trực tiếp có thể lấy instance từ registry rồi gọi executeSupplier. Khi chuyển sang abstraction, code lấy Circuit Breaker từ factory và gọi run. Cả hai đều bảo vệ một thao tác, nhưng kiểu đối tượng và bề mặt API khác nhau.

Không nên coi abstraction là một lớp bao bọc không có chi phí thiết kế. Nó giúp giảm phụ thuộc provider trong lớp gọi, nhưng những phần cấu hình hoặc quan sát vẫn có thể mang đặc điểm của implementation đang chạy.

## 2. Khi nào nên chuyển sang abstraction?

Việc chuyển đổi thường phù hợp khi:

- Các service đang gọi Resilience4j theo nhiều cách khác nhau và cần chuẩn hóa cách tạo, gọi và fallback.
- Muốn dùng tích hợp Circuit Breaker sẵn có của Spring Cloud OpenFeign hoặc các thành phần Spring Cloud khác.
- Muốn lớp nghiệp vụ chỉ biết interface Circuit Breaker chung, để việc chọn implementation nằm ở cấu hình ứng dụng.
- Muốn giảm số import và kiểu provider-specific trong gateway hoặc adapter gọi dịch vụ.
- Ứng dụng có khả năng cần thay đổi implementation trong tương lai và muốn giới hạn phạm vi thay đổi ở cấu hình cùng integration.

Giữ API trực tiếp có thể hợp lý khi:

- Mã cần thao tác nâng cao với registry, state machine, event publisher hoặc metrics riêng của Resilience4j.
- Đang dùng các decorator hoặc module Resilience4j chuyên biệt mà abstraction không cung cấp tương đương.
- Cần kiểm soát chi tiết cách kết hợp nhiều policy và đã có kiến trúc dựa trên Resilience4j.
- Việc thêm abstraction không làm giảm coupling thực tế hoặc tạo thêm lớp chuyển đổi không cần thiết.

Quyết định nên dựa trên nhu cầu của lớp gọi. Không cần chuyển mọi chỗ dùng Resilience4j chỉ để thống nhất import nếu các chỗ đó cần API trực tiếp và không có yêu cầu thay đổi provider.

## 3. Cấu trúc trước khi chuyển đổi

Ví dụ một service đang phụ thuộc trực tiếp vào Resilience4j:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerRegistry registry;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerRegistry registry,
            InventoryClient inventoryClient) {
        this.registry = registry;
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");
        return breaker.executeSupplier(
                () -> inventoryClient.get(sku)
        );
    }
}
~~~

Service biết trực tiếp registry và Circuit Breaker của Resilience4j. Điều này không sai nếu Resilience4j là lựa chọn kiến trúc cố định. Tuy nhiên, nếu nhiều service đều dùng kiểu này, lớp gọi sẽ gắn với provider và cần thay đổi khi chuyển sang abstraction.

Một điểm cần lưu ý: không nên tạo registry mới theo từng request. Registry cần được Spring quản lý hoặc được tạo một lần trong vòng đời ứng dụng. Ví dụ trên inject registry dùng chung, sau đó tra cứu instance theo tên.

## 4. Thêm Spring Cloud CircuitBreaker Resilience4j starter

Nếu ứng dụng chọn Resilience4j làm implementation cho Spring Cloud CircuitBreaker, thêm starter tương ứng và quản lý phiên bản bằng Spring Cloud release train BOM tương thích với Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Không tự chọn một phiên bản starter ngẫu nhiên. Hãy dùng Spring Cloud BOM phù hợp với phiên bản Spring Boot của dự án và kiểm tra dependency tree để tránh trộn các release train hoặc phiên bản Resilience4j không tương thích.

Nếu ứng dụng dùng OpenFeign, dependency OpenFeign vẫn được quản lý riêng. Starter CircuitBreaker cung cấp implementation cho abstraction; cấu hình bật tích hợp OpenFeign là một bước riêng và cần được kiểm tra theo phiên bản Spring Cloud đang dùng.

## 5. Chuyển từ CircuitBreakerRegistry sang CircuitBreakerFactory

Sau khi có starter, lớp gọi có thể phụ thuộc vào factory abstraction của Spring Cloud:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.get(sku),
                failure -> Inventory.unavailable(sku)
        );
    }
}
~~~

Khác biệt chính:

1. Lớp gọi inject CircuitBreakerFactory của Spring Cloud.
2. Factory tạo hoặc lấy Circuit Breaker theo tên logic.
3. Interface Circuit Breaker cung cấp phương thức run để bọc supplier.
4. Hàm fallback nhận Throwable và trả về kết quả cùng kiểu với lời gọi chính.

Trong ví dụ, InventoryClient là adapter gọi dịch vụ Kho. Fallback trả trạng thái unavailable để không biến lỗi phụ thuộc thành số lượng tồn kho bằng 0. Trong ứng dụng thực tế, có thể dùng cache nếu dữ liệu còn trong thời hạn nghiệp vụ cho phép.

Không import nhầm CircuitBreaker của Resilience4j và CircuitBreaker của Spring Cloud trong cùng lớp. Khi đã chuyển sang abstraction, lớp gọi nên dùng interface thuộc package org.springframework.cloud.client.circuitbreaker.

## 6. Chuyển đổi fallback và ngữ nghĩa lỗi

API trực tiếp có thể dùng executeSupplier rồi xử lý exception ở tầng gọi:

~~~java
try {
    return breaker.executeSupplier(() -> inventoryClient.get(sku));
} catch (Exception failure) {
    return fallbackInventory(sku, failure);
}
~~~

Với Spring Cloud abstraction, có thể truyền fallback trực tiếp vào run:

~~~java
return circuitBreaker.run(
        () -> inventoryClient.get(sku),
        failure -> fallbackInventory(sku, failure)
);
~~~

Khi chuyển đổi, cần giữ nguyên chính sách phân loại lỗi:

- Lỗi HTTP 5xx, lỗi kết nối và timeout thường phản ánh vấn đề của phụ thuộc và có thể được ghi nhận là lỗi.
- Lỗi nghiệp vụ như tài nguyên không tồn tại không nhất thiết là lỗi sức khỏe của phụ thuộc.
- Lỗi từ chối do Rate Limiter hoặc Bulkhead là tình trạng giới hạn cục bộ, cần được phân biệt với lỗi của dịch vụ bên ngoài.
- Fallback phải trả đúng kiểu dữ liệu, giữ nguyên ý nghĩa nghiệp vụ và không gọi lại chính phụ thuộc đang lỗi.

Abstraction nhận một Throwable trong fallback. Nếu ứng dụng cần phân biệt exception cụ thể, có thể kiểm tra kiểu hoặc chuyển đổi exception sang một mô hình lỗi nội bộ trước khi xử lý. Đừng làm mất nguyên nhân gốc khi chuyển từ API trực tiếp sang abstraction.

## 7. Chuyển cấu hình Resilience4j sang cấu hình theo instance

Khi implementation vẫn là Resilience4j, có thể giữ cấu hình instance trong application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Tên truyền vào factory.create("inventory") cần khớp instance cấu hình. Khi chuyển đổi, không đổi tên tùy tiện vì dashboard, metrics và cấu hình hiện có có thể đang dùng tên đó.

Một số khác biệt cần lưu ý:

- Config của Resilience4j vẫn mang tính provider-specific dù code gọi đã dùng abstraction.
- TimeLimiter, Bulkhead và các policy khác có thể được cấu hình hoặc kết hợp theo integration của Spring Cloud và implementation.
- Cấu hình qua properties và Java Customizer có quy tắc ưu tiên phụ thuộc phiên bản Spring Cloud CircuitBreaker; hãy kiểm tra tài liệu release train thực tế.
- Không giả định mọi thuộc tính Resilience4j đều được expose qua abstraction chung.

Nếu sau này thay implementation, cần ánh xạ lại chính sách theo khả năng của provider mới. Abstraction không tự chuyển ngữ nghĩa COUNT_BASED, slow-call threshold hoặc TimeLimiter sang cấu hình tương đương ở mọi implementation.

## 8. Cấu hình mặc định bằng Customizer

Spring Cloud CircuitBreaker với Resilience4j cho phép tùy chỉnh cấu hình qua factory. Ví dụ cấu hình mặc định cho các instance:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerDefaults {
    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer() {
        return factory -> factory.configureDefault(id ->
                new Resilience4JConfigBuilder(id)
                        .circuitBreakerConfig(
                                CircuitBreakerConfig.custom()
                                        .slidingWindowSize(20)
                                        .minimumNumberOfCalls(10)
                                        .failureRateThreshold(50)
                                        .build())
                        .timeLimiterConfig(
                                TimeLimiterConfig.custom()
                                        .timeoutDuration(Duration.ofSeconds(2))
                                        .build())
                        .build());
    }
}
~~~

Customizer là cách cấu hình gắn với implementation Resilience4j, không phải API trung lập. Nếu mục tiêu là để lớp nghiệp vụ không biết provider, hãy đặt Customizer trong package cấu hình hoặc adapter infrastructure thay vì inject Resilience4JCircuitBreakerFactory vào service nghiệp vụ.

Khi cùng một thuộc tính được khai báo ở properties và Java Customizer, thứ tự ưu tiên có thể được Spring Cloud CircuitBreaker quy định theo phiên bản. Không trộn hai cách mà không xác định rõ nguồn cấu hình cuối cùng. Với cấu hình cần thay đổi theo môi trường, properties thường dễ quản lý hơn; với cấu hình lập trình có điều kiện, Customizer có thể phù hợp hơn.

## 9. Chuyển lời gọi reactive

Nếu service dùng WebClient và Reactor, dùng ReactiveCircuitBreakerFactory thay cho API Resilience4j Reactor trực tiếp:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInventoryGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final WebClient inventoryWebClient;

    public ReactiveInventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            WebClient inventoryWebClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<Inventory> getInventory(String sku) {
        ReactiveCircuitBreaker breaker =
                circuitBreakerFactory.create("inventory");

        Mono<Inventory> primary = inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        return breaker.run(
                primary,
                failure -> Mono.just(Inventory.unavailable(sku))
        );
    }
}
~~~

Publisher của WebClient là lazy và được thực thi khi có subscription. ReactiveCircuitBreaker bọc Mono chính và fallback cũng phải trả Mono cùng kiểu. Không gọi block() hoặc subscribe() thủ công trong service WebFlux.

Nếu ứng dụng dùng Flux streaming, cần kiểm tra overload mà Spring Cloud abstraction của phiên bản đang dùng hỗ trợ. Một số API abstraction tập trung vào Mono; với luồng Flux dài hoặc không giới hạn, có thể cần dùng integration Reactor của Resilience4j trực tiếp. Đây là một trường hợp hợp lý để giữ API provider-specific trong adapter chuyên biệt.

## 10. Chuyển từ annotation provider-specific

Một ứng dụng có thể đang dùng annotation của Resilience4j:

~~~java
@io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker(
        name = "inventory",
        fallbackMethod = "fallbackInventory")
public Inventory getInventory(String sku) {
    return inventoryClient.get(sku);
}
~~~

Annotation này thuộc Resilience4j và được xử lý qua AOP. Nó không tự động trở thành annotation trung lập của Spring Cloud CircuitBreaker chỉ vì đã thêm starter abstraction.

Khi chuyển sang abstraction, thường cần đưa việc bảo vệ lời gọi vào một gateway hoặc adapter dùng CircuitBreakerFactory:

~~~java
public Inventory getInventory(String sku) {
    return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.get(sku),
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

Nếu vẫn giữ annotation Resilience4j ở một số lớp, hãy ghi rõ ranh giới sử dụng. Tránh bọc cùng một lời gọi bằng annotation và factory abstraction cùng lúc nếu không có chủ đích; hai Circuit Breaker lồng nhau có thể tạo hai state machine, hai sliding window, hai bộ metrics và hành vi fallback khó dự đoán.

Khi chuyển khỏi annotation, kiểm tra lại các trường hợp self-invocation, thứ tự AOP, fallback signature và exception được retry hoặc ignore. Một bài kiểm thử tích hợp cần xác nhận fallback vẫn nhận đúng nguyên nhân và state được cập nhật ở đúng instance.

## 11. Tích hợp OpenFeign qua abstraction

Spring Cloud OpenFeign có thể tích hợp Circuit Breaker thông qua Spring Cloud CircuitBreaker khi bật tính năng tương ứng:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Sau khi bật, các phương thức Feign có thể được bọc bởi Circuit Breaker được tạo từ abstraction. Tên instance phụ thuộc naming resolver và phiên bản Spring Cloud; cần đối chiếu ID runtime với khóa cấu hình Resilience4j.

Tích hợp này hữu ích khi ứng dụng muốn bảo vệ các lời gọi Feign theo một cơ chế thống nhất. Tuy nhiên, không nên đồng thời bọc một lời gọi Feign bằng Circuit Breaker thủ công ở service ngoài và để OpenFeign tự bọc cùng lời gọi, trừ khi thật sự muốn hai lớp bảo vệ độc lập. Bọc trùng có thể làm failure rate, fallback và timeout khó diễn giải.

## 12. Lộ trình migration an toàn

Không cần thay đổi toàn bộ hệ thống trong một lần. Có thể chuyển theo từng phụ thuộc:

1. Liệt kê các nơi đang inject CircuitBreakerRegistry hoặc dùng annotation Resilience4j.
2. Phân loại nơi chỉ cần gọi và fallback cơ bản với nơi cần API nâng cao như event, state hoặc Reactor operator.
3. Chọn một gateway đại diện để chuyển sang CircuitBreakerFactory.
4. Thêm starter Spring Cloud CircuitBreaker Resilience4j và xác nhận dependency version tương thích.
5. Giữ tên instance ổn định và đối chiếu khóa YAML với tên factory tạo.
6. Chuyển supplier, fallback và exception mapping; bảo đảm ngữ nghĩa kết quả không đổi.
7. Kiểm tra TimeLimiter, Bulkhead, Retry và thứ tự policy nếu lời gọi đang kết hợp nhiều cơ chế.
8. Kiểm thử thành công, HTTP 5xx, timeout, OPEN, HALF_OPEN và fallback.
9. So sánh metrics trước và sau migration để phát hiện thay đổi số instance, tag hoặc failure rate.
10. Chuyển các gateway tiếp theo sau khi mẫu đầu tiên hoạt động đúng.

Trong giai đoạn chuyển tiếp, tránh để cùng một request đi qua cả Circuit Breaker cũ và mới. Nếu cần so sánh hành vi, có thể chạy kiểm thử hoặc shadow measurement có kiểm soát, nhưng không tạo hai lớp bảo vệ cùng chặn request production mà không có kế hoạch rõ ràng.

## 13. Kiểm tra sau migration

Sau khi chuyển một lời gọi sang abstraction, xác minh:

| Hạng mục | Kết quả cần thấy |
| --- | --- |
| Dependency injection | Lớp gọi nhận CircuitBreakerFactory hoặc ReactiveCircuitBreakerFactory |
| Tên instance | Factory ID khớp cấu hình instance |
| Cấu hình | Window, threshold, wait duration và timeout tương đương chính sách cũ |
| Thành công | Supplier trả kết quả và Circuit Breaker ghi nhận thành công |
| Lỗi phụ thuộc | Exception truyền qua abstraction và được ghi nhận theo policy |
| Fallback | Được gọi đúng lúc, trả đúng kiểu và không gọi lại phụ thuộc đang lỗi |
| OPEN | Lời gọi bị từ chối trước khi request đến phụ thuộc |
| HALF_OPEN | Số lời gọi thử nghiệm tuân theo cấu hình |
| Metrics và events | Tên instance, state và số liệu được quan sát đúng |
| Policy bổ sung | Retry, TimeLimiter và Bulkhead không bị mất hoặc áp dụng hai lần |

Đừng chỉ xác nhận API cuối cùng trả HTTP 200. Fallback có thể làm request thành công về mặt giao thức trong khi phụ thuộc đang lỗi. Hãy kiểm tra state, metrics, số lần fallback và log nguyên nhân.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đổi import nhưng giữ cách tạo instance cũ | Lớp gọi vẫn phụ thuộc provider hoặc không dùng factory | Chuyển sang CircuitBreakerFactory và interface Spring Cloud |
| Nhầm CircuitBreaker của Resilience4j với Spring Cloud | Sai kiểu API hoặc gọi nhầm phương thức | Dùng đúng package theo ranh giới abstraction |
| Cho rằng abstraction tự chuyển mọi cấu hình | Threshold hoặc timeout không còn tương đương | Đối chiếu properties và config runtime |
| Đổi tên instance trong lúc migration | Cấu hình và dashboard không khớp | Giữ ID ổn định hoặc cập nhật đồng bộ |
| Bọc cùng lời gọi hai lần | Hai state machine, fallback và metrics chồng nhau | Chỉ giữ một lớp bảo vệ cho mỗi mục tiêu |
| Giữ annotation và thêm factory trên cùng method | AOP và abstraction cùng bọc một lời gọi | Xác định rõ ranh giới migration |
| Chuyển fallback nhưng làm mất exception gốc | Khó phân biệt lỗi nghiệp vụ và lỗi phụ thuộc | Giữ Throwable và phân loại rõ ràng |
| Dùng abstraction cho API nâng cao không được expose | Mất khả năng truy cập event hoặc operator cần thiết | Giữ provider API trong adapter có ranh giới rõ |
| Chuyển Flux streaming sang Mono bằng collectList không giới hạn | Tích lũy toàn bộ dữ liệu trong bộ nhớ | Chỉ thu thập khi có giới hạn; nếu không, dùng integration phù hợp cho Flux |
| Không kiểm tra thứ tự Retry/TimeLimiter/Bulkhead | Hành vi và metrics thay đổi sau migration | Kiểm thử thứ tự thực thi và loại exception |

## 15. Kết luận

Spring Cloud CircuitBreaker abstraction phù hợp khi lớp gọi chỉ cần một hợp đồng chung để tạo Circuit Breaker, thực thi supplier và xử lý fallback. Nó giúp giảm phụ thuộc provider và kết nối thuận tiện với các tích hợp Spring Cloud. Resilience4j trực tiếp vẫn hữu ích khi ứng dụng cần registry, event, state, operator hoặc policy chuyên biệt.

Migration tốt giữ nguyên ngữ nghĩa bảo vệ: tên instance, sliding window, ngưỡng lỗi, timeout, fallback và cách phân loại exception. Hãy chuyển từng gateway, kiểm tra runtime và metrics sau mỗi bước, đồng thời giữ các API provider-specific trong lớp infrastructure khi abstraction chưa đáp ứng nhu cầu. Cách làm này giúp ứng dụng tận dụng abstraction mà vẫn kiểm soát được hành vi bảo vệ dịch vụ.
