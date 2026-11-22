# Lựa chọn chạy nguyên JAR hoặc trích xuất lớp trước khi tạo image

## 1. Bối cảnh và mục tiêu của quyết định

Khi đưa một ứng dụng Spring Boot lên Docker/Kubernetes, nhóm phát triển thường có hai cách tạo container image từ một **Spring Boot executable JAR**:

1. **Chạy nguyên JAR (fat/uber JAR)**: copy một file JAR đã build vào image rồi chạy `java -jar application.jar`.
2. **Trích xuất lớp trước khi tạo image**: sử dụng **Spring Boot layered archive** và công cụ `jarmode=tools` để tách dependencies, loader và application code; copy từng nhóm vào các Docker/OCI image layers riêng, rồi chạy **JAR đã trích xuất**.

Cả hai đều có thể triển khai một ứng dụng Spring Boot đúng chức năng. Cách thứ nhất ít bước và dễ điều tra; cách thứ hai giúp **tăng cơ hội tái sử dụng Docker build cache và registry layers** khi mã ứng dụng thay đổi thường xuyên hơn dependencies. Lựa chọn tốt không mặc định là “càng nhiều lớp càng nhanh”: cần xét quy mô JAR, tốc độ thay đổi, CI cache, số lượng image phiên bản, yêu cầu vận hành và giới hạn tooling.

Sau bài học bạn có thể:

- Giải thích vì sao nguyên JAR thường tạo **một layer chứa toàn bộ ứng dụng**, còn trích xuất tạo **nhiều image layers theo độ ổn định của dữ liệu**.
- Phân biệt `BOOT-INF/layers.idx`, các thư mục được Spring Boot extract và **Docker/OCI layers** thực sự.
- Viết **hai Dockerfile hoàn chỉnh** chạy **cùng một executable JAR** và lựa chọn cách build tại CLI.
- Sử dụng Spring Boot **3.3 `-Djarmode=tools`** với `list-layers` và `extract --layers`; biết sự khác nhau với `layertools` ở hướng dẫn cũ.
- Cấu hình Gradle `bootJar` hoặc Maven `repackage` để tạo archive đúng; xác minh launcher, tools dependency và file đầu vào.
- Xây dựng thí nghiệm sửa Controller, so sánh Docker `CACHED` và response HTTP, không tuyên bố cache hit khi chưa đọc log.
- Nhận diện giới hạn về startup, kích thước image, reproducibility, security, non-root user, base image và CI runner.
- Đưa ra quyết định có căn cứ và kiểm chứng artifact đã dùng thật.

**Ví dụ xuyên suốt:** Spring Boot **3.3.5**, Java **17**, Spring MVC, Gradle Wrapper hoặc Maven Wrapper tương thích, Docker hỗ trợ multi-stage build. Các version này chỉ để minh họa một hệ API nhất quán, **không phải bản khuyến nghị mới nhất**. Spring Boot 3.3 đã có `spring-boot-jarmode-tools`; với Spring Boot 2.x/đầu 3.x, cú pháp và layout có thể khác. Hãy ưu tiên tài liệu phiên bản project của bạn.

## 2. Mô hình thứ nhất: chạy nguyên executable JAR

Spring Boot Gradle `bootJar` hoặc Maven `spring-boot:repackage` tạo file JAR có thể chạy bằng `java -jar`. Cấu trúc thường là:

~~~text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...     (Spring Boot launcher)
└── BOOT-INF/
    ├── classes/                           (application classes/resources)
    │   └── com/example/dockerchoice/...
    ├── lib/                               (runtime dependency JARs)
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...
    ├── layers.idx                         (khi layering được bật)
    └── classpath.idx                      (nếu có)
~~~

Khi khởi chạy, JVM đọc `Main-Class` trong manifest. Với Spring Boot 3.3 executable JAR, `Main-Class` thường là `org.springframework.boot.loader.launch.JarLauncher`, còn `Start-Class` chỉ application class do bạn viết. Launcher thiết lập classpath để đọc nested libraries bên trong `BOOT-INF/lib`.

**Dockerfile đơn giản** có thể chỉ cần một base JRE image, một `COPY` và `ENTRYPOINT`:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Đoạn này **chỉ minh họa nguyên tắc**; nếu `app.jar` chưa nằm trong build context thì `COPY` sẽ thất bại. Phần thực hành ở mục 7 sẽ có bản đầy đủ cùng `ARG JAR_FILE` để copy trực tiếp từ output Maven/Gradle.

**Ưu điểm của chạy nguyên JAR:**

- Ít cấu hình nhất, dễ hiểu cho người mới và các project nhỏ.
- Chỉ cần executable JAR, JRE tương thích và Docker build context có file đó; **không cần tools extraction**.
- Dễ chạy thử cùng artifact bằng `java -jar app.jar` trên máy hoặc trong container.
- Không phụ thuộc vào cấu trúc thư mục `extract --layers` và các tên layer tùy biến.
- Phù hợp khi tốc độ build/push/pull chưa phải vấn đề hoặc tổ chức đã có image building flow đơn giản.

**Hạn chế cần đo thực tế:** chỉ đổi một lớp Java nhỏ có thể khiến **cả file app.jar khác bytes**. Nếu Dockerfile COPY toàn bộ file JAR vào một image layer, layer ấy có thể mất cache và phải được lưu/chuyển lại như một khối. Docker không tự “nhìn vào” `BOOT-INF/lib` để nhận biết phần thư viện giữ nguyên.

Không vì thế mà kết luận mọi lần build nguyên JAR đều chậm: Docker vẫn cache **base image** và các bước trước `COPY`; nếu application JAR không đổi, `COPY` có thể được reuse hoàn toàn. Hiệu quả còn phụ thuộc image registry và CI builder cache.

## 3. Mô hình thứ hai: trích xuất layered archive trước khi đóng image

Spring Boot plugin có thể thêm file `BOOT-INF/layers.idx` mô tả cách gán các archive entries vào những nhóm có tần suất thay đổi khác nhau. Mặc định trong Spring Boot 3.3 thường gồm:

| Layer Spring Boot | Chứa gì? | Tần suất thay đổi tương đối |
| --- | --- | --- |
| `dependencies` | Thư viện ngoài có version không chứa `SNAPSHOT`, như các runtime starters/libraries | Ít thay đổi nếu BOM và dependency versions ổn định |
| `spring-boot-loader` | Các class Spring Boot launcher dưới `org/springframework/boot/loader` | Ít thay đổi nếu Boot version không đổi |
| `snapshot-dependencies` | Thư viện snapshot từ dependency graph | Có thể đổi thường xuyên dù version string giữ nguyên |
| `application` | Application classes/resources và local project/module dependencies | Thường đổi mỗi khi phát triển |

Thứ tự mặc định được thiết kế để **đặt nội dung ít đổi trước, nội dung đổi nhiều sau**.

Khi chạy:

~~~bash
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

Spring Boot 3.3 tạo một layout đã trích xuất, thường có các thư mục:

~~~text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
    └── application.jar                  (JAR mỏng tham chiếu thư viện đã tách)
~~~

Đây là **sơ đồ lược giản**; những thư mục khác có thể nằm sâu bên trong các nhóm. `application.jar` ở thư mục application **không phải fat JAR gốc**. Nó là artifact dùng cho chế độ chạy extracted layout, được Spring Boot tools tạo ra và có tham chiếu đến các libraries đã tách ở vị trí phù hợp.

