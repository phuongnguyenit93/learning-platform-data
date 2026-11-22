# MockMvcWebTestClient để dùng cùng API kiểm thử cho MVC

Spring cung cấp `MockMvcWebTestClient` để kiểm thử ứng dụng Spring MVC bằng API fluent của `WebTestClient`. Cách này cho phép viết request và assertion theo phong cách client thống nhất, trong khi phần xử lý phía server vẫn chạy qua MockMvc và Servlet MVC.

Điểm quan trọng là `MockMvcWebTestClient` đóng vai trò cầu nối: test gọi `WebTestClient`, nhưng request được thực thi bởi MockMvc. Vì vậy, ta có thể dùng những assertion quen thuộc như status, header, body và JSONPath; khi cần, ta còn có thể lấy kết quả để kiểm tra các chi tiết riêng của MVC như handler, model hoặc view bằng MockMvc matchers.

## 1. Vì sao cần MockMvcWebTestClient?

Spring có hai API kiểm thử HTTP thường gặp:

- **MockMvc** cung cấp API mô phỏng Servlet request/response. Nó phù hợp với Spring MVC và có các matcher sâu cho handler, model, view, session, flash attribute và nhiều chi tiết của Servlet request.
- **WebTestClient** cung cấp API kiểm thử theo phong cách HTTP client: dựng request, gọi `exchange()`, rồi kiểm tra status, header và body. API này được dùng phổ biến với Spring WebFlux, đồng thời có thể dùng với Spring MVC thông qua `MockMvcWebTestClient`.

Nếu một dự án có nhiều module hoặc nhiều ứng dụng sử dụng cả MVC và WebFlux, việc dùng cùng một kiểu API client giúp cách tổ chức test nhất quán hơn. Một helper kiểm tra response JSON có thể nhận `WebTestClient` và không cần biết request được gửi tới WebFlux server thật hay được chuyển qua MockMvc.

Với MVC, `MockMvcWebTestClient` vẫn dùng hạ tầng MockMvc. Nó không biến controller Servlet thành WebFlux controller và cũng không khởi động một HTTP server thật.

## 2. Kiến trúc của cầu nối

Luồng xử lý khi dùng `MockMvcWebTestClient`:

~~~text
Test code
   |
   v
WebTestClient fluent API
   |
   v
MockMvcWebTestClient bridge
   |
   v
MockMvc
   |
   v
DispatcherServlet / Spring MVC
   |
   v
Controller, filters, interceptors, converters
   |
   v
Mock HTTP response
   |
   v
WebTestClient response assertions
~~~

Các bước trong test thường là:

1. Tạo client bằng `MockMvcWebTestClient.bindToController(...)` hoặc `bindToApplicationContext(...)`.
2. Dựng request bằng `client.get()`, `client.post()`, `uri(...)`, `header(...)`, `bodyValue(...)` hoặc các API tương ứng.
3. Gọi `exchange()` để thực thi request qua MockMvc.
4. Kiểm tra response bằng `expectStatus()`, `expectHeader()`, `expectBody()`.
5. Nếu cần assertion riêng của MVC, gọi `returnResult()` để lấy exchange result rồi chuyển nó sang `MockMvcWebTestClient.resultActionsFor(...)`.

Hai tầng assertion có mục đích khác nhau: WebTestClient kiểm tra những gì client nhìn thấy qua HTTP response; MockMvc matchers kiểm tra thêm các chi tiết nội bộ của quá trình xử lý MVC.

## 3. Tạo client với bindToController

`bindToController(...)` phù hợp khi muốn kiểm thử một hoặc một vài controller độc lập, không cần dựng toàn bộ Spring application context.

Ví dụ controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Greeting greeting() {
        return new Greeting("Hello MVC");
    }
}

record Greeting(String message) {}
~~~

Tạo WebTestClient dùng MockMvc:

~~~java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = MockMvcWebTestClient
    .bindToController(new GreetingController())
    .build();
~~~

Gọi endpoint và kiểm tra response:

~~~java
import org.springframework.http.MediaType;

client.get()
    .uri("/greeting")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.message").isEqualTo("Hello MVC");
~~~

Ở đây, test không gọi `MockMvc.perform(...)`. Nó sử dụng API của WebTestClient từ đầu đến cuối. `MockMvcWebTestClient` chuyển request đó sang MockMvc để Spring MVC xử lý.

### Khi nào dùng bindToController?

Chọn cách này khi:

- Test tập trung vào mapping và response của một controller.
- Không cần toàn bộ bean hoặc cấu hình từ application context.
- Muốn tạo test độc lập, nhẹ và có cấu hình rõ ràng.
- Có thể cung cấp dependency của controller trực tiếp qua constructor hoặc mock.

Nếu controller cần service, repository hoặc component khác, hãy truyền dependency mock vào controller khi tạo instance, hoặc chuyển sang cách bind với application context nếu muốn Spring quản lý wiring.

## 4. Tạo client với bindToApplicationContext

Trong ứng dụng thực tế, controller thường phụ thuộc nhiều thành phần Spring MVC: dependency injection, controller advice, message converter, interceptor, formatter, validator và các cấu hình web khác. Khi muốn kiểm thử cùng cấu hình đó, dùng `bindToApplicationContext(...)`.

Ví dụ với Spring Boot:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    WebApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = MockMvcWebTestClient
            .bindToApplicationContext(applicationContext)
            .build();
    }

    @Test
    void returnsGreeting() {
        client.get()
            .uri("/greeting")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Hello MVC");
    }
}
~~~

`@WebMvcTest` tạo một test slice tập trung vào Spring MVC. Application context được inject vào test, sau đó được dùng để dựng client. Với controller có dependency service, dùng cơ chế mock bean phù hợp với phiên bản Spring Boot đang dùng để cung cấp dependency cho context.

Trong test cần toàn bộ cấu hình ứng dụng, có thể dùng `@SpringBootTest` cùng một web application context. Dù context được tạo rộng hay hẹp, điểm cốt lõi vẫn là client được bind vào context MVC thông qua `MockMvcWebTestClient`.

## 5. So sánh hai cách khởi tạo

| Tiêu chí | `bindToController(...)` | `bindToApplicationContext(...)` |
|---|---|---|
| Phạm vi | Một hoặc một vài controller được chỉ định. | Các thành phần MVC được đăng ký trong ApplicationContext. |
| Dependency injection | Có thể truyền dependency vào controller khi tạo instance. | Spring lấy controller và dependency từ context. |
| Controller advice | Cần cấu hình bổ sung nếu muốn áp dụng. | Dùng advice được đăng ký trong context. |
| Interceptor, converter, validator | Cấu hình theo builder nếu cần. | Dùng cấu hình MVC trong context. |
| Tốc độ và độ cô lập | Thường nhẹ và cô lập hơn. | Phản ánh cấu hình ứng dụng sát hơn nhưng context rộng hơn. |
| Mục đích | Kiểm thử controller tập trung. | Kiểm thử controller trong cấu hình MVC của ứng dụng. |

Không có một lựa chọn đúng cho mọi test. Hãy chọn phạm vi nhỏ nhất vẫn chứa những thành phần mà hành vi đang kiểm tra phụ thuộc vào.

## 6. Dùng WebTestClient để dựng request

Sau khi tạo client, API dựng request gần giống cách gọi HTTP client:

~~~java
client.get()
    .uri("/products?page=2")
    .header("X-Client-Id", "test-client")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk();
~~~

Các phương thức thường dùng:

| API | Mục đích |
|---|---|
| `get()`, `post()`, `put()`, `patch()`, `delete()` | Chọn HTTP method. |
| `uri(...)` | Đặt path và query string. |
| `header(name, value)` | Thêm request header. |
| `headers(consumer)` | Cấu hình nhiều header. |
| `cookie(name, value)` | Thêm cookie. |
| `accept(mediaType)` | Đặt Accept header. |
| `contentType(mediaType)` | Đặt Content-Type. |
| `bodyValue(value)` | Cung cấp object để encode thành request body. |
| `body(...)` | Cung cấp publisher hoặc body inserter. |
| `exchange()` | Gửi request qua binding đã cấu hình và nhận response spec. |

Ví dụ POST JSON:

~~~java
client.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateOrderRequest("BOOK-01", 2))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().exists("Location")
    .expectBody()
    .jsonPath("$.status").isEqualTo("CREATED");
~~~

Ví dụ query parameter:

~~~java
client.get()
    .uri(uriBuilder -> uriBuilder
        .path("/products")
        .queryParam("keyword", "spring")
        .queryParam("page", 2)
        .build())
    .exchange()
    .expectStatus().isOk();
~~~

Điểm thuận tiện là test mô tả request ở góc nhìn client. Nó cũng giúp tái sử dụng helper dựng request hoặc assertion giữa các test dùng WebTestClient.

## 7. Kiểm tra status và header

WebTestClient có nhóm expectation riêng cho status:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk();
~~~

Các trường hợp thường gặp:

