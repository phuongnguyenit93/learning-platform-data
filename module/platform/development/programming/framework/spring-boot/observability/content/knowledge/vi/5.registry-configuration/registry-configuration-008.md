# Thứ tự xử lý handler trong cấu hình ObservationRegistry

> **Chương:** Cấu hình registry  
> **Bài:** Thứ tự xử lý handler  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao thứ tự handler quan trọng?

Một thao tác trong Spring Boot có thể được đo bằng **Micrometer Observation** một lần, rồi tạo ra nhiều tín hiệu: Timer trên metrics, span trên distributed tracing và log phục vụ điều tra. Mỗi chức năng thường gắn với một `ObservationHandler` khác nhau. Những handler này cùng nhận các thông báo vòng đời của một `Observation` thông qua `ObservationRegistry`.

Nếu không hiểu cách registry lựa chọn và phối hợp handler, ta dễ gặp các lỗi như:

- Metric có số đếm tăng hai lần vì cùng một chức năng đo được đăng ký trùng.
- Trace của HTTP client bị xử lý bằng handler tracing mặc định, làm mất logic propagation cho lời gọi ra ngoài.
- Handler ghi log được đặt ở vị trí ưu tiên cao trong nhóm **first matching**, khiến tracing handler phía sau không còn được chọn.
- Một handler mong đọc metadata do handler khác tạo ra tại `onStart` nhưng metadata đó chỉ được bổ sung ở `onStop`.
- Dashboard có metrics bình thường trong khi trace thiếu parent-child hoặc không xuất hiện, dẫn đến nhận định sai về nguyên nhân.

**Điểm cốt lõi:** “Thứ tự xử lý handler” gồm **thứ tự đăng ký**, **quy tắc chọn handler phù hợp**, **thứ tự các mốc vòng đời**, và **thời điểm dữ liệu sẵn sàng**. Đây là những vấn đề khác nhau, cần xét riêng.

Bài này hướng dẫn cách thiết kế và kiểm tra thứ tự đó ở mức Micrometer, rồi áp dụng vào ứng dụng Spring Boot có metrics, logs và tracing. Các chi tiết tự động cấu hình có thể khác theo phiên bản thư viện, nên luôn đối chiếu hành vi quan sát được và tài liệu của phiên bản đang chạy.

## 2. Bốn lớp thứ tự cần phân biệt

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Đăng ký** | Registry đang chứa những handler nào, được thêm bằng cơ chế gì? | Bean handler do Spring Boot tự đăng ký; handler thêm thủ công |
| **Lựa chọn** | Với một `Observation.Context`, handler nào đủ điều kiện nhận callback? | `supportsContext(context)`; composite `first matching` |
| **Vòng đời** | Sự kiện nào đã xảy ra trước/sau? | `start` → `openScope` → `event/error` → `closeScope` → `stop` trong một luồng điển hình |
| **Dữ liệu** | Tag, error và context đã sẵn sàng ở callback nào? | `channel` trước `start`; `outcome` sau thực thi nhưng trước `stop` |

Thứ tự khai báo handler **không tự quyết định** thứ tự diễn ra của `onStart`, `onError` hay `onStop`. Những callback này gắn với hành động trên `Observation`. Tương tự, thứ tự một handler được đăng ký không đảm bảo dữ liệu nó cần đã tồn tại khi callback đến.

Ví dụ, handler A và B đều hỗ trợ một context. Nếu code nghiệp vụ không gọi `observation.error(ex)`, không handler nào nhận `onError` chỉ vì chúng đã được đăng ký đúng thứ tự.

## 3. Registry điều phối ObservationHandler như thế nào?

Các thành phần chính:

- **`Observation`:** đơn vị công việc được quan sát; cung cấp API `start()`, `stop()`, `openScope()`, `event(...)`, `error(...)`.
- **`Observation.Context`:** chứa metadata, lỗi và dữ liệu theo một lần quan sát. Handler có thể đọc hoặc lưu trạng thái tạm ở đây.
- **`ObservationRegistry`:** lưu cấu hình observation, bao gồm các handler, predicate, filter và convention.
- **`ObservationHandler<T>`:** quyết định hỗ trợ context nào qua `supportsContext`, sau đó nhận các callback vòng đời tương ứng.
- **`ObservationHandler.AllMatchingCompositeObservationHandler`:** nhóm nhiều handler, cho phép tất cả handler con phù hợp được xử lý.
- **`ObservationHandler.FirstMatchingCompositeObservationHandler`:** chọn handler con phù hợp **đầu tiên** trong danh sách ưu tiên.

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ tạo Observation"] --> B{"Predicate cho phép?"}
    B -->|Không| C["No-op Observation"]
    B -->|Có| D["Observation + mutable Context"]
    D --> E["Lifecycle: start, scope, event, error, stop"]
    E --> F["Registry và các handler"]
    F --> G["All matching: các chức năng độc lập"]
    F --> H["First matching: một chiến lược phù hợp đầu tiên"]
    G --> I["Metrics, logging kỹ thuật"]
    H --> J["Sender / Receiver / Default tracing"]
    I --> K["MeterRegistry và exporter"]
    J --> L["Tracer, sampler và exporter"]
