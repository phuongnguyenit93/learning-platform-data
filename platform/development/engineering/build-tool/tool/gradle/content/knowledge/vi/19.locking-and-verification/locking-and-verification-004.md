# Quản lý lockfile trong Git và xử lý thay đổi dependency có chủ đích trong Gradle

## 1. Tại sao cần dependency lockfile?

Khi một dự án khai báo:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

`3.+` chỉ là **yêu cầu phiên bản động**, không phải một phiên bản cố định. Gradle sẽ tìm phiên bản phù hợp ở repository và có thể chọn phiên bản mới khi metadata thay đổi. Ngay cả với direct dependency đã pin version, một module bắc cầu, platform/BOM hoặc resolution rule vẫn có thể khiến kết quả phân giải thay đổi.

**Dependency locking** là cơ chế Gradle ghi lại **những module versions đã được chọn trong từng configuration** và dùng kết quả đó để ràng buộc những lần resolve sau. File chứa trạng thái ấy gọi là **lockfile**. Khi được commit vào Git, lockfile giúp toàn đội và CI biết tập phiên bản nào đã được review và phê duyệt.

Bài học thuộc nhóm **Khóa và xác minh** của Build Tool Gradle, tập trung vào:

1. Tạo và đọc `gradle.lockfile`; biết scope của lockfile, configuration và project.
2. Đưa lockfile vào **Git**, review diff trong pull request và tránh ignore nhầm.
3. Nâng dependency **có chủ đích** bằng `--update-locks` hoặc `--write-locks`.
4. Hiểu vì sao thay `build.gradle` mà chưa thay lockfile có thể làm Gradle báo version conflict.
5. Giải quyết thay đổi dependency bắc cầu, merge conflict, multi-project và lỗi CI.
6. Phân biệt **dependency locking**, dependency verification, version catalog, dependency cache và các loại Gradle cache khác.

Ví dụ dùng **Groovy DSL** (`build.gradle`, `settings.gradle`) và Java 17; để chạy phải có Gradle Wrapper hợp lệ, JDK 17 được Gradle phát hiện (hoặc cấu hình resolver cấp toolchain) và kết nối Maven Central nếu artifact chưa có trong cache.

### 1.1. Ba trạng thái cần phân biệt

| Thành phần | Lưu gì? | Câu hỏi được trả lời |
| --- | --- | --- |
| Dependency declaration | `implementation 'g:a:1.2'`, version alias, constraints | **Build yêu cầu** gì? |
| Resolved dependency graph | Các direct/transitive modules, versions, variants của configuration | **Gradle thực tế chọn** gì? |
| Dependency lock state | Danh sách `group:name:version` theo configuration được khóa | **Bản nào phải được giữ ổn định** khi build về sau? |

Ví dụ `build.gradle` yêu cầu `g:a:1.+` nhưng `gradle.lockfile` ghi `g:a:1.4`. Một bản `1.5` mới xuất hiện trên repository không mặc nhiên được dùng trong build đang có khóa. Đội phát triển phải quyết định **nâng có chủ đích**, ghi lại lock state mới và review.

Locking không thay thế khai báo dependency: nếu không có direct/transitive dependency cần module X, chỉ thêm một dòng X vào lockfile **không biến X thành dependency của ứng dụng**.

### 1.2. Mục tiêu là kiểm soát thay đổi, không phải ngăn nâng cấp

Khi phát hiện lỗi bảo mật, cần API mới hoặc cập nhật thư viện để hỗ trợ JDK mới, người bảo trì nên nâng version. Lockfile làm thay đổi đó **hiển thị trong Git diff** và buộc build logic cùng lock state đồng bộ, thay vì tự trôi do metadata từ repository.

Điều lockfile không giải quyết là **tính toàn vẹn byte của JAR**. Nếu cùng một version bị republish với nội dung khác, khóa version không tự phát hiện byte thay đổi. Trường hợp này cần thêm **dependency verification** (checksum/signature) và quy trình phát hành artifact bất biến.

## 2. Hình dung quy trình locking

~~~text
build.gradle / libs.versions.toml / constraints
                 |
                 v
          Resolve dependency graph
        + repository metadata / variants
        + transitive dependencies / rules
                 |
                 v
        Selected versions theo configuration
                 |
       +---------+-----------+
       |                     |
   --write-locks        Build bình thường
   --update-locks       đọc lock state đã có
       |                     |
       v                     v
   gradle.lockfile      Strict constraints và validation
       |                     |
       v                     v
    Git diff/PR          Graph khớp hoặc lỗi
       |
       v
  Code review, tests, merge
~~~

Giải thích:

- **`--write-locks`**: lưu state cho các configurations có khóa **được resolve trong invocation**.
- **`--update-locks group:name`**: cập nhật chọn lọc module chỉ định, trong khi những locked modules khác vẫn được dùng làm ràng buộc theo cơ chế Gradle.
- **Build bình thường**: đọc lockfile hiện có và áp dụng các locked versions như **strict version constraints**; đồng thời kiểm tra graph phù hợp.
- **Git**: lưu declaration và lockfile ở cùng commit để review/rollback/bisect được.

Lưu ý quan trọng: **bật locking không làm Gradle tự resolve mọi configuration**. Một task không cần `testRuntimeClasspath` có thể không chạm configuration này. Muốn state của một configuration được tạo/kiểm tra, phải có invocation thực sự resolve nó.

## 3. Bật dependency locking ở đúng configuration

### 3.1. Bật khóa chọn lọc

Trong một project đã áp dụng Java plugin:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

