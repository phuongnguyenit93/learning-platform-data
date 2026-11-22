# Lộ trình học Gradle: từ một dự án Java đến build nhiều dự án

**Mục tiêu:** Đi từ một ứng dụng Java có thể chạy bằng Gradle tới một hệ thống gồm nhiều dự án con có ranh giới rõ, dependency đúng và quy trình build có thể kiểm chứng. Ví dụ dùng **Java 17+**, **Gradle Groovy DSL** (các tệp `settings.gradle` và `build.gradle`). Các lệnh minh họa dùng Gradle Wrapper; trên Windows PowerShell thay `./gradlew` bằng `.\gradlew.bat`.

## 1. Bản đồ học tập và tiêu chí hoàn thành

| Chặng | Học điều gì? | Kết quả phải tự làm được |
| --- | --- | --- |
| 1. Nền tảng | Build, project, plugin, task, lifecycle, Wrapper | Giải thích Gradle chạy một lệnh như thế nào; liệt kê task của dự án |
| 2. Dự án đơn | Cấu trúc thư mục Java, `application`, toolchain | Chạy, kiểm thử và đóng gói ứng dụng Java đơn |
| 3. Quản lý phụ thuộc | `repositories`, `dependencies`, `implementation`, `testImplementation` | Thêm thư viện kiểm thử và phân biệt classpath |
| 4. Tách dự án | `settings.gradle`, `include`, `java-library`, `project(':core')` | Chuyển mã dùng chung sang `:core`, ứng dụng ở `:app` |
| 5. Chuẩn hóa | Module boundaries, version catalog, convention plugin | Duy trì nhiều dự án con mà không nhân bản cấu hình |
| 6. Vận hành | Task path, dependency graph, cache, CI, lỗi phổ biến | Build/test từng phần hoặc toàn bộ và chẩn đoán sự cố |

Học theo thứ tự, nhưng **chỉ chuyển chặng khi kết quả chặng trước chạy được**. Không cần bắt đầu bằng nhiều dự án nếu chưa nắm được vòng đời của một dự án đơn.

## 2. Nắm mô hình Gradle trước khi viết script

Một **build** là tập hợp dự án mà Gradle điều phối. Một **project** có danh tính và các task riêng; ở build nhiều dự án, project gốc (root) chứa các project con (subproject). “Module” là cách gọi kiến trúc phổ biến, nhưng ở đây dùng từ *project* khi nói đến đối tượng Gradle.

- `settings.gradle`: tên root, danh sách dự án con, một số quy tắc giải quyết plugin và dependency. Nó xác định **những project nào tham gia build**.
- `build.gradle`: plugin, dependency và task của **project chứa tệp đó**. Mỗi project con có thể có script riêng.
- `gradlew`, `gradlew.bat` và `gradle/wrapper/`: Gradle Wrapper giữ phiên bản Gradle mà dự án dùng, giúp máy cá nhân và CI chạy cùng bản.
- `src/main/java` và `src/test/java`: source set mặc định khi dùng Java plugin.
- **Task**: đơn vị công việc như `compileJava`, `test`, `jar`, `build`; Gradle sắp xếp chúng theo quan hệ phụ thuộc.

Ba pha cần phân biệt:

1. **Initialization**: đọc settings, xác định các project.
2. **Configuration**: áp dụng plugin và cấu hình các task cần thiết; đây chưa phải lúc mọi task chạy.
3. **Execution**: chạy các task được chọn và những task phụ thuộc của chúng theo đồ thị công việc.

Lệnh `./gradlew :app:run` có thể khiến `:core:compileJava` chạy trước. Đó là vì quan hệ dependency giữa project và task; không cần tự viết lệnh “chạy core trước” trong shell.

## 3. Chặng 1–2: làm chủ một dự án Java chạy được

Tạo một thư mục, ví dụ `hello-gradle`, với cấu trúc:

~~~text
hello-gradle/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/                 # được tạo bởi Gradle Wrapper
└── src/main/java/com/example/
    ├── App.java
    └── Greeting.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'hello-gradle'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.App'
}
~~~

