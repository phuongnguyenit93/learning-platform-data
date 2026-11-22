# Duy trì khả năng build song song trên JDK cũ và mới trong giai đoạn chuyển tiếp

Trong **Java Advance Compatibility Migration**, nâng JDK không nên là một lần đổi **JAVA_HOME** rồi coi mọi thành phần đã được chuyển đổi. Các môi trường phát triển, CI, máy chạy batch, container production, thư viện dùng chung và consumer có thể có lịch nâng cấp khác nhau. Một khoảng thời gian **hai JDK cùng được hỗ trợ** giúp tổ chức kiểm chứng thay đổi liên tục, thay vì chỉ phát hiện lỗi khi hết khả năng quay về môi trường cũ.

Bài học thuộc chương **Chiến lược chuyển đổi**. Nội dung trình bày cách duy trì build song song trên JDK baseline và JDK mục tiêu, kiểm soát toolchain/bytecode/API, tổ chức CI matrix và test runtime, xử lý dependencies, annotation processors, build caches, variant artifacts, cùng tiêu chí chính thức ngừng hỗ trợ JDK cũ.

Các ví dụ sử dụng **JDK 17** và **JDK 21** làm cặp minh họa. Chúng không phải lựa chọn bắt buộc cho mọi dự án; hãy dùng các phiên bản được tổ chức công bố trong support policy.

## 1. Build song song thực sự có nghĩa gì?

Giả sử source code của ứng dụng cần tiếp tục chạy trên cả Java 17 và Java 21.

Một yêu cầu chưa đủ:

> Lệnh build chạy thành công một lần với Java 17 và một lần với Java 21.

Một yêu cầu có khả năng kiểm chứng tốt hơn:

- Build tool và compiler được xác định rõ ở từng lane.
- Source chính được kiểm tra với Java language/API baseline.
- Dependencies không yêu cầu runtime cao hơn baseline nếu phát hành một artifact.
- Test code được thực thi trên cả runtime còn hỗ trợ.
- Generated source/bytecode không dựa vào output cũ.
- Artifact đóng gói được khởi động bằng đúng JVM mục tiêu.
- Các integration contracts và các thay đổi hành vi được kiểm chứng.
- Pipeline hiển thị trạng thái từng JDK riêng biệt, có release gates.
- Có tiêu chí rõ khi nào JDK cũ không còn được hỗ trợ.

### 1.1. Các lớp Java version khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Build JVM | JVM chạy Gradle daemon hoặc Maven | JDK 21 |
| Compiler JDK | Bản javac trực tiếp biên dịch Java source | javac 17 hoặc javac 21 |
| Language level | Giới hạn cú pháp Java cho phép | Java 17 |
| Platform API level | Java SE APIs được phép tham chiếu | Java SE 17 |
| Bytecode target | Class-file format mà JVM tối thiểu có thể đọc | Major 61 |
| Test JVM | JVM chạy JUnit/integration tests | 17 và 21 |
| Runtime JVM | JVM thực tế chạy artifact | 17 hoặc 21 |
| Build plugin runtime | JVM mà Gradle/Maven plugin thực thi | Có thể là JVM của build tool |
| Agent/processor runtime | JVM hoặc compiler environment của công cụ | Không nhất thiết giống runtime của ứng dụng |

**Một build sử dụng javac 21 với --release 17 không phải build sử dụng javac 17.** Kết quả có thể tương thích bytecode/API Java 17, nhưng annotation processor và compiler plugin vẫn được chạy trên JDK 21.

### 1.2. Hai mục tiêu hỗ trợ khác nhau

**Mô hình A — một source, một artifact chạy trên nhiều JDK:**

~~~text
                    Cùng codebase
                         |
         +---------------+---------------+
         |                               |
   Build/test JDK 17                Build/test JDK 21
         |                               |
         +---------------+---------------+
                         |
                 Phát hành JAR target 17
                         |
             +-----------+-----------+
             |                       |
          Runtime 17              Runtime 21
~~~

Với mô hình này, **minimum runtime vẫn là Java 17**. Không đưa các API Java 21 bắt buộc vào shared code cho đến khi thay chính sách hỗ trợ hoặc có kiến trúc cô lập.

**Mô hình B — một codebase, hai biến thể artifact:**

~~~text
                    Shared modules
                         |
                 +-------+-------+
                 |               |
           Java 17 variant   Java 21 variant
                 |               |
           Test on 17       Test on 21
                 |               |
         Publish legacy    Publish modern
~~~

Mô hình B cho phép sử dụng Java 21 APIs ở variant hiện đại nhưng làm tăng chi phí build, versioning, bảo trì và testing. Hai biến thể phải có **artifact identity** phân biệt, không được phát hành cùng tọa độ/version với nội dung không xác định.

Chọn mô hình trước khi thiết kế matrix; nếu không, hai lane "green" vẫn có thể cho ra hai artifact khác nhau mà không có hợp đồng phát hành rõ ràng.

## 2. Tại sao duy trì hai JDK khó hơn việc chạy hai lệnh?

Một build hiện đại có nhiều tầng:

~~~text
Source code
    |
    v
Gradle/Maven process
    |
    +--> Build plugins
    |
    +--> javac
    |      |
    |      +--> Annotation processors
    |      +--> Generated sources
    |
    +--> Test launcher/JVM
    |      |
    |      +--> JUnit, Mockito, Byte Buddy, JaCoCo
    |
    +--> Packaging
    |      |
    |      +--> Shaded JAR, WAR, Docker, jlink image
    |
    v
Runtime / Container / Cloud
~~~

Mỗi tầng có support matrix riêng. Ví dụ:

- Gradle cũ có thể không khởi động trên JDK mới.
- Lombok cũ có thể phụ thuộc internal APIs của javac.
- Byte Buddy/JaCoCo cũ có thể chưa hỗ trợ class-file version mới.
- Một Maven plugin cũ có thể chỉ hoạt động với JVM baseline.
- Container image có thể dùng runtime khác với CI.
- Dependency transitively được nâng lên bytecode Java 21.
- Một generated class bị thiếu chỉ trên clean CI.
- Java agents, TLS providers hoặc JNI libraries không còn tương thích.

