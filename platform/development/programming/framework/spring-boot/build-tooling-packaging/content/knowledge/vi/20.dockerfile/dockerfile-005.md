# Sắp xếp COPY theo lớp để tăng khả năng tái sử dụng cache trong Dockerfile cho Spring Boot

## 1. Mục tiêu: thay đổi source mà không phải làm lại mọi thứ

Khi đóng gói ứng dụng Spring Boot thành container image, một lỗi tối ưu hóa phổ biến là **chép toàn bộ source vào image quá sớm**:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -ntp package
```

Nếu `src/main/java` hoặc một file bất kỳ mà lệnh `COPY . .` đưa vào image thay đổi, lệnh `COPY` này có thể không còn dùng được cache. Những bước ở phía sau, gồm `RUN mvn package`, phải được đánh giá lại trong một trạng thái filesystem mới. Kết quả: thay đổi một dòng Java cũng có thể dẫn đến nhiều công việc phụ thuộc không cần thiết, nhất là khi thư viện tải từ mạng tốn thời gian.

**Chiến lược cốt lõi:**

> Đặt **những file và thao tác ít thay đổi, tốn chi phí** ở đầu Dockerfile; đưa **những file thay đổi thường xuyên** như `src/` và application resources vào các lệnh `COPY` sau cùng.

Ví dụ mô hình tối ưu ở **build stage**:

```dockerfile
COPY pom.xml ./
RUN mvn -B -ntp dependency:go-offline
COPY src/ ./src/
RUN mvn -B -ntp package
```

Còn ở **runtime image**, Spring Boot hỗ trợ tách executable JAR thành những **application layers** rồi `COPY` theo thứ tự:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Phần lớn dependency có phiên bản cố định thay đổi ít hơn application classes. Vì thế nhiều lần đổi code có thể tái sử dụng image layers của dependency, giảm lượng dữ liệu phải rebuild và tải lên/tải xuống registry.

Bài học phân biệt rõ **hai nơi khác nhau có thể tái sử dụng cache**:

1. **Cache lúc Docker build từ source:** tránh giải quyết/download dependency không cần thiết khi chỉ sửa Java code.
2. **Cache của final runtime image:** tránh tạo/đẩy lại những lớp JAR dependency không đổi dù file executable JAR tổng thể có thể thay đổi.

Hai cách bổ trợ nhau nhưng **không phải một cơ chế**. Ví dụ dùng Docker BuildKit, Java 17 và Spring Boot 3.5.x; cần điều chỉnh tên file/phiên bản nếu project khác.

## 2. Docker cache hoạt động ra sao với COPY?

### 2.1. Dockerfile là chuỗi bước có quan hệ phụ thuộc

Đơn giản hóa cho người học:

```text
FROM base-image
    |
    v
COPY stable-build-files
    |
    v
RUN dependency-resolution
    |
    v
COPY application-source
    |
    v
RUN compile-and-package
    |
    v
COPY artifact into runtime-image
```

Docker/BuildKit tính cache dựa trên lệnh và input của bước tương ứng. Với `COPY`/`ADD`, builder xét file content và metadata phù hợp (ví dụ mode/permissions). Chỉ thay đổi **thời điểm sửa file `mtime`** thông thường không đủ làm invalidation. Với `RUN` thông thường, BuildKit không mở mọi package đã tải bên trong container để xác nhận repository ngoài có bản mới; cache phụ thuộc instruction/state và các input đã được mô hình hóa.

Khi một bước không còn cache hợp lệ, những bước phụ thuộc **ở phía sau** cần tính/kiểm tra lại. BuildKit có thể tối ưu độc lập trong một số trường hợp, nhưng cách suy nghĩ an toàn là: **một thay đổi ở lớp sớm thường làm tăng công việc ở phần sau**.

### 2.2. Hai Dockerfile cùng chạy nhưng cache behavior khác nhau

**Không tối ưu:**

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -ntp dependency:go-offline
RUN mvn -B -ntp package
```

Vì `COPY . .` sao chép cả source lẫn POM trước bước dependency, mỗi khi Java source đổi, layer bên dưới `dependency:go-offline` có thể bị invalidated.

**Tối ưu theo mức độ thay đổi:**

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml ./
RUN mvn -B -ntp dependency:go-offline
COPY src/ ./src/
RUN mvn -B -ntp package
```

Khi chỉ `src/...` đổi:

- `COPY pom.xml` thường vẫn trúng cache.
- `RUN dependency:go-offline` có thể dùng kết quả cache trước đó.
- `COPY src` và `RUN package` cần phản ánh source mới.

Khi `pom.xml` đổi, lớp khai báo dependency và bước ở sau thường phải được tính lại. **Đó là điều đúng** vì dependency graph hoặc build plugin có thể đã đổi.

Đặt những lệnh tốn chi phí ở phía trước **không có nghĩa cố tình giấu dependencies mới khỏi build**: dependency manifest vẫn là input của bước resolve, nên đổi POM phải làm invalidate.

### 2.3. Cần phân biệt cached layer với cache của package manager

Hai ví dụ trên chưa có BuildKit cache mount. Nếu `RUN dependency:go-offline` bị invalidated, Maven có thể lại cần tải artifact. BuildKit `--mount=type=cache` có thể giữ thư mục Maven repository giữa các lần thực thi:

```dockerfile
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp dependency:go-offline
```

- **Layer cache** giúp **bỏ qua toàn bộ lệnh** khi instruction và inputs giống nhau.
- **Cache mount** giúp **tiết kiệm lượt tải về** khi lệnh phải chạy lại, bằng cách tái sử dụng dữ liệu trong thư mục cache.
- Cache mount **không đi vào final image** và không được coi là input bất biến được publish cùng artifact.
- Cache mount có thể bị dọn, không tồn tại trên CI runner mới hoặc có trạng thái khác nhau; build phải vẫn đúng khi cache rỗng.

Đó là lý do nên dùng cả **COPY ordering** và **cache mounts** thay vì chọn một trong hai.

## 3. Chuẩn bị project Spring Boot Java 17 có thể chạy được

Tạo dự án tên `cache-copy-demo` với Spring Boot 3.5.x, Java 17, Maven, dependency Spring Web và Spring Boot Starter Test. Thư mục:

```text
cache-copy-demo/
├── pom.xml
├── src/
│   ├── main/java/com/example/cache/
│   │   ├── CacheCopyApplication.java
│   │   └── GreetingController.java
│   └── test/java/com/example/cache/
│       └── GreetingControllerTest.java
├── Dockerfile.multi
├── Dockerfile.multi.dockerignore
├── Dockerfile.layers
└── Dockerfile.layers.dockerignore
```

Các Dockerfile có **nhiệm vụ độc lập**. `Dockerfile.multi` tự build Maven trong container. `Dockerfile.layers` yêu cầu một executable JAR đã được build trên máy/CI, rồi tách nó thành image layers. Không cố chạy cả hai trong một lệnh.

### 3.1. Maven POM đầy đủ

File `pom.xml`:

```xml
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

    <groupId>com.example</groupId>
    <artifactId>cache-copy-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

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

