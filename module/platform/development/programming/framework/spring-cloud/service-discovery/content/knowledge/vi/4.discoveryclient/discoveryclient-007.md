# Nhiều DiscoveryClient: thứ tự ưu tiên và hành vi tổng hợp

Một ứng dụng Spring Cloud có thể có nhiều implementation của `DiscoveryClient` cùng lúc, chẳng hạn Eureka và Consul. Spring Cloud Commons cung cấp abstraction chung để code ứng dụng truy vấn service mà không phụ thuộc trực tiếp vào từng registry. Khi có nhiều implementation, Spring tạo composite client để điều phối truy vấn. Thứ tự của các client và kiểu composite được dùng sẽ quyết định instance nào được trả về.

Điểm cần nắm rõ là composite không mặc nhiên đồng bộ dữ liệu giữa các registry. Với API blocking, truy vấn instance đi theo thứ tự ưu tiên và dùng kết quả không rỗng đầu tiên. Với API reactive, mặc định client trả kết quả không rỗng nhanh nhất sẽ thắng; có thể cấu hình ép thứ tự hoặc gộp kết quả. Hai cách này tạo ra hành vi khác nhau khi một service được đăng ký ở nhiều nơi.

## 1. Vì sao một ứng dụng có nhiều DiscoveryClient?

`DiscoveryClient` là abstraction đọc dữ liệu service discovery. Một implementation kết nối với một nguồn cụ thể, ví dụ:

- `EurekaDiscoveryClient`: đọc danh sách instance từ Eureka.
- `ConsulDiscoveryClient`: đọc service và health state từ Consul.
- `ZookeeperDiscoveryClient`: đọc dữ liệu discovery từ ZooKeeper.
- `SimpleDiscoveryClient`: đọc danh sách instance tĩnh từ cấu hình ứng dụng.
- Implementation tùy chỉnh: đọc từ registry nội bộ hoặc nguồn dữ liệu khác.

Một ứng dụng có thể cần nhiều client trong các tình huống:

1. Chuyển đổi registry theo từng giai đoạn, ví dụ di chuyển service từ Eureka sang Consul.
2. Một số service vẫn nằm trong registry cũ trong khi service mới đã đăng ký ở registry mới.
3. Các nhóm hoặc vùng triển khai dùng registry khác nhau nhưng consumer cần một abstraction chung.
4. Cần một nguồn instance tĩnh cho môi trường phát triển hoặc kiểm thử.

Khi các starter tương ứng có mặt trên classpath và auto-configuration được bật, Spring Cloud có thể tạo nhiều bean discovery client. Spring Cloud Commons cung cấp `CompositeDiscoveryClient` cho API blocking và `ReactiveCompositeDiscoveryClient` cho API reactive. Composite blocking mặc định là bean `@Primary`, vì vậy khi inject `DiscoveryClient` theo kiểu thông thường, ứng dụng nhận được composite thay vì phải tự chọn một registry.

Trong Spring Cloud hiện đại, `@EnableDiscoveryClient` không còn bắt buộc chỉ để kích hoạt discovery. Việc có implementation tương ứng trên classpath cùng auto-configuration thường đã đủ. Có thể tắt riêng blocking discovery, reactive discovery hoặc toàn bộ discovery bằng các thuộc tính cấu hình.

## 2. Thứ tự ưu tiên của DiscoveryClient

`DiscoveryClient` kế thừa Spring `Ordered`. Mỗi client có một giá trị order để composite sắp xếp trước khi truy vấn:

- Giá trị số **nhỏ hơn** có độ ưu tiên cao hơn và được xét trước.
- `DiscoveryClient.DEFAULT_ORDER` mặc định là `0`.
- Nếu nhiều client cùng `order`, không nên dựa vào thứ tự khởi tạo bean để quyết định registry nào thắng. Hãy đặt các giá trị khác nhau cho những client cần ưu tiên rõ ràng.

Ví dụ, muốn Eureka được hỏi trước Consul:

```yaml
eureka:
  client:
    order: -10

spring:
  cloud:
    consul:
      discovery:
        order: 0
```

Thuộc tính cấu hình chung cho các client do Spring Cloud cung cấp có dạng `spring.cloud.{clientIdentifier}.discovery.order`. Eureka sử dụng thuộc tính riêng `eureka.client.order`. Ví dụ khác:

| Discovery client | Thuộc tính order |
|---|---|
| Eureka | `eureka.client.order` |
| Consul | `spring.cloud.consul.discovery.order` |
| ZooKeeper | `spring.cloud.zookeeper.discovery.order` |
| Simple | `spring.cloud.discovery.client.simple.order` |

