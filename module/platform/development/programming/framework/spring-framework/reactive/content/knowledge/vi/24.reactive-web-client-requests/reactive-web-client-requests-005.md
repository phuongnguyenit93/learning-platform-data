# Gửi đối tượng qua bodyValue trong Spring WebClient

## 1. bodyValue giải quyết việc gì?

**WebClient** là HTTP client reactive của Spring WebFlux. Khi gửi request POST, PUT hoặc PATCH, ứng dụng thường cần serialize một object Java thành JSON để gửi trong HTTP body.

Ví dụ có một object:

~~~java
ProductRequest request = new ProductRequest(
    "BK-01",
    "Reactive Guide",
    new BigDecimal("12.50"),
    2
);
~~~

Ta có thể gửi object đó bằng **bodyValue(request)**:

~~~java
Mono<ProductResponse> result = webClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Spring chọn HTTP message writer phù hợp để encode object thành request body. Với JSON và Jackson có trên classpath, object Java được serialize thành JSON. Ứng dụng không cần tự gọi ObjectMapper để biến object thành chuỗi JSON.

**bodyValue dành cho một giá trị cụ thể đã có sẵn**, chẳng hạn DTO, record, Map hoặc collection. Khi nguồn body là Mono/Flux hoặc một reactive producer, dùng **body(...)** để WebClient tiêu thụ Publisher.

Bài học tập trung vào:

- Khác biệt giữa bodyValue(Object) và body(Publisher, elementType).
- Cách Content-Type, Accept và HTTP message codecs quyết định serialization.
- Gửi DTO/record, Map, form data và multipart.
- Đọc response bằng retrieve(), onStatus() và exchangeToMono().
- Xử lý lỗi, retry, timeout và response body lifecycle.
- Cấu hình WebClient dùng lại trong ứng dụng Spring Boot.
- Kiểm thử request body bằng MockWebServer và StepVerifier.

## 2. bodyValue nằm ở đâu trong fluent API?

Một request WebClient thường được xây dựng theo các bước:

~~~text
WebClient
   |
   v
post() / put() / patch()
   |
   v
uri(...)
   |
   v
headers / contentType / accept
   |
   v
bodyValue(object)
   |
   v
retrieve() hoặc exchangeToMono()
   |
   v
bodyToMono(...) / bodyToFlux(...)
~~~

Ví dụ:

~~~java
webClient.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(order)
    .retrieve()
    .bodyToMono(OrderResponse.class);
~~~

- **post()** chọn HTTP method.
- **uri(...)** chọn URL/path và URI variables.
- **contentType(...)** mô tả định dạng của request body.
- **accept(...)** mô tả định dạng response client mong muốn.
- **bodyValue(...)** cung cấp một giá trị body cụ thể.
- **retrieve()** bắt đầu khai báo cách xử lý response.
- **bodyToMono(...)** decode response thành kiểu Java.

Kết quả là một **Mono<OrderResponse>**. WebClient giữ mô hình reactive; không cần block trong service hoặc controller.

## 3. bodyValue(Object) khác body(Publisher, Class) thế nào?

Đây là khác biệt quan trọng nhất.

| API | Đầu vào | Dùng khi |
| --- | --- | --- |
| **bodyValue(object)** | Một object cụ thể | Đã có DTO/record/Map cần gửi |
| **body(publisher, Class)** | Publisher như Mono hoặc Flux | Body được phát bất đồng bộ |
| **body(publisher, ParameterizedTypeReference)** | Publisher có kiểu phần tử generic | Cần giữ thông tin kiểu generic |
| **body(BodyInserter)** | BodyInserter tùy biến | Cần kiểm soát cách ghi body |
| **bodyValue(MultiValueMap<String,String>)** | Form data dạng key/value | Gửi application/x-www-form-urlencoded |
| **body(MultipartBodyBuilder.build())** | Multipart parts | Gửi field, JSON part và file |

