# Giới hạn sử dụng Zookeeper cho khám phá và phạm vi quản lý dependency

Apache ZooKeeper được thiết kế như một dịch vụ điều phối phân tán. Nó cung cấp cây dữ liệu znode, session, ephemeral node, watch và cơ chế đồng thuận để các tiến trình phối hợp với nhau. Spring Cloud Zookeeper dùng Apache Curator để xây dựng service registration, discovery và client-side load balancing trên các primitive đó.

Cách tích hợp này hữu ích khi hệ thống đã vận hành ZooKeeper cho coordination hoặc cần chia sẻ một nền tảng discovery đơn giản. Tuy nhiên, ZooKeeper không phải một service registry chuyên dụng có sẵn mọi hành vi health check, routing và quản lý phụ thuộc nghiệp vụ. Đội phát triển cần hiểu giới hạn của session, watch, quorum, dữ liệu và cách Spring Cloud mở rộng các primitive đó.

Bài này tập trung vào hai phạm vi: giới hạn của ZooKeeper khi dùng làm nền tảng service discovery và phạm vi của tính năng **Spring Cloud Zookeeper Dependencies**. Cần phân biệt tính năng runtime này với dependency của Maven hoặc Gradle: nó khai báo những service mà ứng dụng muốn gọi, không quản lý thư viện JAR hay cài đặt vòng đời của service từ xa.

## 1. ZooKeeper được thiết kế để làm gì?

ZooKeeper là một dịch vụ điều phối cho các ứng dụng phân tán. Nó cung cấp một namespace dạng cây, trong đó mỗi znode có thể chứa dữ liệu nhỏ và các znode con. Ứng dụng dùng các primitive như create, delete, exists, get data, set data và get children để xây dựng các chức năng cấp cao hơn.

Những đặc tính chính:

- Dữ liệu được tổ chức theo path, ví dụ `/services/inventory-service/instance-a`.
- Mỗi znode có thể chứa một payload nhỏ cùng version và metadata.
- Client kết nối đến một server trong ensemble, gửi request, heartbeat và nhận watch event.
- Ensemble được nhân bản; phần lớn server phải còn hoạt động để dịch vụ ZooKeeper duy trì khả năng phục vụ.
- ZooKeeper phù hợp với workload thiên về đọc và dữ liệu điều phối nhỏ hơn là lưu trữ dữ liệu nghiệp vụ lớn.

Spring Cloud Zookeeper không biến ZooKeeper thành một database service discovery hoàn chỉnh. Nó dùng Curator Service Discovery Extension để lưu thông tin instance và cung cấp API tương thích với Spring Cloud.

~~~mermaid
flowchart TD
    APP["Spring Boot service"] --> SCZ["Spring Cloud Zookeeper"]
    SCZ --> CUR["Apache Curator"]
    CUR --> ZK[("ZooKeeper ensemble")]
    ZK --> ZNODE["Znode registration tree"]
    CON["Consumer"] --> DC["DiscoveryClient"]
    DC --> SCZ
    DC --> LB["Spring Cloud LoadBalancer"]
    LB --> HTTP["HTTP client"]
    HTTP --> PROVIDER["Provider instance"]
~~~

## 2. Service discovery được xây dựng trên znode và session

Khi đăng ký một service, Spring Cloud Zookeeper công bố metadata như service name, instance ID, host, port và các thuộc tính bổ sung. Root path mặc định của discovery là `/services`; tên service và instance được biểu diễn trong cây znode theo quy tắc của Curator/Spring Cloud Zookeeper.

Ví dụ minh họa:

~~~text
/services
  /inventory-service
    /inventory-a
      { host: "10.0.1.11", port: 8081, ... }
    /inventory-b
      { host: "10.0.1.12", port: 8081, ... }
  /order-service
    /order-a
      { host: "10.0.2.21", port: 8082, ... }
~~~

Đây là sơ đồ khái niệm để hình dung service và instance. Cấu trúc payload và cách đặt tên znode thực tế do Curator recipe và cấu hình Spring Cloud Zookeeper quyết định.

Thông tin discovery có thể được đọc qua `DiscoveryClient`:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");
~~~

