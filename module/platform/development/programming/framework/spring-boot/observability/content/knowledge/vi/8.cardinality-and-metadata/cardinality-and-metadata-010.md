# Giới hạn kích thước metadata trong Spring Boot Observability

Trong chương **Cardinality và metadata** của module **SPRING_BOOT_OBSERVABILITY**, việc thiết lập observability không dừng ở thu thập đủ **metrics, logs và distributed tracing** bằng Micrometer Observation. Ở môi trường thực, còn phải kiểm soát **lượng metadata đi kèm mỗi tín hiệu**: tên/giá trị tag, thuộc tính span, sự kiện trace, trường log và thông tin được truyền qua các service.

Metadata giúp trả lời những câu hỏi như “nhà cung cấp thanh toán nào đang chậm?”, “lỗi xuất hiện ở giai đoạn nào?” hoặc “request này liên quan trace nào?”. Nhưng một trường lỗi dài hàng chục kilobyte, hàng trăm attributes trên một span, hoặc một baggage được truyền theo mọi HTTP request có thể gây tăng chi phí, bị backend cắt dữ liệu, làm chậm ứng dụng và vô tình phát tán thông tin nhạy cảm.

**Mục tiêu:** thiết kế giới hạn về **số trường, độ dài từng trường, kích thước tổng, số giá trị khác nhau và phạm vi truyền dữ liệu**; thực thi gần nguồn phát sinh; kiểm tra giới hạn ở SDK, collector và backend.

## 1. Phân biệt kích thước metadata và cardinality

Hai khái niệm liên quan nhưng giải quyết hai vấn đề khác nhau.

**Kích thước metadata** mô tả dung lượng/độ phức tạp của dữ liệu gắn với *một* tín hiệu. Nó có thể được đo bằng:

- **Số lượng trường:** một span có bao nhiêu attributes/events; một log có bao nhiêu key; một metric có bao nhiêu label.
- **Độ dài một key/value:** một chuỗi dài bao nhiêu ký tự hoặc **byte UTF-8**.
- **Kích thước toàn bộ bản ghi:** serialized log event, span hoặc HTTP header có tổng dung lượng bao nhiêu.
- **Độ sâu/cấu trúc:** object lồng nhau, mảng nhiều phần tử, stack trace và danh sách liên kết.

**Cardinality** đo số **giá trị hoặc tổ hợp nhãn khác nhau** có thể xuất hiện, quan trọng nhất với time series metrics.

| Trường hợp | Vấn đề chính | Cách xử lý |
| --- | --- | --- |
| `order.id` là mã 10 ký tự, có hàng triệu giá trị | Cardinality cực cao dù value ngắn | Không dùng ID làm metric label; giữ ở trace/log nếu thật sự cần và được phép |
| Một tag `error.message` dài 30 KB | Vừa lớn vừa có cardinality cao; có thể lộ dữ liệu | Không dùng nguyên văn làm tag; chuyển thành error code hữu hạn |
| Một span có 600 attributes, mỗi value 8 byte | Số thuộc tính lớn, dù từng value ngắn | Giới hạn số attributes và chỉ giữ những trường phục vụ điều tra |
| Một log chứa request body 2 MB | Kích thước sự kiện lớn và có thể chứa PII | Không log body mặc định; lưu dữ liệu cần thiết ở nơi phù hợp |
| `provider=bank_a/bank_b` và `outcome=ok/error` | Cardinality thấp, kích thước nhỏ | Thích hợp để phân tích metrics |

Một giới hạn **256 byte/value không làm cho `userId` trở thành tag có cardinality thấp**. Ngược lại, một enum có bốn giá trị vẫn có thể gây lãng phí nếu tên mỗi giá trị bị ghép thêm một đoạn mô tả khổng lồ.

### Byte, ký tự và độ dài chuỗi

