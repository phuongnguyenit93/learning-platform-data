# Thay đổi metadata hoặc tag sau khi meter đã được đăng ký

Trong Micrometer, một meter được đăng ký với một định danh và bộ cấu hình cụ thể. Sau khi registry đã tạo meter, không thể sửa trực tiếp tên, tag, description, base unit hoặc cấu hình phân phối của meter đó như sửa thuộc tính của một object thông thường.

Điểm quan trọng nhất là tag tham gia vào định danh của meter. Đăng ký lại cùng tên nhưng đổi giá trị tag thường tạo ra một meter khác và một time series mới. Đăng ký lại cùng định danh nhưng đổi description không làm meter cũ tự cập nhật metadata. Vì vậy, cần thiết kế thay đổi theo vòng đời đăng ký và kế hoạch chuyển đổi dữ liệu.

## 1. Phân biệt định danh, metadata và giá trị đo

Một meter thường được mô tả bằng các thành phần sau:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Tên | `orders.created` | Xác định đại lượng được đo |
| Tag key/value | `channel=web` | Chia số liệu thành các chiều phân tích |
| Loại meter | Counter, Gauge, Timer | Xác định cách ghi nhận và diễn giải |
| Description | Số đơn hàng được tạo thành công | Giải thích ý nghĩa của meter |
| Base unit | orders, seconds, bytes | Diễn tả đơn vị của giá trị |
| Cấu hình phân phối | Histogram, percentile, expected range | Quy định cách meter ghi nhận phân phối |

Tên và tag là phần định danh quan trọng để registry phân biệt các meter. Hai meter có cùng tên nhưng khác tag value là hai meter riêng. Ví dụ:

- `orders.created{channel="web"}`
- `orders.created{channel="mobile"}`

Đây là hai chuỗi thời gian riêng, dù cùng đo số đơn hàng được tạo.

Description và base unit là metadata mô tả meter. Chúng không phải tag dimension để lọc từng sự kiện. Cấu hình histogram hoặc percentile quyết định cách meter thu thập và xuất thống kê phân phối.

Cần giữ đúng ngữ nghĩa của meter trong suốt vòng đời của nó. Nếu một metric từng biểu diễn số tiền theo VND rồi chuyển sang USD nhưng vẫn giữ cùng tên và định danh, dashboard có thể cộng hoặc so sánh hai đại lượng không cùng đơn vị.

## 2. Vì sao không thể sửa meter đã đăng ký?

### Meter.Id là định danh bất biến

Micrometer biểu diễn thông tin định danh và metadata của meter bằng `Meter.Id`. Đây là đối tượng bất biến. Các thao tác tạo ID mới, chẳng hạn thay tên hoặc thay tag, tạo ra một ID khác; chúng không thay đổi ID của meter đang nằm trong registry.

Registry quản lý các meter đã đăng ký và tránh tạo nhiều meter trùng định danh. Khi đăng ký lại cùng tên và cùng tập tag, registry thường trả về meter đã tồn tại. Các giá trị description hoặc base unit mới truyền qua builder không có nghĩa là metadata của meter cũ được cập nhật.

Ví dụ:

```java
Counter original = Counter.builder("orders.created")
    .description("Số đơn hàng được tạo thành công")
    .baseUnit("orders")
    .tag("channel", "web")
    .register(registry);

// Cùng tên và cùng tag, nhưng description mới.
Counter attemptedUpdate = Counter.builder("orders.created")
    .description("Số đơn hàng đã được xác nhận")
    .baseUnit("orders")
    .tag("channel", "web")
    .register(registry);
```

Lần đăng ký thứ hai không phải là thao tác cập nhật description cho meter đầu tiên. Registry đã có meter với định danh đó, vì vậy ứng dụng không nên dựa vào builder thứ hai để thay metadata của meter đang chạy.

Nếu cần đổi tag value, kết quả khác:

```java
Counter webCounter = Counter.builder("orders.created")
    .description("Số đơn hàng được tạo thành công")
    .baseUnit("orders")
    .tag("channel", "web")
    .register(registry);

Counter mobileCounter = Counter.builder("orders.created")
    .description("Số đơn hàng được tạo thành công")
    .baseUnit("orders")
    .tag("channel", "mobile")
    .register(registry);
```

Hai counter có tag khác nhau nên là hai meter riêng. Meter dành cho `channel=web` vẫn tồn tại; đăng ký meter dành cho `channel=mobile` không sửa hoặc thay thế meter cũ.

### Thay đổi tag tạo ra time series mới

Backend metrics lưu số liệu theo tên metric và các chiều tag/label. Khi tag thay đổi, backend nhìn thấy một chuỗi thời gian khác. Ví dụ, trước đây ứng dụng chỉ có:

```text
orders.created{application="orders-service"}
```

Sau khi thêm tag `region`, meter mới có thể xuất hiện như:

```text
orders.created{application="orders-service", region="ap-southeast-1"}
```

Chuỗi cũ và chuỗi mới có thể cùng xuất hiện trong giai đoạn chuyển tiếp. Dữ liệu lịch sử của chuỗi cũ vẫn có thể còn trong backend theo chính sách retention, ngay cả khi ứng dụng đã ngừng xuất nó.

Vì vậy, thay đổi tag là thay đổi schema dữ liệu metrics. Dashboard, truy vấn, cảnh báo và quy trình phân tích phụ thuộc vào schema đó đều cần được xem xét.

## 3. Metadata nào có thể thay đổi và thay đổi bằng cách nào?

### Description

Description giải thích ý nghĩa của meter. Nên đặt description ngay khi tạo meter:

```java
Counter.builder("orders.created")
    .description("Số đơn hàng được tạo thành công")
    .register(registry);
```

Nếu chỉ cần sửa câu mô tả trong mã nguồn, hãy cập nhật builder và triển khai một registry mới qua vòng đời khởi động ứng dụng. Không giả định rằng gọi lại builder trên một registry đang chạy sẽ cập nhật description của meter đã tồn tại.

Description nên mô tả chính xác sự kiện hoặc đại lượng, tránh ghi nội dung thay đổi theo request, thời gian hoặc người dùng.

### Base unit

Base unit giúp người đọc và backend hiểu đơn vị của số đo. Hãy dùng một đơn vị nhất quán trong toàn bộ vòng đời metric.

```java
DistributionSummary.builder("orders.payload.size")
    .description("Kích thước payload của đơn hàng")
    .baseUnit("bytes")
    .register(registry);
```

Nếu chỉ sửa cách diễn đạt description, có thể cập nhật ở lần khởi tạo registry tiếp theo. Nếu thay đổi đơn vị hoặc ý nghĩa vật lý của giá trị, hãy xem đó là thay đổi hợp đồng metric. Tạo metric name mới hoặc phiên bản mới để dữ liệu cũ và mới không bị diễn giải lẫn nhau.

Ví dụ, nếu `orders.value` trước đây ghi VND nhưng phiên bản mới ghi USD, không tiếp tục xuất giá trị USD dưới cùng một metric identity như thể nó vẫn là VND. Có thể chuyển sang tên rõ nghĩa như `orders.value.usd`, hoặc chuẩn hóa toàn bộ dữ liệu về một đơn vị thống nhất trước khi ghi nhận.

### Loại meter

Loại meter quyết định cách diễn giải dữ liệu. Counter, gauge, timer và distribution summary không thể hoán đổi chỉ bằng cách thay metadata. Nếu cùng tên và tag nhưng thay đổi ngữ nghĩa từ số sự kiện sang trạng thái hiện tại, hãy chọn một tên metric mới phù hợp với ý nghĩa mới.

Ví dụ:

- `orders.created`: số sự kiện đơn hàng được tạo, dùng counter.
- `orders.pending`: số đơn hàng đang chờ tại thời điểm quan sát, dùng gauge.