Spring Cloud Zookeeper cũng tích hợp Spring Cloud LoadBalancer. Khi dùng starter discovery, `ZookeeperServiceInstanceListSupplier` được cấu hình để cung cấp danh sách instance cho load balancer. Consumer có thể gọi theo logical service name thay vì lưu IP và port cố định.

### 2.1. Starter không phải ZooKeeper server

Dependency `spring-cloud-starter-zookeeper-discovery` thêm các thư viện phía ứng dụng và kích hoạt auto-configuration. Nó không cài đặt hoặc khởi chạy ZooKeeper ensemble cho hệ thống.

Cần triển khai ZooKeeper server riêng, cấu hình kết nối và bảo đảm các ứng dụng truy cập được ensemble. Nếu ZooKeeper nằm ngoài `localhost:2181`, có thể cấu hình:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
~~~

Danh sách host phải khớp với topology ensemble. Mỗi môi trường nên quản lý connect string, authentication và ACL qua cấu hình triển khai an toàn.

## 3. Giới hạn thứ nhất: registration gắn với session

Một điểm quan trọng của mô hình Curator Service Discovery là registration thường sử dụng **ephemeral znode**. Ephemeral node tồn tại khi session tạo ra nó còn hiệu lực; khi session hết hạn, ZooKeeper xóa các ephemeral node thuộc session đó.

Điều này giúp dọn registration khi tiến trình thực sự mất session mà không cần một tác vụ cleanup riêng. Nhưng nó cũng tạo ra một số hành vi cần hiểu rõ:

- Mất TCP connection trong thời gian ngắn không đồng nghĩa session đã hết hạn.
- Nếu client kết nối lại trước session timeout, session có thể tiếp tục và ephemeral registration vẫn tồn tại.
- Nếu session hết hạn, registration bị xóa ở phía ZooKeeper.
- Khi client nhận thông báo session expired, session cũ không thể tiếp tục dùng các ephemeral node đã bị xóa. Curator hoặc integration phải khôi phục session và đăng ký lại instance; ứng dụng cần xác minh quá trình phục hồi này.
- Trong khoảng thời gian giữa session expiry và đăng ký lại, consumer có thể không thấy instance.

Ví dụ một container bị network partition:

~~~mermaid
sequenceDiagram
    participant P as Provider
    participant Z as ZooKeeper
    participant C as Consumer

    P->>Z: Register ephemeral znode
    Z-->>C: Instance appears
    Note over P,Z: Network partition
    P--xZ: Heartbeat interrupted
    Note over P,Z: Session timeout expires
    Z-->>C: Ephemeral znode deleted
    P->>Z: Reconnect with new session
    P->>Z: Register again
    Z-->>C: Instance appears again
~~~

Không nên coi việc mất kết nối trong vài giây là bằng chứng instance đã bị xóa khỏi registry. Trạng thái session và session timeout mới quyết định thời điểm ephemeral node bị dọn.

### 3.1. Session liveness không phải application readiness

Ephemeral node phản ánh vòng đời session ZooKeeper, không trực tiếp chứng minh API nghiệp vụ đang khỏe.

Một tiến trình có thể:

- Giữ kết nối ZooKeeper và duy trì session bình thường.
- Vẫn có ephemeral registration trong cây znode.
- Nhưng database hoặc message broker đã lỗi, khiến API không xử lý được request.

Ngược lại, một ứng dụng có thể tạm thời mất kết nối ZooKeeper nhưng vẫn đang xử lý request đã nhận. Discovery và health cần được xem là hai tín hiệu khác nhau.

Nếu cần phản ánh readiness, hãy thiết kế health check riêng và cập nhật trạng thái instance theo chính sách. Không dùng session liveness như một health probe HTTP thay thế Actuator.

## 4. Giới hạn thứ hai: health status không đầy đủ như registry chuyên dụng

ZooKeeper cung cấp primitive lưu dữ liệu và thông báo thay đổi; bản thân ZooKeeper không chủ động gọi HTTP endpoint của provider để kiểm tra readiness. Curator Service Discovery recipe cũng không có đầy đủ mô hình trạng thái như Eureka.

