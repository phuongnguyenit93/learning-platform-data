# Import dự án Maven vào IDE từ POM thay vì tự ghép classpath

**Một dự án Java sử dụng Maven phải được mở trong IDE như một *Maven project* từ `pom.xml`, không phải như một Java project rỗng rồi thêm từng file `.jar` vào `Build Path` hoặc `Project Structure`.** `pom.xml` là nguồn khai báo của dependencies, versions, source roots, resources, test classpath, plugins, compiler release, modules và profiles. IDE có nhiệm vụ đọc Maven model và đồng bộ mô hình này thành modules, libraries, Java SDK, source/test roots, build/run configurations; Maven CLI là mốc đối chiếu độc lập khi IDE và build cho kết quả khác nhau.

Bài thuộc nhóm **IDE và CI**. Nội dung hướng dẫn quy trình mở đúng dự án từ POM trong **IntelliJ IDEA, Eclipse m2e và Visual Studio Code (Java extensions)**; phân biệt classpath `compile`/`test`/`runtime`, xử lý Maven Wrapper, JDK, repositories/settings, multi-module và active profiles; thực hành với một project **Java 17 + Maven 3.9.x** có dependency Apache Commons Lang, JUnit Jupiter, resource file và plugin chạy Java dùng đúng runtime classpath. Cuối cùng ta chẩn đoán lỗi “IDE đỏ nhưng `mvn verify` xanh” và lỗi “IDE chạy được nhưng CI `mvn verify` đỏ”, rồi đặt checklist đồng bộ IDE–CLI–CI.

**Nguyên tắc xuyên suốt:** sửa **`pom.xml` trước**, đồng bộ/reload dự án sau; **không sửa riêng classpath trong IDE để chữa tạm**. IntelliJ IDEA documentation còn nêu rõ dependencies thêm thủ công trong project/module settings có thể bị xóa khi đồng bộ Maven project. Một build chỉ chạy được trên máy developer nhờ “External Libraries” thêm bằng tay chưa phải cấu hình đáng tin cho đồng đội hoặc CI.

## 1. Vì sao không tự ghép classpath?

Ở Java, `classpath` là tập thư mục/classes/JAR mà compiler hoặc JVM có thể tìm thấy. Khi xây một project đơn giản, bạn có thể chạy:

```bash
javac -cp lib/dependency.jar -d out src/main/java/example/Main.java
java -cp out:lib/dependency.jar example.Main
```

Tuy nhiên command trên dùng dấu `:` làm classpath separator kiểu Unix; Windows thường dùng `;`. Khi dependencies và modules tăng, có ít nhất sáu rủi ro:

1. **Không có phiên bản được khai báo rõ.** File `lib/commons-lang3.jar` không thể hiện Maven GAV và version một cách máy đọc được.
2. **Bỏ sót transitive dependencies.** Library A có thể cần B/C; tự thêm A chưa chắc đủ.
3. **Nhầm classpath theo mục đích.** JUnit, Mockito là test-scope dependencies, không nên đi vào runtime artifact.
4. **IDE khác CI.** Những JAR chỉ được cấu hình trong IntelliJ/Eclipse/VS Code workspace không tự tồn tại trên CI.
5. **Không thống nhất compiler/toolchain.** IDE dùng JDK khác `maven-compiler-plugin` và sinh bytecode/annotation processing khác.
6. **Khó tái lập và review.** Một thay đổi Build Path trong `.idea`/`.classpath` khó phản ánh đúng nhu cầu thực của build.

Maven giải quyết bằng **khai báo dependencies và build rules trong POM**, áp dụng dependency resolution/mediation và tạo classpath cho những plugins/test runners tương ứng. IDE có Maven integration để phản ánh mô hình đó; không nên trở thành “nguồn sự thật thứ hai”.

### 1.1. Dòng chảy đúng

```text
git clone / checkout
        |
        v
pom.xml + parent POM + dependencyManagement/BOM
        |
        + settings.xml / repositories / mirrors / profiles
        |
        + Maven Wrapper + JDK/toolchains
        |
        v
Maven effective model & dependency resolution
        |
        +--------------------+---------------------+
        |                    |                     |
        v                    v                     v
  Maven CLI build     IntelliJ import         Eclipse m2e
        |                    |                     |
        |                    +--------+------------+
        |                             |
        |                    VS Code Java import
        |                             |
        v                             v
  repeatable CI       editor model: modules, roots,
  compile + tests     dependencies, Java SDK, tests
```

IDE có thể sử dụng builder/test runner riêng để tăng tốc, nhưng **Maven model phải là cơ sở**. Khi cần chắc chắn artifact kết quả tương đương CI, chạy `mvn clean verify` hoặc cấu hình IDE delegate build/test cho Maven.

## 2. Maven thực sự đọc những gì khi import?

Những điểm quan trọng trong một dự án Maven:

- **`pom.xml`:** groupId, artifactId, version, packaging, dependencies, plugin executions, properties, build configuration.
- **Parent POM:** cấu hình kế thừa; có thể ở `../pom.xml`, trong local repository hoặc remote repository.
- **`dependencyManagement` hoặc BOM:** quản lý versions/scopes/exclusions cho dependencies sẽ được khai ở nơi dùng; **không tự thêm dependency vào classpath** khi chỉ nằm trong dependencyManagement.
- **`<dependencies>`:** khai dependencies thực sự tham gia resolution và classpaths theo scope.
- **`<modules>`:** danh sách reactor modules ở aggregator POM; khác với `<parent>` quyết định inheritance.
- **`settings.xml`:** mirrors, proxy, credentials, active settings profiles, local repository; không commit secrets.
- **`.mvn`/Maven Wrapper:** hướng dẫn Maven version/build opts; wrapper chỉ pin Maven distribution, không tự pin Java toolchain nếu không có giải pháp bổ sung.
- **JDK và toolchains:** Maven runtime JDK và Java compiler target; IDE project SDK/JDK for importer/runner có thể khác nhau.
- **Active Maven profiles và `-D` properties:** đổi dependencies, modules, source roots hoặc plugins; profile khác nhau có thể khiến IDE và CI lệch model.
- **Maven plugin/extension output:** generated sources, processed resources, annotation processors, compiler/test configuration.

Maven tạo **effective POM** từ các nguồn đó. Một IDE nhận diện Maven project cần hiểu effective model, không chỉ parse vài thẻ `<dependency>` thô trong một POM duy nhất.

### 2.1. POM chứ không phải file .classpath/.iml

Trong Eclipse, classpath được m2e quản lý trong project metadata/`.classpath`; trong IntelliJ, modules/libraries có representation trong IDE workspace; ở VS Code, Java language server sử dụng imported model. Các metadata này có thể được tái tạo hoặc đồng bộ. Không nên sửa trực tiếp generated metadata để “thắng” `pom.xml` vì lần reload tiếp theo có thể làm mất thay đổi.

Bảng so sánh:

| Quyết định | Đúng: khai ở Maven/POM hoặc toolchain | Sai: chỉ chỉnh trong IDE |
| --- | --- | --- |
| Thêm Apache Commons Lang | `<dependency>org.apache.commons:commons-lang3</dependency>` | Add JAR file trong Project Structure |
| JUnit | JUnit dependency `scope=test` | Đưa JUnit JAR vào global library không khai POM |
| Java 17 | `maven.compiler.release=17`, chọn JDK tương ứng | Chỉ đổi language level trong editor |
| Generated code | Annotation processor/plugin và generated source configuration | Mark thư mục generated bằng tay mà không tạo nó khi CI build |
| Repository nội bộ | Settings/mirror và quyền truy cập hợp lệ | Download JAR thủ công và bỏ vào `lib/` |
| Multi-module | Root `<modules>` và các child POM/dependency coordinates | Tự tạo modules IDE với đường dẫn khác reactor |

