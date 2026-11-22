# Đọc WEB-INF/classes, WEB-INF/lib và WEB-INF/lib-provided trong Spring Boot WAR

## 1. Bạn sẽ học được gì?

Một ứng dụng Spring Boot có thể được đóng gói thành **WAR** để triển khai vào servlet container bên ngoài (chẳng hạn Apache Tomcat tương thích), hoặc dùng **Spring Boot executable WAR** để tự chạy với lệnh `java -jar`. Hai chế độ triển khai có thể sử dụng **cùng một tệp WAR**, nhưng phải hiểu chính xác các thư mục bên trong để tránh đóng gói trùng servlet container, thiếu dependency hoặc nhầm classpath.

Trọng tâm của bài học là đọc đúng ba vị trí:

- `WEB-INF/classes/` — classes và tài nguyên ứng dụng do project biên dịch.
- `WEB-INF/lib/` — các JAR của ứng dụng được servlet container truyền thống nạp.
- `WEB-INF/lib-provided/` — các JAR thuộc nhóm **provided** do **Spring Boot executable WAR** giữ lại để chạy độc lập; container truyền thống **không** đưa thư mục này vào classpath webapp theo chuẩn WAR.

Sau bài, bạn có thể:

1. Đọc cây file `.war` bằng lệnh `jar tf` mà không cần giải nén toàn bộ.
2. Xác định lớp Java và `application.properties` ở `WEB-INF/classes`, library dependency ở `WEB-INF/lib` và Tomcat embedded dependency ở `WEB-INF/lib-provided`.
3. Giải thích vì sao `WEB-INF/lib-provided` có thể **có mặt vật lý** trong WAR nhưng **không gây xung đột** khi triển khai vào external servlet container.
4. Phân biệt cơ chế Spring Boot `WarLauncher` khi chạy `java -jar` với classloader của external Tomcat.
5. Cấu hình Maven `<packaging>war</packaging>`, scope `provided`, Spring Boot Maven Plugin; hoặc Gradle `war`, `providedRuntime` và `bootWar`.
6. Viết một ứng dụng Spring MVC Java 17+ có thể chạy trong cả hai chế độ.
7. Tự kiểm tra manifest, dependency placement, HTTP response, context path, lỗi namespace `jakarta.servlet` và phiên bản container.
8. Không nhầm executable WAR với JAR kiểu `BOOT-INF`, không nhầm WAR truyền thống với yêu cầu bắt buộc có `WEB-INF/lib-provided`.

**Phiên bản ví dụ:** Spring Boot **3.5.16**, Java **17+**; được chọn để có cú pháp, thư viện và tên launcher cụ thể. Project thật cần dùng dòng Spring Boot/Maven/Gradle và servlet container đã được team phê duyệt. Spring Boot 4 có một số artifact và starter names khác; đừng áp dụng ví dụ 3.5 nguyên trạng cho major khác.

## 2. WAR là gì? Vì sao khác JAR?

### 2.1. WAR trong hệ sinh thái Servlet

**WAR (Web Application Archive)** là gói triển khai web application theo quy ước Java Servlet. Về mặt vật lý, file `.war` sử dụng định dạng ZIP, tương tự một `.jar`, nhưng cấu trúc webapp mang những vị trí đặc biệt:

~~~text
example.war
├── META-INF/
│   └── MANIFEST.MF
├── index.html                       (nếu có tài nguyên web root)
└── WEB-INF/
    ├── classes/
    │   └── com/example/.../*.class
    ├── lib/
    │   └── *.jar
    └── web.xml                       (nếu dùng descriptor)
~~~

Trong WAR truyền thống:

- `WEB-INF/classes` có classes/resources của ứng dụng, là một **classpath root** của webapp.
- Mỗi JAR trực tiếp trong `WEB-INF/lib` là một phần của web application classpath.
- `WEB-INF/web.xml` là deployment descriptor kiểu truyền thống nhưng **không bắt buộc** trong rất nhiều ứng dụng hiện đại dùng programmatic/annotation-based initialization.
- Các tài nguyên trong `WEB-INF` được servlet container bảo vệ khỏi HTTP request trực tiếp theo quy tắc Servlet; chúng **không** phải một “public static folder”.
- Các file/tài nguyên web-root (ví dụ ảnh hoặc HTML ở root WAR) có thể được container phục vụ nếu cấu hình phù hợp.

Ví dụ ứng dụng Java đặt `com.example.war.WebApplication` tại:

~~~text
WEB-INF/classes/com/example/war/WebApplication.class
~~~

Đó là **đường dẫn lưu trong archive**, không phải file nguồn Java. Source thường nằm ở `src/main/java/com/example/war/WebApplication.java` và được Maven/Gradle compile thành `.class`.

### 2.2. Spring Boot executable WAR mở rộng layout truyền thống

Spring Boot Maven/Gradle plugin có thể tạo một **executable WAR** vừa:

- triển khai được trong một servlet container tương thích; vừa
- có thể chạy trực tiếp bằng `java -jar my-app.war` nhờ Spring Boot Loader.

Để hỗ trợ cả hai đường chạy, Spring Boot thêm launcher classes, manifest entrypoint và thư mục **`WEB-INF/lib-provided`** cho dependencies không nên nạp vào webapp classpath của external container nhưng lại cần cho chế độ embedded.

~~~text
demo-war-0.0.1-SNAPSHOT.war
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   ├── com/example/war/
    │   │   ├── DemoWarApplication.class
    │   │   └── HelloController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   └── ...
    └── lib-provided/
        ├── tomcat-embed-core-*.jar
        ├── tomcat-embed-el-*.jar
        ├── tomcat-embed-websocket-*.jar
        └── ...
~~~

Đây là **cây minh họa**, vì tên/phiên bản của các JAR phụ thuộc build và dependency management. `WEB-INF/lib-provided` không nhất thiết chứa chính xác cả ba file Tomcat như mọi phiên bản; hãy đọc artifact thực tế. `*` chỉ thay cho phần version/biến thể trong sơ đồ, không phải literal file có dấu sao.

### 2.3. Một bảng tổng kết cực quan trọng

| Đường dẫn trong WAR | Chứa gì? | External servlet container | `java -jar` qua Boot WarLauncher |
| --- | --- | --- | --- |
| `WEB-INF/classes/` | Classes và resources của ứng dụng | **Nạp vào webapp classpath** | **Nạp vào app classpath** |
| `WEB-INF/lib/*.jar` | Libraries runtime của webapp | **Nạp vào webapp classpath** | **Nạp cùng app** |
| `WEB-INF/lib-provided/*.jar` | Dependencies do môi trường ngoài cung cấp, điển hình embedded Tomcat | **Không đưa vào webapp classpath theo quy ước Servlet WAR** | **Boot Loader chủ động nạp** |
| `org/springframework/boot/loader/` | Boot loader classes tại root archive | Không phải cơ chế bootstrap webapp của container | `WarLauncher` bootstrap app |
| `META-INF/MANIFEST.MF` | Manifest và entrypoint của executable WAR | Không dùng `Main-Class` để khởi chạy servlet application | `java -jar` đọc `Main-Class` |
| `WEB-INF/web.xml` | Descriptor cũ/nếu cần | Container xử lý khi triển khai | Không phải cơ chế chính của Boot Loader |
| Web resources ở root WAR | Nội dung web root | Có thể phục vụ qua HTTP theo cấu hình | Có thể được framework/container embedded xử lý tùy cấu hình |

**Điểm mấu chốt:** `WEB-INF/lib-provided` **không phải thư mục chuẩn mà servlet container cần nạp**. Nó là phần tổ chức trong Spring Boot executable WAR nhằm giải quyết nghịch lý: external Tomcat phải dùng Tomcat của nó, còn `java -jar` phải có Tomcat embedded để tự mở server.

## 3. Đọc từng thư mục đúng cách

### 3.1. WEB-INF/classes là classpath root

Nếu trong WAR có:

~~~text
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/classes/static/info.txt
~~~

thì tại runtime, ứng dụng tìm class bằng tên:

~~~java
com.example.war.HelloController
~~~

và dùng resource lookup như:

~~~java
getClass().getClassLoader().getResource("application.properties");
~~~

chứ **không** import class với package `WEB-INF.classes.com.example.war`. `WEB-INF/classes` là **vị trí classpath**, không tham gia vào tên package Java.

Thông thường các thư mục nguồn chuyển thành:

| Nguồn project | Vị trí trong WAR |
| --- | --- |
| `src/main/java/com/example/war/HelloController.java` sau compile | `WEB-INF/classes/com/example/war/HelloController.class` |
| `src/main/resources/application.properties` | `WEB-INF/classes/application.properties` |
| `src/main/resources/static/info.txt` | `WEB-INF/classes/static/info.txt` |
| `src/main/resources/templates/page.html` | `WEB-INF/classes/templates/page.html` |
| `src/main/webapp/assets/logo.svg` (nếu dùng) | `assets/logo.svg` ở web root, không phải `WEB-INF/classes` |
| `src/test/java/...` | **Không thuộc** WAR runtime artifact |

Ví dụ `application.properties` nằm trong `WEB-INF/classes` vẫn là **classpath resource** và được Spring Boot đọc khi khởi động. `WEB-INF/classes/static/info.txt` có thể được Spring MVC static resource handling phục vụ qua URL tương ứng nếu framework/configuration cho phép; không nên suy ra rằng URL bắt buộc phải chứa chuỗi `WEB-INF/classes`.

Đừng đưa mật khẩu, API key hoặc bí mật sản xuất vào `src/main/resources/application.properties` vì đóng gói sẽ đưa chúng vào artifact. Dùng externalized configuration và secret management phù hợp.

### 3.2. WEB-INF/lib là webapp library classpath

Các dependencies trong `WEB-INF/lib` được sử dụng khi WAR triển khai vào external servlet container. Ví dụ `spring-webmvc`, `spring-context`, Jackson và những thư viện business khác cần nằm trên classpath webapp, nếu chúng không được chính container cung cấp theo hợp đồng.

Ví dụ:

~~~text
WEB-INF/lib/spring-webmvc-6.*.jar
WEB-INF/lib/jackson-databind-2.*.jar
WEB-INF/lib/slf4j-api-2.*.jar
~~~

Đây chỉ là **các tên minh họa** và version major có thể thay đổi theo Spring Boot BOM; không dùng text này để kiểm đếm chính xác dependencies. Để biết version thực, dùng `mvn dependency:tree` hoặc Gradle `dependencies` cùng `jar tf` của output.

Servlet container truyền thống thường tải các JAR `WEB-INF/lib` vào **web application classloader**. Tuy nhiên, container có thể có libraries dùng chung ở lớp cha; luật delegation và classloading có thể khác theo server. Nếu bạn vô tình đóng thêm một bộ Servlet API/Tomcat implementation trùng bộ có sẵn của server vào `WEB-INF/lib`, nguy cơ xung đột class và lỗi khi khởi động tăng lên.

**Đặt JAR vào `WEB-INF/lib` không có nghĩa nó đang được Spring tự inject thành bean**; nó chỉ làm class/resource có sẵn trên classpath. Auto-configuration, component scanning và bean lifecycle là các cơ chế khác.

### 3.3. WEB-INF/lib-provided là dependency dành cho chế độ tự chạy

Khi Maven dependency được khai báo `provided`, hoặc Gradle dùng `providedRuntime`, và WAR được đóng gói bằng Spring Boot plugin, những libraries tương ứng được đưa vào `WEB-INF/lib-provided`. Ví dụ quan trọng nhất là Tomcat embedded starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Khi WAR triển khai vào Tomcat bên ngoài:

~~~text
External Tomcat:
  server-managed servlet engine / servlet API / web container
        |
        v
  WEB-INF/classes + WEB-INF/lib
        |
        X WEB-INF/lib-provided không thuộc webapp classpath chuẩn
~~~

Khi WAR được chạy trực tiếp:

~~~text
java -jar demo-war.war
        |
        v
  Main-Class: org.springframework.boot.loader.launch.WarLauncher
        |
        +--> WEB-INF/classes
        +--> WEB-INF/lib/*.jar
        +--> WEB-INF/lib-provided/*.jar
        |
        v
  Start-Class: com.example.war.DemoWarApplication
        |
        v
  embedded Tomcat khởi chạy ứng dụng
~~~

**`provided` không có nghĩa “không bao giờ đóng gói vào WAR”.** Điều đó đúng với WAR truyền thống do Maven WAR Plugin tạo theo quy tắc dependency scope thông thường, nhưng Spring Boot **`repackage`** sẽ đưa những dependencies cần thiết của `provided` vào `WEB-INF/lib-provided` để WAR còn tự chạy. Tương tự, Boot `bootWar` lấy dependencies thuộc `providedRuntime`.

### 3.4. Vì sao không chỉ loại hoàn toàn Tomcat embedded?

Nếu Tomcat embedded bị loại hoàn toàn khỏi executable WAR, đường chạy `java -jar` có thể không có servlet engine để mở HTTP server. Spring Boot giữ nó riêng để **WarLauncher** có thể nạp khi tự chạy, nhưng external container không nạp. Đó là lý do `WEB-INF/lib-provided` khác việc chỉ xóa dependency.

Ngược lại, nếu mục tiêu chỉ là **WAR truyền thống không cần `java -jar`**, bạn có thể chọn WAR do Maven WAR Plugin/Gradle `war` tạo mà không chạy Boot repackage; archive ấy có thể **không có `WEB-INF/lib-provided`**. Việc thiếu thư mục này **không tự là lỗi** nếu artifact được thiết kế là plain WAR.

## 4. WAR chạy theo hai đường: ai khởi động ứng dụng?

### 4.1. Đường A: external servlet container

Ví dụ người vận hành deploy WAR vào một Apache Tomcat bên ngoài:

~~~text
$CATALINA_BASE/webapps/demo-war.war
    |
    v
Tomcat giải nén hoặc đọc WAR
    |
    v
Tomcat tạo webapp classloader
    |
    +--> WEB-INF/classes
    +--> WEB-INF/lib/*.jar
    |
    v
SpringBootServletInitializer / Servlet integration
    |
    v
Spring ApplicationContext khởi tạo trong servlet container
    |
    v
Controller nhận request qua Tomcat bên ngoài
~~~

Trường hợp này, **Tomcat bên ngoài quyết định cổng HTTP, connector, webapp context path và một phần lớp servlet server**. `Main-Class` của manifest không được Tomcat dùng để chạy `main(String[] args)` theo cách `java -jar`.

Ứng dụng Spring Boot Servlet thường có class kế thừa `SpringBootServletInitializer` và override `configure(SpringApplicationBuilder)` để đăng ký entrypoint theo Servlet bootstrap.

### 4.2. Đường B: executable WAR

Ví dụ:

~~~bash
java -jar target/demo-war-0.0.1-SNAPSHOT.war
~~~

JVM đọc manifest và gọi **`WarLauncher`**, một class thuộc `spring-boot-loader` được Spring Boot plugin thêm ở **root WAR**. WarLauncher biết các đường dẫn nested:

~~~text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/lib-provided/
~~~

và dựng classloader phù hợp rồi gọi `Start-Class` là ứng dụng có `main`. Ở đây Tomcat embedded có trên classpath nhờ `lib-provided` và app tự có HTTP server.

### 4.3. Phân biệt WarLauncher và JarLauncher

| Thuộc tính | Spring Boot executable JAR | Spring Boot executable WAR |
| --- | --- | --- |
| `Main-Class` thường gặp (Boot 3.5) | `org.springframework.boot.loader.launch.JarLauncher` | `org.springframework.boot.loader.launch.WarLauncher` |
| App classes | `BOOT-INF/classes` | `WEB-INF/classes` |
| Dependency JARs | `BOOT-INF/lib` | `WEB-INF/lib`, `WEB-INF/lib-provided` |
| Plain external servlet container deployment | Không phải chuẩn WAR deploy | Có thể triển khai nếu app phù hợp và container tương thích |
| Khi chạy `java -jar` | Loader nạp nested JARs | Loader nạp cả provided nested JARs |

**Đừng dùng `java -cp app.war com.example.war.DemoWarApplication` và mong JVM chuẩn tự tìm nested dependencies**. Java launcher chuẩn không tự đọc mọi JAR trong `WEB-INF/lib`/`WEB-INF/lib-provided` như Boot Loader. Với executable WAR dùng `java -jar` để đi theo manifest/WarLauncher.

## 5. Ví dụ Maven hoàn chỉnh: một WAR vừa deploy được vừa java -jar được

### 5.1. Cấu trúc

Tạo project Java 17, Spring Boot 3.5.x, Spring Web và Maven. Ví dụ file:

~~~text
demo-war/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/war/
    │   │   ├── DemoWarApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/com/example/war/
        └── DemoWarApplicationTests.java
~~~

Nếu được tạo từ Spring Initializr, project có thể có `mvnw`, `mvnw.cmd` và `.mvn/wrapper/`; nếu tự tạo bằng các file bên dưới, dùng `mvn` đã cài sẵn.

### 5.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-war</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Spring MVC/JSON và những dependencies của ứng dụng. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Có mặt khi tự chạy WAR; không nạp từ WEB-INF/lib
             trong external servlet container. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Vì project **kế thừa `spring-boot-starter-parent`**, parent đã cấu hình execution `repackage` cho Spring Boot Maven Plugin. Plugin được khai báo trong `<build><plugins>` sẽ tạo executable WAR ở phase `package`.

**Tại sao có hai dependency `spring-boot-starter-web` và `spring-boot-starter-tomcat`?** Starter Web thường kéo starter Tomcat như dependency bắc cầu. Khai báo starter Tomcat **trực tiếp với scope `provided`** cho Maven một chỉ dẫn rõ ràng về placement, thay vì để nó mặc định là runtime/compile dependency trong `WEB-INF/lib`. Dependency version được quản lý bởi Spring Boot BOM kế thừa.

**Nếu đã có corporate parent:** chỉ giữ parent đó, import `spring-boot-dependencies` BOM trong `dependencyManagement` và cấu hình `spring-boot-maven-plugin` version + goal `repackage` một cách tường minh. Import BOM **không tự mang theo plugin executions**. Cấu hình Java compiler/Maven WAR Plugin cũng cần được parent/module quản lý phù hợp.

### 5.3. Boot main class + servlet initializer

Tạo `src/main/java/com/example/war/DemoWarApplication.java`:

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoWarApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(DemoWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoWarApplication.class, args);
    }
}
~~~

**Đây là file Java hoàn chỉnh.**

- `@SpringBootApplication`: đánh dấu main configuration và bật component scanning/auto-configuration.
- `extends SpringBootServletInitializer` + `configure`: cung cấp bootstrap path cho **external Servlet container**.
- `main(String[] args)`: entrypoint dùng khi **WarLauncher** gọi ứng dụng theo `java -jar`.
- Hai con đường khởi động cùng sử dụng **`DemoWarApplication.class`** làm source configuration để hành vi nhất quán.

Nếu chỉ có `main` nhưng thiếu initializer phù hợp, `java -jar` có thể chạy trong khi external container không khởi tạo Spring application đúng. Ngược lại, nếu chỉ có servlet initializer mà không có main được Boot Loader dùng, plain WAR có thể deploy được nhưng không đáp ứng yêu cầu executable.

### 5.4. Controller nhận HTTP GET

Tạo `src/main/java/com/example/war/HelloController.java`:

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "WAR_OK";
    }
}
~~~

`@RestController` khiến chuỗi được ghi vào HTTP response body. Vì controller ở cùng package `com.example.war` với main class nên được component scanning mặc định tìm thấy.

### 5.5. Resource cấu hình

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=demo-war
server.port=8080
~~~

Khi `java -jar`, embedded Tomcat dùng `server.port=8080` nếu không bị override bởi env/JVM/CLI. **Khi deploy lên external Tomcat, cổng thực tế do external Tomcat connectors quyết định**, không lấy cổng 8080 trong file app làm chân lý.

### 5.6. Test Spring Boot ApplicationContext

Tạo `src/test/java/com/example/war/DemoWarApplicationTests.java`:

~~~java
package com.example.war;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoWarApplicationTests {

    @Test
    void contextLoads() {
        // Thành công khi Spring ApplicationContext khởi tạo được.
    }
}
~~~

`spring-boot-starter-test` có scope `test`. Maven test classpath vẫn có các components cần cho Spring Boot test, trong đó scope `provided` không làm Tomcat tự mất khỏi test classpath. Test này chỉ kiểm context; **không chứng minh toàn bộ HTTP deployment path**. Với ứng dụng thật, thêm smoke/integration test chạy chính WAR như artifact sản phẩm.

### 5.7. Build và chạy executable WAR

Tại `demo-war/`:

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/demo-war-0.0.1-SNAPSHOT.war
~~~

Nếu có Maven Wrapper:

~~~bash
./mvnw clean package
java -jar target/demo-war-0.0.1-SNAPSHOT.war
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
java -jar .\target\demo-war-0.0.1-SNAPSHOT.war
~~~

Bắt đầu Spring Boot ở terminal thứ nhất, thử endpoint ở terminal thứ hai:

~~~bash
curl -s http://localhost:8080/hello
~~~

HTTP response body **kỳ vọng chính xác** (nếu không đổi URL/port và app chạy thành công):

~~~text
WAR_OK
~~~

Log ứng dụng có thời điểm khởi động, tên thread và container info thay đổi theo môi trường. Không yêu cầu toàn bộ stdout đúng nguyên văn ví dụ.

**Kết luận chạy embedded:** WAR này dùng `WarLauncher` nạp `WEB-INF/lib-provided` chứa Tomcat embedded, nên mặc dù khai báo Tomcat scope `provided`, application vẫn có container để tự chạy.

## 6. Dùng jar tf để đọc archive mà không giải nén

### 6.1. Liệt kê file trong WAR

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war
~~~

Lệnh `jar tf` là JDK tool, đọc ZIP entries và **không extract/chỉnh sửa** WAR.

Nhìn những dòng như:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/DemoWarApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/lib/spring-webmvc-6.x.y.jar
WEB-INF/lib-provided/tomcat-embed-core-10.x.y.jar
~~~

**`6.x.y` và `10.x.y` là kí hiệu phiên bản minh họa**, không phải literal file names hay kết quả đã kiểm bằng runtime. Thực tế cần đọc tất cả entries và xác nhận đúng version được BOM/build resolve.

### 6.2. Lọc theo ba nhóm trên Linux/macOS

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep -E '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/)'
~~~

Để chỉ xem application classes/resources:

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep '^WEB-INF/classes/'
~~~

Chỉ xem dependency JARs trong hai thư mục thư viện:

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep -E '^WEB-INF/(lib|lib-provided)/[^/]+\.jar$'
~~~

Regex cuối chỉ chọn các file `.jar` trực tiếp ở hai đường dẫn. Nếu build có các nested path bất thường, câu lệnh lọc này sẽ bỏ qua chúng và đó cũng là tín hiệu cần kiểm tra packaging.

### 6.3. Lọc trong Windows PowerShell

~~~powershell
jar tf .\target\demo-war-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/classes/'

jar tf .\target\demo-war-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/lib/'

jar tf .\target\demo-war-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/lib-provided/'
~~~

Đường dẫn **bên trong JAR/WAR** dùng dấu `/`, kể cả khi hệ điều hành là Windows. Đường dẫn **file archive ở bên ngoài** có thể dùng `.\target\...` theo PowerShell.

### 6.4. Đếm nội dung với điều kiện đúng

Không dùng “số lượng JAR” làm thước đo chất lượng package. Một WAR có nhiều dependencies vì dùng nhiều starters vẫn có thể đúng; một WAR thiếu `WEB-INF/lib-provided` có thể đúng nếu nó là plain WAR. Kiểm tra mục tiêu triển khai và plugin trước, sau đó mới đối chiếu classpath.

Ví dụ kiểm đếm entries nếu cần kiểm tra drift của build:

~~~bash
jar tf target/demo-war-0.0.1-SNAPSHOT.war |
  grep -c '^WEB-INF/lib/.*\.jar$'
~~~

Count chỉ có ý nghĩa khi so sánh những lần build cùng dependencies/configuration. Với Boot executable WAR có Tomcat `provided`, hãy **kiểm tra vị trí của Tomcat**, không chỉ tổng lượng JARs.

## 7. Đọc MANIFEST.MF để phân biệt WAR truyền thống và executable WAR

### 7.1. Manifest của executable WAR

Spring Boot plugin sửa manifest để hướng JVM tới Boot Loader. Ở Spring Boot 3.5, các thuộc tính quan trọng thường là:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.DemoWarApplication
Spring-Boot-Version: 3.5.16
~~~

Đây là **trích minh họa những thuộc tính có liên quan**, không phải lời khẳng định output của mọi project chỉ có đúng bốn dòng. Manifest thực có thể còn các mục khác hoặc một số mục tùy cấu hình.

Giải thích:

- `Main-Class`: Java launcher sẽ gọi `WarLauncher`, không gọi trực tiếp application `main`.
- `Start-Class`: Boot Loader gọi class chứa `main(String[] args)`.
- `Spring-Boot-Version`: có thể giúp nhận diện release plugin/loader, không thay thế dependency tree.
- Các dòng manifest có quy tắc line wrapping; **đừng parser manifest bằng giả định mỗi giá trị không bao giờ xuống dòng**.

### 7.2. Xem manifest bằng unzip nếu đã có

~~~bash
unzip -p target/demo-war-0.0.1-SNAPSHOT.war META-INF/MANIFEST.MF
~~~

`unzip -p` xuất nội dung file từ archive ra stdout, không sửa WAR. Trên Windows, nếu `unzip` không cài sẵn, mở file WAR bằng một công cụ ZIP và xem `META-INF/MANIFEST.MF` ở chế độ chỉ đọc; hoặc dùng `jar xf` vào **thư mục tạm riêng** (lưu ý extraction tạo file trên disk), tránh tự đóng gói lại artifact sản phẩm.

### 7.3. Manifest không phải cơ chế khởi động external container

External Tomcat không chọn class `Start-Class` theo manifest rồi chạy `public static void main`. Nó dùng Servlet container webapp startup, nhận `WEB-INF/classes`/`WEB-INF/lib` và Spring initializer.

Vì vậy **manifest đúng chưa đủ** để xác nhận WAR deploy được. Ngược lại, **initializer đúng chưa đủ** để xác nhận WAR chạy `java -jar` nếu Spring Boot Loader hoặc các embedded dependencies đã bị loại.

## 8. Cấu hình Gradle tạo cùng kiểu executable WAR

### 8.1. Plugin war và Spring Boot bootWar

Trong Gradle, plugin `war` tạo hỗ trợ WAR và configuration `providedRuntime`. Spring Boot Gradle Plugin nhận diện `war` và tạo task **`bootWar`** để đóng gói executable WAR.

Theo tài liệu Spring Boot, nên dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

`providedRuntime` tốt hơn `compileOnly` cho Tomcat embedded vì `compileOnly` không nằm trên test classpath, có thể làm những web integration tests fail. Đây là **configuration Gradle**, không phải tên scope Maven. Với Maven dùng `<scope>provided</scope>`.

### 8.2. build.gradle hoàn chỉnh (Groovy DSL)

Dùng Java source và `application.properties` ở mục 5 (cùng đường dẫn package), tạo project Gradle riêng `demo-war-gradle/`:

~~~groovy
plugins {
    id 'java'
    id 'war'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Spring Boot plugin phối hợp `io.spring.dependency-management` để import BOM cho phiên bản Boot plugin; vì vậy các Spring Boot starters không cần gắn version riêng. Dùng Gradle version tương thích **cả Boot 3.5 plugin và dependency-management plugin**; Gradle Wrapper nên do project kiểm soát. Trong ví dụ này `bootWar` xuất executable WAR, còn task `war` có thể tạo plain WAR riêng với classifier tùy convention của plugin.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'demo-war'
~~~

**Lưu ý:** project Maven và Gradle là **hai build variants minh họa**. Bạn có thể sử dụng cùng Java sources nhưng không nên chạy hai build tools trên một cây thư mục rồi trộn artifacts từ `target/` và `build/libs/` khi chưa xác định nguồn phát hành.

### 8.3. Build và chạy Gradle

Khi project có Gradle Wrapper:

~~~bash
./gradlew clean bootWar
java -jar build/libs/demo-war-0.0.1-SNAPSHOT.war
jar tf build/libs/demo-war-0.0.1-SNAPSHOT.war
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootWar
java -jar .\build\libs\demo-war-0.0.1-SNAPSHOT.war
jar tf .\build\libs\demo-war-0.0.1-SNAPSHOT.war
~~~

Nếu chỉ cài Gradle ngoài, dùng `gradle clean bootWar` và bảo đảm version phù hợp. **Kiểm tra tên file thật trong `build/libs/`** nếu project đặt archiveBaseName/classifier/custom version khác.

Tìm các entries:

~~~text
WEB-INF/classes/com/example/war/DemoWarApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/lib/spring-webmvc-*.jar
WEB-INF/lib-provided/tomcat-embed-core-*.jar
org/springframework/boot/loader/launch/WarLauncher.class
~~~

Nếu dùng task `war` thay vì `bootWar`, artifact thường theo **plain WAR** layout và có thể không có Boot Loader hoặc `WEB-INF/lib-provided`. Đừng so hai task mà giả định output của chúng giống nhau.

### 8.4. Groovy vs Kotlin DSL: snippet tương đương

Đây là **đoạn `build.gradle.kts`**, không phải file hoàn chỉnh, nhưng đủ để thấy khai báo dependency:

~~~kotlin
plugins {
    java
    war
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Phần còn lại như repositories, group/version, toolchain, test task phải được đặt theo project tương ứng. Trong code Kotlin DSL, `providedRuntime(...)` chỉ có sau khi plugin `war` tạo configuration.

## 9. Từ scope/configuration đến đường dẫn WAR

### 9.1. Maven dependency scopes

Trong Maven, hai vùng classpath cần xét:

- **External container runtime classpath:** lấy app classes, WAR `WEB-INF/lib` và libraries mà container tự cung cấp.
- **Executable WAR runtime classpath:** Boot WarLauncher thêm `WEB-INF/lib-provided` vào app classloader.

| Maven scope của dependency | Khi compile code | Khi tests chạy | Vị trí điển hình trong Boot executable WAR | Ghi chú |
| --- | --- | --- | --- | --- |
| `compile` | Có | Có | `WEB-INF/lib` | Dependencies dùng runtime webapp |
| `runtime` | Không nhất thiết có ở compile trực tiếp | Có | `WEB-INF/lib` | Ví dụ driver chỉ cần khi chạy |
| `provided` | Có | Có | `WEB-INF/lib-provided` | Dự kiến external container cung cấp |
| `test` | Không có ở main compile | Có | Không đóng vào WAR runtime | JUnit, Mockito và test utilities |

Đây là **placement thường gặp với Spring Boot Maven Plugin `repackage` và layout WAR**. Nếu project có exclusions, custom plugin configuration, system/optional scope, hoặc plugin khác can thiệp, cần kiểm artifact thực tế. **Đừng suy placement từ scope mà không biết loại archive đang đọc.**

### 9.2. Gradle configurations

| Gradle | Mục đích trong project Boot WAR | Placement khi `bootWar` |
| --- | --- | --- |
| `implementation` | Dependencies ứng dụng | Thường `WEB-INF/lib` |
| `runtimeOnly` | Dependencies cần lúc chạy | Thường `WEB-INF/lib` |
| `providedRuntime` | Thư viện external container sẽ cung cấp | `WEB-INF/lib-provided` |
| `testImplementation`/`testRuntimeOnly` | Tests | Không thuộc WAR runtime |
| `compileOnly` | Chỉ compile | Không nên dùng thay `providedRuntime` cho embedded Tomcat cần ở test |

**Giải thích một tình huống:** `spring-boot-starter-web` phụ thuộc Tomcat starter bắc cầu; thêm `providedRuntime 'spring-boot-starter-tomcat'` giúp WAR plugin phân biệt Tomcat embedded khỏi web application libraries. Bạn cần kiểm nghiệm `bootWar` output, vì Gradle có cơ chế dependency configurations/resolution riêng, không nên lập luận từ tên artifact là đủ.

### 9.3. Đừng chuyển mọi thư viện thành provided

Chỉ vì một external container cung cấp **Servlet API và engine** không có nghĩa nó cung cấp Spring Framework, Jackson, database driver hoặc code business. Nếu bạn đánh dấu `spring-boot-starter-web` là provided và loại nó khỏi `WEB-INF/lib` mà external server không có Spring Web, application sẽ thiếu classes khi triển khai.

Một nguyên tắc thực tế:

- Servlet engine / servlet API do external server chịu trách nhiệm: **provided** theo contract deploy.
- Các libraries ứng dụng không được external container cung cấp: đóng ở `WEB-INF/lib`.
- Dependencies dành cho tests: không đóng vào runtime WAR.
- Driver JNDI hoặc shared library thật sự do server cung cấp: chỉ đánh dấu provided khi **đã có tài liệu vận hành xác nhận** và được kiểm thử; đừng phỏng đoán.

## 10. Triển khai WAR vào external servlet container

### 10.1. Chọn container tương thích với Spring Boot

Spring Boot 3.x sử dụng **Jakarta Servlet** APIs (`jakarta.servlet.*`), thay vì `javax.servlet.*` của Spring Boot 2.x và servlet containers thế hệ cũ. Vì thế, một WAR Boot 3.5 không thể được coi là tương thích với Tomcat 9 chỉ vì cả hai đều gọi là “Servlet container”.

Chọn Tomcat/Jetty/server có version và Jakarta Servlet compatibility mà release Boot đang dùng hỗ trợ; với ví dụ Boot 3.5, **Tomcat 10.1** là hướng lựa chọn tương ứng với embedded Tomcat dòng 10.1. Trong production, đối chiếu bảng system requirements, tiêu chuẩn tổ chức, JVM/Jakarta version và các servlet features/framework libraries sử dụng trước khi deploy.

### 10.2. Đặt file WAR vào Tomcat

Ví dụ giả định bạn quản lý một Tomcat local, có `CATALINA_BASE` riêng, đang chạy và cấu hình auto-deploy. Sao chép file `target/demo-war-0.0.1-SNAPSHOT.war` tới thư mục webapps:

~~~bash
cp target/demo-war-0.0.1-SNAPSHOT.war \
  "$CATALINA_BASE/webapps/demo-war.war"
~~~

Đây là **ví dụ trên hệ POSIX**, giả định biến `CATALINA_BASE` tồn tại và bạn có quyền deploy; nó không tự khởi động Tomcat. Cần bảo đảm các test/services ngoài WAR cũng đang sẵn sàng nếu app phụ thuộc.

Nếu WAR đặt tên `demo-war.war`, Tomcat mặc định có thể deploy dưới context path `/demo-war` khi auto-deploy và cấu hình container thông thường được bật. Khi đó endpoint ví dụ là:

~~~bash
curl -s http://localhost:8080/demo-war/hello
~~~

Kỳ vọng response body:

~~~text
WAR_OK
~~~

**Cảnh báo:** `/demo-war` và port 8080 là **giả định cấu hình mặc định** của Tomcat minh họa, không phải giá trị được Spring Boot đóng gói cố định. Nếu operator cấu hình context path khác, host/vhost khác, port khác hoặc đặt WAR thành `ROOT.war`, URL thực tế thay đổi.

### 10.3. Vì sao Tomcat ngoài không nạp lib-provided?

Container chỉ nạp các vị trí WAR classpath chuẩn (`WEB-INF/classes` và `WEB-INF/lib/*.jar`), cộng libraries do nó cung cấp. `WEB-INF/lib-provided` không phải nơi Servlet spec yêu cầu quét JARs làm application library. Vì vậy:

- Tomcat **ngoài** dùng Tomcat/Jakarta Servlet implementation của chính server.
- Spring Framework và business libraries vẫn đến từ WAR `WEB-INF/lib`.
- Tomcat embedded trong `WEB-INF/lib-provided` không được webapp classloader nạp như một dependency `WEB-INF/lib`.
- WAR vẫn có thể chứa `WarLauncher` ở root; nó không thay thế external container bootstrap flow.

Đây là **ý nghĩa thiết kế chính** của executable WAR Spring Boot. Không nên cố ép external Tomcat nạp `WEB-INF/lib-provided` để “đầy đủ dependency” — thao tác đó có thể đưa Tomcat embedded/Jakarta APIs trùng với container engine vào webapp classloader.

### 10.4. Các trường hợp không phù hợp WAR

Spring Boot WebFlux dựa trên Reactor Netty không hỗ trợ traditional servlet WAR deployment theo cách Spring MVC Servlet application. Nếu ứng dụng là reactive-first WebFlux, không chuyển `packaging` từ JAR sang WAR và hy vọng external Tomcat nạp Boot như servlet app thông thường.

Trước khi chọn WAR, hỏi: **môi trường vận hành có yêu cầu external servlet container không?** Nếu không, executable Spring Boot JAR là lựa chọn thông dụng, dễ triển khai độc lập hơn. WAR phù hợp khi có yêu cầu ứng dụng chạy trong container được quản trị tập trung hoặc phải tương thích mô hình hạ tầng hiện tại.

## 11. Một WAR có thể vừa là file thực thi vừa được deploy: giới hạn cần nhớ

### 11.1. Điều gì không giống nhau giữa hai lần chạy?

Cùng Java controller nhưng hai chế độ có thể khác:

| Khía cạnh | `java -jar` | WAR trong external Tomcat |
| --- | --- | --- |
| HTTP port | Embedded Tomcat theo Spring config, ví dụ 8080 | External Tomcat Connector config |
| Context path | Thường root `/` khi không cấu hình | Thường theo WAR name/Host config |
| Servlet engine | Từ `WEB-INF/lib-provided` | Tomcat/Jakarta libraries do server quản lý |
| Classpath | Boot WarLauncher nạp cả `lib` lẫn `lib-provided` | Container nạp `classes` + `lib` theo quy tắc |
| Spring startup | `main` qua `Start-Class` | `SpringBootServletInitializer` qua Servlet integration |
| JVM options | Lệnh `java -jar`/process runner | Java process đang chạy external Tomcat |
| Environment / file paths | Theo cwd và env của app process | Theo env và cwd của Tomcat process |
| Logging/shared libraries | Theo embedded app/classpath | Có thể chịu ảnh hưởng server/shared classloader |

Vì vậy **“chạy được bằng java -jar” chưa chứng minh “deploy vào external Tomcat cũng chạy”** và ngược lại. Cần test cả hai nếu doanh nghiệp hứa hỗ trợ cả hai modes.

### 11.2. Tại sao Boot WAR không chỉ là ZIP bình thường?

Spring Boot executable WAR có Boot Loader code và nested dependencies. Các nested JAR entries cần được viết theo layout/ZIP method mà Boot Loader có thể đọc. Nếu bạn giải nén rồi nén lại WAR bằng script không bảo đảm layout/manifest/entry methods, `java -jar` có thể hỏng dù container ngoài vẫn chấp nhận WAR.

Dùng Spring Boot Maven Plugin `repackage` hoặc Gradle `bootWar` để sinh executable WAR; không tự đưa vào JAR root các file `spring-boot-loader` rồi hy vọng lớp bootstrap hoạt động.

### 11.3. WAR executable không phải library JAR

Trong WAR, classes của ứng dụng ở `WEB-INF/classes` chứ không phải root package path `com/example/war/*.class`. Vì vậy không nên dùng WAR làm dependency thay cho module library JAR của project khác. Tách shared code thành module Java library hoặc publish artifact đúng mục đích.

## 12. Phân biệt plain WAR và Boot executable WAR

Một số project chỉ có Maven `maven-war-plugin` hoặc Gradle `war` mà **không** chạy Boot `repackage`/`bootWar`. Khi đó:

- `WEB-INF/classes`: vẫn có app classes.
- `WEB-INF/lib`: vẫn có libraries đóng gói.
- `WEB-INF/lib-provided`: có thể **không tồn tại**.
- Root `org/springframework/boot/loader/...`: có thể **không có**.
- Manifest `Main-Class: WarLauncher`: **không được bảo đảm**.
- `java -jar plain.war`: thường không chạy đúng vì không có Boot entrypoint/embedded libs được đóng gói.

**Plain WAR không nhất thiết là artifact lỗi.** Nếu nó được thiết kế để deploy lên container ngoài và test theo contract đó, việc thiếu `lib-provided` là bình thường. Kết luận đúng cần căn cứ yêu cầu deployment, build task/goal và output artifact cụ thể.

### 12.1. Maven output khi dùng repackage

Với `spring-boot-maven-plugin:repackage`, plugin có thể **thay artifact WAR gốc** bằng executable WAR; bản gốc non-executable thường được lưu bên cạnh với hậu tố `.original` theo mặc định. Nếu dùng classifier riêng, output khác. Không mặc định có hai WAR với cùng cấu trúc và cùng đường dẫn.

Kiểm tra chính xác file do CI publish/deploy, không chỉ lấy file mới nhất trong `target`. Artifact mang hậu tố `.original` có thể là plain WAR và không có `lib-provided` như executable WAR.

### 12.2. Gradle output khi có war và bootWar

Spring Boot Gradle plugin có thể tạo `bootWar` executable artifact và `war` plain artifact (thường có classifier `plain` theo convention của các dòng Boot 3.x). Đừng lấy `*-plain.war` rồi yêu cầu nó chạy bằng `java -jar` nếu chưa cấu hình executable manifest/loader. Hãy đặt tên/classifier rõ ràng trong CI và chạy smoke tests trên đúng file để phát hành.

## 13. Lỗi điển hình và cách sửa

| Dấu hiệu | Cơ chế gây lỗi | Chẩn đoán và hướng xử lý |
| --- | --- | --- |
| `java -jar app.war` báo `no main manifest attribute` | Đang chạy plain WAR, thiếu Boot repackage/bootWar | Đọc manifest, xác minh build goal và artifact đúng |
| WAR có `WEB-INF/classes` nhưng không có `WEB-INF/lib-provided` | Không có provided dependencies hoặc artifact plain WAR | Xem mục tiêu deploy, Maven scopes/Gradle configurations, Boot plugin execution |
| `java -jar` báo thiếu Tomcat/Servlet classes | Tomcat embedded bị loại hoặc không ở lib-provided | Kiểm tra `WEB-INF/lib-provided`, dependency graph và plugin excludes |
| Deploy external Tomcat báo duplicate Servlet/Servlet API class | Embedded servlet container bị đóng vào `WEB-INF/lib` hoặc server/library không tương thích | Đánh dấu Tomcat provided/providedRuntime, kiểm artifact thật, so server version |
| `ClassNotFoundException: jakarta.servlet...` | Servlet container quá cũ hoặc dependency scope/classpath sai | Dùng Jakarta-compatible container được Boot line hỗ trợ, xem lib placement |
| `NoClassDefFoundError: org.springframework...` trên container ngoài | Spring libs bị đặt provided nhầm hoặc bị exclusions | Đưa dependencies ứng dụng vào `WEB-INF/lib`, không giả định external Tomcat cung cấp Spring |
| `@RestController` trả 404 sau deploy | Context path của WAR khác root, bootstrap/config sai | Thử `/<war-name>/hello`, kiểm deployment logs và initializer |
| HTTP 404 dù `java -jar` chạy được | External Servlet initializer không khởi tạo app đúng hoặc context path sai | Kiểm extends `SpringBootServletInitializer`/`configure` và Tomcat context |
| Port `server.port=8080` không có tác dụng trong external Tomcat | Cổng do external connector quản lý | Sửa Tomcat server config/URL, không đổi application.properties để điều khiển external server |
| `jar tf` thấy nhiều `tomcat-embed-*.jar` trong `WEB-INF/lib` | Maven/Gradle dependency scope không được đánh dấu đúng | Xem compile/transitive dependency, direct provided/providedRuntime, clean build |
| Gradle `bootWar` không tồn tại | Không áp dụng plugin `war` hoặc Boot plugin | Kiểm plugins, `./gradlew tasks` và Gradle version |
| Gradle compileOnly Tomcat gây test failure | `compileOnly` không có ở test classpath | Dùng `providedRuntime` theo Spring Boot guide |
| Maven `repackage` không chạy | Không kế thừa Boot parent, chưa bind goal, hoặc plugin không được khai báo | Khai báo plugin version + execution trong parent riêng/child |
| Manifest vẫn là `JarLauncher` trong file `.war` | Đóng nhầm task/layout JAR hoặc custom plugin sửa manifest | Xem Spring Boot packaging/layout, output tasks, không tự override manifest ở sai plugin |
| Một JAR Tomcat xuất hiện ở cả `lib` và `lib-provided` | Dependency conflicts/custom package, duplicate entries | Đọc `jar tf` và effective dependency graph, loại khai báo gây trùng |
| External WAR deploy lỗi `javax.servlet`/`jakarta.servlet` | Trộn Spring Boot 2.x/3.x và servlet container generations | Kiểm compatibility matrix và migrate import namespaces |
| App chạy nhưng tài nguyên `application.properties` không được thấy | Resources không được đưa vào `WEB-INF/classes` hoặc config bị override | Kiểm file trong WAR và Spring property sources/external config |
| `WEB-INF/lib-provided` được server ngoài tự thêm vào app classpath | Server có custom scan/classloader ngoài quy ước hoặc script deploy sai | Loại custom path này, để container dùng implementation của nó |

### 13.1. Phương pháp debug theo thứ tự

**Bước 1 — Xác định file:** tên artifact và đường dẫn đúng từ Maven/Gradle/CI; phân biệt WAR executable vs plain WAR.

**Bước 2 — Đọc layout:** `jar tf`, kiểm ba thư mục `classes`/`lib`/`lib-provided` và Boot Loader.

**Bước 3 — Đọc manifest:** `Main-Class` là `WarLauncher`? `Start-Class` là main class? Nếu không, có thể đang cầm plain WAR hoặc build sai.

**Bước 4 — Đọc dependency graph:** Maven `dependency:tree`/`help:effective-pom` hoặc Gradle `dependencies`/`dependencyInsight`, kiểm Tomcat starter scope/configuration.

**Bước 5 — Chạy kiểm chứng hai mode:** `java -jar` và external Tomcat (nếu project hỗ trợ cả hai); so port, context path, logs.

**Bước 6 — Chỉ sửa nguyên nhân:** scope, plugin/task hoặc container compatibility; không xóa ngẫu nhiên Tomcat JAR để giảm kích thước rồi phá executable mode.

## 14. Một bài tập phân tích bằng đường dẫn giả lập

Giả sử một WAR có những entries:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/DemoWarApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/lib/spring-context-6.x.y.jar
WEB-INF/lib/spring-webmvc-6.x.y.jar
WEB-INF/lib-provided/tomcat-embed-core-10.x.y.jar
WEB-INF/lib-provided/tomcat-embed-el-10.x.y.jar
~~~

Hãy trả lời:

**Câu A:** Application classloader của **external servlet container** tìm `HelloController.class` ở đâu?  
**Đáp án:** `WEB-INF/classes/com/example/war/HelloController.class`, coi `WEB-INF/classes` là classpath root.

**Câu B:** Spring WebMVC JAR nằm ở đâu để external container dùng?  
**Đáp án:** `WEB-INF/lib/spring-webmvc-6.x.y.jar`, nơi WAR webapp libraries được container nạp.

**Câu C:** Vì sao `tomcat-embed-core` trong `lib-provided` không gây hai Tomcat engines khi deploy ngoài?  
**Đáp án:** `WEB-INF/lib-provided` không phải webapp library classpath chuẩn mà external container quét; Tomcat ngoài dùng engine của nó.

**Câu D:** Vì sao cùng file WAR có thể chạy `java -jar`?  
**Đáp án:** Spring Boot `WarLauncher` tạo classloader gồm `WEB-INF/classes`, `WEB-INF/lib`, **và** `WEB-INF/lib-provided`; Tomcat embedded có mặt khi chạy độc lập.

**Câu E:** Có phải mọi WAR đều có `WEB-INF/lib-provided`?  
**Đáp án:** Không. Đây là directory phục vụ executable WAR của Boot khi có provided dependencies; plain WAR có thể hoàn toàn không có.

**Câu F:** Có thể gỡ `WEB-INF/lib-provided` rồi deploy được ngoài không?  
**Đáp án:** Có thể plain external deployment vẫn hoạt động nếu mọi yêu cầu khác đúng, nhưng executable `java -jar` có thể bị phá. Không chỉnh sửa nội dung đã package thủ công khi chưa xác định artifact contract.

**Câu G:** `Main-Class=WarLauncher` có làm Tomcat ngoài gọi `main` không?  
**Đáp án:** Không. Tomcat ngoài dùng Servlet bootstrap và initializer, không dùng Java launcher manifest theo cách `java -jar`.

## 15. Bài tập thực hành với project mẫu

### Bài 1 — Nhận diện archive

Tạo Maven project ở mục 5, chạy `mvn clean package`. Dùng `jar tf` tìm:
- `WEB-INF/classes/com/example/war/DemoWarApplication.class`;
- `WEB-INF/lib/` với các Spring dependencies;
- `WEB-INF/lib-provided/` với Tomcat embedded dependencies.

Ghi lại file Tomcat thực tế và version (không chép tên giả lập). Giải thích từng file sẽ được nạp ở mode nào.

### Bài 2 — So sánh manifest

Đọc `META-INF/MANIFEST.MF`. Xác định `Main-Class` và `Start-Class`. Trả lời vì sao `Main-Class` là `WarLauncher` chứ không trỏ trực tiếp vào `DemoWarApplication`.

### Bài 3 — Kiểm tra URL theo deployment mode

Chạy executable WAR rồi gọi `http://localhost:8080/hello`. Sau đó deploy cùng WAR lên Tomcat ngoài ở tên `demo-war.war` và gọi `http://localhost:8080/demo-war/hello` theo cấu hình thông thường. Ghi nhận rằng response body là `WAR_OK` nhưng URL context path không bắt buộc giống nhau.

### Bài 4 — Sai scope

Trong bản sao project chỉ dùng để thí nghiệm, bỏ `<scope>provided</scope>` khỏi dependency starter Tomcat, clean package và kiểm tra các Tomcat JAR được đóng vào directory nào. Không triển khai phiên bản lỗi lên Tomcat ngoài. Khôi phục scope và build lại, so sánh `jar tf`.

### Bài 5 — Gradle providedRuntime

Tạo Gradle variant với `war` và Spring Boot plugin, `implementation starter-web` + `providedRuntime starter-tomcat`, gọi `bootWar`. Đọc output và so sánh ba vị trí quan trọng với Maven output.

### Bài 6 — CI check

Viết một kiểm tra smoke tại pipeline của **chính project** để báo lỗi khi một executable WAR đáng lẽ có `WarLauncher`, `WEB-INF/classes` hoặc `WEB-INF/lib-provided` mà lại không có. Không áp dụng tiêu chí này cho plain WAR; artifact contract phải được định nghĩa trước.

## 16. Checklist trước khi phát hành WAR

- [ ] Đã xác định mục tiêu: chỉ deploy external container, chỉ `java -jar` hay hỗ trợ cả hai.
- [ ] Nếu triển khai ngoài: ứng dụng Servlet tương thích với version Jakarta/container.
- [ ] `<packaging>war</packaging>` hoặc Gradle `war` plugin được cấu hình đúng.
- [ ] Với executable WAR: có Spring Boot `repackage` hoặc `bootWar`, không chỉ plain `war`.
- [ ] `WEB-INF/classes` chứa application classes và resources thực sự cần.
- [ ] `WEB-INF/lib` chứa Spring MVC/Jackson/business runtime libraries, không nhầm thành `lib-provided`.
- [ ] Embedded servlet container được đánh dấu Maven `provided` hoặc Gradle `providedRuntime` theo thiết kế.
- [ ] `WEB-INF/lib-provided` chứa provided dependencies cần cho `java -jar`, không nằm sai trong `WEB-INF/lib`.
- [ ] Đã kiểm `Main-Class=WarLauncher` và `Start-Class` của executable archive.
- [ ] Main class hỗ trợ cả `main` và `SpringBootServletInitializer` nếu phải chạy hai chế độ.
- [ ] Đã chạy `jar tf`, dependency tree và test HTTP trên đúng artifact sẽ phát hành.
- [ ] Khi deploy external, đã xác minh port/context path là của server ngoài.
- [ ] Không đánh dấu toàn bộ Spring libraries là provided khi external server không cung cấp chúng.
- [ ] Không trộn Spring Boot 3.x Jakarta API với servlet container thế hệ `javax.servlet.*`.
- [ ] Không lưu secrets vào embedded `application.properties` hoặc trông chờ manifest là biện pháp bảo mật.
- [ ] Biết `WEB-INF/lib-provided` có thể vắng mặt hoàn toàn trong plain WAR mà không phải lỗi.

## 17. Tài liệu chính thức để đối chiếu

- Spring Boot 3.5 — Nested JARs và executable WAR structure: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Launching Executable JARs/WARs (WarLauncher): https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html
- Spring Boot 3.5 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Traditional Deployment: https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html
- Spring Boot 3.5 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/reference/getting-started/system-requirements.html
- Spring Boot 3.5 — SpringBootServletInitializer API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html
- Spring Boot 3.5 — BootWar API, providedClasspath: https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootWar.html
- Maven WAR Plugin: https://maven.apache.org/plugins/maven-war-plugin/
- Gradle WAR Plugin: https://docs.gradle.org/current/userguide/war_plugin.html

**Kết luận:** Hãy đọc Spring Boot WAR theo đúng ba vùng: **`WEB-INF/classes` = code/resources của ứng dụng**, **`WEB-INF/lib` = runtime libraries của webapp khi chạy trong external container**, **`WEB-INF/lib-provided` = dependencies do external container được kỳ vọng cung cấp nhưng Boot Loader giữ lại cho `java -jar`**. Cơ chế này cho phép **một executable WAR** đáp ứng hai đường triển khai nếu có bootstrap và dependencies phù hợp. Trước khi đánh giá “đúng/sai”, hãy xác định WAR đó là **plain hay executable**, đọc manifest, inspect archive bằng `jar tf` và smoke-test đường chạy mà sản phẩm thực sự hỗ trợ.