configurations {
    compileClasspath {
        resolutionStrategy.activateDependencyLocking()
    }
    runtimeClasspath {
        resolutionStrategy.activateDependencyLocking()
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

`compileClasspath` và `runtimeClasspath` là **resolvable configurations** trong Java ecosystem. Hai configuration này được khóa; `testRuntimeClasspath` hoặc `annotationProcessor` chưa chắc được khóa vì không được nêu trong cấu hình trên.

`implementation` và `testImplementation` thường là **bucket để khai báo dependencies**, không phải graph dùng để resolve trực tiếp. Vì vậy không nên cố gọi `./gradlew dependencies --configuration implementation` rồi nghĩ đó là report đúng về classpath của Java compiler.

### 3.2. Bật khóa cho mọi project configuration

Cách phổ biến hơn:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Gradle bật locking cho các project configurations; state thực sự được ghi khi một **resolvable configuration** được resolve. `lockAllConfigurations()` không bắt mọi task chạy và **không tự khóa buildscript classpath**.

Đây thường là lựa chọn tốt cho một Java project nhỏ. Với project lớn chứa native/Android/Kotlin Multiplatform variants, có thể cần lựa chọn configurations và môi trường chạy khác nhau để coverage hợp lý.

### 3.3. Buildscript classpath là scope khác

Nếu mã `build.gradle` có dependency dành cho chính script:

~~~groovy
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }

    repositories {
        mavenCentral()
    }

    dependencies {
        classpath 'org.yaml:snakeyaml:2.7'
    }
}
~~~

đó là **buildscript dependency**, không phải `implementation` của ứng dụng. Khi bật khóa cho buildscript classpath, Gradle dùng file **`buildscript-gradle.lockfile`**. Ngược lại, `gradle.lockfile` thông thường ghi **project dependency configurations**.

Plugin DSL (`plugins { id '...' version '...' }`), `buildSrc` và included build `build-logic` có các graph/resolution scopes riêng. **Không khẳng định `root/gradle.lockfile` khóa tất cả Gradle plugins, buildscript libraries và Wrapper distribution**.

## 4. Tạo lock state ban đầu với `--write-locks`

Sau khi bật locking, chạy Gradle để resolve các configurations được chọn:

~~~bash
./gradlew dependencies --write-locks
~~~

Theo Gradle User Manual, task `dependencies` khi gọi trên project hiện tại có thể resolve những **resolvable configurations** đã bật locking và tạo/cập nhật lock state cho chúng. Để chỉ nhắm một configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
~~~

Nếu invocation resolve chỉ `runtimeClasspath`, đừng suy rằng `compileClasspath`, `testRuntimeClasspath` và mọi variants khác cũng đã có state mới.

Nếu build thất bại, không được coi state là đã được persist thành công. Kiểm tra lỗi resolution/task thực tế và thực hiện lại **khi đã sửa nguyên nhân**; đừng tự tạo file rỗng.

### 4.1. Định dạng `gradle.lockfile`

Với Gradle hiện đại, file lock của project có tên **`gradle.lockfile`** trong **thư mục gốc của project/subproject**. Ví dụ chỉ để học cách đọc định dạng:

~~~text
# This is a Gradle generated file for dependency locking.
# Manual edits can break the build and are not advised.
# This file is expected to be part of source control.
org.apache.commons:commons-lang3:3.17.0=compileClasspath,runtimeClasspath,testCompileClasspath,testRuntimeClasspath
empty=annotationProcessor
~~~

Diễn giải:

- `org.apache.commons:commons-lang3:3.17.0`: selected module `group:name:version`.
- Phần sau `=`: những configurations có state của module này.
- `empty=annotationProcessor`: configuration đã được ghi state nhưng **không có module cần khóa**.
- Gradle thường sắp xếp entries/configurations để diff dễ review.
- Nội dung thật phụ thuộc plugins, source sets, configurations và graph đã resolve; **không lấy ví dụ làm lockfile để dán thủ công**.

Một lockfile có thể ghi module trực tiếp và module bắc cầu. Nếu project dùng BOM/platform hoặc constraints, selected graph có thể có nhiều modules hơn số dòng trong `dependencies { }`.

### 4.2. Những file thường được commit

| File | Mục đích | Có commit Git? |
| --- | --- | --- |
| `gradle.lockfile` | State cho project dependencies | **Có** |
| `app/gradle.lockfile` | State của subproject `:app` | **Có** |
| `library/gradle.lockfile` | State của subproject `:library` | **Có** |
| `buildscript-gradle.lockfile` | Buildscript state nếu đã bật khóa buildscript | **Có** |
| `gradle/verification-metadata.xml` | Hash/signature verification policy nếu có | **Có, nhưng khác lockfile** |
| `gradle/libs.versions.toml` | Version catalog | **Có** |
| `gradle/wrapper/gradle-wrapper.properties` | Gradle Wrapper distribution configuration | **Có** |
| `.gradle/` | Project-local Gradle caches | **Không** |
| `build/` | Generated task outputs | **Không** |
| `~/.gradle/caches` | User-home caches | **Không** |

Lockfile là **generated file có ý nghĩa nguồn**. Không nên ignore chỉ vì do Gradle tạo. Ngược lại, không commit thư mục cache `.gradle/` hoặc output `build/` vì chúng thuộc máy/build invocation.

## 5. Git workflow: commit lockfile cùng khai báo dependency

Một chu trình ban đầu:

~~~bash
./gradlew dependencies --write-locks
git status --short
git add build.gradle gradle.lockfile
git commit -m "Enable Gradle dependency locking"
~~~

Đây là **lệnh minh họa cho một repository Git hợp lệ**, không phải hoạt động tự động trong bài. Kiểm tra `git status` trước `git add`; trong project thật còn có thể cần `settings.gradle`, `gradle/libs.versions.toml` hoặc file submodule.

### 5.1. `.gitignore`: đừng nhầm `.gradle/` với `gradle/`

Ví dụ:

~~~gitignore
.gradle/
**/build/

# Không ignore gradle.lockfile hoặc buildscript-gradle.lockfile.
~~~

