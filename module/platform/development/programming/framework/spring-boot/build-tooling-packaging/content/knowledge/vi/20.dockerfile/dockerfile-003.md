# Tổ chức multi-stage build và tối ưu build context bằng .dockerignore

## 1. Mục tiêu của bài

Khi đóng gói ứng dụng Spring Boot thành Docker image, có hai vấn đề rất dễ bị trộn lẫn:

1. **Multi-stage build** quyết định **những công cụ và file nào xuất hiện trong từng giai đoạn xây image**, đặc biệt tránh đưa JDK, Maven/Gradle cache, mã nguồn và công cụ biên dịch vào runtime image.
2. **`.dockerignore`** quyết định **những file nào từ máy build được đưa vào Docker build context**, giúp giảm dữ liệu phải xử lý/truyền cho builder, hạn chế những file không cần thiết và giảm nguy cơ cache bị invalidated bởi thay đổi ngoài ý muốn.

Hai kỹ thuật bổ sung cho nhau nhưng **không thay thế nhau**. Một Dockerfile đã có hai `FROM` vẫn có thể vô tình gửi hàng GB dữ liệu vào build context nếu ignore rules không hợp lý. Ngược lại, `.dockerignore` có thể rất chặt nhưng runtime image vẫn phình to nếu đưa toàn bộ JDK, source code và build tools vào final stage.

Sau bài này, bạn sẽ biết cách:

- Giải thích và kiểm soát build context từ đối số cuối của `docker build`, không nhầm với `WORKDIR`.
- Viết một `.dockerignore` hợp lý cho Spring Boot Gradle/Maven, không vô tình loại wrapper, POM, build scripts hoặc `src`.
- Tổ chức Dockerfile thành các stage `build`, `extract` (khi cần) và `runtime`, chỉ dùng `COPY --from` để mang artifact cần thiết sang final image.
- Tạo một ứng dụng Spring Boot Java 17 chạy được, build thành executable `bootJar` hoặc Maven `repackage` trong container, chạy bằng image cuối.
- Tận dụng Docker layer cache, BuildKit cache mounts cho Gradle/Maven và, khi phù hợp, Spring Boot layered JAR.
- Phân biệt tối ưu **build context**, **build time**, **final image size**, **image layers**, **runtime security** và **reproducibility**.
- Kiểm tra các lỗi thường gặp: `COPY failed`, Gradle wrapper thiếu, runtime JAR nhầm `-plain.jar`, build cache miss, Dockerfile ignore precedence, secrets leak và multi-module paths.

**Mốc ví dụ:** Java 17 và Spring Boot 3.3.13 để thống nhất cú pháp. Đây là một phiên bản minh họa, không khẳng định là bản mới nhất. Tài liệu Docker hiện hành có thể cập nhật; Docker Engine/BuildKit, Gradle wrapper và plugin thực tế của dự án mới là nguồn xác nhận khi triển khai.

## 2. Hình dung luồng từ host đến container

~~~text
Thư mục dự án trên host
    |
    | docker build -t boot-web:gradle .
    |                            ^
    |                      build context = .
    |
    +-- .dockerignore lọc file đưa vào context
    |
    v
Docker / BuildKit builder
    |
    +-- FROM JDK image AS build
    |     | COPY build scripts / wrapper / src
    |     | RUN gradle hoặc maven test + package
    |     v
    |   app.jar ở filesystem của build stage
    |
    +-- FROM JRE image AS runtime
          | COPY --from=build .../app.jar /app/app.jar
          | USER không phải root
          | ENTRYPOINT java -jar ...
          v
      Final image phục vụ chạy ứng dụng
~~~

Điểm quan trọng:

- `COPY gradlew` hoặc `COPY src` lấy dữ liệu từ **build context**, đã áp dụng `.dockerignore`.
- `COPY --from=build /workspace/build/libs/app.jar ...` lấy dữ liệu từ **filesystem của stage build**, **không** lấy từ build context trên host.
- Không cần gửi thư mục `build/` trên máy lập trình vào context khi chính builder stage sẽ tạo Boot JAR mới.
- Chỉ những gì final stage kế thừa từ base image và các lệnh trong final stage mới trở thành filesystem của runtime image. JDK, Gradle cache và `src` ở stage build không tự đi vào image cuối.

Đây là lý do multi-stage rất phù hợp với ứng dụng Java/Spring Boot: cần **JDK + build tool** để biên dịch, nhưng thường chỉ cần **JRE phù hợp + executable artifact** khi chạy.

## 3. “Build context” thực sự là gì?

Khi gõ:

~~~bash
docker build -t boot-web:gradle .
~~~

dấu `.` cuối lệnh chọn **current directory làm filesystem build context**. Với Dockerfile:

~~~dockerfile
WORKDIR /workspace
COPY src/ src/
~~~

Docker đọc `src/` **tương đối với build context**, rồi copy nó vào `/workspace/src` trong stage hiện tại. `WORKDIR` không quyết định thư mục nào trên host được gửi cho Docker.

Hai lệnh này có thể dùng **hai context khác nhau**:

~~~bash
docker build -f Dockerfile .
docker build -f docker/Dockerfile .
~~~

Chúng đều dùng context `.`; chỉ khác đường dẫn Dockerfile. Ngược lại:

~~~bash
docker build -f docker/Dockerfile docker/
~~~

sử dụng context `docker/`. Nếu `src/` và `build.gradle` nằm ở root dự án bên ngoài `docker/`, `COPY src/ src/` sẽ báo không tìm thấy nguồn. Không thể dùng `COPY ../src` để thoát khỏi context như một cơ chế thay thế; Docker giới hạn file nguồn theo context đã chọn.

### 3.1. Vì sao context lớn gây hại?

Một Java repository có thể chứa:

~~~text
.git/                       lịch sử Git có thể rất lớn
.gradle/                    metadata/cache Gradle của project
build/                      compiled classes, reports, JAR cũ
target/                     output Maven
.idea/, .vscode/            dữ liệu IDE
node_modules/               dependencies frontend
logs/, reports/, tmp/       file không cần cho build
.env, *.pem                 cấu hình/khóa nhạy cảm
src/                        mã nguồn ứng dụng
gradle/wrapper/             Gradle wrapper cần cho container build
build.gradle(.kts), pom.xml cấu hình build cần thiết
~~~

Nếu context chứa tất cả, builder có thể phải xử lý/truyền dữ liệu lớn, nhất là khi builder chạy remote. Với Dockerfile dùng `COPY . .`, thay đổi file không liên quan (log, .git, build artifact) còn có thể **invalidate cache** của COPY và các bước phía sau.

BuildKit mới có thể tránh truyền những file không được sử dụng bởi instruction hoặc truyền theo nhu cầu; tuy nhiên vẫn nên **thu hẹp context bằng `.dockerignore`** để giảm rủi ro copy nhầm và giảm các yếu tố gây biến động. Không suy luận kích cỡ context chỉ từ dung lượng toàn bộ project trên disk; hãy xem output `transferring context` khi build.

## 4. `.dockerignore` lọc gì và lọc lúc nào?

Docker tìm `.dockerignore` tại **root của build context**. Những file/path khớp ignore rules bị loại khỏi context trước khi builder sử dụng chúng làm nguồn cho `COPY`/`ADD`.

Ví dụ tại project root:

~~~text
boot-web/
├── .dockerignore
├── Dockerfile
├── settings.gradle
├── build.gradle
├── gradlew
├── gradle/wrapper/
├── src/
├── build/
└── .git/
~~~

Nội dung `.dockerignore` được đề xuất cho **project Spring Boot dùng builder stage tự biên dịch từ source**:

~~~dockerignore
# Version control và cấu hình IDE
.git
.gitignore
.idea
.vscode
*.iml

# Gradle/Maven outputs & local state
.gradle
**/.gradle
build
**/build
target
**/target

# Local cache và front-end dependency nếu không dùng trong image
node_modules
**/node_modules
logs
**/logs
tmp
**/tmp
*.log
*.tmp
.DS_Store