## 3. Scope quyết định classpath như thế nào?

Theo Apache Maven dependency mechanism, scope ảnh hưởng dependency resolution, transitivity và việc một dependency có mặt trên **compile, runtime hoặc test classpath**.

| Scope | Compile main | Runtime main | Test compile/run | Ghi chú |
| --- | --- | --- | --- | --- |
| `compile` | Có | Có | Có | Mặc định; thường transitive |
| `provided` | Có | Không do Maven runtime classpath thông thường | Có | Runtime/container/JDK dự kiến cung cấp; không tự áp khi chạy app standalone |
| `runtime` | Không dùng để compile main | Có | Có | Ví dụ implementation chỉ cần khi thực thi |
| `test` | Không | Không | Có | JUnit, Mockito; không phát hành cùng main runtime |
| `system` | Theo local systemPath | Theo path đã chỉ định | Theo path đã chỉ định | Đặc biệt, không khuyến nghị; Maven không resolve từ repo chuẩn |
| `import` | Không phải dependency thông thường | Không | Không | Chỉ dùng `type=pom` trong `dependencyManagement` để import BOM |

Một JAR có thể xuất hiện trong **test classpath** mà không xuất hiện trong **main runtime classpath**. Ví dụ thư viện JUnit trong `src/test/java` là hợp lệ, nhưng import JUnit trong `src/main/java` sẽ không compile nếu chỉ khai `scope=test` — đó là dấu hiệu đúng của Maven chứ không phải IDE bị lỗi.

### 3.1. Compile, test và runtime là ba bài toán khác nhau

Ví dụ:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

- `commons-lang3` không khai scope, mặc định `compile`; `src/main/java`, `src/test/java` và chương trình đang chạy đều có thể dùng.
- `junit-jupiter` chỉ dùng trong test; không đi vào runtime classpath khi chạy main theo mặc định.
- Nếu IDE thêm JUnit vào **main** classpath thủ công để sửa lỗi import sai, CLI vẫn báo lỗi đúng và team mất thời gian tìm nguyên nhân.
- Nếu IDE chỉ thêm Commons Lang từ một path local, `mvn test` trên CI sẽ báo `package org.apache.commons.lang3 does not exist` vì POM không khai dependency.

### 3.2. Transitive dependencies và version mediation

Maven tự resolve dependencies của dependencies (theo scope, optional/exclusions và dependency mediation). Khi nhiều đường transitively đưa vào phiên bản khác nhau, Maven có luật chọn dependency gần nhất trong graph (*nearest definition*) và thứ tự khai báo ở mức gần bằng nhau có thể quan trọng.

IDE nên hiển thị **Maven-resolved** dependency tree. Để điều tra từ Maven CLI:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Với multi-module chạy từ root, lệnh có thể in tree cho từng module. Không dựa vào thứ tự các JAR trong `.idea/libraries` hoặc `Referenced Libraries` để giải quyết version conflicts; thay bằng `dependencyManagement`/BOM/exclusions có chủ đích rồi reimport.

