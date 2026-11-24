# Phát hiện tag có quá nhiều giá trị theo khả năng công cụ được phiên bản cung cấp

Mỗi tổ hợp tên meter và tag values có thể tạo ra một meter riêng trong Micrometer. Nếu tag nhận giá trị gần như không giới hạn, chẳng hạn user ID, request ID hoặc URL đầy đủ, registry có thể tích lũy hàng trăm nghìn meter. Điều này làm tăng bộ nhớ và chi phí xử lý trong ứng dụng, đồng thời tạo nhiều time series ở hệ thống giám sát.

Micrometer có hai nhóm công cụ liên quan nhưng phục vụ hai mục đích khác nhau:

- `HighCardinalityTagsDetector` phát hiện dấu hiệu nghi ngờ bằng cách đếm số meter cùng tên và cảnh báo khi vượt ngưỡng.
- `MeterFilter` đặt giới hạn khi đăng ký meter, ví dụ giới hạn số giá trị của một tag hoặc tổng số meter.

Detector giúp tìm vấn đề. Filter giúp bảo vệ registry khi cần chặn đăng ký. Cả hai đều không thay thế việc sửa instrumentation để chỉ tạo các tag có tập giá trị hữu hạn.

## 1. Hiểu cardinality của tag

Cardinality là số lượng giá trị khác nhau mà một chiều dữ liệu có thể nhận. Với metrics, mỗi meter được xác định bởi tên và tập tag key-value. Khi một tag nhận nhiều giá trị, mỗi giá trị mới có thể tạo thêm một meter.

Ví dụ:

~~~java
registry.counter("orders.created", "region", "south").increment();
registry.counter("orders.created", "region", "north").increment();
~~~

Tag `region` có tập giá trị nhỏ và được kiểm soát. Nhưng nếu dùng customer ID:

~~~java
registry.counter("orders.created", "customerId", customerId).increment();
~~~

Mỗi khách hàng có thể tạo một meter riêng. Khi hệ thống có hàng triệu khách hàng, số meter tăng theo số khách hàng xuất hiện.

Các tag thường có nguy cơ cardinality cao:

- User ID, customer ID, account ID.
- Request ID, trace ID, session ID.
- Email, token hoặc dữ liệu người dùng nhập.
- Timestamp hoặc giá trị ngẫu nhiên.
- URL có path chứa ID thực, ví dụ `/orders/983742`.
- Tên file hoặc tên resource được sinh động theo từng yêu cầu.

Tag thường có cardinality thấp:

- HTTP method: `GET`, `POST`, `PUT`, `DELETE`.
- HTTP status group: `2xx`, `4xx`, `5xx`.
- Environment: `dev`, `staging`, `prod`.
- Kết quả nghiệp vụ: `success`, `failure`, `timeout`.
- URI template: `/orders/{id}`.

Không có một ngưỡng cardinality chung cho mọi hệ thống. Một tag có vài chục giá trị có thể phù hợp; vài nghìn giá trị có thể đã gây áp lực tùy số meter, histogram, số instance và backend.

## 2. Số meter tăng theo tổ hợp tag

Giả sử một meter có ba tag:

- `method`: 5 giá trị.
- `status`: 6 giá trị.
- `region`: 8 giá trị.

Số tổ hợp tối đa theo lý thuyết là:

\[
5 \times 6 \times 8 = 240
\]

Nếu thêm `customerId` với một triệu giá trị, giới hạn lý thuyết tăng lên 240 triệu tổ hợp. Số tổ hợp thực tế phụ thuộc vào các kết hợp xuất hiện, nhưng chỉ cần một chiều không giới hạn là có thể làm registry tăng liên tục.

Một meter có histogram còn có thể xuất nhiều chuỗi thời gian ở backend. Vì vậy, số meter trong registry và số time series được lưu ở backend không nhất thiết bằng nhau. Detector của Micrometer quan sát meter trong registry; nó không tính toàn bộ bucket series được exporter tạo ra.

