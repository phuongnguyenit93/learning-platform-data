# Đo thời gian khởi động trước và sau thay đổi với cùng dependency và cấu hình

Khi tối ưu Spring Boot, một con số “Started in 4.2 seconds” chỉ có ý nghĩa khi ta biết đồng hồ bắt đầu và kết thúc ở đâu, hai lần chạy có cùng điều kiện hay không và số đo có lặp lại được không. Một thay đổi có thể giảm thời gian tạo ApplicationContext nhưng không cải thiện thời điểm service thực sự nhận traffic. Ngược lại, lazy initialization có thể làm startup nhanh hơn nhưng chuyển phần việc sang request đầu tiên.

Mục tiêu của phép đo trước/sau là xác định **thay đổi mã nguồn đã làm thời gian từ lúc khởi chạy tiến trình đến lúc ứng dụng sẵn sàng phục vụ giảm bao nhiêu**, trong khi dependency, cấu hình, JVM, máy chạy và cách đóng gói được giữ cố định.

Hãy đo hai lớp bổ sung nhau:

- **Process-to-ready:** thời gian từ lúc tạo JVM process đến khi readiness endpoint trả HTTP 200. Đây là số liệu chính để đánh giá thời gian khởi động mà nền tảng triển khai phải chờ.
- **Spring startup steps:** các bước bên trong Spring như chuẩn bị Environment, tạo bean, refresh context. Dữ liệu này giúp tìm nguyên nhân thay đổi đến từ đâu.

Không cộng hai loại thời gian với nhau. Startup steps giải thích số đo tổng; chúng không phải một phép đo độc lập để thay thế thời gian process-to-ready.

## 1. Xác định chính xác mốc bắt đầu và kết thúc

Có ít nhất ba mốc thường bị gọi chung là “startup time”:

| Mốc | Bắt đầu | Kết thúc | Bao gồm |
| --- | --- | --- | --- |
| JVM process-to-ready | Trước khi tạo process java | Readiness probe trả 200 OK | Khởi tạo JVM, load class, Spring, embedded server, runner và thời điểm nhận traffic. |
| SpringApplication startup | Khi SpringApplication bắt đầu chạy | ApplicationReadyEvent hoặc readiness event | Công việc bên trong Spring; không bao gồm toàn bộ thời gian JVM trước khi vào Spring. |
| Context refresh | Khi bắt đầu refresh ApplicationContext | ContextRefreshedEvent/context refresh hoàn tất | Một phần quá trình Spring; không bao gồm đầy đủ JVM, web server và runner. |

Với service web, nên dùng readiness làm mốc kết thúc. Spring Boot phát ApplicationStartedEvent sau khi context refresh, nhưng trước khi chạy ApplicationRunner và CommandLineRunner. ApplicationReadyEvent được phát sau các runner; ngay sau đó readiness chuyển sang ACCEPTING_TRAFFIC. Vì vậy, readiness thể hiện đúng hơn thời điểm ứng dụng có thể nhận traffic.

Nếu chỉ ghi thời điểm ContextRefreshedEvent, các công việc trong runner vẫn có thể đang chạy. Nếu chỉ nhìn log “Started ...”, cần nhớ log đó phản ánh vòng đời SpringApplication và không đo chính xác thời gian process spawn đến khi một request thật sự được chấp nhận.

Với ứng dụng non-web, không có HTTP readiness endpoint. Có thể ghi System.nanoTime() ở đầu main và tại ApplicationReadyEvent, hoặc dùng một tín hiệu readiness riêng mà tiến trình benchmark có thể quan sát. Hãy ghi rõ số đo đó bắt đầu sau khi JVM đã gọi main, nên nó không bao gồm toàn bộ thời gian khởi tạo JVM.

## 2. Giữ nguyên điều kiện giữa hai lần đo

Trước khi chạy, xác định rõ biến nào được phép thay đổi. Nếu muốn đo tác động của một thay đổi code, chỉ thay đổi code thuộc phạm vi thử nghiệm. Giữ nguyên:

| Nhóm | Cần cố định |
| --- | --- |
| Dependency | Cùng groupId:artifactId:version, scope và dependency bắc cầu; cùng Spring Boot/Spring Framework. |
| Cấu hình ứng dụng | Cùng application.properties/YAML, profile, biến môi trường, system properties và command-line arguments. |
| JVM | Cùng JDK vendor/version, JVM flags, heap -Xms/-Xmx, GC và JAVA_TOOL_OPTIONS. |
| Đóng gói | Cùng loại artifact và cách chạy, ví dụ đều dùng executable JAR với java -jar. |
| Máy chạy | Cùng CPU, RAM, hệ điều hành, container CPU/memory limit và storage. |
| Dịch vụ phụ thuộc | Cùng database, broker, cache, DNS, mạng, dữ liệu khởi tạo và trạng thái dịch vụ. |
| Logging/đo lường | Cùng log level, Actuator, readiness probe, startup instrumentation và tần suất polling. |

Đừng đo bản trước bằng mvn spring-boot:run rồi đo bản sau bằng java -jar. Hai cách chạy có classpath, launcher và công việc chuẩn bị khác nhau. Hãy đóng gói cả hai và dùng cùng một lệnh khởi chạy.

Kiểm tra dependency tree trước và sau:

```powershell
mvn dependency:tree -DoutputFile=target/dependency-tree.txt
```

Lưu file dependency tree của mỗi phiên bản rồi so sánh:

```powershell
Compare-Object (Get-Content artifacts/dependencies-before.txt) (Get-Content artifacts/dependencies-after.txt)
```

Nếu không có output, hai file text giống nhau. Nếu có khác biệt, hãy xác định dependency nào đã đổi trước khi quy kết quả startup cho code change. Dependency tree không chứng minh cấu hình runtime giống nhau; vẫn phải lưu và đối chiếu profile, file cấu hình, biến môi trường và JVM flags.

Nếu chủ đích của thay đổi là thêm/bớt dependency, hãy tách thành một thí nghiệm riêng. Khi đó kết luận là tác động của thay đổi dependency graph, không phải tác động thuần của code.

## 3. Dùng ApplicationStartup để tìm bước Spring tốn thời gian

Spring Framework cung cấp ApplicationStartup và StartupStep để ghi nhận trình tự startup. Spring Boot có BufferingApplicationStartup, lưu các bước cùng timestamp và duration trong một buffer. Cách này hữu ích để tìm bean hoặc giai đoạn nào thay đổi sau khi tối ưu.