`spring-boot-starter-parent` quản lý dependency/plugin versions; `spring-boot-maven-plugin` tạo executable archive khi chạy Maven package theo parent conventions. Không cần sửa main class manifest bằng tay.

### 3.2. Spring Boot main class

File `src/main/java/com/example/cache/CacheCopyApplication.java`:

```java
package com.example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheCopyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheCopyApplication.class, args);
    }
}
```

### 3.3. REST controller

File `src/main/java/com/example/cache/GreetingController.java`:

```java
package com.example.cache;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public String hello() {
        return "cache-copy-ok";
    }
}
```

HTTP GET `/hello` trả response body chính xác là:

```text
cache-copy-ok
```

Response body **không phải toàn bộ stdout** của Java/Spring Boot. Server log còn tùy version và môi trường.

### 3.4. JUnit test

File `src/test/java/com/example/cache/GreetingControllerTest.java`:

```java
package com.example.cache;

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
class GreetingControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsGreeting() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("cache-copy-ok"));
    }
}
```

Ví dụ build và test thông qua Maven vì cần Spring Boot/JUnit dependencies. Đây không phải chương trình có thể biên dịch cả dự án chỉ với `javac` của JDK trần. Nếu chỉ muốn kiểm chứng môi trường Java, `java -version` hoặc một chương trình Java Standard Library đơn giản là phép thử riêng; không thay thế việc test Spring Boot.

## 4. Dockerfile.multi: COPY manifest trước, source sau

### 4.1. Dockerfile hoàn chỉnh cho Maven multi-stage

File `Dockerfile.multi`:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: compile và package. Không đưa Maven/JDK build tools vào runtime.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

# Bước ổn định: POM đổi ít hơn source.
COPY pom.xml ./

# Pre-fetch dependencies và build plugins; cache mount giữ Maven repo.
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp dependency:go-offline

# Bước thay đổi thường xuyên hơn:
COPY src/ ./src/

# Maven package vẫn chạy unit tests mặc định.
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp package

# Stage 2: image chỉ có Java runtime và executable archive.
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/target/cache-copy-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Vì sao thứ tự này tốt?**

1. `FROM`/`WORKDIR` gần đầu thường ổn định; nếu đổi base image digest/JDK tag, những lớp phụ thuộc cần được xây lại — đúng vì runtime/build environment đã đổi.
2. `COPY pom.xml ./` chỉ đặt **dependency manifest** vào build stage. Bước Maven dependency resolution không phải đọc toàn bộ `src/` để tìm dependencies.
3. `RUN --mount=type=cache,... dependency:go-offline` dùng cache mount cho các artifact Maven. Khi source thay đổi mà POM giữ nguyên, bước này có thể **CACHED**, không chạy lại.
4. `COPY src/ ./src/` đưa application source vào **sau** bước đắt tiền ít thay đổi.
5. `RUN mvn package` compile/test/package lại khi source thay đổi, như mong đợi; không skip test để đánh lừa thời gian build.
6. `COPY --from=build ...app.jar` chỉ đưa artifact đã build vào **runtime stage**. Maven executable và `/root/.m2` không đi vào final image.

**Giới hạn của `dependency:go-offline`:** goal này cố resolve plugins/dependencies phục vụ offline, nhưng không bảo đảm 100% mọi artifact động được plugin yêu cầu khi thực thi goal sau đó đều đã sẵn. Một cache mount giúp giảm downloads khi phát sinh những dependency phụ ở lệnh `package`; build vẫn cần truy cập repository tin cậy khi thiếu dữ liệu.

**Không đồng nhất “CACHED” với “không kiểm tra mã”.** Khi source mới đi vào `COPY src`, Maven package thực thi theo input của bước mới, gồm unit tests như trong ví dụ. Nếu bạn cố chạy `mvn package -DskipTests` để tăng tốc, đó là thay đổi chính sách kiểm thử, **không phải** lợi ích của COPY ordering.

### 4.2. Dockerfile-specific ignore file cho Maven build

File `Dockerfile.multi.dockerignore` ở **cùng thư mục với Dockerfile.multi**:

```dockerignore
.git
.idea
.vscode
.gradle
build
target
*.log
.env
.env.*
```

Docker hỗ trợ tên file ignore theo Dockerfile: `Dockerfile.multi.dockerignore` áp dụng khi bạn build với `-f Dockerfile.multi`, và có ưu tiên so với `.dockerignore` ở root nếu cả hai tồn tại.

**Vì sao phải bỏ `target` khỏi build context?** Stage Maven ở mục 4 sẽ tự compile và tạo JAR. Một file `target/` cũ ở máy phát triển không cần được gửi vào builder. Nếu dùng `COPY . .` vô tình và `target` không được ignore, build outputs từ lần trước có thể tạo cache miss không liên quan source.

Không loại `pom.xml` hoặc `src/`: Dockerfile cần cả hai. Với Maven project thực tế có `.mvn/` (extensions, maven.config), file settings nội bộ hoặc multi-module, phải bổ sung các file cần thiết cho Maven trước khi resolve dependency; **đừng bỏ một config thực sự ảnh hưởng build chỉ để tăng cache hit**.

### 4.3. Build và chạy

Từ root project:

```bash
docker build --progress=plain \
    -f Dockerfile.multi \
    -t cache-copy-demo:multi \
    .

docker run --rm -p 8080:8080 cache-copy-demo:multi
```

Ở terminal khác:

```bash
curl -s http://localhost:8080/hello
```

