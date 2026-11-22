# Trạng thái đăng ký và giá trị hỗ trợ theo implementation

Spring Cloud Commons định nghĩa abstraction ServiceRegistry để ứng dụng đăng ký, hủy đăng ký và thay đổi trạng thái của một service instance. Tuy nhiên, **trạng thái không phải một enum dùng chung với cùng ý nghĩa cho mọi registry**. Eureka, Consul và Zookeeper lưu trạng thái theo mô hình riêng; Kubernetes còn để nền tảng điều khiển việc đưa Pod vào Service endpoint thay vì cho ứng dụng tự đổi trạng thái đăng ký.

Vì vậy, khi gọi API chung hoặc endpoint Actuator, không nên mặc định mọi implementation đều chấp nhận UP, DOWN và OUT_OF_SERVICE. Cần biết implementation đang chạy, giá trị mà nó hỗ trợ, cách nó lưu trạng thái và thành phần nào dùng trạng thái đó để lọc instance.

Bài học thuộc chương ServiceRegistry của module SPRING_CLOUD_CORE. Nội dung tập trung vào hợp đồng ServiceRegistry, endpoint quản trị trạng thái, sự khác nhau giữa Eureka, Consul, Zookeeper và Kubernetes, cùng cách kiểm chứng trạng thái trong quá trình vận hành.

## 1. ServiceRegistry là abstraction, không phải một state machine chung

Spring Cloud Commons cung cấp các interface để ứng dụng không phụ thuộc trực tiếp vào một nhà cung cấp registry:

- **Registration:** đại diện cho thông tin một instance được đăng ký. Đây là marker interface trong abstraction chung; implementation cụ thể cung cấp dữ liệu như service ID, host, port, URI, metadata và chế độ bảo mật.
- **ServiceRegistry:** cung cấp thao tác đăng ký, hủy đăng ký, đóng registry và đọc/ghi trạng thái của một Registration.
- **DiscoveryClient:** cho phép ứng dụng truy vấn danh sách service và instance mà không cần gọi API riêng của Eureka, Consul hay Zookeeper.
- **ServiceInstance:** mô tả một instance được discovery trả về cho consumer.

ServiceRegistry có các thao tác chính:

| Thao tác | Mục đích |
| --- | --- |
| register(registration) | Đăng ký instance với registry |
| deregister(registration) | Hủy đăng ký instance |
| setStatus(registration, status) | Yêu cầu implementation cập nhật trạng thái |
| getStatus(registration) | Đọc trạng thái theo cách implementation cung cấp |
| close() | Đóng hoặc giải phóng tài nguyên của registry client nếu cần |

Tham số status trong hợp đồng chung là chuỗi. Spring Cloud không áp đặt một enum chuẩn để mọi registry phải hỗ trợ cùng tập giá trị. Tài liệu Commons yêu cầu ứng dụng đọc danh sách giá trị từ tài liệu của implementation đang dùng.

Điều đó có nghĩa:
- Cùng một chuỗi có thể được hiểu khác nhau giữa hai registry.
- Một implementation có thể chỉ hỗ trợ hai trạng thái quản trị.
- Một implementation có thể lưu status dưới dạng metadata rồi để LoadBalancer lọc.
- Một implementation có thể không cho ứng dụng điều khiển trạng thái đăng ký.
- Giá trị GET trả về có thể là chuỗi, object hoặc cấu trúc đặc thù, tùy implementation.

## 2. Phân biệt trạng thái đăng ký, trạng thái health và trạng thái process

Một service có nhiều trạng thái liên quan nhưng không đồng nhất:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Process state | JVM/container còn chạy không? | Running, stopped |
| Application health | Ứng dụng và dependency có hoạt động đúng không? | UP, DOWN, OUT_OF_SERVICE |
| Registration status | Registry đang xem instance ở trạng thái nào? | UP hoặc OUT_OF_SERVICE theo implementation |
| Discovery visibility | Consumer có nhận instance từ discovery/load balancer không? | Có trong danh sách hoặc bị lọc |
| Readiness | Instance có sẵn sàng nhận traffic mới không? | Kubernetes Ready/NotReady |

