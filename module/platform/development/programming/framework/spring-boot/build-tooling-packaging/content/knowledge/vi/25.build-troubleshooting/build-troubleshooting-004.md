# Xử lý UnsupportedClassVersionError và sai JDK giữa build với runtime

## 1. Mục tiêu chẩn đoán

`UnsupportedClassVersionError` xuất hiện khi JVM cố đọc một file `.class` nhưng không hỗ trợ cặp `major_version`/`minor_version` của class file đó. Tình huống thường gặp là ứng dụng hoặc một dependency được compile bằng Java mới hơn, sau đó chạy trên Java cũ hơn.

Ví dụ:

~~~text
class file version 65.0
this runtime only recognizes class file versions up to 61.0
~~~

Class major 65 tương ứng Java 21; major 61 tương ứng Java 17. JVM Java 17 không nạp được class file Java 21. Muốn xử lý đúng, cần xác định **class nào** không tương thích và **JVM nào** đang nạp nó, rồi đồng bộ runtime hoặc compile về một release được hỗ trợ.

Bài thuộc mục **Chẩn đoán sự cố** trong chủ đề **Spring Boot Build Tooling Packaging**. Sau bài này, bạn có thể:

1. Đọc major/minor class-file version và ánh xạ về Java release.
2. Phân biệt JDK chạy Maven/Gradle, compiler toolchain, bytecode target, JVM chạy test và JRE production.
3. Tái hiện lỗi Java 21 bytecode chạy trên Java 17 và sửa bằng `--release`.
4. Cấu hình Maven Compiler Plugin, Maven Toolchains và Gradle Java Toolchains.
5. Tìm class gây lỗi trong source project, transitive dependency, plugin build hoặc nested JAR.
6. Phân biệt `UnsupportedClassVersionError` với `NoSuchMethodError`, `NoClassDefFoundError` và lỗi API không tương thích.
7. Đồng bộ Java version giữa local IDE, CI runner, test runner và Docker/Kubernetes runtime.
8. Dùng một chương trình Java 17 để đọc header của class file.
9. Tạo CI gate để ngăn artifact có bytecode mới hơn runtime được hỗ trợ.

**Bộ ví dụ:** Java `17`, Spring Boot `3.5.16`, Maven và Gradle. Spring Boot 3.5.16 yêu cầu tối thiểu Java 17; các dependency hoặc plugin khác có thể đặt ra yêu cầu cao hơn. Java 17 là baseline của ví dụ, không phải cam kết rằng mọi thư viện trong mọi ứng dụng đều tương thích Java 17.

## 2. Class-file version: con số 61 và 65 có nghĩa gì?

Java compiler không ghi trực tiếp chuỗi "Java 17" vào class file. Nó ghi một cấu trúc nhị phân có hai trường:

- `minor_version`: phiên bản phụ của định dạng class file.
- `major_version`: phiên bản chính của định dạng class file.

Phần đầu class file có magic bytes `CA FE BA BE`, sau đó là minor và major version. JVM dùng cặp version này để xác định có thể đọc định dạng class hay không.

Một số major version thường gặp:

| Java release | Class-file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 24 | 68 |
| Java 25 | 69 |

Quy luật thông dụng là `major = Java release + 44`. Ví dụ Java 17 tương ứng 61, Java 21 tương ứng 65. Bảng đầy đủ được định nghĩa trong Java Virtual Machine Specification, phần `Class File Format`.

**Đừng nhầm major version với phiên bản Maven, Spring Boot hoặc dependency.** Đây là version của định dạng bytecode mà JVM phải đọc.

### 2.1. Tái hiện Java 21 bytecode trên Java 17

Tạo source `src/demo/VersionMismatchDemo.java`:

~~~java
package demo;

public class VersionMismatchDemo {
    public static void main(String[] args) {
        System.out.println("compiled-for-java-21");
    }
}
~~~

Compile bằng JDK 21, không hạ target:

~~~bash
javac --release 21 -d target/java21 src/demo/VersionMismatchDemo.java
~~~

Class được tạo có major version 65. Chạy bằng Java 17:

~~~bash
/path/to/jdk17/bin/java -cp target/java21 demo.VersionMismatchDemo
~~~

JVM Java 17 từ chối class file version 65. Thông điệp đại diện:

~~~text
Exception in thread "main" java.lang.UnsupportedClassVersionError:
demo/VersionMismatchDemo has been compiled by a more recent version
of the Java Runtime (class file version 65.0), this version of the
Java Runtime only recognizes class file versions up to 61.0
~~~

Thông điệp thực tế thường nằm trên một dòng dài và stack trace phụ thuộc lệnh chạy. Hãy tập trung vào cặp **65.0 so với 61.0**.

### 2.2. Sửa bằng cách compile đúng release

Nếu ứng dụng phải chạy trên Java 17, compile lại:

~~~bash
javac --release 17 -d target/java17 src/demo/VersionMismatchDemo.java
~~~

Chạy bằng Java 17:

~~~bash
/path/to/jdk17/bin/java -cp target/java17 demo.VersionMismatchDemo
~~~

Stdout chính xác:

~~~text
compiled-for-java-21
~~~

