# Sử dụng dependency locking và dependency verification trong Gradle

## 1. Hai cơ chế bổ sung cho bản dựng tái lập

Trong dự án Spring Boot, các plugin, starter và thư viện bắc cầu có thể tạo thành một dependency graph lớn. Một khai báo trong `build.gradle` không nhất thiết cho biết **phiên bản cuối cùng** mà Gradle chọn. Đồng thời, ngay cả khi version được chọn giữ nguyên, nội dung JAR tải từ repository vẫn có thể khác với artifact mà nhóm đã phê duyệt.

Gradle giải quyết hai vấn đề đó bằng hai cơ chế khác nhau:

1. **Dependency locking** lưu **selected versions** sau dependency resolution, theo từng configuration. Lock state giữ graph ổn định giữa các lần build, giúp phát hiện hoặc ngăn việc phiên bản dependency bị thay đổi ngoài quy trình phê duyệt.
2. **Dependency verification** kiểm tra **tính nguyên vẹn/xuất xứ** của artifacts và metadata được Gradle tải thông qua checksum (ví dụ SHA-256) và, khi có, chữ ký PGP được tin cậy.

| Câu hỏi | Locking | Verification |
| --- | --- | --- |
| `spring-core` thực tế được chọn version nào? | Lưu và áp dụng resolved version. | Không tự chọn version. |
| Một dependency bắc cầu âm thầm đổi version? | Giúp phát hiện/ngăn graph drift dựa trên lock state. | Chỉ có thể chấp nhận artifact mới nếu verification policy có metadata phù hợp. |
| Cùng version nhưng JAR bytes bị thay? | **Không xác minh được bytes.** | So checksum/chữ ký để phát hiện sai khác. |
| Cấu hình chính | `dependencyLocking`, `--write-locks`, `--update-locks`. | `gradle/verification-metadata.xml`, `--write-verification-metadata`. |
| File cần lưu vào Git | `gradle.lockfile` của các project được khóa. | `gradle/verification-metadata.xml` và public keyring nếu dùng PGP. |
| Không thay thế | Kiểm tra hash, lỗ hổng bảo mật, runtime tests. | Version locking, vulnerability scanning, provenance của chính source ứng dụng. |

**Kết luận:** khóa phiên bản và xác minh file là hai lớp phòng vệ **phối hợp**, không phải hai tên gọi của cùng một tính năng. Để build thực sự có thể tái lập, còn phải kiểm soát Gradle Wrapper, plugin versions, JDK/toolchain, repository, input của build, package output và quy trình CI.

### 1.1. Bài học sử dụng môi trường nào?

Ví dụ dùng **Gradle Groovy DSL**, **Java 17**, **Spring Boot 3.3.13** và **Gradle Wrapper 8.10.2** làm một bộ phiên bản minh họa. Không coi chúng là phiên bản mới nhất tại thời điểm học. Khi áp dụng cho dự án thật, cần chọn phiên bản được tổ chức hỗ trợ, kiểm chứng compatibility và repository policy.

Ta xây **một multi-project Gradle build** với hai modules:

~~~text
repro-demo
├── core: Java library nội bộ
│   └── commons-lang3: external dependency
└── app: Spring Boot Web app
    ├── core: project dependency
    └── spring-boot-starter-web: Spring MVC và web runtime
~~~

Endpoint `GET /state` của app gọi code trong core, core dùng `StringUtils.capitalize` của Commons Lang. Do đó bài kiểm chứng không chỉ đòi Spring Boot startup mà phải nạp được **dependency nội bộ và dependency bắc cầu** thực sự.

## 2. Khái niệm nền: requested version, selected version, artifact bytes

### 2.1. Từ khai báo đến resolved graph

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

`3.+` là **dynamic version**: hôm nay có thể chọn một bản 3.x, tương lai repository có bản mới thì resolved version có thể đổi. Tương tự, dù yêu cầu một version cố định, Gradle constraints, platform/BOM hoặc conflict resolution có thể chọn version khác trên một configuration cụ thể.

Phân biệt:

- **Requested version**: version hoặc range mà build script/dependency metadata yêu cầu.
- **Selected version**: version thực sự được chọn sau resolution.
- **Artifact bytes**: nội dung thật của JAR/POM/module metadata tải từ repository.
- **Runtime classpath**: những dependencies mà module cần khi chạy.
- **Packaged classpath**: những dependencies thực sự được đưa vào Spring Boot executable JAR, thường dưới `BOOT-INF/lib`.

Dependency locking bảo vệ **selected versions**. Dependency verification bảo vệ **artifact bytes/identity theo trust metadata**. Cả hai không tự kiểm tra executable archive đã đóng đúng hoặc endpoint chạy đúng.

### 2.2. Dynamic khác changing dependencies

**Dynamic version** như `3.+` hoặc `latest.release` có thể được giải quyết thành một version mới; lockfile hữu ích để giữ selected version ổn định.

**Changing dependency**, đặc biệt `-SNAPSHOT` hoặc module được đánh dấu `changing = true`, có thể bị publish lại **cùng tọa độ version nhưng bytes khác**. Theo hướng dẫn Gradle, dependency locking **không phù hợp làm cơ chế bảo đảm tính tái lập cho changing versions**. Dùng immutable release artifact, quản lý internal repository/provenance và có quy trình xác minh riêng.

Điều này không có nghĩa cứ tạo verification XML là snapshot tự an toàn: dependency verification của Gradle không xử lý các changing artifacts giống immutable release files; đừng dựa vào hai cơ chế này để bảo vệ việc ghi đè snapshot mà thiếu chính sách repository.

### 2.3. Checksum không phải vulnerability scan

- SHA-256 so file tải về với **digest đã phê duyệt**. Nếu một kẻ tấn công thay nội dung sau đó, checksum mismatch giúp phát hiện.
- Nếu ngay từ đầu bạn bootstrap checksum từ file **đã bị đầu độc**, checksum mới có thể khớp file độc. Vì vậy **trust establishment và review** là điều bắt buộc.
- PGP signature giúp xác minh signer/key theo quy tắc tin cậy, không chỉ so bytes. Không phải thư viện nào cũng được ký.
- Artifact có hash và signature đúng vẫn có thể chứa CVE/license issues. Cần công cụ kiểm tra bảo mật/SBOM riêng.