## 3. Nhận diện dấu hiệu cardinality cao

Các dấu hiệu thường gặp:

1. Số lượng meter trong registry tăng liên tục theo lưu lượng.
2. Một meter name có hàng nghìn meter ID khác nhau.
3. Heap tăng cùng số lượng meter và tag values.
4. Scrape payload lớn hơn theo thời gian.
5. Backend có số time series active tăng nhanh.
6. Chi phí lưu trữ hoặc truy vấn metrics tăng dù số nghiệp vụ không tăng tương ứng.

Hãy tìm tên meter có nhiều biến thể tag. Ví dụ, nếu `http.server.requests` có hàng nghìn meter và tag `uri` chứa các đường dẫn khác nhau, có thể instrumentation đang ghi URL đầy đủ thay vì URI template.

## 4. HighCardinalityTagsDetector hoạt động thế nào?

`HighCardinalityTagsDetector` theo dõi số meter có cùng tên trong một `MeterRegistry`. Khi số meter của một tên vượt ngưỡng, detector báo rằng tên meter đó có khả năng chứa tag cardinality cao.

Quy trình:

1. Lấy các meter hiện có trong registry.
2. Đếm số meter cùng tên.
3. So sánh số lượng với threshold.
4. Gửi thông tin phát hiện đến logger hoặc consumer tùy chỉnh.

Detector không biết chính xác tag key nào gây ra cardinality. Nó chỉ đưa ra tên meter đáng nghi và số lượng meter tương ứng ở các API mới hơn. Sau cảnh báo, cần kiểm tra tag của các meter cùng tên để tìm chiều dữ liệu gây tăng số lượng.

## 5. Khả năng API theo phiên bản Micrometer

Hãy kiểm tra phiên bản `micrometer-core` thực tế được resolve trong ứng dụng. Spring Boot quản lý phiên bản Micrometer qua dependency management, nên phiên bản Spring Boot không luôn trùng với phiên bản Micrometer.

| Khả năng | Phiên bản/API |
|---|---|
| `MeterRegistry.Config.withHighCardinalityTagsDetector()` | Có từ Micrometer 1.10.0 |
| Factory overload nhận `Function<MeterRegistry, HighCardinalityTagsDetector>` | Có từ 1.14.0 |
| Tài liệu High Cardinality Tags Detector | Có trong dòng tài liệu 1.14 và các dòng mới hơn |
| `findFirstHighCardinalityMeterInfo()` | Có từ 1.16.0 |
| `HighCardinalityMeterInfo` và consumer có cấu trúc | Dùng trong API Builder mới |
| Constructor consumer nhận `Consumer<String>` | Bị deprecated từ 1.16.0; chuyển sang `Builder.highCardinalityMeterInfoConsumer(...)` |

Với Micrometer 1.14–1.15, ví dụ cấu hình thường dùng constructor nhận registry, threshold, delay và consumer tên meter. Từ 1.16, ưu tiên Builder và `HighCardinalityMeterInfo` để nhận cả tên lẫn số lượng meter.

Nếu dự án dùng phiên bản cũ hơn 1.10, không giả định detector này có sẵn. Dùng `MeterFilter` nếu API giới hạn tương ứng có trong phiên bản đang dùng, hoặc kiểm kê meter ID bằng API registry và kiểm tra Javadoc của dependency thực tế.

## 6. Bật detector theo cấu hình mặc định

Với phiên bản có hỗ trợ, có thể bật detector mặc định trên registry:

~~~java
registry.config().withHighCardinalityTagsDetector();
~~~

Khi đăng ký thông qua `MeterRegistry.Config`, detector được khởi chạy và quản lý cùng registry. Khi registry được đóng, detector được quản lý theo vòng đời registry.

Cách này hữu ích để bật kiểm tra nhanh trong môi trường phát triển hoặc production. Tuy nhiên, hệ thống thực tế thường cần chọn threshold, chu kỳ kiểm tra và hành vi cảnh báo phù hợp với quy mô ứng dụng.

