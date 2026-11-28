# Không đưa dữ liệu cá nhân vào metric

Metrics giúp nhóm vận hành trả lời các câu hỏi như: module nào đang chậm, có bao nhiêu event được publish, tỷ lệ lỗi tăng hay giảm và hệ thống đang sử dụng tài nguyên ra sao. Để trả lời những câu hỏi đó, metric cần các chiều phân nhóm như module, event type, HTTP method hoặc outcome. Những chiều này nên có tập giá trị hữu hạn và không nhận dạng một cá nhân.

Đưa email, số điện thoại, user ID, customer ID, session ID, địa chỉ IP hoặc dữ liệu cá nhân khác vào metric labels tạo ra hai rủi ro. Thứ nhất, mỗi giá trị mới có thể tạo một time series mới, làm tăng bộ nhớ, chi phí ingest và truy vấn. Thứ hai, metrics thường được scrape, lưu trữ và chia sẻ cho nhiều nhóm vận hành; label có thể làm lộ dữ liệu cá nhân trong dashboard, API, export hoặc bản sao lưu.

Trong ứng dụng Spring Boot dùng Spring Modulith, cần kiểm soát dữ liệu ngay tại nơi tạo observation và meter. Các module như order, inventory, billing và notification nên xuất số liệu theo module, event type và kết quả xử lý. Khi cần điều tra một giao dịch cụ thể, dùng cơ chế log/trace có phân quyền và chính sách lưu trữ riêng; việc đưa một giá trị sang trace không tự động làm giá trị đó an toàn.

Bài học thuộc chương **Bảo mật** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mục tiêu là thiết kế metrics đủ hữu ích để quan sát kiến trúc mô-đun mà không biến hệ thống monitoring thành nơi lưu trữ định danh cá nhân.

> **Nguyên tắc:** metric label chỉ chứa dimension đã được phân loại và có tập giá trị giới hạn. Không đưa dữ liệu cá nhân trực tiếp hoặc dưới dạng hash vào metric. Nếu cần phân tích theo từng người dùng, hãy dùng hệ thống phân tích nghiệp vụ có kiểm soát truy cập, mục đích và thời hạn lưu trữ phù hợp.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao metric labels không phù hợp để lưu dữ liệu cá nhân.
2. Phân biệt cardinality với độ nhạy cảm của dữ liệu.
3. Chọn low-cardinality dimensions phù hợp cho metrics của Spring Modulith.
4. Phân biệt metadata của Micrometer Observation được đưa vào metrics và traces.
5. Ngăn dữ liệu nhạy cảm đi vào meter bằng thiết kế instrumentation và MeterFilter.
6. Hiểu giới hạn của hashing, pseudonymization và redaction.
7. Kiểm tra Prometheus exposition, meter registry, logs và traces để phát hiện rò rỉ.
8. Xây dựng quy trình xử lý khi dữ liệu cá nhân đã xuất hiện trong metric backend.

## 2. Vì sao metric không phải nơi lưu dữ liệu cá nhân?

Metric là dữ liệu đo lường đã được tổng hợp theo thời gian và các chiều phân nhóm. Ví dụ:

~~~text
orders.completed{
  module="order",
  event_type="OrderCompleted",
  outcome="success"
} 125
~~~

Metric trên trả lời được có bao nhiêu đơn hoàn tất, event type nào và kết quả ra sao. Nó không cần biết khách hàng cụ thể là ai.

Nếu thêm customer identifier:

~~~text
orders.completed{
  module="order",
  customer_id="customer-938271"
} 1
~~~

mỗi customer có thể tạo một time series. Dữ liệu đó vừa khó tổng hợp ở quy mô lớn, vừa làm lộ quan hệ giữa khách hàng và hoạt động mua hàng.

### Bốn lý do cần loại dữ liệu cá nhân khỏi metric

**Cardinality và hiệu năng.** Mỗi tổ hợp tên metric cùng label values có thể tạo một time series. Một label nhận giá trị không giới hạn như email, user ID hoặc request ID có thể tạo hàng nghìn đến hàng triệu series.

**Phạm vi truy cập.** Metrics thường được đọc bởi dashboard, alert engine, SRE, nền tảng giám sát, hệ thống billing và API export. Người có quyền xem metrics có thể không được phép xem danh sách khách hàng.