Do đó, khi một lane lỗi, cần phân loại đúng **build tool**, **compiler**, **processor**, **test runtime**, **packaging** hay **application runtime**, không gom mọi lỗi vào "JDK migration".

## 3. Thiết lập chính sách tương thích ngay từ đầu

Một support matrix cần ghi:

1. JDK baseline và target; vendor/distribution nếu cần.
2. Operating systems, CPU architectures và container runtimes được hỗ trợ.
3. Minimum Java version của artifact công bố.
4. Các module được yêu cầu hỗ trợ cả hai JDK.
5. Các module chỉ dành cho JDK mục tiêu.
6. Phiên bản Gradle/Maven, plugins, JUnit và processors.
7. CI jobs bắt buộc xanh ở mỗi mốc.
8. Thời hạn hỗ trợ JDK cũ.
9. Tiêu chí loại bỏ legacy lane.
10. Quy tắc rollback, security và hỗ trợ downstream consumers.

Ví dụ:

| Thuộc tính | Giai đoạn chuyển | Sau cutover |
|---|---|---|
| Min supported runtime | 17 | 21 |
| Source language level | 17 | 21 nếu được phê duyệt |
| Target release | 17 | 21 nếu được phê duyệt |
| Compiler JDK matrix | 17 và 21 | 21 |
| Runtime test matrix | 17 và 21 | 21 |
| Build tool/plugins | Phải hỗ trợ hai lane | Có thể nâng riêng theo support |
| New JDK-only API | Tránh trong shared code | Được phép sau cutover |
| Legacy support gate | Required | Đóng sau khi đủ bằng chứng |

Đây là một **quyết định sản phẩm**, không chỉ là chi tiết cấu hình DevOps. Với thư viện công khai, đổi minimum Java version có thể là breaking change.

### 3.1. Mức bảo đảm nên được đặt tên rõ

- **Compile-supported:** source biên dịch được trên JDK tương ứng.
- **Test-supported:** test suite quan trọng chạy được trên runtime đó.
- **Runtime-supported:** artifact được kiểm chứng khi triển khai vào môi trường đó.
- **Production-supported:** có support, monitoring, incident response và security updates.

Không công bố "supports Java 17 and 21" chỉ từ việc chạy một lệnh **javac**; phạm vi cụ thể phải rõ.

## 4. Hiểu đúng javac --release

Tùy chọn **javac --release N** là công cụ quan trọng giúp biên dịch source cho một Java SE release cũ bằng javac mới hơn.

Ví dụ chạy bằng javac 21:

~~~bash
javac --release 17 -d out src/example/Main.java
~~~

Nó điều khiển cú pháp source, các API Java SE có thể tham chiếu và class-file target theo release 17 trong phạm vi được javac hỗ trợ.

### 4.1. -source/-target không tương đương --release

Cấu hình:

~~~bash
javac -source 17 -target 17 -d out src/example/Main.java
~~~

giới hạn cú pháp và bytecode nhưng không tự cung cấp cùng mức bảo vệ khỏi việc tham chiếu API Java SE mới qua compiler JDK mới.

Với dự án cần duy trì runtime cũ, ưu tiên **--release 17** khi compiler và build tool hỗ trợ.

### 4.2. --release không bảo đảm mọi dependency bên ngoài

Ví dụ:

~~~text
app.jar             -> class file major 61
  |
  +--> common.jar   -> class file major 61
  |
  +--> extra.jar    -> class file major 65
~~~

Java 17 có thể nạp app.jar, nhưng khi đường code dùng extra.jar với class-file major 65, JVM Java 17 không hỗ trợ class đó.

| Java release | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Cần kiểm tra **runtime classpath/transitive dependencies** và artifact cuối, không chỉ bytecode của module chính.

### 4.3. --release không làm ứng dụng có hành vi giống nhau

Hai JDK vẫn có thể khác:

- GC/JIT và memory ergonomics.
- TLS, security providers và thuật toán bị vô hiệu hóa.
- Locale, timezone và charset behavior.
- Reflection, JPMS encapsulation.
- Garbage collector metrics.
- Runtime exception messages.
- Native libraries, Java agents.
- Framework/driver behavior dựa theo runtime version.

**Build xanh dưới --release 17 không thay test runtime bằng Java 17 thật.**

### 4.4. Khi nào không thể giữ --release 17?

Nếu shared source dùng API chỉ có trong Java 21 hoặc syntax mới, có các lựa chọn:

1. Hoãn feature đó cho đến khi kết thúc support Java 17.
2. Cô lập vào module/variant chỉ dùng Java 21.
3. Dùng abstraction và implementation được chọn theo runtime, với đóng gói đúng target.
4. Dùng multi-release JAR nếu phù hợp và đủ nguồn lực testing.

Không sửa thủ công major class-file version để buộc class Java 21 chạy trên Java 17.

## 5. Gradle Toolchains cho hai JDK

**Java Toolchains** của Gradle giúp chọn compiler và runtime launcher cho các task phù hợp, tách chúng khỏi JVM chạy Gradle daemon.

Ví dụ Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

def buildJdk = providers.gradleProperty('buildJdk')
    .map { it.toInteger() }
    .orElse(17)
    .get()

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(buildJdk)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(buildJdk)
    }
}
~~~

Ý nghĩa:

- **buildJdk** chọn toolchain được dùng.
- **options.release = 17** giữ API/language target Java 17.
- **Test.javaLauncher** chọn runtime tương ứng để chạy test.
- Gradle daemon có thể chạy trên JVM khác nếu Gradle version hỗ trợ.
- Toolchain phải có sẵn hoặc được cấu hình cơ chế provisioning phù hợp.

Chạy minh họa:

~~~bash
./gradlew clean test -PbuildJdk=17
./gradlew clean test -PbuildJdk=21
~~~

Trên Windows sử dụng **gradlew.bat**. Đường command chỉ minh họa workflow cho dự án thật.

### 5.1. Không nhầm Gradle JVM và Java toolchain

Các lệnh có ích:

~~~bash
java -version
javac -version
./gradlew -version
./gradlew javaToolchains
~~~

**java -version** trong shell và **./gradlew -version** không chứng minh compiler được chọn cho một task cụ thể.

Trong integration tests có thể in:

~~~java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
~~~

In ngay trong đúng process test giúp xác nhận lane đã dùng runtime được công bố.

