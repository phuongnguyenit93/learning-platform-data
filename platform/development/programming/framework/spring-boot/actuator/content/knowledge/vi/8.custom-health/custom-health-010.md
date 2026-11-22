# Phát hiện kiểm tra chậm và tránh thao tác gây thay đổi dữ liệu

## 1. Phép quan sát cũng tiêu thụ tài nguyên

Kiểm tra sức khỏe (health check) không nằm ngoài hệ thống đang được quan sát. Nó vẫn dùng CPU, luồng, kết nối, bộ nhớ và tài nguyên của dịch vụ phụ thuộc. Nếu một phép kiểm tra chậm được gọi thường xuyên, chính hoạt động giám sát có thể tạo thêm tải đúng lúc hệ thống đang khó khăn.

Một sai sót khác còn khó phát hiện hơn: phép kiểm tra tưởng như chỉ “thử xem có hoạt động không” lại lấy mất một thông điệp khỏi hàng đợi, cập nhật thời điểm xử lý hoặc tạo một bản ghi nghiệp vụ. Kết quả có thể là `UP`, nhưng việc đọc health đã làm thay đổi hệ thống.

Bài này dùng **Java 21 và Spring Boot 3.3.0** để học hai mục tiêu đi cùng nhau:

- nhận diện phép kiểm tra nào chậm, đo đúng phạm vi và hiểu cảnh báo của Actuator;
- thiết kế phép kiểm tra chỉ quan sát, có chi phí được giới hạn và không gây thay đổi dữ liệu nghiệp vụ.

Ví dụ là một hàng đợi công việc trong bộ nhớ. Health đọc độ dài hàng đợi; nó không nhận công việc để xử lý. Mô hình nhỏ giúp kiểm chứng trạng thái trước/sau mà không cần kết nối một hệ thống thật.

## 2. Chậm, hết thời gian chờ và DOWN là ba kết luận khác nhau

| Tín hiệu | Nó nói lên điều gì? | Điều không được suy ra tự động |
| --- | --- | --- |
| Phép kiểm tra mất nhiều thời gian | Một lần quan sát đã tiêu tốn thời gian đáng chú ý. | Thành phần chắc chắn phải `DOWN`. |
| Thao tác hết thời gian chờ | Không có kết quả trong hạn chót đã đặt cho thao tác đó. | Mọi công việc bên dưới đã được hủy hoàn toàn. |
| Indicator trả `DOWN` | Không đạt chính sách sức khỏe mà indicator đang áp dụng. | Nguyên nhân nhất thiết là chậm. |
| HTTP health chậm | Tổng thời gian nhận phản hồi cao. | Chỉ một indicator là nguyên nhân duy nhất. |

Một phép kiểm tra có thể trả `UP` sau 150 ms và đồng thời bị cảnh báo vì ngưỡng cảnh báo là 50 ms. Hai tín hiệu không mâu thuẫn: `UP` mô tả tiêu chí đạt/không đạt, còn cảnh báo mô tả chi phí thời gian.

Ngược lại, một phép kiểm tra có thể trả `DOWN` rất nhanh vì phát hiện cấu hình sai. Không nên dùng độ nhanh của phản hồi để thay thế trạng thái và bằng chứng bên trong.

## 3. Phát hiện kiểm tra chậm bằng Actuator

### 3.1. Ngưỡng cảnh báo

Trong Spring Boot 3.3, Actuator có ngưỡng cảnh báo indicator chậm, mặc định **10 giây**. Có thể điều chỉnh bằng:

```properties
management.endpoint.health.logging.slow-indicator-threshold=200ms
```

