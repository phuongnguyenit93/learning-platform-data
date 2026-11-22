# Maven Archiver và cấu hình manifest cho JAR

> **Build Tool Maven · JAR và manifest**  
> Bài thực hành: **Java 17, Maven 3.x, Maven JAR Plugin 3.5.1, Maven Dependency Plugin 3.11.0**. Hướng dẫn này phân biệt **Maven Archiver (thư viện đóng gói)** với **plugin tạo JAR**, cho thấy cách cấu hình `Main-Class`, `Class-Path`, thông tin implementation và các manifest entries tùy chỉnh.

## 1. Vì sao manifest quan trọng?

Một file **JAR** thực chất là một archive theo định dạng ZIP, chứa `.class`, resources và metadata. Tệp **`META-INF/MANIFEST.MF`** bên trong JAR là nơi khai báo một số thuộc tính mà Java launcher, class loader và các công cụ liên quan có thể đọc.

Ví dụ một manifest:

```text
Manifest-Version: 1.0
Main-Class: org.example.Main
Class-Path: lib/commons-lang3-3.14.0.jar
Implementation-Title: Archiver Manifest Demo
Implementation-Version: 1.0.0
Build-Channel: training
```

Đây là **các dòng quan trọng minh họa**, không phải lời hứa về thứ tự tất cả attributes do Maven tạo. Một manifest thực tế có thể có thêm `Created-By`, `Build-Jdk-Spec` hoặc thuộc tính khác tùy phiên bản Maven Archiver; dòng dài còn có thể bị ngắt theo chuẩn JAR.

Ý nghĩa của các mục:

- **`Manifest-Version`**: phiên bản định dạng manifest, thông thường là `1.0`.
- **`Main-Class`**: tên đầy đủ của class chứa entry point phù hợp để chạy bằng `java -jar`.
- **`Class-Path`**: danh sách đường dẫn/URL **tương đối với vị trí JAR** tới các thư viện ngoài cần thêm vào classpath.
- **`Implementation-Title`**, **`Implementation-Version`**: metadata về implementation được đọc qua Java Package API.
- **`Build-Channel`**: thuộc tính **tùy chỉnh**, chỉ có ý nghĩa nếu ứng dụng/tool của bạn chủ động đọc nó.

**Điều manifest không làm:** nó không tự biên dịch Java code, không tự tải thư viện Maven lúc người dùng chạy `java -jar`, không tự sao chép dependencies vào JAR và không biến một JAR thường thành **fat/uber JAR**.

### Mục tiêu sau bài học

1. Phân biệt đúng Maven Archiver và Maven JAR Plugin.
2. Hiểu cấu trúc file `META-INF/MANIFEST.MF`, main section và named sections.
3. Tạo POM Java 17 có cấu hình `<archive><manifest>...`.
4. Build và chạy JAR bằng `java -jar` với thư viện bên ngoài nằm ở `lib/`.
5. Xác minh `Main-Class`, `Class-Path`, `Implementation-Version`, custom manifest entry bằng Java `JarFile`.
6. Biết khi nào dùng `addClasspath`, `classpathPrefix`, `manifestEntries`, `manifestSections`, `manifestFile` và `addDefaultImplementationEntries`.
7. Phân biệt skinny/thin JAR với fat JAR; tránh classpath không hoạt động khi deploy.
8. Chẩn đoán `no main manifest attribute`, `ClassNotFoundException`, thiếu JAR runtime và manifest sai cú pháp.

## 2. Maven Archiver có phải một Maven plugin không?

**Không theo cách sử dụng thông thường.** **Maven Archiver** là một **thành phần thư viện dùng chung** (*shared component*) được các packaging plugins dùng để tạo các archive và metadata liên quan. Người sử dụng POM thường **không gọi một goal `archiver:...`** để tạo JAR.

Với project `<packaging>jar</packaging>`, cơ chế quen thuộc là:

```text
pom.xml
   |
   |  <build><plugins>...
   v
maven-jar-plugin
   |
   |  jar:jar trong phase package
   v
Maven Archiver / archive configuration
   |
   +--> thu thập class files & resources
   |
   +--> tạo META-INF/MANIFEST.MF
   |
   +--> thêm META-INF/maven/... nếu được cấu hình
   |
   v
target/<artifactId>-<version>.jar
```

Vì thế phần cấu hình Archiver nằm **dưới Maven JAR Plugin**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.5.1</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>org.example.Main</mainClass>
            </manifest>
        </archive>
    </configuration>
</plugin>
```

Đây là **fragment POM** để hiểu cấu trúc, chưa phải một `pom.xml` hoàn chỉnh.

### 2.1. Ba lớp trách nhiệm

| Thành phần | Trách nhiệm chính | Không nên hiểu nhầm |
| --- | --- | --- |
| Maven core/lifecycle | Quyết định phase và plugin goal nào chạy | Không tự biết class `main` của ứng dụng |
| Maven JAR Plugin | Goal `jar:jar`, đóng gói output thành JAR | Không tự tạo executable fat JAR |
| Maven Archiver | Cấu hình metadata manifest và nội dung archive dùng chung | Không phải dependency manager lúc ứng dụng chạy |
| Maven Dependency Plugin | Có thể sao chép các dependency JAR ra thư mục `lib/` | Không tự sửa manifest nếu chưa cấu hình thêm |
| JVM `java -jar` | Đọc `Main-Class` và manifest classpath để khởi chạy | Không đọc POM rồi tải thư viện từ Maven Central |

**Maven JAR Plugin 3.5.1** là bản ổn định trong nhánh 3.x của tài liệu Apache Maven; có một nhánh plugin 4.x dành cho Maven 4 với ràng buộc khác. Bài này chọn bản 3.5.1 để nhất quán với **Maven 3.x**.

### 2.2. Goal `jar:jar` chạy khi nào?

Trong packaging `jar`, Maven có **default binding** để chạy `maven-jar-plugin:jar` ở phase `package`.

```bash
mvn clean package
```

Lệnh này đi qua compile/test và các phases trước đó rồi đóng JAR. Không phải một lời gọi Maven Archiver độc lập. Nếu POM chỉ có `<packaging>pom</packaging>`, mặc định Maven không tạo một application JAR ở phase package; cần module JAR riêng hoặc explicit plugin configuration thích hợp.

## 3. Cấu trúc chuẩn của JAR và manifest

Một JAR của project mẫu sau khi package có thể có:

```text
archiver-manifest-demo-1.0.0.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/
│       └── org.example/
│           └── archiver-manifest-demo/
│               ├── pom.xml
│               └── pom.properties
└── org/
    └── example/
        ├── Main.class
        └── ManifestReader.class
