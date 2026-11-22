# Cấu hình tên image, tag, builder, run image và pull policy với Cloud Native Buildpacks

Spring Boot hỗ trợ đóng gói ứng dụng thành **OCI container image** bằng Maven `spring-boot:build-image` hoặc Gradle `bootBuildImage` thông qua **Cloud Native Buildpacks (CNB)** mà không cần tự viết Dockerfile. Tuy nhiên, cùng một project có thể tạo image dưới tên sai, gắn tag không thể truy vết, lấy builder/run image cũ do cache, kéo image ngoài ý muốn hoặc không push được do nhầm Docker daemon với registry.

Bài này tập trung vào **năm khái niệm chính**: **image name**, **tag**, **builder**, **run image** và **pull policy**; giải thích giá trị mặc định, cách cấu hình trong Maven/Gradle, khác biệt giữa build và publish, cách kiểm chứng Docker image thật, cùng những rủi ro về security và reproducibility. Ví dụ chọn **Spring Boot 3.3.13, Java 17** để dùng cú pháp nhất quán. Đây là phiên bản minh họa, không phải tuyên bố về phiên bản mới nhất hoặc còn được hỗ trợ; khi áp dụng thực tế phải kiểm tra tài liệu đúng version dự án.

## 1. Ba loại image trong một lần build CNB

| Image | Vai trò | Khi nào được dùng? |
| --- | --- | --- |
| **Builder image** | Chứa CNB buildpacks, lifecycle và metadata để build ứng dụng | Build time |
| **Run image** | Cung cấp launch/base operating-system layers cho ứng dụng đã build | Runtime base |
| **Application image** | Sản phẩm OCI cuối, có tên/tag/digest để chạy hoặc phát hành | Output và deploy |

Luồng:

```text
Java source + Maven/Gradle
           |
           v
   executable JAR/WAR
           |
           v
 builder image + buildpacks ---------+
           |                        |
           v                        v
      CNB lifecycle             run image
           |                        |
           +-------------+----------+
                         |
                         v
           application image :1.0.0
                         |
                   +-----+------+
                   |            |
                docker run    registry push
```

**Builder không phải output image.** Đổi image name không đổi builder. **Run image không phải lệnh `docker run`** mà là base image của kết quả. Một build dùng run image không tương thích với builder có thể thất bại dù Java code chạy trong IDE.

## 2. Tên image, tag và digest

Tên tham chiếu OCI thường có dạng:

```text
[registry-host[:port]/][namespace/]repository[:tag][@digest]
```

Ví dụ:

```text
image-config-demo:1.0.0
docker.io/library/image-config-demo:1.0.0
docker.io/acme/image-config-demo:dev
registry.example.invalid/team/image-config-demo:1.0.0
registry.example.invalid/team/image-config-demo:git-a1b2c3d
registry.example.invalid/team/image-config-demo@sha256:<real-digest>
```

`registry.example.invalid` và `acme` là ví dụ, không phải registry/tài khoản thật. Phần `<real-digest>` là placeholder biểu thị digest thực sự cần lấy từ registry sau khi publish.

- **Registry hostname** quyết định máy chủ lưu image từ xa.
- **Repository** quyết định namespace và tên image.
- **Tag** như `dev`, `1.0.0`, `latest` là nhãn có thể bị chuyển sang image mới nếu registry cho phép overwrite.
- **Digest** tham chiếu theo nội dung OCI manifest, thích hợp để triển khai chính xác artifact đã kiểm thử.

Nếu không khai báo tag, Docker image reference thông thường ngầm dùng `latest`. **Tag không phải checksum và không tự đảm bảo bất biến.** `docker tag` tạo thêm reference local đến cùng image; không build lại cũng không push image.

## 3. Mặc định của Spring Boot 3.3.13

Theo tài liệu plugin Spring Boot nhánh 3.3:

| Mục | Maven Plugin | Gradle Plugin |
| --- | --- | --- |
| Output image name | `docker.io/library/${project.artifactId}:${project.version}` | `docker.io/library/${project.name}:${project.version}` |
| Builder (JVM thông thường) | `paketobuildpacks/builder-jammy-base:latest` | `paketobuildpacks/builder-jammy-base:latest` |
| Run image | Lấy theo metadata builder nếu không override | Lấy theo metadata builder nếu không override |
| Pull policy | `ALWAYS` | `ALWAYS` |
| Publish | `false` | `false` |

