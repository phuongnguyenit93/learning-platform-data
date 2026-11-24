# Phân loại dữ liệu trong tag, key-value, mô tả lỗi và ngữ cảnh quan sát

## Mục tiêu

Metrics, traces và logs giúp tìm hiểu trạng thái của ứng dụng, nhưng chúng cũng có thể mang theo dữ liệu nghiệp vụ, dữ liệu cá nhân hoặc bí mật vận hành. Một tag tưởng như vô hại có thể chứa email, token hoặc mã khách hàng nếu giá trị được lấy trực tiếp từ request. Một exception message có thể chứa SQL, URL đầy đủ hoặc nội dung đầu vào. Một trace attribute có cardinality cao vẫn có thể làm lộ dữ liệu dù nó không được xuất thành metric.

Vì vậy, instrumentation Micrometer cần hai quyết định độc lập:

- **Dữ liệu nào được phép ghi?** Đây là quyết định phân loại và bảo vệ dữ liệu.
- **Dữ liệu nào phù hợp với từng tín hiệu?** Đây là quyết định về cardinality, khả năng truy vấn, chi phí và mục đích sử dụng.

Low cardinality không đồng nghĩa với dữ liệu an toàn. High cardinality không đồng nghĩa với dữ liệu bí mật. Việc một key chỉ xuất hiện trong trace thay vì metric cũng không làm nó tự động được phép thu thập.

Sau bài này, bạn có thể:

- Phân loại dữ liệu trước khi đưa vào meter tags, Observation key-values hoặc Context.
- Phân biệt low-cardinality và high-cardinality với mức độ nhạy cảm của dữ liệu.
- Chuẩn hóa giá trị tag thành tập hữu hạn.
- Ghi nhận lỗi mà không đưa message, payload hoặc thông tin nhạy cảm vào metrics.
- Kiểm soát exception message, stacktrace, log fields và baggage.
- Hiểu giới hạn của ObservationFilter và MeterFilter trong bảo vệ dữ liệu.
- Thiết lập quy tắc kiểm thử và rà soát telemetry trước khi phát hành.

## Hai trục cần đánh giá riêng

### Cardinality

Cardinality mô tả số lượng giá trị hoặc tổ hợp giá trị có thể xuất hiện cho một dimension:

- Low cardinality: tập giá trị nhỏ, có giới hạn và được kiểm soát, ví dụ HTTP method, outcome, payment method hoặc deployment region.
- High cardinality: số giá trị lớn hoặc không thể dự đoán, ví dụ request ID, user ID, URL đầy đủ hoặc message ID.

Micrometer Observation phân loại KeyValues thành hai nhóm:

- Low-cardinality key-values được dùng làm metric tags; tracing integration cũng có thể đưa chúng vào span.
- High-cardinality key-values không được DefaultMeterObservationHandler đưa vào meter tags; tracing integration có thể xuất chúng vào span.

Quy tắc này giúp tránh tạo hàng triệu time series trong backend metrics. Nó không phải chính sách bảo mật.

Trong đó, DefaultMeterObservationHandler chỉ dùng low-cardinality key-values làm meter tags. Tracing handler có thể xuất metadata của Observation vào span; Spring Boot mô tả low-cardinality values được dùng cho metrics và traces, còn high-cardinality values chỉ dành cho traces. Phạm vi thực tế phụ thuộc handler và integration được đăng ký, vì vậy hãy kiểm tra cả cấu hình Micrometer Tracing thay vì suy luận chỉ từ meter registry.

### Mức độ nhạy cảm

Mức độ nhạy cảm phải dựa trên chính sách dữ liệu của tổ chức và mục đích xử lý. Một cách phân loại minh họa:

| Nhóm | Ví dụ | Cách xử lý telemetry |
|---|---|---|
| Public | Tên service công khai, phiên bản phát hành | Có thể ghi nếu phục vụ vận hành |
| Internal | Environment, region, tên operation, loại worker | Chỉ ghi trong hệ thống telemetry nội bộ được phép |
| Confidential | Tenant reference, customer reference, mã giao dịch | Chỉ ghi khi có mục đích, kiểm soát truy cập và thời hạn lưu phù hợp; ưu tiên mã giả danh |
| Restricted | Password, access token, private key, session cookie, payment credential, dữ liệu xác thực | Không đưa vào metrics, traces, logs, baggage hoặc Observation Context |

Đây là ví dụ để thiết kế quy tắc; hãy ánh xạ các nhóm trên với chính sách phân loại dữ liệu chính thức của tổ chức.

### Ma trận cardinality và độ nhạy cảm

| Dữ liệu | Cardinality thường gặp | Độ nhạy cảm có thể có | Quyết định |
|---|---|---|---|
| HTTP method | Thấp | Thấp | Phù hợp làm metric tag |
| Outcome success/error | Thấp | Thấp | Phù hợp làm metric tag |
| Route template | Thấp hoặc hữu hạn | Thường thấp | Phù hợp nếu không chứa dữ liệu động |
| Raw URL/query string | Cao | Có thể cao | Không dùng làm metric tag; rà soát trước khi đưa vào trace |
| User ID | Cao | Confidential hoặc PII | Không dùng làm metric tag; chỉ ghi trace/log khi được phê duyệt và cần thiết |
| Access token | Cao | Restricted | Không thu thập |
| Exception class | Thường hữu hạn | Thường thấp | Có thể dùng làm error type nếu đã chuẩn hóa |
| Exception message | Không ổn định | Có thể chứa dữ liệu nhạy cảm | Không đưa nguyên văn vào metric tag; kiểm soát trước khi ghi log/trace |
| Stacktrace | Nhiều nội dung động | Có thể chứa dữ liệu nội bộ hoặc bí mật | Chỉ ghi khi cần, có chính sách truy cập và redaction phù hợp |

Một giá trị có cardinality thấp vẫn có thể nhạy cảm. Ví dụ, một tag payment.method chỉ có bốn giá trị nhưng không nên được xuất nếu quy định dữ liệu của tổ chức cấm thu thập thông tin về phương thức thanh toán trong telemetry.

## Các vị trí dữ liệu có thể đi vào Micrometer

Thông tin quan sát có thể xuất hiện ở nhiều lớp:

| Vị trí | Cách đưa dữ liệu vào | Rủi ro |
|---|---|---|
| Meter tag | Counter, Timer, Gauge, DistributionSummary builder | Cardinality và dữ liệu nhạy cảm trong time series |
| Observation low-cardinality key-value | lowCardinalityKeyValue() | Được đưa vào metrics và traces |
| Observation high-cardinality key-value | highCardinalityKeyValue() | Có thể xuất trong span và bị lưu trữ lâu |
| Observation.Context | put(), field của custom Context | Handler hoặc filter có thể đọc và xuất dữ liệu |
| Error | Observation.error(exception) | Handler có thể ghi exception metadata |
| Description | Meter builder description | Có thể xuất trong scrape hoặc metadata backend |
| Log fields | Structured logging, MDC | Dữ liệu có thể được lập chỉ mục và tìm kiếm |
| Trace baggage | W3C Baggage hoặc tracing API | Có thể được truyền sang service khác |

Không có vị trí nào tự động an toàn chỉ vì nó không phải metric tag. Hãy xem xét toàn bộ đường đi từ nguồn đến exporter, collector, backend và người có quyền truy cập.

## Thiết kế meter tag an toàn

### Chỉ dùng giá trị có tập hữu hạn

Giá trị tag nên được ánh xạ từ input bên ngoài sang một tập giá trị được kiểm soát. Ví dụ, payment method chỉ cho phép card, bank_transfer, wallet và other:

~~~java
import java.util.Locale;
import java.util.Set;

public final class TelemetryValues {
    private static final Set<String> PAYMENT_METHODS =
            Set.of("card", "bank_transfer", "wallet");

    private TelemetryValues() {
    }

