# Chạy nhiều instance của cùng một dịch vụ

Trong hệ thống microservice, một dịch vụ thường chạy nhiều instance để chia tải và duy trì khả năng phục vụ khi một tiến trình gặp sự cố. Các instance cùng thực hiện một vai trò nghiệp vụ, nhưng mỗi instance là một tiến trình riêng với địa chỉ mạng và định danh riêng.

Với Spring Cloud Netflix Eureka, nhiều instance của cùng một dịch vụ đăng ký dưới **cùng một service name**, thường lấy từ spring.application.name. Eureka lưu nhiều instance record trong cùng một application. Consumer tra cứu theo service name, sau đó Spring Cloud LoadBalancer chọn một instance để gửi request.

Ví dụ, ba tiến trình inventory-service có thể được đăng ký như sau:

| Service name | Instance ID | Địa chỉ |
|---|---|---|
| inventory-service | inventory-service:node-a:8081 | 10.20.1.11:8081 |
| inventory-service | inventory-service:node-a:8082 | 10.20.1.11:8082 |
| inventory-service | inventory-service:node-b:8080 | 10.20.1.12:8080 |

Service name cho biết dịch vụ logic mà consumer cần gọi. Instance ID phân biệt từng tiến trình trong registry. Địa chỉ host và port cho biết nơi có thể gửi HTTP request. Ba giá trị này liên quan với nhau nhưng không thể thay thế cho nhau.

## 1. Vì sao cần nhiều instance?

Một instance duy nhất có thể trở thành điểm nghẽn hoặc điểm lỗi của dịch vụ. Chạy nhiều instance giúp hệ thống:

- **Chia tải:** phân phối request đến nhiều tiến trình thay vì dồn vào một tiến trình.
- **Tăng khả năng phục vụ:** khi một instance gặp lỗi, các instance khỏe mạnh khác vẫn có thể nhận request.
- **Mở rộng theo nhu cầu:** tăng số instance khi lưu lượng tăng và giảm khi tải thấp.
- **Triển khai từng phần:** cập nhật một nhóm instance trong khi những instance còn lại tiếp tục phục vụ, nếu API giữa các phiên bản tương thích.
- **Tách biệt tài nguyên:** mỗi instance có thể chạy trên một máy hoặc container khác nhau.

Nhiều instance không tự động bảo đảm tính sẵn sàng cao. Các instance có thể cùng phụ thuộc vào một database, registry hoặc node mạng. Nếu dependency chung gặp sự cố, tất cả instance vẫn có thể không phục vụ được. Vì vậy, cần kết hợp discovery với health check, timeout, retry có giới hạn, quan sát hệ thống và thiết kế hạ tầng phù hợp.

## 2. Service name và instance ID trong Eureka

Provider khai báo tên logic bằng spring.application.name:

~~~yaml
spring:
  application:
    name: inventory-service
~~~

Mọi instance của cùng dịch vụ đều dùng giá trị inventory-service. Khi đăng ký vào Eureka, registry nhóm các instance theo application name. Eureka dashboard thường hiển thị application name ở dạng chữ hoa, ví dụ INVENTORY-SERVICE.

Mỗi instance cần có eureka.instance.instance-id duy nhất. Nếu nhiều tiến trình đăng ký cùng service name và cùng instance ID, chúng có thể ghi đè hoặc cập nhật cùng một registration. Khi đó dashboard không thể hiện đúng số lượng tiến trình đang chạy.

Có thể dùng hostname và port để tạo instance ID:

~~~yaml
eureka:
  instance:
    instance-id: ${spring.application.name}:${HOSTNAME:localhost}:${server.port}
    prefer-ip-address: true
~~~

Cấu hình này phù hợp khi các tiến trình chạy trên cùng máy nhưng dùng port khác nhau, hoặc chạy trên các container/máy có hostname riêng. Địa chỉ được công bố cũng phải truy cập được từ consumer.

Nếu môi trường có quy tắc định danh riêng, có thể truyền INSTANCE_ID từ cấu hình triển khai:

~~~yaml
eureka:
  instance:
    instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
~~~

Khi chạy nhiều tiến trình, hãy kiểm tra instance ID thực tế trên Eureka dashboard. Không giả định rằng đổi port luôn làm instance ID thay đổi nếu ứng dụng đang ghi đè ID bằng một giá trị cố định.

