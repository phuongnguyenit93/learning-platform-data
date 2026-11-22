# Kiểm thử khởi động từ JAR đã đóng gói thay vì chỉ chạy từ mã nguồn

## 1. Vì sao phải kiểm tra chính artifact sẽ phát hành?

Trong ứng dụng Spring Boot, lệnh `mvn spring-boot:run` hoặc `./gradlew bootRun` có thể khởi động thành công, các unit test và `@SpringBootTest` đều xanh, nhưng `java -jar app.jar` trên máy triển khai vẫn thất bại. Lý do: cách chạy từ IDE/build classpath **không hoàn toàn giống** khởi chạy executable JAR được đóng gói.

Một vài lỗi chỉ xuất hiện ở sản phẩm đóng gói:

- `spring-boot:repackage` hoặc `bootJar` chưa chạy, file được chọn là **plain JAR** thiếu Spring Boot launcher.
- Manifest không có `Main-Class`, `Start-Class` sai hoặc class main không tồn tại trong archive.
- Một dependency chỉ có trên compile/test classpath hoặc bị loại khỏi runtime package, gây `ClassNotFoundException` hoặc `NoClassDefFoundError`.
- Resource trong `src/main/resources` không có trong `BOOT-INF/classes`, bị lọc sai hoặc đường dẫn runtime khác đường dẫn mã nguồn.
- Build chạy bằng JDK mới hơn JRE môi trường phát hành, dẫn đến `UnsupportedClassVersionError`.
- Pipeline upload hoặc Dockerfile chọn nhầm file từ module khác hay artifact cũ còn sót sau build.

Đó là lý do bài này — thuộc mục **Kiểm tra bản dựng** của chủ đề **Spring Boot Build Tooling Packaging** — yêu cầu một phép thử **khởi động và gọi thật vào JAR đã đóng gói**. Đây thường gọi là **packaged-artifact smoke test** hoặc **JAR startup smoke test**.

### Mục tiêu sau bài học

1. Phân biệt kiểm tra ở source/test classpath với kiểm thử **đúng executable JAR**.
2. Biết Maven `repackage`, Gradle `bootJar`, manifest và layout `BOOT-INF` ảnh hưởng đến quá trình khởi động như thế nào.
3. Viết một ứng dụng Spring Boot Java 17+ có HTTP endpoint kiểm chứng.
4. Tạo một runner Java 17 dùng `ProcessBuilder` chạy `java -jar`, chờ HTTP với timeout, phát hiện process exit, ghi log và dọn tiến trình khi kết thúc.
5. Áp dụng workflow tương tự cho Maven và Gradle, rồi tích hợp vào CI trước khi upload/publish.
6. Phân biệt việc “server có mở cổng” với “ứng dụng đã sẵn sàng”, không diễn giải quá mức một HTTP 200.

**Phiên bản minh họa:** Spring Boot `3.3.5`, Java `17` và Maven/Gradle tương thích. Đây là phiên bản cố định để trình bày cú pháp, không hàm ý là phiên bản mới nhất. Với dự án thực tế, dùng version Java, build plugin và Spring Boot theo yêu cầu tương thích của chính dự án.

## 2. So sánh bốn cách chạy Spring Boot

| Cách chạy/kiểm thử | Nguồn classpath/entry point | Bằng chứng nhận được | Điều **không** được xác minh |
| --- | --- | --- | --- |
| `@SpringBootTest` | Test classpath, Spring test context | Bean/configuration có thể khởi tạo theo ngữ cảnh test | File JAR phát hành có manifest, launcher, runtime dependencies đúng |
| `mvn spring-boot:run` | Classes/dependencies từ Maven project | Có thể chạy từ Maven development classpath | Artifact do `package/repackage` tạo chạy bằng `java -jar` |
| `./gradlew bootRun` | Gradle `JavaExec` với build classpath | Có thể khởi động từ Gradle project | Output `bootJar` có chạy được không |
| `java -jar path/to/app.jar` | **Chính JAR đã được tạo** và boot launcher bên trong | Khởi động theo đường sẽ dùng để triển khai | Không tự chứng minh tất cả nghiệp vụ và dependencies ngoài đều đúng |

Ngay cả `@SpringBootTest(webEnvironment = RANDOM_PORT)` thường dùng test runtime classpath của build tool; nó có thể khởi động web server thật trong lúc test nhưng **không bắt buộc thực thi executable JAR** đã được đóng gói.

**Ví dụ tình huống:** mã `Application.java` đúng, cả Maven `spring-boot:run` và IDE đều thành công. Nhưng POM không cấu hình Spring Boot Maven Plugin, nên `mvn package` chỉ tạo plain JAR. Khi đưa nó lên server, `java -jar` có thể báo `no main manifest attribute`. Một packaged-JAR smoke test sẽ phát hiện lỗi trước khi publish.

