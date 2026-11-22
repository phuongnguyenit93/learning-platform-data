# GraphQL endpoint readiness

Một ứng dụng Spring for GraphQL chỉ nên nhận traffic khi HTTP server đã khởi động, GraphQL schema đã được nạp và các thành phần bắt buộc để phục vụ request đã sẵn sàng. Trong môi trường container, Kubernetes cần biết lúc nào nên gửi request tới pod, lúc nào nên khởi động lại process và lúc nào nên chờ ứng dụng hoàn tất startup.

Ba trạng thái này có liên quan nhưng không giống nhau. Liveness cho biết process còn hoạt động và không bị kẹt đến mức cần khởi động lại. Readiness cho biết instance có thể nhận traffic tại thời điểm hiện tại. Startup probe cho Kubernetes biết ứng dụng đã qua giai đoạn khởi động ban đầu hay chưa.

Spring Boot Actuator cung cấp health endpoint và các health group cho readiness/liveness. Spring for GraphQL cung cấp GraphQL endpoint và runtime thực thi schema. Kết hợp hai phần này giúp triển khai GraphQL service có kiểm tra sức khỏe rõ ràng, tránh đưa pod chưa sẵn sàng vào load balancer và xử lý shutdown có trật tự.

## 1. Phân biệt GraphQL endpoint và health endpoint

GraphQL endpoint là nơi client gửi GraphQL operation, thường có đường dẫn `/graphql`. Health endpoint là nơi nền tảng vận hành kiểm tra trạng thái của ứng dụng, thường được cung cấp bởi Spring Boot Actuator.

Ví dụ:

| Endpoint | Mục đích | Người gọi thường gặp |
| --- | --- | --- |
| `/graphql` | Thực thi query, mutation hoặc subscription transport | Web/mobile client, service khác |
| `/actuator/health` | Trạng thái sức khỏe tổng quát | Operator, monitoring |
| `/actuator/health/liveness` | Kiểm tra process có còn sống | Kubernetes liveness probe |
| `/actuator/health/readiness` | Kiểm tra instance có thể nhận traffic | Kubernetes readiness probe |
| `/livez` | Liveness probe trên cổng ứng dụng | Kubernetes |
| `/readyz` | Readiness probe trên cổng ứng dụng | Kubernetes |

Không nên cấu hình Kubernetes gọi trực tiếp `/graphql` để kiểm tra readiness. GraphQL HTTP transport thường được gọi bằng POST và cũng có thể hỗ trợ GET cho query tùy cấu hình; tuy nhiên kubelet chỉ gửi HTTP GET tới path, không kèm GraphQL document và variables hợp lệ. Request đó có thể bị từ chối hoặc trả lỗi transport dù ứng dụng vẫn khỏe.

Ngay cả khi gửi một query hợp lệ, HTTP status cũng không phải lúc nào phản ánh kết quả nghiệp vụ. GraphQL có thể trả HTTP 200 cùng trường `errors` khi một field resolver gặp lỗi trong quá trình thực thi. Vì vậy, health probe nên gọi health endpoint chuyên biệt; kiểm tra chức năng GraphQL thực tế nên là một synthetic test riêng.

## 2. Ba trạng thái startup, liveness và readiness

**Startup** trả lời câu hỏi: ứng dụng đã hoàn tất giai đoạn khởi động ban đầu chưa? Trong lúc startup chưa hoàn tất, Kubernetes chưa cần đánh giá liveness/readiness theo chu kỳ thông thường. Startup probe hữu ích với ứng dụng cần thời gian nạp schema lớn, khởi tạo cache hoặc chạy warm-up.

**Liveness** trả lời câu hỏi: process có còn khả năng tiếp tục chạy không? Nếu liveness thất bại liên tục, Kubernetes có thể khởi động lại container. Không nên đưa database hoặc dịch vụ ngoài vào liveness vì một dependency tạm thời lỗi có thể khiến tất cả pod khởi động lại cùng lúc.

