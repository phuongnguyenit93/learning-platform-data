# Gắn @RefreshScope vào bean và quan hệ với singleton

> **Chương:** Refresh Scope  
> **Module:** SPRING_CLOUD_CORE

Trong Spring, bean mặc định thường có scope **`singleton`**: mỗi bean definition có một instance dùng chung trong ApplicationContext. Điều này phù hợp với service stateless, repository và nhiều thành phần hạ tầng. Nhưng một số bean giữ giá trị cấu hình được phép thay đổi khi ứng dụng đang chạy, ví dụ endpoint của dịch vụ phụ thuộc, timeout hoặc một nhóm tham số vận hành.

Spring Cloud Context cung cấp **`@RefreshScope`** để quản lý vòng đời của những bean cần được tạo lại sau khi cấu hình được refresh. Cách hoạt động của nó dựa trên **scoped proxy**: các bean khác có thể giữ một tham chiếu proxy ổn định, trong khi target phía sau proxy được hủy và tạo lại khi refresh. Hiểu quan hệ này giúp tránh lỗi phổ biến: singleton vẫn giữ giá trị cũ dù bean cấu hình đã được refresh.

## 1. Singleton là gì và vì sao cấu hình có thể bị giữ cũ?

Khi một bean Spring không khai báo scope khác, scope mặc định là `singleton`. Spring tạo một instance cho bean definition trong một ApplicationContext và dùng lại instance đó ở các nơi inject.

Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogSettings {

    private final String baseUrl;

    public CatalogSettings(
            @Value("${catalog.client.base-url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

Nếu `CatalogSettings` là singleton mặc định, constructor chạy khi bean được tạo và giá trị `baseUrl` được lưu trong field. Khi nguồn cấu hình bên ngoài thay đổi, Spring không tự gọi lại constructor của singleton đó. Nếu Environment được cập nhật, field đã gán vẫn là giá trị cũ.

Đây là đặc tính bình thường của dependency injection: một giá trị được đọc khi tạo bean không tự biến thành một liên kết động với property source.

### 1.1. Khi nào singleton là lựa chọn đúng?

Singleton phù hợp khi bean:

- Không giữ trạng thái thay đổi theo từng request hoặc từng người dùng.
- Có thể dùng chung an toàn giữa nhiều luồng.
- Không cần được tạo lại chỉ vì một vài thuộc tính cấu hình thay đổi.
- Có vòng đời phù hợp với ApplicationContext.

Phần lớn service nghiệp vụ nên giữ singleton và stateless. Không nên gắn `@RefreshScope` cho mọi bean trong ứng dụng chỉ vì ứng dụng có Config Server. Refresh scope có chi phí quản lý vòng đời và có thể làm mất trạng thái nội bộ của target khi target bị thay thế.

## 2. @RefreshScope là scope riêng có scoped proxy

`@RefreshScope` thuộc Spring Cloud Context, trong package `org.springframework.cloud.context.config.annotation`. Annotation này đánh dấu bean dùng scope `refresh` và tạo proxy để các thành phần khác tương tác với bean.

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogEndpoint {

    private final URI baseUri;

    public CatalogEndpoint(
            @Value("\${catalog.client.base-url}") URI baseUri) {
        this.baseUri = baseUri;
    }

    public URI baseUri() {
        return baseUri;
    }

    public String currentEndpoint() {
        return baseUri.toString();
    }
}
~~~

Khi bean này được inject vào một bean khác, nơi nhận thường giữ **proxy**. Proxy chuyển lời gọi phương thức tới target hiện tại trong refresh scope. Target được quản lý trong cache của scope.

Có thể hình dung:

~~~mermaid
flowchart LR
    S["Singleton bean\nCatalogGateway"]
    P["Scoped proxy\nCatalogEndpoint"]
    C["RefreshScope cache"]
    T["Target hiện tại\nCatalogEndpoint"]
    S -->|"giữ tham chiếu"| P
    P -->|"tra cứu target"| C
    C --> T
    R["Refresh event"] -->|"invalidate target"| C
    C -. "lần gọi tiếp theo tạo target mới" .-> N["Target mới"]
~~~

**Proxy và target là hai đối tượng khác nhau:**

- Proxy là điểm truy cập mà singleton giữ.
- Target là instance thực hiện công việc.
- Refresh scope quản lý target và cache target.
- Khi target bị refresh, proxy vẫn có thể được giữ nguyên; lần gọi tiếp theo lấy target mới.

Trong cách dùng thông thường, refresh-scoped bean được khởi tạo khi lần đầu được gọi qua proxy và target được cache để dùng lại. Khi cache bị làm mới, target cũ bị loại bỏ theo cơ chế scope và target mới được tạo khi có lời gọi tiếp theo.

## 3. Quan hệ giữa singleton và refresh-scoped bean

Giả sử `CatalogGateway` là singleton và inject `CatalogEndpoint` có `@RefreshScope`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {

    private final CatalogEndpoint endpoint;

    public CatalogGateway(CatalogEndpoint endpoint) {
        this.endpoint = endpoint;
    }

    public String endpointForRequest() {
        return endpoint.currentEndpoint();
    }
}
~~~

Ở thời điểm tạo `CatalogGateway`, Spring inject scoped proxy của `CatalogEndpoint`. Singleton giữ tham chiếu tới proxy đó trong suốt vòng đời của nó.

Khi `endpointForRequest()` được gọi, proxy tìm target hiện tại và chuyển tiếp lời gọi. Sau một lần refresh, target cũ bị loại khỏi refresh scope. `CatalogGateway` không cần được tạo lại; lần gọi tiếp theo vẫn đi qua cùng proxy nhưng proxy lấy target mới.

### 3.1. Bảng vòng đời

| Thời điểm | Singleton `CatalogGateway` | Proxy `CatalogEndpoint` | Target refresh-scoped |
| --- | --- | --- | --- |
| Khởi động context | Được tạo | Được inject vào singleton | Có thể chưa được tạo cho tới lần gọi đầu |
| Lần gọi đầu | Giữ nguyên | Chuyển tiếp lời gọi | Được tạo và cache |
| Nhiều lần gọi tiếp | Giữ nguyên | Vẫn là proxy đó | Dùng lại target đã cache |
| Sau refresh | Vẫn là instance cũ | Vẫn là proxy đó | Target cũ bị loại bỏ |
| Lần gọi sau refresh | Vẫn là instance cũ | Tra cứu target mới | Target mới được tạo và cache |

Điểm mấu chốt là **singleton giữ proxy chứ không giữ target trực tiếp**. Đây là lý do một singleton có thể tiếp tục nhìn thấy cấu hình mới mà không phải khởi tạo lại chính singleton đó.

### 3.2. Đừng sao chép giá trị từ proxy vào field singleton

Ví dụ sau dễ tạo ra lỗi stale configuration:

~~~java
import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {

    private final URI baseUri;

    public CatalogGateway(CatalogEndpoint endpoint) {
        // Gọi proxy ngay lúc singleton được tạo và sao chép giá trị.
        this.baseUri = endpoint.baseUri();
    }

    public URI baseUri() {
        return baseUri;
    }
}
~~~

Dù `CatalogEndpoint` là refresh-scoped, `CatalogGateway` đã gọi proxy trong constructor và sao chép URI vào field singleton. Sau refresh, target mới của `CatalogEndpoint` có URI mới, nhưng field `baseUri` trong `CatalogGateway` vẫn giữ giá trị cũ.

Cách đúng là giữ proxy và gọi phương thức lấy cấu hình tại thời điểm cần dùng, hoặc làm cho bean tiêu thụ cấu hình cũng được refresh nếu nó phải xây dựng lại trạng thái nội bộ.

~~~java
import java.net.URI;
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {

    private final CatalogEndpoint endpoint;

    public CatalogGateway(CatalogEndpoint endpoint) {
        this.endpoint = endpoint;
    }

    public URI currentBaseUri() {
        // Gọi qua proxy ở thời điểm sử dụng.
        return endpoint.baseUri();
    }
}
~~~

Không lưu một snapshot của giá trị refresh-scoped vào singleton nếu mong muốn nó thay đổi theo refresh.

## 4. Ví dụ hoàn chỉnh: thay endpoint của catalog khi ứng dụng đang chạy

Giả sử `order-service` gọi `catalog-service`. Endpoint của catalog được quản lý tập trung và có thể đổi theo môi trường hoặc quá trình chuyển hạ tầng.

### 4.1. Khai báo cấu hình ban đầu

`application.yml`:

~~~yaml
spring:
  application:
    name: order-service

catalog:
  client:
    base-url: "https://catalog-v1.internal"
~~~

Giá trị này có thể được ghi đè bởi profile, biến môi trường hoặc Spring Cloud Config theo thứ tự ưu tiên property source.

### 4.2. Tạo bean giữ cấu hình có thể refresh

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
@RefreshScope
public class CatalogEndpoint {

    private final URI baseUri;

    public CatalogEndpoint(
            @Value("${catalog.client.base-url}") URI baseUri) {
        this.baseUri = baseUri;
    }

    public URI baseUri() {
        return baseUri;
    }

    public URI productUri(String productId) {
        return UriComponentsBuilder.fromUri(baseUri)
                .pathSegment("api", "products", productId)
                .build()
                .encode()
                .toUri();
    }
}
~~~

Target của `CatalogEndpoint` đọc `catalog.client.base-url` khi được tạo. Sau khi Environment được cập nhật và refresh scope được refresh, target mới sẽ được tạo với giá trị mới.

### 4.3. Singleton service sử dụng proxy

~~~java
import java.net.URI;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {

    private final WebClient client;
    private final CatalogEndpoint endpoint;

    public CatalogGateway(
            WebClient.Builder builder,
            CatalogEndpoint endpoint) {
        this.client = builder.build();
        this.endpoint = endpoint;
    }

    public Mono<String> findProduct(String productId) {
        return client.get()
                .uri(endpoint.productUri(productId))
                .retrieve()
                .bodyToMono(String.class);
    }

    public URI currentBaseUri() {
        return endpoint.baseUri();
    }
}
~~~

`CatalogGateway` là singleton. Nó giữ `CatalogEndpoint` proxy và gọi `endpoint.productUri(productId)` cho từng request. Khi target endpoint được làm mới, lời gọi qua proxy tiếp theo sẽ lấy URI từ target mới.

Ví dụ giả định ứng dụng đã có `WebClient.Builder` từ cấu hình Spring Boot WebFlux và dependency cần thiết. Trong dự án thực tế, cần cấu hình timeout, error handling, tracing và xác thực cho HTTP client riêng.

### 4.4. Điều gì xảy ra trong quá trình refresh?

Giả sử cấu hình thay đổi từ:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v1.internal"
~~~

sang:

~~~yaml
catalog:
  client:
    base-url: "https://catalog-v2.internal"
~~~

Quy trình khái niệm:

~~~mermaid
sequenceDiagram
    participant Config as Config Server / nguồn cấu hình
    participant Context as Spring Environment
    participant Scope as RefreshScope
    participant Proxy as CatalogEndpoint proxy
    participant Target as CatalogEndpoint target
    participant Gateway as Singleton CatalogGateway

    Config-->>Context: Cấu hình base-url mới
    Context->>Context: Cập nhật property sources
    Context->>Scope: Refresh scope / invalidate target
    Scope->>Target: Hủy target cũ
    Note over Gateway,Proxy: Singleton và proxy vẫn tồn tại
    Gateway->>Proxy: findProduct(...)
    Proxy->>Scope: Lấy target hiện tại
    Scope->>Target: Tạo target mới khi cần
    Target-->>Proxy: URI theo cấu hình mới
    Proxy-->>Gateway: Trả URI mới
~~~

Thứ tự thực tế của bước tải cấu hình, cập nhật Environment và phát refresh event phụ thuộc cơ chế được dùng, ví dụ Spring Cloud Config Client, Actuator refresh endpoint hoặc Spring Cloud Bus. Sơ đồ mô tả quan hệ giữa Environment và refresh scope, không khẳng định một endpoint cụ thể luôn được bật.

## 5. Kích hoạt refresh và vai trò của @RefreshScope

`@RefreshScope` chỉ định bean có scope riêng và có thể được làm mới khi refresh scope nhận lệnh refresh. Annotation **không tự theo dõi file**, không tự polling Config Server và không tự phát hiện thay đổi ở một hệ thống bên ngoài.

Một luồng refresh điển hình gồm:

1. Nguồn cấu hình được cập nhật hoặc Config Client lấy được cấu hình mới.
2. Cơ chế refresh cập nhật Environment/property sources.
3. Refresh scope nhận yêu cầu làm mới và loại bỏ target đang cache.
4. Khi bean được gọi tiếp theo, proxy yêu cầu target mới.
5. Target mới được tạo và bind/resolve giá trị cấu hình hiện tại.

Trong một số ứng dụng có Actuator và Spring Cloud Context, endpoint refresh có thể được bật để nhận thao tác refresh, ví dụ `POST /actuator/refresh`. Endpoint này cần được cấu hình expose, xác thực và phân quyền phù hợp. Nếu dùng Spring Cloud Bus, một sự kiện có thể được phát tới nhiều instance; hành vi và endpoint cụ thể phụ thuộc dependency và cấu hình Bus.

Có thể dùng API `RefreshScope.refreshAll()` trong code quản trị hoặc test để invalidate toàn bộ target thuộc scope. Không gọi refresh tùy tiện trong mỗi request nghiệp vụ; refresh là thao tác quản lý vòng đời và có thể khiến target được tạo lại.

### 5.1. Refresh Environment và refresh bean là hai bước khác nhau

Cần phân biệt:

- **Environment refresh:** nguồn cấu hình được tải lại hoặc property source được cập nhật.
- **Refresh scope:** target của các bean được đánh dấu bị invalidate để có thể tạo lại.
- **Singleton refresh:** singleton mặc định không tự được tạo lại chỉ vì refresh scope chạy.

Nếu chỉ gọi `RefreshScope.refreshAll()` mà không cập nhật Environment, target mới có thể vẫn đọc cùng giá trị cũ. Ngược lại, nếu Environment đã đổi nhưng bean singleton đã lưu snapshot vào field, snapshot đó không tự thay đổi.

## 6. Khi nào nên gắn @RefreshScope?

Nên cân nhắc refresh scope cho bean có những đặc điểm:

- Chứa một nhóm cấu hình cần thay đổi khi ứng dụng đang chạy.
- Có thể tái tạo an toàn từ Environment mới.
- Không giữ trạng thái nghiệp vụ lâu dài cần bảo toàn qua refresh.
- Được truy cập qua proxy từ các thành phần khác.
- Có thể chịu được việc target cũ bị hủy và target mới được tạo khi lần gọi tiếp theo xảy ra.

Ví dụ phù hợp:

| Bean | Lý do có thể refresh |
| --- | --- |
| Client endpoint settings | URL hoặc tham số định tuyến có thể thay đổi |
| Bộ tham số timeout/retry | Cần điều chỉnh chính sách gọi dịch vụ |
| Một client nhẹ được xây dựng từ cấu hình | Có thể tái tạo khi endpoint hoặc credential đổi |
| Bộ cấu hình feature ở cấp ứng dụng | Giá trị được đọc lại từ nguồn cấu hình sau refresh |

Không nên gắn refresh scope một cách mặc định cho:

- Service nghiệp vụ giữ trạng thái của quy trình hoặc giao dịch.
- Repository hoặc bean quản lý transaction có vòng đời phức tạp.
- Bean chứa cache nghiệp vụ lớn mà việc xóa cache sẽ gây mất dữ liệu hoặc tải đột biến.
- Đối tượng giữ thread, scheduler hoặc tài nguyên cần shutdown có kiểm soát mà chưa thiết kế destruction lifecycle.
- Mọi singleton trong ứng dụng chỉ vì muốn “cấu hình tự cập nhật”.

Nếu bean cần tái tạo tài nguyên, hãy kiểm tra callback hủy tài nguyên, đóng connection, dừng scheduler và xử lý request đang chạy trước khi target bị thay thế.

## 7. Quan hệ với bean @Configuration và @Bean

`@RefreshScope` có thể được đặt trên class component hoặc trên phương thức `@Bean`.

Ví dụ dùng bean method:

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogConfiguration {

    @Bean
    @RefreshScope
    CatalogEndpoint catalogEndpoint(
            @Value("${catalog.client.base-url}") URI baseUri) {
        return new CatalogEndpoint(baseUri);
    }
}
~~~

Khi scope được đặt trên bean method, bean được tạo từ method đó là refresh-scoped.

Một điểm dễ nhầm: đặt `@RefreshScope` trên một class `@Configuration` **không có nghĩa mọi bean được khai báo bằng các phương thức `@Bean` bên trong class đó đều tự động có refresh scope**. Nếu một bean cụ thể cần được refresh, hãy đánh dấu chính bean đó bằng `@RefreshScope` hoặc thiết kế scope rõ ràng cho nó.

Cũng cần nhớ rằng singleton khác inject bean refresh-scoped sẽ giữ proxy. Nếu singleton gọi proxy và chỉ sử dụng kết quả ngay lúc đó, nó có thể thấy target mới. Nếu singleton sao chép kết quả vào field hoặc tạo một đối tượng hạ tầng bất biến từ giá trị đó khi khởi tạo, đối tượng snapshot vẫn có thể cũ.

## 8. Những giới hạn và lỗi thường gặp

### 8.1. Environment đã đổi nhưng singleton vẫn cũ

Nguyên nhân thường là singleton đọc property qua `@Value` trong constructor hoặc field injection rồi giữ giá trị. Cách xử lý:

- Đưa nhóm cấu hình vào bean refresh-scoped.
- Inject scoped proxy vào singleton.
- Gọi proxy khi cần giá trị mới.
- Nếu singleton xây dựng một client từ cấu hình, cân nhắc refresh chính client đó hoặc thiết kế client đọc cấu hình qua proxy.

### 8.2. Gắn @RefreshScope nhưng bean không cập nhật

Kiểm tra:

- Có thực sự có thao tác/event refresh được kích hoạt không?
- Environment/property source đã nhận giá trị mới chưa?
- Bean có được tạo trong refresh scope không?
- Consumer đang gọi proxy hay đang giữ target/value đã sao chép?
- Bean có được tạo từ một factory method khác không được đánh dấu refresh scope không?
- Có một singleton phụ thuộc giữ cache hoặc client cũ không?

### 8.3. Mất trạng thái trong bean

Target cũ bị hủy và target mới được tạo. Những field mutable chỉ tồn tại trong target cũ sẽ không tự được chuyển sang target mới. Không đặt trạng thái nghiệp vụ cần bảo toàn vào refresh-scoped bean; hãy lưu trạng thái ở database hoặc một thành phần có vòng đời phù hợp.

### 8.4. Lỗi proxy và class final

Refresh scope thường dùng scoped proxy để chuyển tiếp lời gọi. Proxy class-based có những ràng buộc về khả năng kế thừa; class hoặc method final có thể gây vấn đề tùy loại proxy và cấu hình. Nếu gặp lỗi tạo proxy, kiểm tra log, kiểu bean, interface và proxy mode của phiên bản Spring Cloud đang dùng. Không giả định mọi kiểu Java đều có thể được proxy theo cùng cách.

### 8.5. Refresh đồng thời với request đang chạy

Một request có thể đã bắt đầu gọi target cũ trước khi refresh diễn ra. Không nên giả định refresh sẽ dừng tức thì mọi lời gọi đang chạy. Với client giữ connection hoặc tài nguyên, cần chính sách graceful shutdown, timeout và xử lý lỗi phù hợp để tránh request đang thực thi bị ảnh hưởng.

## 9. Kiểm thử quan hệ giữa singleton, proxy và target

Một test hữu ích nên chứng minh ba điều:

1. Singleton consumer được tạo một lần và giữ proxy.
2. Target ban đầu trả giá trị cấu hình cũ.
3. Sau khi cập nhật Environment và refresh scope, cùng consumer đó nhận giá trị từ target mới.

Ví dụ kiểm thử trong một Spring Boot test context:

~~~java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.core.env.ConfigurableEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "catalog.client.base-url=https://catalog-v1.internal"
})
class RefreshScopeSingletonTest {

    @Autowired
    CatalogGateway gateway;

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void singletonUsesNewTargetAfterRefresh() {
        URI first = gateway.currentBaseUri();

        assertThat(first)
                .isEqualTo(URI.create("https://catalog-v1.internal"));

        TestPropertyValues.of(
                "catalog.client.base-url=https://catalog-v2.internal"
        ).applyTo(environment);

        refreshScope.refreshAll();

        URI second = gateway.currentBaseUri();

        assertThat(second)
                .isEqualTo(URI.create("https://catalog-v2.internal"));
    }
}
~~~

Ví dụ giả định `CatalogGateway` là singleton và giữ `CatalogEndpoint` scoped proxy như phần trước; `CatalogEndpoint` đọc property trong constructor. Test dùng `TestPropertyValues` để cập nhật Environment trước khi gọi `refreshAll()`. Trong một test context cô lập, refresh toàn bộ target thuộc scope là phù hợp; test suite lớn có thể cần tách context để tránh làm mới các bean khác.

Bài kiểm thử này không mô phỏng đầy đủ việc Config Server tải remote config hoặc Spring Cloud Bus phát sự kiện. Nó tập trung vào quan hệ giữa Environment, refresh scope, proxy và singleton consumer.

### 9.1. Các kịch bản kiểm thử bổ sung

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Gọi bean lần đầu | Target được tạo và giá trị cấu hình đúng |
| Gọi nhiều lần trước refresh | Target được tái sử dụng, không tạo mới mỗi lần gọi |
| Cập nhật Environment rồi refresh | Lần gọi sau đọc giá trị mới |
| Refresh khi singleton vẫn sống | Consumer singleton không cần tạo lại |
| Singleton lưu snapshot trong field | Test chứng minh snapshot không tự đổi |
| Target có tài nguyên cần đóng | Destruction callback được thực hiện theo lifecycle đã thiết kế |
| Nguồn cấu hình không đổi nhưng refresh chạy | Target mới vẫn có thể nhận cùng giá trị |
| Environment đổi nhưng không refresh scope | Bean refresh-scoped có thể vẫn dùng target đã cache cho tới khi invalidate |

## 10. Quy trình áp dụng trong ứng dụng Spring Cloud

Khi cần thay đổi một bean theo cấu hình lúc runtime, có thể thực hiện:

1. Xác định chính xác property nào cần thay đổi và nguồn nào cung cấp property đó.
2. Chọn bean nhẹ, có thể tái tạo, không giữ trạng thái nghiệp vụ lâu dài.
3. Gắn `@RefreshScope` lên bean hoặc bean method cần refresh.
4. Để consumer singleton inject scoped proxy thay vì inject một snapshot.
5. Truy cập giá trị qua proxy ở thời điểm sử dụng; tránh sao chép giá trị vào field singleton.
6. Xác định cơ chế cập nhật Environment và phát refresh event.
7. Bảo vệ endpoint/event refresh bằng authentication, authorization và network policy phù hợp.
8. Kiểm thử target cũ, target mới, singleton consumer và lỗi khi refresh.
9. Theo dõi log/metrics để biết refresh có thành công và target được tái tạo đúng lúc.

Nếu một client HTTP hoặc pool được tạo từ cấu hình và không thể đọc giá trị động, hãy đặt chính client đó trong refresh scope hoặc tạo một factory quản lý việc thay thế client có kiểm soát. Không nên chỉ refresh bean chứa chuỗi URL trong khi một singleton khác đã tạo client và lưu URL cũ.

## 11. Kết luận

`@RefreshScope` tạo một scope riêng với scoped proxy để target có thể được invalidate và tạo lại sau khi ứng dụng thực hiện refresh. Khi một singleton inject refresh-scoped bean, singleton giữ proxy ổn định; proxy chuyển lời gọi tới target hiện tại. Vì vậy, singleton có thể tiếp tục sử dụng cấu hình mới mà không cần chính nó được tạo lại.

Điều kiện quan trọng là consumer phải tiếp tục gọi qua proxy. Nếu singleton đọc giá trị một lần rồi sao chép vào field hoặc tạo một client giữ snapshot cũ, refresh target không thể tự cập nhật phần dữ liệu đã sao chép đó. Hãy dùng refresh scope cho bean có thể tái tạo an toàn, phân biệt cập nhật Environment với invalidate target, và kiểm thử cả vòng đời proxy-target lẫn singleton consumer trong ứng dụng **SPRING_CLOUD_CORE**.
