# Kiểm tra khả năng hỗ trợ của từng implementation discovery và HTTP client

Một ứng dụng Spring Cloud có thể chạy tốt trên JVM thông thường nhưng không khởi động được sau khi bật Spring AOT, GraalVM Native Image hoặc JVM checkpoint/restore. Nguyên nhân thường nằm ở implementation cụ thể: discovery client, registry client, HTTP transport, connection pool, proxy, runtime reflection hoặc tài nguyên đang mở.

Vì vậy, không nên đánh giá “Spring Cloud có hỗ trợ AOT” như một kết luận áp dụng cho mọi starter. Cần kiểm tra từng implementation thực sự có trong classpath và từng HTTP client mà Spring Boot chọn lúc chạy.

Bài học thuộc chương **AOT và checkpoint** của module **SPRING_CLOUD_CORE**. Nội dung phân biệt Spring AOT, Native Image và CRaC; lập ma trận hỗ trợ theo discovery implementation và HTTP client; chỉ ra điều kiện cấu hình quan trọng; và xây dựng quy trình kiểm thử để xác nhận ứng dụng có thể build, start, discover, gọi HTTP, checkpoint và restore trên môi trường mục tiêu.

## 1. Ba khái niệm không được đánh đồng

### 1.1. Spring AOT

Spring AOT phân tích ứng dụng trong build time và sinh mã/metadata để tối ưu cách tạo ApplicationContext. Quá trình này cần biết trước một phần cấu trúc bean, điều kiện cấu hình, proxy, reflection, resource và service client.

AOT có thể tạo mã tối ưu cho JVM hoặc làm bước bắt buộc khi build GraalVM Native Image. Một ứng dụng chạy được trên JVM với mã AOT đã sinh có độ tin cậy cao hơn, nhưng chưa thay thế việc build và chạy native executable thật.

### 1.2. GraalVM Native Image

Native Image biên dịch ứng dụng và dependency thành executable theo mô hình closed-world. Những lớp, method, resource hoặc proxy chỉ được nạp động ở runtime có thể không tồn tại trong image nếu build không phát hiện được.

Một số giới hạn thường gặp:
- Reflection hoặc proxy không được khai báo runtime hints.
- Resource nằm trong JAR không được đưa vào image.
- Cấu hình làm thay đổi bean graph ở runtime trong khi bean graph đã được chốt tại build time.
- Service ID hoặc client được tạo động mà AOT không thể suy ra.
- Thư viện dùng class loading hoặc serialization động mà không có hint phù hợp.

### 1.3. JVM Checkpoint/Restore với CRaC

CRaC chụp trạng thái của một JVM đang chạy và khôi phục trạng thái đó sau này. Khác với Native Image, CRaC không biên dịch ứng dụng thành executable native; nó lưu snapshot bộ nhớ và trạng thái tiến trình đã được chuẩn bị.

CRaC đặc biệt nhạy với tài nguyên hệ điều hành và tài nguyên bên ngoài:
- Socket đang mở.
- HTTP connection pool và database pool.
- File handle.
- Thread đang chờ I/O.
- DNS hoặc địa chỉ IP đã cache.
- Token, credential và session có thời hạn.
- Registration, heartbeat hoặc lease ở service registry.
- Scheduler có công việc đến hạn trong thời gian JVM bị checkpoint.

Spring Framework tích hợp CRaC qua lifecycle của bean. Trước checkpoint, các bean Lifecycle/SmartLifecycle được dừng để giải phóng tài nguyên; sau restore, chúng được khởi động lại. Thư viện không tích hợp Spring có thể cần adapter triển khai org.crac.Resource.

### 1.4. Bảng phân biệt

| Tiêu chí | Spring AOT | GraalVM Native Image | CRaC |
| --- | --- | --- | --- |
| Thời điểm xử lý | Build time | Build time và native compilation | Khi JVM đang chạy |
| Artifact | Mã/metadata AOT | Native executable | Snapshot JVM |
| Reflection/resource | Cần hints khi không suy ra được | Cần hints/resource configuration | Có trong trạng thái JVM, nhưng resource hệ điều hành phải được xử lý |
| Bean graph | Một số quyết định được cố định ở build time | Closed-world, cần cấu trúc xác định | Giữ trạng thái bean đã tạo |
| Socket và pool | Không phải trọng tâm | Được tạo khi process chạy | Phải đóng trước và mở lại sau restore nếu không thể giữ |
| Refresh scope | Không được hỗ trợ trong Spring Cloud AOT mode | Không được hỗ trợ | Có thể được refresh khi restart thông qua Spring Cloud Context |
| Mục tiêu | Tối ưu khởi tạo context | Giảm footprint và startup | Giảm thời gian khởi động/warm-up bằng snapshot |

Không dùng kết quả kiểm thử AOT để kết luận CRaC đã an toàn. Một implementation có thể có runtime hints đầy đủ nhưng vẫn giữ socket không thể khôi phục. Ngược lại, một HTTP client có thể xử lý socket tốt khi restore nhưng thiếu reflection hint cho Native Image.

## 2. Ma trận hỗ trợ discovery implementation

Tài liệu chính thức không công bố một ma trận AOT/Native Image/CRaC đồng nhất cho tất cả discovery provider. Bảng dưới đây chỉ đánh dấu hỗ trợ khi tài liệu của implementation nói rõ; trường hợp chưa có tuyên bố cụ thể phải được kiểm thử trên BOM và runtime mục tiêu.

