# Build POM và consumer POM trong Maven 4

## 1. Tổng quan và mục tiêu

POM vốn phục vụ hai nhóm người dùng. **Producer** cần các cấu hình để compile, test, đóng gói và publish artifact. **Consumer** cần tọa độ và metadata về dependencies để Maven hoặc công cụ khác resolve artifact đã phát hành. Với Maven 3, hai nhiệm vụ đó thường nằm trong cùng file `pom.xml` được copy vào repository. Vì Maven Central, IDE, Gradle và scanners đều đã quen POM model `4.0.0`, thay đổi schema trực tiếp có thể phá tương thích.

**Maven 4 phân biệt:**
- **Build POM:** `pom.xml` trong source control, chứa build logic; có thể dùng model `4.1.0`.
- **Consumer POM:** POM Maven4 sinh khi `install` hoặc `deploy`, được lưu theo tên `artifactId-version.pom` và thường dùng model `4.0.0` để Maven3 consumers đọc được.
- **Attached Build POM:** full Build POM được lưu kèm cùng artifact với classifier `build`, tên thường là `artifactId-version-build.pom`.

```text
Source: producer/pom.xml          Build POM model 4.1.0
              |
           Maven 4
              |
              +-- greeting-lib-1.0.0.jar
              +-- greeting-lib-1.0.0.pom           consumer POM
              +-- greeting-lib-1.0.0-build.pom     attached Build POM
                              |
                Maven 3 consumer project
                              |
                   reads normal consumer POM
                              |
                  resolves transitive dependencies
```

