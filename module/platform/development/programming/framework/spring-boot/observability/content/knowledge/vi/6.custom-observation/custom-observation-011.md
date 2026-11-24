# Tránh instrument cùng một đoạn hai lần trong Spring Boot Observability

> **Chương:** Custom observation  
> **Bài:** Tránh instrument cùng một đoạn hai lần  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vấn đề: một công việc bị đo như hai công việc

Giả sử dịch vụ đặt hàng xử lý **100 yêu cầu tạo đơn**. Trong một cấu hình đúng, metric ghi nhận 100 lần thực hiện thao tác nghiệp vụ `orders.checkout`. Nhưng sau khi thêm một custom observation, dashboard bất ngờ báo **200 lần checkout** dù không có traffic mới. Trên trace, cùng một đoạn xử lý còn xuất hiện dưới hai span gần giống nhau.

Nguyên nhân có thể là **instrument trùng** (*double instrumentation*): hai cơ chế cùng quan sát **một ranh giới công việc với cùng ý nghĩa**. Ví dụ:

- Spring Boot đã tự tạo observation cho HTTP server, nhưng developer tạo thêm observation khác để đo lại toàn bộ cùng request ở controller.
- Một phương thức đã được AOP instrument qua `@Observed`, trong khi thân phương thức tiếp tục gọi `Observation.createNotStarted(...)` cho đúng đoạn code đó.
- `ObservationHandler` đo metrics hoặc tạo spans được đăng ký hai lần vào cùng registry.
- Ứng dụng đồng thời bật nhiều cơ chế instrumentation cho cùng một thư viện (chẳng hạn một integration tự động và một instrumentation thủ công tương đương).
- Một thao tác dùng cả `@Timed` và `@Observed` với tên/semantics chồng nhau, khi các aspect và meter handler tương ứng đều hoạt động.

Lỗi này làm tăng chi phí thu thập, gây hiểu nhầm về throughput, tỉ lệ lỗi, latency, số span và ảnh hưởng đến cảnh báo SLI/SLO. Nếu cùng một observation được ghi hai lần vào Timer có cùng tags, **`_count` có thể tăng gấp đôi**. Nếu hai cơ chế ghi bằng các tag khác nhau, dữ liệu có thể nằm ở hai time series riêng nhưng vẫn bị đếm trùng khi cộng toàn bộ.

**Điều cần bảo vệ là ranh giới ngữ nghĩa của phép đo**: với cùng một lần thực hiện của một công việc được định nghĩa, có đúng một cơ chế sở hữu phép đo chính. Không phải cứ thấy hai span lồng nhau hoặc hai loại metric là lỗi: các thao tác *thật sự khác nhau* trong một request nên được quan sát riêng khi hữu ích.

## 2. Phân biệt trùng instrumentation với quan sát lồng nhau hợp lệ

Một HTTP request có thể bao gồm nhiều công việc đáng đo:

~~~mermaid
flowchart TD
    A["HTTP POST /api/orders — observation server do framework tạo"] --> B["orders.checkout — observation nghiệp vụ"]
    B --> C["inventory.reserve — observation bước giữ hàng"]
    B --> D["payment.authorize — observation lời gọi thanh toán"]
    C --> E["db.query — instrumentation cơ sở dữ liệu nếu bật"]
    D --> F["http.client.requests — instrumentation HTTP client nếu bật"]
~~~

Trong ví dụ này, HTTP server, nghiệp vụ checkout, bước giữ hàng và lời gọi ra ngoài có **phạm vi, mục đích và tên khác nhau**. Chúng tạo ra các Timer hoặc span lồng nhau có chủ ý. Thời gian các span bao gồm và chồng lấp nhau nên **không cộng trực tiếp duration của mọi span** rồi coi đó là thời gian request.

Ngược lại, nếu hai observation cùng bắt đầu ngay khi vào `checkout()`, kết thúc ngay khi ra khỏi `checkout()`, đều gọi là `orders.checkout` và đều đại diện cho “một lần checkout” thì đây thường là đo trùng.

| Tình huống | Phân loại | Lý do |
| --- | --- | --- |
| HTTP server observation và observation của bước `inventory.reserve` | Hợp lệ | Hai ranh giới và câu hỏi khác nhau |
| `@Observed("orders.checkout")` và manual `orders.checkout` cùng bọc toàn bộ phương thức | Trùng | Cùng đo một hoạt động nghiệp vụ |
| Một Observation kích hoạt cả meter handler và tracing handler | Hợp lệ | Một nguồn instrumentation tạo hai loại tín hiệu |
| Hai `DefaultMeterObservationHandler` cùng xử lý một observation | Có nguy cơ trùng | Cùng trách nhiệm ghi meter được đăng ký hai lần |
| Parent span checkout và child span gọi HTTP client | Hợp lệ | Parent biểu diễn nghiệp vụ, child biểu diễn dependency |
| Hai HTTP server spans tương tự do hai agent/instrumentation cùng hook vào request | Cần điều tra | Có thể đo trùng request boundary |