Giá trị trên là ví dụ để quan sát trong môi trường học tập, không phải ngưỡng khuyến nghị cho mọi hệ thống. Ngưỡng thật phải phù hợp với ngân sách thời gian, tần suất gọi và đặc điểm của tài nguyên được kiểm tra. Xem [quy định về slow indicator của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

Cần giữ mức log cho phép nhận `WARN` ở nơi Actuator ghi cảnh báo. Nếu hệ thống log chỉ nhận `ERROR`, hạ ngưỡng không làm cảnh báo xuất hiện.

### 3.2. Cảnh báo không phải cơ chế hủy

Ở đường kiểm tra đồng bộ của Spring Boot 3.3.0, `HealthEndpointSupport` ghi nhận thời điểm bắt đầu, gọi contributor rồi kiểm tra thời lượng trong `finally`. Khi thời lượng vượt ngưỡng và logger cho phép `WARN`, nó ghi cảnh báo kèm contributor và thời gian. Cơ chế này không tự đổi kết quả thành `DOWN`, không tạo timeout cho client và không khởi chạy một tiến trình nền để dừng thao tác. Có thể đối chiếu [HealthEndpointSupport](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

Vì vậy, với đường đồng bộ này, nếu lời gọi chưa trả về thì không được kỳ vọng cảnh báo đó sẽ xuất hiện ngay khi đồng hồ vừa qua ngưỡng. Cần timeout ở tầng thực hiện I/O để tránh chờ vô hạn.

Gọi trực tiếp `indicator.health()` trong một unit test cũng không đi qua lớp endpoint chịu trách nhiệm ghi cảnh báo này. Muốn kiểm chứng cảnh báo của Actuator, cần gọi qua endpoint hoặc đường hỗ trợ tương ứng.

### 3.3. Đo toàn bộ request và đo từng phép thử

Thời gian của một request còn có thể gồm định tuyến, xác thực, chờ worker/kết nối, nhiều phép kiểm tra và tạo phản hồi. Một request đồng bộ có năm phép thử nối tiếp, mỗi phép mất khoảng 300 ms, có thể tốn khoảng 1,5 giây cho riêng phần kiểm tra dù không phép nào vượt ngưỡng 500 ms.

Vì vậy, hãy quan sát cả thời gian HTTP và thời gian từng phép thử. Với reactive, cần đo tới tín hiệu kết thúc của publisher thay vì chỉ đo thời gian tạo một `Mono`. Không suy ra phạm vi đo bất đồng bộ chỉ từ một thí nghiệm đồng bộ hoặc từ việc phương thức trả về rất nhanh.

## 4. Thế nào là “không làm thay đổi dữ liệu”?

Trong bài, mục tiêu là không tạo tác dụng phụ nghiệp vụ: không gửi công việc, không nhận/ack thông điệp, không thay đổi đơn hàng, không làm mới hạn dữ liệu và không kích hoạt một quy trình kinh doanh.

Điều này không có nghĩa phép kiểm tra hoàn toàn không để lại dấu vết vận hành. Nó vẫn có thể tạo log, tăng bộ đếm giám sát, mở kết nối hoặc tiêu thụ quota của dịch vụ. Những chi phí đó cũng phải được tính đến.

| Tài nguyên | Cách quan sát có thể phù hợp | Thao tác dễ làm thay đổi hệ thống |
| --- | --- | --- |
| Hàng đợi | Đọc metadata/độ dài bằng API quản trị phù hợp hoặc bản chụp đã có. | Nhận thông điệp, ack, gửi thông điệp thử vào hàng đợi nghiệp vụ. |
| Cơ sở dữ liệu | Kiểm tra kết nối hoặc truy vấn đọc nhỏ đã được xem xét. | Insert/update/delete, gọi procedure có thay đổi dữ liệu. |
| Bộ nhớ đệm | Đọc metadata hoặc khóa kiểm tra theo hợp đồng được thiết kế. | Ghi đè dữ liệu thật, kéo dài TTL, xóa khóa để thử quyền. |
| Dịch vụ HTTP | Gọi API kiểm tra chỉ đọc đã được xác nhận về ngữ nghĩa. | Gọi URL có hành vi reset, tạo tài nguyên hoặc chạy nghiệp vụ. |
| Hệ thống tệp | Đọc metadata cần thiết hoặc trạng thái do thành phần sở hữu công bố. | Tạo/xóa tệp trong thư mục nghiệp vụ mỗi lần health. |

Tên phương thức hoặc HTTP method không đủ bảo đảm tính chỉ đọc. Một URL `GET` vẫn có thể bị triển khai sai; một câu `SELECT` có thể gọi hàm có tác dụng phụ. Phải xem hành vi thực tế của API, câu lệnh và tài nguyên liên quan.

Một thí nghiệm chủ động có ghi dữ liệu có thể hữu ích trong kiểm thử tổng hợp được thiết kế riêng, với tài nguyên cô lập và quy trình dọn dẹp rõ ràng. Không đưa nó vào health được gọi thường xuyên chỉ vì đó là cách nhanh nhất để chứng minh “ghi được”.

## 5. Ví dụ đầy đủ: health chỉ đọc hàng đợi

Đây là dự án Maven độc lập. Tệp `pom.xml`:

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
    <groupId>learning</groupId>
    <artifactId>slow-probe-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.1. Phân biệt đọc trạng thái với lấy công việc

Tệp `src/main/java/learning/slowprobe/WorkQueue.java`:

```java
package learning.slowprobe;

import java.util.ArrayDeque;
import java.util.Collection;
import java.util.Deque;
import java.util.Objects;

public final class WorkQueue {

    public record Snapshot(int pending, long deliveries) {
        public Snapshot {
            if (pending < 0 || deliveries < 0) {
                throw new IllegalArgumentException("Queue counters must not be negative");
            }
        }
    }

    private final Deque<String> jobs;
    private long deliveries;

    public WorkQueue(Collection<String> initialJobs) {
        this.jobs = new ArrayDeque<>(Objects.requireNonNull(initialJobs, "initialJobs"));
    }

    public synchronized Snapshot inspect() {
        return new Snapshot(jobs.size(), deliveries);
    }

    public synchronized String deliverNext() {
        String job = jobs.pollFirst();
        if (job != null) {
            deliveries++;
        }
        return job;
    }
}
```

`inspect()` chỉ lấy bản chụp bộ đếm; `deliverNext()` lấy một công việc ra khỏi hàng đợi và tăng số lượt giao. Hai phương thức phục vụ hai mục đích khác nhau. Health phải dùng `inspect()`, không “thử nhận một công việc rồi tính sau”.

`synchronized` giữ bản chụp nhất quán trong mô hình nhỏ này. Với hệ thống thật, phải xem thời gian giữ khóa và đường đọc metadata của broker; không suy ra một lời gọi quản trị mạng có cùng chi phí với `jobs.size()` trong bộ nhớ.

### 5.2. Indicator nhận một đầu nối đọc

Tệp `src/main/java/learning/slowprobe/QueueHealthIndicator.java`:

```java
package learning.slowprobe;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class QueueHealthIndicator implements HealthIndicator {

    private final Callable<WorkQueue.Snapshot> reader;
    private final int maxPending;

    public QueueHealthIndicator(Callable<WorkQueue.Snapshot> reader, int maxPending) {
        this.reader = Objects.requireNonNull(reader, "reader");
        if (maxPending < 0) {
            throw new IllegalArgumentException("maxPending must not be negative");
        }
        this.maxPending = maxPending;
    }

    @Override
    public Health health() {
        long started = System.nanoTime();
        Health.Builder builder = Health.unknown().withDetail("maxPending", maxPending);
        try {
            WorkQueue.Snapshot snapshot = reader.call();
            if (snapshot == null) {
                builder.down().withDetail("reason", "NO_SNAPSHOT");
            }
            else {
                builder.withDetail("pending", snapshot.pending());
                if (snapshot.pending() > maxPending) {
                    builder.down().withDetail("reason", "BACKLOG_LIMIT");
                }
                else {
                    builder.up().withDetail("reason", "WITHIN_LIMIT");
                }
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            builder.down().withDetail("reason", "INTERRUPTED");
        }
        catch (Exception ex) {
            builder.down().withDetail("reason", "READ_FAILED");
        }
        long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
        return builder.withDetail("durationMs", durationMs).build();
    }
}
```

Indicator nhận một đầu nối đọc thay vì phải sử dụng trực tiếp toàn bộ API của hàng đợi. Cách này làm trách nhiệm dễ thấy và dễ kiểm thử; nó không phải một cơ chế bảo mật ngăn mọi lambda độc hại. Vẫn phải kiểm tra implementation được truyền vào có thực sự chỉ đọc không.

`System.nanoTime()` được dùng để đo khoảng thời gian trôi qua; không dùng chênh lệch đồng hồ lịch làm đồng hồ đo hiệu năng. `durationMs` là thời gian bên trong indicator, không gồm toàn bộ HTTP request hoặc mọi bước bên ngoài nó. Việc đưa số đo vào details cũng không tự tạo một metric lịch sử.

Ngưỡng `maxPending` là chính sách backlog của ví dụ. Đúng ngưỡng vẫn đạt, vượt ngưỡng thì `DOWN`. Chậm không tự làm indicator `DOWN`: nếu đọc thành công và backlog đạt tiêu chí, nó vẫn trả `UP`. Nếu cần giới hạn độ trễ như một tiêu chí sức khỏe, phải bổ sung chính sách đó một cách tường minh.

### 5.3. Kiểm chứng gọi nhiều lần không lấy mất công việc

Tệp `src/main/java/learning/slowprobe/QueueReadOnlyDemo.java`:

```java
package learning.slowprobe;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.actuate.health.Status;

public class QueueReadOnlyDemo {

    public static void main(String[] args) {
        WorkQueue queue = new WorkQueue(List.of("job-1", "job-2"));
        WorkQueue.Snapshot before = queue.inspect();
        AtomicInteger observations = new AtomicInteger();
        var indicator = new QueueHealthIndicator(() -> {
            observations.incrementAndGet();
            return queue.inspect();
        }, 100);

        for (int i = 0; i < 3; i++) {
            if (!Status.UP.equals(indicator.health().getStatus())) {
                throw new AssertionError("Unexpected health status");
            }
        }
        WorkQueue.Snapshot after = queue.inspect();
        if (!before.equals(after) || observations.get() != 3) {
            throw new AssertionError("Observation changed business state or was skipped");
        }

        System.out.println("status=UP");
        System.out.println("pendingBefore=" + before.pending());
        System.out.println("pendingAfter=" + after.pending());
        System.out.println("deliveriesBefore=" + before.deliveries());
        System.out.println("deliveriesAfter=" + after.deliveries());
        System.out.println("observations=" + observations.get());
        System.out.println("businessStateUnchanged=" + before.equals(after));
    }
}
```

Trong thư mục dự án, kiểm tra Maven đang dùng JDK 21 và biên dịch:

```shell
mvn -version
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

Chạy trên PowerShell:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.slowprobe.QueueReadOnlyDemo
```

Hoặc chạy trên Linux/macOS:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.slowprobe.QueueReadOnlyDemo
```

Maven đã thực hiện bước biên dịch Java với classpath cần thiết. Không chạy `javac QueueHealthIndicator.java` đơn lẻ khi chưa đưa thư viện Actuator vào classpath.

Stdout chính xác:

```text
status=UP
pendingBefore=2
pendingAfter=2
deliveriesBefore=0
deliveriesAfter=0
observations=3
businessStateUnchanged=true
```

`observations` tăng là dấu vết đo lường được chủ động tạo trong kiểm tra; số công việc và số lượt giao không đổi. Kiểm tra không chỉ so status: nó còn chứng minh cả ba lần đọc đã xảy ra mà không thay đổi trạng thái nghiệp vụ của mô hình.

## 6. Tạo phép đọc chậm có kiểm soát để thấy cảnh báo

Tệp `src/main/java/learning/slowprobe/SlowProbeApplication.java`:

```java
package learning.slowprobe;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SlowProbeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SlowProbeApplication.class, args);
    }

    @Bean
    WorkQueue workQueue() {
        return new WorkQueue(List.of("job-1", "job-2"));
    }

    @Bean
    QueueHealthIndicator workQueueHealthIndicator(
            WorkQueue queue,
            @Value("${demo.delay-ms:150}") long delayMs,
            @Value("${demo.max-pending:100}") int maxPending) {
        if (delayMs < 0) {
            throw new IllegalArgumentException("delayMs must not be negative");
        }
        return new QueueHealthIndicator(() -> {
            Thread.sleep(delayMs);
            return queue.inspect();
        }, maxPending);
    }
}
```

`Thread.sleep` chỉ tạo độ trễ mô phỏng, không phải thao tác cần có trong một health check thật. Tất cả các phép đọc vẫn dùng `inspect()`. Độ trễ và backlog là hai biến độc lập để thử chính sách.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.logging.slow-indicator-threshold=50ms
logging.level.org.springframework.boot.actuate.health.HealthEndpointSupport=WARN
```

