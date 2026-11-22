# Ranh giới giữa package, chạy ứng dụng và tạo container image

## 1. Cùng một dự án Spring Boot, nhưng ba thao tác hoàn toàn khác

Một dự án Spring Boot có thể tạo tệp `.jar` hoặc `.war`, có thể chạy HTTP server trên máy lập trình và cũng có thể được đóng thành container image. Đó là **ba trạng thái sản phẩm khác nhau**, không tự suy ra lẫn nhau:

1. **Package**: tạo **artifact trên đĩa** như `target/app.jar` hoặc `target/app.war`. Với Boot, goal `repackage` có thể làm archive đó chạy được bằng `java -jar`. Dù vậy, **một file JAR/WAR không phải process đang chạy**.
2. **Run**: tạo process Java hoặc khởi động ứng dụng trong servlet container. Ví dụ `mvn spring-boot:run`, `java -jar target/app.jar`. Nếu là web app, process có thể bind HTTP port và trả response.
3. **Build image**: dùng Cloud Native Buildpacks hoặc Dockerfile tạo **OCI/Docker-compatible image**. Image chứa filesystem layers, metadata và cấu hình start process; **một image trong Docker daemon không đồng nghĩa ứng dụng đã chạy**.

Ngoài ba việc trên còn có **chạy container** (`docker run`), **push image lên registry** (`docker push` hoặc plugin publish), **deploy tới Kubernetes/platform** và **kiểm tra health/rollout**. Các bước này cần môi trường và quyền riêng.

```text
Source Java + POM + resources
            |
            | mvn compile/test/package
            v
   Maven artifact .jar/.war
            |
            +---------------------------+
            |                           |
            | java -jar                 | build-image hoặc docker build
            v                           v
    JVM ứng dụng chạy             OCI image được tạo
    HTTP port (nếu web)                  |
                                        | docker run / container runtime
                                        v
                                  Container đang chạy
                                        |
                                  Registry publish và
                                  platform deploy là
                                  các bước tiếp theo
```

**Không đánh đồng:**

- `mvn package` báo `BUILD SUCCESS` **không** chứng minh server đang lắng nghe.
- `spring-boot:run` chạy được **không** chứng minh JAR phát hành có manifest/nested dependencies đúng.
- `spring-boot:build-image` tạo image thành công **không** chứng minh image đã push hoặc deploy.
- `docker run` chạy container **không** đồng nghĩa readiness đã tốt hoặc endpoint trả đúng response.
- `mvn deploy` thông thường **upload Maven artifacts lên Maven repository**, không tương đương `docker push` hay triển khai ứng dụng.

## 2. Bảng đối chiếu thao tác trong Maven và Docker

| Thao tác | Đầu ra trực tiếp | Có ứng dụng chạy lâu dài? | Có OCI image mới? |
| --- | --- | --- | --- |
| `mvn compile` | `target/classes` | Không | Không |
| `mvn test` | Test compilation/results/reports | Không mặc định; tests có thể mở server tạm | Không |
| `mvn package` | `target/*.jar` hoặc `*.war` | Không | Không, trừ khi tự bind image goal |
| `mvn verify` | Artifact cùng các verification goals | Không mặc định | Không, trừ cấu hình bổ sung |
| `mvn spring-boot:run` | Spring Boot process dùng classes/runtime deps | **Có** | Không |
| `java -jar target/app.jar` | JVM process từ packaged archive | **Có** nếu app chạy liên tục | Không |
| `mvn spring-boot:build-image` | OCI image được builder tạo | Không để lại app container chạy | **Có** |
| `docker build -t name:tag .` | Docker image từ Dockerfile/context | Không | **Có** |
| `docker image inspect name:tag` | Metadata của image | Không | Không |
| `docker run -p ... name:tag` | Container instance với process | **Có** nếu app khởi động đúng | Không |
| `docker push registry/...` | Image được publish lên registry | Không | Không build image |
| `mvn deploy` | Maven JAR/WAR/POM tại repository | Không | Không |

Nếu POM **chủ động khai** `spring-boot:build-image-no-fork` tại phase `package`, `mvn package` lúc đó có tạo image. Đây là **quyết định cấu hình của project**, không phải hành vi Maven package mặc định.

### Một command có thể thực hiện nhiều phase

`mvn clean package` chạy clean lifecycle rồi default lifecycle đến `package`; trong quá trình này Maven có thể compile cả main và test sources, chạy Surefire tests rồi mới tạo archive.

`mvn clean verify` còn đi qua các phase sau package, và có thể chạy Failsafe integration tests nếu project bind chúng. Do đó không nên nói “package không chạy tests”: điều đúng là **package không tự start một server phục vụ production sau khi lệnh kết thúc**.

## 3. Vai trò của `packaging=jar` và `packaging=war`

Một POM có:

```xml
<packaging>jar</packaging>
```

thì Maven sẽ dùng lifecycle bindings phù hợp để tạo JAR. Với:

```xml
<packaging>war</packaging>
```

Maven dùng WAR packaging và Maven WAR Plugin, tạo một web archive theo quy ước servlet.

Khác biệt quan trọng:

- **JAR** trong Spring Boot thường là executable JAR với **embedded servlet server** (Tomcat khi dùng `spring-boot-starter-web` theo defaults).
- **WAR** có thể dùng cho **traditional deployment** lên **external servlet container**, hoặc được Spring Boot repackage thành **executable WAR** có khả năng `java -jar` khi setup phù hợp.
- `packaging=war` không có nghĩa đang dùng Dockerized Tomcat.
- `packaging=jar` không có nghĩa đã có một JAR chạy được: Maven Jar Plugin thông thường không tự thêm Spring Boot launcher và dependencies.
- `packaging=pom` thường dành cho parent/aggregator, không trực tiếp đóng ứng dụng web thành JAR/WAR.

