# Ánh xạ URI, giao thức và thông tin ServiceInstance

Trong Spring Cloud, service discovery không chỉ trả về tên dịch vụ mà còn phải mô tả từng địa chỉ có thể nhận request. Với cấu hình khám phá tĩnh, `SimpleDiscoveryClient` lấy danh sách instance từ cấu hình ứng dụng thay vì truy vấn Eureka, Consul hoặc ZooKeeper. Mỗi URI được ánh xạ thành một `ServiceInstance` để các thành phần như `DiscoveryClient` và Spring Cloud LoadBalancer sử dụng.

URI cho biết giao thức, host và port của endpoint. Từ đó, Spring Cloud cung cấp các trường `serviceId`, `instanceId`, `host`, `port`, `secure`, `uri` và `metadata` thông qua abstraction `ServiceInstance`. Hiểu rõ cách ánh xạ giúp tránh lỗi gọi sai host/port, dùng nhầm HTTP với HTTPS hoặc cấu hình danh sách instance không đúng service ID.

Nội dung này thuộc module `SPRING_CLOUD_SERVICE_DISCOVERY`, nơi service discovery được sử dụng để tìm instance theo tên dịch vụ và hỗ trợ load balancing. Phần này tập trung vào ánh xạ URI trong static discovery và cách consumer sử dụng thông tin `ServiceInstance`.

## 1. Static discovery và SimpleDiscoveryClient

`SimpleDiscoveryClient` là implementation của `DiscoveryClient`, sử dụng các thuộc tính cấu hình làm nguồn dữ liệu cho danh sách service instance. Theo tài liệu Spring Cloud Commons, implementation này được tự cấu hình khi classpath không có một `DiscoveryClient` dựa trên service registry. Nếu ứng dụng có Eureka, Consul hoặc một registry-backed discovery client khác, không nên mặc định rằng cấu hình Simple sẽ là nguồn được sử dụng; cần kiểm tra discovery implementation thực tế trong application context.

Định dạng thuộc tính cơ bản:

```properties
spring.cloud.discovery.client.simple.instances.service1[0].uri=http://s11:8080
spring.cloud.discovery.client.simple.instances.service1[1].uri=https://s12:8443
spring.cloud.discovery.client.simple.instances.service2[0].uri=http://s21:8081
```

Trong đó:

- `spring.cloud.discovery.client.simple.instances` là prefix của cấu hình.
- `service1` và `service2` là service ID dùng để tra cứu.
- `[0]`, `[1]` là chỉ số instance trong danh sách, bắt đầu từ `0`.
- `uri` là địa chỉ endpoint của từng instance.

Ví dụ tương đương dưới dạng YAML:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-01.internal:8081
              - uri: https://payment-02.internal:8443
            inventory-service:
              - uri: http://inventory.internal:8083
```

Khi consumer gọi `getInstances("payment-service")`, `SimpleDiscoveryClient` đọc danh sách được cấu hình dưới key `payment-service` và chuyển từng phần tử thành một `ServiceInstance`. Khi gọi `getServices()`, client trả về các service ID có trong map cấu hình. Nếu không có key cho service ID được hỏi, danh sách instance trả về rỗng.

Static discovery phù hợp với môi trường có số endpoint ít và tương đối ổn định, kiểm thử, demo, tích hợp hệ thống cũ hoặc giai đoạn chuyển tiếp. Danh sách không tự thay đổi khi một máy chủ mới xuất hiện hoặc một endpoint ngừng hoạt động; cần cập nhật cấu hình và triển khai/làm mới ứng dụng theo quy trình đã chọn.

## 2. Cấu trúc một URI của service instance

Một URI HTTP phổ biến có dạng:

```text
scheme://host:port
```

Ví dụ:

```text
https://payment-02.internal.example:8443
```

| Thành phần | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| Scheme | `https` | Giao thức kết nối. |
| Host | `payment-02.internal.example` | Hostname hoặc địa chỉ IP của instance. |
| Port | `8443` | Cổng dịch vụ đang lắng nghe. |

Với static discovery, URI là cách khai báo gọn endpoint. Spring Cloud ánh xạ URI sang thông tin instance để consumer có thể lấy host, port và trạng thái secure. Nên dùng URI tuyệt đối, có scheme rõ ràng và ghi port tường minh, đặc biệt khi ứng dụng chạy trên port khác mặc định.

### 2.1. Hostname và IP

Host có thể là DNS name hoặc IP:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-01.internal.example:8081
              - uri: http://10.20.0.22:8081
```