`.gradle/` bắt đầu bằng dấu chấm: cache/trạng thái Gradle của project. `gradle/` không dấu chấm thường chứa **Wrapper**, version catalog, verification metadata. **Không ignore nguyên thư mục `gradle/`** nếu đó là nơi chứa những file cần version control.

Nếu repository có pattern `*.lockfile` hoặc `**/gradle.lockfile`, cần sửa ignore rule/đặt exception chính xác để các lockfiles được Git theo dõi.

Khi `git status --short` cho thấy file mới là `?? gradle.lockfile` nhưng `git diff -- gradle.lockfile` không hiển thị nội dung: đó là hành vi bình thường vì file **chưa tracked**. Mở file bằng editor/`cat` hoặc dùng `git add -N gradle.lockfile` để xem working-tree diff của file mới trước khi add thực sự.

### 5.2. Review diff thay vì chỉ commit tất cả

Đối với dependency upgrade:

~~~bash
git status --short
git diff -- build.gradle gradle.lockfile
git diff -- gradle/libs.versions.toml app/gradle.lockfile
~~~

Đừng mặc định một PR chỉ sửa `gradle.lockfile`. Khi model dependency thay đổi, declaration (build.gradle/catalog/platform/constraints) phải được xem cùng selected graph.

Một pull request tốt trả lời:

1. Vì sao cập nhật? Bảo mật, bugfix, API, JDK, performance, compatibility?
2. Module trực tiếp nào đổi version?
3. Các transitive modules nào xuất hiện, biến mất hoặc đổi version?
4. Configuration nào bị ảnh hưởng: compile, runtime, test, annotation processing?
5. Plugin/buildscript graph có bị ảnh hưởng không?
6. Đã chạy tests và trên Gradle Wrapper/JDK nào?
7. Có thay đổi verification metadata hoặc policy repository cần review không?

Nếu chỉ nâng một thư viện mà lockfile thay hàng trăm dòng, không mặc định coi đó là lỗi, nhưng phải **giải thích nguyên nhân** — platform/BOM, metadata, multiple configurations hoặc update toàn graph.

### 5.3. Không chỉnh lockfile bằng find-and-replace

Giả sử muốn nâng `org.apache.commons:commons-lang3:3.17.0` lên `3.18.0`. Chỉ đổi chuỗi trong `gradle.lockfile` bằng tay **không bảo đảm**:

- Build script/Version Catalog đồng ý với version mới.
- Tất cả configurations liên quan đều được cập nhật.
- Các transitive dependencies/constraints còn tương thích.
- Graph không thêm module mới.
- Mọi lockfile của subproject đúng với resolved variants.

Gradle User Manual cũng khuyến cáo không chỉnh file sinh bởi locking bằng tay. **Sửa declaration, dùng Gradle để regenerate, rồi review Git diff.**

## 6. Demo Gradle Groovy DSL và Java 17 hoàn chỉnh

Ví dụ này dùng **Application plugin** và **Apache Commons Lang3**. Dùng version `3.17.0` lúc đầu, rồi cập nhật có chủ đích lên `3.18.0` — cả hai đều có artifact trên Maven Central. Mã Java dùng `StringUtils.reverse` có output xác định.

### 6.1. Cấu trúc thư mục

~~~text
locking-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── LockDemo.java
~~~

Bốn file Wrapper phải được tạo đúng quy trình, không phải placeholder rỗng. Ví dụ cần JDK 17 toolchain, Gradle Wrapper tương thích và Maven Central truy cập được ở lần tải đầu.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'locking-demo'
~~~

### 6.3. `build.gradle` — bản ban đầu

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.LockDemo'
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

Tại đây:

- `application` là core Gradle plugin, tạo task `run` cùng các task Java.
- `implementation` là project dependency cho Java application, không phải Gradle plugin dependency.
- `java.toolchain` chọn JDK 17 cho các task Java hỗ trợ, không tự quyết định Gradle Daemon JVM.
- `lockAllConfigurations()` bật khóa project configurations; vẫn cần chạy lệnh resolve để tạo state.

### 6.4. `src/main/java/demo/LockDemo.java`

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class LockDemo {
    private LockDemo() {
    }

    public static void main(String[] args) {
        String input = args.length == 0 ? "Gradle" : args[0];
        System.out.println("reverse=" + StringUtils.reverse(input));
    }
}
~~~

Đây là chương trình Java 17 biên dịch được khi Commons Lang có trên classpath. Tên file phải là `LockDemo.java` trong thư mục package `demo`.

### 6.5. Chạy ứng dụng và kiểm tra stdout

Trên Linux/macOS:

~~~bash
./gradlew -q run
./gradlew -q run --args='Lock'
~~~

Stdout của Java main ở lệnh thứ nhất:

~~~text
reverse=eldarG
~~~

Và lệnh thứ hai:

~~~text
reverse=kcoL
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
.\gradlew.bat -q run --args="Lock"
~~~

Hai output trên là **các dòng do chương trình in**, không phải toàn bộ log Gradle. Lệnh `--args` là tham số ứng dụng cho Java main, khác JVM flags.

Nếu đã có Commons Lang JAR thật tại một đường dẫn, có thể chạy Java độc lập:

~~~bash
# Linux/macOS: LANG_JAR là đường dẫn đến commons-lang3-3.17.0.jar.
javac -cp "$LANG_JAR" -d out src/main/java/demo/LockDemo.java
java -cp "out:$LANG_JAR" demo.LockDemo
~~~

Kết quả cũng là `reverse=eldarG`. Lệnh này **chỉ hoạt động khi `LANG_JAR` đã trỏ tới file thật**; trên Windows dấu ngăn cách classpath là `;`. Dùng Gradle Wrapper đơn giản hơn vì nó tự quản lý classpath.

### 6.6. Tạo lockfile và đọc kết quả

