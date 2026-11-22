# Ánh xạ target Ant sang lifecycle Maven hoặc task Gradle

Khi chuyển một dự án Java từ **Apache Ant** sang **Apache Maven** hoặc **Gradle**, câu hỏi quan trọng nhất không phải là “đổi tên mỗi target thành gì?”, mà là **công việc của target đó thuộc giai đoạn nào, cần đầu vào gì, tạo đầu ra gì, và được kích hoạt khi nào**. Ant cho phép người viết tự định nghĩa hầu như toàn bộ quy trình bằng các target và quan hệ `depends`. Maven cung cấp lifecycle có thứ tự phase tiêu chuẩn; Gradle cung cấp một đồ thị task, trong đó nhiều task được plugin tạo sẵn và có cơ chế theo dõi đầu vào/đầu ra.

Bài học này hướng dẫn cách đọc một `build.xml` hiện hữu, xác định tương đương chức năng trong Maven hoặc Gradle, ánh xạ các target biên dịch, kiểm thử, đóng gói và phát hành, đồng thời xử lý những công việc tùy biến không nằm trong quy trình Java chuẩn.

## 1. Ba mô hình build: target, phase và task

### Ant: chủ động định nghĩa mục tiêu và phụ thuộc

Trong Ant, target có thể gồm nhiều task theo thứ tự XML; các target được nối với nhau bằng `depends`:

```xml
<project name="catalog" default="dist">
    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="src"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="jar" depends="compile">
        <jar destfile="dist/catalog.jar"
             basedir="build/classes"/>
    </target>

    <target name="dist" depends="jar"/>
</project>
```

Chạy `ant -f build.xml dist` khiến Ant thực hiện `init → compile → jar → dist`. Tên `compile` hay `dist` do dự án chọn; Ant không tự gán cho chúng một ý nghĩa chuẩn như Maven. Một target tên `test` có thể chạy JUnit, gọi script, hoặc chỉ in thông báo: phải **đọc phần thân target** mới biết công việc thật.

### Maven: lựa chọn phase trong lifecycle

Maven định nghĩa ba lifecycle chính:

- `default`: các bước xây dựng và phát hành artifact.
- `clean`: dọn đầu ra của build.
- `site`: tạo tài liệu/site của dự án.

Một số phase quen thuộc của lifecycle `default` là:

```text
validate
   ↓
generate-sources
   ↓
process-resources
   ↓
compile
   ↓
test-compile
   ↓
test
   ↓
package
   ↓
integration-test
   ↓
verify
   ↓
install
   ↓
deploy
```

Sơ đồ chỉ thể hiện các mốc thường gặp; giữa chúng còn nhiều phase chi tiết khác. Khi gọi `mvn package`, Maven chạy các phase cần thiết từ đầu lifecycle `default` đến hết `package`; plugin goal được liên kết với các phase sẽ thực hiện công việc tương ứng. `mvn clean package` chạy thêm lifecycle `clean` trước khi xây dựng gói.

**Phase không phải target tùy ý**: người dùng không tạo một phase tên `my-dist` như tạo `<target name="my-dist">` của Ant. Thay vào đó, cấu hình plugin goal vào phase thích hợp hoặc tạo một plugin/mô-đun có vai trò riêng.

### Gradle: đồ thị task và plugin

Gradle có task tương tự khái niệm target của Ant, nhưng plugin có thể cung cấp sẵn task và quan hệ phụ thuộc:

```text
build
 ├── assemble
 │    └── jar
 │         └── classes
 │              ├── compileJava
 │              └── processResources
 └── check
      └── test
           └── testClasses
                ├── compileTestJava
                └── processTestResources
```

Đây là cấu trúc minh họa khi áp dụng plugin `java`; các task/plugin bổ sung có thể thay đổi đồ thị cụ thể. Chạy `./gradlew build` để Gradle xác định những task cần thiết từ đồ thị, không phải chạy tuần tự tất cả dòng được viết trong `build.gradle`.

Vì vậy:

| Khái niệm | Ant | Maven | Gradle |
| --- | --- | --- | --- |
| Đơn vị công việc | `target` chứa task Ant | Goal của plugin thực thi trong phase | `task` |
| Thứ tự phụ thuộc | `depends` giữa target | Thứ tự phase và goal binding | `dependsOn`, đầu vào/đầu ra, quan hệ task |
| Điểm vào phổ biến | `ant dist` | `mvn package`, `mvn verify` | `gradlew build` |
| Tên công việc | Thường do người viết đặt | Phần lớn theo lifecycle chuẩn | Từ plugin và task tùy chỉnh |
| Tái sử dụng | Target, macrodef, antlib | Plugin, parent POM, module | Plugin, convention plugin, task |
| Mô tả đầu vào/đầu ra | Tùy task, thường thủ công | Theo plugin và quy ước | Task có thể khai báo để hỗ trợ incremental/cache |

Chuyển đổi thành công là **giữ nguyên hành vi cần thiết**, đồng thời tận dụng quy ước và khả năng sẵn có của hệ thống đích.

## 2. Lập bản đồ target Ant trước khi chuyển

Đừng bắt đầu bằng việc đổi cú pháp XML sang Groovy/Kotlin hoặc thêm plugin Maven hàng loạt. Hãy lập bảng cho từng target được gọi trong CLI, IDE và CI:

| Cần ghi lại | Câu hỏi gợi ý |
| --- | --- |
| Tên và cách kích hoạt | Target được gọi trực tiếp, mặc định hay qua `depends`? |
| Tác vụ thật | Biên dịch, copy tài nguyên, kiểm thử, tạo JAR, sinh mã hay triển khai? |
| Phụ thuộc | Target nào cần chạy trước? Có target nào chỉ chuẩn bị thư mục? |
| Đầu vào | `src`, `resources`, file properties, thư viện `lib`, biến môi trường nào? |
| Đầu ra | `build/classes`, `dist/*.jar`, báo cáo test hoặc file tạm nào? |
| Điều kiện | `if`/`unless`, property `-D`, OS, profile, môi trường nào? |
| Tác động ngoài | Có xóa dữ liệu, ghi vào mạng, publish repository hay triển khai ứng dụng không? |
| Người sử dụng | CI/script nào gọi tên target, hoặc công cụ nào phụ thuộc vị trí output? |

Một phương pháp nhanh là bắt đầu từ target mặc định trong `<project default="...">`, theo `depends` để nhìn được chuỗi build chính, rồi xem các target có thể chạy riêng như `clean`, `test`, `deploy`. Đọc thêm `<import>`, `<include>`, `<antcall>`, `<ant>`, `<subant>` và cấu hình CI nếu chúng tham gia quy trình. Một target được khai báo trong file không đồng nghĩa nó sẽ được chạy bởi lệnh Ant hiện tại.

Ví dụ bảng kiểm kê:

| Target Ant | Vai trò thực tế | Đầu ra | Hướng thay thế |
| --- | --- | --- | --- |
| `init` | Tạo thư mục `build/classes` | Thư mục rỗng | Maven/Gradle thường tự tạo thư mục đầu ra |
| `compile` | Biên dịch source Java | `.class` | Maven `compile`; Gradle `compileJava` |
| `copy-resources` | Đưa tài nguyên vào classpath | Tài nguyên đã copy | Maven `process-resources`; Gradle `processResources` |
| `test` | Biên dịch và chạy unit test | Test report | Maven `test`; Gradle `test` |
| `jar` | Đóng gói bytecode và resources | `.jar` | Maven `package`; Gradle `jar` |
| `dist` | Tạo thư mục chứa bộ phát hành | ZIP, JAR, scripts | Maven packaging/assembly plugin; Gradle task phân phối |
| `publish` | Đưa artifact lên kho | Artifact trong repository | Maven `deploy`; Gradle `publish` khi dùng plugin phù hợp |

Bảng trên là **ánh xạ theo ý nghĩa thường gặp**, không phải quy tắc máy móc. Nếu target `test` của Ant thực chất chạy integration test hoặc `dist` triển khai thẳng lên production, cách ánh xạ sẽ khác.

## 3. Bảng ánh xạ thông dụng Ant → Maven → Gradle

| Mục đích | Ant điển hình | Maven | Gradle với plugin phù hợp |
| --- | --- | --- | --- |
| Kiểm tra cấu hình đầu vào | `validate` tự viết | Phase `validate`, goal kiểm tra qua plugin | Task validation tùy chỉnh; cho task cần thiết `dependsOn` |
| Xóa đầu ra | `<delete>` trong `clean` | `mvn clean` | `gradlew clean` |
| Tạo thư mục đầu ra | `<mkdir>` trong `init` | Plugin tạo khi xử lý | Task/plugin tạo khi cần |
| Sinh source Java | `generate-sources` tự viết | Goal gắn vào `generate-sources` | Task generator trước `compileJava` |
| Copy tài nguyên | `<copy>` | `process-resources` | `processResources` |
| Biên dịch main | `<javac>` | `compile` | `compileJava` |
| Biên dịch test | `<javac>` cho test | `test-compile` | `compileTestJava` |
| Unit test | `<junit>` hoặc `<java>` | `test`, thường Surefire | `test` |
| Integration test | Target tùy chỉnh | Goal Failsafe ở `integration-test` và `verify` | Task integration test/source set hoặc plugin |
| Tạo JAR | `<jar>` | `package` với packaging `jar` | `jar`; `assemble` phụ thuộc các artifact |
| Đóng gói ZIP/bộ phân phối | `<zip>`, `<tar>` | Assembly plugin hoặc plugin thích hợp | Task `Zip`/`Tar`, plugin `distribution` |
| Kiểm tra tổng hợp | `verify` tự viết | `verify` | `check`; `build` kết hợp check và assemble |
| Cài artifact vào repo local | `copy` hoặc upload riêng | `install` | `publishToMavenLocal` với `maven-publish` |
| Đẩy artifact lên repo từ xa | Target upload riêng | `deploy` | `publish` với `maven-publish` và repository |
| Triển khai ứng dụng lên server | `<exec>`/`<scp>`/script | Plugin deployment riêng, không đồng nhất với `deploy` Maven | Task/plugin deployment riêng |

**Phân biệt đặc biệt quan trọng:** `mvn deploy` thường có nghĩa **đưa artifact vào remote artifact repository**, không mặc định triển khai ứng dụng đang chạy trên server. Nếu target Ant `deploy` cập nhật website hoặc khởi động lại service, cần thiết kế bước triển khai riêng.

## 4. Ví dụ gốc: build Java bằng Ant

Giả sử repository Java cũ có cấu trúc:

```text
catalog/
├── build.xml
├── src/
│   └── org/example/catalog/Main.java
├── resources/
│   └── catalog.properties
├── test/
│   └── org/example/catalog/MainTest.java
├── lib/
│   └── ...
├── build/
└── dist/
```

