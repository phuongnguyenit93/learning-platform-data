# Tra cứu instance bằng SimpleDiscoveryClient

## 1. Mục tiêu thực hành

Trong hệ thống microservices, một service có thể chạy nhiều instance. Consumer cần biết các địa chỉ của instance thuộc một service ID để quan sát topology hoặc chuyển tiếp request qua một cơ chế load balancing.

Spring Cloud Commons cung cấp abstraction `DiscoveryClient`. Khi ứng dụng không có discovery client dựa trên service registry như Eureka, Consul hoặc Zookeeper trên classpath, Spring Cloud có thể cấu hình `SimpleDiscoveryClient`. Implementation này lấy danh sách service và instance từ application properties.

Trong bài lab, ta xây dựng một ứng dụng `discovery-inspector` có thể:

- Khai báo hai instance của `catalog-service` và một instance của `payment-service`.
- Inject `DiscoveryClient` để tra cứu danh sách service.
- Tra cứu instance theo service ID.
- Hiển thị host, port, URI, HTTPS flag, instance ID và metadata.
- Trả về danh sách rỗng khi service ID chưa được cấu hình.
- Viết test xác minh dữ liệu properties được ánh xạ thành `ServiceInstance`.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_CORE**. Module giúp người học hiểu Spring Cloud Commons, Spring Cloud Context, cấu hình ngoài, tương thích Spring Boot, refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử/vận hành các abstraction chung.

## 2. Hiểu đúng vai trò của SimpleDiscoveryClient

### 2.1. DiscoveryClient là hợp đồng tra cứu

`DiscoveryClient` cung cấp các thao tác đọc chính:

| API | Ý nghĩa |
| --- | --- |
| `getServices()` | Trả về các service ID mà discovery client biết |
| `getInstances(serviceId)` | Trả về các instance thuộc service ID được yêu cầu |
| `description()` | Mô tả implementation, thường dùng trong health indicator |
| `probe()` | Kiểm tra discovery client có thể thực hiện thao tác tra cứu hay không; mặc định gọi `getServices()` |

Mỗi phần tử trả về là một `ServiceInstance`, với các thông tin như:

- `getServiceId()`: service ID.
- `getInstanceId()`: ID duy nhất của instance nếu có.
- `getHost()` và `getPort()`: địa chỉ vật lý.
- `getUri()`: URI truy cập.
- `isSecure()`: instance dùng HTTPS hay HTTP.
- `getMetadata()`: các cặp key/value bổ sung.

Consumer nên phụ thuộc vào interface `DiscoveryClient`, vì cùng một code có thể làm việc với Simple Discovery, Eureka, Consul hoặc implementation khác.

### 2.2. SimpleDiscoveryClient lấy dữ liệu từ đâu?

Simple Discovery dùng property prefix:

```text
spring.cloud.discovery.client.simple.instances
```

Cấu trúc dữ liệu là map từ service ID sang danh sách instance. Ví dụ:

```text
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://catalog-1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://catalog-2:8081
```

Trong đó:

- `catalog-service` là service ID.
- `[0]` và `[1]` là chỉ số của hai instance, bắt đầu từ 0.
- `uri` là địa chỉ mà instance có thể được truy cập.

Nếu không có discovery client dựa trên registry trong classpath, Spring Cloud tự cấu hình `SimpleDiscoveryClient`. Nếu ứng dụng đã có Eureka, Consul hoặc Zookeeper starter, implementation tương ứng có thể được chọn thay thế. Vì vậy, khi thực hành cần tránh thêm các starter registry không liên quan.

Với các phiên bản Spring Cloud hiện hành, không cần thêm `@EnableDiscoveryClient` chỉ để kích hoạt discovery khi implementation đã được auto-configure trên classpath.

### 2.3. SimpleDiscoveryClient không phải service registry

Simple Discovery đọc danh sách tĩnh từ cấu hình. Nó không tự:

- Đăng ký instance lên một registry server.
- Gửi heartbeat hoặc lease.
- Phát hiện instance mới được triển khai.
- Tự loại instance chết khỏi danh sách.
- Kiểm tra endpoint có thực sự healthy trước mỗi lần trả kết quả.