Response body: `cache-copy-ok`. Dấu `\` nối dòng dành cho Unix/macOS. Trên Windows PowerShell, nhập `docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .` trên một dòng, rồi gọi `docker run` và `curl.exe` phù hợp.

**Dấu chấm cuối lệnh `docker build ... .` là build context**; `COPY pom.xml` tra file ở root context, không phải ở một thư mục bất kỳ do `WORKDIR` quyết định. Cần Docker Engine/BuildKit hoạt động và mạng để lần đầu tải base images/Maven dependencies.

## 5. Đo hành vi cache của Dockerfile.multi

Thực hiện theo thứ tự, không cần đoán từ thời gian:

### 5.1. Lượt đầu: tạo cache

```bash
docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .
```

Các lớp trước chưa có trong cache có thể tải dependencies và compile/test. Log BuildKit hiển thị những bước `COPY pom.xml`, `RUN ...dependency:go-offline`, `COPY src` và `RUN ...package`.

### 5.2. Lượt thứ hai: không đổi source

Chạy lại chính lệnh build:

```bash
docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .
```

Khi cache còn sẵn và inputs không đổi, nhiều bước hiển thị **`CACHED`**. Một ví dụ log rút gọn (không phải stdout cố định):

```text
#7 [build 3/5] COPY pom.xml ./
#7 CACHED
#8 [build 4/5] RUN --mount=type=cache,... dependency:go-offline
#8 CACHED
#9 [build 5/5] COPY src/ ./src/
#9 CACHED
```

Đừng yêu cầu số thứ tự bước giống ví dụ: Docker/BuildKit quyết định số bước, thứ tự in log và chi tiết nền tảng khác nhau.

### 5.3. Lượt thứ ba: chỉ sửa controller

Trong `GreetingController.java`, đổi response body thành một chuỗi khác, đồng thời cập nhật expected string ở `GreetingControllerTest.java` để test vẫn xác nhận behavior mới. Build lại:

```bash
docker build --progress=plain -f Dockerfile.multi -t cache-copy-demo:multi .
```

Kỳ vọng **`COPY pom.xml` và `dependency:go-offline` vẫn có cơ hội CACHED**; `COPY src` và `RUN package` cần xử lý code mới. Sau khi chạy image mới, endpoint trả chuỗi mới. Việc build thành công nhưng ứng dụng trả chuỗi cũ là **lỗi cần kiểm tra**: container cũ chưa được dừng, tag image chưa cập nhật hoặc đang gọi nhầm cổng.

### 5.4. Lượt thứ tư: thay pom.xml

Thêm một dependency mới cần thiết hoặc đổi version có chủ đích trong POM, rồi build. Khi `COPY pom.xml` thấy nội dung mới, lớp dependency prefetch phải được tính lại theo input mới; các lớp phụ thuộc ở phía sau cũng bị ảnh hưởng. Cache mount Maven có thể giảm lượt tải vì phần lớn JAR cũ vẫn nằm trong `/root/.m2/repository`.

**Sau thí nghiệm, khôi phục source/POM về trạng thái đã kiểm thử.** Đừng commit dependency giả chỉ để thấy cache miss. Một Dockerfile tốt không phải Dockerfile “luôn CACHED”, mà là Dockerfile invalidate **đúng khi input liên quan thay đổi**.

## 6. Image từ executable JAR đã build sẵn: cách đơn giản nhất

Nếu CI đã chạy Maven/Gradle và tạo executable JAR **trước** khi gọi Docker, bạn không cần compile lần nữa trong container. Dockerfile tối giản:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/cache-copy-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Cách này hợp lệ và phù hợp dịch vụ nhỏ; chỉ cần một lớp chứa **toàn bộ** executable JAR. Nhưng mỗi khi source làm thay đổi JAR, toàn bộ blob `app.jar` đổi và layer chứa nó có thể phải build/push lại — dù `BOOT-INF/lib` bên trong gần như không đổi.

**Đây chính là lý do Spring Boot có layered executable JAR.** Chúng ta muốn các dependency ổn định trở thành Docker layers riêng để khi application classes đổi, image layers của dependency có thể tái sử dụng.

Không bắt buộc **mọi** dự án Spring Boot phải dùng layered image: nếu JAR nhỏ, CI/CD không cần tối ưu pull/push, chi phí trích xuất và bảo trì Dockerfile nhiều stage có thể lớn hơn lợi ích. Hãy đo trường hợp thật.

## 7. Layered executable JAR: lớp dependency ổn định trước, application sau

Spring Boot Maven/Gradle Plugin có cơ chế **layered JAR**. Một executable JAR vẫn chứa:

```text
BOOT-INF/classes/
BOOT-INF/lib/
BOOT-INF/layers.idx
META-INF/MANIFEST.MF
```

`BOOT-INF/layers.idx` mô tả nội dung nào thuộc layer nào. Mặc định các lớp được sắp như sau:

| Layer Spring Boot | Thường chứa | Tần suất thay đổi |
|---|---|---|
| `dependencies` | Thư viện third-party không phải SNAPSHOT | Thường thấp khi lock/version quản lý tốt |
| `spring-boot-loader` | Boot Loader classes | Thường chỉ đổi khi nâng Spring Boot/packager |
| `snapshot-dependencies` | Dependency có version chứa SNAPSHOT | Có thể thay đổi nhiều hơn stable deps |
| `application` | Application classes/resources và local module dependencies | Thay đổi thường xuyên khi sửa code |

Thứ tự mặc định được chọn theo mức độ thay đổi kỳ vọng. **Không bảo đảm** SNAPSHOT dependency nào cũng thay đổi liên tục, hoặc application layer lúc nào cũng nhỏ; nhưng nó là quy ước tốt để bắt đầu.

Các ý quan trọng:

1. `layers.idx` là **metadata của archive**, không tự tạo bốn Docker layers chỉ vì JAR được chép nguyên khối vào image.
2. Để tận dụng bốn lớp, Dockerfile cần **extract layered JAR** rồi thực hiện những `COPY --from` tách biệt.
3. Spring Boot 3.5 dùng `spring-boot-jarmode-tools` và `-Djarmode=tools` để liệt kê/extract; **không** dùng `jarmode=layertools` từ những tài liệu Boot cũ.
4. Plugin tạo layered archive mặc định khi packaging theo tài liệu Spring Boot 3.5, trừ khi bạn tắt layering hoặc loại tools dependency.
5. JAR dùng jarmode tools không được là **fully executable archive có launch script prepended**; nếu đang dùng Spring Boot launch script, cần tắt cấu hình đó cho đường extraction.

Kiểm tra JAR bằng JDK:

```bash
jar tf target/cache-copy-demo-0.1.0-SNAPSHOT.jar
java -Djarmode=tools -jar target/cache-copy-demo-0.1.0-SNAPSHOT.jar list-layers
```

Khi có tools mode và index phù hợp, `list-layers` cho biết các layer mà công cụ hiểu. Nếu `Unknown mode` hoặc command không tồn tại, kiểm tra Spring Boot version, file artifact và việc tools dependency/layers bị exclude.

## 8. Dockerfile.layers: COPY bốn lớp runtime image theo thứ tự ổn định → thay đổi

### 8.1. Dockerfile hoàn chỉnh từ JAR Maven đã build sẵn

Đặt file `Dockerfile.layers` cùng root project:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: chỉ dùng để giải nén layered executable JAR.
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /workspace
COPY target/cache-copy-demo-0.1.0-SNAPSHOT.jar application.jar
RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

# Stage 2: runtime image với bốn COPY tách biệt.
FROM eclipse-temurin:17-jre
WORKDIR /application

# Ít thay đổi nhất trước:
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./

# Thay đổi thường xuyên hơn sau:
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
```

