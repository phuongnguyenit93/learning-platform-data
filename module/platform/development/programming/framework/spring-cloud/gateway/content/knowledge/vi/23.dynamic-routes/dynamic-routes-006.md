# RefreshRoutesEvent và làm mới bộ nhớ đệm tuyến

## 1. Vấn đề: cấu hình tuyến đã đổi, tại sao Gateway vẫn đi đường cũ?

Trong hệ thống microservices, **Spring Cloud Gateway Server WebFlux** thường là điểm vào chung: nhận request, dùng **route predicate** chọn tuyến, thực thi **filter chain**, biến đổi path/header, có thể tìm backend bằng `lb://service-id` rồi proxy request tới instance được chọn. Một tuyến có thể được cấu hình cố định từ `application.yml` hoặc lấy từ kho cấu hình động.

Giả sử ban đầu Gateway có tuyến:

~~~yaml
id: catalog-live
uri: http://localhost:9191
predicates:
  - Path=/api/catalog/**
filters:
  - StripPrefix=1
~~~

Người vận hành sửa đích thành `http://localhost:9192` trong kho định nghĩa tuyến. Dù kho đã chứa giá trị mới, một request sau đó vẫn có thể đến cổng **9191**. Lý do là **RouteDefinition nguồn dữ liệu** và **danh sách Route runtime đang được Gateway lưu đệm** không phải cùng một đối tượng.

Spring Cloud Gateway WebFlux cung cấp **`RefreshRoutesEvent`** để báo cho các thành phần quản lý route rằng cần nạp lại danh sách tuyến, đặc biệt là `CachingRouteLocator`. Đối với API quản trị, thao tác tương ứng là **`POST /actuator/gateway/refresh`** khi Gateway Actuator được bật và cho phép ghi.

Đây là chủ đề bài **“RefreshRoutesEvent và làm mới bộ nhớ đệm tuyến”**, thuộc chương **Tuyến động** của module **SPRING_CLOUD_GATEWAY**. Mục tiêu là hiểu **nguồn định nghĩa tuyến → chuyển đổi thành tuyến runtime → cache → refresh**, chứ không chỉ học một lệnh cURL. Các vấn đề bảo mật, rate limiting, circuit breaker, retry, TLS và observability cũng cần được giữ đúng khi route thay đổi.

Sau bài học, bạn có thể:

1. Phân biệt `RouteDefinition`, `RouteLocator` và `CachingRouteLocator`.
2. Giải thích `RefreshRoutesEvent` làm gì và **không làm gì**.
3. Tạo/xóa một tuyến động trong lab rồi làm mới cache **không restart Gateway**.
4. Phát sự kiện từ Java **sau khi thao tác lưu/xóa định nghĩa tuyến hoàn tất**.
5. Kiểm chứng tuyến runtime bằng Actuator, request thực tế và log backend.
6. Phân tích refresh bất đồng bộ, lỗi cấu hình, nhiều Gateway replica và các yêu cầu bảo mật production.

> **Phạm vi:** Bài nói về **Gateway Server WebFlux**; Gateway Server MVC có cách triển khai và API cụ thể khác. Ví dụ quản trị chỉ dùng trong **môi trường local được cô lập**. Không công khai chức năng sửa tuyến hoặc Actuator ghi route lên Internet.

## 2. Ba tầng: RouteDefinition, Route runtime và route cache

Một lỗi vận hành phổ biến là đánh đồng việc **ghi xong cấu hình** với việc **request đã định tuyến theo cấu hình đó**. Trong Gateway WebFlux cần phân biệt:

| Tầng | Kiểu/thành phần tiêu biểu | Vai trò |
| --- | --- | --- |
| **Nguồn RouteDefinition** | `PropertiesRouteDefinitionLocator`, `DiscoveryClientRouteDefinitionLocator`, `RouteDefinitionRepository` | Cung cấp mô tả route: ID, URI, predicates, filters, order, metadata |
| **Route runtime** | `RouteDefinitionRouteLocator`, `RouteLocator` | Chuyển định nghĩa thành predicate/filter đã bind, sẵn sàng để chọn route |
| **Route cache** | `CachingRouteLocator` | Giữ danh sách routes runtime đã được dựng để các request không phải dựng lại toàn bộ mỗi lần |

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    Y["application.yml / Config Server"] --> RD["RouteDefinitionLocator(s)"]
    S["Repository: in-memory / Redis / DB"] --> RD
    D["Service discovery locator (nếu bật)"] --> RD
    RD --> C["RouteDefinitionRouteLocator<br/>bind predicates + filters"]
    J["RouteLocator Java DSL (nếu có)"] --> CO["Composite RouteLocator"]
    C --> CO
    CO --> CA["CachingRouteLocator<br/>route runtime cache"]
    CA --> M["RoutePredicateHandlerMapping"]
    M --> F["GatewayFilter chain"]
    F --> B["HTTP backend / lb://service"]
    E["RefreshRoutesEvent"] -.-> CA
~~~

Tên lớp và cách ghép các locator có thể khác đôi chút giữa các phiên bản; sơ đồ mô tả các trách nhiệm chính. Đặc biệt, **RouteDefinitionRepository** là một nguồn định nghĩa; `CachingRouteLocator` nằm ở tầng các **Route runtime**. Xóa một entry trong cache không tương đương xóa định nghĩa khỏi repository.

### 2.1. RouteDefinition chứa gì?

Một `RouteDefinition` thường có:

~~~text
id          = catalog-live
uri         = http://localhost:9191
predicates  = Path=/api/catalog/**
filters     = StripPrefix=1
order       = 0
metadata    = { group: "lab", revision: "v1" }
~~~

Đây chưa phải hàm predicate Java đã được tạo hay `GatewayFilter` đã sẵn sàng thực thi. Khi định nghĩa được chuyển thành `Route` runtime, Gateway cần tìm factory theo tên, bind args, kiểm tra cấu hình tương ứng, xây predicate và filter.

**Tuyến sai cấu hình có thể thất bại ở pha chuyển đổi.** Chẳng hạn `uri` không hợp lệ hoặc dùng `GatewayFilterFactory` không tồn tại có thể làm refresh gặp lỗi hoặc route không hoạt động như kỳ vọng. Do đó kiểm tra YAML/JSON đúng cú pháp **chưa đủ**.

### 2.2. Cache route giải quyết chi phí gì?

Nếu không có route cache, việc thu thập, chuyển đổi, sắp xếp các route definitions từ nhiều nguồn có thể phát sinh chi phí cho mỗi request. `CachingRouteLocator` cho phép request sử dụng tập tuyến runtime đã dựng sẵn.

**Hệ quả:** Thay đổi repository mà **không làm mới cache** có thể không làm thay đổi routing của các request mới. Ngược lại, chỉ refresh cache khi repository vẫn chứa dữ liệu cũ thường sẽ **nạp lại chính dữ liệu cũ**.

### 2.3. Cache route khác những cache nào?

| Bộ nhớ đệm | Nội dung | Làm mới route cache có xử lý nó không? |
| --- | --- | --- |
| `CachingRouteLocator` | Tập `Route` runtime | **Đúng phạm vi trực tiếp** của RefreshRoutesEvent |
| Discovery/registry cache | Danh sách `ServiceInstance`, metadata health | **Không tự bảo đảm** refresh đồng bộ cùng lúc |
| Spring Cloud LoadBalancer cache | Danh sách instance/tính toán supplier | Có vòng đời và policy riêng |
| DNS/JVM/HTTP client connection pool | Host lookup và kết nối | Không tự xóa khi route refresh |
| CORS configuration mapping | Chính sách CORS theo route/path | Có tương tác theo implementation/version, cần kiểm chứng |
| CDN/proxy/browser cache | HTTP response hoặc preflight | Không liên quan trực tiếp đến việc nạp routes |

Ví dụ: `uri: lb://orders-service` vẫn không đổi nhưng Eureka vừa thay instance. Vấn đề có thể nằm ở **discovery/LoadBalancer cache**, không phải định nghĩa route. Gửi `RefreshRoutesEvent` nhiều lần không nên được coi là giải pháp chắc chắn cho mọi sự cố cập nhật instance.

## 3. RefreshRoutesEvent: cơ chế, phạm vi và thời điểm

`RefreshRoutesEvent` là một **Spring application event** trong module Gateway WebFlux, thuộc package:

~~~java
org.springframework.cloud.gateway.event.RefreshRoutesEvent
~~~

Một thành phần trong cùng ứng dụng có thể yêu cầu làm mới bằng:

~~~java
applicationEventPublisher.publishEvent(
        new RefreshRoutesEvent(this));
~~~

Ở các dòng WebFlux được tài liệu mô tả, `CachingRouteLocator` nhận sự kiện và **nạp lại danh sách tuyến từ `RouteLocator` nguồn** để cập nhật cache; một số bản còn có `RefreshRoutesResultEvent` dành cho quan sát kết quả refresh. Cơ chế cụ thể của việc fetch/cache swap hoặc kết quả bất đồng bộ có thay đổi giữa các dòng, nên cần đối chiếu đúng source/release đang chạy.

~~~mermaid
sequenceDiagram
    participant A as Trusted admin / config change
    participant R as RouteDefinitionRepository
    participant P as ApplicationEventPublisher
    participant C as CachingRouteLocator
    participant L as RouteLocator nguồn
    participant G as Gateway request handling

    A->>R: save / delete RouteDefinition
    R-->>A: Mono hoàn tất
    A->>P: publish RefreshRoutesEvent
    P->>C: thông báo cần refresh
    C->>L: nạp, bind và sắp xếp routes
    L-->>C: danh sách Route runtime mới
    C-->>C: cập nhật route cache
    G->>C: request mới cần chọn route
    C-->>G: Route từ cache hiện hành
~~~

Đây là **thứ tự logic mong muốn**. Trong implementation reactive, bước cập nhật cache có thể chạy **bất đồng bộ** so với lời gọi `publishEvent(...)` hoặc response của endpoint. Không được suy rằng Java method phát event trả về hoặc HTTP 200 từ refresh **chắc chắn đồng nghĩa cache ở mọi replica đã chứa revision mới**.

### 3.1. Refresh không tự lưu định nghĩa

~~~java
publisher.publishEvent(new RefreshRoutesEvent(this));
~~~

**Không**:

- Tạo, cập nhật hay xóa `RouteDefinition` trong repository.
- Đọc lại mọi `application.yml` đã sửa trên đĩa rồi tự hot-reload mọi property.
- Đồng bộ sự kiện từ Gateway A sang Gateway B ở process/JVM khác.
- Xóa cache LoadBalancer, Redis, DNS hoặc HTTP response.
- Xác minh quyền của người gọi hay bảo đảm cấu hình mới không có lỗ hổng.

Thao tác đúng cho một route mới là **thay đổi nguồn định nghĩa rồi yêu cầu refresh**. Với Java `RouteDefinitionWriter`, cần đợi `Mono<Void>` của save/delete **hoàn tất** trước khi phát event.

### 3.2. Một response 200 từ Actuator nghĩa là gì?

Tài liệu chính thức ghi `POST /actuator/gateway/refresh` trả **200** và body rỗng khi endpoint xử lý yêu cầu refresh. Đó là thành công của **lời gọi quản trị**, không phải bằng chứng đã có route runtime mới.

Để xác nhận thật:

1. Gọi `GET /actuator/gateway/routes` qua kênh quản trị được bảo vệ, xem route runtime có revision mong muốn.
2. Gửi request nghiệp vụ mới khớp route, xác minh backend đích và filters.
3. Nếu có nhiều Gateway replica, thực hiện ở **từng replica** hoặc dùng điều phối có xác nhận.
4. Chỉ báo deployment thành công sau khi đạt điều kiện kiểm tra đầu cuối.

### 3.3. Nếu rebuild thất bại thì sao?

Tài liệu Actuator của Gateway nêu rằng nếu **refresh bất đồng bộ gặp lỗi**, thao tác không thay đổi danh sách route hiện có. Đây là mục tiêu giữ tập tuyến cuối cùng đang sử dụng thay vì thay bằng tập lỗi.

Tuy nhiên, **không được suy rằng mọi nguồn route/release có cùng hành vi “atomic”** ở mọi trường hợp race hoặc config bị thay đổi từng phần. Cần kiểm tra bản Gateway thực tế, log lỗi, bộ route cuối và phản hồi request khi xảy ra lỗi liên tiếp.

## 4. Bốn cách làm mới tuyến thường gặp

| Nguồn/cách cập nhật | Thao tác thay đổi | Cần thêm bước nào? |
| --- | --- | --- |
| Actuator quản lý route động | `POST/DELETE /actuator/gateway/routes/{id}` | Gọi `POST /actuator/gateway/refresh` theo tài liệu |
| Java qua `RouteDefinitionWriter` | `save/delete(Mono<...>)` | Phát `RefreshRoutesEvent` **sau completion**, xác minh runtime |
| Repository custom từ DB/Redis | Transaction commit/version thay đổi | Trigger refresh trên **mỗi Gateway replica** sau dữ liệu mới sẵn sàng |
| DiscoveryClient locator tự sinh tuyến | Registry/discovery source thay đổi | Theo cơ chế listener/refresh tương ứng; kiểm tra cả discovery cache và route cache |

**Sửa `application.yml` trên đĩa không mặc định được Gateway giám sát liên tục.** Khác với thao tác cập nhật repository, việc thay file local sau startup thường đòi hỏi cơ chế reload cấu hình riêng hoặc restart/deploy mới. Chỉ phát event không có nghĩa `ConfigurationProperties` được bind lại từ đĩa.

Các event liên quan Spring Cloud Config/RefreshScope hoặc discovery heartbeat có thể dẫn đến việc yêu cầu refresh routes trong cấu hình phù hợp, nhưng **không phải mọi sự kiện làm mới Spring configuration đều giống `RefreshRoutesEvent`**.

## 5. Chuẩn bị lab: Gateway, Actuator và backend echo

Lab sau dùng hai ứng dụng:

| Thành phần | Địa chỉ local | Vai trò |
| --- | --- | --- |
| Gateway WebFlux | `http://127.0.0.1:8080` | API công khai để thử routing |
| Gateway Actuator | `http://127.0.0.1:9090` | Chỉ quản trị trên loopback, được bật ghi **cho lab** |
| Backend A | `http://127.0.0.1:9191` | Echo instance ID/path/header |
| Backend B | `http://127.0.0.1:9192` | Cùng mã nguồn, trả instance ID khác |

Tất cả dùng loopback trên một máy. **Không dùng các cấu hình quản trị ghi bên dưới trên server có người ngoài truy cập.**

### 5.1. Dependency Gateway

Với một dự án Gateway Server WebFlux dòng mới, các dependency Maven tiêu biểu:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Một số dòng WebFlux 4.x cũ dùng starter `spring-cloud-starter-gateway`; chọn Spring Boot, Spring Cloud BOM và starter tương thích đúng release. Gateway Server MVC không dùng cùng cơ chế cấu hình. Không thêm Servlet MVC starter vào Gateway Server WebFlux chỉ để dùng Actuator.

Nếu khai báo **routes tĩnh** trong YAML, cần nhớ namespace:

- Gateway Server WebFlux **4.2.x/4.3.x**: `spring.cloud.gateway.routes`.
- Gateway Server WebFlux **5.x**: `spring.cloud.gateway.server.webflux.routes`.

Trong lab này, **không khai báo catalog-live trong routes YAML** vì muốn tạo/xóa nó qua repository động. Nếu cùng ID tồn tại từ nhiều nguồn, việc chọn route có thể không còn xác định như dự kiến.

### 5.2. application.yml của Gateway trong lab

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: dynamic-routes-lab

management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,gateway
~~~

Tài liệu Gateway 4.2/5.x mô tả actuator `gateway` mặc định **không bật quyền ghi**; cấu hình `management.endpoint.gateway.access=unrestricted` cùng `management.endpoints.web.exposure.include=gateway` cho phép gọi các API ghi/refresh trong những version được hướng dẫn. Tùy dòng Boot, còn có các cách cấu hình bật endpoint cũ như `management.endpoint.gateway.enabled=true`, nhưng cần theo **tài liệu chính xác** và không trộn các ví dụ tùy tiện.

**Vì sao tách cổng 9090 và bind 127.0.0.1?** Chỉ để lab không vô tình mở endpoint ghi route cho người khác trên mạng. Trong Docker/Kubernetes, cách bind/forward cổng có thể khác; production phải dùng management network riêng, xác thực/phân quyền quản trị, audit và giới hạn quyền ghi.

> Nếu endpoint trả **404/405/403**, hãy kiểm tra dependency Actuator, quyền `access`/exposure, Spring Security và management path/port trước khi quy lỗi cho `RefreshRoutesEvent`.

### 5.3. application.yml của backend echo

Tạo một Spring Boot WebFlux project backend có dependency `spring-boot-starter-webflux`:

~~~yaml
server:
  address: 127.0.0.1
  port: ${BACKEND_PORT:9191}

demo:
  instance: ${INSTANCE_ID:A}
~~~

File `src/main/java/demo/catalog/CatalogApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

File `src/main/java/demo/catalog/CatalogController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final String instanceId;

    public CatalogController(
            @Value("${demo.instance:A}") String instanceId) {
        this.instanceId = instanceId;
    }

    @GetMapping("/catalog/items/{id}")
    public Map<String, Object> item(
            @PathVariable String id,
            ServerHttpRequest request) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("instance", instanceId);
        body.put("itemId", id);
        body.put("method", request.getMethod().name());
        body.put("path", request.getPath().value());
        body.put("revision",
                request.getHeaders().getFirst("X-Route-Revision"));
        body.put("query", request.getURI().getRawQuery());
        return body;
    }
}
~~~

Chạy backend A/B bằng hai terminal trong **cùng project backend**, và Gateway trong terminal thứ ba:

~~~bash
# Backend A, terminal 1
BACKEND_PORT=9191 INSTANCE_ID=A ./mvnw spring-boot:run

# Backend B, terminal 2
BACKEND_PORT=9192 INSTANCE_ID=B ./mvnw spring-boot:run

# Gateway, terminal 3 trong project Gateway
./mvnw spring-boot:run
~~~

Đây là cú pháp Bash. Với PowerShell, trong terminal A đặt `$env:BACKEND_PORT="9191"` và `$env:INSTANCE_ID="A"`, trong terminal B đặt các giá trị tương ứng 9192/B, sau đó mỗi terminal chạy `.\mvnw.cmd spring-boot:run`.

Kiểm tra backend trực tiếp:

~~~bash
curl -i "http://127.0.0.1:9191/catalog/items/42"
curl -i "http://127.0.0.1:9192/catalog/items/42"
~~~

Kỳ vọng lần lượt có JSON `"instance":"A"` và `"instance":"B"`. Nếu backend không hoạt động, hãy sửa backend trước khi kiểm tra route refresh.

## 6. Lab Actuator: tạo tuyến, refresh, đổi đích và xóa tuyến

### 6.1. Kiểm tra trạng thái trước khi tạo tuyến

Trên Gateway chưa khai báo route `/api/catalog/**`, chạy:

~~~bash
curl -i "http://127.0.0.1:8080/api/catalog/items/42"

# Kiểm tra routes runtime qua cổng quản trị loopback:
curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"
~~~

Với request đầu tiên, kỳ vọng **404** nếu không có route/handler khác. Danh sách runtime chưa có `catalog-live`. Điều này là baseline để so sánh; **404 không phải lỗi của RefreshRoutesEvent**.

### 6.2. Tạo RouteDefinition trong repository nội bộ

Tài liệu Gateway Actuator 5.0 nêu API `POST /actuator/gateway/routes/{id}` nhận định nghĩa route với `predicates` và `filters` dạng **shortcut DSL strings**, không phải nguyên JSON mà GET route runtime trả về.

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live" \
  -H "Content-Type: application/json" \
  --data-binary '{
    "predicates": ["Path=/api/catalog/**"],
    "filters": [
      "StripPrefix=1",
      "AddRequestHeader=X-Route-Revision,v1"
    ],
    "uri": "http://127.0.0.1:9191",
    "order": 0,
    "metadata": {
      "group": "lab",
      "revision": "v1"
    }
  }'
~~~

Theo API được tài liệu mô tả, thao tác tạo thành công trả **201 Created**. Đây là thao tác cập nhật **nguồn định nghĩa tuyến mà Actuator quản lý** trong process đang nhận lệnh, **chưa phải bằng chứng** cache của Gateway đã được làm mới.

**Chú ý:** Nếu dùng PowerShell, cách quoting JSON bằng dấu nháy đơn và `curl` alias có thể khác Bash. Dùng `curl.exe` hoặc chuẩn bị JSON literal/here-string theo PowerShell rồi gửi tới đúng URL quản trị.

### 6.3. Yêu cầu refresh cache

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"
~~~

Tài liệu chính thức cho biết endpoint refresh trả **200 OK**, không có body khi nhận yêu cầu thành công. Refresh được thực hiện qua cơ chế sự kiện/cache của Gateway và có thể **bất đồng bộ**: không suy rằng request nghiệp vụ ngay trong cùng một mili giây đã nhìn thấy tuyến mới.

Sau khi request refresh kết thúc, kiểm tra tập route runtime **và** gọi thử request:

~~~bash
# Xem tuyến đã materialize:
curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"

# Có thể xem trực tiếp route ID, tùy format response theo version:
curl -i \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"

# Request mới đi qua route:
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?lang=vi"
~~~

Response nghiệp vụ **minh họa**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"instance":"A","itemId":"42","method":"GET","path":"/catalog/items/42","revision":"v1","query":"lang=vi"}
~~~

Đối chiếu ba điểm:

1. Có route ID `catalog-live` trong danh sách runtime.
2. Backend thấy path `/catalog/items/42`, tức `StripPrefix=1` hoạt động.
3. Backend thấy header `X-Route-Revision: v1` qua trường `revision`, và `instance=A` xác nhận đích cổng 9191.

Nếu response vẫn 404 ngay sau refresh, hãy kiểm tra log và thử đọc lại route runtime trước khi kết luận lỗi. Không dùng vòng lặp vô hạn để “đợi” route mới; một bộ deploy nên có timeout hữu hạn và quyết định rollback nếu không đạt.

### 6.4. Phân biệt GET routedefinitions và GET routes

Hai endpoint có mục đích khác nhau:

| Endpoint | Quan sát | Ý nghĩa |
| --- | --- | --- |
| `GET /actuator/gateway/routedefinitions` | Các định nghĩa route nguồn ở nơi endpoint hỗ trợ | Phản ánh những gì các RouteDefinitionLocator cung cấp |
| `GET /actuator/gateway/routes` | Danh sách `Route` runtime | Phản ánh kết quả materialization/route cache mà Gateway dùng |
| `GET /actuator/gateway/routes/{id}` | Một route cụ thể | Có thể khác định dạng JSON dùng khi POST tạo route |
| `POST /actuator/gateway/refresh` | Yêu cầu nạp lại route cache | Không phải lệnh ghi/xóa RouteDefinition |

Một route definition có thể **đã có trong nguồn** nhưng chưa xuất hiện hoặc chưa có revision mong muốn ở **runtime**. Ngược lại, runtime có thể còn route cũ nếu repository thay đổi mà refresh chưa xảy ra. Đây là cách nhìn trực tiếp nhất để phân biệt lỗi ở tầng nguồn với lỗi ở tầng cache.

### 6.5. Làm mới chọn lọc theo metadata

Tài liệu Gateway WebFlux 4.2/5.0 có mô tả refresh chọn lọc bằng query parameter `metadata`, gồm các cặp `key:value`. Trong lab, tuyến có metadata `group: lab`:

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh?metadata=group:lab"
~~~

Tính năng này nhằm làm mới những routes có metadata phù hợp thay vì yêu cầu cập nhật toàn bộ. Tuy nhiên:

- Metadata được dùng để **chọn nhóm route**, **không phải quyền truy cập** hay điều kiện phân quyền.
- Cần xem **đúng version** để chắc cách lọc, trình tự bất đồng bộ và hành vi khi metadata đổi.
- Nếu xóa một route hoặc chuyển route từ nhóm này sang nhóm khác, cách refresh chọn lọc có thể không phải lựa chọn dễ xác minh nhất; **full refresh** là mặc định an toàn hơn cho bài lab.
- Khi thay đổi đồng thời nhiều tuyến liên quan nhau, vẫn phải có cơ chế kiểm soát revision và xác nhận sau refresh.

### 6.6. Đổi đích từ backend A sang backend B

Với API Actuator quản lý route được tài liệu Gateway 5.0 mô tả, **đừng POST trùng một ID đang tồn tại**: tài liệu cảnh báo thao tác đó có thể tạo route definition trùng và gây lỗi khi truy vấn routes. Để sửa route qua API này, hãy **xóa định nghĩa cũ, tạo định nghĩa mới rồi refresh**.

~~~bash
# 1) Xóa RouteDefinition được Actuator quản lý
curl -i -X DELETE \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"

# 2) Tạo lại với URI và revision khác
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live" \
  -H "Content-Type: application/json" \
  --data-binary '{
    "predicates": ["Path=/api/catalog/**"],
    "filters": [
      "StripPrefix=1",
      "AddRequestHeader=X-Route-Revision,v2"
    ],
    "uri": "http://127.0.0.1:9192",
    "order": 0,
    "metadata": {
      "group": "lab",
      "revision": "v2"
    }
  }'

# 3) Yêu cầu nạp lại cache
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"

# 4) Xác minh end-to-end
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?lang=vi"
~~~

Sau khi refresh hoàn tất, kỳ vọng request mới đến **backend B** và JSON có `"revision":"v2"`. Việc chuyển đích thành công chứng minh Gateway đã **nạp lại route từ nguồn**, không chỉ restart backend.

**Cảnh báo:** Chuỗi DELETE → POST **không phải một giao dịch cập nhật nguyên tử**. Nếu có refresh khác chen vào giữa, route có thể tạm biến mất; nếu POST thất bại, nguồn định nghĩa đang thiếu route. Vì thế, cách này phù hợp **lab Actuator**, không phải thiết kế triển khai production cần zero-downtime.

Trong production, nên dùng repository có thao tác cập nhật theo phiên bản (hoặc giao dịch), kiểm tra tính hợp lệ trước commit, rồi mới phát refresh một cách điều phối. Với những thay đổi nhiều routes phải đi cùng nhau, hãy thiết kế **bản snapshot cấu hình/version** để tránh trạng thái nửa cũ nửa mới.

### 6.7. Xóa tuyến và kiểm chứng

~~~bash
curl -i -X DELETE \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"

curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"

curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"
curl -i "http://127.0.0.1:8080/api/catalog/items/42"
~~~

Sau refresh hoàn tất, nếu không có tuyến/handler khác khớp `/api/catalog/**`, request phải về **404**. Nếu vẫn thấy route trong cache, cần điều tra refresh bất đồng bộ, nguồn định nghĩa khác hoặc có nhiều Gateway replicas.

**Giới hạn Actuator:** Theo tài liệu Gateway 5.0, routes được định nghĩa trực tiếp trong `application.yml` hoặc Java `@Bean` không thể bị xóa tùy ý qua `DELETE /actuator/gateway/routes/{id}` như routes do Actuator tạo; API có thể trả 404 đối với loại route này. Đừng xóa/refresh nhiều lần để cố “xóa” một cấu hình vốn do YAML sở hữu.

## 7. Java: lưu RouteDefinition rồi mới phát RefreshRoutesEvent

Tương đương thao tác Actuator, một ứng dụng có thể có luồng **quản trị tuyến đáng tin** sử dụng API Gateway WebFlux:

~~~text
Authorized route change
   → validate route + destination allowlist
   → RouteDefinitionWriter.save/delete(...)
   → đợi Mono hoàn tất
   → ApplicationEventPublisher.publishEvent(RefreshRoutesEvent)
   → kiểm tra Route runtime và request nghiệp vụ
~~~

### 7.1. Hai giao diện cần biết

~~~java
// Các chữ ký khái niệm của API Gateway WebFlux
public interface RouteDefinitionLocator {
    Flux<RouteDefinition> getRouteDefinitions();
}

public interface RouteDefinitionWriter {
    Mono<Void> save(Mono<RouteDefinition> route);
    Mono<Void> delete(Mono<String> routeId);
}
~~~

`RouteDefinitionRepository` kế thừa cả **locator** và **writer**, nên có thể vừa cung cấp định nghĩa route, vừa thực thi thêm/xóa. Tài liệu Gateway phân biệt `InMemoryRouteDefinitionRepository` (state local process) và `RedisRouteDefinitionRepository` (state có thể dùng chung). Không đánh đồng **lưu chung RouteDefinition** với **tự động refresh cache từng replica**.

### 7.2. Mẫu service cập nhật có kiểm soát

Trong project Gateway WebFlux, tạo `src/main/java/demo/gateway/routes/RouteMutationService.java`:

~~~java
package demo.gateway.routes;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class RouteMutationService {

    private static final String ROUTE_ID = "catalog-live";

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher publisher;

    public RouteMutationService(RouteDefinitionWriter writer,
            ApplicationEventPublisher publisher) {
        this.writer = writer;
        this.publisher = publisher;
    }

    // Chỉ cho phép hai destination đã duyệt: tránh biến Gateway
    // thành open proxy hoặc SSRF gateway.
    public Mono<Void> setCatalogTarget(String target) {
        URI destination = switch (target) {
            case "A" -> URI.create("http://127.0.0.1:9191");
            case "B" -> URI.create("http://127.0.0.1:9192");
            default -> throw new IllegalArgumentException(
                    "Target must be A or B");
        };

        RouteDefinition definition = new RouteDefinition();
        definition.setId(ROUTE_ID);
        definition.setUri(destination);
        definition.setOrder(0);
        definition.setPredicates(List.of(
                new PredicateDefinition("Path=/api/catalog/**")));
        definition.setFilters(List.of(
                new FilterDefinition("StripPrefix=1"),
                new FilterDefinition(
                        "AddRequestHeader=X-Route-Revision," + target)));
        definition.setMetadata(Map.of(
                "group", "lab",
                "revision", target));

        return writer.save(Mono.just(definition))
                // Chỉ phát event SAU khi save hoàn tất.
                .then(Mono.fromRunnable(this::requestRefresh));
    }

    public Mono<Void> deleteCatalog() {
        return writer.delete(Mono.just(ROUTE_ID))
                .then(Mono.fromRunnable(this::requestRefresh));
    }

    private void requestRefresh() {
        publisher.publishEvent(new RefreshRoutesEvent(this));
    }
}
~~~

Ý nghĩa:

- Service nhận **target theo allowlist A/B**. Không cho client truyền URI tự do như `http://169.254.169.254/...` hoặc `http://localhost:...` ngoài danh sách: đây là rủi ro SSRF/open proxy rất lớn khi có quyền sửa routes.
- `new PredicateDefinition("Path=...")` và `new FilterDefinition("StripPrefix=1")` dùng shortcut DSL của Gateway để dựng các định nghĩa.
- `writer.save(Mono.just(definition))` trả **Mono<Void>**: thao tác chưa thực thi cho đến khi có subscription. `.then(Mono.fromRunnable(...))` bảo đảm publisher chỉ chạy **sau khi lưu thành công**.
- Nếu save báo lỗi, phần `then(...)` **không chạy**. Nếu nguồn dữ liệu có transaction, còn cần chờ **commit** chứ không chỉ ghi vào bộ nhớ tạm.
- `publishEvent(...)` đánh thức cơ chế refresh của **process hiện tại**. Nó không trả một Future chứng minh cache đã cập nhật hay các replica khác đã hoàn thành.
- Với repository hỗ trợ **upsert/replace theo ID**, `save` có thể cập nhật định nghĩa; semantics khác Actuator POST và tùy implementation. Không dùng code này để mặc định cho mọi repository nếu không biết cách nó xử lý existing ID.

**Không gọi `.subscribe()` tùy tiện trong service rồi trả HTTP 200 ngay.** Hãy trả `Mono<Void>` cho một workflow/handler tin cậy và cho nó subscribe ở ranh giới reactive. Nếu một handler nhận yêu cầu cập nhật, có thể trả **202 Accepted** khi thao tác lưu và phát event thành công, sau đó controller/orchestrator **kiểm chứng async refresh** ở bước riêng.

### 7.3. Repository cho một tiến trình trong lab

Nếu cần đảm bảo service ở mục 7.2 có repository writable, chỉ trong **profile lab** có thể định nghĩa bean:

~~~java
package demo.gateway.routes;

import org.springframework.cloud.gateway.route.InMemoryRouteDefinitionRepository;
import org.springframework.cloud.gateway.route.RouteDefinitionRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("route-lab")
public class RouteLabRepositoryConfiguration {

    @Bean
    RouteDefinitionRepository routeDefinitionRepository() {
        return new InMemoryRouteDefinitionRepository();
    }
}
~~~

Nhiều bản Gateway đã tự tạo in-memory repository khi không có repository khác, nên **không bắt buộc thêm bean thủ công trong mọi dự án**. Khi chọn custom repository, bảo đảm chỉ có repository/writer phù hợp, tránh hai bean ứng viên gây lỗi inject hoặc hai nguồn route cùng ID.

Lab **Actuator** ở mục 6 đã đủ để học refresh, nên **không cần khai báo service và repository của mục 7 đồng thời chỉ để lặp lại thao tác**. Mục 7 minh họa **cách tích hợp sự kiện vào một workflow Java** đã được xác thực/phân quyền; không nên tạo một public controller không bảo vệ chỉ để trigger event.

### 7.4. Nếu dùng hệ thống cập nhật cấu hình từ xa

Với PostgreSQL/Redis/Config Server:

1. Nhận change request từ hệ thống quản trị **đã xác thực và được phân quyền**.
2. Validate route ID, URI scheme, host allowlist, predicate/filter syntax, request path và security policy.
3. Ghi vào source of truth bằng transaction hoặc thao tác có kiểm soát revision.
4. Chỉ sau khi commit, phát sự kiện trong từng Gateway process.
5. Theo dõi kết quả refresh, xác nhận route revision và request smoke test trên từng replica.
6. Ghi audit trail ai sửa, sửa từ revision nào sang revision nào; có rollback.

Không nên đặt `publishEvent(...)` trước khi transaction hoàn tất: listener có thể đọc nguồn cũ và cache lại chính trạng thái cũ.

## 8. Khi Gateway chạy nhiều bản sao: mỗi process có cache riêng

Xét triển khai:

~~~mermaid
flowchart TD
    C["Clients"] --> LB["Load Balancer / Ingress"]
    LB --> A["Gateway A<br/>CachingRouteLocator A"]
    LB --> B["Gateway B<br/>CachingRouteLocator B"]
    A --> DB[("Shared RouteDefinitionRepository<br/>Redis / DB")]
    B --> DB
    E["Admin workflow<br/>write revision v2"] --> DB
    E -.->|"refresh event/push riêng"| A
    E -.->|"refresh event/push riêng"| B
    A --> D1["Backend A / B"]
    B --> D1
~~~

Ngay cả khi A và B cùng đọc **một kho Redis** chứa RouteDefinition, **mỗi Gateway instance vẫn có `CachingRouteLocator` trong bộ nhớ của process đó**. Java `ApplicationEventPublisher` phát event **nội bộ JVM**, không tự gửi qua mạng cho B.

### 8.1. Ba kịch bản thường gặp

| Kho định nghĩa | Cache Gateway A/B | Điều gì xảy ra khi chỉ refresh A? |
| --- | --- | --- |
| `InMemoryRouteDefinitionRepository` riêng từng process | Riêng từng process | B không thấy định nghĩa mới nếu chỉ tạo ở A; refresh B cũng không đủ khi B không có nguồn mới |
| Redis/DB chung | Riêng từng process | A có thể nạp revision mới, nhưng B có thể tiếp tục dùng revision cũ |
| Config Server hoặc discovery chung | Riêng từng process, có cache upstream | Phải bảo đảm cả nguồn lẫn cơ chế refresh ở từng replica đã nhận revision mới |

**Đừng nhầm “shared repository” với “distributed route cache”.** Shared repository chỉ làm cho các node **có thể đọc cùng dữ liệu**, còn cơ chế invalidate/rebuild cache phải được triển khai và xác minh riêng.

### 8.2. RedisRouteDefinitionRepository và namespace phiên bản

Spring Cloud Gateway có implementation `RedisRouteDefinitionRepository` để lưu routes trong Redis thay vì chỉ trong RAM. Muốn dùng cần dependency reactive Redis và cấu hình phù hợp. Trên **Gateway Server WebFlux 5.x**, bảng Configuration Properties nêu:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          redis-route-definition-repository:
            enabled: true
~~~

Ở các dòng **Gateway WebFlux 4.x** theo namespace cũ, tài liệu có:

~~~yaml
spring:
  cloud:
    gateway:
      redis-route-definition-repository:
        enabled: true
~~~

Dependency reactive Redis thường dùng trong Spring Boot 3.x:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
~~~

**Lưu ý phiên bản:** Một số trang văn bản “Sharing Routes” thuộc docs 5.x còn minh họa prefix `spring.cloud.gateway.redis-route-definition-repository.enabled`, trong khi bảng Configuration Properties 5.x liệt kê prefix có `server.webflux`. Khi khác biệt, kiểm tra **configuration metadata và hành vi bean trên đúng artifact/release**. Không chỉ thêm property mà mặc định kết luận Redis repository đã được kích hoạt.

Việc dùng Redis cũng không tự giải quyết transaction xuyên nhiều routes, refresh phân tán hoặc chính sách bảo mật. Với DB/source tùy biến, có thể cần versioned snapshot và API cập nhật riêng.

Tên property đầy đủ của WebFlux 5.x trong bảng Config Props là `spring.cloud.gateway.server.webflux.redis-route-definition-repository.enabled`; ở các dòng 4.x là `spring.cloud.gateway.redis-route-definition-repository.enabled`. Hãy xác minh bean repository đang hoạt động, không chỉ kiểm tra YAML.

### 8.3. Cơ chế phát refresh cho cả cụm

Một thiết kế phổ biến:

1. Admin lưu revision mới **v2** vào kho chung.
2. Sau commit, phát một thông điệp thay đổi có `revision=v2` lên hệ thống tin cậy (message bus, event channel, controller/orchestrator).
3. Mỗi Gateway replica nhận sự kiện **đã xác thực**, đối chiếu revision và gọi `publishEvent(new RefreshRoutesEvent(...))` nội bộ.
4. Mỗi replica materialize routes mới, tự báo trạng thái **applied/failed**, revision đang phục vụ.
5. Bộ điều phối chỉ đánh dấu rollout đạt khi đủ replica đạt revision theo SLA hoặc loại replica lỗi khỏi traffic.

**Không suy rằng Spring Cloud Bus hoặc Redis pub/sub đã tự được bật** chỉ vì project có Spring Cloud Gateway/Redis. Phải cấu hình tích hợp đó và retry delivery/at-least-once/dedup theo khả năng của hệ thống.

Nếu một Gateway replica đang mất kết nối kho chung, refresh không thể tạo ra định nghĩa mới từ dữ liệu không truy cập được. Cần quyết định giữ **last-known-good routes**, readiness/liveness, cảnh báo và giới hạn thời gian stale.

### 8.4. “Cập nhật tức thời” không có nghĩa mọi request trên cụm cùng thấy v2

Trong cửa sổ chuyển đổi:

~~~text
10:00:00  Repository đã commit revision v2
10:00:01  Gateway A cache v2, Gateway B vẫn cache v1
10:00:02  Load balancer có thể phân phối request vào A hoặc B
10:00:03  Gateway B mới cache v2
~~~

Đây chỉ là ví dụ thời gian. Một hệ thống cần **strong consistency của route rollout** phải có cơ chế drain/quiesce, snapshot version và đồng bộ release phù hợp; phát một `RefreshRoutesEvent` không cung cấp tính chất atomic cluster-wide.

## 9. Bất đồng bộ, concurrency và race condition khi refresh

### 9.1. Hai refresh gần nhau có thể đọc các revision khác nhau

Giả sử thao tác thay nguồn liên tiếp:

~~~text
Repository: v1 → v2 → v3
Refresh X bắt đầu đọc v2, thực hiện chậm
Refresh Y bắt đầu đọc v3, thực hiện nhanh
~~~

Nếu implementation không tuần tự hóa/kiểm soát cache swap theo revision, một kết quả refresh cũ hoàn thành trễ **có nguy cơ ghi đè** kết quả mới. Các issue của Spring Cloud Gateway từng ghi nhận tình huống concurrency/race trong một số release. **Không khẳng định mọi bản đều có lỗi**, nhưng điều này giải thích vì sao production cần test refresh liên tục với đúng patch version.

Các biện pháp giảm rủi ro:

- Chỉ có **một workflow phát hành cấu hình** cho mỗi tập routes, tránh hai admin cập nhật cùng lúc.
- Gắn **revision đơn điệu** với snapshot và kiểm tra version trước/sau refresh.
- Hợp nhất (coalesce/debounce) nhiều thông điệp refresh gần nhau thay vì phát vô hạn.
- Chặn deployment mới nếu validator/materialization lỗi; giữ last-known-good.
- Sau refresh, **đọc route runtime và gửi request thử**, không chỉ đợi HTTP 200.
- Nếu kết quả cũ vượt qua revision mới, yêu cầu đồng bộ lại snapshot mới nhất và điều tra root cause.

### 9.2. Thay đổi nhiều routes phải được xem là một đợt cấu hình

Ví dụ tuyến `payment-public` yêu cầu filter xác thực, còn tuyến `payment-internal` cho phép mTLS. Nếu cập nhật hai route trong hai lệnh riêng và refresh ở giữa, hệ thống có thể thoáng chốc rơi vào trạng thái **bỏ sót filter bảo vệ** hoặc route overlap ngoài ý muốn.

Production nên:

1. Validate **toàn bộ snapshot** (route IDs duy nhất, path/method conflicts, priority/order, destinations, security filters).
2. Commit snapshot mới hoặc dùng compare-and-swap theo revision.
3. Refresh tại các replica theo kế hoạch.
4. Đánh giá truy cập end-to-end sau khi refresh.
5. Có thể rollback về snapshot an toàn trước đó nếu không đạt.

**Không để security phụ thuộc hoàn toàn vào một route filter có thể bị xóa bằng API quản trị.** Ranh giới xác thực/phân quyền còn cần được bảo vệ ở Spring Security WebFilter chain và backend.

### 9.3. Refresh fail và route cũ: điều gì nên được quan sát?

Tài liệu Actuator mô tả nếu async refresh có lỗi thì route cache hiện có không được thay đổi. Tuy nhiên, câu “cache cũ còn” chỉ hữu ích khi bạn biết cache cũ đang an toàn và đã kiểm thử trạng thái thực tế.

Hãy ghi nhận:

- **source revision**: kho nguồn hiện lưu v2 hay v3;
- **applied revision**: mỗi Gateway replica thực sự đang dùng revision nào;
- **refresh result**: thành công, thất bại, timeout, bị bỏ qua vì cùng revision;
- **route count/hash**: danh sách ID/URI/predicate/filter có tương ứng snapshot kỳ vọng không;
- **request result**: client thực sự được route tới đâu và security policy có hiệu lực không.

Chỉ log tên route/revision và thông tin lỗi đã làm sạch, **không log secret**, token, cookie, raw request body hoặc credential cấu hình.

## 10. Kiểm chứng bằng bài test có kiểm soát

Một bộ test tốt cần tách **route cache** với **backend availability**. Với lab A/B:

| Ca | Thao tác | Kiểm chứng kỳ vọng |
| --- | --- | --- |
| T1 | GET khi chưa có route | 404 nếu không có handler khác |
| T2 | Tạo RouteDefinition tới A, **chưa refresh** | Nguồn có thể chứa v1; không coi runtime chắc chắn đã đổi |
| T3 | POST refresh, kiểm tra route runtime | Có `catalog-live`, URI 9191, revision v1 |
| T4 | GET `/api/catalog/items/42` | Backend A, path `/catalog/items/42` |
| T5 | Xóa + tạo lại tới B rồi refresh | Runtime mới có URI 9192, revision v2 |
| T6 | GET sau T5 | Backend B nhận request |
| T7 | Xóa route rồi refresh | Route không còn, request không khớp thường 404 |
| T8 | Tạo route có filter không tồn tại | Refresh/materialization phải báo lỗi, không âm thầm bỏ bảo vệ |
| T9 | Thử `DELETE` route từ `application.yml` | Không được coi là thao tác xóa route do YAML sở hữu |
| T10 | Refresh chọn lọc metadata | Chỉ tin kết quả sau khi xem đúng nhóm runtime của release |
| T11 | Hai Gateway replicas, chỉ refresh A | A/B có thể khác revision; phát và kiểm chứng riêng |
| T12 | Kho nguồn chậm/lỗi khi refresh | Quan sát last-known-good, timeouts và alert |

### 10.1. Test một route có cấu hình filter không hợp lệ

Ví dụ **cố tình sai**:

~~~json
{
  "predicates": ["Path=/api/catalog/**"],
  "filters": ["NoSuchSecurityFilter=required"],
  "uri": "http://127.0.0.1:9191",
  "order": 0
}
~~~

Nếu nguồn được tạo và Gateway materialize route, bộ lọc không tồn tại sẽ gây lỗi theo cơ chế phiên bản. **Không dùng ví dụ đó để thử trên production**, đặc biệt với route vốn dùng để bảo vệ API. Mục tiêu là xác nhận pipeline từ chối cấu hình xấu, log và rollback.

### 10.2. Khi tự viết integration test

Với `@SpringBootTest`, `WebTestClient` và một `RouteDefinitionRepository` test:

1. Đầu tiên materialize tập routes để cache có v1.
2. Thay nguồn bằng v2 bằng `save(...)` rồi **đợi hoàn tất** (trong test có thể dùng StepVerifier).
3. Trước refresh, quan sát trạng thái hiện hành để thiết lập baseline.
4. Phát `RefreshRoutesEvent` trong cùng application context.
5. Dùng một điều kiện chờ có **timeout hữu hạn** và đọc lại routes cho tới khi revision mong muốn xuất hiện.
6. Gửi HTTP request qua `WebTestClient`, xác minh destination/filter effects.
7. Test thất bại có kiểm soát khi source cung cấp định nghĩa sai.

Không nên dùng `Thread.sleep(5000)` rồi kết luận test đúng: thời gian refresh phụ thuộc máy, backend và JVM; hãy chờ một **điều kiện cụ thể**. Trong code production không dùng `block()` trong Reactor Netty event loop để “đợi cache refresh”.

### 10.3. Phân biệt route cache với request đang xử lý dở

Một request đã chọn tuyến trước khi refresh có thể tiếp tục đi theo **Route object cũ** trong khi các request mới nhận tuyến mới. Không nhất thiết có sự chuyển đổi giữa chừng của cùng một request, và cũng **không nên hủy mọi in-flight request** chỉ để thay URI.

Trong rolling deployment, cần lập kế hoạch drain/timeout kết nối nếu thay backend đích có thay đổi contract lớn. Kiểm thử cả request ngắn, stream dài và WebSocket nếu hệ thống có dùng.

## 11. Bảo mật: API quản trị tuyến có thể nguy hiểm hơn một API nghiệp vụ

Việc cho phép tạo một route tùy ý có thể khiến Gateway trở thành:

- **SSRF proxy**: trỏ tới metadata service hoặc địa chỉ private không dự định public;
- **open proxy**: chuyển traffic Internet sang host bất kỳ;
- **authorization bypass**: tạo route path khác đi vòng policy;
- **filter bypass**: bỏ JWT, rate limit hoặc circuit breaker bắt buộc;
- **header injection**: thay `Host`, `Authorization`, `Forwarded` hoặc security headers;
- **denial of service**: thêm hàng nghìn routes nặng, predicates/filter không hợp lệ hoặc refresh liên tục.

Vì vậy:

1. **Không expose `/actuator/gateway/routes*` hay `/actuator/gateway/refresh` có quyền ghi cho Internet.**
2. Production ưu tiên Actuator `gateway` **read-only** để quan sát; chỉ mở `unrestricted` trong management plane cô lập nếu thật sự cần.
3. Quản trị tuyến phải có **authentication, authorization theo vai trò và audit trail**; địa chỉ private/loopback và mTLS là biện pháp bổ trợ.
4. Route destination phải qua **allowlist hostname/scheme/port**, không nhận mọi URI do client cung cấp. Cần xem xét DNS rebinding và redirect behavior nếu URL được kiểm soát gián tiếp.
5. Kiểm tra predicate conflicts, route `order`, path rewriting và các **security filters bắt buộc** trước khi ghi.
6. Có rate limit/lock cho hoạt động refresh để tránh lạm dụng hoặc refresh storm.
7. Không chứa secret, JWT, key hoặc thông tin nội bộ nhạy cảm trong route metadata có thể đọc qua Actuator.

**Không nên dùng một HTTP endpoint công khai như `POST /admin/routes/refresh` mà chỉ kiểm tra một header `X-Admin: true` do client tự gửi.** Nếu cần HTTP API quản trị riêng, đặt nó ở control plane có kiểm soát truy cập nghiêm ngặt và không để nó tự động trở thành route public của Gateway.

### 11.1. Dynamic routes có thể vượt ngoài security assumptions

Giả sử Spring Security chỉ yêu cầu authentication cho `/api/orders/**`; một admin endpoint sai quyền lại có thể tạo `/internal/orders/**` trỏ cùng backend mà không được guard. Khi update route, phải xem **security policy ở tầng WebFilter và downstream** bao phủ toàn bộ các path public có thể tồn tại, không chỉ policy của một route duy nhất.

CORS cũng cần kiểm tra theo path công khai và origin: nếu route mới đổi metadata hoặc URI, cấu hình CORS runtime có thể cần được rebuild theo cơ chế version. Một số issue từng ghi nhận timing giữa Redis route refresh và CORS mapping ở các release cũ; vì vậy cần **test CORS preflight và actual request** sau thay đổi route quan trọng.

### 11.2. Actuator read-only và unrestricted

Trong các tài liệu Gateway 4.2/5.0 được tham khảo, Actuator có chế độ:

~~~properties
# Quan sát routes: khuyến nghị mặc định production
management.endpoint.gateway.access=read-only
management.endpoints.web.exposure.include=gateway
~~~

và khi thực sự cần ghi trong management plane được bảo vệ:

~~~properties
# Chỉ cho lab hoặc control plane được khóa nghiêm ngặt
management.endpoint.gateway.access=unrestricted
management.endpoints.web.exposure.include=gateway
~~~

Chế độ `read-only` không cho phép create/delete/refresh routes qua Actuator. Tên property `management.endpoint.gateway.access` cần được đối chiếu cùng Spring Boot version; các bản cũ có thể cấu hình khác. Một endpoint được “exposed” không đồng nghĩa đã được **security** bảo vệ: kiểm tra Spring Security và hạ tầng mạng riêng.

## 12. Quan sát quá trình refresh trong production

### 12.1. Những số liệu nên có

Các chỉ số hữu ích (tên sau là **gợi ý metrics tự thiết kế**, không phải cam kết đều được Gateway xuất mặc định):

~~~text
gateway_route_refresh_total{node, outcome="success|failure"}
gateway_route_refresh_duration_seconds{node}
gateway_routes_applied_revision{node}
gateway_routes_count{node}
gateway_route_change_total{operation="save|delete|rollback"}
gateway_route_stale_seconds{node}
gateway_route_probe_success{route_group,node}
~~~

Ngoài metrics, nên lưu sự kiện audit:

~~~text
change-id:       change-128
requested-by:    admin principal đã xác thực
source-revision: v21
target-revision: v22
changed-routes:  catalog-live
validation:      PASS
node-A:          applied v22
node-B:          applied v22
smoke-test:      PASS
rollback:        not-needed
~~~

Không gắn toàn bộ URI có credentials, access token, cookie, request ID từng user hay body vào metrics labels; điều đó tạo **high cardinality** và rủi ro lộ dữ liệu.

### 12.2. Cấu hình log khi điều tra

Tài liệu Gateway có gợi ý logger:

~~~yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
~~~

Chỉ bật DEBUG/TRACE có thời hạn tại môi trường hoặc route phù hợp. Nếu bật Netty wiretap, cần đặc biệt cẩn thận vì nó có thể đưa headers/body nhạy cảm vào logs. Không để log raw JWT hoặc session cookie khi điều tra refresh.

### 12.3. Những câu hỏi khi thấy route revision cũ

1. **Nguồn route đang ở revision nào?** Đọc repository/Config Server trực tiếp qua công cụ quản trị được bảo vệ.
2. **Đã phát event ở process này chưa?** Kiểm tra log event/change-ID.
3. **Có lỗi bind predicate/filter hoặc URI không?** Kiểm tra error logs của route materialization.
4. **Route runtime của process này đã cập nhật chưa?** Kiểm tra Actuator và route count/hash.
5. **Request thật đang tới replica nào?** Bỏ qua load balancer hoặc dùng header định danh replica trên môi trường test.
6. **Có route khác ưu tiên cao hơn không?** Xem route order và predicate overlap.
7. **URI là `lb://`?** Kiểm tra discovery/LoadBalancer cache tách biệt.
8. **Cache CDN/người dùng có trả response cũ?** Kiểm tra response headers/trace backend.

## 13. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Kiểm tra / hướng xử lý |
| --- | --- | --- |
| `POST /actuator/gateway/refresh` trả 404 | Gateway Actuator chưa bật/expose, sai cổng hoặc context path | Kiểm tra Actuator starter, management port và access config |
| Refresh trả 403/405 | Endpoint ở read-only, security hoặc firewall chặn | Không mở ghi bừa; dùng authorized management plane |
| POST route 201 nhưng request nghiệp vụ vẫn 404 | Cache chưa refresh, refresh chưa hoàn tất, route sai predicate | POST refresh, đọc runtime routes, kiểm thử có timeout |
| GET routedefinitions thấy v2, GET routes còn v1 | Nguồn đã đổi nhưng runtime/cache chưa nạp | Kiểm tra refresh event/log lỗi và route materialization |
| Route runtime v2 nhưng vẫn tới backend A | Có route khác thắng, request qua replica cũ, upstream/cache khác | Kiểm tra route order, replica ID, header revision và backend logs |
| Xóa route qua Actuator trả 404 | Route do application.yml/Java bean quản lý, không do Actuator tạo | Đổi đúng nguồn sở hữu route; không cố xóa bằng API sai |
| Refresh lỗi vì `GatewayFilterFactory` lạ | Route definition dùng filter name/args sai | Validate đầy đủ route trước commit |
| Sau refresh route cũ vẫn hoạt động | Refresh bất đồng bộ, stale source, cache giữ last-good | Xác minh source revision, result và runtime trên mỗi node |
| A đã v2, B vẫn v1 | Event chỉ được phát ở process A | Phát/điều phối refresh riêng cho B |
| Thêm URI `lb://...` nhưng trả 503 | Discovery không tìm được instance | Kiểm tra service ID/registry/LoadBalancer, không nhầm với route cache |
| Request 401/403 sau đổi route | Security policy khác hoặc route path mới chưa được phép | Kiểm tra WebFilter authorization, token/scope, path public |
| CORS OPTIONS 404 hoặc policy cũ | Predicate/Method không khớp OPTIONS, CORS mapping stale | Kiểm tra global CORS, origin/method, refresh theo version |
| Sau nhiều refresh liên tiếp cache lùi revision | Race/stale snapshot hoặc implementation issue | Serialize updates, kiểm tra patch release, snapshot revision và rollback |
| Latency tăng đột biến khi refresh | Materialize routes nặng hoặc contention | Đo duration/CPU, debounce refresh và limit số routes |

## 14. Checklist rollout tuyến động

- [ ] Xác định **source of truth** cho route definitions, không sửa cùng lúc nhiều nguồn không điều phối.
- [ ] Biết rõ phân biệt `RouteDefinitionRepository`, `RouteDefinitionRouteLocator` và `CachingRouteLocator`.
- [ ] Đã commit/hoàn tất `RouteDefinitionWriter.save/delete` **trước** khi phát `RefreshRoutesEvent`.
- [ ] Không giả định `publishEvent` trả về hoặc HTTP 200 refresh là bằng chứng route runtime đã đổi.
- [ ] Có bước kiểm tra **route ID, URI, predicates, filters, order, metadata và revision** sau refresh.
- [ ] Có smoke test qua request nghiệp vụ, xác minh backend được chọn và path/header thực tế.
- [ ] Các routes không được trùng ID hoặc tạo path/order conflict ngoài ý muốn.
- [ ] Cấu hình lỗi được từ chối; có last-known-good, audit trail và rollback.
- [ ] Hạn chế refresh đồng thời và kiểm soát revision để giảm race condition.
- [ ] Nếu nhiều Gateway replicas, đã kiểm tra **từng cache node**; shared DB/Redis không tự phát event toàn cụm.
- [ ] Phân biệt route cache với cache discovery, LoadBalancer, DNS và HTTP response.
- [ ] Không expose Actuator ghi route ra Internet; production ưu tiên read-only hoặc management plane riêng.
- [ ] Tất cả URI destinations có allowlist/scheme validation để chống SSRF/open proxy.
- [ ] Security WebFilter, rate limiter, Retry, circuit breaker, TLS và CORS vẫn có hiệu lực sau route update.
- [ ] Có metrics cho refresh failures, applied revision, stale duration, route count và probe results.
- [ ] Có test refresh liên tiếp, failed rebuild, route deletion, multi-node drift và slow repository.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao repository có v2 mà Gateway vẫn đi tới backend v1?**

Vì `CachingRouteLocator` có thể đang giữ tập routes runtime được dựng từ v1. Cần yêu cầu refresh và xác nhận route runtime đã nhận v2.

**2. Gọi `publishEvent(new RefreshRoutesEvent(this))` có thay một route trong repository không?**

Không. Event chỉ yêu cầu các listener liên quan làm mới; nguồn RouteDefinition phải đã được lưu/xóa riêng.

**3. Khi HTTP `POST /actuator/gateway/refresh` trả 200, có chắc Gateway B đã cập nhật?**

Không. Event và cache thuộc process; Gateway B có thể là JVM khác chưa nhận yêu cầu refresh, ngay cả khi dùng cùng Redis repository.

**4. Có thể dùng DELETE Actuator để xóa bất kỳ tuyến định nghĩa trong application.yml không?**

Không. API quản lý routes được Actuator tạo; các routes sở hữu bởi nguồn YAML/Java bean không mặc nhiên có thể bị xóa qua endpoint đó.

**5. Một route mới `lb://orders-service` trả 503. Có luôn là do chưa refresh routes không?**

Không. Có thể route đã đúng nhưng discovery/LoadBalancer không tìm được instance của `orders-service`. Cần phân tích hai loại cache riêng.

**6. Tại sao route update cần kiểm tra security và CORS ngoài status 200 của backend?**

Vì route mới có thể bypass đường path/security cũ, đổi filter hoặc đổi CORS metadata. Một backend trả 200 không chứng minh người dùng không có quyền vẫn bị chặn đúng.

**7. Tại sao phải đợi `save(Mono<RouteDefinition>)` hoàn tất rồi mới phát event?**

Vì nếu event được xử lý trước khi lưu/commit kết thúc, listener có thể đọc định nghĩa cũ và nạp cache cũ một lần nữa.

## 16. Tài liệu chính thức để đối chiếu

1. [Spring Cloud Gateway Server WebFlux 5.0 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html): refresh route cache, quản lý route definitions, HTTP status và tùy chọn metadata.
2. [Gateway Server WebFlux 4.2 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/actuator-api.html): thao tác quản trị và refresh theo dòng 4.2.
3. [Gateway Server WebFlux 5.0 — Configuration](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/configuration.html): `RouteDefinitionLocator` và nguồn định nghĩa tuyến.
4. [Gateway Server WebFlux 5.0 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html): namespace `spring.cloud.gateway.server.webflux.routes` và Redis route definition repository.
5. [Gateway — Sharing Routes between Multiple Instances](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/sharing-routes.html): repository in-memory so với Redis, cần đối chiếu prefix property với bảng Config Props của release.
6. [Spring Cloud Gateway — Configuration Reference](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/configuration.html): tổng quan cấu hình routes, predicate/filter và các nguồn.
7. [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access level và bảo vệ endpoints quản trị.
8. [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): cơ chế Spring ApplicationEventPublisher và listener.

**Ghi nhớ:** **`RefreshRoutesEvent` báo Gateway WebFlux nạp lại route cache, chứ không lưu RouteDefinition hay tự đồng bộ mọi replica.** Muốn cập nhật tuyến đúng cách, phải **ghi nguồn cấu hình → yêu cầu refresh → xác minh runtime route và request thật**, với revision, validation, quyền quản trị và rollback rõ ràng. Một HTTP 200 từ `/actuator/gateway/refresh` chỉ là một bước trong quy trình này, không phải bảo đảm toàn cụm đã định tuyến theo cấu hình mới.