### 3.1. bodyValue dành cho object đơn

~~~java
ProductRequest product = new ProductRequest(
    "BK-01",
    "Reactive Guide",
    new BigDecimal("12.50"),
    2
);

Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Request body được encode từ object ProductRequest. Việc serialize chỉ diễn ra khi request được subscribe và gửi đi; lời gọi bodyValue không tự thực hiện một request đồng bộ.

### 3.2. Publisher phải dùng body(...)

Không dùng:

~~~java
Mono<ProductRequest> productMono = Mono.just(product);

webClient.post()
    .uri("/products")
    .bodyValue(productMono);
~~~

**bodyValue không nhận Publisher hoặc kiểu được ReactiveAdapterRegistry hỗ trợ**. Spring có thể ném IllegalArgumentException vì nó không thể coi một Publisher là một object đơn cần serialize.

Dùng:

~~~java
Mono<ProductRequest> productMono = Mono.just(product);

Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .body(productMono, ProductRequest.class)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Với Flux:

~~~java
Flux<ProductRequest> products = Flux.just(product1, product2);

Mono<Void> sent = webClient.post()
    .uri("/products/import")
    .contentType(MediaType.APPLICATION_STREAM_JSON)
    .body(products, ProductRequest.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

Publisher được tiêu thụ theo demand của pipeline. Đây là cách phù hợp với dữ liệu phát dần hoặc stream lớn.

### 3.3. bodyValue không phải block()

Tên bodyValue không có nghĩa là thao tác blocking. Nó chỉ phân biệt body là một giá trị cụ thể thay vì Publisher. Request vẫn được thực hiện bất đồng bộ và trả về Mono/Flux.

Không viết:

~~~java
ProductResponse response = webClient.post()
    .uri("/products")
    .bodyValue(product)
    .retrieve()
    .bodyToMono(ProductResponse.class)
    .block();
~~~

trong controller WebFlux hoặc service reactive. Hãy trả Publisher cho tầng gọi tiếp theo:

~~~java
return webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Chỉ cân nhắc block ở ranh giới imperative/CLI hoặc trong test khi thật sự cần.

## 4. Serialization: object Java trở thành HTTP body như thế nào?

WebClient dùng **HTTP message codecs** để encode request body. Codec được chọn dựa trên kiểu object, Content-Type và các codec đã đăng ký trong ClientCodecConfigurer.

Ví dụ với JSON:

~~~java
ProductRequest request = new ProductRequest(
    "BK-01",
    "Reactive Guide",
    new BigDecimal("12.50"),
    2
);

webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request);
~~~

Nếu Jackson được cấu hình, JSON có thể là:

~~~json
{
  "sku": "BK-01",
  "name": "Reactive Guide",
  "price": 12.50,
  "quantity": 2
}
~~~

Spring Boot WebFlux thường cung cấp Jackson JSON codec khi dependency phù hợp có mặt. Trong project tùy chỉnh, hãy kiểm tra ClientCodecConfigurer và dependency Jackson nếu object không được serialize như mong đợi.

### 4.1. Content-Type và Accept là hai ý nghĩa khác nhau

- **Content-Type: application/json**: body request được gửi ở dạng JSON.
- **Accept: application/json**: client muốn server trả response ở dạng JSON.

Ví dụ:

~~~java
webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Đặt rõ hai header giúp contract dễ đọc và tránh phụ thuộc vào default behavior của server.

### 4.2. Không tự serialize thành String nếu không cần

Không cần:

~~~java
String json = objectMapper.writeValueAsString(request);

webClient.post()
    .uri("/products")
    .bodyValue(json);
~~~

Ở đây bodyValue nhận một String, không còn nhận DTO. Writer có thể chọn cách ghi String thay vì serialize object bằng JSON codec. Nếu tự serialize, bạn phải tự kiểm soát Content-Type, encoding, escaping và lỗi serialization.

