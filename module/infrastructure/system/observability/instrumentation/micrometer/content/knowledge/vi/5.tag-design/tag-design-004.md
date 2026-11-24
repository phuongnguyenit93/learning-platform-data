# Chuẩn hóa URI, trạng thái và loại lỗi thành tập giá trị được kiểm soát

## Mục tiêu

Một metric HTTP thường cần cho biết request đi đến endpoint nào, kết thúc với trạng thái gì và thất bại vì nguyên nhân nào. Những thông tin này giúp nhóm vận hành tìm ra endpoint chậm, tỷ lệ lỗi tăng ở nhóm request nào và dịch vụ phụ thuộc nào đang gặp sự cố.

Nếu đưa trực tiếp URI, mã trạng thái hoặc tên exception từ request vào tag mà không kiểm soát, mỗi giá trị mới có thể tạo thêm một meter/time series. Ví dụ, các URI như /orders/10001, /orders/10002 và /orders/10003 thực chất cùng thuộc endpoint /orders/{orderId}. Ghi nhận từng URI cụ thể làm dữ liệu tăng theo số lượng đơn hàng mà không đem lại góc nhìn vận hành tương xứng.

Thiết kế tag tốt cần biến dữ liệu đầu vào thành một tập giá trị nhỏ, ổn định và có ý nghĩa. Bài này tập trung vào ba chiều thường gặp:

- **URI:** dùng route template hoặc allow-list endpoint.
- **Trạng thái:** dùng HTTP status class hoặc một tập status code đã xác định.
- **Loại lỗi:** ánh xạ exception và lỗi nghiệp vụ vào taxonomy hữu hạn.

Sau bài này, bạn có thể thiết kế bộ tag cho metrics HTTP, viết hàm chuẩn hóa, giới hạn cardinality, tích hợp với Spring Boot Observation và kiểm thử các giá trị ngoài allow-list.

## Vì sao phải chuẩn hóa tag?

Micrometer xác định một meter bằng tên và các dimension/tag của nó. Mỗi tổ hợp tên cùng giá trị tag có thể trở thành một meter riêng. Khi một tag nhận dữ liệu gần như không giới hạn, số meter tăng theo dữ liệu thực tế.

Ví dụ, một metric có ba tag:

| Tag | Giá trị được kiểm soát | Giá trị không kiểm soát |
|---|---|---|
| uri | /orders/{orderId} | /orders/10001 |
| status_class | 2xx, 4xx, 5xx | Chuỗi trạng thái tùy ý từ request |
| error_type | timeout, validation, internal | Message exception hoặc tên lỗi do người dùng nhập |

Một tổ hợp tag đại diện cho một nhóm request có cùng đặc điểm. Nhờ chuẩn hóa, dashboard có thể trả lời câu hỏi như “p95 của endpoint orders trong nhóm lỗi 5xx là bao nhiêu?” mà không tạo một time series cho từng đơn hàng.

Cardinality là số lượng tổ hợp giá trị có thể xuất hiện. Có thể ước lượng giới hạn trên bằng cách nhân số giá trị của từng tag. Nếu một metric có 4 route, 5 nhóm trạng thái, 5 loại lỗi và 5 HTTP method thì có tối đa:

\[
4 \times 5 \times 5 \times 5 = 500
\]

tổ hợp trên mỗi instance. Nếu chạy 10 instance và backend phân biệt từng instance, số chuỗi time series có thể lên tới khoảng 5.000. Đây chỉ là ước lượng cho một metric; histogram có thể tạo thêm chuỗi cho từng bucket và các thống kê đi kèm.

Các giá trị như user ID, request ID, trace ID, email, timestamp, full URL hoặc dữ liệu người dùng nhập thường có cardinality cao. Nếu cần tra cứu một request hoặc một người dùng cụ thể, hãy ghi dữ liệu đó vào log hoặc trace. Observation API cho phép đánh dấu metadata high-cardinality để dùng ở trace/log; metadata này không nên trở thành tag metrics.

## Thiết kế tag URI

### Dùng URI template thay cho URI thực tế

URI thực tế thường chứa dữ liệu động:

| URI thực tế | URI template |
|---|---|
| /orders/10001 | /orders/{orderId} |
| /orders/10002 | /orders/{orderId} |
| /customers/8f2a... | /customers/{customerId} |
| /products/42/reviews/7 | /products/{productId}/reviews/{reviewId} |