**Readiness** trả lời câu hỏi: instance có thể nhận request mới không? Nếu readiness thất bại, Kubernetes loại pod khỏi các endpoint phục vụ traffic. Container vẫn chạy để ứng dụng có cơ hội phục hồi.

Có thể hình dung vòng đời như sau:

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: Startup completed
    Ready --> NotReady: Required dependency unavailable
    NotReady --> Ready: Dependency recovered
    Ready --> Stopping: Termination begins
    NotReady --> Stopping: Termination begins
    Stopping --> [*]
~~~

Một pod `NotReady` không nhất thiết cần restart. Ví dụ database mất kết nối trong thời gian ngắn: readiness có thể chuyển DOWN để ngừng nhận request, trong khi liveness vẫn UP để process chờ kết nối phục hồi.

## 3. GraphQL schema readiness hình thành khi nào?

Với Spring Boot GraphQL starter, Spring Boot tạo `GraphQlSource` từ schema SDL và runtime wiring. Quá trình khởi tạo ứng dụng bao gồm đọc schema, parse, validate và xây dựng runtime phù hợp.

Schema không hợp lệ, type reference sai hoặc runtime wiring có cấu hình không thể khởi tạo thường làm application context startup thất bại. Trong trường hợp đó, web server không nên được xem là đã sẵn sàng để nhận GraphQL traffic.

Các bước khái quát:

~~~mermaid
flowchart TD
    A[Load application configuration] --> B[Create GraphQlSource]
    B --> C[Load SDL resources]
    C --> D[Parse and validate schema]
    D --> E[Apply RuntimeWiringConfigurer]
    E --> F[Create GraphQL runtime]
    F --> G[Start web server]
    G --> H[ApplicationReadyEvent]
    H --> I[Readiness becomes accepting traffic]
~~~

Readiness health group của Spring Boot sử dụng application availability state. Khi ứng dụng đã hoàn tất startup và chuyển sang trạng thái accepting traffic, health indicator readiness mới phản ánh trạng thái sẵn sàng.

Lưu ý: schema được khởi tạo thành công không chứng minh mọi resolver đều hoạt động đúng với database, remote service hoặc dữ liệu thực tế. Readiness cần kiểm tra thêm các dependency thiết yếu; integration test và synthetic GraphQL probe cần kiểm tra hành vi operation.

## 4. Thêm Spring Boot Actuator

Ứng dụng cần GraphQL starter và Actuator. Ví dụ Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")

    // Add the database driver and data-access starter used by the application.
}
~~~

GraphQL starter cung cấp endpoint và execution runtime. Actuator cung cấp health infrastructure, health indicators và các health endpoint.

Nếu ứng dụng dùng JDBC hoặc JPA, health indicator `db` có thể được tự cấu hình khi có các thành phần database phù hợp trên classpath. Nếu không có datasource, không thêm `db` vào readiness group. Nếu service dùng dependency khác như Redis hoặc một catalog service, hãy quyết định dependency đó có thực sự cần thiết để xử lý request hay không trước khi thêm health indicator tương ứng.

## 5. Cấu hình GraphQL và health probes

