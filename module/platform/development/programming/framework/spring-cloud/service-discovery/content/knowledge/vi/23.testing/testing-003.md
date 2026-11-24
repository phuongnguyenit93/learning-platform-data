# Dùng SimpleDiscoveryClient để kiểm thử ứng dụng gọi dịch vụ

Khi kiểm thử một ứng dụng Spring Cloud gọi dịch vụ khác, không phải lúc nào cũng cần dựng Eureka Server, Consul hoặc ZooKeeper. Với danh sách endpoint cố định trong môi trường test, **SimpleDiscoveryClient** cho phép khai báo instance bằng cấu hình và cung cấp chúng qua abstraction `DiscoveryClient`.

Kết hợp SimpleDiscoveryClient với Spring Cloud LoadBalancer, ứng dụng vẫn có thể gọi service bằng service ID như `http://catalog-service/...`. LoadBalancer lấy danh sách instance từ discovery client, chọn một địa chỉ và chuyển request tới HTTP server tương ứng. Nhờ vậy, integration test có thể kiểm tra luồng gọi dịch vụ gần với cách ứng dụng chạy thật mà không phụ thuộc một registry bên ngoài.

Bài viết hướng dẫn cấu hình static instance trong test, kiểm tra danh sách qua DiscoveryClient, gọi provider bằng service ID với `@LoadBalanced RestTemplate`, dùng HTTP mock server để xác minh request và kiểm tra các tình huống không có instance hoặc provider lỗi.

## 1. SimpleDiscoveryClient phù hợp với loại kiểm thử nào?

SimpleDiscoveryClient đọc danh sách service instance từ cấu hình. Nó phù hợp khi:

- Muốn kiểm thử consumer mà không khởi động registry thật.
- Provider có endpoint cố định trong test hoặc được thay bằng mock HTTP server.
- Muốn kiểm tra service ID, host, port, metadata và luồng load balancing.
- Cần chạy integration test nhanh, độc lập với Docker Compose hoặc hạ tầng registry.
- Muốn mô phỏng nhiều instance bằng các URI khác nhau.

Ví dụ, consumer gọi `catalog-service`; trong test, service ID này được ánh xạ tới một HTTP mock server:

~~~mermaid
flowchart LR
    TEST["Integration test"]
    APP["Consumer application"]
    DC["SimpleDiscoveryClient"]
    LB["Spring Cloud LoadBalancer"]
    MOCK["Mock HTTP provider"]
    TEST --> APP
    APP -->|"catalog-service"| LB
    LB --> DC
    DC -->|"URI từ test properties"| LB
    LB -->|"HTTP request"| MOCK
~~~

Luồng gọi vẫn sử dụng service ID. Test có thể thay URI trong cấu hình mà không cần sửa mã consumer.

SimpleDiscoveryClient không mô phỏng đầy đủ hành vi của Eureka, Consul hoặc ZooKeeper. Nó không kiểm thử heartbeat, đăng ký động, lease expiration, ACL, watch, health check của registry hay đồng bộ catalog. Những phần đó cần integration test riêng với registry tương ứng.

## 2. Dependency cần thiết