Spring Boot Gradle có ngoại lệ khi áp dụng GraalVM Native Image plugin; ví dụ này **không** dùng native image. Defaults có thể thay đổi qua phiên bản, nên không dùng tài liệu của nhánh Boot mới để kết luận default của Boot 3.3.

Đặc biệt, `latest` của **builder** là tag riêng của repository builder, không liên quan `latest` của **application**. Hai lượt build dùng builder `latest` tại hai thời điểm khác nhau có thể nhận nội dung khác nhau.

## 4. Bảng ánh xạ cấu hình Maven ↔ Gradle

| Ý định | Maven `spring-boot:build-image` | Gradle `bootBuildImage` |
| --- | --- | --- |
| Tên/tag chính | `<image><name>...` | `imageName` |
| CNB builder | `<image><builder>...` | `builder` |
| Launch/run image | `<image><runImage>...` | `runImage` |
| Khi nào pull builder/run | `<image><pullPolicy>...` | `pullPolicy` |
| Buildpack variables | `<image><env>...` | `environment` |
| Publish output | `<image><publish>...` | `publish` |
| Additional tags | Có thể thêm qua Docker `tag` hoặc cấu hình theo API plugin cụ thể | `tags` list |

Giá trị `pullPolicy` chỉ có ba enum trong Spring Boot 3.3: **`ALWAYS`, `IF_NOT_PRESENT` và `NEVER`**.

**Cẩn thận:** Maven XML field là `<name>` nhưng Maven CLI property lại gọi `spring-boot.build-image.imageName`. Gradle task gọi `imageName` ở cả build script và `--imageName` command-line option.

## 5. Project Java 17 để kiểm tra image

Chọn Maven hoặc Gradle, dùng chung ba file:

```text
image-config-demo/
├── pom.xml                          # Maven
├── settings.gradle                   # Gradle (thay thế Maven)
├── build.gradle                      # Gradle (thay thế Maven)
└── src/
    ├── main/java/com/example/image/
    │   ├── ImageConfigApplication.java
    │   └── StatusController.java
    └── test/java/com/example/image/
        └── StatusControllerTest.java
```

`src/main/java/com/example/image/ImageConfigApplication.java`:

```java
package com.example.image;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImageConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImageConfigApplication.class, args);
    }
}
```

`src/main/java/com/example/image/StatusController.java`:

```java
package com.example.image;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/status")
    public String status() {
        return "image-config-ok";
    }
}
```

`src/test/java/com/example/image/StatusControllerTest.java`:

```java
package com.example.image;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class StatusControllerTest {
    @Test
    void returnsExpectedText() {
        assertEquals("image-config-ok", new StatusController().status());
    }
}
```

Các file có package/path khớp và hợp lệ với Java 17. Unit test kiểm tra logic endpoint **không cần Spring context**. Khi chạy application image có embedded server trên port 8080, HTTP `GET /status` có body chính xác:

```text
image-config-ok
```

Đó là HTTP body, không phải tất cả console log. Smoke test thật trên container sẽ kiểm tra packaging/launch.

## 6. Maven POM hoàn chỉnh: image name, builder, run image, pull policy

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>image-config-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <image>
                        <name>docker.io/library/image-config-demo:${project.version}</name>
                        <builder>paketobuildpacks/builder-jammy-base:latest</builder>
                        <runImage>paketobuildpacks/run-jammy-base:latest</runImage>
                        <pullPolicy>IF_NOT_PRESENT</pullPolicy>
                        <publish>false</publish>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là một POM đầy đủ, không cần tạo file phụ. Các mục quan trọng:
- `<name>...:${project.version}</name>` tạo output image chính `docker.io/library/image-config-demo:1.0.0`.
- `builder` chọn Paketo Jammy Base CNB builder.
- `runImage` minh họa override về Paketo Jammy Base run image, phù hợp họ stack; trên dự án thật cần kiểm tra run images trong builder metadata.
- `pullPolicy=IF_NOT_PRESENT` dùng local builder/run images nếu đã có trên Docker daemon.
- `publish=false` **chỉ build local**, không push.
- `BP_JVM_VERSION=17` yêu cầu Paketo Java buildpack chọn runtime major 17 khi khả dụng.

**Có thể bỏ hẳn `<runImage>`** để builder tự chọn run image được khai báo trong metadata — cách ít lỗi hơn nếu chưa có yêu cầu cụ thể. `latest` ở builder/run image là mutable; bài dùng để thực hành, không khuyến nghị release production không pin.

## 7. Maven: build image và chạy smoke test