Container image có thể dùng các `COPY --from=extractor` để chồng bốn nhóm vào `WORKDIR /application`:

~~~text
OCI base JRE image
  + dependencies/             (copy trước)
  + spring-boot-loader/
  + snapshot-dependencies/
  + application/              (copy cuối)
  -> java -jar application.jar
~~~

**Mấu chốt:** `layers.idx` là **metadata**, không phải Docker layer. Chỉ khi công cụ build image trích xuất và COPY **riêng từng nhóm** thì mới hình thành cơ hội reuse các Docker/OCI layers độc lập.

### 3.1. Các folder được trích xuất khác cấu trúc ban đầu

Đừng giả định `extract --layers` chỉ giải nén nguyên `BOOT-INF` và bạn phải tự chọn classpath như:

~~~text
java -cp "BOOT-INF/classes:BOOT-INF/lib/*" ...
~~~

Đó không phải cách chạy mặc định của **tools mode Spring Boot 3.3**. Theo tài liệu Boot 3.3, extracted layout có `application.jar` và thư viện được bố trí để chạy bằng:

~~~bash
java -jar application.jar
~~~

tại thư mục extracted đã được hợp nhất các lớp. Khi dùng Spring Boot 2.x và `layertools`, ví dụ lệnh chạy có thể sử dụng trực tiếp `JarLauncher`; **không sao chép entrypoint kiểu cũ sang tools extraction mới** mà không xác minh.

### 3.2. Không phải mọi file JAR đều dùng được tools mode

Cần thỏa các điều kiện:

1. Đây là **Spring Boot executable archive**, không phải `-plain.jar` hoặc JAR library.
2. Layering đang bật và archive có `BOOT-INF/layers.idx`.
3. `spring-boot-jarmode-tools` thực sự được plugin đưa vào archive; `includeTools` không bị tắt.
4. Archive **không phải fully executable JAR với launch script được prepend**, vì tools mode không hỗ trợ loại này.
5. Java runtime dùng trong extractor stage đủ phiên bản để chạy artifact.

Nếu một điều kiện thiếu, hãy sửa **tại build tool/source configuration**, không tự thêm một file `layers.idx` viết tay vào archive sau khi build.

## 4. So sánh nhanh trước khi quyết định

| Tiêu chí | Chạy nguyên JAR | Trích xuất lớp |
| --- | --- | --- |
| Dockerfile | Một COPY cho JAR, ít bước | Multi-stage extract rồi nhiều COPY |
| Độ dễ đọc/vận hành | Rất đơn giản | Phải hiểu tools mode, extracted layout và tên layers |
| Dữ liệu app vào image | Cả JAR chung một image layer | Dependencies/loader/application thành các layer tách biệt |
| Khi chỉ Controller đổi | Whole-JAR COPY thường mất cache | Thường có thể reuse các dependency/loader COPY |
| Registry upload/pull qua nhiều version | Có thể phải upload/download lại blob JAR lớn | Có thể chia sẻ blob dependencies cũ |
| Trường hợp cache trống | Ít công việc ở build image | Có chi phí extract và nhiều COPY |
| Java entrypoint | `java -jar application.jar` với fat JAR | `java -jar application.jar` với **JAR do extractor tạo**, sau khi hợp nhất các layer |
| Cần `layers.idx`/tools | Không | Có khi dùng `jarmode=tools` |
| Lợi ích startup | Tùy ứng dụng và JVM | Extracted layout có thể giảm overhead nested JAR và thân thiện CDS; không hứa tăng tốc cố định |
| Kích thước image | Tùy base JRE + JAR + file khác | Thường không giảm tổng dependencies; metadata/layers có thể tăng thêm chút |
| CI/caching | Ít phụ thuộc cách cache | Hiệu quả tăng khi BuildKit cache hoặc registry layer reuse được giữ |
| Khả năng debug | Kiểm tra một artifact dễ | Cần kiểm chứng cả extraction và layout runtime |
| Dùng khi | POC, project nhỏ, release thưa, quy trình đơn giản | Release liên tục, fat JAR lớn, image registry/pull cost cao, nhiều app shares dependencies |

**Kết luận lựa chọn sơ bộ:** Nếu chưa có vấn đề đo được về Docker build hoặc registry/pull, chạy nguyên JAR là điểm bắt đầu hợp lý. Khi chi phí lặp lại đủ lớn và nguồn dependencies ổn định, trích xuất lớp là bước tối ưu có cơ sở. Nhưng cả hai phương án đều phải chạy test, scan image, pin runtime và quản trị secrets như nhau.

## 5. Tạo project Spring Boot Java 17 dùng cho cả hai phương án

Chúng ta dùng cùng mã nguồn, cùng Gradle build output, rồi chạy **hai Dockerfile** để loại trừ khác biệt do logic ứng dụng.

~~~text
docker-choice-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
├── Dockerfile.jar
├── Dockerfile.layers
├── .dockerignore
└── src/
    ├── main/java/com/example/dockerchoice/
    │   ├── DockerChoiceApplication.java
    │   └── VersionController.java
    └── test/java/com/example/dockerchoice/
        └── VersionControllerTest.java
~~~

**Lưu ý:** Giả định Gradle Wrapper thực sự được tạo/commit bằng công cụ Gradle; chỉ có file `gradlew` nhưng thiếu `gradle/wrapper` sẽ không chạy được. Nếu project dùng Maven, xem mục 12; **không cần tạo cả Maven và Gradle build file** trong một repository thật.

### 5.1. File settings.gradle

~~~groovy
rootProject.name = 'docker-choice-demo'
~~~

### 5.2. File build.gradle — Groovy DSL đầy đủ

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.dockerchoice.DockerChoiceApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'app.jar'
    layered {
        enabled = true
    }
    includeTools = true
}
~~~

**Tại sao như vậy?**

- `spring-boot-starter-web` chứa Spring MVC và Tomcat runtime phù hợp phiên bản Spring Boot đã chọn.
- `java.toolchain` sử dụng Java 17 khi compile; Docker images cũng chạy JRE 17.
- `testImplementation` chỉ dùng lúc test, không đưa JUnit lên runtime classpath của executable JAR thông thường.
- `useJUnitPlatform()` giúp Gradle Test chạy JUnit Jupiter.
- `bootJar.archiveFileName = 'app.jar'` cung cấp tên output **ổn định**: `build/libs/app.jar`, để Dockerfile không chọn nhầm `-plain.jar` hoặc SNAPSHOT version.
- `layered.enabled=true` khiến plugin tạo `BOOT-INF/layers.idx`; Spring Boot 3.3 đã bật layering mặc định nhưng bài dùng khai báo tường minh để dễ đọc.
- `includeTools=true` bảo đảm `jarmode=tools` có mặt; đây cũng là default trong Spring Boot 3.3 nếu layering bật.
- `springBoot.mainClass` chỉ entry point, tránh nhập nhằng khi sau này thêm nhiều lớp main.