Trong Java, `String.length()` đếm **UTF-16 code units**, không phải số byte khi dữ liệu được gửi dưới dạng UTF-8. Các ký tự tiếng Việt và emoji có thể dùng nhiều byte hơn ký tự ASCII. Ví dụ chuỗi `"đỏ"` có hai ký tự hiển thị nhưng cần năm byte UTF-8 (`đ` chiếm hai byte và `ỏ` chiếm ba byte).

Khi giới hạn do HTTP proxy, collector hoặc backend quy định theo **byte**, phải đo byte của biểu diễn thực tế. Cắt bằng `substring(0, 256)` chỉ đảm bảo một số lượng UTF-16 code units; nó không chắc đáp ứng ngân sách 256 byte UTF-8. Cũng không được cắt tùy ý mảng byte giữa một ký tự đa byte rồi giải mã lại, vì có thể tạo ký tự thay thế.

## 2. Metadata nằm ở những đâu?

Trong một ứng dụng Spring Boot có Micrometer Observation, metadata có thể đi qua nhiều tầng:

```text
Spring Boot service / HTTP / job / message consumer
                |
                v
     Observation.Context + KeyValues
                |
                +--> metric handler --> MeterRegistry --> exporter/scraper
                |                                       --> time series backend
                |
                +--> tracing handler --> span attributes/events/links
                |                       --> tracing SDK/exporter/collector
                |                       --> tracing backend
                |
                +--> logs (ứng dụng chủ động ghi) --> encoder/shipper/backend
                |
                +--> propagation context --> HTTP/message headers --> service khác
```

Không phải mọi dữ liệu trong `Observation.Context` đều được xuất thành metadata. Convention, filter và handler quyết định các key-value nào được xử lý. Tương tự, một span được phép tạo không đồng nghĩa exporter sẽ giữ đầy đủ mọi attribute: SDK, collector hoặc backend có thể giới hạn, cắt hoặc loại bỏ dữ liệu.

| Tín hiệu | Metadata điển hình | Loại giới hạn cần quản lý |
| --- | --- | --- |
| Metrics | Metric name, label keys/values, resource tags | Số label, độ dài, **số tổ hợp values**, số series |
| Traces | Span attributes, events, links, status, error details | Số attributes, độ dài attribute, số events/links, payload xuất |
| Logs | Message, fields có cấu trúc, MDC, stack trace | Kích thước event, độ dài fields, số trường, dữ liệu nhạy cảm |
| Propagation | `traceparent`, `tracestate`, baggage hoặc custom headers | Tổng kích thước HTTP/message headers, số entries và hop truyền |

Mỗi tầng có chính sách riêng. **Không có một thuộc tính cấu hình Spring Boot duy nhất** bảo đảm giới hạn mọi metadata trên cả bốn nơi này.

## 3. Metrics: giữ nhãn ngắn, hữu hạn và có ý nghĩa

Với metrics, cần ưu tiên **cardinality** trước khi tính độ dài label. Số time series thường tăng theo tích các lựa chọn của mỗi nhãn. Nếu một metric có các label:

- `provider` gồm 3 giá trị;
- `outcome` gồm 4 giá trị;
- `region` gồm 5 giá trị;
- `order_id` gồm 100.000 giá trị;

thì số tổ hợp lý thuyết là **3 × 4 × 5 × 100.000 = 6.000.000** (chưa tính các labels hạ tầng khác). Đặt giới hạn độ dài `order_id` bằng 24 byte **không làm giảm số tổ hợp**.

Các quy tắc thiết kế:

1. **Không đặt** order ID, user ID, email, token, URL/query string thô hoặc exception message vào low-cardinality metric tags.
2. Chọn giá trị từ **enum/allowlist**, ví dụ `provider=bank_a/bank_b/other`, `outcome=success/declined/error`.
3. Tên nhãn ngắn và ổn định; không tạo key động theo tên sản phẩm hoặc theo dữ liệu đầu vào.
4. Quy hoạch giới hạn **số lượng nhãn và giá trị khác nhau**, đồng thời có chính sách khi xuất hiện giá trị lạ.
5. Kiểm tra số series trong metric backend sau triển khai; đánh giá sự thay đổi theo phiên bản, số instance và môi trường.

