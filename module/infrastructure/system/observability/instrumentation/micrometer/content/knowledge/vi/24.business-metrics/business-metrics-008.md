# Chọn nhóm lỗi ổn định và gắn hướng dẫn diễn giải số liệu

Metrics nghiệp vụ chỉ có giá trị khi người đọc hiểu chính xác sự kiện nào được đếm, điều kiện nào được xem là thành công, và mỗi nhóm lỗi có ý nghĩa gì. Nếu một counter tăng vì mọi exception đều được gắn vào cùng một tag động, dashboard sẽ nhanh chóng có quá nhiều series nhưng vẫn không trả lời được lỗi nào cần xử lý trước. Nếu tag lưu nguyên thông điệp exception, mỗi request có thể tạo một giá trị mới và làm cardinality tăng không giới hạn.

Cách thiết kế tốt là phân loại lỗi ở ranh giới nghiệp vụ thành một tập nhóm ổn định, có định nghĩa và hành động diễn giải rõ ràng. Micrometer cho phép mô tả meter bằng description và base unit; tag thể hiện các chiều phân tích có miền giá trị hữu hạn. Phần giải thích chi tiết hơn nên nằm trong tài liệu metric contract, dashboard description hoặc runbook có phiên bản, thay vì biến tag thành nơi chứa thông điệp lỗi.

## Mục tiêu

Sau bài học, bạn có thể:

- Xây dựng taxonomy lỗi nghiệp vụ và kỹ thuật với tập giá trị ổn định.
- Phân biệt business rejection với lỗi kỹ thuật của hệ thống.
- Ánh xạ exception và mã lỗi bên ngoài thành nhóm lỗi có cardinality thấp.
- Chọn tag phù hợp cho outcome và error type.
- Gắn ý nghĩa, đơn vị, ranh giới đếm và cách diễn giải bằng meter description.
- Viết truy vấn tỷ lệ lỗi có mẫu số rõ ràng.
- Giữ chi tiết chẩn đoán trong log/trace và liên kết dashboard với runbook.
- Kiểm thử taxonomy, meter ID và nội dung mô tả.

## Vì sao phải phân nhóm lỗi trước khi ghi metrics?

Một ứng dụng có thể gặp nhiều exception khác nhau, nhưng không phải mỗi exception class đều cần trở thành một chuỗi metrics riêng. Ngược lại, nhiều exception class có thể biểu diễn cùng một nguyên nhân vận hành. Ví dụ, socket timeout, read timeout và timeout do HTTP client có thể cùng được phân loại thành `dependency_timeout` nếu hành động xử lý giống nhau.

Phân nhóm lỗi giúp trả lời những câu hỏi vận hành có ý nghĩa:

- Lỗi đến từ đầu vào không hợp lệ, quy tắc nghiệp vụ hay dependency?
- Nhóm lỗi nào đang tăng nhanh?
- Nhóm lỗi nào ảnh hưởng đến tỷ lệ thành công của một thao tác?
- Lỗi có cần retry, kiểm tra quota, xem lại hợp đồng API hay chuyển cho nhóm trực hệ thống?
- Một đợt tăng lỗi có liên quan đến deploy hoặc thay đổi dependency không?

Nếu chỉ ghi `exception=java.net.SocketTimeoutException` hoặc `message=Read timed out after 3021ms for request ...`, số liệu có thể bị chia nhỏ theo class wrapper, nội dung message, URL, ID và các giá trị ngẫu nhiên. Người vận hành phải tự gom các chuỗi đó lại mỗi lần truy vấn.

## Phân biệt outcome nghiệp vụ và error type

Không phải mọi kết quả không thành công đều là lỗi kỹ thuật. Một giao dịch thanh toán bị từ chối vì không đủ số dư có thể là quyết định nghiệp vụ hợp lệ. Một request bị từ chối do dữ liệu đầu vào không đáp ứng quy tắc cũng có thể là kết quả mong đợi của domain.

Nên tách ít nhất hai khái niệm:

- `outcome` mô tả kết quả của thao tác: `approved`, `declined` hoặc `failed`.
- `error.type` mô tả lớp lỗi khiến thao tác thất bại về mặt kỹ thuật hoặc vận hành, chẳng hạn `dependency_timeout` hay `dependency_unavailable`.

