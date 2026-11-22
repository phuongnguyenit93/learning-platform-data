# Vai trò của builder, buildpack, lifecycle và run image trong Cloud Native Buildpacks

## 1. Bối cảnh: từ Spring Boot JAR thành OCI image

Trong Spring Boot, lệnh `mvn spring-boot:build-image` hoặc `./gradlew bootBuildImage` có thể đóng ứng dụng thành OCI container image **không cần viết Dockerfile**. Để hiểu vì sao cơ chế đó hoạt động, cách thay đổi Java runtime, cách khắc phục lỗi build và cách cập nhật image an toàn, cần phân biệt bốn thành phần của **Cloud Native Buildpacks (CNB)**:

1. **Builder**: OCI image được dùng *trong lúc xây dựng*, đóng gói buildpacks, lifecycle, build-time base image và metadata về run image.
2. **Buildpack**: phần mềm biết cách phát hiện một loại ứng dụng, cung cấp runtime/dependencies, đóng các launch layers và mô tả process khởi chạy.
3. **Lifecycle**: chương trình CNB điều phối quy trình phân tích, phát hiện buildpacks, khôi phục cache, thực hiện build và export OCI image.
4. **Run image**: OCI base image của *ứng dụng chạy thật*; cung cấp nền hệ điều hành và system libraries cho final app image.

Các tên khác cũng phải hiểu đúng: **platform** là công cụ điều phối CNB (ví dụ CNB `pack` CLI, tích hợp trong Spring Boot Maven/Gradle plugin); **build image** cung cấp OS/build environment của builder; **app image** là output được triển khai; **launcher** là cơ chế kích hoạt app process của image đã tạo.

### 1.1. Sơ đồ luồng dữ liệu

```text
   Java 17 Spring Boot project
      |                     |
  Maven package          Gradle bootJar
      |                     |
      +---- executable JAR/WAR -----+
                                   |
                     CNB platform / Spring Boot plugin
                                   |
                                   v
    +-------------------- BUILDER IMAGE ------------------+
    | Build-time base (OS và công cụ xây dựng)           |
    | Buildpacks (Java, runtime, Spring Boot support...)  |
    | CNB lifecycle binaries và detection order           |
    | Metadata: các run images/targets tương thích        |
    +-------------------------+---------------------------+
                              |
                    lifecycle orchestrates
          ANALYZE → DETECT → RESTORE → BUILD → EXPORT
                              |
                              v
      +--------------- FINAL OCI APP IMAGE ---------------+
      | Run-image base layers: OS/system libraries       |
      | Launch layers: JVM/JRE, app, dependencies         |
      | CNB launch process / image configuration          |
      +-------------------------+-------------------------+
                                |
                      Docker/Kubernetes runtime
                                |
                     Spring Boot controller
```

**Tóm tắt cần thuộc:** builder là *môi trường làm image*; run image là *nền chạy image*. Buildpack thực hiện công việc chuyên môn; lifecycle là người điều phối. Trong Java buildpacks, JVM/JRE thường được cung cấp dưới dạng **launch layer của buildpack**, không nhất thiết đã có trong run image gốc. Không đồng nhất “run image” với “JDK image”.

### 1.2. Phân biệt bằng một bảng

| Đối tượng | Bản chất | Có trong runtime app image? | Ví dụ công việc |
|---|---|---|---|
| Builder | OCI image cho build | Không phải toàn bộ builder được mang sang | Phân phối Java buildpacks + lifecycle |
| Buildpack | Phần mềm detect/build | Những launch layers do nó tạo ra có thể được mang sang, không phải tool build nguyên trạng | Chọn JVM, tạo start command |
| Lifecycle | Executable chuẩn CNB | Build-phase binaries không phải app server; launcher có thể xuất hiện | Analyze, detect, restore, build, export |
| Run image | OCI image nền runtime | Base layers **có** trong app image | OS và shared system libraries |
| Build image | Nền build-time | Không mặc định xuất sang final app image | Môi trường cho buildpacks chạy |
| Platform | Bộ điều phối gọi lifecycle | Không phải ứng dụng runtime | Maven/Gradle CNB integration, `pack` |
| App image | OCI artifact cuối | Chính nó là output để deploy | `docker run cnb-roles-lab:0.0.1` |

## 2. Builder: image cung cấp ngữ cảnh để tạo image

Theo đặc tả CNB, builder là **một OCI image** gồm build-time base image, tập buildpacks được sắp theo detection order, lifecycle binary và reference tới runtime base image. Đây không phải JAR Maven plugin cũng không phải sản phẩm cuối để `docker run` như một ứng dụng Spring Boot.

### 2.1. Builder chứa những gì?

```text
builder image
├── build-time base filesystem
├── lifecycle executables
├── buildpacks/
│   ├── buildpack A (detect + build)
│   ├── buildpack B (detect + build)
│   └── ...
├── detection order / groups
├── buildpack/lifecycle API metadata
└── run image references / compatibility metadata
```

Đây là **sơ đồ khái niệm**, không phải cây thư mục tuyệt đối bắt buộc của từng builder. Metadata runtime image thường không có nghĩa cả run image đã nằm nguyên trong builder filesystem; CNB platform vẫn truy xuất run image khi tạo app image.

Với Spring Boot Maven/Gradle Plugin **3.5.16**, tài liệu ghi builder mặc định:

```text
paketobuildpacks/builder-noble-java-tiny:latest
```

Đây là một Paketo builder dùng Ubuntu Noble và Java buildpacks. Hậu tố `:latest` **có thể thay đổi nội dung theo thời gian**. Bài học có thể dùng nó để thử tính năng; trong bản phát hành quan trọng nên pin builder bằng digest/phiên bản đã phê duyệt và ghi lại các dependency/buildpack versions thực.

