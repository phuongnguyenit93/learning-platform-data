# Tùy chỉnh BootJar layered DSL trong Gradle cho Spring Boot

## 1. Bài toán: một executable JAR, nhiều lớp cache của container

`BootJar` là task do **Spring Boot Gradle Plugin** tạo ra để đóng gói ứng dụng thành executable JAR. Khác với task `jar` thuần của Java plugin, `bootJar` đưa application classes/resources vào `BOOT-INF/classes`, các runtime dependencies vào `BOOT-INF/lib` và thêm Spring Boot launcher.

Khi xây Docker/OCI image, ta muốn tránh upload/build lại toàn bộ dependency binaries chỉ vì đổi một controller. Spring Boot hỗ trợ **layered JAR**: executable archive vẫn giữ cấu trúc JAR chạy được bằng `java -jar`, nhưng có thêm **`BOOT-INF/layers.idx`**, một chỉ mục mô tả file/đường dẫn nào thuộc layer logic nào. Công cụ build image có thể đọc hoặc trích xuất các layer này thành các bước image riêng để tăng cache reuse.

Ví dụ:

```text
source Gradle / Spring Boot
          |
          v
      ./gradlew bootJar
          |
          v
build/libs/layer-demo-0.1.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...    <- spring-boot-loader
├── BOOT-INF/classes/
│   ├── com/example/layer/...              <- application
│   └── static/info.txt                    <- static-assets (tùy chỉnh)
├── BOOT-INF/lib/
│   ├── spring-boot-3.5.0.jar               <- spring-boot-dependencies
│   ├── spring-web-...jar                   <- dependencies
│   └── ...                                 <- các nhóm dependency
└── BOOT-INF/layers.idx                     <- BẢN ĐỒ nhóm layer
          |
          v
tools extract --layers
          |
          v
COPY layer ổn định trước -> COPY application cuối -> OCI image
```

**Điểm phân biệt:** layering **không tạo một JAR riêng cho mỗi layer**; nó thêm metadata vào **một archive**. Việc hình thành image layers xảy ra khi build image bằng Dockerfile hoặc tooling tương đương. `bootJar` tự nó không publish OCI image. `bootBuildImage` của Spring Boot dùng Cloud Native Buildpacks, là một luồng riêng, thường đã có khả năng tối ưu layers mà không cần viết Dockerfile tùy chỉnh.

Bài này dùng **Spring Boot Gradle Plugin 3.5.0, Java 17, Gradle Kotlin DSL**, kèm Groovy DSL. Version cố định nhằm giải thích cú pháp nhất quán, không phải tuyên bố đây là các phiên bản mới nhất. Cần dùng Gradle Wrapper có version được plugin hỗ trợ; một số API/option khác giữa Spring Boot 2.x, 3.x và 4.x.

## 2. Layered JAR mặc định của Spring Boot

Khi dùng Spring Boot Gradle plugin phiên bản hiện đại, `bootJar` **bật layering theo mặc định**. Chỉ số `BOOT-INF/layers.idx` thường có bốn layer:

| Layer mặc định | Nội dung điển hình | Tần suất thay đổi |
| --- | --- | --- |
| `dependencies` | Các dependency **không phải project dependency**, version không chứa `SNAPSHOT` | Ít đổi hơn mã ứng dụng |
| `spring-boot-loader` | Các class Spring Boot launcher dưới `org/springframework/boot/loader/**` | Thường chỉ đổi khi nâng Boot |
| `snapshot-dependencies` | Các external dependencies version chứa `SNAPSHOT` | Có thể đổi thường xuyên |
| `application` | Application classes/resources và **Gradle project dependencies** | Thường đổi nhất |

**Thứ tự mặc định của các layer** là:

```text
dependencies
spring-boot-loader
snapshot-dependencies
application
```

Các lớp ít đổi được đặt **trước**, còn classes/resources ứng dụng ở cuối để hạn chế những layer Docker phía sau bị invalidated khi sửa source Java. Đây là chiến lược cache, **không phải** thứ tự Java class loading hay thứ tự thực thi của Spring beans.

Một lớp trong `layers.idx` có thể được biểu diễn bằng các đường dẫn:

```yaml
- "dependencies":
  - "BOOT-INF/lib/spring-web-6.x.x.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
```

Đây là **ví dụ giản lược** mô tả định dạng và không phải nội dung chính xác của artifact thực tế. Tên/version JAR, số mục và mức gộp directory trong file do plugin/đồ thị dependency quyết định. Có thể có lớp trống; không nên giả định bốn layer luôn chứa file. File thực được xác minh bằng `unzip -p ... BOOT-INF/layers.idx` sau build.

### Layering khác với classpath.idx

| File | Mục đích | Có thay đổi thứ tự class loading không? |
| --- | --- | --- |
| `BOOT-INF/layers.idx` | Gán archive entries vào các nhóm layer phục vụ image creation/extraction | Không được dùng như cơ chế sắp xếp classpath |
| `BOOT-INF/classpath.idx` | Ghi thứ tự dependency JAR trên classpath khi chạy qua Boot launcher | Có thể ảnh hưởng classpath order ở chế độ hỗ trợ |
| `META-INF/MANIFEST.MF` | Khai báo `Main-Class`/`Start-Class` để JVM chạy archive | Quyết định launcher/main entry |

Đừng sửa `layers.idx` thủ công để “ghi đè” một dependency class khác. Việc chọn dependency version nằm ở Gradle resolution và classpath configuration; layer metadata chỉ phục vụ phân nhóm archive.

## 3. Tổng quan cú pháp BootJar layered DSL

