# Thứ tự bộ lọc và tác động của quyết định chấp nhận sớm

## Mục tiêu

MeterFilter cho phép kiểm soát meter trước khi chúng được đăng ký vào MeterRegistry. Một filter có thể từ chối meter, chấp nhận meter, giữ nguyên quyết định để filter kế tiếp xem xét, đổi tên hoặc tag, hay điều chỉnh cấu hình phân bố như histogram và percentile.

Thứ tự đăng ký filter có ảnh hưởng trực tiếp đến kết quả. Đặc biệt, khi accept() trả về ACCEPT, vòng đánh giá chấp nhận kết thúc sớm: những filter accept() phía sau không còn cơ hội từ chối meter đó. Nếu đặt một filter cho phép rộng ở trước filter giới hạn cardinality hoặc filter từ chối, chính sách bảo vệ có thể bị vô hiệu hóa.

Sau bài này, bạn có thể:

- Phân biệt ACCEPT, NEUTRAL và DENY.
- Sắp xếp filter theo nguyên tắc từ chối cụ thể, giới hạn tài nguyên, cho phép có chọn lọc rồi mới áp dụng mặc định.
- Nhận biết tác động của ACCEPT sớm và tránh đặt nó trước các filter cần được thực thi.
- Phân biệt giai đoạn quyết định đăng ký với việc biến đổi Meter.Id và cấu hình thống kê.
- Kiểm thử thứ tự filter bằng SimpleMeterRegistry.

## MeterFilter tham gia vào quá trình đăng ký meter như thế nào?

Một MeterFilter có ba trách nhiệm chính:

| Hook | Vai trò | Ví dụ |
|---|---|---|
| accept(Meter.Id) | Quyết định meter có được đăng ký hay không | Từ chối metric debug hoặc chỉ cho phép metric nghiệp vụ |
| map(Meter.Id) | Biến đổi danh tính meter | Đổi tên, bỏ hoặc chuẩn hóa tag |
| configure(Meter.Id, DistributionStatisticConfig) | Điều chỉnh thống kê phân bố | Bật histogram hoặc đặt percentile cho một nhóm timer |

Meter.Id chứa tên meter, tag, base unit và description. Các filter dùng thông tin này để đưa ra quyết định hoặc biến đổi cấu hình.

MeterFilter được gắn vào cấu hình registry:

~~~java
registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("internal.debug"));
~~~

Hãy cấu hình filter ngay sau khi tạo registry và trước khi đăng ký các meter đầu tiên. Filter được áp dụng trong quá trình đăng ký meter; không nên kỳ vọng thêm một filter muộn sẽ xóa hoặc biến đổi ngược những meter đã tồn tại.

## Ba quyết định trong accept()

Phương thức accept() trả về một trong ba giá trị MeterFilterReply:

| Kết quả | Ý nghĩa | Điều gì xảy ra tiếp theo? |
|---|---|---|
| NEUTRAL | Filter không có ý kiến | Tiếp tục xét accept() của filter kế tiếp |
| ACCEPT | Chấp nhận meter | Kết thúc sớm vòng xét chấp nhận; các filter accept() phía sau không được hỏi |
| DENY | Từ chối meter | Kết thúc sớm vòng xét chấp nhận; meter không được đăng ký bình thường |

Nếu mọi filter đều trả về NEUTRAL, meter được chấp nhận theo chính sách mặc định của registry.

Điểm quan trọng là ACCEPT và DENY đều là quyết định kết thúc đối với vòng đánh giá accept(). NEUTRAL mới là kết quả cho phép kiểm tra tiếp. Vì vậy, một filter trả ACCEPT có thể ngăn filter phía sau thực hiện quyết định DENY.

### Ví dụ ba filter nối tiếp

Giả sử registry có thứ tự:

1. Filter A: từ chối tên bắt đầu bằng internal.
2. Filter B: chấp nhận tên bắt đầu bằng business.
3. Filter C: từ chối mọi meter còn lại.

Quá trình xét:

| Tên meter | Filter A | Filter B | Filter C | Kết quả |
|---|---|---|---|---|
| internal.debug.events | DENY | Không được gọi | Không được gọi | Từ chối |
| business.orders.created | NEUTRAL | ACCEPT | Không được gọi | Chấp nhận sớm |
| jvm.memory.used | NEUTRAL | NEUTRAL | DENY | Từ chối |

Sơ đồ quyết định:

~~~text
Meter mới
   |
   v
