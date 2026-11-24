# Chọn tích hợp cho Gateway WebFlux và kiểm tra hỗ trợ theo phiên bản

## Bắt đầu từ đúng loại Gateway

Spring Cloud Gateway có các mô hình chạy khác nhau. Bài này tập trung vào **Gateway Server WebFlux**, chạy trên Spring WebFlux, Reactor và mô hình I/O non-blocking. Trong mô hình đó, route filter `CircuitBreaker` sử dụng API reactive của Spring Cloud Circuit Breaker, tức `ReactiveCircuitBreakerFactory` và `ReactiveCircuitBreaker`.

Đây là điểm quyết định khi chọn dependency. Gateway WebFlux cần một provider Circuit Breaker có tích hợp reactive. Nếu ứng dụng dùng Resilience4j, lựa chọn thông thường là starter `spring-cloud-starter-circuitbreaker-reactor-resilience4j`. Starter imperative `spring-cloud-starter-circuitbreaker-resilience4j` dành cho lời gọi đồng bộ và không phải lựa chọn thay thế cho reactive provider trong filter chain WebFlux.

Trước khi thêm dependency, xác định ứng dụng đang dùng:

| Loại ứng dụng | Stack thực thi | Tích hợp Circuit Breaker cần xem xét |
| --- | --- | --- |
| Spring Cloud Gateway Server WebFlux | WebFlux, Reactor, thường dùng Reactor Netty | Reactive Circuit Breaker provider; với Resilience4j là Reactor Resilience4j starter. |
| Ứng dụng service Spring MVC đồng bộ | Servlet, lời gọi Java đồng bộ | Imperative Circuit Breaker provider hoặc Resilience4j Spring Boot integration. |
| Spring Cloud Gateway Server Web MVC | Servlet và MVC filter functions | Kiểm tra tài liệu Gateway MVC và provider tương thích với release train; không áp dụng máy móc hướng dẫn WebFlux. |

Không suy ra loại Gateway chỉ từ việc dự án có tên Spring Cloud Gateway. Hãy kiểm tra starter, application type và API route filter thực tế. Trộn `spring-boot-starter-web` với stack WebFlux mà không có chủ đích có thể khiến Spring Boot chọn application type servlet hoặc tạo cấu hình khó dự đoán. Giữ Gateway WebFlux thuần reactive nếu đó là kiến trúc đã chọn.

## Chọn starter tương thích

Với một ứng dụng Gateway WebFlux dùng Resilience4j, các dependency thường gồm Gateway WebFlux và reactive Circuit Breaker provider. Ví dụ cho các dòng Gateway sử dụng starter tổng hợp truyền thống:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
```

Ở các dòng Spring Cloud Gateway mới hơn, artifact Gateway có thể được tách theo server implementation; ứng dụng WebFlux có thể cần starter chuyên biệt như `spring-cloud-starter-gateway-server-webflux`. Tên artifact, cách đóng gói và namespace cấu hình route thay đổi theo major/release train. Vì vậy, lấy dependency từ trang tài liệu của đúng phiên bản đang dùng, rồi giữ reactive Circuit Breaker starter cùng release train đó.

Không thêm đồng thời cả hai Circuit Breaker starter Resilience4j imperative và reactive chỉ để “cho chắc”. Chọn đúng loại theo call model giúp auto-configuration tạo đúng factory và tránh đưa các cấu hình không cần thiết vào context. Nếu ứng dụng còn có service đồng bộ riêng, có thể service đó dùng imperative integration trong module phù hợp; Gateway WebFlux vẫn cần reactive integration.

## Quản lý phiên bản bằng Spring Cloud BOM

Spring Boot, Spring Cloud Gateway, Spring Cloud Circuit Breaker và các thư viện nền cần thuộc một tổ hợp tương thích. Dùng Spring Cloud BOM để quản lý phiên bản các artifact Spring Cloud, đồng thời dùng Spring Boot dependency management cho các thư viện nền như Spring Framework và Reactor.

Ví dụ Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khai báo version của BOM theo release train được Spring công bố là tương thích với Spring Boot của dự án. Không chọn bản Gateway mới nhất rồi ghép với Spring Boot hoặc Spring Cloud Circuit Breaker của một dòng cũ. Cũng không override riêng Reactor, Spring Framework hoặc Resilience4j nếu chưa xác nhận ma trận tương thích.

Ví dụ Gradle:

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation "org.springframework.cloud:spring-cloud-starter-gateway"
    implementation "org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j"
}
```

