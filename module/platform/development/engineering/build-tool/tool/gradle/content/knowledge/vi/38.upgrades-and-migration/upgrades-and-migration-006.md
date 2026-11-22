# Chuyển build Ant hoặc Maven sang Gradle có kiểm chứng

## 1. Mục tiêu: giữ đúng hợp đồng của build cũ

Một dự án Java có thể chuyển từ Apache Maven hoặc Apache Ant sang Gradle, báo `BUILD SUCCESSFUL` nhưng vẫn **làm sai những việc quan trọng**: mất integration tests, đổi runtime dependencies, không tạo generated sources, bỏ resource filtering, thay JAR manifest, thiếu classifier, publish khác Maven coordinates hoặc khiến CI bỏ qua một quality gate.

Vì vậy, “chuyển build thành công” phải được định nghĩa bằng **bằng chứng tương đương**, không chỉ bằng một lệnh Gradle exit code 0.

Sau bài học, bạn sẽ có khả năng:

- Lập baseline cho Maven/Ant trên một commit và toolchain được xác định.
- Hiểu Maven lifecycle, Ant target graph, Gradle task graph và những chỗ **không có mapping 1:1**.
- Dùng `gradle init` chuyển Maven ban đầu, xác định các Maven plugins/goals chưa được tự động chuyển.
- Dùng `ant.importBuild("build.xml")` làm cầu nối khi chuyển Ant theo giai đoạn.
- Chuyển dependency scopes, Maven BOM/parent, Ant local jars/Ivy, resources, code generation, profiles và tests.
- Chạy các ví dụ **Java 17 thực sự**, có lệnh `javac`/`java` và expected stdout.
- Đối chiếu dependency graph, test counts, JAR entries, output behavior, publication metadata và CI gates.
- Phân biệt khác biệt byte-for-byte với khác biệt phá vỡ hợp đồng runtime.
- Chuyển đổi có shadow CI, cutover, owner approval và rollback policy.

Một quy trình điển hình:

~~~text
Inventory old build
  |
  v
Capture baseline: commands, versions, artifacts, tests
  |
  v
Build Gradle skeleton alongside Maven/Ant
  |
  v
Port dependencies + plugins + targets incrementally
  |
  v
Run both builds at same commit and toolchain
  |
  +--> tests / stdout / deps / JAR entries / publishing metadata
  |
  v
Record PASS, FAIL or accepted differences
  |
  v
CI Gradle required gates + controlled release cutover
  |
  v
Retain rollback capability until stable
~~~

Không xóa `pom.xml` hay `build.xml` ngay. Tài liệu Gradle chính thức khuyên giữ cả hai builds song song cho đến khi xác minh output và tasks cần thiết. Hãy **tránh đổi cả source directory layout, dependency versions và build tool trong một commit**; sự thay đổi đồng thời khiến rất khó biết lỗi xuất phát từ đâu.

## 2. Maven, Ant và Gradle không cùng mô hình

| Góc nhìn | Maven | Ant | Gradle |
| --- | --- | --- | --- |
| Định nghĩa | `pom.xml`, project model, plugin goals. | `build.xml`, targets/tasks. | `settings.gradle.kts`/`build.gradle.kts`, plugins, task graph. |
| Execution | Lifecycle phases cố định. | Target graph tự xây bằng `depends`/`antcall`. | Task dependencies, configuration và execution phases. |
| Compile | Compiler plugin ở `compile`. | `<javac>`. | `compileJava` nhờ Java plugin. |
| Tests | Surefire, Failsafe khi được bind. | `<junit>`, custom targets. | `Test`/`test`, JVM Test Suites. |
| Packaging | `package` phase, jar/war/assembly. | `<jar>`/`<zip>`/`<copy>`. | `assemble`, `jar`, `war`, `distZip`, Zip/Jar tasks. |
| Dependencies | Scopes, BOM, `dependencyManagement`. | Lib folder, Ivy, custom retrieval. | Configurations, `platform`, constraints/variants. |
| Release | Maven install/deploy. | Copy/upload task tùy dự án. | `maven-publish`/publishing tasks. |
| Multi-module | Reactor `<modules>` + parent inheritance. | Nhiều Ant files, `<ant>`/`antcall>`. | `include`, project dependencies. |

Bốn lưu ý quan trọng:

1. Maven `verify` thường chạy các goals đã bind trong toàn bộ lifecycle tới `verify`; Gradle `check` chỉ chạy những tasks được nối vào graph.
2. Maven `package` gần với Gradle `assemble`, nhưng Maven Assembly descriptors không tự biến thành Gradle distribution.
3. Ant target `build` là tên do tác giả đặt, **không** tương đương tự động với Gradle lifecycle task `build`.
4. Gradle ưu tiên task inputs/outputs rõ để hỗ trợ incremental build/cache; port một Ant/Maven external command nhưng quên khai báo inputs có thể sinh cache hit sai.

## 3. Baseline trước khi sửa hệ thống

### 3.1. Danh mục bắt buộc ghi lại

Giữ log và artifact evidence từ **một Git SHA cố định**:
- Versions: Maven/Ant, Gradle nếu đã có, JDK vendor/release, OS, locale, encoding.
- Build commands/arguments thực: profiles, `-D` properties, CI environment.
- Modules, parent POM, Ant imports, extra tasks, dependencies và repositories.
- Compiler options, annotation processors, generated sources, resources filtering.
- Test classes/test counts, integration/functional suites, reports, ignored/skipped tests.
- Outputs: JAR/WAR/ZIP filenames, directories, manifests, resources, service descriptors.
- Maven groupId/artifactId/version, classifiers, POM publication, signing/deploy process.
- External effects: Docker images, codegen, db migrations, uploads; xác định cái gì **không** nên chạy trong PR.
- Release approval/secret scope và rollback mechanism.