Bốn lớp kiểm tra trên **bổ sung cho nhau**: unit tests nhanh, Spring context tests kiểm tra wiring, integration tests kiểm tra tương tác hệ thống, còn packaged smoke test tập trung vào **khả năng thực thi artifact phát hành**.

## 3. Thế nào là một phép thử khởi động JAR đáng tin?

Một luồng tối thiểu nên là:

~~~text
Clean workspace
      |
      v
Compile + unit tests
      |
      v
Maven package/repackage hoặc Gradle bootJar
      |
      v
Chọn ĐÚNG file executable JAR
      |
      v
Inspect manifest/layout nếu cần
      |
      v
Khởi chạy JAR trong process Java riêng
      |
      v
Chờ endpoint có giới hạn thời gian
      |
      +---- process exit sớm? ------> FAIL + đọc log
      +---- hết timeout? ----------> FAIL + đọc log
      +---- HTTP/status/body sai? --> FAIL
      |
      v
HTTP 200 + body đúng contract
      |
      v
Dọn process trong finally
      |
      v
Smoke runner trả exit code 0 -> PASS
~~~

Với một **web service** thông thường, server không tự thoát sau khi nhận request; runner sẽ **chủ động dừng** nó sau khi xác nhận đã sẵn sàng. Nếu viết test chỉ chờ child process trả exit code `0`, bạn có thể khiến build treo vô hạn. Ngược lại, với một **CLI/batch app** được thiết kế để thoát, expected exit code và stdout/stderr mới là contract chính.

Một bài smoke test tốt cần:

- Kiểm tra **file tồn tại** trước khi start.
- Chạy đúng `java -jar` bằng runtime xác định, không import class của app vào test runner.
- Bắt **process exit sớm** và có log để phân tích.
- Poll endpoint thay vì sleep một thời gian cố định.
- Có deadline hữu hạn và timeout từng HTTP request.
- Assert **status code lẫn response body** hoặc tiêu chí health rõ ràng.
- Bảo đảm process được stop kể cả khi test ném exception.
- Trả **nonzero exit code** khi fail để CI chặn bước publish.

## 4. Bài thực hành Maven: tạo một executable JAR có HTTP probe

Ví dụ Spring Boot rất nhỏ sau đây có endpoint `GET /probe` trả về `packaged-ok`. Chúng ta sẽ đóng gói nó thành JAR rồi khởi chạy và gọi endpoint từ chương trình Java khác.

### 4.1. Cấu trúc project

~~~text
packaged-startup-demo/
  pom.xml
  PackagedJarSmokeTest.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`PackagedJarSmokeTest.java` là file độc lập ở **project root**, không nằm trong `src/main/java`. Maven không tự đưa file test harness đó vào ứng dụng. Việc này giúp phân biệt code **được phát hành** với code **dùng để kiểm tra**.

### 4.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>packaged-startup-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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
~~~

**Giải thích:**

- `spring-boot-starter-parent` cung cấp cấu hình Maven tương thích với Spring Boot, bao gồm execution `repackage` đã được định nghĩa sẵn; khi khai báo `spring-boot-maven-plugin` trong `plugins`, `mvn package` có thể tạo executable JAR.
- `spring-boot-starter-web` đưa vào Spring MVC và embedded server.
- `java.version=17` đặt baseline tương thích của ví dụ; JDK thực tế dùng compile/build phải hợp lệ.
- `artifactId=packaged-startup-demo` và `version=1.0.0` tạo file local mặc định `target/packaged-startup-demo-1.0.0.jar` khi packaging là JAR, không đổi `finalName` hay classifier.
- Nếu dự án **không dùng Boot parent**, cần bind `spring-boot:repackage` vào lifecycle rõ ràng; chỉ khai báo Boot dependency chưa bảo đảm JAR executable.

### 4.3. Application.java đầy đủ, chạy được với Java 17

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @GetMapping(value = "/probe", produces = "text/plain")
    public String probe() {
        return "packaged-ok";
    }
}
~~~

Class `Application` vừa có điểm vào `main` vừa là `@RestController` cung cấp route `/probe`. Với request thành công:

~~~text
GET /probe
HTTP 200
Body: packaged-ok
~~~

Đoạn trên là **mô tả ba dữ kiện request/response**, không phải console stdout nguyên văn. Body thực sự là chuỗi `packaged-ok`, không có newline do code tự thêm. Các log Spring Boot trên console không được dùng thay cho một HTTP assertion.

### 4.4. Build JAR

Tại project root:

~~~bash
mvn clean package
~~~

Maven chạy lifecycle đến `package`, tạo archive rồi Spring Boot `repackage` thay main JAR bằng executable archive. File sẽ là:

~~~text
target/packaged-startup-demo-1.0.0.jar
~~~

Nếu có Maven Wrapper, lệnh trên tương ứng `./mvnw clean package` (Linux/macOS) hoặc `.\mvnw.cmd clean package` (Windows PowerShell). Ví dụ không tạo Wrapper tự động; dùng bản Maven phù hợp khi project chưa có Wrapper.

