# Giữ nguyên tài nguyên nhị phân khi lọc hoặc thay thế nội dung

## 1. Vấn đề trong Spring Boot Build Tooling Packaging

Khi biên dịch và đóng gói ứng dụng Spring Boot, thư mục tài nguyên thường chứa cả file **văn bản** cần thay token (chẳng hạn `build-info.properties`) và file **nhị phân** cần giữ nguyên (ảnh, PDF, font, JAR, ZIP, certificate, keystore hoặc dữ liệu `.bin`). Một build có thể thành công và JAR vẫn chứa đủ tên file nhưng dữ liệu bên trong đã bị biến đổi, khiến hình ảnh không mở được, tài liệu hỏng hoặc chương trình không đọc được resource.

**Resource filtering** là thao tác đọc tài nguyên như văn bản, tìm các placeholder như `@project.version@` rồi thay bằng giá trị build-time. **Binary-safe copying** là sao chép nội dung dưới dạng bytes mà không decode, thay token hay encode lại. Hai thao tác này phải được phân biệt ngay trong cấu hình Maven/Gradle.

Bạn sẽ học cách:

1. Phân biệt copy nguyên byte với text filtering/content expansion.
2. Giải thích vì sao filter sai có thể phá file binary mà `mvn package` vẫn xanh.
3. Tách các file cần lọc khỏi các file không được lọc bằng cấu hình Maven Resources Plugin.
4. Dùng Java 17+ và Spring Boot để tự kiểm tra tài nguyên text/binary trong runtime classpath.
5. So sánh bytes giữa file nguồn, `target/classes` và entry trong executable JAR.
6. Nhận diện `nonFilteredFileExtensions`, escaping, encoding và xung đột giữa token Maven với placeholder runtime Spring.
7. Áp dụng nguyên tắc tương đương cho Gradle `processResources` và các bước packaging sau đó.

Bài thuộc mục **Biên dịch và tài nguyên**; trọng tâm là cơ chế xử lý resource trong build, không phải cách viết parser của từng định dạng nhị phân.

## 2. Resource đi từ nguồn vào JAR qua những bước nào?

Với Maven Java project thông thường:

~~~text
src/main/java            src/main/resources
     |                           |
     v                           v
Java compilation         process-resources
     |                    copy / filter
     +------------+--------------+
                  |
                  v
            target/classes
                  |
                  v
               package
                  |
                  v
              plain JAR
                  |
                  v
     Spring Boot repackage (nếu cấu hình)
                  |
                  v
         executable JAR
                  |
                  v
             java -jar
~~~

Maven Resources Plugin thường xử lý file trong `src/main/resources` ở phase `process-resources`, đưa tài nguyên vào `target/classes` theo đường dẫn tương đối. Task package sau đó đóng gói classes/resources. Spring Boot Maven Plugin `repackage` có thể chuyển chúng thành executable archive, đặt application resource trong `BOOT-INF/classes` của JAR layout thông thường và runtime dependencies trong `BOOT-INF/lib`.

Nếu file đã hỏng khi copy vào `target/classes`, repackage không thể tự khôi phục bytes ban đầu. Ngược lại, dù `target/classes` đúng, một bước khác như custom Copy, shading/assembly hoặc script deploy vẫn có thể làm thay đổi artifact. Do đó cần xác minh tại **đích cuối**.

| Bước | Input/Output | Tiêu chí |
| --- | --- | --- |
| Copy nguyên trạng | `src/main/resources/assets/logo.png` → `target/classes/assets/logo.png` | Byte-for-byte equality |
| Filter văn bản | `build-info.properties` chứa `@project.version@` → giá trị version thực | Thay đúng token; giữ phần văn bản khác có chủ đích |
| Đóng gói archive | `target/classes/assets/logo.png` → JAR entry `BOOT-INF/classes/assets/logo.png` | Nội dung **entry** giống file nguồn |
| Deploy và chạy | Executable JAR/OCI image → ứng dụng thực tế | File vẫn đúng path, parse/đọc được |

So sánh SHA-256 của **toàn bộ JAR** với hash ảnh nguồn là vô nghĩa vì JAR là container chứa nhiều entry. Hãy so sánh bytes của resource nguồn với bytes của **đúng entry** đã giải nén từ archive.

