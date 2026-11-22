# Xử lý lỗi Unsupported class version trong Java

## 1. Lỗi Unsupported class version là gì?

**UnsupportedClassVersionError** là lỗi JVM báo rằng một file .class được tạo theo định dạng bytecode mới hơn định dạng mà Java runtime hiện tại hỗ trợ. Trường hợp thường gặp nhất là project được compile bằng JDK mới nhưng ứng dụng lại chạy bằng JRE/JDK cũ.

Ví dụ:

~~~text
java.lang.UnsupportedClassVersionError:
  demo/App has been compiled by a more recent version of the Java Runtime
  (class file version 61.0),
  this version of the Java Runtime only recognizes class file versions up to 55.0
~~~

Diễn giải:

- Class cần chạy có major version 61, tương ứng Java 17.
- Runtime chỉ hỗ trợ đến major version 55, tương ứng Java 11.
- Java 11 không thể nạp class được compile cho Java 17.
- Cần nâng runtime lên Java 17 trở lên hoặc build lại toàn bộ class liên quan với target tương thích Java 11.

Lỗi có thể xuất hiện khi chạy ứng dụng chính, load một thư viện, khởi tạo plugin, chạy test, chạy annotation processor hoặc khởi động một build tool. Vì vậy, project compile thành công chưa chứng minh runtime trên máy đích đủ mới.

## 2. JVM đọc phiên bản class file như thế nào?

Mỗi file class bắt đầu bằng header nhị phân. Phần đầu gồm:

| Trường | Kích thước | Ý nghĩa |
|---|---:|---|
| magic | 4 byte | Giá trị cố định 0xCAFEBABE, nhận diện class file |
| minor_version | 2 byte | Phiên bản phụ |
| major_version | 2 byte | Phiên bản định dạng class chính |

JVM đọc major/minor trước khi xác minh và thực thi bytecode. Với class file hiện đại, major version tăng theo từng Java SE release. Số này không giống số phiên bản Java: Java 17 tạo class file major 61, không phải 17.

Một class file có major version cao hơn mức JVM hỗ trợ sẽ bị từ chối trong quá trình load class. Đây là lỗi tương thích định dạng bytecode, không phải lỗi cú pháp Java hay lỗi thiếu một class trong classpath.

## 3. Bảng đối chiếu Java release và class file major version

Các mốc thường gặp:

| Java release | Class file major | Ghi chú |
|---|---:|---|
| Java 8 | 52 | Nhiều ứng dụng và thư viện legacy |
| Java 11 | 55 | LTS |
| Java 17 | 61 | LTS |
| Java 21 | 65 | LTS |
| Java 24 | 68 | JDK 24 |
| Java 25 | 69 | LTS |
| Java 26 | 70 | JDK 26 |

JVM của một release hỗ trợ các major version cũ hơn trong dải tương thích của đặc tả. Ví dụ Java 25 hỗ trợ class file major 69 và các major cũ hơn; Java 24 chỉ hỗ trợ đến major 68.

Không lấy số major rồi trừ một để suy ra Java release. Hãy tra bảng hoặc dùng javap -verbose để đọc class file thực tế. Đặc tả JVMS của từng release là nguồn chuẩn khi xử lý phiên bản mới.

## 4. Phân biệt compile JDK, target release và runtime JDK

Ba phiên bản này có thể khác nhau:

- **Compile JDK:** JDK cung cấp javac dùng để biên dịch source.
- **Target release:** Java release mà class file đầu ra phải tương thích.
- **Runtime JDK:** JVM thực sự chạy ứng dụng hoặc thư viện.

Ví dụ một team có thể compile bằng JDK 24, đặt target Java 17 và deploy trên runtime Java 17. Cấu hình này hợp lệ nếu mọi dependency, plugin và class được nạp cũng tương thích Java 17.

Ngược lại, compile bằng JDK 24 theo mặc định thường tạo class file major 68. Chạy file đó trên Java 17 sẽ gây UnsupportedClassVersionError.

Không nhầm Maven/Gradle chạy bằng JDK nào với JDK được dùng cho compile task. Maven Toolchains hoặc Gradle Java Toolchains có thể chọn compiler khác với JVM đang chạy build tool.

## 5. Đọc đúng thông báo lỗi

Hãy tìm ba phần trong stack trace:

1. **Tên class:** ví dụ com/example/LibraryAdapter. Đây thường là class đầu tiên bị JVM từ chối.
2. **Class file version:** ví dụ 65.0. Đây là phiên bản bytecode của class đang được nạp.
3. **Runtime recognizes up to:** ví dụ 61.0. Đây là giới hạn của JVM hiện tại.

Ví dụ:

~~~text
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

Class yêu cầu Java 21, trong khi runtime chỉ hỗ trợ đến Java 17. Nâng runtime lên Java 21 hoặc cao hơn, hoặc dùng phiên bản dependency/build tương thích Java 17.

Nếu thông báo nói về preview features, hãy kiểm tra minor version và cờ --enable-preview. Không phải mọi UnsupportedClassVersionError đều chỉ là chênh lệch major version.

## 6. Nguyên nhân thường gặp

| Nguyên nhân | Ví dụ |
|---|---|
| Compile bằng JDK mới | Compile mặc định bằng Java 25, chạy bằng Java 17 |
| Dependency mới hơn runtime | Ứng dụng target Java 17 nhưng một thư viện yêu cầu Java 21 |
| Chọn nhầm Java trên PATH | javac là JDK 24 nhưng java chạy JDK 11 |
| IDE và terminal khác JDK | Terminal dùng Java 21, IDE Run Configuration dùng Java 17 |
| Maven/Gradle dùng JVM khác | Build daemon chạy Java 17, plugin hoặc compiler toolchain chọn Java khác |
| Docker build/runtime khác nhau | Builder compile class Java 24, runtime image chứa Java 17 |
| CI dùng runner không đồng nhất | Build job dùng JDK 25, deploy/test job dùng JDK 17 |
| Plugin hoặc annotation processor | Plugin được biên dịch cho JDK mới hơn JVM chạy Maven/Gradle |
| Preview class file | Compile preview ở một release rồi chạy ở release khác hoặc thiếu enable flag |

Không chỉ class của ứng dụng mới có thể gây lỗi. Một JAR bắc cầu, plugin, processor hoặc class được nạp động cũng có thể là nguồn gốc.

## 7. Kiểm tra Java runtime thực sự đang chạy

Trước tiên, kiểm tra cả runtime và compiler:

~~~bash
java --version
javac --version
~~~

Trên Windows PowerShell:

~~~powershell
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
readlink -f "$(command -v java)"
echo "$JAVA_HOME"
~~~

Kiểm tra các thuộc tính runtime:

~~~bash
java -XshowSettings:properties -version
~~~

Tìm java.version và java.home trong output. java.home cho biết runtime được process đó sử dụng.

Một máy có thể cài nhiều JDK. PATH có thể trỏ tới Java 11 trong khi JAVA_HOME trỏ tới JDK 24, hoặc IDE/daemon giữ một Java home khác. Chỉ kiểm tra biến JAVA_HOME là chưa đủ; phải kiểm tra đúng command/process tạo ra lỗi.

## 8. Kiểm tra class file bằng javap

javap đi kèm JDK và có thể hiển thị header của class:

~~~bash
javap -verbose -classpath target/classes demo.App
~~~

Tìm hai dòng:

~~~text
minor version: 0
major version: 61
~~~

Class trên được compile cho Java 17. Trên Windows có thể lọc output:

~~~powershell
javap -verbose -classpath target/classes demo.App | Select-String "minor version|major version"
~~~

Trên Linux/macOS:

~~~bash
javap -verbose -classpath target/classes demo.App | grep -E "minor version|major version"
~~~

Dùng đúng classpath để tránh kiểm tra nhầm một bản class khác có cùng tên. Nếu class nằm trong JAR, thêm JAR vào classpath:

~~~bash
javap -verbose -classpath libs/example-library.jar com.example.LibraryAdapter
~~~

Nếu JDK hiện tại quá cũ để hiểu class file đó, javap có thể cũng từ chối. Khi đó, chạy javap bằng JDK mới hơn hoặc dùng công cụ đọc class-file header phù hợp.

## 9. Xác định dependency gây lỗi

Khi stack trace chỉ ra class thuộc thư viện bên ngoài, tìm JAR chứa class đó rồi kiểm tra version:

~~~bash
jar tf libs/example-library.jar
javap -verbose -classpath libs/example-library.jar com.example.LibraryAdapter
~~~

Với Maven, xem cây dependency:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.example:example-library
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
~~~

