# Cấu hình Checkstyle cho quy tắc mã nguồn Java trong Gradle

## 1. Checkstyle giải quyết bài toán gì?

Một dự án Java có thể **biên dịch thành công và vượt qua unit tests** nhưng vẫn có mã nguồn thiếu nhất quán: sử dụng `import java.util.*`, dòng quá dài, tên biến không theo chuẩn nhóm, thiếu dấu ngoặc nhọn hoặc phần mã được sinh tự động chưa được quản lý rõ ràng. Nếu mỗi reviewer kiểm tra thủ công, quy tắc dễ bị áp dụng khác nhau giữa máy cá nhân và CI.

**Checkstyle** là công cụ phân tích tĩnh mã nguồn Java dựa trên một tập quy tắc cấu hình được bằng XML. **Gradle Checkstyle plugin** (`id("checkstyle")`) tích hợp công cụ này vào task graph, cho phép chạy kiểm tra theo source set, tạo báo cáo và dùng `check`/`build` làm quality gate.

Bài học thuộc nhóm **Chất lượng mã** của **Build Tool Gradle**. Mục tiêu là cấu hình Checkstyle đúng phạm vi Java trong Gradle, hiểu quan hệ với `check` và `build`, tạo policy dễ review, đọc reports, xử lý vi phạm và phát triển dần một bộ quy tắc phù hợp tổ chức.

Sau bài này, bạn có thể:

1. Phân biệt Checkstyle, Java compiler warnings, unit tests, PMD, SpotBugs và code formatter.
2. Áp dụng plugin `checkstyle`, hiểu các task `checkstyleMain`, `checkstyleTest`, `check` và `build`.
3. Tạo `config/checkstyle/checkstyle.xml` dùng DTD Checkstyle, với các module `Checker`, `TreeWalker`, `AvoidStarImport` và `LineLength`.
4. Chạy một dự án Java 17 nhỏ: cố ý tạo lỗi style, quan sát quality gate fail, sửa source và xác nhận pass.
5. Chọn `toolVersion`, `configDirectory`, `configProperties`, `maxErrors`, `maxWarnings`, `ignoreFailures` và `showViolations`.
6. Bật HTML/XML/SARIF reports và biết giới hạn về phiên bản Checkstyle.
7. Dùng `suppressions.xml` khi có ngoại lệ được duyệt, tránh tắt toàn bộ quy tắc chỉ để build xanh.
8. Áp dụng Checkstyle cho nhiều module Java và xử lý generated sources.
9. Chẩn đoán lỗi XML/DTD, sai đường dẫn, thiếu tool JAR, JDK không tương thích, vi phạm code hoặc cấu hình CI.
10. Thiết lập quality gate theo lộ trình: kiểm tra được, ít ngoại lệ, có reports và được quản lý cùng source trong Git.

Ví dụ chính dùng **Gradle Kotlin DSL**, **Java 17**, Checkstyle **10.24.0** và Gradle Wrapper tương thích. Checkstyle 10.24.0 là một phiên bản dùng để minh họa, **không phải khẳng định đó là bản mới nhất**. Không dùng URL repo hoặc phiên bản trong tài liệu làm nguồn cập nhật bảo mật tự động; phải đối chiếu phiên bản được tổ chức phê duyệt.

## 2. Checkstyle là gì và không phải là gì?

Checkstyle đọc mã nguồn Java và đối chiếu với những **checks** được bật trong XML. Mỗi check có thể phát ra một hoặc nhiều **violations** kèm file, dòng, cột, tên rule và severity.

Ví dụ quy tắc:

- `AvoidStarImport`: không cho dùng wildcard import như `import java.util.*;`.
- `LineLength`: giới hạn độ dài dòng.
- `NeedBraces`: yêu cầu braces trong các cấu trúc điều khiển được rule hỗ trợ.
- `MethodName`: kiểm tra tên method theo biểu thức quy tắc.
- `FileTabCharacter`: kiểm tra sự xuất hiện của tab trong source.
- `JavadocMethod`: kiểm tra một số yêu cầu về tài liệu phương thức.
- `EmptyBlock`: quản lý empty blocks theo tiêu chí khai báo.

Các rule không tự bật chỉ vì bạn áp dụng Gradle plugin. **Nội dung `checkstyle.xml` quyết định kiểm tra những gì.** Plugin kết nối việc thực thi và báo cáo với build; Checkstyle engine cung cấp các checks.

### 2.1. Phân biệt các công cụ

| Công cụ | Công việc chính | Không nên kỳ vọng |
| --- | --- | --- |
| Java compiler (`javac`) | Kiểm tra cú pháp, kiểu dữ liệu, Java API và sinh `.class` | Thực thi toàn bộ quy tắc style của tổ chức |
| Checkstyle | Kiểm tra style/convention Java source theo XML rules | Đảm bảo runtime đúng hoặc tìm mọi bug |
| JUnit | Chạy test cases và assertions | Chứng minh import/tên biến tuân chuẩn |
| PMD | Phân tích code rules/anti-patterns theo ruleset | Thay thế mọi Checkstyle rule |
| SpotBugs | Tìm các bug patterns, thường dựa trên bytecode | Là Java formatter hay bộ kiểm tra style |
| Spotless hoặc formatter khác | Tự động format theo quy tắc được cấu hình | Luôn thay được mọi semantic style rule của Checkstyle |
| JaCoCo | Thu thập và báo cáo test coverage | Kiểm tra quy ước đặt tên mã nguồn |

Checkstyle phát hiện các vi phạm nó được thiết kế và **đã cấu hình**, không bảo đảm ứng dụng không có vulnerability hoặc lỗi logic. Một class có style đạt chuẩn vẫn có thể có `NullPointerException`; một class viết đúng chức năng vẫn có thể bị báo `AvoidStarImport`.

### 2.2. Static analysis khác auto-format

Trong phần lớn cấu hình, Checkstyle **báo vi phạm** chứ **không tự sửa source files**. Nếu chạy `./gradlew checkstyleMain` và thấy fail, bạn cần sửa code, cập nhật cấu hình được review hoặc áp dụng formatter phù hợp rồi chạy lại. Không dựa vào Checkstyle như một lệnh tự động format mọi Java file.

## 3. Gradle Checkstyle plugin và task graph

Để áp dụng trong Kotlin DSL:

~~~kotlin
plugins {
    java
    checkstyle
}
~~~

Groovy DSL tương đương:

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
}
~~~

Khi có Java plugin, Gradle Checkstyle plugin tạo những task kiểm tra theo source set:

- **`checkstyleMain`**: kiểm tra Java source thuộc source set `main`; theo Gradle plugin convention có dependency tới `classes`.
- **`checkstyleTest`**: kiểm tra Java source thuộc source set `test`; theo convention có dependency tới `testClasses`.
- **`checkstyle<SourceSet>`**: thêm task cho source set khác được plugin quản lý.
- **`check`**: lifecycle task tập hợp verification, phụ thuộc vào các Checkstyle tasks do plugin cung cấp.
- **`build`**: lifecycle task phụ thuộc `check` và `assemble` khi dùng Base/Java plugin.

Vì Java plugin cũng gắn `test` vào `check`, một project Java đơn giản có sơ đồ:

~~~text
:build
  |
  +-- :assemble
  |     |
  |     +-- :jar
  |
  +-- :check
        |
        +-- :test
        |
        +-- :checkstyleMain
        |
        +-- :checkstyleTest
~~~

Sơ đồ là **quan hệ phụ thuộc**, không cam kết `test` luôn chạy trước `checkstyleMain` hoặc ngược lại. Gradle có thể sắp xếp hai nhánh độc lập khác nhau. Các task compile/resources cần thiết cũng có trong graph nhưng được lược bớt ở sơ đồ.

**Điểm quan trọng:** `./gradlew checkstyleMain` kiểm tra source `main`, không phải một lệnh thay thế `./gradlew test`. `./gradlew check` mới là điểm tập hợp nhiều verification tasks. `./gradlew assemble` tạo artifact và không mặc định chạy Checkstyle.

### 3.1. Những lệnh phổ biến

~~~bash
./gradlew checkstyleMain --console=plain
./gradlew checkstyleTest --console=plain
./gradlew check --console=plain
./gradlew build --console=plain
./gradlew build --dry-run --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat checkstyleMain --console=plain
.\gradlew.bat checkstyleTest --console=plain
.\gradlew.bat check --console=plain
.\gradlew.bat build --console=plain
.\gradlew.bat build --dry-run --console=plain
~~~

`--dry-run` cho thấy tasks được chọn nhưng **không chạy actions**: không thể coi đó là một lần scan Checkstyle đã pass. Khi task `UP-TO-DATE` hoặc được phục hồi từ build cache, Gradle có thể không khởi động Checkstyle engine lần nữa vì kết quả cũ vẫn được coi là hợp lệ theo task inputs/outputs.

