# RequestInterceptor và truyền ngữ cảnh người gọi

Trong **Spring Cloud OpenFeign**, ứng dụng thường khai báo một interface `@FeignClient(name = "inventory-service")` để gọi dịch vụ theo service ID. Spring Cloud LoadBalancer có thể chọn một `ServiceInstance` phù hợp từ discovery, nhưng không tự xác định những thông tin nào về **người gọi** phải được gửi đến downstream. Ví dụ, inventory-service có thể cần correlation ID để nối log, một danh tính ứng dụng đã xác thực, locale hoặc tenant được cấp quyền.

`feign.RequestInterceptor` cho phép ứng dụng sửa `RequestTemplate` trước khi Feign thực hiện HTTP request. Nó phù hợp để gắn metadata **được cho phép**, nhưng không phải cơ chế xác thực người dùng, không thay thế tracing chuyên dụng và không tự chọn instance.

Mục tiêu bài học là hiểu cách cấu hình interceptor **theo Feign client**, cách chuyển ngữ cảnh trong Spring MVC và các luồng không có servlet request, cách tránh rò rỉ bearer token, cách phối hợp với Spring Cloud LoadBalancer và cách kiểm thử nội dung outbound request.

## 1. RequestInterceptor là gì?

Feign cung cấp interface đơn giản:

~~~java
package feign;

public interface RequestInterceptor {
    void apply(RequestTemplate template);
}
~~~

`RequestTemplate` mô tả method, URL, headers, query và body của lời gọi đang được Feign chuẩn bị. Interceptor có thể thay đổi request template, ví dụ:

~~~java
import feign.RequestInterceptor;
import feign.RequestTemplate;

public final class ServiceIdentityInterceptor
        implements RequestInterceptor {

    @Override
    public void apply(RequestTemplate template) {
        template.header("X-Calling-Service", "order-service");
    }
}
~~~

| Thành phần | Trách nhiệm |
|---|---|
| `RequestTemplate` | Đại diện request cần gửi đi, chưa phải HTTP response |
| `RequestInterceptor.apply` | Bổ sung/điều chỉnh template trong quá trình chuẩn bị lời gọi |
| Feign encoder | Chuyển DTO và dữ liệu đầu vào thành HTTP body/headers theo contract |
| Feign HTTP client | Thực hiện transport và nhận response |
| Spring Cloud LoadBalancer | Dùng service ID để chọn instance đích khi tích hợp load balancing |

Interceptor **không nhận `ClientHttpResponse`** như RestTemplate interceptor; không phải nơi đo chính xác status/body response. Nó cũng không tự biết instance nào vừa được LoadBalancer chọn. Nếu interceptor ném exception trong `apply`, lời gọi có thể thất bại **trước khi** HTTP request đến backend.

Các interceptor thường là singleton hoặc được tái sử dụng giữa nhiều thread. Không lưu `currentUser`, `tenantId`, token hay request ID vào field mutable của interceptor.

## 2. Vị trí của RequestInterceptor trong OpenFeign + LoadBalancer

Giả sử caller `order-service` gọi inventory bằng URI logic, trong khi discovery cung cấp hai bản sao:

~~~text
Service ID: inventory-service

ServiceInstance:
  inventory-1 -> localhost:8081
  inventory-2 -> localhost:8082

@FeignClient(name = "inventory-service")
        |
        v
Feign tạo RequestTemplate
        |
        v
RequestInterceptor gắn correlation ID, token...
        |
        v
Feign Client kết hợp Spring Cloud LoadBalancer
        |
        v
Chọn một ServiceInstance và gửi HTTP request
~~~

~~~mermaid
flowchart LR
    A["OrderService"] --> B["@FeignClient inventory-service"]
    B --> T["RequestTemplate"]
    T --> R["RequestInterceptor"]
    R --> C["Feign + LoadBalancer Client"]
    D["Discovery / supplier"] --> C
    C --> S["ServiceInstance được chọn"]
    S --> H["HTTP transport"]
~~~

Ví dụ caller tạo request `GET /api/items/SKU-001`; interceptor gắn `X-Correlation-Id`, sau đó LoadBalancer chọn `inventory-2`. Header được gửi đến instance đã chọn. Interceptor không cần và không nên tự sửa hostname thành `localhost:8082`.

Muốn biến đổi request **dựa trên metadata của instance đã được chọn**, Spring Cloud OpenFeign có điểm mở rộng khác là `LoadBalancerFeignRequestTransformer`. Đây là trường hợp khác với RequestInterceptor vì lúc đó đã có `ServiceInstance` cụ thể.