Kiểm tra cả dependency bắc cầu. Project có thể khai báo trực tiếp thư viện tương thích Java 17 nhưng một dependency khác kéo về bản mới yêu cầu Java 21.

Nếu class bị lỗi thuộc plugin build, kiểm tra classloader/plugin realm và version plugin. Runtime chạy Maven/Gradle cần đủ mới để load plugin, dù application target release có thể thấp hơn.

## 10. Cách sửa 1: nâng Java runtime

Nếu ứng dụng hoặc dependency thực sự cần API/language feature của Java mới, hãy nâng runtime lên cùng release hoặc mới hơn.

Ví dụ class file major 69 cần runtime Java 25 trở lên:

~~~bash
java --version
java -jar app.jar
~~~

Sau khi nâng runtime, kiểm tra:

- Service chạy bằng đúng Java executable mới.
- JAVA_HOME, PATH, service wrapper và script khởi động đã trỏ đúng.
- Container/VM/host production có cùng runtime.
- IDE, scheduled task, Windows Service hoặc systemd unit không giữ đường dẫn Java cũ.
- Các framework, driver và native library vẫn tương thích với runtime mới.

Không chỉ cài JDK mới trên máy build rồi cho rằng production đã được nâng. Phải cập nhật môi trường thực sự khởi chạy ứng dụng.

## 11. Cách sửa 2: compile về Java release thấp hơn

Nếu production phải chạy Java 17, hãy build class file tương thích Java 17 ngay cả khi máy build dùng JDK 24 hoặc JDK 25.

Dùng javac:

~~~bash
javac --release 17 -d target/classes src/main/java/demo/App.java
~~~

--release 17 đồng thời kiểm soát:

- Cú pháp/language rules của Java 17.
- Class file target Java 17 (major 61).
- Tập API Java/JDK được phép sử dụng theo Java 17.

Đây là cách cross-compile đáng tin cậy hơn việc chỉ đặt source và target. Nếu source gọi API chỉ có từ Java 21, javac sẽ báo lỗi khi build với --release 17 thay vì để lỗi xuất hiện ở runtime.

Chỉ dùng release thấp nhất mà sản phẩm cần hỗ trợ và mọi dependency có thể đáp ứng.

## 12. Vì sao source/target không thay thế hoàn toàn --release?

Hai cấu hình cũ:

~~~bash
javac -source 17 -target 17 App.java
~~~

-source chọn quy tắc ngôn ngữ; -target chọn định dạng bytecode đầu ra. Khi compile bằng JDK mới, compiler vẫn có thể nhìn thấy API mới hơn release đích nếu không giới hạn platform API phù hợp.

Ví dụ code dùng API Java 21 có thể compile trên JDK 21 với source/target 17, nhưng sẽ không chạy trên Java 17 vì runtime không có API đó. Đây có thể dẫn tới NoSuchMethodError hoặc NoClassDefFoundError, dù major version của class đã đúng.

--release kiểm tra cả class-file target và API của release đích. Với JDK 9 trở lên, ưu tiên --release cho build cần tương thích ngược.

## 13. Cấu hình Maven Compiler Plugin

Ví dụ POM target Java 17:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

Build và kiểm tra:

~~~bash
mvn -B -ntp clean package
javap -verbose -classpath target/classes demo.App
java -jar target/app.jar
~~~

Khi dùng JDK 9 trở lên, Compiler Plugin truyền release tới javac. Maven Compiler Plugin 3.13.0 trở lên còn có cơ chế tương thích cho build bằng JDK 8 khi dùng compiler mặc định; JDK 8 không có option --release nên plugin chuyển sang source/target phù hợp. Với dự án legacy, hãy đọc đúng tài liệu plugin version đang pin.

## 14. Cấu hình Gradle Java Toolchain và options.release

Ví dụ Groovy DSL dùng JDK 24 để compile nhưng tạo bytecode/API target Java 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Nếu team đã cài JDK 17 và muốn compiler/test cùng dùng JDK 17, đặt toolchain thành 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Toolchain chọn JDK cho compile/test/Javadoc task. options.release giới hạn language/API/class file target. Hai cấu hình có mục đích khác nhau và có thể dùng cùng nhau.

Kiểm tra toolchain Gradle phát hiện:

~~~bash
./gradlew -q javaToolchains
./gradlew --version
./gradlew clean test
~~~

gradlew --version hiển thị JVM chạy Gradle/daemon. javaToolchains cho biết JDK được Gradle phát hiện và dùng làm toolchain.

