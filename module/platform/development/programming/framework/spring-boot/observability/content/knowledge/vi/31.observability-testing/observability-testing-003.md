# Test observation name trong Spring Boot

Observation name là định danh của một operation được instrument. Tên tốt giúp người vận hành nhận ra cùng một loại operation giữa các request, service instance và môi trường. Tên không ổn định hoặc chứa dữ liệu động có thể làm metrics phân mảnh thành nhiều time series, khiến dashboard khó tổng hợp và alert mất ý nghĩa. Vì vậy, kiểm thử observation name là một phần của kiểm thử observability contract, tương tự kiểm thử API response hoặc event schema.

Bài **Test observation name** thuộc chương **Testing observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể xác định naming contract, kiểm thử tên Observation trực tiếp qua ObservationHandler, xác minh custom ObservationConvention, phân biệt observation name với meter/span name, kiểm soát cardinality và viết regression tests để ngăn thay đổi tên ngoài ý muốn.

## 1. Observation name đại diện cho điều gì?

Observation name định danh loại operation đang được quan sát, ví dụ:

- orders.lookup
- payment.authorize
- inventory.reserve
- messaging.publish
- report.generate

Tên nên mô tả operation, không mô tả một lần thực thi cụ thể. Tên như orders.lookup.ORD-82731 gắn identifier của một order vào tên operation; mỗi order có thể tạo ra một meter name/series khác nhau hoặc trace operation khó tổng hợp.

| Tên ổn định | Tên không ổn định |
| --- | --- |
| orders.lookup | orders.lookup.ORD-82731 |
| payment.authorize | payment.authorize.customer-42 |
| report.generate | report.generate.2026-11-22T10:30 |
| messaging.consume | messaging.consume.message-uuid |

Tên ổn định giúp gom dữ liệu theo loại operation. Thông tin biến đổi theo lần gọi, nếu thật sự cần, nên nằm trong attributes/log fields phù hợp và có policy.

## 2. Observation name khác meter name và span name

Observation là abstraction ở Micrometer. Các handlers có thể chuyển cùng một Observation thành nhiều tín hiệu, và mỗi hệ thống có naming convention riêng:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Observation name | orders.lookup | Tên operation ở tầng instrumentation |
| Meter name | orders.lookup hoặc tên theo convention | Định danh meter trong registry |
| Span name | orders.lookup | Tên span trong tracing backend |
| Metric tag | outcome=success | Phân chiều dữ liệu có cardinality kiểm soát |
| Trace attribute | order.type=retail | Metadata của một span |

Không giả định mọi handler giữ nguyên observation name. Meter convention có thể thêm suffix như .active, .duration hoặc đổi format; tracing bridge có thể áp dụng convention riêng. Khi test, xác định contract ở đúng tầng cần bảo vệ.

Nếu yêu cầu là business instrumentation không đổi tên, test Observation name trực tiếp. Nếu yêu cầu là metric series hoặc span name xuất ra đúng format, viết thêm integration test cho registry/bridge tương ứng.

## 3. Chọn naming convention

Một naming convention tốt có các đặc điểm:

- Dùng tên operation ổn định, có ý nghĩa nghiệp vụ hoặc kỹ thuật.
- Dùng một style thống nhất, thường là lowercase và dấu chấm phân cấp.
- Không chứa request ID, user ID, order ID, timestamp hoặc raw URL.
- Phân biệt operation khác nhau nếu lifecycle/semantics khác nhau.
- Không đổi tên tùy tiện vì dashboard, alert và trace search có thể phụ thuộc tên.

Ví dụ:

| Operation | Observation name đề xuất |
| --- | --- |
| Tìm đơn hàng | orders.lookup |
| Tạo đơn hàng | orders.create |
| Xác nhận thanh toán | payment.authorize |
| Gửi message | orders.message.publish |
| Xử lý message | orders.message.process |

Tránh tạo tên theo Java method name một cách máy móc nếu method name có thể đổi do refactor dù operation semantics không đổi. Observation name là telemetry contract; chọn tên theo operation mà người vận hành cần hiểu.

## 4. Tạo Observation và kiểm thử tên trực tiếp