| Discovery implementation | Spring AOT / Native Image | Điều kiện hoặc giới hạn | CRaC / checkpoint |
| --- | --- | --- | --- |
| Eureka Client | Có hỗ trợ | Tắt spring.cloud.refresh.enabled; không dùng random server port | Cần xác minh đăng ký lại, heartbeat, registry cache và HTTP transport sau restore |
| Eureka Server | Chưa hỗ trợ | Tài liệu Netflix ghi rõ không hỗ trợ AOT/native | Chưa có cam kết riêng; không suy ra từ Eureka Client |
| Spring Cloud Kubernetes Discovery | Chưa hỗ trợ theo tài liệu hiện hành | Tài liệu ghi chưa hỗ trợ Spring Boot AOT transformations hoặc native images | Chưa có ma trận CRaC riêng; cần kiểm tra Kubernetes client, watch và API connection |
| Spring Cloud Consul Discovery | Chưa có tuyên bố AOT riêng trong reference hiện hành | Kiểm tra Consul client, health check, TLS và runtime hints theo version | Kiểm tra Consul session, health check, connection và re-registration |
| Spring Cloud Zookeeper Discovery | Chưa có tuyên bố AOT riêng trong reference hiện hành | Kiểm tra client library, serialization, watcher và dependency runtime | Kiểm tra ZooKeeper session, connection và watcher sau restore |
| SimpleDiscoveryClient | Không có tuyên bố hỗ trợ riêng theo implementation | Nguồn instance là properties; kiểm tra binding và service ID tại build/runtime | Không có registry session, nhưng cần xác minh cấu hình và client cache sau restore |
| Spring Cloud LoadBalancer | Có hỗ trợ từ 4.0.0 | Phải khai báo tường minh các LoadBalancerClient service ID | Kiểm tra child context, supplier, cache và discovery delegate sau restore |
| Spring Cloud Config Client | Có hỗ trợ từ 4.0.0 | Config source phải truy cập được khi build AOT; tắt refresh scope; không dùng config-first legacy bootstrap | Kiểm tra kết nối Config Server/backend và việc tải cấu hình lại sau restore |

**Chưa có tuyên bố hỗ trợ không đồng nghĩa với đã được xác nhận là không hỗ trợ.** Điều đó có nghĩa tài liệu chính thức không đưa ra cam kết để ứng dụng có thể dựa vào. Hãy coi implementation đó là chưa được xác minh cho đến khi test thành công trên đúng release train.

### 2.1. Eureka Client

Spring Cloud Netflix xác nhận Eureka Client hỗ trợ Spring AOT transformations và Native Image khi tắt refresh mode:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Ngoài ra, random port không được hỗ trợ trong AOT/Native Image vì closed-world assumption. Với ứng dụng đăng ký vào Eureka, cần xác định host và port có thể dự đoán tại build/deploy.

Không nhầm điều kiện trên với Eureka Server. Tài liệu hiện hành ghi rõ Eureka Server không hỗ trợ Spring AOT transformations hoặc Native Image.

Khi chạy CRaC, cần kiểm tra riêng:
- Eureka client có đóng kết nối HTTP trước checkpoint không?
- Sau restore, client có đăng ký lại hoặc tiếp tục renewal đúng cách không?
- Instance metadata có còn hợp lệ với host, port và network interface mới không?
- Registry có còn giữ registration cũ trong khi process đang tạm dừng không?
- Client cache có được làm mới đúng thời điểm không?

AOT support của Eureka Client không phải cam kết rằng tất cả các tình huống checkpoint/restore đã được xử lý.

### 2.2. Spring Cloud Kubernetes Discovery

Tài liệu Spring Cloud Kubernetes hiện hành ghi rõ project chưa hỗ trợ Spring Boot AOT transformations hoặc Native Image. Không nên đưa starter Kubernetes Discovery vào native image production chỉ dựa trên việc Spring Boot application cơ bản đã build thành công.

Nếu mục tiêu là deploy native Spring Boot app trên Kubernetes, hãy đánh giá xem có thực sự cần Spring Cloud Kubernetes hay không. Kubernetes đã cung cấp service discovery qua Service DNS, EndpointSlice và các API nền tảng. Một ứng dụng Spring Boot có thể dùng DNS/service address thông thường mà không cần thêm discovery implementation của Spring Cloud Kubernetes.

Nếu ứng dụng bắt buộc dùng Spring Cloud Kubernetes Discovery:
- Kiểm tra trạng thái hỗ trợ của release cụ thể trước khi bật AOT/native.
- Tách test discovery khỏi test native image để xác định dependency gây lỗi.
- Kiểm tra Fabric8 Kubernetes Client hoặc Kubernetes Java Client được starter lựa chọn.
- Kiểm tra service account, namespace, RBAC và API endpoint.
- Không giả định client watch hoặc informer có thể được khôi phục từ CRaC snapshot mà không mở lại kết nối.

### 2.3. Consul và Zookeeper

Không tìm thấy tuyên bố hỗ trợ AOT/Native Image riêng trong reference hiện hành của hai discovery provider này. Vì vậy, cần kiểm tra trên đúng version:

- Runtime hints cho reflection, serialization và resource.
- Client có tải class hoặc provider động không?
- Cấu hình TLS, truststore, credential và namespace có được resolve tại build time không?
- Watcher/listener có được đăng ký lại sau context restart không?
- Connection/session có được đóng và tạo lại sau CRaC restore không?
- Health check và registration có được cập nhật sau khi instance phục hồi không?

Spring Cloud Config Client có tài liệu AOT riêng và có thể kết nối các backend như Config Server, Consul, Zookeeper hoặc Vault. Điều đó không tự động chứng minh Consul Discovery hoặc Zookeeper Discovery có cùng mức hỗ trợ AOT.

### 2.4. SimpleDiscoveryClient

SimpleDiscoveryClient lấy instance từ cấu hình thay vì kết nối tới một registry server. Vì vậy, nó giảm số lượng thành phần bên ngoài cần kiểm thử.

Ví dụ:

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

Với AOT, cần bảo đảm property source và danh sách service được nạp theo cấu hình đã biết tại build time/runtime. Với CRaC, không có registry session để khôi phục, nhưng HTTP client, DNS cache và LoadBalancer cache vẫn cần được kiểm tra.

Không dùng SimpleDiscoveryClient để thay thế một registry động nếu ứng dụng cần tự đăng ký, heartbeat hoặc cập nhật instance khi replica xuất hiện và biến mất.

## 3. Khai báo service ID tường minh cho LoadBalancer

Spring Cloud LoadBalancer hỗ trợ AOT và Native Image từ phiên bản 4.0.0. Điều kiện quan trọng là phải khai báo rõ service ID mà ứng dụng sẽ load-balance.