Chuỗi output giữ nguyên, nhưng class file giờ tương thích Java 17. JDK 21 hoàn toàn có thể tạo bytecode Java 17 bằng `--release 17`; không bắt buộc mọi developer phải cài đúng JDK 17 nếu build được cấu hình đúng và dependencies đáp ứng baseline.

## 3. Phân biệt các Java version trong pipeline

Một pipeline có thể đồng thời dùng nhiều JVM/JDK:

| Thành phần | Vai trò | Cách kiểm tra |
| --- | --- | --- |
| JVM chạy Maven/Gradle | Chạy build tool và plugin | `mvn -version`, `./gradlew --version` |
| JDK compiler/toolchain | Chạy `javac` hoặc compiler tương ứng | Toolchain config và build logs |
| Java release/bytecode target | Quy định class file và API platform | `maven.compiler.release`, `options.release` |
| JVM runtime | Nạp class và chạy ứng dụng/test/container | `java -version`, Docker image |

Ví dụ hợp lệ:

~~~text
Maven JVM        : Java 21
Compiler JDK     : Java 21
Compiler release : 17
Test JVM         : Java 17
Production JRE   : Java 17
Output bytecode  : major 61
~~~

Ví dụ có rủi ro:

~~~text
Maven JVM        : Java 21
Compiler JDK     : Java 21
Compiler release : không cấu hình, mặc định 21
Test JVM         : Java 21
Production JRE   : Java 17
Output bytecode  : major 65
~~~

Ở ví dụ thứ hai, build và test CI đều xanh vì CI dùng Java 21, nhưng production Java 17 không nạp được class major 65.

### 3.1. JDK và JRE

- `JDK` chứa compiler `javac`, debugger và các công cụ phát triển, ngoài JVM/runtime libraries.
- `JRE` cung cấp môi trường thực thi JVM và runtime libraries; image JRE thường không có `javac`.
- `java -version` kiểm tra executable `java` mà shell đang gọi.
- `javac -version` kiểm tra compiler executable mà shell đang gọi.

Một máy có thể có nhiều JDK và nhiều `java.exe` trên `PATH`. Terminal, Maven, IDE và Docker không nhất thiết chọn cùng một bản. Đừng suy ra runtime version từ compiler version.

### 3.2. Baseline của Spring Boot

Spring Boot 3.5.16 yêu cầu ít nhất Java 17. Bản này hỗ trợ Java tới mức được liệt kê trong system requirements; các thư viện bên thứ ba có thể yêu cầu Java cao hơn. Maven và Gradle cũng có compatibility matrix riêng.

Ngay cả khi application bytecode là major 61, một dependency có thể yêu cầu Java 21, hoặc một plugin build có thể cần JVM mới hơn để chạy. Vì vậy phải kiểm tra **framework, dependencies, build plugins và runtime**, không chỉ class của main application.

## 4. Xác định JVM thực tế đang chạy

Trước khi sửa POM hoặc đổi Docker image, thu thập version từ từng môi trường.

### 4.1. Terminal

Linux/macOS:

~~~bash
which -a java
which -a javac
java -version
javac -version
echo "$JAVA_HOME"
~~~

Windows PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
java -version
javac -version
$env:JAVA_HOME
~~~

`which -a` hoặc `Get-Command -All` cho biết có nhiều executable trên PATH hay không. `JAVA_HOME` là gợi ý cho build tools; nó không chứng minh mọi tiến trình đang dùng đúng JDK đó.

### 4.2. JVM chạy Maven

~~~bash
mvn -version
./mvnw -version
~~~

Output có Maven version, Java version, Java home và OS. `mvn -version` là thông tin JVM chạy Maven, **không nhất thiết là compiler toolchain** nếu project dùng Maven Toolchains.

Nếu `java -version` báo Java 17 nhưng `mvn -version` báo Java 11, kiểm tra `JAVA_HOME`, Maven launcher, shell/IDE environment và Maven Wrapper process.

### 4.3. JVM chạy Gradle

~~~bash
./gradlew --version
./gradlew javaToolchains
~~~

`./gradlew --version` cho biết Gradle version và JVM/daemon environment. `javaToolchains` liệt kê các JDK Gradle phát hiện và có thể dùng cho tasks.

Gradle daemon JVM và compiler toolchain có thể khác nhau. Một Gradle build chạy trên JVM 21 vẫn có thể compile bằng JDK 17 toolchain; ngược lại, JVM chạy Gradle phải tương thích với Gradle version đang dùng.

### 4.4. JVM trong container

~~~bash
docker run --rm --entrypoint java your-image:tag -version
~~~

Lệnh này gọi `java` trong **image**, không phải Java trên host. Nếu Kubernetes dùng image khác với image local, inspect image digest và runtime của chính pod đang lỗi.

## 5. Xác định class nào có major version không tương thích

Lỗi thường nêu tên class. Đọc class đầu tiên xuất hiện trong `UnsupportedClassVersionError` và xác định nó thuộc:

1. Application class do dự án compile.
2. Spring Boot loader/framework class.
3. Dependency trực tiếp hoặc transitive.
4. Plugin/build tool chạy bên trong Maven/Gradle.
5. Code được sinh bởi annotation processor, Kotlin/Scala/Groovy compiler hoặc bytecode enhancement.
6. Class nằm trong nested JAR của Spring Boot executable archive.