## 4. Dự án thực hành Java 17 hoàn chỉnh

Mẫu này có một class Java với wildcard import để tạo vi phạm, một bản sửa hợp lệ và các lệnh kiểm tra. Có cả test JUnit để bạn nhìn được `check` chạy nhiều loại verification.

### 4.1. Cấu trúc thư mục

~~~text
gradle-checkstyle-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── config/
│   └── checkstyle/
│       └── checkstyle.xml
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           ├── Greeter.java
│   │           └── Main.java
│   └── test/
│       └── java/
│           └── demo/
│               └── GreeterTest.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Yêu cầu: Java 17 có sẵn cho Gradle toolchain, Gradle Wrapper hợp lệ và repository Maven Central (hoặc mirror được cho phép) truy cập được để tải Checkstyle + JUnit. Nếu bạn mới tạo một folder rỗng, phải tạo Wrapper theo cách dự án được phê duyệt trước khi gọi `./gradlew`.

### 4.2. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-checkstyle-demo"
~~~

### 4.3. build.gradle.kts đầy đủ

~~~kotlin
import org.gradle.api.plugins.quality.Checkstyle

plugins {
    java
    checkstyle
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(
        platform("org.junit:junit-bom:5.10.2")
    )
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

checkstyle {
    // Pin phiên bản Checkstyle đã được chọn cho bài lab.
    toolVersion = "10.24.0"

    // Gradle mặc định tìm config/checkstyle/checkstyle.xml
    // ở root project; ghi rõ để dễ thấy source-of-truth.
    configDirectory.set(
        rootProject.layout.projectDirectory.dir("config/checkstyle")
    )

    // Không cho phép lỗi style trong bài lab.
    maxErrors = 0

    // Warnings cũng phải được xem xét ở phần chính sách riêng.
    // Với XML bên dưới, các checks dùng severity mặc định ERROR.
    showViolations = true
}

tasks.test {
    useJUnitPlatform()
}

tasks.withType<Checkstyle>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}
~~~

Giải thích:

1. `java` tạo Java source sets, compiler tasks và `test`.
2. `checkstyle` tạo Checkstyle tasks rồi nối vào lifecycle `check`.
3. Gradle dùng `toolVersion` để lấy Checkstyle engine và dependencies tương ứng; **đây không phải version Gradle Wrapper**.
4. `configDirectory` trỏ đến folder chứa policy XML. Nó cũng tạo biến `${config_loc}` để Checkstyle XML có thể tham chiếu file suppression/phụ trợ.
5. `maxErrors=0` giữ fail-on-violation ở severity ERROR. Không cần tắt cơ chế fail của plugin.
6. `showViolations=true` giúp xem vi phạm trên console; reports vẫn là nơi xem đầy đủ.
7. `tasks.test { useJUnitPlatform() }` dành cho JUnit, tách biệt với Checkstyle.
8. XML/HTML reports dành cho việc review local và tải lên hệ thống CI. Chúng **không** được commit vào Git như policy XML.

Plugin Checkstyle không cần khai báo `implementation("com.puppycrawl.tools:checkstyle:...")` trong application dependencies. Nó tự quản lý một configuration **`checkstyle`** chứa engine Checkstyle; `toolVersion` điều khiển engine. Đây là build tool dependency, không phải library phải đóng gói vào app.

### 4.4. config/checkstyle/checkstyle.xml

Tạo file XML **chính xác theo đường dẫn** `config/checkstyle/checkstyle.xml`:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">

<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <!-- Rule cấp Checker: kiểm tra chiều dài dòng. -->
    <module name="LineLength">
        <property name="max" value="120"/>
    </module>

    <!-- Các rule AST Java nằm dưới TreeWalker. -->
    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
~~~

Cấu hình này cố ý nhỏ để dễ học:

- `Checker` là root module, điều phối kiểm tra files.
- `charset=UTF-8` khai báo cách Checkstyle giải mã Java source. **Điều này khác với `JavaCompile.options.encoding`** dù trong một dự án nên nhất quán.
- `LineLength` cấp Checker kiểm tra số ký tự của một dòng; giới hạn trong ví dụ là 120.
- `TreeWalker` duyệt Java AST, cung cấp context cho nhiều checks, trong đó có `AvoidStarImport`.
- `AvoidStarImport` báo những wildcard imports như `import java.util.*;`.

**Thứ tự và nơi đặt modules là quan trọng.** Không phải Checkstyle check nào cũng được đặt dưới `TreeWalker`; một số như `LineLength` thuộc `Checker`. Nếu đặt nhầm parent, Checkstyle có thể báo lỗi cấu hình dù Gradle script hoàn toàn hợp lệ.

DTD trong tài liệu là DTD công khai chính thức của Checkstyle. Gradle Checkstyle plugin **tắt tải external DTD theo mặc định vì lý do an ninh**. Những DTD chuẩn mà Checkstyle nhận diện thường được xử lý bằng cơ chế riêng; không bật tải external DTD tùy tiện để sửa lỗi chưa rõ nguồn.

### 4.5. src/main/java/demo/Greeter.java

~~~java
package demo;

import java.util.List;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(List<String> names) {
        return "Xin chào, " + String.join(" và ", names) + "!";
    }
}
~~~

Ở trạng thái này file không dùng wildcard imports; các dòng không vượt 120 ký tự. Đây là source Java hợp lệ và tuân hai rules chính.

### 4.6. src/main/java/demo/Main.java

~~~java
package demo;

import java.util.List;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
            Greeter.greet(List.of("Lan", "Minh"))
        );
    }
}
~~~

Nếu compile thành công, chương trình `demo.Main` sẽ in:

~~~text
Xin chào, Lan và Minh!
~~~

### 4.7. src/test/java/demo/GreeterTest.java

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreeterTest {
    @Test
    void greetsTwoPeople() {
        assertEquals(
            "Xin chào, Lan và Minh!",
            Greeter.greet(List.of("Lan", "Minh"))
        );
    }
}
~~~

JUnit 5 test có assertion thật, và import được khai báo tường minh. Đây cũng là Java source thuộc `test` source set nên task `checkstyleTest` sẽ quét nó theo XML trên.

### 4.8. Chạy kiểm tra trên bản sạch

Linux/macOS:

~~~bash
./gradlew clean check --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean check --console=plain
~~~

Khi có repository/JDK phù hợp, expected result là **JUnit test pass và không có Checkstyle violation** theo XML tối thiểu. Các task `checkstyleMain`, `checkstyleTest` và `test` sẽ thuộc graph của `check`.

**Không có một stdout Gradle cố định** vì thông tin task, warning của Gradle và tình trạng cache khác nhau giữa môi trường. Kiểm tra báo cáo và exit code thay vì chép một chuỗi log tưởng tượng.

Để chạy Java main không cần `application` plugin:

~~~bash
./gradlew classes --console=plain
java -cp build/classes/java/main demo.Main
~~~

PowerShell:

~~~powershell
.\gradlew.bat classes --console=plain
java -cp build\classes\java\main demo.Main
~~~

**Stdout chính xác từ Java application:**

~~~text
Xin chào, Lan và Minh!
~~~

Nếu muốn đối chiếu Java 17 thuần, trong root directory:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out \
    src/main/java/demo/Greeter.java \
    src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Đây chỉ compile hai production classes; chạy JUnit bằng `javac`/`java` thuần còn cần JUnit jars và launcher.

## 5. Chủ động tạo một vi phạm Checkstyle

Giữ nguyên XML và mọi file khác. Trong `src/main/java/demo/Main.java`, **thay đúng một dòng**:

~~~java
import java.util.List;
~~~

thành:

~~~java
import java.util.*;
~~~

Java compiler chấp nhận wildcard import, và `Main` vẫn chạy đúng chức năng. Nhưng **Checkstyle rule `AvoidStarImport`** được bật nên `checkstyleMain` sẽ báo vi phạm.

Chạy:

~~~bash
./gradlew checkstyleMain --console=plain
~~~

Kết quả kỳ vọng:

1. Java compilation `compileJava` có thể vẫn thành công.
2. Checkstyle quét source `Main.java`.
3. Rule `AvoidStarImport` tìm thấy wildcard import.
4. Vi phạm được ghi vào report XML/HTML và có thể xuất hiện ở console.
5. Với `maxErrors=0` và `ignoreFailures` giữ mặc định `false`, **task `checkstyleMain` thất bại**.
6. Lệnh `./gradlew check` hoặc `./gradlew build` cũng không thành công nếu task vi phạm nằm trong graph, do Checkstyle là một quality gate.

Một dòng diagnostic có thể nhắc đến `AvoidStarImport`, source path và line number; **định dạng chính xác phụ thuộc Checkstyle version, đường dẫn OS và report backend**, nên không dùng văn bản lỗi cụ thể làm stdout cam kết.

Sau đó sửa lại:

~~~java
import java.util.List;
~~~