~~~bash
./gradlew dependencies --write-locks
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Lệnh đầu tiên tạo hoặc cập nhật `gradle.lockfile` cho những configurations được resolve. Với demo, bạn sẽ thấy module `org.apache.commons:commons-lang3:3.17.0` được ghi kèm các configurations tương ứng. Không khẳng định mọi Gradle version/plugin in đúng cùng danh sách vì source sets/configurations có thể khác.

Sau khi review file:

~~~bash
git status --short
git add build.gradle settings.gradle gradle.lockfile src/main/java/demo/LockDemo.java
git commit -m "Lock Commons Lang version for Java application"
~~~

Nếu chỉ thực hành trong một thư mục không có Git repository, bỏ qua bước commit. **Tạo state trước, validate và review trước, rồi mới commit.**

### 6.7. Build bình thường dùng state đã khóa

~~~bash
./gradlew clean build
./gradlew -q run
~~~

Không có `--write-locks`. Gradle đọc state đã lưu khi resolve các locked configurations. `clean` dọn output task, **không xóa lockfile**. Nếu build thành công, output của Java main vẫn là `reverse=eldarG`.

## 7. Nâng dependency 3.17.0 → 3.18.0 có chủ đích

Trong một branch học tập, sửa `build.gradle` thành:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.18.0'
}
~~~

Đây là phiên bản Commons Lang3 có trên Maven Central. Không sửa `gradle.lockfile` bằng tay.

### 7.1. Tại sao Gradle báo conflict khi chưa cập nhật lock?

Lockfile cũ ghim `commons-lang3:3.17.0`. Build script mới yêu cầu `3.18.0`. Gradle áp dụng locked versions như **strict constraints** trong resolution. Yêu cầu direct dependency `3.18.0` không tương thích với lock còn ép `3.17.0`, vì thế resolution của `compileClasspath` hoặc `runtimeClasspath` có thể fail.

Đây là tín hiệu đúng: **declaration và lock state chưa thống nhất**, chứ không phải dấu hiệu bắt buộc phải xóa cache.

### 7.2. Cập nhật chọn lọc: `--update-locks`

~~~bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
~~~

Cờ `--update-locks` nhận một hoặc nhiều `group:name`, bỏ ràng buộc khóa cũ đối với module được chỉ định trong lần resolve và cập nhật state. **Nó đã hàm ý `--write-locks`**, không cần thêm cờ đó.

Nếu chỉ muốn cập nhật runtime config:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --update-locks org.apache.commons:commons-lang3
~~~

Nhưng lệnh này **không bảo đảm `compileClasspath` và test configurations cũng đã được cập nhật**. Với demo, nên dùng lệnh đầu không giới hạn configuration để report có thể resolve mọi configuration liên quan của project hiện tại.

Tiếp theo:

~~~bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew clean build
git diff -- build.gradle gradle.lockfile
~~~

Review xem selected version chuyển từ `3.17.0` sang `3.18.0` ở những configurations phù hợp; kiểm tra cả những transitive dependencies bị ảnh hưởng.

### 7.3. Cập nhật toàn bộ state: `--write-locks`

~~~bash
./gradlew dependencies --write-locks
~~~

Lệnh này tạo lại state cho những configurations được resolve, phù hợp khi bootstrap, nâng platform/BOM hoặc thay đổi graph nhiều module. Nó có thể khiến Git diff **lớn hơn** do thêm/bớt modules hay selected versions của dynamic dependencies.

So sánh:

| Tình huống | Phương án thường thích hợp |
| --- | --- |
| Khởi tạo lockfile lần đầu | `--write-locks` |
| Chỉ nâng 1–2 modules được review | `--update-locks group:name` |
| Nâng cả BOM hoặc nhóm dependencies liên quan | `--write-locks` sau khi review phạm vi |
| Merge hai branch làm graph thay đổi | Regenerate có kiểm soát, có thể dùng `--write-locks` |
| Chỉ revalidate metadata/artifact cache | `--refresh-dependencies` — **không thay thế update lock** |
| Chỉ chạy lại task đã `UP-TO-DATE` | `--rerun-tasks` — **khác dependency locking** |

### 7.4. Kiểm tra chương trình sau nâng

~~~bash
./gradlew clean build
./gradlew -q run
./gradlew -q run --args='Lock'
~~~

Hai invocation `run` tiếp tục có stdout:

~~~text
reverse=eldarG
reverse=kcoL
~~~

Đây là **hai dòng đầu ra gộp để tham khảo**, không phải một lệnh in đồng thời hai dòng. Mặc dù hàm sử dụng trong demo không đổi hành vi, trong dự án thật cần chạy compile, unit/integration tests và xem changelog/security implications trước khi merge.

## 8. Cập nhật một module vẫn có thể ảnh hưởng transitive graph

Một nâng cấp HTTP client hoặc logging framework thường đổi graph bắc cầu:

~~~text
Trước khi nâng:
  application -> http-client 1.0 -> codec 1.2

Sau khi nâng:
  application -> http-client 2.0 -> codec 1.4
                           -> new-transport 2.0
~~~

Dù bạn chỉ cho phép update `http-client`, Gradle có thể:

1. Giữ transitive versions đã khóa khi constraints còn tương thích.
2. Cho thay đổi version của một số modules do version constraints/rules yêu cầu.
3. Báo conflict nếu graph mới không thể thỏa các strict locks còn lại.
4. Thêm hoặc bỏ transitive modules trong lock state khi chúng là kết quả đúng của resolution.

Do đó **`--update-locks` không hứa Git diff chỉ có đúng một dòng thay đổi**. Tài liệu Gradle ghi rõ version của modules khác có thể đổi nếu resolution rules yêu cầu.

### 8.1. Cập nhật vài module cùng lúc

