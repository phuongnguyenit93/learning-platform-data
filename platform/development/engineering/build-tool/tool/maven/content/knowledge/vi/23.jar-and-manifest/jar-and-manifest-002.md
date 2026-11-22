# Cấu trúc JAR và kiểm tra các lớp, tài nguyên được đóng gói

## 1. Học được gì từ một file JAR?

Sau khi chạy `mvn package`, một project Java thường tạo file `target/<artifactId>-<version>.jar`. Việc Maven báo `BUILD SUCCESS` **không tự chứng minh** JAR ấy chứa đúng class, tài nguyên, manifest hay dependency mà ứng dụng cần để chạy.

Những câu hỏi nên trả lời trước khi phát hành:

- File `demo/archive/App.class` có thực sự nằm trong JAR không?
- `src/main/resources/config/app.properties` được đóng dưới đường dẫn `config/app.properties` hay nằm nhầm chỗ?
- JAR có `META-INF/MANIFEST.MF` và `Main-Class` đúng cho `java -jar` không?
- Test classes, test fixtures, file bí mật và dữ liệu chỉ dùng khi phát triển có lọt vào artifact không?
- JAR được build là **plain JAR** hay một loại fat/uber JAR, Spring Boot executable JAR, modular JAR?
- Nếu mã chạy trong IDE nhưng fail khi dùng JAR, cần kiểm tra **đường dẫn tài nguyên**, **runtime classpath** hay **binary compatibility**?
- Có thể chuyển các câu hỏi ấy thành một bước tự động fail build ở phase `verify` không?

Bài này trả lời bằng kiến thức cấu trúc JAR, lệnh JDK, Maven Resources/JAR Plugins, Java `JarFile` API và một dự án **Java 17+ có thể biên dịch, chạy và tự kiểm tra JAR cuối**.

## 2. JAR là một archive dựa trên ZIP

**JAR (Java ARchive)** là định dạng gói dựa trên ZIP, chứa những **entries** với tên là đường dẫn tương đối tính từ gốc archive. JAR có thể lưu:

- Bytecode Java: `*.class`.
- Tài nguyên: `*.properties`, `*.xml`, `*.json`, text, ảnh và file khác.
- Manifest: `META-INF/MANIFEST.MF`.
- Metadata Maven: thường có `META-INF/maven/<groupId>/<artifactId>/pom.xml` và `pom.properties`.
- Metadata service provider: `META-INF/services/...` nếu dùng `ServiceLoader`.
- Entry cho multi-release JAR: `META-INF/versions/<N>/...` khi có cấu hình thích hợp.
- Metadata liên quan chữ ký JAR: một số file dưới `META-INF/` như `*.SF`, `*.RSA` hoặc `*.EC` nếu JAR được ký.

Không phải mọi JAR đều có đủ những nhóm trên. Một **library JAR** có thể không có `Main-Class`; một executable JAR có thể có; một plain JAR cũng không tự chứa tất cả dependencies.

Một cấu trúc minh họa:

~~~text
example.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/
│       └── demo.archive/
│           └── example/
│               ├── pom.xml
│               └── pom.properties
├── demo/
│   └── archive/
│       ├── App.class
│       └── Helper.class
├── config/
│   └── app.properties
└── docs/
    └── readme.txt
~~~

Đây là sơ đồ **minh họa**, không phải output cố định của mọi phiên bản Maven plugin. File JAR cũng có thể chứa các entry chỉ biểu thị thư mục như `META-INF/` hoặc `demo/`.

## 3. Java package và JAR entry là hai cách viết của cùng một vị trí

Một Java class:

~~~java
package demo.archive;

