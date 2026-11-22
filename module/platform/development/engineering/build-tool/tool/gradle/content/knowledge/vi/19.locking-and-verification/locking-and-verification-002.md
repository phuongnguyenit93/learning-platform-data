# Dependency locking và phạm vi configuration cần khóa

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Khóa và xác minh

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **dependency locking** chốt lại **những phiên bản module thực sự được resolve**, bao gồm dependency bắc cầu, để các lượt build sau không âm thầm đổi dependency graph.
2. Phân biệt **configuration được khai báo** (implementation, testImplementation), **configuration được resolve** (compileClasspath, runtimeClasspath, testRuntimeClasspath) và những **variant dùng cho consumer**.
3. Chọn phạm vi khóa: **một số configurations quan trọng** hay **lockAllConfigurations()**; biết việc khóa trong một project không tự kích hoạt trên mọi subproject.
4. Tạo **gradle.lockfile** bằng **--write-locks**, đọc định dạng file và nhận ra lệnh chỉ ghi lock state cho những configurations **thực sự được resolve**.
5. So sánh **LockMode.DEFAULT**, **LockMode.STRICT** và **LockMode.LENIENT**; hiểu khi nào build phải thất bại vì thiếu lock state hay dependency graph thay đổi.
6. Cập nhật đúng cách bằng **--update-locks group:name**, hiểu giới hạn của selective updates và biết review thay đổi trong lockfile trước khi commit.
7. Chạy dự án **Gradle Groovy DSL + Java 17**, tạo khóa cho compileClasspath/runtimeClasspath, kiểm tra kết quả Java và thử thay phiên bản để thấy vì sao khóa có giá trị.
8. Phân biệt khóa phiên bản với **version catalog**, **constraints/strictly**, **resolutionStrategy.force**, **build cache**, **dependency verification** và việc dùng JAR cục bộ.
9. Thiết kế phạm vi khóa hợp lý cho **multi-project build, CI, test, annotation processors và buildscript/plugin classpaths**, tránh tưởng mọi thứ đều đã khóa chỉ vì có một file.

**Kết luận trước:** Dependency locking là chính sách **theo configuration được resolve trong từng project**, không phải một nút duy nhất bảo đảm mọi dependency trong toàn bộ repository đã bị cố định. Lockfile ghi các **module versions đã chọn**, không bảo đảm byte của artifact, không tự tải thư viện còn thiếu và không thay thế việc kiểm tra tương thích.

## 1. Vì sao cần dependency locking?

Một thư viện được khai báo với **version động**:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.+'
}
~~~

có thể resolve ra phiên bản 3.x mới nhất khả dụng theo các repositories, metadata và quy tắc Gradle ở thời điểm thực thi. Tuần này build có thể chọn một version, tuần sau một version mới hơn. Code không đổi nhưng thư viện hoặc dependency graph đã đổi, gây:

- **Không tái lập:** Developer và CI nhận các module versions khác nhau.
- **Lỗi bất ngờ:** Một phiên bản mới thay đổi hành vi/API.
- **Khó điều tra:** Khác biệt không nằm trong Git diff của mã nguồn.
- **Không rõ độ phủ:** Một phiên bản transitive đổi dù dependency trực tiếp vẫn giữ nguyên.

**Dependency locking** lưu lại các versions đã được chọn trong một lần resolution, rồi dùng lock state để kiểm tra những lần resolution tiếp theo. Với graph/module requirements tương thích lock state, Gradle tiếp tục dùng phiên bản đã khóa ngay cả khi repository có phiên bản mới hơn phù hợp với selector động.

Locking không đòi mọi dependency phải viết version động. Ngay cả khi direct dependencies dùng versions cụ thể, **transitive versions, constraints và graph tổng thể** vẫn có thể thay đổi; lockfile là bản ghi resolved state để review.

### 1.1. Mô hình hoạt động

~~~text
build.gradle:
    implementation 'group:module:3.+'
               |
               v
runtimeClasspath / compileClasspath được resolve
               |
       +-------+--------+
       |                |
  Chưa có lock      Đã có lock
       |                |
  --write-locks      Gradle áp locked versions
       |            và kiểm tra resolved graph
       v                |
gradle.lockfile     +---+-------------------+
được tạo            |                       |
                Khớp lock                Lệch lock
                    |                       |
                  PASS              DEFAULT/STRICT có thể FAIL
~~~

**Điều quan trọng:** Khóa áp dụng vào **dependency resolution**, không làm task compileJava hoặc run “bất biến” về mọi mặt. Task outputs, JDK, plugin, environment, repositories và byte artifact cũng phải được kiểm soát nếu muốn build hoàn toàn tái lập.

## 2. Khóa configuration nào?

Gradle tạo nhiều **Configuration** với những vai trò khác nhau:

| Vai trò | Ví dụ | Có phải nơi nên chủ động resolve và khóa? |
|---|---|---|
| **Declarable / dependency scope** | implementation, api, compileOnly, runtimeOnly, testImplementation | Không: đây thường là bucket để khai báo; không phải graph cuối của compiler/JVM |
| **Resolvable** | compileClasspath, runtimeClasspath, testCompileClasspath, testRuntimeClasspath | Có: graph thực sự được resolve cho compiler/test/JVM |
| **Consumable / outgoing** | apiElements, runtimeElements của java-library | Không tự resolve như classpath consumer; khóa tác động tại graph được resolve |

Bạn có thể gọi activateDependencyLocking() trên một configuration không resolvable, nhưng nó **không có lock state hữu ích**: tài liệu Gradle xác nhận chỉ configurations **có thể resolve** mới được gắn lock state.

Vì vậy hãy bắt đầu bằng cách xác định task nào dùng classpath nào, rồi khóa những resolvable configurations phù hợp.

### 2.1. Khóa riêng compileClasspath và runtimeClasspath

Trong build.gradle của project dùng Java plugin:

~~~groovy
configurations.named('compileClasspath') {
    resolutionStrategy.activateDependencyLocking()
}

configurations.named('runtimeClasspath') {
    resolutionStrategy.activateDependencyLocking()
}
~~~

Ý nghĩa:

- **compileClasspath**: module versions dùng để biên dịch mã nguồn main.
- **runtimeClasspath**: module versions dùng khi chạy app hoặc một JavaExec task lấy runtime classpath.
- **testCompileClasspath** và **testRuntimeClasspath**: chưa được khóa bởi hai block này.
- **annotationProcessor**: chưa được khóa nếu bạn không cấu hình thêm.
- Rule trong project này **không tự áp sang subproject khác**.

