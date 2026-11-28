# Maven, Gradle và cấu trúc vòng đời build

> **Phạm vi:** Java 27 — chương **Build và quản lý phụ thuộc**. Bài học so sánh cách Maven và Gradle tổ chức dự án, giải quyết phụ thuộc, biên dịch, kiểm thử, đóng gói và phát hành; giải thích **Maven lifecycles/phases/plugin goals** khác với **Gradle initialization/configuration/execution phases và task dependency graph** ra sao. Ví dụ dùng Java 27 chính thức, không cần preview hoặc phương pháp build đã lỗi thời. Các phiên bản công cụ/plugin cần được kiểm tra và cố định theo dự án; tại thời điểm biên soạn, tài liệu Gradle ghi nhận **từ Gradle 9.8.0 có hỗ trợ Java 27 để chạy Gradle và làm toolchain**.

## 1. Build trong dự án Java nghĩa là gì?

Viết mã nguồn `.java` mới chỉ là một phần của vòng đời phần mềm. Để một ứng dụng có thể kiểm chứng và phát hành, quá trình build thường phải:

1. Xác định cấu trúc project, JDK và cấu hình liên quan.
2. Tải hoặc chọn đúng **dependencies** (thư viện) và **build plugins**.
3. Sinh sources/resources khi dự án thực sự có bước code generation.
4. Biên dịch mã nguồn Java thành `.class`.
5. Biên dịch và chạy unit tests; kiểm tra các chất lượng khác.
6. Đóng gói JAR/WAR hoặc phân phối ứng dụng thích hợp.
7. Kiểm chứng artifact được đóng gói và, khi được cho phép, publish lên repository.
8. Lưu log, reports và metadata để tái hiện build trên CI.

Sơ đồ khái niệm:

~~~text
Mã nguồn + build declarations + JDK/toolchain
                      │
                      ▼
              Dependency resolution
                      │
                      ▼
       Compile → Test → Package → Verify
                      │
                      ▼
        Artifact: JAR / WAR / distribution
                      │
                      ▼
          Publish / Deploy (khi cần)
~~~

Thứ tự trên diễn đạt **mục tiêu**. Maven và Gradle **không** tổ chức các bước bằng cùng một cơ chế:

- Maven dùng các **lifecycle** với những **phase có thứ tự xác định** và các **plugin goals được bind** vào phases.
- Gradle dùng **task graph**: người dùng yêu cầu task, Gradle xác định các task phụ thuộc cần chạy, có thể bỏ qua task `UP-TO-DATE` hoặc lấy output từ cache; ba **phases của Gradle** mô tả **cách Gradle cấu hình/thực thi build**, không phải một chuỗi compile/test/package bắt buộc như Maven.

### 1.1. Build tool không phải Java compiler

| Thành phần | Nhiệm vụ chính |
| --- | --- |
| `javac` | Biên dịch mã nguồn Java ra class files |
| `java` | Khởi động chương trình trên JVM |
| `jar` | Tạo/kiểm tra JAR archive |
| Maven | Quản lý project model/POM, dependencies, plugins và lifecycle |
| Gradle | Thực thi task graph, dependency configurations và build logic |
| JDK toolchain | Chọn JDK thực sự dùng để compile/test/javadoc |
| Repository | Lưu artifacts/plugins cùng metadata; **không phải** runtime class loader |

Maven/Gradle có thể gọi `javac` và các công cụ khác thay bạn, nhưng không có nghĩa lúc chạy `java` sẽ tự tải thư viện từ Maven Central. Packaging và runtime classpath phải được cấu hình đúng.

## 2. Chọn Maven hay Gradle?

| Khía cạnh | Maven | Gradle |
| --- | --- | --- |
| Khai báo build | Chủ yếu `pom.xml` theo Maven project model | `build.gradle.kts` (Kotlin DSL) hoặc `build.gradle` (Groovy DSL) |
| Cơ chế cốt lõi | Lifecycles → phases → plugin goals | Tasks và dependency graph |
| Build conventions | Quy ước tiêu chuẩn và plugin bindings theo packaging | Plugins cung cấp conventions và task graph |
| Cấu hình nhiều module | Parent/aggregator POM, reactor | Multi-project build, `settings.gradle(.kts)`, project dependencies |
| Dependency scope | `compile`, `runtime`, `provided`, `test`... | `api`, `implementation`, `runtimeOnly`, `testImplementation`... |
| Tùy biến | Plugin goals, executions, profiles, extensions | Tasks, plugins, convention plugins, build logic |
| Tăng tốc | Incremental behavior tùy compiler/plugin; Maven extensions/caching tùy thiết lập | Incremental tasks, up-to-date checks, build cache, configuration cache |
| File output mặc định | `target/` | `build/` |
| Chạy nhất quán trên CI | Maven Wrapper `mvnw`, pin plugins/toolchain | Gradle Wrapper `gradlew`, pin distribution/toolchain |

**Không có một công cụ thắng mọi dự án.** Đội ngũ có sẵn Maven conventions và plugin ecosystem ổn định thường không cần đổi sang Gradle chỉ vì Gradle có task graph. Ngược lại, hệ thống cần custom build logic, multi-project plugin setup hoặc caching tinh chỉnh có thể tận dụng Gradle.

**Một tiêu chí quan trọng:** người mới có thể chạy và hiểu toàn bộ quy trình **trên CI** mà không phải biết máy của tác giả đang cài bản tool nào.

## 3. Cấu trúc nguồn Java tiêu chuẩn

Cả Maven và Gradle Java plugins đều hỗ trợ layout phổ biến:

~~~text
hello-build/
├── pom.xml                  # Maven, nếu chọn Maven
│   hoặc build.gradle.kts    # Gradle, nếu chọn Gradle
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/app/Main.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       ├── java/
│       │   └── com/example/app/...
│       └── resources/
└── ... công cụ/Wrapper files theo lựa chọn
~~~

Với cấu trúc trên, **không cần** phải tự viết lệnh tìm từng file `.java`. Compiler plugins/tasks được cấu hình để đọc source sets và resources theo quy ước.

### 3.1. Một chương trình mẫu dùng được cho cả hai cách build

File `src/main/java/com/example/app/Main.java`:

~~~java
package com.example.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(greet("Java 27"));
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name;
    }
}
~~~

Mọi ví dụ POM/Gradle trong bài này cùng dùng class trên. Source không cần JUnit hay dependency bên ngoài, nên có thể kiểm tra **compile/package/run** trước khi bổ sung test framework. Chạy trên đúng JDK 27 sẽ cho:

~~~text
Xin chào, Java 27
~~~

### 3.2. Vị trí output và source không giống nhau

| Nội dung | Maven mặc định | Gradle Java/Application plugin mặc định |
| --- | --- | --- |
| Main sources | `src/main/java/` | `src/main/java/` |
| Test sources | `src/test/java/` | `src/test/java/` |
| Resources | `src/main/resources/` | `src/main/resources/` |
| Compiled main classes | `target/classes/` | `build/classes/java/main/` |
| Test results/reports | `target/surefire-reports/` nếu dùng Surefire | `build/test-results/test/` và `build/reports/tests/test/` |
| JAR | `target/<artifactId>-<version>.jar` | `build/libs/<project-name>-<version>.jar` |

Paths là **quy ước mặc định** và có thể bị plugin tùy chỉnh. Đừng coi các đường dẫn này là bất biến nếu project đã cấu hình output khác.

## 4. Maven: mô hình POM và ba build lifecycles

Một Maven project thường có `pom.xml` (*Project Object Model*). Nó khai báo `groupId`, `artifactId`, `version`, `packaging`, dependencies, build plugins và các cấu hình khác.

Maven có **ba built-in lifecycles độc lập**:

