# Thin JAR, fat JAR và trách nhiệm đóng gói dependency trong Gradle

## 1. Mục tiêu bài học

Trong một dự án Java, lệnh **./gradlew jar** thường tạo ra một file **.jar** chứa mã đã biên dịch và tài nguyên của dự án. Người mới dễ cho rằng file ấy có thể mang đi bất kỳ máy nào và chạy ngay bằng **java -jar**. Thực tế, JAR do Java plugin tạo mặc định là **thin JAR**: các thư viện bên ngoài mà ứng dụng cần lúc chạy **không được đóng gói tự động vào trong**. Với ứng dụng phụ thuộc Apache Commons Lang, Jackson hoặc một JDBC driver, chỉ copy mỗi JAR chính sang máy khác có thể dẫn đến **NoClassDefFoundError**.

**Fat JAR** (còn gọi **uber JAR** hoặc **shaded JAR** trong một số ngữ cảnh) là chiến lược tạo một archive chứa classes/resources của ứng dụng **và** các dependency được chọn. Nó thuận tiện cho cách triển khai bằng một file, nhưng tạo thêm trách nhiệm: chọn đúng runtime dependencies, gộp resources và service descriptors, xử lý class conflicts, license notices, chữ ký, artifact metadata, cập nhật lỗ hổng và khả năng tái lập build.

Bài thuộc nhóm **Đóng gói** trong Build Tool Gradle, tập trung vào **Thin JAR, fat JAR và trách nhiệm đóng gói dependency**.

Sau bài này, bạn có thể:

1. Phân biệt **JAR**, **thin JAR**, **fat/uber JAR**, **distribution ZIP/TAR**, **JVM runtime image** và **container image**.
2. Giải thích quan hệ giữa **compileClasspath**, **runtimeClasspath**, **implementation**, **api**, **runtimeOnly**, **compileOnly** và **testImplementation**.
3. Biết tại sao **jar** mặc định chỉ lấy **sourceSets.main.output** chứ không tự chứa external dependency JARs.
4. Biết cách chạy thin JAR bằng **java -cp** hoặc Gradle Application plugin distribution.
5. Dùng **Shadow plugin** ID **com.gradleup.shadow** tạo fat JAR bằng **shadowJar**, và chạy bằng **java -jar**.
6. Hiểu ranh giới dependency nào được bundle và dependency nào cố ý để bên ngoài.
7. Nhận diện lỗi trùng class/resource, **META-INF/services**, dependency chỉ load qua reflection, signed JAR, JPMS và multi-release JAR.
8. Phân biệt packaging ứng dụng thực thi với publishing một thư viện cho consumer khác.
9. Chạy ví dụ đầy đủ Java 17, Apache Commons Lang và JUnit 5; kiểm tra bằng Gradle, **javac**, **java** và **jar tf**.
10. Tổ chức CI build, kiểm tra artifact, lưu checksum, xem dependency graph và áp dụng kiểm soát license/bảo mật.

## 2. Hình dung ba kiểu bàn giao ứng dụng

~~~text
SOURCE JAVA + EXTERNAL LIBRARIES
                  |
          compileJava / classes
                  |
                  v
          sourceSets.main.output
                  |
           +------+-------------------+
           |                          |
           v                          v
        jar task                  shadowJar task
           |                          |
           v                          v
       THIN JAR                    FAT JAR
   [app classes]               [app classes]
   [resources]                 [dependency classes]
   [manifest]                  [dependency resources]
           |                          |
           |                          |
           +--> Cần runtime libs       +--> Thường có thể
                trên classpath             java -jar độc lập
           |
           v
   Application distribution
     bin/ launch scripts
     lib/ app.jar + libs
~~~

**Độc lập** ở đây nghĩa là fat JAR có đủ *các Java library dependencies đã được bundle*. Nó **không chứa JVM/JRE**, không bảo đảm có native libraries của mọi hệ điều hành, không thay thế database, network service, credentials hoặc cấu hình runtime.

### 2.1. So sánh cơ bản

