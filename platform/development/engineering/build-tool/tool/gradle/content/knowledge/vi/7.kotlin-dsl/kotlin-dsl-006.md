# Cấu hình plugin ngoài và xử lý extension chưa có accessor trong Gradle Kotlin DSL

## 1. Mục tiêu

Trong `build.gradle.kts`, một plugin ngoài (third-party plugin) có thể bổ sung task, dependency configuration và **extension** để người dùng tùy chỉnh công cụ. Gradle Kotlin DSL đôi khi sinh hàm cấu hình tiện lợi như `spotless { ... }`, đôi khi không. Khi compiler báo `Unresolved reference: spotless`, vấn đề có thể là **accessor chưa được sinh**, plugin chưa áp dụng, sai scope, sai tên hoặc class của extension chưa nằm trên classpath.

Sau bài học, bạn có thể:

- Khai báo plugin ngoài bằng `plugins { }`, phân biệt plugin ID, phiên bản, repositories và extension.
- Hiểu **thời điểm Gradle tạo type-safe model accessors**; phân biệt accessor được sinh với chính extension object.
- Dùng `configure<ExtensionType> { }` hoặc `extensions.getByType(...)` khi không có accessor.
- Xử lý plugin áp dụng bằng `apply(plugin = "...")`, `apply false`, plugin áp dụng có điều kiện và script plugin.
- Phân biệt vấn đề extension với task/configuration không có accessor.
- Dùng version catalog, precompiled script plugin và quy trình chẩn đoán có thể kiểm tra bằng Gradle Wrapper.

Ví dụ minh họa plugin bên ngoài **Spotless** với ID `com.diffplug.spotless`, phiên bản cụ thể `8.11.0`. Đây là phiên bản được công bố trên Gradle Plugin Portal; khi áp dụng vào dự án thực tế phải kiểm tra tương thích Gradle/JDK và chính sách nâng cấp. Ví dụ không yêu cầu mọi dự án nâng lên phiên bản này.

## 2. Ba định danh không nên nhầm lẫn

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Plugin ID | `com.diffplug.spotless` | Tên dùng để Gradle tìm và áp dụng plugin qua Plugin DSL. |
| Plugin version | `8.11.0` | Phiên bản artifact plugin được chọn/pin; không phải phiên bản Gradle Wrapper. |
| Extension name | `spotless` | Tên object plugin đăng ký vào `project.extensions`. |
| Extension type | `com.diffplug.gradle.spotless.SpotlessExtension` | Kiểu Java/Kotlin public để gọi API cấu hình. |
| Kotlin DSL accessor | `spotless { ... }` | Hàm được Gradle sinh cho extension khi model có thông tin vào đúng thời điểm. |
| Task do plugin cung cấp | `spotlessCheck`, `spotlessApply` | Hành động thực thi, khác extension dùng để khai báo cấu hình. |

Plugin ID, extension name và extension type **không bắt buộc giống nhau**. Một plugin có thể có nhiều extension hoặc chỉ đăng ký task, không hề có extension tên theo plugin ID. Accessor cũng không phải một class cố định trong thư viện của plugin: Gradle sinh Kotlin accessor phù hợp với **model của script đang biên dịch**.

## 3. Vì sao Kotlin DSL không phải lúc nào cũng có accessor?

Một build script Kotlin DSL cần biết tên và kiểu đối tượng **khi biên dịch**. Với `build.gradle.kts` project thông thường, Gradle thực hiện khối `plugins { ... }` trước, áp dụng plugin tại đó, **sau đó xác định các accessor** từ build model. Phần thân script được biên dịch/đánh giá với các accessor đã xác định.

~~~text
settings.gradle.kts -> plugin repositories/versions
                  |
                  v
        plugins { id(...) }
                  |
                  v
         plugin được áp dụng
                  |
                  v
      Gradle sinh model accessors
                  |
                  v
    thân build.gradle.kts được đánh giá
                  |
                  +-> spotless { ... } nếu đã sinh accessor
                  +-> configure<SpotlessExtension> { ... } dùng API theo type
                  +-> apply(plugin = "...") áp dụng muộn
~~~

Hệ quả quan trọng:

1. `plugins { id("...") version "..." }` thường cho phép accessor đối với extension mà plugin tạo khi apply.
2. `plugins { id("...") version "..." apply false }` chỉ đặt plugin lên classpath: **chưa áp dụng**, nên project hiện tại chưa có extension của plugin.
3. `apply(plugin = "...")` nằm trong **thân build script**. Các extension do nó tạo xuất hiện sau lúc Gradle sinh accessor, nên có thể không gọi được bằng block `spotless { ... }` trong chính script đó.
4. Element tạo trong thân script, ví dụ `configurations.create("custom")`, không được sinh accessor `custom(...)` ngược thời gian.
5. Các script được áp dụng bằng `apply(from = "...gradle.kts")` và init script không nhận model accessor giống project script chính.
6. Trong binary plugin Kotlin/Java, dùng API Gradle rõ ràng; không dựa vào accessor riêng của project sẽ sử dụng plugin.
7. Cross-project configuration và plugin áp dụng gián tiếp có thể khiến thời điểm/phạm vi đăng ký model element khác dự đoán. Nên biết **project nào thực sự nhận plugin**.

**Missing accessor không đồng nghĩa plugin không hoạt động.** Plugin vẫn có thể được áp dụng, extension vẫn tồn tại, task vẫn chạy; chỉ là tên hàm Kotlin tiện lợi không có ở thời điểm biên dịch.

## 4. Cách chuẩn: plugin ngoài trong `plugins { }`

Ví dụ tối thiểu gồm Gradle Wrapper và ba file nội dung:

~~~text
plugin-extension-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── settings.gradle.kts
├── build.gradle.kts
└── README.md
~~~

`settings.gradle.kts`:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "plugin-extension-lab"
~~~

`build.gradle.kts`:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0"
}

spotless {
    format("misc") {
        target("*.md")
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

Ở đây `plugins` giải quyết và **áp dụng** Spotless. Khi plugin đóng góp extension `spotless` trong giai đoạn tạo accessor, Kotlin DSL có thể dùng ngay `spotless { }`. Trong block này, `format("misc")` tạo nhóm định dạng tên `misc`, `target("*.md")` chọn file Markdown ở thư mục gốc, còn hai bước sau xử lý dấu cách cuối dòng và newline cuối file.

Tạo `README.md` với vài dòng văn bản, rồi thử:

~~~bash
./gradlew help
./gradlew tasks --all
./gradlew spotlessCheck
./gradlew spotlessApply
./gradlew spotlessCheck
~~~

- `help`: kiểm tra plugin/script được giải quyết và cấu hình thành công.
- `tasks --all`: xem các task plugin thực tế đăng ký.
- `spotlessCheck`: kiểm tra định dạng; có thể fail nếu file vi phạm rule.
- `spotlessApply`: **chủ động sửa file** để phù hợp cấu hình; nên xem Git diff sau khi chạy.
- Lệnh kiểm tra cuối xác minh trạng thái sau format. Số task và stdout phụ thuộc phiên bản plugin, nội dung file, cache và môi trường; không nên bịa một output cố định.

Nếu plugin tải không được, kiểm tra kết nối mạng, chính sách proxy, `pluginManagement.repositories`, version và tương thích Wrapper trước khi nghi ngờ accessor. Repository cho `plugins` **khác** `repositories { mavenCentral() }` dành cho dependency thư viện thông thường; chỉ thêm `mavenCentral()` trong `build.gradle.kts` không tự giải quyết plugin ID tại Plugin DSL.

## 5. Trường hợp điển hình: `apply false` + `apply(plugin = ...)`

So sánh hai phiên bản **thay thế**, không đặt chung trong một file.

**Cách thường có generated accessor**:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0"
}

spotless {
    format("misc") {
        target("*.md")
        endWithNewline()
    }
}
~~~

**Áp dụng plugin muộn trong thân script**:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0" apply false
}

apply(plugin = "com.diffplug.spotless")

// Nếu tiếp tục gọi spotless { ... } tại đây,
// Kotlin compiler có thể báo:
// Unresolved reference: spotless
~~~