| Lifecycle | Mục đích | Phase tiêu biểu |
| --- | --- | --- |
| **default** | Build, test, package, verify, install, deploy | `validate`, `compile`, `test`, `package`, `verify`, `install`, `deploy` |
| **clean** | Dọn output build trước đó | `pre-clean`, `clean`, `post-clean` |
| **site** | Sinh và phát hành website/tài liệu dự án | `pre-site`, `site`, `post-site`, `site-deploy` |

Không nên nói “Maven lifecycle là `clean → compile → test → package`”. `clean` thuộc **lifecycle riêng**; `mvn clean verify` là yêu cầu chạy clean lifecycle đến phase clean, rồi default lifecycle đến phase verify.

### 4.1. Các phases của default lifecycle

~~~text
validate
   │
initialize
   │
generate-sources / process-sources
   │
generate-resources / process-resources
   │
compile
   │
process-test-resources / test-compile
   │
test
   │
package
   │
pre-integration-test → integration-test → post-integration-test
   │
verify
   │
install
   │
deploy
~~~

Sơ đồ bỏ bớt một số phases giữa chặng để dễ đọc; **không phải** danh sách đầy đủ của mọi phase. Mỗi phase chỉ thực thi những plugin goals đã được bind vào nó theo packaging và cấu hình project.

| Phase | Ý nghĩa thực tế |
| --- | --- |
| `validate` | Kiểm tra cấu hình và các điều kiện ban đầu |
| `compile` | Biên dịch production classes |
| `test` | Chạy unit tests qua test plugin theo quy tắc của build |
| `package` | Tạo artifact, ví dụ JAR/WAR |
| `integration-test` | Bước dành cho tích hợp, khi có plugin binding phù hợp |
| `verify` | Kiểm chứng artifact và kết quả integration tests/checks đã được cấu hình |
| `install` | Cài artifact vào **local Maven repository** để project khác trên máy sử dụng |
| `deploy` | Đẩy artifact vào **remote repository** được cấu hình |

**Đừng** mặc định gọi `mvn integration-test` là cách hoàn chỉnh chạy integration tests: các bước setup/teardown và kiểm chứng thường được liên kết tới `pre-integration-test`/`post-integration-test`/`verify`; nên dùng `mvn verify` để đi qua lifecycle được cấu hình đầy đủ.

### 4.2. Chạy một phase sẽ chạy tất cả phases đứng trước nó

~~~bash
mvn compile
mvn test
mvn package
mvn verify
mvn install
mvn deploy
~~~

- `mvn test` đi qua các phases trước `test`, bao gồm `compile`.
- `mvn package` cũng chạy `test` nếu có test goals được bind và không bị skip.
- `mvn verify` bao gồm đóng gói và mọi bước kiểm chứng đã cấu hình đến phase verify.
- `mvn install` đưa artifact vào local repository **sau** các phases trước.
- `mvn deploy` là hành động **publish artifact** vào remote repository, **không** đồng nghĩa triển khai ứng dụng lên server production.

Đối với kiểm tra chất lượng CI thông thường, `mvn verify` là điểm bắt đầu tốt; publish cần pipeline và credentials được tách biệt.

### 4.3. Phase khác plugin goal

Một **phase** như `compile` là vị trí trong lifecycle; một **plugin goal** như `compiler:compile` là hành động thực sự do plugin thực hiện.

Ví dụ với packaging `jar`, các binding thông dụng gồm:

| Phase | Plugin goal thường được bind |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |

Khi chạy `mvn compiler:compile`, bạn gọi **goal trực tiếp**, không yêu cầu Maven chạy toàn bộ default lifecycle đến `compile`. Đối với mục tiêu build thông thường, **chọn phase** là dễ dự đoán hơn; gọi goal trực tiếp hữu ích trong chẩn đoán hoặc workflow đặc biệt.

### 4.4. Packaging ảnh hưởng lifecycle bindings

`<packaging>jar</packaging>` dùng những goal khác với `war` hoặc `pom`. Packaging `pom` thường dùng cho parent/aggregator model, không tự đóng gói class thành JAR như `jar`.

Điều đó giải thích vì sao hai POM cùng chạy `mvn package` có thể tạo ra những artifact khác nhau. **Phase không phải một script cứng**; nó là điểm nối tới các plugin goals.

## 5. Maven: POM tối thiểu cho Java 27

File `pom.xml` của project mẫu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-build</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>27</maven.compiler.release>
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
</project>
~~~

Điểm quan trọng:

- `groupId:artifactId:version` là tọa độ artifact của project.
- `packaging=jar` chọn JAR packaging bindings.
- `maven.compiler.release=27` yêu cầu compiler áp quy tắc source/API/class-file target của Java 27 thông qua `--release 27`.
- `maven-compiler-plugin` được khai báo **phiên bản cụ thể** (3.16.0 theo tài liệu chính thức được đối chiếu), thay vì phụ thuộc vào version plugin được Maven ngầm chọn.
- Build cần **JDK 27** (hoặc toolchain compiler phù hợp); khai `release=27` không tự cài compiler JDK 27.
- POM này **chưa có test framework**, nên chưa thể kỳ vọng Maven tự chạy test JUnit. Đối với một build production thực, cần quản lý thêm phiên bản test/packaging/quality plugins theo chính sách dự án.

Ví dụ trên dùng POM model `4.0.0` theo cấu trúc Maven phổ biến; không yêu cầu dự án phải chuyển ngay sang một mô hình Maven 4-specific chỉ để học lifecycle.

### 5.1. Kiểm tra công cụ, build và chạy

~~~bash
java -version
mvn -version
mvn clean verify
java --class-path target/hello-build-1.0.0.jar com.example.app.Main
~~~

Kết quả từ `main()`:

~~~text
Xin chào, Java 27
~~~

Đây là một **JAR thư viện/ứng dụng thường**, nên chạy bằng cách chỉ rõ main class qua classpath. Không dùng `java -jar target/hello-build-1.0.0.jar` trừ khi có manifest `Main-Class` và cách đóng gói dependencies phù hợp; mặc định một JAR chưa chắc executable.

Trên Windows PowerShell, các lệnh ở trên hoạt động tương tự nếu Maven đã có trong PATH. Nếu repository cung cấp Maven Wrapper, ưu tiên lệnh `./mvnw` (Unix) hoặc `.\mvnw.cmd` (Windows) để sử dụng bản Maven được dự án quản lý.

### 5.2. Những thư mục Maven tạo ra

~~~text
target/
├── classes/
│   └── com/example/app/Main.class
├── maven-status/           # metadata của một số plugins
├── ...                     # kết quả build/test tùy plugin
└── hello-build-1.0.0.jar
~~~

Thư mục `target/` là build output, thường không được commit vào source control. Nếu có pipeline cần lưu artifact, hãy upload/đăng ký artifact riêng; không xem `target/` trên một máy developer là remote release repository.

### 5.3. Chạy clean không phải điều kiện bắt buộc mọi lần

`mvn clean verify` phù hợp khi muốn bảo đảm output cũ được loại bỏ. Nhưng chạy `clean` mọi lần có thể làm mất lợi thế incremental build/cache của một số tools và tăng thời gian build. Chọn sạch hay incremental theo độ tin cậy và mục tiêu CI; không mặc định clean là cách chữa mọi lỗi dependency.

## 6. Maven dependency declarations và scopes

Dependency trực tiếp thường khai báo dưới `<dependencies>`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.17</version>
    </dependency>
</dependencies>
~~~

Đây là **ví dụ tọa độ thư viện đã phát hành**, không phải lời khuyên dùng đúng phiên bản đó cho mọi dự án Java 27. Khi làm production, hãy xác minh release đang hỗ trợ, cảnh báo bảo mật, license và compatibility, rồi pin phiên bản cụ thể.

Các scopes quan trọng:

| Maven scope | Có trong compile classpath? | Có trong runtime classpath? | Mục đích |
| --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Thư viện chính dùng ở compile và runtime |
| `provided` | Có | Không | Runtime/container cung cấp thư viện theo hợp đồng |
| `runtime` | Không | Có | Driver/implementation chỉ cần khi chạy |
| `test` | Chỉ test | Chỉ test | Test framework/test helper |
| `import` | Chỉ dùng trong `dependencyManagement` với dependency type `pom` | Không trực tiếp | Nhập dependency-management entries từ BOM |

Maven còn có `system` scope vì lý do tương thích, nhưng **không nên chọn nó cho dependency mới** vì phụ thuộc vào đường dẫn file local cố định, khó tái tạo và quản lý. Chọn repository dependency hoặc module nội bộ được publish hợp lệ.

**Scope không phải JPMS `requires`.** Maven giải quyết artifacts/classpaths ở cấp build; khi dự án có `module-info.java`, Java compiler/runtime vẫn kiểm tra module readability và exports theo JPMS.

### 6.1. Dependency transitives và xung đột phiên bản

Nếu A phụ thuộc vào B, B phụ thuộc vào C, Maven có thể đưa C vào graph **transitively**. Nhưng nếu source của A **trực tiếp import class từ C**, hãy cân nhắc khai báo C là **direct dependency** để contract rõ ràng, không dựa vào một chi tiết triển khai của B.

Maven dùng các quy tắc lựa chọn phiên bản dependency (trong đó có **nearest definition**, cùng độ sâu xét thứ tự khai báo) khi graph có nhiều phiên bản xung đột. Đừng suy ra cùng tọa độ `groupId:artifactId` có thể đồng thời có nhiều phiên bản hiệu dụng chỉ vì hai thư viện phụ thuộc khác nhau.

Kiểm tra graph bằng Maven Dependency Plugin:

~~~bash
mvn dependency:tree
~~~

Lệnh trên cần dependency plugin được resolve; bản thân output có thể thay đổi theo phiên bản plugin và project. Với dự án quan trọng, pin dependency-plugin version và lưu graph trong build logs hoặc reports để so sánh khi cập nhật.

### 6.2. dependencyManagement không tự thêm dependency

Một đoạn POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Nó **quản lý phiên bản/chính sách dependency** khi dependency xuất hiện, nhưng **không tự đưa SLF4J vào classpath**. Muốn dùng thư viện, project vẫn cần khai báo dependency trong `<dependencies>` (hoặc được đưa vào qua graph theo đúng cơ chế).

**Khác biệt với pluginManagement:** `<pluginManagement>` quản lý plugin versions/configuration, không có nghĩa mọi plugin liệt kê ở đó sẽ được chạy. Goal phải có binding hợp lệ qua packaging hoặc khai báo execution/usage phù hợp.

### 6.3. BOM và import scope

BOM (Bill of Materials) trong Maven thường là POM có `dependencyManagement`. Project có thể import nó:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.2.3</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **tọa độ minh họa giả định** để giải thích cú pháp, không phải một BOM có thể tải từ Maven Central. Cần thay bằng BOM thật do tổ chức hoặc framework đã xác minh phát hành. BOM giúp nhất quán các versions trong một nhóm thư viện, nhưng không tự giải quyết việc các dependency thực tế có tương thích về mặt API, JPMS và runtime hay không.

## 7. Gradle: lifecycle gồm initialization, configuration và execution

Gradle không dùng các Maven phases `compile`, `test`, `package` như một timeline cứng. **Một lần chạy Gradle** gồm ba giai đoạn:

~~~text
     ./gradlew build
            │
            ▼
   1. INITIALIZATION
   - đọc settings.gradle(.kts)
   - xác định root/subprojects/included builds
            │
            ▼
   2. CONFIGURATION
   - áp dụng plugins
   - đánh giá build scripts khi cần
   - đăng ký/configure tasks
   - xây task dependency graph
            │
            ▼
   3. EXECUTION
   - chạy tasks cần thiết theo graph
   - xét UP-TO-DATE / FROM-CACHE / SKIPPED
   - có thể song song khi không phụ thuộc nhau
            │
            ▼
     Build result + outputs
~~~

Các bước chi tiết có thể thay đổi với **configuration cache** và **isolated projects**; mô hình ba giai đoạn vẫn là nền tảng để hiểu build.

### 7.1. Initialization: chọn những projects tham gia

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "hello-build"
~~~

Với multi-project build:

~~~kotlin
rootProject.name = "platform"
include(":core", ":api", ":app")
~~~

Gradle xác định những project nào tồn tại trong build. Nó **không** coi mọi thư mục bất kỳ dưới root là một subproject chỉ vì thư mục chứa file Java.

### 7.2. Configuration: plugins và đăng ký tasks

File `build.gradle.kts` diễn đạt tasks, dependencies và toolchains. Các lệnh cấp configuration được đánh giá trước khi task actions được chạy, trừ trường hợp Gradle tối ưu/khôi phục từ configuration cache theo contract.

Ví dụ:

~~~kotlin
tasks.register("hello") {
    doLast {
        println("Xin chào từ Gradle task")
    }
}
~~~

`tasks.register` **đăng ký task một cách lazy**, không có nghĩa `doLast` đã chạy. Khi gọi:

~~~bash
./gradlew hello
~~~

Gradle chọn task `hello` và thực thi action `doLast` ở execution phase.

### 7.3. Execution: chạy DAG thay vì theo thứ tự văn bản

Ví dụ:

~~~kotlin
tasks.register("compileSpecial") {
    doLast { println("Compile special files") }
}
tasks.register("packageSpecial") {
    dependsOn("compileSpecial")
    doLast { println("Package special files") }
}
~~~

Lệnh:

~~~bash
./gradlew packageSpecial
~~~

sẽ chọn `packageSpecial` cùng dependency `compileSpecial`. Không phải vì `compileSpecial` được đặt phía trên trong file, mà vì **`dependsOn` tạo dependency edge**.

~~~text
compileSpecial ─────▶ packageSpecial
       │                     │
       └── phải xong trước ──┘
~~~

**Đừng** dùng thứ tự khai báo trong `build.gradle.kts` để giả định task A phải chạy trước B. Khai báo quan hệ task phù hợp bằng task inputs/outputs, `dependsOn` và các dependency contracts khác.

### 7.4. Configuration cache khác build cache

- **Configuration cache**: tránh cấu hình lại toàn bộ build khi inputs/configuration thích hợp không đổi; có ràng buộc về build logic có thể lưu lại được.
- **Build cache**: tái sử dụng outputs của tasks có inputs và cache keys phù hợp.
- **Up-to-date checks**: bỏ qua task khi Gradle xác định outputs hiện tại đã phản ánh inputs.
- **Daemon**: tiến trình Gradle lâu sống giúp giảm chi phí khởi động; không phải cache của artifact version.

Không đánh đồng `UP-TO-DATE` với `FROM-CACHE`; thứ nhất có thể dùng output local hiện có, còn thứ hai lấy output từ cache. Cả hai cần task khai báo inputs/outputs đúng để bảo đảm tính chính xác.

## 8. Gradle: ví dụ Java 27 với Kotlin DSL

Với cùng file `src/main/java/com/example/app/Main.java` từ phần 3, ta tạo một Gradle **application** project.

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "hello-build"
~~~

File `build.gradle.kts`:

~~~kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 27
}

application {
    mainClass = "com.example.app.Main"
}
~~~

Đây là ví dụ **Kotlin DSL** (`.gradle.kts`), không phải Groovy DSL. Các block dùng đúng convention của Gradle `application` plugin:

- `application` áp dụng Java plugin và bổ sung tasks chạy/đóng gói ứng dụng.
- `mavenCentral()` chỉ nguồn repository cho external dependencies **khi được khai báo**; không bắt buộc ứng dụng hiện tại cần thư viện ngoài.
- `java.toolchain.languageVersion=27` yêu cầu dùng JDK 27 cho công việc Java hỗ trợ toolchains.
- `options.release=27` cấu hình compiler `--release 27`, giúp kiểm tra Java language/API/classfile target tương ứng.
- `mainClass` chỉ FQN class có entry point.
- `JavaCompile` là task type mà Kotlin DSL nhận qua Gradle API; chạy bằng bản Gradle hỗ trợ Java 27.
- Khả năng **tự tải JDK toolchain** khi máy chưa có JDK 27 phụ thuộc cấu hình toolchain download repositories/auto-provisioning của môi trường. **Khai toolchain không bảo đảm mọi máy offline tự có JDK 27.**

### 8.1. Điều kiện phiên bản Gradle để chạy Java 27

Theo **Gradle Compatibility Matrix** được kiểm tra tại thời điểm biên soạn, hỗ trợ Java **27** được công bố từ:

| Nhu cầu | Gradle release được tài liệu xác nhận |
| --- | --- |
| Dùng Java 27 làm **toolchain** để compile/test | **9.8.0 trở lên** |
| Dùng Java 27 làm JVM **chạy Gradle/daemon** | **9.8.0 trở lên** |

Có thể sử dụng Gradle **9.9.2** làm ví dụ của một bản tương thích được tài liệu chính thức công bố. **Đừng** coi “cài JDK 27” là đủ để bản Gradle cũ bất kỳ cũng chạy trên JDK 27; cần đọc compatibility matrix của version Gradle thực tế.

Để kiểm tra runtime của Gradle:

~~~bash
./gradlew --version
~~~

Output hiển thị Gradle version, Launcher JVM, Daemon JVM và các thông tin môi trường tùy release. Việc project compile bằng toolchain 27 **không bắt buộc** Gradle daemon luôn chạy cùng JDK nếu version Gradle hỗ trợ cấu hình như vậy. Tuy nhiên, nếu muốn Gradle daemon **chạy** trên JDK 27, phải dùng bản Gradle tương thích.

### 8.2. Dùng Gradle Wrapper

Với project đã có Wrapper:

~~~bash
./gradlew clean build
./gradlew run
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean build
.\gradlew.bat run
~~~

Wrapper xác định version Gradle qua `gradle/wrapper/gradle-wrapper.properties`. Với **project mới chưa có Wrapper**, tạo từ một bản Gradle đã cài và phù hợp:

~~~bash
gradle :wrapper --gradle-version 9.9.2
~~~

Lệnh sinh hoặc cập nhật các file như:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Hãy commit **các file Wrapper được công cụ tạo hợp lệ** để nhóm/CI dùng cùng Gradle version, và cân nhắc cấu hình kiểm tra checksum distribution khi chính sách supply-chain yêu cầu. **Không** tải một `gradle-wrapper.jar` không rõ nguồn rồi commit hoặc tự chép một file JAR ngẫu nhiên có tên giống Wrapper.

### 8.3. Chạy chương trình và xem output

~~~bash
./gradlew run
~~~

Task `run` đến từ Application plugin; nó chạy main class với runtime classpath được Gradle cấu hình. Dòng từ ứng dụng:

~~~text
Xin chào, Java 27
~~~

Để tạo JAR và kiểm chứng theo graph:

~~~bash
./gradlew build
~~~

Output JAR thông thường:

~~~text
build/libs/hello-build-1.0.0.jar
~~~

Đây thường là **thin JAR** chứa classes/resources của project. Nó **không tự nhúng tất cả external runtime dependencies**. Với Application plugin, distribution tasks như `distZip`/`installDist` có thể đóng gói scripts và dependencies theo plugin conventions; đó là lựa chọn phù hợp hơn so với tự giả định JAR là một “fat JAR”.

Chạy bằng `java -cp build/libs/hello-build-1.0.0.jar com.example.app.Main` có thể hoạt động với mẫu này vì không có external dependencies. Khi thêm dependencies, phải cung cấp runtime classpath hoặc distribution đúng cách.

### 8.4. Sơ đồ tasks của Java/Application plugin

~~~text
compileJava ──┐
processResources ──▶ classes ──▶ jar ──┐
                                        │
compileTestJava ──▶ testClasses ──▶ test ──▶ check
                                        │    │
                                        └────┼──▶ build
                                             │
                          jar ──▶ assemble ──┘
~~~

Đây là **sơ đồ ý niệm, không liệt kê tất cả edges/tasks**; các relationships cụ thể có thể gồm test runtime dependencies và tasks do plugins khác thêm vào.

| Task | Vai trò |
| --- | --- |
| `compileJava` | Biên dịch source `main` |
| `processResources` | Xử lý/copied resources |
| `classes` | Aggregate cho compiled classes/resources |
| `compileTestJava`, `testClasses` | Chuẩn bị test classes |
| `test` | Chạy tests đã được cấu hình qua test framework |
| `jar` | Đóng gói JAR của project |
| `assemble` | Gom các output artifact tasks |
| `check` | Gom verification tasks, gồm test khi cấu hình |
| `build` | Lifecycle task phụ thuộc `assemble` và `check` |
| `clean` | Dọn build output theo thiết lập Gradle |
| `run` | Chạy entry point khi có Application plugin |

Không suy ra `./gradlew assemble` tự chạy unit tests; nó chủ yếu phục vụ artifact assembly. `./gradlew build` mới có cả phần verification thông qua `check` theo Java plugin conventions.

## 9. Maven lifecycle và Gradle task graph: đối chiếu lệnh

| Mục tiêu | Maven | Gradle (Java/Application) |
| --- | --- | --- |
| Kiểm tra tool version | `mvn -version` | `./gradlew --version` |
| Chỉ compile production | `mvn compile` | `./gradlew classes` hoặc `compileJava` |
| Chạy unit tests đã cấu hình | `mvn test` | `./gradlew test` |
| Tạo artifact | `mvn package` | `./gradlew assemble` hoặc `jar` |
| Full verification build | `mvn verify` | `./gradlew build` |
| Fresh verification build | `mvn clean verify` | `./gradlew clean build` |
| Publish vào local Maven repo | `mvn install` | Cần `maven-publish` và một publish-to-Maven-local task phù hợp |
| Publish vào remote repository | `mvn deploy` | Cần publishing plugin, credentials và repository task/config |
| Inspect dependency graph | `mvn dependency:tree` | `./gradlew dependencies` |
| Inspect lý do một version được chọn | Dependency tree/effective POM | `./gradlew dependencyInsight --dependency <name> --configuration runtimeClasspath` |
| Chạy application main | `java -cp target/...jar ...` (hoặc plugin phù hợp) | `./gradlew run` nếu có `application` plugin |

**Đây là ánh xạ theo mục tiêu**, không phải khẳng định mỗi lệnh có semantics y hệt nhau:

- `mvn package` đi qua các Maven phases tới package, thường bao gồm unit tests.
- `./gradlew assemble` không phải tương đương tuyệt đối với Maven `package` về việc chạy tests.
- `mvn verify` chỉ chạy các verification goals đã được bind; `./gradlew build` chỉ chạy các verification tasks nằm trong graph.
- `mvn deploy` là artifact repository publish; nếu deploy ứng dụng lên cloud/Kubernetes cần pipeline/plugin khác.

## 10. Gradle dependencies, configurations và Java Library API

Trong Gradle, dependencies được khai báo trong **configurations**:

~~~kotlin
dependencies {
    implementation("org.slf4j:slf4j-api:2.0.17")
    // Chỉ thêm dòng sau nếu project thực sự dùng một backend SLF4J:
    // runtimeOnly("org.slf4j:slf4j-simple:<version-da-xac-minh>")
}
~~~

