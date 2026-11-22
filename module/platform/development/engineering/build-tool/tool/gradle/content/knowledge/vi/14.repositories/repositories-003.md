# Tập trung repository bằng dependencyResolutionManagement trong Gradle

## 1. Mục tiêu và vấn đề cần giải quyết

Một dự án Java nhiều module thường cần lấy thư viện từ Maven Central, kho Maven nội bộ hoặc một mirror do doanh nghiệp quản lý. Nếu mỗi file **build.gradle** tự khai báo **repositories { ... }**, danh sách kho dễ lệch nhau: module A tải từ Maven Central, module B dùng mirror, module C vô tình truy cập kho không được phê duyệt. Một plugin cũng có thể thêm repository vào project mà người viết module không nhận ra. Kết quả là build khó tái lập, chậm, khó chẩn đoán lỗi và tiềm ẩn rủi ro supply chain.

**dependencyResolutionManagement** trong **settings.gradle** hoặc **settings.gradle.kts** cho phép khai báo **repository dùng để phân giải dependency của các project trong build tại một chỗ**, kết hợp **repositoriesMode** để quyết định repository đặt trong từng project được ưu tiên, bỏ qua hay gây lỗi.

Sau bài học, bạn có thể:

- Giải thích tại sao nên tập trung dependency repositories ở settings của multi-project build.
- Viết cấu hình **dependencyResolutionManagement { repositories { ... } }** bằng Groovy DSL hoặc Kotlin DSL.
- Phân biệt ba chế độ **PREFER_PROJECT**, **PREFER_SETTINGS**, **FAIL_ON_PROJECT_REPOS** và chọn cách áp dụng hợp lý.
- Biết repository dành cho **plugin**, **project dependencies**, **buildscript** và **publishing** là những phạm vi khác nhau.
- Thiết kế kho Maven nội bộ/mirror có **credentials**, **content filtering** và **exclusiveContent** mà không rò rỉ tên thư viện nội bộ.
- Di chuyển cấu hình cũ **allprojects { repositories { ... } }** sang settings và xử lý plugin tự thêm kho.
- Chạy ví dụ Gradle đa module có Java 17 và JUnit; xác minh dependency được tải, kiểm thử và chạy ứng dụng.
- Phân tích lỗi **Could not resolve**, **401/403/407**, **repository was added by...** cùng tác động của offline/cache.

## 2. Repository tham gia vào quá trình build như thế nào?

### 2.1. Dependency, repository và tọa độ module

Gradle phân giải một external dependency như:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

Thành các thành phần:

~~~text
group       : org.junit.jupiter
module/name : junit-jupiter
version     : 5.11.4
~~~

Đây là **tọa độ thư viện**. Gradle cần biết các kho nào được phép tìm metadata và artifact tương ứng (POM, Gradle Module Metadata, JAR...). Repository quyết định **nguồn tìm/tải**, còn **dependencies** quyết định **thư viện cần dùng**.

Sơ đồ khái quát:

~~~text
settings.gradle
    |
    +-- dependencyResolutionManagement
    |      |
    |      +-- repositoriesMode
    |      +-- Maven Central / kho nội bộ / mirror
    |      +-- content filters
    |
    v
Project :app (build.gradle)
    |
    +-- plugins: application
    +-- dependencies: JUnit 5.11.4
    |
    v
Gradle giải quyết configuration testRuntimeClasspath
    |
    +-- Xác định kho được phép truy vấn
    +-- Tải metadata và artifact khi cần
    +-- Sử dụng cache phù hợp
    |
    v
Chạy task :app:test
~~~

**Tập trung repository không có nghĩa tất cả dependencies được tải ngay khi Gradle đọc settings.** Gradle thường phân giải từng configuration khi cần. Chẳng hạn chạy **help** không nhất thiết tải JUnit; chạy **:app:test** hoặc task/report cần test classpath mới kích hoạt việc phân giải tương ứng.

### 2.2. Vì sao nhân bản repositories là vấn đề?

Giả sử root có ba module:

~~~text
backend/
├── settings.gradle
├── build.gradle
├── api/build.gradle
├── service/build.gradle
└── cli/build.gradle
~~~

Các script cũ có thể viết khác nhau:

~~~groovy
// api/build.gradle
repositories {
    mavenCentral()
}
~~~

~~~groovy
// service/build.gradle
repositories {
    mavenLocal()
    mavenCentral()
}
~~~

~~~groovy
// cli/build.gradle
repositories {
    maven {
        url = uri('https://repo.example.invalid/maven')
    }
}
~~~

Đây là **ba đoạn minh họa vấn đề**, không phải một ví dụ chạy được với URL giả. Module có thể tải thư viện từ nguồn khác nhau, đặc biệt nếu cùng tọa độ xuất hiện ở nhiều kho. **mavenLocal()** cũng có thể chọn artifact còn trong máy developer mà CI không có. Nếu một plugin lặng lẽ thêm repository, danh sách thực tế có thể khác với những dòng bạn nhìn thấy trong script.

Di chuyển danh sách kho vào settings giúp dễ review nguồn tin cậy và thực thi chính sách chung cho mọi subproject.

## 3. Khai báo tập trung trong settings.gradle

### 3.1. Cấu hình tối thiểu — Groovy DSL

**settings.gradle**:

~~~groovy
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'my-build'
include ':api', ':service'
~~~