Packaging ảnh hưởng **cách tạo artifact**, không tự quyết định runtime process hoặc môi trường deployment.

## 4. `spring-boot:repackage` tạo executable archive, không chạy ứng dụng

Spring Boot Maven Plugin có goal `repackage`. Nó nhận JAR/WAR mà Maven đã tạo và chuyển thành archive có loader/nested dependencies thích hợp để chạy `java -jar`.

Spring Boot 3.5 executable JAR thường có cấu trúc:

```text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/             # application classes/resources
    ├── lib/                 # nested dependency JARs
    └── layers.idx           # metadata layers khi bật
```

Manifest điển hình:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.lesson.boundary.BoundaryApplication
```

Ở đây `Main-Class` trỏ tới **Spring Boot loader**, còn `Start-Class` mới trỏ đến main class do bạn viết. Loader giải quyết classpath với **nested JARs** trong `BOOT-INF/lib`. Không hiểu nhầm `Main-Class` của Boot executable archive phải là class Java có `@SpringBootApplication`.

### Khi nào goal `repackage` được bind vào `package`?

Nếu project dùng `spring-boot-starter-parent` và khai `spring-boot-maven-plugin` trong `build/plugins`, parent đã cấu hình execution `repackage` theo defaults. Vì vậy:

```bash
mvn clean package
```

thường đủ tạo executable JAR/WAR.

Nếu project **không** dùng starter-parent (chỉ import BOM qua `dependencyManagement` chẳng hạn), cần tự khai version và execution thích hợp:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.16</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn plugin**, cần đặt dưới `build/plugins` trong POM hợp lệ. Không thêm execution trùng khi parent đã cung cấp binding.

Về CLI, `spring-boot:repackage` thao tác trên JAR/WAR có sẵn từ phase package. Với project không bind goal, thường cần:

```bash
mvn package spring-boot:repackage
```

Nhưng **trong project starter-parent đã bind goal**, không cần gọi thêm vì dễ chạy repackage hai lần.

## 5. `spring-boot:run` khác `java -jar`

### Chạy từ project

```bash
mvn spring-boot:run
```

Goal `run` dùng output classes và project runtime dependencies để chạy ứng dụng, thuận tiện cho vòng lặp dev. Trong Spring Boot Maven Plugin 3.5.x, application chạy trong **forked process**. Lệnh này thường giữ terminal cho đến khi process bị dừng.

Không cần một JAR đã repackage mới gọi được `spring-boot:run`. Vì chạy từ project classpath nên app có thể chạy tốt ở đây nhưng thất bại khi phân phối JAR do thiếu resource/manifest/packaging config.

### Chạy từ artifact đã package

```bash
java -jar target/lifecycle-boundary-demo-1.0.0.jar
```

Lệnh này thực sự dùng **archive sẽ phát hành**: manifest/launcher, classes, nested libs và resources. Nó là phép smoke test quan trọng trước khi đưa artifact vào image.

Cả hai lệnh đều có thể khởi động HTTP server, nhưng:

| Đặc điểm | `spring-boot:run` | `java -jar` |
| --- | --- | --- |
| Input | Maven project classes/dependencies | Packaged executable JAR/WAR |
| Cần chạy package trước? | Không nhất thiết | **Có**, cần archive hợp lệ |
| JVM process | Plugin launch theo goal run | Java launcher launch executable archive |
| Dùng khi | Dev/debug nhanh | Kiểm tra artifact/release, production entry point |
| Có tạo OCI image? | Không | Không |
| Có bind HTTP port? | Có nếu application là web app và khởi động đúng | Tương tự |

Nếu cả hai cùng dùng port 8080, khởi động đồng thời có thể báo **port already in use**. Dừng process trước khi dùng lệnh khác hoặc đổi `server.port`.

## 6. Dự án Java 17 thực hành: một REST endpoint tối giản

Bài này dùng **Spring Boot 3.5.16** (một bản thuộc nhánh 3.5.x), Maven 3.6.3+ và Java 17+. Nếu tổ chức pin nhánh khác, phải điều chỉnh parent/plugin versions tương thích; không trộn starter versions không cùng nhánh một cách tùy tiện.

**Điều kiện:** có JDK 17+, Maven, Maven Central/mirror cho dependencies. Docker daemon **chưa cần** cho bước package/run local.

### Cấu trúc thư mục

```text
lifecycle-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/dev/lesson/boundary/
    │   ├── BoundaryApplication.java
    │   └── GreetingController.java
    └── test/java/dev/lesson/boundary/
        └── GreetingControllerTest.java
```

### POM đầy đủ — `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>dev.lesson</groupId>
    <artifactId>lifecycle-boundary-demo</artifactId>
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
```

Các điểm then chốt:

1. Parent `3.5.16` quản lý dependencies/plugins và `repackage` execution trong cấu hình chuẩn.
2. `packaging=jar` tạo JAR theo lifecycle; Boot plugin repackage JAR thành executable archive.
3. `java.version=17` chọn release/compiler setup theo parent.
4. `spring-boot-starter-web` cung cấp Spring MVC và embedded Tomcat theo defaults.
5. `spring-boot-starter-test` cung cấp JUnit Jupiter cùng công cụ test với scope `test`.
6. Không khai `build-image` execution: `mvn package` sẽ **không** vô tình tạo image trong ví dụ này.
7. POM không chứa Docker/registry credentials; những thứ đó thuộc môi trường image build/deploy.

### `src/main/java/dev/lesson/boundary/BoundaryApplication.java`

```java
package dev.lesson.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