Đây là phương án phù hợp khi bài học hoặc dự án có **chủ đích khóa hai classpath của mã chính** trước, rồi mở rộng dần theo yêu cầu.

### 2.2. Khóa tất cả configurations của một project

Gradle cung cấp DSL đơn giản:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Nó bật locking cho **project configurations**, kể cả những configurations được plugin thêm, nhưng **chỉ configurations resolvable mới có lock state** khi được resolve. Tên phương thức lockAllConfigurations không có nghĩa Gradle sẽ tự resolve mọi graph ngay lập tức.

**Giới hạn quan trọng:**
- Áp dụng trong **project có build.gradle chứa đoạn này**.
- **Không tự bao gồm buildscript classpath**; cần cấu hình riêng nếu muốn khóa.
- **Không tự áp dụng qua mọi subprojects** chỉ vì viết ở root build.gradle.
- Không bảo đảm tất cả configurations sẽ được ghi lockfile trong một lần chạy **build**; chỉ những graph thực sự được resolve trong lượt chạy đó được ghi.
- Có thể bao phủ test/tool configurations mà bạn chưa sẵn sàng quản lý, nên cần review scope.

### 2.3. Giới hạn theo source set và task

| Bạn muốn kiểm soát | Configurations nên xem xét |
|---|---|
| Biên dịch main Java | compileClasspath |
| Chạy ứng dụng main | runtimeClasspath |
| Biên dịch tests | testCompileClasspath |
| Chạy tests | testRuntimeClasspath |
| Xử lý annotation | annotationProcessor, testAnnotationProcessor nếu có |
| Test fixtures từ plugin java-test-fixtures | Các resolvable classpaths/variants liên quan đến fixture |
| Tool code generation/plugin-defined tool classpath | Resolvable configuration mà plugin sử dụng |
| Android/Kotlin/Scala/custom JVM plugin | Tên classpaths/variants đúng theo plugin, không tự mặc định dùng tên Java Plugin |

Một chương trình Java chạy bằng task **run** và một suite test có thể có dependency graph **khác nhau**; khóa runtimeClasspath không đồng nghĩa testRuntimeClasspath đã được bảo vệ. Nếu một runtime issue chỉ xảy ra khi chạy test, cần khóa/kiểm tra graph của test.

### 2.4. Multi-project build: mỗi project có scope và lockfile riêng

Ví dụ:

~~~text
my-product/
├── settings.gradle
├── build.gradle
├── gradle.lockfile           # chỉ khi root có locked configurations
├── core/
│   ├── build.gradle
│   └── gradle.lockfile       # lock state của project :core
└── app/
    ├── build.gradle
    └── gradle.lockfile       # lock state của project :app
~~~

Mỗi project có các Configuration objects riêng. Khi **:app:runtimeClasspath** chứa một dependency project(':core'), graph mà :app resolve có thể chứa các external modules bắc cầu từ :core. Lock state của app ghi versions có mặt trong **app runtime graph**; điều đó **không tự khóa :core:compileClasspath** khi core được biên dịch riêng.

**Tình huống sai hay gặp:** Root build.gradle có lockAllConfigurations() và nhóm nghĩ mọi subproject đã được khóa. Thực tế root chỉ cấu hình **root project**. Cần áp dụng logic locking vào các subprojects cần nó, lý tưởng qua **convention plugin** được các project sử dụng rõ ràng.

## 3. Phạm vi của dependencyLocking và của lockfile

### 3.1. Một file gradle.lockfile cho mỗi project

Trong các phiên bản Gradle hiện đại, lock state mặc định được lưu tại:

~~~text
<project-directory>/gradle.lockfile
~~~

Ví dụ:

~~~text
app/gradle.lockfile
core/gradle.lockfile
~~~

Đối với **buildscript classpath** được khóa riêng, tên tệp mặc định là:

~~~text
buildscript-gradle.lockfile
~~~

File này là **bản ghi generated** và nên được commit vào Git. Không nên tự sửa text để ép một version mà không thực hiện resolution có kiểm soát, vì chỉnh thủ công dễ làm mất quan hệ giữa một module và những configurations sử dụng nó.

### 3.2. Cấu trúc ví dụ

Giả sử một project chỉ khóa compileClasspath và runtimeClasspath, cả hai đều resolve Commons Lang 3.14.0, lockfile có thể chứa:

~~~properties
# This is a Gradle generated file for dependency locking.
# Manual edits can break the build and are not advised.
# This file is expected to be part of source control.
org.apache.commons:commons-lang3:3.14.0=compileClasspath,runtimeClasspath
~~~

Đây là **minh họa của các dòng quan trọng**, không phải cam kết file do mọi Gradle version sinh ra có chính xác các comment/line ordering ấy.

Cú pháp chính:

~~~text
group:artifact:resolvedVersion=configuration1,configuration2
~~~

- Một module có thể xuất hiện trong **nhiều configurations**.
- Các module và configuration names trong file được sắp xếp để diff dễ đọc.
- Dòng **empty=...** có thể ghi những configurations được khóa nhưng không resolve ra external modules.
- File chủ yếu ghi **resolved external module coordinates**. Project dependency và file dependency không tự có một version module để xuất hiện theo định dạng group:artifact:version, nhưng **các external dependencies bắc cầu** qua project dependency vẫn có thể được ghi trong graph của consumer.

### 3.3. Lockfile không giống Gradle cache

**gradle.lockfile**: bản ghi version state nằm trong project, nên đưa vào version control.

**Gradle User Home/caches**: nơi Gradle lưu metadata/artifacts đã tải. Cache có thể đầy/thiếu mà lockfile không thay đổi. Lockfile yêu cầu version cụ thể; nếu JAR không có trong cache và bạn chạy --offline, Gradle vẫn có thể thất bại.

