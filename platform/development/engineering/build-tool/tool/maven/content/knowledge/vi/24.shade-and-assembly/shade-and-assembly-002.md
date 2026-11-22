# Uber JAR và trường hợp cần gộp phụ thuộc vào một artifact trong Maven

## 1. Uber JAR giải quyết vấn đề gì?

Khi một ứng dụng Java dùng thư viện bên ngoài, Maven thường tạo **JAR chính của dự án** nhưng không tự nhúng tất cả JAR phụ thuộc vào bên trong nó. Nếu chuyển mỗi file `target/app-1.0.0.jar` sang một máy khác rồi chạy, ứng dụng có thể không tìm được class của thư viện và gặp `NoClassDefFoundError` hoặc `ClassNotFoundException`.

**Uber JAR** (thường gọi là **fat JAR**) là một JAR phân phối chứa **class/resource của ứng dụng và những class/resource của các dependency được chọn**, để người dùng không phải tự đặt từng thư viện lên runtime classpath. Khi archive còn có `Main-Class` trong manifest, ta có thể chạy:

~~~bash
java -jar target/uber-demo-1.0.0.jar
~~~

Trong bài này, “một artifact” nghĩa là một **gói JAR phân phối**, không có nghĩa chỉ còn một Java process hay JDK. Máy đích vẫn phải có Java runtime phù hợp; native libraries, dữ liệu ngoài, cấu hình, certificates và services mạng **không tự biến mất**.

**Điểm quan trọng:** “đóng gói thành một file JAR” và “có thể chạy bằng `java -jar`” là **hai tính chất khác nhau**. Gộp dependencies giúp giải quyết classpath; một manifest `Main-Class` hợp lệ giúp Java launcher xác định điểm vào. Có thể có Uber JAR không chạy trực tiếp, và có thin JAR có `Main-Class` nhưng vẫn thiếu dependencies lúc chạy.

## 2. Thin JAR, Uber JAR, shaded JAR và distribution ZIP

| Hình thức | Nội dung | Cách chạy/phân phối điển hình |
| --- | --- | --- |
| **Thin JAR** | Class/resource của module hiện tại | `java -cp 'app.jar:lib/*' com.example.Main` trên POSIX; cần các JAR ngoài |
| **Uber/Fat JAR** | Class/resource của module + dependency được bung/gộp | `java -jar app-all.jar` nếu có manifest phù hợp |
| **Shaded JAR** | Uber JAR do Shade Plugin tạo, có thể **relocate** package names | Phân phối executable hoặc artifact phụ; cần test tương thích |
| **Assembly JAR** | JAR do Assembly Plugin gộp, ví dụ `jar-with-dependencies` | Giải pháp basic khi không cần resource transformations phức tạp |
| **Distribution ZIP/TAR** | JAR chính + thư mục `lib/`, scripts, configs, license docs | Hữu ích khi muốn tách/đổi từng dependency |
| **Spring Boot executable JAR** | Thường chứa nested dependencies dưới `BOOT-INF/lib` và launcher đặc thù | Không đồng nghĩa JAR Shade kiểu flat/unpacked |
| **Container image** | Có thể chứa JAR, JRE, cấu hình entrypoint, OS layers | Thuận tiện cho server/CI nhưng không bắt buộc là Uber JAR |

**Thin JAR** và **Uber JAR** đều là những JAR ZIP archives bình thường; khác biệt nằm ở **những entries thực sự có bên trong** và cách runtime load classes.

Ví dụ thin JAR:

~~~text
app-1.0.0.jar
  META-INF/MANIFEST.MF
  com/example/app/Main.class
  config/app.properties
~~~

Ví dụ Uber JAR:

~~~text
app-1.0.0.jar
  META-INF/MANIFEST.MF
  com/example/app/Main.class
  config/app.properties
  org/apache/commons/lang3/StringUtils.class
  org/apache/commons/lang3/... (nhiều class khác)
  META-INF/services/... (nếu có và đã gộp đúng)
~~~

Một **JAR chứa các JAR khác như các file `lib/foo.jar`** không tự khiến Java class loader chuẩn tìm được class trong nested JAR. Một số framework dùng launcher riêng để xử lý nested archives. Shade và Assembly `jar-with-dependencies` thường **bung contents của dependency JAR** vào một JAR phẳng, chứ không đơn giản copy nguyên từng JAR vào thư mục `lib` bên trong.

## 3. Trường hợp nào thực sự cần Uber JAR?

### 3.1. Các trường hợp phù hợp

1. **CLI Java** cần gửi cho người dùng một file dễ tải và chạy.
2. **Batch job** hoặc scheduled task chạy trên server có JDK/JRE nhưng không muốn vận chuyển cả bộ `lib/`.
3. **Tool nội bộ** chạy trong CI runner, nơi artifact được lưu ở registry rồi tải vào workspace.
4. **Ứng dụng nhỏ** muốn giảm lỗi quên copy dependency khi bàn giao.
5. **Hệ thống cần executable độc lập ở mức Java classpath**, nhưng môi trường vẫn quản lý Java runtime và external services riêng.
6. **Plugin hoặc công cụ chạy trong JVM của host có classpath phức tạp**, khi cần relocation để tránh đụng phiên bản dependency; trường hợp này phải rất cẩn thận với API boundary.

Lợi ích chính: đơn giản hóa việc **phân phối và khởi chạy**. Một file có thể được đưa vào artifact repository, gắn checksum và dùng lại trong CI/CD. Không phải chỉnh thủ công `-cp` theo số lượng dependency ngày càng tăng.

### 3.2. Những trường hợp thường không nên mặc định dùng

- **Thư viện Java dùng làm Maven dependency cho project khác**: thông thường publish thin JAR + POM dependency metadata; gộp toàn bộ thư viện có thể làm classpath của consumer phình to và xung đột.
- **Ứng dụng chạy dưới application server hoặc servlet container**: thường theo packaging WAR/đặc thù runtime, không lấy Uber JAR làm mặc định.
- **Dự án dùng Java Platform Module System (JPMS) chặt chẽ**: gộp modules có thể làm hỏng module descriptors/identities.
- **OSGi, Java agents, JNI/native libraries, signed JARs**: cần hiểu quy tắc load và metadata đặc thù; một JAR phẳng không giải quyết mọi thứ.
- **Ứng dụng lớn có nhiều dependencies thay đổi độc lập**: distribution với `lib/` hoặc container layers có thể tối ưu cache/cập nhật tốt hơn.
- **Framework đã có executable packaging riêng** (ví dụ Spring Boot repackage): không nhất thiết chạy Shade thêm lên output đó.
- **Plugin của Maven chạy trong host Maven**: đóng gói tất cả dependencies có thể phá component discovery; chỉ shade những phần cần tránh xung đột theo hướng dẫn plugin.

**Uber JAR là một lựa chọn deployment architecture, không phải tiêu chuẩn bắt buộc của Maven.**

## 4. Từ dependency graph tới nội dung một Uber JAR

Maven phân giải dependencies theo GAV, type/classifier, scope, exclusions và dependency management. Ví dụ:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

Với packaging `jar`, phase `package` mặc định dùng `maven-jar-plugin:jar` để đóng gói class/resource **của module**. JAR thông thường **không tự nhúng** `commons-lang3`.

Khi có Maven Shade Plugin:

~~~text
src/main/java + src/main/resources
            |
            v
compiler:compile + resources:resources
            |
            v
jar:jar -> thin JAR của ứng dụng
            |
            v
shade:shade -> chọn runtime dependencies
            |       |
            |       +-- mở nội dung các JAR được chọn
            |       +-- xử lý trùng đường dẫn resource
            |       +-- có thể relocate class packages
            |       +-- có thể lọc hoặc minimize
            |       +-- tạo/điều chỉnh manifest
            v
final Uber JAR -> java -jar
~~~

Shade goal thường được bind tại phase `package` trong POM. Với project `jar`, Maven xử lý goal mặc định tạo JAR trước goal shade bổ sung ở phase đó. **Không cần thêm một execution khác của `jar:jar`** chỉ để tạo input cho shade, vì việc đó có thể tạo hai main artifact invocations.

### Dependency scopes và nội dung

Thông thường Shade giải quyết dependencies theo runtime dependency graph: các library `compile` và `runtime` có thể được gộp. `test` dependencies chỉ phục vụ kiểm thử và không được nhét vào output runtime mặc định; `provided` thường là những dependency được runtime/container cung cấp, không mặc định nhúng.

Tuy nhiên việc class nào/file nào nằm trong JAR cuối còn phụ thuộc **Shade `artifactSet`, `filters`, exclusions, optional dependencies, relocations và minimization**. Không nên kết luận chỉ bằng scope hoặc chỉ bằng `mvn dependency:tree`; cần kiểm tra **file JAR thực tế**.

Một số dependencies là **POM-only/BOM** chứ không có binary JAR để giải nén. Annotation processors và Maven plugin dependencies cũng không tự là runtime dependencies của ứng dụng.

## 5. Hai plugin chính: Maven Shade và Maven Assembly

| Tiêu chí | **Maven Shade Plugin** | **Maven Assembly Plugin** |
| --- | --- | --- |
| Goal điển hình | `shade:shade` | `assembly:single` |
| Gộp dependency JAR | Có | Có với `jar-with-dependencies` |
| Relocate package/class names | Có | Không phải chức năng chính của descriptor `jar-with-dependencies` |
| Merge `META-INF/services` có chủ đích | `ServicesResourceTransformer` | Descriptor basic không có cùng cơ chế transformer |
| Merge manifest/NOTICE/resources | Các resource transformers | Có cơ chế assembly/archiver riêng; không tương đương tất cả transformers |
| Minimize classes | `minimizeJar` (cần test kỹ) | Không phải tính năng chính của `jar-with-dependencies` |
| Publication output | Có thể thay main artifact hoặc attach classifier | Thường tạo classifier `jar-with-dependencies` |
| Distribution zip/tar với scripts | Không phải mục tiêu chính | Rất phù hợp qua assembly descriptors |
| Độ phức tạp | Nhiều cấu hình cho Uber JAR phức tạp | Dễ cho gói basic, ZIP/TAR distribution |

Theo tài liệu chính thức, **Assembly `jar-with-dependencies` chỉ hỗ trợ Uber JAR ở mức cơ bản**. Nếu cần xử lý resource trùng, service provider metadata hoặc relocation, thường dùng **Shade Plugin**. Nếu cần cả một bản phân phối gồm thư mục `bin/`, `lib/`, README và config, **Assembly descriptors** thường phù hợp hơn một Uber JAR duy nhất.

Không nên bật cả Shade và Assembly cùng tạo một artifact “chính” ở phase package mà không có thiết kế rõ: dễ có hai đầu ra giống nhau, trùng classes hoặc vấn đề attachment.

## 6. Maven Shade Plugin: cấu hình tối thiểu để chạy được