Tên bean `workQueueHealthIndicator` tạo contributor `workQueue`. Khởi động:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.slowprobe.SlowProbeApplication"
```

Ở terminal khác, gọi:

```shell
curl -i http://127.0.0.1:8080/actuator/health/workQueue
```

Trên Windows có thể dùng `mvn.cmd` và `curl.exe`. Với backlog bằng 2 và giới hạn 100, nhánh trả `UP` và HTTP `200`. Chi tiết có dạng:

```json
{
  "status": "UP",
  "details": {
    "maxPending": 100,
    "pending": 2,
    "reason": "WITHIN_LIMIT",
    "durationMs": 151
  }
}
```

`151` là số minh họa; không phải giá trị cố định và có thể cao hơn khi hệ thống bận. Đồng thời, log Actuator có cảnh báo nêu contributor `workQueue` và thời gian phản hồi. Thông điệp của phiên bản này có phần nhận diện `Health contributor` và `took ... to respond`; tên lớp, thời lượng, dấu thời gian và định dạng phụ thuộc lần chạy/cấu hình log.

Quan sát cần rút ra là: **ngưỡng 50 ms không cắt lời gọi ở 50 ms**. Phép đọc mô phỏng khoảng 150 ms vẫn hoàn tất và trả `UP`, rồi cảnh báo thể hiện nó chậm hơn ngưỡng.

Dừng ứng dụng và thử backlog vượt giới hạn:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.slowprobe.SlowProbeApplication" "-Dspring-boot.run.arguments=--demo.max-pending=1"
```