~~~

`ObservationPredicate` quyết định có nên tạo observation thực tế hay no-op. `ObservationFilter` có thể điều chỉnh context ở cuối vòng đời: tài liệu Micrometer mô tả filter được gọi **trước `onStop`** của các handler. Vì vậy một tag do filter bổ sung có thể xuất hiện trong xử lý `onStop` nhưng không mặc nhiên có ở `onStart`.

Một handler **không phải exporter**. Handler metrics thường tương tác với `MeterRegistry`; handler tracing tương tác với tracer. Các registry, reporter, sampler và exporter phía sau mới quyết định dữ liệu được tổng hợp, lấy mẫu hay chuyển tới Prometheus/OTLP và hệ thống quan sát.

## 4. Vòng đời tạo ra thứ tự callback

Một ví dụ instrument thủ công:

~~~java
Observation observation =
    Observation.createNotStarted("checkout.process", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    observation.event(Observation.Event.of("validated"));
    processCheckout();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Theo luồng trên:

1. `start()` kích hoạt callback `onStart` của handler phù hợp.
2. `openScope()` tạo scope hiện hành và kích hoạt callback scope mở.
3. `event(...)` kích hoạt `onEvent`.
4. `error(ex)` chỉ kích hoạt khi nhánh lỗi gọi API này; handler có thể đọc `context.getError()`.
5. `scope.close()` (do `try-with-resources`) kích hoạt callback scope đóng.
6. `stop()` kết thúc phép quan sát và kích hoạt xử lý stop, với các filter được thực hiện trước callback `onStop` theo luồng của Micrometer.

~~~mermaid
sequenceDiagram
    participant App as CheckoutService
    participant Obs as Observation
    participant Registry as ObservationRegistry
    participant Handler as Handler được chọn
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    App->>Obs: openScope()
    Obs->>Handler: onScopeOpened(context)
    App->>Obs: event(validated)
    Obs->>Handler: onEvent(event, context)
    alt có ngoại lệ và được báo
        App->>Obs: error(ex)
        Obs->>Handler: onError(context)
    end
    App->>Obs: scope.close()
    Obs->>Handler: onScopeClosed(context)
    App->>Obs: stop()
    Obs->>Registry: áp dụng ObservationFilter
    Registry-->>Obs: context đã cập nhật
    Obs->>Handler: onStop(context)
~~~

Đây là **thứ tự giữa các pha trong một cách gọi API cụ thể**, không phải cam kết rằng mọi observation đều có đúng một scope, một event, một error. Một observation có thể mở scope nhiều lần hoặc không mở scope nào; và thao tác bất đồng bộ có thể có các mốc bắt đầu/kết thúc khác luồng thực thi.

Cũng cần phân biệt **thứ tự callback của hai handler trong cùng pha** với thứ tự các pha. Nếu phải dựa vào việc handler B đọc một giá trị do handler A đặt ở cùng `onStart`, hãy xác minh chính xác cơ chế dispatch của phiên bản Micrometer đang dùng và viết kiểm tra hợp đồng. Thiết kế ổn định hơn là chuẩn bị metadata trước khi start hoặc đưa quy tắc vào convention/context chung.

## 5. AllMatchingCompositeObservationHandler: tất cả chức năng phù hợp

### 5.1. Ý nghĩa

Nhóm **all matching** phù hợp khi nhiều khả năng độc lập đều cần nhận cùng một observation: ví dụ một handler phân tích latency và một handler ghi sự kiện kỹ thuật.

Giả sử `handlerA.supportsContext(context)` và `handlerB.supportsContext(context)` đều trả `true`. Một `AllMatchingCompositeObservationHandler` chứa A và B cho phép **cả hai** tham gia các callback tương ứng. Nếu handler C trả `false`, C không được chọn.

~~~java
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig().observationHandler(
    new ObservationHandler.AllMatchingCompositeObservationHandler(
        handlerA,
        handlerB
    )
);
~~~

Trong đoạn này, `handlerA` và `handlerB` là **các instance đã tạo trước**, phải có kiểu phù hợp `ObservationHandler<?>`. Ví dụ chỉ minh họa cách ghép, không định nghĩa lại toàn bộ chúng.

Đặc điểm:

- Handler con nào phù hợp context sẽ được gọi; chọn một handler **không ngăn** handler độc lập khác cùng tham gia.
- Nếu hai handler cùng tạo Timer cho một observation, có thể sinh dữ liệu trùng hoặc tăng số phép đo quá mức. All matching **không tự chống trùng nhiệm vụ**.
- Tránh dựa vào side effect theo thứ tự giữa các handler. Nếu cần dữ liệu chung, tạo trong context hoặc convention trước pha liên quan.
- Handler callback nên gọn, chịu lỗi tốt và không gọi mạng đồng bộ trên đường xử lý request.

### 5.2. Khi không cần composite thủ công

Spring Boot Actuator tự đăng ký các bean `ObservationHandler` vào `ObservationRegistry` được cấu hình. Với các chức năng độc lập, có thể dùng handler bean thay vì tự tạo composite và chèn nó vào registry một lần nữa.

Không có lý do để đăng ký một handler vừa bằng `@Component` **vừa** gọi `registry.observationConfig().observationHandler(sameHandler)`. Cấu hình đôi có thể dẫn tới callback chạy trùng. Muốn thay thế cơ chế mặc định, cần rà soát những bean và auto-configuration hiện có trước khi thêm.

## 6. FirstMatchingCompositeObservationHandler: chọn chiến lược ưu tiên

### 6.1. Quy tắc then chốt

Nhóm **first matching** dùng khi có nhiều handler **thay thế nhau** và chỉ một handler được áp dụng với context cụ thể. Danh sách con có **thứ tự ưu tiên**: handler phù hợp đầu tiên được chọn; các handler phía sau không còn cơ hội xử lý trong nhóm đó.

Ví dụ tưởng tượng:

| Vị trí | Handler | `supportsContext` |
| --- | --- | --- |
| 1 | Handler chuyên cho client HTTP | `true` khi context là sender |
| 2 | Handler chuyên cho server HTTP | `true` khi context là receiver |
| 3 | Handler tracing mặc định | `true` với context thông thường |

Đối với observation sender, handler ở vị trí 1 được chọn. Với receiver, vị trí 1 không khớp nên handler 2 được chọn. Với context thông thường, hai handler chuyên biệt không khớp nên handler 3 xử lý.

Nếu đưa handler mặc định với điều kiện hỗ trợ rộng **lên vị trí đầu tiên**, nó có thể “che khuất” sender/receiver. Đây là lỗi cấu hình thứ tự phổ biến.

### 6.2. Ví dụ cấu hình tracing theo tài liệu Micrometer

~~~java
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingReceiverTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingSenderTracingObservationHandler;

// tracer và propagator được cấu hình theo tracing backend đang sử dụng.
void configureTracing(
        ObservationRegistry registry,
        Tracer tracer,
        Propagator propagator) {

    registry.observationConfig().observationHandler(
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
            new PropagatingSenderTracingObservationHandler<>(
                tracer, propagator),
            new PropagatingReceiverTracingObservationHandler<>(
                tracer, propagator),
            new DefaultTracingObservationHandler(tracer)
        )
    );
}
~~~