    public static String paymentMethod(String rawValue) {
        if (rawValue == null) {
            return "other";
        }

        String normalized = rawValue.toLowerCase(Locale.ROOT);
        return PAYMENT_METHODS.contains(normalized)
                ? normalized
                : "other";
    }
}
~~~

Đăng ký meter bằng giá trị đã chuẩn hóa:

~~~java
Counter.builder("business.payment.attempts")
        .tag("payment.method", TelemetryValues.paymentMethod(inputMethod))
        .tag("outcome", "attempt")
        .register(registry)
        .increment();
~~~

Không gắn raw input vào meter rồi hy vọng backend sẽ tự giới hạn số series. Chuẩn hóa tại nơi tạo telemetry giúp mọi exporter nhận cùng một giá trị đã được kiểm soát.

### Dùng route template thay cho raw URL

Với HTTP server metrics, route template như /orders/{orderId} phù hợp hơn raw path như /orders/918273. Query string có thể chứa email, search term, access token hoặc thông tin nghiệp vụ; không đưa URL đầy đủ vào metric tag.

Nên dùng các chiều có ý nghĩa và hữu hạn:

| Tag | Giá trị phù hợp |
|---|---|
| method | GET, POST, PUT, DELETE |
| outcome | SUCCESS, CLIENT_ERROR, SERVER_ERROR |
| status | 2xx, 3xx, 4xx, 5xx |
| uri | /orders/{orderId}, /payments/{paymentId} |

Nếu framework cung cấp route template, hãy dùng giá trị đó. Nếu route chưa được phân giải, dùng nhóm fallback như UNKNOWN hoặc NOT_FOUND thay vì raw path.

### Không đưa định danh riêng vào metric tag

Các giá trị sau không phù hợp làm metric tag:

- request ID, trace ID, span ID.
- user ID, customer ID, tenant ID nếu mỗi khách hàng tạo một series.
- order ID, invoice ID, payment ID, message ID.
- email, phone number, IP address hoặc session ID.
- file path, object key, raw SQL hoặc URL đầy đủ.

Khi cần tìm một request hoặc giao dịch cụ thể, dùng trace ID hoặc correlation ID trong log/trace theo chính sách truy cập. Metrics nên mô tả xu hướng tổng thể qua những dimension có giới hạn.

## Phân loại Observation key-values

Spring Framework và Micrometer Observation dùng KeyValues để truyền metadata từ instrumentation tới handler. Convention thường là nơi phù hợp để định nghĩa key và giá trị mặc định của một loại Observation.

Ví dụ:

~~~java
Observation.createNotStarted("payment.authorize", observationRegistry)
        .lowCardinalityKeyValue("payment.method", "card")
        .lowCardinalityKeyValue("payment.outcome", "success")
        .highCardinalityKeyValue("payment.reference", approvedReference)
        .observe(() -> paymentService.authorize(command));
~~~

Ví dụ này chỉ phù hợp khi payment.reference là mã tham chiếu đã được phê duyệt để ghi trong trace. Nó không nên là số thẻ, access token, customer email hoặc dữ liệu xác thực. Nếu không cần điều tra theo reference trong trace, hãy bỏ key này.

High-cardinality key-value không được đưa vào metric tag bởi DefaultMeterObservationHandler, nhưng nó vẫn có thể xuất hiện trong span. Trace backend có thể được nhiều người truy cập, được export sang hệ thống khác hoặc lưu trong thời gian dài. Vì vậy, chỉ dùng high cardinality khi có mục đích và quyền xử lý rõ ràng.

### Observation.Context không phải vùng lưu bí mật

Observation.Context có thể chứa request, response, exception và field riêng của instrumentation. Handler, convention, filter hoặc tracing bridge có thể đọc dữ liệu trong Context. Việc gọi context.put("secret", value) không làm giá trị trở thành private.

Chỉ đưa dữ liệu cần cho instrumentation vào Context. Không lưu password, token, credential, request body hoặc object nghiệp vụ đầy đủ nếu handler không cần chúng.

