# Base URL, default headers và cấu hình codec

## 1. Vai trò của cấu hình WebTestClient

`WebTestClient` là API kiểm thử HTTP của Spring, có giao diện fluent tương tự `WebClient`. Nó có thể gửi request đến một server đang chạy hoặc gửi request qua hạ tầng mock của Spring MVC/WebFlux. Trước khi gọi `build()`, ta có thể cấu hình các giá trị dùng chung cho mọi request:

- **Base URL**: địa chỉ gốc để phân giải các URI tương đối.
- **Default headers**: các header mặc định như `Accept`, mã client hoặc thông tin xác thực dành cho môi trường test.
- **Codecs**: bộ đọc và ghi HTTP body, ví dụ JSON encoder/decoder, giới hạn kích thước dữ liệu được buffer và codec tùy chỉnh.

Đưa các giá trị lặp lại vào builder giúp các test ngắn hơn và nhất quán hơn. Mỗi test vẫn có thể ghi đè header hoặc gửi URI riêng khi có yêu cầu đặc biệt.

## 2. Cấu hình Base URL

Base URL được dùng khi request cung cấp URI tương đối. Ví dụ, với base URL `https://api.example.test`, lời gọi `.uri("/v1/orders")` được gửi đến `https://api.example.test/v1/orders`.

Với kiểm thử gọi server đang chạy, có thể cấu hình địa chỉ ngay trên builder của `bindToServer()`:

```java
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
```

`bindToServer()` sử dụng kết nối HTTP thực, vì vậy địa chỉ và port phải trỏ đến server có thể truy cập tại thời điểm test chạy. Trong kiểm thử tích hợp với port ngẫu nhiên, hãy lấy port được Spring Boot cấp thay vì cố định `8080`.

Khi bind trực tiếp vào controller hoặc application context, trước hết cấu hình phần mock server, sau đó gọi `configureClient()` để lấy builder dành cho phía client:

```java
WebTestClient client = WebTestClient.bindToController(new CatalogController())
        .configureClient()
        .baseUrl("http://localhost")
        .build();

client.get()
        .uri("/catalog")
        .exchange()
        .expectStatus().isOk();
```

Trong trường hợp này request được xử lý bởi mock infrastructure, không mở kết nối đến một server tại `localhost`. Base URL giúp URI tương đối được phân giải theo cùng một quy tắc như khi dùng client với server thật. Nếu ứng dụng cần đầy đủ cấu hình MVC/WebFlux, filter hoặc controller advice, có thể bind vào application context thay vì chỉ bind một controller:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("http://localhost")
        .build();
```

`applicationContext` ở ví dụ là Spring application context đã được inject hoặc tạo trong test.

### URI tương đối và URI tuyệt đối

Khi dùng base URL, cần phân biệt các dạng URI:

```java
// Dùng base URL để tạo URI đích.
client.get().uri("/v1/orders");

// Dùng URI template cùng biến đường dẫn.
client.get().uri("/v1/orders/{id}", 42);

// URI tuyệt đối đã chứa scheme và host của chính nó.
client.get().uri("https://other.example.test/status");
```

URI tuyệt đối đã xác định địa chỉ đích riêng, nên không dựa vào base URL của builder. URI tương đối giúp test không phải lặp lại host và port trong từng lời gọi.

Nếu có các giá trị URI template dùng chung, builder còn hỗ trợ `defaultUriVariables(...)`. Các biến mặc định được dùng khi phân giải URI template không truyền đủ biến tương ứng. Với đường dẫn chứa id cụ thể, truyền biến trực tiếp vào `.uri(...)` thường dễ đọc hơn.

## 3. Thiết lập default headers

Header mô tả metadata của request và response. Trong test API, header thường được lặp lại gồm:

| Header | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| `Accept` | Các định dạng response client có thể nhận | `application/json` |
| `Content-Type` | Định dạng body của request đang gửi | `application/json` cho body JSON |
| `Authorization` | Thông tin xác thực | Bearer token hoặc Basic authentication dành riêng cho test |
| `X-Client-Name` | Header tùy biến do ứng dụng quy ước | Nhận diện client test hoặc nguồn gọi |
| `X-Correlation-Id` | Mã tương quan request | Theo dõi một request qua log và các thành phần xử lý |

`defaultHeader(name, values...)` khai báo giá trị mặc định cho một header. Giá trị mặc định được áp dụng nếu request cụ thể chưa có header cùng tên. Có thể gọi phương thức này nhiều lần để khai báo nhiều header:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .defaultHeader("X-Client-Name", "catalog-test")
        .build();
```