Các request trên cùng một route nên dùng chung một giá trị tag. Router của framework thường biết route nào đã được khớp và có thể cung cấp route template. Hãy lấy template từ framework sau khi định tuyến thay vì tự ghép URL từ request.

Với Spring Boot, Actuator tự instrument các request được xử lý bởi Spring MVC và Spring WebFlux bằng metric mặc định http.server.requests. Có thể bổ sung tag bằng bean kế thừa DefaultServerRequestObservationConvention, hoặc thay toàn bộ tag bằng implementation của ServerRequestObservationConvention. Cách tùy chỉnh tương ứng cũng có extension point riêng cho WebFlux. Kiểm tra tài liệu của đúng phiên bản Spring Boot đang dùng vì package và API có thể thay đổi giữa các major version.

Nếu framework không cung cấp route template, hãy dùng allow-list các endpoint mà ứng dụng hỗ trợ. Không lấy nguyên request URI rồi thay vài chuỗi theo phỏng đoán. Một quy tắc thay thế thiếu trường hợp có thể để lọt ID, slug, mã giao dịch hoặc dữ liệu nhạy cảm vào metrics.

### Không đưa query string vào tag

Các URL sau có thể cùng trỏ đến một route:

~~~text
/search?q=micrometer&page=1
/search?q=java&page=2
/search?q=secret-token&page=1
~~~

Tag URI nên là /search. Query string có thể chứa từ khóa, email, token hoặc dữ liệu cá nhân; đồng thời mỗi giá trị truy vấn có thể tạo một chuỗi metrics mới. Nếu cần phân tích tham số tìm kiếm, hãy đo theo nhóm đã định nghĩa như query_type=product hoặc page_bucket=1-5, sau khi xác định rõ nhu cầu và giới hạn giá trị.

Không dùng các dữ liệu sau làm tag URI:

- Full URL gồm scheme, host, path và query string.
- Path đã thay biến bằng ID thật, UUID, slug hoặc mã giao dịch.
- Fragment sau ký tự #.
- Giá trị path do người dùng tự nhập nếu chưa được ánh xạ vào route đã biết.

### Chuẩn hóa URI bằng allow-list

Một hàm chuẩn hóa đơn giản có thể nhận route template và chỉ cho phép những route ứng dụng cần theo dõi:

~~~java
public final class UriTagNormalizer {
    private UriTagNormalizer() {
    }

    public static String normalize(String routeTemplate) {
        if (routeTemplate == null) {
            return "UNMATCHED";
        }

        return switch (routeTemplate) {
            case "/orders" -> "/orders";
            case "/orders/{orderId}" -> "/orders/{orderId}";
            case "/payments" -> "/payments";
            case "/customers/{customerId}" -> "/customers/{customerId}";
            default -> "UNMATCHED";
        };
    }
}
~~~

Kết quả:

| Đầu vào | Giá trị tag |
|---|---|
| /orders | /orders |
| /orders/{orderId} | /orders/{orderId} |
| /orders/10001 | UNMATCHED |
| /orders/10001?expand=items | UNMATCHED |
| null | UNMATCHED |

Hàm này cố ý chỉ chấp nhận route template. Nếu đưa URI thực tế vào, nó không cố suy đoán ID nào cần thay; giá trị không được nhận diện sẽ rơi vào một nhóm cố định. Trong ứng dụng thực tế, hãy điều chỉnh allow-list theo route template thật của router.

Nếu cần theo dõi mọi route trong một ứng dụng có nhiều endpoint, hãy bảo đảm router cung cấp template đã chuẩn hóa và có cơ chế fallback cố định. Không tạo tag bằng cách nối trực tiếp chuỗi path.

## Thiết kế tag trạng thái HTTP

### Chọn giữa status code và status class

HTTP status code nằm trong miền số hữu hạn, thường từ 100 đến 599. Vì vậy, dùng mã như 200, 404 hoặc 503 không tự động là cardinality vô hạn. Tuy nhiên, nếu mục tiêu là dashboard tổng quan, status class thường đủ và giúp giảm số chiều:

| Status class | Ý nghĩa | Ví dụ |
|---|---|---|
| 1xx | Informational | 100, 101 |
| 2xx | Success | 200, 201, 204 |
| 3xx | Redirection | 301, 302, 304 |
| 4xx | Client error | 400, 401, 404, 429 |
| 5xx | Server error | 500, 502, 503 |
| other | Giá trị ngoài miền hợp lệ hoặc chưa xác định | 0, 700 |