Có thể dùng annotation:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(name = "catalog-service")
public class CatalogLoadBalancerConfiguration {
}
~~~

Hoặc khai báo bằng properties:

~~~yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - catalog-service
          - inventory-service
          - pricing-service
~~~

Ví dụ với nhiều client:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClients;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClients({
        @LoadBalancerClient(name = "catalog-service"),
        @LoadBalancerClient(name = "inventory-service"),
        @LoadBalancerClient(name = "pricing-service")
})
public class ServiceLoadBalancerClients {
}
~~~

Không dựa vào service ID chỉ xuất hiện trong chuỗi URI được tạo động ở runtime. AOT cần biết các client context cần được cấu hình.

### 3.1. Vì sao cần service ID tường minh?

Spring Cloud LoadBalancer tạo child ApplicationContext riêng cho từng service ID. Mặc định các context này được khởi tạo lazy khi có request đầu tiên. Trong AOT, danh sách service ID cần được xác định trước để quá trình xử lý context có thể tạo metadata tương ứng.

Vì vậy, kiểm tra:
- Danh sách service ID có đầy đủ không?
- URI logical có trùng chính tả với service ID khai báo không?
- Service ID có được tạo từ property động mà build time không biết không?
- Các custom ServiceInstanceListSupplier có được đăng ký đúng context không?
- Các cấu hình theo service ID có được phát hiện trong AOT không?

### 3.2. Không tạo cấu hình LoadBalancer bằng dữ liệu chỉ có ở runtime

Không nên phụ thuộc vào danh sách service được đọc từ database sau khi native image đã build rồi mới tạo các child context. Nếu số service có thể thay đổi, cần chọn thiết kế phù hợp với closed-world assumption hoặc chuyển phần thay đổi sang dữ liệu runtime không làm thay đổi bean graph.

## 4. Spring Cloud OpenFeign và điều kiện AOT

Spring Cloud OpenFeign hỗ trợ Spring AOT transformations và Native Image, nhưng cần đáp ứng các điều kiện:

- spring.cloud.refresh.enabled=false.
- Không bật spring.cloud.openfeign.client.refresh-enabled=true.
- Không bật spring.cloud.openfeign.lazy-attributes-resolution=true.

Ví dụ:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
    openfeign:
      client:
        refresh-enabled: false
      lazy-attributes-resolution: false
~~~

Đây là các điều kiện liên quan đến AOT/native. Không bật refresh chỉ vì ứng dụng muốn đổi URL hoặc Feign client runtime.

### 4.1. URL của Feign client và service ID

Với load balancing, Feign client dùng tên service:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
public interface CatalogClient {

    @GetMapping("/api/catalog")
    CatalogResponse getCatalog();
}
~~~

Tên catalog-service phải tương ứng service ID được discovery và LoadBalancer biết.

Nếu khai báo URL cố định trong FeignClient, client có thể gọi trực tiếp endpoint đó mà không qua load balancing. Tài liệu OpenFeign cũng mô tả khả năng override URL bằng system property nếu URL được khai báo qua properties ngay từ build time. Không giả định mọi giá trị URL có thể được thay đổi tự do sau khi native image đã được tạo.

### 4.2. Lazy attribute resolution

Lazy attribute resolution có thể hữu ích trong một số test hoặc môi trường cần trì hoãn việc resolve annotation attribute. Nhưng AOT/native cần cấu trúc xác định khi build.

Nếu ứng dụng dùng Spring Cloud Contract hoặc test context cần lazy resolution, hãy tách cấu hình test và production. Không bật lazy resolution trên native runtime nếu điều kiện AOT của OpenFeign yêu cầu tắt.

## 5. Spring Cloud Config Client trong AOT/native

Spring Cloud Config Client hỗ trợ AOT transformations và Native Image từ phiên bản 4.0.0. Tuy nhiên, có một số điều kiện quan trọng:

1. Không dùng config-first legacy bootstrap với spring.config.use-legacy-processing=true.
2. Tắt refresh scope bằng spring.cloud.refresh.enabled=false.
3. Nguồn dữ liệu cấu hình từ xa mà Config Client kết nối phải truy cập được trong lúc build AOT.
4. Các property ảnh hưởng bean creation phải nhất quán giữa build time và runtime.
5. Tính đến thời gian gọi Config Server/backend khi ứng dụng native khởi động.

Ví dụ:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
    config:
      uri: https://config.internal
~~~

Nếu Config Server yêu cầu TLS hoặc authentication, môi trường build AOT cũng phải có network route và credential phù hợp. Không đưa secret production vào image hoặc build log; hãy dùng secret injection an toàn cho quá trình build.

### 5.1. Config Client kết nối Consul hoặc Zookeeper

Tài liệu Config Client liệt kê Consul và Zookeeper như những nguồn cấu hình có thể được sử dụng. Khi AOT xử lý context, datasource đó phải có thể truy cập để resolve cấu hình.

Điều này có nghĩa:
- Kiểm thử riêng việc build khi Config Server/backend tạm thời không truy cập được.
- Xác định property nào cần được cung cấp tại build time.
- Giữ các property ảnh hưởng bean graph nhất quán khi chạy.
- Không coi một cấu hình Consul backend thành công là bằng chứng Consul Discovery native image được hỗ trợ.

## 6. Ma trận Spring HTTP client

Spring Boot có nhiều abstraction HTTP. AOT/Native Image support của abstraction Spring không đồng nghĩa mọi implementation bên dưới đều có cùng khả năng. Cần kiểm tra cả API client và HTTP transport được chọn.

### 6.1. RestTemplate và RestClient

Spring Boot tự phát hiện HTTP client dùng với RestTemplate và RestClient theo classpath. Thứ tự ưu tiên hiện hành trong tài liệu Boot 4.1 là:

| Thứ tự | Request factory / HTTP client |
| --- | --- |
| 1 | Apache HttpClient |
| 2 | Jetty HttpClient |
| 3 | Reactor Netty HttpClient |
| 4 | JDK java.net.http.HttpClient |
| 5 | Simple JDK HttpURLConnection |

Nếu nhiều implementation cùng có mặt, client ưu tiên cao nhất được chọn trừ khi ứng dụng cấu hình factory cụ thể.

