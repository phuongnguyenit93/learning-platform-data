# Cloud Native Buildpacks tạo image từ ứng dụng Spring Boot như thế nào?

**Cloud Native Buildpacks (CNB)** là tập hợp đặc tả và công cụ chuyển mã nguồn hoặc artifact ứng dụng thành **OCI container image** mà người phát triển không cần tự duy trì Dockerfile. Với Spring Boot, Gradle task `bootBuildImage` hoặc Maven goal `spring-boot:build-image` lấy executable JAR/WAR đã được build, chuyển cho một **builder** chứa buildpacks và lifecycle, sau đó tạo image có Java runtime, application layers, launch configuration và metadata.

Ba điểm cần nhớ:

1. **Không cần Dockerfile không có nghĩa không cần container engine.** Trong Spring Boot 3.3, những task/goal tích hợp CNB cần giao tiếp với **Docker daemon** để chạy builder và xuất image.
2. **Compile/package và containerize là hai công việc khác nhau.** Gradle/Maven chuẩn bị JAR hoặc WAR; CNB buildpacks nhận diện artifact, cung cấp JRE, layers và launch process cho container.
3. **Image không phải JAR đổi đuôi.** Nó gồm OCI config, runtime base layers, Java runtime, application layers và thông tin process. Image có thể được lưu local hoặc push lên registry theo cấu hình.

Bài học đi sâu vào các thành phần builder/buildpack/lifecycle, năm pha xử lý, cách Spring Boot Gradle/Maven gọi CNB, ví dụ Java 17 thực hành, tối ưu cache/layers, khác biệt với Dockerfile, môi trường build và runtime, SBOM/bảo mật, xử lý sự cố và lưu ý CI/CD.

Ví dụ cố định **Spring Boot 3.3.5**, **Gradle 8.7**, **Java 17** và Paketo Java buildpacks tương thích để minh họa, **không khẳng định đó là phiên bản mới nhất**. Image/builder tag `latest` có thể thay đổi theo thời gian; cần pin version hoặc digest trong quy trình release nghiêm ngặt.

## 1. Vì sao có Cloud Native Buildpacks?

Một cách phổ biến để containerize Spring Boot app là viết Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây chỉ là một **Dockerfile tối giản để so sánh**, không phải file trong ví dụ CNB. Với cách này, bạn phải tự chọn base image, JRE, user, cách copy/partition lớp nội dung, entrypoint, cách cập nhật OS security patches và build pipeline.

Với Spring Boot và CNB, việc tạo image có thể bắt đầu bằng:

~~~bash
./gradlew bootBuildImage
~~~

hoặc:

~~~bash
mvn spring-boot:build-image
~~~

Builder và buildpacks đã đóng gói logic để nhận biết ứng dụng Java, bổ sung runtime, khai báo cách chạy, sử dụng cache và tạo OCI layers. Tư duy vận hành chuyển từ **tự viết quy trình Dockerfile cho từng app** sang **quản lý tập trung builder/buildpacks/run image và chính sách artifact**.

**Không nên suy ra CNB tự động tốt nhất ở mọi tiêu chí.** Với native libraries, packages rất riêng, yêu cầu image cực nhỏ hoặc build pipeline bất thường, Dockerfile hay builder tùy chỉnh có thể phù hợp hơn. Cần đánh giá security, compatibility, performance và khả năng bảo trì.

## 2. Các thành phần chính

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Application input | Source hoặc artifact cần đóng gói | Executable Spring Boot JAR |
| Platform | Kết nối ứng dụng với lifecycle, builder, cache và output | Spring Boot plugin, `pack` CLI |
| Builder image | Môi trường build gồm buildpacks, lifecycle và build-time base | Paketo builder |
| Buildpack | Phát hiện khả năng ứng dụng và đóng góp runtime/layers | Paketo Java buildpacks |
| Lifecycle | Điều phối các giai đoạn build theo CNB specification | Analyzer, detector, restorer, builder, exporter |
| Build image | OS/tools cần trong quá trình build | Build-time base của builder |
| Run image | OS/base layers của image khi chạy | Run image được builder tham chiếu |
| Cache | Lưu các layers tái sử dụng | Docker named volumes hoặc cơ chế platform hỗ trợ |
| Result image | Container image theo chuẩn OCI | `cnb-hello:1.0.0` |
| Launcher/process | Cách chạy app bên trong image | CNB launcher và process type |

### Builder khác buildpack và run image

**Buildpack** là logic biết phát hiện/cung cấp một chức năng: Java runtime, executable-JAR handling, process metadata, v.v. **Builder** là image có cấu hình buildpack order, lifecycle, build-time base và reference tới run image. **Run image** cung cấp các base layers sử dụng ở container cuối.

~~~text
Spring Boot JAR/WAR
       |
       v
+-----------------------------------+
| CNB builder image                 |
| - ordered buildpacks              |
| - lifecycle                       |
| - build-time environment          |
| - reference to run image          |
+-----------------------------------+
       |
       v
 Analyze -> Detect -> Restore -> Build -> Export
       |
       v