| Tiêu chí | Thin JAR | Fat JAR | Application distribution |
| --- | --- | --- | --- |
| Nội dung | Classes/resources của dự án | Classes/resources của dự án và các runtime dependencies được chọn | JAR chính, các dependency JARs riêng, start scripts và tài nguyên phân phối |
| Kích thước một JAR | Thường nhỏ | Thường lớn hơn | Mỗi JAR vẫn riêng, gói ZIP/TAR tổng thể chứa nhiều file |
| Cách chạy | **java -cp** kèm libraries, hoặc launcher | Thường **java -jar** nếu có Main-Class | Script trong **bin/** |
| Quản lý classpath | Deployment/launcher chịu trách nhiệm | Packaging task quyết định nội dung | Gradle Application plugin tạo script/classpath |
| Tách dependency để cập nhật | Có thể đổi JAR riêng, phải quản lý tương thích | Thường rebuild toàn fat JAR | Có thể thay lib riêng nhưng vẫn cần phát hành đồng bộ |
| Gộp resource/service files | Không | Có rủi ro duplicate/merge | Không cần flatten nội dung các JAR |
| Hợp với library dùng bởi project khác | Thường phù hợp | Cẩn trọng, dễ tạo xung đột/metadata sai | Ít dùng để publish thư viện |
| Hợp với CLI ứng dụng | Có launcher/classpath đúng | Rất tiện một file | Thích hợp phân phối cho người dùng |
| Có JVM/JRE sẵn? | Không | Không | Thông thường không |

**Không có một lựa chọn đúng cho mọi hệ thống.** Chọn chiến lược theo người nhận artifact, môi trường triển khai, độ phức tạp classpath, yêu cầu cập nhật, bảo mật và cách quản lý dependency.

## 3. JAR là gì, và manifest quyết định điều gì?

JAR là một archive có cấu trúc gần với ZIP, chứa **.class**, resources và metadata như **META-INF/MANIFEST.MF**.

Ví dụ thin JAR:

~~~text
packaging-lab-1.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── demo/
    └── app/
        ├── Main.class
        └── TextFormatter.class
~~~

Manifest có thể chứa:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
~~~

**Main-Class** chỉ cho Java launcher biết phương thức **public static void main(String[] args)** ở class nào sẽ được gọi khi dùng **java -jar**. Nó **không tự đưa** Apache Commons Lang, Jackson, Spring hoặc bất kỳ dependency nào vào JAR.

Vì vậy hai điều phải độc lập:

- **JAR executable theo manifest:** có Main-Class hợp lệ.
- **Ứng dụng runnable theo dependency graph:** tất cả classes, resources, native dependencies và cấu hình cần lúc chạy có trên classpath/module path.

Một thin JAR có Main-Class **vẫn có thể fail** khi chạy đơn lẻ vì thiếu external dependency.

### 3.1. Manifest Class-Path không phải bundling

Manifest còn có thuộc tính **Class-Path** để chỉ các JAR bên ngoài theo đường dẫn tương đối phù hợp:

~~~text
Main-Class: demo.app.Main
Class-Path: lib/commons-lang3-3.17.0.jar
~~~

Khi đặt các JAR đó đúng vị trí tương đối với JAR chính, **java -jar** có thể tải được các dependency được liệt kê. Tuy nhiên:

- Các JAR vẫn là file riêng, không được “nhúng” vào thin JAR.
- Đường dẫn trong manifest phải phù hợp layout phát hành.
- Việc copy mỗi app.jar sẽ không mang theo thư viện.
- Nếu thư viện đổi tên/version, cần cập nhật layout và manifest.
- Không dùng manifest Class-Path làm thay thế cho quản lý release/distribution có kiểm soát.

Trong lab, JAR thường chỉ khai báo **Main-Class**, nên lệnh chạy thin JAR phải dùng **java -cp** hoặc generated start script.

## 4. Java plugin và hành vi mặc định của task jar

Khi có:

~~~groovy
plugins {
    id 'java'
}
~~~

Gradle tạo **sourceSets.main**, **compileJava**, **processResources**, **classes**, **jar**, **assemble**, **check**, **build** và các configurations cho Java ecosystem.

Task **jar** thường lấy:

~~~groovy
from(sourceSets.main.output)
~~~

để đóng gói:

- Mã Java đã được biên dịch trong **build/classes/java/main**.
- Resources đã xử lý ở **build/resources/main**.
- Manifest và metadata được cấu hình.

Task **jar không tự unzip mọi JAR từ runtimeClasspath**. Đó là thiết kế có chủ đích của Java plugin, không phải bug.

### 4.1. JAR không giống source JAR hoặc test JAR

- **jar**: archive classes/resources của **main**.
- **sourcesJar** (khi bật bằng **java.withSourcesJar()**): archive nguồn giúp IDE và người đọc.
- **javadocJar** (khi bật): archive API documentation.
- **test**: chạy tests; output test classes không mặc định đi vào main JAR.
- **shadowJar**: task do Shadow plugin cung cấp để bundle selected runtime dependencies.

Không đưa **src/test/java** hoặc **build/classes/java/test** vào production JAR chỉ để fat JAR “đầy đủ”. Test dependencies và fixtures có thể không được phép phát hành hoặc chứa thông tin nội bộ.

### 4.2. java-library và application khác mục đích

Một **java-library** project thường xuất bản thin JAR và Gradle Module Metadata/POM mô tả dependencies để **consumer tự resolve** đúng graph/variants.

Một **application** project có thể cần một cách chạy dễ dàng cho end users. Các lựa chọn phổ biến:

- **application plugin + installDist/distZip**: thin JAR và runtime JARs riêng.
- **Shadow plugin + shadowJar**: một executable fat JAR.
- **jpackage/jlink**: xây runtime/distribution chuyên biệt khi cần.
- **Container image**: đóng gói ứng dụng cùng layers/runtime phù hợp.

Đừng áp dụng chiến lược fat JAR của ứng dụng vào mọi thư viện được publish mà không xét tới consumer classpath và dependency metadata.

## 5. Cần hiểu dependency graph trước khi đóng gói

Các configurations thuộc Java/Java Library plugin giúp tách dependency theo vai trò.

| Configuration | Có trên compile classpath chính? | Có trên runtime classpath chính? | Nên bundle trong fat JAR? |
| --- | --- | --- | --- |
| **implementation** | Có | Có | Thường có, trừ khi chủ ý externalize |
| **api** (java-library) | Có | Có | Có thể cần, nhưng publishing library phải xem API contract |
| **runtimeOnly** | Không nhất thiết cho compile | Có | Thường có, nếu runtime thực sự cần |
| **compileOnly** | Có | Không | **Không mặc định**, vì được kỳ vọng do runtime khác cung cấp |
| **annotationProcessor** | Dùng cho compiler processor path | Không mặc định | **Không** nếu chỉ dùng để generate source |
| **testImplementation** | Chỉ test source set | Chỉ test runtime | **Không** trong production fat JAR |
| **testRuntimeOnly** | Không | Chỉ test runtime | **Không** |
| **runtimeClasspath** | Resolvable result, không phải declaration scope | Chính là runtime classpath | Shadow mặc định lấy dependencies từ đây |

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    runtimeOnly 'com.example:provider:1.0'
    compileOnly 'com.example:server-api:1.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

Ba tọa độ có prefix **com.example** chỉ minh họa và không dùng trong lab runnable. Điều cần hiểu: **runtimeClasspath** thông thường gồm implementation + runtimeOnly + transitive runtime dependencies, **không bao gồm** toàn bộ compiler/test-only dependencies.

### 5.1. requested version khác resolved version

Một dependency declaration như:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.17.0'
~~~

biểu thị **requested coordinate**. Gradle giải quyết graph theo version constraints, platform/BOM, conflict resolution và variant attributes. Với graph phức tạp, phiên bản **được chọn cuối cùng** có thể khác requested version.

Trước khi đóng gói, kiểm tra:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-lang3
~~~

Không suy những JAR thực sự nằm trong fat JAR chỉ từ danh sách dependencies viết tay. Shadow xử lý artifacts **đã được resolve** từ cấu hình phù hợp.

### 5.2. Transitive dependencies

Một thư viện A có thể cần B và C lúc chạy. Dù bạn chỉ viết **implementation(A)**, **runtimeClasspath** có thể gồm A, B, C theo metadata. Nếu tự copy đúng mỗi A.jar vào distribution, bạn sẽ thiếu B hoặc C.

Fat JAR plugin nên lấy **resolved runtime dependency graph**, không tự suy danh sách dependency bằng cách đọc ba chuỗi tọa độ từ build.gradle. Nhưng cũng cần kiểm soát exclusions và conflicts: một fat JAR đúng nghĩa không phải “zip mọi thứ có trong ~/.gradle/caches”.

### 5.3. Chọn đúng variant của dependency

Gradle có thể chọn variants theo **usage**, **Java target version**, **capabilities** và attributes khác. Khi resolve **runtimeClasspath**, Gradle thường chọn runtime variant phù hợp, không lấy tùy ý API variant.

Nếu producer công bố nhiều variants, không bỏ qua dependency resolution rồi chọn artifact bằng tên file bất kỳ trong cache; bạn có thể bundle sai binary/runtime dependencies.

### 5.4. BOM/platform và lockfiles

Version catalog giúp thống nhất dependency declarations, nhưng không ép mọi resolved version theo một giá trị bất biến. Có thể dùng:

- **platform(...)** hoặc BOM để căn chỉnh version families.
- Dependency constraints để đặt min/require/strict boundaries.
- Dependency locking để kiểm soát resolved versions.
- Dependency verification để xác minh artifact checksum/signature.
- Repository policies để hạn chế nguồn dependency.
- SBOM/scan policy để biết các components được bundle.

Fat JAR không tự bỏ nhu cầu đó; trái lại, khi gộp nhiều thư viện vào một archive, truy vết nguồn gốc mỗi component càng quan trọng.

## 6. Thin JAR: phương án mặc định cho thư viện và nhiều ứng dụng

### 6.1. Ưu điểm

- Output build nhỏ và nhanh hơn khi chỉ có mã dự án thay đổi.
- Không flatten resources/ServiceLoader metadata của nhiều dependency.
- Consumer được resolve versions/capabilities qua Gradle metadata/POM.
- Có thể tổ chức dependency JARs thành layers hoặc cache độc lập.
- Dễ phân biệt artifact do team tự viết và thư viện bên thứ ba.
- Không phải rewrite classes hoặc resource paths.

### 6.2. Nhược điểm

- Muốn chạy ở môi trường mới phải mang đúng runtime dependencies.
- Nếu tự triển khai bằng **java -cp**, thao tác classpath dễ sai trên Windows/Linux.
- Manifest **Main-Class** không đủ khi runtime classpath thiếu.
- Tương thích dependency graph phải được quản lý khi deploy, không chỉ khi compile.
- Người dùng cuối không quen Java có thể thích một ZIP kèm launch scripts hơn nhiều JAR rời.

### 6.3. Khi nên ưu tiên thin JAR

- Xuất bản một **Java library** để Gradle/Maven consumers quản lý dependencies.
- Chạy ứng dụng bằng Application plugin **installDist/distZip**.
- Ứng dụng trong container có dependency layers tách biệt để tận dụng caching.
- Runtime có application server/plugin host cung cấp một số APIs, nhưng cần quản lý **compileOnly/provided** đúng.
- Có platform metadata/variant và nhu cầu quản lý dependencies linh hoạt.

### 6.4. Chạy thin JAR bằng classpath

Ví dụ layout:

~~~text
release/
├── app.jar
└── lib/
    ├── commons-lang3-3.17.0.jar
    └── dependency-khac.jar
~~~

Trên Linux/macOS:

~~~bash
java -cp "release/app.jar:release/lib/*" demo.app.Main
~~~

Trên Windows PowerShell:

~~~powershell
java -cp "release\app.jar;release\lib\*" demo.app.Main
~~~

**Dấu phân tách classpath khác nhau:** dấu hai chấm **:** trên Linux/macOS, dấu chấm phẩy **;** trên Windows. Wildcard **\*** của Java launcher mở rộng các JAR trong directory; nó không tự đệ quy mọi thư mục con.

**Đừng thêm một JAR ở vị trí khác rồi mong runtime tự tìm thấy.** Một class phải nằm trong JAR/directory thực sự xuất hiện trên effective classpath hoặc module path.

## 7. Application plugin: thin JAR cộng distribution đầy đủ dependencies

Với:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Application plugin áp dụng Java plugin và cung cấp:

- **run**: JavaExec task dùng runtimeClasspath để chạy ứng dụng khi phát triển.
- **startScripts**: tạo launch scripts theo môi trường.
- **installDist**: staging một application distribution ở **build/install/**.
- **distZip**, **distTar**: tạo distribution archives.
- **application** extension: cấu hình mainClass, default JVM args, executable name và các tùy chọn khác.

Một distribution thông thường:

~~~text
build/install/packaging-lab/
├── bin/
│   ├── packaging-lab
│   └── packaging-lab.bat
└── lib/
    ├── packaging-lab-1.0.jar
    └── commons-lang3-3.17.0.jar
~~~

**Đây không phải fat JAR**: thư viện nằm **cạnh** JAR chính trong **lib/**. Script ở bin chuẩn bị classpath rồi khởi chạy Main, nên người dùng không phải tự viết **java -cp**.

### 7.1. Khi thích distribution hơn fat JAR

- Có launch scripts cho cả Windows/Unix.
- Muốn đặt default JVM flags, app config/files dưới **src/dist**.
- Cần kiểm soát/apply updates cho từng library JAR.
- Muốn giữ cấu trúc từng JAR nguyên bản, tránh merge resource conflicts.
- Đang vận hành CI/CD artifact ZIP/TAR có tên và cấu trúc ổn định.

Application plugin distribution thông thường cũng **không đóng gói JRE/JDK**. Nếu cần runtime đi kèm, dùng jlink/jpackage hoặc container/runtime image phù hợp.

### 7.2. run task không kiểm chứng khả năng chạy thin JAR đơn lẻ

Lệnh:

~~~bash
./gradlew run
~~~

dùng classpath Gradle đã resolve, nên ứng dụng chạy dù **jar** không chứa dependencies. Đừng suy rằng **java -jar build/libs/app.jar** chắc chắn cũng chạy chỉ vì **./gradlew run** thành công.

Để xác minh artifact deploy, bắt buộc thử trên **release layout** hoặc JAR được bàn giao bằng launcher thực tế.

## 8. Fat/uber JAR: một file chứa runtime libraries đã chọn

Fat JAR gộp application classes/resources cùng thư viện từ runtime dependency graph thành một JAR mới.

Ví dụ:

~~~text
packaging-lab-1.0-all.jar
├── META-INF/MANIFEST.MF
├── demo/app/Main.class
├── demo/app/TextFormatter.class
├── org/apache/commons/lang3/StringUtils.class
├── org/apache/commons/lang3/... (các classes khác)
└── resource/metadata được chọn từ dependencies
~~~

Nếu manifest có **Main-Class: demo.app.Main**, lệnh:

~~~bash
java -jar build/libs/packaging-lab-1.0-all.jar
~~~

có thể chạy mà không cần mang file commons-lang3.jar riêng. Nhưng JDK/Java runtime tương thích vẫn phải có.

### 8.1. Ưu điểm

- Bàn giao một JAR đơn giản cho CLI/small service.
- Dễ định danh một artifact cùng checksum cho release.
- Tránh lỗi quên copy runtime JARs bên ngoài trong nhiều trường hợp.
- Thuận lợi cho môi trường có Java runtime sẵn, muốn chạy **java -jar**.
- Có thể relocate một số package dependencies để xử lý xung đột khi dùng plugin phù hợp.

### 8.2. Hạn chế

- Archive lớn hơn, rebuild có thể thay cả file khi một dependency thay đổi.
- Trùng class/resource path có thể gây lỗi hoặc silent data loss nếu exclude sai.
- ServiceLoader, logging config, Spring metadata, signature files cần xử lý có chủ đích.
- JPMS/module descriptors và multi-release jars có thể có hành vi khác sau khi merge.
- Thư viện load class bằng reflection/ServiceLoader dễ hỏng nếu minimize/relocate tùy tiện.
- License notices, SBOM, nguồn gốc và vulnerability scanning khó kiểm kê nếu chỉ nhìn một artifact file.
- **Fat JAR không thay thế OS/JRE/native binaries hoặc external services.**

### 8.3. Shadow plugin cho Gradle hiện đại

Plugin chính hiện nay dùng ID:

~~~groovy
plugins {
    id 'com.gradleup.shadow' version '9.6.1'
}
~~~

Shadow trước đây từng dùng ID **com.github.johnrengelman.shadow**. Khi áp dụng vào dự án hiện đại, ưu tiên ID **com.gradleup.shadow** được GradleUp duy trì.

**Phiên bản 9.6.1** là bản phát hành được xác nhận trên Gradle Plugin Portal vào tháng 7/2026. Với Shadow 9.5+ cần Gradle ít nhất **9.2** và Java **17+** để chạy plugin theo compatibility matrix; lab cần Wrapper/JDK đáp ứng mức này. Không suy rằng Shadow version này chạy được trên mọi Gradle 7/8 cũ; nếu project dùng Wrapper cũ, chọn plugin version tương thích đã kiểm tra.

### 8.4. Những task Shadow cung cấp

Với Java/Application plugin, Shadow thường tạo:

- **shadowJar**: archive chứa main classes/resources và dependencies từ runtimeClasspath, classifier mặc định **all**.
- **shadow** dependency configuration cho dependencies **không được gộp** vào fat JAR nhưng phải được quản lý runtime.
- **runShadow** khi kết hợp Application plugin.
- **shadowDistZip**, **shadowDistTar**, **installShadowDist** và start scripts cho distribution dùng shadowed JAR.
- Publication/component/variant support cho Shadow theo plugin integration, cần cấu hình publish đúng nếu sử dụng.

**Đừng nhầm** **shadowJar** là task của Gradle core Java plugin; nó chỉ xuất hiện khi plugin Shadow được resolve và áp dụng.

## 9. Chuẩn bị lab Java 17 chạy được

Lab có một Java application sử dụng **Apache Commons Lang** tại runtime. Ta sẽ tạo:

1. **Thin JAR** từ task **jar**.
2. **Thư mục runtime-libs** copy resolved runtime JARs cho cách chạy thin.
3. **Application distribution** với scripts + libs riêng.
4. **Fat JAR** từ **shadowJar**.
5. **JUnit tests** chứng minh code có thể chạy với dependency thật.
6. **javac/java** độc lập để kiểm tra classpath ngoài Gradle.

### 9.1. Cấu trúc project

~~~text
packaging-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/...
└── src/
    ├── main/
    │   └── java/demo/app/
    │       ├── TextFormatter.java
    │       └── Main.java
    └── test/
        └── java/demo/app/
            └── TextFormatterTest.java
~~~

Tệp Wrapper phải được tạo một lần bằng Gradle CLI đã cài **tương thích** rồi commit vào repo. Nếu chưa có Wrapper, chạy **gradle wrapper** bằng Gradle version thỏa Shadow 9.6.1 yêu cầu, sau đó dùng **./gradlew**/ **.\gradlew.bat**.

