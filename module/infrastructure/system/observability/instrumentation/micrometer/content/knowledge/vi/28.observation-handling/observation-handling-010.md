# Kiểm soát lỗi trong handler để giữ hoạt động nghiệp vụ ổn định

Micrometer Observation gọi các `ObservationHandler` đồng bộ theo vòng đời của Observation. Handler có thể tạo Timer, span, ghi log, thêm dữ liệu vào context hoặc quản lý scope. Vì callback handler chạy ngay trong luồng gọi `Observation`, một exception không được xử lý bên trong handler có thể thoát ra ngoài và làm gián đoạn code đang được đo.

Ví dụ, nếu `onStart` ném exception, phần nghiệp vụ có thể chưa được gọi. Nếu `onError` ném exception, lỗi telemetry có thể che khuất lỗi nghiệp vụ ban đầu. Nếu `onScopeClosed` ném exception, việc khôi phục scope trước đó có thể không chạy. Với những handler chỉ phục vụ quan sát, nên áp dụng chính sách fail-open: ghi nhận lỗi của handler, bỏ qua lỗi telemetry đó và cho phép vòng đời Observation tiếp tục.

Fail-open không có nghĩa là bỏ qua mọi lỗi trong ứng dụng. Nó chỉ phù hợp với các callback quan sát tùy chọn, nơi việc ghi metrics, tracing hoặc logging không được phép thay đổi kết quả nghiệp vụ. Các lỗi nghiêm trọng của JVM vẫn cần được để lan truyền.

## 1. Handler tham gia vào những thời điểm nào?

Một Observation có context và có thể được nhiều handler hỗ trợ. Khi lifecycle thay đổi, Micrometer gọi callback tương ứng:

| Callback | Thời điểm | Công việc thường gặp |
|---|---|---|
| `supportsContext` | Khi xác định handler có nhận context này không | Kiểm tra kiểu context |
| `onStart` | Observation bắt đầu | Tạo span, bắt đầu Timer hoặc LongTaskTimer |
| `onScopeOpened` | Scope được mở | Đưa tracing context vào ThreadLocal |
| `onError` | Code được quan sát báo lỗi | Gắn lỗi vào span hoặc cập nhật trạng thái |
| `onEvent` | Observation phát event | Thêm event vào span hoặc ghi sự kiện |
| `onScopeClosed` | Scope đóng | Khôi phục ThreadLocal hoặc đóng tài nguyên |
| `onStop` | Observation kết thúc | Dừng Timer, kết thúc span, phát dữ liệu |

Các handler được đăng ký qua `ObservationRegistry`. Một Observation chỉ gọi những handler có `supportsContext(context)` trả về `true`.

~~~java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationHandler(new MetricsHandler())
        .observationHandler(new AuditHandler())
        .observationHandler(new TracingHandler());
~~~

Một handler có thể hỗ trợ mọi context hoặc chỉ một loại context cụ thể. Nên kiểm tra context bằng `instanceof` hoặc marker interface phù hợp, thay vì nhận tất cả rồi mới phát hiện sai loại trong callback.

## 2. Vì sao lỗi handler có thể ảnh hưởng code nghiệp vụ?

Trong implementation `SimpleObservation`, các callback được gọi trực tiếp trong vòng lặp handler. Việc dispatch không tự động bắt exception riêng cho từng handler. Do đó, exception có thể thoát ra khỏi lifecycle method và dừng các callback còn lại.

Điều này tạo ra các rủi ro cụ thể:

| Vị trí lỗi | Hậu quả có thể xảy ra |
|---|---|
| `supportsContext` | Việc tạo Observation thất bại trước khi nghiệp vụ chạy |
| `onStart` | `Observation.start()` thất bại; code được đo có thể không được gọi |
| `onScopeOpened` | Scope đã được đặt làm current nhưng callback thất bại trước khi caller nhận Scope |
| `onError` | Exception của handler có thể thay thế exception nghiệp vụ đang được ném lại |
| `onEvent` | Event không được xử lý và các handler sau có thể không được gọi |
| `onScopeClosed` | Các callback đóng scope còn lại có thể bị bỏ qua; registry có thể chưa khôi phục scope trước đó |
| `onStop` | Kết quả thành công hoặc exception gốc có thể bị thay bằng lỗi khi dừng Observation |