Spring Cloud Zookeeper bổ sung hỗ trợ trạng thái instance bằng metadata. Ví dụ, trạng thái `OUT_OF_SERVICE` được lưu trong payload và `ZookeeperServiceInstanceListSupplier` lọc instance có status khác `UP`. Nếu trường status trống, implementation xem instance là `UP` để tương thích ngược.

Điểm cần lưu ý:

- Đây là hành vi do Spring Cloud Zookeeper và LoadBalancer phối hợp, không phải một trạng thái health gốc của ZooKeeper.
- `OUT_OF_SERVICE` có thể dùng để ngừng đưa instance vào danh sách load balancing.
- Việc đổi status không tự động hoàn tất các request đang chạy; graceful shutdown và connection draining vẫn cần xử lý riêng.
- Không nên mặc định mọi health status của Actuator được tự động chuyển thành trạng thái znode.
- Nếu cần kiểm tra database, broker hoặc dependency, ứng dụng phải thiết kế health indicator và cơ chế cập nhật status phù hợp.

Có thể cấu hình trạng thái ban đầu và thông tin instance qua các thuộc tính `spring.cloud.zookeeper.discovery.*`. Ví dụ:

~~~yaml
spring:
  cloud:
    zookeeper:
      discovery:
        register: true
        initial-status: UP
        root: /services
        instance-host: 10.0.1.11
        instance-port: 8081
~~~

Tên và giá trị property phải khớp phiên bản Spring Cloud Zookeeper của dự án. `instance-host` cần là địa chỉ mà consumer có thể truy cập, không nhất thiết là địa chỉ loopback hoặc địa chỉ chỉ tồn tại bên trong container.

### 4.1. Dùng OUT_OF_SERVICE khi bảo trì

Spring Cloud Zookeeper có endpoint actuator cho ServiceRegistry để thay đổi status instance. Ví dụ dùng HTTPie:

~~~bash
http POST http://localhost:8081/service-registry status=OUT_OF_SERVICE
~~~

`ZookeeperServiceInstanceListSupplier` loại các instance có status khác `UP` khỏi danh sách dùng để load balance. Sau khi cập nhật, cần xác minh consumer đã nhận dữ liệu mới trước khi dừng tiến trình.

Luồng drain nên gồm:

1. Chuyển instance sang `OUT_OF_SERVICE`.
2. Chờ discovery/load balancer phía consumer cập nhật.
3. Ngừng nhận request mới ở ứng dụng hoặc ingress nếu có.
4. Hoàn tất request đang xử lý.
5. Dừng ứng dụng và để session đóng hoặc registration được deregister.

Chỉ thay status không đảm bảo mọi consumer đã refresh ngay tức thời. Cần kiểm thử cache và thời gian cập nhật của đúng phiên bản đang dùng.

## 5. Giới hạn thứ ba: watches không phải event stream bền vững

ZooKeeper hỗ trợ watch trên znode để client nhận thông báo khi dữ liệu thay đổi. Watch rất hữu ích để client tránh polling liên tục, nhưng standard watch có đặc tính **one-time trigger**: sau khi kích hoạt, client cần đăng ký watch mới nếu muốn nhận thay đổi tiếp theo.

Vì vậy:

- Watch event chỉ báo rằng dữ liệu đã thay đổi; client cần đọc lại trạng thái mới.
- Có khoảng trễ giữa lúc nhận event và lúc đăng ký watch tiếp theo.
- Một znode có thể thay đổi nhiều lần trong khoảng trễ đó; client không nên coi watch là nhật ký chứa mọi lần thay đổi.
- Khi client mất kết nối, nó không nhận watch event trong thời gian disconnected.
- Client cần xử lý session event và đọc lại trạng thái sau khi kết nối phục hồi.

ZooKeeper từ phiên bản 3.6 hỗ trợ persistent recursive watches, nhưng cần xác nhận phiên bản server, client và thư viện tích hợp có sử dụng khả năng đó hay không. Không nên mặc định Spring Cloud Zookeeper Dependency Watcher biến ZooKeeper thành một message bus.

### 5.1. Cách dùng watch an toàn

Khi nhận thông báo thay đổi, cách xử lý tổng quát là:

1. Đọc lại dữ liệu hiện tại của service hoặc dependency.
2. Cập nhật cache nội bộ từ snapshot mới.
3. Đăng ký lại watch nếu dùng standard watch.
4. Khi nhận session disconnected, chuyển ứng dụng sang chính sách an toàn.
5. Sau reconnect hoặc session mới, đồng bộ lại trạng thái thay vì chỉ dựa vào event đã nhận.

Nếu cần bảo đảm xử lý từng sự kiện nghiệp vụ theo thứ tự và không mất event, hãy dùng message broker hoặc event log phù hợp. Watch của ZooKeeper chủ yếu là tín hiệu thay đổi trạng thái.

## 6. Giới hạn thứ tư: quorum và tính sẵn sàng của ensemble

ZooKeeper chạy dưới dạng ensemble gồm nhiều server. Các server duy trì bản sao trạng thái và dùng cơ chế đồng thuận. Ensemble cần đa số server còn hoạt động để duy trì khả năng phục vụ các cập nhật.

Ví dụ với ensemble ba server:

| Server còn hoạt động | Có quorum? | Ảnh hưởng |
|---|---|---|
| 3/3 | Có | Hoạt động bình thường |
| 2/3 | Có | Vẫn có thể duy trì dịch vụ |
| 1/3 | Không | Không thể tiếp tục các cập nhật cần quorum |

Nếu mất quorum, provider có thể không đăng ký được instance mới, cập nhật status hoặc deregister theo cách mong đợi. Consumer có thể tạm thời còn dữ liệu đã đọc trước đó, nhưng dữ liệu đó có thể cũ.

Không nên coi ZooKeeper như một registry có thể ghi ở mọi node khi mạng bị chia cắt. Cần thiết kế ứng dụng chịu được:

- Lỗi kết nối tạm thời.
- Session disconnected và session expired.
- Registration bị xóa rồi được tạo lại.
- Không thể cập nhật registry khi ensemble mất quorum.
- Consumer nhìn thấy snapshot cũ trong thời gian đồng bộ lại.

Nếu discovery là thành phần thiết yếu để service khởi động, hãy xác định rõ chính sách khi ZooKeeper không sẵn sàng: fail startup, retry có giới hạn, hoặc chạy với cấu hình fallback đã được kiểm soát.

## 7. Giới hạn thứ năm: workload và quy mô dữ liệu

ZooKeeper tối ưu cho dữ liệu điều phối nhỏ và workload thiên về đọc. Nó giữ trạng thái quan trọng trong bộ nhớ, đồng thời duy trì transaction log và snapshot. Dữ liệu znode thường nên nhỏ, từ vài byte đến vài kilobyte.

Điều này ảnh hưởng đến cách dùng làm registry:

- Chỉ lưu metadata cần thiết để định vị instance.
- Không lưu payload nghiệp vụ, file cấu hình lớn hoặc lịch sử request vào znode registration.
- Tránh cập nhật status liên tục với tần suất cao.
- Tránh tạo/xóa znode liên tục cho từng request hoặc từng user session.
- Hạn chế số lượng watch và client connection không cần thiết.
- Theo dõi heap, latency, số connection, watch count và thời gian xử lý transaction.

Mỗi lần provider đăng ký, deregister hoặc cập nhật metadata đều tạo thêm thao tác ghi. Nếu hệ thống có số lượng instance lớn và churn cao, registry sẽ tạo thêm áp lực lên ensemble và client.

Không có một ngưỡng instance cố định áp dụng cho mọi hệ thống. Khả năng chịu tải phụ thuộc cấu hình ensemble, phần cứng, số client, kích thước znode, tần suất thay đổi và mẫu truy vấn.

## 8. Giới hạn thứ sáu: client-side discovery không thay thế routing

Spring Cloud Zookeeper cung cấp `DiscoveryClient` và tích hợp Spring Cloud LoadBalancer. Consumer truy vấn instance rồi chọn endpoint ở phía client.

Nó không tự cung cấp một proxy L7 tập trung để mọi request đều đi qua một router. Ứng dụng vẫn cần HTTP client được tích hợp load balancing, ví dụ OpenFeign, `RestTemplate` hoặc `WebClient`.

Ví dụ gọi service bằng logical name:

~~~java
@LoadBalanced
@Bean
RestTemplate restTemplate() {
    return new RestTemplate();
}
~~~

~~~java
ItemResponse[] items = restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