Không cần lặp **repositories { mavenCentral() }** trong các file **api/build.gradle**, **service/build.gradle**. Gradle áp dụng danh sách repository do settings cung cấp cho project dependency resolution theo chế độ phù hợp.

**Lưu ý:** Nếu không chỉ rõ **repositoriesMode**, chế độ mặc định là **PREFER_PROJECT**. Một project hoặc plugin tự thêm repository thì repository cấp project có thể được ưu tiên thay kho trong settings. Nếu mục tiêu thực sự là kiểm soát nguồn tập trung, chỉ đặt **mavenCentral()** trong settings **chưa đủ để cưỡng chế**.

### 3.2. Cấu hình khuyến nghị khi cần chính sách chặt

**settings.gradle**:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'my-build'
include ':api', ':service'
~~~

Ý nghĩa:

1. **dependencyResolutionManagement** là block cấu hình của **Settings**, được thực thi trong giai đoạn initialization.
2. **repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS** không cho phép một Project hoặc plugin thêm repository vào danh sách giải quyết project dependencies.
3. **repositories { mavenCentral() }** là nguồn tìm dependency được cho phép trong build.
4. **include** quyết định những subproject thuộc build, độc lập với việc repository được cấu hình tập trung.

Nếu vẫn còn block **repositories** trong một subproject, build có thể **thất bại ngay trong configuration**. Đó là cơ chế kiểm soát chủ đích, không phải lỗi Gradle ngẫu nhiên.

### 3.3. Cấu hình tương đương — Kotlin DSL

Nếu repo dùng **settings.gradle.kts**:

~~~kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
    }
}

rootProject.name = "my-build"
include(":api", ":service")
~~~

Khác biệt quan trọng: Kotlin DSL thường dùng **repositoriesMode.set(...)** còn Groovy DSL hỗ trợ **repositoriesMode = ...**. Hãy dùng DSL nhất quán với file thực tế; không trộn **include ':api'** của Groovy vào settings Kotlin.

### 3.4. Cấu trúc hoàn chỉnh có plugin repositories

Một settings thực tế có thể cần cả hai loại kho:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'my-build'
include ':api', ':service'
~~~

**pluginManagement.repositories** phục vụ phân giải plugin được khai báo qua **plugins { ... }**; **dependencyResolutionManagement.repositories** phục vụ external library dependencies như JUnit, Jackson hoặc Apache Commons. Chúng không phải một danh sách kho dùng chung.

Với Kotlin DSL cũng có thể viết:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "my-build"
include(":api", ":service")
~~~

Nếu plugin chỉ có ở repository nội bộ, hãy khai báo repository đó trong **pluginManagement.repositories** riêng. Chỉ thêm internal Maven vào **dependencyResolutionManagement** không khiến plugin marker tự tìm được ở đó.

## 4. Ba chế độ repositoriesMode

Enum **RepositoriesMode** có ba giá trị:

| Mode | Repository trong build.gradle của project | Repository trong settings | Cách dùng |
| --- | --- | --- | --- |
| **PREFER_PROJECT** | Được ưu tiên nếu project khai báo | Áp dụng nếu project không khai báo kho ghi đè | Mặc định, tương thích với cấu hình per-project |
| **PREFER_SETTINGS** | Bị bỏ qua, Gradle có thể ghi cảnh báo | Được ưu tiên | Di chuyển dần về settings nhưng chưa chặn build |
| **FAIL_ON_PROJECT_REPOS** | Gây lỗi build nếu project hoặc plugin thêm kho | Là nguồn được chấp nhận | Cưỡng chế chính sách repository tập trung |

### 4.1. PREFER_PROJECT: mặc định không phải cưỡng chế

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.PREFER_PROJECT
    repositories {
        mavenCentral()
    }
}
~~~

Nếu **:service** có:

~~~groovy
repositories {
    mavenLocal()
}
~~~

thì repository cấp project được ưu tiên và có thể **thay thế tác dụng của danh sách ở settings đối với project đó**. Đừng hiểu “tập trung tại settings” là hai danh sách luôn tự động gộp theo thứ tự.

**PREFER_PROJECT** có thể hữu ích khi một số module thực sự cần nguồn riêng, nhưng khó đảm bảo chỉ dùng kho được phê duyệt trên toàn bộ repo.

### 4.2. PREFER_SETTINGS: cảnh báo, không chặn

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.PREFER_SETTINGS
    repositories {
        mavenCentral()
    }
}
~~~

Nếu một project hay plugin thêm repository, Gradle **bỏ qua repository đó** và có thể in cảnh báo cho biết repository được thêm ở đâu. Đây là lựa chọn trong giai đoạn chuyển đổi cấu hình khi muốn build vẫn chạy được nhưng cần rà soát các khai báo cũ.

Một phụ thuộc từng chỉ có trên kho cũ sẽ không tự tìm thấy nữa. Vì vậy **PREFER_SETTINGS** không bảo đảm chuyển đổi vô rủi ro: phải đưa kho phù hợp lên settings hoặc sửa repository routing.

### 4.3. FAIL_ON_PROJECT_REPOS: biến sai chính sách thành lỗi

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}
~~~

Khi một module còn đoạn:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Gradle có thể báo thông điệp dạng:

~~~text
Build was configured to prefer settings repositories over project repositories
but repository 'MavenRepo' was added by build file ...
~~~

