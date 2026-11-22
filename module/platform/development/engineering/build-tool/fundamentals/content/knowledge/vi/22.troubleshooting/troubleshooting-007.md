# UnsupportedClassVersionError và chênh lệch phiên bản Java

`UnsupportedClassVersionError` là lỗi JVM phát sinh khi Java Virtual Machine cố nạp một class có định dạng bytecode mà phiên bản JVM hiện tại không hỗ trợ. Nguyên nhân thường gặp là class được biên dịch bằng JDK mới hơn runtime đang chạy ứng dụng. Tuy nhiên, class gây lỗi không nhất thiết thuộc source code của ứng dụng: nó có thể đến từ một dependency, plugin Gradle, thư viện framework, test engine hoặc class được nạp động.

Ví dụ, một ứng dụng được biên dịch thành bytecode Java 17 nhưng lại chạy trên Java 11. JVM Java 11 chỉ hiểu class-file format đến major version 55, trong khi Java 17 tạo major version 61. Khi JVM cố nạp class đó, nó có thể ném:

~~~text
java.lang.UnsupportedClassVersionError:
  com/example/orders/OrderService has been compiled by a more recent
  version of the Java Runtime (class file version 61.0),
  this version of the Java Runtime only recognizes class file versions
  up to 55.0
~~~

Cách xử lý đúng là xác định **class nào đang bị nạp, JVM nào đang nạp class đó, bytecode yêu cầu phiên bản nào**, rồi đồng bộ compiler, dependency, Gradle runtime và môi trường chạy. Chỉ nhìn vào kết quả `java -version` trong terminal developer là chưa đủ, vì Gradle daemon, Java toolchain, test worker và server có thể đang dùng các JDK khác nhau.

## 1. UnsupportedClassVersionError là gì?

Java source được compiler chuyển thành bytecode trong file `.class`. Mỗi class file có cấu trúc định dạng và một cặp số phiên bản:

- **Major version:** phiên bản định dạng class file chính.
- **Minor version:** phiên bản phụ, có ý nghĩa đặc biệt với một số định dạng cũ và bytecode dùng preview features.

JVM kiểm tra class-file version khi nạp class. Nếu major version cao hơn mức JVM hỗ trợ, JVM không thể diễn giải bytecode đó và ném `UnsupportedClassVersionError`.

Lỗi này là một loại `LinkageError`, thuộc nhóm lỗi liên quan đến liên kết/nạp class. Nó có thể xuất hiện khi ứng dụng khởi động, khi một class được dùng lần đầu, trong lúc chạy test, hoặc khi framework/plugin nạp class theo cơ chế reflection hay classloader riêng.

### 1.1. Vì sao lỗi có thể xuất hiện dù compile thành công?

Compile và runtime là hai giai đoạn có thể dùng hai Java installation khác nhau:

~~~text
Source code
    |
    v
JDK dùng để compile
    |
    v
.class files / dependency JAR
    |
    v
JVM dùng để chạy
    |
    +---- Hỗ trợ class-file version? ---- Có --> Nạp class
                                   |
                                   +---- Không --> UnsupportedClassVersionError
~~~

Ví dụ:

1. Developer dùng JDK 21 để compile.
2. Gradle tạo class file major version 65.
3. WAR/JAR được đưa lên server đang chạy Java 17.
4. Java 17 chỉ hỗ trợ major version đến 61.
5. Server ném `UnsupportedClassVersionError` khi nạp class cần major 65.

Build có thể hoàn toàn thành công vì compiler mới hiểu source và dependency. Lỗi chỉ xuất hiện khi runtime cũ hơn cố nạp bytecode.

### 1.2. Class gây lỗi không nhất thiết là class của ứng dụng

Một ứng dụng có thể compile source của mình bằng Java 17, nhưng một dependency được nâng lên version chỉ hỗ trợ Java 21. Hoặc Gradle daemon chạy bằng Java 11 nhưng một plugin được biên dịch bằng Java 17.

Các nguồn class thường gặp:

- Class do project compile.
- JAR trong runtime classpath.
- Plugin Gradle và plugin dependency.
- Build logic trong `buildSrc` hoặc included build.
- Test framework, test engine và test fixture.
- Code được sinh ra bởi annotation processor hoặc generator.
- Thư viện được container/server cung cấp.
- Class nạp từ plugin system, scripting engine hoặc classloader tùy chỉnh.

Do đó, cần đọc tên class trong thông báo lỗi và stack trace để xác định thành phần gây ra lỗi. Không nên mặc định rằng toàn bộ project cần đổi Java chỉ vì một dependency yêu cầu runtime mới hơn.

## 2. Đọc class-file major/minor version

Thông báo lỗi thường cung cấp hai con số, ví dụ `61.0` và `55.0`. Số đầu tiên là phiên bản class file của class đang được nạp; số thứ hai là mức cao nhất mà JVM hiện tại nhận biết.

### 2.1. Bảng major version thường gặp

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| Java 27 | 71 |

Từ Java 1.2 trở đi, major version tăng đều theo release. Có thể nhớ quy tắc thực dụng: **major version = Java release + 44**. Ví dụ Java 17 có major 61; Java 21 có major 65.

Bảng giúp suy ra mức Java tối thiểu cần có để nạp class. Nếu thông báo cho biết class file version 65.0 và runtime chỉ nhận đến 61.0, class được tạo cho Java 21 trong khi runtime là Java 17.

### 2.2. Minor version và preview bytecode

Với class file thông thường, minor version thường là 0. Bytecode được biên dịch khi bật preview features có thể dùng minor version 65535.

Ví dụ một class được biên dịch bằng preview features của Java 21 có thể có version `65.65535`. Để chạy class này, JVM cần:

- Cùng Java release đã tạo preview bytecode.
- Cờ `--enable-preview` khi chạy.
- Compiler cũng phải được gọi với `--enable-preview` khi biên dịch.

