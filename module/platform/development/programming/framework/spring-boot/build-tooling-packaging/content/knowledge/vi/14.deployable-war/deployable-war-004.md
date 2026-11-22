# Tạo WAR bằng Gradle `war` và `bootWar` trong Spring Boot

Khi triển khai ứng dụng Spring Boot theo mô hình **WAR**, bạn thường gặp hai task có tên gần giống nhau:

- **`war`** do **Gradle War plugin** cung cấp: tạo WAR truyền thống, phù hợp để triển khai vào servlet container bên ngoài như Apache Tomcat.
- **`bootWar`** do **Spring Boot Gradle plugin** cung cấp khi áp dụng War plugin: tạo **executable Spring Boot WAR**, có launcher và nested dependencies để có thể chạy bằng `java -jar`; khi cấu hình servlet container dependency phù hợp, chính WAR đó còn có thể được triển khai vào servlet container bên ngoài.

**Không phải task nào tạo file đuôi `.war` cũng tạo cùng một loại artifact.** Muốn biết nên dùng `war` hay `bootWar`, hãy xác định **đường triển khai**: servlet container do môi trường cung cấp hay JVM chạy archive trực tiếp.

Bài này hướng dẫn mô hình dependency, cấu hình Gradle Groovy/Kotlin DSL, một ứng dụng Java 17+ có thể xây cả hai WAR, cách xem cấu trúc archive, kiểm thử, triển khai Tomcat và các lỗi thường gặp.

Các ví dụ cố định **Spring Boot 3.3.5**, **Java 17** và **Gradle 8.7** để có đầu vào cụ thể; đây không phải khẳng định phiên bản mới nhất. Với Spring Boot 3.x cần chú ý API **`jakarta.servlet.*`** thay cho `javax.servlet.*` của thế hệ ứng dụng cũ.

## 1. WAR khác JAR như thế nào?

**JAR (Java ARchive)** thường chứa class, resource và metadata để phân phối module Java. **WAR (Web Application Archive)** là định dạng archive dành cho **web application** có cấu trúc mà servlet container nhận diện.

WAR phổ biến có bố cục:

~~~text
sample.war
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   ├── com/example/war/WarDemoApplication.class
│   │   └── application.properties        (nếu có)
│   ├── lib/
│   │   ├── spring-webmvc-*.jar
│   │   └── các thư viện ứng dụng
│   └── web.xml                          (không bắt buộc với Servlet hiện đại)
└── nội dung từ src/main/webapp/         (nếu có)
~~~

Đây là sơ đồ: tên thư viện thực tế mang số phiên bản, `web.xml` có thể hoàn toàn không tồn tại. Trong dự án Spring Boot hiện đại dùng `SpringBootServletInitializer` và cơ chế khởi tạo bằng code, **không nhất thiết phải có `web.xml`**.

Một executable Spring Boot WAR bổ sung **Spring Boot loader classes**, metadata entry point và có thể chứa:

~~~text
WEB-INF/lib-provided/
    tomcat-embed-core-*.jar
    tomcat-embed-websocket-*.jar
    ...
~~~

Thư viện ở `WEB-INF/lib-provided` dành cho đường chạy **executable** bằng `java -jar`, nhưng không nằm trong `WEB-INF/lib` được servlet container ngoài nạp theo quy ước standard WAR. Đó là cơ chế quan trọng để một archive vừa **tự chạy** vừa **triển khai được** vào Tomcat bên ngoài.

### So sánh nhanh

| Tính chất | Gradle `war` | Spring Boot `bootWar` |
| --- | --- | --- |
| Plugin đăng ký task | `id 'war'` | `id 'org.springframework.boot'` khi có War plugin |
| Kiểu task | `War` | `BootWar` (mở rộng `War`) |
| Output | WAR truyền thống | Executable Spring Boot WAR |
| `WEB-INF/classes` | Có | Có |
| `WEB-INF/lib` | Runtime dependencies, trừ provided dependencies | Thư viện application runtime phù hợp |
| `WEB-INF/lib-provided` | Thường không có | Có nếu khai báo `providedRuntime` cần đóng gói |
| Boot launcher/`Start-Class` | Không phải mặc định của plain WAR | Có trong executable archive tiêu chuẩn |
| `java -jar file.war` | Không phải mục tiêu mặc định | Có thể chạy |
| Deploy vào servlet container ngoài | Có, nếu ứng dụng được cấu hình hợp lệ | Có, nếu có cấu hình servlet phù hợp và xử lý server dependency đúng |

**`bootWar` không có nghĩa “chỉ dùng embedded server”**. Một executable Boot WAR được cấu hình đúng có thể deploy vào container bên ngoài; khác biệt quan trọng là thư viện servlet server nằm ở đâu trong archive.

## 2. Cơ chế của Gradle `war` plugin

Chỉ cần khai báo:

~~~groovy
plugins {
    id 'war'
}
~~~

Gradle War plugin **áp dụng Java plugin**, bổ sung task `war` và các cấu hình dành cho ứng dụng web. Trong trường hợp thông thường:

- `src/main/java` chứa source chính.
- `src/main/resources` chứa classpath resource.
- `src/main/webapp` chứa các file web application root, được đưa vào **root của WAR**.
- Output class Java nằm ở `WEB-INF/classes`.
- Dependencies runtime phù hợp được copy vào `WEB-INF/lib`.
- Các dependency thuộc `providedCompile`/`providedRuntime` được xem là do môi trường triển khai cung cấp nên bị loại khỏi phần thư viện đóng gói theo semantics của War plugin.

