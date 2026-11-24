# Khởi động mới khi sổ đăng ký không truy cập được

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt ứng dụng khởi động, đăng ký instance và sẵn sàng nhận traffic.
- Chọn chính sách fail-fast hoặc start-degraded khi registry không truy cập được.
- Cấu hình retry có giới hạn, backoff và timeout theo từng registry.
- Hiểu khác biệt giữa Eureka, Consul, ZooKeeper và Kubernetes discovery trong giai đoạn startup.
- Xử lý riêng trường hợp registry đồng thời là nguồn cấu hình từ xa.
- Tránh restart storm, đăng ký trùng và công bố instance trước khi sẵn sàng.
- Kiểm thử quá trình khởi động khi registry tắt, phục hồi và mất kết nối trở lại.

## 1. Registry không sẵn sàng khi ứng dụng khởi động

Một microservice có thể khởi động đúng về mặt JVM và Spring ApplicationContext nhưng chưa đăng ký được với service registry. Điều đó không nhất thiết có nghĩa ứng dụng bị lỗi hoàn toàn. Hành vi phù hợp phụ thuộc vào việc registry có phải điều kiện bắt buộc để ứng dụng thực hiện nghiệp vụ hay không.

Ví dụ, inventory-service có thể mở HTTP server và phục vụ endpoint quản trị khi Eureka đang tắt. Nhưng nếu các consumer chỉ tìm inventory-service qua Eureka, instance chưa đăng ký sẽ không được tìm thấy. Ứng dụng đang chạy nhưng chưa thể tham gia hệ thống discovery.

Cần phân biệt ba mốc:

| Mốc | Ý nghĩa | Điều cần xác minh |
| --- | --- | --- |
| Process started | JVM và Spring Boot đã khởi tạo đủ để process tiếp tục chạy. | Context, server và các bean cốt lõi đã khởi động. |
| Registered | Registry đã nhận registration theo hợp đồng của client. | Đăng ký instance, service ID, host, port và metadata. |
| Ready to serve | Instance có thể nhận request mới theo hợp đồng của service. | Dependency bắt buộc, warm-up và routing đã sẵn sàng. |

Registration thành công cũng chưa bảo đảm mọi consumer nhìn thấy instance ngay lập tức. Cache, replication và chu kỳ refresh có thể tạo độ trễ. Vì vậy, nếu hệ thống cần xác nhận instance đã xuất hiện trong registry view, cần kiểm tra riêng visibility thay vì chỉ dựa vào việc lệnh register không ném exception.

## 2. Xác định registry đang đóng vai trò gì

Trước khi chọn retry hoặc fail-fast, hãy xác định ứng dụng đang phụ thuộc registry ở mức nào:

1. **Chỉ dùng service discovery:** ứng dụng cần registry để đăng ký chính nó hoặc tìm các service khác.
2. **Dùng registry làm nguồn cấu hình:** ứng dụng tải cấu hình bắt buộc từ Consul KV, ZooKeeper Config, Spring Cloud Config hoặc Kubernetes ConfigMap/Secret.
3. **Dùng DNS native của Kubernetes:** ứng dụng gọi Kubernetes Service bằng DNS, không cần tự đăng ký instance qua Spring Cloud DiscoveryClient.
4. **Có đường dự phòng:** ứng dụng có thể dùng DNS, endpoint tĩnh, cache đã xác thực hoặc một chế độ nghiệp vụ hạn chế khi registry tạm thời mất.

Đặc biệt, lỗi tải remote configuration có thể xảy ra trước khi service discovery được khởi tạo. Ví dụ, Consul Config hoặc Spring Cloud Config có thể làm ApplicationContext dừng ngay trong giai đoạn đọc property source. Khi đó, cấu hình retry của discovery registration không giải quyết được lỗi bootstrap config.

## 3. Chọn một trong hai chính sách khởi động

### Chính sách A: fail-fast

Dùng khi registry là điều kiện bắt buộc để ứng dụng hoạt động an toàn.

Ví dụ:

- API gateway cần danh sách instance để định tuyến mọi request.
- Một worker không thể xử lý job nếu không tìm được coordinator hoặc service bắt buộc.
- Ứng dụng phải đăng ký vào registry trước khi được phép tham gia hệ thống.
- Cấu hình bắt buộc phải tải từ registry và không có bản local an toàn.

Quy trình:

1. Khởi tạo ứng dụng và các dependency cục bộ.
2. Thử kết nối registry.
3. Retry trong một ngân sách thời gian hữu hạn.
4. Nếu registration hoặc lookup bắt buộc vẫn thất bại, kết thúc startup với lỗi rõ ràng.
5. Orchestrator có thể khởi động lại instance theo restart policy.

Ưu điểm là không để một instance nửa sẵn sàng tham gia hệ thống. Nhược điểm là khi registry ngừng lâu, nhiều pod có thể liên tục khởi động rồi thoát. Cần retry có giới hạn, backoff và giám sát để tránh tạo tải bổ sung lên registry đang gặp sự cố.

### Chính sách B: start-degraded

Dùng khi ứng dụng vẫn có thể khởi động an toàn mà không cần registry ngay lập tức.

Ví dụ:

- Endpoint health và endpoint quản trị vẫn hoạt động.
- Ứng dụng có thể phục vụ một nhóm request qua Kubernetes Service DNS.
- Ứng dụng có cache hợp lệ hoặc cấu hình local đã được kiểm tra.
- Registry chỉ cần để công bố instance cho consumer; phần khởi tạo nội bộ không phụ thuộc registry.

Quy trình:

1. Khởi động process và HTTP server.
2. Thử kết nối và đăng ký với registry.
3. Nếu registry chưa sẵn sàng, ghi nhận trạng thái degraded.
4. Giữ readiness ở REFUSING_TRAFFIC nếu consumer chưa thể định tuyến an toàn đến instance.
5. Retry đăng ký ở background với backoff và jitter.
6. Khi đăng ký thành công, xác minh metadata/visibility rồi mới chuyển readiness sang ACCEPTING_TRAFFIC.

Start-degraded không có nghĩa là cứ mở cổng HTTP là cho phép nhận traffic. Chỉ chuyển sang ready khi instance thực sự có thể phục vụ theo hợp đồng của service.

### Bảng quyết định

| Điều kiện | Chính sách nên chọn |
| --- | --- |
| Không thể phục vụ bất kỳ request nghiệp vụ nào nếu registry mất | Fail-fast sau retry hữu hạn, hoặc giữ unready trong thời gian chờ có giới hạn. |
| Có thể phục vụ bằng đường dự phòng đã được kiểm thử | Start-degraded và công bố readiness theo khả năng thực tế. |
| Registry chỉ dùng cho inbound discovery | Có thể khởi động process nhưng giữ readiness false cho tới khi registration hoàn tất. |
| Remote config bắt buộc và không có fallback | Fail-fast ở giai đoạn config bootstrap. |
| Remote config có bản local an toàn và đã được phê duyệt | Cho phép tiếp tục với fallback, ghi rõ phiên bản config và trạng thái degraded. |

Không nên chọn chính sách chỉ dựa trên mong muốn giảm thời gian startup. Cần xác định hậu quả nếu consumer gọi một instance chưa đăng ký hoặc dùng cấu hình cũ.

## 4. Vòng đời khởi động và đăng ký

Một trình tự khởi động điển hình:

~~~~mermaid
flowchart TD
    A[Process starts] --> B[Load local configuration]
    B --> C[Initialize Spring context]
    C --> D[Start embedded server]
    D --> E[Connect to registry]
    E --> F{Registry reachable?}
    F -- Yes --> G[Register service instance]
    F -- No --> H{Startup policy?}
    H -- Fail-fast --> I[Retry with bounded backoff]
    I --> J{Retry budget exhausted?}
    J -- No --> E
    J -- Yes --> K[Fail startup]
    H -- Start-degraded --> L[Mark registry unavailable]
    L --> M[Keep readiness REFUSING_TRAFFIC]
    M --> N[Retry in background]
    N --> O{Registration succeeds?}
    O -- No --> N
    O -- Yes --> P[Verify registration and dependencies]
    G --> P
    P --> Q[Readiness ACCEPTING_TRAFFIC]
~~~~

Các bước cụ thể phụ thuộc implementation. Eureka có thể khởi tạo client và tiếp tục refresh/replicate theo scheduler; Consul có cơ chế retry registration; Curator kết nối ZooKeeper theo session lifecycle; Kubernetes discovery có thể đọc Service/Endpoints qua API hoặc dùng DNS Service native.

## 5. Retry phải có giới hạn và có backoff

Retry giúp vượt qua lỗi tạm thời như registry restart, network route chưa sẵn sàng hoặc DNS chưa cập nhật. Retry liên tục không có giới hạn có thể làm sự cố nặng hơn.