Micrometer Observation API cho phép tạo observation với tên tường minh. Có thể đăng ký một test handler để ghi nhận lifecycle và context:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.Observation.Context;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ObservationNameTest {
    @Test
    void usesStableOperationName() {
        ObservationRegistry registry = ObservationRegistry.create();
        List<String> observedNames = new ArrayList<>();

        registry.observationConfig().observationHandler(
            new ObservationHandler<Context>() {
                @Override
                public boolean supportsContext(Context context) {
                    return true;
                }

                @Override
                public void onStart(Context context) {
                    observedNames.add(context.getName());
                }
            }
        );

        Observation.createNotStarted("orders.lookup", registry)
            .observe(() -> "order-result");

        assertThat(observedNames).containsExactly("orders.lookup");
    }
}
```

Đây là ví dụ test trực tiếp ở tầng Observation. Import và generic types có thể cần điều chỉnh theo Micrometer version trong Spring Boot BOM. Handler chỉ capture tên lúc bắt đầu; trong test thực tế có thể capture thêm low-cardinality key-values và lifecycle callbacks.

Ưu điểm của cách này là test không cần Prometheus, OTLP collector hoặc tracing backend. Nó xác minh instrumentation contract trước khi handler chuyển dữ liệu sang từng signal.

## 5. Kiểm thử convention thay vì hardcode tên ở mọi nơi

Khi tên hoặc metadata phụ thuộc context, Micrometer cho phép dùng ObservationConvention để chuẩn hóa cách đặt tên và tags. Convention nên là nơi tập trung naming policy thay vì lặp logic ở nhiều controller/service.

Ví dụ convention:

```java
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.Observation.Context;

class OrderObservationConvention
        implements ObservationConvention<Context> {
    @Override
    public boolean supportsContext(Context context) {
        return context instanceof OrderObservationContext;
    }

    @Override
    public String getName() {
        return "orders.process";
    }
}

class OrderObservationContext extends Context {
    // Add only explicitly approved operation metadata.
}
```

Đây là skeleton minh họa. Trong ứng dụng thực, context type, convention registration và API cụ thể phụ thuộc instrumentation module/version. Convention có thể cung cấp tên và low-cardinality/high-cardinality key-values theo contract.

Test convention trực tiếp:

```java
@Test
void conventionUsesExpectedName() {
    OrderObservationConvention convention =
        new OrderObservationConvention();
    OrderObservationContext context =
        new OrderObservationContext();

    assertThat(convention.supportsContext(context)).isTrue();
    assertThat(convention.getName()).isEqualTo("orders.process");
}
```

Nếu convention hỗ trợ nhiều context types, cần test cả positive và negative cases. Một convention không nên nhận nhầm context của operation khác.

## 6. Test custom low-cardinality tags cùng tên

Tên ổn định là điều kiện cần nhưng chưa đủ. Tags cũng phải giữ cardinality hữu hạn:

```java
Observation.createNotStarted("orders.lookup", registry)
    .lowCardinalityKeyValue("order.channel", "web")
    .lowCardinalityKeyValue("outcome", "success")
    .observe(() -> orderService.find(orderId));
```

Test nên xác minh:

- Observation name đúng contract.
- Key names nhất quán.
- Channel/outcome thuộc tập giá trị đã định nghĩa.
- Order ID/customer ID không xuất hiện trong low-cardinality tags.
- Không có raw URL, query string hoặc exception message trong tags.

Có thể capture context trong test handler và assert key-values:

```java
// Pseudocode:
// Capture context.getName() at onStart.
// Capture context.getLowCardinalityKeyValues() at onStart/onStop.
// Assert name == "orders.lookup".
// Assert order.channel belongs to {"web", "mobile", "partner"}.
// Assert no key/value contains the request's order ID.
```

Pseudocode minh họa ý tưởng; dùng API key-values của Micrometer version thực tế. Không kiểm thử bằng cách chỉ assert tên vì tag cardinality có thể gây vấn đề ngay cả khi tên ổn định.

## 7. Test name khi dùng @Observed

Nếu ứng dụng dùng @Observed, tên khai báo trên annotation cần được xác minh qua AOP integration:

```java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {
    @Observed(name = "orders.lookup")
    public OrderView lookup(String orderId) {
        return new OrderView(orderId);
    }
}
```

Test cần lấy bean từ Spring ApplicationContext và gọi qua proxy để annotation interceptor thực sự chạy. Tạo object bằng new OrderQueryService() sẽ bỏ qua Spring AOP và không chứng minh annotation hoạt động.

```java
// Pseudocode:
// @SpringBootTest with observation annotation aspect enabled.
// Register a test ObservationHandler that captures context.getName().
// Autowire OrderQueryService from the application context.
// Call lookup("test-order-1") through the injected bean.
// Assert the captured observation name is exactly "orders.lookup".
```

Kiểm tra thêm self-invocation nếu method được gọi từ một method khác trong cùng bean. Proxy-based AOP thường không intercept lời gọi nội bộ qua this.

## 8. Test name của HTTP server observations

HTTP server instrumentation thường dùng route/method conventions do framework cung cấp. Tên/metadata của HTTP observations có thể khác custom application observations.

Khi test HTTP route:

1. Gửi request qua MockMvc/WebTestClient hoặc embedded server phù hợp.
2. Capture observations từ registry/test handler.
3. Xác minh route template được dùng thay vì raw URI có ID.
4. Xác minh method/status/outcome theo convention của stack.
5. Phân biệt server observation với method-level observation nếu cả hai cùng xuất hiện.

Không assert một tên HTTP server observation chung cho mọi Spring Boot version mà không kiểm tra dependency/version. HTTP instrumentation conventions có thể thay đổi theo framework và Micrometer release.

## 9. Test mapping sang meter name

Nếu metric naming là contract, cần test với registry cụ thể. SimpleMeterRegistry giúp kiểm tra meter được đăng ký mà không cần backend.

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ObservationMeterNameTest {
    @Test
    void recordsTimerForExpectedOperation() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        // Register the Micrometer meter handler appropriate to the
        // application's Micrometer version, then observe the operation.
        Observation.createNotStarted("orders.lookup", observations)
            .observe(() -> "ok");

        // Assert the meter name produced by the configured convention.
        assertThat(meters.getMeters()).isNotNull();
    }
}
```