### 3.3. DependencyManagement và BOM không tự add dependency

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Chỉ cấu hình version như trên **không đưa commons-lang3 vào classpath**. Một child module phải khai:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
```

Khi đang import IDE và chỉ thấy commons-lang3 trong parent dependencyManagement mà không thấy ở module đang code, hãy kiểm `<dependencies>` thực tế. Không thêm JAR trong IDE để “bù” dependency chưa khai.

## 4. Ví dụ Maven 3.9.x + Java 17 hoàn chỉnh

Ta tạo một project **đủ nhỏ để kiểm classpath rõ ràng nhưng có dependency thật**:

- Java application dùng `org.apache.commons.lang3.StringUtils` từ Commons Lang3 ở compile/runtime scope.
- JUnit Jupiter trong test scope, với **4 test methods**.
- `src/main/resources/app.properties` được Maven Resources Plugin copy vào `target/classes`.
- Exec Maven Plugin chạy Java main với **runtime classpath do Maven giải quyết**, không tự ghép `lib/*.jar`.
- Compiler Plugin dùng `--release 17`.
- Maven Dependency Plugin hỗ trợ xem dependency tree/Classpath.
- Output Java là **hai dòng ASCII cố định**, giúp kiểm IDE–CLI trên nhiều hệ điều hành.

### 4.1. Cây thư mục

```text
ide-pom-import-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── vn/example/ide/
    │   │       └── App.java
    │   └── resources/
    │       └── app.properties
    └── test/
        └── java/
            └── vn/example/ide/
                └── AppTest.java
```

Thư mục `target` được Maven tạo; **không tạo thủ công rồi commit**. Không có `lib` hay classpath file tự viết. Sau khi mở root POM, IDE phải hiểu `src/main/java` là production source root, `src/test/java` là test source root, `src/main/resources` là resources và `target` là generated build output.

### 4.2. POM đầy đủ

File `ide-pom-import-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>ide-pom-import-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.jupiter.version>5.11.0</junit.jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
                <configuration>
                    <mainClass>vn.example.ide.App</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao POM này đủ dùng trong cả ba IDE?** Nó khai Maven-standard source roots; compiler release; tất cả library dependencies với version/scope; unit test runner version; resources lifecycle; và plugin chạy Java với runtime classpath đúng. Không có IDE-specific `.iml`, `.classpath`, `.vscode/settings.json` hay đường dẫn `C:\Users\...\libs` bắt buộc cho build.

Plugin `exec-maven-plugin:java` chạy main trong JVM của Maven với project dependencies theo `classpathScope`. Nó không tạo một OS process `java` riêng như `exec:exec`; do đó có khác biệt về thread/process behavior so với chạy CLI thuần, nhưng đủ chính xác để minh họa **Maven-managed classpath**. `runtime` scope mặc định bao gồm compile/runtime dependencies, **không bao gồm JUnit test-scope**.

### 4.3. Source: App.java

File `src/main/java/vn/example/ide/App.java`:

```java
package vn.example.ide;

import java.io.IOException;
import java.io.InputStream;
import java.util.Locale;
import java.util.Properties;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String normalize(String input) {
        if (StringUtils.isBlank(input)) {
            return "EMPTY";
        }
        return StringUtils.normalizeSpace(input)
                .toUpperCase(Locale.ROOT);
    }

    public static String label() throws IOException {
        try (InputStream input =
                     App.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing resource app.properties");
            }
            Properties properties = new Properties();
            properties.load(input);
            return properties.getProperty("label", "missing");
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println(
                "normalized=" + normalize("  hello    Maven  "));
        System.out.println("label=" + label());
    }
}
```

Chú ý:

- `org.apache.commons.lang3.StringUtils` **không** thuộc JDK; nếu POM thiếu dependency, compile sẽ fail cả ở CLI lẫn IDE đã import chuẩn.
- `StringUtils.normalizeSpace` loại khoảng trắng thừa; `Locale.ROOT` tránh kết quả uppercase phụ thuộc ngôn ngữ máy.
- `App.class.getResourceAsStream("/app.properties")` đọc resource từ **classpath**, không phụ thuộc working directory.
- Dùng `try-with-resources` để đóng stream; có lỗi rõ nếu resource bị thiếu.
- Đây là executable `main` trong Java class, nhưng main JAR không mặc định có manifest `Main-Class`; `exec:java` vẫn chạy được vì khai `mainClass`.

### 4.4. Resource: app.properties

File `src/main/resources/app.properties`:

```properties
label=from-resources
```

Maven Resources Plugin mặc định copy file này vào `target/classes/app.properties` khi chạy `process-resources`. Trong IDE được import chuẩn, `src/main/resources` là một resource root tương ứng, giúp debug/run nhận được `app.properties`.

**Không dùng `new FileInputStream("src/main/resources/app.properties")` cho runtime library code** chỉ để chữa lỗi khi IDE launch từ workspace root. Cách đó phụ thuộc current working directory và sẽ fail khi chạy JAR trên máy khác. Dùng ClassLoader/Class resource API và khai resources đúng Maven conventions.

### 4.5. Tests: AppTest.java

File `src/test/java/vn/example/ide/AppTest.java`:

```java
package vn.example.ide;

import java.io.IOException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {

    @Test
    void normalizesWhitespace() {
        assertEquals("HELLO MAVEN",
                App.normalize("  hello    Maven  "));
    }

    @Test
    void returnsEmptyForBlankString() {
        assertEquals("EMPTY", App.normalize("   "));
    }

    @Test
    void returnsEmptyForNull() {
        assertEquals("EMPTY", App.normalize(null));
    }

    @Test
    void readsResourceFromClasspath() throws IOException {
        assertEquals("from-resources", App.label());
    }
}
```

Có **4 methods `@Test`**. JUnit Jupiter là dependency test-scope, nên có mặt trong test compiler/test runtime nhưng **không** nằm trong `main` compile/runtime classpath. Surefire 3.5.2 chạy test class theo convention `*Test`.

### 4.6. Lệnh build và stdout thực tế cần đối chiếu

Tại root project:

```bash
java -version
mvn --version
mvn -B clean verify
mvn -q exec:java
```

Lệnh `mvn -B clean verify` sẽ compile Java 17, copy resources, compile test, chạy bốn JUnit tests và package main JAR. Khi plugins/dependencies resolve được và code được chép đúng, Maven dự kiến kết thúc `BUILD SUCCESS`.

**Hai dòng stdout chính xác do `App.main` in ra** (với `-q`, Maven không in INFO logs thông thường; lỗi/extension logs ngoài App có thể vẫn xuất hiện):

```text
normalized=HELLO MAVEN
label=from-resources
```

`mvn -q exec:java` yêu cầu project đã compile trước đó (ở đây `verify` đã chạy). Từ thư mục project sạch chỉ có POM/source mà chưa build, dùng:

```bash
mvn -q compile exec:java
```

vì `exec:java` tự nó **không thay việc compile source**. Với `exec:java` có `classpathScope=runtime`, Commons Lang3 có mặt, còn JUnit test library không được đưa vào classpath của main.

### 4.7. Vì sao không chạy java -cp target/classes một cách tùy ý?

Sau `mvn verify`, thử:

```bash
java -cp target/classes vn.example.ide.App
```

Lệnh này chỉ đưa **project output directory** vào classpath, **không có Commons Lang3 JAR**. Với `App.normalize`, JVM có thể báo `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` khi method đó cần load library. Đây là một **negative example có chủ đích** của classpath thiếu.

Chữa đúng: chạy bằng `mvn exec:java` hoặc xây một **runtime classpath từ Maven Dependency Plugin**, hoặc đóng gói executable/shaded distribution phù hợp. **Không lấy đường dẫn tùy ý tới JAR trong `~/.m2/repository` rồi hardcode vào IDE**; làm như vậy tạo cấu hình chỉ chạy trên máy một người.

### 4.8. Maven Dependency Plugin kiểm cây dependency

Từ root:

```bash
mvn -B dependency:tree
```

Vì POM đã pin Maven Dependency Plugin 3.8.1, command cho thấy direct dependency `commons-lang3` và `junit-jupiter` (cùng transitive JUnit components), scopes và versions thực sự được giải quyết. Nếu muốn output machine-readable để diff/CI:

```bash
mvn -B dependency:tree \
  -DoutputType=json \
  -DoutputFile=target/dependency-tree.json
```

Trên Windows PowerShell dùng một dòng:

```powershell
mvn.cmd -B dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
```

Maven Dependency Plugin 3.8.1 hỗ trợ JSON output cho `dependency:tree`. Đây là bằng chứng Maven resolver chọn gì, không phải kết quả người dùng đã tick trong IDE Project Structure.

## 5. Import dự án vào IntelliJ IDEA

IntelliJ IDEA có Maven integration. Tên menu có thể thay đổi nhẹ theo phiên bản/giao diện; mục tiêu là **đăng ký root `pom.xml` làm một Maven project có thể sync**, không chỉ mở folder và đặt JAR classpath thủ công.

### 5.1. Từ repository đã clone

1. Clone/checkout project bằng Git và xác nhận root có `pom.xml`.
2. Chọn **File → Open**, chọn thư mục `ide-pom-import-lab` hoặc chính `pom.xml` theo phiên bản IDEA.
3. Mở project như một **Maven project**; cho IDE thực hiện Maven import/index/dependency resolution.
4. Nếu được hỏi, chọn **Project SDK / Maven importer JDK** phù hợp Java 17+, và Maven distribution đúng dự án (Maven Wrapper khi repo có cấu hình).
5. Mở **Maven tool window**; kiểm thấy `ide-pom-import-lab`, `Lifecycle`, `Plugins`, `Dependencies`.
6. Trong Project view, kiểm `src/main/java`/`src/test/java`/`src/main/resources` được nhận dạng phù hợp; `target` là build output.
7. Mở `App.java`; import `StringUtils` không đỏ khi Maven dependencies đã resolve.
8. Mở `AppTest.java`; `org.junit.jupiter.api.Test` chỉ cần hiện diện trên **test classpath**.
9. Chạy Maven lifecycle `clean verify` từ Maven tool window/terminal. Dùng Run Configuration với `vn.example.ide.App` để so stdout.

**Dấu hiệu import đúng:** module Maven xuất hiện trong Maven tool window, dependencies hiển thị từ POM, editor hiểu JDK/sources/tests/resources và Maven CLI build pass.

### 5.2. Sau khi thêm hoặc đổi dependency trong pom.xml

Ví dụ thêm một `<dependency>` hoặc đổi version:

- Sửa `pom.xml` — **đây là bước quyết định**.
- Dùng thông báo **Sync Maven Changes** hoặc **Reload/Sync All Maven Projects** trong Maven tool window (tên nút thay đổi theo bản IDE).
- Kiểm plugin import hoàn tất và dependency đã hiện ở Maven tool window.
- Nếu code vẫn đỏ, thử `mvn -B clean test` trong terminal IDE/terminal hệ điều hành để phân biệt lỗi Maven resolution và lỗi IDE index.
- Không vào `Project Structure → Modules → Dependencies` thêm JAR thủ công để “che lỗi”, vì Maven sync có thể gỡ thư viện thêm thủ công.

JetBrains IDEA documentation hiện hành mô tả Maven project model là nguồn chính và nhắc rằng dependencies thêm trong Project Structure không tương ứng POM có thể bị xóa khi sync.

### 5.3. JDK cho IDE không chỉ có một nút

Trong IntelliJ có thể phân biệt:

- **Project SDK:** JDK IDE dùng cho source analysis/run/test configurations.
- **Module SDK / language level:** khả năng của từng module, thường đi theo Maven compiler config nếu import chính xác.
- **JDK for Maven importer:** JDK chạy quá trình import Maven model.
- **JRE/JDK for Maven runner:** JDK dùng khi chạy Maven goals từ IDE.
- **Maven distribution:** Bundled Maven, external Maven installation hoặc Maven Wrapper.

Đặt tất cả cùng Java 17 (hoặc toolchain được project hỗ trợ) giúp giảm khác biệt. `maven.compiler.release=17` **không tự biến một JDK 11 thành JDK 17**; phải cài/chọn JDK hỗ trợ. Nếu Maven runtime JDK quá cũ, build fail trước khi project compile, dù editor đang đặt language level 17.

### 5.4. IDE builder so với Maven builder

IntelliJ có builder/runner nội bộ và lựa chọn ủy quyền build/run cho Maven. Hai chế độ có thể khác nhau nếu project phụ thuộc plugin goals sinh mã/resource, APT hoặc packaging đặc biệt. Để xuất bản sản phẩm, luôn dùng **`mvn clean verify` hoặc release pipeline Maven** làm căn cứ cuối.

Nếu Run trong IntelliJ chạy tốt nhưng `mvn test` fail, hãy tìm configuration chỉ tồn tại trong IDE: manual classpath, working directory, JDK, environment variables, annotation processing, hoặc test runner khác.

## 6. Import dự án vào Eclipse với m2e

**Eclipse m2e** đọc POM và quản lý classpath/build path thông qua Maven integration. Hãy chọn wizard Maven, không chọn “Existing Projects into Workspace” cho một thư mục chỉ có `pom.xml` rồi tự thêm external JAR.

Các bước thông dụng:

1. Mở Eclipse có **Maven Integration for Eclipse (m2e)**.
2. Chọn **File → Import → Maven → Existing Maven Projects**.
3. Chọn root directory chứa `pom.xml`.
4. Eclipse tìm root/child POMs; chọn các projects cần import rồi Finish.
5. Chờ m2e resolve dependencies và update Java Build Path.
6. Mở **Project Explorer**: kiểm `Maven Dependencies` container thay vì một danh sách external JAR thêm bằng tay.
7. Kiểm `Java Build Path`, `JRE System Library`/JDK 17 và `src/main/java`/`src/test/java` root types.
8. Chạy **Run As → Maven test/verify** (hoặc Maven Run Configuration với `clean verify`), đối chiếu Maven CLI.
9. Chạy `App.main` như Java Application nếu classpath Maven đã sync, so hai dòng stdout.

Sau khi sửa `pom.xml` hoặc chuyển Git branch:

- Chọn project → **Maven → Update Project…** (shortcut thường **Alt+F5**).
- Chọn các Maven modules bị ảnh hưởng; để m2e đồng bộ dependency container và project configuration.
- Nếu source/resource artifacts chưa sinh, chạy goals cần thiết theo build lifecycle; chỉ m2e import không nhất thiết gọi mọi custom generator plugin.
- Dùng **Refresh**/Project Clean có kiểm soát khi Eclipse hiển thị stale state.
- Không chỉnh thủ công `.classpath` để thêm JAR ngoài POM; m2e có thể ghi lại classpath ở lần cập nhật sau.

