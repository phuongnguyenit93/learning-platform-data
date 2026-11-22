# Khôi phục liên kết trace khi thiếu builder, propagation hoặc ngữ cảnh bất đồng bộ

Một yêu cầu đi từ dịch vụ đặt hàng sang dịch vụ tồn kho vẫn có thể trả HTTP 200 trong khi hai dịch vụ xuất hiện ở hai trace khác nhau. Luồng nghiệp vụ đã chạy đúng, nhưng thông tin mô tả quan hệ giữa các thao tác đã bị mất ở một ranh giới.

Bài này hướng dẫn tìm đúng ranh giới đó và sửa ba nhóm nguyên nhân: HTTP client không nhận cấu hình quan sát của Spring Boot; hai đầu HTTP không truyền/đọc cùng định dạng ngữ cảnh; tác vụ bất đồng bộ không nhận ngữ cảnh của luồng gửi việc. Ví dụ dùng Spring Boot 3.3.x, Spring Framework 6.1 và Micrometer Tracing, với mã nguồn Java 17+. Không dùng cấu hình Spring Cloud Sleuth của thế hệ Boot 2.

## 1. Cần nối lại điều gì?

**Trace** là hành trình của một yêu cầu hoặc công việc qua nhiều thao tác. **Span** là một thao tác được ghi nhận trong hành trình đó. **Ngữ cảnh trace** chứa thông tin cần để nhận biết hành trình và quan hệ cha–con, chẳng hạn trace ID, span ID và cờ lấy mẫu.

| Thành phần | Vai trò | Điều dễ nhầm |
| --- | --- | --- |
| Trace ID | Nhận diện cùng một hành trình | Hai dịch vụ có log không có nghĩa là chúng cùng trace |
| Span ID | Nhận diện một thao tác | Không yêu cầu mọi span trong một trace có cùng span ID |
| Instrumentation, tức cơ chế gắn quan sát vào thao tác | Tạo và kết thúc observation/span cho HTTP, tác vụ hoặc thao tác khác | Có Actuator không làm mọi đối tượng tự tạo bằng `new` đều được gắn quan sát |
| Propagation, tức truyền ngữ cảnh | Ghi ngữ cảnh ra môi trường truyền dẫn và đọc lại ở đầu nhận | Đưa trace ID vào log chưa truyền được ngữ cảnh qua HTTP |
| Scope, tức phạm vi ngữ cảnh hiện hành | Cho phép mã đang chạy truy cập observation/span hiện hành | Một span tồn tại chưa chắc đang là span hiện hành trên luồng này |
| Exporter và hệ thống lưu trace | Gửi và lưu các span để tìm kiếm, hiển thị | Có liên kết đúng chưa đảm bảo dữ liệu đã được gửi/lưu thành công |

Với một lời gọi HTTP đồng bộ, mô hình cần quan sát là:

```text
orders: server span
    -> orders: HTTP client span
        -> ngữ cảnh trong HTTP request
            -> inventory: server span
```

Trace ID phải được nối xuyên suốt nếu hai dịch vụ chấp nhận ngữ cảnh đó. Trong cấu hình W3C không dùng cơ chế ghép chung span của Brave ở ví dụ, các thao tác có span ID riêng. Trường `parent-id` trong `traceparent` của request từ orders sang inventory là ID của HTTP client span ở orders, không nhất thiết bằng span ID trong controller orders.

Nếu công việc chuyển sang executor trước khi gọi HTTP, có thêm một ranh giới:

```text
luồng nhận HTTP ở orders
    -> gửi tác vụ vào executor
        -> khôi phục ngữ cảnh trên luồng xử lý
            -> HTTP client được gắn quan sát
                -> HTTP request có ngữ cảnh
```

Builder đúng giải quyết cách tạo HTTP client. Truyền ngữ cảnh qua executor giải quyết việc HTTP client đang đứng dưới trace cha nào. Hai điều kiện này bổ sung cho nhau.

## 2. Chẩn đoán theo ranh giới, không sửa theo cảm giác