Filter A: internal.* ?
   | DENY ----------------------> Từ chối
   | NEUTRAL
   v
Filter B: business.* ?
   | ACCEPT --------------------> Chấp nhận, dừng xét accept
   | NEUTRAL
   v
Filter C: deny all
   |
   v
Từ chối
~~~

Đây là cách dùng thứ tự để thể hiện chính sách: một số meter bị cấm tuyệt đối, một nhóm được cho phép rõ ràng, phần còn lại bị từ chối.

## Tác động của ACCEPT sớm

### Filter cho phép rộng có thể vô hiệu hóa filter phía sau

Đoạn cấu hình sau cho phép mọi meter có tên bắt đầu bằng business:

~~~java
registry.config()
        .meterFilter(MeterFilter.acceptNameStartsWith("business."))
        .meterFilter(MeterFilter.deny());
~~~

Với meter business.orders.created, filter đầu trả ACCEPT. Filter deny() phía sau không được gọi trong vòng xét chấp nhận. Với meter jvm.memory.used, filter đầu trả NEUTRAL, sau đó deny() trả DENY.

Điều này có thể được dùng có chủ đích để tạo allow-list. Nhưng nếu phía sau còn filter giới hạn số meter, giới hạn tag hoặc từ chối một trường hợp đặc biệt, đặt ACCEPT quá sớm có thể làm các quyết định đó không còn hiệu lực.

### Đặt DENY cụ thể và giới hạn trước ACCEPT rộng

Ví dụ, ứng dụng muốn:

- Từ chối metric debug nội bộ.
- Giới hạn số giá trị tag tenant của metric nghiệp vụ.
- Cho phép các metric business còn lại.
- Từ chối mọi nhóm khác.

Hãy đăng ký theo thứ tự:

~~~java
registry.config()
        .meterFilter(
                MeterFilter.denyNameStartsWith("internal.debug")
        )
        .meterFilter(
                MeterFilter.maximumAllowableTags(
                        "business.",
                        "tenant",
                        20,
                        MeterFilter.deny()
                )
        )
        .meterFilter(
                MeterFilter.acceptNameStartsWith("business.")
        )
        .meterFilter(MeterFilter.deny());
~~~

Với metric business.orders.created có tag tenant:

- Khi chưa vượt 20 giá trị tenant, filter giới hạn trả NEUTRAL; filter allow-list sau đó trả ACCEPT.
- Khi đã vượt giới hạn, filter giới hạn trả DENY; filter allow-list không được gọi.
- Metric internal.debug.* bị từ chối ngay ở filter đầu.
- Metric ngoài hai nhóm trên đi đến filter cuối và bị từ chối.

Nếu đổi thứ tự, đặt acceptNameStartsWith("business.") trước maximumAllowableTags(...), các meter nghiệp vụ sẽ được chấp nhận sớm và filter giới hạn không còn được xét trong vòng accept(). Đây là lý do các filter có khả năng từ chối hoặc giới hạn phải được đặt trước filter cho phép rộng.

## Dùng NEUTRAL để phối hợp nhiều chính sách

Một filter nên trả NEUTRAL khi nó không chịu trách nhiệm quyết định cuối cùng cho meter đó. Ví dụ:

- Filter A chỉ quan tâm tên internal.debug.*.
- Filter B chỉ quan tâm metric business.*.
- Filter C là chính sách mặc định cho các meter còn lại.

Khi meter không thuộc phạm vi của filter, trả NEUTRAL để các filter tiếp theo được xem xét. Không trả ACCEPT chỉ vì filter hiện tại không thấy vấn đề; điều đó sẽ biến một nhận xét cục bộ thành quyết định cuối cùng và chặn chính sách của các filter sau.

Ví dụ custom filter:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.config.MeterFilterReply;

public final class InternalMetricFilter implements MeterFilter {
    @Override
    public MeterFilterReply accept(Meter.Id id) {
        if (id.getName().startsWith("internal.debug.")) {
            return MeterFilterReply.DENY;
        }

        return MeterFilterReply.NEUTRAL;
    }
}
~~~

Filter này chỉ chịu trách nhiệm từ chối metric debug. Các tên khác được chuyển tiếp cho filter kế tiếp.

## Phân biệt accept với map và configure

Không nên gộp mọi hành vi của MeterFilter thành một quyết định ACCEPT/DENY.

### accept quyết định đăng ký

accept() trả lời câu hỏi meter có được đăng ký hay không. Thứ tự và short-circuit của ACCEPT/DENY áp dụng cho vòng đánh giá quyết định này.

