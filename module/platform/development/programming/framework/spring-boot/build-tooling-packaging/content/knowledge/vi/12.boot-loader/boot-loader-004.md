# Giới hạn của thư viện lồng và cách đọc tài nguyên trong archive

Một ứng dụng Spring Boot chạy tốt từ IDE hoặc với `./gradlew bootRun` nhưng có thể thất bại khi chạy `java -jar app.jar`: không tìm thấy class, không đọc được resource, hay một thư viện đòi đường dẫn `File` và gặp lỗi. Lý do thường là executable Spring Boot JAR sử dụng **các JAR thư viện lồng trong một outer archive**, và **classpath resource không bắt buộc là file hệ thống**.

Bài học giải thích cơ chế Spring Boot Loader, những hạn chế có thật của nested JAR, cách đọc resource một cách di động và cách kiểm chứng trong artifact đã đóng gói.

**Nguyên tắc chính:** Nếu chỉ cần nội dung resource, dùng `InputStream` hoặc Spring `Resource`; **không** đổi URL classpath thành `File` khi chưa biết resource thực sự nằm trên filesystem. Nếu một thư viện cần JAR vật lý, xác định rõ thư viện đó và dùng cơ chế unpack phù hợp, thay vì giải nén tất cả dependencies.

Các ví dụ chạy với **Java 17**, **Spring Boot 3.3.5** và một Gradle version tương thích như **8.7**. Đây là phiên bản cố định cho mục đích học, không phải khẳng định về phiên bản mới nhất.

## 1. Nested library trong Spring Boot executable archive là gì?

Một executable Spring Boot JAR do `bootJar` (Gradle) hoặc `spring-boot:repackage` (Maven) tạo ra có layout thông dụng:

~~~text
application.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── ... các class của Boot Loader ...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/app/Application.class
    │   ├── guide/message.txt
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── spring-context-<version>.jar
    │   └── library-<version>.jar
    ├── classpath.idx  (có thể có)
    └── layers.idx     (có thể có)
~~~

Đây là **sơ đồ**, không phải output nguyên văn từ `jar tf`. Tên `<version>` là ký hiệu thay thế cho version thật.

- `BOOT-INF/classes/` chứa class/resource ứng dụng đã biên dịch và xử lý.
- `BOOT-INF/lib/` chứa các dependency JAR **lồng bên trong outer archive**.
- Boot launcher nằm ở vị trí Java launcher có thể tìm thấy để khởi động.
- `META-INF/MANIFEST.MF` ghi launcher làm `Main-Class` và main class ứng dụng làm `Start-Class` trong kiểu đóng gói thường gặp.
- `classpath.idx` nếu tồn tại có thể xác định thứ tự nested JAR được đưa vào classpath khi chạy archive với launcher.
- `layers.idx` dùng để hỗ trợ chia layer cho container image; nó **không** biến library thành directory thông thường khi runtime.

Với executable WAR, layout khác: `WEB-INF/classes/`, `WEB-INF/lib/` và có thể `WEB-INF/lib-provided/`. Không dùng đường dẫn `BOOT-INF` của JAR làm giả định cứng cho mọi WAR.

### Development classpath và archive classpath

Khi chạy từ IDE/Gradle:

~~~text
build/classes/java/main/
build/resources/main/
~/.gradle/caches/.../spring-boot-3.3.5.jar
~/.gradle/caches/.../other-library.jar
~~~

Từng dependency có thể là **file JAR thật** trong Gradle cache. Sau khi package, file `other-library.jar` có thể trở thành **một ZIP entry** ở `BOOT-INF/lib/other-library.jar` trong `application.jar`.

Điều đó giải thích một nghịch lý bề ngoài: Boot Loader nạp class trong nested library thành công, nhưng `new File("BOOT-INF/lib/other-library.jar")` không mở được gì. Một tên entry trong ZIP **không phải** một path độc lập trên filesystem.

## 2. Boot Loader khởi động từ JAR như thế nào?

JVM tiêu chuẩn hỗ trợ classpath từ directory và JAR thông thường, nhưng không tự cung cấp một classpath chung cho tất cả dạng JAR nằm trong JAR khác. Spring Boot thêm launcher/class loader biết layout archive của nó:

~~~text
java -jar application.jar
      |
      v
JVM đọc META-INF/MANIFEST.MF
      |
      v
Main-Class = Spring Boot JarLauncher
      |
      +-- chuẩn bị BOOT-INF/classes/
      +-- truy xuất nested JAR ở BOOT-INF/lib/
      +-- tạo class loader hỗ trợ nested JAR
      +-- đọc Start-Class của ứng dụng
      |
      v
Application.main(String[] args)
      |
      v
SpringApplication.run(...)
~~~

Với Spring Boot 3.3, launcher JAR thường là `org.springframework.boot.loader.launch.JarLauncher`. Các thế hệ Spring Boot cũ có thể dùng tên package khác. Đừng hard-code tên launcher chỉ dựa trên một bài hướng dẫn không cùng version.

