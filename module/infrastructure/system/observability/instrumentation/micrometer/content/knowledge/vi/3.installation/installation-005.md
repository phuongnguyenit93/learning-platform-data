# Khởi tạo SimpleMeterRegistry trong chương trình Java độc lập

Micrometer cung cấp một API đo lường thống nhất cho ứng dụng Java. Bạn có thể tạo `Counter`, `Gauge`, `Timer` hoặc `DistributionSummary` mà không phải gắn mã nghiệp vụ với một hệ thống giám sát cụ thể. Khi muốn thử nghiệm API đó trong một chương trình Java độc lập, `SimpleMeterRegistry` là điểm bắt đầu gọn nhẹ: nó giữ các meter và giá trị đo ngay trong bộ nhớ của tiến trình.

Bài học này hướng dẫn thêm thư viện Micrometer Core, tạo một `SimpleMeterRegistry` trong `main`, đăng ký và cập nhật các meter, sau đó đọc những giá trị đã ghi nhận. Ví dụ không cần Spring Boot, Actuator, Prometheus hay một máy chủ metrics. Đây là cách thuận tiện để học mô hình meter, viết thử instrumentation và kiểm tra logic đo lường trước khi tích hợp registry xuất dữ liệu.

## Kết quả mong đợi

Sau khi hoàn thành, bạn có thể:

- Thêm dependency `micrometer-core` vào một dự án Java.
- Khởi tạo `SimpleMeterRegistry` trực tiếp trong chương trình.
- Tạo và cập nhật `Counter`, `Gauge`, `Timer` và `DistributionSummary`.
- Đọc giá trị đo bằng API Micrometer và duyệt các `Measurement`.
- Giải thích giới hạn của registry lưu dữ liệu trong bộ nhớ và biết khi nào cần registry khác.

## `SimpleMeterRegistry` nằm ở đâu trong kiến trúc?

Micrometer tách phần ghi nhận số đo khỏi cách dữ liệu được chuyển đến hệ thống nhận. Ứng dụng gọi API chung trên `MeterRegistry`; một registry cụ thể quyết định cách giữ hoặc xuất số đo.

~~~mermaid
flowchart LR
    A[Chương trình Java] --> B[Micrometer API]
    B --> C[SimpleMeterRegistry]
    C --> D[Meter và Measurement trong bộ nhớ]
    D --> E[Đọc giá trị bằng Java API]
~~~

`SimpleMeterRegistry` là một implementation đơn giản của `MeterRegistry`. Khi chương trình gọi `counter.increment()` hoặc `timer.record(...)`, registry cập nhật trạng thái meter tương ứng. Chương trình có thể truy cập lại meter và đọc giá trị trong cùng tiến trình.

Điểm cần nhớ là `SimpleMeterRegistry` không phải một metrics exporter. Nó không mở HTTP endpoint cho Prometheus scrape và cũng không tự gửi dữ liệu đến một collector. Dữ liệu nằm trong bộ nhớ của ứng dụng; khi tiến trình kết thúc, dữ liệu đó không còn được lưu giữ. Vì vậy registry này phù hợp cho ví dụ độc lập, thử nghiệm cục bộ và một số kiểm thử đơn vị. Khi cần quan sát một ứng dụng đang chạy ở môi trường thật, hãy chọn registry tích hợp với hệ thống nhận metrics.

## Thêm Micrometer Core vào dự án

`SimpleMeterRegistry` thuộc thư viện `micrometer-core`. Một chương trình Java độc lập chỉ cần dependency này để sử dụng API cơ bản; không cần kéo Spring Boot vào dự án.

### Với Gradle

Trong `build.gradle.kts`, khai báo plugin ứng dụng, repository và dependency. Đặt phiên bản Micrometer trong `gradle.properties` để dễ quản lý:

~~~properties
micrometerVersion=REPLACE_WITH_COMPATIBLE_MICROMETER_VERSION
~~~

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

val micrometerVersion = providers.gradleProperty("micrometerVersion").get()

dependencies {
    implementation("io.micrometer:micrometer-core:$micrometerVersion")
}

application {
    mainClass.set("example.MetricsDemo")
}
~~~

Thay giá trị placeholder bằng phiên bản Micrometer tương thích với JDK và quy ước quản lý dependency của dự án. Nếu dự án đã dùng một BOM quản lý phiên bản Micrometer, hãy theo phiên bản do BOM đó cung cấp thay vì khai báo một phiên bản độc lập.

Đặt mã nguồn ở `src/main/java/example/MetricsDemo.java`, sau đó chạy:

~~~bash
./gradlew run
~~~

Trên Windows có thể dùng `gradlew.bat run`.

### Với Maven

Thêm dependency sau vào phần `dependencies` trong `pom.xml`:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-core</artifactId>
    <version>REPLACE_WITH_COMPATIBLE_MICROMETER_VERSION</version>