```

Với Maven Archiver, `addMavenDescriptor` thông thường mặc định bật, nên Maven có thể thêm **POM descriptor** và `pom.properties` tại `META-INF/maven/<groupId>/<artifactId>/`. Hai file ấy là **metadata khác** với `MANIFEST.MF`; đừng tìm `Implementation-Version` trong POM descriptor rồi kết luận đó là key manifest.

### 3.1. Main section

Phần đầu manifest chứa các cặp:

```text
Manifest-Version: 1.0
Main-Class: org.example.Main
Implementation-Version: 1.0.0
```

Các thuộc tính trong main section liên quan JAR/ứng dụng nói chung và có thể làm mặc định cho package entries khi Java định nghĩa package từ JAR.

### 3.2. Named sections

Sau một **dòng trống**, manifest có thể chứa sections dành cho package/path/file cụ thể:

```text
Manifest-Version: 1.0
Main-Class: org.example.Main

Name: org/example/
X-Doc-State: reviewed
```

Đây chỉ là **minh họa cú pháp**, không phải giá trị mặc định Maven tạo. `Name` xác định section áp dụng cho đường dẫn nào. Java JAR Specification có quy tắc về main attributes và per-entry attributes; không nên trộn `Name:` vào phần main section.

### 3.3. Định dạng vật lý khác với cách bạn nhìn trong terminal

Theo Java JAR File Specification:

- Manifest là các **header name/value** với dấu `:` theo sau bởi một dấu cách.
- Header names có quy tắc ký tự (chữ, số, dấu gạch nối, `_`) và **không phân biệt chữ hoa/thường** khi tra cứu theo specification.
- **Một dòng vật lý không được dài quá 72 bytes UTF-8**; header dài phải tiếp tục ở dòng mới với **một dấu cách đầu dòng**.
- Sections ngăn nhau bằng **dòng trống**; thứ tự thông thường của các main attributes ngoài `Manifest-Version` không mang ý nghĩa ưu tiên.
- Không nên tự viết manifest theo cách bỏ newline cuối, làm sai continuation hoặc thêm cùng key nhiều lần trong một section.

Ví dụ một `Class-Path` quá dài có thể xuất hiện ở file vật lý như:

```text
Class-Path: lib/first-library.jar lib/second-library.jar lib/third-l
 ibrary.jar
```

Đây là **ví dụ về cơ chế tiếp dòng**; đừng dùng thao tác chia chuỗi thủ công như trên trong code production. Maven Archiver/Java JAR tool quản lý quy tắc này. Khi đọc manifest bằng `java.util.jar.Manifest`, Java sẽ trả về **giá trị logic được ghép lại**, tránh nhầm phần văn bản thụt đầu dòng là tên một artifact khác.

## 4. Cấu hình chính trong `<archive>`

Dưới `<configuration><archive>` của một packaging plugin dùng Maven Archiver, các nhóm thường gặp:

```xml
<archive>
    <manifest>
        <mainClass>org.example.Main</mainClass>
        <addClasspath>true</addClasspath>
        <classpathPrefix>lib/</classpathPrefix>
        <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
    </manifest>

    <manifestEntries>
        <Build-Channel>training</Build-Channel>
    </manifestEntries>
</archive>
```

**Quy tắc vị trí quan trọng:**

- `<archive>` là con của `<configuration>` **trong plugin**.
- `<manifest>` chứa các option chuẩn như `mainClass`, `addClasspath`, `classpathPrefix`.
- `<manifestEntries>` là **anh em của `<manifest>`**, không phải con của `<manifest>`.
- `<manifestSections>` cũng nằm dưới `<archive>`, dùng khi cần named sections.
- `<manifestFile>` (nếu dùng) cũng nằm dưới `<archive>` để cung cấp manifest có sẵn.

### 4.1. `mainClass`: điểm vào của `java -jar`

```xml
<manifest>
    <mainClass>org.example.Main</mainClass>
</manifest>
```

Tạo main manifest attribute:

```text
Main-Class: org.example.Main
```

Tên phải là **fully qualified binary class name**, không có đuôi `.java` hay `.class`; class đó cần nằm trong archive/classpath hợp lệ và có entry point thích hợp.

Đối với project Java truyền thống:

```java
public static void main(String[] args)
```

là entry point dễ hiểu. Đặt `mainClass` không tự tạo phương thức `main` nếu source không có.

Nếu JAR chưa có `Main-Class` đúng và bạn chạy:

```bash
java -jar target/app.jar
```

có thể nhận lỗi:

```text
no main manifest attribute, in target/app.jar
```

Nguyên nhân chính thường là **manifest không có entry point**, không phải do Maven Compiler Plugin không hỗ trợ Java 17.

### 4.2. `addClasspath`: sinh `Class-Path` từ project dependencies

```xml
<manifest>
    <addClasspath>true</addClasspath>
</manifest>
```

Cấu hình này cho Maven Archiver tạo `Class-Path` dựa trên các dependency artifacts thích hợp với classpath build/runtime. Nó **chỉ ghi tên/đường dẫn vào manifest**; không tự **copy JAR** và không **gộp `.class`** của thư viện ngoài vào archive.

Mặc định của `addClasspath` trong Maven Archiver reference là `false`. Vì vậy nếu muốn JAR chạy theo các thư viện ngoài được đóng cùng distribution, bạn phải chủ động quyết định cần manifest Class-Path hay không.

### 4.3. `classpathPrefix`: đặt đường dẫn tương đối

```xml
<manifest>
    <addClasspath>true</addClasspath>
    <classpathPrefix>lib/</classpathPrefix>
</manifest>
```

Khi thư viện runtime có tên `commons-lang3-3.14.0.jar`, kết quả thích hợp có thể là:

```text
Class-Path: lib/commons-lang3-3.14.0.jar
```

Tệp này phải **thực sự có** tại thư mục `lib/` **cùng cấp với JAR chính** trong bố cục triển khai của ví dụ:

```text
release/
├── archiver-manifest-demo-1.0.0.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

`classpathPrefix` **không tạo thư mục**, không tải thư viện từ Maven Central khi chạy và không tìm JAR bằng tọa độ GAV. Một `Class-Path` chỉ đúng nếu đường dẫn được khai báo **khớp bố cục distribution thực tế**.

### 4.4. `addDefaultImplementationEntries`

```xml
<manifest>
    <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
</manifest>
```

Yêu cầu Maven Archiver thêm metadata implementation từ project. Các keys thường gặp:

```text
Implementation-Title: Archiver Manifest Demo
Implementation-Version: 1.0.0
```

Nếu POM có organization metadata phù hợp, có thể xuất hiện `Implementation-Vendor`. **Đừng mặc định `Implementation-Vendor` luôn có** nếu POM thiếu thông tin organization.

Trong Java, có thể đọc:

```java
Package info = Main.class.getPackage();
System.out.println(info.getImplementationVersion());
```

Khi `Main` được load từ một JAR có implementation attributes tương ứng, giá trị có thể là version từ manifest. Khi chạy trực tiếp từ `target/classes` mà **không load từ JAR**, thông tin package manifest có thể là `null`. Đây không phải lỗi Maven build; đó là khác biệt **nguồn class được load**.

### 4.5. `addDefaultSpecificationEntries`

```xml
<manifest>
    <addDefaultSpecificationEntries>true</addDefaultSpecificationEntries>
</manifest>
```

