# Tránh lọc nhầm tệp nhị phân hoặc đóng gói bí mật trong Maven

## 1. Hai rủi ro khác nhau, một vùng cấu hình dễ bị hiểu nhầm

Maven thường xử lý **resource** — những tệp không phải mã Java như `.properties`, `.xml`, ảnh, PDF hoặc dữ liệu đi kèm chương trình — trước khi đóng gói JAR/WAR. Maven Resources Plugin có thể **sao chép nguyên byte** hoặc **resource filtering**, tức mở tệp dạng văn bản rồi thay các biểu thức theo biến Maven.

Hai lỗi nghiêm trọng dễ xuất hiện khi cấu hình quá rộng:

1. **Tệp nhị phân bị filtering như văn bản:** nội dung ảnh, font, PDF, tệp nén hoặc dữ liệu byte có thể bị đổi/giải mã sai, dẫn tới file hỏng sau build. Một lỗi không nhất thiết xuất hiện ở phase `process-resources`; chương trình có thể chỉ gặp lỗi lúc mở file.
2. **Tệp nhạy cảm bị copy hoặc đóng gói:** `.env`, private key, mật khẩu, file credentials, cấu hình môi trường hoặc token vô tình nằm trong thư mục được Maven copy tới `target/classes`, rồi được đưa vào JAR/WAR, image container hoặc artifact phát hành.

**Điểm mấu chốt:** **`<filtering>false</filtering>` bảo vệ tính nguyên vẹn byte, KHÔNG bảo vệ bí mật.** Một tệp `.p12` được sao chép nguyên byte vẫn có thể bị lộ nếu đi vào artifact. Ngược lại, `<excludes>` hoặc allowlist mới quyết định file có được chọn để copy/đóng gói hay không; chúng không phải cơ chế mã hóa.

**Nguyên tắc an toàn:** chỉ filter những tệp văn bản thật sự cần biến đổi; chỉ copy những tài nguyên công khai đã được chấp thuận; cấp secret từ môi trường chạy/secret manager thay vì nhúng vào build output. Sau khi đóng gói, **kiểm tra artifact thật**, không chỉ nhìn POM hoặc `.gitignore`.

## 2. Maven xử lý tài nguyên ở giai đoạn nào?

Với packaging `jar` thông thường, dòng chảy khái quát là:

~~~text
src/main/resources hoặc thư mục resources tùy chỉnh
        |
        | maven-resources-plugin:resources
        | phase: process-resources
        v
target/classes/
        |
        | compiler:compile -> class Java cũng vào target/classes
        v
maven-jar-plugin:jar (thường ở package)
        |
        v
target/<artifactId>-<version>.jar
~~~

Đối với test:

~~~text
src/test/resources/
        |
        | maven-resources-plugin:testResources
        | phase: process-test-resources
        v
target/test-classes/
        |
        | testCompile + surefire:test
        v
Kiểm thử (không tự mặc định đóng trong JAR chính)
~~~

Theo Maven, `src/main/resources` thường được **copy không lọc** khi không cấu hình gì đặc biệt. Nếu dự án thiết lập `<filtering>true</filtering>` hoặc thêm custom execution, quy tắc có thể thay đổi.

**Không đồng nhất ba nơi:**

- **Thư mục nguồn** (`src/main/resources`): nơi developer chọn tệp đầu vào.
- **Thư mục staging** (`target/classes`): nơi các nguồn được copy/biên đổi để biên dịch, chạy và đóng gói.
- **Artifact cuối** (JAR/WAR/ZIP/image): thứ người dùng hoặc hệ thống khác nhận được; cần kiểm tra nội dung thật.

Mặc dù `src/test/resources` không tự đi vào JAR chính theo binding mặc định, nó có thể xuất hiện trong test JAR, test report, Docker build context hoặc artifact CI nếu pipeline copy toàn bộ `target/` hoặc cấu hình plugin khác. Vì vậy **không lưu secret thật trong test resources rồi cho rằng chắc chắn an toàn**.

## 3. Filtering làm gì với dữ liệu?

Một tệp văn bản:

~~~properties
app.name=@project.name@
app.version=@project.version@
~~~

nếu được resource filtering với delimiter `@` và project có tên/version, có thể trở thành:

~~~properties
app.name=Resource Guard Demo
app.version=1.0.0
~~~

Maven Resources Plugin có thể xử lý các token như `@name@` hoặc `${name}` theo cấu hình delimiter, project properties, filters và user/system properties. **Đừng dùng filtering cho mọi file chỉ vì có vài file `.properties` cần thay giá trị.**

Khi filtering tệp, plugin phải xử lý nội dung theo **character encoding**, tìm biểu thức và ghi lại dữ liệu. Với binary, những byte không hợp lệ dưới encoding chọn hoặc byte tình cờ trông như delimiter có thể gây lỗi hoặc làm nội dung đầu ra khác bản gốc.

Ví dụ một file PDF có thể chứa các byte không phải UTF-8; file ZIP, JAR, PNG, font `.woff2`, protobuf `.bin` hoặc keystore có thể chứa dữ liệu trông như chuỗi token. **Đọc-ghi qua bộ lọc văn bản không phải thao tác copy nhị phân an toàn.**

### Định dạng ảnh mặc định được tránh filter

Apache Maven Resources Plugin nêu năm extension mặc định được bảo vệ khỏi binary filtering:

~~~text
jpg, jpeg, gif, bmp, png
~~~

Plugin còn có `nonFilteredFileExtensions` để bổ sung extension khác như `pdf`, `bin`.

**Đừng suy ra mọi binary đều được bảo vệ.** PDF, ZIP, font, `.p12`, `.jks`, `.docx` hoặc một format do tổ chức tự tạo có thể không nằm trong danh sách mặc định. Với tài nguyên nhị phân, **đặt `<filtering>false</filtering>` ở resource set** vẫn là cách rõ ràng hơn so với mong extension list nhận diện hết.

**Đặc biệt:** keystore hoặc private key cũng là bí mật. Đánh dấu extension `p12` là `nonFilteredFileExtension` chỉ tránh làm hỏng bytes nếu bị copy, **không có nghĩa được phép đóng gói** tệp đó.

## 4. Copy đúng file khác với filter đúng file