## 3. Dự án Spring Boot đa module hoàn chỉnh

### 3.1. Cây file

~~~text
repro-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── verification-metadata.xml     (sinh sau khi bootstrap)
├── core/
│   ├── build.gradle
│   ├── gradle.lockfile               (sinh sau khi ghi lock state)
│   └── src/main/java/com/example/core/LibraryMessage.java
└── app/
    ├── build.gradle
    ├── gradle.lockfile               (sinh sau khi ghi lock state)
    ├── src/main/java/com/example/app/ReproApplication.java
    └── src/test/java/com/example/app/ReproApplicationTest.java
~~~

Các lockfiles và verification metadata **chưa tồn tại ở bước đầu**; Gradle sinh chúng bằng command tương ứng. Wrapper `gradlew`, `gradlew.bat`, `gradle-wrapper.jar` phải được tạo/lưu đúng qua Gradle tooling, không tự dựng file giả để chạy ví dụ.

### 3.2. Root `settings.gradle`

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'repro-demo'
include('core', 'app')
~~~

`include` đăng ký project, **không** tự tạo dependency app → core. `pluginManagement.repositories` dùng cho external plugins, còn `dependencyResolutionManagement.repositories` dùng để giải quyết library dependencies. Trong doanh nghiệp, phải dùng approved mirrors/repositories và xác thực đúng; repository order ảnh hưởng nguồn cung ứng artifact.

### 3.3. Root `build.gradle`

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
~~~

`apply false` giữ plugin version được chọn ở root mà **chưa áp Spring Boot plugin vào root hoặc core**. Khi app áp Boot plugin, Gradle tạo `bootJar`; core vẫn tạo plain library `jar`. Version plugin phải được quản lý/kiểm tra riêng, vì `lockAllConfigurations()` trên project **không tự khóa mọi buildscript/plugin classpath**.

### 3.4. `core/build.gradle`: library, implementation và locking

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

Core dùng Commons Lang trong method body, **không lộ kiểu Commons trong public API**. Vì vậy `implementation` là lựa chọn đúng với Java Library plugin: app consumer không cần Commons trên compile API classpath chỉ vì core dùng nó nội bộ, nhưng Commons **vẫn truyền tới runtime graph** của app.

`lockAllConfigurations()` bật locking cho mọi **resolvable configurations** của core. Nó không lập tức tạo lockfile; cần chạy các tasks với `--write-locks`.

### 3.5. `app/build.gradle`: application và locking

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

`implementation project(':core')` khai báo actual project dependency. `io.spring.dependency-management` phối hợp Spring Boot plugin để quản lý version starter/test libraries; BOM không tự thay thế **lockfile** và không tự thêm Commons vào graph.

Test-only dependencies không được đưa vào executable Boot JAR bình thường. `core` tạo library JAR, app BootJar đưa core và Commons Lang vào nested runtime libraries theo graph resolution.

### 3.6. `core/src/main/java/com/example/core/LibraryMessage.java`

~~~java
package com.example.core;

import org.apache.commons.lang3.StringUtils;

public final class LibraryMessage {
    private LibraryMessage() {
    }

    public static String label() {
        return StringUtils.capitalize("locked");
    }
}
~~~

`StringUtils.capitalize("locked")` trả Java String `"Locked"`. Module này không có `main()` và không phải Spring Boot application. Nếu Commons Lang bị loại khỏi runtime classpath, method có thể gây `NoClassDefFoundError` khi được gọi.

### 3.7. `app/src/main/java/com/example/app/ReproApplication.java`

~~~java
package com.example.app;

import com.example.core.LibraryMessage;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReproApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReproApplication.class, args);
    }

    @GetMapping("/state")
    public String state() {
        return "dependency " + LibraryMessage.label();
    }
}
~~~

Chạy đúng thì `GET /state` trả body `dependency Locked`: request thực thi app → core → Commons Lang. Điều này sẽ giúp kiểm chứng **packaged runtime** sau khi lock và verify dependencies.

### 3.8. Test JUnit 5/MockMvc

`app/src/test/java/com/example/app/ReproApplicationTest.java`:

~~~java
package com.example.app;

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
class ReproApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void stateUsesCoreAndCommonsLang() throws Exception {
        mvc.perform(get("/state"))
           .andExpect(status().isOk())
           .andExpect(content().string("dependency Locked"));
    }
}
~~~

Test này dùng MockMvc với Spring test context; **không khởi động HTTP server trên port 8080**. Nó chứng minh mapping và code path khi chạy trên **test runtime classpath**. Phải kiểm tra thêm `java -jar` vì packaged runtime classpath có thể khác test classpath.

### 3.9. Wrapper version và Java toolchain