~~~bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3,org.slf4j:slf4j-api
~~~

Dấu phẩy ngăn cách `group:name`. Không bắt buộc hai module này đều tồn tại trong demo; đây là ví dụ cú pháp cho build thực tế.

Wildcard hợp lệ, nhưng cần biết phạm vi:

~~~bash
./gradlew dependencies --update-locks 'org.apache.commons:*'
./gradlew dependencies --update-locks '*:guava'
~~~

- `org.apache.commons:*`: nhóm modules thuộc group đó.
- `*:guava`: các modules có tên `guava` bất kể group.
- Wildcard rộng có thể mở khóa nhiều hơn ý định ban đầu. Nên ưu tiên `group:name` cụ thể.

Với project nhiều module, thêm task path `:app:dependencies` và `:library:dependencies` đúng scope thay vì chỉ chạy root.

### 8.2. Giải thích vì sao một transitive version đổi

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

`dependencies` giúp thấy graph và các đường dẫn; `dependencyInsight` cho biết selected version và reasons/constraints. Với một module khác, thay `commons-lang3` bằng đúng `group:name` hoặc tên module cần điều tra.

Đừng bỏ qua một dependency mới chỉ vì nó là transitive: bản đó vẫn có thể ảnh hưởng runtime, vulnerabilities và license compliance.

## 9. Gradle enforce locked state thế nào?

Khi locking được bật và có state tương ứng, Gradle dùng locked version như **`strictly` constraint** cho module. Khác biệt cần nhớ:

- **Transitive dependency:** khi graph có module, lock ràng buộc selected version của module đó.
- **Direct dependency:** khai báo version thường được diễn giải là `require`. Nếu direct declaration tăng lên phiên bản cao hơn strict lock đang ghi, resolution sẽ xung đột.
- **Tập dependency:** lock state còn được đối chiếu với danh sách modules được resolve. Một module bị thêm/mất so với state có thể gây lỗi validation trong lock mode mặc định.
- **Thiếu lock state:** hành vi phụ thuộc lock mode; không nên cho rằng mọi configuration có dòng lock ngay khi vừa gọi `lockAllConfigurations()`.

Bảng ví dụ:

| Thay đổi trong build | Kết quả có thể thấy | Cách sửa |
| --- | --- | --- |
| Direct dependency yêu cầu version mới hơn locked version | Version conflict | Cập nhật state có chủ đích |
| Thêm direct/transitive module | Dependency mới ngoài lock | Regenerate relevant configs, review |
| Xóa module đã có trong lock | Lock entry không còn trong resolved graph | Regenerate state, kiểm đường dẫn |
| Đổi BOM/platform | Nhiều version hoặc module thay đổi | Review scope của BOM, tests và lockfile |
| Dynamic version có release mới | Graph vẫn dùng version đã khóa | Đúng mục đích; update khi phê duyệt |
| Repository không còn artifact bị khóa | Resolution fail | Điều tra repository, không sửa lock thủ công |
| Configuration mới chưa có lock state | Có thể fail ở STRICT | Ghi state cho config hoặc điều chỉnh scope |

### 9.1. Lock mode: DEFAULT, STRICT, LENIENT

Trong `build.gradle`, sau khi đã tạo baseline đầy đủ, có thể chọn:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
~~~

| Mode | Ý nghĩa |
| --- | --- |
| **DEFAULT** | Kiểm tra graph và locked versions với state đã tồn tại |
| **STRICT** | Giống DEFAULT, nhưng **fail nếu configuration bật locking mà thiếu lock state** |
| **LENIENT** | Vẫn pin dynamic versions nhưng nới kiểm tra thay đổi graph, ví dụ thêm/bớt modules hoặc transitive drift |

`LENIENT` hữu ích khi thử nghiệm nhưng giảm tính ràng buộc cho release CI. Nếu CI muốn phát hiện configuration bị quên khóa, **STRICT sau khi bootstrap đầy đủ** thường thích hợp hơn.

### 9.2. Changing modules/SNAPSHOT không phù hợp làm nền tảng khóa tái lập

Nếu dependency là `com.example:client:1.0-SNAPSHOT`, cùng tọa độ có thể bị publish lại với byte khác. Lockfile chỉ lưu `group:name:version`, không pin nội dung. Gradle cảnh báo khi persist lock state có changing modules. Với release pipeline, ưu tiên artifact versions **bất biến**, kết hợp locking và verification. Với integration snapshots, hiểu giới hạn và chính sách repository/TTL.

## 10. Multi-project build và file ở từng module

Ví dụ:

~~~text
root/
├── settings.gradle
├── build.gradle
├── app/
│   ├── build.gradle
│   └── gradle.lockfile
├── library/
│   ├── build.gradle
│   └── gradle.lockfile
└── gradle/
    └── wrapper/
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-demo'
include 'app', 'library'
~~~

`app/build.gradle` có thể khai báo:

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':library')
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

Đây là **trích đoạn project `:app`**, không phải một multi-project demo hoàn chỉnh, bởi `:library` còn cần plugin/variants, cấu trúc và dependencies đúng.

**Điểm quan trọng:**

1. Mỗi Gradle project có graph/configurations riêng. `app/gradle.lockfile` không được thay bằng `root/gradle.lockfile`.
2. Một lệnh ở root như `./gradlew dependencies --write-locks` không tự tạo state của mọi subproject.
3. Để resolve các modules đã bật khóa:

~~~bash
./gradlew :app:dependencies :library:dependencies --write-locks
~~~

4. Nếu một plugin tạo variants/extra configurations chỉ khi task đặc thù chạy, cần plan các invocation để cover chúng.
5. Với CI, kiểm đúng target module và configuration; root report không phản ánh mọi runtime graph.

### 10.1. Included builds và build logic

