# Bind tới máy chủ thật để kiểm tra từ đầu đến cuối

## 1. Mục tiêu của RestTestClient khi bind tới server

Một bài kiểm thử controller có thể gọi trực tiếp handler hoặc dùng mock web infrastructure. Cách đó hữu ích để kiểm tra mapping, validation, serialization và logic HTTP trong Spring. Nhưng nó chưa đi qua một HTTP connector đang lắng nghe trên cổng mạng.

Khi cần xác nhận ứng dụng hoạt động qua HTTP thực, có thể dùng **RestTestClient.bindToServer()** để tạo client gửi request tới một server đang chạy. Server có thể là embedded server do Spring Boot khởi động trong test, một ứng dụng chạy độc lập hoặc một môi trường kiểm thử đã triển khai.

Luồng kiểm thử khi bind tới server thật:

~~~text
JUnit test
   |
   | RestTestClient.bindToServer()
   v
HTTP client
   |
   | TCP + HTTP request
   v
Embedded servlet/reactive server
   |
   v
Filters / Security / Dispatcher / Controller
   |
   v
Service / Repository / Database
   |
   | HTTP response
   v
RestTestClient assertions
~~~

Test đi qua connector và HTTP stack của server. Do đó, nó có thể xác nhận nhiều thành phần cùng hoạt động: server khởi động, port, routing, filter, security, message converter, serialization, service và persistence.

**RestTestClient** cung cấp API fluent để gửi request và kiểm tra response. Với cách bind server, request được gửi qua HTTP thật thay vì được dispatch trực tiếp trong mock application context.

## 2. Phiên bản Spring có RestTestClient

**RestTestClient** được giới thiệu trong Spring Framework 7.0. Nó thuộc dòng Spring mới hơn các dự án còn dùng Spring Framework 6.x. Nếu project chưa có class này, kiểm tra phiên bản dependency trước khi viết test; thêm import vào source sẽ không làm API xuất hiện nếu dependency chưa hỗ trợ.

Với các dự án Spring Boot dùng dòng Spring Framework 7.0, có thể dùng RestTestClient. Với ứng dụng ở phiên bản cũ hơn, các lựa chọn thường gặp là:

- **TestRestTemplate** cho integration test Spring Boot theo HTTP thật, đặc biệt với ứng dụng Spring MVC.
- **WebTestClient.bindToServer()** cho endpoint WebFlux hoặc khi cần API test client tương ứng.
- **RestClient** kết hợp assertion riêng nếu muốn tự xây dựng kiểm thử HTTP.

Không nên nhầm **RestTestClient** với **MockRestServiceServer**. MockRestServiceServer thường được dùng để kiểm tra một REST client do ứng dụng tạo ra bằng cách giả lập server mà client gọi tới. Trong bài này, RestTestClient đóng vai trò HTTP client gọi vào server của chính ứng dụng đang được kiểm thử.

## 3. Khởi động server thật trong Spring Boot

Đối với end-to-end test, nên để Spring Boot khởi động embedded server trên một cổng ngẫu nhiên:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OrderApiHttpTest {
}
~~~

**RANDOM_PORT** yêu cầu Spring Boot khởi chạy web server thật và chọn một port còn trống. Cách này tránh phụ thuộc vào port cố định và cho phép nhiều test suite chạy trên cùng máy mà ít xung đột hơn.

Có thể lấy port được cấp bằng **@LocalServerPort**:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
private int port;
~~~

Không dùng **webEnvironment = MOCK** nếu mục tiêu là kiểm tra HTTP connector. Chế độ MOCK dựng web application context cho test nhưng không khởi chạy server nhận kết nối TCP. **DEFINED_PORT** cũng có thể khởi chạy server thật, nhưng yêu cầu port được cấu hình sẵn và dễ xung đột nếu port đó đang được tiến trình khác sử dụng.

### Tạo RestTestClient bằng bindToServer()

Sau khi server khởi động, tạo client trỏ tới địa chỉ và port của server:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.RestTestClient;

RestTestClient client = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:" + port)
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
        )
        .build();
~~~

**bindToServer()** cấu hình client dùng kết nối HTTP tới server đang chạy. **baseUrl(...)** đặt địa chỉ gốc; request sau đó có thể dùng URI tương đối như **/api/orders/42**. **defaultHeader(...)** đặt header mặc định cho các request của client.

Có thể đặt cấu hình chung như base URL, default header, converter hoặc timeout trước khi gọi **build()**. Sau đó tái sử dụng client cho nhiều request trong cùng test class nếu các cấu hình đó không thay đổi.

## 4. Một bài kiểm thử end-to-end hoàn chỉnh

Giả sử ứng dụng có endpoint đọc đơn hàng:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable Long id) {
        return orderService.findById(id);
    }
}
~~~

DTO trả về:

~~~java
public record OrderResponse(
        Long id,
        String orderNumber,
        String status
) {
}
~~~

Test dùng repository để tạo dữ liệu, sau đó gửi request qua HTTP thật:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.RestTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OrderApiHttpTest {

    @LocalServerPort
    private int port;

    @Autowired
    private OrderRepository orderRepository;

    private RestTestClient client;
    private Long orderId;

    @BeforeEach
    void setUp() {
        client = RestTestClient
                .bindToServer()
                .baseUrl("http://localhost:" + port)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE
                )
                .build();

        Order saved = orderRepository.save(
                new Order("E2E-" + java.util.UUID.randomUUID(), "PAID")
        );
        orderId = saved.getId();
    }

    @AfterEach
    void cleanUp() {
        if (orderId != null) {
            orderRepository.deleteById(orderId);
        }
    }

    @Test
    void shouldReadAnOrderThroughRealHttp() {
        client.get()
                .uri("/api/orders/{id}", orderId)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                )
                .expectBody(OrderResponse.class)
                .isEqualTo(new OrderResponse(
                        orderId,
                        orderRepository.findById(orderId)
                                .orElseThrow()
                                .getOrderNumber(),
                        "PAID"
                ));
    }
}
~~~

Trong ví dụ, constructor của **Order**, kiểu id và repository là mô hình minh họa; thay chúng bằng entity và persistence API thực tế của ứng dụng.

Điểm quan trọng là request đi qua địa chỉ HTTP và port của embedded server. Test không gọi trực tiếp **OrderController** hoặc **OrderService**. Spring phải nhận request, route tới controller, gọi service, đọc dữ liệu và tuần tự hóa response trước khi RestTestClient nhận được kết quả.

Khối **@AfterEach** xóa đúng bản ghi do test tạo. Không dùng một id cố định dùng chung giữa các lần chạy, và không xóa toàn bộ bảng nếu test khác có thể đang sử dụng cùng database.

## 5. Kiểm tra status, header và body

Một HTTP integration test nên xác nhận cả ba phần của response.

### HTTP status

Status thể hiện kết quả xử lý ở cấp giao thức:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectStatus().isOk();
~~~

Có thể kiểm tra status cụ thể như **isCreated()**, **isNoContent()**, **isBadRequest()**, **isUnauthorized()** hoặc **isNotFound()**. Chọn status theo hợp đồng endpoint.

### Response header

Header xác nhận metadata mà client thực sự nhận được:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
~~~

Có thể kiểm tra header khác:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectHeader()
        .exists(HttpHeaders.CACHE_CONTROL);
~~~

Với endpoint tạo tài nguyên, có thể kiểm tra **Location** nếu API trả header đó. Với endpoint tải file, cần xác nhận content type và content disposition. Với endpoint có cache, có thể xác nhận cache control hoặc ETag.

### Response body

Khi muốn xác nhận JSON theo DTO:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectBody(OrderResponse.class)
        .isEqualTo(expected);
~~~

Khi muốn xác nhận cấu trúc JSON trực tiếp:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectBody()
        .json("""
                {
                  "id": 42,
                  "orderNumber": "E2E-42",
                  "status": "PAID"
                }
                """);
~~~

So sánh JSON theo cấu trúc giúp test không phụ thuộc thứ tự property hoặc khoảng trắng. Khi API contract có quy định rõ một property bị bỏ qua, có giá trị null hoặc phải là một kiểu JSON cụ thể, hãy kiểm tra đúng sự khác biệt đó.

## 6. Kiểm thử luồng tạo rồi đọc tài nguyên qua HTTP

Một test end-to-end có thể kiểm tra nhiều endpoint trong một luồng nghiệp vụ. Ví dụ, client tạo đơn hàng rồi đọc lại đơn hàng vừa tạo.

~~~java
@Test
void shouldCreateAndThenReadAnOrder() {
    CreateOrderRequest request = new CreateOrderRequest(
            "E2E-" + java.util.UUID.randomUUID(),
            "PENDING"
    );

    OrderResponse created = client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists(HttpHeaders.LOCATION)
            .expectBody(OrderResponse.class)
            .returnResult()
            .getResponseBody();

    assertThat(created).isNotNull();

    client.get()
            .uri("/api/orders/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(OrderResponse.class)
            .isEqualTo(created);
}
~~~

Test này kiểm tra một chuỗi tương tác mà client thực hiện:

1. Gửi JSON request tới endpoint tạo đơn.
2. Server bind request body thành DTO.
3. Controller và service tạo dữ liệu.
4. Server trả status **201 Created**, header **Location** và DTO response.
5. Client dùng id trong response để gọi endpoint đọc.
6. Server truy vấn dữ liệu và trả về đơn hàng đã tạo.

Cần cleanup tài nguyên do test tạo sau khi hoàn thành. Có thể lấy id từ response rồi xóa qua repository hoặc gọi endpoint cleanup dành riêng cho test nếu ứng dụng có cơ chế đó. Nếu test thất bại giữa luồng, cleanup vẫn cần chạy trong **finally** hoặc **@AfterEach**.

Ví dụ trên dùng **body(request)** theo API request builder của RestTestClient. Cần dùng DTO và endpoint thực tế của ứng dụng khi áp dụng.

## 7. Kiểm tra validation và error response qua server thật

Một endpoint có thể hoạt động đúng ở controller test nhưng vẫn có vấn đề khi đi qua filter, security hoặc exception handling được đăng ký ở application context đầy đủ.

Ví dụ gửi dữ liệu không hợp lệ:

~~~java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreateOrderRequest("", "UNKNOWN"))
        .exchange()
        .expectStatus().isBadRequest()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
        )
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");
~~~

