# Chọn starter Resilience4j cho ứng dụng blocking hoặc reactive

Khi tích hợp Circuit Breaker vào ứng dụng Spring Cloud, cần chọn starter Resilience4j phù hợp với cách ứng dụng thực thi lời gọi đến dịch vụ phụ thuộc. Ứng dụng gọi đồng bộ theo kiểu blocking sử dụng starter Resilience4j thông thường; ứng dụng xử lý dữ liệu bằng reactive pipeline sử dụng starter Reactor Resilience4j. Chọn đúng starter giúp Spring Cloud tạo đúng loại Circuit Breaker factory và giữ nguyên mô hình xử lý của ứng dụng.

Trong phạm vi SPRING_CLOUD_CIRCUIT_BREAKER, bước chuẩn bị môi trường gồm xác định kiểu ứng dụng, chọn dependency tương ứng, quản lý phiên bản Spring Cloud tương thích với Spring Boot và kiểm tra dependency đã được đưa vào classpath. Starter chỉ cung cấp tích hợp; chính sách bảo vệ như ngưỡng lỗi, sliding window, thời gian OPEN và fallback vẫn cần được cấu hình theo nhu cầu của dịch vụ.

## 1. Phân biệt blocking và reactive trước khi chọn dependency

Điểm quyết định là kiểu dữ liệu và cách thực thi của lời gọi được bảo vệ:

| Tiêu chí | Blocking | Reactive |
|---|---|---|
| Kiểu kết quả thường gặp | Giá trị trả về trực tiếp như **Stock** hoặc **Product** | Publisher như **Mono<Stock>** hoặc **Flux<Product>** |
| Cách thực thi | Luồng gọi chờ thao tác hoàn tất | Pipeline phát tín hiệu khi có dữ liệu, lỗi hoặc hoàn tất |
| API Circuit Breaker | **CircuitBreakerFactory** | **ReactiveCircuitBreakerFactory** |
| Starter Resilience4j | **spring-cloud-starter-circuitbreaker-resilience4j** | **spring-cloud-starter-circuitbreaker-reactor-resilience4j** |
| Thành phần web thường dùng | Spring MVC với **spring-boot-starter-web** | Spring WebFlux với **spring-boot-starter-webflux** |
| Client thường gặp | **RestClient**, **RestTemplate** hoặc client đồng bộ | **WebClient** trả về **Mono** hoặc **Flux** |

Một ứng dụng Spring MVC thường có các phương thức gọi dịch vụ phụ thuộc trả về kết quả trực tiếp. Khi một lời gọi mất hai giây, luồng xử lý đang gọi thường phải chờ trong khoảng thời gian đó. Đây là mô hình blocking.

Trong ứng dụng WebFlux, client thường trả về **Mono<T>** hoặc **Flux<T>**. Các bước xử lý được nối thành một reactive pipeline; luồng không cần chờ đồng bộ tại từng bước I/O. Đây là mô hình reactive. Circuit Breaker cần bọc đúng publisher để khi trạng thái OPEN, lỗi từ chối được phát ra trong pipeline và được xử lý bằng fallback reactive.

Không chọn starter chỉ dựa vào việc dự án có dùng Spring Boot hay có một endpoint HTTP. Hãy xem chữ ký của thao tác gọi dịch vụ phụ thuộc. Nếu thao tác trả về giá trị trực tiếp và thực thi đồng bộ, dùng API blocking. Nếu thao tác trả về **Mono** hoặc **Flux** và được xử lý theo reactive pipeline, dùng API reactive. Không nên gọi **block()** chỉ để biến một publisher thành lời gọi đồng bộ rồi xem đó là cách tích hợp reactive.

## 2. Dependency cần có cho từng loại ứng dụng

Spring Cloud CircuitBreaker hỗ trợ Resilience4j qua hai starter chính:

- **Blocking:** **org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j**
- **Reactive:** **org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j**

Ứng dụng cần thêm starter web tương ứng với mô hình endpoint và client đang dùng. Spring MVC thường dùng **spring-boot-starter-web**; WebFlux thường dùng **spring-boot-starter-webflux**.

| Kiểu ứng dụng | Spring Boot web starter | Spring Cloud CircuitBreaker starter |
|---|---|---|
| Spring MVC, client đồng bộ | **spring-boot-starter-web** | **spring-cloud-starter-circuitbreaker-resilience4j** |
| WebFlux, client reactive | **spring-boot-starter-webflux** | **spring-cloud-starter-circuitbreaker-reactor-resilience4j** |

Hai starter CircuitBreaker trên là lựa chọn cho hai API khác nhau. Không thêm cả hai theo thói quen. Nếu một ứng dụng thực sự có cả luồng blocking và reactive cần được bảo vệ, hãy xác định rõ từng luồng, kiểm tra auto-configuration của phiên bản Spring Cloud đang sử dụng và chỉ đưa các dependency cần thiết vào dự án. Việc có **spring-boot-starter-web** hay **spring-boot-starter-webflux** tự nó không thay thế lựa chọn CircuitBreaker starter.