## 15. Kiểm tra Maven và Gradle đang dùng JDK nào

Maven:

~~~bash
mvn --version
./mvnw --version
mvn -X -DskipTests compile
~~~

mvn --version cho biết Java chạy Maven. Nếu cấu hình Maven Toolchains, Compiler Plugin có thể dùng JDK khác để compile. Kiểm tra cấu hình toolchain và log debug khi cần xác định compiler thực tế.

Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew -Dorg.gradle.java.home=/path/to/jdk17 test
~~~

org.gradle.java.home chọn JVM chạy Gradle daemon; nó không thay thế khai báo Java Toolchain cho compile/test task. Không đặt đường dẫn này thành một JRE quá cũ nếu Gradle version đang dùng yêu cầu JVM mới hơn.

Maven Wrapper và Gradle Wrapper cố định phiên bản build tool, không tự động cố định Java runtime hoặc bytecode target. Hãy quản lý cả ba yếu tố: build tool, compiler toolchain và deployment runtime.

## 16. Kiểm tra IDE và build daemon

Một project có thể build được ở terminal nhưng chạy lỗi trong IDE vì IDE dùng JDK khác.

Kiểm tra các vị trí:

- **IntelliJ IDEA:** Project SDK, language level, Maven Runner JRE, Gradle JVM và Run/Debug Configuration.
- **Eclipse:** Installed JREs, compiler compliance level và JRE của từng Run Configuration.
- **VS Code:** Java runtime configuration và JDK được chọn cho project.
- **Gradle:** JVM chạy daemon, Java Toolchain và launcher của Test/JavaExec task.
- **Maven:** JVM chạy Maven, Maven Toolchains và compiler plugin configuration.

Sau khi đổi JDK, dừng daemon cũ nếu nó vẫn giữ JVM trước đó:

~~~bash
./gradlew --stop
~~~

Mở terminal mới hoặc restart IDE khi environment đã thay đổi. Kiểm tra lại java.version và java.home của chính process chạy ứng dụng.

## 17. Kiểm tra Docker và container runtime

Một lỗi phổ biến là builder image mới hơn runtime image:

~~~dockerfile
FROM eclipse-temurin:24-jdk AS build
WORKDIR /app
COPY . .
RUN ./mvnw -B -ntp clean package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Nếu Maven compile mặc định bằng JDK 24, class file có thể là major 68 nhưng container cuối chỉ có Java 17 (major 61). Ứng dụng sẽ lỗi khi khởi động.

Có hai hướng:

1. Giữ runtime Java 17 và cấu hình compiler --release 17.
2. Nâng runtime image lên Java 24 hoặc release tương ứng với class/dependency.

Ví dụ cùng target Java 17:

~~~dockerfile
FROM eclipse-temurin:24-jdk AS build
WORKDIR /app
COPY . .
RUN ./mvnw -B -ntp -Dmaven.compiler.release=17 clean package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Kiểm tra image runtime sau khi build:

~~~bash
docker run --rm your-app-image java --version
~~~

Không dựa vào JDK cài trên host. JVM bên trong container là runtime thực sự của ứng dụng.

## 18. Dependency và plugin phải cùng tương thích

Một ứng dụng target Java 17 vẫn có thể lỗi nếu dependency được build cho Java 21 hoặc cao hơn. Việc đặt release trong POM/build.gradle chỉ kiểm soát code do compiler task của project biên dịch; nó không tự hạ bytecode của dependency đã tải.

Các bước xử lý:

1. Xác định class đầu tiên trong UnsupportedClassVersionError.
2. Tìm JAR hoặc plugin chứa class đó.
3. Xem version đang được resolve bằng dependency tree/insight.
4. Kiểm tra Java baseline mà nhà phát hành thư viện công bố.
5. Nâng runtime hoặc hạ dependency về bản hỗ trợ baseline.
6. Rebuild và chạy test trên runtime thấp nhất được hỗ trợ.

Với Maven plugin hoặc annotation processor, kiểm tra JDK chạy Maven và compatibility của chính plugin. Với Gradle plugin, kiểm tra Gradle JVM và yêu cầu Java của plugin.

Không cố khắc phục bằng cách thêm dependency khác vào classpath nếu class đã có nhưng bytecode quá mới.

## 19. Preview feature và minor version 65535

