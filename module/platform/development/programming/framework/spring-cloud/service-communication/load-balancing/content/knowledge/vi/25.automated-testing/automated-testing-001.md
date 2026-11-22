# Phân chia unit test, integration test và kiểm thử tải

**Spring Cloud LoadBalancer** có thể chọn đúng `ServiceInstance` trong một unit test nhưng request HTTP vẫn thất bại vì discovery, interceptor, DNS, connection pool hoặc timeout được cấu hình sai. Ngược lại, một integration test gọi thành công vài lần chưa chứng minh rằng hệ thống phân phối tải ổn định khi số request đồng thời tăng mạnh.

Vì vậy, kiểm thử một hệ thống giao tiếp microservices phải có **nhiều tầng kiểm chứng, mỗi tầng trả lời một câu hỏi khác nhau**:

- **Unit test:** *Thuật toán lựa chọn, chính sách lọc instance và fallback có đúng với dữ liệu đầu vào đã cho không?*
- **Integration test:** *Các thành phần Spring thực sự được nối với nhau đúng chưa; service ID có được chuyển thành instance vật lý và HTTP request có đi tới đúng nơi không?*
- **Kiểm thử tải (load/performance test):** *Dưới lưu lượng và số kết nối đồng thời dự kiến, phân phối, độ trễ, thông lượng và tỷ lệ lỗi có nằm trong giới hạn chấp nhận không?*

Bài thuộc chương **Kiểm thử tự động** của module Spring Cloud LoadBalancer, bao quát discovery, `ServiceInstanceListSupplier`, health check, zone/hint routing, `RestClient`, `WebClient`, OpenFeign và những tương tác với retry/timeout. Trọng tâm là **phân chia trách nhiệm kiểm thử** để vừa có kết quả nhanh và ổn định trong CI, vừa không bỏ sót các lỗi chỉ xuất hiện khi chạy hệ thống thật.

## 1. Mô hình kiểm thử theo ranh giới của LoadBalancer

Một lời gọi giữa các dịch vụ có thể đi theo luồng:

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ<br/>GET http://catalog-service/products/42"]
    B["@LoadBalanced RestClient / WebClient<br/>hoặc OpenFeign"]
    C["Spring Cloud LoadBalancer<br/>chọn một ServiceInstance"]
    D["ServiceInstanceListSupplier<br/>discovery, cache, health, zone"]
    E["HTTP transport<br/>pool, DNS, TCP/TLS, timeout"]
    F["catalog-service instance"]
    U["UNIT<br/>Kiểm tra policy, supplier, selection"]
    I["INTEGRATION<br/>Kiểm tra wiring và request HTTP thật"]
    L["LOAD<br/>Kiểm tra throughput, latency, fairness, saturation"]
    A --> B --> C
    C <--> D
    C --> E --> F
    U -.-> C
    U -.-> D
    I -.-> B
    I -.-> E
    L -.-> A
    L -.-> F
~~~

**Không nên kỳ vọng một loại test bao phủ mọi loại lỗi.** Có thể dùng mock để kiểm tra strict-region filter, nhưng mock không phát hiện lỗi `@LoadBalanced` bị thiếu. Ngược lại, có thể gọi được một endpoint local nhưng không biết policy có chọn instance bị cấm trong mọi tình huống dữ liệu hay không.

| Trục so sánh | Unit test | Integration test | Kiểm thử tải |
|---|---|---|---|
| Đơn vị quan sát | Hàm, filter, supplier, selector | Spring context + HTTP client + discovery giả/registry | Đường gọi từ caller qua các instance |
| I/O mạng | Không | Có, thường tới server trong test | Có, với traffic mô phỏng có kiểm soát |
| Nguồn instance | List/fake supplier bất biến | `SimpleDiscoveryClient`, fake registry, Testcontainers | Discovery hoặc môi trường gần production |
| Loại assertion | Chính xác, xác định, lặp lại | Response thực, instance được chọn, lỗi/wiring | SLO, tỉ lệ phân phối, p95/p99, error rate, capacity |
| Tốc độ phản hồi khi sửa mã | Thường nhanh nhất | Chậm hơn do tạo context/server | Tốn tài nguyên; chạy theo lịch/gate |
| Lỗi được phát hiện tốt nhất | Policy sai và edge case | Dependency, bean, URI, interceptor, HTTP integration | Pool exhaustion, retry storm, latency tail, hotspot |
| Điều **không** chứng minh | HTTP transport hoạt động | Độ bền dưới tải lớn | Tính đúng tuyệt đối với mọi đầu vào |

Các tầng bổ sung như **contract test** và **end-to-end test** vẫn hữu ích, nhưng không thay thế ba tầng trên: contract test kiểm tra schema/HTTP agreement; end-to-end test kiểm tra một luồng nghiệp vụ qua nhiều dịch vụ.

## 2. Thiết kế tiêu chí nghiệm thu trước khi viết test

Ví dụ `catalog-service` có hai instance:

| Instance ID | URI | Zone | Weight |
|---|---|---|---:|
| `catalog-a` | `http://127.0.0.1:8081` | `zone-a` | 3 |
| `catalog-b` | `http://127.0.0.1:8082` | `zone-b` | 1 |

Ứng dụng `order-service` gọi URL logic `http://catalog-service`. Trước khi chọn công cụ test, hãy mô tả các quy tắc muốn bảo đảm:

1. Khi danh sách rỗng, **không chọn** một instance tùy tiện.
2. Khi dùng round-robin và hai instance hợp lệ, cả hai đều có cơ hội được chọn.
3. Khi chính sách yêu cầu **chỉ dùng `zone-a`**, nếu chỉ còn `zone-b` thì phải fail-closed, không chuyển vùng.
4. Khi dùng **zone preference mềm**, không có instance ở zone ưu tiên thì có thể fallback về danh sách còn lại.
5. Khi `catalog-a` ngừng phản hồi, client không bị treo quá ngân sách timeout/retry.
6. Dưới tải mục tiêu, p95/p99 latency và error rate nằm trong mức đã thống nhất; không có một instance bị quá tải ngoài dự kiến.