Loader có cơ chế ánh xạ các entry của nested JAR tới offset dữ liệu trong outer archive, giúp đọc class/resource mà không cần giải nén toàn bộ dependencies trước. Nó cũng cung cấp URL handling cho nested archives trong môi trường Boot Loader. Tuy nhiên, khả năng của class loader **không biến** nested JAR thành một `java.io.File` mà mọi thư viện có thể mở.

Vì vậy phải tách hai câu hỏi:

1. **Class loader có đọc được class/resource không?** Kiểm tra qua `getResourceAsStream` hoặc loader thích hợp.
2. **Một thư viện bên thứ ba có cần file vật lý không?** Xem API nhận `File`/`Path`/`JarFile(String)` và yêu cầu unpack riêng.

### Không suy luận từ `java.class.path`

Với `java -jar`, property `java.class.path` có thể chỉ phản ánh đường dẫn outer JAR ở tầng Java launcher. Nó **không phải** bảng kê đầy đủ những nested libraries mà Spring Boot application class loader có thể thấy. Nếu muốn chứng minh thiếu dependency, kiểm tra `BOOT-INF/lib` và thử load class qua class loader ứng dụng.

## 3. Giới hạn thứ nhất: outer entry của nested JAR phải là `STORED`

Trong ZIP, `ZipEntry.STORED` nghĩa là **entry không bị nén ở tầng ZIP đang xét**; `ZipEntry.DEFLATED` nghĩa là entry được nén.

Theo Spring Boot Loader, **ZIP entry của một nested JAR trong outer archive phải dùng `ZipEntry.STORED`**. Lý do: loader phải seek trực tiếp đến dữ liệu của nested archive dựa trên offset. Nếu công cụ đóng gói khác nén lại toàn bộ outer entries thành DEFLATED, cơ chế truy cập ngẫu nhiên có thể không còn hoạt động đúng.

~~~text
application.jar  (outer ZIP)
    BOOT-INF/lib/library.jar   <-- outer entry: STORED
        com/example/X.class    <-- entry trong library.jar vẫn có thể DEFLATED
        data/default.json      <-- entry trong library.jar vẫn có thể DEFLATED
~~~

**Quan trọng:** không có yêu cầu phải giải nén từng class/resource bên trong nested JAR. Ràng buộc `STORED` là của **outer ZIP entry đại diện cả nested JAR**; các entry bên trong library vẫn có thể nén bình thường.

Spring Boot Maven và Gradle plugins tạo archive theo yêu cầu đó. Rủi ro tăng khi một bước CI/CD, công cụ sửa ZIP hoặc custom packaging script **repack lại** file sau khi `bootJar`/`repackage` đã hoàn thành. Tên `BOOT-INF/lib/foo.jar` vẫn xuất hiện trong `jar tf` nhưng compression method có thể đã đổi.

**Cách kiểm tra:** dùng Java `JarFile` với `ZipEntry#getMethod()` trên **outer JAR entries**, như công cụ hoàn chỉnh ở mục 9. Đừng chỉ kiểm tra phần mở rộng `.jar`.

## 4. Giới hạn thứ hai: system class loader không nhất thiết thấy nested libraries

Spring Boot launcher dùng một application class loader cho classes và nested JARs. Trong mô hình này, `ClassLoader.getSystemClassLoader()` không bảo đảm nhìn thấy class nằm ở `BOOT-INF/lib`.

Phản ví dụ trong một Java method:

~~~java
Class<?> plugin = Class.forName(
        "com.example.plugins.Widget",
        true,
        ClassLoader.getSystemClassLoader());
~~~

Dòng này có thể thất bại khi chạy executable archive, mặc dù class `Widget` được application loader nạp bình thường. Đây là **minh họa với tên class giả định**, không phải một chương trình có thể chạy riêng.

Khi cần tìm class hoặc resource thuộc application context, thường nên dùng:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> plugin = Class.forName(
        "com.example.plugins.Widget", true, loader);
~~~

Hoặc dùng class loader gắn với một application class đã biết. `Thread.getContextClassLoader()` là phương pháp được nhiều frameworks áp dụng để tương thích custom loaders. Nó không làm class không tồn tại bỗng xuất hiện; `ClassNotFoundException` vẫn có thể xảy ra nếu thư viện thật sự thiếu hoặc bị exclude.

Một số thư viện cũ, tích hợp SPI hoặc code dựa vào system class loader có thể cần cấu hình/phiên bản hỗ trợ Boot Loader. Đừng chữa bằng cách thêm dependency trùng lặp nếu nguyên nhân là **chọn sai loader**.

## 5. Giới hạn thứ ba: classpath resource không phải một `File`

Sai lầm thường gặp:

~~~java
// Chỉ an toàn khi URL thực sự trỏ đến file vật lý.
URL url = getClass().getClassLoader().getResource("guide/message.txt");
File file = new File(url.toURI());
~~~