`buildSrc` hoặc included build `build-logic` có thể khai báo external libraries **để tạo Gradle plugin/convention**, nhưng chúng là build graph khác với application `runtimeClasspath`. Đừng coi `root/gradle.lockfile` mặc nhiên khóa mọi classpath của plugin/build-logic. Nếu cần, quản lý locking/verification trong từng build và kiểm trạng thái chúng được resolve ra sao.

### 10.2. Buildscript lock riêng

Nếu bật `buildscript.configurations.classpath.resolutionStrategy.activateDependencyLocking()`, Gradle ghi state ở **`buildscript-gradle.lockfile`**. Đây không phải bằng chứng mọi plugin ID trong `plugins {}` đã được khóa; plugin DSL dùng plugin resolution riêng. Khi review, phân biệt project dependencies, buildscript classpath và plugin dependencies.

## 11. Git merge conflict trong lockfile

Hai branch cùng sửa `gradle.lockfile` là tình huống bình thường. Đừng giải quyết bằng cách tùy tiện giữ toàn bộ bản `ours` hoặc `theirs`.

### 11.1. Vì sao merge text thủ công nguy hiểm?

Lockfile có thông tin về **module và danh sách configuration**. Ghép hai nhánh một cách cơ học có thể:

- Đưa hai versions không tương thích của cùng module vào state.
- Bỏ transitive module do một branch vừa thêm.
- Giữ module mà build model đã bỏ.
- Ghi state ở configuration khác hoặc sai scope.
- Làm CI fail hoặc, ở LENIENT, không còn bảo vệ graph như mong muốn.

### 11.2. Quy trình giải conflict an toàn

1. Merge/rebase **build.gradle, settings.gradle, version catalog, platform constraints** trước, xác định những thay đổi dependency nào cần giữ.
2. Nếu lockfile có conflict markers, đưa nó về một trạng thái văn bản hợp lệ tạm thời để Gradle chạy; **không coi kết quả đó là state được review**.
3. Regenerate lock state trên merged model:

~~~bash
# Single-project:
./gradlew dependencies --write-locks

# Multi-project, chỉ khi các module này tồn tại:
./gradlew :app:dependencies :library:dependencies --write-locks
~~~

4. Review `git diff` và chạy `dependencyInsight` với module quan trọng.
5. Chạy tests, check CI, xác nhận không còn dấu `<<<<<<<`/`=======`/`>>>>>>>`.
6. Commit lockfile đã được Gradle tái tạo và review.

Nếu chạy full `--write-locks` làm diff bất ngờ quá lớn, kiểm tra dynamic versions, repositories, BOM hoặc constraints đã bị thay bởi merge. Có thể cân nhắc selective updates sau khi có một baseline hợp lệ, nhưng **không tự viết lại selected graph bằng tay**.

## 12. CI: lockfile phải được kiểm tra, không tự động thay thế

Trong một pull request bình thường, CI nên dùng Wrapper và **không thêm `--write-locks` vào bước kiểm tra**:

~~~bash
./gradlew --version
./gradlew clean build
~~~

Đây là cách CI kiểm tra build model và **lock state đã được commit** còn thống nhất hay không, với điều kiện tasks/configurations liên quan được resolve. Để xác nhận configuration chưa có lock state, có thể áp dụng `LockMode.STRICT` sau khi toàn bộ baseline đã được tạo.

**Không khuyến nghị làm validation mặc định như sau:**

~~~bash
./gradlew clean build --write-locks
~~~

Lý do: CI có thể ghi lại lock state mới trước khi kiểm tra rằng trạng thái được PR commit còn hợp lệ, khiến update ngầm khó bị phát hiện. Nếu có automation nâng phiên bản, nó nên tạo **PR riêng với declaration + lockfile diff**, chạy tests và yêu cầu review.

### 12.1. Mức coverage cho CI

Không phải `build` luôn resolve toàn bộ custom configurations. Một project có `integrationTestRuntimeClasspath`, Android flavors hoặc toolchains riêng có thể cần tasks bổ sung. CI cần chạy những configurations/variants thực sự quan trọng. Với STRICT, configuration chưa có lock state có thể làm job fail, giúp phát hiện baseline thiếu, nhưng phải chuẩn bị state cho những mục tiêu hợp lệ trước.

### 12.2. Review dependency diff cùng tests

Checklist cho PR update:

- Thay khai báo hoặc version catalog đúng scope.
- Sinh/đổi lockfile bằng Gradle, không sửa tay.
- Xem modules thêm/bớt và selected versions cũ/mới.
- Kiểm `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` hoặc variants tương ứng.
- Chạy unit/integration/smoke tests và security policy checks.
- Xem changelog/migration guide, API/binary compatibility.
- Commit đúng file; không đưa cache, logs, secrets vào Git.
- Đảm bảo CI không tự viết state ngoài pull request.

## 13. Lockfile khác dependency verification, cache và catalog

| Cơ chế | Cái gì được bảo vệ | File/cờ |
| --- | --- | --- |
| **Dependency locking** | Selected module versions per configuration | `gradle.lockfile`, `--write-locks`, `--update-locks` |
| **Dependency verification** | Byte integrity/identity theo checksum/signature đáng tin | `gradle/verification-metadata.xml`, `--write-verification-metadata sha256` |
| **Version Catalog** | Alias và requested versions tập trung | `gradle/libs.versions.toml` |
| **Dependency cache** | Metadata/artifact files được lưu và tái sử dụng | `GRADLE_USER_HOME/caches/modules-2`, `--offline`, `--refresh-dependencies` |
| **Build Cache** | Reuse outputs của task cacheable | `--build-cache` và cấu hình build cache |
| **Configuration Cache** | Reuse task graph/configuration state | `--configuration-cache` |

### 13.1. Verification bổ sung cho locking