+-----------------------------------+
| OCI application image             |
| - compatible run image layers     |
| - Java runtime layers             |
| - application layers              |
| - launch process and metadata     |
+-----------------------------------+
       |
       v
 Docker / Kubernetes / container runtime
~~~

Sơ đồ không cam kết số lượng hoặc vị trí layers giống nhau cho mọi builder. Một buildpack composite có thể gọi các buildpacks con; không phải mỗi buildpack tương ứng chính xác một OCI layer.

### Build image không phải run image

Build-time environment có thể cần compiler/tools để chạy buildpack. Runtime environment thường chỉ cần runtime libraries/JRE và app. Nếu bạn chọn một custom run image không tương thích OS/architecture hoặc với builder target, build có thể thất bại hoặc image chạy sai. Vì thế khi chưa có lý do rõ, **nên dùng run image do builder chọn**.

## 3. Spring Boot plugin truyền gì cho CNB?

Gradle:

~~~text
src/main/java + src/main/resources
             |
     compileJava/processResources
             |
           bootJar
             |
    executable Spring Boot JAR
             |
        bootBuildImage
             |
      CNB builder/lifecycle
             |
        OCI image
~~~

`bootBuildImage` là task Spring Boot Gradle plugin cung cấp khi có Java hoặc War plugin phù hợp. Task lấy executable archive (`bootJar` hoặc `bootWar`) đã được build làm input. Gradle task dependencies bảo đảm những producer tasks cần thiết chạy trước.

Maven:

~~~text
Source -> Maven package/repackage -> executable JAR/WAR
                                             |
                                             v
                                  spring-boot:build-image
                                             |
                                             v
                                          OCI image
~~~

Goal `spring-boot:build-image` dùng từ command line bảo đảm package lifecycle thích hợp đã chạy. Nếu muốn bind vào phase `package`, tài liệu Spring Boot khuyến nghị goal `build-image-no-fork`, tránh khởi chạy vòng lifecycle lặp.

**Điểm cốt lõi:** CNB nói chung có thể build từ source; nhưng tích hợp của Spring Boot Gradle/Maven plugin trong bài **truyền packaged application archive**. Buildpack không mặc định thực thi lại `gradle build` hoặc `mvn package` từ source bên trong builder.

### Phân biệt các tác vụ

- `bootJar`: tạo executable JAR; chưa có container image.
- `bootWar`: tạo executable WAR; chưa có container image.
- `bootBuildImage`: tạo OCI image từ executable archive.
- `java -jar`: chạy artifact bằng JVM hiện tại.
- `docker build`: xây image từ Dockerfile/build context, là một workflow khác.
- `docker run`: chạy container từ một image đã tồn tại.

Nếu `bootJar` thành công nhưng `bootBuildImage` thất bại vì Docker daemon, điều đó **không nhất thiết là lỗi Java compilation**.

## 4. Năm pha của Cloud Native Buildpacks lifecycle

Theo tài liệu CNB, năm giai đoạn chính là **Analyze → Detect → Restore → Build → Export**. Platform có thể chạy chúng thông qua một process tổng hợp như `creator`, nên không phải lúc nào log cũng hiển thị năm process tách rời.

~~~text
                  Application artifact
                          |
                          v
                    [Analyze]
              Previous image metadata
                          |
                          v
                     [Detect]
             Choose applicable buildpacks
                          |
                          v
                    [Restore]
                   Reuse layers
                          |
                          v
                     [Build]
       Runtime + application + launch metadata
                          |
                          v
                     [Export]
              OCI image + cache update
~~~

### 4.1. Analyze

Analyzer kiểm tra metadata của previous image và điều kiện truy cập registry/cache theo platform. Mục tiêu là hiểu trạng thái lần build trước để có thể reuse layers. Lần đầu chưa có previous image vẫn có thể build được; không có cache không tự động là lỗi.

### 4.2. Detect

Detector duyệt cấu hình buildpack order, hỏi buildpacks có nhận diện input không và chọn nhóm phù hợp; từ đó lập **build plan**. Với executable Spring Boot JAR, các buildpacks Java/executable-archive có thể được chọn; buildpacks không liên quan có thể bị loại.

Nếu builder không có buildpack hỗ trợ Java hoặc file đầu vào không phải archive đúng dạng, có thể thấy lỗi trong phase Detect. Đổi `spring.application.name` không giải quyết lỗi thiếu buildpack.

### 4.3. Restore

Restorer khôi phục metadata và các layers có thể tái dùng từ previous image/cache. Java runtime layer, thư viện ít thay đổi hoặc các launch layers có thể được reuse khi inputs/metadata phù hợp. Không nên khẳng định mọi lần sửa code chỉ thay đúng một layer: việc partition và cache invalidation phụ thuộc buildpack/lifecycle/artifact.

### 4.4. Build