Nếu project thật đã dùng `settings.gradle` để quản lý repositories với `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, bỏ block `repositories { mavenCentral() }` tại project và dùng repository được cấp phép. Không thay chính sách repository chỉ để làm Docker image.

### 5.3. File DockerChoiceApplication.java

Đường dẫn `src/main/java/com/example/dockerchoice/DockerChoiceApplication.java`:

~~~java
package com.example.dockerchoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DockerChoiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(DockerChoiceApplication.class, args);
    }
}
~~~

Lớp này là application main class hợp lệ với Java 17 và Spring Boot Starter Web; nó có thể build/run qua Wrapper. Không chạy một mình bằng `javac` mà không có Spring Boot dependencies trên classpath.

### 5.4. File VersionController.java

Đường dẫn `src/main/java/com/example/dockerchoice/VersionController.java`:

~~~java
package com.example.dockerchoice;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {
    @GetMapping("/version")
    public String version() {
        return "image-v1";
    }
}
~~~

Khi ứng dụng đã startup và HTTP request tới `GET /version` thành công, **response body đúng** của mã này là:

~~~text
image-v1
~~~

Không dự đoán chính xác dòng startup log của Spring Boot, vì timestamp, port, PID và log formatting thay đổi theo môi trường.

### 5.5. File VersionControllerTest.java

Đường dẫn `src/test/java/com/example/dockerchoice/VersionControllerTest.java`:

~~~java
package com.example.dockerchoice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(VersionController.class)
class VersionControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void versionReturnsV1() throws Exception {
        mvc.perform(get("/version"))
                .andExpect(status().isOk())
                .andExpect(content().string("image-v1"));
    }
}
~~~

`@WebMvcTest` kiểm tra MVC mapping nhanh mà chưa cần Docker. Nó **không chứng minh container image chạy được**; phải bổ sung container smoke test. Khi đổi Controller sang `image-v2` trong thí nghiệm cache, cũng phải cập nhật assertion để test không cố tình fail.

## 6. Build đúng executable JAR trước khi viết Dockerfile

### Linux/macOS

~~~bash
./gradlew --version
./gradlew clean test bootJar
jar tf build/libs/app.jar | grep '^BOOT-INF/'
java -jar build/libs/app.jar
~~~

### Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
jar tf .\build\libs\app.jar | Select-String '^BOOT-INF/'
java -jar .\build\libs\app.jar
~~~

Dùng terminal thứ hai gọi:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Expected response body:

~~~text
image-v1
~~~

`bootJar` tạo `build/libs/app.jar` theo cấu hình. Các lệnh `jar tf` giúp xác nhận `BOOT-INF/classes`/`BOOT-INF/lib` và `BOOT-INF/layers.idx`. Nếu file JAR không chạy trực tiếp trên máy, **không vội kết luận Dockerfile sai**; phải sửa lỗi build/runtime cơ bản trước.

Sau thử bằng `java -jar`, dừng process trước khi chạy Docker sử dụng cổng host 8080, nếu không port mapping có thể bị xung đột.

**Build source trước, Docker image sau** là kiến trúc của bài này. Dockerfile không tự chạy Gradle/Maven compile; nó chỉ đóng gói artifact đã được test. Đó là một ưu điểm cho CI: same artifact bytes được đưa vào cả hai chiến lược Dockerfile.

## 7. Phương án A — Dockerfile.jar: chạy nguyên JAR

Tạo file **Dockerfile.jar** ở project root:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

ARG JAR_FILE=build/libs/app.jar
COPY $JAR_FILE application.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

**Đây là Dockerfile hoàn chỉnh cho ví dụ đã build Gradle.** Giải thích:

1. `FROM eclipse-temurin:17-jre`: dùng JRE 17 tương thích bytecode/source; image là ví dụ và nên được pin theo digest/chính sách tổ chức khi phát hành.
2. `WORKDIR /app`: đặt thư mục làm việc cho runtime.
3. `ARG JAR_FILE=build/libs/app.jar`: đường dẫn **tương đối với Docker build context** của artifact đã được build. Nó không phải path bên trong image.
4. `COPY $JAR_FILE application.jar`: copy **nguyên executable JAR** vào `/app/application.jar`. Không dùng `COPY build/libs/*.jar`, vì có thể vô tình copy/chọn `-plain.jar`.
5. `USER 10001:10001`: chạy bằng numeric non-root user. App demo chỉ đọc JAR và dùng cổng 8080 nên không cần root, với điều kiện base image cho phép đọc file và dùng thư mục tạm thích hợp.
6. `EXPOSE 8080`: tài liệu hóa cổng trong container; **không tự publish port** ra máy host.
7. `ENTRYPOINT` dạng exec JSON: Java là process chính, không cần shell wrapper, thuận lợi cho quản lý signals. Mã exit của process có thể được Docker/Kubernetes quan sát.

**Không ghi secret trong Dockerfile**; tên database, password, API token được cấp ở runtime qua environment/secret manager. Không dùng lệnh `RUN echo "$PASSWORD" > ...` vì dữ liệu có thể nằm trong image layers.

### Build image A

~~~bash
docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar .
docker run --rm -p 8080:8080 docker-choice:jar
~~~

Mở terminal khác:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Output:

~~~text
image-v1
~~~

Dấu chấm cuối lệnh `docker build` nghĩa là **build context là project root**. Nếu Dockerfile đặt ở nơi khác nhưng build context không chứa `build/libs/app.jar`, `COPY` sẽ không tìm thấy artifact. Đừng “sửa” bằng cách COPY cả repository và các file cá nhân vào image.

### Lợi ích và giới hạn của A

**Phù hợp** với nhiều microservices đơn giản khi build/pull image nhanh, dependency JAR không lớn, release ít hoặc team ưu tiên giảm maintenance burden. Đây không phải một giải pháp “sai”; nó có thể là lựa chọn tốt về tổng chi phí.

**Giới hạn** là Docker không biết nội bộ JAR gồm `BOOT-INF/lib` và `BOOT-INF/classes`. Sửa một Controller làm file `app.jar` đổi; `COPY` đầu vào khác, có khả năng tạo blob ứng dụng mới chứa cả thư viện. Base JRE image vẫn có thể được reuse.

## 8. Bật và kiểm tra layered archive trước khi dùng Dockerfile B

### 8.1. File index trong Boot JAR

Linux/macOS:

~~~bash
jar tf build/libs/app.jar | grep '^BOOT-INF/layers.idx$'
jar tf build/libs/app.jar | grep 'spring-boot-jarmode-tools'
~~~

PowerShell:

~~~powershell
jar tf .\build\libs\app.jar | Select-String '^BOOT-INF/layers.idx$'
jar tf .\build\libs\app.jar | Select-String 'spring-boot-jarmode-tools'
~~~

`BOOT-INF/layers.idx` là bản đồ nhóm file; `spring-boot-jarmode-tools` cung cấp mode công cụ. Hai thành phần này **khác chức năng**. Nếu một trong hai vắng, kiểm tra plugin version, task `bootJar`, `layered.enabled`, `includeTools` và file artifact thật, thay vì tự tạo directory giả.

### 8.2. Liệt kê layers

~~~bash
java -Djarmode=tools -jar build/libs/app.jar list-layers
~~~

Trên PowerShell:

~~~powershell
java -Djarmode=tools -jar .\build\libs\app.jar list-layers
~~~

Với default layering, các tên bạn thường thấy là:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Nếu project có custom layer DSL/XML, tên và thứ tự có thể khác. Một layer có thể không chứa JAR nào, ví dụ không dùng SNAPSHOT. **Danh sách layer không phải danh sách Docker image layers**.

### 8.3. Trích xuất và kiểm tra bằng tay

Linux/macOS:

~~~bash
mkdir -p build/inspect-layers
java -Djarmode=tools -jar build/libs/app.jar \
    extract --layers --destination build/inspect-layers
find build/inspect-layers -maxdepth 2 -type d
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\build\inspect-layers | Out-Null
java -Djarmode=tools -jar .\build\libs\app.jar extract --layers --destination .\build\inspect-layers
Get-ChildItem .\build\inspect-layers\
~~~

Lệnh trích xuất dùng **Spring Boot 3.3 `tools` mode**, không phải `layertools` cũ. Những thư mục được tạo theo các layer. Khi chạy extraction lần nữa, nên dùng **thư mục đích mới/sạch** để không lẫn file còn sót từ lượt trước.

**Không yêu cầu trích xuất trên host để dùng Dockerfile B**; đây chỉ là kiểm tra. Dockerfile B sẽ extract lại trong một builder stage riêng từ **chính artifact** được copy vào build context.

## 9. Phương án B — Dockerfile.layers: trích xuất lớp trong multi-stage build

Tạo file **Dockerfile.layers** ở project root:

~~~dockerfile
# Stage 1: copy executable JAR vào môi trường có Java và extract
FROM eclipse-temurin:17-jre AS extractor

WORKDIR /workspace

ARG JAR_FILE=build/libs/app.jar
COPY $JAR_FILE application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

# Stage 2: runtime không mang fat JAR từ extractor sang
FROM eclipse-temurin:17-jre

WORKDIR /application

COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/application/application.jar"]
~~~

**Đây là multi-stage Dockerfile đầy đủ** cho cấu trúc Spring Boot 3.3 như hướng dẫn chính thức. Phân tích:

1. **Extractor stage** dùng JRE để gọi `-Djarmode=tools`. Không chạy HTTP server ở stage này và không cần source code Java, Maven hay Gradle trong image.
2. `COPY $JAR_FILE application.jar` copy fat JAR nguồn đã build và test, đúng như phương án A nhưng chỉ trong **stage trung gian**.
3. `extract --layers --destination extracted` biến archive thành các nhóm file; Spring Boot tools tạo layout runtime đi kèm JAR ứng dụng đã tách.
4. **Runtime stage** tạo image mới từ JRE base. Nó **không** kế thừa filesystem của extractor stage và **không** copy fat JAR nguồn.
5. `COPY dependencies` trước để giữ các thư viện phát hành thường ít thay đổi ở image layers đầu tiên.
6. `COPY spring-boot-loader` tiếp theo, giữ Boot launcher riêng.
7. `COPY snapshot-dependencies` sau vì thư viện SNAPSHOT thường biến động hơn release dependencies.
8. `COPY application` cuối vì application classes/resources thay đổi thường xuyên nhất.
9. `ENTRYPOINT ["java","-jar","/application/application.jar"]` khởi chạy **JAR mỏng của extracted layout** tại runtime, cùng các thư viện được hợp nhất từ bốn nhóm.
10. `USER 10001:10001` giữ process không có đặc quyền root, giống phương án A; thư mục chứa JAR/libs phải có quyền đọc cho UID này.

**Không thay dòng ENTRYPOINT bằng `java -jar /workspace/application.jar`:** fat JAR nguồn chỉ tồn tại ở **extractor stage**, không được copy sang runtime stage. Tên `application.jar` ở runtime được Spring Boot tools tạo ra từ extracted application layer.

### 9.1. Build image B

~~~bash
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers .
docker run --rm -p 8080:8080 docker-choice:layers
~~~

Mở terminal khác:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Kết quả:

~~~text
image-v1
~~~

**Phải dừng container A hoặc dùng host port khác** trước khi chạy B. Có thể dùng:

~~~bash
docker run --rm -p 8081:8080 docker-choice:layers
~~~

rồi gọi `http://localhost:8081/version`. Cổng của application trong container vẫn là 8080, `-p 8081:8080` chỉ đổi host port.

### 9.2. Cách nhìn Docker build cache

BuildKit in log từng instruction; một số bước có thể được đánh dấu `CACHED` khi inputs và cache store đủ điều kiện. Với B, phần dependencies/loader thường reuse khi chỉ thay Controller, nhưng **không phải cam kết**: nếu CI dùng builder mới, đã xóa cache hoặc base image thay đổi, build có thể thực thi tất cả các bước.

Ngoài ra, khi fat JAR đổi, bước COPY/RUN ở **extractor stage** có thể phải chạy lại. Điều này **không phủ định lợi ích** của các COPY riêng ở runtime stage: miễn các thư mục extracted ổn định thực sự giữ nguyên bytes/metadata và builder nhận diện được, layer registry/runtime liên quan có thể được tái sử dụng.

### 9.3. Ưu điểm và mặt trái của B

**Ưu điểm** gồm cache granularity cao hơn, reuse dependencies blobs tốt hơn, luồng deploy cho microservices cập nhật liên tục có thể tiết kiệm băng thông registry và extracted layout phù hợp với tối ưu JVM như CDS trong các điều kiện được hỗ trợ.

**Chi phí** gồm một extraction stage, Dockerfile dài hơn, phụ thuộc `jarmode tools` và cấu trúc layer, thêm các bước cần debug, test và cập nhật khi framework/build plugin thay version. Trích xuất không tự đảm bảo image nhỏ hơn; thư viện vẫn phải nằm trong image để ứng dụng chạy.

## 10. Quy tắc Docker cache: thứ tự COPY thật sự quan trọng

Docker/BuildKit xét instruction và các inputs liên quan khi quyết định reuse cached result. Nếu một instruction mất cache, các bước downstream phụ thuộc vào trạng thái đã thay đổi thường phải chạy lại. Vì vậy, không nên đặt application code trước dependencies.

**Cách B đúng về thứ tự:**

~~~dockerfile
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./
~~~

**Cách không tối ưu để minh họa:**

~~~dockerfile
COPY --from=extractor /workspace/extracted/application/ ./
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
~~~

Ở thứ tự thứ hai, **application** nằm trước. Khi application đổi, các bước COPY sau có thể bị invalidated theo dependency chain dù bytes dependencies giữ nguyên. Không nên đổi thứ tự các lớp ngẫu nhiên chỉ để thấy lệnh vẫn chạy.

### 10.1. Spring Boot layers và OCI layers không trùng tuyệt đối

Bốn Spring Boot layers là logical groups. OCI image có thể chứa nhiều base image layers, metadata/history và các layer khác ngoài bốn COPY. Một số builder tối ưu/loại layer trống và compression có thể làm số layer thực tế khác với số logical groups.

Vì thế không xác minh thành công chỉ bằng câu “`docker history` phải có đúng bốn dòng”. Thay vào đó, kiểm tra Dockerfile COPY tách biệt, log cache, response runtime và nếu cần so sánh image layer digests.

### 10.2. Không nhầm với Gradle Build Cache

`./gradlew bootJar FROM-CACHE`, `:compileJava UP-TO-DATE` và Docker `CACHED` là ba cơ chế khác nhau:

- **Gradle UP-TO-DATE:** output task trong workspace chưa đổi.
- **Gradle FROM-CACHE:** output task được lấy từ Gradle Build Cache.
- **Docker CACHED:** kết quả Dockerfile instruction đã có trong Docker build cache.
- **OCI registry layer reuse:** registry/client có thể không upload/pull lại một blob đã tồn tại.

Một JAR được Gradle khôi phục từ cache vẫn có thể làm Docker COPY mất cache nếu nội dung hoặc metadata của nó khác với file từng được copy. Ngược lại, Docker có thể reuse dependency image layers dù `bootJar` vừa thực thi mới. Cần thu thập **log ở đúng tầng** khi đánh giá tối ưu.

## 11. Thực hành A/B: sửa một Controller để so sánh hai Dockerfile

Thí nghiệm được thiết kế để **chỉ application classes thay đổi**, còn dependency graph giữ nguyên. Kết quả cache phải được quan sát thật; không giả lập số giây hay kết luận `CACHED` chắc chắn.

### 11.1. Baseline v1

1. Giữ Controller trả `"image-v1"` và test kỳ vọng `image-v1`.
2. Chạy `./gradlew clean test bootJar` hoặc `.\gradlew.bat clean test bootJar`.
3. Build hai image:
   
~~~bash
docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar-v1 .
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers-v1 .
~~~

4. Chạy từng image và gọi endpoint `GET /version`, ghi lại body `image-v1`.
5. Lưu log Docker build, tên JAR, base image digest và thông tin cache store.

Nếu muốn kiểm tra cache của lần **build không có thay đổi**, chạy lại chính các lệnh `docker build` với cùng tag/context. Nhiều bước có thể hiện `CACHED` ở cả hai cách vì không có input đổi; đây không phải phép thử về tối ưu khi source thay đổi.

### 11.2. Thay code, giữ dependencies

Trong `VersionController.java`, thay:

~~~java
return "image-v1";
~~~

bằng:

~~~java
return "image-v2";
~~~

Trong `VersionControllerTest.java`, thay kỳ vọng:

~~~java
.andExpect(content().string("image-v1"));
~~~

bằng:

~~~java
.andExpect(content().string("image-v2"));
~~~

Sau đó:

~~~bash
./gradlew clean test bootJar

docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar-v2 .
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers-v2 .
~~~

Kiểm tra image mới, chọn host port không bị chiếm:

~~~bash
docker run --rm -p 8081:8080 docker-choice:layers-v2
~~~

Terminal khác:

~~~bash
curl -fsS http://localhost:8081/version
~~~

Response body phải là:

~~~text
image-v2
~~~

Thử tương tự với `docker-choice:jar-v2` (dừng container trước hoặc dùng host port khác). **Nếu một image vẫn trả `image-v1`, đó là lỗi build/artifact/caching/đường dẫn hoặc process cũ**, không được tuyên bố tối ưu thành công.

### 11.3. Kết quả dự kiến khi cache thực sự hoạt động

| Bộ phận | Dockerfile.jar | Dockerfile.layers |
| --- | --- | --- |
| JRE base image | Reuse nếu base digest không đổi | Reuse nếu base digest không đổi |
| COPY executable JAR | Phải xét file JAR mới, thường tạo layer mới | Extractor COPY nguồn và RUN extract thường phải chạy lại |
| Dependencies runtime files | Nằm chung trong layer toàn JAR | Có cơ hội reuse layer `dependencies` |
| Spring Boot loader files | Nằm chung trong layer toàn JAR | Có cơ hội reuse layer loader |
| Snapshot dependencies | Nằm chung trong layer toàn JAR | Có cơ hội reuse nếu snapshot bytes không đổi |
| Application classes | Thay đổi trong toàn JAR | Thay đổi ở layer `application` cuối |
| HTTP response | `image-v2` | `image-v2` |
| Time/pull bytes | Phải đo, không định sẵn | Có thể tốt hơn qua nhiều lần phát hành |

**Đọc Docker build logs:** với BuildKit, các dòng được reuse có thể hiện `CACHED`. Nếu builder không có cache hoặc bạn chạy `--no-cache`, không thể dùng sự vắng mặt của `CACHED` để kết luận Spring Boot layers sai. Muốn đo registry layer reuse, có thể so sánh image layer digests và lượng bytes upload/pull được ghi nhận bởi registry/build tool.

### 11.4. Thử thêm một dependency

Khi thêm hoặc nâng một library runtime trong Gradle/Maven, nhóm `dependencies` thường phải đổi. Dockerfile.layers có thể mất cache sớm hơn và các bước sau có thể cũng bị ảnh hưởng. Đây là **invalidation đúng** vì image có dependency graph mới, không phải lỗi tối ưu.

Hãy khôi phục dependency/controller/test về baseline sau thí nghiệm nếu đó là project thật.

## 12. Maven thay thế: vẫn dùng được cùng hai Dockerfile

Nếu project của bạn sử dụng Maven, Spring Boot Maven Plugin `repackage` hỗ trợ layered executable JAR tương đương với `bootJar`. Dưới đây là một POM **độc lập** thay cho `build.gradle`, dùng lại đúng ba file Java và test ở mục 5.

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>docker-choice-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
        <finalName>app</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                    <includeTools>true</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Ý nghĩa:** Starter Parent quản lý plugin/dependencies và cấu hình `repackage`; `<finalName>app</finalName>` giúp Maven tạo executable JAR `target/app.jar`. Maven Boot plugin tạo `BOOT-INF/layers.idx` theo mặc định với layering bật; `includeTools` cho tools mode Spring Boot 3.3. Nếu project chỉ import BOM mà không kế thừa Parent, hãy cấu hình version và execution `repackage` cho plugin tường minh.

Build và kiểm tra:

~~~bash
./mvnw --version
./mvnw clean verify
jar tf target/app.jar | grep '^BOOT-INF/layers.idx$'
java -Djarmode=tools -jar target/app.jar list-layers
~~~

Với Windows PowerShell, dùng `.\mvnw.cmd` và `Select-String` tương ứng. Mã Java không thay đổi vì Maven và Gradle đều sử dụng layout `src/main/java`, `src/test/java`.

**Build Docker từ Maven artifact:** giữ nguyên Dockerfile.jar và Dockerfile.layers, chỉ truyền path vào `ARG JAR_FILE`:

~~~bash
docker build --progress=plain \
    --build-arg JAR_FILE=target/app.jar \
    -f Dockerfile.jar -t docker-choice:maven-jar .

docker build --progress=plain \
    --build-arg JAR_FILE=target/app.jar \
    -f Dockerfile.layers -t docker-choice:maven-layers .
~~~

Đừng đặt `ARG JAR_FILE` thành một đường dẫn tùy tiện bên ngoài Docker build context, vì `COPY` không được đọc file nằm ngoài context. Nếu CI đặt artifact tại thư mục khác, phải chọn context và path sao cho hợp lệ hoặc copy artifact đã kiểm thử vào context staging.

**Lưu ý:** Dockerfile nguyên JAR **không yêu cầu Maven layer index**. Bạn có thể dùng cùng executable Maven JAR có `layers.idx` nhưng Dockerfile.jar sẽ không tận dụng nó. Đây là phép so sánh chính xác hơn giữa hai chiến lược Dockerfile.

## 13. Kotlin DSL thay cho Groovy DSL

Nếu project dùng `build.gradle.kts`, cấu hình Gradle tương đương cho `app.jar`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

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

tasks.test {
    useJUnitPlatform()
}

springBoot {
    mainClass.set("com.example.dockerchoice.DockerChoiceApplication")
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app.jar")
    layered {
        enabled.set(true)
    }
    includeTools.set(true)
}
~~~

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "docker-choice-demo"
~~~

Đây là **phương án thay thế** của Groovy DSL; không chèn hai DSL cùng lúc. Dockerfile và Java sources giữ nguyên. Nếu project có quy tắc repositories hoặc Java plugin đã khác, hợp nhất chỉ những phần cấu hình cần thiết thay vì ghi đè build configuration hiện hữu.

## 14. .dockerignore và đường dẫn artifact: lỗi nhỏ nhưng rất thường gặp

Vì cả hai Dockerfile copy **artifact đã build**, Docker build context phải chứa `build/libs/app.jar` (Gradle) hoặc `target/app.jar` (Maven).

File `.dockerignore` an toàn và dễ hiểu cho ví dụ:

~~~dockerignore
.git
.gradle
.idea
.vscode
src
.repro-check
**/*.log
build/classes
build/generated
build/reports
build/test-results
build/tmp
~~~