Đặc biệt, `Observation.observe(...)` gọi `start()` trước khối `try`, sau đó chạy nghiệp vụ, gọi `error(error)` nếu nghiệp vụ thất bại và cuối cùng gọi `stop()`. Vì vậy:

- Lỗi ở `onStart` xảy ra trước khi khối nghiệp vụ được thực thi.
- Lỗi ở `onError` có thể ngăn việc ném lại exception gốc.
- Lỗi ở `onStop` xảy ra trong `finally` và có thể che kết quả hoặc exception trước đó.

Đây là lý do handler tùy chọn cần có ranh giới lỗi riêng nếu ứng dụng yêu cầu telemetry không ảnh hưởng tính ổn định của nghiệp vụ.

## 3. Phân biệt lỗi nghiệp vụ và lỗi telemetry

Hai nhóm lỗi có ý nghĩa khác nhau:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Lỗi nghiệp vụ | Không đủ tồn kho, dữ liệu không hợp lệ, dependency trả lỗi | Ghi vào Observation bằng `observation.error(error)`, sau đó giữ hợp đồng exception của service |
| Lỗi handler | Exporter lỗi, logger hỏng, callback truy cập context sai, client tracing ném exception | Ghi nhận riêng, cô lập callback nếu handler chỉ phục vụ quan sát |

Không chuyển lỗi handler thành lỗi của Observation đang đo. Nếu một handler ném `IllegalStateException` vì không kết nối được backend tracing, không nên gắn exception đó vào span như thể thao tác thanh toán thất bại.

Tách riêng hai loại lỗi giúp dashboard và trace phản ánh đúng trạng thái nghiệp vụ. Lỗi telemetry cần có log hoặc metric chẩn đoán riêng, còn lỗi nghiệp vụ vẫn được truyền đến caller theo hợp đồng của service.

## 4. Quy tắc fail-open cho handler tùy chọn

Một wrapper fail-open thực hiện bốn việc:

1. Chuyển tiếp từng callback đến handler gốc.
2. Bắt `RuntimeException` phát sinh từ callback đó.
3. Ghi log với tên handler và callback để có thể điều tra.
4. Kết thúc callback wrapper bình thường để các handler khác và code nghiệp vụ tiếp tục.

Không nên bắt mọi `Throwable`. Những lỗi như `OutOfMemoryError`, `StackOverflowError`, `LinkageError` hoặc `ThreadDeath` biểu thị tình trạng nghiêm trọng của JVM; nuốt chúng có thể khiến tiến trình tiếp tục trong trạng thái không an toàn.

## 5. Xây dựng SafeObservationHandler

Ví dụ dưới đây bọc một handler bất kỳ. Wrapper xử lý cả `supportsContext` và các callback lifecycle:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

import java.util.logging.Level;
import java.util.logging.Logger;

final class SafeObservationHandler<T extends Observation.Context>
        implements ObservationHandler<T> {

    private static final Logger LOGGER =
            Logger.getLogger(SafeObservationHandler.class.getName());

    private final ObservationHandler<T> delegate;

    SafeObservationHandler(ObservationHandler<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        try {
            return delegate.supportsContext(context);
        } catch (RuntimeException error) {
            report("supportsContext", error);
            return false;
        }
    }

    private void invoke(String callback, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException error) {
            report(callback, error);
        }
    }

    private void report(String callback, RuntimeException error) {
        try {
            LOGGER.log(
                    Level.WARNING,
                    "Observation handler {0} failed in {1} with {2}",
                    new Object[] {
                            delegate.getClass().getName(),
                            callback,
                            error.getClass().getName()
                    }
            );
            LOGGER.log(Level.FINE, "Observation handler failure details", error);
        } catch (RuntimeException ignored) {
            // Việc ghi log lỗi handler cũng không được làm gián đoạn nghiệp vụ.
        }
    }

    @Override
    public void onStart(T context) {
        invoke("onStart", () -> delegate.onStart(context));
    }

    @Override
    public void onError(T context) {
        invoke("onError", () -> delegate.onError(context));
    }

    @Override
    public void onEvent(Observation.Event event, T context) {
        invoke("onEvent", () -> delegate.onEvent(event, context));
    }

    @Override
    public void onScopeOpened(T context) {
        invoke("onScopeOpened", () -> delegate.onScopeOpened(context));
    }

    @Override
    public void onScopeClosed(T context) {
        invoke("onScopeClosed", () -> delegate.onScopeClosed(context));
    }

    @Override
    public void onStop(T context) {
        invoke("onStop", () -> delegate.onStop(context));
    }

    @Override
    @Deprecated
    public void onScopeReset(T context) {
        invoke("onScopeReset", () -> delegate.onScopeReset(context));
    }
}
~~~