## 3. Tại sao text filtering nguy hiểm với dữ liệu nhị phân?

Một text filter thường thực hiện công việc tương đương:

~~~text
input bytes
   -> decode bằng charset (ví dụ UTF-8)
   -> tìm token
   -> thay giá trị
   -> encode thành bytes
   -> ghi output
~~~

Mỗi plugin có implementation riêng nhưng nguy cơ chung là rõ ràng: byte nhị phân không nhất thiết tạo thành văn bản hợp lệ. Những byte như `FF` và `80` không phải UTF-8 hợp lệ khi đứng một mình; decode/encode lại có thể thất bại hoặc làm thay đổi byte. Nếu dữ liệu tình cờ chứa `@project.version@`, filter còn có thể thay chuỗi ấy thành `1.0.0`, làm sai độ dài, offsets, checksum hoặc chữ ký file.

Hãy tưởng tượng một payload có bytes:

~~~text
00 FF 80 40 70 72 6F 6A 65 63 74 2E 76 65 72 73 69 6F 6E 40 0A 0D
~~~

Ở giữa là ký tự ASCII `@project.version@`, nhưng cả file **không phải text template**. Không nên cố chữa lỗi bằng cách thay `UTF-8` thành encoding khác; yêu cầu đúng là **không chạy phép lọc văn bản lên file đó**.

Các định dạng thường cần bảo vệ gồm `.png`, `.jpg`, `.gif`, `.ico`, `.pdf`, `.zip`, `.jar`, `.woff2`, `.ttf`, `.p12`, `.jks`, `.class`, `.bin` và file tự định nghĩa. Đuôi file không phải bằng chứng tuyệt đối: một file không extension hoặc mang đuôi `.dat` vẫn có thể chứa binary.

## 4. Phương án Maven an toàn: tách nguồn filtered và unfiltered

Chiến lược dễ kiểm soát nhất là **allowlist** những file text thực sự cần thay nội dung, sao chép nguyên byte phần còn lại.

~~~text
src/main/resources/                  (không lọc)
  application.yml
  assets/logo.png
  assets/manual.pdf
  assets/payload.bin
  fonts/site.woff2

src/main/resources-filtered/         (lọc có chọn lọc)
  build-info.properties
~~~

Khai báo hai resource entries:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/resources-filtered</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-info.properties</include>
            </includes>
        </resource>
    </resources>
</build>
~~~

File binary được copy theo nhánh `filtering=false`, kể cả khi nội dung chứa ký hiệu giống token. Chỉ file `build-info.properties` trong thư mục thứ hai được phân tích như text. Cả hai nhánh vẫn đặt resource vào cùng output classpath của Maven, mặc định là `target/classes`.

Không cần ép tất cả file trong `src/main/resources` qua filtering chỉ vì một file text muốn thay version. Nguyên tắc này giảm rủi ro khi người khác thêm PDF, keystore hoặc định dạng mới mà chưa cập nhật danh sách extension.

Một biến thể dùng chung một thư mục và hai include/exclude entries sẽ được trình bày ở mục 8. Hai cách là **lựa chọn thay thế**, không cấu hình chồng để copy một file nhiều lần.

## 5. Thực hành độc lập: Java 17 + Maven + Spring Boot

Bài thực hành tạo một file binary chứa token giả, lọc version trong text file, đóng gói executable JAR và dùng Java chứng minh bytes của binary không đổi.

**Điều kiện:** JDK 17+, Maven 3.x tương thích Spring Boot 3.3.5 và khả năng tải dependencies. Spring Boot `3.3.5` cùng Maven Resources Plugin `3.3.1` là **phiên bản cố định cho ví dụ**, không phải khuyến nghị chọn phiên bản mới nhất.

### 5.1. Cấu trúc file

~~~text
resource-demo/
  pom.xml
  CreateFixture.java
  CompareArchive.java
  src/
    main/
      java/
        demo/
          Application.java
      resources/
        assets/
          payload.bin             (được tạo ở bước tiếp)
      resources-filtered/
        build-info.properties
