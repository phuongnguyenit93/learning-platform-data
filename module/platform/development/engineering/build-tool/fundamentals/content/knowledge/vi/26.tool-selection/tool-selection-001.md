# Các tiêu chí lựa chọn: hệ sinh thái, quy ước và mức tùy biến

Chọn build tool cho một dự án Java là quyết định ảnh hưởng lâu dài tới cách nhóm biên dịch mã nguồn, quản lý dependency, chạy test, đóng gói, xuất bản artifact và vận hành CI. Một công cụ có nhiều tính năng chưa chắc là lựa chọn phù hợp; một công cụ đơn giản cũng có thể trở thành giới hạn nếu dự án cần build nhiều module, nhiều nền tảng hoặc quy trình tạo artifact phức tạp.

Ba nhóm tiêu chí cần xem xét cùng nhau là:

- **Hệ sinh thái:** công cụ có hỗ trợ tốt ngôn ngữ, framework, plugin, IDE, repository và nền tảng CI mà dự án đang dùng không?
- **Quy ước:** công cụ có cung cấp cấu trúc và lifecycle nhất quán để developer dễ hiểu, dễ onboarding và dễ tự động hóa không?
- **Mức tùy biến:** công cụ có đáp ứng được yêu cầu riêng mà không buộc nhóm phải viết quá nhiều build logic khó bảo trì không?

Trong Java, Maven và Gradle là hai lựa chọn phổ biến cho phần lớn ứng dụng và thư viện hiện đại. Ant vẫn có chỗ đứng trong các dự án cũ hoặc quy trình build đặc thù. Với monorepo lớn, yêu cầu hermetic build hoặc nhiều ngôn ngữ, những hệ thống như Bazel cũng có thể đáng cân nhắc. Quyết định nên xuất phát từ đặc điểm dự án và năng lực vận hành của nhóm, không chỉ từ xu hướng hoặc sở thích cá nhân.

## 1. Bắt đầu từ nhu cầu của dự án

Trước khi so sánh tính năng, hãy mô tả dự án cần build tool làm gì. Một thư viện Java nhỏ có thể chỉ cần compile, test và publish JAR. Một nền tảng nhiều module có thể cần build graph phức tạp, code generation, kiểm thử tích hợp, đóng gói nhiều loại artifact và hỗ trợ nhiều nền tảng.

Các câu hỏi đầu tiên:

1. Dự án là thư viện, ứng dụng server, ứng dụng desktop, Android, plugin hay monorepo nhiều thành phần?
2. Có bao nhiêu module và dependency giữa các module phức tạp đến đâu?
3. Cần build những loại artifact nào: JAR, WAR, distribution, native binary hay container image?
4. Có dùng framework hoặc công nghệ yêu cầu plugin chuyên biệt không?
5. Build cần chạy trên hệ điều hành và JDK nào?
6. CI cần kiểm tra, ký, publish và deploy ra sao?
7. Quy trình hiện tại có yêu cầu tùy biến đặc biệt không?
8. Ai sẽ duy trì build logic trong vài năm tới?

Không nên chọn công cụ chỉ vì một task cụ thể có thể làm được. Hãy đánh giá toàn bộ vòng đời từ checkout source tới artifact được phát hành.

## 2. Ba build tool Java thường được cân nhắc

### 2.1. Maven

<text>**Maven**</text> sử dụng mô hình project object model (POM), lifecycle và plugin. Cấu hình thường được đặt trong `pom.xml`. Maven ưu tiên quy ước có sẵn: thư mục source, resource, test, phase build và vị trí output có mặc định phổ biến.

Ví dụ tối giản:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

Các phase như `compile`, `test`, `package`, `verify`, `install` và `deploy` tạo thành lifecycle. Plugin gắn goal vào các phase để thực hiện compile, test, đóng gói hoặc kiểm tra.

Maven thường phù hợp khi nhóm muốn cấu trúc chuẩn, quy trình dễ dự đoán, dependency metadata theo Maven ecosystem và một mô hình tương đối thống nhất giữa các dự án.

### 2.2. Gradle

<text>**Gradle**</text> mô hình hóa build thành task graph. Build script thường dùng Groovy DSL hoặc Kotlin DSL. Gradle cung cấp plugin ecosystem rộng, task API, dependency management, incremental execution, build cache và configuration cache.

Ví dụ tối giản với Kotlin DSL:

```kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}

tasks.test {
    useJUnitPlatform()
}
```

Các task như `compileJava`, `test`, `jar`, `check` và `build` được tạo bởi Java plugin. Plugin hoặc build logic của dự án có thể thêm task và nối chúng vào graph.

Gradle phù hợp khi dự án cần mô hình task linh hoạt, build logic có thể tái sử dụng, tối ưu incremental/cache hoặc tích hợp nhiều bước tạo artifact.

### 2.3. Ant

<text>**Apache Ant**</text> là công cụ build dựa trên target và task, thường được cấu hình trong `build.xml`. Ant có mô hình khá trực tiếp: target mô tả nhóm thao tác và có thể phụ thuộc target khác.

Ví dụ rút gọn:

```xml
<project name="sample-app" default="jar" basedir=".">
    <property name="src.dir" value="src"/>
    <property name="build.dir" value="build"/>
    <property name="classes.dir" value="${build.dir}/classes"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}" destdir="${classes.dir}" includeantruntime="false"/>
    </target>

    <target name="jar" depends="compile">
        <jar destfile="${build.dir}/sample-app.jar" basedir="${classes.dir}"/>
    </target>
</project>
```

Ant cung cấp các task để thao tác file, compile, archive và chạy lệnh. Dependency management, repository integration và các quy ước cấp cao thường được bổ sung bằng công cụ/plugin khác, ví dụ Apache Ivy hoặc build logic riêng.