Hãy chọn theo câu hỏi cần trả lời:

- Dùng status class khi cần so sánh tỷ lệ thành công, redirect, lỗi client và lỗi server.
- Dùng status code cụ thể khi cần phân biệt các tình huống như 401, 404, 429 hoặc 503.
- Có thể giữ cả hai chiều nếu chúng thực sự phục vụ các truy vấn khác nhau, nhưng cần tính tổng số tổ hợp tag.

Các convention HTTP của Spring phân biệt status code và outcome. Ví dụ, tài liệu Spring Boot mô tả outcome 4xx là CLIENT_ERROR và 5xx là SERVER_ERROR; với Jersey, tag status chứa mã HTTP và uri chứa URI template nếu xác định được. Chi tiết tag mặc định có thể phụ thuộc integration và phiên bản framework. Khi dùng metric có sẵn, hãy kiểm tra các tag thực tế để tránh thêm một metric custom trùng lặp chỉ nhằm đếm lại cùng dữ liệu.

### Hàm chuẩn hóa status class

~~~java
public final class StatusTagNormalizer {
    private StatusTagNormalizer() {
    }

    public static String toStatusClass(int statusCode) {
        if (statusCode >= 100 && statusCode < 200) {
            return "1xx";
        }
        if (statusCode >= 200 && statusCode < 300) {
            return "2xx";
        }
        if (statusCode >= 300 && statusCode < 400) {
            return "3xx";
        }
        if (statusCode >= 400 && statusCode < 500) {
            return "4xx";
        }
        if (statusCode >= 500 && statusCode < 600) {
            return "5xx";
        }
        return "other";
    }
}
~~~

Không lấy chuỗi trạng thái từ header, query parameter hoặc nội dung exception. Giá trị tag phải được suy ra từ response status đã được server xác định. Với status code cụ thể, hãy xác nhận nó thuộc miền HTTP hợp lệ trước khi ghi nhận.

### Phân biệt status và error

HTTP status mô tả kết quả trao đổi HTTP. Loại lỗi mô tả nhóm nguyên nhân kỹ thuật hoặc nghiệp vụ. Hai thông tin này liên quan nhưng không đồng nghĩa:

- Request trả 404 có thể là kết quả hợp lệ khi tài nguyên không tồn tại; không nhất thiết là lỗi hệ thống.
- Request trả 503 thường phản ánh dịch vụ không thể phục vụ, nhưng nguyên nhân có thể là timeout, dependency unavailable hoặc quá tải.
- Request trả 400 có thể là dữ liệu đầu vào không hợp lệ; không nên gộp nó với lỗi nội bộ 500.

Vì vậy, giữ hai dimension riêng giúp dashboard phân biệt “response thuộc nhóm nào” và “nguyên nhân được phân loại ra sao”.

## Thiết kế taxonomy cho loại lỗi

### Vì sao không dùng exception message?

Exception message thường chứa dữ liệu biến động:

~~~text
Order 10001 was not found
Order 10002 was not found
Connection to db-10.internal timed out after 3000ms
Invalid email alice@example.com
~~~

Nếu dùng message làm tag, mỗi order ID, hostname hoặc email có thể tạo thêm một giá trị mới. Message cũng có thể chứa dữ liệu nhạy cảm và thay đổi theo phiên bản thư viện.

Tên class exception ít biến động hơn message, nhưng vẫn có thể tạo ra quá nhiều loại nếu ứng dụng có nhiều thư viện hoặc exception tùy chỉnh. Với metrics, hãy ánh xạ exception vào một taxonomy nhỏ do ứng dụng kiểm soát.

### Đề xuất taxonomy

Một taxonomy cơ bản có thể gồm:

| Giá trị error_type | Ý nghĩa | Ví dụ |
|---|---|---|
| none | Không có exception được ghi nhận | Request hoàn tất bình thường |
| validation | Dữ liệu đầu vào không hợp lệ | Thiếu trường bắt buộc |
| not_found | Không tìm thấy tài nguyên | Order không tồn tại |
| conflict | Xung đột trạng thái hoặc tài nguyên | Trùng mã đơn |
| timeout | Hết thời gian chờ | Gọi payment provider quá hạn |
| dependency | Dịch vụ hoặc hệ thống phụ thuộc lỗi | Database unavailable |
| internal | Lỗi nội bộ chưa phân loại cụ thể | Unexpected exception |

