# Quan hệ giữa Observation, ObservationRegistry và ObservationHandler

Micrometer Observation cung cấp một mô hình chung để mô tả một đơn vị công việc cần quan sát, chẳng hạn xử lý HTTP request, gọi database, gửi message hoặc thực hiện một nghiệp vụ. Ba thành phần `Observation`, `ObservationRegistry` và `ObservationHandler` có vai trò khác nhau nhưng phối hợp trong cùng vòng đời: Observation đại diện cho một lần thực thi; Registry quản lý cấu hình và các handler; Handler nhận callback để chuyển thông tin của lần thực thi thành metrics, tracing hoặc hành động quan sát khác.

Hiểu đúng quan hệ này giúp ứng dụng instrument một lần nhưng có thể tạo nhiều loại tín hiệu. Code nghiệp vụ chỉ mô tả ranh giới công việc và context; các handler quyết định cách ghi nhận hoặc xuất dữ liệu.

## 1. Observation là một lần thực thi cần được quan sát

`Observation` đại diện cho một operation cụ thể trong ứng dụng. Mỗi lần xử lý một request hoặc một công việc có thể tạo một Observation riêng. Observation có tên, context và lifecycle.

Ví dụ các operation có thể được quan sát:

- Nhận và xử lý HTTP request.
- Tìm sản phẩm trong catalog.
- Thực hiện thanh toán.
- Gửi message tới broker.
- Đọc hoặc ghi dữ liệu trong database.
- Chạy một tác vụ nền.

Một Observation thường có các thông tin:

| Thành phần | Ý nghĩa |
|---|---|
| Name | Tên ổn định mô tả loại operation |
| Context | Trạng thái và dữ liệu gắn với lần thực thi |
| Low-cardinality key-values | Các chiều phân loại có tập giá trị nhỏ, phù hợp cho metrics |
| High-cardinality key-values | Dữ liệu chi tiết hơn, thường dành cho tracing |
| Error | Exception xảy ra trong operation nếu có |
| Scope | Khoảng thời gian Observation được đặt làm current observation trên thread |

Observation không phải là một Counter hay Timer cụ thể. Nó mô tả operation và lifecycle. Các handler có thể dùng cùng Observation để tạo Timer, span hoặc ghi nhận thông tin khác.

## 2. ObservationRegistry quản lý cấu hình và handler

`ObservationRegistry` là điểm điều phối trung tâm cho Observation. Registry lưu cấu hình như danh sách handler và các quy tắc quyết định Observation nào được tạo hoặc xử lý. Khi code tạo Observation với một registry, lifecycle của Observation sẽ được gửi tới các handler phù hợp đã đăng ký trong registry đó.

Tạo registry độc lập:

~~~java
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();
~~~

Đăng ký handler:

~~~java
registry.observationConfig()
    .observationHandler(new LoggingObservationHandler());
~~~

Sau đó tạo Observation gắn với registry:

~~~java
Observation.createNotStarted("catalog.lookup", registry)
    .observe(() -> catalogService.findProduct(productId));
~~~

Registry không phải backend lưu trữ metrics. Nó cũng không phải một MeterRegistry. Registry quản lý cơ chế quan sát và chuyển lifecycle tới handler; handler hoặc các thành phần tích hợp mới quyết định cách tạo meter, span hoặc tín hiệu khác.

Trong ứng dụng Spring Boot, thường dùng một ObservationRegistry được cấu hình ở cấp ứng dụng và inject vào các thành phần cần tạo Observation. Không tạo registry mới trong từng request vì registry mới sẽ không có đầy đủ handler, convention và cấu hình mà ứng dụng đã thiết lập.

## 3. ObservationHandler nhận callback trong lifecycle

`ObservationHandler` là thành phần phản ứng với các sự kiện trong vòng đời Observation. Một handler có thể ghi log, tạo metric, tạo span hoặc kết nối Observation với một hệ thống quan sát khác.

Các callback lifecycle phổ biến:

| Callback | Thời điểm | Mục đích thường gặp |
|---|---|---|
| onStart | Observation bắt đầu | Khởi tạo phép đo hoặc span |
| onScopeOpened | Scope được mở | Đưa context vào phạm vi hiện tại |
| onEvent | Một event được phát trong operation | Ghi nhận sự kiện phụ |
| onError | Operation gặp lỗi | Gắn exception hoặc trạng thái lỗi |
| onScopeClosed | Scope được đóng | Khôi phục context trước đó |
| onStop | Observation kết thúc | Hoàn tất Timer, span hoặc export |

Một handler khai báo loại context mà nó có thể xử lý thông qua `supportsContext`. Registry dùng thông tin đó để chọn handler phù hợp với từng Observation.

Ví dụ handler đơn giản:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public class LoggingObservationHandler
        implements ObservationHandler<Observation.Context> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        System.out.println("Observation started: " + context.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        System.out.println("Observation failed: " + context.getName());
    }

    @Override
    public void onStop(Observation.Context context) {
        System.out.println("Observation stopped: " + context.getName());
    }
}
~~~

Đây là ví dụ minh họa lifecycle. Trong production, nên dùng logger có cấu trúc và tránh ghi high-cardinality value hoặc dữ liệu nhạy cảm vào log.

Một handler có thể chỉ hỗ trợ một kiểu context chuyên biệt. Ví dụ handler cho HTTP server observation có thể kiểm tra context có phải HTTP server context hay không. Cách này giúp handler chỉ xử lý operation mà nó hiểu.

## 4. Quan hệ giữa ba thành phần trong một lần thực thi

Ba thành phần phối hợp theo trình tự:

1. Ứng dụng tạo Observation và cung cấp ObservationRegistry.
2. Observation nhận tên và context của operation.
3. Khi Observation bắt đầu, Registry chuyển callback tới các handler phù hợp.
4. Khi scope mở, Observation trở thành current observation trong phạm vi thực thi hiện tại.
5. Nếu có event hoặc lỗi, handler nhận callback tương ứng.
6. Khi scope đóng và Observation dừng, handler hoàn tất việc ghi nhận.

Sơ đồ:

~~~text
Application code
      |
      | createNotStarted(name, registry)
      v
 Observation
      |
      | start / observe
      v
ObservationRegistry
      |
      +-------------------------------+
      |               |               |
      v               v               v
 Handler A        Handler B        Handler C
 (metrics)        (tracing)         (logging)
      |               |               |
      v               v               v
 MeterRegistry    Tracer/backend    Log system
~~~

Ứng dụng chỉ cần mô tả operation một lần. Mỗi handler có thể chuyển cùng lifecycle thành tín hiệu riêng. Ví dụ một handler tạo Timer, handler khác tạo span, và handler khác ghi log khi operation thất bại.

Không nên nhầm Registry với Handler: Registry điều phối; Handler thực hiện phản ứng. Cũng không nên nhầm Observation với Registry: Observation là một lần thực thi; Registry tồn tại lâu hơn và phục vụ nhiều Observation.

## 5. Tạo và chạy Observation bằng observe()

Với operation đồng bộ, `observe()` là cách ngắn gọn để bao quanh công việc. API tự quản lý lifecycle cơ bản, bao gồm bắt đầu, mở scope, xử lý lỗi và dừng Observation.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ObservationRegistry observationRegistry;
    private final ProductRepository repository;

    public CatalogService(
            ObservationRegistry observationRegistry,
            ProductRepository repository) {
        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public Product findProduct(String productId) {
        return Observation.createNotStarted(
                "catalog.product.lookup",
                observationRegistry
            )
            .lowCardinalityKeyValue("operation", "lookup")
            .observe(() -> repository.findById(productId)
                .orElseThrow(ProductNotFoundException::new));
    }
}
~~~

Mỗi lần gọi `findProduct` tạo một Observation mới nhưng dùng chung registry. Tên metric/operation ổn định, còn context thuộc về lần gọi cụ thể.

