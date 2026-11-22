# Maven Versions Plugin và kiểm tra bản cập nhật có sẵn

Trong dự án Maven, phiên bản của dependencies, build plugins, parent POM và các thuộc tính dùng để quản lý version thường được ghi trực tiếp trong `pom.xml`. Theo thời gian, Maven repository có thể xuất hiện những bản phát hành mới. Việc **phát hiện bản cập nhật** là một nhiệm vụ khác với **thực sự nâng cấp và kiểm thử**.

**Versions Maven Plugin** của MojoHaus (`org.codehaus.mojo:versions-maven-plugin`) hỗ trợ cả hai công việc: kiểm tra phiên bản mới có sẵn (*display/report goals*) và chỉnh sửa version trong POM (*update/set/use goals*). Trọng tâm của bài này là **kiểm tra một cách an toàn, giải thích kết quả đúng và quyết định có nên nâng cấp hay không**.

Các câu hỏi thực tế:
- Dependency `commons-lang3` đang dùng bản nào, repository có bản nào mới hơn?
- Version `junit.version` được khai báo bằng Maven property, phải xem báo cáo nào?
- Maven Compiler/Surefire/Checkstyle plugin đang dùng có bản phát hành mới phù hợp với Maven/JDK hiện tại không?
- Parent POM, imported BOM và các module reactor nên được xem xét như thế nào?
- Vì sao “bản mới nhất” chưa chắc là bản ổn định hoặc tương thích?
- Làm sao lọc pre-release, hạn chế major updates, lưu kết quả CI, và nâng cấp từng bước mà không làm mất khả năng rollback?

**Nguyên tắc cơ bản:** các goal tên `display-*` ở dưới **không chỉnh sửa source `pom.xml`**. Chúng có thể đọc/download metadata, làm thay đổi local Maven cache hoặc ghi **file báo cáo** nếu bạn chỉ định `outputFile`, nhưng không tự chuyển version trong POM. Ngược lại, `versions:update-properties`, `versions:use-latest-releases`, `versions:set-property`, `versions:set` và nhiều goal khác **có thể sửa POM**.

Bài thực hành sử dụng **Java 17**, **Maven 3.9+** và **Versions Maven Plugin 2.22.0** được ghim để ví dụ có tính tái lập. Theo bảng tương thích chính thức, Versions Plugin **2.22.0** có yêu cầu tối thiểu **Maven 3.6.3 và JDK 8**, vì vậy bộ JDK 17/Maven 3.9 thỏa điều kiện. **2.22.0 là version minh họa đã được công bố, không phải tuyên bố về version mới nhất hôm nay.** Các version “có thể nâng cấp” trong phần output luôn phụ thuộc thời điểm, repository, mirror và chính sách lọc.

## 1. Phiên bản nào xuất hiện trong một POM?

Một project có thể quản lý nhiều loại version, không chỉ một con số `<version>`.

| Vị trí | Ví dụ | Ý nghĩa | Goal kiểm tra phù hợp |
| --- | --- | --- | --- |
| `<dependencies>` | `commons-lang3:3.12.0` | Thư viện dự án sử dụng | `display-dependency-updates` |
| `<dependencyManagement>` | `junit-bom:5.10.2` | Phiên bản do BOM/parent quản lý | `display-dependency-updates` và xem model |
| `<properties>` | `<junit.version>5.10.2</junit.version>` | Giá trị được tham chiếu bằng `${junit.version}` | `display-property-updates` |
| `<build><plugins>` | `maven-surefire-plugin:3.6.1` | Plugin phục vụ build | `display-plugin-updates` |
| `<build><pluginManagement>` | Compiler/Surefire version | Quản lý version plugin | `display-plugin-updates` / kiểm tra effective POM |
| `<parent>` | Corporate parent `1.4.0` | Project kế thừa mô hình cấu hình | `display-parent-updates` |
| `<build><extensions>` | Custom build extension | Mở rộng hành vi Maven build | `display-extension-updates` |
| Root project `<version>` | `1.0.0` | Version của **chính project** | Không đồng nghĩa một dependency update; dùng `versions:set` khi chủ ý đổi |

**Cần phân biệt:** Versions Plugin tìm **candidate versions** cho artifacts khai báo trong mô hình Maven. Nó **không phải** vulnerability scanner, không tự kiểm tra source API migration, không chứng minh tính tương thích binary, không xác nhận Docker image/npm dependency và không thay thế các công cụ như SBOM/SCA hay unit/integration tests.

### 1.1. Plugin groupId chính xác

Versions Maven Plugin có tọa độ:

```text
groupId:    org.codehaus.mojo
artifactId: versions-maven-plugin
version:    2.22.0 (version của bài thực hành)
```

Khác với những plugin thường có `org.apache.maven.plugins`, plugin này thuộc nhóm **MojoHaus**. Lệnh có thể viết ngắn `mvn versions:display-dependency-updates` khi prefix resolution đã được cấu hình/nhận diện, hoặc gọi bằng **fully qualified goal** để ghim chính xác artifact/version:

```bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates
```

Trong lab, `versions-maven-plugin` được khai báo rõ trong `<build><plugins>` với version 2.22.0 nên cả dạng rút gọn và đầy đủ đều có ý nghĩa rõ ràng.

### 1.2. “Available” không đồng nghĩa “nên dùng ngay”

“Có bản mới trong metadata” chỉ có nghĩa plugin tìm được một version candidate từ các Maven repositories được phép truy cập, với bộ quy tắc lọc đang dùng. Nó **không khẳng định**:
- Candidate version hỗ trợ Java 17 hoặc Maven 3.9.
- API vẫn tương thích với source project.
- License/security/behavior thỏa yêu cầu sản phẩm.
- Mọi transitive dependency đều tương thích.
- Artifact đã được mirror nội bộ đồng bộ.
- Project có tests bảo đảm nâng cấp an toàn.

Hãy đọc output dưới góc độ **danh sách việc cần đánh giá**, không phải lệnh “nâng tất cả lên latest”.

## 2. Bốn lệnh kiểm tra cốt lõi không sửa POM

### 2.1. Kiểm tra project dependencies

```bash
mvn -B -ntp versions:display-dependency-updates
```

Goal này hiển thị dependencies có newer versions theo mô hình Maven, bao gồm các khai báo liên quan đến dependency management và plugin dependency theo cấu hình/phiên bản. Khi dự án dùng BOM hoặc parent, cần kiểm tra **nguồn version được quản lý** trước khi chọn chỗ chỉnh.

Dạng ghim version:

```bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates
```

### 2.2. Kiểm tra Maven build plugins

```bash
mvn -B -ntp versions:display-plugin-updates
```

Goal này kiểm tra những plugins Maven được project sử dụng/quản lý, đồng thời cân nhắc Maven version prerequisites theo khả năng của plugin. Đừng đồng nhất với project dependency: Maven plugin chạy trong **build/plugin realm**, có yêu cầu Maven/JDK khác với library runtime.

Có thể kiểm tra những plugins không có explicit version trong POM nhưng được quản lý bởi parent/super POM với tham số của goal:

```bash
mvn -B -ntp versions:display-plugin-updates -DprocessUnboundPlugins=true
```

Không suy ra mọi plugin được liệt kê đều nên được ghim ngay vào POM; xem nó có thực sự tham gia lifecycle, tương thích build và có cần nâng cấp hay không.

