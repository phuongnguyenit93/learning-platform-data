# DiscoveryClient không có instance hoặc chọn sai implementation

Khi `DiscoveryClient#getInstances(serviceId)` trả về danh sách rỗng, ứng dụng thường bị hiểu nhầm là đã mất kết nối tới service registry. Thực tế, kết quả rỗng chỉ cho biết implementation đang được gọi không tìm thấy instance cho đúng `serviceId` tại thời điểm truy vấn. Nguyên nhân có thể nằm ở dependency runtime, cấu hình theo profile, service ID, registry, thứ tự nhiều discovery client hoặc việc ứng dụng đang dùng API blocking trong khi chỉ bật client reactive.

Bài này hướng dẫn lần theo đường đi từ Spring context tới registry, xác định implementation thực sự được chọn và kiểm tra danh sách instance trước khi điều chỉnh cấu hình.

## 1. Hiểu kết quả mà DiscoveryClient trả về

`org.springframework.cloud.client.discovery.DiscoveryClient` là abstraction blocking của Spring Cloud Commons. Hai thao tác quan trọng là:

- `getServices()` trả về các service ID mà client hiện tại biết.
- `getInstances(serviceId)` trả về các `ServiceInstance` thuộc service ID được yêu cầu.

Một `ServiceInstance` mô tả địa chỉ của một instance, thường gồm service ID, host, port, URI, trạng thái secure và metadata. Nếu `getInstances("inventory")` trả về danh sách rỗng, hãy kiểm tra `getServices()` trước để biết client có nhìn thấy service ID `inventory` hay không. Nếu danh sách service cũng rỗng, cần điều tra nguồn discovery và cấu hình kết nối. Nếu danh sách có service nhưng không có instance, hãy kiểm tra trạng thái đăng ký, bộ lọc và đúng tên service.

Phân biệt ba lớp sau giúp khoanh vùng nhanh:

| Lớp | Trách nhiệm | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| Service registry | Lưu thông tin service và instance đã đăng ký | Service có xuất hiện trong registry, đúng namespace/region/tenant và trạng thái có được phép nhận traffic hay không |
| `DiscoveryClient` | Đọc instance từ một registry hoặc từ cấu hình tĩnh | Bean nào được tạo, `getServices()` và `getInstances()` trả về gì |
| Spring Cloud LoadBalancer | Chọn một instance từ danh sách để gửi request | `ServiceInstanceListSupplier`, bộ lọc, cache và cấu hình client theo service ID |

Vì vậy, nếu gọi trực tiếp `DiscoveryClient` và nhận danh sách rỗng, hãy điều tra discovery trước. Nếu `DiscoveryClient` đã trả về instance nhưng request qua load balancer vẫn thất bại, chuyển sang kiểm tra cấu hình LoadBalancer và HTTP client.

Spring Cloud còn có `ReactiveDiscoveryClient`, dùng kiểu trả về reactive. Đây là một abstraction riêng. Một ứng dụng có thể bật hoặc tắt blocking và reactive discovery độc lập; việc một loại client tồn tại không đảm bảo loại còn lại cũng tồn tại.

## 2. Kiểm tra dependency runtime và auto-configuration

Implementation cụ thể được cung cấp bởi integration tương ứng, chẳng hạn Eureka, Consul hoặc ZooKeeper. Chỉ thêm `spring-cloud-commons` cung cấp abstraction chưa đủ để kết nối tới một registry cụ thể. Hãy kiểm tra dependency của đúng module chạy ứng dụng, đặc biệt là `runtimeClasspath`; dependency chỉ có trong test hoặc module khác sẽ không tạo integration trong tiến trình đang gặp lỗi.

Ví dụ các starter thường gặp:

| Registry | Starter thường dùng |
| --- | --- |
| Eureka | `org.springframework.cloud:spring-cloud-starter-netflix-eureka-client` |
| Consul Discovery | `org.springframework.cloud:spring-cloud-starter-consul-discovery` |
| ZooKeeper Discovery | `org.springframework.cloud:spring-cloud-starter-zookeeper-discovery` |