Theo FAQ m2e, action Update Project configuration có default goals liên quan `process-resources` tùy preferences; không suy diễn rằng Eclipse import luôn chạy toàn bộ `verify` hoặc generator đặc biệt. Nếu Maven CLI build xanh mà Eclipse báo **“Plugin execution not covered by lifecycle configuration”**, cần m2e connector/lifecycle mapping phù hợp, không có nghĩa dependency JAR đã thiếu hoặc Maven CLI bị lỗi.

### 6.1. Eclipse và nhiều module

Với reactor, hãy import từ **root POM** để m2e nhận diện các child modules, project references và dependencies. Nếu chỉ import một child module, Maven có thể tìm parent POM ở local repository hoặc đường `relativePath` chưa tồn tại, dẫn đến lỗi. Đừng tự copy compiled child JAR vào build path; import sibling modules hoặc chạy Maven reactor/local install đúng cách.

## 7. Import vào Visual Studio Code với Java extensions

VS Code không phải IDE Java đầy đủ theo mặc định. Để làm việc hiệu quả với Maven, cần **Extension Pack for Java** (bao gồm Java language support, debugger/test tools) và **Maven for Java**. Theo tài liệu Microsoft, có thể mở folder chứa `pom.xml`; Java extensions sẽ nhận diện và import Java project/module trong workspace.

Quy trình:

1. Cài các Java extensions phù hợp (từ marketplace/extension policy của tổ chức).
2. Chọn **File → Open Folder…**, trỏ tới root `ide-pom-import-lab` chứa `pom.xml`.
3. Chờ Java language server và Maven for Java extension hoàn thành import/indexing và dependency resolution.
4. Mở panel **JAVA PROJECTS** và panel **MAVEN**; kiểm project và Maven dependencies/modules được hiển thị.
5. Nếu thêm module hoặc đổi POM mà project chưa hiện, mở Command Palette → **Java: Import Java projects in workspace**.
6. Đảm bảo VS Code Java runtime settings và Maven runner dùng JDK được dự án chấp thuận (Java 17 ở ví dụ).
7. Chạy `mvn -B clean verify` trong terminal của VS Code; chạy class `App` bằng Java Run/Debug và kiểm output.
8. Đừng cấu hình `java.project.referencedLibraries` bằng các local `lib/*.jar` để thay thế dependencies của Maven project — tính năng đó phục vụ unmanaged Java projects; Maven project phải để extension/Maven quản lý classpath.

Maven for Java extension cho phép xem Maven projects, module trees, chạy goals qua context menu và nhận biết `pom.xml`. Nếu VS Code chỉ hiển thị file Java đơn lẻ với thông báo “unmanaged project”, khả năng cao là bạn mở **sai folder** hoặc Java import chưa hoàn tất.

### 7.1. Khi VS Code import nhưng code vẫn có dấu lỗi

Lần lượt xác nhận:

- Root `pom.xml` đã nằm trong opened workspace chưa?
- Java language server/JDK đúng phiên bản chưa?
- Maven extension thực sự đang import project hay chỉ có editor Java syntax?
- Lệnh `mvn clean test` trên cùng folder có chạy được không?
- `settings.xml`, proxy, mirror hoặc offline setting có ngăn dependency resolution không?
- Active Maven profiles trên terminal có khác với IDE importer không?

Các lệnh khôi phục Java workspace/index chỉ nên là **bước sau khi đã kiểm POM/toolchain/dependency**, vì reset caches không sửa POM thiếu dependency hoặc repository 401/403.

## 8. Phân biệt Maven CLI và IDE run/debug classpaths

Một Java Maven project có nhiều cách chạy cùng class `App`:

| Cách | Classpath thường được sử dụng | Điểm cần nhớ |
| --- | --- | --- |
| `mvn test` | Maven Surefire test classpath | Gồm test classes, main classes, compile/runtime/test deps |
| `mvn exec:java` | Exec Maven Plugin classpathScope (ví dụ runtime) | Tự resolve project dependencies theo POM |
| Run/Debug `App` trong IDE | IDE-imported model project dependencies | Phải sync Maven; IDE có thể áp working dir/env riêng |
| `java -cp target/classes ...` | **Chỉ** project classes nếu không thêm deps | Dễ NoClassDefFoundError |
| `java -jar target/*.jar` | Theo manifest/Class-Path và packaging | Plain Maven JAR không có Main-Class và không chứa toàn bộ deps |
| CI `mvn -B clean verify` | Maven lifecycle theo POM/settings/JDK | Là mốc giao hàng; không tin riêng IDE green check |

### 8.1. Tại sao IDE Run được mà java -jar fail?

Có hai lý do phổ biến:

1. Plain JAR từ Maven JAR Plugin thường **không khai `Main-Class`** nếu chưa cấu hình manifest.
2. Main JAR không tự gói Commons Lang3 và transitive dependencies. Java runtime classpath cần các JAR đó nếu không dùng executable/fat JAR packaging.

IDE Run Configuration có thể tự xây classpath từ Maven model, nên chạy được; `java -jar` không tự mang toàn bộ Maven dependencies. Đây không phải lỗi import. Muốn distribution chạy bằng một file, cấu hình Maven Shade Plugin hoặc application packaging thích hợp, nhưng đó là **bài toán phát hành riêng**, không sửa bằng cách thêm JAR thủ công trong IDE.

### 8.2. Test classpath có resources khác main

Maven resource roots tiêu chuẩn:

```text
src/main/resources    -> target/classes
src/test/resources    -> target/test-classes
```

Test classpath thường chứa cả `target/classes` và `target/test-classes`, còn runtime main không chứa test resources. Nếu bạn đặt `app.properties` ở `src/test/resources`, `AppTest` có thể pass nhưng main chạy qua exec:java không thấy file. Hãy đặt cấu hình runtime ở `src/main/resources` theo yêu cầu và kiểm đúng packaging.

## 9. Multi-module Reactor: import root, không tạo modules bằng tay

Một repository thực tế:

```text
workspace-parent/
├── pom.xml                 # packaging pom, aggregator
├── core/
│   ├── pom.xml
│   └── src/main/java/...
└── app/
    ├── pom.xml
    ├── src/main/java/...
    └── src/test/java/...
```

Root POM **fragment minh họa** (không phải toàn bộ runnable example của phần 4):

```xml
<groupId>vn.example</groupId>
<artifactId>workspace-parent</artifactId>
<version>1.0.0</version>
<packaging>pom</packaging>
<modules>
    <module>core</module>
    <module>app</module>
</modules>
```

Một child `app` thường có parent:

```xml
<parent>
    <groupId>vn.example</groupId>
    <artifactId>workspace-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
<artifactId>app</artifactId>
```

và dependency vào sibling:

```xml
<dependency>
    <groupId>vn.example</groupId>
    <artifactId>core</artifactId>
    <version>${project.version}</version>
</dependency>
```

**Root `<modules>` là aggregation; child `<parent>` mới là inheritance.** Import root POM giúp IDE tìm tất cả reactor modules và maps sibling dependency tới module output thay vì luôn tải một JAR version cũ trong local repo.

Nếu chỉ mở `app` như standalone project rồi thêm `core/target/classes` bằng tay, dự án có thể chạy trên máy hiện tại nhưng sai khi Git clone/CI build. Đúng hơn: import root, khai `core` dependency trong child POM và để Maven/IDE resolve reactor.

### 9.1. Dùng Maven CLI kiểm toàn reactor

```bash
mvn -B clean verify
```

Từ root chạy full reactor; Maven sắp xếp thứ tự theo dependency graph. Với nhu cầu chạy riêng `app` và dependencies trong reactor:

```bash
mvn -B -pl :app -am test
```

`-pl` chọn module theo artifactId, `-am` dựng thêm reactor dependencies cần thiết. **Kết quả của selected modules không tự chứng minh full reactor đã pass**, nên CI release vẫn kiểm tập modules bắt buộc.

### 9.2. Parent không resolve

Triệu chứng:

```text
Non-resolvable parent POM
Could not find artifact vn.example:workspace-parent:pom:1.0.0
```

Đầu tiên kiểm đường `relativePath`, parent version và việc mở đúng root. Nếu parent là published POM thì kiểm Maven repository/settings/mirror; nếu parent là local source sibling thì import/sử dụng reactor root. **Không tải một parent POM bất kỳ** rồi chèn vào global IDE library: parent model thuộc Maven resolution, không phải Java classpath.

## 10. Maven Wrapper, JDK và settings.xml

### 10.1. Maven Wrapper dùng làm gì?

Một repository có Maven Wrapper thường chứa:

```text
mvnw                 # Unix/macOS
mvnw.cmd             # Windows
.mvn/wrapper/maven-wrapper.properties
```

Đây là các file ví dụ khi Wrapper đã được thiết lập, không phải yêu cầu của project bài thực hành. Khi tồn tại, developer có thể dùng:

```bash
./mvnw -B clean verify
```

hoặc PowerShell/cmd:

```powershell
.\mvnw.cmd -B clean verify
```

Wrapper giúp sử dụng **Maven distribution** được dự án quy định (có thể tải khi chưa cache). Nó **không tự cài/chọn JDK 17**; IDE và CI vẫn phải có Java runtime/toolchain tương thích. Tùy phiên bản IDE, chọn Maven Wrapper làm Maven home/distribution để build trong IDE giống CLI.

### 10.2. Có ba nơi JDK dễ lệch

Ví dụ lỗi: `java -version` trong terminal là Java 17, nhưng IDEA Project SDK là Java 21 và Maven Runner JRE là Java 11; khi import plugin có thể thất bại hoặc generated classes khác.

Đối chiếu:

```bash
java -version
mvn --version
```

`mvn --version` hiển thị **Java version Maven thực sự đang chạy** (có thể khác `java -version` do JAVA_HOME), Maven home và OS. Chọn JDK để import/run/test trong IDE phù hợp. POM `<release>17</release>` giới hạn public Java API/target bytecode nhưng vẫn cần JDK **hỗ trợ release 17**.

Đối với tổ chức có nhiều JDK, dùng Maven Toolchains Plugin hoặc Maven Enforcer Plugin nếu cần bảo đảm toolchain/policy cụ thể. **Không chấp nhận IDE “vẫn chạy” như bằng chứng build đúng JDK release.**

### 10.3. Settings/mirror/repositories

Khi import POM, IDE/Maven có thể cần tải dependencies từ Maven Central hoặc repository nội bộ:

- `~/.m2/settings.xml` hoặc settings file CI chỉ định qua `-s`.
- `servers` chứa credentials theo ID.
- `mirrors` chuyển download qua proxy/nội bộ; `proxies` mô tả proxy.
- `localRepository` thay vị trí dependency cache.
- `profiles` trong settings có thể thêm repositories/activation khác nhau.

Một project IDE có dependency lỗi vì **401/403/network/PKIX** thường không được chữa bằng việc copy JAR vào Module Dependencies. Sửa đúng mirror/settings/proxy/truststore/credentials, không commit passwords/token vào POM, và kiểm cùng settings path giữa IDE importer và Maven CLI.

### 10.4. Offline mode và cache

`mvn -o verify` chỉ hoạt động khi dependencies/plugins đã có trong local repository. Nếu máy chưa từng resolve Apache Commons Lang/JUnit/Compiler Plugin, offline mode có thể fail. Khi Maven CLI online resolve được nhưng IDE không, kiểm IDE đã bật **Work offline** chưa. Khi CLI offline fail nhưng IDE Run dùng cached external libs, đó là khác biệt môi trường, không tự coi POM hợp lệ trong build sạch.

Một lần download failure có thể bị Maven cache negative result (`.lastUpdated`), khiến lần sau không thử lại ngay tùy update policy. Sau khi sửa mạng/repository, có thể chạy `mvn -U clean verify` để yêu cầu Maven kiểm update/snapshot metadata tương ứng; không xóa cả `~/.m2/repository` như bước đầu.

## 11. Active Maven profiles và IDE–CI parity

POM profiles có thể:

- Bật thêm source roots/modules/dependencies.
- Đổi compiler properties.
- Thay resource filtering/plugin executions.
- Đưa generated sources vào build.
- Bật database/container integration test hoặc production packaging.

Ví dụ fragment **minh họa, không thuộc POM runnable**:

```xml
<profiles>
    <profile>
        <id>integration</id>
        <properties>
            <run.integration.tests>true</run.integration.tests>
        </properties>
    </profile>
</profiles>
```

Nếu CI gọi `mvn -Pintegration verify` mà IDE importer chưa bật profile đó, editor có thể báo thiếu class hoặc runtime env khác. Hãy kiểm **active profiles của IDE Maven integration** và CLI, không thêm JAR cho một dependency chỉ xuất hiện trong profile khác.

Lệnh trợ giúp:

```bash
mvn -B help:active-profiles
mvn -B help:effective-pom -Doutput=target/effective-pom.xml
mvn -B help:effective-settings
```

**Cảnh báo:** `help:effective-settings` có thể trình bày các thuộc tính settings nhạy cảm (thường che mật khẩu nhưng không nên giả định mọi dữ liệu đều an toàn). Không đăng công khai logs chứa repository URL nội bộ, username, token hoặc các env vars. Effective POM giúp xác định dependencies/plugins thực sau khi áp parent/profiles/properties; không sửa file generated effective POM để giải quyết build.

### 11.1. Kỷ luật cấu hình

Các yếu tố quan trọng phải nhất quán giữa IDE và CI:

```text
Git commit / branch
Maven distribution / Wrapper
JDK vendor + major / toolchains
POM parents and dependency BOMs
Active profiles and -D properties
settings.xml, mirrors and repositories
Maven local repository isolation as appropriate
Build command and test selection
Environment variables needed by plugins/tests
```

Nếu một yếu tố khác, trước tiên xác minh **đó có phải khác biệt chủ đích**. Không kết luận IDE hỏng khi một profile đang làm Maven model khác.

## 12. Generated sources và annotation processors

Một số project dùng **Lombok, MapStruct, QueryDSL, OpenAPI Generator, JAXB** hoặc plugin sinh Java code. Đây là điểm dễ gây sai khác:

- Maven CLI có goal `generate-sources`, `process-sources`, `compile` và processor configuration.
- IDE import POM có thể biết generated source directory hoặc cần thêm connector/annotation processing setting.
- IDE builder không nhất thiết chạy mọi plugin execution như Maven lifecycle.
- Nếu generated sources nằm trong `target/generated-sources`, không commit chúng tùy tiện hoặc đánh dấu thủ công như cách duy nhất để code compile trên máy mình.
- Đưa generator dependency/version/goal/execution vào POM, xác định phase chuẩn và cấu hình compiler annotation processor path khi cần.

Ví dụ **fragment** cho một generator plugin, không phải runnable config:

```xml
<execution>
    <id>generate-model</id>
    <phase>generate-sources</phase>
    <goals>
        <goal>generate</goal>
    </goals>
</execution>
```

Tên goal `generate` không thuộc mọi generator plugin và fragment trên chỉ minh họa cách bind phase. Trong dự án thật phải dùng goal/parameters **chính xác theo plugin cụ thể**. IDE import không thể tự suy đoán những outputs mà POM chưa khai.

### 12.1. Làm gì khi m2e báo lifecycle mapping error?

Nếu plugin execution không có m2e connector, Eclipse có thể báo `Plugin execution not covered by lifecycle configuration` dù `mvn clean verify` chạy được. Cách xử lý là:

1. Đọc plugin goal phase và output dự kiến.
2. Xác định m2e connector/lifecycle mapping phù hợp, theo tài liệu plugin/m2e.
3. Nếu plugin sinh nguồn, cần giải pháp khiến Eclipse hiểu generated sources hoặc cho Maven chạy generator đúng lúc.
4. Không thêm output JAR vào IDE build path thủ công để che một generated-source/lifecycle vấn đề.

### 12.2. IntelliJ annotation processing

Maven Compiler Plugin có thể điều khiển annotation processors. Nếu Maven CLI thành công nhưng IntelliJ builder báo các generated symbols không tồn tại, kiểm **annotation processing**/Maven import settings và tương thích processor với JDK. Có thể delegate build to Maven cho dự án yêu cầu plugin code generation phức tạp. Không chuyển một `test` dependency sang `compile` chỉ vì IDE annotation processing cấu hình sai.

## 13. Khi build xanh nhưng editor đỏ: chẩn đoán theo lớp

Có ba tầng dễ nhầm:

1. **Maven model/resolution**: POM, parent, profiles, dependency tree, repositories.
2. **IDE import/index/model**: project link, Maven sync, source roots, JDK, extension/m2e connector.
3. **Execution environment**: run configuration, working dir, VM args, runtime deps, resources, environment variables.

Một error đỏ ở editor **không tự chứng minh Maven build fail**; và Maven build xanh không chắc IDE Run Configuration dùng cùng JDK/profile/working directory.

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý dựa trên POM |
| --- | --- | --- |
| IDE không thấy Maven tool window/modules | Mở Java folder/unmanaged project thay vì import `pom.xml` | File → Open root POM, link/import Maven project |
| `StringUtils` đỏ trong editor, CLI xanh | Chưa Maven sync, IDE offline/index stale | Sync/reload; kiểm Maven tool window, settings |
| CLI fail `package ... does not exist`, IDE chạy được | IDE có JAR thêm bằng tay không có trong POM | Khai dependency GAV/version/scope trong POM |
| JUnit import đỏ trong `src/test/java` | Thiếu `junit-jupiter` `test` hoặc test source root sai | Khai dependency test, sync, kiểm root |
| JUnit có trong `src/main/java` nhưng compile fail | Dùng test-scope dependency trong main code | Sửa source/kiến trúc, không nâng scope bừa |
| Project dùng Java 17 nhưng IDE dùng JDK 11 | Importer/Project SDK/runner khác Maven | Đặt JDK phù hợp ở cả ba nơi |
| `release version 17 not supported` | Maven Compiler chạy với JDK quá cũ | Kiểm `mvn --version` và JAVA_HOME |
| `NoClassDefFoundError StringUtils` khi `java -cp target/classes` | Runtime classpath chỉ có classes của app | Dùng Maven exec:java hoặc runtime classpath đúng |
| Test đọc `app.properties` pass nhưng main fail | Resource chỉ nằm trong `src/test/resources` | Chuyển runtime resource vào `src/main/resources` |
| POM khai dependencyManagement nhưng IDE thiếu JAR | Chưa có dependency trong `<dependencies>` | Khai dependency thực ở module dùng |
| Eclipse báo lifecycle mapping warning | m2e thiếu connector cho plugin goal | Cấu hình connector/mapping, không copy JAR |
| VS Code hiển thị unmanaged Java project | Mở sai folder/Java import chưa hoàn tất | Open root POM, Java: Import Java projects |
| Cùng GAV nhưng Java class khác | Version mediation, local cache hoặc dependency shading | `dependency:tree`, lock versions/exclusions |
| CI download fail 401/403 | Không có credentials/mirror/settings phù hợp | Sửa settings/secret store; không hardcode token |
| Maven offline cannot resolve artifact | Local repo thiếu dependency/plugin | Tắt offline và resolve đúng; tránh xóa toàn cache |
| Parent POM not found | Wrong relativePath/module selection/repo | Import root, khai parent version/path đúng |
| IDE và CI tests chọn khác | IDE runner khác Surefire includes/profiles/JDK | Chạy Maven verify và kiểm test reports |
| Annotation-generated class đỏ trong IDE | APT/import/generator khác Maven | Khai processor/generator đúng POM và sync |
| IDE auto-completion lẫn version khác | JAR global/manual classpath còn trong project | Gỡ manual libs, reload Maven model |
| Build chạy trên máy nhưng fail trong CI sạch | Hidden local dependency, undeclared env/toolchain | Checkout sạch, build qua Maven Wrapper, fix POM |
| IDE và CLI cùng fail | POM/dependency/build thật sự lỗi | Bắt đầu từ Maven error, không reset IDE liên tục |