Wrapper này chỉ cô lập `RuntimeException`. Nó không che giấu lỗi nghiêm trọng của JVM. `supportsContext` trả về `false` khi chính việc kiểm tra context thất bại, nghĩa là handler đó không tham gia Observation hiện tại.

Trong dự án dùng phiên bản Micrometer đã loại bỏ API scope reset cũ, bỏ override `onScopeReset`. Hãy kiểm tra Javadoc của đúng phiên bản `micrometer-observation` đang được resolve.

## 6. Đăng ký wrapper thay cho handler gốc

Đăng ký handler đã bọc vào registry:

~~~java
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationHandler(
                new SafeObservationHandler<>(
                        new OptionalMetricsHandler(meterRegistry)
                )
        )
        .observationHandler(
                new SafeObservationHandler<>(
                        new OptionalAuditHandler()
                )
        );
~~~

Nếu đăng ký handler gốc trực tiếp, wrapper không thể bảo vệ callback đó. Hãy bảo đảm mọi handler cần fail-open đều được đăng ký qua wrapper.

Có thể giữ một helper factory để cấu hình nhất quán:

~~~java
static <T extends Observation.Context> ObservationHandler<T> failOpen(
        ObservationHandler<T> handler) {
    return new SafeObservationHandler<>(handler);
}
~~~

Sau đó:

~~~java
registry.observationConfig()
        .observationHandler(failOpen(new OptionalMetricsHandler(meterRegistry)))
        .observationHandler(failOpen(new OptionalAuditHandler()));
~~~

Không đăng ký cả handler gốc và wrapper của chính nó. Nếu làm vậy, callback vẫn chạy trực tiếp trên instance gốc và lỗi có thể thoát ra ngoài.

## 7. Cô lập lỗi để các handler khác vẫn được gọi

Giả sử có ba handler:

- Handler metrics cập nhật Timer.
- Handler audit ghi sự kiện vào hệ thống audit.
- Handler tracing tạo span.

Nếu handler metrics ném exception trong `onStart`, các handler đứng sau có thể không nhận được callback đó. Khi bọc từng handler, exception của metrics handler được ghi log và vòng dispatch tiếp tục đến audit và tracing.

~~~java
registry.observationConfig()
        .observationHandler(failOpen(metricsHandler))
        .observationHandler(failOpen(auditHandler))
        .observationHandler(failOpen(tracingHandler));
~~~

Đây là cách cô lập ở cấp từng handler. Nếu chỉ bọc toàn bộ nhóm bằng một wrapper, exception ở handler đầu tiên vẫn có thể ngăn các handler còn lại bên trong nhóm chạy.

## 8. Kết hợp với composite handler

Micrometer cung cấp hai kiểu composite thường dùng:

- `AllMatchingCompositeObservationHandler`: gọi tất cả handler con có hỗ trợ context.
- `FirstMatchingCompositeObservationHandler`: chỉ chọn handler con phù hợp đầu tiên.

Composite giúp tổ chức dispatch. Nó không thay thế chính sách cô lập lỗi. Nếu một handler con có thể ném exception và cần fail-open, bọc từng handler con trước khi đưa vào composite:

~~~java
ObservationHandler<Observation.Context> tracingHandlers =
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
                failOpen(senderTracingHandler),
                failOpen(receiverTracingHandler),
                failOpen(defaultTracingHandler)
        );

registry.observationConfig()
        .observationHandler(tracingHandlers);
~~~

Với `FirstMatchingCompositeObservationHandler`, wrapper trả về `false` nếu `supportsContext` của handler con thất bại do RuntimeException. Composite có thể tiếp tục tìm handler con phù hợp tiếp theo.

Không nhầm hai kiểu composite: AllMatching dùng khi nhiều handler cùng cần xử lý một context; FirstMatching dùng khi chỉ một handler trong nhóm được chọn.

