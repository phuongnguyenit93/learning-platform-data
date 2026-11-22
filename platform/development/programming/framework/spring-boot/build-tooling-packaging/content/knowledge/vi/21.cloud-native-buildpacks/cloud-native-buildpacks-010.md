# Quản lý build cache, launch cache và thao tác làm sạch cache trong Cloud Native Buildpacks

## 1. Vấn đề và mục tiêu

Khi dùng **Cloud Native Buildpacks (CNB)** để tạo OCI image cho Spring Boot, một lần build có thể cần tải Java runtime, phân tích executable JAR, chuẩn bị các layers của buildpacks và xuất image. **Cache** giúp những lần build sau tận dụng nội dung đã tạo, giảm download hoặc thao tác lặp, nhưng cũng có thể làm debug khó nếu developer nghĩ đã dùng dữ liệu mới mà hệ thống thực ra tái sử dụng layer cũ.

Có ba khái niệm quan trọng trong Spring Boot `spring-boot:build-image`/`bootBuildImage`:

- **`buildCache`**: nơi giữ các **buildpack-contributed cached layers** phục vụ việc xây dựng image ở các lần sau; thường có dữ liệu cần trong bước build hoặc download.
- **`launchCache`**: nơi phục vụ việc tái sử dụng **launch-related layers** trong quá trình tạo image; liên quan các layers đưa vào image để chạy ứng dụng, không phải cache business ở thời điểm HTTP request.
- **`buildWorkspace`**: vùng làm việc tạm mà builder/buildpacks sử dụng khi build. Nó **không phải** alias của build cache hoặc launch cache và có lifecycle riêng.

Spring Boot Maven/Gradle plugins 3.3 mặc định tạo những vùng này qua **Docker named volumes**, với tên suy ra từ **tên image đầu ra**. Khi tên/tag image đổi thường xuyên, các volumes mặc định có thể thay theo, khiến cache không được tái sử dụng giữa các build mong đợi. Plugin cho phép gán tên cache volume ổn định. <https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html> và <https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html> mô tả các option liên quan.

**Đề bài hướng tới bốn kỹ năng thực tế:**

1. Giải thích build cache, launch cache và build workspace theo đúng vòng đời CNB.
2. Cấu hình cache rõ ràng trong Spring Boot Maven Plugin hoặc Gradle `bootBuildImage`.
3. Phân biệt **warm build**, **cold-ish build có `cleanCache`** và **xóa volume thủ công có kiểm soát**.
4. Lập thí nghiệm đo được cache hit/miss, điều tra tình huống cache không được dùng, mà không xóa nhầm dữ liệu của người khác.

Bài dùng **Spring Boot 3.3.13, Java 17**, Docker daemon tương thích và Maven/Gradle Wrapper. Đây là bộ phiên bản minh họa, không phải khẳng định phiên bản mới nhất. Buildpacks/builder image có thể thay theo thời gian; phải dùng builder được tổ chức duyệt và kiểm tra tài liệu đúng phiên bản plugin/runtime. **Không có lệnh nào trong ví dụ được khẳng định đã thực thi trên máy người học.**

## 2. Mô hình Cloud Native Buildpacks: từ ứng dụng đến image

CNB tạo ứng dụng container image dựa trên **builder image**, **buildpacks**, **lifecycle** và **run image**:

~~~text
Spring Boot project
   |
   | Maven package + spring-boot:build-image
   | hoặc Gradle bootJar + bootBuildImage
   v
Executable JAR/WAR hoặc build input được plugin cung cấp
   |
   v
CNB Builder Image
   +-- buildpack group/order: detect
   +-- lifecycle phases: analyze, detect, restore, build, export
   +-- workspace: files tạm trong quá trình build
   +-- cache: nội dung cần tái sử dụng
   |
   +--> buildCache  (nhóm buildpack layers có thể phục hồi cho build)
   +--> launchCache (nhóm launch-related layers có thể tái sử dụng)
   |
   v
OCI application image
   +-- run image/base layers
   +-- buildpack-contributed launch layers
   +-- application layer(s)
   +-- CNB metadata, process/launch configuration
~~~

**Phân biệt builder và run image:**

- **Builder image** chứa môi trường và buildpacks cần cho **quy trình tạo image**, thường lớn hơn run image.
- **Run image** chứa nền tảng tối thiểu cần cho ứng dụng chạy. Container ở production chạy trên run image và launch layers; không mang toàn bộ môi trường builder.
- **Application image** là đầu ra; nó không “chạy từ cache volume” sau khi phát hành. Cache volumes hỗ trợ **lần build tiếp theo**, không phải nơi lưu trạng thái nghiệp vụ của container đang chạy.

**Lifecycle sơ lược:**

1. **Analyze** kiểm tra thông tin image/layer trước đó để quyết định phần có thể tái sử dụng.
2. **Detect** xác định buildpacks phù hợp với ứng dụng theo builder order.
3. **Restore** phục hồi những cached layers phù hợp.
4. **Build** thực thi buildpacks, có thể lấy lại layers hoặc tải/biên dịch mới.
5. **Export** ghép launch layers, app contents và run image để tạo OCI image, đồng thời cập nhật cache/metadata theo quy tắc platform.

Thứ tự/thành phần từng lifecycle implementation và platform API có thể phát triển; đây là mô hình giải thích, không phải yêu cầu phải chạy từng executable phase thủ công khi dùng Spring Boot plugin.

### 2.1. “Cache” và “layer” ở đâu?

CNB buildpack có thể tạo một layer và đánh dấu các đặc tính của nó theo spec:

~~~toml
[types]
build = true
launch = true
cache = true

[metadata]
example_version = "1.0"
~~~

Đây là **đoạn TOML minh họa cách buildpack author đánh dấu layer**, không phải file cấu hình cần dán vào ứng dụng Spring Boot. Các cờ có ý nghĩa:

- `build = true`: layer có thể được cung cấp cho các buildpacks kế tiếp trong build phase.
- `launch = true`: layer đóng góp vào application image để phục vụ runtime.
- `cache = true`: layer được phép tham gia build cache để có thể phục hồi ở lần build sau.
- `metadata`: buildpack có thể dùng để so version/kiểm tra cache còn phù hợp.

Ba boolean **không phải một cờ duy nhất**. Chẳng hạn `cache=true, build=true, launch=false` có thể mô tả một toolchain chỉ dùng khi build; `launch=true, cache=false` cũng có thể được tái sử dụng từ image đã xuất bản nếu platform/buildpack cho phép. Vì vậy **xóa build cache không bảo đảm tất cả launch layers đều bị rebuild từ đầu**: image/layer trước đó và metadata còn là yếu tố liên quan. Xem tài liệu chính thức về các chiến lược CNB caching ở cuối bài.

### 2.2. Những loại cache khác cần tách riêng

