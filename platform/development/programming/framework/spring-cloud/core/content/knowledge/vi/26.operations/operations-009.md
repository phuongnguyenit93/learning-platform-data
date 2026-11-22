# Giới hạn tải do discovery, health check và làm mới cấu hình

> **Chương:** Vận hành  
> **Module:** SPRING_CLOUD_CORE

Trong hệ thống Spring Cloud, service discovery, health check và configuration refresh giúp ứng dụng thích ứng với thay đổi của hệ thống phân tán. Tuy nhiên, chính các cơ chế này cũng tạo thêm lưu lượng tới registry, các instance và những dependency phía sau. Khi số lượng replica tăng, chu kỳ kiểm tra quá ngắn hoặc một thay đổi cấu hình được phát đồng loạt, lượng công việc phụ có thể tăng nhanh và làm hệ thống quá tải đúng lúc đang có sự cố.

Bài học này tập trung vào cách **giới hạn tải phát sinh từ discovery, health check và refresh**. Ta sẽ xem cách giảm truy vấn registry, dùng cache đúng chỗ, thiết kế probe nhẹ, tránh restart dây chuyền, chia nhỏ đợt refresh và theo dõi các tín hiệu vận hành. Các ví dụ thuộc phạm vi Spring Cloud Commons, Spring Cloud LoadBalancer, Spring Cloud Context và Spring Boot Actuator trong module **SPRING_CLOUD_CORE**.

## 1. Nhìn tải vận hành như một phần của tải hệ thống

Một request nghiệp vụ có thể kéo theo nhiều hoạt động phụ:

- Client cần danh sách instance để chọn đích gọi.
- Discovery health indicator truy vấn registry để kiểm tra trạng thái discovery.
- LoadBalancer health-check supplier gọi endpoint của từng instance theo lịch.
- Kubernetes hoặc nền tảng điều phối gọi liveness/readiness probe.
- Một thay đổi cấu hình phát sinh rebind hoặc khởi tạo lại bean.
- Spring Cloud Bus phân phối refresh event tới nhiều replica.

Nếu mỗi hoạt động chỉ chạy ở một instance thì chi phí có thể nhỏ. Nhưng khi nhân lên theo số replica, số service, số instance đích và tần suất, các hoạt động nền có thể tạo thành tải đáng kể.

### 1.1. Ba nguồn tải chính

| Nguồn | Công việc phát sinh | Hệ quả khi tần suất hoặc phạm vi quá lớn |
| --- | --- | --- |
| Discovery | Truy vấn danh sách service/instance, cập nhật registry, làm mới cache | Registry tốn CPU/network, client nhận danh sách lớn hoặc dữ liệu stale |
| Health check | Probe từ nền tảng, health indicator, LoadBalancer kiểm tra từng instance | Request nền tăng, dependency bị gọi lặp, nhiều instance đồng thời bị đánh dấu lỗi |
| Configuration refresh | Rebind ConfigurationProperties, xóa cache RefreshScope, tạo lại client/pool, phát Bus event | Tải khởi tạo dồn cục, tăng kết nối tới database/API, broker có backlog |

### 1.2. Sơ đồ quan hệ

~~~mermaid
flowchart TB
    A["Nhiều application replicas"]
    A --> B["DiscoveryClient / LoadBalancer"]
    A --> C["Health indicators và probes"]
    A --> D["Configuration refresh"]
    B --> E["Service registry"]
    C --> E
    C --> F["Các service instances"]
    D --> G["Config source / Spring Cloud Bus"]
    D --> H["Khởi tạo lại bean và connection pool"]
    E --> I["Tải điều khiển-plane"]
    F --> J["Tải request nền"]
    G --> K["Tải sự kiện và broker"]
    H --> L["Tải khởi tạo dependency"]
~~~

Điều quan trọng là không coi mọi request tới endpoint health hoặc registry là miễn phí. Chúng cũng tiêu thụ thread, connection, CPU và network như request nghiệp vụ.

## 2. Định lượng tải trước khi thay đổi cấu hình

Một số phép tính đơn giản giúp nhận diện cấu hình có thể tạo ra burst.

### 2.1. Tần suất health probe

Nếu có `N` replica và mỗi replica được gọi probe mỗi `T` giây, tần suất probe xấp xỉ:

`Q_probe ≈ N / T`

Ví dụ 60 replica được probe mỗi 10 giây tạo khoảng 6 request/giây tới endpoint probe. Đây mới là lưu lượng tới endpoint ứng dụng; nếu endpoint lại gọi thêm discovery, database và nhiều API khác, tải downstream sẽ tăng theo.

### 2.2. Health-check từng service instance

Với một nhóm client độc lập, nếu mỗi client kiểm tra `M` instance mỗi `T` giây, ước lượng số lần gọi:

`Q_instance-check ≈ N_clients × M / T`

Ví dụ 20 client kiểm tra 10 instance mỗi 30 giây tạo khoảng 6,7 lần kiểm tra/giây. Đây là ước lượng để lập kế hoạch; số lần thực tế còn phụ thuộc supplier, cache, số service ID và cách triển khai scheduler.

### 2.3. Tải do refresh đồng loạt

Nếu `R` replica cùng refresh và mỗi replica phải khởi tạo lại `B` bean có chi phí đáng kể, số lần khởi tạo trong một đợt có thể lên tới:

`W_refresh ≈ R × B`

Nếu các bean tạo HTTP connection pool, database pool, TLS context hoặc subscription tới broker, đợt refresh có thể tạo ra một burst kết nối. Chia refresh thành từng nhóm nhỏ làm giảm số lần khởi tạo đồng thời.

Các công thức trên không thay thế benchmark. Hãy dùng chúng để tìm quy mô ban đầu, sau đó đo lưu lượng thật trong môi trường gần production.

## 3. Giới hạn truy vấn discovery

Spring Cloud Commons cung cấp abstraction `DiscoveryClient` để lấy danh sách service và instance. Chi phí thực tế phụ thuộc provider, cách provider cache dữ liệu, số service được đăng ký và số client gọi discovery.

### 3.1. Tránh gọi getServices quá thường xuyên

`DiscoveryClientHealthIndicator` mặc định có thể gọi `DiscoveryClient.getServices()` để kiểm tra discovery. Trong hệ thống có nhiều service, thao tác này có thể phải lấy và tổng hợp một danh sách lớn ở mỗi lần health check.

Có thể chuyển sang probe nhẹ hơn:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          use-services-query: false
~~~

Khi `use-services-query` là `false`, health indicator sử dụng `DiscoveryClient.probe()` thay cho truy vấn toàn bộ danh sách service. Cách này hữu ích khi chỉ cần xác nhận discovery client có khả năng hoạt động, không cần tải danh sách tất cả service ở mỗi lần probe.

Nếu health indicator không mang lại tín hiệu vận hành cần thiết, có thể tắt nó:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: false
~~~

Chỉ tắt sau khi xác định có tín hiệu khác đủ để phát hiện lỗi registry. Không nên bỏ health indicator chỉ để làm dashboard xanh hơn.

### 3.2. Tránh kiểm tra discovery trùng lặp

Spring Cloud Commons có thể tổng hợp nhiều `DiscoveryHealthIndicator` qua `DiscoveryCompositeHealthContributor`. Provider cũng có thể cung cấp health indicator riêng. Nếu nhiều indicator cùng kiểm tra một registry hoặc cùng gọi một API, một lần tổng hợp health có thể gây nhiều request lặp.

Hãy rà soát:

- DiscoveryClientHealthIndicator.
- DiscoveryCompositeHealthContributor.
- Health indicator do Eureka, Consul hoặc provider khác cung cấp.
- Custom health indicator của ứng dụng.
- Health check của LoadBalancer và probe của nền tảng.

Chỉ giữ các kiểm tra trả lời câu hỏi vận hành riêng biệt. Nếu cần tắt composite indicator:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        composite-indicator:
          enabled: false
~~~

Đây là lựa chọn theo thiết kế health của ứng dụng; không phải cấu hình mặc định bắt buộc cho mọi hệ thống.

### 3.3. Cache danh sách instance của LoadBalancer

Spring Cloud LoadBalancer có cache danh sách instance. Nếu không có Caffeine trên classpath, starter dùng cache mặc định; nếu có Caffeine, implementation Caffeine được sử dụng.

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

Trong cấu hình Spring Cloud hiện hành, TTL mặc định của cache LoadBalancer là 35 giây và capacity ban đầu là 256. Giá trị phù hợp phụ thuộc tốc độ thay đổi instance, số service ID và yêu cầu về độ mới của danh sách.