Với implementation tùy chỉnh, override `getOrder()`:

```java
public final class InternalDiscoveryClient implements DiscoveryClient {

    @Override
    public int getOrder() {
        // Số nhỏ hơn sẽ được composite xét trước.
        return -20;
    }

    // description(), getInstances() và getServices()
    // được triển khai theo nguồn dữ liệu nội bộ.
}
```

Đặt order chỉ quyết định thứ tự điều phối giữa các client. Nó không sắp xếp instance bên trong một danh sách và cũng không quyết định thuật toán chọn instance của Spring Cloud LoadBalancer.

## 3. CompositeDiscoveryClient blocking hoạt động như thế nào?

API blocking `org.springframework.cloud.client.discovery.DiscoveryClient` trả về `List<ServiceInstance>`. Composite dùng danh sách các client đã được sắp theo order để thực hiện truy vấn.

Với `getInstances(serviceId)`, composite lần lượt hỏi từng client:

1. Gọi `getInstances(serviceId)` trên client có order cao nhất.
2. Nếu kết quả có instance, trả về danh sách đó và dừng truy vấn các client còn lại.
3. Nếu kết quả rỗng, tiếp tục hỏi client kế tiếp.
4. Nếu tất cả đều trả về rỗng, kết quả cuối cùng là danh sách rỗng.

Ví dụ:

| Thứ tự | Nguồn | Kết quả cho `payment-service` |
|---:|---|---|
| `-10` | Eureka | Rỗng |
| `0` | Consul | `payment-1`, `payment-2` |
| `20` | Registry nội bộ | `payment-3` |

Kết quả của composite chỉ gồm `payment-1` và `payment-2`. Khi Consul đã trả danh sách không rỗng, client có order `20` không được hỏi. Danh sách từ Eureka và Consul cũng không được nối lại.

Với `getServices()`, composite tổng hợp các service ID mà những client thành phần biết đến. Vì vậy, service enumeration có thể cho thấy một service tồn tại ở nhiều registry, trong khi `getInstances(serviceId)` chỉ trả danh sách của nguồn đầu tiên có instance.

### 3.1. Thứ tự không phải cơ chế fallback cho mọi loại lỗi

Fallback theo thứ tự xảy ra khi client ưu tiên trả về danh sách rỗng. Không nên giả định một lỗi kết nối tới registry cũng tương đương với danh sách rỗng. Nếu một implementation ném exception trong lúc truy vấn, exception có thể thoát khỏi lời gọi composite và làm luồng truy vấn dừng trước khi client tiếp theo được hỏi.

Điều này đặc biệt quan trọng khi chạy song song Eureka và Consul. Nếu Eureka được ưu tiên nhưng Eureka đang mất kết nối, việc đặt Consul ở order thấp hơn tự nó không tạo thành cơ chế failover khi exception xảy ra. Cần xác định rõ adapter trả về rỗng, ném lỗi hay dùng cache khi registry không truy cập được; nếu cần chịu lỗi, hãy thiết kế chính sách timeout, cache hoặc wrapper có kiểm soát và kiểm thử hành vi đó.

Không biến lỗi thành danh sách rỗng một cách mù quáng. Danh sách rỗng có thể có nghĩa service thực sự chưa đăng ký; che exception thành rỗng có thể làm mất dấu một sự cố registry.

## 4. ReactiveCompositeDiscoveryClient có hành vi mặc định khác

API reactive `ReactiveDiscoveryClient` trả về `Flux<ServiceInstance>` và `Flux<String>`. Với nhiều reactive discovery clients, composite mặc định ưu tiên client trả kết quả không rỗng nhanh nhất. Vì vậy, thứ tự `Ordered` không đồng nghĩa với việc composite luôn chờ client có order nhỏ nhất.

Spring Cloud Commons cung cấp hai thuộc tính để thay đổi hành vi này:

| Thuộc tính | Mặc định | Hành vi |
|---|---|---|
| `spring.cloud.discovery.reactive.order-enforced` | `false` | Nếu bật, chỉ đăng ký truy vấn client ưu tiên thấp hơn sau khi các client ưu tiên cao hơn trả về không có instance |
| `spring.cloud.discovery.reactive.combine-instances` | `false` | Nếu bật, gộp instance từ tất cả reactive discovery clients thay vì chỉ dùng kết quả của một client |

### 4.1. Ép reactive lookup theo thứ tự

```yaml
spring:
  cloud:
    discovery:
      reactive:
        order-enforced: true
        combine-instances: false
```

Với `order-enforced: true`, client ưu tiên thấp hơn chỉ được subscribe khi mọi client có ưu tiên cao hơn không trả về instance. Đây là hành vi fallback theo thứ tự gần với blocking composite.

