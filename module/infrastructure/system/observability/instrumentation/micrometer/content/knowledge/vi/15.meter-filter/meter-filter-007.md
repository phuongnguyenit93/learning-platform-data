# maximumAllowableTags để chặn số giá trị tag vượt ngân sách

Micrometer dùng tag để chia metrics thành các chiều phân tích. Mỗi giá trị tag mới có thể tạo thêm meter identity và time series. Nếu một tag nhận dữ liệu tự do như URL đầy đủ, user ID hoặc tên file, số series có thể tăng theo lượng request và làm backend tốn bộ nhớ, dung lượng lưu trữ cùng chi phí truy vấn.

MeterFilter.maximumAllowableTags giúp đặt giới hạn số giá trị khác nhau của một tag key trên các meter có tên khớp prefix. Khi vượt giới hạn, filter onMaxReached quyết định cách xử lý meter mới; lựa chọn thường dùng là MeterFilter.deny(). Đây là lớp bảo vệ cardinality ở thời điểm đăng ký meter, cần kết hợp với việc chuẩn hóa tag ngay tại nguồn.

## 1. Vì sao số giá trị tag cần có ngân sách?

Trong Micrometer, tên meter cùng tập tag key/value tạo nên định danh của meter. Ví dụ:

~~~text
jobs.completed{worker_pool="mail"}
jobs.completed{worker_pool="report"}
jobs.completed{worker_pool="export"}
~~~

Ba giá trị worker_pool tạo ba meter identity khác nhau. Backend time series lưu mỗi tổ hợp label thành một chuỗi dữ liệu riêng.

Một tag có tập giá trị hữu hạn thường dễ kiểm soát:

- method: GET, POST, PUT, DELETE.
- outcome: success, failure, rejected.
- worker_pool: mail, report, export.
- region: các mã khu vực được cấu hình trước.

Một tag có giá trị gần như vô hạn dễ tạo cardinality cao:

- user_id hoặc order_id.
- request_id hoặc trace_id.
- URL đầy đủ có query string.
- tên file hoặc tên tenant tùy ý.
- nội dung exception hoặc thông báo lỗi tự do.

Ví dụ, nếu mỗi request có một request_id riêng và request_id được đưa vào tag, mỗi request có thể tạo một time series mới. Với hệ thống nhận hàng nghìn request mỗi giây, số series sẽ tăng rất nhanh.

## 2. maximumAllowableTags giới hạn điều gì?

API có dạng:

~~~java
MeterFilter.maximumAllowableTags(
    String meterNamePrefix,
    String tagKey,
    int maximumTagValues,
    MeterFilter onMaxReached
)
~~~

Ý nghĩa các tham số:

| Tham số | Ý nghĩa |
|---|---|
| meterNamePrefix | Prefix tên meter mà filter áp dụng |
| tagKey | Tag key cần giới hạn số giá trị |
| maximumTagValues | Số giá trị khác nhau tối đa được chấp nhận |
| onMaxReached | Filter quyết định cách xử lý khi vượt giới hạn |

Ví dụ:

~~~java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "jobs.completed",
        "worker_pool",
        3,
        MeterFilter.deny()
    )
);
~~~

Với cấu hình trên, các meter có tên bắt đầu bằng jobs.completed và tag worker_pool được giới hạn tối đa ba giá trị khác nhau. Khi có giá trị thứ tư, MeterFilter.deny() từ chối đăng ký meter vượt giới hạn.

Lưu ý: maximumAllowableTags giới hạn số giá trị phân biệt của một tag key trong phạm vi meter name khớp prefix. Nó không giới hạn tổng số tag key của meter, không giới hạn mọi tag khác và cũng không đặt một ngân sách tổng cho toàn bộ registry.

## 3. Ví dụ giới hạn tag cho worker pool

