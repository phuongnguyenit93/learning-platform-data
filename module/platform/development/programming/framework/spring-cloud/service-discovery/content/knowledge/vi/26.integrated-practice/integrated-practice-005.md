# Gây lỗi một Eureka peer và xác minh client tiếp tục khám phá

Eureka có thể chạy nhiều server peer để tăng khả năng sẵn sàng của registry. Khi một peer ngừng hoạt động, các peer còn lại vẫn có thể phục vụ client nếu chúng còn reachable và đã có dữ liệu registry cần thiết. Tuy nhiên, peer replication, client registry fetch và Spring Cloud LoadBalancer cache là các cơ chế riêng, có độ trễ riêng. Vì vậy, không thể kết luận failover thành công chỉ vì Eureka Dashboard của peer còn sống hoặc vì một request tình cờ trả HTTP 200.

Bài thực hành này dựng một cụm Eureka gồm hai peer, đăng ký provider và consumer, chủ động dừng một peer trong môi trường cô lập, sau đó xác minh client tiếp tục khám phá và gọi được service qua peer còn lại. Cuối cùng, khôi phục peer bị lỗi và kiểm tra registry hội tụ trở lại.

Nội dung thuộc module SPRING_CLOUD_SERVICE_DISCOVERY: tìm instance theo service name bằng DiscoveryClient, duy trì registration/heartbeat, đọc registry và chọn instance qua Spring Cloud LoadBalancer. Trọng tâm là kiểm tra đồng thời control plane (registry/replication) và data plane (request đến provider).

## 1. Mục tiêu và tiêu chí PASS

Sau bài thực hành, cần chứng minh được:

- Hai Eureka Server peer có thể giao tiếp và trao đổi registry.
- Provider đăng ký được vào cụm và instance xuất hiện trên các peer.
- Consumer cấu hình nhiều Eureka URL và fetch registry thành công.
- Khi dừng một peer, peer còn lại vẫn trả lời registry API.
- Consumer tiếp tục trả về instance qua DiscoveryClient và request nghiệp vụ vẫn thành công.
- Provider có thể tiếp tục renew hoặc đăng ký instance mới qua peer còn hoạt động.
- Khi peer lỗi được khôi phục, registry hai phía hội tụ lại.
- Test phân biệt được dữ liệu trong server registry, local cache của Eureka Client và cache của Spring Cloud LoadBalancer.

Tiêu chí PASS:

1. Peer còn lại vẫn reachable qua HTTP(S) và trả registry API.
2. Registry còn hoạt động có instance provider với đúng service ID và instance ID.
3. Consumer vẫn nhìn thấy instance qua DiscoveryClient trong giới hạn timeout đã đặt.
4. Request qua service ID/LoadBalancer vẫn thành công và đến đúng provider.
5. Không có lỗi discovery kéo dài vượt ngưỡng chấp nhận; các lỗi ngắn trong lúc failover được ghi nhận và đo.
6. Peer được khôi phục nhận lại dữ liệu registry sau thời gian replication/sync.
7. Không có registration trùng hoặc instance stale ngoài thời gian hội tụ được thiết kế.

## 2. Kiến trúc lab hai peer

Sử dụng hai Eureka Server:

- Peer 1: hostname eureka-peer-1, port 8761.
- Peer 2: hostname eureka-peer-2, port 8761.
- Provider: service ID payment-service, instance ID duy nhất.
- Consumer: order-service, tra cứu payment-service.

~~~mermaid
flowchart TB
    P[Payment provider] -->|Register / renew| E1[Eureka peer 1]
    P -->|Register / renew| E2[Eureka peer 2]
    E1 <-->|Peer replication| E2
    C[Order consumer] -->|Fetch registry| E1
    C -->|Failover / fetch| E2
    C -->|Load-balanced request| P
    T[Test runner] -->|Stop / restore peer 1| E1
    T -->|Check registry API| E2