### Ví dụ: chuyển lỗi bên ngoài thành nhóm có kiểm soát

Không chuyển trực tiếp `providerException.getMessage()` thành tag. Thay bằng mã lỗi của hệ thống:

```java
import java.util.Locale;
import java.util.Set;

public final class PaymentTelemetry {
    private static final Set<String> KNOWN_ERROR_KINDS =
            Set.of("timeout", "rate_limited", "unavailable", "invalid_response");

    private PaymentTelemetry() {}

    public static String errorKind(String providerCode) {
        if (providerCode == null) {
            return "unknown";
        }
        String normalized = providerCode.trim().toLowerCase(Locale.ROOT);
        return KNOWN_ERROR_KINDS.contains(normalized)
                ? normalized
                : "other";
    }
}
```

Với một Observation:

```java
observation.lowCardinalityKeyValue(
        "payment.error_kind", PaymentTelemetry.errorKind(providerErrorCode));
```

Giá trị bất ngờ được gom vào `other` thay vì tạo thêm series vô hạn. Tuy nhiên, **không được bỏ qua sự tăng bất thường của `other`**: nên có cách phát hiện/mổ xẻ lỗi ngoài metric nhãn cao, ví dụ log chẩn đoán có kiểm soát.

### MeterFilter là chốt chặn cuối, không thay thiết kế nhãn