Cache giúp giảm truy vấn discovery lặp lại, nhưng đổi lại client có thể tiếp tục nhìn thấy danh sách instance cũ cho tới khi cache hết hạn hoặc được làm mới. Cần cân bằng:

- TTL dài hơn: ít truy vấn registry hơn nhưng thay đổi instance được nhìn thấy chậm hơn.
- TTL ngắn hơn: cập nhật nhanh hơn nhưng tăng tần suất lấy danh sách.
- Capacity thấp quá: cache có thể liên tục eviction khi ứng dụng gọi nhiều service ID.
- Capacity quá lớn: tăng bộ nhớ mà không tạo thêm lợi ích nếu số service ID thực tế nhỏ.

Nếu discovery provider như Eureka đã cache danh sách instance, cân nhắc tắt cache của LoadBalancer để tránh double caching:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Không bật hai lớp cache một cách máy móc. Hãy xác định lớp nào đang chịu trách nhiệm freshness, TTL và invalidation.

### 3.4. Đừng làm cache và health-check supplier chồng lấn

`HealthCheckServiceInstanceListSupplier` có cơ chế cache riêng dựa trên Reactor Flux replay. Nếu dùng supplier này, không nên tự động bọc thêm `CachingServiceInstanceListSupplier` bên ngoài mà chưa hiểu thứ tự và cache behavior.

Với cấu hình custom, thứ tự supplier cũng quan trọng: supplier lấy instance qua mạng nên đứng trước cache/health-check supplier, và các supplier lọc request nên đứng sau lớp lấy/cập nhật instance phù hợp.

Đoạn cấu hình custom cần được kiểm tra theo phiên bản Spring Cloud đang dùng. Không ghép nhiều supplier chỉ vì mỗi supplier đều có một tính năng hữu ích.

## 4. Dùng LoadBalancer health check đúng trường hợp

Spring Cloud LoadBalancer cung cấp `HealthCheckServiceInstanceListSupplier` để kiểm tra định kỳ các instance do supplier delegate trả về. Supplier này lọc và trả về các instance khỏe; nếu không có instance nào khỏe, nó có thể trả lại danh sách đã lấy được để tránh biến danh sách thành rỗng hoàn toàn.

Điều đó có nghĩa health-check supplier không phải cơ chế fail-closed tuyệt đối: khi toàn bộ instance đều fail check, danh sách gốc vẫn có thể được trả về. Hãy kết hợp với timeout, retry/circuit breaker và trạng thái registry phù hợp; đừng dựa riêng supplier này để bảo đảm request không bao giờ tới instance lỗi.

### 4.1. Khi nào nên dùng?

Health-check supplier đặc biệt hữu ích khi dùng `SimpleDiscoveryClient` với danh sách instance cấu hình tĩnh, hoặc khi provider không cung cấp trạng thái sức khỏe đủ tin cậy.

Với registry thật như Eureka/Consul, service discovery thường đã trả về trạng thái instance theo cơ chế riêng. Trong trường hợp này, thêm một lịch health check từ mọi client có thể tạo lưu lượng trùng lặp mà không tăng nhiều chất lượng lựa chọn.

Trước khi bật, hãy trả lời:

1. Registry có trả trạng thái health của instance không?
2. Trạng thái đó có đủ mới cho yêu cầu định tuyến không?
3. Instance có endpoint health nhẹ và ổn định không?
4. Số client và số instance đích là bao nhiêu?
5. Mỗi client có cần tự kiểm tra cùng một instance hay có thể tin registry?

### 4.2. Điều chỉnh chu kỳ và path

Nếu thực sự cần scheduled health check, cấu hình interval và endpoint phù hợp:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: health-check
      health-check:
        initial-delay: 10s
        interval: 45s
        path:
          default: /actuator/health
~~~

`initial-delay` tránh tạo tất cả probe ngay khi ứng dụng vừa khởi động. `interval` quyết định thời gian giữa các chu kỳ. Đường dẫn mặc định là `/actuator/health` nếu không cấu hình khác; có thể cấu hình path theo service ID khi các service có health endpoint riêng.

Health endpoint được gọi bởi LoadBalancer phải:

- Trả lời nhanh và có timeout hợp lý.
- Không thực hiện truy vấn toàn bộ service registry.
- Không gọi chuỗi dài các downstream chỉ để báo trạng thái instance.
- Không tạo transaction hoặc side effect.
- Có semantics rõ ràng: liveness, readiness hay một kiểm tra phục vụ định tuyến.

Không dùng một endpoint health nặng làm probe cho từng instance từ nhiều client.

### 4.3. Refetch instance list và lặp health check

Trong một số trường hợp delegate không phát danh sách instance mới dù registry đã thay đổi, có thể yêu cầu health-check supplier refetch:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 45s
        repeat-health-check: false
~~~

`refetch-instances` mặc định là false. Khi bật refetch, mỗi lần lấy danh sách instance mới cũng có thể kích hoạt health check. Vì vậy, `repeat-health-check: false` có thể tránh lặp thêm một chu kỳ kiểm tra không cần thiết nếu refetch đã kích hoạt health check.

Không bật refetch chỉ để ép registry cập nhật nhanh hơn khi delegate đã tự phát danh sách thay đổi. Trước tiên hãy đo freshness của delegate và xác định nơi đang giữ cache.

### 4.4. Không dùng đồng thời hai lớp supplier cache không cần thiết

Nếu đã dùng `HealthCheckServiceInstanceListSupplier`, nó có cache riêng. Nếu dùng `CachingServiceInstanceListSupplier` cùng lúc, có thể làm tăng độ trễ cập nhật hoặc khiến việc chẩn đoán freshness khó hơn.

Spring Cloud khuyến nghị đặt health-check supplier trực tiếp sau supplier lấy instance qua mạng và trước các supplier lọc khác. Khi tự viết cấu hình, cần giữ đúng thứ tự này và chỉ chọn một cơ chế cache/health-check phù hợp.

## 5. Thiết kế health check không tạo cascading failure

Health check là tín hiệu cho nền tảng điều phối và các client biết ứng dụng có thể phục vụ hay không. Nếu một health check quá nhạy hoặc phụ thuộc quá nhiều hệ thống ngoài, một sự cố cục bộ có thể biến thành restart storm.

### 5.1. Phân biệt liveness và readiness

- **Liveness** trả lời tiến trình còn sống và có thể tiếp tục chạy hay không.
- **Readiness** trả lời instance có nên nhận traffic mới ở thời điểm hiện tại hay không.
- **Startup probe** giúp nền tảng cho ứng dụng đủ thời gian khởi động trước khi áp dụng liveness.

Không đưa health check database, discovery server hoặc API bên ngoài vào liveness. Nếu dependency ngoài tạm thời lỗi, Kubernetes có thể restart tất cả pod; việc khởi động lại đồng loạt làm tăng tải lên chính dependency đang gặp sự cố.

Readiness có thể xét một số dependency ngoài nếu nghiệp vụ thực sự không thể phục vụ khi dependency đó lỗi. Nhưng hãy lựa chọn cẩn thận: nếu mọi replica cùng chuyển NOT_READY khi một dependency chung gặp sự cố, toàn bộ service có thể ngừng nhận traffic và không còn khả năng phục hồi.

### 5.2. Không đưa mọi health indicator vào readiness

Spring Boot mặc định tạo các health group liveness và readiness trong môi trường Kubernetes. Các health indicator khác không tự động được thêm vào readiness group.

Nếu muốn bổ sung một indicator, cấu hình rõ ràng:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - catalogDependency
~~~

Chỉ thêm `catalogDependency` nếu đây là điều kiện thật sự cần để nhận request mới. Không đưa tất cả indicator vào readiness theo kiểu wildcard.

### 5.3. Điều chỉnh probe interval và threshold

Ví dụ cấu hình Kubernetes:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Các giá trị trên chỉ là ví dụ. Cần căn cứ vào startup time, thời gian xử lý health contributor, timeout của ứng dụng và hành vi phục hồi. Nếu probe quá dày, số request nền tăng; nếu threshold quá thấp, một spike ngắn có thể làm pod bị loại hoặc restart không cần thiết.

Với ứng dụng khởi động lâu, cân nhắc startup probe để không áp dụng liveness quá sớm. Đảm bảo probe đi qua cùng server port nếu cần xác nhận web server chính có thể nhận request; một management port riêng có thể khỏe trong khi cổng phục vụ chính gặp lỗi.