Dùng lệnh `jar` từ JDK để xem archive:

~~~bash
jar tf target/packaged-startup-demo-1.0.0.jar
~~~

Trong executable JAR Spring Boot 3.3 layout phổ biến, có các entry dạng:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Đây là **danh sách rút gọn**, không phải stdout đầy đủ của `jar tf`. `BOOT-INF/classes` chứa classes/resources ứng dụng; `BOOT-INF/lib` chứa runtime JAR; các class `org/springframework/boot/loader` phục vụ khởi động archive.

Nếu máy có `unzip`, xem manifest:

~~~bash
unzip -p target/packaged-startup-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Với Boot 3.3 và layout mặc định, manifest thường có:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

`Main-Class` là launcher JVM gọi khi `java -jar`; `Start-Class` là class ứng dụng launcher sẽ gọi. Các tên launcher có thể thay đổi giữa các phiên bản Boot hoặc layout WAR/ZIP, nên không hardcode chúng như một quy tắc bất biến.

## 5. Viết smoke test tự chạy JAR bằng Java 17

Chạy JAR thủ công rồi dùng curl trong terminal thứ hai dễ làm lúc thử nghiệm, nhưng automation cần kiểm soát tiến trình, port và timeout. Dưới đây là chương trình **không dùng thư viện ngoài JDK**.

Ý tưởng:

1. Nhận đường dẫn artifact **như một tham số**, không đoán glob.
2. Dùng chính `java.home` của runner để khởi chạy child JVM, tránh shell vô tình chọn JDK khác.
3. Tạm xin một cổng loopback còn trống, rồi để Spring Boot bind cổng đó.
4. Đưa stdout/stderr của Spring Boot vào log file tạm, tránh đầy output pipe.
5. Poll `GET /probe` tối đa 45 giây với timeout từng request 2 giây.
6. Fail nếu child thoát sớm, timeout hoặc HTTP 200 có body sai.
7. Dọn process trong `finally` và trả kết quả chính xác cho CI.

**Lưu ý:** chọn cổng bằng socket rồi thả ra có một khoảng thời gian nhỏ để process khác chiếm cổng (*TOCTOU race*). Bài học dùng cách này vì đơn giản trên Java 17 và các máy học tập thông thường. Với CI rất đông job hoặc yêu cầu độ ổn định cao, cân nhắc `server.port=0` kết hợp cơ chế truyền lại actual bound port, hoặc cơ chế retry chọn port.

### 5.1. File PackagedJarSmokeTest.java hoàn chỉnh

Đặt trong root cạnh `pom.xml`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class PackagedJarSmokeTest {

    private static String javaExecutable() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        String file = os.startsWith("windows")
                ? "java.exe" : "java";
        return Path.of(System.getProperty("java.home"),
                "bin", file).toString();
    }

    private static int choosePort() throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (ServerSocket socket =
                new ServerSocket(0, 50, loopback)) {
            return socket.getLocalPort();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java PackagedJarSmokeTest.java <jar-path>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException(
                    "JAR not found: " + jar);
        }

        int port = choosePort();
        Path log = Files.createTempFile("jar-smoke-", ".log");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable(),
                "-jar",
                jar.toString(),
                "--server.address=127.0.0.1",
                "--server.port=" + port,
                "--spring.main.banner-mode=off");
        builder.redirectErrorStream(true);
        builder.redirectOutput(log.toFile());

        Process child = builder.start();
        boolean passed = false;

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            URI uri = URI.create(
                    "http://127.0.0.1:" + port + "/probe");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(45);
            int lastHttpStatus = -1;

            while (System.nanoTime() < deadline) {
                if (!child.isAlive()) {
                    throw new IllegalStateException(
                            "JAR exited early; exit="
                                    + child.exitValue()
                                    + "; log=" + log);
                }

                try {
                    HttpResponse<String> response = client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
                    lastHttpStatus = response.statusCode();

                    if (lastHttpStatus == 200) {
                        if (!"packaged-ok".equals(response.body())) {
                            throw new AssertionError(
                                    "Unexpected /probe body: "
                                            + response.body());
                        }
                        passed = true;
                        System.out.println("smoke.status=PASS");
                        System.out.println("smoke.http=200");
                        System.out.println("smoke.body=packaged-ok");
                        return;
                    }
                } catch (IOException connectionNotReady) {
                    // Server may not yet be ready to accept requests.
                }

                Thread.sleep(250);
            }

            throw new IllegalStateException(
                    "Timeout waiting for /probe; last HTTP="
                            + lastHttpStatus + "; log=" + log);
        } finally {
            if (child.isAlive()) {
                child.destroy();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                    child.waitFor(5, TimeUnit.SECONDS);
                }
            }

            if (passed) {
                try {
                    Files.deleteIfExists(log);
                } catch (IOException ignored) {
                    // Log cleanup does not affect a passed probe.
                }
            } else {
                System.err.println("smoke.log=" + log);
            }
        }
    }
}
~~~