Micrometer có `MeterFilter` để kiểm soát metric name/tags và giới hạn số giá trị tag được registry chấp nhận. Ví dụ:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsProtectionConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> limitProviderValues() {
        return registry -> registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "payment.authorize", "payment.provider", 12,
                        MeterFilter.deny()));
    }
}
```

Ví dụ này đặt giới hạn **12 giá trị khác nhau của tag `payment.provider`** trên các meter có tên bắt đầu bằng `payment.authorize`. Khi vượt giới hạn, fallback `MeterFilter.deny()` có thể khiến **meter mới bị từ chối**, đồng nghĩa mất dữ liệu từ những series đó. Đây là biện pháp bảo vệ khi cấu hình lỗi; cần chuẩn hóa giá trị từ nguồn trước và giám sát sự cố bị từ chối meter. Filter này **không phải cơ chế giới hạn số byte của chuỗi tag**.

## 4. Traces: giới hạn attributes, events và dữ liệu lỗi

Một custom observation có thể sinh span thông qua tracing bridge/handler. Các `lowCardinalityKeyValue(...)` của Micrometer thường được handler dùng cả cho metric tags và trace attributes; `highCardinalityKeyValue(...)` thường chỉ dùng cho ngữ cảnh trace trong các handler tiêu chuẩn. Cách xử lý chính xác phụ thuộc handler, bridge và phiên bản.

Các nhóm dữ liệu cần đặt ngân sách riêng:

| Thành phần trace | Rủi ro khi quá lớn | Hướng kiểm soát |
| --- | --- | --- |
| Span attributes | Span nặng; SDK có thể bỏ attributes sau giới hạn số lượng | Chỉ giữ trường phục vụ chẩn đoán; giới hạn count và value length |
| Span events | Một request tạo hàng nghìn events | Chỉ ghi cột mốc nghiệp vụ quan trọng; đặt giới hạn số events |
| Span links | Fan-out hoặc batch tạo số lượng links lớn | Giữ liên kết cần thiết; giới hạn số links |
| Exception details | Stack trace, cause chain hoặc exception message rất dài | Dùng error kind ngắn cho phân loại; giữ thông tin lỗi có kiểm soát |
| Tên span | Gắn ID hoặc raw URL gây khó tổng hợp | Tên operation ổn định như `payment.authorize` |

Hệ OpenTelemetry SDK có các giới hạn kiểu **max attributes per span, max attribute-value length, max events, max links**. Tùy cách khởi tạo SDK, chúng có thể được cấu hình bằng SDK builder hoặc cơ chế autoconfigure. Ví dụ, trong một hệ thống **thật sự sử dụng OpenTelemetry SDK autoconfigure**, có thể xem xét các biến:

```text
OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT=32
OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT=256
OTEL_SPAN_EVENT_COUNT_LIMIT=16
OTEL_SPAN_LINK_COUNT_LIMIT=16
```

Đây là **giá trị chính sách ví dụ**, không phải mặc định bắt buộc của OpenTelemetry hay Spring Boot. Chúng chỉ có tác dụng khi SDK/autoconfigure cụ thể hỗ trợ và đọc các biến đó; một Spring Boot app dùng **Brave bridge**, hoặc tự xây dựng SDK khác, không tự động nhận cùng chính sách. Các giới hạn của SDK cũng **không quản lý trực tiếp tags trong MeterRegistry, structured logs hoặc baggage**.

Nếu một thuộc tính bị cắt hoặc không còn chỗ, cần biết SDK xử lý ra sao, có đếm dropped attributes/events và backend có chính sách giới hạn thứ hai hay không. Cấu hình collector có thể loại bỏ thêm dữ liệu sau khi đã rời JVM.

## 5. Logs: tránh biến dữ liệu nghiệp vụ thành bản ghi khổng lồ

Log có cấu trúc hữu ích khi cần giải thích **vì sao** một bước lỗi, nhưng một bản ghi chứa request/response body, danh sách hàng nghìn item hoặc stack trace lặp lại có thể vượt ngưỡng kích thước của log shipper và kho lưu trữ. Những nơi này có thể cắt chuỗi, tách bản ghi hoặc từ chối ingest tùy cấu hình.

Một log tốt cho một lỗi thanh toán thường chỉ cần các trường như:

```json
{
  "event": "payment.authorization_failed",
  "provider": "bank_a",
  "error_kind": "timeout",
  "retryable": true,
  "duration_ms": 812
}
```

Nếu tracing và MDC correlation được cấu hình, `traceId`/`spanId` có thể được thêm bởi logging pipeline để đối chiếu với trace; không cần tự đưa toàn bộ trace context hoặc raw header vào từng log.

Nên:

- Dùng mã phân loại lỗi ngắn; log exception có chủ đích và tránh lặp stack trace ở mọi tầng.
- Giới hạn độ dài các trường tự do **trước khi encoder serialize**; xem xét giới hạn tổng kích thước một log event.
- Không log password, token, cookie, số thẻ hoặc nguyên request body chỉ vì đang điều tra.
- Khi phải cắt dữ liệu, giữ một dấu hiệu có kiểm soát như `truncated=true` hoặc số byte ban đầu trong phạm vi hợp lý để người điều tra biết bản ghi chưa đầy đủ.
- Đưa log lớn có giá trị kiểm toán vào nơi lưu trữ chuyên dụng với phân quyền/phương án tham chiếu thích hợp thay vì nhồi vào telemetry.

Không phải mọi lần lỗi đều cần event cực lớn. Thông tin định lượng như tỉ lệ lỗi dùng metrics; quan hệ các bước dùng traces; chi tiết quyết định kỹ thuật/miền dùng logs.

## 6. Context propagation và baggage: giới hạn phải tính cả đường truyền

Distributed tracing giúp liên kết request xuyên các service bằng cơ chế propagation, chẳng hạn **W3C Trace Context** với `traceparent`/`tracestate` khi stack hỗ trợ. **Baggage** là cơ chế riêng để truyền một số key-value theo ngữ cảnh phân tán; nó không phải nơi lưu nguyên payload nghiệp vụ.

Một giá trị baggage có thể được gửi lặp lại qua nhiều HTTP calls hoặc messages. Nếu 1 KB baggage đi qua nhiều hops và fan-out, băng thông/chi phí xử lý tăng theo số lần truyền. Tệ hơn, baggage đi qua ranh giới tin cậy có thể làm lộ dữ liệu trong headers.

Quy tắc thực hành:

1. **Không truyền** user profile, session token, email, nội dung đơn hàng hoặc raw exception qua baggage.
2. Chỉ chọn trường thực sự cần downstream, có danh sách key được phép và giới hạn độ dài; thường ưu tiên metadata phân loại ngắn.
3. Phân biệt **trace ID** do tracing tạo với các business IDs: truyền trace context chuẩn, không dựng header trace thủ công.
4. Kiểm tra **tổng kích thước headers** do reverse proxy, gateway, broker hoặc HTTP client cho phép. Lỗi giới hạn có thể làm request bị từ chối trước khi tới ứng dụng.
5. Khi nghi ngờ kích thước metadata làm hỏng propagation, kiểm tra span cha/con ở downstream và quan hệ với logs, không chỉ xem request có HTTP 200.

Cắt baggage giữa đường có thể làm mất một phần ngữ nghĩa; thiết kế nhỏ và rõ ngay từ nguồn tốt hơn. Tên key, encoding và các giới hạn theo chuẩn/SDK cần được kiểm tra cho propagator thực tế đang triển khai.

## 7. Lập ngân sách metadata theo loại tín hiệu

Không có một con số duy nhất đúng cho mọi ứng dụng. Bảng sau minh họa **mục tiêu nội bộ để bắt đầu đánh giá**, **không phải giới hạn mặc định** hay một quy chuẩn bắt buộc của Micrometer:

| Đối tượng | Mục tiêu ví dụ | Cách kiểm tra và phản ứng |
| --- | --- | --- |
| Low-cardinality metric labels do nhóm tự thêm | Tối đa 6 keys; mỗi value thuộc enum/allowlist | Kiểm tra tập giá trị và số series; giá trị lạ gom về `other` |
| Span attributes do custom instrumentation tự thêm | Tối đa 16 fields; chuỗi tối đa 128 byte UTF-8 | Bỏ field không quan trọng, giữ error code; SDK có thể áp thêm giới hạn tổng |
| Span events nghiệp vụ | Tối đa 8 events cho mỗi operation | Chỉ phát event khi chuyển trạng thái có giá trị điều tra |
| Một log event ứng dụng thông thường | Mục tiêu tối đa 4 KiB sau serialize | Rút gọn, bỏ body; ngoại lệ có thể theo chính sách riêng |
| Baggage do ứng dụng tự định nghĩa | Mặc định không có; chỉ vài key ngắn nếu thật sự cần | Allowlist, kiểm tra encoding và tổng headers |

Với những con số minh họa này, cần làm rõ:

- 128 **byte UTF-8 của một value** không đồng nghĩa một span tối đa 128 byte; còn tên key, nhiều attributes, events và thông tin protocol.
- 4 KiB **một log event** không tự bảo đảm 4 KiB trên đường truyền sau encoding/compression hoặc thêm metadata của shipper.
- Giới hạn **số fields** khác giới hạn **số giá trị khác nhau** qua các bản ghi. Cả hai đều cần với metrics.
- Mỗi môi trường có thể có chính sách khác nhau, nhưng điều đó phải được kiểm chứng ở backend thực tế và được quản lý như một hợp đồng telemetry.

Ưu tiên xác định ngân sách bằng **quan sát phân phối kích thước bản ghi**, điểm giới hạn của vendor và dung lượng vận hành có thể chấp nhận. Khi cắt, cần quyết định nên *reject*, *normalize*, *truncate* hay *drop* để giữ dữ liệu quan trọng nhất.

## 8. Ví dụ Java: cắt chuỗi an toàn theo byte UTF-8

Khi một trường **được phép xuất** nhưng có độ dài biến động, có thể cắt nó theo số byte UTF-8 bằng cách đi qua từng Unicode code point. Cách này tránh cắt giữa các byte của một ký tự:

```java
import java.nio.charset.StandardCharsets;