**build/**: output compilation/task của project, thường được xóa bởi clean. Chạy clean **không xóa** lockfile đã commit hoặc tự đổi versions.

### 3.4. Lockfile tùy chỉnh

Gradle hỗ trợ cấu hình path của lockfile qua dependencyLocking:

~~~groovy
dependencyLocking {
    lockFile = file("$projectDir/locking/gradle-main.lockfile")
}
~~~

Đây là một lựa chọn **thay đổi tên/vị trí**, không phải bắt buộc. Nếu bạn áp dụng vào multi-project, phải bảo đảm **mỗi project có file riêng**; không cho nhiều subprojects cùng ghi/đọc một file path chung rồi tưởng states sẽ tự ghép.

Với hầu hết Java projects, để **gradle.lockfile mặc định** đơn giản, dễ nhận diện và được công cụ Gradle hỗ trợ hơn là tùy chỉnh khi chưa có lý do cụ thể.

## 4. Bật locking và tạo lock state lần đầu

### 4.1. Bật có chọn lọc

Ví dụ một app/build.gradle:

~~~groovy
plugins {
    id 'application'
}

configurations.named('compileClasspath') {
    resolutionStrategy.activateDependencyLocking()
}

configurations.named('runtimeClasspath') {
    resolutionStrategy.activateDependencyLocking()
}
~~~

Đây chỉ là snippet minh họa phần locking; dự án đầy đủ có repository, dependency, Java source ở mục 6.

Bật locking không tự viết file ngay. Phải **resolve các configurations đã bật** trong một invocation có **--write-locks**.

### 4.2. Lệnh tạo lockfile

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle ghi lock state cho những **resolvable configurations có bật locking và đã được resolve trong lượt chạy đó**. Theo tài liệu hiện hành, task **dependencies** thường resolve các resolvable configurations của **project nơi task đó được chạy**, nên là cách bootstrap thuận tiện.

**Multi-project warning:** Chạy **./gradlew dependencies --write-locks** ở root không tự đồng nghĩa tất cả subprojects đã được resolve. Để khóa :app và :core, hãy chạy task dependencies theo path:

~~~bash
./gradlew :app:dependencies :core:dependencies --write-locks
~~~

Chỉ chọn các projects thật sự tồn tại và có locking enabled. Bạn cũng có thể resolve riêng đúng classpath nếu muốn scope chặt:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath --write-locks
./gradlew :app:dependencies --configuration runtimeClasspath --write-locks
~~~

Với lệnh chỉ định **một configuration**, phần lock state của configuration được resolve sẽ được ghi; nó không chứng minh những configurations khác đã được bao phủ.

### 4.3. Có thể viết một task resolve tất cả configurations

Với build có các configurations đặc biệt, nếu muốn chủ động resolve mọi resolvable configuration trong một project, Gradle documentation minh họa một task dạng:

~~~groovy
tasks.register('resolveAndLockAll') {
    notCompatibleWithConfigurationCache(
        'Lọc và resolve configurations trong task action'
    )

    doFirst {
        if (!gradle.startParameter.writeDependencyLocks) {
            throw new GradleException(
                'Chạy với --write-locks để ghi lock state'
            )
        }
    }

    doLast {
        configurations.matching {
            it.canBeResolved
        }.each {
            it.resolve()
        }
    }
}
~~~

Đây là một **snippet bổ sung** cho build.gradle (cần class GradleException nằm trong Gradle API). Chạy:

~~~bash
./gradlew resolveAndLockAll --write-locks
~~~

Nhưng không nên dùng cách này mù quáng: một số configurations phụ thuộc hệ điều hành, toolchain, credentials hoặc môi trường native/Android mà không thể resolve trên mọi máy. Task được đánh dấu không tương thích configuration cache trong minh họa này. Hãy lọc đúng configs, hoặc ưu tiên **dependencies --write-locks** nếu đã đáp ứng yêu cầu.

### 4.4. Không ghi lock nếu build thất bại

Gradle không ghi một lock state mới nếu build thất bại, tránh lưu trạng thái chưa được xác minh. Nếu cần kiểm tra vì sao file chưa xuất hiện, hãy xem **task có thật sự resolve configuration đã bật locking không** và build có hoàn thành thành công không, thay vì tự tạo gradle.lockfile thủ công.

## 5. Ba chế độ khóa: DEFAULT, STRICT và LENIENT

Gradle có các chế độ LockMode:

| Mode | Khi đã có lock state | Khi một locked configuration chưa có lock state | Khi graph đổi ngoài ý muốn |
|---|---|---|---|
| **DEFAULT** | Đối chiếu versions/modules với lock state | Không tự fail chỉ vì thiếu state | Mismatch với state có sẵn → resolution thất bại |
| **STRICT** | Như DEFAULT | **Thất bại** khi cần resolve config đã bật locking nhưng thiếu state | Mismatch → thất bại |
| **LENIENT** | Dùng state để neo dynamic versions, linh hoạt với những thay đổi khác | Không thực thi chính sách đầy đủ như STRICT | Có thể chấp nhận thêm/bớt module hay đổi version trong nhiều trường hợp |

**Không nhầm:**
- DEFAULT vẫn **kiểm tra nghiêm** với state **đã có**; tên “default” không có nghĩa tự bỏ qua mọi mismatch.
- STRICT thêm kiểm tra **phải có lock state** khi locked configuration được resolve.
- LENIENT không phải lựa chọn phù hợp để tuyên bố CI đang kiểm soát đầy đủ dependency graph; nó có thể cho qua những thay đổi mà DEFAULT sẽ chặn.

### 5.1. Cấu hình STRICT sau khi đã tạo baseline

~~~groovy
import org.gradle.api.artifacts.dsl.LockMode

dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}
~~~

Nếu bạn bật STRICT **trước lần đầu tạo lock state**, một build bình thường có thể thất bại vì configurations chưa có lock state. Cách dễ học:

1. Bật locking với DEFAULT.
2. Resolve và ghi states qua --write-locks.
3. Kiểm tra file và commit.
4. Sau đó bật STRICT trong những projects/CI cần bảo đảm không có locked configuration bị bỏ sót.

**Có thể chạy --write-locks để bootstrap hoặc cập nhật state**, nhưng không nên dùng flag này trong mọi lượt CI build thường xuyên, vì nó cho phép ghi lại lockfile thay vì chỉ xác nhận state đã commit.

### 5.2. Cấu hình LENIENT

~~~groovy
import org.gradle.api.artifacts.dsl.LockMode

dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.LENIENT
}
~~~

LENIENT vẫn có thể neo dynamic versions nhưng cho phép những thay đổi dependency graph mà DEFAULT/STRICT sẽ phát hiện. Nó có ích khi khám phá dependency changes nhưng không nên quảng bá như mức bảo đảm reproducibility tương đương STRICT.

**Lời khuyên:** Mục tiêu release ổn định thường thích hợp với DEFAULT hoặc STRICT sau khi baseline đầy đủ; LENIENT dành cho workflow kiểm thử/khám phá có rủi ro được hiểu rõ.

## 6. Thực hành hoàn chỉnh: Gradle + Java 17

Trong bài lab này, ta dùng dependency ngoài **Commons Lang 3.14.0**, khóa cả compileClasspath và runtimeClasspath, sau đó **chủ động đổi yêu cầu lên phiên bản cao hơn** để quan sát lock mismatch.

### 6.1. Cấu trúc project

~~~text
dependency-locking-lab/
├── settings.gradle
├── build.gradle
├── gradlew                    # có khi dùng Wrapper
├── gradlew.bat
├── gradle/wrapper/...         # có khi dùng Wrapper
├── gradle.lockfile            # được Gradle sinh sau --write-locks
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

**Yêu cầu:**
- JDK 17 hoặc Java 17 toolchain được provision.
- Gradle hỗ trợ toolchain 17; khuyến nghị dùng Gradle Wrapper được commit vào repository.
- Kết nối Maven Central cho lần resolve dependency đầu tiên.

Nếu chưa có Wrapper, tạo các file source/config trước, dùng Gradle đã cài chạy **gradle wrapper** từ root, rồi sử dụng **./gradlew** trên Unix hoặc **.\gradlew.bat** trên Windows.

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'dependency-locking-lab'
~~~

### 6.3. build.gradle đầy đủ

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.Main'
}

dependencies {
    // Phiên bản dùng để tạo lock state đầu tiên.
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

// Chỉ khóa hai resolvable classpaths của main.
configurations.named('compileClasspath') {
    resolutionStrategy.activateDependencyLocking()
}

configurations.named('runtimeClasspath') {
    resolutionStrategy.activateDependencyLocking()
}
~~~

Ở đây ta cố ý **không lockAllConfigurations** để dễ nhìn rõ sự khác biệt giữa “đã khóa main classpaths” và “đã khóa mọi configuration”. Những cấu hình test hoặc annotationProcessor còn chưa được bật locking trong bài lab.

### 6.4. Java source

**src/main/java/demo/Main.java**

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "message=" + StringUtils.capitalize("gradle")
        );
    }
}
~~~

Đây là Java 17 hợp lệ; sử dụng StringUtils.capitalize(String) từ Commons Lang.

### 6.5. Tạo lockfile

Linux/macOS:

~~~bash
./gradlew dependencies --write-locks
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --write-locks
~~~

Lệnh giải quyết các configurations của **project hiện tại** do task dependencies xử lý, gồm compileClasspath/runtimeClasspath đã bật locking. Sau khi hoàn thành thành công, Gradle tạo **gradle.lockfile** tại project root. Một dòng quan trọng kỳ vọng:

~~~properties
org.apache.commons:commons-lang3:3.14.0=compileClasspath,runtimeClasspath
~~~

File thật còn có comment hoặc những entries theo Gradle version và các configurations được resolve khác; không nên khẳng định chỉ có đúng một dòng.

**Lưu ý:** Nếu một project mới thêm test dependencies hoặc annotation processors nhưng bài lab không bật khóa những configurations đó, chúng không được ghi thành lock state chỉ vì dependencies task có hiển thị chúng.

### 6.6. Chạy Java app và kiểm chứng kết quả

~~~bash
./gradlew -q run
~~~

Dòng stdout do **Main.main** in:

~~~text
message=Gradle
~~~

Các thông báo Gradle và download phụ thuộc môi trường nên không nằm trong expected stdout cố định.

Sau khi lock state tồn tại, một lần run bình thường có thể resolve Commons Lang 3.14.0 từ cache/repository. Nó cũng kiểm tra những locked configurations được sử dụng. **Bạn không cần --write-locks cho các build thông thường**.

### 6.7. Đọc resolved classpaths

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Mục tiêu là thấy **selected version 3.14.0** và đối chiếu nó với gradle.lockfile. dependencyInsight giải thích vì sao module được chọn, bao gồm khi có locking constraints hoặc những yêu cầu transitive khác.

Bạn có thể ghi lại kết quả report trước khi đổi versions để so sánh sau. Không dùng mỗi **build.gradle** làm bằng chứng selected version trong những graph có constraints/conflicts.

### 6.8. Thí nghiệm A: đổi yêu cầu lên version mới nhưng KHÔNG cập nhật lock

Tạm đổi dòng dependencies thành:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

**Không chạy --write-locks.** Bây giờ direct request yêu cầu 3.17.0, trong khi lock state cũ pin 3.14.0. Theo cơ chế Gradle hiện đại, lock state được áp dưới dạng strict constraints; direct requirement 3.17.0 không tương thích với strict 3.14.0. Khi resolve compileClasspath/runtimeClasspath, build sẽ **fail** thay vì âm thầm dùng 3.17.0.

Thử:

~~~bash
./gradlew compileJava
~~~

Lỗi có thể nói về version constraints/lock state không tương thích, cách diễn đạt cụ thể tùy Gradle version. Đừng ghi một stack trace cố định; ý nghĩa quan trọng là **lock mismatch được phát hiện**.

### 6.9. Thí nghiệm B: cập nhật lock state có chủ đích

Sau khi quyết định nâng lên 3.17.0 và chấp nhận kết quả kiểm thử, chạy:

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle ghi lại state cho các configurations được resolve. Dòng của module khi nâng thành công:

~~~properties
org.apache.commons:commons-lang3:3.17.0=compileClasspath,runtimeClasspath
~~~

Sau đó:

~~~bash
./gradlew -q run
~~~

Stdout vẫn là:

~~~text
message=Gradle
~~~

Vì StringUtils.capitalize đã có ở cả hai version. Tuy nhiên **kết quả giống nhau không đủ chứng minh mọi tính năng ứng dụng đều tương thích**; cần chạy tests và review dependency graph.

**Quy trình review đúng:** Xem Git diff gradle.lockfile, xác minh chỉ những modules/configurations dự kiến thay đổi, kiểm tra dependencies/constraints liên quan, chạy test và commit **build.gradle + gradle.lockfile** cùng nhau.

### 6.10. Thí nghiệm C: bật STRICT sau baseline

Sau khi có đầy đủ lock state cho hai classpaths chính, thêm:

~~~groovy
import org.gradle.api.artifacts.dsl.LockMode

dependencyLocking {
    lockMode = LockMode.STRICT
}
~~~

Đoạn này **bổ sung** vào build.gradle đã có hai block activateDependencyLocking. STRICT làm build thất bại nếu cần resolve một configuration đã bật locking nhưng thiếu lock state; với hai configurations đã có state, build hợp lệ sẽ tiếp tục.

Nếu sau này bạn bật locking cho **testRuntimeClasspath** mà không tạo lock state cho nó, khi graph testRuntimeClasspath được resolve, STRICT có thể báo thiếu lock. Cần generate/review/commit state thay vì tắt STRICT để che lỗi.

### 6.11. Thí nghiệm D: khóa thêm testRuntimeClasspath

Thêm:

~~~groovy
configurations.named('testRuntimeClasspath') {
    resolutionStrategy.activateDependencyLocking()
}
~~~

Sau đó:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath --write-locks
~~~

Gradle tạo hoặc cập nhật lock state cho testRuntimeClasspath khi graph được resolve. Nếu còn các configurations khác, hãy tiếp tục khóa có chủ đích và tạo state cho chúng. **Chỉ vì runtimeClasspath của main đã khóa không có nghĩa test runtime đã khóa.**

Nếu testRuntimeClasspath không chứa external modules, lockfile có thể ghi nó vào dòng **empty=...**. Dòng empty không phải lỗi; nó cho biết configuration đã được tính tới nhưng không có external modules cần liệt kê.

## 7. --write-locks và --update-locks: đừng nhầm

### 7.1. --write-locks

~~~bash
./gradlew dependencies --write-locks
~~~

Ý nghĩa: với configurations được resolve và bật locking, **ghi lại lock state** của kết quả resolution. Nếu file đã tồn tại, những entries có thể được cập nhật khi cần. Tác dụng phụ: một thao tác tạo/update có chủ đích, không phải flag nên dùng cho mọi lần build CI.

**Mẹo review:** Kiểm tra Git diff trước khi commit. Một thay đổi một direct dependency có thể khiến nhiều transitive dependencies đổi versions; điều đó không mặc nhiên là bug, nhưng cần hiểu vì sao.

### 7.2. --update-locks cho module cụ thể

~~~bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
~~~

Theo tài liệu Gradle:

- Cú pháp flag nhận **group:name**; nếu có nhiều modules, phân tách bằng dấu phẩy.
- **--update-locks tự bao hàm --write-locks**, nên không cần thêm cả hai.
- Lock state cũ vẫn được dùng để giữ các modules **không nằm trong danh sách update** khi giải quyết graph.
- Module mục tiêu có thể được nâng/hạ theo dependency declarations, version selectors và resolution rules hiện có.
- Một số modules khác **vẫn có thể thay đổi** khi các quan hệ dependency yêu cầu, vì graph phải nhất quán. Vì vậy selective update không bảo đảm Git diff chỉ có một dòng.

Ví dụ cập nhật hai modules:

~~~bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3,org.slf4j:slf4j-api
~~~

Bạn cũng có thể chỉ định wildcard được Gradle hỗ trợ, chẳng hạn **org.apache.commons:*** cho tất cả modules trong group. Không dùng wildcard bừa bãi trong CI nếu mục tiêu là update một thư viện.

### 7.3. --update-locks không tự yêu cầu version mới

Giả sử build.gradle yêu cầu chính xác Commons Lang 3.14.0 và graph không có lý do chọn 3.17.0. Chạy:

~~~bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
~~~

**không tự có nghĩa** module sẽ thành 3.17.0. Muốn nâng bản, phải thay dependency declarations/constraints/version catalog hoặc rule phù hợp, hoặc đang dùng một selector động có version mới đủ điều kiện.

**Tóm tắt:** --update-locks cho phép state của module mục tiêu được thay đổi khi resolution; nó không phải lệnh “upgrade to latest” một cách độc lập.

### 7.4. Quy trình cập nhật an toàn

1. Tìm modules muốn thay bằng dependencyInsight.
2. Xác định direct vs transitive requests, compatibility và thông tin security.
3. Sửa version declarations/constraints hoặc quyết định dải version mới.
4. Chạy đúng project(s) với --update-locks group:name.
5. Kiểm tra git diff và tất cả modules/configurations bị thay đổi.
6. Chạy build/tests/integration tests cần thiết.
7. Commit thay đổi code/config và lockfile trong cùng change set.
8. CI chạy **không có --write-locks/--update-locks** để xác minh trạng thái đã commit.

## 8. Những tình huống khóa theo phạm vi

### 8.1. Ứng dụng Java độc lập

**Tối thiểu:** Khóa compileClasspath và runtimeClasspath; nếu có tests, khóa testCompileClasspath/testRuntimeClasspath. Nếu dự án có annotation processors hoặc tool configuration ảnh hưởng code generation, cân nhắc khóa cả graph tương ứng.

**Ưu tiên thực tế:** Tùy độ nghiêm ngặt CI, dùng lockAllConfigurations() sau khi kiểm kê plugins/configurations rồi bootstrap lock states. Có thể bật STRICT để phát hiện configs mới chưa được khóa.

### 8.2. Thư viện Java sẽ publish

**Khác ứng dụng:** Library cần đảm bảo phiên bản publish được consumer giải quyết phù hợp. Locking giữ **resolution của local build**, còn **published POM/Gradle Module Metadata** mô tả những dependency/constraints mà consumers sẽ nhận. Nếu một library dùng version động và muốn publish resolved versions, cần cấu hình **publishing resolved versions** và kiểm tra metadata.

Không được giả định “lockfile được commit” đồng nghĩa consumers bên ngoài tự nhận khóa đó. Consumers không lấy file gradle.lockfile từ repo của library làm lock state của họ theo mặc định.

### 8.3. Multi-project build

Dùng convention plugin để áp cùng chính sách ở các projects mong muốn. Với projects :core và :app:

~~~text
root/
├── core/gradle.lockfile
└── app/gradle.lockfile
~~~

Tạo/update state bằng các task scoped:

~~~bash
./gradlew :core:dependencies :app:dependencies --write-locks
~~~

Đảm bảo code/convention plugin đã **bật locking trong từng project**. Chạy task root dependencies không tự khóa các subprojects nếu chúng chưa được resolve.

**Tình huống:** :core compile đã khóa một version của module X, nhưng :app runtime resolve graph bắc cầu khác. App vẫn có **lock state riêng** và có thể chọn version X khác nếu declarations/constraints của app khác. Cần kiểm tra **cả hai graphs** nếu đây là library shared API/ABI.

### 8.4. Test-only dependencies

Một framework JUnit hay mocking library chỉ thuộc testImplementation/testRuntimeOnly. Nếu chỉ khóa main compileClasspath/runtimeClasspath, dependencies của tests **có thể tiếp tục thay đổi**.

Muốn bảo đảm test CI ổn định, khóa **testCompileClasspath/testRuntimeClasspath**, cập nhật states sau khi add/upgrade test libraries. Test fixtures tạo thêm configs riêng; cần xem đúng plugin documentation.

### 8.5. Annotation processor và code generator

Annotation processors ảnh hưởng **generated source code**. Không khóa annotationProcessor trong khi khóa compileClasspath có thể để phiên bản processor thay đổi và tạo output khác mặc dù library source không đổi.

Với dự án dùng Lombok, MapStruct, Dagger hoặc processor/custom generators, xác định **resolvable processor/tool classpath** và khóa nếu cần. Không suy rằng các libs ở annotationProcessor tự được bảo vệ vì implementation đã khóa.

### 8.6. Buildscript classpath

Locking với:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

**không tự khóa buildscript classpath**.

Với legacy buildscript dependencies:

~~~groovy
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}
~~~

Khi state được ghi, buildscript lockfile mặc định là **buildscript-gradle.lockfile**. Đây là ví dụ độc lập; nếu buildscript có repositories/dependencies thật thì cần các cấu hình tương ứng.

**Cẩn thận:** Modern plugins DSL, pluginManagement, Gradle Wrapper distribution, buildSrc và included builds có các vòng đời/cơ chế riêng. Đừng khẳng định chỉ một root gradle.lockfile sẽ khóa toàn bộ plugin code và toolchain; kiểm tra từng build/plugin classpath có thể resolve và cơ chế locking tương ứng.

### 8.7. Source dependencies, changing modules và file dependencies

- **Source dependencies:** Tài liệu Gradle nêu dependency locking hiện không áp dụng cho source dependencies.
- **Changing modules** (ví dụ -SNAPSHOT được publish lại dưới cùng tọa độ): locking **khóa version**, không khóa nội dung JAR; Gradle còn cảnh báo khi ghi lock state có changing dependency. Với reproducibility, tránh changing modules trong pipeline release hoặc bổ sung chính sách phù hợp.
- **File dependencies:** Một JAR qua files('libs/vendor.jar') không có group:name:version để lock như external module. Muốn tái lập binary đó, kiểm tra/chốt checksum, đảm bảo file đúng nguồn và có trong môi trường CI.
- **Project dependencies:** Khóa dependency graph của consumer có thể ghi external modules transitively đến từ project dependency, nhưng **project(':lib')** tự thân không phải external versioned module để ghi tương tự.

## 9. Locking, force, constraints và verification: không trộn vai trò

| Cơ chế | Mục tiêu chính | Không tự làm được |
|---|---|---|
| **Dependency locking** | Chốt resolved module versions và kiểm tra graph theo configurations | Không xác thực bytes/artifact; không tự khóa mọi config |
| **Version catalog** | Tập trung requested module versions và aliases | Không mặc nhiên ép selected graph cuối |
| **Dependency constraint/strictly** | Biểu đạt version requirement trong dependency graph | Không ghi lại trọn graph đã resolve nếu chưa lock |
| **ResolutionStrategy.force** | Ép một module version trong graph của configuration | Không tạo dependency, không công bố lock cho consumers |
| **Dependency verification** | Xác minh checksum/signature metadata/artifacts | Không chọn/khóa dependency versions |
| **Build cache** | Tái sử dụng output task | Không quyết định module versions |
| **Gradle Wrapper** | Chọn Gradle distribution/version chạy build | Không khóa versions của Java dependencies |
| **Java toolchain** | Chọn JDK cho compile/test/tool tasks phù hợp | Không khóa dependency graph |

### 9.1. Tại sao khóa version chưa đủ để an toàn?

Có hai artifact khác nhau cùng tọa độ version được publish lại (changing module) hoặc một nguồn repository bị xâm nhập. Lockfile vẫn ghi cùng group:name:version, nhưng **nội dung có thể khác**.

Dependency verification dùng metadata/checksum/signature để kiểm tra artifact. Reproducible build còn cần kiểm soát JDK/Gradle versions, inputs, environment, plugins và cách packaging.

### 9.2. Lock state được áp thế nào trong resolution?

Gradle hiện đại áp locked versions như **strictly constraints** khi một configuration có state được khóa. Nó không chỉ "đọc version text và tải đúng JAR" bỏ qua các yêu cầu khác.

- Với **transitive dependencies**, locked strictly constraints thường giữ phiên bản đã khóa trước các yêu cầu phiên bản khác trong giới hạn resolution rules.
- Với **direct dependencies**, dependency declaration thường tạo yêu cầu version (require) cần tương thích với locked strictly constraint.
- Nếu direct request được đổi lên bản mới **cao hơn** locked version mà hai yêu cầu không thể thỏa đồng thời, Gradle **fail** để bạn cập nhật lock state có chủ đích.
- Custom resolutionStrategy.force hoặc rules có thể override strictly và khiến graph/lock validation có kết quả khác theo interaction rules; vì vậy tránh trộn force/lock bừa bãi.

Đừng diễn giải “có lockfile thì mọi phiên bản khác đều bị âm thầm downgrade”. Locking cũng là cơ chế phát hiện **yêu cầu version đã đổi**.

## 10. Cách xử lý lỗi khi dùng dependency locking

### Lỗi 1: Có lockAllConfigurations nhưng không thấy gradle.lockfile

**Khả năng:** Chưa chạy --write-locks; project hiện tại không resolve configuration đã bật; build thất bại trước khi ghi; hoặc đang tìm file ở root trong khi state được tạo ở subproject.

**Cách xử lý:** Chạy đúng project và resolvable configuration với --write-locks, kiểm tra task thành công; tìm file tại **thư mục project tương ứng**, không tự kiểm tra một tên khác mà chưa biết build configuration.

### Lỗi 2: Thêm dependency nhưng build báo lock mismatch

**Nguyên nhân:** Graph resolved chứa module mới không khớp state đã commit; DEFAULT/STRICT kiểm tra state hiện có.

**Cách xử lý:** Review dependency mới và các transitives, chạy --write-locks hoặc --update-locks khi phù hợp, kiểm tra diff và commit state mới. Không xóa lockfile để “cho build chạy tiếp” khi chính sách yêu cầu khóa.

### Lỗi 3: Bật STRICT rồi build báo thiếu state

**Nguyên nhân:** Một locked configuration chưa có entry trong lock state, có thể vì bạn chưa từng resolve nó lúc ghi locks.

**Cách xử lý:** Dùng dependencies --write-locks trên đúng project/configuration; nếu có configs không resolve được trong môi trường hiện tại, thiết kế bootstrap workflow tương ứng hoặc deactive locking cho config không cần khóa theo policy.

### Lỗi 4: Đã khóa main nhưng tests vẫn tải version khác

**Nguyên nhân:** testCompileClasspath/testRuntimeClasspath là những configurations riêng, chưa bật locking hoặc chưa sinh state.

**Cách xử lý:** Khóa/resovle configs của tests, sinh lock states, kiểm tra graph của chúng. Nếu test plugin có source sets đặc biệt thì tra đúng classpath nó dùng.

### Lỗi 5: CI có lockfile nhưng không có dependency trong cache

**Nguyên nhân:** Lock state chốt version, không bảo đảm artifact đã có trong Gradle User Home. Khi --offline và cache thiếu, Gradle vẫn fail.

**Cách xử lý:** Cấp repository/network/caches đúng; không bỏ lock chỉ vì một máy mới chưa tải artifact.

### Lỗi 6: --update-locks không nâng version

**Nguyên nhân:** Dependencies/constraints vẫn yêu cầu phiên bản cũ, selector không cho phép version mới, hoặc rule/lock khác vẫn hạn chế selection.

**Cách xử lý:** Sửa declarations/version catalogs/constraints hợp lý rồi chạy --update-locks group:name; xem dependencyInsight và lockfile diff.

### Lỗi 7: --update-locks thay nhiều module ngoài ý muốn

**Nguyên nhân:** Graph cần nâng transitives để nhất quán với module mục tiêu; selective update không cam kết diff chỉ một module.

**Cách xử lý:** Review toàn bộ diff, kiểm tra dependencyInsight và compatibility tests. Nếu thay đổi quá lớn, chia upgrade thành bước nhỏ.

### Lỗi 8: Một Gradle root lockfile không bảo vệ subproject

**Nguyên nhân:** Mỗi project có configurations và lock state riêng. Chỉ root được bật locking hoặc chỉ root:dependencies được resolve.

**Cách xử lý:** Áp convention plugin hoặc cấu hình trong từng subproject cần khóa, chạy :subproject:dependencies --write-locks cho từng project.

### Lỗi 9: Lockfile vẫn nguyên nhưng -SNAPSHOT artifact đổi nội dung

**Nguyên nhân:** Locking phiên bản không khóa bytes của changing module; cùng version có thể có nội dung khác.

**Cách xử lý:** Tránh changing versions khi cần reproducibility, dùng dependency verification khi thích hợp và quản trị release artifact bất biến.

### Lỗi 10: Published library consumer không nhận lockfile

**Nguyên nhân:** Lockfile của producer là build-state local, không tự được publish như một dependency graph lock cho consumer.

**Cách xử lý:** Kiểm tra publication metadata và cơ chế publish resolved versions khi cần; consumer tự quản lý lockfile riêng.

### Lỗi 11: Lockfile bị chỉnh bằng tay gây lỗi

**Nguyên nhân:** Module versions/config names/empty entries không còn phản ánh graph do Gradle giải quyết.

**Cách xử lý:** Khôi phục từ Git hoặc chạy quy trình ghi locks có kiểm soát; review diff, tránh chỉnh bằng tay để bypass incompatibility.

### Lỗi 12: Khóa tất cả làm một custom configuration không thể resolve

**Nguyên nhân:** Configuration có thể phụ thuộc platform/toolchain/credentials hoặc plugin chỉ resolve trong môi trường nhất định.

**Cách xử lý:** Phân nhóm configurations theo môi trường, khóa có chọn lọc hoặc dùng task resolve có filter phù hợp. Không tuyên bố coverage rộng khi không có lock state được sinh ra.

### Lỗi 13: Nhầm lock với --refresh-dependencies

**Nguyên nhân:** --refresh-dependencies kiểm tra trạng thái dependency metadata/artifacts, không phải lệnh tạo lock state hoặc mở khóa graph.

**Cách xử lý:** Dùng --write-locks/--update-locks khi chủ động cập nhật lock; dùng refresh chỉ khi nghi cache metadata có vấn đề.

### Lỗi 14: Muốn quản lý plugin version bằng app runtime lock

**Nguyên nhân:** Plugin resolution classpath không phải Java runtimeClasspath của app.

**Cách xử lý:** Quản trị plugin versions trong pluginManagement/version catalogs có phần plugins, lock buildscript classpath khi phù hợp và kiểm tra riêng Gradle Wrapper.

### Lỗi 15: Một file dependencies report chạy OK nhưng task khác fail STRICT

**Nguyên nhân:** Report chưa resolve một configuration khác đã bật locking; task mới resolve config thiếu state.

**Cách xử lý:** Xác định configuration trong lỗi, tạo state đúng project/config, hoặc xem vì sao nó chưa được bao phủ trong bootstrap. Đừng cho rằng một lần dependencies report tại root là bằng chứng khóa toàn build.

## 11. Quy trình CI và cộng tác nhóm được khuyến nghị

### 11.1. Trong pull request nâng dependency

1. Developer sửa dependency declaration/constraint/version catalog.
2. Chạy **--update-locks** cho modules có chủ đích hoặc **--write-locks** theo policy.
3. Kiểm tra lockfile được cập nhật **ở đúng project và configurations**.
4. Chạy Gradle dependencies/dependencyInsight để hiểu graph thực tế.
5. Chạy unit/integration tests với JDK/Gradle version phù hợp.
6. Review các thay đổi transitive không mong muốn trong diff.
7. Commit source và **gradle.lockfile** cùng PR.
8. CI checkout trên môi trường sạch và **build thường, không có --write-locks**.
9. CI fail nếu lock state không khớp hoặc một configuration bị thiếu state dưới STRICT.
10. Với security-critical artifacts, bổ sung **dependency verification**.

### 11.2. Chọn DEFAULT hay STRICT?

- **DEFAULT** phù hợp khi bạn đang triển khai locking từng phần: kiểm tra những states đã tạo, chưa yêu cầu mọi configuration đã bật đều phải có state.
- **STRICT** phù hợp sau khi coverage/baseline đã rõ: phát hiện project/config bị bật khóa nhưng thiếu lock state.
- **LENIENT** dùng với mục tiêu khám phá/cập nhật có chủ đích; không đánh đồng nó với CI enforcement ở mức đầy đủ.

Không cần mọi repository áp dụng một mode giống nhau ngay. Sự lựa chọn nên xuất phát từ **độ phủ configurations, chính sách CI và khả năng duy trì lock states**.

## 12. Checklist tự kiểm tra trước khi kết luận “đã khóa dependency”

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Project nào đã bật locking? | build.gradle hoặc convention plugin áp đúng project |
| Configuration nào thật sự khóa? | activateDependencyLocking hoặc lockAllConfigurations đúng nơi |
| Configuration có resolvable không? | Kiểm tra role của configuration và task resolve |
| Lock state đã được tạo chưa? | gradle.lockfile tại đúng project |
| Lockfile chứa đúng configurations nào? | Nhìn tên sau dấu = và dòng empty= |
| Có kiểm tra compile và runtime riêng không? | dependencies/dependencyInsight cho từng classpath |
| Test/annotationProcessor đã khóa chưa? | State cho test/processor configs khi cần |
| Multi-project có đủ lockfiles chưa? | Kiểm tra từng project có graph riêng |
| CI có tránh tự ghi lock không? | Build thường không kèm --write-locks |
| Lock state có được commit không? | Git diff/review và version control |
| Module versions có thay đổi chỉ khi review không? | PR cập nhật locks có mục đích rõ |
| Artifact bytes có được xác minh không? | Dependency verification/cơ chế checksum |
| -SNAPSHOT/changing artifacts có tồn tại không? | Kiểm tra changing dependencies và policy |
| Java/Gradle/plugin versions có được quản trị riêng không? | Wrapper, toolchains và plugin versions |
| Library publish có thông tin consumer cần không? | Kiểm tra published Gradle Module Metadata/POM |

## 13. Bài tập tự đánh giá

**Bài 1.** Project có implementation 'org.apache.commons:commons-lang3:3.+' và chỉ khóa runtimeClasspath. compileJava có chắc dùng đúng version trong runtime lock không?

**Bài 2.** Vì sao bật activateDependencyLocking() trên implementation (declarable) không tương đương khóa compileClasspath/runtimeClasspath?

**Bài 3.** Khi muốn khóa cả main compile và run nhưng không khóa tests, nên dùng những block nào?

**Bài 4.** Chạy ./gradlew dependencies --write-locks từ root của multi-project build có chắc tạo core/gradle.lockfile và app/gradle.lockfile không? Vì sao?

**Bài 5.** Lock state có Commons Lang 3.14.0, code trực tiếp nâng yêu cầu thành 3.17.0 nhưng không cập nhật lock. DEFAULT có thể làm gì?

**Bài 6.** STRICT khác DEFAULT quan trọng nhất ở điều kiện nào?

**Bài 7.** LENIENT có nghĩa mọi thay đổi dependency graph bị chặn nghiêm ngặt như STRICT không?

**Bài 8.** Muốn cập nhật đúng module org.apache.commons:commons-lang3 trong lockfile, CLI flag có dạng gì? Có cần --write-locks kèm theo không?

**Bài 9.** --update-locks group:name mà dependency declarations vẫn yêu cầu bản cũ có chắc nâng bản không?

**Bài 10.** Vì sao selective update đôi khi làm những transitive modules khác cũng thay version?

**Bài 11.** Một module :app khóa runtimeClasspath có transitive library từ :core. Điều này có tự khóa :core:compileClasspath không?

**Bài 12.** Một file libs/vendor.jar được đưa bằng files(...). Lockfile có tự mã hóa và khóa bytes của JAR không?

**Bài 13.** Muốn ổn định test runtime với JUnit và mocking libraries, cần xem configuration nào?

**Bài 14.** Vì sao --offline có thể thất bại ngay cả khi gradle.lockfile tồn tại và hợp lệ?

**Bài 15.** Một buildscript plugin dependency cần khóa riêng, file mặc định có tên gì?

**Bài 16.** Vì sao một thư viện được publish không tự chuyển lockfile của producer thành lockfile cho consumer?

**Bài 17.** Khi dùng -SNAPSHOT/changing version, có thể nói dependency locking bảo đảm artifact bytes không thay đổi không?

**Bài 18.** Bạn muốn build CI không cho phép một locked configuration mới thiếu state. Chọn mode nào sau bootstrap?

### Gợi ý đáp án

1. **Không**. compileClasspath là graph riêng; phải khóa/kiểm tra nó nếu cần reproducibility khi compile.
2. implementation là bucket khai báo; lock state chỉ gắn hữu ích với resolvable configurations.
3. Bật activateDependencyLocking() trên **compileClasspath và runtimeClasspath**.
4. **Không**. Root dependencies task không tự resolve mọi subproject; cần chạy tasks scoped và bật locking ở từng project.
5. Graph có thể **fail** vì direct request mới không tương thích locked strictly version cũ.
6. **STRICT fail khi locked configuration thiếu lock state**, ngoài những kiểm tra đã có trong DEFAULT.
7. **Không**. LENIENT có thể cho phép thêm/bớt modules và thay đổi versions trong các trường hợp mà DEFAULT/STRICT chặn.
8. **--update-locks org.apache.commons:commons-lang3**; flag này bao hàm --write-locks.
9. **Không**. Resolution phải có yêu cầu/constraint/version selector cho phép version mới.
10. Bởi graph resolution cần một tập dependencies tương thích, cập nhật một module có thể kéo theo modules khác.
11. **Không**. Mỗi project/configuration có scope và lock state riêng.
12. **Không**. File dependency không có external module version để lock; cần cơ chế bảo đảm binary/file riêng.
13. **testRuntimeClasspath** (và testCompileClasspath nếu muốn ổn định compile tests).
14. Lockfile chốt version nhưng cache chưa chắc chứa artifact; offline không thể tải file còn thiếu.
15. **buildscript-gradle.lockfile**.
16. Lock state là project build-state; consumer giải quyết dependency theo metadata/publication của library và policy riêng.
17. **Không**. Locking version không đủ để khóa bytes của changing artifact.
18. **LockMode.STRICT** sau khi đã sinh và review baseline.

## Tài liệu chính thức

- [Gradle User Manual — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html): scope per configuration, lockAllConfigurations, --write-locks, --update-locks, lock modes, lockfile format, limitations.
- [Gradle JavaDoc — LockMode](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/dsl/LockMode.html): DEFAULT, STRICT, LENIENT.
- [Gradle DSL — DependencyLockingHandler](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.dsl.DependencyLockingHandler.html): lockAllConfigurations, lockFile, lockMode và ignoredDependencies.
- [Gradle User Manual — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): declarable, resolvable và consumable.
- [Gradle User Manual — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies và dependencyInsight.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): --write-locks, --update-locks, --offline, --refresh-dependencies.
- [Gradle User Manual — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): xác minh artifact/metadata và phân biệt locking với verification.
- [Gradle User Manual — Declaring Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): rich versions và constraints khi resolution.
- [Gradle User Manual — Publishing Resolved Versions](https://docs.gradle.org/current/userguide/publishing_maven.html): metadata/publication của library và trách nhiệm của consumer.

**Ghi nhớ:** Dependency locking **ghi lại và kiểm tra versions đã resolve** cho **những configurations được bật locking trong từng project**. Bật đúng phạm vi, tạo lock states bằng **--write-locks**, cập nhật có mục đích bằng **--update-locks**, commit lockfiles và dùng **DEFAULT/STRICT** theo chính sách CI. Không coi lockfile là bản sao của dependency cache, bằng chứng artifact bytes an toàn hoặc lời hứa toàn bộ subprojects/plugins/test configurations đã tự động được khóa.