`apply false` đặt artifact plugin lên build-script classpath, nhưng chưa tạo extension. `apply(plugin = "...")` áp dụng plugin ở phần thân, sau điểm Gradle sinh model accessors. Vì thế cách đầu có thể viết `spotless { }`, còn cách sau cần API cấu hình không phụ thuộc generated accessor.

**Cách sửa đúng với public extension type** — một file `build.gradle.kts` độc lập, hoàn chỉnh:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0" apply false
}

apply(plugin = "com.diffplug.spotless")

configure<com.diffplug.gradle.spotless.SpotlessExtension> {
    format("misc") {
        target("*.md")
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

`configure<T>` tìm extension của project theo **type T** và cấu hình nó. Tên hàm `spotless` không còn cần thiết. Điều kiện cần: plugin đã áp dụng vào đúng project; class `SpotlessExtension` có trên compile classpath của script; và API của version plugin đã chọn vẫn cung cấp type/method tương ứng.

Việc class có package `com.diffplug.gradle.spotless` trong khi plugin ID là `com.diffplug.spotless` là bình thường. Không đoán tên class bằng cách viết hoa plugin ID; phải đọc docs/Javadoc của plugin.

## 6. Các API thay thế khi thiếu accessor

### 6.1. Ưu tiên `configure<T>`

Cú pháp:

~~~kotlin
configure<com.diffplug.gradle.spotless.SpotlessExtension> {
    format("misc") {
        target("*.md")
        endWithNewline()
    }
}
~~~

Đoạn này là **mảnh cấu hình**, phải đặt sau khi plugin đã được áp dụng và class đã có trên classpath. Nó dùng typed Gradle API, compiler kiểm tra tên method/kiểu tham số, IDE vẫn hỗ trợ completion theo class.

### 6.2. `extensions.getByType` khi cần giữ object

Một cách tương đương, trong script đã áp dụng Spotless:

~~~kotlin
val spotlessExtension = extensions.getByType(
    com.diffplug.gradle.spotless.SpotlessExtension::class.java
)

spotlessExtension.apply {
    format("misc") {
        target("*.md")
        endWithNewline()
    }
}
~~~

`getByType` yêu cầu có extension tương ứng; nếu không tồn tại, Gradle báo lỗi lúc cấu hình. `findByType` hữu ích khi extension thật sự tùy chọn, nhưng không nên lặng lẽ bỏ qua việc plugin bắt buộc không được áp dụng. Nếu một plugin có nhiều extension cùng type, tham khảo API theo tên và cách plugin đăng ký extension.

### 6.3. `extensions.findByName` chỉ để phát hiện/chẩn đoán

Khi nghi ngờ tên extension, có thể kiểm tra một cách chủ động trong script thử **đã áp dụng plugin**:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0"
}

val value = extensions.findByName("spotless")
check(value != null) {
    "Extension 'spotless' chưa được đăng ký vào project"
}
~~~

`findByName("spotless")` trả instance hoặc null, nhưng kiểu compile-time là kiểu chung. Đây là một **bước chẩn đoán sự tồn tại**, không tự sinh accessor/không bảo đảm tên method trên instance. Đừng dùng reflection, `extra` hoặc ép kiểu mù để thay thế typed API dài hạn.

Nếu phải tra theo tên và vẫn cần gọi API type-safe:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0"
}

val rawExtension = extensions.getByName("spotless")
val spotlessExtension =
    rawExtension as? com.diffplug.gradle.spotless.SpotlessExtension
        ?: error("Extension 'spotless' không có đúng SpotlessExtension")

spotlessExtension.format("misc") {
    target("*.md")
    endWithNewline()
}
~~~

Dùng `as?` có kiểm tra cho thông báo lỗi rõ hơn; vẫn yêu cầu class public trên classpath. Đây là đường dự phòng khi **tên** có ý nghĩa đặc biệt; nếu type duy nhất và ổn định, `configure<SpotlessExtension>` sáng sủa hơn.

### 6.4. Ví dụ Gradle core để hiểu kỹ thuật mà không cần plugin ngoài

`checkstyle` là core plugin có extension class công khai `CheckstyleExtension`. Mẫu `build.gradle.kts` độc lập:

~~~kotlin
import org.gradle.api.plugins.quality.CheckstyleExtension

apply(plugin = "checkstyle")

configure<CheckstyleExtension> {
    toolVersion = "10.12.4"
}
~~~

Chạy:

~~~bash
./gradlew help
./gradlew tasks --all
~~~

Cấu hình này minh họa bản chất: `apply(plugin)` không sinh accessor cho extension mới, nhưng `configure<CheckstyleExtension>` vẫn làm việc vì type là một phần của Gradle API. Phiên bản `10.12.4` là **phiên bản công cụ Checkstyle**, không phải version plugin; chạy kiểm tra Java thật còn cần source/rule/configuration phù hợp. Ví dụ Spotless ở trên mới là trường hợp plugin ngoài.

## 7. Phân biệt lỗi thiếu accessor với lỗi thiếu class

Nếu viết:

~~~text
Unresolved reference: spotless
~~~

thì Kotlin không tìm thấy tên `spotless` trong scope compile hiện tại. Nhưng nếu viết `configure<SpotlessExtension>` và gặp:

~~~text
Unresolved reference: SpotlessExtension
~~~

thì **type extension** chưa có trên compile classpath, import/package sai hoặc plugin version không cung cấp type tương ứng. Đây là hai nguyên nhân khác nhau:

- **Thiếu model accessor**: plugin được apply muộn hoặc model element không nằm trong snapshot sinh accessors. Chuyển sang API typed.
- **Thiếu class**: compiler không biết type; phải thêm artifact/classpath đúng hoặc chọn public type đúng của plugin. Không thể giải quyết chỉ bằng đổi tên extension.
- **Thiếu extension instance**: script biên dịch thành công nhưng `configure<T>`/`getByType` báo không tìm thấy ở runtime; plugin chưa được áp dụng cho project này hoặc extension chưa được tạo khi gọi.
- **Plugin resolution thất bại**: `Plugin ... was not found`; kiểm tra plugin ID, version, repository, mạng/proxy, quyền và Wrapper trước.
- **Sai scope**: extension thuộc `Project` của `:app` nhưng bạn cố tìm trong root project hoặc trong `Settings`.

Tóm lại, giải quyết lần lượt **plugin resolution → plugin application → type classpath → extension instance → generated accessor/API cấu hình**. Nếu thiếu class public, đừng lấy object chung rồi gọi method Groovy bằng tên string: Kotlin compiler không có type để bảo đảm correctness.

## 8. Lấy đúng tên và kiểu extension

Các cách tra an toàn:

1. Đọc tài liệu phiên bản plugin: `plugin ID`, extension name, extension public type, task names và cú pháp Kotlin DSL.
2. Chạy `./gradlew help` và `./gradlew tasks --all` để biết build script có biên dịch và plugin có đăng ký task không. **Task tồn tại không đồng nghĩa extension cùng tên tồn tại**.
3. Chạy `./gradlew kotlinDslAccessorsReport` để xem các generated accessors hiện có trong Gradle model. Tìm tên hàm, kiểu receiver, kiểu model element. Nó không thể “hồi tố” accessor cho model element được tạo sau snapshot.
4. Tìm lời gọi `extensions.create(...)`, `extensions.add(...)` trong source plugin khi tài liệu thiếu, và xác nhận class public. Hạn chế phụ thuộc API `internal` vì plugin nâng version có thể đổi.
5. Với plugin viết cho settings, tra `Settings.extensions`/API settings tương ứng thay vì áp dụng công thức của `Project` một cách máy móc.
6. So sánh terminal với IDE: nếu `./gradlew help` chạy tốt mà editor báo đỏ, refresh/import Gradle model và script dependencies trong IntelliJ IDEA/Android Studio trước khi sửa mã đúng.

Các lệnh hỗ trợ:

~~~bash
./gradlew help
./gradlew tasks --all
./gradlew kotlinDslAccessorsReport
./gradlew help --task spotlessCheck
~~~

`kotlinDslAccessorsReport` là task Gradle dùng để xem code accessor; nội dung output thay đổi theo cấu hình và version. Dùng `help --task` để xem task được plugin cung cấp, không phải để tra tên extension trực tiếp.

