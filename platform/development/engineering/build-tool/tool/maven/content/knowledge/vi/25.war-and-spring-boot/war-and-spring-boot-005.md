# Phân biệt JAR thường với JAR có cấu trúc thực thi của Spring Boot

## 1. Bài học giải quyết vấn đề gì?

Cùng là file `.jar` và đều có thể được tạo bởi Maven, nhưng **JAR thường** và **Spring Boot executable JAR** không nhất thiết có cấu trúc bên trong giống nhau. Nếu chỉ dựa vào đuôi file hoặc câu `BUILD SUCCESS`, bạn rất dễ chẩn đoán sai vấn đề triển khai.

Ví dụ:

- Một JAR thông thường chứa `demo/boot/BootJarLabApplication.class` ngay tại gốc archive.
- Một JAR được Spring Boot Maven Plugin **repackage** lại có thể chứa class ấy tại `BOOT-INF/classes/demo/boot/BootJarLabApplication.class`.
- Thư viện Spring Framework và những runtime dependencies được chọn có thể nằm dưới `BOOT-INF/lib/*.jar` dưới dạng **JAR lồng trong JAR**.
- Manifest của Boot executable JAR thường dùng `Main-Class` trỏ tới **Spring Boot launcher**, còn `Start-Class` trỏ tới class `main` thật của ứng dụng.
- Dùng `java -cp app.jar demo.boot.BootJarLabApplication` với một JAR đã repackage không tương đương `java -jar app.jar`: class ứng dụng không nằm tại classpath root tiêu chuẩn.
- Một JAR thông thường **vẫn có thể chạy được bằng `java -jar`** nếu nó có `Main-Class` phù hợp và mọi runtime dependencies được cung cấp. “JAR thường” không đồng nghĩa “vĩnh viễn không thực thi được”.

Mục tiêu sau bài học:

1. Nhận biết cấu trúc **plain/thin JAR** và **Spring Boot executable/fat JAR dạng nested JARs**.
2. Giải thích cơ chế `jar:jar` → `spring-boot:repackage` của Maven.
3. Đọc `META-INF/MANIFEST.MF`, phân biệt `Main-Class` và `Start-Class`.
4. Dùng `jar tf` và `JarFile` để kiểm tra vị trí classes, resources và libraries.
5. Tạo **hai kiểu JAR từ cùng một project Java 17** để so sánh chính xác.
6. Hiểu `.jar.original`, classifier, các quy tắc dependency và những lỗi triển khai/CI thường gặp.
7. Không nhầm Boot JAR, shaded JAR, executable WAR, exploded archive và container image.

Các ví dụ dùng **Spring Boot 3.5.0**, JDK 17+, Maven 3.9.x hoặc bản Maven tương thích. Version 3.5.0 được **ghim có chủ đích để học cách đóng gói**, không phải tuyên bố đây là bản Spring Boot mới nhất.

## 2. Hai định dạng đều là JAR/ZIP, khác nhau ở layout và launcher

JAR là archive dựa trên ZIP. Bản chất ZIP/JAR không bắt buộc class nằm trong thư mục nào; runtime class loader và công cụ đóng gói quyết định cách sử dụng entries.

### 2.1. JAR thường từ Maven JAR Plugin

Một project Java `jar` thông thường được Maven Compiler Plugin biên dịch vào `target/classes`; Maven JAR Plugin đóng gói từ output này:

~~~text
plain-app.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/...
├── demo/
│   └── app/
│       └── Main.class
├── config/
│   └── app.properties
└── ...
~~~

Trong bố cục này:

- Class `demo.app.Main` có entry `demo/app/Main.class`.
- File `src/main/resources/config/app.properties` thường có entry `config/app.properties`.
- Main classes/resources nằm **ngay dưới gốc classpath của archive**.
- Dependency JARs **không tự động được nhúng** chỉ vì chúng được khai báo trong Maven `<dependencies>`.
- Manifest có thể có hoặc không có `Main-Class`, tùy cấu hình và mục đích JAR.

Một library JAR như vậy được thêm vào classpath của ứng dụng khác rất tự nhiên: `demo/app/Main.class` nằm ngay nơi class loader chuẩn tìm khi binary name là `demo.app.Main`.

### 2.2. Spring Boot executable JAR

Sau khi Spring Boot Maven Plugin chạy `repackage` trên JAR đã có:

~~~text
boot-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/
│   └── springframework/
│       └── boot/
│           └── loader/
│               └── launch/
│                   └── JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   ├── demo/
    │   │   └── app/
    │   │       └── Main.class
    │   └── config/
    │       └── app.properties
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   └── other-dependencies....jar
    ├── classpath.idx   (nếu được tạo)
    └── layers.idx      (nếu được tạo)
~~~

Sơ đồ có dấu `...` trong tên file để **minh họa**, không phải listing chính xác cho một project/version cụ thể. Một số entries chỉ xuất hiện tùy options và plugins.

Ở cấu trúc Boot:

- Mã ứng dụng: `BOOT-INF/classes/`.
- Resource chính: cũng nằm dưới `BOOT-INF/classes/`.
- Thư viện runtime được repackage chọn: `BOOT-INF/lib/`, mỗi dependency thường vẫn là một file JAR riêng.
- Bootstrap loader: nằm ở **gốc archive** để JVM có thể tìm lớp launcher được nêu trong manifest.
- Manifest `Main-Class`: thường là `org.springframework.boot.loader.launch.JarLauncher` đối với Spring Boot 3.2+ ở layout JAR tiêu chuẩn.
- Manifest `Start-Class`: tên class có `main()` của chính ứng dụng.

**Ý quan trọng:** Spring Boot executable JAR không đơn giản là “JAR thường được thêm `Main-Class`”. Nó có **layout mới và launcher riêng** để các nested dependency JARs được đọc đúng ở runtime.

## 3. Bảng so sánh nhanh

| Tiêu chí | Plain/thin JAR thường | Spring Boot executable JAR mặc định |
| --- | --- | --- |
| Định dạng vật lý | ZIP/JAR | ZIP/JAR |
| Vị trí application class | `demo/app/Main.class` | `BOOT-INF/classes/demo/app/Main.class` |
| Vị trí resource chính | `config/app.properties` | `BOOT-INF/classes/config/app.properties` |
| Vị trí dependencies | Thường là JARs bên ngoài, hoặc do bước packaging khác cung cấp | Nested JARs dưới `BOOT-INF/lib/` theo chính sách repackage |
| Class loader khi chạy | Java classpath/loading thông thường | Boot loader thiết lập class loader cho nested JARs |
| Manifest Main-Class | Có thể thiếu, hoặc trỏ tới app main | Thường trỏ tới Boot `JarLauncher` |
| Manifest Start-Class | Không bắt buộc | Trỏ tới main class của ứng dụng |
| Chạy bằng `java -jar` | Có thể, nếu manifest/runtime classpath đúng | Được thiết kế để chạy theo cách này |
| Được dùng như Maven dependency/library JAR | Phù hợp khi API/classes ở archive root | Không phù hợp làm dependency JAR trực tiếp ở layout mặc định |
| Công cụ đóng gói | `maven-jar-plugin:jar` | `jar:jar` sau đó `spring-boot:repackage` |
| Dùng trong CI | Xác nhận classes/resources, manifest và external runtime libs | Xác nhận BOOT-INF layout, libs, launcher và app startup |
| Dùng để chạy container | Có thể với classpath/distribution đúng | Có thể `java -jar` hoặc khai thác layers |
| Tên file | `*.jar` | Cũng `*.jar`; **không thể nhận biết chỉ qua đuôi** |

Bảng diễn tả **bố cục mặc định**. Maven Shade Plugin tạo kiểu uber JAR khác, Spring Boot hỗ trợ custom layout/classifier, và có những plain JAR tự chạy được không cần Boot.

## 4. Vì sao Spring Boot phải dùng một launcher riêng?

Java launcher hỗ trợ:

~~~bash
java -jar app.jar
~~~