Đổi lại, một client ưu tiên cao phản hồi rất chậm hoặc không kết thúc có thể trì hoãn kết quả từ client phía sau. Theo tài liệu Spring Cloud Commons, lỗi từ client đang được hỏi sẽ được propagate; composite không tự coi lỗi đó là tín hiệu để chuyển sang client kế tiếp.

### 4.2. Gộp instance từ nhiều reactive clients

```yaml
spring:
  cloud:
    discovery:
      reactive:
        order-enforced: false
        combine-instances: true
```

Với `combine-instances: true`, kết quả từ các client được kết hợp. Lỗi ở một client được ghi log và không ngăn kết quả từ các client khác được trả về. Nếu đồng thời bật `order-enforced: true`, các client được truy vấn theo order đã cấu hình trong khi kết quả vẫn được gộp.

`getServices()` của reactive composite tiếp tục tổng hợp danh sách service từ các client; `order-enforced` chỉ ảnh hưởng tới truy vấn instance. Vì vậy, không dùng riêng kết quả liệt kê service để suy ra registry nào đã cung cấp instance cho một request.

Việc gộp nhiều registry có thể tạo instance trùng về mặt logic nếu cùng một endpoint được đăng ký ở nhiều nơi. Không giả định composite tự đồng nhất hai record chỉ vì host và port giống nhau. Nếu cần gộp, hãy xác định quy tắc định danh instance, metadata nguồn và cách loại trùng trước khi đưa danh sách vào load balancer.

## 5. So sánh hành vi blocking và reactive

| Tình huống | Blocking `CompositeDiscoveryClient` | Reactive `ReactiveCompositeDiscoveryClient` mặc định |
|---|---|---|
| Thứ tự truy vấn instance | Theo `Ordered` | Cạnh tranh; client trả non-empty nhanh nhất thắng |
| Client ưu tiên trả danh sách rỗng | Hỏi client tiếp theo | Kết quả rỗng không thắng; chờ client khác nếu còn kết quả |
| Có thể ép fallback theo order | Đã theo order | Có, bật `order-enforced` |
| Có thể gộp instance từ mọi registry | Không phải hành vi của `getInstances` mặc định | Có, bật `combine-instances` |
| Liệt kê service ID | Tổng hợp từ các client thành phần | Tổng hợp từ các client thành phần |
| Client ném lỗi | Không nên giả định lỗi tương đương kết quả rỗng; cần kiểm tra implementation và xử lý | Khi ép order, lỗi được propagate; khi combine, lỗi từng client được log và các nguồn khác vẫn có thể trả kết quả |

Chọn API theo mô hình ứng dụng và hiểu rõ chính sách tổng hợp. Không cấu hình `order-enforced` hoặc `combine-instances` rồi giả định chúng cũng thay đổi hành vi của blocking `DiscoveryClient`.

## 6. SimpleDiscoveryClient: nguồn instance tĩnh

`SimpleDiscoveryClient` đọc instance từ cấu hình thay vì hỏi một registry từ xa. Spring Cloud dùng nó khi không có `DiscoveryClient` dựa trên service registry trong classpath. Cơ chế này hữu ích cho môi trường local, demo hoặc kiểm thử tích hợp đơn giản.

Ví dụ khai báo hai instance cho `catalog-service`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Trong dạng property, cùng cấu hình được biểu diễn như sau:

```properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://localhost:8082
```

`SimpleDiscoveryClient` không tự kiểm tra endpoint có thực sự khỏe hay không và không tự cập nhật khi instance thay đổi. Nếu dùng nó làm nguồn discovery, cần quản lý cấu hình và vòng đời instance bằng quy trình triển khai. Đừng nhầm `SimpleDiscoveryClient` với một registry có heartbeat hoặc health check.

Thuộc tính `spring.cloud.discovery.client.simple.order` xác định order của Simple client khi implementation này tham gia danh sách composite. Tuy nhiên, Simple client chủ yếu là lựa chọn thay thế khi không có registry-backed client; không nên dựa vào nó như một registry dự phòng tự động bên cạnh Eureka/Consul nếu chưa xác minh bean thực tế trong application context.

## 7. CompositeDiscoveryClient không phải Composite Health Indicator

Có hai khái niệm tên gần giống nhau nhưng phục vụ mục đích khác:

- `CompositeDiscoveryClient` điều phối việc đọc service và instance từ nhiều `DiscoveryClient`.
- `DiscoveryCompositeHealthContributor` tổng hợp các bean `DiscoveryHealthIndicator` để báo trạng thái sức khỏe của các thành phần discovery.