Load balancer có thể chọn instance từ danh sách do `ZookeeperServiceInstanceListSupplier` cung cấp. Nhưng consumer vẫn phải xử lý timeout, lỗi kết nối, retry và circuit breaker. Việc tìm thấy endpoint trong ZooKeeper không bảo đảm endpoint sẽ phản hồi thành công.

Ngoài ra, nếu địa chỉ đăng ký không định tuyến được từ consumer, discovery có thể trả về URI hợp lệ về cú pháp nhưng request vẫn thất bại. Luôn kiểm tra host, port và network policy từ chính môi trường của consumer.

## 9. Phạm vi của Spring Cloud Zookeeper Dependencies

Tên **Zookeeper Dependencies** trong Spring Cloud chỉ các service runtime mà ứng dụng khai báo là dependency và muốn gọi qua Feign, `RestTemplate` hoặc WebFlux. Đây không phải dependency JAR của Maven/Gradle.

Ví dụ, `order-service` cần gọi `inventory-service` và `pricing-service`. Ứng dụng có thể khai báo alias và path của các service trong cấu hình:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    zookeeper:
      dependencies:
        inventory:
          path: /services/inventory-service
          loadBalancerType: ROUND_ROBIN
          version: v1
          contentTypeTemplate: application/vnd.inventory.$version+json
          required: true
        pricing:
          path: /services/pricing-service
          loadBalancerType: RANDOM
          required: false
~~~

Trong ví dụ:

- `inventory` và `pricing` là alias mà ứng dụng dùng trong URL và service client.
- `path` là path nơi service được đăng ký trong ZooKeeper.
- `loadBalancerType` khai báo cách chọn instance.
- `version` và `contentTypeTemplate` hỗ trợ tạo Content-Type theo version nếu tính năng header tương ứng được bật.
- `required` quyết định cách xử lý khi dependency chưa được tìm thấy lúc ứng dụng khởi động.

### 9.1. Alias và path có vai trò khác nhau

Spring Cloud LoadBalancer cần application ID trong URL. Nó không nhận một path ZooKeeper phức tạp làm service ID. Vì vậy, Spring Cloud Zookeeper dùng alias để ánh xạ sang path thật.

Ví dụ client gọi alias:

~~~java
@FeignClient("inventory")
public interface InventoryClient {

    @GetMapping("/items")
    List<ItemResponse> getItems();
}
~~~

Alias `inventory` là định danh dùng ở phía Spring Cloud. Path `/services/inventory-service` cho biết nơi tìm registration trong ZooKeeper.

Không nên đưa toàn bộ znode path vào service ID hoặc URL logical service. Hãy giữ alias ổn định và cấu hình path ở một nơi.

### 9.2. Phạm vi của loadBalancerType

Spring Cloud Zookeeper Dependencies hỗ trợ các lựa chọn được tài liệu hóa:

| Giá trị | Hành vi |
|---|---|
| `STICKY` | Sau khi chọn, tiếp tục ưu tiên gọi cùng instance |
| `RANDOM` | Chọn instance ngẫu nhiên |
| `ROUND_ROBIN` | Luân phiên giữa các instance |

Đây là chính sách chọn instance ở client. Nó không tạo ra server-side routing, không đảm bảo phân phối tải hoàn toàn đều và không thay thế health check.

### 9.3. required và kiểm tra presence khi startup

`required: true` nghĩa là dependency phải được tìm thấy khi ứng dụng khởi động. Nếu không định vị được dependency bắt buộc trong ZooKeeper, Spring context có thể không khởi tạo thành công.

`required: false` cho phép ứng dụng khởi động và ghi cảnh báo khi dependency chưa có mặt.

| Cấu hình | Khi dependency không tồn tại lúc startup |
|---|---|
| `required: true` | Startup thất bại |
| `required: false` | Ứng dụng tiếp tục chạy và ghi log WARN |

Đây là kiểm tra presence lúc khởi động. Nó không chứng minh dependency sẽ luôn khỏe sau đó và không tự kiểm tra mọi request. Nếu dependency xuất hiện hoặc biến mất sau startup, cần dùng watcher và chính sách xử lý runtime phù hợp.

## 10. Dependency Watcher quản lý trạng thái đến đâu?