Một consumer dùng `RestTemplate` và Spring Cloud LoadBalancer có thể cần các dependency sau:

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
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>${mockwebserver.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-cloud-starter-loadbalancer` cung cấp tích hợp load balancing và các thành phần discovery của Spring Cloud Commons. MockWebServer tạo một HTTP server nhẹ trong test để nhận request và trả response giả lập. Khai báo property `mockwebserver.version` theo phiên bản OkHttp tương thích mà dự án đang dùng; quản lý phiên bản Spring Cloud bằng Spring Cloud BOM tương thích với Spring Boot.

Nếu chỉ kiểm tra trực tiếp `DiscoveryClient`, không cần HTTP client hoặc mock server. Nếu kiểm tra cả luồng gọi dịch vụ, cần một HTTP client có tích hợp Spring Cloud LoadBalancer.

### Tránh vô tình dùng registry thật trong test

SimpleDiscoveryClient thường được dùng như implementation đơn giản khi không có discovery client khác. Nếu test runtime có thêm Eureka, Consul hoặc ZooKeeper starter, auto-configuration có thể chọn implementation tương ứng thay vì danh sách SimpleDiscoveryClient.

Để test có tính xác định:

- Chỉ đưa dependency discovery cần thiết vào test runtime nếu có thể.
- Dùng test profile hoặc cấu hình riêng cho test.
- Không để cấu hình endpoint registry production được nạp trong integration test.
- Xác minh bean DiscoveryClient thực tế đang cung cấp danh sách từ thuộc tính simple.instances.

Không nên cho test vô tình kết nối registry dùng chung của môi trường phát triển hoặc production.

## 3. Khai báo instance trong cấu hình

SimpleDiscoveryClient sử dụng property theo dạng:

~~~text
spring.cloud.discovery.client.simple.instances.<service-id>[<index>].uri
~~~

Ví dụ trong `application-test.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
                metadata:
                  zone: test-zone
                  version: v1
              - uri: http://localhost:18082
                metadata:
                  zone: test-zone
                  version: v1
            pricing-service:
              - uri: http://localhost:18083
                metadata:
                  zone: test-zone
                  version: v2
~~~

Trong ví dụ:

- `catalog-service` có hai instance.
- `pricing-service` có một instance.
- Mỗi instance có URI và metadata riêng.
- Consumer tra cứu theo service ID, không cần biết host/port cụ thể.

URI cần có scheme như `http` hoặc `https`. Metadata là các cặp key-value để test kiểm tra hoặc áp dụng bộ lọc. Chúng không tự tạo health check hay chính sách load balancing.

## 4. Consumer gọi service bằng service ID

Ví dụ cấu hình một `RestTemplate` có tích hợp load balancing:

~~~java
@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

`@LoadBalanced` đánh dấu RestTemplate để Spring Cloud LoadBalancer xử lý hostname service ID. Nếu bỏ annotation hoặc dùng một RestTemplate không có interceptor load balancing, `catalog-service` sẽ được xem như hostname DNS thông thường.

Mã consumer chỉ cần biết service ID:

~~~java
@Service
public class CatalogClient {

    private final RestTemplate restTemplate;

    public CatalogClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public CatalogItem find(String id) {
        return restTemplate.getForObject(
            "http://catalog-service/api/items/{id}",
            CatalogItem.class,
            id
        );
    }
}
~~~

DTO nhận response:

~~~java
public record CatalogItem(String id, String name) {
}
~~~

Khi gọi `find("42")`, LoadBalancer tra cứu `catalog-service`, chọn một `ServiceInstance` do SimpleDiscoveryClient cung cấp và thay service ID bằng URI thực tế trước khi gửi HTTP request.

## 5. Kiểm thử trực tiếp DiscoveryClient

Có thể kiểm tra danh sách instance và metadata mà không gửi HTTP request:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class SimpleDiscoveryClientTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void returnsConfiguredInstancesAndMetadata() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

        assertEquals(2, instances.size());
        assertTrue(instances.stream().anyMatch(instance ->
            "test-zone".equals(instance.getMetadata().get("zone"))
                && "v1".equals(instance.getMetadata().get("version"))));
    }

    @Test
    void returnsEmptyListForUnknownService() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("unknown-service");

        assertTrue(instances.isEmpty());
    }
}
~~~

Test đầu xác minh service ID có đúng số instance và metadata cần thiết. Test thứ hai xác minh service ID không được khai báo trả về danh sách rỗng.

Nếu thứ tự instance không phải một phần của hợp đồng, tránh kiểm tra host/port bằng vị trí cố định trong danh sách. Có thể kiểm tra bằng cách chuyển danh sách thành tập URI hoặc tìm instance theo metadata để test không phụ thuộc thứ tự.

## 6. Integration test với MockWebServer

Kiểm thử DiscoveryClient mới chỉ chứng minh cấu hình được đọc. Để kiểm tra ứng dụng thực sự gửi request đến provider, dùng một HTTP mock server với port động.

### Khởi tạo mock provider và cấp URI cho SimpleDiscoveryClient