~~~

Đây là sơ đồ logic. Việc client thực hiện request đến URL nào trước và khi nào chuyển sang URL kế tiếp phụ thuộc Eureka Client implementation, cấu hình và trạng thái kết nối. Peer replication là bất đồng bộ; hai server có thể tạm thời có registry view khác nhau.

Không dùng một Eureka Server đơn lẻ rồi tạo hai DNS alias trỏ cùng một process. Hai peer phải là hai tiến trình/server độc lập, có network identity và lifecycle riêng.

## 3. Cấu hình Eureka peer 1 và peer 2

Mỗi peer cần có hostname riêng và khai báo URL của peer còn lại. Trong môi trường lab, hai server có thể dùng cùng port 8761 vì chúng chạy trên hai container/host riêng.

Mỗi server cần dependency spring-cloud-starter-netflix-eureka-server và bật Eureka Server:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
~~~

Provider và consumer cần spring-cloud-starter-netflix-eureka-client. Quản lý các dependency bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án; không trộn tùy ý các release train.

### 3.1. Cấu hình peer 1

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: eureka-peer-1
    prefer-ip-address: false
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-peer-2:8761/eureka/
~~~

### 3.2. Cấu hình peer 2

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: eureka-peer-2
    prefer-ip-address: false
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-peer-1:8761/eureka/
~~~

Peer 1 và peer 2 đăng ký/fetch registry của nhau. Cấu hình register-with-eureka: true và fetch-registry: true cho phép server peer tham gia trao đổi thông tin với peer còn lại. Nếu một peer chỉ được cấu hình như server độc lập với fetch/register bị tắt, nó sẽ không hình thành topology peer như lab này.

Hai hostname phải phân giải được từ container/host của peer đối diện. Nếu chạy Docker Compose, đặt các service trong cùng network để dùng service name. Nếu chạy Kubernetes, dùng DNS ổn định cho từng peer, ví dụ StatefulSet ordinal qua headless Service hoặc Service riêng cho mỗi peer.

### 3.3. Cấu hình client provider và consumer

Provider cần đăng ký và fetch registry; consumer chỉ fetch nếu không cần đăng ký chính nó:

~~~yaml
eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    registry-fetch-interval-seconds: 5
    service-url:
      defaultZone: http://eureka-peer-1:8761/eureka/,http://eureka-peer-2:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: "payment-service:${HOSTNAME}:${server.port}"
~~~

Với consumer chỉ tra cứu:

~~~yaml
spring:
  application:
    name: order-service

eureka:
  client:
    register-with-eureka: false
    fetch-registry: true
    registry-fetch-interval-seconds: 5
    service-url:
      defaultZone: http://eureka-peer-1:8761/eureka/,http://eureka-peer-2:8761/eureka/
~~~

Giá trị fetch interval 5 giây chỉ dùng để làm lab quan sát nhanh hơn. Trong production, chọn chu kỳ theo số lượng client, tải registry và SLA hội tụ. Không giảm interval đồng loạt nếu chưa đo request rate và capacity của Eureka cluster.

Trong YAML, key defaultZone có chữ Z viết hoa theo cách cấu hình Eureka service URL. Nếu dùng biến môi trường hoặc profile, kiểm tra property binding thực tế trong application context.

### 3.4. Địa chỉ instance phải truy cập được

Peer replication chỉ giải quyết dữ liệu registry. Consumer còn phải gọi được địa chỉ provider mà instance đăng ký. Trong Docker network, provider nên công bố DNS alias/hostname mà consumer truy cập được; trong Kubernetes, chọn Service DNS hoặc Pod endpoint theo đúng mô hình load balancing.

Không công bố localhost, 127.0.0.1 hoặc 0.0.0.0 cho client ở container/host khác. Nếu registry có record nhưng request timeout, kiểm tra advertised host và port trước khi kết luận peer failover lỗi.