Khi sử dụng `@FeignClient(url = "...")` hoặc URL cố định qua cấu hình, Feign thường gọi URL đó trực tiếp thay vì chọn instance theo service ID của Spring Cloud LoadBalancer. Hạ tầng DNS, proxy hoặc VIP vẫn có thể cân bằng tải ở tầng khác.

## 3. Ba loại thông tin thường gọi là ngữ cảnh người gọi

| Loại | Ví dụ | Có được dùng trực tiếp để cấp quyền? |
|---|---|---|
| Danh tính dịch vụ gọi | `order-service` | Không, nếu chỉ là header văn bản; phải có credential/mTLS phù hợp |
| Danh tính người dùng cuối | JWT/opaque token của user | Chỉ khi downstream xác thực token và kiểm tra quyền |
| Ngữ cảnh request | `X-Correlation-Id`, locale, trace ID | Không; phục vụ truy vết và xử lý ngữ cảnh |

Một request đến `order-service` có thể xuất phát từ user thật, một scheduled job hoặc message listener. Không thể giả định mọi lời gọi Feign đều tồn tại `HttpServletRequest` hiện tại.

Ví dụ, header `X-Tenant-Id: tenant-A` nếu do người dùng tự điền chỉ là input chưa tin cậy. Nếu cần truyền tenant để kiểm soát truy cập, ứng dụng phải lấy tenant từ authentication đã được xác minh, kiểm tra quyền và downstream vẫn phải làm authorization.

## 4. Chỉ chuyển các header đã được phê duyệt

| Header/ngữ cảnh | Chính sách khuyến nghị |
|---|---|
| `X-Correlation-Id` | Được phép nếu đã validate/chuẩn hóa độ dài và định dạng |
| `Accept-Language` | Chuyển khi cần locale và đã giới hạn giá trị |
| `X-Tenant-Id` | Chỉ lấy từ nguồn đã xác thực, không relay raw từ client |
| `Authorization` | Chỉ chuyển với token relay/exchange có audience, scope và policy hợp lệ |
| `traceparent` và `tracestate` | Để Micrometer Tracing/OpenTelemetry quản lý |
| `Cookie`, `Host`, `Connection`, `Content-Length` | Không sao chép máy móc giữa các services |
| Header nhạy cảm khác | Mặc định không chuyển trừ khi có nhu cầu đã phê duyệt |

Tránh code theo kiểu lấy toàn bộ `HttpServletRequest.getHeaderNames()` rồi đưa hết vào `RequestTemplate`. Cách đó có thể rò token/cookie, tạo request không hợp lệ và khiến downstream tin nhầm ngữ cảnh do client tự khai.

## 5. Khởi tạo Feign client trong Spring Cloud

Dependency Maven trong caller:

~~~xml
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng Spring Boot BOM và Spring Cloud BOM tương thích với nhau. Có thể cần tích hợp Eureka/Consul/Kubernetes hoặc nguồn discovery khác nếu không dùng danh sách instance tĩnh.

~~~java
package com.example.order;

