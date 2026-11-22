# Thin JAR và cách phân phối các thư viện bên ngoài trong Maven

## 1. Bài toán: ứng dụng build thành công nhưng chạy ngoài máy dev lại thiếu thư viện

Một project Java có thể build thành công bằng `mvn package` rồi tạo `target/app-1.0.0.jar`. Tuy nhiên khi chuyển file JAR đó sang server khác và gọi `java -jar app-1.0.0.jar`, chương trình có thể báo `NoClassDefFoundError` hoặc `ClassNotFoundException`. Lý do thường gặp: **JAR ứng dụng chỉ chứa lớp và resources do project tạo, còn các dependency JAR nằm riêng trong Maven repository hoặc classpath của máy build**.

Đó là ý tưởng của **thin JAR** (còn gọi là *skinny JAR* hoặc JAR mỏng): giữ mã ứng dụng trong một JAR tương đối nhỏ; đóng gói những thư viện runtime **thành nhiều JAR độc lập**, thường ở thư mục `lib/` bên cạnh application JAR.

Ví dụ bản phân phối:

~~~text
thin-app/
├── thin-app-1.0.0.jar
├── lib/
│   ├── commons-lang3-3.17.0.jar
│   └── ...các dependency runtime khác...
├── bin/
│   ├── run.sh
│   └── run.cmd
└── README.txt
~~~

Một thin JAR **không tự chứa mọi thư viện**. Bạn phải cung cấp đủ thư viện và khiến Java launcher nhìn thấy chúng thông qua:

1. `Class-Path` trong `META-INF/MANIFEST.MF`, thường do Maven JAR Plugin/Maven Archiver sinh.
2. `java -cp "app.jar:lib/*" fully.qualified.Main` trên Linux/macOS hoặc `java -cp "app.jar;lib/*" ...` trên Windows.
3. Một launcher script hoặc cơ chế deploy/container bổ sung classpath đúng cách.

Bài này tập trung **thin JAR và cách phân phối thư viện bên ngoài** trong ngữ cảnh *Shade và Assembly*: cơ chế runtime classpath, Maven JAR/Dependency/Assembly Plugins, cách tạo ZIP và launcher có thể chuyển sang máy khác, kiểm tra trước khi giao sản phẩm, và khi nào nên chuyển sang Shade/uber JAR.

### Mục tiêu học tập

Sau khi đọc, bạn có thể:

- Giải thích thin JAR khác fat/uber JAR và khác một JAR chỉ là thư viện.
- Biết vai trò của `Main-Class` và `Class-Path` trong manifest.
- Sử dụng Maven Dependency Plugin `copy-dependencies` để lấy cả thư viện **transitive** ở scope runtime.
- Tạo một layout phân phối có application JAR và `lib/` khớp với manifest.
- Chạy chính xác bằng `java -jar` hoặc `java -cp` trên Linux/macOS/Windows.
- Biết tại sao `-cp` bị bỏ qua trong chế độ `-jar` và vì sao `Class-Path: lib/*` không tương đương wildcard CLI.
- Đóng gói ZIP bằng Maven Assembly Plugin mà **không giải nén dependencies thành một uber JAR**.
- Kiểm tra missing JAR, sai version, scope, xung đột classpath, resource/service loader và đường dẫn có khoảng trắng.
- Thiết kế release artifact có license, checksums, kiểm tra dependency vulnerabilities và khả năng chạy offline.

## 2. Thin JAR, fat JAR, uber JAR và distribution archive

Một lệnh `mvn package` với `<packaging>jar</packaging>` tạo artifact ứng dụng từ compiled classes/resources. Maven JAR Plugin thông thường **không tự nhét các dependency JAR** vào đó.

| Kiểu đóng gói | Nội dung | Khi chạy | Ưu điểm | Hạn chế |
| --- | --- | --- | --- | --- |
| Thin JAR | Classes/resources của project; dependency ở nơi khác | Classpath/manifest phải trỏ tới thư viện | Phân tách thư viện, dễ quan sát/thay riêng, phù hợp release dạng thư mục | Phải mang đủ file và giữ layout |
| Fat/uber JAR | Classes/resources ứng dụng và nhiều dependencies đã được gộp vào một archive | Thường `java -jar` với Main-Class đúng | Một file thuận tiện deploy | Xử lý trùng resources, ServiceLoader, signed metadata/relocation phức tạp |
| Assembly `jar-with-dependencies` | JAR chứa project cùng dependencies được **unpack** | Cần entry point nếu muốn `java -jar` | Uber JAR cơ bản, nhanh thử nghiệm | Assembly docs nói tính năng uber JAR chỉ ở mức cơ bản |
| Assembly ZIP/TAR thin distribution | Application JAR + các dependency JAR còn nguyên + script/config/docs | Giải nén, chạy launcher hoặc `java -jar` | Gói vận chuyển một archive nhưng giữ classpath nhiều JAR | Cần script/layout/permissions và kiểm tra sau giải nén |

**Phân biệt hai loại “một file”**:

- `thin-app-1.0.0-thin.zip` là **một file để vận chuyển**, nhưng khi giải nén chứa nhiều JAR.
- `thin-app-1.0.0-all.jar` kiểu uber JAR là **một runtime archive** có thể chứa lớp từ nhiều dependencies.

ZIP chứa nhiều JAR **không làm những JAR con tự trở thành classpath**. Java launcher không tự tìm toàn bộ `lib/` nếu manifest/script chưa khai.

### 2.1. Thin JAR có phải luôn là executable JAR?

Không. Một thin JAR có thể chỉ là library artifact, **không có `Main-Class`**. Nếu là ứng dụng muốn chạy `java -jar`, manifest phải khai Main-Class. Nếu chỉ phát hành library dùng cho ứng dụng khác, không nhất thiết cần launcher hay Main-Class; Maven/Gradle của ứng dụng tiêu thụ sẽ giải quyết transitive dependencies theo metadata.

Trong bài này, ví dụ là **ứng dụng CLI Java 17**, nên ta cố ý cấu hình Main-Class và classpath.

### 2.2. JAR có thể nhỏ nhưng bản phân phối không hề nhỏ

Khi nhìn `thin-app-1.0.0.jar` thấy vài KB, đừng kết luận toàn bộ deployment chỉ tốn vài KB: `lib/` có thể chứa hàng chục MB hoặc hơn. Hãy đo và kiểm kê **tổng distribution**, bao gồm dependencies, scripts, runtime Java nếu được đóng gói và file cấu hình.

### 2.3. So với maven-shade-plugin

Maven Shade Plugin có nhiệm vụ đóng gói **uber JAR**, hỗ trợ **relocation** (đổi package namespace của dependencies) và resource transformers (ví dụ merge `META-INF/services`). Không dùng Shade chỉ để tạo một thư mục `lib/` vì mục tiêu của Shade là khác. Nếu dependency conflict hoặc cần một JAR độc lập là mục tiêu chính, hãy đánh giá Shade; nếu muốn giữ dependencies độc lập, thin distribution sẽ tự nhiên hơn.

## 3. Cơ chế Class-Path trong manifest

Bên trong JAR có metadata:

~~~text
META-INF/
  MANIFEST.MF
~~~

Một application thin JAR có thể có manifest minh họa:

~~~text
Manifest-Version: 1.0
Main-Class: dev.example.thin.ThinMain
Class-Path: lib/commons-lang3-3.17.0.jar

~~~

`Main-Class` là **tên lớp đầy đủ** chứa `public static void main(String[] args)`. `Class-Path` là danh sách **relative URL/path entries** được phân cách bằng khoảng trắng (không dùng dấu `:` hoặc `;` như classpath CLI). Java JAR specification quy định mỗi JAR chỉ có tối đa một `Class-Path` header; manifest cũng có quy tắc xuống dòng/folding khi dòng dài.

Đối với layout:

~~~text
release/
  thin-app-1.0.0.jar
  lib/
    commons-lang3-3.17.0.jar
~~~

`lib/commons-lang3-3.17.0.jar` được giải theo vị trí **JAR chứa manifest**, không phải nhất thiết theo thư mục hiện hành của shell. Vì vậy khi chạy ở thư mục cha:

~~~bash
java -jar release/thin-app-1.0.0.jar
~~~

Java vẫn có thể tìm `release/lib/commons-lang3-3.17.0.jar` nếu cấu hình và file tương ứng đúng.

### 3.1. Manifest Class-Path không tự động liệt kê toàn thư mục

`Class-Path: lib/*` **không phải** cách portable để Java tự nạp mọi `.jar` khi xử lý manifest. Theo JAR specification, entries là những relative URLs. Cú pháp wildcard `lib/*` là tiện ích **của Java launcher `-cp`/`-classpath`**, không phải lời hứa của manifest Class-Path.

Khi có 3 dependencies, manifest có thể cần:

~~~text
Class-Path: lib/a.jar lib/b.jar lib/c.jar
~~~

Thay vì tự gõ danh sách này, Maven Archiver với `<addClasspath>true</addClasspath>` sẽ tạo các entries từ những dependencies mà build biết. `<classpathPrefix>lib/</classpathPrefix>` đặt tiền tố vị trí thư viện. **Bạn vẫn phải copy các JAR đó tới chính xác layout ấy**; manifest không tải chúng từ Maven Central lúc runtime.

### 3.2. addClasspath không phải “đóng gói dependencies”

Khai:

~~~xml
<archive>
    <manifest>
        <mainClass>dev.example.thin.ThinMain</mainClass>
        <addClasspath>true</addClasspath>
        <classpathPrefix>lib/</classpathPrefix>
    </manifest>
</archive>
~~~

giúp Maven JAR Plugin tạo manifest, **không copy dependencies** và cũng không tự sinh `lib/` bên cạnh JAR. Đây là sai sót phổ biến khi người học chỉ thêm `addClasspath` rồi gửi JAR cho người khác.

### 3.3. java -jar và java -cp có hai cách định classpath

Với manifest đúng và `lib/` đúng:

~~~bash
java -jar release/thin-app-1.0.0.jar
~~~

Với classpath tự khai, Linux/macOS:

~~~bash
java -cp 'release/thin-app-1.0.0.jar:release/lib/*' dev.example.thin.ThinMain
~~~

Windows (PowerShell hoặc cmd.exe):

~~~powershell
java -cp "release\thin-app-1.0.0.jar;release\lib\*" dev.example.thin.ThinMain
~~~

**Quy tắc**:

- `-jar` chọn application entry point từ `Main-Class`; JVM **bỏ qua** các thiết lập user classpath `-cp`/CLASSPATH theo semantics của chế độ `-jar`. Nó vẫn xử lý các manifest classpath entries phù hợp.
- `-cp` cần tên class main sau classpath, **không dùng `-jar`** trong cùng lệnh để cố gộp hai cơ chế.
- Dấu phân cách `:` trên các hệ POSIX, `;` trên Windows.
- Dùng dấu nháy quanh chuỗi có `lib/*` để shell không tự mở rộng `*` thành danh sách file theo cú pháp của shell. Java launcher xử lý wildcard `lib/*` với các JAR trực tiếp trong thư mục.
- Wildcard không đệ quy qua mọi thư mục con và thứ tự JAR được mở rộng **không được bảo đảm**. Không dùng `lib/*` nếu tính đúng đắn phụ thuộc thứ tự của các JAR bị trùng class.

## 4. Những dependencies nào phải đi cùng thin JAR?

Maven dependency graph có nhiều scopes; khi triển khai ứng dụng, cần chọn các artifact **thực sự cần lúc runtime**, bao gồm transitive dependencies.

| Dependency scope | Có mặt trên runtime classpath thông thường? | Có nên copy vào thin distribution? |
| --- | --- | --- |
| `compile` (mặc định) | Có | Có, trừ trường hợp thiết kế đặc biệt |
| `runtime` | Có | Có |
| `provided` | Maven giả định môi trường cung cấp; thông thường không nằm trong runtime scope | Chỉ thêm nếu môi trường deploy **không** cung cấp nhưng ứng dụng cần; nên sửa scope/design đúng |
| `test` | Không thuộc runtime production | Không |
| `system` | Có semantics đặc biệt và gắn với local filesystem path | Không nên dùng cho release có thể tái lập; thay bằng dependency repository chuẩn |
| `import` | Dùng trong dependencyManagement với type `pom` cho BOM | Không phải thư viện runtime để copy |

Thông thường `maven-dependency-plugin:copy-dependencies` với `<includeScope>runtime</includeScope>` lấy **compile + runtime dependencies** (bao gồm transitive được resolve), tránh copy test-only libraries. Tài liệu Dependency Plugin định nghĩa `includeScope=runtime` là tập phù hợp với runtime và compile scopes. Đừng hiểu nó là “chỉ những dependency được khai trực tiếp với scope runtime”.

### 4.1. Transitive dependencies quan trọng

Giả sử application trực tiếp phụ thuộc `library-a`, trong khi `library-a` phụ thuộc `library-b` và `library-c`. Nếu runtime cần `b` và `c` mà bạn chỉ copy `a`, chương trình sẽ fail dù `pom.xml` của ứng dụng chỉ ghi một dependency trực tiếp.

`dependency:copy-dependencies` mặc định có thể copy cả transitive graph. **Không bật `excludeTransitive=true` chỉ để giảm số file** khi chưa kiểm tra rằng toàn bộ runtime graph còn hoạt động.

Lệnh điều tra:

~~~bash
mvn -B -ntp dependency:tree -Dscope=runtime
~~~

Trong môi trường muốn pin plugin version:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dscope=runtime
~~~

Kiểm tra kết quả để biết version nào được chọn sau dependency mediation và liệu có conflicts/omissions.

### 4.2. Optional, exclusions và phiên bản trùng

- `<optional>true</optional>` ảnh hưởng khả năng dependency được truyền cho project sử dụng library, không tự biến thư viện thành “chỉ dùng lúc test”. Dự án tự khai dependency optional vẫn có thể cần nó khi chạy.
- `<exclusions>` cắt nhánh transitive dependency; có thể gây `ClassNotFoundException` khi application dùng chức năng đó.
- Maven conflict mediation chọn một version theo dependency graph và dependencyManagement; copy tất cả phiên bản từng tồn tại ở mọi nhánh vào `lib/` **không phải cách sửa conflict**.
- Nếu hai artifact cho ra **tên file giống nhau** trong cùng `lib/`, copy flat directory có nguy cơ overwrite. Maven Dependency Plugin có các tùy chọn bố trí thư mục, nhưng thay đổi layout phải đồng bộ với manifest/classpath.

### 4.3. Runtime JDK cũng là một dependency của bản phân phối

Thin JAR không tự nhúng JVM. Người dùng vẫn phải có **Java runtime đủ phiên bản**. Ví dụ class được biên dịch `--release 17` cần JVM hỗ trợ class version Java 17; chạy trên Java 11 sẽ báo `UnsupportedClassVersionError`.

Nếu sản phẩm cần “giải nén là chạy, không cần cài Java”, hãy đánh giá `jlink`/`jpackage` hoặc đóng gói runtime được phép phân phối. Đây là chiến lược khác với việc copy các thư viện Maven vào `lib/`.

## 5. Lab hoàn chỉnh: Java 17, Commons Lang, JUnit 5 và thin JAR

Lab tạo một application JAR có manifest, copy `commons-lang3` vào `target/dist/lib`, rồi stage application JAR bên cạnh `lib`.

Mục tiêu quan sát:

- `target/thin-app-1.0.0.jar` **không chứa class `StringUtils`**.
- `target/dist/lib/commons-lang3-3.17.0.jar` chứa thư viện ngoài.
- `java -jar target/dist/thin-app-1.0.0.jar` chạy nhờ manifest Class-Path.
- Test `ThinMainTest` dùng JUnit 5 ở scope test, nhưng JUnit **không nằm trong `dist/lib`**.
- Sau khi di chuyển **cả thư mục `dist`** sang máy khác có Java 17+, ứng dụng vẫn chạy mà không cần Maven repository có sẵn trên máy đó.

### 5.1. Cấu trúc nguồn

~~~text
thin-jar-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── dev/example/thin/ThinMain.java
│   │   └── resources/
│   │       └── app-info.properties
│   └── test/
│       └── java/
│           └── dev/example/thin/ThinMainTest.java
└── target/                 (do Maven tạo)
~~~

