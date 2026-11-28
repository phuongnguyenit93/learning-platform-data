# Đồng bộ JDK biên dịch, JDK kiểm thử và JDK chạy trong pipeline

> **Chương:** Build và triển khai
>
> **Phạm vi:** Xây dựng pipeline cho ứng dụng Java 25, kiểm soát JDK dùng để biên dịch, chạy test và triển khai production. Bài tập trung vào Java toolchain, --release 25, Maven/Gradle, CI image, runtime verification và các cờ bổ sung khi ứng dụng chủ động dùng preview/incubator API.

## 1. Vì sao phải đồng bộ JDK ở cả ba giai đoạn?

Một pipeline Java có ít nhất ba môi trường thực thi:

1. **Compile JDK:** cung cấp javac, annotation processors và API được nhìn thấy lúc biên dịch.
2. **Test JDK:** JVM chạy unit test, integration test, test framework, agent và tiến trình phụ.
3. **Runtime JDK:** JVM chạy artifact trên máy chủ, container hoặc custom runtime image.

Ngoài ba môi trường đó, Maven hoặc Gradle cũng chạy trên một JVM riêng. JVM của build tool/daemon có thể khác toolchain biên dịch và test nếu dự án chủ động cấu hình.

Nếu các giai đoạn không được kiểm soát, lỗi có thể chỉ xuất hiện sau deploy:

- Compile thành công vì compiler mới nhìn thấy API mới, nhưng production runtime không có API đó.
- Unit test chạy trên JDK 25, còn integration test hoặc container dùng JVM khác.
- Dependency chứa class file mới hơn runtime production.
- Preview API được compile nhưng runtime thiếu --enable-preview.
- Incubator module có trên máy developer nhưng không có trong runtime image.
- Vendor, patch hoặc architecture khác nhau làm thay đổi TLS, bảo mật, GC hay native integration.

Với module Java 25, cần xác định JDK đích, buộc build tool chọn đúng compiler/test launcher, rồi kiểm tra image triển khai thực sự chứa runtime đã được kiểm thử.

## 2. Phân biệt --release, toolchain và runtime

Ba cấu hình thường bị nhầm là một:

| Cơ chế | Kiểm soát điều gì? | Không kiểm soát điều gì? |
| --- | --- | --- |
| javac --release 25 | Quy tắc ngôn ngữ, class file đích và tập API Java/JDK của release 25 | Không chọn JDK cài đặt nào chạy compiler; không chọn JVM test hoặc production |
| Java toolchain 25 | Chọn JDK cung cấp compiler, test launcher hoặc Javadoc tool | Không tự pin runtime image được deploy; không thay thế kiểm tra API bằng --release |
| Runtime image JDK 25 | JVM thực tế chạy ứng dụng | Không chứng minh artifact được compile/test bằng cùng JDK |

--release là lựa chọn hiện hành để cross-compile đúng một Java release. Nó kiểm tra API của release mục tiêu, tránh vô tình gọi API mới hơn chỉ có trong JDK đang cài. Không kết hợp --release với --source hoặc --target trong cùng lệnh.

Toolchain xác định binary JDK nào được dùng. Runtime image lại là một đầu vào triển khai độc lập. Muốn đồng bộ, phải khai báo cả ba.

~~~text
JDK distribution/build đã pin
             |
             v
       Build tool / daemon
             |
             v
   Compiler toolchain JDK 25
       javac --release 25
             |
             v
      Artifact + metadata
             |
             v
       Test launcher JDK 25
      unit + integration test
             |
             v
       Runtime image JDK 25
          smoke test / deploy
~~~

## 3. Chọn một JDK đích có thể tái lập

Không chỉ ghi “dùng Java 25”. Hãy xác định:

- Major version: 25.
- Vendor/distribution: ví dụ Eclipse Temurin, Oracle JDK, Amazon Corretto hoặc bản OpenJDK được tổ chức phê duyệt.
- Patch/build: phiên bản cập nhật cụ thể đã được kiểm thử.
- Architecture: x64 hoặc AArch64 theo môi trường triển khai.
- Hệ điều hành và libc nếu có native dependency.
- Build image và runtime image được pin bằng digest.

Ví dụ metadata phát hành nội bộ:

~~~text
JAVA_MAJOR=25
JAVA_VENDOR=Eclipse Adoptium
JAVA_BUILD=<exact-tested-build>
JAVA_ARCH=x64
BUILD_IMAGE=registry.example.com/build/jdk25@sha256:<digest>
RUNTIME_IMAGE=registry.example.com/runtime/jre25@sha256:<digest>
~~~

Các giá trị <...> là chỗ điền build và digest thực tế. Không dùng tag trôi nổi như latest làm bằng chứng build và production đang dùng cùng JDK.

### 3.1. Pin major version khác với pin patch version

Toolchain thường chọn theo language version và có thể lọc thêm vendor/implementation. Yêu cầu 25 không nhất thiết khóa đúng patch build. Resolver có thể chọn một bản cập nhật khác nếu nhiều JDK cùng thỏa điều kiện.

Để tái lập chính xác:

1. Chọn vendor và JDK update đã được phê duyệt.
2. Pin build agent/container bằng image digest hoặc artifact nội bộ bất biến.
3. Ghi output java --version trong log pipeline.
4. Cập nhật build image và runtime image theo cùng một thay đổi có kiểm thử.
5. Không để PATH của máy developer tự chọn một JDK khác.

## 4. Kiểm tra JDK đang thực sự được sử dụng

Các lệnh sau giúp kiểm tra môi trường:

~~~bash
java --version
javac --version
java -XshowSettings:properties -version
~~~

java --version cho biết JVM launcher mặc định. javac --version cho biết compiler trên PATH. -XshowSettings:properties hiển thị các thuộc tính như java.home, java.vendor, java.version, os.arch và os.name.

Nếu dùng Maven:

~~~bash
./mvnw --version
~~~

Nếu dùng Gradle:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

Các lệnh version cho biết JVM chạy Maven/Gradle và phiên bản build tool. Chúng **không tự chứng minh** compiler/test fork đã dùng đúng toolchain. Hãy kiểm tra log lựa chọn toolchain và JVM fork của test runner.

## 5. Cấu hình Maven dùng JDK 25

Maven có thể chạy trên một JVM và yêu cầu toolchain khác cho các plugin build. Maven Toolchains Plugin chọn JDK từ cấu hình agent rồi cung cấp cho plugin có hỗ trợ toolchain.

### 5.1. Khai báo toolchain và release trong pom.xml

~~~xml
<properties>
  <maven.compiler.release>25</maven.compiler.release>
</properties>

<build>
  <plugins>
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
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.16.0</version>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.6.1</version>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.6.1</version>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Goal toolchain được chạy ở giai đoạn validate khi được bind như trên. Nếu không tìm được JDK phù hợp, build nên fail sớm thay vì âm thầm dùng compiler khác.

maven.compiler.release giới hạn ngôn ngữ, bytecode và API mục tiêu. Toolchain chọn JDK thực sự dùng cho compiler. Cần cả hai để build tái lập và tránh vô tình dùng API ngoài release 25.

### 5.2. Khai báo JDK trên build agent

Toolchains Plugin đọc các JDK cài trên agent từ ~/.m2/toolchains.xml. Ví dụ trên Linux:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>25</version>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/jdk-25</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Đường dẫn phải trỏ tới JDK thực tế trên agent. Không commit đường dẫn máy cá nhân vào repository; CI tạo file này từ JDK đã cài trong build image hoặc dùng cơ chế discovery được phê duyệt.