### 5.2. Toolchain không giúp Gradle cũ tự chạy trên JDK mới

Một Gradle release có thể hỗ trợ Java 21 như compiler toolchain nhưng có yêu cầu khác để chạy chính Gradle daemon trên Java 21. Cần đọc Gradle compatibility matrix theo version của wrapper thực tế.

Plugin khác như Spring Boot, Kotlin, Shadow hay codegen cũng có compatibility riêng.

### 5.3. Cấu hình Kotlin DSL

Nếu repository dùng **build.gradle.kts**, một biến thể:

~~~kotlin
plugins {
    java
}

val buildJdk = providers.gradleProperty("buildJdk")
    .map(String::toInt)
    .orElse(17)
    .get()

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(buildJdk))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(buildJdk))
    })
}
~~~

Không cần duy trì cả Groovy và Kotlin DSL trong cùng dự án. Chọn cú pháp theo build hiện tại và Gradle version đang hỗ trợ.

## 6. Gradle main source, test source và generated code

Một dự án có thể có các source sets:

~~~text
src/main/java
src/test/java
src/integrationTest/java
build/generated/sources/annotationProcessor/java/main
build/generated/sources/annotationProcessor/java/test
~~~

Hai JDK có thể khác nhau ở annotation processing, compilation và test launchers. Khi thêm integrationTest source set, phải xác nhận launcher/configuration riêng cho task đó.

### 6.1. Cẩn trọng với annotationProcessor

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    annotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'

    testCompileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    testAnnotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
}
~~~

Placeholder phải được thay bằng release processor thực sự hỗ trợ compiler JDK cần sử dụng.

Đặt một processor chỉ trong **implementation** không phải cấu hình chắc chắn để nó chạy trong Gradle. Khi chạy javac từ **JDK 23**, annotation processing cũng có thay đổi mặc định: không được dựa vào phát hiện ngầm từ classpath khi thiếu cấu hình processing tường minh.

### 6.2. Không dùng một output directory cho hai build cùng lúc

Hai lệnh Gradle chạy đồng thời trong cùng workspace có thể cạnh tranh ghi:

~~~text
build/classes/java/main
build/classes/java/test
build/generated/sources/annotationProcessor/java/main
build/test-results/test
~~~

Cách an toàn hơn: mỗi lane CI có workspace hoặc output riêng; sử dụng build cache đúng cơ chế và tránh chia sẻ thư mục writable.

### 6.3. Clean build vẫn quan trọng

Một processor không chạy nhưng generated class từ build trước còn tồn tại có thể khiến local build xanh. CI clean checkout có thể lỗi vì thiếu class.

Để chứng minh compatibility, ít nhất một verification path phải tạo output từ trạng thái sạch và có provenance rõ, không dựa vào generated artifact stale.

## 7. Maven: biên dịch cùng target bằng hai JDK

Với Maven, cách đơn giản là chạy **mvn clean verify** trong hai CI jobs có **JAVA_HOME** khác nhau.

Ví dụ **pom.xml**:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Các version là ví dụ về cú pháp cấu hình. Cần kiểm tra ma trận hỗ trợ thực tế của Maven, Compiler Plugin và Surefire theo JDK.

Mỗi lane:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
~~~

Một job dùng JDK 17, job còn lại dùng JDK 21. Việc ghi version ngay trong CI logs giúp điều tra nếu test chạy trên JVM khác mong đợi.

### 7.1. Maven Toolchains

Maven Toolchains hỗ trợ lựa chọn JDK mà các plugins có tích hợp toolchain sẽ sử dụng, khác với JVM chạy chính Maven.

Ví dụ cấu hình trong **~/.m2/toolchains.xml**:

~~~xml
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Đường dẫn chỉ là minh họa Unix; Windows hoặc container có đường dẫn khác.

Điều quan trọng: **không phải mọi Maven plugin đều tự tuân theo compiler toolchain**. Cần kiểm tra compiler, Surefire/Failsafe, generated code và các subprocess khác theo plugin versions.

### 7.2. Một build chạy Maven 21 và compile 17 chưa chứng minh runtime 17

Nếu Maven process chạy JDK 21, compiler toolchain tạo bytecode target17 nhưng Surefire vẫn chạy dưới JDK21, lane có thể bỏ sót lỗi runtime17.

Cần test JVM riêng đúng với support policy. Trong nhiều trường hợp, hai CI jobs chạy Maven bằng JDK17 và JDK21 là cách dễ quan sát hơn.

### 7.3. Plugins mới có minimum Java riêng

Một bản Maven/Gradle plugin mới có thể yêu cầu JVM cao hơn JDK baseline. Trong giai đoạn coexist, có thể:

- Chọn plugin version hỗ trợ cả hai môi trường.
- Dùng build JVM mới và toolchains cho compiler/test cũ.
- Tách build variants có quy tắc rõ.
- Lên kế hoạch đóng support baseline nếu không thể duy trì.

Không bỏ qua plugin quan trọng ở lane17 rồi gọi đó là "build thành công" nếu artifact release thật phải sử dụng plugin ấy.

## 8. CI matrix bằng GitHub Actions

Một ví dụ hai lane độc lập:

~~~yaml
name: Java JDK compatibility

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21']

    steps:
      - uses: actions/checkout@v4

      - name: Select JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Show Java versions
        run: |
          java -version
          ./gradlew -version

      - name: Test
        run: ./gradlew clean test -PbuildJdk=${{ matrix.java }}
~~~

Giá trị JDK trong matrix phải được truyền vào action và Gradle property theo cú pháp CI. Trong bản trình bày đã sinh, hai vị trí đó sử dụng expression của GitHub Actions.

**Lưu ý:** action versions ở đây minh họa cấu trúc workflow. Với production CI nên tuân thủ chính sách pin/verify third-party actions và kiểm tra chính JDK distribution được hỗ trợ.

### 8.1. fail-fast: false

Khi một lane lỗi, **fail-fast: false** cho phép job khác tiếp tục, giúp quan sát tình trạng của cả baseline lẫn target. Điều này có giá trị trong migration: biết cả Java17 pass/Java21 fail khác với việc hai jobs đều không hoàn thành.

### 8.2. Jenkins, GitLab, Azure DevOps

Không nhất thiết dùng GitHub Actions. Các công cụ CI khác có thể tạo cùng một JDK matrix:

- Một build job mỗi JDK.
- Workspace riêng.
- JDK toolchain rõ.
- Cùng commit/dependency locks.
- Test suite được xác định.
- Artifacts được đặt nhãn.
- Kết quả từng lane thành release gate.
- Log ghi JDK thực sự được dùng.

### 8.3. Nhịp chạy hợp lý

| Thời điểm | JDK cũ | JDK mới | Mục tiêu |
|---|---|---|---|
| Pull request | Compile + unit smoke | Compile + unit smoke | Phát hiện sớm regression |
| Merge/main | Full tests phù hợp | Full tests phù hợp | Giữ tương thích liên tục |
| Nightly | Integration/long-running | Integration/long-running | Kiểm tra toàn diện hơn |
| Release candidate | Packaged runtime smoke | Packaged runtime smoke | Kiểm chứng artifact cuối |
| Canary deployment | Nếu vẫn trong hỗ trợ | Runtime mới | SLO và observability |
| Sau cutover | Theo policy mới | Required | Đóng cửa sổ hỗ trợ |

Một lane không bắt buộc xanh cần có owner và deadline, không thể tồn tại như "optional" vô thời hạn trong khi tài liệu sản phẩm vẫn công bố hỗ trợ JDK đó.

## 9. Kiểm thử chéo compiler và runtime

Hai lane thông thường:

~~~text
javac17 -> runtime17
javac21 -> runtime21
~~~

chưa đủ chứng minh một artifact được build bằng javac21 với **--release 17** có thể chạy trên Java17.

Nếu yêu cầu một artifact cho cả hai runtimes, cân nhắc ma trận:

| Compiler | --release | Test runtime | Mục tiêu |
|---|---|---|---|
| JDK17 | 17 | JDK17 | Baseline compile/runtime |
| JDK21 | 17 | JDK21 | Compiler mới và runtime mới |
| JDK21 | 17 | JDK17 | Artifact mới chạy trên baseline |
| JDK17 | 17 | JDK21 | Artifact baseline chạy trên target |

Không cần chạy mọi tổ hợp ở mọi pull request, nhưng phải biết tổ hợp nào thật sự được test và tổ hợp nào chỉ là giả định.

### 9.1. Lợi ích của bài test JDK21 compile → JDK17 runtime

Nó có thể phát hiện:

- Transitive library được biên dịch bằng Java21.
- Resource hoặc service provider khác biệt.
- Generated source/class sử dụng API không phù hợp.
- Runtime reflection/serialization assumption.
- Packaging bị đưa vào một class version cao hơn.

Nếu lớp class-file major65 nằm trong artifact target17 và được tải ở runtime17, lỗi có thể xuất hiện dù source project dùng **--release 17**.

### 9.2. Artifact nào được chọn để phát hành?

CI có thể tạo:

~~~text
build-17/app.jar
build-21/app.jar
~~~

Nếu chiến lược là **một artifact**, chỉ một path được đưa vào release và phải được test trên các runtime cần hỗ trợ. Không để pipeline tùy vào job chạy cuối mà publish file cùng tên từ compiler khác.

### 9.3. Một build còn thể chạy trên JDK cũ nhưng không còn backward data compatible

Ứng dụng Java17 có thể đọc class file Java17 nhưng không hiểu message/event mới do ứng dụng Java21 ghi. Build matrix phải được kết hợp với **cross-version protocol tests** nếu hai phiên bản đang cùng truy cập database, queue hoặc cache.

## 10. Quản lý dependencies theo minimum runtime

Một thư viện có thể nâng major/minor release và thay minimum JDK. Cần khảo sát:

- Direct dependencies.
- Transitive dependencies.
- Test-only dependencies.
- Annotation processors.
- Maven/Gradle plugins.
- Runtime agents.
- Native/JNI libraries.
- Shaded/fat JAR contents.
- Platform-specific variants.

### 10.1. Ví dụ dependency thay đổi minimum JDK

~~~text
Before:
  core-lib 1.x -> supports Java 17

After:
  core-lib 2.x -> requires Java 21
~~~

Nếu một artifact shared vẫn cần chạy trên Java17, không thể chỉ nâng core-lib rồi giữ project **--release 17** và coi mọi thứ an toàn.

Một số hướng xử lý:

1. Chọn version thư viện còn hỗ trợ cả hai JDK.
2. Tách phần Java21-only khỏi shared artifact.
3. Dùng adapter hoặc variant.
4. Đổi support policy sau khi consumer cũ được chuyển.
5. Kiểm tra dependency lock và bytecode của artifact đã đóng gói.

### 10.2. Resolve graph có thể khác nhau giữa lanes

Build tools có thể chọn dependency variants dựa trên metadata, attributes hoặc platform. Hai lane cùng dùng một source code nhưng resolve khác artifacts.

Cần lưu dependency graph cho từng lane khi troubleshooting. Nếu khác biệt là chủ đích, ghi trong release policy; nếu không, xử lý để build tái lập.

### 10.3. Multi-release JAR ở dependency

Một số thư viện là multi-release JAR: runtime JDK khác nhau có thể load implementation khác nhau từ cùng file. Điều này giúp tối ưu theo version, nhưng có nghĩa **cùng checksum JAR không bảo đảm cùng đường thực thi**.

Cần test trên runtime thật, đặc biệt nếu dependency dùng native access, reflection hoặc APIs mới.

## 11. Annotation processors: một điểm dễ gãy khi nâng compiler

Các công cụ thường gặp:

- Lombok.
- MapStruct.
- JPA metamodel/Hibernate Processor.
- Dagger và dependency injection processors.
- AutoValue, Immutables hoặc generator nội bộ.
- QueryDSL và các generator dùng annotation processing.

Processor chạy trong quá trình compile, khác với runtime library.

### 11.1. Cấu hình processor path rõ ràng

Gradle:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    annotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'

    testCompileOnly 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
    testAnnotationProcessor 'org.projectlombok:lombok:VERSION_DUOC_HO_TRO'
}
~~~

Placeholder phải thay bằng version thực, phù hợp JDK compiler đang dùng.

### 11.2. Từ JDK 23 cần chú ý activation mặc định