File này **cố ý không loại cả thư mục `build` hoặc `target`**, vì Dockerfile cần đọc JAR đã được build. Nếu tổ chức muốn chỉ gửi đúng một JAR làm build context, có thể tạo một **staging directory riêng** chứa artifact và Dockerfiles, rồi chạy `docker build` từ directory đó; cần điều chỉnh `ARG JAR_FILE` và các path phù hợp.

**Các lỗi điển hình:**

- `COPY failed: file not found`: chưa build, path/filename khác, context không có file, hoặc `.dockerignore` đã loại nó.
- `COPY build/libs/*.jar`: có thể vô tình chọn cả `-plain.jar` hoặc nhiều artifacts; tránh wildcard khi mục tiêu là một JAR.
- Docker build từ thư mục con: dấu `.` cuối lệnh không còn là project root, nên `COPY` tìm nhầm.
- Đổi `archiveFileName` trong Gradle hoặc `finalName` trong Maven nhưng Dockerfile vẫn dùng path cũ.
- Maven `target/app.jar.original`: không phải executable JAR cuối, đừng copy nhầm.
- Gradle `bootJar` bị disable, chỉ chạy `jar`: có thể tạo plain JAR thiếu Spring Boot launcher/nested libraries.
- Một lệnh CI chạy `docker build` **trước** `gradlew bootJar`: Docker nhận file JAR cũ từ build trước.

