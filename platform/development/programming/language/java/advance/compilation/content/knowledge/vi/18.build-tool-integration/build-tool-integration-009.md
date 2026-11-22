# Tái hiện lệnh biên dịch Java từ log build và môi trường CI

## 1. Mục tiêu và ý nghĩa

Khi một dự án **biên dịch thành công trên máy cá nhân nhưng thất bại trên CI**, câu hỏi cần giải quyết không chỉ là “CI đã chạy lệnh nào?” mà là: **trình biên dịch Java đã nhận những đầu vào, tùy chọn và môi trường nào?** Tái hiện được lần biên dịch giúp phân biệt lỗi mã nguồn, cấu hình build, JDK, dependency, annotation processor và khác biệt hệ điều hành.

Sau bài này, người học có thể:

- Truy vết từ lệnh gọi Gradle/Maven trong CI đến tác vụ biên dịch và cấu hình thực tế của Java compiler.
- Thu thập đủ bằng chứng: JDK, thư mục làm việc, danh sách tệp nguồn, classpath/module path, đích xuất, encoding, target release, processor và biến môi trường liên quan.
- Dựng một lệnh **javac tương đương về ngữ nghĩa** với build, hoặc xác định trung thực khi log không đủ để dựng lệnh chính xác.
- Chạy lại trên máy phát triển hoặc runner có kiểm soát, so sánh lỗi và xác minh kết quả.

**Phân biệt ba tầng lệnh:**

| Tầng | Ví dụ | Vai trò |
| --- | --- | --- |
| Lệnh pipeline | ./gradlew build, ./mvnw verify | Điểm vào của job CI, có thể chạy nhiều tác vụ trước/sau compile |
| Tác vụ build | Gradle :compileJava, Maven compiler:compile | Chọn nguồn, dependency, toolchain, processor và cấu hình compiler |
| Lần gọi compiler | javac với -d, --release, -cp và các tệp .java; hoặc Java Compiler API | Hoạt động biên dịch cụ thể cần tái hiện |

Không đồng nhất lệnh **build** với lệnh **javac**. Gradle hoặc Maven có thể dùng compiler chạy trong cùng JVM qua API, qua worker, hoặc qua tiến trình fork. Vì vậy **không phải lần biên dịch nào cũng có một dòng shell javac nguyên văn trong log**. Khi thiếu dữ liệu, hãy ghi “lệnh javac tái dựng từ cấu hình” thay vì khẳng định đó là command line thực sự mà CI đã thực thi.

## 2. Mô hình đầu vào của một lần biên dịch

Có thể xem kết quả là hàm của các nhóm dữ liệu:

~~~text
Đầu ra .class và diagnostics
    = Compiler/JDK + phiên bản/cấu hình build
    + Source files + Java options
    + Classpath / module path / processor path
    + Generated sources + working directory
    + Environment + dependency artifacts
~~~

Các biến quan trọng cần ghi lại:

| Nhóm | Dữ liệu cần đối chiếu | Vì sao ảnh hưởng |
| --- | --- | --- |
| Compiler | Đường dẫn javac thực, nhà phân phối và phiên bản JDK | Tính năng ngôn ngữ, API hỗ trợ và cách chẩn đoán khác nhau |
| Build tool | Gradle/Maven wrapper, plugin compiler, build scripts, profile | Có thể đổi tham số, chọn task, chọn toolchain |
| Source | Tập tệp .java chính xác; nguồn do generator tạo; module-info.java | Thiếu một tệp hoặc sai source root có thể gây cannot find symbol |
| Target | --release hoặc -source/-target; -d; -s | Quy định API, bytecode và vị trí class/source được sinh |
| Dependencies | JAR và directory trên -cp/--class-path; --module-path | Khai báo dependencies không đồng nghĩa classpath compile thực tế |
| Processing | -processorpath/--processor-path, -processor, -A..., -proc:... | Ảnh hưởng code generation và thứ tự vòng xử lý annotation |
| Environment | OS, architecture, working directory, JAVA_HOME, PATH, locale/encoding, biến được build đọc | Có thể làm đổi JDK, đường dẫn và cách giải quyết tệp |
| CI execution | Commit, container image, runner image, cache, script và task đã chạy | Làm rõ có thực sự compile hay chỉ lấy kết quả có sẵn |

