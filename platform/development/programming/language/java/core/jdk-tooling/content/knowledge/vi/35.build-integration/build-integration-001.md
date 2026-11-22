# Gọi javac từ build

## 1. Build integration là gì?

Build integration là cách đưa bước biên dịch Java vào một quy trình build có thể chạy lặp lại. Thay vì gõ lệnh `javac` thủ công mỗi lần, build script hoặc build tool xác định source files, dependency, compiler options, output directory và thứ tự các bước cần thực hiện.

Một quy trình Java build thường gồm:

1. Chọn JDK và phiên bản compiler.
2. Tìm các file nguồn trong source set.
3. Chuẩn bị classpath, module path và annotation processor nếu có.
4. Gọi compiler với các tùy chọn thống nhất.
5. Chép resource vào output directory.
6. Biên dịch test source và chạy test.
7. Đóng gói class thành JAR hoặc artifact khác.

`javac` chịu trách nhiệm biên dịch file nguồn thành bytecode `.class`. Nó không tự quản lý toàn bộ dependency, resource, test, package, version hay task graph. Build tool điều phối những phần việc đó.

Có thể gọi compiler trực tiếp bằng script, hoặc dùng một build tool như Apache Ant, Maven hay Gradle. Với Maven và Gradle, cần phân biệt việc dùng Java Compiler API trong tiến trình build với việc fork một process `javac` riêng. Nếu mục tiêu là gọi executable bên ngoài, hãy bật chế độ fork tương ứng.

## 2. Chọn JDK và xác định compiler

Trước khi tích hợp, kiểm tra các công cụ mà build thực sự sử dụng:

~~~bash
java --version
javac --version
mvn --version
gradle --version
~~~

`java --version` cho biết runtime của command `java`. `javac --version` cho biết compiler được tìm thấy qua PATH. `mvn --version` và `gradle --version` cho biết JDK đang chạy chính build tool.

Ba phiên bản này có thể khác nhau nếu máy có nhiều JDK hoặc build tool dùng toolchain riêng. Ví dụ, Maven có thể chạy bằng JDK 24 nhưng compiler được cấu hình từ một JDK khác.

Cần xác định rõ hai mục tiêu:

- **Compiler JDK:** JDK cung cấp executable `javac` hoặc Java Compiler API được build tool dùng.
- **Target Java release:** phiên bản Java mà source code và bytecode cần tương thích.

Dùng `--release 17` với `javac 24` vẫn có thể tạo class file cho Java 17, miễn là JDK 24 hỗ trợ release đó. `--release` không tự chọn compiler JDK; toolchain hoặc PATH mới quyết định compiler được gọi.

Trong CI, nên pin JDK/toolchain và phiên bản build plugin để các máy build dùng cùng môi trường.

## 3. Cấu trúc source và output directory

Một layout thông dụng:

~~~text
javac-build-demo/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/
│   │   │       ├── Main.java
│   │   │       └── Greeting.java
│   │   └── resources/
│   │       └── message.txt
│   └── test/
│       ├── java/
│       └── resources/
├── build/
└── pom.xml hoặc build.gradle hoặc build.xml
~~~

`src/main/java` chứa source code chính. `src/main/resources` chứa file cấu hình, template, hình ảnh hoặc resource khác cần được chép vào class output. `src/test/java` và `src/test/resources` dành cho test.

Giữ output tách khỏi source:

| Build tool | Class output chính | Artifact thường gặp |
|---|---|---|
| javac script | `build/classes` | Tự đóng gói hoặc tạo JAR. |
| Ant | `build/classes` | Theo target trong `build.xml`. |
| Maven | `target/classes` | `target/*.jar`. |
| Gradle | `build/classes/java/main` | `build/libs/*.jar`. |

Không ghi file `.class` vào thư mục source. Khi clean, build có thể xóa output cũ mà không ảnh hưởng source code.

## 4. Lệnh javac cơ bản trong build

Cú pháp tổng quát:

~~~bash
javac [options] source-files
~~~

Một lệnh thường dùng:

~~~bash
javac --release 17 -encoding UTF-8 -g -d build/classes src/main/java/com/example/Greeting.java src/main/java/com/example/Main.java
~~~

Ý nghĩa:

| Option | Tác dụng |
|---|---|
| `--release 17` | Biên dịch theo ngôn ngữ, API Java SE và class file của Java 17. |
| `-encoding UTF-8` | Đọc source file bằng UTF-8. |
| `-g` | Sinh thông tin debug như line number và local variable. |
| `-d build/classes` | Ghi class file vào output directory. |
| Source paths | Các file `.java` cần biên dịch. |

Nếu source khai báo package `com.example`, compiler tạo thư mục `com/example` bên trong output directory.

Sau khi biên dịch, chạy chương trình bằng:

~~~bash
java -cp build/classes com.example.Main
~~~

Tên class chính là tên đầy đủ gồm package. Không truyền đường dẫn file `Main.class` vào lệnh `java`.

## 5. Các option quan trọng khi gọi javac

### Chọn phiên bản Java

Dùng:

~~~bash
javac --release 17 ...
~~~

`--release` kiểm soát source language, API Java SE có thể sử dụng và target class file. Đây thường là lựa chọn phù hợp nhất khi build cần tương thích với một phiên bản Java cụ thể.

Không ghép `--release` với `-source` hoặc `-target` trong cùng lệnh. Hai option cũ này không cung cấp đầy đủ API targeting như `--release`.

### Encoding và debug information

~~~bash
javac --release 17 -encoding UTF-8 -g ...
~~~

Dùng UTF-8 nhất quán cho source code. `-g` giúp debugger hiển thị dòng và local variable. Nếu muốn kiểm soát riêng:

- `-g:lines`: line number.
- `-g:vars`: local variable.
- `-g:source`: source file information.
- `-g:none`: không sinh debug information.

### Warning và compiler diagnostics

~~~bash
javac --release 17 -Xlint:all ...
~~~

`-Xlint:all` bật các cảnh báo compiler được hỗ trợ. Có thể kết hợp `-Werror` để biến warning thành lỗi build:

~~~bash
javac --release 17 -Xlint:all -Werror ...
~~~

Chỉ bật `-Werror` khi dự án đã xử lý warning ổn định. Một warning mới từ JDK hoặc dependency có thể làm build thất bại dù source vẫn biên dịch được.

### Class output và generated files

- `-d`: nơi ghi class file.
- `-s`: nơi ghi source file do annotation processor tạo.
- `-h`: nơi ghi native header file do `javac` sinh.
- `-parameters`: lưu tên tham số method/constructor để reflection có thể đọc.
- `-proc:none`: tắt annotation processing.
- `-processorpath`: nơi tìm annotation processor.

Tách generated source khỏi source do developer viết để clean và incremental build dễ dự đoán.

## 6. Classpath và dependency

Khi source tham chiếu class từ JAR hoặc output directory khác, compiler cần biết nơi tìm dependency:

~~~bash
javac --release 17 -cp "lib/*" -d build/classes @build/sources.args
~~~

`-cp` và `--class-path` là hai cách viết tương đương. Wildcard `lib/*` đưa các JAR trong thư mục lib vào classpath. Wildcard này không tìm JAR đệ quy trong mọi thư mục con.

Classpath separator phụ thuộc hệ điều hành:

| Hệ điều hành | Ví dụ |
|---|---|
| Windows | `build/classes;lib/a.jar;lib/b.jar` |
| Linux/macOS | `build/classes:lib/a.jar:lib/b.jar` |

Khi chạy ứng dụng, runtime cũng cần dependency:

~~~bash
# Windows
java -cp "build/classes;lib/*" com.example.Main

# Linux/macOS
java -cp "build/classes:lib/*" com.example.Main
~~~

Nếu compiler tìm thấy dependency nhưng lệnh chạy không có dependency đó, chương trình có thể gặp `NoClassDefFoundError` hoặc `ClassNotFoundException`.