Plugin `application` tích hợp các khả năng của Java plugin và thêm task `run`. Toolchain yêu cầu Java 17 để biên dịch/chạy ứng dụng; máy cần có JDK phù hợp hoặc cơ chế cung cấp toolchain đã được cấu hình.

**`src/main/java/com/example/Greeting.java`:**

~~~java
package com.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

**`src/main/java/com/example/App.java`:**

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("Gradle"));
    }
}
~~~

Nếu chưa có Wrapper, cài Gradle tạm thời rồi chạy `gradle wrapper` **một lần ở thư mục gốc**; commit các tệp Wrapper vào hệ thống quản lý mã nguồn. Sau đó dùng Wrapper cho những lần chạy tiếp theo:

~~~bash
./gradlew --version
./gradlew tasks
./gradlew run
./gradlew clean build
~~~

**Dòng do chương trình in ra khi chạy `run` (stdout của ứng dụng):**

~~~text
Xin chào, Gradle!
~~~

Gradle sẽ còn in log các task; dòng trên chỉ là stdout của `App.main`. Khi chạy `clean build`, hãy quan sát Gradle biên dịch nguồn, tạo JAR và chạy task kiểm thử nếu có. Thử chạy `build` lần hai mà không thay đổi mã để nhận biết những task có thể `UP-TO-DATE`.

**Tự kiểm tra:** Bạn giải thích được tại sao `run` tồn tại nhờ plugin `application`, tên class trong `mainClass` phải đúng package và vì sao nên dùng `./gradlew` thay vì phụ thuộc vào lệnh `gradle` toàn máy.

## 4. Chặng 3: thêm kiểm thử và hiểu dependency

Sau khi chương trình đơn chạy đúng, thêm vào **cuối `build.gradle`**:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các phiên bản JUnit trên chỉ là một cặp phiên bản tương thích để làm bài thực hành; không hàm ý đây là bản mới nhất. Lần đầu chạy cần truy cập kho Maven Central nếu dependency chưa được cache.

**`src/test/java/com/example/GreetingTest.java`:**

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void createsGreeting() {
        assertEquals("Xin chào, Gradle!", Greeting.message("Gradle"));
    }
}
~~~

Chạy `./gradlew test` rồi `./gradlew build`. Test chứng minh hành vi của `Greeting` trước khi tách dự án. Phân biệt:

- `implementation`: thư viện mà mã ứng dụng cần khi biên dịch/sử dụng.
- `testImplementation`: thư viện chỉ phục vụ biên dịch và chạy test; không tự động thành dependency của mã chính.
- `testRuntimeOnly`: dependency cần lúc **chạy** test, nhưng không cần đưa lên compile classpath của test.
- `repositories`: nơi Gradle tìm thư viện ngoài; nó **không** tự khai báo thư viện nào được dùng.

**Mốc kiểm chứng trước khi tách:** `run` in đúng dòng, `test` thành công và `build` thành công. Nếu chưa đạt, sửa lỗi ở dự án đơn trước.

## 5. Chặng 4: tách ứng dụng thành build nhiều dự án

Giả sử `Greeting` là logic dùng chung và `App` chỉ là điểm vào của ứng dụng. Chia thành đồ thị phụ thuộc một chiều:

~~~text
:app ──implementation──> :core
~~~

`:app` phụ thuộc `:core`; `:core` **không** phụ thuộc ngược lại. Không tách mỗi class thành một project: nên chọn ranh giới theo trách nhiệm, khả năng dùng chung và độ ổn định của API.

### 5.1. Cấu trúc sau khi di chuyển

~~~text
multi-demo/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
├── app/
│   ├── build.gradle
│   └── src/main/java/com/example/app/App.java
└── core/
    ├── build.gradle
    ├── src/main/java/com/example/core/Greeting.java
    └── src/test/java/com/example/core/GreetingTest.java
~~~