## 9. Plugin áp dụng muộn hoặc có điều kiện

Trong build logic dùng chung, plugin có thể chỉ được apply ở một số project. Thay vì dùng `afterEvaluate { ... }` để “chờ”, có thể dùng `pluginManager.withPlugin("id")`, thực hiện cấu hình khi plugin đã được áp dụng.

Ví dụ **mảnh mã dành cho file đã có SpotlessExtension trên classpath**, plugin sẽ được áp dụng ở nơi khác:

~~~kotlin
import com.diffplug.gradle.spotless.SpotlessExtension

pluginManager.withPlugin("com.diffplug.spotless") {
    extensions.configure<SpotlessExtension> {
        format("misc") {
            target("*.md")
            endWithNewline()
        }
    }
}
~~~

`withPlugin` gọi callback khi plugin xuất hiện hoặc ngay nếu đã apply. Nó **không tự áp dụng plugin**. Nếu plugin không bao giờ được áp dụng, callback không chạy. Với binary plugin viết bằng Kotlin, dùng `project.pluginManager.withPlugin(...)` và `project.extensions.configure(...)`, đồng thời khai báo dependency chứa type của plugin ngoài trên classpath build logic.

Không nhầm “chờ plugin được apply” với “chờ một task chạy”: khối `withPlugin` vẫn là **configuration**. Không viết file, gọi deploy hay request mạng trong callback; những công việc này thuộc task actions có input/output rõ ràng.

`afterEvaluate` chỉ trì hoãn cấu hình; nó không sửa nguyên nhân thiếu accessor (thiếu class tại compile-time hoặc plugin apply sai scope), và có thể khiến build khó dự đoán khi mở rộng multi-project.

## 10. Task và dependency configuration thiếu accessor

Không phải mọi thứ do plugin bổ sung đều là extension. Task và dependency configuration cũng có accessor theo một số điều kiện. Khi plugin áp dụng muộn, dùng API theo tên/kiểu.

**Ví dụ task (Gradle core Java plugin):**

~~~kotlin
import org.gradle.api.tasks.testing.Test

apply(plugin = "java")

tasks.named<Test>("test") {
    useJUnitPlatform()
    testLogging.showStandardStreams = true
}
~~~

Đoạn này cấu hình lazy task `test` theo tên và type. `useJUnitPlatform()` yêu cầu có dependency JUnit Platform phù hợp khi chạy test thật; cấu hình task không tự cài thư viện kiểm thử. Nếu task tên `test` không tồn tại tại thời điểm gọi `named`, Gradle báo lỗi.

**Ví dụ dependency configuration theo tên:**

~~~kotlin
apply(plugin = "java-library")

dependencies {
    add("api", "org.apache.commons:commons-lang3:3.14.0")
    add("implementation", "com.google.guava:guava:33.2.1-jre")
}
~~~

Tương đương bằng Kotlin DSL string invocation:

~~~kotlin
apply(plugin = "java-library")

dependencies {
    "api"("org.apache.commons:commons-lang3:3.14.0")
    "implementation"("com.google.guava:guava:33.2.1-jre")
}
~~~

Hai fence trên là **hai cách thay thế**, không đặt cùng nhau vì sẽ khai báo dependency hai lần. Khi thực sự resolve dependency, cần `repositories { mavenCentral() }` hoặc repository khác theo chính sách dự án.

**Ví dụ container extension:**

~~~kotlin
import org.gradle.api.tasks.SourceSetContainer

apply(plugin = "java")

configure<SourceSetContainer> {
    named("main") {
        java.srcDir("src/core/java")
    }
}
~~~

`SourceSetContainer` là extension của Java plugin; `named("main")` chọn source set theo tên, không phụ thuộc accessor `sourceSets.main`. Đừng dùng `tasks.getByName` tùy tiện khi `tasks.named` hoặc `register` giúp giữ lazy configuration.

## 11. Version catalog không giải quyết thay cho extension accessor

Ở `gradle/libs.versions.toml`:

~~~toml
[versions]
spotless = "8.11.0"

[plugins]
spotless = { id = "com.diffplug.spotless", version.ref = "spotless" }
~~~