**Thời gian lưu trữ và bản sao.** Metrics có thể được lưu ở nhiều backend, remote-write destination, replica, snapshot và backup. Việc xóa một label khỏi dashboard không xóa dữ liệu đã ingest.

**Khả năng liên kết.** Một giá trị có thể không trực tiếp nêu tên người dùng nhưng vẫn kết hợp với thời gian, khu vực, tenant, event type hoặc dữ liệu bên ngoài để nhận diện một cá nhân.

## 3. Cardinality và độ nhạy cảm là hai tiêu chí khác nhau

Không nên dùng cardinality làm tiêu chí duy nhất để quyết định dữ liệu có được phép xuất ra metrics hay không.

| Dữ liệu | Cardinality thường gặp | Rủi ro riêng tư | Dùng làm metric label? |
| --- | --- | --- | --- |
| HTTP method | Thấp | Thấp | Có, nếu cần |
| Outcome success/failure | Thấp | Thấp | Có |
| Module identifier | Thấp | Thấp | Có |
| Event type allowlist | Thấp | Thấp | Có |
| Email | Rất cao | Trực tiếp nhận dạng | Không |
| Phone number | Cao | Trực tiếp nhận dạng | Không |
| User/customer ID | Cao | Định danh hoặc liên kết được | Không |
| Session ID/request ID | Cao | Có thể liên kết hoạt động cá nhân | Không |
| IP address | Cao | Có thể là dữ liệu cá nhân/định danh thiết bị | Không |
| Ngày sinh chính xác | Có thể cao | Nhạy cảm khi kết hợp thuộc tính khác | Không |
| Giới tính hoặc nhóm tuổi | Có thể thấp | Có thể là dữ liệu cá nhân hoặc thuộc tính nhạy cảm tùy bối cảnh | Chỉ xem xét dimension đã tổng hợp, được phê duyệt và thực sự cần |
| Khu vực địa lý rất chi tiết | Cao | Có thể nhận diện vị trí cá nhân | Không |
| Nhóm khu vực lớn đã tổng hợp | Thấp hơn | Vẫn có thể nhạy cảm khi nhóm quá nhỏ | Chỉ dùng sau đánh giá rủi ro |

**Low cardinality không đồng nghĩa với vô hại.** Một label chỉ có hai giá trị vẫn có thể tiết lộ thuộc tính cá nhân nếu metric được phân nhóm theo một đặc điểm nhạy cảm. Ngược lại, một identifier nội bộ không phải PII trực tiếp vẫn có thể tạo cardinality rất cao và liên kết với dữ liệu cá nhân ở hệ thống khác.

Do đó, hãy đánh giá độc lập:

- **Privacy classification:** giá trị có nhận dạng, mô tả hoặc liên kết tới cá nhân không?
- **Cardinality:** tập giá trị có giới hạn và ổn định không?
- **Purpose:** dashboard/alert có thực sự cần dimension này không?
- **Access and retention:** ai đọc được và dữ liệu được giữ bao lâu?

## 4. Những dữ liệu không được đưa vào metric labels

Danh sách sau là các ví dụ phổ biến cần chặn trong instrumentation:

| Nhóm | Ví dụ | Cách thay thế |
| --- | --- | --- |
| Định danh cá nhân | email, họ tên, số điện thoại, username | Bỏ khỏi metric; dùng outcome/module nếu cần tổng hợp |
| Định danh tài khoản | user ID, customer ID, account number | Không đưa vào labels; dùng business aggregate |
| Định danh phiên/giao dịch | session ID, request ID, order ID, payment ID | Dùng trace/log correlation có kiểm soát; metric chỉ đếm tổng |
| Định danh mạng | IP address, MAC address, device ID | Nhóm theo loại client hoặc outcome nếu cần |
| Vị trí | GPS, tọa độ chính xác, địa chỉ nhà | Không xuất; nếu có mục đích hợp lệ, chỉ dùng nhóm địa lý đủ lớn sau đánh giá |
| Dữ liệu tài chính | số thẻ, tài khoản ngân hàng, số tiền gắn với cá nhân | Dùng metric tổng hợp theo currency/operation/outcome; không dùng identifier |
| Dữ liệu sức khỏe | chẩn đoán, mã bệnh, hồ sơ điều trị | Không đưa vào telemetry metrics |
| Bí mật xác thực | password, access token, cookie, session token | Không ghi vào bất kỳ metric/label nào |
| Nội dung tự do | search query, comment, URL query string, exception message | Không dùng làm label; chuẩn hóa hoặc loại bỏ |