</dependency>
~~~

Thay `REPLACE_WITH_COMPATIBLE_MICROMETER_VERSION` bằng phiên bản phù hợp với JDK và dependency management của dự án. Nếu phiên bản đã được quản lý qua BOM, có thể bỏ thẻ `version` tại dependency và import BOM tương ứng trong `dependencyManagement`.

Sau khi khai báo dependency, đồng bộ hoặc build lại dự án để IDE và trình biên dịch nhận được các lớp Micrometer.

## Khởi tạo registry và đăng ký meter

Lớp `SimpleMeterRegistry` nằm trong package `io.micrometer.core.instrument.simple`. Bạn có thể tạo instance trực tiếp:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
~~~

Biến `registry` là nơi đăng ký và tìm các meter. Ví dụ, tạo một counter theo kênh bán hàng:

~~~java
Counter webOrders = registry.counter(
    "orders.created",
    "channel", "web"
);
~~~

Tên meter là `orders.created`; cặp tag `channel=web` bổ sung chiều phân tích cho số đơn hàng. Khi cần tăng số đếm, gọi:

~~~java
webOrders.increment();
webOrders.increment(2);
~~~

Micrometer nhận diện meter dựa trên tên và tập tag. Nếu gọi `registry.counter("orders.created", "channel", "web")` lần nữa, registry tìm và tái sử dụng meter tương ứng. Nếu đổi tag thành `channel=store`, registry đăng ký một meter ID khác. Vì vậy, hãy chọn tag có tập giá trị nhỏ, ổn định và có ý nghĩa; không dùng ID người dùng, ID đơn hàng hay request ID làm tag vì chúng có thể tạo cardinality rất lớn.

## Chương trình hoàn chỉnh

Ví dụ dưới đây tạo bốn loại meter thường gặp trong instrumentation ứng dụng. Chương trình ghi nhận số đơn hàng, số tác vụ đang chờ, thời gian xử lý và kích thước payload. Sau đó nó đọc giá trị trực tiếp và duyệt các measurement mà registry đang giữ.

~~~java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Measurement;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MetricsDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        try {
            // 1. Counter: đếm số đơn hàng được tạo.
            Counter orders = registry.counter(
                "orders.created",
                "channel", "web"
            );
            orders.increment();
            orders.increment(2);

            // 2. Gauge: quan sát số tác vụ đang chờ tại thời điểm đọc.
            AtomicInteger queueSize = new AtomicInteger(4);
            Gauge queueGauge = Gauge.builder(
                    "worker.queue.size",
                    queueSize,
                    AtomicInteger::get
                )
                .description("Số tác vụ đang chờ xử lý")
                .register(registry);

            queueSize.set(2);

            // 3. Timer: đo thời lượng của một thao tác.
            Timer processingTimer = Timer.builder("checkout.processing")
                .description("Thời gian xử lý checkout")
                .tag("operation", "authorize")
                .register(registry);

            processingTimer.record(MetricsDemo::simulateWork);

            // 4. DistributionSummary: đo phân phối kích thước payload.
            DistributionSummary payloadSize = DistributionSummary
                .builder("message.payload.size")
                .baseUnit("bytes")
                .register(registry);

            payloadSize.record(512);
            payloadSize.record(1024);
            payloadSize.record(2048);

            // Đọc từng meter qua API chuyên biệt.
            System.out.println("Orders: " + orders.count());
            System.out.println("Queue size: " + queueGauge.value());
            System.out.println("Timer count: " + processingTimer.count());
            System.out.println(
                "Timer total (ms): "
                    + processingTimer.totalTime(TimeUnit.MILLISECONDS)
            );
            System.out.println("Payload count: " + payloadSize.count());
            System.out.println("Payload total: " + payloadSize.totalAmount());

            // Duyệt tất cả meter và các measurement của chúng.
            for (Meter meter : registry.getMeters()) {
                System.out.println("Meter ID: " + meter.getId());

                for (Measurement measurement : meter.measure()) {
                    System.out.printf(
                        "  %s = %.2f%n",
                        measurement.getStatistic(),
                        measurement.getValue()
                    );
                }
            }
        } finally {
            registry.close();
        }
    }

    private static void simulateWork() {
        try {
            Thread.sleep(30);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Thao tác mô phỏng bị gián đoạn",
                exception
            );
        }
    }
}
~~~

Kết quả cụ thể của thời gian xử lý thay đổi theo máy chạy chương trình. Các giá trị đếm trong ví dụ có thể dự đoán được: counter có giá trị `3`, gauge trả về `2`, timer có count bằng `1`, còn summary có count bằng `3` và tổng amount bằng `3584`.

