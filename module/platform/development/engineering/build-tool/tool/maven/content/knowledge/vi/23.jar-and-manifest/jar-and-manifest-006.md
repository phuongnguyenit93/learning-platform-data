# Đóng gói thư viện so với đóng gói ứng dụng chạy độc lập bằng Maven JAR và manifest

## 1. Cùng là tệp JAR nhưng mục đích khác nhau

Maven thường tạo tệp `.jar` cho project có `<packaging>jar</packaging>` tại phase `package`. Tuy nhiên, một **JAR thư viện** và một **JAR ứng dụng chạy độc lập** có hợp đồng sử dụng khác nhau:

- **Library JAR:** chứa API, class và resources để một project khác khai báo làm Maven dependency. Thường không cần `public static void main(String[] args)` và không cần `Main-Class`.
- **Executable JAR:** chứa entry point có `main`, với `Main-Class` trong `META-INF/MANIFEST.MF` để lệnh `java -jar` biết bắt đầu ở đâu.
- **Thin executable JAR:** là application JAR thông thường, giữ các JAR dependency bên ngoài (ví dụ thư mục `lib/`) và cung cấp đường dẫn runtime phù hợp.
- **Fat/uber JAR:** gộp class/resource của application và những Java dependencies được chọn vào một archive, có thể chạy độc lập với các JAR dependency ngoài khi đã đóng gói đủ.

**Cảnh báo then chốt:** Có `Main-Class` không có nghĩa Java dependencies đã được gói trong JAR. Manifest đúng nhưng thiếu classpath vẫn có thể làm chương trình thất bại với `NoClassDefFoundError`.

Mục tiêu bài là phân biệt thiết kế thư viện và ứng dụng, hiểu Maven JAR Plugin, Maven Archiver, Maven Shade Plugin và Maven Dependency Plugin, rồi tự tạo hai module Java 17: một thư viện và một ứng dụng có cả bản thin lẫn bản uber-JAR.

## 2. So sánh những dạng phát hành

| Tiêu chí | JAR thư viện | Thin executable JAR + lib | Fat/uber executable JAR |
| --- | --- | --- | --- |
| Người dùng chính | Project Maven khác | Người chạy ứng dụng | Người chạy ứng dụng |
| Cần `main()` | Không | Có | Có |
| Cần `Main-Class` để chạy `java -jar` | Không | Có | Có |
| Chứa dependency classes | Thường không | Không, JAR riêng trong `lib/` | Thường có |
| Quản lý dependency | POM, transitive dependency resolution | Runtime `Class-Path`, launcher | Gộp Java classes/resources |
| Phân phối | JAR + POM trong repository | JAR + thư mục `lib/` | Một JAR và dữ liệu ngoài nếu cần |
| Dễ cập nhật từng dependency | Maven consumer quản lý | Có thể đổi JAR tương thích trong `lib/` | Thường rebuild |
| Rủi ro chính | Sai POM/transitive metadata | Mất `lib/`, sai tên/path | Trùng resources, ServiceLoader, signature |

**Cả ba vẫn là JAR dựa trên ZIP**; khác nhau ở mục tiêu, cấu trúc nội dung và cách chạy. Một thư viện có thể chứa một entry point phục vụ demo mà vẫn là thư viện; một ứng dụng có thể công bố public API. Nhưng khi thiết kế release, phải quyết định **ai là người sử dụng và họ cần những file nào**.

## 3. JAR, POM và manifest làm việc gì?

Một plain library JAR có thể chứa:

```text
greeter-lib-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/library/Greeter.class
```

Một plain application JAR:

```text
runner-app-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/app/Main.class
```

Đây là **sơ đồ tối giản**, không phải toàn bộ danh sách file mà Maven sẽ sinh. Archive thực tế có thể chứa POM metadata, license và resources khác.

### 3.1. POM quyết định artifact và dependency graph

`pom.xml` khai báo `groupId:artifactId:version`, packaging, dependencies, scopes và build plugins. Khi một consumer khai báo `greeter-lib` làm dependency, Maven đọc POM của thư viện để biết nó còn phụ thuộc `commons-lang3` như thế nào.

**Tệp JAR không thay thế hoàn toàn POM.** Một plain library JAR có thể không chứa bytecode của transitive dependencies vì Maven consumer chịu trách nhiệm resolve chúng qua POM và repositories.

### 3.2. Manifest quyết định entry point và runtime references