### 3.2. Baseline Maven

Ví dụ các lệnh từ root Maven:

~~~bash
mvn -version
mvn -B -ntp clean verify

# Hiển thị kết quả parent POM, profiles, plugin management đã được kế thừa.
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
mvn -B -ntp help:active-profiles

# Dependency graph và selected versions.
mvn -B -ntp dependency:tree -DoutputFile=maven-deps.txt

# Thay bằng artifact path đúng của dự án.
jar tf target/migration-demo-1.0.0.jar
~~~

Maven Help/Dependency plugins có thể cần download lần đầu. `mvn clean verify` **không mặc nhiên chạy integration tests** trừ khi Failsafe/custom plugin goals đã bind vào lifecycle. Thông tin `effective-pom.xml` đặc biệt quan trọng: một project có parent POM/active profile có thể thực thi plugins không xuất hiện trong POM local.

### 3.3. Baseline Ant

~~~bash
ant -version
ant -p
ant -f build.xml clean package

# Ví dụ đường dẫn artifact do Ant script trong lab sinh:
jar tf target-ant/legacy-app.jar
~~~

Ant `-p` chủ yếu hiển thị targets có descriptions. Phải đọc `build.xml` cùng các file được import và target dependencies để hiểu đầy đủ. Ant không có lifecycle chuẩn giống Maven; target `package` của một build có thể **không có test**.

### 3.4. Bằng chứng cần giữ

| Bằng chứng | Mục đích |
| --- | --- |
| Tool versions và Git SHA | So đúng môi trường và source. |
| Test report XML + test counts | Phát hiện tests bị bỏ qua. |
| CLI stdout/exit codes | Behavioral parity. |
| Resolved dependency tree | Tránh missing runtime dependency và version drift. |
| JAR entry list + MANIFEST.MF | Phát hiện thiếu class/resource/metadata. |
| Runtime smoke test/consumer test | Xác minh published API thực sự chạy. |
| Publication POM/metadata | Giữ contract cho Maven/Gradle consumers. |
| SHA-256 artifacts | Byte identity khi contract yêu cầu. |
| CI job/approval log | Bảo đảm không lược quality/security gates. |

**Checksum khác không tự chứng minh migration sai:** Maven/Gradle có thể tạo ZIP entry order, timestamps hoặc manifest khác nhau nhưng hành vi tương đương. Ngược lại, checksum giống cũng không chứng minh integration tests đã chạy.

## 4. Maven → Gradle: dùng `gradle init` như điểm xuất phát

Tài liệu Gradle “Migrating Builds From Apache Maven” mô tả khả năng đọc POM và sinh Gradle build files từ project Maven:

~~~bash
# Chạy ở branch riêng sau khi đã lưu baseline.
gradle init
~~~

Có thể chọn Kotlin DSL khi công cụ hỏi hoặc chọn option init tương ứng nếu phiên bản Gradle hỗ trợ. Nhiều phiên bản còn có `--type pom`; xem `gradle help --task init` cho CLI thực tế.

Conversion ban đầu có thể giữ:
- Repositories được khai báo trong POM.
- External và inter-project dependencies.
- Settings cho Maven multi-module.
- Các Gradle plugins cơ bản như Java, War, Maven Publish.

**Không hứa công cụ chuyển hết** Maven Shade, Assembly, Failsafe profiles, custom codegen, Antrun, Enforcer, plugin executions đặc thù, resource filtering và signing/publish behavior.

Sau conversion:

~~~bash
gradle wrapper

./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew clean check assemble
~~~

Commit một Gradle Wrapper được xác minh, pin distribution version và kiểm tra `gradle-wrapper.jar`. Trên CI/Windows dùng `gradlew.bat`; không dựa vào Gradle system installation trôi version. Giữ Maven baseline chạy được cho đến lúc parity tests pass.

## 5. Maven dependency scopes và lifecycle mapping

### 5.1. Dependency scopes

| Maven | Gradle thông thường | Điều phải rà soát |
| --- | --- | --- |
| `compile` ở app | `implementation`. | Runtime/compile classpaths. |
| `compile` trong API public của library | `api` qua `java-library`. | Public signatures có type của dependency. |
| `runtime` | `runtimeOnly`. | Không có ở compile classpath. |
| `test` | `testImplementation`/`testRuntimeOnly`. | Test compile/runtime distinction. |
| `provided` | Thường `compileOnly`; tests đôi khi cần `testImplementation`. | Container/app server thực có cung cấp API không? |
| `system` | File dependency bridge, tốt hơn là publish module vào repo. | Local path không portable, thiếu POM transitive metadata. |
| `optional` | Gradle feature variants/capabilities khi publish optional feature. | Không tự coi `compileOnly` tương đương mọi optional contract. |
| `dependencyManagement` | `platform`, constraints hoặc platform project. | Version catalog alias không tự quản version của dependency khác. |
| Maven exclusions | `exclude(group=..., module=...)`/constraints. | So selected graph, không copy mù. |

**`api` không phải bản dịch mặc định của Maven `compile`.** Nếu dependency chỉ là implementation detail, `implementation` giúp tránh lộ dependency trên downstream compile classpath.

### 5.2. Maven BOM

