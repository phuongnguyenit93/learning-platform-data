# Cô lập endpoint quản trị khỏi lưu lượng công khai

## 1. Vì sao quản trị API Gateway cần một mặt phẳng truy cập riêng?

Trong kiến trúc microservices, **Spring Cloud Gateway Server WebFlux** thường lắng nghe HTTP traffic của người dùng ở cổng công khai, áp dụng **route predicates**, **filter chain**, biến đổi đường dẫn/header, rồi chuyển tiếp đến backend qua URL cố định hoặc khám phá dịch vụ `lb://service-id`. Đây là **data plane**: mọi request từ client phải đi qua các quy tắc xác thực, phân quyền, rate limiting, circuit breaker, retry, TLS và observability phù hợp.

Trong cùng ứng dụng, **Spring Boot Actuator** có thể cung cấp các HTTP endpoint phục vụ **control/management plane**: xem sức khỏe, đo metrics, liệt kê routes, quan sát filters và — nếu được cho phép — làm mới hoặc sửa routes. Các endpoint này hữu ích cho SRE, hệ thống monitoring và pipeline triển khai, nhưng **không nên xuất hiện như API công khai cho mọi người dùng**.

Ví dụ cấu hình nguy hiểm:

~~~text
Internet
   |
   v
https://api.example.test
   |
   v
Gateway :8080
   +-- /api/orders/**             → orders-service
   +-- /actuator/gateway/routes  → liệt kê nội bộ routes
   +-- /actuator/gateway/refresh → có thể làm mới routes
   +-- /actuator/env            → có thể làm lộ metadata cấu hình
~~~

Nếu không có lớp bảo vệ thích hợp, kẻ tấn công có thể biết cấu trúc route/host nội bộ, khai thác thông tin hệ thống, tạo sức ép qua các endpoint chẩn đoán, hoặc — khi quyền ghi bị bật sai — thay đổi route để tạo **SSRF, open proxy, vượt qua các filter bảo mật**.

Bài thuộc chương **Quản trị Actuator** của module **SPRING_CLOUD_GATEWAY**, tập trung vào một yêu cầu vận hành quan trọng: **tách lưu lượng quản trị khỏi lưu lượng công khai bằng nhiều ranh giới độc lập, có kiểm chứng**.

Sau bài này, bạn có thể:

1. Phân biệt cổng public API với cổng dành cho monitoring/administration.
2. Dùng `management.server.port` và `management.server.address` đúng điều kiện.
3. Phân biệt **endpoint access**, **web exposure**, **Spring Security** và **kiểm soát mạng**.
4. Đặt endpoint `gateway` ở mức **read-only**, tránh vô tình mở các thao tác tạo/xóa/refresh routes.
5. Kiểm thử từ cả bên trong lẫn bên ngoài, không chỉ dựa vào status của một lệnh `curl`.
6. Thiết kế Ingress/Service/NetworkPolicy cho Kubernetes hoặc firewall/reverse proxy trên VM.
7. Hiểu các rủi ro của probes, proxy-route bypass, TLS, logs/metrics và quyền quản trị động.

> **Phạm vi:** Các ví dụ dùng **Spring Cloud Gateway Server WebFlux** và Spring Boot Actuator ở các dòng phiên bản phù hợp. Gateway Server MVC có khác biệt trong hệ thống filter và đường cấu hình. Không dùng cấu hình này như giấy phép mở endpoint quản trị ra Internet.

## 2. Một endpoint quản trị có bốn lớp kiểm soát khác nhau

Không được đánh đồng việc “đã bật Spring Security” với “đã cô lập endpoint”. Một endpoint chỉ nên tiếp cận được khi tất cả các lớp liên quan đều cho phép.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Network reachability** | Client có kết nối được tới cổng quản trị không? | Bind loopback, private interface, firewall, Service/NetworkPolicy |
| **Endpoint access** | Endpoint có tồn tại và được phép thực hiện loại thao tác nào? | `management.endpoint.gateway.access=read-only` |
| **Transport exposure** | Endpoint có được xuất bản qua HTTP/JMX không? | `management.endpoints.web.exposure.include=health,gateway` |
| **Identity & authorization** | Caller thực sự là ai, có vai trò gì? | Spring Security Reactive, mTLS, RBAC, service identity |

Mô hình quyết định:

~~~mermaid
flowchart TD
    C["HTTP client"] --> N{"Đến được management port?"}
    N -->|"Không"| X["Connection denied / unreachable"]
    N -->|"Có"| E{"Endpoint enabled và exposed?"}
    E -->|"Không"| F["Không tìm thấy endpoint / không được công bố"]
    E -->|"Có"| S{"Caller được xác thực,<br/>đủ quyền?"}
    S -->|"Không"| A["401 hoặc 403"]
    S -->|"Có"| P{"Operation được phép?"}
    P -->|"Read operation"| R["Đọc health/routes/metrics"]
    P -->|"Mutation không cho phép"| D["Từ chối POST/DELETE/WRITE"]
    P -->|"Mutation được phép, policy nghiêm ngặt"| W["Chỉ trong management plane"]
~~~

**Lưu ý:** Response cụ thể có thể là 401, 403, 404, 405 hoặc lỗi kết nối tùy lớp chặn và phiên bản. Điều quan trọng là một client công khai **không được dùng endpoint nhạy cảm**, không phải ép tất cả đường bị chặn trả cùng một status.

### 2.1. Access không giống authentication

Ví dụ:

~~~properties
management.endpoint.gateway.access=read-only
~~~

nghĩa là những thao tác quản trị ghi của endpoint `gateway` không được cung cấp ở cấp **endpoint operation**. Nó **không** tự động xác thực người đang đọc danh sách routes. Nếu endpoint đó còn có thể tới từ Internet mà không có Security, các route URI hoặc metadata vẫn có thể lộ.

### 2.2. Exposure không giống quyền ghi

Ví dụ:

~~~properties
management.endpoints.web.exposure.include=health,gateway
~~~

chỉ định những endpoint nào được trình bày qua HTTP. Nó không quyết định liệu `/gateway/refresh` có được phép thực thi hay không. Quyền đọc/ghi phụ thuộc access level và chính sách Security. Ngược lại, đặt `access=unrestricted` mà không expose HTTP cũng không tự biến endpoint thành API web công khai, nhưng có thể còn đường JMX hoặc kênh khác nếu cấu hình.

### 2.3. Đổi đường dẫn /actuator không phải cô lập

~~~yaml
management:
  endpoints:
    web:
      base-path: /_private_ops
~~~

đổi URL từ `/actuator/health` sang `/_private_ops/health`. Đây là **đổi namespace đường dẫn**, không có tác dụng tương đương firewall, authentication hoặc phân quyền. Kẻ tấn công có thể đoán, dò đường dẫn hoặc đọc cấu hình lộ; không dựa vào “đường dẫn bí mật” để phòng thủ.

## 3. Nhận diện mức độ nhạy cảm của các Actuator endpoint

| Endpoint / nhóm | Mục đích chính | Rủi ro nếu public |
| --- | --- | --- |
| `health`, `health/liveness`, `health/readiness` | Kiểm tra sức khỏe/probe | Lộ thành phần chi tiết nếu bật show-details quá rộng; bị quét liên tục |
| `info` | Version, build, ứng dụng | Lộ phiên bản hoặc dữ liệu triển khai nếu cấu hình quá nhiều |
| `metrics` / `prometheus` | Monitoring | Lộ topology, label và thông tin vận hành; bị scrape gây tải |
| `gateway/routes`, `gateway/globalfilters` | Quan sát tuyến và bộ lọc | Lộ URI nội bộ, thứ tự filter, service names |
| `gateway/refresh` và thao tác thêm/xóa route | Quản trị tuyến động | Có thể tạo bypass, SSRF/open proxy hoặc DoS |
| `env`, `configprops`, `beans`, `mappings` | Chẩn đoán runtime | Lộ cấu trúc ứng dụng và metadata cấu hình, dù nhiều giá trị có thể được sanitize |
| `loggers` | Đọc/đổi log level | Nếu ghi được có thể bật DEBUG/TRACE và lộ headers/body nhạy cảm |
| `heapdump`, `threaddump`, `logfile` | Phân tích bộ nhớ/threads/logs | Có thể chứa token, thông tin cá nhân, dữ liệu nhạy cảm |
| `shutdown` | Dừng tiến trình (nếu bật) | Ngừng dịch vụ ngay lập tức |

Danh sách trên không có nghĩa tất cả endpoint đều được bật mặc định. Với Spring Boot 3.5/4.x, **web exposure mặc định thông thường chỉ có health**. Endpoint `gateway` có các quy tắc access riêng và được tài liệu Gateway khuyến nghị để **read-only** khi cần quan sát. Các endpoint nguy hiểm như shutdown/heapdump có giới hạn mặc định và không nên mở chỉ để thử nghiệm.

### 3.1. Hai nhóm use case nên có policy khác nhau

- **Probes tối thiểu:** liveness/readiness phục vụ điều phối workload. Chúng nên trả ít dữ liệu và không phụ thuộc credentials không thể cung cấp từ kubelet/health checker.
- **Quan sát/quản trị nâng cao:** routes, metrics chi tiết, config và thay đổi tuyến. Chỉ cho phép observability agent/operator được xác thực và có quyền rõ ràng, trên management network.

Nếu dùng Prometheus, `prometheus` chỉ có khi có exporter/registry tương ứng; việc expose tên endpoint mà thiếu dependency không tự tạo endpoint.

## 4. Kiến trúc đích: hai cổng, hai đường mạng

~~~mermaid
flowchart LR
    U["Internet / Mobile / Browser"] --> EDGE["Public Ingress / WAF<br/>TLS + auth + rate limiting"]
    EDGE --> API["Gateway WebFlux<br/>:8080 public API"]
    API --> B["Backend services<br/>route/filter/lb://"]
    OPS["Operators / Monitoring<br/>private identity"] --> FW["VPN / Private network<br/>Firewall + RBAC / mTLS"]
    FW --> MGMT["Actuator management listener<br/>:9090 private/loopback"]
    MGMT -.->|"same application, separate listener"| API
    X["Public clients"] -.- NOT["No route to :9090"]
~~~

Trên một máy local, có thể bind management listener vào **127.0.0.1**, cho phép ứng dụng và công cụ chạy trên chính máy truy cập. Trong Kubernetes hoặc VM nhiều mạng, có thể bind vào **private IP**/địa chỉ thích hợp và áp dụng network ACL/NetworkPolicy.

