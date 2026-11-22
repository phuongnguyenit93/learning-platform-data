# Sinh thông tin bản dựng bằng Gradle springBoot.buildInfo và bootBuildInfo

## Mục tiêu và bối cảnh

Một ứng dụng Spring Boot đã được build và triển khai thành công nhưng khi xem log hoặc endpoint quản trị, đội vận hành vẫn cần trả lời những câu hỏi rất thực tế:

- Phiên bản nào của ứng dụng đang chạy: `0.0.1-SNAPSHOT`, `1.2.3` hay một phiên bản khác?
- Artifact được tạo từ module nào khi repository có nhiều module?
- Group, tên ứng dụng và release channel của artifact là gì?
- Thời điểm nào được ghi nhận là **build time**, và vì sao nó có thể làm build chậm hoặc khó tái lập?
- Tệp metadata có thật trong **JAR/WAR phát hành** hay chỉ xuất hiện ở thư mục build local?
- Spring Boot Actuator đọc và công bố metadata theo cách nào? Có cần cấu hình endpoint `/actuator/info` không?
- Khi CI hoặc người dùng chạy `bootBuildInfo` riêng, nó có sinh đúng file và được liên kết với task `bootJar` không?

Spring Boot Gradle Plugin cung cấp sẵn một cách giải quyết: khai báo `springBoot { buildInfo() }` để cấu hình task `bootBuildInfo`, task này tạo **`META-INF/build-info.properties`**. Spring Boot có thể đọc file thành bean `BuildProperties`; nếu ứng dụng dùng Actuator, `BuildInfoContributor` có thể đưa thông tin đó lên endpoint `/actuator/info`.

Sau bài học, bạn có thể:

1. Phân biệt **Gradle DSL `springBoot.buildInfo`** và **task `bootBuildInfo`**, hiểu ai đăng ký task và khi nào task được chạy.
2. Giải thích năm thuộc tính mặc định `build.artifact`, `build.group`, `build.name`, `build.version`, `build.time`.
3. Cấu hình sinh file metadata bằng Gradle Groovy DSL và Kotlin DSL, thêm custom properties, thay đổi hoặc loại bỏ default properties.
4. Hiểu vị trí output trong **Spring Boot 3.3**, đường vào main source set và vị trí bên trong executable JAR/WAR.
5. Dùng Java 17+ và Spring Boot Actuator để đọc `BuildProperties`, xác minh `/actuator/info` và endpoint đơn giản của ứng dụng.
6. Phân tích vì sao `build.time` mặc định làm `bootBuildInfo` không `UP-TO-DATE`, cùng ảnh hưởng tới `test`, `bootJar` và build reproducibility.
7. Chẩn đoán trường hợp file không được sinh, metadata cũ, không có bean `BuildProperties`, endpoint `/actuator/info` trả trống/404 hoặc CI phát hành nhầm artifact.

**Phiên bản áp dụng cho ví dụ:** Spring Boot **3.3.13**, Java **17**, Gradle **8.x** tương thích. Plugin và cấu hình task có thay đổi ở các thế hệ Spring Boot khác, vì vậy cần dùng tài liệu của **đúng phiên bản**. Các đường dẫn `build/...` trong bài là quy ước **Spring Boot 3.3**, không nhất thiết giống những đường dẫn được tài liệu cho Spring Boot 4.x mô tả.

---

## 1. Build metadata là gì? Khác gì với thông tin runtime?

**Build metadata** là thông tin được nhúng vào artifact **tại thời điểm build**, ví dụ tên/group/version của project, thời điểm tạo và thuộc tính tùy chỉnh của release.

Một `build-info.properties` minh họa:

```properties
build.artifact=build-meta-demo
build.group=com.example
build.name=build-meta-demo
build.version=0.0.1-SNAPSHOT
build.time=2026-11-09T08:30:00Z
```

**Đây là nội dung mô phỏng**, không phải file đã được tạo bởi project. Giá trị `build.time` thay đổi theo thời điểm build, vì vậy không được chép timestamp mẫu vào báo cáo thật.

| Trường | Ý nghĩa | Nguồn mặc định khi dùng Gradle Boot Plugin |
| --- | --- | --- |
| `build.artifact` | Tên cơ sở của artifact được đóng gói | Base name của task `bootJar` hoặc `bootWar` |
| `build.group` | Gradle `project.group` | Khai báo `group` trong build script |
| `build.name` | Tên Gradle project/module | `project.name` |
| `build.version` | Phiên bản Gradle project | `project.version` |
| `build.time` | Thời điểm build mà plugin ghi nhận | Instant tại thời điểm build |

**Đừng nhầm** `build.name` với `spring.application.name`. `build.name` đến từ Gradle project, còn `spring.application.name` là Spring runtime configuration. Hai giá trị có thể giống nhau nếu bạn đặt vậy, nhưng không tự đồng bộ.

**Đừng nhầm** `build.time` với uptime, thời điểm deploy hay thời điểm app startup. Build time ghi trong file có thể cách thời điểm deploy nhiều ngày. Đối với đợt rollback, bạn có thể triển khai một artifact cũ vào hôm nay; `build.time` vẫn là metadata thuộc artifact cũ.

Thông tin build cũng không phải **Software Bill of Materials (SBOM)**, danh sách CVE, chữ ký artifact hay attestation về nguồn gốc. Nó có ích để định danh và đối chiếu, nhưng không tự xác nhận chất lượng, tính an toàn hoặc nguồn gốc mật mã của sản phẩm.

## 2. Mối quan hệ giữa `springBoot.buildInfo` và `bootBuildInfo`

### 2.1 Một khai báo DSL đăng ký một task

Trong Gradle Groovy DSL:

```groovy
springBoot {
    buildInfo()
}
```

Dòng này nằm trong `build.gradle` của **project ứng dụng đang áp dụng Spring Boot Gradle plugin**. Nó **không phải lời gọi sinh file ngay lập tức**; trong giai đoạn Gradle configuration, plugin đăng ký và cấu hình một task có tên **`bootBuildInfo`**.

Task này thuộc kiểu `org.springframework.boot.gradle.tasks.buildinfo.BuildInfo`. Khi task được thực thi, nó ghi nội dung dạng Java properties vào:

```text
META-INF/build-info.properties
```

Theo tài liệu **Spring Boot Gradle Plugin 3.3**, thư mục output chuẩn là `META-INF` bên dưới resources output của **main source set**, thường là:

```text
build/resources/main/META-INF/build-info.properties
```

Plugin còn nối `classes` của Java plugin phụ thuộc vào task sinh metadata, nếu `classes` tồn tại. Vì `bootJar` sử dụng output của main source set, file build info có thể được mang theo vào archive như một classpath resource.

Sơ đồ:

```text
build.gradle
  springBoot { buildInfo() }
                |
                v
    Gradle đăng ký task bootBuildInfo
                |
        +-------+--------------------------+
        |                                  |
        v                                  v
 ./gradlew bootBuildInfo          classes phụ thuộc task
        |                                  |
        v                                  v
 build/resources/main/                ./gradlew bootJar
 META-INF/build-info.properties            |
                                           v
                              build/libs/build-meta-demo-...
                                  BOOT-INF/classes/
                                      META-INF/build-info.properties
```

Sơ đồ mô tả **mối phụ thuộc chính**, không phải toàn bộ task graph của Gradle. Trên Spring Boot 3.3, vị trí output được nêu như trên. **Đừng áp đặt đường dẫn này cho Spring Boot 4.x**: tài liệu plugin đời mới mô tả output mặc định `build/bootBuildInfo/META-INF/build-info.properties` và cấu hình source set resources dùng task output theo cơ chế tương ứng.