Một JVM có thể đang chạy nhưng registration đã được đưa OUT_OF_SERVICE để rút khỏi traffic. Một instance có thể còn được đăng ký nhưng health check của Consul đang critical. Một Pod có thể còn chạy nhưng readiness probe thất bại nên Kubernetes loại Pod khỏi EndpointSlice phục vụ Service.

Không nên coi một giá trị status là bằng chứng đầy đủ cho tất cả các trạng thái còn lại.

## 3. Endpoint Service Registry của Actuator

Spring Cloud Commons cung cấp endpoint Actuator có ID là serviceregistry. Với management base path mặc định của Spring Boot, URL thường là:

~~~text
GET  /actuator/serviceregistry
POST /actuator/serviceregistry
~~~

Endpoint dựa trên một bean Registration trong Spring ApplicationContext. GET gọi getStatus() trên ServiceRegistry tương ứng. POST nhận JSON có trường status rồi chuyển giá trị đó tới implementation để cập nhật.

Ví dụ đưa instance ra khỏi traffic:

~~~bash
curl -X POST http://localhost:8080/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"OUT_OF_SERVICE"}'
~~~

Ví dụ yêu cầu instance trở lại trạng thái hoạt động:

~~~bash
curl -X POST http://localhost:8080/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"UP"}'
~~~

Hai ví dụ trên chỉ phù hợp với implementation có hỗ trợ các giá trị tương ứng. Không gửi một giá trị cho tất cả môi trường chỉ vì endpoint URL giống nhau.

Nếu management port hoặc base path được cấu hình riêng, URL sẽ thay đổi. Hãy kiểm tra Actuator links và cấu hình runtime.

### 3.1. Bật exposure và bảo vệ endpoint

Ví dụ expose endpoint qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - serviceregistry
~~~

Exposure chỉ làm endpoint có thể được truy cập qua web; nó không thay thế authentication, authorization hoặc network policy.

Endpoint này thay đổi trạng thái instance trong hệ thống discovery. Nếu người không có quyền gọi POST, họ có thể đưa service ra khỏi traffic hoặc đưa một instance không khỏe trở lại trạng thái được xem xét. Vì vậy:
- Chỉ expose trên management network cần thiết.
- Bảo vệ bằng Spring Security hoặc cơ chế quản trị tương đương.
- Cấp quyền ghi trạng thái cho nhóm vận hành được phép.
- Ghi audit gồm instance, giá trị cũ/mới, người gọi và thời điểm.
- Không đưa management endpoint ra Internet công khai.
- Xác minh kết quả ở registry và consumer sau khi gọi.

### 3.2. Response GET không nhất thiết là một chuỗi đơn giản

Commons mô tả GET là đọc trạng thái của Registration, nhưng cấu trúc dữ liệu cụ thể do implementation quyết định. Có implementation trả về status string; có implementation có thể trả thêm thông tin như trạng thái ghi đè. Đừng viết client quản trị giả định response luôn có một schema giống nhau nếu ứng dụng hỗ trợ nhiều registry.

## 4. Auto-registration và vòng đời đăng ký

Trong nhiều integration, ứng dụng Spring Boot tự đăng ký instance khi khởi động. Auto-registration thường được bật mặc định nếu discovery implementation phù hợp có mặt trên classpath.

Có thể tắt auto-registration bằng:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Hoặc cấu hình trên annotation EnableDiscoveryClient với autoRegister=false trong những trường hợp cần điều khiển bằng Java configuration. Tài liệu Commons cũng mô tả hai event:
- InstancePreRegisteredEvent: phát trước khi instance được đăng ký.
- InstanceRegisteredEvent: phát sau khi đăng ký hoàn tất.

Hai event không được phát khi auto-registration bị tắt qua spring.cloud.service-registry.auto-registration.enabled.

Việc tắt auto-registration không có nghĩa mọi registry đều hỗ trợ cùng một cơ chế manual registration. Cần kiểm tra implementation cụ thể. Đặc biệt, Spring Cloud Kubernetes để Kubernetes quản lý Service/Endpoint; hai cấu hình tắt auto-registration của Commons không có tác dụng tương tự trong implementation này.

## 5. Eureka: UP, DOWN, OUT_OF_SERVICE và UNKNOWN

