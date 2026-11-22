# Interceptor cho xác thực, ghi nhận và truyền ngữ cảnh

Trong **Spring Cloud LoadBalancer**, ứng dụng gọi một dịch vụ qua service ID như `inventory-service` và LoadBalancer chọn một `ServiceInstance` cụ thể từ discovery. Khi dùng `RestTemplate`, các yêu cầu chung như xác thực dịch vụ, ghi log và truyền correlation ID có thể được triển khai ở `ClientHttpRequestInterceptor`. Điều này giúp business code không phải lặp lại cách gắn token, đo thời gian và gửi request context cho từng endpoint.

Cần tách ba trách nhiệm:

- **LoadBalancer**: chọn đích từ danh sách instance theo service ID, có thể kết hợp health check, zone, hint và retry.
- **Interceptor bảo mật**: chọn đúng credential và gắn authorization header cho downstream được phép nhận.
- **Interceptor ngữ cảnh/ghi nhận**: truyền thông tin nhận diện request đã được chấp thuận, đo và ghi log an toàn.

Một interceptor thông thường không được tự chọn địa chỉ replica hay chuyển toàn bộ header của người dùng sang downstream. Bài học sẽ sử dụng `RestTemplate` blocking và `@LoadBalanced` của Spring Cloud, kết hợp OAuth2 client credentials, MDC, correlation ID, observability và kiểm thử lỗi.

## 1. Cơ chế hoạt động của ClientHttpRequestInterceptor

Spring Framework định nghĩa interface:

~~~java
public interface ClientHttpRequestInterceptor {
    ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution
    ) throws IOException;
}
~~~

| Thành phần | Ý nghĩa |
|---|---|
| `HttpRequest request` | HTTP method, URI, headers trước khi gửi |
| `byte[] body` | Nội dung request; không nên ghi trực tiếp vào log |
| `ClientHttpRequestExecution execution` | Bước tiếp theo trong chuỗi interceptor hoặc HTTP transport |
| `ClientHttpResponse` | Kết quả trả về, để RestTemplate tiếp tục xử lý status và body |
| `IOException` | Lỗi liên quan I/O; RuntimeException cũng có thể phát sinh trong xử lý |

Ví dụ đơn giản:

~~~java
public final class ClientNameInterceptor
        implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        request.getHeaders().set("X-Client-Name", "order-service");
        return execution.execute(request, body);
    }
}
~~~

Điểm cốt lõi là `execution.execute(request, body)`. Một interceptor có thể sửa headers trước lời gọi, quan sát response sau lời gọi, nhưng bình thường chỉ gọi `execute` **một lần**. Gọi nhiều lần có thể khiến cùng một thao tác ghi được thực thi trùng; không gọi thì request bị chặn hoàn toàn.

Chuỗi interceptor hoạt động giống các lớp bao quanh nhau:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["RestTemplate"]
    B --> C["CorrelationIdInterceptor"]
    C --> D["InventoryTokenInterceptor"]
    D --> E["OutboundLogInterceptor"]
    E --> F["LoadBalancer integration"]
    F --> G["HTTP transport"]
    G --> H["Inventory replica"]
~~~

Sơ đồ minh họa một thứ tự có thể xảy ra. Vị trí chính xác của `LoadBalancerInterceptor` do tích hợp Spring Cloud thêm và các interceptor do người dùng thêm có thể khác tùy cấu hình hoặc phiên bản. Khi cần chắc chắn, đọc danh sách `restTemplate.getInterceptors()` sau khi Spring hoàn tất khởi tạo bean.

Với chuỗi I1 → I2 → I3, thứ tự bao quanh thường là `I1.before → I2.before → I3.before → HTTP → I3.after → I2.after → I1.after`. Vì thế thứ tự ảnh hưởng đến phạm vi đo latency, lỗi được ghi nhận và dữ liệu headers xuất hiện ở mỗi tầng.

## 2. RestTemplate load-balanced khác RestTemplate thông thường

Một RestTemplate thông thường giải quyết URL bằng DNS và HTTP transport. Với URL như `http://inventory-service/api/items/SKU-01`, hostname `inventory-service` có thể không phân giải được qua DNS bên ngoài.

