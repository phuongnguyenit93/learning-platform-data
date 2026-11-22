# Tạo image bằng Gradle bootBuildImage trong Spring Boot với Cloud Native Buildpacks

## 1. Mục tiêu và kết quả cần đạt

`bootBuildImage` là task của **Spring Boot Gradle Plugin** dùng **Cloud Native Buildpacks (CNB)** để chuyển executable JAR/WAR của ứng dụng thành **OCI container image**, không cần tự viết Dockerfile. Image tạo ra có thể được Docker chạy cục bộ hoặc đưa lên registry để triển khai bằng Docker, Kubernetes hoặc nền tảng container phù hợp.

Sau bài này, bạn cần:

1. Hiểu **Gradle task → executable archive → CNB builder/buildpacks → OCI image**; phân biệt builder image, run image và output application image.
2. Tạo Spring Boot Java 17 project hợp lệ, chạy JUnit test và dùng `./gradlew bootBuildImage` để sinh image.
3. Kiểm tra Docker daemon, tên image, tag, layer metadata và chạy endpoint `/hello` từ container.
4. Cấu hình `imageName`, `builder`, `runImage`, `BP_JVM_VERSION`, runtime JVM options và lựa chọn platform khi cần.
5. Phân biệt **build image cục bộ** với **publish lên registry**; quản lý Docker credentials an toàn.
6. Hiểu buildpack cache, cấu trúc image, hiệu quả tái sử dụng lớp và giới hạn của việc thay image tag.
7. Xử lý những lỗi thường gặp: không kết nối Docker, builder/run image không tương thích, sai Java version, registry authorization, sai architecture, buildpack detection hoặc native-image cấu hình nhầm.

**Phạm vi phiên bản của các ví dụ:** Spring Boot **3.5.16**, Java **17**, Gradle Wrapper **8.14.3** và **Docker Engine có thể truy cập**. Tên/phiên bản builder mặc định thay đổi theo dòng Spring Boot; khi dùng Boot 4.x hoặc Gradle major version khác, phải xem tài liệu đúng phiên bản thay vì sao chép giả định. Các lệnh chỉ là hướng dẫn để chạy trong một môi trường đã cài Java/Docker; bài không khẳng định đã chạy Docker trên máy của người đọc.

**Ghi nhớ ngay:** `bootBuildImage` **không phải** task Docker Gradle độc lập, **không yêu cầu** `Dockerfile`, và **không tự push** image lên registry nếu chưa bật publish.

## 2. Cloud Native Buildpacks làm việc như thế nào?

Cloud Native Buildpacks là tập chuẩn và công cụ đóng gói application thành image. Một **builder image** chứa môi trường xây dựng và một hoặc nhiều **buildpacks**. Các buildpack phát hiện ứng dụng Java, chuẩn bị Java runtime, cấu hình lớp ứng dụng và tạo launch metadata.

Một luồng tiêu biểu với Spring Boot:

```text
settings.gradle + build.gradle + src/
                 |
                 v
        ./gradlew bootBuildImage
                 |
                 +--> bootJar hoặc bootWar
                 |    tạo executable archive
                 |
                 v
      Spring Boot Gradle Plugin
                 |
          giao tiếp Docker daemon
                 |
                 v
       CNB Builder (Paketo mặc định)
         |        |         |
         v        v         v
       Detect   Build     Export
       app      layers    OCI image
                 |
            Run image / JRE
                 |
                 v
      cnb-demo:0.1.0-SNAPSHOT
                 |
        docker run -p 8080:8080
                 |
                 v
           GET /hello
```

Sơ đồ mô tả vai trò; CNB lifecycle thực tế có thể gồm thêm các bước analyze, restore, cache handling và metadata management theo phiên bản, không nhất thiết log đúng thứ tự vẽ.

**Bốn khái niệm khác nhau:**

| Thành phần | Vai trò | Có đưa nguyên builder vào runtime image không? |
|---|---|---|
| **Gradle `bootBuildImage`** | Điều phối đóng gói archive, yêu cầu builder chạy và tạo image | Không |
| **Builder image** | Môi trường build có lifecycle và buildpacks | Không, không phải runtime base image |
| **Run image** | Nền OS/libraries runtime được builder chọn hoặc bạn cấu hình | Có, là nền phù hợp cho output launch image |
| **Application image** | Image cuối có app, Java runtime/layers và launch metadata | Đây là artifact để `docker run`/deploy |

Với Spring Boot 3.5, task `bootBuildImage` được tạo khi Java hoặc WAR plugin được áp dụng cùng Spring Boot plugin; task type là `BootBuildImage`. Nó dùng executable **JAR hoặc WAR** làm input, **không** tự lấy raw Java source rồi thay Maven/Gradle compiler.

**Mặc định theo tài liệu Spring Boot 3.5:** builder được chọn là `paketobuildpacks/builder-noble-java-tiny:latest`. Đây là default **theo dòng tài liệu**, không phải lời khuyên pin `latest` cho mọi hệ thống production. Run image mặc định được lấy theo metadata của builder. Builder **tiny** và run image liên quan có thư viện hệ thống hạn chế, không có shell; ứng dụng cần shell script hoặc native OS libraries có thể phải chọn builder/run image khác.

**Bảo mật CNB:** image được thiết kế để **build và chạy với user không phải root** theo specification. Không suy luận từ điều này rằng image đã được quét lỗ hổng, không chứa secret hoặc phù hợp mọi yêu cầu tổ chức; còn cần scan, SBOM/provenance và policy riêng.

## 3. So sánh bootBuildImage với Dockerfile, bootJar và bootRun

| Công cụ / task | Input | Output | Có cần Docker daemon? | Ý nghĩa |
|---|---|---|---|---|
| `./gradlew bootJar` | Source Java/resources + dependencies | Executable `.jar` | Không | Đóng gói ứng dụng Spring Boot |
| `./gradlew bootWar` | Source + WAR plugin/dependencies | Executable `.war` | Không | Đóng gói WAR |
| `./gradlew bootRun` | Classpath phát triển | Process Java/Spring Boot chạy local | Không | Chạy app khi phát triển, không tạo image |
| `./gradlew bootBuildImage` | Executable JAR/WAR và plugin settings | OCI image trong Docker daemon | **Có** theo Boot 3.5 task | Buildpack tạo image không cần Dockerfile |
| `docker build -f Dockerfile ...` | Dockerfile + build context | Docker image | Thông thường có Docker builder/daemon | Tự điều khiển từng bước/layer |
| `docker run image` | Image đã tạo hoặc pull | Container process | Có | Khởi chạy image đã build |
| `./gradlew bootBuildImage --publishImage` | App + registry/image settings | OCI image và upload registry | Có Docker daemon + registry access | Publish theo CNB/plugin |

