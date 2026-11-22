# Đăng ký Gauge và quản lý vòng đời đối tượng được quan sát

## 1. Gauge đo điều gì trong metrics tùy chỉnh?

Giả sử ứng dụng gửi email qua một hàng đợi có sức chứa 100 tác vụ. Người vận hành muốn biết **hiện có bao nhiêu tác vụ đang chờ**, thay vì chỉ biết từ lúc khởi động đã tiếp nhận bao nhiêu tác vụ. Đây là một đại lượng phù hợp với `Gauge`: giá trị tăng khi thêm việc và giảm khi lấy việc ra.

Trong Micrometer, cần phân biệt ba thành phần:

- **Đối tượng được quan sát**: hàng đợi, bộ nhớ đệm hoặc một đối tượng chứa số liệu hiện tại.
- **Hàm đọc**: lấy một số từ đối tượng đó, chẳng hạn `BlockingQueue::size`.
- **Gauge**: phép đo đã đăng ký trong `MeterRegistry`, gắn tên và các nhãn phân loại (tag) với hàm đọc.

Hãy hình dung việc đăng ký Gauge như đặt một đồng hồ cạnh hàng đợi: đồng hồ phải biết đọc hàng đợi nào, còn ứng dụng phải bảo đảm hàng đợi ấy còn tồn tại trong thời gian cần đo.

| Câu hỏi cần trả lời | Loại phép đo phù hợp |
| --- | --- |
| Hiện có bao nhiêu tác vụ đang chờ? | Gauge đọc kích thước hàng đợi |
| Tổng cộng đã nhận bao nhiêu tác vụ? | Counter |
| Một tác vụ xử lý mất bao lâu? | Timer |
| Đã xử lý bao nhiêu tác vụ trong khoảng thời gian? | Dữ liệu tích lũy từ Counter hoặc số lần ghi nhận của Timer, kết hợp truy vấn tại hệ thống giám sát |

Bài này tập trung vào quan hệ giữa **đăng ký phép đo, tham chiếu đến đối tượng và kết thúc vòng đời**. Không cần tạo API nghiệp vụ chỉ để chứng minh Gauge.

## 2. Gauge đọc giá trị lúc được quan sát

Một Gauge thông thường không lưu lại toàn bộ những lần đối tượng thay đổi. Khi phép đo được đọc, hàm đã đăng ký được gọi để lấy giá trị hiện tại.

Ví dụ, kích thước hàng đợi lần lượt là:

```text
Lúc đọc thứ nhất:             1
Giữa hai lần đọc:             2 -> 3 -> 2
Lúc đọc thứ hai:              1
```

Nếu chỉ đọc ở đầu và cuối, người quan sát nhận được `1` và `1`. Không thể suy ra rằng hàng đợi chưa từng có ba phần tử. Muốn biết tổng lượng công việc đi qua hệ thống hoặc độ trễ xử lý, cần phép đo bổ sung phù hợp.

Đăng ký Gauge cũng không tạo một luồng nền riêng cho từng phép đo. Thời điểm lấy mẫu phụ thuộc cơ chế đọc/xuất của registry và hệ thống giám sát. Trong ví dụ dùng `SimpleMeterRegistry` bên dưới, chương trình chủ động gọi `value()` để kiểm chứng.

Vì hàm đọc có thể chạy đồng thời với luồng nghiệp vụ, đối tượng và cách đọc phải phù hợp với truy cập đồng thời. Dùng một collection thông thường rồi chỉ bọc nó trong Gauge không làm collection đó an toàn hơn. Với một nguồn số đơn giản, `AtomicInteger` hoặc `AtomicLong` thường thuận tiện; với hàng đợi, hãy dùng kiểu hàng đợi phù hợp và đọc chính trạng thái mà nghiệp vụ sử dụng.

Tài liệu [Micrometer 1.13 về Gauge](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html) mô tả mô hình lấy mẫu và các dạng nguồn dữ liệu có thể quan sát.

## 3. Đăng ký đúng nguồn dữ liệu