**Nguyên tắc:** Nếu cần so sánh hai môi trường, hãy so sánh **giá trị đã được build resolve**, không chỉ so sánh dòng khai báo trong build.gradle hoặc pom.xml. Chẳng hạn, hai cấu hình đều viết “Java 21” nhưng một task dùng compiler JDK 21 qua toolchain, task kia dùng JDK khác vì override hoặc cấu hình fork.

## 3. Đọc log và nhận diện sự kiện biên dịch

### 3.1. Đọc từ CI theo chiều nguyên nhân

1. Xác định commit/SHA, job, bước thất bại, thư mục mà bước chạy và lệnh shell của bước đó.
2. Xác định runtime JDK và compiler JDK; nếu có toolchain, không suy ra compiler từ riêng java -version.
3. Tìm task/goal compile đầu tiên thực sự thất bại, thay vì chỉ đọc thông báo tổng kết FAILED ở cuối.
4. Tìm thông tin compiler option, nguồn đầu vào, classpath, generated source và annotation processing.
5. Giữ nguyên **diagnostic đầu tiên có nguyên nhân** cùng vài dòng ngữ cảnh; lỗi cuối đôi khi chỉ là hệ quả.
6. Ghi rõ task **EXECUTED**, **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE** hay bị bỏ qua (tên trạng thái tùy công cụ). Nếu compile bị cache/skip, log đó không chứng minh compiler đã chạy.

Một log ví dụ rút gọn:

~~~text
> Task :compileJava FAILED
error: package example.generated does not exist
import example.generated.GeneratedConfig;
                        ^
1 error

FAILURE: Build failed with an exception.
Execution failed for task ':compileJava'.
~~~

Thông báo task cho biết **vị trí lỗi**. Nó chưa đủ để kết luận phụ thuộc nào thiếu, toolchain nào dùng, hoặc command line cụ thể. Hãy kiểm tra nguồn GeneratedConfig được tạo từ đâu và task generator có nằm trong dependency graph của compileJava hay không.

### 3.2. Lấy thông tin từ Gradle

Tại thư mục gốc dự án có Gradle Wrapper (trên Linux/macOS):

~~~bash
./gradlew --version
java -version
javac -version
./gradlew --no-daemon --no-build-cache --rerun-tasks compileJava --info --stacktrace
~~~

- **--version** cho biết Gradle và JVM chạy Gradle; **không tự chứng minh** compiler task dùng JDK đó.
- **--info** giúp xem task execution và một phần chi tiết biên dịch. Khi cần điều tra sâu có thể dùng **--debug**, nhưng log nhiều và có thể lộ đường dẫn hay cấu hình nhạy cảm.
- **--rerun-tasks** yêu cầu chạy lại task, **--no-build-cache** tránh lấy đầu ra từ build cache, **--no-daemon** hữu ích khi giảm ảnh hưởng của daemon cũ. Đây là lựa chọn *chẩn đoán*, không phải bộ cờ phải áp dụng cho mọi CI.
- Nếu lệnh tác vụ có tên khác, dùng đúng đường dẫn task mà CI chạy, ví dụ **:service:compileJava**; nếu dự án có thêm test, integrationTest, Kotlin hoặc Java module khác, việc chạy mỗi compileJava có thể chưa tái hiện toàn pipeline.
- Nếu task dùng compiler API, Gradle không nhất thiết in ra một lệnh javac có thể copy/paste. Cần xem cấu hình đã resolve thay vì suy diễn từ vài dòng log.