Tạo plain WAR:

~~~bash
./gradlew war
~~~

`war` cũng được tích hợp với lifecycle task `assemble` của Gradle, trừ khi dự án tùy chỉnh/disable task. Nếu muốn đảm bảo chạy **chính xác** task cần kiểm tra, gọi tên `war` trực tiếp thay vì suy ra từ việc chạy `build`.

### Cấu hình đường dẫn và tên file

~~~groovy
import org.gradle.api.tasks.bundling.War

tasks.named('war', War) {
    archiveFileName.set('portal-plain.war')
}
~~~

`archiveFileName` là một Property do Gradle cung cấp; tên output không bắt buộc trùng `project.name`. Theo mặc định thư mục đích thường là `build/libs/`, trừ khi đã tùy chỉnh `destinationDirectory`.

Nếu cần file ứng dụng web truyền thống như JSP, HTML hoặc asset ở root archive, có thể đặt dưới `src/main/webapp`. Nếu chỉ là REST API được Spring Boot quản lý, thư mục đó **không bắt buộc**.

## 3. Spring Boot Gradle plugin thêm `bootWar` khi có War plugin

Khi một project áp dụng **Spring Boot Gradle plugin** và **Gradle War plugin**, Boot plugin đăng ký `bootWar` thuộc loại `BootWar`. Nó được nối vào quy trình `assemble`, đồng thời dùng logic đóng gói archive có thể thực thi.

~~~groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

`io.spring.dependency-management` trong ví dụ dùng để quản lý dependency versions theo Spring Boot BOM. Dự án khác có thể dùng **Gradle native platform/BOM** thay thế; không bắt buộc phải dùng cả hai cách cùng lúc.

Tạo executable WAR:

~~~bash
./gradlew bootWar
~~~

Để cấu hình riêng task:

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named('bootWar', BootWar) {
    archiveFileName.set('portal.war')
}
~~~

**`tasks.named` không tạo task mới**; nó lấy một task đã đăng ký, vì vậy chỉ có nghĩa khi các plugin tạo `bootWar` đã được áp dụng trong đúng project. Không đăng ký lại tên `bootWar` bằng `tasks.register`.

### Vì sao có hai file WAR?

Theo mặc định của Spring Boot Gradle plugin, khi `bootWar` và `war` cùng hoạt động, plain `war` thường dùng **archive classifier `plain`** để tránh ghi đè executable archive:

~~~text
build/libs/portal-1.0.0.war
build/libs/portal-1.0.0-plain.war
~~~

Đây là **một quy ước mặc định minh họa**, phụ thuộc `project.name`, `version`, `archiveBaseName`, `archiveClassifier` và cấu hình thực tế. Không đoán WAR nào cần deploy chỉ qua tên file. Kiểm tra bằng `jar tf` và manifest.

Để loại bỏ bất định trong bài thực hành, chúng ta sẽ đặt **hai tên file khác nhau một cách tường minh**: `war-demo.war` và `war-demo-plain.war`.

## 4. `providedRuntime` là điểm mấu chốt để vừa chạy vừa deploy

Một Spring Boot web starter kiểu Servlet thường mang **embedded Tomcat** qua dependency bắc cầu. Nếu triển khai vào **Tomcat bên ngoài**, container bên ngoài **đã cung cấp** servlet engine. Mang thêm embedded Tomcat vào `WEB-INF/lib` có thể dẫn đến trùng classes, conflict hoặc khởi động không như mong muốn.

Với Spring Boot 3.3, cấu hình khuyến nghị:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Ở đây `spring-boot-starter-web` là dependency của ứng dụng; `spring-boot-starter-tomcat` được đánh dấu là **provided at runtime by container**. Đó là pattern được Spring Boot 3.3 công bố cho **executable and deployable WAR**.

**Điều gì xảy ra khi build?**

1. Với **plain `war`**, Gradle War plugin loại provided dependencies và quan hệ bắc cầu liên quan ra khỏi phần WAR runtime libraries. Container ngoài cần cung cấp servlet engine tương thích.
2. Với **`bootWar`**, Spring Boot plugin đưa phần provided runtime được hỗ trợ vào `WEB-INF/lib-provided`. Khi chạy `java -jar`, `WarLauncher` có thể nạp chúng để tự bật embedded Tomcat. Khi deploy ngoài, servlet container không tự thêm `WEB-INF/lib-provided` vào standard web application classpath.
3. Các dependency **thật sự thuộc ứng dụng** vẫn đi vào `WEB-INF/lib` để được cả hai chế độ nhìn thấy theo semantics của WAR.

~~~text
providedRuntime: spring-boot-starter-tomcat
          |
          +-- plain war:
          |    WEB-INF/lib/          (không đem Tomcat provided vào)
          |
          +-- bootWar:
               WEB-INF/lib/          (thư viện application)
               WEB-INF/lib-provided/ (Tomcat provided)
                  |
                  +-- java -jar: WarLauncher nạp lib-provided
                  +-- external Tomcat: không nạp lib-provided như WEB-INF/lib
~~~

### Vì sao không dùng `compileOnly`?

Gradle War plugin có các configuration `providedCompile` và `providedRuntime` với semantics riêng. `compileOnly` chỉ phục vụ compile, **không** tự cung cấp dependency ở runtime/test runtime. Nếu servlet container dependency bị chuyển sang `compileOnly` một cách máy móc, các web tests cần servlet engine có thể thất bại. `providedRuntime` giữ dependency có mặt trong các môi trường runtime/test phù hợp của build, nhưng loại khỏi WAR truyền thống và được `bootWar` xử lý đặc biệt.

