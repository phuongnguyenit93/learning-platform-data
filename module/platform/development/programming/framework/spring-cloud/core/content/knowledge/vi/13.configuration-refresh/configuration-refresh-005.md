# Phân biệt rebind tại chỗ với tạo lại bean trong Refresh Scope

Khi cấu hình của ứng dụng Spring Cloud thay đổi, không phải bean nào cũng cần được tạo lại. Một bean chỉ giữ các giá trị cấu hình đơn giản có thể được bind lại trên instance đang tồn tại. Ngược lại, một client hoặc đối tượng có trạng thái được tạo từ cấu hình lúc khởi tạo có thể cần được hủy và tạo mới để nhận endpoint, credential hoặc tài nguyên mới.

Spring Cloud Context hỗ trợ cả hai cách. **Rebinding** cập nhật các bean `@ConfigurationProperties` ngay trên instance hiện hữu. **Refresh Scope** giữ một proxy ổn định nhưng invalidate target đã cache, để lần truy cập kế tiếp tạo target mới. Hiểu sự khác nhau này giúp chọn đúng vòng đời, tránh trạng thái nửa cũ nửa mới và giảm rủi ro khi cấu hình thay đổi lúc ứng dụng đang xử lý request.

Bài học thuộc chương **Làm mới cấu hình** của module **SPRING_CLOUD_CORE**. Ta sẽ đi từ `EnvironmentChangeEvent` đến `ConfigurationPropertiesRebinder` và `RefreshScope`, viết hai ví dụ có thể quan sát identity, rồi kiểm thử sự khác nhau giữa cập nhật tại chỗ và tạo lại target.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `EnvironmentChangeEvent` trong quy trình cập nhật cấu hình runtime.
- Mô tả cách `ConfigurationPropertiesRebinder` bind lại một bean mà không thay instance của bean đó.
- Phân biệt identity của bean `@ConfigurationProperties`, scoped proxy và target của `@RefreshScope`.
- Mô tả thứ tự cập nhật Environment, phát sự kiện, rebind và invalidate target cache.
- Chọn rebinding cho cấu hình mutable đơn giản hoặc `@RefreshScope` cho bean cần khởi tạo lại.
- Nhận diện rủi ro đọc đồng thời trong lúc rebinding và giới hạn nhất quán của Refresh Scope.
- Viết ví dụ Java và integration test để chứng minh instance nào được giữ lại, instance nào được tạo mới.
- Xử lý các trường hợp constructor binding, nested properties, HikariDataSource, xóa property và nhiều replica.

### 1.1. Dependency cần có

Hai cơ chế trong bài thuộc **Spring Cloud Context**. Nếu dependency graph chưa có module này, thêm dependency và để Spring Cloud BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

Nếu cần endpoint HTTP `/actuator/refresh`, thêm `spring-boot-starter-actuator` do Spring Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Trong dự án đã dùng Spring Cloud Config Client hoặc starter Cloud khác, `spring-cloud-context` có thể đã được kéo vào bắc cầu. Kiểm tra dependency tree trước khi khai báo trực tiếp. Cặp Spring Boot/Spring Cloud vẫn phải theo ma trận tương thích của release train đang dùng.

## 2. Hai chiến lược có vòng đời khác nhau

### 2.1. Rebind tại chỗ

Với một bean được quản lý bằng `@ConfigurationProperties`, Spring Cloud Context có thể bind lại các thuộc tính khi nhận `EnvironmentChangeEvent`. Bean hiện tại được giữ lại; các trường cấu hình được cập nhật trên chính object đó.

Ví dụ:

~~~java
@Component
@ConfigurationProperties(prefix = "routing")
public class RoutingProperties {

    private String host = "router-default";
    private int timeoutMs = 1000;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getTimeoutMs() {
        return timeoutMs;
    }

    public void setTimeoutMs(int timeoutMs) {
        this.timeoutMs = timeoutMs;
    }
}
~~~

Sau khi Environment có `routing.host=router-v2` và sự kiện thay đổi được phát, `RoutingProperties` được bind lại. Nếu một service đã inject bean này, field tham chiếu của service vẫn trỏ tới cùng instance `RoutingProperties`; khi đọc `getHost()`, service thấy giá trị mới.

### 2.2. Tạo lại target trong Refresh Scope

Với bean `@RefreshScope`, Spring inject một scoped proxy vào các bean tiêu thụ. Scope lưu target đã khởi tạo trong cache. Khi refresh, target cũ bị hủy và cache entry bị xóa. Proxy vẫn tồn tại; lần gọi phương thức tiếp theo qua proxy sẽ tạo target mới.