Nếu cần ràng buộc vendor, thêm token vendor trong provides và yêu cầu tương ứng trong pom.xml. Giá trị vendor phải khớp metadata trong toolchains file; Maven không xác minh rằng đường dẫn jdkHome thực sự chứa đúng vendor/version được khai báo.

### 5.3. Đồng bộ JVM chạy test

Surefire chạy unit tests và Failsafe chạy integration tests. Khi Maven Toolchains Plugin đã chọn JDK chính, các phiên bản Surefire/Failsafe có hỗ trợ toolchain sẽ dùng toolchain đó làm JVM chạy test theo mặc định.

Nếu một execution cần JDK khác, có thể cấu hình jdkToolchain riêng cho plugin. Chỉ làm vậy khi có ma trận test có chủ đích, ví dụ kiểm tra tương thích trên JDK 25 và JDK 27.

mvn --version chỉ mô tả JVM khởi chạy Maven. Hãy kiểm tra log toolchain và log JVM fork của Surefire/Failsafe để xác nhận test launcher.

## 6. Cấu hình Gradle dùng JDK 25

Gradle tách JVM chạy Gradle daemon khỏi Java toolchain dùng cho project. Toolchain ở project giúp các task compile, test và Javadoc dùng JDK đã chọn.

Ví dụ build.gradle.kts:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion
import org.gradle.jvm.toolchain.JvmVendorSpec

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 25
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(25)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
~~~

JvmVendorSpec.ADOPTIUM là ví dụ cho tổ chức chọn Temurin. Nếu dùng vendor khác, hãy chọn vendor tương ứng hoặc bỏ điều kiện vendor khi chính sách cho phép. Pin build image vẫn cần thiết nếu muốn cố định patch/build cụ thể.

options.release = 25 giúp compiler không dùng API mới hơn Java 25. Toolchain chọn JDK 25 cung cấp compiler và launcher. Nếu chỉ đặt options.release mà không đặt toolchain, Gradle vẫn có thể dùng compiler từ JDK khác.

### 6.1. JVM chạy Gradle daemon là một lựa chọn riêng

Gradle daemon được khởi chạy bởi môi trường build, thường qua JAVA_HOME hoặc cấu hình daemon JVM. Đây không phải JavaCompiler hoặc JavaLauncher của project.

Với pipeline ổn định:

- Dùng Gradle Wrapper để khóa phiên bản Gradle.
- Chọn daemon JVM mà phiên bản Gradle hỗ trợ.
- Cấu hình project toolchain JDK 25.
- Chọn cùng JDK vendor cho compile/test nếu đó là yêu cầu phát hành.
- Pin container/build agent để khóa patch và architecture.

Gradle Daemon JVM criteria có thể được lưu trong repository để chọn JVM chạy daemon. Không nhầm tiêu chí đó với toolchain của project.

### 6.2. Tránh fallback âm thầm

Gradle có thể tự phát hiện JDK và, nếu được cấu hình repository resolver, tự tải toolchain còn thiếu. Điều này tiện cho developer nhưng CI release cần biết chính xác JDK nào được dùng.

- Khai báo rõ language version và vendor.
- Chỉ cấu hình download repository được tổ chức phê duyệt.
- Ghi lại kết quả javaToolchains.
- Fail build nếu không tìm được toolchain đáp ứng.
- Không dựa riêng vào JAVA_HOME hoặc cấu hình JVM của IDE.

## 7. --release 25 không tự chọn runtime JDK 25

--release 25 tạo class file cho Java 25 và giới hạn API ở mức Java 25. Nó không đóng gói JVM vào JAR và không ép máy production cài JDK 25.

Ví dụ:

~~~bash
javac --release 25 -d out src/main/java/example/App.java
java -jar app.jar
~~~

Lệnh thứ hai dùng java đầu tiên trên PATH. Nếu PATH trỏ tới runtime cũ hơn, ứng dụng có thể lỗi khi khởi động hoặc khi nạp class có bytecode/API không tương thích.

