# Kiểm tra khả năng hỗ trợ JDK 25 của IDE, công cụ xây dựng và công cụ phân tích

> **Chương:** Thiết lập JDK 25  
> **Học phần:** `JAVA_VERSION_JAVA25` — Java 25 trong phát triển Java hiện đại: compact source files, module import, flexible constructor bodies, ScopedValue, KDF API, AOT cache, JFR và đánh giá nâng cấp JDK.  
> **Phạm vi bài:** Xác minh **toàn bộ chuỗi phát triển** có thể làm việc với JDK 25: IDE, trình biên dịch, Maven/Gradle, kiểm thử, phân tích mã nguồn/bytecode và CI. Chỉ sử dụng các cách tiếp cận còn được hỗ trợ, ưu tiên tính tái lập.

## 1. Vì sao cài được JDK 25 chưa có nghĩa dự án sẵn sàng?

Java 25 là bản phát hành **LTS**, phát hành tháng 9/2025. Tại thời điểm biên soạn (tháng 11/2026), JDK 25 vẫn là lựa chọn hiện hành cho các ứng dụng muốn nền tảng LTS, dù đã có các phiên bản Java phát hành sau đó. Bài này kiểm chứng khả năng làm việc với **Java 25**, không coi việc IDE khởi động hoặc lệnh `java --version` in ra `25` là bằng chứng đủ.

Một ứng dụng có thể vượt qua một lớp nhưng lỗi ở lớp kế tiếp:

- Terminal gọi đúng `java 25`, nhưng `javac` trong `PATH` đến từ JDK 21.
- IDE nhận biết project SDK 25, nhưng **Gradle JVM** vẫn chạy một Gradle Wrapper không hỗ trợ JDK 25.
- Maven thực thi trên JDK 25, nhưng plugin compiler đang dùng `--release 21`, khiến cú pháp Java 25 không được chấp nhận.
- Ứng dụng biên dịch được, song JaCoCo hoặc bytecode analyzer dùng thư viện ASM quá cũ, gây `Unsupported class file major version 69`.
- IDE tô đỏ `import module java.base;` dù `javac --release 25` biên dịch thành công vì Java language server hoặc formatter chưa hiểu cú pháp mới.
- Pipeline chạy `mvn test` thành công ở máy phát triển nhưng CI sử dụng image chứa JDK khác hoặc chưa có toolchain được yêu cầu.

Để kiểm chứng đáng tin cậy, cần xét **năm năng lực độc lập**:

| Năng lực | Câu hỏi quyết định | Phép thử |
|---|---|---|
| **JDK của máy** | Có đúng bản JDK 25 với `java`, `javac`, `jar`, `jfr`? | `java --version`, `javac --version`, đường dẫn executable |
| **IDE** | Editor có hiểu cú pháp Java 25, compile, debug, run test bằng JDK 25? | Import dự án, chạy chương trình smoke-test, debug và kiểm tra IDE/build settings |
| **Build tool** | Maven/Gradle hỗ trợ chạy trên JDK phù hợp **và** chọn javac/test launcher 25? | Wrapper version, toolchain, `--release 25`, `clean test` |
| **Phân tích** | Coverage, lint, static analyzer, annotation processor và bytecode parser hiểu Java 25? | Chạy từng plugin trên class file 69 và cú pháp mới |
| **CI / môi trường chạy** | Pipeline dựng lại kết quả, chạy test và khởi động artifact trên JDK đích? | Reproducible build, test matrix, runtime smoke-check |

Đây là các điều kiện **đồng thời**. Một dòng “supports Java 25” trong release notes của một công cụ có thể chỉ nói về việc **chạy chính công cụ đó trên JDK 25**, chưa bảo đảm nó phân tích được mọi cú pháp Java 25 hay mọi thư viện/plugin đi kèm.

## 2. Chốt tiêu chuẩn Java 25 cần được công cụ hiểu

Để tránh dùng ví dụ preview đã đổi ngữ nghĩa hoặc tính năng đã bị rút, chọn các tính năng **đã trở thành chuẩn trong Java 25** cho smoke-test:

| Tính năng | Trạng thái trong Java 25 | Dùng trong kiểm chứng |
|---|---|---|
| **Module Import Declarations** (JEP 511) | Final/permanent | `import module java.base;` và sử dụng type từ module xuất ra |
| **Compact Source Files and Instance Main Methods** (JEP 512) | Final/permanent | `void main()` ở file nguồn ngắn và `IO.println(...)` |
| **Flexible Constructor Bodies** (JEP 513) | Final/permanent | Kiểm tra cú pháp câu lệnh trước `super(...)` |
| **Scoped Values** (JEP 506) | Final API | Kiểm tra runtime/IDE phù hợp khi dự án thực sự sử dụng |
| **Key Derivation Function API** (JEP 510) | Final API | Kiểm tra security/provider và môi trường sử dụng khi có nhu cầu |
| **Primitive types in patterns, `instanceof`, `switch`** (JEP 507) | **Third preview** ở Java 25 | **Không dùng** làm tiêu chí bắt buộc của project Java 25 production |

`--enable-preview` chỉ dành cho các tính năng preview của đúng JDK đang dùng; không cần bật để chạy **ba tính năng ngôn ngữ đã final** nêu trên. Preview có thể thay đổi giữa các bản phát hành và đôi khi không còn được analyzer đời mới hỗ trợ ở phiên bản Java cũ; chỉ dùng khi đã có quy trình quản lý preview riêng.

Ví dụ trong chương trình gọn, `IO` nằm ở `java.lang`, nên gọi `IO.println("...")`. Cách viết chỉ gọi `println(...)` nhờ nhập tĩnh ngầm trong các bản preview cũ **không còn là cú pháp nên dùng để kiểm chứng Java 25**.

## 3. Kiểm tra JDK thực tế trên máy

