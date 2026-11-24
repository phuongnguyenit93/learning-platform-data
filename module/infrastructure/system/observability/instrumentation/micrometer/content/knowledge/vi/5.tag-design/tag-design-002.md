# Số giá trị của từng tag và số tổ hợp meter được tạo

Khi thiết kế metrics bằng Micrometer, số tag riêng lẻ chưa cho biết đầy đủ chi phí dữ liệu. Điều quyết định số meter được tạo cho một tên metric là **số tổ hợp tag khác nhau thực sự xuất hiện**. Nếu một metric có nhiều chiều phân loại, số tổ hợp tối đa tăng theo tích số giá trị của từng chiều.

Ví dụ, một metric có 4 giá trị `method`, 5 giá trị `route` và 3 giá trị `status` có thể tạo tối đa 4 × 5 × 3 = 60 danh tính meter. Khi thêm một tag có 1.000 giá trị, giới hạn lý thuyết tăng lên 60.000. Vì vậy, thiết kế tag cần xem xét cả cardinality của từng tag lẫn tích số tổ hợp của tất cả tag trên cùng metric.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, phần này giúp bạn ước lượng số meter và chuỗi thời gian trước khi triển khai instrumentation, chọn chiều phân loại có ích, giới hạn tập giá trị và kiểm thử cardinality trong ứng dụng Java/Spring Boot.

## 1. Cardinality của một tag là gì?

Cardinality của một tag là số giá trị phân biệt mà tag đó có thể nhận trong phạm vi đang xét. Ví dụ, tag `method` có các giá trị `GET`, `POST`, `PUT`, `DELETE` thì cardinality là 4.

| Tag | Các giá trị được phép | Cardinality |
| --- | --- | ---: |
| `method` | GET, POST, PUT, DELETE | 4 |
| `status_class` | 2xx, 3xx, 4xx, 5xx | 4 |
| `result` | success, rejected, error | 3 |
| `channel` | web, mobile, partner, other | 4 |

Cardinality đếm số giá trị khác nhau, không phải số lần metric được ghi nhận. Một triệu request đều có `method=GET` vẫn chỉ đóng góp một giá trị cho tag `method` trong tập dữ liệu đó.

Cardinality cần được tính sau khi chuẩn hóa giá trị. Nếu ứng dụng nhận `WEB`, `web`, `Web` nhưng không chuẩn hóa, hệ thống có thể xem chúng là ba giá trị khác nhau. Nếu mọi biến thể được chuyển về `web`, chúng chỉ còn một giá trị.

## 2. Từ cardinality từng tag đến số tổ hợp

Giả sử một meter có tên `shop.orders.created` và hai tag:

```text
channel = web | mobile | partner
result  = success | rejected | error
```

Tag `channel` có 3 giá trị, tag `result` có 3 giá trị. Nếu mọi tổ hợp đều có thể xuất hiện, số danh tính meter tối đa là:

\[
N_{max} = 3 \times 3 = 9
\]

Các tổ hợp có thể có:

| `channel` | `result` | Danh tính |
| --- | --- | --- |
| web | success | 1 |
| web | rejected | 2 |
| web | error | 3 |
| mobile | success | 4 |
| mobile | rejected | 5 |
| mobile | error | 6 |
| partner | success | 7 |
| partner | rejected | 8 |
| partner | error | 9 |

Mỗi tổ hợp tên metric và tập tag khác nhau tương ứng với một danh tính trong `MeterRegistry`. Hai lần đăng ký có cùng tên và cùng tag sẽ dùng chung meter trong registry đó; thay đổi một tag value tạo danh tính khác.

### 2.1. Công thức tổng quát

Với một metric có `k` tag, gọi `C_i` là số giá trị được phép của tag thứ `i`. Số tổ hợp tối đa là:

\[
N_{max} = \prod_{i=1}^{k} C_i = C_1 \times C_2 \times \cdots \times C_k
\]

Ví dụ một metric HTTP có:

| Tag | Cardinality giả định |
| --- | ---: |
| `method` | 4 |
| `route` | 8 |
| `status_class` | 4 |
| `outcome` | 3 |
| **Tổ hợp tối đa** | **4 × 8 × 4 × 3 = 384** |

Nếu thêm `region` với 6 giá trị, giới hạn mới là 384 × 6 = 2.304 tổ hợp. Một chiều phân loại mới có thể làm số meter tăng theo cấp số nhân khi nhiều chiều được kết hợp.

### 2.2. Số tổ hợp thực tế có thể thấp hơn giới hạn