Thông điệp thực có thể khác theo phiên bản Gradle, plugin và vị trí repository. Ngay cả khi subproject thêm **chính Maven Central** trùng settings, chế độ này vẫn có thể coi **hành vi khai báo project-level** là vi phạm. Đây là lựa chọn tốt để phát hiện plugin hoặc script tự ý thay nguồn dependency.

**Cách sửa:** xóa/chuyển repository cấp project sang **dependencyResolutionManagement.repositories**, hoặc thay cấu hình plugin để nó không tự thêm kho. Không nên đổi ngay sang **PREFER_PROJECT** chỉ để làm lỗi biến mất mà chưa xem lại chính sách.

### 4.4. Chọn mode theo từng giai đoạn

Khi migrate một repo lớn, có thể làm có kiểm soát:

1. Ghi nhận các kho cần thiết từ cấu hình hiện tại và chính sách mirror.
2. Đưa kho phù hợp vào settings.
3. Dùng **PREFER_SETTINGS** để phát hiện khai báo trùng/thừa và kiểm tra dependency còn resolve đúng.
4. Sửa plugin/module thêm kho trái ý muốn.
5. Chuyển sang **FAIL_ON_PROJECT_REPOS** để CI chặn tái phát.

Nếu tổ chức cần enforcement từ đầu, có thể dùng **FAIL_ON_PROJECT_REPOS** ngay sau khi đã rà soát. Lộ trình là khuyến nghị vận hành, không phải chuỗi mode bắt buộc của Gradle.

## 5. Các loại repository có phạm vi khác nhau

| Vị trí cấu hình | Phục vụ | Có được điều khiển bởi dependencyResolutionManagement không? |
| --- | --- | --- |
| **settings.gradle: dependencyResolutionManagement.repositories** | External dependencies của các project trong build | Đây là nơi điều khiển chính |
| **settings.gradle: pluginManagement.repositories** | Plugin marker/artifact khi dùng **plugins { ... }** | **Không**, đây là cơ chế riêng |
| **build.gradle: buildscript.repositories** | Dependency trên classpath của build script kiểu cũ | Không coi là một bản sao tự động của kho project |
| **build.gradle: publishing.repositories** | Điểm đích **upload/publish** artifact | **Không**; chiều công việc ngược với tải dependency |
| **settings của included build** | Dependencies của build độc lập trong composite | Cần cấu hình cho build đó riêng |
| **buildSrc** | Dependencies phục vụ build logic | **buildSrc** có build riêng, có thể cần repository trong settings của chính nó |
| **Gradle Wrapper distributionUrl** | Tải Gradle runtime ZIP | Hoàn toàn khác Maven/plugin repositories |

### 5.1. Plugin resolution là một câu chuyện riêng

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Đoạn này cho phép tìm plugin ở các nguồn được chỉ định; thứ tự và khả năng có plugin marker ảnh hưởng kết quả. Nó **không** tự biến Maven Central thành repository cho **implementation 'group:artifact:version'** của project.

Nếu một plugin được dùng qua cơ chế legacy **buildscript { dependencies { classpath ... } }**, phải kiểm tra cách giải quyết classpath của buildscript; không tự giả định settings dependencyResolutionManagement bao phủ nó.

### 5.2. Publishing không chịu tác động

Ví dụ nơi xuất bản:

~~~groovy
plugins {
    id 'maven-publish'
}

publishing {
    repositories {
        maven {
            name = 'releases'
            url = uri('https://publish.example.invalid/releases')
        }
    }
}
~~~

Đây là **ví dụ minh họa chưa thể chạy thành công** vì URL giả và chưa có cấu hình credentials/publication. Nhưng nó cho thấy **publishing.repositories** là **đích xuất bản**, không phải nguồn tải thư viện. Chế độ **FAIL_ON_PROJECT_REPOS** dành cho project dependency repositories không có nghĩa xóa hoặc tự thay thế cấu hình publishing.

### 5.3. Composite build, buildSrc và convention plugin

Với:

~~~groovy
includeBuild 'build-logic'
~~~

**build-logic** là một build độc lập có settings/dependency-resolution scope riêng. Không suy ra rằng danh sách repository trong main build tự động áp dụng trọn vẹn vào included build. Tương tự, **buildSrc** là build logic đặc biệt và có thể có settings riêng; nếu buildSrc không resolve được plugin/dependency, cần xem phạm vi của chính buildSrc.

Trong monorepo lớn, muốn chính sách thống nhất xuyên nhiều build thường cần convention cho settings/init logic hoặc công cụ quản trị thích hợp, không chỉ sao chép một block vào main settings rồi giả định mọi build khác tự kế thừa.

## 6. Ví dụ thực hành hoàn chỉnh: Java 17, hai module và JUnit từ Maven Central

Bài thực hành tạo multi-project build có thư viện **:api** và ứng dụng **:app**. **Tất cả repository cho project dependencies chỉ khai báo trong settings**. Module **:app** dùng **JUnit Jupiter 5.11.4** và **JUnit Platform Launcher 1.11.4** làm dependency kiểm thử, được lấy từ Maven Central; còn source ứng dụng chỉ dùng Java standard library để bạn kiểm tra cả bằng **javac**.

### 6.1. Cấu trúc thư mục

~~~text
central-repositories-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── api/
│   ├── build.gradle
│   └── src/main/java/demo/api/Greeting.java
└── app/
    ├── build.gradle
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/GreetingTest.java
~~~