Ant có thể phù hợp với hệ thống cũ, quy trình rất đặc thù hoặc nơi đã có lượng lớn build script Ant ổn định. Với dự án Java mới, nhóm cần cân nhắc chi phí tự quản lý nhiều quy ước và dependency behavior mà Maven/Gradle cung cấp sẵn.

## 3. So sánh tổng quan

| Tiêu chí | Maven | Gradle | Ant |
|---|---|---|---|
| Mô hình | POM, lifecycle, plugin goals | Task graph, plugin, build logic | Target và task |
| Cấu hình | XML | Groovy DSL hoặc Kotlin DSL | XML |
| Quy ước mặc định | Rõ và phổ biến | Có quy ước qua plugin, cấu hình linh hoạt hơn | Ít quy ước cấp cao hơn |
| Dependency management | Tích hợp chặt với Maven repository và POM | Tích hợp dependency resolution và variant model | Thường cần thêm Ivy hoặc cơ chế riêng |
| Tùy biến | Qua plugin, lifecycle và extension | Rất linh hoạt qua task/plugin/API | Trực tiếp, chi tiết và thủ công |
| Incremental/cache | Có cơ chế incremental theo plugin; hệ sinh thái cache tùy công cụ bổ sung | Có task input/output, incremental execution, build cache | Phụ thuộc target/task và cấu hình; ít mô hình cache chuẩn hơn |
| Multi-module | Reactor và parent POM | Multi-project build, composite build | Có thể tổ chức target/project nhưng cần tự thiết kế nhiều hơn |
| Onboarding | Dễ theo convention nếu biết Maven | Cần hiểu DSL, task graph và plugin model | Dễ hiểu thao tác cơ bản, build lớn dễ thành script riêng |
| Phù hợp thường gặp | Library/service Java theo convention | Build phức tạp, đa module, custom workflow | Legacy hoặc automation đặc thù |

Đây là so sánh về mô hình và đặc điểm phổ biến, không phải giới hạn tuyệt đối. Plugin, version, cấu trúc dự án và build logic thực tế có thể làm trải nghiệm khác đi đáng kể.

## 4. Tiêu chí 1: Hệ sinh thái plugin và thư viện tích hợp

Hệ sinh thái quyết định công cụ có thể tích hợp dễ dàng với công nghệ mà dự án sử dụng hay không. Một build tool tốt cần hỗ trợ những công việc thường ngày và các công nghệ đặc thù của dự án.

### 4.1. Framework và nền tảng

Hãy kiểm tra plugin hoặc hướng dẫn chính thức cho các công nghệ liên quan, ví dụ:

- Spring Boot và các framework server Java.
- Android Gradle Plugin nếu phát triển Android.
- Kotlin/JVM, Scala hoặc ngôn ngữ JVM khác.
- Quarkus, Micronaut hoặc framework native image.
- Protobuf/gRPC và code generation.
- Docker/container image và deployment tooling.
- Annotation processor, compiler plugin và static analysis.
- Test framework, coverage và mutation testing.

Không chỉ hỏi “có plugin không?”. Cần xem plugin có được duy trì, tương thích với build tool/JDK version đang dùng, có tài liệu và có được dùng rộng rãi trong hệ sinh thái đó không.

### 4.2. Chất lượng plugin

Khi đánh giá plugin, kiểm tra:

- Plugin có nguồn phát hành đáng tin cậy không?
- Có tài liệu cấu hình và ví dụ không?
- Release gần đây có tương thích với toolchain của dự án không?
- Issue và pull request có được xử lý không?
- Có test, changelog và chính sách version rõ không?
- Plugin có hỗ trợ configuration cache/incremental build nếu dự án cần không?
- Có yêu cầu quyền hoặc credential đặc biệt không?
- Có thể thay thế bằng tính năng built-in nếu plugin ngừng duy trì không?

Một plugin ít người dùng nhưng được vendor hỗ trợ có thể phù hợp hơn plugin phổ biến nhưng không đáp ứng yêu cầu bảo mật hoặc tương thích. Hãy đánh giá nguồn gốc và mức hỗ trợ thay vì chỉ nhìn số lượt tải.

### 4.3. IDE và developer tooling

IDE cần hiểu build model để import project, đồng bộ dependency, chạy test và debug. IntelliJ IDEA, Eclipse, VS Code và các công cụ khác có mức hỗ trợ khác nhau theo build tool và plugin.

Các câu hỏi nên thử trực tiếp:

- IDE có import project từ build file mà không cần cấu hình thủ công không?
- Thay đổi dependency có được đồng bộ đúng không?
- Test source set và generated source có được nhận diện không?
- Run configuration có dùng đúng JDK/toolchain không?
- Debug test/task có thuận tiện không?
- IDE có dùng wrapper của project hay version build tool cài trên máy?

Không nên chọn build tool chỉ theo trải nghiệm IDE của một developer. Hãy thử trên các IDE và hệ điều hành mà nhóm thực sự hỗ trợ.

### 4.4. Repository và phân phối dependency

Java ecosystem sử dụng Maven repository protocol rộng rãi. Maven và Gradle đều có thể đọc Maven repository; Gradle cũng có thể publish publication Maven. Vì vậy, một dự án dùng Gradle không bị khóa vào một loại repository riêng.

Khi đánh giá hệ sinh thái repository, hãy kiểm tra:

- Maven Central và repository nội bộ.
- Proxy/mirror, authentication và credential management.
- Snapshot/release policy.
- Dependency locking và verification.
- POM, Gradle Module Metadata và variant support.
- Artifact signing, SBOM và provenance.
- Publish plugin, sources/Javadoc và classifier.

Với thư viện Java được consumer dùng qua Maven hoặc Gradle, metadata publication có thể quan trọng hơn build tool mà producer sử dụng.

## 5. Tiêu chí 2: Quy ước và khả năng dự đoán

Quy ước giúp nhiều developer làm việc theo một cách thống nhất. Khi cấu trúc project và lệnh build quen thuộc, người mới dễ tìm source, test, resource, dependency và output.