Một `META-INF/MANIFEST.MF` có thể chứa:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/greeter-lib-1.0.0.jar lib/commons-lang3-3.14.0.jar
```

- `Main-Class`: tên class đầy đủ theo package, **không** thêm đuôi `.java` hoặc `.class`.
- `Class-Path`: tham chiếu tới các JAR/resource khác, **không nhúng chúng vào JAR này**.
- Các vị trí tương đối trong manifest `Class-Path` được Java launcher giải quyết **theo vị trí của JAR chứa manifest**.
- Manifest thật có thể có trường khác và line wrapping, đặc biệt khi `Class-Path` dài.

Để xem danh sách entry trong archive:

```bash
jar tf target/example.jar
```

`jar tf` liệt kê tên file, không tự in nội dung manifest. Trên môi trường có `unzip`, có thể xem metadata bằng:

```bash
unzip -p target/example.jar META-INF/MANIFEST.MF
```

**Không nhầm:** Maven dependency trong POM **không tự động làm Maven JAR Plugin nhúng dependency classes** vào plain JAR. Để tạo fat JAR cần plugin/cơ chế bổ sung.

## 4. Trách nhiệm của JAR thư viện

Thư viện Java thường cần:
1. Public API có nghĩa và kiểm thử được;
2. Tài nguyên đi kèm cần thiết cho library;
3. POM công bố dependencies, version và scope chính xác;
4. Khả năng tương thích binary/API theo versioning policy;
5. Không đóng gói các thư viện bên thứ ba trùng lặp mà không có lý do rõ.

Ví dụ `greeter-lib` dùng `org.apache.commons:commons-lang3:3.14.0`. Plain library JAR thường chứa `Greeter.class` nhưng **không chứa `StringUtils.class`** từ Commons Lang. Project consumer cần compile/runtime classpath với Commons Lang; Maven giúp resolve nếu dependency được công bố đúng.

Một consumer Maven khai báo:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.0.0</version>
</dependency>
```

Khi artifact đã có trong local/remote repository cùng POM, Maven có thể mang `commons-lang3` vào dependency graph theo scope.

**Không có Main-Class không phải lỗi library.** Nếu thử `java -jar greeter-lib.jar`, Java thường báo không có main manifest attribute. Đó không phải lỗi Maven packaging; đây đơn giản là JAR không được thiết kế làm ứng dụng.

## 5. Trách nhiệm của executable JAR

Một app có class:

```java
package com.example.app;

public final class DemoMain {
    private DemoMain() {
    }

    public static void main(String[] args) {
        System.out.println("Ready");
    }
}
```

Có thể được khởi động bằng `java -jar` khi manifest ghi:

```text
Main-Class: com.example.app.DemoMain
```

Đây là **ví dụ entry point riêng**, không phải file `Main.java` của demo nhiều module phía sau.

Maven JAR Plugin dùng Maven Archiver để viết manifest:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>com.example.app.DemoMain</mainClass>
            </manifest>
        </archive>
    </configuration>
</plugin>
```

Đây là **đoạn `<plugin>`**, không phải một POM hoàn chỉnh. Nếu app không có external dependencies, `Main-Class` và classes có thể đã đủ. Nếu app gọi library khác, cần thêm runtime classpath hoặc gộp dependencies.

## 6. Thin executable JAR + lib

Một distribution có thể có layout:

```text
distribution/
├── runner-app-1.0.0.jar
└── lib/
    ├── greeter-lib-1.0.0.jar
    └── commons-lang3-3.14.0.jar
```

Trong Maven JAR Plugin:

```xml
<archive>
    <manifest>
        <mainClass>com.example.app.Main</mainClass>
        <addClasspath>true</addClasspath>
        <classpathPrefix>lib/</classpathPrefix>
    </manifest>
</archive>
```

`addClasspath=true` thêm danh sách dependencies vào manifest `Class-Path`. `classpathPrefix=lib/` cho biết các file đó nằm trong thư mục `lib` **tương đối với application JAR**. Đây **không phải** lệnh copy dependencies.

Để tạo thư mục `lib`, có thể dùng Maven Dependency Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-dependency-plugin</artifactId>
    <version>3.11.0</version>
    <executions>
        <execution>
            <id>copy-runtime-dependencies</id>
            <phase>package</phase>
            <goals>
                <goal>copy-dependencies</goal>
            </goals>
            <configuration>
                <includeScope>runtime</includeScope>
                <outputDirectory>${project.build.directory}/lib</outputDirectory>
            </configuration>
        </execution>
    </executions>
</plugin>
```

`includeScope=runtime` chọn runtime và compile dependencies theo quy tắc Dependency Plugin; `copy-dependencies` có thể copy **transitive dependencies**. Khi có classifier hoặc JARs trùng tên file, phải điều chỉnh layout/metadata để tránh đè file.

**Ưu điểm:** dễ kiểm kê/đổi từng dependency tương thích; phù hợp ZIP/TAR distribution, app có launcher script.

**Nhược điểm:** chỉ gửi thin JAR mà quên `lib/` thì không tự chạy. Manifest có thể tham chiếu tên file hợp lệ nhưng file không tồn tại ở vị trí đó.

## 7. Fat/uber JAR bằng Maven Shade Plugin

Maven Shade Plugin có goal `shade`, thường gắn ở phase `package`, nhằm hợp nhất các class/resource của application và dependencies trong một JAR.

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>build-uber-jar</id>
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
                        <mainClass>com.example.app.Main</mainClass>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Ý nghĩa:
- `ManifestResourceTransformer` đặt `Main-Class` cho shaded artifact;
- `shadedArtifactAttached=true` giữ main artifact thường và **đính kèm một artifact thứ hai** với classifier;
- `shadedClassifierName=all` dùng classifier `all`, tệp thường có tên `runner-app-1.0.0-all.jar`;
- `createDependencyReducedPom=false` tránh thay POM bằng bản reduced trong ví dụ thực hành.

Theo tài liệu Shade Plugin, nếu **không** bật `shadedArtifactAttached`, shaded JAR có thể **thay main artifact** của project. Cách đó phù hợp trong một số ứng dụng, nhưng đòi cân nhắc cẩn thận nếu project là **library**, vì consumer có thể bị duplicate classes/resources và dependency metadata không còn phản ánh cấu trúc mong muốn.

**Standalone** ở đây chỉ nghĩa là ứng dụng Java không cần những dependency JAR bên ngoài mà Shade đã gộp. Nó **không** có nghĩa JAR chứa luôn Java runtime, hệ điều hành, database, native libraries, secrets hoặc mạng.

## 8. Bài thực hành Java 17: Maven reactor có library và app

Ta tạo hai module trong một root Maven reactor:

```text
jar-modes-demo/
├── pom.xml
├── greeter-lib/
│   ├── pom.xml
│   └── src/main/java/com/example/library/Greeter.java
└── runner-app/
    ├── pom.xml
    └── src/main/java/com/example/app/Main.java
```

`greeter-lib` công bố public API và dùng Commons Lang 3. `runner-app` sử dụng library rồi tạo **thin application JAR + lib** cùng một **uber-JAR** để đối chiếu.

### 8.1. Root pom.xml: aggregator và parent

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example.training</groupId>
    <artifactId>jar-modes-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeter-lib</module>
        <module>runner-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Root có `packaging=pom` nên **không sinh root executable JAR**. `modules` khai báo reactor. Parent quản lý Java release và version build plugins. Maven sẽ dùng quan hệ phụ thuộc để build library trước app.

`pluginManagement` quản lý cấu hình/phiên bản khi plugin được sử dụng; nó không tự tạo một main method hay custom application artifact.

### 8.2. greeter-lib/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>jar-modes-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>greeter-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</project>
```

Đây là **POM thư viện hoàn chỉnh**. Library không chứa `maven-shade-plugin`, không có `Main-Class` và mặc định phụ thuộc Commons Lang với compile scope. Consumer sẽ resolve Commons Lang thông qua POM.

### 8.3. greeter-lib/src/main/java/com/example/library/Greeter.java

```java
package com.example.library;

import org.apache.commons.lang3.StringUtils;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        String normalized = StringUtils.defaultIfBlank(name, "friend").trim();
        return "Hello, " + StringUtils.capitalize(normalized) + "!";
    }
}
```

Đây là Java 17 compilable. Với tham số `"maven"`, `StringUtils.capitalize` trả `"Maven"` và `greet` trả **`Hello, Maven!`**. Library class không cần phương thức `main`.

### 8.4. runner-app/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>jar-modes-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>runner-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.training</groupId>
            <artifactId>greeter-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.app.Main</mainClass>
                            <addClasspath>true</addClasspath>
                            <classpathPrefix>lib/</classpathPrefix>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
                <executions>
                    <execution>
                        <id>copy-runtime-dependencies</id>
                        <phase>package</phase>
                        <goals>
                            <goal>copy-dependencies</goal>
                        </goals>
                        <configuration>
                            <includeScope>runtime</includeScope>
                            <outputDirectory>${project.build.directory}/lib</outputDirectory>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>build-uber-jar</id>
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
                                    <mainClass>com.example.app.Main</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM app hoàn chỉnh**. Ba plugin làm ba việc:
1. **JAR Plugin:** tạo plain `runner-app-1.0.0.jar`, ghi `Main-Class` và các dependency references `Class-Path: lib/...`.
2. **Dependency Plugin:** copy transitive runtime JARs vào `runner-app/target/lib/`.
3. **Shade Plugin:** attach thêm `runner-app-1.0.0-all.jar`, đưa app/library/third-party classes vào một file.

`ServicesResourceTransformer` giúp merge metadata `META-INF/services` khi dependency dùng Java `ServiceLoader`; demo không có service provider riêng nhưng minh họa cấu hình an toàn cho ứng dụng có SPI.

Bài thực hành **cố ý tạo cả thin và fat artifact để so sánh**. Ứng dụng production thường chọn một hình thức phân phối chính; không nhất thiết phải duy trì cả hai.

### 8.5. runner-app/src/main/java/com/example/app/Main.java

```java
package com.example.app;

import com.example.library.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("maven"));
        System.out.println("Packaging: application");
    }
}
```

Chuỗi dependency thực tế:

```text
runner-app/Main
    |
    v
greeter-lib/Greeter
    |
    v
