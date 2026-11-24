# Kiểm tra classpath, tự cấu hình và hiện thực CircuitBreakerFactory

## Mục tiêu chuẩn bị môi trường

Spring Cloud Circuit Breaker cung cấp một lớp trừu tượng để ứng dụng gọi dịch vụ phụ thuộc thông qua circuit breaker mà không phải gắn chặt mã nghiệp vụ với một thư viện cụ thể. Với Resilience4j, starter của Spring Cloud đưa implementation, cấu hình tự động và các thành phần tích hợp vào Spring ApplicationContext.

Để tích hợp đúng, cần xác nhận ba điều: dependency phù hợp đã có trên classpath; auto-configuration đã tạo đúng factory và các bean liên quan; ứng dụng đang tiêm và sử dụng đúng `CircuitBreakerFactory`. Khi cần một cơ chế riêng, ta có thể triển khai factory tương thích với abstraction của Spring Cloud.

## Chọn dependency và kiểm tra classpath

Với ứng dụng Spring MVC hoặc Spring Web thông thường, thêm starter Resilience4j:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
```

Nếu ứng dụng sử dụng Reactor và cần circuit breaker reactive, dùng starter tương ứng:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
```

Với Gradle, khai báo dependency tương đương:

```groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    // Chỉ thêm starter reactive nếu ứng dụng dùng Reactor:
    // implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j'
}
```

Quản lý phiên bản Spring Boot và Spring Cloud bằng các BOM tương thích với nhau. Không nên tự chọn một phiên bản Spring Cloud Circuit Breaker riêng lẻ rồi ghép với một release train bất kỳ: các thư viện Spring Cloud dùng chung nhiều API và thay đổi theo dòng phiên bản.

Sau khi khai báo dependency, kiểm tra dependency graph để xác nhận starter và các thư viện cần thiết thực sự nằm trong cấu hình runtime:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

Đọc kết quả theo các điểm sau:

- Có starter đúng với mô hình ứng dụng (imperative hoặc reactive).
- Có Spring Cloud Circuit Breaker core và implementation Resilience4j tương ứng.
- Không có hai phiên bản xung đột của cùng thư viện do dependency bắc cầu.
- Các phiên bản Spring Boot, Spring Cloud và Resilience4j thuộc tổ hợp được hỗ trợ.

Một dependency xuất hiện trong compile classpath chưa chắc đã có trong runtime classpath. Nếu ứng dụng báo `ClassNotFoundException` hoặc `NoClassDefFoundError`, hãy kiểm tra artifact thực tế được đóng gói và cấu hình runtime. Nếu gặp `NoSuchMethodError`, cần kiểm tra xung đột phiên bản vì class đã được tìm thấy nhưng API tại runtime không khớp với mã đã biên dịch.

## Phân biệt classpath, component scan và auto-configuration

Classpath cho JVM biết những lớp nào có thể được nạp. Component scan tìm các lớp do ứng dụng khai báo, thường là những lớp có `@Component`, `@Service` hoặc `@Configuration`. Auto-configuration của Spring Boot dùng điều kiện để quyết định có tạo bean cấu hình sẵn hay không.

Vì vậy, có thư viện trên classpath không đồng nghĩa factory chắc chắn đã được tạo. Auto-configuration có thể còn phụ thuộc vào:

- Có mặt của một lớp cụ thể, thường được kiểm tra bằng `@ConditionalOnClass`.
- Chưa có bean do ứng dụng tự khai báo, được kiểm tra bằng `@ConditionalOnMissingBean`.
- Một property bật hoặc tắt tính năng, được kiểm tra bằng `@ConditionalOnProperty`.
- Các bean phụ thuộc khác đã được đăng ký thành công.