~~~java
.expectStatus().isOk()
.expectStatus().isCreated()
.expectStatus().isAccepted()
.expectStatus().isNoContent()
.expectStatus().isBadRequest()
.expectStatus().isNotFound()
.expectStatus().is5xxServerError()
~~~

Có thể kiểm tra header:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectHeader().exists("ETag")
    .expectHeader().valueEquals("X-Api-Version", "v1");
~~~

Các assertion này xác nhận hợp đồng HTTP bên ngoài: status code và header mà client nhận được. Khi endpoint trả response không có body, có thể kiểm tra status và header mà không cần gọi `expectBody`.

## 8. Kiểm tra JSON body

WebTestClient hỗ trợ kiểm tra JSON trực tiếp:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("""
        {
          "orderId": 101,
          "status": "CONFIRMED"
        }
        """);
~~~

Nếu chỉ cần kiểm tra một số trường, dùng JSONPath:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.orderId").isEqualTo(101)
    .jsonPath("$.status").isEqualTo("CONFIRMED")
    .jsonPath("$.customer.name").isEqualTo("Nguyễn An")
    .jsonPath("$.items[1].sku").isEqualTo("PEN-02");
~~~

JSONPath của WebTestClient có phong cách tương tự matcher JSONPath trong MockMvc, giúp chuyển đổi test từ một API sang API kia dễ hơn. Tuy nhiên, đây là expectation của WebTestClient, không phải `MockMvcResultMatchers.jsonPath(...)`.

Khi cần giải mã body thành một kiểu Java:

~~~java
client.get()
    .uri("/orders/101")
    .exchange()
    .expectStatus().isOk()
    .expectBody(OrderResponse.class)
    .value(order -> {
        assertThat(order.status()).isEqualTo("CONFIRMED");
        assertThat(order.items()).hasSize(2);
    });
~~~

Ví dụ dùng AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
~~~

Việc kiểm tra qua object đã deserialize phù hợp khi test quan tâm đến kiểu dữ liệu và nhiều thuộc tính của response. JSONPath phù hợp khi muốn giữ assertion sát với cấu trúc JSON thực tế.

## 9. Kết hợp assertion client-side với MockMvc server-side

Một lợi ích quan trọng của `MockMvcWebTestClient` là có thể lấy kết quả của WebTestClient rồi chuyển sang MockMvc để kiểm tra chi tiết nội bộ của Spring MVC.

Ví dụ:

~~~java
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.result.MockMvcResultMatchers;

EntityExchangeResult<byte[]> result = client.get()
    .uri("/greeting")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

ResultActions mvcResult = MockMvcWebTestClient.resultActionsFor(result);

mvcResult
    .andExpect(MockMvcResultMatchers.handler().methodName("greeting"));
~~~

Ở đây:

1. WebTestClient gửi request và kiểm tra status.
2. `returnResult()` trả về exchange result chứa kết quả response và thông tin được bridge giữ lại từ MockMvc.
3. `resultActionsFor(result)` lấy lại `ResultActions` tương ứng của MockMvc.
4. Test tiếp tục dùng MockMvc matchers để kiểm tra handler hoặc chi tiết MVC khác.

Đây là điểm phân biệt quan trọng giữa `MockMvcWebTestClient` và một WebTestClient kết nối đến server thật: kết quả từ bridge có thể được chuyển lại thành MockMvc ResultActions.

## 10. Những MVC matcher có thể dùng sau resultActionsFor

Khi đã có `ResultActions`, ta có thể dùng các matcher quen thuộc của MockMvc. Ví dụ:

~~~java
MockMvcWebTestClient.resultActionsFor(result)
    .andExpect(handler().methodName("greeting"));
~~~

Một số nhóm matcher hữu ích:

| Matcher | Thông tin được xác nhận |
|---|---|
| `handler()` | Handler được chọn, controller type và method xử lý request. |
| `model()` | Model attribute và binding result. |
| `view()` | Tên view hoặc trạng thái view. |
| `flash()` | Flash attribute. |
| `request()` | Thuộc tính request, session hoặc async state. |
| `forwardedUrl(...)` | URL được forward đến. |
| `redirectedUrl(...)` | URL redirect. |
| `resolvedException()` | Exception được xử lý trong MVC result. |

Ví dụ với một controller dùng Model:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class GreetingPageController {

    @GetMapping("/greeting-page")
    String greeting(Model model) {
        model.addAttribute("message", "Hello MVC");
        return "greeting";
    }
}
~~~