**`bootBuildImage` không tự chạy `test` chỉ vì nó tạo image.** Việc có dependency tới task packaging như `bootJar`/`bootWar` không đồng nghĩa có dependency tới task `check`/`test`. Khi CI cần test trước khi đóng gói, gọi `./gradlew clean test bootBuildImage`, `./gradlew check bootBuildImage` hoặc tạo dependency/gate rõ trong pipeline.

`bootBuildImage` tạo image nhưng không đồng nghĩa container đang chạy. Muốn thử HTTP endpoint cần `docker run`. Ngược lại, `bootRun` có thể chạy source mà không chứng minh image đã được tạo đúng.

## 4. Điều kiện tiên quyết trước khi chạy

Máy hoặc runner cần:

- JDK **17** (ví dụ) để Gradle chạy/compile theo phiên bản Wrapper/Boot; Java toolchain được cấu hình phù hợp.
- Gradle Wrapper `gradlew`/`gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle-wrapper.properties` hợp lệ. Nên dùng wrapper đã tạo bằng Spring Initializr/Gradle, không tạo file rỗng theo mẫu.
- Docker Engine/Desktop hoặc daemon tương thích có Docker API mà Spring Boot plugin truy cập được; **Docker daemon phải đang chạy**.
- Quyền gọi daemon và truy cập internet/registry cần thiết để kéo builder/run images cùng buildpack dependencies ở lần build đầu.
- Dung lượng disk/RAM đủ cho Gradle, builder container và cache volumes; runner có thể cần nhiều không gian hơn chỉ build JAR.
- Kiến trúc builder/run image hỗ trợ platform mục tiêu: `linux/amd64`, `linux/arm64` tùy image/builder thực tế.

Kiểm tra ở terminal:

```bash
java -version
./gradlew --version
docker version
docker info
docker context show
```

Trên Windows dùng `gradlew.bat --version` hoặc PowerShell `.\gradlew.bat --version`. Docker CLI `docker version` có thể in cả client/server; **chỉ có Docker CLI không đủ** nếu phần server trả lỗi "Cannot connect to the Docker daemon".

Nếu môi trường dùng Docker Desktop, kiểm tra Docker Desktop đã mở. Trong CI, kiểm tra socket/engine đã được cấp đúng quyền; đừng cấp quyền root/privileged rộng chỉ để giải quyết lỗi kết nối khi có giải pháp hạ tầng an toàn hơn.

## 5. Ví dụ Spring Boot Java 17 hoàn chỉnh

Ví dụ tên project `cnb-demo`, dùng Gradle Groovy DSL, Spring Boot Web và JUnit. Ta chọn HTTP endpoint đơn giản để xác minh image từ ứng dụng thật.

### 5.1. Cấu trúc thư mục

```text
cnb-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   └── java/com/example/cnb/
    │       ├── CnbApplication.java
    │       └── HelloController.java
    └── test/
        └── java/com/example/cnb/
            └── HelloControllerTest.java
```

Tạo project bằng Spring Initializr với Java 17, Gradle Groovy, Spring Web và Spring Boot Starter Test; sau đó bảo đảm Gradle build file/version theo ví dụ. Nếu tạo bằng tay, wrapper cần được Gradle tạo và commit đúng.

### 5.2. settings.gradle

```groovy
rootProject.name = 'cnb-demo'
```

Tên này ảnh hưởng tên image mặc định: `docker.io/library/cnb-demo:0.1.0-SNAPSHOT` khi `version` là `0.1.0-SNAPSHOT`. Trong multi-project, task của subproject có thể suy ra tên khác, vì vậy nên đặt `imageName` tường minh ở module ứng dụng khi cần phát hành.

### 5.3. build.gradle (Groovy DSL) chạy được

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = "docker.io/library/cnb-demo:${project.version}"
    environment["BP_JVM_VERSION"] = "17"
}
```

**Giải thích cấu hình:**

1. `java` plugin cung cấp source sets và Java compile/test tasks.
2. `org.springframework.boot` tạo `bootJar`/`bootRun`/`bootBuildImage` theo khả năng plugin.
3. `io.spring.dependency-management` cho phép Spring Boot quản lý version của starter; đây là một phương án. Nếu dùng Gradle native `platform(SpringBootPlugin.BOM_COORDINATES)` thì cần viết dependencies tương ứng, không trộn kiểu quản lý version mà không hiểu quy tắc.
4. `group` và `version` mô tả project artifact. `imageName` trong ví dụ là tên Docker image độc lập, có tag đúng project version.
5. `java.toolchain` bảo đảm compile theo Java 17 nếu toolchain sẵn. Không giả định toolchain tự giải quyết JDK khi máy/Gradle thiếu runtime phù hợp.
6. `BP_JVM_VERSION=17` được truyền **cho builder** để Paketo Java buildpacks chọn JVM version phù hợp. Với default builder, plugin còn có khả năng suy ra Java compatibility từ Java plugin; dòng override này cố ý để dễ quan sát.
7. `tasks.named('test').useJUnitPlatform()` bật JUnit Jupiter. Bài có test nhưng image task **không tự đảm bảo test đã chạy**; khi build CI gọi task `test` trước/đồng thời.

### 5.4. File Java main

`src/main/java/com/example/cnb/CnbApplication.java`:

```java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbApplication {
    public static void main(String[] args) {
        SpringApplication.run(CnbApplication.class, args);
    }
}
```

### 5.5. REST controller

`src/main/java/com/example/cnb/HelloController.java`:

```java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from CNB image";
    }
}
```

Nếu ứng dụng chạy trên cổng 8080 mặc định và không có context path khác, `GET http://localhost:8080/hello` trả HTTP 200 với response body **`Hello from CNB image`**. Đây là body, không phải stdout của Gradle hoặc Docker.

### 5.6. JUnit test xác nhận ứng dụng trước khi đóng gói

`src/test/java/com/example/cnb/HelloControllerTest.java`:

```java
package com.example.cnb;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsExpectedMessage() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello from CNB image"));
    }
}
```

Test dùng `spring-boot-starter-test`, chạy trong Spring test context; không cần khởi động container. **Không phải** chương trình Java Standard Library có thể biên dịch bằng `javac` riêng lẻ mà không có Spring/JUnit dependencies. Việc kiểm tra container thật là bước khác sau khi build image.

### 5.7. Gradle Wrapper

File `gradle/wrapper/gradle-wrapper.properties` có thể chứa:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

Đây chỉ là dòng cần quan tâm của wrapper file, không phải nội dung đầy đủ. Mỗi project có thể có thêm `distributionBase`, `zipStoreBase`, checksum và các cấu hình khác. Dùng wrapper đã được tạo/chấp thuận, không sửa ngẫu nhiên file `gradle-wrapper.jar`.

## 6. Tạo image lần đầu và chạy thử

### 6.1. Kiểm thử code và tạo image

Từ root project `cnb-demo`:

```bash
# Xác minh test không phụ thuộc Docker:
./gradlew clean test

# Build một OCI image cục bộ bằng Cloud Native Buildpacks:
./gradlew bootBuildImage
```

Hoặc một lần Gradle invocation có cùng mục đích:

```bash
./gradlew clean test bootBuildImage
```

Khi `bootBuildImage` chạy, Gradle đóng gói ứng dụng qua task liên quan, nói chuyện với Docker daemon, kéo builder/run images nếu cần, rồi cho CNB lifecycle/buildpacks tạo output image. Lần đầu có thể mất lâu vì phải tải nhiều layers/JDK/buildpack dependencies. Không có stdout cố định giữa máy khác nhau hoặc version builder thay đổi.

**Dấu hiệu cần tìm:** task `:bootBuildImage` chạy thành công và có log tạo image với tên đã chỉ định; toàn bộ Gradle command kết thúc `BUILD SUCCESSFUL`. Không kết luận pass chỉ vì `bootJar` đã tạo JAR nhưng Docker/CNB stage fail.

### 6.2. Kiểm tra image đã thực sự tồn tại

```bash
docker image ls cnb-demo
docker image inspect docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

`docker image ls cnb-demo` lọc tên repository cục bộ; `docker image inspect` kiểm tra image reference cụ thể. Nếu image không có ở daemon Docker bạn đang truy cập, xem Docker context/host và task logs. Có thể Gradle plugin đã dùng **một Docker daemon khác** với CLI hiện tại do `DOCKER_HOST`/`DOCKER_CONTEXT`, remote engine hoặc CI configuration.

Một lệnh inspect có output gọn hơn ở shell phù hợp:

```bash
docker image inspect \
  --format '{{.Id}} {{.Architecture}} {{.Os}}' \
  docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

Dạng template `{{...}}` là Go template do Docker CLI xử lý, không phải chuỗi Gradle/Groovy. Kết quả là image digest ID, kiến trúc và OS của image thực tế, không có giá trị cố định để chép sẵn.

### 6.3. Chạy container

```bash
docker run --rm --name cnb-demo -p 8080:8080 \
    docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

Tại terminal thứ hai:

```bash
curl -s http://localhost:8080/hello
```

**HTTP response body mong đợi:**

```text
Hello from CNB image
```

Dấu `\` nối dòng áp dụng cho shell Unix/macOS; Windows PowerShell nhập các lệnh thành một dòng hoặc dùng quy tắc nối dòng của PowerShell. Nếu cổng 8080 của host đã có app khác, dùng `-p 8081:8080` rồi gọi `http://localhost:8081/hello`; không cần sửa Java code.

Dừng container bằng Ctrl+C ở terminal đang chạy hoặc `docker stop cnb-demo` từ terminal khác. Dòng lệnh `--rm` làm Docker xóa container sau khi dừng, **không xóa image**. Docker image được giữ cho lượt chạy sau trừ khi người vận hành xóa thủ công hoặc garbage collection có chính sách riêng.

### 6.4. Tại sao không có Dockerfile?

CNB builder/buildpacks quyết định Java runtime, launch command, layers và một số biến môi trường. Vì vậy repo tối thiểu ở mục 5 **không có Dockerfile**; `bootBuildImage` vẫn tạo image. Nếu sau đó thêm `Dockerfile`, nó **không tự được bootBuildImage dùng**; bạn phải gọi `docker build` riêng khi muốn pipeline Dockerfile.

## 7. Cấu hình tên image và tag

### 7.1. Image name mặc định

Theo Spring Boot Gradle Plugin 3.5, mặc định là:

```text
docker.io/library/${project.name}:${project.version}
```

Với `rootProject.name='cnb-demo'` và `version='0.1.0-SNAPSHOT'`:

```text
docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

Đây là **Docker image reference** chứ không phải Maven GAV. `group='com.example'` không tự xuất hiện như registry namespace; nếu muốn tổ chức một image dưới `registry.example.com/team/...`, phải đặt image name.

### 7.2. Đặt imageName từ Gradle Groovy

Trong `build.gradle`:

```groovy
tasks.named('bootBuildImage') {
    imageName = "registry.example.com/team/${project.name}:${project.version}"
}
```

Đoạn này **thay cho** cấu hình `imageName` của ví dụ trước; không cần khai báo trùng nhiều khối cùng đặt tên nếu không hiểu cấu hình cuối cùng. `registry.example.com` chỉ là địa chỉ minh họa cho registry của tổ chức, không phải máy chủ mà người đọc có thể push nếu chưa có quyền.

### 7.3. Override ngay tại CLI

```bash
./gradlew bootBuildImage --imageName=example.com/team/cnb-demo:1.0.0
```

Gradle task xây image theo tên chỉ định cho invocation. Chỉ đặt `imageName` khác **không tự publish**. `docker image ls` ở daemon mà plugin dùng để xác nhận kết quả. Khi dùng `latest`, một tag có thể bị gán lại cho artifact khác; CI nên thêm version hoặc Git revision/digest để truy vết.

### 7.4. Nhiều tag cho một lần build

Task `BootBuildImage` hỗ trợ thuộc tính `tags` (các tên image **đầy đủ**). Ví dụ đoạn Groovy bổ sung:

```groovy
tasks.named('bootBuildImage') {
    imageName = "example.com/team/cnb-demo:1.0.0"
    tags = ["example.com/team/cnb-demo:stable"]
}
```

`tags` chỉ ảnh hưởng tagging, không phải cách thay đổi source/JDK. Chọn tag bất biến (`1.0.0` hoặc commit ID) cho rollback; `stable` chỉ là nhãn tiện dụng và có thể trỏ image khác về sau. Nếu hệ thống cung cấp cả `imageName` và `tags` bằng CLI/Gradle script, đảm bảo giá trị có registry/namespace đúng quy ước.

## 8. Builder image, runImage và Java version

### 8.1. Mặc định Paketo trong Spring Boot 3.5

Builder là thành phần CNB để dựng image; run image là nền cho ứng dụng đã dựng. Không chọn `runImage` tùy tiện chỉ vì nó có shell: **builder và run image phải cùng stack và tương thích với nhau**. Nếu đổi builder, theo mặc định plugin đọc run image từ builder metadata, đây là cách ít rủi ro hơn so với gán hai image không liên quan.

Ví dụ ghi rõ builder mặc định đã xác minh ở tài liệu Boot 3.5:

```groovy
tasks.named('bootBuildImage') {
    builder = 'paketobuildpacks/builder-noble-java-tiny:latest'
}
```

Dùng `latest` trong ví dụ làm theo default của plugin, **không phải cam kết reproducibility**. Trong pipeline cần tái lập/kiểm toán, pin một release tag hoặc digest được registry hỗ trợ theo chính sách và có kế hoạch cập nhật khi có bản vá.

**Hạn chế của "tiny":** runtime có thể **không có `/bin/sh`**, package manager hoặc native OS libraries mà các script ứng dụng giả định có. Nếu app cần shell script hoặc thư viện native đặc thù, chọn **builder/run image pair tương thích** có hệ thống thư viện phù hợp, ví dụ theo gợi ý tài liệu Spring Boot 3.5 về `paketobuildpacks/ubuntu-noble-run:latest`. Đây là điểm cần kiểm tra với đúng builder version, không chỉ đổi `runImage` rồi hy vọng hoạt động.

### 8.2. Java toolchain và BP_JVM_VERSION

Trong `java` block:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Cấu hình này phục vụ **Gradle compile/test**. Khi dùng default Paketo builder, Spring Boot Gradle Plugin cũng có thể suy ra Java compatibility từ Java plugin, nhưng ta có thể chỉ định yêu cầu JVM cho CNB builder:

```groovy
tasks.named('bootBuildImage') {
    environment["BP_JVM_VERSION"] = "17"
}
```

`BP_JVM_VERSION` là biến cấu hình **Paketo Java buildpacks ở build time**, không phải biến Spring Boot `server.port`. Nó ảnh hưởng JVM mà buildpack đưa vào output image. Nếu Java 17 source dùng API Java 21 hoặc compiler target 21 nhưng runtime được chọn 17, ứng dụng có thể lỗi `UnsupportedClassVersionError`; hãy đồng bộ compilation target, test JDK và JVM runtime.

Ở phần lớn trường hợp Java server app, **chọn JVM runtime** thay vì native image nếu chưa có yêu cầu rõ và toolchain/native compatibility đã được xác nhận.

### 8.3. Runtime JVM options

Paketo Java buildpacks thiết lập `JAVA_TOOL_OPTIONS`/launch environment cho container. Không đặt `BP_JVM_VERSION` rồi kỳ vọng nó tự thay heap limit hoặc GC policy. Một cách thêm JVM option vào launch environment bằng buildpack configuration (theo Spring Boot docs):

```groovy
tasks.named('bootBuildImage') {
    environment["BPE_DELIM_JAVA_TOOL_OPTIONS"] = " "
    environment["BPE_APPEND_JAVA_TOOL_OPTIONS"] = "-XX:+HeapDumpOnOutOfMemoryError"
}
```

Đây là **fragment tùy chọn**; không cần để chương trình `HelloController` chạy. `HeapDumpOnOutOfMemoryError` có thể tạo file lớn: production cần writable directory, resource limits, retention và bảo vệ dữ liệu heap dump. Với cấu hình runtime khác, xem Paketo environment variables/JVM memory calculator của phiên bản buildpacks.

**Không ghi secret vào `environment[...]` trong build script đã commit.** Các property build time có thể được log/ghi metadata. Ứng dụng nên nhận database password/token khi **chạy container**, qua secret manager/runtime env, không qua tag hoặc Dockerfile/buildpack settings công khai.

## 9. Gradle Kotlin DSL đầy đủ

Nếu project dùng `settings.gradle.kts` và `build.gradle.kts`, dùng cú pháp Kotlin tương ứng. **Chọn một DSL** trong project, không đặt Groovy `build.gradle` và Kotlin `build.gradle.kts` song song chỉ để chạy ví dụ.

`settings.gradle.kts`:

```kotlin
rootProject.name = "cnb-demo"
```

`build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("docker.io/library/cnb-demo:${project.version}")
    environment.put("BP_JVM_VERSION", "17")
}
```

Đây là full build script Kotlin DSL thay thế cho mục 5.3. Các file Java ở mục 5.4–5.6 vẫn dùng được. Trong Kotlin DSL, thuộc tính `imageName` của task `BootBuildImage` là Gradle `Property<String>`, do đó dùng `imageName.set(...)`; `environment` là map-like property nên dùng `environment.put(...)`.

Lệnh thực thi giống Groovy:

```bash
./gradlew clean test bootBuildImage
docker run --rm -p 8080:8080 docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

Nếu project dùng Windows, gọi `gradlew.bat` theo shell; Docker CLI thường vẫn là `docker`. Không chép những snippet `tasks.named('bootBuildImage')` theo Groovy vào Kotlin file và mong Gradle tự chuyển cú pháp.

## 10. Layered JAR, buildpack cache và tốc độ build

### 10.1. Vai trò của layers.idx

Spring Boot executable JAR có thể chứa `BOOT-INF/layers.idx`. Cấu trúc layer mặc định thường bao gồm:

| Spring Boot layer | Thường chứa | Tần suất thay đổi tương đối |
|---|---|---|
| `dependencies` | Thư viện external có release version ổn định | Thường thấp |
| `spring-boot-loader` | Boot Loader classes | Thường theo lần nâng Boot |
| `snapshot-dependencies` | Dependency dạng SNAPSHOT | Phụ thuộc nhịp phát triển |
| `application` | App classes/resources và một số local module dependencies | Thường cao nhất |

