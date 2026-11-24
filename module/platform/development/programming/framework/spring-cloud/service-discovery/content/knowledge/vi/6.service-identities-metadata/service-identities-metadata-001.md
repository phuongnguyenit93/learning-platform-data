# Tên dịch vụ logic và quy ước `spring.application.name`

Trong Spring Cloud Service Discovery, một consumer thường không cần biết trước địa chỉ IP hay cổng của từng instance mà nó sẽ gọi. Consumer cần biết **dịch vụ logic** mà nó muốn sử dụng, chẳng hạn `inventory-service` hoặc `payment-service`. Registry lưu các instance đang cung cấp dịch vụ dưới tên logic đó; client tra cứu tên để nhận danh sách instance và chọn một instance phù hợp.

Thuộc tính `spring.application.name` là điểm cấu hình quan trọng để đặt tên logic cho ứng dụng Spring Boot. Tên này thường được Spring Cloud dùng làm service ID khi đăng ký ứng dụng và cũng là tên mà các consumer dùng để tìm dịch vụ. Vì vậy, cần chọn tên ổn định, thống nhất và có ý nghĩa trong toàn bộ hệ thống.

## 1. Tên dịch vụ logic là gì?

Một dịch vụ có thể chạy thành nhiều bản sao. Ví dụ, hệ thống có ba instance của dịch vụ kho hàng:

- `inventory-service` tại `10.0.1.21:8080`
- `inventory-service` tại `10.0.1.22:8080`
- `inventory-service` tại `10.0.1.23:8080`

Ba tiến trình có địa chỉ mạng và định danh instance khác nhau, nhưng cùng thực hiện một vai trò nghiệp vụ. Registry nhóm chúng dưới một tên logic là `inventory-service`. Consumer chỉ cần yêu cầu các instance của tên đó.

Cần phân biệt bốn khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên dịch vụ logic (service ID) | `inventory-service` | Nhóm các instance cùng cung cấp một dịch vụ |
| Định danh instance (instance ID) | `inventory-service:pod-a81f` | Phân biệt một tiến trình hoặc bản triển khai cụ thể |
| Địa chỉ mạng | `10.0.1.21:8080` | Nơi có thể kết nối tới instance |
| Metadata | `zone=ap-southeast-1a`, `version=v2` | Thông tin bổ sung để mô tả hoặc lọc instance |

Tên logic không phải hostname, IP, cổng, tên class Java hay tên hiển thị trên giao diện. Nó là khóa tra cứu chung giữa bên đăng ký và bên tiêu thụ dịch vụ.

## 2. Vai trò của `spring.application.name`