Yêu cầu: Maven 3.9.x, JDK 17+ (`java -version`/`mvn -version`), mạng hoặc mirror Maven để tải các plugins/dependencies ở lần build đầu. Thư viện `commons-lang3:3.17.0` tương thích với lab. Không cần Spring Boot, database hay Docker.

### 5.2. POM đầy đủ

Tạo file `thin-jar-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>thin-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Thin JAR Lab</name>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <!-- Thư viện phải có ở production runtime -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>

        <!-- Chỉ cho unit tests; không copy sang dist/lib -->
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
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <!-- JAR chứa classes/resources + manifest, KHÔNG gộp thư viện -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.example.thin.ThinMain</mainClass>
                            <addClasspath>true</addClasspath>
                            <classpathPrefix>lib/</classpathPrefix>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <!-- Copy runtime libraries ra thư mục bên ngoài JAR -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
                <executions>
                    <execution>
                        <id>stage-runtime-libraries</id>
                        <phase>package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <outputDirectory>
                                ${project.build.directory}/dist/lib
                            </outputDirectory>
                            <includeScope>runtime</includeScope>
                            <excludeTransitive>false</excludeTransitive>
                            <useRepositoryLayout>false</useRepositoryLayout>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Cấu hình này có hai việc độc lập tại phase `package`:

1. `jar:jar` được `jar` packaging gắn mặc định vào lifecycle, tạo `target/thin-app-1.0.0.jar` với manifest.
2. Execution `stage-runtime-libraries` của Dependency Plugin copy compile/runtime dependencies vào `target/dist/lib`.

**Chưa có bước tự động copy application JAR từ `target/` sang `target/dist/`** trong POM gốc. Bước đó được thực hiện ở mục 5.6 để làm rõ công việc staging. Khi dùng Assembly Plugin ở mục 9, chúng ta có thể tạo **distribution ZIP tự động** thay cho staging thủ công.

**Lưu ý về XML:** Dòng `${project.build.directory}/dist/lib` trong `<outputDirectory>` được đặt trên nhiều dòng để bài dễ đọc. Nếu công cụ XML/Maven gặp vấn đề với whitespace trong một cấu hình cụ thể, hãy viết một dòng tường minh:

~~~xml
<outputDirectory>${project.build.directory}/dist/lib</outputDirectory>
~~~

Mục đích chính vẫn là ghi runtime dependency files vào `target/dist/lib`; không phải đưa các JAR vào classpath của Maven khi nó biên dịch.

### 5.3. Main Java 17

Tạo `src/main/java/dev/example/thin/ThinMain.java`:

~~~java
package dev.example.thin;

import org.apache.commons.lang3.StringUtils;

public final class ThinMain {
    private ThinMain() {
    }

    public static String render(String source) {
        return StringUtils.capitalize(source)
                + "|" + StringUtils.reverse("Maven");
    }

    public static void main(String[] args) {
        String subject = args.length == 0
                ? "thin jar"
                : args[0];
        System.out.println("THIN JAR OK: " + render(subject));
    }
}
~~~

`StringUtils.capitalize` và `StringUtils.reverse` thuộc **Apache Commons Lang 3**, không thuộc JDK. Do đó khi JVM tải code cần class `StringUtils` mà thư viện ngoài không nằm trong runtime classpath, ứng dụng có thể thất bại với `NoClassDefFoundError`.

### 5.4. Unit test JUnit 5

Tạo `src/test/java/dev/example/thin/ThinMainTest.java`:

~~~java
package dev.example.thin;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ThinMainTest {

    @Test
    void usesRuntimeLibraryCorrectly() {
        assertEquals("Thin jar|nevaM",
                ThinMain.render("thin jar"));
    }
}
~~~

Test này xác nhận hành vi của Commons Lang khi test JVM có dependency trên classpath của Maven/Surefire. Nó **không** chứng minh bản phân phối ZIP đã hoàn chỉnh; kiểm tra ZIP và chạy trên thư mục `dist` vẫn là bước riêng.

### 5.5. Main resource đi theo ứng dụng

Tạo `src/main/resources/app-info.properties`:

~~~properties
app.id=thin-app
app.version=1.0.0
~~~

Theo Maven Standard Directory Layout, file này được copy vào `target/classes/app-info.properties` rồi JAR Plugin đóng gói vào JAR ứng dụng. Nó không phụ thuộc thư viện Commons Lang, không cần copy riêng ra `lib/` và cũng không chứa bí mật.

### 5.6. Build và stage file để chạy

Tại `thin-jar-lab`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean package
~~~

Khi build thành công, Surefire dự kiến chạy **một test**, không có failures. Dấu hiệu nhận diện trong Maven log:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Trên Linux/macOS, copy JAR của project vào thư mục phân phối:

~~~bash
mkdir -p target/dist
cp target/thin-app-1.0.0.jar target/dist/
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path target/dist | Out-Null
Copy-Item -LiteralPath target/thin-app-1.0.0.jar -Destination target/dist/
~~~

Khi dùng cấu hình POM gốc, thư mục dự kiến:

~~~text
target/
├── thin-app-1.0.0.jar
├── classes/
│   ├── dev/example/thin/ThinMain.class
│   └── app-info.properties
├── test-classes/
│   └── dev/example/thin/ThinMainTest.class
├── surefire-reports/
│   └── TEST-dev.example.thin.ThinMainTest.xml
└── dist/
    ├── thin-app-1.0.0.jar
    └── lib/
        └── commons-lang3-3.17.0.jar
~~~

Một số file/thư mục Maven nội bộ khác cũng được tạo, nên đây là **sơ đồ những thành phần cần kiểm tra** chứ không phải danh sách chính xác toàn bộ `target`.

`JUnit` và những dependency test-only **không** nên xuất hiện trong `target/dist/lib` vì plugin `copy-dependencies` đã chọn `includeScope=runtime`. Với nhiều dependencies compile/runtime, `lib/` còn chứa các JAR transitive được Maven resolve.

### 5.7. Chạy thin JAR có manifest

Sau staging:

~~~bash
java -jar target/dist/thin-app-1.0.0.jar
~~~

**Stdout chính xác của chương trình ví dụ**:

~~~text
THIN JAR OK: Thin jar|nevaM
~~~

Cách giải thích:

- JVM tìm `dev.example.thin.ThinMain` qua `Main-Class`.
- Maven Archiver đã đặt `Class-Path: lib/commons-lang3-3.17.0.jar` (hoặc một dòng gấp tương đương) vào manifest.
- JVM giải đường dẫn relative tới `target/dist/thin-app-1.0.0.jar` và tìm thư viện tại `target/dist/lib/commons-lang3-3.17.0.jar`.
- `StringUtils.capitalize("thin jar")` trả `Thin jar`.
- `StringUtils.reverse("Maven")` trả `nevaM`.

Nếu chạy:

~~~bash
java -jar target/thin-app-1.0.0.jar
~~~

trong khi chỉ có thư viện tại `target/dist/lib`, lệnh này **không có cùng layout**. Manifest trong `target/thin-app-1.0.0.jar` sẽ tìm `target/lib/` theo vị trí JAR. Có thể xảy ra `NoClassDefFoundError` dù cùng một byte JAR. Đó là minh họa rõ nhất rằng **thin JAR không tự hoàn chỉnh nếu thiếu phân phối thư viện đúng vị trí**.

### 5.8. Truyền tham số vào Java main

Ví dụ:

~~~bash
java -jar target/dist/thin-app-1.0.0.jar "release check"
~~~

Kết quả chính xác:

~~~text
THIN JAR OK: Release check|nevaM
~~~

Chương trình lấy `args[0]` là `release check`. Những arguments sau tên JAR là program arguments. Nếu cần `-Xmx` hoặc `-D` của JVM, phải đặt **trước `-jar`**, ví dụ:

~~~bash
java -Xmx256m -Dapp.stage=local -jar target/dist/thin-app-1.0.0.jar
~~~

`app.stage` không được chương trình ví dụ đọc, nên stdout vẫn như mặc định. Đây là minh họa vị trí cú pháp JVM options, không phải xác nhận thay đổi hành vi ứng dụng.

## 6. Kiểm tra manifest, JAR và dependencies được đóng gói

### 6.1. Manifest được Maven JAR Plugin tạo

Các yếu tố thiết yếu trong cấu hình:

~~~xml
<manifest>
    <mainClass>dev.example.thin.ThinMain</mainClass>
    <addClasspath>true</addClasspath>
    <classpathPrefix>lib/</classpathPrefix>
</manifest>
~~~

Kết quả `META-INF/MANIFEST.MF` có các dòng liên quan như:

~~~text
Main-Class: dev.example.thin.ThinMain
Class-Path: lib/commons-lang3-3.17.0.jar
~~~

Manifest thực tế còn có `Manifest-Version`, `Created-By` hoặc metadata khác. Khi Class-Path dài, manifest có quy tắc **wrap** lines; đừng phân tích ngây thơ rằng mọi dependency phải nằm trên đúng một dòng text. Công cụ `jar` và JVM hiểu cú pháp manifest hợp lệ.

Để xem file manifest trên Linux/macOS nếu có `unzip`:

~~~bash
unzip -p target/dist/thin-app-1.0.0.jar META-INF/MANIFEST.MF
~~~

Hoặc chỉ dùng công cụ JDK ở một thư mục kiểm tra riêng:

~~~bash
mkdir -p target/manifest-check
cd target/manifest-check
jar xf ../dist/thin-app-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ../..
~~~

Windows PowerShell có thể dùng `jar xf` trong một thư mục tạm phù hợp rồi `Get-Content`; không cần mở/chỉnh source JAR. Không chạy `jar xf` bừa bãi tại root source project để tránh tạo thư mục `META-INF` ngoài ý muốn.

### 6.2. Chứng minh application JAR không chứa thư viện ngoài

~~~bash
jar tf target/dist/thin-app-1.0.0.jar
~~~

Tìm:

~~~text
dev/example/thin/ThinMain.class
app-info.properties
META-INF/MANIFEST.MF
~~~

Không kỳ vọng có:

~~~text
org/apache/commons/lang3/StringUtils.class
~~~

vì class `StringUtils` nằm trong JAR bên ngoài:

~~~bash
jar tf target/dist/lib/commons-lang3-3.17.0.jar
~~~

Trong output của lệnh cuối có thể tìm `org/apache/commons/lang3/StringUtils.class`.

**Đừng coi file có hậu tố `.jar` bên trong JAR ứng dụng là đã tự được thêm vào Java classpath.** JVM application classloader mặc định không tự quét nested JARs; một số framework có launcher riêng để giải quyết kiểu đóng gói đó, nhưng không phải behavior chung của plain thin JAR.

### 6.3. Xác minh bản phân phối offline

Một thử nghiệm hữu ích: copy **chỉ thư mục `target/dist`** sang một máy/thư mục khác có JDK 17+ nhưng **không có project source và không cần Maven**. Gọi:

~~~bash
java -jar thin-app-1.0.0.jar
~~~

từ bên trong thư mục dist. Nếu in:

~~~text
THIN JAR OK: Thin jar|nevaM
~~~

thì minh chứng rằng layout ứng dụng + lib đủ cho **luồng ví dụ** này. Tuy nhiên một smoke test không chứng minh đã bao quát **mọi đường code**, ServiceLoader plugins, native libraries hay module-specific dependencies.

## 7. Chạy bằng classpath tường minh thay vì manifest

Có trường hợp bạn không muốn dùng `java -jar`: ví dụ cần thêm nhiều JAR ngoài, config directories hoặc lựa chọn main class khác. Khi đó dùng `java -cp`.

Linux/macOS:

~~~bash
java -cp 'target/dist/thin-app-1.0.0.jar:target/dist/lib/*' \
  dev.example.thin.ThinMain
~~~

Windows PowerShell/cmd.exe:

~~~powershell
java -cp "target\dist\thin-app-1.0.0.jar;target\dist\lib\*" dev.example.thin.ThinMain
~~~

Cả hai có thể in:

~~~text
THIN JAR OK: Thin jar|nevaM
~~~

### 7.1. Quy tắc classpath cần nhớ

- `-cp` (hoặc `-classpath` / `--class-path`) nhận danh sách directories và JAR/ZIP archives.
- Dấu phân cách giữa entries: `:` trên POSIX, `;` trên Windows.
- `lib/*` mở rộng thành các file có đuôi `.jar` hoặc `.JAR` **trực tiếp trong thư mục lib**; không tự quét subdirectories và thứ tự các JAR không được bảo đảm.
- Viết `'...:lib/*'` hoặc `"..."` để shell không mở rộng wildcard sai mục đích.
- Một thư mục resource ngoài JAR có thể được thêm vào `-cp` như một entry, ví dụ `config`, nếu ứng dụng cần đọc các file đó qua classloader.
- `java -cp ... dev.example.thin.ThinMain` chỉ ra main class tường minh; `Main-Class` trong manifest không bắt buộc trong trường hợp này.
- Khi dùng `java -jar`, đặt `-cp` trong cùng command không phải cách đáng tin để thêm lib path; hãy sửa manifest/distribution hoặc dùng hoàn toàn chế độ `-cp`.

### 7.2. Vấn đề thứ tự và trùng class

Giả sử `lib/` vô tình có `library-1.0.jar` và `library-2.0.jar` cùng định nghĩa `com.example.Library`. Với wildcard `lib/*`, thứ tự các JAR được mở rộng là không xác định; ứng dụng có thể tải phiên bản không mong muốn. Giải pháp **không phải** “đặt tên JAR theo alphabet để đảm bảo được chọn”, mà là sửa dependency tree và chỉ phân phối một version hợp lệ.

### 7.3. Classpath khác module path

Java 9+ có **JPMS module path** (`--module-path`, `-m`). Thin JAR trên classpath truyền thống vẫn chạy như ví dụ Java 17 ở bài này. Nhưng một **named modular application** có `module-info.java` có thể cần module path và module resolution, không thể thay mọi trường hợp bằng `Class-Path` trong manifest.

Nếu ứng dụng của bạn là modular JAR hoặc dùng automatic modules, cần thiết kế launcher/module path riêng và xác minh `--module-path` cũng như `--add-modules` theo Java/JDK docs. Đừng kết luận thin JAR “không hỗ trợ Java 17” chỉ vì một ứng dụng modular cần launcher khác.

## 8. Launcher script để người dùng không phải nhớ lệnh

### 8.1. Linux/macOS: bin/run.sh

Sau khi stage, tạo `target/dist/bin/run.sh` (hoặc để nguồn trong `src/distribution/bin/run.sh` rồi copy vào dist):

~~~sh
#!/usr/bin/env sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec java -jar "$APP_DIR/thin-app-1.0.0.jar" "$@"
~~~

Giải thích:

- `dirname -- "$0"` nhận thư mục chứa script.
- `/..` đưa vị trí từ `bin/` lên thư mục distribution.
- `pwd` dùng đường dẫn tuyệt đối nhằm hạn chế phụ thuộc current working directory.
- `"$@"` giữ ranh giới arguments (bao gồm chuỗi có dấu cách).
- `exec` thay shell process bằng Java trên POSIX.
- Script giả định `java` có sẵn trên PATH; có thể sửa để ưu tiên `JAVA_HOME` nếu yêu cầu hạ tầng.

Chạy:

~~~bash
chmod +x target/dist/bin/run.sh
target/dist/bin/run.sh "release check"
~~~

Kỳ vọng:

~~~text
THIN JAR OK: Release check|nevaM
~~~

### 8.2. Windows: bin/run.cmd

Tạo `target/dist/bin/run.cmd`:

~~~bat
@echo off
setlocal
set "APP_DIR=%~dp0.."
java -jar "%APP_DIR%\thin-app-1.0.0.jar" %*
exit /b %ERRORLEVEL%
~~~

`%~dp0` là thư mục chứa batch file. `%*` truyền arguments của caller. Đường dẫn JAR được đặt trong dấu nháy để hỗ trợ paths có khoảng trắng. Nếu cần các trường hợp quoting phức tạp trong args, phải kiểm thử riêng với shell/Windows version thật; batch quoting không hoàn toàn giống POSIX `"$@"`.

Chạy trong PowerShell:

~~~powershell
.\target\dist\bin\run.cmd "release check"
~~~

Kỳ vọng:

~~~text
THIN JAR OK: Release check|nevaM
~~~

### 8.3. Copy scripts vào dist

Trên Linux/macOS:

~~~bash
mkdir -p target/dist/bin
cp src/distribution/bin/run.sh src/distribution/bin/run.cmd target/dist/bin/
chmod +x target/dist/bin/run.sh
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path target/dist/bin | Out-Null
Copy-Item src/distribution/bin/run.sh,src/distribution/bin/run.cmd target/dist/bin/
~~~

Lưu ý: để chạy được các lệnh `cp` trên, bạn **phải tạo hai source scripts** tương ứng bằng nội dung ở mục 8.1 và 8.2 tại `src/distribution/bin/` trước. Nếu chỉ đặt script trực tiếp trong `target/dist/bin`, không cần bước copy này nhưng cần giải pháp để chúng không mất khi `mvn clean`.

### 8.4. Đừng hard-code đường dẫn tới ~/.m2

Một script kiểu:

~~~sh
java -cp "$HOME/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar:target/thin-app-1.0.0.jar" dev.example.thin.ThinMain
~~~

có thể chạy trên laptop nhưng **không phải bản phân phối độc lập**. Nó phụ thuộc local Maven repository, path OS và phiên bản thư viện có sẵn. Launcher của release nên trỏ vào dependencies **nằm trong gói** hoặc một classpath được hạ tầng quản lý rõ ràng.

## 9. Tự động tạo thin distribution ZIP với Maven Assembly Plugin

Bước staging thủ công giúp hiểu cơ chế, nhưng CI/release thực tế thường muốn tạo **một ZIP** chứa application JAR + `lib/` + scripts. Maven Assembly Plugin 3.8.0 có thể làm việc này bằng custom descriptor; **không cần chuyển sang uber JAR**.

### 9.1. Cấu trúc bổ sung

~~~text
thin-jar-lab/
├── pom.xml
├── src/
│   ├── assembly/
│   │   └── thin.xml
│   └── distribution/
│       └── bin/
│           ├── run.sh
│           └── run.cmd
└── ...
~~~

Nguồn `src/distribution/bin/run.sh` và `run.cmd` dùng chính nội dung đầy đủ ở mục 8. Khi ZIP được giải nén, scripts sẽ trỏ lên JAR ở root distribution.

### 9.2. Custom assembly descriptor

Tạo `src/assembly/thin.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
                              https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>thin</id>

    <formats>
        <format>zip</format>
    </formats>

    <includeBaseDirectory>false</includeBaseDirectory>

    <fileSets>
        <!-- Project JAR giữ nguyên, đặt tại root ZIP -->
        <fileSet>
            <directory>${project.build.directory}</directory>
            <outputDirectory>/</outputDirectory>
            <includes>
                <include>${project.build.finalName}.jar</include>
            </includes>
            <fileMode>0644</fileMode>
        </fileSet>

        <!-- Launcher POSIX có quyền execute -->
        <fileSet>
            <directory>src/distribution/bin</directory>
            <outputDirectory>/bin</outputDirectory>
            <includes>
                <include>run.sh</include>
            </includes>
            <fileMode>0755</fileMode>
        </fileSet>

        <!-- Launcher Windows -->
        <fileSet>
            <directory>src/distribution/bin</directory>
            <outputDirectory>/bin</outputDirectory>
            <includes>
                <include>run.cmd</include>
            </includes>
            <fileMode>0644</fileMode>
        </fileSet>
    </fileSets>

    <dependencySets>
        <dependencySet>
            <!-- Không thêm project artifact lần hai vào lib -->
            <useProjectArtifact>false</useProjectArtifact>
            <unpack>false</unpack>
            <scope>runtime</scope>
            <outputDirectory>/lib</outputDirectory>
        </dependencySet>
    </dependencySets>
</assembly>
~~~

Ý nghĩa then chốt:

- `fileSet` thứ nhất lấy JAR sản phẩm đã được `jar:jar` tạo ở `target/` và đưa vào root ZIP.
- `dependencySet` có `scope=runtime` lấy dependencies phù hợp và đặt các **JAR còn nguyên** dưới `lib/`.
- `useProjectArtifact=false` tránh đưa thin-app JAR một lần nữa vào `lib/`.
- `unpack=false` giữ JAR files, **không** giải nén classes/resources vào một uber JAR.
- `fileSets` chứa launchers `run.sh` và `run.cmd`, đồng thời metadata permission cho shell script.
- `includeBaseDirectory=false` để ZIP mở trực tiếp ra `thin-app-1.0.0.jar`, `lib/` và `bin/` thay vì thêm một root folder bất ngờ.

**Vì sao không dùng descriptor `jar-with-dependencies`?** Descriptor đó **unpack dependencies vào một JAR**; nó được thiết kế cho uber JAR cơ bản. Thin distribution cần dependency JAR còn nguyên ở `lib/`.

### 9.3. Thêm Assembly Plugin vào POM

Trong `<build><plugins>` của POM ở mục 5, thêm plugin sau; đây là **fragment**, giữ nguyên những plugins đã có:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.8.0</version>
    <configuration>
        <descriptors>
            <descriptor>src/assembly/thin.xml</descriptor>
        </descriptors>
        <appendAssemblyId>true</appendAssemblyId>
    </configuration>
    <executions>
        <execution>
            <id>make-thin-zip</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Với `mvn clean package`, mặc định `jar:jar` được packaging `jar` thực hiện trong phase `package`, sau đó goal `assembly:single` được bind tường minh cũng ở `package` sẽ tạo ZIP. Trong project mẫu, Dependency Plugin cũng stage dependencies tại `target/dist/lib`, nhưng Assembly `dependencySet` **tự resolve/copy dependencies vào ZIP**, không cần dựa vào thư mục dist thủ công. Khi chuyển hẳn sang Assembly để phát hành, có thể loại execution `stage-runtime-libraries` nếu không cần cây `target/dist` song song.

### 9.4. Build và kiểm tra ZIP

Chạy:

~~~bash
mvn -B -ntp clean package
~~~

Artifact ZIP dự kiến:

~~~text
target/thin-app-1.0.0-thin.zip
~~~

Mở archive, tìm:

~~~text
thin-app-1.0.0.jar
lib/commons-lang3-3.17.0.jar
bin/run.sh
bin/run.cmd
~~~

Giải nén ra một thư mục sạch rồi chạy:

~~~bash
java -jar thin-app-1.0.0.jar
~~~

Tại thư mục đã giải nén, stdout:

~~~text
THIN JAR OK: Thin jar|nevaM
~~~

Hoặc gọi `bin/run.sh` hoặc `bin\run.cmd` phù hợp OS. Nếu bạn chỉ kiểm tra bằng `java -jar target/dist/thin-app-1.0.0.jar` nhưng không giải nén ZIP, **chưa chứng minh descriptor ZIP đã đúng**. Cần smoke test **chính output ZIP** sau khi build.

### 9.5. Tạo release với checksums

Đối với bản phát hành, có thể tạo SHA-256 của ZIP:

Linux/macOS:

~~~bash
sha256sum target/thin-app-1.0.0-thin.zip
~~~

Windows PowerShell:

~~~powershell
Get-FileHash target/thin-app-1.0.0-thin.zip -Algorithm SHA256
~~~

Checksum giúp xác minh file không bị thay đổi trên đường vận chuyển, **không chứng minh người phát hành đáng tin**. Nếu cần xác thực nhà phát hành, dùng chữ ký và quy trình phân phối trust key phù hợp.

## 10. So sánh chiến lược Shade, Assembly và Dependency Plugin

| Nhu cầu | Công cụ phù hợp | Điều cần cẩn thận |
| --- | --- | --- |
| Tạo JAR chứa classes của ứng dụng | Maven JAR Plugin | Chưa tự gồm dependency |
| Ghi Main-Class và danh sách lib trong manifest | Maven JAR Plugin + Maven Archiver | Phải giữ đúng layout `lib/` |
| Copy runtime dependencies vào thư mục riêng | Maven Dependency Plugin `copy-dependencies` | Chọn `includeScope=runtime`, để transitive còn nguyên |
| Gói JAR + lib + scripts thành ZIP/TAR | Maven Assembly Plugin + custom descriptor | `unpack=false`, folder structure và permissions |
| Gộp dependencies thành một uber JAR | Maven Shade Plugin | Resource transformers, relocation, signatures, duplicate classes |
| Uber JAR cơ bản thật nhanh | Assembly `jar-with-dependencies` | Ít tùy biến hơn Shade |
| Chỉ đóng gói thư viện API cho Maven Central | Maven JAR Plugin + POM metadata | Không cần copy `lib/` nếu người dùng giải quyết qua Maven |
| Phát hành native JVM/runtime image | `jlink`/`jpackage` hoặc container packaging | Không còn chỉ là thin JAR distribution |

### 10.1. Khi nào thin JAR có lợi?

- Ứng dụng vận hành ở môi trường có quy định `app.jar + lib/` rõ ràng.
- Bạn muốn điều tra version của mỗi dependency bằng file riêng hoặc scan từng JAR.
- Một hệ thống phân phối cần cập nhật một thư viện riêng biệt theo quy trình kiểm soát (vẫn phải test tương thích).
- Bạn có script/installer đáng tin, và không bắt buộc artifact runtime chỉ là một file.
- Runtime classpath thường, không cần relocation hoặc xử lý đặc biệt các resources trùng của nhiều libraries.

### 10.2. Khi nào uber JAR có thể tốt hơn?

- Muốn gửi **một runtime file** tới môi trường Java đơn giản, không muốn quản lý `lib/` ngoài.
- Có nhu cầu Shade relocation để tránh xung đột package.
- Dependency graph chứa nhiều `META-INF/services` hoặc resources trùng cần transformer hợp lệ.
- Cơ chế phát hành chạy trực tiếp `java -jar app-all.jar` và phù hợp với một file duy nhất.

Tuy nhiên một uber JAR **không tự giải quyết** mọi vấn đề classpath, native library, reflective access hoặc JPMS module path. Hãy test các use case thực tế.

## 11. Những cấu hình copy-dependencies dễ gây bất ngờ

Maven Dependency Plugin `copy-dependencies` có nhiều tham số; tránh chỉnh nhiều cờ cùng lúc khi chưa hiểu.

### 11.1. includeScope không phải bộ lọc bằng exact string

`<includeScope>runtime</includeScope>` thường lấy các dependencies cần ở runtime (gồm compile và runtime), **không chỉ những khai báo có scope literal `runtime`**. `includeScope=test` gần hơn với toàn bộ set trên test classpath. `includeScope=provided` và `includeScope=system` có semantics khác, không phù hợp gói application runtime thông thường.

Không nhầm `includeScope` với `excludeScope`. Chọn một policy dễ giải thích rồi dùng `dependency:tree` và kiểm tra thư mục output thực tế.

### 11.2. Flat lib directory có thể đè file

Mặc định copy-dependencies có thể đặt tất cả artifacts trong một thư mục. Nếu hai artifacts có cùng output filename (do version/classifier/custom naming), plugin có thể ghi đè. Đừng tin rằng `lib/*` với nhiều phiên bản sẽ luôn xử lý đúng. Có thể dùng các tùy chọn `useRepositoryLayout` hoặc `useSubDirectoryPerArtifact` để đổi layout, nhưng khi đó manifest `Class-Path` kiểu `lib/artifact-version.jar` **không còn khớp**. Muốn đổi layout, đồng bộ cấu hình Maven Archiver `classpathLayoutType` hoặc tự tạo launcher/classpath.

### 11.3. stripVersion và fileNameMapping

Nếu bỏ version khỏi tên JAR (`commons-lang3.jar` thay vì `commons-lang3-3.17.0.jar`), manifest phải tạo **đúng cùng tên**. Việc đổi tên lib mà quên sửa manifest dẫn đến `NoClassDefFoundError` sau deploy.

Versioned filenames giúp audit dependency rõ hơn; nếu muốn tên cố định, phải có build pipeline kiểm tra mapping khi nâng version. Tránh thao tác rename sau package không cập nhật manifest.

### 11.4. excludeTransitive

`excludeTransitive=true` giúp copy ít file, nhưng rất dễ khiến bản phát hành thiếu transitive JARs. Chỉ dùng khi bạn có cơ chế khác cung cấp các thư viện đó và đã có smoke/integration test trên **distribution cuối cùng**.

### 11.5. Scope provided và container libraries

Một library `provided` có thể được application server cung cấp theo hợp đồng runtime; phân phối nó thêm vào `lib/` có nguy cơ conflict với version mà container nạp. Ngược lại, nếu chạy plain Java ngoài container, thiếu provided dependency có thể làm ứng dụng lỗi. Scope phải phản ánh **runtime architecture thật**, không chỉ mong JAR nhỏ hơn.

### 11.6. Native libraries và resource-only artifacts

Một thư viện Java có thể cần native `.dll`/` .so `, shared library, data directory, fonts hoặc executable phụ. Copy JAR đủ không đảm bảo hệ thống chạy. Kiểm tra tài liệu dependency, OS/CPU architecture, `java.library.path` và test trên môi trường deploy. Thin JAR là một **packaging strategy**, không phải bộ giải pháp tự động cho mọi native runtime dependency.

## 12. Cấu hình ứng dụng nên nằm trong JAR hay ngoài distribution?

Nhiều dự án muốn thay cấu hình khi deploy mà không rebuild. Hai lựa chọn:

### 12.1. Internal resource trong JAR

~~~text
thin-app-1.0.0.jar
  └── app-info.properties
~~~

Ứng dụng đọc qua classpath; file phù hợp cho metadata, template mặc định, static resources không nhạy cảm. Nếu muốn thay trực tiếp sau phát hành, bạn phải thay artifact hoặc thiết kế overlay.

### 12.2. External config file nằm cạnh JAR

~~~text
release/
├── thin-app-1.0.0.jar
├── lib/
│   └── ...
└── config/
    └── application.properties
~~~

Với ứng dụng tự đọc `-Dapp.config=...`:

~~~bash
java -Dapp.config=./config/application.properties -jar thin-app-1.0.0.jar
~~~

Đây là **mẫu giao diện cấu hình**; class `ThinMain` của lab không đọc `app.config`, nên lệnh không khiến lab tự nạp file. Một ứng dụng thực cần code/framework xử lý property đó. Đừng nhầm `java -cp "config:..."` (đưa directory vào classpath) với `-Dapp.config=...` (truyền path để application code tự đọc).

**Không lưu credentials thật trong JAR hay ZIP chỉ vì file cấu hình dễ vận chuyển.** Dùng secret manager/runtime injection và quyền filesystem tối thiểu. Khi ghi README, mô tả rõ biến bắt buộc, default an toàn và cách set cho từng OS.

## 13. Những lỗi thường gặp khi phát hành thin JAR

### 13.1. no main manifest attribute

~~~text
no main manifest attribute, in thin-app-1.0.0.jar
~~~

**Nguyên nhân:** manifest không có `Main-Class` phù hợp. `java -jar` cần Main-Class; việc class có `main(String[])` trong source không tự khiến JAR executable.

**Sửa:** khai `<mainClass>fully.qualified.ClassName</mainClass>` trong Maven JAR Plugin, build lại và inspect manifest.

### 13.2. NoClassDefFoundError: org/apache/commons/lang3/StringUtils

**Nguyên nhân hay gặp:** thiếu `commons-lang3` trong `lib/` hoặc manifest/classpath trỏ sai file/thư mục.

Chẩn đoán:

~~~bash
jar tf target/dist/thin-app-1.0.0.jar
jar tf target/dist/lib/commons-lang3-3.17.0.jar
java -jar target/dist/thin-app-1.0.0.jar
~~~

Kiểm tra manifest `Class-Path` trỏ `lib/commons-lang3-3.17.0.jar` và file có thật ở vị trí relative tới JAR. Nếu app JAR nằm ở `target/` nhưng lib nằm `target/dist/lib/`, chỉ đổi thư mục đứng chạy lệnh **không** giải quyết đường classpath manifest: phải stage lại layout.

### 13.3. ClassNotFoundException cho main class

Nếu dùng `java -cp`, hãy chỉ định tên lớp đầy đủ `dev.example.thin.ThinMain`, không viết `ThinMain.java` hay `dev/example/thin/ThinMain.class`. Kiểm tra `jar tf` xem package/path có đúng không. `-cp` phải chứa **app JAR** chứ không chỉ `lib/*`.

### 13.4. java -jar kết hợp -cp nhưng vẫn thiếu dependencies

`java -cp "lib/*" -jar app.jar` **không phải cách chuẩn để bổ sung classpath** cho chế độ `-jar`. Sử dụng manifest Class-Path + layout chính xác hoặc chuyển sang `java -cp "app.jar:lib/*" fully.qualified.Main`.

### 13.5. Windows dùng dấu colon trong classpath

`java -cp "app.jar:lib/*" ...` là kiểu POSIX. Trên Windows dùng `;`, ví dụ `"app.jar;lib/*"`. Nếu path có khoảng trắng, quote toàn bộ classpath argument. Với `java -jar` và manifest đúng, bạn tránh được nhiều chi tiết cú pháp shell.

### 13.6. Đưa test libraries vào distribution

Nếu copy bằng `includeScope=test` hoặc default quá rộng, `lib/` có thể chứa JUnit engine, Mockito, AssertJ và các fixtures chỉ dùng trong unit tests. Điều này tăng kích thước, bề mặt attack và nguy cơ conflict. Dùng `includeScope=runtime` rồi kiểm tra không có test dependencies.

### 13.7. Bỏ transitive libraries

Copy chỉ direct dependency trong khi classpath thực sự cần `A → B → C` dẫn tới lỗi chỉ xuất hiện khi đi vào nhánh code cụ thể. Chạy `dependency:tree -Dscope=runtime` và smoke/integration tests từ distribution ZIP.

### 13.8. Trùng version cùng package

`lib/` chứa cả hai version của một thư viện do staging cũ chưa được clean hoặc script copy đè sai. Java classpath wildcard không có thứ tự ổn định; class được tải từ JAR bất ngờ. Dùng `mvn clean package`, staging directory sạch và dependency mediation chuẩn.

### 13.9. Resource/service loader không hoạt động

Với thin JAR, mỗi dependency JAR giữ metadata `META-INF/services` và resources gốc. Tuy vậy nếu bạn vô tình đổi sang uber JAR bằng Assembly `jar-with-dependencies` hoặc Shade mà không dùng transformer thích hợp, các service declarations có thể bị ghi đè. Khi debug phải xác định **kiểu artifact đã deploy**, không chỉ thấy hậu tố `.jar`.

### 13.10. JAR signed hoặc checksum không còn hợp lệ sau chỉnh sửa

JAR của bên thứ ba có thể được ký. Giữ dependency JAR nguyên vẹn thường bảo toàn bytes/chữ ký của nó; nếu tự unpack/repakage và chỉnh manifest/resources, chữ ký có thể không còn hợp lệ. Kiểm tra chính sách ký và tính toàn vẹn artifact; tránh tự sửa binary sau build rồi phát hành.

### 13.11. UnsupportedClassVersionError

App được build `--release 17` nhưng server dùng Java 11 hoặc cũ hơn. Kiểm tra `java -version` trên chính môi trường vận hành và cách launcher chọn executable (PATH/JAVA_HOME). Không coi đây là lỗi Maven manifest/classpath.

### 13.12. ZIP giải nén mất quyền chạy

`bin/run.sh` không executable sau upload/extract hoặc trên filesystem không hỗ trợ mode. Có thể chạy `sh bin/run.sh` để kiểm tra, hoặc `chmod +x bin/run.sh` trên POSIX nếu policy cho phép. Maven Assembly Plugin hỗ trợ `fileMode` trong ZIP/TAR fileSets, nhưng tool giải nén và OS có thể xử lý permissions khác nhau. Kiểm tra **artifact đã giải nén**, không chỉ POM.

### 13.13. Classpath trỏ ra ngoài release folder

Manifest `Class-Path` dùng relative URLs; cấu hình `../lib/foo.jar` có thể gây vấn đề khi chuyển layout và khi áp quy tắc URL/security của JAR specification. Ưu tiên `lib/foo.jar` ở **thư mục con của distribution**, không phụ thuộc thư viện ở bên ngoài package đã phát hành.

### 13.14. Multi-module bị thiếu artifact của module khác

Một module `service` phụ thuộc module `api`. Khi `api` là dependency runtime, bản phân phối phải có artifact `api-...jar` tương ứng, trừ khi nó đã được cung cấp bằng cơ chế runtime khác. Maven reactor build compile được cả hai module không chứng minh `api` JAR đã được stage vào thin distribution của `service`. Kiểm tra `dependency:tree` cho **đúng module service** và thư mục lib cuối.

## 14. Quy trình phát hành kiểm chứng được trên CI

### 14.1. Build sạch

~~~bash
mvn -B -ntp clean verify
~~~

Lệnh này xử lý project lifecycle và unit tests; nếu Assembly được cấu hình ở `package`, nó cũng tạo ZIP. Dùng Maven Wrapper (`./mvnw` hoặc `mvnw.cmd`) khi repository đã có wrapper để pin Maven version.

### 14.2. Test **chính distribution**, không test từ ~/.m2

Để kiểm tra tính độc lập:

1. Lấy `target/thin-app-1.0.0-thin.zip` của Assembly hoặc zip thư mục `target/dist` sau staging.
2. Giải nén vào thư mục sạch không có source project.
3. Không thêm Maven repository (`~/.m2`) vào `CLASSPATH`.
4. Chạy `java -jar thin-app-1.0.0.jar` hoặc `bin/run.sh`.
5. Kiểm tra stdout và exit code; nếu ứng dụng có I/O/HTTP, thực hiện smoke test có kiểm soát và không gọi production dịch vụ thật.
6. Kiểm tra `lib/` chứa đúng versions, không có test-only/duplicate artifacts.

### 14.3. Lưu minh chứng phát hành

Một release có thể kèm:

- ZIP/TAR artifact đã chạy thử.
- SHA-256 checksum, chữ ký nếu yêu cầu.
- Danh sách dependencies và licenses/NOTICE theo điều kiện sử dụng.
- SBOM (ví dụ CycloneDX/SPDX) khi phù hợp quy trình.
- Báo cáo dependency vulnerability scan và chính sách cập nhật.
- Java runtime version được hỗ trợ, OS/CPU platform nếu có native dependencies.
- Hướng dẫn chạy và cấu hình ngoài JAR, không chứa secrets.
- Commit/tag, Maven/Java/toolchain/plugin versions và build settings để tái lập.

**Reproducibility:** Maven JAR/Assembly Plugins có những khả năng hỗ trợ timestamps/deterministic builds theo phiên bản; muốn hai lần build cho ra cùng hash phải kiểm tra cả ZIP entry ordering, timestamps, compression, generated metadata, signing và dependencies. Không tự khẳng định “dùng thin JAR là bit-for-bit reproducible”.

## 15. Khi thư viện ngoài cần được thay đổi riêng

Một lợi ích của thin distribution là có thể nhìn thấy từng JAR trong `lib`. Tuy nhiên thay `commons-lang3-3.17.0.jar` bằng version khác **không tự đảm bảo tương thích**. Manifest có thể tham chiếu filename chứa version cũ, dẫn tới missing library; ngay cả khi sửa tên, API/ABI có thể đổi, còn transitive dependencies có thể không còn phù hợp.

Một quy trình nâng version an toàn:

1. Sửa dependency version trong `pom.xml` (hoặc dependencyManagement/BOM).
2. Chạy `mvn dependency:tree -Dscope=runtime` để biết graph hiệu lực.
3. `mvn clean verify` chạy tests.
4. Tạo lại **cả distribution**: app JAR, manifest và `lib/`.
5. Smoke test output ZIP sau giải nén trên runtime đích.
6. Scan vulnerabilities/licenses và cập nhật SBOM/checksums.
7. Không giữ các JAR version cũ trong `lib/` vì có thể bị classpath wildcard lấy nhầm.

Nếu doanh nghiệp thật sự yêu cầu hot-swapping thư viện độc lập, kiến trúc runtime/plugin classloader và version compatibility phải được thiết kế rõ, không chỉ dựa vào việc file có thể copy.

## 16. Bài tập tự đánh giá có đáp án

**Bài 1.** `mvn package` tạo thin JAR nhưng `java -jar` báo thiếu `StringUtils`. Điều đầu tiên cần kiểm tra là gì?

**Đáp án:** application JAR có manifest `Class-Path` và file Commons Lang thật sự nằm ở vị trí relative được manifest tham chiếu không. `mvn package` thành công không chứng minh layout deploy đầy đủ.

**Bài 2.** `<addClasspath>true</addClasspath>` có tự copy thư viện vào `lib/` không?

**Đáp án:** không. Nó thêm references vào manifest; cần Dependency Plugin/Assembly/custom packaging để copy files.

**Bài 3.** Manifest `Class-Path: lib/*` có tương đương `java -cp "lib/*"` không?

**Đáp án:** không. `lib/*` là Java launcher classpath wildcard khi dùng `-cp`; manifest Class-Path chứa relative URL entries.

**Bài 4.** Với `java -cp`, dấu phân cách classpath trên Windows và POSIX khác nhau thế nào?

**Đáp án:** Windows dùng dấu `;`; Linux/macOS thường dùng dấu `:`.

**Bài 5.** Vì sao `java -jar app.jar -cp "lib/*"` không thêm các thư viện cần thiết?

**Đáp án:** sau `-jar app.jar`, `-cp` có thể chỉ là argument của chương trình, không phải launcher classpath option. Chọn manifest hoặc dùng `java -cp ... MainClass`.

**Bài 6.** `includeScope=runtime` có loại dependency `compile` không?

**Đáp án:** không. Dependency Plugin định nghĩa includeScope runtime bao gồm các dependencies compile và runtime phù hợp.

**Bài 7.** Có nên đặt JUnit 5 scope test vào `lib/` của ứng dụng không?

**Đáp án:** thông thường không; unit test framework không cần cho production CLI này, trừ khi thiết kế đặc biệt bắt buộc.

**Bài 8.** `maven-assembly-plugin` với `jar-with-dependencies` có phải layout thin không?

**Đáp án:** không. Descriptor này unpack dependencies vào một JAR; muốn thin ZIP, dùng custom `dependencySet` với `unpack=false` và `outputDirectory=/lib`.

**Bài 9.** `maven-shade-plugin` phù hợp khi nào?

**Đáp án:** khi muốn uber JAR, relocation hoặc resource transformers. Nó không phải lựa chọn mặc định cho bản phân phối JAR + lib độc lập.

**Bài 10.** Cùng một ZIP chạy trên laptop nhưng fail Java 11 server với `UnsupportedClassVersionError`. Thiếu lib sao?

**Đáp án:** không nhất thiết. App đã build Java 17, server Java 11 quá cũ; cần runtime tương thích.

**Bài 11.** Cùng `lib/` có `foo-1.0.jar` và `foo-2.0.jar` cùng class. Dùng `-cp "lib/*"` có bảo đảm chọn 2.0 không?

**Đáp án:** không. Wildcard expansion order không được đảm bảo. Sửa dependency graph và thư mục phân phối.

**Bài 12.** Khi chạy `java -jar target/thin-app-1.0.0.jar` thiếu lib, nhưng `java -jar target/dist/thin-app-1.0.0.jar` thành công. Vì sao?

**Đáp án:** manifest `Class-Path: lib/...` được giải relative tới vị trí JAR. Chỉ trong `target/dist` có thư mục `lib` đúng cạnh JAR.

**Bài 13.** ZIP có `bin/run.sh` nhưng Linux báo `Permission denied`. Cần xem gì?

**Đáp án:** permission của script sau giải nén, fileMode trong assembly descriptor và tool/OS giải nén.

**Bài 14.** Một `provided` dependency được server container cung cấp. Có nên copy thêm vào `lib/` không?

**Đáp án:** không tự động. Cần kiểm tra hợp đồng runtime/container để tránh xung đột; nếu chạy plain Java mà cần thư viện thì sửa scope/packaging đúng với môi trường thật.

**Bài 15.** Test `ThinMainTest` PASS, có đủ bằng chứng release ZIP chạy offline chưa?

**Đáp án:** chưa. Maven test runtime classpath có thể dùng dependencies từ repository. Phải giải nén và chạy **release artifact** trong môi trường sạch.

## 17. Checklist trước khi đưa thin distribution vào sản xuất

- [ ] Đã phân biệt thin JAR, uber JAR và ZIP distribution.
- [ ] Ứng dụng có `Main-Class` đúng nếu dùng `java -jar`.
- [ ] Manifest `Class-Path` chứa những JAR cần thiết, filename/path đúng với `lib/`.
- [ ] Có chính sách copy dependencies runtime/compile cùng transitive graph.
- [ ] Test dependencies không lọt vào `lib/` trừ yêu cầu đặc biệt.
- [ ] Không copy nhầm `provided` libs có thể xung đột với runtime/container.
- [ ] Không có hai phiên bản cùng class trong `lib/` ngoài chủ đích đã kiểm chứng.
- [ ] Thư mục `lib/` và application JAR được stage cùng layout.
- [ ] Không phụ thuộc `~/.m2` hoặc source repository của máy build lúc chạy.
- [ ] Đã kiểm tra `java -jar` và/hoặc `java -cp` trên OS mục tiêu.
- [ ] Đã kiểm tra classpath wildcard không dựa vào thứ tự JAR.
- [ ] Có launcher `run.sh`/`run.cmd` nếu sản phẩm cần người dùng chạy dễ dàng.
- [ ] Launcher hỗ trợ đường dẫn có khoảng trắng và không giả định shell CWD.
- [ ] Nếu dùng Assembly ZIP, descriptor giữ JAR dependencies với `unpack=false`.
- [ ] Đã mở và chạy thử **chính ZIP sau giải nén**, không chỉ target classes.
- [ ] Java runtime version trên server tương thích `--release` của project.
- [ ] Native resources/ServiceLoader/JPMS được kiểm tra khi dự án sử dụng.
- [ ] Secret không nằm trong POM/ZIP/manifest/config đã phát hành.
- [ ] Có licenses, SBOM/vulnerability scan, checksums và tài liệu release khi cần.
- [ ] CI tạo distribution từ clean build và lưu đúng artifact.
- [ ] Khi upgrade dependency, build lại app JAR + manifest + `lib/` cùng nhau.

## 18. Tài liệu tham khảo chính thức

1. [Apache Maven JAR Plugin — Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html): cấu hình archive/manifest của JAR và `addClasspath`.
2. [Maven Archiver — Set Up The Classpath](https://maven.apache.org/shared/maven-archiver/examples/classpath.html): `Main-Class`, `Class-Path`, `classpathPrefix` và layout dependency.
3. [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): `includeScope`, `excludeTransitive`, layout và artifact copying.
4. [Dependency Plugin — Copying Project Dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/copying-project-dependencies.html): cấu hình copy cả transitive dependencies ra output.
5. [Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem runtime dependency graph sau mediation.
6. [Apache Maven Assembly Plugin — Introduction](https://maven.apache.org/plugins/maven-assembly-plugin/): tạo distribution ZIP/TAR/JAR từ artifacts, dependencySets và fileSets.
7. [Assembly Plugin — Predefined Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html): phân biệt `bin` với `jar-with-dependencies`.
8. [Assembly Plugin — Descriptor Format](https://maven.apache.org/plugins/maven-assembly-plugin/assembly.html): `dependencySet`, `fileSet`, `unpack` và `fileMode`.
9. [Apache Maven Shade Plugin — Introduction](https://maven.apache.org/plugins/maven-shade-plugin/): uber JAR, relocation và transformers.
10. [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes, optional, exclusions, transitive và dependencyManagement.
11. [Oracle Java JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): `Main-Class` và `Class-Path` manifest relative URLs.
12. [Oracle Java Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-jar` vs `-cp`, wildcard classpath, platform separators.
13. [Apache Maven — Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html): sources, resources và `target`.