Thông thường nên truyền object gốc:

~~~java
webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request);
~~~

### 4.3. DTO, record, Map và collection

bodyValue có thể nhận nhiều dạng object:

~~~java
.bodyValue(new ProductRequest(...))
~~~

~~~java
.bodyValue(Map.of(
    "sku", "BK-01",
    "quantity", 2
))
~~~

~~~java
.bodyValue(List.of(product1, product2))
~~~

Với collection, codec serialize cấu trúc collection thành JSON array nếu Content-Type và codec được chọn phù hợp. Nếu muốn phát từng phần tử theo stream, dùng Flux với body(...), không gom toàn bộ danh sách chỉ để dùng bodyValue.

### 4.4. Null và body rỗng

bodyValue dùng cho một giá trị thực tế; không truyền null. Nếu request không có body, dùng API body rỗng phù hợp hoặc bỏ qua bước body.

Không dùng chuỗi "null" để giả lập body rỗng. JSON null và HTTP request không có body là hai nội dung khác nhau.

## 5. Gửi form data và multipart

bodyValue cũng có thể gửi dữ liệu form, nhưng cần phân biệt hai loại.

### 5.1. URL-encoded form

Dùng **MultiValueMap<String,String>**:

~~~java
MultiValueMap<String, String> form =
    new LinkedMultiValueMap<>();

form.add("username", "lan");
form.add("role", "student");

Mono<String> response = webClient.post()
    .uri("/login")
    .bodyValue(form)
    .retrieve()
    .bodyToMono(String.class);
~~~

Với MultiValueMap<String,String>, **FormHttpMessageWriter** tự đặt Content-Type là **application/x-www-form-urlencoded**.

Dạng khác là dùng BodyInserters:

~~~java
Mono<String> response = webClient.post()
    .uri("/login")
    .body(BodyInserters.fromFormData("username", "lan")
        .with("role", "student"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Không đặt application/json cho form-urlencoded body.

### 5.2. Multipart form data

Khi request chứa file, field text và JSON part, dùng **MultipartBodyBuilder**:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();

builder.part("description", "Product manual");
builder.part("metadata", productRequest)
    .contentType(MediaType.APPLICATION_JSON);
builder.part(
    "file",
    new FileSystemResource("/srv/files/manual.pdf")
);

MultiValueMap<String, HttpEntity<?>> parts = builder.build();

Mono<String> response = webClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .retrieve()
    .bodyToMono(String.class);
~~~

Multipart writer tạo boundary và encode từng part. Thông thường không tự đặt header multipart/form-data bằng một chuỗi cố định vì Content-Type phải chứa boundary tương ứng với body.

Spring xác định Content-Type của từng part từ writer được chọn hoặc từ Resource/file extension; có thể chỉ định rõ khi cần.

### 5.3. Multipart streaming với PartEvent

Với file lớn hoặc cần stream từng part, WebClient hỗ trợ **PartEvent**. Có thể ghép FormPartEvent và FilePartEvent bằng Flux.concat rồi dùng body(...). Đây là đường streaming multipart; không gom toàn bộ file vào byte[] chỉ để truyền bằng bodyValue.

## 6. BodyInserters và bodyValue

**BodyInserters** cung cấp API mức thấp để tạo BodyInserter. bodyValue là shortcut tiện lợi cho trường hợp một object.

Ví dụ tương đương:

~~~java
.bodyValue(product)
~~~

và:

~~~java
.body(BodyInserters.fromValue(product))
~~~

**BodyInserters.fromValue(...)** cũng dành cho một giá trị đơn. Nó ném IllegalArgumentException nếu đối tượng là Publisher hoặc một kiểu được ReactiveAdapterRegistry hỗ trợ; với trường hợp đó hãy dùng fromPublisher/fromProducer hoặc WebClient.body(...).

Các API thường gặp:

| API | Mục đích |
| --- | --- |
| **BodyInserters.fromValue(value)** | Ghi một giá trị đơn |
| **BodyInserters.fromPublisher(publisher, Class)** | Ghi Publisher với kiểu phần tử |
| **BodyInserters.fromPublisher(publisher, ParameterizedTypeReference)** | Ghi Publisher có kiểu generic |
| **BodyInserters.fromProducer(producer, Class)** | Ghi producer được ReactiveAdapterRegistry hỗ trợ |
| **BodyInserters.fromFormData(...)** | Ghi form-urlencoded |
| **BodyInserters.fromMultipartData(...)** | Ghi multipart data |

Không dùng **fromObject(...)** trong code mới; API này đã deprecated từ Spring Framework 5.2 để chuyển sang fromValue(...).

## 7. Xử lý response sau khi gửi body

Gửi request body mới là một nửa của thao tác HTTP. WebClient cần decode response hoặc xử lý status.

### 7.1. retrieve() và bodyToMono()

Ví dụ:

~~~java
Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

- **retrieve()** khai báo cách đọc response.
- **bodyToMono(ProductResponse.class)** decode body thành một object.
- **bodyToFlux(ProductResponse.class)** decode một stream object.
- **toEntity(ProductResponse.class)** lấy cả status, headers và body.
- **toBodilessEntity()** lấy metadata response khi không cần body.

Mặc định, response status 4xx hoặc 5xx làm WebClient phát **WebClientResponseException** hoặc subtype tương ứng.

### 7.2. Tùy chỉnh lỗi bằng onStatus()

Ví dụ:

~~~java
Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .onStatus(
        HttpStatusCode::is4xxClientError,
        clientResponse -> clientResponse
            .bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RemoteApiException(
                clientResponse.statusCode(),
                body
            ))
    )
    .bodyToMono(ProductResponse.class);
~~~

Ví dụ giả định có class **RemoteApiException** nhận HttpStatusCode và nội dung lỗi. onStatus giúp chuyển response lỗi thành exception theo contract ứng dụng.

Không đọc body lỗi ở một nơi rồi cố đọc lại lần nữa ở downstream. Response body là stream; hãy tiêu thụ đúng một lần hoặc chuyển nó thành dữ liệu lỗi cần thiết trước khi phát exception.

### 7.3. exchangeToMono() khi cần kiểm soát status

Khi cần quyết định decode khác nhau theo status, dùng **exchangeToMono()** hoặc **exchangeToFlux()**:

~~~java
Mono<ProductResponse> response = webClient.get()
    .uri("/products/{sku}", sku)
    .exchangeToMono(clientResponse -> {
        if (clientResponse.statusCode().is2xxSuccessful()) {
            return clientResponse.bodyToMono(ProductResponse.class);
        }

        if (clientResponse.statusCode().value() == 404) {
            return Mono.empty();
        }

        return clientResponse.createError();
    });
~~~

Đây là ví dụ cho API tìm sản phẩm. exchangeToMono cho phép kiểm soát việc đọc response dựa trên status, headers hoặc media type. Sau khi Publisher được trả từ callback hoàn tất, Spring kiểm tra và release body chưa được consume để tránh rò rỉ connection/buffer.

Nếu cần body lỗi, hãy decode nó bên trong callback trước khi hoàn tất. Không giữ ClientResponse rồi cố đọc body ở một pipeline khác sau khi callback đã kết thúc.

## 8. Cấu hình và tái sử dụng WebClient

Trong ứng dụng Spring Boot, nên tạo WebClient dùng lại thay vì tạo mới trong mỗi lần gọi.

Ví dụ:

~~~java
@Configuration
public class WebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
        WebClient.Builder builder
    ) {
        return builder
            .baseUrl("https://inventory.example")
            .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
            )
            .build();
    }
}
~~~

Service nhận bean:

~~~java
@Service
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(
        @Qualifier("inventoryWebClient") WebClient webClient
    ) {
        this.webClient = webClient;
    }

    public Mono<ProductResponse> create(ProductRequest request) {
        return webClient.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProductResponse.class);
    }
}
~~~

WebClient sau khi build có thể được tái sử dụng cho nhiều request. Có thể cấu hình base URL, default headers, filter, connector, timeout và codec ở builder.

Không tạo WebClient mới ở mỗi method call nếu không có yêu cầu connector riêng. Reuse giúp dùng connection pool và cấu hình thống nhất.

### 8.1. Headers và authentication

Có thể thêm header riêng cho từng request:

~~~java
webClient.post()
    .uri("/api/products")
    .headers(headers -> {
        headers.setBearerAuth(accessToken);
        headers.set("X-Request-Id", requestId);
    })
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Không hardcode token hoặc secret trong source. Token nên được lấy từ security context, credential provider hoặc cơ chế quản lý secret phù hợp.

### 8.2. URI variables và query parameters

Ví dụ:

~~~java
webClient.post()
    .uri(builder -> builder
        .path("/api/products/{sku}")
        .queryParam("notify", true)
        .build(sku))
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Dùng URI builder để encode path/query value đúng cách. Tránh nối chuỗi thủ công khi dữ liệu có ký tự đặc biệt.

### 8.3. Filter dùng chung

Exchange filter có thể thêm logging, correlation ID, authentication hoặc metrics. Không log raw body nhạy cảm một cách mặc định. Filter nên giữ response body lifecycle đúng và không subscribe thủ công vào request/response Publisher.

## 9. Timeout, retry và tính idempotent

WebClient là reactive client, nhưng request vẫn có thể thất bại vì connect timeout, response timeout, DNS, TLS, server error hoặc network disconnect.

Có thể đặt timeout cho một thao tác:

~~~java
return webClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class)
    .timeout(Duration.ofSeconds(5));
~~~

Đây là timeout cho Publisher ở tầng ứng dụng. Timeout kết nối/đọc ở transport connector cần được cấu hình phù hợp riêng; timeout của Mono không thay thế mọi timeout mạng.

### 9.1. Retry không phải lúc nào cũng an toàn

Ví dụ:

~~~java
return inventoryClient.create(request)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(this::isTransientFailure)
    );
~~~

Retry chỉ nên áp dụng cho lỗi tạm thời được xác định rõ. Với POST tạo dữ liệu, server có thể đã ghi thành công nhưng response bị mất; retry có thể tạo bản ghi trùng.

Các biện pháp:

- Dùng **Idempotency-Key** cho thao tác tạo nếu API hỗ trợ.
- Chỉ retry lỗi kết nối/timeout phù hợp với chính sách nghiệp vụ.
- Không retry validation error hoặc lỗi authorization.
- Đặt giới hạn số lần và backoff.
- Ghi log correlation ID và idempotency key.

### 9.2. BodyValue và request replay

bodyValue nhận một object cụ thể, nhưng việc gửi lại request vẫn phụ thuộc Publisher và body inserter có thể tạo lại nội dung hay không. Không giả định mọi body stream đều replayable. Với body từ file stream hoặc nguồn một lần, cần thiết kế retry và mở lại nguồn đúng cách.

## 10. Ví dụ Java 17+ chạy được: gửi DTO bằng bodyValue

Ví dụ dùng **Spring Boot 3.3.5**, Spring Framework 6.1.x và Java 17. Project minh họa một ProductClient gửi record qua JSON bằng bodyValue và kiểm thử request thực tế bằng MockWebServer.

Cấu trúc:

~~~text
webclient-bodyvalue-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/bodyvalue/
    │           ├── ProductRequest.java
    │           ├── ProductResponse.java
    │           └── ProductClient.java
    └── test/
        └── java/
            └── com/example/bodyvalue/
                └── ProductClientTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-bodyvalue-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 10.2. ProductRequest.java