org.apache.commons.lang3.StringUtils
```

**Stdout của chương trình khi classpath đầy đủ:**

```text
Hello, Maven!
Packaging: application
```

## 9. Build toàn reactor và kiểm tra output

Từ thư mục `jar-modes-demo` chứa root POM:

```bash
mvn -version
mvn -B -ntp clean package
```

Yêu cầu: JDK 17+ và bản Maven hỗ trợ các plugins đã chọn (ví dụ Maven 3.9.x), network/repository phù hợp nếu plugin/dependency chưa được cache. Maven biết quan hệ giữa hai modules nên không cần `mvn install` thư viện riêng trước khi build app trong **cùng reactor**.

Những output chính theo POM ví dụ:

```text
greeter-lib/target/
    greeter-lib-1.0.0.jar

runner-app/target/
    runner-app-1.0.0.jar
    runner-app-1.0.0-all.jar
    lib/
        greeter-lib-1.0.0.jar
        commons-lang3-3.14.0.jar
```

Đây là **những file quan trọng**, không phải toàn bộ nội dung `target/`. Maven còn có classes, metadata và thư mục phụ.

### 9.1. Xem library JAR

```bash
jar tf greeter-lib/target/greeter-lib-1.0.0.jar
```

Tìm `com/example/library/Greeter.class`. Không cần tìm `StringUtils.class` trong JAR thư viện, vì Commons Lang còn là Maven dependency được công bố trong library POM.

### 9.2. Xem thin application JAR

```bash
jar tf runner-app/target/runner-app-1.0.0.jar
```

Tìm `com/example/app/Main.class` và `META-INF/MANIFEST.MF`. Plain JAR này thường không chứa `Greeter.class` hay `StringUtils.class`.

Manifest được cấu hình có thể có các dòng tương tự:

```text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/greeter-lib-1.0.0.jar lib/commons-lang3-3.14.0.jar
```

Thứ tự `Class-Path` và những trường metadata bổ sung có thể khác; kiểm tra manifest của file thật. Những dependency references phải khớp JARs thật ở `runner-app/target/lib/`.

### 9.3. Xem uber-JAR

```bash
jar tf runner-app/target/runner-app-1.0.0-all.jar
```

Tìm:
- `com/example/app/Main.class`;
- `com/example/library/Greeter.class`;
- `org/apache/commons/lang3/StringUtils.class`;
- `META-INF/MANIFEST.MF`.

Một uber-JAR thường lớn hơn plain JAR, nhưng **dung lượng file không chứng minh nó chứa đủ dependencies**; phải kiểm tra entries và chạy.

## 10. Chạy thin app cùng lib/

Tại thư mục root:

```bash
java -jar runner-app/target/runner-app-1.0.0.jar
```

Nếu `target/lib` được copy đầy đủ và manifest đúng, **stdout chính xác**:

```text
Hello, Maven!
Packaging: application
```

Vì Java launcher dùng manifest `Class-Path`, lệnh không cần tự chỉ định `commons-lang3` qua `-cp`.

Nếu chỉ copy `runner-app-1.0.0.jar` sang một folder khác mà quên `lib/`, runtime có thể gặp:
- `NoClassDefFoundError: com/example/library/Greeter`, hoặc;
- `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` nếu library có nhưng thiếu dependency.

Đây là **những dạng triệu chứng**, không phải cam kết stack trace luôn giống từng chữ.

### Sai layout làm Class-Path mất hiệu lực

Ví dụ:

```text
deploy/
├── bin/runner-app-1.0.0.jar
└── lib/greeter-lib-1.0.0.jar
```

Manifest `Class-Path: lib/greeter-lib-1.0.0.jar` sẽ tìm tương đối từ `deploy/bin`, nên tìm `deploy/bin/lib`, không tự tìm `deploy/lib`. Cần đổi layout để `lib/` ở cạnh JAR, hoặc sửa prefix phù hợp, hoặc dùng script launcher chuẩn hóa đường dẫn.

**Manifest Class-Path không tự gọi Maven hoặc Internet khi chạy.** Nó chỉ tham chiếu tới những file mà JVM có thể mở.

## 11. Chạy uber-JAR và chứng minh độc lập với lib/

Tại root:

```bash
java -jar runner-app/target/runner-app-1.0.0-all.jar
```

**Stdout chính xác:**

```text
Hello, Maven!
Packaging: application
```

Để chứng minh artifact thật sự mang đủ Java dependency classes, copy **chỉ một file `all.jar`** sang directory không chứa `lib/`.

Linux/macOS:

```bash
mkdir -p /tmp/standalone-jar-check
cp runner-app/target/runner-app-1.0.0-all.jar /tmp/standalone-jar-check/
java -jar /tmp/standalone-jar-check/runner-app-1.0.0-all.jar
```

Windows PowerShell:

```powershell
$dest = Join-Path $HOME "standalone-jar-check"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item "runner-app/target/runner-app-1.0.0-all.jar" $dest
java -jar (Join-Path $dest "runner-app-1.0.0-all.jar")
```

Nếu chạy thành công với một JAR trong folder mới, demo chứng minh bản Shade không phụ thuộc thư mục `lib` bên ngoài. Điều này **không chứng minh ứng dụng thực tế độc lập khỏi native libraries, database, config, secret manager hay network**.

### java -cp không giống java -jar

Nếu muốn chạy class có main mà không dùng manifest, có thể cung cấp classpath trực tiếp:

```bash
java -cp "runner-app/target/classes:greeter-lib/target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" com.example.app.Main
```

Đây là lệnh **Linux/macOS**, giả định default Maven local repository. Trên Windows, classpath thường dùng `;` thay `:`. Nếu Maven dùng `-Dmaven.repo.local` hoặc repository khác, phải chỉnh đường dẫn.

Phân biệt:
- `java -cp ... com.example.app.Main`: chỉ định classpath và main class ở CLI.
- `java -jar runner-app.jar`: lấy `Main-Class` và manifest classpath của JAR.
- Đừng dựa vào `-cp` đặt cạnh `-jar` để bổ sung dependency khi Java launcher đang chạy theo mode `-jar`.

## 12. Shade không chỉ là zip nhiều JAR

Khi unpack nhiều dependency JAR vào một archive, có thể phát sinh xung đột.

### 12.1. Trùng tên resource

Hai dependencies có thể cùng chứa `META-INF/services/com.example.Service`, `META-INF/spring/...` hay `config.properties`. Một fat JAR có thể không tự giữ nguyên semantics của classloader từng JAR riêng biệt.

Shade có **resource transformers**, chẳng hạn `ServicesResourceTransformer` merge service provider lists và xử lý relocation khi phù hợp. POM demo đã khai báo:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>com.example.app.Main</mainClass>
    </transformer>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
```

