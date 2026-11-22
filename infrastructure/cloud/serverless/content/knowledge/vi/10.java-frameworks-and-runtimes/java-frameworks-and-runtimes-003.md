# Đưa ứng dụng Spring Boot lên môi trường serverless

## 1. Spring Boot và mô hình thực thi serverless

Spring Boot thường được triển khai như một ứng dụng chạy liên tục: JVM khởi động, Spring tạo application context, embedded server mở cổng HTTP và ứng dụng tiếp nhận nhiều request trong suốt vòng đời tiến trình. Trong mô hình serverless function-as-a-service (FaaS), nền tảng tiếp nhận trigger rồi gọi một handler; handler thực hiện công việc trong một invocation và trả kết quả. Nền tảng có thể tạo nhiều execution environment song song, tái sử dụng một environment cho các invocation tiếp theo hoặc loại bỏ environment khi không còn nhu cầu.

Điều đó không có nghĩa phải viết lại toàn bộ nghiệp vụ Spring Boot. Phần lớn service, repository, validation và domain logic có thể được giữ lại. Công việc chính là chọn adapter phù hợp, xác định vòng đời ứng dụng, loại bỏ giả định về trạng thái cục bộ và cấu hình tài nguyên theo cách nền tảng serverless vận hành.

Trong phạm vi CLOUD_SERVERLESS, mục tiêu là triển khai Java function được kích hoạt bởi HTTP, message hoặc event. Người học cần xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Vì vậy, việc chuyển Spring Boot không chỉ là đóng gói JAR rồi tải lên nền tảng; cần xem lại cách request đi vào ứng dụng và cách ứng dụng sử dụng tài nguyên trong mỗi invocation.

Một ứng dụng Spring Boot có thể được đưa lên môi trường serverless theo một số hướng:

| Hướng triển khai | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Giữ Spring MVC với adapter FaaS | API Gateway chuyển HTTP event thành request servlet; adapter gọi Spring MVC và đổi response trở lại định dạng nền tảng | Đã có REST API Spring Boot và muốn giữ controller/filter/interceptor |
| Spring Cloud Function | Khai báo nghiệp vụ dưới dạng `Function`, `Consumer` hoặc `Supplier`; adapter chuyển trigger thành lời gọi function | Ứng dụng thiên về message/event hoặc muốn tách nghiệp vụ khỏi HTTP |
| Serverless container | Chạy ứng dụng Spring Boot như một container có thể scale về 0 hoặc scale theo request | Cần giữ mô hình web server, thư viện native hoặc giao thức dài hạn mà FaaS không phù hợp |

Serverless container có mô hình vận hành khác FaaS thuần: ứng dụng vẫn có tiến trình và web server, dù nền tảng quản lý hạ tầng và tự động mở rộng. Cần chọn đúng mô hình theo thời gian chạy, giao thức và cách tính phí của nền tảng.

## 2. Kiểm tra ứng dụng trước khi chuyển đổi

Trước khi thay đổi cấu hình, hãy xác định những giả định của ứng dụng hiện tại:

- Ứng dụng có phụ thuộc vào một cổng HTTP cố định hoặc embedded server chạy liên tục không?
- Có lưu session, cache, file upload hoặc trạng thái nghiệp vụ trong bộ nhớ cục bộ không?
- Có dùng `@Scheduled`, background thread, executor hoặc consumer loop chạy vô hạn không?
- Có mở kết nối database, broker hoặc HTTP client ngay khi khởi động không?
- Có yêu cầu WebSocket, streaming response, long polling hoặc request kéo dài không?
- Có phụ thuộc vào file hệ thống cục bộ, working directory hoặc dữ liệu tồn tại qua nhiều lần gọi không?
- Có cần khởi tạo nhiều bean, scan classpath hoặc tải cấu hình từ xa trong startup không?
- Có các tác vụ cần retry, checkpoint, idempotency hoặc bù trừ không?

Các thành phần nghiệp vụ thuần Java thường dễ tái sử dụng. Những thành phần cần xem xét kỹ gồm web server, session store, scheduler, thread pool, connection pool, file storage và các thư viện giả định tiến trình tồn tại lâu dài.

Một cách tiếp cận an toàn là tách lớp ứng dụng khỏi adapter:

```text
HTTP / Queue / Stream Trigger
            |
            v
  API Gateway hoặc FaaS Adapter
            |
            v
      Spring Application
            |
     +------+------+
     |             |
     v             v
 Domain Service  Application Service
     |             |
     +------+------+
            |
            v
 Repository / HTTP Client / Event Publisher
            |
            v
 Database / Object Storage / Queue / Event Bus
```