Với thao tác hoàn tất thành công, không gắn `error.type`. Với quyết định nghiệp vụ bị từ chối, ghi `outcome=declined` và một lý do nghiệp vụ có miền giá trị hữu hạn nếu cần phân tích. Chỉ dùng `error.type` khi thao tác kết thúc bằng lỗi theo định nghĩa metric contract.

OpenTelemetry semantic conventions cũng yêu cầu `error.type` có giá trị dự đoán được, cardinality thấp và được tài liệu hóa. Nếu một domain có mã lỗi riêng, hãy giữ mã đó ở thuộc tính domain-specific; `error.type` mô tả lớp lỗi ở mức tổng quát. Cách tách này giúp metric có thể liên kết với span/log mà không buộc mọi mã nghiệp vụ trở thành một taxonomy kỹ thuật.

| Kết quả | Ví dụ | outcome | error.type |
|---|---|---|---|
| Thành công | Payment gateway chấp thuận | approved | Không gắn |
| Từ chối nghiệp vụ | Không đủ số dư, thẻ hết hạn | declined | Không gắn nếu đây là quyết định nghiệp vụ bình thường |
| Lỗi dependency | Gateway timeout hoặc không kết nối được | failed | dependency_timeout / dependency_unavailable |
| Lỗi nội bộ | Lỗi bất ngờ trong xử lý | failed | internal_error |

Nếu hệ thống coi một business rejection là thất bại theo KPI, vẫn có thể tính tỷ lệ decline riêng. Hãy đặt tên truy vấn và dashboard rõ ràng để không trộn tỷ lệ decline với tỷ lệ lỗi kỹ thuật.

## Thiết kế taxonomy lỗi ổn định

Một taxonomy nên có số lượng nhóm vừa đủ để mỗi nhóm dẫn đến cách diễn giải hoặc hành động khác nhau. Nếu hai nhóm luôn được xử lý giống nhau, có thể chúng đang bị chia quá nhỏ. Nếu một nhóm chứa các nguyên nhân có cách khắc phục rất khác nhau, cần tách nhóm.

Ví dụ cho luồng thanh toán:

| error.type | Định nghĩa | Cách diễn giải và hướng xử lý |
|---|---|---|
| dependency_timeout | Dependency không phản hồi trong timeout đã cấu hình | Kiểm tra latency, timeout, retry và tình trạng dependency |
| dependency_unavailable | Không thể kết nối hoặc dependency báo không sẵn sàng | Kiểm tra health, network, circuit breaker và sự cố phía nhà cung cấp |
| invalid_upstream_response | Response không đúng schema hoặc không thể giải mã | Kiểm tra contract, phiên bản API và payload mẫu trong trace/log |
| rate_limited | Request bị giới hạn bởi quota hoặc rate limit | Kiểm tra quota, tốc độ gửi và chính sách backoff |
| internal_error | Lỗi nội bộ đã được nhận diện và phân loại trong code ứng dụng | Tra log/trace theo correlation ID và kiểm tra deploy gần nhất |
| unknown | Lỗi chưa được classifier nhận diện hoặc chưa có mapping | Điều tra, bổ sung mapping có kiểm soát; theo dõi tỷ lệ unknown |

Lý do nghiệp vụ nên có taxonomy riêng:

| payment.decline.reason | Ý nghĩa |
|---|---|
| insufficient_funds | Không đủ số dư hoặc hạn mức |
| card_expired | Thẻ đã hết hạn |
| risk_rejected | Quy tắc chống gian lận từ chối |
| issuer_declined | Tổ chức phát hành từ chối |
| other | Lý do không thuộc nhóm đã công bố |

Các giá trị này là ví dụ. Hãy dùng mã domain đã được thống nhất trong hợp đồng nghiệp vụ. Không dùng nguyên văn message từ provider làm giá trị tag.

### Tiêu chí cho một nhóm lỗi tốt

Một nhóm lỗi nên:

1. Có tên ổn định qua các lần deploy.
2. Có định nghĩa đủ rõ để hai nhóm phát triển phân loại giống nhau.
3. Có tập giá trị hữu hạn và được kiểm soát trong code.
4. Có ý nghĩa vận hành riêng, chẳng hạn retry, kiểm tra dependency hoặc điều tra logic nội bộ.
5. Không chứa dữ liệu theo request, người dùng, giao dịch hoặc thời điểm.
6. Có thể được giải thích bằng tài liệu và được kiểm thử bằng các trường hợp đại diện.

