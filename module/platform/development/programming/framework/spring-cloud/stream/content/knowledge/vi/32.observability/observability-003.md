# Quan sát binding bằng endpoint bindings

## Mục tiêu

Spring Cloud Stream tạo các binding để nối function của ứng dụng với destination trên middleware như Kafka topic, RabbitMQ exchange/queue hoặc Pulsar topic/subscription. Khi ứng dụng chạy, cần biết binding nào đã được tạo, binding đang ở trạng thái nào, nó là input hay output, thuộc group nào và có thể điều khiển vòng đời ra sao.

Spring Cloud Stream tích hợp endpoint Actuator có ID `bindings`. Endpoint này cho phép liệt kê tất cả binding của một application instance, xem chi tiết một binding và gửi yêu cầu đổi trạng thái binding. Nó hữu ích khi điều tra một consumer không nhận message, tạm dừng một luồng hỗ trợ bảo trì hoặc xác minh binding đã khởi động sau deployment.

Bài học này trình bày cách bật endpoint, đọc kết quả `GET`, điều khiển binding bằng `POST`, hiểu giới hạn theo binder, bảo vệ thông tin nhạy cảm và kiểm thử endpoint trong môi trường có middleware thật.

Sau bài học, bạn có thể:

- Giải thích binding và tên binding được tạo từ function definition.
- Thêm Spring Boot Actuator và web dependency cần thiết.
- Expose riêng endpoint `bindings` qua HTTP.
- Liệt kê và xem chi tiết binding bằng `GET /actuator/bindings`.
- Đổi trạng thái binding bằng `POST /actuator/bindings/{name}`.
- Phân biệt `STARTED`, `STOPPED`, `PAUSED` và `RESUMED`.
- Nhận biết khả năng điều khiển khác nhau giữa regular binder và Kafka Streams binder.
- Dùng `BindingsLifecycleController` khi cần điều khiển từ code.
- Bảo vệ endpoint, lọc dữ liệu nhạy cảm và quan sát từng instance.
- Kiểm thử trạng thái binding và xử lý các lỗi thường gặp.

## 1. Binding là gì và tại sao cần quan sát?

Binding là kết nối giữa một input/output của ứng dụng Spring Cloud Stream và destination trên middleware. Với function model, tên binding được suy ra từ tên bean function và vị trí input/output.

Ví dụ:

```java
@Bean
Function<OrderCreated, OrderSummary> summarizeOrder() {
    return order -> new OrderSummary(
            order.eventId(),
            order.orderId(),
            "RECEIVED"
    );
}
```

Nếu function tên `summarizeOrder`, Spring Cloud Stream tạo hai binding mặc định:

| Binding name | Hướng | Vai trò |
|---|---|---|
| `summarizeOrder-in-0` | Input | Nhận `OrderCreated` |
| `summarizeOrder-out-0` | Output | Phát `OrderSummary` |

Cấu hình có thể ánh xạ chúng tới các destination:

```yaml
spring:
  cloud:
    function:
      definition: summarizeOrder
    stream:
      bindings:
        summarizeOrder-in-0:
          destination: orders.created
          group: order-summary-service
        summarizeOrder-out-0:
          destination: orders.summary
```

Tên binding là định danh mà endpoint `bindings` dùng trong URL. Nó khác với destination: `summarizeOrder-in-0` là tên binding trong ứng dụng, còn `orders.created` là destination do binder ánh xạ tới Kafka topic, RabbitMQ exchange/queue hoặc Pulsar topic theo binder tương ứng.

Quan sát binding giúp trả lời các câu hỏi vận hành:

- Function có được bind với input/output như dự kiến không?
- Tên binding thực tế là gì?
- Binding thuộc input hay output?
- Consumer group nào đang được sử dụng?
- Binding có đang chạy không?
- Binder có hỗ trợ pause/resume hay chỉ start/stop?
- Một instance cụ thể đã nhận được yêu cầu điều khiển chưa?

Endpoint phản ánh binding của application instance đang được truy vấn. Nó không phải dashboard cluster tự tổng hợp mọi replica.

## 2. Thêm Actuator và web dependency