Một buildfile tiêu biểu, tạm chỉ mô tả việc đóng gói main code:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="catalog" default="dist" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="resources.dir" location="resources"/>
    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="dist"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="init">
        <mkdir dir="${build.dir}/classes"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${build.dir}/classes"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="copy-resources" depends="init">
        <copy todir="${build.dir}/classes">
            <fileset dir="${resources.dir}" includes="**/*"/>
        </copy>
    </target>

    <target name="jar" depends="compile,copy-resources">
        <jar destfile="${dist.dir}/catalog.jar"
             basedir="${build.dir}/classes"/>
    </target>

    <target name="dist" depends="jar">
        <echo message="Artifact: ${dist.dir}/catalog.jar"/>
    </target>
</project>
```

Lệnh:

```bash
ant -f build.xml clean dist
```

Tạo `dist/catalog.jar` từ các class được biên dịch và file `resources`. Trong build thực tế, phải kiểm kê thêm việc test, dependency, manifest, file filtering, signing và các script tùy chỉnh trước khi chuyển đổi. Không được suy ra rằng chỉ vì có target `jar` là JAR được tạo đã chứa tất cả thư viện cần chạy.

## 5. Phương án Maven: chuyển sang quy ước và lifecycle

### 5.1. Sắp xếp thư mục theo chuẩn Maven

Maven dùng quy ước thư mục:

```text
catalog/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── org/example/catalog/Main.java
│   │   └── resources/
│   │       └── catalog.properties
│   └── test/
│       ├── java/
│       │   └── org/example/catalog/MainTest.java
│       └── resources/
└── target/
```

Nếu chưa thể di chuyển source, Maven vẫn có thể cấu hình đường dẫn nguồn riêng, nhưng dùng đúng layout mặc định thường giúp giảm cấu hình và dễ áp dụng plugin. `target/` là thư mục đầu ra mặc định của Maven; không nên nhầm với `<target>` trong Ant.

### 5.2. POM đơn giản cho JAR Java

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>catalog</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
```

Với packaging `jar` và plugin mặc định tương ứng, các giai đoạn thường bao gồm:

- `process-resources`: đưa `src/main/resources` vào thư mục class đầu ra.
- `compile`: biên dịch `src/main/java`.
- `test-compile` và `test`: biên dịch/chạy kiểm thử với plugin test phù hợp.
- `package`: tạo JAR ở `target/catalog-1.0.0.jar`.

Các lệnh:

```bash
mvn clean package
mvn verify
mvn install
```

`mvn clean package` tương đương về **mục đích build sạch và đóng gói** với nhiều chuỗi `ant clean dist`, nhưng vị trí file, tên artifact, cách chạy test và việc copy tài nguyên có thể khác. `mvn verify` chạy tới phase `verify`, thường dùng khi cần kiểm tra bổ sung; `mvn install` còn cài artifact vào Maven repository cục bộ để dự án khác sử dụng.

Nếu dự án cần unit test JUnit, phải khai báo dependency test và cấu hình plugin/version phù hợp với phiên bản JUnit đang dùng. Không nên cho rằng chỉ thêm một file `*Test.java` là mọi loại framework test đều được Maven tự nhận mà không cấu hình.

### 5.3. Thay thế từng target Ant bằng phase hoặc plugin goal

Trong ví dụ gốc:

```text
Ant                          Maven
clean ---------------------> clean lifecycle
init ----------------------> plugin tự chuẩn bị target/classes
copy-resources ------------> process-resources
compile -------------------> compile
jar -----------------------> package (jar packaging)
dist ----------------------> package hoặc plugin assembly tùy đầu ra
```

Maven **không cần một target `init` riêng** chỉ để tạo thư mục class: compiler/resource plugin tạo những thư mục cần thiết. Cũng không cần tự viết task `jar` nếu JAR chuẩn của Maven đã đáp ứng.

Nếu `dist` tạo thêm file ZIP gồm JAR, scripts, README và cấu hình, phase `package` với `maven-assembly-plugin` (hoặc plugin đóng gói thích hợp) thường gần chức năng đó hơn chỉ dùng packaging `jar`. Cần mô tả nội dung distribution, thay vì đổi tên `dist` thành `package` và bỏ sót các thành phần.

### 5.4. Gắn công việc tùy biến vào phase phù hợp

Ví dụ Ant có `generate-sources` trước `compile`:

```xml
<target name="generate-sources">
    <!-- gọi generator để tạo source Java -->
</target>
<target name="compile" depends="generate-sources">
    <!-- javac -->
</target>
```

Trong Maven, chọn plugin generator phù hợp và gắn goal của nó vào phase `generate-sources`, bảo đảm thư mục output được đăng ký làm source root nếu plugin không tự thực hiện. Không nên dùng `exec-maven-plugin` cho mọi việc chỉ vì nó có thể gọi lệnh shell; ưu tiên plugin chuyên dụng với cách khai báo input/output rõ.

Khung ý tưởng:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.example</groupId>
            <artifactId>example-generator-maven-plugin</artifactId>
            <version>PLUGIN_VERSION</version>
            <executions>
                <execution>
                    <id>generate-catalog-sources</id>
                    <phase>generate-sources</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **mẫu cấu trúc cấu hình**, không phải plugin có thật để copy chạy ngay: thay tọa độ plugin, goal và version bằng công cụ tạo mã thực tế. Khi mục đích chỉ là biên dịch Java, POM tối giản ở trên đã đủ về cấu trúc lifecycle.

### 5.5. Maven test và integration test

Trong Ant, target `test` có thể chạy unit test hoặc integration test. Trong Maven, thường phân biệt:

- `test`: unit test theo plugin Surefire và quy ước nhận diện test.
- `integration-test` + `verify`: integration test thường dùng Failsafe, với bước xác định kết quả ở `verify`.