## 7. Cấu hình detector cho Micrometer 1.16 trở lên

Builder cho phép đặt threshold, delay và consumer nhận thông tin meter nghi ngờ:

~~~java
import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.MeterRegistry;

import java.time.Duration;
import java.util.logging.Logger;

final class CardinalityMonitoring {
    private static final Logger LOGGER =
            Logger.getLogger(CardinalityMonitoring.class.getName());

    static void configure(MeterRegistry registry) {
        registry.config().withHighCardinalityTagsDetector(r ->
                new HighCardinalityTagsDetector.Builder(r)
                        .threshold(1_000)
                        .delay(Duration.ofMinutes(5))
                        .highCardinalityMeterInfoConsumer(info ->
                                LOGGER.warning(
                                        "Potential high cardinality meter "
                                                + info.getName()
                                                + " has "
                                                + info.getCount()
                                                + " meter instances"
                                )
                        )
                        .build()
        );
    }
}
~~~

Threshold `1_000` và delay năm phút chỉ là ví dụ. Chọn threshold dựa trên số meter bình thường của ứng dụng, số instance và giới hạn bộ nhớ. Không tăng threshold chỉ để làm cảnh báo biến mất.

Consumer nhận `HighCardinalityMeterInfo`, có thể đọc:

- `getName()`: tên meter có dấu hiệu cardinality cao.
- `getCount()`: số meter cùng tên được detector đếm.

Thông tin này không chỉ ra tag key cụ thể. Hãy dùng nó để khoanh vùng meter, sau đó xem tag values của meter cùng tên.

## 8. Cấu hình cho Micrometer 1.14–1.15

Ở các phiên bản trước khi API Builder mới được dùng, có thể truyền consumer nhận tên meter:

~~~java
import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.MeterRegistry;

import java.time.Duration;
import java.util.logging.Logger;

final class LegacyCardinalityMonitoring {
    private static final Logger LOGGER =
            Logger.getLogger(LegacyCardinalityMonitoring.class.getName());

    static void configure(MeterRegistry registry) {
        registry.config().withHighCardinalityTagsDetector(r ->
                new HighCardinalityTagsDetector(
                        r,
                        1_000,
                        Duration.ofMinutes(5),
                        meterName -> LOGGER.warning(
                                "Potential high cardinality meter: " + meterName
                        )
                )
        );
    }
}
~~~

Consumer cũ chỉ nhận tên meter, không nhận đối tượng chứa count. Khi nâng cấp lên 1.16 trở lên, chuyển sang Builder và consumer nhận `HighCardinalityMeterInfo`.

Không dùng đồng thời nhiều detector cho cùng registry nếu không có mục đích riêng. Cấu hình qua registry đã quản lý vòng đời detector.

## 9. Kiểm tra một lần trong test hoặc khi điều tra

Không phải lúc nào cũng cần bật scheduler. Với kiểm tra một lần, tạo detector tạm thời, đăng ký các meter thử nghiệm rồi gọi `findFirstHighCardinalityMeterInfo()`:

~~~java
import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class CardinalityDetectorTest {
    @Test
    void findsMeterWithTooManyTagCombinations() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try (HighCardinalityTagsDetector detector =
                     new HighCardinalityTagsDetector.Builder(registry)
                             .threshold(10)
                             .build()) {

            for (int i = 0; i < 15; i++) {
                registry.counter(
                        "orders.created",
                        "customerId",
                        String.valueOf(i)
                ).increment();
            }

            Optional<HighCardinalityTagsDetector.HighCardinalityMeterInfo> result =
                    detector.findFirstHighCardinalityMeterInfo();

            assertThat(result).isPresent();
            assertThat(result.get().getName()).isEqualTo("orders.created");
            assertThat(result.get().getCount()).isEqualTo(15);
        }
    }
}
~~~

Đây là API từ 1.16.0. Với bản cũ, dùng `findFirst()` để nhận `Optional<String>`:

~~~java
try (HighCardinalityTagsDetector detector =
             new HighCardinalityTagsDetector(
                     registry,
                     10,
                     Duration.ofMinutes(1)
             )) {
    // Đăng ký meter thử nghiệm trước khi kiểm tra.
    Optional<String> result = detector.findFirst();
    assertThat(result).contains("orders.created");
}
~~~

Luôn đóng detector tạo thủ công. Detector có scheduler nội bộ; nếu quên đóng, test hoặc công cụ điều tra có thể để lại thread chạy nền.

## 10. Kiểm tra định kỳ trong production

Trong production, nên bật detector thông qua registry để nó tự kiểm tra theo chu kỳ:

~~~java
registry.config().withHighCardinalityTagsDetector(r ->
        new HighCardinalityTagsDetector.Builder(r)
                .threshold(2_000)
                .delay(Duration.ofMinutes(3))
                .highCardinalityMeterInfoConsumer(this::onHighCardinality)
                .build()
);
~~~

Callback có thể gửi cảnh báo đến hệ thống vận hành hoặc ghi log có cấu trúc:

~~~java
void onHighCardinality(
        HighCardinalityTagsDetector.HighCardinalityMeterInfo info) {
    LOGGER.warning(
            "Meter cardinality warning: name=" + info.getName()
                    + ", count=" + info.getCount()
    );
}
~~~

Giới hạn log hoặc dùng sampling nếu cảnh báo có thể lặp lại. Không tạo metric cảnh báo với tên meter động làm tag, vì chính tag đó có thể trở thành nguồn cardinality mới.

## 11. Chọn threshold có ý nghĩa

Threshold là ngưỡng cảnh báo, không phải định nghĩa toán học của cardinality cao. Một ứng dụng nhỏ có thể cần threshold thấp hơn; ứng dụng lớn có nhiều endpoint hoặc nhiều pool hợp lệ có thể cần threshold cao hơn.

Khi chọn threshold:

1. Đo số meter bình thường sau startup.
2. Chạy workload đại diện cho giờ cao điểm.
3. Ghi lại số meter theo từng tên.
4. Xác định meter nào có tập tag hợp lệ nhưng tổ hợp tự nhiên lớn.
5. Đặt ngưỡng cao hơn baseline hợp lệ với khoảng dự phòng.
6. Theo dõi tăng trưởng theo thời gian và thay đổi ngưỡng khi kiến trúc thay đổi.

Không đặt threshold quá cao để tránh cảnh báo. Nếu meter count tăng liên tục theo request, cần sửa nguồn tạo tag.

## 12. Detector không xác định chính xác tag key gây lỗi

Detector nhóm meter theo tên. Giả sử `http.server.requests` có 5.000 meter. Nguyên nhân có thể là:

- Tag `uri` chứa 5.000 path cụ thể.
- Tag `tenant` chứa nhiều tenant.
- Hai tag `uri` và `method` tạo ra nhiều tổ hợp.
- Một tag khác trong instrumentation có dữ liệu không giới hạn.

Detector không tự kết luận tag nào có vấn đề. Cần kiểm tra `Meter.Id` của các meter cùng tên:

~~~java
registry.getMeters().stream()
        .filter(meter -> meter.getId().getName().equals("http.server.requests"))
        .forEach(meter -> LOGGER.info(
                meter.getId().getName() + " " + meter.getId().getTags()
        ));
~~~

Chỉ chạy kiểm kê chi tiết khi điều tra và tránh in dữ liệu nhạy cảm như user ID hoặc token vào log. Với registry lớn, giới hạn số mẫu và nhóm giá trị trước khi xuất.

## 13. Những giới hạn của HighCardinalityTagsDetector

Detector là heuristic, không phải bộ phân tích mọi nguyên nhân tăng bộ nhớ:

| Giới hạn | Ý nghĩa |
|---|---|
| Đếm meter cùng tên | Không đếm trực tiếp số giá trị riêng của từng tag key |
| Chỉ báo meter đầu tiên vượt ngưỡng | Có thể phải sửa từng meter rồi kiểm tra lại để phát hiện vấn đề tiếp theo |
| Không phát hiện tên meter động | Nếu request ID được ghép vào tên meter, các meter bị chia thành nhiều tên khác nhau |
| Không phát hiện dưới ngưỡng | Một tag đang tăng nhưng chưa vượt threshold sẽ chưa cảnh báo |
| Không phân tích memory leak khác | Cache, object retention hoặc thread leak cần công cụ khác |
| Không đo toàn bộ backend series | Histogram và exporter có thể tạo thêm series ngoài số meter trong registry |

Vì vậy, detector nên được kết hợp với kiểm tra registry, heap profiling, scrape payload và số active time series ở backend.

## 14. MeterFilter.maximumAllowableTags để giới hạn một tag

Khi cần bảo vệ registry trước một tag cụ thể, dùng:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny()
        )
);
~~~

Tham số:

| Tham số | Ý nghĩa |
|---|---|
| `meterNamePrefix` | Chỉ áp dụng với meter có tên bắt đầu bằng prefix |
| `tagKey` | Tag key cần giới hạn |
| `maximumTagValues` | Số giá trị khác nhau tối đa được chấp nhận |
| `onMaxReached` | Filter được áp dụng khi đã vượt số giá trị cho phép |

Trong ví dụ, tối đa 100 giá trị khác nhau của tag `uri` được đăng ký cho các meter khớp prefix. Các giá trị mới vượt giới hạn bị từ chối bởi `MeterFilter.deny()`.

Meter bị từ chối được registry trả về dạng NOOP meter. Code ứng dụng vẫn có thể gọi `increment()` hoặc `record()`, nhưng dữ liệu ghi vào meter đó bị loại bỏ.

Đây là biện pháp bảo vệ cuối cùng. Nếu meter quan trọng bị từ chối, dashboard có thể thiếu dữ liệu; hãy theo dõi cảnh báo và sửa instrumentation gốc.

## 15. Ghi nhận khi MeterFilter chặn meter

`MeterFilter.deny()` không tự phát cảnh báo. Có thể truyền một filter riêng làm hành động khi đạt giới hạn:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.config.MeterFilterReply;

MeterFilter reportAndDeny = new MeterFilter() {
    @Override
    public MeterFilterReply accept(Meter.Id id) {
        LOGGER.warning(
                "Denied meter after cardinality limit: "
                        + id.getName()
                        + ", uri=" + id.getTag("uri")
        );
        return MeterFilterReply.DENY;
    }
};

registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                reportAndDeny
        )
);
~~~

Filter hành động có thể được gọi cho nhiều meter bị từ chối. Dùng log sampling hoặc bộ đếm có giới hạn để tránh log flood. Không ghi tag value nhạy cảm hoặc toàn bộ ID vào log.

## 16. MeterFilter.maximumAllowableMetrics để đặt trần toàn registry

Nếu cần giới hạn tổng số meter, dùng:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableMetrics(10_000)
);
~~~

Filter này giới hạn tổng số tổ hợp tên và tag được đăng ký trong registry. Nó không phân biệt meter quan trọng với meter ít quan trọng. Khi đạt giới hạn, meter mới có thể bị từ chối bất kể tên của nó.

Do đó:

- Dùng `maximumAllowableTags` khi biết tag key và meter prefix cần bảo vệ.
- Dùng `maximumAllowableMetrics` như trần an toàn cuối cùng.
- Kết hợp whitelist/deny rules nếu cần bảo đảm meter thiết yếu được đăng ký trước.
- Không coi giới hạn tổng meter là cách sửa lỗi tag động.

## 17. Thứ tự MeterFilter có ảnh hưởng

Micrometer áp dụng MeterFilter theo thứ tự đăng ký. Các quyết định `DENY`, `NEUTRAL` và `ACCEPT` ảnh hưởng đến filter tiếp theo:

- `DENY`: không đăng ký meter.
- `NEUTRAL`: tiếp tục xét các filter khác.
- `ACCEPT`: chấp nhận meter ngay, bỏ qua các accept filter sau đó.

Ví dụ whitelist:

~~~java
registry.config()
        .meterFilter(MeterFilter.acceptNameStartsWith("http"))
        .meterFilter(MeterFilter.deny());
~~~

Chỉ meter có tên bắt đầu bằng `http` được chấp nhận trong cấu hình này. Khi kết hợp nhiều filter, hãy kiểm tra thứ tự để tránh một filter chấp nhận sớm làm bỏ qua giới hạn dự kiến.

Nên đăng ký filter trước khi các binder và service tạo meter. Filter không phải công cụ để xóa hoặc sửa lại những meter đã được đăng ký trước đó.

## 18. Bỏ tag không cần thiết bằng ignoreTags

Nếu tag có cardinality cao nhưng không cần cho phân tích, có thể bỏ tag:

~~~java
registry.config().meterFilter(
        MeterFilter.forMeters(
                id -> id.getName().startsWith("http.server.requests"),
                MeterFilter.ignoreTags("userId")
        )
);
~~~

Ở ví dụ này, chỉ các meter phù hợp prefix bị bỏ tag `userId`. Không dùng `ignoreTags("userId")` toàn cục nếu tag cùng tên có ý nghĩa ở các meter khác.

Khi bỏ tag, nhiều meter ID khác nhau có thể trở thành cùng một ID và được hợp nhất theo identity mới. Điều này làm mất khả năng phân biệt theo tag đó; hãy xác nhận dashboard và alert không phụ thuộc vào chiều bị bỏ.

## 19. Chuẩn hóa giá trị bằng replaceTagValues

Nếu cần giữ thông tin phân nhóm, chuẩn hóa giá trị về một tập hữu hạn:

~~~java
registry.config().meterFilter(
        MeterFilter.forMeters(
                id -> id.getName().startsWith("http.server.requests"),
                MeterFilter.replaceTagValues(
                        "uri",
                        uri -> normalizeUri(uri)
                )
        )
);
~~~

Hàm chuẩn hóa có thể chuyển:

| Giá trị thô | Giá trị chuẩn hóa |
|---|---|
| `/orders/123` | `/orders/{id}` |
| `/orders/987` | `/orders/{id}` |
| `/customers/42` | `/customers/{id}` |
| Path không nhận diện | `OTHER` |

Ví dụ hàm:

~~~java
String normalizeUri(String uri) {
    if (uri.matches("/orders/[0-9]+")) {
        return "/orders/{id}";
    }
    if (uri.matches("/customers/[0-9]+")) {
        return "/customers/{id}";
    }
    return "OTHER";
}
~~~

Chỉ dùng biểu thức chuẩn hóa phù hợp với cấu trúc URL thực tế. Với HTTP server instrumentation, ưu tiên cung cấp URI template từ router/framework ở nguồn instrumentation thay vì cố sửa URL sau khi meter đã được tạo.

Hash ID không giải quyết cardinality: một triệu ID khác nhau vẫn tạo một triệu hash khác nhau. Cắt chuỗi theo độ dài cũng không bảo đảm tập giá trị hữu hạn.

## 20. Phân biệt low-cardinality và high-cardinality trong Observation

Nếu dùng Micrometer Observation, metadata được đánh dấu low hoặc high cardinality:

~~~java
Observation.createNotStarted("orders.lookup", registry)
        .lowCardinalityKeyValue("operation", "lookup")
        .highCardinalityKeyValue("customerId", customerId)
        .observe(() -> orderService.lookup(customerId));
~~~

Ý nghĩa:

- Low-cardinality key-value có thể được dùng làm metric tags.
- High-cardinality key-value không được dùng để ghi metrics bởi `DefaultMeterObservationHandler`.
- Tracing handler có thể dùng high-cardinality values làm span attributes.