### 2.2. Không phải mọi buildpack đều chạy

Builder có thể chứa nhiều buildpacks hoặc **composite buildpacks**. Lifecycle chạy **detect** theo các order groups, chọn tập buildpacks thỏa điều kiện của ứng dụng. Vì vậy:

- Builder có 20 buildpacks **không** nghĩa cả 20 đều xây mọi ứng dụng.
- Builder có hỗ trợ Java **không** đồng nghĩa biết xử lý mọi định dạng Java tùy chỉnh.
- Một Java app có thể cần nhiều buildpacks nhỏ: cung cấp JVM, phân tích archive, đặt CA certificates, startup command.
- Chỉ định một buildpack riêng bằng `buildpacks` override có thể **thay tập default**, làm detection thiếu những buildpacks cần cho Java.

### 2.3. Cách chọn builder

Đọc yêu cầu của dự án:

- Hỗ trợ Java version, framework và artifact type `jar/war`.
- Hỗ trợ target OS/architecture của CI và hạ tầng deploy: `linux/amd64`, `linux/arm64`...
- Có lifecycle và Buildpack/Platform API tương thích.
- Có run image tương thích; phù hợp yêu cầu hệ thống/native libraries.
- Được tổ chức phê duyệt, cập nhật security CVEs, công bố SBOM/source.
- Có thể pull từ registry trong CI và không cần vượt quá quyền hạn.
- Cho phép lựa chọn build-time/runtimes mà ứng dụng thật sự cần.

**Tiny image** có thể tiết kiệm dung lượng nhưng thiếu shell hoặc một số system libraries. Nếu app phụ thuộc shell script, fonts, native libraries, không mặc định builder/run image tiny đủ điều kiện. Cần xem tài liệu builder và chạy thử image thật.

### 2.4. Kiểm tra builder bằng pack

Nếu có `pack` CLI:

```bash
pack builder inspect paketobuildpacks/builder-noble-java-tiny:latest
```

Output có thể liệt kê **Buildpacks**, **Detection Order**, **Lifecycle**, **Run Images** và compatibility metadata. Đây là bước đầu để tìm builder đúng hoặc xem run image mà nó tham chiếu. Không viết cứng version từng buildpack/lifecycle trong kịch bản kiểm tra bởi `:latest` sẽ thay đổi.

## 3. Buildpack: người thực hiện công việc kỹ thuật

Buildpack là thành phần CNB chuyển đầu vào ứng dụng thành những phần cần thiết cho OCI image. Một buildpack điển hình có cấu trúc:

```text
buildpack/
├── buildpack.toml
└── bin/
    ├── detect
    └── build
```

`buildpack.toml` chứa ID, name, version/API metadata. `bin/detect` xác định có nên tham gia build hay không; `bin/build` tạo hoặc tái sử dụng layers, thiết lập launch environment và process metadata.

### 3.1. Detect phase

Trong detect:

1. Lifecycle lấy detection order từ builder.
2. Xét các buildpack groups theo thứ tự.
3. Mỗi buildpack có thể khai báo **provides/requires** theo build plan.
4. Khi tìm được group tương thích, lifecycle chọn buildpacks để build.
5. Nếu không group nào khớp, quá trình dừng với lỗi detection.

Ví dụ: JAR Spring Boot được Maven đóng gói rồi đưa vào builder Java. Các Paketo Java buildpacks có thể nhận ra loại archive, chọn runtime và cơ chế khởi động phù hợp. **Không phải detect lúc nào cũng compile source**; với `spring-boot:build-image`, Maven đã chuẩn bị artifact trước khi CNB xử lý. Nếu dùng `pack build --path .` với source directory, các buildpacks của builder có thể làm thêm phần compile.

### 3.2. Build phase

Các buildpacks được chọn có thể:

- Tải/cung cấp Java runtime phù hợp.
- Chuẩn bị start process cho Spring Boot executable archive.
- Phân tích dependency và tạo launch layers.
- Thiết lập biến môi trường build-time/runtime.
- Tạo metadata dùng cho cache, SBOM hoặc launch configuration.
- Sử dụng lại layer từ cache nếu điều kiện buildpack cho phép.

**Đừng nhầm buildpack với builder image:** `paketo-buildpacks/java` là một buildpack/composite buildpack; `paketobuildpacks/builder-noble-java-tiny:latest` là OCI builder chứa hoặc tham chiếu bộ buildpacks; run image là một OCI image khác.

### 3.3. Cấu hình buildpack bằng environment

Với Paketo Java buildpacks:

```text
BP_JVM_VERSION=17
```

là ví dụ biến chọn Java version. Spring Boot Maven truyền biến trong `<image><env>`, còn Gradle dùng `tasks.named('bootBuildImage') { environment[...] }`.

**Không nhầm** biến `BP_JVM_VERSION` của buildpack với `JAVA_TOOL_OPTIONS` mà JVM đọc lúc chạy. Một số buildpacks hỗ trợ các biến `BPE_*` để ghi thay đổi runtime environment; các biến chỉ có nghĩa khi buildpack tương ứng hỗ trợ.

Nếu `BP_JVM_VERSION` yêu cầu phiên bản mà builder/buildpack không cung cấp, build phase có thể thất bại; không sửa bằng việc đổi image output tag.

## 4. Lifecycle: điều phối năm pha tạo OCI image

**CNB lifecycle** là tập executables có giao thức thống nhất để platform gọi buildpacks và export image. Nó **khác**:

- Maven lifecycle: `validate → compile → test → package → verify`.
- Gradle task graph: `compileJava`, `bootJar`, `bootBuildImage`.
- Spring application lifecycle: tạo bean, ApplicationContext và xử lý request.

Luồng năm pha được tài liệu CNB mô tả:

```text
ANALYZE → DETECT → RESTORE → BUILD → EXPORT
```

| Pha | Chức năng | Tín hiệu cần xem khi lỗi |
|---|---|---|
| **Analyze** | Kiểm tra metadata/previous app image, quyền truy cập image/registry, thông tin run image | Auth, network, image references, registry/daemon |
| **Detect** | Chọn group buildpacks tương thích, tạo build plan | Builder order, artifact type, buildpack requirements |
| **Restore** | Khôi phục cache/layers/metadata tái sử dụng | Cache key, previous image, quyền ghi, restore logs |
| **Build** | Gọi `bin/build` của buildpacks được chọn, tạo launch/build layers | JVM version, JDK download, app archive, buildpack env |
| **Export** | Ghép run-image base với launch layers và metadata, xuất OCI image | Run image, image layers, registry push, disk/permissions |

Một số tài liệu CNB rất cũ có mô tả **analyze/restore** khác: ở các Platform API mới, analyze chạy **trước detect** để kiểm tra registry sớm; nhiều trách nhiệm phục hồi cache nằm ở restore. Khi gỡ lỗi phải đối chiếu lifecycle/Platform API của builder thật, không giả định tất cả phiên bản hoạt động giống nhau.

### 4.1. Analyze

Pha analyze đọc thông tin liên quan đến image trước đó/run-image và giúp xác minh rằng platform có quyền đọc/ghi những OCI resources cần thiết. Nếu chưa từng build trước đó, previous metadata có thể không tồn tại; đó không phải lỗi.

Nếu build dừng tại `ANALYZING`, kiểm tra image name, auth, Docker context, registry và proxy trước khi sửa Java source.

### 4.2. Detect

Pha detect quyết định **buildpacks nào tham gia**, theo builder detection order. Nếu xuất hiện `No buildpacks participating` hoặc `failed to detect`, hãy kiểm tra:

- Builder có Java buildpack hay không?
- Đầu vào có phải source/JAR đúng kiểu builder hỗ trợ?
- Có override danh sách buildpacks làm thiếu dependencies không?
- Target architecture/OS tương thích?
- Buildpack/Platform API có chấp nhận lifecycle hiện dùng không?

### 4.3. Restore

Pha restore tìm và khôi phục các layers đã được cache cho buildpack khi có thể. Ví dụ JVM/dependency layers không đổi có thể được reuse. Không phải mọi layer đều cacheable; cũng không phải lần build thứ hai chắc chắn nhanh hơn nếu image name, cache hoặc builder đã thay.

### 4.4. Build

Lifecycle chạy `bin/build` của những buildpacks được chọn. Ở một app Java, buildpacks có thể cung cấp runtime và launch layers. Tên binary **builder** dùng cho CNB build phase **không phải builder image**; một là executable lifecycle, một là OCI image môi trường.

### 4.5. Export

Exporter lấy base layers của **run image**, ghép với **launch layers**, tạo image config/labels/process metadata rồi xuất image. Output có thể nằm trong local Docker daemon hoặc registry tùy platform/publish settings. Đây là **image dùng để deploy**, không phải bản copy nguyên của builder image.

### 4.6. Creator, launcher, rebaser

- **Creator** có thể chạy cả năm pha trong cùng một invocation khi platform dùng chế độ tương ứng (ví dụ trusted builder); nó không phải pha thứ sáu.
- **CNB launcher** là thành phần trong image cuối để khởi chạy application process. Nó khác với `org.springframework.boot.loader.launch.JarLauncher` nằm trong executable Boot JAR.
- **Rebaser** hỗ trợ cập nhật nền run image khi có phiên bản mới tương thích mà không rebuild application layers.
- Các image extensions nếu được dùng có cơ chế riêng; không cần chúng cho ví dụ Spring Boot đơn giản.

## 5. Run image: nền hệ điều hành cho ứng dụng

**Run image** cung cấp phần nền của final app image: OS runtime, system libraries, user/base filesystem cần cho ứng dụng chạy. Trong CNB hiện đại, một builder có metadata tham chiếu run images/targets tương thích, và platform dùng mặc định từ đó nếu developer không override.

Điểm quan trọng: **run image không nhất thiết chứa JVM**. JVM/JRE có thể được Paketo Java buildpack thêm dưới một **launch layer**. Vì vậy không thể kiểm tra Java version chỉ bằng cách nhìn tên run image.

### 5.1. Build image khác run image

| Câu hỏi | Build image | Run image |
|---|---|---|
| Dùng ở giai đoạn nào? | CNB build | Application runtime |
| Có lifecycle/buildpacks trong builder? | Builder chứa và thực thi chúng | Không cần |
| Cần compiler/build dependencies? | Có thể | Không bắt buộc |
| Là OS base của image deploy? | Không | Có |
| Có thể không có shell? | Tùy build image | Có, tiny runtime thường không có shell |
| Có cần phù hợp CPU/OS? | Có | Có |
| Thay đổi có ảnh hưởng rebuild/cache? | Có | Có; có thể cân nhắc rebase |

### 5.2. Run image mặc định được lấy ở đâu?

Spring Boot 3.5 Maven/Gradle Plugin mô tả `runImage` mặc định **không được đặt**: platform sử dụng run image được khai báo trong **builder metadata**. Vì thế cấu hình đơn giản chỉ cần chọn builder:

```text
builder = paketobuildpacks/builder-noble-java-tiny:latest
runImage = (không override: dùng builder metadata)
```

Đừng tự ghép tên image từ tên builder. Xem:

```bash
pack builder inspect paketobuildpacks/builder-noble-java-tiny:latest
```

để đọc **Run Images** và lựa chọn mirrors nếu có. Registry mirrors giúp lấy run image gần output registry hơn khi phù hợp; không thay đổi bản chất runtime base.