### 5.1. Maven convention

Maven thường dùng cấu trúc:

```text
project/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   └── resources/
    └── test/
        ├── java/
        └── resources/
```

Các thư mục này có ý nghĩa chuẩn trong Maven. Nếu tuân theo convention, POM có thể ngắn hơn vì không cần khai báo mọi đường dẫn.

Lifecycle tạo một bộ lệnh quen thuộc:

```bash
mvn test
mvn package
mvn verify
mvn install
mvn deploy
```

Developer có thể hiểu mục tiêu của phase mà không cần biết toàn bộ plugin execution bên trong.

### 5.2. Gradle convention qua plugin

Gradle cũng có cấu trúc mặc định khi áp dụng Java plugin:

```text
project/
├── build.gradle.kts
├── settings.gradle.kts
└── src/
    ├── main/java/
    ├── main/resources/
    ├── test/java/
    └── test/resources/
```

Java plugin tạo các source set và task quen thuộc. Người dùng thường chạy:

```bash
./gradlew test
./gradlew check
./gradlew build
```

Gradle có convention, nhưng build script có thể thay đổi nhiều hơn. Nếu mỗi module tự đặt tên task, source directory và dependency policy, nhóm sẽ mất lợi ích của convention.

### 5.3. Ant và quy ước do nhóm định nghĩa

Ant không áp đặt cùng một cấu trúc Java project cấp cao như Maven. Nhóm có thể tự đặt target, property, directory và luồng build. Sự tự do này có ích khi tích hợp hệ thống cũ hoặc quy trình đặc biệt, nhưng khiến các dự án khác nhau dễ có cách vận hành khác nhau.

Nếu chọn Ant, nên chuẩn hóa:

- Tên target như `clean`, `compile`, `test`, `package`.
- Cấu trúc source/resource/output.
- Cách quản lý dependency và classpath.
- Cách truyền property theo môi trường.
- Cách chạy test và lưu report.
- Cách tạo artifact và publish.

### 5.4. Convention giúp giảm chi phí phối hợp

Một nhóm có nhiều repository sẽ được lợi khi mọi dự án dùng cùng cấu trúc và lệnh. Developer có thể chuyển giữa project mà không phải học lại từng build script.

Quy ước nên được áp dụng ở mức vừa đủ:

- Cấu trúc source/test thống nhất.
- Version JDK và plugin được quản lý tập trung.
- Lệnh build/verification chuẩn.
- Quy tắc dependency và repository chung.
- Quy ước versioning và publication.
- Logging/reporting nhất quán.

Không cần ép mọi dự án dùng cấu hình giống hệt nếu sản phẩm có yêu cầu khác. Hãy chuẩn hóa phần dùng chung và cho phép ngoại lệ có lý do.

## 6. Tiêu chí 3: Mức tùy biến cần thiết

Mức tùy biến là khả năng thay đổi quy trình build để đáp ứng yêu cầu riêng: sinh source, xử lý resource, chạy công cụ ngoài, tạo nhiều artifact, kiểm tra metadata, ký package hoặc tích hợp deployment.

Tùy biến có lợi khi nó giải quyết yêu cầu thật. Quá nhiều build logic tự viết có thể làm build khó đọc, khó debug và phụ thuộc vào một vài người hiểu rõ nội bộ.

### 6.1. Maven: tùy biến qua plugin và lifecycle

Maven có thể tùy chỉnh bằng:

- Plugin và plugin execution.
- Profile và property.
- Parent POM và `pluginManagement`.
- Extension và custom plugin.
- Lifecycle mapping theo packaging/plugin.

Ví dụ gắn plugin vào phase:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.2.5</version>
      <configuration>
        <useModulePath>false</useModulePath>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Ưu điểm là cấu hình theo cấu trúc plugin/lifecycle khá rõ. Hạn chế xuất hiện khi một quy trình rất khác lifecycle mặc định hoặc cần logic điều kiện phức tạp; khi đó POM có thể trở nên dài, nhiều profile và plugin execution khó theo dõi.

### 6.2. Gradle: task graph và build logic

Gradle cho phép định nghĩa task, khai báo input/output, nối task dependency, viết plugin convention và build logic dùng chung.

Ví dụ task nhỏ:

```kotlin
tasks.register("verifyGeneratedFile") {
    val generatedFile = layout.buildDirectory.file("generated/version.txt")
    inputs.file(generatedFile)

    doLast {
        val file = generatedFile.get().asFile
        check(file.isFile) { "Generated version file is missing" }
        check(file.readText().isNotBlank()) { "Generated version file is empty" }
    }
}
```

Gradle phù hợp khi workflow cần nhiều task riêng hoặc cần tạo convention plugin cho nhiều module. Tuy nhiên, cần tuân thủ task configuration avoidance, khai báo input/output đầy đủ và tránh thực thi công việc nặng ngay trong configuration phase.

### 6.3. Ant: điều khiển chi tiết target/task

Ant cho phép định nghĩa target và phụ thuộc target trực tiếp:

```xml
<target name="verify" depends="compile,test">
    <echo message="Verification completed"/>
</target>
```

Nhóm có thể phối hợp task built-in, macrodef, antlib và task custom. Khi build lớn, target có thể trở thành tập lệnh điều phối dài; cần tách file, đặt tên nhất quán và quản lý dependency rõ ràng.

## 7. Tùy biến không đồng nghĩa với khả năng bảo trì

Một build script có thể làm được gần như mọi thứ nhưng không có nghĩa nó dễ duy trì. Hãy đánh giá chi phí vòng đời:

- Người mới mất bao lâu để hiểu build?
- Có thể tìm thấy task nào tạo artifact không?
- Có thể biết input nào làm task chạy lại không?
- Khi plugin lỗi, có log và cách tái hiện rõ không?
- Có thể nâng JDK/build tool mà không sửa hàng chục module không?
- Build logic có test và tài liệu không?
- Có phụ thuộc API nội bộ hoặc hành vi undocumented không?