và chạy:

~~~bash
./gradlew checkstyleMain --console=plain
./gradlew check --console=plain
~~~

Nếu source được lưu đúng, rule trở lại pass.

### 5.1. Vi phạm style khác lỗi biên dịch

`import java.util.*;` có thể là **Java code hợp lệ** nhưng vi phạm style của tổ chức. Vì vậy:

~~~text
compileJava       -> có thể PASS
checkstyleMain    -> FAIL do AvoidStarImport
check            -> FAIL vì phụ thuộc checkstyleMain
build            -> FAIL vì phụ thuộc check
~~~

Khi `checkstyleMain` phụ thuộc `classes`, build có thể compile trước khi kiểm tra style. Nếu Java source **không biên dịch được**, Checkstyle task có thể chưa được thực thi vì prerequisite compile thất bại; điều đó không có nghĩa XML rule không phát hiện lỗi style, chỉ là task chưa chạy.

### 5.2. Thử vi phạm LineLength

Trong `Main.java`, có thể viết một dòng source trên 120 ký tự, ví dụ một Java comment rất dài. `LineLength` báo warning/error tùy severity của rule và cấu hình.

Để thử một cách kiểm soát, thêm một comment Java được viết trên **một dòng thật**, dài hơn giới hạn 120 ký tự trong XML. Sau thử nghiệm, tách dòng ngắn lại để trở về pass.

Đừng dùng một đoạn string literal kéo dài chỉ để đạt 120 ký tự nếu nó làm code khó đọc; mục tiêu là hiểu cách rule đo độ dài dòng.

## 6. Checkstyle tasks và lifecycle check/build

Với Java plugin, những task thông dụng:

| Lệnh | Kết quả chính | Có chạy các unit tests không? |
| --- | --- | --- |
| `./gradlew checkstyleMain` | Scan production Java source | Không mặc định |
| `./gradlew checkstyleTest` | Scan test Java source | Không mặc định (có thể biên dịch test) |
| `./gradlew check` | Run Checkstyle và các verification tasks đã gắn, trong đó có `test` | Có theo Java plugin convention |
| `./gradlew build` | `assemble` và `check`, bao gồm quality gates | Có theo Java plugin convention |
| `./gradlew assemble` | Tạo JAR/artifacts | Không mặc định |
| `./gradlew test` | JUnit Test task | Có, nhưng không mặc định scan Checkstyle |
| `./gradlew check --continue` | Cố chạy các verification khác không phụ thuộc task fail | Có thể, build vẫn fail khi vi phạm còn tồn tại |

`checkstyleMain` **không cần test pass** mới có quyền phân tích mã production; nhưng plugin có dependency tới `classes`, vì vậy Gradle có thể phải compile các class source tương ứng trước khi scan.

### 6.1. Tại sao checkstyleTest quan trọng?

Java test code cũng là code được duy trì trong repository. Nếu bạn chỉ chạy `checkstyleMain`, một wildcard import trong `GreeterTest` **không bị checkstyleMain kiểm tra**. `checkstyleTest` mới quét test sources.

Nếu tổ chức chủ động có quy tắc khác cho test (ví dụ cho phép tên method dài), hãy mô tả scope hoặc suppression rõ ràng. Không vô tình loại toàn bộ test source khỏi Checkstyle mà không biết quality gate đang thu hẹp.

### 6.2. Source set bổ sung

Gradle Checkstyle plugin tạo task theo những Java source sets do plugin quản lý. Nếu bạn khai báo `integrationTest` source set, có thể xuất hiện `checkstyleIntegrationTest` tùy cấu hình source set và version Gradle.

Nếu team muốn chỉ scan những source sets cụ thể, Gradle extension có `sourceSets`. **Chỉnh sourceSets của Checkstyle có thể thay phạm vi của `check`**, vì vậy cần ghi rõ policy và test task graph.

## 7. Những file cấu hình Checkstyle và đường dẫn mặc định

Gradle Checkstyle plugin mặc định tìm:

~~~text
<root-project>/config/checkstyle/checkstyle.xml
~~~

và những file liên quan có thể ở cùng directory:

~~~text
config/checkstyle/
├── checkstyle.xml
└── suppressions.xml
~~~

`configDirectory` là nơi chứa các file policy, mặc định tính từ **root project**. `config`/`configFile` cho biết file XML chính. Trong Gradle mới, `config` dạng TextResource có thể thay thế `configFile`, nên ưu tiên DSL được tài liệu version-specific khuyến nghị.

### 7.1. Dùng đường dẫn riêng

Trong `build.gradle.kts`:

~~~kotlin
checkstyle {
    toolVersion = "10.24.0"

    configDirectory.set(
        rootProject.layout.projectDirectory.dir("quality/checkstyle")
    )
}
~~~

Nếu dùng đoạn này, file chính theo mặc định cần nằm tại:

~~~text
quality/checkstyle/checkstyle.xml
~~~

Đây là **mẫu thay thế** cho `configDirectory` trong bài thực hành phần 4, không dùng đồng thời hai đường dẫn.

Bạn cũng có thể đặt config XML từ resource khác bằng `config` nếu đang dùng shared convention plugin; phải chắc chắn Gradle tracking inputs và Checkstyle runtime nhìn thấy file.

### 7.2. `configDirectory` và `${config_loc}`

Gradle cung cấp biến Checkstyle XML **`${config_loc}`** để trỏ tới directory đã cấu hình. Nó hữu ích khi file XML cần tải `suppressions.xml` bằng đường dẫn nhất quán trên Linux/Windows/CI.

Không hard-code đường dẫn tuyệt đối kiểu `C:\Users\...` hoặc `/home/name/...` trong Checkstyle XML vì file đó có thể fail trên máy khác.

### 7.3. Tại sao không chỉ copy tên file từ IDE?

IDE có thể chạy plugin Checkstyle của riêng nó, với version, classpath và config file khác Gradle. Nếu IDE cho kết quả khác CI, so:

- Gradle `toolVersion` với Checkstyle engine version của IDE.
- Đúng `checkstyle.xml` (không phải một file Google/Sun style mặc định khác).
- `configDirectory` và suppressions.
- JDK dùng chạy Checkstyle.
- File sources/exclusions và severity.
- Line ending/encoding.

**Gradle build script + committed Checkstyle XML** nên là source-of-truth để CI tái lập kết quả.

## 8. Tìm hiểu các module phổ biến trong Checkstyle XML

XML là một **cây modules**, không phải một danh sách flags phẳng. Ví dụ:

~~~text
Checker
├── LineLength
├── FileTabCharacter
├── SuppressionFilter
└── TreeWalker
    ├── AvoidStarImport
    ├── NeedBraces
    ├── MethodName
    └── EmptyBlock
~~~

Khi phát triển policy, thêm rule một cách có chủ đích và xem tài liệu chính thức về **supported parent** của module.

### 8.1. Ví dụ mở rộng nhiều rules

`config/checkstyle/checkstyle.xml` có thể được mở rộng như sau, thay thế toàn bộ XML tối thiểu ở phần 4:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">

<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="LineLength">
        <property name="max" value="120"/>
    </module>

    <module name="FileTabCharacter">
        <property name="eachLine" value="true"/>
    </module>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
        <module name="NeedBraces"/>
        <module name="MethodName"/>
    </module>
</module>
~~~

Đây là một bộ rules cơ bản; nó **không tương đương** toàn bộ Google Java Style hoặc Sun Checks. Các rule như `NeedBraces` có thể làm code legacy fail vì cú pháp `if (x) return;`. Thêm từng rule, review tác động và tạo guidelines để developer sửa đúng.

### 8.2. Severity của rule

Checkstyle cho phép mỗi rule có severity, ví dụ:

~~~xml
<module name="LineLength">
    <property name="max" value="120"/>
    <property name="severity" value="warning"/>
</module>
~~~

Đây là một **mảnh XML thay thế cho module LineLength**, không chèn cả hai modules LineLength trùng nhau nếu không có lý do.

Nếu severity `warning`, kiểm soát việc build fail không chỉ là `maxErrors` mà còn phụ thuộc **`maxWarnings`**. Ngưỡng Gradle mặc định đối với warnings có thể không chặn build; nên nêu rõ chính sách:

~~~kotlin
checkstyle {
    maxErrors = 0
    maxWarnings = 0
}
~~~

Ở đây, nếu có một warning thực sự, task Checkstyle cũng có thể fail. Nếu policy muốn warnings chỉ để theo dõi mà chưa chặn PR, đặt ngưỡng phù hợp và lưu báo cáo; đừng tuyên bố `maxErrors=0` tự chặn mọi warning severity.

### 8.3. Rule càng nhiều không có nghĩa càng tốt

