# Kiểm tra điều kiện tự cấu hình và xung đột thư viện

Spring Cloud LoadBalancer chỉ hoạt động khi ứng dụng có đúng các thư viện, phiên bản tương thích và những bean cần thiết trên application context. Một dependency có mặt trong file build chưa đủ để kết luận tính năng đã được kích hoạt: Spring Boot còn đánh giá các điều kiện tự cấu hình, còn LoadBalancer cần một nguồn cung cấp danh sách `ServiceInstance` cho service ID được gọi.

Trong module này, ứng dụng dùng service ID như `inventory-service` để gọi dịch vụ tồn kho. Spring Cloud LoadBalancer chọn một instance từ danh sách do discovery client hoặc nguồn cấu hình tĩnh cung cấp. Khi client không được cấu hình đúng, ứng dụng có thể khởi động nhưng request không được cân bằng tải, hoặc ứng dụng dừng ngay khi tạo bean do thiếu class, thiếu bean hay xung đột phiên bản. Bài này hướng dẫn kiểm tra từ dependency đến điều kiện auto-configuration và cách xác định nguyên nhân trước khi thay đổi cấu hình.

## 1. Phân biệt ba lớp cần kiểm tra

Khi chẩn đoán Spring Cloud LoadBalancer, hãy tách ba câu hỏi:

1. **Thư viện có trên runtime classpath không?** Starter và các dependency nền tảng phải được resolve với phiên bản tương thích. Nếu class cần thiết không có, điều kiện `@ConditionalOnClass` không thỏa mãn và cấu hình tương ứng có thể không được nạp.
2. **Auto-configuration có được kích hoạt không?** Spring Boot đánh giá điều kiện về class, bean, property, kiểu ứng dụng và các điều kiện khác. Một auto-configuration có thể được phát hiện nhưng bị bỏ qua vì một điều kiện không thỏa.
3. **Ứng dụng có đủ dữ liệu và client phù hợp để gọi service ID không?** LoadBalancer cần danh sách instance cho service ID. HTTP client cũng phải được đánh dấu hoặc tích hợp theo cơ chế load balancing tương ứng.

Ba lớp này liên quan nhưng không thay thế nhau. Ví dụ, `spring-cloud-starter-loadbalancer` có thể đã được resolve và auto-configuration có thể đã chạy, nhưng `inventory-service` vẫn không có instance nào để chọn. Ngược lại, registry có thể chứa instance đầy đủ nhưng một `RestClient` thông thường không được cấu hình load balancing nên không phân giải service ID.

## 2. Quản lý dependency bằng BOM tương thích

Spring Boot và Spring Cloud phát hành theo các dòng phiên bản riêng. Cách an toàn là để Spring Boot quản lý dependency của Boot và import Spring Cloud BOM thuộc release train tương thích với phiên bản Spring Boot đang dùng. BOM giúp các module như `spring-cloud-commons`, `spring-cloud-loadbalancer`, OpenFeign và discovery client được chọn theo một bộ phiên bản đồng bộ.

Ví dụ Maven:

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Chỉ thêm discovery starter mà ứng dụng thực sự sử dụng. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

`YOUR_COMPATIBLE_RELEASE_TRAIN` là chỗ đặt phiên bản release train phù hợp với Spring Boot của dự án. Hãy tra bảng tương thích trong tài liệu Spring Cloud tại thời điểm nâng cấp; không sao chép một số phiên bản từ dự án khác mà chưa kiểm tra. Khi BOM đã quản lý dependency, không cần tự đặt phiên bản riêng cho từng starter Spring Cloud.

Với Gradle dùng native BOM support:

```groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation "org.springframework.cloud:spring-cloud-starter-loadbalancer"

    // Chỉ thêm nếu ứng dụng dùng Eureka làm discovery provider.
    implementation "org.springframework.cloud:spring-cloud-starter-netflix-eureka-client"
}
```