**Vì sao entry point là `application.jar` mà không phải `org.springframework.boot.loader.launch.JarLauncher`?** Với Spring Boot 3.5, lệnh `jarmode=tools extract --layers` tạo cấu trúc runtime có **application.jar nhỏ làm entry point** và các class/JAR được phân thành thư mục layer. Đây là bố cục mà tài liệu Dockerfiles của Spring Boot 3.5 sử dụng; đừng ghép `java -cp ... JarLauncher` từ tutorial Boot cũ vào ví dụ này.

**Không hiểu sai hiệu quả cache:** Khi code thay đổi, **file executable JAR nguyên gốc đổi**, nên `COPY ...application.jar` ở **extractor stage** và `RUN extract` có thể phải chạy lại. Nhưng trong **final runtime stage**, các layer `dependencies`/`spring-boot-loader` có thể vẫn chứa bytes giống hệt và được BuildKit tái sử dụng, trong khi `application` thay đổi. Hai mục tiêu cache khác nhau: cache của bước extraction và cache của runtime layer data.

### 8.2. Ignore file riêng cho Dockerfile.layers

File `Dockerfile.layers.dockerignore`:

```dockerignore
.git
.idea
.vscode
.gradle
.mvn
src
build
*.log
.env
.env.*
target/*
!target/cache-copy-demo-0.1.0-SNAPSHOT.jar
```

Lệnh `COPY target/cache-copy-demo-0.1.0-SNAPSHOT.jar` cần file JAR trong build context. **Không được giữ quy tắc `target` bị ignore toàn bộ** từ Dockerfile.multi cho đường này. Dockerfile-specific ignore file giúp hai lối build giữ context phù hợp:

- `Dockerfile.multi.dockerignore`: bỏ `target`, **giữ `pom.xml` và `src`**.
- `Dockerfile.layers.dockerignore`: **giữ đúng executable JAR** đã build trong `target`, bỏ những file không cần.

Dockerfile-specific ignore file **có ưu tiên** so với root `.dockerignore` khi đúng tên và cùng vị trí Dockerfile. Nếu Docker version/build frontend quá cũ không hỗ trợ đúng cơ chế, hãy kiểm tra context và dùng ignore strategy phù hợp trước khi build.

### 8.3. Build và chạy

Trước tiên build JAR trên máy/CI với Maven Wrapper:

```bash
./mvnw clean package
```

Sau đó:

```bash
docker build --progress=plain \
    -f Dockerfile.layers \
    -t cache-copy-demo:layers \
    .

docker run --rm -p 8080:8080 cache-copy-demo:layers
```

Trong terminal khác:

```bash
curl -s http://localhost:8080/hello
```

Response body mong đợi là `cache-copy-ok`. Không chạy song song container `:multi` và `:layers` cùng bind host port 8080; dừng instance cũ trước, hoặc đổi port mapping.

### 8.4. Tại sao layer có thể được tái sử dụng?

Docker image là tập các lớp, nên các bước tách riêng:

```text
FROM JRE
  + dependencies/             [ổn định]
  + spring-boot-loader/       [ổn định]
  + snapshot-dependencies/    [có thể đổi]
  + application/              [thường xuyên đổi]
```

Nếu thay `GreetingController` mà dependency set giữ nguyên, những file trong `dependencies` và `spring-boot-loader` thường không đổi, nên các Docker `COPY` sớm có cơ hội **CACHED**. Chỉ phần application cuối cần cập nhật, giúp giảm băng thông push/pull layer trong deployment.

Điều này **không có nghĩa** image final “không đổi” khi application khác: content digest/image ID mới vẫn thay đổi; phải publish và deploy image mới để chạy code mới.

## 9. Khi nào cần build trong container và khi nào cần copy JAR từ CI?

| Lựa chọn | Ưu điểm | Điểm đánh đổi |
|---|---|---|
| Dockerfile.multi: Maven build trong Docker | Build JDK/Maven được đóng trong builder image; source-only context | Builder có thể tải dependency; test/compile trong Docker; whole JAR là một lớp runtime |
| Dockerfile.layers: copy JAR đã build | CI tách compile/test khỏi image packaging; runtime layers tái sử dụng tốt | Phải build JAR trước; JAR thay đổi làm extractor stage thực hiện lại |
| Kết hợp Maven builder + jarmode extractor + layered runtime | Có cả cache của dependency build lẫn runtime layers | Dockerfile dài hơn, cần xác minh hai cấp cache và artifact |
| Chép nguyên JAR từ CI vào một runtime image | Đơn giản nhất, ít thao tác | Khi JAR đổi, layer chứa nguyên JAR thường đổi; registry không tách dependency |
| Cloud Native Buildpacks (`bootBuildImage`/`spring-boot:build-image`) | Buildpacks tự quản lý nhiều quy ước layering/image | Không phải Dockerfile tùy chỉnh; cần hiểu buildpack/cache/builder stack riêng |

Câu hỏi chọn phương án:

- Muốn **build hoàn toàn trong Docker từ source**? Bắt đầu `Dockerfile.multi`.
- CI đã build/test và phát hành JAR rõ ràng? `Dockerfile.layers` thuận tiện và dễ kiểm tra nguồn artifact.
- Image lớn vì dependency cố định nhưng code đổi liên tục? Layered JAR thường đáng thử.
- CI ưu tiên quy chuẩn buildpack? Xem `bootBuildImage`/`spring-boot:build-image`, nhưng không mặc định nó dùng các `COPY` Dockerfile của bạn.