Ví dụ cấu hình trong `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  graphql:
    path: /graphql

management:
  endpoints:
    web:
      exposure:
        include: health,info

  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Các cấu hình chính:

- `spring.graphql.path` đặt đường dẫn GraphQL HTTP endpoint.
- `management.endpoints.web.exposure.include` chỉ công khai các Actuator endpoint được chọn qua HTTP.
- `management.endpoint.health.probes.enabled` bật health group cho liveness và readiness.
- `management.endpoint.health.probes.add-additional-paths` tạo thêm `/livez` và `/readyz` trên cổng HTTP chính của ứng dụng.
- `liveness.include` chỉ chứa `livenessState`.
- `readiness.include` chứa `readinessState` và `db` trong ví dụ có database thiết yếu.
- `show-details: never` tránh công khai chi tiết health không cần thiết.

Nếu ứng dụng không dùng database, readiness group có thể chỉ gồm `readinessState`. Nếu có dependency bắt buộc khác, thêm health indicator tương ứng sau khi đánh giá timeout và hành vi khi dependency mất kết nối.

Tên và đường dẫn health group mặc định là `/actuator/health/liveness` và `/actuator/health/readiness`. Khi bật additional paths, `/livez` và `/readyz` giúp kubelet gọi probe qua cùng cổng ứng dụng đang phục vụ GraphQL.

Không đưa `db` vào liveness group. Database tạm thời không sẵn sàng không đồng nghĩa process cần restart.

## 6. Có nên đưa database vào readiness?

Câu trả lời phụ thuộc vào khả năng phục vụ request khi database mất kết nối.

Nếu gần như mọi query/mutation đều cần database, pod không thể xử lý request có ích khi database DOWN. Đưa `db` vào readiness giúp ngừng gửi traffic mới tới instance đó.

Nếu GraphQL service có thể tiếp tục phục vụ phần lớn request bằng cache hoặc dữ liệu độc lập, việc đưa database vào readiness có thể làm pod bị loại khỏi traffic dù vẫn có thể phục vụ một số operation. Khi đó, có thể chỉ dùng `readinessState` cho probe cơ bản và theo dõi database bằng alert riêng; hoặc thiết kế readiness indicator theo dependency thực sự bắt buộc.

Không nên đưa tất cả dịch vụ ngoài vào readiness một cách mặc định. Một dependency phụ trợ lỗi có thể khiến toàn bộ GraphQL API mất khả năng phục vụ dù những operation không phụ thuộc vào nó vẫn chạy được.

Cũng cần kiểm soát tần suất health check. Health indicator nên có timeout ngắn, không thực hiện truy vấn nặng và không tạo thêm tải lớn lên dependency trong lúc hệ thống đang gặp sự cố.

## 7. Health indicator cho dependency thiết yếu

Nếu ứng dụng có một dependency không được Actuator tự hỗ trợ, có thể tạo custom `HealthIndicator`.

Ví dụ một catalog service là bắt buộc cho các query tìm kiếm:

~~~java
package com.example.catalog.health;

import com.example.catalog.client.CatalogClient;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("catalog")
public class CatalogHealthIndicator implements HealthIndicator {

    private final CatalogClient catalogClient;

    public CatalogHealthIndicator(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @Override
    public Health health() {
        boolean available = catalogClient.isAvailable();

        if (available) {
            return Health.up().build();
        }

        return Health.down()
            .withDetail("dependency", "catalog")
            .build();
    }
}
~~~

Sau đó thêm `catalog` vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,catalog
~~~

Đoạn code chỉ minh họa cấu trúc. Trong thực tế, `isAvailable()` phải có timeout hữu hạn và tránh retry kéo dài. Với client reactive, dùng `ReactiveHealthIndicator` và giới hạn thời gian cho publisher thay vì block event-loop.

Không đưa URL nội bộ, credential, stack trace hoặc thông tin kết nối nhạy cảm vào health details. Health endpoint có thể được nhiều hệ thống monitoring truy cập; chỉ cung cấp thông tin đủ để operator phân loại sự cố.

## 8. Cổng management riêng và additional probe paths

Một số hệ thống đặt Actuator trên cổng riêng:

~~~yaml
management:
  server:
    port: 8081
~~~

Nếu kubelet kiểm tra readiness trên cổng management riêng, probe có thể báo UP trong khi cổng chính phục vụ GraphQL không mở được hoặc có vấn đề ở web server chính.

Spring Boot có tùy chọn additional probe paths để đặt `/livez` và `/readyz` trên cổng server chính. Đây là lựa chọn phù hợp khi muốn health probe xác nhận chính web server nhận GraphQL traffic vẫn hoạt động.

Nếu dùng cổng management riêng, hãy cân nhắc:

- Probe nội bộ cần gọi cổng nào.
- Network policy có cho kubelet truy cập cổng đó không.
- Cổng chính có cần additional paths hay không.
- Health endpoint có được bảo vệ và giới hạn exposure phù hợp không.

Không nên mở toàn bộ Actuator endpoint ra Internet chỉ để Kubernetes đọc health. Chỉ expose `health` (và `info` nếu cần), sau đó giới hạn truy cập bằng network policy, firewall hoặc Spring Security.

## 9. Cấu hình Kubernetes startup, liveness và readiness probes

Ví dụ deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-graphql
spec:
  replicas: 3
  selector:
    matchLabels:
      app: spring-graphql
  template:
    metadata:
      labels:
        app: spring-graphql
    spec:
      containers:
        - name: spring-graphql
          image: example/spring-graphql:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Ý nghĩa:

- `startupProbe` cho phép ứng dụng có tối đa khoảng 150 giây để qua giai đoạn startup theo cấu hình ví dụ. Trong khoảng này, Kubernetes chưa dùng liveness/readiness để kết luận container cần restart hoặc nhận traffic.
- `livenessProbe` kiểm tra process định kỳ. Nếu thất bại liên tiếp theo ngưỡng, Kubernetes restart container.
- `readinessProbe` kiểm tra khả năng nhận traffic. Khi thất bại, pod bị loại khỏi Service endpoints cho tới khi phục hồi.

Các con số chỉ là ví dụ. Hãy chọn `periodSeconds`, `timeoutSeconds` và `failureThreshold` dựa trên thời gian khởi động, độ trễ health check và khả năng phục hồi của hệ thống. Timeout quá thấp có thể gây false negative khi node đang quá tải.

## 10. Readiness không thay thế synthetic GraphQL test

Health endpoint xác nhận trạng thái ứng dụng và các dependency được cấu hình. Nó không chứng minh một GraphQL operation cụ thể trả đúng dữ liệu.

Một synthetic test có thể gửi query chỉ đọc tới GraphQL endpoint theo lịch:

~~~graphql
query ReadinessCheck {
    serviceStatus {
        status
    }
}
~~~

Ví dụ field `serviceStatus` phải là field được thiết kế riêng cho kiểm tra chức năng, có semantics ổn định và không làm thay đổi dữ liệu. Không nên thêm một field health giả chỉ để trả về chuỗi `OK` mà không kiểm tra thành phần quan trọng nào.

Một synthetic test nên kiểm tra:

- HTTP endpoint nhận được request.
- Authentication hoặc client credential hoạt động.
- GraphQL document được validate và thực thi.
- Resolver quan trọng có thể truy cập dependency cần thiết.
- Response có shape và giá trị mong đợi.

Synthetic test có thể chạy từ monitoring system hoặc deployment smoke test. Không nên dùng query có side effect làm Kubernetes readiness probe vì probe chạy lặp lại và có thể tạo dữ liệu không mong muốn.

## 11. Kiểm tra GraphQL endpoint và health endpoint

Có thể kiểm tra thủ công sau khi deploy:

~~~bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
curl -i -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query { books { id title } }"}'
~~~

Hai health endpoint thường trả trạng thái HTTP 200 khi UP và trạng thái không thành công khi DOWN. GraphQL endpoint cần document và payload phù hợp với schema của ứng dụng.

Nếu dùng endpoint `/actuator/health/readiness` thay cho additional path, hãy gọi đúng đường dẫn Actuator đó. Không suy ra readiness chỉ từ việc `/graphql` trả HTTP 200; hãy kiểm tra body và lỗi GraphQL khi chạy synthetic test.

Khi bật authentication cho GraphQL, synthetic test phải dùng credential phù hợp. Kubernetes health probe thường không nên cần token người dùng; vì vậy health endpoint cần chính sách truy cập nội bộ riêng, an toàn và đơn giản.

## 12. Kiểm thử readiness health group

Có thể kiểm tra health endpoint bằng integration test. Ví dụ dùng MockMvc:

~~~java
package com.example.graphql.health;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReadinessEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readinessEndpointIsAvailableAfterStartup() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
            .andExpect(status().isOk());
    }
}
~~~

Test này giả định ứng dụng expose Actuator health endpoint và readiness group đang UP. Nếu cấu hình chỉ expose additional path trên main server hoặc management server port riêng, hãy kiểm tra đúng endpoint trong môi trường integration tương ứng.

Ngoài health endpoint, nên có test GraphQL runtime:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GraphQlRuntimeTests {

    @Autowired
    ExecutionGraphQlService graphQlService;

    @Test
    void schemaCanExecuteARepresentativeQuery() {
        GraphQlTester tester =
            ExecutionGraphQlServiceTester.create(graphQlService);

        tester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
            .execute()
            .errors()
            .verify();
    }
}
~~~

Test thứ hai xác nhận schema và resolver có thể thực thi operation đại diện. Nó không thay thế health probe trong runtime, nhưng phát hiện lỗi wiring hoặc schema contract trước khi phát hành.

## 13. Graceful shutdown và ngừng nhận traffic

Readiness cũng quan trọng khi pod được triển khai mới hoặc bị terminate. Khi ứng dụng bắt đầu shutdown, nó cần ngừng nhận request mới và cho request đang chạy thời gian hoàn tất.

Cấu hình Spring Boot:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Với graceful shutdown, web server ngừng nhận kết nối mới và chờ request đang xử lý trong khoảng thời gian được cấu hình. Kubernetes cũng cần có `terminationGracePeriodSeconds` đủ dài để quá trình drain traffic và shutdown hoàn tất.

Ví dụ:

~~~yaml
spec:
  terminationGracePeriodSeconds: 40
~~~

Giá trị ở đây chỉ minh họa; nên đặt lớn hơn tổng thời gian cần cho load balancer cập nhật endpoints, request đang chạy kết thúc và Spring hoàn tất shutdown.

Subscription qua WebSocket hoặc stream dài có vòng đời khác HTTP request ngắn. Khi deploy, cần chính sách reconnect ở client, giới hạn thời gian session hoặc cơ chế thông báo reconnect nếu hệ thống yêu cầu không gián đoạn.

Không dựa vào readiness để đảm bảo mọi request đang chạy đã kết thúc. Readiness ngăn traffic mới được điều phối tới pod; graceful shutdown quản lý việc hoàn tất request hiện có.

## 14. Readiness khi warm-up hoặc phụ thuộc không sẵn sàng

Một số GraphQL service cần warm-up cache, tải metadata hoặc đồng bộ schema từ hệ thống khác trước khi nhận traffic. Nếu công việc này diễn ra đồng bộ trong startup lifecycle, ứng dụng chỉ chuyển sang accepting traffic sau khi startup hoàn tất.

Nếu warm-up chạy bất đồng bộ sau khi ứng dụng đã ready, cần quản lý availability state rõ ràng. Spring Boot cung cấp `ApplicationAvailability` và `AvailabilityChangeEvent` để chuyển trạng thái readiness.

Ví dụ thành phần chủ động từ chối traffic trong khi warm-up:

~~~java
package com.example.graphql.startup;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmup {

    private final ApplicationContext applicationContext;
    private final CatalogCache catalogCache;

    public CatalogWarmup(
            ApplicationContext applicationContext,
            CatalogCache catalogCache) {
        this.applicationContext = applicationContext;
        this.catalogCache = catalogCache;
    }

    public void refresh() {
        AvailabilityChangeEvent.publish(
            applicationContext,
            ReadinessState.REFUSING_TRAFFIC
        );

        try {
            catalogCache.loadRequiredEntries();

            AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC
            );
        } catch (RuntimeException exception) {
            // Keep the instance out of traffic and report the failure.
            throw exception;
        }
    }
}
~~~

Ví dụ này minh họa cơ chế availability; vị trí gọi `refresh()` cần được thiết kế theo lifecycle của ứng dụng. Không tự chuyển sang `ACCEPTING_TRAFFIC` nếu các bước bắt buộc chưa thành công. Nếu warm-up thất bại, readiness tiếp tục DOWN để operator có thể xử lý.

Không dùng readiness state như một công tắc tùy tiện cho từng query. Đây là trạng thái của toàn instance. Nếu chỉ một tính năng phụ trợ tạm lỗi nhưng API vẫn phục vụ được các operation khác, cân nhắc trả lỗi có kiểm soát ở operation liên quan và giữ instance ready.

## 15. Bảo vệ health endpoint

Health endpoint có thể tiết lộ thông tin về database, dependency và cấu trúc nội bộ nếu bật show-details quá rộng.

Các nguyên tắc:

- Chỉ expose health endpoint cần cho probe và monitoring.
- Giữ `show-details: never` hoặc chỉ hiển thị chi tiết cho operator đã xác thực.
- Không trả hostname nội bộ, connection string, credential hoặc exception message.
- Dùng network policy hoặc firewall để giới hạn nguồn gọi probe.
- Nếu dùng Spring Security, cấu hình quyền truy cập health endpoint riêng với GraphQL endpoint.
- Không mở toàn bộ Actuator endpoints ra Internet.

Khi có cổng management riêng, bảo vệ cả cổng đó và kiểm tra network policy. Việc endpoint không nằm trên cổng GraphQL không có nghĩa endpoint tự động an toàn.

## 16. Lỗi thường gặp khi cấu hình readiness

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Pod không bao giờ Ready | Readiness group chứa indicator DOWN | Kiểm tra từng indicator và dependency |
| Pod liên tục restart khi database lỗi | Database bị đưa vào liveness | Chuyển dependency check sang readiness |
| `/readyz` trả 404 | Chưa bật additional paths hoặc probes | Kiểm tra cấu hình Actuator và đúng cổng |
| `/graphql` trả 405 khi probe | Kubelet gọi GET vào endpoint GraphQL | Dùng health endpoint riêng |
| Health UP nhưng query GraphQL lỗi | Schema/runtime khởi tạo được nhưng resolver hoặc dependency lỗi | Thêm integration test và synthetic query |
| Health endpoint lộ chi tiết nội bộ | Show details/exposure quá rộng | Giới hạn exposure và quyền truy cập |
| Pod bị loại khỏi traffic khi dependency phụ lỗi | Readiness chứa quá nhiều dependency | Chỉ include dependency thật sự thiết yếu |
| Deploy làm mất subscription | WebSocket session sống lâu hơn shutdown window | Thiết kế reconnect và drain policy |
| Probe timeout khi hệ thống tải cao | Health indicator gọi dependency chậm | Giới hạn timeout và tối ưu health check |

## 17. Checklist trước khi triển khai

- GraphQL endpoint có path và transport được cấu hình rõ ràng?
- Schema SDL và runtime wiring được kiểm tra trong startup?
- Actuator đã được thêm và chỉ expose endpoint cần thiết?
- Liveness chỉ phản ánh khả năng sống của process?
- Readiness phản ánh trạng thái accepting traffic và dependency thật sự thiết yếu?
- Database hoặc remote service có timeout hữu hạn khi được kiểm tra?
- Kubernetes startup, liveness và readiness probes dùng đúng path và port?
- Additional probe paths có được bật nếu management server dùng cổng riêng?
- Health details không tiết lộ thông tin nhạy cảm?
- Có synthetic test kiểm tra operation GraphQL quan trọng?
- Graceful shutdown và termination grace period đủ cho request đang chạy?
- WebSocket subscription có chính sách reconnect khi deploy?
- Có dashboard/alert cho readiness, liveness, GraphQL error rate và latency?

Một GraphQL endpoint sẵn sàng khi schema/runtime đã khởi tạo, web server có thể nhận request và các dependency bắt buộc của instance đang hoạt động. Dùng Actuator readiness để điều phối traffic, liveness để phát hiện process cần restart và startup probe để bảo vệ giai đoạn khởi động. Kiểm tra GraphQL operation bằng integration test hoặc synthetic probe riêng; kết hợp graceful shutdown để deployment có thể ngừng nhận request mới mà vẫn cho request hiện tại hoàn tất.

## Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — GraphQL Support](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