~~~

Hai Java file tại project root là tiện ích chạy bằng Java source-file launcher. Chúng **không** được Maven biên dịch vào application JAR vì không nằm trong `src/main/java`. Chương trình Spring Boot thực sự nằm ở `demo.Application`.

### 5.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example.learning</groupId>
    <artifactId>resource-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>src/main/resources-filtered</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-info.properties</include>
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
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích POM:

- `<filtering>false</filtering>` bảo đảm `payload.bin` **không đi qua text decoder/token interpolator**.
- `<filtering>true</filtering>` kết hợp `<includes>` giới hạn phạm vi lọc vào một file text đã biết.
- `<delimiter>@</delimiter>` và `<useDefaultDelimiters>false</useDefaultDelimiters>` cho phép `@project.version@` được nội suy mà không xem biểu thức Spring kiểu `${...}` là Maven token.
- `<encoding>UTF-8</encoding>` có ý nghĩa đối với text file được filter; nó **không** yêu cầu giải mã binary unfiltered.
- `spring-boot-starter-parent` cùng khai báo Spring Boot Maven Plugin cho phép `repackage` chạy trong `mvn package` theo cấu hình parent.
- `spring-boot-starter` là starter cơ bản, không khởi động HTTP server, nên chương trình kiểm chứng có thể chạy rồi kết thúc.

Nếu dự án khác không dùng Spring Boot parent, việc bind `spring-boot:repackage` cần cấu hình riêng. Đó là khác biệt lifecycle, không liên quan đến việc bảo vệ resource bytes.

### 5.3. File text có placeholder

Tạo `src/main/resources-filtered/build-info.properties`:

~~~properties
build.version=@project.version@
runtime.placeholder=${APP_RUNTIME_VALUE}
~~~

Sau filtering, nội dung kỳ vọng ở `target/classes/build-info.properties`:

~~~properties
build.version=1.0.0
runtime.placeholder=${APP_RUNTIME_VALUE}
~~~

Giá trị Maven version được thay từ POM; placeholder runtime không bị text filtering đổi. Các giá trị bí mật như mật khẩu hay API token không nên nội suy vào file được đóng gói; cấp chúng qua cấu hình môi trường chạy.

### 5.4. Tạo binary fixture bằng Java

Tạo `CreateFixture.java` tại root:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateFixture {
    public static void main(String[] args) throws Exception {
        byte[] marker = "@project.version@"
                .getBytes(StandardCharsets.US_ASCII);
        byte[] bytes = new byte[marker.length + 5];
        bytes[0] = 0x00;
        bytes[1] = (byte) 0xFF;
        bytes[2] = (byte) 0x80;
        System.arraycopy(marker, 0, bytes, 3, marker.length);
        bytes[bytes.length - 2] = '\n';
        bytes[bytes.length - 1] = '\r';

        Path file = Path.of("src/main/resources/assets/payload.bin");
        Files.createDirectories(file.getParent());
        Files.write(file, bytes);
        System.out.println("fixture.bytes=" + bytes.length);
    }
}
~~~

Chạy từ root:

~~~bash
java CreateFixture.java
~~~

Đầu ra chính xác:

~~~text
fixture.bytes=22
~~~

Java 17 hỗ trợ chạy một file source trực tiếp theo chế độ source-file launcher. Payload có 3 byte đầu `00 FF 80`, 17 byte ASCII của `@project.version@`, rồi 2 byte cuối `0A 0D`. Nó được thiết kế để lộ lỗi nếu bị xử lý như văn bản.