### 5.3. Override run image khi thật sự cần

Spring Boot 3.5 documentation nêu builder tiny không có shell và system libraries hạn chế. Với nhu cầu runtime rộng hơn, tài liệu đưa ví dụ `paketobuildpacks/ubuntu-noble-run:latest`. Lệnh Maven minh họa:

```bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.runImage=paketobuildpacks/ubuntu-noble-run:latest
```

**Chỉ sử dụng khi builder hiện tại và run image mới tương thích**. Không chọn run image Alpine hay Ubuntu tùy hứng; kiểm tra OS/architecture, libc/system libraries và target metadata. Một run image khác có thể yêu cầu Java launch layer/native dependencies tương thích để app hoạt động.

### 5.4. Stack và targets

Tài liệu CNB cũ dùng **stack** như cặp build/run images có **stack ID**. CNB hiện nay đánh dấu stack là khái niệm **deprecated** và dùng **targets** để mô tả sự tương thích, gồm:

- OS name, ví dụ Linux.
- Architecture, ví dụ amd64 hoặc arm64.
- OS distribution name, version và các chi tiết target khác.

Do đó kiểm tra metadata thực tế của builder/run image quan trọng hơn việc chỉ so một chuỗi stack ID trong tài liệu cũ.

### 5.5. Run image tiny có thể không có shell

Một image vẫn chạy Spring Boot bình thường qua CNB launcher dù không có `/bin/sh`. Lệnh:

```bash
docker run --rm --entrypoint /bin/sh cnb-roles-lab:0.0.1
```

có thể thất bại với tiny runtime; đây **không phải lỗi của Java controller hoặc CNB detect**. Nếu ứng dụng cần shell script khi startup, hãy đổi launch strategy hoặc chọn run image rộng hơn mà builder hỗ trợ. Không dựa vào `apt-get` bên trong final tiny container để sửa build.

## 6. Maven/Gradle/pack là platform tích hợp, không phải buildpack

| Đường build | Đầu vào CNB thông thường | Cách chạy |
|---|---|---|
| Maven Spring Boot | Executable JAR/WAR được Maven/plugin tạo | `mvn spring-boot:build-image` |
| Gradle Spring Boot | `bootJar` hoặc `bootWar` artifact | `./gradlew bootBuildImage` |
| CNB pack CLI | Source directory hoặc app input theo cấu hình | `pack build ... --builder ...` |

Maven/Gradle plugin đóng vai trò điều phối CNB: lấy archive, builder, run image, cache, env, rồi gọi lifecycle/engine. **Plugin Maven không phải buildpack Java**. Ngược lại, buildpack Java không tự biết Maven `pom.xml` nên được cấu hình thế nào trong một reactor multi-module nếu platform chỉ đưa final archive cho nó.

**Không cần Dockerfile** khi dùng CNB Spring Boot plugin, nhưng **vẫn cần Docker daemon/API** theo tài liệu plugin 3.5; Dockerfile-free khác Docker-free. Lệnh `docker info` giúp xác minh engine/connection khi debug.

## 7. Ví dụ Java 17 + Spring Boot 3.5.16 với Maven

Ví dụ tạo service web nhỏ để có thể xác minh image bằng HTTP. Version Spring Boot **3.5.16** và Java **17** được pin cho bài học, không đại diện cho “latest” trong mọi dự án. Cần JDK 17+, Maven tương thích hoặc Maven Wrapper đã có, Docker Engine/daemon đang chạy, network/cache đủ để tải dependencies, builder và runtime images.

### 7.1. Cây thư mục

```text
cnb-roles-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/cnb/
    │   ├── CnbRolesApplication.java
    │   └── RolesController.java
    └── test/java/com/example/cnb/
        └── RolesControllerTest.java
```

Nếu project có Maven Wrapper thì root còn có `mvnw`, `mvnw.cmd` và `.mvn/wrapper/...`. Chỉ viết POM **không** tự tạo Wrapper; có thể dùng Maven đã cài sẵn.

### 7.2. pom.xml hoàn chỉnh

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

    <groupId>com.example</groupId>
    <artifactId>cnb-roles-lab</artifactId>
    <version>0.0.1</version>

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
                        <name>cnb-roles-lab:0.0.1</name>
                        <builder>paketobuildpacks/builder-noble-java-tiny:latest</builder>
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

Ý nghĩa:

- Parent quản lý versions cho starter/plugin và cấu hình `repackage` khi app khai báo Boot plugin.
- `spring-boot-starter-web` cung cấp HTTP server và Spring MVC.
- `<builder>` chọn **builder OCI image**.
- `<name>` là **final app image name**, không phải builder.
- `<env><BP_JVM_VERSION>17` truyền Java version cho Paketo buildpacks.
- Không override `runImage`: dùng run image từ builder metadata.
- Không override `buildpacks`: giữ builder detection order.
- `:latest` của builder thay đổi; pin digest trong production.

### 7.3. Java main class

`src/main/java/com/example/cnb/CnbRolesApplication.java`:

```java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbRolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(CnbRolesApplication.class, args);
    }
}
```

### 7.4. Controller HTTP có response xác định

`src/main/java/com/example/cnb/RolesController.java`:

```java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RolesController {
    @GetMapping("/roles")
    public String roles() {
        return "CNB roles: OK\n";
    }
}
```

Một request GET `/roles` trả body `CNB roles: OK` và một ký tự xuống dòng. Java code **không cần import Docker hay CNB API**: trách nhiệm đóng image nằm ở build tool/buildpacks.

### 7.5. Test JUnit Jupiter

`src/test/java/com/example/cnb/RolesControllerTest.java`:

```java
package com.example.cnb;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RolesControllerTest {
    @Test
    void returnsKnownValue() {
        assertEquals("CNB roles: OK\n", new RolesController().roles());
    }
}
```