Một ruleset có hàng trăm checks chưa được team hiểu có thể tạo tiếng ồn, ngoại lệ tràn lan và giảm niềm tin vào CI. Ưu tiên tập rule nhỏ nhưng có giá trị, ví dụ imports, naming, brace style, tabs, line endings, rồi mở rộng khi nhóm đã có khả năng sửa và review.

Không suy luận `GoogleChecks` là một lớp có thể chỉ viết tên file bất kỳ rồi Checkstyle tự tải toàn bộ style. Nếu dùng Google Java Style/Sun Checks, lấy **config XML chính thức phù hợp phiên bản** và quản lý nội dung trong Git để CI ổn định.

## 9. Báo cáo Checkstyle: Console, XML, HTML và SARIF

Gradle Checkstyle tasks có báo cáo phục vụ developer và CI.

Các đường dẫn điển hình của project `gradle-checkstyle-demo`:

~~~text
build/reports/checkstyle/
├── main.xml
├── main.html
├── test.xml
└── test.html
~~~

Đường dẫn thực tế có thể thay đổi nếu `checkstyle.reportsDirectory` hoặc per-task reports destinations bị tùy biến. **HTML là báo cáo để người đọc mở bằng trình duyệt; XML dễ phân tích tự động trong CI**. Nếu một task không có source, report của nó có thể không xuất hiện; kiểm tra task outcome trước khi suy đoán.

### 9.1. Bật reports cho tất cả Checkstyle tasks

Kotlin DSL:

~~~kotlin
import org.gradle.api.plugins.quality.Checkstyle

tasks.withType<Checkstyle>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}
~~~

Nếu IDE plugin chỉ xem XML, vẫn nên bật HTML để developer review trực quan khi cần.

### 9.2. Tùy chỉnh output folder

Extension cung cấp `reportsDirectory` trong những Gradle versions hỗ trợ:

~~~kotlin
checkstyle {
    reportsDirectory.set(
        layout.buildDirectory.dir("quality-reports/checkstyle")
    )
}
~~~

Đây là **cấu hình thay thế** cho thư mục reports mặc định; phải kiểm tra Gradle Wrapper vì API `reportsDirectory` có thể là incubating ở một số phiên bản.

Không ghi report HTML/XML vào source directory được commit cùng code; để chúng dưới `build/` và lưu artifacts trong CI theo retention policy.

### 9.3. Báo cáo SARIF

Checkstyle hỗ trợ SARIF report từ Checkstyle **10.3.3 trở lên** theo Gradle docs. SARIF hữu ích khi muốn tích hợp static analysis với những nền tảng hỗ trợ chuẩn **Static Analysis Results Interchange Format**.

Kotlin DSL:

~~~kotlin
tasks.withType<Checkstyle>().configureEach {
    reports {
        sarif.required.set(true)
    }
}
~~~

Ví dụ này chỉ nên dùng khi **Checkstyle engine version và Gradle plugin API** hỗ trợ. Với `toolVersion="10.24.0"` ở bài lab, yêu cầu tối thiểu từ Gradle docs được đáp ứng. Không giả định mọi CI/Git service sẽ tự import file SARIF; một bước upload/publish riêng có thể cần quyền và cấu hình.

### 9.4. Custom HTML stylesheet

Gradle Checkstyle plugin còn hỗ trợ XSLT để tùy biến HTML report. Đây là nhu cầu nâng cao; chỉ làm khi tổ chức cần format báo cáo riêng và đã kiểm tra stylesheet hợp lệ. Một stylesheet sai có thể làm task report fail dù engine quét source thành công.

Giữ default HTML/XSLT của Gradle thường đơn giản và dễ bảo trì hơn.

### 9.5. Chạy Checkstyle nhưng không thấy stdout

Một task có thể pass mà chỉ in ít log; không đồng nghĩa Checkstyle không làm gì. Xem:

~~~bash
./gradlew checkstyleMain --console=plain
~~~

và đọc report/Gradle task outcome. Nếu cần kiểm tra lần chạy mới:

~~~bash
./gradlew checkstyleMain --rerun-tasks --console=plain
~~~

`--rerun-tasks` làm task được chọn chạy lại thay vì dùng UP-TO-DATE/cache state; **không tự đổi Checkstyle XML hoặc sửa vi phạm**.

## 10. Severity, maxErrors, maxWarnings và ignoreFailures

Có ít nhất hai tầng quyết định một vi phạm có làm Gradle build fail hay không:

1. **Checkstyle XML** quyết định rule nào bật và severity của vi phạm.
2. **Gradle Checkstyle plugin** quyết định ngưỡng chấp nhận/error behavior qua `maxErrors`, `maxWarnings` và `ignoreFailures`.

| Thiết lập | Tác động |
| --- | --- |
| `maxErrors = 0` | Không dung thứ vi phạm severity ERROR trước khi fail |
| `maxWarnings = 0` | Không dung thứ vi phạm severity WARNING trước khi fail |
| `showViolations = true` | Hiển thị violation details trên console |
| `isIgnoreFailures = false` | Giữ Checkstyle vi phạm là lỗi build theo policy |
| `isIgnoreFailures = true` | Cho phép build tiếp dù có lỗi Checkstyle, thường không phù hợp quality gate bắt buộc |

Trong Gradle 9.x Checkstyle docs, `maxErrors` mặc định là 0, còn `maxWarnings` mặc định không giới hạn. Vì vậy **một rule severity WARNING không nhất thiết làm CI fail** nếu bạn chưa đặt `maxWarnings=0`.

### 10.1. Policy nghiêm ngặt

Mảnh Checkstyle extension thay thế:

~~~kotlin
checkstyle {
    toolVersion = "10.24.0"
    maxErrors = 0
    maxWarnings = 0
    showViolations = true
    isIgnoreFailures = false
}
~~~

Khi dùng DSL `isIgnoreFailures`, cần đối chiếu property accessors của Gradle Kotlin DSL/version bạn đang dùng; nếu không có lý do đặc biệt, có thể **để mặc định false**, tránh viết một dòng gây nhầm API. Trong Groovy DSL, property thường viết `ignoreFailures = false`.

### 10.2. Khi nào nên tạm ignoreFailures?

Có thể dùng trong giai đoạn khảo sát code legacy để **thu thập reports** mà chưa chặn toàn bộ build. Nhưng điều này cần ghi rõ là “audit mode”, có deadline, owner và lộ trình giảm vi phạm. Đừng để CI release dùng `ignoreFailures=true` rồi tuyên bố mã đã đạt style standards.

`ignoreFailures=true` không có nghĩa Checkstyle đã pass: báo cáo vẫn có violations. CI phải đọc status/report thật, không chỉ nhìn `BUILD SUCCESSFUL`.

### 10.3. Max warnings khác compiler -Werror

Javac `-Werror` xử lý **compiler warnings** (deprecated APIs, unchecked conversions...). Checkstyle `maxWarnings` xử lý **Checkstyle violations severity WARNING**. Hai công cụ có thể báo trên cùng file source, nhưng chúng có hệ thống rules/report riêng.

Không đưa `-Werror` vào Gradle Checkstyle XML, và không đặt `maxWarnings=0` rồi mong javac dừng vì một warning generic.

## 11. Suppressions: ngoại lệ có kiểm soát

Một số code có thể cần ngoại lệ: generated code, một method có tên bắt buộc do external interface, một file legacy đang được migrate. Checkstyle hỗ trợ **SuppressionFilter** và file `suppressions.xml` để cho phép bỏ qua những violations có phạm vi xác định.

**Điều cần tránh:** biến suppression thành cách tắt toàn bộ quy tắc cho cả source tree khi chỉ có một nơi đặc biệt.

### 11.1. Thêm SuppressionFilter trong checkstyle.xml

Mảnh XML cần đặt **trực tiếp dưới `Checker`**:

~~~xml
<module name="SuppressionFilter">
    <property
        name="file"
        value="${config_loc}/suppressions.xml"/>
    <property name="optional" value="false"/>
</module>
~~~

`config_loc` do Gradle plugin cung cấp dựa trên `configDirectory`. `optional=false` báo cấu hình không được tùy ý thiếu suppression file. Không hard-code đường dẫn theo máy cá nhân.

### 11.2. File suppressions.xml minh họa

**config/checkstyle/suppressions.xml**

~~~xml
<?xml version="1.0"?>
<!DOCTYPE suppressions PUBLIC
    "-//Checkstyle//DTD SuppressionFilter Configuration 1.2//EN"
    "https://checkstyle.org/dtds/suppressions_1_2.dtd">

<suppressions>
    <suppress
        checks="LineLength"
        files=".*[\\/]generated[\\/].*"/>
</suppressions>
~~~

Ví dụ minh họa nhằm bỏ qua `LineLength` đối với paths chứa directory `generated`, **không bỏ `AvoidStarImport` hoặc mọi rule**. Regular expression được Checkstyle/Java xử lý; separator và path normalization có thể khác nhau giữa hệ điều hành/Checkstyle version, nên **kiểm tra thật trên Linux/Windows** trước khi chốt suppression.