Controller hoặc function adapter chỉ nên chuyển đổi giao thức, xác thực đầu vào và gọi application service. Quy tắc nghiệp vụ nên nằm trong service để có thể kiểm thử độc lập và dùng lại từ HTTP, queue hoặc stream.

## 3. Chọn adapter: Spring MVC hay Spring Cloud Function?

### Giữ Spring MVC với adapter serverless

Nếu ứng dụng đã có nhiều `@RestController`, Spring Security filter, validation và exception handler, có thể dùng adapter mô phỏng servlet request/response. Với AWS Lambda và API Gateway, AWS Serverless Java Container là một lựa chọn. Adapter chuyển proxy event thành request mà Spring MVC hiểu, sau đó chuyển response servlet về định dạng API Gateway.

Ưu điểm:

- Giữ lại cấu trúc controller và phần lớn thư viện web hiện tại.
- Có thể tái sử dụng filter, interceptor, validation và Spring Security.
- Thích hợp cho REST API được gọi theo request/response.

Đánh đổi:

- Spring context và servlet stack làm tăng kích thước artifact và thời gian cold start.
- Cần ánh xạ đúng event format của API Gateway; REST API proxy v1 và HTTP API v2 có cấu trúc khác nhau.
- Các tính năng phụ thuộc kết nối dài hạn hoặc server push có thể không phù hợp với request/response FaaS.
- Adapter không biến mọi hành vi của một web server dài hạn thành tương đương hoàn toàn với môi trường servlet truyền thống.

### Dùng Spring Cloud Function

Spring Cloud Function cho phép định nghĩa nghiệp vụ dưới dạng hàm Java. Adapter của nền tảng chuyển HTTP request, message hoặc event thành input của function. Cách này phù hợp khi logic xử lý độc lập với giao thức.

Ví dụ:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    Function<CreateOrderCommand, OrderAccepted> createOrder(
            OrderApplicationService orderService) {
        return orderService::create;
    }
}
```

Trong đó `CreateOrderCommand`, `OrderAccepted` và `OrderApplicationService` là kiểu dữ liệu/lớp nghiệp vụ của ứng dụng. Adapter serverless sẽ chọn function cần gọi và chuyển đổi payload theo hợp đồng của nền tảng. Tên handler, dependency và cấu hình đóng gói cần theo adapter/version đang sử dụng; không tự giả định một handler class là dùng chung cho mọi cloud.

Spring Cloud Function tách phần nghiệp vụ khỏi HTTP hoặc message transport, giúp kiểm thử và tái sử dụng tốt. Tuy nhiên, nếu ứng dụng cần đầy đủ servlet stack, filter phức tạp hoặc nhiều endpoint REST, chuyển đổi tất cả sang function có thể đòi hỏi thay đổi đáng kể.

### Chọn theo đặc điểm workload

| Nhu cầu | Hướng nên xem xét trước |
|---|---|
| REST API hiện có, muốn giữ controller | Spring MVC + adapter serverless |
| Xử lý event/message, ít phụ thuộc servlet | Spring Cloud Function |
| Công việc kéo dài, tiến trình nền liên tục | Queue + worker dài hạn hoặc serverless container/workflow |
| WebSocket hoặc kết nối liên tục | Managed WebSocket service hoặc serverless container phù hợp |
| Khởi động nhanh, artifact nhỏ, một nhiệm vụ đơn giản | Java function gọn, có thể không cần toàn bộ Spring Boot |
| Cần giữ nguyên ứng dụng web hiện tại với ít thay đổi | Serverless container hoặc container platform có scale theo request |

Không nên chuyển sang FaaS chỉ vì ứng dụng đang dùng Spring Boot. Hãy so sánh cold start, thời gian thực thi, tần suất request, kết nối, chi phí và công sức vận hành với mô hình container.

## 4. Vòng đời Spring ApplicationContext trong FaaS

Spring Boot tạo application context, khởi tạo bean và thực hiện các callback startup. Với adapter phù hợp, context thường được khởi tạo khi execution environment bắt đầu và có thể được tái sử dụng cho nhiều invocation trên cùng environment. Nền tảng không bảo đảm một instance sẽ tồn tại mãi hoặc request tiếp theo sẽ đến cùng instance.

Vì vậy:

- Bean singleton có thể chứa dependency dùng chung an toàn như HTTP client hoặc serializer thread-safe.
- Không đặt dữ liệu của một request/người dùng vào field của singleton bean.
- Không dùng static map làm nơi lưu session hoặc trạng thái nghiệp vụ.
- Không giả định `@PostConstruct` chạy một lần cho toàn bộ ứng dụng; nó chạy theo vòng đời context của từng execution environment.
- Không dựa vào hook shutdown để lưu dữ liệu quan trọng; môi trường có thể bị dừng mà không có thời gian shutdown đầy đủ.
- Khởi tạo lazy bean có thể giảm startup ban đầu nhưng chuyển thời gian khởi tạo sang invocation đầu tiên sử dụng bean đó.

Ví dụ không an toàn:

```java
@Service
public class CurrentUserCache {
    // Sai: dữ liệu người dùng có thể bị dùng chung giữa các invocation.
    private String currentUserId;