Ví dụ:

~~~java
@Component
@RefreshScope
public class RoutingClient {

    @Value("${routing.host:router-default}")
    private String host;

    public String currentHost() {
        return host;
    }
}
~~~

Một singleton giữ proxy `RoutingClient`. Sau refresh, field proxy trong singleton không đổi, nhưng target thực hiện `currentHost()` là một instance mới và nhận giá trị cấu hình hiện hành.

### 2.3. So sánh trực tiếp

| Tiêu chí | Rebinding `@ConfigurationProperties` | `@RefreshScope` |
| --- | --- | --- |
| Đối tượng được cập nhật | Bean cấu hình hiện có | Target của bean trong refresh scope |
| Identity của instance | Giữ nguyên instance | Target thay đổi; proxy giữ nguyên |
| Cách cập nhật | Bind lại các trường trên object | Hủy target cache rồi tạo target mới khi truy cập |
| Lifecycle | Bean hiện hữu được reset/rebind và chạy lại các bước khởi tạo tương ứng của rebinder | Target cũ chạy destruction callback; target mới chạy initialization callback |
| Khi nào phù hợp | Cấu hình mutable, đơn giản, có thể cập nhật an toàn tại chỗ | Client, factory hoặc bean có state/tài nguyên cần tạo lại từ cấu hình mới |
| Rủi ro chính | Thread khác có thể đọc trạng thái đang được cập nhật dở | Target mới có thể khởi tạo lỗi; state trong target cũ bị mất |
| Đồng bộ | Các lần rebind cùng bean được tuần tự hóa; không khóa toàn bộ reader bên ngoài | Đọc qua proxy được phối hợp với refresh của bean đó |

Không có chiến lược nào tự thay thế chiến lược kia trong mọi trường hợp. Chọn theo cách bean sử dụng cấu hình và tài nguyên mà nó sở hữu.

## 3. EnvironmentChangeEvent kích hoạt rebinding như thế nào?

`EnvironmentChangeEvent` mang danh sách key đã thay đổi trong Environment. `ConfigurationPropertiesRebinder` lắng nghe sự kiện này và bind lại các bean `@ConfigurationProperties`. Spring Cloud cũng có listener cập nhật mức log khi các key `logging.level.*` thay đổi.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant Source as Config source
    participant Refresher as ContextRefresher
    participant Env as Environment
    participant Event as EnvironmentChangeEvent
    participant Rebind as ConfigurationPropertiesRebinder
    participant Scope as RefreshScope
    Source->>Refresher: Cấu hình mới
    Refresher->>Env: Nạp lại PropertySource
    Refresher->>Refresher: So sánh key và giá trị cũ/mới
    Refresher->>Event: Publish changed keys
    Event-->>Rebind: Rebind @ConfigurationProperties
    Rebind->>Rebind: Cập nhật instance hiện hữu
    Refresher->>Scope: refreshAll()
    Scope->>Scope: Hủy target đang cache
    Note over Scope: Lần gọi sau qua proxy tạo target mới
~~~

Với quy trình refresh chuẩn của Spring Cloud Context, `ContextRefresher.refresh()` thực hiện các bước:

1. Chụp các giá trị đang có trong Environment.
2. Nạp lại các nguồn cấu hình theo cơ chế đang dùng, ví dụ Config Data hoặc legacy bootstrap.
3. So sánh trạng thái trước và sau để xác định các key thay đổi.
4. Phát `EnvironmentChangeEvent` để listener rebind bean cấu hình và cập nhật logger.
5. Gọi `RefreshScope.refreshAll()` để invalidate các target trong refresh scope.
6. Trả về tập key đã thay đổi.

Vì vậy, một lần gọi endpoint refresh có thể kích hoạt **cả hai cơ chế** trong cùng quy trình. Sự khác nhau nằm ở vòng đời từng loại bean, không phải hai endpoint hoàn toàn tách biệt.

### 3.1. Ai phát sự kiện?

Ứng dụng cần có một cơ chế đưa giá trị mới vào Environment và phát sự kiện. Có thể là:

- `POST /actuator/refresh` trong ứng dụng dùng Spring Cloud Context và Config Client.
- Spring Cloud Bus phát sự kiện refresh tới các instance đã đăng ký với bus.
- Một thành phần quản trị nội bộ cập nhật PropertySource rồi phát `EnvironmentChangeEvent` có chủ đích.