Không đổi tên nhóm chỉ vì đổi tên exception class. Nếu thay đổi taxonomy, cần xem đó là thay đổi metric contract và cập nhật dashboard, alert, tài liệu cùng lúc.

## Ánh xạ exception sang nhóm lỗi

Nên thực hiện việc phân loại tại ranh giới nơi ứng dụng hiểu ngữ nghĩa của lỗi: application service, adapter của dependency hoặc lớp chuyển exception thành kết quả domain. Không nên để mỗi controller tự đặt tên tag theo cách riêng.

Ví dụ enum:

~~~java
public enum FailureGroup {
    DEPENDENCY_TIMEOUT("dependency_timeout"),
    DEPENDENCY_UNAVAILABLE("dependency_unavailable"),
    INVALID_UPSTREAM_RESPONSE("invalid_upstream_response"),
    RATE_LIMITED("rate_limited"),
    INTERNAL_ERROR("internal_error"),
    UNKNOWN("unknown");

    private final String tagValue;

    FailureGroup(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Classifier ánh xạ các exception đã biết về tập giá trị đó:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeoutException;

public final class FailureClassifier {

    private FailureClassifier() {
    }

    public static FailureGroup classify(Throwable error) {
        if (error instanceof SocketTimeoutException
                || error instanceof TimeoutException) {
            return FailureGroup.DEPENDENCY_TIMEOUT;
        }

        if (error instanceof ConnectException) {
            return FailureGroup.DEPENDENCY_UNAVAILABLE;
        }

        // Các exception sau là kiểu domain do ứng dụng định nghĩa.
        if (error instanceof UpstreamPayloadException) {
            return FailureGroup.INVALID_UPSTREAM_RESPONSE;
        }

        if (error instanceof RateLimitExceededException) {
            return FailureGroup.RATE_LIMITED;
        }

        if (error instanceof InternalApplicationException) {
            return FailureGroup.INTERNAL_ERROR;
        }

        return FailureGroup.UNKNOWN;
    }
}
~~~

Đoạn classifier chỉ là ví dụ; `UpstreamPayloadException`, `RateLimitExceededException` và `InternalApplicationException` là các kiểu exception do ứng dụng định nghĩa. Trong ứng dụng thật, hãy phân biệt exception đầu vào không hợp lệ do client với response không hợp lệ từ upstream. Không ánh xạ một exception tổng quát thành nhóm upstream nếu nó có thể phát sinh ở nhiều ranh giới khác nhau. Ngữ cảnh domain quan trọng hơn tên class đơn lẻ.

Có thể unwrap wrapper exception nếu wrapper không mang ý nghĩa phân loại và cause bên trong đã được nhận diện. Chỉ unwrap những wrapper đã biết; không đi sâu tùy tiện đến root cause rồi bỏ qua ý nghĩa của lớp adapter.

### Không dùng exception message làm tag

Các giá trị sau không phù hợp cho metrics:

- Nội dung `exception.getMessage()`.
- Stack trace hoặc tên file/dòng code.
- URL đầy đủ có query parameter hoặc ID động.
- Payment ID, order ID, customer ID, request ID.
- Payload hoặc response body từ dependency.
- Nội dung do người dùng nhập.

Hãy ghi chi tiết đó trong log hoặc trace theo chính sách bảo mật, rồi dùng correlation ID để liên kết. Metrics trả lời xu hướng tổng hợp; log và trace giúp điều tra một lần xảy ra cụ thể.

## Đặt tên meter và tag có thể diễn giải

Tên meter nên nói rõ đại lượng đang đo. Micrometer khuyến nghị quy ước tên chữ thường, phân tách bằng dấu chấm; registry chuyển tên sang định dạng phù hợp với backend.

Ví dụ:

| Tên meter | Ý nghĩa |
|---|---|
| business.payment.authorization | Thời lượng của thao tác authorization |
| business.payment.failures | Số thao tác thanh toán kết thúc bằng lỗi kỹ thuật |
| business.orders.created | Số đơn hàng được tạo thành công |
| business.payment.declines | Số quyết định từ chối theo nghiệp vụ |

Tag nên mô tả các chiều phân tích hữu ích và có miền giá trị hữu hạn:

| Tag | Ví dụ | Lưu ý |
|---|---|---|
| operation | authorize, capture, refund | Tập thao tác đã định nghĩa |
| outcome | approved, declined, failed | Bao gồm kết quả thành công và không thành công |
| error.type | dependency_timeout, internal_error | Chỉ gắn khi thao tác kết thúc bằng lỗi |
| payment.decline.reason | insufficient_funds, card_expired | Chỉ gắn cho business decline |
| provider | gateway_a, gateway_b | Danh sách nhà cung cấp được cấu hình |
| channel | web, mobile, partner | Nhóm kênh có miền giá trị hữu hạn |

Không đưa error message vào tên meter. Không tạo một meter name riêng cho từng mã giao dịch hoặc từng exception. Tên meter nên ổn định, còn tag dùng để chia nhỏ theo các chiều đã được duyệt.

## Gắn hướng dẫn diễn giải bằng description và base unit

Micrometer cho phép đặt description và base unit khi tạo meter bằng builder. Description nên trả lời meter đo điều gì, khi nào tăng, phạm vi sự kiện và những gì bị loại trừ. Base unit giúp người đọc hiểu đơn vị của counter hoặc summary.

Ví dụ counter đếm lỗi kỹ thuật:

~~~java
Counter failures = Counter.builder("business.payment.failures")
    .description(
        "Số thao tác authorization kết thúc bằng lỗi kỹ thuật; " +
        "không bao gồm business decline và thao tác thành công."
    )
    .baseUnit("operations")
    .tag("operation", "authorize")
    .tag("error.type", "dependency_timeout")
    .register(registry);

failures.increment();
~~~

Một description hữu ích có thể nói rõ:

- Đối tượng được đo: thao tác authorization.
- Đơn vị: số operation.
- Ranh giới ghi nhận: một lần authorization kết thúc.
- Phạm vi: lỗi kỹ thuật đã phân loại.
- Loại trừ: decline hợp lệ và lần retry nội bộ nếu metric đếm logical operation.

Description không phải một runbook đầy đủ. Không phải backend nào cũng hiển thị description giống nhau, và description không thay thế tài liệu định nghĩa taxonomy, dashboard explanation hay hướng dẫn xử lý. Hãy đặt mô tả ngắn, bền vững trong meter; lưu hướng dẫn chi tiết ở tài liệu có phiên bản và liên kết tài liệu đó từ dashboard hoặc alert.

### Viết metric contract

Một metric contract có thể gồm:

| Trường | Ví dụ |
|---|---|
| Metric | business.payment.authorization |
| Owner | Nhóm Payment |
| Đơn vị | Một logical authorization operation |
| Event boundary | Từ lúc bắt đầu authorization đến kết quả cuối cùng |
| outcome | approved, declined, failed |
| error.type | dependency_timeout, dependency_unavailable, invalid_upstream_response, rate_limited, internal_error, unknown |
| Exclusions | Không đếm validation bị chặn trước khi gọi gateway |
| Retry semantics | Một sample cho toàn logical operation; thời gian bao gồm retry |
| Denominator | Tổng authorization operation hoàn tất trong cửa sổ |
| Interpretation | Phân biệt decline nghiệp vụ với lỗi kỹ thuật |
| Runbook | Hướng dẫn kiểm tra gateway, timeout, quota và trace |

Metric contract giúp dashboard, alert và code dùng cùng định nghĩa. Khi thay đổi mẫu số hoặc ranh giới đếm, phải cập nhật contract; nếu không, số liệu trước và sau deploy có thể không còn so sánh được.

## Ghi nhận outcome và error group bằng Timer

Một Timer vừa đo thời lượng vừa cung cấp count. Có thể dùng một timer cho các kết quả approved, declined và failed. Khi thao tác thất bại, gắn error.type đã phân loại; khi thành công hoặc bị từ chối hợp lệ, không gắn error.type.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class PaymentService {

    private final MeterRegistry registry;
    private final PaymentGateway gateway;

    public PaymentService(
        MeterRegistry registry,
        PaymentGateway gateway
    ) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public PaymentResult authorize(PaymentCommand command)
            throws Exception {
        Timer.Sample sample = Timer.start(registry);

        String outcome = "approved";
        String errorType = null;
        String declineReason = null;

        try {
            PaymentResult result = gateway.authorize(command);

            if (result.isDeclined()) {
                outcome = "declined";
                declineReason = result.declineReason().metricValue();
            }

            return result;
        } catch (Exception exception) {
            outcome = "failed";
            errorType = FailureClassifier.classify(exception).tagValue();
            throw exception;
        } finally {
            Timer.Builder timer = Timer.builder(
                    "business.payment.authorization"
                )
                .description(
                    "Thời lượng một logical authorization operation " +
                    "từ lúc bắt đầu đến kết quả cuối cùng; bao gồm retry nội bộ."
                )
                .tag("operation", "authorize")
                .tag("outcome", outcome);

            if (errorType != null) {
                timer.tag("error.type", errorType);
            }

            if (declineReason != null) {
                timer.tag("payment.decline.reason", declineReason);
            }

            sample.stop(timer.register(registry));
        }
    }
}
~~~

Ví dụ giả định gateway trả một kết quả domain cho business decline và ném exception cho lỗi kỹ thuật. Trong hệ thống thật, điều chỉnh theo hợp đồng API của gateway và phân loại rõ lỗi được xử lý so với lỗi được truyền lên caller.

Nếu cần đo từng lần retry thay vì toàn logical operation, hãy tạo một meter riêng có tên và description thể hiện attempt. Không trộn một sample cho toàn operation với nhiều sample cho từng attempt trong cùng một metric nếu dashboard không phân biệt được hai đơn vị đếm.

### Khi nào cần Counter riêng?

Timer đã có count cho số lần thao tác được ghi nhận. Nếu chỉ cần tỷ lệ lỗi của các thao tác đã đo bằng Timer, không cần tạo một Counter trùng lặp chỉ để đếm cùng sự kiện. Counter riêng phù hợp khi có một sự kiện nghiệp vụ độc lập không có thời lượng hoặc cần một metric contract riêng.

Ví dụ counter cho sự kiện hoàn tất đơn hàng:

~~~java
Counter orderCreated = Counter.builder("business.orders.created")
    .description(
        "Số đơn hàng được tạo thành công sau khi lưu transaction."
    )
    .baseUnit("orders")
    .tag("channel", "web")
    .register(registry);

orderCreated.increment();
~~~

Đặt điểm increment sau khi transaction đã đạt trạng thái được định nghĩa là created. Nếu increment trước commit, metric có thể đếm một đơn hàng sau đó bị rollback.

## Dùng MeterFilter làm hàng rào bảo vệ

Phân loại tại nguồn vẫn là cách chính. MeterFilter có thể đặt giới hạn cho số giá trị tag hoặc số meter để tránh một lỗi instrumentation làm registry tăng không kiểm soát:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "business.payment.authorization",
        "error.type",
        8,
        MeterFilter.deny()
    )
);
~~~