Điều kiện cần:
- JDK 17 và Maven Wrapper hoặc Maven tương thích.
- Docker daemon chạy được, `docker info` thành công.
- Có network/registry auth đủ để lấy builder, run image và artifacts của buildpacks lần đầu.
- Ứng dụng có quyền dùng Docker socket/daemon và đủ disk.

Lệnh từ root project:

```bash
java -version
docker version
docker info
./mvnw clean verify
./mvnw spring-boot:build-image
```

Với PowerShell dùng `.\mvnw.cmd`; nếu không có Maven Wrapper thì dùng `mvn`. Goal `spring-boot:build-image` bảo đảm phase package cần thiết được chạy trước khi sinh OCI image.

Kiểm tra:

```bash
docker image ls image-config-demo
docker image inspect docker.io/library/image-config-demo:1.0.0
docker image inspect docker.io/library/image-config-demo:1.0.0 \
    --format '{{.Id}}'
```

Chạy container:

```bash
docker run --rm -p 8080:8080 \
    docker.io/library/image-config-demo:1.0.0
```

Mở terminal thứ hai:

```bash
curl -fsS http://localhost:8080/status
```

Kỳ vọng:

```text
image-config-ok
```

Dừng container bằng Ctrl+C. Nếu host port 8080 bận, chạy `-p 8091:8080` và gọi `localhost:8091/status`. `docker image inspect` chứng minh image có trên Docker daemon hiện tại, **không** chứng minh đã được push tới registry.

## 8. Maven CLI override các thuộc tính

Spring Boot Maven Plugin 3.3 hỗ trợ user properties:

```bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=image-config-demo:trial \
  -Dspring-boot.build-image.builder=paketobuildpacks/builder-jammy-base:latest \
  -Dspring-boot.build-image.runImage=paketobuildpacks/run-jammy-base:latest \
  -Dspring-boot.build-image.pullPolicy=ALWAYS
```

Bash dùng `\` để nối dòng; PowerShell nên dùng một dòng hoặc backtick của PowerShell. Các options đúng là:
- `spring-boot.build-image.imageName`: tên/tag output.
- `spring-boot.build-image.builder`: CNB builder.
- `spring-boot.build-image.runImage`: run image.
- `spring-boot.build-image.pullPolicy`: `ALWAYS` / `IF_NOT_PRESENT` / `NEVER`.
- `spring-boot.build-image.publish`: bật/tắt push (đừng bật khi chỉ thực hành).

**Phân biệt:** XML là `<image><name>` còn CLI là `imageName`. Nếu project không kế thừa Spring Boot starter parent, chỉ import BOM chưa đủ để quản lý goal/execution và plugin version; cấu hình Maven plugin riêng cho đúng.

## 9. Maven `build-image` và `build-image-no-fork`

Trong Spring Boot 3.3:
- `spring-boot:build-image` phù hợp **gọi trực tiếp trên command line**; nó đảm bảo package lifecycle đã chạy.
- `spring-boot:build-image-no-fork` thích hợp khi **bind vào Maven lifecycle**, tránh fork package lần nữa.

Ví dụ **đoạn thêm vào declaration Spring Boot Maven plugin đang có** nếu muốn package cũng tạo image:

```xml
<executions>
    <execution>
        <id>package-image</id>
        <goals>
            <goal>build-image-no-fork</goal>
        </goals>
    </execution>