Các file Wrapper được sinh bằng **gradle wrapper** nếu máy đã có Gradle CLI tương thích, sau đó nên commit và dùng Wrapper cho các lần chạy. Cần JDK đáp ứng Gradle version đã chọn và Java 17 toolchain đã có hoặc được cấu hình để provision.

### 6.2. settings.gradle

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'central-repositories-lab'
include ':api', ':app'
~~~

**Đây là nơi duy nhất trong demo khai báo kho dùng cho external dependencies của project.** Core plugins **java-library** và **application** không yêu cầu một external plugin repository; block pluginManagement được giữ để giải thích ranh giới rõ ràng.

### 6.3. build.gradle của root

~~~groovy
plugins {
    id 'base'
}
~~~

Root không phải module Java và không thêm **repositories { ... }**.

### 6.4. api/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**api/src/main/java/demo/api/Greeting.java**

~~~java
package demo.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Không cần external dependency cho module api; nó chỉ cung cấp một API nội bộ để app tham chiếu qua project dependency.

### 6.5. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':api')

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.app.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Không có **repositories** block trong app. **implementation project(':api')** là project dependency trong cùng build, còn **testImplementation** và **testRuntimeOnly** yêu cầu external modules từ repository được khai báo ở settings.

**testImplementation** cung cấp JUnit API cho biên dịch test; **testRuntimeOnly** cung cấp launcher tại runtime kiểm thử. Phần test tạo nhu cầu tải artifact thực sự, nên bài thực hành không thêm một dependency không dùng chỉ để “có tên trong report”.

### 6.6. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.api.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("Gradle"));
    }
}
~~~

### 6.7. app/src/test/java/demo/app/GreetingTest.java

~~~java
package demo.app;

import demo.api.Greeting;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void rendersGreeting() {
        assertEquals("Xin chào, Gradle!", Greeting.message("Gradle"));
    }
}
~~~

Test dùng external JUnit từ Maven Central, qua **testRuntimeClasspath** của app. Khi chạy test, Gradle cần resolve các module này. Nếu môi trường chặn mạng, hãy sửa kết nối/mirror chính thức thay vì thêm repository tùy ý vào app.

### 6.8. Chạy bằng Gradle Wrapper

**Linux/macOS:**

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:test
./gradlew :app:run
./gradlew :app:build
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :app:dependencies --configuration testRuntimeClasspath
.\gradlew.bat :app:test
.\gradlew.bat :app:run
.\gradlew.bat :app:build
~~~

Kỳ vọng:

- **projects** liệt kê root **:**, subproject **:api** và **:app**.
- **:app:dependencies --configuration testRuntimeClasspath** hiển thị cây dependency có JUnit Jupiter và các thành phần liên quan. Cây chính xác có thể khác do metadata và giải quyết phiên bản; không giả định indent/nhánh bất biến.
- **:app:test** kết thúc thành công khi test assertion đúng; task có thể in log khác nhau tùy cache và phiên bản Gradle.
- **:app:run** chạy Java application và dòng stdout của chương trình **chính xác** là:

~~~text
Xin chào, Gradle!
~~~

Gradle có thể in thêm log task hoặc thông báo **BUILD SUCCESSFUL**. Dòng trên là stdout từ Java source, không phải toàn bộ log Gradle.

### 6.9. Chạy Java 17 trực tiếp để đối chứng

Vì mã production trong demo không dùng JUnit, có thể biên dịch riêng hai class bằng JDK:

**Linux/macOS:**

~~~bash
mkdir -p out
javac --release 17 -d out api/src/main/java/demo/api/Greeting.java app/src/main/java/demo/app/Main.java
java -cp out demo.app.Main
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out api\src\main\java\demo\api\Greeting.java app\src\main\java\demo\app\Main.java
java -cp out demo.app.Main
~~~

Stdout:

~~~text
Xin chào, Gradle!
~~~

**javac/java không kiểm thử cấu hình dependencyResolutionManagement.** Chỉ các task Gradle cần resolve JUnit (ví dụ **:app:test**, **dependencies**) mới xác minh repository đã được thiết lập đúng. Nếu **javac** chạy tốt nhưng **:app:test** lỗi truy cập Maven Central, nguyên nhân nằm ở Gradle dependency resolution hoặc môi trường mạng, không phải logic Java.

## 7. Thử nghiệm kiểm soát mode trên project thật

Thực hiện từng thử nghiệm riêng, rồi hoàn tác trước khi chuyển trường hợp khác.

### Thử A — project khai báo repository trái chính sách

Giữ mode:

~~~groovy
repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
~~~

Trong **app/build.gradle**, cố ý thêm:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Chạy **./gradlew help**. Build phải báo lỗi liên quan repository cấp project. Thông báo có thể nhắc **repository 'MavenRepo' was added** hoặc địa điểm plugin/script thêm kho. Xóa lại block này để khôi phục build chạy được.

**Điểm quan trọng:** ở chế độ FAIL, Gradle không chấp nhận lời khai báo trùng lặp dù URL trong app cùng Maven Central.

### Thử B — PREFER_SETTINGS

Đổi mode thành:

~~~groovy
repositoriesMode = RepositoriesMode.PREFER_SETTINGS
~~~

Giữ thêm repository trong app và chạy lại. Gradle có thể cảnh báo rằng repository cấp project bị bỏ qua nhưng vẫn dùng kho settings. Đây có thể là bước migrate tạm thời. Sau đó bỏ block thừa khỏi app.