**Thận trọng với tính transitive:** `providedRuntime` của Gradle War plugin có thể loại cả dependency bắc cầu khỏi plain WAR. Nếu một thư viện vừa được kéo bởi provided dependency, vừa được ứng dụng cần độc lập ở runtime, phải xem resolved graph và archive thực tế, không giả định mọi module được giữ nguyên.

### Khi không dùng Tomcat?

Nếu ứng dụng dùng Jetty hoặc container khác, phải chọn đúng starter và runtime dependency; không sao chép `spring-boot-starter-tomcat` vào project vốn đã loại Tomcat. Với Servlet WAR cho external container, API/container version và cách quản lý provided vẫn cần nhất quán.

**Lưu ý bối cảnh phiên bản:** Spring Boot 3.3 dùng Jakarta Servlet; Tomcat 10.1 với Servlet 6.0 là lựa chọn minh họa phù hợp. Một WAR Spring Boot 3.x thường không thể triển khai thẳng trên Tomcat 9 dựa trên `javax.servlet.*`.

## 5. Hai đường khởi động và `SpringBootServletInitializer`

### Cách A — chạy executable WAR

~~~bash
java -jar build/libs/war-demo.war
~~~

JVM đọc `META-INF/MANIFEST.MF` rồi gọi Spring Boot `WarLauncher`; launcher thiết lập classpath từ `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` theo layout chuẩn. Sau đó launcher gọi application main class, thường được ghi dưới `Start-Class`.

Manifest của executable WAR ở Spring Boot 3.3 có hai dòng kiểu:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Đây là **các dòng tiêu biểu**; manifest còn có thể chứa metadata khác. Java launcher chỉ hiểu `Main-Class`, còn Boot launcher dùng `Start-Class`.

### Cách B — deploy WAR vào servlet container ngoài

Servlet container như Tomcat ngoài **không bắt đầu bằng lệnh `java -jar` của ứng dụng**. Nó tải WAR trong ngữ cảnh web application của container, tổ chức classpath/web resources rồi dùng cơ chế Servlet initialization để khởi tạo Spring context.

Với Spring Boot, class ứng dụng nên mở rộng `SpringBootServletInitializer` và override `configure`:

~~~java
@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

Đây là **đoạn minh họa**, các imports cần có sẽ xuất hiện ở bài thực hành. Hai con đường được hỗ trợ trong cùng class:

- `main` phục vụ `java -jar` hoặc các lệnh chạy application trực tiếp.
- `configure` phục vụ servlet container bên ngoài khởi tạo application.

Nếu ứng dụng có customizations đặc biệt khi khởi tạo Spring context, hãy bảo đảm cả hai đường có cấu hình tương ứng; không viết một biến thể chỉ trong `main` rồi chờ external container tự nhận.

**`SpringBootServletInitializer` không tạo WAR.** Nó chuẩn bị entry point cho kiểu triển khai servlet. Task `war`/`bootWar` là bước **đóng gói**. Cần phối hợp cả code và build script để external deployment hoạt động.

## 6. Bài thực hành trọn vẹn: cùng project tạo `war` và `bootWar`

Ví dụ là một Spring MVC REST ứng dụng nhỏ. Sau khi build, một WAR dùng để chạy `java -jar`, WAR còn lại phù hợp deployment truyền thống. Code Java 17+ có thể chạy nếu các file, toolchain và dependencies được tạo đúng như bên dưới.

### 6.1. Cấu trúc thư mục

~~~text
war-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/example/war/
                ├── WarDemoApplication.java
                └── HelloController.java
~~~

Không cần `src/main/webapp` hoặc `web.xml` cho REST API đơn giản. Nếu có static webapp resources, Gradle War plugin có thể copy `src/main/webapp` vào root archive.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'war-demo'
~~~

### 6.3. `build.gradle` — đầy đủ, Groovy DSL

~~~groovy
import org.gradle.api.tasks.bundling.War
import org.springframework.boot.gradle.tasks.bundling.BootWar

plugins {
    id 'war'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.war.WarDemoApplication'
}

// Executable Spring Boot WAR: co the dung java -jar.
tasks.named('bootWar', BootWar) {
    archiveFileName.set('war-demo.war')
}

// Plain WAR: trien khai vao servlet container ben ngoai.
tasks.named('war', War) {
    archiveFileName.set('war-demo-plain.war')
}
~~~

**Chú ý:**

- `id 'war'` áp dụng Java plugin và đăng ký task `war`; kết hợp với Spring Boot plugin sẽ có `bootWar`.
- `spring-boot-starter-web` cung cấp Spring MVC và thư viện web.
- `providedRuntime '...starter-tomcat'` tách servlet server ra khỏi standard WAR runtime library set và để `bootWar` xử lý cho executable mode.
- `testImplementation` dùng cho kiểm thử, không đưa JUnit/Mockito vào `WEB-INF/lib` khi đóng gói production.
- `springBoot.mainClass` đặt main application class rõ ràng, tránh lỗi phát hiện main class trong project có nhiều class `main()`.
- `archiveFileName.set(...)` được dùng thay vì phụ thuộc default classifier để xác định chính xác hai artifact trong phần kiểm tra.
- Các chú thích không dấu trong đoạn Groovy chỉ để tăng tính tương thích nếu người học dùng toolchain encoding không thống nhất; tên và logic code thực tế không phụ thuộc các chú thích.

### 6.4. `src/main/java/com/example/war/WarDemoApplication.java`

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