# Secret và dữ liệu máy lập trình: không gửi vào context
.env
.env.*
**/*.pem
**/*.key
**/*.p12
**/*.jks
~~~

**Quan trọng:** file ignore này **không loại** `gradlew`, `gradle/wrapper/`, `settings.gradle`, `build.gradle` hoặc `src`. Nếu Dockerfile cần wrapper, hãy chắc chắn `gradle/wrapper/gradle-wrapper.jar` và `gradle-wrapper.properties` thực sự tồn tại trong context.

Trong dự án sử dụng Maven builder có image chứa sẵn Maven, các file cần có thường chỉ gồm `pom.xml`, `src` và những POM/config khác trong repository. Nếu build qua Maven wrapper `./mvnw`, phải giữ `mvnw` và `.mvn/wrapper/`; không thêm rule `.mvn` vào ignore file khi Dockerfile cần nó.

**Đây là ví dụ cho repository mẫu, không phải danh sách ignore áp dụng máy móc cho mọi app.** Nếu project có frontend/build scripts bên trong `node_modules`, cần thay chiến lược cài dependencies; nếu SSL cert public/test fixture thật sự được compile/test đọc, không loại nó vô điều kiện. Secrets phải được cấp qua cơ chế secret manager/build secret khi cần, không dựa chỉ vào ignore file.

### 4.1. `.dockerignore` không phải `.gitignore`

`.gitignore` kiểm soát Git tracking và `.dockerignore` kiểm soát build context của Docker. Docker không tự kế thừa Git ignore rules khi dùng local filesystem context. Một file đã bị Git ignore vẫn có thể được gửi vào Docker context nếu `.dockerignore` không loại và builder có nhu cầu sử dụng nó.

Ví dụ, build directory `build/` có thể nằm trong `.gitignore` nhưng nếu Dockerfile `COPY . .` và không có `.dockerignore`, Docker vẫn có thể gửi/copy build artifacts.

### 4.2. Pattern syntax quan trọng

Docker `.dockerignore` có quy tắc match riêng dựa trên filepath matching:

- Một dòng là một pattern; dòng bắt đầu bằng `#` ở cột đầu là comment.
- Dấu gạch `/` đầu/cuối path thường được chuẩn hóa trong matching.
- `*` khớp phần filename/path theo rules của matcher, `?` khớp một ký tự.
- `**` là wildcard mở rộng của Docker, có thể khớp **0 hoặc nhiều cấp thư mục**.
- Prefix `!` tạo exception để include lại file/path đã bị ignore.
- **Rule khớp cuối cùng** có thể quyết định file được include hay exclude; thứ tự có ý nghĩa.
- Pattern `.` là trường hợp đặc biệt được Docker bỏ qua vì lý do lịch sử.

Ví dụ:

~~~dockerignore
*.md
!README.md
README-secret.md
~~~

Mục đích: loại Markdown ở root ngoại trừ `README.md`, rồi tiếp tục loại riêng `README-secret.md` nếu nó từng khớp điều kiện include khác. Đừng hiểu đây là cú pháp giống 100% `.gitignore`: Docker có matcher và rule precedence riêng.

Một ví dụ về **thứ tự ngoại lệ**:

~~~dockerignore
*.md
!README*.md
README-internal.md
~~~

Theo thứ tự này, `README-internal.md` bị loại vì dòng cuối khớp. Nếu chuyển `!README*.md` xuống dưới cùng, nó lại có thể được include. Trong repository có cấu trúc sâu, hãy test rules thật thay vì suy luận từ shell globs.

### 4.3. Không exclude thư mục cha rồi mong file con luôn quay lại

Nếu bạn viết:

~~~dockerignore
gradle
!gradle/wrapper/gradle-wrapper.jar
~~~

rồi Dockerfile `COPY gradle/wrapper/ ...`, kết quả có thể không như mong muốn do thư mục cha đã bị loại. Với Gradle wrapper, cách đơn giản nhất là **không ignore `gradle/`**; chỉ exclude đúng local state `.gradle/` (có dấu chấm), để `gradle/wrapper/` được giữ nguyên.

Nếu tổ chức dùng allowlist dạng `**` exclude-all rồi re-include từng file, phải include cả **directory ancestors** và các paths cần thiết, kiểm thử trên cây thư mục thật. Loại build inputs để “làm context nhỏ” sẽ làm Docker build thất bại hoặc, nguy hiểm hơn, build thành công nhưng thiếu resource cần thiết.

### 4.4. Dockerfile-specific ignore file khi có nhiều Dockerfiles

Docker hỗ trợ file riêng đặt **cùng thư mục với Dockerfile** và có tên dạng:

~~~text
docker/
├── build.Dockerfile
├── build.Dockerfile.dockerignore
├── test.Dockerfile
└── test.Dockerfile.dockerignore
~~~

Khi dùng:

~~~bash
docker build -f docker/build.Dockerfile .
docker build -f docker/test.Dockerfile .
~~~

các file ignore theo tên Dockerfile có thể được ưu tiên so với `.dockerignore` ở root context. **File-specific ignore có precedence**, không nên giả định chúng cộng dồn mọi rule tự động. Hãy đọc đúng file có hiệu lực cho từng command.

Tình huống thực tế: runtime Dockerfile chỉ cần JAR đã build, còn test Dockerfile cần cả sources, test fixtures và wrapper. Hai build có input requirements khác nhau nên có thể dùng hai ignore sets khác nhau. Nhưng luôn xác định root context từ đối số cuối của `docker build`, không từ vị trí của Dockerfile.

### 4.5. Có thể loại Dockerfile và .dockerignore khỏi COPY, nhưng Docker vẫn phải đọc chúng

Docker docs cho phép khai báo `Dockerfile` và `.dockerignore` trong ignore rules. Những file này vẫn được gửi ở mức cần thiết để builder xử lý build, **nhưng không thể dùng chúng làm source trong `COPY`/`ADD` hoặc bind mount từ context** theo cách thông thường nếu bị ignore.

Vì vậy không cần đưa bản copy của Dockerfile vào final image. Nếu pipeline thực sự cần Dockerfile làm artifact để audit, hãy xử lý nó ngoài Docker runtime layer hoặc thiết kế ignore/context riêng phù hợp.

## 5. Project thực hành Spring Boot Java 17

Ta tạo một REST API nhỏ, khởi chạy ở port 8080 của container và trả về body:

~~~text
hello-from-container
~~~

Dùng chính source Java cho **cả Gradle và Maven**; chỉ thay build script và Dockerfile tương ứng.

Cấu trúc project Gradle:

~~~text
boot-web/
├── .dockerignore
├── Dockerfile
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
    │   └── java/com/example/docker/
    │       ├── DockerDemoApplication.java
    │       └── HelloController.java
    └── test/
        └── java/com/example/docker/
            └── HelloControllerTest.java
~~~

Dự án có thể được tạo qua Spring Initializr hoặc bằng cách chuẩn bị wrapper theo quy trình Gradle. **Chỉ có `build.gradle` không tự sinh `gradlew`**; nếu thiếu wrapper, hãy tạo khi có Gradle cài sẵn tương thích hoặc lấy từ repository template đã duyệt.

### 5.1. Application main class

Tệp `src/main/java/com/example/docker/DockerDemoApplication.java`:

~~~java
package com.example.docker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DockerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DockerDemoApplication.class, args);
    }
}
~~~

### 5.2. Controller

Tệp `src/main/java/com/example/docker/HelloController.java`:

~~~java
package com.example.docker;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-from-container";
    }
}
~~~

### 5.3. JUnit test để builder stage chạy kiểm chứng

Tệp `src/test/java/com/example/docker/HelloControllerTest.java`:

~~~java
package com.example.docker;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HelloControllerTest {

    @Test
    void returnsExpectedResponse() {
        HelloController controller = new HelloController();
        assertEquals("hello-from-container", controller.hello());
    }
}
~~~