Runtime phải được khai báo riêng trong deployment manifest/container image. Build thành công không phải bằng chứng deploy thành công.

### 7.1. Xác minh class file

Có thể xem class file major version bằng javap:

~~~bash
javap -verbose -classpath target/classes example.App
~~~

Java 25 sử dụng class file major version 69. Kiểm tra này giúp phát hiện bytecode được tạo ở release khác, nhưng không chứng minh dependency runtime, native library, preview flag hoặc API đều tương thích.

## 8. Chạy test trên đúng runtime mục tiêu

Một pipeline Java 25 nên chạy ít nhất:

| Giai đoạn | JVM yêu cầu | Mục đích |
| --- | --- | --- |
| Unit test | JDK 25 | Kiểm tra logic và thư viện trong môi trường runtime mục tiêu |
| Integration test | JDK 25 | Kiểm tra database, HTTP client, serialization, TLS và native integration |
| Packaging smoke test | Runtime image sẽ deploy | Kiểm tra ứng dụng khởi động từ artifact đã đóng gói |
| Production readiness test | Runtime image đã pin | Xác nhận readiness, cấu hình và dependency lúc chạy |

Không chỉ chạy test trên JVM của Gradle/Maven daemon. Test task phải dùng launcher đã chọn. Integration test cũng cần xác minh JVM của tiến trình ứng dụng do test harness khởi chạy.

Nếu production dùng runtime image tối giản, hãy chạy smoke test trực tiếp trong image đó. Test trên JDK cài đầy đủ có thể che giấu module hoặc file hệ thống bị thiếu.

## 9. Preview API và incubator module cần đồng bộ thêm cờ

Java 25 có các tính năng ở nhiều trạng thái. Không phải tính năng nào cũng dùng cùng một cờ:

| Loại tính năng | Cách bật | Nơi phải cấu hình |
| --- | --- | --- |
| Feature/API đã final trong JDK 25 | Không cần cờ preview riêng | Compile/test/runtime theo yêu cầu thông thường |
| Preview feature của JDK 25 | --enable-preview | Compiler, JVM chạy test và JVM production |
| Incubator module như Vector API | --add-modules jdk.incubator.vector | Compiler, test JVM và runtime launcher; named module khai báo requires |

Nếu dùng preview API:

~~~bash
javac --release 25 --enable-preview -d out src/main/java/example/PreviewApp.java
java --enable-preview -cp out example.PreviewApp
~~~

Preview class file gắn với đúng release đã tạo ra nó. Mã preview biên dịch bằng JDK 25 phải chạy trên JDK 25 có bật preview; không chuyển nguyên preview artifact sang JDK 26/27 và giả định tương thích.

Nếu dùng Vector API:

~~~bash
javac --release 25 --add-modules jdk.incubator.vector -d out src/main/java/example/VectorApp.java
java --add-modules jdk.incubator.vector -cp out example.VectorApp
~~~

Incubator module có thể thay đổi giữa các JDK. Hãy compile, test và chạy trên đúng JDK mục tiêu; khi nâng lên JDK mới, biên dịch lại và kiểm tra API/module flags.

### 9.1. Truyền flags vào Maven và Gradle

Với Maven, cấu hình compiler arguments cho javac và JVM arguments cho test fork. Ví dụ với Vector API:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <release>25</release>
    <compilerArgs>
      <arg>--add-modules</arg>
      <arg>jdk.incubator.vector</arg>
    </compilerArgs>
  </configuration>
</plugin>

<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.6.1</version>
  <configuration>
    <argLine>--add-modules jdk.incubator.vector</argLine>
  </configuration>
</plugin>

<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>3.6.1</version>
  <configuration>
    <argLine>--add-modules jdk.incubator.vector</argLine>
  </configuration>
</plugin>
~~~

Với Gradle Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf("--add-modules", "jdk.incubator.vector")
    )
}

tasks.withType<Test>().configureEach {
    jvmArgs("--add-modules", "jdk.incubator.vector")
}
~~~