Nếu chỉ cần một giá trị đã phân loại, hãy lưu một enum hoặc mã trạng thái đã chuẩn hóa thay vì toàn bộ object.

### Convention và filter có vai trò khác nhau

- ObservationConvention định nghĩa tên Observation và key-values phù hợp với loại Context.
- ObservationFilter biến đổi Context khi Observation dừng, trước callback onStop của handler.
- ObservationHandler tạo metrics, spans hoặc hành vi telemetry khác từ lifecycle.
- ObservationPredicate quyết định Observation có được tạo hay không.

Hãy chuẩn hóa dữ liệu ngay trong convention hoặc instrumentation trước khi thêm vào Observation. Filter có thể là lớp hậu xử lý, nhưng chạy muộn: handler đã nhận onStart, event hoặc onError trước đó có thể đã tiêu thụ dữ liệu.

## Chuẩn hóa lỗi và exception metadata

### Dùng error category có tập giá trị nhỏ

Dashboard thường cần biết lỗi thuộc nhóm nào:

- timeout
- dependency_unavailable
- rejected
- validation
- rate_limited
- internal

Đây là các category có thể kiểm soát. Chúng phù hợp hơn exception message hoặc mã lỗi tùy ý từ hệ thống ngoài.

Ví dụ chuẩn hóa exception:

~~~java
import java.util.concurrent.TimeoutException;

public final class ErrorCategories {
    private ErrorCategories() {
    }

    public static String classify(Throwable error) {
        if (error instanceof TimeoutException) {
            return "timeout";
        }
        if (error instanceof DependencyUnavailableException) {
            return "dependency_unavailable";
        }
        if (error instanceof PaymentDeclinedException) {
            return "rejected";
        }
        if (error instanceof IllegalArgumentException) {
            return "validation";
        }
        return "internal";
    }
}
~~~

Có thể ghi category thành low-cardinality key-value:

~~~java
Observation observation = Observation.createNotStarted(
        "payment.authorize", observationRegistry);
observation.start();
try (Observation.Scope scope = observation.openScope()) {
    try {
        return gateway.authorize(command);
    } catch (RuntimeException exception) {
        observation.lowCardinalityKeyValue(
                "error.category",
                ErrorCategories.classify(exception)
        );
        observation.error(exception);
        throw exception;
    }
} finally {
    observation.stop();
}
~~~

error.category phục vụ metric và phân tích tổng hợp. observation.error(exception) cung cấp exception cho handler; exporter có thể ghi exception type, message hoặc stacktrace tùy cấu hình. Hãy rà soát handler và exporter trước khi cho phép exception đi vào trace.

Không dùng error.message làm metric tag. Không đưa raw error code từ provider vào tag nếu tập mã không được kiểm soát. Hãy ánh xạ mã ngoài sang category nội bộ.

### Exception message có thể chứa dữ liệu nhạy cảm

OpenTelemetry semantic conventions cảnh báo exception.message có thể chứa dữ liệu nhạy cảm. Message có thể bao gồm:

- SQL query và giá trị bind parameter.
- URL hoặc query string chứa token.
- Email, số điện thoại hoặc dữ liệu người dùng.
- Nội dung payload hoặc message broker.
- File path nội bộ, tên bucket hoặc object key.
- Request header hoặc credential được chèn vào message bởi thư viện.

Không giả định exception message đã được làm sạch. Nếu cần message để điều tra, hãy áp dụng redaction ở nơi tạo hoặc chuyển đổi exception trước khi export, giới hạn quyền truy cập và thời gian lưu. Nếu không thể kiểm soát chắc chắn, chỉ ghi exception type và error category.

### Stacktrace cũng cần được kiểm soát

Stacktrace có thể tiết lộ tên package nội bộ, đường dẫn file, tên host, SQL, dữ liệu nằm trong exception message hoặc thông tin từ thư viện bên thứ ba. Không đưa stacktrace vào metric tag. Với logs và spans, chỉ bật khi có mục đích vận hành rõ ràng và có chính sách truy cập phù hợp.