Một dấu hiệu build logic đã quá tùy biến là chỉ một người trong nhóm biết cách phát hành hoặc sửa task. Khi đó, công cụ đang tạo ra rủi ro vận hành dù vẫn đáp ứng tính năng.

## 8. Hệ sinh thái và mức hỗ trợ của cộng đồng/vendor

Không chỉ xem số lượng plugin. Cần đánh giá tính bền vững của hệ sinh thái:

| Tiêu chí | Câu hỏi đánh giá |
|---|---|
| Tài liệu | Có tài liệu chính thức, migration guide và ví dụ không? |
| Cộng đồng | Có nhiều người dùng, câu hỏi và lời giải không? |
| Release cadence | Có bản cập nhật và sửa lỗi đều đặn không? |
| Compatibility | Plugin có hỗ trợ JDK và build tool version mục tiêu không? |
| Security | Có quy trình xử lý lỗ hổng và phát hành bản vá không? |
| Ownership | Có maintainer/vendor chịu trách nhiệm không? |
| Migration | Có thể nâng version hoặc thay plugin khi cần không? |
| Observability | Có log, report, build scan hoặc chẩn đoán hữu ích không? |

Một plugin quan trọng nhưng bị bỏ không có thể khóa dự án vào version cũ của build tool. Hãy tính rủi ro này khi chọn công nghệ phụ thuộc plugin.

## 9. Khả năng tích hợp CI/CD

Build tool cần hoạt động nhất quán trên máy developer và CI. Hãy kiểm tra:

- Wrapper có thể tải đúng build tool version không?
- CI image có JDK/toolchain tương thích không?
- Có thể cache dependency và task output an toàn không?
- Test report có được xuất ra định dạng CI hiểu không?
- Có thể chạy task riêng cho module hoặc test cụ thể không?
- Artifact có thể được tạo, ký, publish và xác minh không?
- Có hỗ trợ secret injection và repository authentication không?
- Build có tái lập trong môi trường sạch không?
- Có thể phân tích thời gian task và bottleneck không?

### 9.1. Wrapper là tiêu chí quan trọng

Gradle Wrapper (`gradlew`, `gradlew.bat`, thư mục `gradle/wrapper/`) và Maven Wrapper (`mvnw`, `mvnw.cmd`, wrapper configuration) giúp repository xác định build tool version.

Wrapper giảm phụ thuộc vào phiên bản được cài toàn cục trên máy developer hoặc runner. Khi chọn build tool, nên đưa wrapper vào repository và hướng dẫn dùng wrapper thay vì lệnh global.

### 9.2. Cache và incremental build

Gradle có mô hình task input/output và build cache tích hợp. Điều này có thể mang lại lợi ích cho dự án nhiều module hoặc build có nhiều task lặp lại, nếu task được thiết kế cacheable và relocatable.

Maven có incremental behavior ở một số plugin và CI thường cache local repository dependency. Có thể bổ sung công cụ hoặc extension cho nhu cầu cache cụ thể. Không nên so sánh chỉ bằng một lần chạy có cache nóng; cần đo clean, warm và incremental build.

### 9.3. CI không nên phụ thuộc máy developer

Tránh để CI cần artifact chỉ có trong `mavenLocal()` hoặc Gradle local cache của một người. Dependency nội bộ cần được publish vào repository dùng chung hoặc được build trong cùng reactor/multi-project build.

## 10. Multi-module và monorepo

Quy mô và cấu trúc repository ảnh hưởng mạnh tới lựa chọn.

### 10.1. Maven reactor

Maven hỗ trợ multi-module qua parent POM và `<modules>`:

```xml
<packaging>pom</packaging>

<modules>
  <module>domain</module>
  <module>application</module>
  <module>web</module>
</modules>
```

Maven reactor sắp xếp module theo dependency relationship và có thể build các module liên quan trong cùng invocation. Cấu trúc parent/child POM và dependency management giúp quản lý version chung.

### 10.2. Gradle multi-project và composite build

Gradle dùng `settings.gradle(.kts)` để khai báo project:

```kotlin
include(":domain", ":application", ":web")
```

Multi-project build cho phép project phụ thuộc nhau trong cùng build. Composite build có thể kết hợp nhiều build độc lập, hữu ích khi phát triển plugin hoặc thư viện cùng ứng dụng consumer.

Gradle convention plugin và version catalog có thể giúp chuẩn hóa cấu hình nhiều module. Tuy nhiên, cần tránh tạo một build logic quá trừu tượng khiến module khó hiểu.

### 10.3. Ant trong dự án nhiều module

Ant có thể gọi target giữa các build file hoặc tổ chức target theo project. Tuy nhiên, dependency graph, version alignment và metadata publication thường cần được nhóm thiết kế rõ ràng hơn. Với monorepo lớn, hãy tính chi phí tự xây các quy ước này.

### 10.4. Khi nào cân nhắc Bazel?

Với monorepo rất lớn, nhiều ngôn ngữ, yêu cầu hermetic build và remote execution, Bazel hoặc một hệ thống tương tự có thể phù hợp. Nó có mô hình rule, action graph, sandboxing và cache phân tán mạnh.

Tuy nhiên, việc áp dụng Bazel thường đòi hỏi thay đổi cách tổ chức build, rule/toolchain và quy trình developer. Hệ sinh thái Java/plugin và quy trình IDE của tổ chức cần được thử nghiệm trước. Không nên chọn Bazel chỉ vì monorepo lớn; cần có nhu cầu về tính xác định, quy mô và remote execution đủ rõ để bù chi phí chuyển đổi.

## 11. Dependency management và version alignment

Build tool không chỉ compile source; nó còn quyết định dependency được tìm ở đâu và version nào được chọn.

Các câu hỏi:

- Có hỗ trợ Maven repository và repository nội bộ không?
- Có dependency constraints/platform/BOM không?
- Có lock version để build tái lập không?
- Có kiểm tra checksum/signature không?
- Có xử lý variant/classifier/capability không?
- Có giải thích được vì sao một version được chọn không?
- Có thể kiểm soát repository order và content filter không?

Maven có dependency management, BOM và mediation theo mô hình Maven. Gradle có version constraints, platforms, rich version, variant-aware resolution và dependency locking. Ant thường cần Ivy hoặc công cụ ngoài để cung cấp quản lý dependency ở mức tương tự.

### 11.1. BOM và dependency management

Một dự án nhiều module nên có cách quản lý version tập trung để tránh mỗi module chọn một version khác nhau. Maven có thể dùng `<dependencyManagement>` và import BOM; Gradle có thể dùng platform/BOM và version catalog.

Ví dụ Maven:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-dependencies</artifactId>
      <version>3.3.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
```

Ví dụ Gradle:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.0"))
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Version minh họa cần được chọn theo compatibility matrix của dự án. Điều quan trọng là cơ chế quản lý version nhất quán và có thể kiểm tra.

## 12. Khả năng kiểm soát lifecycle và task graph

Maven lifecycle giúp developer biết phase nào sẽ chạy. Điều này thuận lợi cho quy trình chuẩn, nhưng một task không nằm trong lifecycle cần được gắn vào phase hoặc gọi rõ ràng.

Gradle task graph cho phép mô hình hóa quan hệ giữa task. Điều này hữu ích khi build có các bước tạo code, kiểm tra artifact, sinh tài liệu hoặc chạy nhiều loại test. Đổi lại, developer cần hiểu task dependency, task ordering, lazy configuration và input/output.

Ant target có thể mô tả thứ tự trực tiếp, nhưng nhóm phải tự định nghĩa cấu trúc và quy tắc nhất quán.

| Nhu cầu | Maven | Gradle | Ant |
|---|---|---|---|
| Quy trình compile-test-package chuẩn | Lifecycle phase | Task lifecycle/plugin | Tự định nghĩa target |
| Task custom có input/output rõ | Plugin goal/mojo hoặc plugin có sẵn | Task API và typed properties | Task và property/file set |
| Điều phối task phức tạp | Plugin/lifecycle/profile | Task graph và dependency | Target dependency |
| Tránh chạy task không cần thiết | Plugin incremental support | Up-to-date checking/build cache | Tùy task và target logic |
| Build logic tái sử dụng | Parent POM/plugin | Convention plugin/build logic | Macrodef/antlib/script riêng |

## 13. Khả năng kiểm thử và chất lượng build

Build tool cần kết nối test framework, static analysis, coverage, integration test và kiểm tra artifact.

Hãy xem xét:

- JUnit/TestNG và test discovery.
- Unit test, integration test, test suite riêng.
- Parallel execution và test isolation.
- HTML/XML test reports.
- JaCoCo hoặc công cụ coverage.
- Checkstyle, PMD, SpotBugs hoặc static analysis khác.
- Test artifact đã đóng gói.
- Quality gate trong CI.

Maven thường dùng Surefire cho unit test và Failsafe cho integration test. Gradle có Test task và source set; plugin khác có thể bổ sung test suite. Ant có thể gọi JUnit task/plugin nhưng cần nhóm cấu hình lifecycle và report rõ ràng.

Không nên đánh giá công cụ chỉ dựa vào việc “chạy được JUnit”. Cần xem test report có tích hợp CI, test filtering có thuận tiện, parallel execution có ổn định và integration test có được đưa vào lệnh verification chuẩn không.

## 14. Hiệu năng và khả năng mở rộng

Build performance phụ thuộc cả công cụ lẫn cách dự án sử dụng nó.

Các yếu tố nên đo:

- Thời gian cấu hình project.
- Clean build và incremental build.
- Số task có thể chạy song song.
- Cache hit/miss và thời gian khôi phục output.
- Dependency download và repository latency.
- Peak CPU/RAM và I/O.
- Thời gian test.
- Hiệu năng CI khi nhiều job chạy đồng thời.

Gradle có các tính năng build cache, incremental execution và configuration cache. Maven có incremental behavior qua compiler/plugin và các cơ chế cache dependency; hiệu năng có thể cải thiện bằng cấu hình/plugin phù hợp. Ant có thể chạy nhanh cho workflow đơn giản, nhưng build lớn có thể cần nhóm tự tối ưu target và dependency.

Không nên kết luận Gradle luôn nhanh hơn Maven hoặc ngược lại. Hãy benchmark trên một phần đại diện của dự án, với clean/warm/incremental build và cùng điều kiện môi trường.

## 15. Khả năng bảo trì và kỹ năng của nhóm

Build tool là mã hạ tầng mà nhóm phải duy trì. Lựa chọn phù hợp phụ thuộc kỹ năng hiện có và khả năng đào tạo.

Đánh giá:

- Bao nhiêu thành viên đã sử dụng công cụ?
- Có người chịu trách nhiệm build logic không?
- Có thể review thay đổi build như code ứng dụng không?
- Có quy trình nâng version và kiểm tra plugin không?
- Có thể debug lỗi build mà không cần chuyên gia bên ngoài không?
- Có tài liệu nội bộ và convention plugin/parent POM dùng chung không?
- Có đủ người duy trì custom plugin hoặc task không?

Một công cụ mạnh nhưng chỉ một người hiểu có thể tạo single point of failure. Một công cụ quen thuộc với nhóm có thể giúp onboarding nhanh và giảm rủi ro vận hành.

### 15.1. Tính dễ đọc

Build file nên trả lời nhanh:

- Project dùng plugin nào?
- Dependency được khai báo ở đâu?
- Task chuẩn để build/test là gì?
- Artifact nằm ở đâu?
- Cấu hình nào thay đổi theo môi trường?
- Task custom có input/output gì?

Nếu câu trả lời bị phân tán qua nhiều script, plugin nội bộ và điều kiện phức tạp, hãy cải thiện tài liệu hoặc convention trước khi thêm tùy biến.

## 16. Bảo mật và supply chain

Build tool có thể tải và thực thi plugin, annotation processor, code generator và dependency. Chọn công cụ cũng cần xét khả năng quản lý nguồn và xác minh các thành phần đó.

Các tiêu chí:

- Wrapper distribution có thể xác minh checksum không?
- Plugin/dependency version có được pin hoặc lock không?
- Repository có thể giới hạn theo namespace/group không?
- Credential có thể được cấp từ secret manager mà không commit không?
- Có dependency verification hoặc signature verification không?
- Có thể tạo SBOM và provenance không?
- Có thể tách quyền đọc dependency và quyền publish artifact không?
- Có thể audit ai publish package không?

Maven và Gradle đều có thể tích hợp repository authentication, locking/verification và công cụ supply-chain. Ant có thể sử dụng công cụ ngoài nhưng cần nhóm thiết kế và duy trì cách tích hợp.

Không nên cho rằng một build tool mặc định làm dự án an toàn. Cấu hình repository, quyền CI, nguồn plugin và quy trình release mới quyết định phần lớn mức bảo vệ thực tế.

## 17. Tính tái lập và khả năng di chuyển

Một build tốt nên chạy nhất quán trên developer machine và CI, đồng thời tạo artifact có thể kiểm tra lại.

Hãy đánh giá:

- Có wrapper pin version không?
- Có thể cố định JDK/toolchain không?
- Dependency có version rõ và lock được không?
- Archive có reproducible timestamp/order không?
- Task có khai báo input/output đầy đủ không?
- Build có phụ thuộc absolute path hoặc trạng thái máy không?
- Có thể chạy offline sau khi dependency đã được tải không?
- Có thể build trong container/agent sạch không?

Gradle có hỗ trợ cacheable task và relocatable build output nếu task được mô hình hóa đúng. Maven có thể hỗ trợ reproducible archive qua plugin và `project.build.outputTimestamp` trong các plugin tương thích. Với Ant, tính tái lập thường phụ thuộc vào cách target và task được viết.

## 18. Chi phí chuyển đổi và khả năng tương thích ngược

Chọn build tool mới có thể kéo theo chi phí:

- Viết lại build script và plugin configuration.
- Chuyển dependency management và publication metadata.
- Thay đổi CI pipeline và cache.
- Cập nhật IDE, developer documentation và onboarding.
- Thay thế custom task hoặc integration.
- Kiểm tra artifact có tương đương về nội dung và behavior không.
- Hỗ trợ các module chưa thể migrate ngay.

Không nên migration chỉ vì công cụ mới có một tính năng hấp dẫn. Hãy xác định vấn đề cụ thể của hệ thống hiện tại và tính lợi ích dài hạn so với chi phí chuyển đổi.

### 18.1. Có thể dùng nhiều build tool không?

Một repository có thể tồn tại build script Ant cũ cùng Maven/Gradle mới trong giai đoạn chuyển tiếp. Tuy nhiên, cần tránh để mỗi công cụ tự tạo artifact khác nhau hoặc quản lý dependency theo cách mâu thuẫn.

Nếu duy trì nhiều build tool:

- Xác định build tool nào là nguồn chuẩn cho release.
- Đồng bộ version và dependency.
- So sánh artifact output giữa hai quy trình.
- Giữ CI entry point rõ ràng.
- Đặt thời hạn hoặc tiêu chí kết thúc migration nếu có kế hoạch loại bỏ công cụ cũ.

## 19. Ma trận quyết định theo tình huống

| Tình huống | Lựa chọn thường đáng cân nhắc | Lý do |
|---|---|---|
| Thư viện Java phổ biến, lifecycle chuẩn, publication Maven | Maven hoặc Gradle | Cả hai có ecosystem Java và Maven repository tốt |
| Ứng dụng Java nhiều module, nhiều task custom | Gradle hoặc Maven tùy độ phức tạp | Gradle task graph linh hoạt; Maven phù hợp nếu workflow vẫn theo lifecycle/plugin chuẩn |
| Nhóm muốn convention mạnh, POM dễ đọc và lệnh lifecycle thống nhất | Maven | Mô hình POM/lifecycle có quy ước rõ |
| Build cần custom workflow, code generation và cache/incremental tuning | Gradle | Task API và plugin model hỗ trợ tùy biến sâu |
| Dự án cũ có Ant script ổn định, chi phí migration cao | Tiếp tục Ant có kiểm soát | Tránh migration không đem lại giá trị đủ lớn |
| Quy trình automation file-centric hoặc build legacy rất đặc thù | Ant có thể phù hợp | Target/task trực tiếp và dễ tích hợp lệnh ngoài |
| Monorepo rất lớn, đa ngôn ngữ, yêu cầu hermetic/remote execution | Đánh giá Bazel hoặc hệ thống tương tự | Mô hình action/rule/cache có thể phù hợp quy mô đặc thù |
| Android app | Gradle với Android Gradle Plugin | Đây là hệ sinh thái build chuẩn của Android hiện đại |

Ma trận chỉ là điểm khởi đầu. Cần xác minh plugin, version, IDE và quy trình CI thực tế của dự án.

## 20. Một quy trình lựa chọn có thể áp dụng

### Bước 1: Liệt kê yêu cầu bắt buộc

Viết danh sách những điều công cụ phải hỗ trợ, ví dụ:

- JDK 21 và Java toolchain.
- Multi-module build.
- JUnit 5 và integration test.
- Tạo executable JAR và distribution ZIP.
- Publish Maven package vào repository nội bộ.
- Chạy trên Linux CI và Windows developer machine.
- Dependency locking và artifact verification.

Phân biệt yêu cầu bắt buộc với tính năng “có thì tốt”.

### Bước 2: Kiểm tra hệ sinh thái

Với mỗi công nghệ, xác định plugin/tool chính thức, mức duy trì, tài liệu, compatibility và support. Thử một project mẫu thay vì chỉ đọc danh sách tính năng.

### Bước 3: Đánh giá quy ước

Kiểm tra cấu trúc source, test, resource, task/lifecycle và cách quản lý dependency. Hãy xem một developer mới có thể build/test mà không phải đọc nhiều tài liệu riêng không.

### Bước 4: Đánh giá phần cần tùy biến

Liệt kê custom task/plugin cần có. Phân loại:

- Có sẵn trong plugin chính thức.
- Có plugin bên thứ ba được duy trì.
- Cần build logic nhỏ.
- Cần custom plugin/task lớn.

Nếu phần lớn yêu cầu phải viết lại bằng script riêng, hãy tính chi phí bảo trì.

### Bước 5: Benchmark trên workload đại diện

Thử clean build, incremental build, test và CI workflow. Dùng cùng source, JDK, dependency và runner class. Đo nhiều lần và ghi p50/p95, peak memory, cache behavior.

### Bước 6: Thử nghiệm với nhóm

Cho một vài developer thuộc các mức kinh nghiệm khác nhau thực hiện checkout, build, test, debug và publish thử. Ghi lại nơi họ cần trợ giúp hoặc phải dùng workaround.

### Bước 7: Đánh giá rủi ro dài hạn

Kiểm tra release cadence, plugin compatibility, security policy, wrapper upgrade và khả năng thay thế plugin. Tính chi phí migration và đào tạo.

### Bước 8: Ghi quyết định và lý do

Ghi lại lựa chọn, các phương án đã cân nhắc, trade-off, yêu cầu không đáp ứng và điều kiện đánh giá lại trong tương lai.

## 21. Mẫu scorecard để so sánh build tool

Có thể dùng scorecard có trọng số. Điểm số chỉ giúp tổ chức thảo luận; không thay thế thử nghiệm kỹ thuật.

Ví dụ trọng số:

| Tiêu chí | Trọng số gợi ý | Điều cần chứng minh |
|---|---:|---|
| Hệ sinh thái/plugin | 20% | Plugin cần thiết có hỗ trợ và được duy trì |
| Quy ước/dễ onboarding | 15% | Developer mới có thể build/test nhanh |
| Tùy biến | 15% | Đáp ứng workflow riêng mà build logic vẫn dễ bảo trì |
| Dependency/repository | 10% | Resolution, locking, verification và publish phù hợp |
| CI/performance | 15% | Build ổn định, incremental/cache phù hợp |
| IDE/developer experience | 10% | Import, run, test và debug thuận tiện |
| Bảo mật/reproducibility | 10% | Credential, wrapper, provenance và artifact được kiểm soát |
| Chi phí migration/vận hành | 5% | Đào tạo, hỗ trợ và nâng cấp nằm trong khả năng nhóm |

Nhóm có thể thay trọng số theo bối cảnh. Ví dụ, dự án Android sẽ tăng trọng số hệ sinh thái Gradle; thư viện Java enterprise theo quy trình Maven hiện có có thể tăng trọng số tương thích và chi phí vận hành.

### 21.1. Cách chấm điểm

Có thể dùng thang 1–5:

- 1: Không đáp ứng hoặc rủi ro lớn.
- 2: Đáp ứng một phần, cần workaround đáng kể.
- 3: Đáp ứng yêu cầu cơ bản.
- 4: Đáp ứng tốt, có tài liệu và support.
- 5: Rất phù hợp, đã được thử nghiệm trong bối cảnh dự án.

Không cho điểm 5 chỉ vì tính năng tồn tại trên trang tài liệu. Cần có bằng chứng từ project mẫu, plugin compatibility hoặc thử nghiệm CI.

## 22. Ví dụ lựa chọn cho ba loại dự án

### 22.1. Thư viện Java dùng chung

Yêu cầu:

- Compile và test nhanh.
- Tạo JAR, sources JAR và Javadoc JAR.
- Publish POM/metadata vào Maven repository.
- Consumer dùng được từ Maven và Gradle.
- Versioning và release bất biến.

Maven thường là lựa chọn tự nhiên nếu nhóm muốn POM/lifecycle chuẩn và publication đơn giản. Gradle cũng phù hợp nếu nhóm đã có convention plugin hoặc cần build logic phức tạp. Điểm quyết định là metadata publication, consumer compatibility và năng lực duy trì, không phải chỉ ngôn ngữ của build file.

### 22.2. Ứng dụng server nhiều module

Yêu cầu:

- Nhiều module domain/application/infrastructure.
- Unit, integration và contract test.
- Sinh source từ schema.
- Tạo executable JAR hoặc distribution.
- Build cache và incremental build để rút ngắn CI.
- Nhiều task kiểm tra artifact.

Gradle có thể phù hợp nhờ task graph và convention plugin, đặc biệt khi custom workflow nhiều. Maven vẫn phù hợp nếu các bước có plugin tốt và có thể mô hình hóa trong lifecycle. Hãy benchmark trên repository thực và tính chi phí build logic.

### 22.3. Hệ thống legacy dùng Ant

Yêu cầu:

- Build hiện tại ổn định.
- Nhiều target custom và công cụ nội bộ.
- Không có yêu cầu mới buộc phải thay đổi.
- Migration có thể ảnh hưởng quy trình phát hành lớn.

Tiếp tục dùng Ant có thể hợp lý nếu nhóm kiểm soát được dependency, version, test, security và tài liệu. Không cần migration chỉ để dùng công cụ mới hơn. Nếu muốn hiện đại hóa, có thể bắt đầu bằng một module hoặc quy trình mới, đo lợi ích và lên kế hoạch chuyển dần.

## 23. Những dấu hiệu lựa chọn chưa phù hợp

- Mỗi module phải có một cách build khác nhau mà không có lý do sản phẩm.
- Build script chứa nhiều logic điều kiện theo máy developer.
- Chỉ một người biết cách tạo release.
- Plugin quan trọng không còn được duy trì hoặc không tương thích JDK mới.
- CI cần dùng artifact trong local repository của một người.
- Build không thể chạy bằng wrapper trong môi trường sạch.
- Thêm một dependency nhỏ khiến phải sửa nhiều file cấu hình không liên quan.
- Tùy biến quá nhiều đến mức không thể giải thích task graph/lifecycle.
- Không có cách kiểm tra artifact hoặc truy vết dependency.
- Thời gian build tăng nhưng nhóm không có số liệu để xác định bottleneck.

Khi gặp các dấu hiệu này, có thể cần chuẩn hóa convention, nâng cấp plugin, tách build logic, bổ sung wrapper hoặc xem xét migration. Không nên mặc định phải đổi toàn bộ build tool; đôi khi sửa cách sử dụng hiện tại đem lại lợi ích lớn hơn.

## 24. Những lỗi thường gặp khi chọn build tool

| Lựa chọn sai | Hệ quả | Cách đánh giá tốt hơn |
|---|---|---|
| Chọn theo xu hướng | Công cụ mới nhưng nhóm thiếu kỹ năng và plugin phù hợp | Đánh giá yêu cầu, ecosystem và chi phí đào tạo |
| Chỉ nhìn số plugin | Plugin quan trọng có thể cũ hoặc không tương thích | Kiểm tra maintainer, release, issue và compatibility |
| Coi nhiều tùy biến là ưu điểm tuyệt đối | Build logic khó hiểu và khó nâng cấp | Đo chi phí bảo trì và khả năng tái sử dụng |
| Chỉ so sánh clean build | Bỏ qua incremental developer workflow | Đo clean, warm, incremental, test và CI |
| Bỏ qua IDE | Developer phải cấu hình thủ công và khó debug | Thử import/run/test trên IDE nhóm sử dụng |
| Không kiểm tra repository publication | Consumer không phân giải dependency đúng | Tạo consumer project và kiểm tra POM/module metadata |
| Dùng Ant cho build mới mà không có convention | Mỗi project tự định nghĩa lifecycle và dependency | Cân nhắc Maven/Gradle hoặc xây convention rõ ràng |
| Migration toàn bộ chỉ vì một plugin | Chi phí chuyển đổi vượt lợi ích | Thử tích hợp plugin hoặc thay một phần trước |
| Chỉ dựa vào local cache | CI/developer khác không tái hiện được | Kiểm tra wrapper, remote repository và môi trường sạch |
| Không ghi quyết định | Nhóm lặp lại tranh luận khi thay đổi nhân sự | Lưu decision record và điều kiện đánh giá lại |

## 25. Mẫu decision record

Một quyết định chọn build tool nên được ghi ngắn gọn nhưng có bằng chứng.

```text
Decision:
Chọn [Maven / Gradle / Ant / công cụ khác] cho [dự án].

