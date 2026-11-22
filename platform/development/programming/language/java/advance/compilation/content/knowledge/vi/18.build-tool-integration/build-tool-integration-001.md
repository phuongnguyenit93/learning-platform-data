# Vai trò của Gradle hoặc Maven quanh trình biên dịch Java

## 1. Tách rõ hai trách nhiệm: biên dịch và điều phối quá trình build

Một câu lệnh `javac` nhận các Java source files, phân giải dependency theo classpath/module path, kiểm tra cú pháp/ngữ nghĩa rồi tạo `.class`. Nhưng một dự án thực tế còn phải:

- Chọn đúng tập nguồn ứng dụng, test và generated source.
- Tải, chọn phiên bản và truyền các JAR phụ thuộc vào compiler.
- Dùng JDK phù hợp, đặt `--release`, encoding và compiler flags.
- Biên dịch trước các module/thư viện mà module sau cần.
- Chạy annotation processor hoặc bước sinh mã, xử lý resources.
- Chạy kiểm thử, phân tích chất lượng, đóng gói, xuất bản artifact.
- Tái sử dụng kết quả hợp lệ trong incremental builds hoặc cache.
- Thực hiện cùng một quy trình trên máy phát triển và CI.

**Gradle và Maven là công cụ điều phối build; `javac` là compiler thực sự kiểm tra và chuyển Java source thành bytecode** (trong những cấu hình Java thông thường). Build tool không tự tạo ra ngôn ngữ Java khác, không thay thế semantic analysis của javac và không biến chương trình sai cú pháp thành hợp lệ.

~~~text
                      Cấu hình build
                  Gradle / Maven
                           |
          +----------------+----------------+
          |                |                |
      source sets       dependencies     JDK/toolchain
          |                |                |
          +----------------+----------------+
                           |
                compiler arguments
                           |
                       javac
                           |
                         .class
                           |
          +----------------+----------------+
          |                |                |
       resources          tests           package
          |                |                |
          +----------------+----------------+
                           |
                  JAR / distribution
~~~

Sơ đồ là mô hình logic. Đường đi thực tế và thứ tự tasks/goals phụ thuộc plugin, cấu hình project và graph phụ thuộc; không phải mỗi lệnh build đều thực hiện tất cả nhánh.

**Điểm mấu chốt:** khi một Java source báo `cannot find symbol`, compiler đưa ra diagnostic; việc type đó có được tìm thấy hay không có thể do *build tool* chưa cấp đúng dependency cho compiler. Chẩn đoán cần biết lỗi nằm ở mã Java hay ở lệnh/cấu hình mà Gradle/Maven đã chuẩn bị.

## 2. So sánh một lệnh javac thủ công với build tool

Lệnh Java thuần để compile và chạy một class:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/App.java
java -cp out demo.App
~~~

Cần chuẩn bị thủ công thêm `-cp` khi chương trình có dependency; phải tự cập nhật lệnh khi thêm source, test, generated sources hoặc nhiều module. Với một file độc lập, cách này vẫn hữu ích để hiểu compiler và tái hiện lỗi tối thiểu.

Gradle/Maven thường chuyển ý định ở cấp cao hơn thành lượt compiler tương đương:

| Nhu cầu | Với javac/java thủ công | Với build tool |
| --- | --- | --- |
| Source files | Liệt kê file/tạo danh sách đầu vào | Source sets hoặc project layout |
| Compiler JDK | Chọn executable `javac` | Toolchain/compiler plugin |
| Java version | `--release 17` | Gradle `options.release`, Maven `maven.compiler.release` |
| Binary dependencies | `-classpath` hoặc `--module-path` | Resolve artifacts, tạo compile classpath |
| Annotation processors | `-processorpath` và tùy chọn liên quan | Processor dependencies/paths, compile task config |
| Class output | `-d out` | Thư mục output theo task/plugin |
| Resources | Copy thủ công | Gradle `processResources`, Maven resources plugin |
| Tests | Compile tests và chạy test runner riêng | Task/goal qua framework/plugin tương ứng |
| JAR | Gọi `jar` | Gradle `jar`, Maven package lifecycle/plugin |
| Incremental/cache | Tự quản lý | Gradle incremental task + build cache, Maven/plugin có cơ chế riêng |

**Không nên nói Gradle/Maven “thay javac”.** Trong các bản build Java thông thường, Gradle `JavaCompile` hoặc Maven Compiler Plugin gọi compiler dưới lớp abstraction. Một dự án có thể dùng compiler thay thế, Kotlin/Scala hay task code generation khác, vì thế cơ chế thực tế cần đọc theo plugin đang cấu hình.

## 3. Ví dụ Java 17+ chung cho cả Gradle và Maven

Dùng **một** file nguồn cho hai phương án build độc lập:

~~~text
sample-project/
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               └── App.java
├── build.gradle             # chọn khi dùng Gradle
├── settings.gradle          # chọn khi dùng Gradle
└── pom.xml                  # chọn khi dùng Maven
~~~

Tệp **src/main/java/demo/App.java**:

~~~java
package demo;

public final class App {
    private App() {}

    public static int total(int left, int right) {
        return Math.addExact(left, right);
    }

    public static void main(String[] args) {
        System.out.println("SUM=" + total(2, 5));
    }
}
~~~

Đây là một Java application bình thường; không import API của Gradle hoặc Maven. Vì thế **mã nguồn không cần viết lại khi đổi từ Gradle sang Maven**. Cả hai chỉ thay đổi cách chuẩn bị compilation input, options và các bước quanh compiler.

### 3.1. Kiểm tra baseline bằng javac, không dùng build tool

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/App.java
java -cp out demo.App
~~~

Stdout của ứng dụng:

~~~text
SUM=7
~~~

Có thể kiểm tra bytecode:

~~~bash
javap -classpath out -verbose demo.App
~~~

Phần header của class file có:

~~~text
major version: 61
~~~

Java 17 dùng class-file major version 61. Kết quả `SUM=7` và major 61 đã được kiểm tra bằng `javac 21` với `--release 17` trong môi trường thử riêng. Điều này xác minh Java source, **không phải** xác nhận các lệnh Gradle/Maven ở môi trường chưa có chúng.

## 4. Gradle: plugin Java, task graph và compiler task

Gradle là hệ thống build dựa trên **tasks** và quan hệ phụ thuộc giữa tasks. Với Java, plugin `java` đăng ký các source sets, configurations và tasks phổ biến:

| Task | Vai trò |
| --- | --- |
| `compileJava` | Dùng Java compiler cho source của `main` |
| `processResources` | Chuyển resources của `main` vào output |
| `classes` | Task tập hợp phụ thuộc vào compile/resources |
| `compileTestJava` | Biên dịch source của `test` với test compile classpath |
| `processTestResources` | Xử lý resources của test |
| `testClasses` | Tập hợp output test |
| `test` | Chạy tests theo test framework/engine đã cấu hình |
| `jar` | Đóng gói production classes/resources thành JAR |
| `assemble` | Tập hợp artifacts đóng gói |
| `check` | Tập hợp các bước xác minh |
| `build` | Thường phụ thuộc `assemble` và `check` |

**Task graph** quan trọng hơn thứ tự các dòng trong file cấu hình. Khi yêu cầu `build`, Gradle lập graph và chạy những prerequisite tasks cần thiết, tránh chạy lại các task không cần làm nếu inputs/outputs đáp ứng điều kiện up-to-date.

### 4.1. Ví dụ Gradle Groovy DSL đầy đủ

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'compiler-build-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.App'
}
~~~

Plugin `application` áp dụng chức năng Java cần thiết và bổ sung task `run`/distribution tasks. `mainClass` là fully qualified name của lớp có `main`. Không cần thêm `implementation` dependency cho ví dụ `App` vì chỉ dùng Java standard library.

**Tách hai thuộc tính:**

- `java.toolchain.languageVersion = 17`: yêu cầu Gradle dùng toolchain Java 17 thích hợp cho compilation và các JVM tools do plugin quản lý.
- `options.release = 17`: yêu cầu compiler áp quy tắc Java 17 về cú pháp, class-file version và public platform APIs.

Nếu mục tiêu là compile bằng JDK 21 nhưng tạo artifact chạy trên Java 17, có thể yêu cầu toolchain 21 và `options.release = 17`, miễn là cả Gradle/toolchain/compiler hỗ trợ tổ hợp đó. Không nên thay `--release` bằng `-source`/`-target` rồi vô tình gọi các API mới hơn runtime đích.

### 4.2. Các lệnh Gradle

Trên dự án có **Gradle Wrapper**:

~~~bash
./gradlew clean build
./gradlew run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean build
.\gradlew.bat run
~~~

Wrapper files (`gradlew`, `gradlew.bat` và `gradle/wrapper/...`) phải đã được tạo/commit theo quy trình dự án. **Bản ví dụ build.gradle ở trên không tự sinh wrapper files.** Nếu chưa có wrapper, có thể dùng bản Gradle đã cài đặt phù hợp để chạy `gradle build`/`gradle run` hoặc tạo wrapper theo quy trình bình thường. Không hứa chạy `./gradlew` được nếu dự án chưa có script đó.

Dòng stdout **do chính App in** trong `run` là:

~~~text
SUM=7
~~~