Đây là class Java có package khớp đường dẫn. `SpringBootServletInitializer` là phần phục vụ **external deployment**, còn `main` phục vụ chạy trực tiếp với Boot launcher.

### 6.5. `src/main/java/com/example/war/HelloController.java`

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "HELLO_FROM_WAR";
    }
}
~~~

Class nằm dưới package `com.example.war`, được component scan từ `WarDemoApplication` tìm thấy. Đây là một HTTP GET endpoint không cần database, secret hoặc network bên ngoài. Response body là text:

~~~text
HELLO_FROM_WAR
~~~

Không thêm `@Controller` hoặc return view name; `@RestController` bảo đảm String được ghi vào HTTP response body.

## 7. Tạo cả hai WAR bằng Gradle

Ở project root có Gradle Wrapper tương thích, trên Linux/macOS:

~~~bash
./gradlew clean war bootWar
~~~

Lệnh này trực tiếp yêu cầu cả hai task, tránh phụ thuộc vào việc task `build` bị customize ở một project khác. Khi thành công, theo `archiveFileName` đã đặt:

~~~text
build/libs/war-demo.war
build/libs/war-demo-plain.war
~~~

Nếu build không thành công, không suy ra file từ lần build cũ là artifact mới. Lệnh `clean` giúp tránh nhiễu nhưng có thể xóa các output do task trước đó tạo trong `build/`, vì vậy dùng ở thư mục project thực hành.

Chạy riêng từng task nếu cần:

~~~bash
./gradlew bootWar
./gradlew war
~~~

Để xem những task thực sự được đăng ký:

~~~bash
./gradlew tasks --all
./gradlew help --task war
./gradlew help --task bootWar
~~~

`tasks --all` có thể liệt kê thêm nhiều task do plugins tạo; kết quả phụ thuộc project và Gradle version. Không nhầm **một task có tên `war`** với **một file WAR đã được tạo thành công**.

### `build`, `assemble` và `bootWar`

Theo tích hợp chuẩn của Spring Boot Gradle plugin, `bootWar` được nối vào `assemble`. Gradle War plugin cũng tích hợp `war` vào assemble. Vì vậy `./gradlew build` thường build những archive liên quan, kèm các bước kiểm thử, nhưng pipeline thực tế có thể tắt hoặc đổi task dependencies. Khi bài học cần kiểm tra hai artifact riêng biệt, gọi `war bootWar` rõ ràng là đáng tin cậy hơn.

## 8. So sánh nội dung hai archive bằng công cụ JDK

Lệnh `jar` có trong JDK 17:

~~~bash
jar tf build/libs/war-demo-plain.war
jar tf build/libs/war-demo.war
~~~

Với plain WAR, tìm các entry đại diện:

~~~text
WEB-INF/classes/com/example/war/WarDemoApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/lib/spring-webmvc-<version>.jar
~~~

Đây là **sơ đồ danh sách rút gọn**, không phải stdout đầy đủ: `<version>` đại diện version JAR thật. Phần `WEB-INF/lib-provided` của Boot plugin không phải là cấu trúc do `war` thông thường sinh ra.

Với executable Boot WAR, tìm thêm:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/WarDemoApplication.class
WEB-INF/classes/com/example/war/HelloController.class
WEB-INF/lib/spring-webmvc-<version>.jar
WEB-INF/lib-provided/tomcat-embed-core-<version>.jar
~~~

Danh sách thật có nhiều entry hơn, và tên nested dependencies chứa số version cụ thể. Điều đáng quan tâm là **vị trí servlet container JAR**: ở `lib-provided` của executable WAR, không ở `lib` của plain WAR trong cấu hình chuẩn.

### Vì sao `jar tf` không in class bên trong nested JAR?

`jar tf file.war` liệt kê các entry **của outer archive**, chứ không tự đệ quy duyệt mọi class nằm trong từng `WEB-INF/lib/*.jar`. Một nested JAR là một entry trong WAR. Để điều tra class trong dependency JAR, dùng dependency graph hoặc extract riêng nested JAR bằng công cụ phù hợp.

### Đọc manifest đúng file

Trên Linux/macOS có `unzip`:

~~~bash
unzip -p build/libs/war-demo.war META-INF/MANIFEST.MF
~~~

Trong executable WAR của ví dụ, hai dòng chính được kỳ vọng:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Không đòi manifest chỉ có hai dòng, vì có thể còn metadata phiên bản, index, build info và thông tin archive khác. `jar tf` chỉ liệt kê entry `META-INF/MANIFEST.MF`; nó **không tự in nội dung file**.

Plain WAR thường **không** có launcher Main-Class như executable WAR. Nếu hai manifest giống nhau, cần xác định đang đọc đúng hai file khác nhau, không bị task khác ghi đè, và cấu hình archive đã được áp dụng đúng chưa.

## 9. Java 17 inspector độc lập: phân biệt archive thực tế

Thay vì chỉ nhìn tên file hoặc viết code phụ thuộc shell, có thể dùng Java standard library mở WAR như một JAR/ZIP. Tạo file **`WarInspector.java`** ở một thư mục riêng:

~~~java
import java.io.IOException;
import java.util.Enumeration;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class WarInspector {
    private WarInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java WarInspector <path-to-war>");
            System.exit(2);
        }

        try (JarFile archive = new JarFile(args[0])) {
            Manifest manifest = archive.getManifest();
            Attributes attrs = manifest == null
                    ? null : manifest.getMainAttributes();

            String mainClass = attrs == null
                    ? null : attrs.getValue(Attributes.Name.MAIN_CLASS);
            String startClass = attrs == null
                    ? null : attrs.getValue("Start-Class");

            boolean classes = false;
            boolean provided = false;
            boolean loader = false;

            Enumeration<JarEntry> entries = archive.entries();
            while (entries.hasMoreElements()) {
                String path = entries.nextElement().getName();
                if (path.equals(
                        "WEB-INF/classes/com/example/war/WarDemoApplication.class")) {
                    classes = true;
                }
                if (path.startsWith("WEB-INF/lib-provided/")
                        && path.endsWith(".jar")) {
                    provided = true;
                }
                if (path.equals(
                        "org/springframework/boot/loader/launch/WarLauncher.class")) {
                    loader = true;
                }
            }

            System.out.println("MAIN_CLASS=" + show(mainClass));
            System.out.println("START_CLASS=" + show(startClass));
            System.out.println("APP_CLASS=" + classes);
            System.out.println("HAS_LIB_PROVIDED=" + provided);
            System.out.println("HAS_BOOT_WAR_LAUNCHER=" + loader);
        }
    }

    private static String show(String value) {
        return value == null ? "(absent)" : value;
    }
}
~~~

Đây là chương trình Java 17 độc lập; nó chỉ đọc artifact, không cần Spring Boot dependency.

Biên dịch:

~~~bash
javac WarInspector.java
~~~

Chạy trên **executable WAR của bài thực hành**:

~~~bash
java WarInspector build/libs/war-demo.war
~~~

Kỳ vọng với đúng cấu hình Spring Boot 3.3.5 ở phần trên:

~~~text
MAIN_CLASS=org.springframework.boot.loader.launch.WarLauncher
START_CLASS=com.example.war.WarDemoApplication
APP_CLASS=true
HAS_LIB_PROVIDED=true
HAS_BOOT_WAR_LAUNCHER=true
~~~

Chạy trên plain WAR:

~~~bash
java WarInspector build/libs/war-demo-plain.war
~~~

Dạng kết quả thường gặp với Gradle War plugin chuẩn:

~~~text
MAIN_CLASS=(absent)
START_CLASS=(absent)
APP_CLASS=true
HAS_LIB_PROVIDED=false
HAS_BOOT_WAR_LAUNCHER=false
~~~

Các dòng `MAIN_CLASS`/`START_CLASS` của plain WAR có thể khác nếu bạn tự cấu hình manifest; vì vậy inspector cho biết **giá trị thực** chứ không hard-code rằng tất cả plain WAR trên đời đều thiếu manifest. Số lượng và vị trí các dependency JAR cũng phụ thuộc resolved configuration/packaging options.

Chương trình dùng `JarFile` đọc **outer WAR**; nó không tự đệ quy vào mọi nested JAR. Với bài tập này, kiểm tra entry layout là đủ.

## 10. Chạy executable WAR bằng `java -jar`

Sau khi tạo `build/libs/war-demo.war`:

~~~bash
java -jar build/libs/war-demo.war --server.port=8081
~~~

Spring Boot `WarLauncher` sẽ thiết lập classpath gồm ứng dụng, các thư viện trong `WEB-INF/lib` và provided runtime libraries trong `WEB-INF/lib-provided`, cho phép khởi động embedded Tomcat. `WarDemoApplication.main` được gọi, rồi embedded server chạy tại port 8081 nếu port rảnh.

Dùng terminal khác kiểm tra:

~~~bash
curl -fsS http://localhost:8081/api/hello
~~~

Nội dung HTTP response body:

~~~text
HELLO_FROM_WAR
~~~

Không coi các dòng Spring Boot startup logs là stdout cố định. Thời gian khởi động, PID và banner/log messages phụ thuộc môi trường. `curl -fsS` có thể không tự thêm newline vào terminal; body logic là chuỗi trên.

Dừng ứng dụng bằng Ctrl+C. Nếu port 8081 đang được ứng dụng khác dùng, chọn cổng khác bằng `--server.port` và chỉnh URL test tương ứng.

**Không dùng plain WAR trong lệnh này như thể nó là executable archive:**

~~~bash
java -jar build/libs/war-demo-plain.war
~~~

Với plain WAR mặc định, Java launcher thường báo thiếu main manifest attribute hoặc không có entry point chạy được bằng `-jar`. Đó **không có nghĩa** plain WAR bị lỗi: mục tiêu của nó là được servlet container bên ngoài triển khai.

## 11. Triển khai WAR vào Tomcat bên ngoài

Với Spring Boot 3.3, sử dụng external servlet container tương thích Jakarta Servlet, ví dụ **Apache Tomcat 10.1**. Tomcat 9 dùng họ `javax.servlet.*` nên không phải đích triển khai trực tiếp phù hợp cho Spring Boot 3.x.

Một quy trình thủ công thường dùng trong môi trường thực hành:

1. Cài đặt JDK 17+ và một Tomcat 10.1 tương thích.
2. Xác định Tomcat instance đang dùng (đúng `CATALINA_BASE`, deployment directory và port).
3. Copy plain WAR đã build vào thư mục deploy, thường là `webapps/` của Tomcat instance đó.
4. Khởi động hoặc yêu cầu Tomcat deploy ứng dụng theo quy trình của server.
5. Đọc Tomcat logs để biết WAR đã deploy thành công và context path thực tế.

Ví dụ trên Linux/macOS, với một Tomcat local chưa có deployment trùng tên:

~~~bash
cp build/libs/war-demo-plain.war /opt/tomcat/webapps/war-demo.war
~~~

