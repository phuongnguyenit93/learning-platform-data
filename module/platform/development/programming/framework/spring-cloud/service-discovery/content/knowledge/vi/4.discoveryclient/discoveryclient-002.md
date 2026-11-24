# Lấy các ServiceInstance bằng getInstances(serviceId)

Trong kiến trúc microservice, một consumer thường chỉ biết tên logic của dịch vụ cần gọi, ví dụ `order-service`. Số lượng instance, host và port có thể thay đổi khi hệ thống scale, triển khai phiên bản mới hoặc thay thế một container bị lỗi. Consumer vì vậy cần một cơ chế tra cứu địa chỉ đang được công bố trong Service Registry.

Spring Cloud cung cấp interface `DiscoveryClient` để thực hiện thao tác khám phá dịch vụ. Phương thức `getInstances(serviceId)` nhận tên dịch vụ và trả về danh sách `ServiceInstance` tương ứng. Bài học này giải thích hợp đồng của phương thức, cách đọc thông tin từng instance, cách xử lý kết quả rỗng và cách kết hợp discovery với load balancing trong ứng dụng Spring Cloud.

## 1. DiscoveryClient trong luồng Service Discovery

`DiscoveryClient` thuộc package `org.springframework.cloud.client.discovery`. Nó là abstraction phía consumer, cho phép ứng dụng tra cứu instance mà không cần gọi trực tiếp API riêng của Eureka, Consul hoặc registry khác.

Một luồng điển hình gồm các bước:

1. Provider khởi động và đăng ký instance của mình với registry.
2. Registry lưu thông tin service ID, host, port và metadata của instance.
3. Consumer gọi `DiscoveryClient.getInstances(serviceId)` để lấy các instance được công bố cho service ID đó.
4. Consumer hoặc Spring Cloud LoadBalancer chọn một instance phù hợp để gửi request.

```mermaid
flowchart LR
    P[Provider: order-service] -->|Đăng ký instance| R[(Service Registry)]
    C[Consumer: payment-service] -->|getInstances("order-service")| D[DiscoveryClient]
    D -->|Tra cứu| R
    R -->|Danh sách ServiceInstance| D
    D --> C
    C -->|Chọn instance / gọi dịch vụ| O[order-service instance]
```

`DiscoveryClient` chịu trách nhiệm tra cứu. Nó không phải là registry, không đăng ký provider và cũng không tự thực hiện load balancing cho từng request. Việc chọn instance có thể do ứng dụng tự quyết định hoặc được giao cho Spring Cloud LoadBalancer.

## 2. Hợp đồng getInstances(serviceId)

Trong Spring Cloud Commons, phần cốt lõi của `DiscoveryClient` có dạng:

```java
package org.springframework.cloud.client.discovery;

import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.core.Ordered;

public interface DiscoveryClient extends Ordered {

    String description();

    List<ServiceInstance> getInstances(String serviceId);

    List<String> getServices();
}
```

Điểm cần tập trung là chữ ký:

```java
List<ServiceInstance> getInstances(String serviceId);
```

- `serviceId` là tên logic của dịch vụ cần tra cứu, ví dụ `order-service`.
- Giá trị trả về là một danh sách `ServiceInstance`; mỗi phần tử mô tả một instance có thể được khám phá.
- Nếu không có instance phù hợp, kết quả thường là danh sách rỗng. Consumer phải kiểm tra trường hợp này trước khi truy cập phần tử đầu tiên.
- Hợp đồng chung không bảo đảm thứ tự phần tử, thời gian cập nhật tức thời hay việc endpoint vẫn khỏe tại đúng thời điểm consumer gửi request.

`getServices()` trả về các service ID mà implementation có thể nhìn thấy. Phương thức này hữu ích khi chẩn đoán sai tên dịch vụ. `description()` cung cấp mô tả implementation. Cả hai không thay thế cho việc gọi `getInstances(serviceId)` khi cần lấy địa chỉ instance.

### 2.1. serviceId là tên logic, không phải địa chỉ mạng