Maven example:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.junit</groupId>
      <artifactId>junit-bom</artifactId>
      <version>5.11.4</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

`platform` đưa dependency constraints vào graph. BOM **không tự thêm** JUnit module; dependency vẫn phải được khai báo. `enforcedPlatform` force versions và có thể lan downstream trong published libraries, không áp dụng mặc định chỉ vì Maven sử dụng import BOM.

### 5.3. Lifecycle phases

| Maven | Gradle candidate | Khác biệt cần kiểm chứng |
| --- | --- | --- |
| `clean` | `clean`. | Output path khác Maven `target`. |
| `compile` | `compileJava`/`classes`. | Generated sources/resources. |
| `test` | `test`. | JUnit provider, test discovery. |
| `package` | `jar`/`war`/`assemble`. | Assembly, classifier, manifest. |
| `verify` | `check` với extra verification task dependencies. | Failsafe/static analysis không tự được nối. |
| `install` | `publishToMavenLocal` nếu cần tương tác Maven. | Thường không cần publish local giữa Gradle projects. |
| `deploy` | `publish...To<Repo>Repository` hoặc `publish`. | Publishing credentials, repository/gates. |

Đừng dùng `./gradlew :build` ở root multi-project rồi giả định mọi subproject tự được check; `:build` là root-only path. Task selector `./gradlew build` hoặc explicit `:core:check :app:check` phù hợp hơn khi muốn phủ toàn modules.

## 6. Lab Maven→Gradle đầy đủ: Java 17 và JUnit 5

Bài lab dùng **chung source tree**, giữ `pom.xml` và `build.gradle.kts` cạnh nhau trong migration window. Maven outputs nằm ở `target/`, Gradle outputs nằm ở `build/`.

### 6.1. File tree

~~~text
migration-demo/
├── pom.xml
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew / gradlew.bat / gradle/wrapper/...
└── src/
    ├── main/java/demo/migrate/
    │   ├── HelloService.java
    │   └── App.java
    └── test/java/demo/migrate/HelloServiceTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>dev.example</groupId>
  <artifactId>migration-demo</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Maven Compiler plugin có `--release 17`, Surefire 3.2.5 hỗ trợ JUnit 5. Maven Central/dependency resolution cần network hoặc local Maven cache đã có dependencies.

### 6.3. `src/main/java/demo/migrate/HelloService.java`

~~~java
package demo.migrate;

public final class HelloService {
    private HelloService() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                "Name must not be blank"
            );
        }
        return "Hello, " + name;
    }
}
~~~

### 6.4. `src/main/java/demo/migrate/App.java`

~~~java
package demo.migrate;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "World" : args[0];
        System.out.println(
            "MIGRATION_OK=" + HelloService.greet(name)
        );
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

### 6.5. `src/test/java/demo/migrate/HelloServiceTest.java`

~~~java
package demo.migrate;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HelloServiceTest {
    @Test
    void greetsAName() {
        assertEquals("Hello, Ada", HelloService.greet("Ada"));
    }

    @Test
    void rejectsBlank() {
        assertThrows(
            IllegalArgumentException.class,
            () -> HelloService.greet(" ")
        );
    }
}
~~~

### 6.6. Chạy Maven baseline

~~~bash
mvn -B -ntp clean verify
java -cp target/classes demo.migrate.App Ada
jar tf target/migration-demo-1.0.0.jar
~~~

Java stdout (không bao gồm Maven logs):

~~~text
MIGRATION_OK=Hello, Ada
ARG_COUNT=1
~~~

JUnit report nằm dưới `target/surefire-reports/`, gồm hai test methods. Nếu repo sử dụng tests khác ngoài unit, phải chụp thêm baseline tương ứng trước migration.

### 6.7. `settings.gradle.kts`

~~~kotlin
rootProject.name = "migration-demo"
~~~

### 6.8. `build.gradle.kts`

~~~kotlin
plugins {
    java
}

group = "dev.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Gradle Java plugin dùng `src/main/java` và `src/test/java` theo conventions. `tasks.test.useJUnitPlatform()` giúp chạy Jupiter tests; `junit-platform-launcher` phục vụ JUnit Platform runtime. `group/version` và project name giữ artifact coordinate/naming trong lab.

### 6.9. Chạy Gradle và so hành vi

~~~bash
./gradlew --version
./gradlew clean test jar
./gradlew check assemble

java -cp build/classes/java/main demo.migrate.App Ada
jar tf build/libs/migration-demo-1.0.0.jar
~~~

Stdout do Java main phải giống Maven:

~~~text
MIGRATION_OK=Hello, Ada
ARG_COUNT=1
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean test jar
java -cp build/classes/java/main demo.migrate.App Ada
jar tf build/libs/migration-demo-1.0.0.jar
~~~

Gradle test XML/HTML reports mặc định ở `build/test-results/test/` và `build/reports/tests/test/`. Kiểm tra **đủ hai test methods** và các test dự án thực, không chỉ task pass `NO-SOURCE`.

### 6.10. `javac`/`java` độc lập

Linux/macOS:

~~~bash
mkdir -p build/manual
javac -encoding UTF-8 -d build/manual \
  src/main/java/demo/migrate/HelloService.java \
  src/main/java/demo/migrate/App.java

java -cp build/manual demo.migrate.App Ada
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual | Out-Null
javac -encoding UTF-8 -d build/manual src/main/java/demo/migrate/HelloService.java src/main/java/demo/migrate/App.java
java -cp build/manual demo.migrate.App Ada
~~~

Output:

~~~text
MIGRATION_OK=Hello, Ada
ARG_COUNT=1
~~~

Đây chỉ là đối chiếu Java source, không tự chứng minh Maven plugin configs và Gradle tasks tương đương.

### 6.11. Đối chiếu stdout tự động

~~~bash
mvn -B -ntp clean verify
java -cp target/classes demo.migrate.App Ada > old-output.txt

./gradlew clean check assemble
java -cp build/classes/java/main demo.migrate.App Ada > new-output.txt

diff -u old-output.txt new-output.txt
~~~

`diff -u` không in gì và trả exit status 0 nếu nội dung giống nhau. Nếu các ứng dụng thực đọc external dependencies, `java -cp target/classes`/`java -cp build/classes/java/main` **chưa đủ**: phải chạy với full runtime classpath hoặc distribution launcher.

Không ép JAR SHA-256 bằng nhau nếu không có byte-identity contract: Gradle và Maven có thể dùng manifest/entry order/timestamp khác. So `jar tf`, service descriptors, resources và consumer behavior. Nếu cần byte-for-byte, pin JDK/compiler/options, reproducible ZIP settings và cả metadata trước khi so SHA.

## 7. Lab Ant→Gradle: import để giữ hành vi, sau đó chuyển sang native tasks

Ant không có chuẩn build layout. Lab dùng `src/legacy` và `target-ant` để chứng minh Gradle có thể giữ cấu trúc cũ trong migration window.

### 7.1. File tree

~~~text
ant-lab/
├── build.xml
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew / gradlew.bat / gradle/wrapper/...
└── src/legacy/demo/legacy/LegacyHello.java
~~~

### 7.2. `src/legacy/demo/legacy/LegacyHello.java`

~~~java
package demo.legacy;

public final class LegacyHello {
    private LegacyHello() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "World" : args[0];
        System.out.println("ANT_MIGRATION_OK=" + name);
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

### 7.3. `build.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-lab" default="package" basedir=".">
    <property name="src.dir" value="src/legacy"/>
    <property name="out.dir" value="target-ant"/>
    <property name="classes.dir" value="target-ant/classes"/>

    <target name="clean" description="Clean legacy outputs">
        <delete dir="${out.dir}"/>
    </target>

