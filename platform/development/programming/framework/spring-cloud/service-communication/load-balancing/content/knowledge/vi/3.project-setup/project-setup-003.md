# Các starter cho LoadBalancer và từng HTTP client

Để một ứng dụng Spring Cloud gọi dịch vụ theo service ID và phân phối request đến các instance, cần ghép đúng các dependency ở ba lớp: **HTTP client**, **Spring Cloud LoadBalancer** và **nguồn khám phá dịch vụ**. Mỗi HTTP client có starter riêng; LoadBalancer cung cấp cơ chế chọn instance dùng chung; discovery cung cấp danh sách instance đang tồn tại.

Ví dụ, `order-service` muốn gọi `catalog-service`. Ứng dụng có thể dùng `RestClient`, `WebClient` hoặc OpenFeign, nhưng cả ba đều cần một cơ chế phân giải tên `catalog-service` thành một instance cụ thể. Việc khai báo dependency đúng giúp Spring Boot tạo HTTP client và Spring Cloud kết nối client đó với LoadBalancer.

## 1. Ba nhóm dependency cần phân biệt

### Starter của HTTP client

Starter HTTP client cung cấp API dùng để gửi request:

| Cách gọi | Starter thường dùng | Thành phần chính |
|---|---|---|
| `RestClient` | `spring-boot-starter-web` | Spring MVC và các HTTP API đồng bộ; `RestClient` có từ Spring Framework 6.1 |
| `WebClient` | `spring-boot-starter-webflux` | HTTP client reactive `WebClient` |
| OpenFeign | `spring-cloud-starter-openfeign` | Khai báo HTTP client qua interface và annotation |

`RestClient` và `WebClient` là API của Spring Framework. OpenFeign là integration của Spring Cloud giúp tạo client từ interface. Việc có một trong các starter trên chỉ cung cấp khả năng gọi HTTP; nó chưa tự tạo danh sách instance cho service ID.

### Starter của Spring Cloud LoadBalancer

Dependency dùng chung là:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Starter này đưa Spring Cloud LoadBalancer và các thành phần tích hợp cần thiết vào ứng dụng. Nó cung cấp cơ chế chọn `ServiceInstance`, chẳng hạn round-robin, và các abstraction như `ServiceInstanceListSupplier`. Với `RestClient` và `WebClient`, ứng dụng thường đánh dấu builder bằng `@LoadBalanced`. Với OpenFeign, integration LoadBalancer được tự động sử dụng khi dependency tương ứng có mặt.

### Starter của service discovery

LoadBalancer cần một nguồn instance. Trong hệ thống dùng registry, thêm starter của đúng nền tảng discovery đang triển khai. Ví dụ:

| Nền tảng registry | Starter discovery |
|---|---|
| Eureka | `spring-cloud-starter-netflix-eureka-client` |
| Consul | `spring-cloud-starter-consul-discovery` |

Chỉ chọn starter tương ứng với hạ tầng thực tế. Ứng dụng không cần thêm cả Eureka và Consul nếu chỉ dùng một registry. Nếu không dùng registry, có thể cung cấp instance tĩnh qua `SimpleDiscoveryClient` hoặc một `ServiceInstanceListSupplier` do ứng dụng cấu hình.

## 2. Quản lý phiên bản Spring Boot và Spring Cloud

Các starter Spring Cloud cần cùng một release train tương thích với phiên bản Spring Boot của dự án. Nên import BOM `spring-cloud-dependencies` để Maven hoặc Gradle quản lý phiên bản nhất quán; không tự gắn những version khác nhau cho từng starter.

Ví dụ Maven, thay `SET_COMPATIBLE_RELEASE_TRAIN` bằng release train tương thích với phiên bản Spring Boot đang sử dụng:

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>SET_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
```

Sau khi import BOM, khai báo dependency mà không cần chỉ định `<version>` cho từng starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
```

Với Gradle Groovy DSL, có thể import cùng BOM bằng `platform`:

```groovy
ext {
    springCloudVersion = 'SET_COMPATIBLE_RELEASE_TRAIN'
}

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
```