Đoạn này dùng cho trường hợp **tự cấu hình registry**, ví dụ ứng dụng Micrometer độc lập, và minh họa chính xác ý tưởng ưu tiên. Trong Spring Boot đã bật tracing auto-configuration, không tự đăng ký thêm toàn bộ nhóm trên nếu framework đã làm công việc đó: có thể tạo span đôi hoặc xung đột propagation.

Lý do sắp xếp sender → receiver → default:

- **Sender** cần truyền trace context vào lời gọi đi ra ngoài (HTTP client, message producer).
- **Receiver** cần nhận trace context từ yêu cầu hoặc thông điệp đi vào.
- **Default** là fallback cho các observation không mang ngữ cảnh sender/receiver.

Tùy theo framework, chính instrumenter sẽ tạo context thích hợp. Chỉ đổi vị trí handler không tạo ra sender/receiver context, cũng không tự bật propagation. Cần đồng thời có tracer, propagator và instrumentation tương ứng.

## 7. Phối hợp metrics và tracing: một hay nhiều composite?

**Mục tiêu** là để một observation nghiệp vụ tạo được Timer và span, nhưng tránh chọn hai handler cùng thực hiện công việc tracing cho một context.

Một mô hình cấu hình Micrometer độc lập:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingReceiverTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingSenderTracingObservationHandler;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
    // Meter độc lập với lựa chọn loại span.
    .observationHandler(new DefaultMeterObservationHandler(meterRegistry))
    // Nhóm tracing chỉ chọn handler phù hợp đầu tiên.
    .observationHandler(
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
            new PropagatingSenderTracingObservationHandler<>(
                tracer, propagator),
            new PropagatingReceiverTracingObservationHandler<>(
                tracer, propagator),
            new DefaultTracingObservationHandler(tracer)
        )
    );