~~~java
@SpringBootTest
@ActiveProfiles("mock-provider")
class CatalogClientIntegrationTest {

    private static final MockWebServer BACKEND = startBackend();

    @Autowired
    DiscoveryClient discoveryClient;

    @Autowired
    CatalogClient catalogClient;

    @DynamicPropertySource
    static void discoveryProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
            () -> BACKEND.url("/").toString()
        );
        registry.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone",
            () -> "test-zone"
        );
        registry.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.version",
            () -> "v1"
        );
    }

    @Test
    void discoversConfiguredInstance() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

        assertEquals(1, instances.size());
        assertEquals("test-zone",
            instances.get(0).getMetadata().get("zone"));
    }

    @Test
    void callsProviderUsingServiceId() throws Exception {
        BACKEND.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":\"42\",\"name\":\"Keyboard\"}"));

        CatalogItem item = catalogClient.find("42");

        assertEquals("42", item.id());
        assertEquals("Keyboard", item.name());

        RecordedRequest request =
            BACKEND.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/api/items/42", request.getPath());
    }

    @Test
    void providerErrorDoesNotRemoveStaticInstance() {
        BACKEND.enqueue(new MockResponse().setResponseCode(503));

        assertThrows(HttpServerErrorException.class,
            () -> catalogClient.find("42"));

        assertEquals(1,
            discoveryClient.getInstances("catalog-service").size());
    }

    @AfterAll
    static void stopBackend() throws IOException {
        BACKEND.shutdown();
    }

    private static MockWebServer startBackend() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }
}
~~~

Các import quan trọng gồm:

~~~java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
~~~

Các import JUnit, Spring Boot Test, RestTemplate, HttpServerErrorException, IOException, List và TimeUnit cũng cần được thêm theo đoạn mã thực tế.

`@DynamicPropertySource` đưa URI có port động của MockWebServer vào đúng property SimpleDiscoveryClient đọc. Test không hard-code một host port cố định và không cần khởi động registry. MockWebServer ghi lại request để xác minh consumer đã gọi đúng path.

Dùng profile `mock-provider` riêng cho test này và không nạp đồng thời danh sách hai URI của ví dụ `application-test.yml` ở phần trước. Nếu cấu hình nền hoặc profile đang hoạt động đã khai báo instance khác, hãy xóa chúng khỏi test property sources để kết quả chỉ còn endpoint động của MockWebServer.

Test lỗi 503 thể hiện một giới hạn có chủ đích: SimpleDiscoveryClient vẫn trả về instance đã khai báo dù provider trả lỗi HTTP. Nó không tự thực hiện health check và loại endpoint khỏi danh sách.

## 7. Kiểm thử nhiều instance

Có thể khai báo hai mock server và gắn URI của từng server vào hai index:

~~~java
registry.add(
    "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
    () -> backendA.url("/").toString()
);
registry.add(
    "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
    () -> backendB.url("/").toString()
);
~~~

Sau đó kiểm tra:

- DiscoveryClient trả về đủ hai instance.
- Cả hai URI đều có scheme, host và port hợp lệ.
- LoadBalancer có thể gửi request đến các instance trong danh sách.
- Metadata từng instance được giữ đúng.

Không nên khẳng định thứ tự request luân phiên cố định nếu chưa cấu hình thuật toán và seed rõ ràng. Round-robin có thể bắt đầu ở vị trí khác tùy trạng thái nội bộ. Với test phân phối, gửi đủ số request và xác minh tập endpoint đã nhận request thay vì giả định request đầu tiên luôn đến instance A.

## 8. Kiểm thử metadata và bộ lọc instance

Nếu ứng dụng dùng metadata để lọc theo zone hoặc version, khai báo metadata riêng cho từng URI:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://localhost:18082
                metadata:
                  zone: zone-b
                  version: v2
~~~

Test có thể xác minh dữ liệu đầu vào của filter:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("catalog-service");

assertTrue(instances.stream().anyMatch(instance ->
    "v2".equals(instance.getMetadata().get("version"))));
~~~