Khi chạy từ IDE, URL có thể là `file:/.../build/resources/main/guide/message.txt` và conversion thành `File` hoạt động. Trong executable Boot JAR, URL có thể chỉ tới resource **nằm trong archive**, có protocol/syntax nested-JAR khác nhau theo thế hệ loader. Nó không phải URI file hệ thống.

Những cách sau **không phải** phương pháp chung để đọc classpath resource:

~~~java
new File("src/main/resources/guide/message.txt");
Path.of("BOOT-INF/classes/guide/message.txt");
Paths.get(resourceUrl.toURI());
~~~

- `src/main/resources` là source directory trong repo, thường không tồn tại trong container triển khai.
- `BOOT-INF/classes` là path **bên trong archive**, không phải path thực của tiến trình.
- `Paths.get(resourceUrl.toURI())` phụ thuộc filesystem provider tương ứng; URL của nested archive không nhất thiết được provider mặc định hiểu.

Triệu chứng có thể là `URI is not hierarchical`, `FileSystemNotFoundException`, `FileNotFoundException` hoặc đọc nhầm một file trùng tên ngoài archive.

**Giải pháp:** nếu ứng dụng cần **nội dung** tài nguyên, đọc bằng `InputStream` từ class loader hoặc `Resource` của Spring; không yêu cầu filesystem path.

### Java chuẩn: `ClassLoader.getResourceAsStream`

Nếu file nằm ở `src/main/resources/guide/message.txt`, tên resource từ classpath root là `guide/message.txt`, dù khi đóng gói nó nằm ở `BOOT-INF/classes/guide/message.txt`.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

static String loadMessage(ClassLoader loader) throws IOException {
    try (InputStream in = loader.getResourceAsStream(
            "guide/message.txt")) {
        if (in == null) {
            throw new IOException("Missing resource: guide/message.txt");
        }
        return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
    }
}
~~~

Đây là **method minh họa**, cần đặt trong một class Java phù hợp. `readAllBytes()` hợp lệ trên Java 17; với file lớn nên đọc theo luồng để không giữ toàn bộ file trong RAM.

Các nguyên tắc:

- Không thêm `BOOT-INF/classes/` vào tên classpath resource.
- `ClassLoader.getResourceAsStream` thông thường nhận tên **không có dấu `/` ở đầu**.
- Phải kiểm tra `null` khi file không tồn tại.
- Dùng `try-with-resources` để đóng stream, kể cả khi lỗi.
- Xác định charset bằng `StandardCharsets.UTF_8` nếu dữ liệu là text.
- Nếu resource chứa nhiều bản sao trong các JAR, `getResourceAsStream` chỉ mở một bản theo logic của class loader; phải hiểu thứ tự classpath khi sự trùng tên có ý nghĩa.

### Khác biệt giữa `Class.getResourceAsStream` và `ClassLoader.getResourceAsStream`

~~~java
// Tuyệt đối từ classpath root:
MyApplication.class.getResourceAsStream("/guide/message.txt");

// Từ classpath root; không có dấu slash đầu:
MyApplication.class.getClassLoader()
        .getResourceAsStream("guide/message.txt");
~~~

Ở `Class#getResourceAsStream`, dấu `/` ở đầu chọn tên tuyệt đối, còn nếu không có `/` thì tìm tương đối với package của class. Ở `ClassLoader#getResourceAsStream`, dùng tên resource tính từ classpath root, thông thường **không có** `/` đầu. Nhầm quy tắc này làm resource trả `null` dù nó có mặt trong JAR.

## 6. Spring Framework: `ClassPathResource` và `ResourceLoader`

Spring cung cấp abstraction `org.springframework.core.io.Resource` để đọc dữ liệu từ classpath, URL, filesystem và các nguồn khác.

### Đọc qua `ClassPathResource`

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource = new ClassPathResource("guide/message.txt");
try (InputStream in = resource.getInputStream()) {
    String message = new String(
            in.readAllBytes(), StandardCharsets.UTF_8).trim();
    System.out.println(message);
}
~~~

Đây là **snippet bên trong method có xử lý/khai báo `IOException`**, không phải class Java độc lập. Nó dùng luồng đọc mà không cần biết resource nằm ở IDE directory, ordinary JAR hay nested archive.

Tránh:

~~~java
new ClassPathResource("guide/message.txt").getFile();
~~~

`ClassPathResource#getFile()` chỉ hợp lệ khi resource được giải quyết thành file vật lý (ví dụ source set đã build nằm trong directory). Với resource trong JAR chưa được unpack, nó có thể báo lỗi. `getInputStream()` là cách di động hơn.

### Đọc qua `ResourceLoader`

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public final class ConfigReader {
    private final ResourceLoader loader;

    public ConfigReader(ResourceLoader loader) {
        this.loader = loader;
    }

    public byte[] read() throws IOException {
        Resource resource = loader.getResource(
                "classpath:guide/message.txt");
        try (InputStream in = resource.getInputStream()) {
            return in.readAllBytes();
        }
    }
}
~~~