Unit test chỉ xác minh logic controller, không mở HTTP port và không thay cho smoke test container. `spring-boot-starter-test` cung cấp JUnit Jupiter theo dependency management của Spring Boot.

### 7.6. Build bằng Maven và xuất image

Từ project root, khi có Maven Wrapper:

```bash
# Trước khi build:
java -version
docker info

# Kiểm tra Java tests, đóng executable JAR:
./mvnw clean package

# Tạo OCI image bằng CNB:
./mvnw spring-boot:build-image

# Xem image đã tạo tại Docker daemon:
docker image inspect cnb-roles-lab:0.0.1
```

Nếu không có Maven Wrapper, thay `./mvnw` bằng `mvn`. Trên Windows PowerShell dùng `.\mvnw.cmd`.

Goal `spring-boot:build-image` **tự bảo đảm package lifecycle chạy nếu cần**, nên có thể gọi trực tiếp khi đã cấu hình plugin. Việc chạy `clean package` tách ra phục vụ minh họa và test, không phải yêu cầu bắt buộc mỗi lần gọi build-image. Nếu muốn bind goal vào `package`, Spring Boot có `build-image-no-fork` dành cho execution, khác cách dùng ở CLI.

Các pha log có thể xuất hiện:

```text
===> ANALYZING
===> DETECTING
===> RESTORING
===> BUILDING
===> EXPORTING
```

Đây là **tên pha để nhận diện**, không phải cam kết output đầy đủ hoặc chính xác từng ký tự cho mọi builder version.

### 7.7. Chạy container và test HTTP

```bash
docker run --rm -p 8080:8080 cnb-roles-lab:0.0.1
```

Từ terminal thứ hai khi ứng dụng đã sẵn sàng:

```bash
curl -fsS http://localhost:8080/roles
```

HTTP body do controller tạo **chính xác**:

```text
CNB roles: OK
```

Body có newline cuối. Spring Boot startup logs/HTTP headers không được liệt kê ở trên. Nếu host port 8080 đang được sử dụng, chạy một container **thay thế** bằng:

```bash
docker run --rm -p 18080:8080 cnb-roles-lab:0.0.1
```

và gọi `http://localhost:18080/roles`. Trong `-p 18080:8080`, vế đầu là host port, vế sau là container port; không cần đổi `server.port` trong Java app.

### 7.8. Kiểm tra image đã được xây bằng ai và trên nền nào

```bash
# Thông tin user/entrypoint của final image:
docker image inspect cnb-roles-lab:0.0.1 \
  --format '{{json .Config.User}} {{json .Config.Entrypoint}}'

# Xem layer history:
docker history cnb-roles-lab:0.0.1

# Nếu có CNB pack CLI:
pack inspect-image cnb-roles-lab:0.0.1
```

Với PowerShell, viết lệnh inspect một dòng. Trong `pack inspect-image`, chú ý **Buildpacks**, **Run Images**, **Processes**, **Rebasable** (nếu được cung cấp) và metadata liên quan. Các phiên bản buildpack/run image phụ thuộc builder `:latest` thực, nên không khai báo output “chắc chắn” ở đây.

`docker history` và `docker image inspect` là công cụ đọc OCI image, **không thay thế** hoàn toàn CNB metadata. Không suy app image thuộc builder nào chỉ từ tên layer, hãy đối chiếu cả logs, image labels và `pack inspect-image`.

## 8. Ví dụ Gradle tương đương

Giữ nguyên các file Java/JUnit ở mục 7; nếu dùng Gradle, thay Maven POM bằng `settings.gradle` và `build.gradle` Groovy DSL.

`settings.gradle`:

```groovy
rootProject.name = 'cnb-roles-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.0.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = 'cnb-roles-lab:0.0.1'
    builder = 'paketobuildpacks/builder-noble-java-tiny:latest'
    environment['BP_JVM_VERSION'] = '17'
    // Không đặt runImage: lấy mặc định từ builder metadata.
}
```

Với **Gradle Wrapper đã có**, phiên bản Gradle tương thích Spring Boot 3.5 và Docker daemon khả dụng:

```bash
./gradlew test
./gradlew bootBuildImage
docker image inspect cnb-roles-lab:0.0.1
docker run --rm -p 8080:8080 cnb-roles-lab:0.0.1
```

Windows dùng `.\gradlew.bat` thay `./gradlew`. `bootBuildImage` sử dụng `bootJar`/`bootWar` output phù hợp, nhưng **không tự chứng minh toàn bộ unit/integration tests đã chạy** nếu CI chỉ gọi task build image. Vì vậy chạy `test` riêng là bước QA có chủ đích.

### 8.1. Override runImage trong Gradle khi cần

Đây là **block thay thế block `bootBuildImage` ở trên**, chỉ dùng khi đã kiểm tra compatibility:

```groovy
tasks.named('bootBuildImage') {
    imageName = 'cnb-roles-lab:0.0.1'
    builder = 'paketobuildpacks/builder-noble-java-tiny:latest'
    runImage = 'paketobuildpacks/ubuntu-noble-run:latest'
    environment['BP_JVM_VERSION'] = '17'
}
```

Nếu cần shell hoặc nhiều OS libraries, một run image rộng hơn có thể phù hợp. Nhưng chỉ đổi `runImage` không tự thêm runtime libraries cho mọi hệ thống native app; cần smoke tests và kiểm tra OS/target.

### 8.2. Kotlin DSL

