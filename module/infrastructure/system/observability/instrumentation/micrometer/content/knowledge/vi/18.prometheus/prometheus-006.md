# Tập khóa tag nhất quán và lỗi đăng ký cùng tên với cấu trúc khác nhau

Trong Micrometer, một meter được nhận diện bằng tên và tập tag của nó. Hai meter cùng tên nhưng có các giá trị tag khác nhau thường là những series khác nhau và có thể cùng tồn tại. Tuy nhiên, khi xuất sang Prometheus, các meter cùng tên cần được thiết kế với cấu trúc label nhất quán để registry và hệ thống truy vấn hiểu chúng như một metric family có cùng ý nghĩa.

Một lỗi phổ biến là chỉ thêm tag khi có dữ liệu, khiến cùng một metric name lúc thì có `outcome`, lúc thì không; hoặc một nhánh code dùng `region`, nhánh khác dùng `zone`. Với một số phiên bản Prometheus registry cũ, meter thứ hai có thể bị từ chối khi tập tag key khác meter đã đăng ký trước. Micrometer 1.17 thay đổi hành vi của registry dùng Prometheus Java Client mới và bỏ giới hạn đăng ký này, nhưng tài liệu hiện hành vẫn khuyến nghị giữ tập tag key nhất quán.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, quy tắc này cần được áp dụng từ instrumentation, common tags và MeterFilter đến kiểm thử registry. Cần phân biệt lỗi khác tập tag key với lỗi đăng ký cùng một Meter ID bằng type khác, cũng như xung đột tên sau khi registry chuẩn hóa tên cho Prometheus.

## 1. Meter ID gồm tên và tag

Micrometer dùng tên và tag để xác định một meter. Ví dụ:

```java
registry.counter("orders.created", "channel", "web").increment();
registry.counter("orders.created", "channel", "mobile").increment();
```

Hai meter có cùng tên `orders.created` và cùng tag key `channel`, nhưng khác tag value. Chúng biểu diễn hai series khác nhau:

```text
orders_created_total{channel="web"} 1
orders_created_total{channel="mobile"} 1
```

Đây là cách phân chiều dữ liệu bình thường. Giá trị tag có thể khác nhau miễn là chúng thuộc vocabulary được kiểm soát và không làm cardinality tăng không giới hạn.

Ngược lại, ví dụ sau dùng hai tập tag key khác nhau:

```java
registry.counter("orders.created", "channel", "web").increment();
registry.counter("orders.created", "region", "ap-southeast").increment();
```

Meter đầu tiên có key `channel`; meter thứ hai có key `region`. Cả hai cùng tên nhưng cấu trúc dimensions không nhất quán. Với các phiên bản Prometheus registry trước 1.17, đây là trường hợp đăng ký bị từ chối. Ở các phiên bản mới hơn, registry sử dụng Prometheus Java Client mới đã bỏ giới hạn này, nhưng vẫn nên duy trì cấu trúc tag key thống nhất để dashboard, rule và truy vấn dễ dự đoán.

## 2. Tập tag key và tag value là hai khái niệm khác nhau

Hãy phân biệt tập khóa tag (tag key set) và các giá trị của tag:

| Meter | Tag key set | Tag values | Đánh giá |
| --- | --- | --- | --- |
| `orders.created{channel="web"}` | `{channel}` | `web` | Hợp lệ |
| `orders.created{channel="mobile"}` | `{channel}` | `mobile` | Hợp lệ; cùng key set với meter trên |
| `orders.created{channel="web",region="ap-southeast"}` | `{channel, region}` | `web`, `ap-southeast` | Khác key set với hai meter đầu |
| `orders.created{region="ap-southeast"}` | `{region}` | `ap-southeast` | Khác key set với meter đầu |

Với cùng metric name, nên giữ nguyên các key `channel` và `region` ở mọi nhánh. Khi một chiều không có giá trị, dùng một giá trị thay thế đã quy ước như `unknown`, `none` hoặc `other`:

```java
registry.counter(
        "orders.created",
        "channel", channel != null ? channel : "unknown",
        "region", region != null ? region : "unknown")
    .increment();
```

Như vậy, mọi series của `orders.created` đều có cùng tập key `{channel, region}`. Chỉ các giá trị thay đổi theo trường hợp nghiệp vụ.