Tọa độ và `version` minh họa phải được cập nhật theo dependency policy của project; `<version-da-xac-minh>` nằm trong comment, **không phải version syntax có thể resolve**.

Các configurations phổ biến:

| Gradle configuration | Ý nghĩa |
| --- | --- |
| `implementation` | Thư viện dùng compile và runtime của project; không expose như API compile cho consumers qua Java Library plugin |
| `api` | Dependency hiện diện trong API contract của **`java-library` plugin** để consumers có thể compile |
| `compileOnly` | Chỉ cần lúc compile, không tự có ở runtime |
| `runtimeOnly` | Chỉ cần lúc chạy |
| `testImplementation` | Cần cho compile/test execution |
| `testRuntimeOnly` | Chỉ cần cho test runtime |
| `annotationProcessor` | Tools chạy trong annotation processing, không tự thành ứng dụng runtime dependency |

`api` **không sẵn có** ở mọi Java project: để khai báo `api(...)` dùng `java-library` plugin (hoặc plugin có cung cấp configuration tương ứng).

Ví dụ library public API:

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    api("org.slf4j:slf4j-api:2.0.17")
}
~~~

Ở một thư viện thực, chỉ nên dùng `api` nếu types từ dependency xuất hiện trong **public API** mà consumers phải compile. Nếu dependency chỉ dùng bên trong implementation, giữ ở `implementation` để giảm compile classpath coupling.

### 10.1. Gradle dependency resolution và variant-aware selection

Gradle dùng metadata/configurations/attributes để chọn **variant** thích hợp cho một dependency (ví dụ API vs runtime elements). Trong multi-project build với `java-library`:

- Consumer compile classpath có thể dùng `apiElements` của thư viện.
- Runtime classpath cần `runtimeElements` và implementation dependencies phù hợp.
- Một dependency chỉ dùng implementation không nhất thiết phải lộ trên compile classpath của consumer.

Điểm này khác cách nghĩ “mọi JAR transitive đều xuất hiện giống nhau ở compile và runtime”. Khi dependency thiếu chỉ lúc chạy, hãy xem **configuration thực sự được resolve**, không chỉ dependency declaration.

### 10.2. Debug dependency graphs

Xem toàn bộ dependencies:

~~~bash
./gradlew dependencies
~~~

Chọn một configuration cụ thể:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Giải thích một module được chọn do đâu:

~~~bash
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
~~~

Khi có xung đột phiên bản, output `dependencyInsight` hữu ích để xem requested versions, constraints và selection reason. Gradle có cơ chế **conflict resolution/constraints/platforms** khác với Maven nearest-definition; không được áp quy tắc Maven vào Gradle một cách máy móc.

### 10.3. Gradle platforms và version catalogs

Với dự án nhiều module, Gradle hỗ trợ:

- **Platform/BOM** để quản lý version constraints của nhóm dependencies.
- **Version catalogs** (thường `gradle/libs.versions.toml`) để khai báo alias và phiên bản trung tâm.
- **Dependency constraints** để điều khiển allowed/preferred/strict versions.
- **Dependency locking** để ghi lại resolved dependency versions cho build có thể tái hiện.

Một version catalog có thể chứa:

~~~toml
[versions]
slf4j = "2.0.17"

[libraries]
slf4j-api = { module = "org.slf4j:slf4j-api", version.ref = "slf4j" }
~~~

Dùng từ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation(libs.slf4j.api)
}
~~~

**Version catalog không phải lock file**: alias và requested versions không bảo đảm mọi transitive version được pin. Khi cần reproducibility mạnh hơn, bổ sung locking/verification phù hợp.

## 11. Unit test, integration test và quy ước build

Build thành công chỉ sau khi compile **không** chứng minh ứng dụng đúng nghiệp vụ. Nhưng ngược lại, viết test source vào `src/test/java` **chưa đủ** nếu project chưa khai báo test framework và task/plugin phù hợp.

### 11.1. Maven: Surefire và Failsafe có vai trò khác nhau

Một cấu hình Maven thông dụng:

- **Surefire**: chạy unit tests ở phase `test`.
- **Failsafe**: chạy integration tests thông qua goals được bind vào `integration-test` và `verify`.
- Các conventions về class name/test framework cần khớp chính xác plugin version và test engine.

Ví dụ block **minh họa** ranh giới plugin (cần pin các phiên bản đang được xác minh ở project):

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.5</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.5.5</version>
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

Đoạn trên là **một block để ghép vào POM hợp lệ**, không phải file `pom.xml` hoàn chỉnh. Trước khi áp dụng trong production, phải kiểm tra phiên bản plugin tồn tại/được hỗ trợ, test framework provider và pattern phát hiện tests cho bản plugin tương ứng. Việc thêm plugins **không tự tạo integration tests** nếu chưa có test source/engine.

### 11.2. Gradle: test task là một task trong graph

Khi dùng Java plugin, Gradle cung cấp `test` task. Với JUnit Platform:

~~~kotlin
tasks.test {
    useJUnitPlatform()
}
~~~

Chỉ thêm `useJUnitPlatform()` **không tự thêm JUnit libraries** vào classpath. Cần khai báo JUnit API/engine (hoặc bộ thư viện phù hợp) với phiên bản được xác minh; các phiên bản JUnit có thể thay đổi qua thời gian.

Có thể tạo task integration test riêng trong Gradle bằng source set/JVM test suite plugin, rồi gắn task này vào `check` nếu muốn nó thuộc full build. **Không** giả định rằng `./gradlew build` tự tìm mọi `*IT.java` trong repository khi chưa cấu hình.

### 11.3. Thử một test class bằng cách nào?

Giả sử có JUnit Jupiter và test engine phù hợp, một unit test đơn giản cho `Main.greet()` có thể là:

~~~java
package com.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void greetsNonBlankName() {
        assertEquals("Xin chào, An", Main.greet("An"));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> Main.greet(" "));
    }
}
~~~

Đặt file `src/test/java/com/example/app/MainTest.java`. **Lưu ý dependency**: ví dụ không chạy được chỉ với hai build files tối giản ở phần 5/8 vì chưa khai JUnit; phải thêm dependency và runner tương thích trước. Điều này thể hiện rõ sự khác nhau giữa **source layout conventions** và **dependency/plugin configuration**.

## 12. Multi-module Maven và multi-project Gradle

### 12.1. Maven reactor và parent/aggregator POM

Ví dụ repository:

~~~text
platform/
├── pom.xml                 # parent/aggregator
├── core/
│   └── pom.xml
├── api/
│   └── pom.xml
└── app/
    └── pom.xml
~~~

Parent/aggregator POM có thể khai:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>platform-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>core</module>
        <module>api</module>
        <module>app</module>
    </modules>
</project>
~~~

Đoạn là một parent/aggregator POM minh họa; `core/pom.xml`, `api/pom.xml` và `app/pom.xml` cần khai báo tọa độ/parent/dependencies thích hợp để tạo build đầy đủ.

Các ý quan trọng:

- **Aggregation:** `<modules>` giúp Maven reactor xác định các project thành viên trong một build.
- **Inheritance:** `<parent>` trong child POM giúp kế thừa một số cấu hình/version policies.
- Một POM có thể làm aggregator mà không nhất thiết là parent của mọi module; đây là **hai quan hệ khác nhau**.
- **Inter-module dependencies** được khai báo bằng tọa độ dependency, không tự sinh chỉ vì có `<module>api</module>`.

Ví dụ từ root:

~~~bash
mvn -pl app -am verify
~~~

`-pl app` chọn project `app`; `-am` cũng build những project trong reactor cần thiết cho module đã chọn. Cần dùng đúng artifact dependencies/child POM để Maven có graph hợp lệ.

### 12.2. Gradle multi-project và project dependencies

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "platform"