Lúc này contributor trả `DOWN/BACKLOG_LIMIT`, HTTP `503` theo mapping mặc định, nhưng không lấy bớt công việc để cố làm backlog giảm. Tính chỉ đọc phải được giữ cả khi kết quả không khỏe.

Cấu hình hiển thị details đầy đủ chỉ phục vụ quan sát trên loopback. Ở môi trường vận hành, cần chính sách truy cập phù hợp và không đưa payload công việc hoặc thông tin nhạy cảm vào kết quả health.

## 7. Những cách “thử cho chắc” dễ làm thay đổi hệ thống

### Lấy một thông điệp rồi trả lại

Nhận rồi gửi lại hoặc ack/nack một thông điệp không tương đương với chưa từng nhận. Nó có thể thay đổi thứ tự, số lần giao, visibility timeout, dead-letter policy hoặc dấu vết xử lý của broker. Trong mô hình trên, `deliverNext()` đã làm thay đổi cả số công việc lẫn số lượt giao.

Không gọi API xử lý thật để kiểm tra khả năng quan sát. Hãy đọc metadata, trạng thái kết nối hoặc một bản chụp do thành phần sở hữu công bố, tùy câu hỏi cần trả lời.

### Ghi bản ghi rồi rollback hoặc xóa ngay

Rollback không phải bằng chứng rằng không có chi phí hay tác dụng phụ. Thao tác có thể đã giữ khóa, sử dụng sequence, kích hoạt logic bên ngoài hoặc gửi một sự kiện không cùng giao dịch. Insert rồi delete cũng có khoảng thời gian tồn tại thật và có thể để lại dấu vết trong các hệ thống khác.