Nếu biến HOSTNAME không tồn tại hoặc không phản ánh hostname có thể phân giải từ phía consumer, hãy truyền INSTANCE_ID rõ ràng theo từng máy/container. Instance ID chỉ giúp registry phân biệt record; địa chỉ hostname/IP mà client quảng bá vẫn phải định tuyến được từ consumer.

### Phân biệt service name, instance ID và metadata

| Thuộc tính | Dùng để làm gì? | Ví dụ |
|---|---|---|
| spring.application.name | Nhóm các instance thành một dịch vụ logic | inventory-service |
| eureka.instance.instance-id | Phân biệt từng tiến trình trong registry | inventory-service:node-a:8081 |
| eureka.instance.hostname hoặc địa chỉ IP | Xác định host được công bố | node-a, 10.20.1.11 |
| server.port | Cổng HTTP mà tiến trình lắng nghe | 8081 |
| eureka.instance.metadata-map | Lưu thông tin bổ sung của instance | version=v2, zone=zone-a |

Metadata có thể giúp quan sát, lọc hoặc xây dựng chính sách định tuyến tùy chỉnh. Spring Cloud LoadBalancer không tự hiểu mọi metadata và không tự động chỉ chọn phiên bản mới nhất. Nếu cần định tuyến theo phiên bản, zone hoặc nhóm triển khai, phải cấu hình chính sách tương ứng ở phía consumer.

## 3. Cấu hình một Eureka Client có thể chạy nhiều lần

Một cấu hình chung cho provider:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: ${SERVER_PORT:8080}

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
    register-with-eureka: true
    fetch-registry: true
    healthcheck:
      enabled: true
  instance:
    instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
    prefer-ip-address: true
    metadata-map:
      version: ${app.version:dev}
      zone: ${APP_ZONE:local}

management:
  endpoints:
    web:
      exposure:
        include: health,info

app:
  version: ${APP_VERSION:dev}
~~~

Các thuộc tính quan trọng:

- spring.application.name: giữ nguyên giữa các instance của cùng dịch vụ.
- server.port: phải khác nhau nếu nhiều tiến trình cùng bind trên một địa chỉ IP và cùng máy.
- eureka.client.service-url.defaultZone: địa chỉ Eureka Server mà client đăng ký.
- eureka.client.register-with-eureka: bật đăng ký instance.
- eureka.client.fetch-registry: cho phép client tải registry; cần thiết khi ứng dụng cũng tra cứu các dịch vụ khác.
- eureka.instance.instance-id: phải duy nhất cho mỗi tiến trình.
- eureka.instance.prefer-ip-address: yêu cầu Eureka công bố IP thay vì hostname khi phù hợp với mạng triển khai.
- eureka.client.healthcheck.enabled: cho phép Eureka Client sử dụng trạng thái health của ứng dụng khi tích hợp với Actuator.
- eureka.instance.metadata-map: mang thông tin bổ sung như version hoặc zone.

Cần có dependency Eureka Client và Actuator tương ứng. Phiên bản Spring Cloud starter phải tương thích với Spring Boot thông qua Spring Cloud BOM. Không tự thêm các phiên bản starter khác nhau cho từng instance nếu tất cả được build từ cùng một ứng dụng.

## 4. Chạy nhiều instance trên cùng một máy

Khi chạy nhiều tiến trình trên một máy, mỗi tiến trình cần một port riêng. Ví dụ, chạy cùng một JAR hai lần:

**Terminal A — instance thứ nhất**

~~~bash
java -jar inventory-service.jar --server.port=8081 --eureka.instance.instance-id=inventory-service:localhost:8081 --app.version=v1
~~~

**Terminal B — instance thứ hai**

~~~bash
java -jar inventory-service.jar --server.port=8082 --eureka.instance.instance-id=inventory-service:localhost:8082 --app.version=v1
~~~

Hai tiến trình có cùng spring.application.name=inventory-service, nhưng dùng port và instance ID khác nhau. Cả hai đăng ký vào cùng Eureka Server.

Có thể truyền cấu hình tương tự bằng biến môi trường:

~~~bash
export SERVER_PORT=8081
export INSTANCE_ID=inventory-service:localhost:8081
export APP_VERSION=v1
~~~

Trên Windows PowerShell, thiết lập biến môi trường trong từng cửa sổ terminal trước khi chạy JAR:

~~~powershell
$env:SERVER_PORT = "8081"
$env:INSTANCE_ID = "inventory-service:localhost:8081"
$env:APP_VERSION = "v1"
java -jar .\inventory-service.jar
~~~