RestTemplate có `@LoadBalanced` được Spring Cloud bổ sung logic dùng host của URI làm service ID:

~~~text
REST request từ OrderService:
  http://inventory-service/api/items/SKU-01
                  |
                  v
  LoadBalancer client ID: inventory-service
                  |
                  v
  ServiceInstanceListSupplier / DiscoveryClient
                  |
                  +--- inventory-1 -> http://localhost:8081
                  +--- inventory-2 -> http://localhost:8082
                  |
                  v
  Round Robin / Random chọn một instance
                  |
                  v
  HTTP request tới địa chỉ replica đã chọn
~~~

`ClientHttpRequestInterceptor` dùng cho xác thực hoặc log không thay thế bộ chọn `ServiceInstance`. Nếu tự đổi URI thành `localhost:8081` trong interceptor, ứng dụng có thể bỏ qua health filtering, retry và định tuyến theo zone.

Các dependency ví dụ trong caller (phiên bản Spring Boot và Spring Cloud phải dùng tổ hợp tương thích được BOM quản lý):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
~~~

Spring Security OAuth2 client là lựa chọn cho ví dụ service-to-service; nếu hệ thống dùng workload identity, mTLS hay gateway cấp token thì nên dùng cơ chế tương đương do kiến trúc bảo mật quy định.

## 3. Gắn interceptor vào một RestTemplate dành riêng cho inventory

Đăng ký bean RestTemplate thông qua `RestTemplateBuilder` mà Spring Boot cung cấp. Điều này giúp kế thừa các customizer và instrumentation đã cấu hình.

~~~java
package com.example.order.http;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean("inventoryRestTemplate")
    @LoadBalanced
    RestTemplate inventoryRestTemplate(
            RestTemplateBuilder builder,
            CorrelationIdInterceptor correlation,
            InventoryTokenInterceptor authentication,
            OutboundLogInterceptor logging) {

        return builder
                .additionalInterceptors(
                        correlation,
                        authentication,
                        logging
                )
                .build();
    }
}
~~~

Trong cấu hình:

- `@LoadBalanced` đánh dấu RestTemplate mà Spring Cloud sẽ tích hợp với LoadBalancer.
- `additionalInterceptors` thêm interceptor nghiệp vụ vào builder. Đừng nhầm với `setInterceptors` có thể thay danh sách đã có.
- RestTemplate có tên `inventoryRestTemplate` chỉ phục vụ inventory để tránh gửi sai token tới các service khác.
- Các interceptor nên là bean stateless hoặc có collaborator thread-safe. Không lưu `currentUser` hay `currentTenant` trong field mutable của singleton interceptor.
- Sau khi ứng dụng hoạt động, không liên tục thay đổi `getInterceptors()`/`setInterceptors()` trong runtime.

Caller sử dụng với qualifier:

~~~java
package com.example.order.inventory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(
            @Qualifier("inventoryRestTemplate")
            RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public InventoryResponse findBySku(String sku) {
        return restTemplate.getForObject(
                "http://inventory-service/api/items/{sku}",
                InventoryResponse.class,
                sku
        );
    }
}
~~~

`InventoryResponse` là DTO tương ứng JSON phía inventory. Nếu client cũng cần `payment-service`, nên cấu hình một RestTemplate riêng hoặc xây dựng cơ chế định tuyến credential rõ ràng; không mặc định chia sẻ interceptor gắn inventory token cho payment.

## 4. Interceptor xác thực: dùng token đúng mục đích

Không nên viết token trực tiếp vào mã:

~~~java
request.getHeaders().setBearerAuth("TOKEN_HARDCODED");
~~~

Trong production, token cần được cấp và làm mới theo chính sách, lưu trữ bí mật an toàn và giới hạn scope/audience. Với yêu cầu `order-service` gọi inventory theo danh tính **ứng dụng order**, OAuth2 `client_credentials` là một lựa chọn phổ biến.

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant A as Authorization Server
    participant L as Spring Cloud LoadBalancer
    participant I as inventory-service

    O->>A: client_credentials khi cần access token
    A-->>O: access token với scope phù hợp
    O->>L: GET http://inventory-service
    L-->>O: chọn instance
    O->>I: GET /api/items + Bearer token
    I-->>O: Response