Mọi file Java trong ví dụ dùng **Java 17**, package/path đúng; project cần Internet hoặc mirror/cache có Apache Commons Lang, JUnit Jupiter và Shadow plugin.

### 9.2. settings.gradle

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'packaging-lab'
~~~

**pluginManagement** chỉ định nơi resolve Shadow plugin. **dependencyResolutionManagement** chỉ định nơi resolve Commons/JUnit libraries. Hai phạm vi khác nhau.

**RepositoriesMode.FAIL_ON_PROJECT_REPOS** là chính sách demo: build.gradle sẽ không tự thêm repository. Trong doanh nghiệp có mirror nội bộ, dùng repository cho phép theo chính sách, thay vì bỏ qua xác thực/proxy.

### 9.3. build.gradle — cấu hình hoàn chỉnh

~~~groovy
plugins {
    id 'application'
    id 'com.gradleup.shadow' version '9.6.1'
}

group = 'demo'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

// Main-Class phải đúng để thử java -jar thin JAR và fat JAR.
tasks.named('jar', Jar) {
    manifest {
        attributes 'Main-Class': 'demo.app.Main'
    }
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

// Sao chép từng runtime JAR để thử classpath của thin JAR.
tasks.register('copyRuntimeDeps', Copy) {
    group = 'distribution'
    description = 'Copy resolved runtime dependencies'
    from(configurations.runtimeClasspath)
    into(layout.buildDirectory.dir('runtime-libs'))
}

// Tách biệt output archive, giữ timestamps và thứ tự tệp ổn định.
tasks.withType(
        org.gradle.api.tasks.bundling.AbstractArchiveTask
    ).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Lưu ý quan trọng:** lab không cấu hình **shadowJar** một cách thủ công vì Shadow tạo sẵn task với classifier **all**, lấy **main output** và bundle **runtimeClasspath**. Với Application plugin, Shadow cấu hình **Main-Class** cho fat JAR; task jar cũng được khai báo manifest ở đây để so sánh minh bạch.

**tasks.named('jar', Jar)** chỉ thêm manifest, không biến thin JAR thành fat JAR. **copyRuntimeDeps** là task phụ dùng để chuẩn bị lớp library JARs khi chạy thin JAR thủ công; nó không tự chạy mỗi lần jar được tạo nếu không yêu cầu.

**testImplementation** không xuất hiện trong main runtimeClasspath, vì vậy JUnit không được bundle vào fat JAR ứng dụng. Nếu thấy **org/junit/** classes trong production artifact, hãy kiểm tra dependency scopes hoặc một cấu hình Shadow đã bị sửa.

### 9.4. src/main/java/demo/app/TextFormatter.java

~~~java
package demo.app;

import org.apache.commons.lang3.StringUtils;

public final class TextFormatter {
    private TextFormatter() {
    }

    public static String greeting(String raw) {
        if (StringUtils.isBlank(raw)) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        String normalized =
                StringUtils.capitalize(StringUtils.trim(raw));

        return "Hello, " + normalized + "!";
    }
}
~~~

**TextFormatter** tham chiếu **org.apache.commons.lang3.StringUtils**, một class nằm trong external library JAR. Điều này tạo phép kiểm thử thực tế: nếu library không có trên classpath, chương trình sẽ không chạy đúng; nếu Shadow bundle library thành công, fat JAR có thể chạy đơn lẻ.

### 9.5. src/main/java/demo/app/Main.java

~~~java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "MESSAGE=" +
                TextFormatter.greeting("  gradle  "));
    }
}
~~~

Đầu vào có khoảng trắng và chữ thường; **StringUtils.trim** và **StringUtils.capitalize** tạo **Gradle**.

**Stdout chính xác từ Main:**

~~~text
MESSAGE=Hello, Gradle!
~~~

### 9.6. src/test/java/demo/app/TextFormatterTest.java

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TextFormatterTest {
    @Test
    void greetsNormalizedName() {
        assertEquals(
                "Hello, Gradle!",
                TextFormatter.greeting("  gradle  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> TextFormatter.greeting("  "));
    }
}
~~~

Hai JUnit tests dự kiến pass. Đây là code kiểm thử trong source set **test**, không phải code được đưa vào thin/fat JAR production.

### 9.7. Các dependency sẽ nằm ở đâu?

Từ build.gradle:

- **Commons Lang 3.17.0** thuộc **implementation**, cần cho compile và runtime của main.
- **JUnit Jupiter 5.11.4** thuộc **testImplementation**, phục vụ test compilation/execution.
- **JUnit Platform Launcher 1.11.4** thuộc **testRuntimeOnly**, phục vụ Test task.
- **Shadow plugin 9.6.1** là Gradle build plugin, **không phải dependency của ứng dụng Java** và không nên nằm trong JAR deploy.
- **Gradle distribution/JDK** phục vụ build, **không mặc nhiên được đóng vào fat JAR**.

## 10. Chạy lab: so sánh các artifact thật

### 10.1. Linux/macOS

~~~bash
./gradlew --version
./gradlew clean test
./gradlew jar
./gradlew copyRuntimeDeps
./gradlew shadowJar
./gradlew installDist
./gradlew installShadowDist
./gradlew -q run
./gradlew -q runShadow
~~~

**Hai lệnh run và runShadow đều dự kiến in dòng stdout của Java Main:**

~~~text
MESSAGE=Hello, Gradle!
~~~

Gradle có thể in task logs, warnings hoặc thông tin daemon; khối trên chỉ là stdout do Main in.

Sau **jar** và **shadowJar**:

~~~text
build/libs/packaging-lab-1.0.jar
build/libs/packaging-lab-1.0-all.jar
~~~

Tên file dựa trên **rootProject.name=packaging-lab**, **version=1.0** và default Shadow classifier **all**. Nếu dự án thay archiveBaseName/version/classifier thì tên thực tế sẽ khác.

Sau **copyRuntimeDeps**:

~~~text
build/runtime-libs/commons-lang3-3.17.0.jar
~~~

Đây là đường dẫn dự kiến từ dependency hiện có, không phải nơi chuẩn để Shadow lấy JAR: Shadow mặc định resolve **runtimeClasspath** trực tiếp.

### 10.2. Thin JAR: java -cp có dependency

~~~bash
java -cp \
  "build/libs/packaging-lab-1.0.jar:build/runtime-libs/*" \
  demo.app.Main
~~~

Stdout:

~~~text
MESSAGE=Hello, Gradle!
~~~

Classpath chứa cả **app.jar** và **commons-lang3.jar**, nên JVM tìm thấy **StringUtils**.

### 10.3. Thin JAR: java -jar đơn lẻ thường thất bại

Với lab này, lệnh:

~~~bash
java -jar build/libs/packaging-lab-1.0.jar
~~~

**được kỳ vọng không chạy thành công**: manifest có Main-Class nhưng không có Commons Lang trên classpath, và lab không khai báo Manifest Class-Path. Java có thể báo **NoClassDefFoundError: org/apache/commons/lang3/StringUtils** hoặc một thông báo lỗi nạp class tương đương khi code thực thi.

Đây là bài kiểm tra **cố ý thất bại để hiểu thin JAR**, không phải cách triển khai được khuyến nghị. Không “sửa” bằng cách copy thư viện vào **src/main/java**.

### 10.4. Fat JAR: java -jar một file

~~~bash
java -jar build/libs/packaging-lab-1.0-all.jar
~~~

Stdout:

~~~text
MESSAGE=Hello, Gradle!
~~~

Lệnh này không thêm **build/runtime-libs** vì Shadow đã bundle Commons classes. Nó vẫn cần Java runtime tương thích trong máy triển khai.

### 10.5. Kiểm tra nội dung bằng jar tf

~~~bash
jar tf build/libs/packaging-lab-1.0.jar
jar tf build/libs/packaging-lab-1.0-all.jar
~~~

Thay vì so sánh tổng số entry theo thứ tự (có thể thay đổi), tìm những class quan trọng:

~~~bash
jar tf build/libs/packaging-lab-1.0.jar \
  | grep 'demo/app/Main.class'

jar tf build/libs/packaging-lab-1.0-all.jar \
  | grep 'org/apache/commons/lang3/StringUtils.class'
~~~

Với lab đúng:

- **Thin JAR** chứa **demo/app/Main.class** và **demo/app/TextFormatter.class**.
- **Thin JAR không chứa** **org/apache/commons/lang3/StringUtils.class**.
- **Fat JAR** chứa cả application classes lẫn Commons Lang classes.
- Không nên có JUnit test classes trong production artifact.

Một fat JAR lớn không mặc định đồng nghĩa đúng: phải **kiểm tra class/service/resources** mà ứng dụng thực sự cần, không chỉ kích thước.

### 10.6. Kiểm tra manifest

~~~bash
unzip -p build/libs/packaging-lab-1.0.jar \
  META-INF/MANIFEST.MF

unzip -p build/libs/packaging-lab-1.0-all.jar \
  META-INF/MANIFEST.MF
~~~

Cả hai có thể có **Main-Class: demo.app.Main**, nhưng chỉ fat JAR có bundled Commons classes. Nếu môi trường không có **unzip**, dùng **jar xf** trong thư mục kiểm tra tạm và đọc manifest.

### 10.7. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat jar copyRuntimeDeps shadowJar
.\gradlew.bat installDist installShadowDist
.\gradlew.bat -q run
.\gradlew.bat -q runShadow

java -cp "build\libs\packaging-lab-1.0.jar;build\runtime-libs\*" demo.app.Main
java -jar build\libs\packaging-lab-1.0-all.jar
~~~

Stdout của các lệnh chạy ứng dụng:

~~~text
MESSAGE=Hello, Gradle!
~~~

Kiểm tra fat JAR classes:

~~~powershell
jar tf build\libs\packaging-lab-1.0-all.jar |
  Select-String 'org/apache/commons/lang3/StringUtils.class'
~~~

**Classpath separator** là dấu **;** trên Windows, không phải dấu **:** như Unix.

### 10.8. Cách chạy application distributions

Sau khi gọi:

~~~bash
./gradlew installDist
~~~

trên Unix:

~~~bash
./build/install/packaging-lab/bin/packaging-lab
~~~

Trên Windows:

~~~powershell
.\build\install\packaging-lab\bin\packaging-lab.bat
~~~

Tương tự **installShadowDist** tạo distribution dựa trên fat JAR và scripts riêng. Shadow docs mô tả staging ở:

~~~text
build/install/packaging-lab-shadow/
~~~

Vì thế trên Unix có thể chạy:

~~~bash
./build/install/packaging-lab-shadow/bin/packaging-lab
~~~

Khi phát hành, nên tải và kiểm tra cả ZIP/TAR trong môi trường sạch, không chỉ chạy từ thư mục build vốn có sẵn Gradle cache. Start script được tạo bởi distribution plugin có đường dẫn/cấu hình phụ thuộc OS, phiên bản plugin và tên ứng dụng.

## 11. Biên dịch Java 17 độc lập để hiểu classpath

Bạn có thể kiểm chứng Java source mà không dùng task **compileJava**, nhưng vẫn phải có Commons Lang JAR vì TextFormatter import một external class.

Sau:

~~~bash
./gradlew copyRuntimeDeps
~~~

trên Linux/macOS:

~~~bash
mkdir -p out

javac --release 17 \
  -cp "build/runtime-libs/*" \
  -d out \
  src/main/java/demo/app/TextFormatter.java \
  src/main/java/demo/app/Main.java

java -cp "out:build/runtime-libs/*" demo.app.Main
~~~

Stdout:

~~~text
MESSAGE=Hello, Gradle!
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat copyRuntimeDeps
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -cp "build\runtime-libs\*" -d out src\main\java\demo\app\TextFormatter.java src\main\java\demo\app\Main.java

java -cp "out;build\runtime-libs\*" demo.app.Main
~~~

**Điều được kiểm chứng:**

- Java 17 compiler hiểu source code và external dependency API.
- JVM chạy đúng Main khi classpath có Commons Lang.
- Nếu bỏ JAR khỏi javac classpath, sẽ có lỗi **package org.apache.commons.lang3 does not exist**.
- Nếu chỉ bỏ JAR khỏi runtime classpath, Java có thể compile xong nhưng fail khi chạy TextFormatter.

**Điều chưa được kiểm chứng bởi javac/java thủ công:** Gradle tasks, Shadow merge/resource handling, default manifest, distributions, JUnit Test task và CI artifact. Cần chạy Gradle Wrapper để xác minh các phần ấy.

## 12. Shadow bundle dependency nào theo mặc định?

Theo mô hình Shadow Java plugin:

- **shadowJar** lấy **sourceSets.main.output** và libraries trong **runtimeClasspath**.
- **runtimeClasspath** có runtime dependencies của ứng dụng, gồm implementation và runtimeOnly theo graph.
- Một configuration tên **shadow** được tạo để khai báo dependencies **không gộp** vào Shadow JAR theo cơ chế Shadow.
- Shadow có integration với Application plugin và publication model.

### 12.1. Chủ động giữ dependency ở ngoài

Ví dụ minh họa:

~~~groovy
dependencies {
    shadow 'com.example:provided-runtime:1.0'
}
~~~

Tọa độ **com.example** ở đây là ví dụ **không có artifact thật**; không thêm vào lab runnable. Theo tài liệu Shadow, dependency khai báo trong configuration **shadow** được hiểu là dependency runtime **không được bundle**, và có thể được liệt kê trong Manifest Class-Path của shadowed JAR khi phù hợp.

Nếu bạn dùng cơ chế này, người triển khai **vẫn phải cung cấp** external JAR tại vị trí tương ứng với manifest/runtime. Một file tên **-all.jar** không bảo đảm hoàn toàn self-contained nếu bạn cố ý externalize một phần dependencies.

### 12.2. compileOnly không tự thành runtime dependency

Một thư viện chỉ có trên **compileOnly** thường là API do container hoặc runtime host cung cấp. Fat JAR tạo từ runtimeClasspath không tự bao gồm nó. Nếu bạn deploy fat JAR ra môi trường **không cung cấp API đó**, lỗi class loading là điều có thể xảy ra.

Cần quyết định rõ **provided-by-runtime** là một contract thật hay chỉ là scope khai báo sai. Không thêm mọi compileOnly dependency vào fat JAR chỉ để hết lỗi — có thể phá classloader isolation của container.

### 12.3. Test dependencies không dành cho production

Không dùng **configurations.testRuntimeClasspath** làm nguồn bundle cho ứng dụng. Nó có thể kéo JUnit, mocks, fake servers hoặc test fixtures vào artifact deploy. Cấu hình đúng là runtime classpath của **main** hoặc một runtime configuration có chủ đích.

### 12.4. External native libraries

Một Java library có thể cần JNI/native .so/.dll/.dylib. Việc bundle Java classes vào fat JAR không tự bảo đảm native library có thể được load bằng **System.loadLibrary**, nhất là khi native binaries phụ thuộc OS/CPU. Cần release packaging riêng theo platform, extraction strategy hoặc runtime image/container phù hợp.

## 13. Vì sao không nên tự zipTree runtimeClasspath một cách máy móc?

Một đoạn thường gặp trên Internet:

~~~groovy
tasks.register('fatJar', Jar) {
    archiveClassifier.set('all')
    from(sourceSets.main.output)
    from {
        configurations.runtimeClasspath.collect {
            it.isDirectory() ? it : zipTree(it)
        }
    }
}
~~~

Đây là **minh họa antipattern** chứ không phải phần được áp dụng vào lab. Nó có thể tạo một JAR cơ bản cho demo nhỏ nhưng có các hạn chế:

1. Resolve/iterate runtimeClasspath tùy cách cấu hình, có thể làm configuration chậm.
2. Không cung cấp chính sách merge resources/service descriptors đầy đủ.
3. Dễ gặp duplicate entries trong **META-INF/**.
4. Các file chữ ký gốc có thể không còn hợp lệ sau khi classes được merge.
5. Có thể mất license notices, multi-release metadata hoặc cấu trúc đặc thù.
6. Không tự cấu hình đúng dependency publication metadata.
7. Không tự nhận diện reflective usages để tránh xóa class nếu sau này minimize.
8. Dễ nhầm **main output** với test output.
9. Có thể làm build khó cache/reproduce nếu việc ghi file không ổn định.

Đây không phải lập luận rằng **zipTree** luôn bị cấm. Nếu bạn thực sự kiểm soát từng JAR và tất cả edge cases, task custom có thể đủ. Nhưng cho ứng dụng thực tế có nhiều dependencies, nên dùng Shadow hoặc công cụ chuyên dụng và kiểm thử kết quả.

## 14. Trùng tài nguyên, ServiceLoader và META-INF/services

Khi merge nhiều JAR thành một, cùng một đường dẫn entry có thể xuất hiện ở nhiều libraries.

Ví dụ:

~~~text
library-a.jar:
  META-INF/services/javax.annotation.processing.Processor
  META-INF/LICENSE

library-b.jar:
  META-INF/services/javax.annotation.processing.Processor
  META-INF/LICENSE
~~~

Nếu fat JAR chỉ giữ resource đầu tiên, danh sách provider trong **META-INF/services/...** từ thư viện thứ hai có thể mất. Nếu ghi cả hai duplicate entries không theo quy tắc, runtime đọc resource có thể không nhất quán.

### 14.1. ServiceLoader dùng metadata dạng text

Java **ServiceLoader** tìm provider implementations qua file **META-INF/services/<fully-qualified-service-interface>**. Mỗi file có các dòng class names provider. Nếu nhiều dependency cùng đóng góp provider cho một service, cần **merge service descriptors** thay vì chỉ EXCLUDE phần thứ hai.

Shadow cung cấp **mergeServiceFiles()**:

~~~groovy
tasks.named('shadowJar') {
    mergeServiceFiles()
}
~~~

**Đoạn này là minh họa bổ sung**; lab với Commons Lang không cần ServiceLoader merge. Không bật một transformer chỉ vì có fat JAR khi chưa hiểu loại resources cần merge.

### 14.2. Duplicates strategy có thể cản transformer

Shadow docs nêu mặc định **DuplicatesStrategy.EXCLUDE** và lưu ý duplicate filtering có thể xảy ra **trước** transformer. Vì thế chỉ viết **mergeServiceFiles()** nhưng vẫn loại duplicate descriptor entries có thể làm mất providers.

Một cấu hình có kiểm soát, **chỉ khi bạn cần gộp service descriptors**, là:

~~~groovy
tasks.named('shadowJar') {
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    mergeServiceFiles()

    filesNotMatching('META-INF/services/**') {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    }
}
~~~

Đây là **mẫu minh họa** từ nguyên tắc trong Shadow docs, không nằm trong build.gradle lab vì lab không cần merge services. Nó cho phép service descriptors đi đến transformer và loại các file trùng ngoài vùng service, nhưng **EXCLUDE không tự chứng minh các file còn lại có thể bị bỏ mà không ảnh hưởng hành vi**.

Shadow docs lưu ý dùng **filesMatching/filesNotMatching/eachFile** có thể tắt output caching của ShadowJar, nên cần cân nhắc giữa chiến lược merge và hiệu quả build. Với Spring/Log4j2, có thể cần transformers chuyên biệt, không chỉ service merge chung.

### 14.3. META-INF/LICENSE và NOTICE

Các thư viện thường chứa **LICENSE**, **NOTICE**, attribution hoặc metadata khác. Hai file trùng tên không nhất thiết chứa cùng nội dung. Việc silently exclude một bản có thể gây thiếu thông tin giấy phép.

**Đóng gói dependency là trách nhiệm pháp lý/kỹ thuật**, không chỉ “có class chạy được”. Khi tạo fat JAR, kiểm tra license obligations và quy trình gộp/đính kèm notices, SBOM và danh sách thư viện bên thứ ba.

## 15. Class collisions, shading và relocation

### 15.1. Cùng fully qualified class name

Giả sử hai dependencies có cùng:

~~~text
com/example/util/Helper.class
~~~

Trong thin distribution, classloader có thể nạp version đầu tiên trên classpath, gây hành vi phụ thuộc thứ tự. Trong fat JAR, hai entry trùng cùng đường dẫn cần một chính sách; việc EXCLUDE một class có thể che version conflict và gây lỗi khi một phần chương trình cần API của version còn lại.

Cách giải quyết tốt trước tiên là:

1. Xem dependency graph và version selection.
2. Nâng/hạ version để có bộ tương thích.
3. Dùng dependency constraints hoặc platform.
4. Xóa dependency không cần.
5. Nếu cần giữ hai bản package khác nhau trong cùng runtime, cân nhắc **relocation**.

### 15.2. Relocation đổi package để giảm xung đột

Shadow có thể chuyển package của một dependency sang namespace riêng. Ví dụ **chỉ để minh họa, không thêm vào lab runnable**:

~~~groovy
tasks.named('shadowJar') {
    relocate(
        'org.apache.commons.lang3',
        'demo.shaded.commons.lang3')
}
~~~

Bản đã relocate có thể chứa classes dưới **demo/shaded/commons/lang3/**. Shadow cố sửa những references cần thiết trong bytecode/resources theo cơ chế plugin.

**Không relocate mọi dependency theo thói quen.** Reflection qua hardcoded class name, serialization, resource lookup, ServiceLoader, JNI, XML config hoặc public API có thể bị ảnh hưởng. Với library đã publish, việc expose relocated classes có thể khóa consumers vào một API không mong muốn.

### 15.3. Shaded library khác executable application

Một fat JAR dùng để **chạy ứng dụng** thường là entrypoint duy nhất, ít lo consumer “import” package đã bundle.

Một **library JAR** mà consumer sẽ đưa lên classpath có yêu cầu khác:

- Dependency metadata/API variants phải đúng.
- Nếu gộp không relocate, dễ gây duplicate classpath.
- Nếu relocate, public API và reflection phải được kiểm thử.
- Có thể publish cả thin và shaded variants nhưng phải đặt capability/artifact rõ để consumer chọn.
- Không publish fat library như thể nó là thin component bình thường mà không kiểm tra POM/Gradle Module Metadata.

Trong đa số trường hợp **thư viện Java chia sẻ**, thin JAR với metadata dependencies đúng là lựa chọn an toàn hơn.

## 16. Cẩn trọng với minimize() và dependency động

Shadow hỗ trợ:

~~~groovy
tasks.named('shadowJar') {
    minimize()
}
~~~

**Đây là tùy chọn nâng cao, không dùng trong lab gốc.** Nó cố bỏ dependency classes không được dùng để giảm kích thước fat JAR. Nhưng việc phân tích bytecode tĩnh có thể không tìm thấy usages qua:

- **Class.forName(...)** hoặc reflection.
- **ServiceLoader**.
- Dependency injection/framework scanning.
- Serialization/deserialization.
- JNI hoặc plugin loading.
- Resource-based class names.
- Classes được tải theo cấu hình người dùng.

Nếu class bị loại nhưng runtime mới cần, ứng dụng có thể pass smoke test nhỏ và fail ở production path hiếm gặp.

### 16.1. Khi nào có thể dùng minimize?

- Đã có integration tests đủ rộng để chứng minh những code paths động.
- Có allowlist/exclusions cho thư viện dùng reflection/services.
- Có runtime smoke tests cho fat JAR sau khi minimize.
- Có thể so sánh SBOM/artifact trước và sau.
- Không làm mất support code được ứng dụng nạp tùy cấu hình.

Đừng coi “JAR nhỏ hơn” là mục tiêu quan trọng hơn tính đúng đắn, bảo mật và khả năng debug.

## 17. Signed JAR, JPMS và multi-release JAR

### 17.1. Signed JAR

Một dependency JAR có thể có chữ ký dưới **META-INF/*.SF**, **META-INF/*.RSA**, **META-INF/*.DSA** và các metadata liên quan. Khi unpack/merge classes/resources, nội dung archive thay đổi và chữ ký của archive gốc có thể không còn hợp lệ.

Shadow mặc định có chính sách loại một số signature/index entries khi tạo shadow JAR. Điều này **không nghĩa** fat JAR mới tự được ký hoặc giữ nguyên tính xác thực chữ ký của mọi dependency. Nếu tổ chức yêu cầu artifact signing, hãy ký artifact sau khi đóng gói theo quy trình release, kiểm soát checksums/dependency verification và provenance riêng.

### 17.2. Java Platform Module System

Nhiều JARs có **module-info.class** mô tả JPMS modules. Merge nhiều module descriptors thành một JAR không phải phép toán đơn giản vì:

- Modules có tên/packages riêng.
- Exports/requires/opens có semantics.
- Có thể bị split packages.
- Service bindings có module declarations.

Fat JAR thường phù hợp với **classpath-based application** hơn việc lấy nhiều Java modules rồi tưởng rằng có một JPMS module hợp lệ. Nếu dự án tận dụng mạnh JPMS, cân nhắc thin JARs trên module path, **jlink** hoặc cách đóng gói hỗ trợ module semantics.

### 17.3. Multi-release JAR

Một số libraries chứa:

~~~text
META-INF/versions/9/...
META-INF/versions/17/...
~~~

và **Multi-Release: true** trong manifest. Đây là cơ chế JAR cho classes/resources khác theo Java version.

Khi flatten/merge, cần đảm bảo manifest/multi-release attributes và cấu trúc tương thích. Không chủ động xóa mọi **META-INF/versions/** chỉ để giảm kích thước nếu dependency dùng chúng. Shadow có tùy chọn/logic liên quan multi-release; phải thử artifact thực trên target Java versions.

### 17.4. Java 17 không tương đương “mọi JAR đều chạy trên Java 17”

Ngay cả khi code ứng dụng được biên dịch với Java 17, fat JAR có thể chứa dependency bytecode biên dịch cho Java version cao hơn. Khi JVM load class đó có thể gặp **UnsupportedClassVersionError**.

Cần kiểm tra compatibility của mọi runtime dependencies và toolchain target. Chọn đúng dependency versions cho target runtime thay vì chỉ đặt **java.toolchain.languageVersion = 17**.

## 18. Reproducibility, checksum và artifact provenance

### 18.1. Vì sao fat JAR khó so sánh hơn thin?

Một fat JAR có thể gồm hàng nghìn entries từ nhiều thư viện, manifest metadata, timestamps, entry order và resource transformers. Nếu thứ tự/mtime khác nhau giữa hai builds từ cùng source, checksum artifact có thể thay đổi dù logic tương đương.

Gradle/Shadow hỗ trợ reproducible archive settings:

~~~groovy
tasks.withType(
        org.gradle.api.tasks.bundling.AbstractArchiveTask
    ).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Lab đã dùng cấu hình này. Nó giảm biến động do timestamp và file order nhưng **không đảm bảo byte-for-byte reproducibility khi các inputs/tool versions/network/metadata vẫn không được pin hoặc chứa nondeterminism**.

### 18.2. Hash artifact

Linux/macOS:

~~~bash
sha256sum build/libs/packaging-lab-1.0.jar
sha256sum build/libs/packaging-lab-1.0-all.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build\libs\packaging-lab-1.0.jar -Algorithm SHA256
Get-FileHash build\libs\packaging-lab-1.0-all.jar -Algorithm SHA256
~~~

Checksum giúp định danh binary được triển khai và so sánh artifacts, nhưng **không tự chứng minh dependency an toàn hay đã được ký bởi nguồn tin cậy**.

### 18.3. SBOM và danh sách runtime components

Fat JAR không làm các dependencies biến mất về mặt license/vulnerability. Với supply-chain audit:

- Lưu resolved dependency graph cùng versions.
- Tạo **SBOM** (ví dụ CycloneDX/SPDX) bằng công cụ đã phê duyệt.
- Kiểm tra licenses, notices và vulnerability advisories.
- Ghi artifact digest, commit SHA, Gradle Wrapper, JDK, build environment.
- Nếu relocation làm thay package paths, giữ mapping để vulnerability scanner/SBOM vẫn nhận diện libraries gốc.
- Đảm bảo process phát hành có chính sách patch/rebuild khi dependency CVE được công bố.

**Fat JAR là dạng phân phối bytecode**, không phải cơ chế bảo mật.

## 19. Fat JAR không giống container image hay runtime image

Một số thuật ngữ có thể gây nhầm:

| Đối tượng | Chứa gì? | Đối tượng sử dụng |
| --- | --- | --- |
| **Thin JAR** | Mã dự án/resources | JVM với external dependencies trên classpath |
| **Fat JAR** | Mã dự án và dependencies được gộp | JVM tương thích |
| **Application distribution** | Thường nhiều JARs + launch scripts | Máy có JVM tương thích |
| **jlink runtime image** | Các Java modules/JVM runtime đã chọn, có thể kèm app modules theo thiết kế | Máy đích, không cần JDK đầy đủ |
| **jpackage installer/app image** | Ứng dụng cùng runtime/launcher theo nền tảng | End-user desktop/OS target |
| **Container image** | Layers chứa runtime và app/dependencies/config hợp lệ | Container runtime |
| **Native image** | Executable biên dịch ahead-of-time theo công cụ | OS/CPU target |

Nếu môi trường deployment đã có Java 17, fat JAR có thể tiện nhất. Nếu muốn không cần Java cài sẵn trên máy người dùng, fat JAR **không đủ**; cần đóng gói runtime hoặc native executable theo hệ sinh thái phù hợp.

### 19.1. Container layering

Nếu Dockerfile chỉ copy một fat JAR và file đó thay đổi sau mỗi build, layer ứng dụng có thể phải upload/lưu cache lại dù chỉ sửa một Java class nhỏ. Thin distribution có thể đặt dependencies ở layer ổn định và app classes ở layer thay đổi thường xuyên, cải thiện caching.

Một số công cụ containerization hỗ trợ tạo layered JAR/images hoặc dependency layers tối ưu. Không khẳng định mọi fat JAR đều kém hiệu quả: có strategies phân lớp; chỉ cần chọn pipeline deployment có căn cứ từ artifact rebuild cadence và registry caching.

## 20. Quyết định chiến lược theo use case

### 20.1. Bảng quyết định

| Tình huống | Lựa chọn khởi đầu hợp lý | Câu hỏi kiểm tra |
| --- | --- | --- |
| Java library cho consumer Gradle/Maven | **Thin JAR** | POM/Gradle Metadata có đúng api/runtime dependencies? |
| CLI muốn download một file chạy bằng java -jar | **Fat JAR** | Class/resource/service merging đã kiểm thử chưa? |
| Java application cài trên máy người dùng | **Application distribution** | Start scripts, JVM args, runtime libs và JDK requirement rõ chưa? |
| Microservice container hóa | Thin/layered distribution hoặc fat JAR tùy toolchain | Build cache, image size, CVE scanning, startup ra sao? |
| App server cung cấp Servlet API | Thin/provided API rõ ràng | CompileOnly/provided và classloader contract đã đúng chưa? |
| Plugin/library muốn giấu dependency conflict | Shade/relocate có kiểm soát | Public API/reflection/service metadata có đổi không? |
| JPMS modular app | Thin module path/jlink phù hợp | Module descriptors và split packages được giữ đúng? |
| Desktop app không muốn cài JRE | jpackage/runtime image | OS/CPU distribution/signing được thiết kế chưa? |
| Serverless Java runtime đã có sẵn | Fat JAR hoặc layer-based package | Limits, cold start, dependency/external config ra sao? |

### 20.2. Những câu hỏi trước khi chọn fat JAR

1. Người nhận artifact có JVM tương thích không?
2. Có yêu cầu chỉ một file deploy hay ZIP/TAR cũng chấp nhận?
3. Dependencies có ServiceLoader/providers và duplicate META-INF resources không?
4. Có thư viện được load bằng reflection, plugins hoặc classpath scanning không?
5. Có native libraries cần bundle riêng theo OS/CPU không?
6. Có cần publish thư viện cho consumer khác, hay chỉ deploy ứng dụng?
7. Ai chịu trách nhiệm cập nhật các libraries khi có CVE?
8. Metadata về licenses, NOTICE, SBOM, provenance được giữ ở đâu?
9. Có cần reproducible artifact checksum không?
10. CI có chạy smoke test **trên chính JAR đã đóng gói**, không chỉ **gradlew run** không?

Nếu câu trả lời chưa rõ, chọn **thin JAR/Application distribution** theo mặc định cho library/app và chỉ chuyển sang fat JAR khi lợi ích vận hành đủ rõ.

## 21. Những lỗi và ngộ nhận hay gặp

| Triệu chứng/Ngộ nhận | Nguyên nhân thực tế | Cách xử lý |
| --- | --- | --- |
| **java -jar app.jar** báo NoClassDefFoundError | Thin JAR không mang Commons/Jackson | Dùng java -cp kèm runtime libs, distribution hoặc fat JAR |
| **Main-Class not found** | Manifest thiếu/sai hoặc entrypoint package khác | Kiểm tra META-INF/MANIFEST.MF và mainClass |
| **java -cp** trên Windows không chạy | Dùng dấu **:** thay **;** | Dùng đúng OS classpath separator |
| **./gradlew run** thành công nhưng app.jar không chạy | run đã dùng runtimeClasspath từ Gradle | Thử release artifact trong môi trường sạch |
| **shadowJar** không tồn tại | Chưa áp dụng Shadow hoặc plugin ID/version sai | Dùng com.gradleup.shadow phù hợp |
| Plugin Shadow không resolve | Thiếu plugin repo/Gradle-Java compatibility | Kiểm tra pluginManagement, Gradle Wrapper, JDK |
| Fat JAR không chứa JUnit | Test dependencies không thuộc main runtimeClasspath | Đó là đúng cho production |
| Fat JAR thiếu provider qua ServiceLoader | META-INF/services bị EXCLUDE/merge sai | Dùng transformer và duplicate strategy phù hợp |
| Duplicate LICENSE/NOTICE | Nhiều libraries có cùng path | Thiết kế legal notices merge, không xóa bừa |
| NoClassDefFoundError khi fat JAR chạy | Excluded/minimized/externalized runtime dependency | Đọc runtimeClasspath, shadow config và jar contents |
| Class conflict vẫn xảy ra | Hai libraries có cùng FQCN | Giải quyết graph trước, relocate có kiểm soát nếu cần |
| UnsupportedClassVersionError | Dependency/runtime bytecode cần Java cao hơn | Chọn Java toolchain/dependency target phù hợp |
| IllegalAccessError/InaccessibleObjectException | JPMS/reflection boundaries | Không giải bằng merge JAR tùy tiện; kiểm tra module path/opens |
| java -jar được nhưng native load fail | Thiếu .dll/.so hoặc OS mismatch | Package native binaries và loader đúng |
| Fat JAR có META-INF chữ ký cũ | Merge đã làm signature không hợp lệ | Xử lý signature metadata và ký lại artifact nếu cần |
| App crash chỉ sau khi minimize | Class được load động bị loại | Exclude khỏi minimization, tăng integration tests |
| Shadow artifact không thấy trong Maven repo | Tạo shadowJar không tự publish mọi thứ | Cấu hình publication/component rõ |
| Publish fat library làm consumers trùng class | Bundle dependencies nhưng metadata/variants không phản ánh đúng | Giữ thin JAR hoặc công bố shaded variant có chủ đích |
| Application distribution không có JDK | Distribution thông thường chỉ chứa libs/scripts | Dùng jpackage/jlink/container khi cần JRE |
| Docker image lớn | Runtime/app layers chưa tối ưu | Dùng base image/layered dependencies, kiểm tra metrics |
| Checksum khác giữa cùng source | Timestamp/entry order/dynamic inputs | Bật reproducibility và pin tool/dependencies |
| CI quét một JAR mà không biết libraries | Fat JAR che coordinate metadata | Tạo SBOM/resolved dependency list |
| Một JAR tên -all nhưng vẫn cần external files | Shadow dependencies/config/JNI/runtime services ở ngoài | Đọc manifest + deployment contract |
| **compileOnly** được hiểu là tự bundle | compileOnly không thuộc runtimeClasspath mặc định | Xác minh provided runtime hoặc sửa dependency scope |
| License notice mất sau shading | DuplicatesStrategy.EXCLUDE vô điều kiện | Review notices/attribution trong output |
| Shadow relocation phá reflection | Runtime load class theo tên hardcode | Test code paths động, cấu hình relocation/exclusions |

### 21.1. Debug từ dependency graph đến artifact

~~~text
Ứng dụng không chạy sau khi đóng gói?
               |
               v
1. Thực sự dùng thin JAR hay shadowed JAR?
               |
               v
2. Manifest Main-Class có đúng không?
               |
               v
3. runtimeClasspath đã resolve những versions/artifacts nào?
               |
               v
4. Class cần thiết có nằm trong JAR hoặc external classpath?
               |
               v
5. META-INF/services/resources có bị merge/exclude sai?
               |
               v
6. Có reflection, JPMS, multi-release, signed JAR hay JNI?
               |
               v
7. Gradle Wrapper, plugin version và Java target có tương thích?
               |
               v
8. CI đã thử chính artifact được deploy chưa?
~~~

Công cụ hữu ích:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-lang3

./gradlew jar shadowJar --info
./gradlew tasks --all

jar tf build/libs/packaging-lab-1.0.jar
jar tf build/libs/packaging-lab-1.0-all.jar

java -jar build/libs/packaging-lab-1.0-all.jar
~~~

Đừng xóa **~/.gradle** hoặc bật **--refresh-dependencies** làm phản xạ đầu tiên với lỗi class không nằm trong fat JAR. Hãy kiểm tra artifact/classpath thật, vì cache không tự khắc phục dependency scope và packaging rules sai.

## 22. CI: kiểm chứng output và giữ artifacts phù hợp

Một pipeline nên kiểm tra **code** và **artifact deploy**, không chỉ kết luận từ task compileJava.

Ví dụ các bước Linux:

~~~bash
./gradlew --no-daemon clean test jar shadowJar copyRuntimeDeps installDist
java -jar build/libs/packaging-lab-1.0-all.jar
java -cp "build/libs/packaging-lab-1.0.jar:build/runtime-libs/*" demo.app.Main
jar tf build/libs/packaging-lab-1.0-all.jar \
  | grep 'org/apache/commons/lang3/StringUtils.class'
sha256sum build/libs/packaging-lab-1.0-all.jar
~~~

Kết quả chính từ hai lệnh chạy Java:

~~~text
MESSAGE=Hello, Gradle!
MESSAGE=Hello, Gradle!
~~~

Nếu chạy theo CI, có thể thêm shell assertion để yêu cầu stdout chính xác. Ví dụ:

~~~bash
actual="$(java -jar build/libs/packaging-lab-1.0-all.jar)"
test "$actual" = 'MESSAGE=Hello, Gradle!'
~~~

Đây là **smoke test thật trên packaged JAR**, khác với **./gradlew run**.

### 22.1. Ví dụ GitHub Actions minh họa

~~~yaml
name: Java packaging

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Build and verify artifacts
        run: |
          ./gradlew --no-daemon clean test jar shadowJar copyRuntimeDeps
          actual="$(java -jar build/libs/packaging-lab-1.0-all.jar)"
          test "$actual" = 'MESSAGE=Hello, Gradle!'

      - name: Upload JAR artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: packaging-artifacts
          path: |
            build/libs/*.jar
            build/reports/tests/**
            build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14
~~~

**Lưu ý:** đây là workflow thực hành, không tự động ký artifact, không tự publish release và không thay thế chính sách supply-chain security của tổ chức. Nếu cần phát hành artifact chính thức, chỉ publish khi test/smoke validation thành công và artifact digest đã được ghi nhận.

### 22.2. Không upload các dependency secrets

Nếu CLI dùng config chứa API token, file đó không nên nằm trong **src/main/resources** hoặc tự đóng vào JAR. Dùng runtime environment/secret manager theo policy. Chỉ upload JAR/reports đã kiểm tra, hạn chế quyền truy cập và thời hạn lưu.

### 22.3. Version pinning

- Commit Gradle Wrapper JAR/properties và xác minh distribution.
- Pin Shadow plugin version tương thích.
- Pin hoặc lock resolved runtime dependencies.
- Kiểm tra checksum của third-party artifacts nếu policy yêu cầu.
- Review dependency update vì một fat JAR có thể nhúng lỗ hổng của thư viện cũ.
- Lưu SBOM và release digest cho deployment.

## 23. Bài tập tự thực hành

### Bài 1 — So sánh nội dung JAR

Tạo thin và fat JAR theo lab rồi dùng **jar tf** tìm:

- **demo/app/Main.class**.
- **demo/app/TextFormatter.class**.
- **org/apache/commons/lang3/StringUtils.class**.
- **org/junit/jupiter/api/Test.class**.

Giải thích vì sao ba class đầu theo kỳ vọng nằm trong fat JAR, còn JUnit không thuộc production runtime artifact.

### Bài 2 — Lỗi classpath có chủ đích

Chạy thin JAR bằng **java -jar** và quan sát lỗi. Sau đó chạy bằng **java -cp** với **build/runtime-libs/**. Giải thích vì sao cùng một file app.jar có thể fail ở lệnh đầu và pass ở lệnh sau.

### Bài 3 — Application distribution

Chạy:

~~~bash
./gradlew installDist
~~~

Mở **build/install/packaging-lab/**. Kiểm tra **bin/** và **lib/**. Vì sao **lib/** có Commons JAR riêng nhưng ứng dụng vẫn được chạy dễ dàng qua script?

### Bài 4 — Bỏ Commons Lang khỏi runtime

Tạm đổi **implementation** thành **compileOnly** cho Commons Lang, rebuild thin/fat. Vì sao compile có thể pass nhưng runtime fat JAR thiếu class? Khôi phục **implementation**.

### Bài 5 — Đổi version dependency

Đổi Commons Lang sang một version hợp lệ tương thích, chạy **dependencyInsight**, **shadowJar**, **jar tf** và smoke test. Mục đích là hiểu rằng bundled dependency phản ánh **resolved artifact**, không phải JAR đã copy thủ công từ cache cũ.

### Bài 6 — Shadow version compatibility

Thử đọc **./gradlew --version** và Shadow compatibility matrix. Nếu Wrapper thấp hơn mức yêu cầu của plugin, chọn phương án nâng Wrapper có kiểm soát hoặc pin Shadow version tương thích. Không giảm Java target tùy tiện chỉ để bỏ qua plugin compatibility error.

### Bài 7 — ServiceLoader

Tạo hai dependencies dùng cùng **META-INF/services/<service-interface>**, sau đó so sánh cách đọc provider khi chạy thin distribution và fat JAR. Cấu hình **mergeServiceFiles()** cùng duplicate handling phù hợp và kiểm thử cả hai providers xuất hiện.

### Bài 8 — Không lạm dụng relocation

Thử relocation một package trong branch thử nghiệm và kiểm tra **jar tf**. Giải thích vì sao các code path dùng **Class.forName** có thể cần test/exclusions khác với code tham chiếu class tĩnh.

### Bài 9 — Reproducible checksum

Xây fat JAR hai lần từ cùng inputs trên cùng Gradle/JDK, so sánh SHA256. Nếu khác, kiểm tra timestamps/order, tool versions và nondeterministic generated inputs trước khi kết luận plugin lỗi.

### Bài 10 — Publish library

Giả sử module trở thành thư viện cho nhiều teams. So sánh hệ quả của publish thin JAR với fat JAR về **POM, Gradle Module Metadata, duplicate classes và consumer dependency graph**. Khi nào nên dùng một shaded variant riêng?

### Bài 11 — Security review

Liệt kê các runtime libraries trong fat JAR từ resolved dependency graph; đối chiếu license notices, SBOM và vulnerability scans. Vì sao chỉ quét tên file **packaging-lab-1.0-all.jar** không đủ để hiểu library components bên trong?

### Bài 12 — Deployment thử trên máy sạch

Chạy fat JAR trên môi trường có Java17 nhưng không có Gradle cache hoặc Commons JAR riêng. Chạy thin JAR chỉ với main artifact và quan sát khác biệt. Sau đó copy đúng runtime libs/start scripts để thin distribution chạy thành công.

## 24. Câu hỏi kiểm tra

1. Thin JAR thường chứa những loại file nào?
2. Vì sao Java plugin **jar** không tự bundle runtimeClasspath?
3. Có Main-Class trong manifest có đồng nghĩa đủ dependency không?
4. **java -jar** khác **java -cp** trong cách chỉ định runtime entrypoint/classpath thế nào?
5. **implementation**, **runtimeOnly** và **compileOnly** khác nhau ra sao khi bundle?
6. **testImplementation** có nên xuất hiện trong fat JAR production không?
7. Application plugin dùng task nào để tạo distribution có launch scripts?
8. Shadow plugin hiện đại sử dụng plugin ID nào?
9. **shadowJar** mặc định bundle dependencies từ configuration nào?
10. Classifier mặc định cho Shadow JAR là gì?
11. Fat JAR có chứa JDK không?
12. Tại sao **./gradlew run** pass không chứng minh thin JAR có thể chạy một mình?
13. Khi nào có thể dùng **shadow** configuration để externalize dependencies?
14. Vì sao ServiceLoader có thể hỏng sau khi merge resources?
15. DuplicatesStrategy.EXCLUDE có thể gây mất dữ liệu gì?
16. Vì sao **mergeServiceFiles()** cần xem lại duplicate handling?
17. Khi nào relocation hữu ích và khi nào rủi ro?
18. Vì sao **minimize()** có thể bỏ nhầm class cần cho reflection?
19. Signed JAR còn giữ chữ ký hợp lệ sau shading không?
20. JPMS module descriptors có thể merge đơn giản không?
21. Fat JAR có bảo đảm native JNI library chạy trên mọi OS không?
22. Một JAR lớn có luôn là fat JAR đúng không?
23. Vì sao thin JAR thường phù hợp cho library publishing?
24. Khi nào dùng jlink/jpackage thay vì chỉ fat JAR?
25. Cách nào kiểm tra **StringUtils.class** nằm trong artifact?
26. Vì sao cần chạy smoke test trên **chính fat JAR** trong CI?
27. SBOM giải quyết vấn đề gì khi nhiều dependencies đã bị gộp?
28. Hash SHA256 giúp kiểm chứng điều gì, và không chứng minh điều gì?
29. **jar**, **assemble**, **shadowJar**, **publish** có cùng ý nghĩa không?
30. Làm sao xác nhận resolved dependency version thay vì chỉ đọc build.gradle?

**Đáp án gợi ý:** (1) classes/resources/main metadata; (2) Java plugin tách artifact khỏi dependency graph; (3) không; (4) jar dùng manifest entrypoint, cp cho phép khai báo classpath và main class; (5) runtimeClasspath thường có implementation/runtimeOnly nhưng không có compileOnly; (6) không; (7) installDist/distZip/distTar; (8) com.gradleup.shadow; (9) runtimeClasspath; (10) all; (11) không; (12) run dùng Gradle runtime classpath; (13) khi dependency được deployment cung cấp ngoài; (14) mất provider descriptors; (15) class/resource/license/service entries; (16) filtering có thể xảy ra trước transformer; (17) xử lý package conflicts nhưng có thể hỏng reflection/API; (18) usage động không hiện trong phân tích tĩnh; (19) không giữ nguyên mặc định sau merge; (20) không; (21) không; (22) không; (23) consumer resolve đúng metadata; (24) khi cần runtime image/installer; (25) jar tf; (26) xác minh artifact được deploy, không phải Gradle classpath; (27) xác định bên thứ ba và versions/licenses; (28) định danh bytes, không bảo đảm an toàn; (29) không; (30) dependencies/dependencyInsight.

## 25. Checklist trước khi phát hành

- [ ] Xác định artifact dành cho **library consumer**, **CLI user** hay **runtime deployment**.
- [ ] Chọn rõ thin JAR, Application distribution hoặc fat JAR theo use case.
- [ ] **jar** và **shadowJar** được kiểm tra bằng task graph/outputs thật.
- [ ] Manifest Main-Class đúng, không nhầm với việc bundle dependencies.
- [ ] Resolved **runtimeClasspath** được xem lại, không dựa trên requested dependencies.
- [ ] Không bundle **testImplementation**, **testRuntimeOnly**, **annotationProcessor** vào production.
- [ ] **compileOnly/provided** dependencies có runtime contract thật.
- [ ] Fat JAR chứa những classes cần thiết và không chứa test/secret files.
- [ ] Application distribution có launch scripts và runtime JARs đúng layout.
- [ ] Service descriptors, duplicate resources, LICENSE/NOTICE được xử lý đúng.
- [ ] Đã cân nhắc signed metadata, JPMS, multi-release, JNI và reflection.
- [ ] Không bật **minimize** hoặc **relocate** khi chưa có runtime tests phù hợp.
- [ ] Plugin Shadow/Gradle Wrapper/JDK version tương thích.
- [ ] Artifact được kiểm tra bằng **jar tf**, **java -jar** hoặc **java -cp** theo cách deploy.
- [ ] Nếu có distribution ZIP/TAR, đã thử giải nén/chạy trên môi trường sạch.
- [ ] Có SBOM/license list/vulnerability review theo policy tổ chức.
- [ ] Build reproducibility settings, dependency locking/verification phù hợp.
- [ ] SHA256/digest và source commit được ghi nhận.
- [ ] CI có test + smoke test trên artifact cuối, không chỉ Gradle run.
- [ ] Fat library publications/variants/metadata đã được kiểm tra nếu publish.
- [ ] Không nhầm executable JAR với Java runtime/container image.
- [ ] Secrets/config production không được hardcode hoặc nhét vào JAR.

## 26. Tài liệu chính thức và nguồn tham khảo

- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Dependency Management for Java Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [GradleUp Shadow — Introduction](https://gradleup.com/shadow/)
- [GradleUp Shadow — Getting Started](https://gradleup.com/shadow/getting-started/)
- [GradleUp Shadow — Configuration](https://gradleup.com/shadow/configuration/)
- [GradleUp Shadow — Merge/Service Files](https://gradleup.com/shadow/configuration/merging/)
- [GradleUp Shadow — Minimizing](https://gradleup.com/shadow/configuration/minimizing/)
- [GradleUp Shadow — Application Plugin Integration](https://gradleup.com/shadow/application-plugin/)
- [GradleUp Shadow — Reproducible Builds](https://gradleup.com/shadow/configuration/reproducible-builds/)
- [Gradle Plugin Portal — com.gradleup.shadow](https://plugins.gradle.org/plugin/com.gradleup.shadow)

**Kết luận:** **Thin JAR** giữ mã dự án và để runtime/dependency management bên ngoài, phù hợp cho libraries và distributions có classpath được quản lý. **Fat JAR** gom mã dự án cùng runtime libraries để triển khai một file thuận tiện, nhưng việc bundling kéo theo trách nhiệm về dependency selection, META-INF resource merge, ServiceLoader, licenses, security và publication metadata. Cách học đúng là tạo cả hai artifact từ cùng Gradle project Java 17, kiểm tra classpath/JAR contents và chạy chính artifact trên runtime thực, rồi chọn giải pháp đóng gói dựa trên nhu cầu triển khai thay vì giả định “một file lớn luôn tốt hơn”.