Consumer phải phân giải được hostname hoặc định tuyến được đến IP. Không cấu hình `localhost`, `127.0.0.1` hoặc `0.0.0.0` cho instance nằm trên máy/container khác. `localhost` trỏ về chính consumer; `0.0.0.0` là địa chỉ wildcard dùng khi bind server, không phải địa chỉ đích để gọi.

Nếu host là IPv6 literal, URI cần đặt địa chỉ trong dấu ngoặc vuông, ví dụ `http://[2001:db8::10]:8081`. Kiểm tra DNS, route và firewall từ đúng môi trường chạy consumer, không chỉ từ máy provider.

### 2.2. Port

Port trong URI phải là port consumer thực sự có thể truy cập. Với container, port trong container có thể khác port publish ra host. Với Kubernetes, Pod port, Service port và NodePort cũng có thể khác nhau. Chọn endpoint dựa trên đường mạng mà consumer sử dụng.

URI có thể bỏ port khi dùng port mặc định của scheme. Tuy nhiên, khi phân tích URI, `getPort()` có thể trả về `-1` nếu port không được ghi rõ; cách một client hoặc URI builder áp dụng port mặc định còn phụ thuộc implementation. Để `ServiceInstance` và HTTP client có cùng endpoint rõ ràng, nên ghi port tường minh. Port mặc định của `http` là `80`, còn `https` là `443`.

## 3. Scheme và giao thức HTTP/HTTPS

Scheme ảnh hưởng đến cách Spring Cloud mô tả kết nối an toàn của instance.

| URI | `host` | `port` | `isSecure()` |
|---|---|---:|---|
| `http://payment-01:8081` | `payment-01` | 8081 | `false` |
| `https://payment-02:8443` | `payment-02` | 8443 | `true` |

Với `SimpleDiscoveryClient`, URI `https` được ánh xạ thành instance có `secure=true`; URI `http` là kết nối không bảo mật. Khi Spring Cloud LoadBalancer tạo địa chỉ vật lý cho request, thông tin secure của instance được dùng để chọn scheme tương ứng.

Ví dụ hai instance cùng service có thể được cấu hình:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-01.internal:8081
                instance-id: payment-http-01
              - uri: https://payment-02.internal:8443
                instance-id: payment-https-02
```

Mặc dù có thể mô tả các instance với scheme khác nhau, chỉ nên trộn HTTP và HTTPS khi consumer, chính sách bảo mật và cấu hình client hỗ trợ rõ ràng cả hai. Trong production, thường nên thống nhất HTTPS để tránh một số request vô tình đi qua endpoint không mã hóa.

Scheme tùy chỉnh như `tcp`, `grpc` hoặc `h2c` không tự động được chuyển thành một hành vi giao thức tương ứng bởi `ServiceInstance` chuẩn. `isSecure()` chủ yếu mô tả kết nối HTTPS. Nếu dùng giao thức khác, cần client và cơ chế định tuyến hỗ trợ giao thức đó; không giả định rằng đổi scheme trong URI sẽ tự cấu hình gRPC hoặc TCP client.

## 4. Ánh xạ sang ServiceInstance

`ServiceInstance` là abstraction chung của Spring Cloud để mô tả một endpoint cụ thể. Các phương thức quan trọng gồm:

| Phương thức | Thông tin trả về | Nguồn trong static discovery |
|---|---|---|
| `getServiceId()` | Tên dịch vụ logic. | Key dưới `instances`, ví dụ `payment-service`. |
| `getInstanceId()` | Mã định danh của instance. | Thuộc tính `instance-id` nếu được cấu hình; có thể không có nếu bỏ trống. |
| `getHost()` | Hostname hoặc IP. | Host được phân tích từ URI hoặc cấu hình host riêng. |
| `getPort()` | Port của instance. | Port được phân tích từ URI hoặc cấu hình port riêng. |
| `isSecure()` | Có sử dụng HTTPS hay không. | Scheme `https` hoặc cờ secure của instance. |
| `getUri()` | URI của instance. | Endpoint được biểu diễn từ thông tin instance. |
| `getMetadata()` | Map key-value bổ sung. | Thuộc tính `metadata` trong cấu hình instance. |

Ví dụ cấu hình đầy đủ:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - instance-id: payment-01
                uri: http://payment-01.internal:8081
                metadata:
                  zone: zone-a
                  version: "2.4.1"
                  api-level: v1
              - instance-id: payment-02
                uri: https://payment-02.internal:8443
                metadata:
                  zone: zone-b
                  version: "2.5.0"
                  api-level: v2
```