Một chính sách retry nên có:

- **Initial delay:** thời gian chờ trước lần thử lại đầu tiên.
- **Multiplier:** hệ số tăng khoảng chờ giữa các lần thử.
- **Maximum delay:** giới hạn thời gian chờ tối đa.
- **Maximum attempts hoặc deadline:** số lần thử tối đa hoặc tổng ngân sách thời gian.
- **Jitter:** độ lệch ngẫu nhiên để nhiều instance không retry cùng một thời điểm.
- **Timeout mỗi lần gọi:** giới hạn thời gian một request kết nối/đăng ký.
- **Phân loại lỗi:** chỉ retry lỗi có khả năng tự phục hồi.

Ví dụ backoff:

~~~~text
Lần thử 1: gọi ngay
Lần thử 2: chờ khoảng 1 giây
Lần thử 3: chờ khoảng 2 giây
Lần thử 4: chờ khoảng 4 giây
Lần thử tiếp theo: tiếp tục tăng nhưng không vượt max interval
~~~~

Các giá trị là ví dụ, không phải cấu hình chuẩn cho mọi registry. Tổng startup budget phải tính cả timeout của mỗi request và thời gian backoff. Nếu mỗi lần gọi có thể treo hàng chục giây, retry sáu lần vẫn có thể kéo dài startup rất lâu.

### Lỗi nào nên retry?

| Lỗi | Hành động gợi ý |
| --- | --- |
| Connection refused trong lúc registry restart | Retry có backoff. |
| DNS lookup tạm thời thất bại | Retry; kiểm tra resolver và service name. |
| HTTP 503 hoặc server đang failover | Retry có giới hạn. |
| Timeout do network chập chờn | Retry với timeout hợp lý. |
| HTTP 401/403 hoặc ZooKeeper NOAUTH | Dừng retry dày; sửa credential/ACL. |
| Sai hostname, port hoặc path cố định | Báo lỗi cấu hình; không retry vô hạn. |
| TLS certificate hết hạn hoặc trust chain sai | Sửa certificate/truststore; retry không tự khắc phục. |
| Service ID hoặc namespace sai | Sửa cấu hình hoặc quyền; không coi là outage tạm thời. |

Không bắt tất cả exception rồi retry như nhau. Với lỗi cấu hình và xác thực, retry chỉ làm chậm quá trình phát hiện lỗi.

## 6. Spring Cloud Consul

Spring Cloud Consul sử dụng HTTP API của Consul Agent để đăng ký và khám phá service. Nếu agent chưa sẵn sàng khi ứng dụng khởi động, Spring Cloud Consul có hỗ trợ retry.

Tài liệu Spring Cloud Consul hiện hành mô tả retry mặc định gồm sáu lần thử, khoảng chờ ban đầu 1.000 ms và multiplier 1,1. Muốn bật cơ chế này, classpath cần Spring Retry và starter AOP/AspectJ phù hợp với nhánh phiên bản đang sử dụng. Spring Cloud Consul 5.0.x hiện hướng dẫn spring-boot-starter-aspectj; tài liệu 4.3.x dùng spring-boot-starter-aop. Hãy kiểm tra tài liệu release train của dự án trước khi thêm dependency.

Ví dụ cấu hình:

~~~~yaml
spring:
  cloud:
    consul:
      host: consul-agent.internal
      port: 8500
      discovery:
        enabled: true
        register: true
        fail-fast: false
      retry:
        enabled: true
        initial-interval: 1000
        max-attempts: 6
        max-interval: 2000
        multiplier: 1.1
~~~~

Các thuộc tính quan trọng:

- spring.cloud.consul.discovery.register: bật/tắt tự đăng ký service.
- spring.cloud.consul.discovery.fail-fast: nếu true, lỗi đăng ký có thể làm startup thất bại; mặc định hiện hành là true. Nếu false, lỗi được ghi warning và ứng dụng có thể tiếp tục khởi động.
- spring.cloud.consul.retry.enabled: bật retry; mặc định hiện hành là true.
- spring.cloud.consul.retry.max-attempts: tổng số lần thử, bao gồm lần gọi ban đầu theo Spring Retry.
- spring.cloud.consul.retry.initial-interval, max-interval, multiplier: điều khiển backoff.

