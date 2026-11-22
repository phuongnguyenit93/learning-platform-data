# JAR artifact trong Java

**JAR (Java Archive)** là định dạng archive dựa trên ZIP, dùng để gom Java class, resource và metadata vào một file để chạy, phân phối hoặc tái sử dụng. Một JAR có thể là thư viện cho ứng dụng khác, executable application có điểm vào `Main-Class`, explicit module có `module-info.class`, hoặc multi-release JAR chứa implementation cho nhiều phiên bản Java.

Trong build pipeline, JAR là **binary artifact** được tạo từ source và dependency đã khai báo. Artifact cần có tên/version ổn định, nội dung đúng, có thể kiểm tra, và được lưu hoặc publish ở nơi mà người dùng build có thể truy cập. Công cụ `jar` của JDK cho phép thao tác archive trực tiếp; Gradle và Maven tích hợp việc đóng gói vào lifecycle build.

## 1. JAR gồm những gì?

JAR là một ZIP archive. Các entry bên trong dùng đường dẫn phân cấp với dấu `/`, không phụ thuộc separator của hệ điều hành.

Ví dụ cấu trúc một JAR thông thường:

```text
jar-demo-1.2.3.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── HelloApp.class
└── app.properties
```

| Entry | Vai trò |
| --- | --- |
| `META-INF/MANIFEST.MF` | Metadata của archive và ứng dụng |
| `com/example/*.class` | Bytecode theo package |
| Resource | Properties, template, ảnh, schema, file cấu hình... |
| `META-INF/services/` | Service Provider Configuration cho `ServiceLoader` |
| `module-info.class` | Module descriptor nếu đây là explicit modular JAR |
| `META-INF/versions/N/` | Class/resource dành cho Java release N trong multi-release JAR |
| `META-INF/*.SF`, `*.RSA`, `*.DSA`, `*.EC` | File phục vụ chữ ký số |

JAR không tự động chứa dependency bên ngoài. JAR được tạo từ Java plugin hoặc lệnh `jar` thường là **thin JAR**: chứa class và resource của module, còn dependency được cung cấp qua classpath, module path hoặc runtime distribution riêng.

Một **fat/uber JAR** gom cả class của ứng dụng và dependency vào cùng archive. Cách này cần plugin hoặc bước đóng gói riêng; lệnh `jar` cơ bản không tự phân giải và copy dependency.

## 2. Manifest và metadata

Manifest là file text tại `META-INF/MANIFEST.MF`. Phần đầu (main section) chứa thuộc tính áp dụng cho toàn archive; các section sau có thể chứa thuộc tính riêng cho từng entry.

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: JAR Artifact Demo
Implementation-Version: 1.2.3
Automatic-Module-Name: com.example.jardemo

```

Các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `Manifest-Version` | Phiên bản định dạng manifest |
| `Main-Class` | Class có `public static void main(String[] args)` để chạy bằng `java -jar` |
| `Class-Path` | Danh sách relative URL tới JAR/thư mục dependency bên ngoài |
| `Implementation-Title` | Tên sản phẩm hoặc module |
| `Implementation-Version` | Version của implementation |
| `Implementation-Vendor` | Nhà cung cấp |
| `Specification-Title`, `Specification-Version` | Metadata về API specification |
| `Automatic-Module-Name` | Tên ổn định khi JAR không có `module-info.class` được dùng như automatic module |
| `Multi-Release: true` | Đánh dấu multi-release JAR |

Manifest phải có dòng trống để kết thúc main section. Header được viết theo dạng `Name: value`; tên header không phân biệt hoa/thường. Dòng dài được manifest format wrap bằng continuation line bắt đầu bằng một dấu cách. Khi có metadata dài hoặc Unicode, nên để `jar`, Gradle hoặc Maven sinh manifest thay vì tự ghép file text.

### Main-Class và executable JAR

`Main-Class` chỉ định entry point, không phải tên file `.class` và không có phần mở rộng `.class`.

Khi manifest có `Main-Class`, có thể chạy:

```bash
java -jar jar-demo-1.2.3.jar
```

Nếu thiếu `Main-Class`, lệnh trên không biết class nào cần chạy và sẽ báo lỗi. Một library JAR thông thường không cần `Main-Class`; ứng dụng command-line mới thường cần.

### Class-Path trong manifest

`Class-Path` dùng các relative URL, phân tách bằng dấu cách, tính tương đối với vị trí của JAR chứa manifest.

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Class-Path: lib/logging.jar lib/http-client.jar
```