Nếu generated sources không thuộc Java source sets Checkstyle quét, suppression trên có thể không có tác dụng vì chúng vốn chưa nằm trong scan.

### 11.3. Cần thiết lập ownership của exceptions

Mỗi ngoại lệ nên có:

- Lý do nghiệp vụ hoặc giới hạn của generated code.
- File/rule cụ thể cần bỏ.
- Owner chịu trách nhiệm.
- Điều kiện hoặc thời hạn review lại.
- Test/CI bảo đảm phần còn lại của mã vẫn được kiểm tra.

Với nhóm lớn, một thay đổi `suppressions.xml` cần code review nghiêm túc như thay XML rules, vì nó **thay đổi chất lượng yêu cầu**, không chỉ sửa tài liệu.

### 11.4. Đừng sửa rule khi chỉ cần sửa code

Với `AvoidStarImport`, sửa `import java.util.*;` thành các imports tường minh thường rất nhanh. Không thêm suppression chỉ vì developer muốn tránh một chỉnh sửa nhỏ. Suppression nên dành cho ngoại lệ khó tránh, có căn cứ.

## 12. ConfigProperties: tái sử dụng XML có tham số

Khi nhiều module dùng cùng một Checkstyle XML nhưng có một vài giá trị thay đổi có kiểm soát, Gradle cung cấp `configProperties` để truyền biến vào Checkstyle config.

Ví dụ XML:

~~~xml
<module name="LineLength">
    <property name="max" value="${lineLengthLimit}"/>
</module>
~~~

Trong Kotlin DSL:

~~~kotlin
checkstyle {
    configProperties = mapOf(
        "lineLengthLimit" to "120"
    )
}
~~~

Đây là **hai mảnh cấu hình thay thế cho cách đặt max="120" trực tiếp trong bài lab**. Nếu bạn dùng XML có `${lineLengthLimit}` mà quên khai báo property trong Gradle, Checkstyle có thể fail lúc load XML.

### 12.1. Không thay thế config_loc một cách vô ý

`config_loc` là biến tích hợp do plugin khai báo để hỗ trợ file paths trong Checkstyle. Nếu bạn tự đặt một property trùng tên hoặc dùng một configProperties map thay thế không bảo toàn biến nội bộ ở Gradle version tương ứng, các đường dẫn suppressions có thể không đúng.

Ưu tiên để Gradle quản lý `config_loc`; chỉ đặt những biến tổ chức thực sự cần. Một khi dùng nhiều source sets/modules, hãy kiểm tra cả XML của Checkstyle task main/test.

### 12.2. Không dùng configProperties để nhúng secrets

Checkstyle config không cần token/password để kiểm tra Java style. Mọi giá trị trong configProperties có thể xuất hiện trong task inputs, logs hoặc reports khi lỗi; không đặt credentials nội bộ vào đây.

## 13. Chọn phiên bản Checkstyle phù hợp với JDK

Checkstyle là một Java application và có **yêu cầu JDK để chạy**. Project source có thể target Java 8 hoặc Java 17, nhưng Checkstyle engine version mới có thể cần JDK mới hơn.

Theo Gradle docs tại thời điểm tham khảo:

- Checkstyle **10.24.0** là một version hợp lệ cho bài lab, yêu cầu JDK 11+.
- Checkstyle **13.0.0 trở lên** yêu cầu JDK 21+.
- Các version khác có compatibility matrix riêng cần xem tài liệu Checkstyle.

**Đừng nhầm JDK chạy Checkstyle với Java release của code đang được phân tích**. Một project có `options.release.set(17)` có thể chạy Checkstyle bằng JDK 21 khi Checkstyle version yêu cầu, mà không buộc bytecode production thành Java 21.

### 13.1. Cấu hình javaLauncher cho Checkstyle tasks

Mảnh bổ sung khi tổ chức cần dùng Checkstyle engine chạy trên một JDK cụ thể:

~~~kotlin
import org.gradle.api.plugins.quality.Checkstyle