include(":core", ":api", ":app")
~~~

Ví dụ `app/build.gradle.kts`:

~~~kotlin
plugins {
    application
}

dependencies {
    implementation(project(":api"))
    implementation(project(":core"))
}
~~~

Khi chạy:

~~~bash
./gradlew :app:build
~~~

Gradle chọn task `build` trong project `:app` và các task dependencies cần thiết ở những subprojects liên quan. Task path `:app:build` khác với Maven phase `install`: nó không tự publish tất cả artifacts vào local repository.

**Đừng** đánh đồng `include(":api")` trong settings với `implementation(project(":api"))` trong project: một bên tạo cấu trúc project, một bên khai phụ thuộc code/artifact giữa projects.

## 13. Build reproducibility và quản lý phiên bản công cụ

Một build “chạy được trên máy tôi” không tự được tái hiện trên CI. Cần kiểm soát các đầu vào có thể thay đổi:

| Đầu vào | Vì sao quan trọng | Cách kiểm soát |
| --- | --- | --- |
| JDK | Syntax/API/class file/annotation processors | Java toolchain, Maven toolchains, `--release` |
| Maven/Gradle distribution | Build engine, plugin resolution, DSL compatibility | Wrapper và version policy |
| Build plugins | Mã chạy trong quá trình build | Pin plugin versions, xem changelog |
| Direct dependencies | API và ABI của thư viện | Khai phiên bản rõ, kiểm tra nâng cấp |
| Transitive dependencies | Có thể thay đổi theo metadata/constraints | BOM/platform, dependency graph, Gradle locking |
| Repository endpoints | Artifact provenance/availability | Repository allowlist, mirror/proxy được kiểm soát |
| OS/locale/timezone | Tests/resource processing có thể lệ thuộc môi trường | Build/test configuration tường minh |
| Environment/secrets | Build/publish cần credentials nhưng không nên lộ | Secret store, CI credentials, không commit secret |
| Generated artifacts | Code generation có thể phụ thuộc version tool | Pin generator, kiểm thử output và schema |

### 13.1. Maven Wrapper và Gradle Wrapper

- Maven Wrapper: scripts `mvnw` / `mvnw.cmd` cùng configuration của wrapper trong repository. Được dùng để chọn Maven distribution theo dự án.
- Gradle Wrapper: `gradlew` / `gradlew.bat`, `gradle-wrapper.jar` và `gradle-wrapper.properties`.

**Không** cho rằng Wrapper tự cài JDK 27. Wrapper cố định **build tool version**; compiler JDK vẫn phải được cài hoặc provision đúng theo toolchain policy.

### 13.2. Pin versions không có nghĩa artifact luôn bất biến

Với Maven, phiên bản không phải `-SNAPSHOT` thường hướng đến artifact ổn định, nhưng repository cấu hình sai hoặc artifact bị thay thế có thể làm cùng tọa độ cho dữ liệu khác. Với Gradle, dynamic versions (`1.+`, ranges) hoặc changing modules làm dependency graph biến động khi không có kiểm soát.

Để tăng khả năng tái hiện:

- Hạn chế dynamic versions trong release builds.
- Ghi lại dependency versions được chọn.
- Dùng Gradle dependency locking khi phù hợp.
- Kiểm tra checksums và chữ ký artifact, nhất là build plugins và transitive libraries.
- Dùng repository được kiểm soát và chính sách nâng cấp an toàn.
- Tạo artifact một lần trong pipeline, **promote chính artifact đã kiểm thử** thay vì build lại bằng môi trường khác rồi giả định chúng giống nhau.

### 13.3. Gradle dependency locking

Ví dụ một cấu hình có thể thêm vào Gradle build:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Để tạo/update lock state, dùng các tasks khiến configurations cần lock được resolve cùng tùy chọn:

~~~bash
./gradlew dependencies --write-locks
~~~

Lock file thường có tên `gradle.lockfile`, nên được commit khi chính sách build yêu cầu khóa phiên bản. **Chú ý:** chỉ bật locking mà chưa có lock state không tự khóa được mọi transitive artifact; các cấu hình và điều kiện resolution cần được xem xét. Locking cũng không chứng minh artifact được publish từ nguồn đáng tin.

### 13.4. Gradle dependency verification

Gradle có cơ chế xác minh integrity/provenance bằng checksums và signatures qua `gradle/verification-metadata.xml`. Ví dụ tạo metadata ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Sau đó **review metadata** và kiểm tra nguồn checksum/trusted keys. Lệnh bootstrapping có thể ghi lại **artifact đã bị thay thế từ trước**, nên không coi việc tạo file thành công là bảo đảm an ninh.

### 13.5. Java toolchain và --release là hai kiểm soát khác nhau

| Thiết lập | Chọn JDK thực tế? | Giới hạn Java SE API theo target? |
| --- | --- | --- |
| Maven `maven.compiler.release=27` | Không tự chọn/cài JDK | Có với compiler hỗ trợ `--release 27` |
| Maven Toolchains Plugin/Toolchain config | Chọn JDK toolchain cho plugins tương thích | Không thay `--release` nếu muốn strict cross-compilation |
| Gradle `java.toolchain.languageVersion=27` | Có cho tasks hỗ trợ toolchain | Chỉ chọn compiler; muốn target API cũ hơn thì cấu hình `options.release` |
| Gradle `JavaCompile.options.release=27` | Không tự provision JDK | Có |
| `JAVA_HOME` | Ảnh hưởng runtime mặc định của tools | Không tự chặn dùng API mới |
| IDE Project SDK | Phục vụ IDE/build integration | Không bảo đảm CI giống IDE |

Khi phát hành một thư viện cho Java 21 nhưng xây từ JDK 27, dùng `--release 21` để giới hạn syntax/classfile/public Java API theo Java 21; **không** chỉ đặt target bytecode version 21 rồi mặc định mọi Java 27 API vẫn chạy trên Java 21.

## 14. CI: build, test, package, publish là các ranh giới khác nhau

Một pipeline phát hành an toàn nên tách rõ:

~~~text
Source checkout
   │
   ▼
Resolve JDK + wrapper + dependencies
   │
   ▼
Compile + unit tests
   │
   ▼
Package
   │
   ▼
Integration tests + static/security checks
   │
   ▼
Verify checksums / produce reports
   │
   ▼
Store immutable artifact
   │
   ▼
Publish to repository (authorized release stage)
   │
   ▼
Deploy application (separate stage, if applicable)
~~~

Maven CI minh họa:

~~~bash
./mvnw -B --no-transfer-progress verify
~~~

Gradle CI minh họa:

~~~bash
./gradlew --no-daemon build
~~~

Các lệnh cần Wrapper file hiện hữu, JDK/toolchains/dependencies có sẵn và build đã cấu hình tests/checks. `--no-daemon` là một lựa chọn cho môi trường CI cụ thể, **không bắt buộc Gradle luôn nhanh hơn hoặc an toàn hơn**; Gradle có chính sách daemon cho CI tùy version và tài nguyên.

**Không publish trong job kiểm thử thông thường** nếu chỉ cần xác nhận build. `mvn deploy` hoặc `publish` của Gradle là bước side effect cần quyền repository, version/release policy và credentials. Lưu artifact/report riêng khỏi output tạm.

## 15. Chẩn đoán khi build thất bại