~~~java
package com.example.bodyvalue;

import java.math.BigDecimal;

public record ProductRequest(
    String sku,
    String name,
    BigDecimal price,
    int quantity
) {}
~~~

Record là DTO bất biến phù hợp để biểu diễn request data. Jackson trong Spring Boot có thể serialize record thành JSON.

### 10.3. ProductResponse.java

~~~java
package com.example.bodyvalue;

public record ProductResponse(
    String id,
    String status
) {}
~~~

### 10.4. ProductClient.java

~~~java
package com.example.bodyvalue;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class ProductClient {

    private final WebClient webClient;

    public ProductClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<ProductResponse> create(ProductRequest request) {
        return webClient.post()
            .uri("/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProductResponse.class);
    }
}
~~~

ProductClient nhận WebClient đã được cấu hình từ bên ngoài. Method create chỉ mô tả request và trả Publisher; nó không block và không tự tạo client mới.

### 10.5. ProductClientTest.java

~~~java
package com.example.bodyvalue;

import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ProductClientTest {

    private MockWebServer server;
    private ProductClient client;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() throws Exception {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new ProductClient(webClient);
    }

    @AfterEach
    void tearDown() throws Exception {
        server.shutdown();
    }

    @Test
    void serializesRecordAsJsonRequestBody() throws Exception {
        server.enqueue(
            new MockResponse()
                .setResponseCode(201)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody(
                    "{\"id\":\"P-100\",\"status\":\"created\"}"
                )
        );

        ProductRequest request = new ProductRequest(
            "BK-01",
            "Reactive Guide",
            new BigDecimal("12.50"),
            2
        );

        StepVerifier.create(client.create(request))
            .assertNext(response -> {
                assertEquals("P-100", response.id());
                assertEquals("created", response.status());
            })
            .verifyComplete();

        RecordedRequest recorded =
            server.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(recorded);
        assertEquals("POST", recorded.getMethod());
        assertEquals("/products", recorded.getPath());
        assertTrue(
            recorded.getHeader("Content-Type")
                .startsWith(MediaType.APPLICATION_JSON_VALUE)
        );
        assertEquals(
            MediaType.APPLICATION_JSON_VALUE,
            recorded.getHeader("Accept")
        );

        JsonNode json = objectMapper.readTree(
            recorded.getBody().readUtf8()
        );

        assertEquals("BK-01", json.get("sku").asText());
        assertEquals("Reactive Guide", json.get("name").asText());
        assertEquals(
            0,
            new BigDecimal("12.50")
                .compareTo(json.get("price").decimalValue())
        );
        assertEquals(2, json.get("quantity").asInt());
    }

    @Test
    void mapsBadRequestToWebClientResponseException() {
        server.enqueue(
            new MockResponse()
                .setResponseCode(400)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody("{\"code\":\"INVALID_PRODUCT\"}")
        );

        ProductRequest request = new ProductRequest(
            "INVALID",
            "Broken Product",
            BigDecimal.ONE,
            1
        );

        StepVerifier.create(client.create(request))
            .expectError(WebClientResponseException.BadRequest.class)
            .verify();
    }
}
~~~

Test đầu kiểm tra response được decode thành ProductResponse và request thực tế chứa JSON đúng field. Test thứ hai xác nhận retrieve() mặc định chuyển HTTP 400 thành WebClientResponseException.BadRequest.

### 10.6. Chạy test

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
~~~

Maven chạy JUnit test. MockWebServer nhận HTTP request thật từ WebClient, cho phép kiểm tra method, path, Content-Type, Accept và JSON body mà không cần gọi một dịch vụ bên ngoài.

## 11. Ví dụ sử dụng WebClient trong Spring Boot

Khi tích hợp vào ứng dụng, có thể đăng ký bean:

~~~java
@Configuration
public class InventoryClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("http://localhost:8081")
            .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
            )
            .build();
    }
}
~~~