Không mặc định class đầu tiên luôn thuộc `src/main/java`. Nếu Maven fail ngay khi load plugin hoặc Gradle fail trước task compile, lỗi có thể thuộc **build tool process**, không phải artifact ứng dụng.

### 5.1. Dùng javap đọc major version

Với class trong Maven output:

~~~bash
javap -verbose target/classes/demo/VersionMismatchDemo.class
~~~

Tìm dòng:

~~~text
major version: 61
~~~

PowerShell:

~~~powershell
javap -verbose .\target\classes\demo\VersionMismatchDemo.class |
    Select-String "major version"
~~~

Với class trong dependency JAR thông thường:

~~~bash
javap -verbose -classpath path/to/library.jar com.vendor.LibraryType
~~~

Kết quả `major version` cho biết bytecode của class được `javap` phân tích. Nếu dependency có nhiều class, kiểm tra đúng class xuất hiện trong stack trace.

### 5.2. Kiểm tra Spring Boot executable JAR

~~~bash
jar tf target/application.jar
~~~

Spring Boot executable JAR thông thường có:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/...
BOOT-INF/lib/spring-*.jar
BOOT-INF/lib/third-party-library.jar
org/springframework/boot/loader/...
~~~

Application classes nằm dưới `BOOT-INF/classes`; dependencies nằm trong các JAR lồng dưới `BOOT-INF/lib`. `javap -classpath target/application.jar ...` không tự động biến nested JAR thành classpath thông thường.

Để kiểm tra class trong nested dependency, trích JAR con ra thư mục tạm:

~~~bash
mkdir -p target/inspect
cd target/inspect
jar xf ../application.jar BOOT-INF/lib/third-party-library.jar
javap -verbose -classpath BOOT-INF/lib/third-party-library.jar com.vendor.LibraryType
~~~

Thay `third-party-library.jar` bằng entry thật tìm thấy từ `jar tf`. Trên Windows, có thể dùng `jar xf` trong thư mục kiểm tra riêng rồi gọi `javap` tương tự.

### 5.3. Tìm nguồn transitive dependency

Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dverbose
~~~

Tìm dependency có group/artifact/version tương ứng với JAR lỗi. Dependency có thể được kéo vào gián tiếp qua một starter hoặc thư viện khác. Kiểm tra version mediation, exclusions và effective POM trước khi nâng/hạ version.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency library-name --configuration runtimeClasspath
~~~

`dependencyInsight` cho biết dependency được yêu cầu từ đâu, version nào được chọn và vì sao resolver chọn nó. Nếu lỗi xảy ra trong test, kiểm tra thêm `testRuntimeClasspath`; nếu xảy ra khi compile, kiểm tra compile classpath.

## 6. Java 17 utility đọc trực tiếp class-file header

Khi muốn biết chính xác một `.class` có version nào mà không phụ thuộc `javap`, đọc 8 bytes đầu bằng Java Standard Library.

