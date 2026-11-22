# Dependency project so với dependency vào đường dẫn artifact thủ công trong Gradle

## Mục tiêu bài học

Khi xây dựng nhiều dự án Java trong cùng một Gradle build, bạn thường muốn module **:app** sử dụng code của module **:lib**. Có hai cách trông có vẻ tương đương nhưng thực chất rất khác nhau:

~~~groovy
// Cách 1: mô hình dependency của Gradle
dependencies {
    implementation project(':lib')
}

// Cách 2: trực tiếp chỉ tới một JAR trên đĩa
dependencies {
    implementation files('../lib/build/libs/lib.jar')
}
~~~

Cả hai đều *có thể* khiến compiler tìm thấy class của lib trong một số hoàn cảnh. Tuy nhiên, cách thứ nhất khai báo **quan hệ giữa hai project**, để Gradle chọn **variant**, tính **dependency graph**, đưa các **transitive dependencies** thích hợp vào classpath và lập lịch các task tạo output được chọn. Cách thứ hai chỉ cung cấp **một file path**, không tự mang theo metadata, không tự yêu cầu module lib biên dịch và không mô tả dependencies của lib.

Bài này tập trung vào **Build nhiều dự án** và quyết định quan trọng: **khi nào phải dùng project dependency, khi nào file dependency có lý do chính đáng, và vì sao tham chiếu thẳng build/libs là anti-pattern cho module nội bộ**.

Sau khi học, bạn sẽ:

1. Phân biệt **ProjectDependency**, **FileCollection/file dependency** và **external module dependency**.
2. Hiểu producer/consumer, project path khai báo trong **settings.gradle**, cấu hình **api/implementation/runtimeOnly**.
3. Giải thích **variant-aware resolution**: apiElements, runtimeElements và khả năng Gradle dùng classes directory thay vì tạo JAR khi compile.
4. Hiểu task dependency ngầm phát sinh từ project dependency và vì sao path tới JAR không mang theo task provenance.
5. Mô tả lỗi missing JAR trên clean build, stale JAR, thiếu transitive dependency, sai runtime classpath và tình trạng CI không tái lập.
6. Chạy lab **Java 17**, bốn module **:api, :engine, :lib, :app**, với kết quả stdout chính xác.
7. Thử thay project dependency bằng file paths một cách có kiểm soát để thấy vấn đề compile/runtime/order.
8. Dùng **files(...){ builtBy ... }** đúng trường hợp file được task tạo, và biết giới hạn của cách này.
9. Hiểu **outgoing consumable configurations và artifact variants** khi thật sự phải chia sẻ một artifact tùy chỉnh giữa các projects.
10. Chọn phương pháp an toàn cho CI, publishing, build cache, Java compatibility và quản trị phụ thuộc.

Ví dụ chính dùng **Groovy DSL**. Phần Kotlin DSL được trình bày riêng. **JDK 17+** và Gradle Wrapper tương thích là điều kiện cho lab; bản lab project-dependency **không cần Maven Central để lấy thư viện ngoài**, vì toàn bộ mã Java tự nằm trong bốn modules. Nếu Gradle distribution chưa có trong máy, Wrapper vẫn có thể cần tải distribution.

---

## 1. Ba loại dependency cần phân biệt

Gradle hỗ trợ các loại dependency phổ biến:

| Loại | Ví dụ Groovy DSL | Trỏ tới | Có metadata của module? |
| --- | --- | --- | --- |
| **Project dependency** | implementation project(':lib') | Một Gradle project trong multi-project build | Có: variants, attributes, dependency graph của project |
| **External module dependency** | implementation 'org.example:lib:1.2' | Module có tọa độ từ repository | Có nếu repository cung cấp POM/Gradle Module Metadata/Ivy descriptor |
| **File dependency** | implementation files('libs/lib.jar') | Một hoặc nhiều local files | Không có dependency metadata của file chỉ từ path |

**Project dependency** và **external module dependency** dùng dependency resolution engine. File dependency vẫn xuất hiện như một dependency file collection trong build, nhưng Gradle không tự biết **file thuộc module nào, được tạo từ task nào, có dependencies gì, version nào, ai publish** chỉ dựa trên đường dẫn.

### 1.1. Project path không phải file-system path

~~~groovy
implementation project(':lib')
~~~

Tên **:lib** là **định danh project** trong Gradle build. Nó được khai báo ở **settings.gradle**, không phải đường dẫn thư mục JAR.

~~~groovy
rootProject.name = 'multi-project-lab'
include 'api', 'engine', 'lib', 'app'
~~~