### Dùng Docker ARG đúng cách

`ARG JAR_FILE` trong hai Dockerfile chỉ là **build-time path selector**. Nó không có tác dụng đổi Java main class, Spring runtime profile hay dependencies trong JAR. Đổi `--build-arg JAR_FILE=...` có thể làm Docker cache thay đổi vì input COPY khác, nhưng không tự build project Java cho bạn.

Không đưa secrets vào `ARG` hoặc một `ENV` hard-coded chỉ để truyền mật khẩu: chúng có thể xuất hiện trong image history/metadata hoặc logs. Dùng secret manager hoặc Docker BuildKit secret mount ở build stage nếu bắt buộc truy cập tài nguyên riêng.

## 15. Image runtime: JRE, non-root và ENTRYPOINT

Một image Spring Boot tốt cần đúng **Java runtime**, đúng **entrypoint**, khả năng nhận signals và các quyền tệp thích hợp.

### 15.1. Chọn Java base image

- Ví dụ dùng `eclipse-temurin:17-jre`, phù hợp compiled Java 17 của Spring Boot 3.3.
- Production nên pin **digest** (và platform nếu cần) theo chính sách để tránh tag đổi âm thầm; đồng thời có lịch cập nhật image nhận bản vá bảo mật.
- Không chọn JRE nhỏ nhất một cách mù quáng: ứng dụng có thể cần fonts, locale, TLS certificates, timezone data hoặc native libraries.
- Không giả định image JRE có `sh`, `bash`, `curl` hoặc package manager; Dockerfile ví dụ **không cần** các công cụ ấy ở runtime.