Tạo `ClassVersionProbe.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassVersionProbe {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClassVersionProbe.java <class-file>");
        }

        Path path = Path.of(args[0]);
        byte[] bytes = Files.readAllBytes(path);

        if (bytes.length < 8
                || (bytes[0] & 0xff) != 0xca
                || (bytes[1] & 0xff) != 0xfe
                || (bytes[2] & 0xff) != 0xba
                || (bytes[3] & 0xff) != 0xbe) {
            throw new IllegalArgumentException(
                    "Not a valid Java class file: " + path);
        }

        int minor = ((bytes[4] & 0xff) << 8)
                | (bytes[5] & 0xff);
        int major = ((bytes[6] & 0xff) << 8)
                | (bytes[7] & 0xff);

        String release = major >= 45
                ? Integer.toString(major - 44)
                : "unknown";

        System.out.println("class.major=" + major);
        System.out.println("class.minor=" + minor);
        System.out.println("class.java-release=" + release);
    }
}
~~~

Chương trình kiểm tra magic number `CAFEBABE`, đọc hai trường 16-bit big-endian và hiển thị release tương ứng theo mapping major-version thông dụng. Nó chỉ cần Java 17 Standard Library, không import Maven/Spring.

Chạy với class Java 17 đã compile:

~~~bash
java ClassVersionProbe.java target/classes/demo/CompatibilityDemoApplication.class
~~~

Nếu class được compile với release 17, stdout chính xác:

~~~text
class.major=61
class.minor=0
class.java-release=17
~~~

Nếu class được compile với Java 21 mà không hạ target:

~~~text
class.major=65
class.minor=0
class.java-release=21
~~~

**Giới hạn:** utility đọc một file `.class` cụ thể. Nó không tự quét nested JARs, không phân tích `META-INF/versions/` của multi-release JAR và không chứng minh toàn bộ dependency graph tương thích. Dùng nó để xác nhận class đã xác định, rồi kiểm tra dependencies theo stack trace.

## 7. Maven: cấu hình release target rõ ràng

### 7.1. POM Spring Boot Java 17 đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>java-compatibility-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`java.version` là property convention mà Spring Boot parent dùng để cấu hình Java build. `maven.compiler.release` khai báo rõ target/API platform cho Maven Compiler Plugin. Nếu dùng parent khác, kiểm tra plugin thực sự đọc property nào.

### 7.2. --release khác source/target

Maven Compiler Plugin có thể nhận:

- `source`: phiên bản cú pháp Java được chấp nhận.
- `target`: class-file target version.
- `release`: kiểm soát cả cú pháp/bytecode và public JDK API của release mục tiêu.

JDK 21 compile với `-source 17 -target 17` có thể tạo major version 61 nhưng vẫn nhìn thấy một số API chỉ có trong JDK 21. Class file có thể được nạp nhưng lỗi ở runtime Java 17 bằng `NoSuchMethodError` hoặc `NoClassDefFoundError`.

`--release 17` giới hạn cả bytecode target 17 và API platform theo Java 17. Vì vậy khi compile bằng JDK mới hơn để hỗ trợ runtime cũ, ưu tiên `maven.compiler.release`.

### 7.3. Build và xác nhận

~~~bash
mvn -version
mvn -B -ntp clean verify
javap -verbose target/classes/demo/CompatibilityDemoApplication.class
~~~

Tìm `major version: 61` trong output `javap`. Sau đó chạy executable JAR bằng runtime baseline:

~~~bash
java -version
java -jar target/java-compatibility-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --spring.main.web-application-type=none
~~~

Nếu application có `CommandLineRunner` như mục 10, output do code chủ động in là `java-compatibility-demo:ready`. Spring startup logs có thể khác theo môi trường.

### 7.4. Maven Toolchains: compiler JDK độc lập với Maven JVM

`maven.compiler.release=17` quy định target/API, nhưng không buộc Maven process chạy trên JDK 17. Nếu cần compiler thực sự là JDK 17, dùng Maven Toolchains.

File `~/.m2/toolchains.xml` trên máy build:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

`jdkHome` là đường dẫn cài JDK thực tế; `/opt/jdks/temurin-17` chỉ là ví dụ Linux. Thay bằng path phù hợp Windows/macOS/CI. Không commit path cá nhân vào project.

Trong POM, thêm plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>17</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Toolchains plugin chọn JDK đáp ứng requirement từ `toolchains.xml` và cung cấp toolchain cho Maven plugins có hỗ trợ, như Maven Compiler Plugin. Maven process vẫn có thể chạy trên một JVM khác nếu phiên bản Maven/plugin cho phép.

Kiểm tra:

~~~bash
mvn -version
mvn -B -ntp validate
mvn -B -ntp clean verify
~~~

`mvn -version` hiển thị JVM chạy Maven; build logs/toolchain selection cho biết compiler toolchain được chọn. **Hai thông tin này có thể khác nhau mà vẫn đúng thiết kế.**

### 7.5. Enforcer kiểm tra JVM chạy Maven

Nếu dự án yêu cầu Maven process chạy tối thiểu Java 17, Maven Enforcer có thể kiểm tra JVM của Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>enforce-build-jdk</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Rule `requireJavaVersion` kiểm tra JVM đang chạy Maven, không thay thế kiểm tra compiler target và runtime production. Nếu Maven chạy Java 21 nhưng compiler dùng toolchain 17, rule vẫn phù hợp vì Maven JVM đáp ứng tối thiểu 17.

## 8. Gradle: toolchain và options.release

### 8.1. Groovy DSL

Trong `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

`toolchain` chọn compiler JDK 17 cho các tasks Java hỗ trợ toolchain. `options.release=17` yêu cầu compiler giới hạn Java 17 APIs và tạo bytecode target 17.

### 8.2. Kotlin DSL

Trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

Đây là fragment Gradle DSL; dự án thực tế còn cần repositories, wrapper version, test dependencies và cấu hình khác. Dùng cú pháp đúng với DSL hiện tại, không trộn hai kiểu.

### 8.3. Gradle daemon JVM khác compiler toolchain

`./gradlew --version` cho biết JVM chạy Gradle. `javaToolchains` liệt kê JDK Gradle phát hiện. Toolchain project chọn compiler/test launcher phù hợp; daemon JVM phải tương thích với Gradle version đang dùng.

Một Gradle release có thể yêu cầu Java tối thiểu để chạy chính Gradle. Việc project target Java 17 không tự cho phép chạy một Gradle version quá cũ trên Java 21, hoặc chạy Gradle mới trên JVM không được hỗ trợ. Đối chiếu Gradle compatibility matrix và Spring Boot Gradle plugin compatibility.

### 8.4. Kiểm tra output Gradle

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew clean build
javap -verbose build/classes/java/main/demo/CompatibilityDemoApplication.class
~~~

Kỳ vọng class major 61 nếu task compile dùng release 17. Nếu output vẫn major 65, xem task `compileJava` có bị override `options.release` hay task/module khác tạo classes hay không.

Nếu project có task custom `JavaExec`, integration test launcher hoặc task chạy tool khác, kiểm tra JVM mà task đó thực sự sử dụng. Compile major 61 nhưng integration test chạy Java 21 không chứng minh ứng dụng hoạt động trên Java 17.

## 9. Vì sao compile target đúng vẫn có thể lỗi?

