# Theo dõi công việc dài bằng LongTaskTimer

## 1. Bắt đầu từ câu hỏi: công việc còn đang chạy có bị chậm không?

Giả sử ứng dụng dựng lại báo cáo mỗi phút. Bình thường một lần chạy mất 20 giây, nhưng hôm nay lời gọi đến hệ thống lưu trữ bị chậm và công việc chạy mãi chưa xong. Bạn cần biết ngay: có bao nhiêu lần chạy đang hoạt động, chúng đã chạy tổng cộng bao lâu và lần chạy lâu nhất đã kéo dài đến mức nào?

`Timer` thông thường ghi nhận thời lượng khi bạn kết thúc phép đo. Nếu công việc chưa kết thúc, thống kê các lần đã hoàn thành chưa mô tả được chính công việc đang bị chậm. `LongTaskTimer` bổ sung góc nhìn về **những tác vụ đang hoạt động**. Nó phù hợp với dựng báo cáo, nhập dữ liệu, đồng bộ danh mục, sao lưu hoặc xử lý theo lô.

Chữ “long” không đặt ra một ngưỡng cố định như 1 giây hay 1 phút. Quyết định sử dụng xuất phát từ nhu cầu quan sát trong lúc tác vụ chưa hoàn thành. Bộ đo này cũng không tự tạo luồng, đặt thời hạn chờ, hủy công việc hay đo phần trăm tiến độ. [Tài liệu Long Task Timers của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html) mô tả vai trò đo trong khi tác vụ còn chạy.

Trong Spring Boot Actuator, mối liên hệ là:

- Mã nghiệp vụ xác định lúc bắt đầu và kết thúc một lần chạy.
- Micrometer `LongTaskTimer` quản lý các phép đo đang hoạt động.
- `MeterRegistry` chứa bộ đo và kết nối với hệ thống giám sát.
- Actuator giúp kiểm tra số đo; hệ thống giám sát bên ngoài thu thập và đánh giá cảnh báo.

Bài thực hành dùng Java 21, Spring Boot 3.3.0 và Micrometer 1.13.0 do Spring Boot quản lý. Đây là bộ phiên bản cố định để tái lập ví dụ.

## 2. Đọc đúng ba số đo cốt lõi

Một `LongTaskTimer` có thể đồng thời theo dõi nhiều lần chạy. Mỗi lần gọi `start()` tạo một `LongTaskTimer.Sample` riêng.

| API | Ý nghĩa tại thời điểm đọc |
| --- | --- |
| `activeTasks()` | Số sample đã bắt đầu và chưa dừng |
| `duration(TimeUnit.SECONDS)` | Tổng thời gian đã trôi qua của các sample còn hoạt động |
| `max(TimeUnit.SECONDS)` | Thời gian đã trôi qua lớn nhất trong các sample còn hoạt động |

Nếu hai tác vụ đang có tuổi lần lượt 15 giây và 5 giây, số đo là:

```text
activeTasks = 2
duration = 20 giây
max = 15 giây
```

Tổng 20 giây là tổng tuổi của hai tác vụ, không phải thời gian tính từ lúc ứng dụng khởi động, không phải thời gian CPU và cũng không khẳng định một tác vụ đã chạy 20 giây.

Nếu tác vụ 15 giây vừa dừng, nó rời tập đang hoạt động: số lượng giảm còn 1, tổng thời gian còn 5 giây và giá trị lớn nhất còn 5 giây. Khi mọi sample đều dừng, ba giá trị trở về 0. Vì thế tổng thời lượng đang hoạt động **có thể giảm**; không xử lý nó như một bộ đếm tích lũy chỉ tăng.

Có thể chia tổng tuổi cho số lượng đang hoạt động để biết tuổi trung bình hiện tại, nhưng phải xử lý trường hợp mẫu số bằng 0. Giá trị này không phải độ trễ trung bình của những công việc đã hoàn thành.

Khi cần cả hiện trạng lẫn lịch sử, dùng hai bộ đo với hai tên rõ nghĩa:

| Câu hỏi | Bộ đo phù hợp |
| --- | --- |
| Công việc nào đó còn chạy bao lâu rồi? | `LongTaskTimer`, ví dụ `report.rebuild.active` |
| Những lần chạy đã kết thúc mất bao lâu? | `Timer`, ví dụ `report.rebuild.completed` |
| Đã có bao nhiêu lần thất bại? | `Counter` riêng hoặc số lần ghi nhận trong `Timer` có nhãn kết quả |