Với build script Groovy, có thể **tạm thời thêm vào bản sao dự án dùng để chẩn đoán** đoạn sau để quan sát đầu vào JavaCompile ngay trước khi task chạy:

~~~groovy
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType(JavaCompile).configureEach {
    doFirst {
        println "DIAG task = " + path
        println "DIAG compiler = " + javaCompiler.get().executablePath.asFile
        println "DIAG release = " + options.release.orNull
        println "DIAG encoding = " + options.encoding
        println "DIAG destination = " + destinationDirectory.get().asFile
        println "DIAG source files = " + source.files.sort()
        println "DIAG classpath = " + classpath.files
        println "DIAG extra compiler args = " + options.compilerArgs
    }
}
~~~

Đây là **thông tin cấu hình task**, chưa phải danh sách toàn bộ tham số hiệu lực được Java Compiler API nhận. Đặc biệt, option mặc định, source path, module path và processor path có thể được Gradle tổ chức theo cơ chế riêng. Đối chiếu plugin, toolchain, annotationProcessor configuration và cấu hình task nếu cần bản tái dựng chính xác hơn. Không giữ đoạn ghi log chẩn đoán trong thay đổi sản phẩm ngoài ý muốn.

Trong Gradle Groovy DSL, ví dụ khai báo rõ compiler JDK 21 nhưng tạo bytecode/API cho Java 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Ở ví dụ này, **JDK dùng để biên dịch là 21**, còn **--release 17** giới hạn ngôn ngữ/API/bytecode theo Java 17. Hai giá trị trả lời hai câu hỏi khác nhau.

### 3.3. Lấy thông tin từ Maven

Tại thư mục có Maven Wrapper:

~~~bash
./mvnw --version
java -version
javac -version
./mvnw -B -ntp -e -X -DskipTests compile
~~~

- **-B** dùng batch mode, **-ntp** giảm output chuyển tải dependency, **-e** in stack trace, **-X** bật debug.
- Tìm mục **maven-compiler-plugin:compile**, source roots, compile classpath, compiler release/options và cấu hình fork/toolchain.
- Trong nhiều phiên bản Maven Compiler Plugin, thông tin dòng lệnh compiler hoặc tệp đối số dùng để debug có thể được tạo khi lỗi hoặc bật verbose; kiểm tra **phiên bản plugin thực tế** và tệp được tạo, không giả định vị trí luôn giống nhau.
- Với Maven multi-module, lệnh **compile** ở root có thể đi qua nhiều module; để tái hiện lỗi một module cụ thể, ghi lại reactor/project selection và các profile hoạt động.

Một cấu hình Maven ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Cấu hình release không thay thế việc xác nhận **compiler JDK**. Nếu CI chạy Maven bằng một JDK và dùng Maven Toolchains hoặc compiler fork bằng JDK khác, phải xác định cả hai.

### 3.4. Chọn nguồn bằng chứng khi log thiếu

Thứ tự hữu ích: **dòng task/goal đã chạy → verbose/debug log → cấu hình task/plugin đã resolve → tập tệp/dependency đã resolve → lệnh tái dựng và kết quả kiểm chứng**.

Khi log thiếu classpath hoặc tham số nội bộ, hãy ghi trạng thái “chưa xác định” và bổ sung quan sát tại task/plugin. Đừng tự điền đường dẫn JAR, đoán phiên bản hoặc thay thế task bằng một lệnh có vẻ giống.

## 4. Định danh đúng môi trường CI

Chạy các lệnh dưới đây **trong cùng job/container và gần bước compile nhất có thể**; đây là ví dụ cho Linux runner:

~~~bash
pwd
command -v java
command -v javac
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'LANG=%s\n' "$LANG"
./gradlew --version
~~~

Nếu job dùng Maven, thay dòng cuối bằng **./mvnw --version**. Trên Windows PowerShell, sử dụng:

~~~powershell
Get-Location
Get-Command java,javac | Select-Object Name,Source
java -version
javac -version
$env:JAVA_HOME
.\gradlew.bat --version
~~~