Khai báo `springCloudVersion` trong phần quản lý version của build. Nếu dự án đã dùng plugin `io.spring.dependency-management` và import BOM theo cấu hình của plugin, tiếp tục theo một cơ chế quản lý dependency thống nhất của dự án.

Một số lưu ý khi chọn starter:

- `spring-cloud-starter-loadbalancer` cung cấp Spring Cloud LoadBalancer và các tích hợp liên quan.
- Discovery starter như Eureka hoặc Consul cung cấp nguồn đăng ký và tra cứu instance. Chỉ thêm provider mà kiến trúc thực sự sử dụng.
- Spring Cloud OpenFeign và LoadBalancer là hai phần tích hợp riêng. Nếu dùng OpenFeign để gọi theo service ID, hãy bảo đảm LoadBalancer có trên runtime classpath theo cấu hình của dòng Spring Cloud đang dùng.
- Không thêm trực tiếp một phiên bản tùy ý của `spring-cloud-commons` hoặc `spring-cloud-loadbalancer` để chữa lỗi tạm thời khi starter đã được quản lý bằng BOM.

## 3. Auto-configuration đánh giá điều kiện như thế nào?

Spring Boot dùng các lớp auto-configuration để đăng ký bean mặc định khi điều kiện phù hợp. Các annotation điều kiện phổ biến gồm:

| Điều kiện | Câu hỏi Spring Boot đánh giá | Ví dụ tình huống |
|---|---|---|
| `@ConditionalOnClass` | Class được chỉ định có trên classpath không? | Chỉ cấu hình tích hợp một HTTP client khi thư viện client tương ứng có mặt. |
| `@ConditionalOnMissingClass` | Class được chỉ định có vắng mặt không? | Chọn một nhánh cấu hình khi một thư viện tùy chọn chưa được cài. |
| `@ConditionalOnBean` | Application context đã có bean phù hợp chưa? | Một cấu hình mở rộng chỉ chạy khi có bean nền tảng cần thiết. |
| `@ConditionalOnMissingBean` | Bean phù hợp chưa tồn tại? | Cung cấp bean mặc định và nhường quyền cho bean do ứng dụng tự khai báo. |
| `@ConditionalOnProperty` | Property có giá trị đáp ứng điều kiện không? | Bật hoặc tắt một phần cấu hình bằng property. |
| `@ConditionalOnWebApplication` | Ứng dụng có đúng loại web application không? | Chỉ đăng ký cấu hình dành cho ứng dụng web. |

Các điều kiện có thể kết hợp. Một auto-configuration có thể yêu cầu class tồn tại, bean nền tảng đã được tạo và một property không bị tắt. Nếu một điều kiện không thỏa, Spring bỏ qua phần cấu hình đó; đây có thể là hành vi có chủ đích chứ không phải lỗi.

`@ConditionalOnMissingBean` đặc biệt quan trọng khi tùy chỉnh. Nếu ứng dụng đã tự khai báo một bean cùng loại hoặc cùng tên định danh mà cấu hình mặc định kiểm tra, Spring Boot thường lùi lại để tránh tạo bean mặc định thứ hai. Vì vậy, một mục `did not match` có thể chỉ ra ứng dụng đang dùng bean tùy chỉnh. Hãy đọc lý do cụ thể trước khi kết luận cần thêm dependency.

Đối với Spring Cloud LoadBalancer, có thể cần kiểm tra các điều kiện ở nhiều lớp: class của LoadBalancer, abstraction của discovery, bean của HTTP client và bean builder được đánh dấu `@LoadBalanced`. Có dependency nhưng thiếu bean client được đánh dấu đúng cách vẫn có thể khiến request không đi qua cơ chế chọn instance.

## 4. Xem Condition Evaluation Report khi ứng dụng khởi động

Spring Boot có thể in báo cáo điều kiện tự cấu hình khi chạy với tham số `--debug`. Báo cáo chia các cấu hình thành nhóm match và không match, kèm lý do. Đây là điểm bắt đầu tốt khi một bean mong đợi không xuất hiện.