Trong Gradle `build.gradle.kts`, đoạn điều khiển task có thể viết:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("cnb-roles-lab:0.0.1")
    builder.set("paketobuildpacks/builder-noble-java-tiny:latest")
    environment.put("BP_JVM_VERSION", "17")
}
```

Đây là **đoạn Kotlin DSL để ghép vào build script thích hợp**, không phải một build.gradle.kts hoàn chỉnh. Khác với Groovy DSL, các Gradle Properties trong Kotlin cần dùng `.set(...)` và `.put(...)`. Không dán lẫn hai DSL vào cùng một file.

## 9. pack CLI và trực tiếp chọn buildpacks

`pack` là CNB platform CLI. Nếu developer muốn thử builder độc lập với Spring Boot Maven/Gradle integration, một lệnh điển hình là:

```bash
pack build cnb-roles-source:0.0.1 \
  --builder paketobuildpacks/builder-noble-java-tiny:latest \
  --path .
```

Ở đây `--path .` nghĩa là source directory. Kết quả phụ thuộc builder có các buildpacks nhận diện **source project** hoặc không; khác với Spring Boot plugin đưa **executable JAR** làm đầu vào. Không mặc định pack phải build y hệt Maven plugin chỉ vì cùng source.

Các khái niệm flag:

- `--builder`: chọn OCI builder.
- `--buildpack`: chọn buildpacks riêng, có thể thay detection order mặc định.
- `--env BP_JVM_VERSION=17`: cấu hình buildpack tương ứng.
- `--run-image` (khi công cụ/phiên bản hỗ trợ): chọn run-image thay vì mặc định.
- `pack builder inspect`: xem builder.
- `pack inspect-image`: xem metadata CNB của app image.

**Cẩn thận** với việc override `--buildpack` hoặc `<buildpacks>`: Spring Boot Plugin tài liệu xác nhận nếu danh sách này được cấp thì chỉ các buildpacks được chỉ định sẽ dùng, không tự cộng thêm mọi buildpack mặc định trong builder. Một danh sách thiếu Java runtime hoặc startup support có thể làm detect/build thất bại.

## 10. Cache: rebuild nhanh hơn, không phải run image

CNB lifecycle có thể restore cached layers từ previous image/cache khi build lại. Với Java:

- JRE và dependencies giữ nguyên có thể được reuse.
- Class application thay đổi thường khiến layers ứng dụng được build/export lại.
- Layer cache hit/miss do chính buildpacks và platform cache configuration quyết định.

Ví dụ logic:

```text
Lần 1: analyze → detect → restore (cache trống)
      → build runtime/app launch layers → export

Lần 2: analyze → detect → restore (reuse layers hợp lệ)
      → build phần thay đổi → export
```

**Không đảm bảo lần thứ hai luôn nhanh hơn.** Cache bị miss khi đổi builder, Java version, image name, cache volume, Docker daemon CI hoặc khi metadata/layer contents thay đổi. Tài liệu Spring Boot Gradle Plugin lưu ý tên cache volume mặc định có thể phụ thuộc **tên đầy đủ output image**; đổi tag liên tục ảnh hưởng reuse.

| Khái niệm | Ý nghĩa |
|---|---|
| Build cache | Tái sử dụng kết quả/layers để giảm công việc build |
| Launch layer | Nội dung dùng khi app chạy, như JRE/app dependencies |
| Run-image layer | Các lớp OS base của app image |
| Image tag | Tên tham chiếu có thể thay đổi trỏ sang content khác |
| Image digest | Mã nhận dạng immutable theo nội dung |
| Reproducibility | Cùng đầu vào được kiểm soát sinh ra đầu ra tương đương |

Không dùng `:latest`, dependency version động và timestamps không kiểm soát rồi tuyên bố build byte-for-byte reproducible. Để quản trị release, lưu builder/run image digests, buildpack versions và image digest cuối.

## 11. Rebase: cập nhật runtime base không cần build lại app layers

**Rebase** cho phép thay **run-image base layers** bằng phiên bản tương thích mới mà không chạy lại toàn bộ buildpacks hoặc compile source, nếu image metadata và policy cho phép.

```text
Trước: App image = run image A + JVM/JAR launch layers
Sau:   App image = run image B + JVM/JAR launch layers
                 (chỉ khi B tương thích và image rebasable)
