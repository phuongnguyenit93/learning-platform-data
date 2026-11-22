# Điều kiện bật tắt khả năng theo classpath và cấu hình

## 1. Vì sao một capability có thể tự xuất hiện?

Spring Cloud được chia thành nhiều module và starter. Một ứng dụng có thể chỉ cần cấu hình tập trung, ứng dụng khác cần service discovery, load balancing, circuit breaker hoặc refresh scope. Nếu mọi capability đều luôn được tạo ra, ứng dụng sẽ mang theo dependency, bean và tác vụ nền mà nó không cần.

Spring Boot và Spring Cloud giải quyết việc này bằng auto-configuration có điều kiện. Khi ứng dụng khởi động, framework đánh giá những gì có trong classpath, các bean đã tồn tại và các thuộc tính trong Environment. Chỉ cấu hình thỏa điều kiện mới được áp dụng.

Một capability thường được quyết định bởi ba nhóm điều kiện:

1. **Classpath:** thư viện hoặc API cần thiết có trong runtime classpath hay không.
2. **ApplicationContext:** bean phụ thuộc đã tồn tại chưa, hoặc ứng dụng đã cung cấp bean thay thế chưa.
3. **Configuration:** property switch có cho phép capability hoạt động không.

Ví dụ, thêm Spring Cloud LoadBalancer starter giúp các lớp LoadBalancer có mặt trên classpath. Nhưng nếu đặt `spring.cloud.loadbalancer.enabled=false`, auto-configuration của LoadBalancer sẽ không được kích hoạt. Ngược lại, đặt thuộc tính thành `true` không thể tạo ra một thư viện chưa có trong dependency.

## 2. Auto-configuration đánh giá điều kiện như thế nào?

Một starter thường đưa vào ứng dụng các dependency cần thiết và module auto-configuration. Spring Boot tìm các lớp auto-configuration đã được đăng ký trong JAR, sau đó đánh giá những điều kiện khai báo trên lớp cấu hình và từng bean.

Trong Spring Boot hiện hành, auto-configuration được liệt kê trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là tên đầy đủ của một lớp auto-configuration. Các điều kiện trên lớp hoặc phương thức @Bean quyết định cấu hình đó có được áp dụng hay không.

### 2.1. Điều kiện theo classpath

`@ConditionalOnClass` chỉ cho phép cấu hình hoạt động khi một lớp có mặt trên classpath. `@ConditionalOnMissingClass` làm điều ngược lại: cấu hình chỉ hoạt động khi lớp được chỉ định không có mặt.

Ví dụ, một integration chỉ cần tạo bean khi thư viện client tùy chọn đã được thêm:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.vendor.InventoryClient")
class InventoryClientConfiguration {
    // Các bean phụ thuộc InventoryClient
}
```

Dùng thuộc tính `name` hữu ích khi lớp được kiểm tra thuộc một dependency tùy chọn và module auto-configuration không nên phụ thuộc trực tiếp vào nó ở thời điểm biên dịch.

Không nên đặt kiểu tùy chọn vào chữ ký phương thức @Bean ở một cấu hình luôn được nạp. JVM có thể phải nạp kiểu đó trước khi điều kiện của phương thức được đánh giá. Hãy cô lập phần phụ thuộc tùy chọn trong một cấu hình lồng hoặc lớp cấu hình riêng có `@ConditionalOnClass`.

### 2.2. Điều kiện theo bean trong ApplicationContext

Hai điều kiện thường dùng:

- `@ConditionalOnBean`: tạo cấu hình hoặc bean khi bean phụ thuộc đã tồn tại.
- `@ConditionalOnMissingBean`: chỉ tạo bean mặc định nếu ứng dụng chưa cung cấp bean tương ứng.

`@ConditionalOnMissingBean` là cơ chế cho phép ứng dụng thay thế mặc định của starter. Nó không gỡ thư viện khỏi classpath và cũng không có nghĩa toàn bộ capability bị tắt.

Ví dụ:

```java
@Bean
@ConditionalOnMissingBean(InventoryGateway.class)
InventoryGateway inventoryGateway(InventoryClient client) {
    return new InventoryGateway(client);
}
```

Nếu ứng dụng đã khai báo `InventoryGateway` của riêng mình, bean mặc định không được tạo. Những bean khác trong cùng auto-configuration vẫn có thể được tạo nếu các điều kiện riêng của chúng thỏa mãn.

### 2.3. Điều kiện theo property

`@ConditionalOnProperty` cho phép cấu hình được áp dụng theo một property trong Spring Environment:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.inventory",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
class InventoryFeatureConfiguration {
    // Các bean của capability inventory
}
```