Spring Cloud Config Client **không mặc định polling Config Server** để tự phát hiện cấu hình thay đổi. Nếu có nhiều replica, cập nhật một instance không tự làm thay đổi Environment của các instance còn lại. Có thể dùng Bus hoặc cơ chế rollout/refresh có điều phối để mọi instance nhận cùng version cấu hình.

### 3.2. Cập nhật Environment trước khi rebind

`EnvironmentChangeEvent` chỉ thông báo rằng các key đã thay đổi; nó không tự tải dữ liệu từ Config Server. Nếu phát sự kiện trước khi PropertySource mới được cài vào Environment, rebinder sẽ bind lại bằng giá trị cũ.

Trình tự đúng là:

~~~text
Load new configuration
        |
        v
Update Environment / PropertySources
        |
        v
Publish EnvironmentChangeEvent
        |
        +----> Rebind @ConfigurationProperties
        |
        v
Invalidate RefreshScope target cache
~~~

## 4. Rebinding thay đổi instance hiện hữu

### 4.1. Bean JavaBean mutable

Rebinding phù hợp với bean cấu hình có thể được bind lại qua setter hoặc field. Ví dụ:

~~~java
package com.example.refresh;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "payment.retry")
public class RetryProperties {

    private int maxAttempts = 2;
    private long backoffMs = 200;

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public long getBackoffMs() {
        return backoffMs;
    }

    public void setBackoffMs(long backoffMs) {
        this.backoffMs = backoffMs;
    }
}
~~~

`application.yml` ban đầu:

~~~yaml
payment:
  retry:
    max-attempts: 2
    backoff-ms: 200
~~~

Sau khi nguồn cấu hình đổi thành:

~~~yaml
payment:
  retry:
    max-attempts: 4
    backoff-ms: 500
~~~

và sự kiện thay đổi được phát, bean `RetryProperties` được bind lại. Một singleton đã inject bean này tiếp tục giữ cùng reference và đọc được các giá trị mới qua getter.

### 4.2. Rebind không thay instance

Có thể quan sát identity bằng `System.identityHashCode` hoặc toán tử `==`:

~~~java
@Service
public class RetryService {

    private final RetryProperties properties;

    public RetryService(RetryProperties properties) {
        this.properties = properties;
    }

    public void logConfiguration() {
        System.out.println(
                "properties identity="
                        + System.identityHashCode(properties));
        System.out.println(
                "maxAttempts=" + properties.getMaxAttempts());
    }
}
~~~

Gọi `logConfiguration()` trước và sau rebinding sẽ cho thấy identity không đổi, trong khi giá trị getter thay đổi.

### 4.3. Reset default trước khi bind

Ở các phiên bản Spring Cloud Context hiện hành, rebinder có bước reset các property về giá trị mặc định trong class trước khi bind lại. Mục tiêu là tránh giữ giá trị cũ khi một key bị loại khỏi Environment.

Ví dụ:

~~~java
private int maxAttempts = 2;
~~~

Nếu giá trị cấu hình trước đó là `5`, nhưng key `payment.retry.max-attempts` bị loại bỏ và bean có thể reset về default, rebinding có thể đưa field về `2` thay vì giữ `5`.

Khả năng reset phụ thuộc cách bean được tạo. Với bean không có no-argument constructor phù hợp, constructor binding hoặc dependency bắt buộc trong constructor, rebinder không thể tạo một object mặc định đáng tin cậy chỉ để lấy giá trị reset. Trong trường hợp đó, giá trị bị loại bỏ có thể không được reset về default như mong đợi. Không dựa vào việc xóa key để điều khiển nghiệp vụ nếu chưa kiểm thử với đúng phiên bản.

### 4.4. Lifecycle của bean khi rebind

Rebinder cập nhật và khởi tạo lại bean theo cơ chế rebinding, nhưng vẫn giữ cùng instance. Do đó:

- Identity của object không đổi.
- Các field cấu hình được reset/bind lại theo khả năng của bean.
- Các bước post-processing và initialization được chạy lại theo quy trình của rebinder.
- Các reference khác đang giữ bean vẫn trỏ tới object đó.
- State nghiệp vụ khác nằm trong bean có thể vẫn còn, trừ phần được reset hoặc thay đổi bởi quá trình bind.

Không xem rebinding là một lần `new` object mới. Nếu bean cần dựng lại connection, HTTP client hoặc cache nội bộ dựa trên cấu hình, hãy tự quản lý việc tái tạo tài nguyên hoặc cân nhắc `@RefreshScope`.

