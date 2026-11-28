# Kiểm tra cardinality trước khi đưa lên production

## 1. Bối cảnh: hệ thống chạy đúng nhưng metrics gây quá tải

Một ứng dụng Spring Boot bán hàng được chia thành các **application module** `orders`, `inventory` và `payments`. Nhóm phát triển dùng Spring Modulith để kiểm chứng module graph, ghi nhận **event publication metrics**, tạo các module-entry observations và xem tracing xuyên qua các module.

Ở môi trường phát triển, nhóm bổ sung tag `order.id` vào counter của sự kiện `OrderPlaced` để tìm số đo theo từng đơn hàng. Mười đơn thử nghiệm hoạt động bình thường. Nhưng khi triển khai thật, hàng trăm nghìn đơn được tạo; mỗi UUID trở thành một giá trị tag mới, mỗi giá trị có thể tạo thêm một **metric time series**. Hệ quả có thể là bộ nhớ JVM tăng, Prometheus ghi nhận nhiều series mới, chi phí lưu trữ lớn và truy vấn dashboard trở nên chậm.

Tình huống này cho thấy: **metric có giá trị đúng không đồng nghĩa thiết kế metric an toàn khi tải tăng**. Trước khi đưa observability lên production, phải kiểm chứng cardinality bằng dữ liệu gần với lưu lượng thật.

Bài **“Kiểm tra cardinality trước khi đưa lên production”** thuộc chương **Cardinality** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Học phần dùng Spring Modulith để sinh tài liệu ranh giới application module, quan sát tương tác qua module graph, Actuator, event metrics, tracing và context propagation. Bài này tập trung vào việc kiểm tra **số lượng chuỗi metric có thể sinh ra** khi bật hoặc thay đổi instrumentation, đặc biệt là metric của các domain event.

Sau bài này, người học có thể:

1. Phân biệt cardinality của một tag, số meter trên một JVM, số series đang hoạt động trên backend và **series churn** theo thời gian.
2. Xác định các tag có tập giá trị hữu hạn trước khi deploy và nhận diện ID/URI động dễ tạo cardinality cao.
3. Lập **ngân sách series** cho từng họ metric, số instance và các label do hạ tầng thêm vào.
4. Kiểm thử cardinality ngay trong Spring-managed `MeterRegistry` và kiểm chứng qua Spring Boot Actuator.
5. Đo số series và số series xuất hiện theo thời gian trên Prometheus hoặc backend tương đương.
6. Sử dụng `MeterFilter` như hàng rào bảo vệ có kiểm soát, không coi việc từ chối meter là sửa xong nguyên nhân.
7. Xây bảng tiêu chí **GO / NO-GO** cùng cách rollback khi phát hiện metric bùng nổ sau deploy.

> **Phạm vi:** Các tên metric, tags và API Spring Modulith dùng theo tài liệu chính thức được tham khảo; các con số tải, ngân sách và số series phía dưới đều là **dữ liệu giả định để luyện cách tính**. Ngưỡng production phải được xác định từ môi trường, kiến trúc backend và ngân sách vận hành cụ thể.

## 2. Bốn khái niệm phải phân biệt

### 2.1. Cardinality của một tag

**Tag cardinality** là số lượng **giá trị phân biệt** có thể xuất hiện dưới cùng một tag key.

| Tag | Tập giá trị ví dụ | Đánh giá |
| --- | --- | --- |
| `module.identifier` | `orders`, `inventory`, `payments` | Thường thấp, gắn với số module |
| `module.event.type` | Các loại event được định nghĩa trong mã | Thường thấp nếu là tập class hữu hạn |
| `sales.channel` | `web`, `mobile`, `pos` | Thấp nếu lấy từ enum cố định |
| `outcome` | `success`, `failure`, `skipped` | Thấp nếu hợp đồng rõ |
| `order.id` | Một UUID khác nhau cho mỗi đơn | Cao, tăng theo nghiệp vụ |
| `user.id` | Một giá trị khác nhau cho mỗi người dùng | Cao, tăng theo số tài khoản |
| `trace.id` | Gần như một giá trị cho mỗi trace | Cao, không dùng làm metric tag |
| `uri` chứa ID | `/orders/1`, `/orders/2`, ... | Cao; cần dùng route template |
| `error.message` | Chuỗi lỗi kèm tham số động | Có thể rất cao và rò rỉ dữ liệu |

**Độ dài chuỗi không quyết định cardinality.** Ba giá trị dài cố định có cardinality thấp; một triệu mã ngắn khác nhau vẫn có cardinality cao. Cũng không nên tự cho rằng tag tên `region`, `partner` hoặc `status` luôn hữu hạn: phải xem dữ liệu phát sinh thật và cách nhóm giá trị.

### 2.2. Meter identity và số series ở một registry

Micrometer nhận diện meter dựa trên **tên** và tập **tags**; đối với cùng tên metric, hai tổ hợp tag-value khác nhau thường có `Meter.Id` khác nhau.

Ví dụ khái niệm:

```text
module.events.published.orders.OrderPlaced{
  module.identifier="orders", sales.channel="web"
}

module.events.published.orders.OrderPlaced{
  module.identifier="orders", sales.channel="pos"
}
```

Hai bản ghi này biểu diễn **hai series**, dù cùng một counter name. Nếu thêm `order.id` với UUID riêng cho từng đơn, số identity có thể tăng theo số đơn.

Trên JVM, `MeterRegistry.getMeters()` cho phép kiểm tra các meter đã đăng ký. Đây là một phép kiểm tra **tại instance hiện tại**; nó chưa tính nhãn do Prometheus thêm, các instance khác, số series lưu trong backend hoặc tác động của histogram buckets.

### 2.3. Active series và series xuất hiện trong khoảng thời gian

- **Active series tại một thời điểm:** Các bộ tên metric + label set đang có mẫu hiện hành trên backend.
- **Distinct series trong một khoảng thời gian:** Các bộ label set từng xuất hiện trong một cửa sổ như 24 giờ.
- **Series churn:** Tốc độ tạo series mới hoặc series biến mất theo thời gian, ví dụ khi container bị thay thế liên tục hoặc có ID runtime trong labels.

Một biểu đồ chỉ cho biết **500 series đang hoạt động** có thể che giấu việc **50.000 series khác nhau đã xuất hiện trong ngày**. Churn làm tăng chi phí index, compaction và lưu trữ, ngay cả khi số series đồng thời không quá lớn.

### 2.4. Số series có thể khác số meter trong JVM

Prometheus và các backend tương tự có thể tạo thêm label `job`, `instance`, `cluster`, `namespace`, `pod`, `environment`. Mỗi tổ hợp khác nhau được lưu thành một series. Ngoài ra:

- Một counter có thể có hậu tố `_total` khi xuất qua Prometheus.
- Một timer hoặc histogram có thể xuất **nhiều chuỗi** cho count, sum và các bucket khác nhau.
- Phân phối percentiles hoặc SLO buckets có thể làm số series tăng theo số bucket và tag set.
- Một ứng dụng nhiều instance cùng xuất một meter name sẽ tạo các series riêng theo instance/target.

Vì thế, **không dùng duy nhất số meter trong `MeterRegistry` để kết luận tổng cardinality ở backend**.

## 3. Ước tính series trước khi đo: mô hình và giới hạn