Maven Resources Plugin có hai trục cấu hình độc lập:

| Câu hỏi | Cơ chế | Thí dụ |
| --- | --- | --- |
| **Tệp nào được chọn để copy?** | `resources/resource/includes` hoặc `excludes` | Chỉ `config/app.properties` và ảnh công khai. |
| **Tệp đã chọn có thay biến không?** | `<filtering>true/false</filtering>` | Chỉ filter text metadata. |
| **Một extension không được filter nếu resource set lọc?** | `nonFilteredFileExtensions` | Bổ sung `pdf`, `bin` như lớp bảo vệ phụ. |
| **Encoding của tệp text được filter?** | `encoding`, `propertiesEncoding` | Chọn UTF-8 cho text thông thường; riêng Java Properties qua `InputStream` cần chú ý ISO-8859-1. |
| **Tệp nào được JAR Plugin đưa từ classesDirectory vào JAR?** | JAR Plugin `includes`/`excludes` | Chặn lần cuối các path nhạy cảm trong staging. |
| **Tệp nào có trong artifact CI/Docker?** | CI publication, Dockerfile, Assembly/Shade, distribution configs | Audit riêng cho từng artifact đầu ra. |

Nếu một file là secret, **đừng copy nó vào staging**, dù đang filtering false. Nếu là binary công khai, **có thể copy nhưng không filter**. Nếu là text metadata công khai cần thay version, **có thể filter sau khi giới hạn tập file đầu vào**.

### Vì sao allowlist thường an toàn hơn denylist?

Một denylist chỉ viết:

~~~xml
<excludes>
    <exclude>**/.env</exclude>
    <exclude>**/*.pem</exclude>
</excludes>
~~~

có thể bỏ sót tên file mới như `prod.credentials.json`, `vault-export.txt` hoặc file sao lưu. Đoạn trên chỉ là **cấu hình minh họa đặt trong một `<resource>`**, chưa đủ an toàn nếu mặc định copy mọi file còn lại.

**Allowlist** chỉ chấp nhận tài nguyên có mục đích đã biết. Ví dụ `config/app.properties` (public metadata) được filter; các ảnh trong `assets/public/` được copy nguyên byte. Một file `config/admin-token.properties` không nằm trong allowlist sẽ không đi theo đường copy đã khai báo.

Tuy nhiên allowlist **không tự xác minh nội dung file**. Nếu ai đó cố đưa secret vào `config/app.properties`, chính file được phép copy vẫn gây rò rỉ. Vì thế phải có **review nội dung, secret scanning và kiểm tra artifact**.

## 5. Thư mục nguồn: tách public resource và private configuration

Một cấu trúc dễ kiểm soát:

~~~text
resource-guard-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/vn/example/resources/ResourceCheck.java
│   │   ├── resources-filtered/
│   │   │   └── config/app.properties       (text metadata công khai)
│   │   └── resources/
│   │       └── assets/public/              (binary công khai; tùy chọn)
│   └── test/
│       └── java/vn/example/resources/ResourceCheckTest.java
└── tools/
    ├── CreateFixture.java                 (công cụ tạo binary mẫu)
    └── ArtifactAudit.java                 (kiểm tra JAR đầu ra)
~~~

Ở đây:

- **`resources-filtered`** chỉ chứa những tệp text được phép thay token. Chỉ `config/app.properties` nằm trong allowlist lọc.
- **`resources/assets/public`** chỉ dành cho những tệp binary được duyệt để phân phối; POM giới hạn các extension và đường dẫn.
- **`tools/`** nằm ngoài `src/main/resources`, nên bản thân source của công cụ kiểm tra không bị sao chép như resource.
- **Không có thư mục chứa secret thật trong ví dụ.** Không tạo file private key hoặc `.env` thật trong source tree để thử nghiệm.

**Bí mật runtime** nên nằm trong môi trường triển khai hoặc secret store được kiểm soát, chẳng hạn biến môi trường của process hoặc credential provider. Tên biến môi trường không tự biến dữ liệu thành an toàn; vẫn phải kiểm soát log, quyền, vòng đời và tránh in giá trị ra stdout.

## 6. POM Java 17 hoàn chỉnh: filter text cho phép, copy binary không lọc

Dưới đây là một **POM chạy được** với Maven 3.9+, JDK 17, các Maven Plugin được chốt version. Tài nguyên `config/app.properties` là metadata công khai; ảnh/PDF/fixture nhị phân nếu có được copy không lọc.

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>resource-guard-demo</artifactId>
    <version>1.0.0</version>
    <name>Resource Guard Demo</name>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <!-- Chỉ text metadata công khai được filter -->
            <resource>
                <directory>src/main/resources-filtered</directory>
                <filtering>true</filtering>
                <includes>
                    <include>config/app.properties</include>
                </includes>
            </resource>

            <!-- Binary công khai: copy nguyên bytes; không lọc -->
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
                <includes>
                    <include>assets/public/*.png</include>
                    <include>assets/public/*.jpg</include>
                    <include>assets/public/*.pdf</include>
                    <include>assets/public/fixture.bin</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <!-- Properties.load(InputStream) dùng ISO-8859-1 -->
                    <propertiesEncoding>ISO-8859-1</propertiesEncoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                    <nonFilteredFileExtensions>
                        <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
                        <nonFilteredFileExtension>bin</nonFilteredFileExtension>
                    </nonFilteredFileExtensions>
                </configuration>
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
                <version>3.4.2</version>
                <configuration>
                    <!-- Chặn thêm theo tên file ở tầng JAR, không thay allowlist -->
                    <excludes>
                        <exclude>**/.env</exclude>
                        <exclude>**/.env.*</exclude>
                        <exclude>**/*.pem</exclude>
                        <exclude>**/*.key</exclude>
                        <exclude>**/*.p12</exclude>
                        <exclude>**/*.jks</exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Điều gì được POM đảm bảo trong luồng build mặc định của ví dụ?**