### 3.1. Builder trả về Gauge

Đoạn sau minh họa phần đăng ký, chưa phải chương trình chạy độc lập:

```java
AtomicInteger pending = new AtomicInteger(0);

Gauge gauge = Gauge.builder("demo.jobs.pending", pending, AtomicInteger::get)
        .tag("queue", "email")
        .description("Số tác vụ đang chờ trong hàng đợi email")
        .register(registry);

pending.set(7);
double current = gauge.value(); // 7.0 tại thời điểm đọc này
```

Ở đây, `pending` chứa trạng thái có thể thay đổi. `gauge` đại diện phép đo. Muốn thay đổi trạng thái, cập nhật `pending`; không gọi một phương thức `set()` trên Gauge.

Với một hàng đợi thật, ưu tiên đo trực tiếp `queue.size()` thay vì duy trì thêm một biến đếm riêng nếu không cần thiết. Một biến đếm thứ hai có thể lệch với hàng đợi khi thao tác thêm thất bại, lấy việc bị hủy hoặc nhánh xử lý lỗi quên cập nhật.

### 3.2. Phương thức tiện ích có kiểu trả về khác

```java
AtomicInteger pending = registry.gauge(
        "demo.jobs.pending", new AtomicInteger(0));

pending.set(7);
```

Với overload này, giá trị trả về là **đối tượng số được quan sát**, không phải `Gauge`. Giữ nó trong một trường của thành phần sống đủ lâu để vừa cập nhật vừa duy trì nguồn đo.

Không dùng cả hai ví dụ để đăng ký cùng một phép đo với các đối tượng khác nhau. Chúng là hai cách lựa chọn cho cùng một nhu cầu.

### 3.3. Không đăng ký một ảnh chụp của số liệu

```java
// Sai nếu muốn theo dõi các thay đổi sau này của hàng đợi:
registry.gauge("demo.queue.depth", queue.size());
```

`queue.size()` được tính ngay khi gọi phương thức. Giá trị số được truyền vào không giữ quan hệ với những thay đổi về sau của `queue`. Tương tự, một `Integer` hay `Double` là đối tượng bất biến; gán biến sang một số khác không thay đổi đối tượng mà Gauge đang đo.

Cách biểu đạt đúng là truyền **nguồn có thể đọc lại**:

```java
Gauge.builder("demo.queue.depth", queue, BlockingQueue::size)
        .tag("queue", "email")
        .register(registry);
```

Các đoạn ngắn trong mục này giả định đã có `registry` và các kiểu Java được import. Mục 5 cung cấp đầy đủ tệp và lệnh chạy.

## 4. Vì sao phải quản lý vòng đời của nguồn đo?

### 4.1. Giữ Gauge không đồng nghĩa giữ đối tượng

Với dạng builder nhận đối tượng và hàm đọc, mặc định Micrometer giữ **tham chiếu yếu (weak reference)** đến đối tượng được quan sát. Tham chiếu yếu không buộc đối tượng phải ở lại bộ nhớ khi ứng dụng không còn đường tham chiếu mạnh nào đến nó.

Mô hình cần thiết trong một ứng dụng Spring có thể biểu diễn như sau:

```text
ApplicationContext
    -> bean quản lý metrics
        -> hàng đợi                         (tham chiếu mạnh)

MeterRegistry
    -> Gauge
        --tham chiếu yếu--> hàng đợi
        -> hàm đọc BlockingQueue::size
```

Bean giữ hàng đợi để nghiệp vụ và phép đo cùng sử dụng. Gauge chỉ quan sát nguồn đó.

Đoạn minh họa sau có vấn đề về vòng đời:

```java
void register(MeterRegistry registry) {
    AtomicInteger temporary = new AtomicInteger(0);
    Gauge.builder("demo.temporary.pending", temporary, AtomicInteger::get)
            .register(registry);
}
```