~~~

### Cấu hình Spring Security OAuth2 Client

~~~yaml
spring:
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

`INVENTORY_CLIENT_SECRET` phải được tiêm từ môi trường/secret store, không commit vào repository. `client-id`, `scope` và token URI trên là ví dụ. Authorization server, inventory-service và caller phải thống nhất audience, signature/opaque-token validation và policy của token.

Với các service call không phụ thuộc HTTP servlet request của user, có thể sử dụng `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

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
public class OutboundSecurityConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clientService) {

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, clientService
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

### InventoryTokenInterceptor

~~~java
package com.example.order.http;

import java.io.IOException;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public final class InventoryTokenInterceptor
        implements ClientHttpRequestInterceptor {

    private final OAuth2AuthorizedClientManager manager;

    public InventoryTokenInterceptor(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        var authorizeRequest = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-client")
                .principal("order-service")
                .build();

        var authorizedClient = manager.authorize(authorizeRequest);

        if (authorizedClient == null
                || authorizedClient.getAccessToken() == null) {
            throw new IllegalStateException(
                    "Cannot obtain inventory-service access token"
            );
        }

        request.getHeaders().setBearerAuth(
                authorizedClient.getAccessToken().getTokenValue()
        );

        return execution.execute(request, body);
    }
}
~~~

OAuth2 manager có thể tái sử dụng authorized client đã lưu và xin token mới khi cần. Đừng tự gọi authorization server mỗi request nếu không có lý do. `principal("order-service")` trong ví dụ đại diện client application, **không** phải danh tính người dùng cuối.

Khi authorization server lỗi, interceptor có thể ném exception **trước** khi HTTP request tới inventory được gửi. Cần phân biệt lỗi xin token với lỗi một inventory replica. Không được nuốt lỗi xác thực rồi tiếp tục gửi request không có token nếu API yêu cầu bảo mật.

### Token relay không phải client credentials

Nếu downstream cần **quyền của user**, phải dùng thiết kế token relay hoặc token exchange có kiểm soát: xác minh audience/scope, quyền chuyển token và chính sách trust giữa services. Không lấy `Authorization` của inbound request rồi chép sang mọi URL; làm vậy có thể lộ token cho dịch vụ không được phép nhận.

| Nhu cầu | Cơ chế thường dùng |
|---|---|
| Caller hành động theo quyền chính mình | `client_credentials` hoặc workload identity |
| Downstream cần quyền user | Token relay/exchange với policy rõ ràng |
| Gắn ID phục vụ logging | Correlation/tracing context |
| Xác định tenant/role | Dữ liệu đã xác thực, không tin header do client khai |

## 5. Truyền correlation ID qua servlet filter và MDC

Correlation ID giúp nối các log của cùng một request khi đi qua nhiều services. Nó không phải credential và cũng không phải `traceparent`/trace ID của hệ thống tracing. Ví dụ sau sử dụng `X-Correlation-Id` để chuyển một UUID qua các service trong Spring MVC.

### Tạo hoặc chuẩn hóa ID khi request vào caller

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
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-Id";
    public static final String MDC_KEY = "correlationId";

    private static final Pattern UUID_PATTERN = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String incoming = request.getHeader(HEADER);
        String correlationId = incoming != null
                && UUID_PATTERN.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        String oldValue = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            if (oldValue == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, oldValue);
            }
        }
    }
}
~~~

Ở ranh giới không tin cậy, có thể chọn **luôn tạo UUID mới** thay vì tin ID do client gửi. Validation ở ví dụ giúp giảm nguy cơ header injection và log pollution. `MDC` phần lớn dựa trên `ThreadLocal` nên phải dọn trong `finally` để thread servlet được tái sử dụng không mang correlation ID của request cũ.

### Gắn ID lên HTTP request outbound

~~~java
package com.example.order.http;

import com.example.order.web.CorrelationIdFilter;
import java.io.IOException;
import org.slf4j.MDC;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;

@Component
public final class CorrelationIdInterceptor
        implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        String id = MDC.get(CorrelationIdFilter.MDC_KEY);

        if (id != null && !id.isBlank()) {
            request.getHeaders().set(CorrelationIdFilter.HEADER, id);
        }

        return execution.execute(request, body);
    }
}
~~~

Khi RestTemplate được gọi **đồng bộ trên cùng thread** với inbound servlet request, interceptor có thể đọc MDC. Nếu business code dùng `@Async`, executor khác hoặc reactive pipeline, `MDC` không tự chuyển sang thread mới; cần cấu hình context propagation phù hợp hoặc truyền context một cách tường minh.

Trong background jobs không có inbound request, nên sinh correlation ID tại ranh giới job thay vì mặc định dùng một ID rỗng.

## 6. Chỉ truyền context đã được tin cậy

Không nên copy tất cả incoming headers sang downstream. Các header như `Authorization`, `Cookie`, `Host`, `Content-Length` và header hop-by-hop có semantics riêng, đôi khi chứa dữ liệu nhạy cảm hoặc không hợp lệ khi chuyển tiếp.

Với `X-Tenant-Id` hoặc thông tin vai trò, cần kiểm tra quyền và nguồn:

~~~text
HTTP request
  -> xác thực user/service
  -> kiểm tra quyền và tenant claim
  -> request context đáng tin cậy
  -> interceptor chỉ copy header trong allowlist
  -> downstream tiếp tục xác thực và phân quyền
~~~

Không dùng một `X-Tenant-Id` do người dùng tự gửi làm cơ sở để cấp quyền trong downstream. Nếu cần chuyển tenant sang service khác, lấy giá trị từ security context đã xác thực hoặc claim hợp lệ, giới hạn định dạng, và để downstream kiểm chứng quyền độc lập.

Một số dữ liệu như `Accept-Language` hoặc `X-Correlation-Id` có thể phù hợp để propagate theo allowlist sau khi được chuẩn hóa. `traceparent` lại nên do framework observability hỗ trợ, không tự lắp thủ công trong interceptor.


## 7. Ghi nhận request, response và độ trễ mà không lộ dữ liệu

Một interceptor ghi log nên đo thời gian bằng `System.nanoTime()` và chỉ ghi dữ liệu cần thiết như method, target host, status, elapsed time hoặc exception class. Tránh log toàn bộ URI có query, headers, bearer token, request body và response body.

~~~java
package com.example.order.http;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;

@Component
public final class OutboundLogInterceptor
        implements ClientHttpRequestInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(OutboundLogInterceptor.class);

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        long start = System.nanoTime();
        String host = request.getURI().getHost();
        String method = request.getMethod().name();

        try {
            ClientHttpResponse response =
                    execution.execute(request, body);

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );

            log.info(
                    "outbound_http method={} targetHost={} status={} elapsedMs={}",
                    method,
                    host,
                    response.getStatusCode().value(),
                    elapsedMs
            );

            return response;
        } catch (IOException | RuntimeException error) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );

            log.warn(
                    "outbound_http_failed method={} targetHost={} errorType={} elapsedMs={}",
                    method,
                    host,
                    error.getClass().getSimpleName(),
                    elapsedMs
            );

            throw error;
        }
    }
}
~~~

Mẫu trên không đọc response body và không sửa status. Sau khi `execution.execute` trả về, RestTemplate vẫn cần đọc stream response. Nếu interceptor đọc `response.getBody()` để ghi log nhưng không cấp lại stream, tầng giải mã JSON có thể thấy body rỗng hoặc lỗi. `BufferingClientHttpRequestFactory` có thể hỗ trợ một số nhu cầu đọc lại body, nhưng có chi phí bộ nhớ đáng kể và không nên bật vô điều kiện cho payload lớn hoặc dữ liệu nhạy cảm.

### Vì sao không ghi raw URI?

URI có thể chứa query `?token=...`, email, số điện thoại hoặc định danh nhạy cảm. Chỉ ghi host và method là một mức mặc định an toàn hơn. Nếu cần path để phân tích API, hãy chuẩn hóa thành route template như `/api/items/{sku}`, giới hạn cardinality và kiểm tra chính sách bảo vệ dữ liệu.

Ngay cả exception message cũng có thể chứa URI hoặc credential do một thư viện tạo ra. Ví dụ ghi `error.getClass().getSimpleName()` để phân nhóm lỗi; chỉ ghi stack trace ở môi trường/đường log đã được làm sạch và kiểm soát truy cập.

### Correlation ID trong mẫu log

Có thể cấu hình logging pattern hoặc structured logging của ứng dụng để thêm trường `correlationId` từ MDC. Khi ấy dòng log outbound có thể được liên kết với dòng log inbound bằng cùng ID, không cần thêm một field mutable vào interceptor.

Không đặt access token, tenant ID nhạy cảm hoặc toàn bộ request headers vào MDC. MDC là tiện ích ghi log, không phải kho lưu an toàn cho thông tin xác thực.

## 8. Thứ tự interceptor ảnh hưởng dữ liệu và latency

Trong ví dụ `InventoryHttpConfiguration`, thứ tự được ứng dụng đăng ký là:

~~~text
CorrelationIdInterceptor
    -> InventoryTokenInterceptor
        -> OutboundLogInterceptor
            -> interceptor tích hợp khác / HTTP transport
~~~

Giả sử có một request được gửi đi:

1. Correlation interceptor lấy ID từ MDC và thêm `X-Correlation-Id`.
2. Authentication interceptor dùng OAuth2 manager để lấy access token và gắn `Authorization`.
3. Logging interceptor bắt đầu đồng hồ đo.
4. Thực thi các interceptor còn lại, bao gồm logic load balancing và HTTP transport.
5. Logging ghi status/exception và elapsed time.
6. Response hoặc exception quay lại hai interceptor ngoài.

Điều này tạo ra các hệ quả quan trọng:

- Logging interceptor nằm **sau** auth nên không tính thời gian lấy token từ authorization server vào elapsed time của nó.
- Nếu muốn đo tổng thời gian **bao gồm** token acquisition, đặt timing ở ngoài auth hoặc đo ở service method/observation phù hợp.
- Nếu đặt logging trước load balancing, `request.getURI().getHost()` có thể vẫn là `inventory-service`; nếu đặt sau, có thể nhìn thấy host vật lý.
- Nếu Spring Cloud thêm interceptor khác lúc khởi tạo, thứ tự đầy đủ không chỉ gồm ba interceptor của ứng dụng.

Để quan sát danh sách thực tế trong môi trường thử nghiệm, có thể kiểm tra một lần sau khi ApplicationContext sẵn sàng:

~~~java
for (var interceptor : inventoryRestTemplate.getInterceptors()) {
    System.out.println(interceptor.getClass().getName());
}
~~~

Mã chẩn đoán này không nên chạy trên mỗi HTTP request trong production. Đừng suy ra chính sách đã bật chỉ dựa trên tên interceptor; cần xác minh bằng request thực tế và metrics.

### Không nhầm logging interceptor với LoadBalancer lifecycle

`OutboundLogInterceptor` ghi nhận yêu cầu logic từ góc nhìn của nó. Muốn biết **instance được chọn** và kết quả load balancing, cần sử dụng tracing, metrics/lifecycle của Spring Cloud LoadBalancer hoặc log của backend. Việc nhìn thấy URI logic trong log không phải bằng chứng LoadBalancer không hoạt động.

## 9. Retry và timeout: một business request có thể có nhiều attempt

Khi `inventory-service` có nhiều replica, Spring Cloud LoadBalancer có thể được cấu hình retry những lỗi phù hợp. Ngoài ra, RestTemplate, gateway hoặc thư viện resilience cũng có thể thực hiện retry.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant R as RestTemplate/Interceptor
    participant L as LoadBalancer Retry
    participant A as Inventory A
    participant B as Inventory B

    O->>R: GET /api/items/SKU-01
    R->>L: Lời gọi logic
    L->>A: Attempt 1
    A--xL: Timeout
    Note over L: Retry chỉ nếu được cấu hình, đủ điều kiện
    L->>B: Attempt 2
    B-->>L: HTTP 200
    L-->>R: Kết quả sau retry
    R-->>O: InventoryResponse
~~~

Nếu logging interceptor nằm ngoài logic retry, nó có thể ghi một event cho **logical request** với elapsed time gồm nhiều attempt. Nếu interceptor nằm bên trong một lớp retry, mỗi attempt có thể được ghi riêng. Do đó, đừng so bộ đếm log outbound với access log backend mà không xác định các tầng retry.

### Không tự tạo retry trong interceptor xác thực

Không nên viết:

~~~java
try {
    return execution.execute(request, body);
} catch (IOException error) {
    // Không nên tự động gọi lại mà thiếu retry policy.
    return execution.execute(request, body);
}
~~~

Request POST có thể đã được backend xử lý thành công trước khi kết nối timeout. Gửi lại có thể tạo đơn hoặc thanh toán trùng. Retry nên nằm trong cơ chế riêng có giới hạn tổng số lần thử, backoff, deadline và idempotency key phù hợp.

### Timeout liên quan nhiều đường đi

Một lần gọi inventory có thể gồm thời gian:

~~~text
RestTemplate interceptor
   |
   +--- Lấy token từ authorization server (nếu cần)
   |
   +--- LoadBalancer chọn instance / discovery (nếu cần)
   |
   +--- Connect timeout của HTTP transport
   |
   +--- Chờ response từ inventory
   |
   +--- Retry/backoff nếu được cấu hình
~~~

`spring.cloud.loadbalancer.service-discovery.timeout` không phải timeout của HTTP transport. Connect/read timeout của RestTemplate phải được đặt ở request factory hoặc builder được hỗ trợ trong phiên bản Spring Boot đang dùng. Request cấp token cũng cần timeout riêng.

Nếu business deadline là 2 giây mà interceptor xin token mất 1,8 giây, không thể chỉ đặt inventory read timeout 2 giây rồi kỳ vọng toàn request luôn dưới 2 giây. Hãy thiết kế end-to-end deadline và giới hạn các tầng retry.

## 10. Distributed tracing: tránh tự sửa traceparent

Nếu ứng dụng đã dùng Spring Boot Actuator, Micrometer Observation và Micrometer Tracing, RestTemplate được tạo bằng `RestTemplateBuilder` do Spring quản lý có thể nhận instrumentation HTTP client. Khi cấu hình đầy đủ, hệ thống tracing quản lý span và truyền trace context qua các header chuẩn như `traceparent`.

Không tự tạo `traceparent` ở interceptor bằng UUID hoặc chuỗi ngẫu nhiên. Header tracing có định dạng và quan hệ parent/span cụ thể; tự sửa có thể làm mất liên kết giữa các span, gây sai tree của distributed trace.

| Thông tin | Công dụng | Nguồn |
|---|---|---|
| `X-Correlation-Id` | Truy vấn log theo một request/nghiệp vụ | Application/filter |
| `traceparent` | Liên kết các span trong distributed trace | Micrometer Tracing/OpenTelemetry instrumentation |
| `Authorization` | Xác thực và phân quyền | OAuth2/workload identity |
| `X-Tenant-Id` | Context tenant đã được xác thực | Trusted security context |

Có thể dùng cả correlation ID và trace ID nếu mỗi thứ có mục đích rõ ràng. Tránh tự động đưa user ID, token hoặc request path có tham số định danh vào metric tag, vì gây lộ thông tin và cardinality cao.

Nếu tự tạo `new RestTemplate()` bỏ qua builder/customizer do Spring Boot cung cấp, instrumentation có thể không được áp dụng như mong muốn. Đó là một lý do nên xây dựng bean thông qua `RestTemplateBuilder`.

## 11. Kiểm thử interceptor độc lập với load balancing

Unit test có thể kiểm tra behavior của `ClientHttpRequestInterceptor` mà không cần khởi động discovery hay HTTP server. Dùng `MockClientHttpRequest` và `MockClientHttpResponse` từ `spring-test` cùng một `ClientHttpRequestExecution` giả.

Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.mock.http.client.MockClientHttpRequest;
import org.springframework.mock.http.client.MockClientHttpResponse;

class CorrelationIdInterceptorTest {

    @Test
    void forwardsCorrelationIdFromMdc() throws Exception {
        String id = "e41c139f-8057-4e88-84bc-af4fc1c414a2";
        MDC.put("correlationId", id);

        try {
            var request = new MockClientHttpRequest(
                    HttpMethod.GET,
                    URI.create("http://inventory-service/api/items/42")
            );

            ClientHttpRequestExecution next = (outbound, body) -> {
                assertEquals(
                        id,
                        outbound.getHeaders()
                                .getFirst("X-Correlation-Id")
                );

                return new MockClientHttpResponse(
                        new byte[0],
                        HttpStatus.OK
                );
            };

            var response = new CorrelationIdInterceptor()
                    .intercept(request, new byte[0], next);

            assertEquals(HttpStatus.OK, response.getStatusCode());
        } finally {
            MDC.remove("correlationId");
        }
    }
}
~~~

Thêm import `CorrelationIdInterceptor` theo package thực tế. `spring-boot-starter-test` thường cung cấp JUnit và spring-test cho dự án Spring Boot phù hợp.

Những test khác cần có:

- Khi không có MDC, interceptor không vô tình gửi correlation ID cũ.
- Khi OAuth2 manager không cấp được token, auth interceptor ném exception và **không gọi** transport.
- Khi có token, request đúng service nhận `Authorization: Bearer ...`, nhưng token không bị in vào log.
- Logging interceptor truyền nguyên body/response và không đọc stream.
- Lỗi I/O được propagate thay vì đổi thành response 200 giả.
- RestTemplate dành cho payment không chứa `InventoryTokenInterceptor`.
- Một lời gọi chỉ có một lần `execution.execute` nếu interceptor không được giao trách nhiệm retry.

**Unit test interceptor không chứng minh RestTemplate đã được load-balanced.** Cần integration test riêng khởi tạo Spring context, discovery và hai backend, rồi xác nhận request `http://inventory-service` được gửi đến instance thật mà vẫn mang headers hợp lệ.