Tích số ở trên là giới hạn trên khi mọi tổ hợp đều có thể xuất hiện. Trong ứng dụng thực tế, một số tổ hợp có thể không hợp lệ hoặc không xảy ra. Ví dụ, một route chỉ hỗ trợ `GET`, còn route khác chỉ hỗ trợ `POST`; khi đó không phải mọi cặp `route` và `method` đều xuất hiện.

Gọi `N_observed` là số tổ hợp đã được đăng ký hoặc quan sát thực tế:

\[
0 \leq N_{observed} \leq N_{max}
\]

Không nên dựa vào mối tương quan giữa các tag để đặt ngân sách quá sát. Sau này luồng nghiệp vụ có thể thay đổi và làm xuất hiện những tổ hợp trước đây chưa có. Hãy dùng tích cardinality như một ước lượng bảo thủ để thiết kế giới hạn.

### 2.3. Tag tùy chọn cũng tạo thêm trạng thái

Nếu một tag đôi khi không có mặt, hãy tính cả trạng thái “không có tag” như một trạng thái bổ sung khi ước lượng. Ví dụ `region` có 5 giá trị và có thể vắng mặt ở một số call site thì có thể phát sinh tối đa 6 trạng thái liên quan đến chiều đó: 5 value và trạng thái không có tag.

Tuy nhiên, với một metric, nên giữ tập key nhất quán giữa các call site. Nếu muốn biểu diễn chưa xác định, hãy cân nhắc một value dự phòng có giới hạn như `unknown`, và dùng nhất quán. Tag bị thiếu, tag có value `unknown` và tag có value rỗng có thể tạo các danh tính khác nhau.

## 3. Phân biệt số meter với số chuỗi thời gian backend

Số tổ hợp tag giúp ước lượng số danh tính meter trong một registry. Số chuỗi thời gian mà backend lưu có thể lớn hơn vì còn phụ thuộc cách registry xuất meter và cấu hình của hệ thống giám sát.

Một số yếu tố cần tính riêng:

- **Nhiều tên metric:** nếu một service có nhiều metric name, cộng số tổ hợp của từng metric name để ước lượng tổng meter.
- **Nhiều instance:** mỗi instance được scrape thường có nhãn đích như `instance` hoặc `pod`. Cùng một tổ hợp tag ở 10 instance có thể trở thành 10 chuỗi thời gian riêng trong backend.
- **Histogram:** timer hoặc distribution summary xuất histogram có thể tạo nhiều chuỗi bucket, cùng các chuỗi `_count` và `_sum` cho mỗi tổ hợp tag. Số chuỗi phụ thuộc cấu hình bucket và registry.
- **Percentile:** một số cấu hình percentile xuất thêm chuỗi số liệu theo percentile. Đây là chi phí bổ sung ngoài số danh tính meter.
- **Tag chung:** tag gắn ở cấp registry hoặc được thêm bởi hạ tầng scrape cũng làm phân tách chuỗi thời gian trong backend.

Ví dụ, nếu một metric có 384 tổ hợp tag và được scrape từ 12 instance, riêng phần nhãn instance có thể tạo tối đa 384 × 12 = 4.608 chuỗi cơ sở trong backend. Nếu metric là histogram, số chuỗi thực tế còn tăng theo bucket và các chuỗi tổng hợp đi kèm.

Vì thế, không đồng nhất `registry.getMeters().size()` với số chuỗi thời gian cuối cùng trong Prometheus hoặc backend khác. Một phép đo trong Micrometer có thể được biểu diễn thành nhiều chuỗi khi xuất.

## 4. Ví dụ tính cardinality trong API HTTP

Giả sử dịch vụ đơn hàng đo `http.server.requests` với các tag đã được chuẩn hóa:

| Tag | Tập giá trị | Cardinality |
| --- | --- | ---: |
| `method` | GET, POST, PUT, DELETE | 4 |
| `route` | `/orders`, `/orders/{id}`, `/payments`, `/payments/{id}`, `/health`, `other` | 6 |
| `status_class` | 2xx, 3xx, 4xx, 5xx | 4 |
| `outcome` | SUCCESS, CLIENT_ERROR, SERVER_ERROR | 3 |
| **Tổ hợp tối đa** | **4 × 6 × 4 × 3** | **288** |

Nếu có 20 instance, backend có thể có đến 288 × 20 = 5.760 tổ hợp chuỗi cơ sở cho metric này, trước khi tính đến histogram hoặc các nhãn khác.