Đây là cách đúng khi ID cụ thể cần cho trace nhưng không phù hợp để tạo time series. Không chuyển `customerId` thành low-cardinality chỉ để xuất nó vào metrics.

## 21. Kiểm tra tag cardinality trong kiểm thử instrumentation

Không chỉ kiểm thử detector bằng meter nhân tạo. Nên có integration test gọi instrumentation thật với nhiều đầu vào khác nhau:

1. Tạo một `SimpleMeterRegistry`.
2. Gắn detector với threshold thấp để test nhanh.
3. Gọi endpoint/service với nhiều URI hoặc customer ID.
4. Kiểm tra detector có phát hiện meter nghi ngờ không.
5. Nếu phát hiện, sửa instrumentation để chuẩn hóa tag.
6. Chạy lại test và xác minh không vượt ngưỡng.

Ví dụ test đơn giản:

~~~java
@Test
void requestInstrumentationUsesTemplatedUri() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    for (int id = 1; id <= 50; id++) {
        registry.timer(
                "http.server.requests",
                "method", "GET",
                "uri", "/orders/{id}",
                "status", "200"
        ).record(Duration.ofMillis(10));
    }

    assertThat(registry.getMeters())
            .filteredOn(meter ->
                    meter.getId().getName().equals("http.server.requests"))
            .hasSize(1);
}
~~~

Test này chứng minh các request khác ID vẫn dùng cùng URI template nên chỉ tạo một meter cho tổ hợp tag đó. Có thể kết hợp detector để kiểm tra các meter khác trong cùng registry.

## 22. Theo dõi cả registry và backend

Detector đếm meter trong registry ứng dụng. Backend có thể nhìn thấy số series lớn hơn vì:

- Timer histogram sinh nhiều bucket series.
- DistributionSummary có bucket hoặc percentile series.
- Nhiều instance cùng xuất meter.
- Exporter đổi tên hoặc thêm dimension theo quy tắc backend.

Do đó nên quan sát hai lớp:

| Lớp | Công cụ |
|---|---|
| Ứng dụng | HighCardinalityTagsDetector, MeterRegistry meter count, heap profile |
| Exporter/backend | Scrape payload, active series, ingestion rate, cardinality dashboard |

Nếu detector không cảnh báo nhưng backend series vẫn tăng nhanh, xem xét histogram buckets, số tag dimensions, nhiều registry hoặc cấu hình exporter.

## 23. Cấu hình trong Spring Boot

Spring Boot thường cung cấp `MeterRegistry` và registry exporter qua Actuator. Có thể thêm một `MeterRegistryCustomizer` để cấu hình detector hoặc MeterFilter trên registry được Boot quản lý:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsCardinalityConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> cardinalityGuard() {
        return registry -> {
            registry.config().meterFilter(
                    MeterFilter.maximumAllowableTags(
                            "http.server.requests",
                            "uri",
                            200,
                            MeterFilter.deny()
                    )
            );

            registry.config().withHighCardinalityTagsDetector();
        };
    }
}
~~~

Ví dụ dùng API `MeterRegistryCustomizer` của Spring Boot Actuator. Kiểm tra package và phiên bản Spring Boot đang dùng nếu dự án có thay đổi API. Detector và filter không nhất thiết được bật tự động chỉ vì thêm Actuator; cấu hình rõ ràng theo nhu cầu.

Nếu cần threshold hoặc consumer riêng, dùng factory overload tương thích với phiên bản Micrometer được Spring Boot quản lý.

## 24. Các lỗi thường gặp

**Cho rằng detector chặn meter.** Detector chỉ cảnh báo. Dùng MeterFilter nếu cần giới hạn đăng ký.

**Cho rằng detector chỉ ra tag key lỗi.** Detector nhóm theo meter name. Kiểm tra Meter.Id và instrumentation để tìm tag gây tăng.