Không lấy trực tiếp path hoặc query string từ request làm tag. Ví dụ /customers/12345/orders?email=a@example.com phải được chuẩn hóa thành route template như /customers/{customerId}/orders hoặc loại bỏ khỏi metric nếu không cần thiết.

## 5. Thiết kế metric cho application modules

Với Spring Modulith, mục tiêu là đo ranh giới và tương tác module. Hãy chọn các chiều cố định:

| Dimension | Giá trị ví dụ | Dùng để trả lời |
| --- | --- | --- |
| module | order, inventory, billing, notification | Module nào đang hoạt động hoặc gặp lỗi? |
| event_type | OrderCompleted, StockReserved | Event type nào được publish? |
| outcome | success, failure, ignored | Kết quả xử lý ra sao? |
| operation | reserve, release, charge | Operation nào đang chậm? |
| dependency | inventory-db, payment-gateway | Downstream nào có vấn đề? |
| status_group | 2xx, 4xx, 5xx | Nhóm HTTP response nào tăng? |
| environment | staging, production | Môi trường nào có vấn đề? |

Các giá trị trên phải được tạo từ allowlist hoặc enum nội bộ. Không dùng trực tiếp giá trị tùy ý do client gửi lên.

### Cẩn thận với common tags

Spring Boot cho phép khai báo common observation key-values để gắn dimension môi trường như region hoặc stack vào mọi observation. Các giá trị này là low-cardinality và được đưa vào metrics/traces. Chỉ dùng thuộc tính hạ tầng ổn định:

~~~yaml
management:
  observations:
    key-values:
      region: ap-southeast-1
      stack: production
~~~

Không đặt email, user ID, customer ID, IP address hoặc tenant ID tùy ý vào common tags. Một common tag được gắn vào mọi observation có thể làm rò dữ liệu trên diện rộng và nhân số series theo từng meter.

### Ví dụ metric an toàn hơn

~~~text
module.events.published{
  module="order",
  event_type="OrderCompleted"
} 125

module.event.listener.completed{
  module="inventory",
  event_type="OrderCompleted",
  outcome="success"
} 120

module.event.listener.failed{
  module="inventory",
  event_type="OrderCompleted",
  outcome="dependency_error"
} 5
~~~

Các metric trên giúp phát hiện chênh lệch giữa event được publish và listener hoàn tất. Không cần thêm customer ID hoặc order ID vào label để tính tổng.

Các label trong ví dụ là schema minh họa do ứng dụng chuẩn hóa; tên meter và tag keys thực tế cần được xác nhận từ registry/exposition của phiên bản Spring Modulith đang dùng. Spring Modulith Insight cung cấp metric publication như module.events.published. Metric này đo số event được publish, không chứng minh listener đã xử lý thành công. Nếu cần quan sát consumer, tạo completion/failure metrics riêng với event type và listener/module identifier có cardinality thấp.

## 6. Micrometer Observation: low-cardinality và high-cardinality

Spring Boot sử dụng Micrometer Observation để tạo metrics và traces. Mỗi Observation có metadata KeyValues:

- **Low-cardinality KeyValues** được đưa vào metrics và traces.
- **High-cardinality KeyValues** chỉ được đưa vào traces.

Đây là phân tách về cardinality, không phải cơ chế phân loại quyền riêng tư. Nếu đặt email hoặc user ID vào high-cardinality key, giá trị đó vẫn có thể xuất hiện trong trace backend.

Ví dụ cấu hình Observation:

~~~java
package com.example.shop.inventory;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
class InventoryObservation {

    private final ObservationRegistry observationRegistry;