public final class TelemetryText {
    private TelemetryText() {}

    public static String limitUtf8Bytes(String value, int maxBytes) {
        if (value == null || maxBytes <= 0) {
            return "";
        }
        StringBuilder result = new StringBuilder();
        int usedBytes = 0;
        for (int offset = 0; offset < value.length();) {
            int codePoint = value.codePointAt(offset);
            String piece = new String(Character.toChars(codePoint));
            int nextBytes = piece.getBytes(StandardCharsets.UTF_8).length;
            if (usedBytes + nextBytes > maxBytes) {
                break;
            }
            result.append(piece);
            usedBytes += nextBytes;
            offset += Character.charCount(codePoint);
        }
        return result.toString();
    }
}
```

Ví dụ nếu muốn giới hạn một **diagnostic hint do ứng dụng tạo và đã được duyệt để xuất**:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void recordPaymentFailure(
        ObservationRegistry registry,
        String approvedDiagnosticHint,
        Runnable action) {

    String hint = TelemetryText.limitUtf8Bytes(approvedDiagnosticHint, 128);

    Observation.createNotStarted("payment.failure.review", registry)
            .lowCardinalityKeyValue("failure.category", "provider")
            .highCardinalityKeyValue("diagnostic.hint", hint)
            .observe(action);
}
```

