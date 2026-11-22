# Maven Assembly Plugin: đóng gói ZIP, TAR và bộ phân phối ứng dụng Java

## 1. Tại sao cần một gói phân phối thay vì chỉ một JAR?

`mvn package` thường tạo JAR chứa class và resource của một project Java. Tuy nhiên, một người nhận ứng dụng có thể cần thêm những thư viện runtime, script khởi động, tài liệu cài đặt, cấu hình mẫu và thông tin bản phát hành. Nếu chỉ đưa cho họ `app.jar`, ứng dụng dùng dependency bên ngoài có thể không chạy dù đã build và test thành công.

Một bộ phân phối có thể có cấu trúc:

~~~text
assembly-demo-1.0.0/
├── README.txt
├── bin/
│   ├── run.sh
│   └── run.cmd
└── lib/
    ├── assembly-demo-1.0.0.jar
    └── commons-lang3-3.14.0.jar
~~~

Người dùng giải nén một file ZIP hoặc TAR.GZ và chạy script tương ứng. Họ chỉ cần Java runtime đủ mới, không cần Maven hay source code để khởi động ứng dụng.

**Maven Assembly Plugin** tạo gói như vậy bằng cách đọc **assembly descriptor**: một file XML quy định định dạng archive, các file/thư mục phải chép, các dependency Maven cần đưa vào, vị trí đích, quyền file và nhiều lựa chọn phân phối khác. Nó phù hợp để tạo **distribution**, không chỉ fat JAR.

### Kết quả học tập

Sau bài này, bạn sẽ:

1. Phân biệt binary JAR, uber-JAR và archive phân phối ZIP/TAR.
2. Hiểu goal `assembly:single`, phase `package` và cách bind một execution vào Maven lifecycle.
3. Biết cách sử dụng các descriptor dựng sẵn `bin`, `jar-with-dependencies`, `src` và `project`.
4. Viết một descriptor riêng có `id`, `formats`, `includeBaseDirectory`, `fileSets`, `files` và `dependencySets`.
5. Chọn định dạng `zip`, `tar`, `tar.gz`, biết ý nghĩa của file permissions và tên thư mục gốc.
6. Tạo **dự án Maven 3.9.x / Java 17 / JUnit 5** hoàn chỉnh, dùng Assembly Plugin **3.8.0** và một dependency runtime thật.
7. Đóng ứng dụng, Commons Lang 3, README, script Linux/macOS và Windows vào cả ZIP và TAR.GZ.
8. Kiểm tra bằng `jar tf`, `tar -tzf`, giải nén, chạy smoke test và xác nhận stdout chính xác.
9. Hiểu khi nào archive được **attach** để `mvn install`/`deploy` xử lý và hậu quả của `appendAssemblyId=false`.
10. Chẩn đoán thiếu dependency, archive chứa nhầm files, build multi-module tạo gói trùng, JAR không chạy và rủi ro phát hành secrets.

Các version được ghim trong bài là **version ví dụ có thể tái hiện**, không phải tuyên bố luôn mới nhất.

## 2. Phân biệt JAR, uber-JAR và distribution

| Loại | Nội dung | Ví dụ | Mục đích |
| --- | --- | --- | --- |
| Binary JAR | Class và resources của project | `assembly-demo-1.0.0.jar` | Java classpath, Maven dependency |
| Uber/fat JAR | Class của project và dependency content được gộp | `app-all.jar` | Chạy một archive có nhiều classes |
| Distribution ZIP | JAR, lib, scripts, tài liệu | `assembly-demo-1.0.0-dist.zip` | Phát hành đa nền tảng |
| Distribution TAR.GZ | Cùng layout, trong TAR nén gzip | `assembly-demo-1.0.0-dist.tar.gz` | Phát hành cho Unix/Linux |
| Source archive | Source tree và metadata cần thiết | `*-src.zip` | Người dùng tải source/project |

Maven **JAR Plugin** tạo JAR chính; Maven **Shade Plugin** có transformers/relocation để xử lý một số vấn đề khi gộp nhiều JAR; Maven **Assembly Plugin** thường tạo **bộ file** với cấu trúc tùy chỉnh. Assembly cũng có descriptor `jar-with-dependencies`, nhưng không thay thế toàn bộ khả năng của Shade.

Ứng dụng ví dụ thực sự sử dụng Commons Lang 3. Binary JAR không chứa class `StringUtils`, còn distribution chứa **Commons Lang JAR riêng** dưới `lib`. Script sẽ chạy:

~~~bash
java -cp "lib/*" vn.example.assembly.App
~~~

Classpath wildcard do Java launcher xử lý, cho phép nạp các file JAR trực tiếp trong `lib`. Không dùng `java -jar app.jar` rồi mong Java tự đoán vị trí tất cả dependency; manifest `Main-Class` không có nghĩa manifest đã cung cấp `Class-Path` cho chúng.

## 3. Cách Assembly Plugin tham gia Maven lifecycle

Goal chính của plugin 3.8.0 là:

~~~text
org.apache.maven.plugins:maven-assembly-plugin:3.8.0:single
~~~

Có thể gọi trực tiếp:

~~~bash
mvn assembly:single
~~~

Nhưng nếu descriptor cần JAR do project vừa sinh, gọi goal đơn lẻ từ một checkout sạch có thể thiếu đầu vào. Với ứng dụng Java, lựa chọn thường đúng hơn là bind goal vào `package`:

~~~text
src/main/java  -> compile
src/test/java  -> test-compile -> Surefire tests
                                   |
                                   v
                               package
                                   |
                         maven-jar-plugin:jar
                                   |
                         project binary JAR
                                   |
                         maven-assembly-plugin:single
                           /                 \
                          v                   v
                     ZIP distribution    TAR.GZ distribution
                                   |
                         install/deploy nếu chạy đến phase đó
~~~

### 3.1. Plugin khai báo nhưng chưa chắc chạy

Chỉ khai:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.8.0</version>
</plugin>
~~~

**không tự tạo ZIP/TAR trong mọi lệnh `mvn package`**. Cần có descriptor và một execution bind goal `single` vào lifecycle, hoặc gọi goal CLI khi đầu vào đã sẵn sàng.

### 3.2. Cấu hình execution đúng

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>3.8.0</version>
    <configuration>
        <descriptors>
            <descriptor>src/assembly/distribution.xml</descriptor>
        </descriptors>
    </configuration>
    <executions>
        <execution>
            <id>build-distribution</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **plugin snippet**; POM runnable đầy đủ ở mục 7. `id=build-distribution` là ID của Maven execution, **không** phải classifier hay tên output. `goal=single` là goal `assembly:single`. Tên goal cũ `assembly:assembly` không nên dùng trong cấu hình hiện đại.

### 3.3. Một descriptor có thể tạo nhiều archive

Mặc dù goal tên `single`, descriptor có thể khai:

~~~xml
<formats>
    <format>zip</format>
    <format>tar.gz</format>
</formats>
~~~

Nó tạo hai archive từ cùng định nghĩa nội dung. `single` liên quan đến xử lý một assembly descriptor trong một lần goal execution, **không giới hạn một extension**.

## 4. Descriptor dựng sẵn và khi nào cần tự viết

Assembly Plugin có bốn built-in descriptor references:

| `descriptorRef` | Nội dung | Đầu ra phổ biến |
| --- | --- | --- |
| `bin` | Project binary artifact, README/LICENSE/NOTICE và tài liệu nếu có | ZIP, TAR.GZ, TAR.BZ2 |
| `jar-with-dependencies` | JAR với các dependency unpack vào archive | JAR |
| `src` | Gói source tree | ZIP, TAR.GZ, TAR.BZ2 |
| `project` | Gói project files phục vụ phân phối mã nguồn/build | ZIP, TAR.GZ, TAR.BZ2 |

Dùng một built-in descriptor:

~~~xml
<configuration>
    <descriptorRefs>
        <descriptorRef>bin</descriptorRef>
    </descriptorRefs>
</configuration>
~~~

Mẫu `bin` tiện để thử nhanh nhưng không mặc nhiên tạo cấu trúc `bin/run.sh`, `bin/run.cmd`, `lib/` đúng với hệ thống của bạn. Khi yêu cầu layout rõ ràng, một custom descriptor dễ bảo trì và kiểm thử hơn.

**Phân biệt:**

- `descriptorRefs/descriptorRef`: tên descriptor được đóng trong classpath plugin, ví dụ `bin`.
- `descriptors/descriptor`: đường dẫn file descriptor bạn tự viết, ví dụ `src/assembly/distribution.xml`.
- `descriptorSourceDirectory`: cách khác để tìm các descriptor files.

Trong project thực hành, chỉ dùng **`descriptors`**, tránh trộn ba cơ chế tìm file trong một demo.

### 4.1. Khi nào chọn Shade?

Built-in `jar-with-dependencies` giải nén libraries vào cùng một JAR. Nó thích hợp vài ứng dụng đơn giản, nhưng có thể gặp vấn đề với trùng resources, `META-INF/services`, signed JAR metadata hoặc class/package conflicts. Maven Shade Plugin cung cấp **resource transformers** và **relocation** để giải quyết những bài toán ấy.

Nếu mục tiêu của bạn là “một thư mục phân phối có thư viện riêng”, Assembly hợp lý. Nếu mục tiêu là “một JAR duy nhất chạy bằng `java -jar` có xử lý xung đột”, cần cân nhắc Shade hoặc plugin của framework.

## 5. Các thành phần quan trọng trong assembly descriptor

Custom descriptor có XML namespace/schema riêng của Maven Assembly, **không phải** schema `pom.xml`:

~~~xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
                              https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>dist</id>
    <formats>
        <format>zip</format>
        <format>tar.gz</format>
    </formats>
    <includeBaseDirectory>true</includeBaseDirectory>
    <!-- Nội dung fileSets/dependencySets được bổ sung bên dưới -->
</assembly>
~~~

Đây là **khung XML minh họa**, chưa phải descriptor đầy đủ cho ứng dụng.

| Node | Vai trò |
| --- | --- |
| `id` | Định danh assembly, thường trở thành classifier và hậu tố file |
| `formats` | Chọn một hoặc nhiều định dạng archive |
| `includeBaseDirectory` | Giữ toàn bộ nội dung trong một thư mục top-level |
| `baseDirectory` | Tùy chỉnh tên thư mục top-level |
| `fileSets` | Sao chép nhóm file từ thư mục và các includes/excludes |
| `files` | Sao chép một file cụ thể, có thể đặt lại tên |
| `dependencySets` | Lấy các Maven dependencies theo scope/filters |
| `moduleSets` | Gom artifact/source từ các module reactor |
| `componentDescriptors` | Chia sẻ những phần descriptor dùng lại |
| `containerDescriptorHandlers` | Xử lý một số nội dung descriptor cần hợp nhất |

### 5.1. id, classifier và version là ba thứ khác

Project POM khai:

~~~text
groupId    vn.example
artifactId assembly-demo
version    1.0.0
~~~

Descriptor khai:

~~~xml
<id>dist</id>
~~~

Khi `appendAssemblyId=true` (mặc định), archives sẽ được đặt tên:

~~~text
assembly-demo-1.0.0-dist.zip
assembly-demo-1.0.0-dist.tar.gz
~~~

`dist` là assembly ID/classifier, không phải một version khác của project. Tên và tọa độ `vn.example:assembly-demo:1.0.0` vẫn giữ nguyên.

### 5.2. Thư mục gốc của archive

Khi có:

~~~xml
<includeBaseDirectory>true</includeBaseDirectory>
~~~

và không đặt `baseDirectory` riêng, plugin dùng mặc định `${project.build.finalName}` làm tên thư mục root, ví dụ `assembly-demo-1.0.0`. Do đó trong ZIP sẽ thấy:

~~~text
assembly-demo-1.0.0/README.txt
assembly-demo-1.0.0/bin/run.sh
assembly-demo-1.0.0/lib/assembly-demo-1.0.0.jar
~~~

Điều này giúp giải nén không làm rải `bin`/`lib` trực tiếp vào thư mục hiện tại. Với `includeBaseDirectory=false`, các file có thể ở root archive; chỉ dùng khi hệ thống nhận file yêu cầu cách đóng gói ấy.

### 5.3. ZIP, TAR, TAR.GZ

Trong descriptor có thể liệt kê:

~~~xml
<formats>
    <format>zip</format>
    <format>tar</format>
    <format>tar.gz</format>
</formats>
~~~

- `zip`: thường thân thiện với Windows và công cụ nén phổ biến.
- `tar`: archive Unix không nén.
- `tar.gz`: TAR được gzip nén, phổ biến với hệ Linux/macOS.
- `tar.bz2`, `tar.xz` và một số format khác được plugin hỗ trợ khi thực sự cần.

Bài thực hành tạo **ZIP và TAR.GZ**; nếu thêm `tar`, plugin tạo thêm `assembly-demo-1.0.0-dist.tar`. Khi kiểm tra file TAR không nén, dùng `tar -tf`; với TAR.GZ dùng `tar -tzf`. Nên kiểm tra khả năng giải nén ở các nền tảng thực tế trước khi chốt release format.

## 6. fileSets, files và dependencySets khác nhau thế nào?

### 6.1. fileSets: lấy files từ một thư mục

~~~xml
<fileSet>
    <directory>${project.basedir}/src/dist/bin</directory>
    <outputDirectory>bin</outputDirectory>
    <includes>
        <include>run.sh</include>
        <include>run.cmd</include>
    </includes>
    <fileMode>0755</fileMode>
</fileSet>
~~~

`directory` là đường dẫn **nguồn**. `outputDirectory` là vị trí **bên trong archive**. `includes/excludes` quy định file được chọn. `fileMode` là quyền dạng octal kiểu Unix, ví dụ `0755` để script có quyền thực thi phù hợp khi archive/unpack tool bảo toàn metadata.

### 6.2. files: một file riêng, có thể đổi tên

~~~xml
<files>
    <file>
        <source>${project.basedir}/src/dist/README.txt</source>
        <outputDirectory></outputDirectory>
        <destName>INSTALL.txt</destName>
        <fileMode>0644</fileMode>
    </file>
</files>
~~~

Đây là **trích đoạn minh họa**, không thuộc descriptor chính. Nếu thêm nó, `README.txt` được chép dưới tên `INSTALL.txt`. Nếu fileSet khác vẫn chép README, bạn có thể có **hai bản** trong archive.

### 6.3. dependencySets: dựa vào Maven dependency graph

~~~xml
<dependencySets>
    <dependencySet>
        <outputDirectory>lib</outputDirectory>
        <scope>runtime</scope>
        <useProjectArtifact>false</useProjectArtifact>
        <useProjectAttachments>false</useProjectAttachments>
        <useTransitiveDependencies>true</useTransitiveDependencies>
        <unpack>false</unpack>
    </dependencySet>