Một giá trị minh họa trong `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
~~~

Wrapper distribution version nên được pin, cùng binary/script wrapper được kiểm soát. Khi chính sách yêu cầu, xác minh Gradle distribution SHA-256 và nguồn cung cấp. `java.toolchain` đặt Java 17, nhưng máy/CI vẫn phải có JDK phù hợp hoặc cấu hình provisioning hợp lệ. Dependency verification **không** tự thay thế việc kiểm tra Gradle distribution và JDK.

## 4. Bật dependency locking theo đúng phạm vi

### 4.1. `lockAllConfigurations` có tác dụng gì?

Hai build scripts ở trên dùng:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Gradle bật locking trên các configurations thuộc **project đó** có khả năng resolve. Configurations không resolvable không tự trở nên resolvable. Một lockfile ghi lại selected versions gắn với những configurations thực sự đã được resolve.

Nếu chỉ muốn khóa một configuration, có thể dùng (lựa chọn khác, không phải bổ sung cần thiết khi đã `lockAllConfigurations`):

~~~groovy
configurations {
    runtimeClasspath {
        resolutionStrategy.activateDependencyLocking()
    }
}
~~~

Trong dự án nhiều module, không nên mặc định chỉ khóa root project: `core` và `app` có dependency graphs/configurations riêng.

### 4.2. Tạo lockfiles lần đầu

Từ root project, sau khi bảo đảm build script và repositories tin cậy:

~~~bash
./gradlew --version
./gradlew projects

# Resolve các configurations trong từng subproject và ghi lock state
./gradlew :core:dependencies :app:dependencies --write-locks

# Chạy build/test thật, đồng thời ghi các lock states phát sinh
# từ configurations do tasks hoặc plugins resolve.
./gradlew :app:build --write-locks
~~~

`--write-locks` chỉ ghi state cho **configurations đã được resolve** trong invocation. Trong Gradle multi-project, lệnh `./gradlew dependencies --write-locks` có thể chỉ chạy task của **root project**, không đủ bao phủ app/core. Vì vậy ví dụ gọi task có project path rõ ràng.

Lệnh `:app:build` có thể tạo thêm resolutions qua task compilation/test/bootJar; việc chạy thêm giúp quan sát coverage. Không có nghĩa mọi custom configuration chưa bao giờ sử dụng cũng đã được khóa. Hãy xem thực tế plugin/tasks của dự án.

### 4.3. File được tạo và ý nghĩa

Thông thường có:

~~~text
core/gradle.lockfile
app/gradle.lockfile
~~~

Một đoạn **minh họa format** của một lockfile, không phải nội dung phải copy-paste:

~~~text
# This is a Gradle generated file for dependency locking.
org.apache.commons:commons-lang3:3.14.0=compileClasspath,runtimeClasspath
empty=annotationProcessor
~~~

Đoạn này chỉ cho thấy dạng `group:name:version=configuration1,configuration2`. Lockfile thực tế của **core** và **app** có thể khác danh sách configurations: core dùng Commons ở compile/runtime; app có thể chỉ thấy dependency ấy trên runtime do Gradle `java-library` tách `api` và `implementation`. Spring Boot BOM/constraints cũng có thể khiến selected version khác requested version `3.14.0`. Đọc **file do Gradle tạo**, không viết assertion dựa trên ví dụ.

### 4.4. Tại sao phải commit lockfiles?

Lockfile là một **input được review** của project. Khi cả team và CI checkout cùng commit, Gradle biết bộ versions nào đã được chấp nhận. Nếu mỗi lần CI đều chạy `--write-locks`, CI có thể tự viết lại state, làm mất tín hiệu drift.

Commit lockfiles vào Git cùng build scripts. Đừng bỏ chúng vào `.gitignore` hay đối xử như caches. Chỉ lưu lock state của những projects/configurations cần thiết, không copy lockfile của repository khác.

## 5. Bật chế độ STRICT sau khi có baseline

Gradle có `LockMode.STRICT`. Khi một configuration đã được đánh dấu locking nhưng **chưa có lock state**, strict mode có thể fail thay vì cho resolution qua không có khóa.

Sau khi sinh, kiểm tra và commit lockfiles, thay phần locking trong **core và app** thành:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
~~~

Chạy:

~~~bash
# Không ghi lại lock state trong luồng build bình thường
./gradlew :core:build :app:build

# Quan sát selected graph của app
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath --dependency commons-lang3
~~~

Nếu strict báo thiếu lock state của một configuration, phải xác định configuration đó do plugin/task nào tạo, có cần khóa không và tạo state theo workflow được review. **Không** sửa bằng cách tự xóa strict ở CI rồi tiếp tục phát hành.

### 5.1. Khi build script thay version mà lockfile giữ phiên bản cũ

Giả sử sửa declaration Commons Lang sang một release version khác **nhưng chưa cập nhật lockfile**. Gradle có thể giữ selected version đã khóa hoặc fail do không thể thỏa constraints; không nên đoán một thông báo lỗi cụ thể nếu chưa chạy. Làm đúng:

1. Dùng `dependencyInsight` và dependency graph để phân tích requested/selected versions.
2. Quyết định có thực sự muốn nâng version không.
3. Nếu có, cập nhật lock state có chủ đích.
4. Review những transitive versions thay đổi.
5. Rerun tests, packaging và executable smoke.
6. Commit thay đổi trong một PR cùng lý do nâng.

### 5.2. Locking không có nghĩa “mỗi dependency chỉ có một version trên tất cả configurations”

Gradle resolve từng configuration: `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath` và configurations do plugins tạo. Một module có thể được chọn version khác tùy constraints/context. Lockfile ghi selected versions **theo configuration**, không phải một global number độc lập.

Nếu bạn thêm integration-test source set/configuration mới, cần xác định configuration có được đánh dấu locking và đã có lock state không, đặc biệt khi STRICT đã bật.

## 6. Cập nhật lock state có kiểm soát

### 6.1. `--write-locks`: ghi lại trạng thái được resolve

Khi nâng một bộ dependencies có kế hoạch:

~~~bash
./gradlew :core:dependencies :app:dependencies --write-locks
./gradlew :app:build --write-locks
~~~

Sau đó review diff:

~~~bash
git diff -- core/gradle.lockfile app/gradle.lockfile
~~~

`--write-locks` có thể viết lại lock state của mọi configuration được resolve; vì thế **không đưa vào CI check bình thường**. Dùng trên upgrade branch, theo sau bởi test, security review và commit.

### 6.2. `--update-locks`: cập nhật một số modules

Để hướng resolution cho một dependency cụ thể:

~~~bash
./gradlew :core:dependencies :app:dependencies \
  --update-locks org.apache.commons:commons-lang3
~~~

`--update-locks` nhận module notation `group:name` (có thể phân tách nhiều module bằng dấu phẩy). Nó dùng lock state còn lại làm input, cho phép những module mục tiêu được chọn lại theo **requested constraints và repositories hiện hành**, rồi cập nhật state liên quan.

**Không tự nâng mọi thứ lên latest:** nếu version declaration vẫn cố định ở `3.14.0` và không có constraints khác, lệnh này không tự biến nó thành một version mới. Bạn phải sửa declaration/BOM/version catalog phù hợp **trước**, rồi update locks. Nếu nâng Commons cũng ảnh hưởng transitives, review toàn bộ lockfile diff.

### 6.3. Version catalog/BOM không thay locking

- `gradle/libs.versions.toml` (nếu dự án có) tập trung aliases và requested versions.
- Spring Boot BOM/platform quản lý version constraints cho dependencies trong graph.
- `gradle.lockfile` ghi selected versions thực sự **sau resolution**.

Một alias không tự thêm dependency; một BOM không tự đóng băng toàn bộ graph của mỗi configuration. Vì vậy một project có catalog/BOM vẫn có giá trị khi dùng locking.

### 6.4. Tránh changing dependencies trong release

Đừng coi `org.example:some-lib:1.0-SNAPSHOT` là immutable chỉ vì nó xuất hiện trong lockfile. Với version có thể bị ghi đè, phải có chính sách publication, artifact immutability, build ID/digest hoặc provenance riêng. Locking rất hữu ích cho dynamic **version selection**, nhưng **không khóa nội dung cùng coordinate**.

## 7. Dependency verification: file `verification-metadata.xml` và trust model

Gradle có thể verify JAR/ZIP, POM, Gradle Module Metadata, plugin artifacts và các external artifacts khác mà Gradle dependency resolution xử lý. File cấu hình đặt tại:

~~~text
gradle/verification-metadata.xml
~~~

File này áp dụng cho **toàn build** gồm subprojects và những plugin artifacts được Gradle xử lý theo quy tắc verification. Với included builds, Gradle có cơ chế chia sẻ chính sách verification trong invocation; không tự giả định một included build hoàn toàn độc lập khỏi trust metadata của build gọi nó.

**Giới hạn quan trọng:** verification không kiểm tra **mã source/`core.jar` được build nội bộ** như một downloaded external artifact. Nó cũng không phải bằng chứng thư viện an toàn trước CVE, license hay malicious behavior khi digest baseline đã bị đầu độc.

### 7.1. Tạo SHA-256 baseline

Sau khi kiểm tra repositories và resolved dependencies đang đáng tin, từ root:

~~~bash
./gradlew --write-verification-metadata sha256 \
  :core:dependencies :app:dependencies :app:build
~~~

Gradle sẽ tạo hoặc bổ sung thông tin ở `gradle/verification-metadata.xml`. Flag này có thể resolve **các resolvable configurations** để thu thập artifacts, không chỉ dependency của một task đơn lẻ. Tuy nhiên các downloads nằm ngoài Gradle dependency engine hoặc artifacts chỉ xuất hiện trong workflow khác vẫn cần xem phạm vi coverage.

**Cảnh báo:** bootstrap tin vào artifacts mà repository cung cấp **lúc đó**. Nếu repository/mirror đã bị thay artifact, checksum sinh ra vẫn có thể khớp file không an toàn. Người học phải review coordinates, source, hashes và critical dependencies trước khi chấp nhận XML.

### 7.2. Cấu trúc của verification metadata

File Gradle tạo thường có:

- `<configuration>`: chính sách xác minh metadata và signatures.
- `<components>`: các tọa độ module.
- `<component group="..." name="..." version="...">`: dependency cụ thể.
- `<artifact name="...">`: JAR/POM/metadata file của module.
- `<sha256 value="..."/>`: digest SHA-256 thực đã ghi nhận.
- `<trusted-keys>` hoặc `<pgp>` khi sử dụng chữ ký.

Một đoạn **minh họa về cấu trúc**, không phải XML hoàn chỉnh dùng được:

~~~xml
<components>
    <component group="org.apache.commons" name="commons-lang3" version="3.14.0">
        <artifact name="commons-lang3-3.14.0.jar">
            <!-- SHA-256 phải được tạo từ artifact thực và được review. -->
        </artifact>
    </component>
</components>
~~~

Không viết giả một digest 64 ký tự để làm ví dụ “có thể chạy”: chữ ký/checksum là dữ liệu tin cậy, không phải chỗ điền tùy ý. Không tự copy một `verification-metadata.xml` của project khác vì file phải khớp **artifact và repository policy của build đang dùng**.

### 7.3. Verification được bật khi nào?

Khi file verification metadata có hiệu lực tồn tại ở root, Gradle dùng các quy tắc của file để verify artifacts. **Chỉ tạo một file XML rỗng hay tối giản** mà chưa có digest cho downloaded dependencies có thể làm build fail ngay vì thiếu verification metadata.

Sau bootstrap/review, chạy bình thường:

~~~bash
./gradlew :core:build :app:build
~~~

Nếu một artifact không có checksum yêu cầu, Gradle có thể báo thiếu metadata. Nếu bytes khác expected digest, nó có thể fail với checksum mismatch. Hai trường hợp đó **không xử lý giống nhau**.

### 7.4. Verification mode: strict, lenient, off

| Mode | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `strict` | Fail khi gặp verification violation. | **Mặc định và khuyến nghị cho CI/release.** |
| `lenient` | Ghi nhận lỗi nhưng tiếp tục build. | Chỉ dùng điều tra tạm thời có kiểm soát. |
| `off` | Bỏ qua kiểm tra. | Không dùng như cách phát hành để né checksum mismatch. |

Ví dụ **chỉ chẩn đoán**:

~~~bash
./gradlew --dependency-verification lenient :app:build
~~~

Không tuyên bố build đã “secure” nếu chạy ở mode lenient/off. Với CI cần hiển thị thông tin chi tiết, `gradle.properties` có thể chứa:

~~~properties
org.gradle.dependency.verification.console=verbose
~~~

Đây chỉ là cấu hình cách in báo cáo, **không giảm hoặc tăng** quy tắc trust.

## 8. SHA-256 và PGP signature: nên sử dụng thế nào?

### 8.1. SHA-256 giúp kiểm tra integrity

SHA-256 tính digest từ bytes của artifact. Mỗi artifact được Gradle kiểm tra với expected digest đã ghi. Một file khác bytes sẽ có digest khác với xác suất rất cao, khiến Gradle báo vi phạm.

**Tuy nhiên:** checksum sinh ra từ một artifact không đáng tin vẫn có thể trở thành một “baseline sai”. Cần xác minh nguồn xuất bản, repository, quyền sửa artifact, critical coordinates và thay đổi trong PR.

Không dùng MD5/SHA-1 làm security checksum chính cho các build hiện đại do hạn chế về collision resistance; ưu tiên SHA-256/SHA-512.

### 8.2. PGP giúp kiểm tra signer/provenance

PGP signature có thể xác minh một artifact được ký bởi key có fingerprint được tin cậy. Cần kiểm tra:

- Chữ ký `.asc` có sẵn và hợp lệ không?
- Public key fingerprint có khớp publisher được xác nhận qua kênh độc lập không?
- Key có bị revoke/rotate/compromise không?
- Artifact không có signature có checksum fallback đã được review không?

Có thể bootstrap thêm PGP bằng:

~~~bash
./gradlew --write-verification-metadata sha256,pgp \
  :core:dependencies :app:dependencies :app:build
~~~

Khi dùng PGP keyring, lưu **public keyring** theo hướng dẫn Gradle nếu policy cần, ví dụ `gradle/verification-keyring.keys`. **Không** commit private signing key. Tự động bootstrap signatures/keys không thay được việc reviewer quyết định signer có thực sự đáng tin không.

### 8.3. Verification không phải SCA/CVE scan

Một library phiên bản cũ có CVE vẫn có thể có checksum hoàn toàn hợp lệ. Vì vậy Gradle verification bảo vệ supply chain **trong phạm vi đã được cấu hình**, còn vulnerability analysis, license compliance, SBOM và patch management phải là gates riêng.

## 9. Cập nhật verification metadata đúng cách

Khi dependency graph thay đổi (thêm starter, nâng Spring Boot, nâng plugin hoặc một thư viện bắc cầu), artifact hoặc metadata mới có thể không nằm trong XML đã commit.

Quy trình:

1. **Xác minh lý do dependency mới xuất hiện.** Đọc PR build scripts, dependency report, source repository và publisher.
2. **Phân biệt missing metadata với incorrect checksum.** Missing có thể là bước cập nhật bình thường; mismatch là dấu hiệu cần điều tra.
3. **Chỉ sau khi nguồn được xác minh**, chạy lại `--write-verification-metadata sha256` hoặc các lựa chọn tương ứng với policy chữ ký.
4. **Xem diff** `gradle/verification-metadata.xml`: component mới, artifact JAR/POM, digest, signing keys.
5. Đối chiếu **lockfile diff** để biết selected versions/configurations đã đổi như thế nào.
6. Chạy lại build **không có flag ghi verification**, kiểm tra JUnit/packaging/runtime.
7. Commit declaration + lockfiles + verification metadata trong cùng PR, có reviewer nếu chính sách yêu cầu.

Lệnh cập nhật minh họa:

~~~bash
./gradlew --write-verification-metadata sha256 \
  :core:dependencies :app:dependencies :app:build

git diff -- gradle/verification-metadata.xml \
            core/gradle.lockfile app/gradle.lockfile

# Build kiểm tra bình thường sau khi đã review state
./gradlew :app:build
~~~

**Không** chạy bootstrap để tự chấp nhận checksum mới ngay sau **checksum mismatch**. Nếu file bytes đã khác expected digest, có thể repository bị rewrite, mirror trả file không đồng nhất, cache bị sửa hoặc có hành vi tấn công. Phải điều tra và ghi nhận quyết định trust trước khi thay baseline.

### 9.1. Vì sao file XML lớn dần?

Gradle bootstrap verification metadata thường có tính **incremental**: bổ sung entries mới, không tự biết một artifact cũ chắc chắn không còn được dùng trong bất kỳ configuration/feature nào. Vì thế XML có thể chứa entries cũ. Dọn dẹp khi có cơ sở, không xóa toàn bộ chỉ để diff nhỏ.

### 9.2. Không lạm dụng trusted-artifacts wildcard

Gradle cho phép khai báo trusted artifact exceptions trong những trường hợp có chủ ý. Một rule trust tất cả group/artifact hoặc mọi sources JAR làm giảm coverage của security gate. Nếu phải dùng exception, nên giới hạn file/group/reason theo policy và có thời hạn review; không dùng wildcard toàn bộ để làm CI xanh.

## 10. Quy trình kết hợp locking và verification từ đầu

### Bước A — hiểu runtime graph

~~~bash
./gradlew --version
./gradlew projects
./gradlew :core:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath --dependency commons-lang3
~~~

App runtimeClasspath phải chứa project `:core` và Commons Lang transitive, cũng như các Spring Boot runtime dependencies. Đừng lấy `compileClasspath` của app làm bằng chứng Commons Lang không cần: Java Library `implementation` có thể không lộ tới consumer compile nhưng vẫn đến runtime.

### Bước B — bật locking và tạo lock state

Chèn `dependencyLocking { lockAllConfigurations() }` vào project build scripts, sau đó:

~~~bash
./gradlew :core:dependencies :app:dependencies --write-locks
./gradlew :app:build --write-locks
~~~

Review `core/gradle.lockfile`, `app/gradle.lockfile`. Khi state đầy đủ, có thể bật `LockMode.STRICT` và chạy build bình thường.

### Bước C — tạo verification metadata từ trusted repositories

~~~bash
./gradlew --write-verification-metadata sha256 \
  :core:dependencies :app:dependencies :app:build
~~~

Review XML, repository/publisher metadata và hash/keys. Commit baseline.

### Bước D — CI chỉ kiểm tra, không ghi lại baseline

~~~bash
./gradlew --no-daemon :core:clean :app:clean :app:build
~~~

**Không thêm** `--write-locks` hoặc `--write-verification-metadata` vào command CI thường lệ. Nếu CI có thể tự refresh baseline, một dependency graph thay đổi ngoài dự kiến có thể bị chấp nhận mà không qua review.

### Bước E — kiểm tra artifact và hành vi runtime

~~~bash
./gradlew :app:bootJar

# Kiểm tra đúng executable JAR; tên dự kiến của ví dụ
jar tf app/build/libs/app-0.1.0.jar

# Terminal 1: khởi động app đóng gói
java -jar app/build/libs/app-0.1.0.jar --server.port=18085
~~~

Tại terminal thứ hai, khi server ready:

~~~bash
curl -i http://localhost:18085/state
~~~

Kỳ vọng **HTTP 200**, body chính xác `dependency Locked`.

Trong executable archive, kỳ vọng:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/app/ReproApplication.class
BOOT-INF/lib/core-0.1.0.jar
BOOT-INF/lib/commons-lang3-<selected-version>.jar
BOOT-INF/lib/spring-boot-<selected-version>.jar
...
~~~

`<selected-version>` là ký hiệu để đọc, không phải tên file cụ thể để chạy shell. Version thật phải lấy từ `jar tf`/`dependencyInsight`. Đừng deploy nhầm `*-plain.jar` do Gradle `jar` tạo.

**Lý do có bước runtime:** locking/verification không bảo đảm Spring Boot `bootJar` đã đóng đủ các libraries. Nếu test classpath có Commons Lang nhưng packaged runtime thiếu nó, MockMvc test có thể pass trong khi `java -jar` fail. Chỉ chạy chính artifact mới phát hiện được sự khác biệt ấy.

## 11. Một bảng QA dành cho code review và CI

| Bằng chứng | Ý nghĩa | Điều không thể kết luận |
| --- | --- | --- |
| `build.gradle` và `settings.gradle` | Requested graph, plugin/registry policy. | Selected versions cuối hoặc artifact integrity. |
| `core/gradle.lockfile`/`app/gradle.lockfile` | Selected versions và locked configurations đã được duyệt. | Artifact bytes đúng hoặc không có CVE. |
| `gradle/verification-metadata.xml` | Artifact checksums/PGP trust policy. | Runtime dependencies có đóng đủ vào JAR không. |
| `:app:dependencies --configuration runtimeClasspath` | Runtime graph đang được resolution chọn. | JAR binary đã thực chứa đúng file không. |
| `:app:dependencyInsight` | Vì sao version được chọn, constraints/conflict. | Checksum/artifact provenance. |
| `jar tf app.jar` | Các entries thực tế trong executable JAR. | Endpoint/job thực chạy được hay không. |
| JUnit/MockMvc report | Test assertions trên test runtime đạt. | Packaged runtime cũng đạt. |
| `java -jar` và HTTP smoke | Executable JAR hoạt động trên môi trường thử. | Security/compliance/production-ready toàn diện. |

### 11.1. Files cần commit trong ví dụ

~~~text
settings.gradle
build.gradle
core/build.gradle
app/build.gradle
core/gradle.lockfile
app/gradle.lockfile
gradle/verification-metadata.xml
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
gradlew
gradlew.bat
~~~

Các source Java, test và resource cũng phải được commit. **Không commit toàn bộ `.gradle/caches`** như thay thế lockfiles/verification XML; caches là dữ liệu môi trường, có thể được tái tạo từ nguồn tin cậy theo policy.

### 11.2. Khi nâng một dependency

Một PR nâng version nên chứa:

1. Diff requested version trong build script/version catalog.
2. Diff **selected versions** trong lockfiles (chỉ files/configurations liên quan).
3. Diff checksum/signature metadata sau khi reviewer xác nhận repository/publisher đáng tin.
4. Test report cho core/app và relevant integration tests.
5. Archive inspection và packaged smoke.
6. Ghi chú compatibility/CVE/license, nếu ảnh hưởng.
7. Artifact/provenance identification theo chính sách phát hành.

Một PR chỉ thay source code không cần tự động chạy bootstrap metadata; lệnh ghi baseline chỉ dùng khi có lý do.

## 12. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Khả năng nguyên nhân | Cách giải quyết có căn cứ |
| --- | --- | --- |
| Không có `app/gradle.lockfile` sau lệnh khóa. | Chưa bật locking ở app, chỉ chạy task dependencies ở root, configuration chưa resolve. | Kiểm tra `app/build.gradle` và gọi `:app:dependencies --write-locks`; xem output thật. |
| Strict mode báo thiếu lock state. | Configuration được đánh dấu locked nhưng chưa có state. | Tạo baseline theo workflow, review và commit; không tắt strict vô điều kiện. |
| Thay version nhưng vẫn dùng version cũ. | Lock state/BOM/constraints đang giữ selected version. | Dùng `dependencyInsight`, sửa declaration có chủ đích rồi `--update-locks`. |
| Một starter mới làm thay đổi hàng loạt locks. | BOM/transitive graph/selected versions đổi. | Review full dependency report và diff, kiểm tra compatibility trước commit. |
| Lockfile có Commons Lang nhưng `bootJar` thiếu nó. | Task/classpath/exclusions khác runtime graph. | Kiểm tra `runtimeClasspath` và `bootJar.classpath`, đừng chỉ nhìn lockfile. |
| Gradle plugin version đổi nhưng project lockfile không đổi. | Plugin/buildscript classpath không thuộc project lock state. | Quản lý plugin versions và verification; xem buildscript locking nếu dùng legacy plugins. |
| Build fail “checksum is missing”. | Artifact mới chưa có metadata đã duyệt. | Xác minh source, update verification metadata có review. |
| Build fail “checksum expected differs from actual”. | Bytes lệch trust baseline, có thể repository rewrite/cache/tamper. | Dừng phát hành và điều tra; không rebootstrap mù. |
| PGP key chưa được trust. | Key mới/không xác minh được signer. | Xác minh fingerprint qua publisher độc lập rồi update policy. |
| Chữ ký PGP sai. | Artifact/signature/key mismatch. | Xử lý như integrity incident, không dùng lenient/off để release. |
| Local pass nhưng CI fail verification. | Repository/mirror/plugin version/cache khác. | So exact coordinates, repository order, Gradle Wrapper, metadata và logs. |
| `--offline` fail dù lockfile đầy đủ. | Lockfile **không chứa JAR bytes**, cache offline thiếu artifact. | Chuẩn bị trusted cache hoặc mirror; đừng coi locks là binary storage. |
| `-SNAPSHOT` giữ version nhưng bytes khác. | Changing dependency; locking không cố định content. | Dùng immutable releases và repository/provenance policy. |
| Gradle Wrapper/JDK khác gây output khác. | Locking/verification không khóa môi trường. | Pin Wrapper/JDK/toolchain, archive reproducibility settings nếu cần bit-for-bit. |
| XML verification metadata dài và nhiều entries cũ. | Bootstrap incremental, không auto-prune. | Review cleanup có chủ đích; không xóa toàn bộ metadata. |
| Runtime báo `NoClassDefFoundError`. | Thiếu transitive dependency trong packaged runtime, sai scope/exclusion. | So graph và `BOOT-INF/lib`; sửa dependency config, không đổi hash để chữa. |
| Test báo `NO-SOURCE` dù build success. | Test source path/Gradle task wiring sai. | Kiểm tra `src/test/java`, JUnit, `useJUnitPlatform` và report. |

### 12.1. Phân biệt lớp lỗi

1. **Declaration:** build script yêu cầu gì?
2. **Resolution:** Gradle chọn version và dependency graph nào?
3. **Locking:** state có đúng configuration và selected versions không?
4. **Verification:** artifact bytes/signature có đúng trust metadata không?
5. **Packaging:** `bootJar` có đúng nested dependencies không?
6. **Runtime:** Java app đã gọi core/Commons Lang thành công chưa?
7. **Security:** artifact có CVE/license/trust policy đáp ứng yêu cầu chưa?

Mỗi lớp cần bằng chứng riêng. Đừng “chữa” checksum mismatch bằng cách sửa HTTP port, hoặc chữa thiếu JAR runtime bằng cách tắt verification.

## 13. Thử nghiệm sai lệch có kiểm soát

### 13.1. Thử thay selected version

Trên một branch học tập, sửa Commons Lang requested version. Không chạy `--write-locks` ngay. Chạy dependency report và build để xem lock state ảnh hưởng resolution thế nào; khi muốn chấp nhận upgrade, dùng `--update-locks org.apache.commons:commons-lang3`, review diff và chạy lại test. Nếu version mới có artifact chưa được verify, phải xem metadata/publisher trước khi cập nhật XML.

### 13.2. Thử thêm artifact chưa có checksum

Trên một branch riêng, thêm một dependency hợp lệ đã được kiểm tra nguồn nhưng chưa có trong XML. Trong strict mode có thể gặp thiếu verification metadata. Xem report, ghi rõ artifact nào thiếu, rồi chỉ thêm digest sau review. Không sử dụng `--dependency-verification off` như đường tắt.

### 13.3. Tình huống checksum mismatch

Không cần phá cache JAR để giả lập tấn công. Đọc một log mẫu “expected SHA-256 khác actual” và trả lời:

- Tọa độ nào và file nào bị ảnh hưởng?
- Digest đã phê duyệt đến từ commit/reviewer nào?
- Repository/mirror nào trả bytes hiện tại?
- Có checksum hoặc signature đáng tin từ publisher không?
- Có cần đổi mirror, kiểm tra cache hoặc báo security incident không?
- Ai quyết định trust baseline mới, và có bằng chứng gì?

**Quy tắc:** mismatch phải được điều tra trước khi có bất kỳ thay đổi trust policy nào.

### 13.4. Bản dựng cùng dependencies nhưng bytes JAR đầu ra khác

Lockfiles/verification metadata giống nhau không tự làm binary build **bit-for-bit reproducible**. JDK toolchain, compiler options, generated timestamps, archive order, file timestamps, locale/time zone và task inputs có thể ảnh hưởng output. Với yêu cầu cao, cần cấu hình reproducible archives, deterministic generation và so file hashes sau khi build trong môi trường kiểm soát.

## 14. Tình huống multi-module và included builds

Trong demo, `core` và `app` là **subprojects** của cùng build. Mỗi project có lockfile cho resolvable configurations đã khóa. Verification metadata root là chính sách chung của build, bao gồm external artifacts/plugins mà Gradle verification hỗ trợ.

Nếu repository có `build-logic` là **included build** tạo convention plugins:

- Không tự giả định `core/gradle.lockfile` của main build khóa cả build-logic classpath.
- Xác định Gradle settings/included build dependency locking riêng nếu build-logic có external runtime/plugin dependencies.
- Dependency verification có scope toàn build invocation theo tài liệu Gradle, nên plugin/build-logic artifacts có thể yêu cầu cập nhật root verification metadata.
- Không dùng đường tắt “trust tất cả com.mycompany” nếu internal artifact repository cũng có nguy cơ bị overwrite/tamper; chọn phạm vi trust theo policy.
- Dùng bản Gradle phù hợp với build scripts của chính included build.

Một project dependency nội bộ `project(':core')` được tạo từ source trong cùng build, không phải một artifact external có SHA-256 trong verification metadata theo cùng cơ chế. Khi publish core sang registry ngoài, consumer sẽ có nhu cầu xác minh **published artifact** theo trust policy của mình.

## 15. Quy trình CI và upgrade PR

Đối với CI thông thường, command nên **chỉ kiểm tra**, không tái tạo file trust/locks:

~~~bash
# CI checkout đã chứa lockfiles và verification-metadata.xml được review
./gradlew --no-daemon --version
./gradlew --no-daemon :core:clean :app:clean :app:build
./gradlew --no-daemon :app:dependencies --configuration runtimeClasspath
jar tf app/build/libs/app-0.1.0.jar
~~~

Nếu pipeline thêm `java -jar` smoke test, phải launch HTTP server có lifecycle/timeout phù hợp, gọi `GET /state` rồi dừng process. Đừng chạy `java -jar` foreground trong CI và chờ web server tự thoát. Chỉ test classpath/`BUILD SUCCESSFUL` chưa đủ chứng minh packaged JAR chạy được.

Trong PR nâng dependencies, reviewer nên có **bốn diff/bằng chứng**: requested versions, resolved lock state, verification metadata/key trust, và test/packaged runtime. Không chấp nhận auto-updated lockfiles/XML mà thiếu giải thích thay đổi.

## 16. Bài thực hành và tiêu chí đạt

### Bài A — tạo lock state

1. Dựng đủ files Gradle/Java ở mục 3 với Wrapper phù hợp.
2. Chạy `./gradlew :core:dependencies :app:dependencies --write-locks`.
3. Kiểm tra `core/gradle.lockfile` và `app/gradle.lockfile`, so các configurations.
4. Chạy `./gradlew :app:build --write-locks` để bao phủ task-induced resolutions.
5. Review diff rồi bật `LockMode.STRICT` khi state đã đủ.
6. Chạy lại `./gradlew :app:build` **không có flag ghi locks**.
7. Giải thích selected versions khác requested versions khi graph/BOM conflict.

### Bài B — tạo verification metadata

1. Kiểm tra repositories, plugin versions và dependency sources đáng tin.
2. Chạy `./gradlew --write-verification-metadata sha256 :core:dependencies :app:dependencies :app:build`.
3. Mở `gradle/verification-metadata.xml`; xác định entries của Commons Lang và các Spring library/plugin artifacts.
4. Giải thích hash của file được tải khác lockfile version ở chỗ nào.
5. Review XML, commit nó cùng lockfiles.
6. Chạy build strict bình thường và quan sát report.
7. Nếu thêm PGP, phân biệt trusted signer và checksum fallback.

### Bài C — nâng dependency đúng quy trình

1. Đổi requested Commons Lang version trong `core/build.gradle` ở branch riêng.
2. Quan sát resolution/locking behavior trước khi cho phép update.
3. Dùng `--update-locks org.apache.commons:commons-lang3`, xem selected versions và diff.
4. Xác minh artifact mới và cập nhật XML qua bootstrap có kiểm soát.
5. Chạy tests, packaged JAR smoke, và review compatibility/security.
6. Hoàn nguyên nếu chỉ là bài thí nghiệm; không phát hành artifact chưa review.

### Bài D — chứng minh sản phẩm

1. Chạy `./gradlew :app:bootJar`.
2. Kiểm tra `jar tf app/build/libs/app-0.1.0.jar` có core JAR, Commons Lang JAR và Boot runtime libraries ở `BOOT-INF/lib`.
3. Chạy `java -jar app/build/libs/app-0.1.0.jar --server.port=18085`.
4. Gọi `curl -i http://localhost:18085/state`, kỳ vọng HTTP 200 và body `dependency Locked`.
5. Ghi test report, exact artifact path, lockfiles và verification metadata đã được review.