## 4. Khởi động lab và kiểm tra baseline

Khởi động peer 1 và peer 2 trong cùng network. Có thể dùng Docker Compose với hai container từ cùng image Eureka Server nhưng profile/config khác nhau. Mỗi peer phải expose port client 8761 trên network nội bộ.

Sau khi khởi động, kiểm tra peer endpoint:

~~~bash
curl -fsS http://eureka-peer-1:8761/actuator/health
curl -fsS http://eureka-peer-2:8761/actuator/health
~~~

Nếu Actuator health chưa expose, có thể kiểm tra Eureka API:

~~~bash
curl -i -H "Accept: application/json" \
  http://eureka-peer-1:8761/eureka/apps

curl -i -H "Accept: application/json" \
  http://eureka-peer-2:8761/eureka/apps
~~~

HTTP response thành công chỉ chứng minh endpoint trả lời; chưa chứng minh peer replication hoặc client failover. Tiếp theo, khởi động provider và đợi registration xuất hiện.

### 4.1. Xác minh peer replication

Sau khi provider đăng ký, đọc service từ cả hai peer:

~~~bash
curl -fsS -H "Accept: application/json" \
  http://eureka-peer-1:8761/eureka/apps/PAYMENT-SERVICE

curl -fsS -H "Accept: application/json" \
  http://eureka-peer-2:8761/eureka/apps/PAYMENT-SERVICE
~~~

Đối chiếu:

- Application name.
- Instance ID.
- Hostname/IP được công bố.
- Port.
- Status, thường là UP khi provider khỏe mạnh.
- Metadata/version nếu có cấu hình.

Peer replication không nhất thiết hoàn tất ngay khi một server trả lời registration. Dùng polling có timeout để chờ cả hai peer thấy đúng instance. Nếu chỉ peer nhận request registration có record, kiểm tra peer URL, DNS, firewall và log replication.

## 5. Xác minh consumer trước khi gây lỗi

Consumer nên dùng DiscoveryClient để quan sát local registry view:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentDiscoveryProbe {

    private final DiscoveryClient discoveryClient;

    public PaymentDiscoveryProbe(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findPaymentInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
~~~

Kiểm tra consumer nhìn thấy instance mong đợi:

~~~java
await()
    .atMost(Duration.ofSeconds(40))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        assertThat(discoveryClient.getInstances("payment-service"))
            .anySatisfy(instance -> {
                assertThat(instance.getInstanceId()).isEqualTo(expectedInstanceId);
                assertThat(instance.getHost()).isNotBlank();
                assertThat(instance.getPort()).isPositive();
            });
    });
~~~

Đặt thao tác đọc bên trong lambda để mỗi lần poll lấy trạng thái mới nhất. Không lấy danh sách trước rồi chờ assertion trên snapshot cũ. Timeout phải đủ cho Eureka fetch interval, server sync và startup.

Nếu dùng Spring Cloud LoadBalancer, tạo client được đánh dấu @LoadBalanced và gửi request bằng service ID. Ví dụ với RestTemplate:

~~~java
@Bean
@LoadBalanced
RestTemplate paymentRestTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

Request:

~~~java
String body = paymentRestTemplate.getForObject(
    "http://payment-service/test/identity",
    String.class
);
~~~

Ghi lại response và instance ID/version để biết request được xử lý bởi provider nào.

## 6. Gây lỗi đúng một Eureka peer

Chỉ thực hiện fault injection trong lab hoặc môi trường kiểm thử được cô lập. Không dừng peer production nếu chưa có change plan, người chịu trách nhiệm và điều kiện rollback.

Có thể dừng peer 1 bằng Docker:

~~~bash
docker stop eureka-peer-1
~~~

Hoặc trong Kubernetes, xóa đúng Pod peer 1 để StatefulSet/Deployment quản lý lifecycle:

~~~bash
kubectl delete pod eureka-peer-0 -n platform
~~~