Với Gradle, có thể kiểm tra cây dependency của module ứng dụng:

```bash
./gradlew :<application-module>:dependencies --configuration runtimeClasspath
```

Tìm starter của registry dự kiến, phiên bản Spring Cloud Commons tương ứng và các integration không mong muốn. Nếu ứng dụng chỉ định dùng Eureka nhưng runtime lại thiếu Eureka client, Spring Cloud không thể tự suy ra registry cần kết nối. Nếu có nhiều starter discovery cùng lúc, cần xác định đây là cấu hình chủ ý hay dependency còn sót lại.

Kiểm tra các cờ discovery trong cấu hình đã được nạp:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: true
```

Các giá trị trên minh họa trạng thái bật cả hai loại client. Nếu `spring.cloud.discovery.enabled=false`, discovery bị tắt. Nếu `spring.cloud.discovery.blocking.enabled=false`, không nên kỳ vọng blocking `DiscoveryClient` được bật; tương tự, `spring.cloud.discovery.reactive.enabled=false` ảnh hưởng tới reactive discovery. Tên property và điều kiện auto-configuration có thể thay đổi theo release train, vì vậy hãy đối chiếu tài liệu đúng phiên bản của ứng dụng.

Trong các phiên bản Spring Cloud hiện hành, `@EnableDiscoveryClient` không còn là annotation bắt buộc: đưa implementation phù hợp vào classpath sẽ kích hoạt cơ chế auto-configuration của integration. Thêm annotation này không thể thay thế starter còn thiếu, sửa dependency scope hoặc bật một property đang tắt discovery. Với release train cũ, hãy kiểm tra hướng dẫn riêng của phiên bản đang dùng.

## 3. Xác nhận implementation thực sự được tạo

Đừng chỉ nhìn dependency khai báo. Hãy kiểm tra bean trong Spring ApplicationContext khi ứng dụng đã khởi động. Có thể tạm thêm một `ApplicationRunner` để ghi tên bean, lớp implementation, thứ tự và kết quả truy vấn. Ví dụ dưới đây dùng `inventory` làm service ID minh họa:

```java
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
class DiscoveryClientDiagnostics implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryClientDiagnostics.class);

    private final ApplicationContext applicationContext;

    DiscoveryClientDiagnostics(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @Override
    public void run(ApplicationArguments args) {
        String serviceId = "inventory";
        Map<String, DiscoveryClient> clients =
                applicationContext.getBeansOfType(DiscoveryClient.class);

        if (clients.isEmpty()) {
            log.warn("Không tìm thấy bean blocking DiscoveryClient");
            return;
        }

        clients.forEach((beanName, client) -> {
            try {
                List<String> services = client.getServices();
                List<ServiceInstance> instances = client.getInstances(serviceId);

                log.info(
                        "bean={} type={} order={} description={} services={} target={} instanceCount={}",
                        beanName,
                        client.getClass().getName(),
                        client.getOrder(),
                        client.description(),
                        services,
                        serviceId,
                        instances == null ? 0 : instances.size());

                if (instances != null) {
                    instances.forEach(instance -> log.info(
                            "bean={} serviceId={} host={} port={} secure={}",
                            beanName,
                            instance.getServiceId(),
                            instance.getHost(),
                            instance.getPort(),
                            instance.isSecure()));
                }
            }
            catch (RuntimeException ex) {
                log.warn("Không truy vấn được DiscoveryClient bean {}", beanName, ex);
            }
        });
    }
}
```

Chạy chẩn đoán trong môi trường kiểm soát rồi gỡ hoặc giới hạn log sau khi tìm được nguyên nhân. Danh sách service, địa chỉ instance và tên registry có thể là thông tin vận hành nội bộ; không mở endpoint hoặc log chẩn đoán ra bên ngoài.

Đọc kết quả theo các dấu hiệu sau:

1. Không có bean `DiscoveryClient`: kiểm tra starter có trong runtime hay không, các cờ `spring.cloud.discovery.*`, cấu hình loại trừ auto-configuration và lỗi khởi tạo context.
2. Implementation là `SimpleDiscoveryClient` trong khi mong đợi Eureka/Consul: thường cần kiểm tra starter registry có bị thiếu, sai module hoặc sai runtime profile hay không.
3. Implementation là `CompositeDiscoveryClient`: có nhiều client blocking được đăng ký. Kiểm tra từng bean con, `order` và kết quả của từng backend.
4. Bean provider ném exception: xem log của integration để phân biệt lỗi DNS, kết nối, xác thực, TLS, timeout hoặc lỗi giao thức.
5. `getServices()` có service ID nhưng `getInstances(serviceId)` rỗng: đối chiếu chính xác ID, trạng thái instance và các điều kiện lọc của registry.

## 4. Hiểu SimpleDiscoveryClient và cấu hình service ID

`SimpleDiscoveryClient` là implementation dựa trên property. Tài liệu Spring Cloud Commons mô tả nó được dùng khi classpath không có implementation `DiscoveryClient` được hỗ trợ bởi service registry. Vì vậy, thấy `SimpleDiscoveryClient` trong khi kỳ vọng registry thật thường là dấu hiệu cần kiểm tra dependency runtime và cấu hình khởi chạy.

Ví dụ cấu hình hai instance tĩnh cho service `inventory`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Property tương đương cho instance đầu tiên có dạng:

```properties
spring.cloud.discovery.client.simple.instances.inventory[0].uri=http://localhost:8081
```

`inventory` trong cấu hình là service ID mà caller phải truyền vào `getInstances("inventory")`. Nếu cấu hình dùng `inventory-api` nhưng caller hỏi `inventory`, `SimpleDiscoveryClient` trả về danh sách rỗng. Các index của danh sách instance bắt đầu từ `0`.

Đừng nhầm `spring.application.name` với service ID của đích gọi. `spring.application.name` thường định danh chính ứng dụng khi đăng ký; tham số `serviceId` trong `getInstances(serviceId)` là tên service mà caller muốn tìm. Hai giá trị có thể trùng nhau trong một số ứng dụng, nhưng không có yêu cầu phải trùng.

Kiểm tra profile đang hoạt động và nguồn cấu hình thực tế. Một file `application-local.yml` có thể chứa danh sách instance đúng, trong khi container đang chạy profile `prod`; biến môi trường hoặc tham số dòng lệnh cũng có thể ghi đè file YAML. Hãy xác minh giá trị cuối cùng của các property liên quan, không chỉ nội dung file cấu hình trong repository.

## 5. Khi có nhiều implementation: thứ tự và CompositeDiscoveryClient

`DiscoveryClient` kế thừa `Ordered`. Implementation mặc định có `order` bằng `0`; implementation tùy chỉnh có thể ghi đè `getOrder()`. Spring Cloud Commons cho phép đặt thứ tự cho các client do Spring Cloud cung cấp bằng property riêng của từng integration, ví dụ `spring.cloud.consul.discovery.order` hoặc `eureka.client.order`. `SimpleDiscoveryClient` có property `spring.cloud.discovery.client.simple.order`.

Với blocking discovery, `CompositeDiscoveryClient` sắp xếp các client theo thứ tự rồi lần lượt gọi `getInstances(serviceId)`. Nó trả về danh sách đầu tiên khác rỗng và dừng lại; nó không gộp instance từ mọi registry. Vì thế, nếu nhiều backend cùng có một service ID, backend đứng trước có thể quyết định địa chỉ mà ứng dụng nhìn thấy. Nếu backend đầu tiên trả về rỗng, composite mới thử backend tiếp theo.

Ví dụ, khi chủ ý ưu tiên Eureka trước Consul, hãy cấu hình thứ tự theo tài liệu của hai integration và xác minh lại kết quả bằng log chẩn đoán. Giá trị `order` nhỏ hơn được xử lý trước theo quy tắc `Ordered`. Chỉ dùng nhiều backend khi đã xác định rõ backend nào là nguồn chính và hành vi fallback mong muốn; nếu ứng dụng chỉ cần một registry, loại bỏ dependency thừa sẽ làm cấu hình dễ hiểu hơn.

Reactive discovery cần được xem riêng. `ReactiveCompositeDiscoveryClient` có hành vi mặc định khác: truy vấn song song và dùng phản hồi không rỗng đến nhanh nhất. Implementation cũng có constructor hỗ trợ ép tuần tự theo thứ tự. Do đó, không áp dụng kết luận về thứ tự của blocking `CompositeDiscoveryClient` cho reactive client nếu chưa xác minh phiên bản và cách composite được tạo.

Nếu ứng dụng dùng WebFlux, kiểm tra đúng kiểu bean và property `spring.cloud.discovery.reactive.enabled`. Nếu code cần `DiscoveryClient` blocking, hãy kiểm tra `spring.cloud.discovery.blocking.enabled` và dependency cung cấp blocking implementation. Đổi kiểu injection một cách tùy tiện có thể che khuất việc ứng dụng đang bật nhầm loại client.

## 6. Phân biệt lỗi registry với lỗi service ID và LoadBalancer

Khi danh sách instance rỗng, kiểm tra theo thứ tự sau:

1. **Service ID:** Gọi `getServices()` và so sánh chính xác ID với tham số truyền vào `getInstances`. Không suy đoán tên từ URL, tên hiển thị hoặc tên module.
2. **Đăng ký:** Mở giao diện hoặc API của registry và xác nhận instance đã đăng ký, đúng ứng dụng, namespace, datacenter/region và trạng thái cho phép nhận traffic.
3. **Cấu hình caller:** Kiểm tra active profile, địa chỉ registry, thông tin xác thực, TLS, namespace và các property ghi đè. Đối chiếu log khởi động của provider integration.
4. **Mạng từ tiến trình ứng dụng:** Kiểm tra DNS, route, firewall, network policy và cổng registry từ chính container hoặc máy chạy ứng dụng. Truy cập được registry từ laptop không chứng minh pod có cùng đường mạng.
5. **Thời điểm:** Xác nhận instance đã đăng ký trước khi caller truy vấn. Registry có thể cập nhật trạng thái trễ; không dùng `Thread.sleep` cố định làm cách đồng bộ. Nếu nghiệp vụ cần đợi service sẵn sàng, dùng cơ chế retry có giới hạn, backoff và timeout rõ ràng.
6. **LoadBalancer:** Nếu `DiscoveryClient` đã trả về instance nhưng request theo tên service vẫn không chọn được server, kiểm tra `ServiceInstanceListSupplier`, cache, health-check supplier, zone preference, bộ lọc và cấu hình client theo service ID.

Actuator có thể hỗ trợ quan sát. `DiscoveryClientHealthIndicator` dựa trên implementation đang được đăng ký; property `spring.cloud.discovery.client.health-indicator.enabled` điều khiển health indicator này. Mặc định health indicator có thể gọi `getServices()`. Với hệ thống có nhiều service, `spring.cloud.discovery.client.health-indicator.use-services-query=false` yêu cầu dùng `probe()` thay cho truy vấn toàn bộ danh sách service. Trạng thái health `UP` cho biết phép kiểm tra của indicator thành công; nó không chứng minh một service ID cụ thể có instance. Hãy kiểm tra trực tiếp `getInstances(serviceId)` khi cần xác nhận service đích.

Actuator endpoint `features` của Spring Cloud Commons cũng có thể cho biết feature discovery nào hiện diện trong classpath và được bật. Chỉ expose Actuator hoặc thông tin cấu hình trong mạng quản trị có xác thực và phân quyền phù hợp; không công khai `/actuator/env`, `/actuator/configprops` hay dữ liệu registry nhạy cảm.

## 7. Kiểm thử cấu hình discovery

Nên có kiểm thử xác nhận service ID mà ứng dụng phụ thuộc được phân giải trong môi trường kiểm thử tương ứng. Nếu dùng registry thật, kiểm thử tích hợp cần khởi tạo registry hoặc môi trường test đã đăng ký instance. Nếu dùng `SimpleDiscoveryClient`, cấu hình rõ instance giả lập cho profile test.

Ví dụ kiểm thử hợp đồng blocking ở mức Spring context:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest
class DiscoveryConfigurationTest {

    @Autowired
    private DiscoveryClient discoveryClient;

    @Test
    void inventoryServiceHasAtLeastOneInstance() {
        assertThat(discoveryClient.getServices()).contains("inventory");
        assertThat(discoveryClient.getInstances("inventory")).isNotEmpty();
    }
}
```