Tra bảng tương thích chính thức giữa Spring Boot và Spring Cloud trước khi chọn release train. Nếu nâng Spring Boot, hãy kiểm tra lại release train tương ứng và nâng các dependency Spring Cloud cùng nhau.

## 3. Dependency cho từng HTTP client

### Dùng RestClient

`RestClient` phù hợp với lời gọi HTTP đồng bộ. Với Spring Boot 3.2 trở lên (dùng Spring Framework 6.1 trở lên), có thể khai báo:

```xml
<dependencies>
    <!-- Cung cấp Spring MVC và RestClient -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Chọn instance theo service ID -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Chỉ thêm nếu ứng dụng đăng ký/tìm dịch vụ qua Eureka -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Nếu hệ thống dùng Consul, thay dependency Eureka bằng `spring-cloud-starter-consul-discovery`. Nếu đã có một discovery provider khác trong dự án, tiếp tục dùng provider đó và không thêm một registry thứ hai chỉ để kích hoạt LoadBalancer.

Khai báo builder được đánh dấu `@LoadBalanced`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Sau đó inject builder vào client và dùng service ID trong URL:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogRestClient {

    private final RestClient client;

    CatalogRestClient(
            @Qualifier("loadBalancedRestClientBuilder") RestClient.Builder builder) {
        this.client = builder.build();
    }

    ProductResponse getProduct(String productId) {
        return client.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

`catalog-service` phải khớp với tên dịch vụ được đăng ký hoặc service ID mà nguồn discovery cung cấp. Khi dự án có nhiều `RestClient.Builder`, đặt tên bean và dùng `@Qualifier` để inject đúng builder load-balanced.

### Dùng WebClient

`WebClient` cung cấp API reactive và non-blocking. Starter tương ứng là `spring-boot-starter-webflux`; thêm LoadBalancer và discovery provider giống cách dùng `RestClient`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Khai báo builder:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Sử dụng builder để tạo client:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
class CatalogWebClient {

    private final WebClient webClient;

    CatalogWebClient(
            @Qualifier("loadBalancedWebClientBuilder") WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<ProductResponse> getProduct(String productId) {
        return webClient.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .bodyToMono(ProductResponse.class);
    }
}
```

`spring-boot-starter-webflux` có thể được dùng chỉ để tạo HTTP client `WebClient`; ứng dụng không bắt buộc phải chạy WebFlux server. Nếu dự án đồng thời có `spring-boot-starter-web`, Spring Boot thường chọn ứng dụng kiểu Servlet khi khởi động, trong khi `WebClient` vẫn có thể được inject và sử dụng như HTTP client.

### Dùng Spring Cloud OpenFeign

OpenFeign cho phép khai báo lời gọi HTTP qua interface. Starter chính là `spring-cloud-starter-openfeign`; hãy khai báo thêm `spring-cloud-starter-loadbalancer` để bật tích hợp cân bằng tải một cách rõ ràng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-openfeign</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Spring Cloud OpenFeign có thể khai báo LoadBalancer như dependency tùy chọn. Vì vậy, không nên chỉ dựa vào việc thêm OpenFeign starter để kết luận LoadBalancer đã có trên classpath. Kiểm tra dependency tree và khai báo starter LoadBalancer khi ứng dụng cần cân bằng tải theo service ID.

Bật quét Feign client và khai báo interface:

```java
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableFeignClients
class OrderApplication {
}
```

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/products/{id}")
    ProductResponse getProduct(@PathVariable("id") String productId);
}
```

Khi LoadBalancer có mặt, tên `catalog-service` trong `@FeignClient` được dùng làm service ID để chọn instance. Không cần tự tạo `RestClient.Builder` hoặc `WebClient.Builder` cho Feign; integration của OpenFeign đảm nhiệm phần kết nối với LoadBalancer.

## 4. Cấu hình nguồn discovery cho các starter

Các ví dụ trên giả định có một discovery provider. Với Eureka, ứng dụng gọi dịch vụ thường có cấu hình như sau:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
```