Eureka có mô hình trạng thái instance riêng. Tài liệu Spring Cloud Commons nêu các giá trị được hỗ trợ qua Service Registry endpoint gồm:

| Giá trị | Ý nghĩa vận hành |
| --- | --- |
| UP | Instance được xem là sẵn sàng phục vụ |
| DOWN | Instance không hoạt động bình thường |
| OUT_OF_SERVICE | Instance vẫn được đăng ký nhưng được đưa ra khỏi traffic |
| UNKNOWN | Không xác định được trạng thái |

Eureka cũng có các trạng thái nội bộ trong mô hình InstanceInfo và có thể có trạng thái khởi tạo như STARTING tùy phiên bản/thời điểm vòng đời. Khi dùng endpoint chung, hãy dựa trên danh sách được tài liệu Spring Cloud Netflix của phiên bản đang chạy hỗ trợ; không tự suy ra rằng mọi trạng thái native đều được hỗ trợ giống nhau qua mọi API.

### 5.1. OUT_OF_SERVICE khác với deregister

OUT_OF_SERVICE đưa instance ra khỏi traffic nhưng vẫn giữ registration trên Eureka. Đây là cách hữu ích cho blue/green deployment, bảo trì hoặc drain instance trước khi dừng process.

Deregister xóa registration khỏi registry. Hai thao tác khác nhau:

| Hành động | Registration còn tồn tại? | Ý định |
| --- | --- | --- |
| setStatus(OUT_OF_SERVICE) | Có | Tạm rút instance khỏi traffic |
| setStatus(UP) | Có | Đưa instance trở lại trạng thái hoạt động |
| deregister() | Không còn registration sau khi xử lý | Kết thúc đăng ký instance |

Nếu cần rollback một đợt triển khai, giữ instance ở OUT_OF_SERVICE có thể giúp thao tác đưa lại traffic dễ hơn so với xóa registration hoàn toàn. Tuy nhiên, cần chờ trạng thái lan truyền tới registry và client cache trước khi tắt instance.

### 5.2. Health check của Eureka không tự bật theo Actuator

Theo mặc định, Eureka dùng heartbeat để xác định client còn sống. Nếu không bật Eureka health check integration, Spring Cloud Discovery Client không tự truyền trạng thái health hiện tại của Spring Boot Actuator sang Eureka; sau khi đăng ký thành công, Eureka có thể tiếp tục công bố instance là UP.

Có thể bật:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Tài liệu Spring Cloud Netflix lưu ý thuộc tính này nên được đặt trong application.yml. Đặt nó trong bootstrap.yml có thể dẫn tới side effect, chẳng hạn instance đăng ký với trạng thái UNKNOWN.

Nếu cần quy tắc riêng để ánh xạ health sang Eureka status, có thể triển khai HealthCheckHandler theo API Eureka được phiên bản tương ứng hỗ trợ.

Eureka còn có cấu hình trạng thái khởi tạo qua eureka.instance.initial-status (mặc định UP). Đây là giá trị lúc khởi tạo registration, khác với thao tác đổi trạng thái runtime bằng ServiceRegistry.setStatus(). Ở phía consumer, eureka.client.filter-only-up-instances mặc định bật để chỉ lấy các instance UP trong một số luồng truy vấn. Hãy kiểm tra giá trị hiệu lực của cả hai thuộc tính khi một instance có trong registry nhưng không được LoadBalancer chọn.

### 5.3. Status override và heartbeat

Eureka có thể duy trì trạng thái ghi đè từ server. Điều này quan trọng khi vận hành:
- Nếu instance được đưa OUT_OF_SERVICE từ phía server, heartbeat UP thông thường không nhất thiết đưa nó trở lại UP ngay.
- Cần dùng đúng thao tác status/reset override mà Eureka implementation cung cấp.
- Kiểm tra cả status và overridden status khi điều tra sự khác nhau giữa trạng thái local và trạng thái server.
- Không coi một log local là bằng chứng duy nhất rằng mọi Eureka peer/client đã thấy trạng thái mới.

### 5.4. Kiểm tra Eureka

