# Đóng gói JAR đã kiểm chứng thành image OCI bằng Dockerfile

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot có thể được build thành executable JAR, chạy tốt bằng `java -jar` trên máy developer, nhưng thất bại khi khởi động bên trong Docker/Kubernetes. Nguyên nhân thường không nằm ở Java source code: image có thể sử dụng JRE khác, Dockerfile copy nhầm plain JAR, cổng và địa chỉ bind sai, quyền file không đủ, biến môi trường bị thiếu hoặc image được build từ một artifact khác file đã vượt qua QA.

Bài thuộc mục **Dockerfile** của chủ đề **Spring Boot Build Tooling Packaging**, với mục tiêu cụ thể: **đóng gói chính executable JAR đã được kiểm chứng thành image tương thích OCI**, sau đó chứng minh rằng image có đúng bytes của JAR đó và ứng dụng thực sự hoạt động trong container.

Bạn sẽ học cách:

1. Phân biệt **executable JAR**, **OCI image**, **image tag**, **image digest**, và **running container**.
2. Tạo một Spring Boot Java 17 web application và Maven executable JAR với tên artifact rõ ràng.
3. Tạo gate kiểm thử JAR thật trước Docker build, không thay bằng `spring-boot:run`.
4. Viết Dockerfile **chỉ COPY đúng JAR đã được test**, sử dụng JRE 17 và non-root user.
5. Giới hạn Docker build context bằng `.dockerignore` để tránh vô tình gửi secrets, source hoặc JAR dư.
6. Đối chiếu bytes JAR trên host với JAR trích từ chính image bằng `docker create`, `docker cp`, `cmp`/SHA-256.
7. Chạy image, publish cổng có kiểm soát, probe HTTP và dọn container dù test PASS hay FAIL.
8. Xử lý image tags, registry digests, architecture, base image cập nhật và các lỗi CI thường gặp.
9. Hiểu khi nào cần layered image hoặc multi-stage build mà vẫn giữ khả năng truy vết đúng artifact.

**Bộ ví dụ:** Java `17`, Spring Boot `3.5.16`, Maven tương thích, Docker Linux containers và `eclipse-temurin:17-jre-jammy`. Đây là các version minh họa; tag image nền có thể thay đổi theo patch, vì vậy production nên pin digest được xác minh và có quy trình cập nhật.

## 2. Phân biệt JAR và image OCI

| Đối tượng | Ví dụ | Thành phần | Danh tính |
| --- | --- | --- | --- |
| Executable JAR | `target/oci-demo-1.0.0.jar` | Boot loader, classes/resources, nested dependencies | Hash SHA-256 của **file JAR** |
| OCI/Docker image | `oci-demo:1.0.0` | JRE, OS filesystem layers, JAR được copy, image config và manifest | Local image ID hoặc registry manifest/index digest |
| Running container | `oci-demo-smoke` | Process Java và writable layer dựa trên image | Container ID, status và logs |

Theo OCI Image Specification, image thường gồm manifest, configuration và filesystem layers. File JAR chỉ là **một phần** filesystem image. Do đó **JAR SHA-256 không phải image digest**, và hai image digests khác nhau không tự chứng minh JAR bên trong khác bytes.

Image tag như `oci-demo:1.0.0` là một **tên có thể gán lại**, không phải chứng cứ immutable. Registry digest mới chỉ rõ manifest/index nội dung đã được push. Với multi-platform image, digest của image index và digest của từng platform manifest còn có thể khác nhau.

**Mục tiêu kép của bài:**

~~~text
Git revision + source + pom.xml
          |
          v
      mvn clean verify
          |
          v
  executable JAR trên host
          |
          +-- GATE 1: java -jar, HTTP probe, SHA-256
          |
          v
  Dockerfile COPY đúng file JAR
          |
          v
  OCI-compatible container image
          |
          +-- GATE 2A: JAR bytes trong image == JAR đã test
          |
          +-- GATE 2B: JRE trong image + HTTP smoke
          |
          v
  Ghi image identity/digest và publish đúng image
~~~

Bước `docker build` của ví dụ **không chạy Maven thêm lần nữa**. Nếu CI kiểm chứng file A rồi Dockerfile/multi-stage build lại sinh file B, không được tuyên bố image chứa artifact A nếu chưa xác minh bytes B trùng A.

## 3. Project Java 17/Spring Boot độc lập

### 3.1. Cấu trúc project

~~~text
oci-demo/
  pom.xml
  Dockerfile
  .dockerignore
  SmokeJar.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`SmokeJar.java` là **test runner riêng tại project root**. Vì không nằm trong `src/main/java`, Maven không đóng nó vào application JAR. Điều này giúp kiểm tra **archive đã phát hành**, không lặng lẽ chạy source/test classpath của build tool.

### 3.2. pom.xml đầy đủ

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>oci-demo</artifactId>
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

Spring Boot starter parent cung cấp dependency management và cấu hình plugin; khi `spring-boot-maven-plugin` được khai báo, goal `repackage` tham gia package lifecycle theo parent. Kết quả với `artifactId=oci-demo`, `version=1.0.0`, không classifier và không custom `finalName`, là `target/oci-demo-1.0.0.jar`.

