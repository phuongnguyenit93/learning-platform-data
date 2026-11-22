# Thử nghiệm trên JDK được hỗ trợ và kiểm tra mức ngôn ngữ

## 1. Mục tiêu

Một dự án Java cần xác định rõ ba điều: JDK nào được dùng để biên dịch, mã nguồn được phép sử dụng cú pháp/API của Java release nào, và ứng dụng phải chạy được trên những JDK runtime nào. Nếu không cố định các yếu tố này, máy cá nhân, IDE và CI có thể biên dịch hoặc chạy bằng những phiên bản khác nhau, khiến lỗi chỉ xuất hiện ở một môi trường.

Quy trình đáng tin cậy là khai báo release mục tiêu trong cấu hình build, chọn JDK bằng toolchain, sau đó chạy build và kiểm thử trên từng runtime nằm trong support matrix của sản phẩm.

## 2. Phân biệt JDK, language level, release và runtime

| Khái niệm | Ý nghĩa | Cách xác minh |
|---|---|---|
| JDK chạy build | JDK chạy tiến trình Maven hoặc Gradle | mvn --version, ./gradlew --version |
| JDK compiler | JDK cung cấp javac thực sự được build sử dụng | Build log hoặc cấu hình toolchain |
| Language level | Tập cú pháp Java mà compiler chấp nhận | Tùy chọn --release |
| Platform API level | Các API Java/JDK mà mã nguồn được phép gọi | Tùy chọn --release |
| Bytecode target | Định dạng class file được sinh ra | javap -verbose |
| Runtime JDK | JVM thực sự chạy ứng dụng và test | java --version, Runtime.version() |

Các giá trị này có liên quan nhưng không đồng nghĩa. Ví dụ, có thể dùng compiler của JDK 25 để biên dịch mã theo Java 21, sinh bytecode chạy được trên Java 21, rồi chạy cùng artifact trên cả JDK 21 và JDK 25.

### Vì sao nên dùng --release

Từ JDK 9, javac cung cấp tùy chọn --release. Tùy chọn này đồng thời giới hạn cú pháp ngôn ngữ, API nền tảng và phiên bản bytecode theo release được chọn. Đây là cách kiểm soát tương thích đầy đủ hơn việc chỉ đặt source và target.

Nếu chỉ đặt source và target, compiler có thể vẫn nhìn thấy API mới của JDK đang chạy. Mã nguồn vì thế có thể biên dịch thành công nhưng lỗi khi chạy trên runtime cũ hơn do gọi API chưa tồn tại ở runtime đó. --release giúp compiler phát hiện loại lỗi này ngay trong giai đoạn biên dịch.

Ví dụ, khi biên dịch bằng JDK 25 với --release 21, mã nguồn chỉ được dùng cú pháp và API được hỗ trợ ở Java 21; class file được tạo theo định dạng Java 21. Không kết hợp --release với source hoặc target trong cùng lần biên dịch.

--release chỉ kiểm soát API của nền tảng Java. Nó không đảm bảo thư viện bên thứ ba, native library, agent hoặc framework tương thích với mọi runtime. Các thành phần đó vẫn cần được kiểm tra khi chạy test trên từng JDK.

## 3. Xác định JDK nào còn được hỗ trợ

Không nên coi phiên bản mới nhất là phiên bản được mọi ứng dụng hoặc mọi nhà cung cấp hỗ trợ. Support matrix phải dựa trên:

- Chính sách hỗ trợ của nhà cung cấp JDK đang sử dụng.
- JDK tối thiểu mà sản phẩm cam kết hỗ trợ.
- Phiên bản framework, application server, driver, agent và thư viện đang dùng.
- Hệ điều hành, kiến trúc CPU và container image được triển khai.
- Yêu cầu cập nhật bảo mật, thời hạn hỗ trợ và điều khoản cấp phép.