**Đường dẫn `/opt/tomcat/webapps` là minh họa**, cần thay bằng deployment directory của Tomcat thực tế. Không copy trực tiếp vào production server nếu chưa có quyền hoặc chưa xác nhận deploy pipeline; với hệ thống có manager/CI/CD, dùng cơ chế deploy được tổ chức hỗ trợ.

Nếu Tomcat deploy WAR thành context path `/war-demo`, endpoint có thể được truy cập:

~~~bash
curl -fsS http://localhost:8080/war-demo/api/hello
~~~

Response body mong đợi:

~~~text
HELLO_FROM_WAR
~~~

**Context path là điểm dễ nhầm:**

- Khi chạy executable WAR bằng `java -jar`, Boot app thường ở root context `/`, nên route là `/api/hello` nếu không đổi `server.servlet.context-path`.
- Khi deploy WAR dưới tên `war-demo.war` vào Tomcat, context thường là `/war-demo`, nên route thành `/war-demo/api/hello`.
- Nếu Tomcat được cấu hình một context khác, hostname, port hay reverse proxy, đường dẫn thực tế cũng khác. Đừng kết luận lỗi dependency chỉ vì nhận 404 ở URL sai context.

Với mục đích deploy ngoài, WAR **`war-demo.war` tạo bởi `bootWar`** cũng có thể được container tương thích triển khai nếu giữ nguyên `SpringBootServletInitializer` và provided dependency semantics. Trong bài này ta dùng plain `war-demo-plain.war` để thể hiện rõ hai task, không vì executable WAR bắt buộc chỉ chạy embedded mode.

### Tại sao `SpringBootServletInitializer` quan trọng?

Trong external container, không có thao tác gọi `public static void main` của application như đường `java -jar`. `SpringBootServletInitializer` tham gia cơ chế servlet startup và cấu hình nguồn cho Spring application context.

Nếu project chỉ có `main` mà không có servlet initializer phù hợp, một WAR dù có các class và dependency vẫn có thể không khởi tạo Spring web application khi được deploy ngoài. Khi gặp lỗi này, sửa entry point/initializer trước khi chỉnh classifier của archive.

## 12. Cách quản lý `war` và `bootWar` trong dự án thực tế

### Dùng tên artifact rõ ràng, không phụ thuộc `plain` mặc định

Ví dụ:

~~~groovy
tasks.named('bootWar') {
    archiveFileName.set('myapp-executable.war')
}

tasks.named('war') {
    archiveFileName.set('myapp-servlet.war')
}
~~~

Hai task sinh hai file riêng. `archiveFileName` tường minh hữu ích khi CI/CD phải biết chính xác file nào được deploy bằng `java -jar` và file nào được copy vào external container.

Nếu chỉ cần một artifact, có thể chỉ thực thi task cần thiết thay vì luôn chạy cả hai. **Không nhất thiết phải disable** task còn lại; việc disable có thể ảnh hưởng publish, assemble hoặc các plugin khác.

### Khi có nhiều module

Trong multi-project Gradle, task `bootWar` tồn tại ở subproject đã áp dụng đúng plugins:

~~~bash
./gradlew :webapp:bootWar
./gradlew :webapp:war
~~~

`:webapp` là ví dụ tên subproject, phải thay bằng module thật. Không yêu cầu `rootProject.tasks.named('bootWar')` khi task chỉ tồn tại trong child. Các module shared library thường chỉ tạo JAR, không cần `war` hoặc `bootWar`.

### Kotlin DSL tương đương

Trong `build.gradle.kts` đã áp dụng `war` và Spring Boot plugin:

~~~kotlin
import org.gradle.api.tasks.bundling.War
import org.springframework.boot.gradle.tasks.bundling.BootWar

tasks.named<BootWar>("bootWar") {
    archiveFileName.set("myapp-executable.war")
}

tasks.named<War>("war") {
    archiveFileName.set("myapp-servlet.war")
}
~~~

Đây là **đoạn cấu hình Kotlin DSL**, không phải file độc lập. Không chép cú pháp generic `named<BootWar>` vào file Groovy `build.gradle`. Trong Kotlin DSL, dependency có thể viết `providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")` khi War plugin đã được áp dụng.

### Thay đổi tên là khác thay đổi classpath

Cấu hình `archiveFileName` chỉ đổi tên output. Nó **không** thay đổi dependency scope, `WEB-INF/lib`, `WEB-INF/lib-provided`, main class hoặc khả năng deploy. Cần cấu hình `dependencies`, `springBoot.mainClass`, `SpringBootServletInitializer` và plugin/task tương ứng nếu muốn thay đổi hành vi.

### Tùy chỉnh content của WAR

Gradle `War`/`BootWar` có các thuộc tính dành cho archive như `webAppDirectory`, `from(...)`, `webInf { ... }`, `archiveFileName` và `destinationDirectory`. Ví dụ khi có static web files:

~~~groovy
tasks.named('war') {
    webAppDirectory.set(layout.projectDirectory.dir('src/main/webapp'))
}
~~~

Đây là đoạn minh họa cho **plain WAR**, giả định directory tồn tại; `war` plugin đã mặc định dùng `src/main/webapp`, nên không cần lặp lại cấu hình nếu không thay đổi. Nếu muốn cùng static resources xuất hiện trong executable WAR, kiểm tra `bootWar` nhận phần content phù hợp rồi **mở archive thực tế**. Không suy ra một task đã được tùy chỉnh thì task còn lại chắc chắn có cấu hình tương ứng.