### 13.1. Thứ tự chữa lỗi hiệu quả

```text
(1) Kiểm repo root và pom.xml
  -> (2) java -version + mvn --version
  -> (3) mvn -B clean verify
  -> (4) mvn dependency:tree
  -> (5) kiểm Maven profiles/settings/parent
  -> (6) IDE Maven Sync/Update Project
  -> (7) source/test/resource roots + JDK
  -> (8) run/debug classpath/working dir/env
  -> (9) IDE index cache reset chỉ khi có bằng chứng cần
```

Không bắt đầu bằng **xóa `~/.m2/repository`, xóa `.idea`/`.classpath` hoặc thêm `*.jar` ngẫu nhiên**. Những thao tác này dễ che nguyên nhân, phá metadata team hoặc khiến Maven tải lại gigabytes dependencies.

## 14. IDE và CI: để pipeline làm trọng tài

Một CI pipeline đáng tin cần:

- Checkout một **commit/tag xác định**, không lấy project state riêng của một IDE.
- Dùng JDK/Maven versions được hỗ trợ; tốt hơn dùng Maven Wrapper/toolchain khi có.
- Áp Maven settings/mirrors/credentials dưới CI secret management.
- Build từ POM bằng `mvn -B clean verify` (hoặc `./mvnw -B clean verify`).
- Thu Surefire/Failsafe XML test reports/coverage khi có.
- Cache Maven repository có kiểm soát, không cache IDE-specific classpath như nguồn thư viện.
- Không cần file `.idea` hoặc `.classpath` để compile/test/package.
- Coi build fail nếu required Maven dependency/profile/plugins không resolve.
- Chặn lệnh `-DskipTests`/`-Dmaven.test.skip=true` ngoài policy cho phép.
- Không dùng IDE Run Configuration thành “build script” duy nhất.

### 14.1. Một ví dụ CI job tối giản

Fragment shell **trên Linux runner có Java 17/Maven**, không phụ thuộc nhà cung cấp CI:

```bash
#!/usr/bin/env sh
set -eu

java -version
mvn --version
mvn -B --no-transfer-progress clean verify
```

Nếu dự án đã có Maven Wrapper:

```bash
#!/usr/bin/env sh
set -eu

java -version
./mvnw -B --no-transfer-progress clean verify
```

Các script trên là **fragments dùng trong CI**, không tự clone repository hoặc cài JDK; CI job phải cung cấp checkout/JDK/environment hợp lệ. `--no-transfer-progress` giảm nhiễu download progress, không đổi dependency resolution.

### 14.2. CI không cần “classpath IDE” nghĩa là gì?

Trong full clean checkout:

```text
repo/
├── pom.xml
├── src/main/java/...
├── src/main/resources/...
└── src/test/java/...
```

Maven tự biết source roots, dependencies, test scope, resource processing và plugins; `target` được tạo lại. Không cần copy `.iml`, `.classpath`, `lib/commons-lang3.jar` hoặc global editor settings từ máy developer.

Tuy nhiên CI **vẫn** cần môi trường ngoại vi chính đáng: JDK, Maven distribution, repository network/auth và secrets nếu tests/plugins yêu cầu. “POM là nguồn sự thật” không có nghĩa có thể build mà không có toolchain hoặc không có quyền tải dependencies.

## 15. Bài tập trước–sau: phát hiện cấu hình chỉ chạy trong IDE

### Trường hợp A — thêm JAR thủ công (sai)

Developer mở empty Java project trong IDE, tải `commons-lang3-3.14.0.jar` về ổ đĩa và thêm vào Build Path. Code `StringUtils.normalizeSpace` compile khi IDE build. Đồng đội clone Git nhưng không có cùng file/path; `mvn clean verify` trên CI fail.

Dấu hiệu: `pom.xml` **không** có dependency Commons Lang3 hoặc thậm chí IDE project không liên kết root Maven project.

**Sửa:** thêm dependency `org.apache.commons:commons-lang3:3.14.0` vào POM, import/reload Maven, xóa manual JAR entry. Test bằng một clean workspace trên máy khác hoặc CI.

### Trường hợp B — khai dependency ở POM (đúng)

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Khi Maven resolve dependencies:

- CLI Compiler Plugin dùng Commons Lang3 khi compile.
- Surefire có Commons Lang3 và JUnit trên test classpath.
- Exec Maven Plugin `runtime` có Commons Lang3 để chạy `App`.
- IntelliJ/Eclipse/VS Code sync POM để hiển thị đúng `StringUtils` và tests.
- CI build từ POM không cần JAR path riêng.

### Trường hợp C — chỉ sửa IDE SDK (chưa đủ)

Developer thấy `String.isBlank` đỏ, đổi language level IntelliJ lên 17 nhưng `mvn --version` báo Maven đang dùng Java 11. Mặc dù IDE editor thôi báo lỗi, Maven Compiler Plugin với `<release>17</release>` không thể chạy đúng bằng JDK 11.

**Sửa:** cài/chọn JDK 17+ cho Maven CLI/IDE importer/runner và nhất quán compiler release. Không bỏ `<release>17</release>` khỏi POM chỉ để build qua trên máy có Java 11 khi dự án yêu cầu Java 17.

### Trường hợp D — profile trên CI nhưng không bật trong IDE

Dependency `jdbc-driver` chỉ có trong profile `integration`. CI chạy `-Pintegration` nhưng IDE không active profile; import class trong module integration đỏ.

**Sửa:** bật Maven profile tương ứng trong IDE, xem effective POM và khôi phục source roots/plugins/generator đúng; không copy jdbc-driver JAR bằng tay.

### Trường hợp E — dependency xung đột

Hai direct dependencies transitively đưa vào các versions khác nhau của cùng thư viện. IDE auto-import một class có API của version X nhưng Maven resolver chọn Y do nearest definition. IDE Run có thể chạy trên stale cached classpath; CI `NoSuchMethodError`.

**Sửa:** inspect `mvn dependency:tree`, xác định version mediation, dùng `dependencyManagement`/BOM và exclusions phù hợp; sync và re-run tests. Không điều chỉnh classpath order thủ công trong IDE.

## 16. Thực hành kiểm chứng theo từng IDE

Một buổi lab hoàn chỉnh nên làm theo thứ tự:

1. Tạo source/POM/resource/test ở mục 4.
2. Từ terminal **ngoài IDE**, chạy `mvn -B clean verify`, xác nhận 4 JUnit tests pass.
3. Chạy `mvn -q exec:java`, đối chiếu đúng hai dòng `normalized=HELLO MAVEN` và `label=from-resources`.
4. Chạy `mvn -B dependency:tree`, thấy Commons Lang3 compile và JUnit test.
5. Mở root POM trong IntelliJ, Eclipse m2e hoặc VS Code Java extension.
6. Đợi sync/reload và kiểm source/test/resources roots cùng external Maven dependencies.
7. Run `App.main` bằng IDE, đối chiếu stdout; chạy `AppTest`, đối chiếu test pass.
8. Sửa POM có chủ đích (chẳng hạn thay `commons-lang3` version theo repository policy) rồi sync; xác minh IDE phản ánh version mới.
9. **Hoàn nguyên** POM nếu chỉ thử nghiệm version change; chạy lại clean verify.
10. Thử chạy `java -cp target/classes vn.example.ide.App` để thấy runtime classpath thiếu, không “sửa” bằng hardcode `lib`.
11. Tạo một clean checkout/CI job với Java17/Maven settings, chạy verify mà không copy IDE metadata.
12. Ghi lại nếu có khác biệt trong JDK/profiles/settings/run working directory; sửa từ Maven model hoặc toolchain.