Cài JDK 25 từ một nhà phân phối OpenJDK/Oracle có bản vá đang được duy trì và phù hợp kiến trúc hệ điều hành. Khi kiểm tra, ghi lại **vendor, version đầy đủ (gồm bản vá), OS và CPU architecture**. Không cần dùng cùng một vendor trên mọi máy nếu thư viện và yêu cầu hỗ trợ của tổ chức cho phép, nhưng CI cần có nguồn cài đặt kiểm soát được.

### 3.1. Windows PowerShell

```powershell
java --version
javac --version
jar --version

$env:JAVA_HOME
Get-Command java
Get-Command javac
where.exe java
where.exe javac
```

Kiểm tra output mong đợi:

```text
java 25.x ...
javac 25.x
```

`where.exe` có thể cho thấy **nhiều JDK trên PATH**. Nếu `java` và `javac` khác nhau, sửa cấu hình môi trường/terminal trước khi xem lỗi trong IDE. Đối chiếu `JAVA_HOME` với thư mục chứa `bin/java.exe` và `bin/javac.exe`, không đặt `JAVA_HOME` trực tiếp vào thư mục `bin`.

Không dùng `where` thuần trong PowerShell để tránh nhầm alias `Where-Object`; dùng rõ `where.exe`. Sau khi đổi biến môi trường, mở **terminal mới** để tiến trình kế thừa giá trị mới.

### 3.2. Linux / macOS shell

```bash
java --version
javac --version
jar --version

printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
```

Nếu có nhiều JDK, sử dụng cách chọn JDK được hệ điều hành và công cụ quản lý JDK hỗ trợ. Đường dẫn Java có thể đi qua symbolic link, nên `command -v` chỉ là điểm khởi đầu; kiểm tra executable/JDK thực của Java launcher khi cần. Ưu tiên cấu hình toolchain **ở mức dự án** thay vì thay `JAVA_HOME` toàn hệ thống cho từng repository.

### 3.3. Phân biệt bốn vị trí chọn JVM/JDK

```text
JDK dùng chạy IDE / Java language server
               |
               v
JDK dùng chạy Maven hoặc Gradle daemon
               |
               v
JDK compiler/test launcher do Maven/Gradle toolchain chọn
               |
               v
JDK/JRE dùng chạy sản phẩm tại production
```

Bốn vị trí này có thể dùng các bản Java **khác nhau**. `JAVA_HOME` chỉ ảnh hưởng những tiến trình đọc biến đó; Gradle Toolchains, Maven Toolchains và thiết lập IDE có thể ghi đè lựa chọn. Khi báo lỗi, luôn chỉ rõ **đang nói về JDK ở vị trí nào**.

## 4. Bài kiểm tra cú pháp chuẩn Java 25 không phụ thuộc framework

Tạo một file thử `Smoke25.java` trong dự án thử hoặc một thư mục tạm **bên ngoài mã sản phẩm**:

```java
import module java.base;

void main() {
    var values = List.of("JDK", "25");
    IO.println(String.join(" ", values));
}
```

Chương trình dùng hai tính năng **final** của Java 25: `import module` và compact source file/instance `main`; không cần `--enable-preview`.

Thử trực tiếp bằng JDK 25:

```bash
java Smoke25.java
javac --release 25 -d out Smoke25.java
java -cp out Smoke25
javap -verbose out/Smoke25.class
```

Kỳ vọng lệnh chạy in:

```text
JDK 25
```

Kết quả `javap -verbose` chứa **`major version: 69`** đối với class file Java 25 được sinh từ lệnh `javac --release 25`. Bytecode 69 là một dấu hiệu quan trọng để kiểm tra coverage agent, bytecode reader và plugin build.

Nếu code biên dịch ở CLI nhưng IDE báo lỗi cú pháp, nghi vấn đầu tiên nằm ở **editor/language server/compiler setting**, không phải ở bản thân JDK 25. Nếu source chỉ chạy bằng `java Smoke25.java` nhưng không chạy được với `javac --release 25`, cần kiểm tra compiler version và môi trường, thay vì cố bật preview.

Có thể kiểm tra thêm flexible constructor bodies (JEP 513), cũng là cú pháp final:

```java
class PositiveId {
    private final int value;

    PositiveId(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        super();
        this.value = value;
    }
}
```

Nếu công cụ phân tích cú pháp từ chối `super()` sau câu kiểm tra trong constructor, cần xem phiên bản parser/plugin. Không cần đổi thành cú pháp preview hoặc mở `--enable-preview` để chạy ví dụ này trên JDK 25.

> **Lưu ý:** chương trình thử trong bài này dành cho **Java 25**. Nếu sản phẩm vẫn phải chạy trên Java 21, hãy tiếp tục build đích bằng `--release 21` và không sử dụng cú pháp Java 25 trong source cần chạy trên Java 21.

## 5. Kiểm tra IDE: hỗ trợ cú pháp khác với chạy được IDE

Tại tháng 11/2026, các dòng IDE hiện đại đã hỗ trợ phát triển Java 25. Điểm cần đánh giá là **phiên bản IDE, plugin Java, cách chọn project JDK, language level, build-system JVM và debugger**.

| IDE | Mốc hỗ trợ có bằng chứng | Thực hiện kiểm tra |
|---|---|---|
| **IntelliJ IDEA** | IntelliJ IDEA **2025.3** có hỗ trợ tính năng Java 25 đã final; các dòng 2026.x tiếp tục hỗ trợ | Đặt Project SDK = JDK 25, Language Level = 25, Gradle JVM/Maven importer đúng, mở và debug `Smoke25.java` |
| **Eclipse IDE / JDT** | Eclipse IDE 2025-09 trở đi có bộ công cụ Java 25; bản 2026-09 còn phát hành kèm Java 25 làm runtime IDE | Chọn Installed JRE/JDK 25, project execution environment/compliance 25, xây lại project và xem marker |
| **VS Code (Extension Pack for Java / Red Hat Java language support)** | Java language extension **1.46.0** có ghi rõ hỗ trợ Java 25; các bản hiện hành tiếp tục hỗ trợ | Cấu hình `java.configuration.runtimes` cho JavaSE-25, import Maven/Gradle, kiểm tra Problems, Run/Debug/Test |
| **Các editor/language server khác** | Không suy đoán từ khả năng mở file `.java` | Xác minh release notes của parser/language server, source level, debugging và test runner riêng |