Với ví dụ này, capability chỉ được bật khi `acme.inventory.enabled=true`. Nếu không khai báo property hoặc đặt `false`, cấu hình không được áp dụng.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `prefix` | Tiền tố chung của property |
| `name` | Tên property cần kiểm tra |
| `havingValue` | Giá trị cần khớp |
| `matchIfMissing` | Có cho phép khớp khi property không tồn tại hay không; mặc định là false |

Nếu bỏ `havingValue`, property tồn tại và không có giá trị `false` thường được xem là khớp. Với cờ bật/tắt, nên ghi rõ `havingValue = "true"` để người đọc hiểu chính xác điều kiện.

### 2.4. Kết hợp nhiều điều kiện

Một capability có thể cần đồng thời thư viện, bean nền tảng và property bật:

```java
@AutoConfiguration
class InventoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(InventoryClient.class)
    @ConditionalOnProperty(
            prefix = "acme.inventory",
            name = "enabled",
            havingValue = "true"
    )
    static class InventoryConfiguration {

        @Bean
        @ConditionalOnBean(InventoryClient.class)
        @ConditionalOnMissingBean
        InventoryGateway inventoryGateway(InventoryClient client) {
            return new InventoryGateway(client);
        }
    }
}
```

Trong ví dụ, cấu hình lồng chỉ được xét khi `InventoryClient` có trên classpath và property bật. Bean gateway chỉ được tạo khi có bean `InventoryClient`, đồng thời chưa có `InventoryGateway` do ứng dụng cung cấp.

Các điều kiện kết hợp theo logic AND. Nếu một điều kiện không khớp, phần cấu hình chịu điều kiện đó sẽ không được áp dụng.

## 3. Classpath và property là hai cổng độc lập

Không nên nhầm việc thêm dependency với việc bật capability:

| Classpath | Property | Kết quả điển hình |
| --- | --- | --- |
| Thiếu thư viện | true | Không có implementation để auto-configure; property không tự tải dependency |
| Có thư viện | false | Auto-configuration bị tắt theo property |
| Có thư viện | true | Capability có thể được cấu hình nếu các điều kiện bean/context khác cũng thỏa mãn |
| Có thư viện | Không khai báo | Phụ thuộc matchIfMissing và giá trị mặc định của property |

Một starter có thể kéo theo dependency bắc cầu. Do đó, capability đôi khi xuất hiện dù nhóm phát triển không khai báo trực tiếp module đó. Khi điều tra, cần kiểm tra dependency tree chứ không chỉ tìm dòng dependency trong file build.