`@SpringBootApplication` bật auto-configuration và component scan cho package `dev.lesson.boundary`. Khi start, embedded web server được tạo nếu có web stack và cấu hình phù hợp.

### `src/main/java/dev/lesson/boundary/GreetingController.java`

```java
package dev.lesson.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from Maven";
    }
}
```

Spring MVC map `GET /hello`. Body response là chuỗi cố định, không phụ thuộc database, thời gian hoặc locale.

### `src/test/java/dev/lesson/boundary/GreetingControllerTest.java`

```java
package dev.lesson.boundary;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingControllerTest {
    @Test
    void greets() {
        assertEquals("Hello from Maven", new GreetingController().hello());
    }
}
```

Đây là **unit test gọi method trực tiếp**, không phải HTTP test với server thực. Điều đó cho phép xem hoạt động của phase `test` mà không tạo server lâu dài.

### Build lần đầu

Từ project root:

```bash
mvn -version
mvn -B -ntp clean package
```

Nếu dependencies resolve và unit test pass, các outputs quan trọng thường là:

```text
target/lifecycle-boundary-demo-1.0.0.jar
target/lifecycle-boundary-demo-1.0.0.jar.original
target/surefire-reports/
```

`.jar.original` là bản chưa repackage mà Boot plugin thường để lại khi thay primary JAR. **Chạy `.jar` chính**, không chạy `.jar.original`.

Ngay sau package: **artifact đã tạo; server chưa tự start; OCI image chưa được tạo**.

### Kiểm tra executable JAR

```bash
jar tf target/lifecycle-boundary-demo-1.0.0.jar
```

Tìm các entries/prefix:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/dev/lesson/boundary/BoundaryApplication.class
BOOT-INF/classes/dev/lesson/boundary/GreetingController.class
BOOT-INF/lib/
org/springframework/boot/loader/
```

Với Bash và có `unzip`:

```bash
unzip -p target/lifecycle-boundary-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Tìm:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.lesson.boundary.BoundaryApplication
```

Đây chỉ là các thuộc tính cần đối chiếu; manifest thật có thêm metadata và có thể fold dòng dài.

### Kiểm tra HTTP bằng `spring-boot:run`

Terminal A:

```bash
mvn spring-boot:run
```

Sau khi log báo ứng dụng khởi động thành công, terminal B:

```bash
curl -fsS http://localhost:8080/hello
```

**Nội dung HTTP body chính xác:**

```text
Hello from Maven
```

`curl` có thể không tự in newline cuối, nên khối trên biểu diễn body chứ không phải mọi byte stdout/HTTP headers. Dùng `curl -i` nếu muốn thấy status/headers.

Dùng Ctrl+C dừng ứng dụng ở terminal A trước khi thử lệnh khác.

### Kiểm tra HTTP bằng packaged JAR

Terminal A:

```bash
java -jar target/lifecycle-boundary-demo-1.0.0.jar
```

Terminal B:

```bash
curl -fsS http://localhost:8080/hello
```

Body vẫn:

```text
Hello from Maven
```

Đây là smoke test **package -> chạy artifact -> HTTP response**. Nó có giá trị cao hơn chỉ xem `BUILD SUCCESS`, nhưng vẫn chưa chứng minh một OCI image chạy được.

### Đổi port khi cần

```bash
java -jar target/lifecycle-boundary-demo-1.0.0.jar --server.port=8081
```

Sau đó gọi:

```bash
curl -fsS http://localhost:8081/hello
```

Phải dừng instance cũ hoặc dùng port khác nếu có xung đột. Đổi port runtime **không tạo JAR mới**.

## 7. Tạo OCI image bằng Cloud Native Buildpacks

Spring Boot Maven Plugin cung cấp `spring-boot:build-image`, tích hợp **Cloud Native Buildpacks (CNB)**. Buildpacks dùng builder image và run image để tạo OCI-compatible container image từ executable JAR/WAR, thay vì cần Dockerfile tự viết.

### Điều kiện

- Docker daemon truy cập được được qua context/socket/endpoint tương thích và có đủ quyền.
- Network/registry access để tải builder/run images khi chúng chưa có trong cache.
- Builder hỗ trợ Java release/architecture cần thiết.
- Có đủ RAM/disk cho buildpacks.
- Maven có thể resolve project/plugin dependencies.
- Ứng dụng đã cấu hình đúng entry point; build-image có thể chuẩn bị executable archive khi cần.

Kiểm tra môi trường Docker (nếu CLI có sẵn):

```bash
docker version
docker info
```

**Docker CLI không nhất thiết là điều kiện nội tại của plugin** nếu nó kết nối trực tiếp Docker daemon bằng cấu hình hợp lệ, nhưng CLI rất hữu ích để inspect/run image sau build.

### Lệnh image build

Từ project root:

```bash
mvn -B -ntp spring-boot:build-image -Dspring-boot.build-image.imageName=demo/lifecycle-boundary-demo:1.0.0
```

Trong cấu hình mặc định:

1. Goal `build-image` **forks Maven package lifecycle** để đảm bảo packaged archive có sẵn.
2. Plugin sử dụng Cloud Native Buildpacks để tạo image từ executable Spring Boot archive.
3. Buildpacks tạo layers, Java runtime/launch metadata theo builder được dùng.
4. Image được tạo trong image store của Docker daemon đã kết nối, với tag `demo/lifecycle-boundary-demo:1.0.0`.
5. `publish=false` mặc định: **không tự push lên registry**.
6. Không có application container chạy phục vụ requests sau khi lệnh image build kết thúc (dù builder có thể tạo containers tạm trong lúc build).

Lưu ý: nếu job đã chạy `mvn clean verify` trước, `build-image` vẫn có thể chạy lại package phases do cơ chế fork; không nên kỳ vọng nó chỉ copy JAR mà hoàn toàn bỏ Maven lifecycle.

**Tên `demo/...` chỉ phục vụ image local**. Đừng tự push sang namespace/registry không thuộc quyền sử dụng của mình.

### Kiểm tra image chưa chạy

```bash
docker image inspect demo/lifecycle-boundary-demo:1.0.0
```

Lệnh `inspect` chỉ đọc image metadata. Một image tồn tại trong Docker daemon **không có nghĩa** image đã được publish hoặc ứng dụng đang lắng nghe cổng 8080.

### Chạy container thật

Khi host port 8080 trống:

```bash
docker run --rm -p 8080:8080 demo/lifecycle-boundary-demo:1.0.0
```

Ở terminal khác:

```bash
curl -fsS http://localhost:8080/hello
```

HTTP body mong đợi:

```text
Hello from Maven
```

**`-p 8080:8080`** map host port ở bên trái sang container port ở bên phải. `--rm` xóa container sau khi dừng; không xóa image. Nếu host port 8080 bận:

```bash
docker run --rm -p 18080:8080 demo/lifecycle-boundary-demo:1.0.0
```

rồi gọi `http://localhost:18080/hello`. Chỉ đổi host port, không đổi `server.port` bên trong app.

