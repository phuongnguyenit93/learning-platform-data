# Chia sẻ tuyến và đồng bộ refresh giữa nhiều bản sao

## 1. Vấn đề: sửa route ở Gateway A nhưng request vẫn đi theo route cũ ở Gateway B

Một API Gateway trong môi trường production hiếm khi chỉ chạy một tiến trình. Giả sử **Spring Cloud Gateway** được triển khai thành ba replica phía sau một load balancer:

- `gateway-a`: nhận một phần request từ client.
- `gateway-b`: nhận một phần request khác.
- `gateway-c`: nhận phần request còn lại.

Cả ba phải có cùng quy tắc định tuyến, ví dụ `/api/orders/**` đi đến `lb://ORDER-SERVICE`, rồi thực thi các route predicate, filter chain, biến đổi path/header, service discovery, xác thực, giới hạn lưu lượng, retry, circuit breaker và TLS theo chính sách.

Đội vận hành đổi đường dẫn `/api/orders/**` từ phiên bản cấu hình **v41** sang **v42** và gọi API chỉnh route trên `gateway-a`. Nếu chỉ A nhận thay đổi, hệ thống trở nên khó đoán:

~~~text
Client -> External Load Balancer
  request #1 -> gateway-a -> route v42 -> backend mới
  request #2 -> gateway-b -> route v41 -> backend cũ
  request #3 -> gateway-c -> route v41 -> backend cũ
  request #4 -> gateway-a -> route v42 -> backend mới
~~~

Hậu quả có thể là `404` lúc có lúc không, header bị sửa không nhất quán, auth/rate-limit policy lệch giữa replicas hoặc request chuyển sai microservice. **Không thể giải quyết bằng cách chỉ gọi refresh một lần qua load balancer**, vì lệnh đó có thể chỉ đến một instance.

Bài thuộc chương **Tuyến động** trong module **SPRING_CLOUD_GATEWAY**. Trọng tâm là **chia sẻ route definitions** và **đồng bộ việc áp dụng thay đổi qua nhiều bản sao**, không phải hướng dẫn chỉnh YAML trên một máy.

Sau bài này, bạn có thể:

1. Phân biệt nguồn lưu route dùng chung với **route cache cục bộ** của từng replica.
2. Chọn `RouteDefinitionRepository`, Redis hoặc nguồn cấu hình ngoài cho bài toán cluster.
3. Hiểu `RefreshRoutesEvent` và `POST /actuator/gateway/refresh` **chỉ tác động tới JVM/instance nhận event hoặc lệnh**.
4. Thiết kế control plane có **revision, thông báo thay đổi, đồng bộ lại khi mất event và xác nhận từng replica đã áp dụng**.
5. Kiểm thử thêm/sửa/xóa route qua 2–3 Gateway replicas, phát hiện cấu hình lệch và thực hiện rollback.
6. Bảo vệ endpoint quản trị, Redis, route URI và filter configuration khỏi sửa đổi trái phép.

> **Phạm vi:** Spring Cloud Gateway **Server WebFlux** và các API route definition/Actuator của nó. Ví dụ nêu sự khác biệt namespace WebFlux 4.x và các nhánh mới dùng `spring.cloud.gateway.server.webflux`. Gateway Server MVC và các phiên bản Spring Cloud khác có thể có cơ chế khác. Cần đối chiếu tài liệu của release đang chạy trước khi áp dụng property, đặc biệt với Redis repository và quyền Actuator.

## 2. Ba lớp cần phân biệt: nguồn sự thật, cache và thông báo refresh

Một hệ thống route động có ít nhất ba lớp dữ liệu:

| Lớp | Câu hỏi nó trả lời | Ví dụ | Có tự đồng bộ với replicas khác không? |
| --- | --- | --- | --- |
| **Shared route definitions** | *Route nào được mong muốn?* | Redis, DB, Config Server/Git | Chia sẻ dữ liệu nếu tất cả replica đọc cùng nguồn |
| **Effective route cache trong từng JVM** | *Replica này hiện đang dùng route nào?* | `CachingRouteLocator` | **Không**, mỗi JVM có trạng thái riêng |
| **Refresh/change notification** | *Khi nào replica cần tải lại?* | `RefreshRoutesEvent`, Actuator, message bus | Event nội bộ JVM **không** tự đi tới JVM khác |

Trong Spring Cloud Gateway, `RouteDefinition` là mô tả route (ID, URI, predicate, filter, order, metadata). `Route` hiệu lực là kết quả chuyển các mô tả ấy thành điều kiện và filter có thể chạy. Một replica có thể **đọc được definition mới trong Redis**, nhưng vẫn tiếp tục dùng **route cache cũ** cho đến khi quá trình refresh của instance đó diễn ra.

Đây là khác biệt trọng tâm:

- **Shared store** giải quyết **các node nhìn vào cùng nguồn dữ liệu**.
- **Refresh local** giải quyết **một node nhận cấu hình mới**.
- **Cluster propagation và convergence check** giải quyết **cả cụm có thực sự hội tụ về cùng phiên bản chưa**.

Chỉ có shared Redis **không đủ** để đảm bảo mọi replica lập tức có cùng effective routes; chỉ có lệnh refresh **không đủ** nếu dữ liệu mỗi replica đang lấy từ nguồn khác nhau.

### 2.1. Sơ đồ kiến trúc đúng

~~~mermaid
flowchart TD
    OP["Admin / CI-CD / Route Control Plane"] -->|"Validate và commit revision v42"| S[("Shared Route Repository<br/>Redis / DB")]
    OP -->|"Phát route-changed revision v42"| BUS["Event Bus / Pub/Sub"]
    BUS --> A["Gateway A<br/>local refresh"]
    BUS --> B["Gateway B<br/>local refresh"]
    BUS --> C["Gateway C<br/>local refresh"]
    S -->|"Đọc route definitions"| A
    S -->|"Đọc route definitions"| B
    S -->|"Đọc route definitions"| C
    A --> ACK["Convergence monitor / ACK"]
    B --> ACK
    C --> ACK
    LB["Client Load Balancer"] --> A
    LB --> B
    LB --> C
    A --> U["Upstream microservices"]
    B --> U
    C --> U
~~~

**Event chỉ nên thông báo có phiên bản mới**, không nhất thiết chứa toàn bộ route object hoặc credential. Replica đọc lại definition từ nguồn sự thật, kiểm tra hợp lệ, làm mới cache, sau đó báo trạng thái áp dụng. Khi event đến trễ, duplicate hoặc bị mất, một cơ chế reconciliation vẫn đưa replica quay về phiên bản hiện hành.