**Quan trọng:** cắt ngắn **không làm dữ liệu trở nên an toàn**. Nếu `approvedDiagnosticHint` chứa password, token, PII, order ID hoặc thông báo lỗi chứa body nhạy cảm, cắt còn 128 byte vẫn có thể làm lộ chúng. Chỉ dùng helper sau khi **phân loại, cho phép và làm sạch dữ liệu tại nguồn**. Đồng thời, high-cardinality attributes không nên bị chuyển sang metric tags bởi convention/handler tùy biến.

Hàm minh họa này chỉ giải quyết **độ dài của một chuỗi**. Nó không áp giới hạn **số attributes**, **tổng span size**, **số log fields**, hay **tổng baggage headers**. Nó cũng không thay việc cấu hình giới hạn SDK/backend.

### Khi nào không nên truncate?

Không nên cắt ngắn một **mã định danh có yêu cầu khớp chính xác** rồi dùng kết quả làm join key: hai mã khác nhau có thể cùng tiền tố sau khi cắt. Tốt hơn là không xuất ID nếu không cần; khi thật sự cần đối chiếu, dùng trường đã được chính sách dữ liệu cho phép, có định dạng/độ dài đã được kiểm soát và lưu ở kênh thích hợp. Băm ID cũng không tự giải quyết cardinality hoặc rủi ro định danh.

## 9. Giới hạn tại nguồn, SDK, collector và backend khác nhau thế nào?

Thường cần nhiều lớp kiểm soát phối hợp:

| Tầng | Trách nhiệm | Giới hạn cần nhớ |
| --- | --- | --- |
| **Code và ObservationConvention** | Chỉ xuất metadata cần thiết, normalize enum, không đưa dữ liệu nhạy cảm vào key-values | Đây là nơi hiểu rõ ý nghĩa nghiệp vụ nhất |
| **ObservationFilter/MeterFilter** | Điều chỉnh context/tags hoặc bảo vệ meter registry | Filter không thể biến mọi payload log/trace thành an toàn chỉ bằng một quy tắc |
| **Tracing SDK** | Giới hạn attributes/events/links và kích thước span field | Không tự giới hạn metric labels, baggage, log messages |
| **Exporter/collector** | Kiểm soát ingest, processor, sampling, redaction, transform | Dữ liệu có thể đã tốn tài nguyên trên app/network trước khi tới đây |
| **Backend** | Giới hạn ingest/time series/event size và retention | Drop hoặc truncate ở backend có thể làm mất chi tiết điều tra |
| **Gateway/proxy/broker** | Giới hạn kích thước headers/message | Metadata propagation quá lớn có thể làm hỏng giao dịch thay vì chỉ mất telemetry |

Ví dụ, nếu một span có 400 custom attributes, collector có thể bỏ 350 attributes khi ingest. Nhưng ứng dụng đã xây context, serialize/export dữ liệu ban đầu và phát sinh overhead tương ứng. Giới hạn **ngay tại code** vẫn quan trọng dù backend đã có quota.

