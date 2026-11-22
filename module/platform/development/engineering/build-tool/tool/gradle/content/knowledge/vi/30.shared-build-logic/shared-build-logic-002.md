# Script plugin và giới hạn về kiểu, classpath, kiểm thử trong Gradle

## 1. Tổng quan: dùng lại build logic nhanh nhưng không phải plugin đóng gói hoàn chỉnh

Khi nhiều Java subprojects cùng phải dùng Java 17, encoding UTF-8, JUnit Platform, cùng quy tắc compiler và vài task tiện ích, cách đơn giản nhất là sao chép cùng một đoạn cấu hình vào nhiều file `build.gradle`. Tuy nhiên copy–paste gây **configuration drift**: module A được sửa nhưng module B dùng bản cũ; một rule có thể bị bỏ sót; CI và máy developer không còn đồng nhất.

Gradle cho phép tách đoạn Groovy DSL ra một file như `gradle/java-conventions.gradle` rồi áp dụng:

~~~groovy
apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

File được áp dụng như trên gọi là **script plugin** hay **applied script plugin**. Nó phù hợp một đoạn build logic nhỏ, dùng trong cùng build hoặc để thử nhanh ý tưởng. Nhưng nó **không tương đương** với **precompiled script plugin** hoặc **binary plugin** về mặt định danh plugin, compile-time typing, classpath management, testing và khả năng tái sử dụng/đóng gói.

Bài này thuộc nhóm **Build logic dùng chung** của **Build Tool Gradle**. Trọng tâm là ba giới hạn được nêu trong đề bài:

- **Giới hạn về kiểu (typing):** Groovy DSL dynamic resolution, thiếu API/plugin extension type được đóng gói thành một hợp đồng ổn định; Kotlin DSL applied script plugins không nhận type-safe model accessors tự động.
- **Giới hạn về classpath:** tập các plugin/classes có sẵn cho script phải đến từ Gradle API, plugin/buildscript resolution hoặc build logic đúng scope; dependency của Java application không tự trở thành dependency để biên dịch/chạy build script.
- **Giới hạn về kiểm thử:** script plugin không mặc định là một project plugin có test suite/plugin-under-test classpath riêng; cần kiểm thử bằng Gradle build fixture hoặc chuyển sang convention/binary plugin và Gradle TestKit.

Mục tiêu cuối bài: tạo được ví dụ Java 17 chạy thật với **hai modules**, dùng một script `apply from:` chung; hiểu thời điểm đánh giá script, phân biệt đường dẫn và scope, phát hiện classpath/type errors, viết test hồi quy cho build logic, rồi lựa chọn lúc nào nên chuyển sang precompiled convention plugin hoặc binary plugin.

**Điều kiện môi trường:** Gradle Wrapper hợp lệ, Gradle version tương thích JDK 17, Java 17 toolchain có sẵn hoặc được cấp qua toolchain resolver, Maven Central truy cập được nếu dependencies chưa cache. Lệnh `./gradlew` dành cho Linux/macOS; PowerShell Windows thay bằng `.\gradlew.bat`. Các đoạn “trích đoạn” chỉ minh họa ý tưởng và không được coi là project hoàn chỉnh trừ khi ghi rõ.

## 2. Ba hình thức tái sử dụng build logic

| Tiêu chí | Script plugin `apply from:` | Precompiled script plugin | Binary plugin |
| --- | --- | --- | --- |
| Nơi lưu | File `.gradle` hoặc `.gradle.kts` bất kỳ trong build | `buildSrc` hoặc included build như `build-logic/src/main/groovy`/`kotlin` | Plugin project chứa classes Java/Kotlin/Groovy |
| Cách dùng | `apply from: '...'` | `plugins { id 'company.java-conventions' }` | `plugins { id 'company.java-conventions' }` |
| Plugin ID độc lập | **Không** tự có chỉ vì tên file | Có, dựa trên tên script/package theo quy tắc | Có, đăng ký plugin ID qua metadata |
| `plugins { }` bên trong file | **Không được hỗ trợ** | Có trong precompiled plugin script | Plugin class gọi `pluginManager.apply` |
| Kiểu/libraries | DSL của script/classpath đang khả dụng; Groovy thường dynamic | Được Gradle biên dịch như plugin; build-logic classpath rõ hơn | Class/source compilation, public types/API được khai |
| TestKit | Có thể black-box test file `apply from` bằng fixture | Có thể test plugin bằng ID trong build-logic test fixture | Có cơ chế plugin-under-test classpath/test lifecycle rõ |
| Phát hành JAR/plugin | Không phải published plugin artifact | Có thể đóng gói, thường khuyến nghị dùng nội bộ | Phù hợp publish/chia sẻ giữa builds |
| Nên chọn | One-off, chuyển tiếp, thử nghiệm nhỏ | Shared conventions nội bộ | Logic có type, extension, task custom, phân phối lâu dài |

**Quan trọng:** từ “script plugin” ở đây chỉ **applied script** `apply from:`, khác với **precompiled script plugin** có file đuôi `.gradle` nhưng nằm trong **plugin source set** và được Gradle biên dịch/đăng ký với ID. Một file `gradle/java-conventions.gradle` ở root **không tự trở thành** plugin ID `java-conventions`.

Tài liệu Gradle hiện đại đánh giá applied script plugins phù hợp tiện ích nhỏ/quick experiments hơn là nền tảng lâu dài cho production build logic phức tạp. Không có nghĩa mọi `apply from` đều “không chạy được”; vấn đề là maintainability, testing boundary, classpath và phát hiện lỗi càng khó khi logic lớn.

## 3. Cơ chế `apply from:` hoạt động ra sao?

Xét:

~~~groovy
// app/build.gradle
plugins {
    id 'application'
}

apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

Gradle đánh giá file được áp dụng như **một Gradle script gắn với target project**, ở đây là `:app`. Nội dung top-level của script dùng project model/context tương ứng để thêm tasks, cấu hình extension hoặc đăng ký callbacks. Nó không phải lời gọi một Java class method “copy/paste text” theo nghĩa lexical; Gradle biên dịch/evaluate script và áp cấu hình lên target.

### 3.1. Thời điểm configuration và execution

Hai giai đoạn chính:

1. **Configuration:** Gradle đánh giá build scripts và applied scripts, đăng ký/configure tasks theo API. Trong các trường hợp Configuration Cache hit, phần cấu hình có thể được tái sử dụng thay vì đánh giá lại.
2. **Execution:** Gradle chạy actions của các tasks được chọn theo task graph.

Ví dụ file applied script:

~~~groovy
tasks.register('sayFromScript') {
    group = 'help'
    description = 'Prints a marker during task execution.'

    doLast {
        logger.quiet('script-plugin-ok')
    }
}
~~~

Với target project, `tasks.register` cấu hình **một task provider** trong configuration phase. `logger.quiet(...)` nằm trong `doLast`, chỉ chạy khi task action thực thi. Không in log ở top-level chỉ để xác minh build luôn chạy: Configuration Cache có thể bỏ qua cấu hình trong lần sau.

Lệnh:

~~~bash
./gradlew -q :app:sayFromScript
~~~

dự kiến in:

~~~text
script-plugin-ok
~~~

Nếu cùng script được áp dụng ở `:core` và `:app`, hai project có **hai tasks riêng**: `:core:sayFromScript` và `:app:sayFromScript`. File chung chỉ mô tả **cùng quy ước**, không gộp task containers của modules.

### 3.2. Đường dẫn script: relative hay root?

Hai cú pháp phổ biến:

~~~groovy
apply from: 'gradle/java-conventions.gradle'
~~~

và:

~~~groovy
apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

Cú pháp thứ nhất dùng path tương đối theo cơ chế resolution của script/target context; trong multi-project build, nếu gọi trực tiếp ở `app/build.gradle` nó dễ trỏ tới location khác dự kiến. Cú pháp thứ hai chỉ rõ file nằm dưới root project, **phù hợp khi `:core` và `:app` dùng chung một file root/gradle**.

Đừng hard-code đường dẫn tuyệt đối như `C:\Users\dev\...` hoặc `/home/alice/...`: CI và máy đồng nghiệp sẽ không có path đó. Đừng dùng working directory hiện tại của shell làm hợp đồng; người dùng có thể chạy Wrapper từ nhiều thư mục.

### 3.3. Scope nhận cấu hình

Script được `apply from` ở `:core` cấu hình `:core`, không tự áp dụng cho `:app`. Cần apply riêng trong từng module hoặc dùng convention plugin đúng scope.

Ví dụ:

~~~groovy
// core/build.gradle
plugins {
    id 'java-library'
}
apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

~~~groovy
// app/build.gradle
plugins {
    id 'application'
}
apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

Hai file cùng tiêu thụ common script. Điều đó tốt hơn root script `subprojects { ... }` đụng trực tiếp mutable state của mọi subproject, nhưng khi lớn lên vẫn nên chuyển sang convention plugin để được type/classpath/test tooling đầy đủ.

### 3.4. Thứ tự áp dụng plugin quan trọng

Nếu shared script cấu hình `java` extension, `JavaCompile` tasks hoặc `Test` tasks nhưng project chưa áp dụng Java plugin, model elements có thể chưa tồn tại.

Cách đơn giản: consumer build script áp dụng `java-library`/`application` trước khi `apply from`. Với script dùng ở nhiều loại project, có thể chờ Java plugin bằng:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

`pluginManager.withPlugin('java')` đăng ký action cho sự kiện plugin `java` được áp dụng; nếu plugin đã áp dụng, callback có thể thực hiện ngay. `tasks.withType(...).configureEach` dùng configuration avoidance. Cách này tránh ép thực hiện `tasks.getByName('compileJava')` quá sớm.

Với project không có Java plugin, callback không cấu hình Java compile tasks. Nhưng nếu muốn **bắt buộc** module phải là Java, hãy apply plugin trong consumer hoặc fail với thông báo rõ ràng; không để chính sách áp dụng âm thầm sai loại project.

## 4. Những giới hạn về cú pháp plugin

### 4.1. Script plugin không dùng `plugins { }` DSL

Đây là nội dung **không hợp lệ** trong file applied script:

~~~groovy
// KHÔNG dùng trong gradle/java-conventions.gradle áp bằng apply from:
plugins {
    id 'java-library'
}
~~~

Gradle `plugins { }` DSL được xử lý đặc biệt khi Gradle biên dịch/resolves plugin trong build scripts/precompiled scripts. Nó **không được phép trong applied script plugin**. Lỗi có thể chỉ đến việc plugins block chỉ được dùng ở những loại scripts phù hợp.

Hai chiến lược thay thế:

**A. Consumer khai plugin trong `build.gradle`**, applied script chỉ cấu hình:

~~~groovy
plugins {
    id 'java-library'
}

apply from: "$rootDir/gradle/java-conventions.gradle"
~~~

**B. Với core plugin đã nằm trong Gradle distribution**, applied script có thể dùng legacy application method:

~~~groovy
apply plugin: 'java-library'
~~~

Tuy nhiên nếu script plugin bắt đầu áp nhiều plugins, quản lý third-party plugin versions, tạo extensions và custom tasks, đó là dấu hiệu nên chuyển sang **precompiled convention plugin** hoặc **binary plugin**.

### 4.2. `apply plugin:` không tương đương plugin resolution declaration

Ví dụ:

~~~groovy
apply plugin: 'com.example.some-external-plugin'
~~~

không khiến Gradle tự biết external plugin implementation version và nơi lấy JAR. Plugin phải **đã khả dụng trên classpath thích hợp** qua plugin/buildscript setup. Đây là nguyên nhân phổ biến của lỗi “Plugin with id ... not found”.

Đối với third-party plugins, ưu tiên công khai version trong consumer build `plugins { id '...' version '...' }`, trong plugin management policy hoặc trong build-logic dependencies của convention plugin. Đừng copy một loạt `buildscript { repositories; dependencies }` riêng vào nhiều applied scripts rồi để mỗi script quyết định version của cùng plugin.

### 4.3. Precompiled script plugin thì khác

Trong build-logic convention plugin:

~~~groovy
// build-logic/src/main/groovy/company.java-conventions.gradle
plugins {
    id 'java-library'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

File này **không được áp bằng `apply from:`** trong consumer. Nó nằm trong plugin source set được Gradle biên dịch và đăng ký ID, để consumer dùng:

~~~groovy
plugins {
    id 'company.java-conventions'
}
~~~

Hai đoạn có ngữ pháp giống Groovy DSL nhưng **lifecycle, packaging và classpath khác nhau**. Không di chuyển file applied script sang `build-logic/src/main/groovy` rồi giữ nguyên cả `apply from` và kỳ vọng có thêm plugin ID; cần thiết lập build-logic plugin project.

## 5. Giới hạn về kiểu (types) và DSL

### 5.1. Groovy dynamic resolution: tiện nhưng dễ lỗi runtime

Trong Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

`JavaCompile` là Gradle task type, `options.encoding` là property được định nghĩa. Đây là cách tương đối rõ kiểu dù dùng Groovy.

Nhưng nếu gõ sai:

~~~groovy
// Sai tên property, chỉ để minh họa lỗi:
tasks.withType(JavaCompile).configureEach {
    options.encodng = 'UTF-8'
}
~~~

Groovy có thể không phát hiện lỗi cho đến lúc callback được thực hiện trong configuration, dẫn đến `MissingPropertyException` hoặc lỗi DSL tương đương. Trong build lớn, lỗi có thể chỉ xuất hiện ở module dùng task/plugin tương ứng, không nhất thiết ở mọi `./gradlew help`.

**Cách giảm rủi ro ngay cả trước khi migration:** dùng task types như `JavaCompile`/`Test`, `tasks.named`/`configureEach`, Gradle public APIs và các test fixtures xác thực task properties. Tránh phụ thuộc vào dynamic methods chưa được document.

### 5.2. Kotlin applied script không có type-safe model accessors

Kotlin DSL được biết đến với `implementation(...)`, `java { ... }` và `tasks.test { ... }` type-safe accessors. Nhưng Gradle phân biệt:

- **Main build script** có `plugins { }` được đánh giá tại thời điểm phù hợp: có type-safe accessors cho model elements từ plugins được apply ở plugins block.
- **Precompiled script plugin**: cũng có cơ chế type-safe model accessors theo plugin source set và các quy tắc Gradle.
- **Applied script plugin** `apply(from = "...gradle.kts")`: **không có type-safe model accessors tự động**.

Ví dụ hướng xử lý bằng API có kiểu rõ trong **applied Kotlin script**, khi Java plugin đã được áp dụng và JavaPluginExtension type có sẵn:

~~~kotlin
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.compile.JavaCompile

extensions.configure(JavaPluginExtension::class.java) {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType(JavaCompile::class.java).configureEach {
    options.encoding = "UTF-8"
}
~~~

Đây là **đoạn minh họa Kotlin applied script**, không phải file `build.gradle.kts` hoàn chỉnh; consumer phải áp Java plugin trước và apply script đúng path. Nếu type cần import khác namespace, IDE/Gradle Kotlin compiler sẽ báo compile error; đừng “chữa” bằng một dynamic accessor vốn không tồn tại trong script plugin.

### 5.3. Không có hợp đồng extension riêng chỉ nhờ tách file

Giả sử applied script đọc:

~~~groovy
def desiredJavaVersion = 17
~~~

`desiredJavaVersion` là local script variable, **không phải** một extension mạnh kiểu do consumer sử dụng trong DSL. Nếu muốn mỗi module cấu hình:

~~~groovy
teamJava {
    languageVersion.set(17)
    strictMode.set(true)
}
~~~

nên định nghĩa một **extension class** có Gradle `Property<T>` hoặc `Provider<T>` rõ ràng trong plugin project, ví dụ binary plugin trong included build, rồi đăng ký với `extensions.create`. Groovy script vẫn có thể cấu hình extra properties hoặc tạo dynamic extension, nhưng thiếu một loại API ổn định có unit tests thường làm maintenance khó hơn.

### 5.4. Custom Task types nên đặt ngoài script lớn

Anti-pattern thường gặp:

~~~groovy
// Trích đoạn anti-pattern trong applied script:
tasks.register('writeInfo') {
    doLast {
        file("$buildDir/info.txt").text = 'Hello'
    }
}
~~~

Vấn đề: output được ghi từ action nhưng không được khai báo là `@OutputFile` hoặc task output; `file(...)`/`buildDir` truy cập project model trong execution có thể gây vấn đề với Configuration Cache trên Gradle hiện đại. Task cũng không có input `Property<String>`, không có cách kiểm thử riêng logic ghi file.

Khi cần task thực sự tạo artifact, dùng custom type như:

~~~java
// Ví dụ task class Java trong binary/convention plugin project,
// cần cấu hình plugin project và Gradle API để biên dịch.
package org.example.buildlogic;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

import java.io.IOException;
import java.nio.file.Files;

@CacheableTask
public abstract class WriteInfoTask extends DefaultTask {
    @Input
    public abstract Property<String> getText();

    @OutputFile
    public abstract RegularFileProperty getDestination();

    @TaskAction
    public void write() throws IOException {
        var output = getDestination().get().getAsFile().toPath();
        Files.createDirectories(output.getParent());
        Files.writeString(output, getText().get());
    }
}
~~~

Class trên là **một thành phần plugin**, không phải Java source của demo app. Nó có typed inputs/outputs để Gradle kiểm tra task history/cache behavior. Cần thêm đăng ký task kiểu `WriteInfoTask` trong plugin project và functional tests với Gradle TestKit; chỉ dán class vào `build.gradle` không tạo plugin published.

**Cân nhắc cacheability:** `@CacheableTask` chỉ đúng khi task deterministic, không phụ thuộc vào thông tin undeclared hoặc external state; ví dụ ghi chính xác text vào file phù hợp. Nếu task có side effects mạng, timestamp hoặc secret, không gắn `@CacheableTask` bừa bãi.

## 6. Classpath của build logic khác classpath Java application

Đây là một trong những nguồn gây lỗi khó hiểu nhất.

| Classpath/nguồn | Chứa | Được dùng khi nào? |
| --- | --- | --- |
| **Gradle API / DSL** | `Project`, `Task`, `JavaCompile`, `Test` và API đi cùng distribution | Khi Gradle biên dịch/evaluate build logic |
| **Buildscript/plugin classpath** | Implementation classes của Gradle plugins/build logic dependencies đã resolve đúng scope | Khi applied script muốn sử dụng plugin types/external classes |
| **Java `compileClasspath`** | `implementation`/`api` dependencies và Java output phù hợp | Khi `compileJava` biên dịch mã sản phẩm |
| **Java `runtimeClasspath`** | Main outputs và runtime libraries | Khi chương trình Java chạy |
| **`testCompileClasspath`/`testRuntimeClasspath`** | JUnit API, engine/launcher, test classes, main output | Khi biên dịch/chạy JUnit tests |

Ví dụ trong `app/build.gradle`:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Điều này làm `StringUtils` có thể import vào **Java source của app**, không có nghĩa applied script `gradle/java-conventions.gradle` được phép:

~~~groovy
// Không giả định lớp này có trên buildscript classpath:
import org.apache.commons.lang3.StringUtils
~~~

Classpath của code sản phẩm và Gradle script là hai scopes riêng. Nếu build logic thực sự cần gọi Commons Lang trong **configuration**, library đó cần được cung cấp như dependency của **build logic**, không nhét vào application `implementation` để “thử may”.

### 6.1. Tại sao core Gradle types thường có sẵn?

Gradle expose APIs như `Project`, `Task`, `JavaCompile`, `Test`, `Provider` hoặc `RegularFileProperty` cho build scripts. Vì thế nhiều Groovy script plugin đơn giản có thể dùng:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

mà không cần tự khai dependency Gradle API trong `app/build.gradle`. Nhưng một external plugin-specific type, ví dụ một task class do Spotless/SpotBugs hoặc một tool nội bộ tạo, **không phải** Gradle core type; khả dụng của nó phụ thuộc plugin/build logic classpath.

### 6.2. Plugin ID có thể apply không đồng nghĩa class import luôn thành công

Hai hoạt động khác nhau:

1. `pluginManager.apply('some.plugin.id')`: tìm plugin implementation theo ID đã có thể resolve, rồi áp dụng lên project.
2. `import com.vendor.gradle.SomeExtension` hoặc `tasks.withType(SomeVendorTask)`: Groovy/Kotlin script compiler cần biết **class type** đó.

Có thể có trường hợp plugin được áp dụng từ consumer nhưng một applied script khác không compile được import type theo kỳ vọng vì script classpath/scope không được thiết kế rõ. Khi cần configure extension qua type, cách ổn định hơn là đưa plugin dependencies vào **precompiled/binary plugin project** và compile/test ở đó.

### 6.3. Script `buildscript { }` không phải giải pháp dùng chung tốt nhất

Gradle có legacy `buildscript { repositories { ... }; dependencies { classpath '...' } }` để cấu hình script classpath. Nó vẫn có use cases, nhưng trong một hệ thống nhiều script plugins, mỗi file tự resolve một version hoặc tự định nghĩa repositories có thể tạo:

- Version conflicts của external Gradle plugin dependencies.
- Mất khả năng review một nơi duy nhất.
- Lỗi classloader/visibility khó tái hiện ở modules khác.
- Configuration work không cần thiết và maintenance overhead.
- Khả năng build khác nhau giữa CI và developer nếu versions không được pin.

Không khẳng định cứ dùng `buildscript` là sai; nhưng với shared quality/test conventions phức tạp, nên dùng plugin resolution policy ở `settings.gradle` và/hoặc **build-logic included build** với dependency declarations phù hợp.

### 6.4. External plugin trong precompiled convention plugin

Với precompiled plugin trong `build-logic`, cách được Gradle document là khai external plugin implementation vào **dependencies của build-logic project**, sau đó apply plugin ID trong precompiled script mà **không đặt version tại đó**.

Cấu trúc khái niệm:

~~~text
build-logic/
  build.gradle
  src/main/groovy/
    company.quality-conventions.gradle
~~~

Với `build-logic/build.gradle`, plugin project pin version của external Gradle plugin trong `dependencies { implementation 'group:artifact:version' }` theo tài liệu vendor; trong `company.quality-conventions.gradle`, dùng `plugins { id 'vendor.plugin.id' }` không kèm `version`.

Đây là **mô hình classpath của plugin project**, khác với Java application `implementation` trong consumer. Khi build-logic được tách riêng, Gradle biên dịch plugin script trên một classpath được quản lý và có thể thêm tests trước khi sử dụng.

### 6.5. Version Catalog không tự giải quyết plugin implementation classpath

Version catalog hữu ích để chuẩn hóa versions/aliases; nó không tự khiến mọi applied script nhận thêm libraries vào script compiler classpath. Với precompiled plugin, các plugin aliases/`version` có giới hạn trong `plugins { }` block của precompiled script; đọc tài liệu Gradle/vender plugin để khai implementation dependency đúng chỗ.

Đừng sửa một `ClassNotFoundException` bằng cách chỉ tăng `implementation '...'` của Java app mà chưa xác định exception đến từ **build script** hay **Java runtime**.

## 7. Ví dụ hoàn chỉnh: hai Java 17 modules dùng chung script plugin

Để thực hành, ta tạo:

- `:core` — Java library có hàm chào.
- `:app` — Java application phụ thuộc core và có `main`.
- `gradle/java-conventions.gradle` — **applied script plugin** dùng chung cả hai modules, cấu hình toolchain, encoding, JUnit Platform và task quan sát.

### 7.1. Cấu trúc project

~~~text
script-plugin-lab/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar
│   │   └── gradle-wrapper.properties
│   └── java-conventions.gradle
├── core/
│   ├── build.gradle
│   └── src/
│       ├── main/java/demo/core/Greeting.java
│       └── test/java/demo/core/GreetingTest.java
└── app/
    ├── build.gradle
    └── src/
        ├── main/java/demo/app/Main.java
        └── test/java/demo/app/MainTest.java
~~~

Bốn file Gradle Wrapper phải được tạo bằng Gradle Wrapper thực sự. Người học không thể tạo các file rỗng để thay thế script/JAR của Wrapper. Nếu cần bootstrap, hãy chạy `gradle wrapper` trên máy đã cài Gradle distribution tương thích và kiểm `gradle-wrapper.properties`.

### 7.2. Root `settings.gradle`

~~~groovy
rootProject.name = 'script-plugin-lab'
include 'core', 'app'
~~~

Mỗi module có một `build.gradle` riêng. Root không cần một `build.gradle` phức tạp cho ví dụ; Gradle vẫn tạo multi-project build qua settings.

### 7.3. Applied script `gradle/java-conventions.gradle`

~~~groovy
// Applied Groovy script plugin: NO plugins {} block here.

pluginManager.withPlugin('java') {
    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
    }

    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}

tasks.register('describeConventions') {
    group = 'help'
    description = 'Prints the conventions shared by Java modules.'

    doLast {
        logger.quiet('shared-script: Java 17 | UTF-8 | JUnit Platform')
    }
}
~~~

Giải thích từng phần:

1. Không có `plugins { }`; file này được áp bằng `apply from`.
2. `pluginManager.withPlugin('java')` cấu hình khi Java plugin đã được áp dụng bởi consumer. `java-library` và `application` đều mang vào Java plugin.
3. `java.toolchain.languageVersion` chọn Java 17 cho các Gradle Java tasks hỗ trợ.
4. `tasks.withType(JavaCompile).configureEach` cấu hình Java compile tasks mà không yêu cầu realize tất cả ngay.
5. `tasks.withType(Test).configureEach` cấu hình test tasks hiện tại và tương lai của từng module để dùng JUnit Platform. JUnit dependencies vẫn phải được consumer khai riêng.
6. `tasks.register('describeConventions')` tạo task quan sát trong **project đang apply**. `logger.quiet` in ở execution và hiển thị khi CLI dùng `-q`.
7. Không có `afterEvaluate`, không resolve dependencies hay đọc/ghi file khi configuration. Đây là phần thiết kế giúp script ít gây side effects và dễ đoán hơn.

Một script plugin được áp vào cả hai modules nhưng vẫn có **hai task providers tách biệt**. Mỗi project chạy test của chính nó và dùng classpaths riêng.

### 7.4. `core/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

apply from: "$rootDir/gradle/java-conventions.gradle"

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}
~~~