## 5. Tạo lại target trong Refresh Scope

### 5.1. Proxy giữ identity, target thay đổi

`@RefreshScope` tạo scoped proxy. Các bean khác inject proxy thay vì giữ target trực tiếp. Scope cache target đã khởi tạo và tái sử dụng cho các lời gọi tiếp theo.

Khi gọi `refresh(beanName)` hoặc `refreshAll()`:

- Target hiện tại bị hủy nếu đã được tạo.
- Destruction callback của target được thực thi.
- Cache entry bị xóa.
- Proxy vẫn còn trong application context.
- Lần gọi phương thức tiếp theo qua proxy tạo target mới và chạy initialization callback.

Nếu bean chưa từng được sử dụng và chưa có target trong cache, refresh không cần tạo target mới ngay tại thời điểm đó. Target sẽ được tạo khi có lần gọi đầu tiên sau refresh.

**Lưu ý về lần khởi động đầu tiên:** proxy có thể chuyển lời gọi tới target theo cách lazy, nhưng implementation `RefreshScope` hiện hành còn có bước eager initialization khi nhận `ContextRefreshedEvent` cho các bean refresh-scope không được đánh dấu lazy. Vì vậy, target có thể được khởi tạo sớm trong lúc application context hoàn tất khởi động. Quy tắc sau khi invalidate vẫn giữ nguyên: target đã bị xóa khỏi cache sẽ được tạo lại khi có lần truy cập kế tiếp.

### 5.2. Ví dụ target cần dựng lại từ cấu hình

~~~java
package com.example.refresh;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class PaymentEndpointClient {

    private static final AtomicInteger IDS = new AtomicInteger();

    private final int targetId = IDS.incrementAndGet();

    @Value("${payment.gateway.base-url}")
    private String baseUrl;

    @PostConstruct
    void initialize() {
        System.out.println(
                "Create target " + targetId + " for " + baseUrl);
    }

    @PreDestroy
    void destroy() {
        System.out.println("Destroy target " + targetId);
    }

    public String endpoint() {
        return baseUrl;
    }

    public int targetId() {
        return targetId;
    }
}
~~~

Singleton tiêu thụ bean:

~~~java
@Service
public class PaymentGateway {

    private final PaymentEndpointClient client;

    public PaymentGateway(PaymentEndpointClient client) {
        this.client = client;
    }

    public String endpoint() {
        return client.endpoint();
    }

    public int targetId() {
        return client.targetId();
    }
}
~~~

`PaymentGateway` vẫn giữ cùng proxy `client`. Khi target bị invalidate, lần gọi `client.endpoint()` tiếp theo sẽ tạo `PaymentEndpointClient` mới, đọc lại `payment.gateway.base-url` và trả endpoint mới.

### 5.3. Không giữ state cũ ngoài proxy

Đoạn code sau không tự đổi sau refresh:

~~~java
@Service
public class CachedEndpoint {

    private final String endpoint;

    public CachedEndpoint(PaymentEndpointClient client) {
        this.endpoint = client.endpoint();
    }

    public String endpoint() {
        return endpoint;
    }
}
~~~

Constructor đã gọi proxy và copy chuỗi vào field singleton. Sau refresh, proxy có thể chuyển sang target mới, nhưng `CachedEndpoint.endpoint` vẫn là chuỗi cũ. Muốn nhận giá trị mới, hãy gọi qua proxy tại thời điểm sử dụng hoặc refresh chính bean đang giữ bản sao đó theo thiết kế phù hợp.

## 6. Hai cơ chế hoạt động trong cùng một lần refresh

Giả sử ứng dụng có:

- `RetryProperties`: bean `@ConfigurationProperties` mutable.
- `PaymentEndpointClient`: bean `@RefreshScope` dùng `@Value`.
- `PaymentGateway`: singleton giữ proxy của `PaymentEndpointClient`.

Trước refresh:

~~~yaml
payment:
  retry:
    max-attempts: 2
  gateway:
    base-url: "https://sandbox.payments.example"
~~~

Sau khi Config Server phát hành cấu hình mới:

~~~yaml
payment:
  retry:
    max-attempts: 4
  gateway:
    base-url: "https://payments.example"
~~~

Khi `ContextRefresher.refresh()` chạy:

1. Environment nhận giá trị mới cho cả hai key.
2. `EnvironmentChangeEvent` thông báo `payment.retry.max-attempts` và `payment.gateway.base-url` thay đổi.
3. `ConfigurationPropertiesRebinder` bind lại `RetryProperties` trên instance đang tồn tại.
4. `RefreshScope.refreshAll()` hủy target `PaymentEndpointClient` đã cache.
5. `PaymentGateway` vẫn giữ proxy cũ.
6. Lần gọi `PaymentGateway.endpoint()` kế tiếp tạo target `PaymentEndpointClient` mới và nhận base URL mới.

Kết quả:

| Đối tượng | Trước refresh | Sau refresh |
| --- | --- | --- |
| `RetryProperties` | Instance A, `maxAttempts=2` | Vẫn instance A, `maxAttempts=4` |
| Proxy `PaymentEndpointClient` | Proxy P | Vẫn proxy P |
| Target `PaymentEndpointClient` | Target T1, sandbox URL | Target T1 bị hủy; lần gọi sau tạo T2 với production URL |
| `PaymentGateway` | Singleton G giữ proxy P | Vẫn singleton G giữ proxy P |

Đây là điểm khác biệt cốt lõi: **rebind thay đổi trạng thái bên trong một instance; Refresh Scope thay instance target đứng sau proxy**.

## 7. Chọn cơ chế theo loại bean

| Loại bean hoặc nhu cầu | Cách tiếp cận nên cân nhắc | Lý do |
| --- | --- | --- |
| Bean chỉ chứa số lần retry, timeout, cờ bật/tắt | `@ConfigurationProperties` và rebinding | Cập nhật giá trị đơn giản, giữ instance |
| Bean cấu hình mutable được nhiều service đọc | Rebinding nếu reader chấp nhận cập nhật tại chỗ; Refresh Scope nếu cần góc nhìn nhất quán | Chọn theo yêu cầu concurrency |
| HTTP client được tạo từ base URL và credential | `@RefreshScope` hoặc factory có cơ chế thay client rõ ràng | Target cần được dựng lại từ cấu hình mới |
| Bean có cache nội bộ phụ thuộc cấu hình | `@RefreshScope` hoặc tự invalidate cache có kiểm soát | Chỉ đổi field có thể không làm cache cũ biến mất |
| Bean immutable/constructor-bound | Thiết kế lại lifecycle, dùng bean refreshable phù hợp hoặc restart | Rebinding thông thường không cập nhật object constructor-bound |
| DataSource/pool | Đánh giá khả năng rebind từng thuộc tính; cân nhắc restart hoặc pool hỗ trợ thay thế | Đổi URL không đồng nghĩa connection đang mở được chuyển an toàn |
| State nghiệp vụ như số dư hoặc giỏ hàng | Không dùng refresh scope để giữ state | Target có thể bị hủy và mất state trong memory |

Không nên thêm `@RefreshScope` vào tất cả bean. Tạo lại bean có chi phí: chạy constructor, inject dependency, khởi tạo connection/client, giải phóng tài nguyên cũ và xử lý lỗi nếu target mới không thể khởi tạo.

## 8. Tính nhất quán và truy cập đồng thời

### 8.1. Rebinding không khóa các thread đọc bean

Spring Cloud tuần tự hóa những lần rebind đồng thời trên cùng bean để hai refresh không chạy chồng các bước reset/bind/init. Tuy nhiên, điều đó không ngăn một thread khác đọc bean trong lúc các field đang được cập nhật.

Ví dụ bean có hai thuộc tính:

~~~yaml
payment:
  min-amount: 100
  max-amount: 1000
~~~

Khi đổi cả hai giá trị, một reader có thể nhìn thấy `min-amount` mới nhưng `max-amount` cũ trong khoảng thời gian bind đang diễn ra. Với collection mutable, binder có thể xóa danh sách trước rồi mới thêm các phần tử mới; reader đồng thời có thể quan sát collection tạm thời rỗng.

Nếu một request phải đọc một bộ cấu hình nhất quán, không chỉ từng field độc lập, rebinding tại chỗ có thể không đáp ứng yêu cầu.

### 8.2. Refresh Scope đồng bộ đọc với refresh theo từng bean

Refresh Scope dùng cơ chế khóa đọc/ghi theo bean để điều phối lời gọi qua proxy với thao tác refresh target. Điều này giúp caller không đọc target trong lúc scope đang thay đổi vòng đời target đó.

Tuy nhiên, đây **không phải transaction nguyên tử trên toàn application context**:

- Một bean scoped có thể đã chuyển sang target mới trong khi bean khác chưa được gọi lại.
- Nhiều replica trong cluster không được đồng bộ chỉ bằng một lần refresh trên một JVM.
- Một request đang dùng target cũ có thể đã lấy reference tới target trước khi refresh bắt đầu; thiết kế tài nguyên phải cho phép xử lý request đang chạy và đóng tài nguyên theo lifecycle.

Với thay đổi cần đồng bộ nhiều bean hoặc nhiều service, cân nhắc version cấu hình, rollout theo đợt, Spring Cloud Bus và cơ chế tương thích ngược giữa hai phiên bản.

## 9. Cập nhật cấu hình bằng Actuator

Trong ứng dụng có Spring Cloud Context và Config Client, có thể dùng endpoint `POST /actuator/refresh` để chạy quy trình refresh. Cần có Actuator và expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

Gọi endpoint:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

Response thường là danh sách các key đã thay đổi. Đây là tín hiệu hữu ích để kiểm tra quy trình nạp cấu hình, nhưng không chứng minh mọi target mới đã được tạo thành công: target trong Refresh Scope chỉ được tạo lại khi có lần gọi tiếp theo.

Endpoint refresh có quyền thay đổi trạng thái runtime, nên phải giới hạn bằng Spring Security, network policy và kênh quản trị nội bộ. Không expose endpoint này công khai.

### 9.1. Refresh nhiều instance

Nếu chạy nhiều replica, một request refresh trực tiếp chỉ tác động application context nhận request. Có thể:

- Dùng Spring Cloud Bus để broadcast sự kiện tới các instance.
- Gọi refresh từng instance qua hệ thống quản trị nội bộ.
- Dùng rolling restart khi thay đổi cần khởi tạo lại nhiều tài nguyên hoặc cần rollback rõ ràng.

Không polling Config Server ở mọi instance theo chu kỳ ngắn nếu không có lý do vận hành rõ ràng. Polling tạo tải và có thể khiến các instance nhìn thấy cấu hình ở các thời điểm khác nhau.

## 10. Các giới hạn cần biết

### 10.1. Constructor binding

Các object `@ConfigurationProperties` dùng constructor binding, bao gồm Java record, không thể được refresh bằng cơ chế rebinding thông thường. Chúng được tạo từ constructor và không có setter để binder cập nhật instance hiện tại.

Nếu cần thay đổi runtime, có thể:

- Đóng gói dữ liệu immutable trong một bean có lifecycle được kiểm soát và tạo lại qua Refresh Scope.
- Dùng một abstraction truy cập cấu hình mới tại thời điểm sử dụng.
- Restart/rollout ứng dụng khi thay đổi cấu hình.

### 10.2. HikariDataSource

`HikariDataSource` mặc định nằm trong `spring.cloud.refresh.never-refreshable`. Không nên kỳ vọng chỉ thêm `@RefreshScope` sẽ làm pool Hikari được tạo lại qua quy trình refresh chuẩn.

Thay datasource cần xem xét connection đang hoạt động, transaction, pool shutdown, drain request và thời điểm chuyển pool. Nếu cần thay datasource runtime, chọn implementation và quy trình đã được kiểm thử; không bỏ Hikari khỏi danh sách `never-refreshable` chỉ để endpoint refresh trả về thành công.

### 10.3. Bean được khai báo trong @Configuration

Đặt `@RefreshScope` trên một lớp `@Configuration` không tự động đưa tất cả bean được khai báo bằng `@Bean` vào refresh scope. Nếu một bean khác phụ thuộc vào các bean đó, nó không tự nhận target mới trừ khi chính nó được thiết kế để refresh và dependency được inject lại.

Nên đặt scope trực tiếp lên bean cần tạo lại:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    @RefreshScope
    PaymentEndpointClient paymentEndpointClient(
            PaymentClientFactory factory,
            PaymentProperties properties) {
        return factory.create(properties.baseUrl());
    }
}
~~~

Trong trường hợp này, bean `paymentEndpointClient` được refresh. Những singleton đã copy dữ liệu từ target hoặc giữ tài nguyên riêng vẫn cần xử lý vòng đời của chính chúng.

### 10.4. Xóa property khỏi Environment

Tài liệu Spring Cloud lưu ý rằng xóa một giá trị khỏi nguồn cấu hình rồi refresh không đảm bảo mọi bean sẽ nhận được ngữ nghĩa “key không còn tồn tại” như mong đợi. Hãy kiểm thử trường hợp xóa key với đúng phiên bản và thiết kế logic dựa trên giá trị mặc định hoặc một trạng thái tường minh thay vì dựa vào việc property biến mất.