Đối với logs, log shipper thường có hành vi khác tracing SDK: một số pipeline có thể **cắt hoặc bỏ nguyên event** khi quá lớn. Vì vậy cần kiểm tra số lượng log bị drop và quan sát cảnh báo về lỗi ingestion. Không nên coi một log không tìm thấy là bằng chứng code không chạy.

## 10. Ứng dụng vào điều tra lỗi, độ trễ và trace liên kết

Giả sử luồng đặt hàng:

```text
POST /checkout
   |
   +-- inventory.reserve        [span nghiệp vụ]
   |      +-- database call     [span hạ tầng nếu được instrument]
   |
   +-- payment.authorize        [span nghiệp vụ]
          +-- provider HTTP     [span client nếu được instrument]
```

Một bộ metadata có ích và nhỏ:

| Tín hiệu | Metadata nên giữ | Tránh |
| --- | --- | --- |
| HTTP metrics | `uri` là route template, `status`, `method` | URL đầy đủ chứa order ID/query |
| `inventory.reserve` | `warehouse.tier=primary/secondary`, `outcome=reserved/out_of_stock/error` | Dump cart hoặc danh sách item |
| `payment.authorize` | `provider=bank_a/bank_b`, `outcome=approved/declined/error` | Payment token, raw card info |
| Trace nghiệp vụ | Ranh giới và thời lượng các bước, thông tin lỗi đã chuẩn hóa | Exception message nguyên văn chưa lọc |
| Log lỗi | `event`, `error.kind`, `retryable`, `traceId`/`spanId` nếu có correlation | Request body và headers nhạy cảm |
| Propagation | Trace context chuẩn, baggage tối thiểu khi thực sự cần | Toàn bộ profile của người dùng |

Khi `payment.authorize` lỗi, metric giúp phát hiện tỉ lệ lỗi theo provider; trace giúp xác định lời gọi outbound chậm; log giúp xác nhận loại lỗi kỹ thuật. Nếu các metadata này bị cắt sai cách, điều tra vẫn có thể thất bại dù cả ba hệ thống đều đang thu thập dữ liệu.

Phải phân biệt **sampling** và giới hạn kích thước: sampler có thể không giữ một trace, trong khi một trace được giữ vẫn có thể mất attributes vì vượt quota. Context propagation sai cũng có thể khiến span con không nối với span cha. Cần kiểm tra từng nguyên nhân, không đổ chung cho “backend mất dữ liệu”.

## 11. Quy trình kiểm chứng và giám sát metadata budget

Trước khi đưa một metadata policy vào sản xuất, thực hiện ít nhất các bước:

1. **Liệt kê trường đang xuất:** từ HTTP, custom observation, logs, tracing attributes/events và baggage. Xác định nơi sinh ra, mục đích dùng và người chịu trách nhiệm.
2. **Phân loại mức nhạy cảm:** tài khoản, credential, dữ liệu cá nhân, ID nghiệp vụ, payload tự do; bỏ hoặc làm sạch trước khi giới hạn độ dài.
3. **Đo mẫu thực tế:** số attributes/log fields, phân phối byte UTF-8, số series theo từng label, kích thước headers và tỷ lệ dropped/truncated records.
4. **Đặt ngân sách riêng:** count, bytes/value, total event, số values khác nhau, retention; ghi rõ con số minh họa và con số do backend bắt buộc.
5. **Chuẩn hóa tại nguồn:** enum/allowlist, tên key ổn định, route template, mã lỗi hữu hạn và không log body mặc định.
6. **Cấu hình tầng phòng vệ:** meter filters, tracing SDK, collector, log pipeline và gateway theo stack đang dùng.
7. **Kiểm tra liên kết tín hiệu:** từ một cảnh báo latency/error, tìm được span, log và service downstream; thử cả async/queue và sampling.
8. **Theo dõi sau phát hành:** time series, dropped spans/attributes/logs, ingest failures, độ trễ telemetry, CPU/memory và chi phí.

### Ma trận thử nghiệm tối thiểu