Sau khi gửi request qua client và lấy exchange result, có thể kiểm tra model và view:

~~~java
EntityExchangeResult<byte[]> result = client.get()
    .uri("/greeting-page")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

MockMvcWebTestClient.resultActionsFor(result)
    .andExpect(model().attribute("message", "Hello MVC"))
    .andExpect(view().name("greeting"));
~~~

Ví dụ này cho thấy hai lớp assertion có thể bổ sung cho nhau: WebTestClient kiểm tra kết quả HTTP, còn MockMvc xác nhận Spring MVC đã chuẩn bị model và chọn view mong muốn. Trong ứng dụng thật, view resolver và template engine cần được cấu hình phù hợp với test context.

## 11. Chọn đúng kiểu result để giữ body

WebTestClient cung cấp một số cách lấy response body:

| Cách dùng | Kiểu kết quả | Phù hợp khi |
|---|---|---|
| `expectBody()` | BodyContentSpec; `returnResult()` thường trả `EntityExchangeResult<byte[]>`. | Muốn kiểm tra raw JSON hoặc lấy exchange result để dùng với `resultActionsFor`. |
| `expectBody(MyType.class)` | BodySpec<MyType, ?>; `returnResult()` trả result đã deserialize. | Muốn assertion trên object Java. |
| `expectBodyList(MyType.class)` | ListBodySpec<MyType>; result chứa danh sách object. | Endpoint trả về JSON array. |
| `expectBody(Void.class)` | BodySpec<Void, ?>. | Endpoint không có response body. |

Nếu cần chuyển sang MockMvc matchers, giữ lại result được trả về từ `returnResult()`. Đừng chỉ gọi `expectBody().jsonPath(...)` rồi bỏ kết quả nếu sau đó còn cần kiểm tra handler, model hoặc view.

## 12. Tái sử dụng helper kiểm thử

Vì `WebTestClient` có API thống nhất, có thể viết helper nhận client để dùng chung các assertion HTTP:

~~~java
static void assertGreetingResponse(WebTestClient client) {
    client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello MVC");
}
~~~

Helper này chỉ phụ thuộc API WebTestClient. Nó có thể được gọi với client được tạo bằng `MockMvcWebTestClient` cho MVC hoặc client được bind theo cách phù hợp với một ứng dụng WebFlux.

Tuy nhiên, không phải mọi test đều nên được dùng chung. Nếu một assertion kiểm tra chi tiết riêng của Servlet MVC, chẳng hạn model, view hoặc handler method, nó cần MockMvc bridge. Nếu assertion phụ thuộc WebFlux-specific exchange result hoặc reactive behavior, nó thuộc test của WebFlux. Hãy giữ phần chung ở hợp đồng HTTP mà cả hai ứng dụng cùng cung cấp.

## 13. MockMvcWebTestClient khác gì kiểm thử server thật?

| Tiêu chí | MockMvcWebTestClient | WebTestClient kết nối server thật |
|---|---|---|
| Backend xử lý | MockMvc và Spring MVC trong test process. | HTTP server đang chạy, ví dụ embedded Tomcat/Jetty/Undertow hoặc server WebFlux. |
| Mạng và socket thật | Không. | Có. |
| Servlet container thực tế | Không khởi động container thật. | Có nếu ứng dụng MVC chạy trên embedded Servlet container. |
| Kiểm tra HTTP status/header/body | Có. | Có. |
| Kiểm tra handler/model/view MVC | Có thể chuyển result sang MockMvc matchers. | Không có MockMvc ResultActions để kiểm tra trực tiếp. |
| Tốc độ và cô lập | Thường nhanh và dễ cô lập hơn. | Tốn tài nguyên và có nhiều thành phần runtime hơn. |
| Phù hợp | Controller, mapping, MVC configuration và HTTP contract ở mức mock server. | Tích hợp toàn bộ ứng dụng, connector, filter/container behavior và giao tiếp HTTP thực tế. |

Nếu mục tiêu là kiểm tra controller và hợp đồng HTTP mà không cần mở server, `MockMvcWebTestClient` phù hợp. Nếu cần xác nhận embedded server, port, connector, TLS, network behavior hoặc cấu hình container, hãy chạy ứng dụng với web environment thật và dùng WebTestClient kết nối tới server.

Đừng xem việc dùng cùng WebTestClient API là bằng chứng rằng test đã đi qua mạng hoặc Servlet container. Backend thực thi quyết định phạm vi kiểm thử.

## 14. Dependency và phiên bản