    <target name="compile" description="Compile Java 17">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="17"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile"
            description="Package Java classes">
        <jar destfile="${out.dir}/legacy-app.jar"
             basedir="${classes.dir}"/>
    </target>
</project>
~~~

Ant version phải hỗ trợ attribute `release` của `<javac>` và `JAVA_HOME` phải trỏ JDK 17. `includeantruntime=false` ngăn Ant runtime vô tình xuất hiện trong compilation classpath.

### 7.4. Ant baseline

~~~bash
ant -f build.xml clean package
java -cp target-ant/classes demo.legacy.LegacyHello Ada
jar tf target-ant/legacy-app.jar
~~~

Expected Java stdout:

~~~text
ANT_MIGRATION_OK=Ada
ARG_COUNT=1
~~~

### 7.5. Cầu nối: `ant.importBuild`

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "ant-lab"
~~~

`build.gradle.kts` — **phiên bản bridge, dùng riêng giai đoạn đầu**:

~~~kotlin
ant.importBuild("build.xml")

tasks.register("verifyLegacy") {
    dependsOn("package")
}
~~~

Chạy:

~~~bash
./gradlew package
./gradlew verifyLegacy
~~~

Ant targets `clean`/`compile`/`package` trở thành Gradle tasks và giữ target dependency `package -> compile`. Output vẫn nằm tại `target-ant/`, Java stdout không thay.

**Giới hạn quan trọng:** Gradle docs nói `ant.importBuild` **không hỗ trợ Configuration Cache**. Đây là lộ trình bridge, chưa phải trạng thái cuối nếu muốn tận dụng Gradle caching/performance. Không đánh giá nó như một native Gradle implementation.

### 7.6. Tên task bị trùng

Nếu vừa thêm `java`/`java-library` plugin vừa import Ant, các tên `build`/`clean`/`jar` có thể trùng tasks Gradle. Có thể dùng rename transformer:

~~~kotlin
plugins {
    `java-library`
}

ant.importBuild("build.xml") { oldName ->
    if (oldName == "build") "ant_build" else oldName
}
~~~

Đây chỉ là **mảnh giải thích** cơ chế rename cho Ant target `build`; Ant lab trên còn có target `clean` nên **không** nên chép y nguyên trong lab rồi nghĩ không có collision. Muốn native replacement cho mẫu đơn giản, **bỏ hoàn toàn import** và dùng script tiếp theo.

### 7.7. Thay toàn bộ `build.gradle.kts` bằng native version

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

sourceSets {
    main {
        java.srcDirs("src/legacy")
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.jar {
    archiveFileName.set("legacy-app.jar")
}

tasks.register<JavaExec>("runLegacy") {
    group = "verification"
    description = "Run the old Java entry point"
    dependsOn(tasks.named("classes"))
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("demo.legacy.LegacyHello")
    args("Ada")
}
~~~

Native Gradle Java plugin tạo `compileJava`, `classes`, `jar`, `check`, `assemble` và `build`. `sourceSets.main.java.srcDirs("src/legacy")` cho Gradle biết thư mục Java cũ; không cần di chuyển source. `archiveFileName` giữ **file name** `legacy-app.jar` nhưng output path là `build/libs/legacy-app.jar` thay vì `target-ant/legacy-app.jar`.

### 7.8. Chạy native Gradle và kiểm tra

~~~bash
./gradlew clean classes jar runLegacy

java -cp build/classes/java/main demo.legacy.LegacyHello Ada
jar tf build/libs/legacy-app.jar
~~~

Expected stdout của Java:

~~~text
ANT_MIGRATION_OK=Ada
ARG_COUNT=1
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean classes jar runLegacy
java -cp build/classes/java/main demo.legacy.LegacyHello Ada
jar tf build/libs/legacy-app.jar
~~~

Task `runLegacy` **không tự chạy trong `check`**; nếu smoke test phải là quality gate thì thêm explicit dependency hoặc CI step. Ant `target-ant/` và Gradle `build/` khác nhau; nếu downstream shell scripts đòi đường dẫn cũ, tạo compatibility task có declared output hoặc cập nhật consumer rõ ràng.

## 8. Maven multi-module, profiles và dependencies

### 8.1. Reactor modules khác parent POM

Maven aggregator:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>core</module>
    <module>service</module>
</modules>
~~~

Gradle `settings.gradle.kts`:

~~~kotlin
rootProject.name = "multi-gradle"
include("core", "service")
~~~

Gradle `service/build.gradle.kts` (mảnh):

~~~kotlin
plugins {
    java
}

dependencies {
    implementation(project(":core"))
}
~~~

Đừng coi Maven `<modules>` và `<parent>` giống nhau. Maven parent có thể truyền `dependencyManagement`, properties và plugin configuration; Gradle không tự có inheritance y hệt. Chọn convention plugins/platform/constraints/version catalog hoặc shared build logic có kiểm chứng.

### 8.2. Maven profiles

Maven `-Pprod` và `<profiles>` có activation rules dựa OS/JDK/env/property. Gradle không có Maven profiles native: dùng Gradle Providers/project properties để mô hình hóa từng quyết định, nhưng **không để profile production tự bật credentials trên PR job**.

Ví dụ Gradle Kotlin DSL mảnh:

~~~kotlin
val environmentName = providers
    .gradleProperty("environmentName")
    .orElse("dev")

tasks.register("showEnvironment") {
    val captured = environmentName
    doLast {
        println("ENV=" + captured.get())
    }
}
~~~

Chạy:

~~~bash
./gradlew showEnvironment -PenvironmentName=staging
~~~

Task in:

~~~text
ENV=staging
~~~

Với dự án thật, các settings liên quan repositories, Java toolchains và publishing phải được kiểm tra từng profile, không chỉ ánh xạ tên `-Pprod` thành một Gradle property.

### 8.3. Resources filtering

Maven Resources Plugin có thể thay template variables; Java plugin của Gradle **không tự áp Maven filtering rules**. Ví dụ:

`src/main/resources/build-info.properties`:

~~~properties
releaseVersion=${releaseVersion}
~~~

Mảnh Gradle:

~~~kotlin
tasks.processResources {
    val releaseVersion = providers
        .gradleProperty("releaseVersion")
        .orElse(project.version.toString())

    inputs.property("releaseVersion", releaseVersion)

    filesMatching("build-info.properties") {
        expand("releaseVersion" to releaseVersion.get())
    }
}
~~~

Kiểm chứng **bytes thực tế** trong `build/resources/main/build-info.properties` hoặc packaged JAR, vì syntax filter/escaping/encoding có thể khác Maven. Không đặt secrets hoặc current timestamp vào filtered resource như một mặc định.

### 8.4. Generated sources

Maven build-helper, protobuf, OpenAPI, JAXB, Ant custom codegen hoặc annotation processors có thể tạo Java code trước compile. Gradle cần một **producer task** có declared inputs/outputs rồi wire source directory Provider vào `sourceSets`. Đừng để Gradle phụ thuộc `target/generated-sources` còn sót từ lần Maven build trước: clean CI sẽ không có nó.

~~~text
generateSources (tracked inputs -> output dir)
         |
         v
sourceSets.main.java.srcDir(generatedOutputProvider)
         |
         v
compileJava -> classes -> jar
~~~

### 8.5. Integration tests/Failsafe

Maven Surefire thường chạy unit tests ở phase `test`; Maven Failsafe được bind cho integration-test/verify và có thể setup/cleanup servers. Trong Gradle:
- Default `test` không tự chứa integration suite khác.
- Tạo thêm JVM Test Suite hoặc source set + Test task.
- Additional suite thường cần `implementation(project())` để test production code.
- Nối `integrationTest` vào `check` bằng `dependsOn`.
- Nếu cần teardown server ngay cả khi test fail, dùng `finalizedBy(cleanupTask)`.
- `shouldRunAfter` chỉ áp ordering khi tasks cùng được chọn, **không** kéo task tự chạy.

Mảnh Kotlin DSL (trong project có Java/JVM Test Suite support):

~~~kotlin
testing {
    suites {
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
            }
        }
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

Check XML reports và test counts; `BUILD SUCCESSFUL` với `NO-SOURCE` **không** chứng minh migration integration tests đã xong.

## 9. Ant local dependencies, Ivy, targets và file operations

### Ant jars tạm thời

Ant XML:

~~~xml
<path id="compile.classpath">
    <fileset dir="lib" includes="*.jar"/>
</path>
~~~

Gradle bridge:

~~~kotlin
dependencies {
    implementation(fileTree("lib") {
        include("*.jar")
    })
}
~~~

File dependencies không có Maven POM/transitive metadata và dễ lỗi runtime, vì vậy đây là bước chuyển tiếp. Đích cuối là `implementation("group:artifact:version")` từ repository được kiểm soát, với dependency locking/verification khi cần.

### Ant Ivy

Map Ivy configurations và repository patterns sang Gradle dependency configurations/Ivy repository. Ant `retrieve` thường copy JAR vào local `lib`; Gradle thường dùng dependency cache trực tiếp, không cần copy. Nếu external compiler/tool yêu cầu file layout cụ thể, viết `Copy` task với declared inputs/outputs và review dependency paths.

### Ant tasks

| Ant element | Gradle thường dùng |
| --- | --- |
| `<javac>` | `JavaCompile`/Java plugin. |
| `<copy>` | `Copy`/`processResources`. |
| `<delete>` | `Delete`/`clean`. |
| `<jar>`, `<zip>`, `<tar>` | `Jar`/`Zip`/`Tar`. |
| `<unzip>` | `Copy` + `zipTree(...)`. |
| `<junit>` | `Test` task. |
| `<exec>` | `Exec`, `JavaExec` hoặc custom task type. |
| `<checksum>` | Custom verifier/Java API hoặc Gradle plugin. |
| `<ant>`/`<antcall>` | Project/task dependencies hoặc bridge import. |

Khi port, kiểm tra globs, relative paths, encoding, line endings, file modes, duplicate handling, Ant properties và environment. Một task `doLast { ant.copy(...) }` có thể chạy nhưng không khai báo file inputs/outputs, làm incremental builds/cache không chính xác. Đích tốt nhất thường là native task types + Providers.

## 10. Packaging và publication: “artifact giống” nghĩa gì?

Maven/Ant và Gradle có thể tạo JAR/WAR/ZIP khác nhau một chút. Kiểm tra theo nhiều tầng:

1. **Public API & runtime behavior:** classes có đủ, app chạy được, external consumer kết nối được.
2. **Archive structure:** `META-INF/MANIFEST.MF`, service loaders, application scripts, properties, resource paths.
3. **Dependency distribution:** runtime libraries có đủ, fat JAR relocations/service descriptors đúng nếu dùng Shade/Shadow.
4. **Publication contract:** `group:artifactId:version`, POM scopes, Gradle Module Metadata, classifiers `sources`/`javadoc`, signatures.
5. **Byte reproducibility:** SHA-256 nếu release policy thật sự yêu cầu bit-for-bit identity.

Maven Assembly descriptors và Shade relocation config không được tự chuyển bởi `gradle init`. Với Application plugin `distZip` sẽ tạo launch scripts và runtime libs; plain `jar` của app **không tự đóng mọi runtime dependencies**. Nếu Maven cũ tạo executable fat JAR, phải thiết kế artifact tương ứng rõ ràng.

### Maven Publish khi cần

Mảnh Gradle Kotlin DSL cho Java library (hợp nhất vào build file phù hợp, không để hai `plugins` blocks):

~~~kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "dev.example"
version = "1.0.0"

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            artifactId = "migration-demo"
            from(components["java"])
        }
    }
    repositories {
        maven {
            name = "staging"
            url = uri(layout.buildDirectory.dir("maven-staging"))
        }
    }
}
~~~