public final class App {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

có tên Java đầy đủ là `demo.archive.App`. Nếu biên dịch bằng cấu hình Maven chuẩn, các vị trí tương ứng là:

| Vai trò | Giá trị |
| --- | --- |
| Source Java | `src/main/java/demo/archive/App.java` |
| Java binary name | `demo.archive.App` |
| Output compiler | `target/classes/demo/archive/App.class` |
| Entry trong main JAR | `demo/archive/App.class` |

**Không** tìm `demo.archive.App.class`, `src/main/java/demo/archive/App.java` hoặc `target/classes/demo/archive/App.class` như tên entry trong archive. JAR lưu đường dẫn tương đối từ classes directory.

Tên entry có phân biệt chữ hoa/chữ thường. `demo/archive/App.class` và `demo/archive/app.class` là hai tên khác nhau. Dấu phân cách trong ZIP/JAR entry là `/`, kể cả khi filesystem Windows thể hiện bằng `\`.

### Những class file được compiler sinh thêm

Java compiler có thể tạo `Outer$Nested.class`, `Outer$1.class` hoặc những file `$...class` từ nested/anonymous classes. Một source file Java không bắt buộc sinh đúng một `.class`. Khi kiểm tra class API/binary, sử dụng `javap` thay vì đếm file.

## 4. Tài nguyên trong JAR đi qua Maven Resources Plugin

Đường đi tiêu chuẩn:

~~~text
src/main/resources/config/app.properties
                  |
                  v
process-resources: resources:resources
                  |
                  v
target/classes/config/app.properties
                  |
                  v
package: jar:jar
                  |
                  v
JAR entry: config/app.properties
~~~

Trong project Maven Java thông thường:

- `src/main/java` là mã Java chính, biên dịch thành `target/classes`.
- `src/main/resources` cung cấp **main resources**, thường được copy/filter vào `target/classes`.
- `src/test/java` biên dịch thành `target/test-classes`.
- `src/test/resources` cung cấp **test resources**, thường copy vào `target/test-classes`.
- Maven JAR Plugin mặc định lấy nội dung từ `${project.build.outputDirectory}`, thường là `target/classes`, chứ không lấy cả `target/test-classes`.

Vì vậy, `src/main/resources/config/app.properties` trở thành `config/app.properties` ở **gốc classpath/JAR**, không mang prefix `src/main/resources/`.

**Cảnh báo quan trọng:** Nếu unit test đọc được `fixtures/sample.txt` từ `src/test/resources` thì **không có nghĩa** resource này nằm trong main JAR. Surefire dùng test classpath, vốn khác classpath khi triển khai một JAR ứng dụng.

## 5. Phân biệt library JAR, executable JAR và fat JAR

| Loại | Mục đích | Điểm cần kiểm tra |
| --- | --- | --- |
| **Plain library JAR** | Được dependency khác sử dụng qua classpath | Class/resource/API đúng; không cần `Main-Class` |
| **Plain executable JAR** | Có thể chạy `java -jar` nếu đủ runtime dependencies | `Main-Class`, main class, resources, classpath |
| **Uber/fat JAR** | Gộp code project và nhiều dependencies | Resource merging, duplicate classes, service descriptors |
| **Spring Boot executable JAR** | Dùng loader/bố cục chuyên biệt | `BOOT-INF/classes`, `BOOT-INF/lib`, launcher, manifest |
| **Modular JAR** | Mang Java module descriptor | `module-info.class` và module exports/requires |
| **Multi-release JAR** | Có class/resource biến thể theo JDK version | `Multi-Release: true`, `META-INF/versions/<N>` |

Một plain JAR mặc định do Maven JAR Plugin tạo **không tự biến các dependency JAR thành nội dung trong archive**. Maven có thể tải dependency để compile/test nhưng khi chạy ngoài Maven vẫn phải cung cấp runtime classpath đúng.

Với library JAR, việc thiếu `Main-Class` **không phải lỗi**. Với executable JAR yêu cầu chạy bằng `java -jar`, thiếu attribute này có thể là lỗi cấu hình manifest.

## 6. Ví dụ Java 17 hoàn chỉnh để kiểm tra đóng gói

Ta tạo một project có:

1. `App.java` là ứng dụng chạy bằng `java -jar`.
2. `ArchiveInspector.java` dùng JDK `JarFile` API kiểm tra entries và manifest.
3. `config/app.properties` và `docs/readme.txt` là **main resources**.
4. `AppTest.java` dùng JUnit Jupiter; `fixtures/sample.txt` là **test resource**.
5. Maven Exec Plugin chạy `ArchiveInspector` ở phase `verify` để kiểm tra **artifact đã package**, không chỉ thư mục output.

Cấu trúc trước build:

~~~text
jar-structure-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/archive/
    │   │       ├── App.java
    │   │       └── ArchiveInspector.java
    │   └── resources/
    │       ├── config/app.properties
    │       └── docs/readme.txt
    └── test/
        ├── java/demo/archive/AppTest.java
        └── resources/fixtures/sample.txt
~~~

**Giới hạn của ví dụ:** Vì `ArchiveInspector.java` đặt trong `src/main/java` để dễ chạy và không cần build một module khác, bản thân class kiểm tra này **cũng sẽ nằm trong main JAR**. Ở sản phẩm thật, có thể chuyển verifier sang plugin hoặc project kiểm thử artifact riêng.

### 6.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.archive</groupId>
    <artifactId>jar-structure-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
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
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>demo.archive.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>verify-jar-entries</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>java</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <mainClass>demo.archive.ArchiveInspector</mainClass>
                    <classpathScope>runtime</classpathScope>
                    <arguments>
                        <argument>${project.build.directory}/${project.build.finalName}.jar</argument>
                    </arguments>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các điểm đáng chú ý:

- Packaging `jar` khiến Maven bind `jar:jar` tại phase `package` trong default lifecycle.
- Resources Plugin chuẩn bị main/test resources. Compiler Plugin biên dịch Java 17. Surefire chạy JUnit tests.
- JAR Plugin ghi `Main-Class: demo.archive.App` vào manifest.
- Exec Plugin gắn `exec:java` tại `verify`, **sau phase `package`**, và truyền đường dẫn JAR vừa tạo cho chương trình kiểm tra.
- Nếu verifier phát hiện thiếu class/resource hoặc manifest sai rồi ném exception, Maven build có thể kết thúc `BUILD FAILURE`, chặn artifact không đạt yêu cầu.
- `project.build.outputTimestamp` là một input của tính năng reproducible archive trong công cụ Maven hỗ trợ; nó không tự bảo đảm mọi byte trong JAR cố định nếu nội dung build khác nhau.
- Các plugin/version được pin cho bài học, không phải một lời khẳng định rằng chúng là bản mới nhất mãi mãi.

### 6.2. `src/main/resources/config/app.properties`

~~~properties
name=jar-lab
mode=plain
~~~

### 6.3. `src/main/resources/docs/readme.txt`

~~~text
This file belongs to the application JAR.
~~~

### 6.4. `src/test/resources/fixtures/sample.txt`

~~~text
fixture-ok
~~~

**Phân loại:** Hai file đầu là **main resources**, phải xuất hiện trong JAR. File `fixtures/sample.txt` là **test resource**, chỉ nên xuất hiện trong test output ở demo này.

### 6.5. `src/main/java/demo/archive/App.java`

~~~java
package demo.archive;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String readProperty(String key) throws IOException {
        Properties values = new Properties();

        try (InputStream input =
                App.class.getResourceAsStream("/config/app.properties")) {
            if (input == null) {
                throw new IOException("Resource not found: config/app.properties");
            }
            values.load(input);
        }

        String value = values.getProperty(key);
        if (value == null) {
            throw new IOException("Property not found: " + key);
        }
        return value;
    }

    public static void main(String[] args) throws IOException {
        System.out.println("name=" + readProperty("name"));
        System.out.println("mode=" + readProperty("mode"));
    }
}
~~~

**Vì sao dùng `getResourceAsStream`?**

Đường dẫn `/config/app.properties` tính từ classpath root. Khi ứng dụng chạy từ JAR, JVM có thể đọc entry bên trong archive trực tiếp mà không phải extract toàn bộ JAR.

Cách không nên dùng cho resource được đóng gói:

~~~java
new java.io.File("src/main/resources/config/app.properties");
~~~

Đường dẫn trên phụ thuộc source tree ở máy phát triển. Bản deploy có thể chỉ có JAR và hoàn toàn không có `src/main/resources`.

Với hai giá trị ASCII trong ví dụ, `Properties.load(InputStream)` là phù hợp. Nếu muốn dùng file properties UTF-8 có ký tự tiếng Việt, cần chủ động chọn `Properties.load(Reader)` cùng `InputStreamReader(input, StandardCharsets.UTF_8)`; đừng giả định mọi phiên bản/hình thức API tự xử lý UTF-8 giống nhau.

### 6.6. `src/test/java/demo/archive/AppTest.java`

~~~java
package demo.archive;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void readsMainResource() throws IOException {
        assertEquals("jar-lab", App.readProperty("name"));
        assertEquals("plain", App.readProperty("mode"));
    }

    @Test
    void readsTestFixture() throws IOException {
        try (InputStream input =
                AppTest.class.getResourceAsStream("/fixtures/sample.txt")) {
            assertNotNull(input);
            String value = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
            assertEquals("fixture-ok", value);
        }
    }
}
~~~

**Điều hai test này chứng minh:** main resource và test fixture được tìm thấy trên **test runtime classpath**. Chúng chưa chứng minh main JAR chứa resource đúng hoặc không chứa test fixture. Vì vậy cần bước kiểm tra artifact thực ở `verify`.

### 6.7. `src/main/java/demo/archive/ArchiveInspector.java`

~~~java
package demo.archive;

import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArchiveInspector {
    private ArchiveInspector() {
    }

    private static void requireEntry(JarFile jar, String name) {
        boolean present = jar.getJarEntry(name) != null;
        System.out.println(name + "=" + present);

        if (!present) {
            throw new IllegalStateException("Missing JAR entry: " + name);
        }
    }

    private static void rejectEntry(JarFile jar, String name) {
        boolean present = jar.getJarEntry(name) != null;
        System.out.println(name + "=" + present);

        if (present) {
            throw new IllegalStateException("Unexpected JAR entry: " + name);
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArchiveInspector <path-to-jar>");
        }

        Path path = Path.of(args[0]);

        try (JarFile jar = new JarFile(path.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing MANIFEST.MF");
            }

            String mainClass = manifest.getMainAttributes()
                    .getValue(Attributes.Name.MAIN_CLASS);
            System.out.println("main=" + mainClass);

            if (!"demo.archive.App".equals(mainClass)) {
                throw new IllegalStateException(
                        "Wrong Main-Class: " + mainClass);
            }

            requireEntry(jar, "demo/archive/App.class");
            requireEntry(jar, "demo/archive/ArchiveInspector.class");
            requireEntry(jar, "config/app.properties");
            requireEntry(jar, "docs/readme.txt");

            rejectEntry(jar, "demo/archive/AppTest.class");
            rejectEntry(jar, "fixtures/sample.txt");

            System.out.println("audit=PASS");
        }
    }
}
~~~

Chương trình kiểm tra chính các **entry names của JAR artifact**, thay vì kiểm tra thư mục `target/classes`. Nó sử dụng những API Java 17 tiêu chuẩn:

- `JarFile` mở archive.
- `JarFile.getManifest()` lấy manifest nếu có.
- `Manifest.getMainAttributes()` lấy main attributes.
- `JarFile.getJarEntry("path")` trả entry nếu có hoặc `null` nếu vắng mặt.
- `try-with-resources` đóng file handle khi kết thúc, nhất là quan trọng trên Windows.

Phần audit này chỉ kiểm tra **tồn tại/không tồn tại** của entries và `Main-Class`. Nó không kiểm tra chữ ký, nội dung resource, toàn bộ binary dependencies, vulnerability hay behavior runtime. Những gate đó có thể được bổ sung theo nhu cầu.

## 7. Chạy build chuẩn và so kết quả

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -version
mvn -B -ntp clean verify
~~~

Luồng chính:

~~~text
clean
  └── xóa target cũ
process-resources
  └── copy config/app.properties và docs/readme.txt
compile
  └── tạo App.class và ArchiveInspector.class
process-test-resources
  └── copy fixtures/sample.txt vào target/test-classes
test-compile
  └── biên dịch AppTest.class
test
  └── Surefire/JUnit: 2 test PASS
package
  └── jar:jar tạo target/jar-structure-lab-1.0.0.jar
verify
  └── exec:java (verify-jar-entries) kiểm tra JAR
~~~

Đây là **sơ đồ các goal quan trọng**, không phải toàn bộ log Maven. Với các file đã mô tả và môi trường Maven/JDK phù hợp, test và audit có thể PASS.

**Stdout dự kiến của ArchiveInspector bên trong log Maven:**

~~~text
main=demo.archive.App
demo/archive/App.class=true
demo/archive/ArchiveInspector.class=true
config/app.properties=true
docs/readme.txt=true
demo/archive/AppTest.class=false
fixtures/sample.txt=false
audit=PASS
~~~

Đừng hiểu các dòng này là nội dung của `App.main`. Đây là chương trình **kiểm tra cấu trúc JAR** in ra. Sau build, chạy riêng ứng dụng:

~~~bash
java -jar target/jar-structure-lab-1.0.0.jar
~~~

**Stdout chính xác của App.main:**

~~~text
name=jar-lab
mode=plain
~~~

Ứng dụng demo không có dependency runtime bên ngoài Java standard library. JUnit chỉ có scope `test` và Maven plugins không phải Java runtime dependencies cần để chạy `App.main`.

### Vì sao chọn verify, không chỉ package?

~~~bash
mvn -B -ntp clean package
~~~

đã tạo JAR nhưng **không đi tới phase `verify`**, nên execution `verify-jar-entries` của ví dụ chưa chạy. Nếu packaging audit là quality gate bắt buộc trước khi publish, pipeline nên chạy ít nhất `mvn clean verify` (cùng những checks khác phù hợp).

## 8. Liệt kê JAR entries bằng jar tf

JDK có công cụ `jar`. Hai cú pháp có chức năng liệt kê tương đương:

~~~bash
jar tf target/jar-structure-lab-1.0.0.jar
jar --list --file target/jar-structure-lab-1.0.0.jar
~~~

Trong cú pháp `jar tf`:

- `t` yêu cầu **table/list**.
- `f` chỉ định archive được đọc từ file.
- Lệnh chỉ liệt kê entries, không chạy chương trình.

Một trích đoạn kết quả có thể là:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/archive/
demo/archive/App.class
demo/archive/ArchiveInspector.class
config/
config/app.properties
docs/
docs/readme.txt
...
~~~

Dấu `...` là ký hiệu rút gọn cho những entries bổ sung có thể tồn tại, **không phải một entry thật**. Maven Archiver có thể thêm metadata dưới `META-INF/maven/...`.

Bạn cần tìm chính xác:

~~~text
demo/archive/App.class
config/app.properties
docs/readme.txt
~~~

Và mong đợi **không** có trong main JAR:

~~~text
demo/archive/AppTest.class
fixtures/sample.txt
~~~

Các file test lại có thể có trong `target/test-classes`; sự vắng mặt của chúng trong main artifact là đúng.

### Lọc entries khi output dài

Linux/macOS:

~~~bash
jar tf target/jar-structure-lab-1.0.0.jar | grep 'demo/archive/'
jar tf target/jar-structure-lab-1.0.0.jar | grep 'config/app.properties'
~~~

Windows PowerShell:

~~~powershell
jar tf target/jar-structure-lab-1.0.0.jar |
    Select-String 'demo/archive/'
~~~

Khi viết kiểm tra tự động, dùng **exact entry names** thay vì chỉ tìm một substring mơ hồ: `App.class` có thể xuất hiện dưới nhiều packages hoặc tên gần giống.

## 9. Giải nén JAR để đọc manifest hoặc resource

Nếu cần kiểm tra bytes nội dung và archive đã tin cậy:

~~~bash
mkdir inspected-jar
cd inspected-jar
jar --extract --file ../target/jar-structure-lab-1.0.0.jar
~~~

Sau đó có thể mở:

~~~text
META-INF/MANIFEST.MF
config/app.properties
docs/readme.txt
~~~

Linux/macOS:

~~~bash
cat META-INF/MANIFEST.MF
cat config/app.properties
~~~

PowerShell:

~~~powershell
Get-Content META-INF/MANIFEST.MF
Get-Content config/app.properties
~~~

**An toàn:** Chỉ giải nén JAR tin cậy vào **thư mục trống được kiểm soát**; không extract một archive không tin cậy vào thư mục chứa file quan trọng. Đừng sửa nội dung đã extract rồi nghĩ mình đã sửa JAR gốc. Muốn sửa ứng dụng, sửa nguồn/resource configuration và build lại.

Nếu mục tiêu chỉ là xem danh sách entries, ưu tiên `jar tf` vì không cần tạo file mới.

## 10. Manifest và vai trò của Main-Class

Đường dẫn chuẩn:

~~~text
META-INF/MANIFEST.MF
~~~

Phần cơ bản của manifest executable JAR có thể là:

~~~text
Manifest-Version: 1.0
Main-Class: demo.archive.App
~~~

Manifest có thể có attributes khác do Maven Archiver/plugin version ghi vào. Thứ tự fields và line endings không nên được hard-code như một hợp đồng nếu không có yêu cầu cụ thể.

`Main-Class` là tên Java class đầy đủ, **dùng dấu chấm**, không phải entry path:

~~~text
Main-Class: demo.archive.App
~~~

Đúng; còn giá trị sau không phù hợp:

~~~text
Main-Class: demo/archive/App.class
~~~

Khi chạy `java -jar file.jar`, JVM đọc manifest để tìm entry point. Khi thư viện chỉ được thêm vào classpath của một ứng dụng khác, manifest **không nhất thiết cần Main-Class**.

Trong POM demo, JAR Plugin cấu hình:

~~~xml
<archive>
    <manifest>
        <mainClass>demo.archive.App</mainClass>
    </manifest>
</archive>
~~~

Đây là **đoạn cấu hình con của plugin**, không phải POM độc lập.

### Lỗi thiếu Main-Class

Nếu JAR là executable theo thiết kế nhưng không có manifest entry point, khi gọi `java -jar` có thể gặp thông điệp dạng:

~~~text
no main manifest attribute, in target/jar-structure-lab-1.0.0.jar
~~~

Lúc đó cần kiểm tra Maven JAR Plugin `archive.manifest.mainClass`, manifest bị post-process thay đổi hoặc bạn đang chạy nhầm artifact. Không mặc định thêm Main-Class cho mọi library JAR.

### Manifest metadata không thay thế classpath

- `Manifest-Version` là version của định dạng manifest.
- `Main-Class` chỉ định runtime entry point.
- `Implementation-Version` có thể chứa version implementation.
- `Class-Path` có thể tham chiếu relative JARs theo manifest classpath rules.
- `Multi-Release` dùng cho cấu trúc multi-release JAR.

Một `Class-Path: lib/helper.jar` **không có nghĩa** `helper.jar` đã được nhúng vào main JAR; nó là một tham chiếu theo runtime/distribution layout phù hợp.

## 11. Quan sát class binary bằng javap

`jar tf` chỉ thấy **tên entry**. Muốn xem chữ ký phương thức và binary details:

~~~bash
javap -classpath target/jar-structure-lab-1.0.0.jar demo.archive.App
javap -classpath target/jar-structure-lab-1.0.0.jar demo.archive.ArchiveInspector
~~~

Trong `javap`, tham số cuối là **Java binary class name** có dấu chấm; không phải archive path.

Các tùy chọn hữu ích:

~~~bash
javap -classpath target/jar-structure-lab-1.0.0.jar -public demo.archive.App
javap -classpath target/jar-structure-lab-1.0.0.jar -s demo.archive.App
javap -classpath target/jar-structure-lab-1.0.0.jar -verbose demo.archive.App
~~~

- `-public` xem public API.
- `-s` xem JVM type descriptors.
- `-verbose` xem major/minor bytecode version, constant pool và thông tin class file chi tiết.

`javap` không phải source-code decompiler hoàn chỉnh. Nó giúp đối chiếu API/class version khi `NoSuchMethodError`, `NoClassDefFoundError`, `UnsupportedClassVersionError` hoặc mismatch runtime xuất hiện.

## 12. Classpath resource và đường dẫn tìm kiếm

Hai biểu thức có ý nghĩa khác nhau về dấu `/`:

~~~java
App.class.getResourceAsStream("/config/app.properties");
~~~

và:

~~~java
App.class.getClassLoader()
        .getResourceAsStream("config/app.properties");
~~~

Với `Class.getResourceAsStream`, dấu `/` đầu trỏ từ classpath root. Không có dấu `/` đầu, đường dẫn sẽ được giải quyết **tương đối với package của class**.

Ví dụ từ `demo.archive.App`:

~~~java
App.class.getResourceAsStream("config/app.properties");
~~~

có thể tìm `demo/archive/config/app.properties`, không phải `config/app.properties`. Nếu JAR chỉ chứa entry `config/app.properties`, kết quả là `null`.

Với `ClassLoader.getResourceAsStream`, đường dẫn được truyền thường **không** có dấu `/` đầu.

Một số resource URLs có dạng:

~~~text
jar:file:/path/to/app.jar!/config/app.properties
~~~

Đây là URL ví dụ, không phải file path thật. Đừng tự chuyển resource URL từ JAR thành `new File(url.getPath())`: entry nằm **bên trong archive**. Dùng `getResourceAsStream` hoặc các API JAR/ZIP phù hợp.

## 13. Vì sao test thấy resource còn ứng dụng sau deploy không thấy?

Maven có hai output directories quan trọng:

~~~text
target/classes/        compiled main classes + main resources
target/test-classes/   compiled test classes + test resources
~~~

Test classpath của Surefire thường gồm cả hai directories và các dependencies trong test scope. Main JAR mặc định lấy classes/resources chính ở `target/classes`.

Trong ví dụ:

- `AppTest.readsTestFixture` thành công vì `fixtures/sample.txt` có mặt trên test classpath.
- `java -jar ...` không nên dựa vào `fixtures/sample.txt`, vì entry đó không nằm trong main JAR.
- `App.main` đọc `config/app.properties` vì đó là main resource.

Nếu một resource cần cho production mà đang nằm ở `src/test/resources`, hãy đặt nó vào `src/main/resources` hoặc thiết kế packaging riêng có chủ đích. Không nên giải quyết bằng việc package toàn bộ test files vào JAR chính.

## 14. Maven JAR Plugin đóng gói dữ liệu từ đâu?

Maven JAR Plugin có goal `jar:jar`, được bind vào phase `package` cho packaging `jar` theo lifecycle mapping thông dụng.

Hai parameters:

- `classesDirectory` mặc định là `${project.build.outputDirectory}`, thường `target/classes`.
- `outputDirectory` mặc định là `${project.build.directory}`, thường `target`.

Trong demo, artifact tên:

~~~text
target/jar-structure-lab-1.0.0.jar
~~~

Nếu đặt `<finalName>`, classifiers hoặc tạo nhiều attached artifacts, tên file có thể khác. Khi kiểm tra một build release, **phải xác định chính xác artifact nào được upload/deploy** trước khi audit.

### Includes và excludes

Một đoạn POM minh họa bên trong Maven JAR Plugin:

~~~xml
<configuration>
    <excludes>
        <exclude>docs/draft-*.txt</exclude>
    </excludes>
</configuration>
~~~

Pattern ở đây tính tương đối từ `classesDirectory`, **không** phải từ `src/main/resources`. Khi một file bị loại bởi JAR Plugin, nó có thể vẫn tồn tại trong `target/classes`, nhưng không có trong JAR.

Vì vậy:

- Có file trong source **chưa chứng minh** Resources Plugin copy nó.
- Có file trong `target/classes` **chưa chứng minh** Maven JAR Plugin đóng nó.
- Chỉ đọc **JAR artifact** mới xác nhận nội dung cuối.

## 15. Thử cố ý loại resource để kiểm tra gate verify

Trong `maven-jar-plugin` của demo, tạm thêm:

~~~xml
<excludes>
    <exclude>docs/readme.txt</exclude>
</excludes>
~~~

Rồi chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Kết quả kỳ vọng:

1. Maven vẫn biên dịch Java và chạy JUnit tests thành công.
2. Maven JAR Plugin loại `docs/readme.txt` khỏi archive.
3. `ArchiveInspector` đọc artifact, in `docs/readme.txt=false` và ném `IllegalStateException`.
4. Exec Plugin làm build `FAILURE` tại phase `verify`.

Đây là **bài thử âm có chủ đích**, không phải cấu hình khuyến nghị cho JAR thật. Khôi phục POM gốc sau bài thử.

Điểm cần học: nếu một resource là hợp đồng của artifact, **unit tests dùng output classes chưa đủ** để kiểm tra nó có thực sự được package.

## 16. Resource filtering có thể thay nội dung JAR

Resources Plugin hỗ trợ thay placeholder trong tài nguyên khi bật filtering. Ví dụ file nguồn:

~~~properties
app.version=@project.version@
~~~

với cấu hình minh họa:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
</build>
~~~

Đây là đoạn **minh họa riêng**, không có trong demo runnable ở trên. Nếu cấu hình filtering và delimiters phù hợp, `@project.version@` có thể được thay bằng version của POM trong output dưới `target/classes`, rồi được đóng vào JAR.

**Cẩn thận với file nhị phân:** không bật filtering cho tất cả images, keystores hoặc JARs; có thể gây hỏng bytes. Trong dự án thật, nên chọn resource groups/file patterns phù hợp và xác định encoding.

Khi cần chẩn đoán resource “bị sửa trong JAR”:

1. Đọc resource nguồn.
2. Đọc bản `target/classes` sau processing.
3. Đọc entry tương ứng trong JAR.
4. Nếu khác ngoài dự kiến, xem Maven Resources Plugin filtering, include/exclude/overwrite và plugin post-processing.

Không nhầm biến đổi trong output với việc Maven tự sửa file nguồn.

## 17. Plain JAR không tự nhúng mọi Maven dependency

Giả sử project có:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Maven có thể resolve Commons Lang để ứng dụng biên dịch và test. Nhưng Maven JAR Plugin thường tạo JAR từ **compiled project classes/resources**; nó không tự copy tất cả dependency class files vào main JAR.

Hệ quả:

- `mvn package` có thể PASS.
- `jar tf app.jar` không có Commons Lang classes.
- `java -jar app.jar` có thể gặp `NoClassDefFoundError` nếu runtime không cung cấp Commons Lang đúng cách.

Có các hướng phân phối:

- Giao main JAR cùng dependency JARs và startup classpath rõ ràng.
- Dùng manifest `Class-Path` trỏ relative paths tới external libraries theo đúng layout.
- Dùng Maven Shade Plugin (uber JAR) khi yêu cầu một archive chứa nhiều dependencies.
- Dùng packaging/launcher phù hợp của framework, như Spring Boot executable JAR.

**Không nhầm Maven dependency resolution với đóng gói dependency vào cùng một ZIP.** Đây là hai bước riêng.

### Khác nhau giữa java -cp và java -jar

Cách gọi class trực tiếp:

~~~bash
java -cp target/jar-structure-lab-1.0.0.jar demo.archive.App
~~~

không đòi hỏi manifest phải có `Main-Class` vì tên class được cung cấp tường minh.

Cách gọi:

~~~bash
java -jar target/jar-structure-lab-1.0.0.jar
~~~

dùng manifest entry point. Không đặt một `-cp` tùy ý cạnh `-jar` rồi mặc định nó được dùng làm user classpath như khi không có `-jar`; đọc đúng Java launcher semantics và distribution strategy.

## 18. Spring Boot, fat JAR và multi-release: không audit nhầm cấu trúc

Bố cục một Spring Boot executable JAR có thể là:

~~~text
BOOT-INF/
├── classes/demo/archive/App.class
└── lib/
    └── dependency.jar
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
~~~

Đây là **sơ đồ minh họa**, thay đổi tùy phiên bản Boot/packaging. Nếu test bắt buộc tìm `demo/archive/App.class` tại root, nó có thể báo sai với artifact dùng loader riêng. Phải **phân loại packaging** trước khi chọn expected entries.

Một multi-release JAR có thể có:

~~~text
com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
~~~

và manifest `Multi-Release: true`. Khi runtime chọn variant, cần xét Java version. `jar tf` liệt kê các entries vật lý nhưng không tự mô phỏng đầy đủ quyết định class loading của runtime.

Một modular JAR có thể chứa `module-info.class`; với `jar --describe-module --file ...`, JDK có thể hiện module descriptor hoặc thông tin automatic module tùy JAR. Demo ở mục 6 là non-modular JAR.

## 19. META-INF/maven, ServiceLoader và chữ ký

Maven-created JAR thường có metadata dưới:

~~~text
META-INF/maven/demo.archive/jar-structure-lab/pom.xml
META-INF/maven/demo.archive/jar-structure-lab/pom.properties
~~~

`pom.properties` có thể chứa:

~~~properties
groupId=demo.archive
artifactId=jar-structure-lab
version=1.0.0
~~~

Các entry này hỗ trợ nhận diện Maven coordinates, nhưng không thay thế `Main-Class`, binary class version hoặc runtime classpath.

Nếu dùng `java.util.ServiceLoader`, Java tìm file:

~~~text
META-INF/services/<fully-qualified-service-interface>
~~~

với danh sách implementation classes. Khi tạo uber JAR, merge ServiceLoader metadata có thể cần resource transformer phù hợp; chỉ ghép class files có thể bỏ mất provider declarations.

Nếu JAR có chữ ký, các entries dưới `META-INF` có thể có phần `*.SF` và certificate/signature files. Công cụ `jarsigner -verify` phục vụ kiểm tra chữ ký; **có manifest không đồng nghĩa JAR đã được ký**.

## 20. Dùng JarFile để kiểm tra nội dung entry thực tế

`JarFile.getJarEntry(name)` chỉ kiểm tra một entry tồn tại. Nếu muốn **đọc nội dung resource thực trong JAR**, có thể dùng:

~~~java
try (JarFile jar = new JarFile("app.jar")) {
    var entry = jar.getJarEntry("config/app.properties");
    if (entry == null) {
        throw new IllegalStateException("Missing resource");
    }
    try (var in = jar.getInputStream(entry)) {
        byte[] bytes = in.readAllBytes();
        System.out.println(bytes.length);
    }
}
~~~

Đây là **mảnh code minh họa** đặt trong một ngữ cảnh có import `java.util.jar.JarFile` và file `app.jar` hợp lệ, không phải phần chạy trong demo ở mục 6. Với archive không tin cậy hoặc entry rất lớn, không nên đọc toàn bộ bytes vào RAM mà không đặt giới hạn; dùng stream và giới hạn kích thước phù hợp.

Nếu cần kiểm tra dữ liệu JSON/properties, dùng parser tương ứng trên bytes entry, không kiểm tra bằng string substring mơ hồ. Đừng quên case sensitivity của entry path.

## 21. Lệnh kiểm tra JDK ngoài jar

Các công cụ bổ sung:

| Công cụ | Công việc | Không thể chứng minh |
| --- | --- | --- |
| `jar tf` / `jar --list` | Liệt kê entries | Class load/runtime behavior đúng |
| `jar xf` / `jar --extract` | Giải nén | Build có đúng dependencies |
| `javap` | Xem class API/descriptors/bytecode details | Source code hoàn chỉnh |
| `jdeps` | Phân tích static dependencies | Mọi dependency qua reflection/dynamic loading |
| `jarsigner -verify` | Kiểm tra JAR signature khi có signing | Business logic an toàn |
| `java -jar` | Chạy theo manifest entry point | Archive có đúng mọi expected test policies |
| `JarFile` API | Kiểm tra manifest và archive entries bằng Java | Security, licensing hay dependency vulnerabilities |

Ví dụ:

~~~bash
jdeps target/jar-structure-lab-1.0.0.jar
jar --describe-module --file target/jar-structure-lab-1.0.0.jar
javap -classpath target/jar-structure-lab-1.0.0.jar -verbose demo.archive.App
~~~

Khi kiểm tra binary compatibility, `javap -s` còn hiển thị JVM descriptors hữu ích đối với lỗi `NoSuchMethodError`. Tuy nhiên `javap` không chạy class để chứng minh mọi code path hoạt động.

## 22. Vì sao clean build hữu ích khi kiểm tra archive?

Một file cũ trong `target` có thể làm bạn đọc nhầm kết quả. Ví dụ:

- Class đã xóa khỏi source nhưng class file cũ còn dưới `target/classes`.
- Resource đã chuyển đường dẫn nhưng bản cũ chưa được dọn.
- JAR Plugin phát hiện input không đổi và không tái tạo JAR, trong khi plugin khác vừa post-process artifact.
- Pipeline upload nhầm file từ một lần build trước.
- Developer kiểm tra JAR có classifier khác với artifact deploy thật.

Để chẩn đoán:

~~~bash
mvn -B -ntp clean verify
~~~

Lệnh này giúp giảm ảnh hưởng của stale files. Không phải mọi lần build đều phải clean, nhưng **clean build là chuẩn kiểm tra tốt** cho bài thực hành artifact và nhiều quy trình release.

Nếu Maven JAR Plugin có tương tác đặc biệt với plugin post-process như Shade, có tham số `forceCreation` trong JAR Plugin để cưỡng bức tạo lại JAR. Chỉ cấu hình khi hiểu nguyên nhân thực tế; không bật mù quáng để che execution-order bug.

## 23. Reproducible JAR và timestamp entries

Hai JAR có cùng class names/resources chưa chắc có cùng SHA-256, vì:

- Timestamp ZIP entries khác.
- Byte order hoặc thứ tự entries khác.
- Manifest/build metadata ghi thời gian/username/machine khác.
- Resource filtering nhúng environment-specific value.
- Compiler/JDK/plugin versions khác.
- Generated sources không deterministic.

Trong POM ví dụ:

~~~xml
<project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
~~~

Maven JAR Plugin/Archiver hỗ trợ dùng timestamp này cho archive entries. Đây là **một thành phần** của reproducible builds, không phải cam kết tự động mọi bytes sẽ giống nhau.

Trên Linux/macOS có thể tính hash:

~~~bash
sha256sum target/jar-structure-lab-1.0.0.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 target/jar-structure-lab-1.0.0.jar
~~~

Muốn so sánh hai build, phải cùng commit/inputs, toolchain, plugin version và điều kiện build phù hợp. Một checksum khác không đủ để kết luận artifact sai nếu đầu vào đã khác.

## 24. Khi gặp lỗi ClassNotFoundException hoặc NoClassDefFoundError

Một quy trình hợp lý:

1. Đọc class name và **cause chain** trong stack trace.
2. Nếu class thuộc chính project, kiểm tra `target/classes/<package-path>.class`.
3. Dùng `jar tf` xác minh class entry có trong **JAR đang chạy**.
4. Nếu có entry, dùng `javap -classpath ...` xác minh binary name/method signatures/bytecode version.
5. Nếu class thuộc third-party library, kiểm tra dependency graph và **runtime classpath/distribution**, không chỉ JAR chính.
6. Kiểm tra version JDK chạy và `UnsupportedClassVersionError` nếu có.
7. Với manifest, kiểm tra đúng `Main-Class` và loader strategy.
8. Với Spring Boot/uber JAR, xem layout và plugin đóng gói tương ứng.
9. Rebuild từ clean rồi chạy **đúng artifact mới**, không chạy một file copy cũ ở thư mục deploy.

**Phân biệt:** `ClassNotFoundException` thường phát sinh khi một cơ chế yêu cầu tìm class bằng tên; `NoClassDefFoundError` là lỗi linkage/definition khi runtime không định nghĩa được một class cần thiết. Cả hai đều có thể liên quan classpath, nhưng không mặc nhiên có cùng root cause.

## 25. Khi resource có trong JAR nhưng ứng dụng báo thiếu

Kiểm tra theo tầng:

| Tầng | Câu hỏi |
| --- | --- |
| Source | File có đúng `src/main/resources/config/app.properties`? |
| Processing | File có trong `target/classes/config/app.properties` sau `process-resources`? |
| Packaging | `jar tf` có entry `config/app.properties`? |
| Lookup | Code dùng `getResourceAsStream("/config/app.properties")` hay đường dẫn tương đối sai? |
| ClassLoader | Runtime có nạp class/JAR đúng theo packaging strategy? |
| Artifact | Có đang chạy đúng file JAR/version/classifier của lần build hiện tại? |
| Content | Nếu file được filter, bytes/value có đúng kỳ vọng? |

Nếu thiếu ngay ở `target/classes`, tìm lỗi ở Resources Plugin/configuration. Nếu `target/classes` có nhưng JAR không có, tìm lỗi ở JAR Plugin/excludes/post-processing. Nếu entry tồn tại mà Java trả `null`, tập trung vào resource lookup path/class loader.

## 26. Những sai lầm phổ biến

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “Có `BUILD SUCCESS` tức JAR đủ mọi tài nguyên.” | Build có thể chưa có artifact audit; packaging rules có thể loại resource |
| “Có file trong `target/classes` là JAR chắc chắn chứa.” | JAR Plugin có `includes/excludes` và classesDirectory |
| “JAR chứa nguyên đường dẫn `src/main/java`.” | JAR chứa entry tương đối từ compiled classes directory |
| “Mọi JAR phải có `Main-Class`.” | Library JAR không nhất thiết executable |
| “Main-Class tự nhúng dependencies.” | Manifest không làm plain JAR thành fat JAR |
| “Test có thể đọc fixture thì JAR runtime cũng đọc được.” | Test resources thường thuộc `target/test-classes` |
| “Resource từ JAR nên đọc bằng `new File`.” | Dùng classpath/resource stream APIs |
| “`jar tf` chứng minh class ABI/runtime hợp lệ.” | Chỉ liệt kê entry names; cần `javap`/runtime tests |
| “JAR không có `.java` là lỗi.” | Main JAR thường phân phối `.class`, sources JAR là artifact khác |
| “META-INF/maven chứng minh JAR runnable.” | Maven metadata không thay thế `Main-Class` |
| “Spring Boot JAR phải có class ở root như JAR thường.” | BOOT-INF layout khác |
| “Có manifest nghĩa là JAR đã ký.” | Signing là quy trình khác; dùng jarsigner |
| “Artifact audit chỉ kiểm tra những file phải có.” | Còn cần kiểm tra file không được phép đóng gói |
| “Cứ extract archive không tin cậy vào project là được.” | Có rủi ro ghi đè/tạo file nguy hiểm; cần isolation |
| “Maven package và verify giống nhau.” | Custom audit ở `verify` không chạy khi chỉ đến `package` |

## 27. Tình huống thực tế và cách ra quyết định

### 27.1. Ứng dụng chạy trong IDE nhưng báo resource not found khi dùng JAR

Ưu tiên `jar tf` và kiểm tra `getResourceAsStream` path. Nếu resource không nằm trong archive, kiểm tra Resources Plugin và JAR Plugin. Không sửa bằng cách hard-code đường dẫn source tree.

### 27.2. JAR chạy local nhưng fail khi deploy lên server

Kiểm tra JDK version, manifest, runtime dependencies, packaging layout, file paths và biến môi trường. Main JAR không tự chứa dependencies; nếu dùng script deployment, đối chiếu đúng file JAR được copy.

### 27.3. CI xanh nhưng phát hành JAR thiếu file license

Viết archive gate ở `verify`, đọc **JAR cuối** và fail khi thiếu license. Đừng chỉ kiểm tra license file ở Git repo. Khi plugin packaging có classifier, audit đúng artifact phát hành.

### 27.4. JAR vô tình chứa test fixtures hoặc secrets

Tìm nguyên nhân tại resource placement và includes/excludes. Chuyển test fixture sang `src/test/resources`. Với secrets, **không lưu trong resources/project** và dùng secret manager/runtime injection theo chính sách tổ chức; không chỉ đưa vào exclude list rồi coi như rủi ro đã được xử lý.

### 27.5. Hai bản JAR cùng code nhưng checksum khác

So toolchain, timestamp, metadata, resource filtering và nội dung generated files. Dùng reproducible build configuration và kiểm tra bytes/entries thay vì chỉ tên JAR.

### 27.6. Một JAR có nhiều class cùng tên

Có thể do shading, duplicate resources hoặc multiple dependencies. Kiểm tra packaging plugin và Maven dependency mediation; đừng giả định tên entry tồn tại là class loader chắc chắn chọn đúng implementation.

## 28. Bài tập tự kiểm tra có đáp án

1. **Class `demo.archive.App` thường có entry name gì?**  
   **Đáp án:** `demo/archive/App.class`.

2. **Vì sao không thấy `src/main/java/demo/archive/App.java` trong main JAR?**  
   **Đáp án:** Main JAR thông thường chứa compiled `.class`, không tự chứa source `.java`.

3. **Resource `src/main/resources/config/app.properties` thường có entry name gì?**  
   **Đáp án:** `config/app.properties`.

4. **Resource trong `src/test/resources` có đi vào main JAR theo mặc định?**  
   **Đáp án:** Không; thường đi vào `target/test-classes`.

5. **Lệnh JDK liệt kê JAR entries?**  
   **Đáp án:** `jar tf file.jar` hoặc `jar --list --file file.jar`.

6. **File manifest nằm đâu?**  
   **Đáp án:** `META-INF/MANIFEST.MF`.

7. **Tên class trong manifest Main-Class dùng dấu `/` hay dấu `.`?**  
   **Đáp án:** Dấu `.`, ví dụ `demo.archive.App`.

8. **Library JAR thiếu Main-Class có nhất thiết lỗi?**  
   **Đáp án:** Không.

9. **Goal Maven nào thường tạo main JAR ở phase package?**  
   **Đáp án:** `maven-jar-plugin:jar` với packaging `jar`.

10. **JAR Plugin lấy input mặc định từ thư mục nào?**  
    **Đáp án:** `${project.build.outputDirectory}`, thường `target/classes`.

11. **Thấy resource trong target/classes có chứng minh nó trong JAR?**  
    **Đáp án:** Chưa; cần kiểm tra includes/excludes và JAR entries.

12. **Một JAR không có Commons Lang class dù Maven dependency đã khai báo. Tại sao?**  
    **Đáp án:** Plain JAR thường không đóng dependencies; cần distribution/classpath hoặc fat JAR strategy.

13. **`Class.getResourceAsStream("/config/app.properties")` tìm từ đâu?**  
    **Đáp án:** Từ classpath root.

14. **`Class.getResourceAsStream("config/app.properties")` từ `demo.archive.App` có gì khác?**  
    **Đáp án:** Tìm tương đối với package, tức `demo/archive/config/app.properties`.

15. **Muốn xem bytecode/API dùng lệnh gì?**  
    **Đáp án:** `javap -classpath file.jar demo.archive.App`.

16. **Vì sao `mvn clean package` không chạy auditor trong demo?**  
    **Đáp án:** Auditor được bind vào phase `verify`, đứng sau `package`.

17. **Thêm exclude `docs/readme.txt` sẽ làm gì trong demo?**  
    **Đáp án:** Resource thiếu trong JAR; auditor ở verify làm build FAIL.

18. **Main JAR của demo có chứa `AppTest.class`?**  
    **Đáp án:** Không; đó là test class.

19. **Có thể đọc resource entry bằng Java API nào?**  
    **Đáp án:** `JarFile.getJarEntry` + `JarFile.getInputStream`, hoặc classpath resource stream khi JAR ở runtime classpath.

20. **`META-INF/maven/.../pom.properties` có phải Main-Class?**  
    **Đáp án:** Không, đó là Maven artifact metadata.

21. **JAR có thể chứa `META-INF/versions/17` để làm gì?**  
    **Đáp án:** Có thể là multi-release variant cho Java 17 khi manifest/runtime hỗ trợ.

22. **Spring Boot executable JAR có layout giống plain JAR?**  
    **Đáp án:** Không nhất thiết; thường có `BOOT-INF/classes` và `BOOT-INF/lib`.

23. **`jar tf` có chứng minh class run thành công không?**  
    **Đáp án:** Không; còn runtime classpath, bytecode version, dependency linkage và behavior.

24. **Nếu JAR thiếu resource nhưng `target/classes` có, nghi gì?**  
    **Đáp án:** Includes/excludes, classesDirectory, artifact path hoặc post-processing.

25. **Khi mã deploy thiếu resource chỉ có trong src/test/resources, nên làm gì?**  
    **Đáp án:** Chuyển resource runtime sang main resources hoặc thiết kế packaging đúng, không nhúng test tree tùy tiện.

26. **Một JAR có manifest có chắc được ký không?**  
    **Đáp án:** Không. Signing là một quy trình riêng, kiểm tra bằng jarsigner khi phù hợp.

27. **Hai JAR có cùng entry list nhưng SHA-256 khác có thể do đâu?**  
    **Đáp án:** Khác timestamps, metadata, thứ tự entry, compiled bytes hoặc resource content.

28. **Vì sao nên chạy clean verify khi điều tra JAR sai?**  
    **Đáp án:** Giảm tác động của stale classes/resources và chạy packaging gate.

29. **`java -cp file.jar demo.archive.App` và `java -jar file.jar` khác nhau thế nào?**  
    **Đáp án:** Cách đầu chỉ định class trực tiếp, cách sau dùng manifest entry point.

30. **Nguyên tắc chung trước khi phát hành JAR?**  
    **Đáp án:** Kiểm tra **chính artifact sẽ phát hành**, gồm class/resources/manifest, đúng packaging và đúng runtime dependencies.

## 29. Checklist kiểm tra artifact

- [ ] Xác định JAR đang kiểm tra là library, plain executable, fat/uber, Spring Boot hay modular.
- [ ] Xác định đúng file artifact, version, classifier và đường dẫn deploy.
- [ ] Dùng `mvn -B -ntp clean verify` từ trạng thái sạch với đúng Maven/JDK.
- [ ] Dùng `jar tf` xác minh những class entries bắt buộc.
- [ ] Kiểm tra package path và chữ hoa/thường trong entry names.
- [ ] Kiểm tra main resources và classpath-relative resource paths.
- [ ] Bảo đảm test classes và test resources không lọt vào main JAR ngoài ý muốn.
- [ ] Kiểm tra manifest và `Main-Class` khi artifact được thiết kế executable.
- [ ] Nếu cần, chạy `java -jar` và đối chiếu stdout/trạng thái process.
- [ ] Dùng `javap` khi cần kiểm tra bytecode version và class APIs.
- [ ] Kiểm tra dependencies của plain JAR được cung cấp ở runtime.
- [ ] Nếu dùng Shade/Boot packaging, audit đúng layout dành riêng cho loại đó.
- [ ] Kiểm tra includes/excludes và resource filtering thực tế.
- [ ] Có kiểm tra **entry phải có** và **entry phải vắng mặt**.
- [ ] Không chứa secrets, test-only data hoặc file tạm trong artifact.
- [ ] Nếu yêu cầu reproducibility, kiểm tra metadata/timestamps và checksums.
- [ ] Không giải nén archive không tin cậy vào thư mục quan trọng.
- [ ] Đặt packaging audit ở `verify` hoặc gate tương đương trước deploy.
- [ ] Xác minh từ build log rằng audit thật sự chạy và có test report phù hợp.
- [ ] Ghi lại chính sách artifact thành tự động hóa có thể tái lập.

## 30. Tài liệu chính thức

- [Oracle Java 17 — jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): `jar tf`, `--list`, `--extract`, modular/multi-release JAR.
- [Oracle Java 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): archive entries, manifest, signatures, multi-release behavior.
- [Oracle Java 17 — JarFile API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): đọc manifest và entries bằng Java.
- [Oracle Java 17 — javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem class files/API/bytecode version.
- [Apache Maven — Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): tạo JAR từ Maven project.
- [Apache Maven — jar:jar Goal](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html): `classesDirectory`, `outputDirectory`, `includes`/`excludes` và `outputTimestamp`.
- [Apache Maven — JAR Includes/Excludes](https://maven.apache.org/plugins/maven-jar-plugin/examples/include-exclude.html): pattern tương đối với classes directory.
- [Apache Maven — Maven Resources Plugin](https://maven.apache.org/plugins/maven-resources-plugin/): copy main/test resources.
- [Apache Maven — Resources Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html): placeholder processing.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `compile`, `test`, `package` và `verify`.
- [Apache Maven — Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): kiểm thử đơn vị và reports.
- [MojoHaus — Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/): chạy Java main trong Maven build goal.

**Kết luận:** Một file JAR đúng phải có **đúng class entries, đúng resource paths, manifest phù hợp, không lộ test data/secrets và có runtime dependencies theo packaging strategy**. Hãy kiểm tra archive thực tế bằng `jar tf`, `javap` và `JarFile`, chứ không chỉ suy luận từ source tree hoặc `target/classes`. Khi nội dung JAR là điều kiện bắt buộc, gắn một bước audit vào Maven `verify` sẽ làm lỗi packaging được phát hiện trước khi phát hành.