**Không phải mọi resource đều được merge tự động.** Với framework/DI/logging khác, cần xem tài liệu và test riêng.

### 12.2. Chữ ký JAR

Một số JAR dependency có signature metadata như `META-INF/*.SF`, `*.RSA`, `*.DSA`. Khi Shade sửa archive, chữ ký cũ có thể không còn hợp lệ. Trong trường hợp phù hợp, Shade filters có thể loại metadata chữ ký cũ:

```xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.RSA</exclude>
            <exclude>META-INF/*.DSA</exclude>
        </excludes>
    </filter>
</filters>
```

Đây là **đoạn cấu hình nâng cao**, không thêm vào mọi POM theo phản xạ. Loại signature metadata cũ **không thay thế** kiểm tra nguồn dependencies, chính sách ký artifact hoặc supply-chain verification.

### 12.3. Relocation

Shade có thể đổi package namespace của dependencies bằng `relocations`, hữu ích khi tránh xung đột nhưng dễ ảnh hưởng:
- Reflection và tên class dưới dạng chuỗi;
- `ServiceLoader` và resource tên provider;
- Serialization, DI, config;
- Native bindings;
- `module-info.class` và Java module system.

Ví dụ app này **không cần relocation**. Chỉ dùng khi có lý do cụ thể, test chứng minh được sự tương thích.

### 12.4. minimizeJar

`minimizeJar` có thể giảm kích thước uber-JAR bằng cách bỏ những classes được đánh giá không dùng. Nhưng classes chỉ được load qua reflection/DI/SPI có thể không thấy qua static analysis. Bật minimize mà không có integration tests có thể làm runtime fail dù build thành công.

Demo giữ mức mặc định, không minimize.

## 13. Maven Assembly Plugin và phương án khác

Maven Assembly Plugin có descriptor `jar-with-dependencies`, tạo một JAR chứa project classes và dependencies đã unpack. Theo tài liệu Apache Maven, cơ chế này có **hỗ trợ uber-JAR cơ bản**; khi cần merge resources hoặc relocation có kiểm soát, Shade Plugin thường là lựa chọn tốt hơn.

Cấu hình **thay thế**, không thêm đồng thời với Shade trong demo trừ khi chủ động muốn build một variant khác:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.7.1</version>
    <configuration>
        <descriptorRefs>
            <descriptorRef>jar-with-dependencies</descriptorRef>
        </descriptorRefs>
        <archive>
            <manifest>
                <mainClass>com.example.app.Main</mainClass>
            </manifest>
        </archive>
    </configuration>
    <executions>
        <execution>
            <id>make-assembly</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Các hệ sinh thái có lựa chọn riêng:
- **Spring Boot Maven Plugin `repackage`:** tạo executable JAR theo layout/launcher Spring Boot (thường có `BOOT-INF/lib`), không giống Shade unpack classes; dùng plugin framework theo tài liệu.
- **Maven JLink Plugin:** hỗ trợ Java runtime image với ứng dụng modular, khác việc gộp JAR.
- **Container image:** có thể đóng JRE, JAR, config và runtime services phù hợp; đây là distribution cao hơn mức Maven JAR.
- **ZIP/TAR distribution:** chứa thin JAR, `lib/`, launcher và config ngoài; thường dễ quản lý khi cần nhiều file.