## 3. Các abstraction của Spring Cloud Gateway

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `RouteDefinition` | Mô tả route ở mức dữ liệu | ID, URI, predicates, filters, order, metadata |
| `RouteDefinitionLocator` | Đọc danh sách `RouteDefinition` | Có thể đọc từ YAML, discovery hoặc repository |
| `RouteDefinitionWriter` | Lưu/xóa definition bằng API reactive | Không đồng nghĩa cache đã được reload |
| `RouteDefinitionRepository` | Gộp khả năng đọc và ghi definitions | Implementation có thể in-memory hoặc shared Redis |
| `RouteDefinitionRouteLocator` | Chuyển definition thành route chạy được | Cần filter/predicate factories tương thích |
| `CachingRouteLocator` | Giữ cache những routes đã xây dựng | Từng Gateway replica có trạng thái riêng |
| `RefreshRoutesEvent` | Tín hiệu làm mới route trong ứng dụng | Là Spring application event **cục bộ JVM** |
| `/actuator/gateway/refresh` | Endpoint làm mới cache route | Chỉ áp dụng trên **instance nhận POST** |
| `DiscoveryClient` / LoadBalancer | Tìm/chọn instance upstream theo `lb://` | **Khác** việc chia sẻ danh sách Gateway routes |

Một `RouteDefinitionRepository` về mặt abstraction hỗ trợ đọc và ghi:

~~~java
// Chữ ký minh họa của abstraction Gateway:
public interface RouteDefinitionRepository
        extends RouteDefinitionLocator, RouteDefinitionWriter {
}

// Đọc:
Flux<RouteDefinition> getRouteDefinitions();

// Ghi hoặc xóa theo API reactive của writer:
Mono<Void> save(Mono<RouteDefinition> route);
Mono<Void> delete(Mono<String> routeId);
~~~

Đoạn code trên nhằm biểu diễn **hợp đồng của các interface**, không phải một file Java hoàn chỉnh để chép vào ứng dụng: các phương thức đọc/ghi thuộc interface tương ứng. Khi triển khai, dùng đúng types/API được thư viện Spring Cloud Gateway của phiên bản project cung cấp.

### 3.1. Route definition khác URL của instance upstream

Route:

~~~yaml
id: orders-api
uri: lb://ORDER-SERVICE
predicates:
  - Path=/api/orders/**
filters:
  - StripPrefix=1
~~~

Đây là **route definition**, quy định cách Gateway nhận request. Tên `ORDER-SERVICE` là **service ID logic**; mỗi instance của `order-service` có host/port riêng do DiscoveryClient và Spring Cloud LoadBalancer quản lý.

Cập nhật danh sách pod của order-service có thể không cần thay route `lb://ORDER-SERVICE`. Ngược lại, thay `Path=/api/orders/**` hay `RewritePath` là thay **Gateway route definition** và cần cơ chế refresh route phù hợp.

## 4. Vì sao InMemoryRouteDefinitionRepository không chia sẻ route?

Một Gateway replica có memory, ApplicationContext và route cache riêng:

~~~text
gateway-a (JVM #1)                gateway-b (JVM #2)
  InMemoryRouteDefinitionRepo       InMemoryRouteDefinitionRepo
  route ID = orders-v42             route ID = orders-v41
  cache = orders-v42                cache = orders-v41
~~~

Thao tác `POST /actuator/gateway/routes/orders-api` tới A có thể lưu route vào repository **của A**. Nếu backend repository là in-memory, B sẽ không đọc được dữ liệu ấy, kể cả bạn gọi `POST /actuator/gateway/refresh` trên B.

Bài toán này không giải quyết bằng đổi chiến lược load balancing giữa các Gateway replicas. Load balancer chỉ chọn node nhận request; **nó không sao chép state trong memory**.

### 4.1. Route từ application.yml có thuộc repository động không?

Không nên coi mọi route từ `application.yml` là route có thể tùy ý sửa/xóa qua Actuator. Gateway thường có một `PropertiesRouteDefinitionLocator` riêng, trong khi Actuator ghi/xóa qua `RouteDefinitionWriter`/repository tương ứng.

Tài liệu Actuator lưu ý những route được tạo từ application configuration (hoặc `@Bean`) **không thể xóa qua endpoint quản trị route động như một route đã được tạo qua Actuator**. Nếu static route và dynamic route cùng ID hoặc cùng predicate có thứ tự ưu tiên không rõ, request có thể khớp route không mong muốn.

Khuyến nghị:

- Định nghĩa rõ **nguồn sở hữu từng route ID**.
- Dành một namespace/nhóm ID cho routes động, ví dụ `dyn-catalog-api`.
- Tránh trùng ID giữa YAML, Java DSL, DiscoveryClient locator và Redis.
- Không dùng Actuator POST để cố ghi đè route static đang nằm trong code.
- Kiểm thử route order khi một URL khớp nhiều predicate.

## 5. Dùng RedisRouteDefinitionRepository cho cluster

Tài liệu Spring Cloud Gateway đề cập hai implementation của `RouteDefinitionRepository`: **`InMemoryRouteDefinitionRepository`** và **`RedisRouteDefinitionRepository`**. Với nhiều Gateway replicas, Redis có thể làm nguồn chung cho các definitions động. <https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/sharing-routes.html>

### 5.1. Dependencies và hạ tầng

Một dự án Gateway Server WebFlux dùng Redis repository cần:

- Starter Gateway Server WebFlux tương thích Spring Boot/Spring Cloud release train.
- `spring-boot-starter-data-redis-reactive` để có kết nối Redis reactive.
- Redis endpoint có thể truy cập từ **mọi Gateway replica**.
- Cấu hình bảo mật Redis: auth/ACL, TLS nếu policy yêu cầu, network isolation.
- Quy trình persistence, backup/restore, HA/failover và quản lý schema/keys.
- Cơ chế phát tín hiệu và đồng bộ refresh giữa các replica (thiết kế ở mục 8–10).

**Không nhầm Redis repository với RedisRateLimiter.** Cả hai có thể dùng Redis nhưng lưu dữ liệu/giải quyết bài toán khác nhau. Bật RedisRateLimiter không tự kích hoạt lưu Gateway routes trong Redis.

### 5.2. Namespace cấu hình WebFlux mới

Ví dụ **Server WebFlux** với nhóm property theo `spring.cloud.gateway.server.webflux` được công bố trong configuration properties của các nhánh mới:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
  cloud:
    gateway:
      server:
        webflux:
          redis-route-definition-repository:
            enabled: true
~~~

Nếu Redis có TLS, password, sentinel/cluster hoặc cơ chế xác thực riêng, cấu hình bằng Spring Data Redis theo phiên bản Spring Boot và môi trường triển khai. Đoạn trên chỉ mô tả một Redis endpoint ví dụ, **chưa phải cấu hình production hoàn chỉnh**.

### 5.3. Namespace thường gặp ở WebFlux 4.x

Một số phiên bản/tài liệu trước đây đặt property tại:

~~~yaml
spring:
  cloud:
    gateway:
      redis-route-definition-repository:
        enabled: true
~~~

**Đây là các lựa chọn theo phiên bản, không phải hai block nên chép đồng thời.** Đặc biệt, trang hướng dẫn “Sharing Routes” và bảng configuration properties ở một số release có thể trình bày tiền tố khác nhau; hãy kiểm tra **effective configuration của đúng jar đang triển khai**, không chỉ tên phiên bản trong một bài blog.

Không nên khẳng định “cấu hình Redis repository là đủ để cluster tự refresh”. Redis là nguồn dữ liệu được chia sẻ, **không phải bảo đảm tất cả JVM đều đã cập nhật local route cache**.

### 5.4. Cùng một nguồn không đồng nghĩa cùng một cấu hình hiệu lực

Giả sử A/B/C đọc cùng Redis nhưng:

- A đã refresh ở revision 42.
- B chưa refresh, vẫn đang dùng cache revision 41.
- C refresh nhưng thiếu `CustomGatewayFilterFactory` chỉ có trong bản binary mới, không xây dựng được route 42.

Dù **store giống nhau**, cả ba chưa hội tụ. Cần quan sát kết quả apply trên từng node và phiên bản binary/feature flag, không chỉ kiểm tra Redis đã có một record.

## 6. Actuator API: CRUD và refresh chỉ trên node nhận lệnh

### 6.1. Những endpoint liên quan

Spring Cloud Gateway có Actuator endpoint `/actuator/gateway`, với các API theo phiên bản gồm:

| API | Ý nghĩa |
| --- | --- |
| `GET /actuator/gateway/routes` | Xem các route đang được Gateway dựng/hiển thị |
| `GET /actuator/gateway/routedefinitions` | Xem cấu hình route definitions mà Gateway có thể đọc |
| `GET /actuator/gateway/routes/{id}` | Xem một route cụ thể |
| `POST /actuator/gateway/routes/{id}` | Tạo route qua writer/repository của instance |
| `DELETE /actuator/gateway/routes/{id}` | Xóa route có thể quản lý qua writer |
| `POST /actuator/gateway/refresh` | Yêu cầu refresh route cache **trên instance đó** |

**Quyền ghi bị hạn chế theo mặc định** ở các phiên bản mới. Ví dụ khi chỉ muốn quan sát:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

`read-only` giúp tránh thay đổi route qua HTTP management endpoint, nhưng **không** thay thế bảo vệ Actuator bằng auth/network policy. Không để danh sách route, URI nội bộ và metadata nhạy cảm lộ ra Internet.

Khi cần quản trị route bằng Actuator ở môi trường thử nghiệm hoặc control plane đã bảo vệ, một số phiên bản dùng:

~~~yaml
management:
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

**Cảnh báo:** `unrestricted` tạo bề mặt điều khiển routing cực kỳ nhạy cảm. Chỉ bật trên management network riêng, qua xác thực mạnh, TLS/mTLS, RBAC, audit và giới hạn nguồn truy cập; hoặc ưu tiên xây một control plane riêng. Tên property và điều kiện exposure cần được kiểm tra theo Spring Boot/Actuator version. Không bật unrestricted chỉ để “thử curl từ Internet”.

### 6.2. Tạo route demo bằng API quản trị

Giả sử đã bật quyền ghi trong staging, `gateway-a` và `gateway-b` đều đọc shared Redis repository. Đặt các biến **cho môi trường thử nghiệm**:

~~~bash
# Ví dụ chạy trên shell có quyền truy cập mạng quản trị.
export ADMIN_A="https://gateway-a-admin.internal.example"
export ADMIN_B="https://gateway-b-admin.internal.example"
# ADMIN_TOKEN được cấp an toàn bởi hạ tầng. Không ghi token thật trong tài liệu.
~~~

Tạo route qua A:

~~~bash
curl -i -X POST "$ADMIN_A/actuator/gateway/routes/dyn-orders-api" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "uri": "lb://ORDER-SERVICE",
    "predicates": ["Path=/api/orders/**"],
    "filters": ["StripPrefix=1"],
    "order": 0
  }'
~~~

Lưu ý:

1. Đoạn JSON dùng **shortcut DSL strings** trong `predicates` và `filters`, theo cách Actuator Create Route mô tả. Response GET route có thể có định dạng trình bày khác, **không thể lấy GET response rồi POST lại nguyên xi**.
2. Cần có `spring-cloud-starter-loadbalancer` và nguồn `ServiceInstance` nếu URI dùng `lb://`; route lưu được không bảo đảm upstream tồn tại.
3. Với Redis-backed writer, bản ghi route có thể xuất hiện trong shared repository; nếu writer của A vẫn là in-memory hoặc app có nhiều writer khác nhau, thao tác này **không hề tạo dữ liệu chung**. Phải xác minh repository thực tế.
4. API này chỉ là công cụ học tập/kiểm tra. Production nên thay đổi qua một control plane đã validate, audit và versioning.

**Không gửi POST lại cùng route ID một cách mù quáng.** Tài liệu Actuator mới cảnh báo việc POST vào route ID đang tồn tại có thể gây trùng definition và lỗi nội bộ trong một số trường hợp. Quy trình cập nhật qua Actuator có thể cần **xóa rồi tạo lại**, nhưng cách làm này có khoảng thời gian route vắng mặt; production nên có cơ chế cập nhật phiên bản/atomic publish thích hợp.

### 6.3. Làm mới A không tự làm mới B

Thực hiện:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/refresh"
~~~

Sau đó kiểm tra A:

~~~bash
curl -sS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes"
~~~

Đến đây **chưa có bằng chứng B đã sử dụng route mới**. B có thể vẫn giữ cache cũ. Để thực hành thủ công:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/refresh"

curl -sS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/routes"
~~~

**Không gửi hai lệnh refresh qua một URL public do load balancer phân phối** rồi cho rằng chắc chắn đã trúng cả A và B. Hai lần request có thể được gửi tới cùng A. Muốn tác động từng replica, cần **management endpoint ổn định theo node/pod** hoặc agent/event consumer chạy bên trong từng tiến trình.

### 6.4. HTTP 200 của refresh không phải chứng nhận cả cluster đã hội tụ

Actuator có thể trả HTTP 200 cho lệnh refresh route cache; ở các version, quá trình refresh thực tế có thể được thực hiện bất đồng bộ. Vì vậy:

- 200 chỉ nói **lệnh được nhận/xử lý theo hợp đồng endpoint**, không nói mọi request trong toàn cluster đã dùng v42.
- Cần quan sát `GET /actuator/gateway/routes` của **từng replica** và/hoặc một API health/revision nội bộ.
- Khi chuyển đổi nhiều route, phải xác nhận **tất cả** route cần thiết được dựng thành công, không chỉ một ID.
- Một request đang xử lý trước refresh có thể hoàn tất theo route/filter đã chọn trước đó; refresh không phải transaction cho mọi HTTP request đang bay.

Ở các phiên bản mới, Actuator còn có tùy chọn refresh theo **metadata** của route; đây là tối ưu cục bộ, không thay thế cơ chế cluster-wide propagation, và không nên dùng khi chưa hiểu đúng phiên bản/cách invalidation.

## 7. RefreshRoutesEvent: tín hiệu Spring bên trong một JVM

Một cách kích hoạt local refresh từ code là phát `RefreshRoutesEvent`:

~~~java
package example.gateway.control;

import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class LocalRouteRefresh {
    private final ApplicationEventPublisher publisher;

    public LocalRouteRefresh(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    // Được gọi sau khi control plane báo có revision mới.
    public void requestRefresh() {
        publisher.publishEvent(new RefreshRoutesEvent(this));
    }
}
~~~

Đây là **hook tối giản**, không phải implementation cluster sync đầy đủ. `ApplicationEventPublisher` phát event trong ApplicationContext của **chính tiến trình đang chạy**. Nó **không** tự gửi message cho A/B/C.

Muốn mỗi replica nhận tín hiệu, cần một trong các giải pháp:

- **Bus/pub-sub** (Redis Pub/Sub, Kafka, RabbitMQ hoặc một event bus được vận hành).
- **Node agent** nhận notification qua một kênh được bảo vệ và gọi local refresh.
- **Control plane** gọi management API của từng replica (khi hạ tầng cho phép, quản trị node membership đúng).
- **Periodic reconciliation/polling** đọc current revision từ store rồi refresh khi khác.

Nếu dùng Spring Cloud Bus hoặc Spring Cloud Config, phải xác minh loại event nào **thực sự** được phát cho route cache trong phiên bản đang chạy. **Không đồng nhất `/actuator/refresh` của Spring Cloud Context với `/actuator/gateway/refresh` hoặc `RefreshRoutesEvent`**: chúng có hợp đồng và phạm vi khác nhau.

## 8. Kiến trúc đồng bộ nhiều replica bằng revision + bus + reconciliation

Một thiết kế production thường cần một **control plane** (thành phần quản trị định tuyến) tách khỏi **data plane** (Gateway nhận request thật).

### 8.1. Luồng cập nhật đề xuất

~~~mermaid
sequenceDiagram
    autonumber
    participant Admin as Admin / CI
    participant CP as Route Control Plane
    participant DB as Shared Redis / DB
    participant Bus as Change Bus
    participant A as Gateway A
    participant B as Gateway B
    participant C as Gateway C
    Admin->>CP: Đề xuất route revision v42
    CP->>CP: Validate, authorization, compare revision
    CP->>DB: Commit định nghĩa v42
    DB-->>CP: Persisted
    CP->>Bus: routes.changed(v42)
    Bus-->>A: Signal v42
    Bus-->>B: Signal v42
    Bus-->>C: Signal v42
    A->>DB: Reload definitions v42
    B->>DB: Reload definitions v42
    C->>DB: Reload definitions v42
    A-->>CP: Applied / failed v42
    B-->>CP: Applied / failed v42
    C-->>CP: Applied / failed v42
    CP-->>Admin: Convergence status, không chỉ write success
~~~

Các ACK trong sơ đồ là **chức năng hệ thống tự thiết kế**, không phải `RefreshRoutesEvent` của Spring Cloud Gateway tự gửi ACK đến control plane.

Quy trình chi tiết:

1. **Xác thực người thay đổi:** RBAC, approval, audit, lý do thay đổi.
2. **Validate candidate:** ID duy nhất, URI/scheme được phép, predicates/filters hợp lệ, không phá route bảo mật, không tạo SSRF.
3. **Ghi shared source:** version/revision tăng đơn điệu, có cơ chế chống lost update.
4. **Chỉ sau commit** mới phát message `routes.changed` có revision hoặc dấu nhận diện snapshot.
5. **Mỗi replica nhận signal** và so sánh với revision đã áp dụng.
6. **Reload local:** kích hoạt `RefreshRoutesEvent` hoặc API refresh cục bộ, để Gateway dựng lại effective routes từ shared locator.
7. **Xác minh:** route snapshot/danh sách ID/order/metadata và thử một request mẫu hoặc health probe.
8. **ACK:** ghi nhận version và kết quả áp dụng cho từng replica.
9. **Convergence monitor:** cảnh báo nếu một replica chậm, chưa apply hoặc apply lỗi; cân nhắc không đưa node stale vào traffic pool.
10. **Reconcile định kỳ:** mọi replica kiểm tra latest revision, khôi phục khi message bus mất event hoặc node khởi động muộn.

### 8.2. Payload của message nên nhỏ và bất biến

Ví dụ notification từ control plane:

~~~json
{
  "eventType": "routes.changed",
  "revision": 42,
  "source": "gateway-routing",
  "changeId": "chg-2026-042",
  "publishedAt": "2026-11-24T05:00:00Z"
}
~~~

Đây là **định dạng ứng dụng tự thiết kế**, không phải event JSON built-in của Spring Cloud Gateway. Không đưa client secret, toàn bộ Authorization header, raw cookie hoặc cấu hình TLS key vào event.

**Không nhất thiết chứa full route definition trong message.** Mỗi node có thể đọc revision mới nhất từ nguồn dữ liệu chung. Cách đó cũng giúp xử lý event đến sai thứ tự:

~~~text
Node đang áp dụng v40.
Message v42 đến trước v41.
Node kiểm tra shared latest revision = v42.
Node áp dụng v42.
Message v41 đến muộn -> bỏ qua hoặc chỉ reconcile v42.
~~~

Không nên “áp dụng mù” payload từ một event v41 đến sau v42 và vô tình rollback cấu hình.

### 8.3. Vì sao Pub/Sub thôi chưa đủ?

Redis Pub/Sub thông thường không phải cơ chế lưu hàng đợi bền vững cho subscriber offline. Nếu `gateway-c` tạm mất kết nối tại thời điểm message v42 được phát, nó có thể **không nhận được message**.

Vì vậy:

- Khi startup, node cần **đọc latest shared revision** và xác minh effective routes.
- Sau khi kết nối bus lại, node cần **reconcile** thay vì chỉ chờ event tiếp theo.
- Nên có polling thưa, ví dụ vài chục giây theo SLA và tải hệ thống, hoặc dùng bus có durable delivery phù hợp.
- Consumer phải **idempotent**: cùng v42 được phát 2–3 lần vẫn an toàn.
- Nếu một node load v42 lỗi, phải **đánh dấu lỗi và retry có giới hạn**, không ACK v42 giả.

**Chia sẻ Redis route definitions là một phần của kiến trúc**; cơ chế revision, ACK và reconcile cần được thiết kế/lập trình riêng nếu tổ chức yêu cầu khả năng hội tụ đáng tin.

### 8.4. Phân biệt write ACK, event ACK và applied ACK

| Tín hiệu | Nó chứng minh điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Shared repository trả lưu thành công | Route definition đã ghi vào store theo hợp đồng | Các node đã đọc |
| Event bus nhận message | Thông báo đã được nhận/persist theo loại bus | Mỗi node đã refresh |
| Node nhận message | Subscriber có tín hiệu về revision mới | Route đã dựng hợp lệ |
| Local refresh được kích hoạt | Node đã được yêu cầu refresh | Effective routes mới đã sẵn sàng |
| Node báo **applied revision** sau validation | Node đã kiểm chứng route snapshot/behavior theo policy | Request đang xử lý trước đó đã kết thúc |
| Convergence monitor thấy A/B/C đều v42 | Cluster đã đồng bộ theo điều kiện kiểm tra | Mọi request nghiệp vụ sẽ thành công |

Sự phân biệt này giúp giải thích tại sao “Redis đã có bản ghi mới” hoặc “refresh trả HTTP 200” **chưa đủ** để triển khai an toàn.

## 9. Code tích hợp local refresh khi nhận message

Dưới đây là phần **adapter nội bộ của từng Gateway node**. Ví dụ giả định đã có một subscriber Kafka/Redis/HTTP management đáng tin gọi `onRouteChangeMessage` sau khi xác minh message.

~~~java
package example.gateway.control;

import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public final class ClusterRouteChangeHandler {
    private final ApplicationEventPublisher publisher;

    public ClusterRouteChangeHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    // Hook được gọi bởi consumer của bus trong tiến trình này.
    // Không gọi trực tiếp từ client public.
    public void onRouteChangeMessage(long revision) {
        // Bản demo: phát local event. Production cần:
        // - so sánh revision với latest shared store;
        // - tránh xử lý event cũ/trùng;
        // - theo dõi refresh completion và validate effective routes;
        // - báo ACK hoặc failure; retry/reconcile khi cần.
        publisher.publishEvent(new RefreshRoutesEvent(this));
    }
}
~~~

**Những điều đoạn code chưa làm**:

- Chưa định nghĩa subscriber Redis/Kafka, TLS/auth, cơ chế đọc message.
- Chưa đồng bộ revision hay xử lý trường hợp message v42 đến trước v41.
- Chưa xác nhận refresh bất đồng bộ đã hoàn tất.
- Chưa ghi metrics/ACK và không tự retry nếu Redis bị lỗi.
- Chưa bảo vệ khỏi route definition không hợp lệ.

Đây là **điểm nối giữa signal cluster và Spring event cục bộ**, không phải một sản phẩm “cluster synchronization” hoàn chỉnh. Một implementation sản xuất cần thêm các phần trên và integration tests.

### 9.1. Không block event loop khi đọc repository

Gateway Server WebFlux sử dụng mô hình reactive. Nếu control plane hoặc listener dùng JDBC, gọi mạng blocking hoặc `Thread.sleep()` trong Gateway filter/event-loop, có thể làm nghẽn request.

Khi xây custom repository:

- Nếu có driver reactive, dùng `Flux`/`Mono` và các API có backpressure phù hợp.
- Nếu phải dùng client blocking, cô lập công việc trên scheduler thích hợp và quản lý concurrency.
- Không gọi `block()` trong `GlobalFilter` hoặc thread Netty xử lý request.
- Không tạo subscription `subscribe()` độc lập không được giám sát để giả vờ đã hoàn tất publish/refresh.
- Bảo đảm errors của repository được quan sát và không làm route cache chuyển sang trạng thái không hợp lệ một cách âm thầm.

## 10. Atomicity khi cập nhật nhiều route

Một thay đổi thực tế có thể cần cập nhật **nhiều routes cùng lúc**:

~~~text
v41:
  /api/catalog/**  -> lb://CATALOG-V1
  /api/orders/**   -> lb://ORDER-V1

v42:
  /api/catalog/**  -> lb://CATALOG-V2
  /api/orders/**   -> lb://ORDER-V2
~~~

Nếu control plane `save` route catalog trước và order sau, một node có thể refresh ở giữa và nhìn thấy:

~~~text
catalog = V2
orders  = V1
~~~

Đó là **mixed-version snapshot**. Một repository hỗ trợ CRUD từng route **không tự đảm bảo cập nhật toàn bộ tập routes một cách nguyên tử**.

Các hướng thiết kế:

1. **Versioned snapshots:** ghi một tập definitions có revision v42, xác minh hoàn chỉnh rồi chuyển con trỏ active revision từ v41 sang v42 theo thao tác nguyên tử.
2. **Stage → validate → activate:** chuẩn bị definitions ở namespace chưa active; chỉ sau khi kiểm thử mới cho các node chọn phiên bản mới.
3. **Transactional DB/outbox:** commit definitions + bản ghi outbox trong cùng transaction (nếu source cho phép), rồi phát event; tránh commit xong nhưng không có notification.
4. **Khống chế route order/precedence:** route mới không được vô tình khớp traffic trước khi được cho phép active.
5. **Rollback theo revision:** có thể quay lại snapshot v41 đã biết tốt, không phải đoán và sửa tay từng route.

Các biện pháp trên là **kiến trúc bổ sung**. `RedisRouteDefinitionRepository` cơ bản **không mặc nhiên cung cấp snapshot transaction/version switching cho mọi route**; nếu yêu cầu atomic rollout, phải thiết kế control plane/repository bổ sung hoặc kiểm soát quy trình deployment.

### 10.1. Race giữa nhiều admin

Nếu hai admin cùng thay đổi route:

~~~text
Admin A đọc v41 -> muốn v42: đổi catalog
Admin B đọc v41 -> muốn v42: đổi orders
Admin A ghi route catalog
Admin B ghi toàn bộ snapshot cũ + orders -> mất thay đổi catalog
~~~

Cần **optimistic concurrency** (revision/ETag/compare-and-set) hoặc khóa giao dịch. Nếu revision gốc không khớp latest, trả conflict và yêu cầu rebase/review lại; không dùng “last write wins” cho routing/security nếu chưa có chính sách rõ ràng.

### 10.2. Route được chọn trước refresh đang bay

Một request đã được Gateway chọn route cũ có thể tiếp tục xử lý sau khi v42 được áp dụng. Đó là tính chất của in-flight requests. Vì vậy:

- Không dùng route refresh để giả định chặn tức thì mọi request cũ đã bắt đầu.
- Nếu cần ngắt khẩn cấp quyền truy cập, thực thi policy ở tầng auth/upstream/firewall theo yêu cầu.
- Với migration API không tương thích, giữ backend cũ đủ lâu cho các request đang chạy hoặc thực hiện canary/staged rollout.
- Không xóa route cũ khi rollback chưa có đường khôi phục đã kiểm thử.

## 11. Những đường cập nhật route khác và giới hạn của chúng

### 11.1. Git/Config Server

Một nhóm có thể lưu route YAML ở Git và phân phối bằng Spring Cloud Config. Đây là **shared configuration source**, nhưng:

- Các Gateway replicas phải nhận/tải lại config theo cơ chế riêng.
- Cập nhật Git không có nghĩa mọi Gateway tự refresh ngay.
- Nếu cấu hình properties thay đổi, phải kiểm tra cơ chế binding/reload và **route cache refresh** tương ứng với phiên bản.
- Không tự giả định `/actuator/refresh` của config client đồng nghĩa đã đồng bộ gateway routes ở mọi node.
- Cần version commit và khả năng rollback.

Mô hình GitOps phù hợp nếu thay đổi theo lần triển khai, có review/approval và không cần cập nhật route trong vài mili giây.

### 11.2. DiscoveryClient Route Definition Locator

Tính năng tạo route từ DiscoveryClient có thể sinh routes cho các service đã đăng ký. **Đó không phải shared route repository**, dù cùng dùng tên “discovery”.

Nó giải quyết câu hỏi **có route nào được sinh từ danh sách service**; còn LoadBalancer sau đó chọn instance cho `lb://`. Nếu dùng discovery locator, cần kiểm soát các service được phép public và route rewrite/filter/security. Không tự bật locator rồi công khai toàn bộ service registry lên Internet.

### 11.3. Java DSL và RouteLocator bean

Route được định nghĩa bằng `@Bean RouteLocator` là cấu hình do code tạo, không phải một bản ghi được quản lý tùy ý bởi `RouteDefinitionRepository`. Thay đổi Java code thông thường cần build/deploy, hoặc logic riêng để cung cấp routes mới.

Không mong `DELETE /actuator/gateway/routes/{id}` xóa được route hard-coded bằng Java DSL như một route động đã lưu qua writer.

### 11.4. Kubernetes ConfigMap có tự refresh không?

Mount ConfigMap/Secret thay đổi ở filesystem **không có nghĩa** Spring Boot tự parse và áp dụng route mới, hay Gateway tự xóa cache. Dù Kubernetes có thể cập nhật volume, ứng dụng cần một **reload mechanism** được chứng minh hoạt động trên phiên bản đang dùng; rollout/restart có thể đơn giản và đáng tin cậy hơn trong một số trường hợp.

Đừng dùng environment variable được inject từ ConfigMap rồi kỳ vọng tiến trình đang chạy tự có giá trị mới. Pod thường cần rollout để thấy env mới.

## 12. Giám sát convergence và độ lệch giữa replicas

Để vận hành được, hệ thống nên theo dõi **hai khái niệm phiên bản**:

- **Desired revision:** revision mới nhất được control plane chấp thuận và công bố trong shared store.
- **Applied revision:** revision mà **từng Gateway replica xác minh** đã tải/biên dịch và phục vụ đúng.

Ví dụ dashboard:

| Replica | Desired | Applied | Tuổi lệch | Trạng thái |
| --- | ---: | ---: | --- | --- |
| gateway-a | 42 | 42 | 0 s | Đã hội tụ |
| gateway-b | 42 | 42 | 0 s | Đã hội tụ |
| gateway-c | 42 | 41 | 75 s | Chưa hội tụ, cần điều tra |

Đây là **dashboard ứng dụng tự xây**, không phải một endpoint mặc định của Spring Cloud Gateway.

### 12.1. Cần đo những gì?

- Route definition count và effective route count trên mỗi node.
- Desired/applied revision, thời điểm refresh gần nhất và kết quả success/failure.
- Convergence lag theo thời gian, số node stale, time-to-convergence p95/p99.
- Số event route-change nhận, bỏ qua vì trùng, xử lý lỗi hoặc mất kết nối bus.
- Lỗi build route vì predicate/filter không tồn tại hoặc URI sai.
- 404/5xx theo route ID/node sau rollout và các thay đổi upstream traffic.
- Lỗi Redis connection/latency, source read failures.
- Route config audit: ai thay đổi, revision nào, lý do, rollback ID.

Spring Cloud Gateway có thể cung cấp metrics cho **số route definitions** khi tích hợp Actuator/metrics đúng phiên bản. Nhưng **desired/applied revision và ACK cluster** vẫn cần instrument riêng.

Không gắn toàn bộ route ID, raw URI động, message ID hay request ID với cardinality không giới hạn vào mọi metric label. Quan sát route ID ổn định được kiểm soát và dùng log/audit cho chi tiết có kiểm soát truy cập.

### 12.2. Chỉ kiểm tra Redis là chưa đủ

Một health check chỉ đọc Redis và trả “route v42 tồn tại” chưa chứng minh **`CachingRouteLocator` của node đã áp dụng v42**.

Một health/convergence endpoint nội bộ nên ghi nhận revision **sau khi** verify effective route snapshot. Nếu không thể xác minh bằng route metadata/Actuator trên phiên bản đang dùng, có thể dùng **synthetic request** đi qua đúng replica và kiểm tra hành vi thực tế.

Một `200 OK` của local refresh hoặc một log “received v42” không phải applied ACK.

## 13. Kiểm thử thủ công ba replicas

### 13.1. Môi trường minh họa

Giả sử có:

- `gateway-a`, `gateway-b`, `gateway-c` chạy cùng version binary.
- Các admin ports chỉ truy cập được từ mạng thử nghiệm: `18081`, `18082`, `18083`.
- Tất cả dùng Redis route-definition repository chung.
- Một mock `ORDER-SERVICE` hoặc upstream HTTP thực sự phục vụ `/orders/42`.
- Actuator quyền ghi đã được bật **chỉ trong staging** hoặc qua cơ chế quản trị an toàn.
- Redis/Kafka bus nếu kiểm thử đồng bộ tự động; bước đầu có thể refresh thủ công từng node.

Trước khi thay đổi, truy vấn danh sách route trên **từng node** (không qua public load balancer):

~~~bash
curl -sS http://localhost:18081/actuator/gateway/routes
curl -sS http://localhost:18082/actuator/gateway/routes
curl -sS http://localhost:18083/actuator/gateway/routes
~~~

**Các URL localhost bên trên chỉ dành cho port-forward/proxy test** vào management ports đã được bảo vệ. Chúng không phải ví dụ nên mở các Actuator admin ports public. Trong môi trường có auth, phải gửi credential qua kênh an toàn; không hạ auth xuống anonymous để test.

### 13.2. Thử write vào một replica

Tạo route động qua A bằng control plane hoặc API Actuator đã bảo vệ. Xác nhận nó thực sự được ghi vào Redis repository. Sau đó:

1. Refresh **chỉ A**.
2. Gọi các GET endpoints ở A/B/C.
3. Quan sát A đã có route mới, B/C có thể vẫn dùng snapshot cũ.
4. Refresh B và C.
5. Xác nhận A/B/C cuối cùng cùng route definitions và behavior.

Test này chứng minh sự khác biệt giữa **shared persistence** và **per-instance cache invalidation**.

### 13.3. Thử đồng bộ qua bus

Thiết lập event consumer riêng trên từng replica và control plane:

1. Commit `revision=42` vào shared store.
2. Phát một event `routes.changed(v42)`.
3. Cả A/B/C nhận event, trigger local refresh.
4. Convergence monitor đợi **ACK applied v42** của cả ba.
5. Kiểm tra synthetic request qua từng node với path và header thay đổi theo v42.
6. Đo time-to-convergence, số lần đọc Redis và lỗi build route.

Không chỉ kiểm tra message broker “đã publish thành công”: cần đo **effective route behavior** của từng replica.

### 13.4. Ma trận tình huống cần test

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| M1 | Thêm route v42 ở A với Redis repository | Definition mới có trong store chung |
| M2 | Refresh A nhưng chưa refresh B/C | Có thể quan sát effective routes khác nhau |
| M3 | Refresh qua URL public load-balanced hai lần | Không đảm bảo đã trúng cả hai node |
| M4 | Gọi refresh trực tiếp từng node | Mỗi node có thể tải lại definitions từ chung source |
| M5 | Phát event v42 một lần | Các node đang online nhận/tự refresh theo bus |
| M6 | Replica C offline khi phát v42 rồi online | Startup/reconcile đưa C về latest revision |
| M7 | Event v42 bị gửi trùng | Consumer idempotent, không phá cache |
| M8 | Event v41 đến **sau** v42 | Không rollback về v41 ngoài ý muốn |
| M9 | Redis tạm không sẵn sàng | Có alert/error; hành vi cache rõ theo phiên bản |
| M10 | Route sử dụng CustomFilter chỉ có ở A | B/C báo apply failure; không giả vờ converged |
| M11 | Hai admin cùng sửa revision 41 | Optimistic lock/conflict, không lost update |
| M12 | Cập nhật hai routes liên quan | Không phục vụ mixed-version snapshot ngoài policy |
| M13 | Thay `uri` đến host không được phép | Validation từ chối SSRF/sai scheme |
| M14 | Xóa route động | Store và cache tất cả node cuối cùng không còn route |
| M15 | Rollback v42 về v41 | Toàn cluster hội tụ về revision đã biết tốt |
| M16 | Request đang xử lý khi refresh | Không kỳ vọng ngắt/đổi route giữa request |
| M17 | Một node refresh báo 200 nhưng route không hợp lệ | Không ACK applied trước khi kiểm chứng effective routes |
| M18 | Redis và route caches có duplicate IDs | Phát hiện conflict và xử lý nguồn sở hữu ID |

### 13.5. Vì sao cần assert hành vi, không chỉ count?

Một cluster có thể có cùng **12 routes** nhưng A trỏ `/api/orders` tới `ORDER-V2`, B trỏ tới `ORDER-V1`; route count giống nhau nhưng behavior sai.

Integration test nên so sánh:

~~~text
expectedRevision: 42
expectedRouteIds: [dyn-orders-api, dyn-catalog-api]
expectedPath: /api/orders/42
expectedUpstreamPath: /orders/42
expectedTargetService: ORDER-SERVICE
expectedAuthPolicy: protected
expectedResultAcrossNodes: tương đương theo contract
~~~

Tránh dùng response header chứa topology nhạy cảm ở production chỉ để biết node nào xử lý. Trong staging, có thể dùng một header debug nội bộ đã được xác thực hoặc correlation/tracing để xác định replica khi cần.

## 14. Khi Redis hoặc message bus lỗi: failover và last-known-good

### 14.1. Redis không sẵn sàng trong lúc refresh

Nếu Redis timeout khi một node đang reload routes:

- Tùy implementation/version, refresh có thể báo lỗi, giữ cache cũ, cache rỗng hoặc bị xử lý theo cách khác.
- **Không được mặc định** khẳng định Gateway luôn giữ route cũ hoặc luôn trả 503.
- Phải test hành vi ở release thật, kể cả sau restart khi local cache có thể chưa được tạo.
- Không tự cho một thay đổi chưa được xác thực đi vào route cache chỉ để “giữ service sống”.
- Ghi rõ policy của đội vận hành: tiếp tục phục vụ **last-known-good đã xác minh**, đưa node out of pool hay fail closed khi không bảo đảm chính sách bảo mật.

**Last-known-good** là một **chiến lược được thiết kế**; nó không mặc định là persistence guarantee của `RedisRouteDefinitionRepository`. Nếu cần khả năng phục hồi sau cold start, phải có nguồn snapshot đã ký/kiểm tra và cơ chế rollback an toàn.

### 14.2. Message bus mất event

Nếu Kafka consumer tụt lag hoặc Redis Pub/Sub subscriber offline:

- Dùng periodic reconciliation so desired và applied revision.
- Nếu bus hỗ trợ durable offset/ack, lưu và quản lý offset theo đúng semantics.
- Không phụ thuộc vào thứ tự event trên nhiều partition/topic khi nó không được bảo đảm.
- Xử lý trùng message idempotent.
- Có cảnh báo nếu route ở một node stale vượt SLA.
- Kiểm tra khả năng làm mới khi node tái khởi động sau một thời gian dài offline.

### 14.3. Refresh lỗi giữa chừng và rollback

Một route definition có filter factory không tồn tại trên một node có thể làm lỗi quá trình dựng route. Tài liệu Actuator bản mới mô tả rằng một số lỗi trong quá trình refresh bất đồng bộ sẽ không thay đổi những route cũ; nhưng **không nên lấy điều đó làm bảo đảm tổng quát cho mọi custom repository và mọi release**.

Quy trình rollback:

1. Xác định revision lỗi và nguyên nhân (route, filter, URI, dependency).
2. Tái kích hoạt snapshot đã biết tốt (ví dụ v41) theo cơ chế version/transaction.
3. Phát `routes.changed(v41-rollback)` hoặc **revision mới** trỏ về nội dung v41 để tránh nhầm thứ tự event.
4. Mỗi replica refresh và xác minh apply.
5. Chỉ tuyên bố rollback xong khi các nodes mục tiêu hội tụ.
6. Giữ audit trail, không chỉnh/xóa history đã dùng cho điều tra.

**Một cách an toàn hơn là revision luôn tăng**, ví dụ v43 chứa nội dung rollback từ v41; do vậy consumer có thể xử lý monotonic revision mà không coi thông báo rollback là event cũ.

## 15. Security: route admin là bề mặt có thể thay đổi toàn bộ cổng vào

Một người có quyền thêm/sửa route có thể tạo ra hậu quả lớn hơn một thay đổi config thường:

- Định tuyến `/api/payments/**` sang host không thuộc tổ chức.
- Thêm `RewritePath`/header filter khiến authentication hoặc audit không hoạt động như mong muốn.
- Tạo route tới `127.0.0.1`, dải mạng nội bộ hoặc cloud instance metadata endpoint (SSRF).
- Công khai service nội bộ bằng predicate quá rộng.
- Ghi đè route ID, route order hoặc `Host` predicate, làm lưu lượng bị chuyển sang backend sai.
- Thêm filter gây lộ Authorization, cookie, token hoặc thông tin cá nhân.

### 15.1. Checklist validation ở control plane

- **RBAC và approval:** ai được đổi route nào, scope theo môi trường/namespace.
- **ID uniqueness:** không trùng route static/dynamic, owner rõ ràng.
- **URI allowlist:** chỉ cho schemes `http`, `https` hoặc `lb` đã được phê duyệt; kiểm tra service ID/domain, port và DNS/network policy.
- **Filter whitelist:** chỉ cho các GatewayFilterFactory và args đã được review, chặn header/token exfiltration.
- **Predicate checks:** kiểm soát `Path`, `Host`, `Method`, route order, độ rộng matching.
- **Compatibility:** filter/predicate factory phải tồn tại trên **tất cả binary versions** còn phục vụ.
- **Change validation:** schema, dry-run, test định tuyến, security regression.
- **Audit/rollback:** revision, author, approval, diff, thời gian áp dụng.
- **Network enforcement:** ngăn Gateway kết nối tùy tiện tới địa chỉ không được phép, dù route config bị sai.
- **Quản lý secrets:** route definitions/events không chứa raw credential, private key hay bearer token.

Không cho client public tự chọn target URI/host rồi lưu thành route. Route control plane phải là một **trust boundary**, được bảo vệ mạnh hơn endpoint nghiệp vụ thông thường.

### 15.2. Bảo vệ Actuator và Redis

- Tách management interface khỏi cổng public API hoặc giới hạn bằng firewall/network policy.
- Mặc định ưu tiên Actuator **read-only**; bật `unrestricted` chỉ khi có yêu cầu chính đáng, auth mạnh và scope phù hợp.
- Dùng TLS/mTLS khi qua mạng không đáng tin, không log token admin.
- Redis chỉ mở cho đúng Gateway/control-plane clients; dùng ACL, auth, encryption và backup/restore.
- Không dựa vào việc `/actuator/gateway/refresh` “khó đoán” để bảo vệ endpoint.
- Giới hạn tần suất refresh để tránh một actor gửi hàng nghìn sự kiện gây rebuild route liên tục.
- Không trộn dữ liệu rate-limit với route definitions trong cùng policy Redis ACL mà không có phân quyền rõ.

## 16. Tình huống thực tế: cập nhật route không restart cả cluster

Giả sử hệ thống có 3 Gateway replicas, Redis shared repository và route:

~~~text
Path:     /api/inventory/**
Route ID: dyn-inventory
Target:   lb://INVENTORY-SERVICE
Filter:   StripPrefix=1
Revision: 71
~~~

Nhóm phát triển muốn thêm một header chung cho upstream ở revision 72 mà không restart cả cụm.

**Kế hoạch rollout:**

1. Control plane nhận thay đổi và kiểm tra owner, target service, predicate/filter và auth impact.
2. Build candidate route revision 72; đảm bảo cả A/B/C đều có filter factory cần dùng.
3. Ghi route mới vào shared source có kiểm soát version, không tạo duplicate route ID.
4. Phát event `routes.changed(72)` sau commit.
5. A/B/C nhận event, kiểm tra latest revision, kích hoạt local `RefreshRoutesEvent`.
6. Mỗi node xác minh `dyn-inventory` có header behavior mới và không tạo route trùng.
7. Convergence monitor xác nhận cả ba applied 72; nếu C lỗi, không báo “deploy thành công 100%”.
8. Synthetic GET qua từng node xác nhận path/headers/status phù hợp.
9. Giám sát 404/5xx, latency, upstream request và auth/rate-limit sau thay đổi.
10. Nếu lỗi, phát **revision 73** khôi phục nội dung 71, refresh và xác minh cả ba nodes.

**Tiêu chí thành công:** không chỉ “Redis chứa route mới”, mà là **cả ba Gateway nodes cung cấp cùng hành vi hợp đồng** và có thể rollback nhanh, an toàn.

### 16.1. Một số câu hỏi kiểm tra kiến thức

1. Vì sao `InMemoryRouteDefinitionRepository` không phù hợp để chia sẻ route giữa ba JVM?
2. Khi dùng chung Redis, tại sao B vẫn có thể giữ route cũ?
3. `RefreshRoutesEvent` tác động tới JVM nào? Vì sao cần event bus hoặc fanout?
4. `POST /actuator/gateway/refresh` trả 200 có chứng minh cluster hội tụ không?
5. Nếu node C offline khi phát Pub/Sub event, cơ chế nào giúp C cập nhật sau khi online?
6. Có thể dùng `GET /actuator/gateway/routes` để biết route đã được dựng, nhưng làm sao chứng minh revision đã áp dụng?
7. Vì sao route count giống nhau chưa chắc route behavior giống nhau?
8. Nếu hai admin cùng sửa routes, làm sao tránh lost update?
9. Vì sao cần thử filter compatibility trước khi cập nhật ở cluster rolling upgrade?
10. Làm thế nào rollback mà không phá logic bỏ qua event cũ của consumer?

## 17. Checklist triển khai production

- [ ] Đã phân biệt **desired route definitions** và **effective route cache** của từng replica.
- [ ] Nguồn route động dùng chung thực sự hoạt động (Redis/DB), không chỉ in-memory.
- [ ] Redis repository được bật bằng property đúng version, dependency reactive Redis đầy đủ.
- [ ] Route IDs có ownership duy nhất; không trùng YAML, Java DSL, discovery và Redis.
- [ ] Mỗi replica có cơ chế local refresh và consumer notification riêng.
- [ ] Không dùng URL public load-balanced để giả định đã refresh mọi replica.
- [ ] Bus/event notification có revision, dedup và xử lý out-of-order.
- [ ] Có periodic reconciliation hoặc durable delivery cho node offline/mất event.
- [ ] Control plane chỉ phát event sau khi store commit.
- [ ] Có optimistic concurrency hoặc transactional snapshot khi nhiều người sửa.
- [ ] Nhiều route liên quan có chiến lược atomic/staged activation để tránh mixed-version.
- [ ] Applied revision được xác minh sau khi dựng effective routes; không ACK dựa vào HTTP 200.
- [ ] Có convergence monitor, alert stale nodes, route diff và metrics refresh failures.
- [ ] Test outage Redis/bus, cold start, rollback, duplicated events, rolling binary versions.
- [ ] Có last-known-good/rollback policy được test, không giả định Gateway mặc định giữ cache cũ.
- [ ] Actuator management endpoint không public, phân quyền chặt; mặc định read-only.
- [ ] URI/predicates/filter arguments được validate để chống SSRF và bypass auth.
- [ ] Event/route metadata không chứa tokens, cookies, secrets hoặc dữ liệu người dùng.
- [ ] Đã thử request qua **từng node** sau rollout và trước khi tuyên bố hội tụ.
- [ ] Thứ tự route, `lb://`, service discovery và filter chain hoạt động đúng sau refresh.
- [ ] In-flight requests và đường rollback tương thích backend cũ/mới.

## 18. Tổng kết và tài liệu tham khảo

**Chia sẻ routes và đồng bộ refresh giữa nhiều bản sao là hai bài toán riêng.** `RedisRouteDefinitionRepository` hoặc một nguồn config chung có thể cung cấp cùng **desired definitions** cho A/B/C, nhưng từng Gateway vẫn có **effective route cache cục bộ**. `RefreshRoutesEvent` và `POST /actuator/gateway/refresh` chỉ yêu cầu làm mới ở instance nhận event/lệnh.

Muốn cluster hội tụ đáng tin, cần **control plane** ghi route đã validate vào shared store, **signal** đến từng replica, **local refresh**, **kiểm chứng applied revision**, **ACK**, **reconciliation** khi mất event và **rollback có version**. Nếu thay đổi nhiều routes cùng lúc, cần xem thêm atomicity và precedence để tránh mixed-version. Đó là nền tảng cho Gateway vừa định tuyến động vừa bảo vệ an toàn các tính năng xác thực, rate limiting, retry, circuit breaker, service discovery, TLS và observability.

Tài liệu chính thức để đối chiếu theo phiên bản:

- [Spring Cloud Gateway Server WebFlux — Sharing Routes between multiple Gateway instances](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/sharing-routes.html).
- [Spring Cloud Gateway Server WebFlux — Actuator API, refresh và quản lý route](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Cloud Gateway Server WebFlux — Configuration và RouteDefinitionLocator](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/configuration.html).
- [Spring Cloud Gateway — Configuration Properties, Redis repository namespace](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway 4.2 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/actuator-api.html).