Ví dụ minh họa một auto-configuration do ứng dụng tự viết:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(CircuitBreakerFactory.class)
@ConditionalOnProperty(
    prefix = "app.circuit-breaker",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ApplicationCircuitBreakerConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ApplicationCircuitBreakerPolicy applicationCircuitBreakerPolicy() {
        return new ApplicationCircuitBreakerPolicy();
    }
}
```

Đây chỉ là ví dụ về điều kiện tạo bean của ứng dụng; starter Resilience4j đã cung cấp auto-configuration riêng. Không cần tạo thêm một `CircuitBreakerFactory` Resilience4j nếu starter đã đăng ký factory phù hợp. Một bean factory trùng loại có thể làm thay đổi lựa chọn bean hoặc gây lỗi khi inject.

## Xác nhận factory được Spring tạo

Ứng dụng có thể inject abstraction `CircuitBreakerFactory` thay vì tự khởi tạo implementation:

```java
@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public CatalogItem find(String id) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.find(id),
            error -> CatalogItem.unavailable(id)
        );
    }
}
```

Factory tạo circuit breaker theo tên `catalog`. Tên này là định danh cấu hình; nên dùng tên ổn định theo dịch vụ phụ thuộc thay vì tạo một tên mới cho từng request. Fallback nhận nguyên nhân lỗi để ứng dụng có thể ghi log hoặc chọn phản hồi phù hợp. Ví dụ `CatalogItem.unavailable(id)` cần biểu diễn rõ dữ liệu chưa xác định, không nên giả dạng một kết quả tìm thấy hợp lệ.

Để kiểm tra auto-configuration, có thể bật báo cáo điều kiện của Spring Boot khi khởi động:

```bash
java -jar app.jar --debug
```

Trong báo cáo, tìm các cấu hình liên quan đến Circuit Breaker và Resilience4j. Kiểm tra cấu hình nào khớp, cấu hình nào bị bỏ qua và lý do. Có thể kiểm tra bean ở thời gian chạy bằng cách xem ApplicationContext hoặc dùng Spring Boot Actuator với endpoint `conditions` trong môi trường đã được bảo vệ phù hợp.

Nếu factory không được tạo, lần lượt kiểm tra dependency, điều kiện classpath, property cấu hình, bean thay thế do ứng dụng khai báo và báo cáo điều kiện. Nếu có nhiều bean cùng loại, xác định bean nào được chọn và vì sao; không giải quyết bằng cách thêm `@Primary` một cách tùy tiện khi chưa hiểu nguồn gốc bean trùng.

## Tự cấu hình factory Resilience4j

Thông thường, nên tùy chỉnh factory do starter cung cấp bằng `Customizer`. Ví dụ đặt cấu hình mặc định cho các instance:

```java
@Configuration(proxyBeanMethods = false)
public class Resilience4jCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfig() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(
                    CircuitBreakerConfig.custom()
                        .failureRateThreshold(50)
                        .slidingWindowSize(10)
                        .minimumNumberOfCalls(5)
                        .build()
                )
                .timeLimiterConfig(
                    TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(3))
                        .build()
                )
                .build()
        );
    }
}
```

Các import tương ứng thuộc Spring Cloud Circuit Breaker, Resilience4j và Java time. Tên lớp builder hoặc cách import có thể thay đổi theo release train đang dùng; hãy giữ các dependency cùng một dòng phiên bản. Trong cấu hình này, `failureRateThreshold`, `slidingWindowSize` và `minimumNumberOfCalls` điều khiển đánh giá lỗi; `TimeLimiterConfig` điều khiển thời gian chờ cho lời gọi được tích hợp với TimeLimiter. Hai cơ chế phối hợp với nhau nhưng có mục đích khác nhau.

Nếu cần cấu hình riêng theo tên, dùng API cấu hình theo instance của factory thay vì nhân bản bean factory. Ví dụ, một dịch vụ thanh toán có thể cần timeout ngắn và ngưỡng lỗi khác dịch vụ danh mục sản phẩm. Tách cấu hình theo tên giúp điều chỉnh chính sách theo đặc tính của dịch vụ phụ thuộc.

## Khi nào cần tự hiện thực CircuitBreakerFactory?

Chỉ nên tự triển khai factory khi ứng dụng cần một provider riêng, muốn bọc một thư viện nội bộ, hoặc cần đưa một cơ chế circuit breaker không có starter tương ứng vào abstraction Spring Cloud. Nếu Resilience4j đáp ứng yêu cầu, tùy chỉnh factory do starter cung cấp thường đơn giản và ít rủi ro hơn.

`CircuitBreakerFactory` là điểm tạo đối tượng `CircuitBreaker` theo định danh. Một implementation cần đảm nhiệm ít nhất các việc sau:

1. Nhận định danh ổn định của dịch vụ phụ thuộc.
2. Tìm chính sách hoặc cấu hình tương ứng, có thể dùng cấu hình mặc định khi chưa có cấu hình riêng.
3. Tạo một đối tượng `CircuitBreaker` có thể thực thi supplier và xử lý fallback theo hợp đồng của Spring Cloud.
4. Giữ trạng thái và số liệu đúng phạm vi của từng breaker; không tạo một trạng thái dùng chung ngoài ý muốn cho mọi dịch vụ.
5. Cho phép Spring đăng ký factory như một bean và để ứng dụng inject abstraction.

Ví dụ khung về cấu trúc factory tùy chỉnh:

```java
public final class CustomCircuitBreakerFactory
        extends CircuitBreakerFactory<CustomBreakerConfig, CustomBreakerConfigBuilder> {

    private final CustomBreakerRegistry registry;

    public CustomCircuitBreakerFactory(CustomBreakerRegistry registry) {
        this.registry = registry;
    }

    @Override
    public CircuitBreaker create(String id) {
        CustomBreakerConfig config = registry.configurationFor(id);
        return new CustomCircuitBreaker(id, config, registry);
    }

    @Override
    protected CustomBreakerConfigBuilder configBuilder(String id) {
        return new CustomBreakerConfigBuilder();
    }
}
```

`CustomBreakerConfig`, `CustomBreakerConfigBuilder`, `CustomBreakerRegistry` và `CustomCircuitBreaker` là các kiểu do ứng dụng định nghĩa để minh họa trách nhiệm của implementation. Builder phải tuân theo hợp đồng `ConfigBuilder` của phiên bản Spring Cloud Circuit Breaker đang dùng; factory cần nối kết quả cấu hình theo ID với registry của provider. Phần cài đặt cụ thể của builder và registry phụ thuộc vào cách provider lưu chính sách, vì vậy không nên sao chép các kiểu minh họa này như thể chúng là API có sẵn của Spring.

Một breaker tùy chỉnh cần xử lý đúng hai nhánh chính: cho supplier chạy khi trạng thái cho phép và trả về fallback khi lời gọi thất bại theo hợp đồng. Không được xem mọi lỗi nghiệp vụ là lỗi hạ tầng một cách mặc định. Cần phân loại ngoại lệ, ghi nhận kết quả và chuyển trạng thái theo chính sách đã chọn. Đồng thời, fallback không nên che mất thông tin nguyên nhân; hãy log hoặc phát metric trước khi trả phản hồi thay thế.

Đăng ký implementation bằng một bean có điều kiện để tránh xung đột với starter:

```java
@Configuration(proxyBeanMethods = false)
public class CustomCircuitBreakerConfiguration {

