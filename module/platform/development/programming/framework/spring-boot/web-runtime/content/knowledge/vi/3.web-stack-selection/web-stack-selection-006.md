# Dùng WebClient trong ứng dụng MVC mà không đổi mô hình máy chủ

Spring MVC và WebClient giải quyết hai việc khác nhau. **Spring MVC** tiếp nhận request từ trình duyệt hoặc client, ánh xạ URL vào controller và tạo response qua mô hình Servlet. **WebClient** là HTTP client dùng để ứng dụng chủ động gọi một dịch vụ bên ngoài.

Vì vậy, một ứng dụng có thể tiếp tục chạy Spring MVC trên Tomcat/Jetty/Undertow, đồng thời dùng WebClient để gọi REST API khác. Thêm thư viện WebFlux để sử dụng WebClient không đồng nghĩa với việc chuyển máy chủ sang WebFlux. Spring Boot có thể nhận diện cả hai stack và ưu tiên Spring MVC khi cả hai cùng có mặt.

Bài này trình bày cách chọn dependency, cấu hình WebClient, gọi dịch vụ từ controller/service MVC, quản lý timeout và lỗi, kiểm thử, cùng những tình huống dễ khiến ứng dụng vô tình chuyển sang reactive server.

## 1. Phân biệt server stack và HTTP client

Một ứng dụng web thường có hai chiều giao tiếp:

- **Inbound (request đi vào ứng dụng)**: trình duyệt gọi endpoint của ứng dụng. Spring MVC dùng Servlet API để nhận request, chạy controller và ghi response.
- **Outbound (request đi ra từ ứng dụng)**: controller hoặc service gọi một API khác. WebClient tạo HTTP request, gửi đến hệ thống đích và chuyển response thành object Java.

Hai chiều này độc lập. Chọn WebClient cho outbound call không buộc inbound server phải dùng WebFlux.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Spring MVC | Xử lý HTTP request đi vào ứng dụng theo mô hình Servlet | **@RestController**, **@GetMapping**, **DispatcherServlet** |
| Servlet container | Máy chủ tiếp nhận request cho ứng dụng MVC | Tomcat, Jetty, Undertow |
| WebClient | Gửi HTTP request từ ứng dụng đến dịch vụ khác | GET catalog, POST payment, gọi identity provider |
| WebFlux server | Reactive web stack xử lý request đi vào | **DispatcherHandler**, reactive server như Reactor Netty |

Một request có thể đi theo luồng:

~~~text
Browser / API client
        |
        | HTTP request
        v
Servlet container (Tomcat)
        |
        v
Spring MVC Controller
        |
        v
Application Service
        |
        | WebClient: outbound HTTP request
        v
Remote REST API
        |
        | HTTP response
        v
WebClient -> Service -> MVC Controller
        |
        v
Servlet response
~~~

Điểm cần nhớ: WebClient là client API. WebFlux là một web framework có thể dùng ở phía server. Việc sử dụng chung thư viện WebClient và Spring MVC là một trường hợp được Spring Boot hỗ trợ.

## 2. Dependency cần có

Nếu dự án đã có Spring MVC qua **spring-boot-starter-web**, hãy bổ sung **spring-boot-starter-webflux** để có WebClient và các thành phần reactive cần thiết.

**Gradle (Groovy):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu **spring-boot-starter-web** đã có sẵn, chỉ cần thêm dependency WebFlux và giữ nguyên dependency MVC.

**Maven:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các dependency version được quản lý bởi Spring Boot parent hoặc BOM của dự án. Không nên tự thêm version riêng cho từng thư viện Spring khi dự án đã dùng dependency management của Boot.

### 2.1. Vì sao thêm WebFlux mà ứng dụng vẫn chạy MVC?

Khi cả Spring MVC và WebFlux cùng có trên classpath, Spring Boot mặc định cấu hình **Spring MVC**. Quyết định này cho phép các ứng dụng MVC dùng WebClient mà không phải đổi server stack.

Trong tình huống này:

- **spring-boot-starter-web** cung cấp Spring MVC và Servlet container.
- **spring-boot-starter-webflux** cung cấp WebClient, Reactor và các thành phần WebFlux.
- Boot phát hiện MVC và chọn mô hình Servlet làm web application type.
- Controller MVC, **DispatcherServlet** và embedded Tomcat tiếp tục hoạt động như trước.