Không phải mọi lỗi build đều là lỗi Java source. Phân loại theo **giai đoạn đầu tiên thất bại** sẽ tiết kiệm nhiều thời gian hơn việc xóa cache hoặc đổi plugin version một cách ngẫu nhiên.

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra ưu tiên |
| --- | --- | --- |
| `invalid target release: 27` | Compiler JDK đang dùng thấp hơn 27 | `java -version`, `mvn -version`, Gradle toolchain/JDK settings |
| Gradle không chạy trên Java 27 | Gradle distribution quá cũ | Compatibility Matrix, `./gradlew --version`; dùng 9.8.0+ |
| `No matching toolchains found` | Chưa có JDK 27 và không cấu hình download repository | Installed JDKs, Gradle toolchain provisioning |
| Maven plugin không resolve được | Plugin repository/network/credentials/version sai | POM plugin versions, `mvn -e`, `mvn -X` |
| `Could not resolve dependencies` | Dependency coordinates hoặc repository metadata/credentials lỗi | Repository config, `dependency:tree` / Gradle `dependencies` |
| `NoClassDefFoundError` lúc chạy | Runtime classpath thiếu library hoặc xung đột ABI | `runtimeClasspath`, JAR contents, dependency graph |
| `NoSuchMethodError` sau nâng thư viện | Runtime JAR không khớp compile ABI | `javap -s` trên artifacts, dependencies resolved |
| Unit test không được chạy | Chưa khai test engine/provider, test task không có inputs/đúng naming | Surefire/Failsafe/JUnit config hoặc Gradle `useJUnitPlatform()` |
| Integration tests không được chạy | Không có Failsafe executions hoặc Gradle test suite/task wiring | `verify` hoặc `check` graph thực tế |
| Gradle task bị `UP-TO-DATE` bất ngờ | Input/output khai báo không đúng hoặc task thực sự không đổi | `--info`, task input/output và build logic |
| Gradle configuration cache báo lỗi | Build logic đọc state không tương thích cache | Configuration cache report, refactor task/provider usage |
| Tests pass ở IDE nhưng fail trên CI | JDK/locale/timezone/test dependencies/OS khác | Wrapper, toolchain, test runtime classpath và env |
| `module not found` khi chạy | Module path và `module-info.java` không khớp | Module descriptor, packaging, compiler/module run config |
| Publish bị `401/403` hoặc thiếu repository | Credential/permission/repository target sai | CI secret scopes, publish config, network |

### 15.1. Xem Maven effective POM

Một project Maven có thể kế thừa parent POM, BOM và pluginManagement, khiến cấu hình hiệu dụng khác những dòng đang thấy trong child POM.

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn -e verify
~~~

- `help:effective-pom` cho biết cấu hình đã tính theo Maven model.
- `dependency:tree` mô tả graph phụ thuộc.
- `-e` bổ sung exception stack traces; `-X` bật debug log sâu hơn khi cần.

Cẩn trọng khi chia sẻ `-X` logs hoặc effective POM: build configurations có thể chứa URLs nội bộ, system properties và thông tin nhạy cảm. Dùng cơ chế masking/redaction trước khi đính kèm logs vào issue công khai.

### 15.2. Xem Gradle task graph và nguyên nhân dependency version

~~~bash
./gradlew tasks --all
./gradlew help --task build
./gradlew build --dry-run
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
~~~

`--dry-run` cho thấy các tasks dự kiến trong graph mà không thực thi task actions; nó không chứng minh build thật chắc chắn pass hoặc cache hit chính xác như lần chạy thực.

Khi cần log:

~~~bash
./gradlew build --info
~~~

`--debug` còn chi tiết hơn nhưng có thể rất lớn và nhạy cảm. **Không** dùng `--refresh-dependencies` hoặc xóa toàn bộ `~/.gradle` như phản xạ đầu tiên khi lỗi do code/build logic: refresh có thể tăng chi phí mạng, còn việc xóa cache thường che nguyên nhân thay vì sửa.

### 15.3. Phân biệt network, cache và artifact integrity

Maven/Gradle thường cache metadata và artifacts để giảm tải repository. Khi mất mạng:

- Maven `-o` hoặc `--offline` yêu cầu dùng artifacts/plugins đã cache **đầy đủ**; không có gì bảo đảm dependency chưa từng tải sẽ xuất hiện.
- Gradle `--offline` cũng không thể resolve artifact chưa có trong cache phù hợp.
- Nếu checksum/signature không khớp, **không bypass verification một cách vội vàng**; phải xác minh nguồn artifact và repository.
- Một version bị xóa khỏi upstream repo hoặc repository credentials thay đổi cũng là lý do hợp lệ khiến build trước chạy được nhưng CI mới fail.

Đối với các build cần supply-chain assurance, dependency verification và logging có kiểm soát hữu ích hơn việc vô hiệu hóa TLS/checksum checks.

## 16. Java 27 và module path khi build bằng Maven/Gradle

Maven và Gradle quản lý dependencies **ở cấp build**, nhưng **JPMS** quản lý readability/exports của Java named modules. Hai bài toán có giao nhau, không đồng nhất.