Sau khi gọi POST:
1. Đọc status qua Actuator của ứng dụng.
2. Kiểm tra InstanceInfo trên Eureka Server.
3. Kiểm tra các Eureka client đã nhận bản cập nhật.
4. Kiểm tra cấu hình lọc instance, ví dụ chỉ nhận instance UP.
5. Gửi request qua Spring Cloud LoadBalancer để xác minh instance đã bị loại hoặc được đưa trở lại.

Không chỉ kiểm tra response HTTP của Actuator. Một response thành công không chứng minh cache discovery ở tất cả consumer đã cập nhật ngay lập tức.

## 6. Consul: UP và OUT_OF_SERVICE qua maintenance mode

Spring Cloud Consul dùng HTTP API của Consul để đăng ký và discovery service. Service registration có thể chứa host, port, ID, name, tags và metadata. Consul thường tạo HTTP health check gọi Actuator health endpoint; nếu health check thất bại, service instance được đánh dấu critical.

Đối với thao tác setStatus của ConsulServiceRegistry, các giá trị quản trị được hỗ trợ là:

| Giá trị | Hành vi |
| --- | --- |
| UP | Tắt service maintenance mode |
| OUT_OF_SERVICE | Bật service maintenance mode |

Consul implementation dùng maintenance mode để đưa service instance ra khỏi lựa chọn traffic. Không nên gửi DOWN hoặc UNKNOWN qua ServiceRegistry endpoint với kỳ vọng Consul xử lý như Eureka; các giá trị đó không nằm trong tập giá trị mà implementation hỗ trợ cho thao tác này.

### 6.1. Maintenance mode khác với health check critical

Consul có nhiều cơ chế trạng thái:
- Maintenance mode là trạng thái được operator/agent bật để đánh dấu service đang bảo trì.
- HTTP health check phản ánh kết quả kiểm tra endpoint.
- TTL check nhận heartbeat từ ứng dụng theo chu kỳ.
- Check state của Consul có các mức passing, warning hoặc critical.

Một health check thất bại có thể làm service critical dù maintenance mode không bật. Ngược lại, service có thể bị đưa vào maintenance để ngừng nhận traffic dù endpoint health vẫn trả UP.

Vì vậy, không dùng getStatus từ ServiceRegistry như một bản tổng hợp thay thế cho toàn bộ health checks của Consul. Hãy kiểm tra Consul health API/UI và Actuator health riêng.

### 6.2. TTL application status

Với TTL heartbeat, Spring Cloud Consul có thể lấy trạng thái từ Actuator health endpoint. Nếu không có health endpoint hoặc ứng dụng không phải Actuator app, integration có thể giả định ứng dụng khỏe theo mặc định. Có thể tắt việc dùng Actuator health cho TTL check hoặc cung cấp ApplicationStatusProvider riêng theo tài liệu phiên bản.

Ví dụ cấu hình TTL:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        heartbeat:
          enabled: true
          ttl: 10s
          use-actuator-health: true
~~~

Nếu dùng health group riêng, cấu hình actuator-health-group tương ứng. Hãy bảo đảm TTL interval, heartbeat interval và Consul check configuration thống nhất để tránh đánh dấu critical do heartbeat trễ.

### 6.3. Quy trình đưa Consul instance ra khỏi traffic

1. Xác định đúng instance ID.
2. Đưa instance vào OUT_OF_SERVICE qua ServiceRegistry.
3. Kiểm tra maintenance mode trong Consul.
4. Chờ consumer/load balancer loại instance khỏi danh sách phù hợp.
5. Drain request/message đang chạy.
6. Dừng hoặc triển khai instance.
7. Khi đã sẵn sàng, đặt lại UP.
8. Kiểm tra maintenance mode đã tắt và health check đang passing.

Không xóa registration nếu mục tiêu chỉ là tạm rút instance để bảo trì.

## 7. Zookeeper: trạng thái trong metadata và lọc ở LoadBalancer

Spring Cloud Zookeeper cũng triển khai ServiceRegistry. Do Curator Service Discovery không có sẵn hành vi OUT_OF_SERVICE giống Eureka, Spring Cloud Zookeeper lưu trạng thái vào metadata của service instance.

Tài liệu mô tả hành vi:
- Instance có status UP được xem là đang hoạt động.
- Instance có status khác UP và khác null bị ZookeeperServiceInstanceListSupplier lọc khỏi danh sách của Spring Cloud LoadBalancer.
- Nếu trường status rỗng, implementation coi là UP để tương thích ngược.
- Có thể POST OUT_OF_SERVICE tới Service Registry Actuator endpoint để đưa instance ra khỏi danh sách active của LoadBalancer.

