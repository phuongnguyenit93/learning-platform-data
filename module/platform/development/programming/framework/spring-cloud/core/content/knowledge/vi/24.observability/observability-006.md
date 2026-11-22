# Phân biệt kết nối registry khỏe với instance xử lý được yêu cầu

Trong hệ thống Spring Cloud, một service có thể xuất hiện trong registry và được đánh dấu **UP**, nhưng request thực tế vẫn thất bại. Ngược lại, registry có thể tạm thời không truy cập được trong khi các instance đang chạy vẫn xử lý request đã được định tuyến từ cache cục bộ.

Để đánh giá đúng tình trạng hệ thống, cần phân biệt bốn lớp:

1. **Registry availability:** client có kết nối và gọi được API của service registry hay không.
2. **Registration freshness:** registry có còn nhận heartbeat hoặc health update hợp lệ của instance hay không.
3. **Instance readiness:** instance có sẵn sàng nhận request mới với dependency và tài nguyên cần thiết hay không.
4. **Request success:** consumer có thực sự hoàn tất được luồng gọi service qua DNS, network, TLS, authentication, ứng dụng và dependency nghiệp vụ hay không.

Các lớp này liên quan nhưng không thay thế nhau. Một HTTP 200 từ registry chỉ chứng minh một endpoint của registry đã phản hồi. Một heartbeat thành công chỉ chứng minh client còn liên lạc với registry. Một readiness probe thành công cho biết instance sẵn sàng theo tiêu chí đã định nghĩa. Chỉ request thật hoặc synthetic transaction mới kiểm tra được toàn bộ đường đi mà consumer sử dụng.

Bài học thuộc chương **Quan sát** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào cách đọc đúng health signal trong Eureka, Consul, Kubernetes và Spring Cloud LoadBalancer; cách thiết kế Actuator health group; cách theo dõi metrics/traces; và cách chẩn đoán tình huống registry khỏe nhưng service vẫn không xử lý được yêu cầu.

## 1. Bốn lớp trạng thái trong hệ thống phân tán

| Lớp | Điều cần xác minh | Ví dụ tín hiệu | Điều tín hiệu chưa chứng minh |
| --- | --- | --- | --- |
| Registry availability | Registry API hoặc agent có phản hồi không? | HTTP probe tới Eureka/Consul, health endpoint của registry | Instance đã đăng ký còn sống hoặc xử lý request được |
| Registration freshness | Registry còn nhận thông tin cập nhật của instance không? | Eureka heartbeat/lease, Consul check, registration metadata | Thread pool, database, broker hoặc luồng nghiệp vụ của instance đang tốt |
| Instance readiness | Ứng dụng có thể nhận traffic mới không? | Actuator readiness, Kubernetes Ready, health check của registry | Mọi request nghiệp vụ đều thành công |
| Request success | Consumer có gọi và nhận kết quả đúng không? | HTTP/gRPC response, synthetic transaction, error rate | Các instance khác hoặc mọi luồng chức năng đều khỏe |

Một số ví dụ:

- Eureka Server trả HTTP 200 nhưng một instance trong registry đã ngừng xử lý request.
- Eureka nhận heartbeat đều đặn từ JVM đang chạy, nhưng database pool của ứng dụng đã cạn.
- Consul đánh dấu HTTP check passing vì endpoint health trả 200, nhưng một endpoint nghiệp vụ trả 500 do dữ liệu hoặc quyền truy cập.
- Kubernetes Pod Ready nhưng một luồng nghiệp vụ cụ thể vẫn lỗi vì dependency không được đưa vào readiness check.
- Registry tạm thời không truy cập được, nhưng consumer vẫn dùng danh sách instance trong cache và request tiếp tục thành công trong một khoảng thời gian.

Không dùng một chữ **UP** để kết luận toàn bộ bốn lớp đều khỏe.

## 2. Control plane và data plane

Registry thuộc control plane: nó lưu và phân phối thông tin instance. Request giữa các service thuộc data plane: nó đi qua DNS, route, load balancer, network policy, TLS, server socket và code xử lý request.

~~~mermaid
flowchart TD
    subgraph CP["Control plane"]
        REG["Service Registry"]
        CLIENT["Discovery Client"]
        HB["Heartbeat / Health update"]
        REG <--> CLIENT
        CLIENT --> HB
        HB --> REG
    end

    subgraph DP["Data plane"]
        CALLER["Consumer"]
        LB["Spring Cloud LoadBalancer"]
        INSTANCE["Service instance"]
        DEP["Database / Broker / External API"]
        CALLER --> LB
        LB --> INSTANCE
        INSTANCE --> DEP
    end

    REG -->|"Instance metadata / status"| LB
    INSTANCE -->|"Readiness / health signal"| CLIENT
~~~

Sơ đồ cho thấy registry cung cấp dữ liệu để chọn instance, nhưng request vẫn đi qua đường mạng riêng. Registry không đứng trên mọi request; sau khi nhận danh sách instance, client có thể cache và sử dụng danh sách đó cho nhiều lần gọi.

Do đó, hai câu hỏi cần được theo dõi riêng:

- **Control plane:** consumer có lấy được danh sách instance mới và đúng không?
- **Data plane:** consumer có kết nối và hoàn tất request tới instance đã chọn không?

Nếu control plane có lỗi, dữ liệu discovery có thể cũ. Nếu data plane có lỗi, registry vẫn có thể hoạt động bình thường và tiếp tục công bố instance.