import com.example.feign.client.InventoryFeignClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(clients = InventoryFeignClient.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Feign client:

~~~java
package com.example.feign.client;

import com.example.feign.config.InventoryFeignConfiguration;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(
        name = "inventory-service",
        configuration = InventoryFeignConfiguration.class
)
public interface InventoryFeignClient {

    @GetMapping("/api/items/{sku}")
    InventoryResponse findBySku(@PathVariable("sku") String sku);
}
~~~

Response DTO:

~~~java
package com.example.feign.client;

public record InventoryResponse(
        String sku,
        int available,
        String instanceId
) {
}
~~~

`name = "inventory-service"` là service ID đích. `contextId`, nếu được khai báo, chủ yếu giúp phân biệt Feign client context/bean, không nên nhầm với danh tính ứng dụng caller.

## 6. Đăng ký RequestInterceptor theo một Feign client

Giữ lớp cấu hình interceptor **ngoài package component scan** của `com.example.order`:

~~~text
com.example.order
    OrderApplication
    web/IncomingCorrelationFilter

com.example.feign.client
    InventoryFeignClient
    InventoryResponse

com.example.feign.config
    InventoryFeignConfiguration
~~~

Mã cấu hình:

~~~java
package com.example.feign.config;

import feign.RequestInterceptor;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;

public class InventoryFeignConfiguration {

    @Bean
    RequestInterceptor inventoryContextInterceptor() {
        return template -> {
            String id = MDC.get("correlationId");

            if (id != null && !id.isBlank()) {
                template.header("X-Correlation-Id", id);
            }

            template.header("X-Calling-Service", "order-service");
        };
    }
}
~~~

`InventoryFeignConfiguration` được import vào context của `@FeignClient(configuration = ...)`, không được component scan như cấu hình global. Một bean `RequestInterceptor` đặt trong ApplicationContext cha có thể ảnh hưởng nhiều Feign client hơn dự định. Điều này đặc biệt nguy hiểm với interceptor thêm `Authorization` dành riêng cho inventory.

Nếu dùng cấu hình bằng properties, Spring Cloud OpenFeign có hỗ trợ `requestInterceptors` theo client trong các release train tương ứng:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 1500
            readTimeout: 3000
            loggerLevel: basic
            requestInterceptors:
              - com.example.feign.interceptor.InventoryContextInterceptor
~~~

Với interceptor cần injected dependencies, cách khai báo `@Bean` trong cấu hình client thường minh bạch hơn. Không đăng ký cùng interceptor đồng thời ở bean và property nếu chưa xác minh nó có bị áp dụng hai lần.

## 7. Tạo Correlation ID từ request vào

Trong Spring MVC caller, có thể dùng `OncePerRequestFilter` để lấy một correlation ID hợp lệ, tự sinh ID nếu thiếu hoặc sai định dạng, đưa vào MDC và phản hồi qua header.

~~~java
package com.example.order.web;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class IncomingCorrelationFilter extends OncePerRequestFilter {

    private static final Pattern UUID_PATTERN = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String incoming = request.getHeader("X-Correlation-Id");
        String id = incoming != null && UUID_PATTERN.matcher(incoming).matches()
                ? incoming : UUID.randomUUID().toString();

        String previous = MDC.get("correlationId");
        MDC.put("correlationId", id);
        response.setHeader("X-Correlation-Id", id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    }
}
~~~

Luồng:

~~~mermaid
sequenceDiagram
    participant U as HTTP Client
    participant O as OrderService
    participant F as Feign RequestInterceptor
    participant L as LoadBalancer
    participant I as Inventory

    U->>O: GET /orders/stock + X-Correlation-Id
    Note over O: Validate/generate ID; MDC.put
    O->>F: InventoryFeignClient.findBySku
    Note over F: Đọc MDC; gắn X-Correlation-Id
    F->>L: Feign request + service ID
    L-->>F: Chọn ServiceInstance
    F->>I: GET /api/items + correlation header
    I-->>O: HTTP response
    Note over O: MDC được restore/clear trong finally
    O-->>U: Response + X-Correlation-Id
~~~

ID từ client không nhất thiết đáng tin cậy. Có hệ thống luôn phát UUID mới ở edge để tránh spoofing; việc cho phép một ID hợp lệ từ client cần dựa trên chính sách ingress.

Dọn MDC trong `finally` là bắt buộc: Spring MVC dùng thread pool, nếu giữ ID cũ có thể làm log của request kế tiếp bị trộn.

## 8. Ngữ cảnh ở thread khác: @Async, scheduled job, message listener

`MDC` thường dùng ThreadLocal. Interceptor ở ví dụ đọc `MDC.get` từ thread chạy Feign. Với một lời gọi blocking trên cùng servlet thread, giá trị có thể sẵn. Nhưng khi:

- Method `@Async` chạy ở executor riêng;
- Scheduled task gọi Feign không có inbound servlet request;
- Kafka/RabbitMQ listener xử lý message;
- Reactive pipeline chuyển execution thread;
- Context servlet đã kết thúc;

thì MDC hoặc `RequestContextHolder` có thể rỗng. Không nên tự bật `InheritableThreadLocal` trong thread pool như giải pháp chung vì ngữ cảnh có thể rò sang tác vụ của request khác.

Giải pháp phù hợp là **truyền context tường minh** cùng message/command, dùng `TaskDecorator` có snapshot/restore, hoặc khởi tạo correlation ID tại boundary của job/message consumer. Với Reactor, sử dụng Reactor `Context` và integration context propagation phù hợp, không cho rằng ThreadLocal tự hoạt động.

Đừng lưu correlation ID gần nhất trong biến của singleton interceptor để “dùng lại”; đó là rò dữ liệu xuyên request.

## 9. RequestContextHolder có dùng được không?

Có thể đọc request đang gắn với thread servlet:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

RequestAttributes attrs = RequestContextHolder.getRequestAttributes();

if (attrs instanceof ServletRequestAttributes servletAttrs) {
    HttpServletRequest incoming = servletAttrs.getRequest();
    String rawId = incoming.getHeader("X-Correlation-Id");

    // Chỉ chuyển một header nếu đã validate, chuẩn hóa.
}
~~~

Đây là kỹ thuật chỉ phù hợp khi thật sự có servlet request gắn với thread hiện tại. Nó không thay thế một mô hình context propagation giữa nhiều kiểu workload. Nếu dùng, phải xử lý trường hợp `attrs == null` và tuyệt đối không tự động copy mọi incoming headers.

Một cấu trúc context bất biến giúp phân biệt dữ liệu đã được kiểm tra khỏi header thô:

~~~java
public record CallerContext(
        String correlationId,
        String tenantId,
        String locale
) {
}
~~~

Có thể tạo `CallerContext` sau ingress authentication/validation rồi truyền qua các layer, hoặc dùng context holder có lifecycle rõ ràng được dọn sau khi xử lý.

## 10. Tenant và quyền truy cập không được lấy từ header tùy ý

Một client có thể tự gửi:

~~~http
X-Tenant-Id: tenant-admin
~~~

Nếu caller relay giá trị này nguyên trạng và inventory tin nó để phân quyền, hệ thống có nguy cơ truy cập chéo tenant. Tenant nên được suy ra từ danh tính đã xác thực hoặc quyền đã được kiểm tra.

~~~text
Incoming request
  -> Spring Security xác thực identity
  -> Kiểm tra tenant user được quyền truy cập
  -> Tạo TrustedCallerContext
  -> Feign RequestInterceptor truyền tenant đã duyệt
  -> Inventory vẫn xác thực và kiểm tra quyền
~~~

Nếu ứng dụng dùng JWT resource server, có thể lấy tenant ID từ claim của `JwtAuthenticationToken` **sau khi** JWT được xác thực và quyền được kiểm tra. Không nên coi bất cứ claim nào cũng có thể dùng làm bằng chứng quyền mà không có chính sách authorization.

Header `X-Tenant-Id` có thể hữu ích cho routing hoặc logging, nhưng không thay thế access token được downstream xác minh. Tương tự, `X-Calling-Service` là metadata; chỉ token, mTLS hoặc workload identity đã được xác thực mới chứng minh danh tính dịch vụ.


## 11. Phân biệt client credentials và token relay

“Truyền ngữ cảnh người gọi” không có nghĩa **luôn chuyển nguyên access token của người dùng cuối**. Có ít nhất hai mô hình:

| Nhu cầu | Danh tính cần có ở inventory | Phương án phù hợp |
|---|---|---|
| Order service tự đồng bộ dữ liệu tồn kho | Danh tính **ứng dụng order-service** | OAuth2 `client_credentials` hoặc workload identity |
| Inventory cần thực hiện nghiệp vụ theo quyền người dùng | Danh tính **user cuối** | Token relay hoặc token exchange có chính sách rõ ràng |
| Chỉ cần nối các dòng log | Correlation/trace ID | Header quan sát; không cấp quyền |

Đây là anti-pattern:

~~~java
// Không dùng mặc định cho tất cả downstream!
template.header(
        "Authorization",
        incomingServletRequest.getHeader("Authorization")
);
~~~

Token của user có thể chỉ được cấp cho gateway/order-service, với audience không hợp lệ ở inventory. Sao chép token không có kiểm soát vừa gây rò credential, vừa khiến downstream nhận quyền không đúng. Nếu cần user delegation, xác định rõ audience, scope, thời hạn, token exchange và cách xác minh ở service đích.

Cũng không nên dùng `X-User-Id` hoặc `X-Role` do request ngoài cung cấp như chứng cứ bảo mật. Các header đó có thể hữu ích về mặt ngữ cảnh sau khi validation, nhưng quyền truy cập vẫn phải được hệ thống security kiểm chứng.

## 12. OAuth2 client credentials với Spring Cloud OpenFeign

Spring Cloud OpenFeign có tích hợp OAuth2 client. Khi có dependency/bean tương ứng, có thể bật hỗ trợ này để framework quản lý access token thay vì tự viết logic request token thủ công.

Ví dụ `application.yml`:

~~~yaml
spring:
  cloud:
    openfeign:
      oauth2:
        enabled: true
        clientRegistrationId: inventory-client

  security:
    oauth2:
      client:
        registration:
          inventory-client:
            provider: internal-idp
            client-id: order-service
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          internal-idp:
            token-uri: https://identity.internal/oauth2/token
~~~

Thêm dependency OAuth2 client vào caller:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Đây chỉ là mô hình minh họa. `INVENTORY_CLIENT_SECRET` phải được nạp từ biến môi trường hoặc secret store; không đưa giá trị thật vào source code. Service đích cần có resource-server authentication hoặc cơ chế kiểm tra token phù hợp; phát token tại caller không đồng nghĩa inventory tự tin cậy token đó.

Khi bật hỗ trợ OAuth2, Spring Cloud OpenFeign có thể cấu hình `OAuth2AccessTokenInterceptor` để gắn `Authorization`. Một số tùy chọn của cơ chế này có **phạm vi ứng dụng**. Nếu nhiều Feign clients cần audience và registration khác nhau, phải kiểm tra phạm vi trước khi bật một registration ID dùng chung.

**Không đồng thời dùng OAuth2 interceptor tự động và một RequestInterceptor tùy chỉnh cũng gắn Authorization** cho cùng client nếu chưa thiết kế quy tắc rõ ràng. Điều đó có thể khiến header bị ghi đè hoặc tạo nhiều giá trị không mong muốn.

## 13. Khi cần OAuth2 interceptor riêng cho từng client

Nếu built-in OAuth2 support không phù hợp với cấu hình nhiều downstream, có thể dùng `OAuth2AuthorizedClientManager` và một `RequestInterceptor` riêng cho inventory.

Với luồng service-to-service không có servlet user, nên dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng provider hỗ trợ `client_credentials`:

~~~java
package com.example.order.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class OutboundOAuth2Configuration {

    @Bean
    OAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clientService) {

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations,
                        clientService
                );

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Sau đó khai báo interceptor:

~~~java
package com.example.feign.config;

import feign.RequestInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public class InventoryOAuth2FeignConfiguration {

    @Bean
    RequestInterceptor inventoryBearerTokenInterceptor(
            OAuth2AuthorizedClientManager manager) {

        return template -> {
            var authorizeRequest = OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory-client")
                    .principal("order-service")
                    .build();

            var client = manager.authorize(authorizeRequest);

            if (client == null || client.getAccessToken() == null) {
                throw new IllegalStateException(
                        "Cannot obtain inventory-service token"
                );
            }

            template.header(
                    "Authorization",
                    "Bearer " + client.getAccessToken().getTokenValue()
            );
        };
    }
}
~~~

Đây là **phương án thay thế** cho auto-configured OAuth2 interceptor. Trường hợp này phải không bật hai cơ chế Authorization cùng lúc. Tham chiếu class từ `@FeignClient(configuration = ...)` hoặc gộp bean vào `InventoryFeignConfiguration`; không để class cấu hình per-client bị component scan thành global.

Những chi tiết vận hành cần nhớ:

- Manager có thể tái sử dụng authorized client và lấy token mới theo nhu cầu; không tự gọi token endpoint cho mọi request nếu không cần.
- Client secret, access token và header Authorization không được đưa vào log.
- Nếu token server chậm hoặc lỗi, Feign call có thể thất bại **trước khi** request đến inventory; phải quan sát riêng loại lỗi này.
- Token phải có scope/audience phù hợp. Inventory vẫn cần validate token và kiểm tra quyền.
- Interceptor chạy trên đường request **blocking** của Feign; việc xin token qua mạng có thể làm tăng tổng độ trễ, nên cấu hình timeout cho token endpoint.
- Không dùng singleton mutable state để giữ token hiện tại; để OAuth2 manager/client service quản lý lifecycle.

## 14. Nhiều RequestInterceptor và thứ tự áp dụng

Feign có thể có nhiều `RequestInterceptor` cho một client. Không nên dựa vào thứ tự ngẫu nhiên của collection interceptor để quyết định ai sẽ ghi đè `Authorization`, `X-Tenant-Id` hoặc `X-Correlation-Id`.

Các nguyên tắc:

- Một header nhạy cảm có **một chủ sở hữu rõ ràng**.
- Nếu có nhiều bước phụ thuộc nhau, dùng một composite interceptor với thứ tự được viết và kiểm thử cụ thể.
- Không kỳ vọng `template.header(...)` luôn có semantics ghi đè chính xác như bạn mong đợi trong mọi phiên bản Feign. Hãy kiểm tra template thực tế khi có header trùng.
- Nếu cần ký request bằng HMAC, không tự ký khi body/query chưa được canonicalize đúng; chọn điểm mở rộng hỗ trợ thao tác chữ ký chính xác.
- Tách context mang tính quan sát khỏi context mang tính phân quyền.

Ví dụ bảng sở hữu:

| Dữ liệu | Thành phần sở hữu |
|---|---|
| `X-Correlation-Id` | Caller context/Correlation RequestInterceptor |
| `Authorization` | Một OAuth2/token interceptor phù hợp |
| Tenant ID | Trusted caller context tạo sau authentication |
| `traceparent` | Micrometer Tracing/OpenTelemetry |
| Host/port instance | Spring Cloud LoadBalancer/Feign HTTP client |
| Response status | Feign client/decoder/ErrorDecoder/observability |

Không nhất thiết đặt mọi header bằng RequestInterceptor. Nếu một method chỉ cần `X-Feature-Flag` riêng, tham số `@RequestHeader` của method có thể rõ ràng hơn. Tránh biến interceptor global thành nơi tập trung mọi logic nghiệp vụ.

## 15. Distributed tracing, logging và MDC

Correlation ID là một khóa để liên kết log. Nó **không giống** trace ID/span ID. Khi ứng dụng có Spring Boot Actuator + Micrometer Observation/Tracing và OpenFeign instrumentation phù hợp, framework có thể tạo span và truyền trace context theo chuẩn W3C qua các header như `traceparent`.

Không tự tạo `traceparent` bằng một UUID trong RequestInterceptor: header tracing có format, sampling flag và quan hệ parent-child riêng.

Ba tầng quan sát:

~~~text
Log ở order-service:
  correlationId = 4f6e...
  Feign client = inventory-service
  method = GET
  outcome = success/error

Tracing:
  traceId / spanId được instrumentation quản lý

LoadBalancer lifecycle:
  serviceId = inventory-service
  instance được chọn (khi metric/tracing thích hợp)

Log ở inventory-service:
  correlationId = 4f6e...
  instanceId = inventory-2
  status = 200
~~~

Không đưa access token, client secret, cookie hoặc full request body vào log. Cẩn thận với Feign `Logger.Level.FULL` vì nó có thể ghi headers và body. Ngay cả `BASIC` cũng có thể log URL chứa query nhạy cảm.

Một cấu hình thận trọng:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            loggerLevel: basic
~~~

Nếu bật debug logging cho Feign, hãy xem chính sách masking/redaction và quyền truy cập log sink. Metrics nên dùng nhãn có cardinality được kiểm soát; không gắn raw user ID hoặc SKU động làm metric label.

## 16. Retry có thể làm số lần thực thi interceptor khác kỳ vọng

OpenFeign hỗ trợ `Retryer` và có thể tích hợp với cơ chế retry ở Spring Cloud LoadBalancer hoặc tầng resilience khác. Spring Cloud OpenFeign thường đăng ký `Retryer.NEVER_RETRY` theo mặc định, khác với một số hành vi retry của Feign lõi. Khi dự án cấu hình retry riêng, mọi giả định phải được kiểm tra lại.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant F as Feign RequestInterceptor
    participant L as LoadBalancer/Retry
    participant A as Inventory A
    participant B as Inventory B

    O->>F: findBySku("SKU-001")
    Note over F: Gắn token và correlation ID
    F->>L: HTTP request theo service ID
    L->>A: Attempt đầu tiên
    A--xL: Timeout
    Note over L: Retry nếu có policy và đủ điều kiện
    L->>B: Attempt tiếp theo
    B-->>L: 200 OK
    L-->>O: Trả DTO
~~~

Tùy cơ chế retry và lớp mà retry bao quanh, Feign có thể dựng template lại hoặc áp dụng RequestInterceptor nhiều lần. **Không dùng RequestInterceptor làm bộ đếm một logical business call**. Nếu cần đếm logical call, đo tại service method; nếu cần đếm attempts, dùng HTTP client, retry listener hoặc LoadBalancer lifecycle instrumentation.

Một số lưu ý quan trọng:

- Correlation ID của cùng business request nên giữ nguyên giữa các attempts.
- Token provider cần cache token phù hợp, không xin lại vô điều kiện mỗi attempt.
- Retry POST thanh toán hoặc thao tác ghi có thể gây side effect trùng; cần idempotency.
- Đừng gọi lại chính Feign client từ RequestInterceptor để tự retry; dễ gây recursive calls và khó kiểm soát timeout.

## 17. Timeout và lỗi không thuộc trách nhiệm của RequestInterceptor

Ví dụ cấu hình timeout:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 1500
            readTimeout: 3000
~~~

Các giá trị thông dụng trên được diễn giải bằng **mili giây** trong cấu hình OpenFeign tương ứng. Connect timeout liên quan thiết lập kết nối; read timeout liên quan thời gian chờ đọc response. Chúng không luôn giới hạn *tổng thời gian* gồm token acquisition, discovery, retry, backoff và xử lý nghiệp vụ.

| Mối quan tâm | Điểm cấu hình phù hợp |
|---|---|
| Token acquisition | Spring Security OAuth2 client/identity provider |
| Correlation ID, ngữ cảnh người gọi | RequestInterceptor và caller context provider |
| Danh sách instance và health check | Discovery/`ServiceInstanceListSupplier` |
| Chọn instance | Spring Cloud LoadBalancer |
| Connect/read timeout | Feign client/HTTP transport |
| Retry/backoff | Feign Retryer, LoadBalancer retry hoặc resilience layer |
| HTTP error mapping | Feign ErrorDecoder và xử lý lỗi nghiệp vụ |
| Metrics/tracing | Micrometer/Feign/LoadBalancer instrumentation |

Khi một Feign call trả 503, có thể là không có instance, backend lỗi hoặc hạ tầng trả response; cần phân loại từ log/metrics và nguồn discovery. Không sửa request header để “chữa” một instance đã chết.


## 18. Unit test RequestInterceptor

Không cần chạy HTTP server để kiểm tra cách interceptor gắn header. Có thể tạo `RequestTemplate` và gọi `apply` trực tiếp.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import feign.RequestInterceptor;
import feign.RequestTemplate;
import java.util.Collection;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class CorrelationInterceptorTest {

    @Test
    void addsIdWhenMdcContainsCorrelationId() {
        String id = "c2c6380a-5f8d-4cc4-b244-08f1c64380cb";
        MDC.put("correlationId", id);

        try {
            RequestInterceptor interceptor = template -> {
                String value = MDC.get("correlationId");

                if (value != null && !value.isBlank()) {
                    template.header("X-Correlation-Id", value);
                }
            };

            RequestTemplate template = new RequestTemplate();
            interceptor.apply(template);

            Collection<String> values =
                    template.headers().get("X-Correlation-Id");

            assertTrue(values != null && values.contains(id));
        } finally {
            MDC.remove("correlationId");
        }
    }
}
~~~

Bổ sung các trường hợp cần test:

1. Không có MDC thì không lấy nhầm correlation ID của request trước.
2. Header người dùng gửi sai định dạng được ingress filter chuẩn hóa hoặc thay thế.
3. Inventory interceptor không xuất hiện trong một Feign client khác dành cho payment.
4. OAuth2 manager không lấy được token thì lời gọi dừng, không gắn bearer token rỗng.
5. Không có hai interceptor cùng chèn `Authorization`.
6. Tenant được truyền phải là giá trị bắt nguồn từ nguồn đã xác thực.
7. Khi gọi từ `@Async`, context được chuyển tường minh hoặc có fallback có chủ đích.

Unit test `RequestTemplate` chỉ kiểm tra phần interceptor, **không chứng minh** tích hợp Spring Cloud LoadBalancer chọn đúng instance. Muốn kiểm tra backend thực nhận request cần integration test.

## 19. Bài thực hành với hai bản sao inventory

Để thử luồng end-to-end, dùng `SimpleDiscoveryClient` khai báo hai instance ở caller:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Chạy cùng ứng dụng inventory ở cổng 8081 và 8082. Mỗi instance cung cấp `GET /api/items/{sku}` trả về `sku`, `available` và `instanceId`, và ghi nhận `X-Correlation-Id` trong log của riêng mình.

Ở caller dùng `InventoryFeignClient` đã tạo và thêm controller:

~~~java
package com.example.order.web;

import com.example.feign.client.InventoryFeignClient;
import com.example.feign.client.InventoryResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderInventoryController {

    private final InventoryFeignClient inventory;

    public OrderInventoryController(InventoryFeignClient inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/orders/stock/{sku}")
    public InventoryResponse stock(@PathVariable String sku) {
        return inventory.findBySku(sku);
    }
}
~~~

Gửi nhiều request từ PowerShell:

~~~powershell
$correlationId = [guid]::NewGuid().ToString()
1..12 | ForEach-Object { Invoke-RestMethod -Uri "http://localhost:8080/orders/stock/SKU-001" -Headers @{ "X-Correlation-Id" = $correlationId } }
~~~

Ví dụ là lab: các service, controller và endpoint phải được triển khai trước khi chạy lệnh. Nếu chưa có identity provider, hãy kiểm tra correlation/context interceptor trước rồi mới bật OAuth2 ở môi trường đã cấu hình bảo mật phù hợp.

Kết quả cần quan sát:

- Phản hồi `instanceId` thuộc `inventory-1` hoặc `inventory-2`; với Round Robin và danh sách ổn định, hai backend thường được phân phối luân phiên theo lần chọn.
- Log của order và inventory dùng cùng correlation ID đã được kiểm tra.
- Không có access token, client secret hoặc cookie trong log.
- Khi dừng một replica, xem discovery, health supplier, timeout và retry trước khi cho rằng RequestInterceptor lỗi.
- Khi thêm một Feign client gọi payment, bảo đảm inventory interceptor không bị đăng ký sang payment.

## 20. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Correlation ID không đến backend | Interceptor không đăng ký hoặc MDC rỗng | Kiểm tra `@FeignClient(configuration=...)`, inbound filter và thread |
| Correlation ID cũ xuất hiện lại | MDC chưa clear hoặc singleton giữ state | Dùng `finally`, test concurrent |
| `@Async` mất caller context | ThreadLocal không tự propagate | Dùng TaskDecorator hoặc truyền context tường minh |
| Token inventory được gửi đến payment | Interceptor bị component scan thành global | Đưa client config ra ngoài scan |
| HTTP 401/403 | Sai token audience/scope hoặc downstream validation | Kiểm tra identity provider và authorization policy |
| Token server lỗi bị hiểu là inventory lỗi | OAuth2 manager thất bại trước HTTP transport | Phân loại lỗi token acquisition riêng |
| Tenant ID bị giả mạo | Copy trực tiếp header tenant từ inbound | Dựa trên authentication đã xác minh |
| `UnknownHostException` với service ID | Chưa tích hợp LoadBalancer hoặc discovery sai | Kiểm tra starter và client name |
| Chỉ một replica nhận request | Supplier chỉ có một ứng viên hoặc health/zone lọc | Kiểm tra tập `ServiceInstance` thực tế |
| RequestInterceptor không thấy host thật | Interceptor chạy trước instance selection | Dùng `LoadBalancerFeignRequestTransformer` khi cần |
| Header Authorization bị trùng | Nhiều interceptor cùng gắn token | Chỉ giữ một chính sách auth cho client |
| Feign FULL log lộ credential | Log headers/body quá chi tiết | Giảm level, redact, hạn chế truy cập log |
| Một business call gửi nhiều HTTP requests | Retry nhiều tầng | Kiểm tra retry budget và idempotency |

## 21. Checklist trước khi triển khai

- [ ] Service ID trong `@FeignClient(name=...)` khớp nguồn `ServiceInstance`.
- [ ] Chỉ truyền context có nhu cầu rõ, dùng allowlist thay vì copy toàn bộ incoming headers.
- [ ] Sinh/validate correlation ID ở ingress và restore/clear MDC trong `finally`.
- [ ] Có chiến lược riêng cho `@Async`, scheduled jobs và message consumers.
- [ ] Interceptor không giữ mutable request state trong singleton.
- [ ] Bean interceptor per-client không bị tự động biến thành global.
- [ ] Không tin user/tenant/role headers do client tự gửi để cấp quyền.
- [ ] Phân biệt token service-to-service và user token relay/exchange.
- [ ] Một client chỉ có một chính sách gắn Authorization.
- [ ] Không hardcode secret, không log token, cookies hoặc body nhạy cảm.
- [ ] Dùng instrumentation của tracing framework cho `traceparent`.
- [ ] Không dùng RequestInterceptor để chọn instance hoặc tự triển khai retry.
- [ ] Nếu cần sửa request theo instance đã chọn, dùng đúng điểm mở rộng ở tầng LoadBalancer.
- [ ] Đặt connect/read timeout, retry budget và idempotency phù hợp.
- [ ] Có unit test RequestTemplate và integration test với hai replica.
- [ ] Theo dõi logical calls và HTTP attempts riêng khi hệ thống có retry.

## Tài liệu tham khảo

- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@FeignClient`, RequestInterceptor, cấu hình client, LoadBalancer, OAuth2 và observability.
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service ID, `ServiceInstance`, discovery, health check và retry.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClientManager`, client credentials và quản lý access token.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics, tracing và context propagation.

**Kết luận:** `RequestInterceptor` giúp OpenFeign đưa **ngữ cảnh đã được phép và chuẩn hóa** vào request để các dịch vụ hiểu được luồng xử lý mà không lặp code ở từng Feign method. Nhưng correlation ID không phải credential, tenant header không mang quyền truy cập, và chuyển access token phải tuân theo scope/audience. Spring Cloud LoadBalancer vẫn chịu trách nhiệm chọn `ServiceInstance`; Feign transport thực hiện HTTP; còn auth, tracing và resilience cần được cấu hình đúng điểm mở rộng, có giới hạn và được kiểm thử.