### 9.1. Dependency được compile bằng Java mới hơn

Application classes có thể major 61, trong khi một thư viện transitive có major 65. Khi JVM nạp class thư viện đó, lỗi vẫn xảy ra.

~~~bash
mvn dependency:tree -Dscope=runtime
jar tf target/application.jar
~~~

Tìm dependency được nêu trong error stack, lấy đúng version JAR và inspect class bằng `javap -verbose`. Nâng runtime lên version phù hợp hoặc chọn dependency version còn hỗ trợ runtime hiện tại. Không hạ version thư viện ngẫu nhiên; cần kiểm tra API compatibility, security fixes và Spring Boot BOM.

### 9.2. Framework có baseline cao hơn runtime

Một framework có thể nâng baseline giữa các major/minor releases. Application bytecode target thấp không tự hạ yêu cầu runtime của framework.

Ví dụ Spring Boot 3.5 yêu cầu ít nhất Java 17. Nếu app dùng Boot 3.5 nhưng production Java 11, sửa `maven.compiler.release=11` không làm Boot 3.5 chạy được. Cần nâng runtime lên 17+ hoặc chọn framework version tương thích với runtime theo chính sách hỗ trợ.

### 9.3. Dùng source/target thay vì release

`source=17` và `target=17` kiểm soát ngôn ngữ và bytecode, nhưng nếu compiler JDK21 vẫn nhìn thấy Java21 APIs, source có thể gọi API mới. Runtime Java17 sau đó lỗi linkage.

Ưu tiên `--release 17` trong Maven/Gradle. Nếu build tool/plugin không hỗ trợ release option, kiểm tra compatibility và cân nhắc compiler/toolchain JDK17 thật.

### 9.4. Annotation processors và generated code

Lombok, MapStruct, QueryDSL hoặc custom annotation processors có thể chạy trong compiler process và tạo code. Các processors cũng có yêu cầu JDK riêng; plugin/compiler có thể fail trước khi tạo application classes.

Phân biệt:

- Processor binary cần chạy được trên JVM/compiler JDK đang dùng.
- Generated Java source cần được compile theo target/release của project.
- Processor có thể tự sinh bytecode hoặc classes theo cơ chế riêng; cần kiểm tra output.
- Compiler plugin, processor plugin và Maven JVM có thể không dùng cùng JDK nếu toolchains chưa áp dụng cho tất cả.

Khi lỗi xảy ra ngay ở compile phase, đọc stack trace đầu tiên và xem đó là processor/plugin hay class của application runtime.

### 9.5. Kotlin, Scala, Groovy và mixed-language project

`maven.compiler.release` chỉ cấu hình Java compiler. Kotlin có `jvmTarget`/`jdkRelease`, Scala có bytecode target/toolchain riêng, Groovy compiler cũng có target bytecode riêng.

Nếu Java compile ra major 61 nhưng Kotlin module ra major 65, executable JAR vẫn có class Java 21. Cần cấu hình từng compiler plugin và kiểm tra class output của từng source set/module.

### 9.6. Multi-release JAR

Một dependency có thể là `Multi-Release JAR`: cùng một JAR chứa class base và implementation theo thư mục `META-INF/versions/N`. Manifest có `Multi-Release: true` để JVM chọn class version phù hợp với runtime.

Ví dụ, JAR có base classes hỗ trợ Java 11 và version-specific classes trong `META-INF/versions/21` cho Java 21. JVM Java 17 không nhất thiết load class Java 21 trong thư mục version 21; nó chọn implementation phù hợp nhất không vượt quá runtime.

Do đó không viết script quét mọi entry rồi báo fail chỉ vì nhìn thấy class major cao trong `META-INF/versions/21`. Cần hiểu manifest và quy tắc multi-release. Ngược lại, class major cao ở base path của dependency không phải multi-release có thể thực sự gây lỗi.

### 9.7. Preview features

Class file dùng preview features có thể mang `minor_version=65535`. Khi chạy, JVM cần đúng Java release tương ứng và flag `--enable-preview`. Class preview không tự được coi như bytecode bình thường chỉ vì major version nằm trong dải hỗ trợ.

Nếu thông điệp lỗi nhắc preview features hoặc minor version `65535`, kiểm tra compiler có bật `--enable-preview` không và runtime có dùng cùng release/flag tương ứng không.

## 10. Ứng dụng Spring Boot Java 17 để kiểm chứng