Nếu cần kiểm thử chính sách lọc của `ServiceInstanceListSupplier`, nên test supplier trực tiếp với danh sách instance có metadata xác định. Sau đó có thể thêm một integration test qua LoadBalancer để kiểm tra request cuối cùng đến đúng mock provider.

Phân biệt hai mục tiêu:

- Discovery test xác minh SimpleDiscoveryClient cung cấp đúng instance và metadata.
- Routing test xác minh supplier/load balancer áp dụng filter và chọn đúng endpoint.

Chỉ kiểm tra metadata có mặt không chứng minh bộ lọc định tuyến hoạt động đúng.

## 9. Kiểm thử khi không có instance

Khi service ID không có URI được cấu hình, DiscoveryClient trả danh sách rỗng. Khi gọi qua LoadBalancer, request không thể được chuyển tới provider và thường kết thúc bằng lỗi không có instance khả dụng.

Ví dụ kiểm tra discovery:

~~~java
@Test
void unknownServiceHasNoInstances() {
    assertTrue(
        discoveryClient.getInstances("missing-service").isEmpty()
    );
}
~~~

Nếu cần kiểm tra lỗi từ HTTP client, có thể gọi một service ID không được cấu hình và xác minh ứng dụng chuyển lỗi thành response hoặc exception phù hợp. Loại exception cụ thể có thể khác theo phiên bản Spring Cloud LoadBalancer và cách consumer xử lý lỗi; nên kiểm tra hợp đồng lỗi của ứng dụng thay vì khóa test vào thông điệp nội bộ của framework.

## 10. Kiểm thử timeout và provider không phản hồi

MockWebServer có thể mô phỏng:

- Response 500 hoặc 503.
- Response chậm hơn response timeout.
- Kết nối bị đóng trước khi trả body.
- Body sai định dạng JSON.
- Header hoặc content type không đúng.

Ví dụ trả response chậm:

~~~java
BACKEND.enqueue(new MockResponse()
    .setResponseCode(200)
    .setBody("{\"id\":\"42\",\"name\":\"Keyboard\"}")
    .setHeadersDelay(3, TimeUnit.SECONDS));
~~~

Để test timeout có ý nghĩa, HTTP client phải được cấu hình connect timeout và read/response timeout phù hợp. Không chỉ thêm delay vào mock server rồi giả định ứng dụng sẽ timeout nếu client không có giới hạn thời gian chờ.

Các tình huống nên xác minh:

1. Consumer kết thúc trong thời gian timeout đã đặt.
2. Lỗi được chuyển thành exception hoặc response theo hợp đồng của ứng dụng.
3. Retry, nếu có, bị giới hạn số lần.
4. Request không bị gửi lặp ngoài ý muốn với thao tác không idempotent.
5. Log và metric ghi nhận service ID cùng loại lỗi để hỗ trợ chẩn đoán.

## 11. Phân biệt discovery test với registry integration test

SimpleDiscoveryClient phù hợp để kiểm tra hành vi consumer với danh sách URI tĩnh. Khi cần xác minh hành vi của registry thật, phải có nhóm test khác.

| Mục tiêu | SimpleDiscoveryClient | Registry thật |
|---|---|---|
| Consumer tra cứu service ID | Có | Có |
| LoadBalancer chọn URI | Có | Có |
| Kiểm tra metadata mapping | Có | Có |
| Provider tự đăng ký | Không | Có thể có |
| Provider deregister khi shutdown | Không | Có thể có |
| Heartbeat/lease/session | Không | Có |
| Health check của registry | Không | Có theo implementation |
| ACL, TLS/mTLS của registry | Không | Có |
| Watch hoặc đồng bộ catalog | Không | Có theo implementation |

Có thể tổ chức test theo tầng:

- Unit test cho logic xử lý response và mapping DTO.
- Integration test với SimpleDiscoveryClient và MockWebServer cho luồng service ID → LoadBalancer → HTTP.
- Contract test giữa consumer và provider để xác minh API contract.
- Registry integration test với Eureka, Consul hoặc ZooKeeper cho đăng ký, health check, bảo mật và vòng đời instance.