Từ Java 12, class file dùng preview feature có minor version 65535. Ví dụ class preview của Java 26 có version 70.65535.

Để compile preview, cần bật preview ở compiler:

~~~bash
javac --enable-preview --release 26 -d out src/demo/PreviewDemo.java
~~~

Và bật preview ở runtime cùng release:

~~~bash
java --enable-preview -cp out demo.PreviewDemo
~~~

Preview class file gắn với đúng Java release đã tạo ra nó. Class preview Java 25 không thể chạy trên Java 26 chỉ bằng cách thêm --enable-preview; phải compile lại với release mới. Thiếu cờ preview ở runtime cũng có thể gây UnsupportedClassVersionError dù major version đúng.

Không dùng preview feature cho artifact cần tương thích rộng nếu chưa có kế hoạch build, test và deploy cùng release.

## 20. Multi-release JAR và class file theo nhiều Java release

Một multi-release JAR có thể chứa implementation khác nhau theo Java release:

~~~text
app.jar
  META-INF/MANIFEST.MF
  com/example/Parser.class
  META-INF/versions/17/com/example/Parser.class
  META-INF/versions/21/com/example/Parser.class
~~~

Manifest phải khai báo:

~~~text
Multi-Release: true
~~~

JVM chọn implementation phù hợp với release đang chạy. Entry gốc ở JAR vẫn phải hỗ trợ baseline thấp nhất mà sản phẩm tuyên bố; entry trong META-INF/versions/N chỉ được dùng trên runtime đủ mới.

Kiểm tra nội dung JAR:

~~~bash
jar --list --file app.jar
jar --describe-module --file app.jar
~~~

Khi tạo multi-release JAR, compile từng phần bằng release tương ứng và kiểm thử trên từng runtime. Đừng đặt class mới vào thư mục gốc rồi kỳ vọng Java cũ tự bỏ qua class đó.

## 21. Ví dụ Java 17+ để kiểm tra class version

Tạo file src/demo/VersionProbe.java:

~~~java
package demo;

public final class VersionProbe {
    public static void main(String[] args) {
        System.out.println("READY class version");
    }
}
~~~

Compile cho Java 17 bằng JDK mới:

~~~bash
javac --release 17 -d out src/demo/VersionProbe.java
~~~

Xem class file header:

~~~bash
javap -verbose -classpath out demo.VersionProbe
~~~

Kết quả quan trọng:

~~~text
minor version: 0
major version: 61
~~~

Chạy chương trình:

~~~bash
java -cp out demo.VersionProbe
~~~

Stdout chính xác:

~~~text
READY class version
~~~

Ví dụ này được kiểm thử bằng Azul JDK 24.0.2. javac 24 compile với --release 17 tạo major 61/minor 0; JVM 24 chạy class và in đúng output.

## 22. Tái hiện UnsupportedClassVersionError có kiểm soát

Có thể kiểm tra cách JVM từ chối class file mới hơn mà không cần cài JDK mới hơn bằng cách tạo một bản copy test và thay major version trong header. Đây là phép thử chẩn đoán, không phải cách sửa ứng dụng.

Trên Windows PowerShell, sau khi compile VersionProbe như phần trước:

~~~powershell
$bytes = [System.IO.File]::ReadAllBytes("out\demo\VersionProbe.class")
$bytes[4] = 0
$bytes[5] = 0
$bytes[6] = 0
$bytes[7] = 69

New-Item -ItemType Directory -Force -Path "out-new\demo" | Out-Null
[System.IO.File]::WriteAllBytes("out-new\demo\VersionProbe.class", $bytes)

java -cp out-new demo.VersionProbe
~~~

Hai byte tại vị trí 6 và 7 là major version theo big-endian. Giá trị 69 mô phỏng class file Java 25. JDK 24 chỉ hỗ trợ đến major 68, vì vậy phép thử trả lỗi tương tự:

~~~text
java.lang.UnsupportedClassVersionError:
  demo/VersionProbe has been compiled by a more recent version of the Java Runtime
  (class file version 69.0),
  this version of the Java Runtime only recognizes class file versions up to 68.0
~~~

Trong kiểm thử, class gốc major 61 chạy thành công; bản copy đổi header sang major 69 bị JVM 24 từ chối với exit code 1. Không sửa class file production bằng cách đổi byte header: major version mới có thể đi kèm bytecode, constant-pool entry hoặc cấu trúc mà JVM cũ không hiểu.

