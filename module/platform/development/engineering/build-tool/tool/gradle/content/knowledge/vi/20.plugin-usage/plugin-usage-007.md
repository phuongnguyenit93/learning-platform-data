# Tương tác giữa plugin và thời điểm dùng `withPlugin` trong Gradle

## 1. Vấn đề: plugin có thể được áp dụng trước hoặc sau build logic của bạn

Trong Gradle, plugin là đơn vị mở rộng build: Java plugin tạo `java` extension và các task như `compileJava`/`test`; Application plugin tạo `application` extension và `run`; Maven Publish plugin tạo publishing model. Một đoạn build logic hoặc convention plugin muốn cấu hình chúng sẽ phụ thuộc vào **thời điểm những thành phần đó xuất hiện**.

Đây là mã dễ thất bại nếu chạy khi Java plugin chưa được áp dụng:

~~~groovy
tasks.named('compileJava') {
    options.encoding = 'UTF-8'
}
~~~

`tasks.named` chỉ tìm được task **đã đăng ký**. Nếu Java plugin chưa đăng ký `compileJava`, lookup có thể báo lỗi. Khi xây dựng convention plugin, bạn thường không kiểm soát việc người dùng đặt Java plugin trước hay sau plugin của mình.

Đó là lý do Gradle có API:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('compileJava') {
        options.encoding = 'UTF-8'
    }
}
~~~

**`withPlugin` nghĩa là: “Khi plugin có ID này đã được áp dụng, chạy phần tích hợp của tôi.”** Nó không có nghĩa “tự apply plugin”, “đợi mọi project cấu hình xong” hay “chạy code mỗi khi task thực thi”.

Sau bài này, bạn sẽ:
- Phân biệt plugin resolution, plugin application, project configuration và task execution.
- Dự đoán chính xác lúc callback `withPlugin` chạy trong ba tình huống: plugin đã applied, applied sau và không bao giờ applied.
- Phân biệt `pluginManager.apply`, `withPlugin`, `hasPlugin`, `findPlugin` và `plugins.withId`.
- Dùng `tasks.named`/`tasks.withType(...).configureEach` để cấu hình task do plugin tạo mà vẫn lazy.
- Tương tác nhiều plugin với nhau theo cách ít phụ thuộc plugin order.
- Thử một ví dụ timing có stdout xác định, một Java 17 Application chạy được và một binary plugin dùng `buildSrc`.
- Tránh lỗi `afterEvaluate`, configuration cache, callback scope và plugin API classpath.

Ví dụ dùng **Gradle Groovy DSL** (`build.gradle`/`settings.gradle`), Gradle Wrapper và JDK 17+ ở phần Java. Linux/macOS: `./gradlew`; Windows PowerShell: `.\gradlew.bat`.

## 2. Hiểu đúng các giai đoạn trong build

Một Gradle project có thể trải qua:

~~~text
plugins {} / pluginManager.apply(...)
          |
          v
Resolve plugin (nếu là plugin ngoài)
          |
          v
Áp dụng plugin vào target Project
  - tạo extensions
  - đăng ký configurations/tasks
  - có thể áp dụng plugin khác
          |
          v
Plugin applied
          |
          +----> withPlugin(id) callbacks đang chờ
          |
          v
Các build script và plugin khác vẫn cấu hình project
          |
          v
Task graph -> task execution
~~~

**Điểm then chốt:** `withPlugin` chạy **sau khi plugin được áp dụng**, nhưng có thể **trước khi người dùng khai cấu hình cuối cùng** ở phần sau của script. Callback này thuộc **configuration phase**, không phải một task action.

### 2.1. `plugins {}` khác với `pluginManager.apply` về vị trí

Project script thường có:

~~~groovy
plugins {
    id 'java'
}

pluginManager.withPlugin('java') {
    println 'Java plugin is present'
}
~~~

Gradle xử lý khối `plugins {}` sớm, trước phần body của script. Vì vậy khi body đến `withPlugin`, Java plugin đã applied và callback chạy **ngay**.

Để minh họa callback được đăng ký trước khi plugin xuất hiện, có thể dùng:

~~~groovy
pluginManager.withPlugin('java') {
    println 'Java now applied'
}

pluginManager.apply('java')
~~~

Dùng `pluginManager.apply('java')` trong build script là hợp lệ cho core plugin. Với external plugin, nó không tự chọn version hoặc tải plugin khi chưa có plugin classpath/resolution phù hợp.

### 2.2. Không nhầm “plugin applied” với “task chạy”

~~~groovy
pluginManager.withPlugin('java') {
    println 'config callback'
}

tasks.register('sayHello') {
    doLast {
        println 'task action'
    }
}
~~~

- `config callback` có thể xuất hiện khi chạy `./gradlew help`, miễn Java plugin được áp dụng.
- `task action` chỉ xuất hiện khi `sayHello` được thực thi.
- Nếu configuration cache được reuse, script/callback có thể không chạy lại, nhưng task action vẫn có thể chạy nếu task được yêu cầu và không bị skip.

Đừng ghi artifact, gọi mạng hoặc thay đổi cơ sở dữ liệu ngay trong callback `withPlugin` chỉ vì bạn muốn “làm việc gì đó sau khi Java có mặt”. Những side effects bắt buộc mỗi build nên thuộc task có hợp đồng input/output hoặc công cụ lifecycle chuyên dụng.

## 3. Ngữ nghĩa chính xác của `PluginManager.withPlugin`

