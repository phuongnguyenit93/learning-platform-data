# Scala, Groovy và cách plugin ngôn ngữ mở rộng mô hình build

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Hệ sinh thái Gradle

## Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

1. Phân biệt **Groovy DSL** của Gradle với ngôn ngữ **Groovy** dùng trong source code và **groovy Gradle plugin** chuyên biên dịch source Groovy.
2. Giải thích cơ chế các language plugins mở rộng **Java plugin model** bằng source sets, configurations, compile tasks, classpaths, lifecycle tasks, documentation tasks và toolchains.
3. Dùng core plugin **id 'scala'** và **id 'groovy'**; nhận biết chúng không phải external Gradle plugins cần Plugin Portal markers.
4. Tìm hiểu **compileScala**, **compileTestScala**, **scaladoc**, **compileGroovy**, **compileTestGroovy**, **groovydoc**, **compileJava**, **classes**, **testClasses**, **jar** và **check**.
5. Hiểu layout src/main/scala, src/main/groovy, src/main/java và quy tắc **joint compilation** Java/Scala, Java/Groovy.
6. Thiết lập **Scala version**, **Scala SDK/compiler**, **Zinc incremental compiler**, **scalaCompilerPlugins**, Groovy runtime/compiler classpath và Java 17 toolchain.
7. Phân biệt **java.toolchain** với **Scala compiler toolchain/configurations**; hiểu các Scala binary artifacts có suffix _2.13, _3 và rủi ro binary compatibility.
8. Dùng **java-library api/implementation separation** để quyết định có expose language-specific runtime types hay che qua Java façade.
9. Tự dựng và chạy được lab **Gradle Groovy DSL + Java 17** ba modules: scala-lib, groovy-lib, app; Java source và Scala/Groovy source biên dịch joint, Java app gọi cả hai libraries.
10. Kiểm tra kết quả bằng Java 17 **AppCheck** và chương trình **javac/java VerifyOutput** với stdout chính xác.
11. Chẩn đoán lỗi thiếu compiler/runtime classpath, sai Scala/Groovy version, source file sai thư mục, compile cycle, runtime NoClassDefFoundError, IDE sync, incremental compilation và caches.
12. Phân biệt **groovy-gradle-plugin** tạo precompiled Groovy DSL convention plugins với **groovy** compile plugin của ứng dụng.
13. Biết khi nào chọn compiler flags, AST transformations, Scala compiler plugins và incremental options; không áp thử nghiệm hoặc override bytecode target tùy tiện.
14. Đọc đúng documentation/reporting commands từ Gradle, đo tính đúng và tốc độ trên multi-language build.

**Ý chính:** Ngôn ngữ của **build script** và ngôn ngữ của **source code** là hai trục độc lập. Plugin ngôn ngữ mới thực sự thêm source sets, tasks, compilation graph, classpaths và đầu ra vào Gradle build model. Cấu hình đúng **source ownership, compiler libraries, runtime variants và toolchains** quan trọng hơn việc chọn Groovy hay Kotlin để viết build.gradle.

## 1. Ba nghĩa của “Groovy” cần tách bạch