Không cần thêm **@EnableWebFlux** chỉ để dùng WebClient. Cũng không đặt **spring.main.web-application-type=reactive** nếu mục tiêu là giữ máy chủ Servlet. Nếu dự án có cấu hình application type tường minh, hãy kiểm tra để nó vẫn là **servlet**.

Có thể xác nhận bằng log khởi động: ứng dụng MVC thường khởi động embedded Tomcat và đăng ký **DispatcherServlet**. Nếu thấy ứng dụng khởi động theo reactive web server, hãy kiểm tra dependency, property **spring.main.web-application-type** và cấu hình web tùy chỉnh.

## 3. WebClient hoạt động như thế nào?

WebClient cung cấp API fluent để mô tả một HTTP request. Request chưa được gửi cho đến khi reactive publisher được subscribe. Các toán tử như **retrieve()**, **bodyToMono()** và **timeout()** xây dựng pipeline xử lý response.

Một GET đơn giản:

~~~java
Mono<CatalogItem> result = webClient.get()
        .uri("/items/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(CatalogItem.class);
~~~

Giải thích:

1. **get()** chọn HTTP method GET.
2. **uri(...)** tạo URI và thay tham số đường dẫn.
3. **accept(...)** khai báo loại response ứng dụng mong muốn.
4. **retrieve()** thực hiện gửi request và chuẩn bị xử lý response.
5. **bodyToMono(...)** chuyển response body thành một object bất đồng bộ.

Với request cần body, có thể dùng **bodyValue()**:

~~~java
Mono<CatalogItem> created = webClient.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateCatalogItemRequest("Keyboard"))
        .retrieve()
        .bodyToMono(CatalogItem.class);
~~~

WebClient hỗ trợ header, query parameter, path variable, request body, filter, codec và nhiều kiểu response. Nên tạo client dùng lại thay vì tạo mới trong từng request đến controller.

## 4. Cấu hình một WebClient dùng chung

Spring Boot tự cấu hình một **WebClient.Builder** khi WebFlux có trên classpath. Builder này có thể nhận các customizer và thiết lập codec/observation do Boot quản lý. Hãy inject builder và build một WebClient dành riêng cho dịch vụ cần gọi.

Ví dụ cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── CatalogClientConfiguration.java
│   ├── CatalogClientProperties.java
│   ├── CatalogClient.java
│   ├── CatalogController.java
│   └── CatalogItem.java
└── application.yml
~~~

**CatalogClientProperties.java**

~~~java
package com.example.shop.catalog;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "clients.catalog")
public record CatalogClientProperties(String baseUrl) {
}
~~~

**CatalogClientConfiguration.java**

~~~java
package com.example.shop.catalog;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogClientProperties properties) {

        return builder.clone()
                .baseUrl(properties.baseUrl())
                .build();
    }
}
~~~

Dùng **clone()** để cấu hình builder riêng cho client này mà không làm thay đổi builder được inject ở nơi khác. WebClient sau khi build có thể được dùng lại giữa các request; nó được thiết kế theo hướng immutable và an toàn cho việc chia sẻ.

**application.yml**

~~~yaml
server:
  port: 8080

clients:
  catalog:
    base-url: http://localhost:9090
~~~

Trong ví dụ, ứng dụng MVC chạy ở cổng 8080 và dịch vụ Catalog chạy ở cổng 9090. Địa chỉ thật nên được đưa vào cấu hình theo môi trường, chẳng hạn biến môi trường hoặc profile deployment, thay vì hard-code trong service.

Nếu cần nhiều dịch vụ, có thể tạo một bean WebClient riêng cho mỗi upstream để quản lý base URL, authentication header, filter và timeout theo từng dịch vụ. Không nên dùng một base URL toàn cục cho các hệ thống có chính sách kết nối khác nhau.

## 5. Gọi WebClient từ service MVC theo kiểu imperative

Trong ứng dụng MVC truyền thống, service thường nhận và trả về object Java thông thường. Có thể dùng WebClient bên trong service rồi chờ kết quả bằng **block()** ở ranh giới giữa reactive client và imperative code.

**CatalogItem.java**

~~~java
package com.example.shop.catalog;

public record CatalogItem(long id, String name) {
}
~~~