Preview bytecode của Java 21 không được xem như bytecode preview có thể chạy tự do trên Java 22. Preview features gắn với release cụ thể. Một class có major version được runtime hỗ trợ vẫn có thể bị từ chối nếu minor version biểu thị preview nhưng JVM không được bật chế độ preview hoặc đang dùng release khác.

### 2.3. Phân biệt với các lỗi Java khác

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| `UnsupportedClassVersionError` | JVM không hỗ trợ class-file version của class |
| `ClassNotFoundException` | Classloader không tìm thấy class được yêu cầu theo cơ chế load thông thường |
| `NoClassDefFoundError` | Class cần thiết không có khi JVM liên kết/nạp, hoặc class trước đó khởi tạo/nạp thất bại |
| `NoSuchMethodError` | Class được nạp nhưng không có method mà code đã biên dịch mong đợi |
| `NoSuchFieldError` | Class được nạp nhưng không có field mà code mong đợi |
| `IncompatibleClassChangeError` | Cấu trúc class thay đổi không tương thích với bytecode đang liên kết |
| `UnsupportedOperationException` | Một operation được gọi nhưng implementation không hỗ trợ; không phải lỗi class-file version |

Nếu log báo `ClassNotFoundException` thì nâng JDK không nhất thiết giải quyết được vấn đề. Nếu báo `NoSuchMethodError`, cần điều tra xung đột version API/library. Hãy xác định chính xác exception đầu tiên và class được nhắc tới.

## 3. Java version trong một Gradle build có nhiều lớp

Một nguyên nhân phổ biến là xem Java version như một giá trị duy nhất. Trên thực tế, Gradle build có thể liên quan tới nhiều JVM:

1. **JVM khởi chạy Gradle client/wrapper:** Java dùng để chạy lệnh Gradle.
2. **Gradle daemon JVM:** JVM thực thi Gradle, plugin và build logic.
3. **Java compiler toolchain:** JDK dùng cho task compile.
4. **Test launcher:** JVM chạy test worker hoặc test suite.
5. **Application runtime:** JVM chạy ứng dụng đóng gói.
6. **Deployment runtime:** JDK/JRE trên server, container hoặc máy production.

Các lớp này có thể cùng phiên bản hoặc khác nhau theo chủ đích. Chúng phải tương thích với nhau theo yêu cầu của Gradle, plugin, compiler và bytecode được tạo.

### 3.1. JVM chạy Gradle không nhất thiết là JDK biên dịch source

Gradle daemon có thể chạy bằng JDK 17, trong khi Java toolchain chọn JDK 21 để compile và test. Đây là cấu hình hợp lệ nếu phiên bản Gradle hỗ trợ chạy trên JDK 17 và task/toolchain được cấu hình đúng.

Ngược lại, việc máy có JDK 21 không bảo đảm Gradle daemon dùng JDK 21. Biến môi trường, IDE, daemon JVM criteria hoặc cấu hình Gradle có thể chọn một JDK khác.

### 3.2. Plugin Gradle chạy trên JVM của Gradle

Plugin Gradle và build logic được nạp trong môi trường Gradle. Nếu plugin được biên dịch với bytecode Java 17 nhưng Gradle daemon chạy trên Java 11, lỗi có thể xuất hiện ngay khi Gradle nạp plugin, trước cả khi task compileJava của ứng dụng chạy.

Trong trường hợp này, thay target version của source application không sửa được lỗi. Cần chọn Gradle runtime đủ mới hoặc dùng phiên bản plugin/build logic tương thích với JDK đang chạy Gradle.

### 3.3. Test có thể chạy trên JVM khác compiler

Java toolchain có thể ảnh hưởng cả compiler và test launcher. Tuy vậy, một build cũng có thể cấu hình task test riêng, fork options hoặc launcher khác. Nếu compile pass nhưng test fail với UnsupportedClassVersionError, hãy kiểm tra JVM thực sự chạy test worker.

Tương tự, test pass trên developer machine không chứng minh ứng dụng chạy được trên production runtime. Hãy kiểm thử với Java version của môi trường triển khai mục tiêu.

## 4. Xác định JVM thực sự đang chạy

Trước khi sửa build, hãy thu thập thông tin từ đúng môi trường gây lỗi. Lệnh chạy trên terminal developer, IDE, Gradle daemon và production server có thể cho kết quả khác nhau.

### 4.1. Kiểm tra Java trong terminal

Trên macOS/Linux:

~~~bash
java -version
javac -version
which java
which javac
echo "$JAVA_HOME"
~~~

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

`java -version` cho biết JVM được tìm thấy qua PATH. `javac -version` cho biết compiler được tìm thấy qua PATH. Hai lệnh có thể trỏ tới hai installation khác nhau nếu PATH được cấu hình không nhất quán.

Nếu `javac` không được tìm thấy nhưng `java` có, máy có thể chỉ có runtime hoặc PATH chưa trỏ tới JDK. Một build compile Java cần compiler phù hợp, thường được cung cấp bởi JDK/toolchain.

### 4.2. Kiểm tra JVM mà Gradle dùng

Chạy wrapper của chính project:

~~~bash
./gradlew --version
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
~~~

Output cho biết phiên bản Gradle và thông tin JVM mà Gradle invocation sử dụng. Với Gradle version mới, có thể thấy thông tin Launcher JVM và Daemon JVM riêng. Hãy đọc phần JVM/Java home thay vì suy luận từ lệnh `java -version`.

Có thể yêu cầu Gradle hiển thị toolchains được phát hiện:

~~~bash
./gradlew javaToolchains
~~~

Task này hữu ích khi Java plugin được áp dụng. Nó liệt kê các toolchain Gradle phát hiện được và thông tin JDK tương ứng. Nếu task không có trong build hiện tại, kiểm tra plugin Java và Gradle version.

### 4.3. Kiểm tra Java runtime bên trong ứng dụng

