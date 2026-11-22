# Đính kèm và xuất bản đầy đủ source, Javadoc và các classifier trong Maven

Một thư viện Java tốt không chỉ phát hành JAR chứa bytecode. Developer cần source để debug và đọc mã trong IDE, Javadoc để tra cứu API và đôi khi một biến thể như compiled tests hoặc API-only JAR. Maven hỗ trợ **attached artifacts** với **classifier**, nhưng chỉ tạo file trong `target/` chưa đủ để `install` hoặc `deploy` tự đưa file đó vào repository.

**Nguyên tắc chính:** Maven Install Plugin và Deploy Plugin xử lý main artifact, POM và **những artifact đã được attach** vào Maven project bởi các plugin trong lifecycle. Tên file `-sources.jar` hoặc `-javadoc.jar` chỉ là quy ước; file bị copy thủ công chưa chắc có classifier/attachment metadata.

Bài nằm trong nhóm **Install và Deploy**. Ta xây project **Maven 3.9.x, Java 17** tạo năm JAR: main, `sources`, `javadoc`, `tests` và `api`; kiểm nội dung từng archive, cài vào Maven local repo, deploy thử vào file repository không có secrets, và phân biệt các yêu cầu của Nexus/Artifactory với Maven Central Publisher Portal. Các versions plugin được pin cho bài thực hành, không khẳng định là phiên bản mới nhất.

## 1. GAV, main artifact và classifier

Ví dụ project dùng `groupId=vn.example`, `artifactId=publication-demo`, `version=1.0.0` và `packaging=jar`. Sau khi chạy đúng lifecycle, ta sẽ có:

| Artifact | Classifier | Nội dung chính |
| --- | --- | --- |
| `publication-demo-1.0.0.jar` | Trống | Main Java classes |
| `publication-demo-1.0.0-sources.jar` | `sources` | Java source files |
| `publication-demo-1.0.0-javadoc.jar` | `javadoc` | HTML documentation |
| `publication-demo-1.0.0-tests.jar` | `tests` | Compiled test classes |
| `publication-demo-1.0.0-api.jar` | `api` | Một tập Java API classes được chọn |

`groupId:artifactId:version` được giữ nguyên ở tất cả variants; classifier phân biệt các file cùng version. `type`/extension xác định kiểu artifact, ví dụ `jar` hoặc `zip`. Một classifier **không tạo POM metadata độc lập**, nên nếu variant có dependency graph riêng phức tạp, dùng module/artifactId khác có thể phù hợp hơn.

### 1.1. Consumer chọn variant bằng classifier

```xml
<dependency>
    <groupId>vn.example</groupId>
    <artifactId>publication-demo</artifactId>
    <version>1.0.0</version>
    <type>jar</type>
    <classifier>api</classifier>
</dependency>
```

Dependency không có `classifier` tải main JAR; ở trên Maven tải JAR `api`. `sources`/`javadoc` thường được IDE tự tìm theo quy ước; không khai các JAR chứa source/docs thành compile dependency vì chúng không cung cấp compiled classes.

## 2. Các giai đoạn Maven liên quan

```text
compile -> test -> package -> verify -> install -> deploy
                    |          |         |           |
              main/tests/api  source +    local       remote
                              Javadoc     repo        repo
```

Trong POM mẫu, JAR Plugin tạo main, tests, api ở `package`. Source Plugin `jar-no-fork` và Javadoc Plugin `jar` được bind vào `verify`, nghĩa là tất cả attachments đã tồn tại trước `install` và `deploy`. Có thể bind các goal này vào `package`, nhưng không được kỳ vọng lệnh `mvn package` chạy execution chỉ được gắn ở `verify`.

| Lệnh | Kết quả theo POM trong bài |
| --- | --- |
| `mvn clean package` | Main JAR, `tests.jar`, `api.jar` |
| `mvn clean verify` | Đầy đủ năm JAR; chưa install |
| `mvn clean install` | Chạy tới verify, sau đó cài POM/main/attachments vào local repository |
| `mvn clean deploy` | Chạy tới install và deploy POM/main/attachments nếu có target |
| `mvn source:jar-no-fork` | Chạy riêng Source Plugin goal, không thay cả lifecycle |
| `mvn javadoc:jar` | Sinh Javadoc JAR theo goal; không tự publish sau khi install đã kết thúc |