Javac từ JDK23 không tự động bật annotation processing khi không có cấu hình processing thích hợp. Nếu một build legacy dựa vào việc quét classpath ngầm, generated classes có thể biến mất sau khi compiler được nâng.

Giải pháp: cấu hình processor path/danh sách processor tường minh theo build tool, thay vì dựa vào service file có mặt tình cờ ở dependency classpath.

### 11.3. JDK chạy processor không phải --release

**javac21 --release17** vẫn chạy processor bằng môi trường compiler JDK21. Một Lombok version chỉ biết javac17 internals có thể lỗi dù target bytecode17.

Trong migration nên:

- Chọn processor version hỗ trợ cả compiler17/21.
- Không nhầm **javax.annotation.processing** với Jakarta Persistence namespace.
- Kiểm tra processor classpath/module path.
- Clean build để loại generated artifacts stale.
- Xác nhận implementation được sinh ra ở cả hai lane.
- Không xem workaround mở **jdk.compiler** internals là giải pháp lâu dài.

### 11.4. Test source cũng cần processor

Nếu code test dùng Lombok hoặc generated test fixtures, phải cấu hình **testAnnotationProcessor** tương ứng. Main compile xanh không chứng minh test compile cũng có annotation processing.

## 12. Test agents, coverage và bytecode tools

Một bản JDK mới có thể khiến testing pipeline lỗi ở những công cụ xử lý bytecode, không phải source Java.

| Công cụ | Rủi ro khi đổi JDK |
|---|---|
| Mockito | Mock maker/inline instrumentation/agent compatibility |
| Byte Buddy | Version class-file, runtime instrumentation |
| JaCoCo | Coverage engine chưa hiểu bytecode mới |
| JUnit engine/launcher | Mismatch plugin hoặc discovery |
| PowerMock/legacy mocking | Dựa vào class loaders và JDK internals |
| Java agents/APM | Attach, bytecode transform, module access |
| Testcontainers | Container engine/JDK/image/runtime config |
| JNI/native test libraries | OS architecture, binary dependencies |

### 12.1. Một lỗi classfile không nhất thiết là lỗi source

Nếu stack trace nói công cụ coverage không xử lý được major class-file version mới, cần nâng đúng coverage tool/ASM dependency. Thêm **--add-opens** không tự sửa parser bytecode cũ.

### 12.2. Test execution khác test compile

Một ứng dụng có thể compile Java17 trên cả hai toolchain nhưng test ở Java21 gặp:

- Module encapsulation.
- TLS/security provider behavior.
- Reflection exception khác.
- Deprecated/removed runtime feature.
- Thay đổi default GC hoặc charset.
- Library hỗ trợ Java17 nhưng không hỗ trợ Java21.

Phân biệt lỗi do tool với lỗi do behavior của application bằng stack trace và tests đại diện.

## 13. Cache, generated output và build reproducibility

Chạy hai build song song cần quản lý trạng thái output và cache cẩn thận.

### 13.1. Các nguyên nhân kết quả không đáng tin