**Các chi tiết cần hiểu:**

- `System.getProperty("java.home")` lấy JDK/JRE **đang chạy runner**; `javaExecutable()` dùng đường dẫn thực thi tương ứng, giúp tránh trường hợp `PATH` có nhiều JDK. Hàm kiểm tra `os.startsWith("windows")` tránh nhầm macOS có tên hệ điều hành `Darwin` thành Windows.
- `ServerSocket(0)` để hệ điều hành chọn port tạm trên `127.0.0.1`. Sau khi đóng socket, Spring Boot có thể bind port đó. Vẫn có một khoảng hở race, nên khi có lỗi hãy xem log startup.
- `ProcessBuilder` gọi **một tiến trình độc lập** với tham số `-jar`; runner **không** import `demo.Application`, nên không thể lặng lẽ chạy source classpath.
- `redirectErrorStream(true)` và `redirectOutput(log.toFile())` ghi log khởi động ra file. Khi child fail, thông báo đưa path log để người học đọc stack trace.
- `HttpClient` gửi `GET` thật vào server. Không coi một port mở hay một log “Started” là điều kiện PASS duy nhất.
- `child.isAlive()` giúp phát hiện child chết trước khi route sẵn sàng. `IOException` do kết nối chưa sẵn sàng được thử lại; lỗi assertion không bị nuốt.
- `deadline` và `HttpRequest.timeout` giúp tránh test chạy vô hạn; `Thread.sleep(250)` giữa các lần poll giảm tần suất request mà **không** mặc định startup xong sau 250 ms.
- `finally` dọn process cả khi PASS, HTTP body sai, timeout hay exception. Một web server bình thường **không tự exit code 0** sau một request, nên runner chủ động stop nó thay vì chờ server tự thoát.
- Khi PASS, log tạm được xóa nếu xóa thành công. Khi FAIL, log được giữ để chẩn đoán. Đối với hệ thống production, cần thêm chính sách bảo vệ log vì startup log có thể chứa thông tin nhạy cảm.

### 5.2. Chạy trên Linux/macOS và Windows

Sau `mvn clean package`, chạy từ project root:

~~~bash
java PackagedJarSmokeTest.java target/packaged-startup-demo-1.0.0.jar
~~~

Trên Windows PowerShell, dùng đường dẫn Windows:

~~~powershell
java PackagedJarSmokeTest.java .\target\packaged-startup-demo-1.0.0.jar
~~~

Java 17 hỗ trợ **source-file mode** nên file runner không cần `javac` và `java -cp` riêng. Hai lệnh trên đều khởi động một JVM thứ hai bằng `java -jar` đối với archive đã đóng gói.

Khi thành công, **stdout của test runner** là chính xác:

~~~text
smoke.status=PASS
smoke.http=200
smoke.body=packaged-ok
~~~

Đây là ba dòng do chính `PackagedJarSmokeTest` in. Spring Boot logs của tiến trình con ở trong file log, không xen vào output này. Một HTTP body `packaged-ok` có thể bị biến đổi bởi application code của một dự án thật; nếu thay endpoint, phải sửa assertion để phản ánh **contract đã định**, không xóa assertion chỉ để test xanh.

Khi fail, Java launcher trả exit code khác `0` và in stack trace; runner giữ log để xem lỗi Spring Boot. Không coi dấu hiệu file tồn tại hoặc HTTP status 200 từ **một process khác** là bằng chứng pass.

### 5.3. Bốn trường hợp FAIL minh họa

**Lỗi 1 — sai path**

~~~text
JAR not found: ...
~~~

Sửa đường dẫn, xác định module và `finalName`/classifier. Nếu package chưa chạy, hãy chạy đúng task package trước. Đừng tạo một file giả hoặc chạy `spring-boot:run` để “vượt” kiểm tra.

**Lỗi 2 — child exit sớm**

~~~text
JAR exited early; exit=1; log=...
~~~

JVM đã thoát trước khi endpoint sẵn sàng. Mở log: có thể main class/Java version, dependency, cấu hình runtime hoặc bind port lỗi. Không khẳng định nguyên nhân chỉ dựa vào exit code `1`.

**Lỗi 3 — timeout**

~~~text
Timeout waiting for /probe; last HTTP=-1; log=...
~~~

`last HTTP=-1` nghĩa là runner **chưa nhận được HTTP response nào**, không nhất thiết là packet bị chặn. Nếu đã nhận `404`, `401` hay `503`, trường `last HTTP` sẽ lưu status đó để điều tra endpoint, security hoặc readiness.

**Lỗi 4 — body không đúng**

~~~text
Unexpected /probe body: ...
~~~

Nếu response HTTP 200 nhưng body khác `packaged-ok`, test **FAIL ngay**. Trường hợp này có thể do route thay đổi, artifact sai, hoặc port bị chiếm và request rơi vào service khác. Một assertion chỉ kiểm tra 200 là chưa đủ khi cần biết chính ứng dụng được kiểm thử.

