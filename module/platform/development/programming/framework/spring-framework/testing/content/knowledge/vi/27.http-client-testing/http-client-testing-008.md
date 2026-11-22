# MockMvcClientHttpRequestFactory cho luồng client tới MVC trong tiến trình

## 1. Bài toán kiểm thử HTTP client gọi vào Spring MVC

Một ứng dụng có thể chứa mã client dùng `RestClient` hoặc `RestTemplate` để gửi HTTP request đến một endpoint Spring MVC. Khi kiểm thử mã client đó, ta thường muốn xác nhận cả hai phía: client tạo đúng method, URI, header và body; controller nhận request, xử lý và trả response đúng hợp đồng.

Nếu dùng một server thật, test phải khởi động ứng dụng và gửi request qua HTTP. Nếu chỉ dùng một mock HTTP server, test có thể kiểm tra cách client gửi request nhưng response thường do test tự khai báo, không chạy qua controller thật.

`MockMvcClientHttpRequestFactory` cung cấp một lựa chọn nằm giữa hai cách này. Đây là một `ClientHttpRequestFactory` dùng `MockMvc` để thực hiện request ngay trong cùng tiến trình. `RestClient` hoặc `RestTemplate` vẫn tạo request theo API HTTP client thông thường; request được chuyển vào hạ tầng MockMvc, đi qua Spring MVC và nhận response từ controller.

Vì vậy, test có thể chạy mã client thật và controller thật trong cùng một JVM mà không cần mở port hoặc khởi động Servlet container.

`MockMvcClientHttpRequestFactory` thuộc artifact `spring-test`, trong package `org.springframework.test.web.client`. Với Gradle, dependency thường được khai báo trong test scope:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
}
```

Nếu dùng `RestClient`, dự án cần Spring Framework 6.1 trở lên vì `RestClient` được giới thiệu từ phiên bản đó. Giữ `spring-test`, `spring-web` và `spring-webmvc` cùng dòng phiên bản để tránh xung đột API. Với Spring Boot, `spring-boot-starter-test` thường đã cung cấp `spring-test`; ứng dụng MVC cũng cần dependency web tương ứng.

## 2. Cách request được chuyển qua MockMvc

`RestClient` không tự biết cách gọi controller. Nó gửi request thông qua một `ClientHttpRequestFactory`. Factory quyết định cách tạo và thực thi request. Khi factory là `MockMvcClientHttpRequestFactory`, request được chuyển thành mock Servlet request để `MockMvc` dispatch qua Spring MVC.

Luồng xử lý có thể hình dung như sau:

```text
Test
 |
 | gọi phương thức của client ứng dụng
 v
RestClient / RestTemplate
 |
 | tạo ClientHttpRequest
 v
MockMvcClientHttpRequestFactory
 |
 | chuyển request vào MockMvc
 v
DispatcherServlet và Spring MVC
 |
 | HandlerMapping -> Controller -> MessageConverter
 | ExceptionResolver / ControllerAdvice khi có lỗi
 v
MockHttpServletResponse
 |
 | chuyển status, headers và body về ClientHttpResponse
 v
RestClient / RestTemplate đọc response
 |
 v
Test xác nhận kết quả của client
```

Factory đóng vai trò cầu nối giữa API client đồng bộ và môi trường MockMvc. Mã client vẫn sử dụng URI, HTTP method, header và body như khi gọi một địa chỉ HTTP thông thường. Ở phía server, Spring MVC xử lý request qua `DispatcherServlet`, mapping, controller, argument resolver, message converter và exception resolver đã được cấu hình trong MockMvc.

Đây là xử lý trong tiến trình. Host và port trong URI giúp client tạo địa chỉ request, nhưng không có kết nối TCP đến host đó. MockMvc nhận request trực tiếp trong JVM.

## 3. Tạo MockMvc và gắn vào RestClient

Ví dụ đơn giản nhất dùng `MockMvcBuilders.standaloneSetup(...)` để tạo môi trường MVC cho một controller:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new ProductController())
        .build();

RestClient restClient = RestClient.builder()
        .baseUrl("http://localhost")
        .requestFactory(new MockMvcClientHttpRequestFactory(mockMvc))
        .build();
```

Có hai điểm quan trọng trong cấu hình:

- `MockMvcBuilders.standaloneSetup(...)` tạo MockMvc với controller được chỉ định và hạ tầng MVC cơ bản. Cách này phù hợp với test nhỏ, tập trung vào controller cụ thể.
- `requestFactory(...)` thay factory mặc định của `RestClient` bằng factory kết nối đến MockMvc. Từ đây các request của client được xử lý trong tiến trình.