Phải xem nội dung và tên test thực tế. Nếu target Ant `test` còn khởi động database, container hoặc HTTP service thì việc thay bằng `mvn test` đơn thuần có thể thiếu các bước chuẩn bị/cleanup. Ngược lại, đưa integration test vào unit-test phase có thể làm build chậm và khó kiểm soát môi trường.

## 6. Phương án Gradle: dùng plugin và task graph

### 6.1. Tổ chức source

Plugin `java` của Gradle mặc định sử dụng layout quen thuộc:

```text
catalog/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── build/
```

Ví dụ `settings.gradle.kts`:

```kotlin
rootProject.name = "catalog"
```

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
}

group = "org.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}
```

Khi áp dụng plugin Java, Gradle tạo các task như `compileJava`, `processResources`, `classes`, `compileTestJava`, `test`, `jar`, `assemble`, `check`, `build` và `clean`. Với cấu trúc chuẩn, source main và resources được nhận từ `src/main/java` và `src/main/resources`.

Chạy:

```bash
./gradlew clean build
./gradlew jar
./gradlew tasks
```

Trên Windows, thường dùng `gradlew.bat` (nếu project có Gradle Wrapper). Ví dụ dùng `./gradlew` giả định wrapper đã được tạo và đưa vào repository. Wrapper giúp đồng bộ phiên bản Gradle giữa các môi trường.

Task `jar` thường tạo `build/libs/catalog-1.0.0.jar` theo metadata đã khai báo. Task `assemble` gom các artifact có thể lắp ráp; task `check` là điểm tập hợp kiểm tra; `build` phụ thuộc vào cả `assemble` và `check`. Tính chính xác của những kiểm tra được nối vào `check` phụ thuộc vào plugin và cấu hình của dự án.

### 6.2. Thay target `dist` bằng task tùy chỉnh

Nếu `dist` của Ant chỉ lấy JAR vừa xây và đặt trong thư mục phát hành riêng, một task Gradle kiểu `Copy` có thể biểu diễn trực tiếp:

```kotlin
tasks.register<Copy>("stageDistribution") {
    dependsOn(tasks.named("jar"))

    from(tasks.named("jar"))
    into(layout.buildDirectory.dir("distribution"))
}
```

Task này dùng output của `jar` làm đầu vào, sau đó copy vào `build/distribution`:

```bash
./gradlew clean stageDistribution
```

Việc `from(tasks.named("jar"))` thể hiện quan hệ với output của task tạo JAR. Khi một task tiêu thụ output task khác, nên liên kết bằng provider hoặc task reference thay vì ghép chuỗi path cứng và hy vọng file đã có từ lần build trước.

Với distribution chứa nhiều file hoặc cần ZIP/TAR, dùng task kiểu `Zip`/`Tar` hoặc plugin `distribution`. Ví dụ tạo ZIP từ JAR và thư mục scripts:

```kotlin
tasks.register<Zip>("bundleDistribution") {
    dependsOn(tasks.named("jar"))

    archiveBaseName.set("catalog-distribution")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))

    from(tasks.named("jar")) {
        into("lib")
    }
    from("scripts") {
        into("bin")
    }
}
```

Ví dụ giả định repository có thư mục `scripts` phù hợp. Nếu scripts yêu cầu quyền thực thi, line ending hoặc bộ file được lọc, cần cấu hình thêm theo yêu cầu môi trường. Task không tự biến một thư viện JAR thành bản phân phối ứng dụng có thể chạy nếu thiếu manifest/main class hoặc dependency runtime.

### 6.3. Viết task tùy biến và nối đúng dependency

Giả sử Ant có target `checkMetadata` phải hoàn thành trước khi đóng gói:

```xml
<target name="jar" depends="compile,checkMetadata">
    <!-- create jar -->
</target>
```

Trong Gradle, có thể đăng ký task riêng rồi nối quan hệ:

```kotlin
val validateMetadata by tasks.registering {
    doLast {
        val metadataFile = file("metadata/release.properties")
        require(metadataFile.isFile) {
            "Missing metadata/release.properties"
        }
    }
}