Cách nhận biết đáng tin cậy là xác định **một lần thực hiện công việc** có tạo bao nhiêu observation cùng semantics, rồi kiểm tra cơ chế nào khởi tạo từng observation. Chỉ nhìn tên span hoặc biểu đồ đếm chưa đủ để kết luận.

## 3. Bản đồ những nơi Spring Boot có thể đã instrument sẵn

Với Spring Boot có Actuator, Micrometer Observation và các thư viện phù hợp, framework tự instrument một số công việc. Phạm vi chính xác phụ thuộc phiên bản Spring Boot, starter, client và auto-configuration.

| Thành phần | Instrumentation thường gặp | Cần cân nhắc khi thêm custom |
| --- | --- | --- |
| HTTP server (Spring MVC/WebFlux) | Request observation, HTTP server metrics và có thể server span | Không bọc lại toàn bộ controller chỉ để có thêm request latency |
| HTTP client (RestClient, RestTemplate, WebClient khi dùng builder/configuration đã instrument) | Client request observation, propagation headers, HTTP client metrics/spans | Không thêm một observation có cùng nghĩa cho mỗi HTTP exchange nếu đã được đo |
| Tracing | Tracing handler tạo span từ Observation; bridge tới tracer | Không đăng ký một nhóm tracing handler thứ hai cho cùng registry |
| MeterRegistry | Handler metrics chuyển Observation thành Timer/metrics | Không đăng ký meter handler hai lần |
| Messaging, scheduling hoặc các thư viện phụ thuộc | Có thể có instrumentation chuyên biệt | Xác minh thực tế trước khi tạo observation bao trùm cùng boundary |
| Business service | Thường do nhóm phát triển quyết định nghiệp vụ nào cần đo | Custom observation hữu ích khi biểu diễn bước nghiệp vụ có nghĩa |

Tên metric thường gặp trên HTTP server là `http.server.requests`; trên Prometheus, Timer thường xuất `http_server_requests_seconds_count` và `http_server_requests_seconds_sum`. Đây là **ví dụ theo convention**, không phải lời khẳng định rằng mọi phiên bản đều dùng đúng các tên này.

**Cách xác minh đang có instrumentation:** chạy một request thử, xem `/actuator/metrics` và `/actuator/prometheus`, kiểm tra tracing UI nếu có, rồi so sánh với điểm vào/ra của code. Cần biết chính xác framework đang đo ở đâu trước khi thêm instrument.

## 4. Lỗi điển hình: @Observed và Observation thủ công cùng bọc một method

### 4.1. Ví dụ sai về mặt thiết kế

Khi `ObservedAspect` hoạt động, annotation `@Observed` tạo một observation quanh lời gọi phương thức qua Spring AOP. Trong ví dụ dưới, lập trình viên lại tạo **một observation khác** với cùng tên và cùng ranh giới bên trong method:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.annotation.Observed;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class DuplicateCheckoutService {
    private final ObservationRegistry registry;

    public DuplicateCheckoutService(ObservationRegistry registry) {
        this.registry = registry;
    }

    @Observed(name = "orders.checkout", contextualName = "checkout")
    public <T> T checkout(Supplier<T> work) {
        // Không nên: @Observed đã bọc đúng phương thức checkout này.
        Observation duplicate = Observation.createNotStarted(
                "orders.checkout", registry).start();

        try (Observation.Scope scope = duplicate.openScope()) {
            return work.get();
        } catch (RuntimeException ex) {
            duplicate.error(ex);
            throw ex;
        } finally {
            duplicate.stop();
        }
    }
}
~~~

Nếu aspect được bật và lời gọi đi **qua proxy Spring**, một lần `checkout(...)` có thể tạo hai observation lồng nhau có cùng tên:

~~~mermaid
sequenceDiagram
    participant Caller
    participant AOP as ObservedAspect
    participant Service as checkout()
    participant Registry
    Caller->>AOP: checkout(work)
    AOP->>Registry: start orders.checkout (1)
    AOP->>Service: invoke method
    Service->>Registry: start orders.checkout (2)
    Service->>Service: work.get()
    Service->>Registry: stop orders.checkout (2)
    Service-->>AOP: return
    AOP->>Registry: stop orders.checkout (1)
    AOP-->>Caller: result
~~~

Tùy metadata của annotation và observation thủ công, hai lần ghi có thể rơi vào hai tập tags khác nhau. Kết luận cần kiểm chứng ở meter/trace thực tế; không thể khẳng định mọi truy vấn nhất định tăng chính xác 2 lần.