### 10.5. AOT và native image

Context Refresh không được hỗ trợ cho Spring AOT transformations và native images theo tài liệu Spring Cloud hiện hành. Với ứng dụng AOT/native, đặt:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Sau đó dùng restart/rollout hoặc một cơ chế cập nhật cấu hình được hỗ trợ cho loại triển khai này.

## 11. Kiểm thử sự khác nhau giữa rebind và recreate

Một test tốt cần chứng minh:

- Bean `@ConfigurationProperties` giữ nguyên identity nhưng getter trả giá trị mới.
- Proxy `@RefreshScope` giữ nguyên identity.
- Target phía sau proxy được tạo mới sau khi cache bị invalidate.
- Target mới đọc giá trị đã cập nhật trong Environment.

Ví dụ dưới đây dùng `MapPropertySource` để thay một giá trị trong test, rồi phát `EnvironmentChangeEvent` và refresh target:

~~~java
package com.example.refresh;

import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ConfigurationRefreshModeTest {

    @Autowired
    RetryProperties retryProperties;

    @Autowired
    PaymentEndpointClient paymentEndpointClient;

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    ConfigurableApplicationContext applicationContext;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void rebindKeepsPropertiesBeanButRefreshRecreatesTarget() {
        RetryProperties propertiesReference = retryProperties;
        PaymentEndpointClient proxyReference = paymentEndpointClient;

        int oldTargetId = paymentEndpointClient.targetId();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "testOverrides",
                        Map.of(
                                "payment.retry.max-attempts", 4,
                                "payment.gateway.base-url",
                                "https://payments.example")));

        applicationContext.publishEvent(
                new EnvironmentChangeEvent(
                        applicationContext,
                        Set.of(
                                "payment.retry.max-attempts",
                                "payment.gateway.base-url")));

        assertThat(retryProperties).isSameAs(propertiesReference);
        assertThat(retryProperties.getMaxAttempts()).isEqualTo(4);

        assertThat(paymentEndpointClient).isSameAs(proxyReference);
        assertThat(refreshScope.refresh("paymentEndpointClient")).isTrue();

        assertThat(paymentEndpointClient.targetId())
                .isNotEqualTo(oldTargetId);
        assertThat(paymentEndpointClient.endpoint())
                .isEqualTo("https://payments.example");
    }
}
~~~

Test giả định hai bean `RetryProperties` và `PaymentEndpointClient` được đăng ký như các ví dụ trước, tên bean của client là `paymentEndpointClient`, và ứng dụng có Spring Cloud Context. Nó phát sự kiện trực tiếp để tập trung kiểm tra hai cơ chế; trong production, nên kiểm thử thêm đường đi đầy đủ qua `ContextRefresher`/Actuator hoặc Spring Cloud Bus.

### 11.1. Ma trận test bổ sung

| Trường hợp | Kết quả cần kiểm tra |
| --- | --- |
| Rebind một bean mutable | Instance giữ nguyên; giá trị property được cập nhật |
| Rebind nhiều field liên quan | Reader đồng thời có thể quan sát trạng thái trung gian; xác định có chấp nhận được không |
| Xóa một property | Kiểm tra default/reset và trường hợp bean không thể reset |
| Bean constructor-bound | Không kỳ vọng rebinding tại chỗ hoạt động |
| Refresh target đã được tạo | Target cũ bị destroy; target mới được tạo khi truy cập |
| Refresh target chưa được gọi | Không cần target mới ngay; lần gọi đầu tạo target |
| Target mới khởi tạo lỗi | Health/log ghi nhận lỗi; có kế hoạch khôi phục cấu hình |
| Nhiều replica | Tất cả instance nhận cùng version sau Bus/rollout |
| AOT/native | Refresh bị tắt và chiến lược restart được xác minh |