| Thành phần | Mục đích | `cleanCache` của Boot build-image có xóa nó không? |
| --- | --- | --- |
| CNB `buildCache` | Phục hồi cached layers khi tạo image. | Tác động tới cache do platform/plugin quản lý cho build tương ứng. |
| CNB `launchCache` | Hỗ trợ tái sử dụng launch layers trong export/ảnh trước đó. | Chính sách clean của build tương ứng cần xem logs; không suy mọi image/volume trên daemon bị xóa. |
| CNB `buildWorkspace` | Tập file tạm phục vụ build. | Không đồng nhất với một cache volume; có thể tồn tại riêng. |
| Maven `~/.m2/repository` | Cache artifacts của Maven trước khi tạo executable JAR. | **Không** bị xóa bằng CNB cleanCache. |
| Gradle `~/.gradle/caches` | Cache resolution/build Gradle trước CNB task. | **Không** bị xóa bằng CNB cleanCache. |
| Docker image layers và image store | Chứa image/base layers đã tạo/pull. | Không biến mất hoàn toàn chỉ vì clean CNB cache. |
| Docker BuildKit build cache | Cache khi chạy `docker build`/Dockerfile. | **Khác** cache của CNB plugin. |
| Redis, HTTP cache, database, local app temp files | Phục vụ **runtime ứng dụng**. | **Không liên quan** tới CNB build cache/launch cache. |

**Quy tắc:** khi một build chậm, trước hết hỏi “đang chậm ở Maven/Gradle dependency resolution, CNB buildpacks, Docker pull, hay image push?” rồi mới chọn loại cache cần điều tra.

## 3. Build cache và launch cache khác nhau thế nào?

### 3.1. Build cache

**Build cache** giữ các nội dung buildpack muốn có sẵn trở lại trong quá trình build lần sau. Tùy buildpack, ví dụ có thể là download cache, công cụ build-time hoặc runtime artifact mà buildpack đánh dấu `cache=true`. Layer chỉ được tái sử dụng khi metadata/input policy cho rằng nó còn hợp lệ.

Một cách đọc logs thường thấy:

~~~text
===> RESTORING
... Restoring data for buildpack layers ...
===> BUILDING
... Reusing cached dependency ...
~~~

Đây là **mẫu diễn giải**, không phải stdout đảm bảo của Paketo/Boot phiên bản cụ thể. Một build vẫn có thể thành công dù restore không tìm được dữ liệu: lúc đó buildpack tạo/download lại layer. Cache làm tối ưu performance, **không phải nguồn chân lý cho artifact version**.

**Điều không thể suy:** cache volume tồn tại không chứng minh buildpack đã dùng nó; có thể cache chứa version cũ hoặc buildpack quyết định invalidate.

### 3.2. Launch cache

**Launch cache** liên quan các layers phục vụ **image launching** và khả năng tái sử dụng chúng trong quá trình build/export tiếp theo. Một số launch layers có thể được tái sử dụng từ **previous application image hoặc remote registry** mà không cần download toàn bộ về host, tùy platform và buildpack metadata.

Trong Spring Boot plugin, `launchCache` là một vị trí cấu hình riêng với `buildCache`. **Không gọi nó là “cache của app sau khi container chạy”**:

- Nó không lưu HTTP session, query result, Redis values hoặc database records.
- Xóa launch cache không “reset state” của một service đang chạy.
- Image đã tạo là artifact độc lập; xóa cache không có nghĩa image đã bị xóa.
- Muốn hiểu launch layer reuse phải xem **analyze/export phase**, previous image và registry/local image availability, không chỉ kích thước volume.

### 3.3. Build workspace

`buildWorkspace` là vùng builder/buildpacks thao tác với files khi build. Nó thường được Spring Boot plugin tạo thành một Docker named volume riêng (theo image name nếu không cấu hình). **Tồn tại workspace không chứng minh cache hit** và việc xóa nó không tương đương với “clean build cache”.

Tránh mount dữ liệu quan trọng của tổ chức vào workspace; builder/buildpacks cần ghi/tạm giữ nội dung. Nếu cấu hình bind mount, phải hiểu permissions và vị trí trên Docker daemon host, nhất là daemon chạy trên máy khác với máy gọi Maven/Gradle.

### 3.4. Bốn câu hỏi để chọn hành động

| Triệu chứng | Câu hỏi nên hỏi | Hành động đầu tiên |
| --- | --- | --- |
| Lần build thứ hai vẫn download Java runtime. | Cache volume có cùng tên và buildpack có đánh dấu layer là reusable? | So image names, volume names, builder/buildpack versions và logs. |
| Image không phản ánh code Java mới. | Executable JAR đầu vào đã chứa bytecode mới chưa? | Kiểm tra Maven/Gradle package, chạy JAR riêng; chưa nên xóa volume. |
| Nâng dependency nhưng logs vẫn báo reuse một số layers. | Layer nào thay, layer nào đúng ra được phép reuse? | Xem resolved dependency graph, SBOM, image labels/layers; reuse không nhất thiết là sai. |
| Muốn đo cold build không có CNB cached layers cũ. | Có thể clean đúng cache cho một image/build cụ thể không? | Dùng `cleanCache` hoặc `pack --clear-cache` có chủ đích; ghi logs. |

## 4. Lưu ở đâu? Image name chi phối cache identity

Theo tài liệu Spring Boot 3.3, `buildCache`, `launchCache` và `buildWorkspace` mặc định được tạo trong **Docker daemon** dưới dạng named volumes, có tên dẫn xuất từ **tên đầy đủ của target image**.

Ví dụ nếu project mặc định build:

~~~text
docker.io/library/cnb-cache-demo:0.0.1-SNAPSHOT
~~~

và CI đổi tag theo commit:

~~~text
docker.io/library/cnb-cache-demo:commit-a1b2
docker.io/library/cnb-cache-demo:commit-c3d4
~~~

thì cache identity mặc định có thể thay đổi giữa các lần build. Hậu quả: logs không thấy cached layers kỳ vọng, build time tăng và có thêm volumes trên daemon, dù application/dependencies gần như không đổi.

**Hai cách giữ cache identity ổn định:**

1. **Dùng cố định một image name/tag cho local build** (ví dụ `cnb-cache-demo:local`), sau đó tag immutable digest/version khác nếu cần — chú ý không làm overwrite tag production.
2. **Cấu hình tên `buildCache` và `launchCache` rõ ràng**, độc lập với target image tag, để nhiều lần build cùng project sử dụng lại cache mong muốn.

Chỉ chia sẻ cache giữa những build thực sự tương thích: cùng trusted builder/buildpack stack, architecture/platform và policy. **Không dùng chung cache volume cho nhiều project không liên quan hoặc nhiều tenant không tin cậy** chỉ để tiết kiệm dung lượng.