### Vì sao buildpacks hữu ích?

- Có thể chọn runtime Java phù hợp mục tiêu build theo khả năng và metadata của builder.
- Có thể tách cached layers dựa trên dependencies/app classes và Spring Boot layers index.
- Tạo launch command/entrypoint phù hợp ứng dụng.
- Mặc định các image CNB thông dụng dùng non-root user theo policy.
- Hỗ trợ Docker-compatible images mà không cần viết Dockerfile.
- Có tùy chọn builder/run image, image name, network, env, platform, tags và publishing.

Nhưng **đừng coi default builder `latest` là reproducible tuyệt đối**. Với CI production cần pin builder/run image version hoặc digest theo khả năng, cập nhật base images có kiểm soát và kiểm tra OS/CPU arch/JRE phù hợp.

## 8. `build-image` và `build-image-no-fork` không được dùng thay nhau tùy tiện

| Goal | Mục đích chính | Lifecycle |
| --- | --- | --- |
| `spring-boot:build-image` | Gọi trực tiếp CLI để tạo OCI image | **Fork package** để chắc chắn archive đã được tạo |
| `spring-boot:build-image-no-fork` | Bind execution vào `package` của POM | **Không fork thêm** package lifecycle |

Ví dụ **chỉ khi chủ ý muốn `mvn package` cũng tạo image**, có thể cấu hình:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>image-when-packaging</id>
            <phase>package</phase>
            <goals>
                <goal>build-image-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **fragment minh họa**, không thêm vào POM demo ở mục 6. Nếu dùng starter-parent, `repackage` vẫn có execution riêng. Việc bind image vào package khiến các lần package ở laptop/CI **cần Docker daemon, builder image và disk**, có thể khiến tác vụ Java đơn giản bất ngờ fail. Với đa số dự án, nên **tách bước package và image build** trong CI.

Goal `build-image-no-fork` không được chọn chỉ để “nhanh hơn” khi gọi riêng từ CLI mà chưa có executable archive; nó được thiết kế cho tình huống package lifecycle đã đang chạy.

## 9. Tạo image bằng Dockerfile thay vì buildpacks

Một workflow khác là dùng `mvn package` tạo JAR, sau đó `docker build` copy JAR vào runtime image.

Tạo file `Dockerfile` ở project root:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY target/lifecycle-boundary-demo-1.0.0.jar /app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ý nghĩa:

- `FROM` chọn Java 17 runtime base image (tag minh họa, chưa pin digest).
- `COPY` chuyển **file JAR đã tồn tại** vào filesystem layer của image.
- `EXPOSE 8080` chỉ ghi metadata gợi ý cổng ứng dụng; **không tự publish port trên host**.
- `ENTRYPOINT` định nghĩa command sẽ chạy khi **container được khởi động**, không chạy trong lúc `docker build`.

Chạy đúng thứ tự:

```bash
mvn -B -ntp clean package
docker build -t demo/lifecycle-boundary-demo:dockerfile .
```

Lệnh `docker build` **không tự chạy Maven** với Dockerfile một stage này; nếu `target/...jar` chưa tồn tại hoặc nằm ngoài build context, `COPY` có thể fail. Các multi-stage Dockerfiles có Maven/JDK build stage là thiết kế khác, không dùng trong ví dụ này.

Chạy:

```bash
docker run --rm -p 8080:8080 demo/lifecycle-boundary-demo:dockerfile
```

Gọi `curl -fsS http://localhost:8080/hello` từ terminal khác; body mong đợi là `Hello from Maven`.

**So sánh với buildpacks:** Dockerfile đơn giản copy toàn bộ JAR thành một layer, còn Spring Boot buildpacks thường tận dụng metadata layers để cache dependencies hiệu quả hơn. Dockerfile cũng yêu cầu team tự quản lý JRE version, runtime user, OS packages, image size và security policies. Cả hai con đường đều tạo **image**, không có con đường nào tự động đồng nghĩa image đã được **run/deployed**.

## 10. WAR truyền thống: đóng gói artifact cho external servlet container

Trong nhóm WAR và Spring Boot, phải phân biệt:

- **Executable JAR** dùng embedded Tomcat khi `java -jar`.
- **Traditional WAR** được external servlet container như Tomcat deploy và quản lý.
- **Executable WAR** do Spring Boot repackage, có thể hỗ trợ cả `java -jar` và traditional deployment khi đúng cấu hình.

Đổi `<packaging>war</packaging>` **không phải** yêu cầu tạo Docker image. WAR chỉ là artifact type.

### POM WAR cần những gì?

Từ POM ví dụ ở mục 6, thay:

```xml
<packaging>jar</packaging>
```

bằng:

```xml
<packaging>war</packaging>
```

và thêm dependency sau vào `<dependencies>`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Starter-web theo mặc định kéo Tomcat; khai starter-tomcat trực tiếp với `provided` cho phép dự án WAR dùng embedded container như một dependency **được môi trường cung cấp** khi deploy external Tomcat.

### Main class WAR cần `SpringBootServletInitializer`

Thay nội dung `BoundaryApplication.java` bằng:

```java
package dev.lesson.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class BoundaryApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(BoundaryApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

`configure(...)` cho phép **external servlet container** khởi tạo Boot app context. `main(...)` vẫn hỗ trợ chạy executable WAR qua Java launcher.

Giữ nguyên `GreetingController.java` và unit test vì package/component scanning không đổi.

### Đóng gói WAR

```bash
mvn -B -ntp clean package
```

Artifact dự kiến:

```text
target/lifecycle-boundary-demo-1.0.0.war
```

Xem nội dung:

```bash
jar tf target/lifecycle-boundary-demo-1.0.0.war
```

Các paths đáng tìm:

```text
WEB-INF/classes/dev/lesson/boundary/BoundaryApplication.class
WEB-INF/classes/dev/lesson/boundary/GreetingController.class
WEB-INF/lib/
WEB-INF/lib-provided/
```

Với Spring Boot **executable WAR**, thư viện Tomcat có scope provided có thể được đặt trong `WEB-INF/lib-provided` để Boot launcher dùng khi `java -jar`. External servlet container không coi nó là `WEB-INF/lib` chuẩn của webapp. Điều này giúp tránh xung đột embedded/container dependencies.

### Cách chạy WAR

**Executable WAR đã repackage:**

```bash
java -jar target/lifecycle-boundary-demo-1.0.0.war
```

**Traditional WAR deployment:** dùng tooling/webapps directory của external Tomcat tương thích và truy cập đúng context path. Ví dụ khi deploy tên `app.war`, URL thường là `http://host:8080/app/hello`; context path phụ thuộc server config.

Spring Boot 3.5.x dùng **Jakarta Servlet** ecosystem. Tomcat 10.1 là một lựa chọn tương thích theo tài liệu, nhưng **không mặc định WAR Boot 3.5 có thể deploy trên Tomcat 9** vốn dùng namespace `javax.servlet` cũ. Với Spring WebFlux mặc định Reactor Netty, **traditional WAR deployment không được hỗ trợ** như mô hình Spring MVC servlet.

**Quan trọng:** nếu file chỉ là traditional WAR do WAR Plugin tạo mà **không có Boot repackage/launcher**, `java -jar app.war` không mặc định hoạt động. Đừng tuyên bố mọi WAR “chạy được bằng java -jar”.

## 11. Image từ executable WAR khác image chứa external Tomcat

Nếu chạy `spring-boot:build-image` trên **executable Spring Boot WAR** thì buildpacks có thể tạo OCI image chạy Boot launcher/embedded runtime từ archive.

Một con đường hoàn toàn khác là **image chứa external Tomcat** rồi copy traditional WAR vào `webapps`. Ví dụ minh họa kiến trúc (cần kiểm tra tag thực tế, server/JDK compatibility):

```dockerfile
FROM tomcat:10.1-jdk17-temurin
COPY target/lifecycle-boundary-demo-1.0.0.war /usr/local/tomcat/webapps/app.war
```

Trong phương án này, container process chính là **Tomcat ngoài**, URL theo context path `/app`, và ứng dụng phải có `SpringBootServletInitializer`. Đây **không đồng nghĩa** với Cloud Native Buildpacks image của một executable WAR.

Hãy xác định **ai sở hữu servlet container** trước khi chọn chiến lược. Không trộn lẫn embedded Tomcat và external Tomcat vô tình thành hai runtime cùng quản lý web app.

## 12. `spring-boot:start` và `stop` cho integration tests

Spring Boot Maven Plugin còn các goals:

- `spring-boot:run`: chạy app để developer tương tác, thường blocking.
- `spring-boot:start`: khởi động app để Maven có thể tiếp tục các goals tiếp theo, thường trong integration test workflow.
- `spring-boot:stop`: dừng app đã được `start` khởi động theo cơ chế tương thích.
- `spring-boot:test-run`: dùng test runtime classpath cho một variant app khi cần.

Sơ đồ **thiết kế** integration test:

```text
pre-integration-test: spring-boot:start
integration-test:     failsafe:integration-test
post-integration-test:spring-boot:stop
verify:               failsafe:verify
```

Đây là **sơ đồ**, chưa phải cấu hình POM runnable độc lập. Muốn áp dụng cần bind executions ở đúng phases, thiết kế readiness checks và bảo đảm teardown ngay khi tests thất bại. Vì Failsafe dùng `verify` để đánh giá kết quả sau cleanup, **`mvn integration-test` một mình chưa phải quality gate hoàn chỉnh**.

Khởi động app cho test vẫn không tương đương image build hoặc production deployment.

## 13. Docker image, registry và platform deployment là ba trạng thái riêng

Một pipeline có thể gồm:

```text
Source commit
   |
mvn clean verify        -> tests + artifact
   |
build image             -> local OCI image
   |
scan/smoke-test image   -> kiểm tra runtime container
   |
push image              -> registry lưu image/tag/digest
   |
deploy release          -> platform tạo/đổi workload
   |
health/readiness        -> service đã hoạt động thật
```

Chạy `mvn verify` đã bao gồm `package`, nên pipeline không nhất thiết chạy thêm `mvn package` lần hai. Với `spring-boot:build-image` gọi trực tiếp, nó có thể lại fork package lifecycle; tính đến điều đó khi tối ưu CI.

### Push image cần registry thật và quyền

Ví dụ cú pháp, với domain **placeholder**:

```bash
docker tag demo/lifecycle-boundary-demo:1.0.0 registry.example.com/team/lifecycle-boundary-demo:1.0.0
docker push registry.example.com/team/lifecycle-boundary-demo:1.0.0
```

`registry.example.com` không phải registry để chạy nguyên xi. Cần URL thật, quyền push và auth từ secret store. Đừng commit token trong POM hoặc log command arguments có password.

Spring Boot plugin có option publish nhưng **mặc định false**. Nếu bật publish, cần image name/credentials đúng và kiểm tra registry metadata sau đó.

### Push chưa phải deploy

Image đã có trên registry vẫn **chưa** có workload mới chạy trên Kubernetes, ECS hoặc cloud runtime khác. Deploy cần manifests/Helm/platform configuration và quyền truy cập, thường với image digest, service, resource requests/limits, secrets, probes và rollout logic.

### `mvn deploy` không phải `docker push`

Maven Deploy Plugin thường upload `.jar`/`.war`/POM tới Maven repository dựa trên `distributionManagement` và credentials của Maven settings. Docker push đưa **OCI image** lên **container registry**. Cả hai có thể cùng cần trong release nhưng không thay thế nhau.

## 14. Layers và image caching

Spring Boot executable archive có thể chứa `BOOT-INF/layers.idx`, phân chia nội dung thành các logical layers như:

- `dependencies`
- `spring-boot-loader`
- `snapshot-dependencies`
- `application`

Buildpacks có thể tận dụng thông tin này để tránh phải rebuild/copy lại toàn bộ dependencies mỗi khi application source đổi. Trong khi đó, Dockerfile mẫu chỉ `COPY` nguyên JAR vào image layer; nếu JAR thay đổi thì layer đó đổi.

**File `layers.idx` trong JAR không phải dấu hiệu image đã tồn tại.** Nó chỉ là metadata packaging hỗ trợ image workflows.

Một plugin fragment điều khiển metadata:

```xml
<configuration>
    <layers>
        <enabled>true</enabled>
    </layers>
</configuration>
```

Đặt dưới Spring Boot Maven Plugin nếu cần, không phải một POM độc lập. Giá trị này không start server, không tự tạo image và không push registry. Với CI nghiêm ngặt, pin builder/run image versions/digests và test layers cache theo môi trường thực tế.

## 15. CI: kiểm soát đầu vào giữa Maven và Docker

Khi dùng Dockerfile:

```dockerfile
COPY target/lifecycle-boundary-demo-1.0.0.jar /app/app.jar
```

Docker chỉ thấy **build context** đã chỉ định (ví dụ `.`), sau khi lọc `.dockerignore`. Vì vậy `COPY` sẽ fail nếu:

- Maven chưa tạo JAR.
- CI chạy `docker build` ở directory khác project root.
- Artifact filename khác do `artifactId`, `version`, `finalName` hoặc classifier.
- `.dockerignore` vô tình loại `target`/JAR.
- Maven build ở worker khác nhưng CI không truyền artifact sang image job.
- Multi-module build tạo JAR dưới `module-name/target`, còn Dockerfile tìm root `target`.

Không giả định source folder và Docker context là một khái niệm. Với multi-stage Dockerfile, Maven compile có thể diễn ra trong image build stage, nhưng đó là **workflow khác** so với Dockerfile chỉ copy JAR sẵn có.

Đồng thời, không copy `.git`, local Maven repository, test reports hoặc secrets vào runtime image khi không cần.

## 16. Bảo mật, reproducibility và Java runtime

### Java bytecode không tự quyết định runtime Java trong image

`<java.version>17</java.version>` trong parent POM giúp compiler target Java 17; nó **không bảo đảm** một Dockerfile bất kỳ hoặc builder bất kỳ sẽ chứa đúng runtime 17. Với Dockerfile minh họa, `eclipse-temurin:17-jre` rõ runtime dự kiến. Với buildpacks, phải xem JRE do builder chọn và platform compatibility.

Nếu code được compile cho Java 21 nhưng runtime image chỉ có Java 17, có thể gặp `UnsupportedClassVersionError`. Hãy test container runtime cuối, không chỉ `mvn -version` trên laptop.

### Không đưa secrets vào image layers

Không để database password, registry token hoặc `application-prod.properties` có mật khẩu trong source/JAR, Dockerfile `ENV` hay build arguments. Secrets trong layer có thể vẫn truy xuất được ngay cả khi một bước Dockerfile sau đó xóa file. Truyền secrets lúc chạy/deploy bằng cơ chế phù hợp.

### Giảm quyền runtime

Cloud Native Buildpacks thường ưu tiên image chạy non-root theo policy. Dockerfile tùy ý **không tự đảm bảo** non-root. Với production, chọn non-root user, sửa file permissions, giới hạn filesystem write access/capabilities, đặt resource limits và health probes phù hợp.

### Pin và rà soát dependency/base images