Đầu ra của Gradle còn có thông tin task/build; vì vậy không coi toàn bộ terminal output chỉ có một dòng. Task `build` đóng gói và thực hiện các bước kiểm tra được cấu hình, **không tự gọi App.main()**. Task `run` của Application Plugin mới chạy main class. Task `test` chạy các bài test nếu có và nếu test framework được cấu hình phù hợp.

Output mặc định của Gradle Java plugin thường nằm trong `build/classes/java/main`, resources trong `build/resources/main` và JAR dưới `build/libs`. Đây là **conventions**, có thể bị thay bằng build configuration, không nên hardcode trong tool tích hợp.

## 5. Maven: lifecycle, phases, goals và Compiler Plugin

Maven vận hành theo **lifecycles** và các **phases**; plugin goals được bind vào phase. Với project có packaging `jar` thông thường:

| Phase/goal | Ý nghĩa tiêu biểu |
| --- | --- |
| `validate` | Kiểm tra project model/cấu hình cơ bản |
| `process-resources` | Copy/filter resources bằng resources plugin |
| `compile` | Compiler plugin biên dịch source main |
| `process-test-resources` | Chuẩn bị resources của test |
| `test-compile` | Compiler plugin biên dịch test source |
| `test` | Surefire plugin có thể chạy unit tests |
| `package` | Đóng gói thành JAR hoặc packaging tương ứng |
| `verify` | Thực hiện thêm kiểm tra sau packaging nếu cấu hình |
| `install` | Cài artifact vào local Maven repository |
| `deploy` | Triển khai artifact tới remote repository phù hợp |

Khi gọi `mvn package`, Maven thực hiện các phases cần thiết **từ đầu default lifecycle tới package** theo binding của project/plugins; không phải chỉ riêng một lệnh `jar`. Các goals cụ thể có thể khác tùy packaging, plugin config và extensions.

### 5.1. pom.xml đầy đủ để compile Java 17

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>compiler-build-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven Compiler Plugin nhận property `maven.compiler.release` và điều khiển compiler tương ứng. Bài chọn phiên bản plugin **3.13.0** cụ thể để cấu hình có khả năng tái lập; dự án thực nên cập nhật phiên bản plugin theo JDK/Maven compatibility đã được kiểm thử, không phải cứ dùng “latest” không kiểm soát.

POM này **không cấu hình Maven Toolchains Plugin**: Maven đang dùng JDK mà môi trường/plugin thực tế chọn, vì vậy cần kiểm tra `mvn -version` và đảm bảo JDK hỗ trợ release 17. Maven chạy bằng JDK 8 không thể hiểu `--release 17`; một POM có property 17 không tự tải JDK 17 cho mọi máy.

### 5.2. Compile, package, chạy

Từ project root khi có Maven 3 và JDK thích hợp:

~~~bash
mvn clean package
java -cp target/classes demo.App
~~~

Stdout do `App` in:

~~~text
SUM=7
~~~

Maven sẽ in nhiều dòng build log; `mvn clean package` không mặc định gọi `App.main`. JAR thường ở vị trí dạng `target/compiler-build-demo-1.0.0.jar` (convention dựa trên artifactId/version), và có thể chạy qua classpath:

~~~bash
java -cp target/compiler-build-demo-1.0.0.jar demo.App
~~~

Trong ví dụ không có thư viện bên ngoài, lệnh dùng JAR có thể chạy nếu đóng gói thành công. Nhưng **`java -jar target/compiler-build-demo-1.0.0.jar` không mặc nhiên chạy được**: mặc định JAR không nhất thiết có `Main-Class` trong manifest. Muốn executable JAR phải cấu hình manifest/packaging phù hợp; nếu có runtime dependencies phải đóng gói hoặc cung cấp classpath hợp lệ.

**Hai cấu hình Gradle và Maven ở đây là hai phương án thay thế.** Không cần chạy cả hai build trong một pipeline nếu dự án chỉ chọn một công cụ. Khi để hai file cấu hình trong cùng thư mục cho mục đích so sánh, output Gradle ở `build/` và Maven ở `target/`; không lấy output của hệ này để đánh giá build của hệ kia.

## 6. Dependency resolution: trách nhiệm lớn nhất ngoài javac

`javac` không đọc Maven POM hay Gradle module metadata để tự đi lên Internet chọn dependency. Nó cần một **compile classpath** hoặc **module path** đã được chuẩn bị.

Ví dụ source:

~~~java
import org.example.api.Widget;
~~~

Là một **import minh họa** (không phải phần của App.java chạy được): nếu compiler không nhận được class `org.example.api.Widget`, nó báo lỗi dù source file có import. Build tool chịu trách nhiệm chọn artifact phiên bản đúng, lấy JAR và đặt đường dẫn class output/JAR vào compiler invocation.

Khai báo dependency có ý nghĩa khác nhau theo scope/configuration:

| Ý định | Gradle Java plugin | Maven |
| --- | --- | --- |
| Dùng lúc compile và runtime | `implementation` | `compile` scope mặc định |
| Chỉ cần khi compile | `compileOnly` | `provided` có semantics phân phối/container riêng, **không tương đương hoàn toàn** |
| Chỉ cần khi runtime | `runtimeOnly` | `runtime` |
| Dùng trong tests | `testImplementation` / `testRuntimeOnly` | `test` |
| Annotation processor | `annotationProcessor` | Processor path/plugin configuration phù hợp |
| Xuất API cho consumer library | `api` của `java-library` | Dependency contract/version trong POM |

**Scope không chỉ ảnh hưởng bước tải thư viện.** Nó quyết định compiler nhìn thấy type nào, test compilation thấy gì và runtime có đủ JAR nào. Với Maven, `provided` có ý nghĩa rằng môi trường chạy/container dự kiến cung cấp dependency, nên không được coi nó như synonym của Gradle `compileOnly` trong mọi kiểu packaging.

Với Java modules (JPMS), build tool còn phải chuẩn bị `--module-path` và module graph tương ứng: một JAR nằm trong dependency graph không đồng nghĩa code được phép truy cập package nếu module không `exports` hay client không `requires`.

### 6.1. Vì sao dependency transitively cần quản lý?

Giả sử App phụ thuộc A, và A phụ thuộc B. Build tool có thể resolve B theo metadata và scopes phù hợp, chọn phiên bản khi nhiều đường dẫn graph xung đột. `javac -cp lib/A.jar` đơn thuần không tự tải B từ repository.

Sơ đồ:

~~~text
App
 |
 +--- library A v2
 |         |
 |         +--- library B v4
 |
 +--- library C v1
           |
           +--- library B v3

Build tool --> dependency resolution --> B được chọn theo rules
Compiler   --> classpath thực tế chứa artifact đã được resolve
~~~

Đừng cho rằng Gradle và Maven luôn chọn **cùng một phiên bản** khi graph có conflict: mỗi công cụ có metadata, scope và dependency resolution rules riêng. Kiểm tra graph thực tế và ràng buộc/lock phiên bản thích hợp.

Đừng thêm tất cả JAR mà tìm được vào classpath chỉ để xóa `cannot find symbol`. Việc đó có thể thêm duplicate classes, ABI không tương thích, class khác phiên bản hoặc thư viện không được phép phân phối.

### 6.2. Cách điều tra dependency graph

Trong Gradle, từ dự án có plugin Java:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencyInsight --dependency example --configuration compileClasspath
~~~

Từ `example` ở trên là **chuỗi tìm kiếm minh họa**, cần đổi thành group/artifact thực tế. Những lệnh này không sửa Java source; chúng giúp biết compiler task sẽ thấy các dependencies nào. Trong multi-project, chọn đúng project/task/configuration tương ứng.

Với Maven:

~~~bash
mvn dependency:tree
~~~

Lệnh này cần Maven Dependency Plugin tương ứng có thể được resolve, và phải xem đúng module/scope. Nó giúp nhận diện dependency transitively và các phiên bản không như ý. Bản thân một dependency được liệt kê không bảo đảm class muốn dùng nằm trong artifact: có thể cần kiểm tra nội dung JAR.

## 7. Toolchain và --release: JDK chạy build khác JDK mục tiêu

Có ba phiên bản cần phân biệt:

1. **JVM chạy Gradle daemon hoặc Maven**: ảnh hưởng khả năng chạy chính build tool/plugins.
2. **JDK compiler/toolchain được chọn cho compile task**: quyết định javac implementation và các releases được hỗ trợ.
3. **Minimum runtime mục tiêu**: JVM thấp nhất mà artifact cần hỗ trợ.

Gradle cho phép cấu hình toolchain tường minh, kể cả khi JDK dùng chạy Gradle khác với JDK dùng compile. Maven có Maven Toolchains Plugin hoặc cách chọn executable/compiler theo plugin/version và môi trường; một POM chỉ đặt `maven.compiler.release` **chưa** khóa compiler JDK cho CI.

`--release 17` yêu cầu compiler tạo bytecode Java 17 và kiểm soát các public platform APIs của Java 17, nhưng không kiểm tra mọi binary dependency JAR có phù hợp JVM 17. Một JAR bên thứ ba biên dịch bằng class-file version mới hơn có thể không chạy trên Java 17.

