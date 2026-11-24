# Đăng ký handler và kiểm tra loại Context được hỗ trợ

Micrometer Observation tách phần tạo tín hiệu quan sát khỏi phần xử lý tín hiệu đó. Mã nghiệp vụ tạo một Observation và phát các lifecycle signal như start, event, error, scope opened hoặc stop. Một hoặc nhiều ObservationHandler đã đăng ký trên ObservationRegistry nhận các signal phù hợp để tạo metric, span, log hoặc hành động quan sát khác.

Mỗi handler có thể giới hạn loại Observation.Context mà nó xử lý bằng supportsContext(...). Đây là điểm kiểm tra quan trọng khi dùng handler có kiểu tổng quát cụ thể, ví dụ ObservationHandler<PaymentObservationContext>. Handler chỉ nên trả về true khi context thực sự thuộc loại mà các callback của nó có thể xử lý an toàn.

## ObservationHandler tham gia vào vòng đời như thế nào?

ObservationHandler là thành phần phản ứng với lifecycle của Observation. Các callback thường dùng gồm:

| Callback | Khi được gọi | Mục đích thường gặp |
|---|---|---|
| onStart(context) | Observation bắt đầu | Khởi tạo trạng thái phụ hoặc bắt đầu một span |
| onError(context) | Observation.error(...) được gọi | Ghi nhận ngoại lệ hoặc đánh dấu span lỗi |
| onEvent(event, context) | Observation.event(...) được gọi | Xử lý một mốc trong operation |
| onScopeOpened(context) | Scope của Observation được mở | Đưa context vào execution context hoặc ThreadLocal |
| onScopeClosed(context) | Scope được đóng | Khôi phục hoặc dọn execution context |
| onStop(context) | Observation kết thúc | Ghi metric cuối cùng hoặc giải phóng trạng thái |
| supportsContext(context) | Registry kiểm tra khả năng xử lý | Chọn handler phù hợp với loại Context |

Không phải handler nào cũng cần override tất cả callback. Một handler chỉ cần ghi nhận thời điểm bắt đầu và kết thúc có thể triển khai onStart và onStop. Handler cần xử lý lỗi hoặc event thì override thêm onError hoặc onEvent.

## Đăng ký handler vào ObservationRegistry

Với ứng dụng Java độc lập, tạo registry rồi đăng ký handler qua observationConfig():

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class OperationLoggingHandler
        implements ObservationHandler<Observation.Context> {

    @Override
    public void onStart(Observation.Context context) {
        System.out.println("START " + context.getName());
    }

    @Override
    public void onStop(Observation.Context context) {
        System.out.println("STOP " + context.getName());
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }
}
~~~

Đăng ký handler:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationHandler(new OperationLoggingHandler());
~~~

Handler trên dùng Observation.Context nên có thể nhận nhiều loại context mặc định và context con. supportsContext trả về true vì callback chỉ đọc tên Observation, một thuộc tính có sẵn ở context cơ sở. Nếu callback cần gọi API riêng của một context chuyên biệt, hãy dùng generic type cụ thể và kiểm tra instanceof thay vì trả true cho mọi context.

Handler cần được đăng ký trước khi Observation cần quan sát được start. Nếu đăng ký sau khi một Observation đã bắt đầu, handler mới không nhận lại các callback đã xảy ra trước đó.

## Hiểu Observation.Context và context chuyên biệt

Observation.Context là một vùng dữ liệu có thể thay đổi, gắn với một Observation. Nó giữ thông tin giữa mã instrumentation và handler, cũng như giữa các callback như onStart và onStop. Context cơ sở có thể lưu dữ liệu theo kiểu key/value; các loại context chuyên biệt thường kế thừa Observation.Context và bổ sung API có kiểu rõ ràng.

Ví dụ, context của một thao tác thanh toán có thể chứa nhà cung cấp và phương thức thanh toán:

~~~java
import io.micrometer.observation.Observation;