- Pin Spring Boot version và kiểm tra compatibility JDK/Maven.
- Dùng Maven Wrapper nếu team cần cùng Maven distribution.
- Pin container base image/builder digest khi cần reproducibility mạnh.
- Scan Maven dependencies, JRE/OS packages và tạo/giữ SBOM.
- Giữ image digest khi deploy, không chỉ mutable tag.
- Không dùng relocation, shading hoặc image packaging để che giấu CVE.
- Kiểm tra artifacts đã được tạo từ source/commit cần phát hành, không dùng cache cũ làm nhầm phiên bản.

Maven cache, buildpacks cache và Docker layers cache là **ba cơ chế khác nhau**, cần theo dõi riêng.

## 17. Quy trình kiểm tra từng ranh giới trong thực tế

### Bước 1 — xác minh POM và plugin bindings

```bash
mvn help:effective-pom
mvn help:active-profiles
```

Xác định packaging, plugin `spring-boot-maven-plugin` và execution `repackage`. Đừng chỉ xem một BOM import rồi suy ra executable archive đã được cấu hình.

### Bước 2 — build và test

```bash
mvn -B -ntp clean verify
```

Kiểm tra JUnit test report và artifact `target/lifecycle-boundary-demo-1.0.0.jar`. `verify` đã đi qua package.

### Bước 3 — inspect artifact và chạy local

```bash
jar tf target/lifecycle-boundary-demo-1.0.0.jar
java -jar target/lifecycle-boundary-demo-1.0.0.jar
```

Từ terminal thứ hai:

```bash
curl -fsS http://localhost:8080/hello
```

Body dự kiến `Hello from Maven`. Dừng process trước bước container để không tranh host port.

### Bước 4 — build image và inspect

```bash
mvn -B -ntp spring-boot:build-image -Dspring-boot.build-image.imageName=demo/lifecycle-boundary-demo:1.0.0
docker image inspect demo/lifecycle-boundary-demo:1.0.0
```

Nếu lỗi Docker daemon, giải quyết engine/context/permissions thay vì sửa Spring controller.

### Bước 5 — chạy container và smoke test

```bash
docker run --rm -p 8080:8080 demo/lifecycle-boundary-demo:1.0.0
```

Terminal thứ hai:

```bash
curl -fsS http://localhost:8080/hello
```

Body dự kiến `Hello from Maven`.

### Bước 6 — publish/deploy khi có workflow và quyền riêng

Kiểm tra registry, image tag/digest, vulnerability scanning, environment manifests, config/secrets và readiness. Không tự push/deploy khi chỉ được giao làm bài học package/run/image local.

**Kết quả cần báo cáo theo lớp:** artifact built, tests passed, app smoke-tested, image built, container smoke-tested, image published, deployed. Không gộp tất cả thành một dòng `BUILD SUCCESS`.

## 18. Bảng chẩn đoán lỗi theo đúng ranh giới

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `mvn package` success, `curl localhost:8080` fail | Chưa chạy ứng dụng | Chạy `spring-boot:run` hoặc `java -jar` |
| `java -jar` báo `no main manifest attribute` | Thiếu/không bind `repackage` hoặc nhầm original JAR | Xem manifest, starter-parent, effective POM |
| `spring-boot:run` chạy tốt nhưng JAR lỗi | Classpath phát triển khác packaged artifact | Kiểm tra `BOOT-INF/classes`/`BOOT-INF/lib`, manifest |
| `java -jar` báo class not found | Thiếu dependency, wrong start class | Inspect archive/nested JAR layout |
| Port 8080 in use | Hai ứng dụng hoặc container cùng host port | Dừng process cũ hoặc đổi host/server port |
| WAR vào Tomcat 9 lỗi | Jakarta Servlet vs javax.servlet incompatibility | Dùng external container tương thích Boot 3.5 |
| WAR `java -jar` không chạy | Traditional WAR chưa Boot repackage | Kiểm tra `WarLauncher`, manifest, `WEB-INF/lib-provided` |
| `build-image` báo Docker daemon unavailable | Engine/socket/context/permissions | `docker info`, Docker context, CI endpoint |
| Builder image pull fail | Network/proxy/registry auth | Kiểm tra builder/run image và quyền |
| `docker image inspect` không thấy image | Sai tag hoặc Docker daemon context khác | So imageName/context/log build |
| Image build success nhưng endpoint fail | Container chưa start hoặc app startup lỗi | `docker run`, logs, port mapping/readiness |
| `docker run -p 8080:8080` bind fail | Host port đã chiếm | `-p 18080:8080`, gọi host 18080 |
| Dockerfile `COPY` not found | JAR chưa build hoặc không thuộc context | Package trước, kiểm tra path và `.dockerignore` |
| `mvn package` bỗng yêu cầu Docker | POM tự bind `build-image-no-fork` | Xem executions; tách image stage |
| Cluster không pull được image | Chưa push hoặc auth/tag/architecture sai | Registry digest, imagePullSecrets, platform |
| `mvn deploy` thành công nhưng workload cũ | Maven repository không phải runtime deploy | Publish image rồi rollout platform |
| `UnsupportedClassVersionError` trong container | JRE trong image không hỗ trợ target bytecode | Kiểm tra compiler release và runtime Java |
| Container exit code khác 0 | App startup exception hoặc sai entrypoint | Đọc container logs/exit code |
| HTTP 404 dù server chạy | Sai `@GetMapping`/context path | Kiểm tra route và URL |
| Image chạy laptop nhưng production lỗi | Config, JDK, env, secrets, architecture khác | Smoke test trên image và runtime thật |

Các lệnh debug:

```bash
mvn -B -ntp -e clean package
mvn -B -ntp -X clean package
docker version
docker image inspect demo/lifecycle-boundary-demo:1.0.0
```

