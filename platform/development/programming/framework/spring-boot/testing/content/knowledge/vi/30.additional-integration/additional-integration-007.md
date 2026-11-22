# ClassPathResource trong test và giới hạn khi ứng dụng được đóng gói

## 1. Vấn đề: test chạy xanh nhưng ứng dụng đóng gói lại lỗi

Trong module **Spring Boot - testing**, nhóm **Tích hợp bổ sung**, một lỗi quen thuộc là đoạn code đọc tài nguyên trong `src/main/resources` hoặc `src/test/resources` chạy được bằng IDE, `gradlew test` và `bootRun` nhưng thất bại sau khi đóng gói thành Spring Boot executable JAR.

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: đường dẫn vật lý không phải hợp đồng runtime.
Path path = Paths.get("src/main/resources/templates/greeting.txt");
String message = Files.readString(path, StandardCharsets.UTF_8);
~~~

Nó phụ thuộc *working directory* là thư mục gốc source repository và việc còn giữ source tree bên cạnh process. Trong Docker image hoặc sau `java -jar app.jar`, thư mục `src/main/resources` có thể **không tồn tại**.

Phản ví dụ thứ hai tinh vi hơn:

~~~java
// PHẢN VÍ DỤ: có thể PASS lúc test trên thư mục build/resources/main,
// nhưng FAIL khi tài nguyên nằm trong executable JAR.
ClassPathResource resource =
        new ClassPathResource("templates/greeting.txt");
String message = Files.readString(
        resource.getFile().toPath(),
        StandardCharsets.UTF_8
);
~~~

`ClassPathResource` tìm đúng tài nguyên qua classpath, nhưng lệnh `getFile()` **đòi một filesystem file thật**. Resource nằm trong JAR chưa bung ra không có đường dẫn File tương ứng. Khi đó Spring thường ném `FileNotFoundException` cho việc chuyển resource thành File dù resource **có tồn tại và đọc được bằng stream**.

Cách portable:

~~~java
ClassPathResource resource =
        new ClassPathResource("templates/greeting.txt");

try (InputStream input = resource.getInputStream()) {
    String message = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
}
~~~

Đây là đoạn code minh họa cần imports `java.io.InputStream`, `java.nio.charset.StandardCharsets` và `org.springframework.core.io.ClassPathResource`; bộ ví dụ hoàn chỉnh nằm ở phần sau.

**Kết quả cần đạt:** phân biệt resource và File; hiểu classpath của test/main và cấu trúc Spring Boot JAR; dùng `getInputStream()`/`ResourceLoader`/`@Value Resource` đúng; biết giới hạn của `getFile()`, `getURL()`, `classpath*:`; viết JUnit tests tạo JAR thật để phát hiện lỗi bị IDE che; và có một bước packaged smoke test với `bootJar`/`java -jar`.

## 2. Resource là abstraction, không mặc định là java.io.File

Spring Framework cung cấp `org.springframework.core.io.Resource` để đại diện cho dữ liệu có thể đọc từ nhiều nguồn.

| Resource implementation | Thường biểu diễn | Điều cần nhớ |
| --- | --- | --- |
| `ClassPathResource` | Tài nguyên được tìm qua classloader/classpath | Có thể nằm trong **thư mục hoặc JAR** |
| `FileSystemResource` | Tệp trong hệ thống tệp thật | Phù hợp khi app cần filesystem path |
| `UrlResource` | `file:`, `https:` và các URL phù hợp | Không mọi URL đều chuyển thành File |
| `ByteArrayResource` | Mảng byte trong memory | Tốt cho unit tests không cần IO |
| `InputStreamResource` | Một stream đã mở | Thường **single-use**, không mặc định replay nhiều lần |
| `ServletContextResource` | Resource qua ServletContext | Phụ thuộc môi trường web, không mặc định là File |

Những thao tác trọng tâm của `Resource`:

- `exists()`: kiểm tra resource có thể được xác định; `false` cho tài nguyên không tồn tại.
- `getInputStream()`: mở stream đọc; người gọi phải **close** bằng `try-with-resources`.
- `getURL()`: đại diện đường dẫn resource bằng URL nếu triển khai hỗ trợ; URL có thể là `file:`, `jar:` hoặc URL do classloader của Spring Boot tạo.
- `getURI()`: URI resource, **không đồng nghĩa** với một `Path` đọc được bởi provider filesystem mặc định.
- `getFile()`: chỉ an toàn khi resource thực sự có filesystem path; JAR entry thường **không**.
- `contentLength()`: metadata kích thước; có thể yêu cầu IO, đừng coi là cache giá trị luôn rẻ.
- `getFilename()`, `getDescription()`: hữu ích cho chẩn đoán, không chứng minh resource có File tương ứng.
- `createRelative(...)`: tạo resource path tương đối theo cơ chế của loại Resource đó.

Spring documentation nhấn mạnh `ClassPathResource` có thể được chuyển thành `File` **chỉ khi resource nằm trên filesystem**, còn resource trong JAR có thể truy cập qua URL/stream. Không phải vì `getFile()` lỗi mà JAR bị hỏng.

## 3. Classpath khác thư mục source và working directory

Khi dùng cấu trúc Gradle Java tiêu chuẩn:

~~~text
project/
  src/main/java/           Java production source
  src/main/resources/      Production resource source
  src/test/java/           Java test source
  src/test/resources/      Test-only resource source

  build/classes/java/main/
  build/resources/main/
  build/classes/java/test/
  build/resources/test/
  build/libs/
~~~

Trong mặc định Gradle:

- `processResources` đưa `src/main/resources` tới `build/resources/main`.
- `processTestResources` đưa `src/test/resources` tới `build/resources/test`.
- `test` dùng classpath gồm outputs của source set `test` **và** những gì cần từ `main`, cùng test dependencies.
- `bootJar` đóng gói **application/main artifacts** và runtime dependencies; test source/resources **không được đưa vào production JAR mặc định**.
- `bootRun` chạy classpath của application, không phải toàn bộ test runtime classpath.
- `java -jar ...` nạp tài nguyên từ executable archive thông qua Spring Boot loader, không cần source tree.

Hậu quả:

| Tài nguyên | `gradlew test` | `gradlew bootRun` | `java -jar bootJar` |
| --- | --- | --- | --- |
| `src/main/resources/templates/greeting.txt` | Có | Có | Có, dưới `BOOT-INF/classes` |
| `src/test/resources/fixtures/test-only.txt` | **Có** | **Không mặc định** | **Không mặc định** |
| `src/main/resources/com/example/.../anchored.txt` | Có | Có | Có |
| File nằm ngoài project, chỉ path tuyệt đối | Phụ thuộc máy | Phụ thuộc máy | Phụ thuộc deployment/mount |