### map biến đổi danh tính

map() có thể thay đổi Meter.Id, ví dụ đổi tên hoặc loại bỏ tag. Nếu mục tiêu là chuẩn hóa tên/tag, hãy dùng filter chuyên cho mapping thay vì trả ACCEPT để cố bỏ qua chính sách khác.

Một ví dụ bỏ tag nhạy cảm khỏi metric:

~~~java
registry.config()
        .meterFilter(MeterFilter.ignoreTags("sessionId", "requestId"));
~~~

Tên và tag cuối cùng cần được thiết kế nhất quán với dashboard. Khi đổi tên hoặc bỏ tag đang được truy vấn, hãy cập nhật dashboard và alert phụ thuộc vào chúng.

### configure điều chỉnh thống kê phân bố

configure() dùng để thay đổi cấu hình phân bố của meter, chẳng hạn percentile histogram, SLA boundaries hoặc cửa sổ thống kê. Đây là trách nhiệm khác với quyết định chấp nhận.

Ví dụ bật percentile histogram cho timer HTTP:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;

MeterFilter httpHistogram = new MeterFilter() {
    @Override
    public DistributionStatisticConfig configure(
            Meter.Id id,
            DistributionStatisticConfig config) {
        if (id.getName().startsWith("http.server.requests")) {
            return DistributionStatisticConfig.builder()
                    .percentilesHistogram(true)
                    .build()
                    .merge(config);
        }

        return config;
    }
};

registry.config().meterFilter(httpHistogram);
~~~

Đoạn code trên chỉ minh họa cách cấu hình thống kê theo tên meter. Hãy chọn bucket/giới hạn phù hợp với miền latency và backend. Histogram làm tăng số chuỗi dữ liệu; không bật đại trà nếu chưa tính chi phí.

Các hook map() và configure() là trách nhiệm riêng của filter pipeline. Không dùng kết quả ACCEPT như một cách thay thế cho mapping hoặc cấu hình thống kê; hãy đặt từng chính sách vào đúng hook và kiểm thử theo phiên bản Micrometer mà dự án đang sử dụng.

## Giới hạn cardinality và thứ tự filter

maximumAllowableTags(...) là một filter thường cần được đặt trước allow-list rộng. Ví dụ:

~~~java
MeterFilter tenantLimit = MeterFilter.maximumAllowableTags(
        "business.orders",
        "tenant",
        20,
        MeterFilter.deny()
);

registry.config()
        .meterFilter(tenantLimit)
        .meterFilter(MeterFilter.acceptNameStartsWith("business."));
~~~

Filter giới hạn cho phép các giá trị tag đã nằm trong ngân sách. Khi xuất hiện giá trị mới vượt ngưỡng, nhánh onMaxReached trả DENY và meter mới không được đăng ký bình thường.

Giới hạn này không tự chuẩn hóa tenant lạ thành other. Nó chỉ chặn meter vượt ngưỡng. Nếu muốn gom giá trị vào nhóm cố định, hãy chuẩn hóa ở instrumentation trước khi meter được tạo, rồi dùng MeterFilter làm lớp bảo vệ bổ sung.

Tương tự, maximumAllowableMetrics(...) có thể giới hạn tổng số meter được đăng ký. Hãy đặt các filter giới hạn trước filter ACCEPT rộng để quyết định giới hạn có cơ hội được xét.

## Kiểm thử thứ tự filter

Nên kiểm thử chính sách ở cấp registry để xác nhận thứ tự thực tế. SimpleMeterRegistry phù hợp cho unit test vì không cần kết nối backend.

### ACCEPT sớm chặn DENY phía sau

~~~java
import io.micrometer.core.instrument.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MeterFilterOrderTest {
    @Test
    void earlyAcceptPreventsLaterDenyFromRejectingMeter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            registry.config()
                    .meterFilter(MeterFilter.acceptNameStartsWith("business."))
                    .meterFilter(MeterFilter.deny());

            registry.counter("business.orders.created");

            assertThat(registry.find("business.orders.created").counter())
                    .isNotNull();
        } finally {
            registry.close();
        }
    }
}
~~~

Test này chứng minh ACCEPT của filter đầu kết thúc vòng xét chấp nhận; filter từ chối phía sau không loại bỏ meter nghiệp vụ.

### Đặt DENY trước ACCEPT