1. Maven Resources Plugin chỉ chọn `config/app.properties` để filter từ `src/main/resources-filtered`.
2. Các file được chọn ở `src/main/resources/assets/public/` được copy **không filter**, dù có đuôi `.bin` hay `.pdf`.
3. File `.env`, `config/secret.properties` hay `credentials.json` đặt tùy tiện trong `src/main/resources` **không khớp allowlist trên**, nên **không được copy bởi hai resource entries này**.
4. JAR Plugin thêm **lớp excludes theo tên** cho một số dạng file nhạy cảm nếu chúng lọt vào classesDirectory từ nguồn khác. Đây chỉ là lớp bảo vệ phụ, không đủ nếu secret mang tên `app.properties` hay nằm trong nội dung file khác.
5. Phần `<filtering>true</filtering>` chỉ áp dụng cho resource set thứ nhất. Danh sách `nonFilteredFileExtensions` ở cấu hình plugin là **lớp phụ** khi có resource set nào được lọc; nó không tự quyết định file nào được copy và không thay thế `<filtering>false</filtering>`.
6. **JAR Plugin excludes được tính tương đối với `classesDirectory`**, tức với đường dẫn tệp trong output chứ không phải trực tiếp từ root Git repository.
7. Nếu dự án có parent/profile/other plugins tự copy file vào `target/classes` hoặc tạo JAR/WAR khác, kết quả phải được kiểm tra lại; POM này không thể bảo đảm an toàn cho mọi pipeline bên ngoài.

**Vì sao `propertiesEncoding=ISO-8859-1`?** Ví dụ sẽ đọc file bằng `java.util.Properties.load(InputStream)`, theo quy ước ISO-8859-1. Các giá trị của file mẫu đều ASCII, nên không có vấn đề mã hóa. Với `ResourceBundle` ở Java 9+ hoặc cách đọc text UTF-8 khác, quy tắc encoding có thể khác; không copy một cấu hình encoding sang mọi dự án mà không xét cách chương trình đọc properties.

**Vì sao delimiter chỉ là `@`?** Ví dụ chỉ cần `@project.name@` và `@project.version@`. Tắt default delimiters tránh vô tình xử lý `${...}` vốn có thể thuộc syntax của application framework. Đây là giảm rủi ro substitution, **không phải cơ chế ngăn tiết lộ secret nếu nội dung đã chứa secret**.

## 7. Tệp properties được phép filter và kết quả chính xác

Tạo **src/main/resources-filtered/config/app.properties**:

~~~properties
app.name=@project.name@
app.version=@project.version@
app.kind=public-metadata
~~~

Sau khi Maven chạy `process-resources`, file được tạo tại:

~~~text
target/classes/config/app.properties
~~~

với nội dung dự kiến:

~~~properties
app.name=Resource Guard Demo
app.version=1.0.0
app.kind=public-metadata
~~~

Các giá trị đều **không nhạy cảm**. Chúng nên là những thông tin mà bạn hoàn toàn chấp nhận cho người tải JAR xem được. `project.name` và `project.version` xuất phát từ POM.

Lưu ý `@project.name@` chỉ được thay khi **resource entry thật sự có `filtering=true`** và delimiter `@` được hỗ trợ/cấu hình. Nếu file vẫn chứa nguyên token sau build, cần kiểm tra `resources` entries, profile, plugin version và đường dẫn file đầu vào/đầu ra.

## 8. Chương trình Java 17 đọc resource sau filtering

Tạo **src/main/java/vn/example/resources/ResourceCheck.java**:

~~~java
package vn.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ResourceCheck {
    private ResourceCheck() {
    }

    public static Properties readPublicMetadata() throws IOException {
        Properties properties = new Properties();

        try (InputStream in = ResourceCheck.class.getResourceAsStream(
                "/config/app.properties")) {
            if (in == null) {
                throw new IOException("Missing public resource: config/app.properties");
            }
            properties.load(in);
        }

        return properties;
    }

    public static void main(String[] args) throws IOException {
        Properties metadata = readPublicMetadata();
        System.out.println("App: " + metadata.getProperty("app.name"));
        System.out.println("Version: " + metadata.getProperty("app.version"));
        System.out.println("Kind: " + metadata.getProperty("app.kind"));
    }
}
~~~

Chương trình đọc **chỉ metadata công khai** bằng classloader; không cần kết nối network hoặc secret. File `.properties` nằm tại `/config/app.properties` trên classpath sau `process-resources`.

### Test tự động cho nội dung được phép

Tạo **src/test/java/vn/example/resources/ResourceCheckTest.java**:

~~~java
package vn.example.resources;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ResourceCheckTest {
    @Test
    void resourceContainsOnlyExpectedPublicMetadata() throws IOException {
        Properties properties = ResourceCheck.readPublicMetadata();

        assertEquals("Resource Guard Demo", properties.getProperty("app.name"));
        assertEquals("1.0.0", properties.getProperty("app.version"));
        assertEquals("public-metadata", properties.getProperty("app.kind"));
        assertEquals(3, properties.size());
    }
}
~~~

Test này xác minh **ba key công khai** được lọc đúng, không có key thứ tư trong file mẫu. Nhưng nó **không tự kiểm tra mọi entry trong JAR**, không phát hiện secret nhúng ở một file được allowlist khác, và không thay thế secret scanner của CI. Việc kiểm tra artifact được tách riêng ở mục 11.

## 9. Build, chạy chương trình và kiểm tra JAR

Từ thư mục `resource-guard-demo/`:

~~~bash
mvn --version
mvn -B clean verify
java -cp target/classes vn.example.resources.ResourceCheck
~~~

Khi Maven/JDK/repository hợp lệ và đã tạo file theo mục 7–8, **stdout chính xác của riêng lệnh Java cuối** là:

~~~text
App: Resource Guard Demo
Version: 1.0.0
Kind: public-metadata
~~~

Lệnh `mvn clean verify` tự chạy `process-resources`, compile/test, package và verify theo packaging `jar`; nó **không tự chạy `ResourceCheck.main`**. Chương trình `java -cp ...` mới in ba dòng trên.

Dùng JDK `jar` để xem entry trong artifact:

~~~bash
jar tf target/resource-guard-demo-1.0.0.jar
~~~

Những entry quan trọng **phải có** gồm:

~~~text
config/app.properties
vn/example/resources/ResourceCheck.class
~~~

JAR còn có `META-INF` và metadata khác; **không nên so khớp toàn bộ `jar tf` với hai dòng mẫu**. Nếu đã tạo binary fixture hoặc ảnh công khai thì các entry thuộc `assets/public` cũng có thể xuất hiện.

