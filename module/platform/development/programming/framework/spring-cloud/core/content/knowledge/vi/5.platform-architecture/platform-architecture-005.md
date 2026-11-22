# Cách cấu hình do ứng dụng khai báo thay thế mặc định

Trong Spring Boot và Spring Cloud, thư viện thường cung cấp giá trị hoặc bean mặc định để ứng dụng có thể khởi động với ít cấu hình nhất. Khi đưa ứng dụng vào một hệ thống cụ thể, nhóm phát triển cần thay các mặc định đó bằng lựa chọn phù hợp: endpoint nội bộ, timeout, nguồn khám phá dịch vụ, quy tắc chọn instance hoặc implementation của một abstraction.

**Cấu hình do ứng dụng khai báo thay thế mặc định** là cách ứng dụng chủ động cung cấp giá trị hoặc thành phần của mình để Spring sử dụng thay cho phương án dự phòng. Cần phân biệt hai cơ chế: **ghi đè thuộc tính trong Environment** và **thay thế bean do auto-configuration tạo ra**. Hai cơ chế có liên quan nhưng không đồng nhất.

Bài học thuộc chương **Kiến trúc nền tảng** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào Spring Boot configuration, Spring Cloud Commons/Context, khả năng mở rộng qua bean và customizer, tương tác với cấu hình bên ngoài, kiểm thử và vận hành.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt giá trị mặc định của thư viện, cấu hình ứng dụng, cấu hình theo môi trường và secret.
- Giải thích cách Spring Boot hợp nhất nguồn cấu hình trong `Environment` và vì sao biến môi trường hoặc tham số dòng lệnh có thể ghi đè file YAML.
- Dùng `@ConfigurationProperties` để bind cấu hình có kiểu, đặt giá trị mặc định và validate dữ liệu.
- Hiểu cơ chế auto-configuration lùi lại khi ứng dụng tự cung cấp bean, đặc biệt với `@ConditionalOnMissingBean`.
- Phân biệt thay thế bean với `@Primary`, `@Qualifier`, `@Order` và bean definition overriding.
- Nhận biết điểm mở rộng của Spring Cloud Commons như discovery, service registry và load balancing.
- Kiểm thử cấu hình và bean thực tế được chọn, chẩn đoán vì sao mặc định vẫn được sử dụng hoặc vì sao ứng dụng có nhiều bean cùng loại.

## 2. Hai loại mặc định cần phân biệt

Từ “mặc định” trong Spring có thể chỉ ít nhất hai thứ khác nhau.

### 2.1. Mặc định của một thuộc tính

Một thư viện có thể cung cấp giá trị mặc định cho property, chẳng hạn timeout, cổng, tên chiến lược hoặc feature flag. Ứng dụng thay đổi hành vi bằng cách cung cấp cùng khóa ở một nguồn cấu hình có độ ưu tiên cao hơn.

Ví dụ thư viện dùng giá trị dự phòng `demo.client.timeout=2s`. Ứng dụng khai báo:

```yaml
demo:
  client:
    timeout: 5s
```

Khi bean đọc khóa `demo.client.timeout`, giá trị `5s` được bind thay cho giá trị dự phòng `2s`. Không có bean nào bị thay thế trong ví dụ này; chỉ có **giá trị cấu hình** thay đổi.

### 2.2. Mặc định của một bean

Auto-configuration có thể tạo bean mặc định khi classpath và điều kiện phù hợp. Ví dụ một thư viện cung cấp bean `EndpointResolver` để chọn địa chỉ mặc định. Ứng dụng muốn dùng quy tắc riêng có thể khai báo bean `EndpointResolver` của chính mình.

Nhiều auto-configuration được thiết kế với điều kiện `@ConditionalOnMissingBean`. Khi bean do ứng dụng khai báo đã tồn tại, cấu hình tự động tương ứng sẽ **back off** và không tạo bean dự phòng. Ở đây, ứng dụng thay **thành phần được inject**, không chỉ thay một chuỗi property.

| Câu hỏi | Ghi đè property | Thay thế bean |
| --- | --- | --- |
| Thứ được thay đổi | Giá trị khóa cấu hình | Đối tượng do Spring container quản lý |
| Cơ chế chính | `Environment`, `PropertySource`, binding | `@Bean`, component scanning, điều kiện auto-configuration |
| Ví dụ | Đổi timeout từ `2s` sang `5s` | Dùng resolver do ứng dụng tự viết |
| Kiểm tra | Giá trị cuối cùng và nguồn của property | Bean nào được tạo và được inject |
| Rủi ro thường gặp | Nguồn ưu tiên cao hơn ghi đè ngoài dự kiến | Nhiều bean cùng loại hoặc auto-configuration không back off |