Ví dụ ép dùng JDK client:

~~~yaml
spring:
  http:
    clients:
      imperative:
        factory: jdk
~~~

Ví dụ ép dùng Jetty:

~~~yaml
spring:
  http:
    clients:
      imperative:
        factory: jetty
~~~

### 6.2. WebClient

Spring Boot tự phát hiện ClientHttpConnector cho WebClient theo classpath:

| Thứ tự | Reactive HTTP client |
| --- | --- |
| 1 | Reactor Netty |
| 2 | Jetty RS client |
| 3 | Apache HttpClient |
| 4 | JDK HttpClient |

Ví dụ ép dùng Jetty connector:

~~~yaml
spring:
  http:
    clients:
      reactive:
        connector: jetty
~~~

Nếu không cố định implementation, thêm hoặc bỏ dependency có thể làm Spring Boot chọn một transport khác. Điều này có thể thay đổi behavior về connection pool, TLS, cookie, proxy và lifecycle.

### 6.3. Ma trận đánh giá AOT và CRaC theo HTTP client

| API / transport | Spring Boot hỗ trợ cấu hình | AOT/native | CRaC/checkpoint |
| --- | --- | --- | --- |
| RestTemplate | Có | Dùng được với AOT của ứng dụng nếu request factory và dependency có hints phù hợp; không có cam kết riêng cho mọi factory | Phải kiểm tra lifecycle của underlying connection pool |
| RestClient | Có | Dùng được với AOT của ứng dụng nếu request factory và dependency có hints phù hợp | Phải đóng/rebuild resource của HTTP transport nếu cần |
| WebClient + Reactor Netty | Có | Kiểm thử native image với đúng Reactor Netty version và resource hints | Kiểm tra event loop, connection pool, socket và DNS sau restore |
| WebClient + Jetty | Có | Kiểm thử native image với Jetty RS client và runtime hints của dependency | Kiểm tra Jetty HttpClient và connection pool lifecycle |
| Apache HttpClient | Có | Kiểm thử đúng major version, reflection/resource hints và TLS provider | Đóng/reopen connection manager và pool |
| JDK HttpClient | Có | Kiểm thử theo JDK và native-image toolchain mục tiêu | Kiểm tra socket/executor và việc tạo lại client sau restore |
| HttpURLConnection | Có | Kiểm thử hành vi trong native image mục tiêu | Không giả định connection state có thể giữ qua checkpoint |

Tài liệu Spring Boot mô tả các lựa chọn transport và cách chọn chúng, nhưng không đưa ra cam kết rằng từng phiên bản Apache, Jetty, Reactor Netty hoặc JDK client đều có cùng chứng nhận CRaC. Không suy diễn hỗ trợ CRaC từ việc Spring Boot có thể auto-configure client đó.

### 6.4. Kiểm tra transport thực sự được chọn

Không chỉ nhìn dependency declaration. Hãy xác nhận implementation tại runtime bằng:
- Bean ClientHttpConnector được inject cho WebClient.
- Request factory được dùng bởi RestClient/RestTemplate.
- Dependency tree của HTTP transport.
- Log startup hoặc debug condition report.
- Một integration test gọi endpoint qua đúng client bean.

Nếu ứng dụng muốn tính tái lập giữa máy developer, CI và production, hãy cấu hình factory rõ ràng thay vì phụ thuộc thứ tự ưu tiên classpath.

## 7. Spring Cloud LoadBalancer với từng HTTP API

Spring Cloud LoadBalancer cung cấp các integration:
- BlockingLoadBalancerClient cho RestTemplate và RestClient.
- ReactorLoadBalancerExchangeFilterFunction cho WebClient.
- Spring Cloud OpenFeign dùng blocking mode của LoadBalancer.
- Từ Spring Cloud LoadBalancer 5.0.0, có integration với Spring HTTP Service Clients auto-configuration.

Với AOT/native, ngoài việc chọn đúng HTTP API, phải khai báo service ID rõ ràng như phần trước. Với CRaC, cần kiểm tra cả child context của LoadBalancer và transport bên dưới.

### 7.1. RestClient load-balanced

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Ví dụ trên minh họa builder được đánh dấu LoadBalanced; trong ứng dụng thật, hãy dùng auto-configured builder hoặc configurer phù hợp với Spring Boot version để giữ các customizer và request factory đã cấu hình.

### 7.2. WebClient load-balanced

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveCatalogHttpConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder catalogWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Khi dùng service ID trong URI, LoadBalancer chuyển URI logic thành địa chỉ instance. AOT vẫn cần biết service ID được sử dụng; CRaC cần kiểm tra resource của connector và LoadBalancer supplier sau restore.

### 7.3. HTTP Service Clients

Spring Cloud LoadBalancer 5.0.0 trở lên tích hợp với Spring HTTP Service Clients auto-configuration. Với group có baseUrl rỗng hoặc scheme lb, LoadBalancer có thể cấu hình base URL theo service ID từ group name.

Đối với AOT, khai báo group và client interface tường minh tại build time. Đối với CRaC, kiểm tra underlying RestClient hoặc WebClient group configurer và lifecycle của transport.

## 8. Refresh Scope có giới hạn đặc biệt trong AOT/native

Spring Cloud Context không hỗ trợ Context Refresh cho Spring AOT transformations và Native Image. Khi dùng AOT/native, cần:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Điều này áp dụng cho cơ chế refresh scope của Spring Cloud Context. Không cố bật RefreshScope để thay đổi bean graph sau khi native image đã được build.

Cần phân biệt:
- spring.cloud.refresh.enabled: bật/tắt refresh scope và các chức năng context refresh.
- spring.cloud.openfeign.client.refresh-enabled: bật refresh cho Feign client.
- spring.cloud.refresh.on-restart.enabled: điều khiển refresh khi JVM restart sau checkpoint/restore.
- spring.cloud.loadbalancer.eager-load.clients: khai báo service ID cho LoadBalancer; không phải cờ refresh.

### 8.1. Refresh Scope on Restart cho CRaC