Service đích đăng ký tên `catalog-service`; `order-service` tìm instance theo đúng tên đó. Các thuộc tính đăng ký instance, địa chỉ quảng bá và địa chỉ registry phải phù hợp với môi trường triển khai.

Trong một bài thực hành chưa cần registry riêng, có thể khai báo instance tĩnh qua `SimpleDiscoveryClient`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Với cấu hình này, LoadBalancer có hai instance ứng viên cho `catalog-service`. Đây là cách tiện lợi để thử nghiệm cơ chế chọn instance; trong môi trường thật, danh sách instance thường đến từ registry hoặc nền tảng triển khai.

## 5. Chọn tổ hợp dependency phù hợp

| Nhu cầu | HTTP client starter | LoadBalancer | Discovery |
|---|---|---|---|
| Gọi đồng bộ bằng RestClient | `spring-boot-starter-web` | `spring-cloud-starter-loadbalancer` | Eureka, Consul hoặc SimpleDiscoveryClient |
| Gọi reactive bằng WebClient | `spring-boot-starter-webflux` | `spring-cloud-starter-loadbalancer` | Eureka, Consul hoặc SimpleDiscoveryClient |
| Gọi qua interface bằng OpenFeign | `spring-cloud-starter-openfeign` | `spring-cloud-starter-loadbalancer` | Eureka, Consul hoặc SimpleDiscoveryClient |

Một ứng dụng có thể sử dụng nhiều HTTP client cùng lúc. Khi đó, khai báo các starter client cần thiết và chỉ khai báo một nguồn discovery phù hợp. Tất cả client có thể dùng chung service ID, nhưng mỗi loại client cần cách cấu hình integration riêng như các phần trên.

## 6. Kiểm tra dependency và các lỗi thường gặp

Sau khi thêm dependency, hãy kiểm tra cây dependency để xác nhận đúng starter đã được đưa vào ứng dụng:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

Khi request theo service ID chưa được phân giải, kiểm tra lần lượt:

1. **Sai release train:** Spring Boot và Spring Cloud không tương thích có thể gây lỗi khởi động hoặc lỗi liên kết class. Kiểm tra BOM và bảng tương thích.
2. **Thiếu LoadBalancer:** HTTP client vẫn chạy nhưng không có integration để chọn instance. Kiểm tra `spring-cloud-starter-loadbalancer` trong runtime classpath.
3. **Thiếu nguồn instance:** LoadBalancer được cấu hình nhưng discovery trả về danh sách rỗng. Kiểm tra registry, discovery starter và service ID.
4. **Sai service ID:** tên trong URL hoặc `@FeignClient` không khớp tên dịch vụ được đăng ký.
5. **Builder không được đánh dấu:** với `RestClient` và `WebClient`, xác nhận client thực sự được tạo từ builder có `@LoadBalanced`; tránh inject nhầm builder thường.
6. **Chỉ có HTTP client starter:** `spring-boot-starter-web`, `spring-boot-starter-webflux` hoặc OpenFeign tự chúng không cung cấp registry và danh sách instance.

Phân biệt lỗi thiếu dependency với lỗi discovery giúp xử lý đúng nguyên nhân. Nếu ứng dụng không khởi động do thiếu class hoặc bean, kiểm tra dependency và cấu hình auto-configuration. Nếu ứng dụng khởi động nhưng không tìm thấy instance, kiểm tra service ID và dữ liệu mà `DiscoveryClient` cung cấp. Nếu instance đã được chọn nhưng request thất bại, tiếp tục kiểm tra host, port, network và response của dịch vụ đích.

## 7. Ghi nhớ

Chọn starter HTTP client theo API muốn dùng: `spring-boot-starter-web` cho RestClient, `spring-boot-starter-webflux` cho WebClient và `spring-cloud-starter-openfeign` cho OpenFeign. Thêm `spring-cloud-starter-loadbalancer` để chọn instance theo service ID, rồi kết nối một nguồn discovery như Eureka, Consul hoặc cấu hình instance tĩnh. Import BOM Spring Cloud tương thích với Spring Boot để giữ các dependency cùng phiên bản và giúp ứng dụng khởi động ổn định.