API Java chính thức:

~~~java
void withPlugin(String id, Action<? super AppliedPlugin> action);
~~~

Groovy DSL:

~~~groovy
pluginManager.withPlugin('java') { appliedPlugin ->
    println appliedPlugin.id
}
~~~

`AppliedPlugin` chứa thông tin về plugin đã được áp dụng, như plugin ID. Nó không phải `JavaPluginExtension` hay instance của JavaPlugin.

Nếu không cần tham số, dùng:

~~~groovy
pluginManager.withPlugin('java') {
    // Có thể cấu hình Java extension/task tại đây.
}
~~~

### 3.1. Ba tình huống

| Khi đăng ký `withPlugin` | Gradle thực hiện gì? |
| --- | --- |
| Plugin ID đã được applied vào chính project | **Gọi callback ngay lập tức** |
| Plugin chưa applied nhưng được áp dụng sau đó | **Gọi callback ngay sau khi plugin applied** |
| Plugin không được áp dụng vào project | **Không gọi callback** |

Không cần tự viết kiểm tra `hasPlugin` rồi cố đăng ký một event listener khác cho trường hợp plugin xuất hiện sau: `withPlugin` đã xử lý cả hai thời điểm.

### 3.2. Callback không áp dụng plugin

Đoạn sau không tạo Java tasks:

~~~groovy
pluginManager.withPlugin('java') {
    println 'Only if Java is applied'
}
~~~

Muốn Java là **bắt buộc**:

~~~groovy
pluginManager.apply('java')
~~~

Hoặc trong project script:

~~~groovy
plugins {
    id 'java'
}
~~~

Một custom plugin chỉ **tích hợp tùy chọn** với Java nên dùng `withPlugin`; một plugin **yêu cầu Java để hoạt động** có thể chủ động gọi `pluginManager.apply('java')` trong `Plugin.apply`.

### 3.3. Callback được gọi bao nhiêu lần?

Một action đăng ký cho plugin ID được gọi khi plugin đó applied. Gradle không apply lại cùng một plugin ID nhiều lần để tạo nhiều instance chỉ vì có hai dòng `apply`. Tuy nhiên, nếu **bạn đăng ký nhiều callbacks khác nhau**, chúng đều có thể được chạy. Đừng đăng ký cùng một task name từ nhiều callbacks rồi mong chúng tự merge.

### 3.4. Core plugin IDs và external plugin IDs

- Core: `java`, `application`, `java-library`, `maven-publish`, `war`...
- Bên ngoài: ID đầy đủ do publisher cung cấp, ví dụ `com.example.conventions`.

`withPlugin` dựa trên **plugin ID**, không dựa trên tên JAR, Maven coordinate, source set hoặc tên của Java implementation class. Khi plugin dùng ID sai, callback không chạy dù một class gần giống có mặt trên classpath.

## 4. Phân biệt `withPlugin`, `withId`, `hasPlugin`, `apply`

| API | Tác dụng | Phản ứng với việc apply sau? | Tự apply plugin? |
| --- | --- | --- | --- |
| `pluginManager.withPlugin('java') { ... }` | Callback khi plugin ID applied | Có | Không |
| `plugins.withId('java') { plugin -> ... }` | Callback theo ID trong PluginContainer | Có | Không |
| `pluginManager.hasPlugin('java')` | Boolean trạng thái **hiện tại** | Không | Không |
| `pluginManager.findPlugin('java')` | `AppliedPlugin` hiện tại hoặc null | Không | Không |
| `pluginManager.apply('java')` | Đảm bảo plugin được áp dụng | Không phải callback | Có |
| `plugins.apply('java')` | Áp plugin qua PluginContainer | Không phải callback | Có |
| `plugins.configureEach { plugin -> ... }` | Quan sát/configure plugin instances | Theo collection | Không |
| `afterEvaluate { ... }` | Callback sau khi project evaluation kết thúc | Không trực tiếp chờ plugin | Không |

### 4.1. `plugins.withId` có tham số khác

~~~groovy
pluginManager.withPlugin('java') { applied ->
    println 'Applied ID=' + applied.id
}

plugins.withId('java') { pluginInstance ->
    println 'Instance=' + pluginInstance.class.simpleName
}
~~~

`PluginManager.withPlugin` nhận **`AppliedPlugin`**, còn `PluginContainer.withId` nhận **plugin instance**. Cả hai đều hỗ trợ plugin đã applied lẫn applied trong tương lai. Đối với tích hợp theo ID, Gradle khuyến nghị `pluginManager.withPlugin`; nếu cần phân loại bằng **plugin class**, có thể dùng `plugins.configureEach` kết hợp `instanceof` khi phù hợp.

### 4.2. `hasPlugin` chỉ là snapshot

Ví dụ kém tin cậy nếu custom plugin được áp dụng trước Java:

~~~groovy
if (pluginManager.hasPlugin('java')) {
    tasks.named('compileJava') {
        options.encoding = 'UTF-8'
    }
}
~~~

Tại thời điểm này Java chưa applied, điều kiện false. Khi Java được apply sau, **không có callback nào được đăng ký**, nên tích hợp mất hiệu lực.

Thay bằng:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('compileJava') {
        options.encoding = 'UTF-8'
    }
}
~~~

`hasPlugin` vẫn hữu dụng khi bạn thật sự cần câu trả lời **bây giờ**, ví dụ một thông báo kiểm tra. Nó không thay được listener trong tình huống plugin order không cố định.