`classpath:` biểu thị resource trong classpath, khác `file:/...` chỉ resource ở filesystem. Đây là class mẫu, cần được tạo hoặc injection trong ngữ cảnh Spring sử dụng. Đừng dùng prefix `file:` chỉ vì file đang nằm ở `src/main/resources` khi phát triển; archive production sẽ không còn source path đó.

| Nhu cầu | API nên ưu tiên | Giới hạn |
| --- | --- | --- |
| Java không cần Spring, tên resource biết trước | `ClassLoader.getResourceAsStream` | Trả null nếu không có |
| Spring resource nội bộ | `ClassPathResource#getInputStream` | `getFile()` không luôn hợp lệ |
| Cấu hình nguồn có prefix rõ ràng | `ResourceLoader#getResource` | Phải chọn đúng `classpath:`/`file:` |
| Cần liệt kê nhiều resource cùng tên | `ClassLoader.getResources` | Thứ tự/cách liệt kê phụ thuộc loader |
| Bên thứ ba bắt buộc cần `File` | Copy có kiểm soát ra temp file hoặc unpack dependency | Cần quản lý tài nguyên và vòng đời file |

## 7. Bài thực hành hoàn chỉnh: đọc classpath resource trong `bootRun` và `java -jar`

Ví dụ dùng Spring Boot 3.3.5, Java 17 và Gradle Groovy DSL. Một resource nằm trong code ứng dụng, còn class `SpringApplication` thuộc dependency JAR. Chương trình xác minh **cả hai đều đọc được** bằng classpath API khi chạy development và archive.

Cấu trúc:

~~~text
nested-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/demo/NestedDemoApplication.java
    └── resources/guide/message.txt
~~~

### File `settings.gradle`

~~~groovy
rootProject.name = 'nested-demo'
~~~

### File `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('bootJar') {
    archiveFileName.set('nested-demo.jar')
}
~~~

`spring-boot-starter` cung cấp Spring runtime cơ bản, không tạo HTTP server. `bootJar` sẽ đóng gói executable JAR, khác `jar` thông thường của Java plugin. Mẫu dùng Spring Boot/Gradle versions cố định để người học tái hiện, không đại diện cho một production recommendation theo thời gian.

### File `src/main/resources/guide/message.txt`

~~~text
HELLO_FROM_ARCHIVE
~~~

### File `src/main/java/com/example/demo/NestedDemoApplication.java`

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.ClassPathResource;

@SpringBootApplication
public class NestedDemoApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(NestedDemoApplication.class, args);
    }

    @Override
    public void run(String... args) throws IOException {
        ClassPathResource resource =
                new ClassPathResource("guide/message.txt");

        try (InputStream in = resource.getInputStream()) {
            String message = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).trim();
            System.out.println("RESOURCE=" + message);
        }

        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        try (InputStream bootClass = loader.getResourceAsStream(
                "org/springframework/boot/SpringApplication.class")) {
            System.out.println(
                    "BOOT_DEPENDENCY_VISIBLE=" + (bootClass != null));
        }
    }
}
~~~

Tính đúng đắn:

1. Tên Java public class khớp tên file và package.
2. `@SpringBootApplication` khiến class ứng dụng là Spring component; `CommandLineRunner` thực thi khi context khởi động.
3. `ClassPathResource` đọc `guide/message.txt` qua stream, không convert sang `File`.
4. `SpringApplication.class` được cung cấp bởi Spring Boot runtime dependency; context class loader vẫn tìm được nó trong executable archive.
5. Cả hai stream được đóng bằng `try-with-resources`.
6. Dữ liệu một dòng UTF-8 cho phép stdout xác định, không phụ thuộc đường dẫn máy.

### Chạy ở development

Nếu dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

Hai dòng do **chính ứng dụng** in:

~~~text
RESOURCE=HELLO_FROM_ARCHIVE
BOOT_DEPENDENCY_VISIBLE=true
~~~

Log Gradle/Spring có thể khác theo máy. Các dòng trên chỉ là output của `System.out.println` trong chương trình.

### Chạy từ executable Boot JAR

~~~bash
./gradlew clean bootJar
java -jar build/libs/nested-demo.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Hai dòng do ứng dụng in vẫn là:

~~~text
RESOURCE=HELLO_FROM_ARCHIVE
BOOT_DEPENDENCY_VISIBLE=true
~~~

Ở đây `guide/message.txt` nằm ở `BOOT-INF/classes` và class `SpringApplication` nằm trong JAR bên dưới `BOOT-INF/lib`. Cơ chế class loader khác development, nhưng API stream vẫn hoạt động.

Kiểm tra outer JAR:

~~~bash
jar tf build/libs/nested-demo.jar
~~~