    public void setCurrentUser(String userId) {
        this.currentUserId = userId;
    }
}
```

Thay vào đó, truyền ngữ cảnh người dùng qua tham số method hoặc request-scoped context được quản lý đúng trong invocation. Nếu cần lưu trạng thái qua nhiều request, dùng session store hoặc database dùng chung.

Execution environment có thể xử lý invocation song song tùy nền tảng và adapter, hoặc chỉ xử lý tuần tự trên một environment. Không dựa vào giả định đó để bỏ đồng bộ hóa. Hãy dùng bean thread-safe và tránh mutable shared state. Nếu có cache cục bộ, xem nó là cache best-effort có thể mất hoặc khác nhau giữa các instance.

## 5. Ví dụ Spring Boot MVC với AWS Serverless Java Container

Ví dụ này minh họa Spring Boot 3 được gọi qua API Gateway REST API proxy event dạng v1 và AWS Lambda. Ứng dụng vẫn dùng `@RestController`; class handler đóng vai trò adapter giữa Lambda runtime và servlet application.

Ứng dụng Spring Boot:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}

@RestController
class HealthController {
    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("UP");
    }
}

record HealthResponse(String status) {}
```

Lambda stream handler:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import com.amazonaws.serverless.exceptions.ContainerInitializationException;
import com.amazonaws.serverless.proxy.model.AwsProxyRequest;
import com.amazonaws.serverless.proxy.model.AwsProxyResponse;
import com.amazonaws.serverless.proxy.spring.SpringBootLambdaContainerHandler;
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestStreamHandler;

public class StreamLambdaHandler implements RequestStreamHandler {
    private static final SpringBootLambdaContainerHandler<AwsProxyRequest, AwsProxyResponse> HANDLER;