**Không phải Deploy Plugin tự dò mọi file trong `target/`.** Plugin này nhìn project artifact và các attached artifacts mà những plugin khác đã đăng ký. Nếu một release profile không bật Source/Javadoc executions, main JAR có thể publish một mình.

## 3. Project Java 17 runnable hoàn chỉnh

Cấu trúc file cần tạo:

```text
publication-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/publishing/
    │   ├── Greeting.java
    │   └── Demo.java
    └── test/java/vn/example/publishing/
        └── GreetingTest.java
```

`Greeting` là public API và được đưa vào `api.jar`, còn `Demo` là lệnh CLI minh họa. `GreetingTest` được Surefire chạy và `maven-jar-plugin:test-jar` đóng gói compiled test classes. Sources và Javadoc được tạo từ chính source set chính.

### 3.1. POM đầy đủ

File `publication-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>publication-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Publication Demo</name>
    <description>Java 17 Maven publication example</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    </properties>

    <dependencies>
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
                <executions>
                    <execution>
                        <id>attach-tests</id>
                        <phase>package</phase>
                        <goals><goal>test-jar</goal></goals>
                    </execution>
                    <execution>
                        <id>attach-api</id>
                        <phase>package</phase>
                        <goals><goal>jar</goal></goals>
                        <configuration>
                            <classifier>api</classifier>
                            <includes>
                                <include>vn/example/publishing/Greeting.class</include>
                            </includes>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>verify</phase>
                        <goals><goal>jar-no-fork</goal></goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <docencoding>UTF-8</docencoding>
                    <charset>UTF-8</charset>
                    <failOnError>true</failOnError>
                </configuration>
                <executions>
                    <execution>
                        <id>attach-javadoc</id>
                        <phase>verify</phase>
                        <goals><goal>jar</goal></goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM độc lập đủ để chạy `verify` và `install` trong môi trường Maven/JDK phù hợp. Không có `distributionManagement` để tránh upload nhầm: bài thực hành `deploy` sẽ dùng file-based repository chỉ định bằng CLI.

**Giải thích plugin executions:** `packaging=jar` đã tạo main JAR theo default lifecycle. `jar:test-jar` tạo tests classifier. `jar:jar` thứ hai có `classifier=api` tạo supplemental JAR; nếu không có classifier, có thể cố tạo main JAR lần hai hoặc fail. Source Plugin `jar-no-fork` có classifier mặc định `sources`, thường `attach=true`. Javadoc Plugin `jar` attach classifier mặc định `javadoc`. Install/Deploy Plugin không cần liệt kê năm filenames khi các goals trên đã attach đúng.

### 3.2. Greeting.java: API có Javadoc

File `src/main/java/vn/example/publishing/Greeting.java`:

```java
package vn.example.publishing;

/**
 * A small, deterministic greeting API for Java 17.
 *
 * <p>No external runtime dependencies are required.
 *
 * @since 1.0.0
 */
public final class Greeting {
    private Greeting() {
    }