Nếu release train đang dùng yêu cầu artifact Gateway WebFlux chuyên biệt, thay dependency Gateway theo tài liệu của release đó. Không thay đổi tên artifact theo phỏng đoán; xác nhận dependency có tồn tại trong BOM và repository mà dự án đang sử dụng.

## Kiểm tra ma trận hỗ trợ trước khi triển khai

Hãy kiểm tra các lớp tương thích theo thứ tự sau:

1. **Spring Boot:** xác định phiên bản Boot và Java runtime mà ứng dụng đang dùng.
2. **Spring Cloud release train:** chọn train được công bố tương thích với Boot đó.
3. **Gateway implementation:** xác nhận dự án dùng Gateway Server WebFlux và chọn đúng starter/artifact cho release train.
4. **Circuit Breaker provider:** với Resilience4j, chọn Reactor provider starter cùng dòng Spring Cloud tương ứng.
5. **Reactor và Resilience4j:** để BOM quản lý phiên bản trước; chỉ override khi có lý do và đã kiểm tra compatibility.

Các release train có thể đổi artifact, package, property namespace và điều kiện auto-configuration. Vì vậy, không dùng một bảng phiên bản cố định trong bài này để thay cho ma trận chính thức của dự án. Ghi lại các phiên bản thực tế từ dependency graph và đối chiếu release notes của đúng Gateway, Circuit Breaker và Spring Boot trước khi nâng cấp.

Một số khác biệt cần chú ý:

| Thành phần | Điều cần xác nhận |
| --- | --- |
| Gateway starter | Starter tổng hợp hay starter riêng cho WebFlux trong release train hiện tại. |
| Route properties | Namespace cấu hình route của đúng major Gateway; không mặc định mọi dòng đều dùng cùng prefix. |
| Circuit Breaker starter | Có cung cấp `ReactiveCircuitBreakerFactory` tương thích với WebFlux hay chỉ có factory imperative. |
| Filter factory | `CircuitBreaker` route filter có được auto-configuration đăng ký trong application context hay không. |
| Resilience4j config | Property instance, TimeLimiter và status code được hỗ trợ trong phiên bản provider hiện tại. |

## Kiểm tra runtime dependency graph

Sau khi khai báo dependency, kiểm tra runtime classpath để phát hiện thiếu module hoặc xung đột phiên bản:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

Tìm các nhóm sau:

- Spring Cloud Gateway WebFlux/server WebFlux tương ứng.
- Spring WebFlux và Reactor Core.
- Spring Cloud Circuit Breaker core.
- Reactive Resilience4j provider và các module Resilience4j được provider yêu cầu.
- Reactor Netty hoặc runtime server phù hợp với Gateway WebFlux.

Kiểm tra không có hai phiên bản khác nhau của Spring Cloud Circuit Breaker hoặc Resilience4j do dependency bắc cầu. Nếu thấy `NoClassDefFoundError`, kiểm tra module runtime bị thiếu. Nếu thấy `NoSuchMethodError` hoặc `AbstractMethodError`, kiểm tra các artifact có được resolve từ cùng một dòng tương thích hay không.

## Xác nhận auto-configuration tạo reactive factory

Gateway CircuitBreaker filter cần reactive factory. Có thể bật báo cáo điều kiện khi chạy ứng dụng:

```bash
java -jar gateway-app.jar --debug
```

Trong Condition Evaluation Report, tìm cấu hình auto-configuration của Spring Cloud Circuit Breaker Resilience4j và Gateway. Kiểm tra điều kiện classpath, bean bị thiếu, property bật/tắt và lý do cấu hình không khớp.

Có thể kiểm tra ApplicationContext trong môi trường phát triển bằng cách inject `ReactiveCircuitBreakerFactory` vào một bean chẩn đoán hoặc xem danh sách bean qua Actuator nếu endpoint đã được bật và bảo vệ. Việc context khởi động thành công chưa chứng minh route filter đã sử dụng đúng provider; cần xác nhận route có filter `CircuitBreaker` và tên breaker được tạo theo cấu hình.