Những buildpacks đã chọn thực hiện logic đóng góp:

- Java/JRE runtime phù hợp với bytecode của ứng dụng.
- Các application files từ executable JAR/WAR.
- Runtime library layers và metadata về cách launch.
- Build-time configuration và thông tin về components/SBOM nếu buildpacks hỗ trợ.
- Thông tin process, environment, filesystem layers để exporter dùng.

Với Paketo Java buildpacks, biến `BP_JVM_VERSION=17` yêu cầu Java major version trong image. Java toolchain của Gradle vẫn là cấu hình khác: Gradle dùng nó để compile, còn buildpack dùng biến trên để chuẩn bị runtime. Hai version phải tương thích.

### 4.5. Export

Exporter kết hợp **run image base layers** với launch layers/metadata để tạo OCI image, ghi vào target output và cập nhật cache. Tùy platform/plugin config, image có thể được load vào local Docker daemon hoặc push registry.

**Image cuối không phải builder image.** Builder là môi trường build; app runtime image được tạo mới dựa trên run image và layers phù hợp.

### Launch và rebase là những hoạt động khác

Khi container chạy, **CNB launcher** thực thi process được buildpacks khai báo, không nhất thiết chính xác chuỗi `java -jar app.jar` mà người phát triển từng dùng từ terminal.

**Rebase** là thao tác đổi base/run-image layers của image đã build khi tương thích, tránh chạy lại toàn bộ buildpacks. Rebase không tự compile Java sources, không nâng version Spring dependencies trong JAR và không tự sửa mọi CVE. Nó tạo image/digest mới, cần kiểm thử và ghi release provenance.

## 5. Thực hành Gradle: Spring Boot REST application → image

Ví dụ này có thể chạy với JDK 17, Gradle Wrapper 8.7, Spring Boot 3.3.5, Docker daemon hoạt động và mạng có thể truy cập builder/dependency repositories. Chúng ta tạo HTTP endpoint trả về `HELLO_FROM_CNB` và đóng gói **không cần Dockerfile**.

### 5.1. Cấu trúc

~~~text
cnb-hello/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/cnb/
    ├── CnbHelloApplication.java
    └── HelloController.java
~~~

Nếu dùng Gradle Wrapper, root còn có `gradlew`, `gradlew.bat` và `gradle/wrapper/`. Ví dụ giả định đã có Wrapper tương thích.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'cnb-hello'
~~~

### 5.3. `build.gradle` (Groovy DSL, đầy đủ)

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.cnb.CnbHelloApplication'
}

tasks.named('bootBuildImage', BootBuildImage) {
    imageName = 'cnb-hello:1.0.0'
    environment['BP_JVM_VERSION'] = '17'
}
~~~

Giải thích:

1. Java plugin và Spring Boot plugin tạo những tasks cần để compile, package rồi image build.
2. `spring-boot-starter-web` mang Spring MVC và embedded Tomcat runtime.
3. `java.toolchain` yêu cầu Java 17 khi compile; `BP_JVM_VERSION` điều khiển yêu cầu version cho Paketo Java buildpack.
4. `imageName` đặt tag local rõ ràng, tránh phải suy đoán từ `project.name` và `project.version`.
5. Không đặt `builder` nên Spring Boot plugin dùng default builder cho phiên bản plugin đang dùng; default này **có thể thay đổi theo plugin version**.
6. Không bật `publish`: image được build vào Docker daemon plugin kết nối, chưa tự push một registry.
7. Không có `Dockerfile` và không gọi `docker build`.

### 5.4. `CnbHelloApplication.java`

