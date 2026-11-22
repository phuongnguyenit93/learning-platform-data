# Kết hợp nhiều registry và vai trò của global registry

Một dịch vụ cần để Prometheus thu thập số đơn đã nhận, đồng thời gửi số đo đó qua OTLP. Phần xử lý đơn hàng có thể ghi một lần qua Micrometer. Việc số đo đến đâu phụ thuộc vào registry mà mã gọi sử dụng và các registry đích được nối vào đó.

## Registry đích, composite và global registry

| Thành phần | Vai trò | Cách mã ứng dụng sử dụng |
| --- | --- | --- |
| Registry đích, ví dụ `PrometheusMeterRegistry` hoặc `OtlpMeterRegistry` | Giữ và biểu diễn số đo theo quy ước của một hệ thống giám sát. | Dùng trực tiếp khi cần một tính năng riêng của đích, chẳng hạn lấy dữ liệu scrape của Prometheus. |
| `CompositeMeterRegistry` | Gom nhiều registry. Một lần tăng counter qua composite chuyển lần tăng đó đến các registry đích đang được nối và chấp nhận meter. | Đăng ký và cập nhật meter qua một đầu mối chung của ứng dụng. |
| `Metrics.globalRegistry` | Một composite tĩnh của Micrometer. Nó có tập registry đích riêng, được chia sẻ giữa các nơi gọi cùng lớp `Metrics`. | Các lời gọi tĩnh như `Metrics.counter(...)` hoặc `Metrics.timer(...)` đi qua composite này. |

Composite chuyển tiếp **thao tác ghi**. Mỗi đích vẫn áp dụng quy ước tên, đơn vị, bộ lọc và cách xuất của mình. Ví dụ, Prometheus đọc theo chu kỳ scrape, còn OTLP gửi dữ liệu theo kỳ được cấu hình. Hai hệ thống có thể hiển thị số liệu ở thời điểm khác nhau dù nhận các thao tác ghi từ cùng một counter. Khi cần kiểm tra mỗi đích đã nhận gì, hãy đọc registry đích tương ứng. `count()` trên composite counter trong Micrometer 1.13 đọc từ một registry con, nên không thể dùng giá trị đó để xác minh đồng thời mọi đích.

Một meter có thể được đăng ký trước khi thêm registry đích. Khi nối registry mới, composite tạo meter tương ứng ở đó. Các lần tăng trước khi nối không được phát lại. Khi composite đang rỗng, các lần ghi vào counter của nó không có đích nhận.

## Cách Spring Boot 3.3 nối các registry

Spring Boot Actuator tự cấu hình các registry được hỗ trợ khi có dependency tương ứng và cấu hình xuất cho phép. Với nhiều bean `MeterRegistry` và chưa có một ứng viên duy nhất để inject, Spring Boot tạo một `CompositeMeterRegistry` chính chứa các registry đích. Khi chỉ có một ứng viên phù hợp, có thể inject trực tiếp bean đó. `SimpleMeterRegistry` của cơ chế tự cấu hình là lựa chọn lưu trong bộ nhớ khi thiếu registry khác.

Trong ứng dụng web, ví dụ dùng đồng thời các dependency sau và để Spring Boot quản lý phiên bản.

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
```

Với một bộ thu OTLP HTTP chạy trên cùng máy ở cổng 4318, có thể đặt cấu hình sau trong `application.properties`.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.otlp.metrics.export.url=http://localhost:4318/v1/metrics
management.metrics.use-global-registry=false
```

Prometheus được cấu hình riêng để scrape `/actuator/prometheus`. Registry OTLP gửi đến URL đã đặt. `management.metrics.use-global-registry=false` tắt việc Spring Boot tự nối các registry do Spring quản lý vào `Metrics.globalRegistry`. Các cờ bật hoặc tắt từng đích xuất hoạt động độc lập. Bean `MeterRegistry` được inject vẫn ghi đến các đích thuộc cấu hình của Spring.

Theo mặc định, Spring Boot nối các registry vào global registry, nên mã cũ gọi `Metrics.counter(...)` có thể vẫn gửi số đo tới các đích của ứng dụng. Khi đặt cờ thành `false`, lời gọi tĩnh vẫn đi vào global registry và chỉ đến được các đích đã được nối theo cách khác, chẳng hạn qua cấu hình thủ công của một thư viện.