Cần phân biệt spring.cloud.consul.discovery.fail-fast với spring.cloud.consul.config.fail-fast. Thuộc tính đầu tiên áp dụng cho đăng ký discovery; thuộc tính thứ hai áp dụng cho việc tải cấu hình từ Consul KV. Một ứng dụng có thể cho phép discovery registration thất bại nhưng vẫn fail startup vì cấu hình bắt buộc không tải được.

Nếu muốn tùy chỉnh retry hoàn toàn, có thể khai báo bean RetryOperationsInterceptor với tên consulRetryInterceptor. Không tạo thêm retry wrapper chồng lên retry tích hợp nếu chưa xác định rõ số lần thử thực tế, vì hai lớp retry có thể nhân số request lên nhiều lần.

## 7. Spring Cloud Netflix Eureka

Eureka Client tự động đăng ký khi starter spring-cloud-starter-netflix-eureka-client có mặt và cấu hình service URL phù hợp. Client cũng có thể lấy registry để tìm service khác.

Ví dụ cấu hình:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka-a.internal/eureka/,https://eureka-b.internal/eureka/
    register-with-eureka: true
    fetch-registry: true
    should-enforce-registration-at-init: false
~~~~

Ba thuộc tính có ý nghĩa khác nhau:

- register-with-eureka: client có đăng ký thông tin instance của chính nó không.
- fetch-registry: client có lấy registry để khám phá instance khác không.
- should-enforce-registration-at-init: có bắt buộc đăng ký ban đầu thành công ngay trong quá trình khởi tạo Eureka Client không.

Theo config properties hiện hành, should-enforce-registration-at-init mặc định là false. Nếu bật true, Eureka Client sẽ ném exception khi lần đăng ký ban đầu tới server thất bại; nếu false, ứng dụng không bị buộc dừng chỉ vì lần đăng ký ban đầu không thành công. Hành vi retry/heartbeat và refresh tiếp theo vẫn phụ thuộc Eureka Client version.

Ví dụ chọn fail-fast:

~~~~yaml
eureka:
  client:
    should-enforce-registration-at-init: true
~~~~

Chỉ bật khi registration là điều kiện bắt buộc để instance được phép chạy. Nếu ứng dụng có thể khởi động degraded, giữ false và dùng readiness để ngăn traffic cho tới khi registration hoàn tất.

Không đặt fetch-registry: false chỉ để bỏ qua lỗi registration nếu ứng dụng vẫn cần tìm các service khác. Hai chức năng đăng ký bản thân và tải registry là hai hành vi độc lập.

Eureka còn có cấu hình backup-registry-impl để cung cấp registry data dự phòng trong lần khởi tạo đầu tiên cho một số ứng dụng cần danh sách service ban đầu. Đây là fallback cho dữ liệu discovery ban đầu, không thay thế việc đăng ký instance của chính ứng dụng và không phải bản sao đồng bộ của Eureka Server.

Nếu client sử dụng nhiều Eureka Server URL, hãy kiểm tra từng URL, DNS, TLS, authentication và khả năng failover. Cấu hình nhiều URL không bảo đảm các peer đã đồng bộ hoặc client có thể truy cập tất cả peer.

## 8. Spring Cloud Zookeeper

Spring Cloud Zookeeper dùng Apache Curator để kết nối ensemble và thực hiện registration/discovery. Registration được bật mặc định qua spring.cloud.zookeeper.discovery.register.

Một số thuộc tính kết nối và retry:

~~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      connection-timeout: 10000
      session-timeout: 30000
      base-sleep-time-ms: 50
      max-retries: 10
      max-sleep-ms: 500
      block-until-connected-wait: 10
      block-until-connected-unit: seconds
      discovery:
        enabled: true
        register: true
~~~~

Ý nghĩa:

- connect-string: danh sách thành viên ensemble mà client có thể kết nối.
- connection-timeout: giới hạn thời gian thiết lập kết nối.
- session-timeout: thời gian session được cấu hình/thương lượng.
- base-sleep-time-ms, max-retries, max-sleep-ms: các tham số retry policy của Curator.
- block-until-connected-wait và block-until-connected-unit: thời gian chờ kết nối ban đầu theo cấu hình Spring Cloud Zookeeper; tài liệu 4.3.x ghi mặc định 10 giây.

Các giá trị ví dụ cần điều chỉnh theo latency mạng và session timeout của ensemble. Giới hạn chờ ban đầu không đồng nghĩa với việc client sẽ retry vô hạn hoặc session chắc chắn được tạo thành công.