Giả sử nhóm phát triển thêm tag `exception` với 12 loại exception. Giới hạn tăng thành 288 × 12 = 3.456 tổ hợp trên mỗi instance. Nếu exception message được dùng trực tiếp thay vì tên class hoặc nhóm lỗi cố định, cardinality có thể không còn giới hạn thực tế.

Trước khi thêm một tag, hãy tự hỏi:

1. Tag này giúp phân tích hoặc hành động vận hành nào?
2. Có thể liệt kê đầy đủ các value hợp lệ không?
3. Số value tối đa là bao nhiêu trong production?
4. Tag có tương quan hoặc trùng ý nghĩa với chiều đã có không?
5. Tích số sau khi thêm tag có nằm trong ngân sách của service không?

Nếu không thể xác định tập value hoặc không có câu hỏi vận hành cần chiều dữ liệu đó, không nên thêm tag.

## 5. Chọn cardinality phù hợp cho từng loại tag

Không phải mọi tag đều cần cùng một giới hạn. Hãy chọn tập giá trị dựa trên ý nghĩa nghiệp vụ và cách dùng số liệu.

| Nhóm tag | Ví dụ | Thiết kế nên dùng |
| --- | --- | --- |
| HTTP method | GET, POST, PUT, DELETE | Danh sách method cố định; không nhận chuỗi tùy ý. |
| HTTP status | 200, 201, 400, 404, 500 | Có thể nhóm theo status class nếu không cần phân tích từng mã. |
| Route | `/orders/{id}` | Route template hoặc tên route đã đăng ký, không dùng URL thực tế có ID. |
| Kết quả nghiệp vụ | success, rejected, error | Enum hoặc danh sách value do ứng dụng kiểm soát. |
| Kênh bán hàng | web, mobile, partner | Danh sách cấu hình rõ ràng và value dự phòng `other`. |
| Vùng triển khai | ap-southeast, eu-west | Danh sách vùng triển khai được quản lý. |
| Người dùng/đơn hàng | user ID, order ID | Không dùng làm tag; dùng log hoặc trace để điều tra từng thực thể. |
| Nội dung tự do | email, query, exception message | Không dùng làm tag. Chuẩn hóa thành nhóm lỗi hoặc loại sự kiện hữu hạn. |

### 5.1. Nhóm hóa giá trị có quá nhiều biến thể

Nếu status code có nhiều giá trị nhưng dashboard chỉ cần nhận biết thành công hay lỗi, có thể nhóm theo lớp:

```java
private String statusClass(int status) {
    if (status >= 200 && status < 300) return "2xx";
    if (status >= 300 && status < 400) return "3xx";
    if (status >= 400 && status < 500) return "4xx";
    if (status >= 500 && status < 600) return "5xx";
    return "other";
}
```

Nhóm hóa làm giảm số value từ hàng chục mã status xuống một vài nhóm có ý nghĩa. Nếu cần phân tích từng mã cụ thể, có thể giữ tag status code với tập giá trị hữu hạn đã xác định; hãy chọn theo câu hỏi cần trả lời.

### 5.2. Chuẩn hóa giá trị đầu vào

Với tag kênh bán hàng, có thể chuyển đầu vào tự do thành tập value được phép:

```java
import java.util.Locale;

private String normalizeChannel(String rawChannel) {
    if (rawChannel == null) {
        return "other";
    }

    return switch (rawChannel.trim().toLowerCase(Locale.ROOT)) {
        case "web" -> "web";
        case "mobile" -> "mobile";
        case "partner" -> "partner";
        default -> "other";
    };
}
```

Khi ghi nhận:

```java
registry.counter(
        "shop.orders.created",
        "channel", normalizeChannel(channel)
).increment();
```

Mọi đầu vào ngoài danh sách đều được gộp về `other`, vì vậy tag `channel` chỉ có tối đa bốn giá trị. Việc chuẩn hóa cần được dùng chung ở mọi nơi đăng ký cùng metric để tránh một call site tạo `WEB` trong khi nơi khác tạo `web`.

## 6. Tính ngân sách cardinality trước khi triển khai

Một cách thực tế là lập bảng cho từng metric quan trọng trước khi viết instrumentation:

| Metric name | Tag | Cardinality dự kiến | Ghi chú |
| --- | --- | ---: | --- |
| `shop.orders.created` | channel | 4 | web, mobile, partner, other |
| `shop.orders.created` | result | 3 | success, rejected, error |
| `shop.orders.processing` | channel | 4 | Dùng cùng quy ước channel |
| `shop.orders.processing` | result | 3 | Chỉ dùng nếu timer thực sự phân loại theo kết quả |