**Lưu ý tính thời điểm:** Tính đến ngày **10/11/2026**, [Maven Releases History](https://maven.apache.org/docs/history.html) liệt kê Maven **4.0.0-rc-7** (24/09/2026), **chưa GA**. Các mô tả dưới đây bám RC-7 và cập nhật đầu tháng 11/2026 của [What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html). Trước khi nâng lên RC/GA tiếp theo, phải kiểm actual behavior, không lấy mặc định từ một bài viết cũ.

**Điểm quan trọng nhất:** trong RC-7, consumer POM feature mặc định bật nhưng **flatten mặc định tắt**. Không còn chính xác nếu nói mọi consumer POM Maven4 mặc định loại bỏ parent, build, properties và non-transitive scopes.

## 2. Ba loại model dễ bị nhầm

| Loại | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| Build POM | `pom.xml` nguồn trong Git | Mô tả build producer |
| Effective POM | Maven tính từ source, parent, profiles, settings | Model thực tế của một invocation |
| Consumer POM | Normal `greeting-lib-1.0.0.pom` trong local/remote repo | Cho downstream dependency resolution |
| Attached Build POM | `greeting-lib-1.0.0-build.pom` | Lưu full build definition cùng release |

**Effective POM không đồng nghĩa consumer POM**. `mvn help:effective-pom` hữu ích để debug inheritance/profile/plugin configuration nhưng không bảo đảm xuất đúng XML mà Maven4 đã install/deploy cho consumers.

**File classifier build không phải version khác**. Với GAV `dev.training.maven4:greeting-lib:1.0.0`, cả normal consumer POM và `-build.pom` cùng thuộc release 1.0.0. Maven3 consumer bình thường phải đọc normal `.pom`, không tự chọn classifier build.

### 2.1. Build POM chứa những gì?

Ngoài GAV và packaging:
- Parent POM, subprojects, dependencyManagement/BOM imports.
- Dependencies `compile`, `runtime`, `provided`, `test`.
- Compiler/test/package plugins và executions.
- Build profiles, resources, source directories, testing/release policy.
- Maven4 model4.1.0 elements, root info và version inference.

Một header Build POM Maven4:

```xml
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd"
         root="true">
    <modelVersion>4.1.0</modelVersion>
    <groupId>dev.training.maven4</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
</project>
```

Đây là POM tối giản minh họa model, chưa khai báo code/tests. Lab phần 7 có POM đầy đủ.

### 2.2. Model4.1.0 có bắt buộc cho mọi Maven4 project?

**Không.** Maven4 vẫn build source POM model `4.0.0`. Model4.1.0 hữu ích khi muốn dùng features chỉ có trong Maven4. Maven3 **không build trực tiếp source model4.1.0**, nhưng có thể consume JAR nếu Maven4 tạo normal consumer POM model4.0.0 hợp lệ. Đó chính là mục đích tách Build và Consumer.

## 3. Hành vi Maven 4.0.0-rc-7 theo hai modes

Các properties từ [Maven4 RC-7 Configuration Options](https://maven.apache.org/ref/4.0.0-rc-7/configuration.html):

```properties
maven.consumer.pom=true
maven.consumer.pom.flatten=false
```

### 3.1. Default: flatten=false

Khi build/install với Maven4:

```bash
mvn -B -ntp clean install -Dmaven.consumer.pom.flatten=false
```

Consumer POM normal ở RC-7:
- Thường dùng model `4.0.0`.
- **Giữ** `<parent>` reference nếu có.
- **Giữ** `<properties>` và `<build>`/plugin configuration.
- **Giữ** dependency declarations của producer, kể cả `provided` và `test`.
- Có file Build POM attached với classifier `build`.

Một nuance không được bỏ qua: **giữ một dependency declaration không có nghĩa scope đó transitive vào runtime của consumer**. Maven3 vẫn áp quy tắc scopes: producer test dependency không tự thành test dependency của consumer; producer provided không tự trở thành runtime transitive.

### 3.2. Opt-in: flatten=true

Chạy Maven4:

```bash
mvn -B -ntp clean install -Dmaven.consumer.pom.flatten=true
```

Khi bật flatten, consumer POM của JAR được chuyển để thuận tiện cho downstream:
- Parent inheritance được resolve/inline; bỏ direct parent reference khi đã flatten.
- Build-only `<build>`/`<properties>` được loại.
- BOM imports và dependency management được xử lý theo flatten policy.
- Chỉ giữ direct dependencies có scope transitive `compile`/`runtime`.
- Bỏ declarations với `provided`/`test`/`system` của JAR consumer.
- Managed dependencies không dùng có thể bị loại theo setting mặc định.
- **Vẫn attach full Build POM** dưới classifier `build`.

**Không khẳng định flatten chỉ là xóa XML tags**: Maven cần materialize đủ tọa độ/version/inherited metadata để consumer không mất thông tin cần dùng. Đừng đoán rằng tất cả transitive artifacts sẽ được copy thành direct dependencies; hãy kiểm XML thực tế.

### 3.3. So sánh nhanh

| Metadata | Build POM | Default consumer RC-7 | Flatten=true consumer |
| --- | --- | --- | --- |
| Model4.1.0 | Có thể | Thường model4.0.0 | Thường model4.0.0 |
| GAV/dependencies compile/runtime | Có | Có | Có |
| Provided/test declarations | Có | **Giữ** | **Bỏ** cho JAR consumer |
| Parent reference | Có nếu dùng parent | **Giữ** | Inline/loại direct reference |
| `<properties>` | Có | **Giữ** | Loại build-only |
| `<build>` | Có | **Giữ** | Loại build-only |
| Build POM classifier | Gốc | **Attach** | **Attach** |

Cần đọc bảng cùng lưu ý: **parent và BOM POM có packaging `pom` hoặc `bom`, không nên áp máy móc hành vi của JAR consumer**. Parent POM dùng để truyền build/properties, BOM dùng dependencyManagement. Với profiles phức tạp, Maven4 có thể cảnh báo nếu không thể biểu diễn tất cả nội dung trong consumer model4.0.0.

### 3.4. Chọn policy bằng user property

Maven4 hỗ trợ cấu hình per-reactor trong:

```text
.mvn/maven-user.properties
```

Nếu tổ chức muốn bật flatten cho release, file có thể chứa:

```properties
maven.consumer.pom.flatten=true
```

Vì property này làm thay đổi **published metadata**, cần review như release policy. Trong lab, dùng CLI `-Dmaven.consumer.pom.flatten=true/false` để dễ so sánh. Không đưa secrets vào project properties.

## 4. Maven4 Build POM: những tính năng model4.1.0

### 4.1. Root directory

Root project có thể khai báo `root="true"` ở `<project>`. Maven4 thêm các root properties:
- `${project.rootDirectory}`: root gắn với project.
- `${session.rootDirectory}`: root của current session khi xác định được.
- `${session.topDirectory}`: top directory của invocation/`--file`.
- `${basedir}`: directory của POM project hiện hành.

Đừng nhầm root project và basedir của child subproject. Với project muốn giữ Maven3-compatible model, một thư mục `.mvn` ở root vẫn giúp xác định root theo cách cũ.

### 4.2. `<subprojects>` thay `<modules>`

Maven4 model4.1.0:

```xml
<subprojects>
    <subproject>core</subproject>
    <subproject>app</subproject>
</subprojects>
```

Maven3 model4.0.0:

```xml
<modules>
    <module>core</module>
    <module>app</module>
</modules>
```

Maven4 dùng từ subproject để tránh nhầm với Java Platform Module System. Cú pháp `<modules>` vẫn có thể được hỗ trợ nhưng deprecated trong model4.1.0.

### 4.3. Parent inference

Child model4.1 có thể dùng:

```xml
<parent/>
```

hoặc:

```xml
<parent>
    <relativePath>..</relativePath>
</parent>
```

Maven4 suy parent coordinates từ POM ở directory trên. Đây là **snippets**, không phải complete child POM runnable khi thiếu parent. Maven3 source build không hỗ trợ shorthand theo cùng cách. RC-7 còn chấp nhận một số shorthand trong source model4.0.0, nhưng **version inference của dependencies lên sibling subprojects vẫn cần model4.1.0**.

### 4.4. Dependency version inference

Trong cùng build reactor model4.1.0, project app có thể phụ thuộc subproject core mà không ghi version:

```xml
<dependency>
    <groupId>dev.training.maven4</groupId>
    <artifactId>core</artifactId>
</dependency>
```

Điều này **không cho phép bỏ version cho mọi external dependency**. Maven chỉ infer khi biết project cùng build; consumer POM đã publish cần có version resolvable cho Maven3.

### 4.5. Parent POM và BOM

Parent `packaging=pom` truyền inheritance, plugin config và dependencyManagement. Nếu default consumer POM của child giữ `<parent>`, parent artifact phải được publish/resolve được. Nếu consumer không có quyền truy cập private parent, build có thể fail dù child JAR đã có. Với flatten=true, consumer JAR POM có thể inline parent info để giảm phụ thuộc vào parent.

Maven4 model4.1.0 thêm `<packaging>bom</packaging>` cho Bill of Materials. BOM consumer cần giữ managed versions có ý nghĩa; không áp quy tắc “loại toàn bộ build/properties/dependencyManagement” của JAR vào mọi BOM/parent. Apache cảnh báo về imported BOM cùng reactor; nên import BOM đã được publish từ repository.

## 5. Dependency scopes và CI-friendly versions

Giả sử Build POM khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
        <scope>compile</scope>
    </dependency>
    <dependency>
        <groupId>javax.annotation</groupId>
        <artifactId>javax.annotation-api</artifactId>
        <version>1.3.2</version>
        <scope>provided</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Khi default flatten=false, normal consumer POM có thể giữ cả ba declarations. **Compile** là transitive; **provided** không tự thành runtime dependency; **test** của producer không tự thành test dependency consumer. Khi flatten=true, consumer JAR POM dự kiến chỉ giữ Commons Lang compile.

Maven4 cũng cải thiện support version placeholders như `${revision}` trong multi-project builds. Ví dụ fragment (không phải POM đầy đủ):

```xml
<version>${revision}</version>
<properties>
    <revision>1.0.0-SNAPSHOT</revision>
</properties>
```

Khi publish, kiểm consumer POM có version đã được resolve hợp lệ, không còn unresolved placeholder. Một published release POM sai phải được sửa bằng **release version mới**, không overwrite POM cùng GAV đã public.

## 6. Quy trình migration an toàn

Theo [Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html):

1. **Prepare trên Maven3:** nâng plugins được hỗ trợ, ghim versions, dọn warnings, provision Java17.
2. **Test Maven4:** giữ source model4.0.0, chạy song song Maven3/Maven4 trên CI để so tests, dependency graph và artifact outputs.
3. **Migrate model:** sau khi builds đạt, thêm model4.1.0/root/subprojects/inference, quyết định flatten policy rồi test consumer bằng Maven3 thật.

Maven4 **cần JDK17 để chạy Maven process**, không có nghĩa mọi artifact Java phải target17. Compiler `release` và Toolchains có thể cấu hình Java target riêng. Bài lab chọn Java17 cả runtime và target.

Maven4 cũng thay defaults `installAtEnd`/`deployAtEnd` thành true theo migration guide; việc hoãn install/deploy không biến release upload thành transaction atomically. Pipeline thật cần staging, tests, signing, approval và immutable repository policy.

## 7. Lab Java17: Maven4 producer và Maven3 consumer

Mục đích: build thư viện với source POM4.1.0 bằng Maven4, cài thư viện vào local repository, cho Maven3 consumer đọc normal POM4.0.0, kiểm generated POM ở hai modes.

Cây file:

```text
maven4-pom-lab/
├── producer/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/training/maven4/GreetingLibrary.java
│       └── test/java/dev/training/maven4/GreetingLibraryTest.java
└── consumer/
    ├── pom.xml
    └── src/
        ├── main/java/dev/training/demo/GreetingApp.java
        └── test/java/dev/training/demo/GreetingAppTest.java
```

Cần JDK17+, Maven4.0.0-rc-7, Maven3.9.x, approved Maven repository hoặc local cache chứa plugins/JUnit/Commons Lang và local Maven repository dùng chung. **Không có deployment lên Central/Nexus**, lab chỉ chạy `install` local.

### 7.1. Tạo folders

Linux/macOS:

```bash
mkdir -p maven4-pom-lab/producer/src/main/java/dev/training/maven4
mkdir -p maven4-pom-lab/producer/src/test/java/dev/training/maven4
mkdir -p maven4-pom-lab/consumer/src/main/java/dev/training/demo
mkdir -p maven4-pom-lab/consumer/src/test/java/dev/training/demo
cd maven4-pom-lab
```

Windows PowerShell có thể dùng `New-Item -ItemType Directory -Force -Path` cho bốn paths trên rồi `Set-Location maven4-pom-lab`. Từ đây mọi lệnh dùng `-f producer/pom.xml` hoặc `-f consumer/pom.xml` từ root.

### 7.2. `producer/pom.xml`: Maven4 Build POM đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.1.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.1.0
                             https://maven.apache.org/xsd/maven-4.1.0.xsd"
         root="true">
    <modelVersion>4.1.0</modelVersion>
    <groupId>dev.training.maven4</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
        <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
        <training.build.marker>INTERNAL-BUILD-METADATA</training.build.marker>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
            <scope>compile</scope>
        </dependency>
        <dependency>
            <groupId>javax.annotation</groupId>
            <artifactId>javax.annotation-api</artifactId>
            <version>1.3.2</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`commons-lang3` compile dùng trong code; `javax.annotation-api` provided cho annotation, JUnit test scope. Property `training.build.marker` giúp quan sát default consumer POM giữ properties còn flattened POM loại build-only properties. `outputTimestamp` hỗ trợ archive timestamp reproducibility nhưng không bảo đảm toàn bộ JAR hash identical trên mọi JDK/OS. Không có `distributionManagement` nên lab không deploy.

### 7.3. `GreetingLibrary.java`

Tệp `producer/src/main/java/dev/training/maven4/GreetingLibrary.java`:

```java
package dev.training.maven4;

import javax.annotation.Generated;
import org.apache.commons.lang3.StringUtils;

@Generated("maven4-pom-lab")
public final class GreetingLibrary {

    private GreetingLibrary() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        String normalized = StringUtils.capitalize(name.strip());
        return "Hello, " + normalized + "!";
    }
}
```

`StringUtils.capitalize` đến từ Commons Lang compile dependency, cần khi consumer gọi API runtime. `@Generated` là annotation dùng compile; provided dependency không cần truyền sang runtime consumer.

### 7.4. `GreetingLibraryTest.java`

Tệp `producer/src/test/java/dev/training/maven4/GreetingLibraryTest.java`:

```java
package dev.training.maven4;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingLibraryTest {

    @Test
    void trimsAndCapitalizes() {
        assertEquals(
            "Hello, Maven 4!",
            GreetingLibrary.greet("  maven 4  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingLibrary.greet("   "));
    }

    @Test
    void rejectsNullName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingLibrary.greet(null));
    }
}
```

Producer có **3 JUnit Jupiter unit tests**. Tests này kiểm logic, chưa kiểm generated consumer POM; phần inspect/consumer Maven3 mới xác minh metadata.

### 7.5. `consumer/pom.xml`: Maven3 source model4.0.0

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.training.demo</groupId>
    <artifactId>maven3-greeting-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.training.maven4</groupId>
            <artifactId>greeting-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
                <configuration>
                    <mainClass>dev.training.demo.GreetingApp</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Consumer không khai báo Commons Lang trực tiếp; nó phải nhận compile dependency này transitively từ producer consumer POM. Consumer khai báo JUnit riêng: test dependencies producer không tự truyền cho consumer.

### 7.6. `GreetingApp.java`

Tệp `consumer/src/main/java/dev/training/demo/GreetingApp.java`:

```java
package dev.training.demo;

import dev.training.maven4.GreetingLibrary;

public final class GreetingApp {

    private GreetingApp() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingLibrary.greet("maven 4"));
    }
}
```

**Java stdout chính xác:**

```text
Hello, Maven 4!
```

Đây là stdout từ Java `System.out.println`; Maven Exec Plugin có thể thêm INFO/banners/logs quanh nó.

### 7.7. `GreetingAppTest.java`

Tệp `consumer/src/test/java/dev/training/demo/GreetingAppTest.java`:

```java
package dev.training.demo;

import dev.training.maven4.GreetingLibrary;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingAppTest {

    @Test
    void usesPublishedLibrary() {
        assertEquals(
            "Hello, Maven 4!",
            GreetingLibrary.greet("maven 4"));
    }
}
```

Consumer có **1 JUnit test**, tổng lab **3 + 1 = 4 tests**.

## 8. Chạy lab và kiểm POM được install

### 8.1. Sử dụng hai Maven versions thực

Giả sử môi trường có `MAVEN4_HOME` và `MAVEN3_HOME` là các installations được quản trị.

Linux/macOS:

```bash
"$MAVEN4_HOME/bin/mvn" --version
"$MAVEN3_HOME/bin/mvn" --version
java -version
```

PowerShell, viết mỗi lệnh **một dòng**:

```powershell
& "$env:MAVEN4_HOME\bin\mvn.cmd" --version
& "$env:MAVEN3_HOME\bin\mvn.cmd" --version
java -version
```

Đây là các environment variables phải được cung cấp, không phải Maven tự tạo. Có thể thay bằng hai terminal PATH khác nhau, miễn xác nhận `mvn --version` lần lượt là Maven4 RC-7 và Maven3.9.x. Maven3 **không dùng để build producer model4.1.0**.

### 8.2. Build producer với flatten=false

Linux/macOS:

```bash
"$MAVEN4_HOME/bin/mvn" -B -ntp -f producer/pom.xml clean install -Dmaven.consumer.pom.flatten=false
```

PowerShell:

```powershell
& "$env:MAVEN4_HOME\bin\mvn.cmd" -B -ntp -f producer/pom.xml clean install -Dmaven.consumer.pom.flatten=false
```

Nếu dependencies/plugins/JDK hợp lệ: build và **3 tests pass**, library JAR/POMs được install vào local Maven repository. Surefire summary dự kiến:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây chỉ là test count, không phải full Maven console. Đừng dùng `-DskipTests` hoặc `-fn` để tạo false-positive build.

### 8.3. Inspect files

Với local repository mặc định:

```text
~/.m2/repository/dev/training/maven4/greeting-lib/1.0.0/
    greeting-lib-1.0.0.jar
    greeting-lib-1.0.0.pom
    greeting-lib-1.0.0-build.pom
```

Linux/macOS:

```bash
ls -l "$HOME/.m2/repository/dev/training/maven4/greeting-lib/1.0.0"
grep -n -E "modelVersion|training.build.marker|commons-lang3|javax.annotation-api|junit-jupiter" "$HOME/.m2/repository/dev/training/maven4/greeting-lib/1.0.0/greeting-lib-1.0.0.pom"
```

PowerShell:

```powershell
$dir = Join-Path $HOME ".m2/repository/dev/training/maven4/greeting-lib/1.0.0"
Get-ChildItem -LiteralPath $dir
Select-String -Path (Join-Path $dir "greeting-lib-1.0.0.pom") -Pattern "modelVersion|training.build.marker|commons-lang3|javax.annotation-api|junit-jupiter"
```

Nếu user settings chỉ định local Maven repository khác, dùng path thực. Normal POM default RC-7 dự kiến có model4.0.0, vẫn giữ `<build>`/`<properties>` và provided/test declarations; attached `-build.pom` chứa full Build POM model4.1.0. Lệnh grep chỉ để tìm nhanh, khi cần chính xác parse XML structure.

### 8.4. Chạy Maven3 consumer

Linux/macOS:

```bash
"$MAVEN3_HOME/bin/mvn" -B -ntp -f consumer/pom.xml clean verify
"$MAVEN3_HOME/bin/mvn" -B -ntp -f consumer/pom.xml org.codehaus.mojo:exec-maven-plugin:3.6.2:java
```

PowerShell:

```powershell
& "$env:MAVEN3_HOME\bin\mvn.cmd" -B -ntp -f consumer/pom.xml clean verify
& "$env:MAVEN3_HOME\bin\mvn.cmd" -B -ntp -f consumer/pom.xml org.codehaus.mojo:exec-maven-plugin:3.6.2:java
```

Kết quả dự kiến:
- Maven3 đọc consumer POM model4.0.0, không phải Build POM4.1.0.
- Maven3 kéo Commons Lang transitively, compile/test consumer.
- **1 consumer test pass**.
- Java app in `Hello, Maven 4!`.

Không dùng `java -jar consumer/target/...jar` khi chưa cấu hình executable manifest/fat JAR; Exec Plugin chạy Java với resolved dependency classpath.

### 8.5. Snapshot và so flattened output

**Trước khi bật flatten**, copy normal consumer POM default:

```bash
mkdir -p pom-snapshots
cp "$HOME/.m2/repository/dev/training/maven4/greeting-lib/1.0.0/greeting-lib-1.0.0.pom" pom-snapshots/consumer-default.pom
```

Sau đó Maven4:

```bash
"$MAVEN4_HOME/bin/mvn" -B -ntp -f producer/pom.xml clean install -Dmaven.consumer.pom.flatten=true
```

PowerShell:

```powershell
& "$env:MAVEN4_HOME\bin\mvn.cmd" -B -ntp -f producer/pom.xml clean install -Dmaven.consumer.pom.flatten=true
```

Lưu normal POM flattened và diff:

```bash
cp "$HOME/.m2/repository/dev/training/maven4/greeting-lib/1.0.0/greeting-lib-1.0.0.pom" pom-snapshots/consumer-flattened.pom
diff -u pom-snapshots/consumer-default.pom pom-snapshots/consumer-flattened.pom
```

PowerShell có thể dùng `Copy-Item` và `Compare-Object` tương tự. **Hai lần install chỉ là test local**, có thể thay file normal POM local cùng GAV. **Không deploy lại remote release 1.0.0** để đổi flatten setting; remote releases phải immutable, cần version mới.

Khi flatten=true, normal consumer POM nên giữ compile `commons-lang3` nhưng bỏ provided/test declarations, `<build>` và build-only `<properties>`. Attached Build POM vẫn có full build metadata. Chạy lại Maven3 consumer để chứng minh không mất transitive compile dependency.

### 8.6. Maven3 dependency graph

```bash
"$MAVEN3_HOME/bin/mvn" -B -ntp -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.9.0:tree
```

Kiểm producer GAV và `commons-lang3:3.14.0`. Không coi test/provided declarations của producer là runtime transitive. Logs Maven khác nhau tùy version/config; không bịa full output.

## 9. Những trường hợp khó hơn lab

### 9.1. Parent/source inference

Multi-project root có thể dùng:

```xml
<project xmlns="http://maven.apache.org/POM/4.1.0"
         root="true">
    <modelVersion>4.1.0</modelVersion>
    <groupId>dev.training.maven4</groupId>
    <artifactId>build-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <subprojects>
        <subproject>greeting-lib</subproject>
    </subprojects>
</project>
```

Child snippet:

```xml
<project xmlns="http://maven.apache.org/POM/4.1.0">
    <modelVersion>4.1.0</modelVersion>
    <artifactId>greeting-lib</artifactId>
    <parent/>
</project>
```

Hai snippets **không tạo project runnable đầy đủ**; còn thiếu source, plugins và namespace/other build declarations khi áp vào hệ thống thật. Default consumer POM của child có thể giữ parent GAV và parent phải publish; flatten consumer JAR có thể inline parent metadata, nhưng parent POM `packaging=pom` vẫn cần cho consumer khác thực sự dùng inheritance.

### 9.2. Profiles phức tạp

Một condition-based profile có thể không chuyển hoàn toàn sang consumer model4.0.0. Maven có thể cảnh báo và tạo consumer POM ở model khác trong tình huống hiếm. Không hứa mọi Maven4 POM luôn tương thích Maven3 chỉ vì version tag. **Kiểm normal POM và build downstream Maven3 thực tế**.

### 9.3. Security/release provenance

Normal consumer POM, attached Build POM, JAR, signatures, checksums đều thuộc release. Attached Build POM có thể chứa internal URLs/config; review trước public publication. Không commit credentials/secrets. Pin Maven/plugins, kiểm source commit/CI build ID, parent/BOM sources và hashes. **Không overwrite cùng GAV** để sửa consumer metadata sau release; phát hành version mới và thông báo consumers.

## 10. Troubleshooting

| Lỗi hoặc hiện tượng | Vì sao | Hướng xử lý |
| --- | --- | --- |
| Maven3 không parse POM4.1 | Đang đọc source Build POM | Publish consumer POM4.0 từ Maven4 |
| Normal POM còn `<build>` | RC-7 default flatten=false | Đúng mặc định; bật true nếu cần |
| Provided/test còn trong POM | Default giữ declarations | Không đồng nghĩa transitive runtime |
| `-build.pom` tồn tại cả hai modes | RC-7 attach Build POM | Đúng design |
| Maven3 không resolve parent | Parent chưa publish hoặc thiếu quyền | Publish parent hoặc flatten child |
| Maven3 consumer thiếu Commons Lang | Consumer graph/metadata sai | Inspect POM và dependency tree |
| JDK11 không chạy Maven4 | Maven4 yêu cầu Java17+ | Provision JDK17 |
| Consumer build bằng Maven4 pass nhưng Maven3 fail | Chưa kiểm backward compatibility | Chạy Maven3 consumer riêng |
| `<parent/>` fail trong Maven3 | Maven4 inference feature | Build source Maven4; publish normal consumer |
| BOM import fail | BOM chưa publish hoặc scopes/management sai | Test BOM consumer, kiểm repository |
| `${revision}` unresolved | POM publication chưa đúng | Kiểm normal POM/version |
| Flatten đổi published metadata | Release GAV immutable | Dùng version mới, không redeploy |

## 11. Câu hỏi và đáp án

**1.** Build POM phục vụ ai? — Producer khi xây artifact.
**2.** Consumer POM phục vụ ai? — Downstream để resolve artifact và dependency graph.
**3.** Maven4 có bắt buộc model4.1.0? — Không, model4.0.0 còn hỗ trợ.
**4.** Maven3 build source model4.1.0 được không? — Không theo design.
**5.** Normal consumer POM thường model nào? — 4.0.0.
**6.** RC-7 default flatten là gì? — False.
**7.** RC-7 default giữ parent/properties/build? — Có.
**8.** Default giữ provided/test declarations? — Có.
**9.** Provided/test vì còn trong XML có thành runtime transitive? — Không.
**10.** Bật flatten thế nào? — `-Dmaven.consumer.pom.flatten=true`.
**11.** Flatten JAR consumer giữ scopes nào? — Compile/runtime.
**12.** Flatten có xóa attached Build POM không? — Không ở RC-7.
**13.** `-build.pom` là version mới? — Không, classifier build.
**14.** Effective POM là consumer POM? — Không.
**15.** Maven4 cần JDK bao nhiêu? — Java17 trở lên.
**16.** Lab producer có mấy tests? — Ba.
**17.** Lab consumer có mấy tests? — Một.
**18.** Java main in gì? — `Hello, Maven 4!`.
**19.** Commons Lang là dependency scope gì? — Compile.
**20.** Consumer có nhận producer JUnit test transitively? — Không.
**21.** Parent POM mặc định còn reference thì cần gì? — Parent resolvable.
**22.** Đổi flatten mode có được deploy lại cùng release GAV? — Không, phải dùng version mới.

## 12. Checklist áp dụng

- [ ] Maven4 version/RC/GA được ghim; CI có Java17+.
- [ ] Build POM model4.0.0 hoặc 4.1.0 được chọn có chủ đích.
- [ ] Source model4.1.0 chỉ được build với Maven4.
- [ ] Consumer POM generation và flatten policy explicit.
- [ ] Không áp tài liệu pre-RC7 cho default RC-7.
- [ ] Normal consumer POM model4.0.0 khi có thể.
- [ ] Attached `-build.pom` được kiểm.
- [ ] Parent POM được publish khi default consumer cần.
- [ ] BOM/dependencyManagement được test downstream.
- [ ] Compile/runtime scopes được giữ đúng, provided/test không bị hiểu sai.
- [ ] Không có unresolved `${revision}`.
- [ ] Maven3 consumer project đã `clean verify` và runtime test.
- [ ] Compiler, Surefire và package plugin versions được ghim.
- [ ] Source/commit, JDK, Maven versions và property flags được ghi vào release record.
- [ ] Không đưa credentials vào POM hoặc attached Build POM.
- [ ] Không deploy lại cùng GAV sau khi publish.
- [ ] Test lại khi Maven4 nâng RC/GA.

## 13. Tài liệu chính thức

- [Apache Maven — What's new in Maven 4?](https://maven.apache.org/whatsnewinmaven4.html): Build/consumer POM, RC-7 default và flatten.
- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html): migration, Java17, parent/BOM.
- [Apache Maven — Release History](https://maven.apache.org/docs/history.html): version/date.
- [Apache Maven 4.0.0-rc-7 Release Notes](https://maven.apache.org/docs/4.0.0-rc-7/release-notes.html): RC compatibility.
- [Apache Maven4 Configuration Options](https://maven.apache.org/ref/4.0.0-rc-7/configuration.html): consumer POM properties.
- [Apache Maven POM Reference](https://maven.apache.org/pom.html): scopes, inheritance, parent.
- [Apache Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies.
- [Apache Maven Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): artifact/POM resolution.
- [Apache Maven4 POM XSD](https://maven.apache.org/xsd/maven-4.1.0.xsd): build schema.
- [Apache Maven3 POM XSD](https://maven.apache.org/xsd/maven-4.0.0.xsd): consumer schema.
- [MojoHaus Exec Plugin](https://www.mojohaus.org/exec-maven-plugin/usage.html): chạy ứng dụng với resolved classpath.