Mỗi quy tắc có thể được kiểm ở một hoặc nhiều tầng, nhưng **chọn tầng thấp nhất đủ để chứng minh nó**. Quy tắc 3 có thể được kiểm tra rất đầy đủ bằng unit test, sau đó có một integration test xác nhận filter đã được gắn đúng cho service ID.

## 3. Test pyramid dành cho Spring Cloud LoadBalancer

Một chiến lược hữu ích:

~~~text
             ÍT HƠN / CHẬM HƠN
             ┌────────────────┐
             │ Load / Soak /  │
             │ Failure tests  │
             ├────────────────┤
             │ Integration    │
             │ + HTTP clients │
             ├────────────────┤
             │ Unit: selector │
             │ / supplier     │
             │ / fallback     │
             └────────────────┘
             NHIỀU HƠN / NHANH HƠN
~~~

Đây là **phân bố tương đối**, không phải quy tắc tỷ lệ số lượng test cố định. Một đội có thể chạy hàng chục unit tests trên mỗi commit, một tập integration tests trên mỗi pull request và kiểm thử tải nặng trước release hoặc theo lịch.

Điểm quan trọng là **không biến mọi yêu cầu thành `@SpringBootTest`**. Nếu chỉ cần kiểm tra `filterByRegion(...)` với ba phần tử, việc mở một application context hoàn chỉnh không bổ sung bằng chứng đáng kể, nhưng làm test chậm và dễ chịu ảnh hưởng của môi trường.

## 4. Unit test: kiểm tra chính sách lựa chọn như một hàm thuần

### Khi nào unit test là đủ?

Các tình huống phù hợp:

- Lọc instance theo metadata `zone`, `region`, API version hoặc tenant policy đã xác thực.
- Xác minh fallback mềm hoặc fail-closed.
- Kiểm tra cách xử lý danh sách rỗng, metadata thiếu, giá trị weight sai.
- Chứng minh thuật toán tùy biến không chọn phần tử ngoài tập hợp hợp lệ.
- Kiểm tra tiêu chí ưu tiên/tie-breaking khi đầu vào cố định.
- Xác minh request context được diễn giải đúng nếu có thể dựng dữ liệu `Request` giả.

**Đừng tạo HTTP server trong unit test.** Dữ liệu nguồn là list/fake supplier, không phải discovery thật.

### 4.1. Ví dụ policy lọc theo vùng bắt buộc

Giả sử hệ thống chỉ cho phép một số instance theo `region`. Tách logic lọc thành một hàm có thể kiểm thử độc lập:

~~~java
import java.util.List;
import java.util.Objects;
import org.springframework.cloud.client.ServiceInstance;

public final class RequiredRegionPolicy {

    public List<ServiceInstance> eligible(
            List<ServiceInstance> instances,
            String requiredRegion) {

        Objects.requireNonNull(instances);
        Objects.requireNonNull(requiredRegion);

        return instances.stream()
                .filter(instance -> instance.getMetadata() != null)
                .filter(instance -> requiredRegion.equals(
                        instance.getMetadata().get("region")))
                .toList();
    }
}
~~~

Đây là **lớp policy minh họa**. Khi dùng thật, `ServiceInstanceListSupplier` tùy biến có thể gọi chính hàm `eligible(...)` trong `get()`/`get(Request)` để tránh logic ở test và production bị tách đôi.

Unit test bằng JUnit Jupiter:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.DefaultServiceInstance;

import static org.junit.jupiter.api.Assertions.*;

class RequiredRegionPolicyTest {

    private final RequiredRegionPolicy policy =
            new RequiredRegionPolicy();

    private static ServiceInstance instance(
            String id, String region) {

        DefaultServiceInstance result =
                new DefaultServiceInstance(
                        id, "catalog-service",
                        "127.0.0.1", 8081, false);

        if (region != null) {
            result.getMetadata().put("region", region);
        }

        return result;
    }

    @Test
    void onlyAllowedRegionSurvives() {
        ServiceInstance a = instance("a", "region-a");
        ServiceInstance b = instance("b", "region-b");
        ServiceInstance missing = instance("x", null);

        List<ServiceInstance> actual = policy.eligible(
                List.of(a, b, missing), "region-a");

        assertEquals(List.of(a), actual);
    }

    @Test
    void noAllowedRegionMustFailClosed() {
        ServiceInstance b = instance("b", "region-b");

        assertTrue(policy.eligible(
                List.of(b), "region-a").isEmpty());
    }

    @Test
    void emptyDiscoveryIsStillEmpty() {
        assertTrue(policy.eligible(
                List.of(), "region-a").isEmpty());
    }
}
~~~

Bộ test trên kiểm tra **kết quả danh sách**, không kiểm tra HTTP status. Nếu custom supplier trả danh sách rỗng, `RoundRobinLoadBalancer` sẽ không có ứng viên; cách integration biểu diễn lỗi HTTP cụ thể phụ thuộc client/version và nên được kiểm ở tầng integration.

### 4.2. Unit test cho supplier và selector thật

Nếu class production là một `ServiceInstanceListSupplier` tự viết, nên test trực tiếp:

- `get()` trả đúng candidate list.
- `get(Request)` nhận đúng context cần thiết; không mất hint/tenant.
- Nếu delegate trả `Flux`, test với `StepVerifier` để xác minh emissions/completion/errors khi thích hợp.
- Filter chỉ dùng metadata đáng tin cậy, xử lý `null` hoặc thiếu field.
- Không giữ state giữa hai request khiến dữ liệu của caller A ảnh hưởng caller B.