tasks.withType<Checkstyle>().configureEach {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
~~~

Với Checkstyle 10.24.0, JDK 17 là phù hợp. Nếu nâng engine lên phiên bản yêu cầu JDK 21, phải chọn launcher 21 theo compatibility docs và bảo đảm CI có/provision JDK đó.

Gradle Checkstyle plugin có thể chọn Java version theo Gradle JVM hoặc project toolchain nếu cấu hình mặc định; `javaLauncher` hữu ích khi cần kiểm soát độc lập.

### 13.2. ToolVersion không phải Gradle version

~~~kotlin
checkstyle {
    toolVersion = "10.24.0"
}
~~~

là phiên bản **Checkstyle engine**, không phải `gradle-wrapper.properties` distribution version, Java sourceCompatibility, JUnit version hoặc Maven dependency của app.

Khi nâng `toolVersion`, một số rule names, module properties, AST support hoặc message texts có thể thay đổi. Cần chạy `checkstyleMain`, `checkstyleTest`, review violation diffs và kiểm tra JDK trước khi merge.

### 13.3. Thiếu Checkstyle dependency

Nếu task fail vì không resolve `com.puppycrawl.tools:checkstyle`, nguyên nhân có thể là repository bị chặn, thiếu Maven mirror hoặc version không có artifact. Hãy kiểm tra Gradle plugin `repositories`, `checkstyle` configuration và network, không tự sửa sang `implementation(...)` của ứng dụng.

Trong môi trường khóa chặt repository, có thể phải đưa Checkstyle engine cùng dependencies vào mirror được cho phép. Không tắt verification hoặc chuyển sang HTTP không an toàn để vượt qua lỗi tải.

## 14. Multi-project Java: chia sẻ Checkstyle policy

Một monorepo có nhiều modules:

~~~text
root/
├── settings.gradle.kts
├── config/checkstyle/checkstyle.xml
├── core/build.gradle.kts
├── api/build.gradle.kts
└── app/build.gradle.kts
~~~

Bạn có thể áp `java` và `checkstyle` cho từng Java subproject cần kiểm tra, rồi cho chúng dùng **cùng một config directory ở root**.

Ví dụ trong mỗi subproject `build.gradle.kts`:

~~~kotlin
plugins {
    `java-library`
    checkstyle
}

checkstyle {
    toolVersion = "10.24.0"
    configDirectory.set(
        rootProject.layout.projectDirectory.dir("config/checkstyle")
    )
}
~~~

**Mảnh này giả định** root thực sự có `config/checkstyle/checkstyle.xml` và project cần Java plugin tương ứng. Nếu một subproject chỉ là BOM platform (`java-platform`) hoặc native project, không nên áp Java/Checkstyle chỉ vì nó có cùng repository.

### 14.1. Convention plugin tốt hơn sao chép

Khi có 10–50 subprojects, việc copy khối plugin/config vào từng module dễ gây version drift. Nên tạo **convention plugin** ở `build-logic` hoặc `buildSrc` (phù hợp kiến trúc hiện tại), chịu trách nhiệm:

1. Áp dụng Checkstyle cho những Java subprojects phù hợp.
2. Pin `toolVersion`.
3. Đặt `configDirectory` về đường dẫn dùng chung.
4. Cấu hình reports và quality-gate thresholds.
5. Quản lý rule additions và suppression reviews.
6. Tạo CI task selection thống nhất.

Đừng viết một root `subprojects { ... }` khổng lồ khi kiến trúc build đã ưu tiên isolated/convention plugins; nó có thể ảnh hưởng configuration cache/isolation trong Gradle hiện đại.

### 14.2. Lệnh có path theo project

~~~bash
./gradlew :core:checkstyleMain --console=plain
./gradlew :app:checkstyleTest --console=plain
./gradlew :app:check --console=plain
./gradlew build --console=plain
~~~

`./gradlew :app:check` chỉ nhắm quality gate của `:app` và những prerequisites được graph kéo vào, **không tự có nghĩa `:core:checkstyleMain` cũng được quét**. Nếu CI yêu cầu mọi Java module tuân style, phải chọn đúng các module tasks hoặc task aggregation/convention được quản lý.

### 14.3. Riêng generated Java source

Các file `.java` do annotation processor/code generator tạo ra có thể có style khác code thủ công. Checkstyle task mặc định dựa trên source sets nên tùy generator có đăng ký generated sources vào source set và file tree được scan hay không.

Cách xử lý nên theo thứ tự:

1. Xác định generated sources **có thực sự nằm trong Checkstyle source inputs** không.
2. Nếu không, không cần suppression.
3. Nếu có, ưu tiên cấu hình generator output đúng `build/generated/...` và kiểm tra khả năng exclude chính xác từ Checkstyle source.
4. Nếu bắt buộc suppression, giới hạn path và rule cụ thể, kèm lý do.
5. Không exclude toàn bộ thư mục Java production vì một số generated file.

## 15. CI: đưa Checkstyle thành quality gate

Một CI job kiểm tra chất lượng Java có thể chạy:

~~~bash
set -e
./gradlew --version
./gradlew check --console=plain
~~~

Với Java plugin, `check` bao gồm `test`, `checkstyleMain` và `checkstyleTest` (cùng những verification tasks được plugins khác gắn vào). Khi Checkstyle violations vượt ngưỡng và `ignoreFailures` không bị bật, Gradle trả exit code khác 0, giúp CI fail.

### 15.1. Vì sao không chỉ gọi assemble?

~~~bash
./gradlew assemble
~~~

Tạo JAR, nhưng theo Java plugin convention **không chạy Checkstyle**. Nếu một job có mục tiêu kiểm tra code quality, gọi `check` hoặc `build`, không chỉ `assemble`.

### 15.2. Upload reports lên CI

Các file reports như:

~~~text
build/reports/checkstyle/main.html
build/reports/checkstyle/main.xml
build/reports/checkstyle/test.html
build/reports/checkstyle/test.xml
~~~

có thể được giữ làm CI artifacts, giúp reviewer xem vi phạm sau khi job fail. Trên GitHub Actions, GitLab hoặc Jenkins cần cấu hình upload artifacts tương ứng; Gradle Checkstyle plugin **không tự upload** reports lên hệ thống quản lý PR.

**Không publish HTML/XML chứa source paths hoặc tên module nội bộ tới nơi công khai nếu policy tổ chức không cho phép.** Thời gian lưu artifacts cũng cần theo quy định nhóm.

### 15.3. Audit mode và enforced mode

Với codebase legacy, có thể chia làm hai giai đoạn:

1. **Audit:** chạy Checkstyle và lưu reports, thống kê vi phạm; có thể dùng ignoreFailures tạm thời ở job riêng và đặt milestone.
2. **Enforced:** sau khi dọn code và exceptions, giữ `maxErrors=0`, kiểm soát warnings, không bật ignoreFailures và chặn PR nếu phát sinh vi phạm mới.

Dự án lớn có thể áp policy theo module hoặc chọn các rule mới trước khi mở rộng. Tránh ngưỡng vi phạm quá cao làm rule mất ý nghĩa.

### 15.4. Không tự sửa XML trong job CI

Một job kiểm tra read-only **không nên** tự nới rule/suppression hoặc đổi threshold để cho build thành công. Những thay đổi policy phải nằm trong PR được review, cùng thay đổi source code nếu cần.

### 15.5. `--continue` để thu thập nhiều báo cáo

~~~bash
./gradlew check --continue --console=plain
~~~

Gradle cố chạy những task khác không phụ thuộc task đã fail. Điều này hữu ích để gom reports `checkstyleMain`, `checkstyleTest`, `test` trong một lần, nhưng **build vẫn fail** nếu violations/failing tests còn tồn tại.

### 15.6. `-x checkstyleMain` bỏ quality gate

~~~bash
./gradlew build -x checkstyleMain
~~~

Lệnh này loại `checkstyleMain` khỏi task graph. Nó có thể hữu ích khi debug packaging, nhưng **không phải bản build đã vượt qua Checkstyle**. Đừng giữ trong release CI hoặc ghi `style pass` chỉ dựa vào `BUILD SUCCESSFUL`.

## 16. Checkstyle reports, cache và task execution

Gradle có thể đánh dấu Checkstyle task:

- `UP-TO-DATE`: inputs/outputs vẫn hợp lệ.
- `FROM-CACHE`: kết quả được restore từ build cache khi task cacheable và input keys khớp.
- `NO-SOURCE`: source file tree không có files cần scan.
- `SKIPPED`: task bị bỏ do condition/disable hoặc chế độ đặc biệt.
- `FAILED`: engine/configuration/violation threshold làm task fail.

**Không thấy violations trên console** khi task `UP-TO-DATE` không có nghĩa code không được kiểm tra trước đó; nó có thể dùng output lần chạy thành công. Tuy nhiên CI phải bảo đảm task source inputs, config XML và classpath được track đầy đủ và không có exclusions vô tình.

### 16.1. Vì sao sửa XML làm task cần chạy lại?

Checkstyle XML là **cấu hình đầu vào** của Checkstyle task. Khi rule thay đổi, task output (violations/report) có thể thay; Gradle cần đánh giá lại. Không tự sửa XML trong `doFirst` hoặc task action nếu điều đó khiến Gradle input snapshot không nhận ra.

### 16.2. Chẩn đoán với --info

~~~bash
./gradlew checkstyleMain --info --console=plain
~~~

Giúp thấy reasons task chạy/skip, process/classpath hoặc vấn đề configuration. Log có thể chứa local paths/internal names; không tự động gửi public log nếu có thông tin nhạy cảm.

### 16.3. Chạy lại có chủ đích

~~~bash
./gradlew checkstyleMain --rerun-tasks --console=plain
~~~

Yêu cầu task actions chạy lại thay vì coi up-to-date; thường không cần cho các build phát triển hàng ngày, chỉ dùng khi điều tra cache/config.

## 17. Những lỗi phổ biến khi thiết lập Checkstyle

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `checkstyleMain` không tồn tại | Chưa apply plugin hoặc project không có Java source set | Áp `java` và `checkstyle` đúng module |
| `checkstyle.xml` not found | File sai path, configDirectory sai | Đặt đúng ở root/config/checkstyle |
| Checkstyle XML parse error | Sai cấu trúc XML/DTD/escaping | Kiểm tra module tree và XML validator |
| Cannot initialize module `TreeWalker` | Rule đặt sai parent hoặc version không hỗ trợ property | Đối chiếu Checkstyle rules docs |
| Unknown property for module | Property đã đổi hoặc module sai version | Pin phiên bản, cập nhật XML phù hợp |
| External DTD load disabled | Cấu hình tham chiếu DTD/remote resource khác chuẩn | Dùng DTD chuẩn/tài nguyên được tin, không bật DTD ngoại lai bừa |
| `AvoidStarImport` báo import | Source có `java.util.*` | Chuyển sang explicit imports |
| LineLength liên tục fail | Limit quá thấp hoặc một số file rất dài | Cập nhật code, review đúng rule/severity |
| Checkstyle chạy trên generated code | Generated files nằm trong Checkstyle source set | Exclude chính xác hoặc suppression có lý do |
| `suppressions.xml` không tìm thấy | `${config_loc}` sai hoặc configDirectory khác | Xác nhận file path và property |
| Suppression không tác dụng | Rule name/path regex không match | Dùng report XML để xác định `source`, file và check name |
| Cấu hình khác nhau giữa IDE và CI | IDE engine/version/XML/JDK khác | Dùng Gradle build config là source-of-truth |
| Task fail dù Java compile pass | Style violation không phải compile error | Xem Checkstyle report, sửa code |
| `check` không quét test Java | Plugin thiếu, test source set không đúng, task bị excluded | Kiểm tra `checkstyleTest` trong graph |
| `build` thành công khi có warnings | `maxWarnings` chưa bật gate hoặc warnings nằm ngoài scope | Cân nhắc maxWarnings=0, kiểm tra XML severities |
| `build` thành công dù errors | ignoreFailures=true, task disabled/excluded, project không scan | Review DSL và task graph |
| Memory OOM khi check | Worker Checkstyle heap không đủ | Cấu hình `maxHeapSize` theo tài nguyên |
| Unsupported class file / Java version | ToolVersion Checkstyle không hợp JDK hoặc Java syntax mới | Chọn engine/JDK tương thích |
| File được scan hai lần | Source sets/source collection trùng | Xem sourceSets và Checkstyle task inputs |
| Checkstyle report không xuất hiện | Task NO-SOURCE, reports disabled hoặc path tùy chỉnh | Xem outcomes và reportsDirectory |
| Task báo UP-TO-DATE, không thấy lỗi mới | Source/config có thể chưa đổi đúng path hoặc cache | Xác minh paths, chạy --rerun-tasks |
| Checkstyle JAR resolve fail | Không có repository/network/mirror | Sửa repository và version, không đưa vào app implementation |
| SARIF output không có | Engine quá cũ hoặc report chưa bật | Check 10.3.3+ và `sarif.required` |
| Không chạy ở multi-module | Chỉ apply Checkstyle cho root, modules thiếu plugin | Áp convention plugin cho Java modules |
| Quality gate bị bypass | CI dùng assemble hoặc -x checkstyleMain | Chạy check/build đúng policy |
| XML có DTD bất thường | Nguy cơ remote external DTD loading | Không bật external DTD load trừ khi được bảo vệ/đánh giá |

## 18. Một số tình huống phân tích thực tế

### 18.1. Vi phạm do imports tự động của IDE

Một IDE có thể tự đổi nhóm imports thành `import java.util.*;` khi số imports vượt ngưỡng. Với XML bật `AvoidStarImport`, file compile đúng nhưng Checkstyle fail.

Hướng xử lý:

1. Dùng Checkstyle XML ở Git làm source-of-truth.
2. Cấu hình IDE imports policy để không tự gom thành wildcard imports.
3. Sửa wildcard imports về explicit imports.
4. Chạy `./gradlew checkstyleMain`.
5. Nếu team đổi policy, sửa XML và IDE template **trong cùng PR**.

Không disable rule rồi tiếp tục để IDE tự tạo code không nhất quán.

### 18.2. Team đổi maxLineLength từ 120 xuống 100

Cấu hình mới có thể tạo nhiều violations trong code cũ.

Một cách rollout hợp lý:

1. Thống kê số violations theo modules.
2. Ước lượng độ khó sửa và tác động đến code generated.
3. Quy định cách wrap method calls, constructors và string literals.
4. Chọn migration theo module hoặc sprint.
5. Với ngoại lệ không thể sửa, suppression cụ thể kèm lý do.
6. Sau khi code hợp lệ, đặt maxErrors/maxWarnings phù hợp.
7. Chạy CI `check` trên toàn bộ phạm vi đã áp.

Một “quy tắc stricter” chỉ có ý nghĩa khi team có cách duy trì và không liên tục bỏ qua báo lỗi.

### 18.3. Mã được sinh tự động có tên không theo style

Generated code thường không nên bị sửa thủ công vì tool sẽ ghi đè. Trước khi tạo suppression:

- Xác nhận file thực sự generated và tool sinh ra file ấy.
- Xem có thể cấu hình generator phù hợp rules không.
- Kiểm tra generated output có nằm ngoài `src/main/java` và Checkstyle source tree không.
- Nếu buộc loại trừ, giới hạn đúng generated directory hoặc checks, ghi lý do.
- Chạy lại test/Checkstyle để đảm bảo production Java code vẫn được scan.

### 18.4. Build fail trên CI nhưng local pass

Có thể do:

- Checkstyle engine version khác vì không pin toolVersion.
- XML config hoặc suppressions không được commit.
- Local Gradle task dùng cache, CI thực thi thật.
- Checkstyle chạy bằng JDK khác.
- Module CI scan khác local, hoặc CI chạy `check` thay vì chỉ `test`.
- Source có line endings/encoding khác.
- IDE chỉ bật một phần rule trong khi Gradle chạy bộ đầy đủ.

Chẩn đoán bằng `./gradlew --version`, `./gradlew checkstyleMain --info`, file reports và so sánh configuration files đã commit. Không dùng `ignoreFailures=true` như “biện pháp sửa” đầu tiên.

## 19. Checkstyle có cần build source trước không?

Theo Gradle Checkstyle plugin, `checkstyleMain` phụ thuộc task `classes`, `checkstyleTest` phụ thuộc `testClasses`. Vì vậy Checkstyle analysis có thể yêu cầu **compile source trước**, mặc dù nhiều style rules chỉ cần parse Java source.

Đây là **task wiring mặc định của plugin**, không đồng nghĩa Checkstyle chạy trên `.class` thay vì `.java`. Nó vẫn phân tích Java source, nhưng classpath/compiled outputs có thể là prerequisites trong Gradle task graph.

Nếu compile fail, Checkstyle có thể chưa chạy. Đừng chỉnh `dependsOn` hoặc `classpath` để cố scan code không compile được khi chưa hiểu plugin implementation; một số checks cần biết type context và source set model.

### 19.1. Nếu chỉ muốn style feedback nhanh

Một cách là tích hợp Checkstyle kiểm tra trong IDE và cùng dùng XML với Gradle. Khi dev save file, IDE có thể cảnh báo sớm; sau đó `./gradlew check` là CI source-of-truth. Tránh dùng IDE-only rule mà Gradle CI không có.

### 19.2. Bỏ JavaCompile có được không?

Gradle plugin mặc định wiring Checkstyle tới `classes`/`testClasses` để hỗ trợ classpath. Tự phá dependency có thể khiến reports sai hoặc Checkstyle tasks fail. Nếu thực sự cần source-only static scan độc lập với compile, cân nhắc dùng cách tích hợp Checkstyle CLI/IDE phù hợp và đặt mục tiêu rõ, không sửa task graph bằng workaround thiếu kiểm chứng.

## 20. Nâng Checkstyle version đúng quy trình

Checkstyle engine có API và các checks thay đổi theo phiên bản. Khi nâng `toolVersion`, không chỉ thay một số mà nên:

1. Đọc release notes của Checkstyle.
2. Kiểm tra **JDK runtime requirement** của version mới.
3. Kiểm tra Checkstyle XML có modules/properties bị đổi hoặc deprecate không.
4. Chạy `checkstyleMain`, `checkstyleTest` hoặc `check`.
5. Review số lượng vi phạm mới, sự khác biệt severity/messages.
6. Sửa code hoặc rules có căn cứ.
7. Kiểm tra suppressions vẫn match.
8. Review XML/HTML/SARIF reports nếu tích hợp hệ thống khác.
9. Pin version mới trong build policy hoặc convention plugin.
10. Commit cùng review, không tự nâng checkstyle dependency transitive bằng tay.

**Không suy luận engine version theo Gradle wrapper version.** Gradle plugin chỉ tích hợp Checkstyle; quy tắc và AST behavior phụ thuộc Checkstyle toolVersion.

### 20.1. Vì sao cần pin toolVersion?

Nếu Gradle default Checkstyle version thay đổi theo Gradle release và team đồng thời nâng Wrapper, số lượng violations có thể đổi dù `checkstyle.xml` không thay. Pin `toolVersion` giúp phân biệt **thay đổi engine có chủ đích** với thay đổi Gradle build engine.

### 20.2. Kiểm soát phiên bản rules XML

Rule/check names không luôn ổn định vĩnh viễn. Một Checkstyle XML từ phiên bản quá mới có thể sử dụng property mà engine cũ không hiểu. Hãy chọn **cặp toolVersion + XML** được test cùng nhau thay vì chỉ tải ruleset “mới nhất” từ internet vào CI.

## 21. Bảo mật khi chạy Checkstyle

Bản chất Checkstyle là công cụ chạy trong JVM riêng/worker của Gradle. Ngoài Java sources, engine còn đọc XML config, suppressions và các classpath artifacts.

Những điểm cần giữ:

- Dùng repositories HTTPS/mirror được cho phép.
- Quản lý Checkstyle engine version và dependencies.
- Không bật `enableExternalDtdLoad` khi không có yêu cầu cụ thể và review.
- Không trỏ Checkstyle config vào URL/file remote không tin cậy.
- Không đưa secrets vào `configProperties`, custom rule properties hoặc diagnostic logs.
- Nếu dùng custom Checkstyle modules do bên thứ ba viết, đánh giá nguồn và runtime permissions như đối với build plugins.
- Không chia sẻ report chứa package/class/source paths nội bộ ra nơi công khai khi chính sách không cho phép.

### 21.1. DTD và XML external entities

XML có thể tham chiếu DTD. Checkstyle config trong bài dùng Checkstyle DTD chuẩn. Việc bật **external DTD loading** làm mở rộng những nguồn dữ liệu engine có thể đọc; Gradle tắt theo mặc định vì lý do an ninh. Nếu lỗi XML/Dtd, hãy phân tích cụ thể và ưu tiên DTD chuẩn được Checkstyle nhận diện, không bật tải từ URL bất kỳ.

### 21.2. Cần phân biệt quality gate và security gate

Checkstyle có thể báo việc dùng wildcard imports hoặc naming không nhất quán; nó **không tự phát hiện** toàn bộ lỗ hổng từ dependency versions, JAR bị thay thế, SQL injection hoặc secrets trong Git. Dự án còn cần dependency verification, vulnerability scanning, tests và code review.

## 22. Groovy DSL tương đương

Nếu dùng `build.gradle`, cấu hình tối thiểu:

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

checkstyle {
    toolVersion = '10.24.0'
    configDirectory = rootProject.layout.projectDirectory.dir('config/checkstyle')
    maxErrors = 0
    showViolations = true
}

tasks.withType(Checkstyle).configureEach {
    reports {
        xml.required = true
        html.required = true
    }
}
~~~

Đây là **mẫu tương đương cho Checkstyle**; nếu copy toàn bộ Java/JUnit lab sang Groovy, cần thêm dependencies và `tasks.test { useJUnitPlatform() }` tương ứng.

Không dùng lẫn syntax `plugins { checkstyle }` của Kotlin DSL với Groovy DSL trong cùng một file mà không điều chỉnh.

### 22.1. Gradle Kotlin DSL và Groovy DSL có cùng cơ chế

Cả hai DSL đều áp cùng plugin `checkstyle`, engine và XML rules. Sự khác biệt chủ yếu là syntax cho types/properties, không phải chất lượng kiểm tra. `checkstyle.xml` có thể dùng chung giữa các DSL vì nó là cấu hình Checkstyle, không phải Gradle Kotlin script.

## 23. Bài tập tự kiểm tra

**Câu 1:** Sau khi áp plugin `checkstyle`, nhưng chưa tạo `checkstyle.xml`, `./gradlew check` có tự dùng Google Java Style không?

**Đáp án:** Không. Gradle mặc định tìm một Checkstyle config file theo đường dẫn, không tự thay thế bằng bộ Google Java Style đầy đủ. Cần cung cấp file cấu hình phù hợp.

**Câu 2:** `checkstyleMain` kiểm tra gì?

**Đáp án:** Java source của source set `main`; mặc định Checkstyle plugin gắn task này với `classes` trong graph.

**Câu 3:** `checkstyleTest` có chạy JUnit assertions không?

**Đáp án:** Không. Nó kiểm tra style Java source trong source set test; task `test` mới chạy JUnit tests.

**Câu 4:** `./gradlew check` có bao gồm Checkstyle khi project áp Java và Checkstyle plugins không?

**Đáp án:** Có theo convention; plugin gắn Checkstyle tasks vào lifecycle `check`. Tuy nhiên cần xem task graph/exclusions và actual task outcomes để biết đã scan source thật hay chưa.

**Câu 5:** `./gradlew assemble` có đủ để tuyên bố Java code tuân thủ Checkstyle không?

**Đáp án:** Không. Assemble tập trung tạo artifacts; không mặc định chạy style analysis.

**Câu 6:** Checkstyle XML có `AvoidStarImport`, file chứa `import java.util.*;`. Java compile thành công nhưng Checkstyle fail. Có mâu thuẫn không?

**Đáp án:** Không. Wildcard import hợp lệ trong Java nhưng bị quy tắc style cấm.

**Câu 7:** `maxErrors=0` có làm mọi violation severity WARNING fail không?

**Đáp án:** Không nhất thiết. Warnings có ngưỡng riêng `maxWarnings`; nếu muốn chặn mọi warning, cân nhắc `maxWarnings=0`.

**Câu 8:** Có nên bật `ignoreFailures=true` để CI report xanh khi code bị vi phạm?

**Đáp án:** Không nếu Checkstyle là quality gate bắt buộc. Có thể dùng tạm trong audit mode có lộ trình, nhưng phải đọc reports và không nói là style pass.

**Câu 9:** Vì sao `LineLength` được đặt dưới Checker còn `AvoidStarImport` nằm trong TreeWalker?

**Đáp án:** Checkstyle modules có parent constraints; `LineLength` là file-oriented check, `AvoidStarImport` là AST-based check dùng TreeWalker.

**Câu 10:** Thêm `${config_loc}/suppressions.xml` để làm gì?

**Đáp án:** Để Checkstyle tìm suppression file tương đối với `configDirectory` được Gradle cấu hình, tránh hard-code đường dẫn máy cá nhân.

**Câu 11:** `toolVersion="10.24.0"` có quyết định version Gradle Wrapper hay JDK source target không?

**Đáp án:** Không. Nó chọn Checkstyle engine; JDK runtime cần tương thích với Checkstyle và target Java source có cấu hình riêng.

**Câu 12:** Checkstyle report thường nằm đâu?

**Đáp án:** `build/reports/checkstyle/main.xml`, `main.html`, `test.xml`, `test.html` theo cấu hình mặc định; đường dẫn có thể tùy chỉnh.

**Câu 13:** Khi nào SARIF report được hỗ trợ?

**Đáp án:** Checkstyle 10.3.3 trở lên theo Gradle docs, đồng thời phải bật `sarif.required` và có Gradle plugin API tương ứng.

**Câu 14:** Trong multi-project build, gọi `:app:checkstyleMain` có tự scan `:core` không?

**Đáp án:** Không. Task path của `:app` nhắm source set main của app, không tự scan các source sets của core. CI cần chọn tasks cho đúng modules.

**Câu 15:** Một `suppressions.xml` exclude toàn bộ `src/main/java` có phải cách tốt để “dọn nhanh” legacy violations không?

**Đáp án:** Không. Nó loại bỏ phần quan trọng nhất của quality gate; nên sửa code/migrate có kế hoạch, hoặc dùng ngoại lệ hẹp có lý do.

**Câu 16:** Vì sao IDE không báo nhưng CI Gradle báo `AvoidStarImport`?

**Đáp án:** IDE có thể dùng ruleset/engine/JDK/scan scope khác, hoặc không bật Checkstyle. Cần đồng bộ IDE với committed Gradle Checkstyle config.

**Câu 17:** Dùng `./gradlew checkstyleMain --rerun-tasks` để sửa rule vi phạm đúng không?

**Đáp án:** Không. Nó chạy lại task, không tự sửa Java source hay XML.

**Câu 18:** Một file generated Java có style khác source do dev viết; cần xử lý thế nào?

**Đáp án:** Xác định file có nằm trong Checkstyle source inputs không, ưu tiên generator output đúng vị trí; nếu cần exclude/suppression thì giới hạn chính xác, có owner và review.

## 24. Checklist triển khai trong dự án Java

1. Dùng Gradle Wrapper và JDK được project hỗ trợ.
2. Áp `java`/`java-library` và `checkstyle` trong đúng Java modules.
3. Pin `toolVersion` của Checkstyle engine theo policy.
4. Tạo `config/checkstyle/checkstyle.xml` được commit và review.
5. Đặt đúng module hierarchy `Checker`/`TreeWalker`; chọn rules có giá trị.
6. Giữ source và Checkstyle charset tương thích, ví dụ UTF-8.
7. Chạy `checkstyleMain`, `checkstyleTest` và `check`.
8. Bật XML/HTML reports, tùy nhu cầu thêm SARIF.
9. Chọn thresholds `maxErrors`, `maxWarnings`; không bật ignoreFailures vô thời hạn.
10. Quản lý suppressions hẹp và có lý do; hạn chế generated code exceptions.
11. Dùng `configDirectory` + `${config_loc}` thay đường dẫn máy cá nhân.
12. Với multi-project, dùng convention plugin/shared XML để thống nhất policy.
13. Duy trì cùng toolVersion/XML/JDK giữa local, IDE và CI.
14. Khi nâng Checkstyle, review compatibility và violation diff.
15. Không tắt external DTD protections hoặc bỏ quality gate chỉ để vượt qua CI.
16. Khi build fail, đọc report trước khi chỉnh flags/rules.
17. Không nhầm Checkstyle với javac warnings, JUnit tests, PMD, SpotBugs hay formatter.
18. Kết hợp quality gate với tests, dependency security và code review.

**Ghi nhớ nhanh:**

~~~text
plugins { java; checkstyle }
            |
            v
config/checkstyle/checkstyle.xml
            |
            +-- Checker
            |    +-- LineLength
            |    +-- TreeWalker
            |         +-- AvoidStarImport
            |
            v
checkstyleMain + checkstyleTest
            |
            v
check  ->  build

Vi phạm style: sửa source hoặc thay policy qua review.
Không đồng nghĩa: compile PASS != Checkstyle PASS.
~~~

## 25. Tài liệu chính thức

1. Gradle — The Checkstyle Plugin: https://docs.gradle.org/current/userguide/checkstyle_plugin.html
2. Gradle — CheckstyleExtension DSL: https://docs.gradle.org/current/dsl/org.gradle.api.plugins.quality.CheckstyleExtension.html
3. Gradle — Checkstyle Task DSL: https://docs.gradle.org/current/dsl/org.gradle.api.plugins.quality.Checkstyle.html
4. Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
5. Gradle — Base Plugin lifecycle tasks: https://docs.gradle.org/current/userguide/base_plugin.html
6. Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
7. Checkstyle — Getting Started: https://checkstyle.sourceforge.io/getting-started.html
8. Checkstyle — Configuration reference: https://checkstyle.sourceforge.io/config.html
9. Checkstyle — AvoidStarImport: https://checkstyle.sourceforge.io/checks/imports/avoidstarimport.html
10. Checkstyle — LineLength: https://checkstyle.sourceforge.io/checks/sizes/linelength.html
11. Checkstyle — SuppressionFilter: https://checkstyle.sourceforge.io/filters/suppressionfilter.html
12. Checkstyle — JDK compatibility: https://checkstyle.sourceforge.io/#Requirements

Các liên kết `current` theo tài liệu Gradle đang được công bố tại thời điểm truy cập, không phải phiên bản Wrapper của tất cả dự án. Khi áp dụng thực tế, hãy đối chiếu **Gradle Wrapper**, **Checkstyle toolVersion**, **JDK dùng chạy Checkstyle**, các checks/properties trong XML và convention/CI của tổ chức. Bản XML tối thiểu trong bài là khởi điểm có thể tái tạo, không phải toàn bộ bộ quy tắc cho mọi doanh nghiệp.