## 12. Thực hành quan sát end-to-end

Trong môi trường thử nghiệm:

1. Chạy `inventory-service` ở hai cổng 8081 và 8082, cùng được discovery đăng ký dưới service ID `inventory-service`.
2. Chạy `order-service` trên 8080, có RestTemplate `@LoadBalanced` và ba interceptor.
3. Nếu cần auth end-to-end, dùng test identity provider cấp token client credentials với scope đúng; không hardcode credential thật.
4. Tạo controller thử nghiệm `GET /orders/demo-inventory/{sku}` gọi `InventoryClient.findBySku(sku)`.
5. Gửi request kèm UUID correlation để theo dõi log và backend nào thực sự xử lý.

Trên PowerShell:

~~~powershell
$correlationId = [guid]::NewGuid().ToString()
Invoke-RestMethod -Uri "http://localhost:8080/orders/demo-inventory/SKU-01" -Headers @{ "X-Correlation-Id" = $correlationId }
~~~

Các endpoint được nêu là ví dụ, cần triển khai trong ứng dụng thử nghiệm. Để đo phân phối, gửi nhiều request và cho mỗi backend trả `instanceId` hoặc ghi access log có chứa instance ID và correlation ID.

Kiểm tra lần lượt:

- Caller có đúng correlation ID trong MDC và header outbound.
- Token được cấp cho đúng client registration, không xuất hiện trong log.
- Khi 8081/8082 cùng khỏe, request có thể đến nhiều bản sao qua Spring Cloud LoadBalancer.
- Thay đổi backend trạng thái lỗi: log phân biệt timeout, HTTP error, token error và discovery error.
- Gắn correlation ID vào backend log để nối dòng sự kiện qua từng service.
- Đo chênh lệch giữa số logical calls, số HTTP attempts và số request backend nhận được khi có retry.