Chọn một request có thể tái hiện và ghi nhận: trace ID tại điểm gọi, ngữ cảnh thực sự rời HTTP client, header thực sự đến dịch vụ nhận và trace ID tại đầu nhận. Trong môi trường kiểm thử cục bộ, có thể đặt xác suất lấy mẫu bằng 1 để giảm nhiễu. Không suy ra nguyên nhân chỉ từ một ảnh chụp giao diện hệ thống lưu trace.

| Hiện tượng | Giả thuyết cần kiểm chứng trước |
| --- | --- |
| Có span hiện hành ở orders, nhưng request ra không có header trace | HTTP client không được gắn quan sát hoặc đang dùng cấu hình truyền ngữ cảnh khác |
| Client tạo header nhưng inventory không nhận được | Proxy, gateway hoặc tầng trung gian đã lọc/ghi đè header |
| Inventory nhận header nhưng tạo trace ID khác | Định dạng không tương thích, header không hợp lệ hoặc đầu nhận chủ động không chấp nhận ngữ cảnh |
| Gọi đồng bộ nối đúng, gọi qua executor bị tách | Ngữ cảnh mất khi đổi luồng hoặc tác vụ chạy trên executor khác dự kiến |
| Worker không có span cha nhưng request ra vẫn có header trace mới | HTTP client được gắn quan sát đã tạo một trace mới; điều này chưa nối lại trace ban đầu |
| Hai đầu có trace ID đúng nhưng hệ thống lưu trace thiếu dữ liệu | Kiểm tra lấy mẫu, gửi dữ liệu, lỗi collector và phạm vi tìm kiếm |
| Log không có trace ID nhưng mã đọc được span hiện hành | Kiểm tra cấu hình log và tích hợp MDC trước khi kết luận mất trace |

Không dùng việc hai ứng dụng đều gọi được `/actuator/health` làm bằng chứng tracing đã hoạt động. Health, metrics và tracing là các chức năng khác nhau.

## 3. Trường hợp thứ nhất: HTTP client đi vòng qua builder của Boot

### 3.1. Vì sao chỉ thêm dependency chưa đủ?

Khi các điều kiện tự cấu hình được đáp ứng, Boot cung cấp builder và áp dụng các bộ tùy chỉnh để HTTP client sử dụng cơ chế quan sát của ứng dụng. Observation của HTTP client kết hợp với tracing handler mới tạo span và truyền ngữ cảnh tương ứng.

Một đối tượng tự tạo có thể gửi HTTP hoàn toàn bình thường nhưng không nhận những cấu hình đó. Một bean do Spring quản lý cũng không tự động được sửa bên trong chỉ vì nó là bean: cách xây dựng đối tượng vẫn quan trọng.

| Client | Cách dễ bỏ qua tự cấu hình | Cách ưu tiên |
| --- | --- | --- |
| `RestTemplate` | `new RestTemplate()` hoặc tự tạo `new RestTemplateBuilder()` | Tiêm `RestTemplateBuilder` do Boot cung cấp rồi gọi `build()` |
| `RestClient` | `RestClient.create()` hoặc `RestClient.builder()` tự tạo | Tiêm `RestClient.Builder` do Boot cung cấp |
| `WebClient` | `WebClient.create()` hoặc `WebClient.builder()` tự tạo | Tiêm `WebClient.Builder` do Boot cung cấp khi ứng dụng có các dependency phù hợp |

Điểm quyết định không phải chỉ có chữ `Builder` trong mã. Builder được tiêm từ Boot và builder tự tạo bằng phương thức tĩnh không có cùng cấu hình mặc định của ứng dụng.

Trong ví dụ hoàn chỉnh bên dưới, `inventoryClient` dùng builder được tiêm; `rawInventoryClient` cố ý dùng `RestClient.create(baseUrl)` để tái hiện lỗi. Cả hai đều là bean và đều gọi cùng một URL.

### 3.2. Nếu vẫn mất liên kết sau khi đổi builder

Kiểm tra chính đối tượng được sử dụng tại điểm gọi:

1. Có đang tiêm đúng bean, đặc biệt khi có nhiều HTTP client và `@Qualifier`?
2. Có chỗ nào tự khai báo bean builder khiến tự cấu hình của Boot phải nhường chỗ không?
3. Có đang thay observation registry bằng registry rỗng hoặc no-op không?
4. Có bộ tùy chỉnh nào tắt/thay cấu hình quan sát sau khi builder đã được tùy chỉnh không?
5. Có tracing bridge hoạt động và tracing handler tương ứng, hay mới chỉ có bộ đo metrics?

Trong phạm vi một ứng dụng, dùng hệ phiên bản do Boot quản lý và chọn tracing bridge có chủ đích. Không thêm cả Brave và OpenTelemetry một cách tùy tiện để thử sửa mất trace. Một hệ thống có thể dùng các triển khai khác nhau giữa các dịch vụ nếu chúng thống nhất cách truyền ngữ cảnh.

Nếu thư viện bắt buộc tự tạo client, phải tích hợp observation/tracing với đúng API của thư viện đó. Không coi việc thêm một header chứa trace ID là cách thay thế đầy đủ cho instrumentation.

## 4. Trường hợp thứ hai: hai đầu HTTP không hiểu cùng ngữ cảnh

### 4.1. Thống nhất định dạng trước khi điều tra sâu hơn

Hai định dạng thường gặp là W3C Trace Context và B3. Với W3C, header chính là `traceparent`; `tracestate` có thể đi kèm để mang trạng thái riêng của hệ thống tracing. B3 có dạng một header `b3` hoặc dạng nhiều header như `X-B3-TraceId`, tùy cấu hình.

Ở hai dịch vụ Boot 3.3.x của bài thực hành, chọn rõ:

```yaml
management:
  tracing:
    propagation:
      type: w3c
```

Không giả định tên header theo nhà cung cấp hệ thống lưu trace. Brave có thể truyền W3C; dùng một hệ thống lưu trace cụ thể cũng không tự quyết định giao thức truyền ngữ cảnh giữa hai dịch vụ.

Đối với hệ thống chuyển đổi giao thức theo giai đoạn, cần xác minh định dạng mà từng phiên bản dịch vụ nhận và phát ra thực tế. Không thay đồng loạt cấu hình production chỉ để làm cho một lần kiểm tra thành công.

### 4.2. Hiểu đúng `traceparent`

Một giá trị dùng trong kiểm thử:

```text
00-11111111111111111111111111111111-2222222222222222-01
```

Với phiên bản `00`:

- `11111111111111111111111111111111` là trace ID gồm 32 ký tự hexadecimal.
- `2222222222222222` là ID của span phía gửi, gồm 16 ký tự hexadecimal.
- `01` có bit sampled được bật.
- Trace ID hoặc parent ID toàn số 0 không hợp lệ.

Dịch vụ nhận tạo server span theo ngữ cảnh được trích xuất. Khi dịch vụ đó gọi tiếp, HTTP client tạo ngữ cảnh của thao tác gửi rồi chèn header tương ứng. Không cần và không nên sao chép nguyên xi `traceparent` đầu vào sang mọi request đầu ra bằng một interceptor tự viết: làm như vậy có thể bỏ mất quan hệ với client span vừa được tạo.

Tên HTTP header không phân biệt hoa thường. Chỉ đổi `Traceparent` thành `traceparent` không sửa được lỗi định dạng hoặc thiếu instrumentation.

### 4.3. Xác định nơi header biến mất

Quan sát theo thứ tự:

```text
ngữ cảnh hiện hành trong orders
    -> header sau instrumentation của client
        -> header sau proxy/gateway
            -> header inventory thực sự nhận
                -> ngữ cảnh hiện hành trong inventory
```

Một interceptor tùy chỉnh chạy trước lúc instrumentation chèn header có thể thấy header còn trống. Khi kiểm tra cần biết vị trí quan sát trong chuỗi xử lý; header mà máy nhận thực sự nhận là bằng chứng rõ hơn việc log quá sớm trong client.

Nếu header đến inventory đầy đủ nhưng trace ID mới được tạo, kiểm tra cấu hình bên nhận, tính hợp lệ của header và chính sách chấp nhận ngữ cảnh từ bên ngoài. Một ranh giới tin cậy có thể được thiết kế để bắt đầu trace mới; phải phân biệt quyết định đó với lỗi cấu hình.

