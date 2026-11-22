# Kiểm thử nhiều instance với SimpleDiscoveryClient

Khi kiểm thử service discovery, không phải lúc nào cũng cần dựng Eureka, Consul hoặc một registry bên ngoài. Spring Cloud Commons có SimpleDiscoveryClient, một DiscoveryClient đọc danh sách service instance từ cấu hình. Ta có thể khai báo nhiều endpoint cho cùng một service ID, sau đó kiểm tra discovery trả đúng danh sách và Spring Cloud LoadBalancer chọn một endpoint hợp lệ.

Cách này phù hợp với unit/integration test cần mô phỏng nhiều replica, kiểm tra URI, port, metadata, lựa chọn instance và định tuyến HTTP. Nó cũng giúp kiểm tra logic client-side load balancing mà không phụ thuộc registry server, network deployment hoặc thời gian hội tụ của registry.

Bài học thuộc chương **Kiểm thử** của module **SPRING_CLOUD_CORE**. Nội dung đi từ cấu hình SimpleDiscoveryClient, kiểm tra DiscoveryClient trực tiếp, kiểm tra LoadBalancer chọn nhiều instance, đến HTTP integration test với hai server giả và health-check supplier.

## 1. SimpleDiscoveryClient dùng để làm gì?

SimpleDiscoveryClient là một implementation của DiscoveryClient. Nó lấy thông tin service và instance từ các property có tiền tố:

~~~text
spring.cloud.discovery.client.simple.instances
~~~

Ví dụ một service có hai instance:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082
~~~

Trong đó:
- catalog-service là service ID mà consumer dùng trong URI logic.
- [0] và [1] là index của các instance trong danh sách, bắt đầu từ 0.
- uri là địa chỉ thực tế của từng instance.
- Mỗi URI có thể chứa scheme, hostname/IP và port riêng.

Khi ứng dụng gọi DiscoveryClient.getInstances("catalog-service"), SimpleDiscoveryClient trả về hai ServiceInstance tương ứng với hai URI đã cấu hình.

### 1.1. SimpleDiscoveryClient được dùng trong trường hợp nào?

Spring Cloud Commons sử dụng SimpleDiscoveryClient nếu classpath không có DiscoveryClient gắn với service registry như Eureka, Consul hoặc Zookeeper.

Điều này có nghĩa:
- Chỉ thêm spring-cloud-starter-loadbalancer không tự dựng registry server.
- Nếu test classpath có Eureka/Consul discovery client, SimpleDiscoveryClient có thể không phải implementation được chọn làm DiscoveryClient mặc định.
- Nếu mục tiêu là kiểm thử SimpleDiscoveryClient, nên dùng test slice/context chỉ có Spring Cloud Commons và LoadBalancer, không kéo thêm registry client không cần thiết.
- Nếu muốn kiểm thử behavior của Eureka/Consul, hãy viết integration test riêng với registry implementation đó.

Trong Spring Cloud hiện đại, @EnableDiscoveryClient không còn bắt buộc chỉ để bật discovery; đưa implementation phù hợp vào classpath sẽ kích hoạt auto-configuration tương ứng.

### 1.2. SimpleDiscoveryClient không phải registry động

SimpleDiscoveryClient đọc danh sách từ cấu hình. Nó không tự cung cấp các chức năng như:
- Đăng ký và hủy đăng ký instance với server registry.
- Heartbeat hoặc lease để phát hiện process chết.
- Đồng bộ trạng thái giữa nhiều client.
- Tự phát hiện Pod/container mới.
- Cập nhật danh sách từ một hệ thống quản trị bên ngoài.

Vì vậy, nó phù hợp để mô phỏng danh sách instance đã biết trong test hoặc môi trường đơn giản. Nó không chứng minh rằng một registry thật hoạt động đúng trong production.

## 2. Khai báo nhiều instance trong application.yml

Có thể khai báo danh sách bằng YAML:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: test-a
                  version: v1
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: test-b
                  version: v1
~~~

Cấu hình trên tạo hai ServiceInstance cho catalog-service. Mỗi instance có URI và metadata riêng.

Nếu dùng application.properties:

~~~properties
spring.application.name=order-service
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=test-a
spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.version=v1
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082
spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=test-b
spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.version=v1
~~~

### 2.1. Service ID và URI là hai giá trị khác nhau

Consumer gửi request tới service ID:

~~~text
http://catalog-service/api/products
~~~

Danh sách instance ánh xạ service ID đó tới các URI thực:

~~~text
catalog-service
  ├── http://127.0.0.1:8081
  └── http://127.0.0.1:8082
~~~

Không dùng hostname logic catalog-service làm địa chỉ cố định của một instance trong SimpleDiscoveryClient. LoadBalancer nhận service ID, lấy danh sách ServiceInstance rồi chọn một URI thực tế.

### 2.2. URI quyết định host, port và secure flag

Một URI HTTP:

~~~text
http://127.0.0.1:8081
~~~

Một URI HTTPS:

~~~text
https://catalog-b.internal:8443
~~~

Thông tin host, port và secure được suy ra từ URI. Khi kiểm thử HTTPS, ngoài việc xác nhận secure flag, cần cấu hình trust material phù hợp cho HTTP client; SimpleDiscoveryClient không tự tạo chứng thư hoặc bỏ qua TLS validation.

### 2.3. Index danh sách bắt đầu từ 0

Các property có dạng:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082
spring.cloud.discovery.client.simple.instances.catalog-service[2].uri=http://127.0.0.1:8083
~~~

Index 0 là phần tử đầu tiên. Hãy giữ index liên tục để cấu hình dễ đọc và tránh nhầm lẫn khi sửa danh sách. Trong test, nên xác nhận cả số lượng và URI của từng instance.

## 3. Thêm dependency cần thiết

Để kiểm thử discovery và lựa chọn instance, dự án cần Spring Cloud Commons và Spring Cloud LoadBalancer. Dependency thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Dùng Spring Cloud BOM tương thích với Spring Boot để quản lý phiên bản starter. Không pin tùy tiện một phiên bản LoadBalancer khác release train của các module Spring Cloud còn lại.

Nếu kiểm thử request HTTP qua server giả, có thể bổ sung MockWebServer ở test scope:

~~~xml
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hãy chọn phiên bản MockWebServer tương thích với dependency OkHttp mà dự án quản lý. Nếu dependency management không cung cấp version, khai báo version test rõ ràng.

Không cần thêm Eureka Server hoặc Consul chỉ để kiểm thử SimpleDiscoveryClient.

## 4. Kiểm thử DiscoveryClient trả về nhiều instance