Nếu Gateway filter báo không tìm thấy reactive factory hoặc không đăng ký được filter, kiểm tra theo thứ tự:

1. Có đúng reactive Circuit Breaker starter trên runtime classpath không?
2. Gateway có đang chạy bằng WebFlux application type không?
3. Có cấu hình loại trừ auto-configuration hoặc property tắt provider không?
4. Có bean `ReactiveCircuitBreakerFactory` tự định nghĩa hoặc bean khác làm thay đổi điều kiện tạo factory không?
5. Các phiên bản Gateway, Circuit Breaker core và provider có cùng tổ hợp tương thích không?

Không giải quyết lỗi bằng cách tạo một factory thủ công trước khi hiểu tại sao auto-configuration không chạy. Làm vậy có thể che lỗi classpath và khiến các cấu hình provider không được áp dụng.

## Cấu hình route CircuitBreaker trên Gateway WebFlux

Ví dụ route đến dịch vụ danh mục. Namespace dưới đây minh họa dạng cấu hình thường gặp ở các dòng Gateway dùng `spring.cloud.gateway.routes`; hãy dùng prefix tương ứng trong tài liệu của major Gateway đang triển khai:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: http://catalog-service:8080
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogGateway
                fallbackUri: forward:/fallback/catalog
                statusCodes:
                  - "500"
                  - "502"
                  - "503"
                  - "504"