Do đó, Simple Discovery phù hợp cho local development, demo, test hoặc topology nhỏ được quản lý bằng cấu hình. Với hệ thống cần registration động và health-aware discovery, hãy dùng registry phù hợp hoặc kết hợp Spring Cloud LoadBalancer với health-check supplier theo yêu cầu.

## 3. Chuẩn bị project

### 3.1. Dependency

Ứng dụng cần Spring Boot Web và Spring Cloud Commons. Dependency management nên dùng Spring Cloud BOM tương thích với phiên bản Spring Boot của project.

Ví dụ Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-commons</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu project đã quản lý Spring Cloud bằng BOM, không khai báo version riêng cho `spring-cloud-commons`. Không thêm Eureka/Consul/Zookeeper starter vào lab này, vì mục tiêu là để Simple Discovery được chọn làm implementation.

### 3.2. Cấu trúc source

Có thể tổ chức project như sau:

```text
discovery-inspector/
└── src/
    ├── main/
    │   ├── java/com/example/discovery/
    │   │   ├── DiscoveryInspectorApplication.java
    │   │   ├── DiscoveryController.java
    │   │   └── InstanceView.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/discovery/
            └── SimpleDiscoveryLookupTests.java
```

## 4. Khai báo nhiều instance trong application.yml

Tạo file `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: discovery-inspector
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
                instance-id: catalog-1
                metadata:
                  zone: zone-a
                  version: v1
              - uri: https://localhost:8443
                instance-id: catalog-2
                metadata:
                  zone: zone-b
                  version: v2
            payment-service:
              - uri: http://localhost:8090
                instance-id: payment-1
                metadata:
                  zone: zone-a
                  version: v1
server:
  port: 8080
```

Cấu hình này tạo topology:

| Service ID | Instance ID | URI | Metadata |
| --- | --- | --- | --- |
| `catalog-service` | `catalog-1` | `http://localhost:8081` | zone-a, v1 |
| `catalog-service` | `catalog-2` | `https://localhost:8443` | zone-b, v2 |
| `payment-service` | `payment-1` | `http://localhost:8090` | zone-a, v1 |

Một số điểm cần chú ý:

- Service ID là key của map bên dưới `instances`; consumer phải truy vấn đúng key đó.
- Index list được Spring Boot bind tự động từ YAML. Nếu dùng properties, index đầu tiên là `[0]`.
- URI phải có scheme `http` hoặc `https` và địa chỉ/port hợp lệ.
- `metadata` là map string key/value để mô tả zone, version hoặc thông tin định tuyến.
- `instance-id` giúp phân biệt các instance cùng service.
- Trong Docker/Kubernetes, không dùng `localhost` để trỏ sang container khác; hãy dùng DNS/service name có thể phân giải từ network của ứng dụng.

Nếu chỉ khai báo URI, Spring Cloud vẫn có thể tạo `ServiceInstance`. Các field host, port và secure được suy ra từ URI. Có thể khai báo thêm metadata để consumer hoặc load balancer dùng khi cần.

## 5. Tạo ứng dụng Spring Boot

### 5.1. Application entry point

```java
package com.example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryInspectorApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryInspectorApplication.class, args);
    }
}
```

Không cần khai báo `@EnableDiscoveryClient` trong ví dụ này. Spring Cloud Commons auto-configuration sẽ tạo Simple Discovery client khi không có service-registry-backed client khác.

### 5.2. Tạo DTO cho instance

Không nên trả trực tiếp object implementation nội bộ của discovery client qua API. Tạo DTO ổn định để kiểm soát field được công bố:

```java
package com.example.discovery;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

public record InstanceView(
        String serviceId,
        String instanceId,
        String host,
        int port,
        boolean secure,
        URI uri,
        Map<String, String> metadata) {

    public static InstanceView from(ServiceInstance instance) {
        Map<String, String> source = instance.getMetadata();
        Map<String, String> safeMetadata = source == null
                ? Map.of()
                : new LinkedHashMap<>(source);

        return new InstanceView(
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getHost(),
                instance.getPort(),
                instance.isSecure(),
                instance.getUri(),
                safeMetadata
        );
    }
}
```

Metadata có thể được dùng trong nội bộ discovery. Nếu metadata chứa thông tin nhạy cảm, không trả toàn bộ map ra API công khai; hãy lọc theo allowlist.

### 5.3. Tạo endpoint tra cứu