Maven và Gradle tự xây classpath từ dependency được khai báo. Đây là một lý do quan trọng để giao việc phân giải dependency cho build tool thay vì tự nối chuỗi classpath trong script.

## 7. Module path khi build dự án JPMS

Dự án dùng Java Platform Module System có thể cần `--module-path` thay cho classpath thông thường.

Ví dụ một module:

~~~bash
javac --release 17 --module-path lib -d build/modules --module-source-path src -m com.example.app
~~~

Trong layout module source, mỗi module có thư mục riêng và file `module-info.java`. `--module-source-path` chỉ ra root chứa source module; `-m` chọn module cần biên dịch.

Các option thường gặp:

- `--module-path`: nơi tìm các module đã biên dịch hoặc module JAR.
- `--module-source-path`: nơi tìm source của nhiều module.
- `--add-modules`: thêm module gốc vào tập module được resolve.
- `--patch-module`: bổ sung hoặc thay thế nội dung của một module.

Không trộn classpath và module path tùy tiện. Xác định dependency là module hay classpath artifact rồi cấu hình nhất quán ở compile và runtime.

## 8. Dùng argument file để gọi javac

Khi dự án có nhiều source file hoặc command line quá dài, dùng argument file:

~~~bash
javac @build/javac.args
~~~

Ví dụ nội dung `build/javac.args`:

~~~text
--release
17
-encoding
UTF-8
-g
-d
"build/classes"
"src/main/java/com/example/Greeting.java"
"src/main/java/com/example/Main.java"
~~~

Mỗi dòng là một argument. Đặt đường dẫn có khoảng trắng trong dấu nháy kép. Có thể đưa option và giá trị lên các dòng riêng như ví dụ.

Argument file hữu ích vì:

- Tránh giới hạn độ dài command line của shell hoặc hệ điều hành.
- Dễ tạo source list từ build script.
- Dễ kiểm tra chính xác compiler đã nhận những file nào.
- Giữ command gọi compiler ngắn và ổn định.

Trên Windows, dấu gạch chéo ngược trong argument file có ý nghĩa escape. Dùng dấu gạch chéo xuôi trong đường dẫn và đặt path có khoảng trắng trong dấu nháy kép để tránh biến mất ký tự phân cách. Gọi file argument có đường dẫn chứa khoảng trắng bằng một argument đã được quote đúng từ shell.

Không ghi UTF-8 BOM vào argument file nếu môi trường compiler không xử lý BOM. Khi tạo file từ PowerShell 5.1, `Set-Content -Encoding utf8` ghi BOM; có thể dùng `System.IO.File.WriteAllLines` với `UTF8Encoding(false)` để ghi UTF-8 không BOM.

## 9. Gọi javac bằng PowerShell build script

Một script có thể tự tìm source, tạo argument file, gọi compiler, kiểm tra exit code và chép resource.

Ví dụ `build.ps1` ở thư mục project:

~~~powershell
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$sourceRoot = Join-Path $root 'src/main/java'
$resourceRoot = Join-Path $root 'src/main/resources'
$classesDir = Join-Path $root 'build/classes'
$argFile = Join-Path $root 'build/javac.args'

New-Item -ItemType Directory -Force -Path $classesDir | Out-Null