Paketo Spring Boot buildpack hiểu layer index và có thể dùng nó để tạo image layers phù hợp. Vì vậy khi chỉ đổi controller Java, nhiều dependency layers có khả năng tái sử dụng; không cần tự extract JAR rồi viết bốn lệnh `COPY` như phương án Dockerfile thủ công.

**Quan trọng:** CNB caching khác Gradle build cache. CNB có build/launch cache ở phía Docker daemon/builder; Gradle có compiler/task cache. Một buildpack cache hit không chứng minh `test` đã chạy; kiểm thử vẫn phải là quality gate của pipeline.

### 10.2. Cache volume do task quản lý

Tài liệu Spring Boot 3.5 nêu `bootBuildImage` sử dụng **named Docker volumes** cho `buildCache`, `launchCache` và `buildWorkspace` theo tên image mặc định. Chúng không phải file JAR mà bạn commit vào Git. Vì cache volume name thường **dựa trên imageName đầy đủ**, đổi tag theo mỗi version có thể tạo tên cache khác, giảm reuse.

Để kiểm soát ổn định cache qua nhiều version/tag của cùng app, có thể chỉ định tên volume riêng (Groovy DSL):

```groovy
tasks.named('bootBuildImage') {
    buildCache {
        volume {
            name = "cache-${rootProject.name}.build"
        }
    }
    launchCache {
        volume {
            name = "cache-${rootProject.name}.launch"
        }
    }
}
```

Với `rootProject.name='cnb-demo'`, hai volume có tên `cache-cnb-demo.build` và `cache-cnb-demo.launch`. Chọn tên khác nhau theo **app, builder stack và môi trường** khi cần tránh chia sẻ nhầm dữ liệu giữa các project. Không phải cứ dùng chung cache là tốt: cache cần được quản lý version/size/permission và dọn theo chính sách.

Kotlin DSL fragment tương đương:

```kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    buildCache {
        volume {
            name.set("cache-${rootProject.name}.build")
        }
    }
    launchCache {
        volume {
            name.set("cache-${rootProject.name}.launch")
        }
    }
}
```

### 10.3. Khi nào làm sạch cache?

Task có `cleanCache`, mặc định false. Khi cần chẩn đoán stale cache, có thể bật tạm:

```groovy
tasks.named('bootBuildImage') {
    cleanCache = true
}
```

**Chỉ dùng cho một lần điều tra có chủ đích**, sau đó khôi phục. Bật `cleanCache` liên tục phá lợi ích tái sử dụng cache. `./gradlew clean` thường chỉ xóa Gradle `build/` outputs, **không** phải cơ chế dọn Docker buildpack volumes.

CI ephemeral có thể làm cache volume biến mất giữa job nếu Docker daemon mới được tạo mỗi lần. Nếu muốn tăng tốc giữa runners, cần thiết kế cache/persistence phù hợp, không giả định volume trên máy này có ở máy khác.

### 10.4. Reproducibility và image createdDate

Spring Boot 3.5 hỗ trợ thuộc tính `createdDate` (mặc định là một mốc cố định để hỗ trợ build reproducibility). Nếu đặt `createdDate='now'`, thời gian metadata của image sẽ đổi theo mỗi build, có thể làm digest thay đổi ngay cả khi code giữ nguyên. Các tài nguyên static có phụ thuộc `last-modified` cũng cần xem vì CNB có thể điều chỉnh file timestamps để tái lập layer; Spring Boot có thuộc tính `spring.web.resources.cache.use-last-modified` để thay đổi cách HTTP static resource cache dùng metadata này khi cần.

**Reproducible image không đồng nghĩa supply-chain verified**: cần pin dependencies/builder/run image đúng, kiểm tra SBOM, scan CVEs, image signature/digest và build provenance độc lập.

## 11. Publish image lên registry

### 11.1. Phân biệt build local và publish

`./gradlew bootBuildImage` mặc định **`publish=false`**. Image được đặt trong daemon local; CI runner khác hoặc Kubernetes cluster sẽ không tự thấy nó trừ khi registry/transport đã được thiết lập.

Khi muốn upload:

```bash
./gradlew bootBuildImage \
  --imageName=registry.example.com/team/cnb-demo:0.1.0 \
  --publishImage
```

`registry.example.com` là tên registry minh họa; phải thay bằng registry thật mà tổ chức có quyền. Nếu registry yêu cầu authentication, dùng Docker credential store/helper hoặc `docker login` vào registry đúng, **không hardcode password trong Gradle file/CLI**.

Theo Spring Boot 3.5, plugin có thể đọc Docker configuration ở `$HOME/.docker/config.json` và credential helpers. Khi cần private builder/run image, sử dụng **`docker.builderRegistry`** credentials; khi publish output, dùng **`docker.publishRegistry`** nếu không dựa vào Docker credentials có sẵn.

**Lưu ý:** registry đích được xác định từ **host trong `imageName`**, không phải tự động từ `docker.publishRegistry.url`. Nếu `imageName` thiếu registry host, image có thể bị nhắm tới Docker Hub mặc định.

### 11.2. Cấu hình publish trong Groovy DSL

Đoạn sau **chỉ dùng cho job phát hành đã được cấp quyền**:

```groovy
tasks.named('bootBuildImage') {
    imageName = "registry.example.com/team/cnb-demo:${project.version}"
    publish = true
}
```

Khi publish từ máy developer, bạn có thể giữ `publish=false`/không khai báo publish rồi dùng `--publishImage` riêng để tránh upload không mong muốn mỗi khi thử build.

Đối với CI, nên truyền image tag từ release version hoặc commit SHA, kiểm tra output digest sau push. Tránh publish mutable `latest` như **tín hiệu duy nhất** để xác định bản đã deploy.

### 11.3. Credentials: cách dùng hợp lý

Nếu đã thiết lập Docker login trên runner qua credential helper được hỗ trợ:

```bash
# Chỉ minh họa cú pháp, lệnh có thể yêu cầu tương tác an toàn.
docker login registry.example.com

./gradlew bootBuildImage \
    --imageName=registry.example.com/team/cnb-demo:0.1.0 \
    --publishImage
```