## 12. Chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `@ConfigurationProperties` không đổi | Environment chưa được cập nhật hoặc event không được phát | Kiểm tra PropertySource hiệu lực và `EnvironmentChangeEvent` |
| Một field đổi nhưng field khác vẫn cũ | Key không có trong Environment, bind lỗi hoặc reset default không thực hiện được | Kiểm tra `ConfigurationPropertiesRebinder` errors và điều kiện constructor |
| Bean có cùng identity sau refresh | Đây là hành vi mong đợi của rebinding | Kiểm tra giá trị getter thay đổi |
| Bean `@RefreshScope` vẫn trả endpoint cũ | Code đang giữ bản sao ngoài proxy hoặc chưa invalidate target | Kiểm tra mọi reference và `refresh(beanName)` |
| Proxy identity thay đổi | Consumer hoặc context bị tạo lại; có thể đang so sánh target thay vì proxy | Kiểm tra scope, context lifecycle và vị trí inject |
| Endpoint refresh trả về nhưng target chưa mới | Chưa có lời gọi qua proxy hoặc target mới lỗi khi khởi tạo | Gọi bean và kiểm tra log/lifecycle/health |
| Một replica chưa nhận cấu hình | Refresh chỉ chạy trên một JVM | Kiểm tra Bus event hoặc quy trình gọi từng instance |
| Hikari pool không được thay | Nằm trong danh sách never-refreshable | Kiểm tra implementation và kế hoạch thay pool |

## 13. Quy trình lựa chọn và vận hành

Trước khi quyết định dùng cơ chế nào, trả lời các câu hỏi:

1. Bean chỉ chứa giá trị cấu hình có thể bind lại, hay nó đã tạo client/tài nguyên từ các giá trị đó?
2. Reader có chấp nhận thấy các field thay đổi tại chỗ trong một khoảng thời gian ngắn không?
3. Có cần một target mới để chạy constructor, dependency injection và lifecycle callback không?
4. Target có state nào sẽ mất khi bị hủy không? State đó có được lưu ở nơi khác không?
5. Thay đổi có cần áp dụng cho nhiều bean hoặc nhiều replica cùng lúc không?
6. Có thể rollback nếu target mới không khởi tạo được không?

Một quy trình production có thể gồm:

- Phát hành cấu hình có version/label rõ ràng.
- Xác thực Config Server và caller có quyền đọc/cập nhật cấu hình.
- Đưa PropertySource mới vào Environment.
- Phát sự kiện để rebind bean cấu hình và cập nhật logger.
- Invalidate target cache cho bean cần tạo lại.
- Kích hoạt đường gọi an toàn để target mới được tạo.
- Kiểm tra health, error rate, latency và trạng thái từng replica.
- Nếu có lỗi, khôi phục version trước và chạy lại quy trình refresh hoặc rollout.

Không coi HTTP 200 từ `/actuator/refresh` là bằng chứng mọi cấu hình và tài nguyên đã được áp dụng thành công. Cần quan sát cả rebinding errors, refresh scope health indicator và kết quả khởi tạo target ở lần sử dụng tiếp theo.

## 14. Tổng kết

Rebinding và Refresh Scope giải quyết hai nhu cầu khác nhau trong quy trình làm mới cấu hình. Rebinding dùng `EnvironmentChangeEvent` để cập nhật các bean `@ConfigurationProperties` ngay trên instance hiện hữu. Refresh Scope giữ proxy ổn định nhưng hủy target đang cache, sau đó tạo target mới khi có lời gọi tiếp theo.

Rebinding nhẹ hơn và phù hợp với cấu hình mutable, nhưng reader đồng thời có thể thấy trạng thái đang được cập nhật. Refresh Scope phù hợp khi bean cần khởi tạo lại từ cấu hình mới và cung cấp cơ chế phối hợp đọc/refresh theo từng bean; nó vẫn không phải transaction nguyên tử cho toàn application context hoặc toàn cluster.

Trong một lần `ContextRefresher.refresh()`, Spring Cloud có thể cập nhật Environment, phát `EnvironmentChangeEvent` để rebind, rồi invalidate Refresh Scope. Hãy chọn bean nào cần cập nhật tại chỗ, bean nào cần tạo lại, kiểm thử cả hai vòng đời và chuẩn bị phương án xử lý lỗi trước khi dùng refresh trong production.

## Tài liệu tham khảo

- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `EnvironmentChangeEvent`, rebinding `@ConfigurationProperties`, concurrency, `@RefreshScope`, HikariDataSource, constructor binding và AOT/native.
- [ConfigurationPropertiesRebinder source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/properties/ConfigurationPropertiesRebinder.java): listener cho `EnvironmentChangeEvent` và cơ chế rebind bean.
- [ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java): cập nhật Environment, tính key thay đổi, phát event và gọi `refreshAll()`.
- [RefreshScope source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java): hủy target theo tên, refresh toàn scope và lifecycle callback.

Đối chiếu tài liệu với release train Spring Cloud đang dùng. Chi tiết reset nested properties, bean không thể rebind và hành vi AOT có thể thay đổi theo phiên bản.