Không đánh đồng `mvn package` với JAR chắc chắn chạy được: nếu project khác không kế thừa Boot parent hoặc repackage execution bị tắt, Maven có thể chỉ tạo plain JAR. Bắt buộc kiểm tra **file thực tế**.

### 3.3. Application.java đầy đủ

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @GetMapping(value = "/probe",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return "oci-jar-ok";
    }
}
~~~

Với một GET request thành công đến `/probe`, HTTP status là **200** và body chính xác là:

~~~text
oci-jar-ok
~~~

`/probe` là một kiểm tra nhỏ về khởi động web server và Spring MVC route, không tự chứng minh database/SSO/broker của các dự án lớn đã sẵn sàng. Trong ví dụ không cấu hình `server.address=127.0.0.1` cố định trong application config, vì server bên trong container cần bind interface có thể nhận traffic từ Docker port forwarding.

### 3.4. Build và xem archive

Tại root project:

~~~bash
mvn -B -ntp clean verify
jar tf target/oci-demo-1.0.0.jar
~~~

`verify` bao gồm compile, tests, package và `repackage` trong ví dụ có Boot parent. Những entries đặc trưng của executable Spring Boot JAR:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Đây là **danh sách minh họa rút gọn**, không phải output nguyên văn của `jar tf`. `BOOT-INF/classes` chứa code/resources ứng dụng và `BOOT-INF/lib` chứa runtime dependencies.

Nếu dùng Maven Wrapper đã được project cung cấp, thay `mvn` bằng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows PowerShell). Không gọi Wrapper nếu chưa có trong repo.

## 4. GATE 1: kiểm thử chính executable JAR trước khi tạo image

### 4.1. Lý do cần java -jar

`mvn spring-boot:run` và IDE chạy dựa trên development classpath, không xác nhận manifest/nested libraries của archive được phát hành. Một gate đáng tin phải gọi **đúng đường dẫn file JAR output**, chờ endpoint với timeout và trả nonzero exit code khi lỗi.

Có thể chạy thủ công:

~~~bash
java -jar target/oci-demo-1.0.0.jar \
  --server.address=127.0.0.1 \
  --server.port=18080
~~~

Rồi từ terminal khác:

~~~bash
curl -fsS http://127.0.0.1:18080/probe
~~~

Body kỳ vọng là `oci-jar-ok`. Khi hoàn tất, dừng Java server bằng `Ctrl+C`. Tuy nhiên để CI không treo hoặc quên cleanup, chúng ta dùng runner Java 17.

### 4.2. SmokeJar.java (Java 17 Standard Library)

Tạo file `SmokeJar.java` tại project root:

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

public class SmokeJar {

    private static String javaExecutable() {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        return Path.of(System.getProperty("java.home"),
                "bin", os.startsWith("windows")
                        ? "java.exe" : "java").toString();
    }

    private static int choosePort() throws IOException {
        try (ServerSocket socket = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"))) {
            return socket.getLocalPort();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java SmokeJar.java <jar-file>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException(
                    "JAR not found: " + jar);
        }

        int port = choosePort();
        Path log = Files.createTempFile("oci-jar-smoke-", ".log");

        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable(),
                "-jar", jar.toString(),
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

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + port + "/probe"))
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(45);

            while (System.nanoTime() < deadline) {
                if (!child.isAlive()) {
                    throw new IllegalStateException(
                            "JAR exited early; exit="
                                    + child.exitValue()
                                    + "; log=" + log);
                }

                try {
                    HttpResponse<String> response =
                            client.send(request,
                                    HttpResponse.BodyHandlers.ofString(
                                            StandardCharsets.UTF_8));
                    if (response.statusCode() == 200) {
                        if (!"oci-jar-ok".equals(response.body())) {
                            throw new AssertionError(
                                    "Unexpected body: "
                                            + response.body());
                        }
                        passed = true;
                        System.out.println("jar.smoke=PASS");
                        System.out.println(
                                "jar.probe=oci-jar-ok");
                        return;
                    }
                } catch (IOException serverNotReady) {
                    // Retry while Spring Boot starts.
                }
                Thread.sleep(250);
            }

            throw new IllegalStateException(
                    "Timeout waiting for /probe; log=" + log);
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
                    // Does not change the HTTP result.
                }
            } else {
                System.err.println("jar.smoke.log=" + log);
            }
        }
    }
}
~~~

`ProcessBuilder` gọi **một tiến trình JVM riêng** bằng `-jar`, không import application classes vào runner. `HttpClient` kiểm tra thật HTTP 200/body; deadline 45 giây và timeout từng request 2 giây hạn chế treo. `finally` dừng process dù PASS hay FAIL, tránh giữ port cho job khác.

Cách xin port tạm bằng `ServerSocket(0)` có khoảng hở nhỏ giữa đóng socket và lúc Spring Boot bind, nên trên CI đông jobs có thể cải tiến bằng bound-port discovery hoặc instance identity. Đây là phiên bản minh họa phù hợp để thực hành Java 17.

### 4.3. Thực hiện Gate 1

~~~bash
java SmokeJar.java target/oci-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
java SmokeJar.java .\target\oci-demo-1.0.0.jar
~~~

Khi PASS, stdout **do runner in** chính xác:

~~~text
jar.smoke=PASS
jar.probe=oci-jar-ok
~~~