Tên Pod là ví dụ; thay bằng Pod tương ứng với peer 1 trong lab. Không scale cả Eureka cluster về 0 và không xóa cả hai peer cùng lúc.

Sau khi dừng peer 1, xác nhận:

- Peer 1 không còn trả lời health/API.
- Peer 2 vẫn trả lời /actuator/health hoặc /eureka/apps.
- Provider và consumer vẫn có peer 2 trong danh sách defaultZone.
- Log client ghi nhận lỗi kết nối đến peer 1 và tiếp tục thử endpoint còn lại theo retry/failover behavior của client.
- Không có rule DNS/load balancer vô tình chuyển cả hai peer hostname về cùng một instance.

Kiểm tra peer 2:

~~~bash
curl -fsS http://eureka-peer-2:8761/actuator/health
curl -fsS -H "Accept: application/json" \
  http://eureka-peer-2:8761/eureka/apps/PAYMENT-SERVICE
~~~

Nếu peer 2 không có service record, client có thể vẫn tiếp tục dùng local cache cũ nhưng không chứng minh registry còn lại có dữ liệu cần thiết. Hãy sửa peer replication/baseline trước khi kết luận HA hoạt động.

## 7. Xác minh client tiếp tục khám phá

Sau khi peer 1 ngừng hoạt động, kiểm tra theo ba lớp riêng.

### 7.1. Registry còn lại vẫn có dữ liệu

Peer 2 phải trả service record với đúng instance ID. Để chứng minh Eureka registration path vẫn hoạt động khi peer 1 down, khởi động provider thứ hai với instance ID mới và xác minh peer 2 nhận bản ghi.

Ví dụ instance mới:

~~~text
serviceId: payment-service
instanceId: payment-service:payment-02:8080
status: UP
~~~

Không dùng lại instance ID của provider đầu tiên vì hai process có thể ghi đè registration hoặc làm kết quả test không rõ ràng.

### 7.2. DiscoveryClient của consumer vẫn trả instance

Chờ consumer local registry cache nhìn thấy instance:

~~~java
await()
    .alias("consumer continues to discover payment-service")
    .atMost(Duration.ofSeconds(40))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        List<ServiceInstance> instances =
            consumerDiscoveryClient.getInstances("payment-service");

        assertThat(instances).isNotEmpty();
        assertThat(instances).anySatisfy(instance ->
            assertThat(instance.getInstanceId()).isEqualTo(expectedInstanceId)
        );
    });
~~~

Điều kiện này chứng minh consumer discovery view có instance. Nó chưa chứng minh request data-plane thành công; cần bước tiếp theo.

### 7.3. Request qua LoadBalancer vẫn thành công

Gửi nhiều request qua service ID và ghi nhận kết quả:

~~~java
for (int i = 0; i < 100; i++) {
    String response = paymentRestTemplate.getForObject(
        "http://payment-service/test/identity",
        String.class
    );
    assertThat(response).contains("payment-service");
}
~~~

Trong test thực tế, response nên chứa instance ID và version. Thu thập số request thành công, lỗi timeout, connection refused và 5xx. Một số request có thể lỗi ngắn trong cửa sổ failover do client đang thử peer URL hoặc refresh registry; đánh giá theo timeout/SLO đặt trước, không chỉ dựa vào một request.

Nếu consumer gọi được provider nhưng không thể truy vấn registry trong thời gian peer lỗi, có thể consumer đang dùng local registry cache. Điều đó vẫn hữu ích cho availability của request hiện tại, nhưng không chứng minh nó có thể nhìn thấy instance mới được đăng ký sau khi peer lỗi. Vì vậy cần kiểm tra cả provider registration mới và consumer discovery refresh.

## 8. Phân biệt peer failover, registry cache và data-plane availability

Ba tình huống khác nhau:

| Tình huống | Điều nó chứng minh | Điều chưa chứng minh |
|---|---|---|
| Peer 2 API vẫn trả lời | Một registry node còn hoạt động. | Consumer đã chuyển sang peer 2 hoặc có dữ liệu mới nhất. |
| Consumer DiscoveryClient vẫn trả instance | Local registry view vẫn có dữ liệu service. | Registry còn lại nhận registration mới hoặc endpoint provider vẫn reachable. |
| Request qua LoadBalancer thành công | Consumer chọn được endpoint và gọi được provider. | Peer replication đã hội tụ hoặc dữ liệu cache không stale. |
| Peer 2 nhận provider mới trong khi peer 1 down | Registration path còn hoạt động qua peer còn lại. | Peer 1 đã được đồng bộ sau khi khôi phục. |
| Peer 1 và peer 2 có cùng record sau recovery | Registry đã hội tụ ở thời điểm kiểm tra. | Không còn lỗi replication trong mọi tình huống tải/mạng. |

Không gộp các assertion thành một điều kiện duy nhất nếu mục tiêu là tìm nguyên nhân failover. Kiểm tra riêng từng lớp giúp xác định lỗi nằm ở peer replication, client URL failover, client cache hay endpoint mạng.

## 9. Hiểu hành vi cache và thời gian hội tụ

Eureka Client thường giữ local registry cache và định kỳ fetch registry. Spring Cloud LoadBalancer có thể cache danh sách ServiceInstance riêng. Khi một peer down:

- Consumer có thể tiếp tục dùng local registry cache trong khi một URL registry không truy cập được.
- Client có thể cần thử peer URL còn lại trước khi fetch thành công.
- Registry fetch interval ảnh hưởng thời điểm consumer nhìn thấy registration mới.
- LoadBalancer cache có thể tiếp tục giữ danh sách đã lấy từ DiscoveryClient.
- Nếu tất cả peer không truy cập được, client có thể tiếp tục dùng dữ liệu cũ nhưng không thể đảm bảo nhận registration mới.

Trong lab, có thể đặt registry-fetch-interval-seconds ngắn để quan sát nhanh. Trong production, cần đo p95/p99 thời gian từ peer failure đến lần fetch thành công qua peer còn lại và từ registration mới đến khi consumer nhìn thấy instance.

Không tắt self-preservation chỉ để làm test eviction nhanh. Eureka self-preservation được thiết kế để hạn chế xóa hàng loạt instance khi heartbeat giảm bất thường; nó không thay thế peer failover. Khi có network partition, stale record có thể tồn tại lâu hơn dự kiến. Cần hiểu semantics này khi đặt assertion cho instance bị dừng.

## 10. Khôi phục peer bị lỗi

Khởi động lại peer 1:

Docker:

~~~bash
docker start eureka-peer-1
~~~

Kubernetes StatefulSet:

~~~bash
kubectl get pods -n platform -w
kubectl describe pod eureka-peer-0 -n platform
~~~

Chờ peer 1 sẵn sàng và xác minh API:

~~~bash
curl -fsS http://eureka-peer-1:8761/actuator/health
curl -fsS -H "Accept: application/json" \
  http://eureka-peer-1:8761/eureka/apps/PAYMENT-SERVICE
~~~

Sau đó chờ peer 1 nhận lại các registration từ peer 2. So sánh instance ID, host, port và status ở hai peer. Dữ liệu có thể cần thời gian đồng bộ; không assert hai response giống hệt nhau ngay tại thời điểm peer vừa mở port.

Nếu peer 1 khởi động nhưng không nhận được registry update, kiểm tra:

- Peer 1 có phân giải và kết nối được peer 2 không?
- Hai peer có cấu hình service URL chính xác và không trỏ nhầm chính nó không?
- Security group/firewall có cho phép peer-to-peer traffic không?
- Clock, TLS certificate và authentication có hợp lệ không?
- Log peer replication có lỗi Connection refused, timeout, 401/403 hoặc TLS không?
- Instance ID/service name có xung đột không?