Kiểm tra metadata trong JAR có thể làm bằng công cụ lưu trữ hỗ trợ mở entry text; đừng chỉ nhìn file gốc còn chứa `@project.name@`, vì artifact chứa **bản đã lọc**.

### Vì sao phải dùng clean trước khi audit?

Nếu build trước từng copy `config/secret.properties` vào `target/classes`, rồi bạn sửa POM để loại file đó mà chạy `mvn package` **không qua clean**, file cũ có thể còn nằm trong staging và JAR mới vẫn chứa nó. Chạy **`mvn clean verify` trước khi kiểm tra** giúp loại bỏ hầu hết stale outputs trong `target`.

**Không kết luận an toàn chỉ vì đã thêm exclude vào POM mà chưa build sạch và kiểm tra artifact thật.**

## 10. Thí nghiệm tệp nhị phân: tạo bytes và chứng minh không bị đổi

Binary có thể là ảnh, font, file nén, PDF hoặc một blob do hệ thống tạo. Để kiểm tra byte-for-byte mà không cần tải ảnh hoặc copy secret, ta tạo một **fixture `.bin` giả hoàn toàn công khai**.

Tạo **tools/CreateFixture.java** (độc lập, không nằm trong `src/main/java`):

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class CreateFixture {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("src/main/resources/assets/public/fixture.bin");
        Files.createDirectories(output.getParent());

        byte[] bytes = {0, 64, (byte) 0xFF, 10, 0, 35, 0, 13};
        Files.write(output, bytes);

        System.out.println("Binary fixture ready: " + bytes.length + " bytes");
    }
}
~~~

Với JDK 17, có thể chạy Java ở chế độ **single-file source**:

~~~bash
java tools/CreateFixture.java
mvn -B clean verify
~~~

**Stdout chính xác của lệnh Java đầu tiên:**

~~~text
Binary fixture ready: 8 bytes
~~~

Vì POM có `<include>assets/public/fixture.bin</include>` trong **resource không filter**, Maven copy nguyên byte sang:

~~~text
target/classes/assets/public/fixture.bin
~~~

và đưa nó vào JAR. Có thể so sánh hash SHA-256 giữa file nguồn và file staging:

**Linux/macOS:**

~~~bash
shasum -a 256 src/main/resources/assets/public/fixture.bin
shasum -a 256 target/classes/assets/public/fixture.bin
~~~

**Windows PowerShell:**

~~~powershell
Get-FileHash src\main\resources\assets\public\fixture.bin -Algorithm SHA256
Get-FileHash target\classes\assets\public\fixture.bin -Algorithm SHA256
~~~

**Hai giá trị hash phải giống nhau** nếu copy không làm thay bytes. Bản thân các giá trị hash cụ thể được tính từ file thật; không tự bịa một checksum rồi yêu cầu người đọc đối chiếu.

Một tệp `.bin` của ứng dụng thật **chỉ được đóng gói khi đã xác nhận nó công khai**. Keystore, private key hay database backup không được đưa vào `assets/public` chỉ vì chúng là binary.

## 11. Audit JAR sau package bằng một chương trình Java nhỏ

Cần kiểm tra **artifact cuối cùng**, vì một file có thể lọt vào `target/classes` từ plugin execution khác, generated resources, parent profile hoặc thao tác CI. Công cụ dưới đây **chỉ kiểm tra các tên entry đáng ngờ và sự hiện diện của metadata**, không giả vờ là secret scanner hoàn chỉnh.

Tạo **tools/ArtifactAudit.java** (single-file source, không được Maven đóng vào JAR chính):

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Locale;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class ArtifactAudit {
    private static boolean suspicious(String path) {
        String n = path.toLowerCase(Locale.ROOT);
        String base = n.substring(n.lastIndexOf('/') + 1);

        return base.equals(".env")
                || base.startsWith(".env.")
                || base.endsWith(".pem")
                || base.endsWith(".key")
                || base.endsWith(".p12")
                || base.endsWith(".jks")
                || base.contains("credential")
                || n.contains("/private/")
                || n.contains("/secrets/");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide a JAR path");
        }

        try (JarFile archive = new JarFile(args[0])) {
            if (archive.getEntry("config/app.properties") == null) {
                throw new IllegalStateException("Public metadata missing");
            }

            for (JarEntry entry : java.util.Collections.list(archive.entries())) {
                if (suspicious(entry.getName())) {
                    throw new IllegalStateException(
                            "Suspicious archive entry: " + entry.getName());
                }
            }

            Path original = Path.of(
                    "src/main/resources/assets/public/fixture.bin");
            JarEntry binary = archive.getJarEntry("assets/public/fixture.bin");

            if (Files.exists(original)) {
                if (binary == null) {
                    throw new IllegalStateException("Binary fixture missing");
                }
                try (var in = archive.getInputStream(binary)) {
                    if (!Arrays.equals(Files.readAllBytes(original),
                            in.readAllBytes())) {
                        throw new IllegalStateException("Binary bytes changed");
                    }
                }
            }
        }

        System.out.println("Artifact audit OK");
    }
}
~~~

Sau `mvn -B clean package`, chạy:

~~~bash
java tools/ArtifactAudit.java target/resource-guard-demo-1.0.0.jar
~~~

Nếu có `config/app.properties`, không có entry trùng tên nhạy cảm bị liệt kê và fixture được copy nguyên byte (nếu có), **stdout chính xác**:

~~~text
Artifact audit OK
~~~

Nếu tên entry đáng ngờ xuất hiện hoặc fixture bị thiếu/đổi bytes, chương trình ném exception và Java process kết thúc bằng mã lỗi, nên CI có thể xem bước audit là thất bại.

**Giới hạn rất quan trọng:** một secret có thể nằm trong `config/app.properties`, một tệp `public.json` hay metadata của ảnh nhưng **tên entry không đáng ngờ**. Công cụ chỉ là ví dụ kiểm tra tên và binary bytes, **không thay thế scanning nội dung, kiểm soát quyền và review dữ liệu đầu vào**.

Không nên in toàn bộ nội dung entry chứa secret ra CI log khi audit thất bại; tên file đôi khi cũng nhạy cảm, nên chính sách thực tế cần quyết định mức thông tin được báo cáo.

