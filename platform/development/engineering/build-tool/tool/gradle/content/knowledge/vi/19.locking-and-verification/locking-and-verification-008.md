# Phân biệt khóa phiên bản, xác minh artifact và checksum Wrapper trong Gradle

## 1. Mục tiêu và tình huống thực tế

Một dự án Java dùng Gradle có thể được build thành công hôm nay nhưng thất bại tuần sau dù source không đổi. Có ít nhất ba nguyên nhân rất khác nhau:

1. **Dependency graph thay đổi**: một dependency dùng version động như `3.+` được resolve sang phiên bản mới, hoặc dependency bắc cầu thay đổi khi cập nhật BOM/plugin.
2. **Artifact bị thay đổi**: cùng tọa độ `group:name:version`, nhưng JAR/POM thực tế được trả về không còn khớp byte được đội ngũ tin cậy.
3. **Bản phân phối Gradle bị thay đổi**: `gradlew` tải một file `gradle-...-bin.zip` không khớp SHA-256 chính thức, hoặc chính `gradle-wrapper.jar` bị thay thế.

Ba loại vấn đề cần **ba lớp kiểm soát**:

- **Dependency locking** → cố định *module versions được chọn* trong một resolvable configuration.
- **Dependency verification** → kiểm tra *checksum/chữ ký của artifacts và metadata* mà Gradle dependency engine tải.
- **Wrapper distribution checksum** → kiểm tra *file ZIP phân phối Gradle* được tải bởi Wrapper theo `distributionSha256Sum`.

Đây là ba cơ chế **bổ sung chứ không thay thế nhau**. Một dự án có `gradle.lockfile` không tự xác minh tính toàn vẹn byte của JAR. Có `verification-metadata.xml` không tự ghim version dependency. Có `distributionSha256Sum` không tự kiểm tra thư viện của ứng dụng hay bản thân file `gradle-wrapper.jar`.

Sau bài học, bạn có thể:

1. Giải thích chính xác đối tượng, thời điểm áp dụng, file cấu hình và giới hạn của cả ba cơ chế.
2. Thiết lập khóa phiên bản cho Gradle project Java 17 và sinh `gradle.lockfile` đúng configuration.
3. Dùng `--write-locks`, `--update-locks` và `dependencyInsight` trong quy trình cập nhật dependency.
4. Tạo, review, commit `gradle/verification-metadata.xml` với SHA-256 và tùy chọn PGP signatures.
5. Phân biệt **checksum integrity** với **signature authenticity**, tránh tin mù quáng vào kết quả bootstrap.
6. Đặt checksum đúng cho Gradle Wrapper distribution qua `distributionSha256Sum`.
7. Biết vì sao checksum của `gradle-wrapper.jar` và checksum của distribution ZIP **khác nhau**.
8. Thiết kế kiểm soát CI, xử lý checksum mismatch, khóa bị lệch và quy trình nâng cấp an toàn.
9. Nêu được những điều cả ba lớp chưa giải quyết: compatibility, vulnerability, nguồn tin cậy ban đầu, dynamic/changing content, kết quả build do chính dự án tạo.

Bài nằm trong nhóm **Khóa và xác minh** của Build Tool Gradle, ưu tiên Kotlin DSL và ví dụ Java 17. Các tên version và hash minh họa không phải tuyên bố đó là lựa chọn mới nhất cho một hệ thống đang vận hành.

## 2. Sơ đồ tư duy: ba lớp bảo vệ ba đối tượng

~~~text
Git repository
├── settings.gradle.kts / build.gradle.kts
│     └── dependency declarations, repositories, configurations
│
├── app/gradle.lockfile
│     └── Lock: resolved component VERSIONS trong app configurations
│
├── gradle/verification-metadata.xml
│     └── Verify: JAR, POM, .module, plugin artifacts tải qua Gradle
│
└── gradle/wrapper/
      ├── gradle-wrapper.properties
      │     ├── distributionUrl=.../gradle-X.Y-bin.zip
      │     └── distributionSha256Sum=<SHA-256 của ZIP này>
      └── gradle-wrapper.jar
            └── File thực thi bootstrap; cần kiểm tra riêng
~~~

Khi chạy:

~~~bash
./gradlew :app:run
~~~

trình tự khái quát là:

~~~text
[1] Hệ điều hành chạy gradlew / gradlew.bat
      |
      v
[2] gradle-wrapper.jar khởi động
      |
      +--> nếu cần tải ZIP Gradle:
      |       distributionSha256Sum kiểm tra ZIP được tải
      |
      v
[3] Bản phân phối Gradle được khởi động
      |
      +--> resolve configuration:
      |       dependency locking kiểm tra selected versions
      |       dependency verification kiểm tra artifacts/metadata
      |
      v
[4] Task compile, test, package, run
      |
      +--> Tính đúng của chương trình vẫn cần tests/scan/runtime checks
~~~

**Chính thứ tự này giải thích vì sao dependency verification không thể thay thế Wrapper checksum:** Wrapper tải và chạy Gradle **trước khi** phần lớn build logic/dependency management hoạt động.

### 2.1. Bảng so sánh

| Câu hỏi | Dependency locking | Dependency verification | Wrapper checksum |
| --- | --- | --- | --- |
| Khóa/kiểm tra cái gì? | Module version được resolve | Byte artifact/metadata hoặc chữ ký | ZIP Gradle distribution |
| File chính | `gradle.lockfile` theo project | `gradle/verification-metadata.xml` ở root build | `gradle/wrapper/gradle-wrapper.properties` |
| Cơ chế | Lock state được dùng khi resolve graph | SHA-256/SHA-512 và/hoặc PGP | SHA-256 cho ZIP |
| Thiết lập | `dependencyLocking { ... }` | Sinh/review metadata file | `distributionSha256Sum=...` |
| Đối tượng | Dependencies của cấu hình bật locking | Dependencies/plugins Gradle tải qua dependency engine | ZIP được Wrapper tải |
| Có pin version? | Có | Không | Pin byte của một distribution được cấu hình |
| Phát hiện cùng version nhưng JAR bị đổi? | Không | Có, nếu được kiểm soát bởi verification metadata | Không |
| Phát hiện Gradle ZIP bị thay? | Không | Không | Có khi Wrapper download và kiểm tra |
| Phát hiện Gradle Wrapper JAR bị thay? | Không | Không | **Không; cần kiểm tra JAR riêng** |
| Chứng minh thư viện an toàn/compatible? | Không | Không | Không |

Đọc bảng theo nguyên tắc: **cùng tên “verify/checksum” không có nghĩa cùng scope**.

## 3. Dependency version locking là gì?