### 2.2 Bốn điều kiện để metadata đi vào sản phẩm

1. Có `org.springframework.boot` Gradle plugin và cấu hình `springBoot.buildInfo` trong **đúng module**.
2. Task `bootBuildInfo` được chạy hoặc được kéo theo task `classes`/`bootJar` như cấu hình của phiên bản đó.
3. File `META-INF/build-info.properties` được coi là tài nguyên của **main runtime classpath**.
4. Stage phát hành dùng **đúng executable JAR/WAR** có chứa tài nguyên, không dùng nhầm plain JAR, artifact cũ hoặc module khác.

Không có Actuator vẫn **có thể sinh file** bằng `bootBuildInfo`. Actuator chỉ là cơ chế thuận tiện để **đọc và công bố build metadata khi ứng dụng chạy**.

### 2.3 Khác biệt giữa `bootBuildInfo` và `build`

`build` là **Gradle lifecycle task** kết hợp build/assemble/check; `bootBuildInfo` là **task tạo resource**. Nó không thay thế `compileJava`, `test`, `processResources` hoặc `bootJar`.

Chạy riêng:

```bash
./gradlew bootBuildInfo
```

thường chỉ tạo hoặc cập nhật file metadata và những task liên quan, **chưa đủ** để tạo executable Boot JAR.

Chạy:

```bash
./gradlew bootJar
```

sẽ tạo executable JAR cho module ứng dụng, đồng thời kéo những bước cần tạo classes/resources, trong đó có `bootBuildInfo` khi đã cấu hình phù hợp.

Nếu chạy `./gradlew bootBuildInfo` rồi xem thư mục `build/libs` mà không có JAR, đừng kết luận task bị lỗi; bạn mới gọi **task tạo metadata**, chưa gọi task đóng gói.

## 3. Ví dụ Gradle Groovy DSL đầy đủ

Bài thực hành dùng một ứng dụng web Spring Boot đơn giản, có endpoint để kiểm tra build version, đồng thời dùng Actuator để xem file metadata.

### 3.1 Cấu trúc dự án

```text
build-meta-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat           (nếu đã tạo Gradle Wrapper)
├── gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/buildmeta/
    │   │   ├── BuildMetaApplication.java
    │   │   └── BuildMetadataController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/buildmeta/BuildMetadataTest.java
```

Nếu project chưa có Gradle Wrapper, tạo bằng Gradle cài sẵn **tương thích với Boot 3.3**, ví dụ `gradle wrapper --gradle-version 8.5`. Chạy Wrapper tạo từ nguồn đáng tin; không tải script Gradle tùy ý từ Internet. Nếu dùng PowerShell, thay `./gradlew` bằng `.\gradlew.bat`.

### 3.2 `settings.gradle`

```groovy
rootProject.name = 'build-meta-demo'
```

### 3.3 `build.gradle` – bản đầy đủ, ưu tiên build tái lập

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    buildInfo {
        // Tránh timestamp thay đổi ở mỗi lần chạy.
        excludes = ['time']

        // Những thông tin này được thêm thành build.channel.
        properties {
            additional = ['channel': 'training']
        }
    }
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **build file hoàn chỉnh** cho ứng dụng minh họa có Java 17 và mã ở phần tiếp theo. Trong Gradle Groovy DSL, `springBoot { buildInfo { ... } }` vừa đăng ký vừa tùy biến task `bootBuildInfo`; không cần gọi thêm `springBoot { buildInfo() }` ở một block khác.

Phân tích các thành phần:

- `id 'org.springframework.boot'` đăng ký Spring Boot Gradle plugin cho project hiện tại.
- `id 'java'` tạo source sets và task `classes`/`compileJava`/`processResources`/`test`.
- `io.spring.dependency-management` quản lý version dependencies qua Spring Boot dependency management; không phải plugin sinh build info.
- `spring-boot-starter-web` tạo ứng dụng HTTP có embedded Servlet container.
- `spring-boot-starter-actuator` kích hoạt infrastructure Actuator, cung cấp `BuildInfoContributor` và `BuildProperties` khi có resource hợp lệ.
- `springBoot.buildInfo` đăng ký task tạo `META-INF/build-info.properties`.
- `excludes = ['time']` ngăn sinh `build.time`, giảm biến đầu vào không ổn định.
- `properties.additional` thêm key riêng `channel`, sẽ được ghi vào file với **prefix `build.`**.
- `test.useJUnitPlatform()` giúp JUnit Jupiter test trong `src/test/java` chạy theo Gradle Java Test task.

**Không nhầm:** `excludes` của `buildInfo` dùng **tên trường metadata** như `time`; nó **không** loại dependency, source code hay các file khác khỏi executable JAR. Nó cũng không phải `configurations.exclude` của Gradle.

### 3.4 Vì sao chọn loại `time` ngay trong ví dụ?

Spring Boot Gradle Plugin 3.3 mô tả `build.time` mặc định là thời điểm build. Thay đổi theo mỗi lượt sẽ khiến task `bootBuildInfo` **không up-to-date**, kéo theo các task phụ thuộc (có thể bao gồm `test` và `bootJar`) phải xử lý lại và khiến output metadata không tái lập.

Trong ví dụ ta ưu tiên **bản dựng có đầu ra ổn định** hơn sự chính xác của "build vừa chạy lúc mấy giờ". Vì vậy `time` được loại ngay trong cấu hình mẫu. Nếu dự án cần build time vì yêu cầu audit/release, có thể giữ nó, nhưng phải hiểu chi phí hiệu năng và khả năng tái lập.

**Lưu ý:** loại riêng `build.time` là **điều kiện thuận lợi**, không phải chứng minh mọi JAR chắc chắn byte-for-byte giống nhau; kết quả còn phụ thuộc compiler, build inputs, archive metadata, phụ thuộc được phân giải và custom tasks.

## 4. Mã Java 17+ chạy được để chứng minh build-info

### 4.1 Lớp main Spring Boot

Tạo `src/main/java/com/example/buildmeta/BuildMetaApplication.java`:

```java
package com.example.buildmeta;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildMetaApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildMetaApplication.class, args);
    }
}
```

Đây là lớp ứng dụng chuẩn, không chạy được bằng `javac BuildMetaApplication.java` trần vì cần Spring Boot dependencies; dùng Gradle để biên dịch và đóng gói.

### 4.2 Controller đọc `BuildProperties` ở runtime

Tạo `src/main/java/com/example/buildmeta/BuildMetadataController.java`:

```java
package com.example.buildmeta;

import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BuildMetadataController {

    private final BuildProperties build;

    public BuildMetadataController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/build/version")
    public String version() {
        return "version=" + build.getVersion()
                + ";channel=" + build.get("channel");
    }
}
```

Đây là **mã Java 17+ hợp lệ trong project Spring Boot đã có Actuator/Web**. Khi resource được tạo đúng và được AutoConfiguration của Actuator nhận diện, Spring cung cấp một bean `BuildProperties` để inject vào constructor. Method `BuildProperties#getVersion()` trả string phiên bản; `get("channel")` truy cập thuộc tính bổ sung đã được đọc từ file `build-info.properties` (prefix `build.` được xử lý khi tạo `BuildProperties`).

Với cấu hình mẫu, response body mong đợi của `GET /build/version`:

```text
version=0.0.1-SNAPSHOT;channel=training
```

Đây là output **của phương thức Java** theo cấu hình ví dụ, không phải toàn bộ stdout khi khởi động Spring Boot. Server còn có banner/log và port có thể khác nếu môi trường ghi đè.