## 6. Làm mới cấu hình mà không tạo refresh storm

Spring Cloud Context hỗ trợ thay đổi Environment, rebind `@ConfigurationProperties` và refresh bean trong `@RefreshScope`. Các thao tác này hữu ích, nhưng nếu mọi replica cùng làm mới trong một thời điểm, chúng có thể đồng thời khởi tạo lại HTTP client, connection pool, cache hoặc subscription.

### 6.1. Hiểu chi phí của từng kiểu refresh

Khi có `EnvironmentChangeEvent`, Spring Cloud có thể:

- Rebind các bean `@ConfigurationProperties`.
- Cập nhật logger level nếu các property tương ứng thay đổi.
- Refresh các bean nằm trong `RefreshScope` khi thực hiện context refresh phù hợp.

Rebind `@ConfigurationProperties` thường cập nhật các field trên bean hiện tại. Quá trình này có thể làm một thread đọc đồng thời thấy trạng thái tạm thời giữa lúc reset và áp dụng giá trị mới.

`@RefreshScope` dùng lazy proxy và cache target bean. Khi refresh, cache bị xóa; lần gọi tiếp theo sẽ tạo lại target bean. Cách này phù hợp với bean cần một trạng thái nhất quán hơn qua refresh, nhưng việc khởi tạo lại target vẫn có chi phí.

### 6.2. Chỉ đưa bean cần thiết vào RefreshScope

Không gắn `@RefreshScope` lên mọi bean trong ứng dụng. Chỉ chọn các bean thực sự cần được tái tạo khi cấu hình đổi, chẳng hạn client dùng endpoint hoặc credential có thể thay đổi.

Ví dụ:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogRemoteClient {

    private final CatalogClientProperties properties;

    public CatalogRemoteClient(CatalogClientProperties properties) {
        this.properties = properties;
    }

    public String currentBaseUrl() {
        return properties.getBaseUrl();
    }
}
~~~

Đây là ví dụ minh họa vòng đời bean; trong ứng dụng thực tế, client có thể giữ connection pool hoặc transport cần đóng đúng cách khi target cũ bị thay thế.

Lưu ý:

- `@RefreshScope` trên một class `@Configuration` không tự động đưa tất cả bean được khai báo trong class đó vào refresh scope.
- Các bean dùng constructor binding, bao gồm Java Record `@ConfigurationProperties`, không thể refresh theo cơ chế này.
- `HikariDataSource` nằm trong nhóm mặc định không refreshable của Spring Cloud; không giả định connection pool này có thể tái tạo an toàn qua refresh.
- Nếu bean cần consistency giữa các lần đọc và refresh, cân nhắc refresh scope thay cho rebind mutable fields trực tiếp.
- Context refresh không được hỗ trợ cho Spring AOT transformations và native images; cần kiểm tra property hỗ trợ của phiên bản.

### 6.3. Không refresh chỉ vì có một lần polling

Spring Cloud Config Client không tự polling Environment theo mặc định. Tài liệu Spring Cloud không khuyến nghị triển khai polling dày để phát hiện thay đổi trong ứng dụng scale-out. Khi cần cập nhật nhiều instance, có thể dùng Spring Cloud Bus để broadcast sự kiện thay đổi thay vì để từng replica liên tục hỏi Config Server.

Polling mỗi vài giây từ hàng trăm replica vừa tăng tải Config Server vừa có thể tạo refresh đồng thời nếu nhiều client cùng phát hiện một thay đổi.

Nếu cần polling do yêu cầu riêng, hãy thiết kế jitter, backoff, cache, giới hạn concurrency và chỉ phát refresh khi fingerprint cấu hình thực sự thay đổi. Không phát refresh lặp lại khi giá trị không đổi.

Ở pipeline triển khai, nên gom nhiều thay đổi property thành một lần refresh sau khi bản cấu hình đã hoàn chỉnh. Dùng khóa hoặc hàng đợi để mỗi service/environment chỉ có một đợt refresh đang chạy; đặt cooldown giữa các đợt và bỏ qua event trùng fingerprint. Cách này ngăn một loạt commit hoặc thao tác vận hành liên tiếp tạo nhiều lần khởi tạo bean gần nhau.