Ở đây service ID là `payment-service`, còn hai instance ID là `payment-01` và `payment-02`. Metadata giúp consumer hoặc load balancer phân biệt zone, software version và API level. Các giá trị này không tự tạo health check hay chính sách lọc; thành phần sử dụng phải đọc metadata và áp dụng quy tắc tương ứng.

### 4.1. Service ID không phải host

Service ID là tên logic mà consumer dùng để tra cứu. Host và port là địa chỉ vật lý của từng instance. Ví dụ:

```text
serviceId = payment-service
instanceId = payment-01
host = payment-01.internal
port = 8081
uri = http://payment-01.internal:8081
```

Khi request đi qua load balancer, consumer gửi đến URI logic dùng service ID, còn load balancer chọn một `ServiceInstance` và thay service ID bằng host/port thực tế.

## 5. Ví dụ đọc ServiceInstance qua DiscoveryClient

Consumer có thể sử dụng `DiscoveryClient` để lấy danh sách endpoint đã khai báo:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentInstanceInspector {

    private final DiscoveryClient discoveryClient;

    public PaymentInstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void printInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("payment-service");

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s, instanceId=%s, host=%s, port=%d, secure=%s, uri=%s, metadata=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure(),
                    instance.getUri(),
                    instance.getMetadata()
            );
        }
    }
}
```

Đoạn code cho thấy consumer không cần biết chi tiết cấu hình YAML. Nó làm việc với abstraction `ServiceInstance`, vì vậy có thể dùng cùng kiểu API khi đổi từ Simple Discovery sang Eureka, Consul hoặc ZooKeeper. Giá trị metadata cụ thể vẫn phụ thuộc provider.

Nếu `getInstances("payment-service")` trả về danh sách rỗng, hãy kiểm tra key service ID trong cấu hình, profile đang bật, file cấu hình đã được nạp và discovery client thực tế đang được Spring sử dụng.

## 6. Dùng ServiceInstance với Spring Cloud LoadBalancer

`DiscoveryClient` cung cấp danh sách instance. Spring Cloud LoadBalancer chọn một instance từ danh sách và chuyển request từ service ID sang địa chỉ thực.

Ví dụ với `RestTemplate`:

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
    RestTemplate paymentRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
```

Consumer có thể gọi bằng service ID:

```java
String response = paymentRestTemplate.getForObject(
        "http://payment-service/api/payments/42",
        String.class
);
```

Để ví dụ hoạt động, ứng dụng cần có Spring Cloud LoadBalancer trên classpath và cấu hình `SimpleDiscoveryClient` với service ID `payment-service`. `@LoadBalanced` khiến client coi `payment-service` là tên logic cần phân giải; load balancer lấy một `ServiceInstance`, sau đó xây dựng địa chỉ vật lý theo host, port và secure flag của instance.

Nếu dùng `RestTemplate` không có `@LoadBalanced`, chuỗi `http://payment-service/...` sẽ được xử lý như hostname thông thường và thường không phân giải được qua DNS. Không nhầm URI logic trong request với URI vật lý trong cấu hình static discovery.

### 6.1. Load balancing không phải health check

Static discovery trả lại các endpoint đã cấu hình. Nó không tự ping endpoint hoặc loại instance chết khỏi danh sách chỉ vì request trước đó thất bại. Nếu một địa chỉ ngừng hoạt động, danh sách tĩnh vẫn chứa địa chỉ đó cho đến khi cấu hình được cập nhật hoặc một cơ chế health-aware khác được bổ sung.

Có thể kết hợp Spring Cloud LoadBalancer health-check supplier hoặc cơ chế kiểm tra endpoint riêng, tùy phiên bản và cấu hình. Dù dùng cách nào, cần xác định tần suất kiểm tra, timeout và hành vi khi tất cả instance đều không khỏe mạnh.

## 7. Metadata và cách dùng trong định tuyến

`metadata` trong cấu hình instance là map key-value. Ví dụ:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            payment-service:
              - uri: http://payment-a.internal:8081
                metadata:
                  zone: zone-a
                  version: "2.4.1"
              - uri: http://payment-b.internal:8081
                metadata:
                  zone: zone-b
                  version: "2.4.1"