Consumer truyền tên dịch vụ, không truyền URL, IP hoặc port:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("order-service");
```

Registry ánh xạ tên logic đó sang một hoặc nhiều instance. Ví dụ, `order-service` có thể tương ứng với `10.0.1.21:8080`, `10.0.1.22:8080` và `10.0.2.15:8080`.

Service ID phải khớp với tên mà provider đã công bố. Quy tắc chuẩn hóa chữ hoa/chữ thường, alias hoặc cách ánh xạ tên có thể phụ thuộc vào registry và implementation. Vì vậy, các service nên thống nhất một tên định danh ổn định và consumer nên dùng chính tên đó thay vì tự suy đoán cách viết.

Không truyền tên class Java, tên bean Spring, tên database hay hostname của một instance vào `getInstances`, trừ khi hệ thống chủ động dùng chính chuỗi đó làm service ID. Service ID đại diện cho dịch vụ logic, còn hostname và port là thuộc tính của từng instance.

### 2.2. Danh sách có thể chứa nhiều instance

Giả sử registry đang ghi nhận ba instance:

| Service ID | Host | Port | Metadata |
|---|---|---:|---|
| `order-service` | `10.0.1.21` | 8080 | `zone=zone-a` |
| `order-service` | `10.0.1.22` | 8080 | `zone=zone-a` |
| `order-service` | `10.0.2.15` | 8080 | `zone=zone-b` |

Khi gọi `getInstances("order-service")`, consumer có thể nhận ba đối tượng `ServiceInstance`. Số lượng này có thể thay đổi sau mỗi lần tra cứu do scale up, scale down, deploy hoặc health check. Không nên lưu cố định một danh sách instance trong code hoặc giả định một service luôn có đúng một địa chỉ.

## 3. Đọc thông tin từ ServiceInstance

`ServiceInstance` thuộc package `org.springframework.cloud.client`. Đây là abstraction mô tả một instance của dịch vụ. Một số thông tin thường dùng gồm:

| Phương thức | Ý nghĩa |
|---|---|
| `getServiceId()` | Service ID mà instance thuộc về. |
| `getHost()` | Host hoặc địa chỉ mạng của instance. |
| `getPort()` | Cổng nhận kết nối của instance. |
| `isSecure()` | Cho biết instance sử dụng kết nối bảo mật hay không. |
| `getUri()` | URI truy cập instance, được tạo từ thông tin địa chỉ và giao thức. |
| `getMetadata()` | Metadata dạng key-value do provider hoặc registry cung cấp. |

Ví dụ, một instance có thể cung cấp các giá trị:

```text
serviceId = order-service
host      = order-7.internal
port      = 8080
secure    = false
uri       = http://order-7.internal:8080
metadata  = {
  zone: "zone-b",
  version: "v2"
}
```

Consumer có thể dùng `getUri()` để biết địa chỉ cơ sở hoặc dùng các thuộc tính riêng lẻ để áp dụng quy tắc định tuyến. Không nên ghép chuỗi host và port thủ công nếu đã có `getUri()`, vì cách tạo URI còn liên quan đến giao thức và có thể có quy tắc riêng của implementation.

Metadata có thể giúp consumer lọc instance theo zone, phiên bản hoặc nhóm triển khai. Tuy nhiên, việc metadata có mặt trong đối tượng không tự động kích hoạt chính sách định tuyến. Ứng dụng hoặc bộ lọc phải chủ động đọc và áp dụng các giá trị đó.

## 4. Gọi getInstances trong ứng dụng Spring Boot

Ứng dụng có thể inject `DiscoveryClient` thông qua constructor injection. Ví dụ sau minh họa một thành phần tra cứu các địa chỉ của `order-service`:

```java
package com.example.payment.discovery;

import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class OrderServiceLocator {

    private static final String ORDER_SERVICE_ID = "order-service";

    private final DiscoveryClient discoveryClient;

    public OrderServiceLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findOrderServiceUris() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances(ORDER_SERVICE_ID);

        return instances.stream()
                .map(ServiceInstance::getUri)
                .collect(Collectors.toList());
    }
}
```

Ví dụ chỉ thực hiện tra cứu và chuyển danh sách instance thành danh sách URI. Nó chưa gửi HTTP request và cũng chưa chọn một instance để phục vụ request. Việc tách riêng hai bước giúp code thể hiện rõ trách nhiệm của discovery và trách nhiệm gọi dịch vụ.

Để `DiscoveryClient` hoạt động, ứng dụng cần dependency và cấu hình tích hợp với registry phù hợp. Chỉ khai báo interface hoặc inject thành công không có nghĩa provider đã đăng ký đúng hay registry đang có dữ liệu. Cần xác minh implementation thực tế được Spring tạo và kết nối tới registry.

### 4.1. Duyệt và quan sát danh sách instance

Trong giai đoạn kiểm tra hệ thống, có thể ghi log những thuộc tính cần thiết:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("order-service");

if (instances.isEmpty()) {
    log.warn("No instances found for serviceId={}", "order-service");
} else {
    for (ServiceInstance instance : instances) {
        log.info("serviceId={}, host={}, port={}, secure={}, uri={}",
                instance.getServiceId(),
                instance.getHost(),
                instance.getPort(),
                instance.isSecure(),
                instance.getUri());
    }
}
```