## 3. Quản lý phiên bản Spring Boot và Spring Cloud

Spring Cloud có release train và ma trận tương thích với các phiên bản Spring Boot. Vì vậy, không nên tự chọn một phiên bản starter CircuitBreaker độc lập hoặc lấy phiên bản mới nhất của Spring Cloud mà không kiểm tra khả năng tương thích.

Cách thông dụng là dùng Spring Cloud BOM (**spring-cloud-dependencies**) để quản lý phiên bản các dependency Spring Cloud. Phiên bản release train phải phù hợp với phiên bản Spring Boot mà dự án đang dùng. Có thể tra bảng tương thích trong tài liệu Spring Cloud trước khi đặt giá trị cho thuộc tính **spring-cloud.version**.

Ví dụ Maven dưới đây minh họa cấu trúc quản lý phiên bản. Giá trị **REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN** là chỗ cần thay bằng release train tương thích với Spring Boot của dự án:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

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
~~~

Nếu dự án dùng Spring Boot parent hoặc Spring Boot dependency management, các dependency Spring Boot như **spring-boot-starter-web** thường đã được quản lý phiên bản. Spring Cloud BOM quản lý các dependency thuộc Spring Cloud. Nhờ đó, khai báo starter không cần gắn một phiên bản tùy ý vào từng dependency.

Khi nâng Spring Boot, hãy kiểm tra lại release train Spring Cloud tương ứng và nâng BOM theo cặp tương thích. Tránh trộn nhiều release train hoặc ghi đè phiên bản riêng của Resilience4j nếu chưa có lý do rõ ràng, vì điều đó có thể tạo ra tập dependency không đồng bộ.

## 4. Cấu hình Maven cho ứng dụng blocking

Với ứng dụng Spring MVC gọi dịch vụ phụ thuộc bằng client đồng bộ, thêm hai dependency sau vào phần **dependencies** của **pom.xml**. Ví dụ giả định dự án đã khai báo Spring Boot parent và import Spring Cloud BOM như phần trên:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>
</dependencies>
~~~

Starter CircuitBreaker đưa tích hợp Resilience4j cho Spring Cloud CircuitBreaker vào classpath. Ứng dụng có thể nhận **CircuitBreakerFactory** và tạo bộ ngắt theo tên cho từng dịch vụ phụ thuộc.

Ví dụ một gateway gọi client đồng bộ:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

**InventoryClient.getStock** trong ví dụ là thao tác đồng bộ và trả về **Stock**. Nếu Circuit Breaker cho phép lời gọi, supplier được thực thi. Nếu bộ ngắt đang OPEN, supplier bị từ chối và hàm fallback được gọi để trả kết quả dự phòng. **Stock.unavailable** là phương thức minh họa do ứng dụng định nghĩa; dữ liệu fallback thực tế phải tuân theo quy tắc nghiệp vụ.

## 5. Cấu hình Maven cho ứng dụng reactive

Với ứng dụng WebFlux dùng **WebClient** và reactive pipeline, khai báo WebFlux cùng starter Reactor Resilience4j:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
~~~

Trong ứng dụng reactive, sử dụng **ReactiveCircuitBreakerFactory**. Hàm gọi được bảo vệ trả về **Mono** và fallback cũng phải trả về **Mono**:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryGateway {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

Ở đây, **ReactiveInventoryClient.getStock** trả về **Mono<Stock>**. Khi bộ ngắt đang OPEN, lỗi từ chối được phát ra trong reactive pipeline; hàm fallback trả về một publisher thay thế. Không gọi **block()** bên trong fallback hoặc trong controller WebFlux, vì điều đó có thể chặn luồng xử lý và làm giảm lợi ích của mô hình reactive.

Nếu client trả về **Flux<T>**, hãy kiểm tra API reactive mà phiên bản Spring Cloud đang dùng cung cấp và giữ việc xử lý dữ liệu trong pipeline tương ứng. Không chuyển đổi qua lại giữa **Mono**, **Flux** và giá trị đồng bộ một cách tùy tiện chỉ để khớp chữ ký.

## 6. Cấu hình dependency với Gradle

Với Gradle, có thể import Spring Cloud BOM bằng **platform** rồi khai báo starter phù hợp. Ví dụ Groovy DSL dưới đây dùng biến **springCloudVersion** đã được định nghĩa trong cấu hình dự án với release train tương thích:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    // Chọn một cặp dependency phù hợp với mô hình ứng dụng.
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j"
}
~~~

Với ứng dụng reactive, thay hai dependency trong ví dụ bằng cặp sau:

~~~groovy
implementation "org.springframework.boot:spring-boot-starter-webflux"
implementation "org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j"
~~~

Nếu dự án dùng Gradle Kotlin DSL hoặc plugin quản lý dependency khác, cú pháp khai báo BOM có thể khác; nguyên tắc vẫn là import đúng Spring Cloud release train và không tự ghim phiên bản starter lệch khỏi BOM.