Tệp `build.gradle` ở root là **không bắt buộc** trong ví dụ này. Toàn bộ source Java nằm trong hai project con. Nếu chuyển từ dự án đơn, giữ Wrapper ở root; chuyển file Java/test sang đúng vị trí, thay package/import và bỏ bản cũ ở thư mục `src` root.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'multi-demo'
include 'app', 'core'
~~~

`include` đăng ký hai project. Mỗi đường dẫn Gradle có dấu hai chấm ở đầu: `:app` và `:core`. Với cấu trúc mặc định, `include 'services:api'` tương ứng thư mục `services/api`. Thư mục project được khai báo phải tồn tại.

**`core/build.gradle`:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`java-library` phù hợp với mã thư viện. Nó cho phép phân biệt `api` (dependency cần lộ ra cho mã của project tiêu thụ biên dịch) với `implementation` (dependency triển khai nội bộ). Chỉ dùng `api` khi hợp đồng công khai thực sự yêu cầu; đừng công khai mọi dependency để “cho chắc”.

**`app/build.gradle`:**

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
    implementation project(':core')
}

application {
    mainClass = 'com.example.app.App'
}
~~~

Điểm then chốt là `implementation project(':core')`: đây là **project dependency**, không phải tọa độ thư viện Maven. Gradle tự đưa output cần thiết của `:core` vào classpath và thiết lập task dependency phù hợp.

**`core/src/main/java/com/example/core/Greeting.java`:**

~~~java
package com.example.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

**`core/src/test/java/com/example/core/GreetingTest.java`:**

~~~java
package com.example.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void createsGreeting() {
        assertEquals("Xin chào, Gradle!", Greeting.message("Gradle"));
    }
}
~~~

**`app/src/main/java/com/example/app/App.java`:**

~~~java
package com.example.app;

import com.example.core.Greeting;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message("Gradle đa dự án"));
    }
}
~~~

Tại root, chạy:

~~~bash
./gradlew projects
./gradlew :core:test
./gradlew :app:run
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew clean build
~~~

Kết quả stdout **chỉ từ chương trình Java** khi chạy `:app:run`:

~~~text
Xin chào, Gradle đa dự án!
~~~

`projects` phải liệt kê `:app` và `:core`; `:core:test` chạy test vừa chuyển; `:app:run` phải tự biên dịch `:core` khi cần. `:app:dependencies --configuration runtimeClasspath` cho thấy quan hệ `project :core`. `clean build` tại root chạy những task `build` tương ứng có trong các project con.

Trên Windows PowerShell, chẳng hạn:

~~~powershell
.\gradlew.bat :app:run
.\gradlew.bat clean build
~~~

### 5.2. Cách di chuyển an toàn từ một project sang nhiều project

1. Chụp mốc hiện trạng: mã đang chạy, kết quả test và đầu ra cần giữ.
2. Chọn một ranh giới nhỏ và rõ (ví dụ `Greeting` là logic dùng chung). Vẽ hướng dependency trước.
3. Tạo thư mục `core`, `app` và thêm `include` trong settings.
4. Chuyển mã, test và package về project sở hữu; cập nhật `import` ở nơi sử dụng.
5. Đặt plugin theo vai trò: `java-library` cho thư viện, `application` cho ứng dụng; khai báo `project(':core')` ở `app`.
6. Chạy lại test của thư viện, chạy ứng dụng, kiểm tra runtime classpath và build toàn bộ; so sánh hành vi với mốc ban đầu.
7. Chỉ tiếp tục tách project mới khi quan hệ phụ thuộc đang rõ và những kiểm chứng trên đều qua.

Điều này ngăn được lỗi thường gặp: dời thư mục mã mà quên khai báo dependency, bỏ sót test, hoặc vô tình giữ hai bản của cùng class.

## 6. Chặng 5: mở rộng có kiểm soát

Khi có nhiều project (ví dụ `:app`, `:core`, `:api`, `:infra`), học thêm theo thứ tự:

**A. Thiết kế ranh giới trước.** Project nền tảng không nên phụ thuộc project ứng dụng; tránh vòng `:a -> :b -> :a`. Một project độc lập phải có mục đích rõ, không cần tách chỉ vì mã đã dài. Coi `:app` là composition root nếu nó ghép các thành phần lại.