Spring Cloud Context cung cấp RefreshScopeLifecycle để kích hoạt Context Refresh khi JVM restart sau CRaC restore. Việc refresh có thể rebind configuration properties và làm mới bean RefreshScope.

Có thể tắt behavior này bằng:

~~~yaml
spring:
  cloud:
    refresh:
      on-restart:
        enabled: false
~~~

Đây là behavior dành cho restart/checkpoint lifecycle, không làm cho refresh scope trở nên tương thích với AOT/native image. Hai chế độ cần được cấu hình và kiểm thử riêng.

### 8.2. RefreshScopeHealthIndicator

Spring Cloud có RefreshScopeHealthIndicator để theo dõi lỗi khi rebind hoặc khởi tạo lại bean sau context refresh. Nếu một bean không thể khởi tạo lại, health indicator có thể chuyển sang DOWN và hiển thị exception liên quan.

Trong môi trường CRaC, cần quan sát health sau restore trước khi cho instance nhận traffic. Không chỉ kiểm tra process đã khởi động lại mà phải xác nhận các bean refreshable đã sẵn sàng.

## 9. CRaC và vòng đời discovery client

Một discovery client thường có nhiều tài nguyên sống lâu:
- HTTP client kết nối registry.
- Scheduled heartbeat hoặc health update.
- Registry cache.
- Watcher hoặc long-polling connection.
- Authentication token.
- Session hoặc lease có thời hạn.

Khi JVM bị checkpoint trong thời gian dài, những tài nguyên này có thể không còn hợp lệ khi restore. Ví dụ:
- Registry đã hết lease của instance.
- Token đã hết hạn.
- Socket bị đóng bởi firewall.
- DNS đã thay đổi.
- Instance được restore ở host hoặc network namespace khác.
- Registry đã nhận một registration mới từ instance khác dùng cùng identity.

### 9.1. Chu trình cần kiểm thử

~~~mermaid
flowchart TD
    A["Khởi động ứng dụng"] --> B["Kết nối discovery và HTTP client"]
    B --> C["Đăng ký service / tải instance list"]
    C --> D["Warm up các luồng thường dùng"]
    D --> E["Trước checkpoint: dừng bean và đóng tài nguyên"]
    E --> F["CRaC lưu JVM snapshot"]
    F --> G["Restore JVM"]
    G --> H["Sau restore: mở lại HTTP client và session"]
    H --> I["Refresh/rebind cấu hình nếu cần"]
    I --> J["Đăng ký hoặc gia hạn discovery"]
    J --> K["Health/readiness xác nhận"]
    K --> L["Cho phép nhận traffic"]
~~~

Không cho instance nhận traffic ngay khi JVM restore xong nếu discovery session hoặc connection pool chưa sẵn sàng.

### 9.2. Spring Lifecycle và org.crac.Resource

Với bean được quản lý bởi Spring, ưu tiên triển khai Lifecycle hoặc SmartLifecycle nếu resource có thể dừng và khởi động theo lifecycle của context.

Với thư viện không tích hợp Spring, có thể triển khai org.crac.Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public class ExternalTransportResource implements Resource {

    private final ExternalTransportFactory factory;
    private ExternalTransport transport;

    public ExternalTransportResource(ExternalTransportFactory factory) {
        this.factory = factory;
        this.transport = factory.open();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        transport.close();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        transport = factory.open();
    }
}
~~~

ExternalTransport và ExternalTransportFactory là abstraction do ứng dụng định nghĩa để quản lý một transport có thể đóng và tạo lại. Không dùng một instance đã đóng sau restore.

Nếu transport thuộc quyền quản lý của Spring Boot hoặc thư viện đã có CRaC integration, không đăng ký thêm adapter trùng lặp. Hai lifecycle handler cùng đóng/mở một resource có thể gây lỗi hoặc tạo connection ngoài dự kiến.

### 9.3. Eureka sau restore

Với Eureka Client, xác nhận:
- Client HTTP đã hoạt động lại.
- Heartbeat được gửi tới Eureka Server.
- Registration có host/port đúng với môi trường restore.
- Instance ID không xung đột với process khác.
- Client registry cache đã được cập nhật.
- LoadBalancer không chọn địa chỉ cũ.

Nếu Eureka client được refresh hoặc re-register khi context restart, theo dõi khoảng thời gian instance bị unregistered và thời điểm được đăng ký lại. Cần kiểm tra behavior theo đúng version và cấu hình Eureka đang dùng.

### 9.4. Consul và Zookeeper sau restore

Với Consul, kiểm tra session, registration, health check, ACL token và HTTP connection sau restore.

Với Zookeeper, kiểm tra session timeout, connection state, watcher registration và việc re-register ephemeral node nếu ứng dụng sử dụng loại node này.

Các bước trên là checklist vận hành cần được xác nhận bằng integration test; không có nghĩa mọi provider đều tự động xử lý toàn bộ trạng thái này.

### 9.5. Kubernetes Discovery sau restore

Nếu ứng dụng dùng Kubernetes API watch hoặc informer:
- Kiểm tra watch connection được mở lại.
- Kiểm tra resource version có còn hợp lệ.
- Nếu watch bị đóng, client có thể phải list lại và tạo watch mới.
- Kiểm tra service account token rotation.
- Kiểm tra DNS cache và EndpointSlice update.
- Kiểm tra network namespace/Pod IP sau restore.

Tài liệu AOT/native của Spring Cloud Kubernetes hiện không hỗ trợ, nhưng điều đó không tự trả lời khả năng CRaC. CRaC phải được đánh giá riêng với client và phiên bản thực tế.

## 10. CRaC và vòng đời HTTP client

HTTP client thường giữ connection pool, socket, event loop và executor. Trước checkpoint, cần bảo đảm:
- Request đang chạy đã hoàn tất hoặc bị hủy có kiểm soát.
- Không còn socket mà CRaC không thể checkpoint.
- Connection pool được đóng hoặc giải phóng.
- Thread event loop không bị treo.
- Sau restore, client có thể tạo connection mới.
- TLS/session/credential được cập nhật nếu hết hạn.
- DNS được resolve lại khi cần.

### 10.1. Reactor Netty