`@Observed` cần AOP instrumentation phù hợp, thường là bean `ObservedAspect`, để có hiệu lực trên method. Nếu aspect không hoạt động hoặc method tự gọi nội bộ mà không qua proxy, annotation có thể không được intercept. Khi đó chỉ có custom observation thủ công chạy; điều này **không làm thiết kế đăng ký trùng trở nên đúng** ở môi trường khác.

### 4.2. Cách sửa A: dùng @Observed làm nguồn đo duy nhất

Nếu chỉ cần biết duration, lỗi và tên thao tác, annotation là cách ngắn gọn:

~~~java
import io.micrometer.observation.annotation.Observed;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    @Observed(name = "orders.checkout", contextualName = "checkout")
    public <T> T checkout(Supplier<T> work) {
        return work.get();
    }
}
~~~

Đoạn này minh họa khi đã **có `ObservedAspect` được đăng ký và phù hợp mô hình Spring AOP**. Không cần tạo observation thủ công trong cùng phương thức.

Nếu cần cấu hình aspect trong ứng dụng chưa có, có thể khai báo **một lần**:

~~~java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ObservationAspectConfiguration {
    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
~~~

Phải kiểm tra trước ứng dụng đã có `ObservedAspect` bean hay chưa. Đừng tạo bean thứ hai chỉ vì chưa thấy metric, vì vấn đề có thể nằm ở proxy, scope, handler hoặc exporter.

### 4.3. Cách sửa B: tự quản lý một Observation

Khi cần metadata động, event nghiệp vụ hoặc phân loại kết quả, có thể bỏ `@Observed` và chọn **một observation thủ công**:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ObservationRegistry registry;

    public CheckoutService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T checkout(String channel, Supplier<T> work) {
        Observation observation = Observation.createNotStarted(
                "orders.checkout", registry)
            .lowCardinalityKeyValue("channel", normalizeChannel(channel))
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = work.get();
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String input) {
        if ("web".equals(input)) return "web";
        if ("mobile".equals(input)) return "mobile";
        return "other";
    }
}
~~~

Mẫu này có một lần `start()` và `stop()` cho một lần gọi nghiệp vụ, đóng scope bằng `try-with-resources` và báo lỗi cho handler khi có exception. `channel` được chuẩn hóa thành tập hữu hạn để không làm bùng nổ cardinality; `outcome` được thêm sau khi biết kết quả, trước khi stop.

Lưu ý riêng cho `CompletableFuture` hoặc thao tác bất đồng bộ: đừng gọi `stop()` ngay sau khi submit công việc nếu mục tiêu là đo đến lúc hoàn tất thật. Cần hoàn tất observation khi callback nhận kết quả và truyền ngữ cảnh theo cơ chế của executor/Reactor đang dùng.

## 5. Tránh tự đo lại HTTP server request đã được framework theo dõi

Ví dụ một controller Spring MVC:

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    // Có thể chồng lấp với instrumentation request HTTP tự động.
    @Observed(name = "http.server.requests")
    @PostMapping("/api/orders")
    public String createOrder() {
        return "created";
    }
}
~~~

Annotation trên có thể tạo thêm observation với tên request server mặc định, nếu `ObservedAspect` đang hoạt động. Nhưng Spring MVC cũng có instrumentation HTTP server riêng. Hai phép đo cùng tên không có nghĩa chúng có cùng conventions/tags; việc đưa cùng tên vào một Timer có thể gây thiếu nhất quán tags, báo cáo khó đọc hoặc đếm trùng trong các tổng hợp.

Một thiết kế rõ ràng hơn:

~~~java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final CheckoutService checkoutService;

    public OrderController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @PostMapping("/api/orders")
    public String createOrder() {
        // HTTP server được Spring instrument nếu cấu hình phù hợp.
        return checkoutService.checkout("web", () -> "created");
    }
}
~~~

Trong cách này, HTTP server observation đo request boundary; `orders.checkout` đo một **bước nghiệp vụ riêng**. Chúng có thể lồng nhau nhưng khác câu hỏi: HTTP request chậm bao nhiêu, và nghiệp vụ checkout mất bao lâu. Nếu muốn thêm thông tin cho HTTP observation đang có, xem các API/customization của framework như `ServerRequestObservationConvention` hoặc cơ chế instrumentation được hỗ trợ, thay vì mặc nhiên dựng observation thứ hai cho cùng request.

Đừng sửa tên `http.server.requests` thành một tên tùy ý chỉ để che duplicate trên dashboard; điều cần giải quyết là **ai sở hữu ranh giới đo**.

## 6. Trùng handler không đồng nghĩa trùng Observation

Ngay cả khi mã nghiệp vụ chỉ tạo **một** `Observation`, dữ liệu vẫn có thể bị ghi hai lần nếu cùng một chức năng được đăng ký trùng handler.