    @Bean
    @ConditionalOnMissingBean(CircuitBreakerFactory.class)
    CustomCircuitBreakerFactory customCircuitBreakerFactory(
            CustomBreakerRegistry registry) {
        return new CustomCircuitBreakerFactory(registry);
    }
}
```

Nếu đóng gói cấu hình này thành thư viện auto-configuration, cần đăng ký nó theo cơ chế của phiên bản Spring Boot. Spring Boot 3 dùng file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; các ứng dụng Spring Boot 2 thường dùng cơ chế `spring.factories`. Không đăng ký cùng một cấu hình theo cả hai cách trong một thư viện nếu không có chủ đích hỗ trợ phiên bản tương ứng.

## Reactive factory và classpath reactive

Ứng dụng dùng `Mono` hoặc `Flux` nên chọn starter reactive tương ứng và dùng `ReactiveCircuitBreakerFactory`. Không nên bọc một lời gọi reactive bằng factory imperative rồi gọi `block()` để ép đồng bộ, vì cách đó có thể chiếm thread và làm mất lợi ích của mô hình non-blocking.

Ví dụ sử dụng reactive factory:

```java
@Service
public class ReactiveCatalogService {
    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final WebClient webClient;

    public ReactiveCatalogService(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            WebClient webClient) {
        this.factory = factory;
        this.webClient = webClient;
    }