Nếu cần lưu đầy đủ exception cho debugging, cân nhắc lưu trong log backend có kiểm soát truy cập chặt hơn, rồi liên kết với trace bằng trace ID. Không nhân bản toàn bộ exception vào metrics.

### Phân biệt exception đã xử lý và lỗi thực sự thoát khỏi thao tác

Không phải mọi exception được tạo ra đều có nghĩa operation thất bại. Một exception có thể được bắt và chuyển thành kết quả nghiệp vụ hợp lệ, ví dụ cache miss hoặc fallback sang nguồn dữ liệu khác.

Hãy phân biệt:

- Operation result: success, fallback, rejected hoặc failed.
- Exception event: exception đã xảy ra trong quá trình thực thi.
- Error status: trạng thái lỗi của span theo semantic convention và chính sách instrumentation.

Đừng tự động gắn outcome=error cho mọi exception nếu ứng dụng đã xử lý exception thành công. Ngược lại, không che giấu lỗi thật chỉ vì method cuối cùng trả về một response HTTP hợp lệ.

## Mô tả meter và metadata tĩnh

Meter description giúp người vận hành hiểu đại lượng được đo. Description nên là câu mô tả tĩnh, không chứa dữ liệu runtime:

~~~java
Timer.builder("payment.authorization.duration")
        .description("Thời gian xử lý yêu cầu ủy quyền thanh toán")
        .tag("payment.method", "card")
        .register(registry);
~~~

Không tạo description từ URL, customer name, exception message hoặc request input. Description có thể được exporter công bố cùng metric metadata và được lưu trong backend.

Tên metric và tag key cũng không nên chứa dữ liệu động. Dùng một tên ổn định cho một đại lượng và dùng tag có tập giá trị hữu hạn cho các dimension được phép.

## Log fields, MDC và correlation ID

Logs thường phù hợp hơn metrics để lưu chi tiết theo từng sự kiện, nhưng logs cũng có thể chứa dữ liệu nhạy cảm và thường được lập chỉ mục.

Một log event có cấu trúc có thể chứa:

- operation: payment.authorize
- outcome: rejected
- error.category: rejected
- trace_id: mã liên kết với trace nếu chính sách cho phép
- duration_ms: thời gian xử lý

Không ghi nguyên request body, authorization header, cookie, token hoặc toàn bộ object nghiệp vụ. Nếu log cần một reference, dùng mã giả danh hoặc mã giao dịch đã được phê duyệt.

MDC thường lưu các giá trị theo thread. Khi dùng async executor, phải bảo đảm context propagation và cleanup đúng cách. Nếu không, correlation ID hoặc tenant của request trước có thể xuất hiện trong log của request sau.

Correlation ID có cardinality cao nhưng có thể hữu ích trong log/trace. Nó không nên là metric tag. Không chuyển correlation ID sang baggage hoặc service khác nếu không có mục đích và chính sách rõ ràng.

## Trace attributes và baggage

Trace span có thể mang high-cardinality attributes để điều tra một request cụ thể. Chỉ ghi những giá trị cần thiết:

- Dùng operation, destination type và outcome để phân tích chung.
- Dùng reference đã giả danh nếu cần tìm một đối tượng cụ thể.
- Tránh raw URL, query string, payload, SQL parameter và user input.
- Không ghi password, token, cookie, private key hoặc credential.

Baggage khác span attribute: baggage được thiết kế để truyền qua ranh giới service. Một key baggage có thể được đưa vào HTTP header hoặc message header và tiếp tục đi qua nhiều hệ thống. Vì vậy:

- Không đưa secret hoặc PII vào baggage.
- Chỉ cho phép một danh sách key cụ thể.
- Giới hạn kích thước và số lượng key/value.
- Không copy toàn bộ request headers hoặc MDC sang baggage.
- Xác minh downstream service có thực sự cần giá trị đó không.