Khi ứng dụng được chạy bằng `java -jar`, launcher có thể tìm các thư viện ở những vị trí tương đối đó. Các file dependency phải thực sự được phân phối đúng cấu trúc. `Class-Path` không copy dependency vào JAR và không thay thế việc quản lý version của dependency.

Không nhầm `Class-Path` trong manifest với `-cp`/`-classpath` trên command line. Khi dùng `java -jar`, launcher lấy entry point và classpath bổ sung từ manifest; cách chạy với `-cp` là một mode khác.

## 3. Tạo JAR trực tiếp bằng JDK

JDK cung cấp `jar` để tạo, liệt kê, cập nhật, giải nén, mô tả module và kiểm tra archive.

Một chương trình mẫu:

Tệp `src/main/java/com/example/HelloApp.java`:

```java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class HelloApp {
    private HelloApp() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                 HelloApp.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                    "app.properties is missing from the JAR"
                );
            }

            properties.load(
                new InputStreamReader(input, StandardCharsets.UTF_8)
            );
        }

        System.out.println("Hello from executable JAR");
        System.out.println("app.name=" + properties.getProperty("app.name"));
        System.out.println(
            "app.version=" +
            HelloApp.class.getPackage().getImplementationVersion()
        );
    }
}
```

Tệp `src/main/resources/app.properties`:

```properties
app.name=jar-demo
```

Đặt manifest ở project root, tệp `MANIFEST.MF`:

```text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp
Implementation-Title: JAR Artifact Demo
Implementation-Version: 1.2.3
Automatic-Module-Name: com.example.jardemo

```

Biên dịch source thành Java 17 bytecode và tạo JAR:

```bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/example/HelloApp.java

jar --create \
  --file build/jar-demo-1.2.3.jar \
  --manifest MANIFEST.MF \
  -C build/classes . \
  -C src/main/resources .
```

`-C directory .` chuyển working directory của thao tác đóng gói sang thư mục đó rồi đưa nội dung vào archive. Nhờ vậy, JAR có entry `com/example/HelloApp.class` và `app.properties`, không chứa cả đường dẫn tuyệt đối trên máy build.

Có thể đặt timestamp cố định cho archive bằng JDK hỗ trợ tùy chọn `--date`:

```bash
jar --create \
  --file build/jar-demo-1.2.3.jar \
  --manifest MANIFEST.MF \
  --date=2026-11-10T00:00:00Z \
  -C build/classes . \
  -C src/main/resources .
```

Timestamp cố định là một phần của reproducible archive; muốn byte-for-byte reproducible còn phải cố định source, toolchain, file order, metadata và dependency.

### Các thao tác jar thường dùng

| Mục đích | Lệnh |
| --- | --- |
| Tạo archive | `jar --create --file app.jar -C classes .` |
| Tạo executable JAR | `jar --create --file app.jar --main-class com.example.Main -C classes .` |
| Liệt kê nội dung | `jar --list --file app.jar` |
| Xem chi tiết | `jar --list --verbose --file app.jar` |
| Cập nhật/thêm entry | `jar --update --file app.jar -C resources .` |
| Giải nén toàn bộ | `jar --extract --file app.jar --dir extracted` |
| Giải nén entry chọn lọc | `jar --extract --file app.jar com/example/Main.class` |
| Mô tả module | `jar --describe-module --file app.jar` |
| Kiểm tra cấu trúc | `jar --validate --file app.jar` |

`--create`, `--list`, `--update`, `--extract` là các operation mode. `-C` xác định thư mục làm gốc cho các file tiếp theo trong lệnh. Có thể dùng `@argfile` để đọc option và danh sách file từ text file khi command line quá dài.

Sau khi tạo archive, kiểm tra nội dung và chạy thử:

```bash
jar --list --file build/jar-demo-1.2.3.jar
jar --validate --file build/jar-demo-1.2.3.jar
java -jar build/jar-demo-1.2.3.jar
```