## 3. Registry API khỏe không đồng nghĩa registration khỏe

Một phép thử TCP/HTTP tới registry thường kiểm tra một số điều như:
- DNS của registry phân giải được.
- Port registry đang mở.
- TLS handshake thành công.
- API endpoint phản hồi.
- Credential có quyền đọc hoặc ghi nếu test thực hiện thao tác có xác thực.

Nhưng một phép thử đơn giản tới registry không xác nhận:
- Instance đã đăng ký có đúng hostname/IP/port.
- Registration còn mới hay đã quá hạn.
- Health check của instance đang passing.
- Consumer đã nhận được bản cập nhật.
- Client-side cache đã loại bỏ instance không khỏe.
- Request tới instance có hoàn tất.

Ví dụ, lệnh sau chỉ kiểm tra endpoint health của registry:

~~~bash
curl -i https://registry.internal/actuator/health
~~~

Nếu response là **UP**, điều đó phản ánh health của chính ứng dụng registry theo các HealthContributor đã cấu hình. Nó không kiểm tra mọi service instance mà registry quản lý.

Tương tự, gọi API liệt kê service thành công chỉ chứng minh registry trả được dữ liệu. Cần kiểm tra record của từng instance, timestamp/lease/check state và kết quả request từ consumer.

### 3.1. Đọc registration theo từng instance

Khi kiểm tra một service, ghi nhận tối thiểu:

- Service ID và instance ID.
- Hostname/IP và port được quảng bá.
- Trạng thái registration.
- Thời điểm cập nhật/heartbeat hoặc lần check gần nhất nếu registry cung cấp.
- Health check URL/path và trạng thái check.
- Metadata cần thiết như zone, version hoặc management port.
- Consumer nào đang đọc record và có cache bao lâu.

Một record có trạng thái tốt nhưng endpoint sai port hoặc sai network zone vẫn không dùng được. Một record có host đúng nhưng consumer không có route tới địa chỉ đó cũng không thể xử lý request.

### 3.2. Kiểm tra cả quyền đọc và quyền ghi

Một client có thể đọc registry nhưng không có quyền đăng ký, gia hạn hoặc cập nhật status. Trong hệ thống có ACL, kiểm tra health endpoint bằng credential chỉ có quyền đọc chưa chứng minh credential của ứng dụng có quyền ghi.

Khi chẩn đoán, kiểm tra riêng:
- Đọc danh sách service.
- Đọc registration cụ thể.
- Đăng ký/gia hạn bằng identity của service.
- Cập nhật status hoặc deregister nếu luồng vận hành cần.
- Kết nối từ network namespace thật của ứng dụng.

Không dùng thao tác deregister hoặc thay đổi status trên production chỉ để thử quyền ghi. Dùng endpoint kiểm tra được thiết kế riêng hoặc môi trường staging.

## 4. Heartbeat chỉ chứng minh client còn liên lạc

Heartbeat/lease là cơ chế để registry biết client còn liên lạc theo chu kỳ. Nó hữu ích để phát hiện process hoặc network path đã mất, nhưng không tự kiểm tra mọi chức năng của ứng dụng.

### 4.1. Eureka heartbeat

Eureka client gửi heartbeat tới Eureka Server để gia hạn lease. Tài liệu Spring Cloud Netflix mô tả mặc định phổ biến là client gia hạn khoảng 30 giây một lần và server loại instance khỏi registry sau khi không nhận heartbeat trong khoảng lease expiration (thường là 90 giây). Các giá trị có thể cấu hình và cần được đánh giá theo phiên bản, tải và topology thực tế.

Điều quan trọng là heartbeat và application health là hai signal khác nhau. Theo mặc định, Eureka dùng heartbeat để xác định client còn hoạt động; trạng thái Actuator health không tự động được truyền sang Eureka nếu chưa bật health check integration.

Có thể bật bằng property `eureka.client.healthcheck.enabled=true` trong `application.yml`:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Đặt thuộc tính này trong **application.yml** theo hướng dẫn Spring Cloud Netflix. Tài liệu cảnh báo đặt trong **bootstrap.yml** có thể dẫn đến side effect, chẳng hạn instance đăng ký với trạng thái **UNKNOWN**.

Khi bật health propagation, status của ứng dụng có thể ảnh hưởng status Eureka và khả năng các consumer chọn instance. Tuy nhiên, vẫn phải cấu hình HealthIndicator/health group đúng mục đích. Nếu health chỉ kiểm tra process mà không kiểm tra readiness cần thiết, Eureka vẫn có thể đánh dấu một instance không xử lý được request là UP.

### 4.2. Consul health check

Spring Cloud Consul mặc định đăng ký HTTP health check gọi **/actuator/health** khoảng mỗi 10 giây. Nếu check thất bại, service instance được đánh dấu critical trong Consul.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        health-check-path: /actuator/health
        health-check-interval: 10s
~~~

Tên property và giá trị mặc định cần đối chiếu với phiên bản Spring Cloud Consul trong BOM của dự án. Nếu ứng dụng dùng context path hoặc management path khác, phải cập nhật health check path để Consul gọi đúng endpoint.

Health check passing có nghĩa endpoint đã trả kết quả mà Consul xem là thành công. Nếu **/actuator/health** chỉ kiểm tra process hoặc một tập component nhỏ, nó không chứng minh các API nghiệp vụ đều hoạt động.