Với WebClient dùng Reactor Netty, kiểm tra:
- ConnectionProvider và pool lifecycle.
- LoopResources/event loop.
- Socket đang mở.
- Connection idle hoặc đang xử lý request.
- DNS resolver cache.
- SSL context và certificate rotation.

Nếu tự tạo ConnectionProvider hoặc LoopResources, ứng dụng phải quản lý disposal và recreation theo lifecycle phù hợp. Không chỉ đóng WebClient wrapper rồi cho rằng toàn bộ Netty resources đã được giải phóng.

### 10.2. Jetty HttpClient

Với Jetty, kiểm tra:
- HttpClient.stop() trước checkpoint.
- Connection pool và scheduler.
- Executor và thread.
- TLS context.
- Khả năng start() lại sau restore.
- Request đang hoạt động có được drain hoặc hủy an toàn không.

Một HTTP client đã stop không được tái sử dụng như thể nó còn đang chạy. Cần dùng factory hoặc bean lifecycle để tạo trạng thái hoạt động mới.

### 10.3. Apache HttpClient

Với Apache HttpClient, kiểm tra:
- Connection manager có đóng socket không?
- Pool có được đóng và tạo lại không?
- Evictor thread hoặc idle connection monitor có được dừng không?
- DNS resolver có cần refresh không?
- TLS socket factory và credential có thể được tái tạo không?

Nếu ứng dụng tự tạo CloseableHttpClient, hãy quản lý nó như một resource có vòng đời rõ ràng. Không giả định auto-configuration đã biết các client do ứng dụng tự tạo.

### 10.4. JDK HttpClient

Với JDK HttpClient, kiểm tra:
- Client có các request đang chạy không?
- Executor riêng có được quản lý không?
- Streaming response body có được đọc hết hoặc hủy không?
- Sau restore, client có thể tiếp tục dùng connection cũ hay cần tạo instance mới?

JDK HttpClient trên Java 21 trở lên có API shutdown/close. Nếu ứng dụng dùng JDK thấp hơn hoặc runtime cụ thể khác, hãy kiểm tra API và behavior của runtime đó thay vì gọi phương thức không tồn tại.

### 10.5. Simple JDK HttpURLConnection

Simple JDK client không cung cấp cùng mô hình connection pool và lifecycle API như Apache/Jetty/Reactor Netty. Tuy nhiên, request đang chạy, DNS cache, proxy và socket vẫn là tài nguyên cần xem xét.

Đừng coi việc không có pool bean là không có vấn đề CRaC. Chạy test checkpoint/restore trong điều kiện có request đang hoạt động và khi client đã idle.

## 11. AOT hints cho implementation tùy chỉnh

Nếu discovery provider hoặc HTTP client tùy chỉnh dùng reflection, resource loading, serialization hoặc JDK proxy mà AOT không suy ra được, cần khai báo RuntimeHints.

Ví dụ registrar:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class CatalogClientRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("catalog/client-defaults.properties");
        hints.reflection().registerType(
                CatalogWireMessage.class,
                hint -> hint.withDeclaredConstructors()
                        .withDeclaredFields()
        );
    }
}
~~~

Đăng ký registrar:

~~~java
import org.springframework.context.annotation.ImportRuntimeHints;

@ImportRuntimeHints(CatalogClientRuntimeHints.class)
public class CatalogClientConfiguration {
}
~~~

Ví dụ minh họa resource và reflection hint cho class do ứng dụng kiểm soát. Chỉ đăng ký quyền truy cập thật sự cần thiết. Không bật reflection cho toàn bộ package hoặc classpath chỉ để làm native image build qua.

### 11.1. Kiểm tra resource trong native image

Các file sau thường cần được xác nhận:
- TLS certificate/truststore.
- JSON schema hoặc serializer metadata.
- Discovery configuration.
- HTTP client service resource.
- META-INF/services.
- File cấu hình được thư viện đọc bằng ClassLoader.
- File chứa template hoặc protocol descriptor.

AOT build thành công chưa chứng minh mọi resource đều có mặt trong image. Hãy chạy native executable và thực hiện request thật để phát hiện resource thiếu.

## 12. Kiểm thử AOT theo từng implementation

Nên chạy theo từng lớp, không bật tất cả discovery provider và HTTP client cùng lúc ngay từ đầu.

### 12.1. Kiểm thử AOT trên JVM

Sau khi build mã AOT, có thể chạy ứng dụng trên JVM với:

~~~bash
java -Dspring.aot.enabled=true -jar target/application.jar
~~~

Đảm bảo JAR đã chứa mã AOT được sinh trong build. Cách này giúp kiểm tra context đã tối ưu mà không phải chờ native compilation mỗi lần.

### 12.2. Kiểm thử native image

Với Maven, bật profile native của dự án và build image theo plugin GraalVM mà dự án đang sử dụng. Sau khi build, chạy executable và xác nhận:
- ApplicationContext khởi tạo thành công.
- Discovery client kết nối đúng endpoint.
- LoadBalancer có đủ service ID.
- HTTP client được tạo đúng implementation.
- Request thành công tới instance thật hoặc test server.
- TLS, serialization và resource hoạt động.
- Health/readiness đạt trạng thái mong muốn.

Không chỉ test endpoint health. Cần có ít nhất một request đi qua discovery và load balancing để chứng minh integration thực sự hoạt động.

### 12.3. Dùng context.exit để kiểm tra startup phase

Spring Framework hỗ trợ:

~~~bash
java -Dspring.context.exit=onRefresh -jar target/application.jar
~~~

Ứng dụng thoát tại lifecycle phase tương tự checkpoint-on-refresh nhưng không cần CRaC-enabled JVM, Linux hoặc CRaC dependency. Đây là cách kiểm tra xem bean nào cố kết nối remote service quá sớm trước khi lifecycle bắt đầu.

Nếu một HTTP client hoặc discovery implementation không thể khởi động ở phase này, hãy xem xét trì hoãn kết nối đến lifecycle phù hợp thay vì thực hiện I/O ngay trong constructor hoặc PostConstruct.

### 12.4. Test matrix AOT