Output của chương trình mẫu:

```text
Hello from executable JAR
app.name=jar-demo
app.version=1.2.3
```

Đây là output đã kiểm tra trên JDK 24.0.2 với class được biên dịch bằng `javac --release 17`.

### Extract và update

Giải nén vào thư mục riêng:

```bash
jar --extract --file build/jar-demo-1.2.3.jar --dir build/extracted
```

Sau đó có thể đọc `build/extracted/META-INF/MANIFEST.MF` hoặc kiểm tra resource. Không giải nén archive không tin cậy vào thư mục chứa source hoặc file quan trọng. `jar --validate` kiểm tra một số vấn đề về duplicate entry và đường dẫn, nhưng không thay thế quy trình kiểm tra nguồn gốc và bảo mật artifact.

`jar --update` thêm hoặc thay entry trong archive. Mỗi lần sửa JAR sau khi đã ký sẽ làm chữ ký không còn khớp; phải tạo lại chữ ký sau khi hoàn tất mọi bước thay đổi.

## 4. Thin JAR, executable JAR và fat JAR

Ba kiểu đóng gói thường gặp:

| Kiểu | Nội dung | Cách chạy |
| --- | --- | --- |
| Library/thin JAR | Class và resource của module | Đưa vào classpath hoặc module path |
| Executable/thin JAR | Class/resource + `Main-Class`; dependency bên ngoài | `java -jar` cùng manifest Class-Path hoặc runtime classpath |
| Fat/uber JAR | Class/resource ứng dụng và dependency đã gom | Thường `java -jar` nếu manifest có Main-Class |

### Thin JAR với dependency ngoài

Có thể chạy ứng dụng bằng classpath:

```bash
# Linux/macOS: path-list separator là dấu :
java -cp "build/jar-demo.jar:lib/*" com.example.HelloApp
```

```powershell
# Windows: path-list separator là dấu ;
java -cp "build\\jar-demo.jar;lib/*" com.example.HelloApp
```

Trong dự án thực tế, nên để Gradle/Maven quản lý dependency và runtime classpath thay vì tự ghép command line. Separator khác nhau theo OS; dấu `:` không dùng được làm classpath separator trên Windows.

### Fat/uber JAR

Gradle Java Plugin và Maven JAR Plugin mặc định tạo JAR của project. Để đóng gói dependency, thường dùng Gradle Shadow Plugin hoặc Maven Shade Plugin.

Khi tạo fat JAR, cần chú ý:

- Tránh đưa nhiều phiên bản cùng một class vào archive.
- Xử lý xung đột resource có cùng đường dẫn.
- Gộp đúng file `META-INF/services/*` để `ServiceLoader` vẫn tìm thấy provider.
- Kiểm tra license và notice của dependency.
- Không giữ signature file cũ của dependency đã được thay đổi hoặc gộp; ký lại artifact cuối nếu cần.
- Chỉ relocate package khi hiểu ảnh hưởng tới reflection, service loader và tên class được cấu hình bằng chuỗi.

Fat JAR thuận tiện cho deployment đơn giản nhưng có thể lớn hơn, khó kiểm soát trùng dependency và khó cập nhật từng thư viện. Với ứng dụng server, có thể phân phối thin JAR cùng thư mục `lib/` hoặc dùng application distribution/container image.


## 5. Tạo JAR bằng Gradle

Gradle Java Plugin tạo task `jar` từ output của source set `main`, gồm compiled classes và resources. Task mặc định ghi archive vào `build/libs/`.

Ví dụ `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.named('jar', Jar) {
    archiveBaseName = 'jar-demo'

    manifest {
        attributes(
            'Main-Class': 'com.example.HelloApp',
            'Implementation-Title': 'JAR Artifact Demo',
            'Implementation-Version': project.version,
            'Automatic-Module-Name': 'com.example.jardemo'
        )
    }
}
```

Chạy:

```bash
./gradlew clean jar
java -jar build/libs/jar-demo-1.2.3.jar
```

Trên Windows PowerShell, dùng `.\\gradlew.bat clean jar`.

Gradle tạo:

```text
build/libs/jar-demo-1.2.3.jar
```

Có thể tùy chỉnh tên archive bằng:

- `archiveBaseName`: tên artifact.
- `archiveVersion`: version.
- `archiveClassifier`: classifier như `sources`, `tests` hoặc `all`.
- `archiveExtension`: phần mở rộng.
- `destinationDirectory`: thư mục đích.

Gradle `Jar` task hỗ trợ `manifest { attributes(...) }` để thêm metadata. Với Gradle 9, archive tasks có file order xác định và timestamp cố định theo mặc định, hỗ trợ reproducible archives.

## 6. Tạo JAR bằng Maven

Maven project có packaging mặc định là `jar` nếu không khai báo packaging khác. Lifecycle phase `package` gọi Maven JAR Plugin để đóng gói compiled classes và resources.

Ví dụ `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>jar-demo</artifactId>
  <version>1.2.3</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.HelloApp</mainClass>
              <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
            </manifest>
            <manifestEntries>
              <Automatic-Module-Name>com.example.jardemo</Automatic-Module-Name>
            </manifestEntries>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Chạy:

```bash
mvn --batch-mode clean package
java -jar target/jar-demo-1.2.3.jar
```

Trên Maven, JAR nằm ở `target/jar-demo-1.2.3.jar`. `maven-jar-plugin` hỗ trợ cấu hình manifest, includes/excludes và timestamp cho reproducible archive.

Gradle và Maven cùng tạo archive từ `src/main/java` và `src/main/resources`, nhưng cấu hình task/plugin khác nhau. Hãy cố định version plugin/build tool để kết quả ổn định giữa local và CI.

## 7. Artifact coordinates, version và classifier

Tên file chỉ là một phần của định danh artifact. Trong Maven repository, tọa độ phổ biến là:

```text
groupId:artifactId:version[:classifier]:extension
```

Ví dụ:

```text
com.example:jar-demo:1.2.3
com.example:jar-demo:1.2.3:sources
com.example:jar-demo:1.2.3:javadoc
```

Các thành phần:

- `groupId`: namespace/nhóm tổ chức, thường dựa trên reverse domain.
- `artifactId`: tên module hoặc library.
- `version`: version phát hành.
- `classifier`: phân biệt biến thể như `sources`, `javadoc`, `tests`, `linux-x86_64`.
- `extension`: loại file, ví dụ `jar`, `pom`, `zip`.

Một repository có thể lưu JAR, POM hoặc Gradle module metadata, checksum và signature cạnh nhau. Metadata cho biết dependency và variant cần resolve; không nên chỉ tải một file JAR rồi tự suy luận dependency graph.

### Quy tắc versioning

- Release version như `1.2.3` nên được xem là bất biến sau khi publish.
- Snapshot/pre-release version như `1.3.0-SNAPSHOT` dành cho quá trình phát triển; repository có thể cập nhật snapshot metadata/artifact.
- Classifier không thay thế version. `jar-demo-1.2.3-tests.jar` vẫn là biến thể test của version `1.2.3`.
- Không ghi đè artifact release đã phát hành; tạo version mới khi binary thay đổi.
- Gắn build metadata hoặc commit ID vào manifest khi cần truy vết build, nhưng không để thông tin bí mật trong metadata.

## 8. Local install và publish repository

Với Maven:

```bash
# Đóng gói artifact
mvn clean package

# Cài artifact vào local Maven repository để project khác trên máy dùng thử
mvn install

# Publish lên repository đã cấu hình trong distributionManagement
mvn deploy
```

`install` ghi artifact vào local repository của user. `deploy` upload artifact lên remote repository theo cấu hình và credentials. Không đưa password/token vào `pom.xml` hoặc commit vào Git; dùng `settings.xml`, secret manager hoặc CI environment.

Với Gradle, dùng `maven-publish`:

```groovy
plugins {
    id 'java'
    id 'maven-publish'
}

