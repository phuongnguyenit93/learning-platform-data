# Kiểm chứng artifact trong môi trường không phụ thuộc IDE

Một ứng dụng Java chạy được khi bấm **Run** trong IntelliJ IDEA, Eclipse hoặc VS Code chưa chắc hoạt động khi chỉ chuyển file JAR sang máy khác. IDE có thể tự thêm thư mục `target/classes`, `target/test-classes`, thư viện trong Maven local repository, generated resources, VM options, environment variables hoặc đường dẫn project vào runtime classpath. Khi triển khai, những yếu tố ấy có thể không có mặt.

Vì thế, **kiểm chứng artifact trong môi trường không phụ thuộc IDE** nghĩa là kiểm tra **chính bản đã đóng gói**, sử dụng đúng công cụ chạy mà người nhận sản phẩm sẽ dùng, không gọi IDE hay build lại code trong bước smoke test. Với ứng dụng CLI JAR, bài kiểm tra có sức thuyết phục là copy file JAR và các runtime dependencies cần phân phối sang một thư mục tạm sạch, gọi `java -jar`, đối chiếu exit code, stdout, manifest, resource và Java runtime. Không được dựa vào source tree hay dependency cache Maven để “bù” cho artifact thiếu.

Bài học tập trung vào **JAR và manifest**, giải thích cách kiểm chứng main class, runtime classpath, resources, phiên bản Java, tính toàn vẹn, cách phân phối thin JAR/fat JAR và kiểm thử smoke trong CI. Có một project Java 17/Maven hoàn chỉnh với **dependency Commons Lang thực tế**, nhờ đó ta chứng minh được khi thiếu JAR trong `lib/` thì JVM độc lập bị lỗi, dù unit test Maven vẫn đạt.

## 1. Chạy trong IDE và chạy artifact là hai bài toán khác nhau

Một Java launch do IDE quản lý có thể giống:

```text
java -cp <project-output>;<maven-local-dependencies> vn.example.artifact.App
```

Đây là **mô tả khái niệm trên Windows**, không phải lệnh copy chạy. Trên Unix, dấu ngăn cách classpath thường là `:` thay vì `;`. IDE có thể nạp class từ folder `target/classes` hoặc plugin build outputs mà không cần một JAR hoàn chỉnh.

Khi xuất một executable JAR, người dùng thường chạy:

```bash
java -jar artifact-proof-1.0.0.jar
```

Lệnh `java -jar` chỉ dựa vào **entry point trong manifest của JAR** và classpath/runtime dependencies hợp lệ của bản phân phối. Nó không hiểu Maven coordinates để tự tải thư viện, và không mặc nhiên biết thư mục nào IDE đã dùng khi build.

| Khía cạnh | Chạy trong IDE | Chạy artifact đóng gói |
| --- | --- | --- |
| Class chính | Có thể từ `target/classes` | Phải nằm trong JAR/module hoặc runtime package |
| Third-party JAR | IDE/Maven resolver có thể thêm | Phải có trong runtime distribution hoặc launcher được quản lý |
| Resource | Có thể từ project/source output | Phải ở classpath JAR hoặc file config ngoài theo contract |
| Entrypoint | IDE biết Java main class được chọn | `Main-Class` hoặc command launcher phải đúng |
| Working directory | Thường là project root | Có thể ở bất cứ đâu |
| Java runtime | JDK của IDE settings | Java/JRE của host/container chạy thật |
| VM arguments/env | Run Configuration có thể thêm | Phải nằm trong startup contract |
| Bằng chứng | Đã chạy source trong một cấu hình phát triển | Đã chạy binary phân phối với phụ thuộc được giao |

**Không có ý coi IDE là “sai”**. IDE rất hữu ích cho phát triển và debug. Vấn đề là dùng kết quả IDE Run để **thay thế** một kiểm chứng artifact độc lập.

## 2. Định nghĩa artifact cần kiểm chứng

Với Maven, project có GAV `groupId:artifactId:version`; `packaging=jar` tạo JAR trong phase `package` theo lifecycle mặc định. Tuy nhiên artifact cần phân phối có thể là:

- **Library JAR**: người khác dùng làm dependency; thường không có `main`.
- **Thin JAR**: chứa classes/resources của project, thư viện runtime nằm ở file ngoài.
- **Executable thin JAR**: thêm `Main-Class` và có thể thêm `Class-Path` trỏ tới thư viện ngoài.
- **Uber/fat JAR**: gộp nhiều class và resources, thường do Shade/Assembly Plugin tạo.
- **Framework executable JAR**: ví dụ Spring Boot có layout/loader riêng, không giống JAR thuần.
- **WAR**: triển khai vào servlet container hoặc cách chạy riêng của framework, không tự giả định `java -jar`.

Do đó phải xác định **đơn vị bàn giao thật sự**: một file JAR, cả thư mục có `lib/`, một ZIP/TAR, một container image, hay một artifact Maven thư viện để được consumer resolve.

Trong ví dụ chính, artifact là **cả thư mục `dist/`**:

```text
dist/
├── artifact-proof-1.0.0.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

Chỉ đưa `artifact-proof-1.0.0.jar` cho người dùng mà không có `lib` sẽ **không đủ** nếu JAR dựa vào thư viện Commons Lang ở runtime.

## 3. Manifest trong JAR: Main-Class và Class-Path

JAR là định dạng ZIP-based archive. File metadata chuẩn thường ở:

```text
META-INF/MANIFEST.MF
```

Một manifest executable thin JAR có những dòng liên quan:

```text
Manifest-Version: 1.0
Main-Class: vn.example.artifact.App
Class-Path: lib/commons-lang3-3.14.0.jar
```

Đây là **trích đoạn minh họa**, không phải toàn bộ nội dung manifest cố định. Maven Archiver có thể ghi thêm các thuộc tính và xuống dòng dài theo JAR specification.

- `Main-Class` là **tên lớp đầy đủ** có public static void main với tham số String[] dùng để khởi chạy bằng `java -jar`.
- `Class-Path` chứa các URL/path classpath tương đối của những JAR/thư mục bên ngoài, thường cách nhau bằng khoảng trắng theo manifest format.
- `Manifest-Version` biểu thị phiên bản format manifest.
- `Implementation-Version`, `Build-Jdk-Spec` hay `Created-By` có thể xuất hiện tùy build/plugin; không nên tự giả định luôn có.

**Lưu ý đặc biệt:** `Class-Path: lib/commons-lang3-3.14.0.jar` được resolve **tương đối với vị trí của chính JAR** (với các điều kiện hợp lệ theo JAR spec). Nó **không tự động** trỏ về `~/.m2/repository` hoặc thư mục source project. Khi copy JAR sang thư mục mới, phải giữ `lib` cùng cấp nếu manifest yêu cầu.

### 3.1. java -jar khác java -cp

Với `-jar`:

```bash
java -jar artifact-proof-1.0.0.jar
```

JVM đọc `Main-Class` trong manifest để tìm entry point. Các thiết lập **user classpath** qua `-cp` hoặc biến `CLASSPATH` không còn hoạt động như khi gọi một main class trực tiếp; các `Class-Path` entries hợp lệ trong manifest vẫn có thể mở rộng search path.

Với classpath tường minh:

```bash
# Linux/macOS
java -cp "artifact-proof-1.0.0.jar:lib/*" vn.example.artifact.App
```

```powershell
# Windows PowerShell
java.exe -cp "artifact-proof-1.0.0.jar;lib/*" vn.example.artifact.App
```

Ở dạng `-cp`, Java cần **main class name tường minh**; `Main-Class` không được dùng để quyết định entry point. Wildcard `lib/*` có thể bổ sung các JAR trực tiếp trong thư mục, nhưng Java không bảo đảm thứ tự mở rộng wildcard. Vì vậy đừng xem wildcard là giải pháp ổn định cho duplicate class/version conflicts.

### 3.2. Tại sao một JAR có class App vẫn không chạy được?

Một file có `vn/example/artifact/App.class` nhưng thiếu `Main-Class` có thể báo lỗi điển hình:

```text
no main manifest attribute, in artifact-proof-1.0.0.jar
```

Khi manifest có Main-Class nhưng thiếu dependent JAR, có thể gặp `NoClassDefFoundError`/`ClassNotFoundException`. Hai lỗi **khác nguyên nhân**: lần đầu sai entry point, lần sau runtime classpath thiếu. Khi chẩn đoán, phải kiểm tra cả archive content và manifest.

## 4. Checklist ba cấp trước smoke test

**Cấp build-time:**

1. Chạy `mvn -B clean verify` từ CLI với Maven/JDK chuẩn.
2. Kiểm tra exit code, log, số test trong `target/surefire-reports`/`target/failsafe-reports` khi có.
3. Xác định đúng artifact produced; không dùng JAR cũ từ lần build trước.
4. Đối chiếu GAV/version/classifier/plugin versions cần phát hành.

**Cấp archive:**

1. Dùng `jar tf` xem JAR có class main và resource.
2. Đọc `META-INF/MANIFEST.MF` xác nhận `Main-Class`.
3. Xem `Class-Path` có khớp đúng files trong `lib`.
4. Dùng `javap -verbose` kiểm tra Java class-file major version.
5. Xem JAR có dung lượng hợp lý, không rỗng/corrupt.

**Cấp runtime:** 

1. Copy đúng distribution bundle sang thư mục không chứa source/Maven artifacts phụ.
2. Chạy bằng Java runtime đích, không qua IDE/Maven Exec Plugin.
3. Kiểm tra **exit code và kết quả đầu ra**.
4. Bật thử nghiệm âm tính, chẳng hạn cố tình thiếu một runtime JAR **trên bản copy tạm**.
5. Ghi checksum/digest và giữ nguyên binary đã smoke trước deployment.

Một bước `mvn verify` chỉ bao quát các goals đã bind trong project. **Không tự làm toàn bộ các mục trên** nếu chưa có plugin/test cụ thể.

## 5. Ví dụ Java 17 hoàn chỉnh: executable thin JAR + lib/

Bài thực hành dùng Maven 3.9.x, Java 17+, Maven JAR Plugin 3.4.2, Maven Dependency Plugin 3.11.0, Apache Commons Lang 3.14.0 và JUnit Jupiter 5.11.0. Sau build, môi trường smoke chỉ cần Java 17+ và thư mục dist đã sao chép, **không cần Maven/IDE hoặc mạng**.

Cây source:

```text
artifact-proof/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/artifact/App.java
    │   └── resources/artifact.properties
    └── test/
        └── java/vn/example/artifact/AppTest.java
```

### 5.1. POM Maven đầy đủ

File `artifact-proof/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>artifact-proof</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <version>5.11.0</version>
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
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <!-- Stage runtime JARs before jar:jar at package phase. -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
                <executions>
                    <execution>
                        <id>stage-runtime-libraries</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <outputDirectory>${project.build.directory}/dist/lib</outputDirectory>
                            <includeScope>runtime</includeScope>
                            <includeTypes>jar</includeTypes>
                            <excludeTransitive>false</excludeTransitive>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <!-- Manifest points to lib/ relative to the main JAR. -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <outputDirectory>${project.build.directory}/dist</outputDirectory>
                    <archive>
                        <manifest>
                            <addClasspath>true</addClasspath>
                            <classpathPrefix>lib/</classpathPrefix>
                            <mainClass>vn.example.artifact.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Phân tích:**

- `packaging=jar` làm Maven bind JAR Plugin vào `package` theo lifecycle thông thường.
- `maven-resources-plugin` đưa resource từ `src/main/resources` vào `target/classes` để được JAR Plugin đóng gói.
- Compiler Plugin `release=17` tạo bytecode/API target Java 17.
- Maven Dependency Plugin goal `copy-dependencies` được bind vào `prepare-package`, trước khi JAR được tạo.
- `includeScope=runtime` trong Dependency Plugin nghĩa là **include compile + runtime dependencies**, nên Commons Lang được copy, còn JUnit `test` scope không được đưa vào dist.
- `outputDirectory=target/dist/lib` tạo layout thư viện ngoài JAR; `excludeTransitive=false` cho phép copy các runtime transitive dependencies có mặt trong dependency graph.
- Maven JAR Plugin ghi file JAR chính vào `target/dist` và tạo `Main-Class` + `Class-Path` để dùng `java -jar`.

**Đây là thin JAR**, không phải fat JAR. Cấu hình manifest không tự nhúng class của Commons Lang vào JAR chính.

### 5.2. Java main code hoàn chỉnh

File `src/main/java/vn/example/artifact/App.java`:

```java
package vn.example.artifact;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        Properties properties = new Properties();

        try (InputStream in =
                 App.class.getResourceAsStream("/artifact.properties")) {
            if (in == null) {
                throw new IllegalStateException(
                    "Missing artifact.properties in classpath"
                );
            }
            properties.load(
                new InputStreamReader(in, StandardCharsets.UTF_8)
            );
        } catch (IOException e) {
            throw new IllegalStateException(
                "Unable to read artifact.properties", e
            );
        }

        String mode = properties.getProperty("mode");
        if (mode == null || mode.isBlank()) {
            throw new IllegalStateException("Missing mode property");
        }
        return "artifact="
            + StringUtils.capitalize("ready")
            + ";mode="
            + mode;
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Dòng `StringUtils.capitalize` gọi API từ `org.apache.commons:commons-lang3`. Trong IDE và Surefire test classpath, Commons Lang thường đã được Maven resolve. Khi chỉ chạy artifact, JVM cần thư viện runtime đã được phát hành trong `dist/lib`.

Hàm `getResourceAsStream("/artifact.properties")` đọc **resource từ classpath**, không đọc `src/main/resources/artifact.properties` từ filesystem. Nhờ vậy đổi working directory không làm mất resource đã đóng gói.

### 5.3. Resource hoàn chỉnh

File `src/main/resources/artifact.properties`:

```properties
mode=portable
```

Sau Maven Resources và JAR Plugin, path bên trong archive là `artifact.properties` ở classpath root, không còn prefix `src/main/resources`. Có thể kiểm tra bằng `jar tf`.

### 5.4. JUnit Jupiter unit test

File `src/test/java/vn/example/artifact/AppTest.java`:

```java
package vn.example.artifact;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("artifact=Ready;mode=portable", App.message());
    }
}
```

Test này giúp xác minh code/resource và build classpath; **nó không thay thế smoke chạy JAR**. Surefire nhận dependency từ project dependency graph, nên có thể pass ngay cả khi packaging `dist/lib` sai.

### 5.5. Build và output mong đợi

Từ thư mục `artifact-proof`:

```bash
java -version
mvn --version
mvn -B clean verify
```

Cần JDK 17+ để build và quyền tải Maven plugins/JUnit/Commons Lang lần đầu. Build chạy resources, compile, unit test, stage runtime libs rồi package và verify.

Output quan trọng:

```text
target/dist/
├── artifact-proof-1.0.0.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

JUnit chỉ ở test scope, nên không phải runtime JAR trong `lib`. Maven có thể tạo thêm các file/thư mục khác trong `target`; cây trên chỉ thể hiện các output chính cần phân phối.

**Không chạy `java -jar` trước khi chắc chắn đã dùng JAR từ lần build mới**, tránh vô tình kiểm tra artifact cũ trong project.


## 6. Kiểm tra nội dung JAR và manifest

### 6.1. Dùng jar tf để thấy classes và resources

Từ project root:

```bash
jar tf target/dist/artifact-proof-1.0.0.jar
```

Trong stdout cần tìm ít nhất:

```text
META-INF/MANIFEST.MF
vn/example/artifact/App.class
artifact.properties
```

Đây là ba entry tiêu biểu, **không phải toàn bộ danh sách**. Nếu `App.class` không tồn tại, tìm lỗi compile/package hoặc build source path. Nếu `artifact.properties` thiếu, xem `src/main/resources` và Maven Resources Plugin.

### 6.2. Đọc manifest đúng cách

Unix có `unzip` có thể dùng:

```bash
unzip -p target/dist/artifact-proof-1.0.0.jar META-INF/MANIFEST.MF
```

Nếu không có unzip, dùng `jar xf` từ một thư mục kiểm tra riêng:

```bash
mkdir -p target/inspect-manifest
cd target/inspect-manifest
jar xf ../dist/artifact-proof-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Sau lệnh `cd`, để quay về project root cần `cd ../..`. Trên Windows có thể dùng `New-Item`, `Push-Location`, `jar xf`, `Get-Content` và `Pop-Location`.

Trong manifest cần kiểm tra các thuộc tính:

```text
Main-Class: vn.example.artifact.App
Class-Path: lib/commons-lang3-3.14.0.jar
```

**Lưu ý:** chuẩn manifest có line wrapping/continuation cho các dòng dài, nên parser tự động không được giả định toàn bộ `Class-Path` luôn nằm trên một dòng. Dùng Java `java.util.jar.Manifest` khi viết checker thực sự.

### 6.3. Xác minh file lib khớp manifest

Linux/macOS:

```bash
ls -l target/dist/lib/
```

Windows:

```powershell
Get-ChildItem "target\dist\lib"
```

Phải thấy `commons-lang3-3.14.0.jar`. **Không đủ nếu chỉ có file cùng artifactId nhưng phiên bản khác**, ví dụ `commons-lang3-3.12.0.jar`, trong khi manifest trỏ tới `3.14.0`.

Đối với nhiều dependencies, đối chiếu manifest `Class-Path`, thư mục lib, và `mvn dependency:tree`. Đừng dựa vào các JAR bất kỳ trong Maven local cache; JVM đang chạy standalone không tự resolve GAV từ cache.

### 6.4. Java 17 class-file compatibility

```bash
javap -verbose -classpath target/dist/artifact-proof-1.0.0.jar vn.example.artifact.App
```

Trong output tìm:

```text
major version: 61
```

Major version 61 tương ứng Java 17. Nếu runtime trên host chỉ là Java 11, JVM có thể báo `UnsupportedClassVersionError`. Chú ý: JAR chính có bytecode Java17 không chứng minh mọi dependency cũng tương thích với Java17; phải kiểm tra các library được phân phối khi có yêu cầu runtime chặt chẽ.

## 7. Smoke test không phụ thuộc IDE trên Linux/macOS

Bây giờ dùng **chỉ bản phân phối**. Từ project root sau build:

```bash
scratch="$(mktemp -d)"
cp -R target/dist/. "$scratch/"

cd "$scratch"
java -version
java -jar artifact-proof-1.0.0.jar
```

**Stdout chính xác của lệnh `java -jar`** trong trường hợp Java17+ và đủ files:

```text
artifact=Ready;mode=portable
```

Lệnh `java -version` in stderr/stdout riêng tùy JVM; kết quả cố định phía trên **chỉ là output chương trình App**.

Giá trị của thử nghiệm:

- Thư mục scratch **không chứa source code, test classes, POM hay Maven local repository**.
- Java launcher phải tìm `Main-Class` trong manifest JAR.
- Manifest `Class-Path` trỏ tới `lib/commons-lang3-3.14.0.jar` ở scratch.
- `artifact.properties` được đọc từ JAR, không dựa vào working directory ở project.
- Nếu runtime library bị thiếu, `StringUtils` không thể tự được IDE thêm vào classpath.
- JAR được chạy bởi `java` như môi trường sản phẩm, không phải `mvn exec:java` hoặc IDE Run.

**Giới hạn:** thư mục scratch vẫn nằm trên cùng hệ điều hành/JDK của máy build. Để kiểm tra một runtime đích khác, copy đúng bundle sang container/JRE/VM thật và chạy cùng smoke command.

### 7.1. Script CI với exit code và stdout assertion

```bash
#!/usr/bin/env sh
set -eu

mvn -B clean verify

scratch="$(mktemp -d)"
cp -R target/dist/. "$scratch/"

(
    cd "$scratch"
    output="$(java -jar artifact-proof-1.0.0.jar)"
    test "$output" = "artifact=Ready;mode=portable"
    printf '%s\n' "$output"
)
```

Script thất bại nếu Maven build, copy, JVM launch hoặc output assertion thất bại trong điều kiện POSIX shell thông thường. Nó không cần chạy lại Maven ở scratch. CI có thể lưu scratch làm diagnostic artifact, hoặc dọn thư mục tạm **vừa tạo** bằng trap/cleanup có kiểm soát.

Nếu ứng dụng thật in nhiều log không ổn định, thay phép so sánh toàn bộ output bằng một command `--version`, `--health`, JSON field hoặc endpoint kiểm tra trạng thái ổn định.

### 7.2. Bẫy working directory

Code sau có thể chạy trong IDE nhưng sai ở bản phát hành:

```java
// CỐ TÌNH SAI nếu file không được phân phối cạnh current directory:
Files.readString(Path.of("src/main/resources/artifact.properties"));
```

Khi copy JAR/lib sang thư mục scratch, đường dẫn `src/main/resources` không còn. Cách đúng với resource đóng trong JAR là:

```java
App.class.getResourceAsStream("/artifact.properties");
```

Nếu ứng dụng thật **cần file config ngoài JAR**, đó là một contract hợp lệ, nhưng phải ghi rõ `--config /path/to/config` hoặc biến môi trường và đóng gói/bố trí file bên ngoài đúng cách; không phụ thuộc đường dẫn project root do IDE đặt ngầm.

## 8. Smoke test trên Windows PowerShell

Từ project root:

```powershell
mvn.cmd -B clean verify
if ($LASTEXITCODE -ne 0) {
    throw "Maven build failed: $LASTEXITCODE"
}

$root = (Get-Location).Path
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) (
    "artifact-smoke-" + [guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Path $scratch | Out-Null
Copy-Item -Path (Join-Path $root "target\dist\*") -Destination $scratch -Recurse

Push-Location $scratch
try {
    $output = & java.exe -jar "artifact-proof-1.0.0.jar"
    if ($LASTEXITCODE -ne 0) {
        throw "Artifact process failed: $LASTEXITCODE"
    }
    if ($output -ne "artifact=Ready;mode=portable") {
        throw "Unexpected artifact stdout: $output"
    }
    Write-Output $output
}
finally {
    Pop-Location
}
```

Khi chạy đúng, stdout Java:

```text
artifact=Ready;mode=portable
```

PowerShell 5.1 **không tự coi mọi native process exit code khác 0 là terminating error**, vì vậy cần kiểm tra `$LASTEXITCODE` ngay sau `mvn.cmd` và `java.exe`. `Push-Location` và `finally` trả current directory về project dù smoke fail.

Chỉ xóa scratch khi chắc chắn nó là đường dẫn mới tạo bởi job. Không làm cleanup wildcard trên `$env:TEMP` hay thư mục có dữ liệu khác.

## 9. Negative test: thiếu dependency trong bản sao phải bị phát hiện

Một bài smoke không chỉ cần pass khi gói đúng, mà còn nên fail khi cố tình phá **bản copy**:

```bash
# Đứng ở project root, Unix/Linux/macOS
broken="$(mktemp -d)"
cp -R target/dist/. "$broken/"

mv "$broken/lib/commons-lang3-3.14.0.jar" \
   "$broken/lib/commons-lang3-3.14.0.jar.disabled"

(
    cd "$broken"
    java -jar artifact-proof-1.0.0.jar
)
```

**Kết quả mong đợi:** process Java **thất bại với exit code khác 0**, thường kèm `NoClassDefFoundError` liên quan `org/apache/commons/lang3/StringUtils`, vì main JAR không chứa lớp của Commons Lang và file `lib/commons-lang3-3.14.0.jar` bị đổi tên.

Không cố định nguyên văn stack trace: lỗi class loading có thể diễn đạt khác giữa runtime versions. Nếu chương trình bất ngờ vẫn pass khi đã xóa dependency, điều tra xem JAR đã bị shaded, launcher có classpath ẩn hay code không đi qua API đang kiểm chứng.

**Không làm bài negative test trên bản distribution thật sắp deploy**. Chỉ thay đổi bản sao scratch; luôn rebuild/smoke lại artifact đúng sau khi sửa POM.

### 9.1. Bỏ Main-Class là lỗi khác thiếu library

Nếu JAR không khai `Main-Class`, lỗi phổ biến khi chạy `java -jar` là:

```text
no main manifest attribute, in artifact-proof-1.0.0.jar
```

Khi đó `App.class` có thể vẫn nằm trong JAR. Sửa ở Maven JAR Plugin `archive/manifest/mainClass` rồi rebuild; không dùng cách mở ZIP sửa manifest thủ công để “vá” artifact deploy, vì không tái lập được từ source.


## 10. Thin JAR với lib/ và fat JAR bằng Shade Plugin

Bài chính dùng **thin JAR + dist/lib** để cho thấy rõ đường dependency. Nếu sản phẩm là command-line app được phân phối bằng một file, có thể dùng Maven Shade Plugin tạo **uber JAR**.

Ví dụ một đoạn plugin **thay thế chiến lược phân phối** (không phải nội dung bắt buộc của POM thực hành):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <shadedArtifactAttached>true</shadedArtifactAttached>
                <shadedClassifierName>all</shadedClassifierName>
                <createDependencyReducedPom>false</createDependencyReducedPom>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>vn.example.artifact.App</mainClass>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Khi phối hợp với JAR Plugin và build lifecycle đúng, Shade Plugin có thể tạo artifact classifier `all`, thường có tên:

```text
artifact-proof-1.0.0-all.jar
```

**Kiểm tra đường dẫn thực tế trong log/output** vì POM ví dụ ở mục 5 đã đặt JAR Plugin outputDirectory khác mặc định. Một shaded JAR có thể chỉ cần một file khi runtime không cần files ngoài, nhưng vẫn phải smoke `java -jar` trong thư mục **chỉ có shaded JAR**, không có `lib`.

Những điểm phải kiểm chứng khi shade:

- `Main-Class` chính xác và executable JAR thực sự được tạo.
- Classes và resources của dependency được merge vào artifact.
- Các file `META-INF/services/*`, spring metadata hoặc configuration resources có thể cần resource transformers chuyên biệt để tránh bị ghi đè.
- Tránh duplicate classes, invalid signature files và loại mất license/NOTICE resources.
- Đối với Spring Boot executable JAR, phải theo packaging/loader của Spring Boot Maven Plugin, không tùy tiện shade làm mất layout nested JAR.
- Library JAR thường **không cần** shaded vì consumer Maven/Gradle quản lý dependencies của chính họ.

**Không tuyên bố fat JAR mặc nhiên an toàn hoặc tốt hơn thin JAR**. Chọn theo delivery contract và kiểm chứng đúng binary được deploy.

## 11. Artifact smoke test trong CI/CD

Một pipeline chất lượng nên phân chia rõ:

```text
BUILD JOB (có Maven/JDK/repository)
   |
   +-- mvn -B clean verify
   +-- package artifact
   +-- tập hợp target/dist/
   +-- ghi checksums, version, build ID
   |
   v
ARTIFACT STORE (immutable bundle)
   |
   v
SMOKE JOB (không IDE/Maven)
   |
   +-- tải chính binary từ artifact store
   +-- copy/unpack vào workspace mới
   +-- java -version (đúng runtime đích)
   +-- java -jar artifact-proof-1.0.0.jar
   +-- kiểm exit code + output/health
   |
   v
DEPLOY JOB (chỉ sử dụng artifact đã smoke)
```

**Không rebuild binary ở smoke/deploy job.** Nếu build tạo artifact A nhưng deploy job lại `mvn package` tạo B, việc A pass smoke không chứng minh B sẽ hoạt động. Lưu artifact digest để mọi job tham chiếu cùng bytes.

### 11.1. Docker/container như môi trường cách ly

Nếu sản phẩm deploy thành container, có thể xây image chỉ chứa Java runtime và bản dist đã tạo. Mẫu Dockerfile **minh họa**, với điều kiện `dist` đã nằm trong Docker build context:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY dist/ ./
ENTRYPOINT ["java", "-jar", "artifact-proof-1.0.0.jar"]
```

Đây là ví dụ về **cách bố trí runtime**, không khẳng định image tag bất biến hay phù hợp mọi tổ chức. Trong production, pin base image theo digest đã kiểm duyệt, kiểm tra nền tảng/kiến trúc, security patches, quyền người dùng và SBOM.

Một Docker smoke thực sự nên chạy image cuối cùng và kiểm tra exit code/health. Nếu base image không có Maven hoặc source code mà app vẫn hoạt động, điều đó tăng độ tin cậy vào tính độc lập khỏi IDE/build workspace.

### 11.2. Shell script được giao cũng cần được test

Nếu người dùng không khởi chạy bằng `java -jar` mà dùng `bin/start.sh` hoặc `start.cmd`, phải **chạy đúng launcher script** trong môi trường cách ly. Những lỗi về quoting, `chmod +x`, Windows `;` so với Unix `:`, `JAVA_HOME` và working directory có thể không lộ nếu smoke gọi Java trực tiếp bằng một lệnh khác.

### 11.3. Kiểm tra secrets/config/runtime contracts

IDE Run Configuration thường có những thông tin mà artifact không tự mang theo:

```text
JAVA_HOME=<runtime-java>
APP_CONFIG=/etc/app/config.yml
APP_MODE=dev
VM options=-Dfile.encoding=UTF-8
Working directory=<project-root>
```

Các giá trị trên là **minh họa**, không chứa secret thật. Khi chuyển giao artifact, cần tài liệu hóa environment variables, CLI args, config paths, startup directory, ports, TLS certs, log locations và quyền truy cập cần có.

Tránh nhúng credentials thật vào POM, JAR hoặc CI logs chỉ để làm smoke pass. Dùng secret store/ephemeral test credentials và data riêng cho staging.

## 12. Java version, OS và dependency compatibility

### 12.1. Kiểm tra bytecode đúng Java target

Java 17 class-file major version là **61**. Nhưng app có thể dùng native library phụ thuộc OS/CPU, một dependency được biên dịch trên Java mới, hoặc module options mà container không có.

```bash
java -version
javap -verbose -classpath target/dist/artifact-proof-1.0.0.jar vn.example.artifact.App
```

Đọc `major version: 61` của lớp chính, rồi kiểm tra runtime Java version thật. Nếu deploy chạy Java 11, có thể thấy `UnsupportedClassVersionError` dù app chạy tốt trên JDK 21 của developer.

Cấu hình `--release 17` giúp compile theo API Java 17, nhưng **không tự đảm bảo** mọi transitive/runtime dependency cũng hỗ trợ Java 17, mọi native library có build phù hợp hay container có đủ CA certificates/timezone data.

### 12.2. Resource và filesystem case sensitivity

Trên Windows, filesystem thường không phân biệt hoa/thường như Linux. Code nạp `/Artifact.properties` có thể tình cờ chạy trong filesystem development nhưng fail trong JAR/classpath khi resource name thực tế là `artifact.properties`. Luôn kiểm tra **case chính xác** và package path.

Nếu code sử dụng `Files.readString(Path.of("config.yml"))`, đó là file ngoài JAR theo working directory; phải tài liệu hóa và cấp file ở runtime. Với resource đóng trong JAR, dùng `Class.getResourceAsStream` hoặc `ClassLoader.getResourceAsStream` phù hợp.

### 12.3. Chỉ nhìn thấy JAR không đủ đảm bảo binary compatibility

Trong trường hợp có nhiều JAR cùng chứa FQCN hoặc method signatures không tương thích, app có thể chạy được main path nhưng fail ở một luồng nghiệp vụ khác với `NoSuchMethodError`/`LinkageError`. Dùng `mvn dependency:tree`, runtime classpath inspection và integration tests trên các đường chạy quan trọng.

JAR manifest `Class-Path` **không thay thế dependency conflict resolution**, không tự chọn “highest version” và không có ý nghĩa Maven GAV ở runtime.

## 13. Checksums và provenance: smoke đúng binary được deploy

Với thin JAR, đơn vị sản phẩm là **cả bundle**. Nếu một file trong `lib` bị thay, app có thể lỗi dù JAR chính giữ nguyên.

Linux/macOS nếu có `sha256sum`:

```bash
sha256sum target/dist/artifact-proof-1.0.0.jar
sha256sum target/dist/lib/commons-lang3-3.14.0.jar
```

PowerShell:

```powershell
Get-FileHash "target\dist\artifact-proof-1.0.0.jar" -Algorithm SHA256
Get-FileHash "target\dist\lib\commons-lang3-3.14.0.jar" -Algorithm SHA256
```

Không có một hash mẫu cố định vì hash phải được tính trên **bytes thực tế của build**. Sau khi upload/copy, so hash bên nhận với hash đã công bố và bảo vệ nguồn công bố hash.

**Checksum không tự chứng minh nguồn phát hành hợp lệ** nếu kẻ tấn công có thể thay cả file và file hash. Với pipeline cần bảo đảm supply chain, bổ sung signed provenance/artifact signatures, immutable storage, access controls và release approvals.

Một bản ghi artifact nên có: Maven/JDK version, Git commit/build ID, dependency/plugin versions, target JRE, hash JAR và runtime JARs, smoke test report, thời điểm và môi trường kiểm chứng.

## 14. Những lỗi dễ xảy ra khi thoát khỏi IDE

| Triệu chứng | Nguyên nhân điển hình | Cách kiểm tra và sửa |
| --- | --- | --- |
| IDE chạy; `java -jar` báo `no main manifest attribute` | Thiếu `Main-Class` | Cấu hình JAR Plugin `archive/manifest/mainClass`; rebuild |
| `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` | Thiếu runtime dependency trong lib/ hoặc Class-Path sai | Copy đúng JAR; xem manifest, runtime scope |
| `ClassNotFoundException` | Class loader không tìm được class | Xem JAR entries, manifest, Class-Path, launcher |
| `Could not find or load main class` | Main class FQCN/`-cp` sai | Xem `jar tf` và package/class name |
| Resource thiếu khi đổi thư mục | Code đọc `src/main/resources` từ project root | Đọc classpath resource hoặc phát hành config ngoài |
| `UnsupportedClassVersionError` | JVM deploy thấp hơn bytecode target | Kiểm Java runtime/JDK và `javap` |
| `java -cp` chạy nhưng `java -jar` lỗi | Manifest entrypoint/Class-Path sai | Kiểm `Main-Class`/`Class-Path` |
| Unit tests pass nhưng distribution fail | Surefire classpath bù dependency | Smoke bản dist trên thư mục sạch |
| JAR thay đổi sau upload | Pipeline deploy binary khác hoặc file corrupt | SHA-256, artifact ID, immutable storage |
| Run trên Windows, lỗi trên Linux | Case/path/permission/native library | Smoke trên OS/container đích |
| Shaded JAR có `ServiceConfigurationError` | Service descriptors chưa merge đúng | Shade resource transformer và integration test |
| `java -jar` vẫn lỗi khi truyền `-cp lib/*` | `-jar` không dùng user classpath theo cách dự kiến | Sửa manifest Class-Path hoặc dùng `java -cp ... Main` |
| Spring Boot JAR không đúng layout | Dùng JAR/Shade Plugin thay Boot repackager | Dùng Boot plugin và smoke executable JAR |
| Container start nhưng health fail | Thiếu config/env/port/secret/permissions | Xem startup contract và container logs |
| Log hiển thị BUILD SUCCESS nhưng không test | Goal/test bị skip hoặc không được bind | Kiểm Surefire/Failsafe reports và test counts |

**Quy trình xử lý ngắn:** đọc lỗi đầu tiên có ý nghĩa → xác định entrypoint/class/resource/runtime → xem archive/manifest/lib → chạy lại trong scratch → sửa build configuration/source → build/smoke lại. Không xóa cả `~/.m2/repository` theo phản xạ khi JVM standalone bị thiếu class; local Maven cache không phải runtime distribution.

## 15. Khi nào cần ràng buộc smoke vào mvn verify?

Có hai chiến lược hợp lệ:

**A. CI smoke sau Maven verify:** `mvn clean verify` build/test/đóng gói, sau đó job script hoặc container chạy đúng bundle đã tạo. Đây là cách trong bài vì tách bạch build classpath khỏi runtime.

**B. Maven Failsafe integration test:** một `*IT` có thể tự copy `target/dist` sang scratch và dùng `ProcessBuilder` gọi `java -jar`; Failsafe goal `integration-test` được bind vào phase integration-test và `verify` đánh giá kết quả. Khi chọn cách này cần kiểm tra:

- Test không vô tình thêm Maven test classpath vào child JVM.
- Có timeout, xử lý stdout/stderr đúng để không deadlock.
- Process có exit code khác 0 làm test fail.
- Resource/fixture được cleanup ngay cả khi test fail.
- `failsafe:verify` có mặt để chốt kết quả sau `post-integration-test`.
- Integration test chạy **sau package**, không gọi `mvn package` đệ quy từ bên trong.

Ví dụ **phác thảo** ProcessBuilder (chưa phải file Java độc lập):

```java
Process process = new ProcessBuilder(
        "/path/to/java17/bin/java",
        "-jar",
        "artifact-proof-1.0.0.jar")
    .directory(new java.io.File("/path/to/isolated-dist"))
    .redirectErrorStream(true)
    .start();

boolean finished = process.waitFor(
    30, java.util.concurrent.TimeUnit.SECONDS);
if (!finished) {
    process.destroyForcibly();
    throw new AssertionError("Smoke timed out");
}
int exitCode = process.exitValue();
// Đọc process output đúng cách, rồi assert exitCode == 0 và stdout.
```

Nếu output dài, phải consume stream trong khi process chạy hoặc redirect sang file, tránh block bởi pipe buffer. Dự án minh họa ở mục 5–9 mới là ví dụ **runnable đầy đủ**; đoạn ProcessBuilder này chỉ chỉ ra cơ chế tích hợp sâu hơn.

Không nhất thiết nhồi mọi smoke test vào Maven lifecycle; một CI job dùng binary thật sau build là cách rõ ràng nếu pipeline kiểm soát luồng phát hành.

## 16. Câu hỏi tự luyện và đáp án

**Câu 1.** Vì sao nhấn Run trong IntelliJ thành công chưa đủ chứng minh `artifact-proof-1.0.0.jar` chạy được trên production?

**Đáp án:** IDE có thể cung cấp classpath, resources, working directory, Java runtime và VM arguments khác bản phân phối. Cần chạy đúng artifact cùng runtime dependencies trong môi trường độc lập.

**Câu 2.** Manifest có `Main-Class` nhưng không có `Class-Path`, trong khi App cần Commons Lang. Lệnh `java -jar` có chắc chạy không?

**Đáp án:** Không. Nếu JAR chính không nhúng Commons Lang và không có runtime launcher/classpath khác hợp lệ, JVM có thể thiếu `StringUtils`. Phải thêm manifest Class-Path và phân phối lib hoặc dùng packaging dạng fat JAR.

**Câu 3.** Tại sao `includeScope=runtime` vẫn copy `commons-lang3` được khai báo không có `scope` trong POM?

**Đáp án:** Scope mặc định của dependency là compile; runtime scope threshold của Maven Dependency Plugin bao gồm cả compile và runtime dependencies, nhưng không bao gồm test-only.

**Câu 4.** `Class-Path: lib/commons-lang3-3.14.0.jar` được resolve theo thư mục nào?

**Đáp án:** Theo vị trí của JAR chứa manifest, không phải Maven local repository hay project root. Nếu JAR ở `/tmp/smoke/app.jar`, runtime dependency cần có ở `/tmp/smoke/lib/...` theo layout hợp lệ.

**Câu 5.** Chạy `java -cp "app.jar:lib/*" pkg.Main` có dùng manifest `Main-Class` không?

**Đáp án:** Không để chọn entrypoint; class `pkg.Main` do người chạy chỉ định. Dùng `java -jar` mới nhờ manifest chọn main class.

**Câu 6.** Unit test `AppTest` pass và `mvn verify` xanh, nhưng khi copy chỉ JAR sang scratch thì lỗi `NoClassDefFoundError`. Lỗi có thể ở đâu?

**Đáp án:** Bản distribution thiếu runtime dependency hoặc manifest Class-Path không khớp layout. Surefire test classpath đã che lỗi packaging.

**Câu 7.** Khi kiểm chứng một JAR Java 17 trên container Java 11, có thể gặp lỗi gì?

**Đáp án:** `UnsupportedClassVersionError`, do class-file major 61 không được Java 11 hỗ trợ. Cần runtime Java 17+ hoặc chỉnh target theo policy và test lại.

**Câu 8.** Vì sao dùng thư mục scratch thay vì xóa toàn bộ Maven local cache khi muốn chứng minh độc lập IDE?

**Đáp án:** Scratch kiểm tra đúng những file được phát hành, không phá cache dùng cho build của các project khác. Java launcher không tự resolve Maven GAV, nên không cần xóa cache.

**Câu 9.** Phát hành thin JAR + lib/ cần lưu hash cho những file nào?

**Đáp án:** Ít nhất JAR chính và các runtime JARs hoặc một archive bundle có digest; smoke và deploy phải dùng cùng binary/digest.

**Câu 10.** Một Maven library JAR không có main class có nhất thiết phải chạy được bằng `java -jar` không?

**Đáp án:** Không. Với library, kiểm chứng phù hợp là resolve từ consumer project, compile/link API, integration tests và metadata/dependency integrity. Tiêu chí `java -jar` áp dụng cho executable application artifact.

## Tài liệu chính thức

- [Apache Maven JAR Plugin — Executable JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/executable-jar.html)
- [Apache Maven JAR Plugin — jar:jar Goal](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven Archiver — Set Up The Classpath](https://maven.apache.org/shared/maven-archiver/examples/classpath.html)
- [Apache Maven Dependency Plugin — Copying Project Dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/copying-project-dependencies.html)
- [Apache Maven Dependency Plugin — copy-dependencies Goal](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html)
- [Apache Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
- [Apache Maven — Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Oracle — JAR File Specification](https://docs.oracle.com/javase/17/docs/specs/jar/jar.html)
