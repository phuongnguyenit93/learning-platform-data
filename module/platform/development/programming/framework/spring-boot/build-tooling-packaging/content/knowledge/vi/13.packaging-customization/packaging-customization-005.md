# Lựa chọn layout JAR, WAR, ZIP hoặc NONE trong Spring Boot Maven Plugin

## 1. Bài học này giải quyết vấn đề gì?

Một ứng dụng Spring Boot có thể được xây dựng bằng Maven thành nhiều dạng archive khác nhau. Khi đọc `pom.xml`, người học thường bắt gặp `<packaging>jar</packaging>`, `<packaging>war</packaging>` hoặc cấu hình `spring-boot-maven-plugin` có `<layout>JAR</layout>`, `<layout>WAR</layout>`, `<layout>ZIP</layout>`, `<layout>NONE</layout>`. Những tên gần giống nhau dễ dẫn đến một hiểu lầm: **`packaging` và `layout` là cùng một lựa chọn**.

Thực tế, chúng giải quyết hai lớp trách nhiệm:

- **Maven `packaging`** xác định kiểu artifact và lifecycle tạo archive ban đầu (ví dụ JAR hay WAR).
- **Spring Boot Maven Plugin `layout`** quyết định **cách sắp xếp class, dependency và launcher bên trong archive** khi goal `spring-boot:repackage` xử lý artifact.

Vì thế, đổi `layout` không phải cách tổng quát để đổi phần mở rộng file, biến một JAR thành WAR có thể deploy trên Tomcat, hoặc tạo một thư mục `.zip` sẵn có trên filesystem.

Sau bài học, bạn sẽ:

1. Phân biệt `packaging`, `layout`, `classifier`, `finalName` và Spring Boot layers.
2. Chọn giữa `JAR`, `WAR`, `ZIP`/`DIR` và `NONE` dựa trên **cách ứng dụng sẽ được khởi chạy/tiêu thụ**.
3. Hiểu vai trò `JarLauncher`, `WarLauncher`, `PropertiesLauncher` và lý do `NONE` không có bootstrap loader.
4. Viết POM và Java 17+ cho một ứng dụng `JAR`, một biến thể `ZIP`, một ứng dụng `WAR` và một cấu hình `NONE` để so sánh.
5. Kiểm tra archive sau khi repackage bằng `jar tf`, manifest và một tiện ích Java chuẩn `JarFile`.
6. Tránh lỗi chọn sai artifact, sai servlet container, thiếu runtime dependency hoặc tưởng rằng `ZIP` đồng nghĩa một tập tin có đuôi `.zip`.

**Quy ước phiên bản ví dụ:** Java `17`, Spring Boot `3.3.5`, Maven 3.x tương thích. Các giá trị này là một bộ ví dụ có thể tái hiện, không phải cam kết chúng là bản mới nhất. Khi thực hành trên Spring Boot 4.x hoặc Maven/plugin khác, cần kiểm tra tài liệu theo version thực tế, nhất là tên launcher và yêu cầu servlet container.

## 2. Phân biệt năm khái niệm rất dễ nhầm

| Khái niệm | Được cấu hình ở đâu? | Nó thực sự điều khiển gì? |
| --- | --- | --- |
| `packaging` | `<project><packaging>jar/war</packaging>` | Maven lifecycle và **loại archive nguồn** mà plugin đóng gói |
| `layout` | `spring-boot-maven-plugin <configuration>` | Cấu trúc classes, dependencies và bootstrap loader sau `repackage` |
| `mainClass` | Spring Boot Maven Plugin | Main class ứng dụng, thường được ghi vào `Start-Class` của executable archive |
| `finalName` | `<build><finalName>...` | Tên file archive cục bộ, không đổi Maven GAV (`groupId:artifactId:version`) |
| `classifier` | Cấu hình goal `repackage` | Tạo/đính kèm một biến thể archive, ví dụ main artifact và `-exec.jar` |

Một nhóm khái niệm khác cũng cần tách riêng:

- **`layers`** của Spring Boot: metadata và phân vùng lớp phục vụ tối ưu OCI image; **không phải** một giá trị của `layout`.
- **`<executable>true</executable>`** của Spring Boot Maven Plugin: cơ chế thêm launch script ở đầu archive cho kiểu chạy như shell script trên hệ thống phù hợp; **không phải** tương đương `layout=ZIP`.
- **`outputDirectory`** hoặc `project.build.directory`: đường dẫn lưu build output; **không** quyết định loader nào được nhúng.
- **`ZIP`** (layout enum) khác một **file ZIP thông thường**: Java JAR vốn sử dụng ZIP file format; layout `ZIP` của Spring Boot có nghĩa cụ thể liên quan tới `PropertiesLauncher`.
- **`NONE`** không đồng nghĩa `skip repackage`: nó vẫn có thể gom dependencies vào archive nhưng **không nhúng bootstrap loader**; còn `<skip>true</skip>` khiến repackage goal bị bỏ qua.

## 3. Bảng lựa chọn nhanh: JAR, WAR, ZIP/DIR hay NONE?

| Layout | Ý định điển hình | Đường dẫn bên trong | Launcher Spring Boot | `java -jar`? |
| --- | --- | --- | --- | --- |
| `JAR` | Ứng dụng standalone tiêu chuẩn, CLI, web service chạy embedded server | `BOOT-INF/classes`, `BOOT-INF/lib` | `JarLauncher` | Có, khi build cấu hình đúng |
| `WAR` | Executable WAR, có thể kết hợp mục tiêu triển khai external servlet container | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | `WarLauncher` | Có cho executable WAR được tạo đúng |
| `ZIP` | Cần classpath linh hoạt do `PropertiesLauncher` quản lý, ví dụ bổ sung thư viện từ ngoài archive | Gần giống JAR layout, trong đó có `BOOT-INF` | `PropertiesLauncher` | Có, khi build cấu hình đúng |
| `DIR` | Alias của `ZIP` theo tài liệu Spring Boot Maven Plugin | Như `ZIP` | `PropertiesLauncher` | Như `ZIP` |
| `NONE` | Gom dependency và resources để hệ thống khác tiêu thụ/khởi động theo cơ chế riêng | Layout không có Boot bootstrap loader | **Không có Boot launcher** | **Không** phải Boot executable archive mặc định |