Giả sử hệ thống có ba nhóm worker được phép: mail, report và export. Cấu hình filter trước khi các meter được đăng ký:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {
    @Bean
    MeterFilter workerPoolTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "jobs.completed",
            "worker_pool",
            3,
            MeterFilter.deny()
        );
    }
}
~~~

Đăng ký meter theo nhóm:

~~~java
registry.counter(
    "jobs.completed",
    "worker_pool", "mail"
).increment();

registry.counter(
    "jobs.completed",
    "worker_pool", "report"
).increment();

registry.counter(
    "jobs.completed",
    "worker_pool", "export"
).increment();
~~~

Ba giá trị này nằm trong ngân sách. Nếu mã nguồn tiếp tục đăng ký:

~~~java
registry.counter(
    "jobs.completed",
    "worker_pool", "unknown-pool"
).increment();
~~~

filter sẽ áp dụng onMaxReached và từ chối meter mới vì đã vượt giới hạn ba giá trị.

Kết quả là metrics của các giá trị đã được đăng ký tiếp tục hoạt động; meter có giá trị tag vượt ngưỡng không được thêm vào registry. Dữ liệu của giá trị bị từ chối không tự động được cộng vào một nhóm "other". Nếu muốn giữ số liệu cho các đầu vào không nhận diện được, hãy chuẩn hóa chúng về một giá trị hợp lệ trước khi đăng ký meter.

Filter chỉ giới hạn số lượng giá trị, không biết giá trị nào được nghiệp vụ cho phép. Các giá trị đầu tiên được đăng ký sẽ chiếm ngân sách; khi có đăng ký đồng thời, nhóm giá trị được chấp nhận có thể phụ thuộc thứ tự đến. Vì vậy, không dùng maximumAllowableTags thay cho allowlist. Hãy kiểm tra và chuẩn hóa đầu vào trước, rồi dùng filter để chặn trường hợp ngoài dự kiến.

## 4. Chặn meter vượt ngưỡng không đồng nghĩa gom nhóm giá trị

Một hiểu nhầm phổ biến là cho rằng khi vượt giới hạn, MeterFilter tự thay các giá trị mới thành "other". Điều này không đúng với cấu hình onMaxReached là deny.

Giả sử giới hạn là hai giá trị:

~~~text
worker_pool=mail
worker_pool=report
worker_pool=export
worker_pool=other
~~~

Nếu mail và report đã được đăng ký trước, export và other sẽ bị từ chối khi filter được cấu hình với MeterFilter.deny(). Chúng không tự động được đổi thành worker_pool=other.

Nếu mục tiêu là giữ một nhóm dự phòng, hãy chuẩn hóa đầu vào trước khi gọi registry:

~~~java
private String normalizeWorkerPool(String rawValue) {
    return switch (rawValue) {
        case "mail", "report", "export" -> rawValue;
        default -> "other";
    }
}

public void recordCompleted(String rawWorkerPool) {
    registry.counter(
        "jobs.completed",
        "worker_pool",
        normalizeWorkerPool(rawWorkerPool)
    ).increment();
}
~~~

Trong trường hợp này, chỉ có bốn giá trị hợp lệ: mail, report, export và other. Filter có thể đặt giới hạn bốn giá trị như lớp bảo vệ bổ sung.

Chuẩn hóa tại nguồn còn giúp kiểm soát dữ liệu trước khi meter được tạo. Nếu đầu vào là dữ liệu định danh hoặc nhạy cảm, không đưa nó vào tag rồi trông chờ filter chặn sau đó. Giá trị ban đầu có thể đã được xử lý trong mã nguồn, log hoặc các hệ thống khác; filter không phải cơ chế bảo vệ dữ liệu nhạy cảm.

## 5. Chọn prefix và tag key chính xác

meterNamePrefix xác định nhóm meter mà giới hạn được áp dụng. Chọn prefix quá rộng có thể ảnh hưởng các meter không liên quan; chọn prefix quá hẹp có thể bỏ sót meter cần bảo vệ.