## 6. Bảo đảm bài test dùng đúng JAR vừa được build

### 6.1. Chọn đúng file giữa nhiều artifact

Một project có thể có:

~~~text
target/
  packaged-startup-demo-1.0.0.jar
  packaged-startup-demo-1.0.0.jar.original
  packaged-startup-demo-1.0.0-exec.jar
~~~

Đây là **các ví dụ tên xuất hiện trong những cấu hình khác nhau**, không phải khẳng định mọi build tạo cả ba. Maven Spring Boot `repackage` mặc định có thể thay main artifact và lưu plain JAR với đuôi `.original`. Nếu dùng classifier `exec`, executable archive có thể được attach riêng ở `-exec.jar`.

Đừng chọn `target/*.jar` một cách mù quáng vì wildcard có thể khớp nhiều file. Chọn **chính archive sẽ deploy**, kiểm tra manifest khi nghi ngờ, rồi truyền path đầy đủ cho runner.

Với Gradle, `jar` task có thể tạo plain JAR trong khi `bootJar` tạo executable archive. Kiểm tra `archiveFileName` hoặc output path được build tool báo, không suy ra mọi file dưới `build/libs` đều khởi động được.

### 6.2. Đừng dùng JAR cũ còn trong target

Khi CI không dùng `clean`, có thể sót `target/app-old.jar` từ build trước. Một smoke test vô tình chỉ vào file cũ sẽ PASS dù commit mới tạo artifact lỗi. Hãy build trong workspace sạch, kiểm tra timestamp/artifact path và chỉ truyền tên file của build vừa hoàn tất.

Một chuỗi lệnh đúng:

~~~bash
mvn clean package
java PackagedJarSmokeTest.java target/packaged-startup-demo-1.0.0.jar
~~~

Một chuỗi lệnh **không** chứng minh packaged JAR:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Lệnh thứ hai chạy project theo cơ chế development plugin, không thực thi file archive bằng `java -jar`. Tương tự, Gradle `bootRun` không thay cho `bootJar` smoke.

### 6.3. Kiểm tra bytes giữa test và publish

Một artifact có thể bị thay sau smoke test (ví dụ pipeline rebuild hoặc copy một file khác). Muốn đảm bảo publish **đúng artifact đã test**, so sánh SHA-256 hoặc artifact identifier ở các bước pipeline.

Linux/macOS:

~~~bash
sha256sum target/packaged-startup-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\packaged-startup-demo-1.0.0.jar -Algorithm SHA256
~~~

Digest thay đổi khi nội dung file thay đổi. Không hardcode một checksum giả trong tài liệu; hãy lưu checksum thực và đối chiếu với artifact ở bước upload/deploy. Với Docker image, cần thêm test trên **chính image cuối** vì Dockerfile, base JRE, quyền file và entrypoint có thể khác host runtime.

## 7. Quy trình tương đương với Gradle bootJar

Dùng `build.gradle` (Groovy DSL) như sau, giữ nguyên `src/main/java/demo/Application.java` và runner ở root:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.learning'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

tasks.named('bootJar') {
    archiveFileName = 'packaged-startup-demo.jar'
}
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'packaged-startup-demo'
~~~

Build và smoke từ đúng root của project có Gradle Wrapper:

~~~bash
./gradlew clean bootJar
java PackagedJarSmokeTest.java build/libs/packaged-startup-demo.jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
java PackagedJarSmokeTest.java .\build\libs\packaged-startup-demo.jar
~~~

`bootJar` là task tạo executable Spring Boot JAR; `bootRun` là task chạy ứng dụng từ classpath của project. Gradle `assemble` hoặc `build` có thể phụ thuộc `bootJar` trong cấu hình Spring Boot/Java plugin chuẩn, nhưng bản thân `build` **không tự chạy packaged black-box smoke test** nếu bạn chưa tạo/cấu hình task riêng.

**Lưu ý Java Toolchains:** Gradle toolchain có thể chọn JDK dùng compile độc lập JVM chạy build. Runner dùng JDK khởi chạy chính runner để chạy child, vì vậy CI phải chọn **đúng Java runtime mục tiêu** nếu muốn kiểm thử tương thích triển khai. Chạy artifact Java 17 trên JDK 21 không đủ chứng minh production Java 17 chạy được.

## 8. Phân biệt startup, liveness, readiness và business health

Endpoint `/probe` trong ví dụ xác nhận rằng Spring Boot HTTP server đã có thể trả một response cụ thể. Đây là mức kiểm thử rất có ích, nhưng không đồng nghĩa toàn hệ thống sẵn sàng phục vụ mọi tác vụ.