```

Rebase hữu ích khi OS runtime base có bản vá bảo mật. Nhưng:

1. Rebase **không** đổi source Java, bytecode hoặc Spring Boot version.
2. Rebase **không tự đổi JVM** nếu JVM là buildpack launch layer phía trên run image.
3. Không phải mọi OCI image đều `Rebasable`.
4. Run image mới phải tương thích với các targets, OS/architecture và native dependencies.
5. Vẫn cần smoke test, CVE scan và policy release/rollback sau rebase.
6. Không dùng rebase thay quy trình build khi ứng dụng hoặc JDK thay đổi.

Kiểm tra metadata:

```bash
pack inspect-image cnb-roles-lab:0.0.1
```

Tìm `Rebasable`, `Run Images` và các metadata liên quan. Không chạy `pack rebase` lên một tag production chưa có chính sách backup/rollback. Khi cần thực hiện trên môi trường thử nghiệm, CNB có `pack rebase` theo tài liệu chính thức để cập nhật runtime base phù hợp.

## 12. Security và vận hành

### 12.1. Non-root và file permissions

Tài liệu Spring Boot về CNB nhấn mạnh image được build và chạy dưới **non-root users** theo mục tiêu an toàn. Do đó:

- Container có thể không ghi được vào root filesystem hoặc một số thư mục.
- Khi cần output, dùng writable volume/path và thiết lập ownership đúng.
- Không bật root chỉ để “chạy cho được” khi ứng dụng được container hóa.
- Cần bảo đảm các Kubernetes securityContext settings tương thích với user/process được image tạo.

### 12.2. Builder/buildpacks có thể thực thi mã trong build

Builder và buildpacks là software chạy trong môi trường build, có thể tiếp cận files/network/bindings/secrets được cấp. Vì vậy:

- Dùng nguồn builder đã được tổ chức duyệt.
- Pin digest, kiểm tra chữ ký/provenance khi cần.
- Giới hạn registry credentials, build-time secrets, network và writable mounts.
- Đọc `trustBuilder` của Spring Boot plugin và chỉ trust builder phù hợp với chính sách.
- Tránh ghi password/token vào POM, Gradle build script, launch layers hoặc logs.
- Thu thập SBOM, image digest, metadata buildpacks và security scan trước deploy.

### 12.3. Tiny runtime có thể thiếu shell và system libraries

Không gọi `docker exec ... /bin/sh` là tiêu chí bắt buộc để kiểm tra mọi CNB image. Với builder Noble Java Tiny, thiếu shell có thể là **đặc tính của image**. Nếu app chạy một startup shell script hoặc gọi native binary, chọn runtime base compatible có đủ thư viện hoặc thay launch process.

### 12.4. Runtime configuration khác build-time configuration

- `BP_JVM_VERSION`: cấu hình lựa chọn Java runtime **trong buildpack build**.
- `JAVA_TOOL_OPTIONS`: JVM options khi launch process chạy (tùy buildpack tích hợp).
- `SPRING_PROFILES_ACTIVE`, `SERVER_PORT` và secrets: môi trường runtime cho Spring Boot.
- `BPE_*`: một số Paketo buildpacks hỗ trợ ghi thay đổi launch environment vào image.

Không giả định mọi buildpack/vendor hiểu cùng một biến. Nếu dữ liệu nhạy cảm chỉ cần khi runtime, ưu tiên cấp qua Kubernetes Secret/secret manager, **không bake vào OCI layers**.

## 13. Chẩn đoán lỗi theo pha

| Hiện tượng | Tầng có khả năng liên quan | Hướng kiểm tra |
|---|---|---|
| Không kết nối được Docker daemon | Platform/engine | `docker info`, context, socket/TLS |
| Không pull được builder | Builder/registry | Tên, tag/digest, registry auth, proxy |
| `No buildpacks participating` | Detect | Builder hỗ trợ Java? artifact source/JAR phù hợp? |
| `Failed to detect` sau khi chỉ định custom buildpacks | Buildpack order | Trả về builder defaults hoặc thêm đủ buildpacks cần |
| Không tìm thấy JRE 17 | Buildpack/runtime provisioning | `BP_JVM_VERSION`, buildpack version, network |
| `UnsupportedClassVersionError` khi app chạy | Launch JVM thấp hơn bytecode target | Java toolchain và JVM launch layer |
| Lỗi `ANALYZING` | Registry/previous-image permissions | Auth, image references, metadata |
| Lỗi `RESTORING` | Cache/workspace | Disk, volume, permissions, thử cache sạch có chủ đích |
| Lỗi `BUILDING` khi tải artifact | Buildpack/network | Proxy, TLS certificate, outbound allowlist |
| Lỗi `EXPORTING` | Run image/registry/disk | Disk quota, pull/run compatibility, push privileges |
| Run image override bị từ chối | Incompatible targets/stack | Builder metadata và run-image architecture |
| App image thiếu `/bin/sh` | Tiny run image | Đổi launch method hoặc compatible run image |
| Không có `docker image inspect` output | Image chưa xuất vào local daemon | Xem publish/local engine, image name/tag |
| HTTP `/roles` không trả về | Runtime/Boot app | `docker logs`, container port mapping, startup errors |
| `docker run` báo port in use | Host port conflict | `-p 18080:8080`, kiểm tra service khác |
| Rebase không chạy | Image không rebasable hoặc run image mismatch | `pack inspect-image`, compatibility |
| CVE của JRE không hết sau rebase | JRE thuộc launch layer | Nâng buildpack/JVM rồi rebuild image |
| Build sau đổi code vẫn có behavior cũ | Artifact/image tag/cache sai | Kiểm tra source commit, JAR, image digest |
| Run image tiny thiếu native lib | OS/runtime compatibility | Chọn compatible run image có system libs |
| CI nói build thành công nhưng registry trống | Chưa publish hoặc auth sai | `publish`/`publishImage`, registry URL |
| Không có Dockerfile | CNB không cần Dockerfile | Dùng build-image theo CNB, không phải lỗi |

### 13.1. Cách đọc log có thứ tự

1. **Trước ANALYZING**: Maven/Gradle compile/test, Docker daemon, builder pull.
2. **ANALYZING**: image/registry access và previous metadata.
3. **DETECTING**: builder buildpacks, group selection, artifact type.
4. **RESTORING**: cache metadata/layers.
5. **BUILDING**: Java runtime download, buildpack logic, image layers.
6. **EXPORTING**: OCI image assembly, run image, disk/registry permissions.
7. **Sau khi build, lúc docker run**: CNB launcher, runtime OS/JVM, Spring Boot application logs.

Đây là **heuristic**, không phải hệ thống chứng minh lỗi chỉ có một nguyên nhân. Đọc lỗi gốc, kiểm tra image đang dùng và so với cấu hình build thực tế.

## 14. Quy trình đề xuất cho CI/CD và production

1. Kiểm tra Java compile, unit/integration tests, dependency policies.
2. Tạo executable JAR/WAR đúng source commit (Maven/Gradle).
3. Chọn builder được duyệt, pin version/digest và xác nhận Java support.
4. Giữ run image theo builder metadata, hoặc override **chỉ** với lý do và compatibility test.
5. Truyền build-time environment đúng; hạn chế secrets.
6. Gọi `spring-boot:build-image` hoặc `bootBuildImage`; quan sát năm pha lifecycle.
7. Inspect output image: buildpacks, run image, user/entrypoint, architecture và digest.
8. Chạy image thật và smoke test HTTP, health, environment, filesystem permissions.
9. Scan image/SBOM và ký/attest theo yêu cầu hạ tầng.
10. Push image với tag/digest rõ ràng; triển khai đúng immutable digest.
11. Khi run image có bản vá, đánh giá rebase nếu image rebasable/compatible; khi Java/app thay đổi, rebuild.
12. Lưu bản ghi builder/run image refs, buildpacks, lifecycle versions, image digest, test reports và kết quả deploy.

**Build-image SUCCESS không chứng minh image đã chạy thành công hay đã được triển khai.** Đầu ra cần qua smoke test và kiểm tra vận hành.

## 15. Bài tập tự kiểm tra

### Bài tập 1: Chọn đúng đối tượng

Giả sử:

```text
Builder:   paketobuildpacks/builder-noble-java-tiny:latest
Buildpack: Paketo Java
Lifecycle: analyze/detect/restore/build/export
Run image: run image do builder metadata cung cấp
Output:    cnb-roles-lab:0.0.1
```

**Hỏi:** image nào đưa vào production? **Đáp:** app image `cnb-roles-lab:0.0.1` (tốt hơn là bằng digest); **không** deploy builder image. Base OS của runtime đến từ run image; launch layers có thể chứa JVM và app.

### Bài tập 2: Chữa nhận định sai

> “Tôi đã đặt `BP_JVM_VERSION=17` nên run image chắc chắn cài JDK 17.”

**Sai:** biến này hướng dẫn buildpack chọn Java version. JVM thường nằm trong buildpack launch layer; run image là nền OS và system libraries. Xác minh JVM trong output bằng logs và runtime behavior.

### Bài tập 3: Phân biệt cache và rebase

- Cache giúp **build lại nhanh hơn** khi layers có thể reuse.
- Rebase giúp **cập nhật run-image base** mà không rebuild app layers khi compatible.
- Đổi controller Java cần **rebuild**.
- Đổi major Java runtime cần **buildpack/JVM layer rebuild**; rebase OS base đơn thuần không đủ.

### Bài tập 4: Nhận diện pha lỗi

- `DETECTING` fail → builder có buildpack Java và artifact phù hợp không?
- `BUILDING` fail tải JRE → network/Java version/buildpack.
- `EXPORTING` fail → run image, disk, registry/daemon.
- `docker run` fail vì thiếu shell → tiny runtime/launch process, không mặc định lỗi Java code.

## 16. Checklist cuối bài

- [ ] Phân biệt builder image và final app image.
- [ ] Biết builder chứa buildpacks, lifecycle, build base và metadata run image.
- [ ] Biết buildpack có `detect` và `build`, có thể tạo Java launch layers.
- [ ] Biết năm pha lifecycle `analyze → detect → restore → build → export`.
- [ ] Không nhầm CNB lifecycle với Maven lifecycle hoặc Spring Boot ApplicationContext.
- [ ] Biết run image là runtime base OS, không đồng nghĩa JDK image.
- [ ] Biết run image mặc định được chọn qua builder metadata.
- [ ] Biết `pack builder inspect` và `pack inspect-image`.
- [ ] Biết Maven `spring-boot:build-image` và Gradle `bootBuildImage` là integration/platform, không phải buildpacks.
- [ ] Biết `BP_JVM_VERSION` khác JVM runtime options.
- [ ] Không đòi Dockerfile khi dùng CNB nhưng vẫn kiểm tra Docker daemon.
- [ ] Kiểm tra builder/run compatibility, OS/architecture và native libraries.
- [ ] Hiểu tiny image có thể thiếu `/bin/sh`.
- [ ] Hiểu cache reuse, image digest, reproducibility và rebase là khái niệm khác nhau.
- [ ] Không cho rằng rebase tự thay Java source hoặc JRE launch layer.
- [ ] Đã chạy test Java, image build và smoke test HTTP trên image thật.
- [ ] Có non-root policy, secret handling, builder provenance và image scanning khi release.

**Kết luận:** CNB **builder** là môi trường xây image, **buildpack** là bộ phận biết phải cung cấp JVM/app layer nào, **lifecycle** là chương trình điều phối các pha tạo image, còn **run image** là nền runtime của OCI image được triển khai. Nhận diện đúng bốn vai trò là tiền đề để cấu hình Spring Boot build-image, chẩn đoán lỗi, kiểm soát cache/rebase và vận hành container có thể truy vết.

### Tài liệu chính thức

- [Cloud Native Buildpacks — Builder](https://buildpacks.io/docs/for-app-developers/concepts/builder/)
- [Cloud Native Buildpacks — Buildpack](https://buildpacks.io/docs/for-app-developers/concepts/buildpack/)
- [Cloud Native Buildpacks — Lifecycle](https://buildpacks.io/docs/for-platform-operators/concepts/lifecycle/)
- [Cloud Native Buildpacks — Run Image](https://buildpacks.io/docs/for-app-developers/concepts/base-images/run/)
- [Cloud Native Buildpacks — Build Image](https://buildpacks.io/docs/for-app-developers/concepts/base-images/build/)
- [Cloud Native Buildpacks — Rebase](https://buildpacks.io/docs/for-app-developers/concepts/rebase/)
- [Cloud Native Buildpacks — Inspect App Image](https://buildpacks.io/docs/for-app-developers/how-to/build-outputs/inspect-app/)
- [Cloud Native Buildpacks — Targets](https://buildpacks.io/docs/for-buildpack-authors/concepts/targets/)
- [Cloud Native Buildpacks — Builder Config](https://buildpacks.io/docs/reference/config/builder-config/)
- [Spring Boot 3.5 — Maven Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html)
- [Spring Boot 3.5 — Gradle Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html)
- [Paketo Noble Java Tiny Builder](https://github.com/paketo-buildpacks/builder-noble-java-tiny)