**Đọc đúng ý nghĩa bằng chứng:**

- **java -version** phản ánh Java launcher mà PATH tìm được; **javac -version** phản ánh compiler ở PATH. Build task có thể chọn Java compiler qua toolchain khác.
- **JAVA_HOME** có thể rỗng hoặc khác vị trí compiler do PATH/toolchain; phải đối chiếu compiler được task chọn.
- **pwd/Get-Location** giúp diễn giải các đường dẫn tương đối trong script, argfile, classpath và source list.
- Hệ điều hành làm thay đổi path separator của classpath: **:** trên Linux/macOS, **;** trên Windows; đồng thời khác dấu phân cách thư mục, cách quote và độ phân biệt chữ hoa/thường của filesystem.
- Repository commit, submodule checkout, biến cấu hình, cache dependency, generated files và artifact đã tải đều là một phần môi trường; chỉ cùng major version JDK chưa bảo đảm tái hiện chính xác.
- Tránh in nguyên toàn bộ biến môi trường hoặc file settings chứa token. Chỉ log biến cần thiết và che thông tin bí mật.

Ví dụ job GitHub Actions cho một lần điều tra trên Ubuntu:

~~~yaml
name: reproduce-java-compile
on:
  workflow_dispatch:

jobs:
  compile:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Show environment
        run: |
          pwd
          java -version
          javac -version
          ./gradlew --version
      - name: Re-run Java compilation
        run: ./gradlew --no-daemon --no-build-cache --rerun-tasks compileJava --info --stacktrace
~~~

Workflow này minh họa cách thu bằng chứng, **không mặc định là CI gốc**. Nếu lỗi gốc xuất hiện trong container riêng, trong task khác, với biến profile khác hoặc trước/sau một bước code generation, phải giữ các điều kiện đó khi tái hiện. Việc chuyển sang runner/JDK mới có thể che lỗi thay vì tái hiện lỗi.

## 5. Từ cấu hình đã tìm được đến một lệnh javac

### 5.1. Bản đồ tùy chọn thường gặp

| Thông tin trong build | Đối số javac tương ứng | Lưu ý |
| --- | --- | --- |
| Java release | --release 17 | Yêu cầu compiler đủ mới để hỗ trợ release này |
| Mã hóa nguồn | -encoding UTF-8 | Quyết định cách đọc ký tự trong .java |
| Thư mục đầu ra | -d out | Chứa .class theo package/module |
| Dependencies classpath | -cp path1:path2 | Dùng ; thay : trên Windows |
| Java modules | --module-path modules | Không đánh đồng với -cp; cần cấu hình module-info và module resolution |
| Sinh nguồn từ processor | -s generated | Nơi đặt tệp .java do annotation processor tạo |
| Processor dependencies | -processorpath processor-jars | Phân biệt với compile classpath |
| Processor options | -Akey=value | Truyền vào annotation processor |
| Thông tin debug | -g hoặc -g:none | Ảnh hưởng metadata trong class file |
| Tên tham số | -parameters | Giữ tên parameter cho reflection |
| Danh sách file/args dài | @compile.args | Javac đọc đối số từ tệp |

**--release** thường nên được ưu tiên khi cần tương thích API của một Java release cũ: nó kiểm soát cả ngôn ngữ, bytecode và API công khai của Java platform. **-source** và **-target** chỉ kiểm soát lần lượt cú pháp và đích bytecode; chúng không tự giới hạn API chuẩn được dùng khi compiler chạy trên JDK mới. Không ghép **--release** với **-source/-target** trong cùng lời gọi.

Một lệnh tái dựng minh họa trên Linux/macOS khi task đã resolve compiler, nguồn và phụ thuộc:

~~~bash
/path/to/jdk-21/bin/javac \
  --release 17 \
  -encoding UTF-8 \
  -cp "lib/api.jar:lib/model.jar" \
  -d build/classes/java/main \
  @compile-sources.args