Đặt tên riêng giúp dashboard và người vận hành không nhầm số tích lũy với trạng thái hiện tại.

### Cấu hình histogram và percentile

Cấu hình histogram, percentile, minimum/maximum expected value và các thuộc tính phân phối cần được thiết lập khi meter được tạo hoặc qua filter áp dụng trong quá trình đăng ký.

```java
import java.time.Duration;

Timer.builder("orders.payment.duration")
    .description("Thời gian xử lý thanh toán")
    .publishPercentileHistogram()
    .minimumExpectedValue(Duration.ofMillis(1))
    .maximumExpectedValue(Duration.ofSeconds(10))
    .register(registry);
```

Khi timer đã được đăng ký, không nên kỳ vọng thay đổi builder sẽ cấu hình lại histogram của timer hiện tại. Nếu cần thay đổi cách thu thập phân phối, hãy lập kế hoạch tạo registry mới hoặc chuyển đổi sang metric mới tùy mức độ ảnh hưởng và yêu cầu tương thích của backend.

## 4. Thay đổi tag: tạo meter mới thay vì sửa meter cũ

Tag biểu diễn một chiều phân tích có tập giá trị dự kiến hữu hạn. Khi giá trị tag thay đổi, registry tạo hoặc tìm meter tương ứng với tổ hợp tên và tag mới.

Ví dụ đếm đơn hàng theo kênh:

```java
private String normalizeChannel(String channel) {
    return switch (channel) {
        case "web", "mobile", "partner" -> channel;
        default -> "other";
    };
}

public void recordOrderCreated(String channel) {
    registry.counter(
        "orders.created",
        "channel",
        normalizeChannel(channel)
    ).increment();
}
```

Mỗi giá trị hợp lệ tạo một meter riêng:

- `orders.created{channel="web"}`
- `orders.created{channel="mobile"}`
- `orders.created{channel="partner"}`
- `orders.created{channel="other"}`

Đây là cách đúng khi muốn phân tích số sự kiện theo một chiều có cardinality thấp và ổn định.

Không nên dùng tag để mô tả trạng thái thay đổi liên tục của cùng một đối tượng. Ví dụ, nếu muốn biết số công việc hiện đang ở trạng thái pending, hãy đo số lượng bằng gauge. Nếu muốn đếm số lần công việc chuyển sang trạng thái success hoặc failed, có thể dùng counter với tag `outcome` thuộc tập giá trị cố định.

### Chuẩn hóa giá trị tag

Dữ liệu đầu vào không nên được dùng trực tiếp làm tag nếu nó có thể chứa vô hạn giá trị. Hãy ánh xạ về một tập giá trị hữu hạn:

```java
private String normalizeOutcome(String rawOutcome) {
    return switch (rawOutcome) {
        case "success", "rejected", "failed" -> rawOutcome;
        default -> "other";
    };
}
```

Không gắn các giá trị sau vào tag:

- ID người dùng, ID đơn hàng hoặc request ID.
- Email, số điện thoại, access token.
- URL đầy đủ hoặc query string.
- Nội dung exception hoặc thông báo lỗi tự do.
- Timestamp hoặc giá trị ngẫu nhiên.
- Tên tenant tùy ý nếu số tenant có thể tăng không giới hạn.

Mỗi tổ hợp tag có thể tạo một time series. Nếu một tag có hàng triệu giá trị, số meter và chi phí lưu trữ có thể tăng rất nhanh.

## 5. Common tags và MeterFilter phải được cấu hình đúng thời điểm

### Common tags

Common tags là các tag được thêm vào nhiều meter trong registry. Chúng hữu ích để gắn thông tin ổn định như tên ứng dụng, môi trường hoặc khu vực triển khai.

```java
registry.config().commonTags(
    "application", "orders-service",
    "environment", "production"
);
```