</executions>
```

Không chép đoạn này như POM độc lập và không thêm plugin declaration trùng. Việc bind image build vào mọi lần `mvn package` sẽ làm những job chỉ chạy unit tests phụ thuộc Docker daemon/registry, nên release pipeline thường chạy image build như bước riêng.

## 10. Gradle Groovy DSL đầy đủ với `bootBuildImage`

`settings.gradle`:

```groovy
rootProject.name = 'image-config-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.image.ImageConfigApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = "docker.io/library/${project.name}:${project.version}"
    builder = 'paketobuildpacks/builder-jammy-base:latest'
    runImage = 'paketobuildpacks/run-jammy-base:latest'
    pullPolicy = 'IF_NOT_PRESENT'
    environment['BP_JVM_VERSION'] = '17'
    tags.set(['docker.io/library/image-config-demo:dev'])
    publish = false
}
```

`bootBuildImage` được Spring Boot plugin tạo khi Java hoặc War plugin được áp dụng, dùng `bootJar`/`bootWar` làm nguồn. Task này thuộc module ứng dụng; nếu dự án nhiều module, hãy chạy đúng project path, không chạy build image cho library không có main class.

`imageName` chọn tag chính `1.0.0`. `tags.set(...)` bổ sung một full reference `:dev` trỏ **cùng content image**, không tạo build thứ hai. `environment` truyền build-time environment cho builder, còn `publish=false` ngăn push.

Chạy:

```bash
./gradlew clean test bootBuildImage
docker image inspect docker.io/library/image-config-demo:1.0.0
docker image inspect docker.io/library/image-config-demo:dev
```

PowerShell dùng `.\gradlew.bat`. Nếu cả hai tags trả về cùng image ID, chúng là hai references tới cùng image local.

## 11. Gradle Kotlin DSL tương đương

Nếu dùng `build.gradle.kts`, ví dụ **file độc lập thay cho Groovy build.gradle**:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
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

springBoot {
    mainClass.set("com.example.image.ImageConfigApplication")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("docker.io/library/${project.name}:${project.version}")
    builder.set("paketobuildpacks/builder-jammy-base:latest")
    runImage.set("paketobuildpacks/run-jammy-base:latest")
    setPullPolicy("IF_NOT_PRESENT")
    environment.put("BP_JVM_VERSION", "17")
    tags.set(listOf("docker.io/library/image-config-demo:dev"))
    publish.set(false)
}
```

`settings.gradle.kts`:

```kotlin
rootProject.name = "image-config-demo"
```

`setPullPolicy("IF_NOT_PRESENT")` là method nhận chuỗi được `BootBuildImage` Spring Boot 3.3 cung cấp; các fields khác là Gradle Property APIs như `imageName.set`, `builder.set` và `tags.set`. Đừng trộn cú pháp Groovy và Kotlin trong cùng file.

## 12. Gradle task options

Có thể thử đổi tên image/builder mà không sửa build script:

```bash
./gradlew bootBuildImage \
  --imageName=image-config-demo:trial \
  --builder=paketobuildpacks/builder-jammy-base:latest \
  --runImage=paketobuildpacks/run-jammy-base:latest \
  --pullPolicy=ALWAYS
```

Các `--...` là **task options** của Gradle, khác các Maven `-Dspring-boot.build-image...`. Kiểm tra options của version đang dùng:

```bash
./gradlew help --task bootBuildImage
```

Không mặc nhiên giả định có CLI `--tags` chỉ vì `tags` là task property. Muốn thêm tag, đặt `tags.set(...)` trong script, truyền Gradle project property được kiểm tra hợp lệ hoặc dùng `docker tag` sau build. Option `--publishImage` có thể bật publish; không sử dụng trong bài demo local.

## 13. Builder image: lựa chọn theo stack và buildpacks

Tài liệu Spring Boot 3.3 dùng `paketobuildpacks/builder-jammy-base:latest` cho JVM build thông thường. Khi chọn builder khác, cần kiểm tra:
- Có Java buildpacks hỗ trợ JDK 17 và Spring Boot executable archive không.
- Builder OS/stack tương thích với run image định sử dụng không.
- Có hỗ trợ kiến trúc CPU của build daemon và target platform không.
- Có các hệ thống thư viện cần thiết cho app native dependencies không.
- Buildpacks/lifecycle versions có nằm trong policy bảo mật và hỗ trợ không.
- Registry nguồn có đáng tin, builder tag/digest có bị thay thế không.
- CI có quyền pull builder/run image và tài nguyên để chạy builder container không.

Nếu đã cài **Pack CLI**, có thể xem metadata builder:

```bash
pack builder inspect paketobuildpacks/builder-jammy-base:latest
```

Pack CLI không bắt buộc để gọi `bootBuildImage`. Nếu image có trên Docker daemon, `docker image inspect` cho metadata local:

```bash
docker image inspect paketobuildpacks/builder-jammy-base:latest
```

Tên `base` hoặc `tiny` không tự chứng minh phù hợp cho mọi ứng dụng. Một builder nhỏ nhưng run image thiếu font, CA certificate hoặc system library có thể khiến app runtime lỗi.

## 14. Run image: mặc định theo builder metadata là lựa chọn an toàn

Không set `runImage` thì Maven/Gradle Spring Boot 3.3 **dùng run image được builder metadata chỉ định**. Điều này giảm nguy cơ ghép một base image không tương thích.

Một cặp ví dụ trong họ Paketo Jammy Base:
- Builder `paketobuildpacks/builder-jammy-base:latest`.
- Run image `paketobuildpacks/run-jammy-base:latest`.