Nếu ứng dụng đồng thời dùng ZooKeeper làm Config Server, thuộc tính spring.cloud.zookeeper.config.fail-fast điều khiển lỗi tải cấu hình. Giá trị mặc định trong tài liệu hiện hành là true. Đây là hành vi của config lookup, không nên nhầm với việc Curator tạo connection hay ServiceRegistry đăng ký ephemeral znode.

Khi kết nối thành công sau một khoảng gián đoạn, cần xác minh session còn hiệu lực hay đã hết hạn. Nếu session cũ đã mất, ephemeral znode registration cũ bị xóa; client cần tạo session mới và đăng ký lại. Không tự tạo CuratorFramework thứ hai để đăng ký lại nếu Spring Cloud đã quản lý client và lifecycle.

## 9. Spring Cloud Kubernetes và Kubernetes Service DNS

Có hai cách dùng Kubernetes để tìm service:

### Kubernetes Service DNS

Nếu ứng dụng chỉ gọi một Kubernetes Service bằng DNS, ví dụ inventory.commerce.svc.cluster.local, không cần khởi tạo Spring Cloud DiscoveryClient chỉ để đăng ký instance. Kubernetes quản lý Service và EndpointSlice dựa trên Pod labels, selectors và readiness.

Trong trường hợp này:

- Pod được tạo và ứng dụng khởi động.
- Readiness probe quyết định Pod có đủ điều kiện nhận traffic qua Service không.
- Kubernetes cập nhật EndpointSlice khi Pod thay đổi trạng thái.
- DNS cung cấp tên Service ổn định cho caller.

Nếu Kubernetes API server tạm thời không truy cập được, một số request data plane qua Service/DNS vẫn có thể tiếp tục hoạt động với trạng thái đã được cấu hình trước đó. Nhưng việc thay đổi Pod/Service/EndpointSlice và cập nhật endpoint mới có thể bị trì hoãn.

### Spring Cloud Kubernetes DiscoveryClient

Khi dùng Fabric8 hoặc Kubernetes Java Client, ứng dụng truy vấn Kubernetes API để lấy Service, Endpoints hoặc EndpointSlices. Cần kiểm tra:

- ServiceAccount token và CA certificate có được mount đúng không.
- Role/ClusterRole có quyền get/list/watch các resource cần thiết không.
- Namespace discovery có đúng không.
- API server URL và network policy có cho phép kết nối không.
- API EndpointSlices có tồn tại và được cluster hỗ trợ nếu bật use-endpoint-slices.

Ví dụ khi bật EndpointSlices:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        use-endpoint-slices: true
~~~~

Nếu cluster không hỗ trợ API EndpointSlices mà ứng dụng bật tính năng này, tài liệu Spring Cloud Kubernetes cảnh báo ứng dụng có thể thất bại ngay trong quá trình startup. Cấu hình này cũng cần RBAC cho resource endpointslices thuộc API group discovery.k8s.io.

Không nên nhầm spring.cloud.kubernetes.config.fail-fast với DiscoveryClient. Thuộc tính config fail-fast điều khiển việc tải ConfigMap; nó không phải công tắc tổng quát cho việc kết nối Kubernetes API phục vụ discovery.

## 10. Remote configuration có thể làm startup dừng trước discovery

Registry đôi khi vừa là nguồn service discovery vừa là nguồn cấu hình. Cần xác định lỗi đang xảy ra ở giai đoạn nào.

| Thành phần | Hành vi khi không truy cập được | Cấu hình liên quan |
| --- | --- | --- |
| Spring Cloud Config Client | Có thể fail startup nếu import là bắt buộc hoặc bật fail-fast. | spring.cloud.config.fail-fast, spring.config.import. |
| Consul Config | Có thể ném exception khi không tải được cấu hình. | spring.cloud.consul.config.fail-fast, mặc định hiện hành true. |
| Consul Discovery registration | Có thể ném exception khi đăng ký thất bại hoặc log warning để tiếp tục. | spring.cloud.consul.discovery.fail-fast. |
| ZooKeeper Config | Có thể fail startup khi config lookup lỗi. | spring.cloud.zookeeper.config.fail-fast. |
| Kubernetes ConfigMap/Secret | Có thể tiếp tục với warning hoặc fail theo cấu hình. | spring.cloud.kubernetes.config.fail-fast, spring.cloud.kubernetes.secrets.fail-fast. |