### Checklist

- [ ] Phân biệt dependency locking với dependency verification.
- [ ] Hiểu requested version, selected version và artifact bytes là ba khái niệm khác nhau.
- [ ] Biết `lockAllConfigurations()` phải đi cùng bước ghi lock state có kiểm soát.
- [ ] Có lockfiles ở đúng subprojects, không chỉ root task.
- [ ] Biết khi nào dùng `LockMode.STRICT` và tại sao cần baseline trước.
- [ ] Biết `--write-locks` khác `--update-locks`, và vì sao không dùng trong CI thường lệ.
- [ ] Giải thích dynamic version và changing/`-SNAPSHOT` không giống nhau.
- [ ] Tạo/review `gradle/verification-metadata.xml` với SHA-256.
- [ ] Không tự trust một checksum mismatch hoặc dùng lenient/off để phát hành.
- [ ] Nêu vai trò của PGP signature/public key và hạn chế nếu bootstrap thiếu review.
- [ ] Hiểu BOM/version catalog không tự thay lockfiles.
- [ ] Biết Gradle plugin artifact/Wrapper/JDK cần được quản lý ngoài project dependency locks.
- [ ] So `runtimeClasspath` với `BOOT-INF/lib`; có core và Commons Lang transitive.
- [ ] Có JUnit/MockMvc report và packaged `java -jar` smoke test.
- [ ] Biết verification không thay CVE scanning/SBOM, testing hoặc deterministic packaging.