Với **đa số ứng dụng Spring Boot standalone**, **giữ layout mặc định** là lựa chọn đơn giản và dễ hỗ trợ nhất: Maven `jar` thường dẫn tới `JAR`, Maven `war` thường dẫn tới `WAR`. Chỉ đổi sang `ZIP` khi thực sự cần tính linh hoạt của launcher; dùng `NONE` khi **chủ động không muốn** Boot bootstrap loader và biết phía tiêu thụ sẽ nạp dependencies như thế nào.

**Lưu ý về `WAR`:** layout chỉ định cấu trúc archive, nhưng để WAR chạy trong **external Tomcat** còn cần đúng servlet API/Jakarta, Spring Boot servlet initialization và dependency scopes. Không thể chỉ thay `layout` từ JAR sang WAR rồi cho rằng archive có thể deploy vào mọi servlet container.

### 3.1. “Executable” ở đây có nghĩa gì?

Một archive Spring Boot **executable** chứa launcher/manifest cần thiết để `java -jar` nạp application classes lẫn nested dependencies mà không phải tạo classpath thủ công. Điều này khác hoàn toàn với một ordinary JAR có mỗi `Main-Class` nhưng thiếu runtime dependencies.

Trong Spring Boot 3.3, với layout phổ biến, manifest của JAR có thể chứa:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

`Main-Class` là bootstrap class được JVM gọi đầu tiên; `Start-Class` là điểm khởi động của ứng dụng. Với `WAR` và `ZIP`, `Main-Class` thay đổi tương ứng với loại launcher. `NONE` không kèm bootstrap loader, nên **đừng mặc nhiên kiểm thử nó bằng `java -jar`** như với JAR/WAR/ZIP.

## 4. Spring Boot repackage làm gì trong Maven?

Với Maven project jar tiêu chuẩn, luồng build thường là:

~~~text
pom.xml + src/main/java + src/main/resources
                    |
                    v
               mvn package
                    |
                    v
            Maven jar:jar / war:war
                    |
                    v
            Archive thông thường
                    |
                    v
     spring-boot-maven-plugin:repackage
                    |
                    v
          Archive theo Boot layout
                    |
                    v
           Inspect + smoke test
~~~

Goal `spring-boot:repackage` hoạt động trên archive **đã được tạo** (JAR hoặc WAR) và đưa application classes, dependencies cùng loader tương ứng vào bố cục theo `layout`. Khi dùng `spring-boot-starter-parent` và khai báo `spring-boot-maven-plugin` trong `<build><plugins>`, execution `repackage` được parent quản lý và thường chạy ở `package`.

Với POM **không sử dụng Boot parent**, phải cấu hình plugin version và execution goal `repackage` hoặc chạy goal tường minh **sau** khi package. Ví dụ fragment:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <configuration>
        <layout>JAR</layout>
        <mainClass>demo.Application</mainClass>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Fragment này **không** phải POM chạy độc lập; còn cần dependencies Spring Boot, compiler/JDK thích hợp và ứng dụng main. Nếu goal chưa bind, có thể chạy `mvn package spring-boot:repackage` để đảm bảo archive đã có trước repackage; không gọi chỉ `mvn spring-boot:repackage` trên một thư mục vừa `clean` rồi mong nó tự compile/package từ đầu.

**Tại sao plugin cần nested JAR layout?** JVM `java -jar` thông thường đọc manifest/classpath của archive, nhưng không tự nạp mọi JAR được đặt như file ZIP entry bên trong một JAR khác. Spring Boot launcher dùng class loading dành cho nested archives, nên application có thể chạy như một executable JAR duy nhất. `JarLauncher` và `WarLauncher` có đường tìm library cố định, trong khi `PropertiesLauncher` cho phép cấu hình classpath rộng hơn.

## 5. Layout JAR: lựa chọn tiêu chuẩn cho ứng dụng tự chạy

### 5.1. Cấu trúc và manifest

Một executable JAR Spring Boot 3.3 thường có layout:

~~~text
app.jar
  META-INF/MANIFEST.MF
  org/springframework/boot/loader/...   (bootstrap classes)
  BOOT-INF/classes/...                  (application classes/resources)
  BOOT-INF/lib/*.jar                    (runtime dependencies)
~~~

`JarLauncher` tìm classes và libraries trong `BOOT-INF/classes` và `BOOT-INF/lib`. Java main của app nằm trong `BOOT-INF/classes`, nhưng manifest `Main-Class` là Boot launcher chứ không phải class của app.

### 5.2. Bài thực hành JAR đầy đủ (Java 17 + Maven)

Cấu trúc:

~~~text
layout-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          Application.java
~~~

Tạo `pom.xml`:

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
    <artifactId>layout-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.Application</mainClass>
                    <layout>JAR</layout>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`<packaging>jar</packaging>` yêu cầu Maven tạo JAR; `<layout>JAR</layout>` xác định cách repackage. Với dự án tiêu chuẩn, có thể **bỏ `<layout>JAR</layout>`** để plugin suy ra mặc định từ packaging, tránh lặp cấu hình không cần thiết. Ở đây ghi rõ chỉ để học sự khác biệt.

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println("layout-demo:ok");
    }
}
~~~

Đây là một chương trình Spring Boot command-line không dùng `spring-boot-starter-web`, nên không mở HTTP server và thông thường tự thoát sau khi runner hoàn tất.

Build và chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn clean package
java -jar target/layout-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Nếu không có Maven cài sẵn nhưng project đã có Maven Wrapper, lệnh build là `./mvnw clean package` trên Linux/macOS hoặc `.\mvnw.cmd clean package` trong PowerShell. Với output của **chính `System.out.println` trong ứng dụng**, dòng kết quả là:

~~~text
layout-demo:ok
~~~

Maven có log build riêng; ví dụ này dùng arguments tắt banner/log Spring Boot để tập trung vào stdout chương trình. Các thông báo JVM hoặc môi trường ngoài ứng dụng không thuộc dòng trên.

Xem các ZIP entries:

~~~bash
jar tf target/layout-demo-1.0.0.jar
~~~

Cần thấy `META-INF/MANIFEST.MF`, `BOOT-INF/classes/demo/Application.class`, các `BOOT-INF/lib/*.jar` và Boot loader classes. Đây là cách xác minh file JAR đã **được repackage** thay vì chỉ thấy một `layout-demo-1.0.0.jar` có tên đúng.

### 5.3. Khi nào chọn JAR?

Chọn layout `JAR` khi:

- Triển khai một Java process chạy bằng `java -jar` hoặc dùng một Docker/OCI image chứa executable JAR.
- Không cần thay đổi classpath ngoài archive qua `PropertiesLauncher`.
- Muốn cấu hình ít, theo convention và hỗ trợ tốt với Maven, CI, Spring Boot tooling.
- Ứng dụng CLI, worker hoặc web service tự mang embedded server.

**Không dùng lý do “tên JAR phải cố định” để đổi layout.** Tên archive thuộc `<build><finalName>`; loại layout không điều khiển tên file.

## 6. Layout ZIP/DIR: dùng PropertiesLauncher cho classpath linh hoạt

### 6.1. ZIP không phải yêu cầu đổi extension thành .zip

Trong Spring Boot Maven Plugin, `ZIP` là tên một `layout`; tài liệu xác nhận **`DIR` là alias của `ZIP`**. Layout này tương tự `JAR` về cách tổ chức application classes và dependencies, nhưng sử dụng `PropertiesLauncher` làm bootstrap.

Nếu Maven project vẫn có `<packaging>jar</packaging>`, file output thường **vẫn là `.jar`**, ví dụ `target/layout-demo-1.0.0.jar`. `ZIP` **không bắt buộc** tạo file `layout-demo.zip` hoặc giải nén thành thư mục. `DIR` cũng không tự chuyển output từ file thành directory trên đĩa.

Trong Spring Boot 3.3, `Main-Class` của ZIP layout thường là:

~~~text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: demo.Application
~~~

Để kiểm chứng, đọc manifest **của file thực tế**. Không chỉ đoán từ `pom.xml`, vì layout có thể bị override trong effective plugin configuration.

### 6.2. Chuyển ví dụ JAR sang ZIP

Dùng nguyên `pom.xml` và `Application.java` từ mục 5, **chỉ sửa** trong `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <mainClass>demo.Application</mainClass>
    <layout>ZIP</layout>
</configuration>
~~~

Chạy lại:

~~~bash
mvn clean package
java -jar target/layout-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do ứng dụng in ra vẫn là:

~~~text
layout-demo:ok
~~~

Điều khác biệt là **launcher** được nhúng và khả năng cấu hình loader classpath, không phải logic `CommandLineRunner`. Nếu dùng `<layout>DIR</layout>` thay cho `ZIP`, theo tài liệu hai tên tương đương về layout.

### 6.3. loader.path và thư viện bổ sung bên ngoài archive

`PropertiesLauncher` có thể lấy thêm thư mục hoặc archive từ thuộc tính `loader.path` hay environment variable `LOADER_PATH`. Ví dụ trong môi trường bạn **chủ động tạo thư mục `external-libs` chứa những JAR được phép dùng**:

~~~bash
java -Dloader.path=external-libs -jar target/layout-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dấu `-Dloader.path=...` là **JVM system property**, phải đứng **trước `-jar`**. Còn các đối số Spring như `--spring.main.banner-mode=off` nằm sau đường dẫn JAR để ứng dụng nhận. `loader.path` có thể chứa nhiều entries cách nhau bằng dấu phẩy theo cú pháp của launcher. Nó không phải `spring.config.location` và không đồng nghĩa với tham số shell `-cp`.

**Ví dụ trên chỉ mô tả cách truyền loader path, không tạo tự động nội dung `external-libs`**. Nếu thư mục trống, điều đó không cho thấy launcher đã thực sự nạp được một thư viện mới; để kiểm thử extension, cần một JAR bổ sung và một chức năng thật sử dụng nó. Không dùng classpath ngoài như cách “thả ngẫu nhiên phiên bản JAR mới” vào production: có thể làm thay đổi thứ tự class loading, phá tương thích nhị phân, giảm tính tái lập và tạo rủi ro bảo mật.

Trong Spring Boot documentation, `PropertiesLauncher` có nhiều setting hơn, ví dụ `loader.home`, `loader.config.name`/`loader.config.location`, `loader.main`, `loader.path`. Cơ chế tìm `loader.properties` và mức ưu tiên giữa system property/environment/manifest phụ thuộc phiên bản; kiểm tra tài liệu của Boot bạn đang dùng, nhất là nếu tự động hóa triển khai.

### 6.4. Khi nào ZIP/DIR có ích và khi nào không?

**Có ích** khi có nhu cầu chính đáng về classpath mở rộng: plugin runtime được tổ chức riêng, một bộ thư viện ngoài được kiểm soát bằng version/checksum hoặc cơ chế vận hành dùng `PropertiesLauncher`. Tuy vậy, lựa chọn này **không tự tạo kiến trúc plugin an toàn**; vẫn cần API contracts, isolation, versioning và test tương thích.

**Không cần ZIP** nếu ứng dụng chỉ cần đóng gói dependencies và chạy như một process độc lập. Layout `JAR` mặc định đơn giản hơn, có ít setting bị hiểu sai và giúp pipeline triển khai rõ ràng.

## 7. Layout WAR: executable WAR và external servlet container

### 7.1. Vì sao WAR khác JAR?

Một Spring Boot executable `WAR` có layout phổ biến:

~~~text
app.war
  META-INF/MANIFEST.MF
  org/springframework/boot/loader/...
  WEB-INF/classes/...             (application classes/resources)
  WEB-INF/lib/*.jar               (runtime dependencies)
  WEB-INF/lib-provided/*.jar      (provided dependencies)
~~~

`WarLauncher` biết nạp `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` khi chạy executable WAR bằng `java -jar`. Các dependencies `provided` được đặt riêng để tránh xung đột với libraries do **external servlet container** cung cấp trong trường hợp deploy WAR theo cách truyền thống.

Nhưng **Maven packaging và Spring Boot layout phải phù hợp với định dạng**: khi muốn build WAR, đặt `<packaging>war</packaging>`, bảo đảm Maven WAR Plugin tham gia đúng lifecycle và Spring Boot `repackage` tạo layout WAR. Đừng đổi riêng `<layout>WAR</layout>` trong một JAR project rồi khẳng định đã có WAR hợp lệ để deploy.

### 7.2. POM WAR minh họa đầy đủ

Tạo project **riêng** `war-layout-demo` (không sửa chồng POM JAR trong ví dụ trước). `pom.xml`:

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
    <artifactId>war-layout-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.WarApplication</mainClass>
                    <layout>WAR</layout>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở đây `spring-boot-starter-web` đã kéo Tomcat theo đường dependency bắc cầu; **khai báo trực tiếp** `spring-boot-starter-tomcat` với `scope=provided` nhằm cho Maven/Spring Boot biết container dependency không nên nằm trên classpath ứng dụng WAR như một runtime dependency bình thường khi triển khai vào servlet container ngoài. Trong executable WAR, nó vẫn có thể được đặt ở `WEB-INF/lib-provided` để `WarLauncher` dùng khi chạy bằng `java -jar`.

Bản Boot 3.3 sử dụng Jakarta Servlet APIs; để deploy vào external servlet container, hãy dùng container **tương thích với đúng phiên bản Boot/Jakarta**, không lấy Tomcat 9 (javax.servlet) cho Boot 3.x. Với servlet container ngoài, những cấu hình class loading/dependency và policy của container vẫn có thể ảnh hưởng.

### 7.3. Ứng dụng WAR với SpringBootServletInitializer

Cấu trúc:

~~~text
war-layout-demo/
  pom.xml
  src/main/java/demo/WarApplication.java
~~~

Tạo `src/main/java/demo/WarApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class WarApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(WarApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarApplication.class);
    }

    @GetMapping(value = "/probe", produces = "text/plain")
    public String probe() {
        return "war-layout-ok";
    }
}
~~~

`main` phục vụ **executable WAR** khi dùng `java -jar`, còn `SpringBootServletInitializer` cấu hình entry point cho **servlet container bên ngoài**. Không dùng chỉ `<layout>WAR</layout>` thay cho lớp initializer khi mục tiêu là deploy WAR lên một container truyền thống.

### 7.4. Build, chạy và kiểm chứng WAR

Từ project `war-layout-demo`:

~~~bash
mvn clean package
jar tf target/war-layout-demo-1.0.0.war
~~~

Bạn sẽ thấy những đường dẫn như `WEB-INF/classes/demo/WarApplication.class`, `WEB-INF/lib/` và `WEB-INF/lib-provided/`, cùng loader classes. Nếu dùng `unzip` có thể xem manifest:

~~~bash
unzip -p target/war-layout-demo-1.0.0.war META-INF/MANIFEST.MF
~~~

Với layout WAR Boot 3.3, `Main-Class` thường là `org.springframework.boot.loader.launch.WarLauncher` và `Start-Class` là `demo.WarApplication`.

Ở terminal thứ nhất, chạy executable WAR bằng embedded server:

~~~bash
java -jar target/war-layout-demo-1.0.0.war --server.address=127.0.0.1 --server.port=8087
~~~

Ở terminal thứ hai, khi startup hoàn tất:

~~~bash
curl -fsS http://127.0.0.1:8087/probe
~~~

**Nội dung HTTP body** chính xác là:

~~~text
war-layout-ok
~~~

`curl` có thể không thêm newline sau body. Khi kết thúc, dừng process Java ở terminal thứ nhất (ví dụ `Ctrl+C`) để giải phóng port. Với CI, hãy tự động quản lý process/timeout/cleanup thay vì dựa vào hai terminal và chờ vô hạn.

**Triển khai external container là một phép thử khác:** deploy file WAR vào container tương thích; khi đó context path có thể lấy từ tên WAR hoặc config container và URL `/probe` có thể không nằm tại root. Phải xác minh trong container thật, không cho rằng `java -jar` PASS tương đương external deploy PASS.

### 7.5. Khi nào chọn WAR?

Chọn khi yêu cầu vận hành thật sự là **WAR deploy vào external Servlet container**, hoặc có hợp đồng phát hành WAR cụ thể. Nếu dùng Spring Boot như một service độc lập không cần container ngoài, `JAR` thường đơn giản hơn.

Không chọn `WAR` chỉ để “có thêm nested dependencies”; executable JAR cũng có `BOOT-INF/lib`. Cũng không đổi phần mở rộng từ `.jar` sang `.war` bằng `finalName` để tạo WAR giả: định dạng và Maven lifecycle phải đúng.

## 8. Layout NONE: gom dependencies nhưng không nhúng launcher

### 8.1. NONE khác skip

`NONE` là layout đặc biệt của `spring-boot:repackage`. Theo tài liệu Spring Boot, nó **gói dependencies và project resources** nhưng **không bao gồm bootstrap loader**. Vì thiếu loader cần cho nested dependencies, nó **không được coi là Spring Boot executable archive theo cách `java -jar` thông thường**.

So sánh:

| Cấu hình | Repackage có chạy? | Boot bootstrap loader được nhúng? | Ý nghĩa |
| --- | --- | --- | --- |
| `layout=JAR` | Có | Có | Boot executable JAR |
| `layout=WAR` | Có | Có | Boot executable WAR |
| `layout=ZIP` | Có | Có (`PropertiesLauncher`) | Boot executable với classpath linh hoạt |
| `layout=NONE` | Có | **Không** | Archive chứa project/dependencies cho consumer chuyên biệt |
| `skip=true` | Không | Không thêm bởi goal này | Giữ artifact từ bước Maven packaging trước đó |

Nếu bạn đặt thủ công `Main-Class` bằng một plugin khác, một file `NONE` **có thể** có một manifest entry khác, nhưng không vì thế mà trở thành executable Boot archive: Java vẫn cần một classpath/launcher phù hợp để tìm dependency. Đừng viết quy tắc tuyệt đối “mọi NONE file đều không có manifest”; quy tắc chắc chắn là **Spring Boot không thêm bootstrap loader cho NONE**.

### 8.2. Biến thể cấu hình trên ví dụ JAR

Từ project `layout-demo` của mục 5, chỉ thay cấu hình plugin thành:

~~~xml
<configuration>
    <layout>NONE</layout>
</configuration>
~~~

Có thể bỏ `mainClass` vì mục đích lúc này **không phải** tạo một executable archive theo launcher của Boot. Chạy:

~~~bash
mvn clean package
jar tf target/layout-demo-1.0.0.jar
~~~

Kiểm tra nội dung thật: project classes/resources và những dependency được repackage phải theo cấu trúc do plugin và version hiện tại tạo. **Không suy đoán** một layout cố định như `BOOT-INF/lib` cho `NONE` nếu chưa inspect; điều quan trọng là file **không có bootstrap loader**.

**Không dùng kết quả `java -jar target/layout-demo-1.0.0.jar` như một test PASS bắt buộc cho layout NONE.** Nếu nó không tự khởi động, đó phù hợp với mục tiêu của NONE. Nếu hệ thống tiêu thụ cần chạy code bên trong, hệ thống ấy phải biết cách nạp classes/libraries hoặc có cơ chế bootstrap riêng.

### 8.3. Khi nào NONE là lựa chọn hợp lý?

- Hệ thống phát hành riêng muốn archive chứa dependencies nhưng **không dùng** Spring Boot launcher.
- Một công cụ bên ngoài có nhiệm vụ phân tích/giải nén/repackaging classes và libraries theo giao thức đã thiết kế.
- Kiến trúc runtime đã có bootstrap và classpath resolution được quản lý ngoài artifact.

**Không nên dùng NONE để “làm JAR nhẹ hơn” theo cảm tính.** Nested dependencies vẫn có thể được gom vào archive; NONE không có nghĩa tạo thin JAR chỉ chứa application classes. Nếu bạn muốn JAR library tiêu chuẩn để project khác phụ thuộc, phải xem lại **có nên repackage module ấy không**, và kiểm tra Maven main artifact/classifier/attach sao cho dependency consumer nhận đúng định dạng.

## 9. Kiểm chứng layout bằng manifest và file entries

Không nên chỉ đọc `<layout>` rồi tuyên bố archive đúng. Một phép kiểm chứng đáng tin:

1. `mvn clean package` từ **đúng module**.
2. Kiểm tra file artifact đã tạo và extension thực.
3. Dùng `jar tf` tìm các đường dẫn lớp/library theo layout.
4. Đọc `META-INF/MANIFEST.MF`, đặc biệt `Main-Class` và `Start-Class`.
5. Nếu layout có loader, **chạy đúng archive** bằng `java -jar` và xác minh kết quả hoặc endpoint.
6. Nếu layout `NONE`, **kiểm tra không có loader** thay vì chờ `java -jar` hoạt động.
7. Nếu output cuối là WAR external deploy hay Docker image, kiểm tra thêm chính sản phẩm/runtime cuối.

### 9.1. Dùng JDK để inspect mà không cần unzip

Java 17 có `java.util.jar.JarFile`; class này có thể đọc cả `.jar` và `.war` nếu file đó là ZIP-compatible archive. Tạo file độc lập `InspectLayout.java`:

~~~java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class InspectLayout {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java InspectLayout.java <archive-path>");
        }

        Path archive = Path.of(args[0]);
        try (JarFile file = new JarFile(archive.toFile())) {
            Manifest manifest = file.getManifest();
            Attributes attrs = manifest == null
                    ? new Attributes()
                    : manifest.getMainAttributes();

            String main = attrs.getValue("Main-Class");
            String start = attrs.getValue("Start-Class");

            boolean bootClasses = file.stream().anyMatch(
                    e -> e.getName().startsWith("BOOT-INF/classes/"));
            boolean bootLibs = file.stream().anyMatch(
                    e -> e.getName().startsWith("BOOT-INF/lib/"));
            boolean warClasses = file.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/classes/"));
            boolean warLibs = file.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/lib/"));
            boolean warProvided = file.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/lib-provided/"));
            boolean bootLoader = file.stream().anyMatch(
                    e -> e.getName().startsWith(
                            "org/springframework/boot/loader/"));

            System.out.println("main=" + main);
            System.out.println("start=" + start);
            System.out.println("boot.classes=" + bootClasses);
            System.out.println("boot.libs=" + bootLibs);
            System.out.println("war.classes=" + warClasses);
            System.out.println("war.libs=" + warLibs);
            System.out.println("war.provided=" + warProvided);
            System.out.println("boot.loader=" + bootLoader);
        }
    }
}
~~~

Đây là một Java source-file launcher program **độc lập**, không cần thêm dependency Maven. Chạy từ thư mục chứa file:

~~~bash
java InspectLayout.java target/layout-demo-1.0.0.jar
~~~

Với **JAR layout của ví dụ mục 5**, output của chương trình sẽ có các giá trị chính như:

~~~text
main=org.springframework.boot.loader.launch.JarLauncher
start=demo.Application
boot.classes=true
boot.libs=true
war.classes=false
war.libs=false
war.provided=false
boot.loader=true
~~~

Các giá trị trên là **kỳ vọng cho đúng ví dụ Spring Boot 3.3.5 sau repackage**, không phải kết quả mặc định của mọi JAR trên thế giới. Nếu chuyển sang `ZIP`, thay đổi quan trọng là `main` thường thành `org.springframework.boot.loader.launch.PropertiesLauncher`. Nếu kiểm tra WAR, `war.classes` và `war.libs` thường là `true`, cùng `war.provided=true` nếu có provided dependencies tương ứng. Với `NONE`, giá trị `boot.loader` được kỳ vọng là `false`.

**Không suy luận layout dựa trên một boolean duy nhất.** Code chỉ báo cấu trúc và manifest. Phần chạy thử bằng `java -jar` hoặc deploy external servlet container mới xác minh khả năng thực thi thật.

### 9.2. Kiểm tra manifest qua CLI khi có unzip

Linux/macOS với `unzip`:

~~~bash
unzip -p target/layout-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Windows PowerShell có thể dùng `jar xf` trong thư mục tạm hoặc Java `InspectLayout.java` như trên. Không giả định `unzip` mặc định được cài trên mọi Windows machine.

Nếu manifest có:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

đó là dấu hiệu JAR layout có launcher theo Spring Boot 3.3. Nếu:

~~~text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: demo.Application
~~~

đó là dấu hiệu ZIP/DIR layout. Với WAR, launcher thường là `WarLauncher`. **Không tự sửa thủ công `Main-Class` bằng `maven-jar-plugin` để “đổi layout”**; Spring Boot plugin quản lý manifest theo loader và archive layout, nên cách đúng là đổi `layout` cùng `mainClass` khi thực sự cần.

## 10. Classifier, attach và rủi ro triển khai nhầm JAR

Một layout đúng vẫn có thể bị kiểm thử sai nếu pipeline chọn nhầm artifact. Ví dụ khi Maven plugin cấu hình:

~~~xml
<configuration>
    <mainClass>demo.Application</mainClass>
    <layout>JAR</layout>
    <classifier>exec</classifier>
</configuration>
~~~

Spring Boot có thể tạo/attach một executable artifact có classifier `exec` bên cạnh main archive thông thường. Tên file cục bộ theo ví dụ project có thể là:

~~~text
target/layout-demo-1.0.0.jar
target/layout-demo-1.0.0-exec.jar
~~~

Khi ấy `-exec.jar` thường là archive được repackage, còn JAR không classifier có thể là plain archive. Vì vậy lệnh smoke phải dùng **đúng file**:

~~~bash
java -jar target/layout-demo-1.0.0-exec.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do `Application` in vẫn là:

~~~text
layout-demo:ok
~~~

**Đừng hardcode rằng mọi build có cả hai file.** Nếu không dùng classifier, repackage có thể thay thế main artifact và để bản gốc với phần mở rộng `.original`. Nếu `attach=false`, artifact repackaged không nhất thiết được install/deploy vào Maven repository theo cách mặc định. Cần đọc cấu hình và output thực của plugin.

**Không dùng `finalName` để thay Maven coordinates.** Ví dụ đổi `<finalName>service</finalName>` có thể cho local file `target/service.jar` nhưng module vẫn có identity `example.learning:layout-demo:1.0.0` khi install/deploy. Thay tên file không quyết định `JAR/WAR/ZIP/NONE`.

## 11. Layered JAR khác layout

Spring Boot có hỗ trợ **layered archive** cho Docker/OCI images, phân tách những thành phần như dependencies, loader, snapshot dependencies, application theo chính sách layer. Layering nhằm tận dụng caching khi xây image; archive vẫn có cấu trúc để launcher tìm classes/libs.

Đừng nhầm:

- `layout=JAR`: quyết định **cấu trúc và bootstrap** của executable archive.
- `layers`: mô tả **các layer** bên trong những archives được hỗ trợ, không tạo ra một layout tên `LAYERS`.
- `spring-boot:build-image`: một goal khác tạo OCI image, không đơn thuần đổi extension của file JAR.
- `<executable>true</executable>`: thêm launch script vào archive được hỗ trợ, không tự đổi `JAR` sang `ZIP` hay `WAR`.

Vì vậy, khi yêu cầu “tối ưu Docker layer caching”, hãy xem cấu hình layers và build-image; khi yêu cầu “có thể nạp thư viện từ thư mục bên ngoài”, hãy cân nhắc `ZIP`/`PropertiesLauncher`; khi yêu cầu “deploy vào servlet container”, hãy xem `WAR`. Một `layout` không giải quyết mọi bài toán packaging.

## 12. Các lựa chọn nâng cao và giới hạn tương thích

### 12.1. Custom layoutFactory

Spring Boot Maven Plugin có parameter `layoutFactory` cho những nhu cầu bố cục đặc biệt. Nó yêu cầu một implementation của Boot `LayoutFactory` và cấu hình plugin classpath phù hợp. Khi đã **chỉ định `<layout>...` tường minh**, tài liệu plugin nói các custom layout factories sẽ bị bỏ qua. Vì vậy không đồng thời mong `layoutFactory` tùy biến có hiệu lực khi một `layout` được cấu hình cố định.

Chỉ sử dụng custom layout nếu có một yêu cầu rõ ràng và đội ngũ đủ khả năng bảo trì/testing; cho các use case tiêu chuẩn, `JAR/WAR/ZIP/NONE` dễ dự đoán hơn.

### 12.2. Không biến embedded server thành external WAR chỉ bằng layout

Một web app cần deploy lên external Tomcat thường phải có:

- Maven `<packaging>war</packaging>` và dependency scopes đúng.
- `SpringBootServletInitializer` hoặc cơ chế bootstrap servlet tương đương.
- Servlet container tương thích `jakarta.servlet` và Java version của Boot.
- Cấu hình context path, logging, JNDI/security và deploy flow phù hợp.
- Smoke test **trên chính external container**.

Nếu chỉ sửa `<layout>WAR</layout>` trong project JAR mà không điều chỉnh các phần kia, kết quả có thể bị mismatch hoặc không phù hợp với deploy mục tiêu.

### 12.3. Không coi PropertiesLauncher là “nâng cấp JAR” miễn phí

`ZIP` có giá trị khi cần configurable classpath. Nhưng classpath bên ngoài làm tăng các biến thể phải kiểm thử: thứ tự tìm classes, library version conflict, permission và files tồn tại khi deploy, rủi ro supply chain nếu thư mục bị thay đổi bởi thành phần không đáng tin. Dùng `ZIP` phải đi kèm quy trình quản lý external JARs, checksum và regression tests.

### 12.4. Đừng kết luận layout NONE có thể chạy bằng java -jar

Một Java archive bất kỳ có thể chứa `Main-Class` nhờ plugin khác, nhưng **Spring Boot layout NONE không nhúng Boot bootstrap loader**. Nested library entries không tự trở thành JVM classpath. Nếu consumer muốn chạy được, consumer phải cung cấp classpath/launcher riêng; nếu cần tự chạy standalone, chọn `JAR` hoặc một layout executable thích hợp.

### 12.5. Chú ý các phiên bản Spring Boot

Spring Boot loader packages thay đổi theo phiên bản. Ví dụ, launcher class trong Spring Boot 3.3 nằm dưới `org.springframework.boot.loader.launch`; tài liệu Boot 3.1 trở về trước có thể hiển thị đường dẫn `org.springframework.boot.loader.JarLauncher`. Không lấy tên class từ bài viết cũ rồi chỉnh manifest bằng tay. Khi dùng Boot version khác, xem manifest được plugin **thực sự tạo ra** và tài liệu đúng version.

## 13. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Việc cần làm |
| --- | --- | --- |
| `no main manifest attribute` khi chạy JAR | Plain archive, layout `NONE`, `repackage` chưa chạy hoặc file sai | Kiểm tra `Main-Class`, plugin execution, classifier |
| `ClassNotFoundException` cho `JarLauncher` | Loader không có trong archive hoặc manifest trỏ launcher không đúng version | `jar tf`, inspect manifest, rebuild đúng Boot plugin |
| `ClassNotFoundException` cho application class | `Start-Class` sai package, compiled class không nằm đúng nơi | Kiểm tra FQCN, `BOOT-INF/classes`/`WEB-INF/classes` |
| `NoClassDefFoundError` khi chạy executable archive | Dependency runtime bị exclude/đặt scope sai | Xem `BOOT-INF/lib` hay `WEB-INF/lib`, dependency tree |
| `UnsupportedClassVersionError` | JRE/JDK runtime quá cũ so với compiled bytecode | `java -version` nơi chạy, compiler/toolchain settings |
| File vẫn `.jar` sau khi đặt `layout=ZIP` | Đây là hành vi bình thường, do Maven `packaging=jar` | Phân biệt layout và extension, xem `PropertiesLauncher` |
| `loader.path` dường như không có tác dụng | App vẫn dùng `JarLauncher`, sai tên property hoặc thiếu external directory | Kiểm tra manifest, JVM `-Dloader.path` trước `-jar`, log |
| File `.war` không deploy được trên Tomcat 9 | Spring Boot 3.x dùng Jakarta Servlet, Tomcat 9 dùng javax | Dùng container phù hợp và cấu hình WAR/initializer |
| `java -jar` WAR chạy được nhưng deploy external thất bại | Servlet initializer/container config/scope/context path không đúng | Kiểm tra external deployment logs, container version và URL |
| `WEB-INF/lib-provided` không như mong đợi | Scope `provided` chưa đúng hoặc WAR chưa repackage | Xem effective dependencies và archive entries |
| `NONE` không chạy với `java -jar` | Không có Boot bootstrap loader, đúng theo design | Dùng consumer-specific launcher hoặc layout executable |
| Build OK nhưng pipeline upload nhầm JAR | Có nhiều classifier/plain/original JARs | Chọn path cố định, manifest và checksum |
| `mvn spring-boot:repackage` báo không có archive | Chưa thực hiện phase `package` | Chạy lifecycle package trước khi repackage |
| Layout đúng nhưng Docker container không start | Image entrypoint, JRE, permissions hoặc môi trường khác | Test trực tiếp OCI image và runtime |
| Custom layoutFactory không hoạt động | `layout` tường minh đang được ưu tiên | Xem cấu hình plugin, bỏ override nếu muốn dùng factory |
| Đổi layout để “giảm size” nhưng JAR vẫn lớn | Layout không phải cơ chế loại dependencies | Xem exclusions, packaging, layering và thực tế archive |

**Cách đọc lỗi:** tên exception chỉ là manh mối, không phải kết luận. Khi lỗi xuất hiện sau deploy, kiểm tra theo thứ tự **artifact đúng → manifest → entries → JVM/version → dependencies → logs/runtime**. Không chữa `ClassNotFoundException` bằng cách đổi ngẫu nhiên `layout` mà không hiểu library bị thiếu ở đâu.

## 14. Tình huống lựa chọn trong dự án thật

### A. Web service Spring Boot chạy một process trong container

Yêu cầu: CI build một executable archive, Dockerfile chạy `java -jar`, không có servlet container ngoài, không có runtime plugin loading.

**Chọn:** Maven `packaging=jar`, Boot `layout=JAR` hoặc giữ mặc định. Build bằng `mvn clean package`, kiểm tra `BOOT-INF`, smoke test `java -jar` và image.

**Không chọn:** `WAR` vì không cần servlet container ngoài; `ZIP` vì không cần external classpath; `NONE` vì thiếu Boot bootstrap launcher.

### B. Doanh nghiệp yêu cầu deploy WAR vào external Tomcat

Yêu cầu: ứng dụng đóng gói thành WAR, chạy trong servlet container tương thích, đồng thời có thể dùng lệnh `java -jar` để debug khi cấu hình đủ.

**Chọn:** Maven `packaging=war`, layout `WAR`, `SpringBootServletInitializer`, container dependency `provided`, test cả executable WAR lẫn external deployment.

**Không làm:** đổi duy nhất `<layout>WAR</layout>` của một project vốn tạo JAR rồi kết luận đã sẵn sàng deploy.

### C. Một launcher cần nhận plugin JAR từ directory bên ngoài

Yêu cầu: cấu hình classpath có kiểm soát, công cụ vận hành quản lý versions/checksums cho external libraries.

**Cân nhắc:** Maven `packaging=jar`, layout `ZIP` hoặc `DIR`, dùng `PropertiesLauncher` cùng `loader.path`. Viết kiểm thử cụ thể chứng minh runtime nạp đúng plugin dự kiến; quản lý permission và version của plugin directory.

**Không suy ra:** `layout=ZIP` sẽ tạo sẵn thư mục plugin, file `.zip` hoặc tự quản lý tương thích của các JAR ngoài.

### D. Artifact được hệ thống khác unpack và khởi chạy bằng runtime riêng

Yêu cầu: hệ thống phát hành có loader/classpath management riêng; không muốn nhúng Spring Boot bootstrap loader.

**Cân nhắc:** layout `NONE` nếu downstream consumer hiểu định dạng output và đã được thử nghiệm. Định nghĩa contract archive, paths, dependency handling và metadata rõ ràng.

**Không dùng:** `NONE` cho service mà pipeline chỉ biết `java -jar` và không có launcher nào khác.

### E. Chỉ muốn tách plain JAR và executable JAR trong Maven repository

Yêu cầu: module khác muốn dùng các classes như thư viện, còn deployment muốn một executable artifact.

**Chọn cơ chế:** classifier `exec`/attach rõ ràng hoặc tách modules theo nhu cầu; không tìm cách giải bằng `layout=ZIP` hoặc `layout=NONE` một cách tình cờ. Kiểm tra tọa độ `groupId:artifactId:version:classifier` và file nào được downstream lấy về.

## 15. Checklist khi thay layout Spring Boot Maven Plugin

1. **Xác định sản phẩm cuối:** process chạy `java -jar`, WAR deploy external Tomcat, external classpath, hay consumer-specific archive?
2. **Chọn Maven `packaging` đúng:** `jar` hoặc `war`; không nhầm với `layout`.
3. **Chọn layout hoặc giữ mặc định:** JAR cho standalone, WAR cho WAR, ZIP/DIR cho `PropertiesLauncher`, NONE cho archive không Boot loader.
4. **Xác nhận Java main và servlet initializer:** `mainClass` cho launcher; WAR external deploy cần initializer/container compatibility.
5. **Xem `dependency scopes`:** đặc biệt WAR `provided` và runtime dependencies; đừng làm thiếu `BOOT-INF/lib` hoặc `WEB-INF/lib`.
6. **Kiểm tra plugin execution:** `repackage` phải chạy sau bước tạo archive; parent/no-parent khác nhau.
7. **Build sạch:** `mvn clean package` đúng module; không kiểm thử file cũ.
8. **Inspect file kết quả:** tên/extension, manifest, `Main-Class`, `Start-Class`, entries `BOOT-INF`/`WEB-INF`, sự có mặt của loader.
9. **Thử đúng launch mode:** `java -jar` cho executable JAR/WAR/ZIP; external container deploy test cho WAR; consumer-specific test cho NONE.
10. **Duy trì danh tính artifact:** classifier, attach và `finalName` không được làm pipeline chọn sai artifact.
11. **Với ZIP:** kiểm tra `loader.path` và external library management nếu thực sự sử dụng.
12. **Với container:** kiểm tra image/runtime cuối, không coi việc JAR chạy trên host là đủ.
13. **Với nhiều versions:** đối chiếu Spring Boot loader classes và docs đúng version, không hardcode manifest từ một bài viết khác.
14. **Ghi nhận quyết định:** vì sao chọn layout khác mặc định, lợi ích gì, điều kiện QA và cách rollback.

### Tự kiểm tra

**Câu 1.** Maven `packaging=jar`, Boot `layout=ZIP`. File output có chắc mang đuôi `.zip` không?

**Trả lời:** Không. Maven vẫn tạo artifact kiểu JAR; layout `ZIP` nói về bố cục và `PropertiesLauncher`, không phải extension file.

**Câu 2.** Vì sao `layout=NONE` không tương đương `skip=true`?

**Trả lời:** `NONE` vẫn cho phép repackage gom project/dependencies nhưng không nhúng loader; `skip=true` bỏ qua goal repackage.

**Câu 3.** `JAR` và `WAR` thường đặt application classes ở đâu?

**Trả lời:** JAR ở `BOOT-INF/classes`, WAR ở `WEB-INF/classes`. WAR có `WEB-INF/lib-provided` cho provided dependencies.

**Câu 4.** Khi nào nên dùng `PropertiesLauncher`?

**Trả lời:** Khi có nhu cầu rõ ràng về classpath tùy chỉnh bên ngoài archive thông qua `loader.path` hoặc loader configuration, và có quy trình quản lý, kiểm thử các JAR ngoài.

**Câu 5.** Một WAR chạy được bằng `java -jar` có chắc deploy vào Tomcat 9 được không nếu dùng Spring Boot 3.3?

**Trả lời:** Không. Boot 3.x dựa trên Jakarta Servlet; Tomcat 9 thuộc hệ javax cũ. Cần container tương thích và cấu hình WAR/initializer phù hợp.

**Câu 6.** Có thể dùng `maven-jar-plugin` đặt `Main-Class=demo.Application` để thay `layout=JAR` không?

**Trả lời:** Không. Spring Boot executable JAR cần loader cho nested runtime libraries, và Boot plugin quản lý manifest. Dùng `mainClass`/`layout` trong Spring Boot Maven Plugin thay vì sửa Main-Class thủ công.

## 16. Tài liệu chính thức

- Spring Boot Maven Plugin — Packaging Executable Archives (layouts JAR/WAR/ZIP/DIR/NONE): https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot Maven Plugin — Repackage goal parameters: https://docs.spring.io/spring-boot/maven-plugin/packaging.html#spring-boot-repackage
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Launching Executable Jars / PropertiesLauncher: https://docs.spring.io/spring-boot/specification/executable-jar/launching.html
- Spring Boot — Traditional Deployment (WAR): https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — POM Reference (`packaging`, `finalName` và plugins): https://maven.apache.org/pom.html
- Java 17 — JarFile: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Kết luận:** `packaging` quyết định **kiểu artifact Maven**, `layout` quyết định **cấu trúc và bootstrap của Spring Boot archive**. `JAR` là mặc định hợp lý cho standalone, `WAR` dành cho yêu cầu WAR/container, `ZIP`/`DIR` dùng `PropertiesLauncher` cho classpath linh hoạt, còn `NONE` gom dependencies mà **không nhúng Boot bootstrap loader**. Quyết định đúng phải được chứng minh bằng **artifact thật, manifest thật và đúng cách khởi chạy của môi trường triển khai**, không chỉ bằng một dòng `<layout>` trong POM.