### Thử C — PREFER_PROJECT

Đổi mode thành:

~~~groovy
repositoriesMode = RepositoriesMode.PREFER_PROJECT
~~~

Khi app khai báo repository cấp project, chính sách per-project có thể chiếm ưu tiên. Nếu đó là repo thiếu JUnit hoặc không được truy cập, **:app:test** có thể thất bại, ngay cả khi settings có Maven Central. Đây là lý do không nên chọn mode mặc định khi mong muốn enforcement chặt.

Sau thử nghiệm, đưa về **FAIL_ON_PROJECT_REPOS**.

### Thử D — không có Maven Central

Bỏ **mavenCentral()** khỏi repositories của settings rồi chạy:

~~~bash
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Trên môi trường sạch, Gradle không có nguồn phù hợp để resolve JUnit. Nếu vẫn thấy một phần dữ liệu từ cache, đừng coi kết quả đó là bằng chứng mọi máy đều build được; kiểm tra môi trường cache và chạy trên CI/runnable environment phù hợp. Khôi phục **mavenCentral()** trước khi tiếp tục.

### Thử E — settings không quyết định nguồn plugin

Nếu một plugin bên ngoài không được tìm thấy khi dùng **plugins { ... }**, chỉ thêm Maven Central vào **dependencyResolutionManagement** có thể không giải quyết. Kiểm tra **pluginManagement.repositories**, plugin marker, version và repository plugin thực tế.

## 8. Kho Maven nội bộ và credential an toàn

### 8.1. Khai báo một repository có tên rõ ràng

Khi tổ chức có Maven repository nội bộ, có thể cấu hình:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.invalid/maven')
            credentials(PasswordCredentials)
        }

        mavenCentral()
    }
}
~~~

**Đây là đoạn minh họa, không phải cấu hình chạy thật:** **repo.example.invalid** là địa chỉ cố tình không tồn tại. Hãy thay bằng HTTPS URL do tổ chức cung cấp. Với repository tên **internal**, Gradle hỗ trợ lấy credential từ Gradle properties tương ứng **internalUsername** và **internalPassword** khi sử dụng **PasswordCredentials**.

Không đặt username/password vào settings đã commit:

~~~groovy
// KHÔNG dùng trong source được commit
credentials {
    username = 'my-user'
    password = 'hard-coded-secret'
}
~~~

Trong môi trường của developer/CI, có thể cấp credential qua **~/.gradle/gradle.properties**, biến môi trường được Gradle mapping hỗ trợ, hoặc secret manager trong pipeline. Ví dụ chỉ minh họa **tên khóa**, không phải dữ liệu thật:

~~~properties
internalUsername=USERNAME_FROM_APPROVED_SECRET_SOURCE
internalPassword=PASSWORD_FROM_APPROVED_SECRET_SOURCE
~~~

Các giá trị viết hoa ở đây **chỉ là ký hiệu minh họa**, không phải credential hợp lệ. Không commit file chứa secret. Trên CI, cấu hình secret bằng công cụ quản lý credentials của nền tảng. Chỉ cấp quyền đọc cần thiết và đảm bảo proxy/TLS truststore được cấu hình đúng.

**401 Unauthorized** thường liên quan xác thực đến Maven server; **403 Forbidden** liên quan quyền truy cập; **407 Proxy Authentication Required** liên quan proxy. Chúng khác **Could not find module** do artifact/version không tồn tại ở repository được phép.

### 8.2. Thứ tự repository và nguồn tin cậy

Gradle tìm artifact theo các repository được cấu hình và metadata có thể ảnh hưởng việc lựa chọn nguồn. Khi cùng một tọa độ tồn tại ở nhiều kho, thứ tự hoặc chính sách định tuyến có thể quyết định source. Không nên trông đợi “Gradle lúc nào cũng tự ưu tiên bản nội bộ” nếu vừa có internal Maven vừa có Maven Central nhưng không có content filter.

Đối với artifact nội bộ, cần ngăn leak tên dependency riêng và nguy cơ **dependency confusion**. Không khai báo cả hai repository rồi cho mọi group tự do tìm ở cả hai.

## 9. Content filtering và exclusiveContent

### 9.1. Content filter ở từng repository

Ví dụ tổ chức sở hữu group **com.example.internal** và các subgroup:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral {
            content {
                excludeGroupAndSubgroups('com.example.internal')
            }
        }

        maven {
            name = 'internal'
            url = uri('https://repo.example.invalid/maven')
            credentials(PasswordCredentials)
            content {
                includeGroupAndSubgroups('com.example.internal')
            }
        }
    }
}
~~~

**Chỉ là cấu hình tham khảo**; URL và credential chưa có thật. Quy tắc:

- Không hỏi Maven Central về **com.example.internal** hoặc các subgroup.
- Kho nội bộ chỉ được hỏi về các tọa độ group tương ứng.
- Dependency khác được tìm ở Maven Central theo quy tắc filter.

**includeGroup('com.example.internal')** chỉ khớp chính xác group đó; **includeGroupAndSubgroups(...)** bao phủ thêm các group con như **com.example.internal.web**, hữu ích nếu tổ chức sử dụng namespace nhiều cấp.