## 9. Xử lý lỗi trong handler có quản lý scope

Handler tracing thường tạo hoặc lấy scope khi Observation mở scope, rồi khôi phục trạng thái khi scope đóng. Đây là khu vực nhạy cảm vì lỗi cleanup có thể để lại ThreadLocal trên thread được tái sử dụng.

Ví dụ handler quản lý một resource:

~~~java
final class ResourceScopeHandler
        implements ObservationHandler<Observation.Context> {

    private static final Object RESOURCE_KEY = ResourceScopeHandler.class;

    @Override
    public void onScopeOpened(Observation.Context context) {
        ResourceScope resource = openResourceScope();
        context.put(RESOURCE_KEY, resource);
    }

    @Override
    public void onScopeClosed(Observation.Context context) {
        ResourceScope resource = context.get(RESOURCE_KEY);
        if (resource == null) {
            return;
        }

        context.remove(RESOURCE_KEY);
        resource.close();
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof RequestObservationContext;
    }
}
~~~

Đây là ví dụ cấu trúc; `ResourceScope` và `RequestObservationContext` đại diện cho kiểu của ứng dụng. Handler thực tế cần thêm các biện pháp:

- Nếu tạo resource thành công nhưng lưu vào context thất bại, đóng resource ngay trong catch.
- `onScopeClosed` phải an toàn khi không có resource vì `onScopeOpened` có thể thất bại giữa chừng.
- Xóa resource khỏi context trước hoặc trong quá trình đóng để tránh đóng lặp.
- Cleanup phải có tính idempotent nếu lifecycle có thể bị gọi lại bởi code ứng dụng.

Wrapper fail-open giúp callback cleanup không làm hỏng nghiệp vụ và không ngăn Micrometer khôi phục scope. Tuy nhiên, wrapper không thể tự giải phóng resource mà handler đã tạo dở rồi ném exception. Handler vẫn phải tự rollback phần công việc đã thực hiện.

## 10. Vì sao onScopeClosed đặc biệt quan trọng?

Scope của Observation thường lưu current observation trong registry và có thể được dùng để quản lý ThreadLocal. Khi đóng scope, Micrometer thông báo cho handler rồi khôi phục scope trước đó.

Nếu callback `onScopeClosed` ném exception mà không được cô lập:

1. Các handler còn lại trong vòng lặp đóng scope có thể không được gọi.
2. Việc đặt current scope về scope trước đó có thể không được thực hiện.
3. Thread được tái sử dụng có nguy cơ giữ lại context cũ.
4. Các request tiếp theo chạy trên thread đó có thể nhìn thấy context sai.

Vì vậy, các handler có callback scope nên được bọc riêng và kiểm thử cả nhánh mở lẫn đóng. Đừng chỉ kiểm tra rằng `onStart` và `onStop` không làm ném lỗi.

## 11. Không nhầm handler failure với Observation.error

`Observation.error(exception)` biểu diễn lỗi của công việc được quan sát. Nó cập nhật error trong context rồi thông báo `onError` cho các handler.

Ví dụ:

~~~java
Observation.createNotStarted("payment.authorize", registry)
        .observe(() -> paymentService.authorize(command));
~~~

Nếu `paymentService.authorize` ném exception, Observation ghi nhận lỗi nghiệp vụ và ném lại exception cho caller. Wrapper quanh handler chỉ cô lập lỗi của callback telemetry; nó không nuốt lỗi của `paymentService`.

Không gọi `observation.error(handlerException)` từ wrapper khi handler lỗi. Làm vậy sẽ biến lỗi telemetry thành trạng thái lỗi của nghiệp vụ, đồng thời có thể kích hoạt thêm callback `onError` và tạo vòng lặp lỗi.

## 12. Bảo vệ ObservationFilter riêng

`ObservationFilter.map(context)` được gọi khi Observation dừng, trước các callback `onStop`. Filter không phải `ObservationHandler`, vì vậy `SafeObservationHandler` không bảo vệ được nó.

Nếu filter chỉ bổ sung metadata tùy chọn, có thể bọc riêng:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

import java.util.logging.Level;
import java.util.logging.Logger;

final class SafeObservationFilter implements ObservationFilter {
    private static final Logger LOGGER =
            Logger.getLogger(SafeObservationFilter.class.getName());

