# Compile task trong Java

Compile task là bước trong quy trình build nhận mã nguồn Java, dependency và cấu hình compiler rồi tạo ra các file `.class` cùng những file được sinh trong quá trình biên dịch. Task này có thể chạy trực tiếp bằng `javac`, được gọi từ Java Compiler API, hoặc được điều phối bởi Maven, Gradle hay Apache Ant.

Một compile task tốt phải xác định rõ JDK/compiler được dùng, phiên bản Java đích, source roots, classpath/module path, annotation processors, thư mục output và quy tắc xử lý warning. Khi các đầu vào này được khai báo nhất quán, build local và CI sẽ cho kết quả có thể lặp lại.

Bài học được kiểm tra trên Zulu/OpenJDK 24.0.2, Maven 3.9.12, Gradle 9.2.1 và Ant 1.10.15 (Ant libraries đi kèm Gradle). Các ví dụ mã nguồn nhắm Java 17; có thể điều chỉnh release theo baseline của dự án.

## 1. Compile task nằm ở đâu trong build?

Compile task chuyển source code thành bytecode. Nó thường là một bước trong build graph lớn hơn:

~~~text
Source files + dependencies + compiler options
                    |
                    v
              Compile task
                    |
          +---------+----------+
          |                    |
          v                    v
      .class files       Generated sources
          |                    |
          +----------+---------+
                     |
                     v
             Classes / resources
                     |
              +------+------+
              |             |
              v             v
           Test task      Package task
              |             |
              +------+------+
                     |
                     v
                JAR / WAR
~~~

Compile task thường xử lý:

- Source files trong `src/main/java` hoặc source roots được khai báo.
- Dependency cần thiết để type-check code.
- Compiler version, language release và encoding.
- Annotation processing và generated source.
- Compiler diagnostics: error, warning và vị trí dòng.
- Thư mục chứa class files.

Compile task không tự đồng nghĩa với chạy ứng dụng, chạy unit test hoặc đóng gói JAR. Build tool nối các task này thành lifecycle hoặc task graph.

## 2. Các bước chính khi compiler xử lý source

Khi `javac` biên dịch một nhóm source file, compiler thực hiện các công việc chính:

1. **Parse:** đọc ký tự source, kiểm tra cú pháp và tạo cấu trúc cú pháp.
2. **Enter:** đăng ký package, type, member và symbol để các file có thể tham chiếu lẫn nhau.
3. **Annotation processing:** chạy processor được cấu hình; processor có thể tạo source hoặc resource mới.
4. **Attribution và type checking:** phân giải tên, kiểm tra kiểu, overload, accessibility và generic constraints.
5. **Flow analysis:** kiểm tra definite assignment, unreachable code và các điều kiện luồng điều khiển.
6. **Lowering và code generation:** chuyển các cấu trúc ngôn ngữ thành bytecode phù hợp.
7. **Class file output:** ghi `.class` vào output directory.

Compiler có thể phát nhiều diagnostic trong một lần chạy. Một compile task chỉ được coi là thành công khi compiler trả exit code 0 hoặc API trả kết quả thành công; warning vẫn có thể xuất hiện nếu build chưa bật `-Werror`.

## 3. Biên dịch trực tiếp bằng `javac`

Tạo file `HelloToCompile.java`:

~~~java
public final class HelloToCompile {
    private HelloToCompile() {
    }

    public static void main(String[] args) {
        System.out.println("HELLO_FROM_COMPILE_TASK");
    }
}
~~~

Biên dịch cơ bản:

~~~text
javac HelloToCompile.java
~~~

Lệnh mặc định ghi `HelloToCompile.class` cạnh source. Trong dự án thật, nên tách class output khỏi source:

~~~text
javac --release 17 -encoding UTF-8 -g -d out HelloToCompile.java
~~~

Chạy class vừa tạo:

~~~text
java -cp out HelloToCompile
~~~

Stdout:

~~~text
HELLO_FROM_COMPILE_TASK
~~~

Trong lệnh này:

- `--release 17`: biên dịch theo ngôn ngữ, bytecode và API Java 17.
- `-encoding UTF-8`: quy định encoding của source.
- `-g`: sinh debug information.
- `-d out`: ghi class files vào thư mục `out`.

Thư mục output được compiler tạo nếu cần. Khi chạy, classpath phải trỏ tới thư mục gốc của package hierarchy, không trỏ thẳng vào file `.class`.

## 4. Các option thường dùng của `javac`

| Option | Công dụng |
|---|---|
| `--release 17` | Chọn Java release và API tương ứng |
| `-source 17` | Chọn cú pháp/ngôn ngữ source |
| `-target 17` | Chọn mức bytecode đích |
| `-d out` | Thư mục class output |
| `-classpath` / `-cp` | Tìm class và JAR dependency trên classpath |
| `--module-path` / `-p` | Tìm named modules |
| `--source-path` | Tìm source được tham chiếu |
| `-encoding UTF-8` | Encoding source |
| `-g` | Sinh debug information |
| `-parameters` | Lưu tên tham số để reflection đọc được |
| `-Xlint:all` | Bật các nhóm compiler warning |
| `-Werror` | Biến warning thành lỗi build |
| `-proc:none` | Tắt annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không biên dịch class |
| `-proc:full` | Chạy annotation processing và compilation |
| `--processor-path` | Nơi tìm annotation processors |
| `-processor` | Chỉ định processor class |
| `-s generated-sources` | Thư mục source được annotation processor sinh ra |
| `-Akey=value` | Truyền option riêng cho annotation processor |
| `-h native-headers` | Thư mục sinh native header cho JNI |
| `@args.txt` | Đọc options và source paths từ argument file |
| `-J-Xmx1g` | Truyền JVM option cho process chạy compiler |

### 4.1. Dùng `--release` thay cho chỉ `-source` và `-target`

`-source` và `-target` riêng lẻ không bảo đảm code chỉ dùng API tồn tại trong Java release cũ. Ví dụ compiler mới có thể chấp nhận cú pháp Java 17 và tạo bytecode Java 17, nhưng source vẫn vô tình gọi API chỉ có ở JDK 24.

`--release 17` kiểm tra source theo quy tắc ngôn ngữ và API của Java 17, đồng thời tạo bytecode tương thích release đó. Không dùng `--release` cùng `-source` hoặc `-target` trong cùng một lần compile.

### 4.2. Kiểm soát warning

Ví dụ compile nghiêm ngặt:

~~~text
javac --release 17 -Xlint:all -Werror -d out src\main\java\example\*.java
~~~

`-Xlint:all` bật nhiều nhóm warning; `-Werror` khiến warning trở thành lỗi. Trong dự án hiện hữu có thể bật từng nhóm như `-Xlint:deprecation` hoặc `-Xlint:unchecked`, xử lý warning rồi mới nâng lên `-Werror`.

Không dùng `-nowarn` để che warning trong CI. Warning có thể báo API deprecated, unchecked conversion, raw type hoặc vấn đề đáng xử lý trước khi phát hành.

## 5. Compile nhiều source file và dependency

Giả sử source tree:

~~~text
src/
  main/
    java/
      com/example/app/Main.java
      com/example/app/OrderService.java
      com/example/model/Order.java
lib/
  validation-api.jar
~~~

Biên dịch cả nhóm source:

~~~text
javac --release 17 -encoding UTF-8 -cp "lib/validation-api.jar" -d out src/main/java/com/example/app/Main.java src/main/java/com/example/app/OrderService.java src/main/java/com/example/model/Order.java
~~~

`javac` phân giải tham chiếu giữa các source được đưa vào cùng compilation. Nếu có nhiều file, có thể dùng source path hoặc argument file.

Ví dụ `compile.args`:

~~~text
--release
17
-encoding
UTF-8
-classpath
lib/validation-api.jar
-d
out
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/OrderService.java
src/main/java/com/example/model/Order.java
~~~

Chạy:

~~~text
javac @compile.args
~~~