Nếu JAR thiếu, tiến trình chết, route sai, timeout hoặc body sai, runner ném exception, trả exit code khác 0 và giữ startup log. Đừng chạy Docker build nếu gate này fail.

Lưu SHA-256 **của JAR đã PASS**:

~~~bash
sha256sum target/oci-demo-1.0.0.jar
~~~

PowerShell:

~~~powershell
Get-FileHash .\target\oci-demo-1.0.0.jar -Algorithm SHA256
~~~

Không ghi một SHA giả trong tài liệu. Từ sau gate này, **không rebuild JAR âm thầm** trước image build; nếu build lại, phải kiểm tra đúng file mới.

## 5. Dockerfile hoàn chỉnh: JRE 17, exact COPY, non-root, exec ENTRYPOINT

Tạo file `Dockerfile` tại root project:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

COPY --chown=10001:10001 target/oci-demo-1.0.0.jar /app/application.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Dockerfile này không có Maven, `RUN mvn`, compiler hay Git. Nó đưa **một artifact có sẵn** vào một runtime image chứa JRE 17.

| Instruction | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `FROM eclipse-temurin:17-jre-jammy` | Chọn Linux base image có Java 17 runtime | Tag là mutable, release cần pin digest đã xác minh |
| `WORKDIR /app` | Đặt working directory của process | Không tự bảo đảm user có quyền ghi mọi file ở đây |
| `COPY --chown=10001:10001` | Copy **một JAR đã build** vào image; đổi owner numeric | Không gọi Maven, không giải nén JAR |
| `USER 10001:10001` | Chạy Java không phải root | Thư mục/volume cần đủ permission cho user |
| `EXPOSE 8080` | Ghi nhận cổng TCP bên trong container | **Không** publish host port |
| `ENTRYPOINT` dạng JSON | Chạy JVM trực tiếp bằng exec form | Tốt cho signal forwarding, lifecycle, application args |

`COPY --chown` dùng số UID/GID nên không bắt buộc tạo account tên trong Linux image. Một số ứng dụng yêu cầu user home hoặc account lookup thì nên tạo user/group rõ ràng và kiểm thử; service HTTP tối giản ở đây chỉ cần đọc JAR và phục vụ request.

`USER 10001:10001` không tự làm `/app` writable: nếu ứng dụng phải ghi uploads hoặc cache, cấu hình writable directory/mount riêng. Dockerfile này cũng không chứa secrets; credentials cho database, broker, TLS nên được cấp ở runtime theo chính sách của deployment.

**Tại sao exact COPY?** Dùng `COPY target/*.jar /app/app.jar` rất dễ chọn sai khi target có cả plain/executable/classifier JARs. File đúng của ví dụ đã biết là `target/oci-demo-1.0.0.jar`; nếu đổi Maven version, classifier hoặc finalName thì cập nhật Dockerfile **và** gate theo cùng artifact identity.

### 5.1. Các điều kiện mặc định

- Build context phải là **project root** có `target/oci-demo-1.0.0.jar`.
- Docker chạy chế độ Linux containers; numeric `USER` và Linux base image không áp trực tiếp cho Windows container mode.
- Spring Boot app phải bind interface nhận traffic container, không chỉ `127.0.0.1` trong container.
- Runtime port của ví dụ là 8080. Thay `server.port` của service thì phải điều chỉnh `EXPOSE`, `docker run -p` và probe.
- JAR compile Java 17 cần JRE đủ mới; nếu dependency compile Java 21 thì JRE 17 vẫn có thể lỗi.
- App có JNI/native libraries phải khớp CPU architecture/libc/system libraries của base image.

## 6. Build context và .dockerignore

Lệnh:

~~~bash
docker build -t oci-demo:1.0.0 .
~~~

dùng dấu `.` làm build context. Dockerfile chỉ có thể `COPY` files nằm trong context và **không bị `.dockerignore` loại bỏ**. Một file tồn tại trên host nhưng bị ignore vẫn khiến lệnh COPY báo không thấy.

Do Dockerfile này chỉ cần một executable JAR, tạo `.dockerignore` ở root:

~~~dockerignore
**
!target/
!target/oci-demo-1.0.0.jar
~~~

Ý nghĩa: loại phần lớn files từ build context, sau đó cho phép thư mục `target` và đúng file JAR được gửi tới builder. Dockerfile và `.dockerignore` vẫn được builder sử dụng theo quy tắc đặc biệt ngay cả khi match ignore rule. Khi Maven artifact đổi tên hoặc nằm dưới `service/target`, phải cập nhật allowlist và `COPY` cùng lúc.

Cách này giảm nguy cơ vô tình gửi source, `.git`, test outputs, IDE files hoặc secrets cho remote builder. Không dùng `COPY . /app` nếu runtime chỉ cần JAR, vì có thể đưa cả source, file nội bộ, credentials hoặc output cũ vào final image.

**Không đặt secrets trong Dockerfile `ENV` hoặc `ARG` chỉ để “tiện build”.** Những giá trị đó có thể xuất hiện trong image config/layers/history/provenance. Cấp secrets ở runtime hoặc sử dụng BuildKit secret mounts thích hợp cho nhu cầu build-time, và không copy chúng vào final image.

## 7. Build image sau khi JAR gate PASS