## 12. Cách cấu hình sai: filtering cả thư mục resources

Một anti-pattern thường gặp:

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

Đây là **đoạn POM minh họa, không dùng thay POM an toàn ở mục 6**. Nó có thể đưa mọi file nguồn trong thư mục vào `target/classes` và cố filter các file không thuộc danh sách binary extensions được tự bỏ qua. Nếu thư mục có `backup.zip`, `report.pdf`, `credentials.json`, `.env`, có hai vấn đề:

- File binary không nằm trong danh sách ngoại lệ có thể bị biến đổi hoặc lọc sai.
- File bí mật có thể được copy/đóng gói dù không bị filter.

Thêm `nonFilteredFileExtensions` có thể giải quyết một phần **rủi ro binary**, nhưng **không giải quyết rủi ro secret inclusion**.

### Sai lầm “tắt filtering là đã an toàn”

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <filtering>false</filtering>
</resource>
~~~

Cấu hình copy rộng như trên giữ nguyên bytes, nhưng nếu nguồn chứa secret, secret được copy nguyên trạng. **Đây là lỗi phân phối dữ liệu**, không phải lỗi encoding.

### Sai lầm “chặn ở JAR Plugin là đủ”

Nếu resource secret đã vào `target/classes`, JAR Plugin có thể loại một số file khỏi JAR, nhưng secret vẫn có thể bị lộ qua:

- `target/classes` bị upload thành CI artifact.
- Dockerfile `COPY target/ ...` hoặc Assembly/ZIP đóng gói rộng.
- Một plugin khác đóng WAR hoặc shaded JAR từ output.
- Log build, report, bộ nhớ cache hoặc file backup.

Tốt nhất là **không đưa secret vào inputs mà Maven có thể copy**. JAR exclusion là phòng tuyến cuối, không phải lớp bảo vệ duy nhất.

## 13. nonFilteredFileExtensions: hữu ích nhưng phạm vi hẹp

Khi có lý do kỹ thuật phải để cả text và binary trong một resource set có filtering, Maven Resources Plugin cho phép chỉ định **thêm** extension không áp dụng filtering:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <nonFilteredFileExtensions>
            <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
            <nonFilteredFileExtension>bin</nonFilteredFileExtension>
        </nonFilteredFileExtensions>
    </configuration>
</plugin>
~~~

Đây là **đoạn plugin**, cần đặt trong `build/plugins` của POM thực. Maven Resources Plugin đã bỏ qua binary filtering mặc định cho `jpg`, `jpeg`, `gif`, `bmp`, `png` trong các bản được tài liệu hóa; đoạn này **bổ sung** `pdf`, `bin`.

Hãy hiểu ba giới hạn:

1. **Danh sách dựa trên extension.** Nếu file binary có extension không đúng hoặc file text lại có extension `bin`, hành vi có thể không như mục đích.
2. **Chỉ bỏ qua filtering.** Một tệp `.pdf` được chọn để copy vẫn có thể nằm trong artifact; nếu PDF chứa dữ liệu nhạy cảm thì vẫn nguy hiểm.
3. **Không thay thế resource separation.** Trong dự án có thể quản lý được cấu trúc, dùng filtered resource directory riêng và unfiltered resource set riêng giúp review dễ hơn.

Khi format binary có tính bảo mật như `.p12`/`.jks`, **đừng dùng `nonFilteredFileExtensions` để “hợp thức hóa” việc đóng gói**. Cần giữ những file này ngoài artifact nếu chúng chứa khóa/bí mật.

## 14. Encoding `.properties` và delimiter có thể gây lỗi tinh vi

### Encoding

Maven Resources Plugin dùng `encoding` để đọc/ghi resource được filter, thường mặc định từ `project.build.sourceEncoding`. Với Java Properties, cách đọc khác nhau:

- `Properties.load(InputStream)` sử dụng **ISO-8859-1** theo đặc tả, ký tự ngoài dải thường được escape bằng `\uXXXX`.
- `Properties.load(Reader)` sử dụng encoding của Reader mà ứng dụng chọn.
- `ResourceBundle` ở Java 9+ có hành vi encoding khác so với Java 8; nên tham khảo tài liệu JDK theo runtime đích.

Ví dụ mục 6 đặt `propertiesEncoding=ISO-8859-1` và file toàn ASCII, nên tránh rủi ro giải mã sai. Nếu hệ thống cần text tiếng Việt trong properties, hãy **thiết kế encoding và cách đọc rõ ràng**, không tự đổi tất cả sang UTF-8 khi code vẫn dùng `Properties.load(InputStream)` cho bytes UTF-8.

### Delimiter

Resources Plugin có thể sử dụng delimiter dạng `${...}` và `@...@`. Nếu một file chứa placeholder của Spring hoặc framework khác, filter quá rộng có thể thay nhầm biểu thức.

Ví dụ một cấu hình ứng dụng chứa placeholder runtime:

~~~properties
service.url=${SERVICE_URL}
~~~

Nếu Maven filtering cùng nhận `${...}`, placeholder có thể bị thay thành một property tại build time hoặc giữ nguyên tùy cấu hình/giá trị. **Đừng phụ thuộc vào kết quả ngẫu nhiên đó.** Khi cần chỉ thay metadata Maven, dùng delimiter riêng (ví dụ `@project.version@`) và `useDefaultDelimiters=false` như POM mẫu.

**Không dùng delimiter để đưa token thật vào JAR.** Một người có thể mở JAR và đọc file resources. Nếu secret được cung cấp qua `-Dsecret=...`, filter vẫn có thể nhúng giá trị vào artifact và lộ qua command line/log/cache. Hãy để credential được cung cấp tại **runtime** hoặc qua hạ tầng secret tương ứng.

## 15. Git ignore, Maven excludes và secret scanner giải quyết các tầng khác nhau