```

Consumer có thể dùng metadata để:

- Ưu tiên instance cùng zone.
- Chọn instance có API level tương thích.
- Quan sát phiên bản phần mềm đang được cấu hình.
- Phân nhóm instance phục vụ canary hoặc môi trường thử nghiệm.

Việc khai báo metadata không tự kích hoạt các chính sách trên. Muốn lọc theo zone hoặc version, cần custom `ServiceInstanceListSupplier`, gateway policy hoặc logic chọn instance riêng. Cần có fallback khi không tìm thấy instance phù hợp; tránh để một bộ lọc metadata sai làm danh sách kết quả luôn rỗng.

Không lưu password, access token, private key hoặc dữ liệu nhạy cảm trong metadata. Các giá trị metadata thường xuất hiện trong log hoặc endpoint quản trị.

## 8. URI có path, query và thông tin xác thực

URI tổng quát có thể chứa thêm path, query, fragment hoặc user information. Tuy nhiên, đối với service discovery và load balancing, phần cốt lõi cần xác định endpoint thường là scheme, host và port.

Ví dụ endpoint:

```text
https://payment.internal.example:8443
```

Request path được thêm ở phía consumer:

```text
https://payment-service/api/payments/42
```

Không nên nhúng username/password vào URI discovery, ví dụ `https://user:password@host:8443`. Thông tin xác thực phải được quản lý qua secret store, OAuth2, mTLS hoặc cơ chế bảo mật phù hợp.

Nếu ứng dụng cần một base path đặc thù cho từng endpoint, hãy xác minh implementation `ServiceInstance`, LoadBalancer và HTTP client có giữ và ghép path theo cách mong muốn hay không. Không giả định mọi discovery provider đều xử lý URI có path giống nhau. Với cấu hình phổ biến, nên giữ URI instance ở dạng `scheme://host:port` và quản lý API path trong client request.

## 9. Nhiều DiscoveryClient và thứ tự lựa chọn

Nếu ứng dụng có nhiều discovery implementation trên classpath, ví dụ Eureka và Simple Discovery, không nên giả định Simple luôn là client đang cung cấp kết quả. Spring Cloud có cơ chế composite discovery và thứ tự client; kết quả phụ thuộc cấu hình và phiên bản.

Tài liệu Spring Cloud Commons mô tả `SimpleDiscoveryClient` như lựa chọn khi không có service-registry-backed `DiscoveryClient` trên classpath. Khi muốn kết hợp hoặc ưu tiên nhiều discovery client, cần kiểm tra thứ tự (`order`) và hành vi composite theo phiên bản đang dùng.

Với static discovery, nên giữ cấu hình đơn giản và tránh khai báo cùng service ID ở nhiều nguồn nếu chưa có chủ đích. Nếu một nguồn trả về instance trùng với nguồn khác, consumer có thể thấy danh sách lặp hoặc lựa chọn endpoint ngoài dự kiến tùy composite behavior.

## 10. Các lỗi thường gặp khi ánh xạ URI

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `getInstances()` trả về danh sách rỗng | Sai service ID hoặc cấu hình `instances` chưa được nạp. | Đối chiếu key trong YAML/properties với service ID consumer tra cứu. |
| Host trong `ServiceInstance` sai | URI sai hostname/IP hoặc DNS không phù hợp với mạng consumer. | Kiểm tra URI và phân giải DNS từ môi trường consumer. |
| Port trả về `-1` hoặc không đúng | URI thiếu port hoặc port không khớp endpoint thực tế. | Khai báo port tường minh và kiểm tra mapping container/gateway. |
| Request HTTPS lại gọi HTTP | URI cấu hình dùng `http` hoặc secure flag không đúng. | Dùng `https://` và kiểm tra `isSecure()` của instance. |
| TLS handshake thất bại | Certificate SAN không khớp hostname/IP hoặc truststore thiếu CA. | Cấp certificate đúng endpoint và cấu hình truststore; không tắt hostname verification. |
| `payment-service` không được phân giải | HTTP client không được đánh dấu `@LoadBalanced` hoặc thiếu LoadBalancer dependency. | Kiểm tra bean và dependency Spring Cloud LoadBalancer. |
| Endpoint chết vẫn được chọn | Static list không tự cập nhật health. | Cập nhật cấu hình hoặc bổ sung health-aware supplier/monitoring. |
| Thay đổi URI nhưng ứng dụng vẫn gọi địa chỉ cũ | Cấu hình chưa được reload hoặc instance cache còn giữ dữ liệu. | Kiểm tra profile/property source, lifecycle restart/refresh và cache của client. |
| Instance xuất hiện hai lần | Nhiều DiscoveryClient cùng trả service ID hoặc cấu hình trùng endpoint. | Kiểm tra composite discovery, client order và danh sách instance từng nguồn. |
| URI chứa path nhưng request bị mất path | LoadBalancer/client chỉ sử dụng host, port và scheme khi tái tạo URI. | Đưa API path vào request hoặc triển khai cơ chế base-path riêng đã được kiểm thử. |