~~~

Trong snippet này, `meterRegistry`, `tracer` và `propagator` là biến đã được tạo/cấu hình; dependency cụ thể phụ thuộc Micrometer và tracing bridge đang dùng.

~~~mermaid
flowchart LR
    A["Observation trên registry"] --> B["Meter handler"]
    A --> C["FirstMatching tracing"]
    C --> D{"Loại context?"}
    D -->|Sender| E["PropagatingSender"]
    D -->|Receiver| F["PropagatingReceiver"]
    D -->|Khác| G["DefaultTracing"]
    B --> H["Timer + low-cardinality tags"]
    E --> I["Span + inject context"]
    F --> J["Span + extract context"]
    G --> K["Span thông thường"]
~~~

Đừng gộp meter handler với tracing handler vào **cùng nhóm first matching** nếu muốn **cả metrics lẫn tracing**. Khi handler đầu tiên khớp, handler tiếp theo sẽ bị loại khỏi nhóm, làm mất một tín hiệu.

Ngược lại, đừng đưa sender, receiver và default tracing vào một nhóm **all matching** nếu các điều kiện hỗ trợ chồng nhau. Rủi ro là nhiều handler cùng thao tác span/context. Cách phối hợp an toàn thường là **meter độc lập**, còn **tracing là một nhóm first matching**.

### Trường hợp exemplars

Một số hệ thống muốn gắn mẫu metric với trace (*exemplar*). Micrometer Tracing có `TracingAwareMeterObservationHandler` kết hợp meter handler với tracer khi pipeline hỗ trợ. Khi dùng dạng này, **thay thế** meter handler thuần tương ứng, không đăng ký đồng thời hai handler cùng ghi cùng meter. Khả năng xuất exemplar còn phụ thuộc registry, exporter và backend; thứ tự handler không tự bật exemplar.

## 8. Đăng ký handler trong Spring Boot: cơ chế và phạm vi trách nhiệm

Spring Boot tích hợp Micrometer Observation thông qua Actuator. Khi cấu hình tương ứng có hiệu lực, Spring Boot tự đăng ký các bean thuộc những loại:

- `ObservationHandler`;
- `ObservationPredicate`;
- `ObservationFilter`;
- `GlobalObservationConvention`.

Ngoài ra, ứng dụng có thể cung cấp `ObservationRegistryCustomizer` để tùy chỉnh registry ở giai đoạn cấu hình. Vì vậy cần phân biệt **cấu hình tự động qua Spring** với **đăng ký handler thủ công trong Java độc lập**.

### 8.1. Cách thông thường: định nghĩa custom handler bean

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CheckoutAuditHandler
        implements ObservationHandler<Observation.Context> {

    private static final Logger log =
        LoggerFactory.getLogger(CheckoutAuditHandler.class);

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "checkout.process".equals(context.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        Throwable error = context.getError();
        log.warn("Checkout observation failed: type={}",
            error == null ? "unknown" :
                error.getClass().getSimpleName());
    }

    @Override
    public void onStop(Observation.Context context) {
        log.debug("Checkout observation stopped");
    }
}
~~~

Bean trên có nhiệm vụ **phản ứng với lỗi và thời điểm kết thúc** của observation có tên `checkout.process`. Nó không tự tạo Timer hoặc span thứ hai. Hạn chế log dữ liệu nhạy cảm và tránh truy cập network trực tiếp trong callback.

Code nghiệp vụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void checkout(ObservationRegistry registry) {
    Observation.createNotStarted("checkout.process", registry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> {
            // Thực thi checkout đồng bộ.
            performCheckout();
        });
}
~~~

Phương thức `observe(...)` bọc vòng đời phổ biến, phù hợp với thao tác đồng bộ. Nếu cần tự mở scope, gửi event hoặc xử lý kết quả bất đồng bộ, nên quản lý lifecycle một cách tường minh.