- Hai lane ghi cùng thư mục **build/** hoặc **target/**.
- Cache key không phản ánh JDK/toolchain.
- Generated code còn từ build trước.
- Một plugin tạo artifact chứa timestamp/random metadata.
- Dependency không được pin/lock nên hai lần build resolve khác nhau.
- Test tải dữ liệu bên ngoài không được kiểm soát.
- Maven local repository bị thay artifact snapshot trong lúc chạy.
- Một task tự đọc biến môi trường nhưng không khai báo là input.

### 13.2. Tách workspace/outputs

Ưu tiên mỗi CI matrix job chạy trong workspace riêng. Chia sẻ **read-only dependency caches** hoặc cache qua build tool có cơ chế kiểm soát phù hợp là khác với việc hai invocations ghi cùng generated/class output.

### 13.3. Byte-for-byte reproducibility khác behavioral compatibility

Hai JDK compilers có thể sinh class/JAR khác byte-level dù cùng **--release17**. Khác biệt hash chưa chứng minh behavior sai.

Cần tách mục tiêu:

- **Reproducible build:** cùng input/toolchain đã xác định tạo artifact giống nhau theo tiêu chuẩn dự án.
- **Cross-JDK compatibility:** artifact giữ API/behavior và chạy trên các runtime được hỗ trợ.
- **Supply-chain integrity:** artifact có provenance, dependency checksums và nguồn đáng tin.

Không yêu cầu byte-identical output giữa hai JDK nếu chưa có thiết kế và lý do rõ.

## 14. Một artifact, hai variants hay multi-release JAR?

### 14.1. Một artifact Java17 target

Ưu điểm:

- Consumer dùng cùng Maven/Gradle coordinates.
- Ít biến thể và ít nhầm lẫn khi deploy.
- Dễ quản lý version/SBOM.
- Có thể thử trên cả Java17 và Java21.

Hạn chế:

- Không thể dùng trực tiếp APIs Java21 trong shared code.
- Transitive dependencies phải hỗ trợ Java17.
- Không khai thác một số feature mới nếu chưa cô lập.

### 14.2. Hai artifacts

Ví dụ:

~~~text
my-lib-2.0-java17.jar
my-lib-2.0-java21.jar
~~~

Đặt tên minh họa; trong repository thực tế có thể dùng classifier hoặc artifact coordinates khác.

Cần công bố:

- Variant naming và selection.
- Minimum JDK mỗi artifact.
- Binary/public API compatibility giữa variants.
- Dependency graph khác nhau.
- Chính sách backport/security.
- CI tests riêng.
- Release notes và cách consumer migrate.

Đừng phát hành hai artifact có nội dung khác nhau vào cùng identity/version mà không có cách phân biệt.

### 14.3. Multi-release JAR

**Multi-release JAR** cho phép cùng JAR chứa class versioned cho JVM khác nhau:

~~~text
library.jar
  META-INF/MANIFEST.MF
  com/example/Feature.class
  META-INF/versions/21/com/example/Feature.class
~~~

Manifest cần:

~~~text
Multi-Release: true
~~~

Base classes cần tương thích Java17; Java21 có thể sử dụng implementation version21 theo quy tắc của MRJAR.

Nhưng MRJAR tăng độ phức tạp:

- Packaging và compiler targets khác nhau.
- Public API consistency.
- Static analysis và codegen.
- Classloading/reflective behavior.
- Dependency compatibility.
- Tests trên từng runtime thực.

Chỉ dùng khi có lý do kỹ thuật rõ và đủ khả năng duy trì.

## 15. Container deployment và runtime images

CI có thể compile Java17 nhưng đóng gói artifact vào Docker image Java21. Hai điều đó khác nhau.

Ví dụ runtime Java17:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ cho Java21 thay base image bằng một bản runtime21 được kiểm soát.

Trong production, nên quản lý base image bằng version/digest và policy cập nhật bảo mật, không chỉ dựa vào floating tags.

### 15.1. Kiểm thử artifact cuối trong image thật

Các bước:

1. Build artifact theo release policy.
2. Đóng gói đúng runtime image.
3. Khởi động container.
4. Xác nhận **java.version** trong process.
5. Chạy health/smoke/integration tests.
6. Kiểm tra agents, JVM flags và module availability.
7. Kiểm tra CPU/memory cgroups và GC.
8. Lưu artifact/image digest làm evidence.

**java -version** của CI host không chứng minh runtime Java trong container.

### 15.2. Jlink image tối giản

Một custom image tạo bằng **jlink** có thể thiếu module mà full JDK trên máy developer có. Khi migration, test bằng runtime image cuối thay vì chỉ test bằng full JDK.

Điều này quan trọng với reflection, XML, management, JFR hoặc những thành phần dựa vào module cụ thể.

## 16. Runtime behavior: JDK mới có thể làm test đổi kết quả

Một project target Java17 có thể không cho kết quả giống hệt trên Java17 và Java21.

### 16.1. Security và TLS

Kiểm tra HTTPS/mTLS, truststore, JDBC TLS và các đối tác sử dụng ciphers cũ. Nâng JDK có thể thay supported algorithms hoặc security defaults.

Không nới TLS/security policy tùy tiện chỉ để CI target xanh; phân loại xem đó là thay đổi chủ đích và tác động thực tế.

### 16.2. Locale/charset/timezone

Đừng để test phụ thuộc default locale, timezone hoặc charset khi business contract yêu cầu giá trị xác định.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.util.Locale;

var charset = StandardCharsets.UTF_8;
var zone = ZoneId.of("UTC");
var locale = Locale.ROOT;
~~~

Code sử dụng lựa chọn tường minh khi phù hợp sẽ giảm nhiễu giữa hai lane.

### 16.3. GC/JIT/performance

Không so sánh raw GC counts giữa hai JDK/collectors rồi kết luận ứng dụng tốt hay xấu. Kiểm tra latency p95/p99, throughput, CPU, heap và business SLO trên workload tương đương.

### 16.4. Native/JNI và profiler

Một application target Java17 có thể vẫn lỗi trên runtime21 do JNI library/Java agent không tương thích. Cần inventory và test các binaries/agents đi cùng artifact, không chỉ JAR Java.

## 17. Schema và giao thức khi hai runtime cùng vận hành

Song song build thường phục vụ một **rolling migration**:

~~~text
App A / JDK 17 ------+
                     |
                     +--> Shared DB / Queue / Cache
                     |
App B / JDK 21 ------+
~~~

Cả hai có thể tạo/đọc dữ liệu trong cùng hệ thống.

Câu hỏi bắt buộc:

- ORM entities có tương thích schema chung?
- JSON serializer mới có bỏ field consumer cũ cần?
- Producer B có gửi enum value A không hiểu?
- Message cũ trong queue có được consumer B đọc?
- New writer ghi dữ liệu khiến old reader không parse?
- Rollback về App A có còn an toàn không?
- Code B có sử dụng API mới nhưng giữ giao thức cũ không?

Nếu cần đổi schema, áp dụng **expand-before-contract**: thêm cấu trúc mới, duy trì read/write compatibility, backfill và đối soát, rồi chỉ xóa phần cũ sau khi không còn consumer cần nó.

**Build matrix không thay thế cross-version data compatibility tests.**

## 18. Ma trận test theo rủi ro

Một test plan có thể gồm:

| Test layer | Java17 | Java21 | Lý do |
|---|---|---|---|
| Compile main source | Có | Có | Compiler/toolchain |
| Compile test source | Có | Có | Test code/APT |
| Unit tests | Có | Có | Behavioral regression |
| Integration DB/ORM | Có | Có | Driver, runtime behavior |
| HTTP/JSON contract | Có | Có | Serializer/protocol compatibility |
| Messaging | Có | Có | Old/new payload |
| Final artifact smoke | Có | Có | Runtime classpath và packaging |
| Agent/coverage | Có | Có | Bytecode instrumentation |
| Container smoke | Theo support | Theo support | Image/runtime thực |
| Performance baseline | Khi cần | Khi cần | SLO sau migration |
| Cross-version producer/consumer | Có | Có | Coexist |
| Consumer precompiled artifact | Nếu cần | Nếu cần | Binary compatibility |

Không cần chạy mọi bài stress test ở mọi PR, nhưng mỗi khả năng được công bố hỗ trợ phải có test và release gate tương ứng.

### 18.1. Contract tests với consumer chưa rebuild

Với thư viện dùng chung, một consumer đã biên dịch từ trước có thể gặp **NoSuchMethodError** hoặc **IllegalAccessError** khi thay library. Build source library trên hai JDK không phát hiện toàn bộ lỗi đó.

Nếu cần bảo vệ binary compatibility, giữ một consumer artifact cũ và chạy nó với library mới trong các runtime được hỗ trợ.

### 18.2. Tests có flaky behavior

JDK khác có thể thay scheduling/timing, làm lộ data races hoặc test phụ thuộc timeouts cứng.

Không giải quyết bằng cách tắt test flaky bừa bãi. Cần phân tích concurrency assumptions, test isolation, external dependencies và thời gian chờ theo môi trường.

## 19. Khi một lane đỏ: điều tra theo thứ tự

| Triệu chứng | Khả năng nguyên nhân | Cần kiểm tra |
|---|---|---|
| Gradle daemon không khởi động | Gradle release không hỗ trợ JDK | Gradle/JDK matrix |
| Maven plugin thất bại | Plugin minimum JVM không phù hợp | Maven JVM, plugin version |
| Compilation lỗi Java API | Source dùng API ngoài --release | Source level, API baseline |
| UnsupportedClassVersionError | Dependency/class major mới hơn runtime | Runtime classpath |
| Generated mapper biến mất | Processor path/activation | Clean build/APT config |
| IllegalAccessError trong Lombok | Internal javac API thay | Processor/JDK versions |
| Mockito/JaCoCo fail | Bytecode/agent support | Test tool versions |
| InaccessibleObjectException | Reflection/JPMS | Module/package/caller |
| Test lỗi trên Java17 nhưng pass Java21 | Dependency/runtime yêu cầu mới | Bytecode/API và integration |
| Test lỗi trên Java21 nhưng pass Java17 | Runtime behavior hoặc framework cũ | Cause chain |
| CI pass nhưng container fail | Image JDK/module/agent khác | Container inspect |
| Local pass, CI clean fail | Stale build outputs/cache | Generated files, cache isolation |
| JSON differences | Serializer/framework behavior | Contract/golden payload |

Quy trình:

1. Ghi lane/commit và build artifact.
2. Xác minh build JVM, compiler JDK, test JVM.
3. Xác định giai đoạn thất bại.
4. Xem stack trace để tìm component chủ sở hữu lỗi.
5. Kiểm tra compile flags, dependency resolution và processors.
6. Kiểm tra cache/output sạch.
7. Kiểm tra runtime image/agents.
8. Sửa đúng tầng.
9. Chạy lại các lane bị ảnh hưởng.
10. Ghi evidence và residual risk.

Không bỏ một lane chỉ vì lane mới đã xanh. Quyết định bỏ hỗ trợ cần một release gate độc lập.

## 20. Release gates trong quá trình chuyển đổi

### Gate M0 — Baseline

- JDK cũ và build tool versions rõ.
- Dependency/processor/test agents được kiểm kê.
- Artifact đang triển khai có checksum/provenance.
- Test baseline tái hiện được.
- Có tài liệu support policy.

**Go:** baseline đủ rõ để so sánh.

### Gate M1 — Build tool readiness

- Gradle/Maven và plugins chạy được theo kế hoạch.
- Có compiler/toolchain target.
- Không còn plugin chặn JDK mới.
- Đã xử lý processor/compiler internals chủ yếu.

**Go:** hạ tầng có thể chạy hai lane.

### Gate M2 — CI matrix

- Hai lane independent.
- Build flags/source/API targets đúng.
- Test runtimes xác minh.
- Clean generated outputs.
- Dependency graph và caches được kiểm soát.
- Results của hai lane hiển thị rõ.

**Go:** có tín hiệu tin cậy cho cả JDK cũ/mới.

### Gate M3 — Runtime compatibility

- Packaged artifact được thử trên runtime cần hỗ trợ.
- Integration/contract tests đạt.
- Agents/TLS/native dependencies được kiểm tra.
- Observability và SLO baseline sẵn sàng.
- Có rollback plan.

**Go:** bản phát hành sẵn sàng canary.

### Gate M4 — Coexist/rollout

- App cũ và mới có thể cùng đọc/ghi dữ liệu cần thiết.
- Không có schema/protocol breaking trong overlap window.
- Canary metrics và error rate ổn định.
- Có incident owner và runbook.
- Rollback được kiểm chứng trong phạm vi còn hợp lệ.

**Go:** chuyển lưu lượng mà không bỏ mất khả năng hỗ trợ phiên bản cũ.

### Gate M5 — Kết thúc support JDK cũ

- Không còn runtime/client được hỗ trợ cần baseline.
- Batch, jobs và recovery tooling đã nâng.
- Consumer owners xác nhận.
- Rollback window cũ đã đóng hoặc đã có phương án khác.
- Tài liệu minimum Java version đã cập nhật.
- Team release phê duyệt.

**Go:** được bỏ legacy build lane và nâng target release nếu cần.

## 21. Khi nào không nên duy trì hai build quá lâu?

Build song song có chi phí:

- Gấp đôi hoặc tăng đáng kể CI compute.
- Dependency phải giữ version hỗ trợ JDK cũ.
- Chậm dùng tính năng Java mới.
- Khó nâng plugin/test tools.
- Tăng số cấu hình cần bảo trì.
- Dễ khác kết quả giữa compiler/runtime.
- Có nguy cơ một lane bị bỏ mặc.

Vì vậy cần có **ngày và điều kiện kết thúc**. Không duy trì vô thời hạn chỉ vì "an toàn hơn", nhưng cũng không cắt sớm khi vẫn có consumer được công bố hỗ trợ.

### 21.1. Mẫu quyết định đóng baseline

~~~text
Gate: DROP_JDK_17_SUPPORT

[ ] No supported production JVMs on JDK 17
[ ] No library consumers require Java 17
[ ] Batch/recovery tools migrated
[ ] Rollback window closed or alternative approved
[ ] Build plugins/agents support new baseline
[ ] Target runtime SLO accepted
[ ] Release notes and API docs updated
[ ] Consumer owners signed off

Decision: GO / NO-GO / PENDING
Owner:
Evidence:
Date:
~~~

**PENDING không đồng nghĩa GO.** Nếu thư viện công khai từng cam kết Java17, nâng minimum runtime lên Java21 cần được công bố như thay đổi có thể phá vỡ consumer.

## 22. Các sai lầm thường gặp

### 22.1. Chỉ đổi JAVA_HOME

Một task Gradle dùng toolchain khác hoặc container dùng JDK khác. **Giải pháp:** xác minh từng process/compiler/test runtime.

### 22.2. Dùng -target17 thay cho --release17

Code có thể tham chiếu Java API mới hơn target. **Giải pháp:** dùng --release khi phù hợp và kiểm tra dependency APIs.

### 22.3. Chỉ compile bằng JDK21

Không có bằng chứng runtime Java17 vẫn chạy được. **Giải pháp:** chạy artifact trên Java17 thực.

### 22.4. Dùng API Java21 trong shared code khi còn hỗ trợ Java17

Source không compile hoặc runtime không hỗ trợ. **Giải pháp:** hoãn, cô lập variant hoặc thiết kế abstraction.

### 22.5. Nâng test agent quá muộn

Mockito/Byte Buddy/JaCoCo cũ có thể không hỗ trợ classfile mới. **Giải pháp:** kiểm tra tool matrix trước khi nâng JDK.

### 22.6. Không khai báo annotation processor rõ

Processor có thể không chạy trên compiler mới. **Giải pháp:** explicit processor path, nâng version và clean build.

### 22.7. Trộn output hai JDK

Generated files/classes bị ghi đè. **Giải pháp:** workspace và output riêng, cache isolation.

### 22.8. Đòi hash hai JDK phải giống nhau

Một build vẫn có thể đúng hành vi nhưng artifact khác byte-level. **Giải pháp:** phân biệt reproducibility và compatibility, chốt artifact release cụ thể.

### 22.9. Bỏ qua runtime image

Host CI JDK17 nhưng Docker image JDK21 hoặc ngược lại. **Giải pháp:** test image cuối.

### 22.10. Để legacy lane optional mãi

Regression có thể tồn tại nhiều tuần mà không chặn release. **Giải pháp:** required checks hoặc ngoại lệ có owner/deadline.

### 22.11. Bỏ quên cross-version data contracts

Hai ứng dụng Java khác JDK cùng ghi database/queue nhưng không hiểu schema nhau. **Giải pháp:** test producer/consumer matrix và expand-and-contract.

### 22.12. Xóa lane cũ khi canary mới chạy tốt

Vẫn có batch, SDK clients hoặc rollback cần JDK cũ. **Giải pháp:** đóng legacy lane bằng evidence và phê duyệt.

## 23. Mẫu báo cáo tương thích cho một release

~~~text
Release:
Commit:
Build system + version:
Baseline JDK:
Target JDK:
Minimum supported runtime:
Source/API target:
Artifacts published:

Lane 17:
  Build JVM:
  Compiler JDK:
  Test JVM:
  Compile:
  Unit tests:
  Integration tests:
  Package:
  Runtime smoke:
  Known deviations:

Lane 21:
  Build JVM:
  Compiler JDK:
  Test JVM:
  Compile:
  Unit tests:
  Integration tests:
  Package:
  Runtime smoke:
  Known deviations:

Cross-runtime artifact tests:
Dependency/processor compatibility:
Java agents/native libraries:
Container images:
Data/protocol compatibility:
Observability/SLO:
Rollback plan:
Release gate:
Owner approvals:
Evidence links:
~~~

Một báo cáo như vậy giúp tách lỗi kỹ thuật khỏi quyết định business về phạm vi hỗ trợ, đồng thời tạo chứng cứ để chính thức ngừng JDK baseline.

## 24. Checklist hoàn tất

### Chính sách và kiến trúc

- [ ] Đã chốt baseline/target JDK và minimum supported runtime.
- [ ] Đã chọn một artifact hay các variants.
- [ ] Đã xác định module nào nằm trong phạm vi dual-JDK.
- [ ] Có owner và điều kiện kết thúc coexist.
- [ ] Có release/rollback policy.

### Build và dependencies

- [ ] Gradle/Maven versions hỗ trợ matrix thực tế.
- [ ] JDK compiler/test runtime được chọn rõ.
- [ ] --release và API target phù hợp baseline.
- [ ] Dependency bytecode/runtime support đã kiểm tra.
- [ ] Processors được khai báo explicit.
- [ ] Generated output không stale.
- [ ] Plugin và build tool minimum JDK không phá baseline.
- [ ] Không chia sẻ writable output giữa lane.

### Testing và phát hành

- [ ] CI chạy cả hai lane với labels và logs rõ.
- [ ] Required checks tương ứng support policy.
- [ ] Unit/integration/contract tests phù hợp từng runtime.
- [ ] Có cross-runtime test nếu phát hành một artifact.
- [ ] Packaged JAR/container được chạy thật trên baseline và target.
- [ ] Mockito/Byte Buddy/JaCoCo/agents tương thích.
- [ ] TLS, native libraries, JPMS và framework behavior đã được cân nhắc.
- [ ] Artifacts có provenance/versioning rõ, không bị publish nhầm.
- [ ] Có canary, metrics, rollback và release evidence.

### Kết thúc migration

- [ ] Không còn consumer/batch/recovery cần JDK cũ.
- [ ] Data/protocol contracts vẫn được hỗ trợ đúng phạm vi.
- [ ] Support docs và release notes đã cập nhật.
- [ ] Từng owner đã phê duyệt việc đóng legacy lane.
- [ ] Target release/API baseline chỉ được nâng sau gate chính thức.

## 25. Tài liệu đối chiếu

Khi triển khai vào dự án thực tế, đối chiếu với tài liệu của đúng JDK và công cụ:

- **javac --release:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java class-file format:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **Gradle Java Toolchains:** https://docs.gradle.org/current/userguide/toolchains.html
- **Gradle Java Compatibility:** https://docs.gradle.org/current/userguide/compatibility.html
- **Maven Compiler Plugin:** https://maven.apache.org/plugins/maven-compiler-plugin/
- **Maven Toolchains Plugin:** https://maven.apache.org/plugins/maven-toolchains-plugin/
- **Maven Surefire Plugin:** https://maven.apache.org/surefire/maven-surefire-plugin/
- **Maven Failsafe Plugin:** https://maven.apache.org/surefire/maven-failsafe-plugin/
- **JDK 23 javac / annotation processing:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **JEP 238 — Multi-Release JAR Files:** https://openjdk.org/jeps/238
- **GitHub Actions setup-java:** https://github.com/actions/setup-java
- **Java Migration Guide:** https://docs.oracle.com/en/java/javase/21/migrate/

Tool support và plugin behavior có thể thay đổi theo release. Không copy một version minh họa vào production mà chưa xác nhận support matrix và chính sách security của dự án.

---

**Kết luận:** Duy trì khả năng build song song trên JDK cũ và mới là một **hợp đồng tương thích được kiểm chứng thường xuyên**. Phải tách rõ build JVM, compiler JDK, Java API/bytecode target, test runtime và runtime triển khai. Cấu hình toolchains và CI matrix độc lập, dùng **--release** đúng chỗ, kiểm tra dependency/annotation processor/agents, không để generated output hoặc cache che lỗi, rồi thử artifact cuối trên các runtime còn hỗ trợ. Chỉ bỏ legacy lane sau khi có bằng chứng rằng consumer, batch, production và rollback không còn cần nó.