`baseUrl("http://localhost")` là địa chỉ cơ sở để `RestClient` phân giải URI tương đối. Với factory này, `localhost` không cần có server đang lắng nghe. Có thể dùng một host giả nhất quán trong test; điều quan trọng là path, query và các phần request mà controller cần nhận.

Nếu controller phụ thuộc service, repository hoặc các bean Spring khác, có thể tạo controller với dependency giả trong test, hoặc dùng `MockMvc` được dựng từ `WebApplicationContext` để sử dụng cấu hình ứng dụng.

## 4. Ví dụ đầy đủ: RestClient gọi controller trong cùng JVM

Giả sử ứng dụng có endpoint trả về thông tin sản phẩm:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

record Product(long id, String name) {
}

@RestController
class ProductController {

    @GetMapping("/api/products/{id}")
    Product findById(@PathVariable long id) {
        return new Product(id, "Mechanical Keyboard");
    }
}
```

Mã client là thành phần mà test muốn kiểm thử. Nó sử dụng `RestClient` để gọi endpoint và chuyển JSON response thành `Product`:

```java
import org.springframework.web.client.RestClient;

class ProductApiClient {

    private final RestClient restClient;

    ProductApiClient(RestClient restClient) {
        this.restClient = restClient;
    }

    Product findById(long id) {
        return restClient.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}
```

Test kết nối client với controller qua MockMvc:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

class ProductApiClientTests {

    @Test
    void readsProductThroughMvcInTheSameProcess() {
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new ProductController())
                .build();

        RestClient restClient = RestClient.builder()
                .baseUrl("http://localhost")
                .requestFactory(new MockMvcClientHttpRequestFactory(mockMvc))
                .build();

        ProductApiClient client = new ProductApiClient(restClient);

        Product product = client.findById(42);

        assertThat(product).isEqualTo(new Product(42, "Mechanical Keyboard"));
    }
}
```

Test trên thực hiện một chuỗi đầy đủ ở mức ứng dụng:

1. Gọi `ProductApiClient.findById(42)` như mã nghiệp vụ.
2. `RestClient` tạo GET request đến `/api/products/42`.
3. Factory chuyển request vào MockMvc.
4. Spring MVC gọi `ProductController.findById(...)` và ghi object thành JSON qua message converter.
5. Factory trả response cho `RestClient`, rồi `RestClient` giải mã JSON thành `Product`.
6. Test xác nhận object nhận được.

Ví dụ dùng record để giữ mã ngắn gọn. Jackson cần có trên test runtime classpath để tuần tự hóa và giải tuần tự hóa JSON. Nếu ứng dụng dùng message converter hoặc cấu hình Jackson tùy chỉnh, nên tạo MockMvc từ application context để test dùng đúng cấu hình đó.

## 5. Dùng WebApplicationContext để có cấu hình MVC đầy đủ

`standaloneSetup(...)` phù hợp khi muốn kiểm thử controller riêng lẻ. Trong ứng dụng thực tế, controller thường chạy cùng interceptor, controller advice, validator, converter và các cấu hình MVC khác. Khi cần kiểm thử client với toàn bộ cấu hình MVC đã nạp, hãy tạo MockMvc từ `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.client.RestClient;

@SpringJUnitConfig(WebConfig.class)
@WebAppConfiguration
class ProductApiClientContextTests {

    @Autowired
    private WebApplicationContext context;

    private ProductApiClient client;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .build();

        RestClient restClient = RestClient.builder()
                .baseUrl("http://localhost")
                .requestFactory(new MockMvcClientHttpRequestFactory(mockMvc))
                .build();

        client = new ProductApiClient(restClient);
    }

    @Test
    void usesMvcConfigurationFromTheApplicationContext() {
        Product product = client.findById(42);

        assertThat(product).isEqualTo(new Product(42, "Mechanical Keyboard"));
    }
}
```

`WebConfig` đại diện cho cấu hình Spring MVC của ứng dụng và cần đăng ký controller cùng các bean cần thiết. `webAppContextSetup(context)` dựng MockMvc dựa trên `WebApplicationContext`, do đó request có thể đi qua cấu hình MVC đã nạp thay vì chỉ dùng cấu hình mặc định của standalone setup.

Nếu ứng dụng có Servlet filter cần tham gia test, hãy bảo đảm filter được đăng ký trong cấu hình MockMvc phù hợp, ví dụ thông qua `addFilters(...)` khi dựng MockMvc. Không nên giả định mọi cấu hình của Servlet container thật đều tự xuất hiện trong MockMvc.

## 6. Kiểm tra method, header và request body

Vì client vẫn tạo request thông qua `ClientHttpRequestFactory`, test có thể xác nhận các hành vi HTTP mà mã client thực hiện. Ví dụ, một client gửi POST JSON kèm header:

```java
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record CreateProductRequest(String name) {
}

class ProductApiClient {

    private final RestClient restClient;

    ProductApiClient(RestClient restClient) {
        this.restClient = restClient;
    }

    Product create(String name) {
        return restClient.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Client-Name", "catalog-client")
                .body(new CreateProductRequest(name))
                .retrieve()
                .body(Product.class);
    }
}
```

Mở rộng `ProductController` ở ví dụ trên bằng method nhận body và header như một endpoint MVC bình thường. Các import tương ứng được khai báo ở đầu file controller:

```java
// Thêm phương thức này vào ProductController.
@PostMapping("/api/products")
ResponseEntity<Product> create(
        @RequestBody CreateProductRequest request,
        @RequestHeader("X-Client-Name") String clientName) {

    Product created = new Product(100, request.name() + " / " + clientName);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
```

Trong test, tạo MockMvc và RestClient như ví dụ trước, sau đó gọi `client.create("Desk Lamp")` và xác nhận sản phẩm trả về có nội dung mong đợi. Nếu request thiếu `Content-Type`, gửi JSON không đúng định dạng hoặc thiếu header bắt buộc, Spring MVC có thể trả về lỗi tương ứng; lỗi đó cũng đi ngược về RestClient như một HTTP response.

Ví dụ này kiểm thử đồng thời cách client mã hóa body/header và cách MVC nhận chúng. Khi chỉ muốn kiểm tra request được gửi ra mà không chạy controller thật, một mock HTTP server sẽ phù hợp hơn.

## 7. Dùng với RestTemplate

`MockMvcClientHttpRequestFactory` triển khai `ClientHttpRequestFactory`, nên cũng có thể được dùng với `RestTemplate`:

```java
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestTemplate;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new ProductController())
        .build();

RestTemplate restTemplate = new RestTemplate(
        new MockMvcClientHttpRequestFactory(mockMvc));

Product product = restTemplate.getForObject(
        "http://localhost/api/products/{id}", Product.class, 42);
```

Điều này hữu ích khi dự án vẫn có mã client dùng `RestTemplate`. Có thể kiểm thử client hiện tại qua MockMvc mà không cần thay đổi mã nghiệp vụ chỉ để chuyển sang `RestClient`.

Với `RestClient`, factory được đặt trên builder bằng `requestFactory(...)`. Với `RestTemplate`, factory được truyền vào constructor hoặc cấu hình trên instance. Cả hai đều dùng cùng một cơ chế bridge đến MockMvc.

## 8. So sánh với MockRestServiceServer và server thật

Các công cụ này giải quyết những mục tiêu khác nhau:

| Phương án | Điều gì được thực thi? | Phù hợp khi |
|---|---|---|
| `MockMvcClientHttpRequestFactory` | Client thật của ứng dụng gửi request vào Spring MVC thật trong MockMvc | Muốn kiểm thử luồng client tới controller và kiểm tra tương tác giữa hai phía trong cùng tiến trình. |
| `MockRestServiceServer` | Client thật gửi request; mock server trả response được khai báo bằng expectation | Muốn kiểm tra URL, method, header, body và cách client xử lý response từ dịch vụ phụ thuộc. |
| MockWebServer hoặc WireMock | Client thật giao tiếp với HTTP server giả qua network | Muốn kiểm tra transport HTTP và mô phỏng dịch vụ ngoài qua socket. |
| Embedded server hoặc môi trường đang chạy | Client gửi request qua HTTP đến ứng dụng thực | Muốn kiểm thử cả Servlet container, cổng mạng và cấu hình runtime. |

Ví dụ về sự khác nhau:

- Với `MockRestServiceServer`, test có thể khai báo: khi client gọi GET `/products/42`, trả về JSON cố định. Controller không được chạy.
- Với `MockMvcClientHttpRequestFactory`, GET `/products/42` được chuyển đến mapping và controller thật trong MockMvc. Response phụ thuộc logic MVC đang chạy.
- Với embedded server, request đi qua socket đến ứng dụng đang lắng nghe trên một port, nên có thể phát hiện vấn đề liên quan đến container hoặc network mà MockMvc không mô phỏng.

Nếu mục tiêu là kiểm thử adapter gọi một dịch vụ bên ngoài, `MockRestServiceServer` hoặc mock HTTP server thường là lựa chọn đúng. Nếu mục tiêu là kiểm thử một HTTP client trong ứng dụng gọi endpoint Spring MVC nội bộ, `MockMvcClientHttpRequestFactory` giúp kết nối hai phía mà không cần dựng hạ tầng mạng.

## 9. Phạm vi và giới hạn của cách kiểm thử trong tiến trình

Factory này kiểm thử hành vi ở ranh giới `ClientHttpRequestFactory` và Spring MVC. Nó có thể xác nhận request được tạo ra, MVC xử lý request và client đọc response. Tuy nhiên, test không đi qua HTTP server hoặc Servlet container thật.

Do đó, test này không xác nhận:

- Port thực sự được bind, DNS hoặc kết nối TCP.
- TLS handshake, chứng chỉ, proxy, socket timeout và cấu hình connection pool của HTTP client trong môi trường mạng.
- Cách Servlet container thật xử lý connector, thread pool, giới hạn request, multipart hoặc các đặc tính triển khai riêng.
- Hành vi streaming hoặc truyền dữ liệu trên đường truyền mạng như khi client giao tiếp với server thật.

MockMvc vẫn chạy hạ tầng Spring MVC đã được cấu hình, nhưng nó không thay thế kiểm thử tích hợp với server thật. Nên dùng factory này cho test nhanh và tập trung vào luồng client-to-MVC; bổ sung kiểm thử server thật khi hợp đồng cần xác nhận cả transport hoặc container.

`MockMvcClientHttpRequestFactory` dành cho Spring MVC trên Servlet stack. Nó không phải factory để dispatch đến WebFlux handler. Nếu ứng dụng dùng WebFlux, `WebTestClient` cung cấp cách bind và kiểm thử phù hợp với reactive web stack.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy `MockMvcClientHttpRequestFactory` | Thiếu `spring-test` hoặc phiên bản Spring không có class này. | Thêm `spring-test` vào test classpath và đồng bộ phiên bản với Spring Framework đang dùng. |
| Request vẫn đi ra network | `RestClient` chưa được cấu hình dùng factory MockMvc hoặc mã client tạo một client khác. | Truyền đúng `MockMvcClientHttpRequestFactory` vào `requestFactory(...)` của builder được client sử dụng. |
| Nhận `404 Not Found` | URI path không khớp mapping hoặc controller chưa được đăng ký trong MockMvc. | Kiểm tra base URL, path, HTTP method và controller được đưa vào setup. |
| Nhận `415 Unsupported Media Type` | Client gửi body với Content-Type không được endpoint hỗ trợ. | Đặt content type đúng và kiểm tra message converter của MockMvc. |
| Nhận `406 Not Acceptable` | Header Accept không tương thích với kiểu response mà MVC có thể tạo. | Kiểm tra Accept, produces và converter được đăng ký. |
| JSON không được chuyển đổi | Jackson hoặc converter cần thiết không có trên test classpath/cấu hình MVC. | Bổ sung dependency phù hợp và dùng `webAppContextSetup` khi cần cấu hình converter của ứng dụng. |
| Filter hoặc controller advice không chạy | MockMvc được dựng theo standalone setup hoặc chưa đăng ký thành phần tương ứng. | Dựng MockMvc từ WebApplicationContext và đăng ký filter/configuration cần kiểm thử. |
| Test qua nhưng ứng dụng triển khai thật lỗi kết nối | Test chỉ chạy trong tiến trình và không tạo socket hoặc khởi động container. | Bổ sung kiểm thử với embedded server hoặc môi trường tích hợp thực. |

## 11. Quy trình áp dụng

Khi dùng `MockMvcClientHttpRequestFactory`, có thể thực hiện theo trình tự:

1. Xác định mã client đang dùng `RestClient` hay `RestTemplate` và giữ nguyên API của mã client đó.
2. Tạo `MockMvc` bằng `standaloneSetup(...)` cho controller đơn giản hoặc `webAppContextSetup(...)` cho cấu hình MVC đầy đủ.
3. Tạo `MockMvcClientHttpRequestFactory` từ MockMvc vừa dựng.
4. Gắn factory vào `RestClient.Builder.requestFactory(...)` hoặc constructor của `RestTemplate`.
5. Cung cấp base URL để client tạo URI hoàn chỉnh; host không cần có server đang lắng nghe.
6. Gọi phương thức client như trong mã ứng dụng và xác nhận kết quả, exception hoặc side effect cần thiết.
7. Dùng mock HTTP server cho dịch vụ ngoài và dùng embedded server khi cần kiểm tra transport/container thật.

## 12. Kết luận

`MockMvcClientHttpRequestFactory` nối một HTTP client dựa trên `ClientHttpRequestFactory` với `MockMvc`. Nhờ đó, `RestClient` hoặc `RestTemplate` có thể gửi request theo API thông thường, nhưng request được dispatch đến Spring MVC ngay trong cùng tiến trình. Cách này phù hợp để kiểm thử sự phối hợp giữa mã client và controller mà không cần mở port hoặc chạy Servlet container. Khi cần kiểm tra network, TLS hoặc hành vi container, vẫn cần một kiểm thử tích hợp với server thật.