    private final ObservationFilter delegate;

    SafeObservationFilter(ObservationFilter delegate) {
        this.delegate = delegate;
    }

    @Override
    public Observation.Context map(Observation.Context context) {
        try {
            Observation.Context result = delegate.map(context);
            return result != null ? result : context;
        } catch (RuntimeException error) {
            try {
                LOGGER.log(Level.WARNING, "ObservationFilter failed", error);
            } catch (RuntimeException ignored) {
                // Logger cũng không được làm gián đoạn vòng đời Observation.
            }
            return context;
        }
    }
}
~~~

Filter phải trả lại context hợp lệ. Ví dụ này dùng context ban đầu nếu delegate trả null hoặc ném RuntimeException. Logger chỉ ghi tên filter, callback và loại exception ở mức WARNING; stack trace chi tiết chỉ xuất hiện ở mức FINE. Dùng logger không tự phát sinh Observation mới.

Chỉ áp dụng fail-open nếu metadata do filter thêm là tùy chọn. Nếu filter kiểm tra một ràng buộc bắt buộc của hệ thống, hãy xác định chính sách lỗi riêng thay vì tự động bỏ qua.

## 13. Predicate và convention cũng cần thuần và ổn định

`ObservationPredicate` và `ObservationConvention` không được bảo vệ bởi wrapper handler:

- Predicate được gọi khi tạo Observation để quyết định tạo Observation thật hay no-op.
- Convention được gọi để lấy tên, contextual name và key-value.

Các phương thức này nên thuần, nhanh và không thực hiện I/O. Không gọi database, network, exporter hoặc hệ thống ngoài từ `supportsContext`, `getName()` hay `getLowCardinalityKeyValues()`.

Nếu chúng có thể ném RuntimeException, việc tạo hoặc bắt đầu Observation vẫn có thể thất bại. Hãy validate dữ liệu trước khi tạo Observation, dùng giá trị mặc định an toàn cho metadata tùy chọn và kiểm thử các context thiếu dữ liệu.

## 14. Không ghi log lỗi handler thông qua chính Observation đang lỗi

Khi một handler thất bại, việc ghi log bằng một logger có tích hợp Observation có thể tạo thêm Observation. Nếu Observation mới lại gọi handler đang lỗi, hệ thống có thể tạo vòng lặp:

~~~text
Observation A
    |
    v
Handler telemetry lỗi
    |
    v
Ghi log qua Observation B
    |
    v
Handler telemetry lỗi lần nữa
    |
    v
Observation C ...
~~~

Để tránh recursion:

- Ghi log bằng logger không tự instrument qua Observation.
- Không tạo Observation mới trong callback xử lý lỗi handler.
- Không gửi metric lỗi handler qua chính handler vừa lỗi.
- Nếu cần đếm lỗi handler, dùng một counter riêng trên registry độc lập hoặc cơ chế chẩn đoán không phụ thuộc pipeline đang gặp sự cố.

Không ghi toàn bộ context hoặc payload vào log lỗi. Context có thể chứa URL, ID hoặc dữ liệu nhạy cảm. Chỉ ghi tên handler, callback, loại exception và một mã tương quan đã được kiểm soát.

## 15. Giới hạn những exception được cô lập

Wrapper ví dụ chỉ bắt `RuntimeException`. Đây là lựa chọn phù hợp cho các lỗi lập trình và lỗi runtime mà handler tùy chọn có thể gặp.

Không nên bắt mọi `Throwable`:

| Loại lỗi | Chính sách đề xuất |
|---|---|
| `RuntimeException` từ handler tùy chọn | Ghi nhận và cô lập |
| Exception do exporter hoặc logging client ném ra dưới dạng RuntimeException | Ghi nhận và cô lập nếu telemetry không bắt buộc |
| `OutOfMemoryError` | Để lan truyền |
| `StackOverflowError` | Để lan truyền |
| `LinkageError` | Để lan truyền và xử lý vấn đề runtime/dependency |
| `ThreadDeath` | Không nuốt |

Nếu handler có thể ném checked exception qua một abstraction khác, hãy chuyển đổi có kiểm soát thành một exception riêng tại ranh giới đó. Không dùng catch-all để che mọi trạng thái lỗi.

## 16. Chính sách cho từng loại handler