Khi phương thức kết thúc, nếu không còn nơi nào giữ `temporary`, đối tượng có thể bị bộ thu gom rác (GC) thu hồi. Việc registry còn Gauge không khắc phục được điều đó. Lưu riêng Gauge vào một trường cũng không thay thế trách nhiệm giữ nguồn đo.

Sau khi nguồn bị thu hồi, Gauge có thể cho `NaN` hoặc không còn xuất hiện trong dữ liệu xuất, tùy registry. **Không diễn giải tình trạng này thành giá trị 0.** Hàng đợi rỗng và không còn đọc được hàng đợi là hai trạng thái khác nhau.

Trong [DefaultGauge của Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/internal/DefaultGauge.java), hàm đọc còn có thể dẫn đến `NaN` khi xảy ra lỗi. Do đó, `NaN` là dấu hiệu cần kiểm tra cả nguồn và hàm đọc, không phải bằng chứng duy nhất về GC.

Không xây kiểm thử với giả định rằng một lần gọi `System.gc()` sẽ thu hồi đối tượng ngay. Thời điểm GC không phải điều kiện ổn định để kiểm tra hành vi nghiệp vụ.

### 4.2. Tránh giữ nguồn một cách vô tình qua lambda

Hai cách sau có ý nghĩa khác nhau về đường tham chiếu:

```java
// Hàm đọc sử dụng chính đối tượng mà Micrometer truyền vào:
Gauge.builder("demo.queue.depth", queue, BlockingQueue::size)
        .register(registry);

// Lambda bắt giữ thêm một đối tượng bên ngoài:
Gauge.builder("demo.queue.depth.captured", queue, ignored -> queue.size())
        .register(registry);
```

Trong cách thứ hai, hàm đọc bắt giữ `queue`. Vì Gauge giữ hàm đọc, đường tham chiếu qua lambda có thể giữ hàng đợi sống lâu ngoài dự kiến. Tham chiếu yếu trên một đường không triệt tiêu tham chiếu mạnh trên đường khác.

Ưu tiên hàm đọc dùng tham số nhận được. Khi một nguồn phải sống lâu, thể hiện điều đó bằng trường của thành phần quản lý nguồn, thay vì dựa vào tác dụng phụ của việc bắt giữ biến.

### 4.3. Khi chủ động dùng strongReference(true)

Builder trong Micrometer 1.13 có lựa chọn giữ mạnh nguồn đo:

```java
AtomicInteger state = new AtomicInteger(5);

Gauge retained = Gauge.builder(
                "demo.explicit.pending", state, AtomicInteger::get)
        .strongReference(true)
        .register(registry);
```

Lựa chọn này hữu ích khi thiết kế chủ động giao việc giữ nguồn cho phép đo. Nó cần đi kèm quyết định nguồn sẽ được giải phóng lúc nào và ai có quyền gỡ phép đo.

Nếu registry tồn tại lâu, nguồn cùng những đối tượng mà nó tham chiếu có thể bị giữ lâu theo. Không bật tùy chọn này hàng loạt để che việc chưa xác định nơi quản lý trạng thái. Nó cũng không giải quyết việc cập nhật sai đối tượng hoặc đăng ký trùng tên/nhãn.

Sau khi gỡ Gauge, nguồn chỉ đủ điều kiện được thu hồi nếu không còn tham chiếu mạnh nào khác; chẳng hạn biến `retained` hoặc thành phần nghiệp vụ vẫn có thể giữ những đối tượng liên quan. Gỡ phép đo không ép GC chạy.

## 5. Chương trình hoàn chỉnh: hàng đợi sống cùng thành phần quản lý phép đo

Ví dụ dùng Java 17 trở lên và Micrometer 1.13.0. Hai tệp Java sau tạo thành chương trình độc lập, không cần Spring hay hệ thống giám sát bên ngoài.

Trong dự án Spring Boot 3.3, hãy để cơ chế quản lý dependency của Boot chọn phiên bản Micrometer tương thích. Phiên bản cố định dưới đây chỉ phục vụ thí nghiệm độc lập.