## 13. Những lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh và xử lý |
| --- | --- | --- |
| `Task 'bootWar' not found` | Chưa áp dụng cả Spring Boot plugin và War plugin ở đúng project | Xem `plugins`, subproject và `./gradlew tasks --all` |
| `Task 'war' not found` | Chưa áp dụng `id 'war'` ở đúng project | Bổ sung War plugin, không nhầm với `bootJar` |
| `java -jar file.war` báo `no main manifest attribute` | Đang chạy plain WAR | Đọc manifest; chọn output của `bootWar` |
| `bootWar` chạy nhưng `Start-Class` sai/không xác định | Plugin không tìm được application main class | Cấu hình `springBoot.mainClass`, kiểm tra tên fully qualified |
| Plain WAR deploy vào Tomcat, startup báo thiếu initializer | Application chưa có servlet initializer phù hợp | Extend `SpringBootServletInitializer`, override `configure` |
| Deploy lên Tomcat 9 lỗi `javax`/`jakarta` | Spring Boot 3.x dùng Jakarta Servlet, Tomcat 9 dùng thế hệ API cũ | Chọn container tương thích, ví dụ Tomcat 10.1 |
| Lỗi trùng Tomcat/servlet classes | Embedded servlet server đóng ở `WEB-INF/lib` thay vì provided | Dùng `providedRuntime` đúng dependency, kiểm tra archive |
| `java -jar` thiếu embedded servlet classes | Provided dependencies không được `bootWar` đưa vào `WEB-INF/lib-provided` | Kiểm tra `providedRuntime`, bootWar config và `jar tf` |
| Web integration test thiếu server | Đưa Tomcat vào `compileOnly` sai semantics | Dùng `providedRuntime` trong Gradle War project |
| HTTP 404 trên external Tomcat | Sai context path hoặc endpoint | Thử `/war-demo/api/hello` thay vì `/api/hello`, kiểm tra logs |
| `build/libs` có nhiều WAR, CI deploy nhầm | Có plain và executable WAR với classifier khác nhau | Dùng tên file tường minh và kiểm tra manifest/layout |
| Build thành công nhưng archive thiếu dependency | Exclusion, provided configurations transitive hoặc publish task khác | Xem `runtimeClasspath`, provided scopes, `jar tf` |
| `war` chứa file không thuộc output hiện tại | Artifact cũ còn lại hoặc copy specs chưa đúng | Dùng `clean` khi cần, mở đúng output mới |
| `java -jar` chạy được, external deploy lỗi DB/profile | Môi trường container khác runtime trực tiếp | Kiểm tra config, credentials, classloader, env và server logs |
| WAR chứa `WEB-INF/lib-provided` nhưng Tomcat không dùng Tomcat nested ở đó | Đây là cơ chế tránh conflict có chủ đích | External container cung cấp server riêng; không tự move `lib-provided` vào `lib` |

**Đọc root cause:** nếu ứng dụng khởi động được nhưng trả HTTP 500 do database/network, đó không nhất thiết là lỗi `war` hay `bootWar`. Chỉ sửa packaging khi có bằng chứng class/resource/loader/initializer hoặc container compatibility khác biệt.

### Các lệnh chẩn đoán đáng nhớ

~~~bash
./gradlew tasks --all
./gradlew help --task war
./gradlew help --task bootWar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
./gradlew clean war bootWar
jar tf build/libs/war-demo.war
jar tf build/libs/war-demo-plain.war
~~~

`dependencies`/`dependencyInsight` cho biết dependency graph và lý do chọn version. **Không** coi graph là bằng chứng duy nhất về archive: providedRuntime và packaging task có thể ảnh hưởng nơi JAR cuối cùng được đặt. `jar tf` kiểm tra artifact thực tế.

Khi dùng `--info`, Gradle log thêm chi tiết task execution, nhưng không nên tuyên bố một stdout cố định vì log thay đổi theo version và môi trường.

## 14. Các giới hạn triển khai cần ghi nhớ

### WebFlux thuần và servlet WAR

Ứng dụng **Spring WebFlux** chạy dựa trên mô hình reactive và Reactor Netty theo mặc định không phải mục tiêu hỗ trợ chuẩn cho **WAR deployment theo Servlet container ngoài** như ví dụ. Bài này dành cho **Spring MVC/Servlet**. Không chuyển một ứng dụng WebFlux thuần thành `war` chỉ bằng cách thêm Gradle War plugin rồi chờ cơ chế external servlet khởi động.

### Container phải tương thích về API và JVM

Spring Boot 3.3 yêu cầu Java 17+ và sử dụng Jakarta Servlet. Tomcat 10.1 là ví dụ phổ biến cho Servlet 6.0. Khi chọn external servlet container khác, phải kiểm tra các ràng buộc Servlet API, Jakarta namespace, Java version, native libraries và các tính năng container mà ứng dụng cần.

### Cấu hình runtime không đi theo file WAR một cách thần kỳ

`java -jar` có thể lấy cấu hình từ command line, environment variables và external config; Tomcat bên ngoài có cơ chế startup, filesystem, logging và environment riêng. Đừng nhầm **cùng source code** với **cùng environment**. Nếu một WAR chạy trực tiếp nhưng deploy ngoài lỗi, xem initializer, servlet container dependency và log container trước khi kết luận lỗi Gradle task.

### Không chép WAR vào server khi chưa xác định context path

Tên WAR thường ảnh hưởng context path do container lựa chọn, nhưng container có thể dùng context XML, manager settings hoặc reverse proxy để override. Endpoint `/api/hello` của code có thể hiển thị thành `/app/api/hello` khi deploy vào context `/app`. Phải kiểm tra context path thực tế thay vì tự thêm hoặc bỏ dấu `/`.