Filter trên từ chối đăng ký meter mới khi số giá trị error.type vượt giới hạn đã đặt cho meter phù hợp. Đây là hàng rào bảo vệ, không phải giải pháp phân loại. Khi vượt giới hạn, meter mới có thể trở thành no-op và dữ liệu bị bỏ; filter không tự động gom mọi lỗi lạ về unknown.

Vì vậy, hãy map giá trị không nhận diện về nhóm unknown trước khi tạo meter. Giữ filter như một lớp phòng vệ cuối cùng và theo dõi log hoặc diagnostics khi giới hạn bị chạm.

Không dùng replaceTagValues để che giấu một taxonomy không được kiểm soát nếu code có thể phân loại chính xác hơn. Việc chuẩn hóa ở ranh giới nghiệp vụ giúp log, trace và metrics dùng chung ý nghĩa.

## Truy vấn và diễn giải tỷ lệ lỗi

Giả sử Timer được export thành Prometheus histogram với metric count có tên `business_payment_authorization_seconds_count`. Đếm tốc độ lỗi kỹ thuật theo nhóm:

~~~promql
sum by (error_type) (
  rate(
    business_payment_authorization_seconds_count{
      outcome="failed"
    }[5m]
  )
)
~~~

Tỷ lệ lỗi kỹ thuật trên tổng authorization operation:

~~~promql
sum(
  rate(
    business_payment_authorization_seconds_count{
      outcome="failed"
    }[5m]
  )
)
/
sum(
  rate(business_payment_authorization_seconds_count[5m])
)
~~~

Tỷ lệ business decline:

~~~promql
sum(
  rate(
    business_payment_authorization_seconds_count{
      outcome="declined"
    }[5m]
  )
)
/
sum(
  rate(business_payment_authorization_seconds_count[5m])
)
~~~

Tên metric và label ở trên là ví dụ theo Prometheus naming convention. Hãy kiểm tra endpoint export thực tế trước khi dùng query. Tag key có dấu chấm như error.type thường được chuẩn hóa thành error_type trong Prometheus.

Nếu mẫu số không có traffic, tỷ lệ không có ý nghĩa. Không ép mẫu số về 1 chỉ để dashboard hiển thị 0%, vì như vậy no traffic sẽ bị hiểu nhầm là không có lỗi. Hãy hiển thị no data hoặc bổ sung panel traffic riêng.

Khi tổng hợp nhiều replica, dùng rate trên counter rồi mới sum. Không lấy trung bình tỷ lệ lỗi của từng replica nếu traffic mỗi replica khác nhau; hãy tổng hợp số lỗi và tổng operation trước khi chia để có tỷ lệ có trọng số theo lưu lượng.