### 5.1. Thành phần giữ nguồn và đăng ký một lần

Tệp `src/example/metrics/QueueDepthMetrics.java`:

```java
package example.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;

public final class QueueDepthMetrics implements AutoCloseable {

    private final MeterRegistry registry;
    private final BlockingQueue<String> queue;
    private final Gauge gauge;

    public QueueDepthMetrics(MeterRegistry registry,
                             BlockingQueue<String> queue) {
        this.registry = Objects.requireNonNull(registry);
        this.queue = Objects.requireNonNull(queue);
        this.gauge = Gauge.builder(
                        "demo.queue.depth", this.queue, BlockingQueue::size)
                .tag("queue", "email")
                .description("Số tác vụ đang chờ trong hàng đợi email")
                .register(this.registry);
    }

    public double value() {
        return this.gauge.value();
    }

    @Override
    public void close() {
        this.registry.remove(this.gauge);
    }
}
```

Trường `queue` giữ mạnh **đúng hàng đợi đang được đo**. Hàm `BlockingQueue::size` không bắt giữ thêm một hàng đợi bên ngoài. Phương thức `value()` được đưa ra để thí nghiệm đọc trực tiếp; xử lý nghiệp vụ không cần liên tục gọi phương thức này.

`close()` chỉ gỡ phép đo thuộc thành phần này, không đóng toàn bộ registry dùng chung và không xóa công việc trong hàng đợi.

**Điều kiện sử dụng:** trong một registry, chỉ một thành phần quản lý bộ tên/nhãn `demo.queue.depth{queue=email}` tại một thời điểm. Không tạo nhiều `QueueDepthMetrics` cùng bộ tên/nhãn, vì chúng có thể dùng chung một phép đo và gỡ nhầm phép đo của nhau.

### 5.2. Thay đổi hàng đợi rồi đọc lại

Tệp `src/example/metrics/GaugeLifecycleDemo.java`:

```java
package example.metrics;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class GaugeLifecycleDemo {

    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(10);

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            try (QueueDepthMetrics metrics =
                         new QueueDepthMetrics(registry, queue)) {

                System.out.println("initial=" + metrics.value());

                queue.add("A");
                queue.add("B");
                System.out.println("after-add=" + metrics.value());

                queue.remove();
                System.out.println("after-remove=" + metrics.value());

                queue.add("C");
                queue.add("D");
                queue.remove();
                queue.remove();
                System.out.println("after-burst=" + metrics.value());
            }

            boolean registered = registry.find("demo.queue.depth")
                    .tag("queue", "email")
                    .gauge() != null;
            System.out.println("registered-after-close=" + registered);
        } finally {
            registry.close();
        }
    }
}
```

Chương trình chạy tuần tự để stdout có thể dự đoán chính xác. Việc lựa chọn `ArrayBlockingQueue` cũng làm nguồn này phù hợp với trường hợp sau đó có nhiều luồng thêm/lấy việc.

### 5.3. Dependency và lệnh biên dịch

Tạo `pom.xml` ở thư mục gốc của thí nghiệm:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>gauge-lifecycle-demo</artifactId>
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

Chạy tại thư mục chứa `pom.xml`, với JDK 17+ và Maven đã có trong PATH. Lần đầu tải dependency cần kết nối Maven Central.

