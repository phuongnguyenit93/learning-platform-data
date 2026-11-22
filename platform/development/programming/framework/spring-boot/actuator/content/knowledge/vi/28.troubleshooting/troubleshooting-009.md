# Chẩn đoán Gauge bị mất dữ liệu và số lượng meter tăng không kiểm soát

## 1. Tách hai loại sự cố trước khi sửa

Một Gauge đọc **giá trị hiện tại** từ một đối tượng. MeterRegistry lưu các meter đã đăng ký, còn hệ thống giám sát bên ngoài lưu các chuỗi thời gian được xuất từ chúng. Ba lớp này liên quan nhưng không phải một thứ.

Hai hiện tượng trong đề bài có thể xảy ra đồng thời:

- Gauge trở thành `NaN`, đứng ở giá trị cũ hoặc không xuất hiện trên biểu đồ.
- Số meter trong tiến trình hoặc số chuỗi thời gian ở hệ thống giám sát tăng liên tục.

Đừng mặc định cả hai đều do “Micrometer mất dữ liệu”. Hãy xác định đối tượng được đo còn tồn tại không, meter nào đang được đọc và bộ tên/tag nào đang được tạo.

| Dấu hiệu | Câu hỏi chẩn đoán đầu tiên |
| --- | --- |
| Có giá trị lúc đầu, sau đó NaN hoặc biến mất | Ai đang giữ đối tượng được Gauge quan sát? |
| Thay đối tượng nhưng Gauge vẫn đọc giá trị cũ | Có đăng ký lại cùng ID không? |
| Không thấy một đỉnh ngắn trên biểu đồ | Gauge có được lấy mẫu đúng lúc đỉnh xảy ra không? |
| Số meter tăng theo số yêu cầu | Tên hoặc tag có chứa dữ liệu riêng của từng yêu cầu không? |
| Registry đọc được nhưng hệ thống giám sát không có | Kiểm tra xuất dữ liệu, thu thập và truy vấn |
| Không thấy meter mới sau khi thêm bộ lọc | Meter có bị từ chối đăng ký không? |

Bài dùng **Java 21, Spring Boot 3.3.13 và Micrometer 1.13.15**. Chương trình ở mục 6 kiểm tra trực tiếp bằng `SimpleMeterRegistry`; nó không cần máy chủ HTTP hay Prometheus.

## 2. Gauge không mặc nhiên sở hữu đối tượng được đo

### 2.1. Phân biệt giữ Gauge với giữ dữ liệu nguồn