Chạy ứng dụng với debug:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc khi chạy file JAR:

```bash
java -jar build/libs/application.jar --debug
```

Với Gradle, có thể truyền `--args='--debug'` cho task `bootRun`:

```bash
./gradlew bootRun --args='--debug'
```

Tìm các mục có tên liên quan đến LoadBalancer, discovery, RestClient, WebClient hoặc Feign trong báo cáo. Tên auto-configuration cụ thể thay đổi theo phiên bản và loại tích hợp; hãy dựa vào báo cáo thực tế của ứng dụng thay vì giả định một lớp luôn tồn tại trong mọi release train.

Một cách khác là dùng Actuator `conditions` endpoint trong môi trường phát triển:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Sau khi ứng dụng khởi động, truy cập `/actuator/conditions` để xem điều kiện match và không match. Endpoint này có thể tiết lộ tên bean, class và cấu hình nội bộ; chỉ mở trong môi trường phù hợp và bảo vệ quyền truy cập trước khi đưa vào môi trường dùng chung hoặc production.

Khi đọc báo cáo, tập trung vào ba thông tin:

- **Positive matches:** auto-configuration hoặc điều kiện nào đã được thỏa mãn.
- **Negative matches:** cấu hình nào bị bỏ qua và điều kiện nào không thỏa.
- **Exclusions:** auto-configuration nào bị loại trừ rõ ràng bằng annotation hoặc property.

Ví dụ, nếu cấu hình dành cho một client không match vì class của client không có trên classpath, hãy xác minh dependency trước. Nếu cấu hình không match vì một bean đã tồn tại, hãy kiểm tra bean đó có phải custom bean dự định dùng hay không. Nếu cấu hình bị exclude, hãy tìm nơi khai báo exclusion trước khi thêm lại dependency.

## 5. Xác minh client được gắn LoadBalancer

Mỗi HTTP client có cách tích hợp riêng. Hãy kiểm tra đúng builder hoặc client mà ứng dụng đang inject.

Với `RestClient`, ví dụ cấu hình builder được đánh dấu `@LoadBalanced`:

```java
@Configuration
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Inject đúng builder khi tạo gateway:

```java
@Service
class InventoryGateway {

    private final RestClient client;

    InventoryGateway(@LoadBalanced RestClient.Builder builder) {
        this.client = builder.build();
    }