Các mốc trong bảng giúp phát hiện bản **quá cũ**; không phải đề nghị đóng băng IDE ở đúng phiên bản đầu tiên đó. Nên cài bản ổn định hiện hành đang được nhà phát hành bảo trì, rồi thử với **project thật** và source JDK 25.

### 5.1. IntelliJ IDEA

Trong **Project Structure**, kiểm tra:

1. **SDK** trỏ đến thư mục JDK 25 đầy đủ, không phải JRE hay một JDK khác cùng tên.
2. **Language level** = 25, hoặc để Maven/Gradle nhập cấu hình đúng khi IDE hỗ trợ.
3. Với Gradle: **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JVM**, kiểm tra JVM chạy daemon được wrapper hỗ trợ; so sánh với `./gradlew --version`.
4. Với Maven: kiểm tra Maven runner/importer JDK và cấu hình compiler plugin trong effective POM; dự án có thể import được nhưng compile theo `release` khác.
5. Chạy, đặt breakpoint, debug cả `Smoke25.java`, một JUnit test và code có `import module` trong project.

Trường hợp IntelliJ syntax highlighting bình thường nhưng Gradle build fail thường nằm ở Gradle Wrapper, toolchain hoặc plugin, không phải language level của editor. Trường hợp Gradle build thành công nhưng editor tô đỏ thường là IDE SDK, indexing hoặc bản parser/language support.

### 5.2. Eclipse IDE / JDT

Trong **Preferences → Java → Installed JREs** và **Project Properties → Java Compiler / Java Build Path**, xác nhận JDK 25 và compiler compliance 25. Khi dự án dùng Maven (`m2e`) hoặc Gradle (`Buildship`), kiểm tra cấu hình JDK mà plugin dùng để import/chạy build, thay vì chỉ thay **Installed JREs** rồi suy ra mọi trình biên dịch đều là Java 25.

Mở `Smoke25.java` và kiểm tra các tính năng: edit/parse, compile, run, debugger, refactor, formatter và test launch. Nếu file chỉ lỗi trong Eclipse, xem bản Eclipse/JDT và cấu hình compiler; bản 2025-09+ là mốc thực tế để đối chiếu.

### 5.3. VS Code và Java language server

Trong VS Code có Java extension tương thích, cấu hình project runtime rõ ràng, ví dụ `settings.json` (đường dẫn chỉ minh họa, phải thay theo máy thật):

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-25",
      "path": "C:\\jdks\\jdk-25",
      "default": true
    }
  ]
}
```

Extension hiện hành có thể dùng **embedded JRE** để chạy language server trên nền tảng được hỗ trợ. Ở bản universal không kèm embedded JRE, `java.jdt.ls.java.home` có thể chỉ đường dẫn tới JDK chạy **language server**; thuộc tính này **khác** `java.configuration.runtimes` dành cho JDK của project. Đừng tự đặt `java.jdt.ls.java.home` khi extension đang tự sử dụng embedded runtime và không cần thay đổi.

Sau khi cập nhật, dùng Java Projects view hoặc command để kiểm tra JDK thực được nhận diện, đồng bộ Maven/Gradle, chạy smoke-test, debugger và Java Test Runner. Nếu VS Code mở được file nhưng báo lỗi tại `import module`, hãy cập nhật Java extension/JDT Language Server và kiểm tra runtime của workspace.

## 6. Bảng kiểm nhanh trước khi đánh giá build tool

| Quan sát | Điều đã chứng minh | Điều **chưa** chứng minh |
|---|---|---|
| `java --version` in `25` | JVM mà terminal gọi là Java 25 | Compiler, IDE, build, test runner, analyzer đều dùng 25 |
| `javac --version` in `25` | Trình biên dịch CLI đúng bản | Maven/Gradle/toolchains đã chọn javac này |
| IDE “Project SDK: 25” | IDE biết JDK 25 | Gradle daemon, compiler plugin và CI cùng dùng 25 |
| `Smoke25.java` chạy trong IDE | Parser/launcher của IDE xử lý được chương trình thử | Coverage, static analyzers, packaging và production runtime |
| `mvn -version` / `gradlew --version` | JVM chạy **build tool** | Java compiler/test launcher do toolchain chọn |
| `clean test` thành công | Các task được gọi chạy được trong cấu hình hiện tại | Tất cả analyzer và production runtime đã được kiểm chứng |

Ở mỗi bước, lưu phiên bản bằng chứng trong ticket nâng cấp JDK. Không sửa đại trà project source level cho đến khi xác định chính xác lớp đang gây lỗi.

## 7. Gradle: tách JVM chạy Gradle khỏi Java Toolchain của dự án

**Mốc hỗ trợ chính thức:** Theo Gradle Java Compatibility Matrix, **Gradle 9.1.0 trở lên** được xác nhận hỗ trợ **Java 25 cho toolchains** và **chạy chính Gradle trên JVM 25**. Không lấy việc `java --version` trả 25 làm bằng chứng rằng Gradle Wrapper cũ chạy được.

### 7.1. Xác định phiên bản Wrapper và Gradle JVM

Trong thư mục dự án có Gradle Wrapper:

```bash
./gradlew --version
./gradlew -q javaToolchains
```

Trong PowerShell Windows:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
```