Trong `build.gradle.kts`, khi đã áp dụng Spring Boot Gradle plugin:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            // Gán application classes, resources và Boot Loader classes vào layer.
        }
        dependencies {
            // Gán runtime dependency JARs vào layer.
        }
        layerOrder.set(listOf(
            "dependencies",
            "spring-boot-loader",
            "snapshot-dependencies",
            "application"
        ))
    }
}
```

**Ba phần bắt buộc cần hiểu khi tùy chỉnh:**
1. `application { ... }` phân loại **các file application và launcher** bằng pattern kiểu Ant path.
2. `dependencies { ... }` phân loại **dependency artifacts** bằng patterns `group:artifact[:version]` hoặc project dependency selectors.
3. `layerOrder` quyết định **thứ tự đưa các lớp vào index/image**, từ lớp ít biến động đến lớp nhiều biến động.

Đối với **custom layering**, `layerOrder` phải khai báo và chứa **tất cả các tên layer** được `application`/`dependencies` sử dụng. Nếu thiếu hoặc dư cấu hình không tương thích, Gradle có thể fail ở quá trình cấu hình/package thay vì tự đoán thứ tự.

### 3.1. `intoLayer` là bộ phân loại theo thứ tự trên xuống

Ví dụ:

```kotlin
application {
    intoLayer("spring-boot-loader") {
        include("org/springframework/boot/loader/**")
    }
    intoLayer("application")
}
```

Block đầu **nhận** mọi archive entries phù hợp pattern Boot Loader, block sau nhận tất cả nội dung còn lại chưa được claim. Cách chọn này chạy **top-to-bottom**. Nếu đặt `intoLayer("application")` catch-all ở đầu, các block đặc biệt đặt sau có thể không còn file để nhận.

Trong `dependencies` cũng vậy:

```kotlin
dependencies {
    intoLayer("snapshot-dependencies") {
        include("*:*:*SNAPSHOT")
    }
    intoLayer("dependencies")
}
```

Nếu package có dependency `com.example:billing-client:1.2.0-SNAPSHOT`, block đầu sẽ nhận; các release JAR còn lại do block catch-all nhận. `*:*:*SNAPSHOT` là matcher của **Gradle module coordinates**, không phải đường dẫn `BOOT-INF/lib/...`.

### 3.2. `include` và `exclude` hoạt động thế nào?

Một `intoLayer` có thể có:
- `include("pattern")`: chỉ nhận entries khớp pattern, nếu định nghĩa include;
- `exclude("pattern")`: loại entries khớp pattern khỏi layer đó;
- không có `include`: xem xét **mọi nội dung còn lại** chưa được claim;
- không có `exclude`: không có điều kiện loại trừ riêng.

**Exclude không có nghĩa xóa file khỏi JAR.** File bị loại khỏi **layer hiện tại** vẫn có thể được layer phía sau nhận. Nếu không có fallback cuối, có thể dẫn tới nội dung không được phân lớp hợp lệ hoặc quá trình package thất bại; luôn kiểm tra `layers.idx` và chạy ứng dụng.

Ví dụ:

```kotlin
dependencies {
    intoLayer("vendor-libs") {
        include("com.vendor:*:*")
        exclude("com.vendor:experimental-agent:*")
    }
    intoLayer("dependencies")
}
```

`com.vendor` và `experimental-agent` là **tọa độ minh họa**, không phải dependency được khai báo trong bài demo. Một dependency bị exclude ở `vendor-libs` vẫn có thể rơi vào `dependencies` catch-all. Nếu mục tiêu là **không đóng gói** dependency, cần sửa dependencies/configurations của Gradle hoặc các exclusions thực sự ở build configuration, không dùng layer exclude.

## 4. Định nghĩa custom layers: ví dụ thiết kế dễ cache

Ta chia thành sáu layer:

| Layer custom | Nội dung | Lý do |
| --- | --- | --- |
| `spring-boot-dependencies` | Những module dependency có group `org.springframework.boot` (không phải snapshot đã được nhận trước) | Tách nhóm core Boot, đổi chủ yếu khi nâng framework |
| `dependencies` | Các external release JAR còn lại | Cache lại giữa thay đổi business code |
| `spring-boot-loader` | Launcher classes | Tương đối ổn định |
| `snapshot-dependencies` | External dependency có version `SNAPSHOT` | Nhóm dễ thay đổi hơn |
| `static-assets` | Nội dung dưới `BOOT-INF/classes/static/**` | Phân biệt tài nguyên web với Java classes |
| `application` | Application classes/resources còn lại, manifest và Gradle project dependencies | Thay đổi thường xuyên nhất |

**Chọn thứ tự:** dependency ổn định trước, Java classes/resources sau. Việc đặt `static-assets` trước `application` có lợi khi chỉ Java source thay đổi; nếu CSS/JS thay đổi nhiều hơn Java classes, cần đo thực tế và có thể đảo thứ tự hai layer cuối. Không có một `layerOrder` tối ưu cho mọi dự án.

### 4.1. Kotlin DSL hoàn chỉnh

Đoạn sau đặt trong `build.gradle.kts` **đã áp dụng Spring Boot plugin**, không phải file độc lập:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }

            intoLayer("static-assets") {
                include("BOOT-INF/classes/static/**")
            }

            intoLayer("application")
        }

        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }

            intoLayer("snapshot-dependencies") {
                include("*:*:*SNAPSHOT")
            }

            intoLayer("spring-boot-dependencies") {
                include("org.springframework.boot:*:*")
            }

            intoLayer("dependencies")
        }

        layerOrder.set(
            listOf(
                "spring-boot-dependencies",
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "static-assets",
                "application"
            )
        )
    }
}
```

**Giải thích thứ tự matcher:**
- Project dependencies được nhận vào `application` trước để theo mặc định chúng thường thay đổi cùng code trong mono-repo.
- SNAPSHOT external được nhận trước release dependency group, tránh vô tình đưa SNAPSHOT `org.springframework.boot` (nếu có) vào nhóm ổn định.
- `org.springframework.boot:*:*` là tọa độ module matcher có cả version wildcard, không phải đường dẫn file.
- `dependencies` không có include nhận mọi JAR dependency còn lại.
- `spring-boot-loader` lấy classes trong `org/springframework/boot/loader/**` (không phải các JAR runtime `org.springframework.boot:spring-boot`).
- `static-assets` lấy static files bên trong `BOOT-INF/classes/static/**`; classes/manifest/resource khác rơi vào `application`.

**Không được rút bỏ fallback `intoLayer("application")` hay `intoLayer("dependencies")`** khi thêm các matcher đặc biệt nếu chưa chứng minh mọi entry được nhận. Sự thiếu hụt fallback có thể gây lỗi layer configuration hoặc artifact không dùng được.

### 4.2. Tại sao các tên layer có thể tùy chỉnh?

`intoLayer("static-assets")` và `intoLayer("spring-boot-dependencies")` là **tên logic do người viết chọn**; không có Java module riêng mang tên đó. Tên xuất hiện trong `BOOT-INF/layers.idx` và trong thư mục trích xuất khi dùng jarmode tools. Khi đổi tên, phải cập nhật:
- `layerOrder`;
- những lệnh kiểm tra index;
- đường dẫn `COPY --from=...` trong Dockerfile;
- bất cứ logic image tool nào đã hardcode tên layer cũ.

Tên layer không tự tạo một Gradle task mới, và cũng không làm một JAR dependency được publish theo classifier mới.

## 5. Ví dụ ứng dụng Spring Boot Java 17 hoàn chỉnh

Ví dụ này đủ để tự tạo project Gradle đơn module và kiểm tra custom layering. `static/info.txt` chứng minh custom `static-assets` layer; controller Java chứng minh `application` layer; dependencies từ Spring Boot starter web chứng minh các layers cho dependency JARs.

### 5.1. Cấu trúc project

```text
layer-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/com/example/layer/LayerDemoApplication.java
└── src/main/resources/static/info.txt
```

Bạn cần JDK 17+ và Gradle Wrapper tương thích với plugin Spring Boot 3.5.0. Với repository đã có Wrapper, dùng `./gradlew`. Với repo chưa có Wrapper, dùng Gradle tương thích đã cài để chạy `gradle wrapper` hoặc chạy Gradle CLI trực tiếp, rồi commit các file wrapper vào repository.

### 5.2. File `settings.gradle.kts`

```kotlin
rootProject.name = "layer-demo"
```

### 5.3. File `build.gradle.kts` đầy đủ

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

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
}

tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("static-assets") {
                include("BOOT-INF/classes/static/**")
            }
            intoLayer("application")
        }

        dependencies {
            intoLayer("application") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include("*:*:*SNAPSHOT")
            }
            intoLayer("spring-boot-dependencies") {
                include("org.springframework.boot:*:*")
            }
            intoLayer("dependencies")
        }

        layerOrder.set(
            listOf(
                "spring-boot-dependencies",
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "static-assets",
                "application"
            )
        )
    }
}
```

**Vì sao cấu hình đủ?** Java plugin cung cấp source sets/tasks; Spring Boot plugin tạo task `bootJar`; dependency-management plugin giúp versions của Spring Boot dependencies được resolve nhất quán với BOM; `java.toolchain` sử dụng compiler Java 17 phù hợp; `layered` cấu hình chỉ số layers khi tạo executable JAR.

Khi dùng một dự án thực tế đã có `plugins`, `repositories` và `dependencies`, **không dán thêm hai block `plugins` hoặc task `bootJar` trùng lặp**. Hãy thêm/ghép duy nhất cấu hình `tasks.named<BootJar>("bootJar")` và giữ quy ước plugin versions của repo.

### 5.4. Main class Java

**`src/main/java/com/example/layer/LayerDemoApplication.java`:**

```java
package com.example.layer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LayerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }

    @GetMapping("/layers")
    public String layers() {
        return "layers-ok";
    }
}
```

### 5.5. Static resource

**`src/main/resources/static/info.txt`:**

```text
STATIC_LAYER_OK
```

Spring Boot MVC có thể phục vụ file trong `static` dưới URL `/info.txt`. Trong archive, file nằm tại `BOOT-INF/classes/static/info.txt` và custom matcher gán nó vào `static-assets`.

### 5.6. Build và kiểm tra ứng dụng

Từ root `layer-demo`:

```bash
./gradlew clean bootJar
java -jar build/libs/layer-demo-0.1.0.jar
```

Khi web server lên ở port 8080 (nếu không có override và cổng còn trống), terminal khác gọi:

```bash
curl -fsS http://localhost:8080/layers
curl -fsS http://localhost:8080/info.txt
```

Response body mong đợi, tương ứng:

```text
layers-ok
STATIC_LAYER_OK
```

Hai lệnh `curl` riêng có thể hiển thị liền vì Java String response không tự thêm newline; file static có thể giữ newline cuối. Dùng Ctrl+C dừng ứng dụng. Nếu port 8080 bận, chạy `java -jar ... --server.port=9090` và đổi URL theo port mới.

**Một lỗi thường gặp:** chạy `./gradlew jar` rồi inspect `build/libs/layer-demo-0.1.0-plain.jar` thay vì `bootJar`. Plain JAR của Gradle Java plugin không phải executable Spring Boot JAR; thường không chứa nested dependencies hay `BOOT-INF/layers.idx`.

## 6. Kiểm tra layers.idx và archive layout

Sau `./gradlew clean bootJar`:

```bash
jar tf build/libs/layer-demo-0.1.0.jar
```

Các entry cần tìm:

```text
BOOT-INF/layers.idx
BOOT-INF/classes/com/example/layer/LayerDemoApplication.class
BOOT-INF/classes/static/info.txt
BOOT-INF/lib/spring-boot-3.5.0.jar
org/springframework/boot/loader/launch/JarLauncher.class
META-INF/MANIFEST.MF
```

Đây là danh sách **các entry đại diện**, không phải output đầy đủ hoặc lời hứa về mọi dependency version. `jar tf` chỉ xác nhận sự hiện diện, chưa đọc **layer assignment**.

### 6.1. Đọc chỉ mục bằng unzip

Trên Linux/macOS hoặc môi trường có `unzip`:

```bash
unzip -p build/libs/layer-demo-0.1.0.jar BOOT-INF/layers.idx
```

Chỉ số phải chứa **sáu tên layer**, đúng thứ tự khai báo:

```text
spring-boot-dependencies
dependencies
spring-boot-loader
snapshot-dependencies
static-assets
application
```

Trên đây chỉ là **danh sách tên cần nhận diện**, không phải nội dung nguyên văn của `layers.idx`. File thực có cú pháp tương thích YAML với keys/paths được quote:

```yaml
- "spring-boot-dependencies":
  - "BOOT-INF/lib/spring-boot-3.5.0.jar"
- "dependencies":
  - "BOOT-INF/lib/spring-web-6.x.x.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "snapshot-dependencies":
- "static-assets":
  - "BOOT-INF/classes/static/"
- "application":
  - "BOOT-INF/classes/com/example/layer/"
  - "META-INF/"
```

Đây là **minh họa rút gọn** của định dạng index; không copy vào JAR như một file chính xác. Có thể xuất hiện additional resource paths, META-INF, project JARs và entries rỗng. Phiên bản `spring-web` trong ví dụ là wildcard mô tả, không phải literal filename.

**Kiểm tra logic mong đợi:**
- `spring-boot-3.5.0.jar`: thuộc `spring-boot-dependencies` (vì group `org.springframework.boot`).
- `spring-web-...jar`: thuộc `dependencies` (vì group `org.springframework`).
- `static/info.txt`: thuộc `static-assets`.
- Class `LayerDemoApplication.class`: thuộc `application`.
- Launcher classes: thuộc `spring-boot-loader`.

Nếu static file xuất hiện trong `application`, cần kiểm tra đường matcher `BOOT-INF/classes/static/**`, liệu file thực có nằm dưới `src/main/resources/static` và task đang inspect đúng JAR hay không.

### 6.2. Kiểm tra trên Windows PowerShell

`jar` của JDK chạy được trên Windows:

```powershell
jar tf build/libs/layer-demo-0.1.0.jar |
    Select-String 'BOOT-INF/layers.idx|BOOT-INF/classes/static/info.txt'
```

Để đọc `layers.idx`, dùng công cụ ZIP có thể mở entry trong JAR (PowerShell/.NET ZipArchive, 7-Zip hoặc IDE). Không giả định lệnh `unzip` luôn có trên Windows. Đừng đổi đuôi JAR sang ZIP rồi sửa/nén lại bằng tay vì có thể làm hỏng manifest/order/timestamps.

## 7. Quy tắc matcher của application và dependencies

### 7.1. Pattern application là đường dẫn file trong archive

`application.intoLayer(...)` dùng Ant-style path matching. Các ví dụ:

| Pattern | Match gì? | Dùng cho |
| --- | --- | --- |
| `org/springframework/boot/loader/**` | Các Spring Boot launcher classes | `spring-boot-loader` |
| `BOOT-INF/classes/static/**` | Static web resources | `static-assets` |
| `BOOT-INF/classes/templates/**` | Template files | Layer template riêng nếu có nhu cầu |
| `BOOT-INF/classes/db/migration/**` | SQL migrations | Layer migrations nếu tính cache hợp lý |
| `BOOT-INF/classes/com/example/**` | Application bytecode/resource paths | Một nhóm classes của ứng dụng |
| `META-INF/**` | Manifest/metadata | Chỉ phân tách khi có lý do rõ |

**Không dùng `src/main/resources/static/**`** làm matcher ở `layered.application`; đó là đường dẫn **trước packaging**, trong khi DSL phân loại archive entries theo đường dẫn **sau packaging**. Với executable Boot JAR, resource root nằm trong `BOOT-INF/classes`.

Matcher chọn **file bên trong archive**, không điều khiển task `processResources`. Nếu muốn loại một file khỏi archive, sửa Gradle resource copy/exclude hoặc source set; `layered.application.intoLayer` chỉ chọn layer.

### 7.2. Pattern dependencies là Maven/Gradle module coordinates

`dependencies.intoLayer(...)` xét `group:artifact[:version]`, không dựa vào filename `spring-web-...jar`:

```kotlin
dependencies {
    intoLayer("spring-boot-dependencies") {
        include("org.springframework.boot:*:*")
    }
    intoLayer("dependencies")
}
```

Các ví dụ matcher:
- `org.springframework.boot:*:*`: mọi artifact trong group Spring Boot.
- `com.example:shared-api:*`: một shared API artifact của group `com.example`.
- `*:*:*SNAPSHOT`: những module versions có đuôi phù hợp với pattern SNAPSHOT.
- `com.vendor:*:*`: các artifacts trong group `com.vendor`, nếu project dùng chúng.

**Không viết `BOOT-INF/lib/spring-boot-*.jar` trong dependencies block** để chọn dependency group: đó là file path, không phải tọa độ. Ngược lại, không dùng `org.springframework.boot:*:*` trong `application` block để chọn Java classes.

### 7.3. Include/exclude order có thể chồng lấp

Giả sử một artifact có coordinates `com.vendor:agent:1.0-SNAPSHOT`, khớp cả:
- `*:*:*SNAPSHOT`;
- `com.vendor:*:*`.

Nếu block snapshot xuất hiện trước, artifact được claim bởi `snapshot-dependencies`; block vendor phía sau không nhận nó nữa. Nếu muốn “ưu tiên vendor bất kể SNAPSHOT”, đặt vendor layer trước. Hai lựa chọn phản ánh **chính sách cache khác nhau**, không có quy tắc đúng cho mọi hệ thống.

### 7.4. Project dependencies khác external SNAPSHOT

Một Gradle dependency:

```kotlin
dependencies {
    implementation(project(":shared-lib"))
}
```

là **project dependency**, khác với:

```kotlin
dependencies {
    implementation("com.example:shared-lib:0.1.0-SNAPSHOT")
}
```

Dòng đầu tham chiếu sibling project trong cùng multi-project build, được matcher `includeProjectDependencies()` nhận; dòng thứ hai là module dependency có GAV qua repository, có thể khớp `*:*:*SNAPSHOT`. Chúng có thể cùng artifactId nhưng quản lý nguồn và caching khác nhau.

## 8. Gradle Groovy DSL tương đương

Nếu project dùng `build.gradle` (Groovy) thay vì `build.gradle.kts` (Kotlin), các ý tưởng giống nhau, nhưng syntax khác.

**Đoạn đặt trong `build.gradle` đã áp dụng Spring Boot plugin**:

```groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('static-assets') {
                include 'BOOT-INF/classes/static/**'
            }
            intoLayer('application')
        }

        dependencies {
            intoLayer('application') {
                includeProjectDependencies()
            }
            intoLayer('snapshot-dependencies') {
                include '*:*:*SNAPSHOT'
            }
            intoLayer('spring-boot-dependencies') {
                include 'org.springframework.boot:*:*'
            }
            intoLayer('dependencies')
        }

        layerOrder = [
            'spring-boot-dependencies',
            'dependencies',
            'spring-boot-loader',
            'snapshot-dependencies',
            'static-assets',
            'application'
        ]
    }
}
```

Đây **không phải file `build.gradle` hoàn chỉnh**: cần có `plugins` (`java` và Spring Boot), repositories/dependencies/toolchain như mẫu Kotlin. Đừng trộn syntax `layerOrder = [...]` của Groovy với `layerOrder.set(listOf(...))` của Kotlin DSL trong một file.

### Kotlin DSL và Groovy DSL đối chiếu

| Tác vụ | Kotlin DSL | Groovy DSL |
| --- | --- | --- |
| Định danh task | `tasks.named<BootJar>("bootJar")` | `tasks.named('bootJar')` |
| Chọn file | `include("BOOT-INF/classes/static/**")` | `include 'BOOT-INF/classes/static/**'` |
| Project libs | `includeProjectDependencies()` | `includeProjectDependencies()` |
| Thứ tự layers | `layerOrder.set(listOf("a", "b"))` | `layerOrder = ['a', 'b']` |
| Tắt index/layering | `layered { enabled.set(false) }` | `layered { enabled = false }` |
| Tắt jar tools ở Boot 3.5 | `includeTools.set(false)` **ở BootJar** | `includeTools = false` **ở bootJar** |

Khi copy snippets từ Spring Boot 2.5 hoặc các bài cũ, có thể thấy `includeLayerTools`, `isIncludeLayerTools` và jar mode `layertools`. Trong Spring Boot 3.5, **`includeTools`** ở `BootJar` và `jarmode=tools` là lựa chọn hiện hành. Chọn tài liệu đúng phiên bản để tránh lỗi “unknown property/method”.

## 9. Không cần custom layer khi mặc định đã đủ

Với nhiều service, mặc định `dependencies → spring-boot-loader → snapshot-dependencies → application` đã có ý nghĩa và dễ quản lý. Chỉ tùy chỉnh khi có **bằng chứng** rằng một nhóm dependency hoặc resource có chu kỳ thay đổi đặc biệt, và Dockerfile/CI thực sự tận dụng cache theo layer.

Các lý do hợp lý:
- Một nhóm framework JAR hiếm đổi, muốn cache độc lập với các third-party libs khác.
- Multi-project modules đổi cùng app source, cần tách chúng khỏi external releases.
- Static resources đổi ít hơn Java classes, muốn có `static-assets` layer.
- Migrations/schema thay đổi theo chu kỳ riêng, cần cache hoặc review diff rõ.
- Giảm thời gian push/pull container image trên CI registry bằng các lớp có digest ổn định.

Các lý do **chưa đủ**:
- Muốn giảm RAM runtime bằng cách tạo nhiều layers: layer metadata không tự phân vùng heap.
- Muốn “chạy từng dependency trước”: image layer không liên quan thứ tự class loading.
- Muốn sửa version conflict: cần dependency resolution/constraints, không phải layer matcher.
- Muốn thu nhỏ image ngay lập tức: layer phân tách có thể **không giảm tổng số bytes**, đôi khi thêm metadata/overhead.
- Muốn mã hóa secret: secret không nên đóng vào executable JAR hoặc image; layering không phải cơ chế bảo mật.

**Thước đo thành công** nên là thay đổi trong **image layer digests**, build time, registry upload/download bytes, cache hit, cùng với startup và correctness; không nên chỉ đếm số layers trong `layers.idx`.

## 10. Tắt layering hoặc bỏ JAR tools khi nào?

### 10.1. Tắt layering

Nếu không dùng image layer extraction/buildpacks metadata và muốn artifact không chứa `layers.idx`:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(false)
    }
}
```

**Đây là cấu hình thay thế**, không dán song song với custom `layered { application {...} ... }` của phần trước trong cùng `bootJar`. Khi layering tắt, không mong đợi `BOOT-INF/layers.idx`. File JAR vẫn có thể chạy bằng `java -jar`, nhưng không có metadata phục vụ trích xuất theo layers.

Groovy:

```groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
```

### 10.2. Giữ layers.idx nhưng không đưa jarmode tools vào JAR

Trong Spring Boot 3.5, `BootJar` hỗ trợ property **`includeTools`**. Nếu deployment không cần tự gọi jar tools, có thể bỏ phần dependency hỗ trợ tools:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    includeTools.set(false)
}
```

Groovy:

```groovy
tasks.named('bootJar') {
    includeTools = false
}
```

Đây là **cấu hình bổ sung ở cấp BootJar**, không phải `layered { includeLayerTools... }` của Boot cũ. Tắt `includeTools` không có nghĩa tắt layering: `BOOT-INF/layers.idx` có thể vẫn được tạo. Nhưng câu lệnh `java -Djarmode=tools -jar app.jar ...` sẽ **không hoạt động** nếu công cụ jar mode không có trong archive; Dockerfile dùng trích xuất phải đổi sang công cụ ngoài hoặc bật lại tools. **Với demo ở mục 5/12, giữ mặc định includeTools=true.**

### 10.3. Fully executable archive với launch script

Một số Spring Boot Gradle builds thêm Unix launch script phía trước JAR bằng `launchScript()`. Với artifact cần dùng `java -Djarmode=tools -jar ... extract`, nên tránh fully executable JAR có prefix script: một số ZIP/JAR tooling và jar mode không xử lý định dạng đó đúng. Demo dùng **executable JAR tiêu chuẩn** (chạy qua `java -jar`), không bật launch script.

## 11. Trích xuất layer bằng Spring Boot jar tools

Spring Boot 3.5 hỗ trợ **`-Djarmode=tools`**, cung cấp các lệnh như `list-layers`, `extract` và `help` khi tools đã được đưa vào archive (mặc định phù hợp với layered Boot JAR).

Với demo:

```bash
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar list-layers
```

Output sẽ liệt kê tên các layer được chỉ mục hóa. Nội dung chính cần xác minh:

```text
spring-boot-dependencies
dependencies
spring-boot-loader
snapshot-dependencies
static-assets
application
```

Đây là **tên layer kỳ vọng**, không cam kết định dạng đầy đủ của console output hoặc đảm bảo tất cả layer có file.

Trích xuất thành thư mục:

```bash
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar \
  extract --layers --destination build/extracted
```

Khi hoạt động bình thường, trong `build/extracted` sẽ có những thư mục mang tên layer (có thể không tạo thư mục cho layer không chứa file), chứa các thành phần JAR thuộc layer. Ví dụ:
- `build/extracted/spring-boot-dependencies/BOOT-INF/lib/...`;
- `build/extracted/dependencies/BOOT-INF/lib/...`;
- `build/extracted/static-assets/BOOT-INF/classes/static/info.txt`;
- `build/extracted/application/...`.

Cần phân biệt **đường dẫn trích xuất** với nội dung logical layer index. Thao tác `extract --layers` tạo filesystem layout để Dockerfile copy; `java -jar build/libs/layer-demo-0.1.0.jar` vẫn chạy ứng dụng từ JAR nguyên bản, không cần bạn extract trước.

### 11.1. Nếu jarmode tools không hoạt động

Kiểm tra:
1. Có dùng đúng executable Boot JAR từ `bootJar`, không phải plain `jar`?
2. Có bị đặt `includeTools.set(false)` không?
3. Java option `-Djarmode=tools` có đứng **trước `-jar`** không?
4. Đang dùng Boot 3.5 hay hướng dẫn jar mode `layertools` của phiên bản cũ?
5. JAR có phải fully executable với launch-script prefix gây bất tương thích không?
6. `layers.idx` có tồn tại khi cần `--layers` không?
7. Có đúng Java 17+ runtime và archive không bị hỏng không?

Lệnh đúng:

```bash
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar list-layers
```

Không nên dùng:

```bash
java -jar build/libs/layer-demo-0.1.0.jar --jarmode=tools
```

Dòng thứ hai đưa argument vào **Spring Boot application**, không đặt JVM system property để chuyển Boot launcher sang jar mode. Nó sẽ không tương đương với lệnh đầu.

## 12. Dockerfile nhiều giai đoạn tận dụng custom layers

Đây là cách thấy lợi ích của layered DSL: dùng jar tools extract archive thành thư mục theo custom layer names, rồi copy từng nhóm vào runtime image theo thứ tự đã chọn.

**`Dockerfile` minh họa đúng với project Kotlin DSL ở mục 5:**

```dockerfile
FROM eclipse-temurin:17-jre AS unpack
WORKDIR /workspace
COPY build/libs/layer-demo-0.1.0.jar application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted \
    && mkdir -p extracted/snapshot-dependencies

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=unpack /workspace/extracted/spring-boot-dependencies/ ./
COPY --from=unpack /workspace/extracted/dependencies/ ./
COPY --from=unpack /workspace/extracted/spring-boot-loader/ ./
COPY --from=unpack /workspace/extracted/snapshot-dependencies/ ./
COPY --from=unpack /workspace/extracted/static-assets/ ./
COPY --from=unpack /workspace/extracted/application/ ./

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
```

**Điều kiện của ví dụ:**
- Lệnh `./gradlew clean bootJar` đã tạo `build/libs/layer-demo-0.1.0.jar`.
- Chạy `docker build` tại project root; Docker build context chứa file JAR và không có `.dockerignore` loại mất nó.
- JAR giữ mặc định `includeTools=true` để builder có thể extract.
- `static-assets` có `info.txt` nên layer đó có nội dung; `snapshot-dependencies` có thể rỗng, nên `mkdir -p` ở builder bảo đảm Docker `COPY` không fail chỉ vì thư mục không được tạo.
- Cả builder và runtime dùng JRE 17 tương thích classfile của demo.
- Tên layer trong `COPY` phải **khớp chính xác** với `layerOrder` và chỉ số layers; đổi tên layer ở Gradle phải cập nhật Dockerfile.
- Tệp `application.jar` ở runtime là archive đã trích xuất cho chế độ chạy này theo jar-tools layout; **không phải nguyên JAR fat** bạn copy ban đầu từ `build/libs`.

Chạy:

```bash
./gradlew clean bootJar
docker build -t layer-demo:dev .
docker run --rm -p 127.0.0.1:8080:8080 layer-demo:dev
```

Sau khi container chạy, `curl -fsS http://localhost:8080/layers` phải trả body `layers-ok`; `curl -fsS http://localhost:8080/info.txt` phải trả `STATIC_LAYER_OK`. Nếu Dockerfile dùng image base khác, kiểm tra Java runtime và filesystem permissions trước khi triển khai.

**Quan trọng về cache:** Docker xử lý `COPY` theo thứ tự. Khi chỉ sửa Java controller, `application` thường đổi, còn những lớp `spring-boot-dependencies`/`dependencies` đứng trước vẫn có thể được cache. Khi đổi một dependency version thuộc `dependencies`, layer đó và các bước sau có thể bị invalidated. Thứ tự Dockerfile nên nhất quán với `layerOrder` và tần suất đổi thực tế. Cache hiệu quả còn phụ thuộc Docker builder, cấu hình registry, image base và tính tái lập của bytes mỗi layer.

### 12.1. Vì sao không chỉ COPY toàn bộ JAR?

Một Dockerfile tối giản:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /application
COPY build/libs/layer-demo-0.1.0.jar application.jar
ENTRYPOINT ["java", "-jar", "application.jar"]
```

vẫn **chạy được** và đơn giản. Nhưng mỗi lần JAR fat thay đổi, lệnh `COPY` đó có thể invalidate một image layer chứa **toàn bộ JAR**, kể cả dependency JARs không đổi. Layered extraction chia nội dung thành nhiều `COPY` để OCI builder/registry tái sử dụng các khối ổn định. Nếu kích thước app nhỏ hoặc pipeline không có image cache, chi phí thêm phức tạp có thể không đáng.

### 12.2. Docker cache không đồng nghĩa JAR reproducible

Hai lần Gradle build có thể tạo JAR bytes khác do timestamp, generated metadata hay input dependencies, dù source không đổi. Khi đó extracted layer content/digest có thể thay đổi và cache hit kém.

Nên dùng:
- Gradle Wrapper/Java toolchain và dependency versions xác định.
- Archive tasks tạo file order/timestamps ổn định (Gradle mới đã có defaults tái lập, với bản cũ cấu hình tường minh).
- Tránh đưa thời điểm build/đường dẫn tuyệt đối/secret vào generated resources.
- So sánh layer contents và image layer hashes giữa hai build cùng commit.
- Không lạm dụng `--no-cache` khi đo hiệu quả cache; dùng cả một phép thử cold và warm build.

## 13. Multi-project Gradle: project dependency thuộc lớp nào?

Một repository lớn có thể:

```text
settings.gradle.kts
├── core/
├── service/
└── app/
```

`app` tham chiếu sibling project:

```kotlin
dependencies {
    implementation(project(":service"))
}
```

Một project JAR như `:service` có thể xuất hiện trong executable `app` khi Gradle resolve runtimeClasspath. **Mặc định, Spring Boot phân loại project dependency vào `application` layer** vì cùng monorepo nên thường biến động nhanh. Custom DSL ở mục 4 giữ hành vi đó:

```kotlin
dependencies {
    intoLayer("application") {
        includeProjectDependencies()
    }
    // Các nhóm dependency còn lại...
}
```

Đây là block thuộc `layered { dependencies { ... } }` trong task `bootJar` của **module app**, không phải top-level `dependencies` của Gradle. Hai DSL đều có tên `dependencies` nhưng phạm vi hoàn toàn khác nhau:

- `dependencies { implementation(project(":service")) }`: khai báo **runtime/compile dependencies** của Gradle project.
- `layered { dependencies { intoLayer(...) } }`: **phân nhóm những dependencies đã resolve** vào layer metadata.

### 13.1. Khi nào tách project dependencies thành một layer riêng?

Nếu app source đổi thường xuyên nhưng module `:service` chỉ đổi ít, có thể chuyển project dependencies sang layer `project-dependencies`:

```kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        application {
            intoLayer("spring-boot-loader") {
                include("org/springframework/boot/loader/**")
            }
            intoLayer("application")
        }
        dependencies {
            intoLayer("project-dependencies") {
                includeProjectDependencies()
            }
            intoLayer("snapshot-dependencies") {
                include("*:*:*SNAPSHOT")
            }
            intoLayer("dependencies")
        }
        layerOrder.set(
            listOf(
                "dependencies",
                "spring-boot-loader",
                "snapshot-dependencies",
                "project-dependencies",
                "application"
            )
        )
    }
}
```

Đây là **một cấu hình thay thế độc lập** so với custom sáu layer ở mục 4. Đừng dán cả hai `tasks.named<BootJar>` với layer selection khác nhau rồi hy vọng thứ tự tự giải quyết. Với multi-project repo, cấu hình bootJar cần nằm đúng **project ứng dụng** hoặc convention plugin được áp dụng có chủ đích cho các app modules. Thư viện `core`/`service` có thể chỉ cần task `jar` và không tạo executable Boot JAR.

**Đánh đổi:** tách project dependencies có thể tăng cache reuse khi chỉ app thay đổi; nhưng nếu module service đổi cùng app trên hầu hết commits, layer này lại thường bị invalidated. Dựa vào thay đổi thực tế, không tối ưu dựa vào giả định.

## 14. Kiểm thử ảnh hưởng của từng thay đổi lên layer cache

Một quy trình thử nghiệm có thể dùng ba lần build:

### 14.1. Build A — baseline

```bash
./gradlew clean bootJar
java -Djarmode=tools -jar build/libs/layer-demo-0.1.0.jar \
  extract --layers --destination build/extracted-a
```

Ghi lại danh sách layer, file count, tổng kích thước, SHA-256 của những file quan trọng. Nếu thử nhiều lần trong cùng workspace, phải tránh `extract` vào thư mục cũ chưa được dọn; tools có thể từ chối ghi khi destination không rỗng hoặc ghi đè theo chính sách riêng.

### 14.2. Build B — chỉ sửa Java controller

Sửa response của `/layers` từ `layers-ok` sang một chuỗi khác, **giữ nguyên dependency versions và static resource**. Build lại và extract vào thư mục mới. Kỳ vọng:
- `application` layer chứa class bytecode đổi.
- `static-assets` và dependency layers không đổi, nếu inputs/generator/archive metadata được kiểm soát.
- Runtime response phải phản ánh code mới.

Nếu `spring-boot-dependencies` layer cũng đổi dù không sửa dependency, kiểm tra Gradle dependency resolution, archive reproducibility, timestamp/permissions hoặc các file generated bị ảnh hưởng bởi lần build.

### 14.3. Build C — chỉ sửa static info.txt

Giữ Java code và dependency versions, đổi `src/main/resources/static/info.txt`:
- `static-assets` layer thay đổi.
- `application` bytecode có thể không đổi.
- Response từ `/info.txt` thay đổi.
- Nếu `static-assets` đứng trước `application` trong Dockerfile, tùy caching image builder, các bước sau static có thể bị invalidated mặc dù bytecode application không đổi. Thứ tự layer vì thế phải được tối ưu dựa trên tần suất thay đổi.

Để đo tác động thực, build Docker image hai lần với BuildKit/cache bật, kiểm tra output layer digests và registry transfer, không chỉ nhìn toàn bộ `build/libs/*.jar` checksum. Container image là output khác với JAR; một JAR thay đổi không nhất thiết khiến **mọi layer** đã extract thay đổi.

## 15. Layer name và pattern bị sai: Gradle biểu hiện thế nào?

### 15.1. Sai `layerOrder`

Ví dụ có:

```kotlin
intoLayer("static-assets") {
    include("BOOT-INF/classes/static/**")
}
```

nhưng `layerOrder` không chứa `static-assets`. Đây là cấu hình không nhất quán: tên layer được tham chiếu bởi matcher phải có trong ordered list. Spring Boot plugin có thể báo lỗi tạo layers hoặc khi package. Sửa bằng cách cập nhật `layerOrder.set(...)` để liệt kê đầy đủ và không dùng tên bị đánh vần khác (`static-asset` vs `static-assets`).

### 15.2. Catch-all sai vị trí

**Sai:**

```kotlin
application {
    intoLayer("application")
    intoLayer("static-assets") {
        include("BOOT-INF/classes/static/**")
    }
}
```

Block `application` đầu tiên nhận mọi entry còn lại nên `static-assets` không có file để nhận. **Đúng:** đưa các matcher đặc biệt lên trước, catch-all cuối. Cùng nguyên tắc cho dependencies.

### 15.3. Pattern của một section dùng nhầm trong section khác

`include("org.springframework.boot:*:*")` là tọa độ cho **dependencies**, không phải application file path. `include("BOOT-INF/classes/static/**")` là đường dẫn cho **application**, không phải dependency coordinates. Pattern có thể hợp lệ về cú pháp nhưng không match nội dung, dẫn đến phân lớp không như dự kiến.

### 15.4. Exclude không xóa file khỏi executable JAR

`exclude("com.vendor:legacy:*")` trong `intoLayer("vendor")` có nghĩa là **không đưa artifact này vào layer vendor**. Nếu catch-all `dependencies` phía sau nhận nó, JAR vẫn có `BOOT-INF/lib/legacy-...jar`. Muốn loại hẳn, dùng Gradle dependency resolution/exclusion đúng chỗ, xác nhận ứng dụng vẫn chạy.

### 15.5. SNAPSHOT và project dependency chồng nhau

Project dependency trong build multi-project và external SNAPSHOT không phải cùng loại. `includeProjectDependencies()` chọn local project outputs, còn `include("*:*:*SNAPSHOT")` chọn GAV pattern của module dependencies. Khi cần chính sách khác, đặt matchers theo ưu tiên, xem `layers.idx` thay vì chỉ đoán theo tên version hoặc filename.

## 16. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Unresolved reference: BootJar` trong Kotlin DSL | Thiếu import hoặc plugin chưa được áp dụng | Thêm `import org.springframework.boot.gradle.tasks.bundling.BootJar` và Spring Boot plugin |
| `Task 'bootJar' not found` | Chạy ở library project hoặc chưa áp dụng Java/Spring Boot plugin | Cấu hình đúng module app; xác minh plugins/tasks |
| Không có `BOOT-INF/layers.idx` | Layering bị tắt hoặc đang xem plain JAR | Kiểm tra `bootJar`, `enabled` và đúng build/libs file |
| Gradle báo thiếu layer order | Có custom `application`/`dependencies` nhưng `layerOrder` không set | Thêm ordered list chứa mọi layer được tham chiếu |
| Layer custom có tên nhưng không có file | Matcher sai, không có matching content, hoặc catch-all trước đã claim hết | Đọc `layers.idx`, xác nhận archive paths/GAV, đổi matcher order |
| `spring-boot-loader` rỗng | Pattern sai (nhầm groupId với path) | Dùng `org/springframework/boot/loader/**` trong application section |
| `static-assets` rỗng | Dùng `src/main/resources/static/**` thay archive path | Dùng `BOOT-INF/classes/static/**` và bảo đảm file được đóng gói |
| External SNAPSHOT vào dependencies thường | Snapshot matcher sai hoặc nhóm khác đã claim trước | Dùng `*:*:*SNAPSHOT` và kiểm tra thứ tự |
| Project JAR không vào application layer | Thiếu `includeProjectDependencies()` hoặc custom policy | Chọn policy/project selector rõ; inspect `layers.idx` |
| `-Djarmode=tools` không chạy | `includeTools=false`, dùng plain JAR, JVM option đặt sai | Dùng BootJar đúng, bật tools, đặt -D trước -jar |
| Docker COPY layer path báo not found | Tên layer khác, layer trống không được tạo, extract path sai | Đồng bộ layerOrder/Dockerfile; tạo empty dirs nếu cần |
| Container thiếu class/resource sau extract | Không copy đủ các layer hoặc thiếu app jar từ extraction | Copy mọi layer cần thiết, chạy smoke test |
| Cache Docker không cải thiện | Image copy nguyên JAR, layer order thiếu hợp lý, generated files đổi liên tục | Dùng extracted COPYs, đo layer digests và stable outputs |
| `bootBuildImage` không dùng Dockerfile custom | Buildpacks không đọc Dockerfile của bạn | Phân biệt buildpack image workflow và Dockerfile workflow |
| Layer tool CLI từ tài liệu cũ không chạy | Dùng `layertools`/`includeLayerTools` cũ trên Boot 3.5 | Dùng `jarmode=tools` và `includeTools` |
| Lớp chứa Spring Boot libs thay theo mỗi build | Version ranges/SNAPSHOT, metadata không ổn định | Pin dependencies/versions, kiểm tra cache và generated files |
| Java service chạy JAR nguyên bản được nhưng image fail | Dockerfile copy sai thứ tự/vị trí hoặc runtime JRE khác | Kiểm tra extracted layout và container logs |
| Gradle `jar` và `bootJar` tạo hai file khác | Chọn nhầm plain artifact | Dùng executable `bootJar` output, inspect manifest/layers |
| Có `layers.idx` nhưng image không có các lớp riêng | Dockerfile chỉ `COPY app.jar`, không dùng layer-aware build | Trích xuất và COPY layers hoặc dùng image tooling có hỗ trợ |

### Trình tự debug đề xuất

1. Xác nhận Spring Boot Gradle Plugin và Gradle Wrapper versions.
2. Chạy `./gradlew clean bootJar`; chắc chắn command thành công.
3. Xác nhận file output đúng tên/version; không dùng `-plain.jar`.
4. `jar tf` tìm `BOOT-INF/layers.idx`, class/resource và dependency JARs.
5. `unzip -p ... BOOT-INF/layers.idx` để xem tên, thứ tự và paths.
6. Kiểm tra `application` pattern = archive entry paths, `dependencies` pattern = module coordinates.
7. Kiểm tra matcher order: special selectors trước, catch-all sau.
8. Kiểm tra `layerOrder` liệt kê mọi layer đã dùng.
9. Chạy `java -Djarmode=tools ... list-layers` rồi `extract --layers` với `includeTools=true`.
10. Kiểm tra filesystem extract output và từng `COPY` trong Dockerfile.
11. Chạy `java -jar`/container smoke test cho `/layers` và `/info.txt`.
12. Nếu cache không cải thiện, so sánh layer content/digests giữa hai phiên bản build, kiểm tra dependency resolution, timestamps và thay đổi thực tế.

## 17. Khác biệt giữa BootJar.layered và các cơ chế Gradle khác

| Cơ chế | Phạm vi | Có tạo OCI image không? |
| --- | --- | --- |
| `tasks.named<BootJar>("bootJar") { layered { ... } }` | Gán entries của executable JAR vào logical layers index | Không |
| `bootJar` | Tạo executable Boot JAR | Không |
| `jar` | Tạo plain Java JAR | Không |
| `bootRun` | Chạy app bằng JavaExec-like task trong development | Không |
| `bootBuildImage` | Xây OCI image bằng Cloud Native Buildpacks | Có, theo cấu hình |
| Dockerfile + jar tools extract | Tạo image từ các extracted layers, dùng Docker/BuildKit | Có, khi chạy docker build |
| Gradle build cache | Cache outputs của Gradle tasks theo inputs | Không trực tiếp |
| Docker layer cache | Cache filesystem layers của container image | Có |
| Spring Boot `layers.idx` | Map archive paths sang logical layers | Không trực tiếp |

**Một nhầm lẫn quan trọng:** “Có `layers.idx` nghĩa là Docker cache tự hoạt động tốt”. Không đúng. Nếu Dockerfile chỉ có `COPY build/libs/layer-demo.jar app.jar`, OCI builder không tự tách mỗi entry trong `layers.idx` thành layer filesystem. Cần jar tools extraction, buildpacks hoặc tooling khác biết cách xử lý index.

## 18. An toàn, chất lượng bản build và việc phân lớp

### 18.1. Layering không bảo vệ secret

Nếu `application.properties` chứa password nằm dưới `src/main/resources`, file đó sẽ vào `BOOT-INF/classes` và thuộc một layer. Docker image và JAR có thể bị inspect; **layering không mã hóa, không che nội dung**. Cần cấp secret qua environment/secret manager/mounted file ở **runtime**, không đóng trong source resource hoặc generated metadata.

### 18.2. Tính tái lập ảnh hưởng cache

Để cùng dependency layer tạo cùng digest giữa các build:
- Pin versions/plugin repositories, tránh version ranges động.
- Dùng Java toolchain/Gradle Wrapper thống nhất.
- Không ghi timestamp hiện thời hoặc path workspace vào artifacts.
- Dùng Gradle archive reproducibility options nếu cần cho phiên bản cụ thể.
- Kiểm tra generated code/resource tasks và annotation processors.
- So sánh extracted contents thay vì chỉ nhìn số layer names.

Tạo nhiều layers không làm một build không deterministic tự trở nên deterministic.

### 18.3. License, SBOM và dependency vulnerability

Các lớp `spring-boot-dependencies`/`dependencies` vẫn chứa đầy đủ thư viện runtime đã resolve. Thay layer không loại một thư viện có CVE hay thay license của nó. Dùng dependency report, SBOM và vulnerability scanning theo chính sách tổ chức; khi cần remove dependency, sửa cấu hình Gradle thực sự.

### 18.4. Quyền runtime và filesystem

Trong Docker image, có thể dùng user không root và copy files với quyền đọc thích hợp. `USER 10001` trong Dockerfile ví dụ giả định các extracted files và app JAR đều world-readable; nếu build môi trường dùng permissions khác, kiểm tra bằng image smoke test. Layering không thay thế securityContext, network policy hay secret handling.

## 19. Checklist trước khi áp dụng custom BootJar layer

- [ ] Xác nhận module ứng dụng đang dùng `bootJar`, không phải plain `jar`.
- [ ] Spring Boot/Gradle versions đã được pin và tương thích Java runtime.
- [ ] Có bằng chứng layer mặc định không đủ tốt cho cache/profile thay đổi.
- [ ] Kotlin DSL dùng `BootJar` import, `tasks.named<BootJar>` và `layerOrder.set(listOf(...))`.
- [ ] Groovy DSL dùng `tasks.named('bootJar')` và `layerOrder = [...]`.
- [ ] `application` matchers dùng archive paths, ví dụ `BOOT-INF/classes/static/**`.
- [ ] `dependencies` matchers dùng GAV patterns, ví dụ `org.springframework.boot:*:*`.
- [ ] `includeProjectDependencies()` được cân nhắc riêng với external SNAPSHOTs.
- [ ] Các `intoLayer` cụ thể đặt trước fallback catch-all.
- [ ] `layerOrder` bao gồm đủ tên layer, đặt lớp ổn định trước lớp hay thay.
- [ ] Kiểm tra `BOOT-INF/layers.idx` thực tế sau `./gradlew bootJar`.
- [ ] Kiểm tra `java -Djarmode=tools ... list-layers` và extract nếu cần.
- [ ] Dockerfile/Buildpacks thực sự dùng layer-aware pipeline.
- [ ] Dockerfile COPY theo đúng tên/thứ tự layer; xử lý layer rỗng.
- [ ] Có smoke test HTTP/runtime từ image, không chỉ `BUILD SUCCESS`.
- [ ] Có số đo cache hit, build time, registry push/pull và image size.
- [ ] Không chứa secret trong JAR/layer và không dùng layer để “giải quyết” dependency version conflict.
- [ ] CI có khả năng tái lập inputs, JDK, Gradle wrapper và dependencies.

## 20. Tài liệu chính thức

- Spring Boot 3.5 – [Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html): `BootJar`, layered JAR, custom `application`/`dependencies`/`layerOrder` và `includeTools`.
- Spring Boot 3.5 – [BootJar API](https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootJar.html): task, `layered` và công cụ packaging.
- Spring Boot 3.5 – [LayeredSpec API](https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/LayeredSpec.html): các layer selectors và ordered configuration.
- Spring Boot 3.5 – [Efficient Container Images](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/efficient-images.html): cấu trúc layers và caching strategy.
- Spring Boot 3.5 – [Dockerfiles](https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html): jar tools mode, `extract --layers` và multi-stage Dockerfile.
- Spring Boot 3.5 – [Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): executable layout, `classpath.idx` và `layers.idx`.
- Gradle – [Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): archive tasks, resource processing và file order.
- Gradle – [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project dependencies và module boundaries.
- Gradle – [Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html): GAV resolution và project dependencies.

**Kết luận:** `BootJar.layered` là DSL điều khiển **cách gán executable JAR entries vào logical layers**, không phải API thay dependency, không phải chức năng tạo image trực tiếp. `application { intoLayer(...) }` match **đường dẫn bên trong archive**; `dependencies { intoLayer(...) }` match **dependency coordinates hoặc project dependencies**; `layerOrder` quyết định thứ tự các lớp để hỗ trợ Docker/OCI cache. Viết matcher từ **cụ thể đến fallback**, kiểm tra `BOOT-INF/layers.idx`, dùng `jarmode=tools` khi cần trích xuất, đồng bộ Dockerfile và đo cache hit thật trước khi đánh giá tối ưu thành công.