~~~java
@Test
void earlierDenyCannotBeOverriddenByLaterAccept() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        registry.config()
                .meterFilter(MeterFilter.deny())
                .meterFilter(MeterFilter.acceptNameStartsWith("business."));

        registry.counter("business.orders.created");

        assertThat(registry.find("business.orders.created").counter())
                .isNull();
    } finally {
        registry.close();
    }
}
~~~

Vì filter đầu đã trả DENY, filter allow-list phía sau không được gọi. Đây là lý do thứ tự đăng ký phải phản ánh thứ tự ưu tiên của chính sách.

### Kiểm thử giới hạn tag trước allow-list

Với maximumAllowableTags(...), hãy tạo các meter cùng tên nhưng có nhiều giá trị tag khác nhau. Xác minh số giá trị trong giới hạn được đăng ký và giá trị mới vượt ngưỡng bị từ chối. Sau đó đổi thứ tự để kiểm chứng rằng filter allow-list rộng đặt trước có thể khiến giới hạn không được xét trong vòng accept.

Không chỉ kiểm thử trường hợp bình thường. Nên có test cho:

- Tên nằm trong nhóm bị từ chối cụ thể.
- Tên được allow-list chấp nhận sớm.
- Tên không khớp filter nào và đi đến default deny.
- Meter có tag vượt ngưỡng.
- Mapping tên/tag và cấu hình histogram vẫn đúng mục đích sau khi thay đổi thứ tự.

## Quy tắc sắp xếp filter trong ứng dụng

Một thứ tự dễ đọc và dễ kiểm thử thường là:

1. **Từ chối cụ thể:** chặn metric nội bộ, debug hoặc metric không được phép xuất.
2. **Giới hạn tài nguyên:** áp dụng maximum metrics, maximum tags và các guardrail cardinality.
3. **Cho phép có chọn lọc:** chấp nhận các prefix hoặc nhóm metric đã được duyệt.
4. **Chính sách mặc định:** chấp nhận hoặc từ chối phần còn lại tùy mục tiêu triển khai.
5. **Mapping/configuration:** tổ chức riêng các quy tắc đổi tên/tag và thống kê phân bố; kiểm thử chúng như các hành vi độc lập.

Nếu registry cần xuất mọi metric mặc định và chỉ chặn một số nhóm, có thể không cần default deny. Khi đó, các filter cụ thể trả DENY cho nhóm bị cấm và NEUTRAL cho phần còn lại.

Không có một thứ tự duy nhất phù hợp cho mọi ứng dụng. Điều quan trọng là ghi rõ chính sách, hiểu filter nào có thể trả kết quả kết thúc và kiểm thử các trường hợp có thể bị short-circuit.

## Checklist trước khi đưa filter vào production

1. Mỗi filter có một trách nhiệm rõ ràng: accept, map hoặc configure.
2. Filter không quyết định cuối cùng trả NEUTRAL.
3. Các điều kiện DENY cụ thể được đặt trước ACCEPT rộng.
4. Giới hạn cardinality và số meter được đặt trước allow-list có thể short-circuit.
5. Có default policy rõ ràng cho meter không khớp nhóm nào.
6. Filter được cấu hình trước khi meter đầu tiên được đăng ký.
7. Đã kiểm tra tác động của mapping đến tên/tag mà dashboard sử dụng.
8. Histogram/percentile chỉ bật cho metric cần thiết và có ngân sách cardinality.
9. Unit test xác minh cả ACCEPT sớm, DENY sớm và NEUTRAL tiếp tục.
10. Integration test xác nhận endpoint export chỉ chứa meter dự kiến.

## Kết luận

Thứ tự MeterFilter quyết định chính sách chấp nhận meter. NEUTRAL cho phép filter kế tiếp xem xét; DENY từ chối ngay; ACCEPT chấp nhận sớm và ngăn các filter accept() phía sau đưa ra quyết định. Vì vậy, hãy đặt từ chối cụ thể và giới hạn cardinality trước allow-list rộng, rồi mới áp dụng chính sách mặc định. Tách riêng trách nhiệm accept, map và configure, đồng thời kiểm thử thứ tự bằng SimpleMeterRegistry, sẽ giúp tránh việc một quyết định chấp nhận sớm vô tình bỏ qua guardrail quan trọng.

## Tài liệu tham khảo

- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): quyết định accept/deny, mapping meter ID và cấu hình distribution.
- [Micrometer - MeterFilter API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/config/MeterFilter.html): các factory filter và các hook accept, map, configure.
- [Micrometer - MeterFilterReply API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/config/MeterFilterReply.html): semantics của ACCEPT, NEUTRAL và DENY.