Đường dẫn `src/main/java/com/example/cnb/CnbHelloApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbHelloApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbHelloApplication.class, args);
    }
}
~~~

### 5.5. `HelloController.java`

Đường dẫn `src/main/java/com/example/cnb/HelloController.java`:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "HELLO_FROM_CNB";
    }
}
~~~

Controller cùng package với main class nên được Spring Boot component scan tìm thấy. Không cần DB, message broker hay cloud secrets. Spring MVC mặc định dùng port 8080 nếu không đổi `server.port`.

### 5.6. Kiểm tra môi trường

~~~bash
java -version
./gradlew --version
docker version
docker info
~~~

`docker version` và `docker info` phải kết nối được daemon. **Chỉ có Docker CLI executable không đủ**. Docker Desktop phải chạy hoặc Docker Engine/remote daemon phải có quyền truy cập phù hợp. Nếu Docker context/`DOCKER_HOST` trỏ daemon khác, image có thể xuất hiện ở một image store khác với nơi bạn đang kiểm tra.

### 5.7. Tạo image

~~~bash
./gradlew clean bootBuildImage
~~~

Gradle chạy những tasks phụ thuộc cần để tạo executable archive, rồi task `bootBuildImage` khởi động CNB lifecycle. Lần đầu có thể phải tải Maven dependencies, builder/run images và JRE runtime nên lâu hơn các lần build có cache.

Log thực tế có thể hiển thị các thông báo tương tự:

~~~text
> Task :compileJava
> Task :bootJar
> Task :bootBuildImage
... buildpack/lifecycle logs ...
... image created ...
~~~

Đây là **sơ đồ log**, không phải stdout được bảo đảm. Task list/thứ tự/phase text và digest thay đổi theo plugin, cache và Docker. Không suy ra image digest trước khi chính image đã được tạo.

### 5.8. Xác minh image

~~~bash
docker image ls cnb-hello
docker image inspect cnb-hello:1.0.0
~~~

Image đã được load vào Docker daemon thì lệnh inspect sẽ cho thông tin image ID/config/layers. Nếu không tìm thấy, kiểm tra imageName trong build output, Docker context/daemon mà Gradle dùng, và xem build có thực sự hoàn thành hay không.

### 5.9. Chạy container

~~~bash
docker run --rm -p 8080:8080 cnb-hello:1.0.0
~~~

Trong terminal khác:

~~~bash
curl -fsS http://localhost:8080/api/hello
~~~

Response body kỳ vọng:

~~~text
HELLO_FROM_CNB
~~~

Nếu port 8080 của host đã bị chiếm:

~~~bash
docker run --rm -p 18080:8080 cnb-hello:1.0.0
~~~

và thử:

~~~bash
curl -fsS http://localhost:18080/api/hello
~~~

Trong option `-p HOST:CONTAINER`, cổng bên phải phải là cổng app thực sự lắng nghe trong container. Lệnh run foreground giữ terminal mở; dừng bằng Ctrl+C. HTTP response body không tự có newline; test nên so đúng nội dung.

**Quan trọng:** Lệnh `curl` có thể chạy quá sớm khi app chưa startup. Trong CI dùng retry/timeout hoặc health check thay vì khẳng định một request ngay sau `docker run -d` luôn thành công.

## 6. Maven tạo OCI image tương tự thế nào?

Với Maven, tạo cùng hai Java files, nhưng dùng `pom.xml` thay vì Gradle scripts. Ví dụ POM hoàn chỉnh cho Spring Boot 3.3.5:

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>cnb-hello</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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
                <configuration>
                    <mainClass>com.example.cnb.CnbHelloApplication</mainClass>
                    <image>
                        <name>cnb-hello:1.0.0</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy từ Maven project root:

~~~bash
mvn spring-boot:build-image
docker image inspect cnb-hello:1.0.0
docker run --rm -p 8080:8080 cnb-hello:1.0.0
~~~

Maven goal `spring-boot:build-image` ở CLI bảo đảm package lifecycle đã chạy. Không cần gọi `mvn package` bằng tay trước nếu dùng goal theo đúng tài liệu.

### `build-image` và `build-image-no-fork`

- **`build-image`:** phù hợp gọi trực tiếp từ terminal; fork lifecycle để bảo đảm packaging.
- **`build-image-no-fork`:** phù hợp bind goal execution vào lifecycle `package` để tránh fork vòng package lần nữa.

Ví dụ snippet trong `spring-boot-maven-plugin`, chỉ dùng khi **muốn tự build image mỗi lần package**:

~~~xml
<executions>
    <execution>
        <goals>
            <goal>build-image-no-fork</goal>
        </goals>
    </execution>
</executions>
~~~

Không thêm snippet vào POM của bài tập nếu muốn image build là một thao tác chủ động. Nếu bind vào package, CI chạy `mvn package` có thể cần Docker daemon và network dù chỉ định compile/test artifact.

## 7. `bootBuildImage` vs `pack build` vs Dockerfile

| Cách | Input | Ai quyết định runtime image/layers? | Cần Dockerfile? |
| --- | --- | --- | --- |
| Gradle `bootBuildImage` | Boot executable archive | CNB builder/buildpacks | Không |
| Maven `spring-boot:build-image` | Boot executable archive | CNB builder/buildpacks | Không |
| CNB `pack build` | Source directory hoặc artifact | Builder/buildpacks được chọn | Không |
| `docker build` | Dockerfile và build context | Dockerfile/base images | Có |

`pack` là CNB CLI độc lập. Nếu đã có Spring Boot JAR:

~~~bash
./gradlew bootJar
pack build cnb-hello:1.0.0 --path build/libs/cnb-hello-1.0.0.jar --builder paketobuildpacks/builder-jammy-base:latest
~~~

Đây là **lệnh minh họa** cần `pack` CLI được cài và builder Java còn tồn tại/tương thích, không phải bắt buộc để dùng Spring Boot plugin. Với Spring Boot Gradle configuration như ví dụ, executable JAR thông thường được đặt `build/libs/cnb-hello-1.0.0.jar`. Nếu đã tùy chỉnh `archiveFileName`, phải dùng đúng path thực.

**Không cần cài pack CLI cho `bootBuildImage`**. Plugin Spring Boot tự đóng vai trò CNB platform/orchestrator. Dockerfile có thể thích hợp khi tổ chức cần OS packages/native customizations vượt khả năng builder hiện có. Tuy nhiên không có câu trả lời rằng một cách luôn an toàn hoặc nhỏ hơn cách còn lại mà không đo và scan.

## 8. Chọn Java version, builder và run image

### Java version ở ba nơi

- **`java.toolchain=17`:** version Java dùng để compile khi Gradle sử dụng toolchain.
- **`BP_JVM_VERSION=17`:** yêu cầu Paketo Java buildpack chọn runtime Java 17 tại image build.
- **`java -version` trên host:** JVM mà shell hiện tại gọi, không nhất thiết trùng runtime JVM được đóng gói trong image.

Với Paketo, major version 17 có thể được giải quyết thành một Java 17 patch hiện hành của builder/buildpack. **Không nên suy ra patch version chính xác chỉ từ `BP_JVM_VERSION=17`.** Dùng SBOM/build output và image metadata để kiểm chứng JRE.

### Custom builder

Snippet Gradle chỉ dùng khi có builder phù hợp:

~~~groovy
tasks.named('bootBuildImage') {
    builder = 'paketobuildpacks/builder-jammy-base:latest'
}
~~~

Paketo builder ở đây là lựa chọn đã có trong tài liệu cho họ Spring Boot 3.3; tag mutable `latest` không nên pin duy nhất ở CI release nghiêm ngặt. Builder versions có thể thay đổi buildpack behavior, cache compatibility, Java runtime và security settings.

### Custom run image

Builder chỉ định run image tương thích theo mặc định. Có thể override runImage với một image **được xác minh tương thích**, nhưng không nên đưa một JRE base image Dockerfile thông thường vào cấu hình này chỉ vì tên có `java`.

**Khác biệt:** builder image có CNB lifecycle/buildpacks; run image cung cấp OS base cho final image. Nếu custom run image khác stack/target architecture/libc, image có thể build fail hoặc chạy sai. Khi không có policy đặc biệt, ưu tiên run image do builder chọn.

### Build-time và runtime variables

| Loại | Ví dụ | Thời điểm |
| --- | --- | --- |
| Buildpack Java option | `BP_JVM_VERSION=17` | Build image |
| Paketo launch/runtime variable | Một số `BPL_*` options | Khi container start |
| Spring application variable | `SPRING_PROFILES_ACTIVE`, `SERVER_PORT` | Khi Spring Boot chạy |
| Gradle compiler config | Java toolchain | Trước image build |

Ví dụ truyền Spring profile lúc chạy:

~~~bash
docker run --rm -p 18080:8080 -e SPRING_PROFILES_ACTIVE=dev cnb-hello:1.0.0
~~~

Profile này không bắt buộc để endpoint của ví dụ hoạt động. Trong ứng dụng thật, đừng đóng credentials hoặc environment-specific secrets cứng vào image/build script.

## 9. Layering và cache ảnh hưởng tốc độ ra sao?

Spring Boot executable JAR có thể có:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
org/springframework/boot/loader/
BOOT-INF/layers.idx       (khi layered archive được tạo)
~~~

Tùy phiên bản/build configuration, Spring Boot có thể phân loại nội dung thành dependencies, snapshot dependencies, loader và application. Java buildpacks có thể tận dụng layered archive hoặc phân tích riêng để tạo OCI layers phù hợp. **Không đồng nhất số OCI layers với số nhóm entries trong JAR**.

Giả sử có hai builds:

~~~text
A: same Spring libraries + Java application code A
B: same Spring libraries + Java application code B
~~~

Nếu chỉ application code đổi, một số dependency/runtime layers có thể tái sử dụng; nếu đổi JRE, builder hoặc dependency graph, cache có thể bị invalidated.

### Build cache và launch cache

Spring Boot Gradle/Maven CNB integration có cấu hình **build cache** và **launch cache**, thường sử dụng Docker named volumes khi build local. Theo tài liệu Spring Boot 3.3, tên cache mặc định có thể được suy ra từ **full output image name**. Vì vậy:

~~~text
cnb-hello:1.0.0
cnb-hello:1.0.1
~~~

có thể có cache names khác nhau khiến layers không được reuse như mong đợi, dù code chỉ thay ít. Đây là lý do CI cần quản lý cache naming và vòng đời cache.

Ví dụ **tùy chọn**, không cần cho project đầu tiên:

~~~groovy
tasks.named('bootBuildImage') {
    buildCache {
        volume {
            name = 'cnb-hello.build-cache'
        }
    }
    launchCache {
        volume {
            name = 'cnb-hello.launch-cache'
        }
    }
}
~~~

Khi dùng shared CI Docker daemon, đặt tên cache riêng cho application/build để tránh đụng nhau giữa các jobs. Không dùng cache chung cho nhiều ứng dụng không liên quan mà không kiểm soát.

### Các cache không giống nhau

- **Gradle build cache/up-to-date:** reuse task outputs/compile results khi inputs phù hợp.
- **CNB cache:** reuse build/launch layers được CNB buildpacks lưu.
- **Docker local image/layer store:** quản lý image blobs của Docker daemon.
- **Registry cache/previous image:** tùy platform và cấu hình remote build.

Lệnh `./gradlew bootBuildImage` có thể tránh compile nếu Gradle thấy source không đổi, nhưng image build/lifecycle vẫn có hoạt động riêng. Không coi `UP-TO-DATE` ở một Gradle task là chứng minh mọi CNB layers đã reuse.

### Đo thay vì đoán

Để benchmark, so các lần build với cùng builder/run images, code/dependencies, cache state, network và machine. Tách lần cold cache khỏi warm cache. Ghi thời gian compile, thời gian CNB lifecycle, số layers restored/rebuilt và peak memory. Một build dùng Dockerfile chưa chắc chậm hơn CNB; Docker layer ordering và context cũng ảnh hưởng lớn.

## 10. Runtime process, non-root, SBOM và image identity

### Launch process

CNB launcher chọn process đã được buildpacks đóng góp. Cấu hình OCI Entrypoint/Cmd không nhất thiết tương đương chuỗi literal `java -jar app.jar`. Dùng:

~~~bash
docker image inspect cnb-hello:1.0.0
~~~

để xem metadata thực tế. Docker publish port qua `-p` chỉ ánh xạ host ↔ container port; không ép Spring Boot tự đổi `server.port`.

### Non-root

Tài liệu Spring Boot 3.3 nói CNB images được build và chạy với non-root users trong workflow được hỗ trợ. Tuy vậy cần xem actual image User/security context nếu có custom builder, container runtime overrides hoặc policy đặc biệt. **Non-root là một lớp bảo vệ, không thay thế image scanning và quản lý quyền filesystem.**

### SBOM

Buildpacks có thể sinh **Software Bill of Materials (SBOM)** mô tả JRE, application dependencies hoặc các thành phần khác tùy buildpack. Nó hỗ trợ inventory/license/CVE scanning và truy xuất nguồn gốc. SBOM **không tự chứng minh image sạch lỗ hổng**: cần scanner, dữ liệu vulnerability, buildpack/base updates và security policy.

CNB CLI `pack` có các thao tác xem/tải SBOM trong những phiên bản hỗ trợ, ví dụ `pack sbom download`. Chi tiết format/path có thể khác theo CNB API và buildpack version; xem output thực tế thay vì tự bịa report.

### Release provenance

Một record có ích:

~~~text
Git commit:           <actual-commit-from-CI>
Spring Boot version:  <actual-version>
Builder digest:       <verified-builder-digest>
Run image digest:     <verified-run-image-digest>
Output image tag:     <registry/repository:tag>
Output image digest:  <actual-sha256-digest>
SBOM reference:       <actual-reference-if-generated>
~~~

Đây là **mẫu điền**, không phải thông tin đã được tạo trong bài. Tag có thể bị thay đổi nếu registry cho phép; image digest nhận diện content tốt hơn khi điều tra production.

### Không nhúng secrets

Không ghi password/token hoặc private registry key vào Gradle `environment`, Spring `application.properties` đã đóng gói, Docker layers hay OCI labels. Registry/build authentication nên lấy từ cơ chế CI secrets/config phù hợp; runtime credentials từ orchestrator secret management. Build logs và SBOM có thể được giữ hoặc chia sẻ nên cần xem chính sách thông tin.

## 11. Rebase khác rebuild và khác cập nhật dependency

CNB hỗ trợ ý tưởng **rebase**: thay base/run image layers bằng run image tương thích mới mà không cần chạy lại toàn bộ buildpacks.

- **Rebase:** thay runtime base layers; có thể cập nhật một số OS security fixes khi tương thích.
- **Rebuild:** thực thi lại buildpacks, có thể chọn runtime/app dependencies khác theo inputs.
- **Application dependency upgrade:** sửa Gradle/Maven dependencies, compile/test và tạo binary mới.

Rebase không tự nâng thư viện Spring trong JAR. Nó cũng không luôn thay JRE nếu Java runtime được buildpacks đóng góp ở layer khác với run image base. Rebase tạo image/digest mới, phải có tests/scans và release record.

Builder tag mutable có thể thay buildpack versions, Java patch selection, SBOM và behavior ngay khi source code không đổi. Muốn supply-chain reproducibility cần quản lý builder/run image digests, buildpack versions, dependency locking và artifact provenance.

## 12. Publish image lên registry và triển khai CI/CD

Trong ví dụ Gradle, `imageName='cnb-hello:1.0.0'` chỉ tạo local image ở Docker daemon. **Nó không tự push image**.

Sau khi đã có quyền registry và đăng nhập bằng cơ chế an toàn:

~~~bash
docker tag cnb-hello:1.0.0 registry.example.test/team/cnb-hello:1.0.0
docker push registry.example.test/team/cnb-hello:1.0.0
~~~

`registry.example.test` chỉ là ví dụ, cần thay bằng registry thật; không có endpoint thật để push ở đây. Spring Boot `bootBuildImage` cũng có thuộc tính `publish` và cấu hình registry authentication, nhưng chỉ bật khi muốn xuất bản image:

~~~groovy
tasks.named('bootBuildImage') {
    publish = true
}
~~~

Đây là **snippet tùy chọn**, không thuộc project thực hành chưa có registry. Image name, authentication và quyền push phải được CI cung cấp đúng. Push image là hành động phát hành, nên cần quality gate/release approvals theo tổ chức.

### CI smoke test

Một pipeline có thể chạy:

~~~bash
./gradlew clean test bootBuildImage
docker image inspect cnb-hello:1.0.0
docker run --rm -d --name cnb-smoke -p 18080:8080 cnb-hello:1.0.0
curl -fsS http://localhost:18080/api/hello
docker stop cnb-smoke
~~~

Đây là **luồng lệnh minh họa**, không phải test CI đã hoàn thiện: `curl` có thể đến trước khi server sẵn sàng. CI thật cần readiness retry, timeout, cleanup nếu lệnh lỗi, container logs và assertion HTTP body/status. Cũng cần bảo đảm Docker daemon mà CI test nhìn thấy là nơi image đã được build.

### Architecture và platform compatibility

Image được build trên amd64 không tự trở thành ARM64 image; target architecture phụ thuộc builder/run image/platform. Muốn chạy trên nhiều architectures phải có build workflow và multi-arch manifest phù hợp. Đừng chỉ đổi tag mà kỳ vọng native libraries và OS layers có thể cross-platform.

## 13. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Task 'bootBuildImage' not found` | Project chưa áp dụng Spring Boot và Java/War plugin phù hợp | Xem `plugins`, `tasks --all` và module đích |
| Maven goal không tìm thấy | Spring Boot Maven plugin/POM setup chưa phù hợp | Kiểm tra `pom.xml`, plugin resolution |
| `Cannot connect to Docker daemon` | Engine chưa chạy, sai context/socket/permission | `docker info`, `DOCKER_HOST`/Docker context/TLS |
| Builder image không pull được | Network, DNS, proxy, registry auth/rate limit | Kiểm tra builder URL và network |
| Detect phase thất bại | Builder thiếu buildpacks Java hoặc archive không hợp lệ | Kiểm tra `bootJar` và builder metadata |
| Build phase thiếu JRE | `BP_JVM_VERSION` không được builder/buildpacks hỗ trợ | Chọn JDK version tương thích |
| `UnsupportedClassVersionError` | Container Java thấp hơn bytecode | Đối chiếu Gradle toolchain và Paketo JVM |
| Image không có ở `docker image ls` | Image tag sai hoặc output nằm trên daemon khác | Xem imageName trong log và Docker context |
| HTTP 404 | Sai route hoặc component scan | Kiểm tra `/api/hello`, package và logs |
| Container start rồi exit | App exception, không có long-lived process hoặc thiếu config | `docker logs`, startup exception |
| Không truy cập được port | `-p` sai, app chưa ready hoặc port conflict | Kiểm tra listen port và port mapping |
| Build mỗi lần tải lại JRE | Cache bị mất, tên image/tag thay đổi, builder update | Xem CNB caches và image naming |
| Image quá lớn | JRE/base/dependency layers nặng | So builder/run image, SBOM và dependencies |
| CI bị OOM | Concurrent builds, image build cache/daemon/JVM thiếu RAM | Kiểm tra cgroup limits và memory allocations |
| Push bị denied | Thiếu registry credentials hoặc quyền repository | Kiểm tra CI identity và registry policy |
| CVE vẫn xuất hiện | App libs/JRE/run image chưa cập nhật | Scan SBOM, patch dependency/runtime/base |
| Cluster ARM không chạy image amd64 | Architecture mismatch | Build đúng platform/multi-arch strategy |

