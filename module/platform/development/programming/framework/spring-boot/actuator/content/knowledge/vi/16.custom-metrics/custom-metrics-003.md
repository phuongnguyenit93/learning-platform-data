# Đăng ký Timer để đo thời lượng và số lần thực hiện

## 1. Timer giải quyết câu hỏi nào?

Giả sử ứng dụng có một thao tác dựng báo cáo. Biết thao tác được gọi bao nhiêu lần chưa cho biết mỗi lần mất bao lâu; chỉ lưu một thời gian gần nhất cũng không cho biết tải xử lý trong cả khoảng quan sát.

`Timer` của Micrometer ghi nhận các lần thực hiện cùng thời lượng tương ứng. Từ cùng một phép đo, bạn có **số lần được ghi nhận** và **tổng thời gian** của những lần đó. Đây là lựa chọn tự nhiên khi câu hỏi là “thao tác diễn ra bao nhiêu lần và tốn bao lâu?”. Nếu chỉ cần biết một trạng thái tức thời, chẳng hạn độ dài hàng đợi hiện tại, đó là một câu hỏi khác.

Bài này dùng Micrometer **1.13.x**, tương ứng phạm vi Spring Boot **3.3.x**. Ví dụ ghim Boot 3.3.0 để quản lý dependency, chạy bằng JDK 21 và dùng cú pháp Java 17+.

Cần phân biệt hai đối tượng ngay từ đầu:

- **Timer:** meter có tên và nhãn, tích lũy các phép đo; thường được đăng ký rồi tái sử dụng cho nhiều lời gọi.
- **Timer.Sample:** trạng thái bắt đầu của **một lần** đo, dùng khi muốn quyết định thời điểm dừng hoặc chọn nhóm kết quả sau khi công việc kết thúc.

Đăng ký Timer không có nghĩa tác vụ đã chạy. Timer cũng không tự biết một phương thức bất kỳ vừa được gọi; mã hoặc tích hợp quan sát phải ghi nhận sự kiện vào nó.

## 2. Hiểu một lần ghi vào Timer

Với một Timer quan sát ba lần dựng báo cáo có thời lượng 10 ms, 25 ms và 5 ms:

```text
COUNT      = 3
TOTAL_TIME = 40 ms
MEAN       = 40 / 3 ≈ 13.33 ms
```

Số đếm ở đây là số mẫu thời lượng đã được ghi, không mặc định là số request HTTP, số người dùng hay số nghiệp vụ thành công. Nếu lần thứ ba ném ngoại lệ nhưng vẫn nằm trong khối được Timer đo, đó vẫn có thể là một lần được ghi nhận.