Path separator của classpath phụ thuộc hệ điều hành: Windows dùng `;`, Linux/macOS dùng `:`. Đặt đường dẫn có khoảng trắng trong dấu quote theo shell đang sử dụng.

Không đặt mọi dependency vào source path. Classpath dùng cho class/JAR trên classpath; source path dùng để tìm source file; module path dùng để tìm named modules.

## 6. Classpath và module path

### Classpath

Classpath phù hợp với ứng dụng trên classpath hoặc thư viện chưa được đóng gói thành named module.

~~~text
javac --release 17 -cp "lib\library-a.jar;lib\library-b.jar" -d out src\Main.java
~~~

Khi chạy, phải truyền dependency cần thiết cho JVM:

~~~text
java -cp "out;lib\library-a.jar;lib\library-b.jar" com.example.Main
~~~

Compile class thành công không bảo đảm runtime tìm thấy dependency. Compile task và launch task phải dùng dependency tương ứng.

### Module path

Với Java Platform Module System, dependency là named module được đặt trên module path:

~~~text
javac --release 17 --module-path mods -d out src/module-info.java src/com/example/Main.java
~~~

Khi biên dịch nhiều module cùng lúc, dùng `--module-source-path` và cấu trúc thư mục theo module:

~~~text
javac --module-source-path src -d out -m com.example.core,com.example.app
~~~

Dùng `--module-path` cho module đã biên dịch và `--module-source-path` cho cây source của nhiều module. Không trộn hai khái niệm này với classpath mà không hiểu module graph.

## 7. Annotation processing trong compile task

Annotation processor đọc annotation và model của source trong quá trình compile. Processor thường dùng để sinh mã hoặc metadata, ví dụ mapper, metamodel, serializer hoặc dependency injection registry.

Các option liên quan:

- `--processor-path`: classpath riêng cho processor và dependency của nó.
- `--processor-module-path`: module path cho processor dạng module.
- `-processor`: chỉ định processor class cụ thể.
- `-proc:full`: chạy processor và compilation.
- `-proc:only`: chỉ chạy processor.
- `-proc:none`: tắt processor.
- `-s`: thư mục nhận source code được sinh.
- `-Akey=value`: cấu hình processor.

Ví dụ CLI:

~~~text
javac --release 17 -processorpath tools\my-processor.jar -processor com.example.GenerateMapper -s build\generated\sources -d build\classes src\main\java\com\example\*.java
~~~

Trong JDK hiện đại, annotation processing cần được bật/cấu hình rõ ràng bằng processor option hoặc `-proc:full`/`-proc:only`. Đừng dựa vào việc processor bất kỳ tự được tìm thấy trên classpath. Với Maven/Gradle, khai báo processor như dependency riêng của compile task.

Processor có thể tạo source mới, sau đó compiler tiếp tục xử lý các round tiếp theo. Khi compile fail, kiểm tra cả lỗi từ source ban đầu lẫn lỗi do generated source tạo ra. Không chỉnh tay generated source vì lần build sau sẽ sinh lại.

## 8. Gọi compiler từ Java bằng `JavaCompiler` API

Java Compiler API thuộc module `java.compiler`, cung cấp giao diện chuẩn để gọi compiler từ chương trình Java.

Các thành phần chính:

- `ToolProvider.getSystemJavaCompiler()`: lấy compiler của JDK đang chạy.
- `StandardJavaFileManager`: quản lý source file, class file và output location.
- `DiagnosticCollector`: thu warning/error và vị trí source.
- `JavaCompiler.getTask(...)`: tạo `CompilationTask`.
- `CompilationTask.call()`: thực hiện compile và trả về `true` nếu thành công.

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu chương trình chạy trên runtime không chứa compiler; hãy chạy compiler host bằng JDK đầy đủ.