`java-library` là core plugin; `apply from` đưa quy ước chung vào core; `testImplementation` cung cấp JUnit Jupiter API/engine theo dependency graph; `testRuntimeOnly` bảo đảm JUnit Platform Launcher có mặt tại test execution. Với Gradle 9+, khai Launcher rõ là thói quen an toàn.

Java 17 toolchain, UTF-8 và `useJUnitPlatform()` **không lặp lại** trong `core/build.gradle` vì chúng nằm trong shared script. Điều này cho phép so sánh trước/sau khi tách logic.

### 7.5. `app/build.gradle`

~~~groovy
plugins {
    id 'application'
}

apply from: "$rootDir/gradle/java-conventions.gradle"

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Application plugin tạo `run` task và áp dụng Java plugin. `implementation project(':core')` tạo project dependency đúng API/variant model, không phải thao tác copy thủ công core JAR. Shared script cấu hình Java 17/JUnit cho app như core.

Không thêm `implementation project(':core')` vào chính core: sẽ tạo dependency ngược/vòng. Không khai `application` trong core nếu core là thư viện không có entry point.

### 7.6. `core/src/main/java/demo/core/Greeting.java`

~~~java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String rawName) {
        String name = rawName == null ? "" : rawName.strip();
        if (name.isEmpty()) {
            name = "bạn";
        }
        return "Xin chào, " + name + "!";
    }
}
~~~

Đây là Java 17 source hoàn chỉnh. `strip()` có từ Java 11. Phương thức tĩnh `Greeting.message` xử lý khoảng trắng và `null`; chương trình không cần bất kỳ Maven library nào ngoài Java standard library.

### 7.7. `core/src/test/java/demo/core/GreetingTest.java`

~~~java
package demo.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void trimsName() {
        assertEquals("Xin chào, Linh!", Greeting.message(" Linh "));
    }

    @Test
    void fallsBackOnBlank() {
        assertEquals("Xin chào, bạn!", Greeting.message("  "));
    }

    @Test
    void fallsBackOnNull() {
        assertEquals("Xin chào, bạn!", Greeting.message(null));
    }
}
~~~

Core có ba JUnit Jupiter tests. `:core:test` thực thi tests của core khi task được chọn; không tự chạy `:app:test`. `useJUnitPlatform` được cấu hình bởi applied script, không có trong `core/build.gradle`.

### 7.8. `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(Greeting.message(name));
    }
}
~~~

`Main` import `demo.core.Greeting` từ project dependency `:core`. Khi chạy `:app:run`, Application plugin chuẩn bị production outputs của core/app trên runtime classpath.

### 7.9. `app/src/test/java/demo/app/MainTest.java`

~~~java
package demo.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.core.Greeting;
import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void coreDependencyIsAvailable() {
        assertEquals("Xin chào, Mai!", Greeting.message(" Mai "));
    }
}
~~~

Đây là smoke test bảo đảm app test classpath thấy core library. Nó không cần tạo process riêng để kiểm `System.out`; app `main` sẽ được kiểm qua lệnh `run`.

### 7.10. Lệnh thực hành và output đúng

Từ root `script-plugin-lab`:

~~~bash
./gradlew -q :core:describeConventions
./gradlew -q :app:describeConventions
~~~

Mỗi lệnh in **một dòng**:

~~~text
shared-script: Java 17 | UTF-8 | JUnit Platform
~~~