Chọn phương án theo mục đích consumer/triển khai, đừng chọn chỉ vì tên “fat jar”.

## 14. Dependency scopes ảnh hưởng distribution

Maven có các scope phổ biến:
- `compile`: mặc định, cần compile và runtime.
- `runtime`: cần runtime, không nhất thiết biên dịch trực tiếp.
- `provided`: cần compile nhưng runtime/container được kỳ vọng cung cấp.
- `test`: chỉ cần cho test, không thuộc runtime distribution thông thường.
- `optional`: ảnh hưởng cách dependency được mang transitively sang Maven consumer.

Trong demo, `greeter-lib` phụ thuộc `commons-lang3` compile; `runner-app` phụ thuộc `greeter-lib` compile; `copy-dependencies` với `includeScope=runtime` có thể lấy cả hai.

**Không đổi Commons Lang thành `provided` chỉ để thu nhỏ JAR nếu runtime không cung cấp nó**. Build có thể compile thành công nhưng ứng dụng sẽ thiếu `StringUtils` khi chạy.

Tương tự, không nhúng JUnit/test dependencies vào application uber-JAR theo mặc định nếu sản phẩm không dùng chúng ở runtime. Nếu library công bố public API có types của dependency khác, cần review scope/optional thật kỹ để consumer vẫn compile được.

## 15. Phát hành thư viện và phát hành ứng dụng là hai quy trình khác nhau

### Library

Quy trình thường gồm:
1. Chạy tests và `mvn package`.
2. Dùng `mvn install` để đưa JAR/POM vào local repository khi muốn thử từ project khác.
3. Dùng `mvn deploy` cùng `distributionManagement` và credentials đúng để publish remote.
4. Consumer khai báo Maven dependency và resolve transitive graph.
5. Khi cần, publish thêm source JAR, Javadoc JAR và metadata/signatures theo quy định.

**Chỉ gửi plain JAR mà không có POM** có thể làm consumer không biết những dependencies cần thiết.

### Application

Người vận hành thường cần **một bộ file để start**:
- Thin JAR + thư mục `lib/`;
- Uber-JAR;
- ZIP/TAR;
- Container image.

Ở POM demo, `shadedArtifactAttached=true` giữ **main artifact** là thin JAR và thêm `classifier=all` cho executable uber-JAR. Nếu chạy `mvn install`, cả main artifact và attached classifier có thể được cài local cùng POM, không có nghĩa chúng đã được deploy.

**Không nên dùng ứng dụng uber-JAR như thư viện dependency cho nhiều project** nếu không có lý do kỹ thuật, vì classes/resources bên thứ ba có thể bị copy đè hoặc xung đột.

### Dependency-reduced POM

Shade Plugin có `createDependencyReducedPom`. Khi shaded JAR thay main artifact, việc giảm dependencies công bố trong POM có thể hữu ích, nhưng cũng ảnh hưởng consumers. Demo đặt `false` và attach classifier riêng để tránh thay Maven metadata ngoài mục đích bài học. Không áp dụng một cấu hình duy nhất cho mọi release.

## 16. Packaging lifecycle và thứ tự các goals

Với packaging `jar`, các mốc quan trọng:

```text
process-resources -> resources:resources
compile           -> compiler:compile
test-compile      -> compiler:testCompile
test              -> surefire:test
package           -> jar:jar (binding mặc định)
                  -> dependency:copy-dependencies (runner-app)
                  -> shade:shade (runner-app)
verify            -> các goal verify khác nếu cấu hình
install           -> cài artifacts vào local repository
deploy            -> publish remote khi có cấu hình
```

Đây là **mô hình của demo**, không phải bảng exhaustive cho tất cả dự án. Root có `packaging=pom` không sinh JAR; library dùng plain `jar:jar`; app vừa có plain JAR vừa thêm hai plugin executions tại phase `package`.

**Không bind thêm một execution `jar:jar` lần hai chỉ để thêm manifest.** Với packaging `jar`, goal đã được lifecycle gọi. Thường chỉ cần cấu hình `maven-jar-plugin` cho binding có sẵn.

Maven reactor dùng quan hệ module/dependency để build `greeter-lib` trước `runner-app`, nên một lượt `mvn clean package` từ root đủ cho demo mà không cần install trước.

## 17. Đối chiếu manifest, dependency tree và file thật

Thực hiện:

```bash
mvn -B -ntp clean package
jar tf greeter-lib/target/greeter-lib-1.0.0.jar
jar tf runner-app/target/runner-app-1.0.0.jar
jar tf runner-app/target/runner-app-1.0.0-all.jar
java -jar runner-app/target/runner-app-1.0.0.jar
java -jar runner-app/target/runner-app-1.0.0-all.jar
```