</dependencySets>
~~~

- `scope=runtime`: lấy dependencies cần ở runtime classpath (phù hợp với compile/runtime), không lấy JUnit test-only.
- `useProjectArtifact=false`: không tự thêm main project JAR vào dependencySet, vì ví dụ copy nó bằng fileSet riêng.
- `useProjectAttachments=false`: không tự đưa attached archives của project vào `lib`.
- `useTransitiveDependencies=true`: gồm transitives phù hợp khi một library cần library khác.
- `unpack=false`: giữ từng dependency JAR riêng, không giải nén classes vào cùng thư mục.

Nếu đặt `useProjectArtifact=true` trong dependencySet **đồng thời** dùng fileSet copy JAR chính đến cùng đường dẫn, có nguy cơ trùng entry. Chọn một cơ chế nhất quán cho artifact chính.

**Không hardcode đường dẫn `~/.m2/repository` để copy dependencies.** Maven Resolver đã biết chính xác version/classifier/scope và local repository có thể khác nhau trên máy dev, Windows và CI.

### 6.4. Runtime vs test dependencies

Trong project mẫu:

~~~text
commons-lang3:3.14.0  -> dependency compile/runtime -> cần trong lib/
junit-jupiter:5.11.4  -> dependency test            -> không cần trong lib/
~~~

Đóng một JAR `junit-jupiter` vào bản phân phối runtime chỉ vì “thư viện đã tải về” là sai phạm vi. Nó làm tăng dung lượng, license surface và sự phức tạp classpath. Dùng `scope=runtime` và kiểm tra archive thật.

## 7. Dự án Java 17 hoàn chỉnh

Tạo các file dưới thư mục `assembly-demo`:

~~~text
assembly-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/assembly/App.java
    ├── test/java/vn/example/assembly/AppTest.java
    ├── assembly/distribution.xml
    └── dist/
        ├── README.txt
        └── bin/
            ├── run.sh
            └── run.cmd
~~~

Có **7 file** cần tạo: POM, App.java, AppTest.java, distribution.xml, README.txt, run.sh và run.cmd. Không tạo `target` thủ công; Maven sẽ sinh output khi build.

Yêu cầu môi trường: Maven **3.9.x**, JDK **17+**, khả năng tải Commons Lang, JUnit và plugin từ Maven repositories/mirror đã cấu hình.

### 7.1. pom.xml — cấu hình hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>assembly-demo</artifactId>
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
            <version>5.11.4</version>
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
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.assembly.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-assembly-plugin</artifactId>
                <version>3.8.0</version>
                <configuration>
                    <descriptors>
                        <descriptor>src/assembly/distribution.xml</descriptor>
                    </descriptors>
                    <appendAssemblyId>true</appendAssemblyId>
                    <attach>true</attach>
                </configuration>
                <executions>
                    <execution>
                        <id>build-distribution</id>
                        <phase>package</phase>
                        <goals>
                            <goal>single</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích thiết kế:

- `maven.compiler.release=17` yêu cầu bytecode/API Java 17.
- `commons-lang3` là **runtime dependency thật**, được App gọi trực tiếp.
- JUnit Jupiter chỉ scope `test`; Surefire chạy các bài kiểm thử trước khi package.
- JAR Plugin tạo binary JAR có manifest `Main-Class` nhưng không tự gom dependency Commons Lang.
- Assembly Plugin 3.8.0 bind `single` vào `package`, lấy cấu trúc gói từ descriptor.
- `appendAssemblyId=true` giữ hậu tố `dist`; `attach=true` đăng ký archive phụ để install/deploy theo lifecycle.

### 7.2. src/main/java/vn/example/assembly/App.java

~~~java
package vn.example.assembly;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message(String subject) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }

        String normalized = subject.trim().toLowerCase(Locale.ROOT);
        return "Maven Assembly: " + StringUtils.capitalize(normalized);
    }

    public static void main(String[] args) {
        System.out.println(message("  distribution  "));
    }
}
~~~

App gọi `StringUtils.capitalize`, không chỉ import mà không sử dụng. Hàm `toLowerCase(Locale.ROOT)` khiến kết quả không phụ thuộc default locale của máy. Stdout **chính xác** khi app chạy với runtime classpath đầy đủ:

~~~text
Maven Assembly: Distribution
~~~

### 7.3. src/test/java/vn/example/assembly/AppTest.java

~~~java
package vn.example.assembly;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsDistributionName() {
        assertEquals(
                "Maven Assembly: Distribution",
                App.message("  distribution  ")
        );
    }

    @Test
    void normalizesCase() {
        assertEquals(
                "Maven Assembly: Hello world",
                App.message("  HELLO WORLD  ")
        );
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> App.message("   ")
        );
    }
}
~~~

Với Maven Surefire/JUnit Jupiter đã khai, dự kiến **3 tests PASS**, 0 failures/errors. Những test classes và JUnit test dependency không cần xuất hiện trong `lib` của distribution.

## 8. Descriptor hoàn chỉnh: src/assembly/distribution.xml

~~~xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
                              https://maven.apache.org/xsd/assembly-2.2.0.xsd">

    <id>dist</id>
    <formats>
        <format>zip</format>
        <format>tar.gz</format>
    </formats>

    <includeBaseDirectory>true</includeBaseDirectory>

    <fileSets>
        <fileSet>
            <directory>${project.build.directory}</directory>
            <outputDirectory>lib</outputDirectory>
            <includes>
                <include>${project.build.finalName}.jar</include>
            </includes>
            <fileMode>0644</fileMode>
        </fileSet>

        <fileSet>
            <directory>${project.basedir}/src/dist/bin</directory>
            <outputDirectory>bin</outputDirectory>
            <includes>
                <include>run.sh</include>
                <include>run.cmd</include>
            </includes>
            <fileMode>0755</fileMode>
        </fileSet>

        <fileSet>
            <directory>${project.basedir}/src/dist</directory>
            <outputDirectory></outputDirectory>
            <includes>
                <include>README.txt</include>
            </includes>
            <fileMode>0644</fileMode>
        </fileSet>
    </fileSets>

    <dependencySets>
        <dependencySet>
            <outputDirectory>lib</outputDirectory>
            <scope>runtime</scope>
            <useProjectArtifact>false</useProjectArtifact>
            <useProjectAttachments>false</useProjectAttachments>
            <useTransitiveDependencies>true</useTransitiveDependencies>
            <unpack>false</unpack>
        </dependencySet>
    </dependencySets>
</assembly>
~~~

Đây là descriptor **runnable**, không phải XML minh họa thiếu mục. Cả ZIP và TAR.GZ có chung danh sách file, nhưng khác container format.

### 8.1. Kiểm tra từng nguồn vào archive

1. fileSet đầu đọc `target/assembly-demo-1.0.0.jar` và đặt ở `lib/`.
2. fileSet thứ hai đọc `src/dist/bin/run.sh` và `run.cmd`, đặt ở `bin/`. Quyền `0755` phù hợp Unix executable script; quyền khôi phục từ ZIP phụ thuộc unpack tool.
3. fileSet thứ ba đọc `src/dist/README.txt`, đặt ở thư mục root trong archive.
4. dependencySet lấy Commons Lang 3 qua Maven dependency resolution và đặt ở `lib/`, không unpack. `useProjectArtifact=false` tránh thêm main JAR lần hai.
5. Vì `scope=runtime`, JUnit `test` dependency không được chọn để đi theo ứng dụng.