Trên POSIX shell, chuỗi lệnh thủ công:

~~~bash
mvn -B -ntp clean verify
java SmokeJar.java target/oci-demo-1.0.0.jar
sha256sum target/oci-demo-1.0.0.jar
docker build -t oci-demo:1.0.0 .
~~~

Nếu tự động hóa, phải cho pipeline **dừng ngay khi một lệnh fail**; trong shell script POSIX thông thường có thể dùng `set -e` và kiểm tra cụ thể những bước quan trọng, còn CI provider có cơ chế fail-on-nonzero riêng. Với PowerShell 5.1, nên kiểm tra `LASTEXITCODE` sau native commands thay vì giả định nonzero luôn tự dừng.

Inspect local image:

~~~bash
docker image inspect --format '{{.Id}}' oci-demo:1.0.0
docker image inspect --format '{{.Config.User}}' oci-demo:1.0.0
docker image inspect --format '{{json .Config.Entrypoint}}' oci-demo:1.0.0
~~~

`Config.User` dự kiến là `10001:10001` và entrypoint là mảng `java`, `-jar`, `/app/application.jar`. `.Id` là local image identifier, **không phải JAR SHA** và không luôn bằng registry manifest digest.

Docker tag `oci-demo:1.0.0` có thể bị gán lại cho build khác. Nếu CI cần deploy/release immutable, hãy ghi digest sau push hoặc có registry tag immutability policy; đừng dùng tag `latest` làm định danh duy nhất.

## 8. GATE 2A: so bytes JAR trong image với JAR đã xác minh

Docker build thành công **không** tự chứng minh file COPY là artifact vừa được test. Kiểm tra trực tiếp bằng cách trích JAR từ filesystem image.

### 8.1. Trích JAR từ một container chưa chạy

Docker `create` chỉ tạo container instance, không gọi entrypoint. `docker cp` đọc files kể cả từ container đã dừng:

~~~bash
cid=$(docker create oci-demo:1.0.0)
docker cp "$cid:/app/application.jar" ./jar-from-image.jar
docker rm "$cid"

cmp target/oci-demo-1.0.0.jar ./jar-from-image.jar
sha256sum target/oci-demo-1.0.0.jar ./jar-from-image.jar
~~~

`cmp` trả exit code `0` khi **toàn bộ bytes giống nhau**. `sha256sum` cho hai digest bằng nhau dù paths khác nhau. Nếu checksum khác, đừng “sửa” bằng cách chạy lại Maven trong Docker build; phải tìm vì sao image chứa file khác.

### 8.2. Script kiểm tra và cleanup an toàn

Để chạy CI, dùng script POSIX có cleanup kể cả khi `docker cp` hay `cmp` fail:

~~~bash
#!/bin/sh
set -eu

jar=target/oci-demo-1.0.0.jar
image=oci-demo:1.0.0
tmp=$(mktemp -d)
cid=