Nếu kiểm tra một `ReactorServiceInstanceLoadBalancer` tùy biến, cung cấp fake `ObjectProvider<ServiceInstanceListSupplier>` hoặc test fixture theo API của version và gọi `choose(request)`. Test phải xác nhận instance nằm trong tập hợp cho phép và kết quả khi danh sách rỗng; không cần mở socket.

### 4.3. Những điều không nên khẳng định cứng

| Policy | Assertion ổn định | Assertion dễ flaky |
|---|---|---|
| Round-robin | Mọi lựa chọn thuộc tập nguồn, đủ lượt có cả hai instance trong fixture ổn định | Lần gọi đầu **luôn** là instance A |
| Random | Không chọn ngoài danh sách; phân phối gần kỳ vọng khi lấy mẫu đủ lớn | Chính xác 50/50 sau 10 request |
| Weighted | Trong test thống kê lớn, tỷ lệ nằm trong khoảng chấp nhận có giải thích | Cứ 4 request thì đúng 3 request vào A |
| Zone preference | Khi có match trả ưu tiên; không match fallback theo semantics thực tế | Không bao giờ cross-zone nếu dùng soft preference |
| Strict region | Không trả instance sai region kể cả khi danh sách rỗng | Tự “cứu” request bằng fallback không được phép |
| Health check | Đã lọc đúng theo snapshot/response probe | Một instance sống sẽ luôn khỏe ở mọi thời điểm |

Nếu thuật toán có random seed hoặc trạng thái round-robin, hãy kiểm soát seed/state trong fixture nếu API hỗ trợ, hoặc assert theo **bất biến** thay vì thứ tự lựa chọn tuyệt đối.

## 5. Kiểm thử đặc tính: property-based và bảng dữ liệu biên

Một số quy tắc rất phù hợp với property-based testing:

- **Không chọn ngoài nguồn:** với mọi danh sách đầu vào, kết quả selector phải thuộc danh sách đó hoặc là no-server.
- **Fail-closed:** khi không có instance đủ điều kiện, bộ lọc strict phải trả rỗng.
- **Không làm biến đổi nguồn:** policy không được sửa metadata/danh sách chia sẻ không kiểm soát.
- **Độc lập thứ tự:** nếu policy chỉ lọc theo region, đảo thứ tự danh sách không làm thay đổi tập hợp kết quả.
- **Metadata lạ:** thiếu `zone`, `weight` âm/không parse được, duplicate instance ID và list trống không được gây NPE không kiểm soát.

Ví dụ bảng test cho một supplier:

| Input | Policy | Expected |
|---|---|---|
| A(zone-a), B(zone-b) | Prefer zone-a | A |
| Chỉ B(zone-b) | Prefer zone-a | B nếu soft fallback |
| Chỉ B(zone-b) | Require zone-a | Empty nếu strict |
| A thiếu zone | Require zone-a | Empty |
| Empty list | Bất kỳ | Empty / no-server |
| A, A duplicate ID | Chọn instance | Xử lý duplicate theo hợp đồng và policy |
| A weight=0, B weight=3 | Weighted | Xác minh quy tắc weight theo version, không tự suy đoán |

**Unit test nên phản ánh đúng semantics của supplier cụ thể.** Chẳng hạn `ZonePreferenceServiceInstanceListSupplier` và `HealthCheckServiceInstanceListSupplier` có các fallback mềm trong những cấu hình thông thường; đừng viết test dựa vào giả định chúng mặc định fail-closed.

## 6. Integration test: xác nhận Spring wiring và HTTP request thật

Unit test không phát hiện các lỗi sau:

- Thiếu dependency `spring-cloud-starter-loadbalancer`.
- Bean `RestClient.Builder` không có `@LoadBalanced`.
- Dùng bean `RestClient` thường để gọi `http://catalog-service` nên host bị xử lý qua DNS.
- `@LoadBalancerClient` chứa sai service ID hoặc configuration class bị scan nhầm.
- `SimpleDiscoveryClient` không bind được URI từ properties.
- LoadBalancer đã chọn instance nhưng HTTP transport không kết nối được tới host/port.
- HTTP client được cấu hình retry/timeout khác dự định.

Để kiểm tra các điểm này, cần **tạo Spring ApplicationContext thật** và **một hoặc nhiều HTTP server thử nghiệm**.

### 6.1. Dependency kiểm thử

Ví dụ Gradle Kotlin DSL với Spring Boot/Spring Cloud BOM tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Snippet giả định ứng dụng dùng `RestClient` và Java 17+, Spring Framework 6.1+; tùy Spring Boot version, starter HTTP có thể khác. Chọn BOM theo release train thay vì cố định version starter không tương thích.

**Không cần Eureka cho mọi integration test.** Khi kiểm thử riêng Spring Cloud LoadBalancer và HTTP integration, có thể dùng `SimpleDiscoveryClient` cùng các server in-process. Khi muốn xác minh đăng ký/refresh thực sự, mở rộng sang Testcontainers + Eureka/Consul hoặc test environment tương ứng.

## 7. Ví dụ integration test với hai backend HTTP thật

Ví dụ dưới đây dùng JDK `HttpServer` làm hai backend thử nghiệm độc lập, tạo port ngẫu nhiên để tránh xung đột CI. `@DynamicPropertySource` đăng ký các URI vào `SimpleDiscoveryClient` **trước khi Spring context được khởi tạo**.