Nếu ứng dụng còn dùng preview feature của Java 25, thêm --enable-preview cho compiler và mọi JVM chạy test/ứng dụng. Ví dụ:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}
~~~

Trong production launcher, truyền các cờ tương ứng vào command line hoặc cấu hình service. Với Maven, nếu plugin khác cũng quản lý argLine (ví dụ coverage agent), hãy ghép các argument thay vì ghi đè cấu hình của plugin kia.

Không thêm --enable-preview hoặc --add-modules mặc định cho mọi ứng dụng. Chỉ bật cờ tương ứng với feature thực sự được dùng và truyền cờ giống nhau vào mọi JVM liên quan.

## 10. Đồng bộ runtime image và container

Một container production nên pin image chứa đúng runtime đã được test:

~~~dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Tag minh họa trên mới khóa major line, chưa khóa patch. Pipeline phát hành nên thay bằng tag patch cụ thể và digest đã được kiểm duyệt:

~~~dockerfile
FROM registry.example.com/runtime/temurin-25-jre@sha256:<approved-digest>
WORKDIR /app
COPY target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build image và runtime image có thể dùng base image khác nhau (JDK đầy đủ và JRE), nhưng nên cùng vendor, major version, patch/build và architecture nếu mục tiêu là kiểm thử đúng môi trường deploy.

Nếu runtime image dùng vendor/build khác, hãy coi đó là một cấu hình runtime mới và chạy test matrix riêng.

## 11. Dùng jlink khi cần custom runtime image

jlink tạo runtime image chứa tập module cần thiết thay vì đóng gói toàn bộ JDK. Điều này có thể giảm kích thước image và giới hạn thành phần được triển khai.

Quy trình:

1. Build artifact bằng JDK 25 đã pin.
2. Phân tích dependency module bằng jdeps.
3. Kiểm tra module được nạp động qua reflection, service loader hoặc plugin.
4. Tạo runtime image bằng jlink từ đúng JDK vendor/build mục tiêu.
5. Chạy smoke test và integration test trong runtime image vừa tạo.

Ví dụ phân tích dependency:

~~~bash
jdeps --multi-release 25 --print-module-deps target/app.jar
~~~

Sau khi xác nhận danh sách module cần có:

~~~bash
jlink \
  --add-modules java.base,java.logging,java.sql \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
~~~

Danh sách module trong ví dụ chỉ minh họa. Hãy thay bằng dependency thực tế và bổ sung module được nạp động. Nếu dùng Vector API hoặc module JDK khác, đưa module đó vào runtime image.

Không dùng jlink từ JDK khác với runtime mục tiêu rồi cho rằng image có cùng hành vi. Tạo và kiểm tra runtime image bằng đúng JDK đã chọn cho release.

## 12. Ma trận kiểm thử khi hỗ trợ nhiều JDK

Nếu ứng dụng chỉ hỗ trợ JDK 25, pipeline bắt buộc build/test/runtime trên JDK 25. Nếu ứng dụng công bố hỗ trợ nhiều JDK, mở rộng thành ma trận:

| Artifact | Test JDK | Runtime JDK | Ý nghĩa |
| --- | --- | --- | --- |
| Compile với --release 25 | 25 | 25 | Baseline bắt buộc |
| Compile với --release 25 | 25 | 26 | Kiểm tra runtime mới hơn |
| Compile với --release 25 | 25 | 27 | Kiểm tra runtime mới hơn trong phạm vi hỗ trợ |
| Compile/test lại theo release mới | 26 hoặc 27 | Cùng release | Kiểm tra khi chủ động nâng target |

Với API Java SE đã final, bytecode release 25 thường có thể chạy trên runtime mới hơn nếu dependency tương thích. Điều này không đảm bảo cho preview API, incubator API, JDK internal API, native library hoặc hành vi đã thay đổi.