Test này gọi controller Java trực tiếp, không khởi động HTTP server; mục đích là cung cấp một JUnit test **runnable**, đơn giản và không phụ thuộc network/test database. Sau khi image chạy, cần thêm smoke test HTTP để chứng minh server thực sự phục vụ request.

## 6. Cấu hình Gradle Groovy DSL dùng trong Dockerfile

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'boot-web'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

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
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'app.jar'
}
~~~

Tại sao đặt `archiveFileName = 'app.jar'`? Vì Dockerfile sẽ copy **một đường dẫn đầu ra xác định**:

~~~text
/workspace/build/libs/app.jar
~~~

Không dùng `COPY --from=build /workspace/build/libs/*.jar /app/app.jar` khi thư mục có thể chứa `-plain.jar` hoặc nhiều classifier/version khác nhau. Đầu ra cố định giúp image lấy đúng executable Boot archive.

**Cảnh báo:** `bootJar` và `jar` khác nhau. Task `bootJar` đóng runtime dependencies theo Spring Boot executable layout. Task `jar` thường tạo plain JAR; `java -jar` từ plain JAR có thể lỗi do thiếu loader/dependencies. Dockerfile phải dùng artifact của `bootJar`.

### 6.1. Kotlin DSL nếu project dùng `.gradle.kts`

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "boot-web"
~~~

Tệp `build.gradle.kts` tương đương:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

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
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app.jar")
}
~~~

Nếu dùng Kotlin DSL, Dockerfile cần `COPY settings.gradle.kts build.gradle.kts ./` thay cho các file Groovy. **Không để hai bản build.gradle khác DSL rồi mong cả hai được áp dụng nối tiếp.**

Không dùng Java 17 toolchain config làm bằng chứng runtime image chắc chắn có Java: **builder stage** có JDK 17 để biên dịch, **final stage** cần một JRE/JDK riêng phù hợp để chạy artifact.

## 7. Dockerfile multi-stage với Gradle — bản chạy được

Tại root `boot-web`, dùng `Dockerfile` sau cùng với Groovy DSL ở mục 6, file `.dockerignore` ở mục 4 và Java sources ở mục 5:

~~~dockerfile
# syntax=docker/dockerfile:1

# Stage 1: JDK + Gradle wrapper + source => executable Boot JAR
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

# Chỉ copy files cần để Gradle nhận project và tải wrapper/plugin
COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

# Warm configuration/plugin resolution; chưa chắc tải mọi runtime JAR
RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon help

# Source thường đổi hơn build scripts
COPY src/ src/

# Build trong container. BuildKit cache mount không đi vào final image.
RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon test bootJar

# Stage 2: chỉ JRE + artifact cần để chạy
FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=build /workspace/build/libs/app.jar /app/app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là **một Dockerfile hoàn chỉnh** cho project Gradle Groovy đã định nghĩa. Nó dựa vào Docker BuildKit để dùng `RUN --mount=type=cache`. Với Docker hiện đại, BuildKit thường là builder mặc định; nếu môi trường cũ không hỗ trợ cache mount, hãy bật BuildKit hoặc bỏ riêng `--mount` và dùng RUN thường, không tự viết các cờ không tồn tại.

### 7.1. Đọc Dockerfile từng stage

**`FROM eclipse-temurin:17-jdk AS build`:** tạo một builder stage có JDK 17, cần cho Gradle và `javac`. Base image này có kích thước và công cụ lớn hơn JRE; vì nó là intermediate stage, không trở thành runtime image cuối khi ta chỉ copy JAR.

**`WORKDIR /workspace`:** đặt thư mục làm việc trong stage, không thay build context trên host.

**`COPY gradlew` và `COPY gradle/wrapper/`:** mang Gradle wrapper shell script cùng wrapper JAR/properties vào builder. Dockerfile không cần `gradlew.bat` để chạy trên Linux stage.

**`COPY settings.gradle build.gradle ./`:** Gradle biết project name, plugin versions, repositories và dependencies. Vì bước này chạy trước `COPY src`, khi chỉ Java code thay đổi Docker có cơ hội reuse layer dành cho wrapper/configuration, thay vì phải làm lại mọi setup từ đầu.

**`RUN chmod +x gradlew`:** bảo đảm wrapper có quyền execute trong Linux builder; không áp dụng quyền này vào runtime JAR.

**`RUN --mount=type=cache,target=/root/.gradle,sharing=locked ... help`:** cho Gradle wrapper/plugin khởi tạo/configure; cache mount lưu dữ liệu Gradle User Home giữa các build trên cùng builder. Lệnh `help` **không bảo đảm resolve và tải toàn bộ application runtime artifacts**. Khi chạy `test bootJar` sau đó, Gradle tải phần còn thiếu.

**`COPY src/ src/`:** chỉ copy Java source/resources/tests. Đối với một project có code generation, included builds, Gradle version catalogs, custom init scripts, Java resources ngoài `src`, phải thêm những build inputs ấy vào các `COPY` phù hợp; đừng giả định mọi project chỉ cần hai folders.

**`RUN ... test bootJar`:** JUnit tests ở mục 5 được chạy bởi task `test`, sau đó task `bootJar` tạo executable `app.jar`. Nếu test fail, image build fail; không tự đặt `-x test` trong production workflow mà chưa có chính sách khác. Nếu build cần integration tests/Docker-in-Docker, cần thiết kế test stage và CI riêng, không mặc định JUnit test này đại diện toàn bộ test suite.

**`FROM eclipse-temurin:17-jre AS runtime`:** tạo stage runtime từ JRE, không có Gradle/Maven/`javac`/source code mặc định. Đây là khác biệt chính làm final image gọn hơn và giảm attack surface so với image dùng JDK builder làm runtime.

**`COPY --from=build ... app.jar`:** sao chép đúng một artifact giữa stages. Ignore rule `build` ở host **không ảnh hưởng** file mới tạo trong filesystem của build stage.

**`EXPOSE 8080`:** ghi metadata về cổng mà ứng dụng thường lắng nghe; **không tự publish port** ra host. Lệnh `docker run -p 18080:8080` mới ánh xạ port.

**`USER 10001:10001`:** khởi chạy process với UID/GID không phải root. JAR do `COPY` thường có quyền đọc phù hợp; nếu application cần ghi vào filesystem (logs/uploads/temp), phải thiết kế writable mounts/directories/quyền trước, không chuyển sang root vô điều kiện.

**`ENTRYPOINT` exec form:** chạy Java trực tiếp, không qua shell wrapping mặc định. Điều này giúp luồng signal/exit status rõ ràng hơn cho container orchestration.

### 7.2. Nếu dùng Kotlin DSL

Đổi chính dòng:

~~~dockerfile
COPY settings.gradle.kts build.gradle.kts ./
~~~

vào Dockerfile trên, giữ các `COPY gradlew`, `gradle/wrapper` và `COPY src` như cũ. Không thêm cả dòng Groovy và Kotlin nếu thực tế chỉ có một cặp file; Docker sẽ báo `not found` khi file nguồn không tồn tại.

### 7.3. Lệnh build và smoke test

Đứng trong root `boot-web`, có Docker Engine/BuildKit, network truy cập base images và Gradle/Maven repositories:

~~~bash
docker build --progress=plain -t boot-web:gradle .
docker run --rm -p 18080:8080 boot-web:gradle
~~~

Lệnh `docker run` ở foreground giữ ứng dụng web chạy. Trong **terminal khác**:

~~~bash
curl -fsS http://localhost:18080/hello
~~~

HTTP body dự kiến:

~~~text
hello-from-container
~~~

Spring Boot còn in startup logs; controller trả body chuỗi không thêm newline. Dừng container foreground bằng Ctrl+C.

Nếu máy đã dùng port 18080, chọn một host port khác trong `-p` và URL tương ứng. Nếu app có `server.port` custom, thay container port trong mapping cho khớp; `EXPOSE 8080` **không thay** Spring configuration.