Actuator và web server là các thành phần tùy chọn. Để expose endpoint qua HTTP, ứng dụng cần Spring Boot Actuator và một web stack như Spring MVC hoặc WebFlux.

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Nếu ứng dụng dùng reactive web stack, có thể thay `spring-boot-starter-web` bằng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Không cần thêm cả MVC và WebFlux chỉ để bật endpoint. Chọn web stack phù hợp với ứng dụng. Để dependency management của Spring Boot/Spring Cloud BOM quản lý version tương thích; không tự chọn một version Actuator khác với Spring Boot đang chạy.

Nếu ứng dụng không có web server, endpoint HTTP sẽ không được phục vụ. Có thể quan sát/điều khiển binding bằng API programmatic trong Spring context, hoặc dùng cơ chế quản trị khác phù hợp với deployment.

## 3. Expose endpoint bindings

Spring Boot mặc định chỉ expose một số endpoint Actuator an toàn, trong đó `health` được expose qua HTTP. Endpoint `bindings` cần được bật tường minh:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,bindings
```

Có thể cấu hình bằng property:

```properties
management.endpoints.web.exposure.include=health,bindings
```

Chỉ expose các endpoint thực sự cần. Nếu đặt `include: "*"`, nhiều endpoint quản trị khác cũng có thể trở nên truy cập được. Không mở rộng toàn bộ Actuator chỉ để quan sát binding.

Sau khi ứng dụng khởi động, kiểm tra log mapping endpoint hoặc gửi request:

```bash
curl http://localhost:8080/actuator/bindings
```

Đường dẫn mặc định là `/actuator/bindings`. Nếu ứng dụng thay đổi management base path hoặc management port, URL sẽ thay đổi theo cấu hình Spring Boot.

### Dùng management port riêng

Có thể tách cổng quản trị khỏi cổng HTTP nghiệp vụ:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,bindings
```

Với ví dụ này, endpoint nằm tại:

```text
http://localhost:8081/manage/bindings
```

Việc tách cổng giúp áp dụng network policy riêng cho traffic quản trị. Nó không tự tạo authentication hoặc authorization; vẫn phải cấu hình bảo mật cho management interface.

## 4. Liệt kê tất cả binding bằng GET

Gửi request:

```http
GET /actuator/bindings
```

Ví dụ:

```bash
curl -s http://localhost:8080/actuator/bindings
```

Endpoint trả về danh sách binding mà application instance hiện tại quản lý. Các trường có thể khác nhau theo binder và version; một response có thể chứa thông tin như:

```json
[
  {
    "bindingName": "summarizeOrder-in-0",
    "name": "summarizeOrder-in-0",
    "group": "order-summary-service",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": true,
    "extendedInfo": {}
  },
  {
    "bindingName": "summarizeOrder-out-0",
    "name": "summarizeOrder-out-0",
    "group": "order-summary-service",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": false,
    "extendedInfo": {}
  }
]
```

Đây là response minh họa; không nên coi mọi field là schema cố định cho tất cả binder. Hãy xem response thực tế của release đang dùng.

Một số trường thường gặp:

| Trường | Ý nghĩa |
|---|---|
| `bindingName` / `name` | Tên binding trong application |
| `group` | Consumer group đối với input binding có group |
| `input` | Cho biết binding là input hay output |
| `state` | Trạng thái lifecycle, ví dụ running hoặc stopped |
| `paused` | Cho biết binding có đang pause hay không nếu binder cung cấp |
| `pausable` | Cho biết binding có hỗ trợ pause/resume hay không |
| `extendedInfo` | Thông tin bổ sung tùy binder |

Binding output thường không có consumer group như input. Với anonymous consumer, group có thể không có giá trị như named group. Không suy luận broker lag, queue depth hoặc số message chưa ack chỉ từ trạng thái `running`; endpoint bindings chủ yếu mô tả lifecycle/configuration của binding.

### Binding name và destination

Nếu response liệt kê `summarizeOrder-in-0`, đó là tên cần dùng trong endpoint chi tiết hoặc POST state. Không dùng destination `orders.created` thay cho binding name nếu chúng khác nhau.

Với function composition hoặc nhiều input/output, tên binding có thể có chỉ số khác như `process-in-1`, `process-out-0`. Hãy lấy tên thực tế từ endpoint thay vì tự ghép tên theo phỏng đoán.

## 5. Xem chi tiết một binding

Dùng tên binding ở path:

```http
GET /actuator/bindings/{bindingName}
```

Ví dụ:

```bash
curl -s http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

Request này giúp tập trung vào một binding khi ứng dụng có nhiều function hoặc nhiều binder. Kết quả thường cho biết tên, group, hướng input/output, trạng thái và thông tin mở rộng mà binder cung cấp.

Nếu binding không tồn tại trong instance đang truy vấn, endpoint có thể trả lỗi không tìm thấy. Trước khi kết luận binding không được tạo, kiểm tra:

- Function có nằm trong `spring.cloud.function.definition` hay không.
- Binding name có đúng suffix `-in-0`/`-out-0` hay không.
- Binding được tạo tự động hay tạo tường minh.
- Instance đang truy vấn có phải instance đã khởi tạo function đó không.
- Application có khởi động thành công và binder provisioning có hoàn tất không.

Endpoint không thay thế log startup hoặc binder health. Nếu binding không được tạo do lỗi cấu hình, cần xem startup error và binder logs.

## 6. Điều khiển lifecycle bằng POST

Endpoint cho phép gửi trạng thái mới đến cùng URL binding:

```http
POST /actuator/bindings/{bindingName}
Content-Type: application/json

{"state":"STOPPED"}
```

Các trạng thái lifecycle phổ biến:

| State | Ý nghĩa |
|---|---|
| `STARTED` | Khởi động binding |
| `STOPPED` | Dừng binding |
| `PAUSED` | Tạm dừng consumer nếu binder hỗ trợ |
| `RESUMED` | Tiếp tục consumer đã pause nếu binder hỗ trợ |

Ví dụ dừng một input binding:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STOPPED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

Khởi động lại binding:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

Pause và resume khi binder hỗ trợ:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"PAUSED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0

curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"RESUMED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

Sau khi POST, đọc lại binding bằng GET để xác minh trạng thái thực tế. Không chỉ dựa vào HTTP response của lệnh điều khiển; binder có thể cần thời gian hoàn tất lifecycle transition hoặc ghi cảnh báo khi trạng thái không được hỗ trợ.

### STOPPED khác PAUSED

`STOPPED` dừng lifecycle binding. Với input consumer, message mới không được nhận qua binding đó trong khi nó dừng. Việc message đang xử lý, offset/ack, queue backlog và redelivery tuân theo semantics của binder/middleware; không giả định POST stop đồng nghĩa mọi message đang xử lý đã hoàn tất hoặc được rollback.

`PAUSED` là trạng thái tạm dừng nhận message trong khi giữ binding theo khả năng của binder. Nó không phải tính năng chung cho mọi middleware. Khi cần drain message trước bảo trì, phải xác định binder có hỗ trợ pause và kiểm tra in-flight processing trước khi thao tác.

## 7. Khả năng lifecycle phụ thuộc binder và version

Không phải mọi binder hỗ trợ mọi trạng thái. Tài liệu Spring Cloud Stream hiện hành nêu:

- Với regular binders, `STARTED` và `STOPPED` là các thao tác lifecycle cơ bản.
- `PAUSED` và `RESUMED` chỉ có hiệu lực nếu binder và middleware hỗ trợ. Tài liệu hiện hành nêu Kafka và Solace hỗ trợ các trạng thái này.
- Kafka Streams binder có tài liệu điều khiển riêng: chỉ hỗ trợ `STARTED` và `STOPPED`; `PAUSED` và `RESUMED` không khả dụng trong Kafka Streams binder.

Vì vậy, không suy ra rằng Kafka Streams binder hỗ trợ pause/resume chỉ vì regular Kafka binder có thể hỗ trợ. Với RabbitMQ hoặc Pulsar binder, không giả định POST `PAUSED`/`RESUMED` có hiệu lực; kiểm tra release guide và response/log của binder đang dùng.

| Binder/model | STARTED / STOPPED | PAUSED / RESUMED |
|---|---|---|
| Regular Kafka binder | Có | Có theo tài liệu hiện hành |
| Kafka Streams binder | Có | Không |
| Solace binder | Có | Có theo tài liệu hiện hành |
| RabbitMQ binder | Có theo lifecycle binding | Không nên giả định; kiểm tra version |
| Pulsar binder | Có theo lifecycle binding | Không nên giả định; kiểm tra version |

Bảng này là hướng dẫn chọn thao tác, không thay thế kiểm tra compatibility matrix của version cụ thể. Nếu binder không hỗ trợ một state, log có thể ghi cảnh báo hoặc binding không chuyển sang trạng thái mong muốn.

## 8. Tên binding trong function, Consumer và StreamBridge

Tên binding mặc định được suy ra từ function definition:

| Function type | Binding name thường gặp |
|---|---|
| `Supplier<T>` | `functionName-out-0` |
| `Consumer<T>` | `functionName-in-0` |
| `Function<I,O>` | `functionName-in-0`, `functionName-out-0` |
| Function có nhiều input | `functionName-in-0`, `functionName-in-1`, ... |
| Function có nhiều output | `functionName-out-0`, `functionName-out-1`, ... |

Nếu sử dụng `StreamBridge`, output binding có thể được tạo khi gửi message nếu binding chưa tồn tại và dynamic destination behavior được bật theo cấu hình. Sau đó binding có thể xuất hiện trong endpoint. Với explicit binding không được tạo từ function definition, tên có thể không có suffix `-in-0`/`-out-0`.

Ví dụ:

```java
@Service
class OrderPublisher {

    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
```

Sau khi output binding được tạo, endpoint có thể hiển thị `orders-out-0`. Nếu không thấy binding, kiểm tra message đã được gửi chưa, binding có được tạo theo cách tường minh hay tự động, và tên output có đúng với code/configuration hay không.

## 9. Quan sát binding không đồng nghĩa quan sát broker

Endpoint bindings cho biết trạng thái binding trong ứng dụng. Nó không cung cấp đầy đủ các chỉ số vận hành của middleware.

| Câu hỏi | Nơi quan sát phù hợp |
|---|---|
| Binding đã được tạo chưa? | `/actuator/bindings` |
| Binding đang chạy hay dừng? | `/actuator/bindings/{name}` |
| Consumer lag Kafka là bao nhiêu? | Kafka consumer group metrics/tooling |
| RabbitMQ queue có bao nhiêu ready/unacked message? | RabbitMQ Management/API/metrics |
| Pulsar subscription backlog và redelivery ra sao? | Pulsar Admin/metrics |
| Application có lỗi hoặc chưa sẵn sàng? | `/actuator/health`, application logs |
| Throughput và latency của message? | Micrometer metrics/tracing và broker metrics |
| Có lỗi serialize/deserialize? | Application logs, error metrics và binder-specific diagnostics |

Một binding ở trạng thái running không chứng minh nó đang nhận message. Có thể không có producer, routing key không khớp, subscription backlog chưa được drain, ACL bị từ chối hoặc consumer handler đang lỗi. Hãy kết hợp endpoint bindings với health, logs, metrics và công cụ quản trị broker.

## 10. Endpoint chỉ điều khiển instance được gọi

Trong deployment nhiều replica, mỗi application instance có Spring context và binding lifecycle riêng. Khi gửi POST đến một pod, thao tác áp dụng cho binding của pod đó. Nó không tự broadcast đến mọi replica trong Kubernetes hoặc VM fleet.

Ví dụ deployment có ba pod:

```text
orders-service-0 -> /actuator/bindings/summarizeOrder-in-0
orders-service-1 -> /actuator/bindings/summarizeOrder-in-0
orders-service-2 -> /actuator/bindings/summarizeOrder-in-0
```

Nếu chỉ gọi endpoint của `orders-service-0`, hai pod còn lại vẫn có thể tiếp tục consume. Với consumer group, các pod có thể chia sẻ cùng logical subscription/group; một pod dừng không có nghĩa toàn group dừng.

Để quản lý toàn fleet, dùng orchestrator/control plane có inventory instance và gọi đúng management endpoint của từng instance, hoặc dùng cơ chế vận hành tập trung. Cần xử lý timeout, instance thay đổi IP, rolling restart và partial success. Không dùng một load-balanced service URL nếu không biết request đã đến instance nào; response từ một pod không chứng minh tất cả pod đã đổi state.

## 11. Bảo mật endpoint bindings

Endpoint có khả năng thay đổi lifecycle của message flow. Nếu người không được phép có thể POST `STOPPED`, họ có thể làm consumer ngừng nhận message. Vì vậy:

- Không expose endpoint quản trị trực tiếp ra Internet.
- Chỉ expose `bindings` khi thực sự cần.
- Dùng management port/network riêng nếu phù hợp.
- Bảo vệ bằng Spring Security hoặc API gateway có authentication/authorization.
- Chỉ cấp quyền POST cho operator/role cần thiết.
- Giới hạn network bằng firewall hoặc Kubernetes NetworkPolicy.
- Ghi audit log cho thao tác thay đổi trạng thái.
- Theo dõi request thất bại và thao tác stop/start bất thường.

Ví dụ cấu hình security đơn giản với Spring Security 6:

```java
@Bean
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher(EndpointRequest.to("bindings"));
    http.authorizeHttpRequests(authorize ->
            authorize.anyRequest().hasRole("STREAM_OPERATOR")
    );
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Đây là ví dụ khái niệm; cấu hình thực tế cần tích hợp authentication provider, TLS và security policy của ứng dụng. Nếu ứng dụng định nghĩa custom `SecurityFilterChain`, Spring Boot có thể không tự áp dụng cấu hình security Actuator mặc định; hãy bảo đảm matcher và authorization bao phủ cả endpoint root lẫn path con.

### Không expose mọi endpoint để tiện debug

Tránh:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Nếu cần endpoint khác, thêm đúng ID cần dùng. Khi bật nhiều endpoint, đánh giá dữ liệu cấu hình, environment, bean, log và thông tin vận hành mà chúng có thể tiết lộ.

## 12. Lọc dữ liệu nhạy cảm trong response

Binding endpoint có thể hiển thị thông tin mở rộng hoặc cấu hình liên quan đến binder. Một số giá trị có thể chứa credential, SASL configuration, SSL key material hoặc thông tin kết nối. Không giả định mọi giá trị đều đã được che theo cùng cách ở mọi version.

Spring Boot cung cấp `SanitizingFunction` để tùy chỉnh cách che dữ liệu nhạy cảm. Ví dụ:

```java
@Bean
SanitizingFunction sanitizingFunction() {
    return data -> {
        if ("sasl.jaas.config".equals(data.getKey())) {
            return data.withValue("[REDACTED]");
        }
        return data;
    };
}
```

Ví dụ trên minh họa che một property cụ thể. Ứng dụng cần xác định danh sách key nhạy cảm theo binder và môi trường, ví dụ password, token, private key, JAAS config hoặc credential trong URL. Không đưa secret vào log khi xử lý response endpoint.

Kiểm thử sanitization bằng response thực tế trên version đang chạy. Nếu endpoint không hiển thị một property ở môi trường test, không có nghĩa môi trường production sẽ không hiển thị property tương ứng.

## 13. Điều khiển binding bằng BindingsLifecycleController

Từ Spring Cloud Stream 3.1, ứng dụng có thể dùng bean `BindingsLifecycleController` để truy vấn và điều khiển binding bằng Java thay vì HTTP:

```java
BindingsLifecycleController controller =
        applicationContext.getBean(BindingsLifecycleController.class);

Binding<?> binding = controller.queryState("summarizeOrder-in-0");

if (binding.isRunning()) {
    controller.stop("summarizeOrder-in-0");
}
```

Có thể đổi state tường minh:

```java
controller.changeState("summarizeOrder-in-0", State.STOPPED);
controller.changeState("summarizeOrder-in-0", State.STARTED);
```

Controller còn cung cấp các phương thức tiện ích như start/stop và pause/resume. Khả năng thực tế vẫn phụ thuộc binder; gọi pause không làm binder tự nhiên có hỗ trợ pause nếu middleware adapter không hỗ trợ.

Dùng API programmatic khi cần tích hợp lifecycle với một service quản trị nội bộ hoặc kiểm thử trực tiếp. Với thao tác vận hành từ bên ngoài process, Actuator endpoint thường dễ tích hợp với công cụ quản trị hơn.

Từ Spring Cloud Stream 4.2, controller còn hỗ trợ tạo binding mới và lấy extension properties cho binding được tạo tường minh. Đây là khả năng quản lý binding động nâng cao; không nhầm với endpoint `GET /actuator/bindings`, vốn dùng để quan sát các binding hiện có.

## 14. Kiểm thử endpoint bindings

Có thể kiểm thử ở nhiều tầng.

### Application context test

Xác minh:

- Actuator dependency có trong classpath.
- Web stack được khởi tạo.
- Endpoint bindings được đăng ký.
- Binding function có tên như mong đợi.
- Exposure config chứa `bindings`.
- Security cho phép role vận hành truy cập và từ chối role không phù hợp.

### HTTP test

Với Spring MVC có thể dùng MockMvc; với WebFlux có thể dùng WebTestClient. Các trường hợp cơ bản:

| Request | Kỳ vọng |
|---|---|
| `GET /actuator/bindings` | Trả danh sách binding |
| `GET /actuator/bindings/{name}` | Trả chi tiết binding tồn tại |
| `GET` binding không tồn tại | Trả lỗi phù hợp, không làm lộ nội bộ |
| `POST` state `STOPPED` | Binding chuyển sang stopped nếu binder hỗ trợ |
| `POST` state `STARTED` | Binding chuyển sang running |
| `POST` state `PAUSED` | Chỉ thành công khi binder hỗ trợ |
| `POST` state không hợp lệ | Trả lỗi validation phù hợp |
| Request không xác thực | Bị từ chối |
| User không có operator role | Bị từ chối |

Ví dụ kiểm tra GET với MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BindingEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void listsBindings() throws Exception {
        mockMvc.perform(get("/actuator/bindings"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$[?(@.name=='summarizeOrder-in-0')]")
                        .exists());
    }
}
```

Test cần cấu hình đúng function definition và test binder hoặc binder phù hợp để binding được tạo trong context. Response schema có thể khác theo binder/version; điều chỉnh JSON path theo response thực tế thay vì phụ thuộc vào field không được contract bảo đảm.

### Broker integration test

HTTP test không chứng minh broker đã dừng hoặc tiếp tục giao message đúng. Bổ sung integration test với Kafka, RabbitMQ hoặc Pulsar tương ứng:

1. Publish message và xác minh consumer nhận.
2. POST `STOPPED` vào input binding.
3. Publish thêm message và xác minh binding không nhận trong thời gian dừng theo semantics binder.
4. POST `STARTED`.
5. Xác minh consumer tiếp tục hoạt động và backlog được xử lý theo broker policy.
6. Nếu test pause/resume, xác minh binder thực sự hỗ trợ state đó.
7. Kiểm tra message đang xử lý khi stop và xác định ack/offset outcome.
8. Kiểm tra log/metric sau thao tác.

Không kiểm tra rằng message "biến mất" khi binding dừng. Broker có thể giữ message trong topic/queue/subscription để consumer nhận sau khi binding start lại; semantics cụ thể phụ thuộc middleware.

## 15. Quy trình điều tra khi binding không hoạt động

Khi consumer không nhận message, dùng trình tự:

1. Gọi `GET /actuator/bindings` trên đúng instance.
2. Xác định binding name chính xác.
3. Gọi `GET /actuator/bindings/{name}` để xem trạng thái.
4. Xác nhận binding là input và destination/group đúng với cấu hình.
5. Kiểm tra application logs và binder health.
6. Kiểm tra broker topic/queue/subscription, ACL, routing và backlog bằng công cụ broker.
7. Kiểm tra message conversion, retry, ack và handler exception.
8. Nếu binding đang stopped ngoài dự kiến, tìm audit/log về thao tác lifecycle.
9. Chỉ POST `STARTED` sau khi xác định lý do dừng và người vận hành có thẩm quyền.
10. Gọi GET lại và xác minh consumer thực sự nhận message.

Nếu endpoint trả `running` nhưng broker backlog tăng, vấn đề có thể nằm ở throughput, partition/concurrency, consumer error hoặc middleware. Đừng liên tục stop/start như một cách chữa mọi lỗi; điều đó có thể làm tăng rebalance, redelivery hoặc gián đoạn xử lý.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/actuator/bindings` trả 404 | Thiếu Actuator/web dependency hoặc chưa expose endpoint | Thêm dependency và cấu hình exposure |
| Endpoint chỉ có health | Chưa thêm `bindings` vào exposure include | Cấu hình `health,bindings` |
| GET trả 401/403 | Security yêu cầu xác thực hoặc role chưa đủ | Cấp quyền operator theo policy |
| Binding không xuất hiện | Function chưa được kích hoạt hoặc binder provisioning lỗi | Kiểm tra function definition và startup logs |
| Dùng destination trong URL nhưng không tìm thấy | URL cần binding name | Lấy tên từ GET list |
| POST PAUSED không có tác dụng | Binder/model không hỗ trợ pause | Kiểm tra capability và version |
| Kafka Streams binder không pause được | Kafka Streams binder chỉ hỗ trợ STARTED/STOPPED | Dùng stop/start hoặc cơ chế khác phù hợp |
| POST thành công nhưng consumer vẫn hoạt động ở pod khác | Chỉ một instance được gọi | Thực hiện qua control plane cho toàn fleet |
| Binding running nhưng không có message | Không có producer, routing/ACL sai, handler lỗi hoặc backlog | Kết hợp broker metrics và logs |
| Response có thông tin cấu hình nhạy cảm | Extended info chứa credential/property | Bảo vệ endpoint và dùng SanitizingFunction |
| Sau stop/start có redelivery | Message đang in-flight chưa được ack/commit | Kiểm tra ack/offset semantics và idempotency |
| URL không đúng | Management port/base path đã tùy chỉnh | Kiểm tra management server config |

## 17. Runbook vận hành an toàn

Trước khi điều khiển binding production:

- Xác nhận cluster, application instance và binding name.
- Xác định input/output và binder đang sử dụng.
- Kiểm tra state hiện tại qua GET.
- Xác định tác động tới backlog, in-flight messages, offset/ack và downstream.
- Có lý do vận hành rõ ràng và operator được phân quyền.
- Thực hiện một thay đổi lifecycle mỗi lần.
- Đọc lại state sau POST.
- Kiểm tra broker metrics và application logs.
- Nếu quản lý nhiều replica, xác minh kết quả trên từng instance.
- Ghi audit record gồm người thực hiện, thời điểm, binding, state cũ/mới và lý do.

Khi bảo trì consumer, cân nhắc drain hoặc chờ xử lý message đang chạy trước khi stop. Endpoint lifecycle không thay thế graceful shutdown strategy của ứng dụng và không tự bảo đảm mọi side effect đã commit.

## 18. Tài liệu đối chiếu theo phiên bản

Các capability của endpoint và binder thay đổi theo release. Khi triển khai, đối chiếu reference guide của đúng Spring Cloud Stream/Spring Boot version trong dependency management:

- [Spring Cloud Stream — Binding visualization and control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html): dependency, GET/POST endpoint, lifecycle state, programmatic controller và sanitization.
- [Spring Cloud Stream — Kafka Streams binder binding visualization and control](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding-visualization-and-control-in-binder.html): response ví dụ và giới hạn chỉ STARTED/STOPPED của Kafka Streams binder.
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access control và bảo mật endpoint.
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): tên binding, destination, group và cấu hình binding.