Kiểm thử trên cần có cấu hình registry hoặc `SimpleDiscoveryClient` phù hợp với profile test; nếu không, kết quả thất bại phản ánh môi trường test chưa được dựng đúng. Trong hệ thống nhiều registry, bổ sung kiểm thử xác nhận implementation được kỳ vọng và thứ tự ưu tiên, tránh để một dependency mới làm thay đổi backend trả instance.

## 8. Lưu ý tương thích phiên bản

Spring Cloud phát hành theo release train và mỗi train hỗ trợ một dải phiên bản Spring Boot cụ thể. Dùng Spring Cloud BOM tương ứng với phiên bản Boot của ứng dụng, thay vì nâng riêng một starter hoặc `spring-cloud-commons` lên phiên bản mới nhất. Compatibility verifier có thể phát hiện một số tổ hợp Boot/Cloud không tương thích khi ứng dụng khởi động; không nên tắt verifier chỉ để che lỗi cấu hình phiên bản.

Tên property, điều kiện auto-configuration và chi tiết giữa blocking/reactive có thể thay đổi theo release train. Khi xử lý sự cố, đối chiếu tài liệu `Spring Cloud Commons` và tài liệu của integration (Eureka, Consul, ZooKeeper hoặc Kubernetes) đúng phiên bản đang chạy. Không lấy ví dụ từ tài liệu `current` rồi mặc định property đó tồn tại trong một ứng dụng dùng release train cũ.