`observe()` phù hợp khi toàn bộ operation có thể được biểu diễn bằng một lambda hoặc Runnable/Supplier. Khi cần điều khiển lifecycle thủ công, có thể dùng `start()`, `openScope()`, `error()` và `stop()`.

## 6. Context giữ dữ liệu của Observation

`Observation.Context` là nơi lưu dữ liệu gắn với một lần thực thi. Context có thể chứa error, key-values và các thuộc tính phục vụ handler. Một Observation có context riêng, nên không nên dùng context đó như một object trạng thái dùng chung giữa nhiều request.

Có thể bổ sung key-value:

~~~java
Observation observation = Observation.createNotStarted(
        "payment.authorize",
        observationRegistry
    )
    .lowCardinalityKeyValue("provider", "primary")
    .lowCardinalityKeyValue("payment_method", "card")
    .highCardinalityKeyValue("payment_reference", paymentReference);
~~~

Các key-value có ý nghĩa khác nhau:

- Low-cardinality key-values dành cho các giá trị nhỏ và ổn định, có thể dùng làm label metrics và thuộc tính tracing.
- High-cardinality key-values dành cho thông tin chi tiết hơn, thường chỉ phù hợp với tracing hoặc hệ thống có khả năng lưu trữ tương ứng.

Không đưa order ID, customer ID, request ID hoặc giá trị tự do vào low-cardinality key-value. Làm vậy có thể tạo hàng triệu time series. High-cardinality cũng không có nghĩa là được phép đưa dữ liệu nhạy cảm vào telemetry; cần cân nhắc privacy và quyền truy cập.

Tên operation nên ổn định, ví dụ payment.authorize. Không tạo tên Observation từ giá trị đầu vào như payment.authorize.12345.

## 7. Low-cardinality và high-cardinality được handler sử dụng thế nào?

Observation cung cấp hai nhóm key-value để các handler có thể chọn cách biểu diễn phù hợp.

| Loại | Ví dụ | Metrics | Tracing |
|---|---|---|---|
| Low cardinality | provider=primary | Phù hợp làm tag | Có thể gắn vào span |
| High cardinality | payment_reference=abc123 | Thường không đưa vào tag metrics | Có thể gắn vào span nếu chính sách cho phép |

Handler tạo metrics thường chỉ sử dụng low-cardinality values để tránh tăng số series. Handler tracing có thể hỗ trợ thêm high-cardinality values để giúp điều tra một request cụ thể.

Việc sử dụng cuối cùng phụ thuộc handler và backend. Không phải mọi handler đều phải đưa mọi key-value vào output. Hãy xem quy ước của handler đang dùng và xác minh dữ liệu thực tế được xuất.

## 8. Observation.Scope và current observation

Khi một Observation mở scope, nó trở thành current observation trong phạm vi thực thi hiện tại. Các thành phần bên dưới có thể lấy current observation để bổ sung context hoặc tạo Observation con có quan hệ với operation cha.

Ví dụ mở scope thủ công:

~~~java
Observation observation = Observation.start(
    "order.submit",
    observationRegistry
);