**Quan trọng:** constructor injection này **cố tình yêu cầu BuildProperties bắt buộc**. Nếu bạn bỏ cấu hình `buildInfo` hoặc Actuator khiến không có bean, ứng dụng có thể **không khởi động** vì thiếu bean. Điều đó giúp bài thực hành phát hiện lỗi sớm; trong dự án thật, nếu metadata là tính năng tùy chọn, hãy thiết kế một fallback rõ ràng hoặc sử dụng `ObjectProvider<BuildProperties>`, không lén bắt ứng dụng phụ thuộc vào metadata tùy ý.

### 4.3 Cấu hình `application.properties`

Tạo `src/main/resources/application.properties`:

```properties
spring.application.name=build-meta-demo

# info endpoint mặc định KHÔNG được expose qua HTTP.
management.endpoints.web.exposure.include=health,info

# Với resource build-info.properties, build contributor được bật mặc định
# trong Spring Boot 3.3; khai báo rõ nếu muốn người đọc nhận biết.
management.info.build.enabled=true
```

**Khác biệt quan trọng:** `BuildProperties` và `build-info.properties` **không tự làm URL `/actuator/info` được expose**. Ở Spring Boot 3.3, mặc định chỉ `health` được expose qua HTTP; cấu hình `management.endpoints.web.exposure.include=health,info` cho phép thêm info. Khi chạy public production, endpoint phải được xem xét và bảo vệ phù hợp.

Không đặt `management.endpoints.web.exposure.include=*` cho mọi môi trường chỉ để xem phiên bản, vì nhiều endpoint khác có thể lộ thông tin nội bộ hoặc cho phép thao tác quản trị.

### 4.4 Test xác minh bean và các thuộc tính

Tạo `src/test/java/com/example/buildmeta/BuildMetadataTest.java`:

```java
package com.example.buildmeta;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringBootTest
class BuildMetadataTest {

    @Autowired
    private BuildProperties properties;

    @Test
    void exposesExpectedBuildMetadata() {
        assertEquals("build-meta-demo", properties.getArtifact());
        assertEquals("com.example", properties.getGroup());
        assertEquals("build-meta-demo", properties.getName());
        assertEquals("0.0.1-SNAPSHOT", properties.getVersion());
        assertEquals("training", properties.get("channel"));
        assertNull(properties.getTime());
    }
}
```

Test này có hai mục đích: kiểm tra `BuildProperties` tồn tại trong Spring context, và kiểm tra **các giá trị đúng với `build.gradle` mẫu**. `assertNull(properties.getTime())` hợp lệ vì ta đã loại `time`; nếu bạn bỏ `excludes`, phải sửa assertion theo yêu cầu mới.

Test không tự chứng minh file **trong executable JAR** đã đúng, vì test có thể chạy trên main output classpath trước khi `bootJar` tạo archive. Phần 6 sẽ kiểm tra trực tiếp artifact cuối cùng.

## 5. Chạy `bootBuildInfo` và xem file trên ổ đĩa

### 5.1 Chạy task sinh metadata riêng

Từ thư mục có `build.gradle` và Wrapper:

```bash
./gradlew bootBuildInfo --console=plain --info
```

Hoặc trên Windows PowerShell:

```powershell
.\gradlew.bat bootBuildInfo --console=plain --info
```

Lệnh này tập trung chạy task metadata, **không phải lệnh build executable JAR**. Task output của **Spring Boot 3.3** dự kiến nằm ở:

```text
build/resources/main/META-INF/build-info.properties
```

Kiểm tra trên Bash:

```bash
test -f build/resources/main/META-INF/build-info.properties
cat build/resources/main/META-INF/build-info.properties
```

Windows:

```powershell
Test-Path -LiteralPath "build\resources\main\META-INF\build-info.properties"
Get-Content -LiteralPath "build\resources\main\META-INF\build-info.properties"
```

Với project mẫu, một dạng output **kỳ vọng theo dữ liệu cấu hình** là:

```properties
build.artifact=build-meta-demo
build.group=com.example
build.name=build-meta-demo
build.version=0.0.1-SNAPSHOT
build.channel=training
```

**Thứ tự dòng có thể khác**, tùy cách task ghi properties và cách công cụ hiển thị. Quan trọng là cặp key/value có mặt. **Không có `build.time`** trong bản mẫu, vì `excludes = ['time']`.

Đừng coi ví dụ là file đã được tạo thật trong môi trường của bạn; phải mở kết quả `bootBuildInfo` của project đang làm.

### 5.2 `bootBuildInfo` chạy riêng rồi `classes`

Dùng:

```bash
./gradlew classes --console=plain --info
```

Theo tài liệu Spring Boot Gradle 3.3, khi đã cấu hình `buildInfo` và project áp dụng Java plugin, task `classes` phụ thuộc `bootBuildInfo`. Vì vậy chạy `classes` sẽ kéo việc tạo file cần thiết, ngay cả khi người dùng không gọi `bootBuildInfo` trực tiếp.

Tuy nhiên, không được hiểu rằng tất cả task Gradle đều phụ thuộc bootBuildInfo. Ví dụ `./gradlew help` chủ yếu mô tả cấu hình và không có lý do cần chạy tác vụ sinh metadata.

### 5.3 Phân biệt `bootBuildInfo` với `processResources`

`processResources` xử lý/copy nguồn `src/main/resources`. `bootBuildInfo` là **task sinh resource** ở vị trí output được plugin quy định.

Với Spring Boot 3.3, plugin cấu hình `classes` phụ thuộc `bootBuildInfo` và task ghi vào resources output area. Nó không yêu cầu developer tự tạo file `src/main/resources/META-INF/build-info.properties`, cũng không yêu cầu gọi `processResources.expand(...)` để tự ghép chuỗi version.

**Đừng viết hai nguồn tạo cùng `META-INF/build-info.properties`**, ví dụ vừa có file thủ công ở `src/main/resources/META-INF` vừa bật `bootBuildInfo`, vì có nguy cơ ghi đè, bản cũ hoặc output/task ownership khó kiểm soát.

### 5.4 Khi nào `bootBuildInfo` có `UP-TO-DATE`?

Với cấu hình đã loại `time`, nếu inputs và outputs không thay đổi, lần sau task **có thể** hiển thị:

```text
> Task :bootBuildInfo UP-TO-DATE
```

Đây là output **minh họa có điều kiện**. Nếu group/name/version/additional values thay đổi, file bị xóa, task implementation/plugin version đổi hoặc có tác nhân khác tác động output, task cần chạy lại. `UP-TO-DATE` là kết quả Gradle kiểm tra, không phải một cờ bạn đặt cho task.

## 6. Đóng gói executable JAR và kiểm tra nội dung ZIP

### 6.1 Build đúng artifact

Chạy:

```bash
./gradlew clean test bootJar --console=plain
```

`clean` dùng để có build output sạch cho bài tập kiểm tra packaging lần đầu; **đừng dùng clean ở thí nghiệm đo up-to-date** ở phần 10. Trong ví dụ, `bootJar` tạo:

```text
build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar
```

Đường này là quy ước từ `rootProject.name` và `version` trong build script; nếu project đặt `archiveBaseName`, `archiveVersion`, `archiveClassifier` hoặc `destinationDirectory` khác, phải dùng đường output thật.

### 6.2 Vì sao metadata nằm bên trong `BOOT-INF/classes`?

Khi `bootJar` đóng gói executable JAR, các compiled classes và main resources nằm trong `BOOT-INF/classes`. Vì `META-INF/build-info.properties` là **classpath resource** của main source set, đường trong archive thường là:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Đường filesystem trước packaging và đường trong archive khác nhau:

| Giai đoạn | Vị trí |
| --- | --- |
| Output task `bootBuildInfo`, Spring Boot 3.3 mặc định | `build/resources/main/META-INF/build-info.properties` |
| Classpath resource theo main source set | `META-INF/build-info.properties` |
| Executable Boot JAR (Boot 3.3 layout thông thường) | `BOOT-INF/classes/META-INF/build-info.properties` |
| Executable Boot WAR nếu dùng `bootWar` | `WEB-INF/classes/META-INF/build-info.properties` |

**Không tìm file ở `BOOT-INF/lib`**: đó là nơi chứa dependency JAR lồng bên trong executable archive. Build metadata là **resource của ứng dụng**, không phải thư viện.

### 6.3 Kiểm tra bằng JDK `jar`

```bash
jar tf build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar
```

Để xác nhận đúng entry:

```bash
jar tf build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar \
  | grep -Fx 'BOOT-INF/classes/META-INF/build-info.properties'
```

Nếu có dòng:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

thì **file ZIP entry tồn tại**. Nó chưa chứng minh giá trị bên trong đúng; cần đọc nội dung. Trên macOS/Linux có `unzip`:

```bash
unzip -p build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar \
  BOOT-INF/classes/META-INF/build-info.properties
```

Kết quả cần có `build.version=0.0.1-SNAPSHOT` và `build.channel=training`, đồng thời **không có `build.time`**. Chú ý cách escape chuỗi trong Java properties nếu custom values chứa ký tự đặc biệt.

Nếu JAR không tồn tại hoặc bạn đang xem file `-plain.jar`, kết quả khác. Không gắn một đường dẫn cố định cho tất cả module.

### 6.4 Đọc archive trong PowerShell

```powershell
$jar = "build\libs\build-meta-demo-0.0.1-SNAPSHOT.jar"

if (-not (Test-Path -LiteralPath $jar)) {
    throw "Executable JAR not found"
}

$entries = & jar tf $jar
if ($LASTEXITCODE -ne 0) {
    throw "Cannot list archive"
}

$matches = @($entries | Select-String -SimpleMatch "BOOT-INF/classes/META-INF/build-info.properties")
if ($matches.Count -ne 1) {
    throw "Build info entry not found exactly once"
}

Write-Output "PASS: build-info.properties entry found"
```

Đây là **script chỉ kiểm tra sự tồn tại của ZIP entry**. Để xem nội dung, dùng công cụ giải nén ZIP đáng tin cậy hoặc API ZIP của .NET. Kiểm tra một file có mặt **không đủ** để xác minh group/version/time; cần đối chiếu key/value.

### 6.5 Phân biệt file thường và file executable

Gradle Spring Boot plugin có thể tạo **hai JAR** nếu cả `jar` và `bootJar` được thực thi:

```text
build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar          # executable Boot JAR
build/libs/build-meta-demo-0.0.1-SNAPSHOT-plain.jar    # JAR thường
```

Theo quy ước Boot Gradle 3.3, plain JAR dùng classifier `plain` để tránh tên trùng. File plain có thể chứa resource ở `META-INF/build-info.properties` gần root chứ không ở `BOOT-INF/classes`. Vì vậy một grep tìm `BOOT-INF/classes` trên plain JAR có thể FAIL dù resource đã được đóng gói.

Đối với bài này, kiểm tra **đúng Boot JAR mà CI sẽ deploy**, không dùng `*.jar` kiểu wildcard nếu nó có thể khớp nhiều output.

## 7. Kiểm chứng runtime: `BuildProperties` và `/actuator/info`

### 7.1 Chạy bản đóng gói

Trong terminal thứ nhất:

```bash
java -jar build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar
```

Với JDK tương thích và cổng 8080 đang rảnh, app web sẽ khởi động và giữ process chạy. Mở terminal khác:

```bash
curl --fail --silent --show-error http://localhost:8080/build/version
```

Response body mong đợi theo mã mẫu:

```text
version=0.0.1-SNAPSHOT;channel=training
```

Nếu response khác, kiểm tra đã build đúng file, nguồn metadata có phải version khác, hay môi trường có custom override Gradle project version. Đừng suy rằng một endpoint trả 200 chứng minh archive chứa đúng build info cho tới khi đã đọc key/value.

### 7.2 Actuator info endpoint

Vì ứng dụng có `spring-boot-starter-actuator` và config expose `info`:

```bash
curl --fail --silent --show-error http://localhost:8080/actuator/info
```

Một dạng JSON kỳ vọng **về cấu trúc**:

```json
{
  "build": {
    "artifact": "build-meta-demo",
    "group": "com.example",
    "name": "build-meta-demo",
    "version": "0.0.1-SNAPSHOT",
    "channel": "training"
  }
}
```

Đây là **ví dụ theo cấu hình**, không khẳng định JSON key order giữ nguyên hoặc output đã lấy từ máy thực. `time` không có vì task đã cấu hình exclude. Endpoint có thể chứa thêm thông tin nếu các `InfoContributor` khác được bật hoặc user bổ sung metadata.

### 7.3 Vì sao `/actuator/info` có thể trả `{}` hoặc 404?

Các tầng liên quan khác nhau:

| Triệu chứng | Nguyên nhân đáng kiểm tra |
| --- | --- |
| HTTP 404 | Không có Actuator, endpoint `info` bị disable/không expose, sai port hoặc sai management base path |
| HTTP 401/403 | Security rule/authorization đang bảo vệ endpoint |
| HTTP 200 nhưng `{}` | Không có `BuildProperties`, build contributor bị disable hoặc không có info contributors khác |
| Có `build.version` trong file nhưng `/actuator/info` không có `build` | Thiếu resource **trên runtime classpath**, auto configuration hoặc contributor config khác |
| `/build/version` không khởi động vì thiếu bean | Constructor yêu cầu `BuildProperties` nhưng bean chưa được tạo |
| `/build/version` trả version cũ | Chạy artifact cũ, Gradle output stale, deploy dùng sai module hoặc metadata bị override |
| `/actuator/info` có build nhưng thiếu `time` | Cấu hình `excludes=['time']` của ví dụ đang hoạt động đúng |

Spring Boot 3.3 mặc định chỉ **`health`** được expose qua HTTP. Để xem `info`, cần `management.endpoints.web.exposure.include=health,info` như ví dụ. Nếu ứng dụng có Spring Security, endpoint còn chịu luật bảo vệ truy cập. Đừng sửa bảo mật bằng cách mở toàn bộ Actuator ra Internet.

### 7.4 Có file nhưng không có bean là hai vấn đề khác nhau

`bootBuildInfo` là **chức năng của build plugin**, chạy tại Gradle build time. `BuildProperties` là **bean runtime** do Spring Boot auto-configuration tạo khi có module và resource phù hợp. `BuildInfoContributor` là **Actuator component** dùng bean để cung cấp thông tin.

```text
Gradle build-time                      Spring runtime
-----------------                      --------------
springBoot { buildInfo() }            classpath:
      |                               META-INF/build-info.properties
      v                                      |
bootBuildInfo ghi resource                   v
      |                               BuildProperties bean
      v                                      |
bootJar đưa resource vào JAR                 v
                                     BuildInfoContributor
                                             |
                                             v
                                      /actuator/info
```

Nếu không dùng `spring-boot-starter-actuator`, việc có file metadata không đồng nghĩa bạn có sẵn endpoint Actuator. Ngược lại, chỉ thêm Actuator dependency mà không tạo resource cũng không khiến `build-info.properties` tự xuất hiện.

## 8. Tùy biến thuộc tính mặc định

### 8.1 Đổi tên artifact, group, name hoặc version