## 23. Các lỗi dễ nhầm với UnsupportedClassVersionError

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| UnsupportedClassVersionError | JVM không hỗ trợ major/minor của class file |
| ClassNotFoundException | Không tìm thấy class khi code yêu cầu load bằng tên |
| NoClassDefFoundError | Class cần thiết không có lúc runtime hoặc khởi tạo class trước đó thất bại |
| NoSuchMethodError | Class được load nhưng runtime không có method mà bytecode đã liên kết |
| NoSuchFieldError | Field được tham chiếu không tồn tại trong class runtime |
| UnsupportedClassVersionError do preview | Class dùng preview version/flag không phù hợp |

Không dùng cùng một cách sửa cho tất cả các lỗi linkage. Nếu class file đã load thành công nhưng thiếu method/API, đó thường là vấn đề dependency/API compatibility thay vì major version.

## 24. Quy trình xử lý sự cố theo thứ tự

Khi gặp lỗi, làm theo trình tự:

1. Sao chép đầy đủ UnsupportedClassVersionError và ghi lại tên class.
2. Đọc class file version yêu cầu và version tối đa của runtime.
3. Chạy java --version từ đúng shell/service/container đang lỗi.
4. Kiểm tra java.home, JAVA_HOME và đường dẫn executable.
5. Dùng javap -verbose để kiểm tra class đầu ra của project.
6. Tìm JAR/plugin chứa class bị lỗi.
7. Xem dependency tree để xác định version được resolve.
8. Quyết định nâng runtime hay hạ compile target/dependency.
9. Cấu hình --release trong javac, Maven hoặc Gradle.
10. Kiểm thử clean build và chạy trên runtime thấp nhất được hỗ trợ.
11. Kiểm tra lại IDE, daemon, CI runner và container production.
12. Ghi rõ Java baseline vào README, build config và release metadata.

Không chỉ xóa thư mục target/build hoặc cache rồi chạy lại nếu chưa sửa version mismatch. Clean build hữu ích để loại class cũ, nhưng không làm runtime cũ hiểu bytecode mới.

## 25. Checklist phòng ngừa

- [ ] Xác định Java runtime thấp nhất mà sản phẩm hỗ trợ.
- [ ] Pin Java release target bằng javac --release, Maven maven.compiler.release hoặc Gradle options.release.
- [ ] Chọn Java Toolchain cho compiler và test task.
- [ ] Đảm bảo dependency trực tiếp và bắc cầu hỗ trợ cùng baseline.
- [ ] Kiểm tra JDK chạy Maven/Gradle và JDK toolchain dùng để compile.
- [ ] Cấu hình IDE project SDK, build JVM và Run Configuration nhất quán.
- [ ] Dùng runtime image tương thích với class file trong Docker/production.
- [ ] Test artifact trên đúng runtime thấp nhất, không chỉ JDK mới nhất.
- [ ] Kiểm tra preview feature và minor version nếu có dùng --enable-preview.
- [ ] Kiểm tra multi-release JAR trên từng Java release được hỗ trợ.
- [ ] Ghi Java baseline trong tài liệu cài đặt và pipeline release.
- [ ] Cập nhật runtime có kiểm thử khi thư viện hoặc framework tăng yêu cầu Java.

## 26. Tài liệu tham khảo

- [Java Virtual Machine Specification 26 — Introduction](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html): bảng đối chiếu Java release và class file major version, bao gồm Java 26 major 70.
- [Java Virtual Machine Specification 26 — Class File Format](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-4.html): cấu trúc header, major/minor version và quy tắc preview class file.
- [Oracle JDK 24 — javac command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html): --release, --source, --target và compile cho release cũ.
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): cấu hình maven.compiler.release và giới hạn của source/target.
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): ví dụ cấu hình release trong Maven Compiler Plugin.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): chọn JDK cho compile/test/Javadoc, kết hợp toolchain và release, xem toolchain được phát hiện.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): Java toolchain, options.release và source/target compatibility.
- [Oracle JDK 26 — ClassFile API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFileVersion.html): mô hình major/minor và minor version 65535 cho preview.

UnsupportedClassVersionError gần như luôn dẫn về một câu hỏi: class file được tạo cho Java release nào, và JVM thực sự đang chạy hỗ trợ đến đâu? Đọc class version, xác định runtime thực tế rồi đồng bộ release target, dependency và deployment runtime để sửa đúng nguyên nhân.