### 3.1. Công thức giới hạn trên để lập ngân sách

Với một **metric family**, giả sử các tag có lần lượt `c1, c2, ..., ck` giá trị, và có `N` instance:

\[
S_{\text{upper}} \le N \times \prod_{i=1}^{k} c_i
\]

Trong công thức này, `S_upper` là số tổ hợp tối đa đơn giản khi xem các chiều phân loại độc lập. Với histogram, còn phải nhân/điều chỉnh theo số chuỗi được exporter tạo cho một tổ hợp nhãn.

**Không xem công thức là số series đo được.** Ví dụ `module.identifier` và `module.name` có quan hệ một–một; 6 modules thường chỉ tạo 6 cặp identifier–name, không phải 36. Một loại domain event cũng thường thuộc một module nhất định; không phải mọi cặp module × event type đều tồn tại.

### 3.2. Ví dụ tính cho counter tổng hợp

Giả sử ứng dụng có 4 modules, mỗi module công bố 3 loại event riêng, chạy 6 instances và được gắn 2 environment labels. Counter tổng hợp `module.events.published` mặc định phân loại theo `module.identifier`, `module.name` và `module.event.type`.

Có thể tính **giới hạn trên thô**:

\[
4 \times 4 \times 12 \times 6 \times 2 = 2\,304
\]

Nhưng điều kiện thực tế nói rằng mỗi identifier khớp đúng một display name, mỗi event type thuộc đúng một module. Do đó, nếu 12 cặp module–event đều xuất hiện ở từng instance và hai environment, một ước lượng sát hơn là:

\[
12 \times 6 \times 2 = 144\ \text{series}
\]

Con số 144 vẫn là **giả định**: một số event chưa được phát nên meter chưa có, hoặc exporter thêm labels khác. Phải kiểm tra runtime để biết số chính xác.

### 3.3. Ví dụ bùng nổ khi thêm tag không kiểm soát

Giả sử counter riêng `module.events.published.orders.OrderPlaced` có `sales.channel` với ba giá trị, chạy 6 instances. Khi đó có tối đa khoảng:

\[
3 \times 6 = 18\ \text{series}
\]

Nếu lập trình viên thêm `order.id` với 50.000 UUID xuất hiện trong một khoảng, mỗi UUID gắn với một channel và mỗi event chỉ được xuất từ một instance, số series của họ counter riêng có thể tiến gần **50.000**, dù không phải `50.000 × 3 × 6` theo cách nhân độc lập.

Điều này minh họa hai bài học:

- **Series thực tế là các tổ hợp đã xảy ra**, có tương quan giữa các tag.
- **Một tag mang ID duy nhất có thể chi phối toàn bộ cardinality**, ngay cả khi mọi tag còn lại đều thấp.

### 3.4. Đừng quên histogram

Ví dụ một module-entry observation được metrics handler biến thành timer. Nếu cùng một meter name/tag set có `B` bucket được xuất, backend có thể lưu gần `B` series bucket **cộng** count và sum (tùy loại histogram và exporter).

Vì vậy, tăng số labels trên một timer có histogram có thể tốn kém hơn tăng số labels trên một counter đơn. Khi lập budget, cần kiểm tra các cấu hình như `management.metrics.distribution.percentiles-histogram`, SLO và distribution statistics hiện hành, theo đúng phiên bản Spring Boot.

## 4. Spring Modulith event metrics: đúng loại counter và đúng tập tags

### 4.1. Hai họ counter

Spring Modulith ghi nhận domain event publications bằng hai họ:

| Tên Micrometer | Vai trò | Low-cardinality tags mặc định |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp tất cả các lần công bố event được instrument | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.<moduleIdentifier>.<simpleEventTypeName>` | Counter riêng từng loại event theo module | `module.identifier`, `module.name` |

Ví dụ một event `OrderPlaced` từ module `orders` có thể tạo counter riêng tên:

```text
module.events.published.orders.OrderPlaced
```

Chú ý sự khác biệt: **`module.event.type` thuộc tập tags mặc định của counter tổng hợp**, không thuộc tập tags mặc định được tài liệu liệt kê cho counter riêng. Counter riêng đã thể hiện event type trong metric name.

**Không cộng count của hai họ để tính tổng event**, vì cùng một lần publish có thể được ghi nhận trong cả hai.

### 4.2. Tag mặc định phù hợp vì sao?

- `module.identifier` là technical identifier của module, thường thuộc tập module đã xác định trong architecture model.
- `module.name` là tên hiển thị module, thường tương quan với identifier.
- `module.event.type` phân loại các event class/hợp đồng được mã nguồn định nghĩa.

Ba tag này **thường có cardinality thấp** nếu metadata module và tập event types được quản lý ổn định. Nếu custom logic tự gán tên event/module động theo request thì cần kiểm tra lại; chỉ tên tag không bảo đảm giá trị an toàn.

### 4.3. `ModulithEventMetricsCustomizer` là vị trí dễ thêm tag rủi ro

Spring Modulith hỗ trợ `ModulithEventMetricsCustomizer` để gắn tags vào **counter riêng theo loại event**. Ví dụ một customizer đọc `OrderPlaced.channel()` từ enum là hợp lý; nhưng đọc `OrderPlaced.orderId()` rồi gắn `order.id` là sai về cardinality.

Đừng nhầm customizer này với `ModulithObservationConvention`. Convention liên quan đến observation của điểm vào module; event metrics customizer liên quan đến counter công bố event. Một tag trên module-entry span **không tự động là tag của event publication counter**.

### 4.4. Traces chứa ID nhưng metrics không nên chứa ID

Traces được lấy mẫu dùng để lần theo **một** luồng xử lý và có thể mang metadata chi tiết theo chính sách bảo mật. Metrics là số đo tổng hợp trên **nhiều** lần xử lý.

Không gắn `orderId`, `customerEmail`, `userId` hay `traceId` vào tags của event counter chỉ để tra một request. Cần dùng trace/log correlation và hệ thống nghiệp vụ cho mục đích đó, đồng thời tránh đưa bí mật/PII vào bất kỳ tín hiệu nào.

## 5. Trước khi deploy: tạo hợp đồng tags

### 5.1. Mỗi metric cần có bản mô tả sở hữu và mục đích

Không bắt đầu bằng cách thêm hàng loạt tag rồi mới xem có ích không. Với mỗi họ metric quan trọng, ghi trước:

| Trường trong hợp đồng | Ví dụ |
| --- | --- |
| Metric family | `module.events.published` |
| Mục đích | Phân tích tốc độ publish theo module và event type |
| Đơn vị đo | Số lần công bố event |
| Owners | Nhóm ứng dụng và nhóm vận hành |
| Tag keys cho phép | `module.identifier`, `module.name`, `module.event.type` |
| Nguồn values | Spring Modulith application-module model và loại event |
| Giới hạn values | Số module/event classes có kiểm soát |
| Tags bị cấm | `order.id`, `user.id`, `trace.id`, payload, email |
| Kết quả listener | **Không đo bởi counter publication** |
| Query mẫu | Tốc độ publish theo `module.identifier` |
| Ngưỡng budget | Xác định từ baseline và mức tăng cho phép |

Với counter riêng của `OrderPlaced`, hợp đồng có thể thêm `sales.channel∈{web,mobile,pos}` và yêu cầu không có UUID làm tag.

### 5.2. Dùng bảng phân loại tag trước khi mở rộng

| Đề xuất | Kết luận ban đầu | Điều kiện |
| --- | --- | --- |
| `module.identifier` | Chấp nhận | Dùng giá trị từ metadata Modulith |
| `module.event.type` | Chấp nhận cho counter tổng hợp | Event type đến từ tập class/hợp đồng hữu hạn |
| `sales.channel` | Có thể chấp nhận | Giá trị được kiểm soát bằng enum/allowlist |
| `result` | Có thể chấp nhận | Định nghĩa rõ success/failure tại đúng thời điểm đo |
| `region` | Có thể chấp nhận | Tập giá trị được kiểm soát, tính vào budget |
| `partner.id` | Cần đánh giá | Số partner có thể tăng nhanh theo business |
| `order.id` | Từ chối | Một giá trị mới cho từng đơn |
| `error.message` | Từ chối | Chuỗi động, dễ chứa dữ liệu nhạy cảm |
| `uri` dạng `/orders/123` | Từ chối | Dùng template `/orders/{id}` ở tầng web instrumentation |
| `pod.uid` | Không dùng làm business metric tag | Dùng labels hạ tầng ở tầng scrape nếu cần |

Một enum hôm nay có 3 giá trị có thể tăng lên 30 trong vài năm. Vì vậy, hợp đồng phải được rà soát khi thêm enum value, module mới hoặc loại domain event mới.

### 5.3. Với mỗi tag, trả lời bảy câu hỏi

1. Tag giúp giải đáp **câu hỏi vận hành** nào?
2. Tập giá trị tối đa trong 6–12 tháng tới có thể ước lượng không?
3. Giá trị đến từ enum/metadata hay text tự do/ID?
4. Tag có trùng chiều phân loại đã tồn tại không?
5. Tag được gắn vào **counter nào** và có cần gắn vào tất cả event types không?
6. Prometheus/backend có thêm labels nào khiến số tổ hợp lớn hơn?
7. Nếu bỏ tag này để giảm series, dashboard/alert nào bị ảnh hưởng?

Nếu không có mục đích rõ hoặc không thể kiểm soát tập giá trị, **không đưa tag vào metric**.

## 6. Đặt budget và tiêu chí GO / NO-GO

### 6.1. Các loại ngân sách nên có

Budget không phải một con số áp cho mọi hệ thống. Có thể xác định theo các lớp:

| Budget | Đơn vị | Điều cần đo |
| --- | --- | --- |
| Per-tag cardinality | Số giá trị phân biệt | Ví dụ tối đa 3 sales channels |
| Per-meter-family | Số series đang hoạt động | Ví dụ cho counter riêng `OrderPlaced` |
| Per-service | Tổng active series | Toàn bộ metric do service xuất |
| Series churn | Series mới trong 1 giờ/24 giờ | Tác động của IDs, restart và pods |
| Ingestion | Samples/giây hoặc bytes/ngày | Chi phí scrape/lưu trữ |
| Query latency | Thời gian chạy dashboard/alert | Khả năng truy vấn sau thay đổi |

**Ví dụ budget minh họa:** Trước thay đổi, staging ở quy mô tương đương có 5.000 active series cho service; thay đổi customizer được phép tăng không quá 150 active series trong tải chuẩn, và không tạo hơn 10% churn mới so với baseline ở cùng khoảng đo. Đây **không phải ngưỡng khuyến nghị phổ quát**. Tổ chức cần chọn số riêng theo tải, retention, giá backend, mục tiêu SLO và headroom.

### 6.2. Ghi baseline có thể so sánh

Trước khi triển khai build mới, ghi lại:

- Commit/build version, cấu hình instrumentation, exporter và scrape interval.
- Số instances/pods, môi trường, các labels hạ tầng và lưu lượng.
- Active series theo service và theo từng metric family.
- Distinct series từng xuất hiện trong 1 giờ/24 giờ, nếu backend hỗ trợ.
- Số samples nhập vào, dung lượng hoặc chi phí liên quan.
- Thời gian chạy query/dashboard quan trọng.
- Dữ liệu từ một cửa sổ tải đại diện, không chỉ khi hệ thống nhàn rỗi.

**So sánh cùng điều kiện.** Nếu số instance tăng gấp đôi, tổng series tăng thường là điều dự kiến. Muốn đánh giá riêng thay đổi code, chuẩn hóa theo số instance, cùng loại tải và cùng cấu hình scrape.

### 6.3. Điều kiện NO-GO

Một thay đổi cần bị chặn trước production nếu xuất hiện một trong các bằng chứng:

- Có ID người dùng, đơn hàng, token, timestamp hoặc raw URL trong metric tags.
- Series count vượt budget đã thống nhất trong tải kiểm thử.
- Tốc độ tạo series mới tăng liên tục không có giới hạn giải thích được.
- MeterFilter phải từ chối những giá trị tag hợp lệ của nghiệp vụ.
- Dashboard có sai nghĩa phép đếm hoặc cộng hai họ event counter.
- Không có cách đo/kiểm chứng trên registry hoặc backend phù hợp.
- Không có người chịu trách nhiệm với labels và kế hoạch quan sát/rollback.

Việc vượt budget cần gắn với **thước đo cụ thể**, không chỉ câu nhận xét “có vẻ nhiều labels”.

## 7. Ví dụ customizer an toàn cho `OrderPlaced`

### 7.1. Domain event và kênh hữu hạn

Ví dụ module `orders`:

```java
package com.example.shop.orders;

import java.util.UUID;