### 8.2. Có nên dùng `@Order` để “sửa” thứ tự?

Các bean của Spring có thể được sắp xếp bởi nhiều cơ chế của framework. Tuy nhiên, **đừng coi chỉ thêm một `@Order` là bảo đảm mọi handler sẽ được thực thi theo ý định**, đặc biệt khi có composite của tracing, auto-configuration và các handler hỗ trợ context khác nhau.

Cách thực tế:

1. Xác nhận handler đang có trong cấu hình registry sau khi Spring Boot khởi tạo.
2. Phân biệt trường hợp cần **chọn đúng một** handler (dùng first matching) với trường hợp cần **nhiều chức năng** (meter + tracing + handler riêng).
3. Nếu ưu tiên là một phần thiết yếu của logic, thiết kế nhóm composite rõ ràng và **kiểm chứng** trên phiên bản đã chọn.
4. Không đăng ký trùng bean handler trong customizer hoặc trong code khởi tạo.

Cần thận trọng khi tự sửa nhóm handler tracing mặc định trong Spring Boot, vì sự thay đổi đó có thể ảnh hưởng inject/extract context của HTTP client, server và messaging.

## 9. Thứ tự giữa convention, predicate, filter và handler

Không phải mọi thành phần có chữ “observation” đều là handler. Chúng tham gia những giai đoạn khác nhau:

| Thành phần | Vai trò | Quan hệ thứ tự |
| --- | --- | --- |
| `ObservationPredicate` | Cho phép hoặc chặn tạo observation thực | Quyết định observation có được theo dõi, trước khi các callback vòng đời hữu ích xuất hiện |
| `ObservationConvention` | Định nghĩa tên, contextual name và key-values | Nên cung cấp metadata có thể xác định từ trước để handler nhìn thấy phù hợp |
| `ObservationHandler.onStart` | Xử lý khi observation bắt đầu | Một số handler phải có tags ở thời điểm này |
| `ObservationFilter` | Chỉnh sửa context khi observation hoàn tất | Micrometer áp dụng filter trước `onStop` của handler |
| `ObservationHandler.onStop` | Hoàn tất Timer/span hoặc nhiệm vụ tương ứng | Có thể đọc metadata bổ sung trước stop |

Ví dụ:

~~~java
Observation observation = Observation.createNotStarted(
        "checkout.process", registry)
    .lowCardinalityKeyValue("channel", "web")
    .start();

try {
    doBusinessWork();
    observation.lowCardinalityKeyValue("outcome", "success");
} catch (RuntimeException ex) {
    observation.lowCardinalityKeyValue("outcome", "error");
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

`channel` biết từ đầu, nên được gắn trước `start()`; `outcome` chỉ được gắn khi đã biết kết quả nhưng trước `stop()`. Timer ghi duration khi stop có thể dùng outcome cuối cùng, song **LongTaskTimer đang hoạt động** hoặc handler đọc tags tại start có thể chỉ thấy những tag đã có ở thời điểm bắt đầu.

Không nên khiến một handler chỉ hoạt động đúng khi handler khác “vừa kịp” bổ sung key. Với dữ liệu chung cần thiết từ sớm, đưa vào context/convention trước pha xử lý. Với dữ liệu cuối cùng, dùng filter hoặc API nghiệp vụ trước stop.

## 10. Quy tắc `supportsContext`: ổn định và chính xác

`supportsContext(Observation.Context)` giúp handler chọn đúng loại observation. Một implementation tốt thường xét **loại context** hoặc một điều kiện ổn định theo vòng đời.

Ví dụ:

~~~java
final class CheckoutContext extends Observation.Context {
    // Các field có ý nghĩa cho instrumentation checkout.
}

final class CheckoutContextHandler
        implements ObservationHandler<CheckoutContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public void onStart(CheckoutContext context) {
        // Xử lý khi bắt đầu checkout.
    }

    @Override
    public void onStop(CheckoutContext context) {
        // Hoàn tất xử lý tương ứng.
    }
}
~~~

Trong pipeline có `FirstMatchingCompositeObservationHandler`, thứ tự các điều kiện càng quan trọng:

- Handler **chuyên biệt** đặt trước handler hỗ trợ rộng.
- Handler **fallback** đặt cuối.
- Tránh điều kiện thay đổi theo `outcome` hoặc metadata chỉ xuất hiện sau `onStart`; các callback của cùng observation có nguy cơ được lựa chọn không nhất quán nếu điều kiện hỗ trợ được đánh giá lại.
- Không viết một handler với `supportsContext(...) == true` đứng đầu first matching nếu muốn handler chuyên biệt phía sau nhận context.