Nếu Spring Boot test **chỉ đọc được file test fixture**, đừng suy rằng nó sẽ đọc được file đó trong production. Ngược lại, nếu test classpath che một resource cùng tên từ main hay dependency, ứng dụng đóng gói có thể chọn resource khác.

## 4. Spring Boot executable JAR thay đổi vị trí vật lý

Một Spring Boot executable JAR dạng chuẩn có cấu trúc:

~~~text
portable-resources-demo-0.0.1-SNAPSHOT.jar
  META-INF/
    MANIFEST.MF
  org/springframework/boot/loader/...
  BOOT-INF/
    classes/
      com/example/portable/ResourceApp.class
      com/example/portable/ResourceReader.class
      templates/greeting.txt
      com/example/portable/anchored.txt
    lib/
      spring-core-...jar
      spring-boot-...jar
      ...
~~~

Đây là **cấu trúc minh họa**, tên các dependency jar bên dưới `BOOT-INF/lib` thay đổi theo dependency versions. Thư viện được lưu như **nested JARs**, không phải luôn được bung hết thành thư mục thật. Spring Boot loader tạo classloader hỗ trợ nạp classes/resources trong kiểu đóng gói này.

Resource logical name vẫn là:

~~~text
templates/greeting.txt
~~~

**Không phải**:

~~~text
src/main/resources/templates/greeting.txt
BOOT-INF/classes/templates/greeting.txt
~~~

khi gọi `new ClassPathResource(...)`. Prefix `BOOT-INF/classes` là **layout nội bộ archive**, không phải phần của logical classpath path mà code ứng dụng phải truyền vào.

**Quy tắc:** kiểm tra classpath resource thông qua `Resource.getInputStream()` thay vì tính File path từ vị trí vật lý của executable JAR. Đừng mở JAR của chính ứng dụng rồi tự trích entry để đọc một dòng text đơn giản; đó là việc classloader đã hỗ trợ.

## 5. So sánh getInputStream, getURL và getFile

| API | Test trên expanded directory | Test với plain JAR | Spring Boot executable JAR |
| --- | --- | --- | --- |
| `resource.exists()` | Có thể true | Có thể true | Có thể true |
| `resource.getInputStream()` | **Đọc được** | **Đọc được** | **Đọc được** với Boot loader đúng |
| `resource.getURL()` | URL `file:...` | URL `jar:...` | Boot-aware URL; scheme/layout có thể đặc biệt |
| `resource.getFile()` | Thường được | **Không** nếu entry còn trong JAR | **Không** với entry trong JAR chưa bung |
| `Files.readString(resource.getFile().toPath())` | Có thể được | **Lỗi** | **Lỗi** |
| `Paths.get(resource.getURI())` | Có thể được với `file:` URI | Không thể mặc định coi là path FS | Không portable |
| `new File(resource.getURL().getFile())` | Có thể tình cờ hoạt động | Sai với `jar:` và encoded URLs | Không portable |

`ClassPathResource#getFile()` **không phải** lựa chọn an toàn chỉ vì test hiện tại sử dụng Gradle. Sau khi tạo JAR, URL resource chuyển thành archive-backed URL và việc chuyển sang File thất bại.

Với `getURL()`: nó hữu ích khi gọi API tiêu thụ URL, nhưng **không** tự động gọi `new File(url.getPath())`. Ký tự khoảng trắng và Unicode có thể được URL encode; một URL `jar:...!/entry` không phải đường dẫn filesystem. Với native filesystem API đòi `Path`, cần cân nhắc copy tài nguyên vào thư mục tạm trước.

## 6. Hai cách đọc đúng: InputStream và ResourceLoader

**Cách thứ nhất — ClassPathResource trực tiếp:**

~~~java
Resource resource = new ClassPathResource(
        "templates/greeting.txt"
);