## 11. Quy trình kiểm chứng cấu hình

Sau khi khai báo static discovery, có thể kiểm tra theo các bước:

1. Xác nhận `spring.cloud.discovery.client.simple.instances` được nạp từ đúng profile và property source.
2. Gọi `DiscoveryClient.getServices()` để xem các service ID đã biết.
3. Gọi `getInstances(serviceId)` để lấy danh sách instance.
4. In `getInstanceId()`, `getServiceId()`, `getHost()`, `getPort()`, `isSecure()`, `getUri()` và `getMetadata()`.
5. Kiểm tra DNS, route và port từ môi trường consumer.
6. Nếu dùng HTTPS, kiểm tra TLS certificate và trust chain.
7. Gửi request qua client có `@LoadBalanced` để xác minh service ID được chuyển thành địa chỉ vật lý.
8. Kiểm thử trường hợp service ID không tồn tại và endpoint bị dừng để xác nhận ứng dụng xử lý lỗi đúng.

Để kiểm tra nhanh endpoint bằng command line, có thể dùng:

```bash
curl -v http://payment-01.internal:8081/actuator/health
curl -v https://payment-02.internal:8443/actuator/health
```

Các endpoint health ở trên chỉ là ví dụ. Chúng phải tồn tại và được cho phép truy cập trong môi trường thực tế. Không công khai Actuator hoặc endpoint nội bộ ra Internet chỉ để kiểm thử discovery.

## 12. Nguyên tắc thiết kế production

- Dùng service ID ổn định làm key của map `instances`.
- Mỗi URI là endpoint có thể truy cập từ consumer; không dùng loopback hoặc wildcard address.
- Khai báo scheme và port rõ ràng, đặc biệt với HTTPS hoặc port tùy chỉnh.
- Giữ một quy ước protocol nhất quán cho các instance của cùng service, trừ khi có yêu cầu hỗ trợ mixed protocol.
- Dùng `instance-id` riêng khi cần truy vết từng endpoint.
- Dùng metadata cho thuộc tính có cấu trúc; không nhầm metadata với health status.
- Hiểu rằng static list không tự đăng ký, heartbeat hoặc tự loại instance chết khỏi danh sách.
- Cập nhật cấu hình theo quy trình version control/CI/CD và có kiểm tra endpoint trước khi rollout.
- Nếu cần endpoint thay đổi thường xuyên, cân nhắc registry động như Eureka, Consul hoặc ZooKeeper thay cho danh sách tĩnh.
- Kiểm tra discovery implementation thực tế khi có nhiều provider trên classpath.
- Bảo vệ URI, metadata và endpoint nội bộ; không nhúng credential trong URI.

## Kết luận

Trong static discovery, key của `spring.cloud.discovery.client.simple.instances` là service ID, mỗi phần tử trong danh sách là một instance và trường `uri` mô tả endpoint của instance. Scheme `http`/`https` quyết định giao thức và trạng thái secure; host và port xác định địa chỉ kết nối. Các thuộc tính `instance-id` và `metadata` bổ sung khả năng nhận diện và mô tả instance.

`SimpleDiscoveryClient` ánh xạ danh sách cấu hình thành các đối tượng `ServiceInstance`, cho phép consumer sử dụng `DiscoveryClient` và Spring Cloud LoadBalancer mà không cần truy vấn một registry server. Vì danh sách là tĩnh, việc cập nhật endpoint và kiểm tra health phải được quản lý riêng. Hãy kiểm tra service ID, URI, `isSecure()`, metadata và khả năng kết nối thực tế trước khi đưa cấu hình vào production.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions và SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — ServiceInstance API](https://docs.spring.io/spring-cloud-commons/docs/current/api/org/springframework/cloud/client/ServiceInstance.html)
- [Spring Cloud Commons — SimpleDiscoveryClient property mapping tests](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/test/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClientPropertiesMappingTests.java)