Đây là **mảnh mở rộng**, không thuộc lab Maven đơn giản trước đó. Chỉ thêm sources/javadoc nếu baseline publication cần; đừng tự mở rộng classifiers khi parity policy còn chưa quyết.

~~~bash
./gradlew publishMavenJavaPublicationToStagingRepository
~~~

Sau publication, hãy dùng **external consumer** resolve artifact từ staging file repo và kiểm tra Maven POM/Gradle Module Metadata, vì Gradle `project(":core")` dependency nội bộ không thay thế kiểm thử published metadata. Gradle-generated POM có thể không giống text POM Maven ban đầu; cần so consumer semantics, không mặc định byte equality.

Không dùng cả Maven deploy và Gradle publish **đẩy hai JAR khác bytes cùng một release version** lên production repository trong thời gian shadow CI. Một release chỉ có **một publisher**.

## 11. Ma trận kiểm chứng trước cutover

| Mục | Maven/Ant baseline | Gradle candidate | PASS khi |
| --- | --- | --- | --- |
| Tools | Maven/Ant/JDK versions. | Wrapper/JDK versions. | Pin, hiểu mọi khác biệt. |
| Source/codegen | Java/resources/generated source paths. | sourceSets/task graph. | Không mất file/generator. |
| Unit tests | Test count, pass/fail/skip. | Test reports. | Counts và contract tương đương. |
| Integration tests | Failsafe/custom targets. | Gradle suite/Test tasks. | Có setup/teardown, gates. |
| Dependency tree | Compile/runtime selected versions. | Gradle configurations. | Không missing/transitive drift bất ngờ. |
| Behavior | CLI expected stdout/exit. | CLI expected stdout/exit. | Golden tests match. |
| Artifact structure | JAR/WAR/ZIP list/manifest. | Gradle archives. | Required entries và metadata đủ. |
| Publishing | GAV, POM, signatures/classifiers. | MavenPublication. | Consumers resolve đúng. |
| CI/CD | Commands/approvals/secrets. | Tasks/jobs/release scopes. | Không mất gate hay lộ quyền. |
| Clean build | No hidden local prerequisites. | Fresh Gradle workspace. | Không dựa `target/`/Ant old outputs. |
| Cache | Legacy behavior. | Up-to-date/Build Cache. | Correctness không đổi khi reuse. |