| Mức kiểm tra | Ví dụ bằng chứng | Không nên suy ra |
| --- | --- | --- |
| Process liveness | `child.isAlive()` là `true` | HTTP server đã bind hoặc có thể phục vụ request |
| TCP listen | Kết nối port thành công | Route và HTTP status đúng |
| HTTP smoke | `GET /probe` trả 200 + body đúng | DB, broker, SSO đều đang ổn |
| Application readiness | Health group readiness phản ánh trạng thái nhận traffic | Mọi giao dịch nghiệp vụ đều đúng |
| Integration/contract | Gọi database/API/message thực | Tất cả luồng E2E đều đã kiểm tra |
| End-to-end | Nhiều tầng tham gia vào một flow thực | Không còn rủi ro môi trường/chạy dài hạn |

### 8.1. Dùng Spring Boot Actuator khi phù hợp

Nếu dự án có `spring-boot-starter-actuator`, `/actuator/health` là health endpoint quen thuộc. Spring Boot có application availability với liveness/readiness indicators và health groups như `/actuator/health/liveness` và `/actuator/health/readiness` trong môi trường/cấu hình bật probes phù hợp.

Không mặc định endpoint ấy luôn public/luôn `200`: `Spring Security`, actuator exposure, management port, context path và health status có thể thay đổi kết quả. Với production-like test, dùng endpoint readiness thực tế của deployment và cấu hình quyền truy cập phù hợp; nếu trả `401`/`403`, cần đọc chính sách security trước khi kết luận app không khởi động.

**Liveness** chỉ ra tiến trình có cần restart không; **readiness** chỉ ra có nên nhận traffic không. Không nên đưa mọi external dependency vào liveness để tránh restart dây chuyền khi hệ thống ngoài gián đoạn. Packaged smoke và readiness/dependency tests nên được phân tầng thay vì trộn lẫn không kiểm soát.

### 8.2. Service có context path hoặc security

Nếu service thật đặt `server.servlet.context-path=/api`, route `/probe` sẽ ở `/api/probe`. Runner ở ví dụ dùng path cố định để học cơ chế; trong dự án thực, hãy tham số hóa URL hoặc đọc config test để khớp route. Tương tự, nếu security yêu cầu authentication, cần kiểm tra endpoint được phép truy cập trong môi trường kiểm thử thay vì tắt toàn bộ security chỉ để được 200.

## 9. Gắn phép thử vào CI mà không làm sai ý nghĩa

Pipeline nên theo thứ tự:

~~~text
Checkout code
    -> xác nhận toolchain/JDK
    -> compile + unit tests
    -> build executable JAR
    -> packaged JAR smoke test
    -> archive / publish ĐÚNG JAR đã test
    -> deploy
    -> health/readiness smoke ở môi trường đích
~~~

Cần bảo đảm một stage fail thì stage publish **không chạy**. Không chạy smoke test bằng `mvn spring-boot:run` hay `bootRun` rồi gắn nhãn là “packaged JAR verified”.

### 9.1. Maven trong POSIX shell

~~~bash
set -e
mvn clean package
java PackagedJarSmokeTest.java target/packaged-startup-demo-1.0.0.jar
~~~

`set -e` là ví dụ đơn giản trong script POSIX thông thường; hành vi có ngoại lệ theo ngữ cảnh shell. Với CI provider, dùng chính tính năng fail-on-nonzero của step để không vô tình tiếp tục publish sau khi smoke runner fail.

### 9.2. Gradle trong POSIX shell

~~~bash
set -e
./gradlew clean bootJar
java PackagedJarSmokeTest.java build/libs/packaged-startup-demo.jar
~~~

Với Windows PowerShell, nếu viết script gồm nhiều lệnh native, phải kiểm tra `LASTEXITCODE` hoặc chế độ fail phù hợp; không luôn giả định một lệnh Java trả nonzero sẽ tự khiến script dừng.

### 9.3. Maven Failsafe khác việc tự kiểm thử executable JAR

`maven-surefire-plugin` thường chạy unit tests, còn `maven-failsafe-plugin` hỗ trợ integration tests qua các lifecycle phases `integration-test` và `verify`. Tuy nhiên, **chỉ thêm Failsafe hoặc chạy `mvn verify` không tự tạo packaged-JAR test**. Bạn phải viết một integration test thật sự gọi `java -jar` đối với file đã package, hoặc đưa bước smoke runner vào CI sau khi artifact được tạo.

Nếu đưa packaged smoke vào hệ thống JUnit/Failsafe hoặc Gradle verification tasks, cần kiểm tra:
- Phase/task chạy **sau** `package/repackage` hoặc `bootJar`.
- Artifact file được truyền là output của build hiện tại.
- Không sử dụng test classpath thay cho archive.
- Process được cleanup dù có assertion exception.
- Kết quả test được phản ánh ở exit code/report để chặn publish.

Runner độc lập trong bài được chọn để nhìn rõ ranh giới giữa **build** và **chạy artifact**; trong project thật có thể tích hợp nó bằng task/plugin theo conventions nội bộ.

## 10. Cô lập process, port và môi trường

### 10.1. Không dùng cổng cố định mà không kiểm soát