Không cần mở ba IDE cùng lúc để hiểu bài: cùng một source/POM có thể được import độc lập vào từng IDE. Kết quả đúng dựa trên Maven model, không phụ thuộc tên icon/toolbar của một IDE version cụ thể.

## 17. Câu hỏi kiểm tra và đáp án

**Câu 1.** Vì sao không tự thêm `commons-lang3.jar` vào Project Structure rồi coi xong?

**Đáp án:** Classpath thủ công chỉ tồn tại ở IDE/máy hiện tại và có thể bị Maven sync gỡ. Khai dependency GAV/scope trong `pom.xml` để mọi IDE/CLI/CI resolve nhất quán.

**Câu 2.** `dependencyManagement` đã có `commons-lang3` có đồng nghĩa nó nằm trong module classpath không?

**Đáp án:** Không. DependencyManagement quản lý version/config cho dependency khi được khai trong `dependencies`; không tự add JAR.

**Câu 3.** Vì sao JUnit ở test scope mà `AppTest.java` compile được?

**Đáp án:** Maven test classpath có test dependencies. `src/main/java` không nên import JUnit test dependency.

**Câu 4.** Lệnh nào là mốc đối chiếu giữa IDE và CI cho project mẫu?

**Đáp án:** `mvn -B clean verify` từ project root với Java 17+ và Maven/settings đúng; sau đó `mvn -q exec:java` để xem stdout.

**Câu 5.** Vì sao `java -cp target/classes vn.example.ide.App` báo thiếu StringUtils?

**Đáp án:** Classpath chỉ có project classes, không có external dependency Commons Lang3. Dùng Maven-managed runtime classpath/exec plugin hoặc packaging hợp lệ.

**Câu 6.** Sau khi đổi dependency trong IntelliJ, phải thao tác gì?

**Đáp án:** Sửa POM, Sync Maven Changes/Reload Maven project, kiểm Maven tool window và chạy Maven CLI nếu nghi lệch.

**Câu 7.** Eclipse import Maven project qua wizard nào?

**Đáp án:** `File → Import → Maven → Existing Maven Projects`, chọn root POM; sau đổi POM dùng `Maven → Update Project`.

**Câu 8.** VS Code nhận Maven project từ đâu?

**Đáp án:** Open Folder chứa `pom.xml` với Java/Maven extensions; dùng `Java: Import Java projects in workspace` khi cần cập nhật.

**Câu 9.** `maven.compiler.release=17` có tự cài JDK 17 không?

**Đáp án:** Không. Cần JDK hỗ trợ release 17 ở Maven và IDE toolchain. Maven Wrapper cũng không tự giải quyết yêu cầu JDK.

**Câu 10.** Root `<modules>` và child `<parent>` giống nhau không?

**Đáp án:** Không. `<modules>` xác định reactor aggregation; `<parent>` xác định POM inheritance. Nên import root multi-module project.

**Câu 11.** Tại sao IDE test pass nhưng Maven Surefire không tìm tests?

**Đáp án:** IDE runner và Maven Surefire có thể dùng test inclusion/profile/JDK/config khác. Kiểm `src/test/java`, Surefire version/patterns và Maven test reports.

**Câu 12.** Nếu CI fail 401 khi resolve dependency, nên thêm JAR local vào IDE?

**Đáp án:** Không. Cần cấu hình credentials/mirror/repository settings phù hợp và an toàn; JAR local chỉ che lỗi.

**Câu 13.** Plugin generator chạy ở `generate-sources` nhưng IDE không thấy generated class; xử lý?

**Đáp án:** Xác nhận Maven goal chạy, cấu hình IDE connector/annotation processing hoặc delegate Maven build; không thêm random output path làm giải pháp duy nhất.

**Câu 14.** Khi project dùng `.mvn/wrapper`, tại sao Maven CLI với `mvn` có thể khác `./mvnw`?

**Đáp án:** Maven Wrapper chọn distribution được pin, còn `mvn` dùng bản cài toàn hệ thống; có thể khác version. Phải chuẩn hóa công cụ ở IDE/CI.

**Câu 15.** Một module không dùng `commons-lang3` trực tiếp nhưng parent khai trong `dependencyManagement`. Nó có tự tải về không?

**Đáp án:** Không, trừ khi dependency được khai thực sự hoặc được đưa vào theo mô hình dependencies thích hợp. Kiểm effective POM/module dependency tree.

## 18. Checklist nghiệm thu

- [ ] Source ở `src/main/java`, tests ở `src/test/java`, resources ở `src/main/resources`.
- [ ] Root `pom.xml` có đúng dependencies, versions/scopes, plugins, compiler release và module declarations.
- [ ] IDE được mở từ **Maven project/root POM**, không phải unmanaged Java project.
- [ ] IDE Maven dependencies được resolve theo POM; không có JAR thủ công cần thiết.
- [ ] Project JDK, Maven importer/runner JDK và CLI JDK hỗ trợ Java 17.
- [ ] `mvn -B clean verify` pass từ một clean checkout.
- [ ] `mvn -B dependency:tree` phản ánh đúng Commons Lang3 compile và JUnit test.
- [ ] `mvn -q exec:java` in đúng hai dòng `normalized=HELLO MAVEN` và `label=from-resources`.
- [ ] Test `AppTest` có 4 unit methods chạy thành công dưới Surefire và IDE runner.
- [ ] IntelliJ sync/reload Maven sau khi sửa POM; không sửa `Project Structure` thay cho POM.
- [ ] Eclipse m2e nhập root POM qua Existing Maven Projects và dùng Update Project khi cần.
- [ ] VS Code Java extensions nhận root POM, import Maven modules và dependencies tự động.
- [ ] Parent POM, active profiles, repositories/settings, Maven Wrapper và JDK thống nhất với CI.
- [ ] Generated sources/annotation processors được quản lý bằng Maven plugins/config.
- [ ] Khi IDE/CLI lệch nhau, kiểm Maven resolution trước rồi mới xem caches/editor.
- [ ] CI chỉ dựa vào POM và công cụ build được khai báo, không cần file IDE metadata.
- [ ] Không có hardcoded personal JAR path, credentials hoặc local repository paths trong POM.
- [ ] Không lấy “IDE chạy được” làm bằng chứng project có thể build/release trên CI.

## 19. Tài liệu chính thức

- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Help Plugin — Effective POM](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [JetBrains IntelliJ IDEA — Maven Projects and Sync](https://www.jetbrains.com/help/idea/delegate-build-and-run-actions-to-maven.html)
- [JetBrains IntelliJ IDEA — Maven Dependencies](https://www.jetbrains.com/help/idea/work-with-maven-dependencies.html)
- [JetBrains IDEA — Maven Project Not Recognized: Troubleshooting](https://support.jetbrains.com/hc/en-us/articles/40252477090066-How-to-troubleshoot-if-Maven-Project-is-not-recognized-by-IntelliJ-IDEA)
- [Eclipse m2e — Frequently Asked Questions](https://eclipse.dev/m2e/documentation/m2e-faq.html)
- [Microsoft VS Code — Managing Java Projects](https://code.visualstudio.com/docs/java/java-project)
- [Microsoft VS Code — Java Build Tools](https://code.visualstudio.com/docs/java/java-build)
- [Microsoft VS Code — Java Language Support](https://code.visualstudio.com/docs/languages/java)