    InventoryObservation(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    void reserveStock(Runnable operation, String outcome) {
        Observation.createNotStarted("inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("module", "inventory")
                .lowCardinalityKeyValue("event.type", "StockReservationRequested")
                .lowCardinalityKeyValue("outcome", normalizeOutcome(outcome))
                .observe(operation);
    }

    private String normalizeOutcome(String outcome) {
        if (outcome == null) {
            return "other";
        }

        return switch (outcome) {
            case "success", "dependency_error", "insufficient_stock" -> outcome;
            default -> "other";
        };
    }
}
~~~

Observation trên chỉ đưa các giá trị đã được giới hạn vào metrics/traces. Không thêm email, customer ID, order ID hoặc dữ liệu payload vào low-cardinality keys.

Nếu cần correlation tới một thao tác cụ thể, ưu tiên trace context/request correlation ID do hệ thống sinh và tuân theo policy của trace backend. Không dùng identifier cá nhân làm metric tag. Việc thêm high-cardinality attribute vào trace vẫn cần đánh giá quyền truy cập, retention và khả năng liên kết.

## 7. Không dùng hash để lách quy tắc

Một cách làm thường gặp là hash email hoặc customer ID rồi đưa hash vào metric label:

~~~java
String tag = sha256(customer.getEmail());
registry.counter("orders.completed", "customer", tag).increment();
~~~

Đây vẫn là thiết kế không phù hợp:

1. Mỗi người dùng vẫn tạo một giá trị riêng, vì vậy cardinality gần như không giảm.
2. Hash ổn định cho phép liên kết hoạt động của cùng một người qua nhiều metric/time window.
3. Email và số điện thoại có không gian giá trị dễ đoán; hash không khóa có thể bị dò bằng dictionary.
4. Dữ liệu hash vẫn có thể được xem là dữ liệu giả danh nếu có cách liên kết hoặc tái nhận diện.
5. Hash không xóa rủi ro khi dữ liệu được export, lưu trữ, query hoặc chia sẻ.

**Pseudonymization không phải anonymization.** Thay identifier bằng hash không làm nó tự động trở thành dữ liệu vô danh. Với metric, vẫn không đưa hash của user/customer/session ID vào labels.

Nếu có yêu cầu phân tích theo người dùng, chuyển nhu cầu đó sang một hệ thống analytics riêng được thiết kế cho dữ liệu cấp cá nhân, có kiểm soát mục đích, quyền truy cập, retention, pseudonymization và quy trình xóa phù hợp. Metrics vận hành nên nhận kết quả tổng hợp đã được giảm thiểu dữ liệu.

## 8. Chặn tag nhạy cảm bằng MeterFilter

Biện pháp tốt nhất là không tạo tag nhạy cảm ngay từ nguồn. Với instrumentation bên thứ ba hoặc code cũ, MeterFilter có thể là lớp bảo vệ bổ sung.

Ví dụ bỏ một số tag key khỏi mọi meter:

~~~java
package com.example.shop.config;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsPrivacyConfiguration {

    @Bean
    MeterFilter removeSensitiveTags() {
        return MeterFilter.ignoreTags(
                "userId",
                "customerId",
                "email",
                "phone",
                "sessionId",
                "clientIp"
        );
    }
}
~~~

Spring Boot tự đăng ký các MeterFilter bean trên registry được quản lý bởi ứng dụng. Tên tag trong ví dụ phải được thay bằng key thực tế của instrumentation đang dùng.

MeterFilter là lớp phòng vệ ở metrics registry. Nó không tự loại các giá trị tương tự khỏi:

- Micrometer Observation high-cardinality values đã được đưa vào traces.
- Log messages, MDC fields hoặc structured JSON.
- OpenTelemetry spans được tạo trực tiếp ngoài MeterRegistry.
- Một exporter/SDK khác không đi qua registry đó.
- Dữ liệu đã được backend ingest trước khi filter được thêm.

Vì vậy, hãy sửa nguồn instrumentation trước; dùng MeterFilter để ngăn lỗi cấu hình còn sót lại.

### Giới hạn số tag values

Với dimension không nhạy cảm nhưng có nguy cơ cardinality cao, có thể đặt giới hạn:

Đoạn dưới là method fragment bên trong class cấu hình Spring, không phải một class hoàn chỉnh:

~~~java
@Bean
MeterFilter limitUriValues() {
    return MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            100,
            MeterFilter.deny()
    );
}
~~~

Đây là giới hạn bảo vệ cardinality, không phải bộ lọc PII tổng quát. Nếu URI chứa email hoặc ID cá nhân, phải chuẩn hóa URI tại nguồn. Không dựa vào giới hạn 100 giá trị để cho phép một số email/customer IDs lọt vào metric.

## 9. Chuẩn hóa và allowlist giá trị

Không nên lấy label value trực tiếp từ request, event payload hoặc exception. Thay vào đó, chuyển dữ liệu đầu vào thành một giá trị trong tập cho phép:

~~~java
enum Outcome {
    SUCCESS,
    VALIDATION_ERROR,
    DEPENDENCY_ERROR,
    TIMEOUT,
    OTHER
}

static String metricOutcome(String rawOutcome) {
    if (rawOutcome == null) {
        return Outcome.OTHER.name().toLowerCase();
    }

    return switch (rawOutcome) {
        case "success" -> Outcome.SUCCESS.name().toLowerCase();
        case "validation_error" -> Outcome.VALIDATION_ERROR.name().toLowerCase();
        case "dependency_error" -> Outcome.DEPENDENCY_ERROR.name().toLowerCase();
        case "timeout" -> Outcome.TIMEOUT.name().toLowerCase();
        default -> Outcome.OTHER.name().toLowerCase();
    };
}
~~~

Một allowlist giúp giới hạn cardinality và ngăn dữ liệu tùy ý đi vào label. Không đưa raw exception message vào outcome; exception message có thể chứa email, URL, SQL parameters, token hoặc nội dung request.

Đối với HTTP route, dùng route template do framework cung cấp, ví dụ /orders/{orderId}, thay cho expanded path /orders/ORD-938271. Nếu route template vẫn chứa thông tin cá nhân do thiết kế URL, hãy loại route khỏi metric hoặc dùng một route category cố định.

## 10. Phân biệt metrics với logs và traces

Không phải dữ liệu nào bị cấm trong metrics đều có thể chuyển nguyên vẹn sang logs/traces.

| Signal | Mục đích | Chính sách dữ liệu |
| --- | --- | --- |
| Metrics | Xu hướng, tổng hợp, alert, SLO | Chỉ dùng dimension được duyệt, cardinality thấp, không có PII |
| Traces | Theo dõi một execution qua module/dependency | Chỉ thêm attribute cần thiết; high-cardinality không đồng nghĩa an toàn; tránh PII và secrets |
| Logs | Điều tra sự kiện, lỗi và hành vi | Redact/mask dữ liệu nhạy cảm; giới hạn quyền, retention và truy cập |
| Audit records | Bằng chứng hoạt động có yêu cầu kiểm soát | Dùng kho lưu trữ và schema riêng, quyền truy cập/retention được phê duyệt |

Nếu cần hỗ trợ đội hỗ trợ tìm một giao dịch:

1. Dùng trace ID hoặc correlation ID do hệ thống sinh để nối các log liên quan.
2. Không đưa email/customer ID vào metric labels.
3. Nếu cần tham chiếu tới hồ sơ khách hàng, dùng business reference không tiết lộ trực tiếp danh tính và chỉ đặt trong hệ thống được phép lưu dữ liệu đó.
4. Giữ bảng ánh xạ reference với danh tính trong kho dữ liệu nghiệp vụ có phân quyền riêng.
5. Không đưa bảng ánh xạ hoặc secret dùng để giải mã vào telemetry backend.

Trace ID cũng là một identifier có thể liên kết nhiều hoạt động. Dù không phải email hay tên thật, cần hạn chế việc gắn trace ID với user profile hoặc đưa trace ID thành label trong metrics.

## 11. Những điểm rò rỉ thường bị bỏ sót

PII có thể đi vào metrics gián tiếp qua:

- URL path hoặc query string có email, phone, account number.
- Exception message có dữ liệu request hoặc SQL parameter.
- Tag được copy từ event payload.
- Tenant/customer ID được thêm làm common tag.
- User-agent hoặc client-provided header chứa định danh.
- Metric name được tạo động từ giá trị đầu vào.
- Label value được nối từ tên module, operation hoặc error message không được kiểm soát.
- Dashboard variables hoặc recording rules giữ lại dimension nhạy cảm.

Kiểm tra cả custom meters lẫn auto-instrumentation của HTTP, database, messaging và client libraries. Không giả định framework tự động loại mọi dữ liệu nhạy cảm khỏi mọi observation.

### Không dùng raw URL làm label

Sai:

~~~java
registry.counter("http.requests", "url", request.getRequestURL().toString())
        .increment();
~~~

Tốt hơn:

~~~java
registry.counter("http.requests",
        "route", "/orders/{orderId}",
        "method", "GET")
        .increment();
~~~

Nếu framework đã cung cấp HTTP server observation, ưu tiên dùng instrumentation chuẩn và cấu hình URI template phù hợp. Tránh thêm một meter custom trùng với meter có sẵn.

### Không dùng exception message làm label

Sai:

~~~java
registry.counter("payment.failures",
        "reason", exception.getMessage())
        .increment();
~~~

Tốt hơn:

~~~java
registry.counter("payment.failures",
        "reason", classify(exception))
        .increment();
~~~

Hàm classify nên trả về một tập giá trị cố định như timeout, declined, dependency_error hoặc other. Chi tiết exception đã redact có thể được ghi trong log/trace theo policy riêng.

## 12. Kiểm tra metric registry trước khi export

Thêm kiểm thử để đảm bảo tag key nhạy cảm không xuất hiện trong registry:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import java.util.stream.Collectors;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.junit.jupiter.api.Test;

class MetricsPrivacyTest {