Có thể log thông tin JVM khi ứng dụng khởi động:

~~~java
System.out.println("java.version = " + System.getProperty("java.version"));
System.out.println("java.runtime.version = " + System.getProperty("java.runtime.version"));
System.out.println("java.home = " + System.getProperty("java.home"));
System.out.println("java.vendor = " + System.getProperty("java.vendor"));
~~~

Giá trị này phản ánh JVM đang chạy chính ứng dụng. Đây là thông tin hữu ích khi server, service manager hoặc container khởi chạy process bằng một Java installation khác với terminal quản trị.

Nếu có quyền truy cập process đang chạy, JDK cung cấp `jcmd` để kiểm tra:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.system_properties
~~~

Lệnh cần chạy bằng user có quyền attach tới process. Nó giúp xác định phiên bản JVM và các system properties của đúng process đang lỗi.

### 4.4. Kiểm tra IDE và service launcher

IDE có thể có cấu hình Gradle JVM riêng. Ví dụ, IDE có thể dùng JDK 17 để chạy Gradle sync trong khi terminal dùng JDK 21. Tương tự, Windows service, systemd unit, Docker image hoặc application server có thể trỏ JAVA_HOME riêng.

Hãy kiểm tra nơi process được khởi chạy:

- Gradle JVM setting của IDE.
- Gradle daemon JVM criteria hoặc cấu hình daemon.
- Biến JAVA_HOME trong shell/service/CI.
- Đường dẫn Java trong startup script của Tomcat/application server.
- Dockerfile, base image và entrypoint.
- Cấu hình runner/agent của CI.

Không kết luận production runtime chỉ từ Java trên máy cá nhân.

## 5. Kiểm tra class hoặc dependency gây lỗi

Thông báo UnsupportedClassVersionError thường nêu tên class. Tên đó là điểm bắt đầu để tìm JAR chứa class.

Ví dụ:

~~~text
com/example/vendor/Parser
~~~

Nếu class thuộc package của một thư viện bên thứ ba, hãy xác định version JAR đang được nạp. Nếu class thuộc plugin, kiểm tra plugin artifact và JVM của Gradle daemon. Nếu class thuộc ứng dụng, kiểm tra compiler output và runtime nơi triển khai.

### 5.1. Đọc major version bằng javap

Với class file độc lập:

~~~bash
javap -verbose path/to/Parser.class
~~~

Trong output, tìm dòng:

~~~text
major version: 65
minor version: 0
~~~

Nếu class nằm trong JAR:

~~~bash
javap -verbose -classpath path/to/library.jar com.example.vendor.Parser
~~~

Lệnh này hiển thị metadata của class được chỉ định. Nếu package/class name không đúng hoặc class không nằm trong JAR đó, javap sẽ báo không tìm thấy class.

Trên Windows, có thể lọc output bằng:

~~~powershell
javap -verbose -classpath .\libs\library.jar com.example.vendor.Parser | Select-String "major version|minor version"
~~~

Trên Unix-like systems:

~~~bash
javap -verbose -classpath libs/library.jar com.example.vendor.Parser | grep -E 'major version|minor version'
~~~

### 5.2. Xác định JAR nào được resolve

Gradle có thể resolve nhiều version của cùng một module theo dependency graph. Hãy xem dependency runtime thực tế thay vì chỉ đọc khai báo trong build script:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để xem lý do một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency parser-library --configuration runtimeClasspath
~~~

Thay `parser-library` bằng tên module cần điều tra. Với plugin Gradle, build logic hoặc buildscript classpath, cần kiểm tra đúng configuration/plugin resolution liên quan; `runtimeClasspath` của ứng dụng không chứa mọi plugin Gradle.

### 5.3. Kiểm tra class nằm trong artifact nào

Có thể liệt kê nội dung JAR:

~~~bash
jar tf path/to/library.jar
~~~

Tìm đường dẫn class tương ứng. Nếu class có mặt trong nhiều JAR, classloader có thể nạp bản khác với bản bạn đang kiểm tra. Cần xác định classpath/module path thực tế và quy tắc classloader của runtime.

Với container/application server, một thư viện có thể đến từ:

- `WEB-INF/lib` của WAR.
- Thư mục shared libraries của server.
- Thư viện platform/server modules.
- Một classloader của application hoặc framework.

Kiểm tra đúng nguồn class được nạp, không chỉ đúng JAR đang có trong thư mục source repository.

### 5.4. Multi-release JAR

Một số JAR là multi-release JAR. Chúng có thể chứa class nền tảng và các phiên bản class dành cho những Java release khác nhau dưới thư mục `META-INF/versions/N`. Manifest cần khai báo `Multi-Release: true` để JVM xử lý các versioned entries theo cơ chế này.

JVM chọn phiên bản class phù hợp với release mà nó đang chạy. Khi điều tra lỗi, hãy kiểm tra cả base entry và versioned entry. Một JAR multi-release được đóng gói đúng có thể hỗ trợ nhiều Java release; một artifact được đóng gói sai hoặc thiếu class base tương thích vẫn có thể gây lỗi trên runtime cũ.

Không nên giả định rằng mọi class trong một JAR đều có cùng major version.

## 6. Các nguồn gây chênh lệch phiên bản Java

### 6.1. Source được compile bằng JDK mới, runtime quá cũ

Đây là trường hợp trực tiếp nhất:

- Compiler JDK 21 tạo bytecode major 65.
- Production chạy Java 17, chỉ hỗ trợ major 61.
- JVM từ chối nạp class.

Có hai hướng xử lý: nâng runtime lên Java 21, hoặc compile target thấp hơn nếu source và dependency có thể chạy trên Java 17.

### 6.2. Dependency yêu cầu Java mới hơn ứng dụng

Project có thể target Java 17 nhưng dependency vừa nâng lên version chỉ hỗ trợ Java 21. Compiler hoặc runtime sẽ gặp lỗi khi nạp class từ dependency.