### 5.5. Ứng dụng Spring Boot đọc cả hai resource

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Properties;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    private static byte[] expectedBytes() {
        byte[] marker = "@project.version@"
                .getBytes(StandardCharsets.US_ASCII);
        byte[] result = new byte[marker.length + 5];
        result[0] = 0x00;
        result[1] = (byte) 0xFF;
        result[2] = (byte) 0x80;
        System.arraycopy(marker, 0, result, 3, marker.length);
        result[result.length - 2] = '\n';
        result[result.length - 1] = '\r';
        return result;
    }

    @Bean
    CommandLineRunner checkResources() {
        return args -> {
            Properties p = new Properties();
            try (InputStream in = Application.class
                    .getResourceAsStream("/build-info.properties")) {
                if (in == null) {
                    throw new IllegalStateException("Missing build-info");
                }
                p.load(in);
            }

            byte[] actual;
            try (InputStream in = Application.class
                    .getResourceAsStream("/assets/payload.bin")) {
                if (in == null) {
                    throw new IllegalStateException("Missing binary");
                }
                actual = in.readAllBytes();
            }

            System.out.println("build.version="
                    + p.getProperty("build.version"));
            System.out.println("runtime.placeholder="
                    + p.getProperty("runtime.placeholder"));
            System.out.println("binary.bytes=" + actual.length);
            System.out.println("binary.intact="
                    + Arrays.equals(actual, expectedBytes()));
        };
    }
}
~~~

Code sử dụng `getResourceAsStream` để đọc file từ **application classpath**, kể cả khi resources nằm trong Spring Boot executable JAR. `Arrays.equals` kiểm tra **tất cả byte**; chỉ kiểm tra kích thước `22` sẽ không đủ.

`Properties.load(InputStream)` sử dụng quy tắc encoding riêng của Java Properties truyền thống. File minh họa chỉ chứa ASCII, nên kết quả xác định. Với file properties có tiếng Việt/Unicode và tự đọc bằng Java API, hãy dùng cơ chế nạp/encoding phù hợp (chẳng hạn `InputStreamReader` UTF-8 khi muốn UTF-8), không nhầm lỗi encoding của text file với việc filter nhị phân.

### 5.6. Build và chạy

Từ thư mục chứa `pom.xml`:

~~~bash
java CreateFixture.java
mvn clean package
java -jar target/resource-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Nếu dùng Maven Wrapper, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trong PowerShell.

Bốn dòng **do chính ứng dụng** in ra, đúng thứ tự, là:

~~~text
build.version=1.0.0
runtime.placeholder=${APP_RUNTIME_VALUE}
binary.bytes=22
binary.intact=true
~~~

Lệnh `mvn clean package` có thể tạo log riêng về plugins và tải dependencies; log ấy không thuộc stdout do `Application` chủ động in. Ví dụ chỉ dùng Spring Boot starter cơ bản, nên không cần mở cổng HTTP.

Nếu `binary.intact=false`, build có thể vẫn xanh nhưng tài nguyên không còn giống nguồn. Cần kiểm tra các bước resource copy/filter và artifact packaging.

## 6. Chứng minh không đổi byte ở từng giai đoạn

### 6.1. So sánh source với target/classes

Sau `mvn clean package`:

~~~text
src/main/resources/assets/payload.bin
target/classes/assets/payload.bin
target/classes/build-info.properties
target/resource-demo-1.0.0.jar
~~~

Ở Linux/macOS:

~~~bash
cmp src/main/resources/assets/payload.bin target/classes/assets/payload.bin
sha256sum src/main/resources/assets/payload.bin target/classes/assets/payload.bin
~~~

Với hai file giống nhau, `cmp` trả exit status `0` và thường không in gì. Hai dòng `sha256sum` phải có digest giống nhau, dù đường dẫn file khác.

Ở Windows PowerShell:

~~~powershell
Get-FileHash .\src\main\resources\assets\payload.bin -Algorithm SHA256
Get-FileHash .\target\classes\assets\payload.bin -Algorithm SHA256
~~~

So sánh thuộc tính `Hash` trong hai kết quả. Hash là cách kiểm tra độc lập với nội dung hiển thị; file khác nhau dù chỉ một byte sẽ có khả năng rất cao cho digest khác nhau.

### 6.2. So sánh bytes của JAR entry