Inject vào service:

~~~java
@Service
public class InventoryService {

    private final WebClient inventoryWebClient;

    public InventoryService(
        @Qualifier("inventoryWebClient")
        WebClient inventoryWebClient
    ) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<ProductResponse> create(ProductRequest request) {
        return inventoryWebClient.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProductResponse.class);
    }
}
~~~

Controller gọi service:

~~~java
@PostMapping("/products")
public Mono<ProductResponse> create(
    @RequestBody ProductRequest request
) {
    return inventoryService.create(request);
}
~~~

Toàn bộ đường đi vẫn reactive. Controller nhận object từ request của client, service gửi object đó sang service khác bằng bodyValue, rồi trả Publisher cho WebFlux.

Nếu service đích có thể trả lỗi nghiệp vụ, hãy bổ sung onStatus hoặc exchangeToMono theo contract của API đích.

## 12. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| IllegalArgumentException khi gọi bodyValue | Đã truyền Mono, Flux hoặc reactive producer | Dùng body(publisher, Class) |
| Server không parse được JSON | Content-Type sai hoặc codec JSON không có | Đặt application/json và kiểm tra Jackson codec |
| Server nhận chuỗi JSON có dấu ngoặc kép lồng nhau | Đã serialize DTO thành String rồi bodyValue(String) | Truyền DTO gốc cho bodyValue |
| Server trả 415 Unsupported Media Type | Content-Type không được endpoint hỗ trợ | Đặt đúng media type theo API contract |
| Server trả 406 Not Acceptable | Accept không phù hợp response server có thể trả | Kiểm tra Accept và response media type |
| Request body là form nhưng server mong JSON | Dùng MultiValueMap<String,String> và FormHttpMessageWriter | Dùng DTO JSON hoặc đổi contract sang form-urlencoded |
| Multipart thiếu boundary | Tự set Content-Type multipart/form-data thủ công | Dùng MultipartBodyBuilder và để writer tạo boundary |
| Mono không phát request | Chưa subscribe hoặc chưa được compose vào pipeline | Trả Publisher cho caller hoặc subscribe ở ranh giới phù hợp |
| Controller WebFlux bị treo | Gọi block() trên event-loop | Compose Mono/Flux thay vì block |
| 4xx/5xx trở thành exception | retrieve() mặc định phát WebClientResponseException | Dùng onStatus hoặc exchangeToMono nếu cần custom behavior |
| Body lỗi không đọc được ở nơi khác | Body đã được consume hoặc response đã release | Decode body trong cùng pipeline xử lý status |
| Connection/buffer bị rò | exchange callback không consume body và quản lý response sai | Dùng exchangeToMono/Flux đúng contract; để framework release body chưa đọc |
| Retry tạo dữ liệu trùng | POST đã thành công nhưng response bị mất | Dùng idempotency key và retry có chọn lọc |
| File lớn gây tăng heap | Gom file vào byte[] hoặc bodyValue toàn bộ dữ liệu | Dùng Resource hoặc Publisher streaming phù hợp |
| Không kiểm tra được JSON request trong test | Chỉ test response mà không ghi nhận request | Dùng MockWebServer và kiểm tra RecordedRequest |
| Không tương thích kiểu generic | Kiểu phần tử Publisher bị erasure hoặc khai báo sai | Dùng overload ParameterizedTypeReference khi cần |

## 13. Checklist trước khi dùng bodyValue