**Quy tắc thiết kế:** điều kiện hỗ trợ mô tả **loại công việc**, còn result/outcome là **metadata của công việc**. Không nên biến result thành bộ chọn handler khi vẫn có thể giải quyết bằng tags hoặc logic nhẹ trong callback.

## 11. Thực hành có thể kiểm chứng: ghi lại thứ tự callback

Khi một bug phụ thuộc thứ tự, cách đáng tin cậy là dựng registry nhỏ trong bộ nhớ và ghi lại **các callback thực tế** trên phiên bản Micrometer hiện có. Cách này không cần exporter hoặc tracing backend.

### 11.1. Handler ghi dấu sự kiện

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import java.util.List;

final class RecordingHandler
        implements ObservationHandler<Observation.Context> {

    private final String id;
    private final List<String> calls;

    RecordingHandler(String id, List<String> calls) {
        this.id = id;
        this.calls = calls;
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "demo.work".equals(context.getName());
    }

    @Override
    public void onStart(Observation.Context context) {
        calls.add(id + ":start");
    }

    @Override
    public void onScopeOpened(Observation.Context context) {
        calls.add(id + ":scope-opened");
    }

    @Override
    public void onEvent(
            Observation.Event event, Observation.Context context) {
        calls.add(id + ":event:" + event.getName());
    }

    @Override
    public void onError(Observation.Context context) {
        calls.add(id + ":error");
    }

    @Override
    public void onScopeClosed(Observation.Context context) {
        calls.add(id + ":scope-closed");
    }

    @Override
    public void onStop(Observation.Context context) {
        calls.add(id + ":stop");
    }
}
~~~

### 11.2. Tạo registry và thực thi

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.ArrayList;
import java.util.List;

List<String> calls = new ArrayList<>();
ObservationRegistry registry = ObservationRegistry.create();

RecordingHandler first = new RecordingHandler("A", calls);
RecordingHandler second = new RecordingHandler("B", calls);

registry.observationConfig().observationHandler(
    new ObservationHandler.AllMatchingCompositeObservationHandler(
        first, second
    )
);

Observation observation =
    Observation.createNotStarted("demo.work", registry).start();

try (Observation.Scope scope = observation.openScope()) {
    observation.event(Observation.Event.of("validated"));
} finally {
    observation.stop();
}

calls.forEach(System.out::println);
~~~

**Cách đọc kết quả:**

- Có callback của **cả A và B** ở những pha phù hợp là đặc trưng quan trọng của nhóm all matching.
- Các pha `start`, `scope-opened`, `event`, `scope-closed` và `stop` phải xuất hiện tương ứng với API đã gọi.
- Đọc **trật tự in ra thực tế** để hiểu dispatch của đúng phiên bản đang dùng. Không viết business logic dựa trên một chuỗi log giả định từ phiên bản khác.
- Đổi composite thành `FirstMatchingCompositeObservationHandler(first, second)`. Vì A và B cùng hỗ trợ tên observation, chỉ A được ưu tiên. Tiếp theo cho A trả `false` để kiểm chứng B nhận callback.
- Nếu muốn kiểm tra lỗi, đưa `observation.error(new IllegalStateException("demo"))` vào giữa pha scope và stop; khi đó các handler được chọn phải nhận `onError`.

Đây là một **thí nghiệm học tập**. Trong ứng dụng Spring Boot thật, registry được framework cấu hình và có thêm các handler. Kết quả ở registry độc lập chỉ xác nhận cách hành xử của Micrometer trong ví dụ, không tự xác nhận auto-configuration của ứng dụng production.

### 11.3. Điều cần quan sát khi viết kiểm thử tự động

Nếu cần bảo vệ một cấu hình phụ thuộc thứ tự, kiểm thử có giá trị nhất là:

1. Context sender chọn handler sender, context receiver chọn handler receiver; handler mặc định không “cướp” hai trường hợp này.
2. Một observation tạo đúng **một** kết quả đo meter và đúng số span kỳ vọng trong một tracing test phù hợp.
3. Callback start/stop được ghép cặp, scope được đóng; nhánh lỗi vẫn hoàn tất observation.
4. Đăng ký custom handler không tạo thêm callback trùng của cùng một instance.
5. Khi thêm metadata muộn, xác minh handler nào đọc được ở `onStop` và handler nào cần giá trị từ `onStart`.