Ví dụ cấu hình trong ứng dụng Java 17 / Spring Boot 3.3:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupLabApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(4096)
        );

        application.run(args);
    }
}
```

Dung lượng 4096 là sức chứa của buffer, không phải thời gian đo. Chọn đủ lớn cho số startup steps của ứng dụng; nếu buffer đầy, những bước mới có thể không được ghi lại.

Để đọc dữ liệu qua Actuator, thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Và cấu hình cho môi trường benchmark:

```properties
server.address=127.0.0.1
server.port=18080

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,startup
```

Khi ứng dụng chạy:

- GET /actuator/health/readiness là tín hiệu để benchmark chờ ứng dụng sẵn sàng.
- GET /actuator/startup trả snapshot các startup steps đã ghi.
- Startup endpoint chỉ có dữ liệu khi SpringApplication được cấu hình với BufferingApplicationStartup.
- Mặc định chỉ endpoint health được expose qua HTTP; cấu hình include ở trên bổ sung startup.

Dùng GET để đọc snapshot. POST /actuator/startup có hành vi drain buffer, nên không dùng POST nếu chỉ muốn quan sát dữ liệu mà không làm rỗng buffer. Chỉ expose Actuator endpoint trên loopback hoặc bảo vệ bằng security phù hợp; không mở endpoint chẩn đoán startup ra Internet công khai.

Các trường quan trọng trong JSON:

- timeline.startTime: thời điểm bắt đầu timeline.
- timeline.events[].startupStep.name: tên bước, ví dụ bước khởi tạo bean.
- timeline.events[].duration: thời lượng của bước.
- timeline.events[].startupStep.tags: thông tin bổ sung như bean name.
- parentId: quan hệ giữa step cha và step con.

So sánh những step có cùng tên và tag giữa hai phiên bản. Step có thời lượng tăng mạnh thường chỉ ra khu vực cần điều tra. Một số step lồng nhau; **không cộng tất cả duration** để suy ra tổng startup vì thời lượng của step cha và con có thể chồng lấp.

## 4. Tạo một ứng dụng mẫu có thể đo được

Ví dụ tối thiểu dùng Maven, Java 17 và Spring Boot 3.3.5. Giữ nguyên POM này cho cả bản baseline và bản sau thay đổi.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>startup-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Trong dự án thật, giữ nguyên toàn bộ dependency đang dùng; không thay POM production bằng POM tối giản này chỉ để benchmark. POM mẫu chỉ cho thấy những dependency cần để chạy ví dụ độc lập.

Nếu Actuator chưa có trong ứng dụng, có thể thêm nó vào **cả hai** bản benchmark để cung cấp readiness và startup endpoint. Việc thêm Actuator sẽ làm thay đổi dependency set và có một ít chi phí đo lường; vì thế phải thêm giống hệt ở cả hai bản. Nếu muốn số đo cuối cùng phản ánh production mà production không có Actuator, hãy chạy thêm một lượt không có instrumentation bằng một readiness signal đã tồn tại trong ứng dụng.

## 5. Đo process-to-ready bằng một launcher bên ngoài

Một benchmark bên ngoài sẽ:

1. Khởi chạy một process Java mới với cùng JAR và cùng JVM.
2. Bắt đầu đồng hồ trước khi tạo process.
3. Poll readiness endpoint theo chu kỳ cố định.
4. Dừng đồng hồ ở lần đầu nhận HTTP 200.
5. Lưu log của process và snapshot startup JSON.
6. Đóng process trước khi bắt đầu lượt tiếp theo.
7. Bỏ các lượt warm-up và tính median, min, max từ các lượt đo.

Tạo file benchmark/StartupBenchmark.java:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class StartupBenchmark {

    private static final Duration STARTUP_TIMEOUT =
            Duration.ofSeconds(120);

    private static final Duration REQUEST_TIMEOUT =
            Duration.ofSeconds(1);

    private static final long POLL_INTERVAL_MILLIS = 50;

    public static void main(String[] args) throws Exception {
        if (args.length < 5 || args.length > 6) {
            System.err.println(
                    "Usage: java StartupBenchmark <jar> <label> "
                    + "<warmups> <runs> <readiness-url> [startup-url]"
            );
            System.exit(2);
        }

        Path jar = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("JAR not found: " + jar);
        }

        String label = args[1].replaceAll("[^A-Za-z0-9._-]", "_");
        int warmups = Integer.parseInt(args[2]);
        int measuredRuns = Integer.parseInt(args[3]);

        if (warmups < 0 || measuredRuns < 1) {
            throw new IllegalArgumentException(
                    "warmups must be >= 0 and runs must be >= 1"
            );
        }

        URI readinessUri = URI.create(args[4]);
        URI startupUri = args.length == 6
                ? URI.create(args[5])
                : null;

        Path resultsDirectory = Path.of("startup-results");
        Files.createDirectories(resultsDirectory);

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();

        List<Long> measurements = new ArrayList<>();

        for (int run = 1; run <= warmups + measuredRuns; run++) {
            Path logFile = resultsDirectory.resolve(
                    label + "-run-" + run + ".log"
            );

            long startedAt = System.nanoTime();

            Process process = new ProcessBuilder(
                    javaExecutable(),
                    "-jar",
                    jar.toString()
            )
                    .redirectErrorStream(true)
                    .redirectOutput(logFile.toFile())
                    .start();

            try {
                waitUntilReady(process, client, readinessUri, logFile);

                long elapsedNanos = System.nanoTime() - startedAt;
                double elapsedMillis = elapsedNanos / 1_000_000.0;

                if (run <= warmups) {
                    System.out.printf(
                            "%s warmup=%d startup_ms=%.3f%n",
                            label, run, elapsedMillis
                    );
                } else {
                    measurements.add(elapsedNanos);
                    System.out.printf(
                            "%s measured=%d startup_ms=%.3f%n",
                            label, run - warmups, elapsedMillis
                    );
                }

                if (startupUri != null) {
                    saveStartupTimeline(
                            client,
                            startupUri,
                            resultsDirectory.resolve(
                                    label + "-run-" + run + "-startup.json"
                            )
                    );
                }
            } finally {
                process.destroy();
                if (!process.waitFor(10, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor();
                }
            }

            Thread.sleep(300);
        }

        measurements.sort(Long::compareTo);

        int size = measurements.size();
        double medianMillis;

        if (size % 2 == 1) {
            medianMillis = measurements.get(size / 2) / 1_000_000.0;
        } else {
            medianMillis = (
                    measurements.get(size / 2 - 1)
                    + measurements.get(size / 2)
            ) / 2_000_000.0;
        }

        double minMillis = measurements.get(0) / 1_000_000.0;
        double maxMillis = measurements.get(size - 1) / 1_000_000.0;

        System.out.printf(
                "%s summary runs=%d median_ms=%.3f min_ms=%.3f max_ms=%.3f%n",
                label, size, medianMillis, minMillis, maxMillis
        );
    }

    private static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win");

        String executable = windows ? "java.exe" : "java";

        return Path.of(
                System.getProperty("java.home"),
                "bin",
                executable
        ).toString();
    }

    private static void waitUntilReady(
            Process process,
            HttpClient client,
            URI readinessUri,
            Path logFile
    ) throws Exception {

        long deadline = System.nanoTime() + STARTUP_TIMEOUT.toNanos();

        HttpRequest request = HttpRequest.newBuilder(readinessUri)
                .timeout(REQUEST_TIMEOUT)
                .GET()
                .build();

        while (System.nanoTime() < deadline) {
            if (!process.isAlive()) {
                throw new IllegalStateException(
                        "Application exited with code "
                        + process.exitValue()
                        + ". Check log: " + logFile
                );
            }

            try {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding()
                );

                if (response.statusCode() == 200) {
                    return;
                }
            } catch (IOException ignored) {
                // Server chưa mở cổng hoặc chưa nhận request.
            }

            Thread.sleep(POLL_INTERVAL_MILLIS);
        }

        throw new IllegalStateException(
                "Readiness timeout at " + readinessUri
                + ". Check log: " + logFile
        );
    }

    private static void saveStartupTimeline(
            HttpClient client,
            URI startupUri,
            Path output
    ) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(startupUri)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        if (response.statusCode() == 200) {
            Files.writeString(output, response.body());
        } else {
            System.out.printf(
                    "startup endpoint returned HTTP %d%n",
                    response.statusCode()
            );
        }
    }
}
```