### 4.1. Không đoán tên Docker volume mặc định

Tên mặc định là **implementation detail có thể khác theo plugin/version/image name**. Không lấy chuỗi mà bạn tự suy từ image name rồi `docker volume rm`. Để quản lý vòng đời chính xác, **đặt tên volume tường minh trong config** và kiểm tra nó bằng `docker volume inspect`.

## 5. Ví dụ Java 17 Spring Boot có thể chạy

Cùng một mã Java sẽ được dùng với **Maven hoặc Gradle**, chọn một build tool.

Cấu trúc cơ bản:

~~~text
cnb-cache-demo/
├── pom.xml                               # nếu chọn Maven
├── settings.gradle                       # nếu chọn Gradle
├── build.gradle                          # nếu chọn Gradle
├── src/main/java/com/example/cnb/CacheDemoApplication.java
├── src/test/java/com/example/cnb/CacheDemoApplicationTest.java
└── (Maven Wrapper hoặc Gradle Wrapper do repository cung cấp)
~~~

### 5.1. Main application

`src/main/java/com/example/cnb/CacheDemoApplication.java`:

~~~java
package com.example.cnb;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @GetMapping("/cache")
    public String cache() {
        return "cache-" + StringUtils.capitalize("warm");
    }
}
~~~

**Dự kiến:** `GET /cache` trả body chính xác `cache-Warm`. Java 17 hỗ trợ mọi Java syntax ở đây. `StringUtils.capitalize` thuộc `commons-lang3`, tạo code path thực sự dùng một external runtime dependency. Đây là **endpoint minh họa**, không phải chức năng quản lý cache của CNB; không được nhầm URL `/cache` với lệnh xóa cache.

### 5.2. JUnit + MockMvc test

`src/test/java/com/example/cnb/CacheDemoApplicationTest.java`:

~~~java
package com.example.cnb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void cacheEndpointReturnsExpectedText() throws Exception {
        mvc.perform(get("/cache"))
           .andExpect(status().isOk())
           .andExpect(content().string("cache-Warm"));
    }
}
~~~

Test chứng minh Java/Spring context/Commons Lang hoạt động trên **test classpath**, nhưng không kiểm tra CNB image cache hay Docker runtime. Phải kiểm tra thêm image đã build. Khi đổi code trong bài A/B/C, cập nhật assertion tương ứng.

## 6. Cách 1: Maven `spring-boot:build-image` và cache volumes

### 6.1. `pom.xml` chạy được

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
    <artifactId>cnb-cache-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                        <!-- Tag ổn định cho thí nghiệm local -->
                        <name>cnb-cache-demo:local</name>
                        <!-- Cache build và launch có tên riêng, dễ quản lý -->
                        <buildCache>
                            <volume>
                                <name>cnb-demo-build-cache</name>
                            </volume>
                        </buildCache>
                        <launchCache>
                            <volume>
                                <name>cnb-demo-launch-cache</name>
                            </volume>
                        </launchCache>
                        <verboseLogging>true</verboseLogging>
                        <cleanCache>false</cleanCache>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Cấu hình đặt ở **Spring Boot Maven Plugin**, không phải `maven-jar-plugin` hoặc `maven-dependency-plugin`:

- `image.name` đặt tên image ổn định cho local experiment.
- `buildCache.volume.name` chỉ định named volume CNB build cache.
- `launchCache.volume.name` chỉ định named volume CNB launch cache.
- `verboseLogging` bật log chi tiết phục vụ QA.
- `cleanCache=false` để mặc định thử warm cache. Khi cần đo clean run, dùng **command-line override** thay vì sửa POM lâu dài.
- Không cấu hình `buildWorkspace` ở demo nên plugin tự chọn workspace; nó **không được xóa thủ công** trong bài tập làm sạch hai cache cụ thể.

Maven `spring-boot:build-image` **fork lifecycle để đảm bảo package đã chạy**; nếu bind goal vào Maven lifecycle, dùng `build-image-no-fork` theo tài liệu thay vì vô ý gọi fork lặp. Bài này gọi command-line goal trực tiếp.

### 6.2. Lệnh build bình thường và clean-cache

Từ root có Maven Wrapper, Docker daemon đang chạy, có quyền tải builder/run images:

~~~bash
# Kiểm tra toolchain, test và artifact trước
./mvnw -version
docker version
./mvnw clean verify

# CNB build thông thường: không cố tình dọn cache
./mvnw spring-boot:build-image

# Cùng code/image/config, thực hiện thêm lần nữa để quan sát warm cache
./mvnw spring-boot:build-image

# Chỉ khi muốn kiểm tra cache-clean có chủ đích:
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.cleanCache=true
~~~

`-Dspring-boot.build-image.cleanCache=true` là property documented trong Spring Boot Maven Plugin 3.3. Không để flag này trên **mọi** command CI nếu muốn tận dụng cache.

**Đừng nhầm `./mvnw clean` với CNB cache cleaning**: Maven clean chỉ dọn build output như `target/`, không xóa Docker named volumes do CNB quản lý. Tương tự, plugin cache không phải local Maven repository.

### 6.3. Tại sao không hardcode đường dẫn Docker volume trên host?

Docker volumes thuộc về **Docker daemon**; với Docker Desktop hoặc daemon chạy từ xa, đường dẫn vật lý không nhất thiết là một thư mục dưới shell người dùng. Dùng Docker CLI inspect thay vì cố vào `/var/lib/docker/volumes` hoặc dùng `rm -rf` trên host.

## 7. Cách 2: Gradle `bootBuildImage` và cache volumes

Nếu dùng Gradle, giữ cùng source/test, thay POM bằng hai file sau.

`settings.gradle`:

~~~groovy
rootProject.name = 'cnb-cache-demo'
~~~

`build.gradle`:

~~~groovy
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    // Giữ image name ổn định để so các lần build.
    imageName.set('cnb-cache-demo:local')

    // Cache volumes do CNB/Docker daemon quản lý.
    buildCache {
        volume {
            name = 'cnb-demo-build-cache'
        }
    }
    launchCache {
        volume {
            name = 'cnb-demo-launch-cache'
        }
    }

    cleanCache.set(false)
    verboseLogging.set(true)
}
~~~

Giải thích:

- Spring Boot Gradle Plugin tạo task `bootBuildImage` khi có Java/War plugin và sử dụng Cloud Native Buildpacks.
- `imageName` là tên image đầu ra. Trong dự án thực có thể đặt tag version/commit riêng và giữ cache volume name ổn định.
- `buildCache` và `launchCache` là **hai CacheSpec riêng**; `volume.name` là tên Docker volume được sử dụng để lưu/truyền cache tương ứng.
- `cleanCache` là `Property<Boolean>` của task, nên có thể dùng `set(false)` trong Groovy DSL. Không copy nguyên DSL này vào Maven POM/Kotlin DSL.
- `verboseLogging` giúp phân tích CNB lifecycle/logs, không thay tính đúng đắn của sản phẩm.