Với Spring Cloud Config sử dụng spring.config.import, tiền tố optional: cho phép ứng dụng tiếp tục khi Config Server không có sẵn, còn import bắt buộc có thể làm startup thất bại. Nếu cấu hình từ xa chứa credential, URL hoặc feature flag bắt buộc, không dùng optional một cách tùy tiện.

Một fallback config an toàn cần có version, nguồn gốc và thời hạn sử dụng rõ ràng. Không tự động dùng cấu hình cũ vô thời hạn nếu nó có thể trỏ tới endpoint đã bị thu hồi hoặc dùng credential hết hạn.

## 11. Giữ readiness đúng trong chế độ degraded

Khi registry không truy cập được, tránh dùng liveness probe để buộc container restart liên tục. Liveness nên phản ánh process có bị hỏng nội bộ hay không; registry outage là trạng thái dependency bên ngoài.

Một thiết kế thường dùng:

- Process vẫn khởi động và liveness vẫn healthy.
- Readiness ở REFUSING_TRAFFIC khi service chưa được công bố hoặc không thể gọi dependency bắt buộc.
- Retry registration trong background theo backoff.
- Khi registration thành công và điều kiện nghiệp vụ hoàn tất, chuyển readiness sang ACCEPTING_TRAFFIC.
- Nếu retry vượt deadline và registry là bắt buộc, kết thúc startup hoặc phát cảnh báo theo chính sách đã chọn.

Với Spring Boot, có thể phát AvailabilityChangeEvent để thay đổi ReadinessState:

~~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class StartupReadiness {

    private final ApplicationContext context;

    public StartupReadiness(ApplicationContext context) {
        this.context = context;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~~

Đây chỉ là cơ chế thay đổi readiness. Nó không tự đăng ký service vào registry. Cần nối hai phương thức này với lifecycle/registration result của implementation cụ thể, hoặc dùng readiness probe và health integration được framework hỗ trợ.

Không gọi acceptTraffic() chỉ vì TCP connection tới registry đã mở. Cần xác minh registration thành công, instance metadata đúng và các dependency bắt buộc đã sẵn sàng.

## 12. Tránh đăng ký trùng khi retry

Khi registry phục hồi, nhiều callback hoặc nhiều lớp retry có thể cùng cố đăng ký instance. Điều này dễ tạo bản ghi trùng hoặc ghi đè registration của một replica khác.

Các nguyên tắc:

- Dùng instance ID duy nhất cho mỗi process/replica.
- Giữ instance ID ổn định trong suốt một vòng đời process.
- Phân biệt retry một logical registration với tạo registration mới.
- Dùng cơ chế idempotent của registry/client khi có thể.
- Không gọi ServiceRegistry.register() từ mọi sự kiện reconnect nếu framework đã tự quản lý re-registration.
- Khi retry thất bại, giữ readiness false cho tới khi registration được xác minh.
- Khi shutdown, deregister nếu registry còn truy cập được; nếu không, dựa vào lease/heartbeat/session cleanup theo công nghệ.

Với ZooKeeper, ephemeral node gắn với session. Với Consul, registration có service ID và health check/TTL. Với Eureka, instance ID và lease renewal giúp server nhận biết instance. Các cơ chế cleanup khác nhau nên logic retry phải theo đúng implementation.

## 13. Timeout và ngân sách startup

Đặt timeout theo từng tầng:

| Tầng | Giới hạn cần xác định |
| --- | --- |
| DNS | Thời gian resolve hostname registry. |
| TCP connect | Thời gian mở socket tới registry. |
| TLS handshake | Thời gian thiết lập kênh TLS và xác thực chứng thư. |
| Registry request | Thời gian chờ response của register/lookup. |
| Retry backoff | Tổng thời gian chờ giữa các lần thử. |
| Startup deadline | Tổng ngân sách từ lúc process start tới khi fail hoặc chuyển degraded. |
| Readiness | Điều kiện và thời gian tối đa instance được giữ unready. |

Không để timeout của mỗi request lớn hơn nhiều so với startup deadline. Ví dụ, nếu startup chỉ được phép chờ 30 giây nhưng một lần connect timeout là 3 phút, retry policy không thể thực hiện đúng ngân sách.

Một phép tính đơn giản:

~~~~text
Startup wait budget
= tổng request timeout
+ tổng backoff delay
+ thời gian khởi tạo local
~~~~

Đây là phép cộng bảo thủ; một số thao tác có thể chạy song song. Hãy đo startup thực tế để chọn deadline.

## 14. Kubernetes orchestration và restart storm

Nếu chạy trên Kubernetes, ba probe có vai trò khác nhau:

- startupProbe: cho ứng dụng thời gian khởi động ban đầu.
- livenessProbe: phát hiện process/container không thể tiếp tục hoạt động.
- readinessProbe: quyết định Pod có nhận traffic từ Service hay không.

Nếu registry ngừng hoạt động, không nên mặc định làm liveness thất bại. Khi đó tất cả Pod có thể bị restart, cùng lúc reconnect và tạo thêm tải lên registry. Đây là restart storm.

Với start-degraded:

- Startup probe kiểm tra ứng dụng đã khởi tạo cục bộ.
- Liveness kiểm tra lỗi nội bộ.
- Readiness kiểm tra điều kiện nhận traffic, bao gồm registration nếu service cần discovery để được gọi.
- Pod vẫn chạy khi registry mất và tiếp tục retry theo backoff.

Nếu chính sách là fail-fast, ứng dụng nên thực hiện retry có deadline rồi thoát với exit code khác 0. Kubernetes sẽ áp dụng restart backoff. Hãy cấu hình rollout và autoscaling để không tạo hàng loạt replica mới trong khi registry vẫn down.

## 15. Quy trình chẩn đoán khi startup thất bại

Khi ứng dụng không khởi động được vì registry, kiểm tra theo thứ tự:

1. **Xác định giai đoạn:** lỗi xuất hiện khi tải remote config, tạo DiscoveryClient, mở kết nối hay đăng ký instance?
2. **Đọc exception gốc:** connection refused, timeout, DNS, TLS, 401/403, NOAUTH hay API resource not found?
3. **Kiểm tra endpoint:** hostname, port, scheme, path và namespace.
4. **Kiểm tra xác thực:** token, username/password, certificate, ACL và quyền RBAC.
5. **Kiểm tra registry health:** server/agent/ensemble/quorum và leader state.
6. **Kiểm tra retry:** số lần thử, timeout, backoff, jitter và retry budget.
7. **Kiểm tra registration:** service ID, instance ID, host, port, metadata và trạng thái health.
8. **Kiểm tra readiness:** instance đã được đưa vào routing hay vẫn REFUSING_TRAFFIC?
9. **Kiểm tra cache/visibility:** consumer đã nhìn thấy instance hay đang dùng registry view cũ?
10. **Kiểm tra phục hồi:** khi registry trở lại, client có tự retry/re-register hay cần hành động vận hành?

### Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Consul agent unavailable làm startup fail | discovery.fail-fast=true và retry đã hết. | Kiểm tra retry dependency, fail-fast policy và agent health. |
| Consul Config fail dù Discovery fail-fast false | config.fail-fast=true ở giai đoạn tải property source. | Xác định config có bắt buộc không; dùng fallback đã kiểm soát nếu được phép. |
| Eureka client khởi tạo thất bại ngay | should-enforce-registration-at-init=true hoặc lỗi cấu hình nghiêm trọng. | Kiểm tra service URL, kết nối và chính sách fail-fast. |
| Eureka app chạy nhưng chưa xuất hiện trong registry | Đăng ký ban đầu thất bại và không enforce init. | Kiểm tra log register/heartbeat, peer URL và retry. |
| ZooKeeper connection timeout | Ensemble không có quorum, DNS/network lỗi hoặc timeout quá ngắn. | Kiểm tra quorum, connection string, session và retry policy. |
| ZooKeeper NOAUTH | ACL hoặc credential không đúng. | Sửa identity/ACL; không retry liên tục. |
| Kubernetes API trả 403 | ServiceAccount thiếu quyền get/list/watch. | Cấp RBAC tối thiểu cho đúng namespace/resource. |
| Kubernetes EndpointSlice API not found | Bật EndpointSlice trên cluster không hỗ trợ. | Kiểm tra API discovery.k8s.io/v1 hoặc tắt cấu hình nếu cần. |
| Pod Running nhưng không Ready | Registration hoặc dependency bắt buộc chưa sẵn sàng. | Kiểm tra readiness endpoint và registry visibility. |
| Nhiều pod retry cùng lúc | Không có jitter hoặc retry policy bị lồng nhau. | Thêm jitter, giới hạn concurrency và loại retry wrapper trùng. |

## 16. Kiểm thử startup khi registry unavailable

Không chỉ kiểm thử happy path. Cần mô phỏng các tình huống:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Registry tắt trước khi ứng dụng start, fail-fast bật | Ứng dụng retry đúng ngân sách rồi dừng với log rõ ràng. |
| Registry tắt trước khi ứng dụng start, start-degraded | Process khởi động, readiness false, retry tiếp tục có kiểm soát. |
| Registry phục hồi sau 20 giây | Instance đăng ký thành công và readiness chuyển true sau xác minh. |
| Registry phục hồi nhưng credential sai | Retry không vô hạn; log phân loại authentication failure và không công bố instance. |
| DNS registry sai | Lỗi được nhận diện là DNS/configuration; không tạo retry storm. |
| Nhiều replica start đồng thời | Jitter phân tán request, registry không bị burst retry quá mức. |
| Registry mất sau khi app đã ready | App không restart chỉ vì registry mất; hành vi cache và readiness theo policy. |
| Registry restart trong rolling deployment | Instance cũ và mới không đăng ký trùng; consumer có thể failover. |
| EndpointSlice API không tồn tại | Discovery client báo lỗi khởi tạo rõ ràng khi tính năng được bật. |
| Config registry unavailable | Chính sách config fail-fast/optional được kiểm tra độc lập với discovery registration. |

Một bài test start-degraded cần xác minh cả ba trạng thái: process còn sống, readiness false, và registration được tạo sau khi registry phục hồi. Chỉ nhìn log Started Application là chưa đủ.

## 17. Checklist thiết kế

- [ ] Đã xác định registry là dependency bắt buộc hay tùy chọn.
- [ ] Đã phân biệt remote configuration và service discovery.
- [ ] Đã chọn fail-fast hoặc start-degraded theo hợp đồng nghiệp vụ.
- [ ] Đã giới hạn số lần retry và tổng startup deadline.
- [ ] Đã cấu hình backoff, max interval và jitter.
- [ ] Đã phân loại lỗi transient với lỗi cấu hình/xác thực.
- [ ] Đã kiểm tra hành vi retry theo đúng phiên bản Spring Cloud.
- [ ] Đã phân biệt Consul Config fail-fast và Consul Discovery fail-fast.
- [ ] Đã kiểm tra should-enforce-registration-at-init của Eureka.
- [ ] Đã kiểm tra Curator connection wait, session và retry policy của ZooKeeper.
- [ ] Đã xác minh Kubernetes ServiceAccount, RBAC, namespace và EndpointSlice API.
- [ ] Đã giữ readiness false cho tới khi instance có thể nhận traffic an toàn.
- [ ] Không dùng liveness probe để restart pod chỉ vì registry tạm thời down.
- [ ] Đã bảo đảm registration retry không tạo instance trùng.
- [ ] Đã kiểm thử registry tắt, phục hồi, credential sai và nhiều replica startup cùng lúc.
- [ ] Đã có log, metric và alert cho registration failure, retry exhaustion và thời gian chờ registry.

## Ghi nhớ

- Process started, registered và ready là ba trạng thái khác nhau.
- Registry không truy cập được không luôn buộc ứng dụng phải thoát; quyết định phụ thuộc vào việc registry có bắt buộc cho nghiệp vụ hay không.
- Fail-fast phù hợp khi không thể phục vụ an toàn nếu thiếu registry hoặc remote config.
- Start-degraded cần giữ readiness false cho tới khi registration và điều kiện phục vụ được xác minh.
- Retry phải có timeout, giới hạn số lần, backoff và jitter.
- Consul có retry registration; discovery fail-fast và config fail-fast là hai chính sách riêng.
- Eureka có should-enforce-registration-at-init, mặc định hiện hành là false.
- ZooKeeper dùng Curator session và retry policy; connection wait không đồng nghĩa retry vô hạn.
- Kubernetes Service DNS khác với Spring Cloud Kubernetes DiscoveryClient gọi API server.
- Không dùng liveness để xử lý registry outage; làm vậy có thể gây restart storm.
- Luôn kiểm thử registry phục hồi sau khi ứng dụng đã khởi động degraded.

## Tài liệu tham khảo chính thức

- [Spring Cloud Consul – Retry](https://docs.spring.io/spring-cloud-consul/reference/retry.html)
- [Spring Cloud Consul – Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul – Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Netflix – Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Zookeeper – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
- [Apache Curator – Retry Policies](https://curator.apache.org/docs/retry-policy/)
- [Spring Cloud Kubernetes – DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)
- [Spring Cloud Config – Client Fail Fast and Retry](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Commons – DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