Không đăng ký `Timer` và `LongTaskTimer` bằng cùng tên và cùng tập nhãn. Tách tên giúp tránh xung đột loại bộ đo và tránh đọc nhầm ý nghĩa.

## 3. Vòng đời phép đo: một sample cho một lần chạy

Quy tắc quan trọng nhất là ghép đúng `start()` với `stop()` theo vòng đời thực của công việc.

Với công việc đồng bộ, mẫu áp dụng là:

```java
LongTaskTimer.Sample sample = activeTimer.start();
try {
    rebuildReport();
} finally {
    sample.stop();
}
```

Đây là đoạn mã minh họa: `activeTimer` là bộ đo đã đăng ký và `rebuildReport()` là công việc nghiệp vụ của ứng dụng.

`finally` bảo đảm dừng phép đo khi phương thức trả về bình thường hoặc thoát vì ngoại lệ. Nếu bỏ quên `stop()` trên nhánh lỗi, hệ thống giám sát có thể nhìn thấy một “công việc đang chạy” tăng tuổi mãi dù công việc thật đã kết thúc.

Giữ `LongTaskTimer` làm trường dùng chung của thành phần xử lý; giữ `Sample` làm biến cục bộ của từng lần gọi. Nếu hai lần chạy chồng nhau mà cùng dùng một trường `Sample`, lần sau có thể ghi đè tham chiếu của lần trước.

Với khối lệnh đồng bộ phù hợp kiểu `Runnable`, có thể dùng `activeTimer.record(() -> rebuildReport())` để Micrometer quản lý vòng đời sample. Ngoại lệ vẫn được truyền ra; phép đo không thay thế cách xử lý lỗi nghiệp vụ. Với phương thức ném checked exception hoặc cần kiểm soát nhiều điểm kết thúc, cách viết `start()`/`finally` thường dễ kiểm tra hơn.

Đăng ký bộ đo bằng `MeterRegistry` của ứng dụng. Tự tạo một `SimpleMeterRegistry` riêng trong service sẽ khiến dữ liệu nằm ở registry đó, thay vì chắc chắn xuất hiện trên Actuator và hệ thống xuất số đo của Spring Boot.

## 4. Dự án thực hành và ví dụ có kết quả xác định

Ví dụ đầu tiên không dùng `Thread.sleep()`. `MockClock` cho phép tăng thời gian đo một cách chủ động, nhờ đó ta kiểm chứng chính xác việc hai tác vụ chạy chồng nhau và sự khác biệt giữa `LongTaskTimer` với `Timer`.

### 4.1. Khai báo Maven

Tạo một dự án thực hành độc lập với `pom.xml` sau. Hai starter cũng được dùng cho ví dụ Actuator ở phần sau; Spring Boot quản lý phiên bản Micrometer.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>long-task-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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
                <configuration>
                    <mainClass>demo.LongTaskApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`mainClass` chỉ định lớp chạy ứng dụng Spring Boot ở phần 5, vì dự án còn có một lớp `main` riêng để thử đồng hồ giả. Muốn đóng gói bằng `mvn package`, hãy tạo cả hai lớp trước.

### 4.2. Chương trình Java hoàn chỉnh

Lưu tại `src/main/java/demo/LongTaskDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class LongTaskDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            LongTaskTimer active = LongTaskTimer.builder("report.rebuild.active")
                    .tag("job", "daily")
                    .register(registry);
            Timer completed = Timer.builder("report.rebuild.completed")
                    .tag("job", "daily")
                    .register(registry);

            show("initial", active, completed);

            LongTaskTimer.Sample taskA = active.start();
            Timer.Sample historyA = Timer.start(registry);
            clock.add(Duration.ofSeconds(10));
            show("t10", active, completed);

            LongTaskTimer.Sample taskB = active.start();
            Timer.Sample historyB = Timer.start(registry);
            clock.add(Duration.ofSeconds(5));
            show("t15", active, completed);

            taskA.stop();
            historyA.stop(completed);
            show("afterA", active, completed);

            clock.add(Duration.ofSeconds(5));
            taskB.stop();
            historyB.stop(completed);
            show("done", active, completed);

            try {
                active.record((Runnable) () -> {
                    throw new IllegalStateException("demo");
                });
            } catch (IllegalStateException expected) {
                System.out.println("failedActive=" + active.activeTasks());
            }
        } finally {
            registry.close();
        }
    }

    private static void show(String label, LongTaskTimer active, Timer completed) {
        System.out.printf(Locale.ROOT,
                "%s active=%d activeSeconds=%.0f maxSeconds=%.0f completed=%d completedSeconds=%.0f%n",
                label, active.activeTasks(),
                active.duration(TimeUnit.SECONDS),
                active.max(TimeUnit.SECONDS),
                completed.count(), completed.totalTime(TimeUnit.SECONDS));
    }
}
```

