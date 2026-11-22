# Kiểm thử meter bằng SimpleMeterRegistry và cô lập trạng thái giữa các lần chạy

Giả sử một tác vụ nhập tệp cần ghi lại số bản ghi nhập thành công và thời gian chạy. Một bài kiểm thử tốt phải chứng minh đúng meter được cập nhật với đúng số liệu. Bài kiểm thử cũng cần cho cùng kết quả khi chạy riêng, chạy cùng các ca khác hoặc chạy lại trong cùng JVM.

`SimpleMeterRegistry` giữ số liệu trong bộ nhớ và không gửi chúng sang hệ thống giám sát. Hãy truyền registry này vào đối tượng cần kiểm thử qua constructor, chạy hành vi nghiệp vụ rồi đọc số đo trực tiếp. Như vậy bài kiểm thử dùng meter thật của Micrometer với dữ liệu do nó kiểm soát. [Registry của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)

## Chọn số đo cần đối chiếu

| Meter | Ý nghĩa trong ví dụ | Giá trị cần kiểm tra |
| --- | --- | --- |
| `Counter` tên `import.records` | Tổng số bản ghi mà các lần nhập thành công báo đã nhập. | `count()` tăng theo số bản ghi. |
| `Timer` tên `import.duration` | Số lần thực thi và tổng thời lượng, bao gồm lần thực thi ném ngoại lệ. | `count()` và `totalTime(TimeUnit.MILLISECONDS)`. |

Cả hai meter có tag `source=csv` trong bài kiểm thử. Khi đọc số đo, chọn theo tên, tag và kiểu meter. Hai lần nhập có thể nhập tổng cộng năm bản ghi. Khi đó counter tăng năm và timer đếm hai lần thực thi. Nếu cần đếm số lần thực thi, có thể dùng ngay `Timer.count()`. [Counter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html) · [Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)

## Ví dụ Java và JUnit

Ví dụ dùng Java 17 trở lên, Gradle và Micrometer 1.13.0 theo danh mục phụ thuộc của Spring Boot 3.3.0. Tạo ba tệp sau trong một thư mục thử nghiệm riêng.

**`build.gradle`**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'io.micrometer:micrometer-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

**`src/main/java/demo/metrics/ImportJob.java`**

```java
package demo.metrics;

import java.util.function.IntSupplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class ImportJob {

    private final Counter importedRecords;
    private final Timer duration;

    public ImportJob(MeterRegistry registry, String source) {
        this.importedRecords = registry.counter("import.records", "source", source);
        this.duration = registry.timer("import.duration", "source", source);
    }

    public int run(IntSupplier importRecords) {
        return duration.record(() -> {
            int count = importRecords.getAsInt();
            if (count > 0) {
                importedRecords.increment(count);
            }
            return count;
        });
    }
}
```

`ImportJob` giữ các meter đã đăng ký trong trường của đối tượng. `IntSupplier` đại diện cho thao tác nhập và trả về số bản ghi đã nhập. Nếu thao tác ném ngoại lệ trước khi trả kết quả, counter giữ nguyên. Timer vẫn ghi một lần thực thi và ngoại lệ tiếp tục truyền đến bên gọi.

**`src/test/java/demo/metrics/ImportJobTest.java`**

```java
package demo.metrics;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ImportJobTest {

    private MockClock clock;
    private SimpleMeterRegistry registry;
    private ImportJob job;

    @BeforeEach
    void setUp() {
        clock = new MockClock();
        registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        job = new ImportJob(registry, "csv");
    }

    @AfterEach
    void closeRegistry() {
        registry.close();
    }

    @Test
    void countsRecordsAndAccumulatesTheDurationOfTwoRuns() {
        assertEquals(0.0, records().count());
        assertEquals(0L, duration().count());

        assertEquals(2, job.run(() -> {
            clock.add(20, TimeUnit.MILLISECONDS);
            return 2;
        }));
        assertEquals(3, job.run(() -> {
            clock.add(30, TimeUnit.MILLISECONDS);
            return 3;
        }));

        assertEquals(5.0, records().count());
        assertEquals(2L, duration().count());
        assertEquals(50.0, duration().totalTime(TimeUnit.MILLISECONDS), 0.000001);
        assertNull(registry.find("import.records").tag("source", "json").counter());
    }

    @Test
    void timesAFailedRunWithoutCountingImportedRecords() {
        assertEquals(0.0, records().count());
        assertEquals(0L, duration().count());

        var failure = new IllegalStateException("invalid input");
        var thrown = assertThrows(IllegalStateException.class, () -> job.run(() -> {
            clock.add(7, TimeUnit.MILLISECONDS);
            throw failure;
        }));

        assertSame(failure, thrown);
        assertEquals(0.0, records().count());
        assertEquals(1L, duration().count());
        assertEquals(7.0, duration().totalTime(TimeUnit.MILLISECONDS), 0.000001);
    }

    private Counter records() {
        return registry.get("import.records").tag("source", "csv").counter();
    }

    private Timer duration() {
        return registry.get("import.duration").tag("source", "csv").timer();
    }
}
```