| Test | Kết quả mong đợi |
| --- | --- |
| Build AOT | Sinh mã và metadata thành công |
| JVM chạy với spring.aot.enabled=true | Context khởi động với mã AOT |
| Native image build | Compiler tạo executable thành công |
| Native startup | Không thiếu class/resource/hint |
| Discovery lookup | Service ID trả đúng instance |
| LoadBalancer | Chọn instance trong danh sách hợp lệ |
| HTTP call | Request/response hoạt động qua transport đã chọn |
| Config Client | Remote source truy cập được và cấu hình đúng |
| Refresh scope | Đã tắt trong AOT/native nếu dùng Spring Cloud Context |

## 13. Kiểm thử CRaC checkpoint/restore

### 13.1. Điều kiện môi trường

Spring Framework hiện yêu cầu:
- JVM có hỗ trợ checkpoint/restore.
- Môi trường Linux cho checkpoint thực tế theo tài liệu hiện hành.
- org.crac:crac phiên bản 1.4.0 trở lên.
- JVM flags như -XX:CRaCCheckpointTo=PATH hoặc -XX:CRaCRestoreFrom=PATH.

Ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
    <version>1.5.0</version>
</dependency>
~~~

Dùng version được runtime và Spring Framework version của dự án hỗ trợ. Không tự pin version CRaC mới nhất nếu dependency management của nền tảng đã quy định version khác.

### 13.2. Tạo checkpoint

Khởi động ứng dụng với CRaC-enabled JDK:

~~~bash
java -XX:CRaCCheckpointTo=./crac-image -jar target/application.jar
~~~

Warm up ứng dụng bằng workload đại diện, sau đó tạo checkpoint:

~~~bash
jcmd application.jar JDK.checkpoint
~~~

Khôi phục từ snapshot:

~~~bash
java -XX:CRaCRestoreFrom=./crac-image
~~~

Cú pháp và khả năng của runtime có thể khác nhau giữa vendor. Kiểm tra tài liệu JDK CRaC đang dùng và quyền Linux/CRIU trên môi trường thực tế.

### 13.3. Kiểm tra sau restore

Sau khi restore:
1. Kiểm tra ApplicationContext đã hoạt động.
2. Xác nhận HTTP connection pool đã mở lại.
3. Xác nhận discovery session/heartbeat được tiếp tục hoặc đăng ký lại.
4. Kiểm tra service instance có địa chỉ đúng.
5. Kiểm tra LoadBalancer supplier/cache đã nhận dữ liệu hợp lệ.
6. Gọi request nghiệp vụ qua HTTP client.
7. Kiểm tra database/broker dependency.
8. Xác nhận readiness trước khi nhận traffic.
9. Kiểm tra log không có socket, executor hoặc thread lỗi.
10. Đo thời gian từ restore đến request thành công.

### 13.4. Fixed rate scheduler sau restore

Với @Scheduled(fixedRate = 5000), các lần chạy bị lỡ trong khoảng thời gian JVM checkpoint có thể được thực thi khi restore. Nếu không muốn dồn nhiều lần thực thi ngay sau restore, cân nhắc fixedDelay hoặc cron expression.

Không để heartbeat, polling hoặc cleanup task chạy dồn dập sau restore làm quá tải registry, broker hoặc database.

### 13.5. Bảo vệ snapshot

CRaC snapshot chứa bộ nhớ JVM. Mọi dữ liệu ứng dụng từng đọc có thể nằm trong snapshot, gồm:
- Secret và access token.
- Database credential.
- HTTP Authorization header.
- TLS session hoặc key material.
- Configuration properties.
- Customer data hoặc request payload còn trong heap.

Do đó:
- Lưu snapshot trên storage có kiểm soát quyền.
- Mã hóa snapshot khi lưu/chuyển nếu chính sách yêu cầu.
- Không đưa snapshot chứa secret vào artifact công khai.
- Hạn chế quyền đọc và ghi snapshot.
- Không restore snapshot production vào môi trường có quyền truy cập khác mà không đánh giá credential.
- Có quy trình xóa snapshot khi hết hạn.

## 14. Quy trình xác nhận implementation trước khi chọn production

### 14.1. Discovery implementation

| Câu hỏi | Bằng chứng cần thu thập |
| --- | --- |
| Implementation nào được tạo? | Dependency tree và ApplicationContext bean |
| Có AOT/native support không? | Reference guide của đúng version |
| Có yêu cầu service ID tường minh không? | AOT config và danh sách LoadBalancer client |
| Có kết nối remote trong build time không? | Build log và config source |
| Có heartbeat/watch/session không? | Log và metric của provider |
| Sau restore có reconnect không? | CRaC integration test |
| Instance có được đăng ký lại không? | Registry record và instance ID |
| Cache có bị stale không? | Discovery list trước/sau restore |

### 14.2. HTTP client implementation

| Câu hỏi | Bằng chứng cần thu thập |
| --- | --- |
| Spring chọn request factory/connector nào? | Runtime bean và dependency tree |
| Native image có đủ hints không? | Native build và runtime smoke test |
| Có resource hoặc reflection động không? | RuntimeHints và resource inspection |
| Pool có được đóng không? | Checkpoint log và resource callback |
| Sau restore có client mới không? | Integration test và request thực tế |
| DNS/TLS có được làm mới không? | Kết quả gọi endpoint sau restore |
| Retry/timeout có bị thay đổi không? | Client metrics và request trace |

### 14.3. Chạy test theo tổ hợp

Ví dụ tổ hợp cần kiểm tra:

| Discovery | HTTP client | AOT/native | CRaC |
| --- | --- | --- | --- |
| Eureka Client | RestClient + JDK | Kiểm tra điều kiện Eureka và LoadBalancer | Kiểm tra registration và client recreation |
| Eureka Client | WebClient + Reactor Netty | Kiểm tra service ID và native hints | Kiểm tra event loop và pool |
| SimpleDiscoveryClient | RestTemplate | Kiểm tra property binding và service ID | Kiểm tra request factory |
| Consul Discovery | RestClient + Apache | Chưa có cam kết AOT riêng; test target version | Kiểm tra session, registration và pool |
| Zookeeper Discovery | WebClient + Jetty | Chưa có cam kết AOT riêng; test target version | Kiểm tra session, watcher và client |
| Kubernetes Discovery | RestClient | Tài liệu hiện hành ghi chưa hỗ trợ AOT/native | Kiểm tra API watch và token lifecycle |