~~~

Đây là **cú pháp mô phỏng**, không chạy độc lập khi chưa có JDK, hai JAR và tệp argfile đúng như đã khai báo. Các đường dẫn phải lấy từ build thực tế và được resolve từ đúng working directory. Nếu project dùng module path hoặc annotation processor thì phải bổ sung tham số tương ứng.

### 5.2. Tệp @argfile

Với nhiều tệp nguồn hoặc classpath rất dài, có thể lưu đối số vào tệp UTF-8 để tránh giới hạn độ dài command line và giữ cấu hình dễ đối chiếu.

Ví dụ nội dung **compile.args**:

~~~text
--release
17
-encoding
UTF-8
-d
out
src/main/java/example/Main.java
~~~

Thực thi:

~~~bash
javac @compile.args
~~~

Javac đọc các tham số theo thứ tự như thể chúng nằm trên dòng lệnh. **Đường dẫn tương đối bên trong argfile được giải quyết từ thư mục làm việc hiện tại**, không tự động từ thư mục chứa argfile. Với đường dẫn có khoảng trắng, cần đặt tên đường dẫn trong dấu nháy kép phù hợp cú pháp argfile. Không sử dụng wildcard file nguồn bên trong argfile với kỳ vọng javac sẽ mở rộng nó như shell; hãy liệt kê từng tệp.

Nếu muốn kiểm chứng cấu hình lớn, lưu bản trích xuất tùy chọn và danh sách nguồn thành artifact chỉ chứa dữ liệu không nhạy cảm; lưu thêm checksum của JAR khi cần phân biệt dependency có cùng tên nhưng byte khác nhau.

## 6. Ví dụ chạy được: tái hiện một lần biên dịch bằng JDK 21

Ví dụ cố ý độc lập với Gradle/Maven để kiểm tra bản chất lệnh javac. Yêu cầu: **JDK 21**, terminal đặt tại thư mục gốc dự án và cây tệp như sau:

~~~text
demo/
└── src/
    └── main/
        └── java/
            └── example/
                └── Main.java
~~~

Nội dung **src/main/java/example/Main.java**:

~~~java
package example;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("CI compile reproducible");
    }
}
~~~

Từ thư mục **demo**, Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/main/java/example/Main.java
java -cp out example.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/main/java/example/Main.java
java -cp out example.Main
~~~

Đầu ra chuẩn của **lệnh java**:

~~~text
CI compile reproducible
~~~

Lệnh **javac** thành công không nhất thiết in gì ra stdout. Tệp kết quả là **out/example/Main.class**. Có thể kiểm tra:

~~~bash
javap -verbose -classpath out example.Main
~~~

Trong kết quả, **major version: 61** biểu thị bytecode Java 17. Điều này minh họa việc compiler chạy trên JDK 21 vẫn có thể tạo bytecode theo Java 17 nhờ **--release 17**; việc một JVM Java 17 chạy được chương trình còn phụ thuộc runtime và dependency thực tế.

Để dùng argfile, thay phần tùy chọn trong lệnh javac bằng nội dung **compile.args** ở mục 5.2, rồi chạy **javac @compile.args** tại cùng thư mục demo. Kết quả biên dịch và stdout của ví dụ này giữ nguyên.

### 6.1. Khi có dependencies hoặc generated sources

Nếu nguồn import thư viện ngoài, bản tái hiện phải cung cấp đúng compile classpath/module path; không lấy runtimeClasspath thay compileClasspath theo thói quen. Một lỗi **package ... does not exist** có thể xuất phát từ JAR bị thiếu, dependency có phiên bản khác, artifact không được tải, sai source root hoặc source generated chưa tồn tại.

Nếu dùng annotation processors, hãy xác định:

1. Tên/phiên bản processor và JAR phụ thuộc của processor.
2. Processor path hoặc processor module path thực tế.
3. Tùy chọn **-A...**, chế độ processing, vị trí source/class được sinh.
4. Bước generator được chạy trước compile hay thuộc vòng xử lý annotation của chính compiler.
5. File sinh ra là đầu vào đã có sẵn hay sản phẩm của lần compile.