### 8.2. Không sao chép toàn bộ target

**Sai cách** là khai một fileSet sao chép mọi thứ từ `${project.build.directory}` không giới hạn. Nó có thể đưa cả test reports, source output, JAR cũ hoặc chính archive được tạo vào archive; gói có thể phình to và mất ổn định.

Đúng cách là dùng:

~~~xml
<includes>
    <include>${project.build.finalName}.jar</include>
</includes>
~~~

để chọn đúng binary JAR. Tương tự, không chép cả thư mục project rồi lọc bằng danh sách exclude rất dài; nên **allowlist** những file được phép phát hành.

## 9. Script Linux/macOS: src/dist/bin/run.sh

~~~sh
#!/usr/bin/env sh
set -eu

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

exec java -cp "$APP_HOME/lib/*" vn.example.assembly.App "$@"
~~~

Giải thích:

- `#!/usr/bin/env sh` sử dụng shell Unix-like.
- `set -eu` giúp dừng khi command lỗi hoặc biến chưa khai (trong các trường hợp shell áp dụng).
- Script tự tính `APP_HOME` là thư mục cha của `bin`, không phụ thuộc người dùng đứng ở đâu khi chạy.
- `"$APP_HOME/lib/*"` được chuyển như một classpath argument; Java launcher xử lý wildcard các JAR trực tiếp trong `lib`.
- `"$@"` chuyển arguments cho main; ví dụ hiện không dùng arguments.
- `exec` thay process shell bằng Java process và giữ exit status.

Script chỉ yêu cầu Java 17+ runtime có sẵn trên PATH. Nó không tự cài Java hay Maven.

### 9.1. Tại sao không hardcode đường dẫn tuyệt đối?

Nếu script ghi `/home/dev/build/target/...`, file phát hành không chạy được trên máy người nhận. Tính path dựa vào vị trí script làm distribution **portable** khi giải nén vào một thư mục bất kỳ, miễn đường dẫn có quyền đọc.

### 9.2. Tại sao phải quote classpath?

Dấu nháy bảo toàn classpath argument nếu đường dẫn có dấu cách. Nếu shell tự mở rộng `*` trước khi gửi tới Java, argument có thể bị chia thành nhiều tên file; đặt `"$APP_HOME/lib/*"` giúp Java launcher chịu trách nhiệm tìm các JAR.

Wildcard `lib/*` không tự tìm mọi JAR trong thư mục con của `lib`. Với descriptor mẫu, các JAR nằm trực tiếp trong `lib` nên lệnh đúng.

## 10. Script Windows: src/dist/bin/run.cmd

~~~bat
@echo off
setlocal
set "APP_HOME=%~dp0.."
java -cp "%APP_HOME%\lib\*" vn.example.assembly.App %*
exit /b %ERRORLEVEL%
~~~

- `%~dp0` là thư mục chứa batch script.
- `..` đưa về root distribution.
- `lib\*` là classpath wildcard cho JAR ứng dụng và Commons Lang.
- `%*` chuyển arguments từ batch script.
- `exit /b %ERRORLEVEL%` trả exit code Java cho caller.

Đây là file CMD/batch, **không phải** PowerShell `.ps1`. Người dùng vẫn có thể gọi `run.cmd` từ PowerShell. Không nên viết một script Bash rồi chỉ đổi extension thành `.cmd` vì cú pháp không tương thích.

## 11. README: src/dist/README.txt

~~~text
Maven Assembly Demo 1.0.0

Requires Java 17 or newer on PATH.