Đoạn code trên là skeleton: chỉ tạo SimpleMeterRegistry chưa tự đăng ký Observation-to-Meter handler, nên assertion cuối chưa chứng minh timer đã được ghi. Test hoàn chỉnh phải đăng ký handler phù hợp, thường được cung cấp qua Micrometer Observation/metrics integration của ứng dụng, rồi assert meter name, count và tags thực tế.

Không nên hardcode tên meter chỉ dựa vào observation name. Timer convention có thể thêm suffix hoặc chuẩn hóa tên. Đọc meter names từ registry trong test để xác nhận contract của version đang dùng.

## 10. Test mapping sang span name

Nếu ứng dụng dùng Micrometer Tracing bridge hoặc OpenTelemetry, có thể test span name với in-memory/test exporter. Mục tiêu là xác minh bridge chuyển observation thành span đúng tên và context:

- Span name đúng hoặc được convention mapping đúng.
- Trace ID được giữ qua parent/child operations.
- Error/status được ghi theo semantics.
- Low/high-cardinality attributes được map đúng.
- Không tạo duplicate spans cho cùng operation.

Test Observation handler không thay thế test exporter. Nó chỉ xác minh tên ở tầng Observation. Test exporter mới xác minh payload span sau processor/bridge.

## 11. Kiểm thử tên không chứa dữ liệu động

Tạo nhiều invocation với identifiers khác nhau và xác minh tên vẫn giống nhau:

```java
@Test
void operationNameDoesNotDependOnOrderId() {
    List<String> names = new ArrayList<>();

    observeLookup("order-100", names);
    observeLookup("order-200", names);
    observeLookup("order-300", names);

    assertThat(names).containsExactly(
        "orders.lookup",
        "orders.lookup",
        "orders.lookup"
    );
}
```

Helper observeLookup trong test thật sẽ tạo Observation bằng tên cố định và capture context name trong handler. Kiểm thử này ngăn việc ai đó vô tình nối order ID vào observation name khi refactor.

Không chỉ kiểm tra số lượng tên khác nhau. Cần assert chính xác tên contract và kiểm tra các identifiers không xuất hiện trong names/tags dùng cho metrics.

## 12. Test exception và lifecycle

Observation name phải giữ nguyên dù operation thành công hay thất bại. Kiểm tra cả start, error và stop:

```java
@Test
void keepsNameWhenOperationThrows() {
    List<String> names = new ArrayList<>();
    ObservationRegistry registry = registryCapturingNames(names);

    assertThatThrownBy(() ->
        Observation.createNotStarted("payment.authorize", registry)
            .observe(() -> {
                throw new IllegalStateException("declined");
            })
    ).isInstanceOf(IllegalStateException.class);

    assertThat(names).containsExactly("payment.authorize");
}
```

registryCapturingNames là helper test cần triển khai bằng ObservationHandler. Không assert exception message là tag; message có thể chứa dữ liệu không an toàn. Test bổ sung có thể xác minh handler nhận onError và onStop đúng lifecycle.

## 13. Naming contract và version changes

Observation names thường được dùng bởi dashboard, alert, trace search và runbooks. Đổi tên có thể làm dashboard cũ không còn dữ liệu hoặc chia lịch sử thành hai series.

Khi đổi tên:

1. Xác định lý do và semantics thay đổi.
2. Tìm consumers của tên cũ trong dashboard/alerts/queries.
3. Quyết định alias/dual publishing nếu cần migration.
4. Cập nhật tests trước khi merge.
5. Cập nhật dashboards và runbooks theo rollout plan.
6. Theo dõi cả tên cũ/mới trong giai đoạn chuyển đổi nếu pipeline hỗ trợ.