Chỉ copy tập .java từ thư mục nguồn viết tay rồi bỏ qua generator thường không tái hiện cùng vấn đề. Ngược lại, copy tệp sinh ra từ máy khác có thể che lỗi task dependency hoặc môi trường.

## 7. Quy trình tái hiện một lỗi CI có kiểm soát

### Bước 1 — Chốt bằng chứng của lần thất bại

Ghi commit, đường dẫn job/step, OS/image, working directory, lệnh pipeline, task/goal lỗi, timestamp và thông báo đầu tiên. Đảm bảo log thuộc **cùng build attempt**; đừng trộn log của các retry có image hoặc commit khác nhau.

### Bước 2 — Tách build tool JVM khỏi compiler JDK

Lấy kết quả java, javac, wrapper và cấu hình toolchain/fork. Nếu compiler thực tế là JDK 17 nhưng release yêu cầu 21, lỗi tương thích JDK là giả thuyết mạnh hơn lỗi source.

### Bước 3 — Chốt tập đầu vào đã resolve

Thu thập source files, generated sources, compile classpath, module path, processor path, Java options, đích xuất và encoding. Với dependency, dùng tọa độ artifact và hash nếu có nghi ngờ hai bản JAR khác nhau.

### Bước 4 — Tái hiện bằng chính build command trước

Trên đúng commit và môi trường tương ứng, chạy lại đúng task/goal với cache được kiểm soát. Thử tái hiện qua build tool **trước khi** chuyển sang javac trực tiếp vì build tool có thể chạy generator, transform dependency hoặc compiler plugin.

### Bước 5 — Dựng lệnh javac tương đương khi cần cô lập

Dùng compiler tương ứng và toàn bộ option/đầu vào đã xác minh. Nếu thất bại khi build tool chạy nhưng javac độc lập thành công, hãy tìm phần không được tái dựng: generated sources, plugin hook, classpath hoặc module path, annotation processing, working directory, JVM flags, compiler daemon/API hay thứ tự task.

### Bước 6 — So sánh kết quả có tiêu chí

So sánh exit code, diagnostic đầu tiên (file/line/symbol), đầu ra .class, nguồn được sinh và tùy chọn thực sự dùng. Thành công khi sửa một biến không đủ chứng minh biến đó là nguyên nhân duy nhất: cần lặp lại với cấu hình gốc để thấy lỗi quay lại, nếu điều kiện cho phép.

Một bảng điều tra ví dụ:

| Thành phần | CI lỗi | Máy tái hiện | Nhận định |
| --- | --- | --- | --- |
| Source commit | Cùng SHA | Cùng SHA | Đã loại trừ khác mã nguồn |
| Runtime Java | 21 | 21 | Giống major, còn cần kiểm tra toolchain |
| Compiler task | JDK 17 | JDK 21 | Khác compiler |
| Requested release | 21 | 21 | JDK 17 không hỗ trợ compile release 21 |
| Kết quả | Unsupported release | Compile thành công | Ưu tiên sửa JDK/toolchain |

Bảng này là **tình huống giả định** để minh họa phương pháp, không phải log thực của một dự án cụ thể.

## 8. Những lỗi phổ biến và cách phân tích