Tập giá trị cần phù hợp với domain. Không cần tạo đủ mọi loại nếu ứng dụng không có các tình huống đó. Điều quan trọng là các nhóm có định nghĩa rõ ràng, ổn định qua các phiên bản và không tăng theo từng exception mới.

### Ánh xạ exception vào taxonomy

Ví dụ dưới đây minh họa cách ánh xạ một số exception Java vào nhóm lỗi. Trong dự án thật, nên ưu tiên exception domain của ứng dụng và phân loại ở lớp xử lý lỗi:

~~~java
import java.io.IOException;
import java.util.concurrent.TimeoutException;

public final class ErrorTagNormalizer {
    private ErrorTagNormalizer() {
    }

    public static String normalize(Throwable error) {
        if (error == null) {
            return "none";
        }
        // Chỉ dùng ánh xạ này nếu ứng dụng quy ước IllegalArgumentException là lỗi đầu vào.
        if (error instanceof IllegalArgumentException) {
            return "validation";
        }
        if (error instanceof TimeoutException) {
            return "timeout";
        }
        // Chỉ phân loại IOException là lỗi dependency khi nó đến từ I/O tới hệ thống phụ thuộc.
        if (error instanceof IOException) {
            return "dependency";
        }
        return "internal";
    }
}
~~~

Đây là ví dụ tối giản. Trong ứng dụng thực tế, có thể bổ sung ánh xạ cho các exception nghiệp vụ như ResourceNotFoundException hoặc DuplicateOrderException. Hãy đặt các nhánh theo thứ tự từ loại cụ thể đến loại tổng quát để exception con được phân loại đúng.

Không dùng error.getMessage(), stack trace, tên class đầy đủ có chứa dữ liệu sinh động hoặc tên exception do client gửi lên làm tag. Nếu cần điều tra chi tiết, ghi exception vào log có correlation ID hoặc gắn dữ liệu high-cardinality vào trace.

Một exception được xử lý bên trong controller có thể không còn xuất hiện tại lớp instrumentation bên ngoài. Khi đó, hãy truyền loại lỗi đã chuẩn hóa từ exception handler hoặc gắn thông tin vào Observation context theo extension point của framework. Không suy ra chính xác loại lỗi chỉ từ HTTP status nếu status có thể đại diện cho nhiều nguyên nhân.

## Kết hợp ba chiều trong instrumentation

Sau khi có các hàm chuẩn hóa, lớp instrumentation có thể nhận route template, response status, exception và thời lượng request. Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public final class HttpRequestMetrics {
    private final MeterRegistry registry;

    public HttpRequestMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCompletedRequest(
            String routeTemplate,
            int statusCode,
            Throwable error,
            Duration elapsed) {

        Timer.builder("http.server.request.duration")
                .description("Thời gian xử lý HTTP request")
                .tag("uri", UriTagNormalizer.normalize(routeTemplate))
                .tag("status_class", StatusTagNormalizer.toStatusClass(statusCode))
                .tag("error_type", ErrorTagNormalizer.normalize(error))
                .register(registry)
                .record(elapsed);
    }
}
~~~

Phương thức này được gọi sau khi request hoàn tất. Lớp tích hợp HTTP cần truyền vào route template đã được router xác định, response status cuối cùng và exception đã được xử lý/phân loại. Thời lượng phải được đo từ thời điểm bắt đầu xử lý đến thời điểm kết thúc theo định nghĩa của metric.

Ví dụ các kết quả ghi nhận:

| Route template | HTTP status | Exception | Tag được ghi |
|---|---:|---|---|
| /orders/{orderId} | 200 | Không có | /orders/{orderId}, 2xx, none |
| /orders/{orderId} | 404 | Không có | /orders/{orderId}, 4xx, none |
| /payments | 503 | TimeoutException | /payments, 5xx, timeout |
| URI không khớp allow-list | 500 | IOException | UNMATCHED, 5xx, dependency |

Metric này chỉ là ví dụ custom để minh họa taxonomy. Nếu Spring Boot đã cung cấp http.server.requests với các chiều cần thiết, hãy ưu tiên tùy chỉnh Observation convention của metric hiện có. Chỉ tạo metric riêng khi nó trả lời một câu hỏi bổ sung hoặc có ý nghĩa khác rõ ràng.