public class PaymentObservationContext extends Observation.Context {
    private String provider;
    private String paymentMethod;

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getPaymentMethod() {
        return paymentMethod;
    }

    public void setPaymentMethod(String paymentMethod) {
        this.paymentMethod = paymentMethod;
    }
}
~~~

Context riêng giúp handler đọc đúng dữ liệu mà không phải ép kiểu từ Object hoặc dùng các key chuỗi rải rác. Chỉ đưa dữ liệu thực sự cần cho instrumentation vào context. Không lưu password, token, số thẻ hoặc dữ liệu cá nhân nhạy cảm trong context telemetry.

## Tạo Observation với context do ứng dụng cung cấp

Observation.createNotStarted(...) có overload nhận Supplier của context. Supplier trả về context cụ thể và được truyền cùng registry:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation observation = Observation.createNotStarted(
        "payment.authorize",
        () -> {
            PaymentObservationContext context =
                    new PaymentObservationContext();
            context.setProvider("bank-a");
            context.setPaymentMethod("card");
            return context;
        },
        observationRegistry);

observation.observe(() -> paymentGateway.authorize(command));
~~~

Supplier giúp Observation trì hoãn việc tạo context cho đến khi cần. Nếu registry là no-op hoặc Observation bị predicate loại bỏ, Micrometer có thể tránh tạo context không cần thiết. Mỗi lần tạo Observation phải cung cấp một context mới; không dùng lại cùng một mutable context cho nhiều operation đồng thời.

Trong ví dụ, handler nhận PaymentObservationContext nhờ supplier trả đúng kiểu đó. Không cần đăng ký tên class hoặc tag để chọn handler; supportsContext sẽ quyết định.

## Viết handler có generic type cụ thể

Khi handler chỉ xử lý PaymentObservationContext, khai báo generic type đó:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public class PaymentAuditHandler
        implements ObservationHandler<PaymentObservationContext> {

    @Override
    public void onStart(PaymentObservationContext context) {
        System.out.println(
                "Payment started with provider " + context.getProvider());
    }

    @Override
    public void onStop(PaymentObservationContext context) {
        System.out.println(
                "Payment finished with method " + context.getPaymentMethod());
    }

    @Override
    public void onError(PaymentObservationContext context) {
        Throwable error = context.getError();
        if (error != null) {
            System.out.println(
                    "Payment failed: " + error.getClass().getSimpleName());
        }
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentObservationContext;
    }
}
~~~

Phương thức supportsContext nhận Observation.Context cơ sở, dù các callback của handler nhận PaymentObservationContext. Biểu thức instanceof kiểm tra kiểu thực tế trước khi framework gọi callback generic. Đây là cách viết an toàn và phổ biến khi handler chỉ phục vụ một loại context.

Không viết supportsContext như sau nếu handler được khai báo là ObservationHandler<PaymentObservationContext>:

~~~java
@Override
public boolean supportsContext(Observation.Context context) {
    return true;
}
~~~

Context cơ sở khác có thể được chuyển vào callback, dẫn đến lỗi ép kiểu khi runtime gọi onStart hoặc callback khác. Giá trị true chỉ phù hợp khi handler thật sự xử lý được mọi context mà registry có thể gửi đến.

## Đăng ký và chạy một handler chuyên biệt

Ví dụ hoàn chỉnh dùng registry độc lập:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationHandler(new PaymentAuditHandler());

Observation observation = Observation.createNotStarted(
        "payment.authorize",
        () -> {
            PaymentObservationContext context =
                    new PaymentObservationContext();
            context.setProvider("bank-a");
            context.setPaymentMethod("card");
            return context;
        },
        registry);

observation.observe(() -> paymentGateway.authorize(command));
~~~