| Triệu chứng | Khả năng cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| error: release version 21 not supported | javac đang chạy không đủ mới | Kiểm tra compiler executable của task và javac -version |
| error: invalid source release: 21 | JDK/compiler plugin đang dùng bản quá cũ | Kiểm tra toolchain, JavaCompile, Maven compiler config |
| package ... does not exist | Thiếu JAR, module, nguồn generated hoặc compile source root | In resolved compile classpath, module path, danh sách source |
| cannot find symbol | Thiếu loại/biến/phương thức hoặc nguồn/generated code lệch phiên bản | Xem lỗi đầu tiên và symbol, kiểm tra processor và dependency |
| package ... is not visible | Cấu hình JPMS/module exports/reads sai | So module-info.java, --module-path, --add-modules, exports |
| invalid flag / bad class file | Compiler option/plugin hoặc JAR không tương thích | Đối chiếu command, toolchain và bytecode version |
| CI xanh dù máy lỗi | Cache, task skip, profile hoặc nguồn đầu vào khác | Tắt cache ở lượt chẩn đoán; xác nhận compile thực sự chạy |
| CI lỗi nhưng javac độc lập chạy được | Bản tái dựng thiếu một đầu vào/hook của build | Diff source, processor, classpath, flags, working directory |

**Đừng sửa ngược theo triệu chứng:** lỗi classpath không nên được “chữa” bằng việc xóa import; lỗi JDK không nên được giải bằng việc tùy tiện hạ **--release** nếu sản phẩm thực sự cần API ngôn ngữ mới. Sửa nguồn gốc cấu hình rồi chạy lại cùng đường đi CI.

## 9. Mức độ tái hiện và ranh giới kết luận

Có ba mức độ thường gặp:

- **Lặp lại pipeline:** cùng wrapper command, commit, environment và các bước tiền biên dịch. Đây là mức phù hợp nhất khi lỗi phụ thuộc graph/task/plugin.
- **Lặp lại compiler inputs:** cùng compiler, sources, flags, classpath/module path, processors và output directory. Đây là mức hữu ích để cô lập lỗi javac, nhưng vẫn có thể khác runtime hosting compiler.
- **Lặp lại byte-for-byte output:** còn cần tính đến tính ổn định của processor, generated timestamps, build metadata, đường dẫn tuyệt đối và artifact phụ trợ. Hai lần biên dịch thành công chưa chắc tạo mọi byte y hệt.

**Tiêu chí kết luận hợp lý:** nêu rõ mức đã đạt được, dữ liệu nào xác minh bằng log/cấu hình, dữ liệu nào chỉ suy đoán và sự khác biệt nào đủ giải thích triệu chứng. Nếu compiler chạy qua API, có thể đạt tái hiện **tương đương hiệu lực** mà không tìm thấy “dòng javac gốc” — điều đó hoàn toàn bình thường.

## 10. Checklist thực hành trước khi đóng lỗi

- [ ] Cùng commit và đúng lệnh CI/task compile thất bại.
- [ ] Compiler JDK/toolchain được xác nhận riêng với JVM chạy Gradle/Maven.
- [ ] Source roots, generated sources và danh sách .java đã được kiểm chứng.
- [ ] Compile classpath, module path, processor path và dependency versions đã resolve.
- [ ] Release/source/target, encoding, output, processor options và argfile được giữ nguyên.
- [ ] Working directory, OS/path separator, biến môi trường liên quan được đối chiếu.
- [ ] Đã xác nhận task thực sự compile, không chỉ lấy cache hoặc bị skip.
- [ ] Đã tái hiện hoặc đã chỉ rõ dữ liệu còn thiếu; diagnostic được so sánh cùng bối cảnh.
- [ ] Không đưa secret/token hay log nhạy cảm vào artifact chia sẻ.
- [ ] Thay đổi sửa lỗi đã được kiểm tra bằng đúng đường đi build/CI.

## Tài liệu tra cứu

- [JDK 21 — tài liệu chính thức của javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): option, argfile, classpath/module path, release và annotation processing.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) và [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): task compilation, JavaCompile và toolchain.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): goal compile, release và khả năng chẩn đoán tùy phiên bản plugin.

**Bài học cốt lõi:** một bản tái hiện đáng tin phải giữ được **compiler thực tế, đầu vào đã resolve và điều kiện thực thi**, đồng thời nói rõ đâu là lệnh được log chứng minh và đâu là lệnh javac được dựng lại để kiểm tra giả thuyết.