    ProductResponse findProduct(String productId) {
        return client.get()
                .uri("http://inventory-service/api/products/{id}", productId)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

`RestClient` thuộc Spring Framework 6.1 trở lên. Vì vậy, chỉ dùng mẫu này khi dòng Spring Boot/Spring Framework và Spring Cloud của dự án hỗ trợ tích hợp `RestClient` tương ứng. Với dòng cũ chưa có `RestClient`, dùng client mà phiên bản đó hỗ trợ, chẳng hạn `RestTemplate` hoặc `WebClient`.

Với `WebClient`, builder cần được đánh dấu tương tự:

```java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
```

Với OpenFeign, khai báo service ID trên client:

```java
@FeignClient(name = "inventory-service")
interface InventoryClient {

    @GetMapping("/api/products/{id}")
    ProductResponse findProduct(@PathVariable("id") String productId);
}
```

OpenFeign cần được tích hợp với Spring Cloud LoadBalancer để phân giải tên `inventory-service` thành instance. Nếu Feign gọi một hostname cố định hoặc cấu hình URL tĩnh, request có thể bỏ qua cơ chế chọn instance theo service ID.

Khi ứng dụng có nhiều builder cùng loại, hãy inject builder có qualifier `@LoadBalanced` một cách tường minh. Tránh lấy nhầm builder thông thường vì client đó có thể không có interceptor hoặc customizer cần thiết để xử lý service ID.

## 6. Kiểm tra nguồn cung cấp ServiceInstance

LoadBalancer cần danh sách instance cho service ID. Danh sách này thường đến từ một discovery provider như Eureka hoặc Consul. Trong một ứng dụng nhỏ hoặc khi kiểm tra cục bộ, có thể dùng `SimpleDiscoveryClient` với danh sách instance tĩnh.

Ví dụ cấu hình instance tĩnh:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Hai URI trên là các instance minh họa của cùng service ID `inventory-service`. Khi gọi `http://inventory-service/...` bằng client đã tích hợp LoadBalancer, danh sách này là đầu vào để chọn instance. Trong môi trường thực, discovery provider sẽ cập nhật danh sách theo trạng thái đăng ký dịch vụ.

Nếu không tìm thấy instance, hãy xác minh service ID giữa caller và registry có trùng khớp, discovery client có được kích hoạt và các instance đã đăng ký hay chưa. Cũng cần phân biệt trường hợp không có provider với trường hợp provider đã hoạt động nhưng trả về danh sách rỗng.

## 7. Phát hiện dependency conflict bằng công cụ build

Một lỗi thường gặp là starter được khai báo đúng nhưng dependency resolution lại chọn các phiên bản không tương thích do một thư viện khác kéo phiên bản bắc cầu hoặc do dự án pin phiên bản thủ công.

Với Maven, xem cây dependency:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework.cloud,org.springframework.boot
```

Để xem POM hiệu lực và các dependency management rule:

```bash
./mvnw help:effective-pom
```

Với Gradle, xem runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để tìm lý do một dependency được chọn:

```bash
./gradlew dependencyInsight \
  --dependency spring-cloud-loadbalancer \
  --configuration runtimeClasspath
```

Đọc kết quả để tìm:

- Nhiều phiên bản khác nhau của cùng artifact Spring Cloud.
- Module bị thay thế hoặc bị ép phiên bản bởi resolution rule.
- Dependency bị exclude khỏi starter hoặc bị đánh dấu sai scope/configuration.
- Thư viện Spring Boot hoặc Spring Framework được nâng riêng lẻ ngoài dependency management.
- Starter tích hợp (Feign, discovery, client HTTP) không có trên `runtimeClasspath` dù có trong cấu hình build ở một scope khác.

Không kết luận chỉ dựa vào việc một dependency xuất hiện trong file build. Runtime classpath mới cho biết artifact nào thực sự được chọn khi chạy ứng dụng.

## 8. Nhận diện lỗi qua dấu hiệu cụ thể

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu artifact hoặc dependency bị exclude; cũng có thể có khác biệt classpath giữa compile và runtime. | Kiểm tra dependency tree và runtime classpath. |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Các module được biên dịch với API khác phiên bản đang có lúc chạy. | So sánh phiên bản Boot, Framework và toàn bộ module Spring Cloud được resolve. |
| `NoSuchBeanDefinitionException` khi inject builder/client | Auto-configuration không tạo bean, thiếu starter hoặc bean bị điều kiện loại bỏ. | Xem Condition Evaluation Report và danh sách bean phù hợp. |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng loại và injection không xác định được bean cần dùng. | Kiểm tra qualifier, `@Primary` và các bean do ứng dụng tự khai báo. |
| `BeanDefinitionOverrideException` | Hai cấu hình đăng ký bean trùng tên trong khi override không được cho phép. | Tìm các cấu hình khai báo bean và kiểm tra việc import cấu hình lặp. |
| Request báo không tìm thấy instance | Discovery provider chưa có dữ liệu, service ID sai hoặc danh sách instance rỗng. | Kiểm tra registry, cấu hình discovery và service ID. |
| Request đi thẳng đến hostname cố định | Client đang dùng URL tĩnh hoặc builder không được tích hợp LoadBalancer. | Kiểm tra URL và qualifier của client/builder đang inject. |

Thông báo lỗi chỉ là manh mối. Ví dụ, `NoSuchBeanDefinitionException` có thể do thiếu starter, nhưng cũng có thể do điều kiện property không thỏa hoặc cấu hình đã bị exclude. Hãy đọc phần `Caused by` và Condition Evaluation Report để xác định nguyên nhân gần nhất.

## 9. Quy trình xử lý khi auto-configuration không xuất hiện

Thực hiện lần lượt để thu hẹp nguyên nhân:

1. Xác nhận dự án đang dùng phiên bản Spring Boot nào và chọn Spring Cloud release train tương thích.
2. Kiểm tra `spring-cloud-starter-loadbalancer` có trên runtime classpath và không bị exclude.
3. Nếu dùng Eureka, Consul hoặc provider khác, kiểm tra đúng discovery starter và cấu hình kết nối registry.
4. Khởi động với `--debug` hoặc xem `/actuator/conditions`, tìm điều kiện không match liên quan đến client và LoadBalancer.
5. Kiểm tra builder/client đang inject có qualifier `@LoadBalanced` hoặc khai báo service ID đúng cách hay không.
6. Xác minh service ID có danh sách instance và các URI instance có thể truy cập.
7. Sau khi sửa dependency hoặc cấu hình, khởi động lại ứng dụng và kiểm tra lại báo cáo điều kiện cùng request thực tế.

Không nên thêm nhiều starter hoặc bật bean override chỉ để làm ứng dụng khởi động. Những thay đổi đó có thể che nguyên nhân gốc và tạo thêm xung đột trong application context.

## 10. Ví dụ kiểm tra cấu hình tối thiểu

Giả sử ứng dụng chỉ cần gọi hai instance cục bộ của `inventory-service`. Có thể dùng starter LoadBalancer, cấu hình `SimpleDiscoveryClient` và một builder được đánh dấu `@LoadBalanced`.

Dependency Maven tối thiểu cho phần LoadBalancer:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Cấu hình hai instance:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Khai báo builder và gateway:

```java
@Configuration
class LoadBalancedClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder restClientBuilder() {
        return RestClient.builder();
    }
}

@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    ProductResponse getProduct(String id) {
        return restClient.get()
                .uri("http://inventory-service/api/products/{id}", id)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

Ví dụ này yêu cầu dòng Spring Boot/Spring Cloud có hỗ trợ tích hợp `RestClient`. Nếu dự án dùng dòng cũ, thay bằng client được hỗ trợ trong phiên bản đó và giữ nguyên nguyên tắc kiểm tra dependency, điều kiện auto-configuration, qualifier và danh sách instance.

Khi xác minh, cần thấy ứng dụng khởi động không có lỗi tạo bean, báo cáo điều kiện cho thấy cấu hình liên quan đã match, và request dùng service ID có thể được gửi đến một instance trong danh sách. Việc một request thành công chỉ xác minh đường gọi tại thời điểm đó; nó chưa chứng minh mọi instance đều khỏe hoặc mọi chính sách retry/timeout đã được cấu hình đúng.

## 11. Checklist trước khi kết luận cấu hình đã đúng

- [ ] Spring Boot và Spring Cloud release train nằm trong ma trận tương thích.
- [ ] `spring-cloud-starter-loadbalancer` có mặt trên runtime classpath.
- [ ] Discovery starter hoặc nguồn instance tĩnh được cấu hình đúng với kiến trúc.
- [ ] Condition Evaluation Report không cho thấy điều kiện bắt buộc bị thiếu ngoài dự kiến.
- [ ] Client/builder dùng để gọi service ID được tích hợp LoadBalancer.
- [ ] Service ID khớp với tên dịch vụ trong nguồn discovery và có ít nhất một instance hợp lệ.
- [ ] Dependency tree không có các phiên bản Spring Boot/Spring Framework/Spring Cloud xung đột.
- [ ] Endpoint chẩn đoán Actuator, nếu bật, được giới hạn và bảo vệ phù hợp với môi trường.

Khi các điều kiện trên được xác minh, nhóm phát triển có thể phân biệt rõ lỗi do dependency, auto-configuration, discovery hay do request của ứng dụng. Điều đó giúp việc thiết lập Spring Cloud LoadBalancer có thể lặp lại và dễ bảo trì khi nâng cấp phiên bản.