Không chạy một test tổ hợp lớn rồi chỉ ghi “native build failed”. Hãy chia nhỏ theo provider để biết lỗi nằm ở discovery, LoadBalancer, HTTP transport, Config Client hay custom runtime hint.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Eureka Client không build native | Refresh mode còn bật hoặc random port | Tắt refresh, dùng port có thể xác định |
| Eureka Server native build thất bại | Implementation chưa hỗ trợ AOT/native | Dùng JVM hoặc kiến trúc registry khác đã được hỗ trợ |
| Kubernetes Discovery native build lỗi | Tài liệu hiện hành chưa hỗ trợ AOT/native | Dùng Kubernetes Service DNS nếu phù hợp hoặc chờ phiên bản hỗ trợ |
| LoadBalancer không tìm thấy client context | Service ID không khai báo tường minh | Dùng LoadBalancerClient hoặc eager-load property |
| Feign client không được tạo trong native | Lazy attribute resolution hoặc refresh client bật | Tắt các option không tương thích AOT |
| Config Client native không resolve được config | Config backend không truy cập được khi build | Cung cấp datasource và property cần thiết ở build time |
| Native image thiếu serializer/resource | Thiếu runtime hints | Đăng ký reflection/resource hints tối thiểu |
| WebClient chọn transport khác CI | Classpath khác nhau | Cố định connector hoặc kiểm tra dependency |
| CRaC checkpoint bị từ chối | Socket/file/thread vẫn mở | Dừng lifecycle bean và giải phóng resource |
| Request fail sau restore | Connection pool hoặc session cũ | Tạo lại client/session và kiểm tra reconnect |
| Eureka registration cũ vẫn tồn tại | Lease/heartbeat và restore timing | Xác minh registration, instance ID và renewal |
| Scheduler chạy dồn sau restore | Dùng fixedRate | Dùng fixedDelay/cron khi phù hợp |
| Snapshot restore lộ credential | Snapshot chứa heap và config | Bảo vệ storage, access và vòng đời snapshot |

## 16. Checklist lựa chọn và kiểm thử

### AOT / Native Image

- [ ] Đã xác định chính xác Spring Boot và Spring Cloud release train.
- [ ] Đã xác định discovery implementation thực tế trong classpath.
- [ ] Đã kiểm tra tài liệu AOT/native của đúng implementation.
- [ ] Đã tắt spring.cloud.refresh.enabled nếu dùng Spring Cloud AOT/native.
- [ ] Eureka Client không dùng random server port.
- [ ] Eureka Server không được giả định là native-compatible.
- [ ] Spring Cloud Kubernetes không được giả định là native-compatible.
- [ ] Đã khai báo service ID cho LoadBalancer.
- [ ] Feign client refresh và lazy attribute resolution đã tắt.
- [ ] Config Client có datasource truy cập được tại build time.
- [ ] Đã xác nhận HTTP transport được Spring Boot lựa chọn.
- [ ] Đã bổ sung RuntimeHints cho custom reflection/resource/proxy.
- [ ] Đã chạy AOT JVM test và native executable smoke test.
- [ ] Đã gọi request qua discovery và LoadBalancer trong native executable.

### CRaC / Checkpoint Restore

- [ ] Runtime JDK có hỗ trợ CRaC và đúng môi trường Linux.
- [ ] Dependency org.crac:crac tương thích Spring Framework.
- [ ] Bean lifecycle dừng và khởi động lại đúng cách.
- [ ] HTTP pool, socket và executor được giải phóng trước checkpoint.
- [ ] Discovery client reconnect hoặc re-register sau restore.
- [ ] Heartbeat, lease, token và watcher được kiểm tra.
- [ ] LoadBalancer cache/supplier không dùng địa chỉ stale.
- [ ] Readiness chỉ chuyển UP sau khi dependency và discovery sẵn sàng.
- [ ] Scheduled task không tạo backlog ngoài ý muốn.
- [ ] Snapshot được bảo vệ như dữ liệu nhạy cảm.
- [ ] Có integration test checkpoint, restore và request thực tế.

## Ghi nhớ

AOT/native và CRaC là hai hướng tối ưu khác nhau. Khi kiểm tra AOT, cần xác nhận discovery implementation có hỗ trợ, service ID của LoadBalancer được khai báo tường minh, HTTP client có đủ runtime hints và các tính năng refresh không tương thích đã được tắt. Khi kiểm tra CRaC, trọng tâm là vòng đời của socket, connection pool, session, heartbeat, watcher và scheduler. Eureka Client có hỗ trợ AOT/native với điều kiện cụ thể; Eureka Server và Spring Cloud Kubernetes hiện không hỗ trợ; Consul/Zookeeper cần kiểm chứng theo version khi tài liệu chưa công bố cam kết. Không kết luận một ứng dụng tương thích chỉ vì nó build thành công: hãy chạy native executable, checkpoint/restore và gọi request qua đúng discovery cùng HTTP transport sẽ dùng trong production.

## Tài liệu tham khảo

- Spring Cloud Netflix – AOT and Native Image Support: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Kubernetes – AOT and Native Image Support: https://docs.spring.io/spring-cloud-kubernetes/docs/current/reference/html/#aot-and-native-image-support
- Spring Cloud Commons – LoadBalancer AOT and Native Image Support: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud OpenFeign – AOT and Native Image Support: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html
- Spring Cloud Context – Application Context Services and Refresh Scope on Restart: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html
- Spring Cloud Config Client – AOT and Native Image Support: https://docs.spring.io/spring-cloud-config/reference/client.html
- Spring Boot – Calling REST Services: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Framework – Ahead-of-Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework – JVM Checkpoint Restore: https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html
- Spring Boot – Checkpoint and Restore With the JVM: https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html
- CRaC – Checkpoint and Restore: https://crac.org/use/checkpoint-and-restore/