public enum SalesChannel {
    WEB, MOBILE, POS
}
```

```java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId, SalesChannel channel) {
}
```

`orderId` vẫn tồn tại trong payload để nghiệp vụ nhận biết đơn hàng; nó **không được đưa vào meter tags**. `SalesChannel` chỉ có ba giá trị.

### 7.2. Đăng ký `ModulithEventMetricsCustomizer`

Khi khai báo bean dùng API compile-time của Spring Modulith, ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dự án phải có Spring Boot plugin/BOM và Spring Modulith BOM tương thích; không tự trộn phiên bản từ nhiều dòng khác nhau. Nếu dùng Actuator HTTP hoặc Prometheus, cần thêm dependency web/registry theo yêu cầu ứng dụng.

Bean:

```java
package com.example.shop.orders;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
class OrderEventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, builder) -> builder.tag(
                "sales.channel",
                event.channel().name().toLowerCase(Locale.ROOT)
            )
        );
    }
}
```

Trong trường hợp này, `sales.channel` chỉ lấy từ tập `web/mobile/pos`. Không cần thêm tag `module.identifier` hoặc `module.name` một lần nữa, vì Spring Modulith cung cấp các tags module mặc định cho counter riêng.

**Đặc biệt:** Callback `Counter.Builder.tag(...)` **không tự biết** một giá trị là high-cardinality. Nếu thay `event.channel()` bằng `event.orderId()`, ứng dụng có thể tạo rất nhiều meter identities. Cần kiểm tra code review và test, không chỉ tin vào chữ “customizer”.

### 7.3. Đặt quy tắc xử lý dữ liệu bất thường

Ví dụ `event.channel() == null` làm `name()` ném exception. Đừng âm thầm chuyển mọi input không hợp lệ thành một chuỗi chứa chi tiết động. Chọn một trong các chính sách có chủ đích:

- Từ chối event không hợp lệ **trước khi publish**.
- Nếu nghiệp vụ cho phép, chuẩn hóa sang **một** enum/bucket `UNKNOWN`.
- Ghi số lần dữ liệu không hợp lệ bằng một counter có **tag hữu hạn**, và ghi chi tiết ở log bảo mật.

Không để customizer trở thành nơi phát sinh hàng triệu tag values bất ngờ.

## 8. Kiểm tra trước deploy ngay trong `MeterRegistry`

### 8.1. Vì sao kiểm tra registry?

Đây là lớp gần nguồn đo nhất: bạn có thể nhìn thấy **`Meter.Id` thực sự được đăng ký** trước khi qua Actuator, Prometheus hay dashboard.

Một kiểm thử tích hợp nên:

1. Khởi động Spring Boot application context với instrumentation thật.
2. Inject **chính `MeterRegistry`** đang được Spring-managed.
3. Phát một tập event đại diện, gồm UUID khác nhau nhưng channel trùng nhau.
4. Đọc tất cả meter thuộc họ tên mục tiêu.
5. Assert không có tag bị cấm và chỉ có channel cho phép.
6. Đo số meter identities khác nhau sau khi chạy, so với budget theo một instance.

Không tạo một `SimpleMeterRegistry` rời rồi tự increment counter để kết luận Spring Modulith customizer hoạt động. Test như vậy chỉ chứng minh cú pháp Micrometer.

### 8.2. Ví dụ service phát event thật

```java
package com.example.shop.orders;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void place(UUID id, SalesChannel channel) {
        // Giả sử các ràng buộc nghiệp vụ đã được xác minh.
        events.publishEvent(new OrderPlaced(id, channel));
    }
}
```

Ở code ứng dụng thật, nghiệp vụ có thể cần transaction, lưu trữ và idempotency; các vấn đề đó không phải mục tiêu của kiểm thử cardinality này.

### 8.3. Test kiểm tra bộ giá trị và ID không được phép

Ví dụ JUnit 5, Spring Boot và AssertJ:

```java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

import com.example.shop.orders.OrderService;
import com.example.shop.orders.SalesChannel;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
    classes = ShopApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class EventCardinalityIntegrationTests {

    private static final String EVENT_METER =
        "module.events.published.orders.OrderPlaced";

    @Autowired
    OrderService orders;

    @Autowired
    MeterRegistry registry;

    @Test
    void eventCounterUsesOnlyBoundedTagValues() {
        for (int i = 0; i < 20; i++) {
            SalesChannel channel = SalesChannel.values()[i % 3];
            orders.place(UUID.randomUUID(), channel);
        }

        var meters = registry.getMeters().stream()
            .filter(m -> m.getId().getName().equals(EVENT_METER))
            .toList();

        assertThat(meters).isNotEmpty();

        Set<String> channels = meters.stream()
            .map(m -> m.getId().getTag("sales.channel"))
            .collect(Collectors.toSet());

        assertThat(channels)
            .isSubsetOf("web", "mobile", "pos")
            .contains("web", "mobile", "pos");

        assertThat(meters).allSatisfy(meter -> {
            Meter.Id id = meter.getId();

            assertThat(id.getTag("module.identifier"))
                .isEqualTo("orders");

            assertThat(id.getTag("sales.channel"))
                .isNotNull();

            assertThat(id.getTag("order.id")).isNull();
            assertThat(id.getTag("user.id")).isNull();
            assertThat(id.getTag("trace.id")).isNull();
            assertThat(id.getTag("customer.email")).isNull();
        });

        // Với một module nguồn và 3 kênh hữu hạn,
        // fixture này không được tạo series mới theo UUID.
        assertThat(meters.size()).isLessThanOrEqualTo(3);
    }
}
```

**Giới hạn của test:**

- Mã minh họa giả định technical module identifier là `orders` và tên counter riêng có đúng dạng trên. Nếu dự án thay cách nhận diện module, phải lấy tên thật từ registry và cập nhật hợp đồng test.
- Dự án có common tags khác vẫn có thể làm xuất hiện thêm meter identities tùy cấu hình; vì vậy giới hạn `≤3` áp dụng cho **fixture một context/instance với bộ tag đã mô tả**. Nếu có code khác thêm tag tự do, test phải thất bại để nhóm điều tra.
- Test khẳng định cardinality **trên một JVM và tập event thử**, chưa thay thế phép đo staging/prod nhiều instance.
- Để tránh biến động, không chạy song song các tác vụ khác cùng gia tăng những meter đang kiểm thử.
- Test này cần được **thực thi trong dự án thật** để xác minh; ví dụ trong tài liệu chưa phải kết quả test đã chạy.

### 8.4. Kiểm tra delta count để không nhầm lỗi cardinality với lỗi đo event

Có thể bổ sung test đo số publish cho counter riêng:

```java
@Test
void aPublishedEventIncrementsExistingChannelSeries() {
    String name = "module.events.published.orders.OrderPlaced";

    var before = registry.find(name)
        .tags("sales.channel", "web")
        .counter();

    double beforeCount = before == null ? 0.0 : before.count();

    orders.place(UUID.randomUUID(), SalesChannel.WEB);

    var after = registry.find(name)
        .tags("sales.channel", "web")
        .counter();

    assertThat(after).isNotNull();
    assertThat(after.count()).isEqualTo(beforeCount + 1.0);
}
```

`registry.find(...)` **không tự tạo meter**, phù hợp để xác minh instrumentation. Không dùng `registry.counter(...)` trong assertion vì hàm đó có thể tạo counter mới và làm test dương tính giả.

Số **series** và số **event publications** là hai đại lượng khác nhau: 1.000 event `WEB` có thể làm một counter tăng 1.000 lần mà không tạo thêm 1.000 series.

### 8.5. Kiểm tra mọi họ metric quan trọng

Chỉ kiểm tra `OrderPlaced` là chưa đủ nếu service còn có:

- HTTP request timers và route tags.
- JDBC/query/client instrumentation.
- Module-entry timers/observations.
- Các event type khác với customizer khác.
- JVM, executor, cache metrics.
- Histogram, SLO buckets hoặc percentiles.
- Common tags trên mọi meter.

Nên có ít nhất một báo cáo **toàn registry** theo metric prefix và số distinct `Meter.Id` cho từng family, kết hợp ngưỡng riêng cho từng nhóm. Đừng suy ra “service đã an toàn” chỉ từ một test event counter.

## 9. Actuator: xác minh tên meter và tag values của bản chạy

### 9.1. Cấu hình endpoint thử nghiệm

Với Spring Boot Actuator và hỗ trợ Modulith phù hợp, ví dụ cấu hình dành cho staging:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,modulith,prometheus"
```

`prometheus` chỉ có khi có registry tương ứng; `modulith` chỉ có khi hỗ trợ Modulith Actuator được đăng ký. **Exposure không đồng nghĩa quyền truy cập**: phải áp dụng xác thực, phân quyền và giới hạn mạng quản trị thích hợp.

### 9.2. Kiểm tra meter đã đăng ký

Gọi:

```bash
curl -i http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/module.events.published
curl -s http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced
```