### 7.1. Lệnh Gradle

~~~bash
./gradlew --version
docker version

# Java compile/test/JAR
./gradlew clean build

# CNB image build, giữ cache
./gradlew bootBuildImage

# Chạy lại cùng code và config, so logs
./gradlew bootBuildImage

# Chỉ khi muốn làm sạch cache trước một lần build:
./gradlew bootBuildImage --cleanCache
~~~

`--cleanCache` là task option được tài liệu Spring Boot Gradle Plugin 3.3 liệt kê. Bạn cũng có thể tạm thay `cleanCache.set(true)` trong build script, nhưng cần **khôi phục false** khi kết thúc thử nghiệm để không vô tình tắt warm cache.

**`./gradlew clean` không xóa Docker named volumes.** Nó dọn output Gradle project như `build/`, khác `cleanCache` của CNB image build. Gradle build cache (`~/.gradle/caches` hoặc remote Gradle build cache) cũng không đồng nghĩa CNB build cache.

### 7.2. Maven và Gradle dùng cùng volume names có an toàn không?

Trong **bài học**, các cấu hình Maven và Gradle có cùng tên volume để dễ so sánh, nhưng chỉ chọn **một tool** chạy mỗi lần. Trong tổ chức, không nên để hai pipeline không tương thích vô tình dùng chung cache cùng tên. Nếu muốn chạy song song Maven và Gradle hoặc hai architectures, hãy thêm prefix theo tool/project/platform, ví dụ `cnb-maven-demo-build` và `cnb-gradle-demo-build`.

**Quy tắc:** cache identity phải đủ ổn định để reuse nhưng đủ biệt lập để không lẫn các buildpacks/tenants/toolchains không tương thích.

## 8. Thao tác quan sát trước khi làm sạch

### 8.1. Kiểm tra Docker daemon

~~~bash
docker version
docker info
~~~

Nếu client không kết nối được server, Spring Boot image build sẽ fail trước hoặc trong lúc tạo builder container. Không nhầm lỗi **daemon unavailable** với lỗi cache. Khi Docker context trỏ daemon remote, mọi named volume nằm **trên daemon đó**, không nhất thiết là máy chạy Maven/Gradle.

### 8.2. Kiểm tra cache volumes đã đặt tên

Các lệnh sau **chỉ đọc metadata**:

~~~bash
docker volume ls
docker volume inspect cnb-demo-build-cache
docker volume inspect cnb-demo-launch-cache
~~~

Nếu volume chưa tồn tại trước lần build đầu, `inspect` có thể trả nonzero; đây không tự là lỗi. Sau một lần image build, việc có volume hay không còn phụ thuộc platform/version/config và build đã tiến đủ xa chưa. Xem `docker volume ls` và logs để kết luận.

**Đừng suy từ một tên chứa chữ `cache`:** một Docker daemon có thể chứa volumes của nhiều dự án. Chỉ xóa volume khi đã đối chiếu **tên chính xác**, mục đích sử dụng, người sở hữu và mức độ ảnh hưởng.

### 8.3. Quan sát image vừa tạo

~~~bash
docker image ls
docker image inspect cnb-cache-demo:local
~~~

`docker image inspect` giúp xác định image ID, labels, digest metadata và platform; nó **không** chứng minh cache volume nào đã hit trong lifecycle. Đọc **logs analyze/restore/build/export** mới biết layer nào được reuse hoặc rebuild theo buildpack.

### 8.4. Kiểm tra hành vi container

Sau khi image tạo thành công, chạy:

~~~bash
docker run --rm -p 18085:8080 cnb-cache-demo:local
~~~

Terminal khác:

~~~bash
curl -i http://localhost:18085/cache
~~~

**Kỳ vọng:** HTTP 200, body `cache-Warm`. Đây là smoke test của **image**, không phải cache hit test. Nếu image chạy đúng nhưng build lần hai không reuse cache, vấn đề là **performance/caching** chứ không nhất thiết là ứng dụng sai.

Dừng server qua Ctrl+C ở terminal chạy container. Trong CI, quản lý background container bằng ID, timeout và cleanup; tránh để ứng dụng chạy foreground vô thời hạn rồi tưởng pipeline sẽ tự hoàn thành.

## 9. Thí nghiệm A/B/C: so warm cache, thay code và thay dependency

Để kiểm chứng cache behavior, cần thay **một biến mỗi lần** và ghi logs cùng thời gian. Đề xuất bốn lượt cơ bản:

| Lượt | Thay đổi đầu vào | Clean cache? | Câu hỏi |
| --- | --- | --- | --- |
| A1 | Baseline source/dependency, image và volume names cố định. | Có thể bắt đầu bằng clean có chủ đích. | Mất thời gian tạo/download các layers nào? |
| A2 | Không đổi code/dependency/builder. | Không. | Buildpacks có reuse cache hoặc image layers không? |
| B | Chỉ đổi một literal trong Java code và test assertion. | Không. | Những buildpack layers còn phù hợp có được reuse không? |
| C | Quay lại code A, chỉ đổi Commons Lang release version đã duyệt. | Không. | Dependency layers nào bị thay/invalidate, runtime có còn đúng không? |

### 9.1. Lượt A1: cache-clean baseline

Maven:

~~~bash
./mvnw clean verify
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.cleanCache=true
~~~

Hoặc Gradle:

~~~bash
./gradlew clean build
./gradlew bootBuildImage --cleanCache
~~~

**Không khẳng định “cold build 100%” chỉ nhờ `cleanCache`:** daemon có thể vẫn giữ builder/run images; Maven/Gradle caches vẫn warm; previous image/registry layers có thể còn; buildpack có thể áp dụng cơ chế reuse khác. Gọi đây là **clean-CNB-cache baseline** và ghi rõ môi trường.

Lưu thông tin bằng chứng theo policy: command, image name, volume names, builder/run image references và digests, JDK, plugin version, selected dependency versions, container logs, thời gian đo từ CI. Nếu môi trường cần log file, có thể redirect stdout/stderr bằng shell phù hợp; không dùng log của một build khác để gán kết quả.

### 9.2. Lượt A2: warm build

Lặp lại đúng cùng command **không có clean flag**:

~~~bash
# Maven hoặc Gradle, chọn một:
./mvnw spring-boot:build-image
# ./gradlew bootBuildImage
~~~

Trong logs, quan sát:
- Có phase **RESTORING** / **Reusing** / **Cached** không?
- Buildpack nào sử dụng cached layer và buildpack nào vẫn chạy lại?
- Có pull builder/run image từ registry do pull policy mặc định không?
- Cùng cache volume names, same daemon/context và same image ref không?
- Kết quả runtime vẫn HTTP 200/`cache-Warm` không?