Đối với repository không có artifact Maven mà dùng kiểu Ivy hoặc nội dung dạng file đơn, phải cấu hình repository tương ứng; không giả định mọi kho đều là Maven.

### 9.2. exclusiveContent để khóa một namespace vào đúng một kho

Khi toàn bộ group nội bộ chỉ được phép tới một repo:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'internal'
                    url = uri('https://repo.example.invalid/maven')
                    credentials(PasswordCredentials)
                }
            }

            filter {
                includeGroupAndSubgroups('com.example.internal')
            }
        }

        mavenCentral()
    }
}
~~~

**exclusiveContent** tạo cơ chế chỉ cho các artifact khớp filter đến từ repository được chỉ định; những repository còn lại không được hỏi về tọa độ đó. Đây là mức bảo đảm mạnh hơn việc chỉ đặt include filter trên internal repository nhưng quên exclude ở các kho còn lại.

Các dependency transitive từ thư viện nội bộ mà thuộc group công cộng vẫn cần nơi phân giải, chẳng hạn Maven Central. Đừng cấu hình exclusiveContent quá rộng khiến transitive dependency hợp lệ không còn nơi tìm.

Trong **pluginManagement**, dùng exclusive content filter còn có những ràng buộc riêng khi plugin/buildscript cố thêm repository; hãy đọc tài liệu chính thức trước khi áp dụng chung quy tắc này cho plugin resolution.

### 9.3. Maven releases và snapshots

Với repository tổ chức tách releases/snapshots, có thể cấu hình filter theo loại version:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/releases')
        mavenContent {
            releasesOnly()
        }
    }

    maven {
        url = uri('https://repo.example.invalid/snapshots')
        mavenContent {
            snapshotsOnly()
        }
    }
}
~~~

Đây là **đoạn minh họa chỉ có ý nghĩa trong repositories block của settings**, URL chưa thực. Trong build có policy **FAIL_ON_PROJECT_REPOS**, đoạn này phải được đưa vào **dependencyResolutionManagement.repositories**, không phải vào module build.gradle.

Mục đích là chỉ hỏi repository thích hợp, giảm các request không cần và tránh lấy snapshot từ nguồn release nhầm. Không cố truy cập kho không có quyền; dùng credential và HTTPS phù hợp.

## 10. Chuyển đổi một repository từ mô hình allprojects cũ

Một build legacy có thể dùng:

~~~groovy
// root build.gradle: cấu hình cũ
allprojects {
    repositories {
        mavenCentral()
    }
}
~~~

Cách này vẫn là cấu hình **project repositories**. Nó nhân logic vào các project và có thể đụng **FAIL_ON_PROJECT_REPOS**. Chuyển theo quy trình:

1. **Kiểm kê bằng mã đã biết:** xác định tất cả khối **repositories**, kể cả từ subprojects, buildSrc/convention plugin và plugin tự thêm kho.
2. **Xác định mục đích:** kho này dùng external dependencies, plugin resolution, buildscript classpath hay publishing? Không chuyển nhầm loại.
3. **Tập trung project dependency repositories:** đặt Maven Central/internal Maven/mirror và content filter trong **settings.gradle: dependencyResolutionManagement.repositories**.
4. **Chọn mode tạm thời:** **PREFER_SETTINGS** có thể hỗ trợ phát hiện các khai báo còn sót mà không chặn toàn bộ; kiểm tra warning.
5. **Xóa cấu hình project-level không còn cần:** bỏ **repositories** khỏi module và **allprojects**; cập nhật plugin nào thêm repository trái chính sách nếu có.
6. **Bật FAIL_ON_PROJECT_REPOS:** biến việc bổ sung kho tùy tiện trong tương lai thành lỗi có thể thấy ở CI.
7. **Chạy test/build trên môi trường sạch hoặc CI:** kiểm tra artifact runtime, tests, plugin resolution, source nội bộ và credentials.
8. **Tài liệu hóa ngoại lệ:** nếu một project thực sự phải dùng kho ngoài, mở rộng policy tại settings hoặc đưa ra một build độc lập hợp lý, thay vì lén đặt lại mode.

Không thay đổi hàng loạt repository cùng plugin, Gradle version và dependency version trong một commit nếu không cần; tách thay đổi giúp dễ truy nguyên lỗi.

### 10.1. Trường hợp plugin thêm repository

Một plugin có thể thực thi code tương đương:

~~~groovy
project.repositories.maven {
    url = uri('https://repo.example.invalid/extra')
}
~~~

Đây là đoạn minh họa hành vi plugin, **không phải lệnh cần đặt vào project thực tế**. Với FAIL_ON_PROJECT_REPOS, Gradle có thể báo lỗi ngay cả khi build.gradle của bạn không chứa block repositories nào.

Khi gặp trường hợp này:

- Đọc thông báo lỗi xem repository được thêm bởi script/plugin nào.
- Tra tài liệu plugin xem có tùy chọn **không tự thêm repository** hay không.
- Đặt repository phù hợp vào settings theo policy và content filter.
- Nếu plugin không hỗ trợ chế độ tập trung, cân nhắc nâng plugin, thay plugin hoặc đưa phần việc vào build khác theo quyết định kiến trúc.
- Không dùng **PREFER_PROJECT** vô điều kiện để che hành vi không mong muốn.

## 11. Version catalogs không phải repository