Dưới `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>make-executable-jar</id>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.example.uber.Main</mainClass>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh plugin**, không phải POM độc lập. Đặt đúng `groupId`, `artifactId`, `version`, và bảo đảm class `com.example.uber.Main` thật sự có:

~~~java
public static void main(String[] args)
~~~

`ManifestResourceTransformer` đặt entry `Main-Class` trong `META-INF/MANIFEST.MF`; lệnh `java -jar` dùng entry đó để tìm entrypoint.

Cấu hình này **không tự tạo `.exe` native** và không đóng gói JDK. Output vẫn là JAR, dùng `java -jar`.

Shade **3.6.2** là phiên bản tài liệu Apache Maven được đối chiếu cho ví dụ; nếu tổ chức đang pin một version khác, kiểm tra compatibility và thay đổi tham số trước khi nâng.

## 7. Project Java 17 hoàn chỉnh: xây một Uber JAR và chạy

Bài thực hành chọn **Commons Lang 3.17.0** làm thư viện runtime. Đó là một phiên bản cụ thể để ví dụ ổn định, không phải khẳng định đây là release mới nhất ở mọi thời điểm. Ta dùng `StringUtils` để chứng minh JAR cuối thực sự chứa class từ dependency.

Yêu cầu: **JDK 17+**, Maven **3.9+**, repository tải được plugins và dependencies. Ví dụ không gọi network ở runtime.

### 7.1. Cấu trúc thư mục

~~~text
uber-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/uber/Main.java
    │   └── resources/demo/banner.txt
    └── test/
        └── java/com/example/uber/MainTest.java
~~~

Mục tiêu:

- Biên dịch `Main.java` dùng một class thuộc Commons Lang.
- Gói resource `demo/banner.txt`.
- Chạy JUnit test ở phase `test`.
- Shade ở phase `package` để đưa runtime dependency vào final JAR.
- Thiết lập `Main-Class`.
- Chạy executable bằng **một lệnh `java -jar`**.

### 7.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>uber-demo</artifactId>
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
            <version>3.17.0</version>
        </dependency>

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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>

                <executions>
                    <execution>
                        <id>make-uber-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>

                        <configuration>
                            <shadedArtifactAttached>false</shadedArtifactAttached>
                            <createDependencyReducedPom>true</createDependencyReducedPom>
                            <minimizeJar>false</minimizeJar>

                            <filters>
                                <filter>
                                    <artifact>*:*</artifact>
                                    <excludes>
                                        <exclude>META-INF/*.SF</exclude>
                                        <exclude>META-INF/*.DSA</exclude>
                                        <exclude>META-INF/*.RSA</exclude>
                                    </excludes>
                                </filter>
                            </filters>

                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>com.example.uber.Main</mainClass>
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
~~~

Đây là **POM đầy đủ**. Những dòng đáng chú ý:

1. `packaging=jar` kích hoạt default lifecycle binding tạo JAR của module trước Shade.
2. `commons-lang3` không có scope tường minh, mặc định là `compile`; nó có mặt trên runtime graph.
3. `junit-jupiter` là test dependency, dùng bởi Surefire, **không phải library cần đi theo executable runtime**.
4. `maven-shade-plugin` bind goal `shade` vào `package`.
5. `shadedArtifactAttached=false` để shaded JAR trở thành **main artifact** của project. Đây cũng là giá trị mặc định, được viết rõ để học dễ hơn.
6. `createDependencyReducedPom=true` giữ hành vi tạo POM rút gọn khi gộp dependencies; xem chi tiết ở phần publication.
7. `minimizeJar=false` giữ các class dependencies được chọn; ví dụ không dùng minimization để tránh kết luận nhầm khi runtime dùng reflection.
8. `ManifestResourceTransformer` tạo `Main-Class`.
9. `ServicesResourceTransformer` hỗ trợ merge `META-INF/services` nếu dependencies có service provider metadata.
10. `filters` loại các signature sidecar entries `.SF`, `.DSA`, `.RSA` **bên trong JAR đã ký** để tránh metadata signature gốc không còn hợp lệ sau khi gộp; đây **không phải tái ký** JAR cuối.
11. Không có execution mới của `jar:jar`: Maven đã cung cấp một lần gọi theo `jar` packaging.
12. Các plugin versions được pin để giảm thay đổi ngoài ý muốn.

**Lưu ý về chữ ký:** ví dụ loại metadata chữ ký gốc bởi bytes final JAR đã đổi; không có nghĩa artifact tự trở thành trusted. Nếu tổ chức cần signed releases, phải ký/phát hành JAR cuối theo quy trình đáng tin và giữ license/NOTICE đúng nghĩa vụ.

### 7.3. Main.java

Tạo `src/main/java/com/example/uber/Main.java`:

~~~java
package com.example.uber;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

import org.apache.commons.lang3.StringUtils;

public final class Main {

    private Main() {
    }

    private static String banner() {
        try (InputStream input =
                Main.class.getResourceAsStream("/demo/banner.txt")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing resource /demo/banner.txt");
            }
            return new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static String message() {
        return "Uber JAR: " + StringUtils.upperCase("maven")
                + " / " + banner();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Trong class:

- `StringUtils.upperCase("maven")` là lời gọi thật tới Commons Lang dependency.
- `getResourceAsStream("/demo/banner.txt")` tải resource từ **classpath của JAR**, không phụ thuộc vào source tree sau khi deploy.
- `readAllBytes()` và `StandardCharsets.UTF_8` có trong Java 17.
- `strip()` loại newline/whitespace của resource.
- `message()` tạo một chuỗi xác định để JUnit test kiểm tra.
- Main class có tên đầy đủ `com.example.uber.Main`, khớp với `ManifestResourceTransformer`.

### 7.4. banner.txt

Tạo tệp UTF-8 `src/main/resources/demo/banner.txt` có nội dung:

~~~text
BUNDLED RESOURCE
~~~

Không dùng đường dẫn tuyệt đối từ máy developer; resource này được Resources Plugin đưa vào `target/classes/demo/banner.txt`, rồi được JAR Plugin đóng gói và Shade giữ lại.

### 7.5. Unit test MainTest.java

Tạo `src/test/java/com/example/uber/MainTest.java`:

~~~java
package com.example.uber;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {

    @Test
    void usesDependencyAndResource() {
        assertEquals(
                "Uber JAR: MAVEN / BUNDLED RESOURCE",
                Main.message());
    }
}
~~~

Test này chạy bằng Surefire ở phase `test` và kiểm chứng API dependency cùng resource trên **test classpath**. Nó **chưa chứng minh Uber JAR sau shade tự chạy được**; bước `java -jar` bên dưới là smoke test phân phối riêng rất quan trọng.

### 7.6. Chạy build

Ở thư mục `uber-demo` chứa `pom.xml`:

~~~bash
mvn -version
java -version
mvn -B clean verify
~~~

Kết quả mong đợi:

- Compiler biên dịch Java source.
- Resources Plugin copy `demo/banner.txt`.
- Surefire chạy **1 JUnit test** và test pass.
- JAR Plugin tạo artifact JAR thông thường ở `package`.
- Shade Plugin gộp Commons Lang runtime dependency vào final JAR, thiết lập manifest và xử lý services nếu cần.
- `verify` hoàn tất các phase tới verify, kết thúc `BUILD SUCCESS` nếu không có lỗi.
- File chính của project, theo cấu hình ví dụ, là `target/uber-demo-1.0.0.jar`.

Chạy:

~~~bash
java -jar target/uber-demo-1.0.0.jar
~~~

**Stdout chính xác của chương trình demo khi build thành công:**

~~~text
Uber JAR: MAVEN / BUNDLED RESOURCE
~~~

Không cần một file commons-lang3 JAR đứng bên cạnh để chạy ví dụ. Đó là bằng chứng thực tế rằng dependency class đã được đóng gói trong artifact.

### 7.7. Kiểm tra nội dung JAR

Chạy:

~~~bash
jar tf target/uber-demo-1.0.0.jar
~~~

Phải có các entries:

~~~text
META-INF/MANIFEST.MF
com/example/uber/Main.class
demo/banner.txt
org/apache/commons/lang3/StringUtils.class
~~~

Danh sách trên là **những entry cần có**, không phải toàn bộ output. Một Uber JAR có thể chứa hàng trăm hoặc hàng nghìn class khác.

Để kiểm tra main class qua Java launcher, `java -jar` là thử nghiệm thực tế. Có thể đọc manifest bằng một archive viewer hoặc công cụ ZIP/JAR phù hợp và xác minh:

~~~text
Main-Class: com.example.uber.Main
~~~

**Hai điều kiện cần kiểm chứng:** `Main-Class` hợp lệ **và** `StringUtils.class` có trong artifact cuối. Nếu chỉ có manifest mà không có dependency class, một lệnh `java -jar` có thể vẫn fail lúc runtime.

### 7.8. Vì sao build có thể sinh dependency-reduced-pom.xml?

Vì POM ví dụ dùng `createDependencyReducedPom=true`, Shade có thể tạo:

~~~text
uber-demo/
├── pom.xml
├── dependency-reduced-pom.xml
└── target/...
~~~

Shade dùng reduced POM khi thích hợp để mô tả artifact đã gộp dependencies. File phụ này **không phải source POM do người học tự viết**, và thường không nên commit vào Git nếu team chưa định rõ workflow. Có thể thêm nó vào `.gitignore` hoặc quản lý bằng convention.

Nếu chạy `mvn clean`, **Maven Clean mặc định dọn output build như `target/`**, không phải lúc nào cũng xóa `dependency-reduced-pom.xml` ở basedir. Vì vậy cần có chính sách cleanup/ignore rõ ràng thay vì nói rằng mọi file do shade tạo đều được clean dọn sạch.

Đừng tự chỉnh dependency-reduced-pom.xml rồi xem nó là POM gốc của project. Khi publication, cần xem artifact POM thực sự được `install`/`deploy` và quy tắc Shade/other release plugins.

## 8. Tại sao `java -jar` không tự tải dependencies từ Maven?

Lệnh:

~~~bash
java -jar target/uber-demo-1.0.0.jar
~~~

là lệnh Java launcher. Nó **không hỏi Maven** cách giải GAV, không đọc POM để tải dependencies, không tự lấy các JAR từ `~/.m2/repository`.

Một thin JAR có thể hoạt động nếu đặt external libraries trên classpath:

~~~text
dist/
├── app.jar
└── lib/
    └── commons-lang3-3.17.0.jar
~~~

Ví dụ classpath trên Linux/macOS:

~~~bash
java -cp "app.jar:lib/*" com.example.uber.Main
~~~

Trên Windows, dấu phân cách classpath thường là dấu `;`, ví dụ:

~~~powershell
java -cp "app.jar;lib/*" com.example.uber.Main
~~~

Các ví dụ này giả định bạn đang đứng trong thư mục `dist/` và `app.jar` có class ứng dụng; runtime libraries được đặt đúng trong `lib/`.

**`java -jar` và `java -cp` không tương đương hoàn toàn:** khi dùng `-jar`, Java launcher dùng manifest entrypoint và classpath theo semantics của `-jar`; một `-cp` tùy ý ở cùng lệnh không cứu một JAR thiếu dependency theo cách người học thường kỳ vọng.

### Lỗi thường gặp với thin JAR

Nếu main manifest đã cấu hình nhưng dependencies không có ở runtime, có thể thấy:

~~~text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
~~~

Đây là **dạng lỗi minh họa**; JVM stack trace và root cause cụ thể phụ thuộc code, launcher và môi trường. Nếu thin JAR còn **không có Main-Class**, `java -jar` có thể báo **no main manifest attribute** trước khi chạy tới code. Hai lỗi này có nguyên nhân khác nhau.

## 9. Shade có nên thay main artifact hay attach classifier?

Shade Plugin cung cấp hai kiểu publication chính:

### 9.1. Thay main artifact

~~~xml
<shadedArtifactAttached>false</shadedArtifactAttached>
~~~

Với POM demo, shaded JAR được chọn làm **main artifact**. Lệnh `mvn install`/`mvn deploy` có thể publish file JAR này là artifact chính ở tọa độ `com.example:uber-demo:1.0.0`. POM tiêu thụ cần phản ánh chính xác những dependencies đã gộp hoặc còn phải tải.

**Ưu điểm:** người dùng chỉ tải GAV và nhận ngay Uber JAR; phù hợp executable app. **Rủi ro:** một downstream library consumer có thể nhận một fat artifact không mong đợi.

### 9.2. Attach shaded artifact riêng

Nếu muốn giữ thin main JAR và có thêm `all`/`shaded` classifier:

~~~xml
<shadedArtifactAttached>true</shadedArtifactAttached>
<shadedClassifierName>all</shadedClassifierName>
~~~

Với cùng GAV, kiểu artifact phụ sẽ có tên thường như:

~~~text
uber-demo-1.0.0.jar
uber-demo-1.0.0-all.jar
~~~

Trong đó `all` là **classifier tự chọn**, không phải từ khóa bắt buộc. Khi consumer muốn artifact phụ, phải khai báo classifier/type phù hợp; dependency vào GAV thường không tự chọn bản `all`.

**Chọn kiểu nào?**

- Với CLI/application được deploy, muốn “main artifact là executable” → có thể để Shade thay main.
- Với library/API module cần công bố thin JAR bình thường và một executable utility riêng → cân nhắc attach classifier; review publication POM.
- Với multi-module dùng chung thư viện, nên suy nghĩ kỹ trước khi phát hành fat JAR làm dependency cho modules khác.

Khi chuyển từ `shadedArtifactAttached=false` sang `true`, **đừng giữ nguyên lệnh `java -jar target/uber-demo-1.0.0.jar` rồi giả định nó vẫn là shaded JAR**. Cần chạy đúng filename classifier đã cấu hình.

## 10. Dependency-reduced POM: giảm transitive duplication khi publish

Maven consumer thông thường đọc **POM** để biết transitive dependencies. Nhưng khi một Uber JAR **đã nhúng** một dependency, việc tiếp tục khai báo nó là external transitive dependency có thể gây tải/thêm thư viện hai lần hoặc tạo conflict với phiên bản khác.

Shade có tham số:

~~~xml
<createDependencyReducedPom>true</createDependencyReducedPom>
~~~

Mặc định của Shade Plugin 3.6.2 là **true**. Reduced POM có thể loại những dependencies đã được gộp khỏi phần dependencies mà consumer cần tải riêng, tùy scope/configuration. Không nên mô tả nó như lệnh “xóa hết dependencies” hoặc “xóa POM gốc”.

Nếu cấu hình:

~~~xml
<createDependencyReducedPom>false</createDependencyReducedPom>
~~~

Shade không tạo reduced POM. Với **executable-only app không được dùng như library**, đây đôi khi là lựa chọn để tránh file phát sinh, nhưng phải review cẩn thận nếu artifact được install/deploy và dùng làm dependency cho module khác.

Các điểm cần kiểm:

1. Dependencies nào thực sự được gộp vào bytecode/resources của shaded JAR?
2. Dependencies nào vẫn phải ở runtime ngoài archive?
3. Có scopes `provided`, `runtime`, `optional`, classifier hoặc exclusions đặc biệt không?
4. Dependency graph downstream có đúng sau khi publish không?
5. Có APIs công khai lộ classes từ libraries đã relocated không?
6. Reduced POM có vô tình ảnh hưởng parent/BOM/dependencyManagement hoặc release pipeline không?
7. Artifact `all` có classifier hay đang thay main artifact?

Đối với một JAR đóng gói để chạy độc lập, vẫn cần giữ **SBOM và thông tin về dependencies bên trong**, dù POM rút gọn khiến Maven consumer không tải chúng như transitive dependencies nữa.

## 11. Resource collisions: một đường dẫn xuất hiện trong nhiều JAR

Khi unpack nhiều JAR vào một namespace file duy nhất, có thể xuất hiện **trùng entry path**:

~~~text
dependency-a.jar: META-INF/services/com.example.spi.Codec
dependency-b.jar: META-INF/services/com.example.spi.Codec

dependency-a.jar: META-INF/spring.handlers
dependency-b.jar: META-INF/spring.handlers

dependency-a.jar: META-INF/LICENSE
dependency-b.jar: META-INF/LICENSE
~~~

Nếu chỉ copy entry theo tên path, bản gộp có thể **mất dữ liệu của một phía** hoặc chọn entry không mong muốn. Không nên mặc định rằng `jar-with-dependencies` hoặc một shade không cấu hình sẽ tự hiểu semantics của mọi file trùng tên.

**Đây là lý do resource transformers tồn tại:** plugin cần biết đường dẫn nào phải merge, append, chọn theo priority hay tạo lại.

### Những loại file trùng phổ biến

| File/resource | Ý nghĩa | Rủi ro nếu gộp sai |
| --- | --- | --- |
| `META-INF/services/<interface>` | Danh sách ServiceLoader implementations | Một provider biến mất, `ServiceLoader` không tìm thấy |
| `META-INF/spring.handlers` / `spring.schemas` | Spring framework metadata đời cũ | Spring loader mất mapping |
| Log framework plugin cache / plugin descriptors | Danh sách plugin/extension | Runtime thiếu extension/serializer |
| `META-INF/NOTICE`, `LICENSE` | Thông báo bản quyền | Vi phạm nghĩa vụ hoặc thất lạc attribution |
| `reference.conf`, config `.properties` | Giá trị mặc định của frameworks | Một config ghi đè config khác |
| Native-image metadata | Hints/resource configs | Native runtime/build có thể sai |
| `META-INF/MANIFEST.MF` | Main class, metadata của archive | Main-Class sai hoặc signed metadata cũ |
| `META-INF/versions/...` | Multi-release JAR entries | Runtime trên JDK mới có thể khác hoặc hỏng |
| `module-info.class` | JPMS module descriptor | Gộp nhiều modules phá mô hình module |

**Không có một transformer chung đúng cho mọi file.** Cần đọc tài liệu của thư viện/framework và kiểm thử output thực.

## 12. `ServicesResourceTransformer`: ServiceLoader cần nhiều providers

Java có API:

~~~java
java.util.ServiceLoader.load(com.example.spi.Codec.class);
~~~

Để biết implementations, ServiceLoader đọc file theo tên:

~~~text
META-INF/services/com.example.spi.Codec
~~~

Giả sử:

~~~text
provider-a.jar:
  META-INF/services/com.example.spi.Codec
  nội dung: com.example.codec.JsonCodec

provider-b.jar:
  META-INF/services/com.example.spi.Codec
  nội dung: com.example.codec.XmlCodec
~~~

Nếu gộp JAR mà chỉ giữ file service của một bên, runtime chỉ nhận một provider. **Phần minh họa này không phải runnable demo độc lập** vì thiếu interface và class provider tương ứng; nó mô tả cơ chế service metadata.

Shade cung cấp:

~~~xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

Transformer này **gộp các service files cùng path**, đồng thời xử lý service class names khi class được relocate. Trong project demo ở phần 7, transformer đã được cấu hình; nếu Commons Lang không có các service entries liên quan, nó không làm thay đổi hành vi Main.

**Test thật phải gọi `ServiceLoader.load(...)` trong executable JAR cuối** và kiểm tra tất cả providers mong đợi. Chỉ dùng `jar tf` và thấy một file `META-INF/services/...` chưa đủ chứng minh nội dung đã merge đúng.

Nếu một thư viện dùng resource registry khác ServiceLoader, cần transformer/framework plugin tương ứng; đừng áp `ServicesResourceTransformer` rồi cho rằng mọi metadata đều được merge.

## 13. ManifestResourceTransformer: Main-Class và manifest entries

Để executable, JAR cần:

~~~text
META-INF/MANIFEST.MF
Main-Class: com.example.uber.Main
~~~

Cấu hình trong Shade:

~~~xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>com.example.uber.Main</mainClass>
    </transformer>
</transformers>
~~~

Nó khác `<archive><manifest><mainClass>...</mainClass></manifest></archive>` được **Maven JAR Plugin / Maven Assembly Plugin** hỗ trợ qua archiver configuration. **Không copy cú pháp manifest giữa Shade và Assembly** mà không kiểm tra tài liệu plugin.

Một số ứng dụng cần thêm manifest entries như `Implementation-Version`, `Automatic-Module-Name` hoặc thông tin build. Cần cân nhắc tính lặp lại và JPMS semantics. Nếu đặt `Main-Class` sai package/class, `java -jar` fail dù dependencies đều có.

**Cảnh báo:** `Main-Class` không phải Maven `groupId` hoặc `artifactId`. Nó là fully qualified class name có `public static void main(String[] args)`.

## 14. Relocation: đổi package của một dependency để tránh conflict

Một mục đích nâng cao của Shade là **relocate** bytecode package names của library đi vào JAR cuối. Tình huống:

~~~text
host application: dùng org.example.util phiên bản A
plugin của bạn: dùng org.example.util phiên bản B
~~~

Nếu hai phiên bản trên cùng classpath, Java class loading có thể lấy class sai và gây `NoSuchMethodError`, `LinkageError` hoặc hành vi không tương thích. Relocation có thể tạo bản private:

~~~text
org.example.util
    ->
com.example.uber.internal.org.example.util
~~~

Ví dụ mảnh Shade configuration (không nằm trong POM demo, không có dependency thực tên này):

~~~xml
<relocations>
    <relocation>
        <pattern>org.example.util</pattern>
        <shadedPattern>com.example.uber.internal.org.example.util</shadedPattern>
    </relocation>
</relocations>
~~~

Shade di chuyển class entries và sửa những bytecode references mà nó hỗ trợ. Với dependency thật Commons Lang, nếu muốn thử relocation có thể chọn `org.apache.commons.lang3` → `com.example.uber.internal.commonslang3`, nhưng **chỉ làm nếu có lý do thực** và thêm regression tests.

**Không relocate bừa toàn bộ `org.apache` hoặc `com.fasterxml`** vì điều đó có thể đổi public API, reflection names và resource conventions của thư viện.

### Những trường hợp relocation không tự sửa được hoàn toàn

- Class names được đọc từ chuỗi cấu hình hoặc gọi `Class.forName("...")`.
- JNI/native libraries dùng tên class/phương thức đã biên dịch.
- Serialization/deserialization hoặc message protocols mang type names cố định.
- Framework scanning dựa trên hardcoded package names.
- Resource files chứa class names nhưng chưa được transformer cập nhật.
- `META-INF/services` nếu không có `ServicesResourceTransformer`.
- Reflection hoặc bytecode code generation dùng tên class theo runtime.
- API công khai của library được consumer bên ngoài tham chiếu.

**Relocation là công cụ xử lý classpath conflicts có giới hạn**, không phải lời đảm bảo rằng mọi runtime references sẽ tương thích. Cần thử `java -jar` và các chức năng có ServiceLoader/reflection thật.

## 15. Minimization: `minimizeJar` không phải tối ưu vô rủi ro

Shade có thể đặt:

~~~xml
<minimizeJar>true</minimizeJar>
~~~

Theo tài liệu chính thức, tính năng này dùng phân tích dependency reachability ở mức class (dựa trên **jdependency**) để bỏ classes không được xem là cần. Có thể làm JAR nhỏ hơn, nhưng **không thể thấy mọi dependency động**.

Ví dụ:

~~~java
Class<?> loaded = Class.forName("com.example.plugins.DynamicPlugin");
~~~

Nếu class chỉ được tham chiếu bằng string hoặc cấu hình bên ngoài, bộ phân tích tĩnh có thể không nhận ra nó cần được giữ. Các kỹ thuật dễ gặp rủi ro:

- Reflection và dependency injection.
- `ServiceLoader`/SPI providers.
- Jackson serializers hoặc annotation-driven discovery.
- Hibernate/JPA entity scanning.
- JNI/native entry points.
- Log4j/SLF4J providers, runtime plugin registries.
- Bytecode generation và scripting engines.
- Các lớp chỉ được gọi từ file cấu hình hoặc qua network conventions.

Do đó, **mặc định nên để `minimizeJar=false`** cho executable app khi chưa có tests đầy đủ. Chỉ bật sau khi so dung lượng, dùng `entryPoints` khi phù hợp và kiểm thử toàn bộ runtime paths cần thiết.

Một Uber JAR lớn nhưng hoạt động đúng thường tốt hơn một JAR nhỏ gây lỗi mất class sau deploy.

## 16. Chọn dependencies và loại entries đúng chỗ

Shade hỗ trợ `artifactSet` để chỉ định những artifact nào được gộp hoặc loại khỏi JAR:

~~~xml
<artifactSet>
    <excludes>
        <exclude>com.example:optional-tool</exclude>
    </excludes>
</artifactSet>
~~~

Đây là mảnh cấu hình minh họa; chỉ exclude nếu application không thực sự cần classes/resources của artifact đó ở runtime.

`filters` cho phép chọn entries **bên trong** những artifact được gộp:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.RSA</exclude>
        </excludes>
    </filter>
</filters>
~~~

Lý do loại các entry signature metadata là vì khi unpack/đổi bytes của signed JAR, chữ ký của JAR gốc có thể không còn hợp lệ cho nội dung archive mới. Tuy nhiên:

- **Không được coi loại signatures là một biện pháp xác thực**.
- Phải giữ giấy phép và NOTICE theo nghĩa vụ của từng dependency.
- Không loại `.class` hoặc resource chỉ để giảm dung lượng khi chưa biết tác động.
- Nếu dependency có `META-INF/services` hoặc metadata đặc biệt, cần merge có chủ đích.
- Có thể có signature formats/metadata đặc thù khác; áp dụng policy của nguồn và release pipeline.
- Nếu final artifact cần ký, phải ký lại **final distribution artifact** theo quy trình release.

**Tốt nhất dùng artifact filters càng hẹp càng đủ**, không xóa toàn bộ `META-INF` vì nhiều frameworks cần metadata trong đó.

## 17. Thay Shade bằng Assembly `jar-with-dependencies` khi nhu cầu đơn giản

Nếu không cần relocation/service merging phức tạp, có thể dùng **Maven Assembly Plugin**. Để so sánh công bằng với cùng Java code ở phần 7, hãy **tạo bản sao project và bỏ cấu hình Shade** trước khi dùng Assembly, tránh hai plugins cùng tạo fat outputs.

Mảnh plugin thay thế:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.8.0</version>
    <configuration>
        <descriptorRefs>
            <descriptorRef>jar-with-dependencies</descriptorRef>
        </descriptorRefs>
        <archive>
            <manifest>
                <mainClass>com.example.uber.Main</mainClass>
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
~~~

Đoạn trên là **một plugin fragment**, thay thế Shade Plugin trong `<build><plugins>` của POM demo. Các dependencies, code Main và resources vẫn như cũ.

Chạy:

~~~bash
mvn -B clean package
java -jar target/uber-demo-1.0.0-jar-with-dependencies.jar
~~~

Với plugin 3.8.0, descriptor chuẩn và manifest cấu hình như trên, **stdout chính xác dự kiến**:

~~~text
Uber JAR: MAVEN / BUNDLED RESOURCE
~~~

Tên file output có classifier `jar-with-dependencies` theo predefined assembly descriptor. Bản main thin JAR thường vẫn có ở `target/uber-demo-1.0.0.jar`.

**Hạn chế cần nhớ:** `jar-with-dependencies` là gói basic. Không khẳng định nó xử lý service provider collisions, signatures hay config registry giống `ServicesResourceTransformer`. Với ứng dụng nhiều frameworks dùng SPI, nên kiểm tra nội dung JAR kỹ và cân nhắc Shade.

### Khi Assembly phù hợp hơn một Uber JAR

Assembly còn hỗ trợ `bin`/custom descriptors để tạo:

~~~text
distribution.zip
  bin/start.sh
  bin/start.cmd
  lib/app.jar
  lib/dependency-a.jar
  lib/dependency-b.jar
  config/application.properties
  README.md
  LICENSE/NOTICE
~~~

Đây là **sơ đồ một distribution do descriptor tự định nghĩa**, không phải output tự động của `jar-with-dependencies`. Nó có thể tốt hơn nếu muốn cho người vận hành đổi config hoặc kiểm soát từng JAR thay vì tạo một fat archive duy nhất.

## 18. Maven package/install/deploy không đồng nghĩa “chạy ứng dụng”

| Lệnh | Kết quả | Không tự làm |
| --- | --- | --- |
| `mvn package` | Tạo JAR/uber JAR trong target | Không upload artifact lên remote |
| `mvn install` | Lưu artifact/POM ở local Maven repository | Không deploy ứng dụng đang chạy |
| `mvn deploy` | Publish artifact đến Maven remote repository | Không khởi động service ở production |
| `java -jar ...` | Khởi động chương trình Java | Không tải Maven dependencies còn thiếu |
| Docker/container deployment | Tạo/chạy container với runtime và config riêng | Không do Shade Plugin tự tạo |

Với `shadedArtifactAttached=false`, Shade thay main Maven artifact bằng Uber JAR trước install/deploy. Với classifier `all`, Maven có thể install/deploy cả main thin artifact và artifact phụ.

Điểm cần review trong release pipeline: **artifact nào được publish dưới GAV chính, artifact nào là classifier, và consumer lấy cái nào**. Không nên để một CI job chạy `java -jar target/*jar` bằng wildcard không chọn lọc, vì có thể chọn thin JAR hoặc JAR khác.

## 19. Reproducible build và supply-chain integrity

“Chỉ một JAR” không tự có nghĩa artifact **lặp lại byte-for-byte**. Kết quả có thể thay đổi do:

- Java compiler/JDK version.
- Maven plugins/shade/assembly version.
- Dependency resolution và snapshot versions.
- ZIP timestamps/order, manifest entries và generated build metadata.
- Resource filtering theo environment.
- File encoding/locale.
- External generators không deterministic.

Để ổn định:

1. Pin Maven/JDK/plugins/dependencies trong release pipeline.
2. Hạn chế SNAPSHOT và dynamic version ranges cho bản phát hành.
3. Dùng `project.build.outputTimestamp` nếu các plugins/build stack hỗ trợ reproducible archives.
4. Tránh nhúng build time/hostname/token không cần thiết.
5. Ghi lại artifact checksum, Maven coordinates, commit và build environment.
6. Kiểm tra POM/metadata đã publish và bytes JAR thật.
7. Lưu SBOM hoặc dependency inventory của các thành phần được gộp.
8. Giữ license/NOTICE đúng nghĩa vụ.
9. Chạy vulnerability/license scans trên **embedded dependencies**, không chỉ trên Maven runtime classpath bên ngoài.
10. Ký hoặc xác minh final release artifact theo chính sách.

Ví dụ Linux:

~~~bash
sha256sum target/uber-demo-1.0.0.jar
~~~

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path "target/uber-demo-1.0.0.jar"
~~~

Giá trị SHA-256 phải tính từ bytes thực tế, **không thể hardcode một digest cố định cho mọi máy và mọi lượt build**. Checksum giúp so sánh nội dung nhưng không tự chứng minh ai đã phát hành JAR; cần trust chain/signature/provenance khi yêu cầu.

### Security update không biến mất khi dependency bị nhúng

Một thư viện có CVE khi được gộp vào Uber JAR vẫn cần update. Vì code library đã là **một phần của artifact**, cập nhật dependency thường yêu cầu **rebuild và phát hành Uber JAR mới**. Không thể chỉ thay file `lib/foo.jar` như khi dùng distribution tách thư viện.

Đây là chi phí vận hành quan trọng khi chọn một artifact monolithic.

## 20. Các trường hợp nâng cao cần thiết kế riêng

### 20.1. Spring Boot executable JAR

Spring Boot Maven Plugin thường tạo JAR có cấu trúc nested libraries và launcher của Spring Boot. Nó **không giống** cách Shade flatten classes vào root archive.

Nếu một ứng dụng đã dùng Spring Boot repackage, đừng thêm Shade vào cùng artifact mà không đọc tài liệu integration và kiểm thử runtime. Có thể cần chọn một cơ chế đóng gói chính, không kết hợp tùy tiện.

### 20.2. Java Platform Module System (JPMS)

Một số JAR có `module-info.class`. Gộp nhiều modules vào một flat JAR có thể làm module metadata hoặc service declarations mất ý nghĩa. Cần kiểm tra việc chạy trên module path, service binding, automatic modules và những gì Shade thực sự thay đổi.

Uber JAR dạng flat thường phù hợp cách chạy **classpath**, không tự là một modular runtime image. Với mục tiêu đóng gói JDK+modules, có thể nghiên cứu `jlink`/`jpackage` và các ràng buộc của chúng.

### 20.3. Native libraries và platform-specific classifiers

Một dependency có thể dùng `.dll`, `.so`, `.dylib` hoặc chọn classifier theo OS/architecture. Khi gộp, cần đảm bảo binary phù hợp được đưa theo artifact, loader biết cách trích xuất/tải, và mỗi runtime platform được kiểm thử.

Một Uber JAR chứa **Linux native library** không tự chạy trên Windows chỉ vì extension là `.jar`.

### 20.4. Signed JARs và framework metadata

Khi xóa signature metadata gốc, phải hiểu khác biệt giữa **tránh lỗi verify archive đã đổi** và **xác thực sản phẩm cuối**. Với những frameworks yêu cầu signing hoặc plugin caches, có thể cần công cụ chuyên dụng hoặc tránh shade các dependencies đó.

### 20.5. Logging frameworks và provider discovery

Một JAR có `slf4j-api` nhưng không có compatible provider/implementation, hoặc có nhiều providers không tương thích, có thể báo warning hoặc log sai. Shade chỉ gộp classes/resources; nó không chọn giúp dependency version tương thích. Cần kiểm tra runtime logs và sử dụng một logging implementation theo thiết kế.

### 20.6. Reflection và generated proxies

Nếu dùng Hibernate, Jackson, CDI, Micronaut, dependency injection hay scripting, đừng bật `minimizeJar` trước khi chạy integration tests. Nếu relocate, kiểm tra thêm metadata/resource mappings và những classes được gọi gián tiếp bằng tên chuỗi.

## 21. Chiến lược QA cho Uber JAR

Chỉ thấy `mvn package` in BUILD SUCCESS **chưa đủ** chứng minh artifact phân phối hoạt động. Một quy trình QA hữu ích:

### 21.1. Kiểm tra build inputs

~~~bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
~~~

Xem Maven/JDK versions, dependencies và Shade/Assembly executions, active profiles. `dependency:tree` cho thấy **Maven graph**, không phải danh sách class cuối trong shaded archive.

### 21.2. Build sạch

~~~bash
mvn -B clean verify
~~~

Clean tránh output stale, verify chạy unit tests và checks cấu hình đến phase verify. Nếu project có integration tests sử dụng Failsafe, kiểm tra đã bind các goals phù hợp; không mặc định `verify` sẽ chạy một suite chưa cấu hình.

### 21.3. Kiểm tra manifest và dependency classes

~~~bash
jar tf target/uber-demo-1.0.0.jar
~~~

Với demo, phải thấy Main.class, StringUtils.class và banner resource. Nếu bật relocations, **đường dẫn class dependency** trong JAR có thể đổi theo relocated package, nên kiểm tra path mới.

### 21.4. Smoke test thật bằng Java launcher

~~~bash
java -jar target/uber-demo-1.0.0.jar
~~~

Nếu chương trình chạy trên developer laptop vì classpath ngầm khác, hãy thử trong một thư mục/CI image không chứa Maven repo và không cung cấp external classpath tùy ý. **`java -jar` từ một đường dẫn đơn lẻ** là phép thử gần với mục tiêu một-file distribution.

### 21.5. Kiểm tra plugins và resource metadata

Nếu application dùng `ServiceLoader`, chạy test thực sự gọi ServiceLoader. Nếu cần Spring handlers hoặc config registry, xác minh các files tương ứng sau transform. Nếu có native code, test trên OS/architecture đích.

### 21.6. Kiểm tra publication

Nếu release với `mvn install` hoặc `deploy`, xem reduced POM, main artifact/classifier và dependency behavior của consumer thử nghiệm. Không chỉ nhìn file trong `target/` và suy ra repository đã publish đúng.

### 21.7. Kiểm tra security/legal

Dùng dependency vulnerability scanning, license inventory, SBOM, artifact signing và provenance phù hợp. Đừng xóa `LICENSE`/`NOTICE` chỉ để giảm size.

## 22. Troubleshooting: triệu chứng, nguyên nhân và giải pháp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `no main manifest attribute` | Thiếu hoặc sai ManifestResourceTransformer | Xem `META-INF/MANIFEST.MF`, cấu hình Main-Class |
| `NoClassDefFoundError` khi `java -jar` | JAR mỏng, dependency bị exclude/minimize, sai scope | `jar tf`, dependency tree, Shade filters |
| Build xanh nhưng chạy `java -jar` fail | Chỉ unit test bằng full Maven test classpath, chưa smoke test output | Chạy executable artifact thật |
| `Invalid signature file digest` | META-INF signature metadata gốc không còn hợp lệ sau merge | Kiểm tra filters `.SF/.DSA/.RSA`, signed policy |
| ServiceLoader chỉ thấy một provider | Trùng META-INF/services file bị ghi đè | Dùng ServicesResourceTransformer và test providers |
| App không thấy resource config | Duplicate path hoặc resource bị filter | Kiểm tra jar entries, transformers, input resource roots |
| `ClassNotFoundException` chỉ khi chạy reflection | `minimizeJar` loại class dùng động | Tắt minimization hoặc cấu hình entryPoints và test |
| `NoSuchMethodError` khi nhúng vào host | Conflict phiên bản classes trên classpath | Review dependency mediation và relocation |
| Maven báo overlapping classes | Nhiều dependencies có cùng FQCN | Xác định nguồn, loại dependency trùng có chọn lọc |
| Runtime behavior khác khi relocate | Class name strings, ServiceLoader hoặc reflection không được cập nhật | Rà soát metadata, integration tests |
| JAR có file JAR bên trong nhưng thiếu class | Nested JAR không được Java class loader chuẩn xử lý | Dùng flattening hoặc framework launcher thích hợp |
| `java -jar target/*.jar` chạy nhầm file | Có thin + shaded/assembly outputs | Chọn filename/classifier tường minh |
| CI không có artifact classifier `all` | shade attached false hoặc deploy scope sai | Kiểm tra shadedArtifactAttached, classifier, install/deploy |
| Consumer tải lại libs đã embed | POM publication không phản ánh shaded contents | Review dependency-reduced POM, consumer graph |
| License NOTICE bị thất lạc | Merge resource tùy tiện | Dùng transformer/policy và kiểm tra legal artifacts |
| Executable quá lớn | Gộp unnecessary runtime dependencies | Review scope, artifactSet và dependency graph |
| JAR nhỏ nhưng production fail | minimizeJar làm mất reflection/service classes | Tắt minimize, bổ sung tests |
| Java 17 class chạy trên Java 11 fail | Bytecode/JDK target không phù hợp | Kiểm tra `maven.compiler.release`, runtime Java version |
| Chỉ Linux chạy, Windows fail | Native binary/platform-specific dependency | Xây/test artifacts phù hợp OS |
| Spring Boot JAR không chạy sau Shade | Hai packaging mechanisms xung đột | Dùng một packaging pipeline được framework hỗ trợ |
| Project phụ thuộc library shaded nhưng API sai | Relocation làm lộ/mất public types | Thiết kế library artifact riêng |
| `mvn clean` không xóa reduced POM | dependency-reduced-pom nằm ở basedir | Quản lý .gitignore/cleanup hợp lệ |
| Scanners không thấy embedded CVE | Dependency metadata bị giảm hoặc scanner chỉ nhìn POM | Quét shaded contents, duy trì SBOM |

**Không sửa một `NoClassDefFoundError` bằng cách copy ngẫu nhiên mọi JAR vào archive**. Cần xác định chính xác class thuộc dependency nào, scope, exclusions, version và liệu class bị minimize/relocate hay runtime thật sự cần một JAR ngoài.

## 23. Thực hành với JAR thực tế: checklist theo từng bước

1. Xác định mục tiêu phân phối: **một executable JAR**, thư viện, hay ZIP/TAR có thư mục `lib/`?
2. Kiểm tra Java runtime đích và có cần native assets không.
3. Chọn **Shade** cho Uber JAR cần merge resources/relocation; **Assembly** cho bundle basic hoặc distribution archive.
4. Pin plugin versions và dependencies.
5. Khai báo `Main-Class` nếu muốn chạy `java -jar`.
6. Xác định dependencies cần embed; review compile/runtime/test/provided scopes.
7. Không add `jar:jar` execution trùng với default packaging binding.
8. Nếu dùng `META-INF/services`, thêm `ServicesResourceTransformer` và test discovery thật.
9. Nếu resources trùng tên, chọn transformer theo semantic từng file.
10. Chỉ relocate khi có xung đột cần giải quyết; test reflection/API boundary.
11. Để `minimizeJar=false` cho đến khi có regression coverage đủ.
12. Xử lý signed JAR metadata có chủ đích; không coi việc xóa signatures là chứng cứ an toàn.
13. Giữ LICENSE/NOTICE và dependency inventory/SBOM.
14. Quyết định replace main artifact hay attach classifier `all`.
15. Review dependency-reduced POM khi artifact được publish.
16. Dùng `mvn clean verify` để build sạch.
17. Dùng `jar tf` để kiểm tra entries thật.
18. Chạy `java -jar` trên artifact cuối trong môi trường gần production.
19. Có smoke/integration tests cho ServiceLoader, config resources, native code và reflection.
20. Kiểm tra checksum/provenance cuối cùng và chính xác artifact được deploy.
21. Không trộn Maven Shade với Spring Boot repackage hoặc framework packaging khác khi chưa kiểm chứng.
22. Giữ runtime secrets và environment config ở ngoài JAR khi có thể.
23. Kiểm tra khả năng rollback và rebuild khi một dependency có lỗ hổng.
24. Với library artifact, cân nhắc giữ thin JAR chuẩn thay vì ép mọi consumer nhận Uber JAR.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `mvn package` tạo JAR thành công nhưng `java -jar` vẫn có thể lỗi class không tìm thấy?

**Đáp:** JAR mặc định thường chỉ chứa class/resource của project. Dependency runtime nằm ở JAR riêng, nên launcher không thấy nếu chưa gộp hoặc cấu hình classpath phù hợp.

**Câu 2.** Thêm `Main-Class` vào manifest có tự gộp dependencies không?

**Đáp:** Không. Main-Class chỉ xác định entrypoint; cần thêm packaging/classpath strategy.

**Câu 3.** `java -jar` có hỏi Maven tải dependencies trong POM không?

**Đáp:** Không. Java launcher không thực hiện Maven dependency resolution.

**Câu 4.** Một JAR chứa `lib/library.jar` bên trong có tự load class của library không?

**Đáp:** Không với Java class loader chuẩn, trừ khi có loader/framework chuyên biệt xử lý nested JAR.

**Câu 5.** Shade khác Assembly `jar-with-dependencies` ở đâu?

**Đáp:** Shade có relocation, resource transformers, minimization/reduced POM; Assembly descriptor là cơ chế gộp basic, thích hợp cho các distribution khác nữa.

**Câu 6.** Khi hai dependency cùng có `META-INF/services/com.example.spi.Codec`, copy một file có đủ không?

**Đáp:** Không nếu cần cả hai providers. Cần merge service metadata đúng, chẳng hạn ServicesResourceTransformer.

**Câu 7.** Có nên bật `minimizeJar` ngay khi project dùng reflection và SPI?

**Đáp:** Không nên nếu chưa có tests bao phủ các class được load động. Phân tích tĩnh có thể không giữ đủ classes.

**Câu 8.** `shadedArtifactAttached=false` khác `true` thế nào?

**Đáp:** False làm shaded artifact thành main project artifact; true attach một artifact phụ có classifier và giữ main artifact riêng.

**Câu 9.** Tại sao Shade có dependency-reduced POM?

**Đáp:** Để publication metadata không tiếp tục yêu cầu consumer tải những dependencies đã được nhúng mà không cần dùng ngoài. Nó không thay thế việc kiểm kê embedded components.

**Câu 10.** Xóa `.SF/.RSA/.DSA` có đồng nghĩa JAR mới được ký và tin cậy không?

**Đáp:** Không. Nó loại metadata chữ ký gốc không còn tương ứng; final artifact cần ký/xác minh riêng nếu policy yêu cầu.

**Câu 11.** Test `MainTest` pass có đủ chứng minh `java -jar` chạy ở máy khác không?

**Đáp:** Chưa. Unit test dùng Maven test classpath. Phải chạy chính artifact cuối bằng Java launcher và test runtime paths.

**Câu 12.** Uber JAR có thể chứa cả JDK, database, secret manager không?

**Đáp:** Không mặc định. Nó chỉ đóng gói những class/resources được chọn; runtime JDK/external services/config vẫn cần được provision riêng.

**Câu 13.** Khi nào nên chọn distribution ZIP có `lib/` thay vì Uber JAR?

**Đáp:** Khi cần quản lý riêng từng dependency, native files, shell scripts, external configs, legal docs hoặc tận dụng layer/cache tốt hơn.

**Câu 14.** Nếu dependency bị CVE sau khi đã shade, có cần rebuild không?

**Đáp:** Thông thường có: embedded library đã nằm trong bytes của Uber JAR và cần được cập nhật bằng một artifact phát hành mới.

**Câu 15.** Với Spring Boot executable JAR có nested dependencies, có nên thêm Shade vào output chỉ để tạo “fat JAR hơn” không?

**Đáp:** Không mặc định. Spring Boot có launcher và packaging riêng; trộn hai cơ chế có thể làm JAR không chạy.

## 25. Tài liệu tham khảo chính thức

- [Apache Maven Shade Plugin — Introduction](https://maven.apache.org/plugins/maven-shade-plugin/)
- [Apache Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
- [Apache Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html)
- [Apache Maven Shade Plugin — Class Relocation](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html)
- [Apache Maven Shade Plugin — Attaching the Shaded Artifact](https://maven.apache.org/plugins/maven-shade-plugin/examples/attached-artifact.html)
- [Apache Maven Shade Plugin — Selecting Contents](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html)
- [Apache Maven Shade Plugin — shade:shade Parameters](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html)
- [Apache Maven Assembly Plugin — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html)
- [Apache Maven Assembly Plugin — Predefined Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Commons Lang — Release Notes](https://commons.apache.org/proper/commons-lang/changes.html)