| Cấu hình | Kiểm soát gì? | Không tự bảo đảm |
| --- | --- | --- |
| Gradle toolchain Java 17 | Chọn JDK/tools để compile/test theo task config | Code không dùng API mới hơn target nếu compiler target lại khác |
| `options.release = 17` | Source, class version, platform APIs Java 17 | Chọn đúng compiler executable hoặc dependency JAR compatible |
| Maven `maven.compiler.release=17` | Tương ứng compiler `--release 17` khi toolchain/plugin hỗ trợ | JVM chạy Maven và compiler JDK đã được pin |
| `sourceCompatibility/targetCompatibility` | Mức ngôn ngữ/class format theo hỗ trợ | API cũ được kiểm soát đầy đủ như `--release` |

**Nếu muốn khẳng định ứng dụng chạy Java 17**, tối thiểu phải compile với target/release phù hợp, chọn dependency JAR có minimum Java phù hợp, và **chạy test trên runtime Java 17 thật**. Biên dịch thành công dưới JDK 21 không đủ chứng minh mọi runtime Java 17 hoạt động giống nhau.

## 8. Compiler options: build tool cấu hình, javac thi hành

Một số compiler options được build tool truyền tới Java compiler:

| Tùy chọn | Công dụng | Build tool phải lo thêm |
| --- | --- | --- |
| `--release N` | Ngôn ngữ, class version, public JDK API level | Toolchain javac hỗ trợ N |
| `-encoding UTF-8` | Charset đọc source | File thực sự lưu bằng charset phù hợp |
| `-cp` / `--class-path` | Classes/JAR compile phụ thuộc | Resolve đúng artifact và scope |
| `--module-path` | Named modules | Resolve module graph và module-info |
| `-processorpath` | Chọn đường dẫn annotation processors | Task/source set và processor versions |
| `-processor` | Chọn processor khi khai báo tường minh | Processor class tồn tại và tương thích |
| `-s` | Nơi ghi generated source của annotation processors | Theo dõi generated output làm task output |
| `-Xlint` | Chẩn đoán warning | Chính sách kiểm tra warnings/CI |
| `-Werror` | Chuyển warning thành build failure | Đảm bảo hiểu và sửa warning nguyên nhân |

Cả Gradle lẫn Maven có lớp cấu hình phù hợp với những options thường gặp. Khi cần một javac flag rất đặc thù, có thể truyền compiler args tường minh theo API plugin nhưng cần kiểm tra phiên bản, tránh duplicate flags hoặc conflict với option đã được plugin tự sinh.

**Không nghĩ rằng build tool sửa được compiler diagnostics bằng việc thay wording.** Nếu Java source vi phạm overload resolution, access control hay definite assignment, compiler vẫn từ chối. Build tool giúp lệnh compile đúng môi trường và cho các task fail sớm khi output không hợp lệ.

## 9. Annotation processing và generated sources

Một processor có thể tạo mã nguồn mới trong quá trình biên dịch, ví dụ mapper, DTO helper hoặc metadata class. Nếu processor thiếu hoặc chạy sai, nhiều source khác có thể đồng loạt báo `cannot find symbol` cho generated types.

~~~text
Annotations / schema
        |
        v
Processor / generate task
        |
        v
Generated source
        |
        v
JavaCompile / compiler plugin
        |
        v
Consumer classes
~~~

Công việc của build tool gồm:

- Đưa annotation API vào **compile classpath** theo scope phù hợp.
- Đưa annotation processor implementation vào **processor path** thay vì vô tình kéo vào runtime.
- Tạo quan hệ task producer/consumer đúng, xác định output/generated source directories.
- Bảo đảm dependency graph và compiler JDK thích hợp với processor.
- Theo dõi input/output để incremental/caching không trả lại generated code cũ.

Ví dụ Gradle fragment, cần artifact thực tế mới chạy:

~~~groovy
dependencies {
    compileOnly 'example:annotations:1.0'
    annotationProcessor 'example:processor:1.0'
}
~~~

Hai tọa độ `example:...` chỉ minh họa cấu hình, **không phải các dependencies có thật được bảo đảm tải được**. Trong Maven Compiler Plugin, cấu hình annotation processor paths hoặc processor dependencies theo version/plugin cần dùng. Các phiên bản JDK và plugin khác nhau có thể có chính sách auto-discovery khác; tốt nhất thiết lập processors tường minh khi build cần generated code.

Khi dùng thư viện như Lombok hoặc MapStruct, không tự cho rằng chỉ khai báo một dependency compile là đủ cho mọi version/plugin. Cần xem quy tắc processor riêng, module opens khi thực sự cần, và test clean build.

## 10. Multi-module: thứ tự biên dịch là quan hệ phụ thuộc

Dự án lớn thường chia `core`, `service`, `app` hoặc nhiều module cùng release. Compiler của module `app` không thể tự tạo class `core` nếu build tool chưa có output/JAR core hợp lệ.

Gradle multi-project dùng một `settings.gradle` liệt kê projects:

~~~groovy
rootProject.name = 'workspace'
include 'core', 'app'
~~~

Trong `app/build.gradle`, fragment:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation project(':core')
}
~~~

Các snippets này **không phải một multi-project hoàn chỉnh**: cần thêm `core/build.gradle`, sources, Java plugin/toolchain config phù hợp. Mục đích là cho thấy dependency edge giữa các tasks/products, để compile core trước khi app dùng binary output của core.

Maven multi-module dùng aggregator POM với các module:

~~~xml
<modules>
    <module>core</module>
    <module>app</module>
</modules>
~~~

Đây là **fragment** trong aggregator `pom.xml` hợp lệ, không phải một POM độc lập. App cần khai báo dependency tới artifact core với tọa độ/phiên bản đúng. Maven reactor sẽ dùng dependency relations để xác định build order; chỉ liệt kê tên trong `modules` mà thiếu dependency edge không đủ diễn đạt mọi phụ thuộc biên dịch.

**Phân biệt Gradle multi-project và JPMS named modules:** có thể trùng nhau về tổ chức nhưng không phải một khái niệm. JPMS là mô hình module của Java với `module-info.java`, `requires` và `exports`; Gradle/Maven có thể quản lý modules mà source vẫn thuộc unnamed module trên classpath.

## 11. Incremental build, up-to-date check, cache và clean

Gradle có task input/output tracking, incremental compilation cho cấu hình hỗ trợ và build caching; Maven có các hành vi incremental dựa vào compiler plugin/version cùng output tracking. Không nên nói mọi build Maven hoặc Gradle đều biên dịch lại toàn bộ project, cũng không hứa mỗi task luôn được cache.

**Cần phân biệt:**

- **Up-to-date task:** đầu vào/đầu ra không đòi thực thi lại task theo kiểm tra của Gradle.
- **Incremental compilation:** compiler/task chỉ xử lý phần source bị ảnh hưởng theo khả năng phân tích thay đổi, không nhất thiết mọi file.
- **Build cache:** tái sử dụng output đã tính trước khi cache key và cấu hình cho phép.
- **Clean build:** xóa output đã sinh theo cơ chế build tool để tái tạo từ đầu và phát hiện stale outputs.

Ví dụ Gradle:

~~~bash
./gradlew compileJava
./gradlew compileJava
./gradlew clean compileJava
~~~

Trong cùng điều kiện ổn định, lượt thứ hai **có thể** được đánh dấu up-to-date; kết quả thực tế phụ thuộc plugins, inputs, compiler arguments, cache và khả năng Gradle theo dõi outputs. `clean` làm mất outputs của build directory theo task tương ứng, giúp kiểm tra việc một artifact còn sót đã che lỗi.

Maven:

~~~bash
mvn compile
mvn clean compile
~~~

Cơ chế incremental và log Maven phụ thuộc phiên bản compiler plugin, môi trường và project cấu hình. Không tự đồng nhất `mvn compile` với Gradle task `compileJava` ở mức cache/incrementality.

Một build thành công nhờ `.class` cũ hoặc source do generator để lại không chứng minh build reproducible. Chạy thử từ checkout sạch, pin toolchain/dependencies và kiểm tra source generation. Nhưng **đừng xóa thủ công thư mục người khác đang dùng** nếu không sở hữu workspace.

## 12. Packaging và test không phải việc của riêng javac

`javac` tạo `.class`, nhưng một bản phân phối còn cần:

1. Resources (config, templates, service descriptors) đi cùng classes khi cần.
2. Manifest hoặc entrypoint phù hợp; không phải mọi JAR đều executable.
3. Runtime dependencies phải có theo classpath/module path hoặc chiến lược đóng gói cụ thể.
4. Tests phải có framework/engine và test-scoped dependencies được cấu hình đúng.
5. Plugin đóng gói phải biết đầu ra nào cần, loại bỏ file không thuộc distribution và tránh duplicate classes/resources.

**JAR thường vs executable/fat JAR**:

- Gradle `jar` hoặc Maven `jar:jar` mặc định có thể đóng gói classes/resources thành **library JAR**.
- Manifest `Main-Class` cần được cấu hình nếu muốn `java -jar` chạy trực tiếp.
- Dù có `Main-Class`, các dependencies bên ngoài không được tự gộp vào archive thông thường. Có thể cần distribution, manifest classpath hoặc plugin tạo một runnable/fat JAR, với chính sách xử lý trùng resources/licenses.
- `java -cp app.jar:dependencies/* demo.App` là một cơ chế chạy khác (separator trên Windows là `;`) và không được đánh đồng với `java -jar`.

Compiler sẽ không biết sản phẩm cuối cần Docker image, native launcher, WAR hay một plugin distribution. Đây là trách nhiệm build/packaging/deployment khác với kiểm tra Java source.