Nếu source có `module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Một build tool có thể xác định module path để compile/chạy theo JPMS nếu plugin/tooling được cấu hình tương thích. Nhưng:

- Dependency nằm trên Maven/Gradle classpath không tự là named module.
- Tên `requires` là **module name**, không nhất thiết trùng Maven `artifactId` hoặc Gradle project path.
- Automatic modules có tên theo manifest hoặc quy tắc suy ra của JDK, cần kiểm tra thật.
- Package phải được `exports` đúng đối tượng; `public` không tự vượt JPMS boundary.
- Một ứng dụng có test/annotation processor/reflection có thể cần cấu hình module path hoặc `--add-opens` cụ thể, nhưng không nên mở toàn bộ module chỉ để che lỗi cấu hình.

Với Gradle Application plugin, một named-module application còn khai:

~~~kotlin
application {
    mainModule = "com.example.app"
    mainClass = "com.example.app.Main"
}
~~~

Ví dụ module/entrypoint trên chỉ đúng khi nguồn thật khai báo module và class cùng tên. Với app **không** có `module-info.java`, dùng `mainClass` như phần 8 là đủ.

Tách ba bước để chẩn đoán:

~~~text
Dependency manager chọn artifacts/versions
                    │
                    ▼
Java compiler nhìn compile classpath/module path
                    │
                    ▼
JVM tại runtime nhìn đúng classpath/module graph
~~~

Build success không tự chứng minh executable distribution chứa đầy đủ runtime dependencies, đặc biệt nếu đóng một thin JAR. Luôn kiểm tra artifact thực tế được phát hành.

## 17. Custom build logic: viết task an toàn, tránh side effect khi cấu hình

Một trong những khác biệt lớn nhất là Gradle cho phép viết build logic linh hoạt bằng Kotlin/Groovy DSL. Tính linh hoạt không đồng nghĩa nên chạy mọi công việc ngay khi đánh giá file `build.gradle.kts`.

Ví dụ **không nên**:

~~~kotlin
// Chạy trong configuration phase, kể cả khi người dùng chỉ gọi "tasks":
// println(file("generated/report.txt").readText())
// val output = java.io.File("build/out.txt")
// output.writeText("generated") // side effect trong configuration
~~~

Tác hại:

- Công việc không cần thiết vẫn chạy khi không có task yêu cầu.
- Configuration cache khó tái sử dụng.
- Không có task inputs/outputs rõ ràng để Gradle áp dụng up-to-date/build cache.
- Thứ tự đánh giá script và side effects có thể gây lỗi giữa các môi trường.

Với công việc cần thực thi theo task, dùng lazy task registration và khai báo outputs/inputs thích hợp:

~~~kotlin
tasks.register("generateGreeting") {
    val outputFile = layout.buildDirectory.file("generated/greeting.txt")
    outputs.file(outputFile)

    doLast {
        val output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText("Xin chào từ Gradle", Charsets.UTF_8)
    }
}
~~~

Đây là **ví dụ dạy về task action**, không phải task class tối ưu hoàn chỉnh cho configuration cache và build cache trong production. Với task phức tạp, nên định nghĩa custom task type có `@Input`, `@OutputFile`, `@TaskAction` và Providers/Property API để Gradle hiểu inputs/outputs và hỗ trợ caching/isolated execution đúng.

Với Maven, không đưa custom logic vào POM dưới dạng shell script không kiểm soát chỉ vì Maven lifecycle có thể gọi plugin. Hãy sử dụng một plugin goal được duy trì, cấu hình execution ở phase thích hợp và ghi rõ các generated sources/resources thuộc quyền sở hữu task nào.

## 18. Lỗi tư duy thường gặp

| Ngộ nhận | Vì sao không chính xác | Cách hiểu đúng |
| --- | --- | --- |
| “Maven và Gradle dùng cùng một build lifecycle” | Maven có phases; Gradle có task graph và ba phases cấu hình/thực thi | So sánh theo **mục tiêu** thay vì ép tên giống nhau |
| “`mvn clean test` là một phase” | `clean` và `test` thuộc hai lifecycles | Hai yêu cầu phase nối tiếp trong một invocation |
| “`mvn package` chỉ đóng JAR” | Nó chạy các phases trước, gồm test khi có goal | Dùng lifecycle semantics |
| “`mvn deploy` triển khai app lên Kubernetes” | Maven deploy phase publish artifact vào repository | Tách artifact publication và application deployment |
| “`pluginManagement` tự chạy mọi goal đã khai báo” | Nó quản lý versions/config, không tự tạo mọi execution | Bind goals hoặc dùng packaging/plugin hợp lệ |
| “`dependencyManagement` tự thêm JAR” | Chỉ điều khiển dependency khi được dùng | Khai direct dependency phù hợp |
| “BOM là file lock dependencies” | BOM quản lý constraints, không khóa mọi artifact resolution trong mọi tool | Dùng locking/verification tùy nhu cầu |
| “`./gradlew assemble` luôn chạy unit tests” | `assemble` tập trung đóng gói | Dùng `build`/`check` khi cần verification |
| “Task đặt ở trên sẽ chạy trước” | Gradle thực thi theo dependencies/task graph | Dùng `dependsOn` và task inputs/outputs |
| “Gradle configuration phase là lúc chạy `compileJava`” | Compile là một task action thuộc execution phase | Phân biệt register/configure và execute |
| “Có toolchain 27 thì Gradle cũ bất kỳ chạy trên JDK 27” | Gradle version có compatibility matrix | Dùng release Gradle xác nhận hỗ trợ JDK 27 |
| “Chỉ dùng `sourceCompatibility=21` là đủ target Java 21” | Chưa chặn mọi Java 27 APIs | Dùng `options.release=21`/`--release 21` |
| “Gradle `implementation` luôn thành public API cho consumers” | `java-library` phân biệt `api` và `implementation` | Expose chỉ dependencies thật sự trong API |
| “Dùng test annotation là tự có test engine” | Framework/runner phải trên test classpath và được cấu hình | Pin test dependency/provider và chạy task thật |
| “Tăng số dependencies trực tiếp không có tác động” | Bề mặt lỗi ABI/supply chain lớn hơn | Chỉ thêm những gì thực sự dùng và audit định kỳ |
| “Mọi JAR có `Main.class` đều chạy `java -jar`” | JAR cần manifest và runtime deps phù hợp | Kiểm tra launcher/packaging/distribution |
| “Bật build cache làm mọi task có thể cache” | Task cần inputs/outputs và cacheability đúng | Kiểm tra task implementations và build outputs |
| “Một lần CI xanh chứng minh reproducibility” | Input ngầm/version động/remote repo có thể đổi | Pin tooling và verify artifacts qua nhiều môi trường |

## 19. Checklist thiết kế và review build Java 27

- [ ] Đã chọn rõ Maven hoặc Gradle làm nguồn sự thật cho build chính.
- [ ] Repository có Wrapper tương ứng, sử dụng bản build tool đã được nhóm xác minh.
- [ ] JDK 27/toolchain 27 khả dụng trong developer machines và CI.
- [ ] Nếu dùng Gradle chạy trên Java 27, bản Gradle đạt mốc hỗ trợ (9.8.0+ theo Compatibility Matrix hiện tại).
- [ ] Đã cấu hình `--release 27` hoặc target release khác đúng với hợp đồng phát hành.
- [ ] Các source sets/resources/tests có layout nhất quán.
- [ ] Maven POM có versions rõ cho compiler/test/packaging plugins dùng thực tế.
- [ ] Gradle build scripts phân biệt settings, configuration và task execution.
- [ ] Mỗi custom task có dependencies, inputs/outputs và side effects được khai báo hợp lý.
- [ ] Dependency scopes/configurations phản ánh compile/runtime/test thật.
- [ ] Không phụ thuộc ngầm vào transitive JAR nếu source trực tiếp dùng API của nó.
- [ ] Dependency graphs có thể kiểm tra bằng `dependency:tree` hoặc `dependencies`/`dependencyInsight`.
- [ ] BOM/platform/version catalogs được sử dụng đúng nghĩa và không nhầm với lock files.
- [ ] Các versions và plugins quan trọng được pin; hạn chế dynamic versions/SNAPSHOT cho release.
- [ ] Có kiểm tra integrity/provenance dependencies theo chính sách tổ chức.
- [ ] Build test/verification thực sự có test engine và tasks/goals được cấu hình.
- [ ] Integration tests không bị bỏ qua chỉ vì chạy một phase/task ngắn hơn.
- [ ] Thin JAR, executable JAR và full distribution được phân biệt rõ.
- [ ] Multi-module/module-path/JPMS được kiểm thử cả compile và runtime.
- [ ] CI lưu báo cáo tests, dependency failures và artifact metadata khi cần.
- [ ] Publish lên remote repository tách khỏi build kiểm thử thông thường.
- [ ] Build logs không làm lộ tokens, credentials hoặc internal repository secrets.
- [ ] Có thể tái hiện bằng một vài lệnh documented từ clean checkout.
- [ ] Cập nhật công cụ/dependencies định kỳ có kiểm soát, sau đó so sánh build graphs và kết quả test.

## 20. Tài liệu chính thức

### Maven

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — ba lifecycles, phases và plugin goals.
- [Apache Maven — Running Maven](https://maven.apache.org/run.html) — syntax CLI và cách chọn phase.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — scopes, transitives, conflict mediation và dependencyManagement.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — cấu trúc `pom.xml`, inheritance, plugins và project metadata.
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html) — giới hạn Java language/API/class-file target bằng `maven.compiler.release`.
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) — unit tests, engines/providers và plugin goals.
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/) — integration tests và goals `integration-test`/`verify`.

### Gradle

- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html) — initialization/configuration/execution và task graph.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — `compileJava`, `test`, `assemble`, `check`, `build`.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — `run`, `mainClass`, `distZip`, `installDist`.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — mốc hỗ trợ Java 27 và Gradle runtime/toolchains.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — `java.toolchain` và `options.release`.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html) — `api`, `implementation`, `runtimeOnly`, test scopes.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — cách tạo, dùng và pin Gradle distribution.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — tái dùng trạng thái configuration.
- [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html) — dependency locking và lock files.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — hashes/signatures và supply-chain verification.

**Kết luận:** Maven và Gradle đều giúp biến dự án Java 27 thành artifacts có thể kiểm thử, đóng gói và phát hành, nhưng **vòng đời build của chúng không phải cùng một khái niệm**. Maven điều phối các plugin goals qua **lifecycle phases** có thứ tự; Gradle xác định **task dependency graph** sau **initialization/configuration** rồi thực thi các tasks cần thiết. Nắm đúng mô hình, khóa phiên bản công cụ và dependencies, chọn toolchain Java 27 phù hợp, cấu hình tests thực sự và phân tách build khỏi publish sẽ giúp kết quả nhất quán giữa máy cá nhân và CI.