Bước đầu tiên là kiểm tra cấu hình được bind và DiscoveryClient trả về đúng danh sách. Đây là test tập trung vào discovery, chưa kiểm tra LoadBalancer hoặc HTTP request.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest(
        classes = SimpleDiscoveryClientTests.TestApplication.class,
        properties = {
                "spring.application.name=order-service",
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081",
                "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082"
        }
)
class SimpleDiscoveryClientTests {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void returnsBothConfiguredInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        assertThat(instances).hasSize(2);
        assertThat(instances)
                .extracting(ServiceInstance::getUri)
                .containsExactly(
                        URI.create("http://127.0.0.1:8081"),
                        URI.create("http://127.0.0.1:8082")
                );
    }

    @Test
    void returnsEmptyListForUnknownService() {
        assertThat(discoveryClient.getInstances("unknown-service"))
                .isEmpty();
    }

    @Test
    void exposesConfiguredServiceId() {
        assertThat(discoveryClient.getServices())
                .contains("catalog-service");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
~~~

Test này kiểm tra:
- Hai property instance được bind thành hai ServiceInstance.
- Thứ tự danh sách theo cấu hình được giữ lại.
- Service ID được công bố trong danh sách service.
- Service không tồn tại trả về danh sách rỗng.

### 4.1. Vì sao dùng DiscoveryClient thay vì gọi trực tiếp SimpleDiscoveryClient?

DiscoveryClient là abstraction mà consumer của ứng dụng sử dụng. Kiểm thử qua abstraction giúp xác nhận wiring của Spring context và behavior mà code nghiệp vụ thực sự nhìn thấy.

Nếu mục tiêu là kiểm tra riêng mapping property của SimpleDiscoveryClient, có thể inject SimpleDiscoveryProperties hoặc SimpleDiscoveryClient trong test chuyên biệt. Tuy nhiên, test qua DiscoveryClient phù hợp hơn để xác nhận tích hợp ở cấp ứng dụng.

### 4.2. Kiểm tra metadata

Nếu ứng dụng dùng metadata để lọc zone hoặc version, cần xác nhận metadata được bind đúng:

~~~java
@Test
void bindsMetadataForEachInstance() {
    List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

    assertThat(instances).hasSize(2);
    assertThat(instances.get(0).getMetadata())
            .containsEntry("zone", "test-a")
            .containsEntry("version", "v1");
    assertThat(instances.get(1).getMetadata())
            .containsEntry("zone", "test-b")
            .containsEntry("version", "v1");
}
~~~

Metadata là dữ liệu để các supplier hoặc custom LoadBalancer áp dụng chính sách lọc. Chỉ khai báo metadata không tự động kích hoạt zone/version routing; phải cấu hình supplier tương ứng nếu muốn lọc instance theo các trường này.

## 5. Kiểm thử LoadBalancer chọn instance từ danh sách

DiscoveryClient chỉ trả về danh sách. Spring Cloud LoadBalancer mới quyết định chọn instance nào cho từng request.

LoadBalancer dùng ServiceInstanceListSupplier để lấy danh sách instance. Cấu hình mặc định sử dụng RoundRobinLoadBalancer; cũng có thể thay bằng RandomLoadBalancer hoặc custom implementation.

Với blocking API, có thể dùng LoadBalancerClient:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest(
        classes = LoadBalancerSelectionTests.TestApplication.class,
        properties = {
                "spring.application.name=order-service",
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081",
                "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082",
                "spring.cloud.loadbalancer.cache.enabled=false"
        }
)
class LoadBalancerSelectionTests {

    @Autowired
    DiscoveryClient discoveryClient;

    @Autowired
    LoadBalancerClient loadBalancerClient;

    @Test
    void selectsOnlyFromConfiguredInstances() {
        List<URI> configuredUris = discoveryClient
                .getInstances("catalog-service")
                .stream()
                .map(ServiceInstance::getUri)
                .toList();

        for (int attempt = 0; attempt < 6; attempt++) {
            ServiceInstance selected =
                    loadBalancerClient.choose("catalog-service");

            assertThat(selected).isNotNull();
            assertThat(configuredUris).contains(selected.getUri());
        }
    }

    @Test
    void returnsNoInstanceForUnknownService() {
        assertThat(loadBalancerClient.choose("missing-service"))
                .isNull();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
~~~

Test này xác nhận LoadBalancer chỉ chọn trong danh sách được SimpleDiscoveryClient cung cấp. Nó không khẳng định chính xác thứ tự chọn instance; nhờ vậy test không phụ thuộc thứ tự khởi tạo child context hoặc một thuật toán tùy chỉnh khác được bật trong môi trường test.

### 5.1. Kiểm thử round-robin có chủ đích

Nếu muốn xác minh thuật toán round-robin, hãy cố định cấu hình test dùng RoundRobinLoadBalancer và gửi nhiều lần chọn instance. Với hai instance và thuật toán mặc định, các lần chọn liên tiếp sẽ luân phiên giữa hai phần tử.

Không nên viết test round-robin rồi chạy nó trong context mà ứng dụng có thể override bằng RandomLoadBalancer hoặc custom policy. Khi đó, assertion về chuỗi lựa chọn cụ thể không còn đúng.

Một test ở cấp ứng dụng thường chỉ cần xác nhận:
- Kết quả không null khi danh sách có instance.
- URI được chọn thuộc danh sách cấu hình.
- Request được định tuyến tới endpoint hợp lệ.
- Service không có instance không tạo ra một địa chỉ giả.

Nếu nghiệp vụ cần đảm bảo phân phối đều, hãy kiểm thử thuật toán riêng và cố định policy trong test đó.

### 5.2. Tắt cache trong test

Spring Cloud LoadBalancer có cache danh sách instance. Cấu hình mặc định hiện hành có TTL 35 giây. Cache hữu ích cho production nhưng có thể làm test khó dự đoán nếu test thay đổi nguồn instance hoặc kỳ vọng thấy thay đổi ngay.

Trong test cần đọc danh sách trực tiếp, có thể đặt:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Hoặc property tương đương:

~~~properties
spring.cloud.loadbalancer.cache.enabled=false
~~~

Tắt cache không phải khuyến nghị production chung. Trong production, cache giúp giảm chi phí gọi discovery; nếu DiscoveryClient đã tự cache, cần tránh cache hai lớp không cần thiết.

## 6. Kiểm thử HTTP request qua hai instance giả

Kiểm tra DiscoveryClient và LoadBalancerClient mới xác nhận danh sách và lựa chọn. Để chứng minh HTTP client thật sự chuyển request tới nhiều endpoint, hãy dựng hai HTTP server giả trên port động.

MockWebServer là một lựa chọn gọn cho integration test:
- Server A trả nội dung node-a.
- Server B trả nội dung node-b.
- SimpleDiscoveryClient nhận URI của hai server qua DynamicPropertySource.
- RestTemplate có @LoadBalanced gọi service ID catalog-service.
- Test gửi nhiều request và xác nhận cả hai server đều nhận request.

Ví dụ cấu hình ứng dụng test:

~~~java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestTemplate;

@SpringBootConfiguration
@EnableAutoConfiguration
class LoadBalancedTestApplication {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Ví dụ integration test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestTemplate;

@SpringBootTest(
        classes = LoadBalancedTestApplication.class,
        properties = {
                "spring.application.name=order-service",
                "spring.cloud.loadbalancer.cache.enabled=false",
                "spring.cloud.loadbalancer.retry.enabled=false"
        }
)
class SimpleDiscoveryHttpIntegrationTests {

    static final MockWebServer NODE_A = new MockWebServer();
    static final MockWebServer NODE_B = new MockWebServer();

    static {
        try {
            NODE_A.start();
            NODE_B.start();
            NODE_A.setDispatcher(dispatcherFor("node-a"));
            NODE_B.setDispatcher(dispatcherFor("node-b"));
        }
        catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @Autowired
    @LoadBalanced
    RestTemplate restTemplate;

    @DynamicPropertySource
    static void registerInstances(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
                () -> NODE_A.url("/").toString()
        );
        registry.add(
                "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
                () -> NODE_B.url("/").toString()
        );
    }

    @Test
    void routesRequestsToBothConfiguredInstances() {
        List<String> responses = IntStream.range(0, 6)
                .mapToObj(index -> restTemplate.getForObject(
                        "http://catalog-service/node",
                        String.class
                ))
                .toList();

        Set<String> distinctResponses = responses.stream()
                .collect(Collectors.toSet());

        assertThat(distinctResponses)
                .containsExactlyInAnyOrder("node-a", "node-b");
        assertThat(NODE_A.getRequestCount()).isPositive();
        assertThat(NODE_B.getRequestCount()).isPositive();
    }

    @AfterAll
    static void stopServers() throws IOException {
        NODE_A.shutdown();
        NODE_B.shutdown();
    }

    private static Dispatcher dispatcherFor(String nodeName) {
        return new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setResponseCode(200)
                        .addHeader("Content-Type", "text/plain")
                        .setBody(nodeName);
            }
        };
    }
}
~~~

Ví dụ này giả định LoadBalancer dùng RoundRobinLoadBalancer mặc định và không có custom policy ghi đè. Nếu dự án dùng thuật toán khác, hãy thay assertion phân phối bằng assertion phù hợp với policy đã cấu hình.

### 6.1. Vì sao dùng port động?

Không nên cố định 8081 và 8082 cho MockWebServer trong test:
- CI có thể chạy nhiều test suite cùng lúc.
- Port có thể đã bị process khác sử dụng.
- Test có thể chạy trên máy developer với topology khác.
- Port động giảm lỗi xung đột môi trường.

DynamicPropertySource đăng ký URI sau khi test server đã mở port. SimpleDiscoveryClient nhận các địa chỉ thực tế này khi ApplicationContext được tạo.

### 6.2. Test HTTP khác với test lựa chọn instance

| Test | Điều chứng minh |
| --- | --- |
| DiscoveryClient test | Properties ánh xạ thành danh sách ServiceInstance |
| LoadBalancerClient test | Thuật toán chọn một instance trong danh sách |
| HTTP integration test | Client thay service ID bằng URI instance và request đến server thật |
| Health-check test | Supplier loại hoặc giữ instance theo kết quả health probe |
| Registry integration test | Hành vi với registry server thật, nếu ứng dụng dùng registry |

Không thay một loại test bằng loại khác. Một test DiscoveryClient thành công không chứng minh request HTTP đi tới endpoint; một HTTP test thành công cũng chưa chứng minh health-check hoặc registry lifecycle.

## 7. Kiểm thử health check với SimpleDiscoveryClient

SimpleDiscoveryClient đọc danh sách tĩnh từ properties. Nó không tự kiểm tra endpoint còn sống hay không. Nếu một instance ngừng phản hồi nhưng vẫn còn trong cấu hình, danh sách discovery vẫn có thể chứa instance đó.

Spring Cloud LoadBalancer cung cấp HealthCheckServiceInstanceListSupplier để kiểm tra các instance theo chu kỳ. Cơ chế này đặc biệt hữu ích khi dùng SimpleDiscoveryClient.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: health-check
      health-check:
        initial-delay: 1s
        interval: 5s
        path:
          catalog-service: /actuator/health
~~~

Health check mặc định sử dụng /actuator/health nếu không cấu hình path khác. Nếu dùng endpoint này, các server giả cần cung cấp endpoint tương ứng và test cần chờ scheduler hoàn tất ít nhất một chu kỳ trước khi assert danh sách khỏe.

### 7.1. Health check cần endpoint thật

Nếu instance A trả 200 cho /actuator/health còn instance B trả 503, supplier có thể chỉ cung cấp instance A trong danh sách healthy khi kết quả kiểm tra đã được cập nhật.

Trong test:
- Khởi động hai server giả.
- Cấu hình mỗi server trả health status khác nhau.
- Bật health-check supplier.
- Chờ lần kiểm tra đầu tiên hoàn tất.
- Đọc danh sách instance từ supplier hoặc gọi LoadBalancer.
- Xác nhận request được chọn theo danh sách healthy.

Không dùng sleep cố định quá dài nếu có thể quan sát điều kiện hoàn tất hoặc cấu hình scheduler phù hợp. Nếu phải chờ, dùng Awaitility hoặc polling có timeout thay vì một khoảng đợi tùy ý.

### 7.2. Health-check không phải registry heartbeat

HealthCheckServiceInstanceListSupplier gửi probe từ phía client tới các URI đã cấu hình. Nó không đăng ký heartbeat lên Eureka/Consul và không cập nhật trạng thái trong một registry server.

Vì SimpleDiscoveryClient không có registry server, health check là một lớp bổ sung để LoadBalancer tránh gọi endpoint không khỏe. Các service registry thật thường đã cung cấp trạng thái health của instance và có thể không cần thêm probe trùng lặp.

### 7.3. Cấu hình refetch instances

Nếu danh sách instance phía delegate có thể thay đổi nhưng không phát ra luồng cập nhật, có thể bật:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 10s
        repeat-health-check: false
~~~

refetch-instances yêu cầu supplier tải lại danh sách theo chu kỳ. Nó không tự biến file application.yml thành nguồn registry động; SimpleDiscoveryClient vẫn đọc từ Environment và property đã bind.

Nếu muốn thay đổi instance list trong runtime, cần cập nhật nguồn cấu hình và cơ chế refresh phù hợp, hoặc dùng một DiscoveryClient/registry implementation hỗ trợ cập nhật instance thực sự.

### 7.4. Xử lý khi mọi instance đều unhealthy

Không viết test dựa vào giả định rằng khi mọi health check đều thất bại thì supplier luôn trả danh sách rỗng. Hành vi fallback có thể khác theo implementation/version; tài liệu phiên bản hiện hành mô tả supplier có thể trả lại danh sách đã lấy khi không có instance healthy.

Hãy kiểm tra đúng phiên bản Spring Cloud BOM đang chạy và xác định chính sách fail-open/fail-closed mà ứng dụng yêu cầu. Nếu yêu cầu an toàn là không gửi traffic khi không có instance healthy, hãy kiểm thử rõ điều kiện đó và cấu hình/customize supplier tương ứng.

## 8. Kiểm thử metadata và lọc instance

SimpleDiscoveryClient hỗ trợ metadata trên từng instance. Metadata có thể được dùng để mô phỏng zone, version, capability hoặc nhóm triển khai.

Ví dụ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-b
                  version: v2
~~~

Nếu LoadBalancer được cấu hình ZonePreferenceServiceInstanceListSupplier, nó có thể ưu tiên instance cùng zone. Với SimpleDiscoveryClient, zone có thể được cung cấp qua metadata và cấu hình spring.cloud.loadbalancer.zone.

### 8.1. Test metadata không đồng nghĩa test filtering

Đầu tiên xác nhận metadata được bind đúng:

~~~java
assertThat(instances.get(0).getMetadata())
        .containsEntry("zone", "zone-a");
~~~

Sau đó mới kiểm thử supplier hoặc LoadBalancer:
- Khi client zone là zone-a, instance zone-a được ưu tiên.
- Nếu không có instance cùng zone, chính sách fallback được xác minh theo supplier.
- Nếu metadata bị thiếu, behavior phải được kiểm tra rõ.

Chỉ khai báo metadata trong YAML không làm LoadBalancer tự động lọc. Phải cấu hình supplier phù hợp hoặc viết custom filtering policy.

### 8.2. Kiểm thử version-aware selection

Nếu ứng dụng lọc instance theo API version, hãy khai báo metadata version trên mỗi instance và cấu hình API version supplier tương ứng. Test nên bao gồm:
- Có instance khớp version.
- Không có instance khớp version.
- Có bật hoặc tắt fallback-to-available-instances.
- Request thiếu version khi policy yêu cầu version.
- Consumer nhận đúng endpoint theo policy.

Không gộp test API version với test SimpleDiscoveryClient cơ bản; hãy giữ test nền tảng chỉ xác minh list/selection trước, sau đó mở rộng sang filter.

## 9. Kiểm thử nhiều service ID

Một SimpleDiscoveryClient có thể chứa nhiều service:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
            inventory-service:
              - uri: http://127.0.0.1:8091
              - uri: http://127.0.0.1:8092
              - uri: http://127.0.0.1:8093
~~~

Mỗi service ID có danh sách instance độc lập. LoadBalancer cũng tạo context riêng theo service ID và khởi tạo context đó một cách lazy khi lần đầu có request cần load balancing.

Test nên xác nhận:
- catalog-service có đúng hai instance.
- inventory-service có đúng ba instance.
- Chọn catalog-service không trả URI thuộc inventory-service.
- Service ID không tồn tại không có instance.
- Metadata của các service không bị trộn lẫn.

Nếu cần khởi tạo sẵn LoadBalancer child context cho một số service, có thể dùng spring.cloud.loadbalancer.eager-load.clients. Trong test đơn giản, không cần bật eager load trừ khi đang kiểm thử startup hoặc cấu hình child context.

## 10. Cache và tính ổn định của test

Spring Cloud LoadBalancer có caching implementation. Starter LoadBalancer cung cấp cache mặc định; nếu Caffeine có trên classpath thì cache Caffeine có thể được sử dụng.

Các thuộc tính thường gặp:

| Property | Mục đích |
| --- | --- |
| spring.cloud.loadbalancer.cache.enabled | Bật/tắt LoadBalancer cache |
| spring.cloud.loadbalancer.cache.ttl | Thời gian sống của cache entry |
| spring.cloud.loadbalancer.cache.capacity | Dung lượng khởi tạo của cache |
| spring.cloud.loadbalancer.health-check.refetch-instances | Yêu cầu health-check supplier tải lại danh sách instance |
| spring.cloud.loadbalancer.health-check.refetch-instances-interval | Chu kỳ refetch danh sách |

Tình huống nên tắt cache trong test:
- Test thay đổi property source giữa các lần gọi.
- Test muốn xác nhận ngay danh sách mới sau khi cấu hình được áp dụng.
- Test đang cô lập behavior của DiscoveryClient và không muốn thêm một lớp cache.

Tình huống nên giữ cache trong test:
- Test chính sách cache/TTL.
- Test behavior khi instance list thay đổi nhưng cache chưa hết hạn.
- Test hiệu năng hoặc số lần gọi DiscoveryClient.
- Test cache eviction.

Không nên tắt cache ở mọi test một cách máy móc. Hãy chọn theo behavior đang kiểm tra.

## 11. Kiểm thử retry và lỗi instance

Khi một instance trả lỗi hoặc ngắt kết nối, retry có thể làm test khó hiểu vì một request logic có thể phát sinh nhiều lần chọn instance.

Trong test kiểm tra định tuyến cơ bản, nên tắt retry để kết quả phản ánh một lần gọi:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
~~~

Khi kiểm thử retry, bật retry có chủ đích và xác định:
- Có retry trên cùng instance hay instance tiếp theo.
- Loại exception/status code nào kích hoạt retry.
- HTTP method nào được phép retry.
- Số lần retry tối đa.
- Có tránh instance vừa thất bại không.
- Kết quả cuối cùng khi tất cả instance đều lỗi.

Không dùng POST có side effect để thử retry nếu server giả không có idempotency key hoặc cơ chế chống thực hiện lặp. Với test cơ bản, GET tới endpoint trả tên node là đủ.

## 12. Phân biệt test SimpleDiscoveryClient và test registry thật

| Mục tiêu | SimpleDiscoveryClient | Registry thật |
| --- | --- | --- |
| Kiểm tra property mapping | Phù hợp | Không cần thiết |
| Kiểm tra nhiều endpoint tĩnh | Phù hợp | Có thể dùng nhưng nặng hơn |
| Kiểm tra LoadBalancer chọn instance | Phù hợp | Phù hợp |
| Kiểm tra HTTP routing tới instance | Phù hợp với server giả | Phù hợp |
| Kiểm tra đăng ký/heartbeat/deregister | Không hỗ trợ | Cần registry thật |
| Kiểm tra lease, TTL và health state registry | Không hỗ trợ | Cần registry thật |
| Kiểm tra discovery cập nhật khi instance xuất hiện/mất đi | Không tự động | Cần registry thật |
| Kiểm tra network và auth của registry | Không hỗ trợ | Cần registry thật |

SimpleDiscoveryClient giúp test nhanh và cô lập logic consumer. Khi hệ thống phụ thuộc vào behavior riêng của Eureka/Consul/Zookeeper, vẫn cần integration test với implementation tương ứng.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| DiscoveryClient trả danh sách rỗng | Sai service ID hoặc property prefix | Kiểm tra tên service và simple.instances |
| Chỉ có một instance | Index bị thiếu hoặc cấu hình sai key | Kiểm tra các index từ 0 và list binding |
| SimpleDiscoveryClient không được dùng | Có registry-backed DiscoveryClient trên classpath | Tách test classpath hoặc dùng implementation mong muốn rõ ràng |
| LoadBalancer không chọn được instance | Thiếu starter hoặc LoadBalancer bị disable | Thêm starter và kiểm tra spring.cloud.loadbalancer.enabled |
| Gọi http://catalog-service bị DNS error | Client không được đánh dấu load-balanced | Dùng @LoadBalanced bean/client và URI service ID |
| Test chọn instance lúc được lúc không | Dùng RandomLoadBalancer hoặc policy custom | Assert tập URI hợp lệ hoặc cố định thuật toán trong test |
| Test không thấy property vừa đổi | LoadBalancer cache còn hiệu lực | Tắt cache trong test hoặc chờ TTL/evict đúng cách |
| Instance chết vẫn được chọn | SimpleDiscoveryClient không có health check mặc định | Bật HealthCheckServiceInstanceListSupplier |
| Health check luôn fail | Server giả không expose health path hoặc port sai | Cấu hình path/port và kiểm tra endpoint |
| Không có traffic tới một node trong HTTP test | Thuật toán không phải round-robin hoặc retry/cache thay đổi kết quả | Kiểm tra policy, request count và test setup |
| Test lỗi do port đã dùng | Hard-code port trong nhiều test process | Dùng MockWebServer hoặc port động |
| Metadata có nhưng không lọc | Chưa cấu hình supplier tương ứng | Bật zone/version/hint supplier và kiểm thử policy |
| Danh sách không đổi sau khi sửa YAML | SimpleDiscoveryClient không tự refresh file config | Tạo context mới hoặc dùng nguồn discovery động |

## 14. Quy trình viết test từ đơn giản đến tích hợp

Một trình tự hiệu quả:

1. Khai báo ít nhất hai instance cho một service ID.
2. Test DiscoveryClient trả đúng số lượng, URI và metadata.
3. Test service ID không tồn tại trả danh sách rỗng.
4. Thêm Spring Cloud LoadBalancer starter.
5. Test LoadBalancer chọn một instance thuộc danh sách.
6. Nếu cần, cố định RoundRobinLoadBalancer để test phân phối.
7. Dựng hai HTTP server giả trên port động.
8. Gửi request qua client có @LoadBalanced và xác nhận cả hai server nhận request.
9. Bật health-check supplier và mô phỏng một node unhealthy.
10. Test cache, retry, metadata filter hoặc API version trong các test riêng.
11. Dùng registry thật cho behavior mà SimpleDiscoveryClient không mô phỏng được.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Khai báo 2+ URI cho service ID"] --> B["Test SimpleDiscoveryClient"]
    B --> C["Test DiscoveryClient.getInstances"]
    C --> D["Test LoadBalancerClient.choose"]
    D --> E["Test HTTP qua 2 server giả"]
    E --> F["Test health-check supplier"]
    F --> G["Test cache/retry/filter riêng"]
    G --> H["Integration test với registry thật nếu cần"]
~~~

## 15. Checklist review

- [ ] Test classpath không vô tình có registry-backed DiscoveryClient nếu mục tiêu là SimpleDiscoveryClient.
- [ ] Có ít nhất hai instance cho cùng một service ID.
- [ ] Property index bắt đầu từ 0.
- [ ] URI của mỗi instance có host/port hợp lệ.
- [ ] DiscoveryClient trả đúng số lượng và URI.
- [ ] Service ID không tồn tại trả danh sách rỗng.
- [ ] Đã thêm spring-cloud-starter-loadbalancer nếu kiểm tra lựa chọn instance.
- [ ] Client dùng service ID logic và được đánh dấu @LoadBalanced.
- [ ] Test không giả định thứ tự round-robin nếu policy không được cố định.
- [ ] Test HTTP dùng port động và server giả.
- [ ] Cache/retry được cấu hình theo mục tiêu test.
- [ ] Health check có endpoint và path đúng.
- [ ] Metadata filter được kiểm tra riêng với property binding.
- [ ] Không dùng SimpleDiscoveryClient để kết luận về heartbeat hoặc registry lifecycle.
- [ ] Spring Cloud BOM tương thích với Spring Boot của dự án.

## Ghi nhớ

SimpleDiscoveryClient cho phép khai báo nhiều ServiceInstance bằng properties mà không cần registry server. Hãy kiểm thử theo từng lớp: property mapping, DiscoveryClient, LoadBalancer selection và HTTP request thực tế. Spring Cloud LoadBalancer mặc định dùng round-robin nhưng có thể được tùy biến; vì vậy test nên cố định policy khi cần xác minh phân phối cụ thể. Khi cần health filtering, dùng HealthCheckServiceInstanceListSupplier và cung cấp endpoint probe cho từng instance. SimpleDiscoveryClient là công cụ mô phỏng danh sách tĩnh, không thay thế kiểm thử registration, heartbeat hoặc cập nhật instance của registry thật.

## Tài liệu tham khảo

- Spring Cloud Commons – Common Abstractions / SimpleDiscoveryClient: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Boot – Testing: https://docs.spring.io/spring-boot/reference/testing/index.html
- OkHttp MockWebServer: https://github.com/square/okhttp/tree/master/mockwebserver