tasks.named("jar") {
    dependsOn(validateMetadata)
}
```

Đây là ví dụ kiểm tra file đơn giản. Với task Gradle tùy chỉnh thực sự tạo file hoặc kiểm tra dữ liệu, nên khai báo đầu vào/đầu ra phù hợp để Gradle hiểu lúc nào cần chạy lại, khi nào có thể bỏ qua hoặc cache. Dùng `dependsOn` chỉ để ép thứ tự khi hai công việc có dependency thật; nếu chỉ cần thứ tự mà không bắt buộc chạy, cần xem xét `mustRunAfter`/`shouldRunAfter` theo đúng ngữ nghĩa.

### 6.4. Test trong Gradle

Plugin Java cung cấp task `test`, nhưng framework test cụ thể phải được cấu hình. Với JUnit Jupiter, một ví dụ:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

Version ở ví dụ là một giá trị minh họa, cần được quản lý thống nhất theo dependency policy của project. Chạy `./gradlew test` để thực thi unit test; `./gradlew check` cho các bước kiểm tra được nối vào lifecycle verification của plugin. Nếu Ant đang có integration test riêng, tạo source set/task hoặc sử dụng plugin phù hợp thay vì dồn mọi test vào task `test` mặc định.

## 7. Những điểm không thể ánh xạ theo tên một-một

### `ant all` hoặc `ant dist`

Trong nhiều project, target `all`/`dist` là **target tổng hợp**. Với Maven, cần chọn phase phù hợp với kết quả cuối (thường `package` hoặc `verify`) và thêm plugin cho đầu ra đặc thù. Với Gradle, dùng `build`, `assemble` hoặc task tổng hợp `dependsOn` các task cần thiết.

Không nhất thiết tạo một task Gradle `dist` chỉ để giữ nguyên tên nếu người dùng/CI đã sẵn sàng dùng `assemble` hoặc `build`. Tuy nhiên, nếu có script bên ngoài đang gọi `dist`, một alias có chủ đích trong giai đoạn chuyển đổi có thể giúp giảm thay đổi đồng loạt.

### `ant clean`

Ant target `clean` có thể xóa cả `build`, `dist`, thư mục cache, hoặc tệp generated source. Maven `clean` mặc định tập trung vào thư mục build output theo cấu hình project; Gradle `clean` mặc định xóa build directory. Trước khi coi tương đương hoàn toàn, cần kiểm kê **từng đường dẫn Ant đang xóa** và cân nhắc liệu các đường dẫn đó nên được đặt dưới thư mục output chuẩn hay cần bước dọn riêng.

Không nên chuyển nguyên xi một lệnh `delete` quét đường dẫn tùy ý vào build đích. Đường dẫn xóa cần được kiểm soát và giới hạn trong vùng output được phép.

### `ant init`

`init` thường chỉ tạo thư mục hoặc đặt property. Maven và Gradle có thể tự tạo thư mục output; giữ thêm một bước `init` rỗng là không cần thiết. Nhưng nếu `init` tải tool, sinh file cấu hình hoặc tạo dữ liệu thử nghiệm, những công việc đó phải được gán sang plugin goal/task thích hợp.

### `ant deploy`

Phải xác định đích của `deploy` là **artifact repository** hay **môi trường chạy**:

| Ant `deploy` làm gì? | Maven | Gradle |
| --- | --- | --- |
| Đưa JAR/POM lên repository cho dự án khác tải | `mvn deploy` với `distributionManagement` và credential | `publish` qua `maven-publish`/repository |
| Copy WAR lên application server | Plugin/application deployment riêng | Task/plugin deployment riêng |
| Chạy SSH, restart container hoặc service | Công cụ deployment được quản lý riêng | Task/plugin deployment hoặc pipeline riêng |
| Tạo bản release có tag và changelog | Plugin release/quy trình CI | Plugin release/quy trình CI |

Tên giống nhau không bảo đảm cùng hành vi. Với môi trường production, việc chuyển tool build không nên đồng thời làm mất bước approval, kiểm tra môi trường và giới hạn credential.

## 8. Phân biệt quan hệ `depends` của Ant với lifecycle Maven và Gradle

Giả sử Ant định nghĩa:

```xml
<target name="prepare"/>
<target name="generate" depends="prepare"/>
<target name="compile" depends="generate"/>
<target name="test" depends="compile"/>
<target name="package" depends="test"/>
```

Đồ thị thực thi theo thứ tự:

```text
prepare → generate → compile → test → package
```

Trong Maven, công việc chuẩn được gắn vào các phase thích hợp; gọi `mvn package` sẽ chạy từ đầu lifecycle cho đến `package`. Một plugin generate được bind vào `generate-sources` sẽ chạy trước compiler nếu thiết lập đúng. Người dùng không cần tự liệt kê `depends` giữa các phase.

Trong Gradle, những mối quan hệ tương ứng là dependency giữa task:

```kotlin
val generateSource by tasks.registering {
    // Action tạo source sẽ được triển khai ở đây.
}

tasks.named("compileJava") {
    dependsOn(generateSource)
}
```

Đây chỉ là **mẫu nối thứ tự**. Một task generator thực tế phải chỉ định input/output và đăng ký thư mục generated source làm source directory cho Java compilation. Nếu chỉ thêm `dependsOn` nhưng compiler không biết nơi chứa source sinh ra, output mới có thể vẫn không được biên dịch.

Gradle không đòi hỏi chạy task theo thứ tự khai báo trong file. Dùng `dependsOn` khi một task **bắt buộc phải chạy** trước task khác. `mustRunAfter` điều khiển thứ tự **khi cả hai task đều có mặt trong đồ thị**, nhưng không tự khiến task trước được thực thi.

## 9. Chuyển cấu hình thư viện và classpath

Ant thường quản lý dependency thủ công:

```xml
<path id="compile.classpath">
    <fileset dir="lib" includes="**/*.jar"/>
</path>

<javac srcdir="src"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="compile.classpath"/>
</javac>
```

Maven và Gradle ưu tiên mô tả dependency bằng tọa độ artifact và repository:

Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.16</version>
    </dependency>
</dependencies>
```

Gradle Kotlin DSL:

```kotlin
repositories {
    mavenCentral()
}
dependencies {
    implementation("org.slf4j:slf4j-api:2.0.16")
}
```

Các version ở trên chỉ minh họa cú pháp; project cần chọn và quản lý các phiên bản phù hợp. Trong quá trình chuyển đổi, phải kiểm kê:

1. **Thư viện compile-time, runtime và test**: một thư mục `lib` có thể đang trộn tất cả.
2. **Dependency transitively cần thiết**: Maven/Gradle thường giải quyết dependency transitively, khác với việc chọn mọi JAR bằng FileSet.
3. **JAR nội bộ**: có sẵn trong repository hay cần publish trước? Có thể cần private artifact repository.
4. **Xung đột version**: build Ant trước đây có thể phụ thuộc tình cờ vào thứ tự JAR trong classpath.
5. **Jar đóng gói ứng dụng**: JAR chuẩn không mặc nhiên là “fat JAR”; nếu ứng dụng cần bundle dependency runtime, phải thiết kế lại packaging.