Tùy project metadata, Archiver có thể thêm `Specification-Title`, `Specification-Version`, `Specification-Vendor`. Chúng là **thông tin specification**, khác với `Implementation-*` mô tả version cụ thể của artifact. Không dùng chúng để tự tính semantic version hoặc chứng minh binary compatibility.

### 4.6. `manifestEntries`: thuộc tính tùy chỉnh

```xml
<manifestEntries>
    <Build-Channel>training</Build-Channel>
    <Build-Label>${project.artifactId}</Build-Label>
</manifestEntries>
```

Kết quả logic mong muốn:

```text
Build-Channel: training
Build-Label: archiver-manifest-demo
```

Giá trị có thể là literal hoặc biểu thức Maven được nội suy. **Không lấy bí mật** như API key, access token, mật khẩu, internal endpoints hoặc thông tin nhận dạng cá nhân đưa vào manifest: bất kỳ người nhận JAR nào cũng có thể đọc chúng.

Nếu chưa cấu hình property hoặc project metadata được tham chiếu bằng `${...}`, cần xác minh kết quả thực tế; không cho rằng một biến POM chưa định nghĩa sẽ luôn tạo entry có giá trị hợp lệ.

### 4.7. `manifestSections`: metadata theo entry/package

Ví dụ fragment:

```xml
<manifestSections>
    <manifestSection>
        <name>org/example/</name>
        <manifestEntries>
            <X-Doc-State>reviewed</X-Doc-State>
        </manifestEntries>
    </manifestSection>
</manifestSections>
```

Đặt trong `<archive>`, không đặt dưới `<manifest>`. Nó tạo một named section có `Name: org/example/` và `X-Doc-State: reviewed`.

**Lưu ý:** `Sealed: true` trong manifest sections/main section có ý nghĩa **package sealing** và có thể gây `SecurityException` nếu classes cùng package được load từ nhiều JAR khác nhau. Không bật `Sealed` chỉ để thử custom attribute; cần hiểu tác động tới class loading và thư viện đang sử dụng.

## 5. Ví dụ chạy được: Java 17 + JAR + thư viện `lib/`

Bài thực hành sử dụng:

- Java source `Main.java` và `ManifestReader.java`.
- Một runtime dependency thật: `org.apache.commons:commons-lang3:3.14.0`.
- **Maven JAR Plugin 3.5.1** để tạo `Main-Class`, `Class-Path`, implementation info và custom entries.
- **Maven Dependency Plugin 3.11.0** với goal `copy-dependencies` để sao chép runtime JAR vào `target/lib` **trước package**.
- Maven Compiler Plugin 3.14.1 target Java 17.

**Mục tiêu:** chạy được:

```bash
mvn clean package
java -jar target/archiver-manifest-demo-1.0.0.jar
```

mà không phải gõ thủ công classpath ngoài, miễn là **JAR chính và thư mục `lib` đi cùng nhau**.

### 5.1. Cấu trúc project

```text
archiver-manifest-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    ├── Main.java
                    └── ManifestReader.java
```

Sau build sẽ có thêm:

```text
target/
├── archiver-manifest-demo-1.0.0.jar
├── lib/
│   └── commons-lang3-3.14.0.jar
└── classes/
    └── org/example/...
```

Mã nguồn và directory layout nhất quán với package `org.example`. Có thể cần Internet hoặc mirror hợp lệ để Maven tải plugins/dependencies lần đầu.

### 5.2. `pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>archiver-manifest-demo</artifactId>
    <version>1.0.0</version>
    <name>Archiver Manifest Demo</name>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.11.0</version>
                <executions>
                    <execution>
                        <id>copy-runtime-libraries</id>
                        <phase>prepare-package</phase>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.Main</mainClass>
                            <addClasspath>true</addClasspath>
                            <classpathPrefix>lib/</classpathPrefix>
                            <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                        </manifest>
                        <manifestEntries>
                            <Build-Channel>training</Build-Channel>
                            <Build-Label>${project.artifactId}</Build-Label>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Đây là một POM hoàn chỉnh**, không phải fragment. Những điểm cần đọc:

1. `maven.compiler.release=17` chọn Java 17.
2. `commons-lang3` là dependency **thật** của code, không chỉ một dependencyManagement entry.
3. Maven Dependency Plugin `copy-dependencies` được bind vào **`prepare-package`** và chỉ copy dependencies thuộc runtime classpath (gồm compile dependencies).
4. Maven JAR Plugin được bind vào **`package`** theo lifecycle của packaging `jar`.
5. `addClasspath=true` sinh manifest Class-Path từ dependencies, `classpathPrefix=lib/` khớp thư mục copy.
6. `mainClass=org.example.Main` là entry point của executable JAR.
7. `addDefaultImplementationEntries=true` thêm Implementation metadata từ POM.
8. `manifestEntries` cung cấp hai custom keys.
9. `project.build.outputTimestamp` cố định timestamp archive entries để **hỗ trợ build tái lập**; nó không cam kết mọi byte của artifact đều giống nhau khi toolchain/dependencies/môi trường khác nhau.

**Tại sao cần một plugin copy phụ thuộc?** `addClasspath` chỉ viết đường dẫn, không thực hiện file copy. `copy-dependencies` mới tạo bố cục `target/lib/...` mà Java launcher có thể tìm được.

**Tại sao không dùng `includeScope=test`?** Bài này chỉ cần runtime dependencies. Theo tài liệu Maven Dependency Plugin, `includeScope=runtime` chọn runtime và compile dependencies; `test` sẽ lấy rộng hơn, có thể đưa JUnit/Mockito không cần thiết vào distribution.

### 5.3. `src/main/java/org/example/Main.java`

```java
package org.example;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String word = StringUtils.capitalize("maven");
        System.out.println("Hello, " + word + " Archiver!");

        Package info = Main.class.getPackage();
        System.out.println("Implementation-Title=" + info.getImplementationTitle());
        System.out.println("Implementation-Version=" + info.getImplementationVersion());
    }
}
```

Giải thích:

- `StringUtils` từ `commons-lang3` chứng minh ứng dụng thật sự cần thư viện ngoài lúc chạy.
- `capitalize("maven")` tạo `"Maven"`; output không phụ thuộc OS, time zone hoặc locale.
- Java Package API đọc implementation info từ manifest khi class được load từ **JAR tương ứng**.
- Hai dòng metadata có thể là `null` nếu bạn chạy Main trực tiếp từ `target/classes` thay vì từ packaged JAR có manifest; vì vậy trong bài, hãy kiểm chứng bằng `java -jar`.

### 5.4. `src/main/java/org/example/ManifestReader.java`

Tạo một class đọc `META-INF/MANIFEST.MF` bằng **Java API**, tránh phải giải nén JAR hoặc tự phân tích line wrapping:

```java
package org.example;

import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ManifestReader {
    private ManifestReader() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected a JAR file path");
        }

        try (JarFile file = new JarFile(args[0])) {
            Manifest manifest = file.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("JAR has no manifest");
            }

            Attributes attrs = manifest.getMainAttributes();
            System.out.println("Main-Class=" + attrs.getValue("Main-Class"));
            System.out.println("Class-Path=" + attrs.getValue("Class-Path"));
            System.out.println("Implementation-Title="
                    + attrs.getValue("Implementation-Title"));
            System.out.println("Implementation-Version="
                    + attrs.getValue("Implementation-Version"));
            System.out.println("Build-Channel="
                    + attrs.getValue("Build-Channel"));
            System.out.println("Build-Label="
                    + attrs.getValue("Build-Label"));
        }
    }
}
```

Đây là một Java 17 class **biên dịch độc lập** chỉ dùng Java standard library. `JarFile` tự parse chuẩn manifest; nó giúp bạn lấy các giá trị đã được **nối continuation lines** thay vì phải tự xử lý cú pháp `MANIFEST.MF`.

**Vì sao reader là class riêng?** `Main` kiểm tra executable JAR và dependency runtime. `ManifestReader` kiểm tra các manifest attributes, không phụ thuộc vào code startup.

### 5.5. Build sạch

Đứng trong thư mục `archiver-manifest-demo`:

```bash
java -version
javac -version
mvn -version
mvn clean package
```

Kỳ vọng:

- `compiler:compile` tạo `Main.class` và `ManifestReader.class`.
- Plugin copy-dependencies đưa JAR `commons-lang3-3.14.0.jar` vào `target/lib`.
- `jar:jar` tạo `target/archiver-manifest-demo-1.0.0.jar` và manifest có cấu hình.
- Build thành công nếu Maven resolve được dependencies/plugins và source Java đúng.

Các plugin khác như Surefire có thể tham gia lifecycle theo default bindings; ví dụ không chứa test sources nên không có unit tests cần chạy. Không đánh đồng build thành công với việc một test suite nào đó đã PASS.

### 5.6. Chạy bằng `java -jar`

```bash
java -jar target/archiver-manifest-demo-1.0.0.jar
```

**Stdout chính xác của chương trình mẫu** khi JAR được đóng gói và thư viện ở đúng đường dẫn:

```text
Hello, Maven Archiver!
Implementation-Title=Archiver Manifest Demo
Implementation-Version=1.0.0
```

Điều kiện để kết quả chính xác:

1. Java launcher đọc được `Main-Class: org.example.Main`.
2. `target/lib/commons-lang3-3.14.0.jar` tồn tại cạnh JAR theo classpath prefix.
3. `Main.class` đã nằm trong JAR.
4. Implementation entries được Archiver sinh theo POM như đã cấu hình.
5. Không có cấu hình môi trường đặc biệt thay đổi class loading.

**Không được tự kết luận** vì `java -cp target/classes org.example.Main` thất bại hoặc metadata `null` thì JAR sai: lệnh ấy không tự thêm JAR Commons và không đọc manifest của archive theo cách của `java -jar`.

### 5.7. Đọc manifest bằng Java

Chạy:

```bash
java -cp target/classes org.example.ManifestReader target/archiver-manifest-demo-1.0.0.jar
```

**Stdout chính xác mong đợi** cho POM/demo:

```text
Main-Class=org.example.Main
Class-Path=lib/commons-lang3-3.14.0.jar
Implementation-Title=Archiver Manifest Demo
Implementation-Version=1.0.0
Build-Channel=training
Build-Label=archiver-manifest-demo
```

Đây là **logical values** được Java `JarFile` đọc. File manifest vật lý có thể sắp key theo thứ tự khác, có thêm default entries hoặc ngắt dòng nếu cần; đó không ảnh hưởng các giá trị mà code reader in.

### 5.8. Xem entries của JAR

Dùng công cụ `jar` đi kèm JDK:

```bash
jar tf target/archiver-manifest-demo-1.0.0.jar
```

Tìm các entries:

```text
META-INF/MANIFEST.MF
org/example/Main.class
org/example/ManifestReader.class
META-INF/maven/org.example/archiver-manifest-demo/pom.xml
META-INF/maven/org.example/archiver-manifest-demo/pom.properties
```

Thứ tự trong output có thể khác. Theo Maven Archiver mặc định, POM descriptor và `pom.properties` thường được thêm khi `addMavenDescriptor=true`.

**Điểm rất quan trọng:** `commons-lang3-3.14.0.jar` **không** xuất hiện bên trong thin JAR ở ví dụ này; nó ở **`target/lib` bên ngoài**. Nếu dùng `jar tf` không thấy thư viện ngoài, đây là hành vi đúng của Maven JAR Plugin mặc định.

### 5.9. Thử di chuyển JAR mà không mang `lib`

Nếu chỉ copy file:

```text
archiver-manifest-demo-1.0.0.jar
```

sang một thư mục mới mà **không mang theo**:

```text
lib/commons-lang3-3.14.0.jar
```

thì khi chạy Java có thể báo lỗi tương tự:

```text
java.lang.NoClassDefFoundError:
org/apache/commons/lang3/StringUtils
```

Đây là **dạng triệu chứng**, không phải lời hứa từng dòng stacktrace. File manifest vẫn có `Class-Path`, nhưng đường dẫn tương đối dẫn tới vị trí **không có thư viện**.

Cách khắc phục: phát hành cả JAR chính và thư mục `lib/` theo đúng layout, hoặc chọn cơ chế packaging **fat JAR** khi cần một file duy nhất.

## 6. Thin JAR không phải fat JAR

Ba hình thức phân phối phổ biến:

| Hình thức | Nội dung JAR chính | Cách chạy | Khi nào phù hợp |
| --- | --- | --- | --- |
| **Thin JAR** | App classes/resources, manifest, không gộp deps | `java -jar` + manifest Class-Path hoặc classpath ngoài | Có bố cục `app.jar` và `lib/*.jar` trong distribution |
| **Uber/Fat JAR** | Classes/resources của app **và** thư viện được gộp | Thường `java -jar single.jar` sau cấu hình plugin phù hợp | Muốn deploy một artifact; cần xử lý resource merge, service files, signatures |
| **Framework executable JAR** | Layout riêng theo framework | Launcher/repackage riêng | Ví dụ hệ sinh thái Spring Boot; không giống Maven JAR Plugin mặc định |

**Maven Archiver tự nó không tạo fat JAR.** `<addClasspath>true</addClasspath>` chỉ sinh một **danh sách đường dẫn**. Nếu cần gộp dependencies, xem Maven Shade Plugin, Maven Assembly Plugin hoặc framework packaging plugin; các plugin ấy có cấu hình manifest, resource transformers và tradeoffs riêng.

### 6.1. Câu hỏi thường gặp: Vì sao `jar tf` không thấy Commons Lang?

Vì ví dụ dùng **thin JAR**. File Commons Lang là một JAR riêng nằm cạnh application JAR. JVM dùng `Class-Path` manifest để tìm nó lúc runtime. Đây là cách đóng gói hợp lệ, không phải dấu hiệu build thiếu một bước.

### 6.2. Nếu muốn dùng `java -cp` thay vì manifest

Bạn có thể không khai báo `Main-Class`, rồi chạy chương trình bằng một command cung cấp classpath đầy đủ. Ví dụ Linux/macOS:

```bash
java -cp "target/archiver-manifest-demo-1.0.0.jar:target/lib/*" org.example.Main
```

Trên Windows PowerShell/cmd:

```powershell
java -cp "target/archiver-manifest-demo-1.0.0.jar;target/lib/*" org.example.Main
```

Đây là cách chọn class bằng Java CLI; `*` trong `target/lib/*` là Java classpath wildcard với thư viện JAR, **khác** cú pháp `Class-Path` trong manifest. Với **`java -jar`**, Java launcher đọc `Main-Class` và **không áp dụng `-cp` do người dùng truyền theo cách thông thường**; dùng manifest hoặc phương thức packaging riêng.

Trong ví dụ chính, dùng `java -jar` để kiểm chứng `Main-Class`/`Class-Path` là trực quan nhất.

### 6.3. Manifest Class-Path không hiểu Maven coordinates

Không viết:

```text
Class-Path: org.apache.commons:commons-lang3:3.14.0
```

và mong JVM tự tìm artifact từ `~/.m2/repository`. `Class-Path` yêu cầu URLs/path entries hợp lệ **tương đối với JAR**, không phải cú pháp dependency POM. Dữ liệu `groupId`, `artifactId`, `version` là thông tin Maven resolution trong **build time**; Java runtime không phải Maven dependency resolver.

## 7. `manifestFile`: cung cấp manifest viết sẵn

Maven Archiver cho phép dùng:

```xml
<archive>
    <manifestFile>${project.basedir}/src/main/manifest/MANIFEST.MF</manifestFile>
</archive>
```

Đây là **fragment**. File được tham chiếu phải tồn tại, có cú pháp manifest hợp lệ, và không gây xung đột ngoài chủ đích với các thuộc tính Archiver tự tạo.

Ví dụ file nguồn:

```text
Manifest-Version: 1.0
Main-Class: org.example.Main
Build-Channel: training

```

File thực cần tuân thủ newline/line wrapping/sections theo Java JAR Specification. **Đừng tự đoán precedence** khi bạn đồng thời chỉ định `manifestFile`, `<manifest><mainClass>` và `<manifestEntries>` có cùng key: hành vi merge của plugin/Archiver có quy tắc và phiên bản cụ thể; tốt nhất chọn **một nguồn chân lý** cho mỗi attribute rồi đọc manifest sau build.

Trong phần lớn project Maven, **cấu hình XML dưới `<archive>` đủ đơn giản và dễ nội suy từ POM**, nên không cần viết manifest thủ công. `manifestFile` hữu ích nếu có yêu cầu chuẩn hóa manifest riêng hoặc nhập metadata phát sinh từ bước build khác.

### 7.1. Không đặt MANIFEST.MF tùy tiện rồi mong Maven dùng

Chỉ tạo:

```text
src/main/resources/META-INF/MANIFEST.MF
```

chưa chắc là cách phù hợp để **điều khiển** manifest output của Maven JAR Plugin. Cách được tài liệu hỗ trợ rõ ràng là **`<archive>` configuration** hoặc `<manifestFile>` có đường dẫn chính xác. Nếu project đã có resource manifest do plugin khác tạo, cần xác định plugin nào thắng và file thực cuối cùng.

### 7.2. Vì sao cần một nguồn chân lý?

Nếu POM có `mainClass=org.example.Main` nhưng manifest file lại có `Main-Class: org.example.OtherMain`, bạn đã tạo cấu hình mâu thuẫn. Hậu quả phụ thuộc merge behavior và có thể khó debug khi đổi plugin version. Nên để `Main-Class` chỉ được quản lý ở một nơi, build sạch và kiểm tra bằng `JarFile`/`jar xf`.

## 8. Thuộc tính implementation/specification và Java Package API

Các entries thuộc nhóm metadata package:

```text
Specification-Title: ...
Specification-Version: ...
Specification-Vendor: ...
Implementation-Title: ...
Implementation-Version: ...
Implementation-Vendor: ...
```

Trong POM có thể bật:

```xml
<manifest>
    <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
    <addDefaultSpecificationEntries>true</addDefaultSpecificationEntries>
</manifest>
```

**Không phải tất cả keys đều được tạo có giá trị nếu project không có metadata tương ứng.** `Implementation-Title` thường lấy `project.name`, `Implementation-Version` lấy `project.version`. `Vendor` thường cần thông tin tổ chức. Maven Archiver reference và version plugin là nguồn chính xác để kiểm chứng.

Java Package API:

```java
Package p = Main.class.getPackage();
String title = p.getImplementationTitle();
String version = p.getImplementationVersion();
String spec = p.getSpecificationVersion();
```

Ba dòng trên là **fragment**; dùng trong một method sau khi `Main` đã được load.

**Cảnh báo về class loaders:** metadata package đến từ quá trình định nghĩa package bằng class loader. Nếu nhiều JAR chứa cùng package hoặc class được load qua công cụ/framework khác, metadata lấy được có thể khác dự đoán. Đừng dùng `Package.getImplementationVersion()` làm cơ chế bảo mật để chứng minh artifact có nguồn gốc đáng tin.

### 8.1. POM version và manifest version không phải lúc nào cũng giống nhau

Nếu bạn tự ghi `Implementation-Version` qua custom `manifestEntries`, dùng `manifestFile` hoặc packaging plugin có transformers, nó có thể **khác** `project.version`. Muốn đồng bộ, dùng một nguồn nội suy từ POM và xác minh output. Đừng giữ chuỗi version hardcoded ở cả ba nơi rồi quên cập nhật.

## 9. `Class-Path` nâng cao: layout và snapshot

Maven Archiver hỗ trợ:

- `classpathLayoutType=simple`: thông dụng, tên JAR.
- `classpathLayoutType=repository`: layout giống cây Maven repository.
- `classpathLayoutType=custom`: dùng expression trong `customClasspathLayout`.
- `classpathPrefix`: tiền tố cho các entries.
- `useUniqueVersions`: cách biểu diễn versions timestamped SNAPSHOT trong classpath khi phù hợp.

Ví dụ **fragment**:

```xml
<manifest>
    <addClasspath>true</addClasspath>
    <classpathLayoutType>simple</classpathLayoutType>
    <classpathPrefix>lib/</classpathPrefix>
</manifest>
```

Với layout `simple`, đường dẫn như:

```text
Class-Path: lib/commons-lang3-3.14.0.jar
```

vừa gọn vừa phù hợp distribution kiểu `lib/`.

### 9.1. Repository layout có nghĩa gì?

Nếu chọn `repository`, manifest entries có thể dùng cấu trúc thư mục giống Maven cache:

```text
lib/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
```

Đây là **minh họa ý tưởng layout**; đường dẫn thực tế còn phụ thuộc artifact và options. **Bạn phải copy dependencies theo cùng layout**. Nếu dùng `copy-dependencies` mặc định copy tất cả JAR vào một `lib/` phẳng nhưng manifest lại dùng repository layout, app sẽ không tìm thấy thư viện.

Đừng đổi `classpathLayoutType` nếu không đồng thời thiết kế lại distribution layout.