Các lệnh sau giúp kiểm tra dependency trong dự án:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies
```

Các lệnh trên chỉ liệt kê dependency. Việc có JAR trong classpath vẫn chưa chứng minh bean đã được tạo; phải kiểm tra điều kiện auto-configuration và ApplicationContext.

## 4. Những công tắc capability trong Spring Cloud Commons

Spring Cloud Commons cung cấp nhiều property switch. Các công tắc này có phạm vi khác nhau; tắt một phần không đồng nghĩa tắt toàn bộ chức năng liên quan.

### 4.1. Service discovery

Provider như Eureka, Consul hoặc ZooKeeper cần dependency tương ứng để cung cấp `DiscoveryClient`. Khi implementation có trên classpath, Spring Cloud có thể auto-configure discovery client.

Commons hiện không yêu cầu thêm `@EnableDiscoveryClient` chỉ để kích hoạt discovery. Sự hiện diện của implementation trên classpath thường đã đủ để auto-configuration hoạt động.

Các công tắc chính:

| Property | Phạm vi |
| --- | --- |
| `spring.cloud.discovery.enabled=false` | Tắt capability service discovery theo điều kiện chung |
| `spring.cloud.discovery.blocking.enabled=false` | Tắt blocking DiscoveryClient |
| `spring.cloud.discovery.reactive.enabled=false` | Tắt reactive DiscoveryClient |

Nếu chỉ dùng một kiểu lập trình, có thể tắt kiểu còn lại. Nếu ứng dụng không dùng discovery, dùng công tắc chung. Hãy kiểm tra property và phiên bản Spring Cloud đang triển khai khi có nhiều discovery provider cùng xuất hiện trên classpath.

### 4.2. Tắt auto-registration nhưng vẫn giữ discovery

Tra cứu instance và đăng ký chính ứng dụng là hai hành vi riêng.

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

`spring.cloud.service-registry.auto-registration.enabled=false` ngăn Spring Cloud tự đăng ký local application instance. Nó không phải công tắc tắt `DiscoveryClient`; ứng dụng vẫn có thể tra cứu service khác nếu discovery client còn được bật.

Điều này hữu ích cho ứng dụng chỉ đóng vai trò consumer, tác vụ batch, công cụ quản trị hoặc trường hợp quy trình triển khai muốn đăng ký service bằng một bước riêng. Khi auto-registration bị tắt, các sự kiện `InstancePreRegisteredEvent` và `InstanceRegisteredEvent` cũng không được phát theo luồng auto-registration.

### 4.3. Health indicator của discovery

DiscoveryClient có thể cung cấp health indicator cho Spring Boot Actuator. Nếu chỉ muốn bỏ health indicator, không cần tắt discovery:

```yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: false
        composite-indicator:
          enabled: false
```

Các property liên quan:

| Property | Tác dụng |
| --- | --- |
| `spring.cloud.discovery.client.health-indicator.enabled=false` | Tắt DiscoveryClientHealthIndicator |
| `spring.cloud.discovery.client.composite-indicator.enabled=false` | Tắt composite indicator tổng hợp các DiscoveryHealthIndicator |
| `spring.cloud.discovery.client.health-indicator.include-description=false` | Không đưa description vào health result |
| `spring.cloud.discovery.client.health-indicator.use-services-query=false` | Dùng `probe()` thay cho truy vấn toàn bộ `getServices()` khi implementation hỗ trợ |

Property `use-services-query=false` chỉ thay cách kiểm tra health, không tắt indicator. Nó hữu ích khi registry có catalog rất lớn và việc lấy toàn bộ service list ở mỗi lần health check gây tốn kém.

### 4.4. Spring Cloud LoadBalancer

LoadBalancer là capability riêng với DiscoveryClient. Nó cần Spring Cloud LoadBalancer trên classpath và có thể lấy instance từ một DiscoveryClient.

```yaml
spring:
  cloud:
    loadbalancer:
      enabled: true
      cache:
        enabled: true
      retry:
        enabled: false
```

Các công tắc có phạm vi khác nhau:

| Property | Tác dụng |
| --- | --- |
| `spring.cloud.loadbalancer.enabled=false` | Tắt auto-configuration của Spring Cloud LoadBalancer |
| `spring.cloud.loadbalancer.cache.enabled=false` | Tắt cache danh sách instance của LoadBalancer |
| `spring.cloud.loadbalancer.retry.enabled=false` | Tắt retry của LoadBalancer |

Tắt cache không tắt discovery hoặc LoadBalancer. Tắt retry cũng không làm mất khả năng chọn instance. Nếu DiscoveryClient đã có cache riêng, cần xem xét có nên bật thêm cache của LoadBalancer để tránh hai lớp cache chồng lên nhau.

### 4.5. Refresh scope

Spring Cloud Context cung cấp refresh scope và các chức năng liên quan. Có thể tắt auto-configuration của nhóm tính năng này:

```yaml
spring:
  cloud:
    refresh:
      enabled: false