**Tiêu chí hoàn tất:** một repo có Gradle Wrapper được kiểm soát, lockfiles của core/app, root verification metadata đã review, build thường chạy mà không tự ghi baseline, runtime graph và Boot executable JAR đầy đủ dependencies, JUnit tests đạt và `GET /state` của JAR thật trả `dependency Locked`. Nếu thiếu JDK, repository access hoặc chưa thực hiện smoke, ghi rõ hạng mục chưa kiểm chứng, không đánh dấu PASS dựa trên dự kiến.

## Tài liệu tham khảo chính thức

- [Gradle 8.10.2 — Locking Dependency Versions](https://docs.gradle.org/8.10.2/userguide/dependency_locking.html)
- [Gradle 8.10.2 — Dependency Verification](https://docs.gradle.org/8.10.2/userguide/dependency_verification.html)
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/securing_dependencies.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot 3.3 — Gradle Plugin Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.3 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)

**Ghi nhớ:** lockfile giúp không âm thầm đổi **resolved versions**, còn verification metadata giúp xác định **artifact bytes/PGP signature có phù hợp trust baseline**. Cả hai phải có quy trình tạo, review, commit và kiểm tra trên CI; kết quả cuối cùng vẫn cần kiểm chứng qua actual executable JAR và runtime behavior.