Nếu dùng preview/incubator của JDK 25, không dùng ma trận runtime mới hơn để thay thế test trên JDK 25. Hãy duy trì artifact riêng cho mỗi JDK preview/incubator mà ứng dụng hỗ trợ.

## 13. Kiểm soát CI để tránh lệch môi trường

Một pipeline phát hành có thể tổ chức thành các stage:

~~~text
1. Resolve build image đã pin
2. In java --version, javac --version và build-tool version
3. Kiểm tra toolchain được chọn
4. Compile với --release 25
5. Chạy unit tests bằng test launcher JDK 25
6. Chạy integration tests bằng JDK 25
7. Đóng gói JAR và lưu build metadata
8. Tạo runtime image JDK 25 đã pin
9. Chạy smoke test bên trong runtime image
10. Publish đúng artifact/image đã được test
~~~

Nguyên tắc vận hành:

- Dùng Maven Wrapper hoặc Gradle Wrapper để khóa phiên bản build tool.
- Khóa JDK build image bằng digest hoặc artifact nội bộ bất biến.
- Khai báo toolchain trong project, không dựa vào PATH ngẫu nhiên.
- Lưu log java --version, javac --version, Maven/Gradle version và toolchain path.
- Lưu checksum artifact và container image để bảo đảm artifact được test chính là artifact được deploy.
- Không build lại artifact trong stage deploy nếu không có lý do; promote artifact đã kiểm thử.
- Cập nhật JDK patch bằng một thay đổi có review và test lại.

## 14. Chẩn đoán khi compile/test/runtime không đồng bộ

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| UnsupportedClassVersionError | Runtime cũ hơn bytecode target | Kiểm tra major version class file và java --version trong runtime image |
| NoSuchMethodError hoặc NoClassDefFoundError | Compile/test/runtime dùng dependency hoặc JDK API khác nhau | Kiểm tra dependency tree, runtime JDK và classpath/module path |
| Compiler không tìm thấy API Java 25 | Compiler toolchain quá cũ hoặc --release đặt thấp | Xác nhận compiler JDK 25 và release mục tiêu |
| Test pass local nhưng fail CI | IDE/JAVA_HOME local khác toolchain CI | In toolchain metadata và dùng build image đã pin |
| mvn --version là JDK 25 nhưng test chạy JDK khác | Maven JVM khác Surefire/Failsafe toolchain | Kiểm tra toolchain selection và forked test JVM |
| Gradle daemon dùng JDK khác toolchain | JVM chạy Gradle daemon tách khỏi project toolchain | Kiểm tra daemon JVM criteria và javaToolchains |
| Preview API báo lỗi khi chạy | Thiếu --enable-preview hoặc chạy sai JDK release | Đồng bộ compile/test/runtime flags và JDK release |
| Không tìm thấy incubator module khi chạy | Runtime image thiếu module hoặc launcher không add module | Thêm module vào jlink image và --add-modules khi cần |
| App chạy ở JDK đầy đủ nhưng fail trong JRE image | Runtime image tối giản thiếu module hoặc native dependency | Kiểm tra jdeps, module nạp động và smoke test trong image |
| Cùng major 25 nhưng hành vi khác nhau | Vendor, patch/build hoặc OS/architecture khác | Ghi metadata đầy đủ và tái hiện trên đúng image |

## 15. Bài tập thực hành

### Bài A — Xác nhận ba JDK

Thiết lập JDK 25 trên máy developer hoặc CI. Ghi lại java --version, javac --version, mvn --version hoặc gradle --version, cùng đường dẫn toolchain.

**Điều kiện đạt:** phân biệt được JVM chạy build tool, compiler toolchain và test launcher.

### Bài B — Cấu hình compiler release

Thiết lập Maven hoặc Gradle dùng toolchain JDK 25 và --release 25.

**Điều kiện đạt:** compiler dùng JDK 25, bytecode target là Java 25 và compiler từ chối API không thuộc release 25.