Tránh chuyển nguyên trạng `lib/**/*` thành một dependency fileTree rộng mà không biết nội dung. Điều đó dễ che giấu dependency thừa hoặc xung đột version; mô hình tọa độ rõ ràng tạo tiền đề cho dependency management về lâu dài.

## 10. Đầu vào, đầu ra, cấu hình và điều kiện

### Property của Ant

Ant thường dùng:

```bash
ant -Denv=staging -Drelease.version=1.2.3 dist
```

Các property có thể ảnh hưởng đến target qua `if`/`unless` hoặc nội suy `${...}`. Khi chuyển đổi, đừng giữ nguyên tên property và mặc định chúng có cùng phạm vi hoặc ưu tiên trong Maven/Gradle.

### Maven

Maven có property trong POM, profile và tham số dòng lệnh `-D`:

```bash
mvn -Prelease -Drelease.version=1.2.3 verify
```

`-Prelease` kích hoạt profile tên `release` nếu project có khai báo; `-Drelease.version` cung cấp property mà plugin/POM có thể sử dụng. Profile không tự tương đương với target Ant: nó có thể thay đổi dependency, plugin execution, repository hoặc cấu hình khác.

### Gradle

Gradle thường dùng project property qua `-P`, và task/script truy cập thông qua Provider API:

```bash
./gradlew build -PbuildMode=staging
```

Ví dụ Kotlin DSL:

```kotlin
val buildMode = providers.gradleProperty("buildMode")
    .orElse("development")

tasks.register("showBuildMode") {
    doLast {
        println("Build mode: ${buildMode.get()}")
    }
}
```

`-P` là project property; `-D` của Gradle thường đặt JVM system property, không nên coi hai cách truyền này giống hệt nhau. Khi dùng task Gradle tùy chỉnh, ưu tiên Provider API và khai báo input/output thay vì lấy biến môi trường một cách không kiểm soát tại configuration time.

### Điều kiện target và kiểm soát thao tác

Nếu Ant có:

```xml
<target name="publish" if="release.enabled">
    <!-- upload -->
</target>
```

`if` của target Ant kiểm tra **sự hiện diện** của property, không có nghĩa yêu cầu giá trị `true`. Maven profile và Gradle `onlyIf` có ngữ nghĩa riêng. Phải thiết kế lại điều kiện với yêu cầu thực tế: cho phép phát hành khi nào, tới đâu, theo quyền nào, và bước nào cần chặn trước khi ghi/xóa.

Không nên đưa một thao tác phát hành vào `package` hoặc `build` mặc định nếu Ant trước đây chỉ phát hành khi gọi target riêng. Build tự động trên PR không nên bất ngờ publish artifact lên repository production.

## 11. Chuyển công việc tùy chỉnh: chọn giải pháp theo mức độ

Trong build cũ, có thể gặp `<exec>` gọi shell, `<replace>` chỉnh file, `<javac>` custom, `<zip>` đặc biệt hoặc task Ant trong antlib. Với mỗi trường hợp, cân nhắc:

| Loại công việc | Maven | Gradle |
| --- | --- | --- |
| Java compile, resource, test, jar thông thường | Dùng lifecycle/plugin chuẩn | Dùng plugin Java và task chuẩn |
| Sinh mã từ schema | Plugin generator gắn phase `generate-sources` | Task generator + source directory + dependency |
| Đóng gói tài nguyên đặc thù | Assembly/plugin packaging | Task `Copy`, `Zip`, `Tar` hoặc plugin distribution |
| Kiểm tra metadata | Plugin validator/enforcer hoặc goal phù hợp | Task validation, nối vào `check`/task liên quan |
| Phát hành repository | Deploy plugin và cấu hình nơi nhận | `maven-publish` + repository |
| Legacy Ant task khó thay ngay | `maven-antrun-plugin` tạm thời | Có thể gọi Ant task qua `ant` trong Gradle |

Giữ một phần Ant trong thời gian chuyển đổi có thể là bước đệm hợp lý nếu chức năng quá đặc thù. Tuy nhiên, nên biết chính xác phần nào còn do Ant quản lý, phần nào đã được lifecycle/task mới điều phối, và tránh cùng lúc có **hai nguồn sự thật** cho cùng bước compile hoặc đóng gói.

Chẳng hạn, sau khi Maven compiler đã biên dịch source, không nên lại gọi nguyên target Ant `compile` từ Antrun mà không có lý do rõ; việc biên dịch hai lần có thể dùng classpath hoặc thư mục output khác nhau.

## 12. Dự án nhiều module: tổ chức lại dependency thay vì chạy `subant`

Ant có thể dùng `<subant>` hoặc `<ant antfile="...">` để build tuần tự các module. Khi chuyển, nên xác định dependency giữa module:

```text
common
   ↑
service
   ↑
web
```

Maven hỗ trợ reactor với parent/aggregator POM chứa danh sách `modules` và dependency giữa artifact module. Gradle hỗ trợ multi-project build với `settings.gradle.kts` chứa `include("common", "service", "web")` và project dependency như `implementation(project(":common"))`.

Nếu mô hình cũ có target chạy `common` trước rồi `service` nhưng Gradle/Maven không khai báo dependency giữa hai module, build có thể chỉ thành công vì artifact cũ còn trên đĩa. Vì vậy cần mô hình hóa dependency bằng cơ chế module chính thức của công cụ mới.