## Hướng dẫn diễn giải số liệu trong dashboard và alert

Dashboard nên giúp người xem hiểu ngay metric đang nói về điều gì. Một bộ panel cho payment authorization có thể gồm:

| Panel | Cách tính | Hướng diễn giải |
|---|---|---|
| Authorization throughput | Rate của Timer count | Khối lượng logical operation |
| Technical failure rate | Failed / total operation | Mức độ lỗi kỹ thuật |
| Business decline rate | Declined / total operation | Tỷ lệ quyết định nghiệp vụ bị từ chối |
| Failure by error type | Rate nhóm theo error.type | Nhóm lỗi nào đóng góp nhiều nhất |
| Authorization latency p95 | Histogram quantile | Độ trễ đuôi của operation |
| Unknown error share | Unknown failures / all failures | Chất lượng taxonomy và mapping |

Trong mô tả panel, ghi rõ cửa sổ thời gian, đơn vị, mẫu số và ngoại lệ. Ví dụ: “Technical failure rate = operation kết thúc bằng lỗi kỹ thuật / tất cả authorization operation hoàn tất trong 5 phút; không bao gồm decline nghiệp vụ.”

Runbook có thể cung cấp hướng xử lý theo từng nhóm:

- dependency_timeout: kiểm tra latency dependency, timeout client, retry và saturation.
- dependency_unavailable: kiểm tra network, health endpoint, DNS, circuit breaker và incident phía provider.
- invalid_upstream_response: xem trace/log có payload đã được redacted, kiểm tra schema và phiên bản hợp đồng.
- rate_limited: kiểm tra quota, burst traffic, backoff và chính sách retry.
- internal_error: đối chiếu deploy, stack trace và thay đổi code gần thời điểm lỗi tăng.
- unknown: xác định lỗi chưa được phân loại, bổ sung mapping và test để tránh tiếp tục dồn vào nhóm fallback.

Alert nên gắn với một điều kiện có ý nghĩa. Ví dụ, cảnh báo khi tỷ lệ lỗi kỹ thuật vượt ngưỡng trong một khoảng đủ dài và có đủ traffic. Không cảnh báo chỉ vì một nhóm lỗi xuất hiện một lần nếu nó không có tác động vận hành đáng kể.

## Kiểm thử taxonomy và meter contract

Kiểm thử classifier bảo đảm exception được ánh xạ vào nhóm ổn định:

~~~java
import org.junit.jupiter.api.Test;

import java.net.SocketTimeoutException;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void classifiesSocketTimeoutAsDependencyTimeout() {
    assertEquals(
        FailureGroup.DEPENDENCY_TIMEOUT,
        FailureClassifier.classify(new SocketTimeoutException())
    );
}

@Test
void mapsUnknownFailureToUnknownGroup() {
    assertEquals(
        FailureGroup.UNKNOWN,
        FailureClassifier.classify(new RuntimeException())
    );
}
~~~

Kiểm thử meter bằng SimpleMeterRegistry:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;

SimpleMeterRegistry registry = new SimpleMeterRegistry();

Timer failed = Timer.builder("business.payment.authorization")
    .tag("operation", "authorize")
    .tag("outcome", "failed")
    .tag("error.type", "dependency_timeout")
    .register(registry);

failed.record(Duration.ofMillis(250));

assertEquals(
    1.0,
    registry.get("business.payment.authorization")
        .tag("outcome", "failed")
        .tag("error.type", "dependency_timeout")
        .timer()
        .count()
);

registry.close();
~~~

Các kiểm thử cần xác nhận thêm:

- Thành công không gắn error.type.
- Business decline được tách khỏi lỗi kỹ thuật.
- Mọi exception đã biết được ánh xạ vào nhóm đã công bố.
- Exception chưa biết rơi vào nhóm fallback ổn định.
- Không có exception message, ID hoặc URL động trong tag.
- Description nêu rõ ranh giới đếm, đơn vị và trường hợp bị loại trừ.
- Tên meter và tag không thay đổi ngoài chủ đích qua lần deploy.
- Metric export có đúng tên, label và đơn vị ở backend.

SimpleMeterRegistry xác minh instrumentation trong process. Cần kiểm tra thêm registry đích nếu muốn xác nhận tên và metadata được export đúng định dạng.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng exception message làm tag | Cardinality tăng theo request và có thể lộ dữ liệu | Map về nhóm lỗi hữu hạn; lưu message trong log |
| Coi business decline là lỗi kỹ thuật | Error rate bị thổi phồng và alert sai | Tách outcome declined và error.type |
| Nhóm unknown không có giới hạn | Mỗi lỗi lạ tạo một series mới | Dùng một fallback cố định và theo dõi tỷ lệ unknown |
| Nhóm lỗi quá chi tiết | Dashboard có nhiều series nhưng khó hành động | Gộp nhóm có cùng cách diễn giải |
| Nhóm lỗi quá rộng | Không biết cần kiểm tra dependency hay logic nào | Tách nhóm khi hành động xử lý khác nhau |
| Description chỉ ghi tên metric | Người đọc không biết mẫu số và ranh giới đếm | Mô tả đơn vị, event boundary và exclusions |
| Dùng Counter trùng với Timer count | Tạo hai số đo cho cùng sự kiện | Dùng Timer count khi đã đo thời lượng |
| Đếm attempt và logical operation chung một metric | Retry làm số liệu và tỷ lệ khó diễn giải | Định nghĩa riêng metric cho attempt và operation |
| Chia error rate khi không có traffic | No data bị hiểu thành 0% lỗi | Giữ no data và theo dõi traffic riêng |
| Đổi taxonomy mà không cập nhật dashboard | Series mới, lịch sử bị chia tách và alert sai | Version hóa metric contract và triển khai đồng bộ |

## Ghi nhớ

- Phân loại lỗi tại ranh giới nghiệp vụ thành một tập nhóm ổn định, có định nghĩa và hành động diễn giải.
- Tách business outcome như approved/declined khỏi lỗi kỹ thuật như dependency_timeout/internal_error.
- Dùng error.type với giá trị dự đoán được, cardinality thấp và có tài liệu liệt kê.
- Không gắn error.type cho thao tác thành công; dùng domain-specific tag cho lý do từ chối nghiệp vụ.
- Không đưa exception message, stack trace, request ID, user ID hoặc transaction ID vào tag.
- Dùng description và baseUnit để mô tả metric; dùng metric contract và runbook cho hướng dẫn chi tiết.
- Timer đã cung cấp count; không tạo Counter trùng cho cùng một thao tác chỉ để đếm.
- Định nghĩa rõ một sample đại diện cho attempt hay logical operation, đặc biệt khi có retry.
- Tính tỷ lệ bằng tổng số lỗi chia tổng số operation trong cùng cửa sổ; không lấy trung bình tỷ lệ của các replica.
- Kiểm thử mapping, tag, description và dữ liệu export trước khi dùng số liệu cho alert.

Khi nhóm lỗi có tên ổn định và mỗi metric có định nghĩa rõ, dashboard có thể chuyển từ việc liệt kê exception sang giải thích nguyên nhân và hướng điều tra. Người vận hành biết một con số đang đếm điều gì, điều gì bị loại trừ và cần kiểm tra đâu khi xu hướng thay đổi.

## Tài liệu tham khảo

- [Micrometer: Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html) — danh tính meter, loại meter và metadata.
- [Micrometer: Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) — counter, rate, description và base unit.
- [Micrometer: Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) — giới hạn số meter và số giá trị tag.
- [Micrometer: Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html) — quy ước tên meter và tag có tính portable.
- [OpenTelemetry: Recording errors](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/) — cách ghi error type trên metrics, spans và logs.
- [OpenTelemetry: HTTP metrics semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/) — yêu cầu error.type có thể dự đoán và cardinality thấp, cùng route template có cardinality thấp.