`MockClock` và `SimpleMeterRegistry` ở đây chỉ phục vụ thí nghiệm độc lập. Chúng cho phép quan sát dữ liệu ngay trong tiến trình Java, không cần khởi động Spring, máy chủ HTTP hay Prometheus.

### 4.3. Biên dịch và chạy

Từ thư mục chứa `pom.xml`, dùng JDK 21 và Maven. Lần tải thư viện đầu tiên cần kết nối kho Maven.

Trên PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/LongTaskDemo.java
java -cp "target/classes;target/dependency/*" demo.LongTaskDemo
```

Trên Linux/macOS, hai lệnh đầu tương tự; lệnh chạy dùng dấu `:` để ngăn cách các mục classpath:

```bash
java -cp "target/classes:target/dependency/*" demo.LongTaskDemo
```

Stdout của chương trình:

```text
initial active=0 activeSeconds=0 maxSeconds=0 completed=0 completedSeconds=0
t10 active=1 activeSeconds=10 maxSeconds=10 completed=0 completedSeconds=0
t15 active=2 activeSeconds=20 maxSeconds=15 completed=0 completedSeconds=0
afterA active=1 activeSeconds=5 maxSeconds=5 completed=1 completedSeconds=15
done active=0 activeSeconds=0 maxSeconds=0 completed=2 completedSeconds=25
failedActive=0
```

Cách suy ra từng kết quả:

1. A bắt đầu ở giây 0; đến giây 10 có một tác vụ với tuổi 10 giây.
2. B bắt đầu ở giây 10; đến giây 15, A có tuổi 15 và B có tuổi 5. Tổng tuổi đang hoạt động bằng 20, còn `Timer` chưa có lần ghi nhận nào.
3. Dừng A ngay tại giây 15 làm A biến mất khỏi số đo đang hoạt động. `Timer` ghi nhận một lần kéo dài 15 giây.
4. Dừng B ở giây 20 ghi nhận thêm 10 giây vào `Timer`. Tổng thời lượng đã hoàn thành là 25 giây, còn `LongTaskTimer` trở về 0.
5. Khối `record` ném ngoại lệ vẫn dọn sample. Dòng cuối xác nhận không còn tác vụ hoạt động; nó không có nghĩa công việc đã thành công.

Chương trình cố ý điều khiển từng điểm dừng để minh họa. Trong mã nghiệp vụ, hãy dùng `finally` như phần 3 thay vì dựa vào việc mọi dòng phía trước đều chạy thành công.

## 5. Áp dụng trong Spring Boot và quan sát qua Actuator

### 5.1. Công việc chạy theo lịch

Lưu lớp hoàn chỉnh sau tại `src/main/java/demo/LongTaskApplication.java`:

```java
package demo;

import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

import java.util.concurrent.TimeUnit;