**Cho rằng mọi phiên bản đều có Builder.** API consumer và thông tin phát hiện thay đổi theo phiên bản. Kiểm tra Micrometer 1.14–1.15 so với 1.16+ trước khi sao chép code.

**Tăng threshold để hết cảnh báo.** Threshold cao hơn không sửa tag động; nó chỉ trì hoãn phát hiện.

**Dùng maximumAllowableMetrics như giải pháp chính.** Trần tổng có thể chặn cả meter quan trọng. Ưu tiên giới hạn đúng meter prefix và tag key.

**Bỏ tag toàn cục.** ignoreTags có thể làm mất chiều phân tích ở meter khác. Dùng forMeters để giới hạn phạm vi.

**Hash ID để giảm cardinality.** Hash vẫn có thể có hàng triệu giá trị riêng.

**Đưa user ID vào metric tag.** Giữ ID ở trace/log hoặc high-cardinality Observation key-value.

**Ghi log mọi meter bị từ chối.** Có thể gây log flood. Dùng sampling, rate limit hoặc tổng hợp cảnh báo.

**Chỉ kiểm tra trong unit test.** Workload thực tế có thể tạo nhiều tag values hơn. Bật detector định kỳ trong môi trường production.

**Không tính histogram và số instance.** Meter count không đồng nghĩa backend series count; cần theo dõi cả hai.

## 25. Checklist vận hành

Trước khi phát hành instrumentation, hãy xác minh:

- [ ] Tag không chứa ID, timestamp hoặc URL động nếu không cần thiết.
- [ ] URI được chuẩn hóa thành template.
- [ ] Observation metadata được phân loại low/high cardinality đúng cách.
- [ ] Phiên bản Micrometer thực tế hỗ trợ API detector được dùng.
- [ ] Threshold được chọn từ baseline và workload đại diện.
- [ ] Detector được cấu hình trên đúng registry.
- [ ] Detector có lịch kiểm tra phù hợp và consumer không gây log flood.
- [ ] MeterFilter giới hạn đúng prefix và tag key.
- [ ] maximumAllowableMetrics chỉ được dùng như trần bảo vệ cuối cùng.
- [ ] Filter được đăng ký trước khi meter được tạo.
- [ ] Có test với SimpleMeterRegistry và instrumentation thực tế.
- [ ] Theo dõi cả meter count trong ứng dụng và active series ở backend.
- [ ] Cảnh báo được điều tra để sửa nguyên nhân gốc, không chỉ tăng threshold.

## 26. Kết luận

`HighCardinalityTagsDetector` giúp phát hiện meter có số lượng tổ hợp tag đáng nghi bằng cách đếm meter cùng tên. Khả năng API phụ thuộc phiên bản: registry hook có từ 1.10.0, factory overload từ 1.14.0, còn `HighCardinalityMeterInfo` và API Builder mới có từ dòng 1.16.0. Với phiên bản cũ, consumer chỉ nhận tên meter; với phiên bản mới, consumer nhận cả tên và số lượng.

Detector không chặn meter và không xác định chính xác tag key gây vấn đề. Dùng `MeterFilter.maximumAllowableTags` để giới hạn một tag, `maximumAllowableMetrics` làm trần toàn registry, và `ignoreTags` hoặc `replaceTagValues` để xử lý tag khi không thể sửa instrumentation ngay. Giải pháp bền vững vẫn là chuẩn hóa giá trị tại nguồn, giữ low-cardinality cho metrics và chuyển dữ liệu định danh sang tracing hoặc logging.

## Tài liệu tham khảo

- [Micrometer – High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Micrometer 1.14 – High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/1.14/concepts/high-cardinality-tags-detector.html)
- [Micrometer 1.15 – High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/1.15/concepts/high-cardinality-tags-detector.html)
- [Micrometer – Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer – MeterFilter API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/config/MeterFilter.html)
- [Micrometer – HighCardinalityTagsDetector API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/HighCardinalityTagsDetector.html)