Response Metrics endpoint có cấu trúc:

```json
{
  "name": "module.events.published.orders.OrderPlaced",
  "measurements": [
    { "statistic": "COUNT", "value": 20.0 }
  ],
  "availableTags": [
    { "tag": "module.identifier", "values": ["orders"] },
    { "tag": "module.name", "values": ["Orders"] },
    { "tag": "sales.channel", "values": ["web", "mobile", "pos"] }
  ]
}
```

Đây là **JSON giả định**, không phải output đã thu được. Trong môi trường thật, tên và values chính xác cần đọc từ runtime; metrics có thể chưa xuất hiện trước khi event được phát.

### 9.3. Đọc tập giá trị bằng `jq`

```bash
curl -s http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced \
  | jq -r '.availableTags[] | "\(.tag): \(.values | join(", "))"'
```

Khi thấy `sales.channel` có thêm `"new-partner-478"` hoặc một UUID, phải chặn việc phát triển khai cho đến khi xác định nguồn tag.

Có thể lọc theo tag:

```bash
curl -s "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced?tag=sales.channel:web"
```

**Lưu ý:** `availableTags` cho một response **đã lọc** có thể không liệt kê chính tag đã dùng làm filter. Để kiểm tra **toàn bộ giá trị của tag**, xem response **không lọc**.

### 9.4. Giới hạn của endpoint metrics

`/actuator/metrics` hữu ích để đọc metric names, giá trị hiện có và một số tag values **trên instance đang gọi**, nhưng chưa đủ để trả lời:

- Trong 24 giờ qua có bao nhiêu distinct series đã từng được xuất?
- Có bao nhiêu instance cùng phát một metric family?
- Scrape target có thêm các labels nào?
- Những histogram buckets nào xuất hiện?
- Chi phí ingestion/storage của toàn backend tăng bao nhiêu?

Các câu hỏi đó cần xem dữ liệu của exporter và monitoring backend.

## 10. Kiểm tra trên Prometheus hoặc backend monitoring

### 10.1. Xác minh tên và labels thật

Khi dùng Prometheus registry:

```groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Đảm bảo endpoint `prometheus` đã expose và được bảo vệ:

```bash
curl -s http://localhost:8080/actuator/prometheus
```

Prometheus có naming convention; ví dụ `module.events.published` có thể xuất dưới tên `module_events_published_total` và các tag keys có dấu chấm thường được chuẩn hóa thành dấu gạch dưới.

**Không coi tên dưới đây là mặc định bất biến.** Hãy tìm **tên xuất thực tế** trong endpoint và cập nhật PromQL theo dữ liệu đang chạy.

### 10.2. Đếm active series theo metric name

Giả sử exporter thực sự công bố `module_events_published_total`:

```promql
count(module_events_published_total)
```

Truy vấn trả về **số series tại thời điểm đánh giá** cho metric name đó, trên các targets mà Prometheus đang thu thập.

Để thấy mỗi service/instance đóng góp bao nhiêu series, nếu có các labels `job` và `instance`:

```promql
count by (job, instance) (module_events_published_total)
```

Để đếm toàn bộ metric names bắt đầu bằng prefix liên quan đến event publication, trong một môi trường cho phép query theo `__name__`:

```promql
count by (__name__) ({__name__=~"module_events_published.*"})
```

Biểu thức thứ ba **có thể tốn kém** nếu số metric family lớn. Dùng trên staging hoặc phạm vi job cụ thể trước, không để một truy vấn rộng làm quá tải backend.

### 10.3. Đếm số series theo giá trị tag

Giả sử counter riêng được xuất với tên `module_events_published_orders_OrderPlaced_total` và label `sales_channel`, có thể hỏi: mỗi kênh có bao nhiêu series đang hoạt động?

```promql
count by (sales_channel) (
  module_events_published_orders_OrderPlaced_total
)
```

Kết quả “web: 6, mobile: 6, pos: 6” có thể nghĩa là **mỗi kênh xuất hiện trên 6 instance**. Nó **không** có nghĩa đã công bố 6 đơn hàng ở từng kênh; đây là phép đếm **series**, không phải phép đếm **event**.

Nếu cần tốc độ sự kiện, dùng `rate(...)` hoặc `increase(...)` trên **counter**:

```promql
sum by (sales_channel) (
  rate(module_events_published_orders_OrderPlaced_total[5m])
)
```

Phải luôn phân biệt:

- `count(metric)` → số **series** đang có.
- `sum(metric)` → tổng **giá trị counter hiện tại**, dễ sai khi instance restart.
- `sum(rate(metric[5m]))` → tốc độ **sự kiện/giây**, có xét counter resets.

### 10.4. Kiểm tra churn qua một cửa sổ thời gian

Với PromQL, một phép **xấp xỉ số distinct series đã có samples trong 24 giờ** là:

```promql
count(
  count_over_time(module_events_published_total[24h])
)
```

`count_over_time` trả một kết quả cho từng label set có sample trong cửa sổ, rồi `count(...)` đếm số label sets đó. So sánh với `count(module_events_published_total)` hiện tại có thể giúp phát hiện có nhiều series chỉ sống trong thời gian ngắn.

**Hạn chế:** Query có thể tốn tài nguyên và không đo chính xác tốc độ tạo/chấm dứt series. Retention, scrape gaps, stale series, remote write và các lựa chọn backend có thể khiến kết quả khác nhau. Khi có số liệu quản trị chuyên dụng như TSDB head series, series creation/removal hoặc ingestion metrics, ưu tiên đối chiếu thêm các chỉ số đó.

### 10.5. Đối chiếu với labels do hạ tầng bổ sung

Trong một cluster, Prometheus có thể thêm `namespace`, `pod`, `instance` hoặc `cluster`. Vì vậy:

1. Ghi số series ở một instance qua registry.
2. Ghi số series của **cùng metric** ở exporter.
3. Đếm số series trên toàn backend, có lọc đúng job/cluster.
4. So sánh với số instances và cấu hình relabeling.
5. Kiểm tra một service có bị scrape **hai lần** hay không.
6. Kiểm tra một label thay đổi theo restart có đang tạo churn cao hay không.

Nếu test trên một local JVM thấy 3 series nhưng trên 100 instances thấy 300 series, đó có thể là nhân hệ số **đúng kỳ vọng**. Nếu thấy 30.000 series, cần tìm label/tổ hợp ngoài dự kiến.

## 11. Đo tải trên staging để kết luận cardinality

### 11.1. Một lần gọi HTTP không đại diện cho production

Muốn kiểm tra trước deploy, staging cần chạy kịch bản tạo đủ các **nhánh sinh giá trị tag**:

- Các module/loại event quan trọng.
- Tất cả `sales.channel` và `outcome` hợp lệ.
- Request bình thường, lỗi validation, retry và batch.
- Listener đồng bộ/bất đồng bộ nếu có.
- Các trường hợp có/không có payload tùy chọn.
- Tải nhiều instance và vòng đời pod restart/rollout.
- Điều kiện traffic peak có thể mô phỏng an toàn.

Mục tiêu của bài test cardinality không chỉ là số request cao; nó là **phủ các cách tạo label values** có thể xuất hiện trong production.

### 11.2. Kịch bản thử nghiệm đề xuất

Giả sử có 6 instances, ba sales channels, và 10.000 order IDs **khác nhau** trong dữ liệu thử:

| Pha | Tải mô phỏng | Điều cần quan sát |
| --- | --- | --- |
| Baseline | Bản code chưa thêm custom tag, cùng số instances | Series hiện hành và churn |
| Warm-up | Kích hoạt từng event type một lần | Meter names/tags nào xuất hiện |
| Phân loại | Phát đơn thuộc cả ba channels | Số series tăng theo enum, không theo UUID |
| Unique IDs | Tạo nhiều order IDs khác nhau | Số series **không tỷ lệ với số UUID** |
| Burst | Tăng tốc độ event publish | Counter tăng, số unique series tương đối ổn định |
| Error/retry | Thử những nhánh hợp lệ và lỗi | Không phát sinh dynamic error tags |
| Rollout | Restart/thay thế instances có kiểm soát | Churn do labels hạ tầng |
| So sánh | Đối chiếu build cũ/mới | Kết quả so với series budget |

Sau mỗi pha, ghi ảnh chụp cả **JVM registry**, **Actuator**, **Prometheus** và backend nếu có. Những phép đo này phải cùng một khoảng thời gian và cùng tập instances để tránh nhầm lẫn.

### 11.3. Khi có nhiều kênh nhưng không phải mọi tổ hợp xuất hiện

Giả sử một event chỉ xuất hiện từ module `orders` và chỉ gắn `sales.channel` với ba values. Đừng nhân số module toàn hệ thống vào metric đó để báo “rủi ro” mà không phân tích quan hệ thực tế.

Ngược lại, nếu thêm một tag `partner` có 5.000 values chỉ trên `OrderPlaced`, cardinality của **chính counter riêng này** vẫn có thể tăng mạnh dù các module khác không dùng tag đó. Phải đánh giá **từng metric family** rồi mới tổng hợp cho service.

### 11.4. Kết quả cần ghi bằng bảng

| Chỉ số | Trước deploy | Staging build mới | Budget | Đánh giá |
| --- | ---: | ---: | ---: | --- |
| Active series `OrderPlaced` trên toàn cluster | 18 | 18 | ≤ 24 | PASS |
| Distinct `sales.channel` values | 3 | 3 | = 3 | PASS |
| Series mới khi tăng từ 100 đến 10.000 UUID | 0 | 0 | = 0 do UUID | PASS |
| Active series toàn service | 5.000 | 5.120 | ≤ 5.150 | PASS |
| Distinct series trong 24h | 6.000 | 8.500 | ≤ 7.500 | FAIL |
| Ingestion samples/giây | 12.000 | 14.000 | ≤ 15.000 | PASS |

Số liệu trong bảng hoàn toàn **giả định**. Dù active series có thể chấp nhận được, kết quả **distinct series 24h vượt budget** là lý do **NO-GO** để điều tra churn; không nên chỉ nhìn vào một chỉ số đang đạt.

## 12. Đặt hàng rào bảo vệ bằng Micrometer `MeterFilter`

### 12.1. Tính năng và phạm vi

Micrometer cung cấp `MeterFilter.maximumAllowableTags(...)` để giới hạn số **giá trị khác nhau của một tag** trên nhóm meter có name prefix phù hợp. Khi ngưỡng bị vượt, một `MeterFilter` khác có thể được áp dụng để từ chối meter.

Ví dụ trong ứng dụng:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricCardinalityGuard {

    @Bean
    MeterFilter limitSalesChannel() {
        return MeterFilter.maximumAllowableTags(
            "module.events.published.orders.OrderPlaced",
            "sales.channel",
            3,
            MeterFilter.deny()
        );
    }
}
```