Ví dụ `CompilerTaskDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilerTaskDemo {
    private CompilerTaskDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path source = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Files.createDirectories(output);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager fileManager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units =
                    fileManager.getJavaFileObjects(source.toFile());

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-Xlint:all",
                    "-d", output.toString());

            boolean success = Boolean.TRUE.equals(
                    compiler.getTask(null, fileManager, diagnostics,
                            options, null, units).call());

            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                System.err.println(diagnostic.getKind() + ":"
                        + diagnostic.getLineNumber() + ":"
                        + diagnostic.getMessage(Locale.ROOT));
            }

            if (!success) {
                throw new IllegalStateException("Compilation failed");
            }
        }

        System.out.println("COMPILATION_TASK_OK");
    }
}
~~~

Chương trình nhận source file và output directory từ arguments. `DiagnosticCollector` giữ thông tin lỗi/warning để ứng dụng có thể hiển thị hoặc lưu lại. Đóng `StandardJavaFileManager` sau khi compile để giải phóng resource.

`JavaCompiler` API còn hỗ trợ `JavaFileObject` tùy chỉnh, source trong memory, file manager tùy chỉnh và các hệ thống file khác. Với các use case phức tạp, có thể giữ lại `StandardJavaFileManager` để tái sử dụng giữa nhiều compilation task, thay vì tạo mới liên tục.

## 9. Maven: compile phase và Maven Compiler Plugin

Trong Maven lifecycle, compile main source được thực hiện ở phase `compile`; test source được biên dịch ở `test-compile`. Maven Compiler Plugin mặc định dùng `javac`.

Một POM cơ bản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>compile-task-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

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
        <configuration>
          <release>17</release>
          <showWarnings>true</showWarnings>
          <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
          </compilerArgs>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Lệnh thường dùng:

~~~text
mvn compile
mvn test-compile
mvn clean compile
mvn package
~~~

- `mvn compile`: chạy lifecycle đến compile, gồm các bước chuẩn bị trước đó.
- `mvn test-compile`: chạy cả compile main source và compile test source.
- `mvn clean compile`: xóa output cũ rồi compile lại.
- `mvn package`: chạy các phase cần thiết để compile, test và đóng gói theo lifecycle.

Main source mặc định ở `src/main/java`; test source ở `src/test/java`; class output ở `target/classes` và `target/test-classes`.

### 9.1. Annotation processor trong Maven

Khai báo processor qua `annotationProcessorPaths` của Maven Compiler Plugin:

~~~xml
<configuration>
  <release>17</release>
  <annotationProcessorPaths>
    <path>
      <groupId>com.example</groupId>
      <artifactId>my-processor</artifactId>
      <version>1.2.0</version>
    </path>
  </annotationProcessorPaths>
</configuration>
~~~

Processor path tách biệt với dependency runtime của ứng dụng. Chỉ khai báo processor mà dự án thật sự dùng và pin version để build ổn định. Kiểm tra generated source trong `target/generated-sources/annotations`.

## 10. Gradle: `JavaCompile`, `compileJava` và toolchain

Khi áp dụng plugin `java`, Gradle tạo compile task cho source set:

- `compileJava`: biên dịch main source.
- `compileTestJava`: biên dịch test source.
- `classes`: phụ thuộc compile và xử lý resource main.
- `testClasses`: chuẩn bị class/resource cho test.
- `build`: tổng hợp các task kiểm tra và đóng gói.

Ví dụ `build.gradle` dùng Groovy DSL:

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
    options.release = 17
    options.encoding = 'UTF-8'
    options.compilerArgs.addAll(['-Xlint:all', '-Werror'])
}
~~~

Chạy task:

~~~text
gradle compileJava
gradle compileTestJava
gradle classes
gradle build
~~~

Trong CI, ưu tiên Gradle Wrapper (`gradlew`/`gradlew.bat`) được commit cùng project để chuẩn hóa Gradle version. Toolchain chọn JDK/compiler dùng để compile; `options.release` chọn API và bytecode release đích.

### 10.1. Annotation processor trong Gradle

Khai báo processor ở configuration riêng:

~~~groovy
dependencies {
    annotationProcessor 'com.example:my-processor:1.2.0'
    testAnnotationProcessor 'com.example:my-test-processor:1.2.0'
}
~~~

Gradle đưa processor vào compile task tương ứng. Generated source của main thường nằm dưới `build/generated/sources/annotationProcessor/java/main`; không commit generated output nếu quy trình dự án không yêu cầu.

## 11. Apache Ant: `<javac>` task

Ant dùng target do dự án tự định nghĩa. Task `<javac>` gọi compiler để biên dịch source tree.

Ví dụ `build.xml`:

~~~xml
<project name="compile-task-demo" default="compile">
  <property name="src.dir" value="src/main/java"/>
  <property name="classes.dir" value="build/classes"/>

  <target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           release="17"
           encoding="UTF-8"
           debug="true"
           includeantruntime="false">
      <classpath>
        <pathelement location="lib/example-api.jar"/>
      </classpath>
      <compilerarg value="-Xlint:all"/>
      <compilerarg value="-Werror"/>
    </javac>
  </target>
</project>
~~~

Chạy:

~~~text
ant compile
~~~

Một số thuộc tính quan trọng:

- `srcdir`: thư mục chứa source.
- `destdir`: nơi ghi class files.
- `release`: Java release đích trên Ant version hỗ trợ thuộc tính này.
- `encoding`: encoding source.
- `debug`: sinh debug information.
- `includeantruntime="false"`: không tự thêm Ant runtime vào compile classpath.
- `<classpath>`: khai báo dependency.
- `<compilerarg>`: truyền option trực tiếp cho compiler.

Ant target có thể phụ thuộc target khác bằng `depends`, ví dụ `compile` phụ thuộc `init` để tạo thư mục output. Dùng `fork="true"` khi cần chạy compiler process riêng; mặc định Ant có thể gọi compiler trong JVM đang chạy Ant. Kiểm tra JDK/Ant version và compiler adapter trước khi dùng option đặc thù.

## 12. So sánh compile task giữa các công cụ

| Nội dung | `javac` | JavaCompiler API | Maven | Gradle | Ant |
|---|---|---|---|---|---|
| Cách điều khiển | CLI | Java code | Lifecycle/plugin | Task graph | XML target |
| Compiler | `javac` | Compiler SPI | Compiler plugin | `JavaCompile` | `<javac>` |
| Dependency | `-cp`, module path | File manager/options | Maven dependencies | Configurations | `<classpath>` |
| Output mặc định | Source folder nếu không dùng `-d` | Do file manager/options | `target/classes` | `build/classes/java/main` | `destdir` |
| Generated source | `-s` | File manager/processor | Plugin config | Processor configuration | Processor/compiler args |
| Incremental build | Không tự điều phối project graph | Do ứng dụng quản lý | Plugin/lifecycle | Task input/output và compiler analysis | Kiểm tra file theo task |
| Phù hợp | Compile trực tiếp, script | Ứng dụng cần gọi compiler | Dự án Maven | Dự án Gradle | Build XML hiện hữu |

Chọn công cụ theo build system của dự án. Không nên gọi `javac` thủ công để thay thế compile task của Maven/Gradle nếu làm vậy sẽ bỏ qua dependency graph, annotation processor, generated source, toolchain và incremental state mà build đã cấu hình.

## 13. Incremental compilation và clean build

Incremental compilation chỉ biên dịch lại phần cần thiết dựa trên input/output và quan hệ dependency mà build tool theo dõi. Gradle sử dụng task input/output và phân tích dependency để tránh chạy lại task khi không cần; Maven Compiler Plugin cũng có cơ chế incremental compilation; Ant `<javac>` so sánh source/class để quyết định file cần biên dịch.

Lợi ích:

- Giảm thời gian build khi thay đổi nhỏ.
- Tránh biên dịch lại toàn bộ module không liên quan.
- Giữ feedback loop nhanh trong quá trình phát triển.

Nhưng output cũ có thể che giấu vấn đề nếu build script, annotation processor, generated file hoặc dependency thay đổi mà task input chưa khai báo đúng.

Khi nghi ngờ stale class:

~~~text
mvn clean compile
~~~

~~~text
gradle clean compileJava
~~~

~~~text
ant clean compile
~~~

Target `clean` cần được định nghĩa trong Ant build file nếu muốn dùng lệnh trên. Với Gradle/Maven, task/phase clean đã được plugin/lifecycle cung cấp.

Không dùng clean build ở mọi bước nếu dự án có incremental build đáng tin cậy; dùng clean build như bước xác nhận khi debug build cache, generated source hoặc class output không đồng nhất.

## 14. Multi-module và compile task theo module

Trong dự án nhiều module, mỗi module có compile task riêng và dependency giữa module quyết định thứ tự thực thi.

Ví dụ Maven reactor:

~~~text
parent
  core
  service
  web
~~~

`service` phụ thuộc `core`, `web` phụ thuộc `service`. Maven reactor xây dependency trước rồi mới compile module phụ thuộc. Có thể chạy từ root:

~~~text
mvn compile
~~~

Hoặc chọn module và dependency cần thiết:

~~~text
mvn -pl web -am compile
~~~

Trong Gradle multi-project, task path có thể chỉ rõ module:

~~~text
gradle :core:compileJava
gradle :service:compileJava
gradle :web:compileJava
~~~

Khi build module trực tiếp, bảo đảm dependency project đã được build/resolve. Tránh copy class output của module khác vào classpath thủ công nếu build system đã có project dependency.

## 15. Toolchain, compiler version và Java release

Có ba khái niệm cần phân biệt:

- **JDK chạy build:** JVM thực thi Maven/Gradle/Ant.
- **Compiler toolchain:** JDK/compiler thực sự được dùng cho compile task.
- **Release đích:** mức Java language/API/bytecode mà artifact phải tương thích.

Một build có thể chạy bằng JDK 24, dùng compiler JDK 24 và tạo class tương thích Java 17 bằng `--release 17`. Điều này không tự bảo đảm mọi plugin hoặc annotation processor chạy được trên mọi JDK; kiểm tra compatibility riêng.

Maven có thể dùng Maven Toolchains Plugin để chọn JDK compiler phù hợp. Gradle có Java toolchains trong `java { toolchain { ... } }`. Ant có thể chọn compiler executable/adapter theo cấu hình và môi trường.

Ghi rõ JDK vendor/version, compiler plugin, Gradle Wrapper và release target trong CI. Không dựa vào `JAVA_HOME` của developer nếu build cần cùng một compiler giữa mọi máy.

## 16. Diagnostics và kiểm soát chất lượng compile

Compiler diagnostic thường gồm:

- Kind: `ERROR`, `WARNING`, `MANDATORY_WARNING` hoặc `NOTE`.
- Source file hoặc compilation unit.
- Line/column.
- Message mô tả vấn đề.

Một compile task cho CI nên bật warning phù hợp:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src\main\java\*.java
~~~

Nếu codebase chưa thể bật `-Werror` ngay, bật `-Xlint:all`, phân loại warning hiện có và xử lý dần. Tránh tắt toàn bộ warning chỉ để build xanh.

Các quy tắc hữu ích:

- Pin compiler release và encoding.
- Giữ debug information nếu cần stack trace/source mapping.
- Dùng `-parameters` nếu framework cần tên parameter qua reflection.
- Tách annotation processor path khỏi dependency runtime.
- Đặt generated source/output vào thư mục riêng.
- Đảm bảo CI fail khi compile task fail.
- Không bỏ qua diagnostic chỉ vì local IDE vẫn biên dịch được.

## 17. Ví dụ Java 17+: compile bằng CLI và JavaCompiler API

Tạo `HelloToCompile.java`:

~~~java
public final class HelloToCompile {
    private HelloToCompile() {
    }

    public static void main(String[] args) {
        System.out.println("HELLO_FROM_COMPILE_TASK");
    }
}
~~~

Tạo `CompilerTaskDemo.java` bằng mã ở phần 8. Biên dịch CLI fixture:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -g -d cli-out HelloToCompile.java
java -cp cli-out HelloToCompile
~~~

Stdout:

~~~text
HELLO_FROM_COMPILE_TASK
~~~

Biên dịch runner API:

~~~text
javac --release 17 -Xlint:all -Werror -d runner-out CompilerTaskDemo.java
~~~

Gọi `CompilationTask` để compile source:

~~~text
java -cp runner-out CompilerTaskDemo HelloToCompile.java api-out
~~~

Stdout của compiler runner:

~~~text
COMPILATION_TASK_OK
~~~

Chạy class được tạo bởi API:

~~~text
java -cp api-out HelloToCompile
~~~

Stdout:

~~~text
HELLO_FROM_COMPILE_TASK
~~~

Ví dụ này chứng minh compile task có thể được gọi từ CLI hoặc từ Java code. Cả hai cách đều cần compiler host và output path hợp lệ.

## 18. Ví dụ compile task trong Maven, Gradle và Ant

Một fixture `HelloToCompile.java` giống phần 17 có thể đặt trong `src/main/java`.

### Maven

Dùng POM ở phần 9 rồi chạy:

~~~text
mvn compile
java -cp target/classes HelloToCompile
~~~

Stdout:

~~~text
BUILD_TOOL_COMPILE_OK
~~~

### Gradle

Dùng `build.gradle` ở phần 10, đặt source trong `src/main/java`, sau đó chạy:

~~~text
gradle compileJava
java -cp build/classes/java/main HelloToCompile
~~~

Stdout:

~~~text
BUILD_TOOL_COMPILE_OK
~~~

### Ant

Dùng `build.xml` ở phần 11, đặt source trong `src/main/java`, sau đó chạy:

~~~text
ant compile
java -cp build/classes HelloToCompile
~~~

Stdout:

~~~text
ANT_COMPILE_OK
~~~

Khi thử nghiệm, nội dung `HelloToCompile.java` cần in đúng dòng tương ứng với fixture của từng build. Output directory của mỗi công cụ khác nhau; lệnh `java -cp` phải trỏ đúng thư mục chứa package root.

## 19. Troubleshooting compile task

### `cannot find symbol`

**Nguyên nhân:** thiếu import, source file không được đưa vào compilation, classpath thiếu dependency hoặc tên type sai.

**Cách xử lý:** kiểm tra source roots, `-cp`, module path, package declaration và dependency version. Với build tool, xem compile classpath của task thực tế.

### `package ... does not exist`

**Nguyên nhân:** JAR thiếu, dependency scope sai hoặc thư viện là named module nhưng đang đặt trên classpath/module path không đúng.

**Cách xử lý:** kiểm tra dependency tree, `--class-path`, `--module-path` và `module-info.java`.

### `invalid source release` hoặc `release version not supported`

**Nguyên nhân:** compiler JDK quá cũ so với release target.

**Cách xử lý:** chọn toolchain đủ mới hoặc giảm release theo baseline hỗ trợ. Kiểm tra `javac -version` và JDK mà Maven/Gradle thật sự sử dụng.

### Code biên dịch được trên JDK mới nhưng lỗi khi chạy JDK cũ

**Nguyên nhân:** dùng `-source`/`-target` mà không giới hạn API, hoặc build task không áp dụng release như mong muốn.

**Cách xử lý:** dùng `--release` hoặc cấu hình `maven.compiler.release`/`options.release`, sau đó chạy test trên runtime target.

### `ToolProvider.getSystemJavaCompiler()` trả `null`

**Nguyên nhân:** chương trình đang chạy trên runtime không có compiler hoặc runtime image bị lược bỏ module compiler.

**Cách xử lý:** chạy chương trình host bằng JDK đầy đủ có module `jdk.compiler`, hoặc cấu hình compiler service phù hợp.

### Annotation processor không chạy

**Nguyên nhân:** processor không nằm trên processor path, chưa bật processing, sai processor class hoặc dependency processor không resolve được.

**Cách xử lý:** cấu hình `--processor-path`, `--processor-module-path`, `-processor` hoặc `-proc:full`; khai báo `annotationProcessorPaths` trong Maven hay `annotationProcessor` trong Gradle.

### Generated source không được compile

**Nguyên nhân:** generated source output path không đúng, processor không chạy hoặc processor phát sinh lỗi.

**Cách xử lý:** kiểm tra `-s`, generated-source directory, diagnostic của processor và các compilation round. Không sửa trực tiếp file generated.

### Build local thành công nhưng CI thất bại

**Nguyên nhân:** khác JDK/toolchain, environment variable, encoding, dependency cache, file case sensitivity hoặc compiler option.

**Cách xử lý:** dùng wrapper/toolchain, pin dependency/plugin version, đặt encoding UTF-8 và chạy clean build trên CI.

### Build không biên dịch lại sau khi đổi dependency/generated source

**Nguyên nhân:** task input/output không đầy đủ hoặc incremental state/cache cũ.

**Cách xử lý:** chạy clean compile để xác minh, kiểm tra khai báo dependency và annotation processor, sau đó sửa task configuration để incremental build theo dõi đủ inputs.

### Warning làm build fail

**Nguyên nhân:** có `-Werror` hoặc warning được cấu hình thành error.

**Cách xử lý:** đọc đúng diagnostic, sửa code hoặc điều chỉnh lint category có chủ đích. Không bỏ toàn bộ `-Werror` chỉ để che một warning.

## 20. Quy trình thiết kế compile task đáng tin cậy

1. Chọn JDK/toolchain compiler phù hợp với dự án.
2. Xác định Java release mà artifact phải hỗ trợ.
3. Khai báo source roots và output directories.
4. Phân biệt classpath, module path và processor path.
5. Khai báo annotation processors và generated-source output tường minh.
6. Đặt source encoding UTF-8.
7. Bật debug symbols khi cần điều tra runtime.
8. Bật compiler lint phù hợp; nâng dần lên `-Werror`.
9. Để build tool quản lý task graph và dependency thay vì tự ghép classpath thủ công.
10. Dùng incremental compilation cho vòng phát triển nhanh.
11. Chạy clean compile khi kiểm tra thay đổi compiler, plugin, processor hoặc dependency.
12. Chạy test/package sau compile để xác nhận class output hoạt động trong runtime thực tế.
13. Pin wrapper, plugin, toolchain và dependency version trong CI.
14. Lưu compiler diagnostic trong build log để có thể truy vết.

## 21. Checklist trước khi đưa compile task vào CI

- [ ] Đã xác định JDK chạy build và compiler toolchain.
- [ ] Đã đặt release target bằng `--release`/`options.release`.
- [ ] Đã khai báo source roots và class output.
- [ ] Classpath/module path chứa đúng dependency compile.
- [ ] Annotation processor được khai báo rõ ràng và pin version.
- [ ] Generated source có thư mục riêng và không bị chỉnh tay.
- [ ] Source encoding được đặt thành UTF-8.
- [ ] Debug information và parameter metadata phù hợp yêu cầu runtime.
- [ ] Compiler warnings được bật và xử lý có chủ đích.
- [ ] Compile failure làm CI thất bại.
- [ ] Maven/Gradle/Ant plugin và build tool version được pin.
- [ ] Clean build thành công trên CI.
- [ ] Output class chạy được trên runtime target.
- [ ] Incremental build không che giấu source hoặc generated output cũ.

## 22. Tài liệu tham khảo

- Oracle JDK 24 — `javac` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Java SE 24 — `JavaCompiler` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 24 — `JavaCompiler.CompilationTask`: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Apache Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Maven Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle `JavaCompile` API: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html
- Apache Ant `<javac>` task: https://ant.apache.org/manual/Tasks/javac.html

Compile task biến source thành bytecode theo compiler, dependency và release đã khai báo. `javac` phù hợp cho compile trực tiếp; JavaCompiler API phù hợp khi ứng dụng cần gọi compiler; Maven, Gradle và Ant điều phối compile task trong build graph. Chuẩn hóa toolchain, `--release`, processor path, diagnostics và output directory giúp build đáng tin cậy từ máy phát triển tới CI.