## 7. Kiểm tra starter đã được chọn đúng

Sau khi sửa dependency, cần xác minh dependency đã được giải quyết và ứng dụng nhận đúng loại factory. Với Maven, có thể xem cây dependency bằng lệnh:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud,io.github.resilience4j
~~~

Với Gradle, xem runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra kết quả theo các điểm sau:

1. Có đúng starter CircuitBreaker mà luồng gọi cần sử dụng.
2. Các dependency Spring Cloud được quản lý bởi release train đã chọn.
3. Không có nhiều phiên bản không mong muốn của cùng một thư viện Resilience4j.
4. Ứng dụng khởi động được và Spring có thể inject đúng factory: **CircuitBreakerFactory** cho luồng blocking hoặc **ReactiveCircuitBreakerFactory** cho luồng reactive.
5. Lời gọi được bảo vệ dùng đúng kiểu trả về. Fallback blocking trả về giá trị; fallback reactive trả về publisher.

Nếu không tìm thấy factory, hãy kiểm tra tên artifact, dependency scope, BOM và auto-configuration trước khi thêm các thư viện Resilience4j riêng lẻ. Nếu classpath có đúng starter nhưng lỗi do không tương thích phiên bản, hãy điều chỉnh Spring Cloud release train theo Spring Boot đang dùng. Không giải quyết lỗi bằng cách thêm ngẫu nhiên nhiều starter hoặc ghi đè từng phiên bản thư viện.

## 8. Những nhầm lẫn thường gặp khi chọn starter

- **Dùng starter blocking cho publisher reactive:** code có thể không có factory reactive cần thiết hoặc buộc phải chuyển đổi sai mô hình. Chọn starter Reactor khi thao tác được bảo vệ trả về **Mono** hoặc **Flux**.
- **Dùng starter reactive chỉ vì dự án có WebFlux:** một phần code vẫn có thể gọi client đồng bộ. Hãy chọn theo API và cách thực thi của từng luồng, không chỉ theo framework endpoint.
- **Nhầm starter CircuitBreaker với thư viện Resilience4j độc lập:** starter Spring Cloud CircuitBreaker cung cấp lớp tích hợp và factory của Spring Cloud. Nếu ứng dụng chủ ý dùng API Resilience4j trực tiếp, cách khai báo dependency và cấu hình sẽ khác.
- **Bỏ qua Spring Cloud BOM:** các module Spring Cloud và Spring Boot có thể không tương thích khi dùng phiên bản tùy ý.
- **Khai báo cả hai starter nhưng không kiểm tra auto-configuration:** trong ứng dụng có nhiều mô hình gọi, cần xác minh factory nào được tạo và được inject vào từng thành phần.
- **Dùng fallback sai kiểu:** fallback blocking phải trả về kết quả phù hợp; fallback reactive phải trả về publisher tương ứng. Trả **Stock** ở nơi cần **Mono<Stock>** sẽ gây lỗi kiểu hoặc buộc phải chuyển đổi không cần thiết.

## 9. Checklist chuẩn bị môi trường

Trước khi chuyển sang cấu hình chính sách Circuit Breaker, hãy xác nhận:

- [ ] Đã xác định lời gọi phụ thuộc là blocking hay reactive.
- [ ] Đã chọn đúng starter Resilience4j của Spring Cloud CircuitBreaker.
- [ ] Đã chọn web starter phù hợp với ứng dụng, nếu ứng dụng cần web stack.
- [ ] Đã import Spring Cloud BOM tương thích với phiên bản Spring Boot.
- [ ] Dependency tree không có xung đột phiên bản ngoài dự kiến.
- [ ] Ứng dụng khởi động và inject được factory tương ứng.
- [ ] Ví dụ lời gọi và fallback dùng đúng kiểu dữ liệu đồng bộ hoặc reactive.

Khi các bước trên hoàn tất, môi trường đã sẵn sàng để cấu hình sliding window, failure rate, slow-call rate, thời gian chờ OPEN, số lượt thăm dò HALF_OPEN, timeout, bulkhead và fallback. Việc chọn starter chỉ xác định lớp tích hợp và mô hình API; hiệu quả bảo vệ dịch vụ còn phụ thuộc vào chính sách và cách xử lý lỗi ở các bước tiếp theo.

## Kết luận

Ứng dụng gọi đồng bộ nên dùng **spring-cloud-starter-circuitbreaker-resilience4j** cùng API **CircuitBreakerFactory**. Ứng dụng xử lý publisher bằng Reactor nên dùng **spring-cloud-starter-circuitbreaker-reactor-resilience4j** cùng API **ReactiveCircuitBreakerFactory**. Quản lý Spring Cloud bằng BOM tương thích với Spring Boot, xác minh classpath và giữ đúng kiểu trả về của lời gọi cùng fallback sẽ tạo nền tảng ổn định để cấu hình Circuit Breaker cho từng dịch vụ phụ thuộc.