**Đọc đúng phase lỗi:** lỗi phát hiện buildpack xảy ra khác với lỗi truy cập Docker daemon hoặc lỗi HTTP ở container đã chạy. Không sửa `spring.application.name` hay Java package chỉ vì image không pull được từ registry.

## 14. Quy trình chẩn đoán chuẩn

1. **Xác nhận JAR/WAR chạy được:** `./gradlew bootJar` và `java -jar` trước khi điều tra CNB.
2. **Xác nhận Docker daemon:** `docker info` thành công đúng user/context của build plugin.
3. **Xác định builder/run image:** log cho biết image tags/digests nào được dùng; kiểm tra OS/architecture/JVM compatibility.
4. **Xem pha lỗi:** Analyze, Detect, Restore, Build hay Export.
5. **Kiểm tra Java:** JDK compile/toolchain, `BP_JVM_VERSION` và JRE thực tế trong image/SBOM.
6. **Xem output image:** `docker image inspect` với đúng imageName/tag/daemon.
7. **Chạy container:** port, environment, log startup và process exit code.
8. **Kiểm tra HTTP endpoint thật:** có retry/health readiness, xác nhận status/body.
9. **Kiểm tra cache:** image name, volumes, builder versions, CI runner lifetime.
10. **Kiểm tra policy:** SBOM, CVE scanner, non-root runtime, image signing và secrets.
11. **Ghi output digest/provenance:** release record có khả năng truy xuất.
12. **Không trộn lỗi build và runtime:** image created không đồng nghĩa ứng dụng business hoạt động.