Không phải handler nào cũng có cùng mức độ quan trọng:

| Handler | Mức độ quan trọng | Cách quyết định |
|---|---|---|
| Metrics handler | Thường là telemetry tùy chọn | Fail-open để request không phụ thuộc exporter |
| Logging/audit quan sát | Tùy yêu cầu audit | Fail-open nếu chỉ là log quan sát; audit bắt buộc cần cơ chế bền vững riêng |
| Tracing exporter | Thường là telemetry tùy chọn | Fail-open nếu mất trace chấp nhận được |
| Context propagation | Có thể ảnh hưởng correlation và baggage | Đánh giá riêng; bảo đảm cleanup và fallback |
| Handler kiểm tra chính sách nghiệp vụ | Không phải telemetry thuần | Không bọc fail-open nếu lỗi phải chặn nghiệp vụ |

Nếu một handler thực hiện authorization, validation hoặc kiểm soát nghiệp vụ, nó không nên được coi là handler telemetry chỉ vì được đăng ký qua ObservationRegistry. Không dùng fail-open để bỏ qua các kiểm tra bảo mật hoặc điều kiện nghiệp vụ.

## 17. Giữ handler nhanh và không chặn luồng nghiệp vụ

Handler được gọi đồng bộ trong lifecycle. Callback chậm có thể làm tăng latency ngay cả khi không ném exception.

Các nguyên tắc:

1. Tránh gọi network hoặc ghi dữ liệu đồng bộ vào hệ thống bên ngoài trong `onStart`, `onError` và `onStop`.
2. Nếu cần gửi dữ liệu ra ngoài, dùng client có timeout và cơ chế buffer/batch phù hợp.
3. Giới hạn kích thước queue và xác định hành vi khi queue đầy.
4. Không chặn event-loop hoặc thread phục vụ request để chờ exporter.
5. Không dùng retry vô hạn trong callback.
6. Không dùng lock toàn cục khiến các Observation chờ nhau.

Fail-open giải quyết exception; nó không tự giải quyết latency do handler block. Một handler không ném lỗi nhưng mất 500 ms trong `onStop` vẫn có thể làm request chậm thêm 500 ms.

## 18. Handler là singleton: quản lý trạng thái đồng thời

Một handler thường được đăng ký một lần và được nhiều Observation gọi đồng thời. Vì vậy:

- Không lưu context hiện tại trong một field mutable duy nhất.
- Không dùng một Timer.Sample chung cho nhiều request.
- Dùng `Observation.Context` để giữ dữ liệu riêng cho từng Observation.
- Dùng cấu trúc thread-safe cho bộ đếm hoặc cache dùng chung.
- Không giữ context sau `onStop` nếu không có lý do và cơ chế giải phóng rõ ràng.

Ví dụ lưu trạng thái riêng trong context:

~~~java
private static final Object START_TIME_KEY = new Object();

@Override
public void onStart(Observation.Context context) {
    context.put(START_TIME_KEY, System.nanoTime());
}

@Override
public void onStop(Observation.Context context) {
    Long startedAt = context.get(START_TIME_KEY);
    if (startedAt == null) {
        return;
    }

    long elapsedNanos = System.nanoTime() - startedAt;
    recordElapsed(elapsedNanos);
    context.remove(START_TIME_KEY);
}
~~~

Mỗi Observation có context riêng nên timestamp không bị ghi đè giữa các request. Trong thực tế, nếu cần đo thời gian, ưu tiên Timer hoặc Timer.Sample để dùng clock và quy tắc đơn vị của Micrometer.

## 19. Kiểm thử handler lỗi không làm hỏng nghiệp vụ

Test nên chứng minh:

- Handler lỗi trong `onStart` không ngăn code nghiệp vụ chạy.
- Handler khỏe mạnh sau nó vẫn nhận callback.
- Lỗi trong `onStop` không thay kết quả thành công.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

class SafeObservationHandlerTest {

    @Test
    void handlerFailureDoesNotStopBusinessOperationOrOtherHandlers() {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger businessCalls = new AtomicInteger();
        AtomicInteger healthyStarts = new AtomicInteger();

        ObservationHandler<Observation.Context> broken =
                new ObservationHandler<>() {
                    @Override
                    public void onStart(Observation.Context context) {
                        throw new IllegalStateException("metrics backend unavailable");
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        throw new IllegalStateException("stop failed");
                    }

                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }
                };