try (Observation.Scope scope = observation.openScope()) {
    orderService.submit(command);
} catch (RuntimeException error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
~~~

Scope được đóng khi thoát khỏi khối try. Sau đó stop() hoàn tất Observation. Nếu có exception, error() ghi nhận lỗi trước khi Observation dừng.

Khi Observation lồng nhau, scope giúp khôi phục current observation trước đó sau khi scope con đóng. Nhờ vậy, handler hoặc instrumentation phía dưới có thể xác định quan hệ cha-con trong luồng thực thi đồng bộ.

Không giữ một Scope trong field của singleton hoặc đóng scope trên một thread khác với thread đã mở nó. Scope gắn với context thực thi hiện tại và phải được đóng đúng vòng đời.

## 9. ObservationRegistry có thể lọc và tùy chỉnh Observation

`ObservationRegistry` có `observationConfig()` để đăng ký handler và các quy tắc cấu hình. Tùy phiên bản Micrometer, cấu hình có thể bao gồm:

- ObservationHandler: xử lý lifecycle.
- ObservationPredicate: quyết định Observation nào được phép tạo hoặc xử lý.
- ObservationConvention: chuẩn hóa tên và key-values theo loại operation.

Predicate hữu ích khi cần loại bỏ một nhóm Observation không cần thu thập. Convention hữu ích khi muốn áp dụng quy ước tên, contextual name và key-values nhất quán cho một loại operation.

Không nên dùng predicate để che giấu một lỗi instrumentation hoặc loại bỏ dữ liệu quan trọng mà không có lý do. Nếu filter Observation, hãy kiểm tra rằng metrics/tracing mong đợi vẫn được tạo.

Convention giúp tránh việc mỗi service tự đặt tên và tag theo cách khác nhau. Ví dụ tất cả operation xử lý đơn hàng có thể dùng cùng quy tắc đặt tên và tag channel, outcome. Hãy giữ danh sách giá trị tag hữu hạn.

## 10. Đăng ký nhiều ObservationHandler

Một registry có thể phục vụ nhiều handler. Mỗi handler kiểm tra context qua `supportsContext` và nhận các callback mà nó hỗ trợ.

Ví dụ đăng ký hai handler:

~~~java
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
    .observationHandler(new LoggingObservationHandler())
    .observationHandler(new AuditObservationHandler());
~~~

Một handler có thể tạo metrics, handler khác ghi log hoặc tạo trace. Cần tránh để nhiều handler cùng ghi một metric với cùng identity nếu điều đó làm số liệu bị nhân đôi.

Handler nên an toàn khi được gọi đồng thời từ nhiều thread. Không lưu state riêng của từng request trong field mutable của handler singleton. Dữ liệu thuộc từng operation nên đặt trong Observation.Context; handler chỉ đọc context và thực hiện hành động tương ứng.

Nếu handler cần giữ dữ liệu tạm trong một lifecycle, hãy lưu dữ liệu vào context hoặc cấu trúc gắn với context thay vì biến instance dùng chung. Điều này tránh việc hai Observation chạy đồng thời ghi đè trạng thái của nhau.

## 11. Tích hợp ObservationRegistry với Spring Boot

Trong Spring Boot có Actuator, ObservationRegistry thường được auto-configure và chia sẻ trong application context. Các thành phần có thể inject registry thay vì tự tạo registry mới.

Ví dụ custom handler là bean:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ObservationConfiguration {

    @Bean
    ObservationHandler<Observation.Context> loggingObservationHandler() {
        return new LoggingObservationHandler();
    }
}
~~~

Spring Boot có thể tự đăng ký các ObservationHandler bean vào registry được auto-configure theo cơ chế của phiên bản đang dùng. Hãy kiểm tra application context và cấu hình thực tế để tránh đăng ký cùng handler hai lần.

Một cấu hình dependency thường gặp:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Actuator/Micrometer cung cấp hạ tầng Observation và registry backend tương ứng. Nếu ứng dụng cần tracing, cần thêm bridge/exporter phù hợp với tracing stack và phiên bản Spring Boot; chỉ có Prometheus registry không tự tạo distributed trace.

Không khai báo ObservationRegistry mới trong từng service. Inject registry được cấu hình chung để mọi Observation đi qua cùng tập handler, convention và predicate.

## 12. Observation có thể tạo metrics và tracing từ cùng một operation

Observation là lớp trừu tượng chung. Handler quyết định tín hiệu nào được tạo.

Ví dụ với operation payment.authorize:

~~~text
Observation: payment.authorize
    |
    +--> Metrics handler
    |       |
    |       +--> Timer / count / histogram
    |
    +--> Tracing handler
    |       |
    |       +--> Span / attributes / error
    |
    +--> Logging handler
            |
            +--> Lifecycle event / error log
~~~

Metrics giúp trả lời câu hỏi tổng thể như tỷ lệ thanh toán lỗi hoặc latency p95. Tracing giúp theo dõi một request qua nhiều service. Log cung cấp sự kiện chi tiết và ngữ cảnh điều tra.

Một Observation có thể cấp dữ liệu cho nhiều tín hiệu nhưng các tín hiệu không thay thế nhau. Counter không chứa toàn bộ call tree; trace không phải sổ cái số lượng giao dịch; log không nên được dùng làm nguồn tính rate có cardinality không kiểm soát.

## 13. Xử lý lỗi và kết thúc Observation đúng cách

Khi operation gặp lỗi, hãy thông báo exception cho Observation trước khi dừng để handler có thể gắn trạng thái lỗi vào metric hoặc span.

Với `observe()`, lifecycle lỗi được quản lý tự động. Với lifecycle thủ công:

~~~java
Observation observation = Observation.start(
    "inventory.reserve",
    observationRegistry
);

try (Observation.Scope scope = observation.openScope()) {
    inventoryService.reserve(command);
} catch (RuntimeException error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
~~~

Một số nguyên tắc:

- Gọi error() khi operation thực sự thất bại.
- Gọi stop() đúng một lần cho mỗi Observation đã start.
- Đóng Scope trước khi kết thúc Observation.
- Không nuốt exception chỉ để metrics hiển thị thành công.
- Không gọi stop() khi Observation chưa được start.
- Dùng observe() nếu không cần tự quản lý lifecycle.

Handler onError không nhất thiết tự kết thúc Observation. Callback onStop vẫn cần được gọi để hoàn tất Timer hoặc span.

## 14. Context propagation khi chuyển thread hoặc dùng reactive

Observation.Scope thường gắn current observation với thread thực thi hiện tại. Nếu code mở scope rồi chuyển công việc sang Executor khác, thread mới không tự động có current observation chỉ vì nó được submit từ thread cũ.

Ví dụ dễ gây mất context:

~~~java
try (Observation.Scope scope = observation.openScope()) {
    executor.submit(() -> {
        // Không mặc định có current observation của thread submit.
        worker.process();
    });
}
~~~

Khi làm việc bất đồng bộ, hãy chọn một cơ chế truyền context phù hợp:

- Bắt đầu Observation bên trong worker nếu muốn đo riêng thời gian xử lý tại worker.
- Dùng Micrometer Context Propagation để capture và restore context khi chuyển executor.
- Với Reactor, dùng cơ chế tích hợp context propagation tương ứng phiên bản.
- Đóng scope trên đúng thread và đúng phạm vi đã mở.

Cần phân biệt thời gian chờ queue với thời gian worker thực thi. Nếu Observation bắt đầu trước khi submit và kết thúc khi future hoàn tất, nó bao gồm cả queue delay. Nếu bắt đầu bên trong worker, nó chỉ đo thời gian thực thi. Chọn ranh giới theo câu hỏi vận hành.

Không chia sẻ cùng một Scope object cho nhiều thread. Scope không phải một token tùy ý để lưu và đóng ở bất kỳ nơi nào.

## 15. Kiểm thử quan hệ Registry và Handler

Có thể tạo ObservationRegistry độc lập và đăng ký một handler ghi lại callback để kiểm tra lifecycle.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ObservationLifecycleTest {

    @Test
    void registryDispatchesLifecycleToMatchingHandler() {
        List<String> callbacks = new ArrayList<>();

        ObservationHandler<Observation.Context> handler =
            new ObservationHandler<>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onStart(Observation.Context context) {
                    callbacks.add("start");
                }

                @Override
                public void onScopeOpened(Observation.Context context) {
                    callbacks.add("scope-open");
                }

                @Override
                public void onScopeClosed(Observation.Context context) {
                    callbacks.add("scope-close");
                }

                @Override
                public void onStop(Observation.Context context) {
                    callbacks.add("stop");
                }
            };

        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(handler);

        Observation.createNotStarted("catalog.lookup", registry)
            .observe(() -> callbacks.add("work"));

        assertEquals(
            List.of("start", "scope-open", "work", "scope-close", "stop"),
            callbacks
        );
    }
}
~~~

Kiểm thử này minh họa cách Registry chuyển callback lifecycle tới handler phù hợp. Nếu phiên bản Micrometer đang dùng có handler bổ sung hoặc thay đổi chi tiết callback, hãy xác minh thứ tự thực tế theo API phiên bản đó.

Nên bổ sung test cho:

- Handler không hỗ trợ context sẽ không xử lý Observation đó.
- Nhiều handler phù hợp đều nhận callback theo cấu hình.
- onError được gọi khi operation ném exception.
- Scope được đóng khi operation kết thúc hoặc lỗi.
- Observation lồng nhau khôi phục current observation trước đó.
- Context propagation hoạt động khi chuyển executor hoặc Reactor.
- Low-cardinality values được đưa vào metrics theo quy ước; high-cardinality values không trở thành metric tag ngoài ý muốn.

## 16. Các lỗi thường gặp

- **Nhầm ObservationRegistry với MeterRegistry:** Registry quản lý Observation và handler, không phải nơi lưu meter backend.
- **Nghĩ ObservationHandler là một Observation:** Handler nhận callback; Observation là lần thực thi.
- **Tạo registry mới cho mỗi request:** các handler và cấu hình chung không được dùng lại.
- **Tạo Observation nhưng không start hoặc observe:** handler không nhận lifecycle đầy đủ.
- **Quên stop Observation thủ công:** Timer hoặc span có thể không được hoàn tất.
- **Không gọi error() khi có exception:** handler có thể không biết operation thất bại.
- **Đưa ID vào low-cardinality key-value:** cardinality metrics tăng không kiểm soát.
- **Cho rằng high-cardinality luôn an toàn:** dữ liệu chi tiết vẫn có thể nhạy cảm và tốn chi phí tracing.
- **Lưu trạng thái request trong field của handler singleton:** nhiều Observation đồng thời có thể ghi đè dữ liệu.
- **Giả định current observation tự truyền qua thread:** context có thể bị mất khi chuyển executor.
- **Đăng ký handler trùng:** cùng một operation có thể bị ghi nhận nhiều lần.
- **Dùng Observation thay cho business ledger:** metrics và tracing không thay thế dữ liệu giao dịch có thẩm quyền.

## 17. Checklist triển khai

- [ ] Xác định operation và đặt tên Observation ổn định.
- [ ] Dùng một ObservationRegistry được cấu hình chung trong ứng dụng.
- [ ] Đăng ký các ObservationHandler cần thiết.
- [ ] Kiểm tra supportsContext của từng handler.
- [ ] Dùng Observation.Context để lưu dữ liệu thuộc một lần thực thi.
- [ ] Chỉ đưa giá trị có cardinality thấp vào metrics.
- [ ] Dùng high-cardinality values có chọn lọc cho tracing và tuân thủ chính sách dữ liệu.
- [ ] Dùng observe() hoặc quản lý start/scope/error/stop đầy đủ.
- [ ] Đóng Scope đúng thread và đúng vòng đời.
- [ ] Cấu hình context propagation khi chuyển executor hoặc reactive pipeline.
- [ ] Tránh đăng ký handler trùng và tránh tạo registry theo request.
- [ ] Kiểm thử lifecycle, error, nested scope và async propagation.
- [ ] Xác minh metrics và traces được tạo đúng ở backend tương ứng.

Observation mô tả một lần thực thi; ObservationRegistry quản lý cách các lần thực thi được cấu hình và điều phối; ObservationHandler chuyển lifecycle cùng context thành tín hiệu quan sát cụ thể. Khi dùng chung registry, handler phù hợp và context có cardinality được kiểm soát, ứng dụng có thể instrument một operation một lần nhưng vẫn tạo được metrics, tracing và log nhất quán.