Ví dụ:

~~~groovy
dependencies {
    implementation 'com.example:parser-library:5.0.0'
}
~~~

Nếu version 5.0.0 yêu cầu Java 21, việc app source target 17 không biến dependency đó thành Java 17-compatible. Cần chọn dependency version hỗ trợ Java 17 hoặc nâng runtime của ứng dụng.

### 6.3. Gradle daemon quá cũ so với plugin

Một plugin Gradle được biên dịch bằng Java mới hơn có thể không được nạp bởi daemon JVM cũ. Lỗi xảy ra trong giai đoạn cấu hình build, trước task compile.

Dấu hiệu thường gặp:

- Stack trace nhắc class của plugin.
- Lỗi xuất hiện khi resolve/apply plugin.
- Task của project chưa bắt đầu.
- Thay đổi JavaCompile target không có tác dụng.

Cách sửa là dùng JDK phù hợp để chạy Gradle và phiên bản Gradle tương thích với JDK đó, hoặc dùng plugin version có bytecode/runtime requirement thấp hơn.

### 6.4. Gradle version không hỗ trợ JDK đang dùng

Gradle itself có yêu cầu Java version để chạy. Một JDK mới có thể không được phiên bản Gradle cũ hỗ trợ làm runtime. Lỗi trong trường hợp này có thể khác UnsupportedClassVersionError, chẳng hạn Gradle từ chối khởi động hoặc plugin/Gradle API không tương thích.

Hãy kiểm tra bảng tương thích chính thức của đúng Gradle release cho hai câu hỏi riêng:

- Gradle release nào có thể chạy trên JDK này?
- Gradle release đó hỗ trợ compile/test bằng toolchain Java release nào?

Không được suy luận rằng Gradle compile được Java version nào thì chính Gradle cũng có thể chạy trên Java version đó.

### 6.5. Test engine hoặc plugin chạy bằng JVM khác

Test có thể được fork thành process riêng. Một test task có thể dùng launcher/toolchain khác với Gradle daemon. Annotation processor, code generator hoặc compiler plugin cũng có thể có runtime requirement riêng.

Nếu lỗi chỉ xảy ra ở `test`, hãy kiểm tra test launcher và test worker. Nếu lỗi xuất hiện khi chạy `compileJava` hoặc configuration, hãy kiểm tra compiler toolchain và plugin runtime tương ứng.

### 6.6. Server hoặc container dùng Java khác

Ứng dụng chạy local trên Java 21 nhưng server chạy Java 17 là tình huống phổ biến. Docker image cũng có thể dùng base image JRE khác với JDK của build stage.

Hãy kiểm tra image/runtime cuối cùng, không chỉ builder image. Multi-stage Docker build có thể compile bằng JDK mới nhưng copy artifact sang runtime image cũ.

Ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
# compile application

FROM eclipse-temurin:17-jre
# run application compiled for Java 21 -> incompatible
~~~

Nếu build tạo bytecode Java 21, runtime image phải hỗ trợ Java 21, hoặc build phải tạo bytecode tương thích với Java 17 và chỉ dùng API có trong Java 17.


## 6. Sửa lỗi bằng cách đồng bộ compiler và runtime

Sau khi biết class yêu cầu Java release nào và runtime thực tế đang chạy release nào, hãy chọn một baseline Java rõ ràng cho ứng dụng. Không nên chỉ đổi một setting rồi hy vọng mọi process dùng cùng JDK.

Có hai chiến lược chính:

1. **Nâng runtime:** dùng JDK/JRE đủ mới để chạy bytecode và dependency hiện tại.
2. **Hạ bytecode mục tiêu:** compile source xuống release thấp hơn, đồng thời chỉ sử dụng API và dependency tương thích với release đó.

### 6.1. Chọn Java toolchain cho Gradle

Với Java plugin, có thể chọn JDK dùng cho compile/test qua toolchain:

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

Toolchain yêu cầu Gradle tìm JDK 17 phù hợp. Nếu máy chưa có toolchain đó, Gradle có thể dùng toolchain được cài sẵn hoặc provision theo cấu hình/resolver mà build cho phép.

Java toolchain giúp build có thể dùng cùng compiler/test launcher trên các máy khác nhau. Tuy nhiên, nó **không tự đổi JVM chạy Gradle daemon**. Gradle vẫn cần một JVM đáp ứng yêu cầu của Gradle release và plugin.

### 6.2. Dùng `options.release` để giới hạn API và bytecode

Toolchain xác định JDK compiler. Thuộc tính `options.release` yêu cầu javac biên dịch theo Java platform release cụ thể.

Ví dụ:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Nếu compiler chạy bằng JDK 21 nhưng `options.release` là 17, javac tạo bytecode tương thích Java 17 và giới hạn API Java platform ở mức Java 17. Điều này hữu ích khi build bằng JDK mới nhưng sản phẩm phải chạy trên runtime cũ hơn.

Cần nhớ rằng `--release` chỉ kiểm soát Java platform API. Nó không làm một dependency bên ngoài vốn yêu cầu Java 21 trở nên tương thích Java 17. Dependency vẫn phải có bytecode và API tương thích với baseline đã chọn.

### 6.3. sourceCompatibility và targetCompatibility khác --release

Các thuộc tính source/target thường gặp:

~~~groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

- `sourceCompatibility` xác định mức cú pháp Java mà compiler chấp nhận.
- `targetCompatibility` xác định mức bytecode target.
- `options.release` kết hợp giới hạn source language, target bytecode và Java platform API cho release được chọn.

Chỉ đặt source/target không bảo đảm code không gọi API mới hơn target. Ví dụ compiler JDK 21 có thể compile code gọi một API chỉ tồn tại từ Java 21 nếu chỉ đặt target bytecode 17; class tạo ra có thể có major 61 nhưng vẫn gọi API runtime Java 17 không có. Khi chạy, lỗi có thể là `NoSuchMethodError` hoặc `NoClassDefFoundError` thay vì UnsupportedClassVersionError.