Ví dụ minh họa trong Micrometer độc lập:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

void configureWrongly(
        ObservationRegistry observationRegistry,
        MeterRegistry meterRegistry) {

    observationRegistry.observationConfig()
        .observationHandler(
            new DefaultMeterObservationHandler(meterRegistry))
        .observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
}
~~~

Hai handler trên đều có mục tiêu ghi Timer vào cùng `MeterRegistry`. Tùy cách triển khai và tập tags, mỗi handler có thể ghi một mẫu riêng cho cùng một observation; dữ liệu `count` dễ bị phóng đại.

Cấu hình đúng khi thực sự tự quản lý toàn bộ registry:

~~~java
void configureOnce(
        ObservationRegistry observationRegistry,
        MeterRegistry meterRegistry) {

    observationRegistry.observationConfig()
        .observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
}
~~~

**Trong Spring Boot có Actuator, không dùng cả hai đoạn trên để đăng ký bổ sung khi framework đã đăng ký meter handler.** Thông thường inject `ObservationRegistry` do Spring Boot cấu hình và chỉ tạo custom handler khi cần hành vi mới. Hai đường đăng ký dễ trùng:

1. Một `@Component` hoặc `@Bean` kiểu `ObservationHandler` đã được Boot đăng ký tự động.
2. Chính instance đó, hoặc một handler tương đương, lại được thêm qua `ObservationRegistryCustomizer` hay đoạn `observationConfig().observationHandler(...)` thủ công.

Trùng chức năng tracing cũng có thể dẫn đến hai span cho một observation. Vì vậy cần phân biệt hai lỗi khác nhau: **hai observation cùng theo dõi một công việc** và **một observation bị hai handler cùng làm một việc**. Biện pháp sửa nằm ở những tầng khác nhau.

## 7. All matching và first matching: phối hợp đúng tín hiệu

Một `Observation` có thể và nên tạo cả **metrics** lẫn **tracing**. Đó là phối hợp tín hiệu, không phải trùng.

| Cơ chế | Ý nghĩa | Nguy cơ khi dùng sai |
| --- | --- | --- |
| `AllMatchingCompositeObservationHandler` | Cho tất cả handler con phù hợp chạy | Hai handler cùng chức năng có thể đo trùng |
| `FirstMatchingCompositeObservationHandler` | Chọn handler con phù hợp đầu tiên theo thứ tự | Một handler quá rộng có thể che các handler chuyên biệt, khiến mất tín hiệu |
| Nhiều handler độc lập được registry cấu hình | Mỗi handler phục vụ chức năng của mình | Cần kiểm tra không đăng ký hai lần cùng trách nhiệm |

Đối với tracing, nhóm `FirstMatchingCompositeObservationHandler` thường được dùng để chọn giữa:

- `PropagatingSenderTracingObservationHandler` cho context gửi tới dịch vụ khác.
- `PropagatingReceiverTracingObservationHandler` cho context nhận từ dịch vụ khác.
- `DefaultTracingObservationHandler` cho trường hợp thông thường.

Đặt sender/receiver chuyên biệt trước fallback thông thường; đừng dùng all matching để cho nhiều tracing handler cùng tạo span trên cùng context. Ngược lại, đừng gộp meter handler với tracing handler vào **cùng một first matching composite** nếu muốn cả hai tín hiệu: khi một handler khớp, handler còn lại có thể bị loại.

~~~mermaid
flowchart LR
    A["Một Observation"] --> B["Meter handler"]
    A --> C["Nhóm first matching tracing"]
    B --> D["Một tập metrics đúng semantics"]
    C --> E{"Context?"}
    E -->|Sender| F["Tracing sender"]
    E -->|Receiver| G["Tracing receiver"]
    E -->|Khác| H["Tracing mặc định"]
    F --> I["Span phù hợp"]
    G --> I
    H --> I
~~~

Trường hợp đặc biệt: `TracingAwareMeterObservationHandler` có thể kết hợp meter với tracer nhằm hỗ trợ exemplar khi stack tương thích. Nếu dùng loại handler này, cần xem nó **thay thế chức năng meter nào**, tránh giữ đồng thời một meter handler độc lập cùng ghi cùng dữ liệu.

## 8. Một nguồn đo cho mỗi công việc: lập bản đồ trách nhiệm

Trước khi viết custom observation, hãy lập bảng nhỏ xác định ranh giới và người sở hữu phép đo. Đối với một dịch vụ đặt hàng:

| Ranh giới | Owner đo chính | Tên/loại tín hiệu | Có viết custom observation? |
| --- | --- | --- | --- |
| HTTP server nhận `POST /api/orders` | Spring MVC instrumentation | `http.server.requests` và server span nếu tracing bật | Không cho cùng request boundary |
| Logic `checkout` xử lý quy tắc nghiệp vụ | Service nghiệp vụ | `orders.checkout` | Có, chọn AOP hoặc manual |
| HTTP client gọi `inventory-api` | HTTP client instrumentation nếu client được cấu hình đúng | HTTP client request, client span | Không đo trùng cùng HTTP exchange |
| Logic tính phí tùy chỉnh | Service nghiệp vụ | `orders.pricing` | Có nếu cần phân tích riêng |
| JDBC/database call | Instrumentation tương ứng khi bật | DB spans/metrics theo integration | Chỉ bổ sung nếu là thao tác nghiệp vụ khác |

Mô hình này còn giúp chọn **tên metric có ý nghĩa và tag có tập giá trị hữu hạn**. Đừng gọi custom observation bằng tên framework sẵn có như `http.server.requests` nếu semantics thực chất là xử lý checkout. Tránh tạo nhiều quan sát tên gần giống nhau nhưng phạm vi trùng nhau, vì dashboard sẽ khó phân biệt và tổng hợp sai.

Một số thao tác có thể xuất hiện **nhiều lần hợp lệ** trong cùng request: checkout gọi inventory hai lần do retry; một request thực hiện hai truy vấn SQL. Khi đó, số đo của operation tương ứng có thể lớn hơn số HTTP request mà không phải lỗi instrument. Cần biết định nghĩa “một lần” trong từng phép đo.

## 9. Kiểm chứng bằng metrics: số lần thực hiện và tags

### 9.1. Chuẩn bị một thử nghiệm có kiểm soát

Giả sử môi trường test có một instance, không có traffic nền, không có retry, một request kích hoạt đúng một `checkout()`. Thực hiện **10 request thành công** và quan sát metric HTTP server cùng metric nghiệp vụ.

Không so sánh trực tiếp `http.server.requests` với `orders.checkout` trong môi trường production nhiều đường đi: một request HTTP có thể không gọi checkout, hoặc gọi nhiều lần. So sánh 1:1 chỉ hợp lệ khi kịch bản test thực sự đảm bảo ánh xạ 1:1.

### 9.2. Endpoint Actuator và Prometheus

Với Spring Boot có Actuator và Prometheus registry:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Ví dụ khi ứng dụng chạy cổng 8080:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/metrics/orders.checkout
curl http://localhost:8080/actuator/prometheus
~~~

Quan sát `measurements`, `availableTags` và chuỗi Prometheus tương ứng. Một Timer `orders.checkout` thường có `orders_checkout_seconds_count`, `orders_checkout_seconds_sum`, và `_bucket` chỉ nếu được cấu hình histogram. Tên và tag thực tế phụ thuộc registry/version/convention, nên luôn xem dữ liệu exporter trước khi viết truy vấn.

**Lưu ý:** `/actuator/metrics` hiển thị số liệu trong registry tại thời điểm truy vấn; Prometheus còn có chu kỳ scrape. Sau khi phát sinh request, hãy chờ một lần scrape khi kiểm tra trên backend. Trong test cục bộ, hiệu số trước/sau là bằng chứng mạnh hơn nhìn một giá trị `count` tích lũy từ nhiều phút trước.

### 9.3. Truy vấn PromQL để tìm dấu hiệu trùng

Nếu exporter tạo chuỗi `orders_checkout_seconds_count`, tốc độ checkout trong cửa sổ 5 phút là:

~~~promql
sum(rate(orders_checkout_seconds_count[5m]))
~~~

Có thể so sánh với HTTP request rate của route phù hợp:

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    uri="/api/orders",method="POST"
  }[5m])
)
~~~

Nếu `orders.checkout` là một lần cho mỗi request, hai giá trị **kỳ vọng gần nhau** sau khi đủ thời gian scrape và điều kiện kiểm soát được đảm bảo. Tỉ số xấp xỉ 2 có thể là dấu hiệu trùng, nhưng cũng có thể do retry, controller gọi hai lần, request nội bộ hoặc phép đo có khác semantics.

Nếu hai instrument tạo series có label `channel` hoặc `outcome` khác nhau, tổng hợp theo mọi tags có thể khiến số đếm tăng; vì vậy cần drill-down:

~~~promql
sum by (channel, outcome) (
  rate(orders_checkout_seconds_count[5m])
)
~~~

Đừng mặc định mọi exporter có những label này. Truy vấn chỉ đúng khi code gắn tags tương ứng. Nếu cần đo chính xác trên một lần test, dùng chênh lệch counter/Timer ở registry trước–sau và đối chiếu một request thực tế.

## 10. Kiểm chứng bằng tracing: phát hiện span lặp

Tracing cung cấp một góc nhìn khác: một lần request xuất ra một trace có các span theo ranh giới nghiệp vụ và dependency. Khi nghi ngờ instrument trùng:

1. Chọn một request có trace được **sampling** và xuất thành công; ghi lại trace ID từ log hoặc UI.
2. Mở trace, quan sát thứ tự cha–con, tên span, start time và duration.
3. Tìm hai span cùng tên/cùng ranh giới gần như hoàn toàn, ví dụ cả hai đều là `orders.checkout` và ôm cùng một lời gọi code.
4. Xác định nguồn tạo mỗi span: framework instrumentation, `@Observed`/AOP, observation thủ công, tracing bridge, agent hoặc handler custom.
5. Sau khi bỏ một nguồn đo trùng, chạy lại một request tương đương để xác nhận số span và mối quan hệ parent-child.

~~~mermaid
flowchart TD
    A["HTTP server span"] --> B["orders.checkout (AOP)"]
    B --> C["orders.checkout (manual)"]
    C --> D["HTTP client: inventory"]
    E["Có thể trùng"] -.-> B
    E -.-> C
~~~

Nếu AOP và manual cùng bọc đúng một method, hai span `orders.checkout` liên tiếp là tín hiệu khả nghi. Nhưng **hai span có cùng tên chưa tự chứng minh lỗi**: hai lần retry hợp lệ hoặc hai đoạn code khác nhau cũng có thể có tên giống nhau. Dùng thời gian, call path, event và mã instrument để phân biệt.

Sampling có thể che giấu dấu hiệu trên trace backend. Không tìm thấy hai span ở một request **không đủ** để kết luận instrumentation không trùng. Trong môi trường test phù hợp, có thể dùng cấu hình sampling nhất quán hoặc công cụ quan sát trong bộ nhớ để kiểm tra, còn ở production vẫn giữ chính sách sampling đã chọn.

## 11. Kiểm chứng ở cấp handler bằng registry tối giản

Để tách vấn đề **logic instrument** khỏi network/exporter, có thể kiểm tra số lần callback trên một `ObservationRegistry` độc lập. Ví dụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;