```

`spring.cloud.refresh.enabled=false` phù hợp với ứng dụng không dùng refresh scope hoặc môi trường Spring AOT/native image, nơi tài liệu Spring Cloud yêu cầu tắt context refresh. Việc tắt refresh scope không đồng nghĩa tắt toàn bộ khả năng nạp cấu hình bên ngoài của Spring Boot hoặc Config Client.

### 4.6. Features endpoint

Spring Cloud Commons cung cấp endpoint `/features` để liệt kê feature có trên classpath và trạng thái nhận diện của chúng. Với Actuator dùng base path mặc định, endpoint thường được gọi là `/actuator/features`.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features

spring:
  cloud:
    features:
      enabled: true
```

`spring.cloud.features.enabled=false` tắt endpoint features. Nó không tắt các capability được liệt kê. Endpoint dùng để quan sát feature, không phải công tắc bật tất cả feature.

Feature có thể là:

- **Abstract feature:** interface hoặc abstract class có implementation bean, ví dụ `DiscoveryClient` hoặc `LoadBalancerClient`.
- **Named feature:** capability được công bố bằng tên và kiểu bean đại diện, ví dụ một module Spring Cloud khác.

Một feature được liệt kê không chứng minh mọi thao tác nghiệp vụ của nó đang hoạt động. Nó cho biết feature được nhận diện trong ứng dụng; cần kiểm tra health, kết nối và hành vi thực tế riêng.

### 4.7. Compatibility verifier

Spring Cloud Commons có compatibility verifier để kiểm tra phiên bản Spring Boot trên classpath có nằm trong nhóm phiên bản tương thích của release train hay không.

Verifier này mặc định không bật trong cấu hình hiện hành. Đặt `spring.cloud.compatibility-verifier.enabled=true` để bật:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Nếu cần tùy chỉnh tập phiên bản Boot được chấp nhận, có property `spring.cloud.compatibility-verifier.compatible-boot-versions`. Chỉ nên thay danh sách này khi đã xác minh ma trận tương thích của release train. Tắt verifier để bỏ qua lỗi khởi động không làm cho hai phiên bản vốn không tương thích trở nên tương thích.

## 5. Ví dụ chọn capability theo môi trường

Giả sử một service production cần discovery để tìm các dependency, nhưng quy trình triển khai đăng ký service bằng một bước riêng. Ứng dụng dùng blocking client, không cần reactive discovery, vẫn dùng LoadBalancer và tắt discovery health indicator do đã có health check vận hành riêng.

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: false
      client:
        health-indicator:
          enabled: false
    service-registry:
      auto-registration:
        enabled: false
    loadbalancer:
      enabled: true
      cache:
        enabled: true
      retry:
        enabled: false
```

Đọc cấu hình này theo từng phạm vi:

1. Discovery vẫn hoạt động qua blocking client.
2. Reactive discovery bị tắt.
3. Ứng dụng không tự đăng ký vào registry.
4. LoadBalancer vẫn được phép chọn instance.
5. Health indicator của discovery bị tắt; các health indicator khác không bị ảnh hưởng.

Trong môi trường test không cần gọi service qua registry, có thể ghi đè:

```yaml
spring:
  cloud:
    discovery:
      enabled: false
    loadbalancer:
      enabled: false