Các kiểm tra này phát hiện sai **hành vi**, thay vì cố định một danh sách thứ tự nội bộ không được ứng dụng thực sự sử dụng.

## 12. Điều tra các lỗi theo thứ tự handler

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Metrics có nhưng tracing biến mất sau khi thêm handler | Đưa meter/tracing vào first matching cùng nhóm; một handler chặn handler còn lại | Xem cấu hình composite; tách chức năng độc lập khỏi nhóm chọn một |
| Có span nhưng thiếu trace propagation khi gọi downstream | Default tracing đứng trước sender/receiver trong first matching, hoặc thiếu propagator | Kiểm tra ưu tiên chuyên biệt → mặc định, instrumenter và propagator |
| Thấy hai span trùng cho một request | Đăng ký tracing handler trùng hoặc nhiều handler cùng tạo span | Rà soát bean, registry customizer và nhóm composite |
| Counter/Timer tăng quá số yêu cầu | Hai meter handler cùng xử lý một observation, hoặc instrumentation tạo hai observation chồng nhau | Kiểm tra registry, annotation và instrumentation mặc định |
| Handler tự viết không chạy | `supportsContext` trả false, bean chưa được đăng ký hoặc observation bị predicate chặn | Đọc điều kiện hỗ trợ, tên/context và cấu hình registry |
| Handler đầu tiên có callback, handler sau không có | Cả hai nằm trong first matching, handler đầu hỗ trợ quá rộng | Dùng all matching cho chức năng độc lập hoặc sắp xếp lại trường hợp chuyên biệt |
| Không thấy `outcome` trong handler tại start | Tag kết quả chỉ gắn sau khi nghiệp vụ hoàn tất | Đọc tag tại stop; chỉ gắn giá trị biết trước tại start |
| Scope hiện hành bị sai khi xử lý async | Context chưa được propagate giữa thread/reactive chain | Dùng cơ chế propagation của Spring/Reactor phù hợp, giữ scope cân bằng |
| Traces ít hơn số Timer | Tracing có sampler; metrics được tổng hợp riêng | Kiểm tra sampler/exporter; không suy request count từ trace count |
| Latency dashboard cao bất thường khi thêm handler | Callback làm I/O đồng bộ, logging nặng hoặc nhiều lớp đo trùng | Đo overhead handler; giảm công việc trong callback |

### Phương pháp khoanh vùng

Khi thấy một trong các triệu chứng trên, hãy lần lượt:

1. Xác định **observation name, context type** và xem thao tác thật sự có `start()/stop()` đúng hay không.
2. Liệt kê các handler được cấu hình, đặc biệt có sự trùng giữa auto-configuration và manual registration.
3. Kiểm tra `supportsContext` của nhóm liên quan và vị trí trong `FirstMatchingCompositeObservationHandler`.
4. Xác nhận callback tương ứng bằng logging kỹ thuật có giới hạn hoặc thí nghiệm registry tối giản.
5. Kiểm tra tín hiệu cuối: Timer tags/`_count` trên metrics, trace/span và propagation trên tracing, trace ID trong logs khi được bật.
6. Nếu metrics/traces còn thiếu, xét registry/exporter/sampler, vì handler đã chạy chưa chắc dữ liệu đã tới backend.

## 13. Trường hợp thực tế: HTTP request qua hai dịch vụ

Giả sử dịch vụ `order-api` gọi `inventory-api`. Sau triển khai, dashboard vẫn có latency của HTTP server nhưng trace của request chỉ hiển thị span ở `order-api` và không nối sang `inventory-api`.

Quy trình phân tích theo chủ đề bài học:

- **Bước 1 — kiểm tra sender/receiver:** xác định instrumentation HTTP client của `order-api` có tạo sender context và server của `inventory-api` có tạo receiver context không.
- **Bước 2 — kiểm tra first matching:** nếu nhóm tracing đặt fallback mặc định trước handler sender/receiver, handler mặc định có thể được chọn quá sớm; sửa ưu tiên nhóm và xác nhận lại.
- **Bước 3 — kiểm tra propagation:** bảo đảm tracer/propagator tương thích, header trace được inject ở client và extract ở server. Thứ tự đúng không thay thế cấu hình propagation.
- **Bước 4 — kiểm tra scope:** request context có đi qua executor hoặc reactive chain không; nếu chuyển thread, cần cơ chế context propagation tương ứng.
- **Bước 5 — kiểm tra sampling/exporter:** một trace bị sampling hoặc exporter lỗi cũng khiến backend không thấy span, dù handler chạy đúng.
- **Bước 6 — đối chiếu metrics:** xem lỗi, p95 latency, RPS để biết sự cố ảnh hưởng toàn hệ thống hay chỉ một số request; dùng logs với trace ID để truy dấu cụ thể.