| Biện pháp | Bảo vệ điều gì? | Không bảo vệ điều gì? |
| --- | --- | --- |
| **`.gitignore`** | Tránh Git theo dõi file chưa được track và đúng pattern. | Không cấm Maven đọc file, không tự bỏ file đã track, không xóa file khỏi JAR. |
| **Maven resource allowlist** | Giới hạn file được copy vào `target/classes` bởi resource entries đã cấu hình. | Không quét nội dung file được phép; không quản lý plugin khác hoặc Docker. |
| **`<filtering>false>`** | Không biến đổi bytes file đã được chọn. | Không ngăn file được đóng gói. |
| **`nonFilteredFileExtensions`** | Bỏ lọc các extension tương ứng khi resource filtering hoạt động. | Không loại file khỏi artifact, không ngăn secret lộ. |
| **JAR Plugin `<excludes>`** | Loại các path từ classesDirectory khỏi JAR do goal này tạo. | Không xóa file ở source/target/classes, không tự bảo vệ WAR/Docker/ZIP. |
| **Secret scanner** | Có thể phát hiện nhiều mẫu token/private key trong nội dung/code/artifact. | Không chắc phát hiện mọi loại bí mật, dữ liệu nhị phân mã hóa, bí mật chưa có pattern. |
| **Artifact inspection** | Xác nhận file/path/bytes cuối đã đóng gói. | Không tự chứng minh không có bất kỳ secret nào nếu chỉ kiểm tên/kiểu file. |
| **Secret manager/runtime injection** | Giảm nhu cầu nhúng secrets vào source/build output. | Vẫn cần bảo vệ log, access policy, lifecycle và memory của runtime. |

**Lưu ý `.gitignore`:** file đã được Git track sẽ không biến mất khỏi lịch sử hoặc index chỉ vì bạn thêm pattern ignore. Nếu secret đã từng commit hay publish vào artifact, xử lý như một sự cố: **thu hồi/rotate credential**, giới hạn truy cập, xử lý bản phát hành và lịch sử theo quy trình an ninh; chỉ xóa file khỏi commit mới là không đủ.

**Tránh test bằng một secret thật:** dùng fixture giả hoặc token giả rõ ràng, vì ngay cả các bài test “để xem nó có lọt vào JAR không” cũng có thể tạo log, cache hoặc artifact chứa secret.

## 16. Maven test resources, generated resources, profiles và multi-module

### Test resources cũng cần quy tắc

Mặc định Maven có vùng `src/test/resources` và `target/test-classes`; đây là vùng tài nguyên cho test. Nó không tự tạo artifact chính, nhưng các profile/custom packaging/CI upload có thể thay đổi điều đó. Test fixtures cần là **dữ liệu giả không nhạy cảm**. Nếu test cần key hoặc connection credential, dùng test secret store và môi trường tách biệt, không commit/đóng gói khóa thật.

### Generated resources có thể lọt qua allowlist sai

Các plugin như code generator, templating plugin, AntRun hoặc custom execution có thể sinh resource vào một thư mục được chọn rồi Maven copy/đóng gói. Nếu sinh ra file chứa secret vào `target/generated-resources` rồi cấu hình build thêm thư mục đó dưới `<resources>`, file có thể lọt vào output.

**Tư duy an toàn không dừng ở `src/main/resources`.** Cần kiểm kê mọi resource directory có trong **effective POM**, mọi plugin execution tạo/copy file và mọi phần của pipeline chịu trách nhiệm phát hành.

### Profiles có thể làm cấu hình khác nhau

Một profile `dev` có thể thêm filtered resources hoặc file config; profile `prod` có thể khác. Nếu CI chạy `-Pprod`, kiểm tra effective POM và artifact của **profile đó**; audit ở build mặc định không chứng minh profile khác an toàn.

Tránh một profile có tên hấp dẫn như `release` nhưng âm thầm thêm `<resource>` trỏ tới thư mục chứa secret. Nếu thực sự cần cấu hình theo môi trường, để resource public được đóng gói giống nhau, còn secrets cấp ở runtime.

### Multi-module

Mỗi module có thể có resource set và packaging khác nhau (`jar`, `war`, `pom`). Parent có thể quản lý plugin version và cấu hình, child có thể ghi đè/hợp nhất resources. Khi audit, phải kiểm tra **artifact của từng module** mà tổ chức phát hành, không chỉ JAR ở parent/root.

Một module chứa binary public và module khác chứa resource sinh mã không nên tự chia sẻ toàn bộ resource directory bằng đường dẫn tương đối trỏ rộng; nó làm khó kiểm toán và có thể mang dữ liệu không dự kiến.

## 17. JAR, WAR, Shade, Assembly, Docker và CI artifacts

Một ứng dụng Java có thể phát hành nhiều loại output:

- **JAR thông thường:** JAR Plugin thường lấy compiled classes và resource từ `target/classes`.
- **WAR:** Web resources có thể đến từ `src/main/webapp`, `WEB-INF/classes` và dependency JARs; cần kiểm tra thêm web resources và cấu hình WAR Plugin.
- **Shade/Assembly:** Có thể gộp dependency resources, license files, service descriptors hoặc copy cả thư mục ngoài nguồn chính. Exclude của Resources Plugin **không tự quản lý tất cả đầu vào của Shade/Assembly**.
- **Docker/OCI image:** Dockerfile có thể `COPY .` hoặc `COPY target/` làm lọt file mà JAR đã loại; `.dockerignore`, multi-stage builds và image inspection có vai trò riêng.
- **CI artifacts/cache:** Pipeline có thể upload `target/`, test reports hoặc workspace snapshot. Bí mật trong những đầu ra này vẫn nguy hiểm dù JAR chính sạch.
- **Source JAR:** Một số cấu hình Source Plugin đóng gói source và file kèm theo; phải kiểm tra source artifacts riêng.

**Kết luận:** audit artifact phải áp dụng cho **mỗi dạng phân phối** thực tế: JAR/WAR/ZIP/image, test artifacts và file upload CI. Không có một `<exclude>` nào bảo đảm mọi công cụ đóng gói trong toàn bộ pipeline tuân theo cùng bộ lọc.

## 18. Xác minh rằng secret không được lọc vào public config

Maven property interpolation có thể lấy giá trị từ POM, user properties, filter files và những nguồn khác. Việc dùng `-Ddb.password=...` rồi filter vào `.properties` là nguy hiểm vì có thể lộ:

- Giá trị trong `target/classes/config/...`.
- Nội dung JAR/WAR/image.
- Build logs hoặc debug logs.
- Local/shared caches và artifact repositories sau deploy.
- Process command line hoặc build metadata.