Một bước khác sau `process-resources` vẫn có thể làm hỏng dữ liệu. Để kiểm tra **executable JAR cuối**, tạo `CompareArchive.java` tại root:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class CompareArchive {
    public static void main(String[] args) throws Exception {
        Path original = Path.of(
                "src/main/resources/assets/payload.bin");
        Path archive = Path.of(
                "target/resource-demo-1.0.0.jar");
        String resource = "BOOT-INF/classes/assets/payload.bin";

        try (ZipFile zip = new ZipFile(archive.toFile())) {
            ZipEntry entry = zip.getEntry(resource);
            if (entry == null) {
                throw new IllegalStateException(
                        "Missing entry: " + resource);
            }
            try (InputStream in = zip.getInputStream(entry)) {
                byte[] source = Files.readAllBytes(original);
                byte[] packaged = in.readAllBytes();
                System.out.println("jar.binary.intact="
                        + Arrays.equals(source, packaged));
            }
        }
    }
}
~~~

Chạy sau khi `mvn clean package` hoàn tất:

~~~bash
java CompareArchive.java
~~~

Đầu ra chính xác khi lưu trữ đúng:

~~~text
jar.binary.intact=true
~~~

`ZipFile` đọc đúng entry đã được đóng gói dưới `BOOT-INF/classes`, còn `Arrays.equals` đối chiếu nội dung với file nguồn. Đây là bằng chứng rõ hơn việc chỉ liệt kê tên file bằng `jar tf`.

Với file rất lớn, không nên dùng `readAllBytes` trên mọi artifact; thay bằng tính SHA-256 theo luồng cho cả file nguồn và stream entry, sau đó so sánh digest. Nếu dữ liệu **có chủ ý** được nén/biến đổi bằng một pipeline chuyên dụng, điều kiện QA sẽ khác và phải được xác định riêng.

### 6.3. Mốc đầu tiên bị sai là đầu mối điều tra

~~~text
source bytes
    |
    +--> target/classes bytes
               |
               +--> plain JAR entry
                         |
                         +--> executable JAR entry
                                     |
                                     +--> container/deploy resource
~~~

Nếu source khác `target/classes`, xem `process-resources` và filtering config. Nếu `target/classes` đúng nhưng JAR entry sai, xem jar/repackage/shading/assembly. Nếu JAR entry đúng nhưng ứng dụng không đọc được, kiểm tra classpath path, thư viện đọc file và môi trường runtime. So sánh theo từng mốc giúp tìm nguyên nhân gốc thay vì chỉ sửa triệu chứng.

## 7. Maven nonFilteredFileExtensions: lớp bảo vệ bổ sung

Apache Maven Resources Plugin có parameter `nonFilteredFileExtensions`, cho phép liệt kê extension mà plugin sẽ **bỏ qua filtering** ngay cả khi resource được khai báo `<filtering>true</filtering>`.