### 9.2. Custom layout cần expression phù hợp

Đặt:

```xml
<classpathLayoutType>custom</classpathLayoutType>
```

mà không có `customClasspathLayout` là cấu hình **chưa đầy đủ**. Maven Archiver yêu cầu layout expression cho custom. Đây chỉ là ví dụ cấu trúc, không phải cấu hình để copy chạy. Nếu không thật sự cần biến thể artifact path, nên giữ `simple` để tránh các sai lệch tên file.

### 9.3. Snapshot cần chú ý `useUniqueVersions`

Maven có thể phát hành snapshot dưới timestamp/buildnumber, ví dụ một artifact logical `1.0-SNAPSHOT` nhưng repository lưu version timestamped. `useUniqueVersions` ảnh hưởng tên snapshot JAR trong manifest classpath theo resolver/Archiver config.

Khi phát hành thin JAR từ snapshot dependencies, cần đảm bảo **tên thực tế đã copy** khớp chính xác tên manifest ghi. Nếu manifest dùng timestamped snapshot mà bước copy đặt tên generic `-SNAPSHOT.jar`, runtime có thể báo thiếu class. Tránh dùng snapshots cho bản release nếu không có lý do rõ và quy trình pin/đóng gói nhất quán.

## 10. `Automatic-Module-Name` và `Multi-Release`

Hai manifest attributes này liên quan hệ thống module Java, nhưng **không giống `Main-Class`**.

### 10.1. Automatic-Module-Name

Một non-modular JAR muốn có tên module ổn định khi đặt trên module path có thể khai báo:

```xml
<manifestEntries>
    <Automatic-Module-Name>org.example.archiverdemo</Automatic-Module-Name>
</manifestEntries>
```

Đây là **fragment**, không nằm trong demo chính. Nó gắn tên automatic module khi JAR không có explicit module descriptor. Nếu JAR có `module-info.class`, descriptor module thực tế quan trọng hơn manifest entry ở ngữ cảnh module path.

`Automatic-Module-Name` **không** tự tạo `module-info.java` và không làm JAR “module hóa hoàn toàn”. Cũng không phải entry point để `java -jar` chạy.

### 10.2. Multi-Release

Java JAR Specification hỗ trợ:

```text
Multi-Release: true
```

khi archive có các class phiên bản khác nhau dưới:

```text
META-INF/versions/9/
META-INF/versions/17/
```

Nhưng **chỉ thêm header `Multi-Release: true` không tự biên dịch/copy các class variant**. Phải có build process tạo đúng bytecode/versioned entries và bảo đảm các quy tắc public API/module compatibility.

Trong nhiều ứng dụng Java 17 thông thường, **không cần multi-release JAR**. Bật nó vô căn cứ có thể làm class-loading behavior khó dự đoán, đặc biệt khi tests không chạy trên nhiều JDK versions.

## 11. Reproducible builds: manifest và timestamps

Một JAR có thể thay đổi bytes giữa hai build dù source không đổi, bởi timestamps và metadata môi trường. Maven JAR Plugin hỗ trợ property:

```xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Tham số `outputTimestamp` của JAR Plugin sử dụng `${project.build.outputTimestamp}` để quy định timestamp cho các entries trong archive. Đây là **một bước quan trọng** để hỗ trợ reproducible builds.

Tuy nhiên, nó **không đủ** nếu:

- Build plugin hoặc dependency versions thay đổi.
- Annotation processors/codegen chèn thời gian hiện tại.
- Custom manifest entries có `${user.name}`, hostname, absolute paths hoặc current timestamp.
- Có artifacts nằm ngoài version control, snapshots biến động hoặc build toolchain khác.
- Thư viện được copy/đóng gói từ repository không đáng tin hay khác bản.

### 11.1. Tránh đưa thông tin máy developer vào manifest

Không khuyến nghị:

```xml
<manifestEntries>
    <Built-By>${user.name}</Built-By>