### 7.1. Một test class tích hợp tương đối đầy đủ

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        classes = LoadBalancedRestClientIT.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "spring.cloud.loadbalancer.cache.enabled=false",
            "spring.cloud.loadbalancer.retry.enabled=false"
        })
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LoadBalancedRestClientIT {

    private static final HttpServer A = server("catalog-a");
    private static final HttpServer B = server("catalog-b");

    @DynamicPropertySource
    static void registerInstances(DynamicPropertyRegistry properties) {
        properties.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
            () -> "http://127.0.0.1:" + A.getAddress().getPort());

        properties.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
            () -> "http://127.0.0.1:" + B.getAddress().getPort());
    }

    @Autowired
    @Qualifier("catalogRestClient")
    RestClient client;

    @Test
    void choosesBothInstancesThroughServiceId() {
        Set<String> observed = new HashSet<>();

        for (int i = 0; i < 12; i++) {
            String body = client.get()
                    .uri("/whoami")
                    .retrieve()
                    .body(String.class);
            observed.add(body);
        }

        assertEquals(
                Set.of("catalog-a", "catalog-b"),
                observed);
    }

    @AfterAll
    static void stopServers() {
        A.stop(0);
        B.stop(0);
    }

    private static HttpServer server(String identity) {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext("/whoami", exchange -> {
                byte[] bytes =
                        identity.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean
        @LoadBalanced
        RestClient.Builder loadBalancedRestClientBuilder() {
            return RestClient.builder();
        }

        @Bean("catalogRestClient")
        RestClient catalogRestClient(
                @LoadBalanced RestClient.Builder builder) {
            return builder
                    .baseUrl("http://catalog-service")
                    .build();
        }
    }
}
~~~

**Điều test chứng minh:** nếu cấu hình LoadBalancer hoạt động với chính sách round-robin mặc định, client gọi một URL service ID và nhận response từ cả hai backend vật lý. Đó là một **integration assertion**, khác với unit test chỉ kiểm tra danh sách ứng viên.

**Điều test chưa chứng minh:** tỉ lệ 50/50 dưới tải thật, tính đúng của health check, retry sau timeout, hoặc độ bền khi registry cập nhật danh sách động.

### 7.2. Tại sao thiết kế như vậy?

- **Port 0** yêu cầu hệ điều hành cấp cổng rảnh; không hardcode `8081`/`8082` trong cùng CI agent.
- **`@DynamicPropertySource`** phù hợp khi URI chỉ biết sau khi fake server chạy.
- **`@DirtiesContext`** giúp tránh dùng lại context có cấu hình gắn với những server đã bị dừng.
- **Tắt LoadBalancer cache** để ví dụ dễ kiểm soát; trong production, cache có thể cần được bật.
- **Tắt retry trong test** để số lần HTTP gọi không bị nhân lên bởi policy không mong đợi.
- **`RestClient.Builder` có `@LoadBalanced`** để gọi theo service ID; nếu bỏ annotation và không có DNS cho `catalog-service`, integration test sẽ lộ lỗi wiring.
- **Assertion dùng tập kết quả**, không phụ thuộc instance được chọn ở request đầu tiên hay số request chính xác trên từng instance.
- Test chỉ dùng server nội bộ trong tiến trình và không phụ thuộc dịch vụ bên ngoài không ổn định.

Ví dụ giả định bộ test có quyền mở port loopback và module JDK `jdk.httpserver` khả dụng. Trong dự án dùng JPMS hoặc runtime image tối giản, cần bảo đảm module này có mặt, hoặc thay bằng WireMock/MockWebServer đã quản lý dependency tương thích.

### 7.3. Đảm bảo test không phụ thuộc state chung

Nếu một test trước đó bật cache/zone preference/weighted policy trong cùng context, việc quan sát hai instance theo round-robin có thể thay đổi. Để ổn định:

1. Đặt rõ property dùng cho test.
2. Không tái dùng Spring context với dynamic URI từ server đã đóng.
3. Không dựa vào thứ tự chạy các test.
4. Không chia sẻ singleton có mutable state giữa các class test độc lập nếu không reset.
5. Dùng một fixture phục vụ đúng policy cần kiểm thử thay vì thêm quá nhiều điều kiện ngầm.

## 8. Integration test cho HTTP clients: RestClient, WebClient và OpenFeign

Cả ba client có thể đi qua Spring Cloud LoadBalancer, nhưng adapter và phương thức quan sát khác nhau.

| Client | Điểm tích hợp cần kiểm tra | Assertion tối thiểu |
|---|---|---|
| `RestClient` | `@LoadBalanced RestClient.Builder`, `BlockingLoadBalancerClient` | Dùng service ID, response từ server thật |
| `WebClient` | `@LoadBalanced WebClient.Builder` / LoadBalancer exchange filter | `bodyToMono(...)` nhận đúng instance, cancel/timeout không phá contract |
| OpenFeign | `@FeignClient(name=...)`, `@EnableFeignClients`, `FeignBlockingLoadBalancerClient` | Interface được inject, gọi service ID, codec/status hoạt động |
| HTTP Interface | Proxy dùng `RestClient` hoặc `WebClient` đã gắn LoadBalancer | Method interface tới đúng backend; group/auto-config theo version |

**Không được dùng một HTTP client thường rồi cho rằng đã kiểm tra LoadBalancer.** Một URL như `http://catalog-service` có thể hoạt động nhờ DNS Kubernetes/mesh, trong khi Spring Cloud LoadBalancer của ứng dụng hoàn toàn không tham gia.

### WebClient test

Với WebClient, có thể dùng cùng fake HTTP servers nhưng tạo `@LoadBalanced WebClient.Builder`. Assertion nên làm rõ:

- Subscription có thực thi request.
- Exchange filter chọn đúng service ID/instance.
- Có thể nhận response hợp lệ khi không có lỗi.
- Timeout, cancel và body decoding được xử lý theo contract của WebClient.
- Không chặn event loop bằng `block()` trong mã production reactive; trong integration test đồng bộ hóa có thể dùng `StepVerifier` với timeout của test.

### OpenFeign test

Với Feign:

- Kiểm tra `@EnableFeignClients` có scan đúng interface.
- Không gắn thuộc tính `url` trong `@FeignClient`/properties nếu muốn test chọn theo service ID; URL cố định sẽ bỏ qua LoadBalancer.
- Kiểm tra kiểu HTTP `Client` thực tế, đặc biệt khi dự án dùng Apache HttpClient 5 hoặc override `feign.Client`.
- Kiểm tra status, decoder, connect/read timeout, request interceptors và fallback riêng thay vì chỉ xem proxy được inject.
- Mỗi test nên kiểm soát retry và idempotency; Spring Cloud OpenFeign thường dùng `Retryer.NEVER_RETRY` mặc định ở tầng Feign, nhưng không có nghĩa các tầng khác đã tắt retry.

## 9. Những kịch bản integration quan trọng ngoài happy path

Một bài test chỉ chứng minh “gọi được 200” chưa đủ. Cần có một ma trận tình huống:

| Kịch bản | Thiết lập | Điều cần xác minh |
|---|---|---|
| **Không có instance** | Supplier trả danh sách rỗng | Không gửi HTTP tới backend khác; lỗi no-server được xử lý |
| **Service ID sai** | `catalog-unknown` không có instance | Không bị “fallback” sang hostname vật lý tùy tiện |
| **Một instance chết** | Backend dừng nhưng danh sách còn URI | Có thể chọn endpoint lỗi; nhận diện transport error |
| **Discovery cập nhật** | Registry/supplier thay danh sách | Sau refresh/cache TTL, client ngừng chọn instance bị loại |
| **Zone preference mềm** | Không có instance trong zone ưu tiên | Fallback theo semantics đã chọn, không coi đây là hard constraint |
| **Strict-region** | Chỉ có instance vùng bị cấm | Không có request nào tới vùng bị cấm; fail-closed |
| **Health-check** | Endpoint health 200/503, thay trạng thái | Danh sách healthy thay đổi theo chu kỳ; biết rõ fallback khi không healthy |
| **Retry** | Backend đầu trả lỗi transient | Số attempt, idempotency và instance của từng attempt phù hợp policy |
| **Timeout** | Server cố ý trả chậm | Client dừng đúng budget, phân biệt read/connect/pool wait |
| **Response sai contract** | JSON sai kiểu, HTTP 200 body rỗng | Nhận lỗi decode/validation, không nhầm lỗi discovery |
| **Pool bị chiếm** | Nhiều request giữ connection | Lỗi chờ mượn connection có giới hạn, tài nguyên được giải phóng |
| **Instance metadata sai** | Thiếu `zone`/`weight` | Chính sách có fallback hoặc reject đúng quy định |

Trong integration test, nên điều khiển trạng thái backend bằng endpoint thử nghiệm, fake registry hoặc fault injection nhẹ. Không phụ thuộc vào việc tắt một service production hoặc điều chỉnh firewall thật của môi trường chung.

### Tách test với discovery tĩnh và registry động

`SimpleDiscoveryClient` rất phù hợp để kiểm chứng lookup và routing theo URI đã cấu hình. Nhưng nó là **nguồn instance tĩnh**: dừng một HTTP server không tự xóa nó khỏi danh sách.

Muốn test lifecycle **register → deregister → refresh**, cần fixture hỗ trợ thay đổi danh sách hoặc một registry thật trong test. Đồng thời phải tính tới cache của DiscoveryClient, LoadBalancer, interval health check và thời điểm context được khởi tạo.

## 10. Kiểm thử tải: mục tiêu và điều kiện thực hiện

Load test không chỉ “gửi nhiều request”. Trước khi chạy cần biết **mục tiêu nghiệp vụ**, **cấu hình thực tế** và **ngưỡng dừng**.

Các câu hỏi thường đặt ra:

- Với mức **RPS mục tiêu** và concurrent users, p95/p99 latency là bao nhiêu?
- LoadBalancer có tạo phân phối tương đối phù hợp giữa các `ServiceInstance` không?
- Một instance có trở thành **hotspot** dù nhiều instance khác còn khỏe?
- Khi backend chậm, hàng chờ connection pool có tăng bất thường không?
- Retry có nhân số request, gây retry storm hay không?
- Khi một instance bị loại, traffic có chuyển sang instance còn lại đúng policy?
- Khi quá tải, hệ thống có trả lỗi có kiểm soát thay vì treo, OOM hoặc chặn toàn bộ caller?

**Kiểm thử tải phải tạo traffic tại đầu vào của caller dùng LoadBalancer**, không chỉ bắn request trực tiếp vào từng instance. Nếu tool gọi thẳng `http://127.0.0.1:8081`, kết quả không đo cơ chế chọn instance của `order-service`.

### Một cách đặt SLO thử nghiệm

Ví dụ mục tiêu riêng cho môi trường lab:

| Chỉ số | Ngưỡng *minh họa*, không phải chuẩn chung |
|---|---|
| Throughput | 60 request/s tại entrypoint caller |
| p95 latency đầu-cuối | Dưới 500 ms |
| p99 latency đầu-cuối | Dưới 900 ms |
| Tỉ lệ HTTP thất bại | Dưới 1% |
| Mất lượt tạo tải từ tool | 0 dropped iterations |
| Memory/CPU/FD/sockets | Không vượt giới hạn hạ tầng đã xác định |
| Phân phối instance | Phù hợp thuật toán sau khi kiểm soát filter/weight |
| Retry amplification | Không vượt giới hạn attempts/budget đã thống nhất |

Các ngưỡng cần xuất phát từ **SLO và capacity thực tế**. Không chọn số tùy ý rồi coi hệ thống production đạt yêu cầu khi pass.

## 11. Ví dụ k6: bắn tải qua caller chứ không qua backend

Giả sử `order-service` chạy local ở cổng `8080` với endpoint thử nghiệm `GET /test/catalog`. Endpoint này dùng một `@LoadBalanced RestClient` gọi `catalog-service` và trả response. Đây là **endpoint phải tự triển khai cho bài lab**, không phải route mặc định của Spring Cloud.

Ví dụ k6:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    stable_load: {
      executor: "constant-arrival-rate",
      rate: 60,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 30,
      maxVUs: 100
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<900"],
    dropped_iterations: ["count==0"]
  }
};