Không đổi tên chỉ để khớp Java method rename nếu operation semantics vẫn như cũ. Ngược lại, nếu semantics thay đổi thực sự, dùng tên mới có thể giúp phân biệt dữ liệu trước và sau.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không capture được observation | Handler chưa đăng ký hoặc supportsContext trả false | Kiểm tra registry và handler matching |
| @Observed không tạo tên như mong đợi | AOP aspect thiếu hoặc gọi không qua proxy | Lấy bean từ context và kiểm tra proxy |
| Meter name khác observation name | Meter convention thêm suffix/normalize | Assert registry meter name ở integration test |
| Span name khác meter name | Tracing bridge dùng convention riêng | Kiểm tra span exporter output |
| Nhiều time series cho cùng operation | Tên hoặc tags chứa identifiers động | Capture names/tags với nhiều input |
| HTTP route name chứa ID | Dùng raw URI thay vì route template | Kiểm tra server observation convention |
| Test pass nhưng production name khác | Test chỉ dùng NOOP/simple handler | Thêm test với registry/bridge production tương ứng |
| Tên thay đổi sau nâng dependency | Convention/version đổi | Pin contract tests và review migration |
| Duplicate observation | Instrumentation ở nhiều tầng cùng tên/lifecycle | Xác định operation boundary và ownership |

## 15. Tình huống thực tế: refactor làm tăng metric cardinality

**Bối cảnh giả định:** Sau một lần refactor, dashboard xuất hiện hàng nghìn meter names như orders.lookup.1001, orders.lookup.1002. Memory của metrics registry tăng và Prometheus có quá nhiều series.

Quy trình:

1. **Capture names:** dùng test ObservationHandler ghi lại context name với nhiều order IDs.
2. **Tìm nguồn động:** xác định annotation/convention đang nối ID vào observation name.
3. **Chuẩn hóa:** đổi về tên cố định orders.lookup.
4. **Chuyển metadata:** nếu cần order ID cho điều tra, đưa vào log field hoặc trace attribute được kiểm soát, không dùng metric name/tag.
5. **Regression test:** chạy nhiều inputs khác nhau và assert chỉ có một operation name cùng tập low-cardinality tags hữu hạn.
6. **Metric verification:** kiểm tra registry/Prometheus series count sau thay đổi.
7. **Dashboard migration:** cập nhật queries nếu tên cũ đã được dùng trong dashboard/alert.

Tên ổn định giúp registry tổng hợp measurements cùng operation thay vì tạo một meter cho từng entity.

## 16. Bài tập tự kiểm tra

**Bài 1.** Observation name nên đại diện cho operation hay một lần thực thi?

*Gợi ý:* Đại diện cho loại operation; không chứa request/order/customer ID.

**Bài 2.** Test ObservationHandler chứng minh điều gì?

*Gợi ý:* Nó xác minh tên/context tại tầng Observation, không chứng minh exporter hoặc backend đã nhận span.

**Bài 3.** Vì sao meter name có thể khác observation name?

*Gợi ý:* Meter convention có thể thêm suffix, chuẩn hóa hoặc map sang một loại meter cụ thể.

**Bài 4.** Làm sao test @Observed được intercept?

*Gợi ý:* Gọi bean qua ApplicationContext proxy và capture tên bằng test ObservationHandler.

**Bài 5.** Vì sao cần test tên với nhiều IDs?

*Gợi ý:* Để phát hiện tên động gây cardinality tăng theo số entity/request.

**Bài 6.** Khi nào cần test span name bằng exporter?

*Gợi ý:* Khi tracing bridge/span naming là contract cần bảo vệ; Observation handler không xác minh bước mapping đó.

**Bài 7.** Có nên đổi observation name khi chỉ đổi Java method name?

*Gợi ý:* Không nhất thiết; tên telemetry gắn với operation semantics và dashboards, không chỉ tên method.

**Bài 8.** Khi đổi tên observation đang được dashboard sử dụng, cần làm gì?

*Gợi ý:* Lập migration cho queries/alerts, cập nhật contract tests và theo dõi dữ liệu cũ/mới.

## 17. Ghi nhớ

- Observation name là định danh ổn định của operation; không gắn request ID, entity ID, timestamp hoặc raw URL vào tên.
- Kiểm thử tên trực tiếp bằng ObservationHandler để xác minh contract ở tầng instrumentation mà không cần backend.
- Observation name, meter name và span name có thể khác nhau do conventions/handlers; test ở đúng tầng cần bảo vệ.
- Dùng ObservationConvention khi cần tập trung naming/tags; test cả context được hỗ trợ và context bị từ chối.
- Với @Observed, gọi bean qua Spring proxy; test self-invocation và các giới hạn AOP nếu có.
- Kiểm thử low-cardinality tags cùng tên; tên ổn định không đủ nếu tags vẫn chứa identifiers động.
- Dùng registry integration test cho meter names và in-memory/test exporter cho span names/attributes.
- Xem observation names là telemetry contract: thay đổi cần regression tests và cập nhật dashboards/alerts/runbooks.