Trong CI thực tế, dùng secret store và cơ chế `--password-stdin` hoặc helper phù hợp; **không đặt token trực tiếp vào command line** sẽ được log trong workflow. Nếu plugin không đọc được helper/registry credentials, xem `docker.publishRegistry` trong Spring Boot Gradle Plugin docs. Không commit credentials vào `build.gradle` hoặc `gradle.properties`.

### 11.4. Kiểm tra kết quả đã publish

Sau khi push, registry API hoặc `docker pull` trên một máy/daemon khác có quyền giúp kiểm chứng image có thật:

```bash
docker pull registry.example.com/team/cnb-demo:0.1.0
docker image inspect registry.example.com/team/cnb-demo:0.1.0
```

Lệnh sẽ không hoạt động với registry minh họa chưa có thật. Trong production, nên ghi **immutable digest** của image được registry trả về vào release record, thay vì chỉ dựa vào tag có thể đổi theo thời gian.

## 12. Tối ưu phát hành trong CI/CD

Một pipeline tối thiểu nên:

1. Checkout đúng source revision và pin Java/Gradle Wrapper/Boot plugin versions.
2. Cài Docker Engine hoặc cấp Docker API/socket đã được bảo vệ cho build job.
3. Resolve Gradle dependencies qua repository có quyền; không tin vào cache như nguồn dependency duy nhất.
4. Chạy unit tests/quality gates **trước hoặc cùng invocation** với `bootBuildImage`.
5. Tạo image có tên registry/namespace/tag rõ ràng.
6. Chạy container smoke test hoặc integration test từ **đúng image được tạo**, kiểm tra HTTP endpoint và startup logs.
7. Scan image, đánh giá SBOM/provenance/signature theo chính sách.
8. Publish image sau khi quality gates thành công; tránh upload image chưa test.
9. Lưu digest và deploy bằng digest hoặc tag bất biến do release process bảo đảm.
10. Không đưa credential vào image labels, buildpack `environment` hoặc public logs.

Ví dụ CI gồm hai giai đoạn phân biệt:

```bash
# Build local và test
./gradlew clean check bootBuildImage \
    --imageName=cnb-demo:ci-candidate

# Smoke test ở daemon có image, theo quy trình CI của tổ chức
docker run --rm -d --name cnb-candidate -p 18080:8080 cnb-demo:ci-candidate
curl --fail --silent http://localhost:18080/hello
docker stop cnb-candidate

# Nếu mọi gate và smoke test thành công, build/publish image release:
./gradlew bootBuildImage \
    --imageName=registry.example.com/team/cnb-demo:0.1.0 \
    --publishImage
```

Các lệnh là **mẫu luồng CI**, không phải script khẳng định luôn chạy thành công: `docker run -d` có thể trả về trước khi Spring Boot sẵn sàng, nên job thật phải có **readiness polling với timeout và cleanup khi fail** (hoặc health check thích hợp). Không dùng một request `curl` thực hiện ngay lập tức rồi coi lỗi connect là lỗi buildpack. Ví dụ cũng tạo lại image ở bước release; quy trình nghiêm ngặt nên kiểm soát việc promote/push **đúng image đã smoke test** hoặc đối chiếu digest trước và sau, thay vì giả định rebuild cho ra bytes giống nhau.

Nếu mục tiêu **chỉ** kiểm tra tại local, không cần registry hay Docker login. Nếu CI runner không có Docker daemon, `bootBuildImage` theo Spring Boot 3.5 sẽ không tạo image thành công; dùng một dịch vụ builder/runner hợp lệ thay vì chuyển sang chạy `bootJar` rồi tuyên bố image đã được phát hành.

## 13. Builder, platform, proxy và tùy chỉnh nâng cao

### 13.1. Chọn image platform

Khi build trên laptop ARM64 nhưng deploy lên x86_64 hoặc ngược lại, phải xét kiến trúc builder/run image và Java distribution do buildpack chọn. Spring Boot 3.5 task có thuộc tính `imagePlatform` nhận dạng `OS[/architecture[/variant]]`, ví dụ:

```groovy
tasks.named('bootBuildImage') {
    imagePlatform = 'linux/amd64'
}
```

**Không phải mọi builder hỗ trợ mọi architecture.** Nếu registry chỉ cung cấp một architecture, override này có thể khiến pull/build thất bại. Container runtime của môi trường đích còn cần tương thích; không đơn giản đổi tên image tag để chuyển architecture.

### 13.2. Docker context và remote daemon

Boot 3.5 task kiểm tra Docker CLI context và một số biến môi trường:

- `DOCKER_CONTEXT`: tên Docker context được chọn, có thể override `DOCKER_HOST`.
- `DOCKER_HOST`: địa chỉ daemon như `unix:///...` hoặc `tcp://...`.
- `DOCKER_CONFIG`: nơi chứa Docker CLI configuration; có thể ảnh hưởng context/credentials.
- `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`: TLS settings cho remote Docker.

Đừng hardcode unencrypted `tcp://host:2375` vào CI vì API Docker cho phép quyền thao tác rất lớn trên host. Với remote Docker, sử dụng TLS/SSH/context bảo mật theo chính sách.

Với Docker Desktop, Colima, Podman hoặc minikube, cách daemon được expose có thể khác. Spring Boot documentation đưa ví dụ `docker.host` cho Podman socket và Colima; hãy xác minh phiên bản runtime, quyền socket, mount semantics và hỗ trợ Docker API trước khi coi chúng tương đương Docker Engine chính thức trong mọi trường hợp.

### 13.3. Network proxy

Nếu builder cần tải Java runtime hoặc buildpack dependencies qua proxy, Gradle process có mạng **chưa đủ**: builder container chạy ở môi trường của Docker daemon, có thể cần `HTTP_PROXY`/`HTTPS_PROXY` ở task `environment`. Fragment minh họa:

```groovy
tasks.named('bootBuildImage') {
    environment["HTTP_PROXY"] = "http://proxy.example.com"
    environment["HTTPS_PROXY"] = "https://proxy.example.com"
}
```

Đây là host minh họa; chỉ dùng nếu tổ chức có proxy thực và xử lý `NO_PROXY`/certificates theo chính sách. Tránh đưa proxy password trong URL vào build script và log.

### 13.4. Chỉ định buildpacks cụ thể