try (InputStream in = resource.getInputStream()) {
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

Đây là snippet trong method có return type `String` và imports phù hợp. Nó sử dụng cùng mã với cả expanded classpath và packaged JAR.

**Cách thứ hai — ResourceLoader cho URI kiểu Spring:**

~~~java
Resource resource =
        resourceLoader.getResource(
                "classpath:templates/greeting.txt"
        );

try (InputStream in = resource.getInputStream()) {
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

Đây là snippet, `resourceLoader` có kiểu `org.springframework.core.io.ResourceLoader`. `classpath:` được hiểu là **classpath location prefix**, không phải một directory literal.

**Cách thứ ba — inject Resource qua @Value:**

~~~java
@Value("classpath:templates/greeting.txt")
private Resource greeting;
~~~

Đây là field snippet cần imports `@Value` và `Resource`, và object phải được Spring quản lý. `@Value`/`ResourceLoader` giúp tách source code khỏi chi tiết resource path; đừng inject một `String` path rồi ép nó thành `File` khi đã có abstraction.

### Đóng stream là bắt buộc

`getInputStream()` tạo stream đọc cần close. Khi đọc những tệp lớn, `readAllBytes()` không phù hợp vì nạp toàn bộ vào heap; nên dùng `BufferedReader`/`InputStream.transferTo`/streaming parser. Khi đọc hình ảnh/PDF/ZIP/binary, đừng ép mọi bytes sang String theo charset.

## 7. Đường dẫn root, ClassLoader và class-relative path

`ClassPathResource` có nhiều constructor:

~~~java
new ClassPathResource("templates/greeting.txt");
new ClassPathResource("/templates/greeting.txt");
new ClassPathResource(
        "templates/greeting.txt",
        someClassLoader
);
new ClassPathResource(
        "anchored.txt",
        ResourceReader.class
);
~~~

Đây là các biểu thức minh họa, cần các biến/type tương ứng. Phân biệt:

1. Khi truyền một `ClassLoader`, path thông thường tính từ **classpath root**, và leading slash được chuẩn hóa bỏ đi.
2. Khi truyền một `Class<?>` và path **không có leading slash**, lookup tương đối với **package của class**.
3. Khi truyền một `Class<?>` với path bắt đầu bằng `/`, lookup tính từ **classpath root**.
4. `ClassPathResource` không phải API nhận OS path; dùng `/` trong logical classpath path trên mọi hệ điều hành, kể cả Windows.

Ví dụ `ResourceReader.class` nằm trong package `com.example.portable`. Với file:

~~~text
src/main/resources/com/example/portable/anchored.txt
~~~

thì:

~~~java
new ClassPathResource("anchored.txt", ResourceReader.class);
~~~

tìm đúng file đó. Còn:

~~~java
new ClassPathResource("templates/greeting.txt", ResourceReader.class);
~~~

sẽ thử `com/example/portable/templates/greeting.txt`, **không** phải `templates/greeting.txt` ở root.

Vì vậy test cần xác nhận path resolution theo constructor thực tế. Một lỗi khác là truyền path với dấu `\\` kiểu Windows hoặc thêm `src/main/resources` vào trước logical name.

## 8. Test-only resources: đừng ship fixture vào production

`src/test/resources` là vị trí đúng cho:

- JSON/XML/CSV fixtures với test cases cụ thể.
- Input files mô phỏng malformed payload.
- Truststore/chứng thư **chỉ dành cho test** (không dùng key/secret production).
- Snapshots có version được test quản lý.
- Golden files mà application runtime **không** cần.

`src/main/resources` dành cho:

- Templates/config defaults mà application cần lúc chạy.
- Static assets do app phục vụ.
- Localization bundles; schema/migration scripts nếu thuộc runtime contract.
- Các resource phải tồn tại trong executable artifact.

Ví dụ một test đọc `fixtures/test-only.txt` thành công chỉ chứng minh nó ở **test runtime classpath**. Không được viết production service phụ thuộc file này mà không chuyển asset sang `src/main/resources` hoặc cung cấp external filesystem resource có cấu hình.

**Cảnh báo bảo mật:** Mặc định test resources không vào `bootJar`, nhưng điều đó không làm chúng thành nơi lưu credential production an toàn; CI test artifacts hoặc source control vẫn có thể công khai nội dung. Không đặt token/password thật trong cả main lẫn test resources.

## 9. Một project runnable để kiểm tra cả test classpath và packaged JAR

Project ví dụ dùng **Java 17 / Spring Boot 3.5.16 / Gradle Groovy DSL**. Boot 3.5.16 được chọn như một phiên bản minh họa nhất quán; với ứng dụng production mới, dùng dòng Spring Boot còn được hỗ trợ phù hợp chính sách nâng cấp của tổ chức.

Cấu trúc thư mục chính xác:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/portable/
    ResourceApp.java
    ResourceReader.java
src/main/resources/
    templates/greeting.txt
    com/example/portable/anchored.txt
src/test/java/com/example/portable/
    ResourceReaderTest.java
    ResourceAppSmokeTest.java
src/test/resources/
    fixtures/test-only.txt
~~~

**Phạm vi chạy:**

- `ResourceReaderTest`: unit tests với tài nguyên main/test, file thật ở `@TempDir` và một **JAR tự tạo ngay trong test** để chứng minh stream đọc được nhưng `getFile()` thất bại.
- `ResourceAppSmokeTest`: Spring integration test xác minh `@Value("classpath:...")` và `ResourceLoader`.
- `java -jar`: packaged smoke, in `MAIN_RESOURCE=...` và `TEST_ONLY_PRESENT=false`; chứng minh main asset vẫn đọc được khi không còn source tree.

Không cần web server, database, Docker, broker hay external network trong runtime của app ví dụ. Gradle lần đầu có thể cần tải dependencies.

## 10. settings.gradle và build.gradle

**`settings.gradle`:**

~~~groovy
rootProject.name = 'portable-resources-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` cung cấp Spring Core `Resource` và auto-configuration tối thiểu; `spring-boot-starter-test` có JUnit Jupiter và AssertJ. Java 17 có `InputStream.readAllBytes()`, `StandardCharsets.UTF_8` và JUnit `@TempDir`.

Gradle sẽ tạo cả `jar` thường và `bootJar` theo plugin; **executable JAR** được dùng ở phần kiểm tra đóng gói là output của `bootJar`, không phải một thin/plain JAR thiếu dependencies.

## 11. ResourceApp: chạy và in tín hiệu packaged resource

**`src/main/java/com/example/portable/ResourceApp.java`:**

~~~java
package com.example.portable;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

@SpringBootApplication
public class ResourceApp {

    public static void main(String[] args) {
        SpringApplication.run(ResourceApp.class, args);
    }

    @Bean
    ApplicationRunner printResourceProbe(
            ResourceReader reader
    ) {
        return args -> {
            Resource main = new ClassPathResource(
                    "templates/greeting.txt"
            );

            System.out.println(
                    "MAIN_RESOURCE="
                    + reader.readUtf8(main).strip()
            );
            System.out.println(
                    "TEST_ONLY_PRESENT="
                    + new ClassPathResource(
                            "fixtures/test-only.txt"
                    ).exists()
            );
        };
    }
}
~~~

Ở đây `ApplicationRunner` được Spring Boot gọi sau khi application context sẵn sàng. Nó đọc **main resource bằng stream**, không dùng `getFile()`. Phần in kiểm tra test-only fixture chỉ có mục đích học về **classpath visibility**, không phải logic production cần giữ.

Khi chạy ứng dụng từ **executable JAR** được tạo theo cấu hình mặc định, kỳ vọng hai dòng:

~~~text
MAIN_RESOURCE=Xin chào từ main
TEST_ONLY_PRESENT=false
~~~

Spring Boot có thể in thêm banner/startup logs trước hoặc sau các dòng trên, nên **không** khẳng định đây là toàn bộ stdout. Khi chạy `@SpringBootTest`, `TEST_ONLY_PRESENT` có thể là `true` vì test runtime classpath chứa `src/test/resources`. Không assert trên console output của test để chứng minh packaged behavior.

**Nếu resource main thiếu:** `getInputStream()` ném lỗi, application startup qua `ApplicationRunner` không hoàn thành. Đây là lỗi hợp lý, tốt hơn việc âm thầm thay bằng file từ working directory không thuộc package.

## 12. ResourceReader: một phương pháp đọc portable

**`src/main/java/com/example/portable/ResourceReader.java`:**

~~~java
package com.example.portable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class ResourceReader {

    public String readUtf8(Resource resource)
            throws IOException {
        try (InputStream stream = resource.getInputStream()) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }

    public String readClasspath(String classpathPath)
            throws IOException {
        return readUtf8(
                new ClassPathResource(classpathPath)
        );
    }
}
~~~

Đây là class **đầy đủ, không phụ thuộc filesystem path**. Khi truyền một `Resource`, code hoạt động với `ClassPathResource`, `FileSystemResource`, `ByteArrayResource` và các implementations trả input stream.

Cách sử dụng:

~~~java
String text = reader.readClasspath(
        "templates/greeting.txt"
);
~~~

Đây là snippet bên trong một method có `reader` là `ResourceReader`. Nhớ rằng tham số `classpathPath` phải là **đường dẫn được kiểm soát theo contract**, không đưa thẳng input từ HTTP user vào path để tránh đọc tài nguyên classpath nhạy cảm ngoài ý muốn.

### Vì sao không dùng String.read() với default encoding?

`new String(bytes)` và `FileReader` không chỉ rõ encoding có thể phụ thuộc default charset của runtime (đặc biệt Java 17 trên nhiều nền tảng). Ví dụ dùng `StandardCharsets.UTF_8` để bảo toàn tiếng Việt khi máy CI và máy developer khác OS.

`readAllBytes()` chỉ phù hợp cho tài nguyên text **nhỏ**. Khi xử lý ảnh, ZIP, PDF hay file lớn, dùng streaming API và không biến binary thành String.

## 13. Nội dung resource trong src/main/resources

**`src/main/resources/templates/greeting.txt`:**

~~~text
Xin chào từ main
~~~

**`src/main/resources/com/example/portable/anchored.txt`:**

~~~text
Tài nguyên theo package
~~~

Trong `templates/greeting.txt`, dòng newline cuối file (nếu có) được `.strip()` bỏ trước assertion/hiển thị. Đừng dựa vào line-ending LF/CRLF từ IDE làm bằng chứng resource khác nội dung; nếu output byte-for-byte là contract, cần assert bytes/charset và có fixture được chuẩn hóa.

Đặt asset theo logical path với `/` và giữ tên file chữ thường, đơn giản để tránh khác nhau về case sensitivity giữa Windows/Linux. Ví dụ `Templates/Greeting.txt` có thể lookup được trên filesystem case-insensitive trong IDE nhưng FAIL trong JAR có entry name case-sensitive.

## 14. Nội dung test-only fixture

**`src/test/resources/fixtures/test-only.txt`:**

~~~text
Chỉ dành cho test
~~~

Test runtime classpath tìm thấy `fixtures/test-only.txt`, nhưng khi tạo `bootJar` theo cấu hình mặc định không có file này.

Nếu production service cần `fixtures/test-only.txt` thật, phải xem lại yêu cầu: hoặc nó là **runtime asset** và chuyển sang main resources, hoặc nó thực sự là **external config/data** và nên cung cấp qua đường dẫn mount, database hoặc storage. Không dùng workaround chép toàn bộ test resources vào `BOOT-INF/classes` để “chữa” một lỗi package nếu không hiểu nội dung test fixture và thông tin nhạy cảm bên trong.

## 15. Unit tests: classpath root, package anchor và file missing

**`src/test/java/com/example/portable/ResourceReaderTest.java`:**

~~~java
package com.example.portable;

import java.io.FileNotFoundException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ResourceReaderTest {

    private final ResourceReader reader =
            new ResourceReader();

    @Test
    void mainClasspathResourceCanBeReadAsUtf8()
            throws Exception {
        String text = reader.readClasspath(
                "templates/greeting.txt"
        );
        assertThat(text.strip())
                .isEqualTo("Xin chào từ main");
    }

    @Test
    void testOnlyFixtureIsVisibleInTestRuntime()
            throws Exception {
        String text = reader.readUtf8(
                new ClassPathResource(
                        "fixtures/test-only.txt"
                )
        );
        assertThat(text.strip())
                .isEqualTo("Chỉ dành cho test");
    }

    @Test
    void leadingSlashWithClassLoaderIsRootRelative()
            throws Exception {
        ClassPathResource resource =
                new ClassPathResource(
                        "/templates/greeting.txt"
                );

        assertThat(resource.exists()).isTrue();
        assertThat(reader.readUtf8(resource).strip())
                .isEqualTo("Xin chào từ main");
    }

    @Test
    void classRelativePathUsesTheClassPackage()
            throws Exception {
        ClassPathResource anchored =
                new ClassPathResource(
                        "anchored.txt",
                        ResourceReader.class
                );

        ClassPathResource root =
                new ClassPathResource(
                        "/templates/greeting.txt",
                        ResourceReader.class
                );

        ClassPathResource wrongRelative =
                new ClassPathResource(
                        "templates/greeting.txt",
                        ResourceReader.class
                );

        assertThat(anchored.exists()).isTrue();
        assertThat(reader.readUtf8(anchored).strip())
                .isEqualTo("Tài nguyên theo package");

        assertThat(root.exists()).isTrue();
        assertThat(reader.readUtf8(root).strip())
                .isEqualTo("Xin chào từ main");

        assertThat(wrongRelative.exists()).isFalse();
    }

    @Test
    void missingClasspathResourceIsNotTheSameAsMissingFile()
            throws Exception {
        ClassPathResource missing =
                new ClassPathResource(
                        "missing/unknown.txt"
                );

        assertThat(missing.exists()).isFalse();
        assertThatThrownBy(
                () -> missing.getInputStream()
        ).isInstanceOf(FileNotFoundException.class);
    }

    @Test
    void realFileSystemResourceSupportsFilePath(
            @TempDir Path temp
    ) throws Exception {
        Path file = temp.resolve("on-disk.txt");
        Files.writeString(
                file,
                "Ở filesystem",
                StandardCharsets.UTF_8
        );

        FileSystemResource resource =
                new FileSystemResource(file);

        assertThat(resource.exists()).isTrue();
        assertThat(resource.getFile().toPath())
                .isEqualTo(file);

        assertThat(reader.readUtf8(resource))
                .isEqualTo("Ở filesystem");
    }

    @Test
    void jarEntrySupportsInputStreamButNotGetFile(
            @TempDir Path temp
    ) throws Exception {
        Path jarFile = temp.resolve("demo-fixture.jar");

        // Tạo một JAR thật với đúng một entry text.
        try (JarOutputStream jar =
                     new JarOutputStream(
                             Files.newOutputStream(jarFile)
                     )) {
            jar.putNextEntry(
                    new JarEntry("packed/inside.txt")
            );
            jar.write(
                    "Nội dung trong JAR".getBytes(
                            StandardCharsets.UTF_8
                    )
            );
            jar.closeEntry();
        }

        // Dùng riêng JAR đó làm classpath cho resource.
        try (URLClassLoader isolatedLoader =
                     new URLClassLoader(
                             new URL[] {
                                     jarFile.toUri().toURL()
                             },
                             null
                     )) {
            ClassPathResource resource =
                    new ClassPathResource(
                            "packed/inside.txt",
                            isolatedLoader
                    );

            assertThat(resource.exists()).isTrue();
            assertThat(reader.readUtf8(resource))
                    .isEqualTo("Nội dung trong JAR");

            // Resource vẫn tồn tại, nhưng không có
            // filesystem file cho entry nằm bên trong JAR.
            assertThatThrownBy(
                    () -> resource.getFile()
            ).isInstanceOf(FileNotFoundException.class);
        }
    }
}
~~~

### Các test này thật sự xác nhận điều gì?

- **Test 1–3:** main/test resource nằm trên test classpath, đọc được với UTF-8; leading slash khi dùng ClassLoader constructor không làm đổi logical root lookup.
- **Test 4:** constructor dùng `Class<?>` phải phân biệt package-relative và classpath-root.
- **Test 5:** missing resource `exists=false` và `getInputStream` báo `FileNotFoundException`.
- **Test 6:** FileSystemResource cho file thật ở `@TempDir` có thể trả `File`.
- **Test 7:** tạo một **plain JAR** ngay trong JUnit, dùng `URLClassLoader` load entry; **stream thành công nhưng `getFile()` ném FileNotFoundException**.

Test 7 là điểm cốt lõi: nó chống hiện tượng **IDE/Gradle che lỗi** vì `ClassPathResource.getFile()` tình cờ chạy được khi resources ở expanded directories. Nó không cần Docker hay chạy production jar để xác minh quy tắc archive resource cơ bản.

**Giới hạn:** Test 7 dùng plain JAR/URLClassLoader của JDK. Spring Boot executable JAR có **nested JAR classloader** riêng; vì vậy cần chạy thêm packaged smoke `bootJar` ở phần sau. Đừng coi plain JAR test là đã kiểm đủ mọi behavior của Boot loader trong mọi deployment layout.

## 16. Spring integration test: @Value Resource và ResourceLoader

**`src/test/java/com/example/portable/ResourceAppSmokeTest.java`:**

~~~java
package com.example.portable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ResourceApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ResourceAppSmokeTest {

    @Autowired
    ResourceReader reader;

    @Autowired
    ResourceLoader resourceLoader;

    @Value("classpath:templates/greeting.txt")
    Resource greeting;

    @Test
    void springInjectsResourceFromClasspathLocation()
            throws Exception {
        assertThat(greeting.exists()).isTrue();
        assertThat(reader.readUtf8(greeting).strip())
                .isEqualTo("Xin chào từ main");
    }

    @Test
    void resourceLoaderReadsWithoutAssumingFileSystem()
            throws Exception {
        Resource resolved = resourceLoader.getResource(
                "classpath:templates/greeting.txt"
        );

        assertThat(resolved.exists()).isTrue();
        assertThat(reader.readUtf8(resolved).strip())
                .isEqualTo("Xin chào từ main");

        assertThat(new ClassPathResource(
                "fixtures/test-only.txt"
        ).exists()).isTrue();
    }
}
~~~

Hai ca Spring integration xác nhận:

1. Bean `ResourceReader` được Spring quản lý; `@Value("classpath:...")` resolve thành `Resource`.
2. `ResourceLoader` hiểu prefix `classpath:`.
3. Trong **test runtime**, fixture từ `src/test/resources` có mặt — đây là trạng thái **dự kiến của test**, không phải của executable JAR.

`ResourceApp` có `ApplicationRunner` tự in kết quả khi context start, nên trong `@SpringBootTest` có thể thấy `TEST_ONLY_PRESENT=true`. Điều đó không mâu thuẫn với `TEST_ONLY_PRESENT=false` khi chạy `java -jar`; hai lần chạy sử dụng classpath khác nhau.

Có **9 JUnit test methods**: 7 trong `ResourceReaderTest` và 2 trong `ResourceAppSmokeTest`. Test suite không assert filesystem path thật của `ClassPathResource`; chỉ test `FileSystemResource.getFile` cho tệp do `@TempDir` tạo.

## 17. Đóng gói và kiểm chứng bằng bootJar

Từ thư mục dự án đã có Gradle Wrapper và JDK 17+:

~~~bash
./gradlew clean test bootJar
~~~

Dự án kết thúc thành công nếu toàn bộ chín test PASS và executable jar được build. Khi build xong, chạy:

~~~bash
java -jar build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

Kết quả liên quan đến lesson (giữa các logs của Spring Boot):

~~~text
MAIN_RESOURCE=Xin chào từ main
TEST_ONLY_PRESENT=false
~~~

Kết quả **được dự kiến theo source** và cấu hình source sets, không phải stdout thật đã thu thập khi soạn bài. Không có gì trong code cần tham số command line hoặc environment variable bổ sung.

### Kiểm tra nội dung archive với jar tf

~~~bash
jar tf build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

Tìm các entries:

~~~text
BOOT-INF/classes/templates/greeting.txt
BOOT-INF/classes/com/example/portable/anchored.txt
~~~

**Không nên có**:

~~~text
BOOT-INF/classes/fixtures/test-only.txt
~~~

Đừng assert thứ tự entries trong `jar tf` hay tên đầy đủ từng dependency ở `BOOT-INF/lib` nếu đó không phải contract. `bootJar` có thể sắp xếp/reproduce archive theo cấu hình Gradle/Boot.

### PowerShell trên Windows

~~~powershell
.\gradlew.bat clean test bootJar

java -jar .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar

jar tf .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar |
    Select-String "BOOT-INF/classes/(templates/greeting.txt|fixtures/test-only.txt)"
~~~

Lệnh `Select-String` giúp thấy entry main được đóng gói và test-only fixture không được in ra. Nếu muốn xác nhận không có fixture một cách tự động trong CI, đọc danh sách `jar tf` rồi assert **không** chứa entry của `fixtures/test-only.txt`; chỉ grep trực quan chưa phải một assertion tự động.

**Không khẳng định** `./gradlew test` một mình kiểm được packaged JAR. Test runtime thường dùng exploded directories; `bootJar + java -jar` mới thực hành hành vi của executable archive.

## 18. Những khác biệt quan trọng giữa test, bootRun và java -jar

| Thuộc tính | `gradlew test` | `gradlew bootRun` | `java -jar` |
| --- | --- | --- | --- |
| Runtime classpath | `main` + `test` outputs/deps | Thường là `main` runtime classpath | Spring Boot executable archive |
| Main resources | Có | Có | Có |
| Test resources | **Có** | Không mặc định | Không mặc định |
| Classpath resource vật lý | Thường thư mục build/resources | Thường thư mục build/resources | `BOOT-INF/classes` trong JAR |
| `ClassPathResource.getFile` | Có thể PASS | Có thể PASS | Thường **FAIL** với JAR entry |
| `Resource.getInputStream` | PASS nếu asset có | PASS nếu asset có | PASS nếu asset được đóng gói/loader đúng |
| Working directory | Theo test task/IDE | Theo Gradle run | Theo command/service/container |
| URL scheme | Thường `file:` | Thường `file:` | Archive-aware URL, không ép thành File |
| Kiểm tra test-only resource bị loại | **Không** | Có thể quan sát | **Có** |

Bảng mô tả **mặc định**, không áp dụng nếu project custom source sets, shadow JAR, exploded layers, `bootRun.classpath` hoặc tự chép fixtures vào runtime artifacts. Khi có build tùy chỉnh, dùng `jar tf` và packaged smoke test xác nhận thực tế.

## 19. Khi API bắt buộc cần File/Path thì làm gì?

Một số thư viện legacy chỉ nhận `File` hoặc `Path` thay vì `InputStream`/`Reader`. **Không gọi bừa `getFile()` trên classpath resource**. Có hai lựa chọn tốt hơn:

1. **Ưu tiên đổi adapter** để thư viện nhận `InputStream` hoặc `Resource` nếu API hỗ trợ.
2. Nếu bắt buộc File, **copy resource sang thư mục tạm hoặc thư mục làm việc được quản lý**, rồi truyền Path/File đã materialize.

Ví dụ helper **độc lập**:

~~~java
package com.example.portable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.core.io.Resource;

public final class ResourceMaterializer {

    private ResourceMaterializer() {
    }

    public static Path copyToTempFile(
            Resource resource,
            String prefix,
            String suffix
    ) throws IOException {
        Path temp = Files.createTempFile(prefix, suffix);

        boolean ok = false;
        try (InputStream in = resource.getInputStream()) {
            Files.copy(
                    in,
                    temp,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING
            );
            ok = true;
            return temp;
        } finally {
            if (!ok) {
                Files.deleteIfExists(temp);
            }
        }
    }
}
~~~

Đây là một **class tùy chọn** có thể thêm vào project nếu tích hợp thư viện legacy; không cần nó để chạy 9 tests ở phần chính. Caller chịu trách nhiệm:

~~~java
Path temp = ResourceMaterializer.copyToTempFile(
        new ClassPathResource("templates/greeting.txt"),
        "greeting-",
        ".txt"
);
try {
    // Chuyển temp.toFile() cho API thật sự cần File.
} finally {
    Files.deleteIfExists(temp);
}
~~~

Đoạn này là **snippet sử dụng**, cần imports và một lời gọi thư viện cụ thể trong ứng dụng thật. Trong test dùng `@TempDir` càng tốt: JUnit kiểm soát cleanup. Production cần giới hạn size, dung lượng đĩa, permissions, lifecycle và xử lý crash, không giữ file tạm vĩnh viễn.

**Không viết ngược** vào file tài nguyên trong JAR. Packaged resources nên coi là **read-only**; dữ liệu runtime cần thay đổi phải đặt ở external filesystem, volume, database hoặc object storage.

## 20. ResourceLoader và dependency injection giúp test linh hoạt

Khi service phụ thuộc một template, có thể inject `Resource` để dễ unit test:

~~~java
public final class TemplateService {
    private final Resource template;

    public TemplateService(Resource template) {
        this.template = template;
    }

    public String load() throws IOException {
        try (InputStream in = template.getInputStream()) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Đây là skeleton minh họa, cần imports `Resource`, `InputStream`, `IOException`, `StandardCharsets`. Unit test có thể truyền `new ByteArrayResource("hello".getBytes(UTF_8))`, không phải khởi động Spring hay tạo tệp thật.

Production bean có thể inject:

~~~java
@Bean
TemplateService templateService(
        @Value("classpath:templates/greeting.txt")
        Resource resource
) {
    return new TemplateService(resource);
}
~~~

Đây là method `@Bean` minh họa cần imports. Test qua `ByteArrayResource` xác nhận business logic; integration test qua `ClassPathResource` xác nhận wiring/path; packaged smoke test xác nhận asset thực sự nằm trong JAR. Mỗi tầng bắt một lớp lỗi khác nhau.

**Lưu ý:** `ByteArrayResource` và `ClassPathResource` cùng thực hiện `Resource` nhưng không có nghĩa `getFile()` đều hoạt động; tránh đặt giả định về File path trong interface consumer.

## 21. Classpath patterns: classpath: khác classpath*:

`ClassPathResource` đọc **một logical location**, không phải pattern scanner cho `*.json`. Nếu cần lấy nhiều resources có cùng pattern qua các JAR/classpath entries, dùng Spring `ResourcePatternResolver`.

~~~java
ResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] rules = resolver.getResources(
        "classpath*:rules/*.json"
);

for (Resource rule : rules) {
    try (InputStream in = rule.getInputStream()) {
        // Parse JSON từ stream.
    }
}
~~~

Đây là snippet minh họa, không phải file runnable của project; cần imports:

~~~java
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
~~~

Phân biệt:

- `classpath:rules/example.json`: một classpath location, thường chọn resource đầu tiên có path đó.
- `classpath*:rules/example.json`: tìm **mọi matching classpath locations** khi API resolver hỗ trợ, hữu ích nếu nhiều JAR cùng cung cấp một path.
- `classpath*:rules/*.json`: pattern scan nhiều files, nhưng khả năng quét JAR/directory roots, classloader và module paths có các giới hạn được tài liệu Spring nêu rõ.
- `new ClassPathResource("rules/*.json")`: **không phải** tự tìm mọi files; nó sẽ thử lookup literal path.

**Không nên liệt kê “các file nằm trong resource directory” bằng `getFile().listFiles()`.** Sau khi đóng gói JAR, directory entries không nhất thiết là thư mục OS. Nếu danh sách files là contract bắt buộc, có thể dùng `ResourcePatternResolver` kèm tests trong JAR thực, hoặc đóng gói một index/manifest tài nguyên tường minh để dùng bền vững.

## 22. Trùng resource name trên nhiều JAR và thứ tự classloader

Classpath có thể chứa:

~~~text
dependency-a.jar!/config/defaults.properties
dependency-b.jar!/config/defaults.properties
BOOT-INF/classes/config/defaults.properties
~~~

Một `ClassPathResource("config/defaults.properties")` thường chỉ cho bạn **một** resource theo kết quả lookup của classloader hiện tại. Đừng giả định nó luôn đến từ JAR A, JAR B hay application nếu resource path trùng nhau và thứ tự classpath có thể đổi giữa IDE, `bootRun` và `java -jar`.

Khi cần merge nhiều nguồn:

- Dùng namespace riêng theo library, ví dụ `META-INF/my-library/rules.json`.
- Dùng `ResourcePatternResolver` với `classpath*:` khi thật sự phải lấy nhiều resources.
- Xác định rõ thứ tự/override policy, sort theo key có ý nghĩa trước khi merge nếu order quan trọng.
- Test cả lúc resources nằm trong JAR dependencies.
- Không log secrets từ resource chỉ để debug classloader path.

Một `ClassLoader#getResource` có thể trả URL đầu tiên, còn `getResources` có thể enumerate nhiều URLs. Enumeration behavior và classpath order là chuyện loader/runtime; **không sử dụng một thứ tự tình cờ làm hợp đồng business**.

## 23. Vì sao test unit thành công vẫn chưa bảo đảm packaged runtime?

Các điểm cần soát:

1. **Resource có trong test runtime, nhưng không trong main JAR.** Nguyên nhân: đặt nhầm `src/test/resources`.
2. **`getFile()` thành công do Gradle copy file ra thư mục.** Nguyên nhân: code đang dựa vào File, không dùng stream.
3. **Đường dẫn `src/main/resources/...` chạy được ở repo.** Nguyên nhân: working directory/source tree còn hiện diện.
4. **Classpath resource trùng tên với dependency.** Nguyên nhân: classpath order khác khi đóng gói.
5. **Case mismatch** (File.txt và file.txt). Nguyên nhân: test trên Windows/macOS filesystem ít phân biệt case, JAR/Linux phân biệt.
6. **File chứa Unicode** nhưng code đọc bằng default charset. Nguyên nhân: encoding OS/JVM khác.
7. **Đổi JAR layout** từ expanded/layered sang nested, code cố xử lý URL string thành File.
8. **Khai báo absolute filesystem path trong config** nhưng container không mount file đó.
9. **Tạo file runtime dưới classpath** trong local dev; JAR resource read-only và không có đường dẫn ghi.
10. **Test @SpringBootTest vẫn nhìn thấy fixtures**, làm ứng dụng code dùng asset không được ship mà không báo lỗi.

Do đó nên có **ba lớp bằng chứng**:

| Lớp | Kiểm gì? | Ví dụ |
| --- | --- | --- |
| Unit test | Resource parser/reader và stream semantics | `ResourceReaderTest`, jar-only test |
| Spring wiring test | `@Value Resource`, `ResourceLoader`, classpath root | `ResourceAppSmokeTest` |
| Packaged smoke test | App chạy bằng `java -jar`, main asset có, test-only fixture vắng | `bootJar` + CLI |

Một JUnit test tạo plain JAR rất hữu ích nhưng **không thay** smoke test trực tiếp executable archive khi bạn triển khai bằng Docker, OCI layers hoặc custom classloaders.

## 24. Chẩn đoán lỗi getFile / missing resource

| Lỗi hoặc dấu hiệu | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `FileNotFoundException ... cannot be resolved to absolute file path` | Resource là entry bên trong JAR | Dùng `getInputStream()`, không `getFile()` |
| `FileNotFoundException ... does not exist` | Logical resource path sai hoặc asset không ở classpath | Kiểm path, source set, `jar tf` |
| `exists=true` nhưng `getFile` FAIL | File path không tồn tại dù stream đọc được | Đây là behavior bình thường của JAR resource |
| IDE PASS, `java -jar` FAIL | Dùng `src/main/resources` path hoặc `getFile` | Stream + packaged smoke |
| Test PASS, production missing fixture | File chỉ có ở `src/test/resources` | Chuyển đúng main resource hoặc external config |
| Resource có ở BOOT-INF/classes nhưng lookup fail | Truyền prefix `BOOT-INF/classes` vào logical path | Dùng root-relative `templates/...` |
| Path với `\\` trên Windows | Dùng OS path làm classpath name | Dùng `/` trong classpath |
| Resource name sai chữ hoa/thường | FS và JAR/Linux khác nhau | Chuẩn hóa tên, test trên Linux/JAR |
| Byte tiếng Việt bị lỗi | Đọc bằng default charset | UTF-8 tường minh |
| `NoSuchFileException` ở container | File nằm ở host, chưa mount vào container | Volume/path config tường minh |
| `Paths.get(jarUri)` fail | URI không thuộc filesystem provider mặc định | Đọc qua stream |
| `new File(url.getFile())` chứa `%20` | URL encoded hoặc `jar:` scheme | Không chuyển URL sang File thủ công |
| `getFile().listFiles()` trả null/fail sau packaging | Không có thư mục filesystem cho JAR entries | `ResourcePatternResolver` hoặc manifest |
| Duplicate resource ở hai dependencies | Classloader chọn một theo lookup order | Namespace hoặc `classpath*:` + merge policy |
| Test tạo file dưới resources rồi production không thấy | Resource trong JAR không phải storage có thể ghi | Dùng external directory/DB |
| File lớn làm OutOfMemoryError | `readAllBytes()` trên tài nguyên quá lớn | Stream/BufferedReader |
| Spring context load lỗi vì resource required | File không có trong packaged classpath | Kiểm file path, imports, build outputs |
| Build custom không include resource | `processResources`/sourceSets custom | Inspect tasks, output, `jar tf` |
| Test chiếu đúng fixture nhưng sai user-facing locale | Đọc nhầm classpath path hoặc charset | Đặt đúng locale files, test resource lookup |
| Classloader khác trong plugin/app server | TCCL và class-anchored loader khác | Dùng explicit loader khi cần, test runtime thật |

Đừng “sửa” `FileNotFoundException` của `getFile()` bằng cách catch rồi dùng hard-coded absolute path trên máy developer. Điều đó làm test bớt portable. Chỉ chuyển sang File khi thư viện thật sự yêu cầu filesystem file, và lúc đó cần materialize tạm/thiết kế storage riêng.

## 25. Resource trong container/Docker và native images

### Docker với executable JAR

Ví dụ Docker image có:

~~~text
/app/app.jar
~~~

Resource trong `BOOT-INF/classes/templates/greeting.txt` vẫn đọc qua classloader dù không có `/app/src/main/resources` hoặc một `/app/BOOT-INF/classes` directory trên filesystem.

Nếu ứng dụng cần đọc **file thay đổi sau deploy**, ví dụ `/etc/my-service/templates/greeting.txt`, hãy cấu hình một `FileSystemResource` hoặc `UrlResource` trỏ tới volume mount, thay vì đóng gói resource rồi cố ghi lại nó.

Một ví dụ tách location qua config:

~~~properties
app.template-location=classpath:templates/greeting.txt
~~~

Và trong code Spring-managed:

~~~java
public TemplateService(
        ResourceLoader loader,
        @Value("${app.template-location}")
        String location
) {
    this.template = loader.getResource(location);
}
~~~

Đây là constructor snippet cần định nghĩa `Resource template`, imports và service class. Nếu môi trường production muốn override, có thể đặt `app.template-location=file:/etc/my-service/greeting.txt`. Test cần kiểm tra cả default classpath và optional external location được mount đúng.

**Bảo mật:** Không cho request user tùy ý chỉ định `file:///etc/...` hoặc classpath secret path mà không có allowlist/authorization; `ResourceLoader` là abstraction mạnh, không phải bộ lọc bảo mật.

### Native image và AOT

Native image không mặc định chứa **mọi** arbitrary classpath resource theo cách JVM/JAR. Khi build GraalVM native image, cần resource hints/metadata để resource được include nếu không được framework nhận diện tự động. Spring Boot có AOT resource hints và `RuntimeHints`.

Đoạn minh họa:

~~~java
hints.resources().registerPattern(
        "templates/greeting.txt"
);
~~~

Đây là snippet nằm trong `RuntimeHintsRegistrar.registerHints(...)` với biến `hints` phù hợp; **không** thuộc project runnable. Nếu phát hành native executable, cần native build/smoke test riêng, không dùng kết quả `bootJar` làm bằng chứng tài nguyên có trong native image.

## 26. Cách kiểm tra packaging khi tài nguyên do dependency cung cấp

Trong starter/third-party library, tài nguyên có thể đến từ `some-library.jar` trong `BOOT-INF/lib` thay vì app `BOOT-INF/classes`. Spring Boot loader vẫn có thể giải classpath resource qua loader thích hợp.

Các tình huống nên test:

- Asset nằm ở `src/main/resources` của **library** và được đóng vào library JAR trước khi app tiêu thụ.
- App và library có trùng logical resource name.
- File được copy/filter lúc `processResources`; placeholder build-time đã được thay?
- Source set test của library có fixture nhưng JAR published không chứa.
- Resource trong library là folder-like name cần scan pattern qua `classpath*:`.
- Khi app upgrade Boot Loader hoặc đổi Docker layering, stream lookup vẫn đúng.

Không giải quyết bằng cách hard-code `BOOT-INF/lib/library.jar!/path` vào business code. Đó là layout internal, không phải Resource contract; dùng logical classpath path và test từ packaged artifact.

## 27. Checklist review: Java 17 + Spring Boot resource tests

- [ ] Mọi runtime asset được đặt đúng `src/main/resources` hoặc external storage?
- [ ] Test-only fixture đúng `src/test/resources` và không bị production tham chiếu?
- [ ] Code nhận logical classpath path, không ghép `src/main/resources` thành OS path?
- [ ] Không dùng `ClassPathResource.getFile()` chỉ để đọc bytes/text?
- [ ] Mọi stream từ `getInputStream()` được close bằng `try-with-resources`?
- [ ] Text được decode bằng charset tường minh, ưu tiên UTF-8?
- [ ] Binary/large resources được streaming, không `readAllBytes` bừa?
- [ ] Constructor `Class<?>` đã phân biệt package-relative và leading-slash root?
- [ ] ClassLoader/TCCL được dùng đúng khi ứng dụng có custom loader?
- [ ] Dùng `ResourceLoader` hoặc `@Value Resource` thay vì giả định File path?
- [ ] Khi cần file thật, dùng `FileSystemResource` hoặc copy vào `@TempDir`/managed temp?
- [ ] Resource trong JAR được thử bằng `URLClassLoader` và `JarOutputStream` test?
- [ ] Có Spring context smoke test cho `@Value` và `ResourceLoader`?
- [ ] Đã build `bootJar` và chạy `java -jar` để thấy packaged behavior?
- [ ] `jar tf` có main resource dưới `BOOT-INF/classes`?
- [ ] `jar tf` không vô tình có fixture từ `src/test/resources`?
- [ ] Không khẳng định `gradlew test` tương đương packaged deployment?
- [ ] Có xét duplicate logical resource paths và classpath order?
- [ ] Nếu cần scan folder/pattern, dùng `ResourcePatternResolver` thay vì `getFile().listFiles()`?
- [ ] Không cố convert `jar:` URL thành `File`/`Path` của OS?
- [ ] Không cố ghi vào archive-backed resource sau deploy?
- [ ] External resource file trong Docker được mount với path/permission rõ?
- [ ] Không nhúng secrets thật vào test/main resource artifacts?
- [ ] Có test filename case sensitivity, encoding và line endings theo contract?
- [ ] Nếu phát hành GraalVM native image, có resource hints và native smoke test?
- [ ] Mã nguồn/shell commands đã được phân biệt với stdout **dự kiến**, không nhận là đã chạy khi chưa chạy?

## 28. Lệnh chạy và expected behavior

Từ dự án đã có Gradle Wrapper, Java 17+ và dependencies:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
jar tf build/libs/portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar
jar tf .\build\libs\portable-resources-demo-0.0.1-SNAPSHOT.jar
~~~

### Expected outcome từ 9 test methods

| Test | Expected |
| --- | --- |
| `mainClasspathResourceCanBeReadAsUtf8` | `Xin chào từ main` |
| `testOnlyFixtureIsVisibleInTestRuntime` | `Chỉ dành cho test` |
| `leadingSlashWithClassLoaderIsRootRelative` | Root resource được tìm |
| `classRelativePathUsesTheClassPackage` | Package resource có, wrong relative path vắng |
| `missingClasspathResourceIsNotTheSameAsMissingFile` | `exists=false` và FileNotFoundException |
| `realFileSystemResourceSupportsFilePath` | `FileSystemResource.getFile` hoạt động |
| `jarEntrySupportsInputStreamButNotGetFile` | InputStream đọc được; `getFile` FileNotFoundException |
| `springInjectsResourceFromClasspathLocation` | `@Value Resource` đọc được |
| `resourceLoaderReadsWithoutAssumingFileSystem` | `ResourceLoader` đọc được; fixture test có |

### Expected packaged output

~~~text
MAIN_RESOURCE=Xin chào từ main
TEST_ONLY_PRESENT=false
~~~

**Đây là kỳ vọng xác định bằng cấu trúc source sets và code**; chưa phải Gradle/JUnit/java-jar output thực tế đã chạy khi biên soạn nội dung. Project cần Gradle Wrapper/JDK, và runtime có thể thêm Spring startup logs. Test JUnit không đảm bảo việc packed JAR đã được chạy; để có bằng chứng đầy đủ, CI nên có **riêng một packaged smoke step** sau `bootJar`.

**Tổng kết:** `ClassPathResource` là một abstraction để đọc dữ liệu theo classpath, **không phải lời hứa có File path**. Unit test trong IDE có thể che bug `getFile()` vì tài nguyên đang ở directory; sau packaging, resource nằm trong JAR. Hãy dùng `Resource.getInputStream()`, giữ logic đọc không phụ thuộc working directory, phân biệt main/test source sets và kết hợp JAR-entry test với một packaged executable smoke. Khi thực sự cần File, hãy tạo file tạm có vòng đời rõ ràng thay vì ép một JAR entry thành `File`.

### Tài liệu tham khảo chính thức

- [Spring Framework — Resources, ClassPathResource và Resource interface](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Framework — ClassPathResource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/ClassPathResource.html)
- [Spring Framework — ResourcePatternResolver và classpath*](https://docs.spring.io/spring-framework/reference/core/resources.html#resources-app-ctx)
- [Spring Boot — Executable JAR Format và Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/)
- [Gradle — Java Plugin source sets và processResources](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Managing Resources](https://docs.gradle.org/current/userguide/building_java_projects.html#sec:java_resources)
- [JUnit Jupiter — @TempDir temporary directories](https://docs.junit.org/current/user-guide/#writing-tests-built-in-extensions-TempDirectory)
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)