**Một POM tốt không đặt bí mật thành property để đóng vào bản phát hành.** Trong file public config có thể giữ **tên biến runtime**, nhưng không điền giá trị thật:

~~~properties
storage.mode=runtime-configured
storage.endpoint=configure-at-deployment
~~~

Đây là text minh họa **không chứa credentials**, không phải cấu hình ứng dụng production hoàn chỉnh. Tên biến môi trường và cơ chế cấp secret cụ thể thuộc ứng dụng/hạ tầng runtime; cần tránh in giá trị khi đọc.

Nếu một ứng dụng thực sự cần cấu hình riêng theo môi trường, xem xét file config do orchestration mount ngoài artifact, secret manager API, hoặc biến môi trường có chính sách truy cập. Secret có thể vẫn bị lộ qua log và quá nhiều quyền; runtime injection chỉ giảm một nhóm rủi ro, không thay thế quy trình bảo mật.

## 19. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| PDF hoặc tệp `.bin` bị hỏng sau build | Được đưa vào resource set `filtering=true`, extension không được loại trừ. | Tách sang `<filtering>false>`; so sánh hash nguồn và output. |
| Ảnh vẫn hỏng dù PNG mặc định không filter | File không thực sự là PNG, custom plugin khác sửa file, hoặc lỗi ở bước packaging/runtime. | So bytes ở nguồn, `target/classes` và trong JAR; kiểm tra toàn bộ plugin executions. |
| `.env` xuất hiện trong `target/classes` | Resources copy rộng hoặc plugin khác copy. | Xem effective resources/executions, thay bằng allowlist, build sạch. |
| `.env` không có trong Git nhưng có trong JAR | `.gitignore` không điều khiển Maven resource copy. | Xóa/di chuyển khỏi resource inputs; chặn ở allowlist và audit artifact. |
| Secret không trong JAR nhưng có trong CI artifact | Pipeline upload `target/` hoặc workspace rộng. | Sửa CI upload và kiểm tra mọi artifact/cache liên quan. |
| Token hiện ngay trong `config/app.properties` | Filter nhận giá trị secret từ POM, filters hay `-D`. | Ngừng nhúng, rotate token nếu đã lộ, cấp tại runtime, quét artifact. |
| `${VAR}` của framework bị thay sai | Maven lọc trùng delimiter của app. | Dùng delimiter `@` riêng và `useDefaultDelimiters=false`; kiểm tra output. |
| `@project.version@` còn nguyên sau build | Sai resource directory, file không được filter hoặc delimiter config khác. | Xem effective POM, log Resources Plugin, tệp `target/classes`. |
| Tiếng Việt trong `.properties` hiển thị sai | Encoding của filter không khớp cách `Properties.load`/ResourceBundle đọc. | Phân biệt `propertiesEncoding`, InputStream vs Reader và Java version. |
| File bị loại khỏi resource allowlist nhưng còn trong JAR | Output từ build cũ hoặc plugin khác vẫn để file trong staging. | Chạy `mvn clean verify`, kiểm tra nguồn sinh file, `jar tf`. |
| Test chạy tốt nhưng production không có resource | Resource chỉ nằm trong `testResources` hoặc profile khác. | Kiểm tra `target/classes`, JAR thực tế và classpath runtime. |
| `java -jar` không chạy được | Không có Main-Class trong manifest, không liên quan resource safety. | Dùng `java -cp ... Main` như ví dụ hoặc cấu hình executable jar phù hợp. |
| JAR sạch nhưng WAR/Shade/Docker vẫn có bí mật | Mỗi plugin đóng gói có input/rules riêng. | Kiểm tra riêng WAR/Shade/Assembly/image/CI artifacts. |
| Audit chỉ theo tên file báo an toàn nhưng secret vẫn lọt | Secret ở file công khai có tên không đáng ngờ hoặc metadata nhị phân. | Bổ sung secret scanning theo nội dung và review dữ liệu, không tin chỉ một kiểm tra. |

**Nếu phát hiện credential thật đã nằm trong artifact từng phát hành**, không chỉ “xóa khỏi source rồi build lại”. Cần đánh giá sự cố và **thu hồi/rotate secret**, thu hồi artifact liên quan nếu chính sách/hệ thống hỗ trợ, kiểm soát người đã tải và hạn chế tái phát. Không dán credential vào issue/chat để nhờ chẩn đoán.

## 20. Quy trình CI kiểm soát resource và artifact

Một pipeline dành cho ví dụ có thể tổ chức:

1. Xây project từ source đã review.
2. Dùng JDK/Maven Plugin versions đã chọn và repository đáng tin cậy.
3. Chạy `mvn clean verify` để giảm nguy cơ stale output.
4. Chạy **ArtifactAudit.java** cho từng JAR/variant cần phát hành.
5. Chạy secret scanner phù hợp **trên source và trên artifact đầu ra**; không in giá trị secret lên log.
6. So sánh hash những binary fixture/asset quan trọng nếu yêu cầu byte-for-byte.
7. Chỉ publish artifact khi các bước kiểm chứng cần thiết đã pass.
8. Kiểm tra cả artifact CI, container image và BOM/distribution khi pipeline tạo chúng.

Ví dụ lệnh **Linux/macOS hoặc Windows có JDK 17/Maven trong PATH**:

~~~bash
mvn -B -ntp clean verify
java tools/ArtifactAudit.java target/resource-guard-demo-1.0.0.jar
~~~

Với Windows PowerShell, cú pháp hai lệnh trên cũng hợp lệ; chỉ cần đảm bảo chạy từ root dự án chứa `pom.xml` và `tools/`.

**Không cần tạo file secret thật để chứng minh CI đang chặn nó**. Unit test có thể dùng filename giả `.env.example` hoặc fixture chứa chuỗi không nhạy cảm nếu muốn kiểm tra quy tắc. Tuy nhiên JAR audit ở đây cố ý fail khi tên `.env.example` xuất hiện vì coi nhóm `.env.*` là đáng nghi; thay quy tắc audit theo chính sách tổ chức sau khi review.