Plugin cung cấp `properties` trên `buildInfo`, có thể override các giá trị mặc định. Ví dụ **trích đoạn thay thế** cho block `springBoot` trong `build.gradle`:

```groovy
springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            artifact = 'release-app'
            group = 'com.example.platform'
            name = 'Release Application'
            version = '1.2.3'
        }
    }
}
```

Trong trường hợp này, output metadata có thể chứa:

```properties
build.artifact=release-app
build.group=com.example.platform
build.name=Release Application
build.version=1.2.3
```

Đây là **giá trị đã override**, không chứng minh rằng `project.version` hoặc tên file JAR đã đổi theo. Nếu build script thực tế vẫn có `version='0.0.1-SNAPSHOT'`, bạn có thể tạo ra tình trạng **file JAR mang version A nhưng build-info mang version B**. Đó có thể là yêu cầu cố ý, nhưng thường là dấu hiệu cấu hình mâu thuẫn.

Để đồng bộ, ưu tiên quản lý Gradle `group`/`version` và archive naming ở một nguồn được kiểm soát; chỉ override metadata nếu có quy ước rõ ràng và kiểm tra consistency trong CI.

### 8.2 Exclude một hoặc nhiều trường

Ví dụ:

```groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
```

`excludes` nhận **tên trường không có prefix `build.`**. Ví dụ dùng `time`, **không** dùng `build.time` trong `excludes`.

Bạn cũng có thể loại trường khác như `name` nếu thực sự không muốn ghi nó, nhưng khi runtime gọi `BuildProperties#getName()` có thể nhận `null`. Nếu dùng field làm startup dependency bắt buộc, không nên exclude tùy ý mà chưa sửa contract ứng dụng/test.

**Không nhầm exclusion metadata với exclusion dependency**. Nó không ngăn `spring-boot-starter-actuator` hoặc JAR khác bị đóng gói.

### 8.3 Thêm custom properties

Ví dụ:

```groovy
springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'channel': 'training',
                'flavor': 'community'
            ]
        }
    }
}
```

Trong file output, các custom keys được ghi với prefix `build.`:

```properties
build.channel=training
build.flavor=community
```

Trong Java khi dùng `BuildProperties`, truy cập `build.get("channel")` và `build.get("flavor")`, không phải `build.get("build.channel")`. Actuator có thể expose chúng dưới object `build` tương ứng.

Đừng đưa `password`, `privateKey`, `API_TOKEN`, mật khẩu database, URL nội bộ nhạy cảm hoặc user/machine identity không cần thiết vào metadata. File sẽ nằm **trong executable archive** và có thể được công bố qua endpoint info nếu bật. Cấu hình HTTP security không xóa dữ liệu đã đóng trong JAR.

### 8.4 Provider cho giá trị đến từ CI

Một giá trị có thể tính **lazy** từ Gradle Provider API để tránh đọc environment quá sớm. Spring Boot 3.3 Gradle Plugin hỗ trợ additional property values được tính qua Provider. Ví dụ **trích đoạn thay cho block `springBoot`**, chỉ dùng nếu CI định nghĩa biến môi trường tương ứng:

```groovy
def releaseChannel = providers.environmentVariable('RELEASE_CHANNEL')
    .orElse('local')

springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = ['channel': releaseChannel]
        }
    }
}
```

Đầu ra được mong đợi khi `RELEASE_CHANNEL=qa` là `build.channel=qa`; khi biến không tồn tại sẽ lấy giá trị `local`.

Lợi ích của Provider: Gradle có cơ chế theo dõi/lazy evaluation phù hợp hơn so với đọc tùy tiện `System.getenv` trong nhiều chỗ rồi giấu ảnh hưởng tới output. Tuy vậy, **mỗi lần biến CI thực sự đổi thì resource cũng đổi**; việc `bootBuildInfo` chạy lại có thể là hành vi **đúng**, không phải lỗi performance.

**Đừng dùng một giá trị thay đổi mọi lần như random build number** nếu mục tiêu là artifact reproducible mà không thật sự cần giá trị đó. Nếu build number là một phần release identity, chấp nhận việc nó tác động output và ghi provenance chính xác.

### 8.5 Commit ID không tự có trong `buildInfo`

`build-info.properties` và `git.properties` là **hai loại metadata khác nhau**:

- `build-info.properties` đến từ task `bootBuildInfo`.
- `git.properties` thường cần một plugin/cơ chế tạo Git information riêng; `BuildProperties` không tự quét Git repository để lấy commit.
- `GitProperties`/`GitInfoContributor` là hướng Spring Boot/Actuator đọc Git metadata khi file tương ứng có trên classpath.

Nếu tổ chức muốn ghi commit vào `buildInfo.properties` qua `additional`, cần đưa commit value vào task input một cách đáng tin cậy và đảm bảo không lộ thông tin không nên công bố. Không tự tạo "commit hash" từ ngày build hoặc dùng version như một giá trị giả.

## 9. Kotlin DSL `build.gradle.kts`

### 9.1 Cấu hình tương đương với ví dụ đầy đủ

`settings.gradle.kts`:

```kotlin
rootProject.name = "build-meta-demo"
```

`build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
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
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

springBoot {
    buildInfo {
        excludes.set(setOf("time"))
        properties {
            additional.set(mapOf("channel" to "training"))
        }
    }
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là **file Kotlin DSL đầy đủ** dành cho cùng mã Java ở phần 4, không dùng đồng thời với Groovy `build.gradle` trong một project. Nếu muốn dùng Kotlin DSL, thay file cũ chứ không đặt cả hai rồi đoán Gradle ưu tiên bản nào.

Cú pháp đối chiếu:

| Groovy | Kotlin |
| --- | --- |
| `springBoot { buildInfo() }` | `springBoot { buildInfo() }` |
| `excludes = ['time']` | `excludes.set(setOf("time"))` |
| `properties { additional = ['channel':'training'] }` | `properties { additional.set(mapOf("channel" to "training")) }` |
| `version = '0.0.1-SNAPSHOT'` | `version = "0.0.1-SNAPSHOT"` |

**Không dán cú pháp map `['channel':'training']` của Groovy vào Kotlin.** Kết quả cần xác minh vẫn là cùng file `META-INF/build-info.properties` và cùng giá trị của các key, không chỉ Gradle sync trong IDE thành công.

### 9.2 Thêm custom properties khác trong Kotlin

Trích đoạn Kotlin DSL:

```kotlin
springBoot {
    buildInfo {
        excludes.set(setOf("time"))
        properties {
            additional.set(
                mapOf(
                    "channel" to "training",
                    "flavor" to "community"
                )
            )
        }
    }
}
```

Nếu đang dùng Kotlin DSL, có thể xem task sau khi build config được đánh giá:

```bash
./gradlew tasks --all
./gradlew help --task bootBuildInfo
./gradlew bootBuildInfo --console=plain --info
```

Nếu Gradle báo `Task 'bootBuildInfo' not found`, kiểm tra Spring Boot plugin đã thực sự được **apply** trong module chưa và `buildInfo` đã được gọi chưa; chỉ khai báo plugin với `apply false` ở root chưa làm task xuất hiện trong mọi subproject.

## 10. `build.time` và tác động đến up-to-date/reproducible build

### 10.1 Vì sao default build time đặc biệt?

Spring Boot Gradle 3.3 documentation cảnh báo `build.time` mặc định được sinh từ **thời điểm project được build**. Giá trị này khác nhau ở những lần chạy, dẫn tới:

```text
./gradlew bootJar
    |
    v
bootBuildInfo tạo build.time=T1
    |
    v
classes/resource output thay đổi
    |
    v
bootJar/JAR có thể thay đổi

./gradlew bootJar  (không sửa Java)
    |
    v