    /**
     * Creates a greeting for a nonblank name.
     *
     * @param name a non-null, nonblank input name
     * @return a normalized greeting ending with an exclamation mark
     * @throws IllegalArgumentException if name is null or blank
     */
    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

`String.isBlank` và `String.strip` có trong Java 17. Javadoc class/method có tags rõ ràng để generated HTML hữu ích. `Greeting.class` là file duy nhất được chọn trong classifier API.

### 3.3. Demo.java: lệnh Java không phụ thuộc IDE

File `src/main/java/vn/example/publishing/Demo.java`:

```java
package vn.example.publishing;

/**
 * Demonstrates the published API.
 *
 * @since 1.0.0
 */
public final class Demo {
    private Demo() {
    }

    /**
     * Prints a single greeting.
     *
     * @param args unused command-line arguments
     */
    public static void main(String[] args) {
        System.out.println(Greeting.hello("Maven"));
    }
}
```

Build và chạy từ project root:

```bash
java -cp target/publication-demo-1.0.0.jar vn.example.publishing.Demo
```

Stdout chính xác:

```text
Hello, Maven!
```

POM không khai `Main-Class` trong manifest; đây là plain library JAR. Đúng cú pháp chạy là `java -cp ... FQCN`, không tự giả định `java -jar` có entrypoint.

### 3.4. GreetingTest.java: hai unit tests

File `src/test/java/vn/example/publishing/GreetingTest.java`:

```java
package vn.example.publishing;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTest {
    @Test
    void greetsTrimmedName() {
        assertEquals("Hello, Maven!", Greeting.hello(" Maven "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> Greeting.hello("   "));
    }
}
```

Surefire nhận pattern `*Test`, chạy hai test methods. Maven JAR Plugin goal `test-jar` đóng gói `GreetingTest.class` vào `publication-demo-1.0.0-tests.jar`. Test JAR không tự mang test-scoped JUnit dependencies vào consumer.

## 4. Kiểm tra đủ năm JAR sau verify

Từ thư mục `publication-demo`:

```bash
java -version
mvn --version
mvn -B clean verify
```

JDK phải là 17+ và có công cụ Javadoc; Maven phải resolve được plugins/JUnit qua repository. Các artifact chính:

```text
target/
├── publication-demo-1.0.0.jar
├── publication-demo-1.0.0-sources.jar
├── publication-demo-1.0.0-javadoc.jar
├── publication-demo-1.0.0-tests.jar
└── publication-demo-1.0.0-api.jar
```

Dùng JDK `jar` tool kiểm nội dung:

```bash
jar tf target/publication-demo-1.0.0.jar
jar tf target/publication-demo-1.0.0-sources.jar
jar tf target/publication-demo-1.0.0-javadoc.jar
jar tf target/publication-demo-1.0.0-tests.jar
jar tf target/publication-demo-1.0.0-api.jar
```

| JAR | Entry cần có |
| --- | --- |
| Main | `vn/example/publishing/Greeting.class`, `Demo.class` |
| Sources | `vn/example/publishing/Greeting.java`, `Demo.java` |
| Javadoc | `index.html`, `vn/example/publishing/Greeting.html` |
| Tests | `vn/example/publishing/GreetingTest.class` |
| API | `vn/example/publishing/Greeting.class`, không cần `Demo.class` |

Một JAR có tên đúng nhưng bị rỗng hoặc chứa sai classes vẫn có thể được deploy, nên kiểm archive contents và fail build khi thiếu các entry bắt buộc.

### 4.1. Windows PowerShell verify

```powershell
$names = @("publication-demo-1.0.0.jar",
           "publication-demo-1.0.0-sources.jar",
           "publication-demo-1.0.0-javadoc.jar",
           "publication-demo-1.0.0-tests.jar",
           "publication-demo-1.0.0-api.jar")
foreach ($name in $names) {
    $file = Join-Path "target" $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing artifact: $file"
    }
    if ((Get-Item -LiteralPath $file).Length -eq 0) {
        throw "Empty artifact: $file"
    }
}
Write-Output "All expected JARs exist."
```

Stdout khi kiểm thành công là `All expected JARs exist.`. File presence chỉ chứng minh packaging, chưa chứng minh attachment; cần kiểm repository sau install/deploy.

## 5. Source JAR và test-sources JAR

Maven Source Plugin goal `jar-no-fork` đóng gói main source roots, mặc định classifier `sources`, attach=true và phù hợp để bind vào lifecycle không fork các phases khác. Project mẫu gắn goal này ở `verify`. Nếu source JAR xuất hiện trong target nhưng local repo không có, kiểm cờ `attach`, effective POM, execution phase và plugin logs.

Muốn xuất bản **test source** chứ không phải compiled test JAR, có thể thêm vào Source Plugin một execution riêng:

```xml
<execution>
    <id>attach-test-sources</id>
    <phase>verify</phase>
    <goals><goal>test-jar-no-fork</goal></goals>
</execution>
```

Goal tạo test-sources JAR (classifier mặc định `test-sources`); khác với `jar:test-jar` classifier `tests`. `test-sources.jar` chứa `.java`; `tests.jar` chứa compiled `.class`. Không tự phát hành mọi variant khi không có use case; nhiều attachments làm tăng dung lượng release/signing.

## 6. Javadoc JAR và Maven Site

Maven Javadoc Plugin goal `jar` gọi JDK `javadoc`, tạo HTML và attach archive classifier `javadoc`. Nếu chỉ chạy `javadoc:javadoc` hoặc cấu hình plugin trong `reporting`/Maven Site, dự án có thể có HTML site nhưng **chưa có Javadoc JAR attachment**.

Các lỗi Javadoc thường gặp: thiếu JDK tool, Javadoc tags sai (`@param`, `@return`, `@throws`), HTML comments không hợp lệ, classpath/doclink/encoding sai. Nên sửa public API docs và build config; không dùng `-Dmaven.javadoc.skip=true` làm cách release chuẩn khi repository yêu cầu tài liệu.

Javadoc chính thường render tất cả public main source APIs. Trong bài, `api.jar` chỉ chứa `Greeting.class` nhưng `javadoc.jar` có thể còn docs của `Demo`. Muốn docs riêng cho API-only variant, cấu hình riêng source set/execution hoặc tạo module riêng; không đổi classifier `javadoc` tùy tiện khiến IDE không tự nhận ra.

## 7. Local install: kiểm những gì Maven thực sự attach

Chạy:

```bash
mvn -B clean install
```

Maven Install Plugin 3.2.0 cài main artifact/POM và attached artifacts vào local repository. Với local repo mặc định, thư mục quan trọng:

```text
~/.m2/repository/vn/example/publication-demo/1.0.0/
├── publication-demo-1.0.0.pom
├── publication-demo-1.0.0.jar
├── publication-demo-1.0.0-sources.jar
├── publication-demo-1.0.0-javadoc.jar
├── publication-demo-1.0.0-tests.jar
└── publication-demo-1.0.0-api.jar
```

Có thể có metadata/resolver marker files khác; nếu dùng `-Dmaven.repo.local` hoặc `settings.xml/localRepository`, dùng đường thực tế thay vì mặc định.

Kiểm trên Linux/macOS:

```bash
repo="$HOME/.m2/repository/vn/example/publication-demo/1.0.0"
for suffix in "" "-sources" "-javadoc" "-tests" "-api"; do
    test -s "$repo/publication-demo-1.0.0$suffix.jar"
done
test -s "$repo/publication-demo-1.0.0.pom"
```

`test -s` trả exit code 0 khi file không rỗng, không in stdout. Kiểm local repo có đầy đủ files **mạnh hơn** kiểm target; một file tạo ra nhưng chưa attach sẽ không tự được install theo lifecycle.

Local install không đưa artifact cho máy developer khác; muốn chia sẻ cần remote repository hoặc một publishing workflow được cấp quyền.

## 8. Deploy thử vào file repository riêng

POM demo không cấu hình `distributionManagement` để tránh vô tình publish lên repository thật. Deploy Plugin 3.x cho phép alternative target qua `-DaltDeploymentRepository=id::url`. Cú pháp `id::layout::url` là định dạng cũ của Plugin 2.x, không dùng ở đây.

Ví dụ Linux/macOS, chỉ deploy tới thư mục học tập:

```bash
mkdir -p /tmp/publication-demo-maven-repo
mvn -B clean deploy \
  -DaltDeploymentRepository=demo-file::file:///tmp/publication-demo-maven-repo
ls -la /tmp/publication-demo-maven-repo/vn/example/publication-demo/1.0.0
```

Khi thành công, directory theo Maven repository layout có POM, main, `sources`, `javadoc`, `tests` và `api` artifacts cùng metadata/checksum files. File repo chỉ là minh họa, không có authentication hoặc tính năng staging/immutability của Nexus/Artifactory.

Windows PowerShell có thể dùng thư mục có quyền ghi, ví dụ:

```powershell
$repo = "C:\temp\publication-demo-maven-repo"
New-Item -ItemType Directory -Path $repo -Force | Out-Null
mvn.cmd -B clean deploy `
  "-DaltDeploymentRepository=demo-file::file:///C:/temp/publication-demo-maven-repo"
Get-ChildItem "$repo\vn\example\publication-demo\1.0.0"
```

Điều chỉnh path/drive phù hợp môi trường; file repository URL sử dụng dấu `/`. Không tự thay vào một production repository nếu chưa có quyền/phê duyệt.

### 8.1. distributionManagement, repositories và settings

Trong POM thật, `distributionManagement` chỉ nơi **ghi** artifacts, còn `repositories` chỉ nơi **đọc** dependencies:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.org/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.org/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

URL ở đây là ví dụ, không phải server thật. Credentials của publisher ở `settings.xml/servers/server` với `id` khớp `company-releases`/`company-snapshots`; CI nên lấy token từ secret store. Không commit mật khẩu/tokens vào POM hoặc chia sẻ log chứa bí mật.

Release `1.0.0` thường immutable; repository có thể từ chối redeploy cùng GAV. Với `-SNAPSHOT`, tên file remote có thể được timestamp hóa kèm metadata, nên không chỉ tìm literal filename `-SNAPSHOT` rồi kết luận variant bị thiếu.

### 8.2. deploy-file khác lifecycle deploy

`mvn deploy` xử lý artifact family đã được attach từ project lifecycle. `deploy:deploy-file` thường dành cho một file ngoài project lifecycle có metadata rõ; nếu chỉ upload main JAR qua deploy-file thì `sources`/`javadoc`/`api` không tự xuất hiện. Tránh publish rời từng variant nếu có thể dùng cùng POM/lifecycle.

Deploy Plugin có `deployAtEnd` cho multi-module, nhưng theo tài liệu Apache Maven nó **không làm nhiều uploads trở thành giao dịch atomic** hoặc tự rollback toàn bộ khi một module bị lỗi giữa chừng.

## 9. Maven Central Publisher Portal

Central Publisher Portal có quy trình bundle/upload/validate/publish; không đơn giản là đổi file URL thành một endpoint rồi dùng Deploy Plugin trực tiếp. Sonatype hướng dẫn dùng `org.sonatype.central:central-publishing-maven-plugin` và metadata/publisher credentials hợp lệ.

Theo Central requirements hiện hành, nhiều Java artifacts cần source và Javadoc JARs, POM metadata như license/SCM/developer và signatures theo chính sách. Central Publishing Plugin có thể sinh checksums nhưng không tự tạo sources/Javadoc JAR khi build thiếu.

Fragment tham khảo, không thuộc POM runnable:

```xml
<plugin>
    <groupId>org.sonatype.central</groupId>
    <artifactId>central-publishing-maven-plugin</artifactId>
    <version>0.12.0</version>
    <extensions>true</extensions>
    <configuration>
        <publishingServerId>central</publishingServerId>
        <autoPublish>false</autoPublish>
    </configuration>
</plugin>
```

Cần xác minh group namespace, credentials, POM metadata, GPG signing và trạng thái Portal. `autoPublish=false` có thể đòi bước publish thủ công. Upload thành công không đồng nghĩa release đã public/searchable. Classifier `tests`/`api` là tùy chọn, không phải yêu cầu chung của Central.

## 10. Custom classifier, test fixtures và nhiều module

### 10.1. Consumer của tests classifier

```xml
<dependency>
    <groupId>vn.example</groupId>
    <artifactId>publication-demo</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
```

`tests.jar` không tự chuyển test-scoped dependencies của producer cho consumer; consumer cần JUnit và các test dependencies. Surefire cũng không nhất thiết tự scan test classes trong dependency JAR, đôi khi cần `dependenciesToScan`. Đối với test fixtures phức tạp, module riêng có POM metadata chính xác thường tốt hơn.

### 10.2. Attach ZIP hoặc biến thể khác

Maven Build Helper Plugin có goal `attach-artifact` cho file đã tạo trước đó, ví dụ archive `docs.zip`. Fragment dưới **không độc lập runnable**; phải đặt trong Build Helper Plugin đã pin version và tạo ZIP trước execution:

```xml
<execution>
    <id>attach-docs-zip</id>
    <phase>package</phase>
    <goals><goal>attach-artifact</goal></goals>
    <configuration>
        <artifacts>
            <artifact>
                <file>${project.build.directory}/docs.zip</file>
                <type>zip</type>
                <classifier>docs</classifier>
            </artifact>
        </artifacts>
    </configuration>
</execution>
```

Goal attach không tự tạo ZIP. Nếu muốn artifact `all` chứa all dependencies, dùng Shade Plugin và kiểm services/resources/transitive runtime; không dùng Source/Javadoc Plugin để tạo uber JAR.

### 10.3. Reactor và release profiles

Root `modules` là aggregation; child `parent` là inheritance. Source/Javadoc executions ở parent chỉ áp dụng tới child khi POM inheritance/config cho phép. POM-only module không có compiled Java code không nhất thiết phải tạo Javadoc/source giả. `javadoc:aggregate-jar` khác `javadoc:jar` per-module và cần tránh hai goals attach trùng classifier/extension.

Nếu plugin executions chỉ nằm trong profile `release`, lệnh phải có `-Prelease`:

```bash
mvn -B -Prelease clean deploy
```

Quên profile có thể deploy main mà thiếu source/docs. Với `-pl`/`-am`, xác nhận đúng reactor modules được chọn, không tuyên bố full repository release khi chỉ build subset.

## 11. Release quality gate: đủ, đúng và cùng phiên bản

Một pipeline phát hành nên đi qua các bước:

```text
checkout immutable commit
  -> mvn -B clean verify (compile + tests + artifacts)
  -> kiểm file inventory + jar contents
  -> signatures, hashes, provenance nếu cần
  -> install/deploy bằng publishing workflow được phê duyệt
  -> xác minh local/remote repository files
  -> consumer smoke test từ repository, không dựa vào target/classes
  -> approve/release chỉ khi mọi điều kiện đạt
```

Không publish source/Javadoc từ một build khác commit với binary main, không để source JAR chứa internal credentials hoặc file config riêng tư. Cần ghi SHA-256 của **mọi variant** sau khi packaging hoàn tất:

```bash
sha256sum target/publication-demo-1.0.0*.jar
```

Trên PowerShell:

```powershell
Get-ChildItem "target\publication-demo-1.0.0*.jar" |
    Get-FileHash -Algorithm SHA256
```

Không có checksum output cố định: hashes phụ thuộc bytes thực tế và build metadata. Nếu cần reproducible release, tìm hiểu `project.build.outputTimestamp` và khả năng hỗ trợ của các plugin, pin JDK/dependencies/plugins và so hashes từng JAR.

### 11.1. Script POSIX kiểm bundle trước deploy

```bash
#!/usr/bin/env sh
set -eu
base="target/publication-demo-1.0.0"
for suffix in "" "-sources" "-javadoc" "-tests" "-api"; do
    test -s "${base}${suffix}.jar"
done
jar tf "${base}-sources.jar" | grep -q "vn/example/publishing/Greeting.java"
jar tf "${base}-javadoc.jar" | grep -q "vn/example/publishing/Greeting.html"
jar tf "${base}-tests.jar" | grep -q "vn/example/publishing/GreetingTest.class"
jar tf "${base}-api.jar" | grep -q "vn/example/publishing/Greeting.class"
printf "Artifact bundle verified.\n"
```

Stdout khi mọi kiểm tra đạt:

```text
Artifact bundle verified.
```

Script kiểm presence và các entries quan trọng, chưa chứng minh attachments đã được install. Cần kiểm local/remote repository sau lifecycle. Với quality gate chặt, kiểm thêm những class **không được** có trong `api.jar`.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Có main JAR, thiếu sources | Source Plugin chưa bind hoặc chưa tới verify | Cấu hình `jar-no-fork`, gọi verify trở lên |
| Có source JAR trong target, repo không có | `attach=false` hoặc install chạy trước attach | Kiểm plugin logs, phase và cờ attach |
| Có HTML docs nhưng thiếu Javadoc JAR | Chỉ chạy site hoặc javadoc goal không attach | Bind `javadoc:jar` vào lifecycle |
| Javadoc build fail | Thiếu JDK, tags/HTML/encoding lỗi | Sửa docs và toolchain |
| API JAR ghi đè main | Gọi jar goal lần hai không có classifier | New execution + classifier |
| Tests JAR thiếu JUnit tại consumer | Test dependencies không tự truyền riêng | Khai test deps ở consumer |
| Maven package thiếu docs | Source/Javadoc executions ở verify | Chạy verify/install/deploy |
| Deploy thiếu repository | Không có distributionManagement/altDeploymentRepository | Cấu hình ID/URL hợp lệ |
| Deploy 401/403 | Credentials hoặc server ID sai | Kiểm settings và quyền |
| Deploy 409 release | Repository không cho ghi đè immutable version | Nâng version theo policy |
| Remote SNAPSHOT tên khác | Timestamped snapshot metadata | Kiểm maven-metadata.xml |
| Central upload xong nhưng không tìm được | Chưa validate/publish | Kiểm Portal state |
| Multi-module thiếu variant | Plugin không kế thừa/profile chưa bật | Kiểm effective POM mỗi module |
| Docs ZIP không được deploy | Có file target nhưng chưa attach | Dùng attach-artifact đúng type/classifier |

### 12.1. Thứ tự điều tra

1. Xác định Maven/JDK: `mvn --version` và `java -version`.
2. Chạy `mvn -B clean verify`; kiểm goals Source/Javadoc/JAR có chạy và `jar tf` đúng.
3. Chạy `mvn -B clean install`; so đủ files trong local repo.
4. Chạy deploy **chỉ tới repository đã được phép**; kiểm remote file inventory.
5. Kiểm distributionManagement, server IDs, credentials, release/SNAPSHOT policy.
6. Nếu phát hành qua Central Portal, phân biệt uploaded, validated và published.
7. Consumer độc lập thử resolve đúng GAV/classifier/type; không dựa vào producer workspace.

## 13. Câu hỏi tự luyện và đáp án

**Câu 1.** Tại sao file `target/*-sources.jar` chưa chứng minh đã publish? **Đáp án:** file chưa chắc được attach; cần kiểm repository sau install/deploy.

**Câu 2.** Goal Source Plugin nào thích hợp để bind lifecycle? **Đáp án:** `jar-no-fork`, không fork lifecycle phụ.

**Câu 3.** Trong POM bài, `mvn package` tạo cả source/Javadoc chưa? **Đáp án:** chưa; goals đó bind ở verify.

**Câu 4.** Vì sao Javadoc HTML site khác Javadoc classifier? **Đáp án:** site/report không đồng nghĩa Javadoc JAR attachment; cần `javadoc:jar`.

**Câu 5.** Tests JAR có mang JUnit của project gốc không? **Đáp án:** không; consumer tự khai test libraries và cấu hình scan nếu cần.

**Câu 6.** Consumer lấy `api.jar` thế nào? **Đáp án:** dependency cùng GAV với `classifier=api`, `type=jar`.

**Câu 7.** `mvn install` khác `mvn deploy` ra sao? **Đáp án:** install vào local repository của máy build, deploy lên target repository chia sẻ.

**Câu 8.** Cú pháp alternative repository của Deploy Plugin 3.x? **Đáp án:** `-DaltDeploymentRepository=id::url`.

**Câu 9.** Root POM có `modules` thì child có tự attach Javadoc không? **Đáp án:** không; cần kế thừa hoặc khai plugin execution đúng.

**Câu 10.** Central Publishing Plugin có tự tạo sources/Javadoc không? **Đáp án:** không; publisher phải tạo artifacts và đáp ứng metadata/signatures.

## 14. Checklist bàn giao và nguồn chính thức

- [ ] Maven/JDK/versions được pin và tests thực sự chạy.
- [ ] Source Plugin `jar-no-fork` và Javadoc Plugin `jar` attach trước install.
- [ ] Custom JAR có execution riêng, classifier đúng và nội dung được kiểm.
- [ ] `mvn clean verify` tạo đủ năm artifacts từ cùng commit.
- [ ] `jar tf` xác minh main/sources/javadoc/tests/api contents.
- [ ] `mvn clean install` cho đủ POM/main/attachments ở local repo.
- [ ] Deploy target/credentials hợp lệ và remote nhận đủ artifact family.
- [ ] Release immutability, provenance, signatures, checksums theo policy.
- [ ] CI không để lọt secrets trong source/Javadoc/test classifiers.
- [ ] Consumer từ repo riêng giải quyết đúng GAV/classifier/type.

Tài liệu:

- [Maven Source Plugin — Usage](https://maven.apache.org/plugins/maven-source-plugin/usage.html)
- [Source Plugin — jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Maven Javadoc Plugin — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [Javadoc Plugin — jar goal](https://maven.apache.org/plugins/maven-javadoc-plugin/jar-mojo.html)
- [Maven JAR Plugin — Attached JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/attached-jar.html)
- [Maven JAR Plugin — Test JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/create-test-jar.html)
- [Maven Guide — Attached Tests](https://maven.apache.org/guides/mini/guide-attached-tests.html)
- [Maven Install Plugin — install](https://maven.apache.org/plugins/maven-install-plugin/install-mojo.html)
- [Maven Deploy Plugin — deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html)
- [Sonatype Central — Requirements](https://central.sonatype.org/publish/requirements/)
- [Sonatype Central — Publishing With Maven](https://central.sonatype.org/publish/publish-portal-maven/)