**Không suy cache hit từ thời gian nhanh hơn đơn thuần**: mạng, Docker image store, Maven local repo, Gradle build cache và máy host khác cũng ảnh hưởng duration. Đọc log/layer metadata cùng kết quả thời gian.

### 9.3. Lượt B: thay code-only

Trong `CacheDemoApplication.java`, thay:

~~~java
return "cache-" + StringUtils.capitalize("warm");
~~~

thành:

~~~java
return "code2-" + StringUtils.capitalize("warm");
~~~

Đổi expected test text thành `code2-Warm` để giữ test hợp lệ. Không sửa POM/Gradle dependencies, cache names, builder/run image hoặc Docker context. Build và chạy image bình thường:

~~~bash
# Maven:
./mvnw clean verify
./mvnw spring-boot:build-image

# Hoặc Gradle:
# ./gradlew clean build
# ./gradlew bootBuildImage
~~~

Chạy lại container với image mới, kỳ vọng body `code2-Warm`. Logs có thể cho thấy nhiều dependency/buildpack layers vẫn được reuse dù application layer thay. **Không ép rằng buildpacks nhất định in một log message giống nhau ở mọi phiên bản**; so dữ liệu thực.

### 9.4. Lượt C: dependency-only

**Khôi phục code và test về A** (`cache-Warm`) trước. Nâng **chỉ** version Commons Lang từ `3.14.0` sang `3.15.0` hoặc release version thực sự được duyệt và resolve:

Maven POM fragment:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.15.0</version>
</dependency>
~~~

Gradle fragment:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.15.0'
~~~

Kiểm tra **selected version** chứ không chỉ declaration:

~~~bash
# Maven
./mvnw dependency:tree

# Gradle (chọn nếu dùng Gradle)
./gradlew dependencyInsight --configuration runtimeClasspath \
  --dependency commons-lang3
~~~

Build image bình thường, so logs với A2, chạy image và xác nhận `cache-Warm`. Một số buildpack layers có thể invalidated, một số khác reused; không gán mặc định cùng một pattern cho mọi builder. Kiểm tra nội dung runtime artifact / SBOM và image metadata khi cần để giải thích thay đổi.

### 9.5. Bảng mẫu ghi kết quả (điền bằng số liệu thật)

| Lần | Input commit/dependency | Clean cache | Volume names | Layers reused/rebuilt (trích log) | Thời gian thực tế | HTTP smoke |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Baseline | Có | Build/launch đã đặt tên | Ghi bằng chứng | Ghi đo đạc | 200 / `cache-Warm` |
| A2 | Giống A1 | Không | Giống A1 | Ghi bằng chứng | Ghi đo đạc | 200 / `cache-Warm` |
| B | Code-only | Không | Giống A1 | Ghi bằng chứng | Ghi đo đạc | 200 / `code2-Warm` |
| C | Dependency-only | Không | Giống A1 | Ghi bằng chứng | Ghi đo đạc | 200 / `cache-Warm` |

Không điền số giây hoặc tỷ lệ cache hit “ước lượng” khi chưa chạy. Trước khi so duration, bảo đảm toolchain, daemon, network và source inputs tương đương.

## 10. Làm sạch cache đúng phạm vi: bốn cách

### 10.1. Cách ưu tiên cho Spring Boot Maven

Dùng **chỉ một lần theo chủ đích**:

~~~bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.cleanCache=true
~~~

Plugin sẽ yêu cầu làm sạch cache **liên quan tới quá trình build image hiện tại** trước khi xây image. Đây **không phải** lệnh xóa tất cả Docker volumes/Gradle caches/Maven repository trên máy. Sau lần này, quay về command bình thường để warm cache có cơ hội hoạt động.

### 10.2. Cách ưu tiên cho Spring Boot Gradle

~~~bash
./gradlew bootBuildImage --cleanCache
~~~

Tương tự, đây là option của **BootBuildImage task**, không phải `./gradlew clean`, không phải `docker system prune`. Kiểm tra logs xem cache handling đã diễn ra đúng và image sau đó vẫn chạy.

### 10.3. Với `pack` CLI — `--clear-cache`

Nếu chọn **`pack` CLI trực tiếp**, đây là một workflow độc lập với Spring Boot Maven/Gradle Plugin. Kiểm tra phiên bản thật:

~~~bash
pack version
pack build --help
pack builder suggest
~~~

Ví dụ dùng builder được tài liệu của phiên bản tương ứng hỗ trợ (thay builder khi policy yêu cầu):

~~~bash
# Từ project root (có Docker daemon và builder phù hợp)
pack build cnb-cache-demo:pack \
  --path . \
  --builder paketobuildpacks/builder-jammy-base:latest

# Chủ động làm sạch cache liên quan image trước lần pack build này:
pack build cnb-cache-demo:pack \
  --path . \
  --builder paketobuildpacks/builder-jammy-base:latest \
  --clear-cache
~~~

`--clear-cache` là option chính thức của `pack build`, làm sạch **cache gắn với image/build đó** trước khi build. **Không** mặc định coi `pack build` hoàn toàn tương đương `spring-boot:build-image`: đầu vào, detection, buildpacks, cache naming và build flags có thể khác. Đừng so thời gian trực tiếp giữa `pack` và Boot plugin rồi gán khác biệt chỉ do cache.

Builder trong ví dụ là một tham chiếu minh họa có tag `latest`; để reproducibility trong dự án thật, pin một builder version/digest được phê duyệt. Nếu image builder không còn ở repository hiện tại, thay bằng builder tương thích được tổ chức duyệt; không tắt verification/TLS để tải bằng mọi giá.

### 10.4. Xóa named volumes thủ công — chỉ sau khi kiểm tra ownership

**Chỉ dùng khi phải dọn local test daemon và đã xác nhận chính xác hai Docker volume do bài demo quản lý.** Không tự động thực hiện trên shared Docker host hoặc CI daemon của nhiều team.

Bước 1 — đọc metadata:

~~~bash
docker volume ls
docker volume inspect cnb-demo-build-cache
docker volume inspect cnb-demo-launch-cache
~~~

Bước 2 — xác nhận:

- Hai tên **trùng hoàn toàn** với cấu hình POM/Gradle của **đúng project**.
- Không có job/build/container khác đang dùng chúng.
- Không chứa dữ liệu không thể tái tạo; CI/ops đã đồng ý xóa khi là shared environment.
- Không nhầm `buildWorkspace` với cache volume.
- Đang kết nối **đúng Docker context/daemon** mà project đã build.

Bước 3 — thao tác thực sự làm mất cache (chỉ sau xác nhận):