Tại ngày 06-11-2026, roadmap Oracle liệt kê Java 17, 21 và 25 là các nhánh LTS; Java 25 là LTS mới nhất và Java 27 là feature release mới nhất. Đây là phân loại và lịch hỗ trợ của Oracle, không phải cam kết hỗ trợ chung cho mọi bản phân phối OpenJDK. Các nhà cung cấp khác có thể có thời hạn cập nhật và điều khoản khác nhau. Luôn kiểm tra roadmap của đúng nhà cung cấp và phiên bản binary mà tổ chức chọn.

Một support matrix nên ghi rõ ít nhất:

| Thành phần | Ví dụ |
|---|---|
| JDK distribution | Eclipse Temurin |
| JDK runtime được hỗ trợ | 21 và 25 |
| Java release dùng để biên dịch | 21 |
| Build tool | Maven Wrapper hoặc Gradle Wrapper đã được pin |
| Hệ điều hành/kiến trúc | Các nền tảng sản phẩm thực sự phát hành |
| Kiểm thử bắt buộc | Build, unit test, integration test và smoke test |
| Bản cập nhật | JDK patch version và ngày xác minh gần nhất |

Ví dụ 21 và 25 trong bài chỉ minh họa cho một ma trận có hai runtime. Dự án thực tế phải thay bằng các phiên bản có trong chính sách hỗ trợ của nó.

## 4. Kiểm tra JDK đang được sử dụng

Chạy các lệnh sau trong cùng terminal dùng để build:

~~~bash
java --version
javac --version
mvn --version
./mvnw --version
./gradlew --version
~~~

Trên Windows, dùng mvnw.cmd và gradlew.bat thay cho các script có dấu gạch chéo.

- java --version cho biết runtime được tìm thấy qua PATH.
- javac --version cho biết compiler được tìm thấy qua PATH.
- mvn --version hoặc ./mvnw --version cho biết JVM chạy Maven.
- ./gradlew --version cho biết JVM chạy Gradle và phiên bản Gradle Wrapper.

Kết quả của các lệnh này chưa chắc là JDK mà một toolchain riêng của dự án sử dụng. Maven Toolchains và Gradle Java Toolchains có thể chọn JDK khác với JDK chạy tiến trình build. Vì vậy, cần kiểm tra thêm cấu hình build và log chọn toolchain.

Không nên dựa riêng vào JAVA_HOME hoặc cấu hình JDK trong IDE để xác định language level của dự án. Những thiết lập đó có thể khác nhau giữa máy lập trình viên và CI.

## 5. Thử biên dịch và chạy trên nhiều runtime

Tạo file src/main/java/demo/LanguageLevelCheck.java:

~~~java
package demo;

public class LanguageLevelCheck {
    record BuildTarget(int release) {}

    public static void main(String[] args) {
        var target = new BuildTarget(21);
        System.out.println("target=" + target.release());
        System.out.println("runtime=" + Runtime.version().feature());
    }
}
~~~

Ví dụ này sử dụng record và local-variable type inference, đồng thời đọc feature version của JVM tại runtime. Các cú pháp/API trên đều nằm trong phạm vi Java 21.

Giả sử JDK 25 là compiler và Java 21 là release mục tiêu. Trước khi biên dịch, tạo thư mục `out` nếu chưa tồn tại.

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out
~~~

Trên macOS/Linux:

~~~bash
mkdir -p out
~~~

Sau đó biên dịch:

~~~bash
javac --release 21 -d out src/main/java/demo/LanguageLevelCheck.java
~~~

Sau khi biên dịch, chạy chính thư mục class file đó bằng từng runtime được hỗ trợ:

~~~bash
/opt/jdks/jdk-21/bin/java -cp out demo.LanguageLevelCheck
/opt/jdks/jdk-25/bin/java -cp out demo.LanguageLevelCheck
~~~

Kết quả khi chạy bằng JDK 21:

~~~text
target=21
runtime=21
~~~

Kết quả khi chạy bằng JDK 25:

~~~text
target=21
runtime=25
~~~

Hai lần chạy sử dụng cùng class file. Giá trị target vẫn là 21; giá trị runtime thay đổi theo JVM đang thực thi.

Có thể kiểm tra bytecode bằng:

~~~bash
javap -verbose -classpath out demo.LanguageLevelCheck
~~~

Với Java 21, phần đầu thông tin class file có major version 65. Đây là cách kiểm tra định dạng bytecode được tạo ra; nó không thay thế việc chạy ứng dụng trên runtime mục tiêu.

### Kiểm tra API có đúng release hay không

Một compiler mới có thể nhìn thấy API mà runtime cũ không có. Ví dụ, List.getFirst() thuộc API Java 21. Khi biên dịch mã gọi API này bằng compiler JDK 25 nhưng đặt --release 17, compiler phải báo lỗi vì API đó không thuộc Java 17.

Điều này cho thấy --release kiểm tra cả API nền tảng, không chỉ cú pháp. Sau khi biên dịch thành công, vẫn phải chạy test trên runtime thấp nhất mà sản phẩm cam kết hỗ trợ.

## 6. Cấu hình Maven

Đặt release mục tiêu trong pom.xml và pin phiên bản Maven Compiler Plugin để kết quả build không phụ thuộc vào phiên bản plugin mặc định của môi trường:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
        </plugin>
    </plugins>
</build>
~~~

Đây là cấu hình release 21. Maven Compiler Plugin chuyển thuộc tính trên thành tùy chọn --release của javac. Khi thay đổi release mục tiêu, hãy cập nhật đúng một giá trị theo support matrix của dự án.

### Chọn JDK compiler bằng Maven Toolchains

Toolchain cho phép Maven sử dụng JDK của dự án độc lập với JDK đang chạy Maven. Cấu hình lựa chọn toolchain trong pom.xml:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
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
                <version>25</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Trên máy build, tạo file ~/.m2/toolchains.xml với đường dẫn JDK đã cài:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>25</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-25</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Giá trị version và vendor trong pom.xml phải khớp với một toolchain được khai báo trên máy build. Đường dẫn jdkHome là ví dụ; mỗi môi trường cần trỏ đến thư mục JDK thực tế.

Chạy build:

~~~bash
./mvnw clean verify
~~~

Maven Toolchains có thể cung cấp cùng JDK cho các plugin tương thích với toolchain, chẳng hạn compiler và Surefire/Failsafe. Khi cần kiểm tra nhiều runtime, hãy cấu hình CI để mỗi job chọn đúng JDK runtime của job đó; không giả định một lần biên dịch đã kiểm tra mọi runtime.

## 7. Cấu hình Gradle

Với Gradle Kotlin DSL, khai báo toolchain và release riêng:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~

Cấu hình trên dùng JDK 25 cho các tác vụ Java của dự án và giới hạn mã nguồn/API/bytecode ở release 21.

Các tác vụ test mặc định sử dụng toolchain của dự án. Có thể tạo tác vụ kiểm tra runtime Java 21 riêng:

~~~kotlin
tasks.register<Test>("testOn21") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
}
~~~

Chạy:

~~~bash
./gradlew clean check
./gradlew testOn21
./gradlew -q javaToolchains
~~~

Tác vụ testOn21 chạy test bằng JDK 21; các tác vụ Java khác vẫn sử dụng toolchain đã khai báo ở cấp dự án. JDK 21 phải được cài sẵn hoặc được cấu hình để Gradle có thể cấp phát toolchain tương ứng.

Java Toolchain điều khiển compiler, test launcher và các công cụ Java mà Gradle task sử dụng. Nó không tự quyết định JVM chạy Gradle Daemon. Phiên bản Gradle Wrapper và JDK chạy Gradle vẫn phải tương thích với nhau. Kiểm tra cả hai khi build trên máy cá nhân và CI.

## 8. Thiết kế kiểm thử trong CI

Một pipeline tốt cần kiểm tra cả khả năng build lẫn khả năng chạy của artifact.