### 4.3. Registry có thể giữ dữ liệu cũ trong một khoảng thời gian

Heartbeat, lease expiration, health check interval, registry replication và client fetch/cache đều có chu kỳ. Khi instance chết hoặc không còn sẵn sàng, có thể tồn tại một khoảng thời gian trước khi mọi consumer ngừng chọn instance đó.

Với Eureka, client fetch registry và giữ cache cục bộ; registry update không nhất thiết xuất hiện đồng thời ở mọi client. Với Consul, health check cũng chạy theo interval và trạng thái cần được quan sát sau lần kiểm tra tiếp theo. Hãy tính đến độ trễ phát hiện và propagation trong SLO, alert và quy trình drain.

Không dùng một giá trị timeout duy nhất để mô tả mọi độ trễ. Tách:
- Thời gian phát hiện instance không gửi heartbeat.
- Thời gian health checker gọi endpoint.
- Thời gian registry cập nhật/replicate trạng thái.
- Thời gian client fetch hoặc refresh cache.
- Thời gian LoadBalancer dùng danh sách mới.
- Thời gian request đang chạy hoàn tất hoặc timeout.

## 5. Health, liveness và readiness của ứng dụng

Spring Boot Actuator cung cấp HealthEndpoint tổng hợp trạng thái từ HealthContributor trong ApplicationContext. Một HealthIndicator có thể kiểm tra database, broker, disk, LDAP hoặc một dependency khác.

Endpoint thường dùng:

~~~text
GET /actuator/health
~~~

Response có thể chứa overall status và components. Việc hiển thị chi tiết phụ thuộc cấu hình **management.endpoint.health.show-details** và quyền truy cập. Mặc định, chi tiết không được hiển thị công khai.

Tuy nhiên, overall health không tự động có nghĩa là instance sẵn sàng nhận traffic. Cần xác định mục đích của từng health group.

| Signal | Câu hỏi | Hành động điển hình |
| --- | --- | --- |
| Liveness | Process/app có bị kẹt hoặc hỏng đến mức cần restart không? | Restart container/process khi probe thất bại theo ngưỡng |
| Readiness | Instance có thể nhận request mới không? | Ngừng đưa traffic mới tới instance |
| Startup | Ứng dụng đã hoàn thành giai đoạn khởi động chưa? | Chưa chạy liveness/readiness cho đến khi startup probe thành công |
| Overall health | Các HealthContributor được tổng hợp đang báo trạng thái nào? | Quan sát và cảnh báo; hành động phụ thuộc chính sách |

### 5.1. Liveness không nên phụ thuộc hệ thống bên ngoài

Nếu database hoặc một API bên ngoài tạm thời lỗi, không nên khiến liveness thất bại nếu process vẫn hoạt động. Kubernetes có thể restart hàng loạt Pod khi dependency chung bị lỗi, làm tăng tải và tạo cascading failure.

Liveness nên tập trung vào tình trạng nội tại mà restart có khả năng khắc phục, chẳng hạn deadlock hoặc trạng thái process không thể tiến triển.

### 5.2. Readiness cần phản ánh khả năng nhận traffic

Readiness có thể kiểm tra những điều kiện cần để instance xử lý request mới:
- Startup tasks đã hoàn thành.
- Connection pool đã sẵn sàng.
- Cấu hình bắt buộc đã được nạp.
- Dependency bắt buộc cho nhóm request chính có thể sử dụng.
- Instance không đang drain hoặc bảo trì.
- Tài nguyên cần thiết chưa vượt ngưỡng khiến service không thể nhận thêm traffic.

Không phải dependency nào cũng cần đưa vào readiness. Nếu một dependency chỉ phục vụ chức năng phụ, đưa nó vào readiness toàn service có thể loại bỏ tất cả replica dù phần lớn request vẫn hoạt động. Chọn theo hợp đồng nghiệp vụ và khả năng fallback.

### 5.3. Startup probe bảo vệ ứng dụng khởi động chậm

Startup probe hữu ích khi ứng dụng cần thời gian nạp cấu hình, warm cache, chạy migration hoặc thiết lập kết nối ban đầu. Khi startup probe được cấu hình, Kubernetes chờ nó thành công trước khi bắt đầu liveness và readiness probe.

Điều này tránh việc liveness probe restart một ứng dụng chỉ vì nó chưa khởi động xong.

## 6. Cấu hình health group trong Spring Boot

Spring Boot có thể expose liveness và readiness health group khi chạy trong Kubernetes hoặc khi bật cấu hình probe phù hợp.

Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
      show-details: when-authorized
~~~

Cấu hình trên đưa **readinessState** và health contributor **db** vào readiness group. Chỉ dùng **db** nếu database thực sự là dependency bắt buộc để nhận traffic của service. Spring Boot không tự thêm tất cả dependency health indicator vào readiness group.

Không đưa database, broker hoặc external API vào liveness group chỉ vì chúng xuất hiện trong overall health.

### 6.1. Tạo HealthIndicator cho điều kiện readiness riêng

Ví dụ một check nội bộ xác nhận dữ liệu khởi tạo đã sẵn sàng:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

interface CatalogBootstrapState {
    boolean isReady();
}

@Component("catalogBootstrap")
public class CatalogBootstrapHealthIndicator implements HealthIndicator {

    private final CatalogBootstrapState bootstrapState;

