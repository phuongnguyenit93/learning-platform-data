# Tạo chương trình Java có Counter, Gauge, Timer và SimpleMeterRegistry

Bài thực hành này xây dựng một chương trình Java nhỏ để đo hoạt động xử lý đơn hàng bằng Micrometer. Chương trình dùng `SimpleMeterRegistry` lưu meter trong bộ nhớ, `Counter` đếm đơn thành công và thất bại, `Gauge` theo dõi số đơn đang chờ, còn `Timer` đo thời gian xử lý.

Bạn sẽ tạo project Maven, chạy chương trình, đọc các giá trị đã ghi nhận và viết một bài kiểm thử xác nhận semantics của từng meter. Bài tập không cần Spring Boot hoặc Prometheus; mục tiêu là hiểu API cốt lõi trước khi đưa metrics vào ứng dụng thật.

## 1. Mục tiêu và tình huống thực hành

Giả sử một service nhận đơn hàng vào hàng đợi rồi xử lý từng đơn. Ta cần trả lời bốn câu hỏi:

1. Có bao nhiêu đơn đã xử lý thành công?
2. Có bao nhiêu lần xử lý thất bại?
3. Hiện còn bao nhiêu đơn đang chờ?
4. Mỗi lần xử lý mất bao lâu?

Ánh xạ sang meter:

| Câu hỏi | Meter | Tên meter | Cách cập nhật |
|---|---|---|---|
| Đơn thành công | Counter | `orders.created` | Tăng sau khi xử lý thành công |
| Đơn thất bại | Counter | `orders.failed` | Tăng khi xử lý ném lỗi |
| Số đơn đang chờ | Gauge | `orders.pending` | Đọc giá trị hiện tại của `AtomicInteger` |
| Thời gian xử lý | Timer | `orders.processing` | Ghi một sample cho mỗi lần xử lý |

Trong bài này, Timer ghi nhận cả lần thành công và lần thất bại vì sample được dừng trong `finally`. `orders.created` chỉ tăng khi công việc hoàn tất thành công. Nhờ vậy, count của Timer là tổng số lần thử đã kết thúc, còn Counter created là số kết quả thành công.

## 2. Chuẩn bị môi trường và tạo project

Yêu cầu:

- JDK 17 trở lên.
- Maven 3.8 trở lên.
- IDE Java hoặc terminal.

Tạo cấu trúc thư mục:

~~~text
micrometer-hands-on/
├── pom.xml
└── src/
    ├── main/java/dev/micrometer/workshop/
    │   ├── OrderMetrics.java
    │   └── OrderMetricsDemo.java
    └── test/java/dev/micrometer/workshop/
        └── OrderMetricsTest.java
~~~

Tạo file `pom.xml` với dependency Micrometer Core, JUnit Jupiter và plugin chạy chương trình:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.micrometer</groupId>
    <artifactId>micrometer-hands-on</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <micrometer.version>1.15.4</micrometer.version>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>${micrometer.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.micrometer.workshop.OrderMetricsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ ghim Micrometer Core ở phiên bản `1.15.4` để project có thể tái lập. Nếu project được quản lý bởi Spring Boot BOM hoặc một dependency platform khác, hãy dùng phiên bản Micrometer do BOM đó quản lý thay vì tự khai báo một phiên bản không tương thích.

## 3. Tạo lớp OrderMetrics

Lớp `OrderMetrics` chịu trách nhiệm đăng ký meter và cập nhật chúng. Registry được truyền từ bên ngoài qua constructor để lớp này không tự tạo một registry riêng.

~~~java
package dev.micrometer.workshop;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.atomic.AtomicInteger;

public final class OrderMetrics {
    private final MeterRegistry registry;
    private final AtomicInteger pendingOrders = new AtomicInteger();
    private final Counter created;
    private final Counter failed;
    private final Timer processing;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;

        this.created = Counter.builder("orders.created")
            .description("Số đơn hàng được xử lý thành công")
            .register(registry);

        this.failed = Counter.builder("orders.failed")
            .description("Số lần xử lý đơn hàng thất bại")
            .register(registry);

        Gauge.builder(
                "orders.pending",
                pendingOrders,
                AtomicInteger::get
            )
            .description("Số đơn hàng hiện đang chờ xử lý")
            .register(registry);

        this.processing = Timer.builder("orders.processing")
            .description("Thời gian xử lý một đơn hàng")
            .register(registry);
    }

    public void enqueue() {
        pendingOrders.incrementAndGet();
    }

    public void processNext(Runnable operation) {
        int pendingBefore = pendingOrders.getAndUpdate(
            current -> current > 0 ? current - 1 : current
        );

        if (pendingBefore == 0) {
            throw new IllegalStateException("Không có đơn hàng đang chờ");
        }

        Timer.Sample sample = Timer.start(registry);
        try {
            operation.run();
            created.increment();
        } catch (RuntimeException error) {
            failed.increment();
            throw error;
        } finally {
            sample.stop(processing);
        }
    }
}
~~~