```

Các profile có thể dùng chung dependency nhưng đặt property khác nhau. Khi một giá trị đến từ biến môi trường, tham số dòng lệnh hoặc Config Server, cần kiểm tra giá trị cuối cùng trong Spring Environment thay vì chỉ đọc file application.yml.

## 6. Ví dụ xây capability tùy chọn trong starter riêng

Các nguyên tắc trên cũng áp dụng khi nhóm phát triển tạo một starter nội bộ.

Giả sử starter tích hợp với thư viện `InventoryClient`. Capability chỉ nên xuất hiện khi:

- Dependency cung cấp InventoryClient có trên classpath.
- Người dùng đặt `acme.inventory.enabled=true`.
- Có bean InventoryClient để gateway sử dụng.
- Ứng dụng chưa tự cung cấp InventoryGateway.

```java
@AutoConfiguration
public class InventoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(InventoryClient.class)
    @ConditionalOnProperty(
            prefix = "acme.inventory",
            name = "enabled",
            havingValue = "true"
    )
    static class InventoryConfiguration {

        @Bean
        @ConditionalOnBean(InventoryClient.class)
        @ConditionalOnMissingBean(InventoryGateway.class)
        InventoryGateway inventoryGateway(InventoryClient client) {
            return new InventoryGateway(client);
        }
    }
}
```

Ví dụ này tách điều kiện lớp khỏi điều kiện bean. Cấu hình lồng giúp lớp tùy chọn không bị nạp khi dependency vắng mặt. Bean gateway chỉ xuất hiện khi có client và không bị ứng dụng thay thế.

Khi đóng gói starter:

1. Đưa lớp auto-configuration vào module cấu hình tự động.
2. Đăng ký lớp trong `AutoConfiguration.imports`.
3. Để dependency tùy chọn ở dạng optional nếu starter không phải lúc nào cũng cần thư viện đó.
4. Dùng namespace riêng cho property của starter, chẳng hạn `acme.inventory`.
5. Ghi rõ giá trị mặc định, `matchIfMissing` và điều kiện classpath trong tài liệu.

## 7. Kiểm tra tại sao capability được bật hoặc bị tắt

Khi một bean không xuất hiện, không nên thêm dependency hoặc đổi property theo phỏng đoán. Hãy xác định điều kiện nào không khớp.

### 7.1. Kiểm tra dependency tree

Xác nhận starter và dependency bắc cầu có trong runtime classpath. Với Maven dùng `mvn dependency:tree`; với Gradle dùng `./gradlew dependencies`. Nếu thư viện bị loại trừ bằng exclusion hoặc scope không đưa vào runtime, `@ConditionalOnClass` có thể không khớp.

### 7.2. Kiểm tra Condition Evaluation Report

Spring Boot tạo condition evaluation report trong quá trình auto-configuration. Report cho biết:

- Cấu hình nào khớp.
- Cấu hình nào không khớp.
- Điều kiện classpath hoặc property nào bị thiếu.
- Bean nào đã tồn tại khiến `@ConditionalOnMissingBean` không tạo bean mặc định.

Có thể xem report qua Actuator endpoint `conditions` nếu endpoint được expose và bảo vệ phù hợp, hoặc bật log debug khi khởi động để in báo cáo điều kiện.

### 7.3. Kiểm tra Features và Beans

Nếu Actuator được bật:

- `/actuator/features` cho biết các feature Spring Cloud đã được nhận diện.
- `/actuator/beans` cho biết bean nào thực sự tồn tại trong ApplicationContext.
- `/actuator/conditions` cho biết điều kiện auto-configuration khớp hoặc không khớp.
- `/actuator/configprops` cho biết các ConfigurationProperties đã được bind.

Các endpoint cần được expose rõ ràng và bảo vệ bằng authentication/authorization. Một feature không xuất hiện trong `/features` có thể do feature không có trên classpath, không có bean đại diện hoặc endpoint bị tắt; hãy đối chiếu thêm condition report.

## 8. Kiểm thử điều kiện auto-configuration

`ApplicationContextRunner` cho phép kiểm tra từng tổ hợp classpath, property và bean mà không cần khởi động toàn bộ ứng dụng.

Ví dụ kiểm thử capability chỉ bật khi property đúng:

```java
class InventoryAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(InventoryAutoConfiguration.class)
                    );

    @Test
    void backsOffWhenFeatureIsDisabled() {
        contextRunner
                .withPropertyValues("acme.inventory.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(InventoryGateway.class));
    }

    @Test
    void createsGatewayWhenFeatureIsEnabledAndClientExists() {
        contextRunner
                .withPropertyValues("acme.inventory.enabled=true")
                .withBean(InventoryClient.class, FakeInventoryClient::new)
                .run(context -> assertThat(context)
                        .hasSingleBean(InventoryGateway.class));
    }
}
```

Có thể bổ sung kiểm thử classpath bằng `FilteredClassLoader`:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(InventoryClient.class))
        .withPropertyValues("acme.inventory.enabled=true")
        .run(context -> assertThat(context)
                .doesNotHaveBean(InventoryGateway.class));
```

Nên kiểm thử ít nhất các trường hợp:

| Classpath | Property | Bean phụ thuộc | Kết quả mong đợi |
| --- | --- | --- | --- |
| Có | true | Có | Capability được tạo |
| Có | false | Có | Capability không được tạo |
| Có | Không khai báo | Có | Theo matchIfMissing |
| Không có | true | Không thể có | Auto-configuration tùy chọn không được áp dụng |
| Có | true | Không có | Bean phụ thuộc không được tạo |
| Có | true | Có bean tùy chỉnh | Bean mặc định back off |

Kiểm thử các tổ hợp này giúp tránh tình trạng starter hoạt động trong ứng dụng mẫu nhưng thất bại khi được thêm vào ứng dụng đã có bean tùy chỉnh hoặc thiếu một dependency bắc cầu.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Property bật nhưng bean không xuất hiện | Dependency không có trên runtime classpath | Xem dependency tree và condition report |
| Starter có trong build nhưng capability bị tắt | Property switch đang là false hoặc profile ghi đè | Xem giá trị cuối cùng trong Environment và configprops |
| Discovery vẫn chạy sau khi tắt auto-registration | Chỉ tắt đăng ký local, DiscoveryClient vẫn hoạt động | Kiểm tra service-registry.auto-registration.enabled và discovery.enabled |
| Tắt health indicator nhưng request vẫn tra cứu service được | Chỉ health indicator bị tắt | Kiểm tra health-indicator.enabled |
| Tắt LoadBalancer nhưng DiscoveryClient vẫn tồn tại | Hai capability có công tắc riêng | Kiểm tra loadbalancer.enabled và discovery switch |
| Bean mặc định không được tạo | Ứng dụng đã khai báo bean cùng kiểu | Xem danh sách bean và điều kiện ConditionalOnMissingBean |
| Capability xuất hiện ngoài dự kiến | Starter khác kéo dependency bắc cầu hoặc profile bật property | Kiểm tra dependency tree, profile và Environment |
| Ứng dụng không khởi động do compatibility verifier | Spring Boot không nằm trong tập phiên bản được chấp nhận | Kiểm tra ma trận release train/BOM trước khi đổi property verifier |
| /actuator/features trả 404 | Actuator chưa có, endpoint chưa expose hoặc features endpoint bị tắt | Kiểm tra dependency Actuator, exposure và spring.cloud.features.enabled |

## 10. Nguyên tắc thiết kế capability

1. Chỉ đưa dependency cần thiết vào starter mặc định; dependency tùy chọn nên được tách rõ.
2. Dùng `@ConditionalOnClass` để cô lập API bên ngoài và tránh lỗi khi dependency vắng mặt.
3. Dùng `@ConditionalOnBean` khi capability cần một bean hạ tầng đã được cấu hình.
4. Dùng `@ConditionalOnMissingBean` để cho phép ứng dụng thay thế implementation mặc định.
5. Dùng `@ConditionalOnProperty` với namespace riêng và quy định rõ giá trị mặc định.
6. Tách công tắc cho các hành vi khác nhau; không dùng một property để đồng thời tắt discovery, registration, health và load balancing.
7. Kiểm tra điều kiện auto-configuration bằng `ApplicationContextRunner`.
8. Dùng condition report, beans và features endpoint để chẩn đoán.
9. Giữ Spring Cloud BOM và Spring Boot ở cặp phiên bản tương thích; không tắt compatibility verifier chỉ để che lỗi dependency.
10. Bảo vệ các actuator endpoint có thể tiết lộ thông tin nội bộ.

## 11. Tài liệu tham khảo

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): auto-configuration imports, class/bean/property conditions và ApplicationContextRunner.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): điều kiện bật discovery, blocking/reactive client, health indicator, auto-registration, /features và compatibility verifier.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): giá trị mặc định và mô tả các property switch.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): điều kiện classpath, công tắc LoadBalancer và cache.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): công tắc refresh scope và giới hạn theo môi trường chạy.

Classpath quyết định thư viện và implementation nào có thể được dùng; điều kiện bean quyết định các thành phần nào có thể được ghép lại; property switch quyết định người triển khai có muốn bật capability đó hay không. Khi tách ba lớp này, việc thêm starter, thay implementation hoặc tắt một chức năng sẽ dễ dự đoán và kiểm thử hơn.