## Tích hợp với Spring Boot Observation

Spring Boot Actuator tự instrument request của Spring MVC và Spring WebFlux thông qua Micrometer Observation. Metric mặc định là http.server.requests. Có thể thêm tag bằng DefaultServerRequestObservationConvention hoặc thay bộ tag bằng ServerRequestObservationConvention.

Khi cần chuẩn hóa tag:

1. Lấy URI template từ thông tin định tuyến, không lấy raw request URI.
2. Chuẩn hóa giá trị vào allow-list route.
3. Lấy status code từ response cuối cùng và nhóm thành status class nếu dashboard không cần mã chi tiết.
4. Ánh xạ exception vào error taxonomy nhỏ.
5. Giữ nguyên các tag chuẩn mà dashboard đang sử dụng, hoặc thay đổi có chủ đích và cập nhật dashboard/alert đi kèm.

Spring Boot có thể không ghi nhận exception đã được xử lý trong controller như một exception tag của request metrics. Nếu cần quan sát các lỗi đã được chuyển thành response bình thường, ứng dụng phải cung cấp thông tin exception cho observation theo cơ chế request attribute hoặc convention tương ứng với phiên bản framework.

Không nên thêm tag động bằng MeterFilter dựa trên request context. MeterFilter được thiết kế để chấp nhận/từ chối meter, biến đổi meter ID hoặc cấu hình thống kê; việc lấy thông tin động theo từng request nên được thực hiện tại instrumentation hoặc Observation convention.

## Dùng MeterFilter làm hàng rào dự phòng

Chuẩn hóa tại nguồn là biện pháp chính. MeterFilter có thể bổ sung giới hạn để tránh một lỗi instrumentation làm số meter tăng quá mức.

Ví dụ giới hạn số giá trị uri cho metric custom:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

public final class MetricsRegistryConfiguration {
    private MetricsRegistryConfiguration() {
    }

    public static void applySafetyLimit(MeterRegistry registry) {
        registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "http.server.request.duration",
                        "uri",
                        20,
                        MeterFilter.deny()
                )
        );
    }
}
~~~

Hãy cài filter trong giai đoạn cấu hình registry, trước khi meter đầu tiên được đăng ký. Filter này giới hạn số giá trị tag uri được đăng ký cho metric có tên bắt đầu bằng http.server.request.duration. Khi vượt giới hạn, meter mới bị từ chối đăng ký. Filter không tự chuyển URI lạ thành UNMATCHED; do đó, không xem nó là hàm chuẩn hóa. Nếu filter kích hoạt, dữ liệu mới có thể bị bỏ, vì vậy cần log hoặc cảnh báo để tìm và sửa nguyên nhân tại instrumentation.

Một số phiên bản Micrometer có thêm High Cardinality Tags Detector để phát hiện tên meter có quá nhiều meter khác nhau. Detector hữu ích trong kiểm thử và giám sát, nhưng chỉ là công cụ phát hiện. Nó không thay thế allow-list và cũng không phát hiện mọi trường hợp như giá trị ngẫu nhiên được ghép vào tên metric.

## Kiểm thử quy tắc chuẩn hóa

Hãy kiểm thử các nhóm đầu vào sau:

- Route hợp lệ được chấp nhận đúng template.
- URI thực tế chứa ID hoặc query string bị đưa về nhóm fallback.
- Status code thuộc các lớp 1xx đến 5xx được phân loại chính xác.
- Status code ngoài miền hợp lệ trở thành other.
- Không có exception trở thành none.
- Exception đã biết được ánh xạ đúng taxonomy.
- Exception chưa biết trở thành internal.

Ví dụ unit test cho các hàm chuẩn hóa:

~~~java
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.concurrent.TimeoutException;

import static org.assertj.core.api.Assertions.assertThat;

class TagNormalizerTest {
    @Test
    void normalizesUriToKnownRouteTemplates() {
        assertThat(UriTagNormalizer.normalize("/orders/{orderId}"))
                .isEqualTo("/orders/{orderId}");
        assertThat(UriTagNormalizer.normalize("/orders/10001"))
                .isEqualTo("UNMATCHED");
        assertThat(UriTagNormalizer.normalize(null))
                .isEqualTo("UNMATCHED");
    }