Nếu không có yêu cầu override:
- **Maven:** bỏ hẳn phần tử `<runImage>` khỏi `<image>`.
- **Gradle:** bỏ assignment `runImage`.

Override run image thường chỉ cần khi dùng private registry mirror, policy cập nhật OS security, pin digest hoặc yêu cầu custom compatible base. Trước khi override, kiểm tra stack ID và run image trong metadata builder đang chọn. **Không ghép Jammy builder với run image Alpine/musl hay stack khác chỉ vì cả hai hỗ trợ Java 17**.

Run image là nền runtime, **không cần** có Maven, Gradle, JDK compiler hoặc tất cả buildpacks bên trong. Nếu app cần native libs, kiểm tra chúng trong run image thực sự, không chỉ trong builder.

## 15. Ba pull policies và ý nghĩa thật

`pullPolicy` của `build-image` ảnh hưởng **builder/run images lúc build**, không ảnh hưởng image của app lúc deploy.

| Giá trị | Chính sách | Khi dùng | Rủi ro |
| --- | --- | --- | --- |
| **`ALWAYS`** | Kiểm tra/pull builder và run image theo registry cho mỗi build | CI cập nhật base images thường xuyên | Tag mutable `latest` có thể đổi, cần mạng |
| **`IF_NOT_PRESENT`** | Dùng image đã có local, chỉ pull nếu chưa có | Developer có cache hoặc CI preloaded base images | Hai daemon dùng cùng tag nhưng nội dung khác |
| **`NEVER`** | Không pull builder/run image từ registry | Môi trường đã preseed đủ images | Thiếu local image thì build fail; dependency sources khác có thể cần mạng |

**`ALWAYS` không tự đảm bảo reproducibility**, còn `IF_NOT_PRESENT` không tự đảm bảo security updates. `NEVER` không làm toàn bộ build offline: Maven/Gradle dependency downloads và các artifact do buildpacks tải vẫn có thể yêu cầu Internet/mirror.

Đừng nhầm với Kubernetes `imagePullPolicy`:
- Spring Boot: `IF_NOT_PRESENT` trong Maven/Gradle build.
- Kubernetes: `IfNotPresent` trong Pod spec, quyết định pull **application image tại node runtime**.

## 16. Docker run và Kubernetes là những thời điểm khác

```text
Spring Boot build-image:
pullPolicy = IF_NOT_PRESENT
    -> chỉ định pull builder/run images khi build.

docker run image-config-demo:1.0.0
    -> Docker daemon chạy application image có sẵn,
       có thể lấy từ registry theo hành vi Docker.

Kubernetes:
spec.containers[].imagePullPolicy = IfNotPresent
    -> kubelet quyết định pull application image khi tạo Pod.
```

Một fragment YAML Kubernetes, **chưa phải manifest hoàn chỉnh**:

```yaml
containers:
  - name: image-config-demo
    image: registry.example.invalid/team/image-config-demo:1.0.0
    imagePullPolicy: IfNotPresent
```

Tên registry là giả. Giá trị Kubernetes gồm `Always`, `IfNotPresent`, `Never`. Chúng có kiểu chữ khác `ALWAYS`, `IF_NOT_PRESENT`, `NEVER` của Spring Boot build plugin.

## 17. Một image có thể mang nhiều tags

Trong Gradle 3.3, `bootBuildImage.tags` là danh sách **additional full image references**:

```groovy
tasks.named('bootBuildImage') {
    imageName = "docker.io/library/image-config-demo:${project.version}"
    tags.set([
        'docker.io/library/image-config-demo:dev',
        'docker.io/library/image-config-demo:git-a1b2c3d'
    ])
}
```

Đoạn này ghép vào task đã có; trong file thật chỉ nên quản lý `imageName` và `tags` nhất quán ở một vị trí.

Với Maven, cách đơn giản để thêm local tags sau khi build image chính là `docker tag`:

```bash
docker tag docker.io/library/image-config-demo:1.0.0 \
    docker.io/library/image-config-demo:dev

docker tag docker.io/library/image-config-demo:1.0.0 \
    docker.io/library/image-config-demo:git-a1b2c3d
```

Không đoán cú pháp Maven `<tags>` dựa trên Gradle property khi chưa xác minh API/version plugin thực tế. `docker tag` không tự push. Kiểm tra hai tags trỏ cùng image ID:

```bash
docker image inspect docker.io/library/image-config-demo:dev \
    --format '{{.Id}}'
```