Spring Cloud Zookeeper cung cấp Dependency Watcher để đăng ký listener theo dõi thay đổi trạng thái của dependency. Listener có thể nhận sự kiện `CONNECTED` hoặc `DISCONNECTED`:

~~~java
public interface DependencyWatcherListener {

    void stateChanged(
            String dependencyName,
            DependencyState newState
    );
}
~~~

Ứng dụng đăng ký implementation dưới dạng Spring bean. Khi dependency thay đổi trạng thái, ứng dụng có thể:

- Ghi log và phát metric.
- Tạm ngừng một luồng xử lý phụ thuộc vào service đó.
- Thông báo trạng thái cho một thành phần giám sát.
- Bật lại công việc khi dependency được kết nối trở lại.

Dependency Watcher không phải một workflow engine. Nó không tự sửa service bị lỗi, không khởi động lại pod, không khôi phục database và không bảo đảm request đang xử lý được hoàn tất.

Tính năng Dependencies có thể được tắt bằng property `spring.cloud.zookeeper.dependency.enabled`. Property này điều khiển phần dependency runtime; nó khác với `spring.cloud.zookeeper.discovery.enabled`, vốn điều khiển discovery client.

### 10.1. Presence Checker

Presence Checker hỗ trợ quyết định khi ứng dụng khởi động dựa trên danh sách dependency:

- Dependency `required` mà không tìm thấy sẽ làm startup thất bại theo implementation mặc định.
- Dependency không bắt buộc mà thiếu sẽ tạo log WARN.
- Có thể thay thế verifier mặc định bằng bean `DependencyPresenceOnStartupVerifier` nếu cần chính sách riêng.

Đây là phạm vi kiểm tra presence. Nó không quản lý dependency bắc cầu như `order-service` cần `inventory-service`, mà `inventory-service` lại cần `database-service`, rồi tự động sắp xếp toàn bộ thứ tự khởi động.

Ứng dụng vẫn cần thiết kế timeout, retry, circuit breaker, fallback và chính sách khởi động riêng.

## 11. Dependency runtime không phải dependency build

Cần phân biệt hai cách dùng từ dependency:

| Khái niệm | Ví dụ | Được quản lý bởi |
|---|---|---|
| Dependency build | `spring-cloud-starter-zookeeper-discovery`, Curator, ZooKeeper Java client | Maven/Gradle và Spring Cloud BOM |
| Dependency runtime | `order-service` gọi `inventory-service` qua alias `inventory` | `spring.cloud.zookeeper.dependencies` |
| Dependency bắt buộc lúc startup | `required: true` cho service cần có khi ứng dụng khởi động | Spring Cloud Zookeeper Presence Checker |
| Trạng thái dependency runtime | `CONNECTED` hoặc `DISCONNECTED` | Spring Cloud Zookeeper Dependency Watcher |

`spring.cloud.zookeeper.dependencies` không tải JAR, không khai báo `groupId`/`artifactId`, không kiểm tra version thư viện và không quản lý transitive dependency. Nó mô tả các service đã đăng ký trong ZooKeeper mà ứng dụng muốn gọi.

## 12. Phạm vi dependency không thay thế API contract

Khai báo dependency alias, path, version hoặc Content-Type template không tự đảm bảo hai service tương thích về API.

Đội phát triển vẫn phải quản lý:

- Contract request và response.
- Schema và serialization.
- Tương thích ngược giữa các phiên bản API.
- Authentication và authorization.
- Timeout, retry và idempotency.
- Circuit breaker, fallback và giới hạn tải.
- Chính sách rollout và rollback.

`version` trong cấu hình Zookeeper Dependencies có thể được dùng để tạo header như `Content-Type`; nó không tự xác minh rằng provider thực sự triển khai version đó. Nếu provider đăng ký sai metadata hoặc không hỗ trợ contract được yêu cầu, request vẫn có thể lỗi.

Các `headers` cấu hình mặc định cũng cần được xem xét về bảo mật. Không lưu bearer token hoặc secret lâu dài trong file cấu hình có thể bị chia sẻ rộng. Dùng cơ chế secret management phù hợp cho thông tin xác thực.

## 13. Phạm vi dependency không phải distributed configuration