Ở `build.gradle.kts`:

~~~kotlin
plugins {
    alias(libs.plugins.spotless)
}

spotless {
    format("misc") {
        target("*.md")
        endWithNewline()
    }
}
~~~

`libs.plugins.spotless` là **accessor của version catalog** để lấy plugin ID/version. `spotless { ... }` là **accessor của Gradle model extension**. Hai thứ không tương đương. Version catalog giúp quản lý version tập trung, nhưng nếu dùng `apply false` và sau đó `apply(plugin)` thì accessor extension vẫn có thể thiếu.

Ví dụ multi-project:

~~~kotlin
// root/build.gradle.kts
plugins {
    alias(libs.plugins.spotless) apply false
}
~~~

~~~kotlin
// app/build.gradle.kts
plugins {
    alias(libs.plugins.spotless)
}

spotless {
    format("misc") {
        target("*.md")
        endWithNewline()
    }
}
~~~

Đây là **hai file khác nhau**: root chuẩn bị version/classpath, `:app` thực sự apply plugin. Chỉ cần cấu hình Spotless trong project đã apply plugin. Nếu định nghĩa version trong `pluginManagement.plugins` hoặc một convention plugin, bảo đảm không có nhiều version của cùng plugin chen vào classpath.

## 12. Plugin ngoài trong precompiled script plugin

Khi một nhóm module cần cùng build logic, có thể dùng **precompiled script plugin** trong `buildSrc` hoặc included build `build-logic`. Quy tắc quan trọng: plugin ngoài phải có artifact trên classpath của **build logic project**; trong `plugins { }` của precompiled script plugin không khai báo `version "..."` hoặc `apply false`.

Cấu trúc mẫu:

~~~text
project/
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── formatting-conventions.gradle.kts
├── settings.gradle.kts
├── build.gradle.kts
└── gradlew
~~~