Một pipeline chất lượng nên xuất **cảnh báo có thể hành động** (artifact nào vi phạm, giai đoạn nào) nhưng không lộ nội dung credential. Scanner có thể có false positive/false negative, cần cơ chế review và exception có hạn thay vì tắt tất cả.

### CI kiểm tra từng module

Trong reactor đa module, `mvn clean verify` có thể tạo nhiều artifact. Chạy bước kiểm tra tên/bytes trên **từng JAR/WAR được phát hành**; nếu các module khác nhau có định dạng artifact khác, công cụ audit phải hiểu đúng loại artifact đó. **Đừng chỉ kiểm tra JAR ở module demo rồi cho rằng cả repository sạch.**

## 21. Checklist review POM trước release

1. **Liệt kê mọi resource directory** ở effective POM, kể cả inherited profiles và generated resources.
2. **Chỉ bật filtering cho text thật sự cần substitution**; không bật toàn bộ `src/main/resources` nếu chứa binary.
3. **Dùng allowlist đầu vào** cho những file được phép đưa vào `target/classes`/artifact, ưu tiên tách `resources-filtered`.
4. **Đặt binary public ở resource set `filtering=false`**; bổ sung `nonFilteredFileExtensions` nếu có trường hợp phải dùng resource set filtered.
5. **Không để secret thật trong source/resources/test fixtures**; cấp từ runtime secret manager hoặc môi trường đã bảo vệ.
6. **Kiểm tra encoding** cho `.properties`, XML/JSON/YAML và Java API thực sự đọc chúng.
7. **Giới hạn delimiter** để tránh thay nhầm placeholder của framework runtime.
8. **Kiểm tra Maven Resource/JAR/Compiler/Surefire Plugin versions** đã được kiểm chứng; không phụ thuộc ngẫu nhiên default cũ.
9. **Chạy build sạch**, kiểm tra `target/classes` và mở JAR thật với `jar tf`.
10. **So sánh bytes binary** ở source, staging, JAR nếu có yêu cầu không biến đổi.
11. **Quét secret trong nội dung**, không chỉ tên file; quét cả artifact phát hành và CI output.
12. **Kiểm tra WAR/Assembly/Shade/Docker/source JAR** theo cách đóng gói thực tế.
13. **Xem lại `.gitignore`** nhưng không coi nó là cơ chế ngăn packaging.
14. **Không log secret/filter properties** khi chạy Maven với `-X`; kiểm soát người có quyền đọc log và artifact.
15. **Nếu lỡ phát hành secret**, xử lý rotate/revoke theo quy trình sự cố, không chỉ xóa file ở commit mới.

## 22. Bài tập thực hành

**Bài 1 — tài nguyên được filter.** Tạo `pom.xml`, `ResourceCheck.java`, `ResourceCheckTest.java` và file `config/app.properties` theo mục 6–8. Chạy `mvn clean verify`, rồi `java -cp target/classes vn.example.resources.ResourceCheck`; đối chiếu chính xác ba dòng stdout.

**Bài 2 — binary public.** Thêm `tools/CreateFixture.java`, chạy Java để tạo file 8 bytes rồi build lại. So sánh SHA-256 source và `target/classes` trước khi xem JAR. Giải thích vì sao fixture `.bin` cần resource unfiltered.

**Bài 3 — kiểm tra JAR.** Chạy `jar tf target/resource-guard-demo-1.0.0.jar`; tìm `config/app.properties` và class `ResourceCheck`, thêm `assets/public/fixture.bin` nếu đã tạo. Chạy `ArtifactAudit.java` và xác nhận `Artifact audit OK`.

**Bài 4 — so sánh anti-pattern.** Trên nhánh thử nghiệm không có dữ liệu nhạy cảm, thay `resources` bằng một entry copy rộng và filtering true; dùng fixture binary công khai để quan sát nguy cơ đổi byte, nhưng không khẳng định file nào cũng hỏng (một số extension được plugin tự bảo vệ).

**Bài 5 — audit secret giả.** Tạo một tệp có tên `.env` với nội dung *hoàn toàn giả và không nhạy cảm* trong môi trường thử nghiệm, kiểm tra vì sao allowlist không copy nó. Không làm trên repo hoặc cache production có credentials thật.

**Bài 6 — profiles/packaging.** Xem effective POM trong một dự án có profile release, phát hiện mọi source directory được copy và so sánh artifact thật với default build. Tìm mọi điểm có thể copy thêm resource vào `target/classes` hoặc image.

**Bài 7 — quyết định thiết kế.** Cho bốn file: `config/app.properties` chứa tên ứng dụng công khai; `assets/logo.png` công khai; `keystore.p12` chứa private key; `report.pdf` là tài liệu mật. Quyết định file nào được filter, file nào được copy nguyên bytes, file nào **không được đóng gói**, rồi giải thích vì sao “binary thì không filter” không đủ là chính sách bảo mật.

### Tổng kết

**Có hai quyết định độc lập:** *(1) file nào được đưa vào artifact, (2) file nào được xử lý bằng bộ lọc văn bản*. Với Maven, nên **filter đúng những metadata công khai**, **copy binary công khai nguyên bytes**, và **không đưa secret vào đường đi đóng gói**. Dùng allowlist trong `build/resources`, đường dẫn resources tách biệt và kiểm tra bằng build sạch, `jar tf`, hash binary cùng secret scanning thực tế.

`nonFilteredFileExtensions` giải quyết nguy cơ **hỏng binary**, không giải quyết nguy cơ **rò rỉ bí mật**. `.gitignore` giúp quản lý Git, không chặn Maven packaging. Và **JAR sạch chưa chắc WAR, Docker hoặc CI artifact sạch**. Cần kiểm tra đúng đầu ra được phát hành.

### Tài liệu chính thức

- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Apache Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven Resources Plugin — Binaries Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html)
- [Apache Maven Resources Plugin — Including and Excluding Files and Directories](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html)
- [Apache Maven Resources Plugin — resources:resources](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
- [Apache Maven Resources Plugin — Filtering Properties Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/filtering-properties-files.html)
- [Apache Maven Resources Plugin — FAQ](https://maven.apache.org/plugins/maven-resources-plugin/faq.html)
- [Apache Maven JAR Plugin — Including/Excluding Files](https://maven.apache.org/plugins/maven-jar-plugin/examples/include-exclude.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