Khi Observation bắt đầu, PaymentAuditHandler nhận onStart. Khi operation kết thúc, handler nhận onStop. Nếu lambda ném exception, Observation ghi nhận lỗi trong context và handler có thể nhận onError trước khi onStop. Context được dùng xuyên suốt lifecycle nên dữ liệu được đặt trước khi start vẫn có thể đọc ở callback kết thúc.

## Một Observation có thể có nhiều handler

Một registry thường cần nhiều hành vi cho cùng Observation: handler metrics tạo Timer, handler tracing tạo span, handler tùy chỉnh ghi audit hoặc bổ sung dữ liệu. Có thể đăng ký các handler riêng:

~~~java
registry.observationConfig()
        .observationHandler(new PaymentAuditHandler())
        .observationHandler(
                DefaultMeterObservationHandler.builder(meterRegistry).build());
~~~

Đoạn minh họa cần import DefaultMeterObservationHandler từ package io.micrometer.core.instrument.observation và dùng một MeterRegistry đã được cấu hình. Trong Spring Boot, registry và meter handler thường đã được auto-configure; chỉ thêm handler tùy chỉnh mà ứng dụng cần.

Mỗi handler được kiểm tra supportsContext. Những handler hỗ trợ context sẽ nhận callback tương ứng. Vì vậy, một context có thể được xử lý bởi nhiều handler cùng lúc. Handler audit không thay thế handler metrics; chúng bổ sung các hành vi độc lập.

Nếu đăng ký cùng một handler hai lần hoặc vừa đăng ký riêng vừa đặt nó trong composite, callback có thể chạy nhiều lần. Chỉ đăng ký một lần cho mỗi vai trò xử lý.

## Chọn composite handler phù hợp

Micrometer cung cấp hai composite handler hữu ích khi cần gom nhiều handler có quy tắc chọn:

| Composite | Hành vi | Trường hợp dùng |
|---|---|---|
| FirstMatchingCompositeObservationHandler | Chuyển callback cho handler đầu tiên hỗ trợ context | Chọn đúng một handler trong nhóm, ví dụ một tracing handler phù hợp với sender, receiver hoặc context mặc định |
| AllMatchingCompositeObservationHandler | Chuyển callback cho tất cả handler hỗ trợ context | Gom nhiều hành vi cần cùng chạy cho context đó |

Ví dụ dùng FirstMatchingCompositeObservationHandler:

~~~java
import java.util.List;

import io.micrometer.observation.ObservationHandler;

ObservationHandler<?> tracingHandlers =
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
                List.of(senderTracingHandler,
                        receiverTracingHandler,
                        defaultTracingHandler));

registry.observationConfig().observationHandler(tracingHandlers);
~~~

Trong ví dụ, danh sách được xét theo thứ tự. Handler đầu tiên có supportsContext trả về true sẽ được chọn trong composite. Cách này phù hợp khi các handler là những lựa chọn thay thế cho cùng một vai trò; ví dụ sender context dùng handler truyền trace header phía gửi, receiver context dùng handler phía nhận, còn context thông thường dùng handler mặc định.

Nếu muốn nhiều handler cùng nhận callback, dùng AllMatchingCompositeObservationHandler:

~~~java
ObservationHandler<?> paymentHandlers =
        new ObservationHandler.AllMatchingCompositeObservationHandler(
                List.of(paymentAuditHandler, paymentMetricsHandler));

registry.observationConfig().observationHandler(paymentHandlers);
~~~

Composite chỉ nhóm cách dispatch. Mỗi handler con vẫn phải có supportsContext đúng. Không dùng FirstMatching cho nhóm gồm audit và metrics nếu cả hai đều cần chạy; composite có thể chỉ gọi một handler và làm mất hành vi còn lại.

## Context type và context name là hai tiêu chí khác nhau

supportsContext nên chủ yếu kiểm tra kiểu context hoặc khả năng xử lý dữ liệu mà callback cần. Tên Observation mô tả operation; context type mô tả cấu trúc dữ liệu mà handler nhận. Hai Observation khác tên vẫn có thể dùng cùng một context type và được cùng handler xử lý.