### 15.2. Chạy bằng non-root user

Cả hai Dockerfile có:

~~~dockerfile
USER 10001:10001
~~~

Đây là numeric UID/GID không phải root. Với demo chỉ đọc JAR và dùng port 8080, nó thường phù hợp. Nếu app phải ghi log/files/uploads, cấp mount/path **có quyền ghi thích hợp** thay vì chạy root để chữa nhanh. JVM có thể cần thư mục tạm như `/tmp`; phải kiểm tra theo base image được chọn.

### 15.3. ENTRYPOINT đúng cho từng layout

| Artifact/runtime | ENTRYPOINT đúng cho ví dụ |
| --- | --- |
| Nguyên `/app/application.jar` | `["java","-jar","/app/application.jar"]` |
| Extracted layout dưới `/application` | `["java","-jar","/application/application.jar"]` |
| JAR tools mode ở extractor stage | `java -Djarmode=tools -jar application.jar extract --layers --destination extracted` |

Tools mode là **lệnh build-time**, không phải container runtime entrypoint. Với extracted layout, đừng copy thiếu `dependencies`/loader rồi chạy fat-JAR entrypoint như thể JAR mỏng chứa toàn bộ thư viện.

### 15.4. Biến môi trường và cấu hình Spring

Các giá trị runtime như `SPRING_PROFILES_ACTIVE`, database URL, credentials và tracing config nên được cấp từ deployment environment, không hard-code vào Dockerfile. `SPRING_PROFILES_ACTIVE=prod` là **Spring runtime profile**, **không thay đổi cách Dockerfile copy JAR hoặc thứ tự layers**.

**EXPOSE 8080** chỉ thông báo port, còn `docker run -p 8080:8080` mới publish cổng ra host. Trong Kubernetes, các objects như Service/Ingress quản lý network; đừng dựa vào EXPOSE để suy ra ứng dụng đã public ra Internet.

## 16. Hiệu quả thực tế: startup, size, transfer và cache

Có bốn thước đo khác nhau, không nên gộp thành “image tối ưu hơn” chung chung:

1. **Docker build time:** multi-stage extraction thêm chi phí, nhưng reuse image layers có thể giúp các lượt build sau nhanh hơn. Kết quả phụ thuộc cache backend.
2. **Registry push/pull bytes:** layered copy có thể reuse blob dependencies khi image ứng dụng đổi; nguyên JAR có thể phải chuyển một blob ứng dụng lớn. Registry có content-addressable storage, nên cần quan sát digest/bytes thực.
3. **Final image size:** tách lớp **không xóa thư viện**; hai cách đều có dependencies và JRE. Đừng hứa layered image luôn nhỏ hơn. Có thể giảm hoặc tăng chút tùy compression/layout.
4. **Startup time:** Spring Boot extracted layout có thể giảm overhead truy cập nested JARs và thuận lợi cho Class Data Sharing (CDS) trong một số workflow, nhưng không bảo đảm mọi ứng dụng đều startup nhanh hơn.

### 16.1. Đo cùng điều kiện

Để so công bằng:

- Cùng commit, cùng JDK/Boot/Gradle version và dependency graph.
- Cùng family/digest của JRE base image cho hai Dockerfile.
- Cùng CPU/memory limit khi chạy container.
- Cùng warm/cold cache policy; ghi rõ Docker BuildKit có được reuse cache không.
- Cùng endpoint smoke, profile, environment và dữ liệu ngoài.
- Không so image push qua mạng A với image pull qua mạng B rồi quy mọi chênh lệch cho layering.
- Đo qua nhiều lượt với cùng điều kiện, không rút kết luận từ một lần may mắn.

### 16.2. Không nhầm tổng image size với bytes chuyển mỗi lần

Một image layered có thể **không nhỏ hơn** image một fat JAR về tổng logical size, nhưng khi deploy version mới cùng dependency layers, registry/kube node có thể chỉ cần tải những blobs chưa có. Đây thường là lợi ích thực tế quan trọng hơn câu hỏi “`docker image ls` hiển thị bao nhiêu MB?”.

### 16.3. Không dùng cache để che thiếu reproducibility

Nếu `BOOT-INF/lib` chứa SNAPSHOT/changing dependencies, hoặc generated resources chèn timestamp hiện tại, Docker có thể mất cache dù source business không đổi. Kiểm soát dependency versions, resource generation và Gradle/Maven toolchain để bảo đảm không có biến động vô ý.

## 17. CI pipeline: build một artifact, kiểm thử rồi đóng hai image

Một pipeline thực tế nên tách ba bước:

~~~text
SOURCE / COMMIT
      |
      v
Build + unit/integration tests
      |
      v
One executable app.jar (immutable input của Dockerfile)
      |
      +---- Dockerfile.jar ----> image A
      |
      +---- Dockerfile.layers -> image B
      |
      v
Smoke test từng image
      |
      v
Chọn phương án được phê duyệt + scan/sign/push/deploy
~~~

**Vì sao “build một JAR” quan trọng?** Nếu A build từ commit X và B build từ commit Y, mọi so sánh cache/size/startup sẽ lẫn khác biệt ứng dụng. Nên build artifact một lần, lưu checksum và dùng đúng file đó cho cả hai Dockerfiles. CI có thể dựng cả hai chỉ trong giai đoạn đánh giá; production thường chọn **một** workflow đã chuẩn hóa.

### 17.1. Các command cốt lõi cho CI Linux

~~~bash
set -eu

./gradlew --no-daemon clean test bootJar
test -f build/libs/app.jar
jar tf build/libs/app.jar | grep -q '^BOOT-INF/layers.idx$'

docker build --progress=plain -f Dockerfile.jar -t docker-choice:jar-ci .
docker build --progress=plain -f Dockerfile.layers -t docker-choice:layers-ci .
~~~

Đây là **đoạn pipeline**, không phải workflow YAML hoàn chỉnh. Trong shell có `set -o pipefail`, lệnh `jar tf | grep -q` đôi khi có thể gặp broken pipe nếu reader thoát sớm; để nghiêm ngặt, dùng `jar tf ... > jar-entries.txt` rồi `grep -q ... jar-entries.txt`.

### 17.2. Smoke test không cứng thời gian chờ

Một cách thủ công:

~~~bash
docker run --rm -p 8080:8080 docker-choice:jar-ci
~~~

Terminal khác:

~~~bash
curl -fsS http://localhost:8080/version
~~~

Thực hiện tương tự với `docker-choice:layers-ci` sau khi dừng container trước. Với CI automation, có thể chạy container detached và **poll endpoint với timeout có giới hạn**, lưu logs và stop/remove container trong cleanup ngay cả khi test fail; không dùng sleep cố định một lần rồi mặc định server đã sẵn sàng.

### 17.3. Lưu dấu vết

- Commit SHA và nguồn dependency/BOM.
- JDK, Spring Boot plugin, Maven/Gradle Wrapper versions.
- SHA-256 của `app.jar` đã test.
- Dockerfile path và build-arg JAR_FILE.
- Base image digest, target platform, builder/cache backend.
- BuildKit logs cho các COPY instructions.
- HTTP smoke result, test reports, image tag/digest và trạng thái scan.
- Deployment reference theo image digest bất biến thay vì chỉ tên tag có thể bị ghi đè.

**Đừng chỉ kiểm tra `docker build` exit 0** rồi gọi image “đã xác minh”. Archive có thể được copy đúng cú pháp nhưng Spring config lỗi hoặc port khác, và startup chỉ phát hiện khi chạy container.

## 18. Các lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Docker `COPY` báo source not found | Chưa build JAR, build context sai, `.dockerignore` loại JAR | Kiểm tra `build/libs/app.jar` hoặc `target/app.jar` và dấu `.` của `docker build` |
| Image A báo `no main manifest attribute` | Copy plain JAR thay Boot executable JAR | Dùng Gradle `bootJar`/Maven `repackage`, xem manifest |
| Image B báo `Unsupported jarmode 'tools'` | Spring Boot/plugin khác phiên bản, tools JAR thiếu hoặc `includeTools=false` | Kiểm tra Boot 3.3 tools mode, `BOOT-INF/layers.idx` và `spring-boot-jarmode-tools` |
| Tools extract không chạy với fully executable JAR | Archive có launch script được prepend | Tắt `launchScript()`/fully-executable option cho artifact định extract |
| Image B `COPY --from` báo không có thư mục | Lệnh extract thiếu `--layers`, path sai, layer custom tên khác | Chạy `list-layers`, xem output extractor và COPY path |
| Image B không tìm thấy `application.jar` ở runtime | Copy thiếu `application/` hoặc dùng layout khác | Kiểm tra Spring Boot 3.3 extracted layout và `ENTRYPOINT` |
| Image B `ClassNotFoundException` | Một trong các nhóm dependencies/loader không được COPY hoặc file bị ghi đè sai | Kiểm tra lần lượt bốn COPY, so `java -jar` với fat JAR nguồn |
| Chạy B thấy lỗi ở `JarLauncher` | Dùng entrypoint theo `layertools` cũ cho tools extraction mới | Theo Boot 3.3, chạy extracted `application.jar` với `java -jar` |
| Dockerfile A và B đều lỗi HTTP | Có thể ứng dụng/port/profile lỗi, không liên quan layering | Chạy JAR trên host và đọc container startup log |
| Cả hai image cùng trả response cũ | Build/copy nhầm JAR cũ hoặc container cũ còn chạy | Chạy lại `clean test bootJar`, kiểm tra build context và container mapping |
| Cache B không hit khi Controller đổi | Cache store không có, base image đổi, generated metadata không ổn định | Đọc BuildKit logs, kiểm tra layer bytes, builder/registry cache |
| Dependencies layer đổi liên tục | SNAPSHOT động, timestamp trong nested JAR, thay BOM | Pin/lock dependencies và rà reproducible outputs |
| `Dockerfile.layers` có nhiều COPY nhưng size không giảm | Layering nhằm tái sử dụng blobs, không xóa libs | Đo push/pull bytes và digests thay vì chỉ `docker image ls` |
| Không mở được HTTP từ máy host | Quên `-p`, app dùng port khác hoặc container chưa ready | `docker run -p HOST:CONTAINER`, logs và `curl` |
| Container không chạy với non-root UID | Không có quyền đọc app/libs, ghi tmp/upload không được | Kiểm tra USER/file permissions/mount, cấp quyền tối thiểu |
| CI runner mới luôn phải rebuild | Không có persisted/remote Docker build cache | Cấu hình cache backend/registry cache theo policy, không hứa CACHED |
| A và B dùng khác JRE runtime | Dockerfiles chọn hai base image khác nhau | Pin cùng Java version/base digest để so sánh có ý nghĩa |
| Image B thiếu dependency sau custom layering | Phân nhóm sai hoặc nhầm `include/exclude` của Boot layering với loại artifact | Kiểm tra archive gốc, index, extracted directories và runtime |
| Deploy chỉ B fail nhưng local chạy | Khác platform, env, permissions hoặc classpath trong extracted image | Ghi full logs, xem image digests, chạy smoke trong môi trường gần production |