**Cổng khác chưa đủ:** nếu firewall/Ingress vẫn forward cả cổng 9090 từ Internet thì endpoint không được cô lập. Tương tự, chỉ viết rule deny `/actuator/**` ở public Ingress có thể bị vô hiệu khi base-path thay đổi hoặc khi Gateway có route trỏ tới management listener. Cần xác minh **đường mạng vật lý/ảo thật sự**.

### 4.1. Management port và application port

Hai địa chỉ ví dụ:

~~~text
Public / lab API       http://127.0.0.1:8080/api/ping
Local management       http://127.0.0.1:9090/actuator/health
Public external        https://api.example.test/api/orders
Private control plane  https://mgmt.internal.example.test/actuator/gateway/routes
~~~

Trong production, management listener chỉ nên có hostname/service riêng trên private network. Không dùng DNS “internal” làm biện pháp duy nhất nếu IP/cổng thực vẫn có route từ Internet.

## 5. Cấu hình baseline: Spring Boot 3.5/4.x + Gateway Server WebFlux

Spring Boot cho phép chạy Actuator trên cổng khác bằng `management.server.port` và chọn địa chỉ lắng nghe bằng `management.server.address`. **Theo tài liệu, địa chỉ management khác với ứng dụng chỉ được cấu hình khi cổng management khác cổng chính.**

### 5.1. Ví dụ lab cấu hình read-only

`src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: secure-gateway-actuator-lab

management:
  server:
    address: 127.0.0.1
    port: 9090

  # Chỉ endpoint được khai báo dưới đây mới có access.
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,gateway"
    jmx:
      exposure:
        exclude: "*"

  endpoint:
    health:
      access: read-only
      show-details: never
    info:
      access: read-only
    gateway:
      access: read-only
~~~

Điểm chính:

1. **API và management chạy hai port riêng**. Cả hai cùng bind loopback để lab an toàn; ở production, API có thể bind interface public/private sau ingress tùy hạ tầng nhưng management cần network riêng.
2. `management.endpoints.access.default=none` chọn chính sách **deny by default** ở cấp actuator endpoint.
3. `management.endpoints.access.max-permitted=read-only` giới hạn mức tối đa, giúp tránh vô tình bật thao tác ghi qua cấu hình endpoint riêng.
4. Chỉ `health`, `info` và `gateway` được cho phép truy cập dạng đọc; các endpoint khác không được cấp access bởi cấu hình này.
5. `exposure.include` chỉ HTTP expose đúng ba endpoint; `jmx.exposure.exclude="*"` giảm bớt bề mặt quản trị qua JMX nếu không dùng.
6. `show-details: never` tránh xuất chi tiết thành phần health cho bất kỳ caller nào trong lab này.
7. `gateway.access: read-only` **không cung cấp thao tác tạo, xóa hoặc refresh route**.

Các property `management.endpoint.<id>.access`, `management.endpoints.access.default` và `max-permitted` có trong tài liệu Spring Boot 3.5/4.x. Với những release cũ hơn, tên property hoặc semantics có thể khác; hãy đối chiếu configuration metadata của **đúng Boot patch** thay vì áp một cấu hình không nhận diện.

> **Không hiểu sai:** Config này cô lập về **mạng local** và giảm bề mặt endpoint, nhưng **không tự tạo một hệ thống danh tính admin**. Trên một máy có nhiều người dùng/process, một process local khác có thể gọi 127.0.0.1:9090 nếu OS policy cho phép. Với production, cần thêm xác thực, RBAC và network isolation.

### 5.2. Với API Gateway WebFlux 4.2/4.3 so với 5.x

Namespace của **Gateway routes** khác theo dòng:

| Thành phần | Gateway Server WebFlux 4.2/4.3 | Gateway Server WebFlux 5.x |
| --- | --- | --- |
| Route YAML | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Gateway starter (tùy patch) | `spring-cloud-starter-gateway` hoặc starter WebFlux riêng | `spring-cloud-starter-gateway-server-webflux` |
| Actuator management port | `management.server.port` | `management.server.port` |
| Actuator access/read-only | Do **Spring Boot** cung cấp, kiểm tra Boot version | Do **Spring Boot** cung cấp, kiểm tra Boot version |
| Gateway actuator | `management.endpoint.gateway.access=read-only` theo docs | Cùng access model, cần expose HTTP |

Không đặt Route YAML ở cả namespace cũ và mới. **Việc đổi namespace tuyến không khiến Actuator listener tự đổi cổng.** Quan hệ giữa Spring Boot, Spring Security và Spring Cloud cần được quản lý bằng BOM tương thích, không chỉ cập nhật một artifact độc lập.

### 5.3. Khi không cần HTTP management listener

Nếu tổ chức dùng công cụ quan sát khác hoặc không muốn mở Actuator qua HTTP:

~~~yaml
management:
  server:
    port: -1
~~~

Spring Boot cho phép tắt HTTP management endpoints bằng `management.server.port=-1`. Hoặc có thể loại tất cả khỏi HTTP exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
~~~

Hai cách khác nhau về implementation; lựa chọn tùy nhu cầu health checks và monitoring. Nếu JMX/khác vẫn được bật, phải xem xét bề mặt quản trị đó riêng.

### 5.4. Đổi base-path không phải phòng tuyến

~~~yaml
management:
  endpoints:
    web:
      base-path: /_ops
~~~

Khi management dùng cổng riêng, base-path được tính tương đối với `management.server.base-path`. Nếu dùng chung cổng, nó tương đối với context path/base path của web stack tương ứng. Cấu hình này có thể giúp tránh trùng tên endpoint, nhưng **không thay thế bảo mật**. Hãy dùng một đường dẫn nhất quán trong tests và rules của reverse proxy.

## 6. Lab: cổng API 8080 và Actuator chỉ có trên 9090

Lab này chỉ cần **một ứng dụng Gateway WebFlux có Actuator**. Để tránh phải dựng backend từ đầu khi kiểm tra hai listener, ta thêm một endpoint nhỏ trên chính Gateway. Endpoint này **không có mục đích thay thế route proxy**, chỉ giúp kiểm tra cổng dữ liệu có hoạt động.

### 6.1. Dependencies Maven

Với Gateway Server WebFlux phiên bản mới:

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

Spring Cloud BOM phải tương thích với Spring Boot. Ví dụ này **chưa bật Spring Security** để kiểm tra network isolation riêng; sẽ bổ sung lớp bảo vệ ở mục 8. Không dùng cấu hình không xác thực này cho management port có thể truy cập từ mạng không tin cậy.

### 6.2. Spring Boot application

`src/main/java/demo/gateway/ManagementIsolationApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementIsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementIsolationApplication.class, args);
    }
}
~~~