Không dùng snapshot documentation để khẳng định capability của một release cũ. Ghi lại Spring Boot, Spring Cloud Stream và binder version khi tạo runbook và test report.

## Kết luận

Endpoint `/actuator/bindings` giúp quan sát binding mà Spring Cloud Stream đã tạo trên một application instance. Dùng `GET /actuator/bindings` để liệt kê, `GET /actuator/bindings/{name}` để xem chi tiết và `POST /actuator/bindings/{name}` với state JSON để điều khiển lifecycle. Tên dùng trong URL là binding name, không nhất thiết là destination trên broker.

Để bật endpoint, thêm Actuator và web dependency, rồi expose ID `bindings` qua management configuration. Bảo vệ endpoint bằng authentication/authorization và network policy vì POST có thể dừng luồng message; lọc các giá trị cấu hình nhạy cảm trước khi trả response. Khả năng pause/resume phụ thuộc binder: Kafka Streams binder chỉ hỗ trợ STARTED/STOPPED, còn các binder khác phải được xác minh theo version.

Endpoint chỉ điều khiển instance nhận request và chỉ mô tả lifecycle của binding. Hãy kết hợp nó với health, logs, metrics và công cụ quản trị Kafka/RabbitMQ/Pulsar. Sau mỗi thao tác, đọc lại trạng thái và kiểm tra broker để xác nhận luồng message thực sự hoạt động theo mong đợi.