Nếu cần build trên JDK mới nhưng chạy trên release cũ, ưu tiên `options.release` và kiểm thử trên runtime mục tiêu.

### 6.4. Đặt Gradle daemon JVM riêng khi cần

Có thể chọn JVM chạy Gradle daemon qua thuộc tính:

~~~properties
org.gradle.java.home=/path/to/jdk-17
~~~

Trên Windows, giá trị là đường dẫn tới JDK đã cài, ví dụ:

~~~properties
org.gradle.java.home=C:/Program Files/Java/jdk-17
~~~

Thuộc tính này chọn Java home cho Gradle build process/daemon theo cơ chế của Gradle. Nó không thay thế Java toolchain cho task compile/test và không bảo đảm server runtime dùng cùng JDK.

Có thể dùng `JAVA_HOME` để chọn Java khi khởi chạy Gradle từ shell. Tuy nhiên, IDE, daemon JVM criteria và cấu hình CI có thể chọn JVM khác. Sau khi đổi cấu hình, kiểm tra lại bằng `./gradlew --version` và log Gradle.

### 6.5. Cấu hình test launcher khi cần

Java plugin thường gắn test task với Java toolchain của project. Nếu build có nhiều test task hoặc cần chạy test trên runtime khác, có thể cấu hình launcher rõ ràng:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Nếu test chạy trên Java 17 nhưng Gradle daemon chạy Java 21, đó có thể là cấu hình hợp lệ. Điều quan trọng là test runtime phải hỗ trợ bytecode của test classes, application classes và test dependencies.

### 6.6. Ví dụ build JDK 21 nhưng phát hành cho Java 17

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
}
~~~

Trong ví dụ này:

- Compiler JDK là Java 21.
- Java source/platform target là Java 17.
- Bytecode được tạo cho Java 17.
- Ứng dụng vẫn cần dependency tương thích Java 17.
- Runtime mục tiêu có thể là Java 17 trở lên.

Đây là một cách xây dựng artifact có baseline thấp hơn compiler JDK. Không nên nhầm nó với việc chạy application bằng Java 21; compile toolchain và application runtime là hai bước khác nhau.

## 7. Đồng bộ Java version trong toàn bộ Gradle build

Một cấu hình Java rõ ràng nên xác định các lớp runtime/compile sau:

| Thành phần | Câu hỏi cần trả lời | Cách kiểm tra/cấu hình |
|---|---|---|
| Gradle wrapper/runtime | JDK nào được phép chạy Gradle release này? | `./gradlew --version`, Gradle compatibility matrix |
| Gradle daemon | Plugin và build logic được nạp bằng JVM nào? | Daemon JVM info, `org.gradle.java.home`, daemon criteria |
| Java compiler | JDK nào compile source? | Java toolchain |
| Java target/API | Bytecode và platform API target nào? | `options.release` |
| Test JVM | Test worker chạy bằng Java nào? | Test task `javaLauncher` |
| Application runtime | Ứng dụng yêu cầu Java tối thiểu nào? | Deployment image/server config |
| Plugin/processor | Plugin hoặc processor cần Java nào? | Plugin docs, stack trace và toolchain/runtime của build |

### 7.1. Gradle version phải hỗ trợ JVM chạy Gradle

Mỗi Gradle release có giới hạn Java version được hỗ trợ để chạy Gradle. JDK mới có thể không được phiên bản Gradle cũ hỗ trợ làm runtime. Lỗi trong trường hợp này có thể khác UnsupportedClassVersionError, chẳng hạn Gradle từ chối khởi động hoặc plugin/Gradle API không tương thích.

Kiểm tra tài liệu tương thích của đúng Gradle version đang dùng, đặc biệt là phần Java runtime compatibility. Gradle Wrapper xác định Gradle distribution, còn JDK được chọn để chạy distribution là một cấu hình riêng.

Không nên chỉ cập nhật JDK trên CI mà giữ nguyên Gradle wrapper và plugin cũ nếu chưa kiểm tra ma trận tương thích.

### 7.2. Plugin và build logic có baseline riêng

Các plugin được nạp trước khi JavaCompile task của project chạy. Vì vậy, `options.release` của ứng dụng không giới hạn bytecode của plugin.

Nếu plugin yêu cầu Java 17, Gradle daemon phải chạy trên JVM có thể nạp plugin đó. Nếu plugin yêu cầu Gradle API mới hơn, chỉ nâng JDK cũng chưa đủ; cần chọn plugin version và Gradle wrapper tương thích với nhau.

Build logic trong `buildSrc` hoặc included build cũng cần được compile và chạy với baseline phù hợp. Khi gặp lỗi ở giai đoạn configuration, hãy điều tra các thành phần này trước khi sửa source target của ứng dụng.

### 7.3. Annotation processor và code generator

Annotation processor thường chạy trong compiler process. Processor hoặc generator có thể yêu cầu Java version cao hơn application target.

Ví dụ, project target Java 17 nhưng processor chỉ chạy trên JDK 21. Có thể dùng compiler toolchain JDK 21 và `options.release = 17` nếu processor hỗ trợ mô hình này. Kết quả generated code vẫn phải tương thích Java 17 và không được gọi API mới hơn.

Nếu processor sinh bytecode trực tiếp hoặc tạo class bằng thư viện bytecode generation, cần kiểm tra version class file mà nó tạo ra.

### 7.4. Kotlin và các JVM language khác

Nếu build có Kotlin, Scala hoặc language plugin khác, Java toolchain không tự động bảo đảm mọi compiler đều tạo cùng target bytecode. Cần cấu hình JVM target tương ứng theo plugin và phiên bản compiler đang dùng.

Đối với Kotlin, kiểm tra `jvmTarget` và Kotlin toolchain/compiler options. Với Scala hoặc code generator, kiểm tra target bytecode và yêu cầu JDK riêng. Sau đó kiểm tra artifact cuối cùng trên runtime mục tiêu.