Header trace thường nằm trên request. Việc response không chứa `traceparent` không chứng minh propagation đã hỏng: framework không bắt buộc trả lại header đó cho trình gọi.

## 5. Trường hợp thứ ba: mất ngữ cảnh khi chuyển sang bất đồng bộ

### 5.1. Vì sao đổi luồng có thể làm tách trace?

Trong mô hình xử lý đồng bộ thông thường, ngữ cảnh hiện hành được gắn với luồng qua cơ chế như `ThreadLocal`. Executor tái sử dụng các luồng đã có; luồng xử lý tác vụ không mặc nhiên có ngữ cảnh của luồng gửi việc.

Các vị trí cần tìm gồm:

- `@Async`.
- `ExecutorService.submit(...)` hoặc `execute(...)`.
- `CompletableFuture.supplyAsync(...)` không truyền executor phù hợp.
- Các bước tiếp nối như `thenApplyAsync(...)` lại chuyển sang một executor khác.
- Chuỗi reactive vượt qua ranh giới không được tích hợp truyền ngữ cảnh.

`CompletableFuture` là kiểu biểu diễn kết quả bất đồng bộ, không phải công cụ truyền ngữ cảnh trace. `InheritableThreadLocal` cũng không phải cách sửa chung cho thread pool vì quan hệ tạo luồng khác quan hệ gửi từng tác vụ.

### 5.2. Dùng decorator cho đúng executor

Spring Framework 6.1 cung cấp `ContextPropagatingTaskDecorator`. Trong ứng dụng Boot có tích hợp Micrometer phù hợp, decorator chụp ngữ cảnh đã được đăng ký tại lúc gửi tác vụ, mở lại khi chạy và khôi phục ngữ cảnh trước đó khi kết thúc.

Ở ví dụ, executor `traceExecutor` có decorator; `plainExecutor` cố ý không có. `@Async("traceExecutor")` phải thực sự trỏ tới executor được cấu hình.

Decorator không tạo một span nghiệp vụ mới cho mọi tác vụ. Nó trước hết khôi phục ngữ cảnh hiện hành. HTTP client bên trong tác vụ vẫn tạo client span của nó. Nếu cần biểu diễn riêng một thao tác nghiệp vụ, có thể tạo observation/span con và quản lý vòng đời rõ ràng, sau khi đã sửa việc truyền ngữ cảnh.

Các điều kiện dễ bị bỏ sót:

1. Lệnh gọi `@Async` phải đi qua proxy Spring. Gọi `this.linked()` từ cùng đối tượng không kích hoạt cơ chế `@Async` thông thường.
2. Bean chứa phương thức và bean executor phải do Spring quản lý.
3. Không cấu hình decorator cho một executor nhưng thực tế gửi việc vào common pool hoặc một executor khác.
4. Chụp ngữ cảnh khi ngữ cảnh cha còn hiện hành. Chụp sau khi đã chuyển sang một luồng mất ngữ cảnh không khôi phục được thông tin đã mất.
5. Truyền ngữ cảnh tracing không đồng nghĩa tự động truyền mọi trạng thái khác như transaction hoặc `SecurityContext`.

### 5.3. Khi dùng executor thuần

Đoạn sau là mã tích hợp đặt trong một phương thức đang có ngữ cảnh cha, không phải chương trình độc lập:

```java
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import java.util.concurrent.Executor;

// executor đã được khởi tạo và quản lý vòng đời ở nơi khác.
void submitWork(Executor executor, Runnable work) {
    ContextSnapshot snapshot = ContextSnapshotFactory.builder()
            .build()
            .captureAll();
    executor.execute(snapshot.wrap(work));
}
```

Snapshot chỉ chụp những loại ngữ cảnh có accessor được đăng ký. Trong chương trình tự tích hợp ngoài Boot, cần thiết lập registry/accessor đúng; chỉ thêm dependency `context-propagation` chưa tự tạo ra một hệ thống tracing.