Với CI, thay vì chạy các build con một cách thủ công, có thể sử dụng reactor/task graph để chỉ build module cần thiết cùng dependency của chúng, tùy mục tiêu. Đồng thời kiểm tra cách chia sẻ version, dependency management, plugin configuration và publication cho nhiều module.

## 13. Giữ tương đương hành vi khi chuyển đổi

Khi thay `ant clean dist` bằng `mvn clean package` hoặc `./gradlew clean build`, hai câu lệnh **không bảo đảm đầu ra giống hệt nhau**. Các khác biệt dễ gặp:

- **Tên và vị trí artifact**: Ant có thể tạo `dist/app.jar`; Maven thường tạo `target/artifactId-version.jar`; Gradle thường tạo `build/libs/name-version.jar`.
- **Manifest**: Ant `jar` có thể khai báo `Main-Class` hoặc các thuộc tính khác; Maven/Gradle cần cấu hình tương ứng nếu ứng dụng chạy trực tiếp.
- **Resource filtering**: Ant `copy` với filterset có thể thay token; Maven resources plugin hoặc Gradle `processResources` cần quy tắc thay token riêng.
- **Classpath và dependency**: JAR bên ngoài, test library, plugin hoặc JAR nội bộ cần được khai báo trong mô hình dependency mới.
- **Bộ test được chạy**: mẫu tên test, framework, integration test và môi trường chuẩn bị có thể khác.
- **File được đưa vào package**: include/exclude, file rác, permission và cấu trúc archive phải được xem xét.
- **Thời gian tạo và metadata**: ZIP/JAR có thể khác byte vì timestamp, thứ tự entry hoặc metadata dù nội dung chức năng tương đương.
- **Hành vi xóa/ghi/publish**: không được vô tình làm bước build thường thành bước xóa ngoài phạm vi hay phát hành ra hệ thống thật.

Để giảm phụ thuộc vào vị trí file cũ, tốt nhất cập nhật các script/CI tiêu thụ artifact sang đường dẫn mới. Nếu cần giữ hợp đồng với hệ thống khác, thêm một task stage/copy hoặc cấu hình tên artifact tại công cụ mới, và ghi rõ vì sao cần tương thích.

## 14. Quy trình chuyển đổi theo từng giai đoạn

### Giai đoạn A: xác định hành vi Ant hiện hữu

1. Lập danh sách target và phụ thuộc từ `build.xml` cùng các file import.
2. Phân loại target thành compile, resource, test, package, distribution, publish và công việc tùy chỉnh.
3. Liệt kê đường dẫn source, resources, test, thư viện, biến cấu hình và đầu ra.
4. Ghi lại lệnh mà developer và CI đang chạy, nhất là target mặc định và target có tác động ra ngoài.

### Giai đoạn B: chọn ánh xạ trong tool đích

Với Maven, bắt đầu từ layout chuẩn và phase `compile`/`test`/`package`; chỉ thêm plugin cho chức năng chưa có. Với Gradle, áp dụng plugin `java` và những task chuẩn, sau đó tạo task tùy chỉnh khi thật sự cần.

Đặc biệt tránh **tạo toàn bộ target Ant thành task Gradle mới** nếu chúng đã được plugin tạo ra. Chẳng hạn không cần viết lại `compileJava` bằng `Exec` gọi `javac` khi Java plugin đã xử lý compiler, classpath và incremental input.

### Giai đoạn C: kết nối tính năng còn thiếu

Chuyển các bước sinh mã, code quality, đóng gói distribution, integration test và publishing tới plugin/task đúng mục đích. Việc tạo classpath, nguồn generated source và artifact cần theo chuẩn tool mới để tránh phụ thuộc vào lần chạy trước.

### Giai đoạn D: cập nhật điểm vào và CI

| Trước với Ant | Sau với Maven (nếu phù hợp) | Sau với Gradle (nếu phù hợp) |
| --- | --- | --- |
| `ant clean compile` | `mvn clean compile` | `./gradlew clean compileJava` |
| `ant test` | `mvn test` | `./gradlew test` |
| `ant clean dist` | `mvn clean package` hoặc mục tiêu assembly | `./gradlew clean build` hoặc task distribution |
| `ant verify` | `mvn verify` | `./gradlew check` hoặc `build` |
| `ant publish` | `mvn deploy` nếu là artifact repository | `./gradlew publish` nếu đã cấu hình plugin |

Đổi command của CI chỉ là một phần: phải cập nhật artifact path, test report path, cache directory, dependency credentials, Java/Gradle/Maven version và điều kiện publish. Một hệ thống CI không nên chạy đồng thời cả Ant lẫn Maven/Gradle cho cùng nhiệm vụ chỉ vì chưa xóa lệnh cũ.

### Giai đoạn E: đối chiếu đầu ra và loại bỏ phần Ant không còn dùng

Khi công cụ mới đã biểu diễn được chức năng của các target Ant, rà soát các lời gọi `ant` còn lại, nhiệm vụ bị chạy hai lần và dependency chỉ tồn tại ở máy của người viết. Có thể giữ Ant cho những công việc chưa chuyển, nhưng cần xác định ranh giới rõ và không để hai công cụ cùng quản lý một đầu ra mà không có thỏa thuận.

## 15. Tình huống minh họa: target `dist` tạo ZIP chứa ứng dụng

Giả sử trong Ant:

```xml
<target name="dist" depends="jar">
    <zip destfile="dist/catalog.zip">
        <fileset dir="dist" includes="catalog.jar"/>
        <fileset dir="scripts" includes="**/*"/>
    </zip>
</target>
```