    @Test
    void sensitiveTagsAreRemovedFromMeters() {
        var registry = new SimpleMeterRegistry();
        registry.config().meterFilter(
                MeterFilter.ignoreTags("userId", "email", "customerId")
        );

        registry.counter(
                "orders.completed",
                "module", "order",
                "outcome", "success",
                "userId", "synthetic-user-123"
        ).increment();

        Set<String> tagKeys = registry.getMeters().stream()
                .flatMap(meter -> meter.getId().getTags().stream())
                .map(tag -> tag.getKey())
                .collect(Collectors.toSet());

        assertTrue(tagKeys.contains("module"));
        assertTrue(tagKeys.contains("outcome"));
        assertTrue(tagKeys.stream().noneMatch(
                Set.of("userId", "email", "customerId")::contains
        ));
    }
}
~~~

Đây là kiểm thử cho MeterFilter, không thay thế kiểm thử Observation, tracing và exporter. Trong ứng dụng thực, hãy kiểm tra cả meter registry do Spring Boot tạo và exposition của từng registry/exporter đang bật.

### Kiểm tra Prometheus exposition

Trong môi trường test, scrape endpoint Prometheus và xác nhận:

- Không có label key như email, user_id, customer_id, phone, session_id.
- Không có giá trị test giả lập như synthetic-user-123 hoặc privacy-canary@example.invalid.
- URL được xuất dưới dạng route template, không chứa path ID hoặc query string.
- Label values chỉ thuộc allowlist.
- Số series không tăng tuyến tính theo số người dùng/giao dịch được tạo trong test.

Không dùng email, số điện thoại hoặc định danh thật làm canary. Dùng giá trị giả lập chỉ dành cho kiểm thử.

## 13. High Cardinality Tags Detector

Micrometer cung cấp High Cardinality Tags Detector để phát hiện khả năng một meter name đang tạo quá nhiều meters do tag values không giới hạn.

Ví dụ bật detector trên registry:

~~~java
registry.config().withHighCardinalityTagsDetector();
~~~

Hoặc cấu hình threshold và hành động khi phát hiện:

~~~java
import io.micrometer.core.instrument.HighCardinalityTagsDetector;

import java.time.Duration;

registry.config().withHighCardinalityTagsDetector(r ->
        new HighCardinalityTagsDetector.Builder(r).threshold(1000)
                .delay(Duration.ofMinutes(5))
                .highCardinalityMeterInfoConsumer(info ->
                        logger.warn("Potential high cardinality meter: {} ({})",
                                info.getName(), info.getCount()))
                .build()
);
~~~

Đây là fragment giả định registry và logger đã được inject vào bean cấu hình.

Detector đếm số meter có cùng tên và cảnh báo khi vượt ngưỡng. Nó hữu ích để phát hiện high-cardinality tags, nhưng không xác định tag nào chứa PII, không phát hiện mọi trường hợp metric name được tạo động và không chứng minh dữ liệu an toàn.

Hãy dùng detector như một cảnh báo kỹ thuật bên cạnh allowlist metric tags, MeterFilter, kiểm thử privacy, review instrumentation và kiểm tra exposition/backend labels.

Không chỉ tăng threshold khi detector cảnh báo. Tìm nguồn tạo nhiều meters và loại dimension không cần thiết.

## 14. Kiểm soát dữ liệu trong traces và logs

Micrometer Observation có thể đưa high-cardinality KeyValues vào traces. Điều này giúp tracing backend tìm một execution cụ thể nhưng cũng có thể tạo kho dữ liệu chứa identifier cá nhân.

Trước khi thêm attribute vào trace, hãy hỏi:

1. Giá trị có phải dữ liệu cá nhân hoặc bí mật không?
2. Nó có thực sự cần để điều tra trace không?
3. Có thể thay bằng operation/outcome/category hoặc reference ít nhạy cảm hơn không?
4. Tracing backend có quyền truy cập và retention phù hợp không?
5. Giá trị có thể bị copy vào logs, span events hoặc error reports không?

Với logs:

- Không log access token, password, cookie hoặc authorization header.
- Không log toàn bộ request/response body theo mặc định.
- Redact/mask email, phone, payment data và identifier không cần thiết.
- Giới hạn quyền đọc log và thời hạn lưu trữ.
- Sanitize dữ liệu đầu vào để tránh log injection.

Redaction ở Collector hoặc log backend là defense-in-depth. Tốt nhất là tránh tạo dữ liệu nhạy cảm tại nguồn vì dữ liệu có thể đã đi qua queue, file tạm hoặc exporter trước khi được redact.

## 15. Xử lý khi PII đã bị đưa vào metric

Nếu phát hiện metric chứa dữ liệu cá nhân:

1. **Ngăn phát sinh mới:** sửa instrumentation hoặc áp dụng filter ở nguồn để dừng export giá trị nhạy cảm.
2. **Xác định phạm vi:** metric names, label keys, thời điểm bắt đầu, service instances, registry và backend nhận dữ liệu.
3. **Xác định bản sao:** kiểm tra Prometheus, remote-write destinations, long-term storage, dashboards, snapshots và backups.
4. **Đánh giá rủi ro:** xác định dữ liệu nào bị lộ, ai có quyền truy cập, khả năng liên kết/tái nhận diện và thời gian lưu.
5. **Xử lý dữ liệu đã lưu:** thực hiện quy trình xóa/retention hoặc xử lý sự cố theo chính sách tổ chức và khả năng của backend. Xóa label khỏi code không xóa time series đã ingest.
6. **Kiểm tra consumer:** cập nhật dashboard, recording rules, alert và query không còn phụ thuộc label nhạy cảm.
7. **Xác minh:** scrape lại, kiểm tra backend và xác nhận không còn giá trị test/production bị rò rỉ.
8. **Ghi nhận:** lưu nguyên nhân gốc, phạm vi ảnh hưởng, quyết định xử lý và kiểm thử ngăn tái diễn.

Không tự xóa dữ liệu production theo cách thủ công khi chưa xác định retention, legal hold, backup và quy trình incident/data request của tổ chức.

## 16. Checklist review instrumentation

### Trước khi merge

- [ ] Mỗi metric có mục đích vận hành cụ thể.
- [ ] Tên metric và tag keys được định nghĩa rõ.
- [ ] Mọi tag value đến từ enum/allowlist hoặc route template.
- [ ] Không có email, phone, name, user/customer ID hoặc session/request ID trong metric labels.
- [ ] Không có token, cookie, query string hoặc exception message trong label.
- [ ] Không dùng hash của identifier cá nhân để tạo metric dimension.
- [ ] Cardinality được ước lượng theo tổ hợp tag values.
- [ ] Custom Observation tách low-cardinality values khỏi metadata chỉ dành cho trace.
- [ ] MeterFilter được dùng như lớp bảo vệ bổ sung khi cần.
- [ ] Có unit/integration test kiểm tra tag keys và values.

### Trước khi deploy

- [ ] Prometheus exposition không chứa dữ liệu cá nhân test.
- [ ] Dashboard/alert chỉ group theo dimension đã duyệt.
- [ ] Collector/exporter không thêm lại label nhạy cảm.
- [ ] Logs/traces có redaction, access control và retention phù hợp.
- [ ] Backend và backup có chính sách xóa/retention phù hợp.
- [ ] Có owner chịu trách nhiệm cho metric schema.

## 17. Bài thực hành

Chuẩn bị ứng dụng Spring Modulith có module order, inventory và billing, Micrometer, Actuator và Prometheus registry.

1. Tạo một counter module.events.published với labels module và event_type.
2. Tạo metric listener completion với module, event_type và outcome.
3. Tạo một meter thử nghiệm có tag email bằng dữ liệu giả lập.
4. Thêm MeterFilter để bỏ email, userId và customerId.
5. Kiểm tra registry và Prometheus exposition không còn các tag keys đó.
6. Thử đưa email vào Observation high-cardinality metadata; xác nhận giá trị vẫn có thể xuất hiện trong trace và loại bỏ nó khỏi instrumentation.
7. Thử thêm URL chứa ID vào HTTP metric; thay bằng route template.
8. Thêm High Cardinality Tags Detector và tạo nhiều giá trị synthetic để quan sát cảnh báo.
9. Kiểm tra dashboard không group theo user/customer identifier.
10. Viết test tự động fail nếu một metric mới có tag key thuộc danh sách cấm.
11. Ghi lại số series trước/sau và chứng minh số series không tăng theo số lượng synthetic users.
12. Xác nhận logs/traces chỉ giữ metadata được phê duyệt và có chính sách truy cập/retention.

Mẫu ghi kết quả:

| Kịch bản | Tag/attribute | Registry metric | Trace | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Event publication | module, event_type | Có | Có thể có | Được phép nếu allowlist |
| Listener outcome | outcome | Có | Có thể có | Chỉ dùng enum |
| Email test | email | Không | Không nếu không có mục đích được duyệt | Bị chặn tại nguồn/filter |
| Customer ID test | customerId | Không | Không mặc định | Không xuất ra telemetry |
| Route có ID | /orders/123 | Không | Có thể được chuẩn hóa | Metric dùng route template |
| Exception có payload | raw message | Không | Không mặc định | Dùng error category cố định |

### Câu hỏi tự kiểm tra

1. Vì sao mỗi labelset mới có thể tạo một time series mới?
2. Cardinality thấp có đủ để chứng minh dữ liệu không nhạy cảm không?
3. Vì sao high-cardinality metadata userId vẫn có rủi ro riêng tư?
4. Hash email có làm giảm cardinality không?
5. Vì sao module.events.published phù hợp hơn metric có order_id?
6. MeterFilter bảo vệ được những đường export nào và không bảo vệ được những đường nào?
7. Vì sao route template an toàn hơn full URL?
8. High Cardinality Tags Detector phát hiện điều gì và không phát hiện điều gì?
9. Nếu metric backend đã lưu email, xóa tag trong code có xóa dữ liệu lịch sử không?
10. Khi cần phân tích theo từng khách hàng, nên dùng loại hệ thống và kiểm soát nào?

## 18. Tổng kết

Metrics là dữ liệu tổng hợp phục vụ vận hành. Mỗi tổ hợp metric name và label values có thể tạo một time series, vì vậy các identifier không giới hạn như email, phone, user/customer ID, session ID, request ID hoặc trace ID vừa làm tăng cardinality vừa tạo rủi ro riêng tư. Cardinality thấp cũng không tự động có nghĩa dữ liệu được phép sử dụng; cần đánh giá cả độ nhạy cảm và khả năng liên kết.

Trong Spring Boot/Micrometer, hãy dùng low-cardinality keys có allowlist như module, event type, operation và outcome. Không đưa PII vào low-cardinality hoặc high-cardinality observation values. High-cardinality values chỉ đi vào traces theo cơ chế mặc định của Observation, nhưng trace backend vẫn cần chính sách riêng. MeterFilter và High Cardinality Tags Detector là lớp phòng vệ bổ sung, không thay thế việc sửa instrumentation tại nguồn.

Với Spring Modulith, metrics theo module/event type và listener outcome đủ để quan sát tương tác giữa các application modules. Khi cần điều tra một giao dịch, dùng logs/traces đã redact và được bảo vệ phù hợp. Kiểm thử exposition, tag allowlist và quy trình xử lý dữ liệu đã ingest để bảo đảm telemetry hữu ích mà không trở thành nơi lưu trữ dữ liệu cá nhân.

## Tài liệu tham khảo

- [Spring Boot — Observability: Low and High Cardinality KeyValues](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html).
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html).
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).
- [Prometheus — Instrumentation: Do not overuse labels](https://prometheus.io/docs/practices/instrumentation/).
- [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/).
- [OpenTelemetry — How to write semantic conventions: PII attributes](https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/).
- [OWASP — Logging Cheat Sheet: Data to exclude and protection](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