PowerShell trên Windows:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/metrics/QueueDepthMetrics.java src/example/metrics/GaugeLifecycleDemo.java
java -cp "out;lib/*" example.metrics.GaugeLifecycleDemo
```

Với Bash trên Linux/macOS, hai lệnh đầu giữ nguyên, còn lệnh chạy đổi dấu phân cách classpath:

```bash
java -cp "out:lib/*" example.metrics.GaugeLifecycleDemo
```

Stdout:

```text
initial=0.0
after-add=2.0
after-remove=1.0
after-burst=1.0
registered-after-close=false
```

Từ `after-remove` đến `after-burst`, kích thước từng tăng lên 3 rồi trở về 1. Gauge chỉ được đọc sau chuỗi thao tác, nên kết quả vẫn là `1.0`. Dòng cuối chứng minh phép đo đã được gỡ khỏi registry; nó không chứng minh hàng đợi đã bị GC thu hồi. Trong Micrometer 1.13.0, registry có phương thức `close()` nhưng không triển khai `AutoCloseable`, nên ví dụ đóng registry bằng `finally` và chỉ dùng try-with-resources cho `QueueDepthMetrics`.

## 6. Gắn vòng đời vào Spring Boot Actuator

Trong một ứng dụng Spring Boot đã có `spring-boot-starter-actuator`, dùng `MeterRegistry` do Spring quản lý. Không tạo một `SimpleMeterRegistry` riêng trong bean nghiệp vụ rồi mong Actuator tự nhìn thấy số liệu ở đó.

Giữ lớp `QueueDepthMetrics` ở trên và thêm cấu hình sau trong vùng package được ứng dụng quét:

Tệp `QueueMetricsConfiguration.java`:

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

@Configuration(proxyBeanMethods = false)
public class QueueMetricsConfiguration {

    @Bean
    public BlockingQueue<String> emailQueue() {
        return new ArrayBlockingQueue<>(100);
    }

    @Bean(destroyMethod = "close")
    public QueueDepthMetrics emailQueueMetrics(
            MeterRegistry registry,
            @Qualifier("emailQueue") BlockingQueue<String> queue) {
        return new QueueDepthMetrics(registry, queue);
    }
}
```

Đây là cấu hình tích hợp, không phải một ứng dụng Boot độc lập. Nó sử dụng lớp ở mục 5 và registry do Actuator cấu hình.

Quan hệ vòng đời rõ ràng:

1. Spring tạo bean hàng đợi.
2. Spring tạo bean `emailQueueMetrics`, truyền cùng hàng đợi và registry vào constructor.
3. Bean metrics đăng ký Gauge một lần và giữ nguồn bằng trường `queue`.
4. Mã nghiệp vụ nhận bean `emailQueue` để thêm/lấy tác vụ; Gauge đọc chính hàng đợi đó.
5. Khi context đóng bình thường, Spring gọi `close()` theo `destroyMethod`, gỡ Gauge.

Không đặt phần đăng ký vào mỗi request hoặc mỗi lần thêm công việc. Cũng không tự gọi `close()` trong khi bean còn cần phục vụ phép đo.

Nếu chọn cách tổ chức bằng `MeterBinder`, một bean binder có thể tập hợp các phép đo phụ thuộc bean khác và được Boot tự gắn với registry. Hãy chọn một đường đăng ký cho từng bộ tên/nhãn để tránh đăng ký lặp. Xem [đăng ký metrics tùy chỉnh trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.registering-custom) và [callback vòng đời bean của Spring](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle).

### Kiểm tra qua endpoint metrics

Nếu ứng dụng đã chạy với môi trường web và các endpoint chưa được cấu hình khác, có thể bổ sung vào cấu hình dành cho môi trường thực hành:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Khi ứng dụng dùng cổng mặc định và đường dẫn Actuator mặc định:

```bash
curl "http://localhost:8080/actuator/metrics/demo.queue.depth?tag=queue:email"
```

Lúc hàng đợi chưa có công việc, phần dữ liệu đo tương ứng có dạng:

```json
{
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 0.0
    }
  ]
}
```

Đây là **trích đoạn** phản hồi, không phải toàn bộ JSON. Các trường khác như tên, mô tả và nhãn có thể xuất hiện. Nếu ứng dụng có Spring Security, yêu cầu còn phải đáp ứng cấu hình xác thực/phân quyền của ứng dụng.