`MockMvcWebTestClient` được cung cấp trong Spring Test và xuất hiện từ Spring Framework 5.3. Khi sử dụng, dự án cần có các lớp kiểm thử Spring MVC/MockMvc và API WebTestClient trên test classpath.

Trong dự án Spring Boot, nên để Spring Boot dependency management quản lý phiên bản các module Spring đồng bộ. Nếu classpath chưa có WebTestClient, thêm dependency Spring WebFlux ở phạm vi test theo dependency management của dự án, thay vì thêm cả reactive starter vào runtime chỉ để lấy API test.

Ví dụ Gradle khi dự án đã dùng Spring Boot dependency management:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-webflux")
}
~~~

Trong nhiều dự án, `spring-test` đã có sẵn qua `spring-boot-starter-test`; khi đó chỉ cần bổ sung module còn thiếu. Kiểm tra dependency graph thực tế trước khi thêm để tránh khai báo trùng hoặc kéo thêm một phiên bản Spring khác với BOM.

Các package chính:

| Thành phần | Package |
|---|---|
| `WebTestClient` | `org.springframework.test.web.reactive.server` |
| `MockMvcWebTestClient` | `org.springframework.test.web.servlet.client` |
| `MockMvc` | `org.springframework.test.web.servlet` |
| MockMvc result matchers | `org.springframework.test.web.servlet.result` |

## 15. Lỗi thường gặp

### Nhầm MockMvcWebTestClient với WebFlux server

`MockMvcWebTestClient` dùng WebTestClient làm API phía client, nhưng request được xử lý bởi MockMvc và Spring MVC. Controller vẫn là Servlet MVC controller.

### Nghĩ rằng exchange() mở kết nối HTTP thật

Khi client được tạo bằng `MockMvcWebTestClient`, `exchange()` gọi bridge trong cùng test process. Không có port hoặc socket thật được mở.

### Dùng bindToController khi cần application configuration

Nếu test phụ thuộc vào controller advice, interceptor, validator hoặc message converter được khai báo trong application context, dùng `bindToApplicationContext` để những cấu hình đó tham gia.

### Quên gọi returnResult trước resultActionsFor

`resultActionsFor` cần exchange result được trả về từ WebTestClient. Hãy lưu kết quả bằng `returnResult()`, sau đó mới chuyển nó sang MockMvc ResultActions.

### Chỉ dùng WebTestClient matcher cho mọi assertion

WebTestClient kiểm tra HTTP response. Nếu cần kiểm tra handler, model, view, flash attribute hoặc resolved exception ở tầng MVC, dùng `MockMvcWebTestClient.resultActionsFor(...)` và MockMvc matchers.

### Dùng resultActionsFor với client không đi qua MockMvc

`resultActionsFor` là cầu nối dành cho exchange result được tạo từ `MockMvcWebTestClient`. Không dùng nó với một WebTestClient kết nối đến server thật hoặc một binding không giữ MockMvc result.

### Thêm WebFlux runtime starter chỉ để lấy WebTestClient

Ứng dụng MVC không cần bật WebFlux runtime chỉ để viết test bằng WebTestClient. Nếu thiếu API cần thiết, hãy bổ sung dependency phù hợp ở test scope và giữ các module Spring đồng bộ phiên bản.

## 16. Quy trình chọn API cho test MVC

Khi viết test cho controller MVC:

1. Chọn `bindToController` nếu cần test cô lập một controller; chọn `bindToApplicationContext` nếu cần cấu hình MVC của ứng dụng.
2. Dùng WebTestClient để dựng request theo hợp đồng HTTP: method, URI, header, cookie, content type và body.
3. Gọi `exchange()` rồi xác nhận status, header và body bằng các expectation của WebTestClient.
4. Nếu response là JSON, dùng `expectBody().json(...)`, JSONPath hoặc deserialize sang kiểu Java.
5. Nếu cần kiểm tra handler, model, view, flash hoặc chi tiết Servlet MVC, gọi `returnResult()` rồi dùng `MockMvcWebTestClient.resultActionsFor(...)`.
6. Nếu cần kiểm tra network hoặc embedded Servlet container thật, dùng test server thật thay vì MockMvc bridge.

`MockMvcWebTestClient` giúp Spring MVC dùng được phong cách kiểm thử client của WebTestClient, đồng thời vẫn giữ khả năng kiểm tra sâu bằng MockMvc khi cần. Hiểu rõ binding đang dùng và biết lúc nào chuyển từ client assertions sang MVC assertions giúp test nhất quán mà vẫn kiểm tra đúng tầng hành vi của ứng dụng.