Kiểm thử qua server thật xác nhận request thực sự đi qua:

- HTTP message converter và quá trình deserialize.
- Bean Validation nếu endpoint dùng validation.
- Controller advice hoặc exception resolver.
- Security filter và các filter khác.
- Cấu hình response error mà ứng dụng công bố.

Có thể kiểm tra các tình huống khác như tài nguyên không tồn tại, request thiếu authentication, role không đủ quyền, content type không được hỗ trợ hoặc payload JSON sai định dạng.

Một test error response nên xác nhận cả status và error body. Chỉ kiểm tra rằng request bị từ chối chưa chứng minh API trả đúng mã lỗi hoặc schema lỗi.

## 8. Authentication, cookie và header qua HTTP thật

Khi cần kiểm tra Security filter chain, request phải mang thông tin xác thực theo cách client thật sử dụng. Ví dụ dùng bearer token:

~~~java
client.get()
        .uri("/api/profile")
        .headers(headers ->
                headers.setBearerAuth(accessToken)
        )
        .exchange()
        .expectStatus().isOk();
~~~

Nếu token khác nhau giữa các test, đặt token trên request builder để tránh làm bẩn default header của client dùng chung. Không lưu token riêng của một test vào cấu hình client nền rồi để test khác vô tình tái sử dụng.

Có thể kiểm tra cookie hoặc session bằng cách gửi header **Cookie** phù hợp và xác nhận response **Set-Cookie**. Khi test cơ chế session, cần giữ cookie trả về từ request trước và gửi lại trong request tiếp theo. Nếu API dùng cookie bảo mật hoặc CSRF, cần mô phỏng đúng quy trình mà browser/client phải thực hiện.

Một client HTTP thật sẽ đi qua security filter của server. Tuy nhiên, test chạy trên localhost không tự kiểm tra được cấu hình OAuth provider, identity proxy hoặc gateway bên ngoài nếu các thành phần đó không nằm trong đường request.

## 9. Database và dữ liệu test

Với server thật, request được xử lý trong luồng server riêng. Transaction của test method không tự bao bọc transaction trong request HTTP. Vì vậy, đặt **@Transactional** trên test không đảm bảo dữ liệu được tạo bởi endpoint sẽ rollback khi test kết thúc.

Một quy trình fixture rõ ràng thường gồm:

1. Tạo dữ liệu riêng cho test trước khi gửi request hoặc thông qua endpoint tạo.
2. Ghi nhận id của dữ liệu đó.
3. Gửi request và xác nhận response.
4. Xóa đúng dữ liệu test đã tạo trong cleanup.

Nếu test chạy song song, hãy dùng UUID, sequence riêng, tenant key hoặc database/schema riêng để tránh trùng dữ liệu. Không dùng **deleteAll()** trên một bảng dùng chung trong cleanup của từng test.

Với hệ thống có nhiều thành phần như database, Redis, message broker hoặc object storage, cleanup cần xử lý đúng từng resource. Reload Spring context không tự xóa dữ liệu bên ngoài context.

## 10. Server thật không có nghĩa là toàn bộ production environment

**RANDOM_PORT** khởi động embedded server thật trong tiến trình test. Request đi qua HTTP connector, nhưng thường vẫn chạy trên cùng máy với test.

Cấp độ này có thể xác nhận:

- Server khởi động và bind port.
- HTTP request đến đúng application.
- Filter chain, security, routing và controller hoạt động.
- Message converter và serialization hoạt động.
- Service và database tích hợp đúng trong môi trường test.
- Status, headers và response body mà client nhận được.

Nó chưa tự xác nhận:

- TLS termination ở load balancer hoặc ingress.
- Reverse proxy có buffering hoặc rewrite header hay không.
- DNS, service discovery và network policy của cluster.
- Cấu hình production secret và identity provider.
- Các khác biệt giữa database test và database production.
- Hành vi của toàn bộ hạ tầng triển khai.