### Quy trình điều tra theo tầng

1. **JAR:** có `build/libs/app.jar` và chạy được bằng `java -jar` trên Java 17 không?
2. **Layer metadata:** có `BOOT-INF/layers.idx`, list-layers thấy nhóm mong đợi không?
3. **Tools:** `-Djarmode=tools ... extract --layers` có chạy và tạo thư mục đúng không?
4. **Dockerfile:** build context chứa đúng JAR? `COPY` chọn đúng file? Runtime có extracted application.jar không?
5. **Runtime:** container logs có ClassNotFound/port/config errors? HTTP response đúng không?
6. **Cache:** BuildKit có cache store phù hợp? Logs chỉ ra instruction nào reused/không?
7. **Security/compatibility:** Java/architecture/base image/UID/secrets đúng không?
8. **CI:** image cuối được deploy chính là image đã smoke test hay pipeline rebuild lại một bản khác?

Không sửa nhiều layer, Java version, dependencies và Dockerfile cùng lúc nếu chưa xác định tầng nào có lỗi.

## 19. Dockerfile security và vận hành: không nên đánh đổi vì cache

**Nguyên tắc chung cho cả A và B:**

- **Base image được kiểm soát:** dùng JRE phù hợp, scan CVEs, theo dõi digest và update theo lịch; không pin bản dễ bị tấn công vô thời hạn chỉ để cache ổn.
- **Run as non-root:** UID cụ thể, cấp quyền đọc/ghi tối thiểu; không dùng root khi không cần.
- **Không đưa credentials vào image:** secret có thể còn trong image layer/history dù bị xóa ở layer sau. Dùng runtime secrets hoặc BuildKit secret mount theo policy.
- **Không copy cả repository:** giới hạn context, dùng `.dockerignore` hoặc staging directory; đặc biệt tránh `.git`, `.env`, Maven/Gradle credentials.
- **Không bật debug/profiles production sai:** tùy chọn Spring runtime như `SPRING_PROFILES_ACTIVE` được quản lý tại deployment; không thay Java entrypoint.
- **Đảm bảo logs gửi ra stdout/stderr:** Docker/Kubernetes thu thập logs; không nên mặc định ghi file trong image filesystem không được mount.
- **Kiểm tra multi-arch:** image cho `linux/amd64` khác `linux/arm64` có thể có native/JDK dependencies khác, ảnh hưởng reproducibility và cách cache.
- **Đặt health/readiness thật sự:** `EXPOSE` không phải health check; với Kubernetes cần probes phù hợp, không tùy tiện public Actuator management endpoints.
- **Chạy image đã test:** store immutable image digest, tránh build lại sau khi đã chạy tests mà không có provenance.
- **Không lạm dụng optimization:** nếu Dockerfile B quá phức tạp nhưng hiệu quả gần bằng A, ưu tiên cách đơn giản và kiểm thử tốt.

### Về Cloud Native Buildpacks

Spring Boot còn hỗ trợ `bootBuildImage` (Gradle) hoặc `spring-boot:build-image` (Maven) để tạo image qua **Cloud Native Buildpacks** thay vì viết Dockerfile thủ công. Buildpacks có builder/run images, cache và cách chia lớp riêng. Đó là **lựa chọn thứ ba** khi tổ chức muốn chuẩn hóa image packaging và giảm tự bảo trì Dockerfile.

Không coi Buildpacks tạo ra đúng image/layer digests giống B; cần chọn **một** pipeline được tổ chức hỗ trợ rồi đánh giá hiệu quả thực tế. Bài này cố ý so sánh **hai lựa chọn Dockerfile** trên cùng executable JAR.

## 20. Bài thực hành và tiêu chí hoàn thành

Thực hiện trong branch thử nghiệm của project Spring Boot có Docker và Java 17:

1. Tạo `DockerChoiceApplication`, `VersionController`, `VersionControllerTest` theo mục 5.
2. Chọn Gradle Groovy/Kotlin hoặc Maven như các phương án đã nêu, build **một** executable `app.jar` đã chạy test.
3. Chạy `java -jar app.jar` trên máy với JRE phù hợp, xác nhận `GET /version` trả `image-v1`.
4. Tạo `Dockerfile.jar` và build image A, chạy container, xác minh response `image-v1`.
5. Kiểm tra Boot archive có `BOOT-INF/layers.idx` và tools dependency, chạy `list-layers`.
6. Trích xuất thử bằng `extract --layers`, quan sát bốn groups và extracted `application.jar`.
7. Tạo `Dockerfile.layers` và build image B, chạy container, xác minh response giống image A.
8. Chạy lại `docker build --progress=plain` không thay source để thấy baseline caching behavior.
9. Đổi Controller/test sang `image-v2`, build lại cùng JAR output, rồi build hai image version mới.
10. Dùng logs so sánh toàn-JAR COPY của A với bốn COPY của B; ghi rõ instruction có cache hit/miss theo môi trường thực.
11. Chạy image A-v2 và B-v2, xác minh **cả hai cùng trả `image-v2`**.
12. Thử tăng/đổi một dependency, ghi lại vì sao `dependencies` layer của B cần cập nhật.
13. Chỉ ra Docker `CACHED`, Gradle `FROM-CACHE` và registry blob reuse là **những cache khác nhau**.
14. Kiểm tra Java runtime version, non-root permissions, port mapping, secret handling và artifact image digests.
15. Viết kết luận ngắn: nhóm của bạn nên dùng A hay B dựa trên tốc độ đổi mã, lượng dependencies, network/registry/CI cache và chi phí vận hành.
16. Khôi phục các thay đổi thử nghiệm ở code/tests/dependencies và không để lại image chưa được scan làm bản triển khai production.

**Tiêu chí đạt:** bạn giải thích được chính xác tại sao **layered archive không tự tạo Docker layers**, chạy được cùng một Spring Boot JAR theo cả hai Dockerfile, so sánh cache có bằng chứng, và đưa ra quyết định **đúng hoàn cảnh** chứ không mặc định mọi ứng dụng phải trích xuất trước khi tạo image.

## Tài liệu chính thức tham khảo

- [Spring Boot 3.3 – Dockerfiles](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3 – Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/oci-image.html)
- [Docker Docs – Build Cache](https://docs.docker.com/build/cache/)
- [Docker Docs – Optimize Cache Usage](https://docs.docker.com/build/cache/optimize/)
- [Docker Docs – Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker Docs – Dockerfile Reference](https://docs.docker.com/reference/dockerfile/)
- [OCI Image Specification](https://github.com/opencontainers/image-spec)