`src/main/java/demo/gateway/PingController.java`:

~~~java
package demo.gateway;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok", "source", "public-api"));
    }
}
~~~

Tạo `application.yml` theo mục 5.1 rồi chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`. Bài này đưa ra quy trình **tự chạy thử**, không khẳng định đã build hoặc chạy kiểm thử trong repository.

### 6.3. Kiểm tra API data plane

~~~bash
curl -i "http://127.0.0.1:8080/api/ping"
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok","source":"public-api"}
~~~

Endpoint trên port 8080 chỉ chứng minh **public/application listener** còn hoạt động. Nó không chứng minh một route `lb://...`, security filter hay backend thật đang khỏe.

### 6.4. Kiểm tra quản trị trên cổng riêng

~~~bash
# Truy cập qua management listener:
curl -i "http://127.0.0.1:9090/actuator/health"

curl -i "http://127.0.0.1:9090/actuator/info"

curl -i "http://127.0.0.1:9090/actuator/gateway/routes"
~~~

Trong **lab chưa có Spring Security**, request localhost tới ba endpoint được cho phép có thể trả 2xx. `health` thường có JSON như:

~~~json
{"status":"UP"}
~~~

Nếu chưa khai báo route nào, `/actuator/gateway/routes` có thể trả mảng rỗng hoặc các routes được cung cấp theo cơ chế hiện hành; không cần có backend để endpoint tồn tại. Status có thể khác nếu Spring Security đã được thêm từ dependency khác hoặc có custom security chain.

### 6.5. Test âm: đường public không được thấy Actuator

~~~bash
curl -i "http://127.0.0.1:8080/actuator/health"

curl -i "http://127.0.0.1:8080/actuator/gateway/routes"

curl -i "http://127.0.0.1:8080/actuator/env"

curl -i -X POST \
  "http://127.0.0.1:8080/actuator/gateway/refresh"
~~~

Kỳ vọng trong **lab không định nghĩa route/proxy nào trỏ tới Actuator**: các URL này **không được phục vụ như management endpoints** tại port 8080; thường sẽ trả 404 hoặc lỗi do handler/security khác. Quan trọng là:

- Không nhận JSON danh sách routes nội bộ.
- Không đọc được môi trường và cấu hình chi tiết.
- Không kích hoạt được refresh/create/delete tuyến.
- Không lộ thông tin ngoài phần API public được thiết kế.

**Bẫy:** Nếu Gateway có một route rất rộng `Path=/**` trỏ vào một backend khác, URL `/actuator/...` trên cổng công khai có thể **được proxy** và nhận một HTTP 200 từ backend. Vì thế, không được chỉ dựa vào status 404/200; cần xác định **response do thành phần nào tạo** và liệu có lộ management data thật không.

### 6.6. Test âm: read-only không cho quản trị ghi

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"

curl -i -X DELETE \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"
~~~

Với `management.endpoint.gateway.access=read-only` và `max-permitted=read-only`, **không được có tác dụng refresh/xóa tuyến** qua Actuator. Response cụ thể có thể là 404, 405 hoặc một status chặn tùy endpoint/version/security. Đừng cố ép mã HTTP trong test; hãy kiểm tra rằng route cache/route definitions **không bị thay đổi**.

Nếu các thao tác ghi thành công, đó là lỗi chính sách nghiêm trọng: kiểm tra active profile, property namespace, custom endpoint, actuator version và đường request đang được route tới đâu.

### 6.7. Test qua một máy khác

Việc gọi từ **localhost** chưa chứng minh cổng management không thấy từ mạng. Trên một máy test **được phép kiểm tra trong cùng mạng**, thử kết nối đến IP của máy chạy Gateway:

~~~bash
# Chỉ dùng IP test do quản trị hệ thống cấp:
curl -i --connect-timeout 2 \
  "http://192.0.2.10:9090/actuator/health"
~~~

`192.0.2.10` thuộc dải địa chỉ dành cho ví dụ tài liệu, **không phải IP của máy thật**. Thay bằng địa chỉ test hợp lệ do môi trường cung cấp. Khi management bind `127.0.0.1` và không có proxy/tunnel đặc biệt, client từ máy khác **không nên kết nối được** tới management listener. Nếu kết nối thành công, kiểm tra container port publishing, port-forward, firewall, reverse proxy và thực tế địa chỉ bind.

Tránh quét Internet hoặc các host bạn không quản lý. Đây là kiểm chứng **đường truy cập của hệ thống do bạn vận hành**.

### 6.8. Ma trận smoke test

| Nguồn request | URL | Mục đích | Kỳ vọng |
| --- | --- | --- | --- |
| Máy host, localhost | `:8080/api/ping` | API application | Trả 200 |
| Máy host, localhost | `:9090/actuator/health` | Health management | Đọc được theo policy |
| Máy host, localhost | `:9090/actuator/gateway/routes` | Route inventory | Read-only, có thể yêu cầu auth nếu đã bật Security |
| Máy host, localhost | `:9090/actuator/gateway/refresh` bằng POST | Thử operation ghi | Không được phép |
| Máy host, localhost | `:8080/actuator/gateway/routes` | Thử public bypass | Không được cung cấp management data |
| Máy khác trong mạng | `host-ip:9090/actuator/health` | Kiểm tra bind loopback | Không kết nối được trong lab |
| Client qua public Ingress | `https://api.example.test/actuator/...` | Kiểm tra đường public | Không thấy management endpoint |
| Monitoring đã được cấp quyền | Management address trong mạng riêng | Scrape/quan sát | Chỉ endpoint được phép, có auth/RBAC |

## 7. Ba lỗi thiết kế khiến “cổng riêng” vẫn không an toàn

### 7.1. Reverse proxy công khai cùng forward management port

Một proxy có thể cấu hình:

~~~text
Public /api/**       → Gateway :8080
Public /actuator/**  → Gateway :9090    <-- SAI
~~~

Đây là trường hợp tách cổng ở Spring Boot nhưng **ghép lại hai đường ở tầng Ingress**. Cách thiết kế đúng:

~~~text
Public hostname     → chỉ Gateway :8080
Private monitoring  → Gateway :9090 (network+identity riêng)
~~~

Không đưa port 9090 vào public Ingress rules, reverse proxy location, TCP LoadBalancer listener hoặc container publish ngoài ý muốn. Ưu tiên **allowlist đường vào public** hơn là hy vọng blacklist `/actuator/**` có thể bao mọi URL.

### 7.2. Route động của chính Gateway quay lại cổng quản trị

Ví dụ route nguy hiểm:

~~~yaml
# CẤU HÌNH SAI NGHIÊM TRỌNG - KHÔNG TRIỂN KHAI
- id: public-admin-proxy
  uri: http://127.0.0.1:9090
  predicates:
    - Path=/ops/**
  filters:
    - StripPrefix=1
~~~

Nếu có quyền sửa routes qua API động, một người có thể tạo tuyến từ cổng public tới **management listener nội bộ**. Browser không kết nối trực tiếp tới 9090, nhưng request đi qua Gateway 8080 rồi proxy tới 9090; **đường loopback từ process Gateway vẫn tới được**.

Đây là ví dụ **SSRF/open-proxy và quản trị bypass**. Phải:

1. Bảo vệ quyền **tạo/sửa/xóa RouteDefinition** bằng authorization nghiêm ngặt.
2. Có **allowlist URI scheme, hostname, port, route IDs, predicates và filters**.
3. Chặn destination thuộc loopback/link-local/metadata/private management addresses khi không được phép.
4. Đánh giá DNS resolution và redirects để tránh bypass allowlist kiểu DNS rebinding.
5. Thiết kế defense-in-depth ở management listener; không chỉ tin rằng nó chỉ nghe localhost.

Nếu dynamic route đã trỏ tới management port, việc đổi tên endpoint từ `/actuator` thành `/_ops` **không giải quyết bản chất vấn đề**.

### 7.3. Một Spring Security rule quá rộng

Ví dụ logic nguy hiểm:

~~~java
// SAI về mặt chính sách:
// .anyExchange().permitAll() trên toàn Gateway
// vì cho rằng management listener đã "private".
~~~

Nếu management port bị public bằng một lỗi hạ tầng, rule trên có thể khiến các endpoint đã expose dễ dàng bị đọc/gọi. Ngoài ra, nếu có **custom SecurityWebFilterChain**, cấu hình bảo mật mặc định của Spring Boot có thể **back off**: không được giả định actuator vẫn tự được khóa theo mặc định.

Khi dùng Spring Security, cần cấu hình endpoint-specific policy và application policy **đầy đủ**, không chỉ thêm một matcher cho `/actuator/**` rồi bỏ qua các request không khớp.

## 8. Spring Security Reactive: kiểm soát vai trò trên Actuator

Tách cổng hạn chế network reachability; **xác thực/phân quyền** xác định người dùng hoặc service identity nào được phép đọc thông tin quản trị. Trong một hệ thống có nhiều operator, chỉ có VPN hoặc IP allowlist không đủ để quy trách nhiệm cho từng hành động.

### 8.1. SecurityWebFilterChain chứ không phải Servlet SecurityFilterChain

Với Gateway Server **WebFlux**, sử dụng:

~~~text
ServerHttpSecurity
SecurityWebFilterChain
ServerWebExchangeMatcher
EndpointRequest (gói reactive)
~~~

Không sao chép ví dụ Servlet dùng `HttpSecurity`, `SecurityFilterChain` và `org.springframework.boot...servlet.EndpointRequest` sang Gateway WebFlux.

**Khác biệt import theo Spring Boot version:**

~~~java
// Spring Boot 3.5.x:
import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
~~~

~~~java
// Spring Boot 4.0.x:
import org.springframework.boot.security.autoconfigure.actuate.web.reactive.EndpointRequest;
~~~

Chọn **một dòng import**, không khai báo đồng thời. Đây là khác biệt do reorganize packages của Spring Boot; code Security còn lại có thể thay đổi theo Spring Security version, nên cần build với BOM chính xác.

### 8.2. Ví dụ phân quyền: health được đọc, routes chỉ cho OPS

Ví dụ ý tưởng hoàn chỉnh về **hai chuỗi WebFlux Security** trên Spring Boot 3.5:

~~~java
package demo.gateway.security;

import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class GatewaySecurityConfiguration {

    @Bean
    @Order(0)
    SecurityWebFilterChain actuatorSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeExchange(exchanges -> exchanges
                        .matchers(EndpointRequest.to("health")).permitAll()
                        .anyExchange().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/ping").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Đây là ví dụ về quy tắc Security; để có quyền truy cập thực tế cần cung cấp một `ReactiveUserDetailsService` hoặc identity provider với tài khoản/authority `ROLE_OPS` và password/credential được quản lý an toàn.** Không dùng mật khẩu cứng hoặc tài khoản demo trong production. Với Basic authentication, bắt buộc TLS trên mọi chặng đi qua mạng không tin cậy.

Diễn giải:

- Chuỗi có `@Order(0)` chỉ xử lý những endpoint match `EndpointRequest.toAnyEndpoint()`; health được phép đọc, routes đòi `ROLE_OPS`.
- Chuỗi `@Order(1)` xử lý các request ứng dụng còn lại; ví dụ chỉ `/api/ping` công khai.
- Boot không mặc định bổ sung một chuỗi bảo vệ API đầy đủ nếu bạn đã tự định nghĩa SecurityWebFilterChain.
- `EndpointRequest` hữu ích hơn hardcode `"/actuator/**"` vì Actuator có thể đổi base path và có nested endpoints.
- Ví dụ không tắt CSRF toàn cục. Với policy **read-only**, không cần bật thao tác thay đổi state chỉ để thử cấu hình.

**Quan trọng với management port riêng:** management listener có thể nằm trong **application context con** và có cơ chế khởi tạo/filter/security khác cổng chính. Không suy rằng hai bean SecurityWebFilterChain trên **chắc chắn** được áp dụng đúng cách ở cả hai port trong mọi cấu hình Boot. Hãy kiểm thử 401/403/2xx **trên cổng 9090 thực**, đồng thời xác nhận cổng 8080 vẫn bị bảo vệ. Khi cần custom quản trị phức tạp, đặt security configuration đúng context của management server theo tài liệu version/hạ tầng.

### 8.3. Role OPS không đồng nghĩa quyền ghi routes

Ngay cả user có `ROLE_OPS`, với:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    access:
      max-permitted: read-only
~~~

thao tác POST refresh hoặc xóa routes vẫn phải bị vô hiệu ở cấp endpoint. **Xác thực thành công không tự nâng quyền access level**.

Nếu tổ chức cần một nhóm **route admins** có quyền thay đổi tuyến, hãy tách rõ vai trò `OPS_READ` và `ROUTE_ADMIN`, các endpoint ghi chỉ bật trong một control plane được khóa nghiêm ngặt, có audit log và workflow approve/rollback. Đừng sử dụng quyền OPS đọc metrics để cấp luôn quyền thay đổi lưu lượng.

### 8.4. Không mở CORS cho management endpoints theo thói quen

Spring Boot Actuator có cấu hình CORS riêng dưới `management.endpoints.web.cors.*`. CORS không phải kiểm soát mạng hoặc authentication. Không đặt `allowed-origins: "*"` để một dashboard công khai gọi endpoint admin từ trình duyệt.

Nếu thật sự có UI quản trị cross-origin, hãy xác thực người dùng/service, chọn **origin cụ thể**, cấu hình CSRF/credentials và giữ endpoint ở management network; browser CORS check **không thay thế** firewall.

## 9. Triển khai Kubernetes: Ingress public khác Service quản trị

Trong Kubernetes, mục tiêu là:

- Ingress/LoadBalancer công khai **chỉ** truy cập cổng API `8080`.
- Monitoring hoặc operator trong cluster có thể truy cập cổng management `9090` qua một **Service riêng** hoặc port-forward/tunnel được cấp quyền.
- **NetworkPolicy** chỉ cho nguồn được phép đi tới 9090, không dựa vào tên Service “internal”.
- Health probes có đường vào và quyền phù hợp, không khiến Gateway bị restart hoặc rút khỏi traffic sai.

### 9.1. Địa chỉ bind khác localhost trong Pod

Trong lab trên máy đơn, `management.server.address=127.0.0.1` là hợp lý. Nhưng trong một Kubernetes Pod, kubelet và các Pod monitoring thường kết nối tới **Pod IP**, không phải loopback namespace của ứng dụng. Nếu chỉ bind `127.0.0.1`, chúng có thể **không kết nối** được tới cổng 9090, dù Service/Kubernetes object đã được tạo.

Một triển khai production có thể:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

management:
  server:
    address: 0.0.0.0
    port: 9090
~~~

**Đây không phải cấu hình cô lập chỉ bằng Spring Boot.** Nó chỉ làm listener lắng nghe trên mọi interface của container/Pod; phải kết hợp **Ingress không publish 9090, Service riêng, NetworkPolicy/firewall, authentication và TLS**. Cấu hình này chỉ phù hợp khi các lớp hạ tầng thực sự kiểm soát đường vào.

Một lựa chọn khác là giữ management trên loopback và cho một sidecar/agent trong **cùng Pod network namespace** scrape qua localhost rồi forward qua một kênh được bảo vệ. Cách đó cũng phải kiểm tra RBAC/identity và không mở tunnel công khai.

### 9.2. Hai Kubernetes Service nhưng chỉ một cái được public

Ví dụ cấu hình **minh họa**, selector `app: gateway` phải trùng label Deployment thực tế:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway-api
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - name: http-api
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: gateway-management
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - name: http-management
      port: 9090
      targetPort: 9090
~~~

Public Ingress chỉ tham chiếu Service `gateway-api`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gateway-public
spec:
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: gateway-api
                port:
                  number: 8080
~~~

Đây là đoạn tối giản để thấy **backend Service + port của Ingress**. Production cần IngressClass, TLS certificate/secret, policy xác thực và rate limiting phù hợp. **Không** tạo thêm Ingress public đến `gateway-management:9090`.

**ClusterIP không đồng nghĩa với bí mật.** Nếu NetworkPolicy không chặn, các Pod khác trong cluster có thể gọi Service quản trị. Cần giới hạn caller theo namespace/pod/service identity.

### 9.3. NetworkPolicy cho phép đúng nguồn vào từng port

Ví dụ chính sách **minh họa**: Pod có label `app=gateway` chỉ cho traffic API từ namespace ingress và management từ Prometheus trong namespace monitoring.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: gateway-ingress-isolation
spec:
  podSelector:
    matchLabels:
      app: gateway
  policyTypes:
    - Ingress
  ingress:
    # Data plane: chỉ ingress-controller namespace
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-system
      ports:
        - protocol: TCP
          port: 8080

    # Management plane: chỉ monitoring namespace
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app: prometheus
      ports:
        - protocol: TCP
          port: 9090
~~~

Điều kiện để policy trên có ý nghĩa:

1. CNI/network plugin phải **thực thi Kubernetes NetworkPolicy**.
2. Namespace/Pod labels phải **khớp đúng** thực tế; các tên trong ví dụ là giả định.
3. Xem xét nguồn health probe của kubelet, log collector, service mesh sidecar, egress/dns và các traffic khác để tránh vô tình chặn readiness/metrics.
4. Nếu yêu cầu mTLS hoặc identity ở mức service, thêm lớp phù hợp; NetworkPolicy dựa trên IP/labels không thay thế xác thực người gọi.
5. Kiểm tra các policy khác áp dụng cho cùng Pod: ingress permissions có thể là hợp của nhiều policy. Không có rule deny ưu tiên như firewall truyền thống.

### 9.4. Vì sao có Service quản trị riêng nhưng vẫn cần security?

Một Pod bị xâm nhập trong namespace monitoring có thể cố truy cập gateway-management. RBAC Kubernetes kiểm soát việc gọi Kubernetes API, **không tự bảo vệ HTTP endpoints bên trong Pod**. Vì vậy endpoint routes/metrics vẫn nên có service identity/Basic-over-TLS/OAuth2 hoặc mTLS và phân quyền tương ứng, tùy platform.

Không gắn role Kubernetes `cluster-admin` cho một scraper chỉ để lấy metrics. Scraper nên có quyền hẹp nhất, ví dụ chỉ GET `/actuator/prometheus`.

## 10. Health probes khi Actuator chạy trên cổng riêng

Spring Boot cung cấp health groups như:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
~~~

Trong Kubernetes, liveness/readiness thường được bật bởi môi trường; có thể chủ động bật:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Nếu có management port riêng, probe tới cổng 9090 có thể **thành công khi cổng ứng dụng 8080 không nhận request**. Đây là bẫy vận hành: management context khỏe không đồng nghĩa data plane khỏe.

Spring Boot hỗ trợ thêm các đường health trên **cổng ứng dụng**:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Khi cấu hình này hoạt động theo tài liệu version tương ứng:

~~~text
GET :8080/livez    → liveness
GET :8080/readyz   → readiness
GET :9090/actuator/health/liveness  → cùng health group, management port
GET :9090/actuator/health/readiness → cùng health group, management port
~~~

Đường `/livez` và `/readyz` là **ngoại lệ công khai có mục đích** trên cổng application, không phải mở toàn bộ `/actuator/**`. Các endpoint này nên trả ít thông tin, không có route inventory hoặc secrets.

### 10.1. Ví dụ probes trong Deployment

~~~yaml
# Một phần Pod container spec, không phải manifest Deployment đầy đủ
ports:
  - name: http-api
    containerPort: 8080
  - name: http-management
    containerPort: 9090

livenessProbe:
  httpGet:
    path: /livez
    port: http-api
  periodSeconds: 10
  timeoutSeconds: 2

readinessProbe:
  httpGet:
    path: /readyz
    port: http-api
  periodSeconds: 5
  timeoutSeconds: 2
~~~

Khi bật NetworkPolicy, cần kiểm tra kubelet có truy cập được cổng 8080 để probe hay không. Không đặt `management.server.address=127.0.0.1` rồi cấu hình probe qua Pod IP cổng 9090 mà cho rằng nó chắc chắn hoạt động.

### 10.2. Liveness khác readiness

| Probe | Hỏi điều gì? | Không nên làm |
| --- | --- | --- |
| **Liveness** | Process còn khả năng tự phục hồi/hoạt động? | Phụ thuộc vào Redis/DB chung gây restart hàng loạt khi một dependency lỗi |
| **Readiness** | Pod hiện có nên nhận traffic mới không? | Dùng một trạng thái quá hời hợt khi API listener đã hỏng |
| **Startup** | Ứng dụng đã khởi động xong chưa? | Để liveness giết process đang khởi động chậm hợp lệ |

Nếu Redis phục vụ rate limiter bị lỗi, hoặc service discovery tạm mất kết nối, chính sách readiness cần phản ánh mức độ ảnh hưởng thật. Không tự động buộc mọi instance Gateway restart chỉ vì một shared dependency unavailable; có thể tạo **cascading failure**.

### 10.3. Lựa chọn khi bắt buộc tách toàn bộ management khỏi public

Một số tổ chức không muốn cả `/livez`/`/readyz` bị expose ra public Ingress. Có thể:

- Để kubelet hoặc internal load balancer kiểm tra **trực tiếp Pod IP/cổng ứng dụng** mà không route health endpoint qua public Ingress.
- Expose health check qua endpoint nội bộ với firewall/Ingress rule có authentication hoặc IP allowlist.
- Dùng một cơ chế probe nội bộ không cần HTTP, nếu hạ tầng hỗ trợ và được kiểm thử.

Đừng xóa probe chỉ để ngăn Internet nhìn thấy status: cần tách **đường đến của probe** khỏi public traffic, không làm mất khả năng phát hiện Pod lỗi.

## 11. Prometheus, metrics và nguy cơ lộ dữ liệu quản trị

Nếu muốn scrape metrics:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Bổ sung endpoint Prometheus vào allowlist **chỉ khi có nhu cầu**:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,gateway,prometheus"
  endpoint:
    prometheus:
      access: read-only
~~~

Port và security policy vẫn giữ từ cấu hình baseline. Prometheus nên kết nối từ **monitoring namespace/host được cấp quyền** tới management port, không dùng public URL.

**Không mặc định metrics là dữ liệu vô hại.** Label có thể lộ route ID, service ID, backend host, tenant hoặc đường dẫn. Tránh dùng raw token, session ID, user ID hoặc path chứa dữ liệu cá nhân làm metric label, vì vừa lộ thông tin vừa gây high cardinality. Kiểm tra cả dữ liệu xuất qua Actuator Gateway routes/filter inventory.

### 11.1. Khi cần loggers, env hoặc threaddump

Không thêm `loggers`, `env`, `heapdump`, `threaddump` vào production expose chỉ vì đang điều tra sự cố. Nếu bắt buộc:

1. Dùng management plane riêng, xác thực đúng người trực ca và giới hạn thời gian.
2. Ghi audit ai mở, thời điểm, operation đọc/ghi và lý do.
3. Không bật giá trị env/config không sanitize nếu không cần.
4. Không cho bất kỳ người dùng monitoring read-only nào bật TRACE hoặc thay log level trên hệ thống chứa thông tin nhạy cảm.
5. Thu hồi quyền và quay về exposure allowlist nhỏ sau khi điều tra.

Các thao tác đổi log level là **write operation**; với `max-permitted=read-only` chúng không được phép, dù người gọi có vai trò quản trị ở tầng Security.

### 11.2. Thông tin nào vẫn có thể lộ dù không có secret?

`GET /actuator/gateway/routes` có thể thể hiện:

~~~json
[
  {
    "route_id": "payments-internal",
    "uri": "lb://payments-service",
    "order": 0
  }
]
~~~

Đây chỉ là JSON minh họa; định dạng thực tế có thể có predicate/filters và field khác theo version. Tên service và cấu trúc tuyến có thể hỗ trợ đối tượng tấn công lập bản đồ hệ thống. Do đó, **read-only vẫn là quyền nhạy cảm** và cần tách khỏi Internet.

## 12. TLS, xác thực và cơ chế truy cập quản trị từ xa

### 12.1. TLS là bắt buộc với management traffic qua mạng không tin cậy

Nếu management listener chỉ bind `127.0.0.1` và được gọi nội bộ trên cùng máy, HTTP có thể phù hợp cho lab. Nhưng khi traffic đi qua host/network khác hoặc tunnel không được bảo vệ, cần HTTPS/mTLS hoặc cơ chế mã hóa/kênh bảo mật tương đương.

Spring Boot cho phép một SSL context riêng khi management dùng cổng khác qua các property `management.server.ssl.*`. Cách thực tế có thể là:

- TLS trực tiếp ở management listener;
- TLS/mTLS qua internal ingress/service mesh/sidecar;
- Truy cập qua VPN/SSH tunnel hoặc công cụ điều phối có identity và audit;
- SSO/OAuth2 cho UI quản trị, client credentials/mTLS cho monitoring agents.

**Không tắt TLS certificate validation** để sửa lỗi hostname mismatch. Không đưa keystore password, Basic password hoặc API key trực tiếp vào repository, YAML mẫu hay lệnh có thể ghi shell history.

### 12.2. Quyền theo vai trò

| Vai trò | Quyền thông thường |
| --- | --- |
| Public API client | Không được gọi management endpoints |
| Health probe | Chỉ được đọc health/liveness/readiness tối thiểu |
| Metrics scraper | Chỉ đọc Prometheus/metrics cần thiết |
| SRE read-only | Xem health, routes, filters và thông tin quan sát đã phê duyệt |
| Route administrator | Có thể đề nghị/phê duyệt thay đổi routes qua control plane riêng |
| Break-glass admin | Quyền khẩn cấp, thời hạn ngắn, audit đầy đủ |

Không gộp mọi người vào một tài khoản shared `ops` có quyền unrestricted. **AuthN/AuthZ** phải được kiểm tra ở management endpoint, không trông vào header tự khai như `X-Admin: true`.

### 12.3. Nếu cần thay đổi routes động

Spring Cloud Gateway Actuator có các API:

~~~text
POST   /actuator/gateway/refresh
POST   /actuator/gateway/routes/{id}
DELETE /actuator/gateway/routes/{id}
GET    /actuator/gateway/routes
~~~

Với Gateway WebFlux 4.2/5.0, tài liệu khuyến nghị:

~~~properties
# Dùng cho quan sát, không cho tạo/xóa/refresh routes:
management.endpoint.gateway.access=read-only
~~~

Nếu **thật sự** cần thao tác ghi qua Actuator:

~~~properties
# CHỈ ở control plane được cô lập và phân quyền nghiêm ngặt:
management.endpoint.gateway.access=unrestricted
~~~

Khi bật unrestricted phải **không còn** cấu hình `management.endpoints.access.max-permitted=read-only` nếu bạn thật sự muốn operation ghi; đây là chủ đích đổi security posture, không phải thay một dòng vô hại. Cần security chain với role riêng, mTLS, allowlist destinations, kiểm tra filter/predicate, audit và rollback.

**Phương án nhiều tổ chức nên ưu tiên:** không expose write API của Actuator; thay vào đó cho pipeline/operator đã xác thực cập nhật một **RouteDefinitionRepository** qua giao diện được kiểm soát, phát `RefreshRoutesEvent` ở các replica và kiểm chứng runtime routes. Việc bảo vệ control plane vẫn bắt buộc trong phương án này.

### 12.4. Không nhầm endpoint read-only với bất biến hệ thống

Ngay cả khi `gateway.access=read-only`, routes vẫn có thể đổi qua **Config Server, Java code, DiscoveryClient, database hoặc workflow khác**. Read-only chỉ hạn chế thao tác thông qua Actuator endpoint tương ứng; nó không đóng băng toàn bộ route definitions hay kho discovery.

## 13. Troubleshooting: vì sao vẫn thấy hoặc không thấy Actuator?

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `localhost:9090/actuator/health` connection refused | Actuator không chạy port riêng, lỗi bind, app chưa khởi động | Log startup, `management.server.port/address` và process listener |
| Port 9090 mở nhưng `/gateway/routes` 404 | Endpoint chưa được cấp access hoặc web exposure | Actuator starter, `gateway.access` và exposure include |
| Port 9090 GET gateway trả 401 | Spring Security yêu cầu authentication | Dùng identity provider/credential hợp lệ, không bỏ auth |
| Port 9090 GET gateway trả 403 | Caller thiếu role/policy | Kiểm tra `ROLE_OPS`, SecurityWebFilterChain và management context |
| POST refresh trả 404/405/403 | Read-only access, CSRF hoặc security chặn | Xác nhận đây là **hành vi mong muốn** khi chỉ cho đọc |
| Port 8080 trả được `/actuator/gateway/routes` | Management trùng port, proxy vòng về 9090 hoặc custom controller | Xác minh response owner và route thực |
| Máy khác truy cập được 9090 dù định bind loopback | Proxy/NAT/port-forward, profile override, container publish | Đọc effective config và đường lắng nghe thực tế |
| Prometheus scrape 404 | Thiếu registry hoặc `prometheus` không access/expose | Dependencies và config |
| Health 9090 thành công nhưng API 8080 timeout | Management context riêng vẫn hoạt động | Probe main port và Netty data plane |
| Kubelet probe timeout với 127.0.0.1 | Kubelet gọi Pod IP, trong khi listener chỉ bind localhost Pod | Dùng main port health path hoặc interface private và NetworkPolicy |
| GET routes chỉ thấy ít hoặc không có tuyến | Routes chưa materialize hoặc sai namespace 4.x/5.x | Logs, route IDs, configuration metadata |
| Thêm Security chain khiến API 401 | Boot auto-security back off, fallback chain khác | Kiểm tra matcher, @Order và hai chains |
| Operator hợp lệ nhưng vẫn bị chặn | Boot 3/4 import/matcher sai hoặc security context khác | Build đúng BOM, test trên management port |
| Metrics có user/token/URI nhạy cảm | Labels hoặc exporter chưa được kiểm soát | Redact/đổi labels, giảm exposure |

### 13.1. Phân biệt lỗi kết nối với lỗi HTTP

- **Connection refused / timeout:** không có HTTP response từ endpoint; kiểm tra listener và mạng.
- **HTTP 404:** server HTTP đã trả lời nhưng không có handler phù hợp, hoặc một proxy/handler khác trả 404.
- **HTTP 401:** caller cần xác thực.
- **HTTP 403:** caller thiếu quyền, hoặc security/CSRF policy chặn.
- **HTTP 405:** path được phục vụ nhưng method/operation không có.

Không chuyển endpoint từ `read-only` sang `unrestricted` chỉ vì một thử nghiệm POST trả 404/405. Khi operation ghi bị khóa, đó có thể là **mục tiêu chính sách đã đạt**.

### 13.2. Những khác biệt phiên bản cần kiểm tra

| Đặc điểm | Đối chiếu |
| --- | --- |
| `management.endpoint.gateway.access` | Docs Gateway và Boot đang chạy |
| `management.endpoints.access.default/max-permitted` | Spring Boot 3.5/4.x configuration metadata |
| `EndpointRequest` reactive import | Boot 3.5: `org.springframework.boot.actuate.autoconfigure.security.reactive`; Boot 4.x: `org.springframework.boot.security.autoconfigure.actuate.web.reactive` |
| WebFlux routes | Gateway 4.x: `spring.cloud.gateway.routes`; 5.x: `spring.cloud.gateway.server.webflux.routes` |
| HTTP Actuator base path | `management.endpoints.web.base-path` và management context |
| SSL trên management port | `management.server.ssl.*` và ingress/service mesh |
| Gateway read-only | Không có write operations; kiểm chứng bằng negative tests |

**Luôn kiểm tra dependency versions thực tế** trước khi áp tài liệu: Spring Boot, Spring Security và Spring Cloud có thể thay đổi cách binding/auto-config giữa các dòng.

## 14. Kiểm thử tự động: xác minh cả điều được phép và điều bị chặn

Chỉ test một `GET /actuator/health = 200` là chưa đủ. Một bộ test cô lập quản trị phải có **negative tests**.

### 14.1. Ma trận chấp nhận bảo mật

| ID | Request | Điều kiện | Kỳ vọng |
| --- | --- | --- | --- |
| M01 | GET `:8080/api/ping` | Public test client | Được phục vụ |
| M02 | GET `:8080/actuator/health` | Public listener | Không xử lý như Actuator endpoint |
| M03 | GET `:8080/actuator/gateway/routes` | Public listener | Không lộ route inventory |
| M04 | POST `:8080/actuator/gateway/refresh` | Public listener | Không thay đổi routes |
| M05 | GET `:9090/actuator/health` | Internal health probe | Đọc tối thiểu theo policy |
| M06 | GET `:9090/actuator/gateway/routes` | Anonymous khi có Spring Security | Bị từ chối |
| M07 | GET `:9090/actuator/gateway/routes` | Operator đúng role | Read-only |
| M08 | POST `:9090/actuator/gateway/refresh` | Dù operator đã xác thực | Bị khóa bởi read-only access |
| M09 | GET `:9090/actuator/env` | Internal caller | Không expose theo allowlist |
| M10 | GET `:9090/actuator/heapdump` | Internal caller | Không expose |
| M11 | TCP tới port 9090 qua public network | External client | Không có đường kết nối |
| M12 | GET `:8080/readyz` | Kubelet/internal probe | Readiness tối thiểu nếu bật thêm health paths |
| M13 | Public hostname `/actuator/**` | Client từ Internet | Không bị proxy vào management context |
| M14 | Route động đích `127.0.0.1:9090` | Control-plane validation | Bị từ chối bởi destination policy |
| M15 | Pod ngoài allowlist truy cập management Service | Pod khác trong cluster | Bị NetworkPolicy/mTLS/RBAC chặn |

Ở M08, không chỉ quan sát HTTP status: cần xác nhận **route definitions và cache không thay đổi**. M14 nên kiểm tra loopback, link-local và metadata service; không để attacker lách URI allowlist bằng hostname hoặc DNS resolution khác.

### 14.2. Quan sát listener bằng công cụ hệ điều hành

Trên máy hoặc VM thử nghiệm có thể dùng công cụ TCP listener để xác nhận process bind vào địa chỉ nào:

~~~bash
# Ví dụ Linux; chỉ kiểm tra máy được phép quản trị
ss -lnt
~~~

Trên Windows có thể dùng `Get-NetTCPConnection`. **Kết quả từ OS không chứng minh được cấu hình Ingress/tunnel ở tầng khác**, nên vẫn phải test qua từng network boundary.

### 14.3. Kiểm thử trong pipeline triển khai

Một pipeline có thể:

1. Validate YAML, configuration metadata và dependency BOM.
2. Khởi động Gateway test với hai port riêng.
3. Test API application và health management.
4. Chạy negative tests các Actuator URLs trên **main port**.
5. Kiểm tra operation ghi của Gateway Actuator bị vô hiệu.
6. Test WebFlux Security với anonymous, monitoring role và ops role.
7. Deploy staging có Ingress/Service/NetworkPolicy thật, thử từ **ngoài** và **trong** cluster.
8. Chỉ rollout production khi đạt; tái kiểm tra sau thay đổi routing hoặc cấu hình.

Không mở firewall production cho một máy lạ chỉ để chạy test. Test runner phải ở trong management network được cấp quyền.

## 15. Observability cho management plane mà không làm lộ dữ liệu

### 15.1. Các tín hiệu nên quan sát

| Tín hiệu | Giá trị vận hành |
| --- | --- |
| Request count theo endpoint group | Phát hiện scan/truy cập bất thường |
| HTTP 401/403 đến management | Nhận biết caller sai quyền hoặc credential hết hạn |
| Route refresh/update events | Audit tác động tới tuyến, revision và operator |
| Routes count/hash/revision theo replica | Phát hiện route drift giữa các Gateway nodes |
| API latency/error rate riêng | Đo sức khỏe data plane, không nhầm với health management |
| Heap, direct memory, process RSS | Phát hiện memory pressure hoặc diagnostic overload |
| Liveness/readiness | Phát hiện node bị hỏng hoặc chưa sẵn sàng |
| Prometheus scrape success/error | Biết metrics pipeline có hoạt động |

Những tên metrics trên chỉ là **các tín hiệu cần có**, không mặc định là tên đã được Spring Cloud Gateway xuất ra. Tùy Spring Boot/Micrometer version, bạn có thể cần tạo riêng metrics hoặc gắn dashboard với metrics tích hợp.

**Không đưa raw access token, cookie session, principal ID từng người, raw IP hay path chứa PII vào metric labels.** Chúng vừa gây high cardinality vừa làm lộ dữ liệu. Audit log nên ghi principal **đã xác thực**, action, endpoint group, result và correlation ID đã được kiểm soát; tránh log full query string nếu có secret.

### 15.2. Những cảnh báo nên có

- Bất kỳ public hostname nào đọc được route inventory hoặc Actuator diagnostics không nằm trong public policy.
- `gateway.access=unrestricted` xuất hiện ngoài change window.
- Role chỉ đọc kích hoạt được refresh hoặc DELETE route.
- Route inventory trên từng replica khác revision được phê duyệt.
- Quá nhiều 401/403 ở management port; cân nhắc dấu hiệu credential stuffing/scan.
- Tăng đột biến yêu cầu tới `env`, `heapdump`, `loggers`, `threaddump`.
- Health probe thành công trên management port nhưng API port không nhận request.
- Prometheus scrape bị mất hoặc latency quản trị tăng cao.

Khi alert, đừng sao chép nguyên dump, env hoặc token vào chat/công cụ ticket không được phê duyệt.

### 15.3. Incident runbook: phát hiện Actuator lộ ra Internet

1. **Chặn ngay public ingress/firewall** tới management port và mọi route proxy vòng vào Actuator.
2. Tạm ngưng quyền ghi bằng access level/read-only hoặc vô hiệu endpoint nếu cần; xác nhận thao tác thực sự được chặn.
3. Rà soát audit trail/route revisions xem có thay đổi RouteDefinition/filter trái phép không.
4. Nếu credential/secret có khả năng lộ, thực hiện quy trình rotate/revoke tương ứng.
5. Kiểm tra các đường phụ: NodePort, LoadBalancer TCP, Ingress routes, port-forward, sidecar, Service và JMX.
6. Chạy lại ma trận positive/negative tests từ **public** và **private** network.
7. Tạo guardrail CI/CD để tránh tái diễn, ghi nguyên nhân và biện pháp giảm thiểu.

Không phải mọi Actuator read-only exposure đều đồng nghĩa dữ liệu đã bị trích xuất; cần điều tra logs/evidence có căn cứ, không suy đoán về tác động.

## 16. Những ngộ nhận và phản ví dụ

**A — “Đổi đường dẫn thành /secret-admin là an toàn.”**

Không. Route/path có thể bị dò, lộ cấu hình hoặc rewrite ở proxy. Phòng thủ cần network isolation, authentication và authorization.

**B — “Port 9090 riêng nên ai cũng có thể đọc routes.”**

Không. Nếu cổng được NAT/Ingress từ Internet, route inventory vẫn có thể lộ topology. Port riêng là điều kiện kiến trúc, không phải bảo đảm security.

**C — “Có dependency Spring Security nên Actuator tự khóa mọi thứ.”**

Không được giả định. Custom `SecurityWebFilterChain` có thể làm Boot auto-security back off. Test đúng các chains trên cổng quản trị.

**D — “gateway.access=read-only nên không cần quan tâm đường public.”**

Không. Read-only có thể lộ internal service names, route filters và metadata; nó không thay thế firewall.

**E — “Bind 127.0.0.1 thì Gateway không thể đi vào Actuator.”**

Không. Một route trong chính Gateway có thể proxy đến `127.0.0.1:9090` từ process local; phải dùng destination allowlist và security trên management plane.

**F — “Health 9090 UP chắc chắn API 8080 khỏe.”**

Không luôn đúng. Management context riêng có thể tiếp tục phản hồi khi application listener lỗi; cần health qua main port hoặc request probe thực sự.

**G — “Kubernetes ClusterIP đủ để bảo vệ management.”**

Không. Những Pod khác trong cluster có thể kết nối nếu NetworkPolicy không chặn. Service type không phải cơ chế xác thực HTTP.

**H — “Thêm /actuator/** vào CORS denylist là xong.”**

Không. CORS chỉ được browser thực thi và không chặn curl, service-to-service client hay route nội bộ. Hãy khóa ở mạng, endpoint access và identity.

## 17. Checklist trước khi triển khai production

- [ ] Phân loại rõ **data plane / management plane**, cổng, hostname và network owner.
- [ ] Management listener chạy cổng riêng hoặc tắt nếu không cần HTTP.
- [ ] Với local/VM, management bind loopback/private IP đúng; với Kubernetes đã kiểm tra Pod IP và kubelet probes.
- [ ] Public Ingress chỉ chuyển tiếp cổng API; không có NodePort/LoadBalancer/Ingress công khai vào management port.
- [ ] Management Service đi qua network riêng và NetworkPolicy/firewall/mTLS theo policy.
- [ ] Đặt `management.endpoints.access.default=none`, khai báo allowlist endpoint có chủ đích.
- [ ] Có `max-permitted=read-only` nếu chỉ cần các thao tác đọc.
- [ ] Đặt `management.endpoint.gateway.access=read-only`, không bật unrestricted thường trực.
- [ ] Web exposure chỉ gồm health/info/gateway/prometheus thật sự cần; không dùng `"*"` tùy tiện.
- [ ] JMX và các management transports khác đã được xem xét.
- [ ] Không expose env/configprops/heapdump/shutdown/loggers khi không có nhu cầu kiểm soát chặt.
- [ ] WebFlux Security có EndpointRequest reactive matcher và policy tương thích đúng Boot version.
- [ ] Kiểm chứng security trên **management port thực**, không chỉ kiểm tra code Java.
- [ ] Operator/monitoring identities được phân vai và least privilege, không dùng tài khoản dùng chung quá rộng.
- [ ] TLS/mTLS hoặc kênh bảo mật tương đương cho quản trị qua mạng; không hardcode credentials.
- [ ] Health probes cung cấp thông tin tối thiểu; main-port liveness/readiness đã được kiểm thử.
- [ ] Dynamic RouteDefinitions không thể proxy vào localhost/management/link-local/metadata service ngoài allowlist.
- [ ] Không tin client-supplied `X-Forwarded-*` khi chưa có proxy trust boundary.
- [ ] Có positive test API/health và **negative test public Actuator** sau mỗi thay đổi cấu hình.
- [ ] Có kiểm tra GET routes chỉ có quyền đọc, POST refresh/DELETE route bị từ chối.
- [ ] Logs/metrics/audit không chứa secrets, token, session IDs hoặc PII.
- [ ] Có runbook chặn management exposure, rollback và kiểm tra sau incident.

## 18. Tự kiểm tra kiến thức

**1. `management.server.port=9090` có tự chặn client Internet không?**

Không. Nếu Ingress, reverse proxy, NAT hoặc firewall mở cổng đó ra Internet, client vẫn có thể kết nối. Cần kiểm soát network path và security.

**2. Access khác exposure như thế nào?**

`access` xác định endpoint có tồn tại và operation nào được phép; `exposure.include` xác định endpoint nào được đưa ra HTTP. Cả hai không thay thế xác thực người gọi.

**3. Có thể đặt management address khác main address khi dùng cùng port không?**

Theo tài liệu Spring Boot, việc bind `management.server.address` độc lập chỉ có thể làm khi **management port khác application port**.

**4. Tại sao phải định nghĩa security chain cho ứng dụng sau khi thêm chain riêng cho Actuator?**

Vì cấu hình custom WebFlux Security có thể làm Boot auto-security back off. Một chain chỉ match Actuator không tự bảo vệ các routes API còn lại.

**5. Vì sao một route mới có `uri: http://127.0.0.1:9090` rất nguy hiểm?**

Nó biến Gateway public thành proxy đến Actuator loopback, có thể vượt qua cách cô lập dựa vào cổng/địa chỉ. Cần URI destination allowlist và quyền quản trị chặt chẽ.

**6. Vì sao có thể nên bật `management.endpoint.health.probes.add-additional-paths=true`?**

Để liveness/readiness cũng được kiểm tra qua **application port** tại `/livez` và `/readyz`, giúp tránh false-positive khi management listener khỏe mà data plane không nhận request.

**7. ClusterIP Service có bảo đảm chỉ monitoring Pod truy cập được không?**

Không. Cần NetworkPolicy, service identity và có thể mTLS để giới hạn nguồn và quyền.

**8. Khi nào mới chấp nhận bật `gateway.access=unrestricted`?**

Chỉ khi có quy trình quản trị tuyến có kiểm soát: management network, authentication/RBAC, audit, change approval, URI allowlist, rollback và negative security tests. Không bật như mặc định public.

## 19. Tài liệu chính thức

1. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): access levels, exposure, security, sanitization và Kubernetes probes.
2. [Spring Boot 4.0 — Actuator Endpoints](https://docs.spring.io/spring-boot/4.0/reference/actuator/endpoints.html): `management.endpoints.access.default/max-permitted`, endpoint security và health groups.
3. [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): `management.server.port/address`, management-specific SSL, base-path và tắt HTTP management.
4. [Spring Cloud Gateway Server WebFlux 5.0 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html): `gateway.access=read-only/unrestricted`, routes, filters và refresh.
5. [Spring Cloud Gateway WebFlux 4.2 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/actuator-api.html): hành vi endpoint và mức truy cập ở bản 4.2.
6. [Spring Boot 3.5 — Reactive EndpointRequest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/security/reactive/EndpointRequest.html): matcher cho Actuator trên WebFlux.
7. [Spring Boot 4.0 — Reactive EndpointRequest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/security/autoconfigure/actuate/web/reactive/EndpointRequest.html): package thay đổi trong Boot 4.x.
8. [Spring Security — WebFlux Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain` và phân quyền request reactive.
9. [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): ingress/egress policy giữa các Pod/namespace khi CNI hỗ trợ.
10. [Kubernetes — Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/): public routing tới đúng Service/port.

**Ghi nhớ:** **Cô lập Actuator không phải đổi đường dẫn hay bật Spring Security đơn lẻ.** Một Gateway WebFlux an toàn cần **đường/cổng quản trị riêng**, endpoint allowlist và mức **read-only** khi chỉ quan sát, **xác thực/phân quyền**, TLS và chính sách Ingress/NetworkPolicy phù hợp. Sau triển khai phải kiểm chứng từ **cả public lẫn private network**, thử các operation ghi bị chặn, ngăn đường proxy vòng vào management listener và bảo đảm health probes vẫn kiểm tra được hoạt động thật của data plane.