bootBuildInfo tạo build.time=T2
    |
    v
file metadata đổi dù source không đổi
    |
    v
các task phụ thuộc phải xem xét chạy lại
```

Điều này không có nghĩa **Gradle không hỗ trợ up-to-date**. Task vẫn hoạt động đúng với một **input thời gian luôn đổi**; vấn đề nằm ở việc project có thật sự cần thời điểm build mới trong artifact mỗi lần hay không.

Nếu luôn tạo `build.time=now()`, hai build từ cùng source code có thể cho hai `build-info.properties` khác nhau, khiến executable archive khác byte. Điều đó ảnh hưởng reproducibility, build cache và công việc downstream như tests/JAR packaging.

### 10.2 Thử so sánh hai cấu hình

**Thí nghiệm A — giữ time mặc định**:

```groovy
springBoot {
    buildInfo()
}
```

Chạy hai lần:

```bash
./gradlew bootBuildInfo --console=plain --info
./gradlew bootBuildInfo --console=plain --info
```

Theo tài liệu Spring Boot 3.3, task sinh build info **không bao giờ up-to-date** với time mặc định thay đổi. Có thể kiểm tra `build.time` trong output sau hai lượt; định dạng timestamp/độ phân giải cụ thể phụ thuộc cách plugin ghi.

**Thí nghiệm B — loại time**:

```groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
```

Chạy hai lần **không dùng clean**:

```bash
./gradlew bootBuildInfo --console=plain --info
./gradlew bootBuildInfo --console=plain --info
```

Nếu không có thay đổi nào khác, lượt thứ hai **có thể** báo `UP-TO-DATE`. Khi đó `build-info.properties` cũng không chứa `build.time`. Hãy kiểm tra task outcome và nội dung file thay vì chỉ so thời gian đồng hồ.

### 10.3 Tại sao không dùng `clean` để đo up-to-date?

`./gradlew clean bootBuildInfo` xóa build outputs trước khi task chạy. Sau `clean`, task không còn output cũ cho local up-to-date check. Nếu build cache bật, một task cacheable có thể `FROM-CACHE`, nhưng đó là **cơ chế khác**.

Muốn chứng minh khả năng `UP-TO-DATE`, chạy **cùng task hai lần liên tiếp, không clean và không sửa build script**. Muốn kiểm tra artifact từ trạng thái sạch, dùng `clean bootJar` **ở lượt riêng**, không trộn hai phép đo.

### 10.4 Build time có thể quan trọng cho vận hành

Có hệ thống yêu cầu thời gian phát hành/đóng gói cho audit. Khi đó **đừng xóa time chỉ để tối ưu build** mà bỏ qua yêu cầu nghiệp vụ. Cân nhắc:

- Phân biệt build timestamp và deployment timestamp trong hệ thống quản trị phát hành.
- Dùng giá trị **được cố định cho release** nếu quy trình có nguồn thời gian đáng tin và plugin version hỗ trợ cấu hình thích hợp.
- Không đặt timestamp động không khai báo vào mọi custom task.
- Xác minh tính tương thích của `BuildProperties#getTime()`: nó trả `Instant` khi parse được hoặc `null` khi field vắng/không parse được.
- Ghi nhận nếu intentionally giữ timestamp, phải chấp nhận task invalidation và artifact không hoàn toàn tái lập từ cùng đầu vào.

Một `build.time` được ghi dưới dạng ISO-8601 có thể giúp tra cứu nhưng **không chứng minh thời điểm deploy hoặc thời điểm Git commit**. Ghi thời gian theo một quy ước rõ ràng.

### 10.5 Build cache vs up-to-date

| Cơ chế | Dấu hiệu | Điều kiện chính |
| --- | --- | --- |
| Up-to-date | `bootBuildInfo UP-TO-DATE` | Inputs/outputs hiện còn hợp lệ theo execution history trong workspace |
| Build cache | `bootBuildInfo FROM-CACHE` nếu task được hỗ trợ cache và key khớp | Có cached outputs phù hợp |
| Task chạy bình thường | `bootBuildInfo` không nhãn | Có thay đổi đầu vào hoặc output không đủ điều kiện reuse |
| Clean build | Có thể thực thi hoặc lấy cache | Local build outputs bị xóa; không nên suy là "tự biên dịch lại tất cả" |

Không đảm bảo mọi phiên bản task `BuildInfo` luôn cacheable; xem outcome thật và tài liệu plugin. Chỉ áp dụng build cache cho task có input/output đầy đủ và metadata không chứa dữ liệu nhạy cảm không nên chia sẻ.

## 11. Multi-module Gradle: task thuộc module nào?

Giả sử:

```text
project/
├── settings.gradle
├── app/
│   ├── build.gradle
│   └── src/main/java/...
└── core/
    ├── build.gradle
    └── src/main/java/...
```

`settings.gradle`:

```groovy
rootProject.name = 'platform'
include 'app', 'core'
```

Nếu `:app` là Spring Boot **executable application**, thông thường chỉ **`app/build.gradle`** cần apply Spring Boot plugin và `springBoot { buildInfo() }`. `:core` là thư viện Java dùng bởi app có thể chỉ cần `java-library`.

Chạy:

```bash
./gradlew :app:bootBuildInfo --console=plain
./gradlew :app:bootJar --console=plain
./gradlew :app:tasks --all
```

Nếu gọi `./gradlew bootBuildInfo` từ root và Gradle không tìm thấy task tại root, điều đó không chứng minh build-info bị hỏng; có thể task nằm trong subproject `:app`. Cũng có trường hợp Gradle cho phép gọi tên task mà nó match ở nhiều module, cần dùng **qualified task path** khi muốn hành động chính xác.

### 11.1 Vì sao không cần buildInfo ở mọi module library?

Executable Spring Boot JAR mang classes/resources của **module ứng dụng** và những dependencies. Nếu một thư viện nội bộ `:core` sinh riêng `META-INF/build-info.properties` rồi app cũng sinh file cùng path, runtime classpath có thể có **nhiều resource trùng tên**. Cơ chế classloader có thể chọn một bản theo classpath order, không cho kết quả rõ ràng như bạn kỳ vọng.

Vì vậy nếu mục tiêu là **metadata của artifact phát hành**, sinh một bản canonical build info ở **module ứng dụng đóng gói** thường dễ quản trị hơn. Nếu mỗi module cần metadata riêng, dùng tên/đường dẫn resource riêng và contract đọc riêng, không để tất cả cạnh tranh cho một path `META-INF/build-info.properties`.

### 11.2 Artifact name khác project name

Task `bootBuildInfo` có `build.artifact` mặc định từ **base name của `bootJar`/`bootWar`**, còn `build.name` mặc định là `project.name`. Nếu bạn đổi `bootJar.archiveBaseName` thành `service-runtime` mà project.name vẫn là `app`, hai trường có thể khác.

Đừng tự kết luận đó là lỗi; hãy xác minh tên mong đợi của artifact và metadata theo chính sách module. Trước khi dùng `build.version` làm release identity, so nó với Gradle project version, image tag và deployment descriptor để tránh drift.