    public CatalogBootstrapHealthIndicator(
            CatalogBootstrapState bootstrapState) {
        this.bootstrapState = bootstrapState;
    }

    @Override
    public Health health() {
        if (bootstrapState.isReady()) {
            return Health.up().build();
        }

        return Health.outOfService()
                .withDetail("reason", "catalog data is still loading")
                .build();
    }
}
~~~

Đưa indicator này vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,catalogBootstrap
~~~

Tên component trong group phải khớp tên HealthContributor đã đăng ký. Không expose detail chứa credential, connection string, customer data hoặc thông tin hạ tầng nhạy cảm.

Một HealthIndicator nên:
- Có timeout rõ ràng cho thao tác I/O.
- Không thực hiện query nặng mỗi lần probe.
- Không tạo side effect.
- Trả kết quả nhanh và ổn định.
- Có phân biệt lỗi tạm thời với lỗi không thể phục hồi.
- Không tự restart process hoặc sửa dữ liệu trong health check.

### 6.2. HTTP status của health endpoint

Theo cấu hình mặc định của Spring Boot:
- **UP** ánh xạ HTTP 200.
- **DOWN** và **OUT_OF_SERVICE** ánh xạ HTTP 503.
- **UNKNOWN** thường ánh xạ HTTP 200 nếu không có mapping khác.

Nếu ứng dụng định nghĩa custom status mapping, các mapping mặc định cho DOWN và OUT_OF_SERVICE có thể bị thay thế và cần khai báo lại nếu vẫn muốn giữ. Do đó, hãy kiểm tra cả body và HTTP status code mà probe thực sự nhận được.

### 6.3. Management port riêng có thể tạo false positive

Nếu Actuator chạy trên một management port riêng, health endpoint có thể trả UP trong khi HTTP server chính không nhận được kết nối. Hai port có thể dùng web infrastructure và connection path khác nhau.

Với ứng dụng cần probe trên main server port, có thể bật additional paths:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Spring Boot cung cấp các path bổ sung mặc định như **/livez** và **/readyz** trên main server port cho health groups tương ứng. Kiểm tra version và path hiệu lực trong tài liệu Boot đang dùng.

## 7. Kubernetes readiness điều khiển traffic như thế nào?

Kubernetes phân biệt probe của container với readiness condition của Pod. Khi readiness probe thất bại, Pod có thể vẫn chạy nhưng được đánh dấu NotReady; EndpointSlice controller cập nhật endpoint để Service không gửi traffic thông thường tới Pod đó.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: catalog
          image: example/catalog-service:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 2
~~~

Các con số chỉ là ví dụ để minh họa. Hãy chọn period, timeout, success/failure threshold và startup allowance theo thời gian khởi động, tải và yêu cầu availability của ứng dụng.

### 7.1. Liveness thất bại và readiness thất bại có hành động khác nhau

| Probe | Khi thất bại liên tiếp | Tác động |
| --- | --- | --- |
| Startup | Container chưa hoàn tất khởi động | Kubelet có thể restart container theo restart policy |
| Liveness | Container không còn khỏe theo tiêu chí liveness | Kubelet restart container |
| Readiness | Container chưa sẵn sàng nhận traffic | Pod bị đánh dấu NotReady; container vẫn chạy |

Không dùng readiness thay liveness để restart ứng dụng. Cũng không dùng liveness để loại instance tạm thời khỏi traffic vì hành động restart có thể làm lỗi lan rộng.

### 7.2. Readiness không phải synthetic transaction

Readiness probe thường kiểm tra một endpoint nhẹ trên từng Pod. Nó không nhất thiết đi qua:
- DNS service name của consumer.
- Ingress hoặc API gateway.
- Service mesh sidecar theo đường đi của request.
- Authentication/authorization của client thật.
- Tất cả dependency và transaction nghiệp vụ.

Vì vậy, readiness cần kết hợp với kiểm thử request từ phía consumer và monitoring ở gateway/data plane.

## 8. Health check trong Eureka và Consul

### 8.1. Eureka: heartbeat và health propagation

Cấu hình:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Khi bật health check integration, trạng thái health của ứng dụng có thể được truyền sang Eureka. Consumer thường chỉ chọn instance ở trạng thái UP theo cấu hình discovery mặc định.

Hãy kiểm tra:
- Eureka Server còn nhận heartbeat không?
- InstanceInfo có status đúng không?
- Health check handler có được bật trong application.yml không?
- Client fetch registry đã nhận status mới chưa?
- LoadBalancer có lọc instance theo status mong muốn không?
- Instance có đang bị server-side override hoặc cache cũ không?

Nếu chỉ kiểm tra heartbeat, instance có thể tiếp tục được xem là UP trong khi endpoint nghiệp vụ đang lỗi. Nếu bật health propagation nhưng health group được cấu hình quá rộng hoặc quá hẹp, status vẫn có thể không phản ánh readiness thực tế.

### 8.2. Consul: HTTP check và trạng thái critical

Consul thường gọi health check path của instance theo chu kỳ. Khi endpoint không phản hồi hoặc trả mã thất bại, Consul có thể đánh dấu check critical.

Ví dụ:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        health-check-path: /actuator/health/readiness
        health-check-interval: 10s
~~~

Dùng readiness endpoint khi muốn Consul chỉ đưa instance sẵn sàng nhận traffic vào danh sách healthy. Tuy nhiên, phải xác minh path đó được expose và có thể truy cập từ Consul agent.