**B. Tập trung phiên bản thư viện ngoài.** Gradle có *version catalog* mặc định ở `gradle/libs.versions.toml`. Ví dụ sau thay cho hai chuỗi JUnit lặp lại trong các `build.gradle`:

~~~toml
[versions]
junit = "5.11.4"
junitPlatform = "1.11.4"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
junit-launcher = { module = "org.junit.platform:junit-platform-launcher", version.ref = "junitPlatform" }
~~~

Khi đã thêm catalog, phần dependency của project dùng test có thể viết:

~~~groovy
dependencies {
    testImplementation libs.junit.jupiter
    testRuntimeOnly libs.junit.launcher
}
~~~

Đây là **cách thay thế** hai dòng dependency JUnit cũ, không phải thêm vào bên cạnh chúng. Catalog tập trung tên/phiên bản dependency **bên ngoài**; quan hệ giữa các subproject vẫn dùng `project(':core')`.

**C. Thống nhất kho dependency.** Khi cấu hình lớn hơn, có thể đưa repository vào `dependencyResolutionManagement { repositories { mavenCentral() } }` trong `settings.gradle`, rồi chọn chính sách repository phù hợp và loại bỏ khai báo thừa ở các project. Giữ quyền sở hữu cấu hình rõ ràng.

**D. Chia sẻ build logic bằng convention plugin.** Nếu cùng toolchain, cách chạy test hoặc cấu hình chất lượng lặp ở nhiều project, đóng gói thành convention plugin; với build lớn, đặt logic này trong included build như `build-logic`. Làm sau khi đã hiểu cấu hình của từng project. Tránh một khối `subprojects { ... }` quá lớn âm thầm áp chính sách cho mọi project, kể cả project không thuộc loại đó.

**E. Biết điểm khác của composite build.** `include 'core'` đưa `:core` vào **cùng multi-project build**. `includeBuild('../shared-build')` tham chiếu một **build độc lập**; cách này phù hợp khi muốn phối hợp các build có settings/vòng đời riêng. Đừng thay multi-project bằng composite chỉ vì có hai thư mục.

## 7. Chặng 6: vận hành, hiệu năng và CI

Các lệnh nên thành thói quen:

| Lệnh | Dùng để |
| --- | --- |
| `./gradlew projects` | Xem các project Gradle nhận diện |
| `./gradlew :app:tasks` | Xem task của project ứng dụng |
| `./gradlew :core:test` | Kiểm thử một project cụ thể |
| `./gradlew :app:run` | Chạy ứng dụng, tự giải quyết project dependency |
| `./gradlew build` | Chạy các task build khớp trong build nhiều dự án |
| `./gradlew :app:dependencies --configuration runtimeClasspath` | Quan sát cây dependency runtime của ứng dụng |
| `./gradlew :app:dependencyInsight --dependency junit --configuration testRuntimeClasspath` | Truy nguyên cách chọn một dependency liên quan tới JUnit trong project app **nếu app có cấu hình test JUnit** |
| `./gradlew build --dry-run` | Xem task dự kiến mà không thực thi tác vụ |
| `./gradlew build --build-cache` | Thử tận dụng build cache cho các task có hỗ trợ |
| `./gradlew build --configuration-cache` | Thử lưu/tái sử dụng cấu hình khi build logic tương thích |

Với ví dụ ở phần 5, JUnit nằm ở **`:core`**, nên lệnh thực tế để tra JUnit là:

~~~bash
./gradlew :core:dependencyInsight --dependency junit --configuration testRuntimeClasspath
~~~

Cache và chạy song song có thể giúp thời gian build nhưng chỉ nên tối ưu sau khi kết quả đúng và task graph ổn định. Không mặc định mọi task đều được cache hay mọi plugin đều tương thích configuration cache. CI nên dùng **Wrapper ở root**, chạy ít nhất `test`/`build` theo phạm vi phù hợp và dùng JDK đúng toolchain.