        ObservationHandler<Observation.Context> healthy =
                new ObservationHandler<>() {
                    @Override
                    public void onStart(Observation.Context context) {
                        healthyStarts.incrementAndGet();
                    }

                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }
                };

        registry.observationConfig()
                .observationHandler(new SafeObservationHandler<>(broken))
                .observationHandler(healthy);

        String result = Observation.createNotStarted("checkout", registry)
                .observe(() -> {
                    businessCalls.incrementAndGet();
                    return "accepted";
                });

        assertThat(result).isEqualTo("accepted");
        assertThat(businessCalls).hasValue(1);
        assertThat(healthyStarts).hasValue(1);
    }
}
~~~

Test này dùng handler giả lập lỗi để chứng minh callback lỗi được cô lập. Trong ứng dụng thực tế, nên kiểm thử cả handler metrics/tracing thật với dependency được giả lập để xác nhận timeout, exception và trạng thái cleanup.

## 20. Giữ nguyên exception nghiệp vụ khi onError và onStop lỗi

Một test khác xác minh exception gốc vẫn đến caller:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SafeObservationHandlerBusinessExceptionTest {

@Test
void preservesBusinessExceptionWhenHandlersFail() {
    ObservationRegistry registry = ObservationRegistry.create();
    RuntimeException businessFailure =
            new IllegalArgumentException("invalid order");

    ObservationHandler<Observation.Context> broken =
            new ObservationHandler<>() {
                @Override
                public void onError(Observation.Context context) {
                    throw new IllegalStateException("tracing failed");
                }

                @Override
                public void onStop(Observation.Context context) {
                    throw new IllegalStateException("metrics stop failed");
                }

                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }
            };

    registry.observationConfig()
            .observationHandler(new SafeObservationHandler<>(broken));

    assertThatThrownBy(() ->
            Observation.createNotStarted("checkout", registry)
                    .observe((Runnable) () -> {
                        throw businessFailure;
                    })
    ).isSameAs(businessFailure);
}
}
~~~

Kết quả mong đợi là caller nhận đúng `businessFailure`. Lỗi handler được ghi log riêng và không thay thế exception nghiệp vụ.

## 21. Kiểm thử khôi phục scope sau lỗi

Handler lỗi khi đóng scope có thể làm current scope bị giữ lại nếu callback exception thoát ra ngoài. Hãy kiểm tra registry không còn Observation hiện tại sau khi khối `observe` kết thúc:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SafeObservationHandlerScopeTest {

@Test
void restoresCurrentScopeWhenScopeCloseHandlerFails() {
    ObservationRegistry registry = ObservationRegistry.create();

    ObservationHandler<Observation.Context> brokenScopeHandler =
            new ObservationHandler<>() {
                @Override
                public void onScopeClosed(Observation.Context context) {
                    throw new IllegalStateException("scope cleanup failed");
                }

                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }
            };

    registry.observationConfig()
            .observationHandler(new SafeObservationHandler<>(brokenScopeHandler));

    Observation.createNotStarted("checkout", registry)
            .observe(() -> {});

    assertThat(registry.getCurrentObservation()).isNull();
}
}
~~~

Đây là kiểm thử quan trọng cho handler tracing hoặc handler quản lý ThreadLocal. Nó xác minh wrapper không để exception trong callback đóng scope ngăn registry khôi phục trạng thái trước đó.

## 22. Theo dõi lỗi handler mà không tạo vòng lặp

Log là lựa chọn đơn giản để ghi nhận callback lỗi. Nếu cần metric cho lỗi handler, hãy dùng một registry độc lập hoặc một đường ghi nhận không phụ thuộc vào ObservationRegistry đang gặp sự cố.

Một mô hình có thể dùng:

| Dữ liệu | Cách ghi |
|---|---|
| Tên handler | Log field hoặc tag có tập giá trị hữu hạn |
| Tên callback | `onStart`, `onError`, `onStop`, `onScopeClosed` |
| Loại exception | Tên class exception |
| Số lần lỗi | Counter riêng nếu registry metric còn hoạt động |
| Stack trace | Log có kiểm soát, không gắn vào metric tag |