Chọn sentinel có ý nghĩa. `unknown` phù hợp khi hệ thống chưa xác định được giá trị; `none` phù hợp khi chiều đó không áp dụng; `other` phù hợp khi gom những giá trị ngoài danh sách cho phép. Không dùng một chuỗi ngẫu nhiên hoặc ID duy nhất làm giá trị thay thế.

## 3. Lỗi đăng ký do khác tập tag key trong các phiên bản cũ

Trong các phiên bản Prometheus registry cũ, các meter có cùng tên phải có cùng tập tag key. Ví dụ:

```java
registry.counter("checkout.events", "result", "success").increment();

// Tập tag key khác: meter thứ hai không được đăng ký.
registry.counter("checkout.events", "failure", "timeout").increment();
```

Registry đã thấy metric `checkout.events` với key `result`. Khi đăng ký lần thứ hai với key `failure`, nó phát hiện cấu trúc khác nhau. Theo tài liệu Micrometer 1.12/1.14, đăng ký tiếp theo sẽ không được thực hiện và mặc định có thể chỉ ghi warning rồi giảm mức log cho những lần sau. Vì vậy, ứng dụng có thể vẫn chạy nhưng dữ liệu của meter thứ hai không xuất hiện ở endpoint scrape.

Đây là lý do lỗi này dễ bị bỏ sót nếu chỉ kiểm tra HTTP endpoint hoặc không theo dõi log đăng ký. Không nên dựa vào việc ứng dụng khởi động thành công để kết luận mọi meter đã được đăng ký.

### Sửa bằng tập key cố định

Thay vì tạo key khác nhau theo kết quả, hãy dùng một key chung như `outcome`:

```java
registry.counter("checkout.events", "outcome", "success").increment();
registry.counter("checkout.events", "outcome", "timeout").increment();
registry.counter("checkout.events", "outcome", "rejected").increment();
```

Nếu có nhiều chiều tùy chọn, luôn truyền đầy đủ tất cả key:

```java
registry.counter(
        "checkout.events",
        "outcome", "success",
        "payment_method", "card")
    .increment();

registry.counter(
        "checkout.events",
        "outcome", "timeout",
        "payment_method", "unknown")
    .increment();
```

Mọi series đều có hai key `outcome` và `payment_method`. Chỉ value thay đổi.

## 4. Khác biệt theo phiên bản Micrometer và Prometheus client

Không nên áp dụng nguyên trạng thông báo lỗi của một phiên bản cũ cho mọi ứng dụng hiện tại:

| Phiên bản/adapter | Hành vi liên quan đến tập tag key |
| --- | --- |
| Micrometer Prometheus registry trước 1.17 | Không cho phép cùng tên meter có tập tag key khác nhau; meter đăng ký sau có thể bị từ chối |
| Micrometer 1.17 trở lên với `micrometer-registry-prometheus` (Prometheus Java Client mới) | Đã bỏ giới hạn đăng ký cùng tên phải có cùng tập tag key |
| `micrometer-registry-prometheus-simpleclient` (adapter legacy) | Dùng Prometheus Java Client 0.x; cần kiểm tra hành vi theo đúng phiên bản adapter đang triển khai |

Micrometer 1.17 nâng cấp Prometheus Java Client mới và loại bỏ giới hạn tag-key-set của registry. Tuy nhiên, tài liệu Prometheus hiện hành vẫn khuyến nghị mạnh mẽ việc đăng ký các meter cùng tên với tập tag key nhất quán. Quy tắc này giúp dữ liệu có cấu trúc dễ hiểu và giữ dashboard/recording rule ổn định giữa các phiên bản.

Trước khi kết luận lỗi thuộc về Micrometer hay Prometheus, hãy xác định:

1. Phiên bản Micrometer Core thực tế.
2. Artifact đang dùng: `micrometer-registry-prometheus` hay `micrometer-registry-prometheus-simpleclient`.
3. Phiên bản Prometheus Java Client bắc cầu được resolve.
4. Thông báo warning/exception tại thời điểm meter được đăng ký.

Spring Boot thường quản lý phiên bản Micrometer bằng dependency management. Hãy xem dependency tree hoặc dependency insight để biết phiên bản thực tế thay vì suy đoán từ version của Spring Boot.

## 5. Lỗi cùng Meter ID nhưng khác meter type