Nếu handler chỉ muốn xử lý một nhóm tên Observation, có thể kiểm tra thêm context.getName() sau khi xác nhận kiểu:

~~~java
@Override
public boolean supportsContext(Observation.Context context) {
    return context instanceof PaymentObservationContext
            && context.getName() != null
            && context.getName().startsWith("payment.");
}
~~~

Không nên dùng tên làm cách thay thế cho kiểm tra kiểu khi callback yêu cầu một subclass cụ thể. Một Observation có tên payment.authorize vẫn có thể được tạo với Observation.Context mặc định; ép kiểu chỉ dựa vào tên là không an toàn.

## Handler tổng quát và handler chuyên biệt

Có thể triển khai handler theo hai phạm vi:

| Kiểu handler | Generic type | supportsContext thường dùng |
|---|---|---|
| Handler dùng cho mọi Observation | Observation.Context | true nếu callback chỉ dùng API cơ sở |
| Handler dùng cho một context riêng | PaymentObservationContext | context instanceof PaymentObservationContext |
| Handler cho context transport | SenderContext<?> hoặc RequestReplyReceiverContext<?, ?> | Kiểm tra đúng loại sender/receiver context |
| Handler cho một nhóm context con | Context cha chung | Kiểm tra context instanceof loại cha phù hợp |

Ví dụ handler tổng quát chỉ ghi tên và lỗi:

~~~java
public class ErrorLoggingHandler
        implements ObservationHandler<Observation.Context> {

    @Override
    public void onError(Observation.Context context) {
        Throwable error = context.getError();
        if (error != null) {
            System.err.println(
                    context.getName() + " failed: "
                            + error.getClass().getSimpleName());
        }
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }
}
~~~

Handler tổng quát phù hợp cho chức năng thực sự dùng được với mọi context. Nếu logic cần truy cập setter, carrier, response hoặc field riêng của một context transport, hãy dùng generic type cụ thể và kiểm tra instanceof tương ứng.

## Đăng ký handler bằng Spring Boot

Spring Boot tự động đăng ký các bean kiểu ObservationHandler trên ObservationRegistry do Boot quản lý. Vì vậy, trong ứng dụng Spring Boot, có thể khai báo handler chuyên biệt bằng bean:

~~~java
import io.micrometer.observation.ObservationHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ObservationHandlerConfiguration {
    @Bean
    ObservationHandler<PaymentObservationContext> paymentAuditHandler() {
        return new PaymentAuditHandler();
    }
}
~~~

Service inject ObservationRegistry do Spring Boot quản lý và tạo Observation với context supplier như ví dụ trước. Không cần gọi observationConfig().observationHandler(...) lần nữa cho cùng bean, vì Boot đã tự đăng ký bean handler. Đăng ký cả hai cách có thể làm callback chạy lặp.

Nếu tự tạo một ObservationRegistry riêng thay vì dùng registry do Boot quản lý, các bean handler không tự động được gắn vào registry riêng đó. Khi ấy phải đăng ký handler trực tiếp trên registry riêng hoặc cấu hình qua ObservationRegistryCustomizer phù hợp với registry mà ứng dụng thực sự sử dụng.

## Dùng ObservationRegistryCustomizer khi cần cấu hình thêm

Spring Boot cũng hỗ trợ ObservationRegistryCustomizer để bổ sung cấu hình registry. Ví dụ, có thể thêm một handler trực tiếp qua customizer:

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RegistryCustomization {
    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> observationHandlerCustomizer() {
        return registry -> registry.observationConfig()
                .observationHandler(new OperationLoggingHandler());
    }
}
~~~

Chỉ chọn một cách đăng ký cho cùng handler: khai báo handler thành bean để Boot tự phát hiện, hoặc thêm handler qua customizer. Không dùng đồng thời cả hai cách với cùng instance/logic nếu không muốn callback lặp. Tên package của ObservationRegistryCustomizer có thể phụ thuộc phiên bản Spring Boot; kiểm tra dependency và API của phiên bản dự án trước khi áp dụng.