Nếu Consul agent không truy cập được endpoint do network policy, firewall, TLS hoặc sai port, check sẽ fail dù ứng dụng xử lý request từ consumer bình thường. Khi đó lỗi nằm ở đường probe từ agent tới instance, không nhất thiết ở data plane của consumer.

### 8.3. Đừng dùng một endpoint health cho mọi mục tiêu

Có thể dùng:
- Liveness cho kubelet quyết định restart.
- Readiness cho Kubernetes/registry quyết định instance nhận traffic.
- Health check nhẹ cho LoadBalancer hoặc registry.
- Synthetic endpoint/transaction cho monitoring end-to-end.

Các endpoint có thể chia sẻ một số HealthIndicator nhưng cần có ngữ nghĩa rõ. Không để một health check của dependency phụ làm toàn bộ instance bị loại khỏi traffic nếu ứng dụng vẫn có fallback.

## 9. Health check của Spring Cloud LoadBalancer

Spring Cloud LoadBalancer cung cấp **HealthCheckServiceInstanceListSupplier**. Supplier này kiểm tra định kỳ các instance do supplier delegate trả về và chỉ trả các instance khỏe; nếu không có instance nào khỏe, implementation hiện hành trả lại toàn bộ danh sách đã lấy.

Điểm này rất quan trọng khi thiết kế fail-open/fail-closed. Nếu tất cả probe thất bại, không được mặc định rằng LoadBalancer chắc chắn trả danh sách rỗng và dừng traffic.

Cơ chế này đặc biệt hữu ích với **SimpleDiscoveryClient**, vì SimpleDiscoveryClient chỉ cung cấp danh sách tĩnh từ properties và không có registry server thực hiện health check. Với discovery client lấy trạng thái từ registry thật, thường không cần thêm probe trùng lặp vì registry đã cung cấp health state.

### 9.1. Cấu hình health-check supplier

Ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: health-check
      health-check:
        initial-delay: 2s
        interval: 20s
        path:
          default: /actuator/health/readiness
          catalog-service: /actuator/health/readiness
~~~

Nếu không khai báo path riêng, default path thường là **/actuator/health**. Đảm bảo dependency Actuator có mặt hoặc ứng dụng tự cung cấp endpoint tương ứng.

Các thuộc tính có thể thay đổi theo release train; đối chiếu Spring Cloud Commons configprops của BOM đang dùng. Giá trị mặc định hiện hành thường là initial delay 0 và interval 25 giây.

### 9.2. Refetch instance list

Nếu delegate không phát ra danh sách cập nhật liên tục nhưng instance list có thể thay đổi, có thể bật refetch:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 25s
        repeat-health-check: false
~~~

Refetch yêu cầu supplier tải lại danh sách instance theo chu kỳ. Nó không tự biến một nguồn properties tĩnh thành registry động; danh sách mới chỉ xuất hiện nếu nguồn cấu hình/DiscoveryClient thực sự trả dữ liệu mới.

### 9.3. Chọn port và path đúng

Health check có thể dùng port riêng nếu endpoint quản trị chạy ở port khác. Cần bảo đảm:
- Port được cấu hình là port mà probe có thể truy cập.
- Path không yêu cầu session hoặc token không được cấp cho probe.
- TLS certificate được tin cậy.
- Network policy cho phép probe.
- Endpoint trả mã HTTP mà supplier xem là thành công.
- Path không chuyển hướng tới trang login hoặc URL bên ngoài.

Nếu probe gọi management port riêng, nó có thể không phát hiện lỗi ở main HTTP connector. Với service cần xác nhận main server có thể nhận request, nên cung cấp readiness path trên main port hoặc bổ sung synthetic transaction từ phía consumer.

### 9.4. Đừng thêm health check trùng lặp vô điều kiện

Một registry có thể đã health-check instance và LoadBalancer có thể đã nhận danh sách healthy. Thêm một health-check supplier khác có thể:
- Tăng request probe tới từng instance.
- Tạo tải không cần thiết.
- Có hai interval và hai nguồn status khác nhau.
- Tạo kết quả mâu thuẫn khi một probe pass và probe kia fail.
- Tăng thời gian loại instance khỏi traffic nếu hai lớp có cache riêng.

Chỉ bật probe ở LoadBalancer khi cần, ví dụ với SimpleDiscoveryClient hoặc một nguồn instance không có health state đáng tin cậy.

## 10. Health check không chứng minh request nghiệp vụ thành công

Một endpoint **/actuator/health** thường nhẹ và tổng hợp component status. Nó có thể không kiểm tra:
- Một API cụ thể có mapping đúng không.
- Request serialization/deserialization có lỗi không.
- Authentication/authorization của consumer có được chấp nhận không.
- Database query nghiệp vụ có đủ quyền không.
- Broker có thể publish/consume message theo đúng topic/queue không.
- Một transaction nhiều bước có hoàn tất không.
- Thread pool hoặc connection pool có còn capacity dưới tải thật không.

Ví dụ, database health indicator có thể chạy một câu query nhẹ thành công, nhưng một truy vấn nghiệp vụ phức tạp vẫn timeout do lock hoặc index. Tương tự, broker TCP connection còn sống không chứng minh consumer group đang xử lý message đúng.

### 10.1. Synthetic transaction

Synthetic transaction là request thử được tạo theo chu kỳ để kiểm tra một luồng đại diện từ góc nhìn client.

Ví dụ một transaction đọc catalog:

~~~text
monitor
  -> resolve catalog-service
  -> chọn instance qua LoadBalancer
  -> gọi GET /internal/synthetic/catalog
  -> ứng dụng truy vấn dữ liệu kiểm thử
  -> xác nhận response schema và dữ liệu kỳ vọng
~~~

Endpoint synthetic nên:
- Có mục đích rõ và chỉ đọc hoặc có thể lặp an toàn.
- Dùng dữ liệu kiểm thử riêng.
- Có timeout ngắn và giới hạn tần suất.
- Không tạo order, thanh toán, email hoặc message side effect thật.
- Không bỏ qua authentication/TLS nếu muốn kiểm tra đường gọi thật.
- Ghi nhận kết quả, latency và instance đã nhận request.

Synthetic transaction không nên được gọi quá thường xuyên hoặc thực hiện thao tác nặng. Nếu mỗi replica nhận nhiều probe phức tạp, chính health check có thể tạo tải gây lỗi.

### 10.2. Kiểm tra từ đúng góc nhìn

Một phép thử chạy trên chính instance bằng localhost không kiểm tra được DNS, routing hoặc firewall từ consumer. Nên có các mức:
- Probe nội bộ từ process hoặc sidecar.
- Probe từ registry agent tới instance.
- Probe từ consumer trong cùng network zone.
- Probe từ gateway/client bên ngoài.
- Synthetic transaction xuyên qua luồng nghiệp vụ quan trọng.

Kết quả khác nhau giữa các góc nhìn giúp xác định lỗi nằm ở instance, registry path hay network path.

## 11. Quan sát bằng metrics, logs và traces

Không dựa vào một health endpoint duy nhất. Nên kết hợp:
- **Metrics:** tỷ lệ request thành công/thất bại, latency, số instance active, số lần không chọn được instance.
- **Logs:** lỗi heartbeat, timeout, health check failure, registration update, connection reset.
- **Traces:** request qua LoadBalancer tới instance, thời gian ở từng hop, dependency call và lỗi trả về.
- **Registry view:** registration status, lease/check state, host/port và thời điểm cập nhật.
- **Synthetic results:** kết quả transaction từ network zone của consumer.

### 11.1. Metrics của Spring Cloud LoadBalancer

Spring Cloud Commons cung cấp Micrometer statistics qua **MicrometerStatsLoadBalancerLifecycle**. Có thể bật:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

Khi có **MeterRegistry**, các meter thường gặp gồm:

| Meter | Ý nghĩa |
| --- | --- |
| **loadbalancer.requests.active** | Gauge số request đang active |
| **loadbalancer.requests.success** | Timer cho request kết thúc với response được chuyển tới HTTP client |
| **loadbalancer.requests.failed** | Timer cho request kết thúc bằng exception |
| **loadbalancer.requests.discard** | Counter cho request không lấy được ServiceInstance |

Các meter có thể kèm tag về service instance, request và response khi có dữ liệu. **success** ở tầng LoadBalancer không nhất thiết có nghĩa HTTP status là 2xx hoặc nghiệp vụ thành công; hãy theo dõi status/outcome ở HTTP server/client instrumentation và kết quả nghiệp vụ riêng.

### 11.2. Tránh high-cardinality tag

Không đưa user ID, order ID, session ID hoặc URL chứa ID động vào metric tag. Với LoadBalancer, có thể cân nhắc tắt path trong URI tag nếu path có cardinality cao:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        include-path: false
~~~

Dùng trace hoặc log có kiểm soát cho chi tiết từng request. Metric nên giữ tập tag nhỏ và ổn định để không làm tăng bộ nhớ và chi phí backend.

### 11.3. Dashboard nên có nhiều góc nhìn

Một dashboard vận hành có thể chia thành:

| Panel | Dữ liệu | Câu hỏi |
| --- | --- | --- |
| Registry control plane | API latency/error, leader/cluster status, client connection | Có đọc/ghi registry được không? |
| Registration | Số instance theo service/status, heartbeat/check age | Record có mới và đầy đủ không? |
| Readiness | Ready/NotReady theo replica, probe failures | Instance nào nhận traffic được? |
| LoadBalancer | active/success/failed/discard, selected instance | Consumer chọn instance nào và request ra sao? |
| HTTP server | request rate, status code, latency | Instance có xử lý request thành công không? |
| Dependency | DB pool, broker lag, connection errors | Dependency nào làm request thất bại? |
| Synthetic | transaction pass rate và latency theo zone | Luồng end-to-end có hoạt động không? |

Alert nên dựa trên SLO và thời gian kéo dài, tránh cảnh báo một probe đơn lẻ thất bại trong khi traffic thật vẫn bình thường.

## 12. Chẩn đoán các tình huống registry khỏe nhưng service lỗi