Với mã do ứng dụng sở hữu, dùng constructor để nhận `MeterRegistry` từ Spring và giữ meter đã đăng ký trong trường. Ví dụ dưới đây là một thành phần đặt trong vùng quét bean của ứng dụng.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {
    private final Counter accepted;

    public OrderMetrics(MeterRegistry registry) {
        accepted = registry.counter("orders.accepted");
    }

    public void recordAcceptedOrder() {
        accepted.increment();
    }
}
```

Gọi `recordAcceptedOrder()` một lần sau khi đơn được chấp nhận. Các bean tùy chỉnh registry, chẳng hạn `MeterRegistryCustomizer` để đặt tag chung hoặc `MeterFilter` để lọc meter, thuộc cấu hình do Spring quản lý. Việc inject registry giữ đường ghi gắn với cấu hình ứng dụng và cho phép thay registry bằng một bản riêng trong kiểm thử.

## Thí nghiệm với hai registry trong bộ nhớ

Chương trình sau chạy độc lập với Java 17+ và `io.micrometer:micrometer-core:1.13.0` cùng các phụ thuộc lúc chạy. Hai `SimpleMeterRegistry` đóng vai trò hai đích. Chương trình tự nối và tháo global registry để quan sát luồng ghi mà không cần mở một máy chủ giám sát.

Lưu tệp `RegistryRouting.java`.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.Locale;

public class RegistryRouting {
    public static void main(String[] args) {
        CompositeMeterRegistry application = new CompositeMeterRegistry();
        SimpleMeterRegistry first = new SimpleMeterRegistry();
        SimpleMeterRegistry second = new SimpleMeterRegistry();
        Counter business = application.counter("orders.accepted");
        Counter legacy = Metrics.counter("legacy.orders.accepted");

        try {
            business.increment(10);
            legacy.increment(10);
            application.add(first);
            business.increment(2);
            application.add(second);
            printCounts("late-join", "orders.accepted", first, second);
            System.out.println("global-meter-before-link="
                    + (first.find("legacy.orders.accepted").counter() != null));

            business.increment(3);
            Metrics.addRegistry(application);
            legacy.increment();
            printCounts("application", "orders.accepted", first, second);
            printCounts("global-linked", "legacy.orders.accepted", first, second);

            Metrics.removeRegistry(application);
            legacy.increment(10);
            business.increment();
            printCounts("application-after-unlink", "orders.accepted", first, second);
            printCounts("global-unlinked", "legacy.orders.accepted", first, second);
        } finally {
            Metrics.removeRegistry(application);
            Metrics.globalRegistry.remove(legacy);
            application.close();
            first.close();
            second.close();
        }
    }

    private static void printCounts(String stage, String name,
            SimpleMeterRegistry first, SimpleMeterRegistry second) {
        System.out.printf(Locale.ROOT, "%s first=%.0f second=%.0f%n", stage,
                first.get(name).counter().count(), second.get(name).counter().count());
    }
}
```

Trên Bash, đặt `MICROMETER_CP` thành classpath chứa các JAR lúc chạy mà Maven hoặc Gradle giải quyết cho `micrometer-core:1.13.0`.

```bash
javac --release 17 -cp "$MICROMETER_CP" RegistryRouting.java
java -cp ".:$MICROMETER_CP" RegistryRouting
```

Kết quả với Micrometer 1.13.0.

```text
late-join first=2 second=0
global-meter-before-link=false
application first=5 second=3
global-linked first=1 second=1
application-after-unlink first=6 second=4
global-unlinked first=1 second=1
```

- `late-join` cho thấy 10 lượt đầu xảy ra khi composite rỗng. Registry thứ nhất nhận 2 lượt sau khi nối. Registry thứ hai được nối muộn hơn và bắt đầu tại 0.
- `global-meter-before-link=false` cho thấy registry thứ nhất chưa có meter của lời gọi tĩnh. Sau khi nối composite của ứng dụng vào global registry, cả hai registry nhận 1 lượt mới từ meter đó.
- Sau khi tháo kết nối global, một lần ghi qua composite ứng dụng vẫn tăng cả hai đích. Hai giá trị của meter tĩnh giữ ở 1 vì lần tăng mới đi vào global registry đang rỗng.

## Kiểm tra khi số đo thiếu hoặc tăng gấp đôi

1. **Xác định lời gọi đi qua đâu.** Kiểm tra đoạn mã đang dùng `registry.counter(...)` từ bean Spring, `Metrics.counter(...)` từ global, hay gọi trực tiếp một registry đích.
2. **Kiểm tra kết nối và thời điểm đăng ký.** Xem kiểu bean `MeterRegistry` được inject và `getRegistries()` nếu bean là composite. Nếu dùng global, kiểm tra thêm `Metrics.globalRegistry.getRegistries()`. Đối chiếu lúc đích được nối với lúc sự kiện đã được ghi.
3. **Đọc từng đích.** Kiểm tra meter có được chấp nhận qua bộ lọc, tên và tag sau khi xuất, rồi kiểm tra lần scrape hoặc lần gửi OTLP tương ứng. Một registry có dữ liệu vẫn có thể đi cùng một đích khác đang gặp lỗi cấu hình hoặc kết nối.
4. **Tìm hai lần ghi cho cùng sự kiện.** Khi cả composite của Spring và global registry nối đến cùng các registry đích, gọi cả hai API cho cùng một sự kiện với cùng tên và tag có thể tăng counter hai lần ở mỗi đích. Chọn một đường ghi cho sự kiện đó.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer — Registry, composite và global registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Spring Boot 3.3.0 — Cấu hình composite registry](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/CompositeMeterRegistryConfiguration.java)
- [Spring Boot 3.3.0 — Kết nối registry với global registry](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryPostProcessor.java)