Chương trình dùng chính JDK đang chạy benchmark để khởi chạy JAR con. Mỗi lượt là một JVM process mới. Log stdout/stderr được lưu trong startup-results; startup JSON được lấy **sau khi đã dừng đồng hồ**, nên thao tác tải JSON không cộng vào thời gian process-to-ready.

Readiness URL trong ví dụ là http://127.0.0.1:18080/actuator/health/readiness. Nếu ứng dụng dùng port hoặc management base path khác, truyền URL thực tế. Nếu Actuator được bảo vệ bởi Spring Security, hãy cấu hình benchmark client gửi thông tin xác thực dành riêng cho môi trường test; không tắt bảo mật production chỉ để chạy phép đo.

## 6. Tạo hai artifact có thể so sánh

Giả sử hai phiên bản đều tạo file target/startup-lab-1.0.0.jar. Lưu artifact baseline trước khi build phiên bản sau. Ví dụ PowerShell:

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null

mvn clean package
mvn dependency:tree -DoutputFile=target/dependency-tree.txt

Copy-Item target/startup-lab-1.0.0.jar artifacts/before.jar
Copy-Item target/dependency-tree.txt artifacts/dependencies-before.txt
```

Sau khi chuyển sang revision chứa thay đổi cần đo, build lại bằng cùng JDK, Maven và profile:

```powershell
mvn clean package
mvn dependency:tree -DoutputFile=target/dependency-tree.txt

Copy-Item target/startup-lab-1.0.0.jar artifacts/after.jar
Copy-Item target/dependency-tree.txt artifacts/dependencies-after.txt