cleanup() {
  if [ -n "$cid" ]; then
    docker rm -f "$cid" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT HUP INT TERM

cid=$(docker create "$image")
docker cp "$cid:/app/application.jar" "$tmp/from-image.jar"
cmp "$jar" "$tmp/from-image.jar"

printf '%s\n' 'image.jar.bytes=PASS'
~~~

Khi PASS, dòng **do script tự in**:

~~~text
image.jar.bytes=PASS
~~~

Khi mismatch, `cmp` trả nonzero và script fail, chặn publish. `rm -rf "$tmp"` chỉ dùng trên directory mới tạo từ `mktemp -d` trong script; không đổi `tmp` sang đường dẫn tùy ý chưa xác minh.

Trên Windows có thể dùng `docker create`/`docker cp` tương tự, rồi so `Get-FileHash` của `target/oci-demo-1.0.0.jar` và file trích, hoặc dùng một Java 17 `Files.mismatch` utility. Trong PowerShell khi ghép container ID với dấu `:`, dùng biểu thức nối chuỗi riêng để tránh PowerShell hiểu nhầm biến:

~~~powershell
$cid = docker create oci-demo:1.0.0
$source = $cid + ":/app/application.jar"
docker cp $source .\jar-from-image.jar
docker rm $cid
$one = (Get-FileHash .\target\oci-demo-1.0.0.jar -Algorithm SHA256).Hash
$two = (Get-FileHash .\jar-from-image.jar -Algorithm SHA256).Hash
if ($one -ne $two) {
    throw "Image JAR differs from verified JAR"
}
Write-Output "image.jar.bytes=PASS"
~~~

Đoạn PowerShell này minh họa hash comparison; CI cần bổ sung `try/finally` và kiểm tra `LASTEXITCODE` cho `docker create/cp` để không bỏ sót lỗi trung gian. Script POSIX ở trên đã có cleanup đầy đủ.

**Cần nhớ:** image có thể mang nhiều layers và bytes khác JAR; phép so đúng là **host JAR với /app/application.jar trích từ image**, không phải JAR SHA với image ID.

## 9. GATE 2B: khởi chạy container và kiểm tra HTTP

### 9.1. Run và kiểm tra thủ công

~~~bash
docker run -d --name oci-demo-smoke \
  -p 127.0.0.1:18081:8080 \
  oci-demo:1.0.0
~~~

`docker run -d` tạo container và chạy entrypoint Java. Tham số `-p` publish host loopback port `18081` sang port `8080` trong container. **`EXPOSE 8080` chỉ khai báo cổng, không tự publish host port**.

Kiểm tra trạng thái:

~~~bash
docker ps --filter name=oci-demo-smoke
docker logs oci-demo-smoke
curl -fsS http://127.0.0.1:18081/probe
~~~

HTTP body kỳ vọng:

~~~text
oci-jar-ok
~~~

Dòng trên là body của endpoint, không phải Docker startup log. Khi kết thúc:

~~~bash
docker stop oci-demo-smoke
docker rm oci-demo-smoke
~~~

Trong CI, dùng script có timeout và cleanup thay vì chạy nền rồi quên dừng process.

### 9.2. Smoke script CI có retry/timeout

Ví dụ POSIX shell, từ project root sau khi image được build:

~~~bash
#!/bin/sh
set -eu

image=oci-demo:1.0.0
name=oci-demo-smoke-$$
port=18081

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

docker run -d --name "$name" \
  -p "127.0.0.1:$port:8080" "$image" >/dev/null

ready=0
i=0
while [ "$i" -lt 45 ]; do
  running=$(docker inspect \
    --format '{{.State.Running}}' "$name")

  if [ "$running" != "true" ]; then
    docker logs "$name" || true
    echo "Container exited before HTTP probe" >&2
    exit 1
  fi

  if body=$(curl -fsS --max-time 2 \
      "http://127.0.0.1:$port/probe" 2>/dev/null); then
    if [ "$body" = "oci-jar-ok" ]; then
      ready=1
      break
    fi
  fi

  i=$((i + 1))
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  docker logs "$name" || true
  echo "Container HTTP probe failed" >&2
  exit 1
fi

printf '%s\n' 'image.smoke=PASS'
printf '%s\n' 'image.probe=oci-jar-ok'
~~~

Khi PASS, **hai dòng do script chủ động in** là:

~~~text
image.smoke=PASS
image.probe=oci-jar-ok
~~~

Script redirect container ID của `docker run` sang `/dev/null`, giữ startup logs để in khi FAIL và dùng `trap` dọn container. Host port `18081` là ví dụ; khi chạy nhiều jobs đồng thời, cần mỗi job một port hoặc container network riêng để tránh tranh chấp.

Bước này kiểm tra **JRE và networking của image thật**, khác với host JAR gate: host có thể dùng Java21 còn image là Java17; một dependency được compile quá mới sẽ lộ lỗi `UnsupportedClassVersionError` trong image.

### 9.3. Kiểm tra Java trong image

~~~bash
docker run --rm --entrypoint java oci-demo:1.0.0 -version
~~~

Lệnh chạy JRE **bên trong image** để xem runtime version. Java launcher có thể ghi thông tin version lên stderr; không hardcode full vendor/patch stdout vì nó thay đổi theo base image update. Trong Kubernetes còn cần kiểm thử deployment thực tế với volumes, securityContext, probes, config và network policies.

## 10. Nhiều kiểu định danh: source commit, JAR SHA, image digest

Một release record có thể chứa:

~~~text
Git revision          : commit đã build
Executable JAR        : target/oci-demo-1.0.0.jar
JAR SHA-256           : checksum của file đã qua Gate 1
Local image tag       : oci-demo:1.0.0
Local image ID        : giá trị docker image inspect
Target platform       : linux/amd64 hoặc linux/arm64
Registry image digest : digest manifest/index sau push
Gate 1 result         : PASS/FAIL
Gate 2A + 2B result   : PASS/FAIL
~~~

**Không trộn** commit SHA, JAR SHA và image SHA. Commit SHA định danh source revision; JAR SHA định danh artifact bytes; registry digest định danh container manifest/index. Một Git commit có thể tạo nhiều JAR khác nhau nếu timestamp/generated dependencies không deterministic. Một JAR giống bytes cũng có thể được copy vào hai images khác nhau với base JRE/OS/labels khác.

`docker image inspect --format '{{.Id}}'` cho local ID nhưng không bắt buộc bằng registry digest mà Kubernetes sử dụng. Tags có thể được overwrite; với production, prefer triển khai theo **registry digest** của image đã verify, hoặc dùng chính sách tag immutability và audit.

## 11. Base image, digest và nền tảng

### 11.1. FROM tag mutable

Dockerfile ví dụ:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
~~~

Tag này là một tham chiếu dễ đọc, nhưng nội dung image bên dưới có thể thay đổi khi JRE hoặc Ubuntu base nhận cập nhật. Nếu build ở hai thời điểm khác nhau, dù JAR SHA y hệt, image ID/digest có thể khác.

Với yêu cầu release/reproducibility mạnh, hãy **pin base image bằng digest đầy đủ đã xác minh từ trusted registry** và ghi nhận target platform. Không điền một digest rút gọn/bịa chỉ để trông như đã pin; lấy giá trị từ registry hoặc hệ thống quản lý dependencies đáng tin.

Lệnh `docker build --pull` có thể kiểm tra và tải tag cập nhật nhưng **không thay thế pin digest**. Pin digest cũng cần quy trình cập nhật định kỳ để nhận bản vá security.

### 11.2. CPU architecture

Nếu deployment dùng `linux/amd64`:

~~~bash
docker build --platform linux/amd64 \
  -t oci-demo:1.0.0 .
~~~

Một build khác có thể dùng `linux/arm64`. JAR thuần Java bytecode tương đối portable, nhưng base JRE và native/JNI libraries phụ thuộc platform. Trên máy ARM mà chạy image AMD64 có thể cần emulation; không giả định mọi Docker installation đều cung cấp nó.

Nếu publish multi-platform image với Buildx, cần hiểu image index và **digest cho từng platform manifest**. Một tag có thể trỏ tới manifest list chứ không phải một image duy nhất. Với CI, smoke-test platform dự định deploy hoặc dùng runners/emulation phù hợp.

### 11.3. OCI tar archive là một output khác

`docker build` thông thường nạp image vào local store. Khi cần giao một **OCI image layout tarball** thay vì local tag, Buildx có exporter:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  --output type=oci,dest=oci-demo.oci.tar \
  .
~~~

Lệnh này cần Buildx builder hỗ trợ exporter `type=oci`. Nó tạo một file OCI archive, **không mặc nhiên load image vào local Docker daemon** để `docker run`. Phải kiểm chứng image được xuất/push theo workflow phù hợp, không dùng kết quả test trên một local tag khác rồi mặc nhiên gắn cho OCI archive mới.

## 12. Dùng JRE, non-root và exec ENTRYPOINT đúng cách

### 12.1. JRE thay vì Maven/JDK trong final image

Final image chỉ cần runtime để khởi động JAR đã được Maven build trước. Giữ Maven, compiler/JDK, Git repository và local `~/.m2` ở bên ngoài image sẽ giảm kích thước và attack surface. Tuy nhiên base JRE vẫn có hệ điều hành, CA certificates và packages phải được scan, cập nhật theo chính sách.

Không chọn JRE 17 cho JAR chứa class Java21. Host gate có thể PASS trên JDK21, nhưng image sẽ fail khi JVM17 đọc bytecode mới. Bước image smoke phát hiện rủi ro này.

### 12.2. Non-root không làm mọi filesystem writable

`USER 10001:10001` chạy process với numeric UID/GID non-root. `COPY --chown` cho phép JAR thuộc quyền user, nhưng `WORKDIR /app` không tự cấp quyền ghi cho cả thư mục. Khi app cần export files, writable cache hoặc temp files, cấu hình directory/mount và securityContext phù hợp. Không đổi về root chỉ vì thấy `permission denied` mà chưa xem đúng đường dẫn/quyền.

### 12.3. EXPOSE khác publish

`EXPOSE 8080` chỉ là metadata về cổng dự kiến. `docker run -p 127.0.0.1:18081:8080` thực sự tạo host port forwarding. Nếu app bên trong container chỉ bind `127.0.0.1`, external traffic từ Docker networking có thể không vào; trong ví dụ để Spring Boot bind interface mặc định phù hợp.

### 12.4. Exec form và signals

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Với exec form, Java process nhận tín hiệu dừng trực tiếp hơn so với shell form. Docker/Kubernetes thường gửi SIGTERM trước rồi mới SIGKILL khi quá thời hạn; nên kiểm tra graceful shutdown và shutdown hooks của ứng dụng thật. Có thể thêm Spring application arguments sau image name; còn JVM options như `-Xmx` và `-D...` cần đặt đúng vị trí **trước `-jar`** hoặc dùng cơ chế cấu hình JVM phù hợp.

### 12.5. Không dùng healthcheck dựa vào tool không có

Một image JRE tối giản có thể không cài `curl`, `wget` hoặc shell. Nếu Dockerfile có `HEALTHCHECK CMD curl ...` nhưng không có curl, container sẽ unhealthy dù app tốt. Trong Kubernetes, probe có thể được thực hiện từ kubelet vào HTTP endpoint; khi dùng Spring Boot Actuator, cần phân biệt liveness/readiness và policy bảo mật của endpoints.

## 13. Layered image, multi-stage build và những trường hợp khác

### 13.1. Vì sao copy nguyên JAR dễ audit?

Một Dockerfile `COPY` đúng JAR tạo đường kiểm chứng trực tiếp:

~~~text
verified host JAR
      |
    COPY
      |
      v
/app/application.jar inside image
      |
    docker cp + cmp
      |
      v
exact byte equality
~~~

Nhược điểm của cách này là mọi dependency JAR nằm trong một uber JAR; đổi một application class có thể làm layer chứa cả JAR thay đổi, khiến cache push/pull kém hiệu quả.

### 13.2. Spring Boot layered JAR

Spring Boot hỗ trợ layers index và công cụ layer extraction để tách dependencies, snapshot dependencies, Boot loader, application classes thành những Docker layers khác nhau. Từ đó Docker caching có thể giữ các dependency layers ít thay đổi khi source code cập nhật.

Nhưng khi Dockerfile **extract** thay vì copy nguyên JAR, image cuối có thể không còn `/app/application.jar` ở dạng file nguồn như ví dụ. Khi ấy tiêu chí QA phải khác:

1. Verify **JAR input của bước extract** là artifact đã qua gate.
2. Dùng jarmode/loader command đúng phiên bản Spring Boot.
3. Kiểm tra files/layers sau extract và runtime entrypoint thật.
4. Smoke-test image cuối; không chỉ so directory names.
5. Giữ provenance từ JAR checksum đến image digest.

Tài liệu Spring Boot mới có ví dụ `-Djarmode=tools` và `extract --layers`; không giả định mọi archive Boot cũ đều hiểu đúng command ấy. Một layered image có thể tối ưu hơn, nhưng cần quy trình QA rõ ràng thay vì tự động thay Dockerfile đơn giản trong bài học.

### 13.3. Multi-stage Docker build khác workflow này

Một multi-stage Dockerfile có thể dùng stage Maven/JDK build source, stage JRE copy output. Workflow đó hợp lý khi muốn build trong container, nhưng **file được sinh trong builder stage** phải được verify. Nếu một CI job đã test JAR host A rồi Dockerfile tạo JAR B riêng, không được tuyên bố đã đóng gói chính A mà chưa đối chiếu bytes.

Spring Boot `spring-boot:build-image`/Cloud Native Buildpacks cũng có thể tạo OCI-compatible image mà không cần Dockerfile thủ công. Đó là một lựa chọn khác, không phải cách thực hiện đề bài này.

## 14. Quy trình CI fail-fast

Pipeline nên chạy theo thứ tự:

~~~text
1. Checkout đúng Git revision
2. Chọn Maven, Java và dependencies được kiểm soát
3. mvn clean verify
4. Java SmokeJar.java chạy đúng target/oci-demo-1.0.0.jar
5. Lưu SHA-256 của JAR đã PASS
6. docker build với đúng Dockerfile và context
7. docker create/cp rồi cmp JAR host/image
8. docker run + HTTP probe có deadline
9. Scan dependencies/base image và kiểm tra platform
10. Push đúng image đã PASS, lưu registry digest
11. Deploy đúng digest + smoke test môi trường đích
~~~

| Gate | Điều kiện đạt | Nếu thất bại |
| --- | --- | --- |
| Maven package/test | Exit code 0, executable JAR đúng đường dẫn | Dừng Docker build |
| Packaged-JAR smoke | `java -jar` chạy, HTTP200/body đúng | Dừng Docker build |
| JAR integrity | Lưu SHA của chính file đã test | Không chuyển sang builder khác khi chưa verify |
| Docker build | Exact `COPY`, JRE đúng, image tạo thành công | Dừng image test |
| Image/JAR byte check | File trích từ image giống từng byte JAR đã test | Dừng publish |
| Container smoke | Process chạy, HTTP200/body đúng, cleanup | Dừng publish |
| Registry publish | Push chính image đã verify, lưu digest/platform | Không deploy tag chưa xác minh |

Nếu các job chạy ở runners khác nhau, cần upload/download **cùng một file JAR** từ artifact storage, kiểm tra SHA ngay sau tải về rồi mới build image. Không chạy lại Maven trong Docker job chỉ để lấy file khác và bỏ qua gate đầu.

Đừng gắn nhãn `REPRODUCIBLE` chỉ vì hai image tags giống nhau. Byte-for-byte reproducible JAR và reproducible OCI image là hai mục tiêu riêng; base image, layer timestamps, compression, config và arch có thể thay đổi dù app JAR nguyên vẹn.

Một release record hữu ích ghi commit SHA, JAR SHA, artifact path, base image digest, target platform, image registry digest, gate results và links tới build/test logs. Không nhúng passwords/tokens vào log hoặc `LABEL` chỉ để truy vết.

## 15. Chẩn đoán lỗi thường gặp

| Lỗi | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| `COPY failed: file not found` | Chưa build JAR, sai build context, `.dockerignore` exclude file | Xác minh `target/...jar` và context root |
| `no main manifest attribute` | Plain JAR, `repackage` chưa chạy | Inspect manifest, Boot loader và classifier |
| `ClassNotFoundException` | Sai archive hoặc thiếu runtime dependencies | `jar tf`, `BOOT-INF/lib`, startup logs |
| `UnsupportedClassVersionError` | JRE image quá cũ so với bytecode | Java image version, Maven compiler target |
| Docker build PASS, container exit ngay | JAR/config/JRE/runtime lỗi | `docker logs`, process exit code |
| HTTP connection refused | Server chưa ready, sai port, bind loopback bên trong container | `-p`, `server.address`, logs |
| `EXPOSE 8080` mà host vẫn không truy cập | EXPOSE không tự publish port | `docker run -p` hoặc orchestrator network |
| Host JAR hash khác image JAR hash | COPY file khác, JAR được rebuild sau gate | Artifact path, sha256 và `docker cp` |
| `permission denied` khi viết file | UID non-root thiếu quyền volume/temp directory | User, mount ownership, writable path |
| Image chạy trên AMD64, lỗi trên ARM | Base platform/JNI/native libs khác | Buildx `--platform`, target CPU |
| Container unhealthy | Healthcheck gọi curl không có trong image hoặc endpoint sai | Healthcheck implementation/probe |
| Shell ENTRYPOINT không nhận SIGTERM | Shell wrapper không forward signal | Exec-form entrypoint, shutdown logs |
| JAR bytes giống mà image digest khác | Base image/config/layers/compression khác | Inspect base/digest/layers riêng |
| Cùng tag image nhưng deploy sai version | Tag mutable, publish/rebuild sau smoke | Registry digest và CI artifact ID |
| K8s fail dù docker run PASS | Network/secret/probe/securityContext/volumes khác | Deployment manifest, pod events/logs |
| Docker build context chứa secrets | `COPY .` hoặc ignore rules lỏng | Exact COPY, strict .dockerignore, image inspect |
| Remote builder thiếu JAR | Artifact chưa được chuyển sang build context | Tải artifact cùng hash rồi mới build |

**Không mặc định `docker build --no-cache` là cách chữa mọi vấn đề.** Nếu chọn sai JAR, sai JVM version hoặc bind port sai, bỏ cache không giải quyết nguyên nhân. Theo dõi **JAR nào được build, JAR nào được copy, image nào được chạy và image nào được publish**.

## 16. Checklist và câu hỏi tự kiểm tra

### Checklist trước khi publish

- [ ] Đã build executable JAR đúng version/artifact path.
- [ ] `java -jar` và smoke HTTP từ packaged JAR PASS trước Docker build.
- [ ] SHA-256 JAR đã PASS được lưu và kiểm tra sau các bước chuyển job.
- [ ] Dockerfile chỉ COPY đúng JAR, không rebuild âm thầm.
- [ ] Base image JRE và CPU architecture tương thích Java target/native libs.
- [ ] Dùng non-root user, exec-form entrypoint và permissions phù hợp.
- [ ] .dockerignore không gửi .git/secrets/source không cần thiết, vẫn cho phép JAR.
- [ ] Build context là project root đúng như Dockerfile giả định.
- [ ] JAR trong image được trích và so bytes với file đã PASS.
- [ ] Container chạy, HTTP probe PASS, có timeout/log/cleanup.
- [ ] Kiểm tra image JRE, cổng và bind address phù hợp.
- [ ] Lưu Git revision, JAR SHA, image digest và target platform riêng biệt.
- [ ] Đã xem security scan/secret policy và runtime configurations.
- [ ] Publish/deploy **chính image được kiểm thử**, không rebuild hoặc đổi tag âm thầm.

### Câu hỏi A

**Maven tạo JAR thành công nhưng `java -jar` báo `no main manifest attribute`. Có nên cứ COPY JAR vào image?**

Không. Cần sửa/chọn đúng Spring Boot executable JAR và vượt qua JAR gate trước. Dockerfile không biến plain JAR thành executable archive.

### Câu hỏi B

**Hai images có cùng `/app/application.jar` nhưng image digests khác nhau có mâu thuẫn không?**

Không. Image còn có JRE/OS, manifest, config và layers; chúng có thể khác trong khi file JAR bytes y hệt.

### Câu hỏi C

**Vì sao `EXPOSE 8080` chưa đủ để gọi `http://127.0.0.1:18081/probe` từ host?**

EXPOSE chỉ mô tả cổng container. Cần `docker run -p 127.0.0.1:18081:8080` hoặc networking của orchestrator.

### Câu hỏi D

**Host đã smoke-test JAR A. Docker build chạy lại Maven tạo JAR B. Có thể coi image chứa đúng artifact A đã kiểm chứng không?**

Không, trừ khi đã chứng minh B giống bytes A và kiểm tra B theo đúng quy trình. Tốt nhất chuyển nguyên A bằng artifact storage có SHA verification.

### Câu hỏi E

**Đặt `USER 10001:10001` có nghĩa mọi thư mục trong image writable không?**

Không. Numeric non-root user giảm quyền, còn writable directory, `/tmp`, mounts và volumes phải được cấp quyền đúng.

### Câu hỏi F

**Một image tag `oci-demo:1.0.0` có đủ làm khóa deployment immutable không?**

Không. Tag có thể bị gán lại. Dùng registry digest của image đã publish/verify, kèm source SHA, JAR SHA và platform.

## 17. Tài liệu chính thức

- Spring Boot 3.5 — Container Images: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/index.html
- Spring Boot — Dockerfile và Layered JAR: https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Efficient Container Images: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/efficient-images.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Docker — Dockerfile Reference: https://docs.docker.com/reference/dockerfile/
- Docker — Build Context và .dockerignore: https://docs.docker.com/build/concepts/context/
- Docker — Building Best Practices: https://docs.docker.com/build/building/best-practices/
- Docker — Docker Buildx Exporters/OCI Tar: https://docs.docker.com/build/exporters/
- Docker — docker cp: https://docs.docker.com/reference/cli/docker/container/cp/
- Docker — docker image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Eclipse Temurin Docker Official Image: https://hub.docker.com/_/eclipse-temurin
- Open Container Initiative — OCI Image Specification: https://github.com/opencontainers/image-spec
- Java 17 — ProcessBuilder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Java 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html

**Kết luận:** Kiểm chứng một Spring Boot JAR xong mới **đóng gói chính bytes JAR đó** vào image với JRE phù hợp. Sau Docker build, cần xác minh **file JAR trong image** và **container runtime** bằng hai phép thử riêng, sau đó publish image đúng digest đã qua QA. Chỉ có `BUILD SUCCESS`, một tag dễ đọc hoặc file JAR có mặt **chưa** chứng minh image triển khai là bản đã được kiểm chứng.