Nếu mục tiêu là kiểm tra những thành phần đó, dùng **RestTestClient.bindToServer()** với base URL của môi trường staging hoặc môi trường triển khai tương ứng. Khi đó test cần có dữ liệu và quyền truy cập được chuẩn bị riêng cho môi trường đó.

Không gọi một test vào production nếu test có thể tạo, sửa hoặc xóa dữ liệu. Hãy dùng môi trường kiểm thử có dữ liệu và quyền phù hợp.

## 11. Khi nào dùng RestTestClient, WebTestClient hoặc TestRestTemplate?

| Công cụ | Phù hợp với | Kiểu kiểm thử |
|---|---|---|
| **RestTestClient** | REST API qua API test fluent của Spring Framework mới | Mock binding hoặc HTTP server thật tùy cách bind |
| **WebTestClient** | WebFlux và reactive endpoint; cũng có thể test một số MVC endpoint | Mock WebFlux/MVC hoặc HTTP server thật |
| **TestRestTemplate** | Spring Boot integration test với REST API, đặc biệt MVC | HTTP tới embedded server |
| **MockMvc** | Spring MVC controller và MVC infrastructure | Mock servlet request/response, không mở socket thật |

Chọn công cụ theo stack và mục tiêu. Nếu muốn kiểm tra một REST API đồng bộ bằng HTTP thật và project hỗ trợ Spring Framework 7.0, RestTestClient là lựa chọn phù hợp. Nếu cần test reactive flow, SSE hoặc streaming, WebTestClient thường có API phù hợp hơn. Nếu project dùng Spring Boot và Spring Framework cũ hơn, TestRestTemplate là một lựa chọn HTTP integration test quen thuộc.

## 12. Những lỗi thường gặp khi bind tới server

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Connection refused | Server chưa khởi động hoặc client dùng sai port | Dùng **RANDOM_PORT** và port được inject từ **@LocalServerPort** |
| Test gọi nhầm endpoint | Base URL hoặc context path không đúng | Kiểm tra base URL, servlet context path và URI |
| Client nhận 404 dù controller tồn tại | Controller không được component scan hoặc profile test không nạp cấu hình | Dùng application configuration phù hợp với test |
| Response khác mock test | Filter, security, converter hoặc cấu hình thật được bật | Kiểm tra full application context và request thực tế |
| Test pass riêng nhưng fail khi chạy cả suite | Dữ liệu dùng chung hoặc cleanup quá rộng | Dùng fixture id riêng và cleanup theo id |
| Test phụ thuộc port cố định | Port bị chiếm hoặc test chạy đồng thời | Dùng **RANDOM_PORT** |
| Dữ liệu không rollback sau test | Request server có transaction độc lập với test method | Cleanup rõ ràng hoặc dùng database riêng |
| Authentication khác với dự kiến | Token, cookie hoặc CSRF chưa được gửi như client thật | Kiểm tra request header/cookie và security flow |
| Test bị treo khi gọi endpoint | Server không trả response hoặc client timeout quá dài | Cấu hình timeout phù hợp và kiểm tra async/server log |
| Test nhầm mock server với server thật | Dùng chế độ MOCK hoặc bind vào application context | Dùng **RANDOM_PORT** và **bindToServer()** |

Khi gặp lỗi, hãy kiểm tra status, response body, header và log server. Một exception trong controller có thể được chuyển thành response 500; connection refused thường xảy ra trước khi request tới ứng dụng. Hai lỗi này cần được chẩn đoán ở hai lớp khác nhau.

## 13. Tổ chức test suite theo nhiều cấp

Không cần mọi test đều khởi động server thật. Có thể phân chia trách nhiệm như sau:

| Cấp test | Công cụ | Điều cần xác nhận |
|---|---|---|
| Unit test | JUnit, Mockito | Logic service, validation thuần và mapping độc lập |
| Controller test | MockMvc hoặc WebTestClient mock binding | Routing, binding, serialization và response contract |
| HTTP integration test | RestTestClient + **RANDOM_PORT** | HTTP connector, filter, security, controller, service và persistence |
| Deployment smoke test | RestTestClient + base URL môi trường | DNS, TLS, ingress, proxy và cấu hình triển khai có trong đường request |

HTTP integration test thường chậm hơn test mock vì phải khởi động server và các dependency. Hãy giữ số lượng vừa đủ để xác nhận các luồng quan trọng; dùng mock-bound test cho các trường hợp response nhỏ và logic lặp lại.

Một bài kiểm thử end-to-end có giá trị khi nó chứng minh được một luồng client thực sự cần dùng: request được gửi qua HTTP, server xử lý với cấu hình đang chạy, dữ liệu được lưu hoặc truy vấn, và client nhận status, header cùng body đúng hợp đồng. **RestTestClient.bindToServer()** cung cấp điểm bắt đầu cho loại kiểm thử đó.