## 7. Chia nhỏ refresh bằng Spring Cloud Bus

Spring Cloud Bus phân phối refresh event qua broker tới các application instance. Endpoint `/actuator/busrefresh` xóa cache `RefreshScope` và rebind `@ConfigurationProperties` ở các instance nhận sự kiện.

### 7.1. Broadcast có thể tạo burst

Nếu phát một refresh event tới toàn bộ service đang chạy, mọi instance nhận sự kiện có thể bắt đầu rebind hoặc khởi tạo lại bean gần như cùng lúc. Khi mỗi instance mở lại pool hoặc kết nối tới cùng dependency, tải có thể tăng đột ngột.

Một đợt refresh lớn cần tính đến:

- Số replica của service.
- Số bean trong refresh scope.
- Số connection pool hoặc HTTP client phải tái tạo.
- Giới hạn kết nối của database/API/broker.
- Thời gian khởi tạo và readiness của mỗi replica.
- Khả năng xử lý message và backlog của Bus broker.

### 7.2. Target một instance hoặc một nhóm instance

Spring Cloud Bus cho phép target destination trong path. Ví dụ target một instance:

~~~bash
curl -X POST   http://localhost:8080/actuator/busrefresh/catalog-service:8081
~~~

Hoặc target mọi instance của một service:

~~~bash
curl -X POST   http://localhost:8080/actuator/busrefresh/catalog-service:**
~~~

Destination được so khớp với service ID của Bus. Hãy bảo đảm ID của từng instance là duy nhất; ID mặc định được tạo từ application name và thông tin instance/port phù hợp. Có thể cấu hình `spring.cloud.bus.id` khi cần kiểm soát định danh.

Target một instance cho phép canary refresh trước. Sau khi kiểm tra thành công, tiếp tục theo từng nhóm nhỏ rồi mới refresh phần còn lại. Nếu không cần thay đổi cùng thời điểm, tránh broadcast tất cả replica một lần.

### 7.3. Quy trình refresh theo batch

Một quy trình an toàn có thể là:

1. Xác định thay đổi property và danh sách service/instance chịu ảnh hưởng.
2. Xác nhận các bean nào sẽ được rebind hoặc refresh.
3. Target một instance canary.
4. Kiểm tra `/actuator/health`, `/actuator/configprops` và metric của dependency.
5. Chờ instance ổn định và các pool đạt trạng thái bình thường.
6. Refresh batch nhỏ tiếp theo.
7. Theo dõi broker lag, lỗi khởi tạo và connection count.
8. Dừng batch nếu error rate hoặc tải dependency tăng vượt ngưỡng.
9. Tiếp tục cho tới khi toàn bộ nhóm đã nhận cấu hình mới.
10. Xác nhận version/fingerprint cấu hình trên toàn bộ replica.

Nếu hệ thống có 100 replica, có thể bắt đầu bằng một canary, sau đó 5-10 replica mỗi batch và điều chỉnh theo năng lực dependency. Đây là ví dụ chiến lược, không phải giá trị mặc định của Spring Cloud.

### 7.4. Refresh không thay thế rollout

Một số thay đổi không phù hợp với refresh runtime: thay đổi cấu trúc bean, thay đổi thư viện, thay đổi kiểu cấu hình không thể rebind hoặc thay đổi connection/resource cần khởi tạo lại toàn bộ context.

Khi thay đổi ảnh hưởng lớn tới lifecycle hoặc tương thích, dùng rolling deployment có giới hạn surge/unavailable phù hợp. Không cố refresh một cấu hình mà ứng dụng không hỗ trợ tái tạo an toàn.

## 8. Bộ cấu hình vận hành tham khảo

Ví dụ sau minh họa cấu hình giảm truy vấn discovery và giữ cache LoadBalancer:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          use-services-query: false
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - refresh
          - busrefresh
          - configprops
~~~

`refresh` và `busrefresh` có thể thay đổi trạng thái runtime và kích hoạt khởi tạo lại bean. Chỉ expose chúng trên management network, yêu cầu xác thực/phân quyền cho người vận hành, ghi audit cho mỗi thao tác và không mở các endpoint này công khai.