group = 'com.example'
version = '1.2.3'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'internal'
            url = uri(System.getenv('MAVEN_REPO_URL'))

            credentials {
                username = System.getenv('MAVEN_REPO_USER')
                password = System.getenv('MAVEN_REPO_PASSWORD')
            }
        }
    }
}
```

Chạy `publish` để publish tới repository đã cấu hình; `publishToMavenLocal` dùng local Maven repository. Ví dụ này dùng environment variables cho URL và credentials; cần cung cấp các giá trị đó trong CI secret settings, không ghi secret trực tiếp trong build file.

Trước khi publish, kiểm tra tọa độ, version, manifest, dependency metadata, JAR contents và checksum. Không publish artifact từ build thất bại hoặc từ source revision không xác định.

## 9. Modular JAR và Automatic-Module-Name

Từ Java 9, JAR có thể là explicit modular JAR nếu `module-info.class` nằm ở root archive.

Ví dụ `src/main/java/module-info.java`:

```java
module com.example.jardemo {
    exports com.example;
}
```

Biên dịch module:

```bash
javac --release 17 \
  -d build/module-classes \
  src/main/java/module-info.java \
  src/main/java/com/example/HelloApp.java

jar --create \
  --file build/jar-demo-module.jar \
  --main-class com.example.HelloApp \
  --module-version 1.2.3 \
  -C build/module-classes .
```

Xem descriptor:

```bash
jar --describe-module --file build/jar-demo-module.jar
```

Chạy module:

```bash
java --module-path build/jar-demo-module.jar \
  --module com.example.jardemo
```

`module-info.class` xác định tên module, các module phụ thuộc, package export/open, service `uses` và `provides`. `--module-version` ghi version vào module descriptor của modular JAR.

Một JAR không có `module-info.class` nhưng có `Automatic-Module-Name` có thể được đặt trên module path dưới tên automatic module đó. Nếu không có thuộc tính này, tên automatic module được suy ra từ tên JAR; việc đổi tên file có thể làm thay đổi tên module. Library muốn hỗ trợ module path lâu dài nên cân nhắc tên module ổn định.

## 10. Multi-release JAR

Multi-release JAR cho phép một artifact hỗ trợ nhiều major release của Java. Class tương thích nền tảng cũ nằm ở root; implementation dành cho release mới hơn nằm dưới `META-INF/versions/N/`.

Ví dụ cấu trúc:

```text
multi-release.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 21/
│           └── com/example/RuntimeFeature.class
└── com/example/RuntimeFeature.class
```

Manifest cần có:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Tạo archive bằng `jar --release`:

```bash
jar --create \
  --file build/library.jar \
  --manifest MANIFEST.MF \
  -C build/classes-base . \
  --release 21 \
  -C build/classes-21 .
```

Khi chạy trên Java 21 hoặc mới hơn, class loader chọn implementation version phù hợp nhất với runtime, rồi fallback về versioned directory thấp hơn và cuối cùng là root. Java 17 sẽ dùng bản root nếu không có version 17 phù hợp.

Lưu ý:

- `N` phải là Java release từ 9 trở lên.
- Manifest phải có `Multi-Release: true`; chỉ đặt file vào `META-INF/versions/` chưa đủ.
- Public/protected API của các version phải tương thích theo JAR specification.
- Resource trong `META-INF` không được version theo cơ chế multi-release.
- Dùng `jar --validate --file library.jar` để kiểm tra một số điều kiện và API consistency.
- Không tạo multi-release JAR chỉ để chứa file khác OS; hãy dùng classifier hoặc artifact riêng cho native binary.

Multi-release JAR hữu ích khi library cần tận dụng API mới trên JDK mới nhưng vẫn duy trì runtime baseline cũ.


## 11. Kiểm tra nội dung và chất lượng JAR

Trước khi phát hành, hãy kiểm tra archive thay vì chỉ dựa vào việc task `package` kết thúc thành công.

### Kiểm tra file và manifest

```bash
jar --list --verbose --file build/jar-demo-1.2.3.jar
jar --describe-module --file build/jar-demo-1.2.3.jar
```

Có thể extract manifest để xem `Main-Class`, version, module name, classpath và các thuộc tính khác. Xác nhận resource nằm ở đúng vị trí mà code dùng `Class.getResourceAsStream()` hoặc `ClassLoader.getResource()` truy cập.

### Chạy từ archive thực tế

Chạy JAR trong một working directory khác với thư mục classes của build. Điều này giúp phát hiện code vô tình đọc resource từ filesystem source thay vì resource đã đóng gói.

```bash
java -jar build/jar-demo-1.2.3.jar
```

Với library, tạo consumer test nhỏ để resolve dependency từ repository, compile và chạy thử API. Một JAR có thể chứa đủ class của project nhưng vẫn thiếu dependency hoặc metadata cần thiết cho consumer.

### Kiểm tra checksum

Tạo SHA-256 checksum để xác nhận hai bản sao có cùng byte:

```bash
sha256sum build/jar-demo-1.2.3.jar
```

PowerShell:

```powershell
Get-FileHash .\\build\\jar-demo-1.2.3.jar -Algorithm SHA256
```

Checksum giúp phát hiện file bị thay đổi khi truyền/lưu trữ nếu giá trị kỳ vọng đến từ kênh đáng tin. Một checksum tải cùng từ chính nơi không đáng tin không tự chứng minh nguồn gốc artifact.

## 12. Ký số và xác minh JAR

`jarsigner` dùng private key và certificate để ký JAR; `jarsigner -verify` kiểm tra chữ ký và tính toàn vẹn các entry đã ký.

Tạo keystore cho môi trường thử nghiệm:

```bash
keytool -genkeypair \
  -alias release-key \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -keystore release.p12 \
  -storetype PKCS12