Trong môi trường production, log nên tránh ghi metadata nhạy cảm hoặc dữ liệu có thể chứa thông tin nội bộ không cần thiết. Nên ưu tiên metric về số lượng instance, lỗi tra cứu và thời gian xử lý; chỉ ghi địa chỉ cụ thể khi chính sách vận hành cho phép.

## 5. Xử lý danh sách rỗng và lỗi tra cứu

Một consumer cần phân biệt ít nhất ba tình huống:

1. **Tra cứu thành công và có instance:** có thể tiếp tục bước chọn instance hoặc chuyển danh sách cho LoadBalancer.
2. **Tra cứu thành công nhưng danh sách rỗng:** hiện không có instance nào được trả về cho service ID đó.
3. **Tra cứu thất bại:** implementation gặp lỗi khi truy cập registry, đọc dữ liệu hoặc xử lý yêu cầu. Tùy implementation, lỗi có thể được biểu diễn bằng exception runtime hoặc cơ chế lỗi riêng.

Danh sách rỗng không nhất thiết chứng minh registry đang hỏng. Nguyên nhân có thể là provider chưa đăng ký, service ID sai, instance bị loại bởi health check, registry chưa đồng bộ hoặc ứng dụng đang dùng một namespace/partition khác.

Ví dụ xử lý kết quả rỗng ở tầng nghiệp vụ:

```java
public List<ServiceInstance> requireOrderInstances() {
    List<ServiceInstance> instances =
            discoveryClient.getInstances("order-service");

    if (instances.isEmpty()) {
        throw new IllegalStateException(
                "No available instances for order-service");
    }

    return instances;
}
```

Đây là cách minh họa để làm rõ điều kiện. Trong ứng dụng web thực tế, nên chuyển tình huống phụ thuộc không khả dụng thành phản hồi phù hợp, thường là `503 Service Unavailable`, hoặc để cơ chế retry/circuit breaker ở tầng gọi dịch vụ xử lý theo chính sách của hệ thống. Không nên trả `404 Not Found` chỉ vì một dịch vụ nội bộ không có instance; `404` thường diễn tả tài nguyên mà client yêu cầu không tồn tại.

Không nên tự động chuyển mọi exception thành danh sách rỗng. Nếu làm vậy, ứng dụng sẽ mất khả năng phân biệt “không có instance” với “không liên lạc được registry”, khiến việc giám sát và chẩn đoán sai lệch. Hãy ghi nhận lỗi tra cứu riêng và áp dụng timeout, retry có giới hạn cùng backoff phù hợp với implementation.

## 6. Không nhầm discovery với load balancing

`getInstances(serviceId)` trả về danh sách instance. Nó không cam kết chọn instance theo round-robin, least connections hay thuật toán nào khác. Thứ tự danh sách không phải hợp đồng load balancing; lấy `instances.get(0)` không phải một chiến lược cân bằng tải đáng tin cậy.

Nếu tự chọn instance, ứng dụng phải tự chịu trách nhiệm về phân phối request, xử lý instance chết, cập nhật danh sách, retry, timeout và các quy tắc vùng. Đây là lượng logic vận hành lớn và dễ tạo ra các hành vi không nhất quán giữa các consumer.

Với lời gọi HTTP theo service ID, nên cân nhắc Spring Cloud LoadBalancer. Ví dụ dùng `RestTemplate` được đánh dấu `@LoadBalanced`:

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate orderRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
```

Sau đó, consumer có thể gọi bằng service ID trong hostname:

```java
String response = orderRestTemplate.getForObject(
        "http://order-service/api/orders/42",
        String.class);