## 8. Preview features và `--enable-preview`

Nếu thông báo lỗi cho biết minor version 65535 hoặc stack trace đề cập preview features, cần kiểm tra compiler và runtime có cùng Java release hay không.

Ví dụ compile với preview features trên Java 21:

~~~bash
javac --release 21 --enable-preview -d out src/main/java/com/example/Main.java
~~~

Chạy bằng Java 21 với preview enabled:

~~~bash
java --enable-preview -cp out com.example.Main
~~~

Với Gradle, có thể cấu hình compiler arguments và test JVM arguments, nhưng phải dùng cùng release:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.compilerArgs += '--enable-preview'
}

tasks.withType(Test).configureEach {
    jvmArgs += '--enable-preview'
}
~~~

Ứng dụng chạy trực tiếp cũng cần cờ `--enable-preview`. Nếu triển khai vào container hoặc server, phải cấu hình JVM startup options của chính process server. Chỉ bật preview ở compile hoặc test không đủ để bật preview trong production.

Preview features không phải lựa chọn tốt cho artifact cần chạy trên nhiều Java release. Nếu không cần preview, bỏ `--enable-preview` và compile bằng API ổn định.

## 9. Xử lý lỗi trong môi trường Servlet/container hoặc Docker

Nếu ứng dụng chạy trong Tomcat, Jetty hoặc application server, runtime Java do process server sử dụng quyết định khả năng nạp class. JDK của Gradle build không tự thay đổi JDK của server.

### 9.1. Kiểm tra runtime của server

Với server chạy trực tiếp trên máy, kiểm tra startup script, service definition và log khởi động để xác định đường dẫn Java. Nếu có thể, log `java.version` và `java.home` từ ứng dụng đang chạy.

Với Docker, kiểm tra image cuối cùng:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
# Gradle build tạo artifact

FROM eclipse-temurin:17-jre
# Runtime này chỉ hỗ trợ bytecode tối đa Java 17
COPY --from=build /workspace/build/libs/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu build tạo class file Java 21, runtime Java 17 trong ví dụ sẽ không nạp được class đó. Có thể nâng runtime image lên Java 21 hoặc cấu hình build tạo artifact tương thích Java 17 và xác nhận toàn bộ dependency cũng hỗ trợ Java 17.

### 9.2. Build image với một Java baseline thống nhất

Ví dụ dùng Java 17 ở cả build và runtime:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew clean build

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Cấu hình này giúp giảm khả năng chênh lệch giữa build JDK và runtime JRE, nhưng vẫn cần kiểm tra Gradle wrapper và plugin có chạy được trên JDK 17 hay không. Nếu muốn build bằng JDK 21 và target Java 17, phải cấu hình toolchain/release rõ ràng và kiểm tra dependency.

### 9.3. Servlet container và namespace không giải quyết class-file version

Chuyển từ `javax.servlet` sang `jakarta.servlet` là thay đổi namespace/API. Nó không tự hạ bytecode của ứng dụng hoặc dependency.

Tương tự, nâng Tomcat version có thể kéo theo thay đổi Servlet API, namespace và Java runtime requirement. Hãy kiểm tra riêng:

- Java version mà Tomcat/container cần để chạy.
- Servlet API namespace/version mà container cung cấp.
- Java bytecode version của WAR và mọi JAR bên trong.
- Java version tối thiểu của framework/dependency.

Một WAR có thể dùng đúng Servlet namespace nhưng vẫn chứa class Java quá mới so với runtime server.

## 10. Quy trình chẩn đoán từng bước

Khi gặp `UnsupportedClassVersionError`, có thể điều tra theo thứ tự sau.

### Bước 1: Ghi nhận đầy đủ exception

Lưu nguyên thông báo lỗi, tên class, class-file version yêu cầu và version tối đa runtime hỗ trợ. Lấy stack trace để biết lỗi xuất hiện khi Gradle khởi động/configuration, compile source, chạy test, khởi động ứng dụng, nạp plugin hoặc deploy WAR.

### Bước 2: Xác định JVM gây lỗi

Chạy `./gradlew --version` nếu lỗi trong Gradle. Kiểm tra test launcher nếu lỗi trong test. Kiểm tra `java.home` hoặc process runtime nếu lỗi trong ứng dụng/server.

Không dùng kết quả của một process khác làm bằng chứng cho JVM gây lỗi.

### Bước 3: Giải mã class-file version

Đối chiếu major version với bảng Java release. Nếu cần, dùng `javap -verbose` để xác nhận major/minor của class trong JAR.

### Bước 4: Tìm artifact chứa class

Dựa vào package/class name, stack trace, classpath/module path và nội dung JAR. Với Gradle dependency, dùng `dependencies` và `dependencyInsight` trên configuration đúng. Với plugin, kiểm tra plugin artifact và build logic.

### Bước 5: Chọn baseline Java

Quyết định runtime tối thiểu mà ứng dụng phải hỗ trợ. Đây là quyết định sản phẩm/deployment, không nên chỉ dựa vào JDK đang cài trên developer machine.

### Bước 6: Đồng bộ compiler và dependency

Dùng toolchain để chọn JDK compile/test. Dùng `options.release` để giới hạn Java platform API và bytecode. Chọn dependency/plugin version hỗ trợ baseline. Kiểm tra annotation processor và các compiler plugin.

### Bước 7: Đồng bộ Gradle runtime

Kiểm tra Gradle wrapper, plugin compatibility và JVM chạy daemon. Nếu plugin bytecode quá mới, nâng daemon JVM hoặc dùng plugin version tương thích.

### Bước 8: Kiểm thử trên runtime mục tiêu

Chạy test và smoke test bằng cùng Java release với production. Với container, kiểm tra đúng image/server startup. Đừng chỉ xác nhận task build thành công.