### Lệnh chẩn đoán nhanh

~~~bash
./gradlew tasks --all
./gradlew clean bootJar
./gradlew bootBuildImage --info
docker info
docker image ls
docker image inspect cnb-hello:1.0.0
docker run --rm -p 18080:8080 cnb-hello:1.0.0
curl -fsS http://localhost:18080/api/hello
~~~

`--info` hiển thị thêm Gradle logs, còn output chi tiết của buildpacks thay đổi theo platform/builder versions. Nếu cache lạnh, lần đầu có thể tải nhiều images/runtime layers.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `bootBuildImage` có cần Dockerfile không?

**Đáp án:** Không. Nó dùng CNB builder/lifecycle để tạo OCI image từ executable archive. Với Spring Boot 3.3 integration, vẫn cần Docker daemon.

**Câu 2.** Builder image và run image khác nhau thế nào?

**Đáp án:** Builder chứa buildpacks/lifecycle và môi trường build; run image cung cấp runtime base layers cho image cuối.

**Câu 3.** Năm pha chính của lifecycle?

**Đáp án:** Analyze → Detect → Restore → Build → Export, lần lượt xem previous metadata, chọn buildpacks, reuse cache, đóng góp layers và tạo output image/cache.

**Câu 4.** `bootJar` thành công có chắc `docker image inspect` tìm được image mới?