## 13. Những lỗi phổ biến khi triển khai

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `UnknownHostException` khi gọi service ID | Dùng RestTemplate thường hoặc sai bean | Kiểm tra `@LoadBalanced`, dependency, bean qualifier |
| Downstream luôn trả 401 | Token thiếu, sai audience/scope hoặc lỗi validation | Kiểm tra OAuth2 registration và security policy, không in token |
| Token inventory bị gửi sang payment | Sử dụng chung RestTemplate có auth interceptor cho mọi đích | Tách bean theo downstream hoặc chọn credential có kiểm soát |
| Correlation ID chỉ xuất hiện ở inbound | Chưa thêm outbound interceptor hoặc MDC trống | Kiểm tra bean, filter và luồng thực thi |
| Correlation ID lẫn request khác | Không dọn MDC trên thread tái sử dụng | Sử dụng `finally` và test đồng thời |
| Lời gọi `@Async` mất correlation ID | ThreadLocal không tự propagate | Dùng context propagation hoặc truyền context tường minh |
| Response body bị mất sau logging | Interceptor đã đọc body stream | Không đọc body trong log, hoặc thiết kế buffering có giới hạn |
| Một request phát sinh nhiều log outbound | Retry nằm ở nhiều tầng hay logger chạy mỗi attempt | Phân biệt logical call và HTTP attempt, xem thứ tự interceptor |
| Log chỉ thấy `inventory-service` | Logger nhìn URI trước LoadBalancer | Dùng backend log/lifecycle metrics để xem instance được chọn |
| Token server lỗi bị hiểu là inventory lỗi | Authorization xảy ra trước network call | Phân loại exception theo giai đoạn |
| Interceptor không chạy với WebClient | WebClient dùng cơ chế filter khác | Với WebClient dùng `ExchangeFilterFunction`, không áp interceptor RestTemplate nguyên trạng |
| Sửa danh sách interceptor ở runtime gây lỗi | Bean RestTemplate bị thay cấu hình khi nhiều thread đang sử dụng | Cấu hình trước khi phục vụ request |