## 13. Reproducibility và CI: điều kiện để “máy tôi build được” có ý nghĩa

Một bản build đáng tin cần kiểm soát:

- **Gradle/Maven version**: dùng Wrapper phù hợp, ví dụ Gradle Wrapper hoặc Maven Wrapper đã được cấu hình/commit trong dự án.
- **Compiler JDK/toolchain**: chính xác Java version và compiler provider; log build nên cho biết toolchain thực.
- **Dependency versions**: pin hoặc lock theo chính sách; tránh phụ thuộc vào phiên bản dynamic không kiểm soát.
- **Plugin versions**: Maven Compiler Plugin, Surefire, resources/JAR, Gradle plugins theo chính sách tương thích.
- **Repositories và metadata**: cấu hình mirror, xác thực, chế độ offline, artifact integrity khi cần.
- **Encoding/locale/timezone**: tránh output phụ thuộc môi trường; đặc biệt resource filtering, source encoding, generated files.
- **Annotation processors/generated sources**: output được tái sinh từ source rõ ràng, tránh stale files.
- **Tests**: chạy dưới JDK runtime thực tế mục tiêu và với dependency graph runtime.
- **Build artifact**: ghi version, checksums và provenance khi giao sản phẩm.

Một CI job có thể làm các bước như:

~~~text
Checkout sạch
  |
Setup JDK 17 + Gradle/Maven Wrapper
  |
Resolve pinned dependencies
  |
Compile sources + process resources
  |
Compile/run unit tests
  |
Package artifact
  |
Smoke test dưới runtime mục tiêu
  |
Publish nếu toàn bộ checks thành công
~~~

Đây là pipeline khái niệm; tổ chức thực tế có thể thêm security scans, integration tests, signed artifacts và môi trường staging.

## 14. Cách đọc lỗi để biết javac hay build tool đang thất bại

| Triệu chứng | Lớp nên kiểm tra đầu tiên |
| --- | --- |
| `cannot find symbol` khi code dùng type thật | Compiler diagnostic + compile classpath/source roots |
| `package ... does not exist` | Import, JAR thực tế, dependency scope, module path |
| `invalid target release` | Compiler JDK và `--release`/toolchain |
| `UnsupportedClassVersionError` khi chạy | Runtime JVM thấp hơn bytecode của ứng dụng/dependency |
| `NoSuchMethodError` khi chạy | Binary API/JAR runtime khác compile time |
| Processor-generated type biến mất | Annotation processor config, generated source task/output |
| `Could not resolve ...` của Gradle/Maven | Repository, dependency coordinates/metadata, proxy/network |
| `Task :compileJava FAILED` | Đọc **nội dung javac diagnostic** bên trong task |
| Maven compiler goal failure | Đọc javac diagnostics và plugin/compiler parameters |
| Source compile pass nhưng `java -jar` fail | Main-Class, packaging, runtime dependencies |
| CI pass bằng cache nhưng clean build fail | Missing declared inputs, stale generated output, cache config |
| Main compile pass, testCompile fail | Test-specific source set, dependencies và test toolchain |

**Không sửa import bằng cách đổi tên package tùy tiện khi lỗi thực sự là dependency chưa được resolve.** Ngược lại, không đổ lỗi cho Gradle/Maven khi source có ambiguity hoặc vi phạm Java type system. Build tool và compiler đưa ra hai tầng thông tin bổ sung.

Với Gradle, nếu cần thấy nhiều thông tin task, có thể dùng `--info`; với Maven dùng `-X` để debug. Debug log của build tool giúp tìm compiler invocation/dependency resolution nhưng không thay thế thông báo lỗi của compiler tại file và dòng.

## 15. Những hiểu lầm phổ biến