Các điểm cần chú ý:

- `Counter.builder(...).register(registry)` đăng ký meter một lần trong constructor. Những lần xử lý tiếp theo chỉ gọi `increment()`.
- `AtomicInteger` là nguồn dữ liệu của Gauge. Giữ nó trong field để object còn sống trong suốt vòng đời của meter; một số Gauge giữ weak reference tới object được quan sát.
- `Gauge` đọc giá trị hiện tại khi registry lấy snapshot hoặc scrape. Nó không cộng dồn các lần cập nhật như Counter.
- `Timer.Sample` bắt đầu đo trước operation và dừng trong `finally`, do đó thời gian vẫn được ghi khi operation ném exception.
- `getAndUpdate()` giảm số đơn chờ theo cách nguyên tử và không cho giá trị bị giảm xuống dưới 0.

## 4. Tạo chương trình chạy thử

Tạo `OrderMetricsDemo.java`. Chương trình tạo hai đơn chờ, xử lý thành công một đơn và mô phỏng lỗi ở đơn còn lại.

~~~java
package dev.micrometer.workshop;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class OrderMetricsDemo {
    private OrderMetricsDemo() {
    }

    public static void main(String[] args) {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);

            metrics.enqueue();
            metrics.enqueue();
            printPending(registry, "Sau khi nhận hai đơn");

            metrics.processNext(OrderMetricsDemo::simulateWork);
            printPending(registry, "Sau khi xử lý đơn thứ nhất");

            try {
                metrics.processNext(() -> {
                    simulateWork();
                    throw new IllegalStateException("Lỗi xử lý mô phỏng");
                });
            } catch (IllegalStateException expected) {
                System.out.println("Đã ghi nhận một lần xử lý thất bại");
            }

            printPending(registry, "Sau khi xử lý đơn thứ hai");
            printMetrics(registry);
        }
    }

    private static void simulateWork() {
        try {
            Thread.sleep(35);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Công việc bị interrupt", interrupted);
        }
    }

    private static void printPending(
            SimpleMeterRegistry registry,
            String label) {
        double pending = registry.get("orders.pending")
            .gauge()
            .value();
        System.out.printf(Locale.ROOT, "%s: orders.pending = %.0f%n", label, pending);
    }

    private static void printMetrics(SimpleMeterRegistry registry) {
        Counter created = registry.get("orders.created").counter();
        Counter failed = registry.get("orders.failed").counter();
        Timer processing = registry.get("orders.processing").timer();

        System.out.println();
        System.out.println("--- Metrics summary ---");
        System.out.printf(Locale.ROOT, "orders.created = %.0f%n", created.count());
        System.out.printf(Locale.ROOT, "orders.failed = %.0f%n", failed.count());
        System.out.printf(Locale.ROOT, "orders.pending = %.0f%n",
            registry.get("orders.pending").gauge().value());
        System.out.printf(Locale.ROOT, "orders.processing.count = %d%n",
            processing.count());
        System.out.printf(Locale.ROOT, "orders.processing.total_ms = %.2f%n",
            processing.totalTime(TimeUnit.MILLISECONDS));
        System.out.printf(Locale.ROOT, "orders.processing.mean_ms = %.2f%n",
            processing.mean(TimeUnit.MILLISECONDS));
    }
}
~~~

`Thread.sleep()` chỉ mô phỏng công việc mất thời gian để Timer có giá trị dễ quan sát. Trong ứng dụng thật, thay `simulateWork()` bằng lời gọi service hoặc thao tác cần đo; không dùng sleep để đo hiệu năng production.

## 5. Chạy chương trình và đọc kết quả

Mở terminal tại thư mục `micrometer-hands-on` và chạy:

~~~bash
mvn clean compile exec:java
~~~

Kết quả sẽ có dạng sau. Thời gian thực tế thay đổi theo máy chạy nên các giá trị milliseconds chỉ mang tính minh họa:

~~~text
Sau khi nhận hai đơn: orders.pending = 2
Sau khi xử lý đơn thứ nhất: orders.pending = 1
Đã ghi nhận một lần xử lý thất bại
Sau khi xử lý đơn thứ hai: orders.pending = 0

--- Metrics summary ---
orders.created = 1
orders.failed = 1
orders.pending = 0
orders.processing.count = 2
orders.processing.total_ms = 70.00
orders.processing.mean_ms = 35.00
~~~

Giải thích kết quả:

- `orders.created = 1`: chỉ lần xử lý đầu tiên thành công.
- `orders.failed = 1`: lần xử lý thứ hai ném `IllegalStateException`.
- `orders.pending = 0`: cả hai đơn đã được lấy khỏi hàng đợi.
- `orders.processing.count = 2`: Timer ghi cả hai lần xử lý vì sample luôn được dừng trong `finally`.
- `orders.processing.total_ms` là tổng thời gian hai lần xử lý; `mean_ms` là thời gian trung bình trên mỗi sample.

`SimpleMeterRegistry` chỉ giữ dữ liệu trong bộ nhớ của process. Nó phù hợp cho ví dụ, unit test và kiểm tra nhanh; nó không tự xuất dữ liệu sang Prometheus hoặc hệ thống giám sát bên ngoài.

## 6. Kiểm thử semantics của Counter, Gauge và Timer

Tạo `OrderMetricsTest.java` để xác minh hành vi thay vì chỉ nhìn output console:

~~~java
package dev.micrometer.workshop;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderMetricsTest {

    @Test
    void recordsSuccessFailureQueueAndDuration() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);
            metrics.enqueue();
            metrics.enqueue();

            Gauge pending = registry.get("orders.pending").gauge();
            assertEquals(2.0, pending.value(), 0.0);

            metrics.processNext(() -> {
                // Công việc thành công, không cần sleep trong unit test.
            });

            assertEquals(1.0, pending.value(), 0.0);
            assertEquals(1.0,
                registry.get("orders.created").counter().count(), 0.0);

            assertThrows(IllegalStateException.class, () ->
                metrics.processNext(() -> {
                    throw new IllegalStateException("Test failure");
                })
            );

            assertEquals(0.0, pending.value(), 0.0);
            assertEquals(1.0,
                registry.get("orders.failed").counter().count(), 0.0);

            Timer processing = registry.get("orders.processing").timer();
            assertEquals(2L, processing.count());
        }
    }

    @Test
    void doesNotProcessWhenQueueIsEmpty() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);

            assertThrows(IllegalStateException.class,
                () -> metrics.processNext(() -> {}));

            Counter created = registry.get("orders.created").counter();
            assertEquals(0.0, created.count(), 0.0);
            assertEquals(0L,
                registry.get("orders.processing").timer().count());
        }
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Test đầu tiên xác nhận Gauge thay đổi theo hàng đợi, Counter chỉ tăng đúng nhánh và Timer đếm cả success lẫn failure. Test thứ hai xác nhận không có đơn chờ thì operation không được chạy và không meter nào tăng.

## 7. Quan sát meter trong SimpleMeterRegistry

Sau khi chương trình đăng ký meter, có thể truy xuất chúng bằng tên:

~~~java
Counter created = registry.get("orders.created").counter();
Gauge pending = registry.get("orders.pending").gauge();
Timer processing = registry.get("orders.processing").timer();

double successfulOrders = created.count();
double queuedOrders = pending.value();
long processingAttempts = processing.count();
double totalProcessingMs = processing.totalTime(TimeUnit.MILLISECONDS);
~~~

Registry cũng hỗ trợ duyệt danh sách meter đã đăng ký bằng `registry.getMeters()`. Khi debug, hãy kiểm tra tên và tag thực tế trước khi kết luận meter không được ghi.

Không cần tạo lại meter khi đọc giá trị. Gọi `registry.counter(...)` hoặc builder/register lặp lại với identity giống nhau thường trả về meter đã đăng ký, nhưng việc đăng ký meter trong constructor rồi giữ reference vẫn làm ý định rõ ràng và tránh lookup không cần thiết trên đường xử lý.

## 8. Những điều cần nhớ về từng meter

**Counter** phù hợp với sự kiện chỉ tăng như đơn được tạo, lỗi xảy ra hoặc message được xử lý. Không dùng Counter để biểu diễn số lượng hiện tại trong hàng đợi vì nó không giảm khi công việc được lấy ra.