Inject interface `DiscoveryClient` vào controller:

```java
package com.example.discovery;

import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/discovery")
public class DiscoveryController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/implementation")
    public String implementation() {
        return discoveryClient.description();
    }

    @GetMapping("/services")
    public List<String> services() {
        return discoveryClient.getServices().stream()
                .sorted()
                .toList();
    }

    @GetMapping("/services/{serviceId}/instances")
    public ResponseEntity<List<InstanceView>> instances(
            @PathVariable String serviceId) {

        List<InstanceView> result = discoveryClient.getInstances(serviceId)
                .stream()
                .map(InstanceView::from)
                .toList();

        return ResponseEntity.ok(result);
    }
}
```

Ba endpoint thực hiện ba thao tác riêng:

- `GET /api/discovery/implementation`: xác nhận implementation đang được inject.
- `GET /api/discovery/services`: liệt kê service ID đã cấu hình.
- `GET /api/discovery/services/{serviceId}/instances`: tra cứu các instance của một service.

Với service ID không tồn tại, `SimpleDiscoveryClient.getInstances()` trả về danh sách rỗng. Controller giữ semantics này và trả HTTP 200 với mảng rỗng. Nếu API nghiệp vụ cần phân biệt service không tồn tại với service chưa có instance, hãy định nghĩa quy ước riêng ở tầng ứng dụng.

## 6. Chạy ứng dụng và tra cứu instance

Khởi động ứng dụng bằng IDE hoặc lệnh chạy Spring Boot mà project đang dùng. Sau khi ứng dụng sẵn sàng trên port 8080, gọi các endpoint sau.

### 6.1. Xác nhận implementation

```bash
curl http://localhost:8080/api/discovery/implementation
```

Kết quả mong đợi khi không có registry-backed discovery client:

```text
Simple Discovery Client
```

Nếu kết quả cho biết implementation khác, kiểm tra dependency tree và loại bỏ starter registry khỏi profile thực hành.

### 6.2. Liệt kê service ID

```bash
curl http://localhost:8080/api/discovery/services
```

Ví dụ kết quả:

```json
[
  "catalog-service",
  "payment-service"
]
```

Thứ tự phần tử có thể khác nhau tùy implementation. Controller đã sắp xếp kết quả theo tên để response ổn định hơn trong lab.

### 6.3. Tra cứu instance của catalog-service

```bash
curl http://localhost:8080/api/discovery/services/catalog-service/instances
```

Ví dụ kết quả rút gọn:

```json
[
  {
    "serviceId": "catalog-service",
    "instanceId": "catalog-1",
    "host": "localhost",
    "port": 8081,
    "secure": false,
    "uri": "http://localhost:8081",
    "metadata": {
      "zone": "zone-a",
      "version": "v1"
    }
  },
  {
    "serviceId": "catalog-service",
    "instanceId": "catalog-2",
    "host": "localhost",
    "port": 8443,
    "secure": true,
    "uri": "https://localhost:8443",
    "metadata": {
      "zone": "zone-b",
      "version": "v2"
    }
  }
]
```

Các giá trị host, port và secure được suy ra từ URI cấu hình. Metadata được giữ lại dưới dạng map key/value.

### 6.4. Tra cứu service chưa được cấu hình

```bash
curl http://localhost:8080/api/discovery/services/shipping-service/instances
```

Kết quả:

```json
[]
```

Đây là hành vi bình thường của Simple Discovery khi map không có service ID được yêu cầu. Consumer cần quyết định nghiệp vụ tiếp theo, chẳng hạn trả lỗi service unavailable hoặc dùng fallback.

## 7. Viết integration test cho SimpleDiscoveryClient

Test dưới đây khởi động Spring context với property riêng của test. Không cần tạo Eureka/Consul server vì Simple Discovery chỉ đọc cấu hình.