### Bước 9: Kiểm tra artifact cuối cùng

Kiểm tra JAR/WAR thực tế được phát hành, các dependency đóng gói và class-file version của class nghi ngờ. Nếu artifact cũ còn sót, clean/rebuild có thể cần thiết sau khi sửa cấu hình, nhưng xóa cache không thể biến bytecode Java mới thành bytecode Java cũ.

## 11. Những cách sửa sai thường gặp

| Cách làm | Vì sao không giải quyết đúng |
|---|---|
| Chỉ chạy `java -version` trên terminal | Chưa chắc đó là JVM của Gradle daemon, test worker hoặc server |
| Chỉ đổi `sourceCompatibility` | Không nhất thiết giới hạn Java API; dependency mới vẫn có thể yêu cầu runtime cao hơn |
| Chỉ đổi `targetCompatibility` | Bytecode target thấp hơn không biến dependency bytecode mới thành cũ |
| Chỉ đổi `options.release` | Không ảnh hưởng bytecode của plugin Gradle hoặc dependency đã biên dịch |
| Chỉ nâng JDK cài trên máy | IDE, daemon, CI hoặc server có thể vẫn dùng JDK cũ |
| Chỉ nâng Gradle wrapper | Plugin/dependency/runtime vẫn có thể không tương thích |
| Hạ version class file bằng công cụ chỉnh byte | Có thể làm bytecode sai định dạng hoặc gọi API không tồn tại; không phải cách chuyển đổi an toàn |
| Xóa toàn bộ Gradle cache | Không làm class bytecode yêu cầu Java thấp hơn |
| Thêm `--add-opens` hoặc `--add-exports` | Các cờ này điều chỉnh truy cập module/reflection, không hỗ trợ class-file version mới |
| Đổi `javax` thành `jakarta` | Namespace API khác nhau, không thay đổi major version của class file |
| Chỉ test trên JDK mới nhất | Không chứng minh artifact chạy được trên Java baseline đã cam kết |

## 12. Checklist tránh tái diễn

Khi chuẩn bị build và phát hành ứng dụng Java, hãy ghi nhận rõ:

- [ ] Java baseline tối thiểu của ứng dụng là gì?
- [ ] Gradle wrapper version có hỗ trợ JVM chạy Gradle không?
- [ ] Gradle daemon đang dùng đúng JDK mong muốn không?
- [ ] Java toolchain cho compile/test đã được cấu hình chưa?
- [ ] `options.release` có khớp runtime baseline không?
- [ ] Dependency runtime có yêu cầu Java cao hơn baseline không?
- [ ] Plugin Gradle và build logic có chạy được trên daemon JVM không?
- [ ] Annotation processor/code generator có yêu cầu JDK riêng không?
- [ ] Test launcher dùng đúng Java release không?
- [ ] Preview features có được bật đồng bộ ở compile, test và runtime không?
- [ ] Docker runtime image/server JDK có hỗ trợ bytecode của artifact không?
- [ ] CI có dùng cùng cấu hình toolchain và runtime test như local không?
- [ ] Artifact JAR/WAR cuối cùng đã được kiểm tra và smoke test trên Java mục tiêu chưa?

## 13. Kịch bản chẩn đoán theo nơi lỗi xuất hiện

Thời điểm lỗi xuất hiện thường giúp thu hẹp phạm vi tìm kiếm trước khi đọc toàn bộ dependency graph.

### 13.1. Lỗi xuất hiện ngay khi chạy Gradle

Ví dụ:

~~~text
Could not apply plugin ...
UnsupportedClassVersionError: ...PluginImplementation...
~~~

Khả năng cao class lỗi thuộc Gradle plugin hoặc build logic. Kiểm tra:

1. JVM của Gradle bằng `./gradlew --version`.
2. Plugin ID và version trong `plugins` block hoặc plugin management.
3. JDK tối thiểu plugin yêu cầu.
4. Gradle wrapper version mà plugin hỗ trợ.
5. Class nằm trong plugin JAR nào nếu stack trace chỉ rõ.

Đổi `options.release` của application không giải quyết lỗi này vì JavaCompile task của ứng dụng chưa chạy.

### 13.2. Lỗi xuất hiện ở compileJava

Nếu lỗi xuất hiện khi javac nạp annotation processor hoặc compiler plugin, hãy xem toolchain/compiler process và processor path. Nếu lỗi xảy ra khi compiler đọc dependency class, xác định dependency đó và kiểm tra class-file version của class được nhắc trong log.

Một dependency có thể có bytecode mới hơn target application. Việc compile source với `options.release` thấp hơn không làm compiler đọc được class file mà chính compiler JVM không hỗ trợ.

### 13.3. Compile pass nhưng test fail

Kiểm tra test worker JVM và test runtime classpath:

~~~bash
./gradlew test --info --stacktrace
~~~

Nếu build có nhiều test task, kiểm tra task cụ thể và cấu hình launcher của nó. Xem class lỗi thuộc test engine, test fixture, application class hay runtime dependency.

Một số test framework mới có thể yêu cầu Java release cao hơn runtime mà test task đang dùng. Cần chọn version framework phù hợp hoặc nâng test launcher.

### 13.4. Build pass nhưng ứng dụng không khởi động

Trong trường hợp này, kiểm tra JVM chạy application process. Đối chiếu major version của class được nêu trong lỗi với runtime server/container. Nếu dùng JAR/WAR, kiểm tra artifact đã deploy và dependency được nạp tại runtime.

Không nên kết luận rằng Gradle đã tạo artifact đúng baseline chỉ vì task build thành công. Build thành công chỉ chứng minh các task trong build đã chạy được trên môi trường build; nó không chứng minh runtime production có thể nạp tất cả class.

### 13.5. Chỉ một endpoint hoặc chức năng mới gây lỗi

Một số class chỉ được nạp khi code path cụ thể chạy. Framework có thể nạp serializer, driver, plugin hoặc implementation theo tên class khi request đầu tiên tới endpoint.