### Không tự sửa manifest ZIP sau khi build

`bootWar` tạo loader và manifest phù hợp cho executable WAR; `war` tạo WAR truyền thống. Chỉnh `Main-Class` thủ công không biến plain WAR thành executable, vì còn thiếu launcher và classpath layout. Nếu phải đổi main class, sửa cấu hình Spring Boot plugin rồi rebuild.

## 15. Quy trình quyết định nhanh

1. **Xác định nơi chạy:** JVM trực tiếp hay servlet container bên ngoài.
2. **Bảo đảm ứng dụng thuộc Servlet stack** nếu cần external WAR deployment.
3. **Áp dụng Gradle `war` plugin** để có task `war`, và Spring Boot Gradle plugin nếu cần `bootWar`.
4. **Đặt `SpringBootServletInitializer` và `configure`** cho external deployment; giữ `main` cho executable mode nếu cần chạy trực tiếp.
5. **Khai báo web starter và `providedRuntime`** cho embedded servlet container phù hợp.
6. **Tạo task mong muốn** với `./gradlew war`, `./gradlew bootWar` hoặc gọi cả hai.
7. **Đọc artifact**: `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, loader và manifest.
8. **Thử đúng đường chạy**: `java -jar` cho executable WAR; deploy trên Tomcat phù hợp cho traditional WAR.
9. **Kiểm tra endpoint và context path**, sau đó xác minh logs/test trong môi trường đích.
10. **Ghi rõ sản phẩm release nào dùng vào đâu**, tránh pipeline phân phối nhầm plain/executable WAR.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** `id 'war'` tạo ra task nào, và có tự tạo `bootWar` không?

**Đáp án:** War plugin tạo `war`; `bootWar` xuất hiện khi Spring Boot Gradle plugin phối hợp với War plugin trong cùng project.

**Câu 2:** Vì sao `war-demo-plain.war` thường không chạy với `java -jar`?

**Đáp án:** Plain WAR hướng tới external servlet deployment, không mặc định có Boot loader và main manifest entry point. Để chạy trực tiếp, dùng executable WAR tạo từ `bootWar`.

**Câu 3:** Tại sao đặt `spring-boot-starter-tomcat` vào `providedRuntime`?

**Đáp án:** Servlet container ngoài tự cung cấp Tomcat; plain WAR không nên đóng trùng embedded server vào `WEB-INF/lib`, còn `bootWar` có thể giữ provided dependencies dưới `WEB-INF/lib-provided` phục vụ executable mode.

**Câu 4:** `SpringBootServletInitializer` có thay nhiệm vụ `war`/`bootWar` không?

**Đáp án:** Không. Initializer giúp external servlet container khởi tạo Spring context; build tasks quyết định archive nào được tạo và nó chứa gì.

**Câu 5:** Cùng endpoint `/api/hello`, tại sao chạy direct WAR ở port 8081 có URL khác khi deploy vào Tomcat?

**Đáp án:** Direct WAR thường dùng root context nên `http://localhost:8081/api/hello`. External Tomcat có context path theo tên WAR/deployment nên có thể là `http://localhost:8080/war-demo/api/hello`.

**Câu 6:** Nếu hai file đều có đuôi `.war`, làm sao biết file nào executable?

**Đáp án:** Kiểm tra `META-INF/MANIFEST.MF`, `Main-Class=WarLauncher`, `Start-Class` và Boot loader entries; đồng thời kiểm tra `WEB-INF/lib-provided`, nguồn task và chạy artifact đúng cách.

**Câu 7:** Có thể thay `providedRuntime` bằng `compileOnly` một cách tùy ý không?

**Đáp án:** Không. `compileOnly` không cung cấp dependency ở test/runtime classpath, dễ khiến web tests hoặc runtime path khác mong đợi. `providedRuntime` có semantics WAR riêng.

**Câu 8:** Spring Boot 3.3 WAR có thể deploy thẳng lên Tomcat 9 không?

**Đáp án:** Không phải cấu hình triển khai tương thích thông thường: Boot 3.x dùng Jakarta Servlet còn Tomcat 9 dùng `javax.servlet.*`. Cần chọn container tương thích, chẳng hạn Tomcat 10.1.

## 17. Tài liệu chính thức

- Spring Boot 3.3 — [Packaging Executable Archives with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootWar`, `providedRuntime`, executable and deployable WAR, plain classifier.
- Gradle — [The War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html): `war`, `WEB-INF/classes`/`WEB-INF/lib`, `providedCompile`, `providedRuntime` và webapp root.
- Spring Boot — [Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer` và cách chuẩn bị WAR cho external servlet container.
- Spring Boot 3.3 — [SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): callback `configure`.
- Spring Boot 3.3 — [System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java, Gradle và Servlet container compatibility.
- Spring Boot — [Launching Executable Archives](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/launching.html): `WarLauncher` và manifest `Main-Class`/`Start-Class`.

**Ghi nhớ:** **`war` tạo WAR truyền thống**, **`bootWar` tạo executable Spring Boot WAR**; `providedRuntime` và `SpringBootServletInitializer` là hai mảnh ghép thiết yếu nếu muốn **cùng ứng dụng** hoạt động với embedded servlet server khi `java -jar` và với servlet container bên ngoài khi deploy WAR. Muốn phân biệt hai artifact, **mở nội dung WAR và thử đúng đường chạy**, đừng chỉ nhìn đuôi file.