Không phải mọi property đều có thể thay một bean, và không phải mọi bean mặc định đều có một property để thay đổi. Cần xem API và điều kiện của thành phần đang sử dụng.

## 3. Spring Boot hợp nhất cấu hình trong Environment

Spring Boot tạo `Environment` chứa nhiều `PropertySource`. Mỗi nguồn cung cấp các cặp khóa–giá trị. Khi ứng dụng đọc một khóa, Spring tìm giá trị theo thứ tự ưu tiên của các nguồn đang hoạt động.

Các nguồn cấu hình thường gặp:

- File `application.yml` hoặc `application.properties` trong artifact.
- File cấu hình bên ngoài artifact và file riêng cho profile như `application-prod.yml`.
- Biến môi trường của tiến trình, ví dụ `DEMO_CLIENT_TIMEOUT`.
- Java system properties, ví dụ `-Ddemo.client.timeout=3s`.
- Tham số dòng lệnh, ví dụ `--demo.client.timeout=4s`.
- Nguồn được import bằng `spring.config.import`, chẳng hạn Config Server hoặc config tree.
- Nguồn cấu hình được bổ sung bởi framework hoặc ứng dụng qua API Spring.

Trong các tình huống Spring Boot phổ biến, tham số dòng lệnh có độ ưu tiên cao hơn biến môi trường, và biến môi trường có độ ưu tiên cao hơn file cấu hình thông thường. Cấu hình bên ngoài có thể ghi đè cấu hình được đóng gói trong JAR. Tuy nhiên, thứ tự chi tiết còn phụ thuộc loại nguồn, vị trí file, profile, import và phiên bản Boot; không nên áp dụng một danh sách rút gọn cho mọi trường hợp.

### 3.1. Ví dụ cùng một khóa xuất hiện ở nhiều nguồn

`application.yml`:

```yaml
demo:
  client:
    timeout: 2s
```

`application-prod.yml`:

```yaml
demo:
  client:
    timeout: 3s
```

Khởi động với profile production và một biến môi trường:

```powershell
$env:DEMO_CLIENT_TIMEOUT = '5s'
java -jar app.jar --spring.profiles.active=prod
```

Nếu không có nguồn ưu tiên cao hơn can thiệp, biến môi trường cung cấp `5s` và ghi đè giá trị trong các file cấu hình. Nếu thêm tham số:

```bash
java -jar app.jar --spring.profiles.active=prod --demo.client.timeout=4s
```

thì tham số dòng lệnh `4s` thường thắng biến môi trường `5s` trong ứng dụng Spring Boot thông thường.

**Điểm quan trọng:** file profile không mặc nhiên thắng biến môi trường chỉ vì nó mang tên `prod`. Profile quyết định tài liệu cấu hình nào được kích hoạt; thứ tự ưu tiên giữa các nguồn quyết định giá trị cuối cùng.

### 3.2. Cấu hình bên ngoài và profile

Có thể đặt file cấu hình ngoài JAR và chỉ định vị trí khi chạy:

```bash
java -jar app.jar --spring.config.additional-location=file:./config/
```

`spring.config.additional-location` bổ sung vị trí để Spring Boot tìm cấu hình; `spring.config.location` có ý nghĩa thay thế các vị trí mặc định trong một số cách dùng. Cần đọc tài liệu đúng phiên bản trước khi chọn vì thay nhầm location có thể khiến ứng dụng không còn nạp file cấu hình mong đợi.

Trong hệ thống triển khai, nên quy định rõ:

- Cấu hình mặc định nào được đóng gói cùng artifact.
- Cấu hình nào do nền tảng cung cấp bên ngoài.
- Profile nào được bật ở từng môi trường.
- Khóa nào là bắt buộc và phải fail fast nếu thiếu.
- Nguồn nào có quyền ghi đè khóa nhạy cảm hoặc ảnh hưởng bảo mật.

Không dùng giá trị mặc định vô hại cho một khóa production bắt buộc nếu điều đó có thể khiến ứng dụng chạy sai môi trường mà không báo lỗi.

## 4. Đặt giá trị mặc định và bind cấu hình có kiểu

Với một property đơn lẻ, `@Value` hỗ trợ biểu thức có giá trị dự phòng:

```java
@Value("${demo.client.timeout:2s}")
private Duration timeout;
```

Nếu `demo.client.timeout` không tồn tại, biểu thức dùng `2s`. Nếu có nguồn cấu hình cung cấp giá trị, Spring chuyển đổi sang kiểu `Duration`. Cách này tiện cho một số giá trị đơn giản, nhưng khi có nhiều khóa liên quan, nên dùng `@ConfigurationProperties`.

### 4.1. Tạo lớp properties

`ClientProperties.java`:

```java
package com.example.platform.config;

import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.client")
public class ClientProperties {

    @NotBlank
    private String baseUrl = "http://localhost:8081";

    @NotNull
    private Duration timeout = Duration.ofSeconds(2);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Đăng ký lớp properties trong ứng dụng:

```java
package com.example.platform;

import com.example.platform.config.ClientProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class PlatformApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlatformApplication.class, args);
    }
}
```

Trong project lớn, có thể dùng `@ConfigurationPropertiesScan` để quét các lớp properties thay cho khai báo từng lớp. Cần bảo đảm package được quét nằm dưới package gốc hoặc chỉ định rõ package scan.

### 4.2. Ứng dụng thay giá trị dự phòng

`application.yml`:

```yaml
demo:
  client:
    base-url: https://inventory.internal
    timeout: 5s
```

`ClientProperties` có mặc định `localhost:8081` và `2s`. File cấu hình của ứng dụng cung cấp endpoint và timeout khác nên các giá trị được bind vào bean sẽ là `https://inventory.internal` và `5s`.

Có thể dùng biến môi trường `DEMO_CLIENT_TIMEOUT` hoặc tham số `--demo.client.timeout` để thay tiếp giá trị file YAML khi chạy ở một môi trường cụ thể.

### 4.3. Default không đồng nghĩa fallback an toàn

Giá trị khởi tạo trong Java hoặc default của annotation chỉ được dùng khi không có giá trị khác bind vào. Cần cân nhắc liệu fallback có hợp lý không:

- Timeout có thể có default vừa phải, nhưng phải đủ an toàn cho latency và retry budget.
- URL của mock server chỉ phù hợp cho dev/test; không nên là fallback production.
- API key và mật khẩu không được đặt giá trị mặc định trong mã nguồn.
- Thuộc tính bắt buộc nên validate và khiến ứng dụng không khởi động nếu thiếu.

Nếu muốn endpoint production bắt buộc, có thể bỏ giá trị mặc định và khai báo validation:

```java
@NotBlank
private String baseUrl;
```

Khi chưa có `demo.client.base-url`, validation sẽ báo lỗi trong quá trình tạo bean properties (với dependency validation phù hợp), giúp phát hiện cấu hình thiếu trước khi ứng dụng nhận traffic.

## 5. Auto-configuration và cơ chế back off

Spring Boot auto-configuration dựa trên classpath, điều kiện và các bean đã có trong container để tạo cấu hình phù hợp. Thư viện có thể cung cấp bean mặc định nhằm giảm công việc cho ứng dụng. Một mẫu phổ biến là `@ConditionalOnMissingBean`.

Ví dụ sau mô phỏng một thư viện nội bộ cung cấp bộ phân giải endpoint mặc định.

### 5.1. Hợp đồng dùng chung

`EndpointResolver.java`:

```java
package com.example.platform.endpoint;

public interface EndpointResolver {
    String resolve(String serviceName);
}
```

### 5.2. Cấu hình mặc định của thư viện

`DefaultEndpointAutoConfiguration.java`:

```java
package com.example.platform.endpoint.autoconfigure;

import com.example.platform.endpoint.EndpointResolver;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class DefaultEndpointAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(EndpointResolver.class)
    EndpointResolver defaultEndpointResolver() {
        return serviceName -> "http://" + serviceName + ":8080";
    }
}
```

`@ConditionalOnMissingBean(EndpointResolver.class)` có nghĩa: chỉ tạo bean mặc định nếu tại thời điểm điều kiện được đánh giá, container chưa có bean phù hợp với kiểu `EndpointResolver`. Khi ứng dụng khai báo một bean cùng hợp đồng, auto-configuration có thể lùi lại.