Khi đó ứng dụng có thể khởi động thành công nhưng ném UnsupportedClassVersionError ở request đầu tiên. Hãy kiểm tra class được nạp lazy và dependency liên quan tới chức năng đó, thay vì chỉ kiểm tra classpath lúc startup.

## 14. Ví dụ cấu hình Java nhất quán cho Gradle

Một build có thể ghi rõ compiler toolchain và release target:

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
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình minh họa này có chủ đích:

- JDK 21 được chọn làm toolchain của project.
- Compiler tạo bytecode/API target Java 17.
- Test launcher dùng Java 17 để xác nhận ứng dụng và test chạy trên baseline mục tiêu.
- Gradle daemon vẫn chạy trên JVM được chọn riêng theo Gradle runtime configuration.

Trong dự án thực tế, nếu cần annotation processor chạy trên JDK 21 nhưng test chạy Java 17, hãy xác định rõ toolchain cho từng task thay vì giả định mọi task dùng một JVM. Cũng cần xác nhận dependency runtime tương thích Java 17.

### 14.1. Ghi lại Java version trong CI

CI nên in thông tin Java và Gradle ở đầu job:

~~~bash
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

Các thông tin này giúp phát hiện khác biệt giữa local và CI. Với build containerized, in thêm Java version trong runtime image hoặc log từ application process.

### 14.2. Kiểm tra class-file version của artifact release

Sau khi build, dùng `javap` để kiểm tra class nghi ngờ từ đúng JAR được phát hành. Với WAR, trước hết liệt kê archive và xác định JAR chứa class. Có thể trích JAR ra thư mục tạm rồi chạy javap trên class đó.

Nếu nhiều module trong sản phẩm được phát hành riêng, kiểm tra artifact của từng module có baseline nhất quán. Dependency runtime có thể đặt yêu cầu Java cao hơn module chính.

## 15. Ma trận quyết định sửa lỗi

| Tình huống | Hướng xử lý chính |
|---|---|
| Runtime production thấp hơn bytecode ứng dụng | Nâng runtime hoặc compile ứng dụng về baseline được hỗ trợ |
| Dependency yêu cầu Java mới hơn baseline | Dùng dependency version cũ tương thích hoặc nâng baseline ứng dụng |
| Gradle daemon không nạp được plugin | Nâng JVM chạy Gradle hoặc dùng plugin version tương thích |
| Gradle wrapper không hỗ trợ JDK hiện tại | Nâng Gradle wrapper theo compatibility matrix hoặc chọn JDK được Gradle hỗ trợ |
| Test worker quá cũ | Cấu hình test launcher phù hợp hoặc hạ version test framework |
| Preview class bị từ chối | Dùng đúng Java release và bật preview ở compile/runtime |
| Docker runtime thấp hơn build JDK | Đồng bộ runtime image hoặc đặt compile release thấp hơn có kiểm soát |
| Chỉ class nạp lazy bị lỗi | Xác định dependency/class được nạp theo code path và thay version tương thích |

### 15.1. Ví dụ quyết định từ thông báo lỗi

Giả sử log cho biết:

~~~text
class file version 65.0
runtime recognizes up to 61.0
~~~

Diễn giải:

- Class cần Java 21.
- JVM hiện tại là Java 17.
- Nếu class thuộc ứng dụng: kiểm tra compile target và runtime deployment.
- Nếu class thuộc dependency: chọn dependency version tương thích hoặc nâng runtime.
- Nếu class thuộc Gradle plugin: kiểm tra JVM chạy Gradle, không chỉ Java toolchain của project.

Cùng một cặp version nhưng cách sửa phụ thuộc class được nạp trong process nào. Bởi vậy, đọc tên class và stack trace là bước bắt buộc trước khi thay đổi cấu hình.

## 16. Checklist xử lý một sự cố thực tế

Khi nhận ticket UnsupportedClassVersionError, có thể thu thập các thông tin sau:

- [ ] Toàn bộ exception và stack trace.
- [ ] Tên class được JVM từ chối nạp.
- [ ] Class-file major/minor version của class đó.
- [ ] Java version và java.home của process bị lỗi.
- [ ] Gradle wrapper version và Gradle daemon JVM nếu lỗi trong build.
- [ ] Java toolchain và options.release của compile task.
- [ ] Java launcher của test task nếu lỗi trong test.
- [ ] Dependency/plugin artifact chứa class.
- [ ] Runtime JDK của server hoặc Docker image.
- [ ] Baseline Java đã cam kết với người dùng/production.
- [ ] Cách tái hiện lỗi sau khi đồng bộ version.

Với các thông tin này, có thể phân loại lỗi thuộc build runtime, compiler/toolchain, dependency, test runtime hay deployment runtime. Sau khi sửa, chạy lại đúng bước từng thất bại và smoke test bằng Java baseline mục tiêu.

## Kết luận

`UnsupportedClassVersionError` không đơn giản là “máy thiếu JDK mới”. Đây là dấu hiệu một JVM đang nạp class file có version cao hơn mức nó hỗ trợ. Class đó có thể thuộc ứng dụng, dependency, plugin, processor, test engine hoặc thư viện do server cung cấp.

Hãy bắt đầu từ thông báo lỗi, xác định process/JVM gây lỗi và class-file version, rồi truy ra artifact chứa class. Sau đó chọn một Java baseline rõ ràng, đồng bộ Gradle runtime, toolchain, compiler release, dependency, test launcher và deployment runtime. Toolchain chọn JDK cho task; `options.release` giới hạn bytecode và Java API; JVM chạy Gradle và JVM chạy ứng dụng vẫn là các cấu hình riêng. Khi mọi lớp này được xác định rõ và được kiểm thử trên runtime mục tiêu, lỗi do chênh lệch Java version sẽ dễ chẩn đoán và phòng tránh hơn.