**Những tags khác nhau không tạo hai executable JAR hoặc hai OCI builds khác nhau**. Chúng chỉ là các references đến image đã có, miễn là bạn đang tag cùng một image ID.

## 18. Local image khác push lên registry

Theo mặc định, Spring Boot Maven/Gradle image build dùng `publish=false`. Image được lưu trên Docker daemon kết nối với build tool; **chưa xuất hiện trên registry**.

Muốn publish khi được phê duyệt:
- Maven `<image><publish>true</publish>` hoặc CLI `-Dspring-boot.build-image.publish=true`.
- Gradle `publish.set(true)` hoặc task CLI `--publishImage`.
- Docker CLI `docker push registry/path/image:tag` sau khi đã tạo/tag và có quyền.

Đoạn Maven minh họa, **không dùng registry giả để push**:

```xml
<image>
    <name>registry.example.invalid/team/image-config-demo:${project.version}</name>
    <publish>true</publish>
</image>
```

Phải **gộp** đoạn này vào image block hiện tại chứ không tạo hai `<image>` blocks. Cấu hình registry **trong image name** quyết định đích push; `docker.publishRegistry.url` không tự thay hostname của image name.

### 18.1. Hai loại registry credentials

Spring Boot plugins phân biệt:
- `docker.builderRegistry`: quyền **pull private builder và run image**.
- `docker.publishRegistry`: quyền **push application image** đến registry đích.

Không hardcode password/token thật vào POM, `build.gradle` hay command-line logs. Nên inject bằng CI secret manager và giới hạn quyền theo repository. Việc build local không cần publish credentials trừ khi builder/run images nằm trong private registry.

## 19. Docker daemon và Docker context

Trước khi debug `builder` hoặc `pullPolicy`, kiểm tra:

```bash
docker context show
docker version
docker info
```

Build-image cần Docker daemon. Các môi trường có thể khác nhau về socket/permissions/context:
- `DOCKER_CONFIG` trỏ thư mục cấu hình Docker CLI.
- `DOCKER_CONTEXT` chọn Docker context.
- `DOCKER_HOST` chọn host/socket kết nối.
- `DOCKER_TLS_VERIFY` và `DOCKER_CERT_PATH` dùng cho kết nối TLS khi cần.

**Docker daemon không đồng nghĩa registry.** Image hiện trong `docker image ls` trên remote Docker daemon có thể không hiện trên Docker Desktop local; image local chưa push cũng không tự hiện trên Kubernetes cluster. Không đổi pullPolicy để chữa lỗi `Cannot connect to Docker daemon`; cần sửa daemon/context/permission.

## 20. Tag mutability, cache và reproducibility

Một build có fixed source code vẫn có thể khác nhau vì:
1. Builder `:latest` đổi digest.
2. Run image `:latest` đổi digest.
3. Buildpack/JDK artifacts tải được khác phiên bản.
4. Maven/Gradle dependencies hoặc plugin versions biến động.
5. Docker daemon image cache khác nhau giữa CI runners.
6. Metadata hoặc build timestamp thay đổi.
7. Registry repoint một release tag mutable.

Để phát hành có thể truy vết:
- Pin source commit, JDK, Maven/Gradle Wrapper và Spring Boot plugin.
- Ghi builder/run image IDs/digests, kiểm tra stack/runtime compatibility.
- Dùng immutable release tags hoặc deploy theo manifest digest.
- Lưu SBOM/test reports và checksum/provenance phù hợp.
- Quản lý pull policy theo mục tiêu môi trường, không dùng `NEVER` mãi để né security patches.
- Update base images có kiểm thử, không vô tình dùng local cached builder quá cũ.

Gradle plugin còn có `buildCache`, `launchCache` và `buildWorkspace` thường dùng Docker named volumes; cache name có thể dẫn xuất từ output image name. Khi primary imageName đổi liên tục theo tag, cache reuse có thể bị giảm. `cleanCache` dọn CNB build caches, khác `pullPolicy` chỉ kéo builder/run images.

**Không coi `docker image inspect --format '{{.Id}}'` là registry digest.** Local image ID khác manifest digest nhận được sau publish; muốn deploy đúng content đã duyệt, lấy digest được registry công bố và verify.

## 21. Chọn Java runtime trong Paketo builder

Paketo Java buildpacks nhận biết Java target version và có thể dùng biến:

```text
BP_JVM_VERSION=17
```

Maven đặt trong `<image><env>`:

```xml
<env>
    <BP_JVM_VERSION>17</BP_JVM_VERSION>
</env>
```