- **Tạo đồng hồ và registry mới trong `@BeforeEach`.** Đối tượng `ImportJob` cũng được tạo lại để các trường meter đều trỏ đến registry của ca hiện tại. Hai lần gọi trong cùng ca thành công dùng chung registry để kiểm tra tính cộng dồn. Ca lỗi bắt đầu lại với số đo bằng 0.
- **Điều khiển thời gian bằng `MockClock`.** Truyền cùng đồng hồ vào registry rồi tăng thời gian ngay bên trong thao tác được đo. Timer thấy chính xác khoảng thời gian đã tăng. Bài kiểm thử không cần `Thread.sleep` hay phụ thuộc vào tốc độ máy chạy.
- **Tìm meter đã đăng ký.** Dùng `registry.get(...)` kèm tag và kiểu meter để ca kiểm thử thất bại nếu không tìm thấy meter mong đợi. Dùng `registry.find(...)` khi muốn kiểm tra trường hợp không có meter. Gọi `registry.counter(...)` trong phần đối chiếu có thể tự đăng ký một counter mới và che mất lỗi thiếu đăng ký.
- **Đóng registry do ca kiểm thử sở hữu.** `@AfterEach` gọi `close()` sau mỗi ca. Việc bắt đầu từ số đo bằng 0 đến từ tạo registry mới trong `@BeforeEach`.

Chạy từ thư mục chứa `build.gradle`.

```bash
gradle test --tests demo.metrics.ImportJobTest
```

Kỳ vọng cả hai ca đều đạt. Ca thành công kiểm tra năm bản ghi, hai lần thực thi và tổng thời lượng 50 ms. Ca lỗi kiểm tra không có bản ghi nào được cộng, timer ghi một lần với 7 ms và ngoại lệ gốc được ném tiếp đến bên gọi.

## Xử lý khi trạng thái bị chia sẻ

**Registry toàn cục.** Các lệnh như `Metrics.counter(...)` dùng `Metrics.globalRegistry`, là trạng thái tĩnh của JVM. Khi code nhận registry qua constructor, bài kiểm thử có thể cung cấp registry riêng. Nếu cần kiểm thử code cũ dùng registry toàn cục, giới hạn phạm vi chạy và gọi `Metrics.removeRegistry(registry)` để gỡ registry tạm do ca đó thêm vào, rồi đóng registry đó trong bước dọn dẹp. Tránh chạy song song các ca cùng sửa registry toàn cục vì chúng có thể ghi vào số đo của nhau. [Global registry của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)

**Registry do Spring quản lý.** Spring Test có thể dùng lại cùng ngữ cảnh cho các ca có cấu hình giống nhau. Khi đó bean registry và các đối tượng đang giữ meter có thể tồn tại qua nhiều ca. Nếu chủ đích của bài kiểm thử là dùng chung một registry, đọc số đếm trước hành động và kiểm tra phần tăng sau hành động. Chỉ dùng cách này khi ca kiểm thử kiểm soát được mọi ghi nhận vào cùng meter trong khoảng đo. [Bộ nhớ đệm ngữ cảnh Spring Test](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)

**Xóa đăng ký meter.** `registry.clear()` gỡ các meter khỏi registry. Một đối tượng đã lưu `Counter` hoặc `Timer` trong trường vẫn giữ tham chiếu cũ. Nếu mục tiêu là chạy lại với trạng thái mới, tạo lại registry và đối tượng sử dụng nó cùng nhau như trong ví dụ.

Các kiểm thử trên xác nhận hành vi ghi số đo và việc cô lập trạng thái. Kiểm tra số liệu xuất hiện tại `/actuator/metrics` hoặc được chuyển đến một hệ thống giám sát cần chạy qua cấu hình Actuator và bộ xuất số liệu tương ứng. [Metrics trong Spring Boot Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