**CatalogClient.java**

~~~java
package com.example.shop.catalog;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(
            @Qualifier("catalogWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    public CatalogItem findById(long id) {
        return findByIdAsync(id).block(Duration.ofSeconds(4));
    }

    public Mono<CatalogItem> findByIdAsync(long id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(CatalogItem.class)
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

Trong ví dụ:

- **findByIdAsync()** trả về **Mono<CatalogItem>**, giữ nguyên API reactive của WebClient.
- **timeout(Duration.ofSeconds(3))** giới hạn thời gian chờ response của publisher.
- **findById()** gọi **block(Duration.ofSeconds(4))** để trả về object Java cho code imperative.
- Thời gian block có giới hạn dài hơn timeout của publisher để tránh chờ vô hạn nếu có vấn đề ở pipeline.

Khi upstream trả HTTP 4xx hoặc 5xx, **retrieve()** mặc định phát sinh **WebClientResponseException**. Lỗi kết nối hoặc request có thể phát sinh **WebClientRequestException**; timeout của Reactor phát sinh lỗi timeout. Ứng dụng nên chuyển những lỗi này thành lỗi tích hợp có ý nghĩa, ghi log có kiểm soát và trả HTTP status phù hợp cho client gọi vào. Không trả nguyên nội dung lỗi nội bộ hoặc thông tin nhạy cảm của upstream ra ngoài.

**block()** khiến thread Servlet hiện tại chờ kết quả. Cách này đơn giản và phù hợp khi muốn giữ service/controller imperative, nhưng trong lúc chờ, thread đó không thể xử lý request khác. Cần đặt timeout và giới hạn concurrency phù hợp với số thread của MVC và khả năng chịu tải của upstream.

Không gọi **block()** bên trong một reactive pipeline hoặc trên event-loop thread của WebFlux/Reactor Netty. Trong những ngữ cảnh đó, việc block có thể gây lỗi hoặc làm nghẽn event loop.

## 6. Controller MVC vẫn trả object thông thường

Controller có thể dùng service imperative như trước.

**CatalogController.java**

~~~java
package com.example.shop.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public CatalogItem getItem(@PathVariable long id) {
        return catalogClient.findById(id);
    }
}
~~~

Khi client gọi:

~~~http
GET /api/catalog/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

MVC nhận request, gọi **CatalogController**, service dùng WebClient gọi **http://localhost:9090/items/42**, nhận JSON và chuyển thành **CatalogItem**. Sau đó controller trả object để MVC message converter ghi JSON response.

Ví dụ response:

~~~json
{
  "id": 42,
  "name": "Keyboard"
}
~~~

Inbound request vẫn do Servlet container và Spring MVC xử lý. WebClient chỉ thực hiện outbound call đến Catalog API.

## 7. Dùng WebClient bất đồng bộ nhưng vẫn giữ Spring MVC

Nếu muốn tránh giữ thread Servlet trong lúc chờ upstream, có thể trả **Mono** từ controller MVC:

~~~java
@GetMapping("/async/{id}")
public Mono<CatalogItem> getItemAsync(@PathVariable long id) {
    return catalogClient.findByIdAsync(id);
}
~~~

Spring MVC có thể nhận biết các reactive return type như **Mono** thông qua reactive adapter và xử lý kết quả bằng cơ chế asynchronous request processing của Servlet. Request vẫn đi vào **DispatcherServlet** và server vẫn là Servlet stack; không cần chuyển toàn bộ ứng dụng sang WebFlux.

Khác biệt giữa hai cách:

| Cách gọi | Kiểu trả về của controller | Hành vi chờ |
|---|---|---|
| Imperative | **CatalogItem** | Thread Servlet chờ kết quả tại **block()** |
| MVC async | **Mono<CatalogItem>** | MVC bắt đầu xử lý async và hoàn tất response khi publisher phát kết quả |

Dùng cách imperative khi code hiện tại được tổ chức theo kiểu đồng bộ và lưu lượng phù hợp. Dùng kiểu async khi muốn tận dụng việc chờ I/O bất đồng bộ, đặc biệt khi có nhiều outbound call đồng thời. Cả hai vẫn là Spring MVC.

Không nên chuyển một phần code sang reactive chỉ vì muốn dùng WebClient. Nếu chọn trả **Mono**, cần giữ pipeline reactive xuyên suốt đoạn xử lý bất đồng bộ; không gọi **block()** rồi lại bọc kết quả vào **Mono.just()**, vì cách đó làm mất lợi ích của xử lý async.

## 8. Timeout, connection pool và giới hạn tài nguyên

Timeout của request cần được thiết kế theo nhiều lớp:

- **Connect timeout**: giới hạn thời gian thiết lập kết nối TCP.
- **Response timeout**: giới hạn thời gian chờ dữ liệu response theo cấu hình HTTP client.
- **Publisher timeout**: giới hạn thời gian pipeline reactive chờ hoàn tất.
- **MVC request timeout**: giới hạn thời gian xử lý request phía server nếu ứng dụng cấu hình cơ chế này.

**Mono.timeout(...)** giới hạn thời gian publisher, còn **block(Duration)** giới hạn thời gian caller chờ. Hai giới hạn này không thay thế hoàn toàn cấu hình kết nối ở tầng transport. Với hệ thống production, hãy cấu hình connect/response timeout và connection pool phù hợp với thư viện HTTP connector đang dùng.

Nếu ứng dụng dùng Reactor Netty, có thể tùy chỉnh connector bằng **ReactorClientHttpConnector** và **HttpClient**. Ví dụ phần cấu hình transport:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient webClient = builder.clone()
        .baseUrl(baseUrl)
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Đoạn này cần các import từ Netty và Reactor Netty:

~~~java
import io.netty.channel.ChannelOption;
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
~~~

Khi tự cung cấp connector, cần kiểm tra lại các thiết lập TLS, proxy, metrics, tracing và connection pool mà ứng dụng đang dùng. Nếu Boot hoặc nền tảng triển khai đã tùy chỉnh connector, thay connector có thể làm mất một số thiết lập đó. Hãy giữ lại các customizer cần thiết khi tạo transport riêng.

Không đặt timeout quá dài chỉ để che lỗi upstream. Timeout phải phù hợp với SLA, thời gian xử lý của endpoint và ngân sách thời gian của request đi vào. Nếu request gọi nhiều upstream nối tiếp, tổng thời gian chờ cần nằm trong giới hạn mà client gọi vào chấp nhận.

## 9. Xử lý HTTP status và lỗi upstream

WebClient có hai API thường dùng để đọc response:

- **retrieve()**: phù hợp với luồng thông thường; status 4xx/5xx được chuyển thành exception mặc định.
- **exchangeToMono()** hoặc **exchangeToFlux()**: dùng khi cần rẽ nhánh theo status/header và tự kiểm soát việc đọc body.

Ví dụ dùng **onStatus()** để tùy chỉnh lỗi:

~~~java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.is4xxClientError(),
                response -> response.createException()
        )
        .onStatus(
                status -> status.is5xxServerError(),
                response -> response.createException()
        )
        .bodyToMono(CatalogItem.class);