## 12. Các lỗi thường gặp với `bootBuildInfo`

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `Task 'bootBuildInfo' not found` | Chưa có `springBoot { buildInfo() }`/`buildInfo { ... }`, Spring Boot plugin không apply, hoặc task nằm ở module khác | Kiểm tra `plugins`, `:app:tasks --all`, đúng project |
| Chạy `bootBuildInfo` thành công nhưng không có JAR | Task chỉ tạo metadata, không đóng gói | Chạy `bootJar`/`bootWar` để tạo artifact |
| Tìm `build/bootBuildInfo` không thấy trong Boot 3.3 | Đường output đó thuộc hướng dẫn plugin đời mới | Với Boot 3.3 kiểm tra `build/resources/main/META-INF/build-info.properties` |
| Có file local nhưng JAR không có entry | Chọn nhầm JAR/module, task graph/classpath custom hoặc output bị loại | Kiểm tra `bootJar`, `jar tf`, main resources |
| `bootJar` có file nhưng `/actuator/info` là `{}` | Không có Actuator/contributor runtime hoặc resource không trên classpath | Kiểm tra starter, bean `BuildProperties`, runtime classpath |
| `/actuator/info` HTTP 404 | Info endpoint không expose hoặc sai port/base path | Expose `health,info`, kiểm tra management server config |
| `/actuator/info` HTTP 401/403 | Security đang bảo vệ endpoint | Dùng quyền xác thực phù hợp; không mở toàn bộ endpoint |
| `BuildProperties` không inject được | Resource thiếu, không có auto-configuration phù hợp hoặc bean bị disable | Kiểm tra `META-INF/build-info.properties` và Actuator |
| `build.time` vắng mặt | `excludes=['time']` | Đây là mong đợi trong ví dụ |
| `bootBuildInfo` luôn chạy mỗi lần | `build.time` mặc định thay đổi | Nếu không cần time, exclude `time` rồi thử hai lượt |
| Version bên trong không khớp filename JAR | Metadata `properties.version` bị override khác `project.version` | Đồng bộ nguồn version, kiểm tra CI |
| Metadata vẫn là version cũ | Đang chạy bản cũ, copy nhầm `-plain.jar` hoặc task input/output bị cấu hình sai | Làm clean build một lượt có chủ đích rồi kiểm tra đúng artifact |
| Thay CI channel mà file không đổi | Additional property không nhận giá trị/Provider đúng, hoặc task được chọn sai module | Đọc generated file, Gradle task input và logs |
| Test liên tục chạy lại không đổi Java | Time thay làm resource thay, kéo task downstream | Loại `time` nếu phù hợp hoặc chấp nhận chi phí |
| Properties có key `build.buildNumber` | Additional name được plugin prefix `build.` | Trong build DSL chỉ đặt tên `buildNumber`, không tự thêm prefix |
| Build info lộ token/địa chỉ nhạy cảm | Đưa secret từ environment/CI vào additional | Không đưa secret vào artifact; thay đổi metadata và quay vòng secret nếu lộ |
| Có hai bản `build-info.properties` trong classpath | Module/library hoặc file thủ công bị trùng path | Thiết kế một nguồn canonical, loại bản trùng |
| Actuator hiển thị Git commit khác mong đợi | Git properties sinh từ cơ chế riêng | Kiểm tra `git.properties`/plugin Git và artifact được deploy |
| `buildInfo` và Maven build-info bị trộn | Nhầm DSL Gradle với Maven plugin goal | Dùng đúng build system và đúng plugin |
| CI xanh nhưng image chạy version cũ | Deploy stage dùng artifact khác đã test hoặc Docker cache/copy sai | Kiểm tra hash/tag và đường dẫn artifact thật |
| Cấu hình dùng cú pháp Kotlin trong Groovy | DSL không khớp file `.gradle`/`.gradle.kts` | Dùng bảng so Groovy/Kotlin ở phần 9 |

### Trình tự chẩn đoán ngắn

1. Xác định **module chứa ứng dụng** và build system đúng.
2. Kiểm tra Spring Boot Gradle plugin có apply ở module đó, và `springBoot.buildInfo` đã được cấu hình.
3. Chạy `:module:bootBuildInfo --info` và mở **file output** đúng version Boot.
4. Chạy `:module:bootJar`, dùng `jar tf` để xác nhận ZIP entry.
5. Đọc **giá trị** `build.version`, `build.artifact`, `build.channel` và có/không `build.time`.
6. Chạy `java -jar` trên chính JAR đã kiểm tra, thử `/build/version` và `/actuator/info`.
7. Nếu endpoint không phù hợp, tách lỗi bean, contributor, exposure, security và config.
8. Nếu build chậm, thử hai lượt không clean và đọc `UP-TO-DATE`; không bật/tắt cache theo cảm giác.
9. Đối chiếu artifact được CI đưa vào image/deploy với artifact đã xác minh.

## 13. CI/CD: kiểm chứng metadata trước khi phát hành

### 13.1 Chính sách tối thiểu

Một pipeline release có thể yêu cầu:

- `build-info.properties` phải nằm trong **chính executable JAR được publish**.
- `build.version` phải khớp phiên bản release được phép triển khai.
- `build.artifact` phải là tên module/app mong đợi.
- Nếu chính sách ưu tiên reproducible build, `build.time` phải vắng mặt hoặc ổn định theo quy ước.
- Additional metadata không chứa secret/PII và không được công bố qua Actuator nếu có rủi ro.
- Build/release dùng **đúng một file artifact** từ stage đã kiểm tra; tránh rebuild ở stage deploy với input khác.
- HTTP `/actuator/info` chỉ được expose và bảo vệ khi thật sự cần.

**Không coi timestamp hoặc version string trong build-info là chữ ký đảm bảo nguồn gốc**. Nếu yêu cầu provenance nghiêm ngặt, cần kết hợp checksum, artifact signing/attestation, SBOM và chính sách release.

### 13.2 Ví dụ Bash gate kiểm tra executable JAR

Với dự án của phần 3:

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar"
resource="BOOT-INF/classes/META-INF/build-info.properties"

if [[ ! -f "$artifact" ]]; then
    echo "FAIL: executable artifact missing"
    exit 1
fi

# Bắt lỗi ZIP/JAR hỏng hoặc sai file.
entries="$(jar tf "$artifact")"

if ! printf '%s\n' "$entries" | grep -Fxq "$resource"; then
    echo "FAIL: build info resource missing in executable JAR"
    exit 1
fi

# Script mẫu sử dụng unzip; nếu môi trường CI không có,
# thay bằng công cụ ZIP/JDK đáng tin cậy.
metadata="$(unzip -p "$artifact" "$resource")"

if ! printf '%s\n' "$metadata" | grep -Fxq 'build.version=0.0.1-SNAPSHOT'; then
    echo "FAIL: unexpected build version"
    exit 1
fi

if ! printf '%s\n' "$metadata" | grep -Fxq 'build.channel=training'; then
    echo "FAIL: missing expected release channel"
    exit 1
fi

if printf '%s\n' "$metadata" | grep -Eq '^build[.]time='; then
    echo "FAIL: build.time should be excluded for this release"
    exit 1
fi