~~~bash
docker volume rm cnb-demo-build-cache cnb-demo-launch-cache
~~~

Đây là **lệnh có tác động phá hủy** hai Docker volumes có tên đã chỉ định. Nếu volume đang được container sử dụng, Docker có thể từ chối. **Không thêm `-f` hoặc kill container tùy tiện để ép xóa**, đặc biệt trên daemon shared.

Bước 4 — verify có chủ đích:

~~~bash
docker volume ls
./mvnw spring-boot:build-image
# Hoặc nếu dùng Gradle: ./gradlew bootBuildImage
~~~

Sau khi build, volumes có thể được tạo lại; điều này là bình thường. Không tuyên bố “volume không bao giờ xuất hiện nữa” khi platform vẫn cần lưu cache cho các build về sau.

### 10.5. Tuyệt đối phân biệt với những lệnh rộng hơn

| Lệnh/hành động | Tác động | Có nên dùng chỉ để clean CNB cache bài này? |
| --- | --- | --- |
| Maven `clean` | Xóa build output Maven như `target`. | Không thay CNB cache clean. |
| Gradle `clean` | Xóa build output như `build`. | Không thay CNB cache clean. |
| `docker image rm <image>` | Xóa local image tag/image khi không bị dùng. | Không bảo đảm xóa cache volumes. |
| `docker builder prune` | Làm sạch **Docker BuildKit build cache**, không phải chính xác hai CNB named volumes. | **Không**, trừ khi đang xử lý BuildKit riêng. |
| `docker volume prune` | Có thể xóa **nhiều volumes không được tham chiếu** của dự án khác. | **Không** trên shared host. |
| `docker system prune --volumes` | Có tác động rộng tới objects/caches/volumes không dùng. | **Không** cho một bài kiểm chứng cache. |
| `rm -rf ~/.m2`/`~/.gradle/caches` | Xóa cache dependency/build tool, không phải CNB cache. | Không; tác động lớn và có thể làm builds tải lại rất nhiều. |

**Nguyên tắc an toàn:** ưu tiên `cleanCache`/`--clear-cache` trong phạm vi **một image build**, hoặc xóa **đúng named volume đã sở hữu** khi thật sự cần. Không dùng lệnh prune tổng quát để “xử lý nhanh” một triệu chứng cache miss đơn lẻ.

## 11. Cấu hình cache ổn định khi image tag thay đổi theo CI

Một pipeline thường sinh image theo commit:

~~~text
cnb-cache-demo:abc123
cnb-cache-demo:def456
cnb-cache-demo:ghi789
~~~

Nếu plugin dùng tên volume mặc định **phụ thuộc full image name**, mỗi tag có thể có bộ volumes riêng, làm giảm khả năng tận dụng cache giữa các commit. Cách giải quyết là **gắn tên cache volume vào project/toolchain**, không gắn vào tag biến động.

### 11.1. Maven

Đoạn trong `spring-boot-maven-plugin`:

~~~xml
<image>
    <!-- Có thể thay image name/tag theo pipeline -->
    <name>registry.example.invalid/team/cnb-cache-demo:commit-id</name>
    <!-- Giữ volume cache ổn định theo project -->
    <buildCache>
        <volume><name>team-cnb-demo-build</name></volume>
    </buildCache>
    <launchCache>
        <volume><name>team-cnb-demo-launch</name></volume>
    </launchCache>
</image>
~~~

Đây là **mảnh configuration**, không phải URL registry có thật và không phải POM độc lập. `registry.example.invalid` là ký hiệu minh họa, không push. Ở CI thực tế, gán image name từ hệ thống release/versioning, dùng registry approved và credentials/permission phù hợp. Nếu nhiều CI runners dùng daemon riêng, **cùng tên volume không làm cache tự xuất hiện trên máy khác**.

### 11.2. Gradle

Mảnh Groovy DSL:

~~~groovy
tasks.named('bootBuildImage') {
    // Thay imageName theo version/commit thật của CI.
    imageName.set('cnb-cache-demo:ci-demo')

    buildCache {
        volume { name = 'team-cnb-demo-build' }
    }
    launchCache {
        volume { name = 'team-cnb-demo-launch' }
    }
}
~~~

Tương tự, volume names có thể ổn định khi image tag đổi. Cần tránh **race condition** khi hai jobs chạy song song cùng daemon và cùng cache: dùng cache namespace theo pipeline/platform hoặc cơ chế đồng bộ theo chính sách. Cache không phải mutable shared state an toàn mặc định cho bất kỳ số runner đồng thời nào.

### 11.3. Khi CI là ephemeral runner

Nếu mỗi build có Docker daemon/VM mới và không còn volumes giữa jobs, **local named-volume cache không tự tồn tại** dù tên bạn đặt giống nhau. Khi đó:

- Dùng runner/daemon persistent nếu policy cho phép.
- Cân nhắc remote image/cache strategy của CNB platform, chẳng hạn `pack --cache-image` hoặc registry-based cache theo hỗ trợ của CLI và quyền publish.
- Kiểm tra **registry reachability/authentication** và cache tenancy/security.
- Không tuyên bố chỉ thêm `buildCache.volume.name` là đủ cho CI runner hoàn toàn stateless.

`pack` còn hỗ trợ các dạng cache volume/bind/registry image tùy phiên bản và flags; nên đọc `pack build --help` của binary đang dùng. Remote cache có yêu cầu authentication, registry policy và quyền publish riêng; đây không phải tính năng tự động được bật trong Maven/Gradle snippet ở bài.

## 12. Vì sao cache vẫn không hit dù volumes tồn tại?

### 12.1. Buildpack quyết định tính hợp lệ bằng metadata

Một cache entry cũ không nhất thiết được dùng mãi. Buildpack có thể so Java version, buildpack version, dependency checksum, input build metadata, stack/run image compatibility hoặc một điều kiện riêng. Nếu metadata không khớp, nó tạo lại layer. Đây là **cache invalidation đúng**, không phải lỗi cần tìm cách ép bỏ qua.

### 12.2. Những nguyên nhân phổ biến