Ví dụ:

~~~bash
curl -X POST http://localhost:8081/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"OUT_OF_SERVICE"}'
~~~

Đường dẫn thực tế phụ thuộc management port/base path và phiên bản endpoint.

### 7.1. Status trong metadata không phải trạng thái native của Curator

Zookeeper implementation tận dụng payload linh hoạt để lưu metadata status. Vì vậy:
- Status là metadata mà Spring Cloud Zookeeper hiểu.
- Không nên giả định mọi Curator client hoặc ứng dụng khác đều lọc theo trường này.
- Spring Cloud LoadBalancer sử dụng ZookeeperServiceInstanceListSupplier để lọc instance không UP.
- Consumer tự đọc dữ liệu Zookeeper hoặc dùng discovery client khác có thể cần quy tắc lọc riêng.

Implementation có thể lưu chuỗi status trong metadata; tuy nhiên, giá trị được tài liệu khuyến nghị cho điều khiển traffic là UP và OUT_OF_SERVICE. Nếu dùng chuỗi khác, hãy kiểm tra chính xác mọi consumer và supplier có cùng quy tắc hay không.

### 7.2. Tương thích ngược khi metadata không có status

Một số registration cũ có thể chưa có trường status. ZookeeperServiceInstanceListSupplier xem giá trị null/rỗng là UP để không làm các instance cũ biến mất khỏi danh sách. Đây là hành vi tương thích ngược, không phải khuyến nghị bỏ qua việc kiểm tra trạng thái.

Khi migrate hệ thống, hãy kiểm tra metadata của registration hiện hữu và hành vi lọc trước khi áp dụng chính sách status mới.

## 8. Kubernetes: nền tảng điều khiển registration

Trong Kubernetes, Service và EndpointSlice được quản lý bởi Kubernetes control plane dựa trên Pod, label selector, readiness và các controller. Ứng dụng không tự đăng ký Pod vào một registry bên ngoài theo cách Eureka hoặc Consul thực hiện.

Spring Cloud Kubernetes nêu rõ:
- Việc service registration do nền tảng Kubernetes kiểm soát.
- spring.cloud.service-registry.auto-registration.enabled không thay đổi cơ chế này.
- EnableDiscoveryClient(autoRegister=false) cũng không có hiệu lực tương tự như với registry client khác.

Do đó, không nên dùng ServiceRegistry Actuator endpoint như một cách chung để setStatus trên Kubernetes.

### 8.1. Readiness điều khiển việc nhận traffic

Kubernetes readiness probe quyết định container/Pod có sẵn sàng nhận traffic hay không. Khi Pod không Ready, endpoint controller có thể loại Pod đó khỏi EndpointSlice được dùng để phục vụ Service.

Ví dụ:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Để đưa instance khỏi traffic trong Kubernetes, có thể:
- Làm readiness probe chuyển sang NotReady qua trạng thái ứng dụng có kiểm soát.
- Dùng preStop hook và terminationGracePeriodSeconds để drain.
- Điều chỉnh Deployment rollout/replica.
- Quản lý Service selector hoặc EndpointSlice qua control plane khi có lý do phù hợp.

Không thay đổi Pod readiness chỉ bằng một chuỗi status trong ServiceRegistry của Spring Cloud Commons.

### 8.2. Health và readiness không giống nhau

Một ứng dụng có thể còn sống nhưng chưa sẵn sàng nhận request. Kubernetes phân biệt liveness, readiness và startup probe. Hãy cấu hình health group phù hợp để:
- Liveness phản ánh process có cần restart không.
- Readiness phản ánh có thể nhận traffic không.
- Startup probe bảo vệ ứng dụng khởi động chậm khỏi bị liveness kiểm tra quá sớm.

Không dùng liveness DOWN để rút traffic nếu ý định chỉ là drain; liveness failure có thể khiến container bị restart.

## 9. SimpleDiscoveryClient không phải ServiceRegistry động