Nếu hardcode `8080` và một service cũ đang chạy, test có thể nhận HTTP 200 từ **service không phải JAR mới**. Runner xin port loopback ngẫu nhiên, kiểm tra child còn sống và assert body. Đây là cách giảm rủi ro, nhưng vẫn có khoảng race nhỏ giữa lấy port và Spring Boot bind.

Đối với test yêu cầu định danh instance tuyệt đối, dùng nonce duy nhất được truyền vào app và phản hồi qua endpoint, hoặc kênh truyền bound port từ chính process mới; không chỉ lấy “HTTP 200 từ localhost” làm bằng chứng danh tính ứng dụng.

### 10.2. Log và timeout hữu hạn

Một cách test thủ công kém tin cậy:

~~~bash
java -jar app.jar &
sleep 3
curl http://localhost:8080/health
~~~

Nếu không lưu PID và không có trap/cleanup, process có thể còn chạy sau job. Ngay cả `sleep 3` cũng không chứng minh app đã ready: CI có thể chậm hơn hoặc app chết sớm.

Runner trong bài dùng:
- Deadline tổng 45 giây, timeout HTTP request 2 giây.
- Kiểm tra `isAlive` trước mỗi request.
- Retry có giới hạn khi kết nối chưa sẵn sàng.
- Fail ngay khi HTTP 200 nhưng body sai.
- `ProcessBuilder` redirect logs vào file để không nghẽn output stream.
- `finally` dừng child, kể cả khi FAIL.

Đây là **cấu hình minh họa**, không phải SLA chung cho tất cả dịch vụ. Dự án thật nên điều chỉnh thời gian theo startup profile và tài nguyên CI.

### 10.3. Working directory và runtime environment

`java -jar` có thể được khởi động ở một working directory khác IDE. Nếu mã nguồn dùng `Files.readString(Path.of("config/service.yml"))`, nó sẽ tìm **file tương đối với working directory**, không phải resource trong JAR. Nếu ứng dụng cần resource packaged, thường nên lấy từ classpath bằng `ClassLoader.getResourceAsStream` hoặc API tương đương.

Smoke test nên chạy dưới cấu hình gần deployment: Java runtime đúng version, profile phù hợp, biến môi trường cần thiết và working directory có chủ đích. Nếu local có sẵn các file bí mật hoặc config mà CI không có, cần phát hiện sự phụ thuộc ngoài ý định. Không copy secrets thật vào repo hoặc log smoke test.

### 10.4. Khi sản phẩm cuối là OCI image hoặc WAR

Packaged-JAR smoke kiểm tra executable JAR trên host, nhưng không chứng minh Docker image chạy đúng vì image có base JRE, permissions, file system, entrypoint, user và networking khác. Với Docker/OCI, sau smoke JAR còn cần chạy **image cuối cùng** và probe endpoint trong container.

Với executable WAR hoặc WAR triển khai vào servlet container ngoài, layout và cách khởi chạy khác. Phải kiểm tra **đúng artifact và đúng launch mode** sẽ dùng thực tế; không áp nguyên lệnh JAR lên mọi WAR.

## 11. Trường hợp không phải HTTP server: CLI và batch applications

Không phải mọi Spring Boot application đều mở cổng web. Một CLI application có thể chạy `CommandLineRunner`, in kết quả rồi tự thoát. Khi đó test startup của artifact cần:

1. Khởi chạy `java -jar path/to/cli.jar` với args thích hợp.
2. Chờ process kết thúc với một timeout hữu hạn.
3. Kiểm tra exit code `0` nếu thành công là contract, và kiểm tra stdout/stderr hoặc file output kỳ vọng.
4. Khi timeout, hủy process trong `finally`.
5. Đảm bảo input dữ liệu test, working directory và môi trường được cô lập.

Đừng reuse HTTP runner ở mục 5 cho CLI, vì nó sẽ coi việc process tự thoát là lỗi và chờ endpoint không tồn tại. Ngược lại, không dùng “process exit code 0” như tiêu chí chính cho một web server cần chạy liên tục. Bài này chọn HTTP server để thực hành startup/serving readiness.