Với `shop.orders.created`, giới hạn tổ hợp là 4 × 3 = 12. Với `shop.orders.processing`, nếu dùng hai chiều đó thì cũng tối đa 12. Hai metric name tạo tối đa 24 danh tính meter trong một registry, giả sử mọi tổ hợp đều xuất hiện.

Bạn có thể đặt ngân sách ở nhiều cấp:

- **Mỗi tag:** giới hạn số value riêng lẻ, ví dụ `channel` tối đa 4.
- **Mỗi metric:** giới hạn tích số tổ hợp tag, ví dụ một metric không vượt quá 100 tổ hợp.
- **Mỗi service:** cộng ngân sách của các metric, đồng thời tính các metric tự động do thư viện tạo ra.
- **Toàn backend:** tính thêm số instance, môi trường, histogram bucket và các nhãn do hệ thống scrape bổ sung.

Ngân sách nên dựa trên khả năng lưu trữ và truy vấn của hệ thống giám sát, số instance dự kiến, tần suất scrape và thời gian lưu dữ liệu. Đừng chỉ đặt một ngưỡng cho một tag rồi bỏ qua tích số của tất cả tag còn lại.

## 7. Bảo vệ registry bằng MeterFilter

Chuẩn hóa ở điểm tạo tag là biện pháp chính. Có thể bổ sung `MeterFilter` để giới hạn số giá trị tag được chấp nhận cho các meter khớp một prefix.

Ví dụ cấu hình giới hạn tag `channel` của các metric bắt đầu bằng `shop.orders` tối đa 4 giá trị:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {
    @Bean
    MeterFilter limitOrderChannelValues() {
        return MeterFilter.maximumAllowableTags(
                "shop.orders",
                "channel",
                4,
                MeterFilter.deny()
        );
    }
}
```

Trong cấu hình Spring Boot hỗ trợ `MeterFilter` bean, filter này được áp dụng vào registry do auto-configuration quản lý. Hãy xác nhận phiên bản Micrometer/Spring Boot của dự án và cách registry được tạo trước khi áp dụng.

`maximumAllowableTags` giới hạn số value phân biệt của một tag trên các meter khớp prefix. Khi vượt ngưỡng, filter từ chối đăng ký meter mới phù hợp với điều kiện vượt giới hạn. Đây là lớp bảo vệ để hạn chế phát sinh không kiểm soát; nó không tự chuyển value lạ về `other` và cũng không đảm bảo tổng số tổ hợp của mọi tag nằm dưới một ngân sách cụ thể.

Ví dụ, `channel` có tối đa 4 value nhưng nếu metric còn có `route` 100 value và `result` 5 value, số tổ hợp vẫn có thể đạt 4 × 100 × 5 = 2.000. Hãy kết hợp filter với thiết kế tập value và việc tính ngân sách trước triển khai.

## 8. Kiểm thử số tổ hợp trong SimpleMeterRegistry

`SimpleMeterRegistry` giúp kiểm tra số meter được tạo trong một test mà không cần backend. Ví dụ sau đăng ký ba tổ hợp khác nhau cho cùng một metric:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class TagCardinalityTest {
    @Test
    void createsOneMeterForEachDistinctTagCombination() {
        try (var registry = new SimpleMeterRegistry()) {
            registry.counter("shop.orders.created",
                    "channel", "web", "result", "success");
            registry.counter("shop.orders.created",
                    "channel", "web", "result", "error");
            registry.counter("shop.orders.created",
                    "channel", "mobile", "result", "success");

            assertThat(registry.getMeters()).hasSize(3);
        }
    }
}
```

Test này xác minh mỗi tổ hợp tag khác nhau tạo một meter. Nếu gọi lại `counter()` với cùng tên và cùng tag, registry dùng lại meter hiện có và số lượng meter không tăng.