Quan sát `Gradle ...`, `Launcher JVM`/`Daemon JVM` (tùy bản) và danh sách JDK Gradle phát hiện. Nếu Wrapper thấp hơn 9.1 và yêu cầu JDK 25, phải chọn **phiên bản Gradle tương thích** theo compatibility matrix và xác minh phiên bản plugin liên quan; không chỉ sửa IDE Gradle JVM hoặc `JAVA_HOME`.

Ưu tiên chạy **wrapper của repository** thay vì lệnh `gradle` cài toàn máy để đảm bảo local và CI dùng cùng bản Gradle. Cập nhật wrapper phải được review và chạy build/test của project; không chỉnh tệp wrapper tùy tiện chỉ vì IDE gợi ý.

### 7.2. Chỉ định JDK 25 trong Gradle Kotlin DSL

Ví dụ `build.gradle.kts` dành cho dự án Java thuần (các project Spring Boot cần giữ plugin/BOM tương thích đã có):

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

Hai lựa chọn có ý nghĩa khác nhau:

- `java.toolchain.languageVersion = 25`: yêu cầu trình biên dịch, test launcher và công cụ Java liên quan (khi task hỗ trợ toolchain) dùng JDK 25; không buộc Gradle daemon phải chạy trên JVM 25.
- `options.release.set(25)`: `javac` phải biên dịch đúng mức ngôn ngữ, class file và Java SE API của release 25; không dùng API chỉ xuất hiện ở JDK cao hơn do máy build tình cờ có bản mới.
- `useJUnitPlatform()` chỉ phù hợp khi test framework/project dùng JUnit Platform và có dependency test tương ứng; bản thân dòng này không kéo JUnit vào project.

Chạy theo chuỗi khi kiểm tra **trong dự án thật**:

```bash
./gradlew -q javaToolchains
./gradlew clean test
./gradlew check
```

Kiểm tra task `JavaCompile`, `Test`, JaCoCo/PMD/Checkstyle và task tùy biến; một plugin cũ có thể tự chạy JVM riêng hoặc đọc class file với thư viện ASM cũ, nên **toolchain đúng chưa bảo đảm plugin tương thích**.

Toolchain có thể tự tìm JDK cài sẵn. Tự tải JDK chỉ hoạt động khi đã cấu hình **toolchain download repository/resolver** phù hợp; không giả định Gradle tự tải mọi JDK nếu cấu hình repository thiếu hoặc tổ chức chặn network.

### 7.3. Nếu cần chạy trên Java 21 nhưng dùng JDK 25 để build

Đừng đổi target sang Java 25 nếu sản phẩm còn phải chạy trên JVM 21. Có thể dùng toolchain 25 với:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

Cách này biên dịch theo **API và ngôn ngữ Java 21**, tạo class file tương thích Java 21; không cho phép dùng `import module` hoặc compact source syntax của Java 25. Cần kiểm tra dependency runtime cũng hỗ trợ JDK 21, vì `--release` không tự hạ phiên bản bytecode của các thư viện bên thứ ba.

## 8. Maven: kiểm tra `mvn -version`, Compiler Plugin và Toolchains

Maven cho phép chọn JDK compiler độc lập với JVM chạy Maven thông qua **Maven Toolchains**. Quan trọng hơn là dự án cần dùng compiler plugin có hỗ trợ `--release` và build/test plugins thích hợp; không nên đoán compiler source level từ Java trong terminal.

### 8.1. Lấy bằng chứng về Maven thực đang chạy

Với Maven Wrapper trong repository:

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw test
```

PowerShell Windows:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd help:effective-pom
.\mvnw.cmd test
```

Trong kết quả `--version`, xác nhận bản Maven và **Java version/Java home** mà tiến trình Maven sử dụng. Trong effective POM, tìm `<maven.compiler.release>`, cấu hình `maven-compiler-plugin`, các plugin test/coverage và profile đã active. Nếu dự án đang dùng Maven trên JDK cũ nhưng có toolchain 25, JVM hiển thị ở `mvn --version` **không phải** bằng chứng duy nhất về compiler thực.

### 8.2. `pom.xml` khai báo release 25 rõ ràng

Ví dụ phần cấu hình hợp lệ trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <release>${maven.compiler.release}</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **một phần của POM**, đặt bên trong `<project>` đầy đủ. Compiler Plugin 3.16.0 là phiên bản hiện hành được tài liệu Apache Maven sử dụng trong ví dụ cấu hình `--release` tại thời điểm viết. Với dự án thực có parent/BOM/pluginManagement, chọn bản ổn định tương thích và tránh khai báo version xung đột.

`<release>25</release>` khiến Maven Compiler Plugin yêu cầu javac hiểu Java 25; nếu compiler thực là JDK 21 sẽ báo lỗi kiểu `release version 25 not supported`. Cần đổi **JDK compiler/toolchain** sang 25, không sửa `<release>` xuống 21 chỉ để làm build xanh nếu yêu cầu bài là Java 25.

### 8.3. Maven Toolchains chọn đúng JDK 25

Với Maven Toolchains Plugin 3.3.0, có thể yêu cầu chọn JDK theo version để các plugin có hỗ trợ toolchain dùng chung. Ví dụ fragment `pom.xml`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>select-jdk-toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <version>25</version>
    </configuration>