Với kiểu đăng ký đối tượng và hàm đọc thông thường, Gauge mặc định giữ tham chiếu yếu tới đối tượng được quan sát. Nếu ứng dụng không giữ đối tượng đó sống, bộ gom rác có thể thu hồi nó. Tùy registry, kết quả sau đó có thể là `NaN` hoặc không còn mẫu được xuất. Đây là hành vi được mô tả trong [tài liệu Gauge của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Mảnh mã có vấn đề:

```java
void registerQueueDepth(MeterRegistry registry) {
    var depth = new AtomicInteger(0);
    Gauge.builder("app.queue.depth", depth, AtomicInteger::get)
            .tag("queue", "mail")
            .register(registry);
}
```

Đây là mảnh minh họa, cần các import Micrometer và `AtomicInteger`. Sau khi phương thức kết thúc, không còn chủ sở hữu lâu dài nào giữ `depth`. Không có bảo đảm rằng lỗi xuất hiện ngay; thời điểm thu gom không xác định.

Giữ biến tham chiếu đến **Gauge** chưa chắc giữ được **đối tượng mà Gauge đo**. Cần xem quan hệ sở hữu dữ liệu, không chỉ xem meter đã được đăng ký hay chưa.

Tham chiếu yếu không ngăn đối tượng bị thu hồi; xem [WeakReference trong Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html). Không dùng một lần `System.gc()` rồi chờ vài mili giây để khẳng định chắc chắn thời điểm Gauge sẽ mất giá trị.

### 2.2. Giữ trạng thái ở đối tượng có vòng đời phù hợp

Ví dụ component trong một ứng dụng Spring Boot đã có Actuator:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
public final class QueueDepthMetrics {
    private final AtomicInteger depth = new AtomicInteger();

    public QueueDepthMetrics(MeterRegistry registry) {
        Gauge.builder("app.queue.depth", depth, AtomicInteger::get)
                .tag("queue", "mail")
                .register(registry);
    }

    public void updateDepth(int currentDepth) {
        depth.set(currentDepth);
    }
}
```

Lưu component ở file `QueueDepthMetrics.java` trong package được Spring quét. Đây là component tích hợp, không phải chương trình có `main` chạy độc lập.

Bean giữ `depth` bằng một trường `final`; mã cập nhật cùng đối tượng đó. Ứng dụng phải gọi `updateDepth` từ nơi biết kích thước hàng đợi thực tế. Gauge không tự suy ra công việc trong hàng đợi từ tên metric.

Nếu đã có một đối tượng hàng đợi sống lâu, có thể đo trực tiếp kích thước của nó thay vì duy trì một biến đếm phụ có nguy cơ lệch với trạng thái thật. Hàm đọc nên nhanh, an toàn khi truy cập đồng thời và không thực hiện truy vấn mạng nặng cho mỗi lần lấy mẫu.

Builder cũng có tùy chọn `strongReference(true)` để giữ đối tượng được đo. Đó là lựa chọn về vòng đời: đối tượng có thể bị giữ lâu cùng meter. Không bật tùy chọn này trên hàng loạt đối tượng ngắn hạn có ID không giới hạn rồi bỏ qua việc dọn dẹp.

### 2.3. NaN không chỉ có một nguyên nhân

Một đối tượng còn sống vẫn có thể tạo `NaN` nếu chính phép tính trả về giá trị đó. Chẳng hạn, phép chia số thực `0.0 / 0` cho kết quả `NaN`; chương trình ở mục 6 kiểm tra trường hợp này.

Khi gặp NaN, kiểm tra lần lượt:

1. Đối tượng nguồn còn được giữ sống không?
2. Hàm đọc có tạo ra giá trị không xác định, chẳng hạn mẫu số bằng 0 không?
3. Có lỗi trong hàm đo hoặc log chẩn đoán liên quan không?
4. Bạn đang đọc đúng bộ tag, đúng registry và đúng tiến trình chưa?

Không thay tất cả NaN bằng 0 trên dashboard trước khi hiểu nguyên nhân. “Không có số đo hợp lệ” khác với “hàng đợi đang rỗng”.

## 3. Đăng ký lại cùng ID không thay đối tượng nguồn

Trong một registry, tên và bộ tag xác định danh tính meter. Đăng ký lại cùng ID không tạo một Gauge mới để tự động theo dõi đối tượng thay thế. Cơ chế giữ lần đăng ký đầu có thể đối chiếu trong [MeterRegistry 1.13.15](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

Ví dụ:

```java
var firstState = new AtomicInteger(7);
Gauge first = Gauge.builder("app.queue.depth", firstState, AtomicInteger::get)
        .tag("queue", "mail")
        .register(registry);

var newState = new AtomicInteger(99);
Gauge second = Gauge.builder("app.queue.depth", newState, AtomicInteger::get)
        .tag("queue", "mail")
        .register(registry);
```

Cả hai lần có cùng tên và tag. Trong thí nghiệm với `SimpleMeterRegistry`, `first == second` là `true`; Gauge tiếp tục đọc `firstState`.

Hệ quả thực tế:

- Gán trường của ứng dụng sang một `AtomicInteger` mới không tự đổi đối tượng Gauge đã ghi nhận.
- Đăng ký lại sau mỗi lần cập nhật có thể không làm giá trị đổi như bạn nghĩ.
- Đăng ký lại cùng ID không nhất thiết làm số meter tăng; nguyên nhân tăng thường là **ID thực sự khác nhau**.
- Nếu cần thay đối tượng, ưu tiên một chủ sở hữu ổn định có thể cung cấp giá trị hiện tại, hoặc thực hiện tháo/đăng ký lại có kiểm soát theo vòng đời.

Đừng “sửa” việc đăng ký trùng bằng cách thêm UUID hay timestamp vào tag. Cách đó né trùng ID bằng cách tạo vô hạn ID mới và chuyển lỗi giá trị sang lỗi số lượng meter.

Cũng tránh dùng cùng ID cho những loại meter hoặc ý nghĩa đo khác nhau. Một ID phải đại diện cho một phép đo rõ ràng.

## 4. Gauge có thể bỏ qua đỉnh ngắn mà không bị hỏng

Giả sử giữa hai lần đọc, biến lần lượt có giá trị:

```text
0 -> 20 -> 0
```

Nếu lần đọc kế tiếp xảy ra ở cuối, Gauge báo 0. Nó không lưu lịch sử mọi lần cập nhật và không tự nhớ đỉnh 20.

Trong chương trình ở mục 6, hai lệnh `set(20)` rồi `set(0)` được thực hiện trước khi đọc Gauge. Kết quả là 0.0.

Chọn loại meter theo câu hỏi:

| Câu hỏi | Công cụ phù hợp thường gặp |
| --- | --- |
| Hiện có bao nhiêu phần tử đang chờ? | Gauge |
| Tổng cộng đã nhận bao nhiêu yêu cầu? | Counter |
| Thời gian xử lý từng công việc như thế nào? | Timer |
| Phân bố kích thước các đối tượng đã xử lý? | DistributionSummary |

Giảm chu kỳ thu thập có thể tăng cơ hội thấy biến động, nhưng không biến Gauge thành bộ lưu mọi sự kiện. Nếu cần số sự kiện hoặc phân bố, sửa cách đo thay vì chỉ tăng tần suất thu thập.

## 5. Vì sao số lượng meter tăng không kiểm soát?

### 5.1. Mỗi bộ giá trị tag mới tạo thêm danh tính

Các ID sau khác nhau:

```text
app.queue.depth{queue=mail}
app.queue.depth{queue=image}
app.queue.depth{queue=mail,requestId=request-1}
app.queue.depth{queue=mail,requestId=request-2}
```

Dù tên metric chỉ có một, số meter có thể rất lớn. Cardinality là số lượng giá trị hoặc tổ hợp định danh khác nhau của các chiều dữ liệu.

Prometheus cũng tạo chuỗi thời gian riêng cho các bộ nhãn khác nhau; nhiều chiều có thể nhân số tổ hợp. Xem [Cardinality matters](https://prometheus.io/docs/practices/the_zen/#cardinality-matters).

Ví dụ tính ngân sách, với một phép đo có:

```text
4 queue x 3 state x 2 region = tối đa 24 tổ hợp
```

Đây là số tổ hợp có thể có trong mô hình ví dụ, không khẳng định mọi tổ hợp đã xuất hiện. Nếu thêm `requestId` mới cho từng yêu cầu, miền giá trị không còn bị chặn bởi 24.

### 5.2. Những nguồn ID không giới hạn

| Cách gắn dữ liệu | Vấn đề | Hướng thay thế |
| --- | --- | --- |
| Tag `requestId`, `traceId`, `userId`, `orderId` | Miền giá trị tăng theo hoạt động | Đưa định danh vào log/trace; metric dùng nhóm hữu hạn |
| Tag chứa URL nguyên bản có ID hoặc query | Mỗi URL có thể thành một giá trị mới | Dùng mẫu route như `/orders/{id}` nếu phù hợp |
| Tag chứa thông báo lỗi nguyên văn | Thông báo có thể chứa ID và dữ liệu động | Dùng mã lỗi hoặc loại lỗi được phân loại |
| Tên metric chứa UUID/timestamp | Số tên cũng tăng vô hạn | Giữ tên cố định, thiết kế chiều dữ liệu có giới hạn |
| Meter cho từng đối tượng ngắn hạn, không tháo | Registry tích lũy ID qua thời gian | Tổng hợp theo nhóm hoặc quản lý vòng đời rõ ràng |

Băm `userId` thành một chuỗi khác không làm giảm số giá trị khác nhau. Cắt ngắn chuỗi tùy tiện có thể tạo va chạm mà vẫn không đưa ra một ngân sách có ý nghĩa.

Với ứng dụng HTTP, cần kiểm tra tag route thực tế, nhất là lỗi không tìm thấy route hoặc các điểm tự ghi metric. Đừng chỉ nhìn tên tag `uri` rồi giả định giá trị đã được chuẩn hóa.

### 5.3. Phân biệt meter trong JVM với chuỗi thời gian ở hệ thống giám sát

Hai số đo sau không phải lúc nào cũng bằng nhau:

- Số meter trong một `MeterRegistry` của một tiến trình.
- Số chuỗi thời gian đang được lưu hoặc truy vấn trong hệ thống giám sát.

Hệ thống bên ngoài còn có nhãn instance/job/Pod, nhiều replica và dữ liệu từ các phiên bản triển khai trước. Một meter kiểu Timer hoặc histogram cũng có thể được xuất thành nhiều chuỗi.

Vì vậy, cần đo đúng phạm vi. `/actuator/metrics` liệt kê tên không phải là phép đếm đầy đủ mọi tổ hợp meter. Một tên đứng yên vẫn có thể chứa hàng nghìn bộ tag.

## 6. Chương trình chạy được để phân biệt các hành vi

Ví dụ sau không mở web server. Nó dùng thư viện do Spring Boot quản lý phiên bản để kiểm tra Gauge trong bộ nhớ, tách khỏi các vấn đề thu thập dữ liệu bên ngoài.

Cây file:

```text
gauge-diagnostics/
├── pom.xml
└── src/main/
    ├── java/example/GaugeDiagnostics.java
    └── resources/logback.xml
```

Nội dung đầy đủ `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>gauge-diagnostics</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung đầy đủ `src/main/java/example/GaugeDiagnostics.java`:

```java
package example;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class GaugeDiagnostics {
    public static void main(String[] args) {
        var registry = new SimpleMeterRegistry();
        var limited = new SimpleMeterRegistry();
        try {

            var depth = new AtomicInteger(4);
            Gauge first = Gauge.builder("lab.queue.depth", depth, AtomicInteger::get)
                    .tag("queue", "mail")
                    .register(registry);
            depth.set(7);
            System.out.println("current=" + first.value());

            var replacement = new AtomicInteger(99);
            Gauge second = Gauge.builder("lab.queue.depth", replacement, AtomicInteger::get)
                    .tag("queue", "mail")
                    .register(registry);
            replacement.set(100);
            System.out.println("sameGauge=" + (first == second));
            System.out.println("afterReplacement=" + second.value());
            System.out.println("stableMeters=" + count(registry, "lab.queue.depth"));

            depth.set(20);
            depth.set(0);
            System.out.println("afterSpike=" + first.value());

            Gauge retained = Gauge.builder("lab.retained.depth",
                    new AtomicInteger(9), AtomicInteger::get)
                    .strongReference(true).register(registry);
            if (retained.value() != 9.0) {
                throw new IllegalStateException("Unexpected retained gauge value");
            }

            var denominator = new AtomicInteger(0);
            Gauge ratio = Gauge.builder("lab.ratio", denominator,
                    value -> 0.0 / value.get()).register(registry);
            System.out.println("ratioIsNaN=" + Double.isNaN(ratio.value()));

            var requestStates = new ArrayList<AtomicInteger>();
            for (int i = 0; i < 5; i++) {
                var state = new AtomicInteger(i);
                requestStates.add(state);
                Gauge.builder("lab.bad.depth", state, AtomicInteger::get)
                        .tag("requestId", "request-" + i)
                        .register(registry);
            }
            System.out.println("unboundedPatternMeters=" + count(registry, "lab.bad.depth"));

            limited.config().meterFilter(MeterFilter.maximumAllowableTags(
                    "lab.limited.depth", "queue", 2, MeterFilter.deny()));
            var boundedStates = List.of(
                    new AtomicInteger(1),
                    new AtomicInteger(2),
                    new AtomicInteger(3));
            var queues = List.of("mail", "image", "video");
            for (int i = 0; i < queues.size(); i++) {
                Gauge.builder("lab.limited.depth", boundedStates.get(i), AtomicInteger::get)
                        .tag("queue", queues.get(i))
                        .register(limited);
            }
            System.out.println("limitedMeters=" + count(limited, "lab.limited.depth"));
            System.out.println("videoRegistered=" +
                    (limited.find("lab.limited.depth").tag("queue", "video").gauge() != null));

            registry.remove(first);
            System.out.println("afterRemove=" + count(registry, "lab.queue.depth"));

            Reference.reachabilityFence(depth);
            Reference.reachabilityFence(replacement);
            Reference.reachabilityFence(denominator);
            Reference.reachabilityFence(requestStates);
            Reference.reachabilityFence(boundedStates);
        } finally {
            registry.close();
            limited.close();
        }
    }

    private static int count(MeterRegistry registry, String name) {
        return registry.find(name).meters().size();
    }
}
```

Nội dung `src/main/resources/logback.xml`:

```xml
<configuration>
    <root level="OFF"/>
</configuration>
```

Cấu hình logging này chỉ giúp thí nghiệm có stdout xác định, không phải khuyến nghị tắt log chẩn đoán của ứng dụng thật.

Dùng JDK 21 và Maven, chạy từ thư mục chứa `pom.xml`:

```shell
mvn package
java -jar target/gauge-diagnostics-1.0.0.jar
```

Maven biên dịch với classpath thư viện và đóng gói JAR thực thi. Không chạy riêng `javac GaugeDiagnostics.java` khi chưa chuẩn bị các phụ thuộc.

Stdout chính xác:

```text
current=7.0
sameGauge=true
afterReplacement=7.0
stableMeters=1
afterSpike=0.0
ratioIsNaN=true
unboundedPatternMeters=5
limitedMeters=2
videoRegistered=false
afterRemove=0
```

Giải thích:

- `current`: cập nhật đúng đối tượng nguồn làm Gauge thay đổi.
- `sameGauge`, `afterReplacement`, `stableMeters`: cùng ID vẫn là Gauge đầu tiên và chỉ có một meter cho tên đang xét.
- `afterSpike`: đỉnh giữa các lần quan sát không được Gauge tích lũy.
- `ratioIsNaN`: một phép tính có thể sinh NaN dù đối tượng nguồn còn sống.
- `unboundedPatternMeters`: năm giá trị `requestId` tạo năm meter; số 5 chỉ giới hạn vòng lặp của thí nghiệm.
- `limitedMeters`, `videoRegistered`: bộ lọc chấp nhận hai giá trị tag rồi từ chối giá trị thứ ba.
- `afterRemove`: tháo Gauge làm ID tương ứng không còn trong registry của thí nghiệm.

`Reference.reachabilityFence` giữ rõ vòng đời các đối tượng tới cuối phép kiểm chứng; trong ứng dụng, cơ chế sở hữu thường là bean hoặc đối tượng nghiệp vụ sống lâu. Chương trình không dự đoán thời điểm GC và không tạo ra một phép thử GC có stdout giả định.

Phép kiểm tra `retained.value()` cũng xác nhận tùy chọn `strongReference(true)` dùng được với phiên bản thư viện của ví dụ.

## 7. Giới hạn tag là biện pháp bảo vệ, không phải phép tổng hợp

Trong thí nghiệm:

```java
limited.config().meterFilter(MeterFilter.maximumAllowableTags(
        "lab.limited.depth", "queue", 2, MeterFilter.deny()));
```

Đây là mảnh lấy từ chương trình đầy đủ. Nó đặt giới hạn số giá trị khác nhau của tag `queue` cho các tên bắt đầu bằng tiền tố đó trong registry đang cấu hình.

Điều cần phân biệt:

- Giới hạn 2 là để minh họa, không phải ngưỡng chung cho ứng dụng thật.
- Bộ lọc không cộng giá trị của meter bị từ chối vào meter đã có.
- Meter bị từ chối không tự xuất hiện trong registry chỉ vì mã đăng ký không ném lỗi.
- Một tag được giới hạn không làm các tag còn lại tự bị giới hạn.
- Bộ lọc không tự dọn những ID đã tích lũy trước đó.

API còn có `maximumAllowableMetrics` để đặt giới hạn rộng hơn. Cần hiểu phạm vi và thứ tự các filter trước khi dùng, đặc biệt các quy tắc `ACCEPT` có thể ảnh hưởng việc xét các filter sau. Đối chiếu [Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) và [mã nguồn MeterFilter 1.13.15](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

Ví dụ cấu hình bảo vệ trong Spring Boot:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class QueueMetricConfiguration {
    @Bean
    MeterFilter queueTagLimit() {
        return MeterFilter.maximumAllowableTags(
                "app.queue.depth", "queue", 20, MeterFilter.deny());
    }
}
```

Đặt lớp này trong package cấu hình được quét. Giá trị 20 là ngân sách minh họa cần thay bằng quyết định thiết kế thực tế. Các tag khác vẫn cần ngân sách riêng.

Trong ứng dụng Spring, dùng `MeterRegistry` được Spring quản lý và đăng ký filter từ giai đoạn cấu hình, trước khi tạo metric liên quan. Đừng giả định một registry tự tạo bằng `new` hoặc một đường đăng ký tĩnh đã nhận đúng các filter của bean Spring. Xem [custom metrics và MeterFilter của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing).

### Không gộp tag Gauge mà quên gộp dữ liệu

Bỏ tag `queue` hoặc đổi mọi giá trị thành `all` có thể làm nhiều Gauge trở thành cùng ID. Điều đó không có nghĩa registry tự tính tổng kích thước các hàng đợi; Gauge đăng ký trước có thể tiếp tục quyết định giá trị.

Nếu cần tổng số phần tử, thiết kế **một đối tượng/hàm đọc giá trị tổng** rồi đăng ký một Gauge tổng. Nếu cần phân biệt một tập hàng đợi hữu hạn, giữ chiều `queue` với tập giá trị được quản lý.

Tương tự, bộ nhớ đệm giữ `AtomicInteger` cho mọi ID giúp tránh mất đối tượng do GC nhưng sẽ thành một nguồn giữ bộ nhớ nếu ID không giới hạn. Sửa vòng đời và sửa cardinality phải đi cùng nhau.

## 8. Quy trình chẩn đoán trên ứng dụng đang chạy

### Bước 1: Xác định nơi dữ liệu bắt đầu sai

Phân biệt bốn điểm:

```text
đối tượng nghiệp vụ
    -> Gauge.value() trong registry đúng
    -> dữ liệu được xuất/thu thập
    -> truy vấn và biểu đồ
```

Ghi lại tên metric, tag, instance/Pod và thời điểm. Một biểu đồ trống có thể do bộ lọc truy vấn hoặc phạm vi thời gian; chưa đủ để kết luận đối tượng bị GC.

### Bước 2: Kiểm tra danh tính và giá trị ngay trong registry

Mảnh chẩn đoán cho một registry đã được inject:

```java
int totalMeters = registry.getMeters().size();
int queueMeters = registry.find("app.queue.depth").meters().size();
Gauge mail = registry.find("app.queue.depth").tag("queue", "mail").gauge();
```

Nếu `mail` là `null`, kiểm tra việc đăng ký, tag, filter và registry đang dùng trước khi đọc giá trị. Nếu có Gauge, so sánh đối tượng nguồn thực tế với `mail.value()`.

Không đưa mọi ID/tag lên log trong vòng lặp tải cao chỉ để chẩn đoán cardinality; lấy mẫu và đếm theo tên hoặc khóa tag sẽ dễ kiểm soát hơn.

### Bước 3: Dùng Actuator đúng mục đích

Trong một ứng dụng web đã có Actuator, có thể công bố riêng endpoint chẩn đoán theo chính sách truy cập đang dùng:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Ví dụ gọi ứng dụng ở cổng 8080:

```shell
curl -sS http://localhost:8080/actuator/metrics
curl -sS -G --data-urlencode "tag=queue:mail" http://localhost:8080/actuator/metrics/app.queue.depth
```

Trên Windows PowerShell có thể dùng `curl.exe` để tránh alias. Điều chỉnh URL theo cổng, context path và thông tin xác thực thực tế.

Dùng tên Micrometer như `app.queue.depth` khi gọi endpoint này. API metrics phục vụ chẩn đoán, hỗ trợ lọc bằng `tag=key:value`; không dùng nó thay hệ thống thu thập metric sản xuất. Xem [API metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Nếu truy vấn chưa chọn đủ tag, bạn có thể đang xem nhiều meter cùng tên được tổng hợp. Khi cần đối chiếu một nguồn đo, lọc đúng ID thay vì chỉ so tên.

### Bước 4: Đối chiếu dữ liệu xuất và hệ thống bên ngoài

Nếu dùng Prometheus, cần registry Prometheus và endpoint công bố phù hợp; endpoint `metrics` có dữ liệu không tự chứng minh dữ liệu đã được Prometheus thu thập.

Kiểm tra đúng target/instance, tên sau quy ước xuất, lần thu thập gần nhất và truy vấn. Ví dụ, với tên xuất thực tế là `app_queue_depth`, có thể đếm các chuỗi hiện diện bằng:

```promql
count(app_queue_depth)
count by (queue) (app_queue_depth)
```

Đây là phép đếm theo phạm vi truy vấn tại thời điểm đánh giá, không phải số meter lịch sử trong một JVM. Phân biệt truy vấn tức thời với truy vấn theo khoảng thời gian; xem [Prometheus querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/).

Tháo meter trong JVM không đồng nghĩa xóa lịch sử đã lưu ở hệ thống bên ngoài. Sau khi sửa, kiểm tra cả tốc độ tạo ID mới và quá trình dữ liệu cũ hết hiệu lực theo hệ thống đang dùng.

### Bước 5: Kiểm tra quyền sở hữu và vòng đời

Tìm điểm đăng ký Gauge trong constructor, binder, request handler hoặc tác vụ định kỳ. Với từng Gauge quan trọng, trả lời:

- Đối tượng nào được đo?
- Ai giữ nó sống và trong bao lâu?
- Giá trị được cập nhật trên cùng đối tượng hay thay bằng đối tượng khác?
- Meter được đăng ký một lần hay liên tục?
- Nếu tài nguyên biến mất, ai tháo meter?

GC của đối tượng nguồn không phải hợp đồng tự động xóa mọi ID đã đăng ký. Khi cần quản lý tài nguyên động, chủ sở hữu phải quản lý cả đối tượng nguồn lẫn meter tương ứng.

### Bước 6: Kiểm tra tốc độ tạo danh tính mới

Theo dõi số meter theo tên qua thời gian và thống kê số giá trị khác nhau của từng tag. So sánh với số queue, vùng, trạng thái hoặc loại nghiệp vụ thực sự cần phân biệt.

Nếu số meter tăng gần theo số yêu cầu dù tài nguyên nghiệp vụ ổn định, tìm dữ liệu theo yêu cầu trong tên/tag. Nếu số meter JVM ổn định nhưng chuỗi bên ngoài tăng, kiểm tra replica, nhãn hạ tầng và thay đổi định danh qua các lần triển khai.

## 9. Sửa đúng nguyên nhân, tránh tạo lỗi thứ hai

| Cách sửa hấp tấp | Rủi ro | Cách làm có cơ sở |
| --- | --- | --- |
| Tạo tag UUID mới để Gauge chịu cập nhật | Số meter tăng liên tục | Cập nhật đối tượng ổn định của ID đúng |
| Giữ mọi đối tượng trong Map vô hạn | Hết NaN nhưng tăng bộ nhớ | Quản lý tập tài nguyên và vòng đời có giới hạn |
| Bỏ tag của nhiều Gauge rồi mong được tổng | Trùng ID, giá trị có thể chỉ từ nguồn đầu | Tính tổng dữ liệu trước khi đo |
| Tăng tần suất thu thập để sửa NaN | Không khôi phục đối tượng đã mất | Sửa quyền sở hữu hoặc hàm đo |
| Tăng giới hạn tag khi chạm trần | Dời sự cố tới ngưỡng cao hơn | Sửa miền giá trị và theo dõi meter bị từ chối |
| Đổi mọi dữ liệu thiếu thành 0 | Che lỗi đo lường | Phân biệt giá trị 0 với thiếu số đo |

Sau sửa, kiểm chứng ít nhất hai điều độc lập: Gauge theo dõi đúng nguồn qua nhiều lần cập nhật, và số ID không tăng ngoài ngân sách khi tải yêu cầu tăng. Nếu có tài nguyên động hợp lệ, kiểm tra thêm việc tháo meter khi tài nguyên kết thúc.

## 10. Tự kiểm tra

**A. Sau một thời gian Gauge thành NaN, nhưng ứng dụng vẫn giữ biến Gauge. Đủ để loại trừ GC chưa?**

Chưa. Cần kiểm tra đối tượng nguồn mà Gauge đo còn được giữ bằng tham chiếu mạnh không.

**B. Cùng tên/tag được đăng ký với AtomicInteger mới, giá trị vẫn cũ.**

Registry có thể đang dùng Gauge của lần đăng ký đầu. Cập nhật đúng đối tượng hoặc quản lý thay thế theo vòng đời; đừng thêm ID ngẫu nhiên.

**C. Chỉ có một tên metric nhưng JVM có hàng nghìn meter cho tên đó.**

Kiểm tra các bộ tag. Số tên không phải số tổ hợp ID.

**D. Bỏ tag queue khỏi ba Gauge có tự tạo Gauge tổng không?**

Không. Cần một hàm đọc tổng hoặc dữ liệu tổng được duy trì đúng; việc làm các ID trùng nhau không tự cộng nguồn đo.

**E. Gauge trả 0 sau khi biến từng lên 20 rồi về 0 trước lúc đọc.**

Đó là hành vi lấy giá trị hiện tại. Nếu cần ghi nhận mọi sự kiện hoặc phân bố, chọn loại meter phù hợp hơn.

**F. Sau khi đặt giới hạn tag, metric của queue mới không xuất hiện nhưng chương trình không ném lỗi.**

Kiểm tra quyết định của MeterFilter. Meter có thể đã bị từ chối; bộ lọc không tự gom dữ liệu đó vào queue khác.