Đó là marker do task action in, không phải log xuất hiện khi configuration. Cả core và app nhận cùng quy ước vì cả hai có `apply from`.

Chạy tests:

~~~bash
./gradlew :core:test
./gradlew :app:test
./gradlew test
~~~

Với project đầy đủ, `:core:test` chạy 3 methods và `:app:test` chạy 1 method. Root task selector `test` chọn tests của cả hai subprojects, tổng cộng 4 methods trong demo. `:app:test` có thể kéo production tasks từ core để cung cấp compiled classes/JAR, nhưng không mặc định chạy `:core:test` chỉ vì project dependency.

Chạy ứng dụng:

~~~bash
./gradlew -q :app:run
./gradlew -q :app:run --args="Lan"
~~~

Stdout Java program lần lượt:

~~~text
Xin chào, Gradle!
~~~

và:

~~~text
Xin chào, Lan!
~~~

`-q` ẩn phần lớn Gradle lifecycle logs, không ẩn stdout của Java app. Khi muốn kiểm task graph, bỏ `-q` và thêm `--dry-run` hoặc `--info`.

### 7.11. Kiểm bằng `javac` và `java` không qua Gradle

Do main classes chỉ dùng Java standard library, trên Linux/macOS có thể thử thủ công:

~~~bash
mkdir -p manual-out/core manual-out/app

javac -encoding UTF-8 \
    -d manual-out/core \
    core/src/main/java/demo/core/Greeting.java

javac -encoding UTF-8 \
    -cp manual-out/core \
    -d manual-out/app \
    app/src/main/java/demo/app/Main.java

java -cp "manual-out/core:manual-out/app" demo.app.Main Lan
~~~

Stdout Java chính xác:

~~~text
Xin chào, Lan!
~~~

Đây là phép kiểm API/classpath Java độc lập với Gradle. Nó **không** chứng minh applied script được thực thi, bởi `javac`/`java` không chạy Gradle tasks. Muốn kiểm shared build logic phải dùng `./gradlew :core:describeConventions`, `./gradlew :app:test` hoặc một Gradle TestKit fixture.

Trên Windows PowerShell, tạo các thư mục output trước, đặt các tham số javac trên một dòng hoặc dùng line continuation phù hợp PowerShell, và dùng dấu `;` thay cho dấu `:` trong Java classpath.

### 7.12. Kiểm task graph thật

~~~bash
./gradlew :core:tasks --all
./gradlew :app:tasks --all

./gradlew :core:test --dry-run
./gradlew :app:test --dry-run
./gradlew :app:run --dry-run
~~~

Bạn nên thấy task `describeConventions` ở cả hai modules. `--dry-run` chỉ lập graph chứ không thực thi test methods hoặc task actions. Đừng tuyên bố “JUnit pass” dựa trên một dry-run.

Để xem các lý do task chạy hoặc up-to-date:

~~~bash
./gradlew :core:test --info
./gradlew :app:test --info
~~~

`UP-TO-DATE`, `NO-SOURCE` hoặc `FROM-CACHE` là kết quả tối ưu hóa hợp lệ theo task inputs/outputs; không chứng minh shared script bị bỏ qua. Nếu thay `java-conventions.gradle`, Gradle có thể cần tính lại configuration/inputs và tasks theo thay đổi; không suy mọi task action chắc chắn sẽ chạy lại.

## 8. Kiểm thử script plugin: thử được nhưng chưa có project test tách biệt sẵn

Một điểm cần phân biệt: **Java unit tests của app/core** kiểm mã sản phẩm; **functional tests của build logic** kiểm applied script có thật sự đăng ký/configure tasks như mong đợi không. Demo ở mục 7 chỉ chứa Java tests cho core/app, nên chưa bao phủ mọi cách script plugin có thể sai.

Ví dụ một developer vô tình sửa:

~~~groovy
options.encoding = 'UTF16'
~~~

trong shared script. Java tests vẫn có thể compile tùy source, nên không bảo đảm báo lỗi policy. Cần test hoặc assertion riêng cho **build configuration**.

### 8.1. Manual smoke tests có mục tiêu

Kiểm tra riêng:

~~~bash
./gradlew -q :core:describeConventions
./gradlew -q :app:describeConventions
./gradlew :core:test
./gradlew :app:test
~~~

Chúng trả lời:

- Shared script được apply vào cả hai modules hay không?
- Task marker có tồn tại và thực thi đúng không?
- Test task của từng module có cấu hình JUnit Platform không?
- Java 17 compiler được cung cấp đúng hay không?
- Khi thêm module mới, có quên `apply from` không?

Nhưng chỉ smoke test bằng tay dễ bị quên trong PR; nên tự động hóa build logic tests khi policy trở nên quan trọng.

### 8.2. Gradle TestKit chạy một build fixture thật

Gradle TestKit có API `GradleRunner` để chạy Gradle trong thư mục fixture độc lập. Ta có thể copy một script plugin vào fixture, viết `settings.gradle`/`build.gradle` tối thiểu, gọi task rồi assert stdout/task outcome.

**Quan trọng:** thử một file `apply from` **không nhất thiết cần** `withPluginClasspath()`, vì chính fixture chứa file script. API `withPluginClasspath()` thường phục vụ plugin classes được build bằng `java-gradle-plugin` khi plugin-under-test được apply qua `plugins { id '...' }`; không giả định file applied script sẽ được inject tự động như một binary plugin.

Ví dụ dưới là **một TestKit test project tách biệt** với demo ở mục 7. Nó tự kiểm hành vi `apply from` mà không phụ thuộc source code core/app. Điều đó chứng minh ta **có thể** test applied script plugins, chỉ là không có packaging/test harness sẵn như plugin project.

### 8.3. Project kiểm thử build logic

Cây thư mục:

~~~text
script-logic-tests/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/test/java/demo/logic/ScriptPluginFunctionalTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'script-logic-tests'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation gradleTestKit()
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`gradleTestKit()` đưa TestKit APIs vào compile/test classpath của test project. Nó **không** tự cấu hình test framework; JUnit dependencies và `useJUnitPlatform()` vẫn cần thiết. TestKit fixture dùng một Gradle distribution tương ứng môi trường chạy TestKit hoặc được chỉ định rõ, nên cần quản lý Gradle version khi muốn test compatibility.

### 8.4. File `src/test/java/demo/logic/ScriptPluginFunctionalTest.java`

~~~java
package demo.logic;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ScriptPluginFunctionalTest {
    @TempDir
    Path fixtureRoot;

    @Test
    void appliesScriptFromFixture() throws IOException {
        Path scripts = Files.createDirectories(
            fixtureRoot.resolve("gradle")
        );

        Files.writeString(
            fixtureRoot.resolve("settings.gradle"),
            "rootProject.name = 'fixture'\n"
        );

        Files.writeString(
            fixtureRoot.resolve("build.gradle"),
            "plugins { id 'java' }\n" +
            "apply from: 'gradle/conventions.gradle'\n"
        );

        Files.writeString(
            scripts.resolve("conventions.gradle"),
            "tasks.register('proof') {\n" +
            "    doLast { logger.quiet('script-ok') }\n" +
            "}\n"
        );

        BuildResult result = GradleRunner.create()
            .withProjectDir(fixtureRoot.toFile())
            .withArguments("proof", "--quiet")
            .build();

        assertTrue(result.getOutput().contains("script-ok"));
        assertNotNull(result.task(":proof"));
        assertEquals(
            TaskOutcome.SUCCESS,
            result.task(":proof").getOutcome()
        );
    }
}
~~~