Thông thường **không cần** chỉnh `buildpacks`: builder đã có thứ tự phát hiện/những buildpack được chọn phù hợp. Nếu cần thêm custom buildpack, task cho cấu hình danh sách. Khi chỉ định `buildpacks`, **chỉ những buildpack được liệt kê sẽ được sử dụng**, có thể vô tình bỏ Java buildpack cần thiết.

Ví dụ khái niệm (chỉ dùng sau khi xác nhận buildpack ID có trong builder):

```groovy
tasks.named('bootBuildImage') {
    buildpacks = ['urn:cnb:builder:paketo-buildpacks/java']
}
```

Không dùng fragment này làm mặc định cho mọi project; ID, order và buildpack dependencies có thể khác giữa các builder/version. Nếu build fails ở detection, khôi phục builder defaults rồi thêm từng customization.

## 14. Native image là nhánh khác, không phải hành vi mặc định

Theo Spring Boot 3.5, khi project áp dụng **GraalVM Native Build Tools plugin**, Spring Boot Gradle plugin có thể cấu hình AOT/native image tasks, và `bootBuildImage` tạo **native image container** thay vì JVM image thông thường. Đây là nhánh cần GraalVM/native buildpacks và tương thích thư viện; có thể mất thời gian build và tài nguyên đáng kể hơn.

**Không nhầm:** đặt `BP_JVM_VERSION=17` chỉ chọn JVM cho **JVM application image**; nó **không** tự làm project thành GraalVM native image. Cũng không cần apply native tools plugin chỉ để container Spring Boot khởi động nhanh trong mọi trường hợp.

Nếu tổ chức chọn native image, phải có bài kiểm thử riêng cho reflection, proxies, serialization, runtime hints, profiles, AOT, binary architecture và startup/heap; không copy toàn bộ workflow JVM trong bài này rồi mặc định native image behavior tương đương.

## 15. Cách kiểm tra image metadata, logs và cache

### 15.1. Kiểm tra container image sau build

```bash
docker image ls
docker image inspect docker.io/library/cnb-demo:0.1.0-SNAPSHOT
docker history docker.io/library/cnb-demo:0.1.0-SNAPSHOT
```

Lệnh `inspect` cho bạn các thuộc tính như architecture, labels, exposed ports hoặc config của image thực tế; **không nên dựa vào một vị trí label cố định** mà chưa xem builder/plugin version. `docker history` hiển thị lịch sử layer, nhưng không phải một báo cáo kiểm thử bảo mật hoặc toàn bộ SBOM. Với CNB, có các metadata/labels để công cụ đọc, nhưng field cụ thể có thể khác theo builder và lifecycle version.

### 15.2. Debug task Gradle và builder

```bash
# Xem task có tồn tại và dependency graph mà không build image
./gradlew tasks --all
./gradlew bootBuildImage --dry-run

# Log chi tiết nếu tạo image thất bại
./gradlew bootBuildImage --info --stacktrace
```

`--dry-run` cho thấy những task Gradle sẽ được lên lịch, **không chứng minh Docker daemon hoặc CNB builder sẽ build image thành công**. `--info`/`--stacktrace` có thể lộ paths, registry hostnames hoặc metadata nội bộ; xem lại trước khi đăng công khai.

Bạn có thể bật `verboseLogging` ở task để đọc thêm log builder nếu cần, nhưng không để log chi tiết chứa credentials trong public CI artifacts.

### 15.3. Buildpack cache hit khác Gradle cache hit

Khi source thay đổi:

- `compileJava`/`bootJar` có thể chạy lại, vì application classes đổi.
- Buildpacks có thể vẫn reuse runtime/dependency layers và cache volumes.
- Image digest/tag mới phản ánh nội dung application mới.
- Không kết luận cache hỏng chỉ vì bước compile phải chạy; source code thay đổi thì compile là việc hợp lý.

Nếu image tag đổi ở mỗi build, default cache volume names có thể đổi theo, làm hit rate thấp hơn. Có thể đặt `buildCache`/`launchCache` ổn định ở mục 10 khi đo được lợi ích. Nếu base/builder image có security update, cache cần invalidate tương ứng để áp dụng bản vá.

## 16. Bảng lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `Task 'bootBuildImage' not found` | Chưa áp dụng `org.springframework.boot` và `java`/`war` đúng module, hoặc gọi nhầm root | Kiểm tra `plugins`, `./gradlew tasks --all`, chọn `:app:bootBuildImage` |
| `Cannot connect to Docker daemon` | Docker Engine tắt, socket/permissions/context sai | `docker version`, `docker info`, Docker context, quyền socket |
| Buildpack pull lỗi TLS/proxy | Docker daemon/builder container không truy cập registry/proxy, chứng chỉ không tin cậy | Kiểm tra Docker proxy/certificates và `HTTP_PROXY`/`HTTPS_PROXY` builder |
| `manifest unknown` khi pull builder/run image | Tên/tag image sai hoặc đã bị xóa | Xem builder/run image đúng theo Spring Boot version, pin release |
| `no matching manifest for linux/arm64` | Image không hỗ trợ architecture được chọn | Chọn builder có platform tương ứng hoặc thay architecture build/deploy có kiểm soát |
| `buildpack detection failed` | Artifact không phải executable archive phù hợp hoặc custom buildpacks loại mất Java buildpack | Kiểm tra `bootJar`/`bootWar`, builder mặc định, restore buildpacks |
| `UnsupportedClassVersionError` khi container chạy | Compile target Java cao hơn JVM runtime do buildpack chọn | Đồng bộ toolchain, `targetCompatibility`, `BP_JVM_VERSION` |
| `/bin/sh: not found` trong container | Tiny run image không có shell | Không dựa vào shell; dùng builder/run pair có shell nếu bắt buộc |
| `docker run image` báo image not found | Build bị fail, tag khác hoặc Docker context khác | Đọc task output `imageName`, inspect đúng daemon/tag |
| Container chạy nhưng `curl /hello` trả 404 | Sai port/context path hoặc chạy nhầm image version | `docker logs`, `docker inspect`, kiểm tra controller và routing |
| `docker run -p 8080:8080` báo port in use | Host port đã được process khác bind | Dừng process cũ hoặc dùng `-p 8081:8080` |
| `--publishImage` trả `401` hoặc `denied` | Chưa đăng nhập đúng registry hoặc thiếu quyền push repository | Dùng Docker credentials/`docker.publishRegistry`, kiểm tra namespace |
| Image bị đẩy nhầm Docker Hub | `imageName` không chỉ định registry host | Dùng fully qualified `registry.example.com/team/app:tag` |
| Cache volumes quá nhiều, build chậm | imageName/tag đổi liên tục hoặc daemon mới mỗi job | Xem cache policies, đặt volume name ổn định khi phù hợp |
| Image khác digest dù source không đổi | Builder/run image latest đổi, timestamps, JDK/dependencies hoặc build inputs khác | Pin builder/run image, dependency lock, createdDate/reproducibility |
| Native image chậm hoặc fail | Apply GraalVM native tools/plugin, thiếu hints/toolchain | Tách workflow native, profile/compatibility test riêng |
| Gradle test xanh nhưng container startup fail | Chỉ chạy unit tests, chưa smoke test đúng image | Thêm `docker run` + readiness + API smoke test |
| CI không có Docker daemon | Runner chỉ có CLI hoặc bị chặn socket | Cấp builder/daemon service được phép hoặc thay kiến trúc pipeline |
| Code đổi nhưng container cũ vẫn trả response cũ | Container được tạo trước khi image tag cập nhật | Stop/recreate container; kiểm tra digest mới |