```

Ở một major Gateway mới, prefix có thể được đặt dưới namespace riêng của Gateway Server WebFlux. Không khai báo đồng thời hai prefix để hy vọng một trong hai hoạt động; hãy dùng đúng property namespace của release đang chạy và kiểm tra route đã được nạp trong runtime.

Filter dùng reactive factory để bọc việc chuyển tiếp đến route đích. `name` là định danh breaker. `fallbackUri` dạng `forward:` chuyển nội bộ đến handler trong Gateway. `statusCodes` liệt kê response status mà filter cần xem là lỗi. Chỉ chọn status có ý nghĩa là dependency đang suy giảm; không mặc định mọi 4xx là lỗi hạ tầng.

## Cấu hình Resilience4j instance

Với Resilience4j provider, cấu hình instance có tên khớp `catalogGateway`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogGateway:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Breaker đánh giá tối đa 20 kết quả gần nhất và chỉ bắt đầu tính tỷ lệ sau ít nhất 10 lời gọi được ghi nhận. Khi failure rate đạt hoặc vượt 50%, nó có thể chuyển sang `OPEN`. Sau thời gian chờ, breaker có thể vào `HALF_OPEN` và cho phép tối đa ba lời gọi thử nghiệm theo cấu hình.

Nếu filter và instance không dùng cùng tên, breaker có thể nhận cấu hình mặc định hoặc không nhận chính sách mà bạn mong đợi. Kiểm tra tên được factory nhận và metrics theo tên đó. Các property chi tiết cần đối chiếu với phiên bản Resilience4j được BOM resolve.

## Fallback phải là handler reactive trong Gateway

Ví dụ controller xử lý URI nội bộ `/fallback/catalog`:

```java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GatewayFallbackController {

    @RequestMapping("/fallback/catalog")
    public Mono<ResponseEntity<Map<String, String>>> catalogFallback() {
        Map<String, String> body = Map.of(
            "code", "CATALOG_UNAVAILABLE",
            "message", "Dịch vụ danh mục tạm thời chưa thể xử lý yêu cầu."
        );

        return Mono.just(ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(body));
    }
}
```

Handler trả HTTP 503 để client nhận biết dịch vụ tạm thời không khả dụng. Nếu Gateway có dữ liệu cache hoặc nguồn thay thế, có thể trả phản hồi phù hợp nhưng cần đánh dấu rõ dữ liệu cũ hoặc trạng thái chưa xác định. Fallback không nên gọi lại chính route đang lỗi, vì có thể tạo vòng lặp hoặc dồn thêm tải vào dependency.

## Phân biệt reactive filter với lời gọi imperative

Gateway WebFlux xử lý request bằng reactive pipeline. CircuitBreaker filter tích hợp với `ReactiveCircuitBreakerFactory`; việc chuyển tiếp và fallback diễn ra theo publisher. Không dùng `CircuitBreakerFactory` imperative để bọc một publisher rồi gọi `block()` trong filter chain.

Nếu một ứng dụng service đồng bộ khác cũng cần bảo vệ lời gọi, nó có thể dùng imperative factory hoặc Resilience4j annotation riêng. Đó là quyết định ở module/service đồng bộ, không phải lý do để Gateway WebFlux chuyển sang imperative provider.

Tương tự, không chạy một HTTP client blocking trên event-loop. Nếu Gateway cần gọi một thư viện blocking trong custom filter hoặc handler, phải cô lập công việc trên scheduler phù hợp, đặt timeout và giới hạn concurrency; ưu tiên API reactive sẵn có như WebClient cho lời gọi mạng.

## Kiểm thử theo phiên bản thực tế

Sau khi cấu hình, kiểm tra bằng một dịch vụ đích giả lập có thể trả thành công, lỗi và trì hoãn phản hồi. Các bước nên thực hiện:

1. Khởi động Gateway và xác nhận application type là reactive.
2. Xác nhận route và CircuitBreaker filter được nạp từ đúng namespace cấu hình.
3. Gửi request khi dependency trả 200; response phải đi qua bình thường.
4. Cho dependency trả status nằm trong `statusCodes`; xác nhận breaker ghi nhận lỗi và fallback được gọi theo cấu hình.
5. Làm dependency không thể kết nối; xác nhận exception được provider ghi nhận và fallback hoạt động.
6. Gửi đủ số lỗi để breaker mở; xác nhận request tiếp theo không được chuyển tiếp đến dependency.
7. Quan sát sau thời gian `OPEN`; xác nhận hành vi `HALF_OPEN` và kết quả lời gọi thử.
8. Kiểm tra metrics, log và trace để biết breaker name, số lời gọi bị từ chối và số lần fallback.

Đối chiếu kết quả giữa route filter, Resilience4j metrics và số request mà dịch vụ đích thực sự nhận. Một fallback trả HTTP 503 không tự chứng minh Circuit Breaker đã mở; nguyên nhân cũng có thể là timeout hoặc lỗi kết nối tức thời.

## Các lỗi lựa chọn tích hợp thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng starter Circuit Breaker imperative cho Gateway WebFlux | Không có reactive provider phù hợp với filter chain. | Chọn Reactor provider starter. |
| Dùng nhầm Gateway MVC và Gateway WebFlux | Artifact, filter API và application type không khớp. | Xác nhận server implementation trước khi chọn dependency. |
| Ghép Gateway với Spring Boot/Spring Cloud không tương thích | Lỗi auto-configuration, linkage hoặc startup. | Dùng ma trận release train và BOM tương ứng. |
| Sao chép property prefix từ major khác | Route không được nạp hoặc filter không xuất hiện. | Dùng namespace của đúng phiên bản Gateway. |
| Có dependency nhưng không có reactive factory | Auto-configuration bị loại trừ hoặc thiếu provider. | Kiểm tra condition report và runtime classpath. |
| Đặt sai breaker name | Instance không nhận cấu hình dự kiến. | Đồng bộ `name` giữa route và Resilience4j. |
| Gọi `block()` trong Gateway filter | Chặn event-loop và làm giảm khả năng xử lý đồng thời. | Giữ pipeline reactive từ đầu đến cuối. |
| Chỉ kiểm tra response fallback | Có thể nhầm timeout với trạng thái `OPEN`. | Đối chiếu state, event và số request đến dependency. |

Chọn đúng tích hợp cho Gateway WebFlux nghĩa là chọn đúng server implementation, reactive Circuit Breaker provider và một tổ hợp phiên bản Spring Boot/Spring Cloud tương thích. Sau đó cần xác nhận factory, filter, route properties và fallback thực sự được kích hoạt ở runtime. Quy trình này giúp Gateway bảo vệ dependency bằng reactive pipeline mà không vô tình đưa lời gọi đồng bộ hoặc cấu hình của một major khác vào hệ thống.