### 4.3. Vì sao không dùng `afterEvaluate` thay thế?

~~~groovy
afterEvaluate {
    if (pluginManager.hasPlugin('java')) {
        tasks.named('compileJava') {
            options.encoding = 'UTF-8'
        }
    }
}
~~~

`afterEvaluate` quan sát **project evaluation**, không trực tiếp ràng buộc vào việc plugin đã applied. Nếu nhiều plugins/callbacks cùng cấu hình project, thứ tự các `afterEvaluate` có thể dễ gây logic khó hiểu; việc kết hợp với lazy task registration cũng dễ dẫn đến cấu hình quá muộn. Gradle khuyến nghị:
- `withPlugin` cho **plugin application**.
- `Provider`/`Property` và `convention(...)` cho **giá trị cấu hình lazy**.
- `tasks.named`/`configureEach` cho **task registration/configuration avoidance**.

Không có lý do để dùng `afterEvaluate` chỉ vì “plugin có thể xuất hiện sau”.

## 5. Demo A chạy được: thứ tự callback chính xác

Bài này không cần source code hoặc Maven Central. Tạo một Gradle project với:

**`settings.gradle`:**

~~~groovy
rootProject.name = 'hook-timing-lab'
~~~

**`build.gradle` — toàn bộ:**

~~~groovy
println '01 register early hook'

pluginManager.withPlugin('java') {
    println '03 Java early hook fired'
}

println '02 before apply'
pluginManager.apply('java')
println '04 after apply'

pluginManager.withPlugin('java') {
    println '05 Java late hook fired immediately'
}

pluginManager.withPlugin('war') {
    println 'This should not print without war'
}

tasks.register('showOrder') {
    group = 'help'
    doLast {
        println '06 task action'
    }
}
~~~

Chạy:

~~~bash
./gradlew showOrder --quiet --no-configuration-cache
~~~

**Stdout của các `println` được viết trong script/task:**

~~~text
01 register early hook
02 before apply
03 Java early hook fired
04 after apply
05 Java late hook fired immediately
06 task action
~~~

Giải thích:
1. Hook Java được đăng ký, nhưng Java chưa applied nên **chưa chạy**.
2. Dòng `02` in trước `pluginManager.apply('java')`.
3. Gradle áp Java plugin, sau đó gọi callback Java đang chờ.
4. `apply` trả về, dòng `04` in.
5. Callback Java đăng ký sau lúc Java applied, nên chạy **ngay** và in `05`.
6. `showOrder` được Gradle thực thi sau cấu hình, in `06`.
7. War plugin không được áp dụng, nên callback `war` không chạy.

Chúng ta dùng `--no-configuration-cache` để **thấy lại configuration-time prints** mỗi lần chạy. Nếu configuration cache được reuse, Gradle có thể không đánh giá lại script, các dòng từ configuration không xuất hiện, dù task vẫn chạy đúng.

### 5.1. Nếu Java được applied qua `plugins {}` trước callback

Thay `build.gradle` bằng:

~~~groovy
plugins {
    id 'java'
}

println 'before callback registration'

pluginManager.withPlugin('java') {
    println 'Java already applied -> immediate'
}

println 'after callback registration'
~~~

Chạy:

~~~bash
./gradlew help --quiet --no-configuration-cache
~~~

**Thứ tự các dòng do build script in:**

~~~text
before callback registration
Java already applied -> immediate
after callback registration
~~~

Task `help` có thể in nội dung trợ giúp riêng tùy Gradle version; ba dòng trên là những dấu mốc do script tạo ra, không phải toàn bộ stdout của Gradle.

### 5.2. Nếu không bao giờ apply plugin

~~~groovy
pluginManager.withPlugin('java') {
    println 'Java callback'
}

tasks.register('plain') {
    doLast { println 'Plain task works' }
}
~~~

Chạy `./gradlew plain --quiet`, output do task in:

~~~text
Plain task works
~~~

Không có `Java callback`. `withPlugin` không tự khiến Java được apply. Đây là hành vi đúng của một **optional integration**.

## 6. Kết hợp với task configuration avoidance

Bản thân `withPlugin` chỉ giúp biết **khi plugin sẵn sàng**. Để cấu hình task an toàn và hiệu quả, bạn còn cần lazy task APIs:

| API | Ý nghĩa |
| --- | --- |
| `tasks.register('name', Type)` | Đăng ký task và trả `TaskProvider` mà chưa cần tạo instance ngay |
| `tasks.named('name', Type) { ... }` | Cấu hình task đã được đăng ký theo tên, lazy |
| `tasks.withType(Type).configureEach { ... }` | Cấu hình mọi task có type đó khi chúng được realize, gồm task được đăng ký sau |
| `tasks.getByName('name')` | Lookup/realize task ngay; tránh nếu không cần |
| `tasks.create('name')` | Eager tạo task; ưu tiên `register` |
| `tasks.withType(Type).all { ... }` | Có thể eager configure task; ưu tiên `configureEach` |

### 6.1. Một task cụ thể sau plugin application

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('compileJava', JavaCompile) {
        options.encoding = 'UTF-8'
    }
}
~~~

`compileJava` được Java plugin đăng ký. Hook bảo đảm Java đã applied trước khi tìm tên task. `tasks.named` vẫn không cần ép task thực thi ngay. Lưu ý `JavaCompile` là class thuộc Gradle API, có thể import `org.gradle.api.tasks.compile.JavaCompile` khi viết build logic tách file.