Trong một thư viện auto-configuration thực tế, lớp cấu hình phải được đăng ký theo cơ chế auto-configuration imports của Spring Boot (file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` ở các thế hệ Boot hiện đại). Ví dụ này minh họa cơ chế điều kiện; chỉ đặt một class vào package không khiến nó tự trở thành auto-configuration được phát hiện từ mọi ứng dụng.

### 5.3. Ứng dụng cung cấp implementation riêng

`ApplicationEndpointConfiguration.java`:

```java
package com.example.platform;

import com.example.platform.endpoint.EndpointResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationEndpointConfiguration {

    @Bean
    EndpointResolver applicationEndpointResolver() {
        return serviceName -> {
            if ("inventory".equals(serviceName)) {
                return "https://inventory.prod.internal";
            }
            return "https://" + serviceName + ".prod.internal";
        };
    }
}
```

Khi bean này đã được đăng ký trước lúc auto-configuration đánh giá điều kiện, `@ConditionalOnMissingBean` không khớp và bean mặc định không được tạo. Ứng dụng dùng implementation riêng.

Kết quả mong muốn:

| Service name | Resolver mặc định | Resolver do ứng dụng cung cấp |
| --- | --- | --- |
| `inventory` | `http://inventory:8080` | `https://inventory.prod.internal` |
| `catalog` | `http://catalog:8080` | `https://catalog.prod.internal` |

Trong dự án thật, endpoint thường nên được cấu hình qua properties hoặc discovery thay vì nối chuỗi host như ví dụ. Ví dụ chỉ làm rõ việc thay thế implementation ở ranh giới abstraction.

### 5.4. Vì sao thứ tự auto-configuration quan trọng?

Các điều kiện bean được đánh giá trong quá trình refresh application context. Auto-configuration của Spring Boot được sắp xếp theo cơ chế của framework; bean definitions từ cấu hình ứng dụng thông thường thường có thể được phát hiện để điều kiện `@ConditionalOnMissingBean` lùi lại.

Không nên tự tạo một auto-configuration tùy tiện cùng mức ưu tiên rồi giả định điều kiện luôn nhìn thấy mọi bean sẽ được đăng ký về sau. Với thư viện, hãy dùng annotation auto-configuration và ordering phù hợp, kiểm thử bằng `ApplicationContextRunner`, đồng thời xem condition evaluation report nếu hành vi khác mong đợi.

## 6. Thay thế bean khác với chọn bean khi inject

Có một số annotation thường bị hiểu nhầm là “ghi đè mặc định”.

### 6.1. `@Primary` chọn bean ưu tiên

`@Primary` đánh dấu một bean là lựa chọn ưu tiên khi Spring cần inject một bean trong số nhiều bean cùng kiểu. Nó **không xóa** bean còn lại. Nếu auto-configuration dùng `@ConditionalOnMissingBean`, sự hiện diện của bean ứng dụng cùng kiểu có thể làm điều kiện lùi lại; việc đó xảy ra do bean đã tồn tại, không phải do annotation `@Primary`.

```java
@Bean
@Primary
EndpointResolver preferredEndpointResolver() {
    return serviceName -> "https://" + serviceName + ".internal";
}
```

Nếu có một bean mặc định và một bean `@Primary`, cả hai có thể cùng tồn tại trong trường hợp cấu hình mặc định không dùng điều kiện back off. Injection theo kiểu `EndpointResolver` sẽ chọn bean primary trong trường hợp phù hợp, nhưng code truy vấn danh sách bean vẫn thấy cả hai.

### 6.2. `@Qualifier` chỉ rõ bean cần dùng

```java
public InventoryClient(
        @Qualifier("inventoryEndpointResolver")
        EndpointResolver resolver) {
    this.resolver = resolver;
}
```

`@Qualifier` giúp lựa chọn bean cụ thể theo qualifier/name khi inject. Nó không tự thay implementation mặc định ở toàn ứng dụng.

### 6.3. `@Order` ảnh hưởng thứ tự, không phải thay thế

Với các extension được Spring tổng hợp thành danh sách hoặc chạy theo thứ tự, `@Order` có thể ảnh hưởng thứ tự xử lý. Nó không khiến một bean có cùng kiểu biến mất và không phải công cụ thay auto-configuration.

### 6.4. Bean definition overriding

Spring có cơ chế cho phép hoặc từ chối việc một bean definition đăng ký sau dùng cùng tên để thay definition trước, tùy cấu hình. Không nên dựa vào việc trùng tên bean để tùy biến auto-configuration. Cách rõ ràng hơn là sử dụng extension point được tài liệu hỗ trợ, điều kiện `@ConditionalOnMissingBean` hoặc cấu hình riêng theo API của thư viện.

Không bật `spring.main.allow-bean-definition-overriding=true` chỉ để che xung đột. Trùng tên có thể khiến kết quả phụ thuộc thứ tự nạp cấu hình và khó chẩn đoán khi nâng cấp.

## 7. Thay thế mặc định ở Spring Cloud Commons

Spring Cloud Commons cung cấp các abstraction để ứng dụng làm việc với hạ tầng phân tán mà không phụ thuộc trực tiếp vào một sản phẩm cụ thể. Ứng dụng có thể chọn implementation hoặc tùy biến theo extension point mà thành phần cung cấp.

### 7.1. DiscoveryClient và ServiceRegistry

`DiscoveryClient` cung cấp API tìm các instance của service theo tên. `ServiceRegistry` cung cấp abstraction đăng ký và hủy đăng ký instance. Các abstraction này không tự tạo registry; cần một implementation tương ứng (ví dụ Eureka hoặc Consul) và cấu hình kết nối.

Khi dùng một discovery implementation, hãy bắt đầu bằng cách cấu hình client theo tài liệu của nó. Chỉ tự cung cấp implementation `DiscoveryClient` hoặc `ServiceRegistry` khi thực sự cần tích hợp registry riêng hoặc nguồn instance đặc thù. Việc thêm bean cùng kiểu có thể tác động đến điều kiện auto-configuration và cách ứng dụng lựa chọn client; phải kiểm tra cụ thể với release train đang dùng.

Ví dụ cách ứng dụng sử dụng abstraction:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceLookup {

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
```

Code trên chỉ truy vấn các instance đã được discovery client cung cấp. Nếu chưa cấu hình registry hoặc implementation trả về danh sách rỗng, kết quả cũng có thể rỗng. Không thể kết luận ứng dụng đã đăng ký thành công chỉ vì context khởi động được.

### 7.2. Spring Cloud LoadBalancer

Spring Cloud LoadBalancer cung cấp abstraction chọn instance từ các nguồn `ServiceInstance`. Ứng dụng có thể dùng chiến lược mặc định hoặc tùy biến theo service. Với một service cụ thể, `@LoadBalancerClient` cho phép khai báo cấu hình riêng cho named client.

Ví dụ minh họa cách gắn cấu hình cho service `inventory`:

```java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "inventory",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class LoadBalancerClientsConfiguration {
}
```

Cấu hình của named client:

```java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryInstances(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .build(context);
    }
}
```

Ví dụ minh họa việc khai báo nguồn instance cho named client; cần có dependency LoadBalancer, discovery implementation tương ứng. Không đặt cấu hình dành riêng cho named client vào component scan toàn cục nếu điều đó khiến bean trở thành cấu hình global; giữ class cấu hình ở vị trí không bị quét như cấu hình ứng dụng thông thường và để `@LoadBalancerClient` tham chiếu đến nó.

Khi cần đổi chiến lược chọn instance, hãy dùng extension point được phiên bản Spring Cloud LoadBalancer hỗ trợ (ví dụ `ReactorLoadBalancer` hoặc `ServiceInstanceListSupplier`), đồng thời xác định phạm vi global hay chỉ cho một service. Không thay toàn bộ LoadBalancer chỉ để đổi một property đã có sẵn.

### 7.3. Customizer thường phù hợp hơn thay toàn bộ bean

Nhiều thư viện cung cấp interface dạng `Customizer` hoặc callback để thay đổi một phần cấu hình của đối tượng được tạo tự động. Nếu nhu cầu chỉ là chỉnh timeout, default header, retry policy hoặc cách xây dựng client, hãy ưu tiên customizer mà thư viện hỗ trợ thay vì tự dựng lại toàn bộ bean.

Lý do:

- Giữ lại các thiết lập mặc định khác mà framework đã tối ưu.
- Giảm nguy cơ bỏ sót metrics, tracing, security hoặc lifecycle hook.
- Giảm phụ thuộc vào constructor và chi tiết triển khai nội bộ có thể thay đổi giữa các phiên bản.
- Làm rõ phạm vi tùy biến và dễ kiểm thử hơn.

## 8. Spring Cloud Context và cấu hình được làm mới

Spring Cloud Context bổ sung cơ chế quản lý context và refresh cho ứng dụng Spring. Khi cấu hình từ nguồn ngoài thay đổi, một quy trình refresh có thể cập nhật `Environment` và làm mới những bean được đánh dấu phù hợp.

Ví dụ:

```java
@Component
@RefreshScope
public class GreetingPolicy {

    private final String greeting;

    public GreetingPolicy(
            @Value("${app.greeting:Xin chào}") String greeting) {
        this.greeting = greeting;
    }

    public String greeting() {
        return greeting;
    }
}
```

Khi có cơ chế refresh hợp lệ, proxy refresh scope có thể tạo lại target bean khi được truy cập sau khi scope bị làm mới. Giá trị mới được lấy từ cấu hình hiệu lực tại thời điểm tạo target mới.

Phân biệt ba thao tác:

1. **Thay đổi nguồn:** sửa Git repository, biến môi trường được cấp cho lần chạy sau hoặc secret manager.
2. **Nạp/refresh cấu hình:** ứng dụng cập nhật `Environment` theo cơ chế được tích hợp.
3. **Áp dụng vào tài nguyên:** bean, cache, connection pool hoặc client phải hỗ trợ việc nhận cấu hình mới.

Ba bước này không tự động xảy ra đồng thời. Thay biến môi trường của tiến trình đang chạy thường không đổi giá trị mà JVM đã nhận. `@RefreshScope` cũng không tự phát hiện thay đổi ở Git hay secret manager.

Một số bean giữ trạng thái hoặc tài nguyên dài hạn (ví dụ connection pool, TLS context, client có connection đã mở) cần chiến lược thay thế, đóng tài nguyên và rollout phù hợp. Với thay đổi ảnh hưởng bảo mật hoặc kết nối, restart có kiểm soát thường dễ dự đoán hơn refresh tùy tiện.

Endpoint Actuator phục vụ refresh nếu được dùng phải giới hạn truy cập, xác thực và exposure. Không mở endpoint quản trị ra mạng công cộng; refresh có thể làm thay đổi hành vi production.

## 9. Kiểm thử để chứng minh mặc định đã được thay

Kiểm thử không nên chỉ xác nhận context khởi động. Cần chứng minh **giá trị nào được bind** hoặc **bean nào được tạo**.

### 9.1. Kiểm thử property binding

`ClientPropertiesTest.java`:

```java
package com.example.platform.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void usesApplicationValuesWhenProvided() {
        runner.withPropertyValues(
                "demo.client.base-url=https://inventory.test",
                "demo.client.timeout=5s")
            .run(context -> {
                ClientProperties properties =
                    context.getBean(ClientProperties.class);

                assertThat(properties.getBaseUrl())
                    .isEqualTo("https://inventory.test");
                assertThat(properties.getTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(5));
            });
    }

    @Test
    void fallsBackWhenPropertyIsAbsent() {
        runner.run(context -> {
            ClientProperties properties =
                context.getBean(ClientProperties.class);

            assertThat(properties.getBaseUrl())
                .isEqualTo("http://localhost:8081");
            assertThat(properties.getTimeout())
                .isEqualTo(java.time.Duration.ofSeconds(2));
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {
    }
}
```

`ApplicationContextRunner` giúp tạo context nhỏ với property kiểm soát được. Hai test chứng minh cả trường hợp ứng dụng khai báo giá trị và trường hợp giữ default.

### 9.2. Kiểm thử auto-configuration back off

Có thể kiểm tra cấu hình mặc định độc lập bằng `ApplicationContextRunner`:

```java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
            DefaultEndpointAutoConfiguration.class));

@Test
void createsDefaultWhenApplicationHasNoResolver() {
    runner.run(context -> {
        EndpointResolver resolver =
            context.getBean(EndpointResolver.class);

        assertThat(resolver.resolve("inventory"))
            .isEqualTo("http://inventory:8080");
    });
}

@Test
void backsOffWhenApplicationProvidesResolver() {
    runner.withUserConfiguration(ApplicationEndpointConfiguration.class)
        .run(context -> {
            EndpointResolver resolver =
                context.getBean(EndpointResolver.class);

            assertThat(resolver.resolve("inventory"))
                .isEqualTo("https://inventory.prod.internal");
        });
}
```

Ví dụ cần import `org.springframework.boot.autoconfigure.AutoConfigurations` và `org.springframework.boot.test.context.runner.ApplicationContextRunner` cùng AssertJ. Nó kiểm tra hợp đồng: bean mặc định tồn tại khi không có bean ứng dụng, và không được tạo khi ứng dụng cung cấp implementation.

Nếu auto-configuration là thư viện riêng, cần test cả đăng ký qua imports metadata và các điều kiện classpath/property, không chỉ gọi trực tiếp class cấu hình.

### 9.3. Kiểm thử thứ tự ưu tiên nguồn

Với Spring Boot integration test, có thể truyền thuộc tính kiểm thử:

```java
@SpringBootTest(properties = {
    "demo.client.timeout=7s"
})
class ClientConfigurationIntegrationTest {
    // Inject ClientProperties và assert timeout là 7 giây.
}
```

Nếu muốn kiểm tra biến môi trường thật, hãy chạy integration test trong tiến trình hoặc container có environment được thiết lập rõ ràng. `@DynamicPropertySource` phù hợp để đưa endpoint/port động từ Testcontainers vào context. Không dùng test unit để khẳng định thứ tự mọi PropertySource của mọi phiên bản; kiểm tra theo cấu hình thực tế mà ứng dụng triển khai.

### 9.4. Kiểm thử refresh

Refresh là luồng khác với bind lúc khởi động. Khi kiểm thử, cần:

- Đặt giá trị ban đầu cho property và xác nhận bean đọc giá trị đó.
- Thay đổi nguồn cấu hình theo cách hệ thống thực tế hỗ trợ.
- Kích hoạt sự kiện/cơ chế refresh được cấu hình.
- Xác nhận bean refresh scope nhận giá trị mới sau khi target được tạo lại.
- Kiểm tra bean không thuộc refresh scope hoặc tài nguyên dài hạn có cần restart hay xử lý riêng.

Không coi test bind lúc khởi động là bằng chứng refresh đã hoạt động.

## 10. Chẩn đoán khi mặc định vẫn được dùng

Khi ứng dụng không nhận giá trị hoặc bean tùy chỉnh, đi theo thứ tự:

1. **Kiểm tra khóa và kiểu:** property có đúng prefix, đúng tên, đúng định dạng và chuyển đổi được không?
2. **Kiểm tra nguồn:** profile có hoạt động không, file có được nạp không, biến môi trường có vào đúng tiến trình không?
3. **Kiểm tra ưu tiên:** có nguồn nào có độ ưu tiên cao hơn đang ghi đè giá trị ứng dụng không?
4. **Kiểm tra binding:** bean properties có được đăng ký và có setter/constructor binding hợp lệ không?
5. **Kiểm tra điều kiện auto-configuration:** điều kiện nào match, bean mặc định có được tạo không, ứng dụng có cung cấp bean đúng kiểu không?
6. **Kiểm tra injection:** có nhiều bean cùng kiểu không, injection đang dùng qualifier/primary nào?
7. **Kiểm tra thời điểm:** property hoặc bean có được cập nhật sau refresh/restart hay ứng dụng vẫn giữ instance cũ?

Khi cần xem auto-configuration condition, có thể chạy với `--debug` để in condition evaluation report:

```bash
java -jar app.jar --debug
```

Actuator cung cấp endpoint như `conditions`, `env` hoặc `configprops` tùy dependency và cấu hình exposure. Chúng có thể tiết lộ thông tin nội bộ, vì vậy chỉ bật có kiểm soát, bảo vệ bằng security và giới hạn mạng. Không gửi toàn bộ output môi trường vào ticket công khai; loại bỏ token, mật khẩu, URL có credential và dữ liệu nhạy cảm trước khi chia sẻ.

## 11. Tương thích Spring Boot và Spring Cloud

Cách tùy biến phụ thuộc API của phiên bản. Một ví dụ dùng `@AutoConfiguration` hoặc `@LoadBalancerClient` phải khớp release train; không lấy code từ một thế hệ Cloud rồi chép nguyên vào dự án Boot khác thế hệ.

Nguyên tắc quản lý dependency:

- Chọn Spring Boot version theo yêu cầu runtime và chính sách hỗ trợ của dự án.
- Tra bảng tương thích Spring Cloud release train với Spring Boot.
- Import `spring-cloud-dependencies` BOM tương ứng và để BOM quản lý version của Cloud modules.
- Không tự pin version riêng cho `spring-cloud-commons`, `spring-cloud-context` hoặc LoadBalancer nếu không có lý do đã được kiểm chứng.
- Khi nâng phiên bản, đọc release notes và chạy test cho extension point, điều kiện auto-configuration và hành vi refresh.

Nếu một bean tùy chỉnh đột nhiên không còn được chọn sau nâng cấp, cần kiểm tra condition report, thay đổi package/API và thứ tự auto-configuration của phiên bản mới trước khi thay đổi cấu hình toàn cục.

## 12. Tình huống thực tế: ứng dụng muốn thay discovery mặc định

Giả sử một nhóm dùng service registry nội bộ và muốn ứng dụng gọi service bằng tên logic. Có ba hướng xử lý:

- Nếu registry đã có Spring Cloud integration được hỗ trợ, dùng discovery starter tương ứng và cấu hình endpoint/credential bằng nguồn cấu hình bên ngoài.
- Nếu nguồn instance được xây dựng từ dữ liệu riêng, xem xét triển khai abstraction phù hợp hoặc extension point của LoadBalancer; chỉ làm khi hợp đồng và lifecycle đã rõ.
- Nếu chỉ muốn thay quy tắc chọn instance (ví dụ ưu tiên vùng gần nhất), giữ nguồn discovery hiện có và tùy biến supplier/load balancer cho service cần thiết.

Không nên tự viết discovery client mới chỉ vì muốn đổi timeout hoặc thứ tự chọn instance. Hãy xác định chính xác điểm thay đổi thuộc **nguồn cấu hình**, **nguồn danh sách instance** hay **chiến lược chọn instance**.

Quy trình triển khai an toàn:

1. Ghi lại hành vi mặc định hiện tại bằng test và log.
2. Xác định abstraction/extension point được hỗ trợ trong release train.
3. Cấu hình hoặc cung cấp implementation tùy chỉnh trong phạm vi cần thiết.
4. Test cả trường hợp có và không có bean tùy chỉnh.
5. Test khi registry lỗi, danh sách instance rỗng, cấu hình thiếu và khi refresh/restart.
6. Rollout từng phần, theo dõi lỗi kết nối và khả năng gọi đúng instance; giữ phương án quay về cấu hình đã biết.

## 13. Bài tập vận dụng

Một thư viện nội bộ cung cấp `PaymentEndpointProvider` và bean mặc định trỏ tới `http://localhost:9000`. Ứng dụng production muốn dùng endpoint `https://payment.prod.internal`, timeout mặc định `2s` nhưng staging muốn `4s`.

Hãy thực hiện:

1. Định nghĩa `PaymentEndpointProvider` và auto-configuration với `@ConditionalOnMissingBean`.
2. Viết bean do ứng dụng cung cấp để thay endpoint mặc định.
3. Tạo `PaymentProperties` với `@ConfigurationProperties` và `Duration`; đặt default `2s`.
4. Khai báo timeout `4s` trong `application-staging.yml` và kích hoạt profile staging.
5. Truyền thêm `--payment.timeout=6s`; giải thích vì sao giá trị hiệu lực có thể là `6s`.
6. Viết test chứng minh auto-configuration tạo default khi không có bean ứng dụng và back off khi có bean tùy chỉnh.
7. Mô tả cách bảo vệ endpoint chẩn đoán và secret nếu dùng Config Server hoặc Actuator.

**Tiêu chí đánh giá:** phân biệt được property override với bean replacement; không dựa vào bean name collision; có test cho cả hai nhánh điều kiện; hiểu rằng profile chọn tập cấu hình còn PropertySource precedence quyết định giá trị cuối cùng.

## 14. Ghi nhớ

- Giá trị mặc định là điểm bắt đầu; ứng dụng có thể thay bằng property có độ ưu tiên cao hơn hoặc bằng bean implementation phù hợp.
- `Environment` và `PropertySource` quyết định giá trị cấu hình hiệu lực; file profile không tự động thắng biến môi trường hay tham số dòng lệnh.
- `@ConfigurationProperties` phù hợp với nhóm cấu hình có kiểu, default và validation.
- `@ConditionalOnMissingBean` là mẫu phổ biến giúp auto-configuration lùi lại khi ứng dụng đã cung cấp bean riêng.
- `@Primary`, `@Qualifier` và `@Order` điều khiển lựa chọn/thứ tự sử dụng bean; chúng không tương đương với việc xóa hoặc thay bean mặc định.
- Với Spring Cloud Commons, hãy tùy biến đúng abstraction: discovery source, service registry, instance supplier hay load-balancer strategy.
- `@RefreshScope` chỉ hỗ trợ làm mới bean theo cơ chế refresh; nó không tự theo dõi nguồn cấu hình và không bảo đảm mọi tài nguyên được cập nhật động.
- Kiểm thử cả giá trị cuối cùng lẫn bean được tạo; dùng condition report và công cụ chẩn đoán đã bảo vệ khi cần tìm nguyên nhân.