@SpringBootApplication
@EnableScheduling
public class LongTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(LongTaskApplication.class, args);
    }

    @Bean
    public ReportJob reportJob(MeterRegistry registry) {
        return new ReportJob(registry);
    }

    public static class ReportJob {
        private final MeterRegistry registry;
        private final LongTaskTimer active;
        private final Timer completed;

        public ReportJob(MeterRegistry registry) {
            this.registry = registry;
            this.active = LongTaskTimer.builder("report.rebuild.active")
                    .description("Elapsed time of report rebuilds still running")
                    .tag("job", "daily")
                    .register(registry);
            this.completed = Timer.builder("report.rebuild.completed")
                    .description("Duration of finished report rebuild attempts")
                    .tag("job", "daily")
                    .register(registry);
        }

        @Scheduled(initialDelay = 10000, fixedDelay = 60000)
        public void rebuild() throws InterruptedException {
            Timer.Sample history = Timer.start(registry);
            LongTaskTimer.Sample running = active.start();
            try {
                TimeUnit.SECONDS.sleep(20);
            } finally {
                running.stop();
                history.stop(completed);
            }
        }
    }
}
```

`sleep(20)` mô phỏng thời gian dựng báo cáo, không phải cách triển khai công việc thật. Khi áp dụng, thay dòng này bằng xử lý nghiệp vụ cần đo.

Lần chạy đầu được lên lịch sau độ trễ ban đầu 10 giây. `fixedDelay = 60000` tính khoảng chờ 60 giây từ khi lần trước hoàn tất đến khi bắt đầu lần tiếp theo; nó không có nghĩa một lần bắt đầu mới cứ đúng mỗi 60 giây bất kể lần trước đã xong hay chưa.

Cả hai bộ đo được đăng ký khi tạo bean nên có thể tìm thấy ngay cả trước lần chạy đầu. `Timer` ở ví dụ ghi nhận **mọi lần kết thúc phép đo**, bao gồm lần thoát bằng ngoại lệ hoặc bị ngắt; tên `completed` không tự phân biệt thành công với thất bại.

### 5.2. Cấu hình chỉ để thử tại máy cá nhân

Lưu tại `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
```

Đóng gói và khởi động:

```text
mvn -q package
java -jar target/long-task-lab-1.0.0.jar
```

Ở cửa sổ terminal khác, gọi:

```bash
curl "http://127.0.0.1:8080/actuator/metrics/report.rebuild.active?tag=job:daily"
curl "http://127.0.0.1:8080/actuator/metrics/report.rebuild.completed?tag=job:daily"
```

Trên Windows có thể gọi `curl.exe` để chắc chắn dùng chương trình curl thay vì bí danh của PowerShell.

Đọc tên có dấu chấm đúng như lúc đăng ký trong Java. Tham số `tag=job:daily` chọn bộ đo của công việc `daily`. Đây là quy tắc được giải thích trong [phần Metrics Endpoint của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

Với bộ phiên bản và registry trong ví dụ, bộ đo đang hoạt động có các thống kê `ACTIVE_TASKS` và `DURATION`; `DURATION` là tổng thời lượng và có đơn vị cơ sở là giây. Để xem rõ giá trị lớn nhất trong thí nghiệm, chương trình phần 4 gọi trực tiếp `max(TimeUnit.SECONDS)`; đừng giả định mọi kênh xuất đều trình bày đủ ba giá trị bằng cùng tên trường.

Hãy thực hiện ba lần quan sát:

| Thời điểm | Kỳ vọng về `report.rebuild.active` |
| --- | --- |
| Trước lần chạy đầu | `ACTIVE_TASKS = 0` và `DURATION = 0` |
| Trong khoảng mô phỏng 20 giây | `ACTIVE_TASKS = 1` và `DURATION` tăng theo thời gian |
| Sau khi tác vụ kết thúc, trong lúc chờ lần kế tiếp | Hai giá trị trở về 0 |

JSON và số giây thực tế phụ thuộc lúc gửi HTTP request, nên không có một giá trị thời lượng cố định để chép làm output. Muốn kiểm tra kết quả tuyệt đối, dùng ví dụ đồng hồ giả; muốn kiểm tra tích hợp, quan sát sự chuyển trạng thái 0 → 1 → 0.

Actuator `metrics` giúp chẩn đoán số đo tại thời điểm gọi. Nó không tự cung cấp kho lịch sử hoặc bộ đánh giá cảnh báo. Ví dụ chỉ mở endpoint trên loopback để thực hành; trong môi trường triển khai, cấu hình quyền truy cập management endpoint theo chính sách của ứng dụng.

## 6. Từ số đo đến cảnh báo có ý nghĩa

Bắt đầu bằng câu hỏi nghiệp vụ rồi chọn phép đo:

- **Có công việc chạy quá 5 phút không?** Kiểm tra tuổi lớn nhất của tác vụ đang hoạt động vượt 300 giây. Nếu có nhiều instance, lấy giá trị lớn nhất giữa các instance để phát hiện một lần chạy quá lâu.
- **Có quá nhiều công việc cùng chạy không?** Kiểm tra số tác vụ đang hoạt động vượt mức đồng thời cho phép. Khi muốn nhìn toàn cụm, cộng số lượng giữa các instance phù hợp.
- **Những lần đã kết thúc đang chậm dần không?** Phân tích `Timer` của các lần hoàn thành; không lấy tuổi hiện tại của các tác vụ đang chạy làm phân vị độ trễ hoàn thành.

Ví dụ 10 tác vụ, mỗi tác vụ mới chạy 40 giây, có tổng tuổi 400 giây. Cảnh báo “một tác vụ quá 300 giây” dựa trên tổng tuổi sẽ báo sai ý định; tuổi lớn nhất lúc này chỉ là 40 giây. Ngược lại, dùng trung bình có thể che khuất một tác vụ rất cũ giữa nhiều tác vụ mới.

Các ngưỡng và phép gộp ở trên là cách thiết kế cảnh báo từ ý nghĩa số đo, không phải cấu hình mà `LongTaskTimer` tự áp dụng. Thời điểm nhận cảnh báo còn chịu ảnh hưởng bởi chu kỳ thu thập, chu kỳ đánh giá và khoảng yêu cầu điều kiện phải duy trì. Tác vụ chạy rồi kết thúc hoàn toàn giữa hai lần thu thập có thể không xuất hiện trong ảnh chụp số đo đang hoạt động; `Timer` hoàn thành giúp bổ sung phần lịch sử đó.

Nếu dùng Prometheus, thêm `io.micrometer:micrometer-registry-prometheus` do Spring Boot quản lý và expose thêm `prometheus`, rồi đọc dữ liệu thực ở `/actuator/prometheus` trước khi viết truy vấn. Tên Java và tên time series đã chuẩn hóa có thể khác nhau.

Đặc biệt, Micrometer 1.13 thay đổi cách xuất `LongTaskTimer` với Prometheus Java client mới: khi không cấu hình bucket, cách xuất là `Summary`; khi cấu hình bucket là `GaugeHistogram` với hậu tố `_gcount`/`_gsum`. Những tên `_active_count` hoặc `_duration_sum` từ ví dụ của client cũ không phải giả định an toàn cho client mới. Xem [hướng dẫn chuyển sang Micrometer 1.13](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide#longtasktimer).

Dù gặp hậu tố `count` hoặc `sum` trong dữ liệu xuất, vẫn phải xét loại bộ đo và tính chất đang hoạt động của nó. Không áp dụng máy móc công thức tốc độ tăng của counter cho dữ liệu có thể giảm khi sample dừng.

## 7. Giới hạn cần xác định khi xử lý bất đồng bộ

Phạm vi đo do vị trí bắt đầu và kết thúc quyết định, không do tên phương thức quyết định.

```java
activeTimer.record(() -> executor.execute(this::rebuildReport));
```

Đoạn minh họa trên thường chỉ đo thời gian **gửi** công việc vào executor. `execute(...)` trả về trước khi công việc trong luồng nền hoàn tất, nên sample cũng dừng quá sớm.

Nếu muốn đo thời gian thực thi, bắt đầu sample **bên trong công việc được executor thực thi**, rồi dừng trong `finally` của chính công việc đó. Thời gian chờ trong hàng đợi sẽ không nằm trong phép đo này.

Nếu muốn đo từ lúc tiếp nhận đến lúc thực sự xử lý xong, bắt đầu trước khi gửi và chuyển sample đến điểm kết thúc thực tế. Khi đó phải thiết kế rõ việc dừng sample nếu gửi thất bại, công việc bị từ chối, hoặc được hủy khi còn trong hàng đợi. Không dừng chỉ vì phương thức bên ngoài trả về một `Future`.

Cũng cần phân biệt trạng thái “Future bị hủy” với “phần xử lý đã thực sự dừng”: không phải công việc nào cũng đáp ứng yêu cầu ngắt ngay lập tức. Hãy chọn một ý nghĩa đo nhất quán, rồi bảo đảm mỗi sample được kết thúc đúng một lần theo ý nghĩa đó.

`LongTaskTimer` không lưu danh sách công việc bền vững qua lần khởi động lại JVM. Nếu cần truy vết một mã công việc cụ thể hoặc trạng thái nghiệp vụ sau khi tiến trình dừng, dùng dữ liệu trạng thái bền vững và log/trace bổ sung.

## 8. Khi nào dùng @Timed(longTask = true)?

Có thể biểu đạt ý định đo bằng annotation:

```java
@Timed(value = "report.rebuild.active", longTask = true)
public void rebuild() {
    rebuildReport();
}
```

Đây là đoạn minh họa thay cho phép đo thủ công trên một phương thức đồng bộ; cần import `io.micrometer.core.annotation.Timed` và có phương thức nghiệp vụ tương ứng. Không đặt annotation này lên ví dụ đã tự `start()`/`stop()` với cùng ý nghĩa, vì một lần chạy có thể bị đo hai lần.

Annotation cần thành phần thực thi. Với service thông thường được gọi qua Spring AOP, có thể thêm dependency `spring-boot-starter-aop` và cấu hình:

```java
package demo;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimingConfiguration {
    @Bean
    public TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
```

Lưu cấu hình này tại `src/main/java/demo/TimingConfiguration.java` nếu chọn cách annotation. Phần thực hành thủ công trước đó không cần cấu hình này.

Lời gọi cần đi qua proxy. Tự gọi một phương thức khác trên cùng đối tượng bằng `this` có thể bỏ qua advice của Spring AOP. Vì vậy, đừng kết luận “có `@Timed` là chắc chắn đã có số đo”; hãy kiểm tra bộ đo xuất hiện và thay đổi khi gọi đúng luồng thực thi. [Tài liệu Timer và TimedAspect](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation) giải thích nhu cầu có cơ chế xử lý annotation.

Với luồng bất đồng bộ hoặc tích hợp đã có sẵn phép đo, cần kiểm tra vòng đời mà cơ chế đó hỗ trợ. Cách `start()`/`stop()` thủ công giúp làm rõ ranh giới khi bạn phải đo qua nhiều bước hoặc nhiều luồng.

## 9. Nhãn, chẩn đoán và lỗi thường gặp

Nhãn nên mô tả nhóm công việc với số giá trị hữu hạn, chẳng hạn `job=daily`, `source=inventory` hoặc `mode=full`. Tránh dùng `jobId`, mã người dùng, thời điểm bắt đầu hoặc nội dung lỗi tự do làm nhãn. Mỗi tổ hợp tên và nhãn tạo danh tính bộ đo; nhãn tăng không kiểm soát sẽ tạo quá nhiều chuỗi số liệu.

Kết quả `success`/`failure` chỉ biết khi kết thúc. Không đổi nhãn của bộ đo đang hoạt động từ `running` thành `success`; ghi kết quả vào bộ đo hoàn thành hoặc bộ đếm riêng. Dùng log/trace để tra cứu một lần chạy cụ thể.

| Triệu chứng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Số tác vụ hoạt động không về 0 | Thiếu `stop()` trên nhánh lỗi, hoặc công việc vẫn thật sự chưa kết thúc |
| Thời lượng gần 0 dù công việc nền rất lâu | Chỉ đo đoạn gửi công việc vào executor |
| Không tìm thấy tên metric | Chưa đăng ký bộ đo, dùng registry riêng, tên sai, bộ lọc từ chối, hoặc annotation chưa được thực thi |
| HTTP 404 khi gọi `/actuator/metrics` | Chưa expose endpoint, sai cổng hoặc sai đường dẫn management |
| HTTP 401/403 | Kiểm tra quyền truy cập endpoint theo cấu hình bảo mật |
| Sau khi xong việc mọi số đo active bằng 0 | Hành vi đúng; xem `Timer` nếu cần thông tin đã hoàn thành |
| Tổng thời gian lớn dù không có tác vụ nào quá lâu | Nhiều tác vụ cùng hoạt động; so sánh thêm tuổi lớn nhất |
| Số liệu khác nhau giữa các instance | Mỗi tiến trình có registry riêng; kiểm tra nhãn instance và phép gộp ở hệ thống giám sát |

Phép đo phản ánh thời gian đã trôi qua. Nó không phân biệt tác vụ đang dùng CPU, chờ I/O hay bị chặn bởi khóa. Khi có cảnh báo, kết hợp thread dump, log và trace để tìm nguyên nhân.

## 10. Tự kiểm tra cách hiểu

1. Ở giây 15 của ví dụ, vì sao tổng tuổi là 20 giây mà tuổi lớn nhất chỉ là 15 giây?
2. Vì sao dừng A làm tổng tuổi đang hoạt động giảm nhưng tổng thời gian của `Timer` tăng?
3. Muốn cảnh báo một lần dựng báo cáo vượt 5 phút, bạn chọn tổng tuổi hay tuổi lớn nhất?
4. Nếu một công việc ném ngoại lệ trước khi trả về, `finally` bảo vệ tính đúng của số đo như thế nào?
5. Khi chuyển sang executor, phép đo cần đặt ở đâu để loại trừ thời gian chờ hàng đợi?

Đối chiếu: hai tuổi 15 và 5 được cộng thành 20; A dừng thì rời tập active nhưng được ghi vào lịch sử; cảnh báo một lần quá lâu dùng tuổi lớn nhất; `finally` dừng sample ngay cả khi thoát bằng ngoại lệ; muốn loại trừ hàng đợi thì bắt đầu trong phần xử lý thật của worker.

Bạn đã nắm được cơ chế khi có thể dự đoán đúng trạng thái trước, trong và sau một công việc, chọn đúng ranh giới đo và giải thích được vì sao số đo đang hoạt động có thể giảm.