### 2.3. Kiểm tra versions khai báo bằng properties

```bash
mvn -B -ntp versions:display-property-updates
```

Ví dụ source POM:

```xml
<properties>
    <commons.lang3.version>3.12.0</commons.lang3.version>
    <junit.jupiter.version>5.10.2</junit.jupiter.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>${commons.lang3.version}</version>
    </dependency>
</dependencies>
```

Đây chỉ là **POM snippet**, chưa phải project hoàn chỉnh. `display-property-updates` tìm những properties được liên kết với version của dependency/plugin. Nó không phải công cụ hiển thị “property nào cũng có update”; chẳng hạn `project.build.sourceEncoding=UTF-8` không phải version và không có version update để đề xuất.

Với property dùng cho nhiều artifacts, cần đánh giá khả năng **đồng bộ cả nhóm** (ví dụ các artifacts cùng BOM hoặc framework family), thay vì tự động tăng từng dependency độc lập.

### 2.4. Kiểm tra parent POM

```bash
mvn -B -ntp versions:display-parent-updates
```

Goal này hữu ích khi child có:

```xml
<parent>
    <groupId>dev.company.build</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.4.0</version>
</parent>
```

Đây là **snippet minh họa**, không phải parent tồn tại sẵn trong lab. Parent update có thể thay đổi dependencyManagement, pluginManagement, repositories, enforcer rules và quality gates trên **toàn bộ child projects**, nên cần test reactor trước khi áp dụng.

Lab phía dưới là project **không có parent khai báo tường minh**, vì vậy `display-parent-updates` không có parent update hữu ích để báo. Dùng nó trên project thực có `<parent>` khi cần.

### 2.5. Mở rộng: build extensions

```bash
mvn -B -ntp versions:display-extension-updates
```

Khi POM có `<build><extensions>` hoặc dùng core/build extensions phù hợp, goal giúp phát hiện phiên bản mới. Extension có thể tham gia rất sớm trong Maven bootstrap/model formation; luôn kiểm tra khả năng tương thích Maven version, plugin API và bootstrap sau update.

## 3. Chuẩn bị lab Java 17: source tree

Lab xây một ứng dụng Java dùng **Apache Commons Lang 3.12.0** và **JUnit Jupiter 5.10.2**. Các version được chọn làm điểm bắt đầu cho việc quan sát updates; **không khẳng định** đây là phiên bản mới nhất hoặc ít rủi ro nhất. JUnit được khai báo qua property để minh họa `display-property-updates`.

```text
versions-audit-lab/
├── pom.xml
└── src/
    ├── main/java/dev/training/versions/
    │   ├── TextBanner.java
    │   └── Main.java
    └── test/java/dev/training/versions/
        └── TextBannerTest.java
```

Yêu cầu:
- JDK 17+ với `java` và `javac`.
- Maven 3.9+.
- Có thể tải plugins/dependencies từ Maven Central hoặc mirror được phép.
- Có quyền đọc project và ghi thư mục `target`/local Maven cache.
- Trên CI, Maven repository/proxy và credentials phải được thiết lập hợp lệ; bài không cần thông tin đăng nhập thật.

Linux/macOS:

```bash
mkdir -p versions-audit-lab/src/main/java/dev/training/versions
mkdir -p versions-audit-lab/src/test/java/dev/training/versions
cd versions-audit-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "versions-audit-lab/src/main/java/dev/training/versions" | Out-Null
New-Item -ItemType Directory -Force -Path "versions-audit-lab/src/test/java/dev/training/versions" | Out-Null
Set-Location versions-audit-lab
```

Các lệnh Maven/Java ở những mục tiếp theo giả định bạn đứng **trong thư mục `versions-audit-lab`**.

## 4. POM hoàn chỉnh có Versions Maven Plugin

Tệp **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.versions</groupId>
    <artifactId>versions-audit-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <commons.lang3.version>3.12.0</commons.lang3.version>
        <junit.jupiter.version>5.10.2</junit.jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.lang3.version}</version>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>versions-maven-plugin</artifactId>
                <version>2.22.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Phân tích:
- `<packaging>jar</packaging>`: ứng dụng Java thông thường với compiler, test và JAR lifecycle.
- `maven.compiler.release=17`: sử dụng API/bytecode target Java 17.
- Hai properties `commons.lang3.version` và `junit.jupiter.version` **đang được dùng để xác định phiên bản thư viện**, nên Versions Plugin có thể liên kết chúng với artifacts.
- `junit-jupiter` thuộc `scope=test`, không cần cho Java main runtime.
- Compiler/Surefire/JAR/Dependency Plugins được ghim versions để baseline ổn định.
- Versions Plugin được khai báo version **nhưng không bind update goal vào lifecycle**. Đây là thực hành an toàn: `mvn verify` không tự sửa POM, và việc kiểm tra updates được gọi riêng khi cần.

**Không nên bind `versions:use-latest-releases` hoặc `versions:update-properties` trực tiếp vào phase `validate`/`compile`/`package` chỉ vì muốn luôn mới.** Nó sẽ làm mỗi build có khả năng sửa source POM và mất tính tái lập.

## 5. Java source đầy đủ

### 5.1. `TextBanner.java`

Tệp `src/main/java/dev/training/versions/TextBanner.java`:

```java
package dev.training.versions;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class TextBanner {

    private TextBanner() {
    }

    public static String message(String input) {
        if (StringUtils.isBlank(input)) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String cleaned = StringUtils.trim(input)
            .toLowerCase(Locale.ROOT);
        String capitalized = StringUtils.capitalize(cleaned);
        return "Hello, " + capitalized + "!";
    }
}
```

Đây là file Java 17 hoàn chỉnh. `StringUtils.isBlank` và `StringUtils.capitalize` thuộc Commons Lang, còn `Locale.ROOT` là API JDK tránh kết quả thay đổi theo system locale. Nếu `input` là `null` hoặc chỉ có khoảng trắng, chương trình ném `IllegalArgumentException`.

### 5.2. `Main.java`

Tệp `src/main/java/dev/training/versions/Main.java`:

```java
package dev.training.versions;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(TextBanner.message(" mAVEN "));
    }
}
```

Chạy trên Java 17 với Commons Lang đúng classpath, stdout dự kiến **chính xác một dòng**:

```text
Hello, Maven!
```

Không có log Maven khi chạy trực tiếp `Main.main` bằng Java launcher. Maven logs là đầu ra riêng của các lệnh `mvn`.

### 5.3. `TextBannerTest.java`

Tệp `src/test/java/dev/training/versions/TextBannerTest.java`:

```java
package dev.training.versions;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TextBannerTest {

    @Test
    void normalizesNameWithStableLocale() {
        assertEquals("Hello, Maven!",
            TextBanner.message(" mAVEN "));
    }

    @Test
    void rejectsWhitespaceOnlyInput() {
        assertThrows(IllegalArgumentException.class,
            () -> TextBanner.message("   "));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(IllegalArgumentException.class,
            () -> TextBanner.message(null));
    }
}
```

Đây là **3 JUnit Jupiter tests**. `TextBannerTest` khớp naming convention mặc định của Surefire. Một lần `mvn clean verify` với POM đã cho và dependencies được tải đúng sẽ chạy ba test methods này.

## 6. Xác minh build baseline trước khi xem updates

Trước mọi thay đổi version:

```bash
mvn -version
mvn -B -ntp clean verify
```

Quan sát:
1. `mvn -version` phải hiển thị Maven/JDK dự kiến.
2. Maven Compiler Plugin biên dịch `TextBanner` và `Main`.
3. Surefire chạy ba JUnit Jupiter tests.
4. Maven JAR Plugin đóng gói artifact `target/versions-audit-lab-1.0.0.jar`.
5. Build đạt `BUILD SUCCESS` nếu các giai đoạn đều thành công.

Một dòng thống kê **theo nội dung**, không phải toàn bộ stdout Maven:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Nếu baseline fail vì thiếu repository plugin hoặc test, **giải quyết trước**; không dùng phiên bản mới như một cách đoán mò “nâng rồi sẽ hết lỗi”.

### 6.1. Chạy Java main bằng runtime classpath đúng

Vì `TextBanner` sử dụng Commons Lang, chạy Java main cần cung cấp dependency JAR.

Copy runtime dependencies vào thư mục output:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies "-DincludeScope=runtime" "-DoutputDirectory=target/dependency"
```

Linux/macOS:

```bash
java -cp "target/classes:target/dependency/*" dev.training.versions.Main
```

Windows PowerShell:

```powershell
java -cp "target\classes;target\dependency\*" dev.training.versions.Main
```

**Stdout chính xác của Java application:**

```text
Hello, Maven!
```

Trên Linux/macOS dùng dấu hai chấm `:` giữa classpath entries; Windows dùng dấu chấm phẩy `;`. `target/dependency/*` là classpath wildcard được Java launcher hiểu để tìm JARs. Đây là khác nhau giữa **application runtime dependencies** và Maven build-plugin dependencies: không phải đưa `versions-maven-plugin` vào classpath ứng dụng.

### 6.2. Tùy chọn javac/java thủ công

Sau khi có `target/dependency/commons-lang3-3.12.0.jar`, có thể biên dịch main sources không cần Compiler Plugin:

Linux/macOS:

```bash
mkdir -p manual-classes
javac --release 17 -cp "target/dependency/*" -d manual-classes src/main/java/dev/training/versions/TextBanner.java src/main/java/dev/training/versions/Main.java
java -cp "manual-classes:target/dependency/*" dev.training.versions.Main
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path manual-classes | Out-Null
javac --release 17 -cp "target\dependency\*" -d manual-classes "src\main\java\dev\training\versions\TextBanner.java" "src\main\java\dev\training\versions\Main.java"
java -cp "manual-classes;target\dependency\*" dev.training.versions.Main
```

Output vẫn **`Hello, Maven!`**. Bài thực hành này cho thấy Versions Maven Plugin chỉ giúp phân tích **version artifacts** trong POM; Java compiler cần JAR thật trên classpath, không thể compile chỉ dựa trên báo cáo “có bản mới”.

## 7. Thực hành kiểm tra update cho dependencies

Từ root project `versions-audit-lab`:

```bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates
```

Goal có thể báo những updates cho Commons Lang hoặc JUnit. Không viết cố định “version mới nhất là X” vì con số thay đổi theo repository/time; nếu mirror nội bộ chỉ công bố một số versions, báo cáo có thể khác Maven Central.

Ví dụ **minh họa định dạng**, dùng những version đã tồn tại trong lịch sử, **không phải stdout thực tế của lần chạy hiện tại**:

```text
The following dependencies have newer versions:
  org.apache.commons:commons-lang3 ....... 3.12.0 -> 3.14.0
  org.junit.jupiter:junit-jupiter ......... 5.10.2 -> 5.11.4
```

Một lần chạy hiện tại có thể đề xuất **những bản cao hơn**, có thể phân thành mục direct dependencies và dependencyManagement; không nên so khớp nguyên văn đoạn minh họa để quyết định CI PASS/FAIL.

### 7.1. Vì sao không đồng nhất dependency update và transitive update?

POM khai báo trực tiếp `commons-lang3`, còn JUnit Jupiter kéo thêm transitive artifacts như API/engine/platform. Versions Plugin cung cấp các goal đánh giá project dependencies và management, **không phải công cụ tự cập nhật từng transitive JAR bất chấp version được quản lý bởi framework/BOM**.

Để xem effective dependency graph:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Một dependency tree hỗ trợ:
- Xem scope `compile`/`test`.
- Tìm artifact đến từ direct hay transitive dependency.
- Phát hiện version conflict/mediation sau nâng cấp.
- Hiểu một artifact bị BOM/parent quản lý hay không.

**Không nhầm:** `dependency:tree` mô tả phiên bản **đã resolve**, còn `display-dependency-updates` truy tìm **candidate updates**. Cả hai cần được dùng ở các thời điểm khác nhau.

### 7.2. So sánh trước và sau cập nhật

Một bảng có thể dùng trong pull request nâng cấp:

| Artifact | Version trước | Candidate | Lý do/nguồn | Kết quả kiểm thử |
| --- | --- | --- | --- | --- |
| `commons-lang3` | `3.12.0` | Version đã kiểm tra trong report | Bugfix/API compatibility/security review | Chưa chạy trước khi update |
| `junit-jupiter` | `5.10.2` | Version từ property report | Phù hợp Surefire/JUnit Platform | Chưa chạy trước khi update |
| `maven-compiler-plugin` | `3.14.1` | Version từ plugin report | Maven/JDK compatibility | Chưa chạy trước khi update |

“Candidate” không tự động là “approved”. Bảng này là khung đánh giá, **không phải báo cáo live hiện tại**.

## 8. Thực hành kiểm tra plugin updates

```bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-plugin-updates
```

Kiểm tra những plugins:
- Maven Compiler Plugin: cần đúng Maven + Java target.
- Maven Surefire Plugin: liên quan test engine, JUnit Platform, fork behavior.
- Maven JAR Plugin: liên quan archive content/manifest.
- Maven Dependency Plugin: ảnh hưởng các thao tác phân tích dependencies.
- Versions Maven Plugin: bản thân plugin cũng có thể có version mới hơn.

**Không phải mọi plugin đều độc lập về compatibility.** Ví dụ một bản plugin mới có thể yêu cầu Maven 3.9+ hoặc JDK version cao hơn. Goal `display-plugin-updates` có cơ chế xét Maven prerequisites, nhưng người nâng cấp vẫn cần đọc release notes và kiểm tra JDK requirements, API changes, cấu hình plugin và tests.

### 8.1. Parent và pluginManagement

Trong multi-module build, plugin versions thường được quản lý ở parent:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là **POM snippet**. Nếu child sử dụng Surefire qua lifecycle hoặc khai báo plugin, pluginManagement có thể cung cấp version/configuration. Tuy nhiên `pluginManagement` **không tự kích hoạt một custom plugin mới** chỉ bằng việc quản lý version.

Để đánh giá đúng:
1. Xem parent/pluginManagement nơi version được quản lý.
2. Xem child effective POM và plugin execution đang chạy.
3. Chạy display-plugin-updates trên module/parent phù hợp.
4. Nâng version tại nơi sở hữu contract.
5. Test toàn bộ reactor khi parent thay đổi.

### 8.2. “Newer” nhưng không tương thích JDK

Maven build plugins chạy bằng **JDK mà Maven đang sử dụng**, không chỉ `maven.compiler.release`. Nếu project target Java 17 nhưng Maven process dùng JDK 11, một plugin yêu cầu Java 17 có thể không chạy được, dù code dự kiến compile target 17. Vì vậy kiểm tra `mvn -version` trước, không chỉ đọc property `maven.compiler.release`.

## 9. Thực hành kiểm tra property-linked updates

Trong lab, hai properties:

```xml
<commons.lang3.version>3.12.0</commons.lang3.version>
<junit.jupiter.version>5.10.2</junit.jupiter.version>
```

được dùng bởi dependency versions. Chạy:

```bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-property-updates
```

Báo cáo có thể đề xuất version candidates cho những properties đó. Nếu không thấy property mà bạn nghĩ đang dùng:
- Nó có nằm trong `<properties>` của project hiện tại không?
- Dependency/plugin `<version>` có thật sự tham chiếu property không?
- Property được định nghĩa trong parent hoặc active profile khác?
- Version được quản lý qua BOM/dependencyManagement thay vì local property?
- Có filters hoặc ruleSet bỏ qua version candidates?
- Project module nào đang được dùng để chạy goal?

**Mẹo:** với một property không phải artifact version, như `project.build.sourceEncoding=UTF-8`, plugin không thể “tìm UTF-9” như một bản cập nhật version. Đây là phân biệt hữu ích giữa Maven configuration properties và properties dùng để pin dependency versions.

### 9.1. Một property dùng cho cả nhóm thư viện

Một hệ thống có:

```xml
<properties>
    <junit.version>5.10.2</junit.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-api</artifactId>
        <version>${junit.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter-engine</artifactId>
        <version>${junit.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **snippet** để dạy property version thống nhất, không yêu cầu copy thêm vào lab vốn đã có `junit-jupiter` aggregate artifact. Nếu hai dependencies có một property dùng chung, update property sẽ ảnh hưởng **cả hai**; nên test versions tương thích với nhau và xem framework compatibility guide.

Một BOM version cũng có thể là property, nhưng cập nhật BOM làm thay đổi nhiều artifacts được nó quản lý, nên phải review **effective dependency graph** sau update.

## 10. Parent POM, BOM và các version không viết trực tiếp ở dependency

### 10.1. Parent POM là một artifact đặc biệt

Ví dụ child có:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
</parent>
```

Đây là **snippet minh họa cấu trúc parent**, không bắt buộc cho lab. Parent upgrade có thể kéo thay đổi Java baseline, dependencies, plugin defaults, resources và test behavior. Không thay parent chỉ vì có version cao hơn; cần đọc migration guide/release notes tương ứng với framework đang dùng.

Kiểm tra:

```bash
mvn -B -ntp versions:display-parent-updates
```

Goal chỉ báo candidate; không sửa parent declaration.

### 10.2. Imported BOM là dependencyManagement, không phải parent

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.10.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **snippet** minh họa. BOM không được khai báo bằng `<parent>`. Nó quản lý versions cho các dependencies mà project sử dụng; **không tự thêm JUnit vào classpath**. Khi kiểm tra cập nhật:
- Xem `display-dependency-updates` và `dependencyManagement`.
- Nếu BOM version dùng property, xem `display-property-updates`.
- Review danh sách artifacts nhận version mới sau BOM upgrade.
- Không override từng transitive dependency nếu BOM đã quản lý phù hợp, trừ khi có lý do được kiểm chứng.

### 10.3. Dependency version không viết trong child POM

Child có thể dùng:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
```

Maven nhận version từ parent `dependencyManagement` hoặc imported BOM. Goal `display-dependency-updates` ở các phiên bản phù hợp có option `showVersionless` để hiển thị version-managed dependencies; với 2.22.0 option này có default **true** theo tài liệu goal. Hãy kiểm tra phiên bản plugin, effective POM và nơi quản lý version; **không thêm explicit version vào child chỉ để update một cách vội vàng**.

### 10.4. Reactor internal versions

Với multi-module reactor, các module nội bộ có thể dùng một project version chung. Không nên áp tự động “latest remote” cho những internal dependencies đang thuộc cùng reactor. Đó có thể là artifact version đã phát hành, khác với version source đang build.

Nếu cần đổi version của **chính reactor projects**, xem `versions:set` và `versions:update-child-modules` theo chính sách, thay vì dùng `display-dependency-updates` như một lệnh đổi project version.

## 11. Lọc các candidate updates theo chính sách

Các reports dễ gây nhiễu nếu đề xuất alpha/beta/RC/milestone hoặc phiên bản vượt quá mức thay đổi mà dự án cho phép. Versions Plugin có nhiều cơ chế lọc; cần hiểu phạm vi từng cơ chế.

### 11.1. Snapshots và pre-releases khác nhau

Tham số mặc định:

```text
allowSnapshots = false
```

có nghĩa **không cho phép các `-SNAPSHOT` versions** trong tìm kiếm latest theo mục tiêu tham số. Nhưng một bản `2.0.0-RC1`, `2.0.0-M2` hoặc `2.0.0-beta1` **không nhất thiết có suffix `-SNAPSHOT`**, nên chỉ tắt snapshots **không có nghĩa mọi candidate đều là stable GA**.

Ví dụ:

```text
1.5.0          (release)
2.0.0-RC1      (release candidate, không phải SNAPSHOT)
2.0.0-M2       (milestone)
2.0.0-SNAPSHOT (snapshot)
```

Đây là minh họa các kiểu version string, **không phải danh sách version của một artifact cụ thể**.

### 11.2. Lọc major updates

```bash
mvn -B -ntp versions:display-dependency-updates -DallowMajorUpdates=false
```

Mục đích là bỏ candidate làm thay đổi major segment theo cách so sánh được plugin hỗ trợ. Nhưng **không tự coi mọi version Maven đều theo Semantic Versioning nghiêm ngặt**; artifact có thể đặt version theo lịch, qualifiers hoặc schemes riêng.

Muốn giới hạn hơn:

```bash
mvn -B -ntp versions:display-dependency-updates -DallowMinorUpdates=false
```

Theo tài liệu goal 2.22.0, `allowMinorUpdates=false` **cũng hàm ý allowMajorUpdates=false**. Và **`allowIncrementalUpdates=false` còn hàm ý allowMinorUpdates=false cùng allowMajorUpdates=false**. Vì vậy **không** dùng `-DallowIncrementalUpdates=false` với suy nghĩ “chỉ hiện major/minor”: có thể khiến bạn không còn candidate updates thuộc các nhóm chính.

### 11.3. Lọc pre-release bằng ignoredVersions

Một ví dụ CLI chạy được trên Bash/PowerShell thông thường:

```bash
mvn -B -ntp versions:display-dependency-updates "-Dmaven.version.ignore=.*-RC.*,.*-M.*,.*-alpha.*,.*-beta.*"
```

Các biểu thức là **Java regular expressions**, dùng để bỏ những **candidate version strings** khớp patterns. Regex có thể phân biệt hoa/thường; ví dụ không bao phủ mọi convention khác như `-preview`, `-EA` hoặc `-cr`. Đây là điểm xuất phát để viết policy, **không phải danh sách tuyệt đối đầy đủ**.

Bạn cũng có thể cấu hình trong plugin:

```xml
<configuration>
    <ignoredVersions>
        <ignoredVersion>.*-RC.*</ignoredVersion>
        <ignoredVersion>.*-M.*</ignoredVersion>
        <ignoredVersion>.*-alpha.*</ignoredVersion>
        <ignoredVersion>.*-beta.*</ignoredVersion>
    </ignoredVersions>
</configuration>
```

Đây là đoạn bên trong `maven-versions-plugin` configuration, cần hợp nhất vào POM lab nếu muốn sử dụng. Tài liệu MojoHaus cho biết `maven.version.ignore` là cách cung cấp ignoredVersions từ command line, và có thể **override ruleSet đã cấu hình** trong những phiên bản tương ứng. Đừng vô tình làm mất security/compatibility policy của team bằng một CLI flag đơn giản.

### 11.4. ruleSet cho bộ quy tắc có cấu trúc

```xml
<configuration>
    <ruleSet>
        <ignoreVersions>
            <ignoreVersion type="regex">.*-RC.*</ignoreVersion>
            <ignoreVersion type="regex">.*-M.*</ignoreVersion>
        </ignoreVersions>
    </ruleSet>
</configuration>
```

`ruleSet` hỗ trợ rules phức tạp hơn các regex toàn cục; với những artifacts có lịch sử version riêng, có thể cần selective rules theo group/artifact/range. Khi dùng `rulesUri` để trỏ đến ruleset bên ngoài, CI phải bảo đảm vị trí/tài nguyên này đáng tin và sẵn có. Không tải ruleset từ nguồn không kiểm soát rồi cho nó quyết định tự động các bản nâng cấp.

### 11.5. dependencyIncludes và dependencyExcludes

`display-dependency-updates` có các tham số để **chọn artifact đầu vào** được báo cáo:

```bash
mvn -B -ntp versions:display-dependency-updates "-DdependencyIncludes=org.apache.commons:commons-lang3"
```

Điểm phân biệt quan trọng:
- `dependencyIncludes`/`dependencyExcludes` chọn **những dependencies đang sử dụng** để xem xét.
- `ignoredVersions`/`ruleSet` lọc **candidate versions có thể nâng lên**.
- Đừng dùng `dependencyExcludes` với một version string kiểu `2.*-RC.*` rồi tưởng nó ngăn plugin đề xuất RC; hãy dùng **version rules** đúng mục đích.

Các parameter có pattern GAV mở rộng, phạm vi classpath, classifier và management riêng. Nếu cần lọc chặt trong production, xem goal docs của **đúng version** thay vì suy ra mọi glob đều hoạt động như shell wildcard.

## 12. Lưu báo cáo mà không chỉnh sửa pom.xml

Mục tiêu thường gặp ở CI là lưu artifact text để reviewer xem.

Ví dụ, sau khi build tạo `target`:

```bash
mvn -B -ntp versions:display-dependency-updates "-Dversions.outputFile=target/dependency-updates.txt"
```

Đây là **ghi file báo cáo text**, không phải edit `pom.xml`. Goal cũng có tham số `versions.logOutput` điều khiển có in báo cáo lên console hay không và `versions.overwriteOutput` điều khiển tình huống file đã tồn tại trong các version hỗ trợ.

Để dễ tổng hợp:
- Ghi rõ Maven/JDK versions dùng cho scan.
- Ghi plugin version 2.22.0 (hoặc bản thực tế đang dùng).
- Ghi thời điểm, branch/commit, repository mirror/profile.
- Đính kèm report file như CI artifact nếu chính sách cho phép.
- Tránh commit các report tạm vào source project nếu chúng chỉ thuộc một build.
- Bảo vệ logs vì Maven settings/proxy/URL/stack traces có thể chứa thông tin hạ tầng nội bộ.

**Không nên coi file report có cùng tên là report mới nếu goal đã fail trước đó.** Có thể có output file từ lần chạy cũ; dùng job workspace sạch hoặc kiểm tra timestamp/exit status theo chính sách CI.

### 12.1. Maven Site reports

Versions Plugin còn cung cấp:
- `dependency-updates-report`.
- `plugin-updates-report`.
- `property-updates-report`.
- Các aggregate report goals cho multi-module site trong những cấu hình phù hợp.

Nếu dùng Maven Site Plugin, có thể cấu hình `<reporting><plugins>` để xuất reports. **Phân biệt:** goal `display-*` in/ghi text phù hợp chạy từ CLI; goal `*-updates-report` cung cấp Maven Site report và không đồng nghĩa với CLI display output.

Một snippet minh họa:

```xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>versions-maven-plugin</artifactId>
            <version>2.22.0</version>
            <reportSets>
                <reportSet>
                    <reports>
                        <report>dependency-updates-report</report>
                        <report>plugin-updates-report</report>
                        <report>property-updates-report</report>
                    </reports>
                </reportSet>
            </reportSets>
        </plugin>
    </plugins>
</reporting>
```

Đây là **reporting snippet**, không phải thay thế phần `<build><plugins>` của lab. Khi chạy site/report ở môi trường CI, kiểm tra Maven Site Plugin, skin, rendering dependencies và đường dẫn output trước khi công bố.

## 13. Sau khi đã đánh giá: cập nhật một property có kiểm soát

**Phần này minh họa các goal có thay đổi file. Không chạy trên production branch chưa commit hoặc POM có thay đổi chưa lưu mà không chuẩn bị rollback.**

Giả sử team đã kiểm thử và chấp thuận Commons Lang **3.14.0** cho lab. Trước khi chỉnh:

```bash
git status --short
git diff -- pom.xml
```

Các lệnh chỉ minh họa cách quan sát workspace Git; không giả định project lab mới tạo đã được `git init`. Nếu không dùng Git, sao lưu POM theo công cụ quản lý nguồn tương ứng.

Cập nhật một property theo version **đã chọn**:

```bash
mvn -B -ntp versions:set-property "-Dproperty=commons.lang3.version" "-DnewVersion=3.14.0"
```

`versions:set-property` **sửa source POM** và theo docs **không tự kiểm tra tính phù hợp của newVersion**; nó áp giá trị do bạn chỉ định. Lần đầu các modifying goals được dùng có thể tạo file backup như `pom.xml.versionsBackup`, trừ khi cấu hình tắt tính năng backup.

Sau đó:

```bash
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Và chạy Java main lại với runtime dependency copy phù hợp. Hãy kiểm tra:
- Test count và assertions còn pass.
- Main stdout `Hello, Maven!` như trước.
- Không có version conflict bất ngờ.
- API/behavior và security/licensing phù hợp.
- Maven plugin/JDK vẫn tương thích.
- Chỉ đúng property dự định được chỉnh trong POM.

**Không gộp modifying goal với compilation lifecycle vào cùng một invocation khi có thể tránh.** Dùng **một lệnh cập nhật**, kiểm tra diff, sau đó **một invocation Maven khác** để build/test — nhất là với Maven 3 và các trường hợp mô hình effective POM được tạo khi Maven bắt đầu invocation.

### 13.1. update-properties khác set-property

```bash
mvn -B -ntp versions:update-properties
```

là lệnh **có thể tự cập nhật nhiều properties** theo version candidates/rules. Khác với `display-property-updates` chỉ báo, nó có thể chỉnh POM. Khi nhiều libraries dùng properties chung, thay đổi có thể rộng hơn một mục bạn dự định.

```bash
mvn -B -ntp versions:use-latest-releases
```

cũng là **lệnh có thể sửa dependency versions**. Nó không phải một công cụ đảm bảo mọi API compatible hoặc tránh mọi pre-release theo policy, và không nên bind vào default build lifecycle. Đối với project quản lý versions qua properties, `update-properties`/`set-property` có thể là con đường đúng hơn so với việc cố thay version trực tiếp của dependency.

### 13.2. Backup/revert/commit của Versions Plugin

Theo tài liệu MojoHaus, modifying goals thường có thể tạo `pom.xml.versionsBackup`. Plugin có:
- `versions:revert`: khôi phục từ backup mà plugin đã tạo khi còn hợp lệ.
- `versions:commit`: xóa backup, chấp nhận file đang thay đổi theo cơ chế plugin.

Nhưng nếu bạn đang dùng Git và đã có modifications khác, **đừng dựa vào revert/commit để xử lý mọi loại thay đổi**; hãy xem diff trước và kiểm tra đúng files được thay. Không đặt `generateBackupPoms=false` chỉ để tránh file backup nếu team chưa có cơ chế rollback đáng tin cậy.

### 13.3. Không tự nâng “latest” vào production

Một quy trình đủ kiểm soát:
1. Scan reports.
2. Chọn candidate theo release notes/compatibility/security policy.
3. Update một nhóm nhỏ.
4. Review POM diff và dependency tree.
5. Chạy `mvn clean verify`.
6. Chạy integration/contract tests nếu thay framework/platform.
7. Đánh giá transitive updates, classpath, licenses, SBOM.
8. Mở pull request; không thay release immutable khi chưa có phê duyệt.
9. Nếu fail, rollback thay đổi cụ thể; không che test failure bằng `-DskipTests`.

## 14. Multi-module reactor: nên chạy goal ở đâu?

Với cấu trúc:

```text
workspace/
├── pom.xml              (packaging=pom, parent/aggregator)
├── core/
│   └── pom.xml          (jar)
├── service/
│   └── pom.xml          (jar)
└── app/
    └── pom.xml          (jar)
```

Version có thể nằm:
- Ở parent `<dependencyManagement>`.
- Ở parent `<properties>` dùng chung.
- Trong từng child `<dependencies>`.
- Trong root `<pluginManagement>`.
- Trong plugin declarations của riêng từng child.
- Trong imported BOM hoặc parent khác.

**Không áp dụng một lệnh update hàng loạt vào root rồi tưởng mọi version được thay theo mong muốn.** Cần biết nơi nào **sở hữu version** và goals nào xử lý properties/management trong những version plugin cụ thể.

Một số lệnh ví dụ:

```bash
mvn -B -ntp -pl :service versions:display-dependency-updates
```

hoặc scan toàn reactor từ root:

```bash
mvn -B -ntp versions:display-dependency-updates
```

Đối với Maven reactor, lựa chọn `-pl` điều khiển module nào được execute; `-am` bổ sung upstream dependencies nếu cần. **Versions Plugin display goals chủ yếu đọc POM/metadata**, nhưng Maven có thể vẫn cần resolve parent/plugin/repository settings để lập model và chạy plugin.

### 14.1. excludeReactor trong update properties

Các goal chỉnh properties có tham số như `excludeReactor` (theo tài liệu `update-properties`). Việc update internal module versions của cùng reactor không nên xảy ra theo đề xuất “latest remote” nếu các modules đang được build đồng bộ một version mới. Cần quản lý project versions bằng `versions:set`/parent policy riêng.

### 14.2. Parent version trong reactor

Nếu child kế thừa root version nội bộ, một thay đổi parent `<version>` hoặc child `<parent><version>` sai có thể làm reactor model không resolve. `versions:update-child-modules` phục vụ kịch bản đồng bộ parent reference trong những tình huống được thiết kế, nhưng **đó là modifying goal**; không phải công cụ để dò available dependency updates.

### 14.3. Tại sao report có thể lặp trên mỗi module?

Khi chạy một Maven goal trong multi-module reactor, plugin có thể thực thi trên nhiều projects; log/report có thể có thông tin lặp về parent-managed versions hoặc modules nhận cùng dependency. Đừng đếm mỗi dòng report là một artifact độc lập cần tạo PR riêng. Nếu cần một dashboard chung, cân nhắc **aggregate Maven Site reports** hoặc tool phân tích graph được tổ chức theo project.

## 15. Maven repositories, mirror, proxy và metadata freshness

Versions Plugin chỉ nhìn thấy versions mà Maven có thể **tra cứu được**. Trong doanh nghiệp, Maven Central có thể nằm sau Nexus/Artifactory/mirror nội bộ; kết quả phụ thuộc vào:
- `settings.xml` mirrors/proxies/servers.
- Repository policies (releases/snapshots).
- Authentication/authorization.
- Metadata cache và cập nhật metadata.
- Profiles đang kích hoạt.
- Plugin repositories (đặc biệt khi kiểm tra Maven plugin artifacts).
- Network/DNS/TLS và artifact replication delay.

### 15.1. “Không có update” không đồng nghĩa tất cả đều mới nhất trên Internet

Nếu nội bộ mirror chỉ cho phép versions đã duyệt, plugin có thể báo không có candidate cao hơn. Đó là **kết quả đúng trong repository scope hiện tại**, không phải bằng chứng không có release trên Maven Central.

Tương tự, nếu network failure/missing metadata xảy ra, một số candidate có thể không được nhìn thấy hoặc goal fail. Hãy phân biệt report thực sự hoàn thành với report bị cắt bởi lỗi truy cập.

### 15.2. Offline mode

```bash
mvn -o versions:display-dependency-updates
```

Đây là **lệnh minh họa**, không nên xem là cách scan fresh updates. Offline mode `-o` chỉ dùng metadata/artifacts sẵn trong local cache. Nó có thể fail vì thiếu plugin/artifact hoặc cho thấy ít/không có candidate mới dù repository online đã có. Để đánh giá cập nhật mới, cần metadata nguồn đáng tin và kết nối phù hợp.

### 15.3. Mạng và credential an toàn

Không đưa token/password vào command line, `pom.xml` hoặc log `mvn -X` khi chia sẻ. Thông tin xác thực thường nằm trong Maven settings/CI secret manager phù hợp. Khi báo cáo lỗi mirror, chỉ chia sẻ phần cần thiết đã redacted; logs có thể chứa hostnames, repository paths hoặc environment details nội bộ.

## 16. Đọc đúng mức độ thay đổi version

Version numbers trong Maven có thể theo:
- `major.minor.patch`/incremental convention.
- Maven qualifiers `-RC`, `-M`, `-beta`, `-SNAPSHOT`.
- Ngày/tháng/năm hoặc các schemes riêng.
- Vendor-specific suffixes.
- Version range constraints.

Ví dụ khi có `1.8.7` và `2.0.0`, người học thường xem là major update. Nhưng **Versions Plugin không thể thay tác giả thư viện cam kết semantic compatibility** chỉ bằng việc so sánh số. Framework Java có thể thực hiện breaking changes trong một “minor” update hoặc ổn định qua major tùy chính sách.

### 16.1. Đọc release notes trước khi nâng cấp

Checklist với từng candidate:
1. Có thay đổi minimum JDK/Maven không?
2. Có removed/deprecated APIs không?
3. Có thay plugin configuration parameters không?
4. Có thay transitive dependencies/BOM versions không?
5. Có thay runtime behavior, logging, serialization hoặc test engine không?
6. Có yêu cầu migration script hay runtime config mới không?
7. Có bản vá security cần ưu tiên hoặc CVE nào được xử lý không?
8. Có tương thích Java 17 và deployment environment thực không?

Cần phân biệt “update candidate đang available” với “đã được phê duyệt nâng cấp”.

### 16.2. Dependency và plugin có lifecycle khác nhau

Nâng Commons Lang ảnh hưởng **bytecode/runtime behavior của ứng dụng**. Nâng Surefire Plugin ảnh hưởng **cách test được chạy, test providers, fork JVM và reports**. Nâng Compiler Plugin ảnh hưởng compilation flags, JDK compatibility và generated bytecode. Vì vậy tiêu chí nghiệm thu mỗi loại update khác nhau; một `mvn test` pass chưa đủ cho mọi loại artifact.

## 17. Các lỗi phổ biến và xử lý

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `No plugin found for prefix 'versions'` | Maven không resolve được plugin prefix/plugin group/repository. | Dùng fully qualified goal với `org.codehaus.mojo:versions-maven-plugin:2.22.0` và kiểm tra plugin repositories. |
| Plugin goal fail vì JDK/Maven quá cũ | Plugin version có prerequisites mới hơn toolchain. | `mvn -version` và trang System Requirements của đúng plugin version. |
| Không thấy dependency update | Repo metadata hạn chế, filters, snapshots off, version đã được quản lý ở parent/BOM. | Kiểm tra mirror, goal log, effective POM và ruleSet. |
| Không thấy property update | Property không được dùng làm artifact version hoặc nằm ở parent/profile khác. | Xem property references và `display-property-updates`. |
| Version candidate là RC/beta | `allowSnapshots=false` không loại mọi pre-release. | Dùng `ignoredVersions`/`ruleSet` phù hợp. |
| Bản mới compile fail | API thay đổi, JDK tối thiểu cao hơn hoặc transitive conflict. | Review release notes, source compile errors và `dependency:tree`. |
| Plugin update khiến test count bằng 0 | Surefire/JUnit engine/config không tương thích hoặc naming filter. | Test engine và `target/surefire-reports`, không chỉ BUILD SUCCESS. |
| update goal sửa nhiều POM ngoài dự kiến | Multi-module/parent-managed properties hoặc scope selection rộng. | Git diff, hạn chế goal và áp dụng update theo nhóm nhỏ. |
| `pom.xml.versionsBackup` xuất hiện | Modifying goal tạo backup theo policy mặc định. | Xem `versions:revert`, `versions:commit`, giữ source control rõ ràng. |
| Report khác giữa local và CI | Mirror/profile/settings/cache khác, metadata availability khác. | Ghi Maven/plugin versions, repo policy và active profiles. |
| Mặc dù report gợi ý update, CI vẫn pass version cũ | Display goal chỉ báo, không thay POM. | Chạy update riêng có kiểm soát khi đã duyệt. |
| dependency:tree khác báo cáo Versions Plugin | Một lệnh xem resolved graph, một lệnh dò available candidates. | So sánh đúng mục tiêu của từng công cụ. |
| Parent update làm child thất bại | Parent thay BOM, plugins, repositories hoặc Java baseline. | Test reactor và migration guide trước merge. |
| Offline report thiếu version mới | Local metadata cache cũ/thiếu. | Chạy online với repository được phép sau khi kiểm tra network. |
| Security scanner không đồng ý với report | Plugin không phải vulnerability scanner; dependency mediation/embedded JAR khác. | Dùng SBOM/SCA và kiểm tra artifact contents riêng. |

### 17.1. “BUILD SUCCESS” của display goal chứng minh gì?

Nó chứng minh goal hoàn thành theo điều kiện Maven report, **không chứng minh dependencies đã được cập nhật hoặc ứng dụng đã kiểm thử với versions mới**. Sau khi chỉ chạy display goal, source POM vẫn có các version như trước.

### 17.2. “No dependency updates available” có phải kết luận bảo mật?

Không. Có thể không có candidate trong mirror, rules lọc quá chặt hoặc metadata không fresh. Hơn nữa phiên bản hiện tại vẫn có thể chứa vulnerability chưa được khắc phục. Cần policy bảo mật và công cụ chuyên dụng riêng.

### 17.3. Vì sao không chạy use-latest-releases trong mọi CI build?

Vì nó có thể sửa POM và làm build không tái lập: commit không đổi nhưng kết quả phụ thuộc vào repository versions phát hành sau đó. Release pipelines nên build từ **versions được pin/đã review**, còn việc đề xuất nâng cấp nên là quy trình riêng (PR được kiểm thử).

## 18. Quy trình kiểm tra cập nhật an toàn trong dự án thật

**Giai đoạn A – Baseline**

```bash
mvn -version
mvn -B -ntp clean verify
```

Xác nhận baseline đã compile/test hợp lệ. Nếu build có nhiều module, ghi nhận số tests/reports của từng module thay vì chỉ nhìn BUILD SUCCESS.

**Giai đoạn B – Scan (không sửa POM)**

```bash
mvn -B -ntp versions:display-dependency-updates
mvn -B -ntp versions:display-plugin-updates
mvn -B -ntp versions:display-property-updates
mvn -B -ntp versions:display-parent-updates
```

Lệnh parent có thể không có thông tin nếu project không có parent, nhưng chạy riêng giúp phân biệt các loại metadata. Khi cần scan extensions, thêm `display-extension-updates`. Không cần ghép bốn goals vào một invocation; chạy riêng giúp logs dễ đọc và xử lý lỗi từng nhóm.

**Giai đoạn C – Đánh giá**

Ghi các candidate versions với nguồn/release notes, mức độ major/minor/incremental, Maven/JDK constraints, security/licensing, migration effort, dependency graph và test plan. Chọn một nhóm nhỏ ít rủi ro để nâng trước.

**Giai đoạn D – Update có kiểm soát**

Dùng modifying goal phù hợp sau khi đã có Git branch/backup. Ví dụ trong lab:

```bash
mvn -B -ntp versions:set-property "-Dproperty=commons.lang3.version" "-DnewVersion=3.14.0"
```

Đây là một **lựa chọn version cố định để minh họa**, không phải khuyến nghị rằng 3.14.0 là bản mới nhất hiện tại.

**Giai đoạn E – Verify lại**

```bash
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Kiểm tra stdout ứng dụng, JUnit reports, diff POM và artifact contents. Nếu framework/plugin update đáng kể, chạy thêm integration tests/compatibility tests theo sản phẩm thật.

**Giai đoạn F – Review/merge/publish**

Chỉ merge/publish khi thay đổi có lý do rõ ràng và quality gates đạt yêu cầu. Không để Versions Plugin cập nhật version silently trong release job.

## 19. Checklist trước khi chốt quyết định nâng cấp

- [ ] Đã xác nhận `mvn -version` và JDK đang dùng.
- [ ] Đã build/test baseline thành công.
- [ ] Versions Maven Plugin được ghim version, biết requirements tương ứng.
- [ ] Đã phân biệt dependency/plugin/property/parent/extension.
- [ ] Đã biết version được quản lý tại source POM, parent, BOM hay property nào.
- [ ] Display goals được chạy riêng, không tự sửa POM.
- [ ] Đã kiểm tra repository mirror, profiles và metadata freshness.
- [ ] Đã lọc snapshots/pre-releases theo policy, không giả định RC là GA.
- [ ] Đã xét major/minor/incremental theo quy tắc artifact cụ thể.
- [ ] Đã đọc release notes và migration requirements.
- [ ] Đã đánh giá JDK/Maven/plugin framework compatibility.
- [ ] Đã có Git diff/rollback khi dùng modifying goal.
- [ ] Đã chạy lại `clean verify` sau khi update.
- [ ] Đã kiểm tra JUnit test count và reports.
- [ ] Đã xem `dependency:tree` để phát hiện transitives/version mediation.
- [ ] Đã test consumer nếu artifact là thư viện dùng bởi project khác.
- [ ] Đã xem SBOM/CVE/license riêng thay vì chỉ nhìn Versions Plugin.
- [ ] Không để update goal chạy ngầm trong mọi default build.
- [ ] Report CI có timestamp, commit, mirror/profile và toolchain context.
- [ ] Bản nâng cấp được review trước khi publish.

## 20. Câu hỏi ôn tập và đáp án

**Câu 1.** Maven Versions Plugin dùng để làm gì?

**Đáp án:** Kiểm tra những versions mới có sẵn cho artifacts/parent/plugins/properties và hỗ trợ thay đổi version declarations trong POM qua các goals riêng.

**Câu 2.** Lệnh nào xem dependency updates mà không sửa POM?

**Đáp án:** `mvn versions:display-dependency-updates`.

**Câu 3.** Lệnh nào xem build-plugin updates?

**Đáp án:** `mvn versions:display-plugin-updates`.

**Câu 4.** Lệnh nào xem property-linked version updates?

**Đáp án:** `mvn versions:display-property-updates`.

**Câu 5.** Lệnh nào xem parent POM updates?

**Đáp án:** `mvn versions:display-parent-updates`.

**Câu 6.** Vì sao `display-dependency-updates` khác `dependency:tree`?

**Đáp án:** Một goal tìm candidate versions trong repository, goal còn lại cho thấy resolved dependency graph hiện tại.

**Câu 7.** `allowSnapshots=false` có loại tất cả `-RC`, `-M`, `-alpha` không?

**Đáp án:** Không. Chúng có thể không phải SNAPSHOT; cần ignoredVersions/ruleSet phù hợp.

**Câu 8.** `-DallowMinorUpdates=false` ảnh hưởng major updates thế nào?

**Đáp án:** Theo docs của Versions Plugin, false cũng hàm ý `allowMajorUpdates=false`.

**Câu 9.** Nếu đặt `allowIncrementalUpdates=false`, plugin có vẫn gợi ý major/minor không?

**Đáp án:** Không theo parameter semantics được tài liệu goal ghi: false kéo theo minor và major cũng false.

**Câu 10.** `<dependencyManagement>` có tự thêm dependency vào classpath không?

**Đáp án:** Không. Nó quản lý version/scope khi một dependency thực sự được khai báo.

**Câu 11.** Property `project.build.sourceEncoding` có version update không?

**Đáp án:** Không; nó là encoding setting, không phải version của artifact.

**Câu 12.** Lab dùng Maven Versions Plugin version nào?

**Đáp án:** `2.22.0` để ví dụ có version tường minh; không khẳng định là latest.

**Câu 13.** Lab có bao nhiêu JUnit tests?

**Đáp án:** **3**: tên được chuẩn hóa, input toàn whitespace, input null.

**Câu 14.** Java application trong lab in gì?

**Đáp án:** Chính xác một dòng `Hello, Maven!`.

**Câu 15.** `versions:set-property` có sửa `pom.xml` không?

**Đáp án:** Có. Nó sửa property theo giá trị chỉ định, **không tự bảo đảm** version tương thích hoặc kiểm thử thành công.

**Câu 16.** Vì sao nên tách lệnh modifying goal khỏi `mvn clean verify`?

**Đáp án:** Để Maven build ở invocation mới đọc POM sau khi sửa, diff/rollback được kiểm soát, tránh sự nhầm lẫn model đã load.

**Câu 17.** `pom.xml.versionsBackup` xuất hiện từ đâu?

**Đáp án:** Các modifying goals của Versions Plugin có thể tạo backup POM theo cấu hình mặc định.

**Câu 18.** Trong multi-module build, có nên cập nhật mọi internal project dependency theo latest remote không?

**Đáp án:** Không tự động. Internal reactor versions cần chính sách đồng bộ riêng; latest remote có thể khác source đang build.

**Câu 19.** Report không có update chứng minh Maven Central chưa phát hành version mới không?

**Đáp án:** Không. Mirror, metadata cache, profiles, rules hoặc network có thể giới hạn những candidates nhìn thấy.

**Câu 20.** Có phải Versions Plugin là vulnerability scanner không?

**Đáp án:** Không. Cần SBOM/SCA/CVE workflow riêng, và tự đọc release/security notes.

**Câu 21.** Tại sao không bind `versions:use-latest-releases` vào `package`?

**Đáp án:** Vì nó có thể tự sửa POM trong default build, làm pipeline không còn reproducible và khó review.

**Câu 22.** Muốn chạy plugin có version chính xác, không dựa vào prefix resolution, làm sao?

**Đáp án:** Gọi fully qualified goal, ví dụ `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates`.

## 21. Tài liệu tham khảo chính thức

- [MojoHaus – Versions Maven Plugin Introduction](https://www.mojohaus.org/versions/versions-maven-plugin/): mục tiêu, loại goals và reporting.
- [MojoHaus – Versions Maven Plugin Usage](https://www.mojohaus.org/versions/versions-maven-plugin/usage.html): phân biệt display goals và modifying goals, backup, Maven Site reports.
- [MojoHaus – Plugin Details / System Requirements](https://www.mojohaus.org/versions/versions-maven-plugin/plugin-info.html): danh sách goals và yêu cầu Maven/JDK theo plugin version.
- [MojoHaus – display-dependency-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-dependency-updates-mojo.html): flags `allowMajorUpdates`, `allowMinorUpdates`, `allowIncrementalUpdates`, `allowSnapshots`, `showVersionless`, `dependencyIncludes` và rules.
- [MojoHaus – display-plugin-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-plugin-updates-mojo.html): xét plugin versions và `processUnboundPlugins`.
- [MojoHaus – display-property-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-property-updates-mojo.html): properties được liên kết đến artifact versions.
- [MojoHaus – display-parent-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-parent-updates-mojo.html): parent POM version candidates.
- [MojoHaus – Checking for new dependency updates](https://www.mojohaus.org/versions/versions-maven-plugin/examples/display-dependency-updates.html): ignoredVersions/ruleSet với pre-releases.
- [MojoHaus – set-property](https://www.mojohaus.org/versions/versions-maven-plugin/set-property-mojo.html): thao tác thay đổi property theo `newVersion`.
- [MojoHaus – update-properties](https://www.mojohaus.org/versions/versions-maven-plugin/update-properties-mojo.html): nâng property-linked artifact versions.
- [Apache Maven – Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scope, dependencyManagement, BOM và mediation.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): parent, properties, dependencies, plugins và reporting.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor selection/sorting khi scan POM nhiều module.
- [Apache Maven – Plugin Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html): tiến hóa yêu cầu runtime Maven/JDK của plugins.