Spring Cloud Zookeeper còn có module cấu hình phân tán riêng. Discovery và Config cùng dùng ZooKeeper nhưng có mục tiêu khác nhau:

- `spring-cloud-starter-zookeeper-discovery`: đăng ký và khám phá service.
- `spring-cloud-starter-zookeeper-config`: đọc cấu hình ứng dụng từ namespace cấu hình.
- `spring.cloud.zookeeper.dependencies`: khai báo service runtime mà ứng dụng muốn gọi.

Không cần thêm Zookeeper Config nếu ứng dụng chỉ dùng service discovery. Ngược lại, thêm Config không tự đăng ký provider hoặc tạo DiscoveryClient.

Với Spring Cloud Zookeeper Config, cấu hình được đọc vào Spring Environment theo cơ chế bootstrap/config data của phiên bản. Tài liệu hiện hành mô tả cấu hình được đọc lúc startup và có thể reload qua endpoint refresh; việc tự động watch namespace config không được mô tả là đã triển khai trong luồng đó. Cần kiểm tra tài liệu đúng release train trước khi dựa vào cập nhật cấu hình tức thời.

## 14. Dependency build và phạm vi starter

Đối với discovery, starter thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

Nếu ứng dụng cần HTTP server, thêm dependency web tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Quản lý version Spring Cloud bằng BOM tương thích với Spring Boot:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Không nên tự thêm một phiên bản Curator hoặc ZooKeeper client tùy ý nếu starter đã quản lý phiên bản. Spring Cloud Zookeeper dùng Curator phía dưới; cần kiểm tra tương thích giữa Spring Cloud release train, Spring Boot, Curator và ZooKeeper server trước khi override dependency bắc cầu.

Nếu cần cấu hình phân tán, thêm `spring-cloud-starter-zookeeper-config` riêng. Không dùng một starter tổng hợp hoặc một loạt dependency không cần thiết chỉ vì muốn bật discovery.

## 15. Bảo mật và phân quyền

ZooKeeper dùng ACL trên từng znode để kiểm soát ai có thể đọc, ghi, tạo hoặc xóa node. ACL không tự động kế thừa xuống các znode con. Vì vậy, cấu hình ACL ở root path không có nghĩa toàn bộ registration bên dưới đã được bảo vệ như mong muốn.

Cần chú ý:

- Giới hạn quyền đọc và ghi theo service hoặc namespace.
- Chỉ cho workload hợp lệ tạo registration và thay đổi status.
- Bảo vệ thông tin xác thực của client và connection string.
- Không lưu secret trong metadata của service.
- Giới hạn network access đến cổng client của ZooKeeper.
- Kiểm tra ACL của cả node cha lẫn node con được tạo ra.
- Dùng TLS/authentication theo yêu cầu của hạ tầng và phiên bản triển khai.

Nếu một client có thể ghi vào path registration của service khác, nó có thể công bố endpoint giả hoặc thay đổi dữ liệu discovery. Quyền ghi registry cần được xem như quyền ảnh hưởng đến định tuyến nội bộ.

## 16. Khi nào nên dùng và khi nào nên cân nhắc giải pháp khác?

| Bối cảnh | Đánh giá |
|---|---|
| Hệ thống đã vận hành ZooKeeper cho coordination và có đội ngũ hiểu rõ session/ACL | Có thể tận dụng cho discovery để giảm thêm một nền tảng |
| Service count và churn vừa phải, dữ liệu registration nhỏ, phần lớn thao tác là đọc | Phù hợp với đặc tính read-dominant của ZooKeeper |
| Cần tích hợp `DiscoveryClient` và Spring Cloud LoadBalancer | Có hỗ trợ qua Spring Cloud Zookeeper |
| Cần health check phong phú, query passing, status policy nhiều mức | Cần tự thiết kế và kiểm chứng kỹ; registry chuyên dụng có thể phù hợp hơn |
| Tần suất tạo/xóa instance rất cao hoặc lượng watch/client lớn | Cần benchmark và đánh giá tải ensemble; cân nhắc registry khác |
| Hệ thống chạy hoàn toàn trên Kubernetes | Có thể dùng Kubernetes Service/EndpointSlice nếu đáp ứng yêu cầu |
| Cần service mesh, traffic policy và observability ở tầng mạng | Cân nhắc nền tảng service mesh hoặc registry tích hợp tương ứng |