### 6.2. Mọi Java compile tasks, kể cả được đăng ký sau

~~~groovy
pluginManager.withPlugin('java') {
    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

Nếu sau đó một plugin tạo thêm task `compileIntegrationJava` hoặc `compileTestJava`, callback `configureEach` vẫn áp dụng cho task type `JavaCompile` trong cùng project khi task được cấu hình.

**Hai lớp callback khác nhau:**
- `withPlugin` chờ **plugin application**.
- `configureEach` chờ **task realization/configuration**.

Một plugin đã applied **không có nghĩa** tất cả tasks của nó đã được tạo/realized. Do đó không cần gọi `tasks.getByName(...)` để ép mọi task xuất hiện cho bằng được.

### 6.3. Cảnh báo về cấu hình task khác trong task configuration closure

Không viết logic dạng:

~~~groovy
tasks.register('alpha') {
    tasks.named('beta') {
        // cố tình cấu hình task khác từ closure cấu hình alpha
    }
}
~~~

Đó là mẫu phụ thuộc thời điểm realize `alpha`. Khi build chỉ cần `beta`, code cấu hình `alpha` có thể chưa chạy, nên hành vi trở nên không ổn định. Đăng ký các task providers và quan hệ task ở cấp cấu hình plugin/script thích hợp, không dựa trên closure của một task khác để tạo side effects.

## 7. Demo B chạy được: Java 17 Application và hai plugin hooks

Ví dụ này có **Java application chạy thật** mà không dùng thư viện hoặc plugin bên thứ ba. Nó cho thấy Application plugin áp Java plugin gián tiếp và `withPlugin` vẫn hoạt động khi hook đăng ký trước lúc apply.

### 7.1. Cấu trúc

~~~text
plugin-interaction-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/Main.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Máy cần Gradle Wrapper tương thích với JDK 17 và có Java 17 toolchain. Nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` một lần rồi commit các file Wrapper vào repository.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'plugin-interaction-lab'
~~~

### 7.2. `build.gradle` — toàn bộ

~~~groovy
import org.gradle.api.plugins.JavaApplication
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion

pluginManager.withPlugin('java') {
    extensions.configure(JavaPluginExtension) { javaExt ->
        javaExt.toolchain.languageVersion.convention(
            JavaLanguageVersion.of(17)
        )
    }

    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }

    tasks.withType(Test).configureEach {
        systemProperty 'lab.profile', 'demo'
    }
}

pluginManager.withPlugin('application') {
    extensions.configure(JavaApplication) { appExt ->
        appExt.mainClass.set('demo.Main')
    }
}

// Áp Application sau khi đã đăng ký hai callbacks.
// Application cũng áp Java và Distribution plugins.
pluginManager.apply('application')

pluginManager.withPlugin('java') {
    tasks.named('compileJava', JavaCompile) {
        options.compilerArgs.add('-Xlint:deprecation')
    }
}
~~~

**Mốc thời gian:**
1. Callback `java` được đăng ký, chưa chạy.
2. Callback `application` được đăng ký, chưa chạy.
3. `pluginManager.apply('application')` áp dụng Application plugin, đồng thời Java plugin được áp dụng theo cơ chế của Application.
4. Hook `java` chạy khi Java đã applied: có thể cấu hình `JavaPluginExtension`, và `JavaCompile`/`Test` qua `configureEach`.
5. Hook `application` chạy khi Application đã applied: có thể đặt `mainClass` trên `JavaApplication` extension.
6. Hook Java đăng ký sau cùng chạy ngay do Java đã có, cấu hình `compileJava` qua `tasks.named`.
7. Java source chỉ compile khi task cần thiết được thực thi; `withPlugin` không tự chạy `compileJava` hay `run`.

`JavaPluginExtension` là API của Java plugin, `JavaApplication` là extension do Application plugin thêm; chúng không phải cùng một object. `convention(JavaLanguageVersion.of(17))` đặt default, nên người dùng vẫn có thể cấu hình `java.toolchain.languageVersion.set(...)` sau đó.

### 7.3. `src/main/java/demo/Main.java`

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("withPlugin OK: Java + Application");
    }
}
~~~

Tên package, folder và public class khớp nhau. Java code không cần external dependency.

### 7.4. Chạy

~~~bash
./gradlew tasks --all
./gradlew run --quiet
~~~

**Stdout chính xác từ `Main.main` (không tính log môi trường):**

~~~text
withPlugin OK: Java + Application
~~~

Application plugin tạo task `run` kiểu `JavaExec`. `tasks.withType(Test).configureEach` chỉ thay system property của `Test` task; nó **không** thay JVM properties của `run`. Nếu muốn cấu hình `run`, có thể làm trong hook Application:

~~~groovy
pluginManager.withPlugin('application') {
    tasks.named('run', JavaExec) {
        systemProperty 'lab.profile', 'run'
    }
}
~~~

Đây là **snippet tùy chọn**, dùng với project đã có Application plugin. `JavaExec` phải được import hoặc được nhận qua mặc định Gradle DSL. Trong main demo, app không đọc system property nên stdout không thay đổi.

## 8. Demo C: viết custom plugin bằng Java trong `buildSrc`

Mục tiêu là tạo một plugin có **optional integration** với Java: project apply custom plugin trước hay sau Application/Java plugin đều nhận cùng cấu hình. Đây là một trường hợp thực tế của `withPlugin`.

### 8.1. Cấu trúc

~~~text
custom-plugin-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/Main.java
├── buildSrc/
│   ├── build.gradle
│   └── src/main/java/demo/build/OptionalJavaPlugin.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'custom-plugin-lab'
~~~

**`buildSrc/build.gradle`:**

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

gradlePlugin {
    plugins {
        optionalJava {
            id = 'demo.optional-java'
            implementationClass = 'demo.build.OptionalJavaPlugin'
        }
    }
}
~~~

`java-gradle-plugin` đăng ký plugin ID và implementation class. Gradle tự tạo metadata descriptor cần thiết cho plugin; không cần viết thủ công `META-INF/gradle-plugins/*.properties` nếu đã dùng DSL trên.

### 8.2. `buildSrc/src/main/java/demo/build/OptionalJavaPlugin.java`

~~~java
package demo.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.plugins.JavaPluginExtension;
import org.gradle.api.tasks.compile.JavaCompile;
import org.gradle.jvm.toolchain.JavaLanguageVersion;

public final class OptionalJavaPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager().withPlugin("java", applied -> {
            project.getExtensions().configure(
                JavaPluginExtension.class,
                extension -> extension.getToolchain()
                    .getLanguageVersion()
                    .convention(JavaLanguageVersion.of(17))
            );

            project.getTasks().withType(JavaCompile.class)
                .configureEach(task ->
                    task.getOptions().setEncoding("UTF-8")
                );
        });
    }
}
~~~

Phân tích:
- `Plugin<Project>` cho biết plugin áp vào Project, với method `apply(Project project)`.
- `withPlugin("java", ...)` đăng ký callback trên chính project ấy.
- Plugin **không tự áp Java**, nên nó có thể áp dụng vào một project không dùng Java mà không tự tạo compile tasks.
- Khi Java xuất hiện, có Java extension và các task type để cấu hình.
- `configureEach` giúp áp dụng encoding cho JavaCompile tasks kể cả chúng được đăng ký sau.
- Java source của plugin là **build logic**, được `buildSrc` compile và đưa lên classpath của main build; không phải một Java application chạy qua `java demo.build.OptionalJavaPlugin`.

### 8.3. Consumer build script, thứ tự A

**`build.gradle` ở root:**

~~~groovy
plugins {
    id 'demo.optional-java'
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
~~~

**`src/main/java/demo/Main.java`:**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Order independent plugin");
    }
}
~~~

Chạy:

~~~bash
./gradlew run --quiet
~~~

**Stdout của chương trình Java:**

~~~text
Order independent plugin
~~~

Ở thứ tự này custom plugin được áp trước; nó đăng ký hook. Application plugin được áp sau và tự apply Java; hook chạy.

### 8.4. Consumer build script, thứ tự B

Đảo hai dòng trong block `plugins`:

~~~groovy
plugins {
    id 'application'
    id 'demo.optional-java'
}
~~~

Giữ nguyên block `application` và file Java. Kết quả `./gradlew run --quiet` vẫn:

~~~text
Order independent plugin
~~~

Ở thứ tự B, Java đã applied trước lúc custom plugin chạy, vì Application áp Java. Callback `withPlugin("java")` chạy **ngay khi custom plugin đăng ký nó**. Đây là lý do nó order-independent.

### 8.5. Khi phải áp Java bắt buộc

Nếu công ty định nghĩa convention plugin **chỉ dành cho Java projects**, hãy nói rõ hợp đồng và áp Java trực tiếp:

~~~java
@Override
public void apply(Project project) {
    project.getPluginManager().apply("java");
    // Sau đây Java extension và compile task model đã sẵn sàng.
}
~~~

Đây là **snippet**, không phải toàn bộ class mới. Sự khác biệt về thiết kế:
- Plugin **optional integration**: `withPlugin`, không thay semantics project nếu Java vắng mặt.
- Plugin **mandatory requirement**: `apply`, đảm bảo project có Java capability.

Không dùng `withPlugin` rồi chờ mãi nếu một plugin thật sự không thể chạy thiếu Java và cần báo lỗi rõ.

## 9. Tích hợp khi có cả hai plugin

Ví dụ muốn tạo Maven publication khi **cả Java Library và Maven Publish** cùng áp dụng. Bạn không biết thứ tự, nên đăng ký nested callbacks:

~~~groovy
pluginManager.withPlugin('java-library') {
    pluginManager.withPlugin('maven-publish') {
        // Cả hai plugin đã applied: có Java component và publishing extension.
    }
}
~~~

Trình tự:
- Nếu Java Library đến trước: callback ngoài chạy, đăng ký callback cho Maven Publish.
- Nếu Maven Publish đến trước: khi Java Library đến sau, callback ngoài chạy rồi callback trong chạy **ngay**.
- Nếu chỉ có một plugin: đoạn tích hợp không chạy.

Một ví dụ **snippet** có cấu hình publication, chưa có upload repository:

~~~groovy
import org.gradle.api.publish.maven.MavenPublication

pluginManager.withPlugin('java-library') {
    pluginManager.withPlugin('maven-publish') {
        publishing {
            publications {
                create('library', MavenPublication) {
                    from components.java
                }
            }
        }
    }
}
~~~

Khi project có:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
~~~

hai plugins được áp, đoạn tích hợp tạo publication tên `library` từ Java component. Không có `publish` action được yêu cầu ở đây, và đoạn snippet không tự gửi artifact lên mạng. Nếu plugin khác đã tạo publication trùng tên `library`, `create` có thể lỗi; người viết convention plugin cần thống nhất người sở hữu publication.

**Điểm tinh tế:** `withPlugin` chỉ giúp **plugin order-independent**. Nó không tự giải quyết khi hai plugin cùng `set` một property, tạo task cùng tên, hoặc đưa cấu hình xung đột. Các vấn đề đó cần policy, owner rõ ràng, `Property.convention` và integration tests.

## 10. Callback sau plugin nhưng chưa chắc đã có cấu hình cuối cùng

Một anti-pattern:

~~~groovy
pluginManager.withPlugin('java') {
    def toolchainNow = java.toolchain.languageVersion.get()
    println toolchainNow
}
~~~

Java extension có thể tồn tại nhưng toolchain language version chưa có giá trị, hoặc người dùng vẫn định set nó ở các dòng phía sau. `withPlugin` chạy sau **plugin application**, không phải sau khi mọi script/plugins đã cấu hình xong.

**Nên sử dụng Provider/Property:**

~~~groovy
pluginManager.withPlugin('java') {
    extensions.configure(JavaPluginExtension) {
        toolchain.languageVersion.convention(JavaLanguageVersion.of(17))
    }
}
~~~

`convention` đặt **default** mà người dùng có thể override bằng `set`. Nếu yêu cầu nghiệp vụ phải enforce đúng một JDK/version, thiết kế policy/validation rõ thay vì đọc sớm và phỏng đoán value đã final.

Tương tự:
- Không bắt mọi task `get()` trong callback chỉ để đọc status.
- Không resolve `compileClasspath` ở configuration callback một cách tùy tiện.
- Không dùng snapshot của user-supplied environment value nếu task output cần dependency tracking; dùng Providers kết nối vào task properties.

## 11. Multi-project và callback scope

Mỗi project Gradle có plugin manager riêng:

~~~text
root
├── app    (application)
└── lib    (java-library)
~~~

Nếu root `build.gradle` có:

~~~groovy
pluginManager.withPlugin('java') {
    println 'Root Java plugin detected'
}
~~~

callback đó **chỉ quan sát plugin áp dụng vào root project**, không tự bắt sự kiện khi `:app` hoặc `:lib` áp Java.

Có thể viết callback từ root cho subprojects:

~~~groovy
subprojects {
    pluginManager.withPlugin('java') {
        tasks.withType(JavaCompile).configureEach {
            options.encoding = 'UTF-8'
        }
    }
}
~~~

Đây là ví dụ **cross-project configuration**. Nó có thể hợp lệ, nhưng trong build lớn nên ưu tiên **convention plugin áp dụng trực tiếp vào từng subproject** để tránh phụ thuộc giữa các project trong configuration, hỗ trợ isolated projects và dễ tái sử dụng hơn.

### 11.1. Plugin áp dụng gián tiếp

- Application plugin **áp Java plugin**.
- Java Library plugin cũng xây trên Java plugin.
- Convention plugin có thể apply Java bằng `project.pluginManager.apply('java')`.

Vì vậy `withPlugin('java')` có thể chạy dù project không ghi trực tiếp `plugins { id 'java' }`. Nếu logic chỉ dành cho library publication/API, có thể cần lắng nghe **`java-library`** chứ không chỉ `java`.

### 11.2. Không suy luận quá rộng

Hook `withPlugin('java')` chỉ cho biết Java plugin đã applied vào target. Nó **không** chứng minh:
- Java source code tồn tại hoặc compile thành công.
- JUnit Platform được cấu hình.
- Maven publication được tạo.
- Java toolchain đã được tải/cài.
- Người dùng đã hoàn tất mọi DSL values.
- Mọi plugin callback khác đã chạy xong.

Đây là **readiness signal của plugin**, không phải một bài kiểm thử build end-to-end.

## 12. Configuration cache và side effects

`withPlugin` là **configuration logic**. Khi Gradle sử dụng configuration cache, nó có thể reuse mô hình configuration mà không đánh giá lại build script, vì thế callback/`println` bên trong không chạy mỗi lần. Đừng dùng nó như một action đảm bảo chạy trên mỗi invocation.

**Không nên:**

~~~groovy
pluginManager.withPlugin('java') {
    new File('/tmp/gradle-info.txt').text = 'Java plugin active'
}
~~~

Mã ghi file **ngay trong configuration**; hard-code đường dẫn máy và không khai output cho task.

**Hướng đúng:** chỉ **đăng ký task** trong callback:

~~~groovy
pluginManager.withPlugin('java') {
    def report = layout.buildDirectory.file('reports/java-hook.txt')

    tasks.register('writeJavaHookReport') {
        outputs.file(report)

        doLast {
            def target = report.get().asFile
            target.parentFile.mkdirs()
            target.setText('Java plugin active\n', 'UTF-8')
        }
    }
}
~~~

Đây là snippet minh họa cách tách registration khỏi execution. Với convention plugin production, nên dùng **typed custom task** có `RegularFileProperty`, `@OutputFile`/`@TaskAction`, và không capture các đối tượng `Project`/build script không tương thích với configuration cache vào task action.

### 12.1. Performance checklist

- Ưu tiên `tasks.register`, không `tasks.create`.
- Ưu tiên `tasks.named`, không `tasks.getByName` khi không cần instance ngay.
- Ưu tiên `tasks.withType(...).configureEach`, không `all`.
- Dùng `Property/Provider` để giữ value lazy.
- Không resolve all configurations hay iterate mọi task trong `withPlugin`.
- Không gọi network, ghi source/artifact, publish/deploy trong configuration callback.
- Thử `--configuration-cache` khi triển khai reusable plugin.

### 12.2. External plugin classpath

Nếu custom plugin dùng API của một plugin bên ngoài trong code:
- Plugin API phải có mặt trên **compile classpath** khi build custom plugin.
- Trong runtime, plugin API/class có thể khác version do consumer đã apply.
- Gradle có hướng dẫn `compileOnly` cho API của một optional plugin, tránh rò dependency/plugin classpath không cần thiết sang consumers.
- Dùng `withPlugin('external.plugin.id')` để chỉ chạy integration code khi plugin có mặt.

**`withPlugin` không tự tải plugin**; nó không xác định plugin version, repository URL hay credentials. Nếu consumer không thể resolve plugin, cần xử lý ở plugin resolution settings/build-logic dependencies.

## 13. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| `UnknownTaskException` ở `tasks.named('compileJava')` | Java chưa đăng ký task khi lookup | Đưa vào `withPlugin('java')` |
| `withPlugin('java')` không bao giờ chạy | Plugin Java thực tế không áp trong project ấy | Kiểm tra ID/target/plugin application; nếu bắt buộc thì apply |
| Hook chạy ngay dù đứng cuối script | Java đã applied bởi `plugins {}` trước script body | Đây là behavior đúng |
| Hook không in ở lần chạy sau với config cache | Configuration model đã được reuse | Không dùng config logging làm dấu hiệu task execution |
| `hasPlugin('java')` false rồi bỏ lỡ Java | Snapshot ở thời điểm quá sớm | Dùng `withPlugin` |
| `withPlugin` cấu hình property nhưng user override sau | Hook không phải project-final callback | Dùng `convention`/Provider hoặc policy có kiểm soát |
| Hook root không phản ứng với Java ở `:lib` | Plugin manager theo scope project | Đặt convention plugin ở `:lib` |
| Cấu hình JavaCompile quá nhiều tasks | Dùng eager `all`/`getByName` | Chuyển sang `configureEach`/`named` |
| `NoClassDefFoundError` với plugin ngoài | Implementation API classpath không phù hợp hoặc thiếu plugin runtime | Kiểm tra plugin dependency/version và optional integration guard |
| Hai callbacks tạo task cùng tên | Trùng trách nhiệm owner | Chỉ một plugin register task, plugin khác configure qua provider |
| `afterEvaluate` làm kết quả phụ thuộc thứ tự | Project callback ordering fragile | `withPlugin` + lazy APIs |
| Java hook chạy khi áp Application | Application tự áp Java | Đây là behavior đúng |
| Java hook không thiết lập được extension | Dùng sai extension type hoặc áp plugin ID khác | Dùng `JavaPluginExtension` sau Java apply |
| Nested hook không chạy | Một trong hai plugin chưa applied | Kiểm tra cả hai plugin IDs |
| Gắn side effect trong hook gây artifact lạ | Đang ghi trong configuration phase | Tạo task có declared output thay vì ghi ở hook |

### 13.1. Lệnh điều tra

~~~bash
./gradlew help --no-configuration-cache
./gradlew tasks --all
./gradlew showOrder --quiet --no-configuration-cache
./gradlew run --quiet
./gradlew compileJava --info
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

`showOrder`/`run`/`compileJava` chỉ tồn tại nếu project có cấu hình tương ứng. Khi xem `--info`, phân biệt log áp plugin/configuration với task graph/exec. Không đăng logs công khai nếu chúng chứa URL repository/credentials nội bộ.

### 13.2. Quy trình kiểm tra logic

1. Xác định callback thuộc Project/Settings/Gradle target nào; chủ đề ở đây chủ yếu là `Project.pluginManager`.
2. Tìm **plugin ID thực** được apply ở project.
3. Xác định apply trực tiếp, trong `plugins {}` hay gián tiếp do plugin khác.
4. So sánh thời điểm callback đăng ký và thời điểm apply.
5. Đối chiếu task/extension chính xác do plugin cung cấp.
6. Kiểm tra có eager task lookup, Provider.get hoặc afterEvaluate không.
7. Kiểm tra user config sau plugin callback có ghi đè default không.
8. Thử hai thứ tự plugin ở cùng project và kiểm tra task graph/outputs.
9. Thử configuration cache và đọc báo cáo nếu không tương thích.
10. Khi là reusable binary plugin, viết TestKit/integration test cho cả plugin present/absent.

## 14. Bài tập có đáp án

### Bài 1 — Đã applied

~~~groovy
plugins {
    id 'java'
}
pluginManager.withPlugin('java') {
    println 'ready'
}
~~~

**Đáp án:** `ready` in khi callback được **đăng ký** trong configuration, vì `plugins {}` đã áp Java trước script body; không cần chạy `build`.

### Bài 2 — Applied sau

~~~groovy
pluginManager.withPlugin('java') { println 'hook' }
println 'before'
pluginManager.apply('java')
println 'after'
~~~

**Đáp án:** Output do script in theo thứ tự `before`, `hook`, `after`. Hook chạy sau Java applied trước khi `apply` trả về.

### Bài 3 — Không áp dụng

Project chỉ áp Base plugin, có callback `withPlugin('java')`. Java tasks có tự xuất hiện không?

**Đáp án:** Không. `withPlugin` không tự áp plugin; callback không chạy khi Java không applied.

### Bài 4 — Snapshot sai thời điểm

Một convention plugin dùng `if (pluginManager.hasPlugin('java')) { ... }`, sau đó người dùng áp Java. Logic integration có tự chạy lại không?

**Đáp án:** Không. `hasPlugin` chỉ trả trạng thái hiện tại, không đăng ký listener. Dùng `withPlugin`.

### Bài 5 — Lazy task

Tại sao `tasks.withType(JavaCompile).configureEach` khác `tasks.withType(JavaCompile).all`?

**Đáp án:** `configureEach` trì hoãn cấu hình đến khi tasks cần được realize, tránh eager configuration và áp cho tasks thêm sau.

### Bài 6 — Chưa phải giá trị cuối

`withPlugin('java')` đọc `java.toolchain.languageVersion.get()` ngay, rồi người dùng set toolchain sau. Giá trị callback đã đọc có chắc đúng cuối cùng?

**Đáp án:** Không; callback chỉ đợi Java applied. Dùng `Property.convention`/Provider thay vì snapshot sớm.

### Bài 7 — Hai plugins

`withPlugin('java-library')` lồng `withPlugin('maven-publish')`, Maven Publish áp trước. Callback chung có chạy khi Java Library xuất hiện sau?

**Đáp án:** Có, vì callback trong được đăng ký khi Maven Publish đã applied và sẽ chạy ngay.

### Bài 8 — Plugin áp gián tiếp

User áp `application` mà không khai `java` trực tiếp. Callback `withPlugin('java')` có chạy?

**Đáp án:** Có. Application plugin áp Java plugin.

### Bài 9 — PluginContainer

`plugins.withId('java') { plugin -> ... }` khác `pluginManager.withPlugin('java') { applied -> ... }` về tham số gì?

**Đáp án:** `withId` nhận **Plugin instance**; `withPlugin` nhận **AppliedPlugin** thông tin áp dụng.

### Bài 10 — buildSrc

Custom plugin trong lab phần 8 được áp **trước** Application rồi đảo thứ tự. Vì sao cả hai đều chạy cùng output?

**Đáp án:** Callback `withPlugin("java")` hoạt động với cả Java xuất hiện sau lẫn đã applied. Tích hợp không phụ thuộc thứ tự trong `plugins {}`.

### Bài 11 — Multi-project

Root `withPlugin('java')` có tự nhìn thấy `:lib` áp `java-library` không?

**Đáp án:** Không. PluginManager theo Project target; nên áp convention plugin vào từng subproject cần hành vi đó.

### Bài 12 — Configuration cache

Tại sao các dấu mốc `println` trong demo timing có thể biến mất ở lần chạy kế tiếp nếu bật configuration cache?

**Đáp án:** Configuration state được reuse nên Gradle không cần evaluate script và gọi callbacks một lần nữa. Task action vẫn hoạt động theo task graph/up-to-date rules.

**Tiêu chí hoàn thành:** Bạn dự đoán được lúc plugin applied, hook được đăng ký và chạy, lý do `tasks.named` hợp lệ trong hook, lúc nào phải `apply` thay vì `withPlugin`, cách tránh eager tasks và cách giữ tích hợp đúng khi đảo plugin order.

## 15. Checklist dành cho build author

- [ ] Plugin khác là **bắt buộc**? Nếu có, `pluginManager.apply` rõ ràng.
- [ ] Plugin khác là **tùy chọn**? Dùng `pluginManager.withPlugin('exact.id')`.
- [ ] Không dùng `hasPlugin` snapshot như một future listener.
- [ ] Không nhầm plugin applied với project configured xong.
- [ ] Dùng `tasks.named` cho task có sẵn, `withType(...).configureEach` cho mọi task của type.
- [ ] Dùng Provider/Property/convention thay vì gọi `get()` sớm.
- [ ] Tránh `afterEvaluate` để chờ plugin.
- [ ] Không tạo artifact/deploy/network effect trong hook.
- [ ] Không áp plugin bên ngoài chỉ để hook được chạy.
- [ ] Kiểm thử hai thứ tự application khi tạo reusable plugin.
- [ ] Multi-project dùng đúng target; ưu tiên convention plugin áp vào từng project.
- [ ] Chú ý plugin classpath/version khi tích hợp plugin bên ngoài.
- [ ] Kiểm thử Gradle configuration cache và task laziness.

## 16. Tài liệu Gradle chính thức

- [Gradle — PluginManager API](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/PluginManager.html): `apply`, `findPlugin`, `hasPlugin`, `withPlugin` và hợp đồng callback.
- [Gradle — PluginContainer API](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/PluginContainer.html): `withId` và plugin instances.
- [Gradle — General Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): tránh phụ thuộc plugin order và `afterEvaluate`, dùng `withPlugin`.
- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach` và eager APIs.
- [Gradle — Plugin Basics](https://docs.gradle.org/current/userguide/plugin_basics.html): plugin application và model.
- [Gradle — Implementing Gradle Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): tạo plugin và lifecycle.
- [Gradle — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): `Plugin<Project>`, classpath và optional plugin integration.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): Application áp Java và cung cấp `JavaApplication`/`run`.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): JavaPluginExtension, JavaCompile và Test.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration state reuse và side effects.