## 10. Gradle: chiến lược COPY tương đương

Nếu project chọn Gradle thay Maven, ý tưởng giống hệt:

```text
settings.gradle, build.gradle, gradle.properties, Gradle Wrapper
          -> resolve Gradle dependencies
src/
          -> test + bootJar
          -> final runtime image
```

### 10.1. Build file Groovy DSL đầy đủ

`settings.gradle`:

```groovy
rootProject.name = 'cache-copy-demo'
```

`gradle.properties` ví dụ:

```properties
org.gradle.jvmargs=-Xmx1g
```

`build.gradle`:

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
```

Dùng **cùng ba file Java** của mục 3 nhưng chọn Gradle làm build tool chính. Wrapper `gradlew`, `gradlew.bat` và `gradle/wrapper/gradle-wrapper.{jar,properties}` phải là file hợp lệ sinh từ Gradle/Initializr; tạo file rỗng theo sơ đồ không đủ.

### 10.2. Dockerfile.gradle multi-stage

`Dockerfile.gradle` (build từ source, có Dockerfile-specific ignore tương ứng):

```dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

# Build descriptors + Wrapper trước source.
COPY gradlew settings.gradle build.gradle gradle.properties ./
COPY gradle/wrapper/ ./gradle/wrapper/
RUN chmod +x gradlew

# Tải dependencies qua Wrapper, lưu Gradle cache giữa các build.
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon dependencies --configuration runtimeClasspath

# Source đổi thường xuyên nên copy sau dependency step.
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon test bootJar

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/cache-copy-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Cần `Dockerfile.gradle.dockerignore` ít nhất bỏ `.git`, `build`, `.gradle`, `target`, editor files, log và secrets — **không** bỏ Gradle Wrapper, `settings.gradle`, `build.gradle`, `gradle.properties` hoặc `src`.

**Chú ý:** `./gradlew dependencies --configuration runtimeClasspath` chỉ giúp resolve dependency cho **configuration này**, không bảo đảm mọi plugin artifact/test dependency đã tải. Việc dùng **cache mount** giúp `test bootJar` tiếp tục tái sử dụng Gradle user home cache. Đừng dùng `RUN ./gradlew --offline` trong builder khi chưa có đủ artifacts; điều đó sẽ thất bại trên builder mới.

Nếu build cần `buildSrc`, version catalog `gradle/libs.versions.toml`, multi-module `include` hoặc convention plugins, cần đưa **toàn bộ file cấu hình liên quan** vào những `COPY` sớm. Dockerfile tối giản ở trên dành cho single-module theo mẫu `build.gradle` này.

### 10.3. Build và runtime

```bash
docker build --progress=plain -f Dockerfile.gradle \
    -t cache-copy-demo:gradle .
docker run --rm -p 8080:8080 cache-copy-demo:gradle
```

Nếu dùng PowerShell hoặc CMD, nhập lệnh một dòng. Nếu Gradle build tạo JAR khác vì `archiveFileName`, classifier hoặc `version` tùy chỉnh, sửa `COPY --from` theo output thực. **Không** lấy nhầm `-plain.jar`; cần executable JAR do `bootJar` tạo.

Layered runtime với Gradle vẫn dùng `-Djarmode=tools` sau khi `bootJar` tạo file. Với project Gradle đã build JAR ngoài Docker, thay `target/...` trong `Dockerfile.layers` bằng `build/libs/cache-copy-demo-0.1.0-SNAPSHOT.jar` và đặt ignore file cho phép đưa đúng JAR đó vào context.

## 11. Khi dùng Gradle nhiều module hoặc Maven reactor

Với repository đa mô-đun, chỉ chép root `pom.xml` trước khi resolve dependency có thể **chưa đủ**: Maven reactor thường cần POM của các module con trong giai đoạn dependency resolution. Tương tự, Gradle có `settings.gradle`, version catalog, root và subproject build scripts.

### 11.1. Maven multi-module: copy POM từng module trước source

Cấu trúc ví dụ:

```text
platform/
├── pom.xml
├── shared-core/pom.xml
├── api-app/pom.xml
├── shared-core/src/
└── api-app/src/
```

Dockerfile builder fragment:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

# Files cấu hình ít thay đổi trước.
COPY pom.xml ./
COPY shared-core/pom.xml shared-core/pom.xml
COPY api-app/pom.xml api-app/pom.xml

# Goal này phải được thử với reactor và plugins của project.
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp dependency:go-offline