Hãy cấu hình common tags trước khi các meter được đăng ký. Nếu thêm common tags sau khi một số meter đã tồn tại, các meter cũ vẫn giữ định danh cũ trong khi meter đăng ký sau có thể nhận thêm tag mới. Kết quả là cùng một metric name có thể xuất hiện với schema tag không đồng nhất.

Trong Spring Boot, có thể cấu hình qua thuộc tính:

```properties
management.metrics.tags.application=orders-service
management.metrics.tags.environment=production
```

Hoặc dùng `MeterRegistryCustomizer` để cấu hình registry khi khởi tạo:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config().commonTags(
            "application", "orders-service",
            "environment", "production"
        );
    }
}
```

Đặt common tags tại một nơi cấu hình trung tâm giúp mọi binder và meter nghiệp vụ nhận cùng quy ước, miễn là chúng được đăng ký sau khi customizer đã cấu hình registry.

### MeterFilter

`MeterFilter` có thể biến đổi, từ chối hoặc cấu hình meter trong quá trình đăng ký. Ví dụ, thêm tag chung, đổi tên meter, giới hạn tag values hoặc áp dụng cấu hình phân phối.

```java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "orders.created",
        "channel",
        10,
        MeterFilter.deny()
    )
);
```

Filter này giới hạn số giá trị khác nhau của tag `channel` cho meter `orders.created`. Khi giới hạn bị vượt, meter mới có thể bị từ chối theo filter đã chọn.

Filter được áp dụng trong quá trình đăng ký meter. Cài filter sau khi một meter đã tồn tại không tự động sửa ID, tag hoặc cấu hình của meter đó. Vì vậy:

1. Cấu hình filter trước khi binder và mã nghiệp vụ đăng ký meter.
2. Đảm bảo các filter không mâu thuẫn về tên hoặc tag.
3. Kiểm tra thứ tự filter khi có nhiều filter cùng biến đổi một meter.
4. Kiểm tra số meter thực tế sau khi ứng dụng khởi động.

Không dùng filter như một cách thay đổi tùy ý schema của các meter đang chạy. Khi schema đã tồn tại, hãy xử lý bằng kế hoạch chuyển đổi rõ ràng.

## 6. Thêm, đổi tên hoặc bỏ tag trong hệ thống đang chạy

Các thay đổi schema thường gặp có cách xử lý khác nhau.

| Thay đổi | Hành vi trong registry | Việc cần làm |
|---|---|---|
| Đổi tag value | Tạo meter có định danh khác | Chọn tập giá trị mới và cập nhật truy vấn |
| Thêm tag | Tạo tổ hợp định danh mới | Chuẩn bị dashboard và alert hiểu tag mới |
| Bỏ tag | Tạo định danh mới với ít chiều hơn | Kiểm tra nguy cơ gộp nhiều nhóm dữ liệu |
| Đổi tên metric | Tạo meter khác | Cập nhật truy vấn và kế hoạch chuyển tiếp |
| Đổi description | Không cập nhật meter đã đăng ký | Cập nhật ở lần khởi tạo registry mới |
| Đổi base unit | Không thay đổi metadata của meter đang tồn tại | Giữ đơn vị cũ hoặc tạo metric mới nếu ngữ nghĩa thay đổi |
| Đổi loại meter | Thay đổi ngữ nghĩa của số đo | Dùng tên metric mới |
| Đổi histogram/percentile | Không cấu hình lại meter đã đăng ký | Cấu hình trước đăng ký hoặc chuyển đổi có kiểm soát |

### Quy trình chuyển đổi tag

Giả sử hệ thống đang xuất:

```text
orders.created{application="orders-service"}
```

Đội vận hành muốn phân tích thêm theo `channel`.

**Bước 1: Chốt schema mới**

Xác định tên tag, tập giá trị, cách chuẩn hóa và số series dự kiến. Không đưa ID hoặc giá trị không giới hạn vào tag.

**Bước 2: Cập nhật instrumentation**

Đăng ký meter với tag mới tại điểm ghi nhận. Xác nhận các giá trị tag được chuẩn hóa.

**Bước 3: Kiểm tra đầu ra**

Đọc endpoint metrics hoặc registry để xác nhận meter mới có tag đúng, không có tag rỗng bất ngờ và không phát sinh cardinality ngoài dự kiến.

**Bước 4: Cập nhật dashboard và cảnh báo**

Các truy vấn đang giả định schema cũ cần được rà soát. Nếu truy vấn mới nhóm theo `channel`, hãy bảo đảm dữ liệu lịch sử không có chiều này được xử lý phù hợp.

**Bước 5: Chọn thời điểm ngừng schema cũ**

Sau khi dashboard và cảnh báo đã dùng schema mới, ngừng ghi meter cũ. Dữ liệu lịch sử cũ có thể tiếp tục tồn tại trong backend cho đến khi hết retention.

### Có nên ghi đồng thời meter cũ và mới?

Dual-write có thể hữu ích trong giai đoạn chuyển tiếp khi cần so sánh số liệu hoặc nâng cấp dashboard theo từng đợt. Tuy nhiên, nếu cả hai meter cùng đại diện một sự kiện và truy vấn tổng hợp cả hai, kết quả có thể bị đếm hai lần.

Nếu cần dual-write:

- Tách tên metric hoặc phiên bản schema đủ rõ để truy vấn có thể chọn chính xác.
- Xác định dashboard nào đọc metric cũ và dashboard nào đọc metric mới.
- Không cộng hai luồng cùng sự kiện trong cùng một biểu đồ tổng.
- Đặt thời hạn kết thúc dual-write và tiêu chí ngừng metric cũ.

Không dual-write chỉ để giữ cảm giác an toàn. Chỉ dùng khi có yêu cầu tương thích hoặc xác minh chuyển đổi cụ thể.

## 7. Gỡ meter cũ khỏi registry

Micrometer cung cấp thao tác loại bỏ meter khỏi registry. Khi cần ngừng xuất một meter cụ thể, có thể giữ lại tham chiếu tới meter đã đăng ký và gọi:

```java
registry.remove(oldMeter);
```

Thao tác này loại meter khỏi registry hiện tại. Nó không xóa dữ liệu lịch sử đã được backend lưu trữ. Những nơi còn giữ tham chiếu tới object meter cũ cũng cần được kiểm tra để tránh tiếp tục ghi vào meter không còn được registry quản lý.

Chỉ gỡ meter cụ thể khi đã biết rõ tác động. Tránh gọi `registry.clear()` để xử lý một thay đổi nhỏ vì thao tác đó loại bỏ toàn bộ meter trong registry, bao gồm cả meter do framework và binder đăng ký.

Trong nhiều ứng dụng, cách đơn giản nhất để loại bỏ meter cũ là triển khai phiên bản mới và để registry mới được tạo trong quá trình khởi động. Với registry sống lâu hoặc hệ thống plugin, cần quản lý rõ vòng đời của meter và tham chiếu đang giữ.

## 8. Kiểm thử thay đổi metadata và tag

Kiểm thử với `SimpleMeterRegistry` giúp xác minh registry tạo đúng meter cho từng tổ hợp tag và giữ metadata được thiết lập ở lần đăng ký đầu tiên.

Ví dụ kiểm tra hai giá trị tag tạo hai meter riêng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MeterIdentityTest {

    @Test
    void differentTagValuesCreateDifferentMeters() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Counter web = Counter.builder("orders.created")
            .description("Số đơn hàng được tạo")
            .tag("channel", "web")
            .register(registry);

        Counter mobile = Counter.builder("orders.created")
            .description("Số đơn hàng được tạo")
            .tag("channel", "mobile")
            .register(registry);

        web.increment(2);
        mobile.increment(3);

        assertEquals(
            2.0,
            registry.get("orders.created")
                .tag("channel", "web")
                .counter()
                .count()
        );

        assertEquals(
            3.0,
            registry.get("orders.created")
                .tag("channel", "mobile")
                .counter()
                .count()
        );
    }
}
```