Gradle chọn dependency theo cấu hình (`compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, ...), giữa các yêu cầu direct/transitive, BOM/platform, rich versions, variants và rules. Nếu có version động như:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.+")
}
~~~

thì `3.+` có thể resolve thành những version 3.x khác nhau qua thời gian, khi repository có bản mới. Cũng có trường hợp dependency bắc cầu thay đổi sau khi update một module trực tiếp hoặc BOM.

**Dependency locking** lưu những module/version đã resolve thành *lock state*. Trong lần chạy sau, Gradle áp dụng lock versions và kiểm tra graph hiện tại khớp state.

Điểm cần nhớ:

- Lock là theo **configuration của từng project**, không phải một danh sách file JAR chung cho cả monorepo.
- Lock state chứa **tọa độ module version**, không chứa checksum của file JAR.
- Lock không tự bật chỉ vì trong project có một file tên `gradle.lockfile`; cần cấu hình locking theo cách Gradle hỗ trợ.
- Với những configuration có locking bật, Gradle dùng locked versions như các **strict constraints** trong resolution và kiểm tra module thừa/thiếu so với lock state theo lock mode.
- Lock không tự chạy test, không đảm bảo binary compatibility hoặc artifact chưa bị thay đổi.
- Gradle khuyến nghị **không dựa vào locking để xử lý changing dependencies** như `-SNAPSHOT` có thể đổi nội dung tại cùng tọa độ.

### 3.1. “Khóa version” không phải “khóa toàn bộ mọi thứ”

Một tọa độ Maven như:

~~~text
org.apache.commons:commons-lang3:3.14.0
~~~

chỉ nói group, artifact và version. Nếu repository hoặc mirror trả lại byte khác với byte được phê duyệt cho tọa độ đó, lockfile vẫn có thể **khớp hoàn toàn**. Để kiểm tra nội dung JAR và POM, cần dependency verification.

Ngược lại, verification metadata có thể xác minh một artifact `3.15.0` hợp lệ nhưng không biết nhóm dự án có muốn nâng từ `3.14.0` sang `3.15.0` hay không. Để kiểm soát thay đổi version, cần lockfile hoặc một cơ chế version policy tương đương.

## 4. Ví dụ Java 17 chạy được: khóa dependency versions

Tạo một multi-project Gradle đơn giản để minh họa rõ nơi đặt lockfile.

### 4.1. Cấu trúc

~~~text
lock-verify-demo/
├── settings.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/demo/App.java
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
└── gradlew.bat
~~~

Ví dụ giả định đã có Gradle Wrapper phù hợp và có JDK 17 (hoặc một toolchain provisioner được cấu hình). Nếu khởi tạo mới, tạo wrapper theo quy trình dự án trước khi chạy các lệnh.

**settings.gradle.kts**

~~~kotlin
rootProject.name = "lock-verify-demo"
include(":app")
~~~

**app/build.gradle.kts**

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    // Version cố định trong ví dụ để kết quả dễ giải thích.
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

application {
    mainClass.set("demo.App")
}

// Áp dụng locking cho các configurations của project :app.
// Chỉ những configurations thực sự được resolve mới có lock state.
dependencyLocking {
    lockAllConfigurations()
}
~~~

**app/src/main/java/demo/App.java**

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String result = StringUtils.capitalize("gradle") + " ready";
        System.out.println(result);
    }
}
~~~

Đây là Java 17 hợp lệ. Cách dùng `StringUtils.capitalize("gradle")` minh họa module Commons Lang đã được đặt trên runtime/compile classpath.

### 4.2. Chạy thử

Linux/macOS:

~~~bash
./gradlew :app:run --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --console=plain
~~~

**Stdout chính xác do App.main in ra** (bên cạnh log Gradle):

~~~text
Gradle ready
~~~

Task `:app:run` có thể build/compile trước khi chạy Java. Không dùng số lượng dòng log `BUILD SUCCESSFUL` làm bằng chứng chính, vì chúng phụ thuộc phiên bản Gradle và tình trạng cache.

### 4.3. Tạo lock state lần đầu

Một lệnh ngắn gọn để resolve runtime configuration của `:app` và ghi lock:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --write-locks \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath --write-locks --console=plain
~~~

Với configuration được resolve và locking bật, Gradle tạo/cập nhật:

~~~text
app/gradle.lockfile
~~~

Nội dung có thể gồm các dòng dạng:

~~~text
# Đây là ví dụ diễn giải, không chép nguyên văn thay file Gradle sinh.
org.apache.commons:commons-lang3:3.14.0=runtimeClasspath
~~~

Tên configuration/sắp xếp/ký hiệu khác có thể xuất hiện nếu bạn chạy thêm các configurations hoặc Gradle version thay đổi. **Không tự viết lại lockfile** cho giống ví dụ; để Gradle sinh file thật.

### 4.4. Vì sao lockfile nằm trong app thay vì root?

Vì trong ví dụ `dependencyLocking` được khai báo tại **`app/build.gradle.kts`**, và configuration `runtimeClasspath` thuộc project `:app`. Lock state mới sẽ lưu trong **`app/gradle.lockfile`**. Root project có thể có lockfile riêng nếu được cấu hình locking và resolve các configuration của root.

Trong multi-project build, chạy lệnh:

~~~bash
./gradlew dependencies --write-locks
~~~

ở root **không bảo đảm** khóa mọi configuration của mọi subproject. Task `dependencies` thường chạy trên project được nhắm đến; cần chỉ rõ `:app:dependencies` hoặc resolve chính những configurations của từng subproject cần locking.

### 4.5. Đưa lockfile vào Git

`gradle.lockfile` nên được commit cùng `build.gradle.kts`, vì nó là **quyết định version đã được nhóm chấp thuận**. Khi review pull request, diff lockfile giúp nhìn thấy những transitive modules bị thêm/bớt/nâng.

Lockfile không phải secret. Tuy vậy, nó có thể để lộ tên artifact nội bộ; với repository công khai cần theo chính sách thông tin của tổ chức.

## 5. Bật locking đúng scope

### 5.1. Bật cho tất cả project configurations

Trong `build.gradle.kts` của project cần khóa:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Điều này áp dụng cho **project configurations**, nhưng **không tự bật locking cho buildscript classpath**. Các configuration không thể resolve không tạo lock state hữu dụng dù được đánh dấu.

### 5.2. Chỉ bật cho một configuration

Nếu chỉ quan tâm runtime của app:

~~~kotlin
configurations {
    runtimeClasspath {
        resolutionStrategy.activateDependencyLocking()
    }
}
~~~

Đây là mẫu thay thế cho `lockAllConfigurations`, không cần đồng thời dùng cả hai. Dùng khóa theo configuration khi build có những configuration đặc thù hoặc luôn thay đổi mà không thích hợp để khóa.

### 5.3. Bật khóa buildscript classpath (cơ chế riêng)

Nếu dự án sử dụng legacy `buildscript { dependencies { classpath(...) } }`, Gradle cho phép:

~~~kotlin
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}
~~~

Các lock của buildscript có thể nằm trong `buildscript-gradle.lockfile`, khác file project dependencies thông thường. Không nhầm cơ chế này với việc đặt `gradle.lockfile` của ứng dụng.

**Chú ý:** Plugin được resolve trong `plugins {}` có những quy tắc resolution riêng. Dependency verification có scope rộng với plugins, trong khi locking của một project không tự ghim mọi plugin version của build. Hãy xác định rõ nơi khai báo plugin versions và buildscript classpath.

### 5.4. Lock mode

Gradle có các lock mode như `DEFAULT`, `STRICT`, `LENIENT`.

- `DEFAULT`: khi có lock state, kiểm tra graph được resolve khớp lock; có thể cho phép configuration chưa có lock state bắt đầu trong những tình huống theo quy tắc mặc định.
- `STRICT`: ngoài việc kiểm tra lock state hiện có, có thể fail nếu configuration cần khóa **chưa có lock state**.
- `LENIENT`: ít chặt hơn đối với việc dependency thêm/bớt, chủ yếu giữ tính ổn định cho dynamic version và những behavior tương ứng.

Một mẫu code cho project dùng policy strict:

~~~kotlin
import org.gradle.api.artifacts.dsl.LockMode

dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
~~~

**Cần đặt import ở đầu file Kotlin DSL**, không ở giữa script. Đây là cấu hình tùy chọn sau khi đã tạo lock state đầy đủ; bật strict ngay khi chưa có lockfile có thể khiến tác vụ resolve thất bại. Không chuyển qua LENIENT chỉ để “cho CI xanh” khi chưa hiểu dependency nào đổi.

## 6. Cập nhật dependency và lockfile có kiểm soát

Giả sử một ngày cần nâng Commons Lang theo đánh giá của nhóm. Việc sửa `implementation("...:3.14.0")` sang version cao hơn **không đủ** nếu lockfile cũ vẫn đang khóa graph.

Quy trình:

1. Xác định version mục tiêu bằng release notes/compatibility/security review.
2. Sửa dependency hoặc BOM/platform phù hợp.
3. Chạy thao tác cập nhật lock state.
4. Review toàn bộ diff lockfile, kể cả transitive modules.
5. Chạy unit/integration/smoke tests trên graph mới.
6. Commit cùng nhau source declaration và lockfile.

Cập nhật toàn bộ configurations được resolve trong một lệnh:

~~~bash
./gradlew :app:dependencies --write-locks --console=plain
~~~

**Quan trọng:** `--write-locks` chỉ ghi state của những configurations **thật sự được resolve** trong execution đó. Không suy luận rằng một lệnh đã khóa test/annotationProcessor/implementation của mọi subproject nếu chúng chưa được resolve.

### 6.1. Cập nhật chọn lọc module

Gradle có lựa chọn `--update-locks`, ví dụ:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --update-locks org.apache.commons:commons-lang3 \
  --console=plain
~~~

Nó cho phép module được chỉ định thay đổi trong quá trình resolution của configuration đó; các lock entries còn lại vẫn tham gia như input. Có thể cập nhật một danh sách ngăn bởi dấu phẩy, ví dụ `org.apache.commons:commons-lang3,org.slf4j:slf4j-api`.

Những dependency bắc cầu **vẫn có thể đổi** nếu resolution rules bắt buộc; “update một module” không hứa diff sẽ chỉ một dòng. **Review diff thật** trước khi merge.

### 6.2. Lỗi lock mismatch

Các tình huống:

- Thêm một dependency nhưng không cập nhật lockfile.
- Xóa module nhưng lockfile vẫn chứa entry của graph cũ.
- Thay declared version khiến constraints không còn tương thích với locked version.
- Chạy một configuration mới trong strict mode nhưng chưa có lock state.

Cách xử lý không phải xóa lockfile và commit lại mù quáng. Phân tích `dependencies` và `dependencyInsight`, xác minh version thay đổi có chủ đích, rồi cập nhật và review lock state.

### 6.3. Dynamic/changing dependencies

Một lockfile giúp ghim **module version** từ dynamic selector như `3.+`. Nhưng dependency dạng changing, điển hình `-SNAPSHOT`, có thể đổi byte tại **cùng một module version**. Gradle cảnh báo khi dùng locking với changing dependencies; locking **không phải công cụ bảo đảm nội dung thay đổi không âm thầm**.

Khi cần reproducibility cao, ưu tiên release versions bất biến, repository được kiểm soát và artifact verification thích hợp.

## 7. Dependency verification kiểm tra cái gì?

**Dependency verification** của Gradle dùng metadata để đối chiếu file tải về với những giá trị đáng tin:

- **Checksum**: kiểm tra nội dung file có đúng byte như giá trị đã được phê duyệt hay không.
- **Signature**: kiểm tra chữ ký số của artifact với khóa công khai được tin cậy; hỗ trợ đánh giá provenance (ai ký artifact), với điều kiện tin đúng khóa.

File chính ở root:

~~~text
gradle/verification-metadata.xml
~~~

Khi file này có mặt và cấu hình đúng, Gradle thực hiện verification trong dependency management engine đối với các artifacts được resolve theo phạm vi hỗ trợ.

Ví dụ những đối tượng có thể được xác minh:

- JAR/ZIP của dependency từ Maven/Ivy repository.
- POM, Ivy descriptors, Gradle Module Metadata (`.module`) khi cấu hình verify metadata.
- Artifact của Gradle plugins được resolve qua dependency engine.
- Một số artifacts từ các API dependency resolution nâng cao.

**Không tự dùng cơ chế này để kiểm tra:**

- Bản phân phối Gradle ZIP mà Wrapper tải.
- Chính `gradle/wrapper/gradle-wrapper.jar`.
- File JAR được custom task trong chính build tạo ra.
- Changing dependencies (`SNAPSHOT` variants) theo giới hạn verification được Gradle nêu trong tài liệu.

Khi hỏi “Artifact nào được verify?”, phải xác định **nó đi qua dependency engine hay cơ chế tải khác**.

### 7.1. Checksum là tính toàn vẹn, không tự là tính xác thực

SHA-256 tạo digest 256 bit của byte file. Nếu JAR đổi một byte, checksum sẽ khác với digest được lưu từ bản tin cậy.

Nhưng nếu bạn lần đầu tải JAR từ repository đã bị chiếm quyền, sau đó **tin luôn** vào SHA-256 của chính JAR đó, bạn chỉ đang ghi lại checksum của một artifact có thể đã bị thay thế. Checksum không tự nói ai là nhà xuất bản hợp lệ.

Vì vậy cần nguồn **expected checksum đáng tin**, review dependency và bảo vệ repository/CI. Với chữ ký, cần xác thực đúng **public-key fingerprint** được phê duyệt chứ không tin một khóa bất kỳ vừa tải về.

### 7.2. Signature hỗ trợ provenance, vẫn cần trust model

Gradle có thể đọc PGP `.asc` signatures khi repository công bố, lấy public keys và so sánh với những trusted key IDs trong metadata/keyring. Chữ ký chỉ hữu ích khi khóa ký được **xác minh đúng tác giả**.

Đối với security cao, có thể kết hợp **SHA-256 + PGP** khi đủ dữ liệu. Không phải mọi artifact có `.asc` hợp lệ; với file không có signature, cấu hình checksum vẫn cung cấp integrity check.

## 8. Tạo verification metadata bằng Gradle

Đối với dự án `lock-verify-demo` ở mục 4, sau khi Wrapper và repositories hợp lệ, bạn có thể bootstrap verification metadata.

### 8.1. Sinh SHA-256

Từ root project:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

PowerShell:

~~~powershell
.\gradlew.bat --write-verification-metadata sha256
~~~

Gradle sẽ cố resolve các configurations phù hợp và sinh/cập nhật:

~~~text
gradle/verification-metadata.xml
~~~

Lệnh này là **bootstrap**. Dữ liệu được sinh phải được review: Gradle chỉ tính hash của bytes mà môi trường đang nhận được, **không tự chứng minh bytes đó an toàn**.

### 8.2. Sinh checksum và chữ ký (khi publisher có PGP)

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Cơ chế này có thể tạo checksum và thông tin liên quan PGP signatures/keys. Không giả định mọi artifact đều ký số; trường hợp chữ ký không có/cannot verify cần đọc báo cáo và xác minh nguồn tin cậy.

Một chiến lược cẩn trọng:

1. Bootstrap checksum cho dependencies đã được review.
2. Xác minh checksum với nguồn độc lập tin cậy nếu có.
3. Thêm signature verification nếu artifact cung cấp signatures.
4. Verify fingerprint của khóa ký theo thông tin publisher đáng tin.
5. Commit metadata và keyring thích hợp cùng source changes.

Theo tài liệu Gradle, có thể bootstrap SHA-256 **trước**, sau đó mở rộng sang PGP để bảo đảm có checksums cho cả những artifacts được ký, không dựa vào chữ ký đơn độc.

### 8.3. Cấu trúc XML minh họa

Một entry **có tính minh họa** (không dùng để chạy trực tiếp do checksum là placeholder):

~~~xml
<components>
  <component
      group="org.apache.commons"
      name="commons-lang3"
      version="3.14.0">
    <artifact name="commons-lang3-3.14.0.jar">
      <sha256 value="REPLACE_WITH_TRUSTED_64_HEX_SHA256"/>
    </artifact>
  </component>
</components>
~~~

Trong file Gradle thật, cấu trúc còn có root `<verification-metadata>` và namespace/schema được Gradle sinh, thường có phần `<configuration>` và nhiều artifact/metadata entries. **Không chép snippet này thành một verification-metadata.xml “hoàn chỉnh”**. Giá trị placeholder không phải checksum hợp lệ; hãy dùng file Gradle generate rồi review mỗi thay đổi.

Một checksum 64 ký tự hex áp cho **một file cụ thể**. SHA-256 của `.jar` không phải SHA-256 của `.pom`, `.module`, source JAR hoặc Javadoc JAR. Mỗi artifact có bytes riêng và cần thông tin verification tương ứng nếu được tải.

### 8.4. Phạm vi của metadata trong multi-project

Một file ở **root build** kiểm soát dependencies của root, subprojects, `buildSrc` và những phạm vi included builds theo quy tắc Gradle. Đây không phải một file mới tự tạo cho từng subproject như `gradle.lockfile`.

Điều đó lý giải cách kiểm soát trong monorepo:

~~~text
app/gradle.lockfile             (lock của :app)
service/gradle.lockfile         (lock của :service)
gradle/verification-metadata.xml (verification chung)
~~~

Nếu có included build, cần đọc các quy tắc override/precedence của Gradle để đảm bảo metadata policy áp dụng như kỳ vọng. Không copy verification file vào từng module tùy ý.

## 9. Cập nhật verification metadata an toàn

Một ngày bạn nâng Commons Lang hoặc thêm JUnit, có thể xuất hiện artifact mới chưa được whitelist trong XML.

Workflow được khuyến nghị:

1. Chọn dependency mới qua change request và kiểm tra nguồn/release notes.
2. Sửa dependency declarations hoặc BOM/platform.
3. Cập nhật lockfiles cần thiết.
4. Chạy `--write-verification-metadata sha256` để nhận checksums mới **trên môi trường tin cậy**.
5. Review diff `gradle/verification-metadata.xml` và tìm checksums của artifact mới.
6. So sánh với nguồn đáng tin độc lập nếu có; kiểm tra nguồn Maven repository, project maintainer, signatures, key fingerprints.
7. Chỉ duyệt metadata sau khi đã xác nhận.
8. Chạy build với verification bật trong CI sạch.
9. Commit dependency declarations, lockfiles và verification metadata **trong cùng thay đổi đã review**.

### 9.1. Đừng “accept all checksums” khi verification fail

Nếu log cho biết artifact có SHA-256 khác expected:

- Có thể repository/mirror bị thay byte.
- Có thể Gradle chọn **artifact classifier hoặc metadata khác**, không phải file bạn tưởng.
- Có thể nhà phát hành đã republish một version không bất biến, điều này cần điều tra.
- Có thể mirror/proxy/cache trả nội dung sai.
- Cũng có thể **bootstrap baseline trước đó đã sai**.

Không cập nhật XML bằng cách copy checksum từ file hiện tại chỉ để CI xanh. Việc làm đó vô hiệu hóa mục đích của verification nếu chưa xác minh tính đúng của artifact.

### 9.2. Tránh dùng MD5/SHA-1 cho bảo đảm hiện đại

Gradle vẫn có thể hỗ trợ các thuật toán cũ để tương thích, nhưng SHA-256 hoặc SHA-512 là lựa chọn phù hợp hơn cho **cryptographic integrity** hiện đại. MD5 và SHA-1 có các vấn đề va chạm đã biết; không dùng làm biện pháp an ninh chính.

### 9.3. Sinh preview metadata

Gradle có thể tạo một phiên bản preview khi dùng dry-run:

~~~bash
./gradlew --write-verification-metadata sha256 help --dry-run
~~~

Tùy phiên bản Gradle, kết quả được ghi vào:

~~~text
gradle/verification-metadata.dryrun.xml
~~~

Đó là bản dùng để review, **không phải file metadata đang được áp dụng thay** `verification-metadata.xml`. Lưu ý dry-run không thực hiện task actions nên có thể **không phát hiện những dependencies chỉ được resolve khi action chạy**.

### 9.4. Updating metadata không tự xóa entries cũ

Quá trình tạo metadata thường mang tính incremental, có thể giữ checksums của các version không còn được dùng. Khi nâng cấp định kỳ, review và làm sạch entries cũ theo policy; không xóa các entries còn được module hoặc job khác dùng.

## 10. Dependency verification: signatures, trusted keys, keyring

Khi dùng PGP, `verification-metadata.xml` có thể chứa trusted key fingerprints; một keyring trong `gradle/` có thể được commit nếu chính sách cho phép.

Các khái niệm:

- **Signature `.asc`**: file chữ ký được publisher công bố cùng artifact.
- **Public key**: dùng để kiểm tra chữ ký; public key có thể được tải từ key server.
- **Trusted fingerprint**: danh tính khóa ký mà tổ chức đã xác minh theo kênh độc lập.
- **Keyring**: tập khóa công khai có thể được dùng offline/giảm phụ thuộc key server.
- **Ignored key**: cấu hình bỏ qua khóa không đáng tin/không khả dụng; nếu bỏ qua thì vẫn cần checksum tin cậy cho artifact để bảo vệ integrity.

Một tổ chức có thể dùng Gradle CLI để tạo/export keys:

~~~bash
./gradlew --write-verification-metadata pgp,sha256 --export-keys
~~~

Không nhất thiết phải tạo keyring ngay ở bài thực hành đầu tiên; bước này chỉ phù hợp khi dự án quản lý và review PGP trust. **Public key không phải private signing key**: không bao giờ commit private keys/secrets vào repository.

### 10.1. “Có chữ ký” chưa đủ

Một artifact có PGP signature hợp lệ nhưng được ký bằng một public key **không được xác minh là của nhà phát hành** thì tính xác thực vẫn chưa được đảm bảo. Tương tự, một checksum khớp với giá trị tự sinh từ file bị nhiễm độc ở lần tải đầu không chứng minh file tốt.

Một trust model thực tế có thể kết hợp:

- HTTPS repository đáng tin.
- Artifact checksums được review.
- Fingerprints xác minh qua thông báo publisher/channels độc lập.
- Dependency locking để version không trôi.
- Dependabot/renovation/review policy.
- Security scans và integration tests.

## 11. Giới hạn của dependency verification

Cơ chế này rất hữu ích, nhưng không hứa bảo vệ mọi file mà một task có thể download.

### 11.1. Những ngoại lệ quan trọng

- **Changing modules** như Maven `SNAPSHOT` không được xác minh như những immutable release artifacts thông thường theo giới hạn Gradle mô tả.
- **Artifacts sinh nội bộ bởi build tasks** (file JAR tự tạo trong build) không phải external dependency mà engine tải từ repository, nên không dùng verification metadata để đảm bảo chúng.
- **Wrapper distribution ZIP** được tải trước khi Gradle dependency engine hoạt động.
- **Gradle Wrapper JAR** là binary bootstrap riêng cần kiểm tra chính nó.
- **Mã tùy chỉnh dùng HTTP client/curl** để tải file ngoài API dependency resolution không tự được Gradle dependency verification bảo vệ.
- **Dependency versions chưa được resolve** không tự có artifacts để kiểm tra.
- **Artifact bytes đúng** không chứng minh ứng dụng có behavior đúng hay không có CVE.

### 11.2. Dependency verification khác cache

Gradle cache giữ các artifacts/metadata đã tải để tiết kiệm network và phục vụ offline. Cơ chế verification nhằm kiểm tra artifact theo metadata được tin cậy, nhưng **cách vận hành cache không biến một checksum không đáng tin thành checksum đáng tin**.

Nếu đang điều tra checksum mismatch, phải xác định file/entry bị lỗi, nguồn repository, thông tin tin cậy ban đầu và configuration đang resolve. Không xóa toàn bộ caches hay tắt verification chỉ để bắt đầu lại mà chưa hiểu nguyên nhân.

### 11.3. Dependency verification khác dependency locking

Ví dụ:

~~~text
lockfile:
  commons-lang3 3.14.0

verification-metadata:
  commons-lang3-3.14.0.jar -> SHA-256 A

Repository bị thay:
  commons-lang3-3.14.0.jar -> SHA-256 B
~~~

Lockfile vẫn khớp tên/version, vì `3.14.0` không đổi. **Verification phải phát hiện A khác B** nếu artifact đang được kiểm soát bằng expected checksum A. Đây là tình huống cho thấy hai cơ chế bổ sung nhau.

## 12. Gradle Wrapper và checksum của distribution

Gradle Wrapper gồm:

~~~text
gradlew                         (shell script)
gradlew.bat                     (Windows batch script)
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Khi dùng Wrapper, những file này thường được commit để các thành viên chạy cùng **Gradle distribution version**. Trong properties:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
~~~

Là ví dụ URL distribution cụ thể; phiên bản dự án thực tế có thể khác. `distributionUrl` chọn nguồn và version, **nhưng URL đơn thuần không phải checksum**.

Muốn Wrapper kiểm tra ZIP được tải, thêm:

~~~properties
distributionSha256Sum=REPLACE_WITH_OFFICIAL_64_HEX_SHA256
~~~

**Dòng trên chỉ là cú pháp có placeholder, không phải checksum thực.** Nếu copy nguyên dòng này vào project, verification sẽ không hoạt động đúng. Hãy lấy **giá trị SHA-256 chính thức của đúng file ZIP** từ nguồn tin cậy và thay placeholder bằng chuỗi hex 64 ký tự được xác minh.

### 12.1. Ví dụ file gradle-wrapper.properties cấu trúc

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
distributionSha256Sum=REPLACE_WITH_OFFICIAL_64_HEX_SHA256
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Đây là **mẫu cấu trúc**, không phải file sẵn dùng vì thiếu SHA-256 thật. Việc lựa chọn `-bin.zip` hay `-all.zip` quyết định file cần lấy checksum tương ứng. Checksum của `gradle-8.14.3-bin.zip` **không thể dùng** cho `gradle-8.14.3-all.zip`, dù cùng version Gradle.

### 12.2. Lấy checksum ở đâu?

Ưu tiên nguồn chính thức của Gradle:

- Trang phân phối Gradle có file `.sha256` tương ứng.
- Danh sách distribution checksums chính thức trên `gradle.org`.
- Chính sách nội bộ có mirror đáng tin có thể yêu cầu kiểm tra SHA theo bản chuẩn đã được duyệt.

Không lấy expected SHA-256 **chỉ từ cùng một nguồn không đáng tin đang phát hành ZIP** mà chưa có một kênh xác minh độc lập. Nếu attacker thay được cả ZIP lẫn dòng checksum trên cùng một máy chủ bị chiếm quyền, phép so sánh nội bộ không giúp phát hiện.

### 12.3. Tạo Wrapper checksum qua task

Gradle Wrapper task hỗ trợ chỉ định checksum khi cấu hình distribution. Ví dụ **mẫu lệnh cần thay placeholder bằng giá trị chính thức**:

~~~bash
./gradlew wrapper \
  --gradle-version 8.14.3 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum OFFICIAL_64_HEX_SHA256
~~~

PowerShell phiên bản một dòng:

~~~powershell
.\gradlew.bat wrapper --gradle-version 8.14.3 --distribution-type bin --gradle-distribution-sha256-sum OFFICIAL_64_HEX_SHA256
~~~

Chỉ chạy sau khi `OFFICIAL_64_HEX_SHA256` được thay bằng checksum thật và bạn đã xác nhận đúng Gradle version/distribution. Wrapper task có thể cần chạy lại để cập nhật đầy đủ JAR/scripts khi thay đổi Gradle version, theo hướng dẫn Gradle và policy của dự án.

**Không tự đoán checksum** hoặc tái sử dụng checksum của version khác.

## 13. Một giới hạn quan trọng: Wrapper ZIP chỉ được kiểm tra khi cần download

Theo tài liệu chính thức của Gradle, `distributionSha256Sum` được kiểm tra **khi Wrapper tải distribution chưa có trong cache**. Nếu distribution đã tồn tại trong cache và được reuse, đây **không phải bước quét SHA-256 mọi lần bạn gọi `./gradlew`**.

Suy ra:

- Kiểm tra fresh download từ nguồn tin cậy rất quan trọng.
- Nếu CI dùng image/cache dựng sẵn, không nên giả định mỗi build đang re-hash ZIP bằng Wrapper.
- Cache policy và quyền ghi vào nơi lưu Gradle distributions là một phần của mô hình bảo vệ.
- Nếu cần điều tra nghi ngờ tampering của distribution đã có, cần thực hiện quy trình kiểm tra cache/ZIP hoặc dựng môi trường sạch theo policy, **không chỉ nhìn vào một lần Wrapper chạy thành công**.

### 13.1. `distributionSha256Sum` kiểm tra file gì?

Nó nhắm đến ZIP distribution chỉ định bởi `distributionUrl`. Nó **không kiểm tra**:

- `gradle-wrapper.jar`.
- `gradlew` hoặc `gradlew.bat`.
- JDK được dùng để chạy Gradle.
- JAR/POM dependencies của ứng dụng.
- Plugin artifacts được tải bởi Gradle dependency engine.
- Docker image của CI.

Những đối tượng khác cần kiểm soát độc lập.

### 13.2. Khi đổi bin sang all

Một ví dụ update:

~~~text
Trước: gradle-8.14.3-bin.zip
Sau:   gradle-8.14.3-all.zip
~~~

Dù version `8.14.3` không đổi, **nội dung ZIP khác nhau**. Phải tra checksum riêng của `all.zip`. Nếu copy checksum từ `bin.zip`, lần download mới sẽ báo mismatch. Đừng xóa checksum để “cho tải được”; sửa `distributionUrl` và `distributionSha256Sum` thành **cặp đúng**.

## 14. Wrapper JAR checksum là một lớp kiểm tra khác

File:

~~~text
gradle/wrapper/gradle-wrapper.jar
~~~

là binary Java được thực thi rất sớm để tải/khởi động Gradle. Nếu kẻ tấn công thay nó, các kiểm tra ở giai đoạn sau có thể đã quá muộn.

**Điểm phân biệt bắt buộc:**

~~~text
distributionSha256Sum
  -> SHA-256 của gradle-X.Y-bin.zip / gradle-X.Y-all.zip

Wrapper JAR integrity
  -> checksum/signature của gradle/wrapper/gradle-wrapper.jar
~~~

Chúng là **hai file khác nhau**, có SHA-256 khác nhau và nguồn đối chiếu chính thức khác nhau.

Gradle công bố checksum của Wrapper JAR cho các bản phát hành phù hợp. Có thể kiểm tra thủ công bằng công cụ hash của hệ điều hành, rồi **so với checksum chính thức đúng version**.

### 14.1. Tính hash của Wrapper JAR trên Linux/macOS

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
~~~

Một số môi trường macOS dùng:

~~~bash
shasum -a 256 gradle/wrapper/gradle-wrapper.jar
~~~

Kết quả là **checksum tính được**, chưa chứng minh hợp lệ cho tới khi so sánh với danh sách checksum đáng tin.

### 14.2. Trên Windows PowerShell

~~~powershell
Get-FileHash .\gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256
~~~

So sánh output với checksum chính thức của **Wrapper JAR**, không phải SHA-256 distribution ZIP.

### 14.3. CI verification của Wrapper JAR

Gradle nêu cách tích hợp các hành động kiểm tra Wrapper JAR trong CI. Ví dụ **Gradle Setup action phiên bản v4** hỗ trợ kiểm tra Wrapper JAR như một phần workflow. Tổ chức có thể yêu cầu pin action version theo commit SHA để giảm rủi ro supply chain.

Quan trọng hơn: đừng tin rằng `distributionSha256Sum` đã tự xác minh `gradle-wrapper.jar`. Đây là hiểu nhầm có thể bỏ sót một binary chạy trước build script.

## 15. Ba kịch bản tấn công/sai lệch và cơ chế phát hiện

### Kịch bản A: Dynamic version cập nhật ngoài ý muốn

Hôm qua resolve:

~~~text
commons-lang3:3.+ -> 3.14.0
~~~

Hôm nay repository có phiên bản 3.x mới, graph có thể chọn version khác. Nếu có lock state hợp lệ, Gradle phải giữ **selected version theo lock** cho configuration được khóa.

- **Dependency locking:** giảm rủi ro.
- **Dependency verification:** không quyết định 3.x nào *được phép nâng*; nó chỉ kiểm tra artifacts thuộc scope.
- **Wrapper checksum:** không liên quan.

### Kịch bản B: Cùng version nhưng artifact byte khác

Repository trả JAR cùng `3.14.0` nhưng checksum khác giá trị đã review.

- **Lock:** vẫn có thể khớp, vì version không đổi.
- **Verification:** có thể báo checksum mismatch và từ chối artifact.
- **Wrapper checksum:** không liên quan.

### Kịch bản C: Wrapper tải Gradle ZIP sai byte

Một CDN/proxy/mirror trả file `gradle-X.Y-bin.zip` không khớp official SHA.

- **Lock:** không chạy ở thời điểm này.
- **Dependency verification:** không chạy ở thời điểm này.
- **Wrapper `distributionSha256Sum`:** phát hiện mismatch khi download nếu đã đặt đúng expected checksum.

### Kịch bản D: Chính gradle-wrapper.jar bị thay

Nếu attacker thay binary bootstrap:

- Cả ba cơ chế trên **không tự chứng minh Wrapper JAR là bản chính thức**.
- Cần validation riêng cho Wrapper JAR và bảo vệ quy trình PR/CI.
- Kể cả `gradle-wrapper.properties` chứa SHA đúng, không nên tin một Wrapper JAR đã bị sửa.

### Kịch bản E: JAR đúng nhưng chứa lỗ hổng

Nếu JAR đúng tọa độ, đúng checksum, đúng chữ ký và distribution đúng, ứng dụng **vẫn có thể chứa CVE hoặc lỗi logic**.

- Lock/verification là kiểm soát consistency/integrity.
- Vulnerability scanning, release policy, SCA, SBOM, update cadence và tests vẫn cần thiết.
- “Checksum hợp lệ” không phải nhãn “thư viện an toàn”.

## 16. Ví dụ Java 17: bản chất SHA-256 độc lập với Gradle

Để hiểu checksum, dùng một chương trình Java 17 hoàn chỉnh tính SHA-256 của chuỗi `"abc"` theo UTF-8. Đây **không phải chương trình xác minh Gradle Wrapper**, chỉ minh họa nguyên lý hash byte.

**Sha256Demo.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class Sha256Demo {
    private Sha256Demo() {
    }

    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] data = "abc".getBytes(StandardCharsets.UTF_8);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(data);
        System.out.println(HexFormat.of().formatHex(hash));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac Sha256Demo.java
java Sha256Demo
~~~

**Stdout chính xác:**

~~~text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Nếu byte input thay đổi (kể cả một dấu xuống dòng) thì digest thay đổi. Đó là lý do không thể coi checksum của file ZIP hoặc JAR là checksum của “tên version” hay “nội dung gần giống”; checksum được tính **trên chính những byte cụ thể**.

### 16.1. Checksum của chuỗi khác checksum của file

Chương trình trên hash `"abc"` (3 bytes), không hash file tên `abc.txt` nếu file có thêm newline. Ví dụ:

~~~bash
printf 'abc' > abc.txt
sha256sum abc.txt
~~~

Trong một môi trường Unix có `sha256sum`, hash của file không chứa newline sẽ giống output Java trên. Nếu dùng `echo abc > abc.txt`, lệnh thường thêm newline, nên hash khác.

### 16.2. Dùng API nào để xác minh distribution ZIP?

Trong project thật, không cần tự viết Java cho Wrapper verification. Wrapper cung cấp `distributionSha256Sum` và có thể dùng `Get-FileHash`/`sha256sum` để kiểm tra thủ công theo quy trình. Viết custom verifier chỉ nên làm nếu có yêu cầu đặc biệt và đã xử lý đủ kiểm tra nguồn giá trị expected.

## 17. Kết hợp ba lớp trong CI/CD

Một pipeline đáng tin cậy có thể tổ chức theo thứ tự:

1. Checkout source từ commit được phép chạy.
2. Kiểm tra **Wrapper scripts/JAR** (theo công cụ được tổ chức phê duyệt).
3. Dùng Wrapper với `distributionUrl` và checksum chính thức.
4. Tải/bắt đầu Gradle trong môi trường JDK được kiểm soát.
5. Resolve project dependencies với lock state đã commit.
6. Kiểm tra artifacts/plugins theo verification metadata đã commit.
7. Chạy compile, unit/integration tests và security scans.
8. Kiểm tra dependency lockfile/verification metadata **không bị tự đổi** trong job chỉ chạy build.
9. Đối với PR nâng cấp dependency, review các file `build.gradle.kts`, lockfile, verification XML và kết quả tests cùng nhau.
10. Chỉ cấp secrets nội bộ cho job đáng tin; không dùng code không được review trên runner chứa credential nhạy cảm.

### 17.1. Các file nên được commit

| File | Có nên commit? | Lý do |
| --- | --- | --- |
| `gradlew`, `gradlew.bat` | Có | Tài liệu/cơ chế khởi động Wrapper của project |
| `gradle/wrapper/gradle-wrapper.jar` | Có, sau khi xác minh | Bootstrap binary |
| `gradle/wrapper/gradle-wrapper.properties` | Có | Pin Gradle version/URL/SHA của distribution |
| `app/gradle.lockfile` | Có | Resolved dependency versions cho :app |
| `gradle/verification-metadata.xml` | Có | Expected artifact checksums/signatures |
| Gradle verification public keyring | Có, nếu được dùng và review | Offline/public-key verification |
| Password/token trong `gradle.properties` root | Không | Secret không được commit |
| `$GRADLE_USER_HOME/caches` | Không | Local caches, không phải source-of-truth |

### 17.2. Ví dụ CI script kiểm tra build

Một job shell trên Linux:

~~~bash
set -e

# Bước validation Wrapper JAR cần dùng công cụ/phê duyệt
# riêng theo policy tổ chức trước khi chạy gradlew.

./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --console=plain

./gradlew :app:run --console=plain
~~~

Job này **không dùng `--write-locks` hoặc `--write-verification-metadata`**, vì các lệnh đó là thao tác cập nhật policy, không phải thao tác kiểm tra read-only thường ngày. Nếu CI luôn tự regenerate và chấp nhận mọi hash/lock mới, việc review version drift và artifact integrity bị suy yếu.

### 17.3. PR cập nhật dependencies

Khi nâng một dependency trong CI:

~~~text
PR changes
├── app/build.gradle.kts                : version/BOM updated
├── app/gradle.lockfile                 : selected versions updated
└── gradle/verification-metadata.xml    : hashes/signatures reviewed
~~~

Nếu đồng thời nâng Gradle Wrapper:

~~~text
gradle/wrapper/gradle-wrapper.properties
  -> distributionUrl / distributionSha256Sum cùng bản
gradle/wrapper/gradle-wrapper.jar
  -> validation checksum riêng
gradlew / gradlew.bat
  -> update nếu cần theo Wrapper task
~~~

Không bắt buộc mọi PR phải đụng tất cả file. Chỉ cập nhật thứ gì **thực sự thay đổi**, với review traceable.

## 18. Quy trình nâng Gradle Wrapper an toàn

1. Xác định target Gradle version tương thích với JDK, plugins, Android/Java tooling của dự án.
2. Đọc release notes và upgrade guide.
3. Lấy checksum **đúng ZIP phân phối `-bin` hoặc `-all`** từ nguồn chính thức.
4. Nâng wrapper qua task/command thích hợp với checksum được cấu hình.
5. Kiểm tra `gradle-wrapper.properties` đã ghi đúng version, URL, SHA.
6. Kiểm tra riêng `gradle-wrapper.jar` với official checksums hoặc CI validation.
7. Dùng workspace/môi trường sạch để test lần tải distribution mới; lưu ý cache reuse không xác minh lại ZIP mỗi lần.
8. Chạy `./gradlew --version`, `./gradlew help` và build/test phù hợp.
9. Review những plugin/Gradle API có thay đổi hành vi.
10. Commit các Wrapper files cùng nhau theo policy.

**Không áp dụng SHA của `-all.zip` cho `-bin.zip`. Không “fix” mismatch bằng cách xóa `distributionSha256Sum`.**

### 18.1. Khi Wrapper version không đổi

Nếu chỉ chạy wrapper task nhưng version không đổi, Gradle có quy tắc giữ lại `distributionSha256Sum` trong properties. Khi version đổi, phải cung cấp checksum tương ứng theo cơ chế task và phiên bản Wrapper đang dùng.

Không sửa tay `distributionUrl` mà quên cập nhật `distributionSha256Sum`. Đây là nguyên nhân phổ biến của checksum mismatch khi download mới.

## 19. Khác biệt giữa checksum, chữ ký, TLS và repository policy

Cả ba lớp Gradle nên nằm trong một chuỗi tin cậy rộng hơn:

- **TLS/HTTPS**: bảo vệ kênh truyền và giúp xác định server ở thời điểm giao tiếp; không pin version.
- **Checksums**: bảo đảm artifact bytes khớp expected digest; không tự cho biết expected digest đến từ nguồn tốt.
- **PGP signatures**: giúp xác minh publisher key/provenance nếu trust được thiết lập đúng.
- **Version locking**: pin selected module versions; không verify byte.
- **Wrapper distribution checksum**: xác minh Gradle ZIP khi download; không kiểm tra JDK hoặc Wrapper JAR.
- **Dependency verification**: hash/signature của external dependencies/plugins trong scope.
- **Dependency verification metadata**: phải được review, không tự tin cậy mọi checksum vừa sinh.
- **SCA/vulnerability scanning**: đối chiếu thư viện/version với rủi ro bảo mật đã biết; không thay thế integrity check.
- **Unit/integration tests**: phát hiện lỗi tương thích/hành vi; không chứng minh artifact không bị tamper.

Một dependency **có chữ ký hợp lệ** vẫn có thể bị một publisher hợp lệ vô tình phát hành với lỗ hổng. Một artifact không có lỗ hổng đã biết vẫn có thể không tương thích với môi trường.

## 20. Chẩn đoán lỗi: triệu chứng và cách xử lý

| Triệu chứng | Lớp cần xem | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- | --- |
| Lỗi `Could not resolve ...` sau đổi version | Locking hoặc resolution | Declared version xung đột lock, module bị xóa | Xem dependencyInsight, review update locks |
| Build báo lock state không khớp | Locking | Module added/removed/upgraded chưa cập nhật | Sinh/review lại lock state sau thay đổi có chủ đích |
| CI lỗi còn local chạy | Cả ba và environment | Local cache, local lockfile chưa commit, khác JDK/repos | So sánh committed files/configuration, dùng CI sạch |
| Artifact checksum mismatch | Dependency verification | JAR/POM byte khác expected, mirror bị sửa | Kiểm tra nguồn và expected digest; không accept mù |
| Artifact chưa có trong verification XML | Verification | Dependency/plugin version mới hoặc task resolve thêm module | Bootstrap có review, bổ sung checksum tin cậy |
| PGP signature không verify | Verification | Khóa không tin cậy/không tải được/signature sai | Xác minh fingerprint publisher và keyring |
| `verification-metadata.xml` quá lớn | Verification | Entries cũ, POM/module metadata/sources/javadocs | Rà soát/sắp xếp policy; đừng tắt kiểm tra vì tiện |
| Gradle distribution checksum mismatch | Wrapper ZIP | URL và SHA không cùng ZIP, mirror trả sai bytes | Tra SHA chính thức đúng bin/all/version |
| `./gradlew` vẫn chạy dù ZIP cache bị nghi thay | Wrapper ZIP | Cache reuse không reverify download | Kiểm tra cache theo policy / dựng runner sạch |
| Wrapper JAR bị thay nhưng `distributionSha256Sum` đúng | Wrapper JAR | Nhầm đối tượng kiểm tra | Validate JAR riêng trước khi chạy |
| `--write-locks` không sinh lockfile cho test | Locking | Chỉ runtimeClasspath được resolve | Resolve test configuration với locking bật |
| `gradle.lockfile` nằm trong subproject | Locking | Lock state per project | Đây có thể đúng; không ép về root |
| Build pass nhưng `NoSuchMethodError` | Compatibility | API/runtime versions hoặc classloader lệch | Xem runtimeClasspath, tests, package contents |
| Verify metadata pass nhưng CVE vẫn còn | Supply chain | Integrity không phát hiện lỗ hổng đã biết | SCA scan, update policy và remediation |
| Wrapper tải qua proxy fail TLS | Network/Wrapper | CA, proxy, interception, DNS | Sửa truststore/network, không bỏ checksum |
| Artifact có cùng version nhưng mới được republish | Verification | Mutable repository | Điều tra, dùng immutable releases, không trust blind |
| PGP key tải không được trên CI | Verification | Key server bị chặn | Commit keyring công khai đã review theo policy |

### 20.1. Cách điều tra không làm yếu bảo mật

Khi có checksum mismatch:

1. Không sửa metadata/hash trong cùng bước chỉ để CI xanh.
2. Ghi lại module, filename, expected digest, observed digest và repository source nhưng không lộ secret.
3. Đối chiếu publisher release page, SHA từ nguồn tin cậy, bản artifact đã duyệt.
4. Kiểm tra mirror/proxy/credentials và server response.
5. Nếu thực sự nâng phiên bản có chủ đích, mở PR riêng hoặc commit review cùng lockfile.
6. Chạy lại CI sau khi chính sách đã được sửa và phê duyệt.

Khi lock mismatch:

1. Đọc `gradle.lockfile` cho configuration lỗi.
2. Chạy `dependencies` và `dependencyInsight` để xác định request.
3. Tìm BOM/platform/constraint/force vừa thay đổi.
4. Chỉ update lock khi dependency change là hợp lệ và đã test.

Khi Wrapper checksum mismatch:

1. Kiểm tra `distributionUrl` trỏ `-bin` hay `-all`.
2. Lấy SHA chính thức của file ZIP chính xác.
3. Kiểm tra giá trị trong properties không bị copy nhầm từ version khác.
4. Không tắt kiểm tra; không chạy ZIP từ mirror không tin cậy.
5. Dùng cache/runner sạch được quản trị phù hợp để tái hiện.

## 21. Những sai lầm phổ biến cần tránh

### 21.1. “Có gradle.lockfile rồi nên JAR không thể bị thay”

Sai. Lock chỉ ghi `group:name:version`; cùng version vẫn có thể trả byte khác từ một repo/mirror. Phải có artifact verification.

### 21.2. “Có verification-metadata.xml rồi thì Gradle luôn dùng cùng version”

Sai. Verification metadata không quyết định version; một version mới có thể được resolve nếu policy cho phép, nhưng artifact mới chưa được verify có thể làm build fail. Dùng lockfile/version constraints để kiểm soát version.

### 21.3. “Có distributionSha256Sum rồi, mọi dependency và Wrapper JAR đều được kiểm tra”

Sai. Nó chỉ dành cho ZIP Gradle distribution được Wrapper tải, và theo tài liệu Gradle chỉ thực hiện checksum khi distribution chưa được download. Wrapper JAR cần validation khác; dependencies cần verification khác.

### 21.4. “Bootstrap verification một lần là đủ tin cậy”

Sai. Bootstrap ghi lại những artifact bytes nó nhận được **ở thời điểm đó**. Nếu nguồn đã bị xâm nhập, XML có thể ghi đúng hash của JAR độc hại. Phải review nguồn và expected checksums.

### 21.5. “Dùng SNAPSHOT với lockfile là hoàn toàn reproducible”

Sai. Snapshot/changing artifact có thể đổi bytes cùng tọa độ. Lock chỉ giữ version identity, không biến một mutable artifact thành immutable.

### 21.6. “Lệnh dependencies --write-locks ở root tự khóa mọi module”

Không luôn đúng. Với multi-project, task `dependencies` chạy ở project được nhắm tới và chỉ những configurations thực sự được resolve mới có lock state. Dùng qualified tasks/configurations đúng.

### 21.7. “Tắt verification là cách xử lý đúng khi CI fail”

Không. Tắt verification có thể bỏ qua dấu hiệu artifact bị tamper. Phải điều tra nguyên nhân và chỉ thay metadata với review tin cậy.

### 21.8. “So checksum từ chính ZIP tải về với checksum do cùng mirror gửi là đủ”

Không đảm bảo khi nguồn/mirror bị chiếm quyền cả hai giá trị có thể bị thay. Hãy chọn nguồn expected checksum chính thức hoặc độc lập, có trust anchor rõ.

### 21.9. “Build reproducible chỉ cần ba file lock, metadata và wrapper checksum”

Không đủ. Output còn chịu ảnh hưởng JDK/compiler, môi trường, timestamps, toolchains, native tools, timezone/locale, random/clock, network APIs và task implementation. Cần deterministic build logic và tests.

## 22. Bài tập thực hành và đáp án

**Câu 1.** Một project có `implementation("org.apache.commons:commons-lang3:3.+")`. Sau hai tháng Gradle chọn version khác, nhưng JAR không bị thay tại cùng tọa độ. Cơ chế nào giải quyết hiện tượng version trôi?

**Đáp án:** Dependency locking cho những configurations được resolve; sinh và commit `gradle.lockfile`. Dependency verification không tự chọn version.

**Câu 2.** Lockfile vẫn ghi `commons-lang3:3.14.0`, nhưng JAR có SHA-256 khác expected. Lockfile có bắt được không?

**Đáp án:** Không. Dependency verification bằng checksum/signature mới phù hợp để phát hiện bytes thay đổi.

**Câu 3.** Wrapper tải `gradle-8.14.3-bin.zip` qua HTTPS, nhưng ZIP không khớp official SHA. Cần kiểm tra file cấu hình nào?

**Đáp án:** `gradle/wrapper/gradle-wrapper.properties`, đặc biệt `distributionUrl` và `distributionSha256Sum`, rồi so expected SHA với distribution ZIP chính thức.

**Câu 4.** Cùng Gradle 8.14.3, đổi `-bin.zip` sang `-all.zip`. Có thể dùng lại cùng SHA không?

**Đáp án:** Không. Hai ZIP khác bytes; lấy checksum riêng của `-all.zip`.

**Câu 5.** Đã cấu hình `distributionSha256Sum`, có cần kiểm tra `gradle-wrapper.jar` không?

**Đáp án:** Có. Wrapper JAR là binary bootstrap riêng, không được đối chiếu bởi property đó.

**Câu 6.** Cấu hình locking chỉ ở `:app`, chạy root `./gradlew dependencies --write-locks`. Có chắc sinh `app/gradle.lockfile` không?

**Đáp án:** Không. Phải resolve configuration của `:app`, chẳng hạn `./gradlew :app:dependencies --configuration runtimeClasspath --write-locks`.

**Câu 7.** Khi Gradle sinh verification XML lần đầu, có thể chấp nhận toàn bộ SHA vì nó được Gradle tính toán không?

**Đáp án:** Không. Hash chỉ mô tả bytes đã nhận được; phải review baseline và xác thực provenance theo nguồn đáng tin.

**Câu 8.** Metadata có SHA-256 và PGP signatures. Việc trust key của publisher có cần kiểm tra không?

**Đáp án:** Có. Chữ ký dùng khóa không được xác minh danh tính chưa chứng minh đúng publisher. Cần so fingerprint với thông tin từ kênh đáng tin.

**Câu 9.** Khi một plugin Gradle mới được thêm vào build, verification metadata có thể phải cập nhật không?

**Đáp án:** Có. Plugin artifacts được resolve qua Gradle dependency engine có thể thuộc phạm vi dependency verification.

**Câu 10.** `Sha256Demo.java` hash chuỗi `"abc"` cho giá trị nào?

**Đáp án:** `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`.

**Câu 11.** `gradle.lockfile` có lưu secret hoặc binary JAR không?

**Đáp án:** Thông thường không; nó ghi module coordinates, versions và configurations. Không dùng nó làm nơi lưu credential.

**Câu 12.** Ba lớp đều pass nhưng runtime báo `NoSuchMethodError`. Cơ chế đã làm sai?

**Đáp án:** Không nhất thiết. Ba lớp bảo vệ version consistency, artifact integrity và distribution ZIP. Chúng không tự xác minh ABI/runtime compatibility; cần dependency graph investigation và tests.

**Câu 13.** Vì sao `--write-verification-metadata` không nên chạy như một job tự động accept mỗi lần CI build?

**Đáp án:** Nó có thể ghi checksum của artifact chưa được đánh giá, biến thay đổi không rõ nguồn thành baseline được “tin”. Metadata mới cần review trước khi commit.

**Câu 14.** Nếu Gradle Wrapper distribution đã được cache, có phải property `distributionSha256Sum` sẽ hash lại file ZIP sau mỗi `./gradlew`?

**Đáp án:** Không. Gradle Wrapper docs nói verification diễn ra khi distribution **chưa được download** và cần download mới. Cần quản lý/kiểm tra cache riêng nếu có nghi ngờ.

## 23. Checklist áp dụng cho dự án Gradle thật

1. Xác định **Gradle Wrapper version, JDK và môi trường** được dự án hỗ trợ.
2. Commit Wrapper scripts/JAR/properties từ nguồn tin cậy, kiểm tra riêng Wrapper JAR.
3. Lấy checksum chính thức của đúng Gradle ZIP `-bin` hoặc `-all`; ghi `distributionSha256Sum`.
4. Bật dependency locking cho các configurations quan trọng và resolve đủ phạm vi trước khi commit lockfiles.
5. Review lockfile trong PR, không tự sửa thủ công hoặc tự accept version drift.
6. Chọn immutable releases, hạn chế dynamic versions hoặc changing SNAPSHOTs trong release builds.
7. Bootstrap verification metadata trên môi trường đáng tin, dùng SHA-256/PGP khi phù hợp.
8. Review checksum/signature/keys với nguồn độc lập, commit verification metadata.
9. Khi thêm/nâng dependency, cập nhật declarations + lockfiles + verification XML theo cùng review.
10. Trong CI thường ngày, chạy build/test **không tự regenerate và chấp nhận** lock/metadata.
11. Tránh mở rộng exception/disable verification chỉ để build xanh.
12. Với archive/caches được reuse, hiểu những gì kiểm tra tự động thực sự được chạy.
13. Bổ sung dependency scanning, tests và reproducible build policies.
14. Đọc tài liệu đúng **phiên bản Gradle Wrapper** vì chi tiết API/options có thể thay đổi.

**Ghi nhớ ba câu:**

~~~text
gradle.lockfile
  -> Phiên bản module nào đã được chọn?

gradle/verification-metadata.xml
  -> File dependency/plugin nhận được có đúng checksum/signature đáng tin?

gradle/wrapper/gradle-wrapper.properties / distributionSha256Sum
  -> ZIP Gradle distribution được Wrapper tải có đúng SHA-256 chính thức?
~~~

Và một câu bổ sung: **`gradle-wrapper.jar` phải được kiểm tra riêng**; không dùng checksum của ZIP distribution để chứng minh JAR bootstrap an toàn.

## 24. Tài liệu chính thức

1. Gradle — Locking Dependency Versions: https://docs.gradle.org/current/userguide/dependency_locking.html
2. Gradle — Verifying Dependencies: https://docs.gradle.org/current/userguide/dependency_verification.html
3. Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
4. Gradle — Dependency Constraints and Conflicts: https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html
5. Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
6. Gradle — Dependency Verification / Security overview: https://docs.gradle.org/current/userguide/securing_dependencies.html
7. Gradle — Declaring Repositories: https://docs.gradle.org/current/userguide/declaring_repositories_basics.html
8. Gradle — Dependency Verification and Security Best Practices: https://docs.gradle.org/current/userguide/best_practices_security.html
9. Gradle releases/downloads và checksum công bố chính thức: https://gradle.org/releases/
10. Gradle distributions/checksums: https://services.gradle.org/distributions/

Các URL `current` trong danh sách theo tài liệu Gradle hiện hành. Một repository có thể vẫn dùng Gradle 8.x hoặc 9.x khác, vì thế cần đối chiếu **Gradle Wrapper của dự án** trước khi áp dụng những flags, metadata format hoặc policy cụ thể. Các mẫu chứa placeholder `REPLACE_WITH_OFFICIAL_64_HEX_SHA256` không được sử dụng nguyên văn trong project; cần thay bằng giá trị đã xác minh.