Khi dùng bean filter trong Spring Boot, xác nhận nó được gắn vào **Spring-managed MeterRegistry** thực sự dùng để xuất metrics. Trường hợp tạo registry rời trong code sẽ không tự được bảo vệ bởi bean này.

### 12.2. Vì sao filter chỉ là phương án cuối?

Giả sử code tạo tag `sales.channel=partner-504`; khi vượt giới hạn, filter có thể từ chối meter đó, khiến **dữ liệu bị mất khỏi metrics**. Hành vi này bảo vệ tài nguyên nhưng không sửa sai nguồn tag.

Một bộ lọc như vậy cần đi kèm:

1. Chuẩn hóa `sales.channel` về enum hợp lệ ngay khi nhận event.
2. Cảnh báo khi giá trị bị từ chối hoặc meter bị drop, nếu cơ chế có thể quan sát.
3. Test với tập giá trị được phép và giá trị ngoài hợp đồng.
4. Document hậu quả khi xuất hiện channel mới.
5. Không đặt giới hạn cứng thấp hơn tập giá trị nghiệp vụ hợp lệ.
6. Đánh giá `maximumAllowableMetrics(...)` nếu cần giới hạn tổng meter registrations; đây cũng là cách từ chối dữ liệu, phải cân nhắc kỹ.

Filter có thể thay đổi hoặc từ chối meter **ở thời điểm đăng ký**, không có nghĩa nó xóa toàn bộ các series đã được backend thu trước đó.

### 12.3. Tự động xóa một tag gây hại cũng có chi phí ngữ nghĩa

`MeterFilter.ignoreTags(...)` hoặc một phép biến đổi Meter.Id có thể bỏ tag. Điều đó đôi khi giảm cardinality, nhưng cũng có thể gộp những series vốn khác nhau thành một identity hoặc làm dashboard không còn phân biệt đúng dữ liệu.

Để an toàn, hãy sửa **nguồn sinh tag**, xác định lại câu hỏi vận hành và cập nhật truy vấn trước khi dùng filter biến đổi diện rộng. Không lặng lẽ gộp các counters có ý nghĩa khác nhau.

## 13. Kiểm tra các nguồn cardinality ngoài event metrics

### 13.1. HTTP server metrics

HTTP instrumentations thường phân loại theo **route template** thay vì raw URI có ID. Ví dụ:

```text
Tốt:  uri=/orders/{id}
Xấu:  uri=/orders/6caef2a1-...
```

Nếu ứng dụng gắn raw URL, query parameters hoặc path không chuẩn vào metric tags, số series có thể tăng theo từng request. Khi đổi interceptor hoặc observation convention, kiểm tra những tag động này trên staging.

### 13.2. Module-entry observations

Spring Modulith có thể tạo module-entry observations tại các API module được instrument. Các attribute như `module.identifier`, `module.name`, `module.invocation-type` và `module.method` giúp giải thích đường đi giữa module.

- Định danh module thường là tập hữu hạn.
- Tên method thường đến từ code, là tập hữu hạn.
- Không tạo observation name theo `orderId` hoặc `userId`.
- Nếu một custom `ModulithObservationConvention` đổi tên kỹ thuật theo dữ liệu động, điều đó có thể làm tăng số **metric names**, không chỉ số tag values.
- Tracing vẫn cần sampling/exporter và context propagation; không nên nhầm vắng span với vắng metric.

### 13.3. Database, messaging và external clients

Các instrumentation khác cũng có thể mang labels nguy hiểm như SQL statement kèm tham số, queue name động, URL host/path do người dùng nhập, response body hoặc exception messages. Trước deploy, rà soát **tất cả metric families được bật bởi dependency mới**, không chỉ Spring Modulith.