Gradle Groovy:

```groovy
tasks.named('bootBuildImage') {
    environment['BP_JVM_VERSION'] = '17'
}
```

Gradle Kotlin:

```kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    environment.put("BP_JVM_VERSION", "17")
}
```

Đây là **các đoạn để ghép vào cấu hình sẵn có**, không là files độc lập. `BP_JVM_VERSION` là buildpack-specific, không đảm bảo mọi builder ngoài Paketo hiểu nó. Đừng nhầm nó với `JAVA_TOOL_OPTIONS` hoặc `BPE_APPEND_JAVA_TOOL_OPTIONS` dành cho JVM runtime flags.

## 22. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Image không có tên/tag mong đợi | Maven/Gradle project version, imageName override khác | Kiểm tra log và `docker image inspect` |
| Maven XML `<imageName>` không có tác dụng | Field POM đúng là `<name>` | Sửa `<image><name>...` |
| Tag bị hiểu là `latest` | Không ghi `:tag` | Ghi explicit version/commit tag |
| `invalid reference format` | Repo name viết hoa hoặc cú pháp reference sai | Sửa lowercase/path/tag |
| `docker run` không tìm thấy image | Image nằm trên Docker daemon khác | Kiểm tra `docker context show` và image list |
| `pullPolicy=NEVER` báo thiếu image | Builder/run image chưa tồn tại local | Pre-pull theo policy hoặc đổi policy |
| `IF_NOT_PRESENT` cho kết quả khác giữa máy | Builder tag mutable và caches khác nhau | Pin builder/run digests |
| `pull access denied` lúc build | Registry private thiếu quyền | `docker.builderRegistry` hoặc auth daemon |
| `unauthorized` khi push | Thiếu quyền publish/namespace sai | `docker.publishRegistry` và đúng image name |
| Stack mismatch | Run image khác họ/stack builder | Dùng builder metadata default hoặc compatible run |
| Image chạy lỗi native libraries | Run image thiếu OS dependencies | Kiểm tra run image, kiến trúc, libc/certs |
| Build báo không có Docker daemon | Docker Engine chưa chạy/context/socket sai | Chữa Docker trước khi đổi builder |
| `BP_JVM_VERSION` không được áp dụng | Builder không dùng Paketo Java buildpack | Đọc logs và builder docs |
| Gradle library không có task `bootBuildImage` | Không áp dụng plugin phù hợp hoặc sai module | Build trên module ứng dụng |
| Pull policy `ALWAYS` vẫn cho byte khác | Builder `latest` được cập nhật | Dùng immutable identifiers |
| `NEVER` nhưng vẫn cần internet | Maven/Gradle hoặc buildpacks tải dependencies | Mirror/cache mọi input nếu cần offline |
| Tag `dev` đã tạo local nhưng registry không thấy | `docker tag` không push | Push/publish khi được phê duyệt |
| Docker/Kubernetes pull hành vi khác build | Nhầm pullPolicy của Spring với `imagePullPolicy` | Cấu hình theo từng tầng |
| Docker build quá chậm dù base đã có | CNB buildCache/Maven downloads khác pull policy | Đọc build logs, phân tích cache layers |
| Container chạy nhưng `/status` báo 404 | Sai class/controller hoặc image được chọn | So sánh source, JAR và image ID |

## 23. Quy trình CI/CD kiểm soát được

Gợi ý trình tự:
1. Build Java 17 và chạy unit/integration tests.
2. Kiểm tra dependency graph và plugin/builder/run-image references.
3. Build image local với `publish=false`.
4. Inspect image ID, tag, runtime metadata và lưu build logs.
5. Chạy container, đợi readiness rồi assert `GET /status` trả `image-config-ok`.
6. Scan image/SBOM, kiểm tra security policy.
7. Tạo version/commit tags và xác nhận cùng image ID.
8. Push qua secret-based registry credentials, lưu manifest digest thực.
9. Deploy bằng immutable tag/digest, kiểm tra health và có rollback reference.

Ví dụ Bash smoke test sau Maven build:

```bash
#!/usr/bin/env bash
set -euo pipefail

./mvnw -B clean verify
./mvnw -B spring-boot:build-image

IMAGE=docker.io/library/image-config-demo:1.0.0
docker image inspect "$IMAGE" >/dev/null

cid=$(docker run -d -p 18080:8080 "$IMAGE")
trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT

for i in $(seq 1 30); do
    if curl -fsS http://localhost:18080/status > response.txt; then
        break
    fi
    sleep 1
done
test "$(cat response.txt)" = "image-config-ok"
```