Ví dụ:

~~~java
MeterFilter.maximumAllowableTags(
    "http.server.requests",
    "uri",
    100,
    MeterFilter.deny()
)
~~~

Filter này nhắm đến nhóm meter HTTP server requests có tên bắt đầu bằng http.server.requests và tag uri.

Khi chọn prefix, hãy kiểm tra tên meter thực tế được registry đăng ký. Một số framework hoặc phiên bản có thể thay đổi tên meter hoặc cách chuẩn hóa tên khi xuất sang backend.

Tag key phải khớp chính xác key trong Meter.Id. Nếu ứng dụng dùng uri nhưng filter giới hạn path, filter sẽ không áp dụng cho tag uri. Hãy kiểm tra meter ID và tag thực tế thay vì suy đoán từ tên hiển thị trên dashboard.

Nếu cần bảo vệ nhiều meter name hoặc nhiều tag key, đăng ký các filter riêng với prefix và key tương ứng. Đừng dùng một filter rộng cho toàn bộ registry nếu các nhóm metrics có ngân sách khác nhau.

## 6. Giới hạn tag value khác với giới hạn tổng số meter

maximumAllowableTags giới hạn số giá trị phân biệt của một tag key. Micrometer còn có filter khác là maximumAllowableMetrics để giới hạn số meter khớp prefix.

Ví dụ:

~~~java
registry.config()
    .meterFilter(
        MeterFilter.maximumAllowableMetrics(
            "jobs.",
            200,
            MeterFilter.deny()
        )
    )
    .meterFilter(
        MeterFilter.maximumAllowableTags(
            "jobs.completed",
            "worker_pool",
            4,
            MeterFilter.deny()
        )
    );
~~~

Hai giới hạn này giải quyết hai vấn đề khác nhau:

| Filter | Giới hạn |
|---|---|
| maximumAllowableMetrics | Số meter được đăng ký cho tên khớp prefix |
| maximumAllowableTags | Số giá trị khác nhau của một tag key trên meter khớp prefix |

Một meter có thể có nhiều tag key và nhiều tổ hợp giá trị. Giới hạn từng tag key không tự động bảo đảm tổng số tổ hợp meter thấp.

Ví dụ, nếu có bốn giá trị worker_pool, năm giá trị outcome và ba giá trị region, tổ hợp tối đa có thể lên đến:

~~~text
4 × 5 × 3 = 60 meter identities
~~~

Đây là lý do cần tính ngân sách cardinality theo toàn bộ tổ hợp tag, chứ không chỉ nhìn số giá trị của một tag riêng lẻ.

## 7. Tính ngân sách cardinality

Giả sử metric jobs.completed có các chiều:

| Tag | Số giá trị dự kiến |
|---|---:|
| worker_pool | 4 |
| outcome | 3 |
| region | 5 |

Số tổ hợp tối đa là:

~~~text
4 × 3 × 5 = 60 series
~~~

Nếu metric có histogram, mỗi series bucket có thể nhân số lượng series lên thêm nhiều lần. Với 20 bucket, số series bucket ước tính có thể là 60 × 20 = 1.200, chưa tính count, sum và các series thống kê khác.

Vì vậy, ngân sách cần xét:

1. Số giá trị của từng tag key.
2. Số tổ hợp giữa các tag.
3. Số meter name.
4. Số bucket nếu bật histogram.
5. Số registry/backend nhận metrics.
6. Số instance ứng dụng đang xuất dữ liệu.

maximumAllowableTags giúp bảo vệ một chiều cụ thể. Nó không thay thế thiết kế schema metrics và không bảo đảm một ngân sách series tổng thể.

## 8. Cấu hình với Spring Boot

Trong Spring Boot Actuator, có thể khai báo MeterFilter dưới dạng bean. Spring Boot sẽ áp dụng MeterFilter bean vào các registry được auto-configure:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterFilter workerPoolTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "jobs.completed",
            "worker_pool",
            4,
            MeterFilter.deny()
        );
    }
}
~~~