Trong danh sách rất dài, phải tìm được entry như:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/demo/NestedDemoApplication.class
BOOT-INF/classes/guide/message.txt
~~~

Danh sách còn chứa các `BOOT-INF/lib/...jar` với tên thật. `jar tf` liệt kê **outer entries**; không tự đệ quy hiển thị từng `.class` bên trong nested dependencies.

Trên Windows PowerShell dùng `.\gradlew.bat` thay `./gradlew` và quote arguments theo shell. Nếu chưa có Gradle Wrapper, có thể dùng một Gradle version tương thích để tạo bằng `gradle wrapper --gradle-version 8.7` tại project root.

## 8. Java 17 inspector độc lập: chứng minh compression method của nested JAR

Để kiểm tra quy tắc `STORED`, dùng `JarFile` duyệt **outer JAR entries**. Tạo file `InspectBootArchive.java` độc lập:

~~~java
import java.io.IOException;
import java.util.Enumeration;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipEntry;

public final class InspectBootArchive {
    private InspectBootArchive() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java InspectBootArchive <boot-jar>");
            System.exit(2);
        }

        try (JarFile jar = new JarFile(args[0])) {
            boolean resourcePresent =
                    jar.getEntry("BOOT-INF/classes/guide/message.txt") != null;

            int nestedCount = 0;
            int storedCount = 0;
            Enumeration<JarEntry> entries = jar.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                String name = entry.getName();

                if (!entry.isDirectory()
                        && name.startsWith("BOOT-INF/lib/")
                        && name.endsWith(".jar")) {
                    nestedCount++;

                    if (entry.getMethod() == ZipEntry.STORED) {
                        storedCount++;
                    }
                }
            }

            System.out.println("APP_RESOURCE_PRESENT=" + resourcePresent);
            System.out.println("HAS_NESTED_LIBRARIES=" + (nestedCount > 0));
            System.out.println("ALL_NESTED_STORED=" +
                    (nestedCount > 0 && storedCount == nestedCount));
        }
    }
}
~~~

Biên dịch bằng JDK 17:

~~~bash
javac InspectBootArchive.java
~~~

Sau khi tạo JAR từ bài thực hành và chạy inspector từ đúng thư mục:

~~~bash
java InspectBootArchive build/libs/nested-demo.jar
~~~

Output cho **archive chuẩn của bài này**:

~~~text
APP_RESOURCE_PRESENT=true
HAS_NESTED_LIBRARIES=true
ALL_NESTED_STORED=true
~~~

Số lượng nested libraries không cố định vì nó phụ thuộc dependency versions và plugin. Chương trình chỉ in các giá trị logic cần xác nhận.

**Giới hạn của inspector:** `new JarFile("build/libs/nested-demo.jar")` mở outer archive như file hệ thống. Bạn có thể dùng `jar.getInputStream(entry)` để đọc byte của nested JAR entry, nhưng không thể chỉ đưa `"build/libs/nested-demo.jar!/BOOT-INF/lib/foo.jar"` cho `new JarFile(...)` và kỳ vọng Java coi đó là file JAR vật lý thông thường.

Khi phải phân tích một nested JAR offline, có thể extract entry ra một temp JAR rồi mở bằng `JarFile`, hoặc dùng tooling biết nested archive. Với việc đọc resource trong ứng dụng Boot runtime, cách đơn giản hơn là **đọc qua classloader/Resource stream**, không cần tự giải nén.

## 9. Giới hạn thứ tư: một số thư viện bắt buộc nhận JAR hoặc resource như file thật

Một thư viện đời cũ hoặc native integration có thể:

- gọi `new File(...)` với đường dẫn classpath resource;
- bắt buộc truyền physical `Path` cho API;
- gọi `new JarFile(path)` sau khi suy luận path từ `ProtectionDomain#getCodeSource()`;
- tự đọc nested ZIP nhưng chỉ hỗ trợ một mức JAR;
- yêu cầu shared library/native asset được extract ra một filesystem directory.

Một class có thể được Spring Boot Loader nạp thành công nhưng thư viện vẫn thất bại vì **giả định filesystem**. Không phải lúc nào cũng đúng để thêm lại dependency: vấn đề có thể nằm ở API thư viện.

### `requiresUnpack` — đánh dấu dependency cụ thể cần giải nén

Spring Boot build plugins hỗ trợ đánh dấu một số JAR cần unpack khi chạy. Ví dụ trong `build.gradle` Groovy DSL có `bootJar`:

~~~groovy
tasks.named('bootJar') {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

`JRuby` là ví dụ chính thức về dependency có cơ chế nội bộ yêu cầu JAR như một file thật. Đoạn trên **chỉ có tác dụng** khi project thật sự có dependency phù hợp; đây không phải yêu cầu thêm JRuby vào mọi Boot application.

Maven tương đương, đoạn bên trong `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <requiresUnpack>
        <dependency>
            <groupId>org.jruby</groupId>
            <artifactId>jruby-complete</artifactId>
        </dependency>
    </requiresUnpack>
</configuration>
~~~

Trong những trường hợp được hỗ trợ, Boot Loader sẽ unpack dependency đã đánh dấu tới một thư mục tạm khi cần. Không nên bật unpack cho mọi JAR: nó tốn I/O và làm phát sinh yêu cầu vận hành cho temp directory.

Trong container hoặc môi trường có readonly root filesystem, hãy bảo đảm `java.io.tmpdir` chỉ tới vùng có thể ghi, đủ disk, quyền phù hợp và không bị process dọn file khi app còn sử dụng. Thư viện native cũng có thể yêu cầu môi trường/architecture/ABI riêng — unpack không tự sửa các lỗi tương thích đó.

### Nếu chỉ một resource dữ liệu cần `File`

Khi API bên thứ ba **bắt buộc** nhận `File` và không có overload nhận stream, có thể copy resource ra temp file có kiểm soát:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

static Path materializeResource(
        ClassLoader loader, String name) throws IOException {

    Path temp = Files.createTempFile("resource-", ".bin");
    try (InputStream in = loader.getResourceAsStream(name)) {
        if (in == null) {
            Files.deleteIfExists(temp);
            throw new IOException("Missing resource: " + name);
        }

        Files.copy(in, temp, StandardCopyOption.REPLACE_EXISTING);
        return temp;
    } catch (IOException | RuntimeException ex) {
        Files.deleteIfExists(temp);
        throw ex;
    }
}
~~~

Đây là **method minh họa** trong một class Java, không phải file độc lập. Caller phải xóa file khi dùng xong, giới hạn kích thước dữ liệu, tránh ghi secrets với quyền truy cập quá rộng và bảo đảm temp location hợp lệ. `deleteOnExit()` không phải chiến lược đủ tốt cho dịch vụ sống lâu.

Nếu API đã chấp nhận `InputStream`, `byte[]` hoặc Spring `Resource` thì **không** cần tạo temp file.

## 10. Giới hạn thứ năm: wildcard scanning và nhiều resource trùng tên

Đọc một resource biết tên:

~~~java
loader.getResourceAsStream("guide/message.txt");
~~~

thường dễ dự đoán hơn việc **quét mọi resource** theo pattern trong nhiều JAR lồng. Spring `PathMatchingResourcePatternResolver` hỗ trợ các mẫu như `classpath*:META-INF/services/*`, nhưng kết quả phụ thuộc class loader, URL handling, directory entries và phiên bản thư viện.

Đoạn minh họa trong một Spring method có thể ném `IOException`:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

var resolver = new PathMatchingResourcePatternResolver();
Resource[] resources =
        resolver.getResources("classpath*:META-INF/services/*");
~~~

`classpath*:` cố tìm nhiều resource phù hợp, còn `classpath:` thường đại diện một location trên classpath. Theo tài liệu Spring Framework, quét wildcard ở classpath root có thể gặp giới hạn portability giữa app servers và JAR/classloader implementations.

Lưu ý:

1. Resource có tên trùng nhau ở nhiều dependency có thể trả về nhiều kết quả, theo thứ tự classpath.
2. Tự parse URL của JAR bằng cách split chuỗi theo `!` hoặc tìm `file:` là không đáng tin khi nested URL format khác nhau giữa loader versions.
3. Khi library tự mở URL với `URLClassLoader`/ZIP parser riêng, phải kiểm tra compatibility; việc Spring Boot nạp class thành công không bảo đảm scanner đó hỗ trợ layout.
4. Với resource quan trọng, ưu tiên **tên classpath resource chính xác** thay vì wildcard root scan nếu business logic không cần quét nhiều.
5. Nếu bắt buộc scanning, **test trên executable archive thật**, không chỉ `bootRun` hoặc IDE.

## 11. `classpath.idx` và `layers.idx` không phải magic fix cho classpath

Hai loại index thường được nhầm:

| Index | Dùng làm gì? | Không làm gì? |
| --- | --- | --- |
| `BOOT-INF/classpath.idx` | Mô tả thứ tự nested JAR khi launcher chạy `java -jar` trong cấu hình hỗ trợ | Không tự thêm một library chưa tồn tại trong JAR |
| `BOOT-INF/layers.idx` | Chia artifact thành layer khi tạo image | Không tạo thư mục file vật lý cho mọi nested dependency lúc runtime |

`classpath.idx` không nhất thiết được sử dụng khi chạy ứng dụng từ IDE/`bootRun` hoặc `mvn spring-boot:run`. Khi có lỗi “cùng tên resource nhưng chọn nhầm bản”, thứ tự classpath và duplicate entries cần được xem xét, nhưng **không nên sửa index thủ công** trước khi xác định chính xác dependency graph và artifact.

## 12. `JarLauncher`, `PropertiesLauncher` và chạy exploded

`JarLauncher` phù hợp layout executable JAR mặc định, tìm nested libraries trong `BOOT-INF/lib`. `WarLauncher` áp dụng layout WAR. `PropertiesLauncher` hỗ trợ cơ chế cấu hình đường dẫn bổ sung, chẳng hạn qua `loader.path` hoặc `LOADER_PATH` theo phiên bản, và yêu cầu manifest/launcher phù hợp.

Không suy luận `-Dloader.path=...` luôn có hiệu lực với `JarLauncher` mặc định. Nếu cần external libraries, hãy xác định launcher đang dùng trong `Main-Class` và đọc tài liệu Spring Boot của đúng phiên bản.

Một số môi trường lựa chọn **exploded archive**: unpack artifact vào directories và thiết lập cách chạy thích hợp. Khi đó dependency có thể là file vật lý, nhưng không có nghĩa chỉ giải nén JAR là mọi lệnh hoạt động tương đương `java -jar`. Cần giữ đúng main class, classpath và resources.

Chọn exploded layout, shaded JAR hoặc cấu hình unpack **chỉ khi** thư viện thực tế không tương thích nested format và không thể sửa API đọc resource. Cách sửa một dòng `getInputStream()` thường đơn giản hơn đổi cả phương pháp phân phối artifact.

## 13. Kiểm chứng bằng công cụ Gradle và Maven

### Gradle

~~~bash
./gradlew clean bootJar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
jar tf build/libs/nested-demo.jar
~~~

- `runtimeClasspath` cho biết dependency graph được resolve; việc library có nằm trong archive còn phụ thuộc packaging config, exclusions và artifact đã được build đúng chưa.
- `dependencyInsight` giúp xác định vì sao version được chọn.
- `jar tf` hiển thị file/entry của outer archive; nó không đệ quy đi sâu vào từng dependency JAR.
- Inspector ở mục 8 kiểm tra outer compression method.

### Maven

~~~bash
mvn clean package
mvn dependency:tree
mvn help:effective-pom
jar tf target/your-application.jar
~~~

`your-application.jar` là tên minh họa cần thay bằng tên artifact thực tế. Với Maven, `spring-boot-maven-plugin` và goal `repackage` phải được cấu hình/bind phù hợp. Chỉ import Spring Boot BOM hoặc thêm `spring-boot-starter` **không tự bảo đảm** tạo executable Boot JAR. Một plain JAR không nhất thiết có `BOOT-INF/lib` hoặc Boot launcher.

Cả hai hệ thống đều cần **kiểm tra đúng file sẽ triển khai**, không chỉ đọc build script và suy luận.

## 14. Triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý/kiểm chứng |
| --- | --- | --- |
| `getFile()` chạy được từ IDE nhưng lỗi trong JAR | Resource ở trong archive | Dùng `getInputStream` |
| `URI is not hierarchical` | Biến `jar:`/nested URL thành `File` | Dùng stream; chỉ tạo temp file nếu API bắt buộc |
| `FileSystemNotFoundException` | ZIP/nested URL không được filesystem provider hỗ trợ | Đọc qua classloader/Resource |
| `ClassNotFoundException` với system loader | Class trong application loader | Thử TCCL; kiểm tra `BOOT-INF/lib` |
| `jar tf` có `foo.jar` nhưng API nói file không tồn tại | JAR là nested entry, không phải physical file | Dùng `requiresUnpack` cho thư viện xác định |
| JAR bị repack bằng ZIP tool rồi khởi động lỗi | Outer nested JAR entries thành `DEFLATED` | Kiểm tra `ZipEntry.STORED`, sửa bước đóng gói |
| Resource chỉ hiện khi `bootRun` | Chưa được package hoặc nằm ở dev-only path | Đưa vào đúng source set; xác minh `BOOT-INF/classes` |
| `getResourceAsStream` trả null | Sai tên/case, slash đầu hoặc thiếu file | Kiểm tra classpath root, archive listing |
| Class có mặt nhưng `NoClassDefFoundError` | Thiếu dependency bắc cầu hoặc lỗi initialization | Đọc `Caused by`, xem dependency versions |
| `NoSuchMethodError` | Có thể sai binary compatibility giữa các versions | So resolved versions và archive |
| Wildcard `classpath*:` bỏ sót file | Scanner/URL/classloader portability | Test trong packaged archive, ưu tiên tên chính xác |
| Native library lỗi `UnsatisfiedLinkError` | OS/ABI/path/extraction khác | Kiểm tra native platform, filesystem, temp directory |
| `java.class.path` chỉ hiển thị outer JAR | Boot launcher dùng application loader | Không kết luận mất nested dependencies |
| Không thấy class nested qua `jar tf` | Công cụ chỉ liệt kê outer entries | Trích riêng nested JAR hoặc dùng tooling phù hợp |

### Quy trình chẩn đoán 8 bước

1. **Xác nhận đúng artifact**, đúng Git revision/build và JVM runtime tương thích.
2. **Đọc manifest** để biết launcher, `Main-Class` và `Start-Class`.
3. **Liệt kê outer archive**: `BOOT-INF/classes` và `BOOT-INF/lib` có nội dung dự kiến không?
4. **Kiểm tra method STORED** nếu có bước custom ZIP/repack trong pipeline.
5. **Thử resource/class loader**: `Thread.currentThread().getContextClassLoader().getResourceAsStream(...)` trả gì?
6. **Tìm giả định filesystem**: `getFile()`, `new File(url.toURI())`, `Paths.get(url.toURI())`, `JarFile(codeSource)`.
7. **Sửa chính xác**: đổi sang stream/`Resource`, đưa resource vào main source set, hoặc cấu hình unpack cho **đúng dependency** bắt buộc cần file.
8. **Build lại rồi chạy đúng executable archive** trong môi trường gần production và kiểm tra exception chain.

## 15. Câu hỏi ôn tập

**Câu 1.** `BOOT-INF/lib/example.jar` xuất hiện trong `jar tf application.jar`. Có thể mở ngay bằng `new File("BOOT-INF/lib/example.jar")` không?

**Đáp án:** Không chỉ từ việc tên entry có mặt. JAR đó nằm trong outer archive chứ không nhất thiết là một file hệ thống độc lập.

**Câu 2.** Vì sao outer nested-JAR entry phải là `STORED` còn class bên trong nested JAR vẫn có thể `DEFLATED`?

**Đáp án:** Spring Boot Loader cần seek trực tiếp tới vị trí nested archive trong outer file, nhưng có thể giải nén từng entry class/resource bên trong nested JAR như JAR thông thường.

**Câu 3.** `ClassPathResource#getInputStream` đọc được file trong executable JAR nhưng `getFile` thất bại. Đây có phải lỗi packaging không?

**Đáp án:** Không nhất thiết. Resource có thể tồn tại trên classpath nhưng không có physical file path. Stream là API đúng khi chỉ cần nội dung.

**Câu 4.** Dùng `ClassLoader.getSystemClassLoader()` để nạp class từ `BOOT-INF/lib` có đáng tin không?

**Đáp án:** Không phải trong mọi cấu hình Spring Boot Loader. Ưu tiên thread context loader hoặc class loader của application class khi phù hợp.

**Câu 5.** Có nên dùng `requiresUnpack` cho mọi dependency?

**Đáp án:** Không. Phần lớn dependency được Boot Loader nạp trực tiếp. Chỉ unpack khi xác định một thư viện cần JAR vật lý và chuẩn bị temp directory phù hợp.

**Câu 6.** Tại sao `jar tf` không in tất cả class nằm trong `BOOT-INF/lib/spring-core-....jar`?

**Đáp án:** Vì đó là nested JAR nằm dưới dạng **một entry** của outer archive; `jar tf` không tự giải nén và duyệt recursive entry của nested JAR.

**Câu 7.** `classpath.idx` có thêm dependency chưa tồn tại vào executable JAR không?

**Đáp án:** Không. Index mô tả thứ tự các JAR được nạp, không tải hoặc đóng gói một thư viện mới.

**Câu 8.** Cách nào chứng minh resource đọc đúng khi ứng dụng triển khai?

**Đáp án:** Build executable JAR, kiểm tra `BOOT-INF/classes`/`BOOT-INF/lib`, rồi **chạy chính JAR đó** và đọc resource qua stream từ application/context class loader; không chỉ test từ IDE.

## 16. Tài liệu chính thức

- Spring Boot — [Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html): cấu trúc archive, nested libraries và index files.
- Spring Boot — [Executable Jar Restrictions](https://docs.spring.io/spring-boot/specification/executable-jar/restrictions.html): `ZipEntry.STORED` và system class loader.
- Spring Boot — [NestedJarFile](https://docs.spring.io/spring-boot/specification/executable-jar/jarfile-class.html): offset mapping và URL handling của nested JAR.
- Spring Boot — [Launching Executable Jars](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html): `JarLauncher`, `WarLauncher`, `PropertiesLauncher`.
- Spring Boot — [Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar` và `requiresUnpack`.
- Spring Boot — [Build How-to](https://docs.spring.io/spring-boot/how-to/build.html): unpack thư viện đặc biệt và temp directory.
- Spring Framework — [Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `ClassPathResource`, `ResourceLoader` và giới hạn wildcard scan.
- Oracle Java 17 — [JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html) và [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html): kiểm tra contents và compression method.

**Kết luận:** Spring Boot Loader giúp nạp class và resource từ nested JAR mà không phải giải nén toàn bộ, nhưng **không biến mọi nested entry thành file vật lý**. Hãy dùng class loader đúng, đọc tài nguyên bằng stream, để build plugin tạo layout `STORED` phù hợp, và unpack một cách có chọn lọc khi API bên thứ ba bắt buộc cần filesystem.