~~~

Ví dụ trên giữ loại exception mặc định nhưng làm rõ nơi có thể tùy chỉnh hành vi theo nhóm status. Nếu cần chuyển 404 của upstream thành kết quả nghiệp vụ riêng, hãy map status ở đây hoặc tại service boundary.

Một chính sách xử lý lỗi nên phân biệt:

- **4xx từ upstream**: request gửi đến upstream không hợp lệ hoặc tài nguyên không tồn tại. Tùy hợp đồng, có thể chuyển thành lỗi nghiệp vụ hoặc lỗi gateway.
- **5xx từ upstream**: upstream gặp lỗi; thường biểu diễn thành lỗi phụ thuộc dịch vụ.
- **Network error**: DNS, connection refused, TLS hoặc kết nối bị đóng.
- **Timeout**: upstream phản hồi quá chậm hoặc kết nối không hoàn tất trong ngân sách thời gian.
- **Decode error**: body không khớp kiểu dữ liệu hoặc JSON không hợp lệ.

Không nên retry mọi lỗi một cách tự động. Retry có thể hữu ích với một số lỗi tạm thời và thao tác idempotent, nhưng retry POST tạo đơn hàng hoặc thanh toán có thể gây thực hiện lặp nếu không có idempotency key và cơ chế chống trùng. Khi cần retry, phải giới hạn số lần, backoff, jitter và tổng thời gian.