Không tự giải quyết bằng cách `MDC.put("traceId", ...)`. MDC phục vụ log; HTTP client lấy ngữ cảnh từ hệ thống observation/tracing, không coi một chuỗi tự đặt trong MDC là trace cha hợp lệ. Với scope tự mở, luôn đóng bằng `try-with-resources`; với span tự tạo, kết thúc span trong `finally` khi thích hợp để tránh rò ngữ cảnh giữa các tác vụ dùng chung luồng.

## 6. Bài thực hành: so sánh bốn đường gọi

### 6.1. Chuẩn bị dự án độc lập

Tạo dự án thử nghiệm sau. Đây là ứng dụng minh họa độc lập, không yêu cầu sửa cấu hình build của một repository có sẵn.

```text
trace-link-lab/
├── pom.xml
└── src/main/
    ├── java/demo/trace/
    │   ├── TraceLabApplication.java
    │   ├── ClientConfiguration.java
    │   ├── AsyncConfiguration.java
    │   ├── TraceCalls.java
    │   ├── AsyncCalls.java
    │   └── TraceController.java
    └── resources/application.yml
```

Dùng JDK 17+ và Maven. Phiên bản 3.3.5 dưới đây được cố định để ví dụ có môi trường cụ thể; đây không phải đề nghị chọn phiên bản triển khai production.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>trace-link-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Actuator cung cấp các tích hợp quan sát; bridge Brave nối Micrometer Tracing với triển khai tracer. Không cần hệ thống lưu trace bên ngoài để so sánh ID/header trong bài thực hành. Dependency exporter và cấu hình gửi dữ liệu là phần riêng nếu muốn xem giao diện trace.

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: orders
management:
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
    brave:
      span-joining-supported: false
logging:
  pattern:
    level: "%5p [${spring.application.name:},%X{traceId:-},%X{spanId:-}]"