Không cần đưa mọi test vào một test suite phụ thuộc hạ tầng. Phân tầng giúp test consumer chạy nhanh và vẫn có test riêng cho các đặc tính của registry.

## 12. Cấu hình test tách khỏi môi trường thật

Một số nguyên tắc để tránh test dùng nhầm endpoint:

- Đặt danh sách instance trong `application-test.yml` hoặc `@DynamicPropertySource`.
- Dùng hostname/port của mock server, không dùng địa chỉ production.
- Không nạp token, password hoặc certificate production vào test.
- Nếu ứng dụng có Eureka/Consul/ZooKeeper starter, cô lập dependency hoặc auto-configuration để SimpleDiscoveryClient thực sự được sử dụng.
- Đóng mock server sau test để giải phóng socket.
- Không phụ thuộc vào thứ tự instance nếu thuật toán không bảo đảm thứ tự đó.
- Tắt hoặc kiểm soát retry khi test lỗi để tránh request thừa và test kéo dài.
- Dùng port động để tránh xung đột giữa các test chạy song song.

Nếu test chạy song song, mỗi test context hoặc test class cần quản lý vòng đời MockWebServer riêng. Không chia sẻ một mock server mutable giữa nhiều test không đồng bộ vì response queue có thể bị tiêu thụ sai thứ tự.

## 13. Lỗi thường gặp khi kiểm thử

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getInstances()` trả danh sách rỗng | Sai service ID hoặc sai property prefix/index | Kiểm tra `simple.instances.<service-id>[index].uri` |
| URI được đọc nhưng gọi service ID thất bại | RestTemplate chưa có `@LoadBalanced` hoặc thiếu LoadBalancer starter | Kiểm tra bean và dependency |
| Test gọi nhầm registry thật | Registry starter khác đang có trong test runtime | Cô lập dependency hoặc auto-configuration |
| `localhost` không truy cập được mock server | Mock server chưa start hoặc port property được nạp quá sớm | Dùng `@DynamicPropertySource` với server khởi tạo tĩnh |
| Metadata không xuất hiện | Sai key path hoặc cấu hình metadata không bind | Kiểm tra property `metadata.<key>` và kết quả ServiceInstance |
| Test nhiều instance không ổn định | Giả định thứ tự round-robin cố định | Kiểm tra tập endpoint hoặc cấu hình thuật toán rõ ràng |
| Provider trả 503 nhưng vẫn được discovery | Đây là hành vi bình thường của danh sách tĩnh | Test health check riêng hoặc dùng registry có health integration |
| Test timeout không kết thúc | HTTP client chưa cấu hình timeout | Đặt connect/read timeout cho client |
| Test phụ thuộc cổng cố định | Port đã được tiến trình khác sử dụng | Dùng port động của MockWebServer |

## 14. Checklist cho integration test

1. Xác nhận test runtime sử dụng SimpleDiscoveryClient.
2. Khai báo service ID và URI bằng test properties.
3. Dùng `DiscoveryClient.getInstances()` để xác minh số lượng và metadata.
4. Kiểm tra service ID không tồn tại trả về danh sách rỗng.
5. Tạo mock HTTP provider với port động.
6. Dùng client có `@LoadBalanced` để gọi bằng service ID.
7. Xác minh HTTP method, path, header và body nhận được tại mock server.
8. Mô phỏng response thành công, lỗi server và timeout.
9. Xác minh lỗi HTTP không tự làm SimpleDiscoveryClient xóa URI.
10. Đóng mock server và không để test dùng cấu hình hoặc secret production.

SimpleDiscoveryClient giúp kiểm thử phần tra cứu và gọi dịch vụ với danh sách endpoint có thể kiểm soát. Khi kết hợp với Spring Cloud LoadBalancer và một HTTP mock server, integration test có thể xác minh consumer sử dụng service ID, chọn instance và gửi request đúng. Cần nhớ đây là kiểm thử luồng gọi dựa trên cấu hình tĩnh; đăng ký động, health check, heartbeat, bảo mật và đồng bộ registry vẫn phải được kiểm tra riêng với implementation thực tế.