Nếu muốn bootstrap checksum:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Đây là **quy trình riêng** tạo hoặc cập nhật `gradle/verification-metadata.xml`. Nó không tương đương `--write-locks`. Metadata tạo tự động cần được review: công cụ có thể ghi checksum của artifact đang nằm ở repository, nhưng **không tự biết nguồn đó có đáng tin cậy hay không**.

Ví dụ một JAR giữ version `3.17.0` nhưng bị republish với byte khác. Lockfile vẫn giữ version string cũ; **verification** giúp phát hiện checksum/signature không khớp với giá trị đã tin cậy. Ngược lại, verification có hash hợp lệ cho nhiều artifact không tự ngăn dynamic selector đổi selected version khi chưa có locking.

### 13.2. Refresh không cập nhật khóa

`--refresh-dependencies` buộc Gradle kiểm tra lại dependency cache/repository metadata, nhưng **không bỏ locked version constraints** hay tự sinh lockfile mới.

So sánh:

~~~bash
# Cập nhật selected versions trong lock state:
./gradlew dependencies --update-locks org.apache.commons:commons-lang3

# Kiểm tra lại metadata cache mà vẫn tôn trọng lockfile:
./gradlew --refresh-dependencies dependencies --configuration runtimeClasspath

# Buộc task chạy lại, không có nghĩa cập nhật lock:
./gradlew --rerun-tasks build
~~~

`clean` chỉ dọn build outputs theo task plugin; `--offline` chỉ dùng dependency cache có sẵn cho resolution và không tải byte artifact thay cho lockfile. **Có lockfile không đồng nghĩa build có thể chạy khi hoàn toàn không có mạng và cache trống**.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Nâng direct version và gặp conflict | Declaration mới nhưng lock còn cũ | Dùng `--update-locks` đúng module/configurations |
| Thêm dependency nhưng lock không khớp | Graph mới có module ngoài state | Regenerate state, xem transitive dependencies |
| Xóa dependency mà vẫn còn lock entry | State cũ chưa được cập nhật | Chạy `--write-locks` cho config liên quan |
| Không có `gradle.lockfile` | Chưa bật locking, chưa resolve hoặc build fail | Xác nhận scope và lệnh `dependencies --write-locks` |
| Root lockfile tồn tại, subproject thiếu | Lockfile nằm theo từng project | Gọi `:app:dependencies --write-locks` |
| File mới không xuất hiện ở `git diff` | File chưa tracked | Xem `git status`/mở file hoặc `git add -N` |
| Lockfile bị ignore | `*.lockfile` hoặc ignore quá rộng | Sửa `.gitignore` và track lockfiles |
| `STRICT` fail configuration mới | Chưa có initial lock state | Resolve/write state, review variants |
| `--update-locks` làm đổi module khác | Graph/rules/constraints phụ thuộc nhau | Dùng `dependencyInsight` và review diff |
| Full `--write-locks` gây diff lớn | Nhiều configs/dynamic/BOM thay đổi | Xem scope; cân nhắc selective update |
| Merge conflict trong lockfile | Hai branch cập nhật graph khác nhau | Merge build model trước, regenerate bằng Gradle |
| Chỉ `--refresh-dependencies` nhưng version không đổi | Lock còn pin version cũ | Dùng update lock khi đã phê duyệt version mới |
| Cache có JAR nhưng offline fail | Thiếu metadata/plugin/toolchain/Wrapper | Prefetch cho đúng invocation |
| SNAPSHOT đổi byte mà lock không đổi | Lock không pin artifact bytes | Tránh changing modules trong release; dùng immutable version và verification |
| `buildEnvironment` khác lock app | Buildscript classpath khác project | Kiểm `buildscript-gradle.lockfile` nếu bật khóa |
| CI build xanh dù PR thiếu lock update | CI dùng `--write-locks` trước khi validate | Bỏ cờ khỏi validation, kiểm Git diff |
| Module bị force hoặc constraint bất ngờ | Version rules can thiệp resolution | Đọc `dependencyInsight`, kiểm platform/constraints |
| Lockfile mang `empty=...` | Config không có modules | Đây có thể là state hợp lệ; không xóa tay |
| Repository không có artifact locked | Artifact bị xóa, sai repo/auth | Sửa nguồn/repo policy, không đổi lock ngẫu nhiên |

### 14.1. Trình tự chẩn đoán

~~~text
Lỗi version/state ở configuration nào?
                  |
                  v
Khai báo nào vừa đổi (build.gradle/catalog/BOM)?
                  |
                  v
Lockfile của project ghi selected version gì?
                  |
                  v
Có module trực tiếp, transitive, constraint hoặc variant mới?
                  |
                  v
Chọn update có chủ đích:
--update-locks group:name hoặc --write-locks
                  |
                  v
Resolve đúng configuration và đọc dependencyInsight
                  |
                  v
Review Git diff + chạy tests
                  |
                  v
Commit/PR/CI
~~~

Đừng bắt đầu bằng cách xóa `~/.gradle/caches` hoặc sửa lockfile bằng tay. Đa số lỗi ở đây là sự khác biệt giữa **model mong muốn** và **resolved state đã commit**, không phải cache hỏng.

## 15. Nhu cầu nâng cao

### 15.1. Chỉ cho phép một nhóm module cập nhật nhanh

Gradle có cơ chế bỏ qua một số dependencies khi locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
    ignoredDependencies.add('com.example.internal:*')
}
~~~

Đây là **ngoại lệ làm giảm tính tái lập**. Ignored modules không được validation/writing như modules khác; transitive dependencies của chúng **không tự động đều được bỏ qua**. Chỉ dùng khi nhóm đã có policy rõ ràng, không dùng `*:*` để tắt toàn bộ locking.

### 15.2. Tách lockfile theo bối cảnh có chủ đích

Gradle cho phép tùy chỉnh vị trí lockfile:

~~~groovy
// Ví dụ độc lập cho project đặc thù có nhiều lock states.
def target = 'scala-2.12'

dependencyLocking {
    lockFile = file(projectDir.toString() + '/locking/gradle-' + target + '.lockfile')
}
~~~

Đây là **trích đoạn custom lockFile location**, không bắt buộc cho Java demo. Khi dùng nhiều lockfiles, phải commit tất cả state được hỗ trợ, đảm bảo CI chọn đúng file theo cấu hình target và không dùng biến môi trường không kiểm soát để tạo lockfile “mỗi máy một khác”.

### 15.3. Migration lockfiles legacy

Một số Gradle builds cũ từng có file khóa **theo configuration**. Khi nâng Gradle và ghi state bằng cơ chế hiện đại, Gradle có thể chuyển sang một file **`gradle.lockfile` per project** và dọn các legacy files đã được chuyển. Cần review coverage trước khi xóa file cũ, chạy tests/CI trên Wrapper mục tiêu, và commit migration như một thay đổi rõ ràng.

### 15.4. Bỏ locking ở một configuration

Có thể không gọi `activateDependencyLocking()` ở configuration đó, hoặc dùng `deactivateDependencyLocking()` khi cần ghi đè policy chung. State cũ có thể được Gradle dọn khi một lần `--write-locks` resolve configuration liên quan. Đừng bỏ khóa toàn build chỉ vì một configuration đặc thù không phù hợp.

## 16. Bài tập thực hành có đáp án

### Bài A — dynamic version và lock

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

Lock state minh họa có `org.apache.commons:commons-lang3:3.17.0=runtimeClasspath`. Release `3.18.0` xuất hiện, build có tự chọn 3.18.0 không? **Không nếu lock state đang áp dụng**, vì selected version được khóa. Muốn update cần lệnh Gradle và review.

### Bài B — vì sao root `dependencies --write-locks` chưa đủ?

Root multi-project chạy `./gradlew dependencies --write-locks` nhưng `app/gradle.lockfile` chưa có. **Lý do:** task root không tự resolve tất cả subprojects. Cần bật locking ở `:app` và chạy `:app:dependencies --write-locks` hoặc task thực sự resolve configuration đó.

### Bài C — update chỉ một module

~~~bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
~~~

Cờ này hàm ý write locks. Vì sao vẫn phải review module khác? **Transitive graph có thể thay đổi** theo resolution rules của version mới.

### Bài D — Git diff file mới

File `gradle.lockfile` vừa sinh nhưng `git diff -- gradle.lockfile` không hiển thị. **Lý do:** file untracked. Kiểm `git status --short`, mở file hoặc dùng `git add -N gradle.lockfile` để xem diff trước khi commit.

### Bài E — có thể sửa `3.17.0` thành `3.18.0` bằng text editor?

Có thể sửa văn bản, nhưng **không nên**: lock state là kết quả resolution, có thể có nhiều configurations và transitive modules. Sửa khai báo và chạy `--update-locks`/`--write-locks` để Gradle sinh state hợp lệ.

### Bài F — lockfile chống JAR bị sửa?

Không. Version locking giữ tọa độ module, **dependency verification** giúp kiểm tra checksum/signature đáng tin cậy. Kết hợp hai cơ chế và repository artifact bất biến nếu cần tính tái lập/bảo mật.

### Bài G — CI có nên luôn chạy `--write-locks`?

Không, bởi bước validate sẽ tự cập nhật state thay vì kiểm tra state đã commit. CI thường nên chạy build/test **không có cờ ghi lock**; có pipeline update riêng tạo PR để review.

### Bài H — merge conflict

Hai branch cùng sửa `gradle.lockfile`. Cách đúng là hợp nhất declarations/constraints, regenerate state bằng Gradle, review toàn bộ diff, kiểm `dependencyInsight` và tests. Không chọn `ours`/`theirs` cho cả file một cách ngẫu nhiên.

### Bài I — STRICT thiếu state

Plugin tạo `integrationTestRuntimeClasspath` chưa có lock state; STRICT fail. Cần quyết định config này phải được khóa không và sinh state nếu có. Đừng mặc định chuyển cả project sang LENIENT chỉ để tránh lỗi.

## 17. Checklist trước khi merge pull request

1. Có **lý do** nâng dependency và version mục tiêu được review?
2. Declaration ở `build.gradle`/catalog/BOM/constraints đã cập nhật chính xác?
3. Đã tạo state bằng `--update-locks` khi cần selective, `--write-locks` khi cần full update?
4. Đã xem **`gradle.lockfile` và subproject/buildscript lockfiles** liên quan?
5. Có transitive modules nào thêm/bớt/đổi version cần kiểm tra riêng?
6. Đã dùng `dependencies`/`dependencyInsight` ở đúng project/configuration?
7. Đã kiểm tra ABI/API, release notes và security policy của version mới?
8. Đã chạy compile, test và integration/smoke tasks trên Wrapper/JDK mục tiêu?
9. Nếu dùng dependency verification, `verification-metadata.xml` và checksums đã được review?
10. Lockfile được **track trong Git**, không bị ignore và không còn conflict marker?
11. CI có validate **state được commit**, không auto-write state trước khi check?
12. PR đã ghi rõ **module cũ → mới, lý do, phạm vi và kết quả kiểm chứng**?

## Tài liệu tham khảo chính thức

- [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html): cấu hình locking, file format, `--write-locks`, `--update-locks`, modes, transitive và migration.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): các cờ liên quan dependency locks.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): vai trò declarable/resolvable/consumable.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`/`dependencyInsight` và selected versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum, signature, `verification-metadata.xml`.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): dynamic/changing versions và `--refresh-dependencies`.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): aliases và requested versions.
- [Maven Central — Commons Lang 3.18.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.18.0): artifact dùng cho ví dụ nâng version.