Nếu ứng dụng dùng registry thực sự đã trả trạng thái instance, không bật thêm scheduled health-check supplier nếu chưa có lý do. Nếu dùng `SimpleDiscoveryClient` và cần kiểm tra từng instance, cấu hình health-check riêng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: health-check
      health-check:
        initial-delay: 10s
        interval: 45s
        path:
          default: /actuator/health
~~~

Đây là hai cách triển khai theo nhu cầu. Không nhất thiết phải bật cả hai. Hãy kiểm tra cache và health supplier của provider trước khi thêm lịch probe.

## 9. Quan sát để biết đã giới hạn tải hiệu quả chưa

Không thể đánh giá chỉ bằng việc endpoint trả trạng thái UP. Cần theo dõi tải control-plane và tác động của nó lên dependency.

### 9.1. Discovery và LoadBalancer

Theo dõi:

- Số lần gọi DiscoveryClient, latency và error rate.
- Số service/instance được trả về mỗi lần truy vấn.
- Tỷ lệ cache hit/miss nếu implementation cung cấp metric.
- Thời gian từ lúc instance đăng ký/hủy đăng ký tới lúc client nhìn thấy thay đổi.
- Số request LoadBalancer không chọn được instance.

Spring Cloud LoadBalancer có thể bật Micrometer statistics:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

Khi có MeterRegistry phù hợp, LoadBalancer có thể ghi các meter `loadbalancer.requests.active`, `loadbalancer.requests.success`, `loadbalancer.requests.failed` và `loadbalancer.requests.discard`. Các meter này giúp xác định lỗi chọn instance, request thất bại và tải theo service instance. Kiểm tra tên metric/tag theo phiên bản và backend quan sát đang dùng.

### 9.2. Health check

Theo dõi:

- Request rate tới liveness/readiness endpoint.
- Thời gian xử lý health endpoint.
- Số lần health contributor gọi registry hoặc downstream.
- Timeout, lỗi probe và số pod bị restart.
- Số instance bị loại khỏi danh sách LoadBalancer.
- Sự khác biệt giữa health của ứng dụng và health của dependency ngoài.

Nếu health endpoint tăng latency khi database chậm, hãy xem indicator có đang thực hiện query đồng bộ hoặc chờ timeout quá dài hay không.

### 9.3. Configuration refresh

Theo dõi:

- Số refresh event theo service và instance.
- Thời gian xử lý refresh/rebind.
- Số bean bị tạo lại và lỗi khởi tạo.
- Số kết nối database/HTTP trước, trong và sau refresh.
- Broker queue depth/consumer lag nếu dùng Bus.
- Thời gian từ lúc phát event tới lúc toàn bộ instance hội tụ cấu hình.
- RefreshScopeHealthIndicator nếu được bật.

Không tạo metric tag chứa raw property value, token, user ID hoặc một ID ngẫu nhiên có cardinality cao. Dùng service name, environment, result và một số nhãn có giới hạn.

## 10. Kiểm thử khả năng chịu tải của các cơ chế nền

Nên kiểm tra riêng ba nhóm tải thay vì chỉ chạy một bài benchmark request nghiệp vụ.

### 10.1. Discovery load test

Tạo kịch bản với số replica và số service ID gần production. Đo:

- Số request registry trên mỗi giây.
- Latency getServices/getInstances.
- CPU và memory của registry.
- Sự khác nhau khi cache bật/tắt.
- Thời gian nhìn thấy instance mới hoặc instance bị gỡ.

Thử cả lúc scale-out và scale-in để biết TTL cache có làm chậm việc cập nhật danh sách instance quá mức chấp nhận được không.

### 10.2. Health-check load test

Tăng dần số client và số instance. Xác nhận health-check interval tạo lưu lượng như dự tính, endpoint health có thời gian đáp ứng ổn định và các health indicator không truy vấn lặp cùng một dependency.

Mô phỏng dependency chậm hoặc lỗi để kiểm tra probe có tạo retry/restart storm hay không. Đừng chỉ test trong trạng thái mọi dependency đều khỏe.

### 10.3. Refresh burst test

Dùng một nhóm replica thử refresh đồng thời, quan sát:

- Số kết nối mới tới database hoặc API.
- Thời gian khởi tạo bean và pool.
- Số lỗi trong quá trình refresh.
- Readiness có bị hạ trong khi target bean tái tạo không.
- Broker có backlog khi phát nhiều refresh event không.