### 7.4. Phân biệt lỗi ở build stage và runtime stage

- `COPY ... not found`: nguồn không có trong context hoặc bị ignore; không phải lỗi Java controller.
- `gradlew: not found`/permission denied: wrapper/script/execute bit thiếu trong build stage.
- `Could not resolve ...`: dependency repository/network/proxy/credentials trong builder.
- `compileJava FAILED`: Java source/toolchain/classpath.
- `test FAILED`: JUnit assertion hoặc môi trường test.
- `COPY --from=build ... app.jar not found`: output task `bootJar` khác tên hoặc build task chưa chạy.
- Image build thành công nhưng container thoát: kiểm tra logs/runtime args, không mặc định build context là nguyên nhân.
- `curl` timeout: server chưa sẵn sàng, port mapping sai hoặc ứng dụng bind vào loopback nội bộ thay vì interface phù hợp.

## 8. Vì sao `.dockerignore` giúp multi-stage dù Dockerfile copy rất chọn lọc?

Một câu hỏi hợp lý: Dockerfile ở mục 7 chỉ dùng `COPY gradlew`, `COPY gradle/wrapper`, `COPY settings.gradle build.gradle` và `COPY src`; tại sao vẫn cần `.dockerignore`?

**Có ba lý do:**

1. **Giảm dữ liệu trong context:** nhất là khi builder remote hoặc Docker/BuildKit version/configuration truyền thêm file; loại `.git`, cache và outputs tránh context không cần thiết.
2. **Phòng ngừa khi build script phát triển:** một developer sau này thêm `COPY . .`, hoặc dùng Dockerfile khác có broad COPY. Ignore rules giúp tránh gửi file dư và tránh những file đó làm invalidation.
3. **Giảm nguy cơ vô tình đưa file nhạy cảm vào build:** `.env`/private keys/logs được loại từ context. Đây là defense-in-depth, **không phải bảo mật tuyệt đối**; source repo, remote build context, build args, secrets management và base image còn cần kiểm soát riêng.

BuildKit có thể tối ưu hóa việc truyền context và bỏ qua file không được sử dụng; không khẳng định rằng mỗi byte bị ignore đều luôn tương ứng trực tiếp một byte network tiết kiệm ở mọi phiên bản. Hãy đo bằng logs `transferring context` hoặc build diagnostics trên builder đang dùng.

### 8.1. Đừng exclude file đang được COPY

Ví dụ `.dockerignore` sai cho Dockerfile Gradle:

~~~dockerignore
gradle
gradlew
src
~~~

Hậu quả:

~~~text
COPY gradlew ...       -> source bị loại
COPY gradle/wrapper ...-> source bị loại
COPY src ...           -> source bị loại
~~~

Tùy BuildKit, lỗi có thể xuất hiện dạng `failed to calculate checksum ... not found` hoặc `COPY failed`. Cách sửa không phải xóa `COPY`, mà là giữ đúng inputs cần cho builder và chỉ ignore cache/output không cần.

### 8.2. `.dockerignore` không thay thế stage boundary

Nếu bạn có:

~~~dockerfile
FROM eclipse-temurin:17-jdk
COPY . .
RUN ./gradlew bootJar
ENTRYPOINT ["java", "-jar", "build/libs/app.jar"]
~~~

dù `.dockerignore` tốt, **final image vẫn dùng JDK stage**, còn source/wrapper/Gradle artifacts đã được copy vào image layers. Đây là single-stage image và thường không phù hợp cho production.

Cần thêm một `FROM ... AS runtime` để tạo stage mới, rồi copy đúng output qua `COPY --from`; ignore file không thể xóa JDK/base layers đã nằm trong final stage.

## 9. Docker cache khác Gradle cache

Có ba cache liên quan nhưng không đồng nghĩa:

| Cơ chế | Dữ liệu | Ví dụ |
| --- | --- | --- |
| Docker/BuildKit layer cache | Kết quả instructions/layers khi input không đổi | Reuse `COPY build scripts` và `RUN gradlew help` |
| BuildKit cache mount | Một directory persistent cho package manager/compiler | `/root/.gradle`, `/root/.m2/repository` |
| Gradle dependency/build cache | Gradle modules, metadata, task output tùy Gradle settings | `~/.gradle/caches/modules-2`, task build cache entries |

Nếu `COPY src` thay đổi, Docker có thể phải chạy lại `RUN gradlew test bootJar`. Nhưng **cache mount** vẫn có thể giữ dependencies đã tải nên Gradle không cần download lại toàn bộ. Nếu Gradle build cache được bật và task cacheable, task outputs có thể reuse theo Gradle inputs; điều này là một tối ưu **bên trong build stage**, không phải thay thế Docker layer cache.

### 9.1. Vì sao copy build scripts trước source?

Docker layer cache xét instruction và file phụ thuộc. Nếu Dockerfile làm:

~~~dockerfile
COPY . .
RUN ./gradlew test bootJar
~~~

thay đổi README, logs hoặc một Java source có thể invalidate broad COPY; `RUN` phía sau lại chạy. Với trình tự:

~~~dockerfile
COPY settings.gradle build.gradle ./
RUN ./gradlew help
COPY src/ src/
RUN ./gradlew test bootJar
~~~

các bước trước `COPY src` có thể reuse khi chỉ source code thay đổi. Nhưng phải nói rõ `gradlew help` chỉ warm wrapper/plugins/configuration, **không bảo đảm download trọn runtime dependency graph**. Muốn cache dependencies qua các lần RUN thì dùng BuildKit cache mount như Dockerfile ở mục 7.

### 9.2. Cache mount: hữu ích nhưng có điều kiện

Fragment:

~~~dockerfile
RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon test bootJar
~~~

Ý nghĩa:

- `type=cache` cho phép directory cache được giữ trong builder qua nhiều build invocations, tùy cache GC.
- `target=/root/.gradle` phù hợp khi builder stage chạy Gradle dưới user `root` mặc định của image mẫu.
- `sharing=locked` yêu cầu các tác vụ dùng cùng cache chờ nhau, có thể an toàn hơn trong kịch bản concurrent writers; đánh đổi throughput khi build song song.
- Cache mount **không tự mang toàn bộ Gradle User Home vào final image**.
- Cache có thể bị prune; build **phải vẫn đúng** khi cache rỗng. Không dựa vào cache như nguồn sự thật độc nhất.

Nếu bạn đổi builder user sang `gradle` hoặc `app`, đường dẫn `GRADLE_USER_HOME` cũng có thể đổi. Mount đúng directory của user đó, đặt UID/GID cho cache mount nếu cần; đừng copy cứng `/root/.gradle` vào một stage chạy non-root.

### 9.3. Không dùng Docker `--no-cache` để xóa Gradle dependency cache

~~~bash
docker build --no-cache --progress=plain -t boot-web:gradle .
~~~

`--no-cache` buộc Docker không dùng instruction layer cache cho build đó, nhưng **không nhất thiết xóa BuildKit cache mounts** hoặc repository/download caches bên ngoài. Cũng không tự thay đổi Gradle dependency resolution TTL.

Ngược lại, `./gradlew clean` dọn workspace output nhưng không xóa BuildKit layers và Gradle dependency cache. Đừng dùng các lệnh khác tầng như một chức năng chung tên “clear cache”.

### 9.4. Mua tốc độ bằng correctness là sai

Các bước như:

~~~dockerfile
RUN ./gradlew bootJar -x test
~~~

có thể chạy nhanh hơn nhưng **không kiểm thử**. Chỉ bỏ tests nếu pipeline có job riêng đã chạy đúng bộ tests theo chính sách và release gate bảo đảm kết quả. Không vì tối ưu Docker build mà tự bỏ dependency verification, security checks hay compile warnings.

## 10. Maven multi-stage build — lựa chọn tương đương

Nếu repository dùng Maven, không cần Gradle wrapper. Tạo project riêng `boot-web` với cùng Java source và `pom.xml` dưới đây; dùng Dockerfile riêng để tránh nhầm build tools.