Mở cửa sổ PowerShell khác và dùng port cùng instance ID khác cho tiến trình thứ hai. Không chạy hai tiến trình cùng bind vào một địa chỉ IP và một port, vì hệ điều hành sẽ từ chối bind port thứ hai.

Nếu các instance chạy trên những máy khác nhau, chúng có thể dùng cùng port nội bộ, ví dụ đều là 8080. Khi đó instance ID phải phân biệt được hostname hoặc địa chỉ của từng máy.

## 5. Chạy nhiều instance trong container

Trong Docker hoặc Kubernetes, mỗi container/pod có network namespace riêng. Nhiều container có thể cùng lắng nghe port 8080 bên trong container, vì mỗi container có địa chỉ mạng riêng. Provider vẫn dùng cùng service name, nhưng instance ID và địa chỉ đăng ký phải phân biệt được từng container.

Ví dụ các service trong Compose:

~~~yaml
services:
  inventory-a:
    image: inventory-service:1.0
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      EUREKA_SERVER_URL: http://eureka-server:8761/eureka/
      INSTANCE_ID: inventory-service:inventory-a:8080
      APP_VERSION: "1.0"

  inventory-b:
    image: inventory-service:1.0
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      EUREKA_SERVER_URL: http://eureka-server:8761/eureka/
      INSTANCE_ID: inventory-service:inventory-b:8080
      APP_VERSION: "1.0"
~~~

Đây là phần service minh họa; hai container còn phải cùng tham gia network có thể truy cập Eureka Server. Không gán cùng một container_name cố định cho nhiều replica. Nếu dùng Docker Compose scale hoặc Kubernetes Deployment, nên tạo instance ID theo hostname/pod name để tránh trùng lặp.

Trong container, địa chỉ localhost trỏ về chính container. Provider phải đăng ký địa chỉ có thể truy cập từ consumer, thường là IP hoặc hostname của container/pod trong network chung. Nếu Eureka hiển thị instance nhưng địa chỉ được công bố không định tuyến được từ consumer, discovery có thể thành công trong khi HTTP request thất bại.

Không publish cùng một host port cố định cho nhiều container trên cùng máy. Nếu cần debug trực tiếp từ host, hãy dùng port mapping riêng cho từng container hoặc truy cập qua consumer/load balancer.

## 6. Xác nhận nhiều instance đã đăng ký

Sau khi khởi động các tiến trình, mở Eureka dashboard, thường là:

~~~text
http://localhost:8761
~~~

Tìm application INVENTORY-SERVICE. Cần thấy số lượng instance đúng với số tiến trình đã khởi động. Mỗi dòng phải có instance ID khác nhau, địa chỉ host/port phù hợp và trạng thái hiện tại.

Có thể xác minh thêm qua REST endpoint của Eureka:

~~~bash
curl -H "Accept: application/json" http://localhost:8761/eureka/apps/INVENTORY-SERVICE
~~~

Response JSON chứa application và các instance record. Các trường hữu ích khi kiểm tra gồm:

- instanceId: định danh tiến trình.
- hostName: hostname mà instance công bố.
- ipAddr: địa chỉ IP được đăng ký.
- port: cổng HTTP.
- status: trạng thái mà Eureka đang ghi nhận.
- metadata: thông tin bổ sung do client đăng ký.

REST endpoint và dashboard có thể khác nhau tùy cấu hình bảo mật, content negotiation và phiên bản Eureka. Nếu endpoint trả về 401/403, hãy kiểm tra xác thực của registry thay vì kết luận rằng không có instance.

## 7. Consumer gọi theo service name

Consumer không cần biết port riêng của từng instance. Nó gọi service name và để Spring Cloud LoadBalancer chọn một instance từ registry.