Contents:
  bin/run.sh   Unix-like launcher
  bin/run.cmd  Windows CMD launcher
  lib/*.jar    Application JAR and runtime dependencies

Linux/macOS:
  sh bin/run.sh

Windows CMD:
  bin\run.cmd

Expected output:
  Maven Assembly: Distribution

This archive is a folder distribution, not a native installer.
Do not copy only the application JAR: it requires the other JARs
in the lib directory.
~~~

Đây là plain-text README hoàn chỉnh cho demo. Một release sản phẩm thật còn cần license/notice, hướng dẫn cài JDK, cách cấu hình, đường dẫn logs, phương án upgrade/rollback, support và checksum nếu chính sách yêu cầu.

Không đưa passwords, API keys, credentials hoặc private service endpoints vào README/script/descriptor.

## 12. Build và kiểm tra các file thật

Tại thư mục `assembly-demo`:

~~~bash
java -version
mvn -version
mvn clean package
~~~

Kết quả mong đợi trong lifecycle:

~~~text
compile        -> App.class
test-compile   -> AppTest.class
test           -> 3 JUnit tests PASS
package        -> maven-jar-plugin:jar
package        -> maven-assembly-plugin:single
                   -> ZIP distribution
                   -> TAR.GZ distribution
BUILD SUCCESS
~~~

Dòng trên là **sơ đồ**, không phải log Maven nguyên văn. Thư mục `target` sẽ có các file trọng tâm:

~~~text
target/
├── assembly-demo-1.0.0.jar
├── assembly-demo-1.0.0-dist.zip
├── assembly-demo-1.0.0-dist.tar.gz
├── classes/vn/example/assembly/App.class
├── test-classes/vn/example/assembly/AppTest.class
└── surefire-reports/
    └── TEST-vn.example.assembly.AppTest.xml
~~~

Maven có thể sinh thêm metadata/build output. Không coi cây này là danh sách duy nhất của mọi file bên trong `target`.

### 12.1. Xem ZIP bằng JDK jar tool

~~~bash
jar tf target/assembly-demo-1.0.0-dist.zip
~~~

Các entry quan trọng:

~~~text
assembly-demo-1.0.0/README.txt
assembly-demo-1.0.0/bin/run.sh
assembly-demo-1.0.0/bin/run.cmd
assembly-demo-1.0.0/lib/assembly-demo-1.0.0.jar
assembly-demo-1.0.0/lib/commons-lang3-3.14.0.jar
~~~

`jar tf` có thể liệt kê ZIP vì JAR là archive dựa trên ZIP. Output thực tế có thể bao gồm directory entries và thứ tự khác; nội dung/đường dẫn logic mới là tiêu chí kiểm chứng.

**Không nên có** JUnit `junit-jupiter` trong `lib` vì nó là test-only dependency. Trong dự án lớn, vẫn cần kiểm tra toàn bộ libs do transitive dependencies hoặc profiles có thể ảnh hưởng.

### 12.2. Xem TAR.GZ

Trên môi trường có tar:

~~~bash
tar -tzf target/assembly-demo-1.0.0-dist.tar.gz
~~~

Cấu trúc logic phải tương đương ZIP. Tool tar có thể hiển thị tiền tố đường dẫn hoặc folder entries khác công cụ ZIP. Đừng đòi hai danh sách text byte-for-byte giống nhau.

Nếu thêm `<format>tar</format>` vào descriptor, lệnh kiểm tra TAR không nén là:

~~~bash
tar -tf target/assembly-demo-1.0.0-dist.tar
~~~

Không dùng option gzip `-z` với TAR không nén.

### 12.3. Xem binary JAR

~~~bash
jar tf target/assembly-demo-1.0.0.jar
~~~

Các mục quan trọng thường có:

~~~text
META-INF/MANIFEST.MF
vn/example/assembly/App.class
~~~

Binary JAR **không bắt buộc chứa `StringUtils.class`**, vì Commons Lang được đặt trong JAR riêng ở `lib` distribution. Điều đó đúng với thiết kế không dùng Shade.

## 13. Giải nén và chạy ZIP trên Linux/macOS

~~~bash
mkdir -p target/unpacked
unzip target/assembly-demo-1.0.0-dist.zip -d target/unpacked
sh target/unpacked/assembly-demo-1.0.0/bin/run.sh
~~~

Stdout chính xác:

~~~text
Maven Assembly: Distribution
~~~

Script tự định vị `lib`; người dùng không phải `cd` đến root trước khi chạy. `unzip` là công cụ hệ điều hành, không thuộc Maven/JDK; cần cài sẵn khi làm bước này.

Nếu không có unzip, có thể dùng những công cụ ZIP khác tương thích để giải nén vào một thư mục sạch, sau đó chạy script tương tự.

## 14. Giải TAR.GZ và chạy trên Linux/macOS

~~~bash
mkdir -p target/unpacked-tar
tar -xzf target/assembly-demo-1.0.0-dist.tar.gz -C target/unpacked-tar
sh target/unpacked-tar/assembly-demo-1.0.0/bin/run.sh
~~~

Stdout:

~~~text
Maven Assembly: Distribution
~~~

Điều này kiểm tra **nội dung thực tế của gói TAR.GZ**, thay vì chỉ thấy Maven tạo tên file có đuôi `tar.gz`.

### 14.1. Quyền thực thi của script

Descriptor đặt `fileMode=0755` cho fileSet `bin`. TAR có thể giữ quyền file kiểu Unix; ZIP và công cụ giải nén trên nhiều nền tảng không nhất thiết khôi phục execute bit giống nhau. Vì vậy bài dùng `sh .../run.sh`, không phụ thuộc script có execute bit.

Trong sản phẩm thật, nếu muốn chạy `./bin/run.sh`, kiểm tra chmod/permission **sau giải nén bằng đúng công cụ người dùng sẽ dùng**.

## 15. Giải ZIP trên Windows PowerShell

~~~powershell
Expand-Archive -LiteralPath '.\target\assembly-demo-1.0.0-dist.zip' -DestinationPath '.\target\unpacked' -Force
& '.\target\unpacked\assembly-demo-1.0.0\bin\run.cmd'
~~~

Stdout:

~~~text
Maven Assembly: Distribution
~~~

`Expand-Archive` là PowerShell cmdlet; `&` gọi CMD script. Khi dùng Windows CMD trực tiếp, người dùng có thể vào distribution root rồi chạy `bin\run.cmd`.

Nếu script không tìm thấy Java, kiểm tra `java -version` trong **terminal đó**. JDK/Maven có trên máy build không bảo đảm runtime Java đã được cài trên máy nhận bản phân phối.

### 15.1. Smoke test không nên phụ thuộc Maven classpath

Để kiểm tra bằng Java trực tiếp, từ root project sau khi giải nén:

~~~bash
java -cp "target/unpacked/assembly-demo-1.0.0/lib/*" vn.example.assembly.App
~~~

Stdout phải như trên. Nếu lệnh này chạy được còn script fail, lỗi nhiều khả năng nằm ở cách script tính đường dẫn hoặc quoting. Nếu cả hai fail vì `StringUtils` không tìm thấy, hãy kiểm tra dependencySet và nội dung `lib`.

Một test chỉ gọi `mvn test` **không chứng minh** gói phân phối đủ libraries; Maven đã tự cung cấp dependency trên test classpath.

## 16. Assembly attach vào Maven install/deploy như thế nào?

Assembly Plugin 3.8.0 có các tùy chọn:

~~~xml
<appendAssemblyId>true</appendAssemblyId>
<attach>true</attach>
~~~

Cả hai mặc định true, nhưng POM mẫu khai tường minh để dễ học.

- `appendAssemblyId=true` giữ `-dist` trong tên output và classifier khi attach.
- `attach=true` đăng ký generated archives là Maven **attached artifacts** của project.

Lệnh:

~~~bash
mvn clean install
~~~

chạy qua `package` rồi `install`. Trong cùng một Maven invocation, Assembly goal tạo ZIP/TAR.GZ trước; Install Plugin có thể đưa artifact chính và attached archives vào local repository. Với local repo mặc định:

~~~text
~/.m2/repository/vn/example/assembly-demo/1.0.0/
├── assembly-demo-1.0.0.pom
├── assembly-demo-1.0.0.jar
├── assembly-demo-1.0.0-dist.zip
└── assembly-demo-1.0.0-dist.tar.gz
~~~

Thư mục có thể có thêm metadata/checksum và vị trí local repo có thể bị settings thay đổi. **Chỉ có file ZIP ở `target` chưa chứng minh nó đã được attach/install.** Cần kiểm tra output của đúng lần `install` và file tại repository tương ứng version.

### 16.1. Classifier không phải packaging chính

Biểu diễn tọa độ logic:

~~~text
vn.example:assembly-demo:1.0.0:jar
vn.example:assembly-demo:1.0.0:zip:dist
vn.example:assembly-demo:1.0.0:tar.gz:dist
~~~

Hai artifact phụ có classifier `dist` và extension/type khác nhau. Chúng không phải dependency Java thông thường cần thêm vào `compile` classpath.

### 16.2. Cẩn thận với appendAssemblyId=false

Nếu ghi:

~~~xml
<appendAssemblyId>false</appendAssemblyId>
~~~

plugin bỏ assembly ID khỏi tên và không tạo classifier như thông thường. Khi assembly có **cùng format với packaging chính**, kết quả có thể cạnh tranh/thay thế artifact chính. Với ZIP/TAR distribution, vẫn nên giữ `true` để phân biệt archive và tránh xung đột metadata.

### 16.3. Không cần deploy thật trong bài thực hành

~~~bash
mvn clean deploy
~~~

chạy lifecycle đến `deploy` và có thể xuất bản attached artifacts nếu project/repository đã cấu hình. Không chạy lệnh này vào repository tổ chức/Maven Central chỉ để thử, vì việc publish có thể tạo artifact tồn tại lâu dài và đòi credentials/quyền phù hợp.

## 17. Các lỗi thường gặp với fileSets

### 17.1. Chép cả thư mục target

Một fileSet không giới hạn từ `${project.build.directory}` có thể đưa vào archive: JAR cũ, Surefire reports, build intermediates, generated sources, thậm chí archive đang được tạo. Cách đúng là **định nghĩa allowlist**, ví dụ chỉ `${project.build.finalName}.jar`.

### 17.2. Sai outputDirectory

`outputDirectory` là đường dẫn tương đối **trong archive**. Nếu đặt thành `/absolute/path/on/ci/agent` một cách máy móc, nó không có ý nghĩa là copy file tới thư mục máy người dùng lúc giải nén. Hãy dùng tên đích rõ như `bin`, `lib`, `conf`, `docs`.

### 17.3. Chọn file bằng includes quá rộng

Pattern `**/*` dưới project root có thể đưa cả POM, source, build caches, test data, `.env` hoặc secret vào gói. Kiểm tra descriptor và nội dung archive trước khi publish; ưu tiên liệt kê trực tiếp những file hợp lệ.

### 17.4. Không phân biệt fileMode và directoryMode

`fileMode=0755` điều khiển metadata quyền của file trong một fileSet; `directoryMode` có mục đích riêng cho directories. Không nên gán executable bit cho mọi JAR/README. Quyền metadata trong archive không thay thế filesystem/ACL policy của máy người dùng.

## 18. Các lỗi thường gặp với dependencySets

### 18.1. Thiếu Commons Lang tại runtime

Nếu bỏ dependencySet, `mvn test` có thể vẫn PASS vì Maven có Commons Lang trên test/compile classpath. Nhưng distribution chỉ còn app JAR; khi chạy `App.message`, có thể báo `NoClassDefFoundError: org/apache/commons/lang3/StringUtils`.

**Cách sửa:** kiểm tra `mvn dependency:tree`, descriptor `dependencySets` và các JAR trong `lib`, không cố thêm thư viện vào main class một cách thủ công.

### 18.2. Đưa nhầm JUnit vào runtime archive

Nếu dependencySet scope quá rộng hoặc fileSet copy từ cache toàn bộ, `lib` có thể chứa JUnit dù ứng dụng không cần. Đặt `scope=runtime` và kiểm tra archive; đừng dùng `scope=test` cho gói người dùng cuối nếu không có lý do đặc biệt.

### 18.3. Duplicated project artifact

`useProjectArtifact` mặc định true trong dependencySet. Trong mẫu này ta **chủ động đặt false** vì main JAR đã được fileSet thêm vào `lib`. Nếu để true, có thể đưa project JAR vào archive hai lần hoặc tạo entry conflict. Chọn một cơ chế duy nhất.

### 18.4. Sai tên JAR

DependencySet sử dụng filename mapping của plugin. Khi có artifacts cùng artifactId/version classifier, cần đảm bảo mapping tạo tên duy nhất. Với dự án phức tạp, xem `outputFileNameMapping` để tránh collision trong `lib`; việc đổi tên file trong archive có thể yêu cầu sửa script/classpath nếu không dùng wildcard.

## 19. ZIP/TAR khác nhau ngoài extension

| Vấn đề | ZIP | TAR | TAR.GZ |
| --- | --- | --- | --- |
| Cấu trúc | Các entries trong ZIP | TAR entries | TAR entries được gzip nén |
| Dung lượng | Nén theo ZIP | Không nén | Nén gzip |
| Tool thường dùng | `unzip`, `jar tf`, PowerShell Expand-Archive | `tar -tf` | `tar -tzf` |
| Unix permissions | Phụ thuộc archiver/unpacker | Có metadata kiểu Unix | Tương tự TAR |
| Người dùng mục tiêu | Phổ biến trên Windows | Unix/tooling | Linux/macOS/Unix |

Archive ZIP và TAR.GZ có thể chứa cùng nội dung logic nhưng bytes, headers và metadata khác nhau. Không đòi hai checksum giống nhau. Nên tạo checksum **riêng từng file**, giải nén vào thư mục sạch và chạy smoke test.

### 19.1. Long file paths trong TAR

Assembly Plugin có tham số `tarLongFileMode`, cho phép các chế độ như `warn`, `fail`, `gnu`, `posix`. Khi distribution có nested paths dài và người nhận dùng công cụ tar hiện đại, có thể cân nhắc:

~~~xml
<tarLongFileMode>posix</tarLongFileMode>
~~~

Đây là snippet tùy chọn **trong Maven Assembly Plugin configuration**, không cần cho demo có đường dẫn ngắn. Phải kiểm tra compatibility với tool giải nén thực tế; đừng bật chỉ vì một cảnh báo chưa hiểu.

### 19.2. Line endings trong launcher

Unix shell script dùng line endings phù hợp shell; Windows CMD script thường dùng CRLF nhưng nhiều công cụ vẫn xử lý LF. Assembly descriptor có tham số `lineEnding` trên fileSet/file. Khi phát hành đa OS, có thể tách fileSets cho `run.sh` và `run.cmd` để áp dụng `unix`/`dos` tương ứng, nếu môi trường build/source control yêu cầu. Demo để nội dung từ source files giữ nguyên, với các scripts đơn giản.

**Không bật text filtering** cho binary JAR/ZIP: nó có thể phá nội dung archive.

## 20. Filtering và dữ liệu nhạy cảm

Assembly fileSet/file có tham số `filtered` để thay tokens trong **text resources** theo Maven/filter properties. Ví dụ **snippet tùy chọn, không nằm trong 7 file demo**:

~~~xml
<fileSet>
    <directory>${project.basedir}/src/dist/conf</directory>
    <outputDirectory>conf</outputDirectory>
    <includes>
        <include>application.properties</include>
    </includes>
    <filtered>true</filtered>
</fileSet>
~~~

Chỉ dùng khi nội dung file có token chủ đích và charset đúng. Không lọc images, certificates hoặc binary archives trừ khi plugin hỗ trợ/chỉ rõ loại file và quy trình đã được test.

**Không đưa secrets thật** vào files để phân phối: production DB passwords, cloud keys, API tokens, `.env`, private keys, log người dùng, internal hostnames nhạy cảm. Artifact sau khi publish có thể được cache và phân phối rất rộng. Nên dùng config templates không chứa secret; lúc deployment nhận bí mật từ CI/secret manager theo quyền hạn phù hợp.

Cũng phải review `LICENSE`, `NOTICE` và OSS license obligations của các runtime dependencies. Plugin giúp copy libraries, **không tự đảm bảo** toàn bộ yêu cầu license đã được đáp ứng.

## 21. Khi nào nên dùng Assembly và khi nào nên dùng Shade?

Bảng quyết định:

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Đóng class của project thành JAR | Maven JAR Plugin |
| Tạo distribution chứa `bin`, `lib`, `README` | Maven Assembly Plugin |
| Gộp class/deps và xử lý ServiceLoader, relocation | Maven Shade Plugin |
| Built-in JAR gộp deps đơn giản | Assembly `jar-with-dependencies` |
| Tạo runtime image kèm JDK modules | JDK `jlink` |
| Tạo bản cài đặt OS/native launcher | JDK `jpackage`/installer tools |
| Chạy trong container image | Container/OCI tooling |

Một dự án có thể kết hợp **Shade rồi Assembly**: Shade tạo uber-JAR, Assembly đóng nó cùng script và docs. Khi đó phải tránh dependency JAR bị đưa vào `lib` lần hai nếu chúng đã ở uber-JAR. Cần kiểm tra artifact thực tế được Assembly chọn và thứ tự lifecycle executions.

**Không coi Assembly và Shade là hai plugin tương đương** chỉ vì cả hai có thể tạo file `.jar`. Assembly mô tả **bộ phân phối**, Shade giải quyết **ghép class/resource**.

## 22. Multi-module và module sở hữu distribution

Một reactor có thể như sau:

~~~text
platform-parent/
├── pom.xml                 packaging=pom
├── core/
│   └── pom.xml             packaging=jar
├── cli/
│   └── pom.xml             packaging=jar
└── distribution/
    └── pom.xml             packaging=pom hoặc jar
~~~

Một distribution có thể cần các JAR của `core` và `cli`. Tuy nhiên, nếu bind Assembly Plugin execution ở parent rồi để **inherited** mặc định, goal có thể chạy ở nhiều child và sinh ra gói trùng/rỗng hoặc sai đường dẫn.

Gợi ý:

- Parent dùng `pluginManagement` để quản lý **version và cấu hình chung**, không mặc nhiên tạo output.
- Chỉ module sở hữu distribution khai/bind `assembly:single`.
- Có thể dùng `<inherited>false</inherited>` khi một execution không được truyền xuống child.
- Dùng `dependencySets` hoặc `moduleSets` để lấy artifacts từ modules, sau khi đảm bảo chúng đã được package.
- Kiểm tra `mvn help:effective-pom` của **đúng module** đang tạo distribution.
- Đảm bảo artifacts đã có trong reactor/đúng build order trước khi assemble.

Ví dụ:

~~~bash
mvn -pl :distribution -am package
~~~

`-pl` chọn module theo artifactId, `-am` build thêm modules phụ thuộc trong reactor. Nhưng nếu một module không thật sự khai dependency relationship đến module khác, `-am` không tự tạo quan hệ build hoặc đảm bảo package input đúng. Thiết kế dependencies/modules rõ và tránh Assembly execution inherited không chủ đích.

### 22.1. Dùng moduleSets khi nào?

`moduleSets` cho phép descriptor chọn project artifacts hoặc sources từ reactor. Nó hữu ích khi tạo một ZIP cấp hệ thống gồm nhiều module, nhưng cần lưu ý aggregator context, lifecycle phase và thứ tự module artifacts đã sẵn sàng. Đừng copy snippet moduleSets từ một tutorial khác mà không kiểm tra version/plugin và reactor layout thực tế.

### 22.2. Tránh dùng chung output path khi build song song

Hai module cùng ghi vào một thư mục `target/distribution` hoặc cùng tên archive có thể tranh chấp output, nhất là với parallel builds. Một module distribution chuyên trách hoặc một thư mục riêng theo module/build ID thường dễ kiểm chứng hơn.

## 23. Những tham số Assembly Plugin hay gặp

| Tham số | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `descriptors` | File XML custom | Dùng trong demo |
| `descriptorRefs` | Descriptor dựng sẵn | Dùng `bin` hoặc `src` khi đủ |
| `appendAssemblyId` | Có nối id/classifier vào output không | Giữ true cho distribution |
| `attach` | Có gắn archive vào Maven project không | True để install/deploy |
| `formats` | Các định dạng archive | Dùng khi cần thay qua profile |
| `finalName` | Prefix filename trong `target` | Không đổi Maven coordinates ở repo |
| `outputDirectory` | Nơi plugin ghi archives | Mặc định `target` |
| `skipAssembly` | Bỏ qua goal Assembly | Dùng khi dev không cần dist |
| `runOnlyAtExecutionRoot` | Điều khiển chạy ở execution root context | Cẩn thận multi-module |
| `tarLongFileMode` | Cách xử lý path dài trong TAR | Chỉ chỉnh khi cần |
| `dryRun` | Kiểm tra phần xử lý mà không tạo archive cuối | Debug cấu hình |

### 23.1. Skip assembly không skip tests

~~~bash
mvn -Dassembly.skipAssembly=true package
~~~

Trong Assembly Plugin 3.8.0, `assembly.skipAssembly` là property cho `skipAssembly`. Lệnh có thể tạo JAR chính và chạy test bình thường, nhưng không tạo ZIP/TAR distribution ở execution bị skip.

Ngược lại:

~~~bash
mvn -DskipTests package
~~~

thường vẫn tạo distribution, dù Surefire bỏ thực thi test. Không báo cáo “3 tests PASS” nếu đã dùng skip flag.

### 23.2. Goal trực tiếp có thể sử dụng file stale

~~~bash
mvn assembly:single
~~~

Goal không mặc nhiên chạy compile/test/package ở phía trước. Nếu JAR chính chưa có hoặc là output cũ, distribution có thể fail hoặc đóng nhầm version. Với demo, ưu tiên `mvn clean package` hoặc `mvn clean install` để bảo đảm lifecycle đầy đủ.

Nếu Assembly đã bind ở `package`, gọi `mvn package assembly:single` có thể khiến Assembly goal chạy **hai lần** trong cùng command; không cần thiết.

## 24. Troubleshooting có hệ thống

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `mvn package` không tạo ZIP/TAR | Không bind `single`/profile khác | Kiểm tra effective POM và log |
| Không tìm thấy descriptor | File path/XML namespace sai | Kiểm tra `src/assembly/distribution.xml` |
| Gói không có app JAR | fileSet input/include sai hoặc JAR chưa tạo | Xem `target` và package order |
| Gói không có Commons Lang | dependencySet scope/selection sai | `mvn dependency:tree`, xem `lib` |
| Có JUnit trong `lib` | Scope quá rộng hoặc copy thư mục cache | Chỉ chọn runtime dependencies |
| Chạy báo `NoClassDefFoundError` | Thiếu libs hoặc script classpath sai | Dùng `jar tf`, `java -cp "lib/*" ...` |
| `java -jar` không chạy dù có Main-Class | Binary JAR không chứa dependency | Dùng script phân phối hoặc Shade |
| Script lỗi khi cwd khác | Relative lib path không tính từ script | Tính APP_HOME từ script location |
| ZIP giải nén rải file trực tiếp | `includeBaseDirectory=false` | Chọn true khi cần root folder |
| Script mất execute bit | ZIP extraction/tool khác | Chạy `sh bin/run.sh`/phục hồi chmod |
| Có file test/log/secret trong gói | fileSet includes quá rộng | Dùng allowlist, pre-release scan |
| Archive chứa chính output ZIP/TAR | Copy cả `target` | Chỉ include main JAR |
| Tên file không có `-dist` | id hoặc `appendAssemblyId` khác | Xem descriptor/config |
| ZIP tồn tại nhưng repository không có | attach false hoặc chưa install | `mvn clean install`, kiểm tra repo |
| Version Commons Lang khác kỳ vọng | DependencyManagement/conflict | Effective POM/dependency tree |
| TAR lỗi path dài | Path limit, tar mode/tool | Xem `tarLongFileMode` |
| Multi-module tạo archive ở mọi child | Execution inherited từ parent | Bind đúng distribution module |
| Build xanh nhưng tests chưa chạy | `-DskipTests` hoặc plugin config | Xem Surefire test count |
| Không tải plugin/dependency | Maven repo/proxy/mirror | Xử lý dependency resolution trước |

### 24.1. Sáu bước điều tra

1. Ghi Maven command, Java/Maven versions, profiles và module.
2. Xem `mvn help:effective-pom` để xác minh Assembly Plugin version, execution, descriptor.
3. Kiểm tra log `maven-jar-plugin:jar` và `maven-assembly-plugin:single`, thứ tự và kết quả.
4. Đọc descriptor `id/formats/fileSets/dependencySets`, đối chiếu đường dẫn source.
5. Kiểm tra nội dung archive `jar tf`/`tar -tzf`, xác minh main JAR, runtime libs, scripts.
6. Giải nén vào thư mục sạch và chạy smoke test trên Java runtime thật.

Các lệnh hữu ích:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn clean package
jar tf target/assembly-demo-1.0.0-dist.zip
tar -tzf target/assembly-demo-1.0.0-dist.tar.gz
~~~

Nếu bật Maven debug `-X`, kiểm tra secrets/URLs nội bộ trong log trước khi chia sẻ.

## 25. CI, release và an toàn artifact

Một pipeline hợp lý có thể phân lớp:

**Build/test:** `mvn clean test` chạy JUnit tests; riêng lệnh này chưa đến package và không tạo ZIP/TAR.

**Package:** `mvn clean package` tạo main JAR và distribution archives, kiểm tra đúng file names, classifier, formats.

**Archive QA:** liệt kê entries trong ZIP/TAR, đảm bảo không chứa test-only dependencies, files ngoài allowlist, secrets hoặc artifact version cũ.

**Smoke test:** giải nén ZIP/TAR, chạy script thật với Java 17+, không dùng Maven test classpath để “vô tình” che thiếu dependencies.

**Install/staging:** kiểm tra main và attached artifacts đúng tọa độ/version. Chỉ deploy đến remote repository khi release policy cho phép và credentials đã cấu hình.

### 25.1. Reproducibility

Để tái tạo distribution, nên ghi lại revision, Maven/JDK versions, plugin versions, dependency graph, archive contents, test reports và checksums riêng cho ZIP/TAR.GZ. Metadata timestamps, file permissions và compression có thể ảnh hưởng bytes của archive; hai format **không có checksum giống nhau** ngay cả khi nội dung logic giống.

### 25.2. License và cấu hình

Bản phân phối runtime libraries có thể phát sinh nghĩa vụ license/NOTICE. Có pipeline rà soát OSS dependencies và SBOM theo policy. Không để credentials trong `.env`/config được filtered rồi đóng vào ZIP/TAR; người dùng tải archive có thể đọc nội dung, bất kể fileMode đặt gì.

## 26. Bài tập thực hành

**Bài A — Phân biệt artifact.** Giải thích sự khác nhau giữa JAR chính, `-dist.zip` và `-dist.tar.gz`. Tại sao cần Commons Lang JAR riêng?

**Bài B — Dựng dự án.** Tạo đủ 7 file mục 7–11. Chạy `mvn clean package`, xác nhận 3 JUnit tests PASS và hai archives.

**Bài C — Chọn đầu vào.** Chỉ ra fileSet nào chép main JAR, fileSet nào chép scripts, fileSet nào chép README và dependencySet nào chép Commons Lang.

**Bài D — Kiểm tra ZIP.** Dùng `jar tf ...dist.zip` để tìm `lib/commons-lang3-3.14.0.jar`. Kiểm tra không có JUnit test dependencies ngoài ý muốn.

**Bài E — Kiểm tra TAR.GZ.** Dùng `tar -tzf` và so sánh đường dẫn logic với ZIP. Vì sao format khác nhưng nội dung application cần giống nhau?

**Bài F — Smoke test.** Giải ZIP và chạy `run.sh`/`run.cmd` đúng hệ điều hành. Stdout phải chính xác `Maven Assembly: Distribution`.

**Bài G — Thiếu dependency.** Trong một bản sao bài tập, bỏ dependencySet, build lại và giải nén vào thư mục sạch. Dự đoán lỗi lúc chạy rồi khôi phục descriptor.

**Bài H — TAR không nén.** Thêm `<format>tar</format>`, build và dùng `tar -tf`. Vì sao `tar.gz` cần `-z` còn TAR thường không?

**Bài I — Bỏ thư mục root.** Thử `includeBaseDirectory=false`, kiểm tra các paths trong ZIP. So sánh ảnh hưởng đến trải nghiệm giải nén.

**Bài J — Permissions.** Đọc `fileMode=0755` của scripts và `0644` của JAR/README. Vì sao ZIP extraction trên Windows/Linux có thể xử lý quyền khác nhau?

**Bài K — Attached artifacts.** Chạy `mvn clean install` rồi tìm ZIP/TAR cùng version trong local repo. Nếu có file trong `target` nhưng không thấy trong repo, điều tra `attach` và lệnh install.

**Bài L — Assembly vs Shade.** Thiết kế thay thế khi yêu cầu chỉ một executable JAR không có `lib`, giải thích vấn đề `META-INF/services` và relocation.

**Bài M — Multi-module.** Đề xuất module sở hữu distribution cho reactor `core` + `cli`. Vì sao không bind Assembly execution mặc định cho mọi module?

**Bài N — Security review.** Một POM chép toàn bộ project root vào ZIP. Nêu file dễ lộ như `.env`, private key, logs hoặc source nội bộ và thay bằng allowlist.

**Bài O — CI gate.** Định nghĩa các bằng chứng cần thiết: 3 tests PASS, ZIP/TAR chứa libs/scripts, smoke test thành công, attached artifacts ở repository và checksum đúng.

## 27. Checklist cuối cùng

- [ ] Biết sự khác nhau giữa binary JAR, fat JAR và distribution archive.
- [ ] Chọn đúng Assembly Plugin 3.8.0 và goal `assembly:single`.
- [ ] Bind goal vào `package` sau khi main JAR có thể được tạo.
- [ ] Descriptor đúng namespace/schema, id và formats rõ ràng.
- [ ] ZIP/TAR.GZ chứa một thư mục root theo chính sách.
- [ ] fileSets chỉ copy JAR, scripts, README được phép.
- [ ] dependencySets chỉ chọn runtime libraries và không trùng project JAR.
- [ ] JUnit test-only libraries không lọt vào `lib`.
- [ ] Scripts tự tìm đường dẫn `lib` từ vị trí chính chúng.
- [ ] Quyền thực thi và line endings được kiểm tra trên nền tảng nhận.
- [ ] `mvn clean package` chạy đủ tests và tạo mọi archive.
- [ ] `jar tf` / `tar -tzf` xác nhận cấu trúc thực tế.
- [ ] Smoke test chạy từ archive đã giải nén, không dựa vào Maven classpath.
- [ ] `mvn clean install` xác nhận ZIP/TAR được attach đúng version.
- [ ] Không lộ secret, logs, test reports hoặc file source ngoài chính sách.
- [ ] License, NOTICE, checksums và SBOM được xử lý theo release policy.
- [ ] Với multi-module, distribution có module owner rõ và không tạo archive trùng.

**Kết luận:** Maven Assembly Plugin mô tả **đóng gói file nào, vào thư mục nào, với định dạng nào**. `fileSets` chọn các file từ workspace, `dependencySets` chọn thư viện runtime theo Maven dependency graph, còn `assembly:single` tại `package` tạo ZIP/TAR. Một bộ phân phối chỉ đạt yêu cầu khi **giải nén được, tìm đủ dependency, chạy đúng trên runtime mục tiêu và không chứa dữ liệu ngoài phạm vi phát hành**.

## 28. Tài liệu chính thức

- [Apache Maven Assembly Plugin — Introduction](https://maven.apache.org/plugins/maven-assembly-plugin/): mục đích plugin và goal chính.
- [Apache Maven Assembly Plugin 3.8.0 — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html): `descriptorRefs`/`descriptors`, `single` và phase package.
- [Apache Maven Assembly Plugin — assembly:single](https://maven.apache.org/plugins/maven-assembly-plugin/single-mojo.html): parameters `attach`, `appendAssemblyId`, `skipAssembly`, `formats`, `tarLongFileMode`.
- [Apache Maven Assembly Plugin — Assembly Descriptor Format](https://maven.apache.org/plugins/maven-assembly-plugin/assembly.html): `id`, `fileSets`, `files`, `dependencySets`, `moduleSets`.
- [Apache Maven Assembly Plugin — Predefined Assembly Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html): `bin`, `jar-with-dependencies`, `src`, `project`.
- [Apache Maven Assembly Plugin — Including and Excluding Artifacts](https://maven.apache.org/plugins/maven-assembly-plugin/examples/single/including-and-excluding-artifacts.html): dependency inclusion/exclusion, `useProjectArtifact`.
- [Apache Maven Assembly Plugin — Multimodule Examples](https://maven.apache.org/plugins/maven-assembly-plugin/examples/multimodule/index.html): reactor modules và distribution.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package/install/deploy.
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): Maven dependency scopes và transitive libraries.
- [Java SE 17 — java Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): classpath wildcard và JVM options.