Đoạn script cần Bash, curl, Docker, Maven Wrapper và port 18080 trống. Nếu app không sẵn sàng, lệnh test fail. Trong CI production cần kiểm soát timeout/readiness và remote Docker daemon network để tránh giả định host localhost luôn là cùng máy.

Với Gradle thay hai dòng Maven bằng `./gradlew clean test bootBuildImage`, giữ các bước inspect/run như nhau. Bài thực hành **không tự push image** vì không có registry và quyền thật của người học.

## 24. Bài tập thực hành

**A. Đổi imageName:** dùng Maven CLI `-Dspring-boot.build-image.imageName=image-config-demo:trial` hoặc Gradle `--imageName=image-config-demo:trial`. Sau build, kiểm tra reference mới và giải thích vì sao builder/run image vẫn như cũ.

**B. Thêm tag:** dùng Gradle `tags.set(...)` hoặc `docker tag` sau Maven build; xác minh hai tags trỏ cùng image ID. Giải thích vì sao thêm tag không tự push.

**C. So sánh pull policies:** trên môi trường thử nghiệm đã có image cache, đổi `ALWAYS` thành `IF_NOT_PRESENT`; xem logs và IDs. Sau đó giải thích tại sao `NEVER` có thể fail khi một base image thiếu.

**D. Run image:** bỏ override `runImage`, để builder metadata quyết định. So sánh với cặp Jammy Base minh họa và xác minh stack compatibility; không tự đổi sang base image không cùng stack.

**E. Release trace:** ghi image version/commit tag và digest sau publish, giải thích vì sao không nên deploy chỉ bằng `latest`.

## 25. Checklist

- [ ] Hiểu builder, run image, application image và trách nhiệm của từng loại.
- [ ] Image name có registry/repository/tag hợp lệ; tránh tag ngầm `latest` cho release.
- [ ] Không nhầm image tag với immutable digest.
- [ ] Maven POM dùng `<image><name>`; Gradle task dùng `imageName`.
- [ ] Maven CLI dùng `-Dspring-boot.build-image.imageName`; Gradle CLI dùng `--imageName`.
- [ ] Builder có Java buildpacks phù hợp JDK/architecture.
- [ ] Run image tương thích builder; biết cách để metadata tự chọn.
- [ ] Biết rõ `ALWAYS`, `IF_NOT_PRESENT`, `NEVER` và phạm vi base image build.
- [ ] Không nhầm `pullPolicy` với Kubernetes `imagePullPolicy`.
- [ ] Không dùng `NEVER` làm lời đảm bảo hoàn toàn offline.
- [ ] Gradle additional tags dùng full references; `docker tag` không push.
- [ ] `publish=false` cho thử nghiệm local, publish khi có registry và quyền thật.
- [ ] Docker daemon/context đúng và image được inspect bằng Docker.
- [ ] Cấu hình Java 17 và `BP_JVM_VERSION` phù hợp Paketo buildpack.
- [ ] Image sau build chạy và `GET /status` trả `image-config-ok`.
- [ ] CI lưu source commit, dependency graph, builder/run digests, output image digest và test results.
- [ ] Có chính sách cập nhật base images, kiểm thử bảo mật và rollback.

**Kết luận:** `name`/`imageName` quyết định tên output; `tags` thêm references; `builder` thực hiện build; `runImage` là nền runtime; `pullPolicy` chỉ kiểm soát pull **builder/run images khi build**. Tag không phải digest, build local không phải publish và CNB pull policy không phải Kubernetes pull policy. Xác minh theo chuỗi **build → inspect → smoke test → publish → kiểm tra digest**.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Maven Plugin Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Spring Boot 3.3 — Maven Image API](https://docs.spring.io/spring-boot/3.3/maven-plugin/api/java/org/springframework/boot/maven/Image.html)
- [Spring Boot 3.3 — Gradle BootBuildImage API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootBuildImage.html)
- [Paketo Buildpacks — Builders Reference](https://paketo.io/docs/reference/builders-reference/)
- [Cloud Native Buildpacks](https://buildpacks.io/docs/)
- [Docker — Image Tag](https://docs.docker.com/reference/cli/docker/image/tag/)
- [Docker — Image Inspect](https://docs.docker.com/reference/cli/docker/image/inspect/)
- [Kubernetes — Container Images](https://kubernetes.io/docs/concepts/containers/images/)