</plugin>
```

Goal `select-jdk-toolchain` có khả năng **tự tìm JDK** và ràng buộc version; cơ chế cụ thể tùy bản Maven Toolchains, các JDK được phát hiện và cấu hình máy. Công cụ có thể dùng `~/.m2/toolchains.xml` hoặc discovery hiện đại. Phải xem output chọn toolchain, không chỉ thấy mục `<version>25</version>` trong POM. Một số plugin **không** sử dụng toolchain được chọn, vì vậy phải kiểm tra từng plugin cần `java`/`javac`/`javadoc`.

**Maven Surefire/Failsafe, JUnit và mocking** cũng cần test trên JDK 25. Thao tác `test` chỉ thành công khi test provider, framework, reflection/bytecode instrumentation và runtime dependencies thật sự tương thích; compiler plugin thành công chưa đủ.

## 9. Công cụ phân tích: kiểm cả source parser và bytecode reader

JDK 25 sinh **class file major version 69**. Các công cụ phân tích thường dùng AST parser (phân tích source) hoặc ASM/BCEL/Byte Buddy để đọc hoặc biến đổi bytecode. Chúng có ma trận tương thích **riêng** với IDE và build tool.

| Công cụ / loại | Mốc hỗ trợ đáng chú ý | Kiểm tra tối thiểu |
|---|---|---|
| **JaCoCo** — coverage/agent/bytecode | **0.8.14** công bố hỗ trợ chính thức Java 25; bản ổn định mới hơn cũng tiếp tục hỗ trợ (0.8.16 phát hành 10/2026) | Chạy test với agent và tạo report trên class file major 69; kiểm tra report thực có lớp và coverage |
| **PMD** — AST/static rules | PMD **7.16.0** trở lên hỗ trợ ngôn ngữ **Java 25** ở mức chuẩn | Parse thử `import module`, compact source file; chạy ruleset hiện hành và xác nhận version thực |
| **Checkstyle** — coding style/parser | Checkstyle **12.2.0** có hỗ trợ module import của Java 25; các bản 13.x đã tiếp tục sửa nhiều trường hợp compact source files | Chạy cả những cú pháp JEP 511/512, kiểm tra false positive, formatter và check rules |
| **SpotBugs** — bytecode analysis | Phụ thuộc bản SpotBugs cùng BCEL/ASM đi kèm; không dùng mốc “hỗ trợ JDK runtime” thay cho khả năng đọc class file 69 | Chạy trực tiếp trên artifact class file 69 và xem báo cáo |
| **SonarQube / SonarJava** | Phân biệt **JDK để chạy scanner/server** và **mức Java source/bytecode analyzer hiểu được**, vốn thay đổi theo release | Kiểm tra bảng hỗ trợ của đúng SonarQube/SonarJava version; chạy scan có Java 25 syntax và build bytecode |
| **Annotation processors / bytecode agents** (Lombok, MapStruct, Mockito, Byte Buddy, agent giám sát...) | Không có một mốc chung; từng bản dùng javac API/parser/agent riêng | Chạy compile, unit/integration tests, debugger, instrumentation thực tế trên JDK 25 |
| **Công cụ JDK** (`jdeps`, `jdeprscan`, `jfr`, `jcmd`, `javap`) | Có trong bản JDK 25 đầy đủ | Gọi từ cùng JDK 25, dùng để phát hiện internals, API deprecated, JFR và kiểm tra bytecode |

**Lưu ý về PMD preview:** một số bản PMD đời mới đã **ngừng hỗ trợ tùy chọn `java-25-preview`** khi Java 27 xuất hiện, nhưng vẫn hỗ trợ **Java 25 chuẩn**. Vì vậy đừng hướng dẫn kích hoạt `25-preview` trên công cụ hiện đại chỉ để phân tích mã Java 25 thông thường. Đây là một ví dụ điển hình về cách tránh kiến thức phiên bản đã lỗi thời.

**Lưu ý về SonarQube:** tài liệu 2026 có thể nêu SonarQube Server được chạy trên JDK 25, trong khi bảng ngôn ngữ Java của một phiên bản cụ thể ghi nhận mức source support khác. Hai thông tin này nói về **hai năng lực khác nhau**. Xác minh phiên bản server, scanner, Java analyzer plugin và feature level được hỗ trợ ở thời điểm triển khai.

### 9.1. Smoke-test analyzer trên cùng input

Trước khi nâng cấp dự án lớn, chạy analyzer trên mã có:

1. `import module java.base;` (JEP 511).
2. File `Smoke25.java` với `void main()` (JEP 512).
3. Constructor chứa validation trước `super()` (JEP 513).
4. Class file **major 69** từ `javac --release 25`.
5. Một test thực chạy cùng coverage agent, tạo coverage XML/HTML.
6. Một module có annotation processor và mocking nếu sản phẩm dùng chúng.

Công cụ pass khi **kết thúc thành công và trả kết quả có ý nghĩa**, không chỉ không ném exception. Ví dụ JaCoCo job exit 0 nhưng HTML report rỗng là **không đạt**; Sonar scan thành công nhưng bỏ qua file dùng syntax Java 25 cũng **chưa đạt**.

### 9.2. Công cụ phân tích sẵn có trong JDK

Khi đã có artifact Java 25, những lệnh sau có ích cho chẩn đoán (thay tên JAR bằng bản build thực tế):

```bash
javap -verbose out/Smoke25.class
jdeps --jdk-internals app.jar
jdeps --multi-release 25 -summary app.jar
jdeprscan --release 25 app.jar
jfr --version
jcmd -l
```

`javap` kiểm tra classfile, `jdeps --jdk-internals` phát hiện phụ thuộc vào JDK internal APIs, `jdeprscan` quét API bị đánh dấu deprecated cho release tương ứng, còn `jfr`/`jcmd` hỗ trợ quan sát runtime. Các công cụ này **bổ sung**, không thay cho static analyzer theo ruleset hoặc kiểm thử tương thích thư viện. Nếu có classpath/module-path phức tạp, `jdeps` có thể cần thêm cấu hình dependency để báo cáo đầy đủ.

Không khởi động recording production chỉ để chứng minh công cụ có sẵn; `jfr --version` và `jcmd -l` đủ cho kiểm tra hiện diện. Khi thật sự muốn phân tích JFR, cần kiểm soát quyền truy cập, tệp ghi và tác động chi phí.

## 10. Các nhóm lỗi thường gặp và cách suy luận

| Dấu hiệu | Lớp có khả năng gặp lỗi | Phép kiểm / hướng xử lý |
|---|---|---|
| `javac: release version 25 not supported` | Compiler thực thấp hơn Java 25 | `javac --version`, JVM/toolchain của Maven/Gradle; chọn JDK 25 |
| `invalid source release: 25` | Compiler hoặc plugin chọn javac sai | Kiểm tra effective POM/Gradle task JDK và Gradle/Maven toolchain |
| `Unsupported class file major version 69` | JVM quá cũ **hoặc** thư viện bytecode parser cũ | Xem stack trace xác định JVM hay ASM/BCEL/plugin; cập nhật đúng thành phần |
| `UnsupportedClassVersionError` khi chạy `.class` | JVM runtime thấp hơn target | `java --version`, `--release` và JDK runtime ở container/CI |
| `No matching toolchains found` | Toolchain 25 không được phát hiện | `javaToolchains`, Maven toolchains discovery, đường dẫn JDK/auto-provision |
| Gradle daemon không khởi động trên JDK 25 | Gradle Wrapper chưa hỗ trợ JVM 25 | Dùng Gradle 9.1.0+ theo compatibility matrix, kiểm plugin |
| CLI compile được, IDE báo lỗi `import module` | Parser/language level của IDE cũ | Cập nhật IDE/Java extension, project SDK và level 25 |
| Maven/Gradle build được, coverage fail | JaCoCo/ASM cũ hoặc agent lỗi | Kiểm tra JaCoCo 0.8.14+, plugin test và output coverage |
| Unit tests fail vì bytecode instrument | Mockito/Byte Buddy/agent/reflective access không tương thích | Nâng bộ test dependencies tương thích, xem stack trace; không mở module JVM hàng loạt |
| Checkstyle/PMD báo lỗi ở compact source | AST/rules chưa hỗ trợ JEP 512 | Đối chiếu bản analyzer, cập nhật, viết test cho rules |
| Sonar analysis chạy nhưng thiếu file Java 25 | Java analyzer/parser version hoặc bytecode đầu vào | Kiểm tra release support, output scanner và report |
| IDE debug chạy nhưng CI test fail | CI image/wrapper/toolchain/plugin version khác local | Lưu evidence `java`, wrapper, compiler và test-runtime versions; tái tạo CI |

**Đặc biệt với class file 69:** nếu log là `UnsupportedClassVersionError`, thường JVM đang cố load bytecode mới bằng runtime cũ. Nếu log nêu `org.objectweb.asm` hoặc lớp analyzer, có thể JVM đang đủ mới nhưng **thư viện đọc bytecode không hiểu định dạng**. Cần xử lý đúng lớp; tránh giảm target xuống 21 chỉ để né lỗi nếu sản phẩm yêu cầu dùng Java 25.

Không dùng hàng loạt JVM flags kiểu `--add-opens`, `--add-exports`, `-XX:+...` làm giải pháp mặc định cho mọi lỗi nâng cấp. Chỉ dùng khi có lý do được chứng minh và kế hoạch loại bỏ phù hợp.

## 11. Xây ma trận kiểm chứng local và CI trước khi nâng cấp dự án

Một dự án đạt chuẩn khi **cùng commit** có thể biên dịch, kiểm thử và phân tích trong pipeline sử dụng JDK đích. Không nhất thiết phải thay production ngay; có thể chạy song song build/test trên JDK cũ và JDK 25 để phát hiện bất tương thích.

### 11.1. Chia bài kiểm tra thành các cổng

| Cổng kiểm tra | Thực hiện | Bằng chứng cần lưu | Điều kiện đạt |
|---|---|---|---|
| **G0 — JDK trên runner** | `java --version`, `javac --version`, xác nhận vendor/architecture | Output phiên bản đầy đủ và đường dẫn JDK | JDK 25 có đủ compiler + tools |
| **G1 — Editor/source** | Parse, compile, debug `Smoke25.java` tại IDE; test compact source/module import | IDE version, SDK, language level, kết quả run/debug | Không báo lỗi giả về cú pháp final Java 25 |
| **G2 — Build** | Gradle Wrapper + toolchain hoặc Maven Wrapper + compiler toolchain | Wrapper version, toolchain được chọn, `--release 25` | Compile/reproducible build thành công |
| **G3 — Tests** | Unit + integration tests, JUnit/mock framework/annotation processors | Tổng số test chạy, failures, JVM chạy test | Không lỗi classfile/reflective access hoặc test provider |
| **G4 — Analysis** | JaCoCo, PMD, Checkstyle, SpotBugs, Sonar (nếu áp dụng) | Tool/plugin versions, số class/file phân tích, reports | Các analyzer hiểu cú pháp và bytecode Java 25 |
| **G5 — Runtime** | Khởi động artifact trên runtime 25, smoke endpoint/CLI và quan sát logs/JFR | Java runtime, liveness/startup, lỗi application | Không có `UnsupportedClassVersionError` hay dependency break |
| **G6 — Release readiness** | So sánh với baseline, rà dependency/CI/container images | Checklist, risk register và quyết định triển khai | Có phương án rollout/rollback, xác định người chịu trách nhiệm |

Nếu sản phẩm **vẫn phục vụ runtime 21**, G2 phải chạy compile với `--release 21` cho artifact cần tương thích ngược và G5 phải kiểm tra cả runtime 21; không cố đưa tính năng ngôn ngữ Java 25 vào đường biên tương thích đó. Nếu quyết định **target Java 25**, artifact có classfile 69 và runtime tối thiểu phải là JDK/JRE hiểu được Java 25.

### 11.2. Pipeline thực hành với Maven hoặc Gradle

Ví dụ dành cho dự án đã có wrapper và test/analysis tasks cấu hình đầy đủ:

```text
1. Runner cài JDK 25, ghi rõ vendor + patch version.
2. In `java --version`, `javac --version`.
3. Maven: `./mvnw --version`, `./mvnw verify`.
   Hoặc Gradle: `./gradlew --version`, `./gradlew -q javaToolchains`,
                 `./gradlew clean check`.