Context Propagation trong một tiến trình không tự động đồng nghĩa với việc truyền baggage qua mạng. Micrometer Tracing propagator chịu trách nhiệm inject/extract trace context và baggage vào carrier. Hãy quản lý danh sách baggage fields ở cấu hình tracing riêng.

## Vì sao MeterFilter không thay thế phân loại dữ liệu?

MeterFilter có thể đổi tên meter, thêm hoặc loại tag, từ chối meter và giới hạn số giá trị tag. Ví dụ maximumAllowableTags giúp ngăn một meter tạo quá nhiều series.

Nhưng filter cardinality không phải data loss prevention:

- Giá trị nhạy cảm có thể đã được ghi vào registry trước khi giới hạn được kích hoạt.
- Một trong những giá trị đầu tiên được chấp nhận có thể chính là token hoặc email.
- Filter không bảo vệ trace attributes, logs, baggage hoặc exporter khác.
- Giới hạn số giá trị không làm giá trị đã được chấp nhận trở nên an toàn.

Chuẩn hóa và loại dữ liệu ngay tại nguồn trước khi tạo meter. Dùng MeterFilter như lớp bảo vệ bổ sung cho cardinality và naming.

## Vì sao ObservationFilter không thay thế redaction tại nguồn?

ObservationFilter chạy khi Observation dừng, trước onStop. Handler có thể đã nhận dữ liệu ở onStart, onEvent hoặc onError. Vì vậy, filter xóa key ở cuối không đảm bảo dữ liệu chưa từng được ghi vào span, log hoặc counter.

Nếu dữ liệu không được phép xuất hiện trong telemetry:

1. Không thêm dữ liệu đó vào Observation Context.
2. Không đưa dữ liệu vào exception message nếu có thể tránh.
3. Chuẩn hóa hoặc loại giá trị trước khi tạo KeyValue.
4. Kiểm tra instrumentation và handler bên thứ ba.
5. Dùng filter như lớp hậu xử lý cho những key hợp lệ cần được điều chỉnh.

Không dùng ObservationFilter để che giấu việc thu thập dữ liệu không cần thiết ở upstream.

## Ví dụ: instrumentation thanh toán với dữ liệu đã phân loại

Ví dụ sau chỉ ghi method và outcome có tập giá trị hữu hạn. Exception được đánh dấu trên Observation để handler xử lý, nhưng raw message và payment reference không được thêm vào key-value:

~~~java
public AuthorizationResult authorize(PaymentCommand command) {
    String method = TelemetryValues.paymentMethod(command.paymentMethod());

    Observation observation = Observation.createNotStarted(
                    "payment.authorize", observationRegistry)
            .lowCardinalityKeyValue("payment.method", method);

    try {
        return observation.observe(() -> gateway.authorize(command));
    } catch (PaymentDeclinedException exception) {
        // Category hữu hạn có thể được ghi ở metric riêng hoặc convention.
        rejectedPayments.increment();
        throw exception;
    }
}
~~~

Trong hệ thống thực tế, không đưa toàn bộ PaymentCommand vào Observation.Context. Nếu gateway exception có thể chứa credential hoặc provider payload, hãy làm sạch message trước khi handler/exporter ghi exception. Nếu cần phân loại outcome trên cùng Observation, hãy cập nhật low-cardinality value ở thời điểm phù hợp trước khi stop và xác minh handler đọc giá trị ở callback nào.

## Kiểm thử dữ liệu được xuất

Unit test nên kiểm tra cả giá trị hợp lệ và input độc hại:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TelemetryValuesTest {

    @Test
    void keepsPaymentMethodWithinBoundedSet() {
        assertThat(TelemetryValues.paymentMethod("CARD")).isEqualTo("card");
        assertThat(TelemetryValues.paymentMethod("wallet")).isEqualTo("wallet");
        assertThat(TelemetryValues.paymentMethod("unknown-value")).isEqualTo("other");
        assertThat(TelemetryValues.paymentMethod(null)).isEqualTo("other");
    }
}
~~~