Có thể kiểm tra filter giới hạn số value bằng test riêng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterTagLimitTest {
    @Test
    void deniesNewChannelValuesAfterLimit() {
        try (var registry = new SimpleMeterRegistry()) {
            registry.config().meterFilter(
                    MeterFilter.maximumAllowableTags(
                            "shop.orders", "channel", 2, MeterFilter.deny()));

            registry.counter("shop.orders.created", "channel", "web");
            registry.counter("shop.orders.created", "channel", "mobile");
            registry.counter("shop.orders.created", "channel", "partner");

            assertThat(registry.getMeters()).hasSize(2);
        }
    }
}
```

Test filter giúp phát hiện thay đổi ngoài dự kiến trong tập value. Hãy kiểm tra hành vi filter theo phiên bản Micrometer mà ứng dụng đang dùng, đặc biệt nếu registry có customizer hoặc filter khác được áp dụng cùng lúc.

Ngoài số lượng meter, nên kiểm tra trực tiếp tập tag được tạo:

- Value có được chuẩn hóa đúng không?
- Có xuất hiện `null`, chuỗi rỗng hoặc biến thể chữ hoa-thường không?
- Có tag ID hoặc dữ liệu tự do bị thêm vào không?
- Khi thêm một chiều mới, tích cardinality có vượt ngân sách không?

## 9. Theo dõi cardinality sau khi triển khai

Ước lượng trước triển khai giúp tránh thiết kế có rủi ro cao, nhưng cần tiếp tục quan sát sau khi chạy production. Tập value có thể thay đổi do cấu hình, route mới, tích hợp đối tác hoặc phiên bản ứng dụng.

Nên theo dõi:

1. Số meter đang được đăng ký theo metric name.
2. Số value phân biệt của từng tag quan trọng.
3. Số tổ hợp tag thực tế so với ngân sách dự kiến.
4. Số chuỗi thời gian của backend theo service, job và instance.
5. Số chuỗi tăng bất thường sau một lần release hoặc thay đổi cấu hình.

Khi cardinality tăng đột ngột, hãy xác định metric name và tag nào đóng góp nhiều tổ hợp nhất. Kiểm tra các giá trị mới có phải route template, exception class, tenant code hay dữ liệu tự do vô tình được gắn vào tag. Sau đó chuẩn hóa hoặc loại bỏ chiều không cần thiết, đồng thời xem lại truy vấn và dashboard phụ thuộc vào tag đó.

Không nên chỉ quan sát tổng số chuỗi thời gian. Tổng có thể tăng do số instance tăng, histogram thay đổi hoặc metric mới được thêm. Cần phân biệt nguồn tăng đến từ số target, số metric name, tổ hợp tag hay số chuỗi được tạo bởi histogram.

## 10. Những sai lầm thường gặp

- **Cộng cardinality thay vì nhân:** với nhiều tag độc lập, số tổ hợp tối đa là tích số value của từng tag.
- **Chỉ giới hạn từng tag:** từng chiều có thể nhỏ nhưng tích số của nhiều chiều vẫn rất lớn.
- **Dùng ID làm tag:** mỗi thực thể mới tạo value mới, khiến cardinality tăng theo dữ liệu nghiệp vụ.
- **Dựa vào tổ hợp hiện tại:** một số tổ hợp chưa xuất hiện hôm nay có thể xuất hiện sau release hoặc thay đổi luồng xử lý.
- **Không chuẩn hóa value:** `web`, `WEB` và `Web` bị tính thành các giá trị khác nhau.
- **Dùng URL đầy đủ làm route:** path variable và query string làm số value tăng theo request.
- **Quên số instance:** một tổ hợp ở nhiều target tạo nhiều chuỗi thời gian ở backend.
- **Đồng nhất meter với time series:** timer histogram có thể xuất nhiều chuỗi cho một meter identity.
- **Dựa hoàn toàn vào MeterFilter:** filter giới hạn value mới nhưng không thay thế thiết kế tag có cardinality thấp và không tự nhóm dữ liệu.

## 11. Checklist trước khi thêm tag

- [ ] Xác định câu hỏi vận hành mà tag mới giúp trả lời.
- [ ] Liệt kê tập value hợp lệ và cardinality tối đa của tag.
- [ ] Chuẩn hóa đầu vào về tập value hữu hạn.
- [ ] Tính tích cardinality của tất cả tag trên metric.
- [ ] Tính thêm số metric name, instance và chi phí histogram khi ước lượng backend.
- [ ] Tránh ID, trace ID, URL động, exception message và dữ liệu tự do.
- [ ] Đặt ngân sách cardinality cho metric và service.
- [ ] Thêm kiểm thử số meter và giá trị tag trong `SimpleMeterRegistry`.
- [ ] Cân nhắc `MeterFilter` làm lớp bảo vệ bổ sung.
- [ ] Theo dõi số chuỗi thời gian sau khi triển khai và sau mỗi release.

Khi tính được cardinality từng tag và tích số tổ hợp, bạn có thể dự đoán chi phí của một thiết kế instrumentation trước khi đưa vào production. Mỗi tag nên đại diện cho một chiều phân tích có ích, có tập value rõ ràng và nằm trong ngân sách số tổ hợp mà hệ thống giám sát có thể vận hành ổn định.