```java
package com.example.discovery;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.application.name=discovery-inspector",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://catalog-1:8081",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].instance-id=catalog-1",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=zone-a",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=https://catalog-2:8443",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].instance-id=catalog-2",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=zone-b",
        "spring.cloud.discovery.client.simple.instances.payment-service[0].uri=http://payment-1:8090"
})
class SimpleDiscoveryLookupTests {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void usesSimpleDiscoveryImplementation() {
        assertThat(discoveryClient.description())
                .isEqualTo("Simple Discovery Client");
    }

    @Test
    void listsConfiguredServices() {
        assertThat(discoveryClient.getServices())
                .containsExactlyInAnyOrder(
                        "catalog-service",
                        "payment-service"
                );
    }

    @Test
    void returnsAllCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        assertThat(instances).hasSize(2);

        ServiceInstance first = instances.get(0);
        assertThat(first.getServiceId()).isEqualTo("catalog-service");
        assertThat(first.getInstanceId()).isEqualTo("catalog-1");
        assertThat(first.getUri())
                .isEqualTo(URI.create("http://catalog-1:8081"));
        assertThat(first.isSecure()).isFalse();
        assertThat(first.getMetadata()).containsEntry("zone", "zone-a");

        ServiceInstance second = instances.get(1);
        assertThat(second.getUri())
                .isEqualTo(URI.create("https://catalog-2:8443"));
        assertThat(second.isSecure()).isTrue();
    }

    @Test
    void returnsEmptyListForUnknownService() {
        assertThat(discoveryClient.getInstances("unknown-service"))
                .isEmpty();
    }
}
```

Test này kiểm tra bốn contract:

1. Runtime đang dùng Simple Discovery.
2. Các service ID được lấy từ map properties.
3. URI, HTTPS flag và metadata được ánh xạ vào `ServiceInstance`.
4. Service ID không tồn tại trả về danh sách rỗng.

Không assert thứ tự instance nếu thứ tự đó không phải contract của ứng dụng. Trong test trên, thứ tự được kiểm tra theo list index vì cấu hình khai báo hai phần tử có index 0 và 1. Nếu implementation hoặc nguồn cấu hình khác không cam kết thứ tự, hãy tìm instance theo `instanceId` trước khi assert.

## 8. Từ tra cứu đến gọi service

### 8.1. DiscoveryClient chỉ trả thông tin instance

Đoạn code:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");
```

chỉ tra cứu địa chỉ. Nó không gửi HTTP request, không chọn retry policy và không tự kiểm tra endpoint có hoạt động hay không.

Không nên tự lấy `instances.get(0)` làm chiến lược load balancing trong code nghiệp vụ. Cách đó luôn ưu tiên phần tử đầu tiên và không có health-aware selection, retry hoặc thống kê request.

### 8.2. Dùng Spring Cloud LoadBalancer khi cần gọi theo service ID

Nếu muốn gọi `catalog-service` bằng logical service ID thay vì địa chỉ vật lý, thêm Spring Cloud LoadBalancer starter tương thích với release train của project. Tạo HTTP client được đánh dấu `@LoadBalanced` và gọi URI dạng:

```text
http://catalog-service/api/catalog
```

LoadBalancer sử dụng các instance do DiscoveryClient cung cấp để chọn một địa chỉ vật lý. Với Simple Discovery, danh sách đầu vào vẫn đến từ properties trong `application.yml`.

Nếu tự tạo `RestClient.Builder` hoặc builder khác, áp dụng các customizer/configurer của Spring Boot tương ứng để giữ observation và tracing. Xem tài liệu Spring Cloud Commons về `@LoadBalanced` builder của RestClient/RestTemplate/WebClient.

Simple Discovery không tự xác minh health. Với một topology nhỏ, có thể cấu hình health-check supplier của Spring Cloud LoadBalancer để loại instance không phản hồi khỏi danh sách được chọn. Cơ chế health check cần có timeout, interval và path phù hợp với ứng dụng.

## 9. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không inject được `DiscoveryClient` | Thiếu Spring Cloud Commons hoặc discovery bị disable | Kiểm tra dependency management, classpath và `spring.cloud.discovery.enabled` |
| Implementation không phải Simple Discovery | Có registry-backed discovery client khác trên classpath | Kiểm tra Eureka/Consul/Zookeeper starter và profile đang bật |
| `getServices()` không có service mong đợi | Sai prefix hoặc key service ID | Kiểm tra `spring.cloud.discovery.client.simple.instances` và tên service |
| `getInstances()` trả list rỗng | Sai service ID hoặc không có phần tử instance được bind | So khớp chính xác service ID và kiểm tra index bắt đầu từ 0 |
| Chỉ nhận một instance | Cấu hình các phần tử dùng trùng index hoặc viết sai list syntax | Dùng index liên tiếp `[0]`, `[1]`, ... |
| URI thiếu host/port hoặc không hợp lệ | URI thiếu scheme hoặc port | Khai báo URI đầy đủ như `http://catalog-1:8081` |
| Instance HTTPS có `secure=false` | URI dùng scheme http hoặc cấu hình bị bind sai | Dùng `https://` và kiểm tra `ServiceInstance.isSecure()` |
| Metadata không xuất hiện | Sai cấu trúc key hoặc metadata chưa được bind | Kiểm tra `metadata.zone`, `metadata.version` và test properties |
| Discovery trả URI nhưng request thất bại | Instance không chạy, DNS không phân giải hoặc port bị chặn | Kiểm tra network, health endpoint và firewall; discovery lookup không phải health check |
| Local chạy được nhưng container không gọi được | Cấu hình dùng `localhost` để trỏ sang container khác | Dùng DNS/service name trên container network |
| Test pass nhưng app thật không thấy Simple Discovery | Test không có registry starter nhưng runtime có | So sánh dependency/profile giữa test và ứng dụng thật |