export default function () {
  const response = http.get(
    "http://127.0.0.1:8080/test/catalog",
    { tags: { operation: "catalog-read" } }
  );

  check(response, {
    "caller returns 200": (r) => r.status === 200
  });
}
~~~

**Giải thích phép đo:**

- `constant-arrival-rate` cố gắng khởi tạo 60 iterations mỗi giây, không nhất thiết đảm bảo đạt nếu thiếu VUs/capacity.
- `http_req_duration` là độ trễ **k6 thấy từ entrypoint caller**, không phải riêng thời gian chọn instance.
- `http_req_failed` bao gồm điều kiện lỗi của HTTP request từ k6 tới caller; lỗi downstream bị application che bởi response 200 có thể không được metric này nhận diện.
- `dropped_iterations` giúp phát hiện load generator không duy trì được lịch phát request.
- `check(...)` là kiểm tra kết quả; khi đặt thresholds, cần đồng bộ điều kiện “đúng nghiệp vụ” với metric đánh giá thất bại, không chỉ HTTP 200.

**Không dùng URL trực tiếp của backend** nếu mục tiêu là đo LoadBalancer. Nếu chạy k6 từ một container khác, `127.0.0.1` là container đó, không phải máy host; chỉnh địa chỉ caller theo topology test.

### Phân biệt load test và stress/soak test