Compare-Object (Get-Content artifacts/dependencies-before.txt) (Get-Content artifacts/dependencies-after.txt)
```

Giữ cả hai JAR, dependency tree và thông tin revision. Đừng để lần build thứ hai ghi đè artifact baseline. Nếu dependency tree khác, dừng việc so sánh thuần code cho đến khi đã giải thích được khác biệt.

Có thể ghi lại môi trường bằng các lệnh:

```powershell
java -version
mvn -version
git rev-parse HEAD
```

Ghi cả JVM flags, profile và các biến môi trường có ảnh hưởng đến Spring. java -version cần chỉ ra cùng JDK vendor và version cho cả hai lượt.

## 7. Chạy benchmark lặp lại

Biên dịch launcher bằng JDK 17:

```powershell
javac benchmark/StartupBenchmark.java
```

Đo baseline với ba lượt warm-up và mười lượt được tính:

```powershell
java -cp benchmark StartupBenchmark artifacts/before.jar before 3 10 http://127.0.0.1:18080/actuator/health/readiness http://127.0.0.1:18080/actuator/startup
```

Đo phiên bản sau bằng cùng tham số:

```powershell
java -cp benchmark StartupBenchmark artifacts/after.jar after 3 10 http://127.0.0.1:18080/actuator/health/readiness http://127.0.0.1:18080/actuator/startup
```

Mỗi lần chạy sẽ khởi động một process, đợi readiness HTTP 200, ghi thời gian, lưu log và lấy startup timeline. Chương trình tính median, min và max của mười lượt đo; ba lượt đầu chỉ để làm nóng cache hệ điều hành và không đưa vào thống kê.

Với một phép đo nghiêm túc hơn:

- Chạy nhiều batch và đổi thứ tự, ví dụ thứ tự ABBA: baseline → after → after → baseline, để giảm ảnh hưởng của tải máy hoặc thay đổi nhiệt độ CPU theo thời gian.
- Giữ cùng port, cùng dữ liệu và cùng trạng thái dịch vụ phụ thuộc.
- Không chạy build, test suite hoặc tác vụ nặng khác song song với benchmark.
- Dùng cùng timeout, chu kỳ poll 50 ms và cùng health group.
- Giữ cùng JAVA_TOOL_OPTIONS, -Xms, -Xmx, GC và các JVM flags.
- Nếu cần đo cold start với page cache lạnh, phải định nghĩa và kiểm soát riêng cách làm lạnh cache. Việc khởi động process mới không đồng nghĩa hệ điều hành đã xóa filesystem cache.

Ba lượt warm-up ở đây tạo ra số đo **fresh JVM process với OS cache có thể đã ấm**. Đây là tình huống lặp lại thường gặp khi restart service trên một host đang hoạt động. Không gọi kết quả này là cold boot của toàn hệ điều hành.

## 8. Đọc số liệu và kết luận

Dùng median làm số liệu chính vì một lượt chậm bất thường có thể kéo mean lên cao. Min/max cho thấy độ phân tán; giữ lại toàn bộ raw samples để người khác có thể kiểm tra.

Công thức:

```text
delta_ms = median_after - median_before

improvement_percent =
    (median_before - median_after) / median_before * 100