| Triệu chứng | Khả năng | Kiểm tra/hướng xử lý |
| --- | --- | --- |
| Build lần hai tải lại rất nhiều dependencies. | Tên image/cache volume đổi, daemon khác, cache bị clean hoặc builder version khác. | In image name và exact volume names, Docker context, logs restore/build. |
| Docker volume tồn tại nhưng không có Reusing log. | Buildpack invalidate cache, layer không đánh dấu cache hoặc metadata mới. | Xem builder/buildpack versions, runtime deps, buildpack logs. |
| Thay tag theo commit thì build như mới. | Tên cache mặc định suy từ image name có tag. | Đặt `buildCache`/`launchCache` names ổn định, nếu các builds tương thích. |
| Cache clean xong build vẫn nhanh. | Maven/Gradle caches, Docker builder/run images và previous image layers còn. | Phân biệt nguồn cache, không kết luận cleanCache vô hiệu. |
| `java -jar`/Docker app vẫn trả dữ liệu code cũ. | Package input không được rebuild, image tag cũ, container cũ, resource/config khác. | Kiểm tra executable JAR, image ID, container ID và code path; đừng xóa volumes đầu tiên. |
| Nâng Commons Lang mà buildpack reuse JRE layer. | JRE layer không phụ thuộc trực tiếp Commons Lang. | Đây có thể là cache reuse đúng; kiểm tra application/dependency layers đã đổi. |
| `docker volume inspect` báo not found. | Chưa tạo, tên sai, daemon context khác, build fail sớm. | Xem config, Docker context/logs, không đoán theo image name. |
| `bootBuildImage` task không tồn tại. | Thiếu Java/War plugin hoặc Spring Boot plugin. | Kiểm tra `plugins` và `./gradlew tasks --all`. |
| Maven `build-image` không tìm Docker daemon. | Docker chưa chạy, thiếu permission hoặc context/TLS config. | `docker version`/`docker context ls`; xem plugin Docker connection. |
| Build lỗi download builder/run image. | Network/registry/TLS/auth/pull policy. | Sửa truy cập đúng nguồn, không xoá cache hoặc tắt TLS. |
| Cache quá lớn, disk full. | Nhiều image tags tạo volumes, stale caches, builder images và image store. | Inventory có giới hạn, xóa đúng volume sở hữu, quản lý retention. |
| Chạy CI song song ghi cùng volume. | Cache namespace trùng giữa jobs, tương thích không đảm bảo. | Tách namespace theo tool/platform/runner hoặc đồng bộ. |
| Thay Java version mà cache bị vô hiệu. | JDK/runtime compatibility/metadata đổi. | Đây có thể là đúng; xác nhận builder/buildpack pin và Java toolchain. |
| Bật `cleanCache=true` cố định nên lần nào cũng cold-ish. | Cấu hình được giữ trong POM/Gradle. | Chỉ bật cho lần clean thử nghiệm, sau đó quay false. |
| Chạy `docker builder prune` nhưng CNB vẫn reuse. | BuildKit cache khác CNB volumes/previous image layers. | Không dùng BuildKit prune để xử lý CNB volumes. |
| `launchCache` bị hiểu như application Redis cache. | Nhầm build-time container artifact cache với business runtime state. | Đọc lifecycle/docs, kiểm tra image thay vì Redis endpoints. |
| Image mới chạy lỗi dù build reuse cache. | App/dependency/config mới không tương thích, cache không phải correctness test. | Smoke test image, SBOM, dependency graph và logs. |

### 12.3. Khung chẩn đoán theo tầng

1. **Build tool:** Maven/Gradle đã chạy compile/test/package đúng code chưa?
2. **Input:** source hash, dependency versions, application archive và selected builder image có đúng?
3. **Docker:** daemon/context nào được dùng; network/registry có ổn không?
4. **Cache configuration:** tên build/launch cache và workspace có đúng như config?
5. **CNB lifecycle logs:** analyze/restore/build/export đã reuse/invalidate những layers nào?
6. **Image result:** image tag, ID, labels, runtime stack và process được tạo đúng?
7. **Runtime:** container có thực sự chạy code mới và trả HTTP expected không?
8. **Security:** provenance, SBOM/CVEs/registry policy và không có secrets trong layers/cache?

Chỉ sau khi biết **tầng nào sai** mới quyết định dùng cleanCache, thay config hoặc sửa code/dependencies.

## 13. Phân biệt cache CNB với Spring Boot layered JAR

Một Spring Boot JAR có thể có `BOOT-INF/layers.idx`, thường phân thành:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Đây là **cách nhóm file bên trong executable archive**, không phải chính các Docker cache volumes tên `buildCache` và `launchCache`.

- `BOOT-INF/layers.idx` cho biết Java class/dependency JAR nào thuộc logical archive layer.
- CNB buildpacks/lifecycle quyết định cách tạo/tái sử dụng layers của **OCI image**, dựa trên application content và buildpack metadata.
- `buildCache`/`launchCache` là những cache resources cung cấp cho lifecycle của image build.
- Docker BuildKit cache là cơ chế khác khi dùng `docker build`/Dockerfile.

Vì vậy một thay đổi `BOOT-INF/classes` có thể làm application layer đổi, nhưng Java runtime/JRE layer của buildpack vẫn có thể reuse. Một thay đổi dependency có thể tác động OCI layer khác tùy buildpack strategy. **Không ép có quan hệ 1:1 giữa các tên ở `layers.idx` và Docker volume contents**.

Nếu bạn thật sự cần biết cache hiệu quả bao nhiêu, phải **đo build logs và image layers** từ đúng builder và cùng đầu vào, không chỉ grep `layers.idx`.

## 14. Hành vi “làm sạch cache” không đồng nghĩa build tái lập

Một fresh cache run có thể cho cùng kết quả image nếu inputs được kiểm soát; ngược lại một warm cache run vẫn có thể tạo image mới khi source/dependency thay đổi. Tính tái lập cần:

- Pin Java toolchain, Gradle/Maven Wrapper, plugin và builder/run image phiên bản/digest theo chính sách.
- Chốt dependency versions, tránh dynamic/changing dependencies khi build release.
- Quản lý dependency verification/provenance, trusted registry mirrors và buildpack selection.
- Giữ generated metadata không chứa timestamp/random IDs không cần thiết; chú ý build image `createdDate`.
- Không dùng ``latest`` image tags làm căn cứ bit-for-bit reproducibility nếu không biết digest thực.
- Kiểm tra binary behavior và image content/SBOM; build nhanh không phải đồng nghĩa build đúng.
- Dùng clean cache **chỉ khi cần chẩn đoán**, không biến nó thành bước CI mặc định khiến build tốn network/storage vô ích.

Spring Boot 3.3 có `createdDate` với default cố định để hỗ trợ reproducibility; nếu người dùng đặt `now`, image metadata thay mỗi lần build và digest có thể đổi dù ứng dụng code không đổi. Đây là khác biệt **image metadata**, không phải bằng chứng cache sai.

### 14.1. Nên dùng cấu hình cache nào trong production?

**Dev local:** volumes có tên ổn định theo project/toolchain, ít quan tâm retention, thỉnh thoảng clean có chủ đích khi debug.

**CI persistent runner:** tách cache theo project/platform và permissions, retention rõ, monitor disk usage, tránh jobs đồng thời dùng cache không tương thích.

**CI ephemeral runner:** local Docker volumes không survive; đánh giá registry-backed caching hoặc persistent cache service hỗ trợ platform/tooling, nhưng phải kiểm chứng auth, latency và trust.