Ví dụ fragment trong `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <nonFilteredFileExtensions>
            <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
            <nonFilteredFileExtension>zip</nonFilteredFileExtension>
            <nonFilteredFileExtension>bin</nonFilteredFileExtension>
            <nonFilteredFileExtension>woff2</nonFilteredFileExtension>
            <nonFilteredFileExtension>p12</nonFilteredFileExtension>
        </nonFilteredFileExtensions>
    </configuration>
</plugin>
~~~

Ở Maven Resources Plugin **3.3.1**, tài liệu chính thức nêu một số extension được bỏ filter mặc định: `jpg`, `jpeg`, `gif`, `bmp`, `png`. Không suy rộng rằng **mọi** file binary đều đã được mặc định bảo vệ, cũng không coi mặc định của phiên bản plugin khác là giống hệt.

`nonFilteredFileExtensions` có giới hạn: nó dựa trên extension và chỉ tác động đến plugin đang được cấu hình. File không có extension, file có đuôi lạ, script custom hoặc một bước `replace` khác vẫn có thể làm hỏng dữ liệu. Trong ví dụ mục 5, chúng ta **không cần** cấu hình extension guard vì binary đã được đặt ở nhánh `filtering=false`.

Chọn theo ưu tiên: **allowlist text files → unfiltered copy cho còn lại → extension guard khi buộc phải filter rộng → xác minh byte trong sản phẩm cuối**.

## 8. Nếu text và binary nằm chung src/main/resources

Một project cũ có thể không tiện tách thêm `src/main/resources-filtered`. Khi đó dùng hai resource declarations **trỏ đến cùng folder**, nhưng **không được trùng tập file**:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-info.properties</include>
            </includes>
        </resource>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>build-info.properties</exclude>
            </excludes>
        </resource>
    </resources>
</build>
~~~

Đây là **phương án thay thế** phần `<resources>` ở POM ví dụ, không phải khối XML cộng thêm nguyên xi vào cùng một POM. Đưa `build-info.properties` về `src/main/resources` nếu dùng phương án này. Bản filtered chỉ chứa file text đã chọn; bản unfiltered chứa mọi file khác.

Cần tránh hai resource entries cùng tạo một file output nhưng theo hai chế độ khác nhau: thứ tự copy hoặc cơ chế overwrite có thể khiến kết quả khó dự đoán. Với nhiều text templates, chỉ mở rộng `includes` đến các tên/pattern thực sự cần, chẳng hạn `build-*.properties`, thay vì `**/*`.

## 9. Spring Boot Maven placeholders và vấn đề xung đột

File `application.properties` hoặc `application.yml` của Spring Boot có thể chứa biểu thức runtime:

~~~properties
service.url=${SERVICE_URL:http://localhost:8080}
~~~

Nếu Maven filtering nhận cả cú pháp `${...}`, giá trị này có thể bị thay sai ở **build-time**. Spring Boot Maven parent có cấu hình resource filtering dành cho các file application properties/YAML dùng delimiter `@...@` để tránh xung đột với cú pháp Spring `${...}`.

Ví dụ mục 5 minh bạch hóa quy tắc:

~~~xml
<delimiters>
    <delimiter>@</delimiter>
</delimiters>
<useDefaultDelimiters>false</useDefaultDelimiters>
~~~

Điều này có nghĩa:

- `@project.version@`: Maven được phép thay lúc build.
- `${SERVICE_URL:...}`: giữ cho runtime Spring Boot xử lý nếu file ấy là application config.
- File binary không được filter dù chứa token `@project.version@`.

Nếu dự án không dùng Spring Boot parent hoặc có parent nội bộ, đừng đoán delimiter: kiểm tra effective POM và cấu hình Maven Resources Plugin của dự án. Đừng bật filter chỉ để biến giá trị kết nối hoặc secret theo môi trường; việc đóng gói secret vào artifact có thể lộ thông tin và buộc build lại cho từng môi trường.

**Text cũng không mặc nhiên nên filter.** Một template HTML/JavaScript/SQL có thể cố tình chứa `${...}`, `@...@` hoặc syntax của engine khác. PEM key/certificate có thể trông như text nhưng thay newline/escaping cũng phá định dạng. Lọc dựa trên hợp đồng rõ ràng của từng file, không dựa đơn thuần vào extension `.txt` hay `.properties`.

### Encoding và escape

Với file text đã chọn, đặt encoding ổn định, thường `UTF-8`. Maven Resources Plugin có `encoding` và, ở các bản hỗ trợ, `propertiesEncoding` cho file properties. `escapeString` có thể ngăn một token cụ thể bị nội suy, nhưng không phải giải pháp bảo vệ một thư mục binary.

Nếu file không cần thay token, để `filtering=false` là cách đúng nhất. Dù chọn encoding nào, áp dụng text decoder lên binary vẫn là sai về mặt mô hình xử lý.

## 10. Gradle processResources: cùng nguyên tắc bảo vệ

Gradle Java plugin có task `processResources`, thường copy file từ `src/main/resources` sang `build/resources/main`. Mặc định copy resource không yêu cầu thay text. Nguy cơ xuất hiện khi build script áp `expand` hoặc `filter` lên toàn task/copy spec.

**Cấu hình dễ gây lỗi khi thư mục có binary:**

~~~groovy
tasks.named('processResources') {
    expand(project.properties)
}
~~~

`expand` diễn giải nội dung file như Groovy template, có thể ảnh hưởng cả binary và các placeholder runtime. Không nên dùng trên mọi file chỉ vì một `build-info.properties` cần version.

**Cách giới hạn đúng file** trong `build.gradle` (Groovy DSL):

~~~groovy
version = '1.0.0'
def buildVersion = project.version.toString()

tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(version: buildVersion)
    }
}
~~~

File `src/main/resources/build-info.properties` cho ví dụ Gradle dùng:

~~~properties
build.version=${version}
~~~

Sau `./gradlew processResources`, giá trị trong `build/resources/main/build-info.properties` là:

~~~properties
build.version=1.0.0
~~~

`filesMatching` chỉ gọi `expand` trên **file text đã chọn**. Các binary còn lại được copy theo đường xử lý mặc định. Cú pháp token Gradle ở đây là Groovy template `${version}`, khác với Maven `@project.version@`. Nếu file cần giữ placeholder runtime cùng dạng `${...}`, phải thiết kế cách escape/tách file cho phù hợp; `expand` có thể cố diễn giải các biểu thức chưa có giá trị.

Với `bootJar` của Spring Boot Gradle plugin, resource output thường đi vào `BOOT-INF/classes` của executable JAR; vẫn cần so sánh bytes của entry cuối. Nếu Gradle có custom `Copy` tasks, plugin transform hoặc `processTestResources`, cần kiểm tra đúng task chịu trách nhiệm từng nguồn.

## 11. Test resources, generated resources và bước packaging khác

- **Test resources:** `src/test/resources` của Maven/Gradle thường có test fixtures nhị phân như PDF, ảnh hoặc keystore. Chúng cần copy byte-safe. Cấu hình `testResources` hoặc `processTestResources` có thể khác production.
- **Generated resources:** file do `generate-resources` hoặc custom task tạo ra có thể được add vào resources rồi bị lọc lần hai. Nếu đầu ra là binary, phải tránh text transform sau bước sinh file.
- **WAR/assembly/shading:** Spring Boot executable WAR thường chứa tài nguyên trong `WEB-INF/classes`, còn Maven WAR plugin, shade/assembly plugins có thể có chính sách filtering/merging riêng. Kiểm tra artifact thật.
- **Container image:** JAR đúng chưa bảo đảm file được copy đúng vào image hoặc container khởi chạy đúng artifact. Xác định tên artifact và đường dẫn người dùng cuối thực sự chạy.
- **Runtime resource path:** `ClassLoader.getResourceAsStream` đọc resource từ classpath; `Files.readAllBytes("src/main/resources/...")` đọc filesystem. Folder nguồn thường không tồn tại trên máy deploy, nên không dùng source path làm đường dẫn runtime mặc định.

Khi cần biến đổi binary **có chủ đích** (nén, ký số, tối ưu ảnh, tạo protobuf descriptor), sử dụng công cụ hiểu định dạng hoặc API xử lý byte, kèm tiêu chí QA riêng. `sed`, regex replace và text template engines không phải công cụ tổng quát để sửa byte trong archive/keystore/class files.

## 12. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách chẩn đoán |
| --- | --- | --- |
| PNG/PDF trong JAR không mở được | Binary bị filter hoặc bước package thay đổi bytes | So sánh SHA-256/byte source → `target/classes` → JAR entry |
| `.bin` đổi kích thước sau `process-resources` | Token thay nội dung, decoder/encoder thay bytes | Chuyển file sang nhánh `filtering=false`; build sạch |
| Keystore `.p12` nguồn dùng được nhưng app không đọc được | File bị filter hoặc đường dẫn/sao chép sai | So hash, check classpath path và cách nạp secret |
| `@project.version@` không được thay | Include pattern hoặc delimiter không khớp, filtering chưa bật | Kiểm tra POM, file đích và cấu hình Resources Plugin |
| Spring placeholder `${DB_URL}` bị thay lúc build | Maven/Gradle đang lọc cả runtime token | Dùng delimiter riêng; giới hạn file text và kiểm tra output |
| Local đúng nhưng CI hỏng | Tool/plugin version, encoding, cache hoặc task trong CI khác | In versions, effective POM/task graph và hash ở đúng job |
| File tồn tại trong `target/classes` nhưng vắng trong JAR | Packaging exclude/shade/assembly hoặc sai module | Dùng `jar tf`, tìm đúng entry và kiểm tra archive được deploy |
| Hash source và class output giống nhưng JAR entry khác | Bước repackage hoặc custom packaging đã biến đổi entry | Trace theo từng bước thay bytes |
| Tài nguyên văn bản không hiển thị tiếng Việt đúng | Charset khi filter/read text không thống nhất | Đặt UTF-8 hợp lý cho text; kiểm tra API đọc properties |
| Trùng file đích từ hai resource entries | Filtered/unfiltered entries overlap | Tách includes/excludes, tránh hai nhánh cùng ghi một đường dẫn |

**Đừng dựa vào việc build xanh hoặc chỉ so dung lượng.** Một thay đổi chỉ một byte có thể phá file được ký số; file có cùng số byte vẫn có thể khác nội dung. Byte equality hoặc hash là bằng chứng xác đáng khi mục tiêu là giữ nguyên.

## 13. Quy trình kiểm chứng trước phát hành

1. Xác định resource nào là **text template** thật sự có token cần thay tại build-time.
2. Phân loại các file còn lại là **copy nguyên byte**, đặc biệt binary và file có cấu trúc nghiêm ngặt.
3. Trong Maven, dùng thư mục nguồn riêng hoặc hai resource entries có includes/excludes không chồng lấn. Trong Gradle, dùng `filesMatching` giới hạn `expand`.
4. Kiểm tra delimiters, encoding và placeholder runtime Spring; không đưa secret vào artifact.
5. Nếu buộc phải filtering rộng, bổ sung `nonFilteredFileExtensions` theo **phiên bản plugin đang dùng**, nhưng không coi đó là bảo vệ duy nhất.
6. Chạy build sạch; kiểm tra files trong output classpath.
7. So sánh source và output binary bằng `cmp`, `Get-FileHash`, `Files.mismatch` hoặc SHA-256.
8. Kiểm tra **đúng entry** trong JAR/WAR đã đóng gói; so sánh bytes với file nguồn.
9. Chạy smoke test để xác nhận ứng dụng nạp và sử dụng resource đúng.
10. Gắn kiểm tra binary artifact quan trọng vào CI nếu nguy cơ tái diễn là đáng kể.

### Tự kiểm tra

**Câu A:** Maven đã tạo JAR và `logo.png` có trong `jar tf`. Có thể kết luận ảnh nguyên vẹn?

**Đáp án:** Chưa. Cần so sánh entry trong JAR với bytes nguồn hoặc mở/parse thử định dạng.

**Câu B:** Plugin Maven có một số image extensions được bỏ filter mặc định. `cert.p12` có chắc được bảo vệ?

**Đáp án:** Không. Cần kiểm tra version và cấu hình, tốt nhất copy file bằng nhánh `filtering=false`.

**Câu C:** Vì sao không dùng `<build><outputDirectory>` để tránh binary filtering?

**Đáp án:** `outputDirectory` đổi nơi output được lưu, không thay chế độ filter. Cần sửa `<resources>` và `<filtering>` hoặc lựa chọn include/exclude.

**Câu D:** Source và `target/classes` giống nhau, nhưng executable JAR bị hỏng. Cần xem bước nào?

**Đáp án:** Kiểm tra packaging/repackage/shade hoặc task copy sau đó; đối chiếu bytes của JAR entry với nguồn.

**Câu E:** Vì sao chỉ lọc `build-info.properties` bằng Gradle `filesMatching` tốt hơn `expand` trên toàn `processResources`?

**Đáp án:** Vì scope biến đổi chỉ còn file text được chọn; binary không đi qua text template engine.

## 14. Tài liệu chính thức

- Maven — Guide to Filtering Resources: https://maven.apache.org/guides/mini/guide-filtering-resources.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
- Maven Resources Plugin — Binaries Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html
- Maven Resources Plugin 3.3.1 — resources:resources parameters: https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/resources-mojo.html
- Spring Boot 3.3 — Using Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Gradle — ProcessResources task: https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html
- Gradle — CopySpec API: https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html

**Ghi nhớ:** Chỉ áp dụng text filtering lên những file văn bản đã được chọn rõ ràng. Giữ binary ở đường copy nguyên byte, và kiểm chứng trên **resource entry thực sự được đóng gói**, không chỉ trên file nguồn hoặc trạng thái thành công của build.