`-X` có thể in repository URLs, system properties, đường dẫn local và cấu hình nhạy cảm. Redact trước khi chia sẻ debug logs.

## 19. Những câu hỏi tự kiểm tra

**Câu 1:** `mvn package` tạo JAR thành công. Có chắc port 8080 đang mở?  
**Đáp án:** Không. Cần start application bằng `spring-boot:run` hoặc `java -jar`.

**Câu 2:** `spring-boot:run` hoạt động. Có đủ chứng minh JAR phát hành chạy được?  
**Đáp án:** Không. Phải smoke-test packaged executable JAR.

**Câu 3:** Dự án kế thừa starter-parent và khai Spring Boot Plugin. Muốn executable JAR khi package có cần tự khai thêm execution repackage?  
**Đáp án:** Thông thường không; parent đã cung cấp execution. Đừng bind trùng.

**Câu 4:** `spring-boot:build-image` có tự push Docker Hub không?  
**Đáp án:** Không, mặc định publish=false. Cần registry/auth/publish riêng nếu muốn.

**Câu 5:** Image đã có trong Docker daemon, nghĩa là container đang chạy?  
**Đáp án:** Không. Image là vật liệu để chạy container, phải gọi `docker run`/runtime và kiểm tra HTTP.

**Câu 6:** Khi bind image build vào Maven `package` dùng goal nào?  
**Đáp án:** `build-image-no-fork`, vì `build-image` khi gọi CLI có cơ chế fork package lifecycle.

**Câu 7:** WAR deploy external Tomcat cần gì ngoài thay `<packaging>war</packaging>`?  
**Đáp án:** Cần `SpringBootServletInitializer`, đánh dấu embedded Tomcat `provided`, container/Jakarta version tương thích và cấu hình deployment đúng.

**Câu 8:** `mvn deploy` có triển khai container lên Kubernetes không?  
**Đáp án:** Không theo mặc định. Nó upload Maven artifacts, khác image registry push và deployment.

**Câu 9:** Dockerfile dùng JRE 17 nhưng code target Java 21 thì sao?  
**Đáp án:** Có thể `UnsupportedClassVersionError`. Phải đồng bộ Java target và runtime image.

**Câu 10:** Có bắt buộc dùng Dockerfile khi `spring-boot:build-image` không?  
**Đáp án:** Không. Cloud Native Buildpacks làm nhiệm vụ image creation từ Boot archive; Dockerfile là phương án khác.

## 20. Checklist kết thúc bài học

- [ ] Phân biệt rõ **artifact**, **process**, **image**, **container instance**, **registry entry**, **deployed workload**.
- [ ] Biết `mvn package`/`verify` đã chạy những phase/test goals nào.
- [ ] Xác nhận `packaging=jar` hoặc `packaging=war` đúng nhu cầu.
- [ ] Đã kiểm tra `spring-boot:repackage` binding và manifest/Boot launcher trong artifact.
- [ ] Không gọi repackage hai lần khi starter-parent đã thiết lập.
- [ ] Đã test `java -jar` trên artifact thật, không chỉ `spring-boot:run`.
- [ ] Đã chạy unit/integration tests và xem test report, không chỉ nhìn build xanh.
- [ ] Đã xác minh HTTP endpoint với process thật và port đúng.
- [ ] Nếu là traditional WAR, có initializer, provided Tomcat và container tương thích.
- [ ] Nếu tạo image, đã xác minh Docker daemon và builder/JRE hỗ trợ.
- [ ] Hiểu `build-image` fork package còn `build-image-no-fork` dùng cho lifecycle execution.
- [ ] Không kỳ vọng `mvn package` tự tạo image nếu POM không yêu cầu.
- [ ] Đã inspect image, chạy container và smoke test lại.
- [ ] Hiểu `EXPOSE` không tương đương `-p` publish port.
- [ ] Image push và platform deploy là hai bước riêng có credential/policy.
- [ ] Không nhầm Maven `deploy` với container image deployment.
- [ ] Không đưa credentials/secrets vào artifact/image layers.
- [ ] Đã cân nhắc non-root user, pinned image digest, SBOM/security scan.
- [ ] CI dùng đúng artifact cuối, không trộn output cũ từ caches/workspaces.
- [ ] Có trạng thái ghi nhận riêng cho build/test/run/image/publish/deploy.

**Kết luận:** `mvn package` tạo JAR/WAR. `spring-boot:repackage` làm JAR/WAR thành executable archive khi được cấu hình. `spring-boot:run` và `java -jar` **chạy ứng dụng**, còn `spring-boot:build-image` hoặc `docker build` **tạo image**. `docker run` mới khởi chạy container; registry publication và deployment là các bước khác. Với WAR, triển khai vào external servlet container khác với chạy executable Boot archive. Hiểu các ranh giới này giúp thiết kế CI đúng và không báo “đã deploy” khi mới chỉ “đã package”.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Maven Plugin — Running Your Application](https://docs.spring.io/spring-boot/maven-plugin/run.html)
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
- [Spring Boot Maven Plugin — Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html)
- [Spring Boot 3.5 — Cloud Native Buildpacks](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/cloud-native-buildpacks.html)
- [Spring Boot 3.5 — Build and Executable Archives](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/)
- [OCI Image Specification](https://github.com/opencontainers/image-spec)

*Các ví dụ được thiết kế với Spring Boot 3.5.16, Maven 3.6.3+ và Java 17. Lệnh Docker cần Docker daemon/registry phù hợp; nội dung `Hello from Maven` là HTTP body của ứng dụng mẫu, không phải stdout Maven.*