## 11. Tự động hóa assertion bằng Awaitility

Thay vì dùng Thread.sleep, chờ điều kiện registry và consumer hội tụ.

Ví dụ helper chờ một instance:

~~~java
static void awaitInstance(
        DiscoveryClient discoveryClient,
        String serviceId,
        String instanceId) {

    await()
        .alias("instance " + instanceId + " appears in " + serviceId)
        .atMost(Duration.ofSeconds(40))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
            assertThat(discoveryClient.getInstances(serviceId))
                .anySatisfy(instance ->
                    assertThat(instance.getInstanceId()).isEqualTo(instanceId)
                );
        });
}
~~~

Ví dụ chờ peer API có record có thể dùng RestClient/RestTemplate hoặc WebTestClient gọi /eureka/apps/{APP} rồi parse JSON. Đặt request API trong lambda để mỗi poll thực hiện một lần đọc mới.

Với trạng thái peer down, không chờ “peer 1 trả lời” trong cùng điều kiện với “peer 2 còn hoạt động”. Hãy assert peer 1 không reachable theo timeout ngắn, peer 2 reachable, sau đó mới chờ consumer discovery và request. Điều này giúp test không bị treo vì endpoint lỗi.

## 12. Fault injection bổ sung

Sau kịch bản dừng một peer, có thể mở rộng lab với các lỗi có kiểm soát:

| Kịch bản | Cách gây lỗi trong lab | Điều cần quan sát |
|---|---|---|
| Peer 1 process dừng | Stop container hoặc delete đúng Pod. | Client chuyển sang peer 2, cache vẫn phục vụ. |
| Peer 1 port bị chặn | Chặn TCP từ provider/consumer đến peer 1. | Khác biệt giữa process down và network partition. |
| DNS peer 1 lỗi | Tạm thời thay DNS/alias trong test network. | UnknownHost, retry và failover URL. |
| Peer 1 chậm | Giới hạn network latency trong test environment. | Request timeout, retry/backoff và thời gian chuyển peer. |
| Provider đăng ký mới khi peer 1 down | Start provider thứ hai với instance ID khác. | Peer 2 nhận registration và consumer fetch được. |
| Peer 1 khôi phục | Start lại peer 1. | Replication catch-up và registry convergence. |
| Cả hai peer cùng down | Dừng cả hai trong lab riêng. | Client dùng cache cũ đến đâu; registration mới không thể persist. |

Không thực hiện fault injection trên production chỉ để hoàn thành bài học. Các tình huống network partition có thể gây split view hoặc stale registration khó khôi phục nếu không có quy trình vận hành.

## 13. Ma trận quan sát và tiêu chí PASS/FAIL

| Kiểm tra | PASS | FAIL |
|---|---|---|
| Peer 2 health/API | Trả lời bình thường sau khi peer 1 down. | Peer 2 không truy cập được hoặc API lỗi. |
| Provider record | Peer 2 có đúng service ID/instance ID. | Bản ghi không tồn tại hoặc sai host/port. |
| Consumer registry view | DiscoveryClient còn trả instance hợp lệ. | Danh sách rỗng kéo dài quá timeout. |
| Load-balanced request | Request tiếp tục thành công trong SLO. | Timeout/5xx vượt ngưỡng đã đặt. |
| Registration mới | Provider mới đăng ký được qua peer còn lại. | Không tạo được bản ghi mới dù peer 2 healthy. |
| Peer recovery | Peer 1 trở lại và nhận registry state. | Peer 1 không sync hoặc giữ dữ liệu sai kéo dài. |
| Cache convergence | Consumer nhìn thấy bản ghi mới và trạng thái mới trong thời gian mục tiêu. | Client tiếp tục dùng stale registry quá SLA. |
| Resource cleanup | Lab dừng sạch và không còn test instance. | Registration/test process còn tồn tại gây nhiễu lần chạy sau. |