**Nguyên tắc debug:** trước hết xem **Gradle task failure**, sau đó Docker daemon/context, tiếp theo builder/detection/buildpack logs và cuối cùng application startup. Không quy mọi `java.lang.ClassNotFoundException` trong app cho Docker engine nếu Boot archive/classpath vốn đã lỗi.

## 17. Bài thực hành xác minh và checklist

### 17.1. Thí nghiệm A — build image và chạy ứng dụng

- Tạo source Java và build file ở mục 5.
- Chạy `./gradlew clean test bootBuildImage`; xác nhận tất cả task thành công.
- Chạy `docker image inspect docker.io/library/cnb-demo:0.1.0-SNAPSHOT` để chứng minh image tồn tại.
- Chạy container, gọi `GET /hello`. Response body là `Hello from CNB image`.

### 17.2. Thí nghiệm B — đổi source

Đổi `HelloController.hello()` trả `"CNB release two"` và đổi expected string trong test tương ứng. Chạy lại `./gradlew test bootBuildImage`. Buildpack có thể reuse các dependency/Java layers nhưng application content phải đổi. Tạo **container mới** từ image vừa build, kiểm tra response mới.

Không chỉ nhìn `BUILD SUCCESSFUL` để đo cache: một image với Java code cũ vẫn có thể chạy được. Dùng response và image digest/created metadata để xác định bản đang chạy.

### 17.3. Thí nghiệm C — nâng Java/đổi builder có chủ đích

Chỉ thực hiện trên branch thử nghiệm: đổi `BP_JVM_VERSION` thành version mà builder hỗ trợ và **đồng bộ toolchain/source compatibility**; xem Java runtime được buildpack chọn. Nếu chỉ đổi runtime xuống thấp hơn bytecode đã compile, lỗi compatibility là đúng.

Đổi builder tag/digest cũng có thể khiến cache invalidation và base image khác. Sau thí nghiệm, khôi phục version/builder được dự án hỗ trợ và chạy lại smoke test.

### 17.4. Thí nghiệm D — publish an toàn

Với registry thử nghiệm thật và credentials đã cấp, đặt `--imageName=registry...` và `--publishImage`. Dùng máy/daemon khác pull image, inspect digest rồi chạy smoke test. Ghi release record. **Không publish một image chỉ có tag `latest` lên namespace công khai nếu chưa được phép.**

### 17.5. Checklist trước khi đưa vào CI production

- [ ] Gradle Wrapper, Java 17 toolchain và Spring Boot plugin version được quản lý.
- [ ] `bootBuildImage` tồn tại đúng module, build thành công với Docker daemon đang chạy.
- [ ] Project dùng executable JAR/WAR hợp lệ; `bootBuildImage` không bị nhầm với `bootRun`.
- [ ] Unit tests/quality gate chạy trước khi publish, không mặc định `bootBuildImage` sẽ làm.
- [ ] `imageName`, registry host, namespace và tag phản ánh release; có đường dẫn digest để truy vết.
- [ ] Builder và run image tương thích, kiến trúc image đúng platform đích.
- [ ] Java compile target và Paketo `BP_JVM_VERSION` đồng bộ.
- [ ] Tiny run image có đủ system libraries; không phụ thuộc shell nếu không có.
- [ ] Buildpack cache volumes được quản lý phù hợp, tránh để `cleanCache` bật thường trực.
- [ ] Runtime environment variables/secret được cấp khi deploy, không nhúng vào buildpack image.
- [ ] Docker login/registry credentials không xuất hiện trong Git repository hoặc public logs.
- [ ] CI chạy thử container từ **đúng image đã kiểm tra**, có readiness polling/timeout.
- [ ] Image được scan, SBOM/attestation/signature theo chính sách bảo mật của tổ chức.
- [ ] Không coi mutable `latest` tag là bằng chứng duy nhất của bản đã triển khai.
- [ ] Đã biết cách đọc `bootBuildImage --info`, `docker info` và CNB error logs.
- [ ] Có phương án rollout/rollback bằng image digest hoặc release tag ổn định.

### Tài liệu chính thức

- [Spring Boot 3.5 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html)
- [Spring Boot 3.5 — Container Images với Cloud Native Buildpacks](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/cloud-native-buildpacks.html)
- [Spring Boot 3.5 — Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Cloud Native Buildpacks — Documentation](https://buildpacks.io/docs/)
- [Cloud Native Buildpacks — Specification](https://github.com/buildpacks/spec)
- [Paketo Buildpacks — Java](https://paketo.io/docs/howto/java/)
- [Docker Docs — CLI Reference](https://docs.docker.com/reference/cli/docker/)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)

**Ghi nhớ:** `./gradlew bootBuildImage` là con đường Spring Boot + Gradle trực tiếp tạo **OCI image bằng CNB**, không cần Dockerfile nhưng **cần Docker daemon** và builder/run images tương thích. Hãy kiểm tra image bằng `docker image inspect`, chạy container thật, gọi endpoint, kiểm soát Java version/caching và chỉ dùng `--publishImage` khi đã có image name, registry credentials và quality gate đúng.