Kiểm tra:
1. Plain library JAR có `Greeter.class`, không chứa Commons Lang classes.
2. Thin app JAR có `Main.class` và `Main-Class`/`Class-Path` phù hợp, thư mục `lib` tồn tại.
3. Uber-JAR có `Main.class`, `Greeter.class`, `StringUtils.class`.
4. Hai lượt chạy in cùng hai dòng đã mô tả.
5. Uber-JAR chạy được sau khi di chuyển **một mình** sang thư mục không có `lib`.

Để xem dependency tree:

```bash
mvn -B -ntp -pl runner-app -am org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Phần graph cần thấy về bản chất:

```text
runner-app:jar:1.0.0
\- greeter-lib:jar:1.0.0:compile
   \- commons-lang3:jar:3.14.0:compile
```

Đây là **sơ đồ rút gọn**, không phải raw log có đủ groupIds và parent. **Dependency tree cho biết Maven resolve những gì, không chứng minh Shade/Archiver đã gói file nào.** Kết luận packaging phải dựa trên cả `jar tf`/manifest và runtime test.

## 18. Rủi ro phát hành và tính tái lập

- **Ghim plugin versions** trong POM/parent để CI và máy developer không chọn build behavior khác nhau một cách vô tình.
- **Java release target:** ví dụ dùng `maven.compiler.release=17`, nên runtime phải hỗ trợ classfile Java 17 (major version 61). Maven chạy trên JDK khác không tự sửa runtime target.
- **Reproducible archives:** có thể dùng `project.build.outputTimestamp` cùng plugin versions tương thích; hạn chế resource chứa timestamp/path máy không kiểm soát.
- **Licenses/NOTICE:** khi gộp third-party JAR bằng Shade, cần tuân thủ điều khoản license/NOTICE, không mặc định xóa metadata có nghĩa pháp lý.
- **Supply chain:** kiểm tra nguồn dependency, checksums/signatures, vulnerabilities theo quy trình; Shade không làm dependency tự an toàn hơn.
- **ServiceLoader/DI:** test những đường code dùng reflection hoặc dynamic providers trên uber-JAR cuối, không chỉ unit tests trên Maven classpath.
- **Native libraries:** một JAR có tất cả Java classes vẫn có thể phụ thuộc hệ điều hành và native binaries không được Shade tự động xử lý.
- **Version metadata:** phát hành cùng coordinates nhưng nội dung khác giữa các lượt build phá tính tái lập; quản lý release version và artifact retention rõ.

Một property minh họa cho reproducible archive ở Maven plugins hỗ trợ:

```xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Đây là **đoạn cấu hình tùy chọn**, không phải POM độc lập. Trong thực tế lấy giá trị ổn định theo release/CI policy; không hard-code timestamp cũ mà không có lý do.

## 19. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách sửa |
| --- | --- | --- |
| Library JAR không chạy bằng `java -jar` | Không có `Main-Class`, không có `main` | Bình thường; đây là library |
| `no main manifest attribute` trên app JAR | Thiếu `Main-Class` | Cấu hình Jar Plugin hoặc Shade transformer |
| App có Main.class nhưng báo sai main class | FQCN trong manifest sai | Kiểm tra package và `jar tf` |
| `NoClassDefFoundError: Greeter` | Thin app thiếu greeter-lib JAR | Copy đủ `lib`, sửa `Class-Path` |
| `NoClassDefFoundError: StringUtils` | Thiếu transitive Commons Lang JAR | Copy runtime dependencies hoặc Shade |
| Có `Class-Path` nhưng vẫn thiếu lớp | Filename, relative path hoặc layout distribution sai | Đặt lib đúng nơi, kiểm tra manifest |
| App chạy được trong IDE nhưng lỗi khi phát hành | IDE cấp classpath hộ, distribution thiếu JAR | Test artifact thực bằng `java -jar` |
| `target/lib` trống | copy-dependencies chưa chạy, scope/filter sai | Xem package execution và dependency tree |
| Không có `-all.jar` | Shade chưa bind, cấu hình classifier sai | Xem build log, effective POM |
| `all.jar` vẫn thiếu lớp | Exclude/filter, scope hoặc dependency chưa được resolve | Dùng `jar tf`, dependency tree |
| Service provider biến mất | `META-INF/services` merge chưa đúng | Kiểm tra ServicesResourceTransformer |
| Lỗi JAR signature khi shade | Metadata chữ ký cũ không hợp lệ | Xem filters, signing policy |
| Reflection lỗi sau shading | Relocation/minimize loại hoặc đổi class động | Test integration, giảm filter |
| App module riêng không build được | Library chưa có trong repository nếu không chạy reactor | Build root reactor hoặc install library |
| `invalid target release: 17` | Compiler đang dùng JDK quá cũ | Kiểm tra Maven JVM/toolchain/release |
| Spring Boot app shaded không khởi động đúng | Spring Boot layout/launcher riêng | Dùng Spring Boot Maven Plugin repackage |
| JAR chứa classes nhưng native library vẫn thiếu | Shade không tự bundle OS native dependencies | Phân phối native artifact riêng |
| Application và library đóng gói trùng classes | Consume uber-JAR như library | Dùng main library JAR/POM thay classifier all |
| Hai build cùng version khác bytes | Timestamp/encoding/plugins/resources khác nhau | Chốt versions và reproducible settings |