Composite health contributor được bật mặc định khi có các health indicator phù hợp. Có thể tắt bằng:

```yaml
spring:
  cloud:
    discovery:
      client:
        composite-indicator:
          enabled: false
```

`DiscoveryClientHealthIndicator` mặc định gọi `getServices()` để kiểm tra client và đưa danh sách service vào health details. Trong môi trường có rất nhiều service, thao tác này có thể tốn kém; có thể chuyển sang `probe()` nhẹ hơn:

```yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          use-services-query: false
```

Điều chỉnh health indicator không thay đổi thứ tự hoặc chính sách tổng hợp instance của `CompositeDiscoveryClient`. Tương tự, một health indicator báo `UP` không đảm bảo service cụ thể mà consumer đang gọi có instance khỏe.

## 8. Discovery và đăng ký service là hai hướng riêng

`DiscoveryClient` đọc instance. `ServiceRegistry` đăng ký hoặc hủy đăng ký instance. Khi một ứng dụng có nhiều discovery integration, cần kiểm tra cả hai hướng:

- Consumer có thể truy vấn nhiều registry thông qua composite.
- Producer có thể được auto-register với một hoặc nhiều `ServiceRegistry` tùy các starter và cấu hình đang hoạt động.

Việc có hai `DiscoveryClient` không tự đảm bảo service được đăng ký vào cả hai registry. Ngược lại, nếu nhiều cơ chế auto-registration cùng hoạt động, service có thể được đăng ký ở nhiều nơi. Đây là quyết định triển khai riêng, cần được xác nhận bằng log registration và catalog của từng registry.

Spring Cloud Commons cho phép tắt auto-registration chung bằng:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

Cũng có thể cấu hình `@EnableDiscoveryClient(autoRegister = false)` trong các trường hợp còn sử dụng annotation đó. Tắt auto-registration không tắt khả năng đọc instance bằng `DiscoveryClient`; hai chức năng này độc lập.

## 9. Tích hợp với Spring Cloud LoadBalancer

Discovery trả về danh sách `ServiceInstance`; LoadBalancer chọn một instance trong danh sách để gửi request. Hai bước này khác nhau:

1. Composite discovery quyết định danh sách instance được lấy từ nguồn nào hoặc kết hợp ra sao.
2. Spring Cloud LoadBalancer áp dụng thuật toán chọn instance trên danh sách mà `ServiceInstanceListSupplier` cung cấp.

Ví dụ, nếu blocking composite chọn Consul vì Eureka trả rỗng, LoadBalancer sẽ chọn instance trong danh sách Consul. Thay đổi `eureka.client.order` không biến thuật toán round-robin thành thuật toán khác và cũng không làm LoadBalancer tự gộp instance từ các registry.

Nếu muốn cân bằng trên instance của nhiều registry, hãy xác định rõ cách tổng hợp trước khi LoadBalancer nhận danh sách. Với reactive composite, `combine-instances` là tùy chọn gộp có sẵn. Với blocking API, có thể cần một implementation tổng hợp tùy chỉnh nếu use case yêu cầu union; khi đó cần giải quyết duplicate, metadata, zone, health và nguồn gốc instance.

## 10. Kiểm tra thứ tự và kết quả trong ứng dụng

Trước khi bật nhiều discovery starter ở production, kiểm tra bean thực tế trong application context. Ví dụ, có thể liệt kê tên bean và order của từng client:

```java
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@Configuration
class DiscoveryDiagnostics {

    @Bean
    ApplicationRunner logDiscoveryClients(
            Map<String, DiscoveryClient> clients) {
        return args -> clients.forEach((name, client) ->
            System.out.printf("%s -> %s, order=%d%n",
                name, client.description(), client.getOrder()));
    }
}
```

Trong cấu hình có composite, map bean có thể bao gồm cả composite và các client thành phần. Khi xem thứ tự, hãy phân biệt bean composite với các implementation thực sự gọi registry. Không gọi `getInstances()` trên tất cả client rồi cộng kết quả trong code production nếu chưa có chính sách loại trùng và xử lý lỗi.