| Triệu chứng | Tầng có thể lỗi | Cách kiểm tra |
| --- | --- | --- |
| Registry API trả 200 nhưng không có instance | Registration | Kiểm tra service ID, auto-registration, quyền ghi và status |
| Registry có instance UP nhưng TCP timeout | Advertised endpoint/network | Kiểm tra host/port, route, firewall, security group |
| Heartbeat đều nhưng request 500 | Application/dependency | Kiểm tra readiness, logs, traces và dependency |
| Consul check critical nhưng request từ consumer vẫn thành công | Probe path/agent network | Gọi health path từ Consul agent và consumer riêng |
| Eureka còn instance cũ sau khi process chết | Lease/cache propagation | Kiểm tra heartbeat age, lease expiration và client fetch |
| Pod Ready nhưng API cụ thể lỗi | Readiness quá tổng quát | Kiểm tra synthetic transaction và health group |
| /actuator/health UP nhưng main port không nhận kết nối | Management port tách biệt | Probe readiness trên main port hoặc additional path |
| LoadBalancer chọn instance đã fail probe | Cache/supplier/fallback | Kiểm tra supplier chain, cache và hành vi khi mọi instance unhealthy |
| Một zone gọi được, zone khác timeout | Network zone/routing | Probe từ từng consumer zone và kiểm tra advertised address |
| Registry và consumer hiển thị status khác nhau | Replication/client cache | Kiểm tra thời điểm cập nhật, fetch interval và cache |
| Health check pass nhưng request chậm | Capacity/saturation | Theo dõi thread pool, queue, connection pool, latency |
| Liveness liên tục restart nhiều Pod | Probe thiết kế sai/cascading failure | Loại external dependency khỏi liveness và kiểm tra ngưỡng |

### 12.1. Trình tự điều tra

1. Gọi health endpoint của registry từ đúng network namespace của service client.
2. Đọc record của service và xác minh host, port, status, metadata.
3. Kiểm tra heartbeat/lease hoặc health-check timestamp.
4. Gọi readiness endpoint trực tiếp trên instance từ consumer network.
5. Kiểm tra DNS, TCP, TLS và HTTP tới địa chỉ được quảng bá.
6. Gửi request qua đúng Spring Cloud LoadBalancer client.
7. Đọc metrics LoadBalancer và HTTP client/server.
8. Theo trace để xác định hop nào timeout hoặc trả lỗi.
9. Kiểm tra dependency và capacity của instance.
10. Chỉ thay status/deregister/rollout sau khi xác định đúng nguyên nhân và phạm vi tác động.

Giữ timestamp và instance ID trong các bước này để đối chiếu cùng một sự kiện. Không so sánh hai log khác thời điểm rồi kết luận registry sai.

## 13. Kiểm thử các lớp health riêng biệt

Một test health endpoint không thay thế test registry, và test registry không thay thế test request. Nên tổ chức test theo mục tiêu.

| Loại test | Thiết lập | Điều cần chứng minh |
| --- | --- | --- |
| Registry availability test | Gọi API/health endpoint của registry | Registry endpoint có thể truy cập và trả response hợp lệ |
| Registration test | Khởi động discovery client, đọc record | Instance đăng ký đúng host/port/status |
| Heartbeat/lease test | Chờ renewal hoặc mô phỏng client mất kết nối | Registry phát hiện registration cũ theo chính sách |
| Actuator health test | Mock dependency và gọi health group | Health status phản ánh đúng component/group |
| Readiness test | Chuyển app state/dependency sang not ready | Endpoint readiness trả trạng thái và HTTP code phù hợp |
| LoadBalancer health test | Hai instance, một probe pass và một probe fail | Supplier lọc theo health policy |
| Consumer reachability test | Gọi từ container/Pod của consumer | DNS, route, TLS và port hoạt động |
| Synthetic transaction test | Gọi luồng nghiệp vụ không side effect | Request end-to-end hoàn tất đúng |
| Failure injection test | Ngắt registry hoặc dependency có kiểm soát | Hệ thống degrade theo chính sách, không tạo cascading failure |

### 13.1. Kiểm thử Actuator readiness

Ví dụ với MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoint.health.probes.enabled=true"
})
@AutoConfigureMockMvc
class ReadinessEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readinessEndpointIsExposed() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
    }
}
~~~

Đây chỉ là ví dụ cho trạng thái khỏe mặc định. Test thực tế nên điều khiển trạng thái readiness hoặc mock HealthIndicator để xác nhận cả trường hợp DOWN/OUT_OF_SERVICE và HTTP 503.

### 13.2. Kiểm thử LoadBalancer health supplier

Nên tạo hai ServiceInstance:
- Instance A trả HTTP 200 cho readiness path.
- Instance B trả HTTP 503 hoặc timeout.
- Bật HealthCheckServiceInstanceListSupplier.
- Chờ health check đầu tiên hoàn tất bằng polling có timeout.
- Xác nhận danh sách healthy và request selection.

Đừng dùng Thread.sleep cố định dài mà không kiểm tra scheduler đã chạy. Có thể dùng Awaitility hoặc điều kiện quan sát được để test ổn định.

Nếu tất cả instance đều unhealthy, kiểm tra hành vi fallback của đúng phiên bản Spring Cloud Commons. Tài liệu hiện hành mô tả supplier trả lại toàn bộ danh sách đã lấy khi không có instance healthy; nếu ứng dụng yêu cầu fail-closed, cần test và cấu hình/customize rõ chính sách đó.

### 13.3. Kiểm thử khi registry mất kết nối

Một test resilience có thể:
1. Khởi động registry test server.
2. Đăng ký hai instance.
3. Để consumer lấy registry list.
4. Ngắt kết nối registry.
5. Gửi request qua client đang có cache.
6. Quan sát request còn được định tuyến hay không.
7. Hết cache/lease hoặc làm mới discovery.
8. Xác nhận hành vi khi không còn instance có thể dùng.