Timer đã cung cấp số đếm, nên không cần thêm Counter chỉ để đếm lại đúng tập sự kiện và cùng ranh giới đó. Một Counter riêng vẫn có ý nghĩa nếu nó biểu diễn sự kiện khác, chẳng hạn yêu cầu bị từ chối trước khi bước dựng báo cáo bắt đầu. Xem [quan hệ giữa Counter và Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

Khi đọc thời gian, luôn chỉ rõ đơn vị. `timer.totalTime(TimeUnit.MILLISECONDS)` trả tổng theo mili giây; đổi sang giây thì cùng lượng thời gian 40 ms trở thành 0,04 giây. Tên meter không nên bị hiểu như một cam kết rằng mọi backend sẽ dùng cùng đơn vị biểu diễn.

## 3. Đăng ký và giữ lại Timer

Một khai báo thường có hình dạng sau; đây là fragment trong ngữ cảnh đã có biến `MeterRegistry registry`:

```java
Timer buildTimer = Timer.builder("demo.report.build")
        .description("Time spent building reports")
        .tag("format", "csv")
        .register(registry);
```

Ý nghĩa của từng phần:

| Thành phần | Vai trò |
| --- | --- |
| `Timer.builder(...)` | Chuẩn bị định nghĩa meter; chưa thực hiện công việc nghiệp vụ |
| Tên `demo.report.build` | Nhận diện loại thao tác được đo |
| `description(...)` | Giải thích ý nghĩa cho người đọc số liệu |
| `tag("format", "csv")` | Phân nhóm bằng một chiều thông tin có tập giá trị kiểm soát được |
| `register(registry)` | Đưa định nghĩa vào registry và nhận Timer dùng để ghi |

Định danh meter dựa trên tên và bộ nhãn trong registry, sau những biến đổi liên quan nếu có filter. Đăng ký lại cùng tên/nhãn với cùng loại meter trong ví dụ không tạo một bộ đếm độc lập hoặc xóa số liệu cũ. Nếu cần một tập phép đo khác, hãy thiết kế định danh khác có ý nghĩa; không trông chờ việc tạo thêm biến Java sẽ tạo thêm một lịch sử mới.

Với tập nhãn cố định, đăng ký một lần trong constructor hoặc cấu hình rồi giữ Timer ở trường `final` giúp ý định dễ đọc. Với nhãn chỉ xác định ở cuối thao tác, có thể tra cứu/đăng ký Timer theo nhóm kết quả hữu hạn như ví dụ `Timer.Sample` phía dưới. Điều cần tránh là tạo tên/nhãn mới cho từng yêu cầu.

Dùng `io.micrometer.core.instrument.Timer`; Java cũng có `java.util.Timer`, nhưng đó là lớp phục vụ lập lịch, không phải meter đang học trong bài.

## 4. Các cách ghi thời lượng

| API | Trường hợp sử dụng | Điểm cần nhớ |
| --- | --- | --- |
| `record(Runnable)` | Khối lệnh không cần trả kết quả | Đo lần thực thi khối lệnh |
| `record(Supplier<T>)` | Khối lệnh trả kết quả, không khai báo checked exception | Trả lại kết quả của Supplier |
| `recordCallable(Callable<T>)` | Công việc có thể khai báo checked exception | API khai báo `throws Exception`; bên gọi phải xử lý hoặc khai báo phù hợp |
| `record(long, TimeUnit)` / `record(Duration)` | Đã có thời lượng được đo ở nơi khác | Ghi mẫu thời gian, không tự chạy tác vụ |
| `Timer.Sample` + `stop(timer)` | Điểm bắt đầu/dừng tách nhau hoặc nhãn phụ thuộc kết quả | Mỗi lần thực thi cần Sample riêng và đường dừng đúng một lần |

Các khối đồng bộ được `record`/`recordCallable` bọc vẫn được ghi thời lượng khi công việc ném ngoại lệ. API không biến lỗi thành thành công, không tự phục hồi tác vụ và không tự thêm nhãn `outcome`/`exception` vào Timer thủ công. Bạn phải quyết định cách phân loại nếu cần.

Ví dụ ghi một thời lượng đã biết, trong ngữ cảnh đã có Timer:

```java
buildTimer.record(15, TimeUnit.MILLISECONDS);
```

Dòng này thêm **một** mẫu 15 ms; nó không chờ 15 ms và không gọi hàm dựng báo cáo. Chỉ ghi khi giá trị đại diện cho một sự kiện có thật cần đo. Không truyền thời lượng âm, không nhầm timestamp kể từ epoch với một khoảng thời gian, và không đổi đơn vị bằng phỏng đoán.

Xem [các dạng ghi thời gian của Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html). Các ví dụ hoàn chỉnh tiếp theo kiểm chứng cụ thể cách đếm, truyền kết quả và xử lý nhánh lỗi.

## 5. Chương trình chạy được với thời lượng xác định

Để kiểm tra số liệu mà không phụ thuộc tải máy, ví dụ dùng `MockClock`. Mã chủ động tăng đồng hồ của registry; không dùng `Thread.sleep` và không coi các con số giả lập là thời gian thực tế của thuật toán.

Tạo dự án:

```text
timer-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/TimerDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'timer-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'io.micrometer:micrometer-core'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = providers.gradleProperty('demoMain').getOrElse('TimerDemo')
}
```

BOM của Boot chỉ quản lý phiên bản dependency; chương trình đầu tiên chưa khởi động Spring. Cần Gradle 8.5 và JDK 21 cho cấu hình này. Lần đầu phân giải dependency cần truy cập Maven Central; dự án có wrapper tương thích có thể dùng wrapper thay lệnh `gradle`.

**`src/main/java/TimerDemo.java`**

```java
import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class TimerDemo {
    public static void main(String[] args) throws Exception {
        basicMeasurements();
        measurementsByOutcome();
    }

    private static void basicMeasurements() throws Exception {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            Timer timer = Timer.builder("demo.report.build")
                    .description("Time spent building reports")
                    .tag("format", "csv")
                    .register(registry);

            System.out.println("BEFORE_COUNT=" + timer.count());

            timer.record(() -> {
                clock.add(Duration.ofMillis(10));
            });

            String result = timer.record(() -> {
                clock.add(Duration.ofMillis(25));
                return "report.csv";
            });
            System.out.println("RESULT=" + result);

            try {
                timer.recordCallable(() -> {
                    clock.add(Duration.ofMillis(5));
                    throw new IOException("Cannot read source");
                });
            } catch (IOException expected) {
                System.out.println("ERROR=" + expected.getClass().getSimpleName());
            }

            Timer same = Timer.builder("demo.report.build")
                    .tag("format", "csv")
                    .register(registry);

            System.out.println("SAME_INSTANCE=" + (same == timer));
            System.out.println("COUNT=" + timer.count());
            System.out.printf(Locale.ROOT, "TOTAL_MS=%.2f%n",
                    timer.totalTime(TimeUnit.MILLISECONDS));
            System.out.printf(Locale.ROOT, "MEAN_MS=%.2f%n",
                    timer.mean(TimeUnit.MILLISECONDS));
        } finally {
            registry.close();
        }
    }

    private static void measurementsByOutcome() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            attemptPayment(registry, clock, false);
            try {
                attemptPayment(registry, clock, true);
            } catch (IllegalStateException expected) {
                // Chỉ tiếp tục để đọc cả hai nhóm kết quả trong ví dụ.
            }

            Timer success = registry.get("demo.payment.duration")
                    .tag("outcome", "success").timer();
            Timer error = registry.get("demo.payment.duration")
                    .tag("outcome", "error").timer();

            System.out.printf(Locale.ROOT, "SUCCESS count=%d totalMs=%.0f%n",
                    success.count(), success.totalTime(TimeUnit.MILLISECONDS));
            System.out.printf(Locale.ROOT, "ERROR count=%d totalMs=%.0f%n",
                    error.count(), error.totalTime(TimeUnit.MILLISECONDS));

            long total = registry.find("demo.payment.duration")
                    .timers().stream().mapToLong(Timer::count).sum();
            System.out.println("ALL_OUTCOMES_COUNT=" + total);
        } finally {
            registry.close();
        }
    }

    private static void attemptPayment(SimpleMeterRegistry registry,
                                       MockClock clock, boolean fail) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "error";
        try {
            clock.add(Duration.ofMillis(fail ? 7 : 30));
            if (fail) {
                throw new IllegalStateException("Payment rejected");
            }
            outcome = "success";
        } finally {
            sample.stop(registry.timer("demo.payment.duration",
                    "outcome", outcome));
        }
    }
}
```

Chạy từ thư mục dự án:

```shell
gradle --console=plain run
```

Các dòng do chương trình in ra là:

```text
BEFORE_COUNT=0
RESULT=report.csv
ERROR=IOException
SAME_INSTANCE=true
COUNT=3
TOTAL_MS=40.00
MEAN_MS=13.33
SUCCESS count=1 totalMs=30
ERROR count=1 totalMs=7
ALL_OUTCOMES_COUNT=2
```

Gradle có thể in thêm thông tin tác vụ. Khi biên dịch trực tiếp bằng `javac`, phải cấp classpath gồm Micrometer và dependency của nó; chỉ đưa tên tệp Java cho compiler sẽ không cung cấp các lớp ngoài JDK.

Ví dụ dùng `Locale.ROOT` để dấu thập phân trong output luôn là dấu chấm. `SimpleMeterRegistry` ở đây do chương trình sở hữu, nên được đóng trong `finally`; không dùng mẫu `try` với tài nguyên `AutoCloseable` cho lớp này ở API Micrometer 1.13.

### Đọc phần đo cơ bản

- `BEFORE_COUNT=0` cho thấy việc đăng ký chưa tạo một lần thực hiện.
- Khối Runnable ghi 10 ms. Supplier ghi 25 ms và vẫn trả lại chuỗi `report.csv` cho bên gọi.
- Callable tăng đồng hồ thêm 5 ms rồi ném `IOException`. Ngoại lệ đến bên gọi và mẫu thời gian vẫn được ghi: tổng cộng ba mẫu, tổng 40 ms.
- `SAME_INSTANCE=true` kiểm chứng việc đăng ký lại cùng tên/nhãn trong registry này trả về cùng Timer; nó không đặt count về 0.
- Trung bình 13,33 ms được tính từ đúng ba mẫu trên, bao gồm lần kết thúc bằng ngoại lệ.

Hai phần của chương trình dùng hai registry riêng. Vì vậy thời gian và số đếm của phần thanh toán không được cộng vào Timer dựng báo cáo.

## 6. Timer.Sample: chọn nhóm kết quả sau khi công việc kết thúc

Phần `measurementsByOutcome` minh họa một nhu cầu khác: lúc bắt đầu chưa chắc đã biết thao tác sẽ thành công hay lỗi. `Timer.Sample` lưu thời điểm bắt đầu bằng đồng hồ của registry; đến cuối mới chọn Timer có nhãn phù hợp.

Trong `attemptPayment`:

1. Mỗi lời gọi tạo một Sample mới.
2. Biến kết quả bắt đầu bằng `error`, rồi chuyển sang `success` khi thân xử lý đi đến nhánh thành công.
3. `finally` dừng Sample vào Timer của nhóm kết quả đã xác định.
4. Ngoại lệ vẫn truyền ra ngoài; phần ghi nhận không thay thế chính sách xử lý lỗi của ứng dụng.

Bài thực hành chỉ có hai giá trị nhãn: `success` và `error`. Lần thành công ghi 30 ms vào nhóm thứ nhất; lần lỗi ghi 7 ms vào nhóm thứ hai. Tổng các count theo hai nhóm bằng 2, không phải một Timer duy nhất tự có hai bộ giá trị khác nhau.

Trong ví dụ này, `registry.timer(...)` ở điểm dừng có chủ đích: lấy hoặc đăng ký đúng Timer của nhóm kết quả hữu hạn. Khi chỉ muốn hỏi “meter đã tồn tại chưa?”, dùng `registry.find(...)` để tra cứu mà không tự tạo một meter mới.

**Một Sample chỉ nên được dừng đúng một lần cho một lần thực hiện.** Không dừng ở cả nhánh thành công rồi lại dừng trong `finally`; gọi `stop` lặp có thể ghi thêm mẫu và làm count lớn hơn số thao tác. Ngược lại, nếu quên đường dừng khi có lỗi, bạn sẽ làm mất mẫu của nhánh lỗi và có thể khiến số liệu nhìn tốt hơn thực tế.

Biến kết quả của ví dụ là một quy ước đo lường. Trong nghiệp vụ thật, có thể cần phân biệt bị từ chối, hết thời gian hoặc hoàn tất; hãy chọn các nhóm hữu hạn, có định nghĩa rõ. Một hàm trả về `false` mà không ném ngoại lệ có thể vẫn là kết quả nghiệp vụ không đạt yêu cầu; Timer không tự quyết định điều đó thay bạn.

## 7. Đưa Timer vào service của Spring Boot

Trong ứng dụng Boot, inject `MeterRegistry` mà ứng dụng đang dùng. Không tự tạo một `SimpleMeterRegistry` bên trong mỗi service nếu muốn số liệu đi cùng hệ thống metrics của ứng dụng. Registry riêng ở ví dụ trước phục vụ thực nghiệm độc lập.

Để chạy bản Boot trong cùng dự án, thêm dòng sau vào khối `dependencies` đã có:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Tạo ba tệp dưới đây. Lớp service chỉ mô phỏng kết quả thành công/lỗi để làm rõ cơ chế đo; nó không mô phỏng một hệ thống tạo báo cáo hoàn chỉnh.

**`src/main/java/demo/ReportService.java`**

```java
package demo;

import java.io.IOException;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final Timer buildTimer;

    public ReportService(MeterRegistry registry) {
        this.buildTimer = Timer.builder("demo.report.build")
                .description("Time spent building reports")
                .tag("format", "csv")
                .register(registry);
    }

    public String build(boolean fail) throws Exception {
        return buildTimer.recordCallable(() -> {
            if (fail) {
                throw new IOException("Cannot read source");
            }
            return "report.csv";
        });
    }
}
```

Timer được đăng ký trong constructor và giữ ở trường `final`. Mỗi lần `build` gọi `recordCallable` để đo đúng phần công việc được chọn. Chữ ký `throws Exception` ở ví dụ phản ánh hợp đồng của `recordCallable`; khi tích hợp vào API nghiệp vụ thật, cần chuyển tiếp hoặc ánh xạ ngoại lệ theo hợp đồng của API đó, thay vì bắt mọi lỗi rồi bỏ qua.

**`src/main/java/demo/TimerApplication.java`**

```java
package demo;

import java.io.IOException;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TimerApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimerApplication.class, args);
    }

    @Bean
    ApplicationRunner experiment(ReportService service, MeterRegistry registry) {
        return args -> {
            service.build(false);
            try {
                service.build(true);
            } catch (IOException expected) {
                System.out.println("BOOT_ERROR=" + expected.getClass().getSimpleName());
            }
            Timer timer = registry.get("demo.report.build")
                    .tag("format", "csv").timer();
            System.out.println("BOOT_COUNT=" + timer.count());
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

Chạy biến thể Boot nhờ thuộc tính main class đã khai báo trong build:

```shell
gradle --console=plain run -PdemoMain=demo.TimerApplication
```

Với tiến trình mới và không có lời gọi bổ sung, các dòng của ứng dụng là:

```text
BOOT_ERROR=IOException
BOOT_COUNT=2
```

`ApplicationRunner` gọi service một lần thành công và một lần lỗi. Dù runner bắt ngoại lệ để tiếp tục đọc meter, nhánh lỗi đã được Timer ghi nhận nên count là 2. Trong ứng dụng thật, việc tiếp tục, trả lỗi hay thử lại phải theo chính sách nghiệp vụ; đoạn bắt lỗi ở đây chỉ phục vụ thực nghiệm.

Biến thể này không thêm web starter, nên không có HTTP server hay endpoint HTTP để gọi. Timer vẫn hoạt động trong registry. Cũng không cần `@Timed` hoặc một aspect chỉ để sử dụng các lệnh `Timer.recordCallable` tường minh ở trên.

Spring Boot cung cấp cấu hình registry và các điểm tùy biến metrics; xem [metrics trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html). Registry do Spring quản lý có vòng đời của ứng dụng; service không tự đóng registry được inject trong lúc các thành phần khác còn sử dụng.

## 8. Đọc qua Actuator trong ứng dụng có web

Nếu áp dụng `ReportService` vào một ứng dụng Boot đang có web server, có thể mở endpoint chẩn đoán:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Sau khi tạo các lời gọi service, đọc đúng tên và nhãn:

```shell
curl http://localhost:8080/actuator/metrics/demo.report.build
curl --get http://localhost:8080/actuator/metrics/demo.report.build --data-urlencode "tag=format:csv"
```

Trên Windows PowerShell, dùng `curl.exe` khi `curl` là alias của lệnh khác. Địa chỉ phải khớp management port, base path và quyền truy cập thực tế của ứng dụng.

Tìm `COUNT` và `TOTAL_TIME` trong `measurements`; kiểm tra `baseUnit` trước khi so sánh với một con số được in theo mili giây. Với Timer của nhánh `format=csv`, đừng cộng số liệu của định dạng khác vào kết quả mà bạn đang diễn giải.

Tên dùng trong đường dẫn Actuator là tên gốc như `demo.report.build`, không phải tên đã được chuẩn hóa bởi một bộ xuất. Các nhãn đang có có thể được xem ở `availableTags`. Endpoint này để chẩn đoán tức thời; để lưu lịch sử và dựng cảnh báo, cần bộ xuất/backend phù hợp. Xem [REST API metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Mở endpoint không tự đăng ký Timer và không tạo một lần gọi service. Ngược lại, endpoint chưa được expose không làm cho một Timer đã ghi trong registry tự biến mất.

## 9. Thiết kế tên và nhãn để số liệu còn sử dụng được

Đặt tên biểu diễn một loại công việc ổn định, ví dụ `demo.report.build`; dùng tag cho các chiều phân nhóm có giá trị giới hạn như `format=csv/pdf`. Không tạo tên mới theo ID báo cáo và không dùng email, ID người dùng hoặc thông báo ngoại lệ đầy đủ làm giá trị tag.

Mỗi tổ hợp nhãn có thể tạo một chuỗi số liệu khác. Khi phân loại theo kết quả, giữ bộ khóa nhãn nhất quán: chẳng hạn mọi meter cùng tên đều có `outcome`, với giá trị hữu hạn. Một nhánh có khóa `outcome`, nhánh khác chỉ có khóa `exception` sẽ khó tổng hợp và có thể vi phạm yêu cầu của backend.

Description giải thích ý nghĩa; nó không phải một chiều định danh thay cho tag. Đừng đăng ký lại cùng định danh với description/cấu hình khác rồi trông chờ mọi metadata hoặc phân bố được cập nhật theo lần khai báo sau. Thiết lập định nghĩa và cấu hình dự kiến trước khi meter được sử dụng.

Xem [quy tắc đặt tên và giá trị tag](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html). Nếu có filter đổi tên hoặc bỏ nhãn, cần đánh giá định danh sau biến đổi để tránh các phép đo khác nhau vô tình bị gộp.

## 10. Chọn đúng ranh giới và giải thích đúng số đếm

### Một lần thử hay một nghiệp vụ hoàn chỉnh?

Một lần xử lý nghiệp vụ có thể thử dựng báo cáo nhiều lần. Timer đặt bên trong mỗi lần thử đo số lần thử; Timer đặt bên ngoài toàn bộ quy trình đo một lần xử lý bao gồm cả các lần thử lại. Cả hai đều có thể hữu ích nhưng phải có tên/ý nghĩa riêng; không đổi cách đặt Timer giữa các phiên bản rồi so sánh số đếm như cùng một loại sự kiện.

Nếu đã có phép đo tự động ở tầng HTTP hoặc repository, một Timer nghiệp vụ chỉ nên bổ sung khi nó trả lời câu hỏi ở một ranh giới khác. Nếu bọc hai lần bằng cùng Timer cho một thao tác, có thể ghi hai mẫu cho một lần thực hiện và làm sai cả count lẫn tổng thời gian.

### Công việc bất đồng bộ đã thực sự hoàn tất chưa?

Khối `record(() -> executor.submit(...))` chủ yếu bao quanh thao tác gửi công việc, không mặc định bao quanh toàn bộ thời gian công việc nền chạy xong. Muốn đo thời gian làm việc trong worker, đặt phép đo ở đường thực thi worker. Muốn bao gồm cả chờ hàng đợi, phải xác định mốc bắt đầu sớm hơn và kết thúc khi công việc hoàn tất theo hợp đồng mong muốn.

`Timer.Sample` có thể hỗ trợ tách mốc bắt đầu/kết thúc, nhưng bạn vẫn phải quản lý đúng một lần dừng cho mỗi lần thực hiện, kể cả lỗi/hủy/từ chối gửi công việc. Không coi việc tạo một Sample là tự động xử lý mọi nhánh bất đồng bộ.

### Dùng chung Timer, tạo riêng Sample

Timer được thiết kế để dùng chung cho việc ghi metrics từ nhiều lời gọi. Giữ một Timer cố định trong service không có nghĩa mọi lời gọi dùng chung một thời điểm bắt đầu. Ngược lại, Sample là trạng thái của một lần đo; không đặt một Sample dùng lại ở trường singleton cho mọi request.

Khi kiểm tra trong môi trường có nhiều luồng, tổng số có thể thay đổi ngay giữa các lần đọc. Các kết quả số học chính xác trong ví dụ dùng đồng hồ giả lập và không có lời gọi đồng thời.

## 11. Những thống kê không nên suy diễn quá mức

Trong `SimpleMeterRegistry` của ví dụ, count và tổng thời gian là các giá trị cộng dồn của những mẫu đã ghi vào Timer đó. Đổi registry/backend có thể thay đổi cách trình bày theo bước/cửa sổ thu thập, nên phải đọc đúng quy ước của hệ thống đang dùng.

Khi cần trung bình của nhiều nhóm hoặc instance, lấy tổng thời gian của các nhóm chia cho tổng count trong cùng phạm vi/cửa sổ; không lấy trung bình cộng các giá trị trung bình khi số sự kiện của mỗi nhóm khác nhau. Không chia khi count bằng 0. Số đếm tuyệt đối cũng phụ thuộc vòng đời tiến trình; để đọc tốc độ xử lý trong một khoảng, dùng biến thiên/tốc độ tương ứng ở backend.

Thời gian lớn nhất `MAX` của Timer thường liên quan cửa sổ thống kê, không phải một cam kết giữ “kỷ lục từ khi chương trình được triển khai”. Cũng không thể suy ra p95/p99 chỉ từ count, tổng và trung bình. Những yêu cầu phân bố cần histogram/percentile và backend hỗ trợ tương ứng; xem [Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

Timer thông thường ghi nhận thời lượng khi mẫu được hoàn tất; count không phải số tác vụ hiện đang chạy. Nếu câu hỏi là “hiện có bao nhiêu tác vụ kéo dài và chúng đã chạy bao lâu?”, xem xét `LongTaskTimer` theo đúng mục tiêu đó. Xem [phân biệt Long Task Timer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html).

## 12. Lỗi phổ biến và bài tập kiểm chứng

| Lỗi | Hệ quả | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ tạo builder, chưa register | Chưa có Timer dùng để ghi vào registry | Giữ kết quả của `register(registry)` |
| Chỉ register, chưa record | Meter có thể tồn tại nhưng chưa có mẫu | Gọi một tác vụ được bọc và so sánh count trước/sau |
| Dùng registry riêng trong service | Actuator/bộ xuất của ứng dụng không đọc đúng nơi bạn ghi | Inject registry ứng dụng đang quản lý |
| Bỏ nhánh lỗi khi dừng Sample | Thiếu thời gian và số lần thực hiện bị lỗi | Bảo đảm đường hoàn tất/lỗi đều được ghi theo hợp đồng |
| Dừng cùng Sample hai lần hoặc bọc cùng Timer hai lớp | Đếm và cộng thời gian trùng | Kiểm tra vị trí `record`/`stop` trên một đường gọi |
| Dùng count như số thành công | Hiểu sai các mẫu kết thúc bằng ngoại lệ hoặc kết quả nghiệp vụ không đạt | Tách nhóm kết quả hữu hạn khi thực sự cần |
| Ghi thời gian nhưng sai đơn vị | Tổng/độ trễ sai nhiều bậc | Chỉ rõ TimeUnit/Duration tại nơi ghi và nơi đọc |
| Tạo tên/tag theo từng yêu cầu | Tăng số meter và chi phí giám sát | Dùng tên ổn định, nhãn có giới hạn |
| Có mã ghi nhưng số liệu không xuất hiện | Có thể bị filter từ chối hoặc đang tra cứu sai tên/nhãn | Kiểm tra registry, filter và đúng định danh |

Filter có thể từ chối meter, biến đổi định danh hoặc cấu hình phân bố. Một đối tượng Timer được trả về không có nghĩa mọi cấu hình hiện tại đều cho phép số liệu được lưu/xuất như bạn mong muốn. Xem [Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Tự kiểm chứng bằng các thay đổi nhỏ, từng lần trên một registry mới:

1. Đổi thời gian Callable bị lỗi từ 5 ms thành 15 ms: dự đoán count vẫn bằng 3, tổng thành 50 ms; giải thích vì sao lỗi không làm mất mẫu.
2. Sau phần đo cơ bản, ghi thêm mẫu tường minh 15 ms: dự đoán count từ 3 thành 4 và tổng từ 40 thành 55 ms. Phân biệt việc ghi một mẫu với chạy tác vụ.
3. Thêm một lần thanh toán thành công vào ví dụ Sample: nhóm success có count 2, nhóm error có count 1; tổng count hai nhóm bằng 3.
4. Xác định một thao tác trong ứng dụng của bạn, ghi rõ mốc bắt đầu, mốc kết thúc, việc có tính các lần thử lại hay không và tập nhãn được phép dùng.

Một Timer có ích khi người đọc biết chính xác một mẫu đại diện cho lần thực hiện nào, thời lượng bao phủ đoạn công việc nào và số đếm bao gồm những kết quả nào. Đăng ký đúng API là bước đầu; ranh giới và định nghĩa sự kiện mới quyết định số liệu có trả lời được câu hỏi vận hành hay không.