Ghi mỗi dòng `PASS`, `FAIL` hoặc `ACCEPTED DIFFERENCE` kèm evidence/owner. Đừng ép tất cả JAR SHA phải giống nếu baseline không có byte-reproducibility policy, nhưng cũng không chấp nhận các class/resource quan trọng bị mất.

## 12. CI shadow build: chạy hai tool trên cùng Git SHA

Ví dụ GitHub Actions cho **Maven lab**:

~~~yaml
name: Maven to Gradle parity

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-both:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify toolchain
        run: |
          java -version
          mvn -version
          ./gradlew --version

      - name: Old Maven verification
        run: |
          mvn -B -ntp clean verify
          java -cp target/classes demo.migrate.App Ada > old-output.txt

      - name: New Gradle verification
        run: |
          ./gradlew clean check assemble --console=plain --stacktrace
          java -cp build/classes/java/main demo.migrate.App Ada > new-output.txt

      - name: Fail if behavior differs
        run: diff -u old-output.txt new-output.txt

      - name: Collect JAR structure evidence
        run: |
          jar tf target/migration-demo-1.0.0.jar | sort > old-jar.txt
          jar tf build/libs/migration-demo-1.0.0.jar | sort > new-jar.txt

      - name: Store parity evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: migration-parity
          path: |
            old-output.txt
            new-output.txt
            old-jar.txt
            new-jar.txt
            target/surefire-reports/**
            build/test-results/test/**
          if-no-files-found: ignore
~~~

Tại đây:
- Maven và Gradle cùng checkout commit, hai output directories khác nhau.
- `diff -u` là **hard gate về Java stdout**.
- JAR entry lists được lưu để review, chưa ép giống 100% vì manifest/metadata có thể khác hợp lệ.
- Runner phải có Maven (GitHub-hosted Ubuntu thường có; tự pin/validate hoặc dùng Maven Wrapper trong production).
- `setup-gradle@v6` chỉ setup/caching/wrapper validation; không tự tạo Gradle build.
- `mvn clean verify` được chọn trước `./gradlew clean check assemble` nhưng vẫn cần xem JUnit reports để bảo đảm tests thực sự chạy.
- Không cấp publishing credentials trong PR parity workflow.
- Với Ant, thay Maven step bằng `ant -f build.xml clean package` và so `ANT_MIGRATION_OK=Ada`; đừng copy lệnh Maven nguyên xi.
- Trong production nên pin actions SHA đã review, bảo vệ `main`/workflows bằng required checks/reviews.

## 13. Cutover có kiểm soát, rollback và trách nhiệm

### Chiến lược theo module

1. Chọn module lá có ít dependencies, xác nhận baseline.
2. Port Java compile/resources/tests; Gradle và Maven/Ant cùng chạy.
3. Map dependencies, BOM, exclusions và publication metadata.
4. Chuyển generators, integration suites và custom build goals.
5. So parities ở CI, thêm regression tests cho từng lệch trước đó.
6. Chạy Gradle như required verification gate.
7. Xác định một publisher duy nhất cho mỗi release tag/version.
8. Giữ Maven/Ant làm fallback trong migration window.
9. Sau đủ số release/CI runs thành công, mới dọn build cũ và scripts tương ứng.
10. Ghi documented rollback trigger và command.

### Khi phải rollback

- Dừng Gradle publication/deployment.
- Giữ Git SHA, logs, test reports, artifacts và dependency graphs.
- Chạy Maven/Ant baseline từ exact source revision để xác định regression.
- Khôi phục old CI job qua review/approval, không lộ secrets cho PR.
- Nếu version mới đã publish vào immutable Maven repo, không overwrite cùng GAV bằng bytes khác; dùng version mới hoặc incident policy.
- Thêm parity regression test trước khi thử cutover lại.

Đây là quá trình **giảm rủi ro**, không phải thất bại: khả năng rollback chủ động là tiêu chí của một migration có kiểm chứng.

## 14. Troubleshooting

| Lỗi | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| `gradle init` tạo files nhưng thiếu assembly | Maven Assembly không tự chuyển. | Chọn Application/Distribution/Zip/Jar tasks theo artifact contract. |
| Maven `verify` có integration tests, Gradle `check` không | Test Suite chưa được khai báo/nối graph. | Integration suite + dependsOn check. |
| Gradle JUnit test `NO-SOURCE` | Source dirs/JUnit setup không đúng. | Kiểm tra `src/test/java`, reports, task inputs. |
| Gradle JUnit5 không chạy | Thiếu Jupiter/runtime Launcher/useJUnitPlatform. | Cấu hình đúng dependencies/Test task. |
| Build pass nhưng runtime ClassNotFound | Maven compile/runtime scopes chuyển sai. | `dependencies`/`dependencyInsight` và runtimeClasspath. |
| BOM versions đổi | `dependencyManagement` chưa chuyển. | `platform` + kiểm tra selected versions. |
| `api`/`implementation` làm client compile sai | Published compile API khác Maven. | Dùng `java-library`, inspect POM/Module Metadata. |
| Maven parent properties thiếu | Parent inheritance chưa port. | Convention plugins, constraints/platform. |
| Maven profiles không có ở Gradle | Gradle dùng project properties, không có native Maven profiles. | Model build flavor bằng Providers và CI flags. |
| Resource vẫn chứa template token | Gradle chưa filtering hoặc syntax khác. | ProcessResources + byte-level tests. |
| Codegen chạy Maven nhưng không chạy Gradle | Chưa tạo/wire producer task. | Declare inputs/outputs và generated source Provider. |
| `ant.importBuild` không dùng Configuration Cache được | Ant import hiện không hỗ trợ. | Bridge tạm, chuyển native Gradle tasks. |
| Ant `clean` trùng Gradle task | Apply native plugin khi còn Ant import. | Rename target hoặc bỏ import khi thay native. |
| Gradle lib folder thiếu JAR | FileTree/Ivy dependency migration sai. | Migrate metadata, resolve graph. |
| `target/` khác `build/` | Output convention thay. | Update consumer hoặc compatibility copy task. |
| JAR SHA khác nhưng Java behavior giống | Manifest/entry order/timestamps khác. | So structural/consumer contract, pin reproducibility nếu cần. |
| CI Gradle nhanh nhưng chưa chạy tests | `SKIPPED`/`NO-SOURCE`/task selection sai. | Kiểm tra test reports và required tasks. |
| Gradle publication Maven GAV không đúng | project.name, group/version, artifactId khác. | Set MavenPublication tường minh và consumer test. |
| Maven Local che lỗi production repo | Có artifact cũ trong `~/.m2`. | Clean external consumer và staging repo. |
| CI hai builds upload cùng release version | Migration shadow pipeline vẫn có hai publishers. | Verification-only shadow, một publisher. |
| Cache output sai | Input/output tracking thiếu hoặc nondeterministic. | No-cache control, sửa task model. |
| Java toolchain trên CI không phù hợp | Gradle/JDK compatibility/version khác. | Pin Wrapper và Java 17 toolchain. |

## 15. Checklist và câu hỏi tự kiểm tra

Checklist trước khi tuyên bố `MIGRATION=PASS`:

- [ ] Baseline chụp đúng Git commit, Maven/Ant/JDK versions.
- [ ] Effective POM/Ant targets, active profiles và dependencies được liệt kê.
- [ ] Source/test/resource/generated paths được giữ hoặc thay có lý do.
- [ ] Maven scopes/BOM/exclusions và Ant local jars/Ivy được map.
- [ ] Toolchain Java 17 và encoding/annotation processors phù hợp.
- [ ] Unit/integration tests được phát hiện và chạy đủ.
- [ ] `check` gồm tất cả required quality gates.
- [ ] Java stdout và exit codes được so tự động.
- [ ] JAR/WAR/ZIP entries, manifest và runtime dependencies được kiểm tra.
- [ ] POM/Gradle Module Metadata và external consumer resolution được test.
- [ ] Không phụ thuộc Maven `target/` outputs cũ trong clean Gradle CI.
- [ ] Ant bridge không bị nhầm với native migration hoàn tất.
- [ ] CI shadow chỉ verify, không publish trùng GAV.
- [ ] Những khác biệt chấp nhận được có owner approval.
- [ ] Rollback plan và protected release credentials đã rõ.

Câu hỏi:
1. Vì sao một Gradle build xanh chưa chứng minh migration đúng?
2. Maven `verify` và Gradle `check` khác nhau thế nào?
3. Gradle Init không tự chuyển những Maven plugin behavior nào?
4. Vì sao phải đọc `effective-pom` khi dự án dùng parent/profiles?
5. Maven `compile` map sang `api` hay `implementation` khi nào?
6. `platform` và `enforcedPlatform` khác gì?
7. Maven reactor `<modules>` có cùng nghĩa với parent POM không?
8. Ant `ant.importBuild` dùng để làm gì và có hỗ trợ Configuration Cache không?
9. Vì sao Ant `build`/`clean` có thể đụng task names Gradle?
10. Vì sao nên giữ `src/legacy` trước khi đổi layout?
11. Gradle `test` có tự chạy Maven Failsafe integration tests không?
12. Tại sao generated sources cần producer task?
13. Byte-identical JAR khác behavioral parity ở điểm nào?
14. Một `jar tf` diff có đủ chứng minh published Maven POM đúng không?
15. Vì sao phải kiểm thử external consumer từ staging repo?
16. Tại sao không cho cả Maven và Gradle deploy cùng immutable GAV?
17. Điều kiện nào khiến bạn **không** cutover dù Gradle `build` thành công?
18. Khi Gradle release artifact đã publish sai, rollback cần bảo vệ điều gì?

## 16. Tài liệu chính thức

- [Gradle — Migrating Builds From Apache Maven](https://docs.gradle.org/current/userguide/migrating_from_maven.html): Maven lifecycle, dependencies/BOMs, profiles, integration tests, plugins.
- [Gradle — Migrating Builds From Apache Ant](https://docs.gradle.org/current/userguide/migrating_from_ant.html): Ant import, staged migration, Ivy, file tasks, Configuration Cache limitation.
- [Gradle — Using Ant from Gradle](https://docs.gradle.org/current/userguide/ant.html): `ant.importBuild` và task dependencies.
- [Gradle — Build Init Plugin](https://docs.gradle.org/current/userguide/build_init_plugin.html): `gradle init` Maven conversion.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): sourceSets, Java compile, lifecycle tasks.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Gradle Test/JUnit.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): additional integration suites.
- [Gradle — Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html): configurations/version resolution.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): Copy/Zip, filtering, file model.
- [Gradle — Maven Publish](https://docs.gradle.org/current/userguide/publishing_maven.html): publications/POM/metadata.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pinned distributions/checksums.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/signature policies.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task input/output correctness.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): Maven phases/goals.
- [Apache Maven — Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/): JUnit provider/reports.
- [Apache Ant — Manual](https://ant.apache.org/manual/): Ant targets, javac, jar, filesets.