$sourceArgs = Get-ChildItem $sourceRoot -Recurse -Filter '*.java' |
    ForEach-Object {
        '"' + $_.FullName.Replace('\', '/') + '"'
    }

$compilerArgs = @(
    '--release', '17',
    '-encoding', 'UTF-8',
    '-g',
    '-d', ('"' + $classesDir.Replace('\', '/') + '"')
) + $sourceArgs

[System.IO.File]::WriteAllLines(
    $argFile,
    [string[]]$compilerArgs,
    [System.Text.UTF8Encoding]::new($false)
)

& javac "@$argFile"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (Test-Path $resourceRoot) {
    Get-ChildItem $resourceRoot -Force |
        Copy-Item -Destination $classesDir -Recurse -Force
}

& java -cp $classesDir com.example.Main
exit $LASTEXITCODE
~~~

Chạy:

~~~powershell
.\build.ps1
~~~

Script dùng đường dẫn tuyệt đối để không phụ thuộc terminal được mở từ thư mục nào. Argument file giúp xử lý source path có khoảng trắng. Build dừng ngay nếu compiler trả về exit code khác 0; không chạy ứng dụng với class output cũ sau khi compile thất bại.

Trong PowerShell 7 có thể dùng encoding `utf8NoBOM` cho các file text. Với PowerShell 5.1, cần chú ý khác biệt encoding của `Set-Content` và `Out-File`.

## 10. Gọi javac từ Apache Ant

Ant có task `javac` để biên dịch source directory:

~~~xml
<project name="javac-build-demo" default="compile">
    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac
            srcdir="src/main/java"
            destdir="build/classes"
            release="17"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false"
            fork="true"/>
        <copy todir="build/classes">
            <fileset dir="src/main/resources"/>
        </copy>
    </target>
</project>
~~~

Chạy:

~~~bash
ant clean compile
~~~

Các thuộc tính chính:

- `srcdir`: root chứa source file.
- `destdir`: nơi ghi class file.
- `release`: Java release cần biên dịch.
- `encoding`: encoding source.
- `debug`: sinh debug information.
- `includeantruntime="false"`: không tự đưa Ant runtime vào classpath compile.
- `fork="true"`: gọi compiler trong process riêng.

Nếu `fork` là false, Ant có thể dùng compiler API trong JVM chạy Ant. Khi cần gọi executable `javac` bên ngoài, đặt `fork="true"`. Ant có thể dùng compiler từ PATH; nếu cần chỉ định JDK riêng, cấu hình executable phù hợp với hệ điều hành.

Ant hỗ trợ incremental compile dựa trên trạng thái source/class và các thuộc tính task. Target clean giúp loại bỏ class cũ trước một build sạch.

## 11. Gọi javac từ Maven

Maven dùng standard layout và Maven Compiler Plugin để biên dịch source ở `src/main/java`. Ví dụ cấu hình `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>javac-build-demo</artifactId>
    <version>1.0.0</version>

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
                    <encoding>UTF-8</encoding>
                    <fork>true</fork>
                    <showWarnings>true</showWarnings>
                    <compilerArgs>
                        <arg>-Xlint:all</arg>
                    </compilerArgs>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy:

~~~bash
mvn clean verify
~~~

Maven tự thực hiện các phase cần thiết, gồm resource processing, compile, test compile, test và package theo lifecycle. Class output mặc định là `target/classes`; JAR được tạo trong `target`.

Maven Compiler Plugin mặc định có thể dùng Java Compiler API trong process Maven. `fork=true` yêu cầu plugin khởi chạy compiler process riêng. Khi bật fork, có thể chỉ định executable bằng cấu hình plugin nếu muốn dùng một compiler cụ thể; cần đảm bảo đường dẫn phù hợp Windows/Linux/macOS hoặc dùng Maven Toolchains để chọn JDK.

Trong lab JDK 24.0.2, Maven 3.9.12 và Compiler Plugin 3.13.0 đã in:

~~~text
Compiling 2 source files with javac [forked debug release 17] to target\classes
BUILD SUCCESS
~~~

Lệnh build tiếp theo báo `Nothing to compile - all classes are up to date` khi source không thay đổi. Đây là hành vi incremental của compiler plugin trong lần chạy đó.

Các dependency khai báo trong `dependencies` được Maven resolve và đưa vào compiler classpath. Không cần tự nối đường dẫn JAR bằng tay.

## 12. Gọi javac từ Gradle

Gradle Java Plugin cung cấp task `compileJava` và `JavaCompile`. Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.debug = true
    options.fork = true
    options.compilerArgs.addAll(['-Xlint:all'])
}
~~~

Chạy:

~~~bash
gradle clean build
~~~

Hoặc dùng Gradle Wrapper đã commit cùng dự án:

~~~bash
./gradlew clean build
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean build
~~~

`java.toolchain` chọn JDK cung cấp compiler. Máy build cần có JDK phù hợp hoặc được cấu hình toolchain resolver để provision JDK. `options.release` quyết định API và bytecode target. Có thể dùng compiler JDK mới hơn với release cũ hơn nếu JDK đó hỗ trợ release cần thiết.

`options.fork=true` yêu cầu Gradle chạy compiler trong process riêng. Nếu bỏ fork, Gradle có thể dùng compiler API thông qua worker process. Không cần tự tạo command line cho mọi source file; Gradle quản lý source set, dependency classpath, resource và output.

Output mặc định:

- Class chính: `build/classes/java/main`.
- Resource chính: `build/resources/main`.
- Test class: `build/classes/java/test`.
- JAR: `build/libs`.

Trong lab, Gradle 9.2.1 dùng JDK 24.0.2 làm toolchain và `options.release=17`. Task `compileJava` và `jar` chạy thành công; lần build tiếp theo báo `UP-TO-DATE` khi input không thay đổi.

## 13. So sánh cách gọi compiler trong các build tool

| Build tool | Cách cấu hình | Cách gọi compiler |
|---|---|---|
| Script | Gọi `javac` và kiểm tra exit code. | External process trực tiếp. |
| Ant | `<javac fork="true"/>`. | External process khi fork bật. |
| Maven | `maven-compiler-plugin` với `fork=true`. | External process khi fork bật; mặc định có thể dùng compiler API. |
| Gradle | `JavaCompile.options.fork=true`. | External compiler process khi fork bật; mặc định có thể dùng compiler API. |

Chọn cách phù hợp với dự án:

- Dùng script khi project nhỏ, ít dependency và cần một lệnh build đơn giản.
- Dùng Ant khi cần target tùy chỉnh và build XML rõ ràng.
- Dùng Maven khi cần lifecycle, dependency management và quy ước project chuẩn.
- Dùng Gradle khi cần build graph linh hoạt, task tùy chỉnh và toolchain integration.

Không nên tự tạo một lớp gọi `javac` riêng nếu Maven hoặc Gradle đã quản lý compile task đầy đủ. Có thể bổ sung task hoặc compiler option vào build tool hiện tại mà vẫn giữ dependency graph và incremental behavior.

## 14. Annotation processing và generated source

Annotation processor chạy trong quá trình compile để đọc annotation và tạo source/class bổ sung. Ví dụ các processor sinh metamodel, mapper, serializer hoặc boilerplate code.

Khi gọi `javac` trực tiếp, cấu hình processor path và output directory:

~~~bash
javac --release 17 \
  -processorpath tools/processor.jar \
  -processor com.example.GenerateProcessor \
  -s build/generated-sources \
  -d build/classes \
  @build/sources.args
~~~

Các option:

- `-processorpath`: classpath của annotation processor.
- `-processor`: tên processor cần chạy.
- `-s`: nơi ghi source được sinh ra.
- `-Akey=value`: truyền option cho processor.

Từ JDK 23, annotation processing không còn tự động chạy chỉ vì processor tình cờ có trên classpath. Hãy khai báo processor rõ ràng qua `-processor`, `-processor-path`, `--processor-module-path` hoặc chọn chế độ `-proc:full` khi thực sự cần xử lý annotation.

Trong Maven, khai báo processor qua `annotationProcessorPaths` của Maven Compiler Plugin. Trong Gradle, dùng configuration `annotationProcessor` riêng cho processor. Tách processor khỏi dependency runtime để classpath ứng dụng không chứa công cụ build không cần thiết.

## 15. Compile test và copy resource

`javac` chỉ biên dịch source Java. Nó không tự chép file trong `src/main/resources` vào output directory.

Với script hoặc Ant, thêm bước copy resource sau compile. Với Maven, resource plugin thực hiện việc này trong lifecycle. Với Gradle, task `processResources` xử lý source set resources.

Test source cần compiler classpath riêng, bao gồm class chính và test dependencies. Maven dùng `maven-compiler-plugin` cho `testCompile`; Gradle dùng task `compileTestJava`.

Không gộp test class vào output production nếu không có chủ đích. Giữ riêng:

- Main source và main resources.
- Test source và test resources.
- Generated source.
- Main class output và test class output.

Sự tách biệt này giúp đóng gói artifact production mà không đưa test framework hoặc test fixture vào runtime.

## 16. Incremental build và clean

Incremental build chỉ chạy lại những task bị ảnh hưởng bởi input thay đổi. Maven compiler plugin có thể phát hiện source đã thay đổi; Gradle dùng task input/output tracking để đánh dấu task `UP-TO-DATE`; Ant javac có cơ chế kiểm tra timestamp.

Một số nguyên tắc:

- Giữ source input và output directory tách biệt.
- Không sửa trực tiếp file trong `target/classes` hoặc `build/classes`.
- Khai báo dependency và compiler option trong build file để task có thể theo dõi.
- Để generated source ở thư mục riêng.
- Dùng clean khi cần xác nhận build từ trạng thái rỗng.

Lệnh clean thường dùng:

~~~bash
# Maven
mvn clean verify

# Gradle
gradle clean build

# Ant
ant clean compile
~~~

Nếu một class cũ vẫn tồn tại sau khi source đã bị xóa hoặc đổi package, build output có thể chứa artifact lỗi thời. Clean build giúp phát hiện tình huống này.

Không chạy clean trước mọi lần compile nếu không cần. Build incremental nhanh hơn và giúp xác định chính xác task nào cần thực hiện lại.

## 17. Kiểm tra output và Java release

Sau compile, xác nhận class file đã được tạo đúng nơi. Chạy ứng dụng từ class output:

~~~bash
java -cp build/classes com.example.Main
~~~

Có thể dùng `javap` để xem class file:

~~~bash
javap -verbose -classpath build/classes com.example.Main
~~~

Tìm dòng `major version`. Một số giá trị thường gặp:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

`javap` giúp xác nhận target bytecode thực tế. Tuy nhiên, class file version phù hợp không chứng minh mọi dependency đều tương thích với runtime target; vẫn cần test trên JDK mục tiêu.

Trong lab, cả bốn cách compile — javac argument file, Ant, Maven và Gradle — đều tạo class file major version 61 khi dùng `--release 17` hoặc cấu hình tương đương.

## 18. Lỗi thường gặp khi gọi javac từ build

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac is not recognized` | JDK bin chưa nằm trong PATH hoặc JAVA_HOME sai. | Kiểm tra `javac --version` và toolchain. |
| `invalid source release` | Compiler quá cũ so với release yêu cầu. | Chọn JDK mới hơn có hỗ trợ release đó. |
| `file not found` | Source list hoặc working directory không đúng. | Kiểm tra root và đường dẫn trong argument file. |
| `illegal character: '\\ufeff'` ở dòng đầu | Source UTF-8 có BOM mà compiler không bỏ qua. | Lưu source UTF-8 không BOM. |
| Path có dấu cách bị tách thành nhiều argument | Thiếu quote trong command hoặc argument file. | Quote toàn bộ path; dùng argfile. |
| Windows path bị mất dấu gạch chéo ngược trong argfile | Backslash bị hiểu là escape. | Dùng dấu gạch chéo xuôi và quote path. |
| `package does not exist` | Dependency thiếu trên compile classpath hoặc module path. | Khai báo dependency trong build tool hoặc `-cp`/`--module-path`. |
| `cannot find symbol` | Thiếu source, dependency hoặc generated source. | Kiểm tra source set, compile order và annotation processor. |
| `NoClassDefFoundError` khi chạy | Runtime classpath thiếu dependency. | Bổ sung dependency vào runtime classpath hoặc dùng artifact packaging phù hợp. |
| `class file has wrong version` | Bytecode được tạo bởi release mới hơn runtime. | Hạ target bằng `--release` và kiểm tra dependency. |
| Annotation processor không chạy | Processor chưa được khai báo rõ hoặc sai processor path. | Cấu hình processor path/processor trong build tool. |
| Compile pass nhưng resource không có | Chỉ gọi javac, chưa có bước resource processing. | Thêm copy resource hoặc dùng task resource của build tool. |
| Build dùng sai JDK | Build tool và shell dùng JDK khác nhau. | Kiểm tra `mvn --version`, `gradle --version` và toolchain. |
| Build không biên dịch lại source | Task input/output hoặc timestamp không được cập nhật đúng. | Kiểm tra source set, generated files và chạy clean build để đối chiếu. |
| Class cũ vẫn chạy sau khi đổi source | Output directory còn class cũ. | Clean output và build lại. |

## 19. Lab hoàn chỉnh: cùng một ứng dụng, nhiều cách build

Tạo hai file source.

`src/main/java/com/example/Greeting.java`:

~~~java
package com.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name;
    }
}
~~~

`src/main/java/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Build integration ready");
        System.out.println(Greeting.message("javac"));
    }
}
~~~

Biên dịch bằng javac:

~~~bash
javac --release 17 -encoding UTF-8 -g -d build/classes \
  src/main/java/com/example/Greeting.java \
  src/main/java/com/example/Main.java
~~~

Chạy:

~~~bash
java -cp build/classes com.example.Main
~~~

Stdout chính xác:

~~~text
Build integration ready
Xin chào, javac
~~~

Có thể dùng cùng hai source file này trong Ant, Maven hoặc Gradle. Khác biệt nằm ở cách build tool tìm source, tạo classpath, gọi compiler, xử lý resource và đóng gói output.

Kết quả đã kiểm chứng trên Windows 11 với:

| Thành phần | Phiên bản |
|---|---|
| JDK/compiler | 24.0.2 |
| Maven | 3.9.12 |
| Maven Compiler Plugin | 3.13.0 |
| Gradle | 9.2.1 |
| Ant runtime | 1.10.15 |

Project thử nghiệm nằm trong thư mục có dấu cách để kiểm tra quoting. Direct javac argument file, Ant `<javac fork="true"/>`, Maven `fork=true` và Gradle `options.fork=true` đều compile thành công. Cả bốn output chạy với stdout như trên và tạo class file major version 61. Maven và Gradle build lần hai nhận diện compile task không cần chạy lại khi source không đổi.

## 20. Quy trình build ổn định trong CI

Một build CI có thể theo trình tự:

1. Chọn JDK bằng toolchain hoặc image build đã pin.
2. In phiên bản Java, javac và build tool để lưu vào build log.
3. Resolve dependency theo lock/version đã khai báo.
4. Chạy clean build khi cần xác minh trạng thái từ đầu.
5. Biên dịch main và test source.
6. Chạy test.
7. Chép resource và đóng gói JAR.
8. Kiểm tra artifact và lưu build output.

Ví dụ:

~~~bash
# Maven
mvn -B clean verify

# Gradle Wrapper
./gradlew --no-daemon clean build
~~~

Các nguyên tắc giúp build lặp lại:

- Pin phiên bản Maven/Gradle plugin.
- Dùng Maven Wrapper hoặc Gradle Wrapper để thống nhất build tool.
- Chọn JDK bằng toolchain thay vì dựa vào JDK tình cờ có trên PATH.
- Ghi rõ `--release` và encoding.
- Khai báo dependency và annotation processor trong build file.
- Không commit class output hoặc file tạm do compiler sinh ra.
- Không bỏ qua exit code của compiler.
- Chỉ bật `-Werror` khi warning policy của dự án đã ổn định.
- Giữ build log đủ thông tin để xác định compiler và option được dùng.

## 21. Tài liệu tham khảo

- [The javac Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Java Compiler API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle Java Plugin and JavaCompile](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Apache Ant javac Task](https://ant.apache.org/manual/Tasks/javac.html)

Build integration giúp compiler chạy nhất quán cùng dependency, resource, test và packaging. Với script, hãy quản lý source list, argument file và exit code. Với Ant, Maven hoặc Gradle, khai báo release, encoding, toolchain và chế độ fork trong build file. Kiểm tra class output và chạy test trên JDK mục tiêu để xác nhận artifact thực sự tương thích.