## 12. Bảng chẩn đoán lỗi từ JAR thật

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra trước tiên |
| --- | --- | --- |
| `JAR not found` | Sai path, module, `finalName`, classifier hoặc package chưa chạy | Xem output task, chọn file cụ thể của build hiện tại |
| `no main manifest attribute` | Plain JAR, repackage/bootJar chưa chạy hoặc chọn sai artifact | Xem manifest, `BOOT-INF`, plugin execution |
| `ClassNotFoundException` cho launcher | Thiếu Spring Boot loader hoặc archive bị biến đổi | `jar tf`, `Main-Class`, checksum artifact |
| `ClassNotFoundException` cho app main | `Start-Class` sai, class không có trong `BOOT-INF/classes` | So FQCN, compiled class và manifest |
| `NoClassDefFoundError` | Runtime dependency thiếu hoặc classpath mismatch | Xem `BOOT-INF/lib`, Maven/Gradle resolved graph |
| `NoSuchMethodError` | Binary incompatibility giữa các version runtime | Xem selected versions và libs trong JAR |
| `UnsupportedClassVersionError` | Runtime Java quá cũ so với bytecode compile | `java -version` ở nơi chạy, compiler/toolchain config |
| Web server bind port fail | Port đã chiếm, interface sai hoặc permissions | Child log, port settings, process khác |
| Timeout với HTTP `-1` | Không nhận phản hồi, app khởi động chậm/chết hoặc endpoint chưa bind | Child log, process state, networking |
| HTTP `401`/`403` | Endpoint bị security bảo vệ | Spring Security/Actuator config, quyền truy cập |
| HTTP `404` | Sai route, context path hoặc artifact | Request URL, route mapping, log khởi động |
| HTTP `503` | Health/readiness chưa đạt hoặc ứng dụng báo unavailable | Health details, dependencies bắt buộc |
| HTTP `200` nhưng body khác | Route thay đổi, app khác hoặc artifact sai | Assertion, identity, port và build path |
| `spring-boot:run` đúng nhưng JAR lỗi | Classpath khác nhau hoặc packaging cấu hình sai | Manifest, `BOOT-INF/lib`, resource và plugin logs |
| JAR host PASS nhưng image FAIL | JRE, env, file permissions, entrypoint khác | Chạy/probe chính OCI image cuối |
| Smoke test xanh nhưng deploy chạy bản cũ | Artifact khác checksum, CI chọn file khác | So SHA-256 và đường dẫn qua các stage |

Đây là **các giả thuyết đầu tiên**, không phải chẩn đoán duy nhất từ một exception. Hãy ưu tiên child log và kiểm tra chính file JAR đã chạy.

## 13. Checklist trước khi publish

1. Chọn JDK/runtime mà môi trường triển khai thật hỗ trợ; xác nhận Maven/Gradle/Boot tương thích.
2. Chạy compile, unit tests và package từ workspace sạch.
3. Với Maven: bảo đảm `spring-boot:repackage` có hiệu lực; với Gradle: dùng `bootJar`.
4. Xác định đúng **artifact file sẽ phát hành**; không dùng wildcard giữa nhiều JAR.
5. Khi nghi ngờ, xem manifest, `Start-Class`, `BOOT-INF/classes` và `BOOT-INF/lib`.
6. Khởi động **chính archive** bằng `java -jar`, không thay bằng `spring-boot:run`/`bootRun`.
7. Chọn endpoint kiểm tra đúng mục tiêu; assert HTTP status và body/health contract.
8. Có timeout, phát hiện process exit, log và cleanup trong mọi nhánh.
9. Bảo đảm test FAIL khiến publish/deploy bị chặn; không nuốt exit code.
10. Dùng checksum hoặc artifact identity xác nhận file được deploy là file đã test.
11. Bổ sung image/production-readiness smoke nếu output cuối là container hoặc hạ tầng khác host.
12. Duy trì unit/integration/e2e tests riêng; smoke test không thay thế các lớp kiểm thử đó.

### Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `@SpringBootTest` xanh chưa đủ chứng minh `java -jar` chạy được?

**Trả lời:** Spring test thường dùng test classpath, chưa kiểm tra manifest, Boot launcher, nested dependencies và file artifact cuối.

**Câu 2:** Nếu JAR được package thành công nhưng runner báo `no main manifest attribute`, cần kiểm tra gì?

**Trả lời:** Chọn đúng executable archive; xác minh `repackage`/`bootJar` và `META-INF/MANIFEST.MF`.

**Câu 3:** Web server chạy ổn định và không tự thoát. Sau khi endpoint PASS, runner nên làm gì?

**Trả lời:** Chủ động dừng process con trong cleanup; không chờ server tự trả exit code `0`.

**Câu 4:** HTTP 200 trên port 8080 có đủ chứng minh JAR mới chạy không?

**Trả lời:** Chưa. Một server cũ có thể trả 200. Dùng port cô lập, kiểm tra process mới và response contract; khi cần, thêm instance identity.

**Câu 5:** Vì sao cần test thêm Docker image dù host `java -jar` đã PASS?

**Trả lời:** Base JRE, user permissions, environment, entrypoint và filesystem có thể khác, dẫn đến lỗi chỉ xuất hiện trong image cuối.

## 14. Tài liệu tham khảo chính thức

- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot 3.3 — First Application and Maven package: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot Gradle Plugin — Packaging: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot Actuator — Endpoints, Liveness and Readiness: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Apache Maven Failsafe Plugin — Integration Test Lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/index.html
- Gradle — Testing Java Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Java 17 API — ProcessBuilder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Java 17 API — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html

**Ghi nhớ:** Build xanh chưa chứng minh **archive được phát hành** chạy được. Hãy build executable JAR, chọn đúng file, khởi chạy nó bằng `java -jar` trong một process riêng, chờ bằng HTTP probe có timeout/cleanup và chỉ publish **chính artifact đã được kiểm chứng**.