JVM đọc `META-INF/MANIFEST.MF` và tìm `Main-Class`. Với một JAR tiêu chuẩn, class loader không mặc nhiên hiểu rằng:

~~~text
outer.jar!/BOOT-INF/lib/spring-context.jar!/org/springframework/...
~~~

là một classpath JAR phụ **lồng trong một JAR khác**. Không thể chỉ đặt các nested dependency JARs vào một plain JAR rồi kỳ vọng Java classpath loader tiêu chuẩn tự khám phá chúng.

Spring Boot giải quyết bằng **Spring Boot Loader**:

1. JVM tìm `Main-Class` của bootstrap launcher **ở gốc outer JAR**.
2. `JarLauncher` nhận diện `BOOT-INF/classes/` và `BOOT-INF/lib/`.
3. Boot Loader tạo cấu trúc classpath/class loader hỗ trợ đọc các nested JARs.
4. Launcher đọc `Start-Class` trong manifest.
5. Launcher chuyển quyền thực thi tới `main(String[] args)` của ứng dụng.

Một chuỗi gọi ở mức ý tưởng:

~~~text
java -jar boot-app.jar
          |
          v
META-INF/MANIFEST.MF
          |
          +-- Main-Class: org.springframework.boot.loader.launch.JarLauncher
          |
          v