**Release:** không dựa vào cache để bỏ qua tests, artifact integrity/SBOM, signature/CVE scan hoặc runtime smoke. Cache là **performance optimization**, không được làm thay đổi quy tắc chấp nhận sản phẩm.

## 15. Bài thực hành cuối và tiêu chí kiểm chứng

### Bài A — xây image lần đầu và làm rõ ba vùng lưu trữ

1. Dựng project Java 17 theo mục 5 và POM hoặc Gradle file ở mục 6/7.
2. Chạy test suite và đọc report; xác nhận `cacheEndpointReturnsExpectedText` thực sự chạy/pass.
3. Chạy image build lần đầu bằng plugin tương ứng, tạo image `cnb-cache-demo:local`.
4. Đọc lifecycle logs, nhất là RESTORING/BUILDING/EXPORTING, ghi layer nào được tạo.
5. `docker volume inspect` hai tên cache volumes được cấu hình.
6. Nêu rõ build workspace khác build/launch cache ở điểm nào.
7. Run container, `GET /cache` trả HTTP 200/`cache-Warm`.

### Bài B — warm build và so sánh

1. Không đổi source/dependency/builder/image name/cache volume names.
2. Build lại **không có `cleanCache`**.
3. Ghi logs cho biết layers nào reused, layers nào vẫn rebuilt.
4. So duration đo thực tế (cùng daemon/network nếu có thể).
5. Giải thích các nguồn tăng tốc khác như Maven repository, Gradle cache, Docker image store.
6. Không tự khẳng định tiết kiệm X% nếu chưa đo.

### Bài C — clean cache có chủ đích

1. Dùng Maven `-Dspring-boot.build-image.cleanCache=true` hoặc Gradle `--cleanCache` cho đúng một build.
2. Đọc lifecycle logs và so với warm build.
3. Xác nhận image vẫn chạy và response đúng.
4. Quay lại command bình thường, chứng minh warm cache có thể được tái sử dụng sau đó.
5. Trình bày vì sao `mvn clean`/`gradlew clean` không tác động cùng cache.

### Bài D — thay code và dependency

1. Chỉ sửa method body trả `code2-Warm`, update test, build không clean cache.
2. Ghi các layers có thể reuse/invalidate và HTTP smoke sau build.
3. Quay code về baseline, nâng Commons Lang tới release version được duyệt.
4. Đối chiếu resolved versions, build logs, image behavior và SBOM nếu có.
5. Giải thích vì sao dependency update không buộc mọi buildpack/JRE layer phải rebuild.

### Bài E — quản lý cache volumes có trách nhiệm

1. Xác định Docker daemon/context và kiểm tra owner của hai volume names tường minh.
2. `docker volume inspect` để xác minh trước khi cân nhắc xóa.
3. Trong **local test daemon riêng**, nếu có quyền và không có job dùng volume, dùng `docker volume rm` đúng hai tên.
4. Build lại, xác minh volumes/layers có thể được tạo mới.
5. Trình bày vì sao không dùng `docker volume prune` hoặc `docker system prune --volumes` ở shared host.

### Checklist hoàn thành

- [ ] Biết build cache dùng để phục hồi buildpack cached layers, launch cache phục vụ reuse launch-related layers.
- [ ] Phân biệt CNB cache với `buildWorkspace`, Maven/Gradle caches, Docker BuildKit và Redis/runtime caches.
- [ ] Giải thích lifecycle analyze/detect/restore/build/export ở mức đủ để đọc logs.
- [ ] Biết buildpack layer flags `build`, `launch`, `cache` và metadata reuse.
- [ ] Biết image name/tag mặc định ảnh hưởng tới Docker cache volume names.
- [ ] Biết cấu hình `buildCache.volume.name`/`launchCache.volume.name` trong Spring Boot Maven Plugin.
- [ ] Biết cấu hình `buildCache { volume {...} }`/`launchCache {...}` trong Gradle `bootBuildImage`.
- [ ] Biết `spring-boot.build-image.cleanCache` và Gradle task option `--cleanCache`.
- [ ] Biết `pack build --clear-cache` là workflow CLI riêng và không cùng nghĩa với Docker prune.
- [ ] Biết dùng `docker volume ls/inspect` trước mọi thao tác dọn.
- [ ] Không xóa Docker volumes của job/team khác hoặc dùng prune tổng quát cho lỗi cache một app.
- [ ] Biết local Docker volumes không tự chia sẻ giữa CI runners/daemons.
- [ ] Có JUnit/MockMvc test report và Docker image HTTP smoke kiểm chứng binary.
- [ ] Có logs/layer evidence để so cold-ish, warm, code-only, dependency-only.
- [ ] Không dùng warm build/cold build durations làm bằng chứng cache hit duy nhất.
- [ ] Biết vì sao custom builder/plugin/toolchain và previous image có thể gây cache invalidation.
- [ ] Biết cache không chứng minh lỗ hổng bảo mật đã được vá hoặc build có thể tái lập bit-for-bit.

**Tiêu chí đạt:** nộp cấu hình Maven hoặc Gradle dùng hai named cache volumes rõ ràng; log ít nhất một image build có cache, một clean-cache run và một warm build; xác nhận volume names qua Docker; giải thích một trường hợp code change và dependency change; kiểm tra container runtime `/cache` trả đúng response. Nếu chưa có Docker daemon, ghi rõ phần Docker/CNB **chưa được chạy**, không tự đánh dấu cache hit/pass bằng suy đoán.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3.13 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Spring Boot 3.3.13 — BootBuildImage API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootBuildImage.html)
- [CNB — Caching Strategies](https://buildpacks.io/docs/for-buildpack-authors/concepts/caching-strategies/)
- [CNB — Create Dependency Layers](https://buildpacks.io/docs/for-buildpack-authors/how-to/write-buildpacks/create-layer/)
- [CNB — Lifecycle Tutorial](https://buildpacks.io/docs/for-platform-operators/tutorials/lifecycle/)
- [CNB — pack build CLI](https://buildpacks.io/docs/tools/pack/cli/pack_build/)
- [Docker — Volumes](https://docs.docker.com/engine/storage/volumes/)
- [Docker — Docker Build Cache](https://docs.docker.com/build/cache/)

**Ghi nhớ:** `buildCache` và `launchCache` phục vụ **quá trình tạo OCI image**, không phải cache dữ liệu kinh doanh của ứng dụng. Muốn tối ưu, đặt tên cache ổn định đúng phạm vi, quan sát logs của CNB lifecycle. Muốn làm sạch, dùng **Spring Boot `cleanCache` / pack `--clear-cache`** hoặc xóa **đúng Docker volume đã xác minh**, tuyệt đối không dùng lệnh prune toàn hệ thống để xử lý một project.