| Kịch bản | Kỳ vọng |
| --- | --- |
| Value ASCII ngắn, thuộc allowlist | Giữ nguyên và được xuất đúng |
| Value tiếng Việt/emoji gần ngưỡng byte | Không vượt ngân sách UTF-8; không xuất ký tự bị hỏng |
| Provider trả mã lỗi lạ | Low-cardinality tag chuyển `other`; không tạo value vô hạn |
| Exception message dài chứa dữ liệu nhạy cảm | Không đưa nguyên văn vào metric/trace/log; dùng mã phân loại an toàn |
| Span có quá nhiều attributes/events | Giữ các trường quan trọng; có cách nhận biết drop/truncate ở SDK/backend nếu hỗ trợ |
| Log event vượt ngưỡng | Pipeline cắt/bỏ theo chính sách đã kiểm chứng; không làm mất toàn bộ thông tin lỗi thiết yếu |
| Baggage/header quá lớn | Hệ thống ngăn phát sinh từ nguồn; không làm HTTP/message bị từ chối vì header |
| Trace bị sampling bỏ | Metrics vẫn có thể tồn tại nếu metric handler hoạt động; không nhầm với mất attributes |
| Task chạy ở thread/service khác | Parent-child trace và log correlation đúng khi context propagation được cấu hình |

Một phép kiểm tra rất quan trọng là so sánh **dữ liệu đã gắn trong mã** với **dữ liệu thực sự nhìn thấy ở backend**. Nếu code đưa vào 15 attributes nhưng backend chỉ còn 10, cần lần theo SDK → exporter → collector → backend để tìm giới hạn gây ra việc cắt hoặc drop. Nếu metric tăng series đột ngột, cần tìm nhãn có nhiều giá trị mới, thay vì chỉ rút ngắn chuỗi value.

## 12. Bài tập áp dụng

Một service Spring Boot xử lý 10.000 đơn/ngày đang có các telemetry fields:

```text
Metric: checkout.duration
  tags: outcome, provider, orderId, errorMessage

Trace span: checkout
  attributes: provider, fullRequestBody, paymentToken,
              retryCount, failurePhase, errorMessage

Log: "checkout failed: " + fullExceptionStack

Propagation baggage:
  userProfileJson, orderId
```

Hãy đề xuất cách giảm kích thước và cardinality mà vẫn có khả năng điều tra lỗi, độ trễ và liên kết các service. Một đáp án tham khảo:

1. **Metric:** giữ `outcome` và `provider` đã chuẩn hóa; bỏ `orderId`, `errorMessage`; nếu cần phân loại lỗi, thêm `error.kind` từ allowlist.
2. **Span:** giữ `provider`, `retry.count` và `failure.phase`; loại `fullRequestBody` và `paymentToken`; chỉ sử dụng mã lỗi/mô tả chẩn đoán đã được duyệt, có giới hạn byte và số attributes.
3. **Log:** ghi event có cấu trúc với error kind, retryability và trace correlation. Ghi exception chi tiết có kiểm soát, tránh lặp và không chứa secrets.
4. **Baggage:** bỏ `userProfileJson`; không mặc định truyền `orderId`. Dùng trace context propagation chuẩn; chỉ có baggage khi downstream có nhu cầu được chứng minh.
5. **Hạ tầng:** kiểm tra SDK, collector, exporter, log pipeline, gateway và metric backend để bảo đảm policy đang thật sự có hiệu lực.

**Kết luận:** Giới hạn kích thước metadata là một phần của thiết kế observability, chứ không chỉ là cấu hình quota. Với Micrometer Observation trong Spring Boot, hãy đưa ra **ít metadata nhưng đúng ngữ nghĩa**: metric labels hữu hạn, trace attributes/events vừa đủ, logs có cấu trúc và an toàn, baggage tối thiểu. Kết hợp chuẩn hóa tại nguồn, giới hạn trong SDK/backend và kiểm chứng xuyên metrics–logs–traces sẽ giữ hệ thống đủ tín hiệu để điều tra mà không bị metadata làm quá tải.