**Đáp án:** Không. `bootJar` chỉ tạo JAR; `bootBuildImage` mới tạo image.

**Câu 5.** `BP_JVM_VERSION=17` có đổi Gradle compiler sang Java 17 không?

**Đáp án:** Không. Đó là Paketo Java buildpack build-time setting; Gradle Java toolchain riêng và cần tương thích.

**Câu 6.** Vì sao đổi tag image có thể làm cache mất hiệu lực?

**Đáp án:** Default CNB cache volumes của Spring Boot plugin có thể phụ thuộc full image name; đổi tag ảnh hưởng cache name/lifecycle.

**Câu 7.** Image được tạo local có tự xuất hiện trên registry không?

**Đáp án:** Không. Phải bật publish có auth phù hợp hoặc dùng push riêng.

**Câu 8.** SBOM có bảo đảm không còn CVE?

**Đáp án:** Không. SBOM mô tả components, hỗ trợ scanning/audit; cần vulnerability data và remediation.

**Câu 9.** Rebase có sửa Spring dependency versions trong JAR không?

**Đáp án:** Không. Rebase thay run-image base layers tương thích, không compile lại source hay cập nhật Java dependencies.

**Câu 10.** Khi container không trả `HELLO_FROM_CNB`, nên kiểm tra gì?