# Sau đó mới chép source.
COPY shared-core/src/ shared-core/src/
COPY api-app/src/ api-app/src/
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp -pl :api-app -am package
```

Đây là **fragment mô hình**: để chạy được phải có parent POM khai báo đúng `<modules>`, POM con, dependencies và source thực tế. Maven `dependency:go-offline` ở một reactor với nhiều plugin có thể cần artifact nội bộ chưa build; hãy kiểm chứng lệnh riêng thay vì mặc định mọi multi-module repo đều hỗ trợ offline resolve bằng một goal.

### 11.2. Gradle multi-project: đừng quên input cấu hình

Với Gradle, những file ảnh hưởng dependency graph gồm:

- `settings.gradle` hoặc `settings.gradle.kts`.
- Root/subproject `build.gradle` hoặc `build.gradle.kts`.
- `gradle.properties`.
- `gradle/libs.versions.toml` (version catalog).
- `buildSrc`/`build-logic` convention plugins và metadata cần thiết.
- `gradle/wrapper` và wrapper script, khi build bằng wrapper.
- Một số file khóa dependency hoặc verification metadata.

Chúng cần được đưa vào các bước `COPY` trước bước resolve dependency nếu goal/task đọc đến chúng. Nên copy **tường minh** cấu hình cần thiết để source thay đổi không làm invalidation bước dependency, nhưng không được bỏ file cấu hình thật sự ảnh hưởng build.

Khi nhiều module cùng phát hành, image layer `application` của Spring Boot có thể bao gồm local module dependencies. Nếu thay một local library, application layer có thể đổi, dù external dependency layer vẫn tái sử dụng. Đây là behavior đúng.

## 12. .dockerignore: giảm context và tránh cache miss ngoài ý muốn

Docker build context là tập file client gửi cho builder theo đường dẫn cuối lệnh `docker build ... .`. Mặc định có thể chứa `.git/`, `target/`, `build/`, IDE settings, test reports, logs, local secrets, backup files. Một thay đổi trong những file này có thể gây invalidation khi Dockerfile dùng `COPY . .`, và còn làm context lớn hơn.

**Ví dụ root .dockerignore khi build Maven từ source:**

```dockerignore
.git
.idea
.vscode
target
build
.gradle
*.log
.env
.env.*
.DS_Store
```

**Không bỏ mất input thực sự cần thiết.** Nếu Dockerfile dùng `COPY target/app.jar`, rule `target` sẽ khiến Docker không tìm thấy JAR. Vì vậy dùng Dockerfile-specific ignore là lựa chọn phù hợp khi có cả `Dockerfile.multi` và `Dockerfile.layers`.

**Lưu ý quy tắc phủ định:** Docker `.dockerignore` hỗ trợ `!pattern` để đưa lại file sau khi đã loại nhóm rộng, và **quy tắc khớp cuối** ảnh hưởng kết quả. Ví dụ:

```dockerignore
target/*
!target/cache-copy-demo-0.1.0-SNAPSHOT.jar
```

Giữ lại **đúng artifact** cần copy, không giữ cả `target/classes`, test reports và JAR cũ. Trước khi áp dụng lên pipeline thật, kiểm tra build context bằng `docker build --progress=plain` hoặc thử `COPY` đúng file để phát hiện pattern sai.

**Bảo mật:** `.dockerignore` là lớp bảo vệ hạn chế vô tình đưa secret vào context, **không thay thế** secret manager. Đừng commit `.env` chứa credentials; và đừng thiết kế Dockerfile cần copy private keys vào image rồi “xóa ở RUN sau” — layer trước có thể vẫn chứa bytes nhạy cảm trong build cache/history.

## 13. BuildKit cache mounts: giúp dependency download hiệu quả

### 13.1. Maven local repository

```dockerfile
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn -B -ntp package
```

Vị trí `/root/.m2/repository` phù hợp với Maven image chạy dưới user root trong ví dụ. Nếu builder dùng user không root, `MAVEN_CONFIG` hoặc `-Dmaven.repo.local` khác, **đổi target** cho đúng repository Maven của tiến trình; không dùng path root theo thói quen khi tool thực tế đọc chỗ khác.

Docker BuildKit cache mount được giữ cục bộ theo builder/GC policy, không đồng nghĩa artifact của package manager nằm trong runtime image. Khi lệnh chạy lại vì source đổi, Maven có thể dùng lại dependency đã tải trong mount.

### 13.2. Gradle user home

```dockerfile
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon test bootJar
```

Mount `/root/.gradle` có thể giữ Gradle distribution, downloaded modules, plugin jars và một số metadata cache. Khi project dùng user `gradle` hoặc `GRADLE_USER_HOME` khác, cần điều chỉnh target/quyền sở hữu; đừng để permission denied rồi quy là dependency lỗi.

**Nguyên tắc correctness:** cả Maven và Gradle build vẫn phải chạy đúng khi cache mount trống, miễn repository được phép truy cập. Không dùng một cache mount có chứa file nguồn không được khai báo rồi phụ thuộc vào nó như input duy nhất.

### 13.3. Cache mounts không thay thế COPY ordering

Nếu bạn đặt `COPY . .` trước dependency resolution, cache mount có thể giảm download, nhưng Maven/Gradle goal vẫn bị kích hoạt lại thường xuyên. Tách `COPY pom.xml` rồi `COPY src` làm Docker có cơ hội **bỏ qua cả bước resolve** khi chỉ source thay đổi; cache mount chỉ là tối ưu bổ sung khi task cần chạy lại.

## 14. Cache từ CI runner mới: registry cache và tính an toàn

Trên laptop, BuildKit thường giữ build cache cục bộ; ở CI dùng runner ngắn hạn, mỗi job có thể bắt đầu với cache trống. Nếu muốn tái sử dụng giữa các runner, có thể dùng cache exporter/importer của Buildx.

**Mẫu cú pháp minh họa cho registry thuộc tổ chức** (cần thay namespace và registry bằng tài khoản có quyền thực tế):

```bash
docker buildx build --push \
  -f Dockerfile.multi \
  -t registry.example.com/team/cache-copy-demo:latest \
  --cache-from type=registry,ref=registry.example.com/team/cache-copy-demo:buildcache \
  --cache-to type=registry,ref=registry.example.com/team/cache-copy-demo:buildcache,mode=max \
  .
```

`registry.example.com` là tên miền ví dụ dành cho tài liệu, **không phải registry có thể push được nếu chưa cấu hình**. Bên cạnh credentials, phải đảm bảo builder driver/cache backend hỗ trợ exporter `registry`. Với default Docker driver, một số cách dùng registry backend đòi containerd image store được bật; Buildx driver phù hợp là lựa chọn khác.

- `mode=max` có thể xuất cả cache của intermediate stages, hữu ích cho Maven builder.
- Cache entry có thể bị ghi đè nếu nhiều nhánh cùng push một `buildcache` tag; cần chính sách cache scope.
- Cache không tự đảm bảo image mới nhất, không thay thế base image vulnerability scanning hoặc dependency verification.
- Cache export có thể chứa dữ liệu từ build steps; **đừng đưa secret vào `ARG`, `COPY` hoặc RUN command** để rồi đẩy cache ra registry công khai.
- Sử dụng `RUN --mount=type=secret` và cơ chế credentials phù hợp khi cần token; secret mount không được đưa vào final image theo mặc định.
- **Cache mounts** của Maven/Gradle và **exported layer cache** là hai thứ khác nhau. Không giả định dữ liệu trong `--mount=type=cache` sẽ được xuất ra registry cùng `--cache-to`.

Nếu CI chỉ cần tối ưu nhanh trong một runner, trước tiên thiết kế `COPY` đúng thứ tự và dùng cache mount tại builder; không nên lập remote-cache infrastructure khi chưa có bằng chứng chi phí build đủ lớn.

## 15. Cách đọc log để đánh giá một cải tiến COPY

Ví dụ các trạng thái BuildKit:

| Dòng log | Ý nghĩa | Cần kết luận thế nào? |
|---|---|---|
| `CACHED` ở `COPY pom.xml` | Input manifest/context phù hợp với cache | Bước này được tái sử dụng |
| `CACHED` ở `RUN dependency:go-offline` | Builder không cần chạy lại bước resolve | Mục tiêu cache build stage đã đạt trong lượt này |
| `DONE 9.2s` ở `RUN mvn package` | Lệnh package đã thực thi | Có thể là đúng vì Java source vừa thay đổi |
| `CACHED` ở `COPY --from=extractor .../dependencies` | Runtime dependency layer có thể tái sử dụng | Tốt khi code đổi nhưng dependency bytes giữ nguyên |
| `DONE ...` ở `COPY .../application` | Application layer đổi/phải tạo lại | Bình thường khi source hoặc resource đổi |
| `FROM-CACHE` trong Gradle logs | **Gradle Build Cache**, không phải Docker image layer | Đừng nhầm với BuildKit `CACHED` |
| `UP-TO-DATE` của Gradle | Gradle task output vẫn phù hợp | Không xác nhận Docker layer cache |
| Log Maven `Downloading from ...` | Maven phải lấy artifact | Có thể do cache mount rỗng/manifest mới |
| `COPY failed: file not found` | File không tồn tại trong context hoặc bị ignore | Kiểm tra context, filename, .dockerignore, build output |

Một cải tiến có giá trị khi **lượt đổi source thường xuyên** không kích hoạt các bước dependency đắt tiền hoặc không làm Docker phải upload lại toàn bộ dependency runtime. Tuy nhiên tổng build time còn chịu ảnh hưởng của compiler/test, download base image, CPU, network, registry và cache eviction.

Không đo hiệu quả từ một lượt duy nhất sau khi đổi Dockerfile: **sửa chính lệnh Dockerfile cũng là cache invalidation**. Cần làm nóng cache cho phiên bản Dockerfile mới rồi so sánh các tình huống đổi source tương đương.

## 16. Sử dụng COPY --link: tùy chọn nâng cao, không phải điều kiện bắt buộc

Docker BuildKit có tùy chọn `COPY --link` cho phép layer copy source trở nên độc lập hơn với các lớp trước trong một số trường hợp. Với một image runtime layered, khi các layer base thay đổi, cơ chế này có thể giúp reuse/rebase những layer copy có nội dung không đổi.

Ví dụ snippet nâng cao:

```dockerfile
# syntax=docker/dockerfile:1
COPY --link --from=extractor /workspace/extracted/dependencies/ ./
```

**Điều kiện:** `COPY --link` không được dựa vào việc truy cập nội dung/symlink của destination layer trước như `COPY` bình thường. Nếu destination path có symlink hoặc cần merge theo semantics đặc biệt, phải thử kỹ. Cú pháp yêu cầu Dockerfile frontend/BuildKit hỗ trợ.

**Không dùng một cách máy móc** ở mọi build để thay thế giải pháp cốt lõi: sắp xếp `COPY` theo tần suất thay đổi, giữ context nhỏ và phân tách Spring Boot layers đã mang lại lợi ích chính. `--link` là tối ưu tiếp theo khi build infrastructure hỗ trợ và đã đo được tác dụng.

## 17. Những lỗi thường gặp và cách khắc phục

| Vấn đề | Nguyên nhân dễ gặp | Cách khắc phục |
|---|---|---|
| Đổi một file Java làm Maven tải lại toàn bộ | `COPY . .` đứng trước dependency resolve, cache mount chưa có | `COPY pom.xml` trước, `COPY src` sau; thêm BuildKit cache mount |
| Docker build luôn có `COPY . .` miss | `.git`, logs, `target`, editor files hoặc output thay đổi | Dùng `.dockerignore` đúng build context |
| Dockerfile.multi không thấy `pom.xml` | Build từ thư mục sai hoặc context `.` không phải project root | Chạy tại root, xác minh `docker build ... .` |
| Dockerfile.layers không tìm thấy JAR | Chưa chạy Maven package, file tên khác hoặc bị ignore bởi rule `target` | Build JAR trước; cho phép đúng file trong Dockerfile-specific ignore |
| Có `layers.idx` nhưng chỉ một lớp app.jar trong image | `COPY` nguyên executable JAR, chưa extract | Dùng `jarmode=tools extract --layers` và bốn `COPY --from` |
| `Unsupported jarmode` | Archive không có tools jar, dùng mode cũ hoặc không phải executable JAR phù hợp | Xem Boot version, tools setting, manifest và layers |
| Tools extraction thất bại | Archive fully executable có launch script prepended | Tắt launch script cho artifact dùng jarmode tools |
| `application.jar not found` ở runtime | Chép thiếu layer application hoặc sai destination | So đường dẫn stage extraction với Spring Boot 3.5 Dockerfiles docs |
| Runtime báo thiếu dependency | Bỏ layer dependencies hoặc snapshot-dependencies; artifacts thiếu từ build | Copy đủ bốn lớp, kiểm tra JAR gốc |
| `jar tf` cho ra plain JAR | Chọn nhầm `jar`/`plain.jar` thay vì `bootJar`/repackage | Chọn executable archive thật, kiểm tra `BOOT-INF/layers.idx` |
| Thay Maven pom mà bước dependency vẫn CACHED | Có thể Dockerfile không copy file vừa thay hoặc đang build context khác | Kiểm tra `COPY` thực tế, cache logs và source path |
| Mỗi lần build image có version cũ | Docker copy artifact cũ, tag/container cũ chưa được thay | Xóa đúng container cũ, rebuild JAR/image đúng artifact |
| Maven `go-offline` vẫn truy cập mạng ở package | Một số plugin artifact resolve lúc goal thực thi | Chấp nhận khả năng đó, dùng cache mount và plugin repo đúng |
| Gradle wrapper không chạy | Thiếu wrapper jar/scripts hoặc `chmod`, sai Java/Gradle compatibility | Commit wrapper hợp lệ, chọn JDK/Wrapper phù hợp |
| Cache mount permission denied | Target trỏ sai user home hoặc owner không đủ quyền | Dùng đúng `MAVEN_CONFIG`/`GRADLE_USER_HOME` và uid/gid phù hợp |
| Build CI cache hit thấp | Ephemeral runner không giữ cache, base/tag thay đổi, plugin dynamic version | Dùng external cache phù hợp, pin dependencies và base image |
| Docker cache che cập nhật bảo mật | Base image tag không được refresh, package manager RUN reused | Có lịch `--pull`/rebuild và quét image; không ép cache hit mãi |
| Secret bị xuất hiện trong layer | `COPY` hoặc `ARG` truyền credential, rồi `RUN rm` | Không copy secret; BuildKit secret mount, rotate credential nếu lộ |

**Khi có lỗi, ưu tiên kiểm tra input thực tế trước khi dùng `docker build --no-cache`.** Cờ `--no-cache` bỏ qua layer cache nên hữu ích để chẩn đoán, nhưng nó **không phải** giải pháp tối ưu; chạy thường xuyên sẽ che mất lợi ích của Dockerfile đã sắp xếp đúng.

## 18. Hiệu năng, bảo mật và tính tái lập

### 18.1. Cân bằng giữa cache và bản vá

Giữ dependency/base layer lâu giúp giảm thời gian rebuild/push, nhưng **không được** dùng lại base image có lỗ hổng mãi mãi. Khi có patch JDK/OS, CI cần lấy base image mới theo chính sách, rebuild, chạy tests và scan. Có thể dùng image digest được pin cho tính tái lập, đồng thời có quy trình cập nhật digest định kỳ.

Docker `RUN apt-get update` có thể cache dù package repository ngoài đã có thay đổi, vì builder không tự kiểm chứng nội dung của mọi URL khi quyết định cache cho một instruction. Đừng lạm dụng cache để bỏ qua việc vá package.

### 18.2. Không đưa secrets vào image/cache

- Đặt repository credentials trong CI secret storage và truyền bằng BuildKit `--secret`, không commit `settings.xml`/`gradle.properties` chứa token vào source.
- Không `COPY` file `.env` hoặc private SSH key vào stage rồi xóa bằng `RUN rm`; bytes có thể vẫn nằm trong layer/cache.
- Không ghi credential vào `ARG`/`ENV` có thể xuất hiện trong image metadata/history.
- Kiểm soát quyền truy cập remote cache registry và tránh publish cache từ trusted build sang namespace người lạ.
- Build cache là tối ưu hiệu năng, **không phải cơ chế xác minh supply-chain**. Kiểm tra provenance, SBOM, image scanning và artifact digest riêng.

### 18.3. Chạy với quyền ít nhất

Các Dockerfile minh họa tập trung vào cache. Khi triển khai production, cân nhắc tạo/chọn user không root, đặt `USER` phù hợp, cấu hình permissions, writable temporary directory, health check và resource limits. Không chỉ thêm `USER 10001` vào cuối một Dockerfile bất kỳ mà không kiểm tra quyền đọc JAR/các thư mục runtime và ghi logs/tmp.

### 18.4. Cân nhắc số layer

Một `COPY` riêng tạo một lớp metadata/nội dung, nhưng nhiều lớp không phải luôn tốt. **Bốn layer Spring Boot có ý nghĩa** vì chúng nhóm dependencies/classes theo tần suất đổi khác nhau; không có lợi ích rõ ràng khi tạo hàng nghìn `COPY` cho từng class Java riêng. Mục tiêu là **lớp tái sử dụng được và dễ bảo trì**, không phải tối đa số instruction.

## 19. Checklist nghiệm thu: COPY được sắp xếp đúng chưa?

- [ ] Dockerfile sử dụng base image/JDK phù hợp Spring Boot và được cập nhật bảo mật.
- [ ] Các file ổn định quyết định dependency/plugin versions được `COPY` **trước** `src`.
- [ ] Lệnh resolve dependencies chỉ phụ thuộc các build descriptors thực sự cần thiết.
- [ ] `COPY src` nằm **sau** bước dependency resolution đắt tiền.
- [ ] BuildKit cache mount cho Maven/Gradle không bị hiểu nhầm là một Docker image layer.
- [ ] Build vẫn hoạt động khi cache mount rỗng và repositories truy cập hợp lệ.
- [ ] `.dockerignore` loại bỏ Git metadata không cần thiết, output cũ, logs, local secrets.
- [ ] Nếu image từ JAR đã build sẵn: không ignore file JAR cần `COPY`.
- [ ] Nếu dùng layered JAR: artifact có `BOOT-INF/layers.idx` và hỗ trợ `-Djarmode=tools`.
- [ ] Four `COPY --from` của runtime image đi từ `dependencies` đến `application`.
- [ ] `ENTRYPOINT` dùng đúng file `application.jar` sau extract với Spring Boot 3.5.
- [ ] Chạy hai lần không đổi source thấy nhiều bước CACHED khi builder cache còn.
- [ ] Sửa Java source làm rebuild app layer nhưng giữ dependency layer khi inputs không đổi.
- [ ] Sửa dependency manifest làm đúng các bước liên quan bị invalidated.
- [ ] JUnit tests vẫn chạy; endpoint trong image mới trả code mới, không chạy nhầm container cũ.
- [ ] CI ephemeral có chiến lược cache persistence phù hợp nếu thời gian build thực tế yêu cầu.
- [ ] Không dùng `--no-cache` làm mặc định hay đánh đổi việc cập nhật bản vá để luôn cache hit.
- [ ] Secrets được cấp an toàn, không bị lưu trong layers hoặc exported build cache.

### Nguồn tài liệu chính thức

- [Docker — Optimize Cache Usage in Builds](https://docs.docker.com/build/cache/optimize/)
- [Docker — Build Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Docker — Build Context and Dockerfile-specific Ignore Files](https://docs.docker.com/build/concepts/context/)
- [Docker — Dockerfile Reference: COPY, --link, cache mounts](https://docs.docker.com/reference/dockerfile)
- [Docker — Cache Storage Backends for BuildKit/Buildx](https://docs.docker.com/build/cache/backends/)
- [Spring Boot 3.5 — Dockerfiles and jarmode=tools](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.5 — Maven Packaging Layered JARs](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Apache Maven — dependency:go-offline goal](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html)
- [Docker Official Maven Image](https://hub.docker.com/_/maven)
- [Docker Official Eclipse Temurin Image](https://hub.docker.com/_/eclipse-temurin)

**Ghi nhớ:** Docker layer cache phát huy hiệu quả khi bạn đặt **input ít thay đổi trước, input thường thay đổi sau**. Với Spring Boot, trong **builder stage** hãy chép Maven/Gradle descriptors trước `src`; trong **runtime stage** hãy đặt các Spring Boot extracted layers theo `dependencies → spring-boot-loader → snapshot-dependencies → application`. Dùng `.dockerignore`, cache mount và phép thử thay đổi code/POM để chứng minh cache được tái sử dụng **đúng chỗ**, chứ không chỉ vì build có dòng `CACHED`.