```

Xác suất 1.0 dùng để quan sát dễ hơn trong phòng thực hành, không phải một cách sửa propagation. Định dạng W3C được chọn ở cả hai tiến trình. Tắt span joining của Brave giúp quan hệ giữa client span và server span dễ phân biệt.

### 6.2. Mã nguồn đầy đủ

`TraceLabApplication.java`:

```java
package demo.trace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TraceLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TraceLabApplication.class, args);
    }
}
```

`ClientConfiguration.java`:

```java
package demo.trace;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {
    @Bean
    RestClient inventoryClient(RestClient.Builder builder,
            @Value("${inventory.base-url:http://localhost:8081}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }

    @Bean
    RestClient rawInventoryClient(
            @Value("${inventory.base-url:http://localhost:8081}") String baseUrl) {
        return RestClient.create(baseUrl);
    }

    @Bean
    RestTemplate inventoryTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
```

`inventoryTemplate` minh họa cách tạo `RestTemplate` bằng builder được tiêm. Các endpoint của bài này dùng `RestClient`. Không cần thêm WebFlux chỉ để chạy bài thực hành.

`AsyncConfiguration.java`:

```java
package demo.trace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {
    @Bean("traceExecutor")
    ThreadPoolTaskExecutor traceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("trace-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean("plainExecutor")
    ThreadPoolTaskExecutor plainExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("plain-worker-");
        return executor;
    }
}
```

Spring khởi tạo và quản lý vòng đời hai executor vì chúng là bean. Hai executor có cùng kích thước để điểm khác biệt cần quan sát là decorator, không phải số lượng luồng.

`TraceCalls.java`:

```java
package demo.trace;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class TraceCalls {
    public record Snapshot(String traceId, String spanId) {}
    public record Seen(String traceId, String spanId, String incomingTraceparent) {}
    public record Result(String mode, Snapshot atCallSite, Seen downstream) {}

    private final Tracer tracer;
    private final RestClient client;
    private final RestClient rawClient;

    public TraceCalls(Tracer tracer,
            @Qualifier("inventoryClient") RestClient client,
            @Qualifier("rawInventoryClient") RestClient rawClient) {
        this.tracer = tracer;
        this.client = client;
        this.rawClient = rawClient;
    }

    public Snapshot snapshot() {
        Span span = tracer.currentSpan();
        if (span == null) {
            return new Snapshot("(none)", "(none)");
        }
        return new Snapshot(span.context().traceId(), span.context().spanId());
    }

    public Result call(String mode, boolean raw) {
        Snapshot before = snapshot();
        RestClient selected = raw ? rawClient : client;
        Seen seen = selected.get()
                .uri("/inventory")
                .retrieve()
                .body(Seen.class);
        return new Result(mode, before, seen);
    }
}
```

`atCallSite` là ngữ cảnh trước khi gửi HTTP. Nếu không có span hiện hành, mã trả đúng chuỗi `"(none)"`. `downstream` chứa dữ liệu do inventory trả về. Ghi nhận ở hai vị trí này giúp phân biệt mất cha trên worker với mất header HTTP.

`AsyncCalls.java`:

```java
package demo.trace;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncCalls {
    private final TraceCalls calls;

    public AsyncCalls(TraceCalls calls) {
        this.calls = calls;
    }

    @Async("traceExecutor")
    public CompletableFuture<TraceCalls.Result> linked() {
        return CompletableFuture.completedFuture(calls.call("async-linked", false));
    }

    @Async("plainExecutor")
    public CompletableFuture<TraceCalls.Result> detached() {
        return CompletableFuture.completedFuture(calls.call("async-detached", false));
    }
}
```

Mặc dù dùng `CompletableFuture.completedFuture(...)`, phần thân phương thức vẫn chạy trên executor khi được gọi qua proxy `@Async`. Công việc đã được thực hiện trong luồng đó trước khi tạo future hoàn tất. Đặt `AsyncCalls` và controller ở hai bean tránh lỗi tự gọi trong cùng đối tượng.

`TraceController.java`:

```java
package demo.trace;

import java.util.concurrent.CompletableFuture;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceController {
    private final TraceCalls calls;
    private final AsyncCalls asyncCalls;

    public TraceController(TraceCalls calls, AsyncCalls asyncCalls) {
        this.calls = calls;
        this.asyncCalls = asyncCalls;
    }

    @GetMapping("/inventory")
    public TraceCalls.Seen inventory(
            @RequestHeader(value = "traceparent", required = false) String header) {
        TraceCalls.Snapshot current = calls.snapshot();
        return new TraceCalls.Seen(current.traceId(), current.spanId(), header);
    }

    @GetMapping("/orders/sync")
    public TraceCalls.Result sync() {
        return calls.call("sync-linked", false);
    }

    @GetMapping("/orders/raw")
    public TraceCalls.Result raw() {
        return calls.call("sync-raw", true);
    }

    @GetMapping("/orders/async")
    public CompletableFuture<TraceCalls.Result> linked() {
        return asyncCalls.linked();
    }

    @GetMapping("/orders/async-detached")
    public CompletableFuture<TraceCalls.Result> detached() {
        return asyncCalls.detached();
    }
}
```

Endpoint inventory trả lại header nhận được để phục vụ kiểm thử cục bộ. Đây là dữ liệu ứng dụng chủ động đưa vào JSON, không phải hành vi mặc định trả header trace của Spring.

### 6.3. Biên dịch và chạy hai tiến trình

Tại thư mục chứa `pom.xml`, đóng gói:

```bash
mvn clean package
```

Terminal thứ nhất chạy inventory:

```bash
java -jar target/trace-link-lab-1.0.0.jar --server.port=8081 --spring.application.name=inventory
```

Terminal thứ hai chạy orders:

```bash
java -jar target/trace-link-lab-1.0.0.jar --server.port=8080 --spring.application.name=orders --inventory.base-url=http://localhost:8081
```

Hai tiến trình dùng cùng mã nguồn để giữ ví dụ gọn, nhưng có ngữ cảnh JVM độc lập và trao đổi qua HTTP. Chờ cả hai khởi động thành công. Nếu cổng đã có ứng dụng khác sử dụng, đổi cổng và `inventory.base-url` tương ứng.

Terminal thứ ba:

```bash
curl --fail --silent http://localhost:8080/orders/sync
curl --fail --silent http://localhost:8080/orders/raw
curl --fail --silent http://localhost:8080/orders/async
curl --fail --silent http://localhost:8080/orders/async-detached
```

Trong Windows PowerShell có alias `curl`, dùng `curl.exe` để gọi đúng chương trình cURL. Kết quả là JSON; trace/span ID thay đổi theo mỗi request. Không đối chiếu ID của bốn request độc lập với nhau.

### 6.4. Cách đọc kết quả chính xác

Gọi `T` là trace ID của request hiện tại ở orders, `U` là trace ID mới khác `T`. Đây là ký hiệu giải thích quan hệ, không phải chuỗi mà chương trình in ra.

| Endpoint | `atCallSite.traceId` | `downstream.traceId` | `downstream.incomingTraceparent` | Kết luận |
| --- | --- | --- | --- | --- |
| `/orders/sync` | `T` | `T` | Có, chứa trace ID `T` | Builder và propagation nối đúng |
| `/orders/raw` | `T` | `U` | `null` | Raw client bỏ qua cấu hình quan sát |
| `/orders/async` | `T` | `T` | Có, chứa trace ID `T` | Decorator giữ ngữ cảnh khi chuyển luồng |
| `/orders/async-detached` | `"(none)"` | `U` | Có, chứa trace ID `U` | Worker mất cha; client tạo trace mới cho lời gọi HTTP |

Hàng cuối là một điểm chẩn đoán quan trọng: **có header trace không đồng nghĩa còn liên kết với trace của request gốc**. Builder hoạt động nhưng không thể tự tìm lại trace cha đã mất trước khi gọi client.

Trong đường gọi đồng bộ có liên kết, `atCallSite.spanId` là server span ở orders. Parent ID trong header ở inventory thuộc client span của orders. Không dùng điều kiện ba span ID phải bằng nhau để xác nhận thành công.

### 6.5. Kiểm tra bằng trace ID đầu vào đã biết

Gửi một W3C header hợp lệ vào orders:

```bash
curl --fail --silent -H "traceparent: 00-11111111111111111111111111111111-2222222222222222-01" http://localhost:8080/orders/sync
```

Trong cấu hình bài thực hành, hai trường sau phải cùng là `11111111111111111111111111111111`:

- `atCallSite.traceId`.
- `downstream.traceId`.

Header trong `downstream.incomingTraceparent` phải giữ trace ID đó, nhưng parent ID của nó thuộc client span mới ở orders, không sao chép cố định `2222222222222222`. Chạy lại lệnh có thể tạo các span ID khác. Chỉ tái sử dụng ID cố định trong kiểm thử có kiểm soát; request nghiệp vụ độc lập cần có danh tính trace phù hợp.

### 6.6. Tự gây lỗi để kiểm chứng giả thuyết

Thực hiện từng thay đổi riêng, khởi động lại tiến trình bị thay đổi và so sánh trong cùng một request:

1. Đổi client đang dùng sang raw client: trace ID vẫn có ở orders nhưng header đến inventory mất.
2. Đổi `@Async("traceExecutor")` sang `@Async("plainExecutor")`: tại worker không có span cha; HTTP client vẫn phát một ngữ cảnh mới.
3. Chỉ ở inventory, đổi định dạng sang `b3` trong khi orders vẫn phát W3C: trong ví dụ đơn giản chỉ có W3C header, inventory không dùng được ngữ cảnh đó để nối trace. Việc nhìn thấy chuỗi header trong JSON chưa chứng minh tracer đã chấp nhận nó.
4. Khôi phục W3C ở cả hai phía và executor có decorator; kiểm tra lại quan hệ trace ID.

Sau mỗi thử nghiệm, trả cấu hình về trạng thái ban đầu trước khi kiểm tra nguyên nhân tiếp theo. Không bật đồng thời nhiều cách gắn instrumentation vì có thể tạo span trùng và che mất nguyên nhân.

## 7. Nếu đường gọi sử dụng WebClient hoặc Reactor

Builder vẫn quan trọng với `WebClient`, nhưng `TaskDecorator` cho thread pool không thay thế cơ chế ngữ cảnh của Reactor.

Trong ứng dụng Boot 3.3.x có Reactor và các tích hợp Micrometer tương ứng, có thể dùng:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Cần kiểm tra cả builder được tiêm và ngữ cảnh ở lúc đăng ký thực thi chuỗi reactive. Ngữ cảnh Reactor đi theo chuỗi đăng ký thực thi, không đơn giản theo luồng đang lắp ráp chuỗi.

Các lỗi hay gặp là tự gọi `subscribe()` tách khỏi luồng xử lý hiện tại, tạo công việc ngoài chuỗi đang mang ngữ cảnh hoặc đọc `ThreadLocal` quá sớm rồi coi đó là giá trị của mọi lần thực thi. Không dùng `block()` trong đường xử lý WebFlux để ép trở lại mô hình đồng bộ nhằm che lỗi mất ngữ cảnh.

Nếu một bước lại gửi việc sang executor tùy chỉnh, kiểm tra thêm chính ranh giới đó. Cấu hình Reactor không tự gắn decorator cho mọi executor mà ứng dụng tạo ra.

## 8. Phân biệt mất liên kết với thiếu dữ liệu hiển thị

### Có trace ID nhưng không thấy trace trên hệ thống lưu trữ

Kiểm tra lần lượt:

- Span có được lấy mẫu và được ghi nhận không?
- Span đã kết thúc chưa, hay còn chờ tác vụ chưa hoàn tất?
- Exporter có được cấu hình và có gửi thành công không?
- Địa chỉ collector, giao thức, xác thực và kết nối có đúng không?
- Bộ lọc dịch vụ, khoảng thời gian tìm kiếm và độ trễ nhập dữ liệu có phù hợp không?

Ứng dụng mẫu không cấu hình exporter nên không hứa có dữ liệu trên giao diện Zipkin hay hệ thống khác. Nó kiểm tra liên kết qua ngữ cảnh hiện hành và header.

### Lấy mẫu không phải sửa builder hoặc executor

Quyết định lấy mẫu liên quan đến việc ghi nhận/gửi span. Ngữ cảnh vẫn có thể được truyền ngay cả khi trace không được lấy mẫu. Đặt `probability: 1.0` không bổ sung instrumentation cho raw client và không đưa ngữ cảnh vào một executor thường.

Ngược lại, khi đã có ngữ cảnh lấy mẫu từ thượng nguồn, phải xét cách tracer xử lý quyết định đó. Không coi xác suất cục bộ là lời bảo đảm mọi request trong một hệ thống phân tán đều được lưu.

### Log giống nhau không đủ chứng minh đúng

Một correlation ID do ứng dụng tự truyền có thể hữu ích cho tìm log nhưng không tạo quan hệ span cha–con. Không đặt trace ID làm nhãn metric có số lượng giá trị tăng không giới hạn chỉ để hỗ trợ điều tra. Dùng ID trong log/trace theo đúng mục đích và kiểm tra quan hệ trong một request cụ thể.

## 9. Tiêu chí xác nhận đã khôi phục

Một lần sửa có thể được coi là đạt khi các bằng chứng sau cùng nhất quán:

1. HTTP client thực sự được gọi nhận cấu hình observation/tracing mong muốn.
2. Tại điểm trước khi gửi việc và tại điểm chạy tác vụ, ngữ cảnh còn thuộc trace gốc nếu thiết kế yêu cầu điều đó.
3. Request đầu ra chứa đúng định dạng ngữ cảnh, và dịch vụ nhận thực sự nhận được nó.
4. Đầu nhận tạo span thuộc đúng trace, với quan hệ cha–con phù hợp; không ép mọi span ID giống nhau.
5. Lặp lại với nhiều request độc lập không làm tác vụ sau thừa hưởng trace của tác vụ trước.
6. Các trường hợp lỗi hoặc ngoại lệ vẫn đóng scope/kết thúc span do mã tự quản lý đúng cách.
7. Nếu yêu cầu có giao diện trace, kiểm tra thêm lấy mẫu và gửi dữ liệu; không dùng kết quả HTTP 200 thay thế bước này.

Khi điều tra, luôn hỏi ngữ cảnh mất ở ranh giới nào: tạo client, truyền qua HTTP hay chuyển công việc sang nơi thực thi khác. Khôi phục đúng ranh giới giúp nối lại hành trình mà không phải tự ghép trace ID bằng log hoặc header thủ công.