Mọi request dùng client này đều có `Accept: application/json` và `X-Client-Name: catalog-test`, trừ khi request đã chỉ định header tương ứng.

Khi cần thiết lập nhiều header trong một thao tác, dùng `defaultHeaders(...)` để truy cập đối tượng `HttpHeaders` mặc định:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .defaultHeaders(headers -> {
            headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));
            headers.set("X-Client-Name", "catalog-test");
            headers.setBasicAuth("test-user", "test-password");
        })
        .build();
```

Thông tin đăng nhập trong ví dụ chỉ là dữ liệu giả dành cho môi trường kiểm thử. Không đặt credential thật vào mã nguồn hoặc cấu hình được commit. Nếu ứng dụng sử dụng Bearer token, hãy lấy token từ fixture hoặc cơ chế cấp token dành cho test.

### Ghi đè header ở từng request

Default header tạo giá trị chung, còn request có thể thay đổi giá trị cho riêng lần gọi đó. Ví dụ, client mặc định nhận JSON nhưng một test cụ thể muốn nhận XML:

```java
client.get()
        .uri("/catalog/export")
        .headers(headers -> headers.setAccept(
                java.util.List.of(MediaType.APPLICATION_XML)))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_XML);
```

`headers(...)` cho phép sửa `HttpHeaders` của request hiện tại. Dùng `set(...)` khi muốn thay giá trị hiện có của một header; dùng `add(...)` khi chủ đích là bổ sung thêm một giá trị. Điều này quan trọng với header có thể chứa nhiều giá trị, chẳng hạn `Accept`.

Không nên đặt `Content-Type: application/json` làm default một cách máy móc cho mọi request. `Content-Type` mô tả body đang gửi; request GET không có body thường không cần header này. Hãy đặt content type tại request có body:

```java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("book-42", 2))
        .exchange()
        .expectStatus().isCreated();
```

Ngược lại, `Accept` mô tả định dạng response mong muốn và thường phù hợp để cấu hình mặc định cho client test.

## 4. Cấu hình codec mặc định

Codec chịu trách nhiệm chuyển đổi giữa HTTP body và kiểu dữ liệu Java. Khi gửi request, encoder ghi object thành byte hoặc nội dung theo media type. Khi đọc response, decoder phân tích body thành object mà test yêu cầu.

`WebTestClient.Builder.codecs(...)` cho phép tùy chỉnh `CodecConfigurer` của client. Một cấu hình thường gặp là tăng giới hạn buffer cho test phải đọc response JSON lớn:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(4 * 1024 * 1024))
        .build();
```

Giá trị `4 * 1024 * 1024` tương đương 4 MiB. Một số codec cần gom dữ liệu vào bộ nhớ trước khi giải mã hoặc trả kết quả. Nếu body vượt quá giới hạn, thao tác có thể thất bại với `DataBufferLimitException`. Tăng giới hạn chỉ phù hợp khi test thực sự cần xử lý payload lớn và môi trường có đủ bộ nhớ.

Giới hạn này không làm server tự động chấp nhận request lớn hơn. Nó cấu hình codec ở phía `WebTestClient`. Nếu ứng dụng có giới hạn riêng ở server, gateway hoặc tầng lưu trữ, các giới hạn đó vẫn có hiệu lực độc lập.

### Dùng ObjectMapper riêng cho JSON

Khi ứng dụng có quy tắc JSON riêng, ví dụ cách xử lý Java time, naming strategy hoặc custom module, test client có thể dùng cùng cấu hình Jackson để serialize request và deserialize response:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .codecs(configurer -> {
            configurer.defaultCodecs().jackson2JsonEncoder(
                    new Jackson2JsonEncoder(objectMapper));
            configurer.defaultCodecs().jackson2JsonDecoder(
                    new Jackson2JsonDecoder(objectMapper));
            configurer.defaultCodecs().maxInMemorySize(4 * 1024 * 1024);
        })
        .build();