Context:
- Loại sản phẩm:
- Số module:
- JDK/toolchain:
- Framework/plugin chính:
- CI và repository:
- Yêu cầu build đặc thù:

Requirements:
- Bắt buộc:
- Mong muốn:

Options considered:
- Option A:
- Option B:
- Option C:

Evaluation:
- Ecosystem/plugin support:
- Conventions/onboarding:
- Customization/maintenance:
- Dependency/publication:
- CI/performance:
- Security/reproducibility:
- Migration/operations cost:

Decision and trade-offs:
- Lý do chọn:
- Điều chấp nhận đánh đổi:
- Rủi ro cần theo dõi:

Evidence:
- Project sample:
- Build commands and measurements:
- IDE/CI trial:
- Plugin compatibility:

Revisit when:
- Điều kiện khiến nhóm đánh giá lại quyết định.
```

Decision record giúp nhóm hiểu lựa chọn dựa trên bối cảnh nào. Khi JDK, framework, quy mô hoặc CI thay đổi, nhóm có thể đánh giá lại bằng cùng bộ tiêu chí.

## 26. Nguyên tắc cần ghi nhớ

- Bắt đầu từ nhu cầu của dự án, không bắt đầu từ danh sách tính năng của công cụ.
- Hệ sinh thái gồm plugin, framework, IDE, repository, tài liệu và mức duy trì.
- Quy ước giúp project nhất quán và giảm chi phí onboarding.
- Maven nổi bật với POM/lifecycle và convention; Gradle nổi bật với task graph và khả năng tùy biến; Ant cho phép điều khiển target/task trực tiếp nhưng cần tự xây nhiều quy ước hơn.
- Tùy biến phải đi cùng khả năng đọc, kiểm thử và bảo trì build logic.
- Đánh giá multi-module, dependency management, test, publication, CI, cache và reproducibility trên workload thật.
- Wrapper và toolchain giúp developer/CI dùng cùng phiên bản công cụ.
- Plugin quan trọng cần được kiểm tra nguồn gốc, compatibility và tình trạng duy trì.
- Không migration chỉ vì xu hướng; so sánh lợi ích dài hạn với chi phí chuyển đổi.
- Ghi lại quyết định, trade-off và điều kiện đánh giá lại để nhóm có thể tiếp tục duy trì lựa chọn.

Lựa chọn build tool tốt là lựa chọn phù hợp với hệ sinh thái dự án, tạo được quy ước đủ thống nhất và cung cấp mức tùy biến cần thiết mà nhóm vẫn có thể hiểu, kiểm thử và duy trì. Hãy xác minh bằng một project mẫu và workload thực tế, sau đó ghi lại lý do lựa chọn để quyết định tiếp tục có cơ sở khi dự án phát triển.