## 8. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Khả năng cao | Kiểm tra/cách xử lý |
| --- | --- | --- |
| `Project with path ':core' could not be found` | Quên `include` hoặc sai đường dẫn | Xem `settings.gradle` và `./gradlew projects` |
| Project đã include nhưng Gradle không tìm thấy thư mục | Thư mục không tồn tại hoặc sai mapping | Tạo đúng thư mục `core/`; với nested path, kiểm tra cấu trúc thư mục |
| `:app:compileJava` không tìm thấy `Greeting` | Quên `implementation project(':core')`, sai `package`/`import` | Kiểm tra cả build script lẫn đường dẫn Java sau khi chuyển |
| Không tìm được `mainClass` | Tên package/class không đúng hoặc class thiếu `main` | Đối chiếu `application.mainClass` với mã Java thực |
| Không tìm được Java toolchain 17 | Thiếu JDK phù hợp/cấu hình cung cấp JDK | Kiểm tra JDK đã cài, cấu hình toolchain và phiên bản Gradle |
| Test không chạy theo JUnit Jupiter | Thiếu JUnit runtime hoặc `useJUnitPlatform()` | Kiểm tra `testImplementation`, `testRuntimeOnly` và task `test` |
| Build có vòng phụ thuộc giữa các project | Ranh giới module sai | Vẽ lại đồ thị, chuyển hợp đồng dùng chung về project độc lập |
| API của thư viện dùng một type từ dependency khác nhưng consumer không compile được | Phân biệt `api`/`implementation` chưa đúng | Chỉ đưa dependency cần lộ trong public API sang `api` của `java-library` |
| Các project dùng phiên bản dependency khác nhau | Khai báo rải rác | Gom phiên bản thư viện ngoài vào version catalog |
| Chạy Gradle trên máy khác ra kết quả khác | Dùng Gradle cài toàn máy/JDK không nhất quán | Commit Wrapper, đồng bộ toolchain và cấu hình CI |

Đọc lỗi **đầu tiên có ý nghĩa**, xác định project/task đang lỗi rồi chạy đúng task path để khoanh vùng; không dùng `clean` như cách chữa mọi sự cố. Nếu thêm module mới mà project cũ phụ thuộc ngược vào nó, hãy sửa kiến trúc dependency trước khi tối ưu tốc độ.

## 9. Bài thực hành cuối lộ trình

**Bài 1 — Dự án đơn:** Tạo `hello-gradle`, chạy `run`, thêm JUnit, bảo đảm `test` và `build` qua. Giải thích file nào quyết định main class, JDK và dependency.

**Bài 2 — Chuyển thành multi-project:** Tách `Greeting` sang `:core` và ứng dụng sang `:app` theo cấu trúc phần 5. Không để mã Java ở root. Kiểm tra ba điều: `:core:test` qua, `:app:run` in đúng dòng, `./gradlew projects` hiển thị hai project.

**Bài 3 — Thêm consumer:** Thêm project `:cli` (plugin `application`) sử dụng lại `project(':core')`. Hãy bảo đảm `:core` không cần biết `:app` hay `:cli` là ai. Vẽ đồ thị mới:

~~~text
:app ──> :core <── :cli
~~~

**Bài 4 — Chuẩn hóa:** Đưa JUnit sang version catalog, so sánh các build script trước/sau. Chỉ khi có cấu hình lặp thực sự, thử viết convention plugin để chia sẻ quy ước Java/test.

**Bài 5 — Kiểm chứng vận hành:** Từ một checkout sạch, dùng Wrapper thực thi `projects`, `:core:test`, `:app:run`, `build`. Giải thích vì sao Gradle biết phải biên dịch `:core` trước khi chạy `:app` và nêu một trường hợp nên dùng composite build.

**Đạt mục tiêu** khi bạn tự tạo được build hai hoặc ba project, giải thích được luồng dependency và task, xác minh được kết quả bằng lệnh chạy thật, và không cần sao chép thủ công JAR từ project này sang project khác.

## Tài liệu đối chiếu

- [Gradle: Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle: Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html)
- [Gradle: Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html)
- [Gradle: Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