## supportsContext cần thuần, nhanh và an toàn

supportsContext có thể được gọi trong quá trình dispatch lifecycle. Hãy giữ phương thức này đơn giản:

- Chỉ kiểm tra kiểu hoặc điều kiện nhẹ trên context.
- Không thực hiện I/O, truy vấn database hoặc gọi service bên ngoài.
- Không thay đổi context hoặc ghi metric trong lúc kiểm tra.
- Không dựa vào state mutable của handler để quyết định kiểu.
- Không ép kiểu trước khi xác nhận instanceof.

Handler thường được dùng chung trong ứng dụng. Tránh lưu dữ liệu của một operation vào field mutable của handler, vì nhiều Observation có thể chạy đồng thời. Hãy đặt dữ liệu riêng của từng operation trong Observation.Context; handler đọc dữ liệu đó ở callback tương ứng.

Nếu handler cần tạo state khi onStart và dùng lại ở onStop, lưu state vào context hoặc một cấu trúc gắn với context. Không dùng một biến instance duy nhất như currentPayment cho nhiều operation đồng thời.

## Phân biệt supportsContext với Predicate và Filter

Ba cơ chế này tác động ở các giai đoạn khác nhau:

| Thành phần | Câu hỏi nó trả lời | Kết quả |
|---|---|---|
| ObservationPredicate | Có nên tạo Observation cho operation này không? | Tạo Observation thật hoặc no-op Observation |
| ObservationHandler.supportsContext | Handler này có xử lý được loại context hiện tại không? | Gọi hoặc bỏ qua handler |
| ObservationFilter | Cần điều chỉnh context thế nào trước khi handler xử lý lúc stop? | Trả về context đã được biến đổi |

Nếu predicate loại Observation, handler không nhận lifecycle callback của operation đó. Nếu predicate cho phép nhưng không handler nào hỗ trợ context, Observation vẫn có thể chạy nhưng không có hành vi handler tương ứng. Nếu handler hỗ trợ context, filter vẫn có thể điều chỉnh context trước callback onStop.

Không dùng supportsContext để thay thế predicate khi mục tiêu là tắt toàn bộ Observation. Ngược lại, không dùng predicate để chọn một handler chuyên biệt; đó là trách nhiệm của supportsContext.

## Kiểm thử handler chỉ nhận đúng Context

Test dưới đây đăng ký một handler cho PaymentObservationContext, sau đó chạy một Observation có context thanh toán và một Observation dùng context mặc định:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class PaymentObservationHandlerTest {
    @Test
    void handlesOnlyPaymentContext() {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger starts = new AtomicInteger();
        AtomicInteger stops = new AtomicInteger();

        ObservationHandler<PaymentObservationContext> handler =
                new ObservationHandler<>() {
                    @Override
                    public void onStart(PaymentObservationContext context) {
                        starts.incrementAndGet();
                    }

                    @Override
                    public void onStop(PaymentObservationContext context) {
                        stops.incrementAndGet();
                    }

                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return context instanceof PaymentObservationContext;
                    }
                };

        registry.observationConfig().observationHandler(handler);

        Observation payment = Observation.createNotStarted(
                "payment.authorize",
                PaymentObservationContext::new,
                registry);
        payment.observe(() -> {
            // Thực hiện operation thanh toán giả lập.
        });

        Observation generic = Observation.createNotStarted(
                "generic.operation", registry);
        generic.observe(() -> {
            // Operation dùng Observation.Context mặc định.
        });

        assertThat(starts).hasValue(1);
        assertThat(stops).hasValue(1);
    }
}
~~~