Nếu cần chứng minh luồng ghi end-to-end, hãy thiết kế kiểm thử tổng hợp riêng với dữ liệu và quyền được cô lập; đừng lặp lại trên bảng nghiệp vụ ở mọi lần health.

### Làm mới dữ liệu ngay khi thấy cũ

Health gọi `refresh()`, cập nhật `lastSeen`, gia hạn TTL hoặc tạo cache entry khi miss sẽ khiến hoạt động quan sát thay đổi bằng chứng. Khi giám sát gọi càng thường xuyên, dữ liệu có thể càng được giữ mới giả tạo hoặc càng phát sinh nhiều lần tải.

Thành phần sở hữu dữ liệu nên tự làm mới theo vòng đời của nó. Health đọc bản chụp, thời điểm thành công gần nhất và tiêu chí hết hạn đã được định nghĩa.

### Tưởng annotation readOnly là hàng rào tuyệt đối

`@Transactional(readOnly = true)` là thông tin cho transaction manager và tối ưu hóa tương ứng; không phải bảo đảm phổ quát rằng mọi lớp bên dưới sẽ từ chối ghi. Nó cũng không ngăn một lời gọi HTTP, gửi thư hoặc thao tác hàng đợi bên ngoài giao dịch đó. Xem [hợp đồng readOnly của Transactional](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/transaction/annotation/Transactional.html#readOnly()).

Muốn giảm nguy cơ ghi nhầm, kết hợp API đọc hẹp, câu lệnh đã được rà soát, quyền tài nguyên phù hợp và kiểm thử trạng thái trước/sau. Đồng thời, đừng dùng một tài khoản quản trị hoàn toàn khác rồi coi kết nối thành công của tài khoản đó là bằng chứng tài khoản ứng dụng vẫn làm việc được.

## 8. Chỉ đọc vẫn có thể rất tốn kém

Một câu `SELECT COUNT(*)` trên tập dữ liệu lớn, việc liệt kê toàn bộ bucket hoặc lấy mọi thông điệp để đếm có thể chỉ đọc nhưng không phù hợp cho health thường xuyên. Cần quan sát nhỏ và đúng phạm vi, không tái dựng báo cáo nghiệp vụ trong mỗi phép kiểm tra.

Các điểm thường làm phép kiểm tra chậm gồm:

- chờ lấy kết nối từ pool trước khi bắt đầu lệnh;
- DNS, thiết lập TLS hoặc xác thực lại quá thường xuyên;
- timeout của client quá lớn hoặc chưa được đặt;
- retry nhiều lần ngay trong một lần health;
- giữ khóa trong ứng dụng hoặc dịch vụ phụ thuộc;
- truy vấn đọc không có giới hạn, quét dữ liệu lớn hoặc deserialize payload không cần thiết.

Ngân sách phải tính cả thời gian chờ tài nguyên và số lần thử, không chỉ thời gian xử lý lệnh cuối cùng. Hạ ngưỡng cảnh báo không thay thế việc đặt timeout, giới hạn đồng thời và giảm chi phí của phép đọc.

Không tạo executor hoặc client mới cho mỗi request chỉ để áp một timeout ở ngoài. Khi hết thời gian chờ, tác vụ bên dưới có thể vẫn chạy, giữ kết nối và tích lũy thêm tải. Cần hiểu cơ chế hủy của client thực tế và quản lý vòng đời tài nguyên dùng chung.

### Tính cả tần suất của toàn bộ hệ thống giám sát

Ví dụ có 100 instance, mỗi instance bị hai hệ thống gọi mỗi 10 giây. Tải quan sát trung bình là khoảng `100 × 2 / 10 = 20` request/giây. Nếu một phép thử giữ tài nguyên khoảng hai giây, lượng công việc đang chờ/xử lý có thể tương đương khoảng 40 phép thử trong điều kiện ổn định, trước khi xét thêm các giới hạn và hàng đợi.

Đây là ước lượng để thấy chi phí nhân lên, không phải cam kết về số thread thực tế. Pool bị giới hạn có thể chuyển tải đó thành thời gian xếp hàng. Các request đồng loạt còn tạo đỉnh tải cao hơn trung bình.

## 9. Đo lường đủ để tìm nguyên nhân

Cảnh báo từng lần giúp tìm contributor chậm, nhưng không thay cho lịch sử phân bố độ trễ. Khi cần theo dõi lâu dài, có thể dùng một `Timer` của Micrometer quanh phép thử, với tên thành phần ổn định và tập nhãn nhỏ.

Ví dụ minh họa tại nơi đã có `MeterRegistry registry` và `HealthIndicator indicator`:

```java
Timer timer = registry.timer("app.health.probe", "component", "workQueue");
return timer.record(indicator::health);
```

Đoạn này cần import `io.micrometer.core.instrument.Timer` và không phải chương trình độc lập. Tên `app.health.probe` do ứng dụng tự định nghĩa; không phải metric Actuator mặc định đã tự được tạo cho mọi indicator.

Đoạn bọc đo toàn bộ lời gọi đồng bộ được truyền vào, trong khi `durationMs` của ví dụ đo từ bên trong indicator. Không gắn customer id, payload công việc, URL động hoặc exception message làm nhãn: chúng làm tăng số chuỗi thời gian và có thể chứa dữ liệu nhạy cảm.

Đối chiếu thời lượng probe với thời gian lấy kết nối, độ bận worker, độ trễ của tài nguyên phụ thuộc và thời gian HTTP. Tăng ngưỡng hoặc tắt logger chỉ làm giảm dấu hiệu quan sát, không chứng minh nguyên nhân đã được xử lý.

## 10. Quy trình kiểm chứng trước khi dùng thực tế

1. **Xác định câu hỏi sức khỏe.** Kiểm tra kết nối, độ mới dữ liệu hay backlog là các câu hỏi khác nhau; chọn phép đọc nhỏ nhất trả lời được câu hỏi cần thiết.
2. **Rà soát đường gọi.** Đi từ indicator qua service, repository/client đến API hoặc câu lệnh thật. Không dừng ở tên phương thức `check()` hoặc một annotation.
3. **Chụp trạng thái trước/sau.** Với hàng đợi, kiểm tra số lượng, thứ tự và số lần giao nếu có; với cơ sở dữ liệu, kiểm tra dữ liệu cùng các tác dụng phụ liên quan. Trong kiểm thử cô lập, ngăn tác nhân khác làm thay đổi dữ liệu để có thể quy kết đúng nguyên nhân.
4. **Gọi lặp và đồng thời.** Bảo đảm không nhận mất công việc, không ghi dữ liệu và không làm mới trạng thái chỉ vì quan sát. Theo dõi cả số lời gọi I/O và số kết nối.
5. **Tạo độ trễ có kiểm soát.** Xác nhận cảnh báo nhận diện đúng contributor, kết quả status vẫn theo chính sách và timeout thật hoạt động ở tầng cần thiết.
6. **Thử đường lỗi.** Kiểm tra exception, ngắt luồng, backlog quá mức và dữ liệu quan sát không tồn tại; tính chỉ đọc phải đúng cả ở đường lỗi.
7. **Kiểm tra đường công bố.** Gọi qua Actuator khi kiểm chứng cảnh báo của Actuator; kiểm tra quyền hiển thị và HTTP status riêng với phép gọi trực tiếp indicator.

Kết quả `UP` không đủ để đánh giá một health check tốt. Cần chứng minh thêm rằng nó quan sát đúng tài nguyên, hoàn tất với chi phí phù hợp, phát hiện được chậm và giữ nguyên dữ liệu nghiệp vụ sau mỗi lần được gọi.
