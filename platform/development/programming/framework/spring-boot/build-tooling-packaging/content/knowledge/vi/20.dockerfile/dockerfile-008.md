# Lựa chọn ENTRYPOINT dạng exec và truyền tùy chọn JVM khi chạy

## 1. Bối cảnh: Dockerfile không chỉ quyết định lệnh khởi động

Một ứng dụng Spring Boot đóng gói thành executable JAR có thể chạy trực tiếp trên máy phát triển:

~~~bash
java -Xms64m -Xmx256m -Ddemo.jvm.tag=local -jar target/runtime-probe-1.0.0.jar --app.mode=local
~~~

Nhưng khi đưa ứng dụng vào container, lệnh này trở thành **hợp đồng khởi động** của image: Docker phải biết tiến trình chính là gì, nó nhận các tham số nào, xử lý `SIGTERM` ra sao, và người vận hành có thể đổi các cấu hình JVM/ứng dụng mà không phải build lại image hay không.

Bài này tập trung vào **lựa chọn `ENTRYPOINT` dạng exec và truyền tùy chọn JVM khi chạy**. Không đánh đồng:

- **Lệnh build:** `RUN` trong Dockerfile thực hiện ở thời điểm build image.
- **Lệnh khởi động:** `ENTRYPOINT` chạy khi container được tạo.
- **Tham số mặc định:** `CMD` bổ sung các argument mặc định cho `ENTRYPOINT` dạng exec, và có thể được thay bằng phần sau tên image trong `docker run`.
- **Tùy chọn JVM:** `-Xmx`, `-Xms`, `-XX:...`, `-D...` là đầu vào của Java launcher/VM, phải xuất hiện **trước `-jar`** nếu truyền trên Java command line.
- **Tham số ứng dụng:** `--server.port=...`, `--spring.profiles.active=...`, `--app.mode=...` là arguments sau file JAR mà Spring Boot xử lý.
- **Biến môi trường:** `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS` được JDK hỗ trợ; `JAVA_OPTS` chỉ là quy ước của một số entrypoint scripts hoặc launcher, **không được Java tự đọc theo mặc định**.

Sau bài học, bạn sẽ biết khi nào chọn JSON-array exec form, lý do shell form dễ gây lỗi signal/argument forwarding, cách đặt `CMD`, cách truyền JVM flags ở runtime mà vẫn giữ exec form, cách kiểm tra bên trong container, cùng một ví dụ Spring Boot 4.1.2/Java 17 chạy được và các lỗi an toàn/vận hành phổ biến.

## 2. Exec form và shell form khác nhau ở đâu?

Docker hỗ trợ hai cú pháp cho `ENTRYPOINT` và `CMD`. Đây là những lệnh khác nhau về **cách Docker tạo process**.

### 2.1. Exec form — lựa chọn mặc định được khuyến nghị

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là **JSON array**. Docker gọi executable `java` với từng argument tách biệt:

~~~text
argv[0] = "java"
argv[1] = "-jar"
argv[2] = "/app/app.jar"
~~~

Ưu điểm:

1. **Không tự gọi `/bin/sh -c`.** Java là tiến trình chính của container khi không thêm init process, nên việc nhận signal từ Docker rõ ràng hơn.
2. Không có shell word splitting, variable expansion, globbing hoặc pipeline không mong muốn.
3. Dễ kiểm toán: từng tham số là một phần tử JSON, không cần suy luận thêm shell quoting.
4. Kết hợp được với `CMD ["--server.port=8080"]` để truyền argument ứng dụng mặc định.
5. Tương thích với model container runtime và orchestrators dùng `command`/`args` để override.
6. Tránh việc shell cha giữ PID 1 rồi không forward `SIGTERM` tới JVM con.

**Cú pháp JSON:** dùng **dấu nháy kép**, không dùng dấu nháy đơn; mỗi token cần là một phần tử riêng. Ví dụ `["java", "-Xmx256m", "-jar", "/app/app.jar"]` là hợp lệ, còn `["java -Xmx256m -jar /app/app.jar"]` cố gọi một executable có tên chứa cả chuỗi, nên không đúng.

### 2.2. Shell form — ngắn nhưng có hệ quả

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

Trên Linux, Docker thường thực thi tương đương:

~~~text
/bin/sh -c "java -jar /app/app.jar"
~~~

Khi shell giữ PID 1, JVM có thể là **process con**. Shell mặc định không tự forward mọi signal tới child process; `docker stop` gửi `SIGTERM` cho tiến trình chính, nên ứng dụng Java có thể không nhận được yêu cầu dừng đúng cách và bị buộc dừng sau grace period.

Thêm chữ `exec` vào shell form:

~~~dockerfile
ENTRYPOINT exec java -jar /app/app.jar
~~~

có thể khiến shell **thay chính nó bằng JVM**, giúp giải quyết một phần vấn đề PID 1. Tuy nhiên, dạng shell của Docker `ENTRYPOINT` vẫn có các ngữ nghĩa không thuận lợi khi kết hợp `CMD` và arguments sau image. **Đừng chọn shell form chỉ vì muốn truyền JVM flags qua môi trường**; có lựa chọn an toàn và đơn giản hơn ở mục 7.

### 2.3. Bảng so sánh

| Khía cạnh | Exec form | Shell form |
| --- | --- | --- |
| Dockerfile | `ENTRYPOINT ["java","-jar","/app/app.jar"]` | `ENTRYPOINT java -jar /app/app.jar` |
| Có shell tự động? | **Không** | **Có** (`/bin/sh -c` trên Linux) |
| PID 1 (nếu không có init) | Trực tiếp là Java | Thường là shell |
| `CMD`/runtime args | Được append vào exec ENTRYPOINT | Dễ bị bỏ qua theo semantics của shell ENTRYPOINT |
| Biến `$VAR` trong lệnh | **Không** tự expand | Shell có thể expand |
| Signal shutdown | Java nhận signal trực tiếp hơn | Shell cha có thể không forward |
| Độ dễ kiểm toán | Từng phần tử JSON rõ ràng | Phụ thuộc shell parsing/quoting |
| Khuyến nghị cho Spring Boot | **Ưu tiên** | Chỉ dùng khi thực sự cần shell và hiểu hậu quả |

**Không nói quá:** exec form **không tự bảo đảm** shutdown graceful nếu ứng dụng không xử lý signal, bị deadlock hoặc grace period quá ngắn. Nó loại bỏ một nguyên nhân phổ biến khiến signal không tới JVM, chứ không thay thế kiểm thử dừng ứng dụng.

## 3. JVM options phải ở trước `-jar`

Cú pháp Java 17 là:

~~~text
java [JVM/launcher options] -jar <executable-jar-file> [application arguments]
~~~

Ví dụ **đúng**:

~~~bash
java -Xms64m -Xmx256m -Ddemo.jvm.tag=from-command -jar app.jar --app.mode=blue
~~~

Phân loại:

| Token | Ai xử lý? | Ý nghĩa |
| --- | --- | --- |
| `-Xms64m` | JVM | Heap khởi tạo gợi ý 64 MiB |
| `-Xmx256m` | JVM | Giới hạn heap tối đa 256 MiB |
| `-Ddemo.jvm.tag=from-command` | JVM | Java system property tên `demo.jvm.tag` |
| `-jar app.jar` | Java launcher | Chọn executable JAR |
| `--app.mode=blue` | Spring Boot / ứng dụng | Runtime configuration của Spring |
| `--server.port=9090` | Spring Boot / ứng dụng | Port server nội bộ |

Cú pháp **không có tác dụng mong muốn**:

~~~bash
java -jar app.jar -Xmx256m
~~~

Ở vị trí sau file JAR, chuỗi `-Xmx256m` được Java launcher chuyển tới `main(String[] args)` dưới dạng **application argument**. Nó không còn được Java launcher diễn giải là giới hạn heap. Framework có thể xử lý hoặc bỏ qua chuỗi đó theo quy tắc của mình; **không** khẳng định JVM đã nhận flag chỉ vì container vẫn khởi động.

Tương tự, với:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["-Xmx256m"]
~~~

`CMD` được append **sau** `/app/app.jar`, nên đây **không phải** cách cấu hình JVM heap. Dùng biến môi trường Java hỗ trợ, đặt flag cố định trước `-jar`, hoặc dùng wrapper script có `exec`.

### Cùng là `-D` nhưng khác `--`

- `-Dspring.profiles.active=prod` (trước `-jar`): Java system property do JVM đưa vào system properties; Spring Boot có thể đọc.
- `--spring.profiles.active=prod` (sau `.jar`): command-line property Spring Boot đọc từ application arguments.
- `SPRING_PROFILES_ACTIVE=prod`: biến môi trường Spring Boot có thể đọc, không phải JVM option.
- `-Ddemo.jvm.tag=...`: kiểm chứng qua `System.getProperty("demo.jvm.tag")`.
- `--app.mode=...`: kiểm chứng qua Spring `Environment#getProperty("app.mode")`.

Đừng nhầm các nguồn cấu hình. Nếu cùng một key được cung cấp ở nhiều nguồn, Spring Boot có thứ tự ưu tiên riêng; không đánh giá tác dụng của một flag khi một nguồn ưu tiên cao hơn đang override.

## 4. `ENTRYPOINT` kết hợp với `CMD` và `docker run`

Dockerfile:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

Khi chạy:

~~~bash
docker run --rm example-app:1.0
~~~

Docker tạo tiến trình tương đương:

~~~text
java -jar /app/app.jar --server.port=8080
~~~

Nếu chạy:

~~~bash
docker run --rm example-app:1.0 --server.port=9090 --app.mode=green
~~~

thì **tất cả `CMD` mặc định** được thay bằng các arguments đứng sau tên image. Tiến trình tương đương:

~~~text
java -jar /app/app.jar --server.port=9090 --app.mode=green
~~~

Đây là lý do `CMD` nên chứa **thông số mặc định có thể override**. Nếu mục tiêu là truyền app args và vẫn giữ Java làm entrypoint thì exec form là thiết kế hợp lý.

### Bẫy thứ tự argument của `docker run`

Cú pháp tổng quát:

~~~text
docker run [Docker options] IMAGE [COMMAND or arguments...]
~~~

Ví dụ:

~~~bash
docker run --rm -p 18080:8080 -e APP_MODE=blue example-app:1.0
~~~

`-p` và `-e` là **Docker options**, nên đặt trước tên image. Nếu đặt chúng **sau** `example-app:1.0`, Docker thường chuyển chúng tới `ENTRYPOINT` dưới dạng app args; chúng không tự biến thành Docker flags.

Tương tự, `--server.port` sau image là một **app argument**; `-Xmx256m` sau image cũng chỉ là một **app argument**. Muốn cung cấp `-Xmx` cho JVM khi runtime, hãy dùng `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` hoặc đổi exec command theo chủ đích.

### Khi nào không cần `CMD`?

Nếu tất cả runtime Spring Boot configuration được truyền qua `application.properties`, environment variables hoặc external config, bạn có thể chỉ khai báo:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Việc bỏ `CMD` không làm ảnh hưởng đến khả năng truyền arguments sau tên image. `CMD` là **defaults**, không phải bắt buộc để có entrypoint.

## 5. Ví dụ Spring Boot 4.1.2 và Java 17 hoàn chỉnh

Để kiểm tra điều gì được JVM nhận và điều gì được Spring Boot nhận, ta tạo HTTP endpoint có output xác định. Ví dụ không dựa vào log JVM, thứ tự startup hay memory usage vốn thay đổi theo máy.

### 5.1. Cấu trúc project

~~~text
runtime-probe/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/
│   ├── main/
│   │   ├── java/dev/example/runtime/
│   │   │   ├── RuntimeProbeApplication.java
│   │   │   └── ProbeText.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/dev/example/runtime/ProbeTextTest.java
└── target/              # được Maven tạo, chứa executable JAR
~~~

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>runtime-probe</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Starter parent cấu hình Maven Plugin `repackage` để tạo Spring Boot executable JAR khi phase `package` chạy. `spring-boot-starter-webmvc` cung cấp Spring MVC và embedded servlet server cho ví dụ HTTP; `spring-boot-starter-test` phục vụ JUnit Jupiter ở test scope. Java 17 là phiên bản tối thiểu phù hợp với Spring Boot 4.1.2.

### 5.3. `src/main/java/dev/example/runtime/ProbeText.java`

~~~java
package dev.example.runtime;

public final class ProbeText {
    private ProbeText() {
    }

    public static String render(String jvmTag, String appMode) {
        return "jvmTag=" + jvmTag + ";appMode=" + appMode;
    }
}
~~~

Class này chỉ dùng Java SE. Việc tách format logic thành một class thuần Java giúp unit test không cần mở web server.

### 5.4. `src/main/java/dev/example/runtime/RuntimeProbeApplication.java`

~~~java
package dev.example.runtime;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class RuntimeProbeApplication {

    private final Environment environment;

    public RuntimeProbeApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(RuntimeProbeApplication.class, args);
    }

    @GetMapping("/probe")
    public String probe() {
        String jvmTag = System.getProperty("demo.jvm.tag", "unset");
        String appMode = environment.getProperty("app.mode", "default");
        return ProbeText.render(jvmTag, appMode);
    }

    @PreDestroy
    public void onShutdown() {
        System.out.println("APP_CONTEXT_CLOSED");
    }
}
~~~

**Hai giá trị do hai nguồn khác nhau cung cấp:**