```

Ký archive sau khi đã hoàn tất mọi bước đóng gói:

```bash
jarsigner \
  -keystore release.p12 \
  build/jar-demo-1.2.3.jar \
  release-key
```

Xác minh:

```bash
jarsigner -verify -verbose -certs build/jar-demo-1.2.3.jar
```

Khi dùng release thật:

- Bảo vệ private key bằng secret store hoặc HSM theo chính sách tổ chức.
- Dùng certificate chain được bên nhận tin cậy.
- Cân nhắc timestamp authority để chữ ký vẫn có thể được kiểm tra sau khi certificate hết hạn.
- Xác minh chữ ký và trust chain; thông báo `jar verified` với self-signed certificate không có nghĩa signer đã được tin cậy.
- Không chỉnh sửa JAR sau khi ký; thay đổi manifest, class hoặc resource làm signature verification thất bại.
- Ký đúng artifact cuối cùng được publish, không ký một bản rồi upload một bản khác.

Chữ ký số xác minh integrity và danh tính signer theo certificate trust model. SHA-256 checksum và chữ ký số phục vụ mục đích khác nhau; release pipeline có thể dùng cả hai.

## 13. Reproducible JAR

Reproducible build nghĩa là cùng source, toolchain, dependency và build instructions tạo ra artifact có byte giống nhau. Điều này giúp xác minh binary có đúng được tạo từ source đã review hay không.

Những yếu tố thường làm JAR khác nhau:

- Timestamp của từng ZIP entry.
- Thứ tự file trong archive.
- Version compiler/build plugin.
- Dependency không được pin hoặc thay đổi theo thời gian.
- Manifest có build timestamp hoặc metadata biến động.
- Generated resource chứa đường dẫn tuyệt đối hoặc thông tin máy build.

Với JDK `jar`, có thể dùng `--date` để đặt timestamp entry cố định.

Gradle 9 mặc định tạo reproducible archives với file order xác định và timestamp cố định. Với Gradle cũ hơn hoặc muốn khai báo rõ:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Với Maven, đặt `project.build.outputTimestamp` và dùng plugin hỗ trợ reproducible output:

```xml
<properties>
  <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Để kiểm tra, build hai lần trong môi trường tương đương và so sánh SHA-256. Nếu hash khác, kiểm tra archive entry timestamps/order, manifest, generated files, tool versions và dependency resolution.