```

Với cấu hình LoadBalancer tương ứng, Spring Cloud chuyển service ID thành một instance được chọn từ danh sách discovery trước khi gửi request. Dependency và cách cấu hình cụ thể phụ thuộc phiên bản Spring Boot/Spring Cloud đang sử dụng. Nếu ứng dụng dùng `WebClient` hoặc `RestClient`, hãy dùng tích hợp LoadBalancer tương ứng của phiên bản đó.

`DiscoveryClient` vẫn hữu ích khi ứng dụng cần quan sát danh sách instance, kiểm tra metadata, xây dựng công cụ quản trị hoặc triển khai một quy tắc khám phá đặc thù. Đối với request thông thường, nên để thành phần load balancing chuyên trách chọn instance.

## 7. Quan hệ với Eureka, Consul và các implementation khác

`DiscoveryClient` là abstraction của Spring Cloud Commons. Starter hoặc integration cụ thể cung cấp implementation để nói chuyện với registry. Consumer có thể giữ cách gọi `getInstances(serviceId)` trong khi phần triển khai bên dưới thay đổi.

| Registry / implementation | Vai trò khi gọi getInstances |
|---|---|
| Eureka | Tra cứu các instance được Eureka client/registry ghi nhận cho service ID tương ứng. |
| Consul | Tra cứu các service instance từ dữ liệu catalog và trạng thái health theo cấu hình tích hợp. |
| Simple Discovery Client | Cung cấp danh sách instance từ cấu hình tĩnh, hữu ích cho môi trường đơn giản hoặc kiểm thử. |

Abstraction không làm cho hành vi của mọi registry giống hệt nhau. Các điểm sau cần được kiểm tra theo implementation:

- Service ID được chuẩn hóa hoặc ánh xạ như thế nào.
- Registry trả về tất cả instance hay chỉ instance đạt điều kiện health cụ thể.
- Client có cache danh sách instance hay không và chu kỳ cập nhật là bao lâu.
- Dữ liệu metadata được chuyển đổi ra sao.
- Lỗi kết nối registry, timeout và retry được biểu diễn như thế nào.
- Có nhiều `DiscoveryClient` cùng tồn tại hay một lớp tổng hợp kết quả hay không.

Do đó, khi chuyển từ Eureka sang Consul, code gọi abstraction có thể ít thay đổi nhưng vẫn cần kiểm thử hành vi, cấu hình và chính sách sức khỏe của registry mới.

## 8. Cache, độ mới dữ liệu và tính nhất quán

Không nên giả định mỗi lần gọi `getInstances` đều gửi một request mạng trực tiếp tới server registry. Một implementation có thể giữ bản sao cục bộ, nhận cập nhật định kỳ hoặc dùng cache ở tầng client. Spring Cloud LoadBalancer cũng có thể sử dụng cache cho danh sách instance tùy cấu hình và phiên bản.

Hệ quả là danh sách trả về có thể trễ hơn trạng thái thực tế trong một khoảng thời gian. Ví dụ, một instance vừa bị dừng nhưng vẫn xuất hiện trong cache; hoặc một instance vừa đăng ký chưa xuất hiện ở consumer. Đây là lý do discovery không thay thế health check và timeout của request.

Khi điều tra dữ liệu cũ, hãy xác định rõ các tầng có thể giữ cache: registry server, registry client, DiscoveryClient adapter, LoadBalancer supplier và cache do ứng dụng tự tạo. Tránh thêm một cache riêng nếu chưa hiểu cache hiện có; nhiều tầng cache có thể làm tăng độ trễ khi cập nhật hoặc gỡ instance.

Consumer vẫn cần xử lý trường hợp kết nối tới instance vừa trở nên không khả dụng. Dùng timeout hợp lý, retry có giới hạn cho thao tác an toàn khi retry, circuit breaker khi phù hợp và quan sát lỗi kết nối theo từng service ID.

## 9. Metadata và lựa chọn instance theo ngữ cảnh

Mỗi `ServiceInstance` có thể mang metadata do provider công bố. Ví dụ, consumer muốn ưu tiên instance cùng vùng triển khai:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("order-service");

List<ServiceInstance> sameZone = instances.stream()
        .filter(instance -> "zone-a".equals(
                instance.getMetadata().get("zone")))
        .collect(Collectors.toList());
```

Đoạn mã minh họa lọc dữ liệu; nó chưa phải một thuật toán load balancing hoàn chỉnh. Nếu `sameZone` rỗng, ứng dụng cần xác định có fallback sang zone khác hay báo không có instance. Quy tắc này nên được cấu hình nhất quán và kiểm thử, tránh âm thầm bỏ qua tất cả instance.

Metadata có thể thiếu, sai định dạng hoặc không đồng nhất giữa các phiên bản provider. Luôn xử lý giá trị null/thiếu và thống nhất tên khóa. Không đưa secret, token hoặc thông tin xác thực vào metadata; dữ liệu này thường được lưu trong registry và có thể được nhiều thành phần đọc.

## 10. Bảo mật khi sử dụng kết quả discovery

Kết quả discovery ảnh hưởng trực tiếp đến nơi consumer gửi request. Vì vậy:

1. Chỉ tra cứu các service ID nội bộ mà thành phần được phép gọi; không dùng chuỗi tùy ý từ request bên ngoài làm service ID.
2. Bảo vệ kết nối giữa provider, consumer và registry bằng xác thực, phân quyền và TLS theo yêu cầu môi trường.
3. Tôn trọng `isSecure()` và URI mà `ServiceInstance` cung cấp; không tự hạ kết nối HTTPS thành HTTP.
4. Không coi metadata là dữ liệu đáng tin tuyệt đối. Xác thực các giá trị dùng trong quyết định định tuyến.
5. Áp dụng network policy để consumer chỉ truy cập được những dịch vụ và cổng cần thiết.
6. Không trả toàn bộ danh sách host, port và metadata nội bộ cho người dùng cuối hoặc API công khai nếu không có nhu cầu rõ ràng.

Service Discovery cung cấp địa chỉ và ngữ cảnh của instance. Nó không thay thế xác thực giữa các service, phân quyền nghiệp vụ hoặc kiểm tra quyền truy cập ở endpoint đích.

## 11. Các lỗi thường gặp khi gọi getInstances

### Danh sách luôn rỗng

Kiểm tra service ID có khớp với tên provider đăng ký không, provider đã bật registration chưa, registry có bản ghi không và consumer có đang kết nối đúng cluster, namespace hoặc datacenter không. Dùng `getServices()` để xem các tên service mà client hiện nhìn thấy, đồng thời kiểm tra dashboard và log của registry.

### Danh sách có instance nhưng request thất bại

Discovery chỉ cung cấp thông tin instance theo registry/client. Host có thể không phân giải được từ mạng consumer, port có thể bị firewall chặn hoặc ứng dụng chưa sẵn sàng. Kiểm tra `getUri()`, DNS, routing, network policy, TLS và health check. Bổ sung timeout và xử lý lỗi ở HTTP client.

### Chỉ có một instance dù provider đang scale nhiều bản

Kiểm tra từng provider có đăng ký với instance ID riêng hay không, registry có nhận đủ bản ghi không và implementation có lọc theo trạng thái hoặc zone không. Cũng cần kiểm tra cache và thời gian đồng bộ ở consumer.

### Instance cũ vẫn xuất hiện sau khi deploy

Có thể provider chưa deregister đúng lifecycle, tiến trình bị dừng đột ngột hoặc cache chưa được làm mới. Kiểm tra graceful shutdown, heartbeat/TTL, health check và các tầng cache. Không xóa bản ghi thủ công nếu chưa xác định cơ chế sở hữu và tự phục hồi của registry.

### Consumer dùng sai service ID

Đối chiếu tên trong cấu hình provider, tên trong registry và hằng số consumer truyền vào `getInstances`. Không suy luận tên service ID từ tên package hoặc tên class. Nên tập trung service ID vào cấu hình/hằng số dùng chung phù hợp với kiến trúc dự án.

## 12. Checklist trước khi đưa discovery vào production

| Hạng mục | Câu hỏi cần xác minh |
|---|---|
| Dependency | Ứng dụng đã có starter và implementation DiscoveryClient đúng chưa? |
| Service ID | Provider và consumer có dùng cùng service ID không? |
| Registration | Provider có xuất hiện trong registry với host/port hợp lệ không? |
| Kết quả rỗng | Consumer có xử lý danh sách rỗng và phản hồi dependency unavailable không? |
| Nhiều instance | Hệ thống có xử lý được danh sách thay đổi khi scale không? |
| Load balancing | Việc chọn instance có dùng chiến lược rõ ràng và có kiểm thử không? |
| Health | Có phối hợp readiness, health check, heartbeat và deregistration không? |
| Cache | Đã hiểu thời gian cập nhật của registry client và LoadBalancer chưa? |
| Resilience | Có timeout, retry có giới hạn và circuit breaker phù hợp không? |
| Security | Service ID, metadata, kết nối registry và endpoint có được bảo vệ không? |
| Observability | Có metric/log để phân biệt không có instance với lỗi truy cập registry không? |

## Kết luận

`DiscoveryClient.getInstances(serviceId)` là thao tác tra cứu các instance theo tên dịch vụ trong Spring Cloud. Phương thức nhận service ID và trả về `List<ServiceInstance>`; mỗi phần tử cung cấp thông tin địa chỉ cùng metadata của một instance. Consumer phải xử lý danh sách rỗng, hiểu rằng dữ liệu có thể trễ và không giả định thứ tự danh sách là chính sách cân bằng tải.

Trong ứng dụng microservice, hãy dùng `DiscoveryClient` khi cần tra cứu hoặc quan sát instance. Với lời gọi request thông thường, kết hợp Spring Cloud LoadBalancer để chọn instance, đồng thời duy trì timeout, health check, bảo mật và khả năng quan sát. Cách tổ chức này giúp consumer tìm dịch vụ bằng tên logic trong khi hệ thống vẫn có thể thay đổi số lượng và địa chỉ instance trong suốt vòng đời triển khai.