Trong cùng **dependencyResolutionManagement**, Gradle còn hỗ trợ **version catalogs**; ví dụ một repo có thể có file **gradle/libs.versions.toml**. Catalog giúp quản lý **tọa độ và phiên bản** dependency, nhưng **không chỉ nguồn tải artifact**.

| Công cụ | Quản lý |
| --- | --- |
| **dependencies { implementation(...) }** | Module project nào cần thư viện nào |
| **Version catalogs** | Alias, group, module, version chung |
| **dependencyResolutionManagement.repositories** | Kho được phép cung cấp artifact |
| **repositoriesMode** | Chính sách đối với repository cấp project |
| **Dependency constraints/platforms** | Quy tắc lựa chọn và ràng buộc version |
| **Dependency verification** | Kiểm tra tính toàn vẹn artifact, chữ ký/checksum theo cấu hình |
| **Dependency locking** | Khóa kết quả resolution để giúp tái lập |

Một build có thể dùng cả version catalog và centralized repositories; không nên coi việc đưa JUnit vào **libs.versions.toml** là đã khóa nguồn tải JUnit vào Maven Central. Đối với an toàn chuỗi cung ứng, kết hợp **repository policy + content filter + dependency verification/locking** theo nhu cầu.

## 12. Chẩn đoán lỗi khi dependencyResolutionManagement được bật

| Lỗi/hiện tượng | Nguyên nhân có thể | Kiểm tra và cách xử lý |
| --- | --- | --- |
| **repository ... was added by ...** trong FAIL mode | Project hoặc plugin thêm repository | Chuyển kho hợp lệ lên settings, xóa khai báo project hoặc sửa plugin |
| Warning tương tự ở PREFER_SETTINGS | Project repo bị bỏ qua | Rà soát plugin/script; đảm bảo settings có nguồn thay thế |
| **Could not find group:module:version** | Artifact không có trong các kho được phép; sai version/group; content filter loại nó | Kiểm tra tọa độ, kho, filter, metadata và thứ tự |
| **Could not resolve all files for configuration ...** | Lỗi resolution chung, cần xem nguyên nhân sâu hơn | Chạy task với **--info/--stacktrace**, xem URL và mã HTTP |
| **401 Unauthorized** | Credentials sai/thiếu với Maven server | Kiểm tra name repository, Gradle properties và secret injection |
| **403 Forbidden** | Tài khoản không có quyền artifact hoặc repo | Kiểm tra ACL và phạm vi token với quản trị repo |
| **407 Proxy Authentication Required** | Xác thực proxy thiếu/sai | Cấu hình JVM HTTP/HTTPS proxy, không nhầm với Maven credentials |
| **PKIX path building failed** | JVM không tin CA của proxy/server | Kiểm tra JDK truststore/certificate chain, không tắt TLS |
| **UnknownHostException / Connect timed out** | DNS/firewall/proxy/mirror offline | Kiểm tra đúng host, cổng, mạng và policy |
| Maven dependency chạy nhưng plugin không tải | Plugin repo khác project dependency repo | Kiểm tra **pluginManagement.repositories** |
| Publish thất bại dù compile chạy | publishing.repositories/credentials khác | Kiểm tra destination publish, không sửa dependencyResolutionManagement sai chỗ |
| Máy developer build được nhưng CI thiếu dependency | mavenLocal, cached artifact hoặc credentials môi trường | Test trên runner sạch, chuẩn hóa source và secret |
| buildSrc hoặc build-logic thiếu dependency | Nó có build scope riêng | Kiểm tra settings của build logic thay vì chỉ main settings |
| **--offline** lỗi | Artifact không có trong cache | Cho phép fetch khi online hoặc dùng mirror, offline không tự tạo artifact |
| Repo nội bộ bị dò bởi Maven Central | Thiếu content filter hoặc exclusive routing | Áp dụng exclude/includeGroupAndSubgroups hay exclusiveContent |

### 12.1. Quy trình điều tra có hệ thống

~~~text
Không resolve được dependency?
             |
             v
1. Nó là plugin, external library, buildscript hay publishing?
             |
             v
2. Xác định đúng build/settings scope (main, buildSrc, included build)
             |
             v
3. Đọc dependencyResolutionManagement và repositoriesMode
             |
             v
4. Xác định repo thực được phép và content/exclusive filters
             |
             v
5. Kiểm tra tọa độ, version, transitive dependencies, metadata
             |
             v
6. Kiểm tra DNS, proxy, TLS, 401/403/407 và credentials
             |
             v
7. Test resolution bằng task report/CI sạch, không tùy tiện sửa policy
~~~

Một số lệnh hữu ích:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
./gradlew :app:test --info
./gradlew :app:test --stacktrace
~~~

**:app** chỉ là tên module của ví dụ; thay bằng project path và configuration đúng trong repo thật. **dependencyInsight** giúp xác định dependency được chọn do yêu cầu/version nào, trong khi log **--info** có thể giúp điều tra repository và cache. Không chia sẻ log có credentials/token ra nơi công khai.

### 12.2. Không đánh đồng cache với repository policy

Nếu Maven Central tạm thời không truy cập được, một máy có cache đủ artifact vẫn có thể build thành công. Điều đó **không chứng minh kho đã được cấu hình đúng**. Ngược lại, **--refresh-dependencies** yêu cầu kiểm tra lại metadata/artifact theo quy tắc Gradle nhưng không xóa sạch mọi cache hay sửa URL/credentials. **--offline** chỉ dùng dữ liệu đã có trong cache, có thể thất bại nếu thiếu artifact.