Gradle ánh xạ project path **:lib** tới thư mục **lib/** theo convention, nhưng bạn có thể cấu hình lại projectDir trong settings. Vì vậy không được suy luận project path nhất thiết trùng với filesystem path trong mọi repository.

Trong dự án lồng nhau, có thể có **project(':platform:shared')** với khai báo include phù hợp. **:platform:shared** khác một Maven coordinate và cũng khác chuỗi đường dẫn tương đối tới **shared.jar**.

### 1.2. File path phụ thuộc vị trí đang viết script

Trong file **app/build.gradle**:

~~~groovy
dependencies {
    implementation files('../lib/build/libs/lib.jar')
}
~~~

Path tương đối được giải quyết theo **project directory** của **:app**, không phải tên project path. Khi thay đổi output directory, archive name, version hoặc layout của producer, string này có thể trở thành path sai.

Nếu file chưa được tạo, việc file path tồn tại trên giấy trong DSL **không khiến Gradle tự hiểu producer là task :lib:jar**.

### 1.3. Project dependency không phải “copy JAR”

Với **project(':lib')**, Gradle có thể lấy các class directories đã biên dịch thay vì một JAR cho **compileClasspath**, nhờ secondary artifact sets/variants được Java Library plugin cung cấp. Ngược lại, **runtimeClasspath** có thể chọn JAR hoặc resource outputs tương ứng.

Do đó không nên nghĩ “project dependency đơn giản là đường dẫn build/libs được Gradle điền hộ”. Nó là quan hệ thành phần/variant, có thể chọn nhiều dạng artifact theo nhu cầu của consumer.

---

## 2. Producer và consumer là ai?

Giả sử:

~~~text
multi-project-lab/
├── api/
├── engine/
├── lib/
└── app/
~~~

Vai trò:

- **:api** công khai interface mà thư viện muốn expose.
- **:engine** chứa code trợ giúp nội bộ.
- **:lib** cung cấp class Greeter và phụ thuộc :api/:engine.
- **:app** là consumer dùng Greeter.

Sơ đồ dependencies:

~~~text
:app
  |
  +-- implementation project(':lib')
                      |
                      +-- api project(':api')
                      |
                      +-- implementation project(':engine')
~~~

Khi **:app** compile:

- Cần API của **:lib**.
- Vì public API của :lib trả về type từ :api, consumer phải thấy **:api** trên compile classpath.
- **:engine** chỉ được dùng bên trong method body của :lib nên thường không cần trên compile classpath của :app.

Khi **:app** chạy:

- Cần classes của **:app**, **:lib**, **:api** và **:engine**.
- :engine là runtime dependency của :lib dù không thuộc public API.

Phân biệt compile/runtime classpaths là nền tảng để hiểu vì sao chỉ copy **lib.jar** thường không đủ.

### 2.1. api và implementation của Java Library plugin

Trong **lib/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':api')
    implementation project(':engine')
}
~~~

**api** thể hiện dependency có types trong public API của thư viện hoặc cần được expose cho consumer compile. **implementation** là dependency phục vụ nội bộ nhưng vẫn cần khi chạy code thư viện.

Ở consumer **:app**:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

Gradle dùng metadata/variants để giải quyết sự khác biệt này. Không cần consumer thủ công liệt kê tất cả dependencies của lib ở mọi phiên bản build.

### 2.2. Khi nào dùng api thay implementation?

Nếu một public method của :lib trả về hoặc nhận type **demo.api.Greeting**, dependency vào :api thuộc **api**.

Nếu :lib chỉ gọi **demo.engine.TextFormatter** trong method body mà không expose type của engine trong method signature, nó thuộc **implementation**.

Đừng thêm mọi dependency của :lib vào api chỉ để app compile: điều đó làm rò dependencies nội bộ vào consumer compileClasspath, tăng recompilations và khó bảo trì.

### 2.3. Project dependency còn mang theo dependency graph

Một JAR thông thường chỉ chứa classes/resources đã được đóng gói. Nó **không tự chứa toàn bộ JARs** trong implementation/api của producer; JAR kiểu này thường gọi là **thin JAR**.

Gradle project dependency biết graph của :lib nên có thể đưa :api/:engine vào classpaths phù hợp. Một đường dẫn tới **lib.jar** không biết graph đó, trừ khi bạn tự mô tả thêm.

---

## 3. Gradle chọn variant như thế nào?

Gradle có cơ chế **variant-aware dependency resolution**: consumer yêu cầu các thuộc tính, producer công bố những variants có attributes và artifacts. Engine chọn variant tương thích hoặc fail nếu không có lựa chọn hợp lệ.

Một **java-library** module thường có:

| Producer variant | Usage | Dependency scope tiêu biểu |
| --- | --- | --- |
| **apiElements** | java-api | Public API dependencies (api, compileOnlyApi theo semantics) |
| **runtimeElements** | java-runtime | Runtime dependencies (implementation, runtimeOnly và những phần liên quan) |

Consumer thường dùng:

| Consumer configuration | Mục đích | Variant producer phù hợp |
| --- | --- | --- |
| **compileClasspath** | Biên dịch code gọi library API | apiElements hoặc artifact set phù hợp |
| **runtimeClasspath** | Chạy code ứng dụng | runtimeElements hoặc artifact set phù hợp |

### 3.1. Attributes không chỉ có usage

Các thuộc tính liên quan Java bao gồm:

- **org.gradle.usage**: java-api hoặc java-runtime.
- **org.gradle.libraryelements**: jar, classes, resources hoặc loại artifact tương ứng.
- **org.gradle.category**: library hay category khác.
- **org.gradle.jvm.version**: mức Java tối thiểu producer cần.
- **org.gradle.dependency.bundling**: hình thức đóng gói dependencies.
- Những attributes do plugin/project tùy chỉnh.

Nếu consumer chỉ hỗ trợ JVM 17 nhưng producer công bố variant yêu cầu Java 21, Gradle có thể từ chối ngay khi resolution. Với đường dẫn file JAR thô, không có bộ metadata variants để Gradle kiểm tra compatibility ở bước chọn dependency theo cùng cách.

### 3.2. Classes folder có thể được chọn thay vì JAR

Java Library plugin có thể cung cấp **secondary variant classes**: compile dựa trên directory **build/classes/java/main** thay vì đợi **:lib:jar**. Điều này giảm công việc tạo archive không cần thiết và có thể hỗ trợ incremental compilation.

Do đó, khi chạy:

~~~bash
./gradlew :app:compileJava
~~~

bạn có thể thấy các compilation tasks của producer chạy, nhưng **:lib:jar** không nhất thiết chạy. Đây là hành vi hợp lệ: consumer yêu cầu **khả năng compile**, không yêu cầu mọi trường hợp phải có một JAR trên đĩa.

### 3.3. Kiểm tra variants trong project thật

~~~bash
./gradlew :lib:outgoingVariants
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
~~~

Khi xem output, chú ý attributes, artifact sets, dependency configurations, **apiElements** và **runtimeElements**. Tên secondary variants và output layout có thể khác theo Gradle version/plugin, nhưng nguyên tắc producer/consumer matching không thay đổi.

### 3.4. Version mismatch không nên che bằng file path

Nếu một project Java 17 không chọn được variant từ thư viện Java 21, đừng sửa bằng cách đặt **implementation files('lib.jar')** để qua bước variant matching. Dù compiler có thể tìm thấy class trong một số trường hợp, runtime Java 17 vẫn không hỗ trợ Java 21 bytecode (class file major 65).

Sửa đúng: align Java toolchains, options.release, target compatibility hoặc chọn producer variant hỗ trợ Java 17.

---

## 4. Task dependency và build order

### 4.1. Project dependency tạo quan hệ producer–consumer

Khi bạn khai báo:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

Gradle biết consumer cần output của producer. Các **build dependencies** của artifact/class directory được chọn có thể được đưa vào task graph.

**Không cần**:

~~~groovy
tasks.named('compileJava') {
    dependsOn ':lib:jar'
}
~~~

để làm project dependency hoạt động. Thậm chí gắn thủ công :lib:jar có thể khiến archive được build không cần thiết khi compile chỉ cần classes directory.

### 4.2. File dependency không tự tạo task phụ thuộc

~~~groovy
dependencies {
    implementation files('../lib/build/libs/lib.jar')
}
~~~

Gradle biết một FileCollection. Nó **không có căn cứ** để suy ra file ấy do **:lib:jar** tạo. Nếu JAR chưa có, task **:app:compileJava** có thể thất bại vì không tìm thấy package/class; nếu JAR cũ còn từ một lần build trước, nó có thể compile bằng bytes cũ.

Đây là lỗi nghiêm trọng ở CI: developer chạy **:lib:jar** từ tuần trước nên build local xanh, trong khi clean checkout và CI mới chỉ chạy **:app:compileJava** thì không có JAR.

### 4.3. Tại sao chỉ sửa bằng dependsOn là chưa đủ?

Một workaround:

~~~groovy
tasks.named('compileJava') {
    dependsOn ':lib:jar'
}
~~~

có thể bắt producer tạo JAR trước compile theo task graph, nhưng **không thêm transitive dependencies của lib**, không khôi phục api/runtime variants, không mô tả metadata/publishing. Nó cũng ghép chặt task names giữa projects.

Với module Java trong cùng build, **implementation project(':lib')** là cách đúng, không phải một JAR path cộng thêm dependsOn thủ công.

### 4.4. Thứ tự yêu cầu trên command line không thay graph

Chạy:

~~~bash
./gradlew :lib:jar :app:compileJava
~~~

có thể tạo JAR trước trong một lượt chạy theo cách Gradle lập lịch, nhưng không làm cho mối quan hệ giữa file dependency và producer trở thành một dependency graph bền vững. Nếu người khác chỉ gọi **:app:compileJava**, graph vẫn thiếu.

Thiết kế build đúng phải bảo đảm **mỗi entrypoint cần thiết** tái lập được, không phụ thuộc “nhớ chạy thêm một lệnh trước”.

### 4.5. builtBy cho file thật sự có producer task

FileCollection của Gradle có thể khai báo **builtBy** khi file được sinh bởi một task.

Ví dụ *fragment* trong **cùng một project**, giả định có file **vendor/helper.jar**:

~~~groovy
def stageVendor = tasks.register('stageVendor', Copy) {
    from('vendor/helper.jar')
    into(layout.buildDirectory.dir('staged'))
}

def stagedJar = files(
    layout.buildDirectory.file('staged/helper.jar')
) {
    builtBy stageVendor
}

dependencies {
    runtimeOnly stagedJar
}
~~~

Ở đây **stagedJar** có task provenance **stageVendor**, giúp Gradle biết phải copy file trước khi consumer cần nó. Điều này có ích cho **file thực sự được tạo bởi một task**. Nó **không làm JAR có POM/Gradle Module Metadata, transitive dependencies hay Java variant attributes**.

**Fragment không độc lập**: cần file vendor/helper.jar tồn tại, Java plugin và consumer thực sự dùng runtimeOnly. Nó không phải pattern được khuyến nghị để truy cập **output project khác** khi đã có project dependency phù hợp.

---

## 5. Lab Java 17: project dependency đúng

Lab có bốn modules **:api**, **:engine**, **:lib**, **:app** và chỉ dùng core Gradle plugins. Mã Java không dùng thư viện bên ngoài, nên không cần Maven Central để resolve code dependencies của lab.

### 5.1. Cây thư mục

~~~text
multi-project-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── api/
│   ├── build.gradle
│   └── src/main/java/demo/api/Greeting.java
├── engine/
│   ├── build.gradle
│   └── src/main/java/demo/engine/TextFormatter.java
├── lib/
│   ├── build.gradle
│   └── src/main/java/demo/lib/Greeter.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

Nếu chưa có Wrapper, tạo bằng một Gradle distribution được cài hợp lệ hoặc lấy từ project tin cậy. Không tự tạo **gradle-wrapper.jar** bằng cách chép text. JDK 17 phải được Gradle phát hiện; Java Toolchain Resolver chỉ cần nếu JDK thích hợp chưa cài và team muốn auto-provision.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'multi-project-lab'

include 'api', 'engine', 'lib', 'app'
~~~

**settings.gradle** định nghĩa cả bốn Gradle project paths. Nếu không include **lib**, consumer dùng project(':lib') sẽ báo project không tồn tại thay vì tự tìm lib/build.gradle theo filesystem.

### 5.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}
~~~

Root script không dùng **subprojects { apply plugin ... }** để gây cấu hình chéo ngoài ý muốn. Mỗi subproject tự áp plugin tương ứng. Root này không khai báo external dependency repositories vì không có external code dependencies.

### 5.4. api/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

**java-library** công bố Java library variants phù hợp cho consumer. **options.release = 17** bảo đảm compiler đủ mới chỉ cho phép Java 17 APIs/language/bytecode, không chỉ source/target syntax.

### 5.5. api/src/main/java/demo/api/Greeting.java

~~~java
package demo.api;

@FunctionalInterface
public interface Greeting {
    String text();
}
~~~

Type **Greeting** sẽ xuất hiện trong public method signature của :lib. Điều đó quyết định tại sao :lib phải khai báo **api project(':api')**.

### 5.6. engine/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

### 5.7. engine/src/main/java/demo/engine/TextFormatter.java

~~~java
package demo.engine;

public final class TextFormatter {
    private TextFormatter() {
    }

    public static String greeting(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

TextFormatter là chi tiết triển khai của thư viện :lib. Consumer :app không cần import type này.

### 5.8. lib/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    api project(':api')
    implementation project(':engine')
}
~~~

Hai declarations rất quan trọng:

- **api project(':api')**: public return type của Greeter liên quan tới interface Greeting.
- **implementation project(':engine')**: TextFormatter chỉ được dùng trong implementation, không nằm trong public API.

Nếu thay **api project(':api')** thành **implementation project(':api')**, consumer :app có thể không compile vì signature của Greeter tham chiếu type Greeting mà consumer compileClasspath không thấy.

### 5.9. lib/src/main/java/demo/lib/Greeter.java

~~~java
package demo.lib;

import demo.api.Greeting;
import demo.engine.TextFormatter;

public final class Greeter {
    private Greeter() {
    }

    public static Greeting forPerson(String name) {
        return () -> TextFormatter.greeting(name);
    }
}
~~~

Greeter trả về **Greeting** (type từ :api), nhưng phần lambda body gọi **TextFormatter** của :engine. Đây là ví dụ thật, nhỏ và thể hiện rõ api/implementation separation.

### 5.10. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencies {
    implementation project(':lib')
}

application {
    mainClass = 'demo.app.Main'
}
~~~

**application** là core Gradle plugin, tạo task **:app:run** để thực thi Java main. App chỉ khai báo **một project dependency**. Gradle phải giải quyết các dependencies của :lib ở scope phù hợp.

### 5.11. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.api.Greeting;
import demo.lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        Greeting greeting = Greeter.forPerson("Lan");
        System.out.println(greeting.text());
    }
}
~~~

**Main** tham chiếu type Greeting từ :api qua public API của :lib. JVM cần TextFormatter từ :engine khi callback của lambda được thực thi.

### 5.12. Chạy project đúng

Linux/macOS:

~~~bash
./gradlew :app:run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run
~~~

Stdout do chương trình Java in chính xác:

~~~text
Xin chào, Lan!
~~~

Toàn console còn có Gradle task logs và BUILD SUCCESSFUL; dòng trên là **stdout của Main**, không phải transcript hoàn chỉnh. Nếu JDK 17 toolchain thiếu, lỗi xảy ra trước khi program chạy; kiểm tra **./gradlew -q javaToolchains**.

### 5.13. Khi chỉ yêu cầu compileJava

~~~bash
./gradlew :app:compileJava
~~~

Gradle có thể lập lịch compilation outputs của :api/:engine/:lib mà :app cần. **Không được kết luận :lib:jar luôn phải chạy.** Với Java Library plugin, consumer compile có thể dùng class directories. Điều cần kiểm tra là compile task thành công từ clean state, không phải số lượng JAR được tạo.

### 5.14. Xem dependency graph

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Kỳ vọng về logic:

- **compileClasspath** của :app chứa project **:lib** và public API dependency **:api**.
- **:engine** không phải API dependency của :lib, nên bình thường không được expose trên compileClasspath của :app.
- **runtimeClasspath** chứa các phần cần cho runtime, gồm **:lib, :api, :engine**.

Output exact (variant labels, indentation, selected artifacts) thay đổi theo Gradle version; không dựa vào một transcript giả định để đánh giá. Hãy so resolved graph và kiểm tra build chạy.

### 5.15. Xem producer variants

~~~bash
./gradlew :lib:outgoingVariants
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
~~~

Những lệnh này giúp chứng minh library công bố apiElements/runtimeElements và consumer yêu cầu usage/attributes nào, thay vì chỉ đọc tên JAR trong thư mục build.

### 5.16. Chạy clean build

~~~bash
./gradlew :api:clean :engine:clean :lib:clean :app:clean :app:run
~~~

Tất cả subprojects dọn outputs của chính chúng, sau đó app run làm Gradle tạo lại những outputs cần thiết qua project dependency graph. Không cần tự chạy **:api:jar**, **:engine:jar**, **:lib:jar** trước.

**Kết quả của app vẫn là:**

~~~text
Xin chào, Lan!
~~~

Việc tasks được Gradle đánh dấu UP-TO-DATE/FROM-CACHE thay đổi theo môi trường nhưng behavior đúng phải giữ nguyên.

---

## 6. Thí nghiệm đối chứng: thay project dependency bằng file path

**Không áp vào build production.** Hãy copy lab sang một thư mục khác hoặc giữ thay đổi local dễ hoàn nguyên; mục tiêu chỉ để nhận diện sự khác biệt.

### 6.1. Bước 1 — Chỉ trỏ tới lib.jar

Thay block dependencies trong **app/build.gradle** bằng:

~~~groovy
dependencies {
    implementation files('../lib/build/libs/lib.jar')
}
~~~

Không sửa các project khác. Bây giờ consumer không còn dependency graph tới **:lib**; nó chỉ biết một file.

### 6.2. Bước 2 — Dọn producer outputs rồi compile app

~~~bash
./gradlew :api:clean :engine:clean :lib:clean :app:clean
./gradlew :app:compileJava
~~~

**Kết quả dự kiến:** **:app:compileJava** thất bại vì classpath thiếu JAR/classes cung cấp **demo.lib.Greeter** (cách compiler trình bày có thể khác). Gradle không tự gọi :lib:jar chỉ vì string path trỏ vào lib/build/libs.

Lỗi có thể có dạng rút gọn:

~~~text
error: package demo.lib does not exist
~~~

Đây là **minh họa loại lỗi**, không phải cam kết nguyên văn toàn bộ log javac.

### 6.3. Bước 3 — Tạo lib.jar bằng tay

~~~bash
./gradlew :lib:jar
./gradlew :app:compileJava
~~~

**:lib:jar** tạo JAR lib và các compilation outputs producer cần. Tuy nhiên, app vẫn có thể không compile vì **demo.api.Greeting** xuất hiện trong public signature của Greeter nhưng chỉ có **lib.jar** trên classpath.

Bạn có thể thấy lỗi tương tự:

~~~text
cannot access Greeting
class file for demo.api.Greeting not found
~~~

Log thực tế phụ thuộc javac/Gradle version. Điểm cần học: **JAR lib không tự chứa JAR api** và file dependency không đi kèm metadata nói rằng lib cần api.

### 6.4. Bước 4 — Ghép thêm api.jar và engine.jar thủ công

Trước hết chạy trong **một lượt riêng** để tạo đủ archives:

~~~bash
./gradlew :api:jar :engine:jar :lib:jar
~~~

Sau đó cấu hình **app/build.gradle**:

~~~groovy
dependencies {
    implementation files(
        '../lib/build/libs/lib.jar',
        '../api/build/libs/api.jar'
    )
    runtimeOnly files('../engine/build/libs/engine.jar')
}
~~~

Chạy:

~~~bash
./gradlew :app:clean :app:run
~~~

Khi ba files thật sự tồn tại, app có thể compile và chạy, stdout:

~~~text
Xin chào, Lan!
~~~

Nhưng **đây không phải tương đương kỹ thuật với project dependency**:

- App tự liệt kê những JAR cần thiết.
- Không tự lập lịch tasks tạo JAR khi chỉ gọi app:run từ một checkout sạch.
- Nếu :lib thay dependency nội bộ, app có thể phải thay danh sách path bằng tay.
- Chọn version, metadata, Java compatibility và variant attributes bị mất.
- App có thể dùng **JAR cũ** dù source :lib thay đổi mà JAR chưa build lại.
- Thay archive baseName/version/output path sẽ làm chuỗi path lỗi.
- Khi publish app, danh sách local file dependencies không trở thành dependency coordinates trong descriptor cho consumers ở build khác.

### 6.5. Bước 5 — Thử lỗi stale artifact

Giữ file-dependency version. Sau khi tạo lib.jar, đổi chuỗi trong **TextFormatter.greeting** từ **"Xin chào, "** thành **"Chào bạn, "** trong module :engine, nhưng **không rebuild engine.jar**.

Chạy:

~~~bash
./gradlew :app:run
~~~

Vì app chỉ nhìn file **engine.jar** cũ, output có thể vẫn là:

~~~text
Xin chào, Lan!
~~~

Đây là **tình huống stale artifact có điều kiện** (JAR cũ phải còn nguyên, app không có project dependency nào khác tự cập nhật nó). Với project dependency, Gradle mô hình hóa source→tasks→consumer, nên khi build cần producer output thay đổi, task graph và up-to-date checks có thể xử lý.

### 6.6. Khôi phục lab đúng

Trong **app/build.gradle**, trả lại:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

Rồi chạy:

~~~bash
./gradlew :app:run
~~~

Giờ app nhận code mới nếu producer source được sửa và tasks cần thiết chạy. Nếu TextFormatter đã đổi thành **Chào bạn**, stdout tương ứng là:

~~~text
Chào bạn, Lan!
~~~

Nếu không muốn giữ thay đổi thực nghiệm ở engine, hoàn nguyên source về **Xin chào** để các lệnh và expected output trong mục 5 khớp.

### 6.7. Sơ đồ so sánh dependency graph và file path

~~~text
PROJECT DEPENDENCY:
:app:run
  -> runtimeClasspath
     -> project :lib runtime variant
        -> :api + :engine variants/dependencies
           -> producer tasks và artifacts được chọn

FILE DEPENDENCY:
:app:run
  -> runtimeClasspath
     -> ../lib/build/libs/lib.jar
     -> ../api/build/libs/api.jar (nếu liệt kê)
     -> ../engine/build/libs/engine.jar (nếu liệt kê)
     -> không tự biết ai tạo ba files
~~~

Chính sự khác biệt về mô hình này quan trọng hơn việc cuối cùng Java có đọc được một file JAR hay không.

---

## 7. Dùng javac/java độc lập để hiểu classpath

Nếu bạn muốn hình dung những bước mà Gradle thực hiện giúp project dependency, có thể biên dịch **chính bốn source files từ lab** bằng JDK 17 trực tiếp. Phần này độc lập với build.gradle nhưng dùng cùng cấu trúc nguồn.

### 7.1. Linux/macOS

Tại root thư mục lab:

~~~bash
mkdir -p out/api out/engine out/lib out/app

javac --release 17 -encoding UTF-8 -d out/api \
    api/src/main/java/demo/api/Greeting.java

javac --release 17 -encoding UTF-8 -d out/engine \
    engine/src/main/java/demo/engine/TextFormatter.java

javac --release 17 -encoding UTF-8 \
    -cp out/api:out/engine \
    -d out/lib \
    lib/src/main/java/demo/lib/Greeter.java

javac --release 17 -encoding UTF-8 \
    -cp out/api:out/lib \
    -d out/app \
    app/src/main/java/demo/app/Main.java

java -cp out/app:out/lib:out/api:out/engine demo.app.Main
~~~

Stdout của chương trình nếu nguồn chưa bị thay trong thí nghiệm:

~~~text
Xin chào, Lan!
~~~

Giải thích:
- Compiler của **:lib** cần :api và :engine.
- Compiler của **:app** chỉ cần :lib và :api.
- Runtime của **:app** còn cần :engine khi lambda gọi TextFormatter.

### 7.2. Windows PowerShell

Windows dùng dấu **chấm phẩy** để phân tách các phần tử classpath:

~~~powershell
New-Item -ItemType Directory -Force out\api,out\engine,out\lib,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\api api\src\main\java\demo\api\Greeting.java

javac --release 17 -encoding UTF-8 -d out\engine engine\src\main\java\demo\engine\TextFormatter.java

javac --release 17 -encoding UTF-8 -cp "out\api;out\engine" -d out\lib lib\src\main\java\demo\lib\Greeter.java

javac --release 17 -encoding UTF-8 -cp "out\api;out\lib" -d out\app app\src\main\java\demo\app\Main.java

java -cp "out\app;out\lib;out\api;out\engine" demo.app.Main
~~~

Stdout:

~~~text
Xin chào, Lan!
~~~

Các lệnh trên không cần Gradle, Maven Central hay JUnit; chỉ JDK17+ và đúng file layout của mục 5. Chúng làm rõ *vì sao file dependencies yêu cầu bạn tự lắp classpath* — Gradle project dependency giúp duy trì graph thay vì bắt mọi consumer tự điền đường dẫn.

### 7.3. Thử bỏ engine runtime

Ví dụ Linux/macOS:

~~~bash
java -cp out/app:out/lib:out/api demo.app.Main
~~~

Khi Main gọi **greeting.text()**, code lib cần **demo.engine.TextFormatter**. Nếu class không có ở classpath, JVM thường ném **NoClassDefFoundError** liên quan TextFormatter. Đó là lỗi **runtime dependency bị thiếu**, không phải thiếu source code của app.

### 7.4. Một classpath có đủ file vẫn có thể sai version

Biên dịch :engine bằng JDK21 target21 trong khi app chạy JDK17 sẽ không thể load Java21 class bytecode. File path vẫn tồn tại; Gradle file dependency không chọn variant theo Java compatibility như project dependency có metadata.

Cách sửa là thống nhất toolchain/options.release và module variants, không chỉ “thêm đúng tên JAR”.

---

## 8. File dependency có khi nào phù hợp?

File dependencies **không bị cấm**. Chúng hợp lý nếu bạn thật sự có **một artifact độc lập trên đĩa** với lifecycle/version/provenance được quản lý khác.

### 8.1. Vendor JAR có sẵn, không có repository

~~~groovy
dependencies {
    implementation files('vendor/special-driver.jar')
}
~~~

Điều kiện nên có:
- File được đặt trong repository hoặc qua bước provision được kiểm soát.
- Hash, version, nguồn gốc, license và update policy được ghi nhận.
- Các transitive dependencies, nếu có, được khai báo tường minh.
- Không nhầm file JAR với output của một Gradle project trong cùng build.
- CI sạch có quyền truy cập cùng bytes.

Nếu có thể publish artifact vào Maven/Ivy repository nội bộ với metadata, **external module dependency** thường tốt hơn vì version, transitivity và provenance rõ.

### 8.2. Một thư viện là tập JAR cũ

~~~groovy
dependencies {
    runtimeOnly files(
        'vendor/driver-a.jar',
        'vendor/driver-b.jar'
    )
}
~~~

Cách này có thể dùng tạm cho legacy components. Nhưng cần kiểm soát update/version và không coi các files này là Maven modules; Gradle không thể tự giải quyết xung đột phiên bản dựa trên module coordinates của chúng.

### 8.3. fileTree cho nhiều files

~~~groovy
dependencies {
    runtimeOnly fileTree('vendor') {
        include '*.jar'
    }
}
~~~

**fileTree** tiện khi cần một tập artifacts, nhưng tài liệu Gradle lưu ý **thứ tự file trong FileTree không đảm bảo ổn định**, thậm chí trên cùng máy. Nếu thứ tự classpath quan trọng, sử dụng **files(...)** có thứ tự rõ hoặc repository/module dependencies.

**fileTree('lib/build/libs') không biến producer project thành dependency**. Nó chỉ thêm tất cả files matching pattern, có thể vô tình lấy JAR cũ, sources JAR, tests JAR hoặc nhiều versions.

### 8.4. File dependency không có dependency descriptor xuất bản

Tài liệu Gradle lưu ý local file dependencies **không được đưa vào dependency descriptor khi publish project**. Chúng có thể tham gia vào in-build dependency relations theo configuration rules, nhưng không trở thành tọa độ Maven cho users tải artifact ngoài build.

Đây là khác biệt quan trọng: **“file có mặt trong runtimeClasspath hiện tại”** không đồng nghĩa **“người tiêu thụ bản publish sẽ tự biết tải file ấy”**.

### 8.5. Tránh hardcode absolute path

Ví dụ:

~~~groovy
implementation files('/home/alice/work/lib/build/libs/lib.jar')
~~~

mang đường dẫn cá nhân, không portable sang Windows/CI. Ngay cả relative path cũng không giải quyết metadata/task graph. Với module nội bộ, dùng **project(':lib')**; với thư viện ngoài, dùng repository + coordinates khi có thể.

---

## 9. Khi chỉ cần một output đặc biệt của project khác

Không phải mọi project dependency đều nhằm sử dụng public Java library. Có khi project **:generator** tạo một ZIP, JSON schema bundle, native binary hoặc instrumented JAR để project **:consumer** đọc.

**Không nên mặc định lấy từ build/outputs bằng string.** Gradle hỗ trợ **outgoing consumable configurations**, **artifact variants** và attributes để producer công bố artifact có chủ đích, consumer lựa chọn qua configuration riêng.

### 9.1. Vai trò của configuration

| Configuration role | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Declarable / dependency scope** | Khai báo những dependencies cần dùng | implementation, customDeps |
| **Resolvable** | Resolve graph thành artifacts/files | compileClasspath, runtimeClasspath |
| **Consumable** | Producer công bố variants/artifacts | apiElements, runtimeElements, customElements |

Một configuration không nên bị lạm dụng làm đồng thời mọi vai trò; Gradle hiện đại khuyến khích phân tách rõ để tránh implicit behavior và variant ambiguity.

### 9.2. Producer công bố artifact tùy chỉnh

Ví dụ *fragment cấu hình nâng cao* trong **generator/build.gradle**, giả định có thư mục **assets/** để đóng gói. Gradle version hỗ trợ configuration role APIs mới:

~~~groovy
plugins {
    id 'base'
}

def bundleAssets = tasks.register('bundleAssets', Zip) {
    from('assets')
    archiveFileName = 'assets.zip'
    destinationDirectory = layout.buildDirectory.dir('dist')
}

def assetKind = Attribute.of('com.example.asset.kind', String)

configurations {
    consumable('assetBundleElements') {
        attributes {
            attribute(assetKind, 'zip')
            attribute(
                Usage.USAGE_ATTRIBUTE,
                objects.named(Usage, 'asset-bundle')
            )
        }
    }
}

artifacts {
    add('assetBundleElements', bundleAssets)
}
~~~

Các điểm:
- Producer có **task bundleAssets** tạo ZIP.
- Consumable configuration **assetBundleElements** công bố artifact.
- Attributes phân biệt loại artifact với Java API/runtime variants.
- **artifacts.add(..., TaskProvider)** giữ quan hệ với task sản xuất thay vì chỉ cung cấp string path.

Đây là ví dụ của **custom artifact variant**, không phải pattern để thay thế Java Library plugin khi cần bình thường **:lib** classes. Với project thực, kiểm tra tương thích attribute schema và Gradle Wrapper vì API mới có thể thay đổi theo version.

### 9.3. Consumer lựa chọn bằng attributes

Fragment ở **consumer/build.gradle**, giả định :generator đã được include ở settings và công bố variant như trên:

~~~groovy
plugins {
    id 'base'
}

def assetKind = Attribute.of('com.example.asset.kind', String)

configurations {
    dependencyScope('assetBundleDependencies')

    resolvable('assetBundleFiles') {
        extendsFrom(configurations.assetBundleDependencies)
        attributes {
            attribute(assetKind, 'zip')
            attribute(
                Usage.USAGE_ATTRIBUTE,
                objects.named(Usage, 'asset-bundle')
            )
        }
    }
}

dependencies {
    assetBundleDependencies project(':generator')
}

tasks.register('showAssetBundles') {
    inputs.files(configurations.assetBundleFiles)

    doLast {
        configurations.assetBundleFiles.files.each { file ->
            println file.name
        }
    }
}
~~~

Khi gọi **showAssetBundles**, Gradle resolve project dependency variant theo attributes, yêu cầu producer tạo output tương ứng và in tên file được chọn. **Không cần consumer biết generator/build/dist/assets.zip**.

Đây là fragment dành cho Gradle có **dependencyScope/resolvable/consumable** role APIs tương ứng. Tên usage **asset-bundle** là một giá trị custom phải được producer và consumer đồng nhất; nếu mismatch, variant selection có thể fail.

### 9.4. Vì sao không đặt phụ thuộc chéo vào tasks producer?

Một cách coupling chặt:

~~~groovy
tasks.named('processResources') {
    dependsOn ':generator:bundleAssets'
}
~~~

có thể ép một task chạy trước, nhưng không nêu **artifact nào được tiêu thụ**, path/version/attributes/variant nào phù hợp và không tự tạo FileCollection input chính xác cho Gradle up-to-date checks.

Outgoing variant là hợp đồng producer/consumer rõ hơn: producer công bố artifact, consumer yêu cầu loại phù hợp và task sử dụng cấu hình đã resolve.

### 9.5. Khi cần đúng một configuration theo tên

Gradle còn hỗ trợ project dependency chọn outgoing configuration cụ thể, chẳng hạn **project(path: ':generator', configuration: 'assetBundleElements')** trong một số legacy workflows. Tuy nhiên, chọn theo tên bỏ qua nhiều lợi ích variant-aware matching, có thể khó tiến hóa với nhiều variants. Khi thiết kế mới, ưu tiên consumable configuration có attributes và consumer resolvable configuration rõ.

### 9.6. Task outputs và builtBy

Nếu task tự tạo một FileCollection, một cách đúng khác là dùng **TaskProvider** hoặc task output providers làm input thay vì string path. Gradle theo dõi provenance và có thể tự tạo task dependency phù hợp. Trong **multi-project** build, **consumable variants** giữ sự đóng gói tốt hơn việc consumer trực tiếp truy cập task object của producer.

Không nên viết code lấy **project(':generator').tasks.named(...)** trong consumer chỉ để kéo artifact; cross-project task configuration tạo coupling và có thể cản trở các chế độ build hiện đại như isolated projects.

---

## 10. Runtime classpath, compile classpath và publishing

### 10.1. Một project dependency có thể expose các artifacts khác nhau

**:app:compileJava** cần API; **:app:run** cần runtime. Gradle có thể chọn variants/file sets khác nhau, nhưng cả hai đều dựa trên project dependency cùng một component.

**File path tới lib.jar** được đưa như một file ở configuration bạn chọn. Nó không thể tự trả lời “đây là API variant hay runtime variant?” và không mang graph từ lib/build.gradle.

### 10.2. api/implementation/runtimeOnly ảnh hưởng transitivity

Producer :lib khai báo:

~~~groovy
dependencies {
    api project(':api')
    implementation project(':engine')
}
~~~

Consumer:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

Compile sees :api; runtime sees :engine. Nếu lib có thêm **runtimeOnly project(':driver')**, runtimeClasspath của consumer có thể nhận driver dù compileClasspath không cần nó.

Ngược lại, consumer trỏ một file lib.jar không tự biết :driver. Người dùng có thể chạy ứng dụng và gặp **ClassNotFoundException/NoClassDefFoundError**.

### 10.3. Publishing metadata

Khi Java library được cấu hình **maven-publish** và artifacts/coordinates chính xác, project dependency có thể được phản ánh thành module dependencies thích hợp trong published metadata/POM. **api/implementation separation** cũng có ý nghĩa cho Maven compile/runtime scopes hoặc Gradle Module Metadata.

Ví dụ concept:

~~~text
Build nội bộ:
:app -> project(':lib') -> project(':api') / project(':engine')

Sau khi publish đúng cách:
consumer -> com.example:lib:1.0
            -> com.example:api:1.0
            -> com.example:engine:1.0
~~~

Đây là **mô hình ý tưởng**, không phải publishing configuration tự chạy. Để publish thật cần khai báo **group, version, maven-publish, publications, repository, credentials** và kiểm tra artifacts/metadata; project dependency một mình không tự upload gì.

File dependencies không được mang vào published dependency descriptor như coordinates, vì không có module identity.

### 10.4. Project dependency chỉ cho project trong build

**project(':lib')** yêu cầu :lib là một Gradle project được include trong build tương ứng. Nếu library nằm ở repository khác hoặc release độc lập, nên:

- Publish module có **group:name:version** rồi dùng external dependency, hoặc
- Dùng **composite build / includeBuild** với dependency substitution khi cần phát triển nhiều builds cùng nhau.

Đừng viết **project('../other-repository')** và hy vọng Gradle nhận đó là project path; project path không phải filesystem path.

### 10.5. Configuration names và Java compatibility

Project path phải đúng, nhưng còn phải có **compatible producer variant**. Nếu :lib chỉ công bố Java21 variant còn :app target Java17, resolution có thể fail. Đây là tín hiệu tốt: consumer không thể an toàn dùng bytecode quá mới.

File dependency có thể che incompatibility lúc resolution; lỗi chỉ lộ ở javac hoặc JVM runtime. Do đó “file path dễ hơn vì không báo no matching variant” không phải lý do hợp lý để sử dụng nó.

---

## 11. Build cache, incremental build và khả năng tái lập

### 11.1. Project dependency cung cấp task provenance

Gradle model hóa producer artifact outputs, task dependencies và dependency graph. Các tasks có thể:
- Chạy trước task consumer khi cần.
- Được đánh dấu UP-TO-DATE khi inputs/outputs không thay.
- Dùng build cache nếu task và inputs/outputs được cấu hình phù hợp.
- Không tạo JAR nếu consumer chỉ cần classes directory.
- Tối ưu incremental compilation theo API/implementation separation.

Không có nghĩa “mọi project dependency đều tự động cacheable”; task caching còn phụ thuộc annotation inputs/outputs, reproducibility, plugin version và environment.

### 11.2. File dependency không mặc nhiên phá build cache

Một file dependency **vẫn có thể là input được Gradle snapshot** và có thể tham gia vào cache key nếu task dùng file collection đúng cách. Vấn đề chính không phải “file dependency cấm cache”; mà là **file path thiếu producer metadata/task provenance và module dependency graph**.

Một stale lib.jar có thể được tính hash chính xác nhưng **vẫn là bản cũ** so với source code hiện tại, do consumer không biết phải rebuild producer.

### 11.3. Tính reproducible từ clean checkout

Một kiểm tra quan trọng:

~~~bash
./gradlew :api:clean :engine:clean :lib:clean :app:clean
./gradlew :app:run
~~~

Với project dependency, Gradle có thể tái tạo outputs từ source. Với file dependency, nếu app chỉ trỏ JAR trong lib/build/libs và JAR chưa có, build thất bại cho tới khi người dùng tự tạo artifact.

CI nên có job thực hiện clean checkout có kiểm soát và entrypoint **:app:build** / **:app:run** đúng để phát hiện những task dependencies bị thiếu.

### 11.4. Configuration cache và isolated projects

Modern Gradle khuyến khích cấu hình task lazily và tránh trực tiếp đọc/cấu hình internals của project khác trong build scripts. **project(':lib')** là một dependency model được Gradle quản lý, không đồng nghĩa truy cập trực tiếp object/tasks của lib theo cách tùy tiện.

Khi share artifacts custom, thiết kế consumable/resolvable configurations giúp giảm cross-project coupling. Tránh đặt các đoạn đoán path hoặc truy cập task provider xuyên project nếu đã có API dependency thích hợp.

### 11.5. Thay đổi project layout

Nếu đổi archiveBaseName, version hoặc destinationDirectory của producer, project dependency vẫn dùng variant metadata để lấy output mới. File dependency trỏ chuỗi **build/libs/lib.jar** cần sửa thủ công hoặc sẽ dùng bản sai.

Tương tự nếu project directory được remap trong settings, **project path** có thể giữ ổn định, còn relative artifact path lại đổi.

---

## 12. Kotlin DSL tương đương

### 12.1. settings.gradle.kts

~~~kotlin
rootProject.name = "multi-project-lab"
include("api", "engine", "lib", "app")
~~~

### 12.2. lib/build.gradle.kts

~~~kotlin
plugins {
    \`java-library\`
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

dependencies {
    api(project(":api"))
    implementation(project(":engine"))
}
~~~

**Lưu ý cú pháp:** Trong một file Kotlin DSL thực, dòng plugin được viết bằng **id("java-library")** hoặc accessor Kotlin phù hợp. Để tránh khác biệt render của Markdown, bạn có thể dùng dạng đầy đủ sau (tương đương và độc lập):

~~~kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

dependencies {
    api(project(":api"))
    implementation(project(":engine"))
}
~~~

### 12.3. app/build.gradle.kts

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

dependencies {
    implementation(project(":lib"))
}

application {
    mainClass = "demo.app.Main"
}
~~~

Phương án file path trong Kotlin:

~~~kotlin
dependencies {
    implementation(files("../lib/build/libs/lib.jar"))
}
~~~

Nó vẫn có những hạn chế về task graph, metadata, transitive dependencies và portability như Groovy DSL, không an toàn hơn chỉ vì Kotlin có type checking.

### 12.4. Type-safe project accessors

Một số Gradle builds dùng:

~~~kotlin
dependencies {
    implementation(projects.lib)
}
~~~

API type-safe project accessors từng được Gradle đánh dấu incubating và có yêu cầu cấu hình feature preview tùy phiên bản. Khi chưa thiết lập, dùng **project(":lib")** là cách ngắn, phổ biến và rõ nghĩa. Đừng coi **projects.lib** là một Maven coordinate hoặc đường dẫn file.

### 12.5. Kotlin DSL không thay đổi bản chất dependencies

Dù cú pháp là **implementation project(':lib')** (Groovy) hay **implementation(project(":lib"))** (Kotlin), Gradle vẫn có **ProjectDependency** và variant-aware graph. Dù syntax là **files('../lib/...')** trong Groovy/Kotlin, file vẫn không có thông tin module producer để Gradle tự hiểu.

---

## 13. Debug chính xác lỗi project vs file

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý đúng |
| --- | --- | --- |
| **Project with path ':lib' could not be found** | Chưa include hoặc path sai | Kiểm tra settings.gradle và project name |
| **No matching variant** | Consumer attributes không tương thích producer | Xem outgoingVariants, resolvableConfigurations, Java target |
| **compileJava không thấy Greeter** | App dùng file path nhưng lib.jar chưa có | Đổi sang project(':lib'), không chỉ chạy jar một lần |
| **cannot access Greeting** | File lib.jar thiếu api.jar | Dùng project dependency để nhận api transitive |
| **NoClassDefFoundError TextFormatter** | Runtime thiếu engine.jar | Dùng project dependency hoặc khai báo runtime deps có metadata |
| **App chạy bản code cũ** | JAR path trỏ artifact từ build trước | Loại file dependency tới build/libs |
| **:lib:jar không chạy khi compile app** | Gradle chọn classes secondary variant | Hành vi có thể đúng; kiểm tra compilation/output |
| **FileTree lấy nhiều JAR không dự kiến** | Pattern quá rộng, JAR cũ/test jars | Dùng exact dependencies hoặc artifact variants |
| **Build thành công trên máy dev, fail CI sạch** | JAR chỉ tồn tại local | Kiểm tra clean checkout/task graph, sửa dependency model |
| **Báo lỗi Java class file version** | Producer dùng Java mới hơn consumer | Align Java toolchain/release, đừng ẩn variant compatibility |
| **External package không có khi publish** | File dependencies không vào descriptor | Publish dependency có coordinates/metadata |
| **Task dependency implicit missing** | FileCollection không có producer info | builtBy với generated file, hoặc project dependency |
| **Consumer cần ZIP custom, không dùng JAR** | Chưa có outgoing consumable artifact | Tạo variant/configurations riêng |
| **Project variant ambiguity** | Producer có nhiều variants attributes tương tự | Dùng attributes rõ, inspect outgoingVariants |
| **Implementation dependency bị leak vào compile API** | Producer dùng api quá rộng hoặc manual jars | Chỉnh api/implementation đúng public ABI |
| **Compilation của app kéo jar dù không cần** | Explicit dependsOn :lib:jar | Bỏ manual order, dùng project dependency |
| **Circular dependency** | :lib phụ thuộc :app trong khi :app phụ thuộc :lib | Xem project graph, tách common API/module |
| **Kotlin accessors chưa tồn tại** | Type-safe project accessors không bật/version khác | Dùng project(":lib") và xem settings |
| **Composite build không resolve bằng project(':other')** | Other build không thuộc project paths | Dùng published module hoặc includeBuild |
| **CI checksum không kiểm soát local JAR** | File không có repository provenance | Publish vào repo đáng tin hoặc kiểm hash/provenance ngoài |

### 13.1. Lệnh chẩn đoán nên thuộc

~~~bash
./gradlew projects
./gradlew :lib:outgoingVariants
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency lib --configuration runtimeClasspath
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:compileJava --dry-run
./gradlew :app:run --info
~~~

**--dry-run** chỉ cho biết tasks dự kiến được lập lịch, không tạo artifacts và không chứng minh compilation/runtime pass. **dependencyInsight** hữu ích khi dependency được Gradle nhận diện thành module/project; với file dependencies chỉ có đường dẫn, thông tin reason/coordinate có thể hạn chế.

### 13.2. Tìm nơi khai báo dependency sai

Trong build scripts của app, kiểm tra:

- Có **implementation project(':lib')** không?
- Có **implementation files('../lib/build/libs/lib.jar')** không?
- Có fileTree trỏ sang outputs của project khác không?
- Có manual **dependsOn ':lib:jar'** mà không có dependency graph không?
- Có duplicate paths vừa project dependency vừa file dependency cùng thư viện không?
- Có hardcoded absolute OS paths hoặc archive names không?

Một consumer vừa khai báo **project(':lib')** vừa thêm **lib.jar** có thể đưa cùng classes lên classpath hai lần, gây warning/behavior khó hiểu và làm giảm lợi ích variant-aware dependencies. Chọn một quan hệ rõ, tránh trùng.

### 13.3. Đọc task graph thật

Dùng:

~~~bash
./gradlew :app:run --dry-run
~~~

để quan sát producer compilation tasks có được kéo vào graph không. Sau đó chạy **:app:run** thật và kiểm tra stdout. Không đánh giá chỉ qua sự có mặt của **:lib:jar**; Gradle có thể chọn classes directory hợp lệ.

### 13.4. Xem JVM target của variants

Trong **:lib:outgoingVariants**, tìm **org.gradle.jvm.version** và usage. Nếu producer yêu cầu Java21 nhưng consumer target17, giải quyết tại compile release/toolchain, không tắt compatibility checking bằng file path.

---

## 14. Bài tập có đáp án

### Bài 1 — Hai cách khai báo có tương đương không?

~~~groovy
implementation project(':lib')
implementation files('../lib/build/libs/lib.jar')
~~~

**Đáp án:** không. Project dependency mang metadata/variants/task provenance; file dependency chỉ trỏ tới path. Hai dòng thêm cả hai có thể gây classpath trùng.

### Bài 2 — Project path được khai báo ở đâu?

**Đáp án:** **settings.gradle(.kts)** bằng **include(...)**, không lấy từ đường dẫn JAR.

### Bài 3 — Vì sao compile app không chạy :lib:jar?

**Đáp án:** Gradle Java Library plugin có thể cung cấp classes directory variant cho compile; việc không tạo JAR không tự chứng minh lỗi.

### Bài 4 — Tại sao file path không chạy task producer?

**Đáp án:** Gradle không biết file build/libs/lib.jar là output của :lib:jar nếu chỉ nhìn string path. Dùng project dependency hoặc FileCollection có task producer/builtBy khi hợp lý.

### Bài 5 — Project dependency có phải tự động tạo fat JAR?

**Đáp án:** không. Nó có thể giải quyết transitive dependencies vào classpath, nhưng standard Jar task không đóng mọi dependency JAR vào cùng artifact. Fat/shaded JAR là cấu hình riêng.

### Bài 6 — api và implementation khác nhau thế nào?

**Đáp án:** api expose dependencies cần cho public interface/API; implementation giữ dependencies nội bộ ngoài consumer compile classpath nhưng vẫn phục vụ runtime phù hợp.

### Bài 7 — Trong lab :lib.api project(':api') có ý nghĩa gì?

**Đáp án:** public method Greeter.forPerson trả về type Greeting thuộc :api, nên app compiler cần thấy :api trên compileClasspath.

### Bài 8 — Trong lab :lib.implementation project(':engine')?

**Đáp án:** TextFormatter chỉ dùng trong lambda body/internal logic, không xuất hiện ở public ABI; runtime vẫn cần :engine.

### Bài 9 — Dùng chỉ lib.jar, app fail không thấy Greeting?

**Đáp án:** JAR lib không chứa tự động api.jar; file dependency không có transitive metadata. Project dependency giải quyết đúng api variant.

### Bài 10 — Dùng api.jar và lib.jar, runtime thiếu engine.jar?

**Đáp án:** compile có thể pass vì public API đủ, nhưng gọi TextFormatter có thể gây NoClassDefFoundError. Cần runtime graph, không chỉ compile files.

### Bài 11 — Stale artifact là gì?

**Đáp án:** file build/libs còn từ build cũ; consumer file dependency vẫn dùng bytes ấy dù source module producer thay. Thiếu task provenance làm lỗi khó phát hiện.

### Bài 12 — Thêm dependsOn :lib:jar có giải quyết mọi vấn đề?

**Đáp án:** không. Có thể giải quyết task ordering hẹp nhưng không mang api/runtime graph, variants, metadata, publishing. Đổi sang project(':lib').

### Bài 13 — File dependency có bao giờ đúng?

**Đáp án:** có, cho một local vendor artifact độc lập được kiểm soát version/hash/nguồn gốc và không có repository phù hợp, hoặc output task có builtBy. Không nên dùng nó thay project dependency nội bộ.

### Bài 14 — Khi nào dùng outgoing consumable configuration?

**Đáp án:** khi muốn project khác lấy một ZIP/binary/custom artifact thay vì Java library API; producer xuất variant có attributes, consumer resolve phù hợp và không cần hardcode build path.

### Bài 15 — Khi publish library, file deps có vào Maven POM không?

**Đáp án:** local file dependencies không được đưa như coordinates vào published dependency descriptor. Dùng module dependency có metadata/publishing phù hợp nếu users ngoài build phải tải chúng.

### Bài 16 — type-safe project accessors có thay đổi semantics không?

**Đáp án:** không. **projects.lib** nếu feature được bật vẫn là một project dependency, không phải một file path.

### Bài 17 — Classpath của :app cần module nào khi compile và runtime?

**Đáp án:** compile cần :lib và :api; runtime cần :lib, :api và :engine. Đây là ý nghĩa của api/implementation separation trong lab.

### Bài 18 — Vì sao project dependency thường tốt hơn cho CI?

**Đáp án:** Gradle hiểu graph và các producer outputs, có thể lập lịch tasks từ clean checkout, chọn variants phù hợp và giảm phụ thuộc vào artifacts cũ trên máy dev.

### Bài 19 — FileTree có đảm bảo thứ tự classpath ổn định?

**Đáp án:** không. Gradle docs cảnh báo thứ tự FileTree có thể không ổn định; dùng explicit files hoặc module/project dependencies khi ordering/reproducibility quan trọng.

### Bài 20 — Project trong repo khác thì dùng project(':other')?

**Đáp án:** chỉ khi project path thật sự thuộc build; với separate build dùng publishing coordinates hoặc composite builds/includeBuild theo đúng thiết kế, không coi filesystem path là project name.

---

## 15. Checklist trước khi merge

- [ ] Dependency liên project có dùng **project(':...')** thay vì đường dẫn **../other/build/libs/*.jar**?
- [ ] Mọi project paths đã được include trong settings?
- [ ] Producer là **java-library** khi công bố Java library API?
- [ ] Public ABI dependencies đã khai báo **api** đúng?
- [ ] Internal deps dùng **implementation** và runtime-only deps đúng scope?
- [ ] Consumer compile/runtime classpaths có đủ dependencies phù hợp?
- [ ] Các outgoing variants mang đúng usage/libraryElements/JVM version?
- [ ] Không hardcode JAR output directory hoặc archive filename khi cần code module khác?
- [ ] Không yêu cầu jar task dư thừa nếu compile có thể dùng classes variant?
- [ ] Không dùng manual dependsOn như một thay thế cho project dependency?
- [ ] Khi dùng file thật sự sinh tự động, có task provenance/builtBy phù hợp?
- [ ] Khi cần custom artifacts, producer có consumable configuration/variant rõ?
- [ ] Không có dependency trùng cả project(':lib') và files('lib.jar')?
- [ ] File dependencies còn lại có provenance/hash/version/license và CI availability?
- [ ] Published metadata có đủ external/project dependencies sau khi publish?
- [ ] Không giả định file dependency có Maven/Gradle Module Metadata tự động?
- [ ] Clean checkout chạy được app:run/build mà không cần bước build JAR bằng tay?
- [ ] Dự án chạy đúng JVM phiên bản được tuyên bố hỗ trợ?
- [ ] Không che Java variant mismatch bằng việc chèn JAR trực tiếp?
- [ ] Dependency graph đã xem bằng dependencies/dependencyInsight/outgoingVariants?
- [ ] Có chạy lab/test thực tế, không chỉ dùng --dry-run?
- [ ] CI và máy developer cùng dùng Gradle Wrapper và Java toolchain policy?
- [ ] Không vô tình kéo packages nội bộ vào consumer compile API?
- [ ] Thay đổi liên module không phá incremental build hoặc gây stale outputs?

## Tài liệu chính thức của Gradle

- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): phân biệt module/project/file dependencies, file dependency limitations, builtBy và type-safe project accessors.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): project paths, dependency graph và cách dùng output của project khác.
- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): producer/consumer attributes, apiElements/runtimeElements và classes artifact sets.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation separation, runtime/compile variants, classes vs JAR.
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): declarable/resolvable/consumable roles và custom configurations.
- [Gradle — How to Share Artifacts Between Projects](https://docs.gradle.org/current/userguide/how_to_share_outputs_between_projects.html): consumable artifact variants, dependencies trên producer outputs và custom artifact selection.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): compileJava/classes/jar tasks, configurations.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): task run và mainClass.
- [Gradle — Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle JVM/toolchain version support.

**Kết luận:** Với modules Java nằm trong cùng multi-project Gradle build, **implementation project(':lib')** mô tả quan hệ phụ thuộc thực sự: Gradle hiểu variants, transitive API/runtime dependencies, Java compatibility và các task tạo outputs. **implementation files('../lib/build/libs/lib.jar')** chỉ là một đường dẫn file, thiếu metadata/task provenance, dễ gây stale outputs và lỗi clean CI. Khi thật sự cần một artifact tùy chỉnh, hãy công bố **consumable artifact variant** hoặc dùng FileCollection có producer rõ; đừng biến đường dẫn trong thư mục build thành một API giữa các projects.