Cấu hình dependency cho consumer gồm Eureka Client và Spring Cloud LoadBalancer. Với WebClient, khai báo builder có annotation @LoadBalanced:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Tạo client gọi đến service name:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getInstanceInfo() {
        return webClient.get()
                .uri("http://inventory-service/api/instance")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

URI dùng inventory-service thay vì IP và port cụ thể. LoadBalancer lấy các instance ứng viên theo service name, chọn một instance rồi thay thế host/port logic bằng địa chỉ thực tế trước khi gửi request.

Nếu dùng một WebClient builder không có @LoadBalanced, hostname inventory-service có thể được xử lý như DNS hostname thông thường và không được phân giải qua Eureka. Vì vậy cần kiểm tra đúng bean được inject vào client.

Với cấu hình mặc định, Spring Cloud LoadBalancer thường sử dụng thuật toán round-robin để luân phiên chọn instance trong danh sách. Có thể cấu hình supplier hoặc thuật toán khác khi cần. Round-robin không bảo đảm mọi request ngắn sẽ chia đều tuyệt đối: danh sách instance, cache, request đồng thời và trạng thái lỗi đều ảnh hưởng kết quả.

## 8. Quan sát instance được chọn

Provider nên có endpoint trả về thông tin nhận diện tiến trình. Ví dụ:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceInfoController {

    @Value("${spring.application.name}")
    private String serviceName;

    @Value("${eureka.instance.instance-id}")
    private String instanceId;

    @Value("${app.version:dev}")
    private String version;

    @GetMapping("/api/instance")
    public Map<String, String> instance() {
        return Map.of(
                "service", serviceName,
                "instanceId", instanceId,
                "version", version);
    }
}
~~~

Khi gọi consumer nhiều lần, quan sát instanceId trong response. Nếu request lần lượt được gửi đến nhiều instance, kết quả sẽ có ID khác nhau. Nếu luôn nhận cùng một ID, kiểm tra số instance trong registry, danh sách mà consumer nhận được, cấu hình LoadBalancer và cache.

Có thể log instance ID ở provider cho mỗi request. Log giúp đối chiếu giữa request của consumer, instance đã xử lý và trạng thái registry tại thời điểm đó. Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm trong log.

## 9. Vòng đời của nhiều instance

Mỗi tiến trình Eureka Client có vòng đời đăng ký riêng:

1. **Khởi động:** tiến trình đọc service name, instance ID, hostname/IP và port.
2. **Đăng ký:** client gửi instance record lên Eureka Server.
3. **Gia hạn lease:** client định kỳ gửi heartbeat để thông báo instance vẫn còn hoạt động.
4. **Tra cứu:** consumer lấy danh sách instance theo service name; dữ liệu có thể được cache.
5. **Dừng có kiểm soát:** client cố gắng hủy đăng ký khi ứng dụng tắt.
6. **Dừng đột ngột:** nếu không nhận heartbeat, registry có thể giữ instance đến khi lease hết hạn và cơ chế eviction xử lý.

Các thời gian heartbeat, lease expiration và registry fetch được điều khiển bởi cấu hình và phiên bản. Không giả định instance chết sẽ biến mất ngay khỏi mọi consumer. Eureka có cơ chế self-preservation để hạn chế xóa hàng loạt registration khi phát hiện heartbeat giảm bất thường. Cơ chế này có thể khiến một instance lỗi còn xuất hiện trong registry lâu hơn dự kiến.

Health check của ứng dụng giúp phản ánh khả năng phục vụ, nhưng cần cấu hình đúng và hiểu cách trạng thái được truyền tới Eureka. Docker health status, Kubernetes readiness và Eureka instance status là các tín hiệu khác nhau; chúng không tự đồng bộ trong mọi cấu hình.

## 10. Triển khai phiên bản mới và giảm instance

Khi triển khai phiên bản mới, có thể chạy instance cũ và mới đồng thời dưới cùng service name nếu chúng tương thích API. Ví dụ:

| Instance | Service name | Metadata version | Trạng thái |
|---|---|---|---|
| inventory-v1-a | inventory-service | v1 | UP |
| inventory-v1-b | inventory-service | v1 | UP |
| inventory-v2-a | inventory-service | v2 | UP |

Khi phiên bản mới đã sẵn sàng, consumer có thể nhận cả instance v1 và v2. Điều này hữu ích cho rolling update nhưng cũng có nghĩa request có thể đến phiên bản cũ hoặc mới. Nếu hai phiên bản không tương thích, không nên cho chúng dùng chung service name mà không có chiến lược routing phù hợp.

Metadata version chỉ là thông tin. Để canary hoặc blue/green, cần cấu hình routing, filter hoặc service name riêng, chẳng hạn inventory-service-v1 và inventory-service-v2, tùy mô hình triển khai. Không dựa vào metadata đơn thuần để giả định LoadBalancer sẽ ưu tiên phiên bản mới.

Khi giảm số instance, dừng tiến trình có kiểm soát để client deregister. Với hệ thống có lưu lượng cao, cần drain request đang xử lý trước khi tắt instance. Nếu tắt container đột ngột, consumer có thể tiếp tục chọn instance trong một khoảng thời gian trước khi registry và cache cập nhật.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Chỉ thấy một instance dù chạy hai tiến trình | Cả hai dùng cùng instance ID hoặc một tiến trình chưa đăng ký | So sánh instance ID và log đăng ký |
| Hai tiến trình không cùng bind được port | Cùng host và cùng port | Chọn port khác nhau hoặc chạy trên host/container riêng |
| Dashboard có nhiều instance nhưng request chỉ tới một | Consumer chỉ nhận một instance, cache chưa cập nhật hoặc bean không có LoadBalancer | Kiểm tra danh sách discovery và bean client |
| Instance xuất hiện nhưng request timeout | Địa chỉ công bố không truy cập được từ consumer | Kiểm tra IP, hostname, port và network route |
| Instance chết vẫn còn trong dashboard | Lease chưa hết hạn, heartbeat chưa timeout hoặc self-preservation | Kiểm tra heartbeat, eviction và trạng thái registry |
| Instance mới ghi đè instance cũ | Instance ID bị trùng | Tạo ID dựa trên hostname/pod và port hoặc ID triển khai |
| Request phân phối không đều | Ít request, tải đồng thời, cache hoặc thuật toán chọn | Ghi log instance ID và quan sát trên tập request đủ lớn |
| Consumer không phân giải được service name | WebClient không được đánh dấu @LoadBalanced hoặc thiếu starter | Kiểm tra dependency và bean được inject |

Khi chẩn đoán, phân biệt ba câu hỏi:

- Eureka có lưu đủ instance record không?
- Consumer có nhận được danh sách instance mới không?
- LoadBalancer có chọn được địa chỉ mà consumer truy cập được không?

Nếu trả lời riêng từng câu hỏi, sẽ dễ xác định lỗi nằm ở provider registration, registry, discovery cache, LoadBalancer hay mạng.

## 12. Bảo mật và vận hành

Mỗi instance tự đăng ký địa chỉ và metadata vào registry. Nếu một ứng dụng không đáng tin có thể đăng ký tùy ý dưới service name của dịch vụ quan trọng, consumer có nguy cơ gửi dữ liệu đến instance giả mạo. Vì vậy:

- Giới hạn mạng có thể truy cập Eureka Server.
- Bật xác thực và TLS cho registry theo yêu cầu môi trường.
- Chỉ cho phép workload được cấp quyền đăng ký vào các service name tương ứng.
- Không lưu secret hoặc dữ liệu nhạy cảm trong metadata.
- Không coi trạng thái UP là bằng chứng caller được phép gọi API; provider vẫn phải xác thực và phân quyền.
- Theo dõi số instance, trạng thái, heartbeat, thời gian đăng ký và lỗi gọi giữa service.
- Đặt timeout và retry có giới hạn; chỉ retry thao tác có thể lặp an toàn hoặc đã có cơ chế chống trùng.

Khi vận hành, cần kiểm tra cả số instance dự kiến và số instance thực tế. Một dịch vụ có ba replica theo cấu hình nhưng chỉ một instance đăng ký thành công vẫn có thể tạo điểm nghẽn. Ngược lại, các registration cũ chưa được dọn dẹp có thể khiến consumer thử gửi request tới địa chỉ không còn hoạt động.

## 13. Quy trình thực hành

Thực hiện theo thứ tự sau để kiểm tra nhiều instance:

1. Khởi động Eureka Server và xác nhận dashboard sẵn sàng.
2. Cấu hình hai tiến trình có cùng spring.application.name=inventory-service.
3. Gán port và instance ID riêng cho từng tiến trình.
4. Khởi động cả hai tiến trình và chờ registration xuất hiện trong Eureka.
5. Xác nhận mỗi instance có địa chỉ host/port truy cập được từ consumer.
6. Cấu hình consumer dùng Eureka Client và Spring Cloud LoadBalancer.
7. Gửi nhiều request qua service name, quan sát instance ID trả về.
8. Dừng một instance có kiểm soát và quan sát quá trình deregister.
9. Dừng đột ngột một instance trong môi trường lab để quan sát heartbeat, lease expiration và cập nhật registry.
10. Khởi động lại instance và xác nhận nó đăng ký lại với định danh phù hợp.

Khi hoàn tất, cần nắm rõ quan hệ: **nhiều tiến trình cùng service name tạo thành một dịch vụ logic; mỗi tiến trình có instance ID và địa chỉ riêng; Eureka lưu danh sách instance; consumer tra cứu theo service name; LoadBalancer chọn instance cho từng request.** Đây là nền tảng để mở rộng số replica và triển khai rolling update trong hệ thống Spring Cloud.