### 9.1. Checklist debug nhanh

1. Xác nhận `spring-cloud-commons` có trên runtime classpath.
2. Xác nhận không có registry-backed discovery client nếu muốn dùng Simple Discovery.
3. Xác nhận `spring.cloud.discovery.enabled` không bị tắt.
4. Kiểm tra đúng prefix và service ID.
5. Kiểm tra index list bắt đầu từ 0 và không trùng.
6. Kiểm tra URI, scheme, host và port.
7. Gọi `/api/discovery/implementation`, `/services` rồi mới gọi endpoint instances.
8. Nếu định gửi HTTP request, kiểm tra health và network độc lập với kết quả discovery.

## 10. Bài tập mở rộng

Sau khi hoàn thành lab cơ bản, thử các yêu cầu sau:

1. Thêm instance thứ ba cho `catalog-service` với metadata `zone: zone-c`.
2. Thêm `shipping-service` với hai instance và xác minh `getServices()` cập nhật.
3. Mở rộng controller để nhận query parameter `zone`, chỉ trả instance có metadata zone tương ứng.
4. Viết test cho filter zone và test trường hợp metadata không có key `zone`.
5. Thêm một registry-backed discovery starter vào profile riêng, quan sát implementation được chọn thay đổi như thế nào.
6. Thêm Spring Cloud LoadBalancer và gọi endpoint bằng service ID `http://catalog-service`.
7. Cấu hình health-check supplier và mô phỏng một instance không phản hồi để quan sát lựa chọn instance.

## 11. Tiêu chí hoàn thành

Bài lab đạt yêu cầu khi:

- Ứng dụng khởi động mà không cần Eureka, Consul hoặc Zookeeper.
- `DiscoveryClient.description()` xác nhận Simple Discovery đang được dùng.
- `getServices()` trả đủ service ID đã khai báo.
- `getInstances("catalog-service")` trả hai instance với URI và metadata chính xác.
- Instance HTTPS được nhận diện qua `isSecure()`.
- Service ID không tồn tại trả về list rỗng.
- Integration test xác minh được các contract trên.
- Người học giải thích được sự khác nhau giữa discovery lookup, health check và load balancing.

## 12. Tài liệu tham khảo chính thức

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): điều kiện sử dụng SimpleDiscoveryClient, property prefix và service discovery abstraction.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): các thuộc tính `spring.cloud.discovery.client.simple.*`.
- [DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): contract `getServices()`, `getInstances()`, `description()` và `probe()`.
- [SimpleDiscoveryClient source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClient.java): cách ánh xạ properties thành danh sách ServiceInstance.
- [ServiceInstance API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java): các field service ID, instance ID, host, port, URI, secure và metadata.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): cách dùng danh sách instance từ DiscoveryClient để chọn instance khi gọi service.

**Ghi nhớ:** SimpleDiscoveryClient là discovery client dựa trên properties. Nó giúp ứng dụng tra cứu danh sách instance theo service ID qua cùng contract `DiscoveryClient`, nhưng không cung cấp registry động, heartbeat hoặc health check. Khi cần gọi service theo tên và chọn instance, hãy kết hợp discovery với Spring Cloud LoadBalancer.