```

Trong ứng dụng Spring Boot, nên cân nhắc dùng `ObjectMapper` đã được cấu hình trong application context để test phản ánh đúng cấu hình JSON của ứng dụng. Ví dụ trên tạo mapper độc lập để minh họa API; mapper thực tế có thể cần các module và feature giống với server.

Encoder và decoder đảm nhiệm hai chiều khác nhau:

- `Jackson2JsonEncoder` chuyển object Java thành JSON khi gửi request hoặc ghi body.
- `Jackson2JsonDecoder` đọc JSON và tạo object Java khi nhận response.

Nếu chỉ thay encoder mà không thay decoder, request và response có thể dùng hai cấu hình JSON khác nhau. Khi kiểm thử hợp đồng API, nên xác định rõ chiều nào cần cấu hình và giữ hai chiều đồng bộ khi thích hợp.

## 5. Đăng ký codec tùy chỉnh

Khi body dùng định dạng riêng hoặc kiểu dữ liệu chưa được codec mặc định hỗ trợ, có thể đăng ký encoder/decoder bổ sung thông qua `customCodecs()`:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .codecs(configurer -> {
            configurer.customCodecs().register(new MeasurementEncoder());
            configurer.customCodecs().register(new MeasurementDecoder());
        })
        .build();
```

`MeasurementEncoder` và `MeasurementDecoder` là các lớp do ứng dụng định nghĩa, triển khai hợp đồng encoder/decoder của Spring và công bố media type mà chúng hỗ trợ. Ví dụ chỉ ra vị trí đăng ký; nó không giả định một codec cụ thể có sẵn trong Spring.

Codec tùy chỉnh cần khai báo đúng kiểu Java, media type và cách đọc/ghi buffer. Cũng cần kiểm soát việc cấp phát và giải phóng `DataBuffer`, đặc biệt khi làm việc với body dạng streaming. Đăng ký codec không làm cho server tự động hiểu định dạng đó; server và client test phải có cấu hình tương thích.

## 6. Khi nào dùng ExchangeStrategies?

`ExchangeStrategies` đóng gói tập hợp reader/writer (codec) và các chiến lược trao đổi dữ liệu mà WebClient/WebTestClient sử dụng. Có thể xây dựng strategy riêng rồi gắn vào builder:

```java
import org.springframework.web.reactive.function.client.ExchangeStrategies;

ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(4 * 1024 * 1024))
        .build();

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .exchangeStrategies(strategies)
        .build();
```

Chọn `codecs(...)` khi chỉ cần chỉnh một vài codec trên cấu hình mặc định của builder. Chọn `exchangeStrategies(...)` khi muốn tái sử dụng một bộ strategy đã được tạo và quản lý riêng, hoặc cần kiểm soát tập codec ở mức tổng thể.

Hai cách này đều cấu hình codec cho client. Tránh xây dựng một strategy rồi đồng thời cấu hình lại codec ở nhiều nơi mà không xác định rõ strategy cuối cùng được sử dụng; cách làm đó khiến test khó hiểu và khó bảo trì.

## 7. Kết hợp cấu hình trong một WebTestClient

Một factory nhỏ có thể gom base URL, header và codec dùng chung cho một nhóm test:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class ApiTestClientFactory {

    static WebTestClient create(String baseUrl) {
        return WebTestClient.bindToServer()
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader("X-Client-Name", "integration-test")
                .codecs(configurer -> configurer.defaultCodecs()
                        .maxInMemorySize(4 * 1024 * 1024))
                .build();
    }
}
```

Test có thể truyền địa chỉ server tương ứng với môi trường chạy:

```java
WebTestClient client = ApiTestClientFactory.create("http://localhost:8080");

client.get()
        .uri("/api/products/{id}", 42)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
```

Factory chỉ nên chứa cấu hình thật sự dùng chung. Những header mang dữ liệu riêng của từng test, token có vòng đời ngắn hoặc media type đặc thù nên được đặt tại request để test thể hiện rõ điều kiện đầu vào.

## 8. Tích hợp với Spring Boot test context

Khi kiểm thử ứng dụng Spring Boot bằng server thật trên port ngẫu nhiên, có thể để Spring Boot cung cấp `WebTestClient`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductApiIntegrationTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void readsProductAsJson() {
        webTestClient.get()
                .uri("/api/products/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
    }
}
```

Ở chế độ này, `WebTestClient` được cấu hình để gửi request đến ứng dụng đang chạy trên port ngẫu nhiên. Nếu cần các default header hoặc codec riêng cho một nhóm test, có thể tự tạo client với builder phù hợp và địa chỉ server đang chạy, hoặc tổ chức một factory test dùng chung. Không nên thay base URL bằng một giá trị cố định làm mất port ngẫu nhiên mà Spring Boot đã cấp.