1. Body đã là một object cụ thể hay là Publisher?
2. Nếu là Mono/Flux, đã dùng body(...) chưa?
3. DTO có field và kiểu dữ liệu phù hợp API contract?
4. Content-Type có đúng với định dạng request?
5. Accept có đúng với định dạng response mong muốn?
6. Codec cần thiết như Jackson đã có?
7. Có thực sự cần gửi toàn bộ collection cùng lúc hay nên stream?
8. Nếu là form-urlencoded, MultiValueMap có đúng kiểu?
9. Nếu là multipart, MultipartBodyBuilder có được dùng để tạo boundary?
10. retrieve() có đủ hay cần exchangeToMono()?
11. 4xx/5xx được xử lý theo chính sách nào?
12. Retry có an toàn với method và side effect không?
13. Timeout được cấu hình ở application và transport?
14. Response body được consume/release đúng một lần?
15. Có test xác nhận request body thực tế bằng MockWebServer?

## 14. Bài tập thực hành

**Bài 1 — DTO đơn:** Tạo ProductRequest record và gửi bằng bodyValue. Kiểm tra JSON body trên MockWebServer.

**Bài 2 — Map:** Thay record bằng Map<String,Object>. So sánh JSON được serialize và kiểm tra field tùy chọn.

**Bài 3 — Content-Type:** Bỏ contentType(APPLICATION_JSON), quan sát request header và cách server xử lý. Sau đó đặt lại header rõ ràng.

**Bài 4 — Publisher:** Thay ProductRequest bằng Mono<ProductRequest>. Dùng body(mono, ProductRequest.class), xác nhận request vẫn được gửi.

**Bài 5 — Flux:** Gửi Flux<ProductRequest> với application/stream+json. So sánh với một JSON array gửi bằng bodyValue(List).

**Bài 6 — Form:** Gửi MultiValueMap<String,String> bằng bodyValue và kiểm tra application/x-www-form-urlencoded.

**Bài 7 — Multipart:** Dùng MultipartBodyBuilder gửi metadata JSON cùng file Resource. Kiểm tra boundary và từng part.

**Bài 8 — Error mapping:** Tạo response 400 và dùng onStatus để chuyển thành RemoteApiException có mã lỗi.

**Bài 9 — exchangeToMono:** Với 404 trả Mono.empty; với 2xx decode ProductResponse; với status khác propagate exception.

**Bài 10 — Retry:** Mô phỏng timeout hoặc 503. Thêm retryWhen có giới hạn và kiểm tra không retry lỗi validation.

**Bài 11 — Idempotency:** Thêm Idempotency-Key vào request POST và thiết kế server không tạo bản ghi trùng khi client retry.

**Bài 12 — Reactive pipeline:** Gọi WebClient từ một WebFlux controller, trả Mono trực tiếp và xác nhận không có block() trong đường xử lý.

## 15. Ghi nhớ

**bodyValue(Object)** là shortcut của WebClient để gửi một giá trị cụ thể, chẳng hạn DTO, record, Map hoặc collection. Spring dùng HTTP message codecs để serialize body theo Content-Type. Với JSON, truyền object gốc và đặt application/json khi cần contract rõ ràng.

Khi body là **Mono**, **Flux** hoặc reactive producer, dùng **body(...)**; bodyValue không dành cho Publisher và có thể ném IllegalArgumentException. Với form-urlencoded, MultiValueMap<String,String> có thể được ghi tự động; với multipart, dùng MultipartBodyBuilder và body(...).

Sau khi gửi request, chọn retrieve() cho response thông thường, onStatus() để tùy biến lỗi hoặc exchangeToMono/Flux() khi cần điều khiển theo status. Giữ pipeline reactive, xử lý body lifecycle đúng và chỉ retry khi thao tác an toàn/idempotent.

## 16. Tài liệu tham khảo

- Spring Framework Reference — WebClient Request Body: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html
- Spring Framework API — WebClient: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html
- Spring Framework API — BodyInserters: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html
- Spring Framework Reference — WebClient retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework Reference — WebClient exchangeToMono/exchangeToFlux: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework API — ClientCodecConfigurer: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/codec/ClientCodecConfigurer.html
- Spring Boot Reference — WebClient: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Reactor Reference Guide — Error Handling and Retry: https://projectreactor.io/docs/core/release/reference/