Một dependency tracing/metrics mới có thể làm xuất hiện nhiều meter names/tags mà đội dự án chưa định nghĩa trực tiếp.

### 13.4. Debug bằng trace thay vì gắn ID lên metrics

Khi cần kiểm tra **một** đơn hàng:

- Tìm trace theo trace ID/correlation ID.
- Dùng logs có cấu trúc và chính sách bảo mật phù hợp.
- Kiểm tra trạng thái nghiệp vụ hoặc event publication registry.
- Giữ counters để đo **tốc độ và xu hướng**, tags để phân nhóm hữu hạn.

Sử dụng high-cardinality dữ liệu trong traces/logs vẫn cần kiểm soát dữ liệu nhạy cảm và retention; không đồng nghĩa có thể ghi bất kỳ nội dung nào.

## 14. Một checklist kiểm tra trước production

### 14.1. Kiểm tra thiết kế

| Câu hỏi | PASS khi |
| --- | --- |
| Mỗi metric family có mục đích rõ chưa? | Có owner, đơn vị và câu hỏi vận hành |
| Có bản hợp đồng tags? | Key, source, values, budget được ghi lại |
| Có ID/PII trong metric tags? | Không có |
| Các tag tùy biến của Modulith đã phân đúng họ counter? | Customizer chỉ tác động counter dự kiến |
| Có biết các metrics/timers từ starter mới? | Đã liệt kê names và labels thực tế |
| Có đánh giá histogram/SLO? | Đã tính các chuỗi phát sinh thêm |
| Có phân biệt publication và processing? | Dashboard không coi publish là listener success |

### 14.2. Kiểm tra kỹ thuật

| Câu hỏi | PASS khi |
| --- | --- |
| Unit/integration tests có chạy trên registry thật? | Có test integration với Spring-managed registry |
| Đã thử đủ tag values hợp lệ? | Mỗi enum/category có dữ liệu |
| Đã thử nhiều IDs khác nhau? | Series không tăng theo unique ID |
| Có kiểm tra `Meter.Id` và tags? | Có kiểm tra whitelist và blacklist |
| Actuator có trả meter name/availableTags đúng? | Có sau khi phát hoạt động thử |
| Đã xem tên exporter thật? | Không đoán metric name Prometheus |
| Có đo active series và churn? | Có dữ liệu staging so sánh baseline |
| Có đủ các instances/labels? | Phạm vi đo tương đương production |
| Có kiểm tra tác động của filters? | Không từ chối giá trị hợp lệ |
| Có quy trình rollback và người theo dõi? | Được xác nhận trước deploy |

### 14.3. Tiêu chí nghiệm thu minh họa

Một bản thay đổi `sales.channel` nên được thông qua chỉ khi:

- Các kênh `web`, `mobile`, `pos` xuất hiện đúng.
- Không có UUID hoặc ID động trong `Meter.Id` và exporter labels.
- Phát nhiều đơn có ID khác nhau không tạo series theo từng ID.
- Event count theo kênh tăng đúng và dashboard không cộng đúp hai họ counters.
- Số series toàn service, số series theo family và churn trong tải staging nằm trong budget.
- Filter không chặn dữ liệu hợp lệ.
- Các alerts theo dõi series growth và telemetry health có thể hoạt động sau deploy.

Nếu chưa đo được một mục quan trọng, ghi **chưa kiểm chứng** và xem xét chặn rollout; không tự thay trạng thái thiếu dữ liệu thành PASS.

## 15. Kế hoạch triển khai và rollback có kiểm soát

### 15.1. Trước thời điểm triển khai

- Lưu baseline cùng khoảng thời gian và cấu hình instance count.
- Ghi lại bản code, danh sách customizers, meter filters và schema tags.
- Xác nhận các query/alerts mới khớp tên exporter thật.
- Kiểm thử thao tác rollback/feature toggle cho phần metric thêm mới nếu dự án hỗ trợ.
- Thống nhất ai sẽ kiểm tra biểu đồ series/cardinality sau rollout.

### 15.2. Trong rollout

Tăng dần lưu lượng hoặc số instance nhận build mới, theo dõi:

- Series count theo service và metric family.
- Series churn / số series mới.
- Ingestion rate, query latency và lỗi scrape/remote write.
- CPU/heap liên quan đến `MeterRegistry` và exporter.
- Counter publication có hợp lý so với lưu lượng nghiệp vụ không.
- Các nhánh có tạo tag values mới ngoài hợp đồng không.

Nếu số series hoặc churn tăng vượt budget, dừng rollout; kiểm tra series labels nào xuất hiện mới, và rollback/revert instrumentation hoặc customizer gây vấn đề. **Không chỉ tăng tài nguyên backend** nếu nguyên nhân là gắn ID duy nhất vào tag.

### 15.3. Sau rollback

Lưu ý một số series đã được backend nhận có thể vẫn tồn tại trong dữ liệu lịch sử cho đến khi hết retention. Rollback ngăn nguồn mới tiếp tục phát sinh, nhưng **không xóa lịch sử lưu trữ**. Cần theo dõi sự giảm của active series, tốc độ tạo series mới và chi phí ingestion.

Sau khi sửa nguồn tag, chạy lại kiểm thử staging, so sánh baseline và cập nhật hợp đồng metric trước một lần rollout tiếp theo.

## 16. Bài thực hành: quyết định GO / NO-GO

### 16.1. Tình huống giả định

Nhóm `orders` thêm customizer cho `OrderPlaced`. Ứng dụng chạy 8 instances; mỗi ngày công bố 200.000 `OrderPlaced`. Ban đầu, customizer dùng:

```java
builder.tag("sales.channel", event.channel().name());
builder.tag("order.id", event.orderId().toString());
```

Khi test 100 event, hệ thống tạo gần 100 series riêng cho counter `OrderPlaced` trên các giá trị `order.id` khác nhau. Sau khi bỏ dòng thứ hai, bộ tag còn lại chỉ gồm metadata module và ba giá trị `sales.channel`.

### 16.2. Câu hỏi phân tích

1. Vì sao 100 event ban đầu có thể tạo gần 100 series dù chỉ có 3 sales channels?
2. Sau khi bỏ `order.id`, số series có tăng theo tổng 200.000 event/ngày không?
3. Trong 8 instances và 3 channels, có thể có khoảng bao nhiêu series cho counter riêng, nếu mọi channel xuất hiện ở từng instance và không có tag khác?
4. Vì sao phải đo **churn trong 24 giờ**, không chỉ active series tại một thời điểm?
5. Nếu có thêm `module.events.published`, tại sao không cộng hai họ counters để đo tổng sự kiện?
6. Nếu metric bị biến đổi tên trong Prometheus, nên kiểm tra tên thực tế ở đâu?
7. Nếu filter giới hạn ba channel nhưng nghiệp vụ thêm `PARTNER`, liệu dashboard có được phép im lặng mất series mới không?
8. Dữ liệu nào phải thu để quyết định rollout sau khi sửa customizer?

### 16.3. Đáp án phân tích