Lưu lại timestamp của từng mốc: dừng peer, peer 2 xác nhận healthy, provider renew/register, consumer fetch thành công, request đầu tiên sau failover và peer 1 recovery. Từ các mốc này có thể tính thời gian failover và thời gian hội tụ thay vì chỉ ghi “test pass”.

## 14. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Peer 2 không có record sau khi peer 1 down | Peer replication chưa hoạt động hoặc provider chỉ đăng ký vào một peer không còn reachable. | Kiểm tra peer URLs, DNS, network và log replication trước fault injection. |
| Peer 2 có record nhưng consumer không thấy | Consumer fetch cache chưa refresh hoặc chỉ cấu hình peer 1. | Kiểm tra defaultZone, fetch interval, client log và LoadBalancer cache. |
| Consumer thấy instance nhưng request timeout | Advertised host/port không reachable. | Kiểm tra instance metadata và gọi trực tiếp URI từ consumer network. |
| Client log lặp connection error đến peer 1 | Client vẫn thử URL lỗi theo retry schedule. | Xác minh peer 2 URL có trong cấu hình, DNS và timeout; đo thời gian failover. |
| Peer 1 khởi động nhưng không hội tụ | Peer URL sai, peer replication bị chặn hoặc config mismatch. | Kiểm tra peer-to-peer connection, hostname, TLS/auth và server logs. |
| Record stale vẫn tồn tại | Lease/self-preservation/eviction chưa hội tụ. | Phân biệt graceful deregistration với crash; không tắt self-preservation tùy tiện. |
| Provider mới không đăng ký khi một peer down | Client không failover URL, peer còn lại không reachable hoặc auth/TLS lỗi. | Kiểm tra log register, registry URL list, ACL và certificate. |
| Test flaky | Dùng sleep cố định, service ID trùng hoặc timeout thấp hơn fetch interval. | Dùng Awaitility, ID riêng và timeout theo cấu hình. |

## 15. Dọn dẹp lab

Sau khi hoàn tất:

- Khôi phục peer bị dừng và xác nhận cluster healthy.
- Dừng provider/consumer test theo lifecycle để client deregister.
- Xóa container/network hoặc namespace test.
- Xác minh không còn instance ID của test trong Eureka.
- Thu thập log và metrics trước khi xóa nếu cần phân tích.
- Không để port, credential hoặc test registry mở ngoài môi trường lab.

Nếu chạy trên Kubernetes, dùng namespace riêng cho lab và xóa namespace sau khi xác minh dữ liệu cần thiết đã được lưu.

## 16. Kết luận

Một Eureka peer bị lỗi không nhất thiết làm toàn bộ service discovery ngừng hoạt động, miễn là peer còn lại reachable, có registry data và provider/consumer được cấu hình để sử dụng nó. Tuy nhiên, peer replication, client fetch cache và LoadBalancer cache hội tụ bất đồng bộ. Client có thể tiếp tục phục vụ từ local cache trong một khoảng thời gian nhưng không thể nhận registration mới nếu mọi peer đều không truy cập được.

Để chứng minh HA, hãy kiểm tra riêng peer còn hoạt động, registry record, provider registration/renew, consumer DiscoveryClient, request qua LoadBalancer và quá trình peer recovery. Gây lỗi đúng một peer trong môi trường cô lập, đo thời gian failover bằng timestamp/Awaitility và giữ self-preservation cùng các cơ chế bảo vệ mặc định trừ khi có lý do kiểm thử rõ ràng.

## Tài liệu tham khảo

- Spring Cloud Netflix — Eureka Server and Client: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Netflix Eureka — Peer Awareness and Replication: https://github.com/Netflix/eureka/wiki
- Spring Cloud Commons — DiscoveryClient: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Awaitility — Usage: https://github.com/awaitility/awaitility/wiki/Usage