### 10.1. POM Maven đầy đủ

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>boot-web</artifactId>
    <version>0.1.0</version>

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
        <finalName>app</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent quản lý dependency/plugin versions và repackage execution khi plugin được khai báo. `<finalName>app</finalName>` làm output executable artifact có tên ổn định `target/app.jar`. Không coi `<finalName>` là Maven artifactId/version thay đổi: tọa độ artifact vẫn do POM quyết định.

### 10.2. Dockerfile.maven đầy đủ

Tại root Maven project, tạo `Dockerfile.maven`:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml ./

# Warm dependencies/plugins; một số plugin vẫn tải thêm ở phase sau
RUN --mount=type=cache,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp dependency:go-offline

COPY src/ src/

RUN --mount=type=cache,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp verify

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=build /workspace/target/app.jar /app/app.jar

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là phiên bản tương đương Gradle:

- Build stage chứa Maven + JDK 17.
- `pom.xml` được COPY trước `src` để dependency resolution có cơ hội cache tốt.
- `dependency:go-offline` tải nhiều dependency/plugin cần cho offline build, nhưng **không cam kết mọi plugin/test/task động đều đã tải**; main goal `verify` vẫn có thể cần network.
- `mvn verify` chạy Maven test/package/verify lifecycle theo project cấu hình; plugin Spring Boot repackage tạo executable archive.
- Final stage chỉ nhận `target/app.jar` và JRE, không có Maven local repo, POM hay sources.

Lệnh thực hành:

~~~bash
docker build --progress=plain -f Dockerfile.maven -t boot-web:maven .
docker run --rm -p 18081:8080 boot-web:maven
~~~

Trong terminal khác:

~~~bash
curl -fsS http://localhost:18081/hello
~~~

Body mong đợi:

~~~text
hello-from-container
~~~

Chú ý file `.dockerignore` dùng chung cũng phù hợp với Maven builder này: nó không loại `pom.xml` và `src`. Nếu project Maven dùng multi-module parent POM, local dependencies hoặc `.mvn/extensions.xml`, cần thêm những build inputs đó vào context và `COPY` theo đúng cấu trúc.

### 10.3. Nếu dùng Maven wrapper thay image có Maven

Bạn có thể dùng image JDK và copy `mvnw` + `.mvn/wrapper` rồi chạy `./mvnw` thay vì dựa vào Maven cài sẵn trong builder. Khi đó:

- Giữ `mvnw`, `.mvn/wrapper/maven-wrapper.properties` và những file wrapper cần thiết trong context.
- Không ignore thư mục `.mvn` một cách blanket.
- Builder phải tải được Maven distribution hoặc đã có cache/provision offline phù hợp.
- Maven wrapper version được pin từ repository giúp build tool nhất quán hơn.

Không trộn hai phương án mà quên source files: nếu Dockerfile gọi `./mvnw` nhưng không COPY `mvnw`/`.mvn`, build thất bại trước cả bước compile.

## 11. Thêm stage extract để tận dụng Spring Boot layered JAR

Multi-stage có thể tối ưu hơn việc copy một uber JAR duy nhất. Spring Boot 3.3 có **layered executable JAR** với `BOOT-INF/layers.idx` và `spring-boot-jarmode-tools` (khi tính năng được bật). JAR tools cho phép:

~~~bash
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

Lệnh trên tạo các nhóm layer như:

~~~text
dependencies/
spring-boot-loader/
snapshot-dependencies/
application/
~~~

Sử dụng separate Docker `COPY` cho mỗi nhóm có thể giúp image cache tốt hơn: thư viện ổn định ở layer riêng, code ứng dụng đổi nhiều ở layer cuối. Đây là cơ chế **Spring Boot artifact layers**, khác với việc Dockerfile có nhiều stage.

### 11.1. Dockerfile ba stage: Gradle build → extract → runtime

Đây là **một biến thể hoàn chỉnh thay thế Dockerfile ở mục 7**, dùng đúng Gradle Groovy project `boot-web` với `bootJar.archiveFileName='app.jar'`:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
RUN chmod +x gradlew

RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon help

COPY src/ src/

RUN --mount=type=cache,target=/root/.gradle,sharing=locked \
    ./gradlew --no-daemon test bootJar

FROM eclipse-temurin:17-jre AS extract
WORKDIR /extract
COPY --from=build /workspace/build/libs/app.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=extract /extract/extracted/dependencies/ ./
COPY --from=extract /extract/extracted/spring-boot-loader/ ./
COPY --from=extract /extract/extracted/snapshot-dependencies/ ./
COPY --from=extract /extract/extracted/application/ ./

EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Theo Spring Boot 3.3, output của extract có layer `application` chứa một application JAR và manifest tham chiếu các thư viện đã được extract; sau khi COPY từng layer vào cùng `WORKDIR`, lệnh `java -jar application.jar` chạy từ layout đó.

Đây **không phải** lệnh `java -jar app.jar` chạy uber JAR cũ ở final stage: image cuối chỉ nhận các file đã trích từ layers, không cần giữ nguyên uber JAR.

### 11.2. Điều kiện quan trọng để extract chạy

- Executable JAR phải hỗ trợ `-Djarmode=tools` và chứa `spring-boot-jarmode-tools`; nếu team tắt `includeTools`, mode có thể không tồn tại.
- JAR phải được build **không có launch script**. Tài liệu Spring Boot 3.3 nói tools mode **không dùng** cho fully executable archive đã prepend shell script.
- Kiểm tra JAR có layer metadata theo cấu hình plugin. Nếu team thay custom layers, tên/folder mặc định có thể không đúng.
- Dùng đúng Java runtime tương thích trong extract stage.
- Nếu `extract` báo lỗi, đọc log thực trước khi đổi `Dockerfile` hoặc disable tests.
- Với Spring Boot phiên bản cũ, mode/arguments có thể khác (`layertools` ở các dòng cũ). Không copy cú pháp này sang mọi version.

### 11.3. Multi-stage và layered copy tối ưu những thứ khác nhau

| Tối ưu | Tác động chính |
| --- | --- |
| Build stage riêng và JRE final stage | Không mang JDK/Maven/Gradle/source sang final image |
| `.dockerignore` | Loại file host không cần khỏi build context |
| Thứ tự `COPY` hợp lý | Tránh invalidate các Docker layers sớm khi source đổi |
| BuildKit cache mount | Tái sử dụng downloaded dependencies và một phần caches giữa build invocations |
| Spring Boot layers + separate `COPY` | Tách runtime libraries/loader/app classes cho Docker image layer caching |
| Smaller/pinned base image | Giảm footprint và rủi ro tùy image; phải test compatibility |
| Gradle/Maven reproducible build policy | Giảm khác biệt artifact bytes không cần thiết |

Đừng gọi tất cả những kỹ thuật trên là “multi-stage build” hoặc “Docker cache”. Chúng tác động tại các lớp khác nhau của hệ thống.

## 12. Tổ chức context cho Gradle multi-project và Maven multi-module

Dự án thật thường không nhỏ như demo:

~~~text
workspace/
├── settings.gradle
├── build.gradle
├── gradle/
│   ├── wrapper/
│   └── libs.versions.toml
├── gradlew
├── common-lib/
│   ├── build.gradle
│   └── src/
├── api-service/
│   ├── build.gradle
│   └── src/
└── docker/
    └── api.Dockerfile
~~~

Nếu Dockerfile nằm ở `docker/api.Dockerfile`, câu lệnh đúng để lấy root build context thường là:

~~~bash
docker build -f docker/api.Dockerfile -t api-service:local .
~~~

Dấu `.` vẫn là context root. Dockerfile phải copy những files cần cho Gradle root, các subprojects, version catalogs, shared build logic. Ví dụ fragment tham khảo:

~~~dockerfile
WORKDIR /workspace
COPY gradlew ./
COPY gradle/wrapper/ gradle/wrapper/
COPY settings.gradle build.gradle ./
COPY gradle/libs.versions.toml gradle/libs.versions.toml
COPY common-lib/build.gradle common-lib/build.gradle
COPY api-service/build.gradle api-service/build.gradle
COPY common-lib/src/ common-lib/src/
COPY api-service/src/ api-service/src/
RUN ./gradlew --no-daemon :api-service:test :api-service:bootJar
~~~

Đây là **fragment minh họa**, không phải Dockerfile đầy đủ: nó phụ thuộc project root thực sự có tất cả path trên. Nếu dùng Kotlin DSL, thay file names `.gradle` tương ứng. Nếu có `buildSrc`, included build `build-logic`, `gradle.properties`, generated sources, schema files hoặc codegen inputs, phải copy thêm đúng paths.

Nguyên tắc:

1. **Chỉ include đúng modules cần để build ứng dụng**, nhưng không bỏ những project dependencies mà ứng dụng cần.
2. Keep root settings/version catalogs nếu Gradle cần để resolve toàn bộ dependency graph.
3. Chọn task path `:api-service:bootJar` thay vì `bootJar` ở root khi root không phải Spring Boot application.
4. Cấu hình output file name rõ ở module thực sự tạo artifact.
5. Dùng `COPY --from=build /workspace/api-service/build/libs/app.jar ...` ở runtime stage, không lấy `workspace/build/libs` theo mặc định.
6. Không đặt context vào `api-service/` nếu settings cần `common-lib/` nằm ngoài context.

### 12.1. Maven multi-module

Maven reactor có parent POM và module POMs. Một `Dockerfile.maven` có thể cần:

~~~dockerfile
COPY pom.xml ./
COPY common-lib/pom.xml common-lib/pom.xml
COPY api-service/pom.xml api-service/pom.xml
COPY common-lib/src/ common-lib/src/
COPY api-service/src/ api-service/src/
RUN mvn -B -ntp -pl api-service -am verify
~~~

Đây là **fragment**: root POM phải định nghĩa modules tương ứng, và mọi plugin/parent dependency cần resolve được. `-pl api-service -am` chọn module cùng các reactor dependencies cần build, không tạo artifact ở `target` root.

Runtime stage phải copy đúng module output, ví dụ `/workspace/api-service/target/app.jar` nếu module Maven đó đặt `finalName=app`. Không dùng `COPY target/*.jar` của root khi root chỉ có POM packaging.

### 12.2. Đừng áp dụng blanket `**/build` rồi lại muốn COPY local JAR

Có hai mô hình khác nhau:

**A. Docker build từ source:** builder stage tự chạy Gradle/Maven, cần `src`/build scripts; nên ignore local `build/`/`target/` để tránh gửi output cũ.

**B. Docker image từ JAR đã được CI build sẵn:** Dockerfile chỉ cần executable JAR; context cần chứa **JAR được stage/publish một cách xác định**, ví dụ `dist/app.jar`. Khi đó không được đặt ignore rule làm mất chính source JAR mà `COPY dist/app.jar` cần.

Không có một file `.dockerignore` tối ưu cho cả hai kịch bản nếu input requirements khác. Dùng tên file riêng `Dockerfile.source`/`Dockerfile.artifact` và Dockerfile-specific ignore rules khi cần.

## 13. Trường hợp chỉ đóng image từ JAR đã build trên host

Đây **không phải multi-stage build từ source**, nhưng rất hữu ích khi CI đã chạy `./gradlew test bootJar` trước và chỉ cần packaging container. Tách build artifact khỏi Docker build có thể giúp provenance/CI orchestration rõ ràng hơn.

Ví dụ cấu trúc:

~~~text
publish-image/
├── Dockerfile
├── .dockerignore
└── dist/
    └── app.jar
~~~

Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY dist/app.jar /app/app.jar
EXPOSE 8080
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

`.dockerignore` cho kịch bản này có thể dùng allowlist có kiểm soát:

~~~dockerignore
**
!dist/
!dist/app.jar
!Dockerfile
!.dockerignore
~~~

Với allowlist/negation, phải kiểm thử thật vì matcher và parent directory rules có thể ảnh hưởng. Đây là ví dụ cố tình giữ `dist/app.jar`. Nếu thư mục `dist` ở root context, Docker build cần chạy tại `publish-image/`:

~~~bash
docker build -t boot-web:artifact .
~~~

Không lấy JAR qua một glob `build/libs/*.jar` khi có cả `-plain.jar` và Boot JAR. Lệnh staging trong CI nên copy **output của đúng task** vào `dist/app.jar`; file đó phải được QA trước.

**Phân biệt:** loại `build/` trong `.dockerignore` giúp context source-build nhỏ hơn, nhưng với image-from-artifact bạn phải *include* đường dẫn chứa artifact đã được chuẩn bị. Trọng tâm là **contract của mỗi Dockerfile**, không phải rule ignore chung cứng nhắc.

## 14. Kiểm tra hiệu quả build context và cache đúng cách

### 14.1. Bật output build đủ chi tiết

~~~bash
docker build --progress=plain -t boot-web:gradle .
docker build --progress=plain -t boot-web:gradle .
~~~

Quan sát các dòng gần:

~~~text
[internal] load .dockerignore
[internal] load build context
transferring context: ...
CACHED ...
RUN ... test bootJar
~~~

Đây là **tên các loại message**, không phải stdout cố định. Số byte context, duration và cache hit phụ thuộc Docker/BuildKit version, builder backend, source tree và state hiện tại.

Lần đầu có thể tải base image, Gradle distribution, plugins/dependencies. Lần hai có thể nhanh hơn do Docker layers, BuildKit cache mounts, Gradle downloaded dependencies và filesystem cache. **Không kết luận một con số tiết kiệm cụ thể** khi chưa đo có đối chứng.

### 14.2. Đổi một file để xem invalidation

Sau khi build lần đầu, sửa một string trong `HelloController.java`, build lại:

~~~bash
docker build --progress=plain -t boot-web:gradle .
~~~

Kỳ vọng:

- Các layers copy wrapper/build scripts có thể `CACHED` khi các inputs đó không đổi.
- Layer `COPY src` thay đổi.
- Task `test bootJar` chạy lại hoặc Gradle reuse outputs hợp lệ từ cache mount nếu được cấu hình.
- Runtime stage chỉ nhận Boot JAR mới; không mang source vào final image.

Nếu sửa `build.gradle` thay vì source, một phần các bước setup/configuration có thể bị invalidated sớm hơn; đây là hành vi phù hợp vì plugin/version/dependency graph có thể đã đổi.

### 14.3. Xác nhận final image không chứa build tooling

Các lệnh khảo sát sau chỉ để kiểm chứng, không phải hợp đồng bảo mật tuyệt đối:

~~~bash
docker image ls boot-web
docker image inspect boot-web:gradle
docker history --no-trunc boot-web:gradle
~~~

`docker history` cho image cuối và có thể phản ánh nguồn base/history/runtime instructions. Nó không tự chứng minh mọi file có hay không; để kiểm tra chắc hơn, chạy shell inspect khi runtime image có shell:

~~~bash
docker run --rm --entrypoint sh boot-web:gradle -c 'ls -la /app'
~~~

Kỳ vọng trong ví dụ: `/app/app.jar` tồn tại. Không có `gradlew` hoặc source dưới `/app`. Tuy nhiên `eclipse-temurin:17-jre` vẫn chứa thành phần của hệ điều hành/JRE; multi-stage không tạo “image chỉ có một file” tuyệt đối.

Nếu dùng distroless image không có shell, lệnh `--entrypoint sh` không hoạt động; kiểm tra bằng tooling khác hoặc stage debug phù hợp thay vì kết luận image hỏng.

### 14.4. So sánh image size và thời gian build

Để đo có ý nghĩa:

- Sử dụng cùng source revision, base images, builder, network và cache state.
- Ghi size qua `docker image inspect`/`docker image ls`, duration từ build logs.
- So sánh Dockerfile single-stage (chỉ phục vụ thí nghiệm) với multi-stage/JRE runtime.
- Đừng chỉ so sánh compressed registry transfer size với uncompressed local image size như cùng một đơn vị.
- Ghi trạng thái cold vs warm Docker layer cache và Gradle/Maven dependency caches.
- Kiểm tra endpoint/behavior; image nhỏ hơn nhưng thiếu runtime library hoặc permission không phải tối ưu thành công.

## 15. Bảo mật: multi-stage và .dockerignore chỉ là các lớp bảo vệ

### 15.1. Không đưa secrets vào Dockerfile hoặc build args

Tránh:

~~~dockerfile
ARG REPO_PASSWORD=hardcoded-secret
ENV REPO_PASSWORD=hardcoded-secret
COPY .env /app/.env
~~~

Các ví dụ trên là **anti-pattern**. Build args/environment/layers/history có thể làm lộ giá trị nhạy cảm nếu được dùng sai. `.dockerignore` giảm nguy cơ gửi file nhạy cảm từ máy local, nhưng **không** bảo vệ secret đã hardcode trong Dockerfile/build script hoặc một network fetch không kiểm soát.

Với BuildKit, dùng `--secret` và `RUN --mount=type=secret` theo Docker documentation khi builder cần credentials của repository nội bộ. Không in secret vào log hoặc copy vào final artifact/layer. Hãy phối hợp với CI secret manager và chính sách credential rotation.

### 15.2. Dùng non-root runtime

Ở final stage:

~~~dockerfile
USER 10001:10001
~~~

Giúp process Spring Boot không chạy mặc định bằng root. Nhưng phải kiểm tra:

- File JAR có thể đọc được bởi UID/GID này.
- Log storage và temp directory writable nếu ứng dụng cần.
- Port sử dụng không yêu cầu đặc quyền (8080 phù hợp).
- Runtime filesystem có thể read-only hoặc có mount cần thiết.
- Container orchestration có thể override UID/GID; không giả định mọi môi trường giữ y nguyên.

Không khắc phục lỗi permission bằng cách chuyển `USER root` vô điều kiện. Ưu tiên chỉ cấp quyền cho đúng thư mục cần ghi.

### 15.3. Pin base image và kiểm tra supply chain

`eclipse-temurin:17-jdk`/`:17-jre` và `maven:3.9-eclipse-temurin-17` là image tags minh họa. Tags có thể được cập nhật theo security patches; trong production nên dùng policy về approved registries, image digest pinning hoặc update cadence, vulnerability scanning, SBOM và provenance.

Không chép một `sha256:...` giả vào Dockerfile; phải lấy digest thật từ registry được tổ chức phê duyệt và kiểm chứng compatibility. Multi-stage làm runtime image thường ít công cụ hơn nhưng **không tự chứng minh** đã hết CVEs hoặc base image đáng tin.

### 15.4. Không tin nguồn context tùy ý

Docker hỗ trợ local/remote Git/tar contexts. Nếu `docker build` nhận remote URL, các tệp được lấy từ nguồn đó; cách ignore file và quyền của builder có thể khác với local checkout. Không build từ Git URL không tin cậy cùng secrets/privileged builder. Kiểm tra context source, commit/revision và checksum theo CI pipeline.

## 16. Lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân phổ biến | Kiểm tra và sửa đúng |
| --- | --- | --- |
| `COPY gradlew: not found` | Wrapper không có trong context hoặc bị ignore | Xác minh `gradlew` tồn tại, context root và `.dockerignore` |
| `COPY gradle/wrapper: not found` | Tên/path sai hoặc exclude `gradle` | Giữ `gradle/wrapper`, tránh nhầm với `.gradle` |
| `gradlew: Permission denied` | Wrapper không executable trong Linux | `RUN chmod +x gradlew` trước RUN |
| `gradlew` tải Gradle distribution thất bại | Network/TLS/URL/permission của wrapper | Kiểm tra `gradle-wrapper.properties`, proxy, approved mirror |
| `settings.gradle`/`build.gradle` not found | Dùng Kotlin DSL nhưng Dockerfile COPY tên Groovy | Đổi sang `.gradle.kts` và giữ đúng context |
| `COPY src` not found | Chọn nhầm context `docker/` hoặc ignore source | Dùng context repository root và sửa ignore |
| Gradle `bootJar` task không tồn tại | Plugin chưa apply ở đúng module | Xem `plugins` và Gradle project path |
| `COPY --from=build ... app.jar` không thấy | Output filename khác, task chưa build, module path khác | Cố định `archiveFileName`/`finalName`, chọn đúng path |
| `java -jar` thiếu Main-Class hoặc runtime libraries | Copy nhầm plain JAR | Xem `bootJar`/Maven repackage, manifest và `BOOT-INF` |
| Container start nhưng URL không truy cập | `-p` sai hoặc app không bind đúng port | Xem logs, port mapping và `server.port` |
| Docker build rất chậm khi sửa README | `COPY . .` và context thiếu ignore | Tách COPY theo độ ổn định, loại docs/logs/cache không cần |
| Docker build tải Gradle/Maven deps lại | Cache mount chưa có hoặc builder mới/GC prune | Dùng BuildKit cache mount, pin wrapper và repositories |
| `.dockerignore` không có hiệu lực như kỳ vọng | File đặt sai root hoặc file-specific ignore có precedence | Xác định context, Dockerfile path và ignore file đúng |
| Rule `!` không include lại file | Rule order hoặc directory ancestors bị loại | Xem last-match rule; test tree path thực tế |
| Builder stage compile OK, runtime `ClassNotFound` | Copy sai JAR/dependency scope | Xem `BOOT-INF/lib`, production runtimeClasspath |
| `USER 10001` không ghi được logs | Runtime writable directory/permissions thiếu | Cấp đúng mounts và quyền, không bật root tùy tiện |
| `jarmode=tools` báo không hỗ trợ | JAR có launch script hoặc thiếu tools/version sai | Dùng Boot JAR không script, include tools và đúng Boot version |
| Layered Dockerfile `COPY extracted/...` fail | Extract không tạo expected folders hoặc layer custom | Kiểm tra command/output extract trong stage |
| Image lớn bất thường | Copy toàn source/JDK vào runtime, base quá lớn | Kiểm tra final stage và `COPY --from`, chọn JRE phù hợp |
| Build context chứa secrets | Ignore rules thiếu hoặc broad COPY | Loại files trước context, dùng secret mount, audit nguồn |
| Build multi-module fail | Thiếu project dependencies/version catalogs/buildSrc | COPY đủ required inputs hoặc dùng đúng context root |

### 16.1. Quy trình chẩn đoán an toàn

1. **Xem dòng lệnh** `docker build -f ... CONTEXT`, xác định root context thật.
2. **Kiểm `.dockerignore` có hiệu lực** và Dockerfile-specific ignore file nếu tồn tại.
3. **Xác định stage lỗi**: build, extract hay runtime. Không sửa controller khi lỗi `COPY` xảy ra trước compilation.
4. **Kiểm output của build tool**: Gradle `bootJar`/Maven `repackage` và file path thực.
5. **Kiểm artifact**: manifest và `BOOT-INF/classes`/`BOOT-INF/lib` nếu đang dùng executable Boot JAR.
6. **Kiểm image cuối**: runtime JRE, JAR path, non-root permissions, `ENTRYPOINT`.
7. **Chạy smoke test** với port mapping phù hợp; quan sát logs.
8. **Mới tối ưu cache** khi một bản build không cache đã thành công và có kiểm thử.

## 17. Bài tập thực hành có đáp án

### Bài 1 — Hiểu root context

Dockerfile ở `docker/Dockerfile`, còn `src`/`build.gradle` ở root. Bạn chạy:

~~~bash
docker build -f docker/Dockerfile docker/
~~~

`COPY src/ src/` fail. Vì sao?