## 14. Troubleshooting JAR artifact

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `no main manifest attribute` | Manifest thiếu `Main-Class` | Thêm `Main-Class` và rebuild |
| `Could not find or load main class` | Tên class sai hoặc class không có trong JAR | Kiểm tra `jar --list`, package và manifest |
| `NoClassDefFoundError` | Thiếu dependency runtime | Cung cấp classpath, manifest Class-Path hoặc fat JAR |
| Resource trả về `null` | Resource không được đóng gói hoặc path sai | Kiểm tra entry và dùng classpath resource API |
| `ClassNotFoundException` chỉ trên Linux | Sai chữ hoa/thường trong entry hoặc classpath | Kiểm tra package và tên file chính xác |
| `Invalid signature file digest` | JAR bị sửa sau khi ký hoặc signature file cũ bị đóng gói lại | Xóa signature cũ phù hợp, tạo archive cuối và ký lại |
| Module not found | Module path sai hoặc module name khác dự kiến | Dùng `jar --describe-module` và kiểm tra module descriptor |
| Runtime không chọn versioned class | Thiếu `Multi-Release: true` hoặc version path sai | Kiểm tra manifest và `META-INF/versions/N` |
| Archive khác hash giữa hai build | Timestamp/order/metadata/toolchain thay đổi | Cấu hình reproducible build và cố định toolchain |
| JAR quá lớn | Gộp dependency/resource không cần thiết | Kiểm tra contents, exclude file và xem lại fat JAR |
| Duplicate classes/resources | Nhiều dependency chứa cùng entry | Kiểm tra dependency graph, exclusion và shading |
| Consumer không resolve dependency | Chỉ publish JAR, thiếu POM/module metadata hoặc tọa độ sai | Publish bằng Maven/Gradle và xác minh repository metadata |
| JAR có resource nhưng ứng dụng không đọc được | Dùng filesystem path thay cho classpath resource | Dùng `getResourceAsStream()` hoặc `ClassLoader` |

## 15. Quy trình quản lý JAR artifact trước release

1. Xác định `groupId`, `artifactId`, version và classifier.
2. Chọn JDK/compiler release và pin Gradle/Maven/plugin version.
3. Compile, test và tạo JAR bằng build task.
4. Kiểm tra manifest, class, resource, module descriptor và dependency metadata.
5. Chạy thử executable JAR hoặc consumer test cho library.
6. Chạy `jar --validate` khi phù hợp.
7. Kiểm tra licenses, secret, dependency vulnerabilities và nội dung không được phép phát hành.
8. Tạo checksum và SBOM theo release policy.
9. Ký đúng archive cuối cùng nếu quy trình yêu cầu.
10. Publish JAR cùng metadata vào repository.
11. Xác nhận artifact đã resolve và tải lại được từ repository.
12. Lưu checksum, signature, build logs, commit ID và release provenance.

Không publish artifact từ workspace chưa biết trạng thái hoặc từ build mà test/verification thất bại. Artifact release nên gắn với source revision cụ thể và không bị ghi đè sau khi công bố.

## 16. Ghi nhớ

- JAR là ZIP archive chứa class, resource và metadata; entry bên trong dùng dấu `/`.
- `META-INF/MANIFEST.MF` chứa `Main-Class`, `Class-Path`, version và module metadata.
- `java -jar` cần `Main-Class`; library JAR thường không cần entry point.
- JAR thông thường không tự chứa dependency; phân biệt thin JAR và fat/uber JAR.
- `jar --create`, `--list`, `--update`, `--extract`, `--describe-module` và `--validate` là các thao tác chính.
- Gradle Java Plugin tạo task `jar`; Maven JAR Plugin đóng gói ở phase `package`.
- Artifact coordinates và classifier giúp repository phân biệt version và biến thể.
- `module-info.class` tạo explicit modular JAR; `Automatic-Module-Name` đặt tên ổn định cho automatic module.
- Multi-release JAR cần `Multi-Release: true` và cấu trúc `META-INF/versions/N/`.
- SHA-256 kiểm tra byte; `jarsigner` ký và xác minh integrity/signer certificate.
- Reproducible build giúp tạo lại archive byte-for-byte từ cùng đầu vào.
- Kiểm tra nội dung và chạy thử JAR thật trước khi publish.

JAR artifact là đầu ra có thể triển khai và chia sẻ của Java build. Khi cấu trúc archive, manifest, dependency, version, signature và provenance được quản lý rõ ràng, artifact sẽ dễ chạy, dễ kiểm tra và đáng tin cậy hơn trong toàn bộ vòng đời phát triển.

## Tài liệu tham khảo

- [The jar Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [JAR File Specification — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
- [The jarsigner Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Gradle: Building Java & JVM Projects — JAR manifest](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle Jar Task DSL](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle: Reproducible archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Apache Maven JAR Plugin 3.4.2](https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/plugin-info.html)
- [Maven: Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