Sau đó so sánh broadcast toàn bộ với refresh theo batch. Chọn batch size dựa trên tải thực tế và khả năng phục hồi, không chọn chỉ theo số replica.

## 11. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Registry CPU tăng khi probe | Discovery health indicator gọi getServices quá thường xuyên | Dùng probe nhẹ hơn bằng use-services-query=false; kiểm tra tần suất probe |
| Client thường xuyên gọi registry | LoadBalancer cache tắt hoặc TTL quá thấp | Đo freshness, điều chỉnh TTL và kiểm tra provider cache |
| Instance mới xuất hiện chậm | Cache nhiều lớp hoặc TTL quá dài | Xác định lớp cache, giảm một lớp hoặc TTL theo yêu cầu |
| Health check tạo nhiều request | Nhiều client cùng kiểm tra toàn bộ instance | Chỉ bật health-check supplier khi cần; tăng interval hoặc dùng trạng thái từ registry |
| Tất cả pod restart khi database lỗi | Liveness phụ thuộc health database | Tách liveness khỏi external dependency; dùng readiness có chọn lọc |
| Readiness chuyển DOWN hàng loạt | Indicator chung bị lỗi hoặc timeout | Kiểm tra dependency chung, ngưỡng và chính sách readiness |
| Database connection tăng đột biến sau refresh | Nhiều replica tạo lại client/pool cùng lúc | Refresh theo batch, giảm số bean refresh và giới hạn pool |
| Bus broker backlog tăng | Refresh broadcast quá dày hoặc consumer xử lý chậm | Giảm tần suất, target theo destination và kiểm tra consumer |
| Refresh thành công nhưng giá trị chưa đổi | Bean không thuộc RefreshScope hoặc property không được rebind | Kiểm tra configprops, lifecycle và cách bean đọc cấu hình |
| Bean lỗi sau refresh | Giá trị mới không hợp lệ hoặc khởi tạo phụ thuộc ngoài thất bại | Validate trước rollout, canary và có kế hoạch rollback |
| Health endpoint chậm | Indicator gọi nhiều dependency tuần tự | Giảm số indicator, đặt timeout và tách check sâu khỏi probe thường xuyên |

## 12. Quy trình vận hành tổng thể

Khi chuẩn bị scale một service hoặc thay đổi cấu hình trên diện rộng:

1. Đo baseline request rate tới registry, health endpoint, broker và các dependency.
2. Ước lượng số lần discovery/health check/refresh theo số replica và interval.
3. Xác định provider đã cache danh sách instance hay chưa.
4. Chọn một lớp cache rõ ràng và đặt TTL theo yêu cầu freshness.
5. Giảm DiscoveryClientHealthIndicator dùng-services-query nếu không cần tải danh sách service.
6. Chỉ bật LoadBalancer health-check supplier khi registry không cung cấp health state phù hợp.
7. Tách liveness khỏi dependency ngoài và chọn readiness indicator có chủ đích.
8. Xác định bean nào cần refresh, bean nào nên giữ ổn định hoặc cần rolling restart.
9. Chọn canary và batch size cho refresh, không phát đồng loạt nếu dependency có giới hạn kết nối.
10. Theo dõi metrics, log, broker lag và health state sau từng batch.
11. Dừng rollout khi error rate, latency hoặc connection count vượt ngưỡng.
12. Xác nhận tất cả replica đã hội tụ cấu hình và instance list đã cập nhật.

**Điểm cần ghi nhớ:** Discovery cần cache có chủ đích; health check phải nhẹ và tránh kiểm tra trùng lặp; refresh cần giới hạn phạm vi và chia nhỏ theo batch. Hãy dựa vào trạng thái mà registry đã cung cấp trước khi thêm health-check riêng, giữ liveness độc lập với dependency ngoài và dùng Spring Cloud Bus destination để điều khiển refresh theo nhóm. Đo tải nền cùng tải nghiệp vụ để vận hành ổn định khi hệ thống **SPRING_CLOUD_CORE** mở rộng.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions and Discovery Health Indicators](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud LoadBalancer — Caching and Instance Health Checks](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Context — Environment Changes and Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Bus — Refresh Endpoint](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
- [Spring Cloud Bus — Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html)
- [Spring Boot Actuator — Health Groups and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