Tạo `src/main/java/demo/CompatibilityDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompatibilityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CompatibilityDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println(
                "java-compatibility-demo:ready");
    }
}
~~~

Dùng POM ở mục 7, build:

~~~bash
mvn -B -ntp clean verify
~~~

Inspect class:

~~~bash
javap -verbose target/classes/demo/CompatibilityDemoApplication.class
~~~

Với `maven.compiler.release=17`, tìm:

~~~text
major version: 61
~~~

Chạy executable JAR:

~~~bash
java -jar target/java-compatibility-demo-1.0.0.jar --spring.main.web-application-type=none --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout do `CommandLineRunner` in chính xác:

~~~text
java-compatibility-demo:ready
~~~

Spring Boot logs có thể xuất hiện tùy logging config; dòng trên là application output. Vì ví dụ không dùng web starter nên tiến trình có thể kết thúc sau khi runner hoàn thành.

### 10.1. Kiểm chứng trên hai runtime

Nếu có cả JDK17 và JDK21:

~~~bash
/path/to/jdk17/bin/java -jar target/java-compatibility-demo-1.0.0.jar
/path/to/jdk21/bin/java -jar target/java-compatibility-demo-1.0.0.jar
~~~

Với class/dependencies tương thích Java17 và không dùng API/feature yêu cầu cao hơn, cả hai runtime có thể chạy. Java21 hỗ trợ class major61; Java17 cũng hỗ trợ major61. Runtime mới hơn thường đọc được bytecode release cũ hơn, nhưng vẫn cần test API behavior và dependencies.

## 11. Docker và Kubernetes: nơi mismatch thường lộ muộn

### 11.1. Dockerfile dùng JRE 17

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app
COPY target/java-compatibility-demo-1.0.0.jar /app/application.jar

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Docker image dùng JRE17; JAR phải được compile cho Java17 hoặc thấp hơn và mọi dependencies/framework phải tương thích Java17.

Kiểm tra runtime trong image:

~~~bash
docker run --rm --entrypoint java compatibility-demo:1.0.0 -version
~~~

Kiểm tra ứng dụng:

~~~bash
docker run --rm compatibility-demo:1.0.0 --spring.main.web-application-type=none --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Nếu host Java21 chạy được nhưng container Java17 báo `UnsupportedClassVersionError`, so class major với runtime trong image. Không lấy `java -version` của host thay cho version container.

### 11.2. Build stage và runtime stage khác nhau

Một multi-stage Dockerfile có thể build trên JDK21 rồi chạy trên JRE17. Điều này hợp lệ **nếu** compiler dùng `--release 17` và mọi dependencies tương thích.

~~~text
Build stage      : JDK 21 + Maven
Compiler         : --release 17
Artifact         : class major 61
Runtime stage    : JRE 17
Kết quả mong đợi : compatible nếu dependencies cũng hỗ trợ Java 17
~~~

Nếu build stage không set release, nó có thể tạo major65 rồi copy vào runtime stage Java17. Docker build vẫn thành công vì `COPY` không kiểm tra class-file compatibility; lỗi chỉ lộ khi container khởi động và JVM nạp class.

### 11.3. Kubernetes image tag và digest

Trong Kubernetes, pod có thể chạy image khác local test. Kiểm tra:

- Image reference trong Deployment/StatefulSet.
- Image digest thực tế node đã kéo.
- Base image/JRE version bên trong.
- Multi-arch manifest được chọn theo node architecture.
- Init containers, sidecars và startup scripts có gọi Java khác không.

Nếu dùng mutable tag, hai nodes có thể kéo image khác nhau theo thời điểm. Với release, pin registry digest và lưu JAR SHA/source revision. Một lỗi chỉ xuất hiện ở một node có thể là image rollout không đồng nhất.

## 12. CI: khóa Java version giữa build, test và runtime

### 12.1. GitHub Actions với Java 17

~~~yaml
name: Java 17 compatibility

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show Java used by Maven
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Build and test
        run: ./mvnw -B -ntp clean verify

      - name: Inspect compiled bytecode
        run: |
          javap -verbose target/classes/demo/CompatibilityDemoApplication.class |
            grep "major version"

      - name: Run packaged executable JAR
        run: |
          output="$(java -jar target/java-compatibility-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --spring.main.web-application-type=none)"
          test "$output" = "java-compatibility-demo:ready"
~~~

`setup-java` cài Java17 cho job; `mvnw -version` cho biết Maven JVM; `javap` xác nhận major version; cuối cùng `java -jar` chạy đúng packaged JAR trong cùng runtime.

Nếu muốn build trên JDK21 nhưng target Java17, đổi `java-version` thành 21 nhưng giữ `maven.compiler.release=17`, rồi **bổ sung job/runtime smoke bằng Java17**. Chỉ test bằng JDK21 không chứng minh artifact chạy trên Java17.

### 12.2. Matrix test nhiều runtime

Có thể build một artifact Java17 rồi test cùng file trên Java17 và Java21:

~~~yaml
strategy:
  matrix:
    java: ['17', '21']
~~~

Trong mỗi matrix job, cài runtime theo matrix, download **cùng executable JAR** từ build job và chạy smoke test. Không build lại ở mỗi matrix nếu mục tiêu là xác nhận một binary chạy trên nhiều JVM; nếu mỗi job tự compile, bạn đang test các artifacts khác nhau.

Nếu chỉ support Java17 production, Java21 matrix là kiểm tra compatibility bổ sung, không thay Java17 gate bắt buộc.

### 12.3. Kiểm tra image runtime

Một stage container nên:

1. Build executable JAR bằng release/toolchain đã khóa.
2. Lưu SHA-256 và chuyển đúng JAR đã kiểm tra.
3. Docker build từ JAR đó.
4. Xác nhận file JAR trong image giống bytes đã chuyển.
5. Gọi `java -version` trong image.
6. Smoke-test ứng dụng trong container.
7. Chỉ publish image đã qua các gates.

Build xanh trên runner Java21 nhưng deploy image Java17 là mismatch cần phát hiện trước release.

## 13. Phân biệt UnsupportedClassVersionError với lỗi liên quan

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM không hỗ trợ class-file major/minor hoặc preview mode | Class version, runtime, compiler target, preview flag |
| `NoSuchMethodError` | Class được load nhưng runtime class thiếu method mà bytecode mong đợi | Dependency version conflict, API platform mismatch |
| `NoSuchFieldError` | Runtime class thiếu field mà compile-time class tham chiếu | Dependency mediation và binary compatibility |
| `NoClassDefFoundError` | Class cần thiết không có hoặc static initialization thất bại | Classpath/nested JAR, init exception trước đó |
| `ClassNotFoundException` | Code dùng class-loading API không tìm thấy class | Classpath, classloader, optional dependency |
| `IncompatibleClassChangeError` | Binary contract thay đổi giữa compile/runtime | API shape, static/instance change, dependency conflict |
| `UnsupportedOperationException` | Operation không được implementation hỗ trợ | Runtime behavior/API contract; không phải bytecode version |

Nếu major version thấp hơn runtime nhưng ứng dụng vẫn lỗi, đừng tiếp tục nâng JDK theo phản xạ. Có thể vấn đề là dependency conflict hoặc API mismatch.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Bước xử lý |
| --- | --- | --- |
| Class major 65, runtime max 61 | Java21 bytecode chạy Java17 | Compile bằng `--release 17` hoặc nâng runtime |
| App class major61 nhưng vẫn lỗi | Dependency/framework/plugin class mới hơn | Đọc tên class trong lỗi, inspect dependency JAR |
| `java -version` là 17 nhưng Maven build fail | Maven JVM hoặc plugin dùng JDK khác | `mvn -version`, Toolchains, plugin requirements |
| Maven JVM 21 nhưng output major65 | `maven.compiler.release` chưa áp dụng | Effective POM, Compiler Plugin config/log |
| Maven JVM21, compiler toolchain17, app vẫn fail | Dependency hoặc generated code không tương thích | Dependency tree và archive inspection |
| `javac -version` là 17 nhưng `java -version` là 11 | PATH có nhiều JDK | Kiểm tra executable paths và JAVA_HOME |
| Local chạy, Docker fail | Base image dùng JRE thấp hơn host | `docker run --entrypoint java ... -version` |
| CI build xanh, production fail | CI test runtime mới hơn production | Chạy artifact trên production baseline |
| Test fail nhưng app chạy | Surefire/Failsafe JVM khác compile/runtime | Kiểm tra test toolchain và test runtime |
| Spring Boot plugin fail trước compile | Maven JVM không đáp ứng plugin/framework minimum | Kiểm tra `mvn -version` và plugin requirements |
| Java17 bytecode nhưng NoSuchMethodError | Compile với API JDK mới qua source/target | Dùng `--release 17` |
| Một dependency class fail | Một transitive JAR có bytecode mới | `dependencyInsight`/`dependency:tree` và javap |
| Class version cao trong `META-INF/versions/21` | Multi-release JAR | Xem manifest và runtime selection |
| Lỗi nhắc preview features/minor 65535 | Preview bytecode chạy sai release/thiếu flag | Cùng JDK release và `--enable-preview` |
| Gradle daemon không chạy trên Java hiện tại | Gradle version không hỗ trợ JVM daemon | Compatibility matrix, wrapper upgrade |
| Gradle compile khác Java dự kiến | Toolchain chưa cấu hình hoặc task override | `javaToolchains`, compile task config |
| Một module có major cao | Module dùng compiler/target riêng | Kiểm tra child POM/build.gradle và inherited config |
| K8s pod chỉ lỗi ở một node | Image digest/architecture/rollout khác | Inspect pod imageID và actual runtime |

## 15. Checklist chẩn đoán theo thứ tự

Khi gặp lỗi, làm theo chuỗi sau:

1. **Ghi nguyên văn lỗi.** Lấy class name và major/minor version.
2. **Xác định tiến trình ném lỗi.** Maven/Gradle build, test JVM, ứng dụng local hay container.
3. **Đo JVM thật.** `java -version`, `mvn -version`, `./gradlew --version`, Docker runtime.
4. **Xác định class file.** Dùng `javap -verbose` hoặc `ClassVersionProbe`.
5. **Tìm nguồn class.** Project output, dependency tree, nested JAR, plugin, generated code.
6. **Kiểm tra compiler config.** `maven.compiler.release`, Maven Toolchains, Gradle toolchain và `options.release`.
7. **Kiểm tra framework/dependency baseline.** Spring Boot, Spring Framework, Kotlin/Scala plugins và transitive dependencies.
8. **Build sạch và inspect lại.** Dùng `mvn clean`/`gradlew clean`, không xóa local dependency repository tùy tiện.
9. **Chạy đúng artifact trên runtime đích.** Không thay bằng IDE classpath hoặc `spring-boot:run`.
10. **Kiểm tra Docker/Kubernetes image thực tế.** Runtime JRE, image digest, platform và startup command.
11. **Lưu evidence.** Commit, toolchain versions, class major, dependency tree, JAR hash và image digest.

### 15.1. Lệnh thu thập thông tin nhanh

Linux/macOS:

~~~bash
java -version
javac -version
mvn -version
./mvnw -version
./gradlew --version
mvn help:effective-pom
mvn dependency:tree -Dscope=runtime
javap -verbose target/classes/demo/CompatibilityDemoApplication.class
~~~

Windows PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
java -version
javac -version
mvn -version
.\mvnw.cmd -version
javap -verbose .\target\classes\demo\CompatibilityDemoApplication.class |
    Select-String "major version"
~~~

Chạy những lệnh phù hợp với build tool thực tế; không cần Maven và Gradle đều có trong mọi project.

## 16. Checklist phòng ngừa trong dự án

### Build tool và compiler

- [ ] Xác định JDK tối thiểu để chạy Maven/Gradle và plugin.
- [ ] Khai báo release target rõ ràng; Maven dùng `maven.compiler.release`, Gradle dùng toolchain + `options.release`.
- [ ] Nếu cần compiler JDK cụ thể, cấu hình Maven/Gradle toolchain.
- [ ] Không chỉ dựa vào PATH hoặc IDE JDK settings.
- [ ] Đồng bộ Java target giữa Java, Kotlin, Scala, Groovy và generated code.
- [ ] Kiểm tra annotation processors và compiler plugins.

### Dependency và framework

- [ ] Chọn Spring Boot version phù hợp runtime baseline.
- [ ] Kiểm tra transitive dependencies và minimum Java requirement của chúng.
- [ ] Dùng BOM/dependency management để giảm version drift.
- [ ] Inspect class được nêu trong error stack thay vì nâng tất cả dependencies.
- [ ] Xem xét multi-release JAR và preview features đúng ngữ cảnh.

### Test và release runtime

- [ ] Test packaged JAR, không chỉ development classpath.
- [ ] Có smoke test trên JVM production baseline.
- [ ] Container base image dùng đúng JRE/Java version.
- [ ] Lưu image digest và kiểm tra runtime trong image.
- [ ] CI build, test, package và deploy dùng version policy nhất quán.
- [ ] Sau khi đổi dependency/JDK/runtime, chạy lại compatibility tests.

## 17. Câu hỏi tự kiểm tra

**A. Class file major 65 có nghĩa là Java 17 không?**

Không. Major 65 tương ứng Java 21; Java 17 là major 61.

**B. Maven chạy bằng JDK21 nhưng compile với `--release 17` có thể tạo class chạy trên Java17 không?**

Có, nếu source/dependencies/framework tương thích và compiler thực sự áp dụng release 17. `--release` giới hạn bytecode và API platform.

**C. Đặt `source=17` và `target=17` đã tương đương `--release 17` chưa?**

Chưa. Source/target không giới hạn đầy đủ JDK APIs mà compiler nhìn thấy; code có thể gọi API mới rồi lỗi ở runtime cũ.

**D. `mvn -version` báo Java21. Có chứng minh compiler dùng JDK21 không?**

Không nếu Maven Toolchains hoặc compiler-specific toolchain được cấu hình. `mvn -version` là JVM chạy Maven; kiểm tra toolchain selection và compiler logs.

**E. Application classes major61 nhưng Spring Boot JAR vẫn lỗi major65. Nguyên nhân có thể là gì?**

Một nested dependency, Boot loader, generated class hoặc plugin-related class có major65. Kiểm tra tên class trong stack trace và inspect JAR dependency tương ứng.

**F. Host có Java21 nhưng Docker image JRE17. Runtime version nào quyết định?**

JRE trong image. Host Java không thay thế JVM chạy bên trong container.

**G. Multi-release JAR chứa class major65 có chắc không chạy trên Java17?**

Không. Nếu class nằm đúng `META-INF/versions/21` trong JAR có manifest `Multi-Release: true`, JVM17 có thể chọn base/version thấp hơn. Phải xem vị trí và manifest.

**H. Vì sao dùng `--release 17` vẫn cần test trên Java17?**

Compiler target không chứng minh mọi dependency, framework, native library, runtime configuration hoặc container đều tương thích. Test trên runtime đích là gate độc lập.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Oracle — UnsupportedClassVersionError API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedClassVersionError.html
- Java Virtual Machine Specification, Java SE 21 — Class File Format: https://docs.oracle.com/javase/specs/jvms/se21/html/index.html
- Apache Maven Compiler Plugin — Setting the --release of the Java Compiler: https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html
- Apache Maven — Guide to Targeting a Java Version: https://maven.apache.org/guides/mini/guide-java-target.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven Toolchains Plugin — Introduction and goals: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Apache Maven Toolchains Plugin — Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Gradle — Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Building Java & JVM projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Java compatibility matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Java 17 — javap tool reference: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Ghi nhớ:** `UnsupportedClassVersionError` là vấn đề tương thích **class-file format với JVM thực tế đang nạp class**. Hãy xác định đúng class và đúng tiến trình, sau đó kiểm soát compiler bằng `--release`/toolchains, kiểm tra dependencies và test packaged artifact trên runtime production. Đồng bộ Java version từ build tool đến Docker/Kubernetes giúp phát hiện mismatch ngay trong CI thay vì sau khi deploy.