Không dùng exception message hoặc request ID làm tag. Nếu handler lỗi liên tục, dùng rate limiting hoặc log sampling để tránh biến sự cố telemetry thành một đợt log flood.

## 23. Những lỗi thường gặp

**Cho rằng Micrometer tự nuốt exception từ handler.** Lifecycle dispatch gọi callback trực tiếp. Nếu cần fail-open, bọc handler và xử lý RuntimeException trong từng callback.

**Chỉ bọc onStart.** Lỗi có thể xảy ra trong supportsContext, onError, onEvent, onScopeOpened, onScopeClosed hoặc onStop. Wrapper cần bao phủ toàn bộ callback.

**Bọc cả nhóm handler bằng một try/catch.** Một handler lỗi có thể ngăn các handler còn lại trong nhóm chạy. Bọc từng handler con.

**Bắt Throwable và bỏ qua.** Cách này có thể che giấu lỗi nghiêm trọng của JVM. Chỉ cô lập các exception dự kiến từ handler tùy chọn.

**Đưa lỗi handler vào Observation.error.** Điều này làm sai trạng thái nghiệp vụ và có thể kích hoạt thêm callback lỗi.

**Chỉ kiểm thử metrics được tạo.** Cần kiểm tra cả kết quả nghiệp vụ, exception gốc, handler sau vẫn chạy và scope được khôi phục.

**Bỏ qua cleanup sau lỗi một phần.** Wrapper không thể giải phóng resource mà handler đã tạo dở. Handler phải rollback và cleanup an toàn.

**Dùng logging có instrument lại Observation đang lỗi.** Điều này có thể tạo vòng lặp callback. Dùng logger độc lập.

**Cho rằng fail-open xử lý được callback chậm.** Wrapper cô lập exception, không loại bỏ latency do I/O hoặc blocking.

**Áp dụng fail-open cho kiểm tra nghiệp vụ.** Authorization, validation và chính sách bắt buộc phải có chính sách lỗi riêng.

## 24. Checklist triển khai

Trước khi triển khai handler tùy chỉnh, hãy xác minh:

- [ ] Xác định handler có thực sự tùy chọn đối với nghiệp vụ hay không.
- [ ] Xác định các callback mà handler triển khai.
- [ ] Bọc `supportsContext` và mọi callback có thể ném RuntimeException.
- [ ] Khi `supportsContext` lỗi, wrapper bỏ qua handler cho context đó.
- [ ] Log lỗi handler bằng logger không tạo Observation đệ quy.
- [ ] Không bắt các Error nghiêm trọng của JVM.
- [ ] Handler sau vẫn chạy khi handler trước thất bại.
- [ ] `onScopeClosed` không thể ngăn khôi phục scope.
- [ ] Handler có state rollback và cleanup an toàn sau lỗi một phần.
- [ ] Filter, predicate và convention được bảo vệ riêng nếu có logic có thể lỗi.
- [ ] Không thực hiện I/O blocking hoặc retry vô hạn trong callback.
- [ ] Có test cho onStart, onError, onStop và scope cleanup.
- [ ] Exception nghiệp vụ gốc vẫn được truyền đến caller.

## 25. Kết luận

ObservationHandler là một phần của đường thực thi Observation. Các callback được gọi đồng bộ, vì vậy RuntimeException từ handler có thể chặn code nghiệp vụ, ngăn handler khác chạy, che khuất exception gốc hoặc làm scope không được khôi phục.

Với handler chỉ phục vụ telemetry, hãy dùng wrapper fail-open để bắt và ghi nhận RuntimeException riêng cho `supportsContext`, `onStart`, `onError`, `onEvent`, `onScopeOpened`, `onScopeClosed` và `onStop`. Bọc từng handler con để lỗi được cô lập đúng phạm vi; không bắt các Error nghiêm trọng. Handler vẫn phải tự rollback resource nếu callback thất bại giữa chừng, còn filter, predicate và convention cần chính sách bảo vệ riêng. Kiểm thử cả kết quả nghiệp vụ, exception gốc và việc khôi phục scope để bảo đảm telemetry không làm giảm độ ổn định của ứng dụng.

## Tài liệu tham khảo

- [Micrometer – Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer – Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer – SimpleObservation source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-observation/src/main/java/io/micrometer/observation/SimpleObservation.java)
- [Micrometer – ObservationHandler API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationHandler.html)