Có thể dùng **@ControllerAdvice** để chuyển exception tích hợp thành response API nhất quán. Log nên có correlation ID, tên upstream, method, path đã làm sạch, status và thời gian xử lý; tránh log Authorization header, cookie, token hoặc dữ liệu nhạy cảm trong response body.

## 10. Gửi header, query parameter và body

WebClient hỗ trợ tạo request theo từng nhu cầu.

**Query parameter:**

~~~java
webClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/items")
                .queryParam("category", "keyboard")
                .queryParam("page", 0)
                .build())
        .retrieve()
        .bodyToFlux(CatalogItem.class);
~~~

**Header theo request:**

~~~java
webClient.get()
        .uri("/profile")
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Profile.class);
~~~

Không hard-code token vào source code hoặc application.yml được commit vào repository. Credential nên đến từ secret manager hoặc cơ chế quản lý bí mật của môi trường.

**POST JSON:**

~~~java
webClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(createOrderRequest)
        .retrieve()
        .bodyToMono(OrderResponse.class);
~~~

Nếu body là collection hoặc kiểu generic, dùng **ParameterizedTypeReference** để giữ thông tin kiểu khi decode:

~~~java
ParameterizedTypeReference<List<CatalogItem>> itemListType =
        new ParameterizedTypeReference<>() {};

Mono<List<CatalogItem>> items = webClient.get()
        .uri("/items")
        .retrieve()
        .bodyToMono(itemListType);
~~~

Nên xây dựng URI bằng template hoặc **UriBuilder** thay vì nối chuỗi thủ công, đặc biệt khi có query parameter chứa dấu cách, ký tự Unicode hoặc ký tự cần URL encode.

## 11. Cấu hình authentication và filter dùng chung

Nếu mọi request đến một upstream cần cùng header hoặc correlation ID, có thể thêm filter ở lúc tạo client:

~~~java
WebClient webClient = builder.clone()
        .baseUrl(baseUrl)
        .filter((request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Application", "shop-api")
                    .build();
            return next.exchange(updated);
        })
        .build();
~~~

Filter cần import:

~~~java
import org.springframework.web.reactive.function.client.ClientRequest;
~~~

Có thể dùng filter cho correlation ID, logging metadata, authentication hoặc metrics. Cần tránh ghi log body/token đầy đủ và tránh thay đổi header có thể làm sai chữ ký request.

Với OAuth2, Spring Security cung cấp các integration dành cho OAuth2 Client và WebClient. Nên dùng cơ chế quản lý access token/refresh token phù hợp thay vì tự viết logic cấp phát và gia hạn token trong filter đơn giản.

Nếu mỗi request cần token của người dùng hiện tại, cần xác định rõ token được lấy từ SecurityContext, OAuth2AuthorizedClient hay một credential service. Không dùng một token cố định toàn ứng dụng để thay cho danh tính của từng người dùng.

## 12. Kiểm thử ứng dụng MVC có outbound WebClient

Nên kiểm thử hai ranh giới riêng:

**Kiểm thử controller MVC:** mock **CatalogClient** để xác nhận URL, status và JSON response mà ứng dụng cung cấp. Test này không cần gọi dịch vụ Catalog thật.

**Kiểm thử WebClient integration:** chạy một HTTP mock server như WireMock hoặc OkHttp MockWebServer, cấu hình base URL trỏ tới server giả rồi xác nhận request method, path, header, body, status và cách decode response.

Các trường hợp quan trọng:

- Response 200 với JSON hợp lệ được chuyển thành DTO.
- Response 404/500 được map thành lỗi phù hợp.
- Server không chạy hoặc đóng kết nối thì ứng dụng trả lỗi tích hợp rõ ràng.
- Server phản hồi chậm thì timeout được áp dụng.
- JSON không hợp lệ được xử lý như decode error.
- Header xác thực và correlation ID được gửi đúng, không bị ghi vào log.
- Controller MVC vẫn được kiểm thử qua MockMvc.
- Nếu dùng controller trả Mono, xác nhận MVC async request hoàn tất và response đúng.

Ví dụ kiểm thử controller bằng MockMvc có thể dùng Mockito để stub service:

~~~java
@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    CatalogClient catalogClient;

    @Test
    void returnsCatalogItem() throws Exception {
        given(catalogClient.findById(42))
                .willReturn(new CatalogItem(42, "Keyboard"));

        mockMvc.perform(get("/api/catalog/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Keyboard"));
    }
}
~~~

Ví dụ dùng **@MockitoBean** của Spring Framework mới; với phiên bản Spring Boot/Spring Framework cũ hơn, dự án có thể dùng **@MockBean**. Cần static import **given**, **get**, **status** và **jsonPath** tương ứng. Nếu test chỉ kiểm tra controller, không cần nạp cấu hình WebClient hoặc kết nối upstream thật.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thêm WebFlux nhưng ứng dụng khởi động reactive server | Dependency MVC bị thiếu, application type bị đặt là reactive hoặc cấu hình web tùy chỉnh | Kiểm tra cả hai starter và **spring.main.web-application-type**; giữ **servlet** nếu đó là chủ đích |
| Không inject được **WebClient.Builder** | WebFlux chưa có trên classpath hoặc auto-configuration bị loại trừ | Bổ sung starter phù hợp và kiểm tra điều kiện auto-configuration |
| Gọi API xong controller chờ quá lâu | Chưa có timeout hoặc upstream chậm | Đặt timeout ở publisher và tầng transport |
| Thread MVC bị chiếm trong lúc gọi API | Dùng **block()** trong request thread | Giới hạn timeout/concurrency hoặc trả reactive type để MVC xử lý async |
| Lỗi 4xx/5xx bị biến thành 500 chung chung | Chưa map exception upstream tại service/API boundary | Phân loại status và chuyển thành lỗi API có chủ đích |
| JSON không decode được | Content-Type, cấu trúc JSON hoặc DTO không khớp | Kiểm tra response thực tế, codec và kiểu dữ liệu |
| Builder dùng chung bị thay đổi ngoài ý muốn | Nhiều cấu hình cùng mutate một builder | Clone builder trước khi cấu hình client riêng |
| Mỗi request tạo một WebClient mới | Client được khởi tạo trong controller hoặc method xử lý request | Đăng ký WebClient thành bean dùng lại |
| Retry gây tạo trùng đơn hàng/thanh toán | Retry thao tác không idempotent | Dùng idempotency key và chính sách retry có giới hạn |
| Gọi upstream thất bại sau khi tự cấu hình connector | Connector mới làm mất cấu hình TLS/proxy/pool hoặc observability | Kiểm tra transport settings và giữ các customizer cần thiết |

## 14. Checklist khi triển khai

Trước khi đưa WebClient vào ứng dụng MVC, hãy xác nhận:

1. Dự án vẫn có **spring-boot-starter-web** và chỉ bổ sung WebFlux cho nhu cầu client.
2. Boot nhận diện ứng dụng là Servlet/MVC; embedded server và **DispatcherServlet** vẫn được khởi tạo.
3. WebClient được build từ **WebClient.Builder** đã cấu hình và được dùng lại.
4. Base URL, credential và các header theo môi trường được quản lý bên ngoài source code.
5. Có connect/response/publisher timeout phù hợp.
6. Lỗi status, network, timeout và decode được phân loại.
7. Không block trên event-loop; nếu dùng **block()** trong MVC thì đã tính đến thread occupancy.
8. Retry chỉ áp dụng cho thao tác phù hợp và có giới hạn.
9. Log không chứa token, cookie hoặc dữ liệu nhạy cảm.
10. Có test MVC riêng và test HTTP client với mock upstream.

## 15. Ghi nhớ

Spring MVC xử lý request đi vào theo mô hình Servlet; WebClient gửi request đi ra theo API reactive. Hai thành phần có thể cùng tồn tại trong một ứng dụng Spring Boot. Khi thêm **spring-boot-starter-webflux** bên cạnh **spring-boot-starter-web**, Boot mặc định ưu tiên MVC nếu cả hai stack cùng có mặt.

Với code imperative, có thể gọi **Mono.block()** tại ranh giới service và giới hạn thời gian chờ. Với nhu cầu bất đồng bộ, MVC có thể nhận **Mono** và hoàn tất response bằng cơ chế async của Servlet mà vẫn giữ server MVC. Hãy cấu hình client dùng lại, timeout, connection pool, xử lý lỗi và kiểm thử upstream để việc tích hợp ổn định khi chạy thực tế.