| Loại | Mục tiêu | Kết luận được |
|---|---|---|
| Baseline | Lưu lượng thấp và ổn định | Chi phí cố hữu của các thành phần |
| **Load test** | Lưu lượng dự kiến khi vận hành | Có đạt SLO ở mức tải mục tiêu? |
| **Stress test** | Tăng tải qua ngưỡng | Điểm bão hòa và cách thất bại |
| **Spike test** | Tăng/giảm đột ngột | Khả năng phục hồi sau burst |
| **Soak test** | Giữ tải lâu | Rò rỉ socket, heap, connection pool, cache/metric growth |
| **Resilience/failure test** | Kill/slow backend dưới tải | Chuyển hướng, retry amplification và phục hồi |

Các loại test có thể dùng cùng công cụ phát tải, nhưng **cách tăng tải và tiêu chí chấp nhận** phải được định nghĩa riêng.

## 12. Đo đúng số liệu ở cả caller và instance

Một dashboard chỉ có “thành công 99%” thường chưa đủ để giải thích LoadBalancer hoạt động tốt hay không.

### Tầng caller

Nên đo:

- Total inbound requests, RPS, p50/p95/p99 latency.
- HTTP status và error category (no-instance, connect/read timeout, 4xx/5xx, decode).
- Số lần chọn instance theo `serviceId` và `instanceId` hoặc nhãn an toàn được phép.
- Retry attempts, backoff và tổng thời gian operation.
- Active/pending/idle connections, pool lease time, connect/response time.
- CPU, memory, GC, thread pool, event loop và file descriptors.
- Cache hits/age, discovery refresh nếu instrument được.

### Tầng backend

Nên đo:

- RPS và số request đồng thời **từng instance**.
- Latency và error rate của từng instance.
- CPU, heap, DB connection pool, queue depth.
- HTTP active requests, 503/429 và thời gian xử lý downstream.
- Thời điểm instance bắt đầu/hoàn tất graceful shutdown.

Có thể dùng Micrometer/Actuator, distributed tracing, logs có cấu trúc, HTTP client metrics hoặc `LoadBalancerLifecycle` tùy hệ thống. **Tên metric/labels cụ thể phụ thuộc phiên bản và cấu hình**, không nên giả định mọi metric tự xuất hiện sau khi thêm starter.

### Tỷ lệ phân phối có thể đánh lừa

Với hai instance cùng weight và round-robin, một lượng request đủ lớn thường được phân phối tương đối đều **trước khi retry/filter/circuit breaker tác động**. Nhưng không kết luận từ vài chục request đầu, vì:

- Có nhiều caller và mỗi caller có trạng thái round-robin riêng.
- Danh sách ứng viên thay đổi khi health/cache/discovery cập nhật.
- Zone/hint filter có thể loại bớt một instance.
- Backend trả nhanh/chậm khác nhau, làm số request hoàn thành lệch so với số request bắt đầu.
- Retry tạo thêm attempts.
- Sticky session hoặc weighted supplier làm lệch phân phối có chủ đích.

Để đánh giá, đo cả **số lần được chọn** và **số request backend thực sự nhận/hoàn thành**, trên cùng khoảng thời gian và cùng policy version.

## 13. Kiểm thử saturation: pool, thread, timeout và retry

Một hệ thống có thể chọn instance đều nhưng vẫn thất bại do tài nguyên ở HTTP transport.

Ví dụ `RestClient` dùng Apache HttpClient 5:

~~~text
maxConnTotal = 20
maxConnPerRoute = 8
connectionRequestTimeout = 300 ms
responseTimeout = 2 s
2 catalog-service instances
~~~

Nếu hàng trăm request đồng thời dồn vào một route, một số request phải **chờ mượn kết nối** dù LoadBalancer đã chọn được instance. Một số request khác kết nối thành công nhưng backend xử lý chậm và bị **response timeout**.

Đây là ba nguyên nhân khác nhau:

| Quan sát | Nút nghẽn có thể | Bằng chứng cần có |
|---|---|---|
| Pool pending cao, leased chạm max per-route | Giới hạn từng route | Connection manager route stats |
| Total leased chạm max tổng, nhiều route pending | Giới hạn pool tổng | Total pool stats |
| Pool còn chỗ, response timeout tăng | Backend/proxy chậm | Server processing duration, traces |
| Error rate tăng sau khi bật retry | Retry amplification | Attempts theo operation, queue, RPS backend |
| No-instance tăng | Discovery/health/policy | Supplier candidates và lựa chọn LoadBalancer |

Kiểm thử tải có ích khi **đo đồng thời caller, HTTP pool và backend**. Nếu chỉ đo p95 từ load generator, ta biết hệ thống chậm nhưng chưa biết chậm ở giai đoạn nào.

### Bật retry có thể biến một lỗi nhỏ thành bão tải

Giả sử 100 operations/s, mỗi operation thất bại và được thử lại hai lần. Hệ thống có thể tạo tới khoảng 300 attempts/s khi mỗi attempt đi đến backend và không bị giới hạn ở tầng khác. Đây là mô hình minh họa, không phải giới hạn trên chung trong hệ thống có nhiều tầng retry.

Trong load test, cần ghi:

- Số operations và số HTTP attempts thực tế.
- Số retries mỗi operation.
- Tỉ lệ retry cùng instance/instance khác.
- Backoff/jitter và deadline tổng.
- Mức tăng tải của backend khi một instance ngừng phục vụ.

**Không retry mù quáng những thao tác không idempotent** như tạo đơn hoặc thanh toán khi không có cơ chế chống ghi trùng.

## 14. Kiểm thử trong điều kiện một instance bị loại

Tình huống thực tế: có `catalog-a`, `catalog-b`; trong lúc đang tải, instance A bị dừng.

Cần xác định trước sự khác biệt giữa các cơ chế:

1. **Discovery động:** instance có thể bị loại sau một khoảng heartbeat/refresh.
2. **LoadBalancer cache:** dữ liệu cũ có thể tồn tại cho tới khi refresh/TTL.
3. **Health check supplier:** có lịch probe riêng và có thể fallback về toàn bộ nguồn khi không còn healthy.
4. **HTTP transport pool:** có thể còn socket idle tới instance đã dừng.
5. **Retry:** có thể chọn lại same/next instance theo chính sách.
6. **Strict routing:** không được bypass giới hạn region/tenant chỉ để request thành công.

### Bộ bước resilience dưới tải

- Chạy load test ổn định và ghi baseline.
- Dừng instance A trong môi trường test hoặc dùng fault injection.
- Ghi thời điểm A ngừng phục vụ, thời điểm discovery loại A, thời điểm LoadBalancer ngừng chọn A.
- Đo tỉ lệ lỗi, latency tail, số retry và load trên B trong giai đoạn chuyển tiếp.
- Khởi động lại A, đo thời gian trở lại danh sách và khả năng phục hồi.
- Kiểm tra hệ thống không tạo retry storm, không làm cạn pool và không gọi instance bị cấm theo policy.

**Đừng khẳng định dừng một server trong `SimpleDiscoveryClient` tĩnh sẽ làm danh sách instance tự cập nhật**. Với test discovery lifecycle, phải dùng nguồn có thể thay đổi hoặc registry động, không chỉ tắt port.

## 15. Ma trận: nên đặt test nào ở đâu?

| Trường hợp cần chứng minh | Unit | Integration | Load |
|---|:---:|:---:|:---:|
| Filter theo region đúng với list mẫu | **Chính** | Khói/khẳng định bean được gắn | Không cần |
| Soft zone fallback khi không match | **Chính** | Có thể kiểm tra URI thực | Chỉ khi muốn đo cross-zone traffic |
| Empty instance list → no-server | **Chính** | **Bắt buộc** để xem adapter/client biểu diễn lỗi | Theo dõi error spike nếu discovery outage |
| `@LoadBalanced RestClient.Builder` thực sự được gắn | Không | **Chính** | Chỉ đo sau khi wiring đã PASS |
| `@FeignClient` được scan và decoder dùng đúng | Không | **Chính** | Tùy tải/giao tiếp |
| Connect/read timeout cấu hình đúng | Có thể test logic settings | **Chính** với fake slow backend | **Chính** khi backend chậm dưới tải |
| Retry không vượt attempt limit | **Chính** | **Chính** với fake errors | **Chính** để đo amplification |
| Pool sizing và queue dưới đồng thời cao | Không đủ | Test biên nhỏ | **Chính** |
| Round-robin phân phối tương đối đều dưới tải | Có thể xác minh thuật toán | Một số request để xác nhận đa instance | **Chính** khi kiểm tra workload thực |
| Weighted 3:1 | Kiểm tra weight policy | Chọn đúng candidate | **Chính** cho tỉ lệ dưới tải |
| Instance bị dừng/khởi động lại | Unit cho empty/fallback | **Chính** cho HTTP/failover | **Chính** cho recovery SLO |
| Không lộ token trong logs | Unit cho log formatter | **Chính** với canary | Kiểm tra log capture dưới tải nếu cần |
| Contract JSON/status lỗi | Unit DTO validation | **Chính** | Thứ cấp, không thay contract test |
| p95/p99, throughput và CPU | Không | Không đủ | **Chính** |

“Chính” là tầng có bằng chứng mạnh nhất. Một requirement quan trọng thường có **một nhóm unit tests đầy đủ** cộng **một vài integration tests đại diện**, chứ không phải lặp lại toàn bộ cartesian product ở mọi tầng.

## 16. Cách giảm flaky tests trong CI

Test LoadBalancer rất dễ không ổn định nếu vô tình phụ thuộc vào timing và tài nguyên chung.

### Unit tests

- Dùng candidate list bất biến, tránh state chung với test khác.
- Không kiểm tra thứ tự lựa chọn ban đầu của round-robin nếu trạng thái không được reset/seed.
- Với random/weighted, dùng test bất biến hoặc dải chấp nhận có đủ mẫu; tránh so tỷ lệ trên 5 request.
- Không phụ thuộc đồng hồ hệ thống trừ khi có clock/scheduler test-controlled.