Sự khác biệt giữa bốn trụ quan sát lúc này rõ ràng: **metrics** chỉ ra xu hướng, **traces** cho thấy cấu trúc đường đi, **logs** cho biết sự kiện, còn **registry và thứ tự handler** quyết định việc instrument được chuyển thành các tín hiệu đó như thế nào.

## 14. Bài tập thực hành và câu hỏi kiểm tra

Một ứng dụng có ba handler:

- `MetricHandler` hỗ trợ mọi `Observation.Context`.
- `SenderTracingHandler` chỉ hỗ trợ sender context.
- `DefaultTracingHandler` hỗ trợ context thông thường.

**Bài tập A — chọn cấu hình:**

1. Nếu đưa cả ba vào first matching với `MetricHandler` đầu tiên, điều gì xảy ra với tracing?
2. Nếu đưa sender và default vào all matching, rủi ro nào xuất hiện khi cả hai cùng hỗ trợ sender context?
3. Hãy thiết kế registry sao cho metrics luôn được ghi, còn tracing chọn sender khi phù hợp và fallback default khi không phù hợp.

**Bài tập B — kiểm tra thứ tự:**

Dùng `RecordingHandler` ở phần 11 và so sánh all matching với first matching trên cùng `demo.work`. Ghi nhận số callback cho A và B. Thử đổi thứ tự hai handler để giải thích thứ tự ưu tiên của first matching. Sau đó thêm handler C có `supportsContext == false` để kiểm chứng C không nhận callback.

**Bài tập C — vòng đời và metadata:**

Tạo `Observation` với `channel=web` trước `start`, rồi ghi `outcome=error` và `observation.error(ex)` sau khi exception xảy ra, trước `stop`. Tự giải thích vì sao handler đo ở start có thể không thấy outcome, còn handler đo ở stop có thể đọc được.

**Câu hỏi tự kiểm tra:**

1. Registry có 5 handler nhưng chỉ 2 handler hỗ trợ context; “đăng ký 5” có đồng nghĩa “5 callback hữu ích” không?
2. Sự khác nhau giữa thứ tự callback theo lifecycle và thứ tự ưu tiên của first matching là gì?
3. Vì sao một handler `supportsContext == true` đặt đầu first matching có thể làm mất tracing cho sender?
4. Khi có hai meter handler cùng tạo Timer, kết quả dashboard có thể bị ảnh hưởng thế nào?
5. `ObservationFilter` được áp dụng trước callback nào trong stop flow? Vì sao thời điểm này quan trọng?
6. Tại sao một trace bị sampling không chứng minh handler tracing không chạy?
7. Vì sao nên kiểm tra integration của Spring Boot khi đã có auto-configuration, thay vì chỉ chạy ví dụ `ObservationRegistry.create()` độc lập?

**Tiêu chí hoàn thành:** phân biệt được bốn lớp thứ tự; chọn đúng all matching/first matching; giải thích thứ tự sender–receiver–default tracing; instrument vòng đời đầy đủ; tránh đăng ký trùng; biết kiểm tra metrics, traces, logs và context propagation trên cấu hình thực.

## Ghi nhớ

- `ObservationRegistry` giữ handler; `supportsContext` chọn handler phù hợp; lifecycle quyết định callback nào được kích hoạt.
- **All matching** cho các chức năng độc lập cùng quan sát; **first matching** cho những chiến lược thay thế nhau theo ưu tiên. Trong first matching, đặt handler chuyên biệt trước handler fallback.
- Ghép **meter handler** riêng và **first matching tracing handler** là mô hình phổ biến; đừng để một chức năng “nuốt” chức năng kia.
- Spring Boot tự đăng ký `ObservationHandler` bean. Tránh lặp lại registration thủ công khi đã có auto-configuration.
- `ObservationFilter` chạy trước `onStop`; metadata có sớm hay muộn ảnh hưởng khả năng đọc của từng handler. Giữ `supportsContext` ổn định theo vòng đời.
- Thứ tự handler chỉ là một phần của observability: còn phải kiểm soát tag cardinality, sampling, exporter và propagation để điều tra độ trễ và lỗi chính xác.

## Tài liệu tham khảo

- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Reference — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