Khai báo tên trong cấu hình ứng dụng:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
```

Trong cấu hình Spring Cloud có tích hợp service discovery, `spring.application.name` thường được dùng làm service ID mặc định khi ứng dụng đăng ký với registry. Ví dụ:

- Với Eureka, tên ứng dụng được dùng làm tên application trong registry.
- Với Consul, tên này thường được dùng làm tên service đăng ký. Có thể cấu hình `spring.cloud.consul.discovery.service-name` nếu cần một tên đăng ký khác.
- Với consumer, cùng service ID được dùng khi gọi `DiscoveryClient` hoặc khi tạo URL logic cho Spring Cloud LoadBalancer.

Chỉ khai báo `spring.application.name` chưa tự tạo ra một registry hay bảo đảm ứng dụng đã đăng ký thành công. Ứng dụng vẫn cần dependency và cấu hình discovery client phù hợp với Eureka, Consul hoặc nhà cung cấp registry đang dùng.

### Luồng sử dụng tên dịch vụ

1. Ứng dụng khởi động và nạp cấu hình, trong đó có `spring.application.name`.
2. Discovery client tạo thông tin đăng ký cho instance. Thông tin thường bao gồm service ID, instance ID, host, port, trạng thái và metadata.
3. Registry lưu instance dưới service ID tương ứng. Nhiều instance có thể cùng thuộc một service ID.
4. Consumer tra cứu service ID để nhận danh sách instance.
5. Spring Cloud LoadBalancer hoặc logic lựa chọn của ứng dụng chọn một instance để gửi request.
6. Khi instance dừng hoặc mất kết nối, cơ chế deregistration, heartbeat hoặc health check của registry sẽ cập nhật trạng thái của instance đó.

Tên logic giúp consumer không phải gắn cứng vào địa chỉ của một máy cụ thể. Khi số lượng instance thay đổi, consumer vẫn gọi cùng một service ID.

## 3. Quy ước đặt tên dịch vụ

Một tên dịch vụ tốt phải ổn định và thể hiện vai trò của dịch vụ trong hệ thống. Có thể áp dụng các quy ước sau:

- **Dùng chữ thường và dấu gạch ngang.** Ví dụ: `order-service`, `inventory-service`, `payment-service`. Cách viết này dễ đọc và ít gây khác biệt giữa môi trường.
- **Đặt tên theo năng lực nghiệp vụ.** Tên nên cho biết dịch vụ chịu trách nhiệm về điều gì, thay vì tên nhóm phát triển, tên máy hoặc công nghệ triển khai.
- **Giữ tên giống nhau giữa các replica.** Mọi instance của cùng một dịch vụ logic phải đăng ký dưới cùng service ID. Mỗi instance được phân biệt bằng instance ID và địa chỉ riêng.
- **Không đưa thông tin thay đổi theo lần triển khai vào service ID.** Không dùng pod name, hostname, IP, port hoặc mã build làm tên dịch vụ.
- **Không gắn phiên bản vào tên nếu không có chủ đích tách tuyến.** Thông tin phiên bản thường phù hợp hơn với metadata hoặc cơ chế version routing. Chỉ dùng `inventory-v2` khi hệ thống thực sự cần xem phiên bản đó là một đích dịch vụ độc lập.
- **Tránh tên quá chung chung.** Các tên như `service`, `backend`, `api` không cho biết trách nhiệm và dễ va chạm.
- **Thống nhất phạm vi tên trong registry.** Hai ứng dụng khác nhau không nên đăng ký cùng một service ID nếu consumer có thể nhận nhầm instance của ứng dụng kia.

Ví dụ:

| Nên dùng | Nên tránh | Lý do |
|---|---|---|
| `customer-service` | `CustomerService` | Chữ thường, quy ước nhất quán |
| `order-service` | `order_service` | Dấu gạch ngang dễ thống nhất hơn dấu gạch dưới |
| `inventory-service` | `inventory-service-pod-7f9c` | Tên logic không phụ thuộc một pod |
| `payment-service` | `backend` | Tên thể hiện năng lực nghiệp vụ |
| `notification-service` | `notification-service-v2026-11-24` | Bản build thay đổi không nên làm đổi danh tính logic |

Các registry có thể có quy tắc chuẩn hóa hoặc so khớp tên riêng. Vì vậy, hãy dùng một cách viết thống nhất và bảo đảm consumer sử dụng chính xác service ID mà provider đăng ký; không dựa vào giả định rằng registry sẽ tự chuyển chữ hoa, dấu gạch dưới hoặc khoảng trắng về cùng một tên.

### Tên theo môi trường

Nếu mỗi môi trường có registry hoặc namespace riêng, có thể giữ nguyên tên `inventory-service` ở development, staging và production. Môi trường đã được phân tách ở tầng registry nên tên dịch vụ không cần thay đổi.

Nếu nhiều môi trường dùng chung một registry và cùng namespace, cần phân tách rõ ràng để tránh consumer của môi trường này nhìn thấy instance của môi trường khác. Có thể dùng namespace/datacenter riêng hoặc quy ước tiền tố như `dev-inventory-service`, tùy khả năng của nền tảng. Không nên thêm tiền tố môi trường một cách máy móc khi registry đã cung cấp ranh giới cách ly.

## 4. Cấu hình tên trong Spring Boot

Cấu hình cơ bản nên đặt ở file cấu hình chung của ứng dụng:

```yaml
spring:
  application:
    name: order-service
```

Các profile có thể thay đổi port, endpoint registry hoặc thông số môi trường mà vẫn giữ tên logic:

```yaml
# application-dev.yml
server:
  port: 8082
```

Cũng có thể truyền tên qua biến môi trường:

```bash
SPRING_APPLICATION_NAME=order-service
```

Hoặc qua tham số dòng lệnh:

```bash
java -jar order-service.jar --spring.application.name=order-service
```

Khi dùng cấu hình ngoài, cần bảo đảm giá trị tên đã được nạp trước khi discovery client tạo thông tin đăng ký. Nếu nhiều nguồn cấu hình cùng đặt thuộc tính này, hãy kiểm tra thứ tự ưu tiên của cấu hình Spring Boot để xác định giá trị cuối cùng.

### Ví dụ với Eureka

Một ứng dụng có thể khai báo tên và địa chỉ Eureka server như sau:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

Khi Eureka client được bật và kết nối thành công, ứng dụng đăng ký dưới tên application tương ứng. Nhiều bản chạy của `order-service` sẽ xuất hiện như các instance của cùng application.

### Ví dụ với Consul

Có thể khai báo tên service một cách tường minh:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        service-name: ${spring.application.name}
```

Việc đặt `service-name` bằng `spring.application.name` giúp cấu hình thể hiện rõ tên được đăng ký. Nếu chủ động đặt `service-name` thành giá trị khác, consumer phải tra cứu đúng tên thực tế trong Consul; không nên giả định hai thuộc tính luôn giống nhau khi đã override.

## 5. Consumer tra cứu bằng service ID

Spring Cloud cung cấp `DiscoveryClient` để truy vấn danh sách instance theo tên dịch vụ. Ví dụ sau minh họa cách đọc các instance của `inventory-service`:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Kết quả là danh sách instance mà discovery client nhìn thấy tại thời điểm truy vấn. Mỗi `ServiceInstance` cung cấp thông tin như service ID, host, port, URI và metadata. Danh sách rỗng có thể cho biết dịch vụ chưa đăng ký, tên tra cứu không khớp, instance chưa sẵn sàng hoặc registry chưa cập nhật.