Nếu chuyển đơn giản sang `mvn package` và chỉ để Maven tạo JAR thì **chưa đầy đủ**: mất ZIP và scripts. Ánh xạ đúng theo đầu ra:

1. Để Maven `package` hoặc Gradle `jar` tạo JAR.
2. Cấu hình plugin assembly trong Maven hoặc task `Zip` trong Gradle để lấy JAR cùng scripts.
3. Giữ cấu trúc thư mục, tên file, quyền cần thiết của scripts và nội dung archive theo yêu cầu.
4. Cập nhật CI để lấy `catalog.zip` từ thư mục distribution mới hoặc cấu hình tên/đường dẫn phù hợp.

Nếu ZIP là artifact phát hành, chỉ sau khi bundle đúng và các kiểm tra bắt buộc thành công mới cho pipeline publish nó. Không nên đồng nhất thao tác **tạo distribution** với **triển khai ra production**.

## 16. Lựa chọn Maven hay Gradle khi đang có Ant

Không có một ánh xạ tuyệt đối cho mọi dự án. Việc lựa chọn phụ thuộc vào tính chất build:

| Tiêu chí | Maven thường thuận lợi khi | Gradle thường thuận lợi khi |
| --- | --- | --- |
| Cấu trúc Java chuẩn | Cần quy ước và lifecycle ổn định, ít logic riêng | Cũng hỗ trợ tốt bằng Java plugin |
| Tùy chỉnh workflow | Có plugin phù hợp để bind vào phase | Cần nhiều task tùy chỉnh và task graph rõ |
| Multi-module | Dùng reactor và POM theo quy ước | Muốn dependency project và logic task linh hoạt |
| Quản lý dependency | Muốn POM, dependency management phổ biến | Muốn cấu hình dependency và variant qua plugin |
| Tái sử dụng logic build | Parent POM, plugin/shared configuration | Convention plugin và plugin tùy chỉnh |
| Ant đang chứa nhiều tác vụ đặc thù | Có thể cần plugin chuyển tiếp như Antrun | Có thể dùng Ant integration trong thời gian chuyển |

Quyết định nên dựa trên số lượng target tùy biến, loại output, plugin hệ sinh thái, công cụ CI và kỹ năng đội dự án. **Maven không phải cách “đổi tên target” thành phase, và Gradle không phải cách “chép nguyên build.xml” thành nhiều task tùy chỉnh.** Mỗi công cụ có cơ chế chuẩn để diễn đạt cùng một mục đích.

## 17. Những lỗi ánh xạ thường gặp

**Lỗi 1: `mvn deploy` được dùng thay target triển khai ứng dụng.** Maven `deploy` phổ biến là upload artifact vào remote repository. Nếu Ant cũ restart server, cần pipeline deployment đúng chức năng.

**Lỗi 2: Chỉ ánh xạ target theo tên.** Một target Ant `package` có thể chỉ copy file, còn `test` có thể làm integration test. Luôn đọc task bên trong và xác định đầu ra.

**Lỗi 3: Mất bước sinh source.** Maven/Gradle compile được source có sẵn nhưng không sinh code mới vì generator chưa được nối vào phase/task compilation.

**Lỗi 4: Chạy unit test nhưng bỏ integration test.** Ant có thể chạy cả hai loại test trong target `verify`, còn Maven/Gradle mặc định chỉ nhận những test và plugin đã cấu hình.

**Lỗi 5: Hard-code tên JAR và thư mục cũ.** Build mới có artifact tên gắn version; một script CI vẫn chờ `dist/app.jar` sẽ báo lỗi dù compile/package thành công.

**Lỗi 6: Mang theo mọi thao tác shell của Ant.** Maven và Gradle có task/plugin tương ứng, giúp hạn chế phụ thuộc vào `sh`, `cmd`, `cp` hoặc `rm` trên hệ điều hành cụ thể.

**Lỗi 7: Dùng `dependsOn` hoặc thứ tự phase để thay kiểm tra đầu vào.** Quan hệ thứ tự không chứng minh version hợp lệ, artifact đã kiểm thử hay quyền phát hành đủ. Các điều kiện an toàn vẫn cần được mô tả riêng.

**Lỗi 8: Hiểu nhầm `mvn install` là cài ứng dụng.** Maven `install` đưa artifact vào local Maven repository, không cài service vào hệ điều hành.

## 18. Ghi nhớ khi ánh xạ Ant sang Maven hoặc Gradle

Trước tiên, **đọc ý nghĩa và đầu ra của từng target Ant**. Sau đó, ánh xạ:

- Công việc Java chuẩn sang lifecycle phase/goal của Maven hoặc task có sẵn của Gradle.
- Công việc tùy biến sang plugin/task phù hợp, với dependency và đầu vào/đầu ra rõ ràng.
- Các target tổng hợp như `dist`/`all` sang điểm vào tạo đủ artifact cần thiết, không tự giả định `package` hay `build` đã tương đương.
- Công việc publish/deploy sang cơ chế có đúng ý nghĩa đích nhận và bảo vệ quyền phát hành.

**Đích của quá trình chuyển đổi là một bản build có hành vi rõ ràng, dễ tái hiện và dùng đúng cơ chế của công cụ mới**, chứ không phải giữ nguyên số lượng target hay tên gọi. Nếu kết quả biên dịch, tài nguyên, test, archive và phát hành đáp ứng yêu cầu cũ với cấu hình mới dễ hiểu hơn, việc ánh xạ đã đi đúng hướng.