Thứ tự các meter khi duyệt `registry.getMeters()` không nên được xem là thứ tự cố định. Hãy dựa vào `Meter.Id` hoặc tên và tag để nhận diện meter.

## Hiểu từng loại meter trong ví dụ

| Meter | Cách ghi nhận | Giá trị đọc thường dùng |
|---|---|---|
| `Counter` | `increment()` hoặc `increment(n)` | `count()` |
| `Gauge` | Đọc một đối tượng hoặc trạng thái hiện tại | `value()` |
| `Timer` | `record(...)` hoặc `record(amount, unit)` | `count()`, `totalTime(unit)` |
| `DistributionSummary` | `record(value)` | `count()`, `totalAmount()` |

### Counter: đếm sự kiện tích lũy

`Counter` phù hợp với các sự kiện chỉ tăng như đơn hàng được tạo, email được gửi hoặc tác vụ hoàn tất. Mỗi lần sự kiện xảy ra, gọi `increment()`. Có thể tăng nhiều đơn vị trong một lần bằng `increment(amount)` với amount không âm.

Counter trong ví dụ được gắn tag `channel=web`. Nếu cần đếm đơn hàng ở cửa hàng, hãy đăng ký một counter cùng tên nhưng có tag `channel=store`. Khi truy vấn hoặc xuất dữ liệu, hai tập tag này được phân biệt thành hai meter ID.

Không dùng counter để biểu diễn một giá trị có thể tăng và giảm, chẳng hạn số kết nối hiện tại. Trường hợp đó phù hợp với `Gauge`.

### Gauge: quan sát giá trị hiện tại

`Gauge` đọc giá trị từ một đối tượng mà bạn cung cấp. Trong ví dụ, `AtomicInteger` giữ số tác vụ đang chờ. Khi gọi `queueSize.set(2)`, lần đọc tiếp theo qua gauge sẽ thấy giá trị mới.

Giữ một tham chiếu mạnh đến đối tượng được gauge quan sát trong suốt thời gian cần đo. Micrometer sử dụng tham chiếu yếu cho đối tượng được quan sát để tránh việc registry vô tình giữ vòng đời của đối tượng ứng dụng. Nếu đối tượng không còn được giữ ở nơi khác, nó có thể bị garbage collector thu hồi và gauge không còn đọc được giá trị hữu ích.

Gauge biểu diễn trạng thái tại thời điểm đọc. Nó không ghi lại mọi thay đổi trung gian. Nếu cần đếm số lần một sự kiện xảy ra, hãy dùng counter.

### Timer: đo thời lượng và số lần thực hiện

`Timer` ghi nhận thời lượng của một thao tác và số lần thao tác được thực hiện. `record(Runnable)` thực thi đoạn mã rồi ghi thời gian chạy của đoạn mã đó. Trong ví dụ, `simulateWork` ngủ khoảng 30 mili giây để tạo một thao tác có thời lượng quan sát được.

`count()` trả về số lần đã ghi nhận. `totalTime(TimeUnit.MILLISECONDS)` trả về tổng thời gian đã ghi nhận theo đơn vị yêu cầu. Timer thích hợp cho thời gian xử lý request, truy vấn cơ sở dữ liệu hoặc gọi dịch vụ ngoài.

Nên đo đúng vùng công việc cần quan sát. Nếu đặt cả thời gian khởi tạo ứng dụng vào timer đo thời gian xử lý đơn hàng, số đo sẽ không phản ánh đúng độ trễ nghiệp vụ.

### DistributionSummary: đo phân phối của giá trị số

`DistributionSummary` ghi nhận các giá trị số như kích thước payload, số bản ghi trong một batch hoặc dung lượng dữ liệu. Mỗi lần có giá trị mới, gọi `record(value)`. Trong ví dụ, summary ghi nhận ba payload có kích thước 512, 1024 và 2048 bytes.

`count()` cho biết số giá trị đã ghi nhận; `totalAmount()` trả về tổng các giá trị đó. Khi cần theo dõi phân phối, có thể cấu hình histogram hoặc percentile theo khả năng của registry được sử dụng. Ví dụ hiện tại chỉ minh họa cách khởi tạo và đọc các số đo cơ bản từ `SimpleMeterRegistry`.

## Đọc Measurement và Meter ID

Các meter có API đọc riêng, chẳng hạn `Counter.count()` hoặc `Timer.totalTime(...)`. Ngoài ra, `Meter.measure()` cung cấp các `Measurement` mà meter đang công bố. Mỗi measurement gồm một loại thống kê và một giá trị.

Trong vòng lặp của chương trình, `meter.getId()` giúp xem danh tính meter, bao gồm tên và tag; `meter.measure()` giúp xem các thống kê đang có. Đây là cách hữu ích để khám phá meter khi viết ví dụ hoặc debug instrumentation. Tập measurement cụ thể phụ thuộc vào loại meter và cấu hình.