Trong ứng dụng thực tế, không nên mặc định lấy phần tử đầu tiên của danh sách rồi dùng nó cho mọi request. Cách đó bỏ qua việc cân bằng tải và có thể dồn toàn bộ lưu lượng vào một instance. Khi gọi HTTP giữa các dịch vụ, thường nên dùng client tích hợp Spring Cloud LoadBalancer.

Ví dụ với `RestTemplate`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

Consumer gọi bằng tên logic:

```java
String url = "http://inventory-service/api/items/42";
Item item = restTemplate.getForObject(url, Item.class);
```

Với bean có `@LoadBalanced` và cấu hình Spring Cloud LoadBalancer phù hợp, phần host `inventory-service` được hiểu là service ID. LoadBalancer lấy các instance từ discovery client và chọn instance cho request. Ví dụ này cần có dependency LoadBalancer tương ứng trong dự án.

## 6. Những lỗi thường gặp khi đặt tên

**Provider và consumer dùng hai tên khác nhau.** Provider đăng ký `inventory-service` nhưng consumer gọi `inventories-service`. Registry không tìm được instance theo tên consumer yêu cầu, dẫn tới danh sách rỗng hoặc lỗi không có instance phù hợp.

**Mỗi replica tự tạo một tên riêng.** Nếu mỗi pod đăng ký bằng hostname hoặc mã pod, các replica không còn được gom dưới một service ID chung. Consumer phải biết từng tên riêng và việc cân bằng tải theo một dịch vụ logic trở nên khó khăn.

**Nhiều ứng dụng không tương thích dùng chung một tên.** Nếu `billing-service` và một ứng dụng khác cùng đăng ký dưới `billing-service`, LoadBalancer có thể chọn nhầm instance. Tên giống nhau chỉ phù hợp khi các instance thực sự cung cấp cùng hợp đồng dịch vụ mà consumer mong đợi.

**Tên đăng ký bị override ở cấu hình của provider.** Một thuộc tính riêng của Eureka hoặc Consul có thể làm tên thực tế trong registry khác với `spring.application.name`. Khi điều tra lỗi, hãy xem tên hiển thị trong registry và cấu hình discovery của provider, sau đó đối chiếu với service ID consumer đang truy vấn.

**Dùng service ID để biểu diễn metadata.** Không nên tạo các tên như `inventory-service-zone-a-v2` chỉ để mô tả zone hoặc phiên bản nếu đó không phải ranh giới định tuyến có chủ đích. Metadata phù hợp hơn cho thông tin bổ sung; service ID nên đại diện cho danh tính logic ổn định.

## 7. Kiểm tra trước khi đưa vào môi trường chạy

Khi cấu hình một dịch vụ mới, hãy kiểm tra lần lượt:

1. `spring.application.name` được khai báo rõ ràng và đúng quy ước.
2. Mọi replica của cùng dịch vụ dùng cùng tên logic.
3. Mỗi instance có thông tin nhận diện và địa chỉ riêng để registry phân biệt.
4. Tên service trong registry trùng với tên mà consumer tra cứu.
5. Nếu provider có thuộc tính override như `service-name`, giá trị cuối cùng đã được xác định.
6. Các môi trường được cách ly bằng registry hoặc namespace phù hợp.
7. Consumer nhận được danh sách instance mong đợi và HTTP client có cơ chế load balancing.

Không đưa mật khẩu, token, khóa bí mật hoặc dữ liệu nhạy cảm vào service ID hay metadata. Metadata có thể được hiển thị trong registry và được nhiều thành phần trong hệ thống đọc.

## 8. Ví dụ tổng hợp

Giả sử một hệ thống bán hàng có ba dịch vụ:

| Ứng dụng | `spring.application.name` | Trách nhiệm |
|---|---|---|
| Đơn hàng | `order-service` | Tạo và theo dõi đơn hàng |
| Kho hàng | `inventory-service` | Kiểm tra và cập nhật tồn kho |
| Thanh toán | `payment-service` | Xử lý thanh toán |

Khi `order-service` cần kiểm tra tồn kho, nó gửi request tới địa chỉ logic `http://inventory-service/api/items/42`. Registry cung cấp các instance đang đăng ký dưới `inventory-service`; LoadBalancer chọn một instance và chuyển request tới địa chỉ mạng tương ứng.

Nếu đội vận hành tăng số replica của kho hàng từ hai lên năm, consumer vẫn gọi `inventory-service`. Các địa chỉ mới được đưa vào registry khi instance đăng ký thành công. Consumer không phải sửa URL theo IP hoặc port mới.

Đó là mục đích của tên dịch vụ logic: giữ cho cách các microservice tham chiếu lẫn nhau ổn định trong khi số lượng và vị trí instance có thể thay đổi theo quá trình triển khai và vận hành.
