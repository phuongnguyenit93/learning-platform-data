# Lọc, đổi tên hoặc từ chối meter bằng MeterFilter

## 1. Vì sao cần một lớp chính sách cho phép đo?

Một ứng dụng Spring Boot có thể nhận phép đo từ nhiều nơi: mã nghiệp vụ, thư viện, JVM và các thành phần được Actuator cấu hình tự động. Các nguồn này không nhất thiết cùng tuân theo một quy ước tên và nhãn.

Giả sử phần xử lý đơn hàng đang đăng ký:

```text
legacy.orders.processed
    result=success
    request.id=req-101
```

Nhóm vận hành muốn:

- Dùng tiền tố `shop.orders.` để thống nhất tên.
- Đổi khóa nhãn `result` thành `outcome`.
- Bỏ `request.id` khỏi nhóm phép đo này để không tách một chuỗi số liệu cho từng request.
- Không đăng ký các phép đo chẩn đoán bắt đầu bằng `shop.orders.internal.`.

**MeterFilter là cơ chế đặt chính sách khi meter được đăng ký vào một MeterRegistry.** Nó có thể biến đổi định danh hoặc quyết định chấp nhận/từ chối việc đăng ký.

MeterFilter không thay thế mã ghi nhận sự kiện. Mã nghiệp vụ vẫn phải gọi `increment`, `record` hoặc cung cấp nguồn đọc phù hợp. Filter quyết định phép đo đó đi vào registry dưới định danh nào và có được đăng ký hay không.

Trong bài này, `Meter` được hiểu là đối tượng phép đo như Counter, Gauge hoặc Timer; `Meter.Id` chứa định danh và metadata liên quan. Tên cùng tập tag là phần quan trọng để phân biệt các phép đo.

## 2. Ba điểm mở rộng của MeterFilter

| Phương thức | Vai trò |
| --- | --- |
| `map(Meter.Id)` | Trả về định danh sau biến đổi: tên, tag hoặc metadata phù hợp |
| `accept(Meter.Id)` | Quyết định chấp nhận, từ chối hoặc để filter tiếp theo xét |
| `configure(Meter.Id, DistributionStatisticConfig)` | Tùy chỉnh cấu hình phân phối của những loại như Timer và DistributionSummary |

Các phương thức có triển khai mặc định, nên một filter chỉ cần ghi đè phần mình sử dụng. Ví dụ đổi tên thường chỉ cần `map`; quy tắc từ chối thường chỉ cần `accept`.

`configure` phục vụ những chính sách như cấu hình histogram hoặc percentile. Khi mở rộng phần đó, cần kết hợp cấu hình mới với cấu hình đã có một cách có chủ đích, thay vì vô tình xóa những thiết lập của builder hoặc filter khác.

Phạm vi tác động là registry được gắn filter. Nếu ứng dụng dùng nhiều registry độc lập, không suy ra rằng cấu hình một nơi sẽ tự có tác dụng ở tất cả những nơi còn lại.

Tài liệu [Meter Filters của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html) trình bày ba vai trò và các hàm tiện ích tương ứng.

### Filter không chạy trên từng lần increment

Một Counter đã đăng ký được giữ trong biến và được tăng nhiều lần. MeterFilter không được gọi như một bộ lọc sự kiện trước mỗi lần tăng.

Vì vậy, không viết `map` để đọc request hiện tại từ `ThreadLocal`, thêm ID ngẫu nhiên hoặc lấy dữ liệu từ dịch vụ mạng. Ánh xạ nên ổn định theo định danh đầu vào và cấu hình ổn định của ứng dụng.

Tag phụ thuộc một sự kiện cụ thể phải được thiết kế ở điểm ghi nhận thích hợp, với tập giá trị được kiểm soát. MeterFilter không phải chỗ thay thế cho việc thiết kế đó.

## 3. Hiểu đúng NEUTRAL, ACCEPT và DENY

Phương thức `accept` trả về một trong ba giá trị của `MeterFilterReply`:

| Giá trị | Ý nghĩa trong chuỗi quyết định |
| --- | --- |
| `NEUTRAL` | Chưa quyết định; tiếp tục xét filter phía sau |
| `ACCEPT` | Chấp nhận; không hỏi các phương thức `accept` còn lại |
| `DENY` | Từ chối; không hỏi các phương thức `accept` còn lại |

Nếu không có filter nào đưa ra quyết định chấp nhận hoặc từ chối, meter được phép đăng ký.

Điều này có hai hệ quả dễ nhầm.

**NEUTRAL không có nghĩa là từ chối.** Một filter không quan tâm đến tên hiện tại có thể trả NEUTRAL, để các quy tắc khác tiếp tục làm việc.

**ACCEPT không chỉ là “tôi không cấm”.** Nó quyết định kết quả ngay trong chuỗi chấp nhận/từ chối. Một quy tắc ACCEPT quá rộng có thể bỏ qua quy tắc từ chối hoặc giới hạn tag ở phía sau.

### Ví dụ thứ tự sai với ý định chặn metrics nội bộ

Các đoạn ngắn sau giả định đã có biến `registry`:

```java
registry.config()
        .meterFilter(MeterFilter.acceptNameStartsWith("shop."))
        .meterFilter(MeterFilter.denyNameStartsWith("shop.orders.internal."));
```

Một meter tên `shop.orders.internal.debug` khớp quy tắc đầu tiên và được ACCEPT. Quy tắc từ chối sau đó không được hỏi.

Nếu muốn ngoại lệ từ chối có ưu tiên cao hơn:

```java
registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("shop.orders.internal."))
        .meterFilter(MeterFilter.acceptNameStartsWith("shop."));
```

Các tên không khớp hai quy tắc này vẫn không tự bị cấm, vì cả hai có thể trả NEUTRAL.

Để có danh sách chỉ cho phép một nhóm, có thể thêm `MeterFilter.deny()` ở cuối, hoặc dùng `denyUnless` với predicate phù hợp. Cần lựa chọn rõ ý định, không chỉ xếp filter theo tên phương thức.

### accept và denyUnless khác nhau ở trường hợp khớp

```java
MeterFilter.accept(id -> id.getName().startsWith("shop."));
MeterFilter.denyUnless(id -> id.getName().startsWith("shop."));
```

Với một tên bắt đầu bằng `shop.`:

- `accept(...)` trả ACCEPT, kết thúc chuỗi quyết định.
- `denyUnless(...)` trả NEUTRAL, để các quy tắc phía sau tiếp tục xét.

Với tên không khớp, `denyUnless` trả DENY. Nhờ vậy, nó có thể giới hạn một phạm vi mà vẫn cho các quy tắc sau từ chối những trường hợp cụ thể trong phạm vi đó.

## 4. Thứ tự map khác với thứ tự accept

Với một meter cần được tạo mới trong Micrometer 1.13.0, có thể hình dung:

```text
Định danh ban đầu
    -> map của filter 1
    -> map của filter 2
    -> ... định danh sau ánh xạ
    -> chuỗi accept trên định danh đã ánh xạ
        -> DENY: trả meter NOOP
        -> được chấp nhận: cấu hình phân phối nếu có, rồi tạo meter
```

Các phép `map` nối tiếp nhau: filter sau nhận kết quả ánh xạ của filter trước. Vì vậy, đổi tiền tố trước rồi đổi khóa tag dựa trên tiền tố mới là một thứ tự có ý nghĩa.

Các phương thức `accept` xét **định danh đã qua chuỗi map**. Nếu tên `legacy.orders.processed` đã được đổi thành `shop.orders.processed`, quy tắc chấp nhận/từ chối cần được viết theo tên cuối phù hợp.

Không hình dung mỗi filter là một khối “map rồi accept rồi configure” hoàn chỉnh trước khi chuyển qua filter tiếp theo. Các giai đoạn được registry phối hợp.