1. **Build matrix:** chạy build trên từng JDK compiler được support matrix cho phép. Việc này phát hiện khác biệt của compiler, annotation processor, plugin và build tool.
2. **Runtime matrix:** chạy cùng artifact đã biên dịch theo release mục tiêu trên từng JDK runtime được sản phẩm hỗ trợ. Ít nhất phải kiểm tra runtime thấp nhất và mới nhất; nếu sản phẩm cam kết nhiều nhánh, hãy kiểm tra từng nhánh.
3. **Integration test:** kiểm tra kết nối database, driver, TLS, serialization, reflection, module loading, native library và các thành phần phụ thuộc vào runtime khi những chức năng đó có trong sản phẩm.
4. **Packaging test:** kiểm tra JAR hoặc container image thực tế. JDK trong máy CI có thể khác JRE/JDK bên trong image triển khai.
5. **Patch update:** chạy lại pipeline sau khi cập nhật JDK patch hoặc dependency quan trọng; không chỉ ghi nhận major version.

Ví dụ một pipeline có thể dùng matrix runtime 21 và 25, cài đúng distribution đã phê duyệt ở mỗi job, rồi chạy Maven Wrapper hoặc Gradle Wrapper. Release biên dịch vẫn giữ ở 21 nếu đó là mức thấp nhất mà sản phẩm cam kết hỗ trợ. Nếu sản phẩm hỗ trợ JDK 27, thêm JDK 27 vào matrix; nếu không, không cần coi feature release đó là runtime được hỗ trợ.

Để kết quả có thể tái lập, hãy commit Maven Wrapper hoặc Gradle Wrapper, pin plugin/build tool versions, khóa dependency khi phù hợp, và ghi nhận JDK distribution cùng patch version trong log CI.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| invalid source release | Compiler đang chạy quá cũ hoặc release không được compiler hỗ trợ | Kiểm tra javac --version và toolchain |
| UnsupportedClassVersionError | Runtime thấp hơn phiên bản bytecode của class | Kiểm tra runtime và major version bằng javap |
| cannot find symbol khi gọi API | API không thuộc release đang cấu hình hoặc dependency thiếu | Kiểm tra --release và dependency |
| NoSuchMethodError hoặc NoClassDefFoundError | Phiên bản thư viện lúc chạy khác lúc biên dịch, hoặc classpath bị xung đột | Kiểm tra dependency tree và runtime classpath |
| Chạy được trong IDE nhưng lỗi ở CI | IDE và build tool đang dùng JDK/toolchain khác nhau | Kiểm tra IDE project SDK, wrapper và toolchain |
| Maven/Gradle chạy bằng JDK không mong muốn | JAVA_HOME, PATH hoặc JVM của build daemon khác dự kiến | Kiểm tra mvn --version, gradlew --version và toolchain log |

Không sửa lỗi bằng cách tùy tiện hạ release hoặc đổi JDK của máy phát triển. Trước tiên xác định sản phẩm thực sự cam kết hỗ trợ runtime nào, sau đó chỉnh compiler, toolchain và CI theo cùng một support matrix.

## 10. Checklist nghiệm thu

- [ ] Support matrix ghi rõ JDK distribution, runtime major, patch policy và hệ điều hành hỗ trợ.
- [ ] Release mục tiêu được khai báo trong build file.
- [ ] Maven/Gradle plugin và wrapper versions được pin.
- [ ] Compiler được chọn bằng toolchain khi cần tách khỏi JDK chạy build.
- [ ] IDE đồng bộ cấu hình từ Maven/Gradle project.
- [ ] Build và unit test chạy thành công trên từng JDK được yêu cầu.
- [ ] Artifact được chạy trên từng runtime trong support matrix.
- [ ] Bytecode được kiểm tra khi cần xác minh target release.
- [ ] Integration test và container image được chạy trên môi trường gần production.
- [ ] JDK patch và ngày kiểm tra gần nhất được ghi lại.

## Tài liệu tham khảo

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — phân loại LTS và lịch hỗ trợ của Oracle.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/) — các bản JDK hiện hành.
- [The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — ý nghĩa của --release và các tùy chọn compiler.
- [Maven: Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html) — cấu hình release trong Maven Compiler Plugin.
- [Maven: Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html) — chọn JDK độc lập với JVM chạy Maven.
- [Gradle: Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — Java toolchains và --release.