Nếu chỉ cần test controller mà không cần khởi động server, có thể dùng `@WebFluxTest` hoặc bind vào controller/application context. Cách bind quyết định hạ tầng nào được đưa vào test; cấu hình client như base URL, header và codec là lớp cấu hình riêng ở phía client.

## 9. Những nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Request gọi sai host hoặc port | Base URL chưa được cấu hình, hoặc test dùng port cố định trong khi server chạy port ngẫu nhiên. | Dùng base URL chứa địa chỉ runtime thực tế; với Spring Boot random port, để cấu hình test tự quản lý port hoặc lấy port được cấp. |
| Đường dẫn bị lặp prefix | Test thêm prefix đã nằm trong base URL vào URI lần nữa. | Quy ước rõ base URL chứa host hay cả path prefix; chỉ thêm phần path còn lại trong `.uri(...)`. |
| Header mặc định không xuất hiện | Request đã có header cùng tên nên giá trị mặc định không được áp dụng. | Kiểm tra header ở cấp request; dùng `headers(...)` để đặt rõ giá trị mong muốn. |
| Server trả `406 Not Acceptable` | `Accept` yêu cầu media type mà endpoint không thể tạo. | Kiểm tra default `Accept`, `produces` và message converter của server. |
| Server trả `415 Unsupported Media Type` | `Content-Type` của request không được endpoint hỗ trợ hoặc body được gửi sai định dạng. | Đặt content type phù hợp trên request có body và kiểm tra codec encoder. |
| Đọc response lớn gặp `DataBufferLimitException` | Codec cần buffer body vượt giới hạn đang cấu hình. | Xem xét tăng `maxInMemorySize` hợp lý hoặc xử lý dữ liệu theo streaming thay vì gom toàn bộ body. |
| JSON deserialize khác với ứng dụng | Client test và server dùng cấu hình Jackson khác nhau. | Dùng `ObjectMapper` hoặc codec configuration tương thích với ứng dụng. |
| Codec tùy chỉnh không được dùng | Codec chưa được đăng ký đúng hoặc media type/kiểu Java không khớp. | Kiểm tra decoder/encoder hỗ trợ kiểu và media type của request/response. |
| Test mock gọi nhầm server ngoài | Nhầm lẫn giữa `bindToController`/`bindToApplicationContext` và `bindToServer`. | Chọn kiểu bind đúng với mục tiêu: mock infrastructure hoặc HTTP server thực. |

## 10. Nguyên tắc tổ chức cấu hình

- Dùng base URL để gom host và port; giữ URI của từng request ở dạng tương đối khi có thể.
- Chỉ đặt default header thực sự dùng chung. Header theo user, token, correlation id hoặc media type riêng nên được cấu hình theo request nếu chúng thay đổi giữa các test.
- Phân biệt `Accept` (định dạng response mong muốn) và `Content-Type` (định dạng request body).
- Dùng `codecs(...)` cho điều chỉnh codec thông thường như buffer size hoặc Jackson mapper; dùng `exchangeStrategies(...)` khi cần đóng gói và tái sử dụng toàn bộ chiến lược codec.
- Giữ giới hạn buffer hữu hạn và phù hợp với payload dự kiến. Tăng giới hạn không thay thế cho kiểm soát kích thước request/response ở các tầng khác.
- Đảm bảo codec client tương thích với media type và định dạng mà server thực sự cung cấp.
- Tách cấu hình dùng chung vào factory hoặc test configuration khi có nhiều test cùng dùng; tránh tạo abstraction cho một test đơn giản.
- Chọn mock binding để kiểm thử MVC/WebFlux ở mức framework và server binding để kiểm thử HTTP qua mạng; base URL phải tương ứng với cách bind đã chọn.

## 11. Kết luận

`baseUrl(...)` giúp phân giải URI tương đối và loại bỏ việc lặp host/port trong từng request. `defaultHeader(...)` và `defaultHeaders(...)` thiết lập metadata mặc định, trong khi request vẫn có thể ghi đè giá trị cần thiết. `codecs(...)` tùy chỉnh encoder/decoder và các giới hạn buffer; `exchangeStrategies(...)` cho phép cung cấp một bộ chiến lược codec hoàn chỉnh. Khi kết hợp ba nhóm cấu hình này, hãy giữ rõ ranh giới giữa cấu hình client, cấu hình request riêng và cấu hình server để test phản ánh đúng hợp đồng HTTP của ứng dụng.