Spring Boot Loader
          |
          +-- BOOT-INF/classes/
          +-- BOOT-INF/lib/*.jar
          |
          v
Start-Class: demo.boot.BootJarLabApplication
          |
          v
SpringApplication.run(...)
          |
          v
Ứng dụng chạy
~~~

Tên launcher `org.springframework.boot.loader.launch.JarLauncher` áp dụng cho các phiên bản Boot hiện đại như 3.5.0; ở các tài liệu Spring Boot 2.x cũ, bạn có thể gặp tên `org.springframework.boot.loader.JarLauncher`. **Không sao chép tên launcher đời cũ vào manifest của một project Boot mới** nếu plugin có thể tạo metadata đúng tự động.

## 5. Manifest: Main-Class khác Start-Class

Một Boot executable JAR với layout mặc định thường có phần manifest tương tự:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.boot.BootJarLabApplication
Spring-Boot-Version: 3.5.0
~~~

Đây là **trích đoạn minh họa**; Maven Archiver có thể thêm attributes khác, thứ tự dòng không cố định. `Spring-Boot-Version` phụ thuộc phiên bản đang build.

- **`Main-Class`:** lớp **JVM trực tiếp gọi** khi chạy `java -jar`. Với Boot executable JAR, đó là **Boot launcher**, không phải nhất thiết là class viết bởi lập trình viên.
- **`Start-Class`:** lớp `main()` của ứng dụng Spring Boot; Boot launcher gọi nó sau khi thiết lập classpath thích hợp.
- **`Spring-Boot-Version`:** metadata Boot version khi plugin tạo ra.
- **`Class-Path`:** không phải danh sách cần thiết để trỏ tới các nested `BOOT-INF/lib/*.jar` trong Boot layout thông thường; Boot loader suy ra classpath của chúng.

Với một **plain executable JAR tự cấu hình**, manifest có thể là:

~~~text
Manifest-Version: 1.0
Main-Class: demo.boot.BootJarLabApplication
~~~

Nhưng điều này **không đóng gói Spring dependencies**. Nếu class chính khởi tạo Spring Framework mà các thư viện không ở runtime classpath, chương trình vẫn có thể lỗi `NoClassDefFoundError` dù `Main-Class` đúng.

## 6. Quy trình Maven: jar:jar trước, spring-boot:repackage sau

Một Spring Boot project có packaging `jar` thường đi qua:

~~~text
generate-sources / process-resources / compile
                       |
                       v
                     test
                       |
                       v
                  package phase
                       |
                       +-- maven-jar-plugin:jar
                       |       |
                       |       +-- tạo archive JAR thường
                       |
                       +-- spring-boot-maven-plugin:repackage
                               |
                               +-- bố trí lại classes/resources
                               +-- đưa dependencies vào BOOT-INF/lib
                               +-- thêm Boot Loader
                               +-- điều chỉnh manifest
                               +-- tạo executable JAR
                       |
                       v
                verify / install / deploy
~~~

Maven JAR Plugin phải tạo **source archive** trước; Spring Boot `repackage` không phải compiler hoặc một cách thay thế `jar:jar` trong lifecycle. Tài liệu plugin nhấn mạnh `repackage` **không nhằm gọi riêng từ command line trên một thư mục chưa package**.

Trong project dùng `spring-boot-starter-parent`, execution `repackage` đã được parent cấu hình. Bạn vẫn khai báo plugin ở `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
~~~

Nếu **không dùng** `spring-boot-starter-parent`, thường phải cấu hình goal execution rõ ràng (và version/plugin management phù hợp):

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>repackage</id>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đoạn này chỉ mô tả cấu hình plugin, **không phải một POM độc lập**. Với starter-parent, đừng cấu hình trùng thêm một execution mới nếu bản thân parent đã có execution `repackage`: có thể khiến repackage goal chạy thừa hoặc tạo cấu hình khó hiểu.

### Lệnh nào đúng?

~~~bash
mvn -B -ntp clean package
~~~

chạy toàn lifecycle đến `package`, bao gồm việc tạo JAR và repackage nếu execution Boot active.

~~~bash
mvn -B -ntp package spring-boot:repackage
~~~

là cách gọi thủ công hợp lệ khi bạn chủ đích muốn gọi goal sau khi `package`. **Nếu POM đã tự bind repackage vào `package`**, câu lệnh này có thể dẫn tới thêm một lần repackage không cần thiết; không dùng như lệnh build mặc định của lab.

Không chạy `mvn spring-boot:repackage` từ project hoàn toàn sạch rồi coi nó tương đương `mvn package`; goal có thể không tìm được source archive cần xử lý.

## 7. Bài lab Java 17: một project, hai kiểu JAR

Ta dùng **cùng một `pom.xml` và code** để tạo:

- Plain JAR: tạm bỏ qua bước Spring Boot repackage bằng đúng user property của plugin.
- Boot executable JAR: bật lại repackage theo cấu hình mặc định.
- Cả hai được đọc bằng `jar tf` và một chương trình Java 17 `JarLayoutProbe.java` độc lập dùng JDK `JarFile`.
- Cuối cùng chạy Boot executable JAR bằng `java -jar` để chứng minh Boot loader hoạt động.

### 7.1. Cấu trúc dự án

~~~text
boot-jar-layout-lab/
├── pom.xml
├── tools/
│   └── JarLayoutProbe.java
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/boot/BootJarLabApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── config/build-label.txt
    └── test/
        ├── java/demo/boot/BootJarLabApplicationTest.java
        └── resources/fixtures/test-only.txt
~~~

`tools/JarLayoutProbe.java` chỉ phục vụ việc **kiểm tra archive bên ngoài**. Nó **không** nằm dưới `src/main/java`, nên Maven không đóng nó vào JAR ứng dụng. Có thể chạy nó bằng Java 17 source-file mode mà không cần cài thêm thư viện.

### 7.2. POM đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo.boot</groupId>
    <artifactId>boot-jar-layout-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.boot.BootJarLabApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao POM này đủ cho lab?**

- `spring-boot-starter-parent:3.5.0` quản lý dependency/plugin versions và cấu hình phổ biến, gồm execution của `spring-boot:repackage`.
- `spring-boot-starter` cung cấp Spring Boot core, auto-configuration, logging và các thư viện nền; không thêm web server nếu không khai báo web starter.
- `spring-boot-starter-test` cung cấp JUnit/test dependencies cần cho hai test trong demo.
- `<java.version>17</java.version>` chọn Java 17 theo cấu hình parent. Cần dùng JDK tương thích thật trên máy/CI.
- `<mainClass>` chỉ định main class tường minh, tránh chọn nhầm khi có nhiều class `main()`.
- Với parent này, chỉ cần **khai báo** `spring-boot-maven-plugin`; không phải viết lại `<executions>`.
- `project.build.outputTimestamp` hỗ trợ reproducible archive timestamps khi các plugin liên quan sử dụng giá trị ấy, nhưng không tự bảo đảm nội dung JAR bất biến giữa hai build khác input.

Đây là một **POM hoàn chỉnh**, khác với các đoạn XML chỉ minh họa ở các mục sau.

### 7.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
demo.label=boot-layout-lab
~~~

Ứng dụng demo chạy như **non-web Spring Boot application**, không mở HTTP port. Ta tắt banner và hạn chế startup logs để dễ quan sát các dòng `System.out.println` từ `CommandLineRunner`. Output log ngoài ý muốn còn có thể phụ thuộc phiên bản/môi trường; không xem việc in đúng hai dòng là quy tắc tuyệt đối của mọi Spring Boot application.

### 7.4. `src/main/resources/config/build-label.txt`

~~~text
resource-from-jar
~~~

Resource được Maven copy vào main classpath. Khi còn là **plain JAR**, entry thường là:

~~~text
config/build-label.txt
~~~

Khi đã **repackage**, entry trở thành:

~~~text
BOOT-INF/classes/config/build-label.txt
~~~

Dù đường dẫn entry vật lý khác nhau, chương trình vẫn dùng logical classpath resource path:

~~~text
/config/build-label.txt
~~~

vì Boot Loader ánh xạ `BOOT-INF/classes` thành ứng dụng classpath root.

### 7.5. `src/test/resources/fixtures/test-only.txt`

~~~text
fixture-only
~~~

Đây là **test fixture**. Nó xuất hiện trong `target/test-classes` cho JUnit, không được package vào Boot executable JAR như main resource.

### 7.6. `src/main/java/demo/boot/BootJarLabApplication.java`

~~~java
package demo.boot;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootJarLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootJarLabApplication.class, args);
    }

    @Bean
    CommandLineRunner showPackaging(
            @Value("${demo.label}") String label) {
        return args -> {
            String marker;

            try (InputStream input =
                    BootJarLabApplication.class.getResourceAsStream(
                            "/config/build-label.txt")) {
                if (input == null) {
                    throw new IllegalStateException(
                            "Missing config/build-label.txt");
                }
                marker = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                ).strip();
            }

            System.out.println("label=" + label);
            System.out.println("marker=" + marker);
        };
    }
}
~~~

**Giải thích code:**

- `@SpringBootApplication` bật cấu hình Spring Boot theo convention.
- `SpringApplication.run(...)` khởi chạy Spring application context.
- `CommandLineRunner` chạy khi context đã được khởi tạo.
- `@Value("${demo.label}")` lấy property từ `application.properties`.
- `getResourceAsStream("/config/build-label.txt")` đọc resource **từ classpath**, không giả định source tree tồn tại trên máy deploy.
- Code kiểm tra resource null và thất bại rõ ràng thay vì ngầm dùng file không tồn tại.
- `System.out.println` in hai dòng thuộc **ứng dụng**, không phải danh sách đầy đủ log do Spring/Maven/JVM có thể sinh.

Hai dòng **do code trong CommandLineRunner in ra** khi resource đúng:

~~~text
label=boot-layout-lab
marker=resource-from-jar
~~~

Code này **không chạy khi gọi Maven compile**. Nó chạy khi khởi động ứng dụng bằng Boot launcher, ví dụ `java -jar` trên artifact đã repackage.

### 7.7. `src/test/java/demo/boot/BootJarLabApplicationTest.java`

~~~java
package demo.boot;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class BootJarLabApplicationTest {

    @Test
    void mainResourceIsPresent() throws Exception {
        try (InputStream input =
                BootJarLabApplication.class.getResourceAsStream(
                        "/config/build-label.txt")) {
            assertNotNull(input);
            String value = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
            assertEquals("resource-from-jar", value);
        }
    }

    @Test
    void testFixtureIsPresentInTests() throws Exception {
        try (InputStream input =
                BootJarLabApplicationTest.class.getResourceAsStream(
                        "/fixtures/test-only.txt")) {
            assertNotNull(input);
            String value = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();
            assertEquals("fixture-only", value);
        }
    }
}
~~~

Test này không khởi động Spring context; nó chỉ kiểm tra classpath/resources ở lúc Surefire chạy. **Test PASS không chứng minh Boot executable JAR có layout đúng**, vì test classpath có thể là `target/classes` và `target/test-classes` chứ chưa phải archive sau repackage.

## 8. Tạo JAR thường từ chính project đó

Ta dùng **user property thực tế của Spring Boot Maven Plugin** để tạm skip bước repackage:

~~~bash
mvn -B -ntp clean package -Dspring-boot.repackage.skip=true
~~~

Với POM ở mục 7, goal `spring-boot:repackage` có cấu hình được nhận nhưng bị skip; Maven vẫn thực hiện normal JAR packaging. Khi thành công, file chính thường là:

~~~text
target/boot-jar-layout-lab-1.0.0.jar
~~~

Để xem entries:

~~~bash
jar tf target/boot-jar-layout-lab-1.0.0.jar
~~~

Các entry cần chú ý trong **plain JAR**:

~~~text
META-INF/MANIFEST.MF
demo/boot/BootJarLabApplication.class
application.properties
config/build-label.txt
...
~~~

Dấu `...` nghĩa là còn metadata/entries khác tùy plugin. Bạn không nên thấy nhóm nested dependencies `BOOT-INF/lib/*.jar` hay application class ở `BOOT-INF/classes/...` trong bản plain từ POM này.

**Tuyệt đối không kết luận:** Vì file có `BootJarLabApplication.class` ở root nên `java -jar` sẽ hoạt động. Với plain JAR, manifest có thể không đặt `Main-Class`; ngay cả nếu đặt Main-Class trực tiếp, runtime vẫn cần Spring dependencies **ngoài JAR**, hoặc phải có một packaging strategy khác.

Có thể dùng một tập JARs bên ngoài và classpath thích hợp để chạy plain JAR, nhưng trong bài này ta **cố ý không biến plain JAR thành distribution hoàn chỉnh**. Mục tiêu là so sánh cấu trúc đầu ra.

## 9. Tạo Spring Boot executable JAR từ cùng code

Chạy lại từ trạng thái sạch, **không truyền skip flag**:

~~~bash
mvn -B -ntp clean package
~~~

Vì POM dùng starter-parent và khai báo Spring Boot plugin:

1. Maven compile và chạy hai JUnit tests.
2. Maven JAR Plugin tạo JAR thông thường tại phase `package`.
3. Spring Boot Maven Plugin chạy `repackage`.
4. Archive cuối `target/boot-jar-layout-lab-1.0.0.jar` trở thành **Boot executable JAR**.
5. Plugin theo cấu hình mặc định thường giữ bản JAR trước repackage với đuôi `.jar.original`, chẳng hạn `target/boot-jar-layout-lab-1.0.0.jar.original`.

Kiểm tra:

~~~bash
jar tf target/boot-jar-layout-lab-1.0.0.jar
~~~

Những entry quan trọng:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/demo/boot/BootJarLabApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/config/build-label.txt
BOOT-INF/lib/spring-boot-...jar
BOOT-INF/lib/spring-context-...jar
...
~~~

Các tên JAR thư viện là dạng viết tắt; version thực tế phụ thuộc dependency management của Spring Boot 3.5.0. File `BOOT-INF/classes/fixtures/test-only.txt` **không nên có**, vì fixture nằm trong test source set.

### So nguyên bản .jar.original khi có

Nếu plugin đã tạo bản trước repackage:

~~~bash
jar tf target/boot-jar-layout-lab-1.0.0.jar.original
~~~

Công cụ `jar tf` vẫn đọc file vì **định dạng bên trong là JAR/ZIP** dù hậu tố tên file là `.original`. Bản này thường có class dưới:

~~~text
demo/boot/BootJarLabApplication.class
~~~

nhưng không có nested dependency libraries dưới `BOOT-INF/lib`.

**Không phân phối nhầm `.jar.original` thay cho Boot executable JAR** nếu dịch vụ deploy mong đợi chạy bằng `java -jar` không có external classpath.

## 10. Chạy Boot JAR bằng java -jar

~~~bash
java -jar target/boot-jar-layout-lab-1.0.0.jar
~~~

Với code trên, chương trình in các dòng ứng dụng:

~~~text
label=boot-layout-lab
marker=resource-from-jar
~~~

Đây là **hai dòng do CommandLineRunner trực tiếp in**. Các dòng log khác (nếu có) phụ thuộc logging, JVM và môi trường; không khẳng định toàn bộ console output nhất thiết chỉ có hai dòng.

Vì cấu hình `spring.main.web-application-type=none`, demo không dựng HTTP server/port. Sau khi runner hoàn thành và không có non-daemon background work giữ JVM, process kết thúc bình thường.

**Quan trọng:** Nếu gõ:

~~~bash
java -cp target/boot-jar-layout-lab-1.0.0.jar demo.boot.BootJarLabApplication
~~~

trên Boot executable JAR mặc định, Java classpath loader tiêu chuẩn **không tự coi `BOOT-INF/classes` là classpath root**; lệnh có thể báo không tìm thấy main class. Đây là **hành vi do layout**, không nhất thiết là lỗi do Spring Boot Maven Plugin đóng gói thiếu class.

Dùng `java -jar` để kích hoạt Boot launcher, hoặc nếu project muốn chạy class trực tiếp bằng Java classpath thông thường thì phải sử dụng **plain JAR với external dependencies** đúng cách.

## 11. Kiểm tra manifest thật, không chỉ dựa vào tên JAR

Một cách portable là dùng `jar --extract` trong thư mục kiểm tra riêng; ví dụ:

~~~bash
mkdir inspect-boot
cd inspect-boot
jar --extract --file ../target/boot-jar-layout-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Sau đó đọc `META-INF/MANIFEST.MF` bằng trình soạn thảo text hoặc lệnh của hệ điều hành. Bạn có thể thấy:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.boot.BootJarLabApplication
~~~

Những attribute này là **đặc trưng của Boot executable JAR** với layout JAR chuẩn. Trong bài lab, Spring Boot plugin **quản lý** `Main-Class`/`Start-Class` của JAR đã repackage. Nếu cần thay app main class, cấu hình Spring Boot plugin `<mainClass>` thay vì chỉ cố sửa thuộc tính `Main-Class` trong Maven JAR Plugin.

**Lưu ý:** Với một archive đang dùng launcher kiểu khác (WAR/ZIP/PropertiesLauncher), `Main-Class` có thể khác. Không hard-code tên `JarLauncher` cho mọi Spring Boot output bất kể layout.

## 12. Công cụ Java 17 tự động so layout: JarLayoutProbe.java

Bạn có thể kiểm tra JAR bằng một chương trình Java **độc lập, không dùng Spring**, chỉ cần JDK 17. Tạo file `tools/JarLayoutProbe.java`:

~~~java
import java.nio.file.Path;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class JarLayoutProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: JarLayoutProbe <path-to-jar>");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile())) {
            boolean rootClass = jar.getJarEntry(
                    "demo/boot/BootJarLabApplication.class") != null;

            boolean bootClass = jar.getJarEntry(
                    "BOOT-INF/classes/demo/boot/BootJarLabApplication.class") != null;

            boolean bootResource = jar.getJarEntry(
                    "BOOT-INF/classes/config/build-label.txt") != null;

            boolean nestedLib = jar.stream().anyMatch(entry ->
                    entry.getName().startsWith("BOOT-INF/lib/")
                    && entry.getName().endsWith(".jar"));

            Manifest manifest = jar.getManifest();
            String main = manifest == null ? null
                    : manifest.getMainAttributes().getValue("Main-Class");
            String start = manifest == null ? null
                    : manifest.getMainAttributes().getValue("Start-Class");

            System.out.println("root-class=" + rootClass);
            System.out.println("boot-class=" + bootClass);
            System.out.println("boot-resource=" + bootResource);
            System.out.println("nested-lib=" + nestedLib);
            System.out.println("manifest-main=" + main);
            System.out.println("manifest-start=" + start);
        }
    }
}
~~~

Ưu điểm:

- `java.util.jar.JarFile` đọc trực tiếp archive entries.
- Không cần extract JAR ra disk.
- `getJarEntry` phân biệt chính xác tên entry và chữ hoa/thường.
- `JarFile.stream()` kiểm tra có ít nhất một nested library JAR.
- `Manifest` đọc attributes ở dạng có cấu trúc, tránh parse bằng substring.
- Chương trình dùng Java 17 standard library; **không phụ thuộc Spring** nên có thể inspect cả plain JAR lẫn Boot executable JAR.

### 12.1. Chạy trên plain JAR

Sau lệnh build plain ở mục 8:

~~~bash
java tools/JarLayoutProbe.java target/boot-jar-layout-lab-1.0.0.jar
~~~

Java 17 có **source-file mode** nên không bắt buộc biên dịch thủ công bằng `javac` cho file đơn lẻ. Các giá trị cấu trúc dự kiến:

~~~text
root-class=true
boot-class=false
boot-resource=false
nested-lib=false
~~~

Các giá trị `manifest-main` và `manifest-start` có thể là `null` hoặc giá trị được plugin/manifest config ghi, tùy cấu hình JAR thường; **đừng dựa vào các giá trị này để phân loại layout duy nhất**.

### 12.2. Chạy trên Boot executable JAR

Sau lệnh build Boot ở mục 9:

~~~bash
java tools/JarLayoutProbe.java target/boot-jar-layout-lab-1.0.0.jar
~~~

Dữ liệu dự kiến:

~~~text
root-class=false
boot-class=true
boot-resource=true
nested-lib=true
manifest-main=org.springframework.boot.loader.launch.JarLauncher
manifest-start=demo.boot.BootJarLabApplication
~~~

Đây là những dòng **do JarLayoutProbe in**, tương ứng cách đóng gói Spring Boot 3.5.0 mặc định trong lab. Nếu ứng dụng được repackage với custom layout/classifier hoặc plugin thay đổi behavior, output có thể khác và cần đối chiếu tài liệu đúng version.

### 12.3. Muốn dùng javac riêng?

Có thể biên dịch tool thành class file độc lập:

~~~bash
javac -d tools tools/JarLayoutProbe.java
java -cp tools JarLayoutProbe target/boot-jar-layout-lab-1.0.0.jar
~~~

Lệnh `javac` trên đặt `JarLayoutProbe.class` trong thư mục `tools`, không thuộc Maven main source root nên không làm thay đổi nội dung JAR nếu bạn không cấu hình Maven quét thư mục ấy.

Không chạy lệnh trên từ một working directory khác mà không điều chỉnh relative paths. Nếu dùng Windows PowerShell, đường dẫn `/` trong tên file Java vẫn được Windows Java tools chấp nhận trong ngữ cảnh phù hợp.

## 13. Vì sao Spring Boot JAR không nên dùng trực tiếp như library dependency?

Một project Java khác khai báo dependency:

~~~xml
<dependency>
    <groupId>demo.boot</groupId>
    <artifactId>boot-jar-layout-lab</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Nếu Maven artifact mà nó nhận là **Boot executable JAR mặc định**, application class `demo.boot.BootJarLabApplication` nằm dưới:

~~~text
BOOT-INF/classes/demo/boot/BootJarLabApplication.class
~~~

thay vì:

~~~text
demo/boot/BootJarLabApplication.class
~~~

Java compiler/class loader trong project phụ thuộc thường **không** coi `BOOT-INF/classes` là classpath root khi chỉ thêm JAR ấy như dependency thông thường. Vì vậy Spring Boot khuyến nghị tách **library/shared code** thành một module plain JAR riêng, còn executable application ở module khác.

Giải pháp thiết kế phổ biến:

~~~text
multi-module/
├── pom.xml
├── business-api/            plain JAR, dùng làm dependency
│   └── pom.xml
└── service-app/             Boot executable JAR
    └── pom.xml
~~~

`service-app` phụ thuộc vào `business-api`. Phần thư viện có API để dùng lại không bị nhét vào executable archive rồi đem tái sử dụng như một library thông thường.

## 14. Muốn giữ cả plain JAR và Boot JAR: dùng classifier

Nếu một module buộc phải tạo cả hai artifact, Spring Boot Maven Plugin hỗ trợ `classifier`. Chẳng hạn, với POM dùng `spring-boot-starter-parent`, trong plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.boot.BootJarLabApplication</mainClass>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

**Đây là cấu hình thay thế đoạn plugin trong POM demo**, không thêm một plugin mới trùng vào danh sách. Khi build đúng:

~~~text
target/boot-jar-layout-lab-1.0.0.jar       plain JAR
target/boot-jar-layout-lab-1.0.0-exec.jar  Spring Boot executable JAR
~~~

Phần classifier `exec` phân biệt hai loại artifact. Với mặc định attach phù hợp, artifact có classifier được Maven cài đặt/deploy song song với main artifact.

Chạy:

~~~bash
mvn -B -ntp clean package
java -jar target/boot-jar-layout-lab-1.0.0-exec.jar
~~~

Và nếu muốn dùng làm dependency, các module khác thường khai báo plain main artifact (không classifier) thay vì executable artifact.

**Lưu ý kỹ thuật:** Spring Boot Maven Plugin có cách xử lý classifier khi có sẵn một attached archive cùng classifier. Đừng chọn classifier trùng với những artifacts khác được plugin khác sinh ra mà chưa kiểm tra interaction. Trong project chỉ cần một application executable, mặc định không classifier thường đơn giản hơn.

## 15. .jar.original không phải lựa chọn giống classifier

Hai khái niệm khác nhau:

- **`.jar.original`**: Spring Boot plugin có thể đổi tên file JAR gốc trước khi repackage để giữ bản trên filesystem khi Boot JAR thay thế main artifact. Nó **không tự trở thành một Maven artifact classifier** có thể tham chiếu như `groupId:artifactId:jar:original:version`.
- **Classifier `exec`**: tách hai artifact có Maven coordinates rõ ràng, cho phép quản lý dependency/attach/install/deploy theo chính sách.

Với dự án có nhu cầu chia sẻ code như library, classifier hoặc module riêng có thể cần thiết; không nên bảo downstream services “cứ tự lấy file `.jar.original` từ target của một build khác” để làm dependency.

Khi pipeline upload artifact, phải xác nhận **file nào** được dùng: `*-exec.jar`, `*.jar` hay `*.jar.original`. Một script chọn file bằng wildcard `target/*.jar*` có thể vô tình chọn nhầm.

## 16. Những lệnh dễ gây nhầm lẫn

| Lệnh | Ý nghĩa | Điều dễ hiểu nhầm |
| --- | --- | --- |
| `mvn package` | Chạy lifecycle đến package, bao gồm repackage nếu active | Không phải lúc nào cũng chỉ tạo plain JAR |
| `mvn jar:jar` | Gọi trực tiếp Maven JAR Plugin goal | Không tự thực hiện toàn bộ lifecycle trước nó |
| `mvn spring-boot:repackage` | Gọi trực tiếp repackage goal | Cần source JAR đã được tạo; không phải compiler |
| `mvn spring-boot:run` | Chạy ứng dụng Spring Boot từ project trong môi trường Maven | Không chứng minh executable JAR đã đóng gói đúng |
| `java -jar target/app.jar` | Chạy theo manifest launcher của archive | Phụ thuộc artifact chính xác đang dùng |
| `java -cp app.jar my.app.Main` | Chạy main class theo classpath loader tiêu chuẩn | Có thể không tìm được class trong `BOOT-INF/classes` |
| `jar tf app.jar` | Liệt kê archive entries | Không tự khởi động ứng dụng |
| `java tools/JarLayoutProbe.java app.jar` | Chạy Java source-file tool để inspect JAR | Không thay đổi artifact, không phải Spring Boot application |

Đặc biệt, `spring-boot:run` có thể thành công trong IDE/Maven dev loop vì các classes và dependencies có sẵn ngoài archive. **Nó không thay thế phép thử `java -jar` trên executable artifact thực tế**.

## 17. Vì sao không chỉ dùng Maven Shade Plugin?

Maven Shade Plugin và Spring Boot repackage đều có thể tạo distribution “một file JAR”, nhưng cách đóng gói **khác nhau**:

### Shaded/uber JAR

Một shaded JAR có thể gộp class files/resources của nhiều dependencies **vào cùng archive root**:

~~~text
shaded-app.jar
├── demo/app/Main.class
├── org/apache/commons/...
├── com/fasterxml/jackson/...
├── META-INF/MANIFEST.MF
└── ...
~~~

Tùy cấu hình Shade, có thể relocate packages, filter entries và merge service resources. Khi nhiều dependency chứa cùng path, phải chọn cách xử lý collisions/transformers phù hợp.

### Spring Boot nested-JAR executable JAR

~~~text
boot-app.jar
├── BOOT-INF/classes/demo/app/Main.class
├── BOOT-INF/lib/library-a.jar
├── BOOT-INF/lib/library-b.jar
├── org/springframework/boot/loader/...
└── META-INF/MANIFEST.MF
~~~

Mỗi dependency được giữ như **archive con** trong outer JAR, thay vì nhất thiết giải nén rồi trộn class files vào một root chung.

**Ưu/nhược điểm thực tế:**

- Nested layout giữ ranh giới dependency JAR rõ ràng và hỗ trợ Boot loader.
- Shading có thể thích hợp cho thư viện/CLI hoặc các mục tiêu relocation cụ thể.
- Shading có rủi ro xử lý không đầy đủ duplicate classes/resources và `META-INF/services` nếu cấu hình thiếu.
- Boot nested JARs cần launcher và có các yêu cầu riêng về ZIP entry compression/class loader.
- Không dùng cả Shade và Boot repackage chỉ theo thói quen; nếu phối hợp, cần xác định thứ tự và artifact nào là source/target của mỗi plugin.

## 18. Nested libraries không phải được extract toàn bộ mỗi lần chạy

Spring Boot Loader hỗ trợ tìm kiếm và đọc nội dung nested JARs bằng cơ chế chuyên dụng. Không đúng khi nghĩ `java -jar boot-app.jar` luôn phải extract **toàn bộ `BOOT-INF/lib`** ra filesystem trước khi JVM chạy được.

Trong Boot Loader có cơ chế `NestedJarFile`, ánh xạ ZIP entries tới vị trí dữ liệu trong outer archive để truy cập phù hợp. Một số thư viện đặc biệt cần có bản unpack riêng vì tự dùng filesystem/JAR assumptions; plugin có option `requiresUnpack` dành cho các trường hợp ấy.

### Zip compression restriction

Trong định dạng Boot nested JAR, entry **bọc file dependency JAR bên trong outer JAR** cần dùng ZIP method `STORED` để Boot Loader có thể seek hợp lý tới nội dung thư viện con. Bên trong chính dependency JAR, dữ liệu lại có thể được nén; vì vậy không nên diễn giải “STORED nested JAR” thành “toàn bộ bytecode trong mọi JAR đều không nén”.

**Đừng tự rezip executable JAR bằng công cụ bất kỳ mà không hiểu quy tắc compression của nested dependencies.** Việc thao tác ZIP không giữ đúng format có thể tạo archive vẫn liệt kê được bằng `jar tf` nhưng Boot loader không chạy được.

## 19. classpath.idx và layers.idx

Nhiều Boot executable JARs có thêm những file index:

~~~text
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
~~~

- **`classpath.idx`** mô tả thứ tự các nested dependency JARs trên classpath khi Boot launcher dùng archive; thường được build plugin sinh. Nó không phải Maven `pom.xml` hoặc danh sách Java `Class-Path` manifest.
- **`layers.idx`** mô tả cách chia nội dung archive thành các layer logic phục vụ container image caching/packaging.
- Layering **không biến JAR thành Docker image**. Nó chỉ cung cấp metadata để công cụ xây image có thể tách các phần và cache hiệu quả.
- Index files không bắt buộc có trong mọi bản Boot JAR/custom layout. Không dùng sự thiếu một file index làm bằng chứng duy nhất rằng JAR không phải Boot executable.

Các layer mặc định thường gồm:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Các tên trên là **nhãn layer**, không nhất thiết là bốn thư mục xuất hiện trực tiếp tại gốc outer JAR.

Nếu bạn sửa duy nhất mã ứng dụng, container layer chứa dependencies có thể tái sử dụng cache. Nhưng điều này tùy Dockerfile/buildpacks và cách tạo image; chỉ có `layers.idx` không tự bảo đảm image nhỏ hoặc build nhanh.

## 20. JAR và WAR thực thi của Spring Boot không có cùng layout

Dù nhóm chủ đề là **WAR và Spring Boot**, bài này tập trung vào so sánh JAR thường với **Boot executable JAR**. Tuy nhiên cần nhận ra sự khác biệt để tránh kiểm tra sai artifact WAR.

Một Boot executable WAR thường có:

~~~text
app.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── WEB-INF/
    ├── classes/demo/app/Main.class
    ├── lib/dependency-a.jar
    └── lib-provided/servlet-container-dependency.jar
~~~

Với WAR:

- Application classes ở `WEB-INF/classes`.
- Dependencies thường ở `WEB-INF/lib`; dependencies được đánh dấu `provided` phù hợp có thể ở `WEB-INF/lib-provided` để tránh xung đột khi deploy vào servlet container truyền thống.
- Boot launcher khi chạy WAR theo kiểu executable thường là `WarLauncher`.
- WAR còn có mục đích triển khai vào servlet container bên ngoài, với các yêu cầu cấu hình khác plain executable JAR.

**Không** lấy policy “phải có `BOOT-INF/classes` và `BOOT-INF/lib`” áp vào WAR mà không kiểm tra packaging. Đây là hai kiểu layout khác nhau.

## 21. Cấu hình layout khác: JAR, WAR, ZIP, NONE

Spring Boot Maven Plugin có property `layout` cho repackage. Những lựa chọn thường được tài liệu mô tả:

- `JAR`: layout executable JAR thông thường với `JarLauncher`.
- `WAR`: executable WAR layout và `WarLauncher`.
- `ZIP` (alias `DIR`): gần kiểu JAR nhưng dùng `PropertiesLauncher` và có thể tùy chỉnh loader path.
- `NONE`: đóng dependency theo cấu trúc nested mà **không bao gồm bootstrap launcher**, do đó **không tự là executable Boot JAR**.

Ví dụ đoạn plugin configuration minh họa:

~~~xml
<configuration>
    <layout>JAR</layout>
    <mainClass>demo.boot.BootJarLabApplication</mainClass>
</configuration>
~~~

Đây là đoạn XML cấu hình con, không phải POM độc lập. Trong project demo dùng packaging `jar`, layout mặc định đã phù hợp; **không cần đặt layout thủ công** để chỉ muốn chạy `java -jar`.

Nếu cần customize Boot loader/classpath, hãy đọc tài liệu của **Spring Boot Maven Plugin cùng version thực tế**, không lấy tham số của Spring Boot 2.x rồi áp vào 3.x/4.x.

## 22. Tại sao repackage có thể bị skip ngoài ý muốn?

Lệnh lab:

~~~bash
mvn -B -ntp clean package -Dspring-boot.repackage.skip=true
~~~

là **skip có chủ đích** để tạo plain JAR. Nhưng nếu flag này xuất hiện vô tình trong CI, release artifact có thể trở thành plain JAR và không thể khởi chạy theo cách production mong đợi.

Những nguyên nhân khác:

- Chưa khai báo `spring-boot-maven-plugin` trong `<build><plugins>` dù tưởng parent tự chạy tất cả plugin.
- Không dùng `spring-boot-starter-parent` và cũng chưa khai báo execution `repackage`.
- Có profile ghi đè `skip` hoặc execution không active.
- Dùng `mvn jar:jar` trực tiếp thay vì `mvn package`.
- Build mới chỉ chạy tới `test`, chưa tới `package`.
- Một plugin khác chạy sau repackage và thay artifact thành plain JAR hoặc làm hỏng layout.
- CI chọn nhầm `*.jar.original` hay artifact không classifier thay vì `*-exec.jar`.
- Module có packaging `pom` nhưng script lại chờ file JAR.
- Lệnh release đang lấy file JAR từ một build cũ trong `target`.

Khi gặp lỗi, **đừng đoán từ tên artifact**. Dùng `jar tf`, đọc manifest, xem Maven execution log và chạy từ `clean package` để có bằng chứng.

## 23. Đọc Maven build log để xác nhận đúng thứ tự goal

Chạy:

~~~bash
mvn -B -ntp clean package
~~~

Tìm những goal/ID có dạng tương tự:

~~~text
... compiler:...:compile (default-compile) ...
... surefire:...:test (default-test) ...
... jar:...:jar (default-jar) ...
... spring-boot:3.5.0:repackage (repackage) ...
BUILD SUCCESS
~~~

Đây là **trích đoạn minh họa**, không phải transcript thực tế của một lần chạy. Phiên bản Compiler/Surefire/JAR plugins được parent quản lý; format và log chi tiết có thể thay đổi.

Nếu chỉ có `jar:jar` mà không có `spring-boot:repackage` hoạt động, hãy xem POM, active Maven profiles và `spring-boot.repackage.skip`.

Có thể dùng:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

để xem model hiệu lực, gồm những plugin executions được kế thừa. Nhưng **effective POM chỉ chứng minh cấu hình**, không tự chứng minh goal đã chạy; cần đối chiếu log và archive entries.

## 24. Phân biệt spring-boot:run với java -jar

Hai cách chạy phổ biến:

~~~bash
mvn spring-boot:run
java -jar target/boot-jar-layout-lab-1.0.0.jar
~~~

- `spring-boot:run` thường sử dụng output classes và dependency classpath trong quá trình phát triển. Nó không nhất thiết chạy JAR đã repackage.
- `java -jar` chạy **artifact đóng gói** và đi qua launcher của executable archive.

Nếu `spring-boot:run` thành công nhưng `java -jar` thất bại, có thể lỗi ở packaging/plugin/repackage, thiếu file trong archive, manifest, custom layout hoặc runtime environment. Cần test artifact cuối chứ không chỉ test dev-mode.

Tương tự, unit tests trong `mvn test` có thể PASS vì thấy dependency và resource trên Maven test classpath, nhưng JAR cuối vẫn thiếu file nếu packaging excludes sai.

## 25. Kiểm tra tài nguyên và test fixtures trong hai layout

Trong lab, resource chính:

~~~text
src/main/resources/config/build-label.txt
~~~

sẽ có entry khác nhau:

~~~text
Plain JAR: config/build-label.txt
Boot JAR:  BOOT-INF/classes/config/build-label.txt
~~~

Trong code Java, ứng dụng vẫn dùng:

~~~java
BootJarLabApplication.class.getResourceAsStream(
        "/config/build-label.txt");
~~~

Spring Boot launcher thiết lập classpath để logic resource lookup vẫn dùng tên logical `config/build-label.txt`. **Không cần hard-code `/BOOT-INF/classes/config/build-label.txt` trong ứng dụng.**

Test resource:

~~~text
src/test/resources/fixtures/test-only.txt
~~~

thường ở `target/test-classes/fixtures/test-only.txt`, **không** được đưa vào JAR thực thi cuối. Điều này đúng cho lab; nếu bạn tự cấu hình packaging resources khác, hãy inspect archive để xác nhận thực tế.

Rủi ro bảo mật: resource bị package vào Boot executable JAR có thể chứa token, file cấu hình nội bộ hoặc dữ liệu PII. Không xem việc “file nằm trong `BOOT-INF/classes`” là cơ chế bảo mật; người nhận artifact có thể đọc archive như ZIP.

## 26. Security, licensing và dependencies trong BOOT-INF/lib

Boot executable JAR thường mang nhiều dependency JARs dưới `BOOT-INF/lib`, giúp triển khai thuận tiện. Nhưng “có sẵn thư viện trong một archive” **không đồng nghĩa** mọi dependency đều an toàn hoặc cấp phép phù hợp.

Một quy trình kiểm tra release có thể yêu cầu:

1. Xem dependency graph và plugin management thực sự được resolve.
2. Kiểm tra BOM hoặc Spring Boot dependency management versions.
3. Sinh SBOM phù hợp với quy trình tổ chức.
4. Quét vulnerabilities và license compliance cho nested JAR dependencies.
5. Loại secrets/test fixtures/debug data khỏi artifact.
6. Kiểm tra reproducibility/provenance của artifact.
7. Xác nhận cấu hình native libraries/OS dependencies của runtime môi trường mục tiêu.

Spring Boot repackage thường loại một số development tools theo default plugin policy; nhưng không coi đó là việc loại **mọi** dependency không phù hợp. Nếu cần exclude một dependency cụ thể, đọc options của Boot Maven Plugin thay vì xóa bằng cách tự sửa ZIP sau build.

## 27. Khi cần tạo container image, layers hoạt động thế nào?

Một Boot JAR có `BOOT-INF/layers.idx` có thể hỗ trợ tooling chia thành các phần:

~~~text
dependencies           thư viện release ít thay đổi
spring-boot-loader     lớp bootstrap
snapshot-dependencies  thư viện SNAPSHOT có thể thay đổi nhiều
application            classes và resources của app
~~~

Một workflow container có thể lưu các phần tương đối ổn định thành layer Docker/OCI riêng để cache. Tuy nhiên:

- `layers.idx` không phải Dockerfile.
- Một plain JAR cũng có thể được đưa vào container nếu có startup classpath/distribution phù hợp.
- Boot JAR có thể dùng buildpacks hoặc Dockerfile; layout và startup strategy tùy hệ thống.
- Một container image **không thay thế** việc xác minh chính JAR đã build.
- Nếu dùng Boot tools mode như `java -Djarmode=tools -jar app.jar extract`, phải xem version và options thực tế; công cụ có thể cung cấp chế độ extract/layers khác nhau giữa các phiên bản.

Đừng đóng gói thêm một lần chỉ để có container khi plugin hoặc buildpacks đã tạo được image hợp lệ. Chọn workflow nhất quán và kiểm tra file chạy thực tế.

## 28. Debug lỗi phổ biến: bảng quyết định

| Hiện tượng | Nguyên nhân có khả năng | Cách xác minh |
| --- | --- | --- |
| `java -jar ...` báo `no main manifest attribute` | Plain JAR, repackage bị skip/chưa chạy, hoặc manifest sai | Xem `META-INF/MANIFEST.MF` |
| `Could not find or load main class demo.boot...` khi dùng `-cp boot.jar` | Class app ở `BOOT-INF/classes`, không ở archive root | `jar tf`; dùng `java -jar` |
| `ClassNotFoundException` liên quan Spring | Thiếu runtime dependencies hoặc custom packaging/classpath sai | Kiểm tra `BOOT-INF/lib` và dependency graph |
| `NoClassDefFoundError` với plain JAR | Runtime không cấp JAR dependency ngoài | Chọn startup classpath hoặc Boot distribution |
| `Main-Class` trỏ vào app nhưng archive có BOOT-INF layout | Manifest bị cấu hình sai/thay đổi sau repackage | Kiểm tra Boot plugin manifest management |
| `Start-Class` không đúng | Có nhiều main classes hoặc plugin config sai | Đặt Boot plugin `<mainClass>` tường minh |
| JAR có `BOOT-INF/classes` nhưng không có `BOOT-INF/lib` | Repackage configuration, layout NONE, exclusions hoặc project không có runtime libs | Inspect POM, log và artifact |
| `java -jar` fail nhưng `spring-boot:run` PASS | Dev classpath khác artifact runtime | Build clean và inspect JAR |
| `.jar.original` chạy không được | Đây là bản trước repackage, thường không kèm Boot launcher/deps | Chạy đúng repackaged JAR |
| Một project khác dùng Boot JAR làm dependency báo thiếu class | Application classes nằm dưới BOOT-INF/classes | Dùng plain library JAR/module riêng |
| Executable JAR sai sau khi bị nén lại | Nested ZIP entries không giữ layout/compression yêu cầu | Xem nested JAR restrictions, build lại từ plugin |
| Local được, CI thất bại | Khác JDK/Maven/profiles/artifact name/permissions | `mvn -version` và exact CI command |
| Không thấy `layers.idx` | Layers bị tắt hoặc version/config khác | Không dùng index làm điều kiện duy nhất để phân loại |
| Ứng dụng chạy nhưng resource không tìm thấy | Resource path sai hoặc không được copy | Kiểm tra `BOOT-INF/classes/...` và `getResourceAsStream` |
| Lỗi ký tự tiếng Việt trong properties | Resource encoding hoặc Java properties reader không phù hợp | Kiểm tra bytes/UTF-8/Reader |

**Không quy mọi lỗi `ClassNotFoundException` về packaging**. Có thể còn version mismatch, dependency exclusion, reflection, class loader đặc thù hoặc runtime JDK không phù hợp. Cần đọc root cause và stack trace thật.

## 29. Bài tập thực hành có đáp án

1. **JAR thường do Maven JAR Plugin tạo đặt main class ở đâu?**  
   **Đáp án:** Thường tại gốc archive theo package path, ví dụ `demo/app/Main.class`.

2. **Spring Boot executable JAR đặt main application class ở đâu?**  
   **Đáp án:** `BOOT-INF/classes/demo/app/Main.class` trong layout JAR chuẩn.

3. **Spring Boot đặt nested dependency JARs ở đâu?**  
   **Đáp án:** `BOOT-INF/lib/`.

4. **Tại sao không chỉ nhúng dependency JAR files vào plain JAR rồi chạy?**  
   **Đáp án:** Standard Java loader không tự hiểu nested archive classpath; Boot dùng loader riêng.

5. **Trong Boot manifest, Main-Class thường là ai?**  
   **Đáp án:** Boot launcher, ví dụ `org.springframework.boot.loader.launch.JarLauncher` trên Boot 3.5.

6. **Trong Boot manifest, Start-Class thường là ai?**  
   **Đáp án:** Class của ứng dụng chứa main method.

7. **JAR thường có thể dùng `java -jar` không?**  
   **Đáp án:** Có, nếu có Main-Class phù hợp và mọi runtime dependencies được cung cấp.

8. **Goal Maven nào tạo JAR nền trước repackage?**  
   **Đáp án:** `maven-jar-plugin:jar` tại phase `package` theo JAR lifecycle.

9. **Goal Maven nào biến JAR nền thành Boot executable JAR?**  
   **Đáp án:** `spring-boot:repackage`.

10. **Đang dùng starter-parent và khai báo Boot plugin, có cần khai báo thêm execution repackage mới không?**  
    **Đáp án:** Không; starter-parent đã cấu hình execution đó.

11. **Không dùng starter-parent, cần bổ sung gì?**  
    **Đáp án:** Quản lý version và bind `repackage` goal vào lifecycle bằng execution phù hợp.

12. **Tại sao không nên chạy `spring-boot:repackage` trên project sạch?**  
    **Đáp án:** Goal cần source archive đã được tạo trước bởi package.

13. **Cờ nào trong lab tạm skip repackage?**  
    **Đáp án:** `-Dspring-boot.repackage.skip=true`.

14. **Sau khi repackage không classifier, bản JAR thường được giữ tên gì trên filesystem?**  
    **Đáp án:** Thường là `*.jar.original` theo default plugin behavior.

15. **Có thể dùng `.jar.original` làm Maven dependency classifier tự động không?**  
    **Đáp án:** Không; đây chỉ là bản file gốc được giữ, khác cơ chế classifier.

16. **Muốn tạo plain JAR và executable JAR trong cùng build, chọn gì?**  
    **Đáp án:** Dùng classifier như `exec` hoặc tốt hơn tách library module khi mục đích là chia sẻ code.

17. **Vì sao Boot executable JAR không phù hợp làm dependency trực tiếp?**  
    **Đáp án:** Application classes nằm dưới `BOOT-INF/classes` chứ không ở classpath root thông thường.

18. **Lệnh nào cho biết JAR có `BOOT-INF/lib`?**  
    **Đáp án:** `jar tf file.jar`, hoặc Java `JarFile`.

19. **Đường dẫn resource từ source `config/build-label.txt` thay đổi thế nào khi repackage?**  
    **Đáp án:** Entry chuyển vào `BOOT-INF/classes/config/build-label.txt`, nhưng classpath logical resource path vẫn là `/config/build-label.txt`.

20. **Cách chạy chính thức một Boot executable JAR mặc định?**  
    **Đáp án:** `java -jar app.jar`.

21. **Vì sao `java -cp app.jar ...` có thể lỗi trên Boot JAR?**  
    **Đáp án:** App class không nằm tại JAR root; lệnh không đi qua Boot loader.

22. **`spring-boot:run` có chứng minh executable JAR đã package đúng không?**  
    **Đáp án:** Không; nó chủ yếu phục vụ chạy trực tiếp từ Maven project.

23. **`classpath.idx` nhằm làm gì?**  
    **Đáp án:** Mô tả thứ tự nested JARs trên classpath khi dùng Boot loader theo hình thức phù hợp.

24. **`layers.idx` có biến JAR thành Docker image không?**  
    **Đáp án:** Không; chỉ mô tả metadata các layer để tooling xây image sử dụng.

25. **Một Boot executable WAR có layout nào?**  
    **Đáp án:** Thường `WEB-INF/classes`, `WEB-INF/lib` và có thể `WEB-INF/lib-provided`, khác Boot JAR.

26. **Boot layout NONE có mặc nhiên executable launcher không?**  
    **Đáp án:** Không; layout NONE không bundle launcher như layout JAR.

27. **Một shaded JAR có nhất thiết chứa nested JAR dưới BOOT-INF/lib không?**  
    **Đáp án:** Không; Shade thường hợp nhất classes/resources vào cùng archive.

28. **Vì sao nested dependency JAR entry cần ZIP STORED?**  
    **Đáp án:** Để Boot loader có thể seek tới nội dung nested JAR theo thiết kế của định dạng.

29. **Hai lệnh nào cần dùng để tái hiện khác biệt từ cùng code?**  
    **Đáp án:** `mvn clean package -Dspring-boot.repackage.skip=true` cho plain, và `mvn clean package` cho Boot JAR khi POM như lab.

30. **Dùng Java 17 API nào để kiểm tra JAR entries?**  
    **Đáp án:** `java.util.jar.JarFile` với `getJarEntry` và `getManifest`.

31. **Tại sao không kết luận chỉ dựa vào đuôi `.jar`?**  
    **Đáp án:** Plain JAR, shaded JAR và Boot executable JAR đều có thể dùng cùng đuôi.

32. **Khi CI upload nhầm JAR thường thay Boot JAR, nên kiểm tra gì?**  
    **Đáp án:** Exact artifact filename/classifier, Maven repackage log, manifest và BOOT-INF entries.

33. **Trong lab, test fixture phải nằm ở `BOOT-INF/classes/fixtures/test-only.txt` không?**  
    **Đáp án:** Không; fixture là test resource, không thuộc main artifact.

34. **Boot Loader có luôn extract toàn bộ nested libs khi khởi động?**  
    **Đáp án:** Không; loader có cơ chế truy cập nested entries mà không mặc nhiên giải nén toàn bộ.

35. **Một Boot JAR đã bị rezip có thể fail dù `jar tf` vẫn liệt kê được không?**  
    **Đáp án:** Có; có thể vi phạm yêu cầu ZIP compression/loader layout.

## 30. Checklist review artifact trước khi deploy

- [ ] Xác định rõ artifact cần phát hành là **plain JAR**, Boot executable JAR hay executable WAR.
- [ ] Dùng Maven Wrapper/JDK và plugin versions phù hợp, cố định khi build CI.
- [ ] Chạy `mvn clean package` hoặc `clean verify` với đúng profile, settings và build flags.
- [ ] Kiểm tra `spring-boot:repackage` thực sự chạy và không bị skip ngoài ý muốn.
- [ ] Đối chiếu JAR Plugin tạo archive trước Boot Plugin repackage.
- [ ] Dùng `jar tf` kiểm tra các entries của artifact thực tế.
- [ ] Với Boot JAR: xác nhận `BOOT-INF/classes` có application classes và resources.
- [ ] Với Boot JAR: xác nhận `BOOT-INF/lib` chứa libraries theo dependencies được chọn.
- [ ] Với Boot JAR: xác nhận Boot launcher class tồn tại tại root.
- [ ] Đọc manifest, xác minh `Main-Class` và `Start-Class` theo version/layout.
- [ ] Dùng `java -jar` trên đúng executable artifact, không chỉ `spring-boot:run`.
- [ ] Không dùng Boot repackaged application artifact như một library dependency thông thường.
- [ ] Nếu cần cả hai artifact, cấu hình classifier rõ ràng; tránh upload nhầm `.jar.original`.
- [ ] Kiểm tra runtime resource paths bằng classpath APIs, không hard-code `BOOT-INF/classes` trong code ứng dụng.
- [ ] Không ship test fixtures, secrets hoặc dev-only configuration trong main JAR.
- [ ] Không tự rezip nested JARs khi chưa kiểm soát ZIP compression/layout rules.
- [ ] Nếu dùng layered JAR/container, kiểm tra `layers.idx` và image startup strategy.
- [ ] Nếu dùng executable WAR, áp dụng layout `WEB-INF` thay vì policy Boot JAR.
- [ ] Có báo cáo dependency/security/licensing/provenance cho artifact cuối.
- [ ] Đảm bảo local/CI/production dùng đúng JAR path, classifier, Java runtime và startup command.

## 31. Tài liệu chính thức để tra cứu

- [Spring Boot — Packaging Executable Archives (Maven Plugin)](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): cách `repackage`, `.original`, classifier, manifest và layout.
- [Spring Boot — Create an Executable JAR with Maven](https://docs.spring.io/spring-boot/3.5/how-to/build.html): starter-parent, boot plugin, dependency JAR và classifier.
- [Spring Boot — Executable JAR: Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `BOOT-INF/lib`, lớp loader, `classpath.idx` và `layers.idx`.
- [Spring Boot — Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html): `JarLauncher`, `WarLauncher`, `PropertiesLauncher`, `Main-Class` và `Start-Class`.
- [Spring Boot — NestedJarFile](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/jarfile-class.html): cách đọc nested dependencies.
- [Spring Boot — Executable Jar Restrictions](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html): ZIP STORED và class-loader caveats.
- [Spring Boot — Efficient Deployments](https://docs.spring.io/spring-boot/3.5/reference/packaging/efficient.html): exploded JAR/layers/optimized startup.
- [Apache Maven — Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): đóng gói plain JAR.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase `package`/`verify`.
- [Oracle Java 17 — jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): `jar tf` và archive inspection.
- [Oracle Java 17 — JarFile API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): đọc manifest/entries bằng Java.

**Ghi nhớ:** Sự khác biệt không nằm ở hậu tố `.jar` mà ở **bố cục classpath và cách khởi chạy**. Plain JAR đặt classes/resources ở archive root và thường cần cấp runtime dependencies riêng; Boot executable JAR dùng `BOOT-INF/classes`, nested `BOOT-INF/lib`, Boot loader và cặp manifest `Main-Class`/`Start-Class`. Muốn chắc chắn artifact nào đang được dùng, hãy **inspect chính JAR cuối**, chạy `java -jar` và đối chiếu build log `repackage` thay vì suy đoán từ tên file.