Nếu không có một ServiceRegistry-backed DiscoveryClient trên classpath, Spring Cloud Commons có thể dùng SimpleDiscoveryClient với các instance được khai báo qua property. Ví dụ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8080
              - uri: http://catalog-b.internal:8080
~~~

SimpleDiscoveryClient đọc danh sách instance từ cấu hình. Nó không tương đương một registry server có thao tác setStatus/deregister runtime. Muốn thay đổi danh sách, cần thay đổi nguồn property và áp dụng cơ chế cấu hình tương ứng hoặc dùng implementation có hỗ trợ đăng ký động.

Không kỳ vọng endpoint serviceregistry hoạt động chỉ vì SimpleDiscoveryClient có mặt.

## 10. Bảng so sánh status theo implementation

| Implementation | Giá trị quản trị được hỗ trợ/được tài liệu mô tả | Cách lưu hoặc áp dụng | Điều consumer cần lưu ý |
| --- | --- | --- | --- |
| Eureka | UP, DOWN, OUT_OF_SERVICE, UNKNOWN theo tài liệu Commons endpoint; mô hình native có thể có trạng thái khác theo phiên bản | InstanceInfo/status và trạng thái override phía Eureka | Eureka health check không tự propagate nếu chưa bật; client có cache |
| Consul | UP, OUT_OF_SERVICE | UP tắt maintenance; OUT_OF_SERVICE bật maintenance | Health check passing/warning/critical là một cơ chế riêng |
| Zookeeper | UP, OUT_OF_SERVICE là giá trị điều khiển được tài liệu mô tả | Lưu status trong metadata | LoadBalancer lọc status khác UP; status rỗng được coi là UP |
| Kubernetes | Không có thao tác ServiceRegistry status chung để ứng dụng điều khiển registration | Kubernetes control plane, Pod readiness và EndpointSlice | Dùng readiness, rollout và drain |
| SimpleDiscoveryClient | Không có status mutation của registry động | Danh sách instance từ Environment properties | Cập nhật cấu hình hoặc chọn registry có hỗ trợ động |

Bảng trên mô tả hành vi của các integration Spring Cloud phổ biến, không phải danh sách enum toàn cầu. Phiên bản BOM, module discovery, server và client đều có thể ảnh hưởng hành vi cụ thể.

## 11. Đăng ký thủ công và auto-registration

Nếu ứng dụng cần tự điều khiển thời điểm đăng ký, có thể tắt auto-registration trong những implementation hỗ trợ:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Sau đó, code có thể gọi ServiceRegistry.register() hoặc deregister() với Registration cụ thể. Vì generic type của Registration phụ thuộc implementation, nên code cần được viết theo bean registry cụ thể được inject.

Ví dụ helper tổng quát:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public class RegistrationStatusOperations<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;
    private final R registration;

    public RegistrationStatusOperations(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public Object currentStatus() {
        return serviceRegistry.getStatus(registration);
    }

    public void changeStatus(String status) {
        serviceRegistry.setStatus(registration, status);
    }

    public void register() {
        serviceRegistry.register(registration);
    }

    public void deregister() {
        serviceRegistry.deregister(registration);
    }
}
~~~

Đây là helper minh họa cho một registry bean và Registration cùng kiểu. Không dùng raw type để trộn EurekaRegistration với ConsulServiceRegistry hoặc ZookeeperRegistration với registry khác.

Nếu chỉ cần lắng nghe vòng đời auto-registration, dùng InstancePreRegisteredEvent và InstanceRegisteredEvent thay vì tự tạo luồng đăng ký song song. Tránh đăng ký trùng một instance bằng cả auto-registration và manual registration.

## 12. Kiểm thử status đúng ở cả registry và consumer

Một test chỉ xác nhận setStatus không ném exception chưa đủ. Cần kiểm tra status được lưu, discovery trả dữ liệu đúng và load balancer có lọc instance theo ý định.

### 12.1. Unit test cho code điều khiển

Có thể mock ServiceRegistry để xác nhận ứng dụng gửi đúng chuỗi status cho implementation:

~~~java
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

@ExtendWith(MockitoExtension.class)
class RegistrationStatusOperationsTest {

    interface TestRegistration extends Registration {
    }

    @Mock
    ServiceRegistry<TestRegistration> serviceRegistry;