**Gauge** biểu diễn giá trị hiện tại như queue depth, số worker active hoặc số kết nối đang mở. Gauge không tích lũy lịch sử; backend chỉ quan sát các giá trị tại thời điểm scrape hoặc export. Nguồn dữ liệu phải còn sống và được cập nhật thread-safe.

**Timer** đo thời gian và đồng thời cung cấp count cùng total time. Dùng Timer thay vì tự tạo Counter riêng chỉ để đếm số lần gọi cùng một thao tác. Khi đo code có nhiều nhánh kết thúc, đặt `sample.stop(timer)` trong `finally` để không bỏ sót lần đo.

**SimpleMeterRegistry** là registry đơn giản trong bộ nhớ. Mỗi registry là một tập meter độc lập; hai registry khác nhau không tự chia sẻ dữ liệu. Đóng registry sau khi dùng xong trong ứng dụng độc lập hoặc test để giải phóng tài nguyên.

## 9. Bài tập mở rộng

Sau khi chương trình cơ bản chạy đúng, thực hiện các thay đổi sau:

1. Thêm Counter `orders.cancelled` và chỉ tăng khi một đơn bị hủy theo quy tắc nghiệp vụ.
2. Thêm tag có tập giá trị hữu hạn như `channel=web` hoặc `channel=mobile` cho Counter created. Không dùng order ID làm tag.
3. Bật percentile histogram cho Timer và quan sát số meter/series thay đổi trong registry phù hợp.
4. Thêm Gauge `orders.workers.active` dựa trên `AtomicInteger` để theo dõi số worker đang xử lý.
5. Viết test xác nhận Gauge source vẫn được giữ tham chiếu và thay đổi sau khi worker bắt đầu/kết thúc.
6. Thay `SimpleMeterRegistry` bằng registry phù hợp với backend của ứng dụng và tìm hiểu cách export dữ liệu.

Với mỗi thay đổi, hãy ghi rõ metric đo sự kiện hay trạng thái, nơi cập nhật giá trị, đơn vị đo và tập tag được phép. Không thêm tag có giá trị gần như duy nhất cho từng request hoặc entity.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Counter luôn bằng 0 | Nhánh code chưa gọi `increment()` hoặc đang đọc nhầm registry | Kiểm tra nơi cập nhật và registry được inject |
| Gauge trả về 0 | Source chưa được cập nhật hoặc Gauge đang quan sát object khác | Kiểm tra `AtomicInteger` được truyền vào builder |
| Gauge không còn giá trị đúng | Source object không còn reference mạnh | Giữ source trong field có vòng đời ổn định |
| Timer count nhỏ hơn số lần thử | Có nhánh không gọi `stop()` | Đặt `sample.stop(timer)` trong `finally` |
| Timer không xuất hiện | Observation/sample chưa dừng hoặc query sai tên | Kiểm tra meter name và vòng đời sample |
| Số meter tăng liên tục | Tên hoặc tag chứa giá trị động | Chuẩn hóa tên và dùng tag hữu hạn |
| Không thấy metrics ở Prometheus | Đang dùng SimpleMeterRegistry hoặc chưa cấu hình exporter/scrape | Simple registry chỉ giữ dữ liệu trong bộ nhớ |

## 11. Checklist hoàn thành

- [ ] Project biên dịch bằng JDK 17 và Maven.
- [ ] Chương trình tạo một `SimpleMeterRegistry` và đóng registry sau khi chạy.
- [ ] `orders.created` tăng sau xử lý thành công.
- [ ] `orders.failed` tăng khi operation ném exception.
- [ ] `orders.pending` phản ánh số đơn đang chờ và không bị âm.
- [ ] `orders.processing` ghi nhận cả lần thành công và thất bại.
- [ ] Unit test xác nhận Counter, Gauge và Timer có semantics đúng.
- [ ] Tên meter ổn định và không chứa ID riêng của từng đơn hàng.
- [ ] Hiểu SimpleMeterRegistry không tự export dữ liệu ra hệ thống bên ngoài.

Khi hoàn thành bài, bạn đã có một chương trình nhỏ dùng đủ Counter, Gauge, Timer và SimpleMeterRegistry. Cấu trúc này là nền tảng để chuyển sang registry backend, thêm histogram, tích hợp Spring Boot và kiểm thử instrumentation trong một ứng dụng thực tế.