    public Mono<String> find(String id) {
        return factory.create("catalog")
            .run(
                webClient.get()
                    .uri("/catalog/{id}", id)
                    .retrieve()
                    .bodyToMono(String.class),
                error -> Mono.just("CATALOG_UNAVAILABLE")
            );
    }
}
```

Kiểm tra classpath reactive riêng biệt nếu Spring không tìm thấy `ReactiveCircuitBreakerFactory` hoặc không tạo được implementation reactive. Chỉ thêm starter reactive khi ứng dụng thực sự dùng Reactor; một ứng dụng MVC không cần đưa thêm các thành phần reactive chỉ để dùng circuit breaker imperative.

## Quy trình chẩn đoán khi khởi động

Khi ứng dụng không thể tạo hoặc inject factory, kiểm tra theo trình tự:

| Triệu chứng | Vị trí cần kiểm tra |
| --- | --- |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Dependency runtime, artifact được đóng gói, starter imperative/reactive đã chọn. |
| `NoSuchMethodError` | Phiên bản Spring Boot, Spring Cloud và dependency bắc cầu có tương thích hay không. |
| Không có bean `CircuitBreakerFactory` | Báo cáo auto-configuration, điều kiện classpath, property bật/tắt và cấu hình bị loại trừ. |
| Có nhiều bean cùng loại | Các cấu hình tự viết, component scan, starter khác và điều kiện `@ConditionalOnMissingBean`. |
| Circuit breaker luôn dùng cấu hình mặc định | Tên ID khi gọi `create`, tên instance trong cấu hình và thứ tự áp dụng customizer. |
| Reactive factory không được tạo | Starter Reactor, các lớp Reactor trên runtime classpath và auto-configuration reactive. |

Sau khi sửa, khởi động lại ứng dụng và xác nhận factory được inject, breaker được tạo với đúng ID, fallback chạy khi có lỗi và metrics phản ánh kết quả. Trong môi trường phát triển, có thể thử một dịch vụ giả lập trả lỗi hoặc trì hoãn phản hồi để quan sát hành vi. Không nên dùng endpoint chẩn đoán hoặc actuator công khai mà chưa giới hạn quyền truy cập.

## Các nguyên tắc cần nhớ

- Dependency quyết định lớp nào có trên classpath; auto-configuration quyết định bean nào được tạo.
- Dùng starter đúng loại và quản lý phiên bản bằng BOM tương thích.
- Ưu tiên tùy chỉnh factory Resilience4j được starter cung cấp trước khi tự triển khai `CircuitBreakerFactory`.
- Dùng tên breaker ổn định để ánh xạ chính xác cấu hình và metrics.
- Giữ fallback rõ nghĩa và phân biệt lỗi nghiệp vụ với lỗi phụ thuộc.
- Với Reactor, dùng reactive starter và `ReactiveCircuitBreakerFactory` xuyên suốt pipeline.

Khi classpath và auto-configuration được xác nhận đúng, ứng dụng có thể sử dụng abstraction `CircuitBreakerFactory` nhất quán. Điều này giúp thay đổi chính sách bảo vệ dịch vụ phụ thuộc có kiểm soát và hỗ trợ triển khai circuit breaker trong Spring Cloud mà không làm rối mã nghiệp vụ.