Với Observation, có thể xác minh low-cardinality key-value được đưa vào Timer và high-cardinality value không trở thành metric tag:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ObservationDataClassificationTest {

    @Test
    void onlyLowCardinalityValuesBecomeMetricTags() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meters).build());

        try {
            Observation.createNotStarted("payment.authorize", observations)
                    .lowCardinalityKeyValue("payment.method", "card")
                    .highCardinalityKeyValue("payment.reference", "ref-123")
                    .observe(() -> {
                    });

            Timer timer = meters.get("payment.authorize")
                    .tag("payment.method", "card")
                    .timer();

            assertThat(timer.count()).isEqualTo(1);
            assertThat(meters.find("payment.authorize")
                    .tag("payment.reference", "ref-123")
                    .timer()).isNull();
        } finally {
            meters.close();
        }
    }
}
~~~

Test này xác minh semantics cardinality của DefaultMeterObservationHandler. Nó không chứng minh high-cardinality value đã được redacted khỏi tracing. Muốn kiểm tra trace, cần test span exporter hoặc test ObservationHandler tương ứng và xác minh attribute thực tế được gửi đi.

### Kiểm thử log và exception redaction

Thêm test cho các trường hợp:

- Authorization header và cookie không xuất hiện trong log event.
- Exception message chứa email hoặc token được loại bỏ hoặc thay bằng thông điệp an toàn.
- Stacktrace chỉ được xuất theo chính sách đã chọn.
- Raw URL/query string không xuất hiện trong metric tag.
- Baggage chỉ chứa key trong allow-list.
- Không có user ID, request ID hoặc message ID trong metric labels.

Đừng chỉ kiểm tra object trước exporter. Kiểm tra payload cuối cùng sau khi handler, processor và exporter đã biến đổi dữ liệu.

## Quy trình phân loại dữ liệu trước khi phát hành

Với mỗi meter hoặc Observation mới:

1. Liệt kê key, nguồn dữ liệu và ví dụ giá trị thực tế.
2. Xác định mục đích vận hành của từng key.
3. Phân loại độ nhạy cảm theo chính sách tổ chức.
4. Ước lượng cardinality và số tổ hợp tag.
5. Chọn tín hiệu phù hợp: metrics, traces, logs hoặc không thu thập.
6. Chuẩn hóa giá trị thành enum hoặc nhóm hữu hạn khi có thể.
7. Xác định dữ liệu nào phải redaction tại nguồn.
8. Kiểm tra convention, handler, filter và exporter.
9. Kiểm thử payload cuối cùng với dữ liệu giả lập chứa secret/PII.
10. Xác minh quyền truy cập, retention và quy trình xóa dữ liệu ở backend.

Một bảng data contract nhỏ có thể giúp review:

| Key | Nguồn | Phân loại | Cardinality | Signal | Quy tắc |
|---|---|---|---|---|---|
| payment.method | Request enum | Internal | Thấp | Metrics, traces | Allow-list |
| payment.outcome | Kết quả xử lý | Internal | Thấp | Metrics, traces | Enum cố định |
| payment.reference | Hệ thống thanh toán | Confidential | Cao | Không mặc định | Chỉ pseudonymous trace khi được duyệt |
| exception.type | Runtime exception | Internal | Thấp/hữu hạn | Logs, traces | Chuẩn hóa wrapper |
| exception.message | Exception | Có thể confidential | Không ổn định | Không mặc định | Redact hoặc bỏ |
| authorization | HTTP header | Restricted | Cao | Không thu thập | Loại tại nguồn |

## Những lỗi thường gặp

**Đánh đồng high cardinality với dữ liệu an toàn.** High-cardinality key-value vẫn có thể được ghi vào trace và lộ PII hoặc bí mật.

**Dùng user ID làm metric tag.** Mỗi người dùng có thể tạo một time series. Dùng aggregate metrics và trace/log có kiểm soát khi cần điều tra.