Có thể kiểm tra truy vấn qua abstraction được inject:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class CatalogLookup {

    private final DiscoveryClient discoveryClient;

    CatalogLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
```

Trong ứng dụng dùng auto-configuration mặc định, injection theo type thường nhận composite `@Primary`. Nếu cần gọi một registry cụ thể để chẩn đoán, inject bean theo qualifier hoặc truy cập bean map có tên rõ ràng; tránh thay đổi `@Primary` toàn cục chỉ để phục vụ một phép kiểm tra.

## 11. Quy trình triển khai nhiều registry an toàn

1. Xác định mục đích: fallback theo thứ tự, chọn một nguồn ưu tiên hay gộp instance từ nhiều registry.
2. Chọn API blocking hoặc reactive theo stack của ứng dụng; đọc đúng hành vi composite tương ứng.
3. Đặt order khác nhau cho các client cần ưu tiên rõ ràng và kiểm tra property prefix đúng với starter.
4. Quyết định producer sẽ đăng ký ở registry nào; xác minh auto-registration độc lập với lookup.
5. Quy định service ID, instance ID, metadata, zone và chính sách loại trùng trong giai đoạn di chuyển.
6. Đặt timeout và chính sách lỗi cho từng registry; xác định trường hợp trả danh sách rỗng và trường hợp ném exception.
7. Kiểm tra cache của registry, cache discovery và cache LoadBalancer để hiểu độ trễ cập nhật.
8. Thử khi registry ưu tiên trả rỗng, phản hồi chậm, mất kết nối hoặc ném exception.
9. Thử khi service chỉ có ở registry thứ hai và khi cùng service xuất hiện ở cả hai registry.
10. Theo dõi nguồn instance được chọn, tỷ lệ lỗi theo registry, thời gian truy vấn và số lần fallback.

## 12. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
|---|---|---|
| Client không chạy theo thứ tự mong muốn | Dùng sai property prefix hoặc các client có cùng order | Kiểm tra config properties và log `getOrder()` của từng bean; đặt order khác nhau |
| Eureka có instance nhưng composite trả instance từ Consul | Consul có order cao hơn theo thứ tự ưu tiên hoặc Eureka trả rỗng | Kiểm tra `eureka.client.order`, `spring.cloud.consul.discovery.order` và kết quả từng registry |
| Registry ưu tiên lỗi khiến nguồn sau không được hỏi | Client ném exception thay vì trả danh sách rỗng; blocking composite không phải circuit breaker | Kiểm tra exception, timeout và failure policy của adapter; bổ sung fallback có kiểm soát |
| Cùng service xuất hiện trong `getServices()` nhưng instance trả về chỉ từ một registry | Service enumeration tổng hợp; blocking instance lookup dừng ở client đầu tiên có kết quả | Kiểm tra từng registry và nhớ rằng hai method có ngữ nghĩa khác nhau |
| Reactive lookup trả kết quả từ registry phản hồi nhanh hơn | Mặc định reactive composite chọn fastest non-empty | Bật `spring.cloud.discovery.reactive.order-enforced=true` nếu cần ép thứ tự |
| Reactive lookup chậm hoặc lỗi không fallback | `order-enforced` chờ client ưu tiên cao; lỗi được propagate | Kiểm tra latency/timeout và chính sách lỗi; cân nhắc `combine-instances` nếu muốn tổng hợp |
| Instance trùng khi gộp registry | Cùng endpoint được đăng ký nhiều nơi hoặc instance ID không thống nhất | Thiết kế quy tắc định danh và loại trùng trước khi LoadBalancer nhận danh sách |
| Service được đăng ký ở nhiều registry ngoài dự kiến | Nhiều auto-registration integration cùng hoạt động | Kiểm tra `ServiceRegistry`, sự kiện registration và cấu hình bật/tắt của từng integration |

## 13. Checklist

- [ ] Đã xác định tất cả `DiscoveryClient` bean được tạo trong application context.
- [ ] Đã đặt order khác nhau cho những registry cần ưu tiên rõ ràng.
- [ ] Đã xác định đang dùng blocking hay reactive composite.
- [ ] Đã hiểu blocking lookup trả danh sách đầu tiên không rỗng, còn reactive mặc định chọn kết quả không rỗng nhanh nhất.
- [ ] Nếu dùng reactive, đã chọn rõ `order-enforced` và `combine-instances` theo mục tiêu.
- [ ] Đã kiểm tra cách từng client biểu diễn lỗi registry: rỗng, exception hay cache.
- [ ] Đã phân biệt `getServices()` với `getInstances(serviceId)`.
- [ ] Đã quyết định producer đăng ký vào registry nào và kiểm tra auto-registration.
- [ ] Đã kiểm soát duplicate, metadata, zone và instance ID nếu gộp nguồn.
- [ ] Đã kiểm tra danh sách instance thực tế mà LoadBalancer nhận được.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions, DiscoveryClient ordering và reactive composite](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons — DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java)
- [Spring Cloud Commons — CompositeDiscoveryClient auto-configuration](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/composite/CompositeDiscoveryClientAutoConfiguration.java)