### Integration tests

- Dùng ephemeral ports, không dùng fixed port dễ xung đột.
- Dùng `@DynamicPropertySource` hoặc cấu hình test phù hợp, không hardcode URI không truy cập được.
- Đảm bảo server khởi động trước khi Spring giải quyết properties.
- Đóng server, request factory và connection pool sau test; tránh thread leak.
- Kiểm soát caching, health scheduler, retries và context cache.
- Hạn chế `Thread.sleep` để chờ discovery/health updates; ưu tiên poll có timeout rõ và điều kiện kiểm tra.
- Với reactive code, dùng `StepVerifier` và virtual time khi kiểm tra logic thời gian có thể virtualize; network thật vẫn phụ thuộc thời gian thực.
- Không chia sẻ random ports/context cache khi test class khác có cùng configuration nhưng server đã dừng.

### Kiểm thử tải

- Bảo đảm load generator không phải nút nghẽn đầu tiên.
- Không chạy song song nhiều bài benchmark trên cùng worker CI có tài nguyên giới hạn mà không kiểm soát.
- Warm up JIT, connection pools và caches trước khi lấy số đo chính thức nếu bài test yêu cầu.
- Giữ cùng cấu hình server/client, dataset, số instance và version khi so sánh trước/sau.
- Đo ít nhất vài lần để phân biệt nhiễu hạ tầng với regression.
- Không coi một lần benchmark ngắn là chứng cứ chính xác cho p99 ở traffic ít.
- Dùng test environment được cô lập; không gây tải phá hoại tới production hoặc hệ thống dùng chung.

## 17. Tổ chức pipeline CI/CD theo chi phí và mức độ rủi ro

Có thể tổ chức:

~~~mermaid
flowchart TD
    A["Developer push / pull request"]
    B["Unit tests<br/>policy, supplier, selector"]
    C{"PASS?"}
    D["Integration tests<br/>Boot context + fake HTTP servers"]
    E{"PASS?"}
    F["Build artifact / candidate"]
    G["Load baseline + regression test<br/>môi trường riêng"]
    H{"SLO & policy PASS?"}
    I["Cho phép phát hành theo quy trình"]
    X["Dừng pipeline và báo lỗi"]
    A --> B --> C
    C -->|"Không"| X
    C -->|"Có"| D --> E
    E -->|"Không"| X
    E -->|"Có"| F --> G --> H
    H -->|"Không"| X
    H -->|"Có"| I
~~~

Không phải tổ chức nào cũng chạy **full load test** trên mỗi pull request. Có thể dùng:

- **Mỗi commit/PR:** unit suite + nhóm integration trọng yếu, fail nhanh.
- **Trước khi merge/release:** integration đầy đủ, hợp đồng HTTP, smoke performance nhỏ.
- **Trước release lớn hoặc theo lịch:** load/stress/soak/failure tests trên môi trường gần production.
- **Sau phát hành:** canary metrics, alert và khả năng rollback nhanh nếu phân phối/lỗi/latency lệch dự kiến.

Cần lưu cấu hình test cùng version ứng dụng để có thể giải thích một regression: dependency Spring Cloud, HTTP transport, cache TTL, retry policy, server capacity và dữ liệu discovery đều có thể tác động kết quả.

## 18. Checklist nghiệm thu và điều không được suy luận

Trước khi coi chức năng cân bằng tải đã được kiểm thử đủ, cần trả lời:

1. **Unit:** mọi policy quan trọng có test cho list rỗng, metadata thiếu, fallback và phần tử bị cấm không?
2. **Unit:** custom selector có test không bao giờ chọn ngoài tập ứng viên không?
3. **Integration:** đã kiểm chứng bean `@LoadBalanced` thật và service ID được resolve qua LoadBalancer thay vì DNS?
4. **Integration:** đã gọi ít nhất hai backend thử nghiệm và xác nhận instance ID trả về chưa?
5. **Integration:** response 4xx/5xx, empty discovery, timeout và lỗi decode có được phân loại đúng?
6. **Integration:** retry/health/cache đã có test mô phỏng đúng vòng đời và tính thời gian chưa?
7. **Load:** traffic được phát **tới caller**, không bypass LoadBalancer?
8. **Load:** có đo cả caller lẫn mỗi instance, pool, CPU, latency tail và attempts?
9. **Load:** có SLO/ngưỡng chấp nhận và điều kiện abort rõ ràng?
10. **Load:** đã kiểm thử một instance chậm hoặc bị dừng dưới tải chưa?
11. **Isolation:** các test có dùng cổng riêng, dữ liệu giả và không sửa môi trường chung?
12. **Observability:** trace/metrics/log đủ để giải thích một lỗi mà không ghi token, cookie hay dữ liệu nhạy cảm?
13. **CI/CD:** test nhanh chạy thường xuyên, test nặng chạy theo risk/cadence phù hợp?
14. **Reporting:** có lưu kết quả kèm phiên bản/config và ghi rõ những gì chưa được chứng minh?

**Kết luận:** Hãy dùng **unit test** để chứng minh tính đúng đắn của policy, supplier và selector; **integration test** để chứng minh Spring Cloud LoadBalancer thực sự được gắn vào `RestClient`, `WebClient` hoặc OpenFeign và HTTP request tới đúng `ServiceInstance`; cuối cùng dùng **kiểm thử tải** để đánh giá phân phối, p95/p99, pool saturation, retry amplification và khả năng phục hồi. Ba tầng kiểm thử bổ sung nhau: **đúng logic không đồng nghĩa đúng wiring; đúng wiring không đồng nghĩa chịu tải tốt**.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – Dynamic Property Sources trong integration tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework – TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Grafana k6 – Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)