- `jvmTag` đọc **Java system property**; muốn đổi thông qua Java launcher, đặt `-Ddemo.jvm.tag=...` trước `-jar` hoặc dùng biến môi trường Java hỗ trợ.
- `appMode` đọc **Spring Environment**; `--app.mode=...` nằm sau `.jar` hoặc biến môi trường `APP_MODE` có thể cung cấp giá trị.
- `@PreDestroy` in `APP_CONTEXT_CLOSED` khi bean bị destroy trong quá trình Spring context được đóng. Đây là dấu hiệu hữu ích cho thử nghiệm `docker stop`, **không phải lời bảo đảm** nếu tiến trình bị `SIGKILL`, máy mất điện hoặc shutdown hook không kịp chạy.
- Endpoint `GET /probe` trả về **response body**, không phải stdout của tiến trình Java.

### 5.5. `src/main/resources/application.properties`

~~~properties
spring.application.name=runtime-probe
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.banner-mode=off
~~~

`server.shutdown=graceful` cho phép web server xử lý yêu cầu đang chạy theo chính sách shutdown của Spring Boot; timeout 20 giây là **thời gian của các shutdown phases Spring**, không tự thay thế Docker stop timeout. Cần phối hợp **grace period của container** đủ dài với giới hạn ứng dụng; nhiều pha hoặc request chậm có thể khiến quá trình dừng vượt kỳ vọng.

### 5.6. `src/test/java/dev/example/runtime/ProbeTextTest.java`

~~~java
package dev.example.runtime;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProbeTextTest {
    @Test
    void rendersSeparateJvmAndAppInputs() {
        assertEquals(
                "jvmTag=from-env;appMode=blue",
                ProbeText.render("from-env", "blue")
        );
    }
}
~~~

Test xác nhận format output, **không xác nhận Docker/ENTRYPOINT nhận biến môi trường**. Phần đó cần kiểm tra trên image thật sau build.

### 5.7. Build JAR trước khi tạo image

~~~bash
java -version
mvn -version
mvn clean verify
jar tf target/runtime-probe-1.0.0.jar
~~~

Trong archive nên có `BOOT-INF/classes/dev/example/runtime/RuntimeProbeApplication.class`, `BOOT-INF/classes/dev/example/runtime/ProbeText.class` và các dependency phù hợp ở `BOOT-INF/lib`. Không chọn `*.jar.original` làm file deployment nếu Spring Boot plugin giữ bản backup của ordinary JAR.

Thử trực tiếp ngoài Docker:

~~~bash
java -Ddemo.jvm.tag=local -jar target/runtime-probe-1.0.0.jar --server.port=18080 --app.mode=local
~~~

Ở terminal khác:

~~~bash
curl -fsS http://127.0.0.1:18080/probe
~~~

**HTTP response body chính xác:**

~~~text
jvmTag=local;appMode=local
~~~

Dừng tiến trình bằng `Ctrl+C`. Đây là baseline để biết Java code/app config hoạt động trước khi thêm biến thể Docker.

## 6. Dockerfile mặc định: exec ENTRYPOINT và app CMD

Tệp **`Dockerfile`**:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY --chown=10001:10001 target/runtime-probe-1.0.0.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

**Ý nghĩa:**

1. `FROM eclipse-temurin:17-jre` chọn runtime Java 17. Trong production nên **pin image bằng digest** theo chính sách để tránh việc tag thay đổi theo thời gian.
2. `WORKDIR /app` đặt thư mục làm việc, nhưng không quyết định classpath resource bên trong Boot JAR.
3. `COPY --chown=10001:10001` copy **artifact đã được Maven build** vào image; không copy source tree để chạy.
4. `USER 10001:10001` chạy không phải root (một ví dụ UID/GID dạng số). Port 8080 không phải privileged port. Container thật vẫn cần kiểm tra permission của các thư mục cần ghi.
5. `EXPOSE 8080` mang tính thông tin/metadata cho port ứng dụng; **không tự publish port lên host**.
6. `ENTRYPOINT` dạng exec khiến `java` là tiến trình chính khi không chạy container với init wrapper.
7. `CMD` chứa **tham số Spring Boot mặc định**, được append sau `/app/app.jar` và có thể override khi `docker run`.

Tệp **`.dockerignore`** dành cho ví dụ build artifact có sẵn:

~~~text
.git
.idea
.vscode
src
target/classes
target/test-classes
target/surefire-reports
target/*.jar.original
*.log
~~~

**Chú ý:** không viết quy tắc `target` hoặc `target/*.jar` ở `.dockerignore` vì điều đó có thể loại luôn `target/runtime-probe-1.0.0.jar` khỏi build context, khiến `COPY` thất bại. Trong pipeline thực nên sử dụng multi-stage build hoặc context chỉ chứa artifact đầu ra nếu cần bảo vệ thông tin build.

### Build Docker image

Từ thư mục chứa `Dockerfile` sau khi `mvn clean verify` thành công:

~~~bash
docker build -t runtime-probe:1.0.0 .
~~~

Đừng gọi `docker build` trước khi JAR tồn tại. `COPY` có nguồn `target/runtime-probe-1.0.0.jar`, vì vậy Maven artifact phải được tạo trước hoặc Dockerfile phải có một build stage riêng (không nằm trong ví dụ đơn giản này).

## 7. Truyền JVM flags qua `JDK_JAVA_OPTIONS` — cách đơn giản giữ exec form

**`JDK_JAVA_OPTIONS` là biến môi trường được Java launcher hỗ trợ từ JDK 9**, có trong Java 17. Launcher đọc nó rồi **đặt các options của biến vào trước Java command line**, giúp truyền `-Xms`, `-Xmx` và `-D` mà không cần shell word splitting trong Dockerfile.

Từ terminal host:

~~~bash
docker run --rm --name runtime-probe-env \
  --memory=512m \
  -p 18081:8080 \
  -e JDK_JAVA_OPTIONS='-Xms64m -Xmx256m -Ddemo.jvm.tag=from-env' \
  runtime-probe:1.0.0 \
  --server.port=8080 --app.mode=blue
~~~

Tiến trình Java được tạo bởi exec ENTRYPOINT vẫn là:

~~~text
java -jar /app/app.jar --server.port=8080 --app.mode=blue
~~~

Nhưng **Java launcher** đọc thêm `JDK_JAVA_OPTIONS` và áp dụng các JVM options tương đương:

~~~text
java -Xms64m -Xmx256m -Ddemo.jvm.tag=from-env \
     -jar /app/app.jar --server.port=8080 --app.mode=blue
~~~

Đây là cách giải thích **về ngữ nghĩa launcher**, không có nghĩa Docker đã sửa chuỗi JSON của ENTRYPOINT.

Terminal khác:

~~~bash
curl -fsS http://127.0.0.1:18081/probe
~~~

**HTTP response body chính xác:**

~~~text
jvmTag=from-env;appMode=blue
~~~

**Điều kiện:** port 18081 trên host còn trống, port 8080 trong container được app mở, không có nguồn cấu hình ưu tiên cao hơn thay đổi `app.mode` hoặc `demo.jvm.tag`.

### Các điểm phải nhớ

- `JDK_JAVA_OPTIONS` không phải một **shell variable expansion** trong Dockerfile; nó được **bản thân Java launcher** đọc.
- Java launcher có thể in một dòng nhắc nhở trên **stderr** như `NOTE: Picked up JDK_JAVA_OPTIONS: ...`. Dòng đó không phải lỗi JVM.
- Biến này **không dùng để thay `-jar` hoặc main class**. Java launcher từ chối một số tùy chọn như `-jar`, `-h` trong `JDK_JAVA_OPTIONS`.
- Nếu cần truyền một giá trị có dấu cách trong `-D...`, xem quy tắc quote của Java launcher; đừng mặc định shell và Java launcher sẽ diễn giải giống nhau. Ưu tiên option values đơn giản hoặc một file/config mechanism rõ.
- Đừng đặt secrets vào `JDK_JAVA_OPTIONS`; chúng có thể lộ qua cấu hình container, log, diagnostics hoặc các công cụ quản trị.
- `--memory=512m` là giới hạn **memory container**, không đồng nghĩa `-Xmx256m` chiếm toàn bộ memory. JVM còn dùng metaspace, thread stacks, code cache và native memory. Để tránh OOM, cần tính cả overhead của JVM và ứng dụng.

### Dockerfile có giá trị JVM mặc định

Có thể cho image một JVM baseline (không chứa secrets):

~~~dockerfile
ENV JDK_JAVA_OPTIONS="-XX:MaxRAMPercentage=70.0 -Dfile.encoding=UTF-8"
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu runtime cung cấp `-e JDK_JAVA_OPTIONS=...`, giá trị environment tại runtime có thể **thay thế** default của image. Đừng giả định Docker tự **ghép** các chuỗi options. Nếu muốn bảo toàn hai bộ flag, phải định nghĩa rõ policy và hợp nhất tại bước cấu hình phù hợp.

**`-XX:MaxRAMPercentage=70.0`** là cơ chế dùng tỷ lệ memory cho heap khi không có lựa chọn heap overriding như `-Xmx`; việc sizing thực tế phụ thuộc Java/cgroup và các JVM settings. Không khẳng định 70% container memory là toàn bộ memory Java có thể dùng.

## 8. `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và `JAVA_OPTS`

Ba tên biến dễ bị nhầm, nhưng **không giống nhau**:

| Biến | Ai đọc? | Có dùng với exec ENTRYPOINT? | Lưu ý |
| --- | --- | --- | --- |
| `JDK_JAVA_OPTIONS` | Java launcher `java` | **Có** | Prepend launcher options, từ chối một số launcher controls như `-jar` |
| `JAVA_TOOL_OPTIONS` | Cơ chế khởi tạo JVM/JNI (nếu được hỗ trợ) | **Có** | Phù hợp nhiều VM options/agent flags; không dùng để thay main class hoặc jar target |
| `JAVA_OPTS` | **Không phải biến tiêu chuẩn Java launcher** | **Không tự động** | Chỉ có tác dụng khi wrapper/buildpack/entrypoint **chủ động** đọc nó |
| `APP_MODE` | Spring Boot environment resolver | Có | Là **application config**, không phải JVM flag |
| `SPRING_PROFILES_ACTIVE` | Spring Boot environment resolver | Có | Chọn Spring profile, không phải `-Xmx` |

### 8.1. Dùng `JAVA_TOOL_OPTIONS`

Ví dụ:

~~~bash
docker run --rm --name runtime-probe-tool \
  -p 18082:8080 \
  -e JAVA_TOOL_OPTIONS='-Ddemo.jvm.tag=from-tool -Xmx256m' \
  runtime-probe:1.0.0 --server.port=8080 --app.mode=tool
~~~

Terminal khác:

~~~bash
curl -fsS http://127.0.0.1:18082/probe
~~~

Body:

~~~text
jvmTag=from-tool;appMode=tool
~~~

`JAVA_TOOL_OPTIONS` thường được JVM thông báo đã nhận trên stderr, ví dụ `Picked up JAVA_TOOL_OPTIONS: ...`. Nó có thể tác động đến **mọi JVM process** được khởi tạo trong cùng môi trường, kể cả Java tools chạy trong container. Vì vậy không mặc định rằng nó chỉ tác động tới một Boot app khi một container thực hiện nhiều công cụ Java.

**Phạm vi:** không đặt `-jar app.jar` vào `JAVA_TOOL_OPTIONS` vì việc lựa chọn ứng dụng là nhiệm vụ của Java launcher/ENTRYPOINT, không phải một JVM option thông thường.

### 8.2. `JAVA_OPTS` là quy ước, không phải Java standard

Ví dụ sau **không bảo đảm cấu hình heap** với image chúng ta tạo:

~~~bash
docker run --rm -e JAVA_OPTS='-Xmx256m' runtime-probe:1.0.0
~~~

Với `ENTRYPOINT ["java","-jar","/app/app.jar"]`, Java launcher **không tự đọc** `JAVA_OPTS`. Nếu một image khác dùng entrypoint script hoặc buildpack đọc biến này, kết quả có thể khác; phải xem tài liệu image/launcher đó.

Cũng **không đúng**:

~~~dockerfile
ENTRYPOINT ["java", "$JAVA_OPTS", "-jar", "/app/app.jar"]
~~~

Vì exec form không thực hiện shell expansion, Java nhận nguyên chuỗi literal `$JAVA_OPTS` như một argument. Nếu bạn muốn thay đổi JVM flags ở runtime và không cần logic shell phức tạp, dùng `JDK_JAVA_OPTIONS` là lựa chọn đơn giản, dễ kiểm thử hơn.

## 9. Đặt flag cố định trong exec ENTRYPOINT

Khi chỉ có một bộ JVM flags cố định theo sản phẩm, có thể viết trực tiếp:

~~~dockerfile
ENTRYPOINT [
  "java",
  "-XX:MaxRAMPercentage=70.0",
  "-Dfile.encoding=UTF-8",
  "-jar",
  "/app/app.jar"
]
CMD ["--server.port=8080"]
~~~

**Mỗi JVM flag đứng trước `-jar`**, còn `CMD` đứng sau JAR, đúng cách phân loại. Nhưng chú ý: syntax JSON cho Dockerfile exec form **thông thường phải được viết trên một instruction hợp lệ theo Dockerfile parser**. Để tránh khác biệt cách xử lý xuống dòng, ví dụ portable nhất là một dòng:

~~~dockerfile
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=70.0", "-Dfile.encoding=UTF-8", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

Ưu điểm: dễ kiểm tra và không có env parsing. Hạn chế: thay JVM flags thường phải **build lại image** hoặc override toàn bộ entrypoint; vì thế phù hợp với baseline ít thay đổi.

### Không nên dùng `CMD` cho flags JVM sau `-jar`

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["-Xms64m", "-Xmx256m"]
~~~

Trong tổ hợp này, Docker append hai tham số vào **cuối** lệnh:

~~~text
java -jar /app/app.jar -Xms64m -Xmx256m
~~~

Đó là **application arguments**, không phải Java VM flags. Đây là lỗi có thể khó nhận biết vì Spring Boot đôi khi vẫn khởi động bình thường; chỉ kiểm tra heap thật mới phát hiện cấu hình không được áp dụng.

## 10. Khi thực sự cần entrypoint script: dùng `exec` và `"$@"`

Đôi khi container cần chuẩn bị certificate truststore, kiểm tra quyền file, tạo thư mục tạm hoặc chọn một trong nhiều Java launch modes. Trong trường hợp này, bạn có thể dùng **script như executable của exec-form ENTRYPOINT**:

Tệp **`entrypoint.sh`**:

~~~sh
#!/bin/sh
set -eu

# Thực hiện chuẩn bị nhỏ, có kiểm soát nếu cần.
# Không đưa secrets vào log và không tạo shell command bằng eval.
exec java -XX:MaxRAMPercentage=70.0 -jar /app/app.jar "$@"
~~~

Dockerfile biến thể:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --chown=10001:10001 target/runtime-probe-1.0.0.jar /app/app.jar
COPY --chown=10001:10001 entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--server.port=8080"]
~~~

**Các điểm bảo toàn hành vi:**

- Docker dùng exec form để chạy script. Script bắt đầu bằng `#!/bin/sh`, nên shell sẽ thực thi nội dung.
- Dòng `exec java ...` **thay shell bằng Java**, giảm rủi ro shell giữ PID 1 và không forward `SIGTERM`.
- `"$@"` truyền từng argument từ `CMD` hoặc `docker run IMAGE ...` **nguyên ranh giới token**, không trộn tất cả thành một chuỗi; đây là phần rất quan trọng nếu arguments chứa dấu cách.
- `set -eu` giúp script dừng khi có lỗi command chưa được xử lý hoặc biến chưa được định nghĩa. Nó không thay thế logging/observability đúng cách.
- JVM flag cố định ở **trước `-jar`**, còn app args được đưa vào **sau `/app/app.jar`**.
- File script cần line endings tương thích Linux (`LF`) và executable permission; nếu lưu kiểu CRLF, container có thể báo `/bin/sh^M: not found`.
- Không cần entrypoint script chỉ để đưa `-Xmx`; `JDK_JAVA_OPTIONS` đã đáp ứng trường hợp đó.

### Vì sao không khuyến nghị `eval java $JAVA_OPTS ...`?

Các pattern như:

~~~sh
eval "java $JAVA_OPTS -jar /app/app.jar $*"
~~~

mất ranh giới argument, có thể phân tích lại shell metacharacters và tăng nguy cơ command injection nếu `JAVA_OPTS` chịu ảnh hưởng bởi input không tin cậy. Đây là **ví dụ phản diện**, không được dùng làm startup script. Ngay cả dạng `java $JAVA_OPTS -jar ...` không có `eval` vẫn có unquoted word splitting/globbing và khó xử lý argument có dấu cách.

**Lựa chọn ít rủi ro hơn:** dùng `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` cho JVM flags, truyền app args bằng `"$@"` và sử dụng exec form. Nếu policy đòi một launcher tự nhận `JAVA_OPTS`, hãy thiết kế parser/allowlist rõ ràng thay vì tự ráp một shell command từ input.

## 11. Kiểm chứng `ENTRYPOINT`, argv và JVM settings

### 11.1. Kiểm tra image configuration

~~~bash
docker image inspect runtime-probe:1.0.0 \
  --format 'ENTRYPOINT={{json .Config.Entrypoint}} CMD={{json .Config.Cmd}}'
~~~

Giá trị mong đợi theo Dockerfile mục 6:

~~~text
ENTRYPOINT=["java","-jar","/app/app.jar"] CMD=["--server.port=8080"]
~~~

Đây là cấu hình **trên image**, không phải tuyên bố về mọi command override ở runtime. Khi dùng `docker run --entrypoint`, container có thể có entrypoint khác với image mặc định. Nếu tool in escape spaces/format khác, xác minh các phần tử JSON thực tế chứ không so chuỗi spacing một cách máy móc.

### 11.2. Kiểm tra Java process

Khi container đang chạy:

~~~bash
docker top runtime-probe-env
~~~

Trên Linux có thể xem `/proc/1/cmdline` nếu base image hỗ trợ shell và tiện ích `tr`:

~~~bash
docker exec runtime-probe-env sh -c 'tr "\000" " " < /proc/1/cmdline'
~~~

Kỳ vọng khi không có init wrapper: tiến trình PID 1 là `java` với `-jar /app/app.jar` và application arguments được truyền đúng. **JDK_JAVA_OPTIONS có thể không hiện trong `/proc/1/cmdline`**, bởi đó là environment variable được Java launcher xử lý, không phải argument do Docker ghi vào command line. Kiểm tra biến và JVM behavior riêng, đừng dùng `/proc/1/cmdline` làm bằng chứng duy nhất rằng `-Xmx` được áp dụng.

Trong image chỉ có JRE, không tự giả định lệnh `jcmd` có sẵn; muốn kiểm tra sâu hơn dùng JDK diagnostic image, JVM metrics, Actuator/JMX hoặc công cụ observability được phép trong môi trường đó.

### 11.3. Kiểm tra system property và app property qua endpoint

Với container có:

~~~bash
-e JDK_JAVA_OPTIONS='-Ddemo.jvm.tag=from-env' \
runtime-probe:1.0.0 --app.mode=blue
~~~

thì endpoint của demo trả:

~~~text
jvmTag=from-env;appMode=blue
~~~

Đây là bằng chứng rằng `-Ddemo.jvm.tag` được Java nhận và `--app.mode` được Spring Boot nhận. Nó **không** chứng minh giá trị `-Xmx` thực tế. Muốn kiểm chứng heap limit, đo JVM MaxHeapSize/`Runtime.maxMemory()` hoặc dùng diagnostics trên một JVM tương thích, lưu ý overhead và cách JVM làm tròn giá trị.

## 12. Kiểm tra `docker stop`, PID 1 và graceful shutdown

Docker thường gửi `SIGTERM` cho tiến trình chính khi gọi `docker stop`; sau một khoảng grace period, tiến trình còn sống có thể bị `SIGKILL`. Với JSON-array exec `ENTRYPOINT`, Java thường nhận signal trực tiếp và Spring Boot có cơ hội dừng web server/context.

### Thí nghiệm

Terminal 1:

~~~bash
docker run --rm --name runtime-probe-stop \
  -p 18083:8080 \
  runtime-probe:1.0.0
~~~

Terminal 2:

~~~bash
curl -fsS http://127.0.0.1:18083/probe
docker stop --time 25 runtime-probe-stop
~~~

Sau `docker stop`, xem log:

~~~bash
docker logs runtime-probe-stop
~~~

**Lưu ý về `--rm`:** container có thể bị xóa ngay khi dừng, khiến `docker logs runtime-probe-stop` không còn truy cập được. Để **giữ log sau stop** trong thí nghiệm, chạy lại phiên bản **không có `--rm`**:

~~~bash
docker run --name runtime-probe-stop-qa -p 18083:8080 runtime-probe:1.0.0
~~~

Terminal khác:

~~~bash
docker stop --time 25 runtime-probe-stop-qa
docker logs runtime-probe-stop-qa
docker rm runtime-probe-stop-qa
~~~

Nếu shutdown graceful hoàn tất, log ứng dụng có thể chứa dòng từ `@PreDestroy`:

~~~text
APP_CONTEXT_CLOSED
~~~

Đây là **dấu hiệu ứng dụng đã đóng Spring context**, không phải cam kết cứ gửi SIGTERM là dòng này luôn xuất hiện. Một số phiên bản/cấu hình/điều kiện tải có thể gây timeout; phải xem exit status, shutdown logs và behavior thực tế. Docker stop timeout 25 giây ở đây được chọn lớn hơn một shutdown phase 20 giây để minh họa, không phải công thức đủ cho mọi ứng dụng.

### Có cần `--init` không?

Với image có nhiều child processes có thể cần reaping zombie processes, Docker cho phép:

~~~bash
docker run --init --rm -p 18084:8080 runtime-probe:1.0.0
~~~

`--init` thêm một init process nhỏ làm PID 1 để forward signals và thu dọn child processes. Trong chế độ này, **Java không còn là PID 1**, nhưng vẫn là process ứng dụng được init quản lý. Vì vậy câu “exec form luôn khiến Java là PID 1” chỉ đúng **khi không có init wrapper hoặc process supervisor khác**.

**Khuyến nghị:** với Spring Boot app đơn tiến trình, exec ENTRYPOINT đủ rõ và thường phù hợp. Dùng `--init` nếu cần xử lý child processes; không áp dụng một quy tắc cứng cho mọi image.

## 13. Khi nào dùng JVM flags cố định và khi nào truyền lúc chạy?

| Yêu cầu | Phương án phù hợp | Nhận xét |
| --- | --- | --- |
| Tất cả deployment cần một flag giống nhau | Flag trực tiếp trong exec ENTRYPOINT | Dễ kiểm toán, nhưng đổi image nếu flag thay |
| Mỗi environment có memory limit khác | `JDK_JAVA_OPTIONS` | Giữ exec form, không cần shell |
| Java VM cần agent/diagnostic options và env hỗ trợ | `JAVA_TOOL_OPTIONS` | Kiểm tra phạm vi ảnh hưởng và bảo mật |
| Cần thay Spring profile hoặc port | `--spring.profiles.active`, `--server.port` sau image; hoặc Spring env vars | Đây là application configuration, không phải JVM flags |
| Cần chuẩn bị filesystem trước khi Java chạy | Script có `exec java ... "$@"` | Giữ signal forwarding và argument boundaries |
| Hệ thống hiện có launcher hỗ trợ `JAVA_OPTS` | Theo tài liệu launcher đó | Không suy ra Java tự hiểu `JAVA_OPTS` |
| Muốn tăng heap vì container OOM | Kiểm tra memory limit + native overhead, sau đó điều chỉnh JVM | `-Xmx` không được bằng toàn bộ container memory |
| Muốn đổi VM option mà không rebuild image | Runtime env Java hoặc override entrypoint đầy đủ | Không dùng `CMD` đặt flag sau `-jar` |

### Sizing heap trong container

Một ví dụ có chủ đích:

~~~bash
docker run --rm --memory=512m \
  -e JDK_JAVA_OPTIONS='-Xms64m -Xmx256m' \
  -p 18085:8080 runtime-probe:1.0.0
~~~

JVM có thể dùng thêm memory ngoài heap cho native allocations. Không đặt `-Xmx512m` trong container `--memory=512m` và mặc định còn đủ memory cho metaspace/stacks/GC. Hãy quan sát RSS, heap, memory cgroup, OOM kill events và khối lượng workload thực tế.

Mối quan hệ giữa `-Xmx`, `-XX:MaxRAMPercentage` và memory constraints cũng phụ thuộc tùy chọn JVM khác; không khẳng định một tỷ lệ duy nhất phù hợp mọi service.

## 14. Docker Compose và Kubernetes: đưa cấu hình đúng chỗ

### 14.1. Docker Compose

Đây là file **`compose.yaml`** minh họa cho image ở mục 6:

~~~yaml
services:
  runtime-probe:
    image: runtime-probe:1.0.0
    ports:
      - "18080:8080"
    environment:
      JDK_JAVA_OPTIONS: "-Xms64m -Xmx256m -Ddemo.jvm.tag=compose"
    command:
      - "--server.port=8080"
      - "--app.mode=compose"
    stop_grace_period: 25s
~~~

Với Docker Compose, `command` thường tương ứng việc **override `CMD`**, không phải thay `ENTRYPOINT`. Các giá trị `--server.port`/`--app.mode` được append sau `-jar` vì image đã có exec ENTRYPOINT. Environment đưa JVM options vào Java launcher trước khi main class chạy.

Chạy:

~~~bash
docker compose up
~~~

Khi app ready:

~~~bash
curl -fsS http://127.0.0.1:18080/probe
~~~

Body:

~~~text
jvmTag=compose;appMode=compose
~~~

Dừng bằng `docker compose down`. Với production, thêm restart policy, health/readiness, resources và secrets theo policy vận hành. Không đặt sensitive keys vào Compose YAML nếu file được commit.

### 14.2. Kubernetes

Trong Kubernetes, đối với một container image có exec ENTRYPOINT:

- `command` trên container thường **override image ENTRYPOINT**.
- `args` thường **override image CMD**.
- `env` đặt environment variables của process trước khi Java launcher chạy.

Fragment minh họa bên trong `containers:`:

~~~yaml
- name: runtime-probe
  image: runtime-probe:1.0.0
  env:
    - name: JDK_JAVA_OPTIONS
      value: "-Xms64m -Xmx256m -Ddemo.jvm.tag=k8s"
  args:
    - "--server.port=8080"
    - "--app.mode=k8s"
  ports:
    - containerPort: 8080
~~~

Đây **không phải manifest Deployment đầy đủ**, chỉ minh họa ánh xạ. Vì không khai báo `command`, Kubernetes có thể giữ ENTRYPOINT của image, còn `args` thay CMD mặc định. Để triển khai thật cần Pod template, resource requests/limits, probes, termination grace period, security context và image pull policy theo môi trường.

Khi thay `command` thành `["java","-jar","/app/app.jar"]`, hãy nhớ toàn bộ JVM flags muốn đặt trực tiếp phải nằm **trước `-jar`**, còn `args` app config đứng sau.

## 15. Bảo mật và tính lặp lại của runtime configuration

1. **Không đưa secrets vào JVM args hoặc Docker ENV mặc định** nếu chúng có thể nằm trong image layers, diagnostics, container inspection, logs hoặc process metadata. Sử dụng secret manager/volume injection và ứng dụng đọc secrets từ nguồn được bảo vệ.
2. **Không chạy root** nếu không cần. Kiểm tra quyền đọc JAR, quyền ghi `/tmp`, log directory và port binding khi dùng UID/GID không có user name trong image.
3. **Pin base image digest** khi cần reproducible/reviewable release, thay vì phụ thuộc một tag có thể đổi.
4. **Không trộn build-time và runtime options.** `MAVEN_OPTS`/`GRADLE_OPTS` của máy build không tự cấu hình JVM khi container chạy `java -jar`.
5. **Không dùng `eval` hoặc tự ghép untrusted flags vào shell command.** Điều này có thể gây injection/word splitting và làm thay đổi ý nghĩa argument.
6. **Không dump toàn bộ environment hoặc JVM args ra public HTTP endpoint.** Probe ví dụ chỉ phơi bày một property giả không nhạy cảm để dạy học. Trong production, giới hạn/loại bỏ endpoint debug.
7. **Không cho phép runtime application config thay đổi vô kiểm soát.** Biến `--app.mode` là ví dụ; profile/port/tài nguyên production cần IaC/đánh giá thay đổi.
8. **Tách build artifact với vận hành:** cùng image có thể chạy trong dev, staging và prod bằng env/args phù hợp. Ghi release image digest và deployment config riêng để audit.

## 16. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách kiểm tra và sửa |
| --- | --- | --- |
| `exec: "java -jar /app/app.jar": executable file not found` | Cả lệnh bị đặt làm một phần tử JSON | `ENTRYPOINT ["java","-jar","/app/app.jar"]` |
| Dockerfile exec form không expand `$JAVA_OPTS` | Exec form không gọi shell | Dùng `JDK_JAVA_OPTIONS` hoặc script được thiết kế đúng |
| Heap không đổi dù `CMD ["-Xmx..."]` | Flag nằm **sau `-jar`** | Đưa trước `-jar` hoặc vào `JDK_JAVA_OPTIONS` |
| App không nhận `--app.mode` | Dùng shell ENTRYPOINT hoặc args bị override/sai vị trí | Dùng exec ENTRYPOINT + exec CMD, kiểm tra `docker inspect` |
| `docker stop` kéo dài đến SIGKILL | Shell giữ PID 1, app không nhận SIGTERM, hoặc shutdown chậm | Exec ENTRYPOINT, kiểm tra graceful timeout và logs |
| Java là PID 2 dù exec ENTRYPOINT | Có `--init` hoặc supervisor | Kiểm tra process tree; có thể là cấu hình đúng |
| `JAVA_OPTS=-Xmx256m` không tác dụng | JVM không tự đọc `JAVA_OPTS` | Dùng `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` |
| `NOTE: Picked up JDK_JAVA_OPTIONS` trên stderr | Java launcher thông báo env options | Bình thường; kiểm tra flag và đừng đánh dấu là crash |
| `JDK_JAVA_OPTIONS=-jar ...` làm launcher abort | Biến chứa tùy chọn launcher bị cấm | Chỉ đưa VM/launcher flags được hỗ trợ, giữ `-jar` trong ENTRYPOINT |
| `java -jar` không tìm thấy file | `COPY` sai tên artifact, `.dockerignore` loại JAR | Build Maven trước, inspect image path |
| Container chạy nhưng host không kết nối | Không có `-p`, sai port nội bộ hoặc service chưa ready | `docker run -p HOST:CONTAINER`, check logs/port |
| Port 9090 trong app nhưng Docker map 8080 | `--server.port` override CMD, mapping không đổi | Dùng `-p 18081:9090` phù hợp |
| JVM bị OOM kill dù `-Xmx` không quá limit | Native memory + heap vượt container limit | Kiểm tra cgroup, metaspace, stacks, GC và margins |
| JDK option bị áp dụng cho Maven trong image build | Biến JVM được export quá rộng | Scope env vào runtime process/stage cần thiết |
| Script `entrypoint.sh` báo `not found` dù file có thật | CRLF, shebang sai, không executable | Chuyển LF, chmod +x, kiểm tra `#!/bin/sh` |
| `"$@"` bị bỏ trong script | App args từ CMD/run không được forward | Dùng `exec java ... -jar ... "$@"` |
| Dùng `docker run IMAGE --entrypoint ...` mà không hoạt động | `--entrypoint` là **Docker option**, phải trước IMAGE | `docker run --entrypoint java IMAGE -Xmx... -jar ...` |
| Thử JVM flag trên image không có JDK tools | JRE image không chứa `jcmd` | Dùng JVM observability hoặc JDK diagnostic image |
| Debug endpoint lộ secrets | Trả toàn bộ JVM args/env ra HTTP | Chỉ expose thông tin giả không nhạy cảm; bỏ probe khi production |

## 17. Các phép thử trước khi phát hành

### Gate A — image entrypoint

- [ ] `docker image inspect` xác nhận `Entrypoint` là array, không phải string shell form.
- [ ] Các flags được viết đúng token và JVM options nằm **trước `-jar`** nếu cố định trong ENTRYPOINT.
- [ ] `CMD` chỉ chứa default arguments thuộc ứng dụng hoặc đúng mục đích đã thiết kế.
- [ ] Không có `$JAVA_OPTS` literal trong exec argument array.

### Gate B — Java/Spring config

- [ ] Java 17 runtime hợp lệ, executable JAR chứa Boot loader và runtime dependencies.
- [ ] Startup bằng `docker run -p ...` thành công, endpoint `/probe` trả HTTP 200.
- [ ] `-e JDK_JAVA_OPTIONS='-Ddemo.jvm.tag=from-env'` khiến endpoint phản ánh đúng `jvmTag`.
- [ ] `--app.mode=blue` sau image làm `appMode` thay đổi đúng.
- [ ] Cấu hình `-Xmx` được kiểm tra bằng JVM metrics/diagnostics, không suy đoán từ `docker inspect`.

### Gate C — shutdown và vận hành

- [ ] `docker stop` gửi signal phù hợp và app hoàn tất hoặc ghi rõ vấn đề trong grace period.
- [ ] Spring graceful shutdown được cấu hình nếu service cần chờ request đang xử lý.
- [ ] Container không chạy root nếu không bắt buộc, filesystem permissions phù hợp.
- [ ] Memory limit có headroom ngoài heap; không chứa secrets trong args/log.
- [ ] Logs, health/readiness checks và rollback strategy rõ ràng.

### Gate D — reproducibility và deployment

- [ ] Image tag/digest và app JAR version xác định.
- [ ] Dependency/base image từ nguồn đáng tin.
- [ ] Application config và JVM config được quản lý như deployment inputs, không copy bí mật vào image.
- [ ] Compose/Kubernetes không vô tình đổi ENTRYPOINT hoặc gắn JVM flags sau `-jar`.
- [ ] Không đánh đồng chạy thành công với việc signals/memory được cấu hình đúng.

## 18. Câu hỏi tự kiểm tra kèm đáp án

**1. Vì sao nên ưu tiên `ENTRYPOINT ["java","-jar","/app/app.jar"]`?**

Vì Docker gọi Java trực tiếp, tách arguments rõ, hỗ trợ append `CMD`/runtime args và tránh một shell parent không forward SIGTERM. Đây là lựa chọn tốt cho ứng dụng Spring Boot đơn tiến trình.

**2. Với exec ENTRYPOINT trên, `docker run image -Xmx256m` có đặt JVM heap không?**

Không. Docker append tham số này **sau file JAR**, nên Java launcher chuyển nó thành argument ứng dụng.

**3. Muốn đổi `-Xmx` ở runtime nhưng không đổi Dockerfile, dùng gì?**

Dùng `JDK_JAVA_OPTIONS` hoặc `JAVA_TOOL_OPTIONS` được Java 17 hỗ trợ và đã kiểm thử. Với các image/launcher đặc biệt, xem tài liệu riêng.

**4. `JAVA_OPTS` có giống `JAVA_TOOL_OPTIONS` không?**

Không. `JAVA_OPTS` chỉ là quy ước của entrypoint scripts/buildpacks; `JAVA_TOOL_OPTIONS` có cơ chế JVM hỗ trợ. Với exec ENTRYPOINT gọi Java trực tiếp, `JAVA_OPTS` không tự tác dụng.

**5. `CMD ["--server.port=8080"]` đứng ở đâu khi chạy?**

Được append sau `/app/app.jar` dưới dạng application argument Spring Boot, nếu không bị `docker run IMAGE ...` override.

**6. Vì sao shell form `ENTRYPOINT java -jar app.jar` có thể làm `docker stop` không graceful?**

Shell thường là PID 1 và không chuyển SIGTERM đến process Java con đúng cách. Dùng exec form, hoặc nếu cần script thì thay shell bằng Java bằng `exec`.

**7. Khi dùng `--init`, Java còn là PID 1 không?**

Không nhất thiết. Init process thường giữ PID 1, forward signals và reaps children; Java là process con được init quản lý.

**8. Có nên đặt `-Dsecret.password=...` trong `JDK_JAVA_OPTIONS` không?**

Không khuyến nghị. JVM flags và container env có thể lộ qua nhiều kênh vận hành. Dùng cơ chế secrets an toàn theo môi trường.

**9. Đặt `--server.port=9090` sau image nhưng vẫn map `-p 18081:8080` thì sao?**

Ứng dụng listen port 9090 trong container còn Docker forward tới 8080, gây sai mapping. Cần thay thành `-p 18081:9090`.

**10. Khi `docker stop` diễn ra, output `APP_CONTEXT_CLOSED` có bắt buộc xuất hiện không?**

Không. Nó chỉ xuất hiện khi Spring context được đóng và bean `@PreDestroy` chạy thành công; nếu bị SIGKILL hoặc quá thời gian thì có thể không thấy.

**11. `ENTRYPOINT ["java", "$JDK_JAVA_OPTIONS", "-jar", "/app/app.jar"]` có đúng không?**

Không. Docker không tự expand string argument đó. Để Java launcher tự đọc environment `JDK_JAVA_OPTIONS`; đừng thêm nó như một token JSON literal.

**12. Vì sao không nên cho `-Xmx` đúng bằng memory limit của container?**

Heap không phải toàn bộ footprint của Java process; cần chừa memory cho native allocations, metaspace, threads, code cache và GC structures.

## 19. Tóm tắt và quyết định thiết kế

- **Mặc định dùng exec ENTRYPOINT:** `["java","-jar","/app/app.jar"]`.
- **Mặc định của app:** đặt vào `CMD` hoặc Spring environment/config.
- **JVM flags cố định:** đặt trước `-jar` trong exec ENTRYPOINT.
- **JVM flags thay đổi theo môi trường:** dùng `JDK_JAVA_OPTIONS` (hoặc `JAVA_TOOL_OPTIONS` khi phù hợp), không dùng `CMD` chứa `-Xmx` sau JAR.
- **Có chuẩn bị động trước khi khởi động:** dùng một script ngắn với `exec java ... "$@"`, không dùng `eval`.
- **Kiểm tra tín hiệu dừng:** thử `docker stop` và xem Spring shutdown logs, phối hợp grace period.
- **Kiểm tra vận hành:** đúng port mapping, memory headroom, non-root permissions, secrets và deployment overrides.

**Kết luận:** Với Spring Boot chạy trong Docker, chọn `ENTRYPOINT` **dạng exec** giúp giữ semantics của Java process rõ ràng và nhận tín hiệu dừng đáng tin cậy hơn. `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` giúp truyền JVM options khi chạy mà **không phá exec form**; `CMD` và tham số sau image nên dành cho **application arguments**. Hãy kiểm chứng cả `System.getProperty`, Spring `Environment`, JVM memory và `docker stop` trên image thực tế, không chỉ đọc Dockerfile.

## 20. Tài liệu chính thức

1. [Docker Docs — Dockerfile reference: Shell and exec form, ENTRYPOINT, CMD](https://docs.docker.com/reference/dockerfile/)
2. [Docker Docs — Build check JSONArgsRecommended](https://docs.docker.com/reference/build-checks/json-args-recommended/)
3. [Docker Docs — docker container run: --init, --memory, port mapping, environment](https://docs.docker.com/reference/cli/docker/container/run/)
4. [Docker Docs — docker container stop: SIGTERM and grace period](https://docs.docker.com/reference/cli/docker/container/stop/)
5. [Oracle Java 17 — The java Command and JDK_JAVA_OPTIONS](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
6. [Oracle Java 17 — JVM TI / JAVA_TOOL_OPTIONS](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html)
7. [Spring Boot — Dockerfiles and Executable JARs](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
8. [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
9. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
10. [Spring Boot 4.1.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