Trong CI, nên chạy kiểm tra trên môi trường sạch hoặc có cache được quản lý, ghi rõ nguồn artifact; không xóa **~/.gradle** bừa bãi khi chẩn đoán vì có thể mất cache cần thiết và che lấp nguyên nhân ban đầu.

## 13. Checklist review cho team và CI

- [ ] **dependencyResolutionManagement** nằm trong đúng **settings.gradle(.kts)** của build.
- [ ] **repositoriesMode** được chọn có chủ đích; với enforcement chặt, dùng **FAIL_ON_PROJECT_REPOS**.
- [ ] Module build scripts không tự khai báo repository khi chính sách cấm.
- [ ] Các plugin tự thêm repository đã được rà soát; không bỏ qua warning/error.
- [ ] **pluginManagement.repositories** được cấu hình riêng khi cần plugin bên ngoài.
- [ ] Maven nội bộ/mirror dùng HTTPS, có content filter rõ và credentials không commit.
- [ ] Tọa độ nội bộ không bị gửi đến kho công cộng; cân nhắc **exclusiveContent**.
- [ ] buildSrc và included builds được xử lý đúng phạm vi, không giả định kế thừa settings.
- [ ] Publishing destinations được giữ riêng, không trộn với dependency download.
- [ ] Dependencies cần thiết resolve thành công trên CI; test/build vẫn chạy sau migrate.
- [ ] Chất lượng source và reproducibility được bảo vệ thêm bằng verification/locking khi cần.

## 14. Câu hỏi và bài tập củng cố

**Câu 1.** Nếu khai báo Maven Central trong settings mà không đặt repositoriesMode, một project có thể dùng repository riêng thay nó không?

**Câu 2.** Sự khác nhau giữa **PREFER_SETTINGS** và **FAIL_ON_PROJECT_REPOS** khi một plugin thêm Maven repository?

**Câu 3.** Vì sao đã khai báo Maven Central trong **dependencyResolutionManagement** mà một external plugin vẫn có thể không tải được?

**Câu 4.** Trong ví dụ ở mục 6, JUnit được resolve từ đâu và task nào thực sự cần JUnit?

**Câu 5.** Vì sao không nên chỉ dùng **mavenLocal()** trên máy developer làm nguồn tham chiếu trong CI?

**Câu 6.** Phân biệt **content { includeGroup(...) }** và **exclusiveContent**. Vì sao một kho công cộng cần biết càng ít tên thư viện nội bộ càng tốt?

**Câu 7.** Nếu một included build cần dependency riêng, danh sách repositories trong main settings có tự áp dụng cho nó không?

**Câu 8.** Nếu build tải external dependencies thành công nhưng upload artifact thất bại, phải kiểm tra block nào trước?

**Câu 9.** Khi gặp HTTP 407 thay vì HTTP 401, vì sao không nên chỉ thay internal Maven username/password?

**Câu 10.** Version catalog giúp quản lý thư viện nhưng có bảo đảm chúng chỉ tải từ mirror được phê duyệt không?

**Đáp án gợi ý:** (1) Có, mặc định PREFER_PROJECT; (2) PREFER_SETTINGS bỏ qua và cảnh báo, FAIL gây lỗi; (3) plugin dùng pluginManagement.repositories; (4) từ Maven Central của settings, task test/testRuntimeClasspath; (5) cache local có artifact khác CI; (6) filter hạn chế từng kho, exclusive buộc namespace chỉ tới một kho; (7) không, build scope riêng; (8) publishing.repositories; (9) 407 liên quan proxy, 401 thường là server; (10) không, catalog quản lý tọa độ/version, repository policy quyết định nguồn.

### Bài tập thực hành

1. Tạo multi-project **central-repositories-lab** như mục 6; chạy **:app:test**, **:app:run** và **:app:dependencies**.
2. Thêm **repositories { mavenCentral() }** vào **app/build.gradle** khi mode FAIL, xem lỗi; hoàn tác.
3. Đổi sang PREFER_SETTINGS, quan sát warning; so sánh rồi đưa về FAIL.
4. Xây một tình huống kho nội bộ giả định dùng group **com.example.internal**; viết **content filters** để Maven Central không nhận yêu cầu về group này.
5. Phân loại các lỗi giả định: JUnit resolution failure, plugin marker not found, publishing HTTP 403, proxy HTTP 407, buildSrc thiếu repository. Với mỗi lỗi, chỉ ra **settings/build script scope** cần kiểm tra trước.

## 15. Tài liệu chính thức

- [Gradle — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html)
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html)
- [Gradle — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html)
- [Gradle — Filtering Repository Content](https://docs.gradle.org/current/userguide/filtering_repository_content.html)
- [Gradle — RepositoriesMode API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/resolve/RepositoriesMode.html)
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html)
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)

**Ghi nhớ:** **dependencyResolutionManagement.repositories** tập trung **nguồn tải external dependencies của các project trong một build**, còn **repositoriesMode** quyết định mức độ bắt buộc tuân thủ. Chính sách tốt kết hợp mode chặt, Maven mirror đáng tin, content filtering, credential an toàn và kiểm thử CI. Luôn phân biệt nó với kho plugin, buildscript và publishing; khi đó bạn sẽ sửa đúng nguồn khi Gradle không tìm được dependency và giữ build đa module nhất quán.