Không nên giả định mỗi meter luôn có đúng một measurement. Một timer có thể cung cấp count, total time và các thống kê phân phối khác. Đây cũng là lý do một meter trong ứng dụng không nhất thiết tương ứng với một chuỗi dữ liệu duy nhất khi được xuất sang backend giám sát.

## Đóng registry và vòng đời chương trình

Khi kết thúc công việc, gọi `registry.close()` để đóng registry. Với một ví dụ nhỏ, việc này có thể trông không cần thiết, nhưng nó giúp thể hiện rõ vòng đời tài nguyên và giữ cách viết nhất quán khi sau này thay registry đơn giản bằng implementation có tài nguyên hoặc tác vụ nền cần giải phóng.

Trong ví dụ, `try/finally` đảm bảo registry được đóng kể cả khi thao tác ghi nhận hoặc đọc số đo phát sinh lỗi. Nếu ứng dụng dùng registry tồn tại trong suốt vòng đời tiến trình, hãy quản lý nó ở phạm vi phù hợp và đóng khi ứng dụng dừng.

## Kiểm tra lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không import được `SimpleMeterRegistry` | Chưa thêm `micrometer-core` hoặc IDE chưa đồng bộ dependency | Kiểm tra dependency và chạy lại build |
| Counter luôn bằng `0` | Chưa gọi `increment()` hoặc đang đọc meter khác tag | Kiểm tra tên và toàn bộ tag khi đăng ký |
| Hai counter cùng tên có số khác nhau | Tập tag khác nhau tạo meter ID khác | In `meter.getId()` để xem tag |
| Gauge trả về giá trị không mong đợi | Đang quan sát nhầm đối tượng hoặc đối tượng không còn được giữ tham chiếu | Giữ đối tượng sống và kiểm tra hàm đọc |
| Timer có count bằng `0` | Đoạn code chưa được ghi nhận hoặc đang đọc timer khác tag | Kiểm tra lời gọi `record(...)` và meter ID |
| Không thấy metrics ở Prometheus | `SimpleMeterRegistry` không cung cấp endpoint scrape hay exporter | Cấu hình registry Prometheus hoặc registry xuất phù hợp |

Nếu chương trình không biên dịch, hãy kiểm tra dependency `io.micrometer:micrometer-core`, phiên bản thư viện tương thích với JDK và các import trong ví dụ. Nếu chương trình chạy nhưng số đo không đúng, hãy kiểm tra meter ID, tên và tập tag trước khi xem xét backend.

## Khi nào chuyển sang registry khác?

`SimpleMeterRegistry` phù hợp để học và kiểm thử vì không cần cấu hình dịch vụ bên ngoài. Khi yêu cầu thay đổi, hãy chọn registry theo cách hệ thống nhận dữ liệu:

- Dùng `PrometheusMeterRegistry` khi Prometheus sẽ scrape endpoint metrics của ứng dụng.
- Dùng registry OTLP khi muốn gửi metrics theo OpenTelemetry Protocol đến collector hoặc endpoint tương thích.
- Dùng registry tương ứng với nhà cung cấp giám sát nếu hệ thống đã chuẩn hóa theo một backend cụ thể.
- Dùng `CompositeMeterRegistry` khi có nhu cầu phát cùng instrumentation đến nhiều registry.

Dù chuyển registry, phần lớn mã tạo `Counter`, `Gauge`, `Timer` và `DistributionSummary` vẫn dùng API Micrometer chung. Đây là lợi ích quan trọng của việc viết instrumentation qua `MeterRegistry`: mã nghiệp vụ không phải phụ thuộc trực tiếp vào giao thức xuất dữ liệu.

## Ghi nhớ

- Thêm `io.micrometer:micrometer-core` để dùng Micrometer trong chương trình Java độc lập.
- Tạo `new SimpleMeterRegistry()` để có registry lưu meter trong bộ nhớ.
- Dùng `Counter`, `Gauge`, `Timer` và `DistributionSummary` theo đúng ý nghĩa của đại lượng cần đo.
- Dùng tên và tag ổn định để phân biệt meter; tránh tag có cardinality cao.
- Đọc số đo qua API chuyên biệt hoặc `Meter.measure()`.
- Đóng registry khi kết thúc vòng đời sử dụng.
- Chuyển sang registry xuất dữ liệu khi cần gửi metrics đến hệ thống giám sát.

Một chương trình Java độc lập với `SimpleMeterRegistry` giúp bạn kiểm tra instrumentation ngay tại nơi tạo ra số đo. Khi đã hiểu cách đăng ký, cập nhật và đọc meter, bạn có thể giữ nguyên phần lớn mã đo lường và thay registry phù hợp với môi trường triển khai sau này.