Nếu ứng dụng có nhiều MeterRegistry, hãy xác minh filter được áp dụng vào từng registry cần bảo vệ. Các registry có thể có vòng đời hoặc cấu hình khác nhau; đừng giả định mọi registry tự tạo đều nhận cùng một filter bean.

Với registry được tạo thủ công, có thể gắn filter trực tiếp qua registry.config().meterFilter(...). Cần bảo đảm filter được cấu hình trước khi binder, auto-configuration hoặc mã nghiệp vụ đăng ký meter.

## 9. Thời điểm áp dụng và thứ tự filter

MeterFilter tác động trong quá trình đăng ký meter. Khi meter đã tồn tại, thêm một filter mới không tự quét lại và xóa các meter đã đăng ký trước đó.

Vì vậy:

1. Tạo registry.
2. Cấu hình các filter và common tags.
3. Đăng ký binder và meter tùy chỉnh.
4. Bắt đầu nhận traffic hoặc xử lý công việc.
5. Theo dõi meter được chấp nhận và meter bị từ chối.

Nếu filter được thêm sau khi một nhóm meter đã được đăng ký, các meter cũ có thể vẫn tồn tại dù vượt ngân sách mới. Muốn thay đổi chính sách, cần có kế hoạch khởi tạo lại registry hoặc migration phù hợp với vòng đời ứng dụng.

Khi có nhiều filter, thứ tự và hành vi của từng filter cần được kiểm tra. Một filter có thể đổi tên hoặc tag trước khi filter giới hạn kiểm tra identity. Hãy giữ cấu hình đơn giản, đặt filter có chủ đích và xác minh kết quả từ registry thực tế.

## 10. Kiểm thử maximumAllowableTags

Có thể dùng SimpleMeterRegistry để kiểm tra filter từ chối giá trị vượt ngưỡng:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class MaximumAllowableTagsTest {

    @Test
    void deniesNewTagValuesAfterLimit() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                    "jobs.completed",
                    "worker_pool",
                    2,
                    MeterFilter.deny()
                )
            );

            registry.counter(
                "jobs.completed",
                "worker_pool", "mail"
            ).increment();

            registry.counter(
                "jobs.completed",
                "worker_pool", "report"
            ).increment();

            assertNotNull(
                registry.find("jobs.completed")
                    .tag("worker_pool", "mail")
                    .counter()
            );

            assertNotNull(
                registry.find("jobs.completed")
                    .tag("worker_pool", "report")
                    .counter()
            );

            registry.counter(
                "jobs.completed",
                "worker_pool", "export"
            ).increment();

            assertNull(
                registry.find("jobs.completed")
                    .tag("worker_pool", "export")
                    .counter()
            );
        }
    }
}
~~~

Kiểm thử xác minh hai giá trị đầu được đăng ký và giá trị thứ ba không có meter trong registry. Với phiên bản Micrometer cụ thể của dự án, cần chạy test để xác nhận API và hành vi thực tế.

Có thể bổ sung các trường hợp:

- Meter name không khớp prefix thì không bị filter này giới hạn.
- Tag key khác tag key cấu hình thì không bị giới hạn bởi filter này.
- Đăng ký lại một meter cùng identity không tiêu thụ thêm một tag value mới.
- Nhiều thread đồng thời đăng ký các giá trị mới không vượt quá ngân sách đã đặt.
- Filter được cấu hình trước và sau thời điểm đăng ký meter cho thấy khác biệt về vòng đời.

## 11. Xử lý khi vượt ngân sách

Khi filter từ chối meter mới, cần có cách phát hiện và điều tra. Nếu chỉ âm thầm deny, dashboard có thể thiếu số liệu mà đội vận hành không biết lý do.

Nên:

- Ghi log có kiểm soát tại nơi chuẩn hóa hoặc nơi phát hiện đầu vào không hợp lệ.
- Theo dõi các giá trị tag đã biết và số lượng đầu vào rơi vào nhóm other.
- Kiểm tra số series thực tế trong backend.
- Đặt cảnh báo nếu một nhóm metrics đột ngột biến mất hoặc giảm bất thường.
- Điều chỉnh ngân sách chỉ sau khi xác định nguồn cardinality tăng.

Không ghi tag value độc hại hoặc nhạy cảm vào log chỉ để chẩn đoán. Có thể log tên metric, tag key và thông tin nhóm đã chuẩn hóa mà không lưu giá trị định danh.

Nếu cần đếm số lần đầu vào bị đưa về other, tạo một Counter riêng có tag hữu hạn như reason=unknown_worker_pool. Không tạo counter với tag chứa raw input.

## 12. Các lỗi thường gặp

- **Hiểu maximumAllowableTags là giới hạn số tag key:** API giới hạn số giá trị khác nhau của một tag key.
- **Nghĩ giá trị vượt ngưỡng tự động thành other:** với MeterFilter.deny(), meter mới bị từ chối, không được gom nhóm.
- **Dùng filter thay cho chuẩn hóa dữ liệu:** giá trị tự do vẫn có thể là dữ liệu nhạy cảm và không nên đưa vào tag.
- **Chọn prefix quá rộng:** có thể chặn meter thuộc nhóm không liên quan.
- **Chọn prefix quá hẹp:** bỏ sót các meter cần giới hạn.
- **Cấu hình filter sau khi meter đã đăng ký:** meter cũ không tự bị xóa hoặc đánh giá lại.
- **Chỉ giới hạn một tag rồi bỏ qua các tag khác:** tổ hợp nhiều chiều vẫn có thể tạo cardinality lớn.
- **Không tính bucket histogram:** histogram làm tăng số series trên mỗi tổ hợp tag.
- **Dùng maximumAllowableMetrics thay cho maximumAllowableTags:** hai filter có mục đích khác nhau.
- **Không quan sát meter bị từ chối:** dashboard thiếu dữ liệu nhưng không có dấu hiệu giải thích.

## 13. Checklist triển khai

- [ ] Xác định metric name prefix cần bảo vệ.
- [ ] Chọn đúng tag key có nguy cơ cardinality cao.
- [ ] Đặt maximumTagValues dựa trên ngân sách thực tế.
- [ ] Chọn onMaxReached rõ ràng, thường là MeterFilter.deny().
- [ ] Chuẩn hóa dữ liệu tự do về tập giá trị hữu hạn trước khi đăng ký meter.
- [ ] Dùng other cho nhóm đầu vào không nhận diện nếu nghiệp vụ cần giữ số liệu.
- [ ] Cấu hình filter trước khi binder và meter được đăng ký.
- [ ] Tính cardinality từ tích số các tag và số bucket histogram.
- [ ] Dùng maximumAllowableMetrics khi cần giới hạn số meter tổng thể theo prefix.
- [ ] Kiểm thử giá trị được chấp nhận và bị từ chối.
- [ ] Theo dõi sự thiếu hụt metrics và điều tra khi ngân sách bị chạm.
- [ ] Không đưa ID hoặc dữ liệu nhạy cảm vào tag hay log.

maximumAllowableTags là hàng rào bảo vệ hữu ích ở thời điểm đăng ký meter: nó giới hạn số giá trị khác nhau của một tag key trong nhóm metric được chỉ định. Hãy dùng nó sau khi đã thiết kế tập tag hữu hạn và chuẩn hóa dữ liệu ở nguồn. Khi kết hợp giới hạn từng tag, ngân sách tổng series và kiểm thử registry, ứng dụng có thể kiểm soát cardinality mà vẫn giữ được các chiều phân tích cần thiết.