## 14. Checklist khi đưa vào production

- [ ] Dùng `@LoadBalanced` cho RestTemplate gọi service ID và xác nhận dependency của Spring Cloud LoadBalancer.
- [ ] Tạo RestTemplate qua builder do Spring quản lý khi cần instrumentation/customizer.
- [ ] Mỗi interceptor có trách nhiệm rõ; không lưu state của request trong field singleton.
- [ ] Credential được cấp và làm mới an toàn; không hardcode, log hoặc relay token tùy tiện.
- [ ] Giới hạn token cho đúng downstream, scope và audience.
- [ ] Chỉ propagate header có trong allowlist và được chuẩn hóa.
- [ ] Tenant/role phải được lấy từ security context đáng tin cậy, downstream vẫn tự phân quyền.
- [ ] Correlation ID được tạo hoặc xác thực ở inbound và dọn MDC trong `finally`.
- [ ] Có context propagation chuyên dụng cho `@Async` hoặc reactive flows.
- [ ] Logging chỉ ghi method/host/status/elapsed time; không ghi body, full URI, headers, secrets.
- [ ] Kiểm tra thứ tự interceptor runtime và phạm vi thời gian đo được.
- [ ] Không tự retry trong interceptor nếu thiếu chính sách idempotency, budget và deadline.
- [ ] Đặt timeout cho authorization server và HTTP client, không nhầm với discovery timeout.
- [ ] Dùng tracing instrumentation cho `traceparent` thay vì tự tạo header.
- [ ] Có unit test interceptor và integration test LoadBalancer với ít nhất hai backend.
- [ ] Quan sát cả caller và backend để phân biệt request logic với từng attempt.

## Tài liệu tham khảo

- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate, client request interceptors và cách cấu hình HTTP client.
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `@LoadBalanced RestTemplate`, `ServiceInstance`, retry và lifecycle.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClientManager`, client registration và `client_credentials`.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Observation, tracing và các HTTP client được Spring cấu hình.

**Kết luận:** trong RestTemplate được tích hợp Spring Cloud LoadBalancer, interceptor là một điểm mở rộng tốt để xử lý xác thực, ghi nhận và truyền ngữ cảnh. Nhưng nó không thay thế việc chọn instance, không cấp quyền cho user và không tự biến một request lỗi thành retry an toàn. Khi tách biệt trách nhiệm, cấu hình đúng thứ tự, bảo vệ token và kiểm thử các tình huống lỗi/async/retry, giao tiếp giữa các dịch vụ sẽ dễ theo dõi và ít rủi ro hơn.