Kết quả phụ thuộc registry client, cache, retry và timeout. Không viết assertion chung rằng mất registry thì mọi request lập tức thất bại hoặc luôn tiếp tục thành công.

## 14. Thiết kế alert và SLO

Alert cần gắn với tác động tới người dùng hoặc khả năng phục vụ. Một số tín hiệu có thể kết hợp:

- Registry API error rate cao kéo dài.
- Số instance healthy giảm dưới ngưỡng cần thiết.
- Heartbeat/check age vượt ngưỡng.
- Readiness failure tăng ở nhiều replica.
- LoadBalancer discard tăng.
- HTTP 5xx hoặc timeout tăng.
- Synthetic transaction thất bại từ một hoặc nhiều zone.
- p95/p99 latency vượt SLO.
- Dependency pool cạn hoặc queue/consumer lag tăng.

Không cảnh báo chỉ vì registry không truy cập được trong vài giây nếu consumer vẫn có cache hợp lệ và request success không suy giảm. Ngược lại, registry hoàn toàn khỏe nhưng synthetic transaction thất bại liên tục là tín hiệu sự cố data plane cần ưu tiên.

Có thể chia mức độ:
- **Warning:** registry hoặc health probe có lỗi, nhưng request success/SLO chưa suy giảm.
- **Critical:** request success giảm, latency vượt SLO hoặc không còn đủ instance nhận traffic.
- **Capacity risk:** số instance còn khỏe thấp, nhưng hiện tại request vẫn thành công.

Các ngưỡng phải dựa trên SLO, tải, số replica tối thiểu và thời gian phục hồi chấp nhận được.

## 15. Nguyên tắc vận hành

- Đo registry availability, registration freshness, readiness và request success riêng.
- Không coi heartbeat là health check nghiệp vụ.
- Không coi HTTP 200 từ registry là bằng chứng instance xử lý được request.
- Thiết kế liveness cho lỗi nội tại có thể phục hồi bằng restart.
- Thiết kế readiness theo khả năng nhận traffic và dependency thật sự bắt buộc.
- Dùng startup probe cho ứng dụng khởi động lâu.
- Không đưa dependency bên ngoài vào liveness nếu lỗi của nó có thể gây restart hàng loạt.
- Đảm bảo registry agent gọi đúng health path/port/TLS.
- Tránh probe trùng lặp nếu registry đã cung cấp health state đáng tin cậy.
- Hiểu rõ fallback của HealthCheckServiceInstanceListSupplier khi mọi instance unhealthy.
- Kiểm tra consumer cache và propagation delay trước khi kết luận status chưa cập nhật.
- Dùng synthetic transaction để kiểm tra luồng quan trọng từ góc nhìn client.
- Kết hợp metrics, logs, traces và registry record trong cùng timeline.
- Không expose health details, topology hoặc credential cho người không có quyền.

## 16. Checklist khi service có trạng thái UP nhưng request thất bại

- [ ] Registry API có thể truy cập từ service client.
- [ ] Registration có đúng service ID, instance ID, host và port.
- [ ] Heartbeat/lease hoặc registry health check còn mới.
- [ ] Eureka có bật health propagation nếu cần dùng Actuator status.
- [ ] Consul agent gọi đúng health-check path và port.
- [ ] Actuator readiness phản ánh đúng điều kiện nhận traffic.
- [ ] Liveness không phụ thuộc vào database/broker/API bên ngoài.
- [ ] Kubernetes readiness và EndpointSlice phản ánh Pod readiness.
- [ ] Management port riêng không tạo false positive.
- [ ] LoadBalancer supplier và cache được cấu hình phù hợp.
- [ ] Fallback khi không còn instance healthy đã được hiểu và kiểm thử.
- [ ] Consumer có DNS resolution và route tới advertised endpoint.
- [ ] TLS, authentication, authorization và NetworkPolicy không chặn request.
- [ ] Metrics LoadBalancer và HTTP server/client có dữ liệu.
- [ ] Synthetic transaction kiểm tra được luồng nghiệp vụ quan trọng.
- [ ] Alert dựa trên request success/SLO và không chỉ dựa trên registry ping.

## Ghi nhớ

Registry khỏe chỉ cho biết control plane có thể phản hồi; heartbeat còn mới chỉ cho biết client tiếp tục liên lạc; readiness cho biết instance sẵn sàng theo tiêu chí đã cấu hình; request success mới xác nhận consumer hoàn tất được đường gọi thực tế. Eureka mặc định dựa vào heartbeat và cần bật health propagation nếu muốn đồng bộ Actuator status; Consul có thể gọi HTTP health endpoint theo chu kỳ; Kubernetes dùng readiness để điều khiển endpoint phục vụ Service; Spring Cloud LoadBalancer có health-check supplier riêng, đặc biệt hữu ích với SimpleDiscoveryClient. Hãy quan sát đủ bốn lớp và xác minh từ network zone của consumer trước khi kết luận service khỏe.

## Tài liệu tham khảo

- Spring Cloud Netflix – Eureka Health Checks: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Netflix – Configuration Properties: https://docs.spring.io/spring-cloud-netflix/reference/configprops.html
- Spring Cloud Consul – Service Discovery and Health Checks: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Commons – LoadBalancer Health Check and Statistics: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Boot – Actuator Endpoints and Health Groups: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot – Health Endpoint API: https://docs.spring.io/spring-boot/api/rest/actuator/health.html
- Kubernetes – Liveness, Readiness, and Startup Probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/