Một ACCEPT sớm chỉ dừng việc hỏi các phương thức `accept` phía sau. Nó không có nghĩa các phép map phía sau bị bỏ qua: chuỗi map đã được thực hiện trước bước quyết định. Tương tự, không suy ra ACCEPT sẽ bỏ qua mọi cấu hình phân phối của filter khác.

Khi registry tìm thấy meter đã có, nó có thể dùng lại đối tượng thay vì đi qua toàn bộ đường tạo mới. Chi tiết thứ tự này được kiểm chứng trong [MeterRegistry của Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

## 5. Đổi tên meter, đổi khóa tag và bỏ tag

Ba việc sau khác nhau:

| Nhu cầu | Cách biểu đạt |
| --- | --- |
| `legacy.orders.processed` thành `shop.orders.processed` | Ghi đè `map`, trả `id.withName(...)` |
| Khóa tag `result` thành `outcome` | `MeterFilter.renameTag(prefix, fromKey, toKey)` |
| Bỏ khóa tag `request.id` | `MeterFilter.ignoreTags(...)`, có thể bọc để giới hạn phạm vi |
| Chuẩn hóa một nhóm giá trị tag | `MeterFilter.replaceTagValues(...)` với ánh xạ phù hợp |

**renameTag không đổi tên meter.** Tham số đầu là tiền tố tên dùng để xác định phạm vi đổi khóa nhãn.

Không sửa trực tiếp đối tượng ID rồi trả null. Các phương thức như `withName` tạo ID mới; `map` phải trả về ID cần dùng, hoặc trả ID ban đầu khi không có thay đổi.

### Lớp chứa các ánh xạ dùng chung

Tệp `src/example/filter/OrderMetricFilters.java`:

```java
package example.filter;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;

public final class OrderMetricFilters {

    private OrderMetricFilters() {
    }

    public static MeterFilter renameLegacyOrders() {
        return new MeterFilter() {
            @Override
            public Meter.Id map(Meter.Id id) {
                if (id.getName().startsWith("legacy.orders.")) {
                    return id.withName(
                            "shop." + id.getName().substring("legacy.".length()));
                }
                return id;
            }
        };
    }

    public static MeterFilter ignoreOrderRequestId() {
        MeterFilter delegate = MeterFilter.ignoreTags("request.id");

        return new MeterFilter() {
            @Override
            public Meter.Id map(Meter.Id id) {
                if (id.getName().startsWith("shop.orders.")) {
                    return delegate.map(id);
                }
                return id;
            }
        };
    }
}
```

Filter thứ nhất chỉ đổi tên thuộc nhóm `legacy.orders.`. Filter thứ hai chỉ bỏ tag cho nhóm `shop.orders.`; nó không xóa `request.id` trên mọi meter khác trong registry.

Giới hạn phạm vi là một phần của chính sách. Một lời gọi `ignoreTags("request.id")` được gắn trực tiếp sẽ tác động đến mọi định danh đi qua nó, không chỉ các phép đo đơn hàng.

## 6. Chương trình hoàn chỉnh: đổi tên, gộp tag và từ chối

Thí nghiệm dưới đây sử dụng một registry riêng, với chính sách cố ý chỉ cho phép tiền tố `shop.`, sau khi đã loại nhóm nội bộ. Nó giúp nhìn rõ kết quả của từng quy tắc.

Tệp `src/example/filter/MeterFilterDemo.java`:

```java
package example.filter;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public final class MeterFilterDemo {

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            registry.config()
                    .meterFilter(OrderMetricFilters.renameLegacyOrders())
                    .meterFilter(MeterFilter.renameTag(
                            "shop.orders.", "result", "outcome"))
                    .meterFilter(OrderMetricFilters.ignoreOrderRequestId())
                    .meterFilter(MeterFilter.denyNameStartsWith(
                            "shop.orders.internal."))
                    .meterFilter(MeterFilter.acceptNameStartsWith("shop."))
                    .meterFilter(MeterFilter.deny());

            Counter first = registry.counter(
                    "legacy.orders.processed",
                    "result", "success",
                    "request.id", "req-101");
            first.increment(2);

            Counter second = registry.counter(
                    "legacy.orders.processed",
                    "result", "success",
                    "request.id", "req-102");
            second.increment(3);

            Counter internal = registry.counter(
                    "legacy.orders.internal.debug");
            internal.increment(9);

            Counter outside = registry.counter("other.events");
            outside.increment(7);

            System.out.println("name=" + first.getId().getName());
            System.out.println("outcome=" + first.getId().getTag("outcome"));
            System.out.println("request.id="
                    + first.getId().getTag("request.id"));
            System.out.println("same-counter=" + (first == second));
            System.out.println("merged-count=" + first.count());
            System.out.println("internal-count=" + internal.count());
            System.out.println("outside-count=" + outside.count());

            System.out.println("original-name-present="
                    + (registry.find("legacy.orders.processed")
                            .counter() != null));
            System.out.println("mapped-name-present="
                    + (registry.find("shop.orders.processed")
                            .tag("outcome", "success").counter() != null));
            System.out.println("meters=" + registry.getMeters().size());
        } finally {
            registry.close();
        }
    }
}
```

Hai lần đăng ký có request ID khác nhau nhưng sau ánh xạ đều thành cùng tên/tag:

```text
shop.orders.processed{outcome=success}
```

Vì cùng là Counter cho cùng một đại lượng, chúng dùng chung đối tượng; số lần ghi được cộng vào Counter đó.

Meter nội bộ được đổi tên sang `shop.orders.internal.debug`, rồi bị quy tắc từ chối nhận diện bằng tên mới. Meter `other.events` không được ACCEPT và bị quy tắc DENY cuối cùng từ chối.

**Danh sách chỉ cho phép trong thí nghiệm là một lựa chọn có chủ đích cho registry này.** Không đưa nguyên quy tắc `deny()` cuối cùng vào một ứng dụng Boot đang cần JVM/HTTP metrics rồi mong các nhóm ngoài `shop.` vẫn còn được đăng ký.

### Dependency và lệnh chạy

Ví dụ độc lập dùng JDK 17+ và Micrometer 1.13.0. Tạo `pom.xml` tại thư mục gốc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-filter-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Cần Maven trong PATH; lần đầu tải dependency cần kết nối Maven Central. Chạy tại thư mục chứa `pom.xml`.

PowerShell trên Windows:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/filter/OrderMetricFilters.java src/example/filter/MeterFilterDemo.java
java -cp "out;lib/*" example.filter.MeterFilterDemo
```

Trên Linux/macOS, dùng dấu `:` trong classpath của lệnh chạy:

```bash
java -cp "out:lib/*" example.filter.MeterFilterDemo
```

Stdout:

```text
name=shop.orders.processed
outcome=success
request.id=null
same-counter=true
merged-count=5.0
internal-count=0.0
outside-count=0.0
original-name-present=false
mapped-name-present=true
meters=1
```

`request.id=null` biểu thị khóa nhãn không còn trong ID, không phải có một tag mang chuỗi giá trị `"null"`.

Trong Micrometer 1.13.0, registry có `close()` nhưng không triển khai `AutoCloseable`, nên ví dụ đóng nó bằng `finally`.

## 7. Meter bị từ chối vẫn có thể có đối tượng trả về

Khi filter trả DENY, Micrometer thường trả một phép đo NOOP, chẳng hạn `NoopCounter`. Mã nghiệp vụ vẫn có thể gọi `increment` trên đối tượng này, nhưng không ghi được số liệu như một Counter thực.

Trong chương trình trên, `internal` và `outside` đều khác null. Tuy nhiên:

- Giá trị đọc của các NOOP Counter trong thí nghiệm là `0.0`.
- Registry chỉ có một Counter được chấp nhận.
- Không có phép đo nội bộ hoặc `other.events` được đăng ký.

Vì vậy, kiểm tra `counter != null` sau lời gọi đăng ký không chứng minh chính sách cho phép nó. Khi kiểm chứng filter, tìm theo định danh cuối trong registry và đối chiếu kết quả ghi nhận.

Việc chặn đăng ký cũng không tự xóa dữ liệu lịch sử đã được hệ thống giám sát nhận trước đó. Nếu chuyển chính sách ở một lần triển khai mới, cần phân biệt số liệu cũ với các phép đo hiện đang được đăng ký.

## 8. Đổi định danh có thể làm các nguồn nhập thành một

Bỏ tag hoặc đổi nhiều tên về cùng một tên có thể làm những định danh khác nhau trở thành trùng nhau.

Trong mục 6, gộp các request vào cùng Counter kết quả là chủ đích: câu hỏi cần trả lời là tổng số đơn hàng xử lý thành công, không phải mỗi request có một Counter riêng.

Nhưng không phải phép gộp nào cũng có cùng ý nghĩa.

| Loại phép đo/tình huống | Hệ quả cần kiểm tra |
| --- | --- |
| Các Counter cùng đại lượng sau khi bỏ một nhãn | Các lời gọi có thể dùng chung một Counter và cộng sự kiện vào đó |
| Hai Gauge đang đo hai đối tượng khác nhau | Không tự trở thành Gauge tính tổng của hai đối tượng |
| Hai tên về cùng ID nhưng khác loại phép đo | Có thể gặp xung đột loại khi đăng ký |
| Hai tag có cùng ý nghĩa sau chuẩn hóa | Có thể chủ đích giảm số chuỗi số liệu, nhưng cần kiểm tra cách đọc và cảnh báo |

Ví dụ minh họa Gauge trên một registry mới:

```java
registry.config().meterFilter(MeterFilter.ignoreTags("queue"));

AtomicInteger left = new AtomicInteger(2);
AtomicInteger right = new AtomicInteger(9);

Gauge a = Gauge.builder("shop.queue.depth", left, AtomicInteger::get)
        .tag("queue", "left")
        .register(registry);

Gauge b = Gauge.builder("shop.queue.depth", right, AtomicInteger::get)
        .tag("queue", "right")
        .register(registry);
```

Sau khi bỏ tag `queue`, hai lần đăng ký trùng ID. Với registry mặc định và thứ tự trên, Gauge đã có vẫn đọc nguồn `left`; không có phép cộng tự động thành 11.

Nếu cần tổng kích thước hai hàng đợi, thiết kế một nguồn/hàm tổng hợp rõ ràng thay vì dùng `ignoreTags` để mong registry tự tổng hợp.

Khi đổi khóa tag, cũng kiểm tra trường hợp ID đã chứa sẵn cả khóa cũ lẫn khóa mới. Chính sách phải có cách xử lý xung đột rõ ràng; không dùng hai khóa như thể chúng vẫn độc lập sau khi đổi về cùng một khóa.

## 9. Tích hợp trong Spring Boot Actuator

Trong Boot 3.3 có Actuator và auto-configuration metrics hoạt động, các bean `MeterFilter` được Boot gắn vào registry do Spring quản lý.

Cấu hình dưới đây dùng lại `OrderMetricFilters` ở mục 5, với thứ tự ánh xạ rõ ràng. Nó từ chối nhóm đơn hàng nội bộ và cho các nhóm khác tiếp tục đi qua chính sách còn lại của ứng dụng.

Tệp `OrderMetricsConfiguration.java`:

```java
package example.filter;

import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class OrderMetricsConfiguration {

    @Bean
    @Order(10)
    public MeterFilter renameLegacyOrders() {
        return OrderMetricFilters.renameLegacyOrders();
    }

    @Bean
    @Order(20)
    public MeterFilter renameOrderResultTag() {
        return MeterFilter.renameTag(
                "shop.orders.", "result", "outcome");
    }

    @Bean
    @Order(30)
    public MeterFilter ignoreOrderRequestId() {
        return OrderMetricFilters.ignoreOrderRequestId();
    }

    @Bean
    @Order(40)
    public MeterFilter denyInternalOrders() {
        return MeterFilter.denyNameStartsWith("shop.orders.internal.");
    }
}
```

Đây là cấu hình tích hợp vào ứng dụng Boot sẵn có, không phải ứng dụng độc lập. Package phải được quét hoặc cấu hình phải được import. Để dependency management của Boot chọn phiên bản Micrometer tương thích.

`@Order` thể hiện quan hệ giữa các filter trong ví dụ. Ứng dụng vẫn cần kiểm tra những filter hoặc quy tắc chấp nhận khác được bổ sung từ nơi khác; một ACCEPT xuất hiện sớm trong chuỗi có thể ảnh hưởng quy tắc từ chối.

Sử dụng `MeterRegistry` được inject để đăng ký phép đo nghiệp vụ. Không tạo registry riêng rồi mong các bean filter của Boot tự được áp dụng lên registry đó. Xem [tùy biến metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing).

Nếu nhu cầu chỉ là bật/tắt một tiền tố, Boot còn hỗ trợ cấu hình như:

```properties
management.metrics.enable.shop.orders.internal=false
```

Đó là một lựa chọn cho chính sách chấp nhận/từ chối theo tiền tố. Đổi tên meter hay ánh xạ tag vẫn cần cơ chế phù hợp như MeterFilter trong mã.

### Kiểm tra tên sau ánh xạ qua Actuator

Trong ứng dụng có web runtime, có thể mở endpoint chẩn đoán bằng cấu hình môi trường thực hành:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Sau khi mã nghiệp vụ của ứng dụng đã đăng ký và ghi nhận Counter đơn hàng như ví dụ, với cổng và đường dẫn Actuator mặc định:

```bash
curl "http://localhost:8080/actuator/metrics/shop.orders.processed?tag=outcome:success"
```

Dùng tên logic **sau ánh xạ** là `shop.orders.processed`, cùng tag `outcome`. Không dùng tên cũ hay khóa `result`.

Tên do exporter chuẩn hóa, chẳng hạn chuyển dấu chấm thành dấu gạch dưới khi xuất Prometheus, lại là một lớp biểu diễn khác. Truy vấn endpoint `metrics` theo tên logic trong registry.

Endpoint chỉ hiển thị các phép đo thực sự có trong ứng dụng. Cấu hình filter không tự tạo Counter hay phát sinh sự kiện. Nếu ứng dụng có xác thực, cổng quản trị hoặc đường dẫn riêng, yêu cầu cần theo cấu hình đó.

Việc expose endpoint qua HTTP cũng khác việc chấp nhận meter: mở `metrics` không làm một meter bị DENY trở thành có số liệu.

## 10. Các giới hạn và lỗi cấu hình cần nhận ra

### Cấu hình filter trước khi đăng ký các meter liên quan

Trong Java thuần, gắn filter ngay sau khi tạo registry và trước khi đăng ký. Trong Boot, ưu tiên các bean filter để cơ chế metrics thiết lập chúng đúng vòng đời.

Thêm filter sau khi đã có meter không phải một thao tác di chuyển toàn bộ phép đo cũ. Không dựa vào nó để đổi tên, gỡ hoặc cập nhật nhất quán những đối tượng đã được ứng dụng giữ tham chiếu.

Micrometer 1.13.0 có cảnh báo khi cấu hình filter muộn. Khi triển khai thay đổi tên/tag, kiểm tra kết quả trong một context mới và xem lại các truy vấn, biểu đồ, cảnh báo đang dùng định danh cũ.

### Giới hạn tag cần đứng trong chuỗi quyết định phù hợp

Ví dụ đăng ký sớm một giới hạn:

```java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "shop.orders.", "outcome", 3, MeterFilter.deny()));
```

Nó giới hạn số giá trị tag `outcome` gặp ở nhóm tên tương ứng. Nhưng nếu một filter phía trước đã trả ACCEPT cho mọi `shop.`, quy tắc giới hạn có thể không được hỏi ở giai đoạn `accept`.

Giới hạn chỉ là lớp bảo vệ bổ sung. Vẫn cần thiết kế tập tag hữu hạn và quan sát được việc số liệu bị từ chối. Không tạo giá trị tùy ý rồi chỉ trông chờ filter bỏ bớt.

### Filter phải giữ ý nghĩa của số liệu

Một phép đổi tên không nên làm hai đại lượng khác nhau trông như cùng một đại lượng. Ví dụ không đổi cả “đơn hàng nhận vào” và “đơn hàng hoàn tất” về một Counter chỉ vì muốn ít tên hơn.

Tương tự, bỏ tag có thể giúp giảm số tổ hợp nhãn nhưng cũng làm mất khả năng phân biệt nguồn. Kiểm tra ý nghĩa của phép tổng hợp trước khi triển khai.

### Phân biệt cấu hình registry với phạm vi dữ liệu khác

MeterFilter không sửa mã nghiệp vụ, log, trace hay dữ liệu lịch sử bên ngoài. Nó cũng không phải cơ chế lọc từng request trước khi nghiệp vụ xử lý.

Khi không thấy một phép đo, kiểm tra lần lượt: có đăng ký/ghi nhận chưa, tên/tag sau map là gì, filter nào quyết định accept, và registry nào đang được truy vấn.

## 11. Kiểm chứng và thực hành

| Điều cần chứng minh | Cách kiểm tra |
| --- | --- |
| Ánh xạ tên đúng phạm vi | Tên đơn hàng cũ được đổi; tên không thuộc phạm vi không bị đổi |
| Đổi khóa tag đúng | ID có `outcome`, không còn `result` |
| Bỏ tag đúng phạm vi | `request.id` vắng trên nhóm đơn hàng, không bị xóa tùy ý ở nhóm khác |
| Chuỗi từ chối đúng thứ tự | Tên nội bộ bị DENY trước quy tắc ACCEPT rộng |
| NOOP không bị nhầm với meter được đăng ký | Đối chiếu số liệu và tìm kiếm trong registry |
| Phép gộp có ý nghĩa | Hai Counter cùng đại lượng gộp được; hai Gauge không tự cộng nguồn |
| Boot đã gắn các bean filter | Tạo context có metrics auto-configuration, đăng ký qua registry được inject và tìm theo tên cuối |

Bài thực hành:

1. Chạy hai tệp Java ở mục 5–6 và đối chiếu đủ 10 dòng stdout.
2. Đổi một lần ghi `result=success` thành `result=failure`. Hai kết quả cần tạo hai Counter khác nhau theo tag `outcome`, dù đã bỏ request ID.
3. Trong một registry thử nghiệm riêng, đưa ACCEPT rộng lên trước DENY nội bộ. Kiểm tra meter nội bộ được đăng ký và giải thích vì sao.
4. Thử đặt filter đổi tên ở sau một filter ACCEPT trong danh sách. Quan sát rằng ánh xạ vẫn diễn ra trước khi xét chấp nhận; không coi thứ tự này như một chuỗi filter HTTP.
5. Chạy đoạn Gauge ở mục 8 và kiểm tra nguồn được đọc. Thay đổi riêng `right` rồi giải thích vì sao Gauge đã đăng ký đầu tiên không đổi theo nó.
6. Tích hợp cấu hình mục 9 và xác nhận các phép đo ngoài phạm vi đơn hàng vẫn có thể đăng ký theo chính sách hiện có của ứng dụng.
7. Trước khi áp dụng một filter vào hệ thống, ghi rõ: phạm vi tên, phép đổi ID, thứ tự quyết định, tác động đến số tổ hợp tag và những truy vấn cần cập nhật.

Một chính sách MeterFilter rõ ràng phải cho biết meter nào được giữ, meter nào bị từ chối, định danh cuối cùng là gì và liệu phép biến đổi có làm thay đổi ý nghĩa số liệu hay không.