Có thể kiểm tra metadata được thiết lập trên meter đầu tiên:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MeterMetadataTest {

@Test
void reRegisteringSameIdentityDoesNotUpdateExistingDescription() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    Counter original = Counter.builder("orders.created")
        .description("Mô tả ban đầu")
        .tag("channel", "web")
        .register(registry);

    Counter secondRegistration = Counter.builder("orders.created")
        .description("Mô tả mới")
        .tag("channel", "web")
        .register(registry);

    assertEquals("Mô tả ban đầu", original.getId().getDescription());
    assertEquals(
        "Mô tả ban đầu",
        secondRegistration.getId().getDescription()
    );
}
}
```

Ngoài unit test, nên có integration test xác minh:

- Common tags được gắn vào các meter khi registry khởi tạo.
- Binder được đăng ký sau cấu hình registry và nhận đúng filter.
- Meter bị filter từ chối không xuất hiện trong endpoint.
- Tag mới xuất hiện đúng trong Prometheus scrape output.
- Dashboard và alert dùng đúng schema mới.
- Không có metric cũ và mới cùng bị cộng gây double-count.

Kiểm thử nên dùng đúng phiên bản Micrometer và registry mà ứng dụng triển khai. Một số chi tiết định dạng tên, metadata hoặc histogram phụ thuộc backend và phiên bản.

## 9. Các lỗi thường gặp khi thay đổi meter

- **Gọi lại builder để sửa description:** builder tạo yêu cầu đăng ký; nó không phải API cập nhật meter đã tồn tại.
- **Thêm common tags sau khi meter đã được tạo:** các meter cũ có thể thiếu tag mới, tạo schema không đồng nhất.
- **Thêm filter quá muộn:** filter không tự chạy lại trên các meter đã đăng ký.
- **Đổi tag value theo từng request:** tạo thêm time series liên tục và làm cardinality tăng.
- **Dùng cùng metric name cho hai đơn vị khác nhau:** khiến truy vấn tổng hợp dữ liệu không cùng ngữ nghĩa.
- **Đổi loại meter nhưng giữ tên và tag:** làm hợp đồng metric không rõ ràng và có thể gây xung đột đăng ký.
- **Gỡ toàn bộ registry để sửa một meter:** làm mất các meter khác do ứng dụng, framework và binder đăng ký.
- **Dual-write mà không cập nhật truy vấn:** có thể khiến số liệu bị cộng hai lần.
- **Cho rằng xóa meter sẽ xóa lịch sử backend:** registry và backend là hai vòng đời dữ liệu khác nhau.

## 10. Checklist trước khi triển khai thay đổi

- [ ] Đã xác định thay đổi thuộc tag, description, base unit, loại meter hay cấu hình phân phối.
- [ ] Đã xác nhận meter hiện tại và schema tag đang được backend nhận.
- [ ] Tag mới có tập giá trị hữu hạn và không chứa dữ liệu định danh.
- [ ] Đơn vị và ngữ nghĩa số đo nhất quán giữa các phiên bản.
- [ ] Common tags và MeterFilter được cấu hình trước khi meter đăng ký.
- [ ] Dashboard, truy vấn và cảnh báo đã được rà soát.
- [ ] Có kế hoạch xử lý dữ liệu lịch sử và thời gian chuyển tiếp.
- [ ] Dual-write có tiêu chí kết thúc và tránh double-count.
- [ ] Unit test và integration test xác minh meter mới.
- [ ] Meter cũ chỉ bị gỡ khi đã đánh giá tác động và vòng đời tham chiếu.

Khi meter đã được đăng ký, hãy xem định danh và metadata của nó như một hợp đồng với hệ thống giám sát. Muốn thay đổi hợp đồng đó, cần tạo meter theo schema mới, kiểm tra đường xuất dữ liệu và chuyển các truy vấn phụ thuộc sang schema mới theo một kế hoạch có kiểm soát.