```

- delta_ms âm: phiên bản sau khởi động nhanh hơn.
- improvement_percent dương: thời gian giảm.
- improvement_percent âm: thời gian tăng.

Không kết luận một thay đổi có ích chỉ vì một lần chạy nhanh hơn. Nếu chênh lệch median nhỏ hơn độ dao động giữa các lượt, kết quả chưa đủ mạnh; tăng số batch hoặc giảm nhiễu môi trường trước khi kết luận.

Khi đã có chênh lệch tổng, mở các file *-startup.json tương ứng và tìm:

1. Startup step nào tăng/giảm thời gian nhiều nhất?
2. Bean nào có tag beanName và mất nhiều thời gian khởi tạo?
3. Thời gian nằm ở component scan, configuration parsing, bean instantiation, server startup hay runner?
4. Có thêm bước kết nối database, migration, broker hoặc gọi HTTP bên ngoài không?
5. Số lượng bean/step có thay đổi ngoài dự kiến không?

Đừng chỉ nhìn Started ... seconds trong log. Log là một chỉ báo hữu ích để đọc nhanh, còn readiness probe cung cấp mốc kết thúc nhất quán cho benchmark bên ngoài.

Nếu thay đổi bật lazy initialization, startup có thể giảm vì bean được tạo muộn hơn. Spring Boot cũng lưu ý lazy initialization có thể trì hoãn phát hiện lỗi cấu hình tới lúc bean được sử dụng. Trong trường hợp đó, đo thêm latency của request đầu tiên hoặc thao tác nghiệp vụ đầu tiên. Nếu không, ta có thể nhầm việc chuyển chi phí sang request đầu thành một tối ưu tổng thể.

## 9. Phân biệt phép đo code change với phép đo AOT

AOT là một biến thể build/runtime riêng. Spring Boot process-aot phân tích ứng dụng lúc build và tạo mã tối ưu; với native image, AOT là bước bắt buộc. Trong quá trình này, các condition và profile có thể được đánh giá ở build time.

Khi benchmark AOT:

- Giữ dependency graph, cấu hình nghiệp vụ, profile và dữ liệu tương đương giữa hai bản.
- Cấu hình profile/property dùng để đánh giá Conditional đúng ngay ở bước process-aot.
- Ghi lại GraalVM/native-image version, build flags, target OS/architecture và resource limits.
- So sánh JVM thường với JVM AOT, hoặc native image trước với native image sau như các cặp thử nghiệm được đặt tên rõ ràng.
- Nếu so JVM với native image, coi đó là so sánh hai runtime mode khác nhau; không quy toàn bộ chênh lệch cho một thay đổi code.
- Tách build time (AOT/native compilation) khỏi runtime process-to-ready. Hai số đo trả lời hai câu hỏi khác nhau.

Một cấu hình AOT build-time có thể cố định bean dựa trên profile hoặc condition. Không đổi runtime property để bật/tắt bean nếu quyết định đó đã được tính trong AOT artifact; phải build lại với môi trường AOT tương ứng.

## 10. Những sai lầm thường làm kết quả mất ý nghĩa

| Sai lầm | Vì sao gây sai lệch | Cách sửa |
| --- | --- | --- |
| So sánh một lần chạy trước và một lần chạy sau | Nhiễu do CPU, disk cache, network và GC có thể lớn hơn phần cải thiện | Dùng warm-up, nhiều lần đo và median. |
| Dependency tree thay đổi | Không biết phần nhanh/chậm đến từ code hay dependency | Giữ graph giống nhau hoặc tách thành benchmark dependency riêng. |
| Profile hoặc config khác nhau | Số bean và integration được tạo có thể khác | Cố định profile, properties, env và command line. |
| Chạy spring-boot:run ở một bản, java -jar ở bản kia | Launcher và classpath khác nhau | Dùng cùng artifact type và lệnh chạy. |
| Chỉ đo tới ContextRefreshedEvent | Có thể bỏ qua runner và readiness | Đo tới readiness/traffic-accepting. |
| Dùng ApplicationReadyEvent như process start | Event này xảy ra sau phần lớn startup | Dùng đồng hồ ngoài process hoặc ghi rõ chỉ đo nội bộ Spring. |
| Thay đổi log level hoặc bật --debug ở một bản | Logging và condition report tạo thêm công việc | Giữ log level và instrumentation giống nhau. |
| Thêm Actuator chỉ ở bản sau | Dependency và bean set thay đổi | Thêm giống nhau cho cả hai hoặc dùng endpoint có sẵn. |
| Đo startup nhưng không đo request đầu | Lazy init có thể chuyển thời gian sang request đầu tiên | Đo readiness và first-request latency riêng. |
| Cộng tất cả startup step durations | Step cha/con có thể lồng nhau | So sánh step tương ứng, không cộng mù quáng. |
| Gọi startup endpoint trước khi dừng đồng hồ | Thêm request chẩn đoán vào số đo | Dừng đồng hồ khi readiness 200, rồi mới GET startup JSON. |
| Gọi POST startup để xem dữ liệu | POST drain buffer | Dùng GET snapshot để đọc. |

## 11. Checklist trước khi công bố kết quả

- [ ] Hai bản dùng cùng JDK, Maven, Spring Boot và dependency tree.
- [ ] Cùng profile, file cấu hình, env, system properties và JVM flags.
- [ ] Cùng loại artifact và cùng lệnh khởi chạy.
- [ ] Cùng host/container, CPU/RAM limits và dịch vụ phụ thuộc.
- [ ] Readiness signal có cùng ý nghĩa ở cả hai bản.
- [ ] Startup instrumentation và Actuator giống nhau.
- [ ] Có warm-up và đủ lượt đo; lưu toàn bộ samples.
- [ ] Báo cáo median, min, max và phần trăm cải thiện.
- [ ] Giữ log, startup JSON, dependency tree và revision để truy vết.
- [ ] Nếu dùng lazy initialization, đã đo request đầu.
- [ ] Nếu dùng AOT/native, đã ghi rõ build-time profile, runtime mode và toolchain.

**Ghi nhớ:** phép đo có giá trị khi hai phiên bản chỉ khác ở điều đang thử nghiệm. Dùng đồng hồ ngoài process để đo tới readiness, dùng BufferingApplicationStartup và Actuator để tìm bước Spring tốn thời gian, lặp lại nhiều process mới và báo cáo median cùng độ phân tán. Khi thử AOT/native, giữ dependency và cấu hình tương đương nhưng báo cáo riêng runtime mode và build-time environment.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — SpringApplication, application events, readiness và startup tracking: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator endpoints và exposure/security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Startup endpoint API: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Maven plugin AOT processing: https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html
- Spring Boot — AOT conditions và build-time profiles: https://docs.spring.io/spring-boot/how-to/aot.html