`buildSrc/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}

dependencies {
    implementation("com.diffplug.spotless:com.diffplug.spotless.gradle.plugin:8.11.0")
}
~~~

Dấu `kotlin-dsl` trong đoạn trên là **cú pháp Kotlin backtick** của plugin Gradle; nó không phải string thường.

`buildSrc/src/main/kotlin/formatting-conventions.gradle.kts`:

~~~kotlin
plugins {
    id("com.diffplug.spotless")
}

configure<com.diffplug.gradle.spotless.SpotlessExtension> {
    format("misc") {
        target("*.md")
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

`build.gradle.kts` ở project tiêu thụ:

~~~kotlin
plugins {
    id("formatting-conventions")
}
~~~

Plugin ID `formatting-conventions` được suy ra từ tên file precompiled script. Artifact `implementation(...)` cung cấp plugin ngoài và class extension trong build logic; `plugins { id(...) }` apply plugin, `configure<T>` thực hiện cấu hình bằng API typed.

Trong included build `build-logic`, project tiêu thụ thường dùng `pluginManagement { includeBuild("build-logic") }` ở settings, cùng repositories/dependencies hợp lệ ở phía build logic. **Không** thêm `version "8.11.0"` vào `plugins` của `formatting-conventions.gradle.kts`: version đã được chốt bởi `implementation(...)` của build logic.

Đối với **binary plugin** (class Kotlin/Java implement `Plugin<Project>`), cũng phải dùng API Gradle qua object `Project` thay vì generated accessor riêng của build script tiêu thụ.

## 13. Dịch DSL Groovy của plugin ngoài sang Kotlin

Nhiều tài liệu plugin viết mẫu Groovy:

~~~groovy
plugins {
    id 'com.diffplug.spotless' version '8.11.0'
}

spotless {
    format 'misc', {
        target '*.md'
        endWithNewline()
    }
}
~~~

Không thể paste thẳng vào `build.gradle.kts`. Dạng Kotlin:

~~~kotlin
plugins {
    id("com.diffplug.spotless") version "8.11.0"
}

spotless {
    format("misc") {
        target("*.md")
        endWithNewline()
    }
}
~~~

Kotlin dùng dấu ngoặc tròn cho lời gọi và cú pháp lambda, yêu cầu kiểu được compiler biết. Nếu tài liệu plugin chỉ công bố Groovy Closure, tra public Java/Kotlin API của đúng phiên bản để biết cách gọi; một số overload có thể khác. Không mặc định rằng mọi Groovy block là một extension; nó có thể là task, container element hoặc API tùy biến.

Đặc biệt, tên package của extension có thể giữ một tên thương hiệu cũ dù plugin ID đã đổi. Tên extension được plugin đăng ký, không được sinh từ cách chuyển tên plugin ID sang camelCase.

## 14. Bảng lỗi thường gặp

| Dấu hiệu | Khả năng | Cách xử lý |
| --- | --- | --- |
| `Unresolved reference: spotless` | Accessor không sinh do apply muộn/nhầm scope/tên. | Apply trong `plugins` hoặc dùng `configure<SpotlessExtension>` sau khi plugin apply. |
| `Unresolved reference: SpotlessExtension` | Class thiếu trên classpath hoặc package sai. | Kiểm tra plugin dependency, marker artifact và public type. |
| `Plugin ... was not found` | Plugin repo/ID/version/network sai. | Kiểm tra `pluginManagement.repositories`, proxy, quyền và phiên bản. |
| `Extension of type ... does not exist` | Plugin chưa apply đúng project hoặc extension chưa tạo. | Apply đúng project, bảo đảm thứ tự, có thể dùng `withPlugin`. |
| `Extension with name ... does not exist` | Sai extension name hoặc plugin không cung cấp extension. | Đọc docs, dùng `findByName` để chẩn đoán. |
| `ClassCastException` | Cast object sang type sai. | Dùng type public chính thức và `as?` để báo lỗi rõ. |
| Root dùng `apply false` rồi cấu hình root | Root không có extension của plugin. | Áp dụng plugin ở root nếu cần hoặc cấu hình tại subproject có plugin. |
| `libs.plugins.spotless` hoạt động nhưng `spotless { }` thiếu | Catalog accessor khác model accessor. | Kiểm tra thực sự apply plugin lúc sinh model accessor. |
| `api(...)`/`implementation(...)` unresolved | Configuration được tạo sau thời điểm accessor sinh. | Dùng `dependencies.add("api", "...")` hoặc `"api"("...")`. |
| `tasks.test` unresolved | Task accessor không sinh, task không tồn tại hoặc sai project. | Xem `tasks --all`; dùng `tasks.named<Test>("test")` nếu task đã có. |
| IDE báo lỗi nhưng terminal build thành công | IDE chưa sync model/script dependencies. | Sync Gradle, reimport, kiểm tra Kotlin DSL IDE cache. |
| `version "..."` trong precompiled script báo lỗi | Precompiled script plugin không nhận version ở đó. | Đặt version vào dependency `implementation(...)` của build logic. |
| Script plugin qua `apply(from=...)` không có accessor | Loại script không nhận generated model accessors tương tự main script. | Dùng Gradle typed API, cân nhắc convention plugin. |
| Cập nhật plugin làm method/property không còn | API hoặc runtime requirements thay đổi. | Đối chiếu changelog, API phiên bản được pin và Wrapper/JDK. |

## 15. Quy trình sửa lỗi thực tế

1. **Kiểm tra đúng đề bài:** plugin nào, cấu hình extension nào, project nào? Phân biệt root, `:app`, Settings và build logic.
2. **Xác nhận plugin resolve/apply:** xem `plugins { }`, `apply false`, `apply(plugin)`, `pluginManagement.repositories`. Chạy `./gradlew help` để lấy lỗi thật.
3. **Kiểm tra task và accessor:** `./gradlew tasks --all`, `./gradlew kotlinDslAccessorsReport` và tài liệu public extension. Nếu plugin chỉ có task, đừng tìm extension không tồn tại.
4. **Chọn giải pháp:** với main project script thông thường, đưa plugin vào `plugins { }` để có accessor; nếu phải apply muộn, dùng `configure<ExtensionType>`.
5. **Sửa classpath khi cần:** nếu compiler không thấy type, thêm marker dependency cho build logic hoặc khai báo plugin đúng cách trên script classpath. Chỉ import package đúng khi class đã hiện diện.
6. **Xử lý plugin có điều kiện:** dùng `pluginManager.withPlugin` cho callback cấu hình; đừng lạm dụng `afterEvaluate`.
7. **Dùng API đúng loại:** `tasks.named` cho task, `dependencies.add` cho configuration, `configure<T>` cho extension, `named(...)` cho phần tử của container.
8. **Xác nhận ngoài IDE:** `./gradlew help` chạy được không? Nếu được mà IDE lỗi, Sync/Import Gradle trước khi làm phức tạp mã.
9. **Chạy task có hành vi thực:** `spotlessCheck` hoặc task tương ứng; nếu `spotlessApply` sửa file, kiểm tra diff; pin plugin version trong CI.
10. **Đóng gói logic lặp:** sử dụng precompiled script/binary convention plugin khi nhiều module dùng chung cấu hình.

### Checklist trước khi chốt

- [ ] Đúng plugin ID, version và plugin repository.
- [ ] Plugin được áp dụng vào đúng project; `apply false` chỉ chuẩn bị classpath.
- [ ] Biết extension name và public extension type, không đoán theo plugin ID.
- [ ] Phân biệt generated accessor với extension object.
- [ ] Nếu accessor thiếu, dùng typed API có classpath phù hợp.
- [ ] Không dùng `afterEvaluate`/reflection/cast không kiểm soát để che lỗi thứ tự.
- [ ] Không nhầm `libs.plugins.*` với extension accessor.
- [ ] Với precompiled script plugin, version được đặt trong build-logic dependency.
- [ ] Kiểm tra bằng Wrapper, task thực tế và IDE sync; không chỉ dựa vào màu code editor.
- [ ] Không cho logic cấu hình bất ngờ tạo artifact; công việc thực thi thuộc task action của plugin.

## 16. Tự kiểm tra

1. **`com.diffplug.spotless` có đồng nghĩa `spotless` không?** Không. Cái đầu là plugin ID; cái sau là extension name/accessor khi phù hợp.
2. **Vì sao `apply(plugin = "...")` không sinh accessor mới cho thân script?** Vì nó chạy sau thời điểm Gradle tạo schema accessors.
3. **Cần làm gì nếu extension có thật, class public có sẵn nhưng không có accessor?** Dùng `configure<ExtensionType> { ... }` hoặc `extensions.getByType(...)`.
4. **`plugins { id(...) version "..." apply false }` có extension chưa?** Chưa; plugin chưa apply cho project.
5. **Nếu compiler không thấy `SpotlessExtension`, đổi `spotless` thành `configure<SpotlessExtension>` có đủ không?** Không; phải bảo đảm class ở trên compile classpath và đúng package.
6. **Khi plugin chỉ tạo task, dùng API nào?** `tasks.named<Type>("taskName")` hoặc `tasks.named("taskName")`.
7. **Version catalog tạo `libs.plugins.spotless` có đồng thời tạo `spotless { }`?** Không, đó là hai hệ accessor khác nhau.
8. **Precompiled script plugin bên ngoài khai báo version ở đâu?** Trong `implementation(...)` của build logic project, không trong `plugins` của precompiled script.
9. **Tại sao `findByName("spotless")` chưa thể gọi mọi method Spotless?** Vì object trả về không mang static public type để Kotlin kiểm tra các method.
10. **Làm sao biết lỗi chỉ ở IDE?** Chạy `./gradlew help` và task thật. Nếu CLI chạy đúng, đồng bộ lại Gradle model trong IDE.

## Tài liệu chính thức

- [Gradle Kotlin DSL Primer: generated accessors và fallback](https://docs.gradle.org/current/userguide/kotlin_dsl.html).
- [Gradle: Migrating from Groovy to Kotlin DSL](https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html).
- [Gradle: Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html).
- [Gradle: Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html).
- [Gradle Kotlin DSL API: configure](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.kotlin.dsl/configure.html).
- [Spotless trên Gradle Plugin Portal](https://plugins.gradle.org/plugin/com.diffplug.spotless).
- [Spotless Gradle Plugin README](https://github.com/diffplug/spotless/blob/main/plugin-gradle/README.md).