public final class DuplicateHandlerDemo {
    static final class CounterHandler
            implements ObservationHandler<Observation.Context> {

        private final AtomicInteger stops;

        CounterHandler(AtomicInteger stops) {
            this.stops = stops;
        }

        @Override
        public boolean supportsContext(Observation.Context context) {
            return "orders.checkout".equals(context.getName());
        }

        @Override
        public void onStop(Observation.Context context) {
            stops.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger stops = new AtomicInteger();

        // Chỉ đăng ký một handler.
        registry.observationConfig()
            .observationHandler(new CounterHandler(stops));

        for (int i = 0; i < 10; i++) {
            Observation.createNotStarted("orders.checkout", registry)
                .observe(() -> {
                    // Một lần nghiệp vụ, không cần exporter.
                });
        }

        System.out.println(stops.get()); // Kỳ vọng: 10
    }
}
~~~

Ví dụ trên chỉ kiểm chứng số callback `onStop`, không trực tiếp kiểm chứng số metric series hay span được export. Để tái hiện đăng ký trùng, đăng ký **hai handler cùng tăng vào một counter**: số callback tổng có thể tăng 20 cho 10 observation. Cách đó chứng minh vấn đề ở lớp handler, độc lập với Prometheus hoặc tracing.

Với ứng dụng Spring Boot thật, nên dùng các integration test kiểm tra cấu hình registry và một đường request; không tự tạo một registry khác trong service chỉ để các số đếm “trông đúng” ở test. Registry mới có thể không mang theo các handler, predicate, filter và tracer của ứng dụng.

## 12. Khi số đếm tăng đôi nhưng không phải double instrumentation

Một số nguyên nhân tạo ra hiện tượng tương tự:

| Hiện tượng | Giải thích hợp lệ có thể có | Cách phân biệt |
| --- | --- | --- |
| `orders.checkout` có số đếm gấp đôi HTTP POST | Mỗi request gọi checkout hai lần | Kiểm tra call path và log nghiệp vụ có correlation |
| Client có nhiều span HTTP | Retry hoặc redirect tạo thêm HTTP exchange | Kiểm tra số request gửi ra và thử tắt retry trong môi trường test |
| Hai instance đều có cùng số đếm | Mỗi instance xử lý traffic riêng, `sum` toàn cụm cộng hợp lệ | Nhóm theo `instance`, `pod` hoặc nhãn triển khai |
| Có cả Timer count và Counter count | Một thao tác được đo bằng hai metric **khác tên, khác mục đích** | Tránh cộng hai metric làm một đơn vị request |
| Latency business + HTTP server đều tăng | Hai phép đo ranh giới khác nhau | Không cộng thời gian lồng nhau như các chi phí độc lập |
| Traces thưa hơn metrics | Sampler chỉ xuất một phần traces | Kiểm tra sampling trước khi nghi tracing handler hỏng |
| Một exporter gửi về hai collector | Duplicate ingestion/pipeline ở backend, không phải code Observation tạo hai lần | So sánh dữ liệu tại registry/app và ở backend |
| Một method annotated không tạo span | Aspect chưa hoạt động hoặc gọi nội bộ không qua Spring proxy | Kiểm tra AOP/proxy thay vì tự thêm manual ngay lập tức |

Một lần “đo hai lần” trong công việc thực tế cũng có thể là **hai sự kiện có thật**. Chẳng hạn một checkout có bước xác nhận và một bước retry đều gọi cùng API; nếu mục tiêu là đếm *attempts*, hai count là chính xác. Nếu mục tiêu là đếm *logical checkouts*, phải định nghĩa một metric khác ở boundary cao hơn.

Vì vậy trước khi xóa instrumentation, hãy ghi rõ **đơn vị đếm**: HTTP request, business operation, attempt, message delivery hay database call.

## 13. Quy trình sửa lỗi an toàn, theo thứ tự nguyên nhân

1. **Mô tả ranh giới:** định nghĩa “một lần `orders.checkout`” bắt đầu/kết thúc ở đâu; thống nhất metric name và tags cần thiết.
2. **Liệt kê nguồn đo:** auto instrumentation của framework, `@Observed`, `@Timed`, custom `Observation`, agent, interceptor, handler metrics/tracing, registry customizer.
3. **Xác định loại trùng:** hai observation cùng boundary, một observation có hai handler cùng chức năng, hay dữ liệu bị nhân đôi sau exporter.
4. **Chọn owner:** dùng instrumentation chuẩn khi nó đã bao phủ boundary; dùng một custom observation cho bước nghiệp vụ chưa có instrument. Nếu dùng annotation thì không bọc manual cùng phạm vi.
5. **Sửa tại nguồn:** bỏ annotation/manual wrapper trùng, hoặc bỏ bean/registration của handler trùng. Không chỉ đổi tên metric hay thêm bộ lọc truy vấn để che hiện tượng.
6. **Kiểm tra hành vi:** tạo workload có số lần xác định; đối chiếu Timer count trước–sau, số span/parent-child khi được sample và logs theo request.
7. **Xác nhận hậu quả:** đảm bảo request latency, error rate, custom business metrics, propagation và liên kết metrics–logs–traces vẫn còn chính xác.

Đối với ứng dụng lớn, thao tác sửa có thể ảnh hưởng dashboard/alert dùng tên metric cũ. Nếu một metric trùng đã từng được dùng trong SLO, cần kiểm tra lại công thức và ngưỡng sau sửa, bởi dữ liệu mới sẽ có semantics đúng hơn. Tránh so sánh hai giai đoạn trước/sau mà không chú thích sự thay đổi instrumentation.

### Cảnh báo về ObservationPredicate

`ObservationPredicate` cho phép loại observation có điều kiện, nhưng không phải lựa chọn đầu tiên để chữa double instrumentation. Một predicate chặn theo tên rộng có thể đồng thời loại bỏ observation hợp lệ, làm mất metrics/traces của những hoạt động khác dùng cùng tên. Hãy tìm và loại bỏ **nguồn đo trùng** trước, chỉ dùng predicate khi có chính sách chủ động rõ ràng về những observation cần bỏ.

## 14. Tình huống sản xuất: sau triển khai, số checkout tăng 100%

**Bối cảnh.** Dịch vụ `order-api` đang xử lý khoảng 40 request checkout mỗi giây, error rate khoảng 0,5%. Sau khi thêm annotation để theo dõi nghiệp vụ, metrics hiển thị `orders.checkout` tăng tới 80 lần/giây. Lưu lượng HTTP server vẫn ổn định. Trace đôi khi có hai span `orders.checkout` gần như cùng phạm vi.

**Điều tra.** Nhóm so sánh một request test không retry với code của `checkout()`. Phương thức đã tạo observation thủ công để gắn `channel` và `outcome`; annotation `@Observed(name = "orders.checkout")` mới thêm vào cùng method. `ObservedAspect` đang hoạt động, nên một lời gọi tạo hai observation. Hai observation có thể mang bộ tags khác nhau, khiến các dashboard tổng hợp theo tên đếm đôi.

**Khắc phục.** Nhóm giữ observation thủ công vì cần phân loại outcome sau khi xử lý và xóa annotation trên method. Sau đó gửi 20 request test, kiểm tra hiệu số Timer count, danh sách labels và trace của các request được sample. `orders.checkout` trở về gần với số request checkout hợp lệ, không còn cặp span trùng. HTTP server instrumentation và các span dependency vẫn hoạt động.

**Bài học.** Không phải lỗi exporter hay sampling; nguyên nhân nằm ở **hai nguồn instrumentation cùng sở hữu một đoạn code**. Chọn một nguồn đo cho boundary nghiệp vụ và kiểm chứng bằng một kịch bản có số lần thực thi xác định giúp xử lý dứt điểm.

## 15. Bài tập thực hành

### Bài tập A — xác định trùng hay hợp lệ

Với từng cặp sau, phân loại và giải thích:

1. Server span `POST /api/orders` và span `orders.checkout` trong service.
2. `@Observed("orders.checkout")` trên method, bên trong method còn gọi manual `Observation.createNotStarted("orders.checkout", ...)` cho toàn bộ thân hàm.
3. Một observation `orders.checkout` được cả meter handler và tracing handler xử lý.
4. Hai `DefaultMeterObservationHandler` cùng đăng ký vào một registry và sử dụng chung MeterRegistry.
5. Một client span cho request đầu và client span cho retry thật sau timeout.

Mong đợi: trường hợp 2, 4 cần sửa trùng; trường hợp 1, 3 và 5 thường hợp lệ khi chúng thật sự biểu diễn các hoạt động hoặc tín hiệu khác nhau.

### Bài tập B — viết lại service

Cho một `CheckoutService` đang kết hợp `@Observed` với observation thủ công. Hãy chọn **một** cơ chế, vẫn bảo đảm:

- Đo duration đầy đủ cho thao tác đồng bộ.
- Khi lỗi, `Observation` được báo `error(ex)` (nếu dùng manual).
- Có hai tags `channel=web/mobile/other` và `outcome=success/error` trong trường hợp manual.
- Không đặt `orderId` hay `requestId` vào metric label.
- Scope được đóng và observation được stop trên cả luồng thành công/lỗi.

### Bài tập C — kiểm tra định lượng

Trong môi trường test không có background traffic, gọi API đúng 50 lần. Từ trước và sau chạy thử:

1. Đo chênh lệch `http.server.requests` cho route cụ thể.
2. Đo chênh lệch Timer count `orders.checkout`.
3. Mở một trace được sample, kiểm tra một span business checkout và các span dependency thực tế.
4. Bật lại ví dụ đo trùng trong môi trường thử nghiệm để quan sát metric và trace thay đổi thế nào.
5. Sửa đúng nguồn trùng và xác minh số đếm trở về đúng semantics.

Không dựa vào snapshot PromQL trước/sau khi chưa tính cửa sổ `rate()` và chu kỳ scrape. Khi muốn kiểm chứng chính xác số event trong một đơn vị test, ưu tiên counter/Timer count trong bộ nhớ hoặc hiệu số counter trên interval đã kiểm soát.

### Câu hỏi tự kiểm tra

1. Tại sao hai span lồng nhau không nhất thiết là duplicate?
2. Nếu `@Observed` không có hiệu lực, cần kiểm tra gì trước khi tạo manual observation?
3. Khi một observation bị đăng ký hai meter handler, số observation thực sự có tăng không?
4. Vì sao một query `sum(rate(...))` có thể nhân đôi dù các time series có labels khác nhau?
5. Sender/receiver/default tracing dùng first matching để phòng vấn đề nào?
6. Sampling ảnh hưởng đến việc nhìn thấy duplicate spans ra sao?
7. Vì sao sửa lỗi bằng cách đổi tên metric có thể che vấn đề và làm dashboard sai semantics?
8. Trong một hệ thống có retry, phân biệt “lần thực thi” với “giao dịch nghiệp vụ logic” thế nào?

**Tiêu chí hoàn thành:** giải thích được các nguồn trùng instrumentation trong Spring Boot; thiết kế một owner đo cho mỗi boundary; phân biệt tín hiệu độc lập với observation trùng; phát hiện và sửa lỗi qua code, registry, metrics, traces; và giữ đúng tags/cardinality, context propagation, sampling.

## Ghi nhớ

- **Một boundary, một nguồn instrumentation chính.** Một observation có thể sinh nhiều tín hiệu qua các handler phù hợp; điều đó không phải double instrumentation.
- Spring Boot Actuator có thể đã instrument HTTP server/client và các tích hợp khác; kiểm tra trước khi bọc lại cùng đoạn code.
- Không ghép `@Observed` và manual `Observation` cho cùng method nếu chúng đo cùng semantics; tương tự, tránh đăng ký meter/tracing handler trùng.
- **All matching** phù hợp để phối hợp chức năng khác nhau; **first matching** phù hợp để chọn một tracing handler chuyên biệt theo context.
- Tìm lỗi bằng workload có kiểm soát, hiệu số Timer count, labels, trace waterfall và danh sách handler; luôn phân biệt retry thật với duplicate đo.
- Sau khi sửa, theo dõi lại dashboard/SLO và kiểm tra propagation, cardinality, exporter, sampling để các tín hiệu observability tiếp tục liên kết đúng.

## Tài liệu tham khảo

- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