    static {
        try {
            HANDLER = SpringBootLambdaContainerHandler.getAwsProxyHandler(
                    OrdersApplication.class);
        } catch (ContainerInitializationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @Override
    public void handleRequest(
            InputStream input,
            OutputStream output,
            Context context) throws IOException {
        HANDLER.proxyStream(input, output, context);
    }
}
```

Handler trên dùng API Gateway proxy event kiểu REST API v1. Nếu dùng API Gateway HTTP API v2, cần chọn handler/adapter hỗ trợ payload v2 và cấu hình integration tương ứng; không đưa event v2 vào parser v1. Tên class và method có thể thay đổi theo phiên bản AWS Serverless Java Container, vì vậy phải đồng bộ phiên bản dependency với ví dụ và tài liệu của bản đang dùng.

Các dependency cần có thường gồm adapter Spring Boot 3 của AWS Serverless Java Container và AWS Lambda Java Core. Dùng phiên bản tương thích với Java/Spring Boot của dự án, khai báo trong Maven hoặc Gradle và đóng gói toàn bộ dependency cần thiết vào artifact. Handler cấu hình ở Lambda phải trỏ đến class `StreamLambdaHandler` theo định dạng handler mà runtime yêu cầu.

Đoạn code minh họa cấu trúc tích hợp; một dự án thực tế cần bổ sung cấu hình build, API Gateway route, IAM role, biến môi trường, logging, security filter và kiểm thử event mẫu. Không khởi động một embedded HTTP server độc lập trong Lambda handler nếu adapter đã chịu trách nhiệm chuyển request vào servlet stack.

## 6. Tách nghiệp vụ khỏi HTTP controller

Một controller tốt chỉ điều phối giao thức. Nghiệp vụ nên nằm trong application service để HTTP, message và workflow có thể gọi cùng một logic.

```java
public record CreateOrderCommand(
        String customerId,
        String sku,
        int quantity,
        String idempotencyKey) {}

public record OrderAccepted(String orderId, String status) {}

@Service
public class OrderApplicationService {
    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderAccepted create(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // Trong ứng dụng thật, repository dùng transaction và idempotency key.
        Order order = orders.createOnce(command);
        return new OrderAccepted(order.id(), order.status());
    }
}
```

Controller MVC có thể nhận HTTP DTO rồi chuyển thành command. Spring Cloud Function có thể nhận cùng command từ event adapter. Việc tách lớp này giúp unit test service không cần dựng API Gateway event hoặc Spring MVC context.

Không để DTO của API Gateway hoặc message broker trở thành domain model. Adapter chịu trách nhiệm chuyển đổi các kiểu transport sang command nội bộ và chuyển kết quả nghiệp vụ thành HTTP response hoặc event.

## 7. Statelessness và lưu trạng thái bên ngoài

FaaS có thể scale từ một instance lên nhiều instance. Mỗi instance có bộ nhớ riêng và vòng đời không được bảo đảm. Dữ liệu cần tồn tại qua invocation phải được lưu ở hệ thống bền vững:

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Đơn hàng, thanh toán, trạng thái nghiệp vụ | Database hoặc data store có transaction phù hợp |
| Session người dùng | Session store dùng chung hoặc token có chiến lược thu hồi |
| File upload và file kết quả | Object storage |
| Cache dùng chung | Managed cache; dữ liệu cache phải có thể tái tạo |
| Message chờ xử lý | Queue hoặc event stream |
| Tiến độ workflow dài hạn | Workflow engine hoặc state store bền vững |
| Idempotency key và inbox | Database với unique constraint/TTL phù hợp |

File tạm trong `/tmp` hoặc thư mục tạm có thể hữu ích trong một invocation, nhưng không được xem là lưu trữ bền vững. Nếu file tạm còn tồn tại khi environment được tái sử dụng, dữ liệu cũ có thể lộ sang invocation khác. Dùng tên file ngẫu nhiên, quyền truy cập hạn chế và xóa dữ liệu nhạy cảm sau khi dùng.

Không dùng `@SessionAttributes`, in-memory HTTP session hoặc local cache làm nguồn sự thật trong môi trường có nhiều instance. Nếu cần session, cấu hình Spring Session với store dùng chung hoặc dùng cơ chế xác thực phù hợp.

## 8. Database connection và scale-out

Một vấn đề phổ biến khi chuyển Spring Boot sang FaaS là mỗi execution environment tạo một connection pool riêng. Nếu một function scale lên 100 instance và mỗi instance mở pool tối đa 10 connection, database có thể phải chịu tới khoảng 1.000 connection từ function, chưa tính ứng dụng khác.

Hãy tính tổng kết nối theo công thức gần đúng:

\[
Connections_{max} \approx Instances_{max} \times PoolSize_{perInstance}
\]

Đây là giới hạn cấu hình lý thuyết; số kết nối thực tế phụ thuộc việc pool tạo lazy hay eager, số invocation đồng thời và thời điểm instance bị giữ lại. Dù vậy, phép tính giúp tránh để FaaS mở kết nối vượt khả năng database.

Khuyến nghị:

- Đặt max pool size nhỏ và phù hợp với concurrency.
- Tạo datasource/client theo vòng đời context khi có thể tái sử dụng an toàn, nhưng không mở quá nhiều connection khi khởi tạo.
- Dùng connection proxy/pooling service nếu nền tảng và database hỗ trợ.
- Đặt connect timeout, socket timeout và query timeout.
- Đóng transaction nhanh; không giữ connection trong lúc chờ HTTP provider hoặc tác vụ không liên quan.
- Giới hạn concurrency của function theo năng lực database.
- Theo dõi connection count, pool wait time, timeout và lỗi exhausted pool.

Không nên tăng pool size chỉ để xử lý nhiều invocation hơn. Nếu database là nút thắt, tăng concurrency có thể làm thời gian chờ và số lỗi tăng mạnh. Có thể chuyển một phần công việc sang queue để điều tiết tốc độ ghi.

## 9. Cold start và thời gian khởi động Spring Boot

Cold start là độ trễ phát sinh khi nền tảng phải tạo execution environment mới trước khi xử lý invocation. Với Spring Boot, thời gian khởi động có thể gồm:

1. Chuẩn bị runtime và tải artifact.
2. Khởi động JVM hoặc runtime native.
3. Nạp class và dependency.
4. Component scan, auto-configuration và tạo Spring bean.
5. Khởi tạo logging, serializer, client và datasource.
6. Xử lý invocation đầu tiên.

Spring Boot có hệ sinh thái phong phú nhưng auto-configuration và reflection có thể làm tăng startup time và kích thước artifact. Không phải mọi bean đều cần được khởi tạo cho một function nhỏ.

### Cách giảm cold start

- Chỉ đưa dependency cần thiết vào artifact; tránh starter không sử dụng.
- Thu hẹp component scan và cấu hình auto-configuration phù hợp.
- Tránh gọi dịch vụ từ xa hoặc chạy truy vấn nặng trong constructor/`@PostConstruct`.
- Tái sử dụng HTTP client, serializer và SDK client thread-safe.
- Đo thời gian khởi tạo từng nhóm bean trước khi tối ưu.
- Dùng provisioned/pre-warmed capacity nếu SLA yêu cầu latency ổn định và chi phí cho phép.
- Đánh giá runtime snapshot hoặc JVM optimization nếu nhà cung cấp hỗ trợ.
- Cân nhắc Spring AOT/GraalVM Native Image khi ứng dụng tương thích và lợi ích startup đủ lớn.

Không tối ưu chỉ dựa trên thời gian cold start một lần. Hãy đo p50/p95/p99 latency, tỷ lệ cold start, memory, CPU và chi phí trong tải thực tế. Một giải pháp làm startup nhanh hơn nhưng tăng memory hoặc build complexity có thể không có lợi tổng thể.

### Spring AOT và GraalVM Native Image

Spring AOT xử lý một phần công việc phân tích ứng dụng ở build time. GraalVM Native Image biên dịch ứng dụng thành executable native, thường giúp giảm thời gian khởi động và footprint trong một số workload. Đổi lại, build native có thể phức tạp hơn và các tính năng dựa vào reflection, dynamic class loading, proxy hoặc resource cần khai báo hints phù hợp.

Trước khi chọn native image:

- Kiểm tra tất cả thư viện và driver có hỗ trợ native image.
- Bổ sung runtime hints cho reflection, serialization, proxy và resource nếu cần.
- Chạy integration test trên artifact native, không chỉ JVM mode.
- Đo memory và throughput; native không mặc định nhanh hơn ở mọi workload.
- Đánh giá thời gian build, debugging và hỗ trợ production.

JVM mode vẫn là lựa chọn phù hợp khi cần tương thích thư viện rộng, JIT tối ưu workload chạy lâu hoặc quy trình build native chưa đáng đầu tư.

## 10. Đóng gói và triển khai artifact

Có hai cách đóng gói thường gặp:

### ZIP/JAR cho managed Java runtime

Artifact phải có handler đúng, dependency cần thiết và cấu trúc mà runtime hỗ trợ. Với adapter Spring MVC, cần đóng gói Spring Boot application cùng AWS Serverless Java Container và Lambda Java Core. Có thể dùng Maven Shade Plugin hoặc cơ chế packaging được adapter hướng dẫn. Phải kiểm tra resource, service loader và file cấu hình không bị ghi đè khi tạo fat JAR.

### Container image

Container image chứa runtime và ứng dụng. Cách này phù hợp khi cần kiểm soát OS package, native library hoặc cách đóng gói. Tuy nhiên, cần dùng base image tương thích với nền tảng serverless, thiết lập entrypoint/handler đúng và giữ image gọn. Container image không loại bỏ cold start; kích thước image, khởi tạo JVM và Spring context vẫn ảnh hưởng startup.

Build nên có các bước:

1. Chạy unit test và kiểm tra dependency.
2. Build JAR hoặc image với profile production.
3. Kiểm tra artifact có handler, resource và dependency cần thiết.
4. Quét dependency và image theo quy trình bảo mật của tổ chức.
5. Deploy lên môi trường thử nghiệm với event thật hoặc event mẫu.
6. Chạy smoke test và kiểm tra log/metric.
7. Chuyển traffic theo chiến lược có thể rollback.

Không đưa secret vào JAR, image layer hoặc file cấu hình commit trong source. Dùng secret manager, parameter store hoặc cơ chế secret injection của nền tảng.

## 11. Cấu hình theo môi trường

Spring Boot có thể đọc cấu hình từ `application.yml`, profile và environment variables. Trong serverless, nên để cấu hình triển khai được truyền qua environment hoặc secret manager, ví dụ:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX:2}
      connection-timeout: ${DB_CONNECTION_TIMEOUT_MS:3000}

app:
  payment:
    base-url: ${PAYMENT_BASE_URL}
    timeout-ms: ${PAYMENT_TIMEOUT_MS:5000}
```

Ví dụ này chỉ minh họa cấu hình; giá trị mặc định cần được điều chỉnh theo runtime và tải thực tế. Mật khẩu database không nên lưu trong plain environment nếu nền tảng có secret manager chuyên dụng. Hãy giới hạn quyền function chỉ đọc secret mà nó cần.

Tránh gọi secret manager và config service nhiều lần trong từng request nếu có thể cache an toàn theo vòng đời environment. Nhưng khi secret được xoay vòng, cần có chiến lược refresh hoặc giới hạn thời gian cache. Không giữ secret trong log hoặc exception message.

## 12. Trigger HTTP và giới hạn request/response

Với HTTP trigger, API Gateway hoặc HTTP adapter thường đảm nhiệm TLS termination, routing, authentication sơ bộ, throttling và chuyển request thành event. Java function xử lý request rồi trả status code, headers và body theo giao thức integration.

Cần chú ý:

- API Gateway có giới hạn thời gian chờ, payload và header riêng.
- Function timeout không nhất thiết bằng timeout gateway.
- Request có thể bị client gửi lại khi client timeout dù function đã hoàn tất.
- Cần idempotency key cho thao tác tạo đơn, thanh toán hoặc ghi dữ liệu quan trọng.
- CORS phải được cấu hình ở đúng lớp và response lỗi cũng cần header phù hợp.
- Không giữ HTTP request mở trong thời gian dài để chờ công việc nền; trả mã tiếp nhận và theo dõi trạng thái qua API/event nếu nghiệp vụ cho phép.

Nếu công việc kéo dài hơn giới hạn request/response, hãy tiếp nhận yêu cầu, lưu trạng thái bền vững, gửi message hoặc khởi chạy workflow rồi trả `202 Accepted` cùng mã theo dõi. Client truy vấn trạng thái hoặc nhận webhook/callback sau khi hoàn tất.

## 13. Trigger message và event

Spring Boot service có thể xử lý message bằng Spring Cloud Function hoặc adapter riêng của nền tảng. Với trigger queue/stream, function thường nhận một batch event và cần trả kết quả theo semantics acknowledgement/checkpoint của trigger.

Các yêu cầu thiết kế:

- Parse và validate từng record; payload không hợp lệ cần được cách ly hoặc đưa vào DLQ.
- Xử lý idempotent vì thông điệp có thể được giao lại.
- Chỉ xác nhận/checkpoint sau khi side effect được lưu bền vững.
- Với batch, hiểu partial batch failure để một record lỗi không làm xử lý lại toàn bộ không cần thiết.
- Giữ thứ tự trong partition/group nếu nghiệp vụ yêu cầu.
- Giới hạn concurrency và batch size theo năng lực database hoặc API phụ thuộc.
- Truyền `eventId`, `correlationId` và tenant context theo hợp đồng.

Không chạy một vòng lặp `while(true)` để poll queue bên trong function nếu event source mapping đã chịu trách nhiệm poll. Với mô hình worker container dài hạn, vòng lặp consumer có thể phù hợp, nhưng đó là mô hình triển khai khác và cần quản lý shutdown, lease, rebalance và checkpoint.

## 14. Bảo mật và quyền truy cập

Mỗi function nên chạy với service identity riêng và quyền tối thiểu. Một function đọc đơn hàng không cần quyền xóa bucket; function gửi email không cần quyền đọc toàn bộ bảng khách hàng. Phân tách role theo nhiệm vụ giúp giảm phạm vi ảnh hưởng khi một dependency hoặc function bị xâm nhập.

Các lớp bảo vệ cần có:

- Xác thực caller ở API gateway hoặc Spring Security; kiểm tra authorization cho từng tài nguyên.
- Kiểm tra tenant context và không tin tenant ID tùy ý từ payload.
- Dùng IAM/service account để function truy cập queue, database proxy, object storage và secret.
- Mã hóa dữ liệu khi truyền và khi lưu; giới hạn quyền đọc log và DLQ.
- Không đóng gói secret vào artifact hoặc log request.
- Validate payload và giới hạn kích thước để giảm rủi ro dữ liệu độc hại.
- Cập nhật dependency và base image; kiểm tra CVE trong pipeline.

Nếu dùng Spring Security, kiểm tra adapter có chuyển tiếp đúng header, method, path và identity context. Với API Gateway authorizer, cần xác định claim nào được tin cậy và cách chuyển sang Spring Security principal. Không chỉ kiểm tra một header do client tự gửi để quyết định quyền truy cập.

## 15. Retry, timeout và idempotency trong Spring Boot FaaS

Một function có thể được gọi lại do trigger retry, workflow retry, client retry hoặc lỗi mạng. Nếu các lớp cùng retry mà không phối hợp, số lần gọi dependency có thể nhân lên. Hãy xác định retry owner và ngân sách tổng.

Trong Spring Boot:

- Cấu hình connect/read/request timeout rõ ràng cho `RestClient`, `WebClient` hoặc HTTP client đang dùng.
- Chỉ retry lỗi tạm thời như timeout kết nối, 429 hoặc 503 theo chính sách dependency.
- Dùng backoff và jitter, giới hạn attempts và tổng deadline.
- Không retry lỗi validation, lỗi quyền hoặc business rejection.
- Gắn idempotency key ổn định với một hành động nghiệp vụ.
- Ghi dấu xử lý cùng transaction với cập nhật dữ liệu khi có thể.
- Nếu timeout làm kết quả bên ngoài chưa rõ, tra cứu trạng thái trước khi gửi lại.

Ví dụ, `OrderApplicationService.create` cần thực hiện `createOnce` bằng unique constraint cho idempotency key. Nếu hai invocation cùng nhận request do client retry, database chỉ tạo một đơn và trả lại kết quả đã có. Không dựa vào synchronized block trong JVM vì các function instance khác nhau không chia sẻ lock.

## 16. Background task và scheduler

Các ứng dụng Spring Boot truyền thống thường dùng `@Scheduled` hoặc `@Async`. Trong FaaS, không nên giả định một instance sẽ sống liên tục để chạy scheduler hoặc hoàn tất tác vụ nền sau khi request trả về.

Thay thế bằng:

- Managed scheduler phát sự kiện theo lịch và kích hoạt function.
- Queue cho công việc nền cần retry và điều tiết tải.
- Workflow engine cho quy trình nhiều bước hoặc kéo dài.
- Event bus cho các consumer độc lập phản ứng với thay đổi nghiệp vụ.

`@Async` có thể dùng trong phạm vi invocation nếu function đợi kết quả hoàn tất trước khi trả response. Không khởi chạy thread rồi trả thành công trong khi công việc còn chạy; runtime có thể freeze hoặc kết thúc environment. Nếu cần công việc tiếp tục độc lập, ghi job vào queue hoặc workflow trước khi trả response.

Nếu dùng scheduler managed, thiết kế idempotency theo khoảng lịch hoặc business date để tránh hai lần trigger cùng một kỳ. Xử lý timezone, daylight saving, lịch chạy bù và trường hợp trigger đến trễ.

## 17. Observability: log, metric và trace

Một request có thể đi qua API Gateway, Lambda adapter, Spring filter, service, database và event bus. Log nên có cấu trúc và mang theo correlation ID hoặc trace context xuyên suốt các lớp.

Thông tin hữu ích:

- Invocation/request ID do nền tảng cấp.
- `correlationId`, `eventId`, `orderId` hoặc business key.
- Function name/version, trigger type và thời gian xử lý.
- Cold start indicator nếu runtime cung cấp.
- Database pool wait, dependency latency và timeout.
- Retry attempt, idempotency result và DLQ/partial batch failure.
- Kết quả nghiệp vụ và error code ổn định.

Metric nên theo dõi gồm invocation count, error rate, duration p50/p95/p99, timeout, concurrency, throttling, cold start, memory, queue age/lag, database connection và chi phí trên mỗi nghiệp vụ. Không ghi cookie, bearer token, secret hoặc toàn bộ payload nhạy cảm. Dùng sampling cho trace nếu lưu lượng cao và vẫn giữ đủ dữ liệu để điều tra lỗi hiếm.

Spring Boot Actuator có thể cung cấp health và metric endpoint, nhưng không nên mặc định public toàn bộ endpoint trong FaaS. Chỉ bật những metric cần thiết, bảo vệ endpoint và tích hợp với cơ chế quan sát của nền tảng.

## 18. Kiểm thử ứng dụng Spring Boot serverless

Kiểm thử nên được chia theo ranh giới:

| Loại kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test | Kiểm tra nghiệp vụ không phụ thuộc framework | Test `OrderApplicationService` với repository fake/mock |
| Spring slice test | Kiểm tra controller, validation, security hoặc serialization | `@WebMvcTest` cho controller |
| Context test | Xác minh Spring bean graph và cấu hình | `@SpringBootTest` với dependency giả lập |
| Adapter contract test | Kiểm tra event/API Gateway payload được chuyển đổi đúng | Event mẫu v1/v2, header và response |
| Integration test | Kiểm tra database, queue, secret và external API qua môi trường thử nghiệm | Testcontainers hoặc managed test resources |
| Deployment smoke test | Kiểm tra artifact thật sau deploy | Gọi endpoint, gửi event, kiểm tra log và permission |
| Failure test | Kiểm tra retry, timeout, duplicate và partial batch | Ngắt database, trả 429/503, dừng function giữa side effect |

Unit test không chứng minh adapter event đúng. Một bài kiểm thử tích hợp cần dùng đúng payload format của trigger, đặc biệt khi phân biệt API Gateway REST v1 và HTTP API v2. Kiểm tra cả response thành công và lỗi, CORS, serialization, security context và request ID.

Hãy kiểm thử cold start và warm invocation riêng. Nếu dùng native image, chạy test trên native artifact; JVM test không phát hiện hết vấn đề reflection hoặc resource hint. Nếu dùng provisioned capacity, kiểm tra cả thời gian khởi tạo và chi phí duy trì capacity.

## 19. Triển khai an toàn và rollback

Một lộ trình triển khai có thể gồm:

1. Tách nghiệp vụ khỏi controller và các chi tiết runtime.
2. Chọn adapter HTTP hoặc function adapter theo trigger.
3. Chuyển session, cache và trạng thái cần tồn tại sang dịch vụ dùng chung.
4. Giới hạn connection pool, concurrency, timeout và batch size.
5. Đóng gói artifact và cấu hình runtime/handler.
6. Cấp quyền tối thiểu, cấu hình secret và network access.
7. Deploy môi trường dev/staging; chạy contract test và smoke test.
8. Đo cold start, warm latency, memory, throughput và chi phí.
9. Chuyển traffic theo canary hoặc alias/version nếu nền tảng hỗ trợ.
10. Theo dõi error rate, timeout, lag và trạng thái nghiệp vụ; rollback nếu vượt ngưỡng.

Khi thay đổi schema event hoặc database, cần giữ tương thích giữa phiên bản cũ và mới trong thời gian có invocation hoặc message tồn đọng. Rollback function không tự rollback side effect đã xảy ra. Cần migration có tính tương thích ngược, idempotency và quy trình bù trừ khi cần.

## 20. Khi nào Spring Boot không phải lựa chọn tốt cho một function?

Spring Boot hữu ích khi ứng dụng cần dependency injection, cấu hình phong phú, validation, security và hệ sinh thái Spring. Nhưng một function nhỏ chỉ chuyển đổi payload hoặc xử lý một message đơn giản có thể không cần toàn bộ Spring context.

Hãy cân nhắc Java thuần hoặc framework khởi động nhẹ hơn khi:

- Function chỉ có một handler và vài dependency.
- Cold start là yêu cầu rất nghiêm ngặt.
- Artifact nhỏ và thời gian build/deploy quan trọng.
- Không cần servlet, auto-configuration hoặc phần lớn Spring ecosystem.

Hãy cân nhắc serverless container hoặc worker dài hạn khi:

- Công việc kéo dài hoặc cần chạy nền liên tục.
- Cần giữ kết nối WebSocket, streaming hoặc protocol stateful.
- Ứng dụng cần kiểm soát tiến trình hoặc thread trong thời gian dài.
- Workload ổn định với thời gian chạy liên tục khiến chi phí FaaS cao hơn container.

Quyết định nên dựa trên workload đo được: invocation rate, thời gian chạy, memory, cold start, dependency latency, concurrency, dữ liệu truyền và chi phí. Không có một framework Java phù hợp nhất cho mọi function.

## 21. Checklist trước khi đưa Spring Boot lên serverless

- [ ] Đã chọn rõ FaaS, Spring MVC adapter, Spring Cloud Function hay serverless container.
- [ ] Đã xác định đúng event format của HTTP/queue/stream trigger.
- [ ] Nghiệp vụ được tách khỏi controller và adapter.
- [ ] ApplicationContext và singleton bean không giữ trạng thái request/người dùng.
- [ ] Session, cache quan trọng và trạng thái nghiệp vụ nằm ở hệ thống dùng chung.
- [ ] Không dựa vào `@Scheduled`, background thread hoặc local file để duy trì công việc dài hạn.
- [ ] Connection pool và concurrency phù hợp với giới hạn database.
- [ ] Timeout dependency, function, gateway và workflow được phối hợp.
- [ ] Retry có giới hạn; side effect có idempotency và reconciliation.
- [ ] Cold start được đo; dependency và bean không cần thiết đã được loại bỏ.
- [ ] Native/AOT chỉ được chọn sau khi kiểm tra compatibility và integration test.
- [ ] Artifact chứa handler, dependency, resource và cấu hình cần thiết.
- [ ] Secret được quản lý ngoài artifact; function có quyền tối thiểu.
- [ ] Log/metric/trace có correlation ID nhưng không lộ credential hoặc dữ liệu nhạy cảm.
- [ ] Đã kiểm thử adapter contract, duplicate, timeout, cold start và deployment thật.
- [ ] Có chiến lược canary/rollback và tương thích schema trong thời gian chuyển phiên bản.

## Kết luận

Đưa Spring Boot lên serverless là quá trình thích nghi vòng đời và ranh giới tích hợp của ứng dụng với mô hình invocation, không chỉ là thay đổi cách đóng gói. Spring MVC adapter giúp giữ REST API hiện có; Spring Cloud Function phù hợp với logic hướng sự kiện; serverless container là lựa chọn khi cần giữ tiến trình web dài hạn. Dù chọn hướng nào, ứng dụng cần stateless giữa invocation, lưu trạng thái ở dịch vụ dùng chung, kiểm soát connection và concurrency, tối ưu cold start, bảo vệ quyền truy cập và thiết kế retry/idempotency. Đo latency, throughput và chi phí trên workload thật sẽ giúp quyết định Spring Boot có phù hợp cho từng function hay không.