    @Test
    void groupsHttpStatusCodes() {
        assertThat(StatusTagNormalizer.toStatusClass(201)).isEqualTo("2xx");
        assertThat(StatusTagNormalizer.toStatusClass(404)).isEqualTo("4xx");
        assertThat(StatusTagNormalizer.toStatusClass(503)).isEqualTo("5xx");
        assertThat(StatusTagNormalizer.toStatusClass(700)).isEqualTo("other");
    }

    @Test
    void mapsExceptionsToFiniteErrorTypes() {
        assertThat(ErrorTagNormalizer.normalize(null)).isEqualTo("none");
        assertThat(ErrorTagNormalizer.normalize(new TimeoutException()))
                .isEqualTo("timeout");
        assertThat(ErrorTagNormalizer.normalize(new IOException()))
                .isEqualTo("dependency");
        assertThat(ErrorTagNormalizer.normalize(new IllegalStateException()))
                .isEqualTo("internal");
    }
}
~~~

Ngoài unit test cho hàm chuẩn hóa, nên kiểm tra meter thực tế trong SimpleMeterRegistry:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import static org.assertj.core.api.Assertions.assertThat;

class HttpRequestMetricsTest {
    @Test
    void recordsOnlyNormalizedTagValues() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            HttpRequestMetrics metrics = new HttpRequestMetrics(registry);

            metrics.recordCompletedRequest(
                    "/orders/{orderId}",
                    503,
                    new TimeoutException(),
                    Duration.ofMillis(25)
            );

            Timer timer = registry.get("http.server.request.duration")
                    .tag("uri", "/orders/{orderId}")
                    .tag("status_class", "5xx")
                    .tag("error_type", "timeout")
                    .timer();

            assertThat(timer.count()).isEqualTo(1);
        } finally {
            registry.close();
        }
    }
}
~~~

Một bài kiểm thử tích hợp có thể tạo nhiều request với ID khác nhau rồi xác minh chúng cùng đi vào một URI template. Đồng thời gửi một số route không nhận diện được và xác nhận chỉ xuất hiện một giá trị fallback. Đây là cách kiểm tra cardinality theo hành vi thật của router, không chỉ kiểm tra riêng hàm tiện ích.

## Checklist trước khi đưa tag vào production

1. Mỗi tag có danh sách giá trị hợp lệ hoặc quy tắc chuẩn hóa rõ ràng.
2. URI lấy từ route template; query string và path variable không xuất hiện trong tag.
3. Status lấy từ response cuối cùng; dùng status class nếu không cần phân tích từng mã.
4. Error type là taxonomy nghiệp vụ/kỹ thuật hữu hạn; không dùng message hoặc stack trace.
5. Giá trị null, không xác định và ngoài allow-list đều có fallback cố định.
6. Ước lượng số tổ hợp tag, tính cả method, instance, environment và histogram.
7. Không tạo metric custom trùng với metric HTTP mặc định nếu không có mục đích riêng.
8. Có unit test và integration test cho các trường hợp bình thường lẫn dữ liệu bất thường.
9. Có cảnh báo khi MeterFilter từ chối meter hoặc detector phát hiện cardinality tăng đột biến.
10. Dashboard và alert sử dụng đúng tên tag, taxonomy và ý nghĩa của metric.

## Kết luận

Thiết kế tag URI, status và error type cần bắt đầu từ câu hỏi vận hành, sau đó xác định tập giá trị hữu hạn. URI nên là route template, status có thể được nhóm thành status class, còn exception cần được ánh xạ vào taxonomy ổn định. Chuẩn hóa ở instrumentation hoặc Observation convention giúp giữ cardinality trong giới hạn; MeterFilter và detector hỗ trợ phát hiện, chặn sự cố khi có dữ liệu ngoài dự kiến. Khi các quy tắc được kiểm thử và thống nhất, metrics vừa đủ chi tiết để phân tích vừa ổn định cho dashboard, cảnh báo và lưu trữ lâu dài.

## Tài liệu tham khảo

- [Spring Boot - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP server metrics, Observation convention và cách tùy chỉnh tag.
- [Micrometer - High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): ví dụ high-cardinality, URI template, status grouping, Observation high-cardinality metadata và biện pháp giới hạn.
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): chấp nhận/từ chối meter, biến đổi tag và maximum allowable tags.
- [Micrometer - Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): định danh meter bằng tên và tags/dimensions.