## 9. Checklist xử lý nhanh

- [ ] Xác nhận ứng dụng đang gọi blocking `DiscoveryClient` hay `ReactiveDiscoveryClient`.
- [ ] Kiểm tra starter registry có trong `runtimeClasspath` của đúng module.
- [ ] Xác minh `spring.cloud.discovery.enabled` và cờ bật loại client tương ứng.
- [ ] Ghi nhận tên bean, implementation class, `order`, `getServices()` và kết quả `getInstances(serviceId)`.
- [ ] Nếu là `SimpleDiscoveryClient`, kiểm tra dependency registry và `spring.cloud.discovery.client.simple.instances`.
- [ ] Nếu là `CompositeDiscoveryClient`, kiểm tra từng delegate và thứ tự ưu tiên; nhớ rằng blocking composite lấy danh sách không rỗng đầu tiên.
- [ ] So sánh service ID với tên được registry công bố; xác nhận instance đã đăng ký và khỏe.
- [ ] Nếu discovery đã trả instance, chuyển sang kiểm tra Spring Cloud LoadBalancer.
- [ ] Đối chiếu Spring Cloud release train với Spring Boot và dùng tài liệu đúng phiên bản.

## Tài liệu tham khảo chính thức

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `DiscoveryClient`, cờ bật/tắt discovery, thứ tự implementation, `SimpleDiscoveryClient`, health indicator và LoadBalancer.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): danh sách property được Spring Cloud Commons công bố.
- [DiscoveryClient.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): hợp đồng blocking và `Ordered`.
- [CompositeDiscoveryClient.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/composite/CompositeDiscoveryClient.java): cách composite blocking sắp xếp và chọn danh sách instance.
- [ReactiveCompositeDiscoveryClient.java — Spring Cloud Commons source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/composite/reactive/ReactiveCompositeDiscoveryClient.java): hành vi truy vấn reactive và tùy chọn ép thứ tự.
- [Spring Cloud Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/index.html): phiên bản release train và quan hệ tương thích với Spring Boot.