Một trường hợp khác với khác tập tag key là đăng ký cùng một Meter ID nhưng bằng hai loại meter khác nhau. Ví dụ:

```java
registry.counter("worker.active", "pool", "primary").increment();

Gauge.builder("worker.active", activeWorkers, AtomicInteger::get)
        .tag("pool", "primary")
        .register(registry);
```

Cả hai đăng ký có cùng tên `worker.active` và cùng tag `pool=primary`, nhưng một meter là counter, meter kia là gauge. Đây là cùng Meter ID nhưng khác type. `MeterRegistry` core không thể trả về một meter cùng ID với type không tương thích và sẽ ném `IllegalArgumentException` khi phát hiện đã có meter loại khác.

Hãy đặt tên khác nhau theo ngữ nghĩa:

```java
registry.counter("worker.tasks.completed", "pool", "primary").increment();

Gauge.builder("worker.active", activeWorkers, AtomicInteger::get)
        .tag("pool", "primary")
        .register(registry);
```

Counter đếm số tác vụ đã hoàn tất; gauge đo số worker đang hoạt động. Hai phép đo có ý nghĩa khác nhau nên phải có tên riêng.

Nếu cùng tên và cùng tag được đăng ký lặp lại bằng cùng type, Micrometer thường trả về meter đã tồn tại để các nơi trong ứng dụng cùng cập nhật một phép đo. Đây là cơ chế tái sử dụng có chủ đích, không phải xung đột. Chỉ khi type hoặc cấu trúc/metadata không tương thích mới cần điều tra.

## 6. Xung đột tên sau khi chuẩn hóa cho Prometheus

Micrometer sử dụng tên canonical trong Java, sau đó registry chuyển tên theo quy ước của backend. Vì vậy, hai tên canonical khác nhau vẫn có thể đụng nhau sau khi chuẩn hóa hoặc bổ sung hậu tố.

Ví dụ được ghi nhận trong hướng dẫn nâng cấp Micrometer 1.17:

```java
registry.counter("test").increment();
registry.counter("test.total").increment(42);
```

Prometheus thêm hậu tố `_total` cho counter. Hai meter trên có thể cùng ánh xạ về tên Prometheus `test_total`. Từ Micrometer 1.17, registry giữ meter được đăng ký trước và từ chối meter tiếp theo nếu chúng tạo ra cùng Prometheus name. Ở các phiên bản cũ, xung đột có thể dẫn đến output không như mong đợi mà không có lỗi rõ ràng.

Một dạng xung đột khác là timer tự tạo các chuỗi phụ như count, sum, max hoặc bucket. Nếu ứng dụng tự đăng ký một gauge có tên trùng với một chuỗi phụ mà timer tạo ra, scrape có thể thất bại do duplicate metric name. Ví dụ timer `test` có thể tạo `test_seconds_max`, vì vậy không nên dùng chính tên đó cho một gauge độc lập.

Hãy kiểm tra tên sau chuẩn hóa bằng endpoint `/actuator/prometheus`, không chỉ nhìn tên builder trong Java. Khi thay đổi meter name, type hoặc registry version, cần xác minh lại tên export và các dashboard/alert liên quan.

## 7. Dùng common tags để giữ cấu trúc nhất quán

Nếu một số tag phải có trên mọi meter, có thể khai báo common tags ở cấp registry:

```java
registry.config().commonTags(
        "application", "order-service",
        "environment", "production");
```

Spring Boot cũng hỗ trợ cấu hình common tags:

```yaml
management:
  metrics:
    tags:
      application: order-service
      environment: production
```

Common tags giúp mọi meter được đăng ký sau đó có cùng các chiều chung. Hãy tránh thêm lại cùng key ở builder của từng meter với value khác. Tập tag cuối cùng sau khi áp dụng common tags và filter mới là cấu trúc cần được kiểm tra.

Nếu dùng `MeterFilter` để thêm, đổi hoặc xóa tag, hãy bảo đảm filter không làm các meter cùng tên có cấu trúc cuối cùng khác nhau. Một filter được áp dụng toàn registry có thể ảnh hưởng đến meter do thư viện hoặc binder khác đăng ký.

## 8. Kiểm soát tag tùy chọn

Tag tùy chọn là nguồn phổ biến tạo ra key set không đồng nhất. Ví dụ một request có `tenant`, request khác không có; một nhánh ghi `status`, nhánh khác ghi `errorCode`. Hãy thiết kế schema tag ngay từ đầu:

```java
private static final String UNKNOWN = "unknown";

void record(String outcome, String tenant) {
    registry.counter(
            "api.operations",
            "outcome", normalizeOutcome(outcome),
            "tenant", tenant != null ? tenant : UNKNOWN)
        .increment();
}
```

`normalizeOutcome` nên ánh xạ về tập giá trị nhỏ, ví dụ `success`, `rejected`, `timeout`, `error`. `tenant` chỉ phù hợp làm tag nếu tập tenant được giới hạn và số series phát sinh có thể kiểm soát; nếu tenant có số lượng lớn hoặc tăng liên tục, không nên đưa tenant ID vào metric label.

Đối với HTTP metrics, dùng route template như `/orders/{id}` thay cho URL chứa ID thực tế. Với exception, dùng nhóm lỗi hữu hạn như `timeout`, `validation`, `dependency` thay cho message hoặc class name tùy ý.

## 9. Kiểm thử lỗi đăng ký trên registry đích

`SimpleMeterRegistry` hữu ích để kiểm tra tên, tag và giá trị ở lớp Micrometer core. Tuy nhiên, nó không tái hiện đầy đủ các quy tắc riêng của Prometheus registry. Những kiểm thử về tập tag key và xung đột tên cần chạy với đúng Prometheus adapter của ứng dụng.

### Kiểm thử tập tag key trên phiên bản cũ

Với registry cũ có giới hạn tag key, có thể cấu hình registration failure listener để biến warning thành exception trong test:

```java
registry.config().onMeterRegistrationFailed((id, reason) -> {
    throw new IllegalArgumentException(reason);
});

registry.counter("test", "first", "1").increment();

// Trên registry có giới hạn cũ, dòng này sẽ làm test thất bại.
registry.counter("test", "second", "2").increment();
```

Với các phiên bản Prometheus registry có hỗ trợ shortcut, có thể bật chế độ nghiêm ngặt bằng:

```java
prometheusRegistry.throwExceptionOnRegistrationFailure();
```

Kiểu `PrometheusMeterRegistry` và package import phụ thuộc adapter Prometheus Java Client mới hay legacy. Hãy dùng lớp tương ứng với dependency đang có trong dự án. Trên Micrometer 1.17 trở lên với adapter mới, khác tập tag key không còn là lỗi đăng ký theo giới hạn cũ; test cần phản ánh hành vi phiên bản thực tế.

### Kiểm thử cùng ID nhưng khác type

Trường hợp cùng tên, cùng tag và khác type là lỗi ở MeterRegistry core:

```java
assertThrows(IllegalArgumentException.class, () -> {
    registry.counter("worker.active", "pool", "primary");
    Gauge.builder("worker.active", activeWorkers, AtomicInteger::get)
            .tag("pool", "primary")
            .register(registry);
});
```

Test này có thể dùng registry trong bộ nhớ vì nó kiểm tra xung đột type cho cùng Meter ID, không phụ thuộc Prometheus.

### Kiểm tra output scrape

Trong integration test Spring Boot, đăng ký các meter với tập tag key chuẩn, gọi endpoint `/actuator/prometheus` và xác nhận:

1. Mỗi metric family xuất hiện với tên dự kiến.
2. Tất cả series của một metric name có cùng label keys theo schema đã thiết kế.
3. Các trường hợp thiếu giá trị dùng sentinel đã quy ước.
4. Không có warning hoặc registration failure bị bỏ qua.
5. Không có hai meter canonical ánh xạ về cùng tên Prometheus.

Một endpoint HTTP trả về 200 chưa chứng minh mọi meter đã được đăng ký. Hãy kiểm tra nội dung scrape và log registration, đặc biệt với các phiên bản cũ có thể chỉ ghi warning khi từ chối meter.

## 10. Quy trình điều tra khi meter không xuất hiện

Khi một metric thiếu khỏi Prometheus, hãy kiểm tra lần lượt:

1. Xác nhận instrumentation thực sự đăng ký meter và tên canonical được dùng.
2. Kiểm tra tên và toàn bộ tag key/value ở mọi nhánh code đăng ký cùng metric name.
3. Kiểm tra có đăng ký trùng cùng Meter ID nhưng khác type hay không.
4. Kiểm tra common tags và MeterFilter có làm thay đổi cấu trúc tag cuối cùng không.
5. Xem log warning/registration failure ở thời điểm meter được tạo.
6. Xác định Micrometer version và Prometheus registry adapter (new client hay legacy client).
7. Kiểm tra tên export sau normalization và hậu tố của counter/timer.
8. Gọi `/actuator/prometheus` để xem metric family thực tế được công bố.
9. Xác nhận Prometheus đã scrape target và series đã có trong query.

Không chỉ sửa dashboard để bỏ qua metric bị thiếu. Nếu registry đã từ chối meter, cần sửa schema tag hoặc tên/type ở nơi đăng ký để dữ liệu được xuất đúng.

## 11. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cùng tên nhưng nhánh code dùng key khác nhau | Tag tùy chọn được thêm có điều kiện | Luôn truyền đủ tập key và dùng sentinel cho giá trị thiếu |
| Nghĩ khác tag value cũng là lỗi cấu trúc | Nhầm key set với value | Giữ key giống nhau; cho phép value thay đổi trong vocabulary hữu hạn |
| Dùng cùng tên và cùng tag cho Counter với Gauge | Meter ID giống nhau nhưng type khác | Đặt tên riêng theo ngữ nghĩa phép đo |
| Meter thứ hai không xuất nhưng ứng dụng vẫn chạy | Registry cũ ghi warning và từ chối đăng ký | Bật registration failure listener trong test, kiểm tra log |
| Giả định mọi Micrometer version có cùng giới hạn | Bỏ qua thay đổi ở 1.17 | Xác định phiên bản và adapter cụ thể |
| Hai tên Micrometer va chạm sau chuẩn hóa | Suffix hoặc naming convention tạo cùng Prometheus name | Kiểm tra scrape output và chọn tên canonical khác |
| Timer và gauge tạo cùng tên chuỗi phụ | Không xét các series do timer sinh ra | Tránh đặt gauge trùng `_count`, `_sum`, `_max` hoặc `_bucket` |
| Đưa ID vào tag để phân biệt series | Cardinality tăng cao | Dùng chiều có tập giá trị hữu hạn; chi tiết để trong log/trace |

## 12. Quy tắc thiết kế đề xuất

Khi thiết kế metric có nhiều nhánh ghi nhận:

1. Chọn một metric name cho một khái niệm và một meter type ổn định.
2. Định nghĩa trước tập tag key cho metric name đó.
3. Dùng cùng tập key trong mọi nhánh code, kể cả khi một số chiều không áp dụng.
4. Chuẩn hóa tag value về vocabulary hữu hạn; dùng `unknown`, `none` hoặc `other` khi phù hợp.
5. Dùng common tags một cách nhất quán và kiểm tra tag cuối cùng sau MeterFilter.
6. Tránh đăng ký cùng Meter ID bằng type khác; đặt tên riêng cho phép đo khác ngữ nghĩa.
7. Kiểm tra tên export để phát hiện collision do naming convention hoặc suffix.
8. Kiểm thử trên Prometheus registry đúng phiên bản, không chỉ dựa vào SimpleMeterRegistry.
9. Theo dõi registration failure và scrape output trong integration test.

Tập tag key ổn định giúp một metric name có cấu trúc rõ ràng và dễ truy vấn. Với Micrometer Prometheus registry cũ, điều này còn tránh lỗi đăng ký làm meter không xuất hiện. Các phiên bản mới đã nới lỏng giới hạn cụ thể về tag key, nhưng vẫn cần thiết kế schema nhất quán, meter type rõ ràng và tên export không xung đột để dữ liệu metrics giữ được ý nghĩa trong suốt vòng đời ứng dụng.

## Tài liệu tham khảo

- [Micrometer Prometheus Registry 1.18](https://docs.micrometer.io/micrometer/reference/implementations/prometheus)
- [Micrometer Prometheus Registry 1.12: giới hạn tag key và registration failure](https://docs.micrometer.io/micrometer/reference/1.12/implementations/prometheus.html)
- [Micrometer 1.17 Migration Guide: thay đổi Prometheus registry và duplicate names](https://github.com/micrometer-metrics/micrometer/wiki/1.17-Migration-Guide)
- [MeterRegistry source: đăng ký lại cùng ID và kiểm tra meter type](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java)