Test chứng minh handler chỉ nhận context chuyên biệt. Observation mặc định vẫn có thể được tạo và hoàn tất, nhưng handler thanh toán không nhận callback vì supportsContext trả false. Không cần kiểm tra log; bộ đếm trong test xác nhận chính xác số callback.

Có thể bổ sung test cho:

1. Payment context hoàn tất thành công: onStart và onStop mỗi callback một lần.
2. Payment context gặp lỗi: onError và onStop được gọi.
3. Generic context: handler thanh toán không nhận callback.
4. Hai handler cùng hỗ trợ PaymentObservationContext: cả hai được gọi khi đăng ký riêng hoặc dùng AllMatching composite.
5. FirstMatching composite: chỉ handler đầu tiên hỗ trợ context được gọi.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ClassCastException trong callback | supportsContext trả true cho context không đúng generic type | Dùng instanceof kiểm tra context trước khi trả true |
| Handler không chạy | Chưa đăng ký handler, Observation là no-op hoặc supportsContext trả false | Kiểm tra registry, predicate và context thực tế |
| Handler tổng quát chạy với mọi operation | Generic type là Observation.Context và supportsContext luôn true | Giới hạn theo context type hoặc điều kiện nhẹ |
| Hai handler cùng ghi một metric | Đăng ký lặp hoặc composite và đăng ký riêng cùng lúc | Chọn một đường đăng ký |
| Audit chạy nhưng metrics không chạy | Composite first-matching chỉ chọn một handler hoặc meter handler không được đăng ký | Dùng đăng ký riêng hoặc all-matching theo mục tiêu |
| Context ở onStop thiếu dữ liệu | Mã instrumentation chưa đặt dữ liệu vào context hoặc filter thay đổi context | Kiểm tra supplier, thứ tự cập nhật và ObservationFilter |
| Handler hoạt động ở registry này nhưng không ở registry kia | Handler chỉ được gắn vào một ObservationRegistry | Kiểm tra registry mà instrumentation thực sự dùng |
| Dữ liệu operation bị ghi đè giữa request | Handler lưu state per-operation trong field dùng chung | Lưu state trong Observation.Context |
| Handler không nhận context con như dự kiến | supportsContext kiểm tra sai class hoặc dùng equals/name thay type | Kiểm tra kế thừa và dùng instanceof đúng loại |

## Checklist triển khai

- [ ] Handler được đăng ký trên đúng ObservationRegistry mà instrumentation sử dụng.
- [ ] Generic type của handler phản ánh loại Context mà callback cần.
- [ ] supportsContext kiểm tra instanceof hoặc điều kiện tương đương an toàn.
- [ ] Handler tổng quát chỉ trả true khi callback xử lý được context cơ sở.
- [ ] Context chuyên biệt được tạo qua Supplier mới cho mỗi Observation.
- [ ] Nhiều handler được phối hợp theo đúng mục tiêu: chạy tất cả hay chọn một.
- [ ] Không đăng ký trùng cùng handler qua bean, customizer và cấu hình thủ công.
- [ ] supportsContext không thực hiện I/O hoặc thay đổi context.
- [ ] State riêng của operation được giữ trong Context, không nằm ở field dùng chung.
- [ ] Test xác nhận context được hỗ trợ nhận callback và context khác bị bỏ qua.
- [ ] Đã kiểm tra các nhánh start, error, event, scope và stop cần thiết.

## Tài liệu tham khảo

- [Micrometer Observation - Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Observation - Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation - Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

Đăng ký ObservationHandler giúp bổ sung metric, tracing, log hoặc xử lý tùy chỉnh cho cùng một instrumentation. supportsContext xác định handler nào có thể xử lý Context hiện tại và bảo vệ callback có generic type chuyên biệt. Hãy tạo context đúng kiểu, đăng ký handler trên đúng registry, chọn composite theo semantics cần thiết và kiểm thử cả context được hỗ trợ lẫn context bị bỏ qua để tránh lỗi ép kiểu hoặc callback chạy lặp.