| Thuật ngữ | Vai trò | Ví dụ |
|---|---|---|
| **Groovy DSL** | Cú pháp cấu hình Gradle | build.gradle, settings.gradle |
| **Groovy language** | Ngôn ngữ source chạy trên JVM | src/main/groovy/.../Greeter.groovy |
| **Groovy plugin** | Core Gradle plugin compile source Groovy | plugins { id 'groovy' } |
| **Groovy runtime/compiler** | Maven dependency phục vụ app và compiler | org.apache.groovy:groovy:4.0.24 |
| **groovy-gradle-plugin** | Core plugin hỗ trợ viết precompiled Gradle script plugins | build-logic/src/main/groovy/*.gradle |

Ví dụ một build script sau dùng **Groovy DSL** nhưng project không cần Groovy source compiler:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Không có compileGroovy chỉ vì file được đặt tên build.gradle. Để Gradle compile .groovy:

~~~groovy
plugins {
    id 'groovy'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.groovy:groovy:4.0.24'
}
~~~

Groovy plugin là core plugin **mở rộng Java plugin**, còn Maven artifact là thư viện ngôn ngữ trên classpath. Trong khi đó một build.gradle.kts viết bằng Kotlin DSL vẫn có thể áp:

~~~kotlin
plugins {
    groovy
}
~~~

Đó vẫn là project Groovy, chỉ khác DSL cấu hình. Tương tự project Scala có thể dùng build.gradle hoặc build.gradle.kts.

### 1.1. Scala ở đâu?

**Scala** là ngôn ngữ JVM riêng, có compiler và standard library. Gradle cung cấp **core Scala plugin**:

~~~groovy
plugins {
    id 'scala'
}
~~~

Plugin tạo tasks ScalaCompile/ScalaDoc và conventions cho Scala sources. **Không có Scala DSL chuẩn thay thế Groovy/Kotlin DSL trong ví dụ này**: Scala là ngôn ngữ của chương trình được biên dịch, không phải một Gradle plugins syntax.

~~~text
          Build configuration syntax
           /                   \
     Groovy DSL             Kotlin DSL
           \                   /
              Gradle Project
                   |
             Applied plugins
        +----------+----------+
        |          |          |
       java       scala      groovy
        |          |          |
   JavaCompile ScalaCompile GroovyCompile
        |          |          |
        +----------+----------+
                   |
             outputs / JARs
                   |
              JVM runtimes
~~~

## 2. Language plugin thay đổi Gradle model như thế nào?

Không có plugin Java/JVM, Gradle project vẫn có repositories, tasks, configurations và extensions. Một language plugin giúp biến các thành phần đó thành **mô hình build có ngữ nghĩa cho ngôn ngữ**:

1. Tạo **source sets** main/test và language-specific source directory sets.
2. Định nghĩa **compileClasspath**, **runtimeClasspath**, test classpaths và compiler tool classpaths.
3. Đăng ký **compile tasks** trên mỗi source set, với source, destination directory, compiler options và input/output tracking.
4. Nối compiler outputs vào **SourceSetOutput** và component artifacts/variants.
5. Nối **compile tasks** vào lifecycle tasks như **classes** và **testClasses**.
6. Gắn các task run/test/jar/doc vào mô hình dependencies/variants.
7. Cho phép IDE Tooling API đọc source roots, tasks, toolchains và dependencies.
8. Dùng up-to-date checks, incremental compilation, build cache khi task phù hợp.

**Không có nghĩa áp plugin tự động tạo ra code đúng.** Compiler dependencies, file layout, Java version và source/API vẫn do người phát triển quản lý.

### 2.1. Bảng task bổ sung

| Mô hình | Java plugin | Scala plugin | Groovy plugin |
|---|---|---|---|
| Source Java main | src/main/java | Giữ nguyên | Giữ nguyên |
| Source ngôn ngữ | — | src/main/scala | src/main/groovy |
| Test source ngôn ngữ | — | src/test/scala | src/test/groovy |
| Compile production | compileJava | compileScala | compileGroovy |
| Compile tests | compileTestJava | compileTestScala | compileTestGroovy |
| API documentation | javadoc | scaladoc | groovydoc |
| Compiler | javac | Scala compiler / Zinc | Groovy compiler |
| Classes lifecycle | classes | Thêm compileScala | Thêm compileGroovy |
| Test classes lifecycle | testClasses | Thêm compileTestScala | Thêm compileTestGroovy |

ScalaCompile và GroovyCompile **phụ thuộc compileJava theo conventions**. Những Java source files nằm trong **language-specific directories** có thể được compiler tương ứng compile jointly, khác Java files trong src/main/java.

### 2.2. Source-set model

~~~text
sourceSets.main
  +-- java      -> src/main/java
  +-- resources -> src/main/resources
  +-- scala     -> src/main/scala (nếu áp scala plugin)
  +-- groovy    -> src/main/groovy (nếu áp groovy plugin)

sourceSets.test
  +-- java      -> src/test/java
  +-- resources -> src/test/resources
  +-- scala     -> src/test/scala (nếu có)
  +-- groovy    -> src/test/groovy (nếu có)
~~~

**Có thể áp cả scala và groovy trong một project**, nhưng khi classes giữa hai compiler phụ thuộc vòng lẫn nhau, cần thiết kế classpath/compiler graph rõ, không mong Gradle tự giải một compiler cycle. Trong thực hành, tách modules Scala và Groovy với public Java APIs thường đơn giản hơn.

### 2.3. Tasks là đơn vị có đầu vào/đầu ra

Gradle không chỉ chạy một câu lệnh scalac hoặc groovyc bằng một Exec task tùy tiện. ScalaCompile/GroovyCompile tasks cung cấp:
- Input source file collections.
- Compile classpath và compiler-specific classpath.
- Destination directory.
- Compiler options, target/version.
- Java toolchain integration.
- Incremental state và task outputs.
- Task dependency wiring từ upstream project libraries.

**Nếu tự tạo Exec task gọi compiler**, bạn phải tự khai task inputs/outputs, compiler dependencies, source sets và build cache behavior. Dùng core language plugins tránh nhiều lỗi task modeling.

## 3. Scala plugin: compiler và Zinc

### 3.1. Cấu hình Scala 2.13

Ví dụ Groovy DSL từ Gradle hiện hành:

~~~groovy
plugins {
    id 'scala'
}

repositories {
    mavenCentral()
}

scala {
    scalaVersion = '2.13.12'
}
~~~

**scalaVersion** là API được tài liệu Gradle 9.9 đánh dấu **incubating**. Khi được cấu hình, Gradle thêm Scala compiler/SDK dependencies vào **scalaToolchain** và lập **scalaToolchainRuntimeClasspath** cần thiết để chạy compiler. Không nhất thiết tự khai implementation scala-library nếu đã dùng scalaVersion theo API hiện hành.

**Không nhầm Scala toolchain với Java toolchain.** Scala toolchain ở đây là compiler/SDK artifacts; Java toolchain là JDK compiler/launcher/version/vendor.

### 3.2. Scala 3

Có thể thay cấu hình phiên bản bằng:

~~~groovy
scala {
    scalaVersion = '3.6.3'
}
~~~

Gradle Scala plugin hỗ trợ Scala 3. Nhưng **Scala 2.13 và Scala 3 không tự tương thích với mọi library**, đặc biệt macro/compiler plugins và binary artifact suffix. Cần kiểm thư viện thực sự xuất bản artifact **_3**, **_2.13** hoặc metadata compatibility rõ ràng.

### 3.3. Scala tasks

| Task | Kiểu | Mục đích |
|---|---|---|
| compileScala | ScalaCompile | Scala production và Java trong Scala source dirs |
| compileTestScala | ScalaCompile | Scala tests |
| scaladoc | ScalaDoc | API docs Scala |
| compileSourceSetScala | ScalaCompile | Scala source set tùy tên |
| classes | Lifecycle | Phụ thuộc compileScala cùng Java sources |
| testClasses | Lifecycle | Phụ thuộc compileTestScala cùng test Java sources |

**Task compileScala phụ thuộc compileJava** theo default Java/Scala wiring. Dùng:

~~~bash
./gradlew :scala-lib:tasks --all
./gradlew :scala-lib:compileScala --dry-run
~~~

để nhìn tasks của dự án thực.

### 3.4. Scala source directories

~~~text
src/main/scala/       Scala và có thể Java, joint compile
src/main/java/        Java do compileJava xử lý
src/main/resources/   resources
src/test/scala/       Scala tests và Java joint test sources
src/test/java/        Java tests do compileTestJava xử lý
~~~

Scala code trong src/main/scala có thể gọi class Java đã được compile trong src/main/java. Nhưng Java source trong src/main/java **không mặc nhiên** gọi được Scala class chỉ mới được compile sau đó. Nếu cần Java↔Scala dependencies hai chiều trong cùng compile unit, đặt Java liên quan ở **src/main/scala** cho joint compilation, hoặc tách một Java API project.

### 3.5. Zinc incremental compiler

Gradle Scala plugin dùng **Zinc** làm incremental Scala compiler backend:
- Gradle có configuration **zinc**.
- Với Gradle hiện đại, Zinc sử dụng module family **org.scala-sbt:zinc_2.13**.
- Zinc backend dùng Scala runtime riêng khi cần, có thể không trùng đúng Scala SDK version của application.
- Incremental ScalaCompile có thể chỉ recompile affected classes, không mặc định compile toàn bộ source mỗi lượt.
- Compiler chạy external process, có memory/fork JVM options.
- Một thay đổi public API upstream có thể kéo theo downstream recompilation.

Điều tra:

~~~bash
./gradlew :scala-lib:dependencies \
  --configuration zinc --console=plain

./gradlew :scala-lib:dependencyInsight \
  --dependency zinc \
  --configuration zinc --console=plain
~~~

### 3.6. Scala compiler plugins không phải Gradle plugins

~~~groovy
dependencies {
    scalaCompilerPlugins(
        'org.typelevel:kind-projector_2.13.12:0.13.2'
    )
}
~~~

Đây là **snippet minh họa dependency configuration** theo Scala plugin docs, không phải yêu cầu của lab. Nó tải compiler plugin cho scalac, khác hẳn:

~~~groovy
plugins {
    id 'scala'
}
~~~

Gradle plugin ID ở plugins block làm thay đổi Gradle model; Scala compiler plugin thêm biến đổi/hỗ trợ compiler khi compile source Scala.

### 3.7. Zinc version và target bytecode

Ví dụ override khi thực sự cần:

~~~groovy
scala {
    scalaVersion = '2.13.12'
    zincVersion = '1.12.0'
}
~~~

Không cần override zincVersion mặc định trong lab. Nếu thay version:
- Kiểm compatibility matrix trong Scala plugin docs.
- Kiểm Scala 2/3 compiler support.
- Kiểm JDK/toolchain target.
- Kiểm compiler plugin versions.

Với Scala plugin phiên hiện hành, Java toolchain có thể được dùng để suy ra Scala target/release compiler flags. **Tự đặt -target hoặc -release trong scalaCompileOptions.additionalParameters có thể override suy luận mặc định**. Chỉ đặt rõ khi đã kiểm supported Scala version/JDK matrix.

## 4. Groovy plugin: compiler classpath và AST

### 4.1. Cấu hình Groovy application source

~~~groovy
plugins {
    id 'groovy'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.groovy:groovy:4.0.24'
}
~~~

**org.apache.groovy** là group Groovy 4+; ví dụ Gradle docs cũ có thể dùng **org.codehaus.groovy** cho Groovy 2.x. **4.0.24** là version pin để học, không phải tuyên bố bản mới nhất.

### 4.2. Vì sao không dùng Groovy từ Gradle DSL?

Gradle distribution chứa Groovy phục vụ Groovy DSL, nhưng **ứng dụng production cần khai runtime/compiler dependency** trên classpath phù hợp. Nếu chỉ code test bằng Groovy, testImplementation có thể đủ; nếu code sản phẩm viết Groovy, khai implementation hoặc api theo public API contract.

~~~groovy
dependencies {
    implementation localGroovy()
}
~~~

**localGroovy()** phụ thuộc Groovy embedded trong Gradle distribution, có thể hữu ích khi phát triển Gradle plugins nhưng không phải lựa chọn mặc định cho application production vì nâng Wrapper có thể đổi version runtime Groovy.

### 4.3. Groovy task/model

| Task | Kiểu | Trách nhiệm |
|---|---|---|
| compileGroovy | GroovyCompile | Compile Groovy/Java production trong Groovy dirs |
| compileTestGroovy | GroovyCompile | Compile Groovy tests |
| groovydoc | Groovydoc | Groovy API docs |
| compileJava | JavaCompile | Java trong src/main/java |
| classes | Lifecycle | Gồm compileGroovy |
| testClasses | Lifecycle | Gồm compileTestGroovy |

Groovy source dirs:

~~~text
src/main/groovy/       .groovy và .java
src/main/java/         .java
src/test/groovy/       .groovy và .java
src/test/java/         .java
~~~

### 4.4. GroovyCompile có hai classpaths

- **classpath**: libraries/classes dùng khi compile source.
- **groovyClasspath**: libraries để **chạy Groovy compiler**.

Gradle cố suy ra groovyClasspath từ Groovy library có trên classpath nếu không set explicit. Một lỗi “Cannot infer Groovy class path” thường là thiếu hoặc sai Groovy compiler library/version, **không phải vì chưa tạo thêm một compileGroovy task thủ công**.

### 4.5. Groovy AST transformations

Groovy có các compiler transformations như:
- **@CompileStatic**: tăng mức static checking/generate calls rõ hơn.
- **@Immutable**: hỗ trợ tạo immutable class convention.
- Custom AST transformations: có thể đọc extra classpath/resources.

Ví dụ:

~~~groovy
package demo.example

import groovy.transform.CompileStatic

@CompileStatic
class SimpleGreeter {
    String hello(String name) {
        return 'Groovy: ' + name.trim() + '!'
    }
}
~~~

**@CompileStatic không biến Groovy thành Java**. Mã vẫn cần Groovy compiler/runtime hoặc generated bytecode dependencies phù hợp. Custom transformations có thể tác động compiler incremental correctness, nên cần model **astTransformationClasspath** và inputs nếu được dùng.

### 4.6. Groovy incremental compilation/avoidance

Gradle hỗ trợ các tính năng Groovy incremental/compilation avoidance, nhưng một số cơ chế được tài liệu đánh dấu **incubating/experimental** theo phiên. Đừng lấy flags của một Gradle guide cũ áp mặc định cho Gradle phiên khác.

Nếu muốn dùng AST transformation classpath:

~~~groovy
configurations {
    astTransformation
}

dependencies {
    astTransformation project(':ast-transformation')
}

tasks.withType(GroovyCompile).configureEach {
    astTransformationClasspath.from(
        configurations.astTransformation
    )
}
~~~

Đây là **snippet minh họa** chỉ dùng nếu có project :ast-transformation thật và version hỗ trợ. Không chèn vào lab baseline.

## 5. Java ↔ Scala/Groovy joint compilation

### 5.1. Quy tắc thứ tự

~~~text
src/main/java/*.java --> compileJava
                             |
                             v
src/main/scala/*.scala --> compileScala
  (có thể chứa .java joint)

src/main/java/*.java --> compileJava
                             |
                             v
src/main/groovy/*.groovy --> compileGroovy
  (có thể chứa .java joint)
~~~

Nếu Java source ở src/main/java gọi một Groovy class chỉ được tạo trong compileGroovy, **compileJava có thể fail** vì compiler chưa nhìn thấy class. Không sửa bằng cách thêm dependsOn đảo chiều tạo compiler cycle.

### 5.2. Ba giải pháp

1. **Joint compilation**: đặt Java classes cần tham chiếu Scala/Groovy trong src/main/scala hoặc src/main/groovy, dùng language compiler support.
2. **Tách Java API module**: :api chứa interfaces/DTOs thuần Java, :scala-impl và :groovy-impl phụ thuộc :api, :app tiêu thụ APIs.
3. **Một chiều rõ ràng**: Java src/main/java không dùng Scala/Groovy classes, Scala/Groovy source có thể dùng Java compiled outputs.

Với số lượng source lớn và nhiều language variants, giải pháp **API module độc lập** thường dễ test/publish hơn.

### 5.3. Public API và java-library

Nếu Groovy library expose Groovy class trực tiếp, Java consumer compiler có thể cần **groovy.lang.GroovyObject** trên compileClasspath. Khi public APIs thực sự expose Groovy/Scala-specific types, dùng **api dependencies** cần thiết.

Một lựa chọn khác là public **pure Java façade**:

~~~text
Java app
    |
    | calls String -> String Java APIs
    v
  ScalaFacade.java        GroovyFacade.java
        |                         |
        v                         v
  ScalaGreeter.scala      GroovyGreeter.groovy
        |                         |
  Scala compiler/runtime    Groovy compiler/runtime
~~~

Trong lab, façade public signatures chỉ dùng **String**, nên **Groovy runtime có thể là implementation dependency** của producer. App nhận runtime transitive dependency theo Gradle variant, không cần tự chỉ định groovy.jar paths.

## 6. Bài lab hoàn chỉnh: 3 modules, Scala + Groovy + Java 17

Dự án:
- **:scala-lib** dùng Scala 2.13.12 + Java 17, compile ScalaGreeter và Java façade joint.
- **:groovy-lib** dùng Groovy 4.0.24 + Java 17, compile GroovyGreeter và Java façade joint.
- **:app** dùng Java 17 application, gọi cả hai façades, có JavaExec smokeCheck thực.
- **VerifyOutput.java** là Java 17 independent checker, compile bằng javac/java.

**Lưu ý quan trọng:** Scala compiler/Zinc/Groovy dependencies nằm trên Maven Central, vì vậy môi trường sạch cần Internet hoặc corporate Maven mirror đã cấu hình. Core Gradle plugins không cần external plugin marker nhưng **compiler libraries vẫn cần tải**.

### 6.1. Cấu trúc thư mục

~~~text
jvm-language-plugins-lab/
├── settings.gradle
├── gradlew                         # sau khi tạo Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── scala-lib/
│   ├── build.gradle
│   └── src/main/scala/demo/scala/
│       ├── ScalaBase.java
│       ├── ScalaGreeter.scala
│       └── ScalaFacade.java
├── groovy-lib/
│   ├── build.gradle
│   └── src/main/groovy/demo/groovy/
│       ├── GroovyBase.java
│       ├── GroovyGreeter.groovy
│       └── GroovyFacade.java
├── app/
│   ├── build.gradle
│   ├── src/main/java/demo/app/Main.java
│   └── src/test/java/demo/app/AppCheck.java
└── tools/
    └── VerifyOutput.java
~~~

**Cấu trúc cố ý không chứa Java files dưới src/main/java của Scala/Groovy modules**, vì Java facades tham chiếu language classes. Joint compilation chỉ được kích hoạt đúng khi các files liên quan nằm trong Scala/Groovy source dirs.

### 6.2. settings.gradle

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = 'jvm-language-plugins-lab'

include 'scala-lib', 'groovy-lib', 'app'

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}
~~~

- Scala/Groovy/compiler Maven dependencies được resolve từ settings repositories.
- **FAIL_ON_PROJECT_REPOS** cấm child projects tự thêm repositories.
- Scala/Groovy là core Gradle plugins nên settings không bắt buộc pluginManagement Gradle Plugin Portal cho baseline.
- Nếu CI cần proxy/credentials, dùng approved repository policy ở settings; không thêm public fallback ở child project.

### 6.3. scala-lib/build.gradle

~~~groovy
plugins {
    id 'scala'
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

scala {
    scalaVersion = '2.13.12'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Trong Gradle 9.9, **scalaVersion** cấu hình Scala SDK/compiler dependencies theo API tương ứng. Không cần khai riêng scala-library vào implementation khi dùng tính năng này theo hướng dẫn chính thức.

### 6.4. scala-lib/src/main/scala/demo/scala/ScalaBase.java

~~~java
package demo.scala;

public class ScalaBase {
    public String prefix() {
        return "Scala: ";
    }
}
~~~

### 6.5. scala-lib/src/main/scala/demo/scala/ScalaGreeter.scala

~~~scala
package demo.scala

final class ScalaGreeter extends ScalaBase {
  def message(name: String): String =
    prefix() + name.trim + "!"
}
~~~

Scala class kế thừa JavaBase và trả một **String**. name.trim loại khoảng trắng đầu/cuối của tên truyền vào.

### 6.6. scala-lib/src/main/scala/demo/scala/ScalaFacade.java

~~~java
package demo.scala;

public final class ScalaFacade {
    private ScalaFacade() {
    }

    public static String message(String name) {
        return new ScalaGreeter().message(name);
    }
}
~~~

Java façade gọi Scala class trong **cùng source set Scala joint compilation**. Public Java API method chỉ nhận/trả String, dễ dùng từ application Java.

### 6.7. groovy-lib/build.gradle

~~~groovy
plugins {
    id 'groovy'
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.groovy:groovy:4.0.24'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.withType(GroovyCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Để compile Groovy production source, Groovy runtime/compiler dependency cần xuất hiện trên classpath. Version 4.0.24 là sample version, không nhằm chỉ định bản mới nhất của Groovy.

### 6.8. groovy-lib/src/main/groovy/demo/groovy/GroovyBase.java

~~~java
package demo.groovy;

public class GroovyBase {
    public String prefix() {
        return "Groovy: ";
    }
}
~~~

### 6.9. groovy-lib/src/main/groovy/demo/groovy/GroovyGreeter.groovy

~~~groovy
package demo.groovy

class GroovyGreeter extends GroovyBase {
    String message(String name) {
        return prefix() + name.trim() + '!'
    }
}
~~~

GroovyGreeter là Groovy class, kế thừa JavaBase. String message method dùng JDK String.trim() và nối chuỗi xác định.

### 6.10. groovy-lib/src/main/groovy/demo/groovy/GroovyFacade.java

~~~java
package demo.groovy;

public final class GroovyFacade {
    private GroovyFacade() {
    }

    public static String message(String name) {
        return new GroovyGreeter().message(name);
    }
}
~~~

GroovyFacade.java gọi Groovy class cùng source set, nên là một ví dụ joint compilation thực chứ không chỉ Java/Groovy cùng project nhưng độc lập.

### 6.11. app/build.gradle

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
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':scala-lib')
    implementation project(':groovy-lib')
}

tasks.register('smokeCheck', JavaExec) {
    group = 'verification'
    description = 'Checks Java and JVM language integration'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.app.AppCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeCheck')
}
~~~

App chỉ compile **Java source**, nên không cần id 'scala' hay id 'groovy'. **project dependencies** và runtime variants truyền library outputs/runtime dependencies tới app.

### 6.12. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.scala.ScalaFacade;
import demo.groovy.GroovyFacade;

public final class Main {
    private Main() {
    }

    public static String report() {
        String scala = ScalaFacade.message(" Mai ");
        String groovy = GroovyFacade.message(" Mai ");
        return scala + "\n" + groovy;
    }

    public static void main(String[] args) {
        System.out.println(report());
    }
}
~~~

### 6.13. app/src/test/java/demo/app/AppCheck.java

~~~java
package demo.app;

public final class AppCheck {
    private AppCheck() {
    }

    public static void main(String[] args) {
        String expected = "Scala: Mai!\nGroovy: Mai!";
        String actual = Main.report();

        if (!expected.equals(actual)) {
            throw new AssertionError(
                "Unexpected app output: " + actual
            );
        }

        System.out.println("check=PASS");
    }
}
~~~

AppCheck là **Java main có assertion**, không phải một **JUnit @Test**. Gradle JavaExec smokeCheck task chạy class này; Gradle test task mặc định **không tự nhận mọi main method làm một test**.

### 6.14. Chạy lab trên Linux/macOS

~~~bash
./gradlew projects --console=plain
./gradlew :scala-lib:tasks --all --console=plain
./gradlew :groovy-lib:tasks --all --console=plain

./gradlew :app:run --quiet
~~~

**Stdout chính xác của Java Main.main:**

~~~text
Scala: Mai!
Groovy: Mai!
~~~

Chạy smoke:

~~~bash
./gradlew :app:smokeCheck --quiet
./gradlew :app:check --console=plain
~~~

**Stdout của riêng AppCheck.main khi chạy smokeCheck --quiet:**

~~~text
check=PASS
~~~

Gradle check có thể in task outcomes/BUILD SUCCESSFUL; không xem tất cả các dòng đó là stdout Java.

### 6.15. Windows PowerShell

~~~powershell
.\gradlew.bat projects --console=plain
.\gradlew.bat :scala-lib:tasks --all --console=plain
.\gradlew.bat :groovy-lib:tasks --all --console=plain
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:smokeCheck --quiet
.\gradlew.bat :app:check --console=plain
~~~

Output Java Main giống Linux/macOS, và smokeCheck in check=PASS. Nếu Wrapper chưa có, cần tạo Wrapper bằng Gradle cài sẵn rồi commit Wrapper files; không tự suy từ build.gradle rằng gradlew đã tồn tại.

### 6.16. Xem task graph và outputs

~~~bash
./gradlew :app:run --dry-run --console=plain

./gradlew :scala-lib:compileScala \
  :groovy-lib:compileGroovy --console=plain

./gradlew :scala-lib:classes \
  :groovy-lib:classes :app:classes --console=plain
~~~

Trong output directories theo convention, bạn có thể thấy:

~~~text
scala-lib/build/classes/scala/main/
groovy-lib/build/classes/groovy/main/
app/build/classes/java/main/
~~~

Gradle có thể thay paths nếu user cấu hình destinationDirectory hoặc plugin version khác. Không hardcode các directory này làm consumer classpath: **project dependency** sẽ mang producer outputs tới compiler/run tasks.

### 6.17. Xem compiler/runtime dependency graph

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath --console=plain

./gradlew :scala-lib:dependencies \
  --configuration scalaToolchainRuntimeClasspath --console=plain

./gradlew :scala-lib:dependencies \
  --configuration zinc --console=plain

./gradlew :groovy-lib:dependencies \
  --configuration runtimeClasspath --console=plain
~~~

**Ý nghĩa:**
- :app:runtimeClasspath cần project :scala-lib/:groovy-lib và relevant runtime dependencies.
- :scala-lib:scalaToolchainRuntimeClasspath phục vụ compiler, không phải app runtime library set.
- :scala-lib:zinc cho biết compiler implementation dependencies.
- :groovy-lib:runtimeClasspath cần Groovy runtime.
- Gradle dependencyInsight giúp tìm nguyên nhân version selected khi conflict/constraints.

### 6.18. Toolchain và compiler logs

~~~bash
./gradlew --version
./gradlew -q javaToolchains

./gradlew :scala-lib:compileScala \
  :groovy-lib:compileGroovy --info --console=plain
~~~

Gradle runtime JVM có thể khác Java 17 compile toolchain một cách hợp lệ. **--info** cung cấp thêm thông tin task execution/compile caching nhưng không cam kết một log line cố định giữa Gradle versions.

## 7. Java 17 verifier độc lập: javac/java và output chính xác

Tạo **tools/VerifyOutput.java** để đọc stdout đã capture từ application, giúp đối chiếu bytes/text mà không cần compile plugin code riêng.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class VerifyOutput {
    private VerifyOutput() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Expected UTF-8 text file path"
            );
        }

        List<String> actual = Files.readAllLines(
                Path.of(args[0]), StandardCharsets.UTF_8
        );
        List<String> expected = List.of(
                "Scala: Mai!",
                "Groovy: Mai!"
        );

        if (!expected.equals(actual)) {
            throw new AssertionError(
                "Actual output: " + actual
            );
        }

        System.out.println("verification=PASS");
    }
}
~~~

### 7.1. Linux/macOS

~~~bash
mkdir -p build/verify
./gradlew :app:run --quiet > build/verify/run.txt

javac --release 17 -encoding UTF-8 \
  -d build/verify tools/VerifyOutput.java

java -cp build/verify VerifyOutput \
  build/verify/run.txt
~~~

**Stdout chính xác của VerifyOutput.main:**

~~~text
verification=PASS
~~~

### 7.2. Windows PowerShell

Để tránh khác biệt text encoding khi redirect với PowerShell cũ, ghi stdout của Gradle bằng UTF-8 explicit:

~~~powershell
New-Item -ItemType Directory -Force build\verify | Out-Null
$lines = & .\gradlew.bat :app:run --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Gradle run failed: $LASTEXITCODE"
}
[System.IO.File]::WriteAllLines(
    (Join-Path (Get-Location) 'build\verify\run.txt'),
    [string[]]$lines,
    (New-Object System.Text.UTF8Encoding($false))
)
javac --release 17 -encoding UTF-8 -d build\verify tools\VerifyOutput.java
java -cp build\verify VerifyOutput build\verify\run.txt
~~~

**Stdout của Java verifier:**

~~~text
verification=PASS
~~~

Verifier chỉ xác minh **output text**, không thay việc Gradle kiểm compiler/source-set/variant graph. AppCheck trong :app:smokeCheck vẫn là functional smoke test chạy bằng Gradle.

## 8. Testing layers và compilation order

### 8.1. Test source sets

Scala và Groovy plugins đều mở rộng sourceSets.test với source dirs ngôn ngữ. Có thể bổ sung Scala test source dưới src/test/scala, Groovy test source dưới src/test/groovy, rồi khai **testImplementation** dependency cho framework phù hợp.

Gradle **Test** task cần framework/test classes nó hiểu (JUnit/Spock/TestNG), không tự chạy class chỉ có static void main.

### 8.2. Dùng JUnit Jupiter thay JavaExec smoke

Đây là **lựa chọn nâng cao**, không cần trong baseline:

~~~groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Sau đó phải tạo test methods với JUnit @Test. Với Groovy test, có thể dùng Spock nếu dependency/framework version tương thích Groovy đang khai. Đừng copy test dependencies này vào tất cả modules mà không chọn version đúng và review runtime classpath.

### 8.3. Khi thư viện thay đổi

Nếu Scala/Groovy logic thay đổi nhưng public façade method signature không đổi:
- JavaCompile của consumer có thể tận dụng compile avoidance/up-to-date/cache.
- **Consumer runtime tests vẫn có thể cần chạy**, vì behavior thay đổi.
- Dependency graph để Gradle xây upstream outputs không tự đồng nghĩa tất cả downstream tests đã chạy.

CI nên chọn app smoke/integration checks tương ứng với module library thay đổi.

## 9. Scala 2 vs Scala 3 và compiler compatibility

Trong Scala ecosystem, các artifacts có thể dùng suffix:

~~~text
org.example:parser_2.13:1.0.0
org.example:parser_3:1.0.0
~~~

**Đây là minh họa tọa độ**, không khẳng định một library tên parser đã được publish. Không dùng parser_2.13 cho Scala 3 mà không kiểm docs interoperability. Scala 2/3 còn khác macro/compiler plugin binary APIs.

Với Scala version migration:
1. Pin Gradle Wrapper và Java toolchain.
2. Kiểm scalaVersion/Scala SDK và Zinc compatibility.
3. Kiểm Scala 2/3 binary suffix của dependencies.
4. Kiểm Scala compiler plugins/macros.
5. Kiểm cross-module public API types.
6. Re-run Scala tests và downstream Java/Groovy integration tests.
7. So source syntax/compiler warnings.
8. Xác minh runtime dependency graph/lockfiles.
9. Tạo release candidate trước khi đổi production.
10. Không tự force incompatible Scala runtime versions chỉ để dependency graph hết conflict.

### 9.1. Scala compiler JVM memory

Scala compilation có thể cần JVM memory và external compiler process settings. Ví dụ:

~~~groovy
tasks.withType(ScalaCompile).configureEach {
    scalaCompileOptions.forkOptions.memoryMaximumSize = '1g'
}
~~~

Chỉ tăng memory khi logs/metrics cho thấy compiler memory pressure; setting quá cao trên CI với nhiều workers có thể gây OOM vì tổng memory vượt runner limit.

### 9.2. ScalaCompile additionalParameters

~~~groovy
tasks.withType(ScalaCompile).configureEach {
    scalaCompileOptions.additionalParameters = [
        '-deprecation',
        '-feature'
    ]
}
~~~

Flags cần kiểm Scala compiler version. Không thêm target/release override vào đây chỉ để sửa một error chung vì Gradle đã có Java toolchain → Scala target logic riêng.

## 10. Groovy-gradle-plugin khác Groovy application plugin

**groovy** plugin chuyên compile mã ứng dụng. **groovy-gradle-plugin** chuyên biến script Gradle conventions trong build-logic thành precompiled Gradle plugins.

Ví dụ **build-logic/build.gradle**:

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}
~~~

Tệp ví dụ:

~~~text
build-logic/src/main/groovy/company.java-conventions.gradle
~~~

Có thể chứa:

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

Gradle precompiled plugin được đăng ký với plugin ID theo tên script khi build-logic được cấu hình đúng. **Đây là snippet về kiến trúc convention plugins**, không phải phần bắt buộc của lab ba modules; để chạy cần build-logic settings, pluginManagement.includeBuild và full folder setup.

| Plugin | Mục tiêu |
|---|---|
| **scala** | ScalaCompile/Zinc + Scala source sets |
| **groovy** | GroovyCompile + Groovy source sets |
| **groovy-gradle-plugin** | Precompiled Groovy DSL Gradle convention plugins |
| **java-gradle-plugin** | Binary Gradle plugin development |
| **java-library** | API/implementation separation và publish variants |
| **application** | Application run task và distributions |

**Nhầm groovy-gradle-plugin với groovy** có thể dẫn tới project không có compileGroovy task cho production source.

## 11. Hiệu năng và Build Cache

### 11.1. UP-TO-DATE vs FROM-CACHE vs incremental

- **UP-TO-DATE:** Gradle xác nhận task inputs/outputs không đổi, không chạy task action.
- **FROM-CACHE:** Cached output được phục hồi từ cache key hợp lệ, task action không chạy.
- **Incremental Scala/Groovy compile:** Compiler task chạy nhưng có thể chỉ compile source bị ảnh hưởng.
- **Configuration Cache:** Reuse configured task graph, không tự thay output cache.

Chạy:

~~~bash
./gradlew :scala-lib:classes :groovy-lib:classes \
  --build-cache --console=plain

./gradlew :scala-lib:classes :groovy-lib:classes \
  --build-cache --console=plain
~~~

Lượt hai có thể UP-TO-DATE. Khi cần fresh tasks:

~~~bash
./gradlew :scala-lib:compileScala \
  :groovy-lib:compileGroovy \
  --rerun-tasks --no-build-cache --console=plain
~~~

**Không khẳng định FROM-CACHE chắc chắn xuất hiện** vì phụ thuộc eligibility, key, cache state và outputs.

### 11.2. Java toolchains trong multi-language build

Một Java 17 toolchain hợp lệ có thể được dùng bởi JavaCompile, ScalaCompile và GroovyCompile theo plugin support. Nhưng:
- Gradle Daemon JVM có thể là JDK khác.
- Scala/Groovy compiler versions vẫn cần JVM compatibility.
- Nếu toolchain JDK 17 không có sẵn và resolver không được cấu hình, build fail.
- IDE Gradle JVM cũng cần tương thích Wrapper.
- Compile target flags của Scala/Groovy phải phù hợp; không giữ old target của Java 8 một cách vô ý.

### 11.3. Tối ưu classpaths

Nếu module không có Groovy source, không cần áp groovy compiler plugin chỉ để dùng Groovy JAR do thư viện khác cung cấp. Tương tự Java app dùng Scala façade không cần ScalaCompile task.

Giữ public API theo Java types khi thích hợp giúp:
- Giảm compile classpath surface.
- Hạn chế consumers cần biết Groovy/Scala runtime-specific types.
- Dễ phát triển/kiểm thử modules độc lập.
- Có thể cải thiện compile avoidance/variant separation.

**Đổi code implementation vẫn có thể làm downstream tests fail**, nên performance optimization không thay QA coverage.

## 12. Troubleshooting theo từng lớp

### Lỗi 1 — Viết build.gradle bằng Groovy nhưng không thấy compileGroovy

**Nguyên nhân:** Chỉ có Groovy DSL, chưa apply groovy plugin.

**Cách xử lý:** Áp id 'groovy' tại project chứa source .groovy, khai compiler/runtime dependency.

### Lỗi 2 — compileGroovy không suy luận được groovyClasspath

**Nguyên nhân:** Thiếu hoặc không resolve được Groovy library/compiler JAR trên classpath.

**Cách xử lý:** Kiểm implementation/testImplementation Groovy version, repositories và compiler classpath. Không áp plugin thêm lần nữa.

### Lỗi 3 — ScalaCompile thiếu Scala compiler classpath

**Nguyên nhân:** Không có scalaVersion trên Gradle support API hoặc Scala SDK/compiler dependency không được cấu hình đúng.

**Cách xử lý:** Dùng scala { scalaVersion = '2.13.12' } như lab hoặc cấu hình Scala dependencies theo Gradle version cụ thể.

### Lỗi 4 — Scala plugin được áp nhưng Scala file không compile

**Nguyên nhân:** Source đặt sai thư mục hoặc sourceSets.main.scala.srcDirs bị override.

**Cách xử lý:** Kiểm src/main/scala, project path và --info source inputs; không chuyển .scala vào src/main/java.

### Lỗi 5 — Zinc resolution fail

**Nguyên nhân:** zinc configuration/module/version không resolve hoặc incompatible toolchain.

**Cách xử lý:** Xem zinc dependency graph, trusted Maven repo, Gradle/Zinc support matrix; không nhầm zinc là application runtime GAV.

### Lỗi 6 — Java trong src/main/java tham chiếu ScalaGreeter không compile

**Nguyên nhân:** compileJava chạy trước compileScala, tạo cycle.

**Cách xử lý:** Đặt Java façade trong src/main/scala như lab hoặc tách Java API module.

### Lỗi 7 — Java trong src/main/java tham chiếu GroovyGreeter không compile

**Nguyên nhân:** compileJava chạy trước compileGroovy.

**Cách xử lý:** Di chuyển Java façade liên quan vào src/main/groovy cho joint compilation.

### Lỗi 8 — Consumer Java compile thiếu GroovyObject

**Nguyên nhân:** Public Groovy class type yêu cầu Groovy runtime trên compileClasspath nhưng producer khai Groovy dependency implementation.

**Cách xử lý:** Expose API dependency đúng hoặc dùng pure Java façade để che implementation.

### Lỗi 9 — Scala module báo NoClassDefFoundError khi app chạy

**Nguyên nhân:** RuntimeClasspath thiếu Scala SDK hoặc Scala binary version mismatch.

**Cách xử lý:** Xem app.runtimeClasspath, scalaVersion, variants/constraints và Scala library artifacts.

### Lỗi 10 — Groovy module báo NoClassDefFoundError

**Nguyên nhân:** RuntimeClasspath thiếu Groovy library hoặc version conflict.

**Cách xử lý:** Kiểm groovy-lib.runtimeClasspath và app.runtimeClasspath, group org.apache.groovy/version.

### Lỗi 11 — Đổi Groovy 2 sang 4 mà artifact không tồn tại

**Nguyên nhân:** Maven group thay đổi, version pin hoặc repository filter sai.

**Cách xử lý:** Khai org.apache.groovy:groovy:4.x đúng và kiểm dependencies/verification.

### Lỗi 12 — Scala artifact có hậu tố _2.12 nhưng compiler dùng 2.13

**Nguyên nhân:** Scala binary compatibility mismatch.

**Cách xử lý:** Dùng artifact _2.13 phù hợp hoặc migration review; không force suffix.

### Lỗi 13 — Scala compiler plugin không hoạt động

**Nguyên nhân:** Compiler plugin được khai nhầm vào Gradle plugins DSL hoặc không tương thích Scala version.

**Cách xử lý:** Dùng scalaCompilerPlugins configuration, xác minh artifact và compiler flags.

### Lỗi 14 — Java 17 toolchain không tìm thấy

**Nguyên nhân:** Không cài JDK 17/Gradle không phát hiện/resolver chưa có.

**Cách xử lý:** java -version, javac -version, gradlew -q javaToolchains, cấu hình trusted toolchain.

### Lỗi 15 — AppCheck.main có code đúng nhưng Gradle :app:test không chạy

**Nguyên nhân:** Plain main không phải JUnit/Spock test.

**Cách xử lý:** Chạy :app:smokeCheck hoặc thêm test framework với @Test thật.

### Lỗi 16 — :app:smokeCheck có failure nhưng :app:run vẫn in kết quả

**Nguyên nhân:** :app:run chỉ chạy Main, không tự include all QA/check tasks.

**Cách xử lý:** Chạy :app:check và điều tra assertion; không xem app run là toàn bộ test suite.

### Lỗi 17 — Incremental Groovy tasks chạy lại quá nhiều

**Nguyên nhân:** AST transformations, compiler classpath/source inputs đổi hoặc Gradle support limitations.

**Cách xử lý:** Đo --info, compiler inputs, Gradle version, AST classpath; không bỏ task inputs để ép cache hit.

### Lỗi 18 — Scala incremental compile tốn RAM hoặc compile chậm

**Nguyên nhân:** Zinc/compiler process memory, macro/plugin overhead, full API change.

**Cách xử lý:** Đo forkOptions/compiler daemon, caches, classpaths, available CI workers.

### Lỗi 19 — IDE không đánh dấu Scala/Groovy source directories

**Nguyên nhân:** Project chưa reload/sync hoặc IDE Gradle JVM/Wrapper không tương thích.

**Cách xử lý:** Sync Gradle, kiểm sourceSets, JDK và language IDE support; không đổi source path tùy tiện.

### Lỗi 20 — groovy-gradle-plugin được áp nhưng không có app compileGroovy

**Nguyên nhân:** Nhầm precompiled Gradle convention plugin development với application language plugin.

**Cách xử lý:** Áp core groovy plugin vào application project.

### Lỗi 21 — FAIL_ON_PROJECT_REPOS chặn repository trong subproject

**Nguyên nhân:** Settings repository policy enforce đúng.

**Cách xử lý:** Đưa approved Maven repository vào settings, không tự disable policy.

### Lỗi 22 — compileScala và compileGroovy báo Java version mismatch

**Nguyên nhân:** JDK toolchain/Scala target/Groovy runtime version không tương thích.

**Cách xử lý:** Pin Wrapper, Scala/Groovy version và Java toolchain; kiểm Scala target matrix, compiler versions trước khi override flags.

### Lỗi 23 — Gradle báo UP-TO-DATE nhưng không có compiler log

**Giải thích:** Task action đã được skip do up-to-date checks. Đó không phải compiler không tồn tại.

**Cách xử lý:** Xem task outcome, có thể dùng --rerun-tasks để kiểm source compiler execution khi cần.

### Lỗi 24 — Build Cache FROM-CACHE nhưng Java app vẫn chạy được

**Giải thích:** Gradle đã phục hồi compiler outputs; app sử dụng outputs hợp lệ. FROM-CACHE không có nghĩa compiler chạy lại.

**Cách xử lý:** Báo task provenance đúng và giữ full QA/integration tests phù hợp.

## 13. Checklist trước khi dùng Scala/Groovy plugin trong production

1. Phân biệt Gradle DSL với source language đã rõ?
2. Các projects áp đúng scala/groovy/java-library/application plugins?
3. Không áp compiler plugin cho project chỉ có Java source vô ích?
4. Scala version, Zinc version và Scala library binary suffixes được quản lý?
5. Groovy runtime version pin với đúng Maven group?
6. Java toolchain version/JDK vendor được kiểm trong CI?
7. Gradle Wrapper và Daemon JVM tương thích?
8. Source sets/language dirs đúng convention?
9. Java cần reference Scala/Groovy sources được đưa vào joint compile unit?
10. Không có circular compileJava ↔ compileScala/Groovy wiring?
11. Groovy compiler groovyClasspath resolve đúng?
12. Scala compiler toolchain/scalaToolchainRuntimeClasspath/zinc resolve đúng?
13. Compiler plugins/AST transformations có versions và classpaths phù hợp?
14. Public API có cần expose language-specific types không?
15. api/implementation được khai đúng với public Java façade?
16. Runtime variant đưa Groovy/Scala dependencies tới consumer?
17. Test source sets và frameworks được cấu hình có chủ đích?
18. :app:smokeCheck hoặc JUnit tests có assertion thực?
19. IDE/Tooling API nhận đúng sources và outputs?
20. Caches và incremental compilation được đo, không đoán?
21. Dependency locking/verification và Maven repositories đáng tin?
22. Các bước upgrade Scala 2→3 hoặc Groovy 3→4 có migration tests?
23. CI chạy downstream consumer tests khi library behavior thay đổi?
24. README có lệnh chạy, stdout, failure modes để người học tự kiểm?

## 14. Bài tập có đáp án

**Bài 1.** Có build.gradle dùng Groovy DSL thì tự có compileGroovy không?  
**Đáp:** Không. Cần apply core Groovy language plugin.

**Bài 2.** Core Scala plugin có cần version trong plugins block không?  
**Đáp:** Không; nó đi kèm Gradle distribution.

**Bài 3.** Scala compiler library có giống Gradle plugin id 'scala' không?  
**Đáp:** Không; một cái là Maven compiler/SDK, một cái mở rộng Gradle model.

**Bài 4.** Scala plugin bổ sung tasks nào?  
**Đáp:** compileScala, compileTestScala, scaladoc và source-set-specific ScalaCompile.

**Bài 5.** Groovy plugin bổ sung tasks nào?  
**Đáp:** compileGroovy, compileTestGroovy, groovydoc và source-set-specific GroovyCompile.

**Bài 6.** src/main/scala có thể chứa Java source không?  
**Đáp:** Có, để Scala/Java joint compilation.

**Bài 7.** src/main/groovy có thể chứa Java source không?  
**Đáp:** Có, để Groovy/Java joint compilation.

**Bài 8.** Java src/main/java mặc định gọi class mới chỉ có sau compileScala được không?  
**Đáp:** Không chắc; compileJava chạy trước. Dùng joint directory hoặc tách Java API module.

**Bài 9.** Java façade trong Scala source directory làm gì?  
**Đáp:** Gọi Scala implementation cùng compiler unit và expose Java-friendly API.

**Bài 10.** GroovyFacade được compile ở task nào trong lab?  
**Đáp:** compileGroovy vì Java file nằm trong src/main/groovy.

**Bài 11.** java.toolchain và scala.scalaVersion có cùng nghĩa không?  
**Đáp:** Không; cái đầu chọn JDK, cái sau chọn Scala compiler/SDK version.

**Bài 12.** Zinc dùng để làm gì?  
**Đáp:** Incremental Scala compilation và dependency analysis.

**Bài 13.** scalaCompilerPlugins dùng cho Gradle plugins hay compiler plugins?  
**Đáp:** Scala compiler plugins, khác Gradle plugins DSL.

**Bài 14.** groovyClasspath dùng cho điều gì?  
**Đáp:** Load/chạy Groovy compiler, khác source compile classpath.

**Bài 15.** localGroovy() có tốt để pin ứng dụng production không?  
**Đáp:** Không mặc định; phụ thuộc embedded Groovy version của Gradle distribution.

**Bài 16.** Scala 2.13 binary suffix và Scala 3 suffix có giống nhau?  
**Đáp:** Không; thường _2.13 và _3.

**Bài 17.** App Java trong lab có cần apply Scala/Groovy plugins không?  
**Đáp:** Không; nó chỉ dùng outputs của two language library projects.

**Bài 18.** Sao Groovy implementation dependency vẫn có thể xuất hiện ở app runtime?  
**Đáp:** java-library runtime variant truyền implementation dependencies cho consumers runtime.

**Bài 19.** Nếu public Groovy type được expose cho Java consumer, dùng implementation đủ không?  
**Đáp:** Không chắc; có thể cần Groovy library trên API compile classpath hoặc dùng pure Java façade.

**Bài 20.** AppCheck.main tự là JUnit test?  
**Đáp:** Không; cần JavaExec smokeCheck hoặc JUnit @Test framework.

**Bài 21.** Main.main của app in gì?  
**Đáp:** Hai dòng Scala: Mai! và Groovy: Mai!.

**Bài 22.** VerifyOutput in gì khi file match?  
**Đáp:** verification=PASS.

**Bài 23.** Groovy-gradle-plugin dùng cho điều gì?  
**Đáp:** Tạo precompiled Groovy DSL Gradle convention plugins, không thay groovy app source plugin.

**Bài 24.** Vì sao Scala/Groovy lang plugins vẫn cần Maven repositories?  
**Đáp:** Compiler SDK, Zinc, Groovy runtime/compiler là external dependencies.

**Bài 25.** Thay Scala 2 bằng 3 chỉ đổi scalaVersion là đủ?  
**Đáp:** Không; cần binary suffix, compiler plugins, API, runtime và test compatibility.

**Bài 26.** --build-cache có đảm bảo FROM-CACHE?  
**Đáp:** Không; cần eligible task, compatible key và cache entry.

**Bài 27.** Compile avoidance có nghĩa downstream runtime tests được bỏ?  
**Đáp:** Không; runtime behavior vẫn có thể thay.

**Bài 28.** Gradle Daemon JVM khác Java 17 compiler toolchain có chắc sai?  
**Đáp:** Không; có thể đúng theo design.

## 15. Tài liệu chính thức

- [Gradle — The Scala Plugin](https://docs.gradle.org/current/userguide/scala_plugin.html): ScalaCompile/ScalaDoc, scalaVersion, Zinc, Scala compiler plugins, Scala 3 và joint compilation.
- [Gradle — The Groovy Plugin](https://docs.gradle.org/current/userguide/groovy_plugin.html): GroovyCompile, groovyClasspath, runtime dependencies, joint compilation và AST/incremental caveats.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): JVM language plugins, source sets và compilation dependencies.
- [Gradle — Plugin Reference](https://docs.gradle.org/current/userguide/plugin_reference.html): core Scala/Groovy/Java/application/java-library plugins.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation variants.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): mainClass và run task.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): JavaCompiler, JavaLauncher và Scala/Groovy toolchain support.
- [Gradle — The Groovy Gradle Plugin](https://docs.gradle.org/current/userguide/groovy_gradle_plugin.html): precompiled Groovy DSL plugin development.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): buildSrc/build-logic và convention plugin IDs.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Test tasks, Java source sets và frameworks.
- [Gradle — Dependency Reporting](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies/dependencyInsight.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output reuse.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configured task graph reuse.

**Kết luận:** Scala/Groovy language plugins **mở rộng Java source/task/dependency model**, không chỉ là hai cú pháp build scripts. Scala cần đúng Scala compiler/SDK/Zinc và Java toolchain; Groovy cần compiler/runtime classpath và nên pin version tường minh. Joint compilation của Java source nằm trong Scala/Groovy source dirs giải quyết cross-language references có kiểm soát. Dùng Java façades, java-library variants và Java 17 consumer tests để đảm bảo hệ đa ngôn ngữ biên dịch, chạy và nâng cấp an toàn.