Không có một giới hạn số instance cố định cho mọi triển khai. Quyết định nên dựa trên benchmark thực tế, tốc độ thay đổi registration, số client, watch, kích thước metadata và khả năng vận hành ensemble.

## 17. Checklist trước khi đưa ZooKeeper Discovery vào production

1. Xác định ZooKeeper có phải nền tảng coordination sẵn có hay chỉ được dựng thêm để discovery.
2. Triển khai ensemble có quorum và kiểm tra backup, snapshot, log, heap và disk.
3. Chọn session timeout phù hợp với network và thời gian phục hồi.
4. Xác nhận provider đăng ký host/port có thể truy cập từ consumer.
5. Phân biệt session liveness với application readiness.
6. Thiết kế health/status và drain thay vì chỉ dựa vào ephemeral node.
7. Kiểm tra consumer refresh, watch và hành vi khi session expired.
8. Giữ payload znode nhỏ, hạn chế registration churn và watch không cần thiết.
9. Chỉ khai báo runtime dependency thực sự cần thiết; quyết định rõ `required`.
10. Kiểm tra Dependency Watcher và Presence Checker trong các tình huống service mất/kết nối lại.
11. Cấu hình ACL và authentication cho từng path.
12. Kiểm tra Spring Cloud BOM, Curator và ZooKeeper version compatibility.
13. Đo hành vi khi mất quorum, partition, session expiry và provider restart.
14. Xác minh timeout, retry, circuit breaker và fallback ở consumer.

## 18. Ghi nhớ

- ZooKeeper là dịch vụ coordination; Spring Cloud Zookeeper dùng Curator để xây dựng registration, discovery và tích hợp LoadBalancer.
- Ephemeral registration gắn với session. Session hết hạn sẽ xóa node, nhưng mất kết nối tạm thời chưa chắc làm session hết hạn ngay.
- Session liveness không đồng nghĩa ứng dụng đã sẵn sàng xử lý nghiệp vụ.
- Standard watches là one-time trigger; không nên dùng chúng như một event log bền vững.
- Ensemble cần quorum; mất đa số server có thể làm gián đoạn cập nhật registration.
- ZooKeeper phù hợp dữ liệu điều phối nhỏ và workload thiên về đọc; cần cẩn trọng với churn, payload và watch quy mô lớn.
- Spring Cloud Zookeeper có hỗ trợ `OUT_OF_SERVICE` qua metadata và LoadBalancer supplier; đây không phải health check đầy đủ như một registry chuyên dụng.
- `spring.cloud.zookeeper.dependencies` khai báo service runtime bằng alias và path; nó không quản lý JAR Maven/Gradle.
- `required`, Dependency Watcher và Presence Checker hỗ trợ kiểm tra presence/trạng thái dependency, không thay thế resilience hoặc API contract.
- Discovery, distributed configuration và dependency build là ba phạm vi riêng; chỉ thêm starter tương ứng với nhu cầu.

ZooKeeper có thể là nền tảng discovery hữu ích khi hệ thống đã cần coordination và đội ngũ hiểu rõ cách vận hành session, watch, quorum và ACL. Khi dùng nó cho service discovery, hãy giữ dữ liệu nhỏ, thiết kế health/readiness rõ ràng và giới hạn tính năng dependency ở phạm vi khai báo, theo dõi các service runtime mà ứng dụng thực sự gọi.

## Tài liệu tham khảo

- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Service Registry and Instance Status](https://docs.spring.io/spring-cloud-zookeeper/docs/current/reference/html/)
- [Spring Cloud Zookeeper — Zookeeper Dependencies and Dependency Watcher](https://docs.spring.io/spring-cloud-zookeeper/docs/current/reference/html/)
- [Spring Cloud Zookeeper — Quick Start and Maven/Gradle setup](https://docs.spring.io/spring-cloud-zookeeper/reference/quickstart.html)
- [Apache ZooKeeper — Overview and Design Goals](https://zookeeper.apache.org/doc/current/zookeeperOver.html)
- [Apache ZooKeeper — Programmer's Guide: Sessions, Watches and ACLs](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