echo "PASS: Spring Boot build metadata verified"
```

Dòng in ra **khi các điều kiện của script đạt**:

```text
PASS: Spring Boot build metadata verified
```

Đây là **output dự kiến**, không phải bằng chứng script đã chạy trên file thật. Nếu thiếu JAR/resource, version/channel không đúng hoặc time xuất hiện khi không được phép, script in FAIL và exit 1.

Cổng này phù hợp **dự án mẫu có property values ASCII đơn giản**. Với file Java `.properties` thực tế có escaped characters, line continuations, unicode escape hoặc metadata tùy biến, cần parse bằng Java `Properties.load` hoặc một parser đúng chuẩn thay vì dùng `grep` để diễn giải toàn bộ cú pháp. Đối với CI có version được tạo tự động, lấy giá trị mong đợi từ nguồn phát hành được kiểm soát, không cố định `0.0.1-SNAPSHOT`.

### 13.3 Kiểm tra byte artifact và runtime

Sau khi gate PASS:

```bash
sha256sum build/libs/build-meta-demo-0.0.1-SNAPSHOT.jar
```

Ghi checksum để stage deploy có thể so đúng artifact. Khi dùng Docker image, kiểm tra Dockerfile/Buildpacks đang dùng **file executable JAR đã được gate xác minh**, không dùng một file khác hoặc build lại với task/version không cùng cấu hình.

Nếu một image đã chạy, metadata nội bộ `/actuator/info` (khi được expose có kiểm soát) có thể giúp đối chiếu version với release record. Nhưng một chuỗi version giống nhau chưa bảo đảm byte artifact giống nhau; dùng checksum/digest và provenance khi cần.

## 14. Không để metadata phát hành trở thành rủi ro bảo mật

`META-INF/build-info.properties` nằm trong artifact thường có thể bị người có artifact đọc được. Nếu Actuator `/info` được expose, một phần dữ liệu còn có thể ra HTTP.

**Nên ghi** group/artifact/name/version, channel công khai hoặc commit id không nhạy cảm theo chính sách.

**Không nên ghi** access token, private key, database password, AWS credentials, CI bearer token, địa chỉ hệ thống nội bộ chưa được phép công bố hoặc thông tin cá nhân không cần thiết.

Nếu app có Spring Security, endpoint `info` có thể được bảo vệ; nếu không có Spring Security và `info` được expose, bất kỳ bên nào tới được HTTP endpoint có thể xem. Đừng mặc định metadata public là vô hại chỉ vì nó có chữ "info". Kiểm tra firewall, auth và exposure theo môi trường.

**Lưu ý:** tắt `management.endpoints.web.exposure.include=info` **không xóa metadata khỏi JAR**. Nếu dữ liệu lỡ chứa secret, phải thay đổi cách tạo artifact và xử lý lộ lọt theo quy trình bảo mật, không chỉ tắt endpoint.

## 15. Các bài thực hành

### Thực hành A — Xác nhận task được đăng ký

1. Tạo Gradle project mẫu, apply đúng Spring Boot plugin 3.3.13.
2. Chạy `./gradlew tasks --all` và tìm `bootBuildInfo`.
3. Tạm bỏ block `springBoot.buildInfo` trên **bản sao lab**, chạy lại xem task còn được đăng ký không. Hoàn nguyên sau thử.
4. Giải thích vì sao plugin DSL đăng ký task trong configuration phase, còn task tạo file trong execution phase.

### Thực hành B — Đọc file metadata

1. Chạy `./gradlew bootBuildInfo`.
2. Xác minh đường `build/resources/main/META-INF/build-info.properties` của Boot 3.3.
3. Mở file và ghi chính xác `build.artifact`, `build.group`, `build.name`, `build.version`, `build.channel`.
4. Giải thích vì sao không có `build.time` trong mẫu.
5. Đổi `version` trong project thành một giá trị thử trên nhánh lab, chạy lại task và xem file đã cập nhật chưa; hoàn nguyên version.

### Thực hành C — So Gradle output và executable JAR

1. Chạy `./gradlew clean test bootJar`.
2. Dùng `jar tf` xác minh `BOOT-INF/classes/META-INF/build-info.properties`.
3. Giải nén đúng entry và đối chiếu property values với file `build/resources/main`.
4. Chạy `java -jar` và `GET /build/version`.
5. Giải thích vì sao chỉ chạy `bootBuildInfo` không tạo JAR; vì sao file nằm trong `BOOT-INF/classes` thay vì `BOOT-INF/lib`.

### Thực hành D — Actuator info

1. Bật `spring-boot-starter-actuator` và expose `health,info` ở cấu hình lab.
2. Gọi `GET /actuator/info`, quan sát object `build`.
3. Gỡ `management.endpoints.web.exposure.include=health,info` trên bản sao, thử lại và giải thích vì sao resource có thể vẫn tồn tại dù HTTP trả 404.
4. Thử tắt `management.info.build.enabled` ở lab và quan sát JSON khác; không xoá JAR metadata chỉ để thay HTTP output.
5. Đối chiếu `/actuator/info` và `/build/version`, xác định điểm chung là `BuildProperties`.

### Thực hành E — Tác động của build time

1. Đổi block buildInfo thành `springBoot { buildInfo() }`, chạy `bootBuildInfo` hai lần không clean, đọc task outcome và `build.time`.
2. Khôi phục `excludes = ['time']` rồi chạy hai lần, không đổi input.
3. Ghi xem `bootBuildInfo UP-TO-DATE` có xuất hiện không.
4. Giải thích vì sao timestamp động làm output khác và có thể kéo `test`/`bootJar` chạy lại.
5. Không "tối ưu" bằng cách ép `outputs.upToDateWhen { true }` vì có thể tạo metadata sai.

### Thực hành F — Kotlin DSL và multi-module

1. Chuyển project lab sang `build.gradle.kts` tương đương.
2. Cấu hình `excludes.set(setOf("time"))` và `additional.set(mapOf("channel" to "training"))`.
3. Nếu ứng dụng là `:app` trong multi-project, chạy `./gradlew :app:bootBuildInfo`.
4. Giải thích vì sao việc chỉ apply Boot plugin ở root với `apply false` không tự đăng ký task ở subprojects.
5. Chỉ ra nguy cơ hai module cùng sinh resource `META-INF/build-info.properties` và xuất hiện trong một classpath.

### Thực hành G — Viết checklist CI

Tạo một bước kiểm tra sau `bootJar`:

1. Xác minh artifact đúng đường dẫn.
2. Kiểm tra có `BOOT-INF/classes/META-INF/build-info.properties`.
3. Đọc phiên bản thật từ file, so với release version mong đợi.
4. Kiểm tra không có key bí mật hoặc `build.time` nếu chính sách yêu cầu loại.
5. Ghi SHA-256 và lưu artifact đã kiểm tra để deploy.
6. Kiểm tra endpoint runtime qua quyền truy cập thích hợp.

**Tiêu chí đạt:** có bằng chứng từ **DSL cấu hình → task `bootBuildInfo` → file output → executable JAR/WAR → `BuildProperties` → Actuator/runtime**. Biết tách tác động của `time` lên performance khỏi tính đúng của metadata và biết chọn đúng phiên bản plugin/đường dẫn output.

## 16. Tài liệu chính thức

- Spring Boot 3.3 Gradle Plugin — Integrating with Actuator (task `bootBuildInfo`, output path, default properties, `excludes`, `additional`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html
- Spring Boot 3.3 — Actuator Endpoints, build information và endpoint exposure: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Java API của `BuildProperties` và `getTime()`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html
- Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives (`bootJar`, `bootWar`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Gradle — Incremental Build, task inputs/outputs/up-to-date: https://docs.gradle.org/current/userguide/incremental_build.html
- Gradle — Java Plugin, `classes` và resource output: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Provider API và build environment properties: https://docs.gradle.org/current/userguide/build_environment.html
- Gradle — Build Cache, task outputs và cache keys: https://docs.gradle.org/current/userguide/build_cache.html

**Ghi nhớ:** `springBoot { buildInfo() }` là **DSL cấu hình**, `bootBuildInfo` là **task tạo file**; task output chuẩn của Spring Boot **3.3** là `build/resources/main/META-INF/build-info.properties` và khi đi vào executable JAR thường nằm ở `BOOT-INF/classes/META-INF/build-info.properties`. Actuator có thể đọc file thành `BuildProperties` và đưa lên `/actuator/info` khi được expose phù hợp. Hãy cân nhắc loại `build.time` khi ưu tiên **up-to-date và reproducibility**, đồng thời kiểm chứng **đúng artifact cuối cùng**, không chỉ file trong build directory.