**Đáp án:** context là `docker/`, không phải thư mục chứa source ở root. Dùng `docker build -f docker/Dockerfile .` từ project root hoặc thay đổi tổ chức context có chủ đích.

### Bài 2 — Giữ wrapper, loại cache

Chọn hai directory:

~~~text
.gradle/
gradle/wrapper/
~~~

**Câu hỏi:** file nào nên ignore khi Dockerfile chạy `./gradlew`?

**Đáp án:** thường ignore `.gradle/` (local state), **giữ** `gradle/wrapper/` và `gradlew`. Wrapper cần chạy trong Linux builder.

### Bài 3 — Vì sao `.dockerignore` không thu nhỏ single-stage runtime?

**Câu hỏi:** một Dockerfile dùng `FROM eclipse-temurin:17-jdk`, `COPY src` và `RUN ./gradlew bootJar` rồi chạy chính image này. Tại sao image vẫn lớn dù context nhỏ?

**Đáp án:** image cuối vẫn dựa trên JDK stage, còn sources/build tooling có thể tồn tại trong filesystem/layers. Cần tạo final stage JRE mới và `COPY --from` đúng JAR.

### Bài 4 — Chọn JAR đúng

Task Gradle có cả:

~~~text
build/libs/boot-web-0.1.0-plain.jar
build/libs/boot-web-0.1.0.jar
~~~

**Câu hỏi:** Dockerfile nên copy file nào vào `java -jar` runtime?

**Đáp án:** output của `bootJar`, thường file không classifier theo mặc định; tốt hơn định nghĩa `archiveFileName='app.jar'` để COPY path chính xác. Không chọn glob ngẫu nhiên.

### Bài 5 — BuildKit cache mount

**Câu hỏi:** Dockerfile dùng `RUN --mount=type=cache,target=/root/.gradle ...`, thay một Java source khiến `RUN` chạy lại. Có cần tải toàn bộ dependency từ đầu không?

**Đáp án:** không nhất thiết. Docker instruction cache miss có thể xảy ra nhưng Gradle dependency cache trong mount vẫn còn nếu builder giữ nó. Nếu cache mount bị GC/xóa hoặc dependency thay đổi, tải thêm là bình thường.

### Bài 6 — Maven và Gradle

**Câu hỏi:** Dockerfile Maven dùng `FROM maven:3.9-eclipse-temurin-17`, copy POM và `src`; có cần `gradlew` không?

**Đáp án:** không. Đây là Maven builder, lệnh `mvn` có sẵn từ image. Nếu muốn dùng Maven wrapper thì phải đổi thiết kế và COPY `mvnw`/`.mvn` đầy đủ.

### Bài 7 — Layered image

**Câu hỏi:** tại sao dùng 4 lệnh `COPY --from=extract` cho `dependencies`, `spring-boot-loader`, `snapshot-dependencies` và `application` thay vì chỉ COPY một uber JAR?

**Đáp án:** Docker có thể cache/pull các layers riêng; khi app classes đổi mà dependencies giữ nguyên, các layer ổn định ít phải thay đổi hơn. Điều kiện: Spring Boot JAR hỗ trợ extract và output layout đúng.

### Bài 8 — Launch script

**Tình huống:** project bật `launchScript()` vì muốn chạy trực tiếp `./app.jar` trên Unix; Dockerfile mới gọi `-Djarmode=tools ... extract --layers`.

**Đáp án:** với Spring Boot 3.3, tools mode không hỗ trợ fully executable archive có launch script. Build một Boot JAR **không script** cho Docker layer extraction; nếu cần Unix direct execution, có thể phát hành một biến thể riêng.

### Bài 9 — Include exception

`.dockerignore` có:

~~~dockerignore
*.md
!README*.md
README-private.md
~~~

**Câu hỏi:** `README-private.md` có ở context không?

**Đáp án:** bị exclude do rule khớp cuối. Nếu chuyển exception cuối cùng, kết quả có thể đổi; order là một phần semantics của ignore file.

### Bài 10 — Secrets

**Câu hỏi:** đã ignore `.env`, liệu có an toàn để đặt `ARG DB_PASSWORD=...` trong Dockerfile không?

**Đáp án:** không. `.dockerignore` lọc host context, không che giá trị hardcode/build args/layers/logs. Dùng BuildKit secrets hoặc cơ chế CI/runtime secrets theo chính sách.

## 18. Checklist trước khi merge Dockerfile

- [ ] Đã xác định **đúng build context** và root `.dockerignore` cho mỗi lệnh `docker build`.
- [ ] Build inputs thật sự cần thiết (source, wrapper, POM, settings, version catalog, generated input) không bị ignore.
- [ ] `.git`, `.gradle`, `build/`, `target/`, logs, local credentials và file không cần được loại khỏi context.
- [ ] Stage build dùng JDK/build tool, stage runtime chỉ dùng JRE/artifact cần thiết.
- [ ] Dockerfile dùng `COPY --from` rõ stage và artifact path; không lấy nhầm plain JAR.
- [ ] Gradle `bootJar` hoặc Maven `repackage` chạy thật, test gates được giữ theo policy.
- [ ] BuildKit cache mounts (nếu có) không làm build phụ thuộc vào dữ liệu cache không kiểm chứng.
- [ ] Source-only changes không invalidate những bước Dockerfile sớm không liên quan một cách vô ích.
- [ ] Khi dùng layered JAR, `jarmode=tools` tương thích Spring Boot version, tools hiện diện và launch script đã tắt.
- [ ] Final image chạy bằng user không phải root, có port mapping và quyền filesystem phù hợp.
- [ ] Không có build secrets/certs/token trong context, image history, runtime JAR hoặc Docker logs.
- [ ] Base images từ registry được cho phép; có version/digest policy, scanning và update cadence.
- [ ] Đã chạy `docker build --progress=plain` và smoke test endpoint bằng `docker run -p`/`curl`.
- [ ] Đã đo context/cache/image size với điều kiện rõ; không tuyên bố có số % tối ưu khi chưa đo.
- [ ] CI chọn đúng Dockerfile/context và artifact variant khi repository có Gradle/Maven/multi-project.

**Kết luận:** multi-stage build giải quyết **ranh giới giữa build environment và runtime image**; `.dockerignore` giải quyết **ranh giới giữa host filesystem và dữ liệu được đưa vào build context**. Dùng cả hai cùng với thứ tự `COPY` phù hợp và BuildKit cache mounts có thể giảm thời gian build, tránh copy artifact/cache/secret không cần thiết và giữ image runtime gọn. Nhưng điều kiện hoàn thành thực sự vẫn là **build có thể tái lập, tests được kiểm soát và image cuối chạy đúng ứng dụng trong môi trường mục tiêu**.

## 19. Nguồn chính thức

- Docker Docs — Build Context và `.dockerignore` patterns, negation, Dockerfile-specific precedence: https://docs.docker.com/build/concepts/context/
- Docker Docs — Multi-stage Builds: https://docs.docker.com/build/building/multi-stage/
- Docker Docs — Optimize Cache Usage in Builds: https://docs.docker.com/build/cache/optimize/
- Docker Docs — Dockerfile Reference, `RUN --mount=type=cache`: https://docs.docker.com/reference/dockerfile/
- Docker Docs — BuildKit: https://docs.docker.com/build/buildkit/
- Spring Boot 3.3.13 — Dockerfiles và `jarmode=tools extract --layers`: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3.13 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Running Gradle Builds with Docker: https://docs.gradle.org/current/userguide/docker.html
- Apache Maven — Build and Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html

Khi thay Gradle wrapper/Maven plugin/Spring Boot version hoặc Dockerfile frontend, hãy đối chiếu tài liệu đúng phiên bản và kiểm chứng build/image trong môi trường thực. Mục tiêu là có **context nhỏ và đúng, builder đủ công cụ, final image gọn và an toàn, artifact được xác minh**, không chỉ có hai dòng `FROM` hoặc một file `.dockerignore` dài.