1. **“Dùng Maven nghĩa là không cần javac.”** Sai: compiler plugin vẫn cần Java compiler/toolchain để tạo class files cho Java source.
2. **“Chỉ cài JDK 17 là artifact chắc chắn chạy trên Java 17.”** Sai: phải kiểm tra release, class-file version, dependencies và runtime.
3. **“Khai báo dependency đồng nghĩa mọi scope đều nhìn thấy nó.”** Sai: compile, runtime, test và annotation processor paths có trách nhiệm khác nhau.
4. **“`mvn package` chạy main class.”** Sai với cấu hình thông thường; package tạo artifact, không gọi `App.main()`.
5. **“`gradle build` chỉ là một cách gọi `javac`.”** Sai: nó có task graph gồm các bước khác theo plugins.
6. **“Cùng source, Gradle và Maven chắc chắn ra JAR byte-for-byte giống nhau.”** Sai: metadata, manifest, timestamps, plugin config, resource ordering và reproducible archive settings có thể khác.
7. **“Thêm JAR vào thư mục lib là build tool tự dùng.”** Không nhất thiết: dependency phải được khai báo vào configuration thích hợp.
8. **“Clean mọi lúc là cách build nhanh nhất.”** Clean bỏ khả năng dùng outputs hợp lệ; dùng khi cần xác minh/tái hiện lỗi, không mặc định cho mọi vòng phát triển.
9. **“Plugin tự chạy theo thứ tự viết trong build.gradle/pom.xml.”** Quan hệ tasks/phases/bindings mới là căn cứ thực thi.
10. **“Annotation processor là Java source runtime library.”** Processor chạy ở compile phase; thường cần processor path riêng, không tự động thuộc runtime distribution.
11. **“Toolchain và `--release` là cùng một cờ.”** Toolchain chọn compiler JDK; release định nghĩa target của compilation.
12. **“Compile pass nghĩa là build đã sẵn sàng phát hành.”** Chưa: còn tests, resources, packaging, runtime dependencies, compatibility và deployment checks.

## 16. Quy trình học và kiểm chứng thực hành

**Bài 1 — So sánh Java source không đổi:** tạo `App.java` ở mục 3 và biên dịch bằng `javac` thủ công. Chạy ra `SUM=7`, dùng `javap -verbose` kiểm tra major 61.

**Bài 2 — Dùng Gradle:** chọn `settings.gradle` + `build.gradle` ở mục 4. Với Gradle version và JDK phù hợp, chạy `gradle clean build` rồi `gradle run` (hoặc Wrapper nếu có). Đọc task graph, tìm output `build/classes/java/main/demo/App.class` và phân biệt log task với stdout của App.

**Bài 3 — Dùng Maven:** dùng `pom.xml` ở mục 5 và JDK 17+. Chạy `mvn clean package`; quan sát output `target/classes/demo/App.class` và JAR. Chạy `java -cp target/classes demo.App` thay vì kỳ vọng package tự chạy chương trình.

**Bài 4 — Tạo lỗi có chủ đích:** thay `Math.addExact` thành lời gọi tới method không tồn tại. Cả hai build systems đều phải báo lỗi `javac` dù đường chạy task/goal khác nhau. Khôi phục mã rồi rebuild.

**Bài 5 — Đọc dependency graph:** trong một dự án có dependency thật, kiểm tra Gradle `dependencies` / `dependencyInsight` hoặc Maven `dependency:tree`. So sánh compile và runtime paths, xác định một dependency chỉ được đưa vào test.

**Bài 6 — Quan sát toolchain:** biên dịch với JDK mới và `--release 17`, kiểm tra class major 61. Chạy bài test trên Java 17 runtime thực tế nếu tuyên bố Java 17 là minimum runtime.

**Bài 7 — Clean vs incremental:** chạy compile hai lần, ghi nhận task có được skip/up-to-date hay không; chạy clean compile để xem sự khác biệt. Không diễn giải một lượt thử thành cam kết chung cho mọi project.

## 17. Checklist cấu hình trước khi commit một build Java

- Project đang chọn Gradle hay Maven làm nguồn chân lý của build? Wrapper/plugin versions có được quản lý không?
- Source roots `main` / `test` / generated source có đúng và tách nhau không?
- Compiler JDK, `--release`, encoding có rõ và nhất quán với runtime hỗ trợ không?
- Compile classpath, runtime classpath, test path và processor path đã tách đúng chưa?
- Dependencies, phiên bản và conflict-resolution rules có được kiểm soát không?
- Multi-module/project dependencies được khai báo bằng graph edges, không chỉ hy vọng thứ tự script?
- Generated sources và resources có producer tasks, inputs/outputs và dependency tasks đúng?
- `build` hoặc `package` có thực sự chạy tests cần thiết, chứ không chỉ compile?
- JAR cần executable không, manifest/runtime dependencies được đóng gói thế nào?
- CI có tái hiện từ checkout sạch và chạy với toolchain/runtime đích không?

**Kết luận:** Gradle/Maven tổ chức mọi thứ *quanh* `javac`: nguồn, dependency, toolchain, task order, processors, tests, resources, packaging và khả năng tái lập. `javac` vẫn là nơi kiểm tra cú pháp/ngữ nghĩa và tạo bytecode trong một Java compilation thông thường. Hiểu đúng ranh giới đó giúp sửa lỗi ở đúng tầng và giữ build dễ duy trì.

## Tài liệu tham khảo

- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): tasks, source sets, compile/runtime configurations.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): JDK toolchain, `options.release` và reproducibility.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution và task graph.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, goals và bindings.
- [Apache Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): `maven.compiler.release`.
- [Oracle Java SE 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler options mà build tools cấu hình.