</manifestEntries>
```

nếu mục tiêu là artifact tái lập và hạn chế lộ tên tài khoản local. Đây là một **phản ví dụ**. Tương tự, tránh nhúng đường dẫn home, tokens hoặc hostname vào custom entries.

Các entries đáng dùng hơn: project version, artifactId, build channel không nhạy cảm, commit ID do CI **có quy trình kiểm soát rõ**. Nếu commit hash được nhúng, phải hiểu đó là thay đổi có chủ đích làm artifact khác khi commit khác.

### 11.2. So sánh hash sau hai clean builds

Một cách kiểm chứng nguyên lý:

```bash
mvn clean package
```

Tính SHA-256 của `target/archiver-manifest-demo-1.0.0.jar`, lưu giá trị, rồi chạy lại với **cùng môi trường/inputs/toolchain**. Trên Linux:

```bash
sha256sum target/archiver-manifest-demo-1.0.0.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\target\archiver-manifest-demo-1.0.0.jar"
```

Nếu khác hash, cần điều tra entries/manifest/ZIP metadata, không vội kết luận plugin bị lỗi. Một `outputTimestamp` cố định giúp một phần, chứ không cam kết mọi plugin đều tạo outputs deterministic.

## 12. Manifest và JAR signing

`META-INF/MANIFEST.MF` cũng liên quan tới **signed JARs**: các `*.SF`, `*.RSA`, `*.DSA`, `*.EC` và per-entry digests có vai trò trong quá trình `jarsigner` ký/xác minh archive.

**Thay đổi manifest hoặc nội dung archive sau khi ký có thể làm chữ ký không còn hợp lệ.** Nếu cần ký JAR trong pipeline:

1. Hoàn tất compile/package, bao gồm manifest entries.
2. Kiểm tra chính xác file output.
3. Ký bằng công cụ/quy trình hợp lệ.
4. Không sửa manifest hoặc archive sau khi ký.
5. Xác minh chữ ký bằng tool thích hợp trong CI/release process.

Đừng lẫn:

- `Implementation-Version`: **metadata**, không phải chữ ký.
- `Build-Channel`: custom string, không chứng minh provenance.
- `Class-Path`: URL search paths, không chứng minh thư viện được xác thực.
- `META-INF/*.SF` và signature block: một phần cơ chế JAR signing.

Nếu app thực sự cần bảo đảm supply-chain, kết hợp chính sách artifact repositories, checksum/signatures và CI provenance; manifest version string **không phải** bằng chứng bảo mật.

## 13. Maven module, parent và pluginManagement

Trong multi-module reactor:

```text
workspace/
├── pom.xml          (parent/aggregator, packaging=pom)
├── api/pom.xml      (jar)
└── cli/pom.xml      (jar, có Main-Class)
```

Không nên đặt `mainClass=org.example.cli.Main` trong `<build><plugins>` của parent nếu mọi child JAR kế thừa cấu hình và `api` không có main class đó. Hệ quả: JAR API có thể mang Main-Class sai dù bản thân nó không phải executable application.

### 13.1. Quản lý version chung ở parent

Parent có thể quản lý plugin version:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây là **fragment**. Child cần cấu hình `archive` phù hợp với nhiệm vụ riêng. `pluginManagement` không tự ép mọi goal tùy ý chạy; song Maven JAR Plugin vẫn có default lifecycle binding cho packaging JAR, và settings/version quản lý có thể áp dụng khi plugin được sử dụng.

### 13.2. Application module khai báo mainClass riêng

Trong `cli/pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>org.example.cli.Main</mainClass>
                    </manifest>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là fragment minh họa. `api` module chỉ cần JAR library bình thường, không có Main-Class nếu không có mục tiêu executable.

### 13.3. `modules` không tự tạo fat JAR tổng hợp

Aggregator POM liệt kê `<modules>` không tự gộp tất cả child JARs thành một JAR. Mỗi module có packaging/goal riêng. Muốn CLI application phân phối cùng `api` JAR, cần tạo dependency đúng và chọn **distribution layout** hoặc fat JAR strategy. Đừng nhầm **Maven reactor aggregation** với **archive aggregation**.

## 14. Chẩn đoán lỗi thực tế

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `no main manifest attribute` | Không có Main-Class | Kiểm tra `<archive><manifest><mainClass>` và JAR cuối |
| `Could not find or load main class` | Ghi sai FQCN hoặc class không được đóng gói | `jar tf`, kiểm tra package và Main-Class |
| `NoClassDefFoundError` khi `java -jar` | Runtime JAR ngoài không ở đường dẫn Class-Path | Đối chiếu `target/lib` và manifest |
| `java -cp ...` chạy nhưng `java -jar` lỗi | Hai cách chọn classpath khác nhau | Kiểm tra manifest Main-Class/Class-Path |
| `jar tf` không thấy Commons Lang | Thin JAR không gộp dependency | Đây là mặc định; copy lib hoặc chọn Shade |
| `Class-Path` có đường dẫn `lib/...` nhưng copy ở `target/dependency` | `classpathPrefix` lệch outputDirectory | Đồng bộ bố cục distribution |
| Có `Implementation-Version` nhưng Java in `null` | Class được load từ `target/classes`/classloader khác | Chạy `java -jar`, xem JAR được load thực tế |
| Implementation entries vắng mặt | Chưa bật addDefaultImplementationEntries/thiếu metadata | Kiểm tra option và effective POM |
| Custom entry không có | Sai chỗ `<manifestEntries>` hoặc biến chưa nội suy | Kiểm tra XML nesting và `JarFile` output |
| `Main-Class` sai khi child build | Parent plugin config bị kế thừa | Đặt config ở module ứng dụng |
| `java -jar` không thấy `Class-Path` wildcard | Manifest không dùng Java CLI wildcard như classpath shell | Khai báo path tới JAR thật, không `lib/*` |
| JAR chạy trên máy dev, lỗi trên server | Máy dev có classpath ngoài, server thiếu lib | Đóng gói đủ distribution và test trong clean environment |
| Dùng repository layout nhưng thư viện ở lib/ phẳng | Manifest và copy layout không khớp | Dùng simple layout hoặc copy theo repository layout |
| Snapshot dependency runtime không tìm thấy | Manifest sử dụng tên timestamped khác file copy | Kiểm tra useUniqueVersions & output filenames |
| Tự thêm `Multi-Release: true` nhưng không thấy versioned classes | Header không tự tạo multi-release variants | Cấu hình compiler/packaging cho versioned entries |
| `jar xf` hiện dòng Class-Path bị bẻ | Chuẩn giới hạn 72 bytes mỗi dòng | Dùng `JarFile` để đọc logical attribute |
| Sau khi sửa manifest, chữ ký JAR lỗi | Signed JAR bị thay đổi nội dung | Build final rồi mới ký, verify |
| `mvn compile` không thấy JAR mới | Phase package chưa chạy | Dùng `mvn clean package` |
| POM hợp lệ nhưng `java -jar` báo JAR not found | Sai working directory hoặc artifact name/version | Kiểm tra `target/` và `artifactId/version` |
| Java 17 code không chạy trên Java 11 | Bytecode/runtime mismatch | Kiểm tra `maven.compiler.release` và JVM runtime |
| Manifest chứa secrets | Đưa token/user info vào manifestEntries | Gỡ khỏi POM, rotate secrets, review artifact |
| Hai lần build khác SHA dù outputTimestamp cố định | Còn sources/plugin/env không deterministic | So sánh archive entries, codegen, metadata |
| `Class-Path` dùng Maven GAV | JVM không resolve GAV | Thay bằng relative URL và copy JAR |

### 14.1. Quy trình debug tối thiểu

Chạy từ root module:

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean package
jar tf target/archiver-manifest-demo-1.0.0.jar
java -cp target/classes org.example.ManifestReader target/archiver-manifest-demo-1.0.0.jar
java -jar target/archiver-manifest-demo-1.0.0.jar
```

Kiểm tra theo thứ tự:

1. **Project POM/plugin version thực sự**: JAR Plugin được khai báo đúng? Parent/profile có override không?
2. **File thật sự**: `target/...jar` đúng GAV, build hiện tại hay file cũ?
3. **Archive content**: có `Main.class`, `META-INF/MANIFEST.MF`?
4. **Manifest logical values**: đúng Main-Class, Class-Path, Implementation-Version, custom entries?
5. **External distribution**: đúng `target/lib/...`?
6. **JDK runtime**: Java có đọc được classfile format và load dependencies?
7. **CI deploy**: có mang cả JAR và thư viện ngoài khi publish?

Lệnh `mvn -X clean package` có thể giúp khi cần chi tiết về plugin execution/Archiver configuration. Nhưng debug logs có thể chứa URLs nội bộ, môi trường hoặc thông tin nhạy cảm; không đăng lên issue công khai nếu chưa lọc.

### 14.2. Lỗi thiếu class khác lỗi thiếu Main-Class

`no main manifest attribute` xảy ra **trước** khi chương trình chạy: Java launcher không biết class entry point. `NoClassDefFoundError` từ `StringUtils` xảy ra **sau** khi entry point được tìm nhưng lúc runtime thiếu Commons Lang. Vì vậy hai lỗi cần hai cách sửa khác nhau; thêm Main-Class không tự sửa thư viện bị thiếu.

### 14.3. Một build thành công chưa chứng minh deploy đúng

Maven có thể compile với dependency đã tải trong local repository, còn server runtime không có JAR ấy. Vì thế bài thực hành dùng `target/lib` và `Class-Path` tương ứng, rồi yêu cầu chạy chính JAR đã package. Trong CI, nên kiểm tra ứng dụng trong **layout phân phối giống production**, không chỉ gọi `mvn package` rồi dừng.

## 15. Các câu hỏi tự kiểm tra

**Câu 1.** Maven Archiver có phải goal Maven mà ta phải chạy trực tiếp để đóng JAR?  
**Đáp án:** Không. Nó là thư viện packaging dùng bởi các plugin như Maven JAR Plugin; `jar:jar` mới là goal đóng gói.

**Câu 2.** Cấu hình Main-Class đặt ở vị trí nào trong POM?  
**Đáp án:** Dưới `<build><plugins><plugin>` của JAR Plugin, trong `<configuration><archive><manifest><mainClass>`.

**Câu 3.** `Main-Class` có chứa đuôi `.class` không?  
**Đáp án:** Không; ghi fully qualified class name, ví dụ `org.example.Main`.

**Câu 4.** `addClasspath=true` có tự copy `commons-lang3` vào JAR không?  
**Đáp án:** Không. Nó tạo `Class-Path` manifest; cần copy JAR ra đường dẫn tương ứng hoặc dùng fat JAR plugin.

**Câu 5.** Vì sao `classpathPrefix=lib/` cần bố cục `app.jar` cạnh `lib/`?  
**Đáp án:** Manifest Class-Path được giải quyết **tương đối với vị trí JAR**; path phải tồn tại tại runtime.

**Câu 6.** `manifestEntries` nên đặt dưới `<manifest>` hay dưới `<archive>`?  
**Đáp án:** Dưới `<archive>`, cùng cấp với `<manifest>`.

**Câu 7.** Có thể đọc `Implementation-Version` từ Java thế nào?  
**Đáp án:** `Main.class.getPackage().getImplementationVersion()` khi class được load từ JAR với manifest metadata phù hợp.

**Câu 8.** Tại sao chạy Main bằng `java -cp target/classes` có thể trả `Implementation-Version=null`?  
**Đáp án:** Vì class được load từ classes directory, không phải JAR archive với manifest.

**Câu 9.** `manifestSections` giải quyết loại nhu cầu gì?  
**Đáp án:** Tạo named sections cho path/package/file cụ thể, phân biệt với main attributes toàn JAR.

**Câu 10.** Nếu ghi `Class-Path: lib/*` có giống wildcard trong `java -cp "lib/*"` không?  
**Đáp án:** Không. Manifest Class-Path liệt kê các URLs tương đối đến JARs/directories; không sử dụng Java CLI wildcard theo cùng cách.

**Câu 11.** Tại sao `jar tf` không hiển thị JAR phụ thuộc trong JAR chính?  
**Đáp án:** Vì Maven JAR Plugin tạo thin JAR; các dependencies được copy ra thư mục ngoài.

**Câu 12.** `manifestFile` có thể kết hợp với `<mainClass>` và custom entries như thế nào?  
**Đáp án:** Có cơ chế merge theo Archiver/plugin; tránh key trùng và đọc JAR output để kiểm chứng, không đoán precedence.

**Câu 13.** `project.build.outputTimestamp` hỗ trợ điều gì?  
**Đáp án:** Cố định timestamp archive entries cho reproducibility; không tự bảo đảm mọi tool/dependency tạo byte-identical artifacts.

**Câu 14.** `Automatic-Module-Name` có tự tạo `module-info.class` không?  
**Đáp án:** Không. Nó hỗ trợ tên automatic module cho non-modular JAR trong module-path context.

**Câu 15.** `Multi-Release: true` có tự sinh classes ở `META-INF/versions/17` không?  
**Đáp án:** Không; build phải tạo đúng versioned entries.

**Câu 16.** Thay manifest sau khi ký JAR có rủi ro gì?  
**Đáp án:** Có thể làm chữ ký không còn hợp lệ; nên ký sau khi hoàn thiện archive.

**Câu 17.** Parent POM có `Main-Class` cho module CLI; module API cũng kế thừa có vấn đề gì?  
**Đáp án:** Có thể gắn entry point không tồn tại vào API JAR; nên cấu hình ở module executable.

## 16. Checklist trước khi phát hành JAR

- [ ] Đã ghim Maven JAR Plugin version phù hợp với Maven/JDK.
- [ ] Hiểu Maven Archiver là **thư viện** hỗ trợ plugin, không phải goal tạo artifact trực tiếp.
- [ ] Đã chọn `Main-Class` là tên package/class chính xác.
- [ ] Class entry point có trong JAR output và tương thích runtime.
- [ ] Nếu có dependencies ngoài, quyết định rõ thin JAR + `lib` hay fat JAR.
- [ ] Nếu dùng `addClasspath`, `classpathPrefix` khớp đường dẫn dependency thực tế.
- [ ] Bước copy dependency chạy đủ sớm và chỉ đóng gói runtime jars cần thiết.
- [ ] Không để generated manifest `Class-Path` trỏ tới GAV hoặc cache riêng máy.
- [ ] Đã dùng `manifestEntries` đúng vị trí, tránh key trùng và không nhúng secrets.
- [ ] Nếu muốn implementation metadata, đã bật `addDefaultImplementationEntries`.
- [ ] Đã kiểm tra main section và sections theo nhu cầu, không nhầm `manifestSections`.
- [ ] Không copy `MANIFEST.MF` thủ công trái với cấu hình Archiver mà không kiểm chứng kết quả.
- [ ] Đã dùng `jar tf` để kiểm tra archive entries.
- [ ] Đã đọc `META-INF/MANIFEST.MF` bằng Java `JarFile` hoặc công cụ phù hợp.
- [ ] Đã chạy `java -jar` từ layout thực tế để xác nhận runtime classpath.
- [ ] Nếu dùng SNAPSHOT, tên dependency JAR trong manifest và output copy khớp nhau.
- [ ] Nếu cần reproducible build, đã kiểm soát timestamps và metadata môi trường.
- [ ] Nếu cần JAR signing, thực hiện **sau khi hoàn tất manifest**, rồi verify chữ ký.
- [ ] Trong multi-module, chỉ cấu hình Main-Class ở module cần executable JAR.
- [ ] CI không báo release thành công chỉ dựa vào `mvn package`; phải kiểm tra artifact phân phối.

## 17. Tài liệu chính thức

1. [Apache Maven JAR Plugin — Plugin Overview](https://maven.apache.org/plugins/maven-jar-plugin/)
2. [Apache Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
3. [Apache Maven JAR Plugin — Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html)
4. [Apache Maven Archiver — Configuration Reference](https://maven.apache.org/components/shared/maven-archiver/)
5. [Apache Maven Archiver — Set Up The Classpath](https://maven.apache.org/shared/maven-archiver/examples/classpath.html)
6. [Apache Maven Archiver — Manifest Entries](https://maven.apache.org/shared/maven-archiver/examples/manifestEntries.html)
7. [Apache Maven Archiver — Manifest Sections](https://maven.apache.org/shared/maven-archiver/examples/manifestSections.html)
8. [Apache Maven Archiver — Implementation & Specification Entries](https://maven.apache.org/shared/maven-archiver/examples/manifest.html)
9. [Apache Maven Dependency Plugin — dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html)
10. [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
11. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
12. [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)

**Ghi nhớ cuối bài:** Maven Archiver giúp các packaging plugins **tạo và cấu hình manifest**, nhưng một executable JAR đúng cần **Main-Class hợp lệ, classes đã đóng gói, dependency runtime thực sự tồn tại ở classpath phù hợp**. `Class-Path` là thông tin đường dẫn, không phải cơ chế tự tải/gộp JAR. Luôn kiểm tra cả **manifest logic lẫn bố cục phân phối và kết quả `java -jar`**.