    @Mock
    TestRegistration registration;

    @Test
    void requestsOutOfServiceForDrain() {
        RegistrationStatusOperations<TestRegistration> operations =
                new RegistrationStatusOperations<>(serviceRegistry, registration);

        operations.changeStatus("OUT_OF_SERVICE");

        verify(serviceRegistry).setStatus(registration, "OUT_OF_SERVICE");
    }
}
~~~

Unit test này kiểm tra code ứng dụng. Nó không chứng minh registry server đã nhận hoặc consumer đã lọc instance.

### 12.2. Integration test theo từng implementation

| Implementation | Test cần có |
| --- | --- |
| Eureka | Đặt OUT_OF_SERVICE, đọc InstanceInfo/server state, xác nhận client không chọn instance đó; đưa UP và kiểm tra lại |
| Consul | Bật maintenance, kiểm tra Consul health/service state; tắt maintenance và xác nhận trạng thái phục hồi |
| Zookeeper | Cập nhật metadata status, kiểm tra ZookeeperServiceInstanceListSupplier lọc non-UP và xử lý metadata rỗng |
| Kubernetes | Chuyển Pod readiness sang NotReady, xác nhận EndpointSlice/Service không gửi traffic tới Pod đó |
| SimpleDiscoveryClient | Thay đổi cấu hình instance list và kiểm tra discovery đọc danh sách mới sau khi cấu hình được áp dụng |

Nên chạy integration test với phiên bản registry server và Spring Cloud BOM mà production sử dụng. Không chỉ test bằng một mock chung rồi kết luận mọi implementation tương đương.

### 12.3. Kiểm tra sau thao tác

Sau khi đổi status, xác minh:
1. Actuator endpoint chấp nhận yêu cầu.
2. ServiceRegistry.getStatus trả trạng thái phù hợp.
3. Registry server ghi nhận trạng thái hoặc metadata.
4. DiscoveryClient trả instance theo quy tắc của implementation.
5. LoadBalancer có hoặc không chọn instance theo mong muốn.
6. Request thật không tiếp tục đi tới instance đã drain.
7. Khi phục hồi, instance đã Ready/UP và nhận traffic trở lại.

## 13. Vận hành drain, bảo trì và rollback

Một quy trình drain thường gồm:

1. Chọn đúng instance ID, tránh thao tác nhầm toàn bộ service.
2. Ghi nhận health, traffic và số request/message đang xử lý.
3. Đặt trạng thái OUT_OF_SERVICE nếu implementation hỗ trợ.
4. Chờ registry và client/load balancer cập nhật.
5. Ngừng nhận công việc mới và drain request/message đang chạy.
6. Xác nhận không còn traffic mới tới instance.
7. Bảo trì hoặc triển khai phiên bản mới.
8. Kiểm tra health/readiness và dependency.
9. Đưa instance về UP hoặc Ready.
10. Xác nhận consumer đã nhìn thấy instance trở lại.

Không tắt process ngay sau khi gọi POST. Eureka client cache, Consul health checks, Zookeeper watches và LoadBalancer cache có thể có độ trễ. Hãy xác minh trạng thái từ phía consumer.

Nếu cần rollback, giữ instance ở trạng thái có thể phục hồi trong thời gian triển khai. Với Eureka/Consul, OUT_OF_SERVICE thường phù hợp cho mục tiêu này hơn deregister. Với Kubernetes, dùng rollout/replica/readiness theo cơ chế nền tảng.