- Mỗi UUID khác nhau tạo label set mới; `order.id` là high cardinality.
- Khi bỏ ID và chỉ còn ba channel cố định, nhiều event có thể tăng **count trên cùng series**.
- Khoảng **8 × 3 = 24 series** là ước lượng cho một counter cụ thể nếu mỗi instance xuất cả ba channel và không có labels/tùy biến khác; đo thực tế vẫn cần để xác nhận.
- Churn phát hiện series có vòng đời ngắn khi pod restart hoặc tag động.
- Counter tổng hợp và counter riêng có thể ghi nhận **cùng lượt publish**.
- Dùng `/actuator/prometheus` và dữ liệu scrape để lấy tên/labels thật.
- Khi thêm enum mới, phải cập nhật contract, budget, filter và test; nếu meter bị deny, dữ liệu sẽ thiếu.
- Cần cả test registry, Actuator, exporter và backend staging nhiều instance với baseline rõ ràng.

### 16.4. Mẫu báo cáo nghiệm thu

| Hạng mục | Bằng chứng | Trạng thái ví dụ |
| --- | --- | --- |
| Tag contract | Diff customizer và danh sách keys | PASS |
| Không còn `order.id` | Kiểm tra toàn bộ `Meter.Id` liên quan | PASS |
| Tag channel có 3 values | Registry + Actuator `availableTags` | PASS |
| Count tăng theo publish | Integration test delta count | PASS |
| Không tạo series theo UUID | 10.000 event IDs thử nghiệm | PASS |
| Active series trong budget | Query staging toàn cluster | PASS |
| Churn 24h trong budget | Query/backend series lifecycle | **Chưa kiểm chứng** |
| Điều kiện rollback | Runbook và feature flag nếu có | PASS |

Với kết quả minh họa, **chưa thể coi là GO hoàn chỉnh** vì vẫn thiếu phép đo churn. Mục đích của bài thực hành là xây kết luận có bằng chứng và ghi rõ lỗ hổng, thay vì chỉ báo “test xanh”.

## 17. Những sai lầm thường gặp

1. **Đo số tag keys thay vì số tag values.** Một tag `order.id` có thể tạo vô số series dù chỉ thêm một key.
2. **Nhân tất cả cardinalities và coi đó là số đo thực.** Phải xét các cặp module–event type và các chiều có tương quan.
3. **Chỉ chạy một request trên local.** Không đại diện tải, tập values hoặc số instances production.
4. **Chỉ nhìn `MeterRegistry.getMeters()` trên một JVM.** Backend có nhiều targets, labels và histogram buckets.
5. **Đếm event bằng `count(metric)` trong PromQL.** Hàm `count` đếm **series**, không đếm số event.
6. **Cộng hai họ event counters.** Cùng một publish có thể được biểu diễn hai lần và làm dashboard sai.
7. **Dùng `orderId` hoặc `traceId` để tìm riêng request.** Dùng traces/logs phù hợp thay vì biến thành tags của metrics.
8. **Giữ mọi tag có tên ngắn.** Cardinality dựa vào tập giá trị, không dựa vào độ dài tên.
9. **Dựa vào MeterFilter để “sửa” cardinality.** Filter từ chối meter làm thiếu dữ liệu và che nguồn tag sai.
10. **Bỏ qua churn.** Một ngày có rất nhiều series ngắn có thể đắt dù active series tại một thời điểm thấp.
11. **Không tính nhãn hạ tầng và histogram.** Backend có thể tạo nhiều series hơn JVM dự đoán.
12. **Giả định metric có sẵn ngay lúc khởi động.** Một số meter xuất hiện sau khi sự kiện hoặc operation được thực thi.
13. **Đưa tên contextual span chứa ID động vào metric name.** Tên quan sát/meter cần ổn định, đặc biệt khi có observation convention tùy chỉnh.
14. **Nhầm event publication với listener success.** Một counter tăng không chứng minh listener hoặc transaction hoàn tất.
15. **Bỏ qua canary/rollback.** Dù staging PASS, traffic thật và nhãn hạ tầng khác có thể tạo các trường hợp chưa được mô phỏng.

## 18. Câu hỏi tự đánh giá

1. Tag cardinality là gì? Khác số series đang hoạt động và distinct series trong 24 giờ ra sao?
2. Vì sao một `order.id` tag có thể nguy hiểm hơn việc thêm ba channel labels?
3. Số meter ở một JVM có bằng số series trong Prometheus không? Những yếu tố nào làm chúng khác nhau?
4. Khi tính `4 × 4 × 12` cho module, display name và event type, tại sao đó có thể là giới hạn trên quá lớn?
5. Bộ low-cardinality tags mặc định của `module.events.published` gồm những key nào?
6. Counter riêng của `OrderPlaced` mặc định có `module.event.type` không?
7. `ModulithEventMetricsCustomizer` có tác động tới counter tổng hợp theo cách dùng thông thường không?
8. Vì sao `Counter.Builder.tag("order.id", ...)` cần bị chặn ở code review?
9. Nêu hai bằng chứng tối thiểu để xác nhận tag `sales.channel` chỉ có ba giá trị trên bản chạy.
10. `count(module_events_published_total)` và `sum(rate(module_events_published_total[5m]))` trả lời các câu hỏi khác nhau như thế nào?
11. Tại sao phải xem `/actuator/prometheus` trước khi viết PromQL?
12. Nêu ba lý do một metric có thể có 3 series trên JVM nhưng nhiều hơn trên backend.
13. `MeterFilter.maximumAllowableTags(...)` bảo vệ được gì và có thể gây mất dữ liệu gì?
14. Làm sao nhận diện một thay đổi gây **churn** dù số active series tương đối ổn định?
15. Trong bài thử staging, khi nào bạn quyết định NO-GO dù integration tests đã PASS?
16. Khi rollout đã tạo nhiều series có tag UUID, rollback có xóa ngay mọi series lịch sử không?
17. Khi muốn lần theo một sự kiện riêng lẻ, vì sao nên dùng trace/log correlation thay vì thêm ID vào metric labels?

## 19. Tài liệu tham khảo chính thức

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module observability, hai họ event publication counters, bộ low-cardinality tags và `ModulithEventMetricsCustomizer`.
- [Spring Modulith — ModulithEventMetricsCustomizer API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html): điểm mở rộng customizer.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, metrics endpoint, common tags, Actuator.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access và bảo mật.
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): phát hiện tag cardinality cao và thực hành giảm cardinality.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): `maximumAllowableTags`, `maximumAllowableMetrics`, lọc/thay đổi meter.
- [Micrometer — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): registration, meter identity và registry lifecycle.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): low/high-cardinality key-values.
- [Prometheus — Aggregation Operators](https://prometheus.io/docs/prometheus/latest/querying/operators/): `count`, `sum` và grouping.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase` và `count_over_time`.

> **Ghi nhớ:** Kiểm tra cardinality trước production phải đi từ **hợp đồng tag → ước lượng budget → kiểm thử MeterRegistry → kiểm tra Actuator/exporter → đo active series và churn trên staging → quyết định GO/NO-GO**. Với Spring Modulith, giữ tag module và event type có tập giá trị ổn định, dùng customizer cho những enum nghiệp vụ hữu hạn và tuyệt đối tránh biến ID từng event thành metric labels. `MeterFilter` chỉ là hàng rào cuối cùng; an toàn thực sự đến từ việc thiết kế đúng nguồn sinh tags và đo được tác động của toàn hệ thống.