Đây là Java 17/JUnit test **có thể biên dịch** trong test project phía trên. Nó tạo fixture Gradle source **trước khi GradleRunner chạy**, rồi assert:

- Script `apply from` load đúng file.
- Task `proof` được register.
- Task execution in ra `script-ok`.
- Task có outcome `SUCCESS`.

TestKit tự chạy một Gradle build thực tế khác với quá trình chạy JUnit test. Nếu muốn kiểm script **`java-conventions.gradle` thật** của demo, thay vì tự tạo fixture script đơn giản, test phải **copy source script thật** vào temp fixture hoặc thiết lập absolute/relative location chính xác và assert Java compiler options, task `Test` framework và desired toolchain.

Khi chạy từ `script-logic-tests`:

~~~bash
./gradlew test
~~~

JUnit report của test project ở `build/reports/tests/test/index.html`. **Không khẳng định TestKit fixture này đã chạy demo core/app**: nó chỉ kiểm một applied script nhỏ đã được dựng trong test.

### 8.5. Giới hạn test của applied script plugin so với plugin project

| Vấn đề | Applied script | Precompiled/binary plugin |
| --- | --- | --- |
| Script source được đưa vào fixture | Cần path/copy file rõ ràng | Có plugin artifact/classpath và ID |
| Assertion trên apply bằng ID | Không có plugin ID độc lập | Có |
| Test unit với compiled plugin class | Không tách type project rõ tự nhiên | Có custom types/classes được compile độc lập |
| TestKit `withPluginClasspath()` | Không tự inject file `apply from` | Thường hỗ trợ qua `java-gradle-plugin` và plugin-under-test metadata |
| Dependency/plugin classpath | Cần setup fixture y như consumer | Plugin project khai dependency rõ |
| Kiểm nhiều Gradle versions | Có thể chỉ định GradleRunner distribution nhưng fixture phải tương thích | Cũng có thể, phù hợp CI matrix rõ |
| Test configuration cache | Phải kiểm task execution/configuration thực tế | Có thể thiết kế fixtures đặc thù và assertions |

TestKit không giúp “tự động biến script Groovy thành strongly typed plugin”. Nó chỉ chạy một build và quan sát behavior. Nếu logic có state, algorithm hoặc file transformations đủ phức tạp, tách custom types sang plugin project sẽ tạo cơ sở kiểm unit/functional tests tốt hơn.

### 8.6. Chạy tests hai lần và kiểm Configuration Cache

Một smoke test thực tế:

~~~bash
./gradlew :core:describeConventions --configuration-cache
./gradlew :core:describeConventions --configuration-cache
~~~

Lần đầu có thể lưu configuration cache; lần hai có thể tái sử dụng nếu không thay đổi inputs và mọi build logic/tasks tương thích. Không hứa **luôn** có cache hit: Gradle version, state, thay đổi build script, file inputs hoặc plugins có thể invalidate cache.

Script plugin `apply from` **không tự động làm Configuration Cache bị cấm**. Chính cách code trong script dùng Project/Task ở execution hoặc thực hiện side effects trong configuration mới có thể gây incompatibility. Do đó quan trọng hơn tên file là **tách configuration khỏi execution và khai inputs/outputs đúng**.

## 9. Những lỗi typing/classpath/test cần phân tích riêng

### 9.1. `Plugin with id ... not found`

Nguyên nhân thường là external plugin chưa được resolve đúng, hoặc script plugin dùng `apply plugin:` khi plugin implementation không có trên classpath. Cần phân biệt:

- `plugins { id 'external.id' version 'x.y.z' }` trong consumer main build file có cơ chế plugin resolution.
- `apply plugin: 'external.id'` không tự khai version.
- Precompiled plugin dùng external plugin cần dependency của plugin project và ID không kèm version trong precompiled script.
- Binary plugin dùng `pluginManager.apply` cùng plugin implementation classpath phù hợp.

Đừng thêm external plugin implementation vào `app.dependencies.implementation` vì mục đích đó sai classpath.

### 9.2. `Could not find method java()` hoặc `unknown property options`

Nếu shared script gọi `java { ... }` trước khi Java plugin được apply, extension có thể chưa tồn tại. Dùng consumer `plugins { id 'java-library' }` hoặc `pluginManager.withPlugin('java')`. Nếu dùng `options` ở context không phải `JavaCompile` task, xem lại `tasks.withType(JavaCompile).configureEach` và dấu ngoặc Groovy.

### 9.3. `Unresolved reference: java / implementation / test` trong Kotlin DSL applied script

Kotlin applied script **không có type-safe accessors** như main build script. Dùng normal Gradle APIs, ví dụ `extensions.configure(JavaPluginExtension::class.java)`, `tasks.withType(JavaCompile::class.java)`, hoặc dependency configuration theo string name. Đừng copy snippet từ precompiled plugin sang applied Kotlin script mà không thay DSL.

### 9.4. `MissingPropertyException` do dynamic Groovy

Sai tên property Groovy có thể fail khi callback được evaluate. Test tối thiểu một fixture có đúng plugin/model và kiểm property đang được cấu hình. Nếu callback được gọi chỉ ở một module nhất định, phải test module type đó; `./gradlew help` ở root chưa chắc chạm code path lỗi.

### 9.5. `NoClassDefFoundError` hoặc `ClassNotFoundException`

Đầu tiên xác định stack trace ở **build configuration** hay **Java execution**:

- Nếu build script không import được class, xem buildscript/plugin classpath.
- Nếu Java source không import được class, xem `compileClasspath`.
- Nếu Java runtime thiếu class, xem `runtimeClasspath`/`testRuntimeClasspath`.
- Nếu class có ở một phiên bản plugin nhưng biến mất sau upgrade, xem Gradle/plugin compatibility và dependency conflicts.

Không chữa tất cả bằng `--refresh-dependencies` hoặc xóa `~/.gradle`; cache không giải quyết sai dependency scope.

### 9.6. `Task with name 'test' not found`

Một script áp vào project chưa có Java plugin nhưng gọi `tasks.named('test')` ngay sẽ fail. Có thể:

- Consumer áp plugin Java trước applied script.
- Dùng `pluginManager.withPlugin('java')`.
- Dùng `tasks.withType(Test).configureEach` để cấu hình Test tasks khi được tạo.
- Kiểm plugin type; không phải mọi module (docs/root aggregator) đều có test task.

### 9.7. Task được register nhưng chạy lại không đúng

Nếu task action tự đọc file hoặc environment mà không khai input, Gradle không có đủ dữ liệu để làm up-to-date/cache đúng. Nếu task đọc Project mutable state trong execution, Configuration Cache cũng có thể báo lỗi. Chuyển sang typed task `Property<T>`, `RegularFileProperty`, `@Input`/`@OutputFile` và Provider wiring.

### 9.8. CI pass dù shared logic bị xóa

Nếu test suite chỉ kiểm business Java tests, một chính sách compiler encoding/Checkstyle/feature gate có thể biến mất mà tests không fail. Bổ sung **build logic functional tests** hoặc assertions rõ về task types, plugin application, report config và artifact metadata. Một marker task như `describeConventions` kiểm “đã apply” nhưng chưa đủ để chứng minh **mọi quy ước** chính xác.

## 10. Khi nào nên chuyển sang precompiled convention plugin?

Các tín hiệu nên migration:

1. Shared script được apply vào nhiều modules và có nhiều plugin/version dependencies.
2. Build script chứa class/type imports của external plugins.
3. Có custom extensions và tasks phải được consumers cấu hình có type.
4. Các thay đổi shared logic cần review và automated regression tests.
5. IDE khó refactor/đi tới định nghĩa, dynamic DSL lỗi muộn.
6. Config cache/isolated projects hoặc performance tuning trở nên quan trọng.
7. Muốn policy build logic có semver và khả năng tái sử dụng giữa builds.
8. Lỗi build logic gây ảnh hưởng nhiều repos và cần kiểm thử trước phân phối.

### 10.1. Chuyển từ file `gradle/java-conventions.gradle` sang included build `build-logic`

Cấu trúc minh họa:

~~~text
project/
├── settings.gradle
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       └── company.java-conventions.gradle
├── core/build.gradle
└── app/build.gradle
~~~

Root `settings.gradle`:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'script-plugin-lab'
include 'core', 'app'
~~~

`build-logic/settings.gradle`:

~~~groovy
rootProject.name = 'build-logic'
~~~

`build-logic/build.gradle`:

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

`build-logic/src/main/groovy/company.java-conventions.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Consumer `core/build.gradle` sau migration:

~~~groovy
plugins {
    id 'java-library'
    id 'company.java-conventions'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}
~~~

Consumer `app/build.gradle` tương tự, thay application plugin và giữ `implementation project(':core')`/`mainClass`. **Xóa `apply from` cũ** khi precompiled plugin đã được áp bằng ID, tránh cấu hình trùng.

Những đoạn trên là **bộ khung migration**; với build-logic có external plugin dependencies hoặc source classes riêng, cần thêm `dependencies`/plugin metadata theo tài liệu Gradle. Không paste song song hai giải pháp vào một project đang chạy nếu chưa kiểm tính tương thích.

### 10.2. Khác biệt về Groovy precompiled script plugin

Precompiled Groovy script plugin trong `src/main/groovy` có ID dựa trên tên file (ví dụ `company.java-conventions`). Theo hướng dẫn Gradle, **Groovy precompiled script plugins không dùng package declarations** như Kotlin counterpart; không thêm `package com.example` đầu file rồi hy vọng tạo plugin ID theo cách Kotlin.

Đối với external plugins, version được đưa vào dependencies của `build-logic`, không đặt `version 'x.y.z'` trong `plugins { }` của precompiled script. Cũng không dùng `apply false` ở precompiled plugin script; policy version đến từ plugin project classpath.

### 10.3. Khi nào binary plugin tốt hơn?

Nếu chỉ cấu hình Java 17/JUnit, precompiled convention plugin thường đủ. Nếu bạn xây:

- Custom Gradle task types với annotations/Providers.
- DSL extension `companyQuality { strictMode.set(true) }`.
- Verification rules, services, caching và lifecycle phức tạp.
- Plugin cần publish thành JAR cho nhiều builds/teams.
- Các unit tests ở cấp Java/Kotlin class và TestKit cross-version tests.

thì binary plugin phù hợp hơn. Nó được viết thành một class implements `Plugin<Project>`, build bằng Gradle plugin development plugin và đăng ký ID. Consumer vẫn có thể apply bằng `plugins { id '...' }` nhưng implementation được compile, test và publish như một artifact đúng nghĩa.

### 10.4. Một lộ trình migration an toàn

1. **Đóng băng behavior**: lấy danh sách modules dùng `apply from`, plugins, tasks và expected compiler/test/report config.
2. **Thêm smoke/functional tests** cho script plugin hiện tại.
3. **Tạo included build `build-logic`** với precompiled script plugin.
4. **Chuyển cấu hình bất biến trước**, như toolchain/encoding/test framework, không chuyển custom task phức tạp ngay.
5. **Áp plugin mới trong một module**, bỏ `apply from` ở module đó, chạy `:module:build` và test configuration cache.
6. **So sánh task graph và outputs** giữa trước/sau, không chỉ build success.
7. **Mở rộng sang các modules khác** sau khi CI pass.
8. **Tách custom typed tasks** sang binary classes nếu cần; bổ sung TestKit tests.
9. **Gỡ file script cũ**, không để hai nguồn sự thật.
10. **Document ownership/version policy** của build-logic để sau này nâng Gradle/plugins an toàn.

Không migration chỉ vì “có file .gradle”; mức độ bảo trì thực tế, classpath complexity và nhu cầu test mới là tiêu chí lựa chọn.

## 11. Anti-pattern cần tránh trong shared script

| Anti-pattern | Vấn đề | Hướng khắc phục |
| --- | --- | --- |
| `plugins { }` trong `apply from` file | Không được hỗ trợ cho script plugin | Consumer `plugins { }` hoặc precompiled plugin |
| Dùng `tasks.create`/`getByName` hàng loạt | Eager task realization | `tasks.register`, `named`, `configureEach` |
| Dùng `allprojects/subprojects` đổi state chéo | Coupling cross-project, khó isolated projects | Convention plugin per module |
| External plugin class import không có trên script classpath | Compile-time class not found | Build-logic dependencies/plugin classpath rõ |
| Trộn `implementation` của app với buildscript classpath | Sai scope | Tách application vs build logic deps |
| `afterEvaluate` để chữa plugin ordering | Khó dự đoán và phụ thuộc timing | `pluginManager.withPlugin`, Providers |
| Gọi HTTP/file write ở top-level script | Side effects trong configuration | Typed tasks có inputs/outputs |
| Tạo file bằng `doLast` mà không khai output | Up-to-date/cache sai | `@OutputFile`/`RegularFileProperty` |
| Đọc `project` trong task action khi dùng Configuration Cache | Có thể không tương thích cache | Capture task inputs qua Providers |
| Copy script nội bộ sang nhiều repos nhưng không pin version | Drift và thiếu review | Plugin artifact/convention versioned workflow |
| Unit tests chỉ kiểm business code | Không kiểm build policy | GradleRunner functional fixtures |
| Không có regression test cho migration | Behavior đổi âm thầm | So task graph, compiler options, outputs |
| Plugin áp vào module chưa có Java | Không tìm `java` extension/task | Consumer apply plugin, `withPlugin` guard |
| Cố tạo extension typed bằng `ext.someFlag` tùy ý | Khó validate/IDE refactor | Extension class dùng `Property<T>` |
| Run `clean build` sau mọi thay đổi | Mất incremental benefits | Sửa input/output tracking |

## 12. Cách chẩn đoán lỗi theo tầng

~~~text
Lệnh chạy sai hay module nào fail?
             |
             v
Script plugin có được apply vào đúng project/path?
             |
             v
Build fail ở configuration hay task execution?
             |
    +--------+--------+
    |                 |
 configuration     execution
    |                 |
    v                 v
plugins block?    Missing task input/output?
plugin present?   Java runtime classpath?
script classpath? configuration cache violation?
    |                 |
    +--------+--------+
             |
             v
Đang lỗi Gradle build logic type/classpath hay Java app?
             |
             v
Minimal Gradle fixture + --stacktrace/--info
             |
             v
Sửa API/plugin scope, thêm functional test hồi quy
~~~

Lệnh hữu ích:

~~~bash
./gradlew :core:tasks --all
./gradlew :app:tasks --all
./gradlew :app:test --dry-run
./gradlew :app:test --stacktrace
./gradlew :app:test --info
./gradlew :core:describeConventions --configuration-cache
~~~

Để biết lỗi type nào, đọc **phần đầu tiên của stacktrace nơi script/class cụ thể bị lỗi**, không chỉ dòng cuối “BUILD FAILED”. Nếu exception liên quan build script compilation, kiểm Groovy/Kotlin DSL và plugin classpath; nếu liên quan `JavaCompile`, kiểm Java code/compileClasspath/toolchain; nếu liên quan test runtime, kiểm JUnit launcher/engine và `testRuntimeClasspath`.

## 13. Bài tập thực hành có đáp án

### Bài 1 — Nhận diện script plugin

Một file `gradle/java-conventions.gradle` được dùng qua `apply from:`. Nó có plugin ID tự động `java-conventions` không? **Không.** ID tự động có trong precompiled script plugin/binary plugin được đăng ký đúng, không phải bất cứ file Groovy nào.

### Bài 2 — `plugins { }` đặt ở đâu?

Nếu muốn core áp Java Library plugin, đặt `plugins { id 'java-library' }` trong `core/build.gradle` hoặc chuyển shared logic thành precompiled plugin. Không đặt `plugins { }` trực tiếp trong script được `apply from`.

### Bài 3 — Lỗi type Groovy

Người học viết `options.encodng = 'UTF-8'`. Vì sao có thể lỗi muộn? Vì Groovy DSL dynamic property resolution, task callback có thể chỉ được thực hiện khi task/type được cấu hình. Sửa thành `options.encoding` và bổ sung fixture test.

### Bài 4 — Kotlin applied script có `java { }` accessor không?

Không tự có type-safe model accessors. Khi cần, dùng `extensions.configure(JavaPluginExtension::class.java)`, typed task APIs và đảm bảo Java plugin đã apply trước. Đừng sao chép precompiled Kotlin script code mà không điều chỉnh.

### Bài 5 — Tách application dependency và build logic dependency

`app.dependencies.implementation 'org.apache.commons:commons-lang3:3.17.0'` giúp Java app import Commons Lang. Nó có đưa Commons Lang lên Groovy script plugin classpath không? **Không, không mặc định.** Build logic cần dependency ở classpath buildscript/plugin build phù hợp.

### Bài 6 — Script được áp vào bao nhiêu module?

Nếu cả core và app gọi `apply from: "$rootDir/gradle/java-conventions.gradle"`, sẽ có `:core:describeConventions` và `:app:describeConventions`. Không có một task chung duy nhất `:describeConventions` ở root trừ khi root cũng đăng ký.

### Bài 7 — Shared script bị bỏ khỏi app

Xóa `apply from` trong `app/build.gradle`, giữ core. `:app:describeConventions` không còn tồn tại, còn `:core:describeConventions` vẫn có. Đây là cách nhanh để chứng minh scope per project.

### Bài 8 — Java test pass có chứng minh quality policy không?

Không chắc. Java test kiểm hành vi Java code, có thể không assert Java compiler encoding, reporting rules hoặc registered tasks. Dùng functional tests của build logic để kiểm policy.

### Bài 9 — TestKit có cần `withPluginClasspath()` cho `apply from` không?

Không nhất thiết. Nếu fixture tự tạo file `gradle/conventions.gradle` và build script `apply from` file đó, TestKit load script file qua Gradle runtime của fixture. `withPluginClasspath()` chuyên dùng để inject compiled plugin under test vào build trong trường hợp plugin có ID/classpath từ plugin project.

### Bài 10 — Có nên đặt `doLast { file("$buildDir/report.txt").text = ... }` trong shared script?

Không nếu mong đợi caching/up-to-date/Configuration Cache mạnh. Tạo typed task với `@Input`, `@OutputFile` và Provider APIs, rồi kiểm bằng TestKit. Nếu chỉ là tiện ích one-off, ít nhất phải khai outputs và tránh đọc Project mutable state trong action.

### Bài 11 — Khi nào nên dùng convention plugin?

Khi cùng script được dùng rộng rãi, có plugin classpath deps, custom DSL/task types và cần functional tests/IDE refactoring. Precompiled script plugin phù hợp quy ước nội bộ; binary plugin hợp logic phức tạp/publishing.

### Bài 12 — Chạy hai lần với Configuration Cache

Chạy `./gradlew :core:describeConventions --configuration-cache` hai lần. Nếu lần sau cache hit, điều đó cho thấy configuration đã được tái sử dụng phù hợp; task action vẫn được chạy khi task được chọn, vì `describeConventions` không có declared outputs/up-to-date contract. Đừng in marker duy nhất trong configuration rồi kỳ vọng luôn thấy ở mọi lần gọi.

### Bài 13 — Plugin ordering

Shared script configure `java` extension nhưng một module không apply Java. Dùng `pluginManager.withPlugin('java')` hoặc bắt buộc consumer apply `java`/`java-library`/`application`. Không dùng `afterEvaluate` như giải pháp mặc định.

### Bài 14 — Quy trình migration

Chuyển `gradle/java-conventions.gradle` vào `build-logic/src/main/groovy/company.java-conventions.gradle`, cấu hình `groovy-gradle-plugin` và `pluginManagement.includeBuild`, rồi apply `id 'company.java-conventions'`. Cần **bỏ `apply from` cũ**, kiểm tasks/tests/output/Configuration Cache và thực hiện test hồi quy.

## 14. Checklist cuối bài

1. Đã hiểu `apply from:` nạp script vào target project chứ không tự tạo plugin ID?
2. Đã phân biệt script plugin, precompiled script plugin và binary plugin?
3. Có biết `plugins { }` **không được dùng trong applied script**?
4. Consumer có apply đúng plugins trước khi script cần model elements?
5. Script dùng `pluginManager.withPlugin` khi cần cấu hình theo plugin timing?
6. Đường dẫn root script có ổn định giữa modules, CI và developers?
7. Đã phân biệt **Gradle buildscript/plugin classpath** với Java `implementation`/`testImplementation` classpaths?
8. Với external Gradle plugin type, đã khai dependency đúng classpath và pin version?
9. Có tránh suy Kotlin applied script có type-safe model accessors như main/precompiled scripts?
10. Với Groovy dynamic DSL, có functional fixture test bắt lỗi property/task wiring?
11. Có dùng `tasks.register`, `named` và `configureEach` thay vì eager APIs khi phù hợp?
12. Không tạo file/network calls trong configuration nếu nên thuộc execution?
13. Custom task có typed `Property<T>`, `@Input`, `@OutputFile`, task actions rõ ràng?
14. Có test Java product code **và** functional test shared build logic?
15. Đã hiểu TestKit fixture `apply from` khác plugin-under-test ID/classpath?
16. Có phân biệt Configuration Cache với up-to-date checking và Build Cache?
17. Khi script lớn, có lộ trình chuyển sang precompiled/binary plugin?
18. Khi migration, có gỡ source cũ và kiểm hành vi cùng task graph trước/sau?

## 15. Tài liệu Gradle chính thức

- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/plugins.html): các loại plugin, ví dụ `apply from` và vị trí của applied script trong hệ sinh thái.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin application, `plugins { }` DSL và giới hạn trong script plugins.
- [Gradle — Implementation Options for Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): so sánh script, precompiled và binary plugin, khuyến nghị bảo trì.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): plugin ID, build-logic classpath, external plugin versions, Groovy/Kotlin conventions.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): `buildSrc`, included build và convention plugins.
- [Gradle — Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html): type-safe model accessors và ngoại lệ đối với applied scripts.
- [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner fixtures, outputs/outcomes, plugin classpath.
- [Gradle — Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): unit/functional testing và plugin development lifecycle.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `tasks.named`, `configureEach`.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Property<T>`/`Provider<T>` và wiring.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration-time side effects, execution-time restrictions.
- [Gradle — Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): typed task classes, inputs/outputs và task actions.