**Đáp án:** Image đã được build đúng, container còn chạy, logs/startup, port mapping, HTTP route, readiness và app runtime config.

## 16. Tài liệu chính thức

- Spring Boot 3.3 — [Packaging OCI Images with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html): `bootBuildImage`, Docker, builder, run image, env, caches.
- Spring Boot 3.3 — [Maven Build Image](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html): `build-image`, `build-image-no-fork`, Docker và publish.
- Spring Boot 3.3 — [Container Images: Cloud Native Buildpacks](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/cloud-native-buildpacks.html): Spring Boot CNB overview.
- CNB — [How Buildpacks Work](https://buildpacks.io/how-it-works/): builder, buildpacks và image flow.
- CNB — [Lifecycle Phases](https://buildpacks.io/docs/for-buildpack-authors/concepts/lifecycle-phases/): Analyze, Detect, Restore, Build, Export.
- CNB — [What Is a Builder?](https://buildpacks.io/docs/for-app-developers/concepts/builder/): builder components.
- Paketo — [Building Java Applications](https://paketo.io/docs/howto/java/): Java buildpacks và `BP_JVM_VERSION`.
- Spring Boot — [BootBuildImage Task API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootBuildImage.html): imageName, builder, runImage, publish, caches.

**Kết luận:** Spring Boot plugin tạo **executable archive**; CNB **builder** chọn buildpacks rồi thực hiện **Analyze → Detect → Restore → Build → Export**; **run image** cung cấp nền runtime; cuối cùng nhận được **OCI image** có Java runtime và launch process phù hợp. Để khẳng định thành công, hãy kiểm tra **output image**, chạy **container thật** và kiểm thử ứng dụng thay vì dừng ở việc tạo JAR.