Dùng tên đăng ký `demo.queue.depth` để truy vấn endpoint này. Khi xuất sang hệ thống khác, tên biểu diễn có thể được chuẩn hóa theo quy ước riêng. Tham số tag giúp chọn đúng hàng đợi khi có nhiều chuỗi số liệu. Đặc điểm endpoint và cách lọc nhãn được nêu trong [tài liệu metrics endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

## 7. Đăng ký trùng và thay đối tượng: hai lỗi dễ nhầm với GC

### 7.1. Cùng tên và nhãn không có nghĩa là thay nguồn đo

Trong cùng registry, đăng ký lại Gauge với cùng tên và cùng bộ tag không phải lệnh cập nhật đối tượng được quan sát. Giả sử:

```java
AtomicInteger first = new AtomicInteger(2);
AtomicInteger second = new AtomicInteger(9);

Gauge original = Gauge.builder(
                "demo.pending.same", first, AtomicInteger::get)
        .tag("queue", "email")
        .register(registry);

Gauge repeated = Gauge.builder(
                "demo.pending.same", second, AtomicInteger::get)
        .tag("queue", "email")
        .register(registry);

first.set(4);
second.set(12);
```

Với registry chấp nhận phép đo và không có cấu hình lọc đặc biệt, phép đo đã tồn tại vẫn theo dõi `first`, nên đọc giá trị sẽ nhận `4.0`. `second` không trở thành nguồn mới chỉ vì được truyền vào lần đăng ký sau. Registry có thể ghi cảnh báo cho việc đăng ký lặp.

Hậu quả thực tế: bạn cập nhật `second` nhưng đồng hồ không đổi, rồi kết luận nhầm rằng Gauge bị cache hoặc xuất số liệu chậm.

Nếu cấu hình `MeterFilter` biến hai bộ tên/nhãn thành cùng một định danh, xung đột tương tự cũng có thể xảy ra. Các tên/nhãn trong thiết kế phải phân biệt được những nguồn thực sự khác nhau.

### 7.2. Gán trường sang đối tượng mới không đổi nguồn đã đăng ký

Giả sử lúc khởi động, Gauge được đăng ký bằng `queueA`. Sau đó chương trình gán biến hàng đợi sang `queueB`. Gauge vẫn giữ quan hệ với `queueA` đã nhận khi đăng ký.

Có hai hướng xử lý, tùy thiết kế:

- Giữ một nguồn ổn định suốt vòng đời phép đo, thay đổi dữ liệu bên trong nguồn đó.
- Khi nguồn thật sự được thay thế, để thành phần quản lý nguồn phối hợp gỡ phép đo cũ rồi đăng ký nguồn mới.

Nếu việc thay nguồn là một khả năng thường xuyên của hệ thống, cũng có thể thiết kế một đối tượng trung gian sống ổn định để đọc nguồn hiện hành. Khi đó phải bảo đảm việc thay/đọc nguồn an toàn giữa các luồng và xác định rõ hành vi khi chưa có nguồn.

Không gỡ rồi đăng ký liên tục trong đường xử lý mỗi tác vụ. Việc thay nguồn và gỡ phép đo phải do một thành phần chịu trách nhiệm; nếu các luồng tự làm độc lập, có thể tạo khoảng trống quan sát hoặc gỡ phép đo vừa được luồng khác tạo.

## 8. Kết thúc vòng đời và chẩn đoán

Với một đối tượng sống bằng vòng đời ứng dụng, bean giữ mạnh nguồn thường là đủ. Với đối tượng được tạo/hủy trong lúc ứng dụng đang chạy, cần xác định thêm thời điểm thôi quan sát nó.

**Nguồn bị thu hồi không đồng nghĩa phép đo đã tự được gỡ khỏi registry.** Một mục đăng ký cũ vẫn có thể tồn tại nhưng không đọc được nguồn. Nếu sau đó tạo một đối tượng mới và đăng ký lại cùng tên/nhãn, bạn còn có thể gặp vấn đề đăng ký trùng.

Khi một nguồn động hết vòng đời, trình tự thiết kế nên là: phối hợp dừng việc sử dụng nguồn theo yêu cầu nghiệp vụ, gỡ Gauge thuộc nguồn đó, rồi bỏ các tham chiếu mạnh không còn cần thiết. Dữ liệu lịch sử đã được hệ thống giám sát lưu không bị xóa chỉ vì ứng dụng gọi `registry.remove(gauge)`.

Đừng tạo nhãn từ request ID, địa chỉ email của từng người hay định danh tùy ý chỉ để tránh xung đột. Mỗi tổ hợp nhãn tạo thêm chuỗi số liệu; gỡ Gauge trong ứng dụng cũng không làm lịch sử bên ngoài biến mất ngay. Ví dụ sử dụng nhãn `queue=email` có số giá trị được kiểm soát.

| Biểu hiện | Kiểm tra trước | Cách xử lý phù hợp |
| --- | --- | --- |
| Ban đầu có số, sau đó NaN hoặc mất mẫu | Còn tham chiếu mạnh đến đúng nguồn không? Hàm đọc có lỗi không? | Sửa vòng đời nguồn hoặc lỗi hàm đọc; không đổi thành 0 tùy tiện |
| Cập nhật một biến nhưng Gauge đứng yên | Biến đó có trỏ đúng đối tượng đã đăng ký không? | Cập nhật nguồn ổn định; xử lý thay nguồn rõ ràng |
| Đăng ký lại mà vẫn đọc số cũ | Có dùng lại cùng tên/tag không? | Đăng ký một lần; gỡ/đăng ký lại chỉ khi chủ động thay nguồn |
| Bộ nhớ tăng theo số đối tượng được tạo | Lambda có bắt giữ đối tượng lớn? Có giữ mạnh và quên gỡ không? | Xem lại đường tham chiếu và trách nhiệm dọn dẹp |
| Giá trị thỉnh thoảng sai khi chạy nhiều luồng | Nguồn và thao tác đọc có an toàn đồng thời không? | Chọn cấu trúc dữ liệu/cơ chế đồng bộ phù hợp |
| Đọc Gauge nội bộ được nhưng Actuator không thấy | Phép đo có nằm trong registry Spring quản lý không? Endpoint đã được expose chưa? | Dùng registry được inject và kiểm tra cấu hình endpoint |
| Đỉnh ngắn hạn không xuất hiện | Có xảy ra giữa hai lần lấy mẫu không? | Chọn thêm phép đo phù hợp với câu hỏi cần trả lời |

Hàm đọc nên nhanh, ít tác dụng phụ và không thực hiện công việc nghiệp vụ. Tránh gọi dịch vụ mạng, chạy truy vấn nặng hoặc lấy phần tử khỏi hàng đợi chỉ để trả một con số. Một lần quan sát không được vô tình làm thay đổi chính đại lượng đang đo.

## 9. Thực hành tự kiểm chứng

1. Chạy chương trình ở mục 5 và đối chiếu cả năm dòng stdout.
2. Chuyển lệnh đọc `after-burst` đến ngay sau hai lệnh thêm `C`, `D`. Giá trị lúc đó là `3.0`; giải thích vì sao lần đọc cũ chỉ nhận `1.0`.
3. Trong một registry thử nghiệm riêng, chạy đoạn đăng ký trùng ở mục 7.1 và kiểm tra đối tượng nào thực sự được đo. Không trộn phép đo này với Gauge của chương trình hàng đợi.
4. Tích hợp cấu hình ở mục 6 vào ứng dụng Boot, thêm hai việc qua bean hàng đợi và truy vấn theo tag. Khi hai việc vẫn đang chờ và không có luồng lấy việc, giá trị phải là `2.0`.
5. Xem một thành phần metrics trong ứng dụng và xác định được: ai giữ nguồn, ai thay đổi nguồn, ai đăng ký phép đo, ai gỡ phép đo. Nếu chưa trả lời được một câu, thiết kế vòng đời còn thiếu trách nhiệm cụ thể.

Một Gauge đáng tin cậy cần đồng thời đúng **ý nghĩa đại lượng**, đúng **đối tượng được đọc**, đúng **thời gian tồn tại của nguồn** và đúng **trách nhiệm gỡ phép đo**.