### Quy trình điều tra theo thứ tự

1. Xác định artifact muốn kiểm là library, thin executable hay uber executable.
2. Xác nhận `mvn -version`, JDK và build từ đúng root reactor.
3. Chạy `mvn clean package`, kiểm tra Maven exit code.
4. Liệt kê các JAR trong target của từng module.
5. Dùng `jar tf` xem classes và resources thật.
6. Đọc manifest của đúng JAR: `Main-Class`, `Class-Path`.
7. Với thin app, đối chiếu từng manifest entry với file trong `lib/`.
8. Với uber app, xác minh dependency classes nằm ngay trong JAR.
9. Thực thi cả hai dạng và so stdout.
10. Copy uber-JAR sang folder không có lib để kiểm tra tính độc lập.
11. Nếu lỗi, tra dependency tree, scope, Shade filters/transformers và runtime stack trace.
12. Trước khi publish, rà soát licenses, signature metadata, vulnerabilities và reproducibility.

## 20. Bài tập tự kiểm tra

1. Vì sao thư viện Java không nhất thiết cần `Main-Class`?
2. Trong ví dụ, plain JAR của greeter-lib có chứa `StringUtils.class` không? Vì sao Maven consumer vẫn dùng được?
3. `Main-Class` và `Class-Path` trong manifest khác nhau như thế nào?
4. Tại sao chỉ copy thin app JAR mà không copy `lib/` có thể gây lỗi?
5. `copy-dependencies` có tác dụng gì khác `addClasspath=true`?
6. Cấu hình `shadedArtifactAttached=true` và `shadedClassifierName=all` tạo ra artifact gì?
7. Tại sao nên thử chạy uber-JAR sau khi chuyển nó sang folder không chứa `lib`?
8. Vì sao Shade Plugin có ServicesResourceTransformer?
9. Khi nào relocation/minimizeJar có thể làm ứng dụng fail?
10. Nếu consumer cần API Greeter, nên phụ thuộc `greeter-lib` hay `runner-app-all`?
11. `mvn install` khác `mvn deploy` thế nào?
12. Vì sao Spring Boot executable JAR không mặc nhiên tương đương một Shade uber-JAR?
13. Nếu JAR được biên dịch target Java 17, runtime Java 11 có thể chạy không?
14. Những bằng chứng nào cần có trước khi gọi một artifact là “standalone”?

## 21. Checklist khi phát hành

- [ ] Xác định rõ artifact là library hay application.
- [ ] Với library, POM công bố đúng dependencies/scope; JAR chứa API/resource cần thiết.
- [ ] Với executable, `Main-Class` trùng fully qualified name có `main` hợp lệ.
- [ ] Với thin app, `Class-Path` và thư mục `lib` khớp đường dẫn.
- [ ] Đã copy đủ transitive runtime dependencies.
- [ ] Với Shade, biết main artifact và attached classifier `all` khác nhau.
- [ ] Uber-JAR chạy được khi copy riêng nó tới folder không chứa `lib`.
- [ ] Đã kiểm tra ServiceLoader/resources trùng nếu có.
- [ ] Không bật relocation/minimizeJar vô căn cứ.
- [ ] Không nhúng dependencies của test hoặc làm mất required runtime dependencies vì scope.
- [ ] JDK runtime đáp ứng `maven.compiler.release`.
- [ ] Plugin versions được ghim và build reproducibility được cân nhắc.
- [ ] Đã xem manifest, `jar tf`, dependency tree và chạy artifact thực tế.
- [ ] Phân phối đúng bộ file cho người dùng: JAR+POM, thin JAR+lib, uber-JAR hoặc container.

**Kết luận:** Library JAR phục vụ **Maven consumers và dependency graph**; executable JAR phục vụ **người chạy chương trình**. `Main-Class` là điểm bắt đầu, **không phải cơ chế mang theo dependencies**. Maven JAR Plugin/Maven Archiver ghi manifest, Maven Dependency Plugin tạo thư mục `lib/` cho thin app, còn Maven Shade Plugin có thể tạo uber-JAR chứa Java dependency classes. Muốn khẳng định đóng gói đúng, phải kiểm tra archive thật và chạy ứng dụng ở môi trường không phụ thuộc vô tình vào IDE hoặc cache.

## Tài liệu Apache Maven chính thức

- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/)
- [Maven Archiver — Classpath and Main-Class](https://maven.apache.org/shared/maven-archiver/examples/classpath.html)
- [Maven Dependency Plugin — Copying Project Dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/copying-project-dependencies.html)
- [Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html)
- [Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
- [Maven Shade Plugin — Attached Shaded Artifact](https://maven.apache.org/plugins/maven-shade-plugin/examples/attached-artifact.html)
- [Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html)
- [Maven Shade Plugin — shade:shade](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html)
- [Maven Assembly Plugin — Predefined Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html)