**Ghi raw URL hoặc query string.** Route có thể chứa ID, token hoặc thông tin tìm kiếm. Dùng route template.

**Đưa exception message vào tag.** Message vừa có cardinality không giới hạn vừa có thể chứa dữ liệu nhạy cảm.

**Cho rằng exception type luôn an toàn.** Class name thường ít nhạy cảm hơn message, nhưng vẫn cần chuẩn hóa nếu có class động hoặc tên nội bộ không nên công bố.

**Đưa payload vào Observation.Context.** Handler có thể đọc và xuất Context. Chỉ lưu metadata tối thiểu.

**Dựa vào ObservationFilter để xóa secret.** Filter chạy ở stop; handler có thể đã tiêu thụ dữ liệu trước đó.

**Dùng MeterFilter như cơ chế bảo mật.** Giới hạn cardinality không loại bỏ PII hoặc secret đã được chấp nhận.

**Copy toàn bộ MDC hoặc headers sang baggage.** Baggage có thể truyền sang nhiều service và tạo thêm nơi lưu trữ dữ liệu.

**Cho rằng logs luôn an toàn hơn traces.** Logs thường được lập chỉ mục và có thể được chia sẻ rộng. Cả hai đều cần kiểm soát truy cập và retention.

**Chỉ test meter trong registry.** Dữ liệu có thể được thêm ở tracing handler hoặc exporter. Cần kiểm tra payload cuối cùng của từng signal.

## Checklist triển khai

1. Có danh sách key và data contract cho mỗi Observation.
2. Phân loại độ nhạy cảm riêng với cardinality.
3. Không đưa secret/restricted data vào bất kỳ signal nào.
4. Chỉ dùng low-cardinality values có tập hữu hạn cho metric tags.
5. Chỉ dùng high-cardinality trace attributes khi có mục đích và phê duyệt.
6. Dùng route template thay raw URL.
7. Chuẩn hóa error category và mã lỗi.
8. Rà soát exception.message và exception.stacktrace.
9. Giữ meter description tĩnh, không chứa dữ liệu runtime.
10. Không lưu object nghiệp vụ đầy đủ trong Observation.Context.
11. Giới hạn baggage keys, kích thước và phạm vi propagation.
12. Redact tại nguồn; không dựa vào filter chạy muộn.
13. Kiểm tra metrics, traces, logs và baggage sau exporter.
14. Xác minh access control, retention và quy trình xóa dữ liệu.

## Kết luận

Phân loại dữ liệu trong Micrometer cần xem xét cả cardinality lẫn độ nhạy cảm. DefaultMeterObservationHandler dùng low-cardinality key-values làm meter tags; tracing integration có thể xuất low và high-cardinality values vào span theo cấu hình. High cardinality không làm dữ liệu trở nên an toàn. Hãy chuẩn hóa tag tại nguồn, dùng error category hữu hạn, kiểm soát exception message và stacktrace, coi Observation.Context và baggage là dữ liệu có thể được xuất, đồng thời không dựa vào MeterFilter hoặc ObservationFilter để thay thế redaction. Kiểm thử payload cuối cùng của metrics, traces và logs giúp bảo đảm instrumentation vừa hữu ích cho vận hành vừa tuân thủ chính sách dữ liệu.

## Tài liệu tham khảo

- [Spring Framework - Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Observation Context, conventions và low/high-cardinality KeyValues.
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): cách Spring Boot dùng Micrometer Observation và phân phối low/high-cardinality tags.
- [Micrometer - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): handler lifecycle, meter tags và giới hạn cardinality.
- [OpenTelemetry - Exception Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/): exception type, message, stacktrace và cảnh báo message có thể chứa dữ liệu nhạy cảm.
- [OpenTelemetry - Semantic Conventions](https://opentelemetry.io/docs/specs/otel/semantic-conventions/): quy ước attributes và key names cho telemetry.
- [OpenTelemetry - How to Write Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/): ghi rõ khi attribute có thể chứa PII hoặc dữ liệu nhạy cảm.