### Bài C — Chạy test bằng đúng launcher

Cấu hình unit và integration tests dùng JDK 25. In java.version và java.vendor trong tiến trình test.

**Điều kiện đạt:** log test cho thấy đúng vendor/version được phê duyệt.

### Bài D — Kiểm tra runtime image

Đóng gói ứng dụng trong runtime container hoặc custom runtime image. Chạy java --version và smoke test từ chính image đó.

**Điều kiện đạt:** runtime image dùng đúng JDK đã kiểm thử; ứng dụng khởi động và readiness test thành công.

### Bài E — Mở rộng ma trận runtime

Nếu sản phẩm tuyên bố hỗ trợ JDK mới hơn, chạy cùng artifact trên từng runtime được hỗ trợ.

**Điều kiện đạt:** có báo cáo rõ version, vendor, build, OS/architecture và kết quả test của từng runtime.

## 16. Checklist trước khi phát hành

- [ ] Đã chọn JDK major, vendor, patch/build và architecture cho release.
- [ ] Build image được pin bằng tag cụ thể và digest bất biến.
- [ ] Maven Wrapper hoặc Gradle Wrapper được khóa phiên bản.
- [ ] Compiler toolchain dùng đúng JDK mục tiêu.
- [ ] Compiler đặt --release 25.
- [ ] Unit test và integration test dùng đúng test launcher.
- [ ] Đã phân biệt JVM chạy Maven/Gradle với JVM chạy compiler/test.
- [ ] Preview/incubator flags được khai báo tường minh nếu ứng dụng thực sự sử dụng.
- [ ] Runtime image dùng cùng JDK vendor/build đã được kiểm thử.
- [ ] Runtime image có đủ module và native dependencies.
- [ ] Smoke test chạy bên trong image sẽ deploy.
- [ ] Artifact được promote nguyên vẹn từ build/test sang deploy.
- [ ] Build metadata lưu JDK, vendor, build, toolchain, dependency và image digest.
- [ ] Mỗi lần cập nhật JDK patch/vendor đều chạy lại pipeline.

## 17. Tài liệu tham khảo

1. [Oracle Java 25 — javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): ý nghĩa --release, --source, --target và API được dùng khi compile.
2. [Oracle Java 25 — java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): launcher, JVM settings và cách xem runtime properties.
3. [Oracle Java 25 — Preparing for Migration](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html): khuyến nghị dùng --release thay cho cấu hình -source/-target riêng lẻ.
4. [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): chọn compiler, test launcher, vendor và toolchain download.
5. [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): JVM chạy Gradle daemon và daemon JVM criteria.
6. [Gradle — Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html): kết hợp Java toolchain và --release.
7. [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains): chọn JDK toolchain cho các plugin Maven.
8. [Apache Maven — Toolchains Plugin usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html): cấu hình yêu cầu toolchain và xử lý khi không tìm thấy JDK phù hợp.
9. [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cấu hình maven.compiler.release.
10. [Maven Surefire — Using Maven Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains): chọn JVM chạy unit test bằng toolchain.
11. [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html): vòng đời integration-test và verify.
12. [Maven Plugin Directory](https://maven.apache.org/plugins/): kiểm tra phiên bản hiện hành của Maven Compiler, Surefire và Failsafe plugins.
13. [Oracle Java 25 — Image and Runtime Modifications](https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html): tạo custom runtime bằng jlink và đóng gói bằng jpackage.

**Ghi nhớ:** --release 25 khóa ngôn ngữ, API và bytecode; toolchain khóa JDK chạy compiler/test; runtime image khóa JVM production. Ba lớp này phải được cấu hình và kiểm tra riêng. Với preview hoặc incubator API, còn phải đồng bộ đúng JDK release và cờ compile/runtime. Chỉ phát hành artifact đã được kiểm thử bên trong runtime image sẽ triển khai.