4. Chạy coverage/static analysis ở đúng task/goal của repository.
5. Kiểm tra coverage/quality reports không rỗng.
6. Kiểm tra một class file đại diện có major version 69.
7. Khởi động artifact thật bằng runtime 25 và chạy smoke test.
8. Lưu các version/outputs trong CI artifact hoặc báo cáo nâng cấp.
```

Tùy plugin, `verify`/`check` có thể **không** mặc định kích hoạt toàn bộ analyzer. Chỉ đánh dấu G4 `PASS` khi job thật sự gọi các plugin và có report. Ví dụ trong Gradle, task `jacocoTestReport`, `pmdMain`, `checkstyleMain` phải có cấu hình tương ứng; trong Maven, goals analyzer cần được bind vào lifecycle hoặc được gọi riêng. Kiểm tra stdout không có dòng task bị `SKIPPED` bất ngờ.

### 11.3. Kiểm chứng chính sách JDK nhiều nền tảng

Nên dùng ít nhất một runner Linux giống production và một runner Windows/macOS nếu nhóm phát triển hoặc sản phẩm hỗ trợ nền tảng đó. Với JNI/native libraries, charset, filesystem case-sensitivity hoặc ARM64, cần thêm matrix theo kiến trúc CPU. Bản Windows x64 tương thích không chứng minh bản Linux ARM64 tương thích.

Để giảm “works on my machine”, cần:

- **Pin wrapper** Maven/Gradle trong repository và ghi phiên bản plugin quan trọng.
- **Chọn JDK qua toolchain hoặc cấu hình CI có kiểm soát**, không dựa vào bản JDK ngẫu nhiên trên agent.
- Dùng image/container build có cập nhật bản vá bảo mật và có khả năng truy xuất nguồn gốc.
- Xác minh test runtime, annotation processors, bytecode agents và analyzer bên cạnh `javac`.
- Không bật preview hàng loạt chỉ để làm IDE “nhận Java 25”, vì các tính năng final không đòi preview.
- Với framework như Spring Boot, kiểm tra **ma trận hỗ trợ JVM/Gradle/Maven** của đúng phiên bản framework, không suy ra từ việc JDK 25 tự chạy được một file `.java`.

## 12. Lập hồ sơ tương thích để đưa ra quyết định

Đừng viết “JDK 25 supported” chung chung. Dùng bảng có bằng chứng sau khi tự chạy trên project thực:

| Thành phần | Phiên bản tại môi trường | JDK để chạy công cụ | JDK compile/test/analyze | Kết quả | Bằng chứng / việc cần làm |
|---|---|---|---|---|---|
| JDK command line | Điền version + vendor | 25 | 25 | PASS/FAIL | `java`, `javac`, `jar` |
| IDE / Java plugin | Điền bản ổn định | IDE runtime có thể khác | Project SDK/Language Level 25 | PASS/FAIL | `Smoke25`, Run/Debug/Test |
| Gradle hoặc Maven Wrapper | Điền version | JVM thực chạy wrapper | Toolchain 25, `--release 25` | PASS/FAIL | Version/Toolchain/Effective POM |
| Unit/integration test | JUnit/test runner/plugin | Theo build tool | Runtime test 25 | PASS/FAIL | Số test, log lỗi |
| JaCoCo | 0.8.14+ hoặc bản bảo trì mới | Agent tại test runtime | Bytecode 69 | PASS/FAIL | Coverage report có dữ liệu |
| PMD/Checkstyle | Bản hỗ trợ Java 25 chuẩn | Tool runtime theo plugin | Parse source Java 25 | PASS/FAIL | Parse/ruleset report |
| Sonar/SpotBugs/agent khác | Phiên bản thực tế | Theo công cụ | Java 25 syntax/bytecode | PASS/FAIL | Analyzer log và report |
| Production runtime | Vendor + patch | Java 25 | Artifact target 25 | PASS/FAIL | Startup, smoke test, monitoring |

Một ô **CHƯA XÁC MINH** không nên bị tự suy diễn thành PASS chỉ vì công cụ có logo Java hoặc chạy trên JDK 25. Nếu mới xác nhận khả năng chạy analyzer nhưng chưa xác nhận cú pháp/bytecode mới, ghi rõ: `TOOL_RUNTIME=PASS; JAVA_25_SOURCE=UNKNOWN; CLASS_69=UNKNOWN`.

### Đánh giá rủi ro theo nguyên nhân, không chỉ theo số tool

Ví dụ:

- Gradle 9.1+ và JDK 25 đã đúng, nhưng plugin coverage quá cũ → **không giảm Gradle xuống**; cập nhật plugin coverage.
- Compiler 25, test runtime 25, JaCoCo đúng, Sonar analyzer chưa xác minh → có thể thử project trên JDK 25 trong nhánh/canary, nhưng không tuyên bố quality gate production hoàn tất.
- IDE và build đều chạy được, nhưng container runtime 21 → nâng runtime hoặc hạ target có chủ đích; không phát hành classfile 69 lên runtime 21.
- Analyzer hỗ trợ Java 25 chuẩn nhưng không hỗ trợ preview Java 25 trong bản mới → nếu dự án không dùng preview thì vẫn đạt; không cần chọn công cụ legacy để giữ tính năng preview không cần thiết.

## 13. Kịch bản thực hành và bài tập tự kiểm tra

### Bài tập 1 — Máy có nhiều JDK

Một laptop cho kết quả `java --version = 25` nhưng `javac --version = 21`. Trong IntelliJ, Project SDK = 25 và Gradle JVM = 21, còn Gradle Wrapper = 8.14.

Hãy chỉ ra **ba cấu hình khác nhau** cần kiểm tra, vì sao `javac --release 25` từ terminal có thể lỗi, và vì sao Gradle Wrapper 8.14 chưa phải môi trường được Gradle xác nhận chạy/toolchain Java 25. Đề xuất cách nâng wrapper và dùng toolchain có kiểm chứng thay vì chỉ đổi PATH.

### Bài tập 2 — IDE tốt nhưng analyzer lỗi

`Smoke25.java` chạy tốt, unit tests thành công nhưng coverage báo `Unsupported class file major version 69`. Hãy xác định ít nhất hai khả năng từ stack trace, rồi mô tả cách kiểm tra JaCoCo version, bytecode parser và report. Giải thích vì sao đổi `--release` sang 21 không phải giải pháp nếu mục tiêu đã phê duyệt là target Java 25.

### Bài tập 3 — Maven và Docker runtime không khớp

`mvnw verify` dùng JDK 25 và `maven.compiler.release=25` thành công, nhưng container chạy trên Java 21 bị `UnsupportedClassVersionError`. Cần thay đổi gì ở runtime hoặc chính sách target? Liệu chỉ sửa `JAVA_HOME` trong máy phát triển có giải quyết container đã phát hành hay không?

### Bài tập 4 — Cú pháp final bị IDE tô đỏ

IDE nhận `record` nhưng báo lỗi với `import module java.base;` và `void main()`. Trình bày kế hoạch kiểm tra IDE/language-server version, compiler compliance, project SDK và `javac --release 25` để phân biệt parser cũ với lỗi nguồn thật. Có cần `--enable-preview` cho hai cú pháp này ở Java 25 không?

### Bài tập 5 — Phân tích mã nguồn và khả năng hỗ trợ Java 25

Một nhóm thấy SonarQube Server có thể **chạy trên JDK 25**, rồi kết luận mọi phiên bản SonarJava đều phân tích trọn vẹn cú pháp Java 25. Hãy giải thích vì sao kết luận không chắc chắn, đề xuất smoke-test analyzer và mô tả bằng chứng cần lưu.

### Tiêu chí đạt bài

Bài học hoàn tất khi bạn:

1. Xác minh được `java`/`javac` từ đúng JDK 25, phân biệt JDK của IDE, build daemon, compiler, test và production.
2. Dùng **cú pháp Java 25 đã final** để chứng minh editor/compiler hiểu ngôn ngữ, không dựa vào preview cũ.
3. Có Gradle Wrapper **9.1.0+** hoặc Maven/Compiler Plugin/Toolchains tương thích, khai báo rõ toolchain và `--release`.
4. Chạy unit/integration tests, coverage và static analyzers trên source/bytecode Java 25, thu được report có nội dung thay vì chỉ dựa vào exit code.
5. Có bảng tương thích theo thành phần với phiên bản, đường chạy, kết quả và bằng chứng từ CI.
6. Không phát hành classfile major **69** tới runtime cũ hơn Java 25; giữ cấu hình `--release` thấp hơn nếu mục tiêu vẫn cần tương thích ngược.
7. Đánh giá và báo cáo rõ những plugin chưa tương thích mà không thay thế bằng công nghệ không còn được duy trì.

## 14. Tài liệu chính thức nên tra khi chuẩn hóa môi trường

Các đường dẫn dưới đây là nguồn tham khảo nên đối chiếu khi chọn version thực tế, vì IDE và công cụ phân tích phát hành cập nhật liên tục:

- [Oracle — Java 25 Language Changes](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): phân biệt feature final và preview, cú pháp `import module`, compact source files và flexible constructors.
- [Oracle — `javac` của JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `--enable-preview`, `--source` và `--target`.
- [Oracle — JVM Spec Java SE 25](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-1.html): classfile major version 69.
- [IntelliJ IDEA — Supported Java versions and features](https://www.jetbrains.com/help/idea/supported-java-versions.html): Java language features và IDE versions.
- [Eclipse IDE](https://eclipseide.org/): các bản IDE/JDT được bảo trì cùng hỗ trợ Java.
- [VS Code Java language extension](https://github.com/redhat-developer/vscode-java): project JDK, language server runtime và Java version support.
- [Gradle — Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): mốc Gradle 9.1.0 cho Java 25.
- [Gradle — JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): chọn compiler, test launcher và `--release`.
- [Apache Maven Compiler Plugin — `--release`](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cấu hình build release.
- [Apache Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/index.html): JDK discovery/selection độc lập Maven JVM.
- [JaCoCo — Change History](https://www.jacoco.org/jacoco/trunk/doc/changes.html): 0.8.14 hỗ trợ chính thức Java 25 và các bản mới hơn.
- [PMD — Java Language Support](https://pmd.github.io/pmd/pmd_languages_java.html): Java 25 từ PMD 7.16.0, phân biệt preview.
- [Checkstyle — Release Notes](https://checkstyle.org/releasenotes.html): `import module` và compact source file fixes.
- [SonarQube — Java Analysis](https://docs.sonarsource.com/sonarqube-server/2026.1/analyzing-source-code/languages/java): bảng hỗ trợ ngôn ngữ của từng phiên bản SonarJava; đối chiếu thêm với yêu cầu JVM chạy server/scanner.
- [Oracle — JDK 25 Tool Specifications](https://docs.oracle.com/en/java/javase/25/docs/specs/man/index.html): `jdeps`, `jdeprscan`, `javap`, `jfr`, `jcmd`.

**Quy tắc cập nhật kiến thức:** Nếu tài liệu bản mới của một analyzer/IDE thay đổi giới hạn hỗ trợ, ưu tiên tài liệu **đúng version thực dùng** và kết quả smoke-test. Không gắn cờ preview cho các tính năng đã final ở Java 25, không đưa quy trình tích hợp cũ đã bị thay thế thành cách làm bắt buộc, và không coi kết quả “chạy được công cụ” là bằng chứng phân tích trọn vẹn source/bytecode Java 25.