## 14. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| POST trả lỗi unknown status | Giá trị không được implementation hỗ trợ | Đọc tài liệu implementation và kiểm tra đúng chuỗi |
| Actuator không có serviceregistry | Thiếu Registration/ServiceRegistry bean hoặc endpoint chưa expose | Kiểm tra dependency, auto-configuration và Actuator links |
| GET status trả giá trị khác kỳ vọng | getStatus phản ánh trạng thái local/maintenance/metadata riêng | Đối chiếu với API/UI của registry server |
| Eureka vẫn gửi traffic sau OUT_OF_SERVICE | Client cache chưa cập nhật hoặc có consumer không lọc status | Kiểm tra InstanceInfo, overridden status và LoadBalancer |
| Eureka vẫn UP dù Actuator health DOWN | Eureka health check integration chưa bật | Kiểm tra eureka.client.healthcheck.enabled và HealthCheckHandler |
| Consul trả UP nhưng health check critical | getStatus/maintenance không phải tổng hợp toàn bộ health check | Kiểm tra Consul checks và Actuator health riêng |
| Consul không chấp nhận DOWN | ConsulServiceRegistry chỉ hỗ trợ UP và OUT_OF_SERVICE cho thao tác setStatus | Dùng maintenance mode hoặc sửa health check theo đúng mục tiêu |
| Zookeeper instance cũ không có status vẫn được chọn | Status null/rỗng được xem là UP để tương thích ngược | Kiểm tra metadata và chính sách migration |
| Zookeeper raw client vẫn thấy instance OUT_OF_SERVICE | Bộ lọc nằm trong ZookeeperServiceInstanceListSupplier | Kiểm tra consumer có dùng supplier của Spring Cloud LoadBalancer không |
| Kubernetes không phản ứng với setStatus | Registration do nền tảng điều khiển | Dùng readiness, EndpointSlice và rollout |
| Tắt auto-registration không tác dụng trên Kubernetes | Kubernetes integration không điều khiển registration theo Commons flag | Thay đổi Pod/Service qua Kubernetes API |
| Instance đã UP nhưng chưa nhận traffic | Health/readiness, cache hoặc network chưa hội tụ | Kiểm tra registry, consumer cache, route và health |

### 14.1. Tìm đúng tầng lỗi

Khi trạng thái không như mong đợi, kiểm tra theo thứ tự:
1. Implementation nào đang được tạo trong ApplicationContext?
2. ServiceRegistry bean có đúng implementation và đúng Registration type không?
3. Giá trị status có nằm trong tập mà implementation hỗ trợ không?
4. setStatus có cập nhật registry server hay chỉ metadata local?
5. getStatus đang trả trạng thái nào và đọc từ đâu?
6. DiscoveryClient có nhìn thấy trạng thái mới không?
7. LoadBalancer có filter instance theo trạng thái đó không?
8. Consumer có cache hoặc policy riêng không?

Không sửa một implementation theo giả định của implementation khác.

## 15. Nguyên tắc thiết kế

- Không định nghĩa một enum status nội bộ rồi gửi tùy tiện sang mọi ServiceRegistry.
- Đặt một abstraction nghiệp vụ của ứng dụng nếu cần chuẩn hóa ý nghĩa, rồi ánh xạ rõ sang từng registry.
- Tách health, readiness, registration status và process state.
- Dùng OUT_OF_SERVICE để drain khi implementation hỗ trợ và cần giữ registration.
- Chỉ deregister khi thực sự kết thúc vòng đời registration.
- Kiểm tra implementation-specific behavior trước khi expose endpoint cho operator.
- Bảo vệ POST endpoint bằng authentication, authorization và audit.
- Xác minh cả registry server và consumer sau thao tác.
- Đưa status vào integration test cùng đúng release train.
- Với Kubernetes, điều khiển readiness/rollout qua platform API thay vì giả lập ServiceRegistry status.
- Ghi rõ tập status hợp lệ trong runbook theo môi trường triển khai.

## Ghi nhớ

ServiceRegistry cung cấp API chung để đăng ký, hủy đăng ký và đọc/ghi status, nhưng **tập giá trị và ý nghĩa status do implementation quyết định**. Eureka có UP, DOWN, OUT_OF_SERVICE và UNKNOWN theo tài liệu Commons; Consul dùng UP/OUT_OF_SERVICE thông qua maintenance mode; Zookeeper lưu status trong metadata và LoadBalancer lọc các giá trị khác UP; Kubernetes để nền tảng điều khiển registration qua readiness và EndpointSlice. Luôn xác minh status tại registry và hành vi từ consumer, không chỉ dựa vào response của endpoint Actuator.

## Tài liệu tham khảo

- Spring Cloud Commons – Common Abstractions: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Netflix – Eureka Health Checks: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul – Service Discovery and Health Checks: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Zookeeper – Service Registry and Instance Status: https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html
- Spring Cloud Kubernetes – Service Registry Implementation: https://docs.spring.io/spring-cloud-kubernetes/reference/service-registry.html

