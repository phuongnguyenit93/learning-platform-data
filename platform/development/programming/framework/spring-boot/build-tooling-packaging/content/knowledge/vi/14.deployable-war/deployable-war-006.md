# Quản lý máy chủ nhúng qua Maven `provided` và Gradle `providedRuntime` khi đóng gói WAR Spring Boot

## 1. Tình huống: cùng một ứng dụng, hai kiểu khởi chạy WAR

Một ứng dụng **Spring Boot Servlet Web** có thể cần triển khai theo hai hướng:

- **Chạy độc lập (standalone):** `java -jar war-demo.war`. Ứng dụng phải có các thư viện máy chủ nhúng, ví dụ Tomcat embedded, để tự tạo web server.
- **Triển khai lên máy chủ Servlet bên ngoài:** đặt `war-demo.war` vào một Tomcat/container tương thích. Container bên ngoài đã cung cấp servlet engine, thread pools, HTTP connector và một phần các API liên quan; app không nên ép container nạp thêm một bộ engine nhúng cạnh tranh trong `WEB-INF/lib`.

Hai yêu cầu này tưởng mâu thuẫn: **máy chủ nhúng phải có khi chạy `java -jar`, nhưng không được gây xung đột khi WAR được container bên ngoài triển khai**. Spring Boot giải quyết bằng **layout WAR đặc biệt** và một quy tắc đánh dấu dependency:

- Maven: `<scope>provided</scope>` đối với `spring-boot-starter-tomcat`.
- Gradle: `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` khi dùng `war` plugin.

Khi được đóng gói bằng Spring Boot Maven Plugin/Gradle Plugin đúng cách, các dependency đó được xếp vào **`WEB-INF/lib-provided/`**, không phải `WEB-INF/lib/`. Đường chạy standalone qua **`WarLauncher`** vẫn nhìn thấy chúng; container bên ngoài không dùng `WEB-INF/lib-provided` như thư mục library ứng dụng tiêu chuẩn nên không bị một bản Tomcat nhúng bên cạnh tranh.

**Mục tiêu:** phân biệt đúng scope/configuration, viết được POM và Gradle build tương ứng, tạo WAR vừa executable vừa deployable, nhìn thấy `WEB-INF/lib-provided` bằng `jar tf`, chạy được `java -jar` và biết cách kiểm tra deployment vào Servlet container ngoài. Không chấp nhận kết luận “build xanh nghĩa là WAR đã an toàn để deploy” nếu thiếu kiểm chứng thực tế.

### 1.1. Những thứ `provided` không có nghĩa

- **Không có nghĩa** “xóa thư viện khỏi mọi chỗ”: Spring Boot executable WAR **vẫn chứa** thư viện trong `WEB-INF/lib-provided`.
- **Không có nghĩa** “bỏ test”: Maven `provided` có trong compile/test classpaths; Gradle `providedRuntime` được ưu tiên chính vì phù hợp test runtime.
- **Không có nghĩa** “tắt embedded Tomcat bằng một property”: các lệnh development run hoặc standalone cần classpath runtime tương ứng.
- **Không có nghĩa** Spring Boot tự biết mọi third-party container tương thích: Servlet API, `jakarta.*`, Tomcat/Jetty versions, logging và các thư viện chung vẫn phải được kiểm tra.
- **Không có nghĩa** một JAR và một WAR có cấu trúc giống nhau: executable JAR dùng `BOOT-INF`, WAR dùng `WEB-INF`.

Trong bài, sử dụng **Java 17, Spring Boot 3.3.13**, Maven hoặc Gradle phù hợp để minh họa. Đây là **phiên bản minh họa có chủ đích**, không phải khẳng định phiên bản mới nhất/còn được hỗ trợ tại thời điểm đọc. Xác định version thực của dự án và chính sách hỗ trợ trước khi chọn toolchain.

## 2. Phân biệt máy chủ nhúng và Servlet container bên ngoài

### 2.1. Chạy standalone với embedded Tomcat

Khi có `spring-boot-starter-web`, Spring Boot 3.3 thông thường nhận Spring MVC và mặc định dùng Tomcat Servlet web server. Khi app được chạy bằng `java -jar` hoặc `spring-boot:run`/`bootRun` với classpath phù hợp:

1. `main(String[] args)` gọi `SpringApplication.run(...)`.
2. Spring Boot tạo application context, auto-configure web server factory và khởi tạo Tomcat nhúng.
3. Tomcat bind cổng do `server.port` quyết định (ví dụ 18085).
4. HTTP request đi trực tiếp vào process JVM của ứng dụng.

Với executable WAR, `WarLauncher` trước đó chuẩn bị classpath từ `WEB-INF/classes`, `WEB-INF/lib` **và** `WEB-INF/lib-provided`. Nhờ vậy máy chủ nhúng ở `lib-provided` vẫn có thể phục vụ standalone.

### 2.2. Deploy WAR lên Tomcat ngoài

Với container bên ngoài:

1. Bạn cung cấp file `war-demo.war` cho cơ chế deploy của Tomcat/container.
2. Container quản lý lifecycle, thread pools, HTTP connector và classloader theo luật Servlet.
3. `SpringBootServletInitializer` của ứng dụng tham gia bootstrap Spring ApplicationContext từ Servlet container.
4. HTTP port, virtual host, HTTPS connector và context path chủ yếu là **cấu hình của container**, không phải của embedded Tomcat.
5. Application classes và các thư viện phù hợp với Web application được container đọc từ `WEB-INF/classes`/`WEB-INF/lib`.

Container chuẩn **không xử lý `WEB-INF/lib-provided` như phần classpath thư viện của webapp**. Vì vậy những Tomcat embedded JAR ở đó không va chạm trực tiếp với engine Tomcat mà container đang dùng.

**Không nhầm runtime:** gọi `java -jar xxx.war --server.port=18085` khác hẳn việc copy WAR vào `webapps/` của Tomcat ngoài. Trong trường hợp thứ hai, `server.port` của Spring Boot không cấu hình connector của Tomcat bên ngoài; bạn phải dùng cấu hình/server logs đúng.

### 2.3. Tại sao `SpringBootServletInitializer` quan trọng?

Một `main()` chỉ giải quyết entrypoint của **Java process standalone**. Servlet container ngoài **không gọi `main()`** của ứng dụng khi deploy WAR. Spring Boot cung cấp `SpringBootServletInitializer` để nối lifecycle của Spring với cách Servlet container khởi tạo webapp.

Mẫu Java 17 đầy đủ sẽ có:

~~~java
@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

Đoạn trên là **khung minh họa thiếu imports**; file Java đầy đủ ở mục 6. Nếu chỉ thêm `<packaging>war</packaging>` hoặc plugin `war` mà không có bootstrap phù hợp, WAR có thể đóng gói thành công nhưng không được Servlet container ngoài khởi chạy như kỳ vọng.

### 2.4. Điều kiện tương thích Spring Boot 3.3

Spring Boot 3.3.13 yêu cầu **Java 17+**, hỗ trợ embedded Tomcat **10.1**, Jetty **12.0**, Undertow **2.3** và có thể triển khai tới Servlet container tương thích **Servlet 5.0+** theo tài liệu phiên bản. Trong thực hành nên dùng Tomcat **10.1.x tương thích Jakarta Servlet** để dễ đối chiếu. Tomcat **9.x/`javax.servlet.*`** thuộc hệ Java EE trước Jakarta, không phải một lựa chọn “cắm WAR Boot 3.3 vào là chạy”.

**Cảnh báo:** tương thích Servlet API chỉ là một điều kiện. Còn cần xét Servlet container vendor, Java runtime, logging/classloading policy, thư viện chung của server và các vấn đề bảo mật, hỗ trợ vận hành. Chọn bản container được duyệt trong tổ chức, không suy chỉ từ hai chữ “Tomcat”.

## 3. Nhìn vào WAR: `WEB-INF/lib` và `WEB-INF/lib-provided` khác nhau thế nào?

Đây là **sơ đồ khái niệm** của một Spring Boot 3.3 executable WAR được build đúng cách. Version/tên library thực tế khác nhau theo dependency resolution:

~~~text
war-demo-0.0.1-SNAPSHOT.war
|
+-- META-INF/
|   +-- MANIFEST.MF
|
+-- org/springframework/boot/loader/
|   +-- launch/
|   |   +-- WarLauncher.class
|   |   +-- ...
|   +-- ...
|
+-- WEB-INF/
    +-- classes/
    |   +-- com/example/war/WarDemoApplication.class
    |   +-- com/example/war/PingController.class
    |   +-- application.properties
    |
    +-- lib/
    |   +-- spring-boot-3.3.13.jar
    |   +-- spring-webmvc-<resolved-version>.jar
    |   +-- ...            # application runtime libraries
    |
    +-- lib-provided/
        +-- tomcat-embed-core-<resolved-version>.jar
        +-- tomcat-embed-el-<resolved-version>.jar
        +-- ...            # provided container runtime libraries
~~~

Một số archive còn có `WEB-INF/layers.idx` hay index ở vị trí theo plugin/layout phiên bản; **không** dùng việc có index như điều kiện duy nhất cho WAR chạy được. Cốt lõi nằm ở manifest, launcher, classes, `lib` và `lib-provided`.

| Vị trí | Ai sử dụng? | Vai trò |
| --- | --- | --- |
| `META-INF/MANIFEST.MF` | JVM khi gọi `java -jar`. | `Main-Class` trỏ tới Boot `WarLauncher`, `Start-Class` trỏ tới main app class. |
| `org/springframework/boot/loader/` | JVM khởi chạy executable WAR. | Loader bootstrap, dựng nested classpath. |
| `WEB-INF/classes` | Standalone launcher **và** servlet container ngoài. | Class/resource production của app. |
| `WEB-INF/lib` | Standalone launcher **và** servlet container ngoài. | Dependency runtime thông thường của webapp. |
| `WEB-INF/lib-provided` | Standalone launcher của Boot, không phải standard library path của container ngoài. | Servlet engine/runtime do bên ngoài cung cấp khi deploy. |

**Ý tưởng quan trọng:** file Tomcat vẫn được **đóng trong WAR** để chạy độc lập, chỉ được đặt ở vị trí mà **container ngoài không load như một JAR webapp thông thường**.

### 3.1. Lưu ý về loader version

Với Spring Boot 3.3.13, executable WAR thông thường có:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Một số tutorial Boot cũ dùng tên package launcher khác. **Không sửa manifest dựa trên tutorial cũ**; hãy đọc `META-INF/MANIFEST.MF` của chính WAR đang build. Cấu hình main class/packaging phải được xử lý qua Spring Boot plugin, không tự thay thông số bootloader để “sửa nhanh”.

### 3.2. WAR không tương đương JAR, WAR plain cũng khác WAR executable

- **Plain WAR:** có `WEB-INF/classes`/`WEB-INF/lib` để container deploy, nhưng có thể **không có** Boot loader/Main-Class để chạy bằng `java -jar`.
- **Boot executable WAR:** có loader và bố trí `WEB-INF/lib-provided` để hỗ trợ cả standalone và traditional deployment.
- **Boot executable JAR:** thường có `BOOT-INF/classes`/`BOOT-INF/lib` và `JarLauncher`, không áp dụng quy tắc `WEB-INF/lib-provided` cho mục đích deploy WAR.
- **Gradle WAR task `war`** và **Boot task `bootWar`** có thể sinh **hai artifact khác nhau**. Phải chọn đúng output theo mục đích.

## 4. Maven `provided`: vừa tránh xung đột container, vừa giữ khả năng chạy độc lập

### 4.1. Khai báo điển hình

Với Spring Boot Maven app sử dụng starter Web và đóng WAR, ví dụ:

~~~xml
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
~~~

`spring-boot-starter-web` đưa Spring MVC và theo mặc định kéo Tomcat starter vào đồ thị transitively. Khai báo **trực tiếp** `spring-boot-starter-tomcat` với `provided` giúp Maven xác định scope mong muốn cho server starter, thay vì để nó chỉ xuất hiện như transitive `compile`. Kiểm tra `dependency:tree` để xác nhận effective scope chứ đừng suy từ một dòng XML.

Với Boot starter parent, version starter được BOM quản lý nên không cần ghi `<version>` cho Tomcat starter. **Đừng** tự chốt một Tomcat version không tương thích với BOM chỉ để “chuyển provided” cho một module.

### 4.2. Maven `provided` thực sự có mặt ở classpath nào?

Trong Maven convention:

- **Compile:** `provided` có mặt vì code có thể compile dựa trên API/container dependency được hứa cung cấp lúc chạy.
- **Test:** `provided` có mặt khi chạy unit/integration tests bằng Maven thông thường, hỗ trợ kiểm thử Spring Web context.
- **Runtime Maven classpath chuẩn:** `provided` không được đưa vào runtime transitive resolution như `compile`/`runtime`.
- **Distribution của WAR do Spring Boot Plugin `repackage`:** trường hợp đặc biệt. Plugin **xét cả provided dependencies**, nhưng với layout WAR nó đặt chúng trong **`WEB-INF/lib-provided`**, không phải thư mục `WEB-INF/lib` của webapp.

Đây là điểm dễ gây hiểu nhầm khi dùng kiến thức Maven chung để đoán nội dung executable WAR. `provided` **không có nghĩa** “Tomcat biến mất hoàn toàn khỏi WAR”. Spring Boot cố ý giữ nó theo đường riêng để `java -jar` vẫn chạy được.

### 4.3. Maven `provided` khác `test` và `optional`

| Khai báo | Ý nghĩa cho build | Kết quả đối với Boot WAR |
| --- | --- | --- |
| `compile` (mặc định) | Cần compile + runtime. | Thường vào `WEB-INF/lib`. |
| `runtime` | Cần runtime, không cần compile trực tiếp. | Thường vào `WEB-INF/lib`. |
| `provided` | Compile/test có; container/JDK cung cấp lúc deploy. | Với repackage, thường vào `WEB-INF/lib-provided`. |
| `test` | Dành cho test. | Không tự vào executable WAR thông thường. |
| `optional=true` | Hạn chế việc kéo dependency transitively vào project tiêu thụ. | **Không tự đồng nghĩa** loại khỏi executable archive; phải đối chiếu quy tắc version/plugin đang dùng. |
| `system` | Phụ thuộc file ở đường dẫn local; khó tái lập. | Không đưa vào theo mặc định nếu `includeSystemScope=false`; tránh trong project thực tế. |

**Phạm vi đúng:** kết quả bên trên nói về **Spring Boot `repackage` ở WAR layout**, không nói tất cả Maven plugins dùng `provided` giống nhau. Nếu bạn tạo **plain WAR** hay dùng một plugin tùy chỉnh, cần kiểm tra archive thật.

### 4.4. Vì sao không exclude toàn Tomcat starter?

Nếu mục tiêu là **chỉ deploy WAR tới Tomcat ngoài, không bao giờ chạy standalone**, một số nhóm cân nhắc loại embedded engine hoàn toàn. Nhưng nếu bài toán cần **một WAR vừa deploy vừa chạy bằng `java -jar`**, thì việc loại Tomcat artifact khỏi dependency graph là sai mục tiêu: executable WAR sẽ mất thư viện để khởi động web server. `provided` đặt đúng chỗ mới là lựa chọn thuận tiện.

Đừng dùng Boot plugin `<excludes>`/`<excludeGroupIds>` để loại hết `org.apache.tomcat.embed` khi chưa xác định có cần standalone; đó là hành động khác với `provided` và có thể khiến packaged smoke test fail.

## 5. Gradle `providedRuntime`: lý do không dùng `compileOnly`

### 5.1. Configuration dành cho War plugin

Khi project áp dụng Gradle `war` plugin, có configuration `providedRuntime` cho các dependency **có tại runtime của máy chủ container bên ngoài**. Với Spring Boot Gradle Plugin, chúng được đưa tới **`WEB-INF/lib-provided`** của executable WAR:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Mặc dù `spring-boot-starter-web` kéo Tomcat transitively, declaration `providedRuntime` của Tomcat starter là quy tắc nhận diện container runtime đúng theo hướng dẫn Spring Boot. Khi kiểm chứng, hãy đọc **`bootWar` archive** và configuration reports thay vì chỉ nhìn `implementation` rồi nghĩ mọi transitive dependency đều vào `WEB-INF/lib`.

### 5.2. Vì sao `compileOnly` nghe giống Maven `provided` nhưng lại không phù hợp?

Gradle `compileOnly` làm thư viện có trên **main compile classpath** nhưng thông thường không có trên **main runtime classpath** và **không được kế thừa vào test classpath** như `providedRuntime`. Đây là vấn đề thực tế với tests cần khởi động Spring Web context hoặc dùng embedded servlet engine.

| Tiêu chí | Gradle `compileOnly` | Gradle `providedRuntime` |
| --- | --- | --- |
| Ý định chính | Cần API lúc compile nhưng không tự cần trong runtime chính. | Dependency sẽ do external web container cung cấp, song cần xử lý trong packaging WAR/test. |
| Có ở main compile? | Có. | Theo quan hệ configuration của WAR plugin và dependency declaration thực tế; không dùng `compileOnly` thay thế. |
| Có ở test runtime? | **Không mặc định.** | Có thể tham gia test runtime đúng mục đích WAR plugin. |
| Có được `bootWar` bố trí vào `WEB-INF/lib-provided`? | **Không phải cơ chế chuẩn.** | **Có**, theo Spring Boot Gradle Plugin. |
| Phù hợp để đánh dấu embedded servlet container của WAR? | Không khuyến nghị. | **Khuyến nghị.** |

Nếu dùng `compileOnly 'org.springframework.boot:spring-boot-starter-tomcat'`, Gradle có thể compile được các class phụ thuộc Tomcat API, nhưng test web mất engine và BootWar không nhận dependency theo quy tắc `lib-provided` mong muốn. **Dùng `providedRuntime` cho embedded container**, không “tự sửa” bằng cách chuyển Tomcat sang `testImplementation` hoặc `implementation` làm mất ý nghĩa WAR.

### 5.3. `providedRuntime` không phải `developmentOnly`

Spring Boot Gradle Plugin còn có `developmentOnly` để giữ thư viện phát triển (ví dụ DevTools) khỏi executable artifact theo mặc định. **Đừng nhầm:**

- `providedRuntime`: library **vẫn nằm trong WAR**, nhưng ở `WEB-INF/lib-provided` để standalone launcher dùng và external container bỏ qua.
- `developmentOnly`: library phục vụ dev, **không được đóng trong executable archive** theo mặc định.
- `runtimeOnly`: runtime dependency thông thường, thường vào `WEB-INF/lib`.
- `testImplementation`: chỉ để test, không được xem là runtime dependency của app.

Khi một dependency chỉ phục vụ test, hãy dùng test configuration; khi nó thực sự được container bên ngoài cung cấp nhưng standalone vẫn cần, dùng `providedRuntime`.

### 5.4. BOM và version catalog không thay thế `providedRuntime`

Spring Boot BOM/Gradle version catalog có thể quản lý version của Tomcat starter nhưng **không tự quyết định cấu hình runtime**. Trong build script:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
~~~

phần `providedRuntime` nêu ý định packaging. Dù version của starter đã có trong BOM, vẫn phải áp đúng configuration. Một alias `libs.spring.boot.starter.tomcat` nếu được tạo trong version catalog cũng không tự gán nó cho `providedRuntime`.

## 6. Ví dụ Java 17: một source dùng được cả standalone WAR và external Tomcat

Cấu trúc chương trình đơn giản, giữ nguyên mã Java dù bạn chọn Maven hoặc Gradle:

~~~text
war-demo/
  pom.xml                                  # CHỌN Maven
  # hoặc:
  settings.gradle
  build.gradle                             # CHỌN Gradle
  src/main/java/com/example/war/WarDemoApplication.java
  src/main/java/com/example/war/PingController.java
  src/main/resources/application.properties
  src/test/java/com/example/war/WarDemoApplicationTest.java
  (Maven Wrapper HOẶC Gradle Wrapper do repository tạo)
~~~

### 6.1. Entrypoint cho hai cách chạy

`src/main/java/com/example/war/WarDemoApplication.java`:

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

**Hai entrypoint ở cùng class:**

- `main(String[] args)`: chạy khi Boot `WarLauncher` khởi động ứng dụng bằng `java -jar`.
- `configure(SpringApplicationBuilder)`: chỉ ra application sources khi external Servlet container khởi tạo web app qua `SpringBootServletInitializer`.

Không cần `web.xml` cho ví dụ Boot Servlet 3.0+ style thông thường; project cũ có cấu hình Servlet/Filter/XML riêng phải chuyển/giữ những thành phần cần thiết. Với Servlet container đặc thù, cần xem hướng dẫn tương thích của vendor.

### 6.2. Controller có thể kiểm tra bằng HTTP

`src/main/java/com/example/war/PingController.java`:

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Spring Boot component scanning từ package `com.example.war` thấy `PingController`. Endpoint trả body chính xác `pong`, không cần kết nối database; thích hợp để kiểm tra riêng vấn đề bootstrap/classpath/server.

### 6.3. Application properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=war-demo
# Cổng HTTP standalone có thể override qua command-line argument
server.port=8080
~~~

Khi chạy standalone, `server.port` do embedded server dùng. **Khi deploy external Tomcat, Tomcat server cấu hình connector port của chính nó**; giá trị này trong application.properties không buộc Tomcat ngoài mở cổng 8080. Tránh đưa tên host/password/private key trong WAR; các môi trường nhận cấu hình nhạy cảm từ secret store hoặc cơ chế server được cấp quyền.

### 6.4. JUnit test với MockMvc

`src/test/java/com/example/war/WarDemoApplicationTest.java`:

~~~java
package com.example.war;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WarDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void pingRespondsWithPong() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

Test này tải Spring context và kiểm tra mapping/response bằng MockMvc, **không deploy WAR vào external server** và không mở một HTTP listener thật. Nó cần test dependencies và Spring Web application context. Vì vậy `providedRuntime`/`provided` hỗ trợ classpath test nhưng test pass **không thay thế** kiểm chứng `WEB-INF/lib-provided` và cả hai cách chạy.

## 7. Maven `pom.xml` hoàn chỉnh với `provided`

Đây là POM có thể sử dụng cùng Java source ở mục 6, giả định đã có Maven Wrapper/JDK17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>war-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Server container có khi compile/test, do bên ngoài cấp khi deploy -->
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
            <!-- Parent Spring Boot có cấu hình version/execution repackage -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích theo lớp:**

1. `<packaging>war</packaging>` thay lifecycle/package type từ JAR sang WAR.
2. `spring-boot-starter-web` giữ Spring MVC và các dependency web app.
3. `spring-boot-starter-tomcat` ở `provided` thay ý định runtime đối với embedded container, không “xóa Tomcat khỏi mọi nơi”.
4. `spring-boot-starter-parent` quản lý version dependency/build plugins; `spring-boot-maven-plugin` được khai báo để `repackage` gắn với phase package.
5. Test starter `scope=test` không vào WAR runtime thông thường.
6. `SpringBootServletInitializer` ở Java source mới là cầu nối cho external Servlet container, ngoài phần POM.

### 7.1. Vì sao không cần tự cấu hình `maven-war-plugin` ở ví dụ?

Spring Boot starter parent đã thiết lập các defaults Maven WAR/plugin phù hợp ở version này. Trong corporate parent hoặc POM chỉ import BOM, có thể cần quản lý rõ plugin versions, maven-war-plugin và execution `spring-boot:repackage`. **Import `spring-boot-dependencies` BOM một mình không mang theo toàn bộ build defaults**.

Không tự thêm một execution `repackage` có ID khác trong khi parent đã có execution đó, vì có thể gây chạy goal lặp. Khi cần thay cấu hình, đọc `help:effective-pom` để sửa đúng điểm trong mô hình kế thừa.

### 7.2. Lệnh Maven và output dự kiến

~~~bash
./mvnw -version
./mvnw clean verify

# Xem resolved dependency và scope:
./mvnw dependency:tree

# Tên file theo GAV của ví dụ:
jar tf target/war-demo-0.0.1-SNAPSHOT.war
~~~

Kỳ vọng archive có:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/com/example/war/WarDemoApplication.class
WEB-INF/classes/com/example/war/PingController.class
WEB-INF/classes/application.properties
WEB-INF/lib/<các-runtime-lib-của-Spring>.jar
WEB-INF/lib-provided/tomcat-embed-core-<resolved-version>.jar
WEB-INF/lib-provided/<các-container-lib-khác>.jar
~~~

`war-demo-0.0.1-SNAPSHOT.war` là tên mẫu, cần lấy tên đúng từ `target/`. Các tên thư viện chứa `<resolved-version>` là ký hiệu để đọc; **không** được sao chép nguyên chuỗi có dấu góc vào CLI.

### 7.3. Đừng lấy kết quả `dependency:tree` làm danh sách file đóng gói

`dependency:tree` mô tả dependency graph/scope ở cấp Maven. Spring Boot Plugin còn **bố trí lại** provided dependency vào `WEB-INF/lib-provided` khi `repackage`. Vì vậy dependency tree và `jar tf` bổ sung bằng chứng khác nhau; không được kết luận Tomcat đã “biến mất” chỉ vì không nằm dưới `WEB-INF/lib`.

## 8. Gradle `build.gradle` hoàn chỉnh với `providedRuntime`

File `settings.gradle`:

~~~groovy
rootProject.name = 'war-demo'
~~~

File `build.gradle` (Groovy DSL, phù hợp bản minh họa):

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
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

    // WAR sẽ đặt Tomcat embedded dưới WEB-INF/lib-provided:
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Phân tích:**

- Plugin `war` tạo Gradle WAR lifecycle/configurations, trong đó có `providedRuntime`.
- Spring Boot plugin bổ sung task `bootWar` khi có WAR plugin; không chỉ tạo `bootJar` như Java application chỉ có `java`.
- Dependency management plugin quản lý versions theo Spring Boot BOM tương ứng; không tự xác định provided scope. `providedRuntime` chính là lựa chọn của build script.
- `testImplementation` và `testRuntimeOnly` cung cấp công cụ test; không coi chúng là production runtime dependencies.
- `java.toolchain` yêu cầu Java 17 để compile; nếu JVM toolchain không có sẵn, Gradle cần cơ chế provisioning/cài JDK phù hợp.
- Plugin versions ở đây được cố định cho ví dụ; dự án thật cần kiểm chứng compatibility Gradle Wrapper/JDK/plugin versions.

### 8.1. Gradle `bootWar` khác `war`

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew clean build

# Gọi riêng task executable WAR:
./gradlew bootWar
~~~

`bootWar` là task tạo **Spring Boot executable WAR** và được tích hợp vào assemble/build. Task `war` của Gradle tạo **plain WAR**. Với quy ước plugin Boot 3.3, khi cả plain và executable được tạo, plain WAR thường có classifier `plain`, ví dụ:

~~~text
build/libs/war-demo-0.0.1-SNAPSHOT.war
build/libs/war-demo-0.0.1-SNAPSHOT-plain.war
~~~

**Không deploy/chạy bằng cách chọn ngẫu nhiên file `*.war` đầu tiên.** File nào đúng phải được xác định qua task output, tên archive, manifest và `jar tf`. Plain WAR có thể deploy vào container ngoài theo servlet rules nhưng không nhất thiết hỗ trợ `java -jar` standalone.

### 8.2. Khi `compileOnly` làm test bị lỗi

Đoạn dưới là **phản ví dụ** cho ứng dụng vừa deployable vừa executable:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // KHÔNG dùng như thay thế providedRuntime trong bài toán WAR:
    compileOnly 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Thay vào đó:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

`compileOnly` không tự cấp Tomcat cho test runtime và không ra hiệu BootWar đặt Tomcat vào `lib-provided`. Nếu integration tests cần Spring Web context, chúng có thể fail với missing server classes. Đừng “sửa” bằng cách vô hiệu hóa test; dùng configuration đúng và quan sát `testRuntimeClasspath`.

### 8.3. Kotlin DSL tương đương

Với `build.gradle.kts` (mảnh dependency declaration, yêu cầu `war`/Boot plugins đã áp và dependency management đang hoạt động):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

Đây là phần Kotlin DSL **không phải một file độc lập**. Không copy dấu nháy đơn/cú pháp Groovy vào Kotlin và cho rằng Gradle tự dịch.

## 9. Vì sao có thể để `spring-boot-starter-web` đồng thời với `provided` Tomcat?

Đây là câu hỏi nhiều người gặp:

> “Starter Web đã kéo Tomcat rồi. Nếu thêm Tomcat starter một lần nữa, có tải hai bản Tomcat không?”

Trong Maven/Gradle dependency resolution, một tọa độ xuất hiện qua nhiều đường **không nhất thiết tạo hai bản sao runtime**. Công cụ giải quyết graph và áp quy tắc phiên bản/scope/configuration; khai báo thêm ở `provided`/`providedRuntime` nhằm **điều chỉnh nơi nó thuộc về khi build/deploy**, không phải thêm một server thứ hai theo ý định.

Nhưng đừng chỉ suy đoán. Với dự án có exclusions, dependency overrides hoặc nhiều web starters, hãy kiểm tra:

- Maven `./mvnw dependency:tree`: starter nào dẫn tới Tomcat, effective scope là gì?
- Gradle `./gradlew dependencies --configuration runtimeClasspath` và `testRuntimeClasspath`: Tomcat có ở những classpath nào?
- `jar tf executable.war`: Tomcat embedded JAR có nằm **`WEB-INF/lib-provided`** như kỳ vọng không, và **không** tràn xuống `WEB-INF/lib`?
- Boot runtime: `java -jar` start và trả HTTP?
- External deployment: webapp có start qua server container logs, không gặp duplicate Servlet/Tomcat classes?

Nếu thấy **Tomcat embedded trong cả `WEB-INF/lib` và `lib-provided`** theo đường build tùy biến, hãy điều tra ngay: có thể có một dependency/configuration khác đã kéo chúng vào runtime webapp. Đừng thủ công xóa một nested JAR khỏi WAR rồi dùng làm release; sửa graph/build logic và rebuild sạch.

### 9.1. Gradle và Maven đều có cách resolve scope riêng

Đừng coi `Maven provided == Gradle compileOnly` chỉ vì cả hai nghe giống “cần lúc compile”. Trường hợp **Spring Boot executable WAR** đòi **đồng thời**:

1. Có servlet engine cho standalone app.
2. Không trộn embedded engine vào webapp lib chuẩn khi deploy ngoài.
3. Có classpath phù hợp để unit/integration tests chạy.
4. Có artifact reproduci​ble và đóng đúng layout bởi Boot plugin.

Maven dùng `provided` + Spring Boot repackage; Gradle dùng `providedRuntime` + `bootWar`. Đây là **tương đương về mục đích đóng gói**, không phải đồng nhất toàn bộ semantics của dependency scopes giữa hai build systems.

## 10. Kiểm tra WAR bằng `jar tf` và manifest

Bước QA quan trọng nhất là **đọc đúng artifact** trước khi deploy. `jar` (JDK) có thể liệt kê WAR vì WAR là ZIP/JAR-compatible archive.

### 10.1. Kiểm tra danh sách entry

Maven:

~~~bash
jar tf target/war-demo-0.0.1-SNAPSHOT.war
~~~

Gradle:

~~~bash
jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war
~~~

Với macOS/Linux, nếu có `grep`:

~~~bash
WAR=target/war-demo-0.0.1-SNAPSHOT.war

jar tf "$WAR" | grep '^WEB-INF/classes/'
jar tf "$WAR" | grep '^WEB-INF/lib/'
jar tf "$WAR" | grep '^WEB-INF/lib-provided/'
jar tf "$WAR" | grep '^org/springframework/boot/loader/'
~~~

Khi lọc, **`^WEB-INF/lib/` không bao gồm `^WEB-INF/lib-provided/`**, nên có thể phân biệt chính xác hai nhánh. Các tên `tomcat-embed-core-*.jar`, `tomcat-embed-el-*.jar`, `tomcat-embed-websocket-*.jar` là dấu hiệu điển hình nhưng số thư viện/phần mở rộng thực tế phụ thuộc resolved graph.

### 10.2. Manifest của executable WAR

Nếu có `unzip`:

~~~bash
unzip -p "$WAR" META-INF/MANIFEST.MF
~~~

Kỳ vọng một số key như:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

Không ép toàn bộ manifest phải giống đúng hai dòng; có thêm build metadata và manifest line wrapping khác. Nếu không có `Main-Class` phù hợp, `java -jar` có thể báo `no main manifest attribute`. Khi dùng WAR plain, điều đó chưa hẳn lỗi deploy ngoài; chỉ là không có standalone launcher như Boot executable WAR.

### 10.3. Kiểm tra tự động (Bash)

Dưới đây là script kiểm tra **sự tồn tại** của class và Tomcat ở đúng nhánh, đồng thời tìm dấu hiệu package sai. Cần JDK `jar` và Bash/grep; **đổi đường dẫn cho Gradle** khi dùng nó.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

WAR="target/war-demo-0.0.1-SNAPSHOT.war"
LIST="$(jar tf "$WAR")"

# App classes phải có
grep -q '^WEB-INF/classes/com/example/war/WarDemoApplication.class$' <<< "$LIST"
grep -q '^WEB-INF/classes/com/example/war/PingController.class$' <<< "$LIST"

# Tomcat embedded phải được đưa vào nhánh provided của executable WAR
grep -Eq '^WEB-INF/lib-provided/tomcat-embed-core-[^/]+\.jar$' <<< "$LIST"

# Không cho Tomcat engine của app lẫn vào webapp lib bình thường
if grep -Eq '^WEB-INF/lib/tomcat-embed-(core|el|websocket)-[^/]+\.jar$' <<< "$LIST"; then
    echo "FAIL: embedded Tomcat found in WEB-INF/lib" >&2
    exit 1
fi

# Test class không phải runtime application class
if grep -Eq 'WarDemoApplicationTest.class' <<< "$LIST"; then
    echo "FAIL: test class packaged into WAR" >&2
    exit 1
fi

echo "PASS: WAR classes and container layout verified"
~~~

**Stdout kỳ vọng khi đạt điều kiện (và exit code 0):**

~~~text
PASS: WAR classes and container layout verified
~~~

Nếu thiếu class, thiếu Tomcat ở `lib-provided` hoặc Tomcat lẫn xuống `lib`, script kết thúc code khác 0 (các assertion bằng grep không nhất thiết in thông điệp). Script chỉ là **một bộ assertion cấu trúc**, không chứng minh JVM/container outside thật sự chạy được hoặc các dependencies khác hoàn toàn tương thích.

**Vì sao dùng here-string `<<< "$LIST"`?** Tránh đường ống `jar tf | grep -q` dưới `set -o pipefail` có thể bị ảnh hưởng bởi SIGPIPE trên archive có quá nhiều entries. Here-string dùng kết quả đã đọc; khi WAR lớn, CI có thể chọn công cụ ZIP API chuyên dụng để không giữ toàn bộ list trong shell memory.

### 10.4. Windows PowerShell

Có thể xem các entry mà không cần Bash:

~~~powershell
$war = "target/war-demo-0.0.1-SNAPSHOT.war"
jar tf $war | Select-String '^WEB-INF/classes/'
jar tf $war | Select-String '^WEB-INF/lib/'
jar tf $war | Select-String '^WEB-INF/lib-provided/'
~~~

Đổi `$war` thành `build/libs/...war` nếu dùng Gradle. Trong CI PowerShell, cần viết assertion với `Select-String -Quiet` và exit code, không coi việc nhìn bằng mắt là QA đầy đủ.

## 11. Chạy `java -jar`: kiểm tra embedded Tomcat vẫn đủ

Sau khi đã có executable WAR, thử **đúng binary vừa đóng**:

~~~bash
# Maven WAR:
java -jar target/war-demo-0.0.1-SNAPSHOT.war --server.port=18085

# Hoặc Gradle WAR, trong một phiên khác:
# java -jar build/libs/war-demo-0.0.1-SNAPSHOT.war --server.port=18085
~~~

Khi app log đã ready, ở terminal khác:

~~~bash
curl -i http://localhost:18085/ping
~~~

**Kỳ vọng:** status HTTP **200** và body chính xác **`pong`**. Startup log/HTTP headers/port-bind timing thay đổi theo môi trường; không tuyên bố đây là stdout thực tế nếu chưa chạy.

Nếu `WEB-INF/lib-provided` không chứa đủ Tomcat engine, standalone launch có thể fail vì thiếu `ServletWebServerFactory` hoặc các class Tomcat/Servlet. Điều đó **không tự kết luận** external-container deployment cũng fail: hai con đường runtime khác nhau. Nhưng nếu yêu cầu bài toán là WAR chạy được cả hai kiểu, đây là lỗi QA cần sửa.

### 11.1. Dùng sai artifact sẽ cho kết quả sai

Nếu Gradle tạo cả:

~~~text
war-demo-0.0.1-SNAPSHOT.war
war-demo-0.0.1-SNAPSHOT-plain.war
~~~

chỉ file **executable** được Spring Boot `bootWar` tạo mới kỳ vọng chạy `java -jar`. Không dùng wildcard `*.war`/“lấy file mới nhất” không kiểm tra classifier. Với Maven, `repackage` có thể giữ bản WAR gốc dưới tên `*.war.original`; file gốc không phải binary để kiểm chứng standalone launcher.

### 11.2. Phân biệt cổng và URL hai môi trường

| Loại chạy | Ai mở HTTP port? | Cách truy cập endpoint ví dụ |
| --- | --- | --- |
| `java -jar ...war --server.port=18085` | Embedded Tomcat trong JVM ứng dụng. | `http://localhost:18085/ping`. |
| WAR deploy ở external Tomcat trên port 8080, context `/war-demo` | Tomcat server ngoài (connector 8080). | `http://localhost:8080/war-demo/ping`. |
| WAR deploy ở external Tomcat dưới context root `/` | Tomcat server ngoài. | `http://localhost:8080/ping`. |

Port và context path của external server **chỉ là ví dụ**. Tomcat có thể có HTTPS connector, host, reverse proxy, virtual context path khác; lấy giá trị thật từ container configuration/logs và deployment descriptor. Spring `server.port` không áp đặt socket của external Tomcat.

## 12. Triển khai WAR lên Tomcat ngoài mà không lẫn embedded engine

Trước khi deploy, đảm bảo external Servlet container/JDK đã được phê duyệt và có đường triển khai rõ ràng. Với Spring Boot 3.3, hệ Java 17+ và Jakarta Servlet là nền tảng; Tomcat 10.1 là lựa chọn minh họa gần với embedded container của dòng này.

Một quy trình local có kiểm soát:

1. Chuẩn bị **Tomcat bên ngoài độc lập** đã khởi động, có quyền deploy. Không dùng máy production cho lần thử đầu tiên.
2. Build executable WAR từ source đúng version và test `jar tf` để xác nhận Tomcat JAR ở `WEB-INF/lib-provided`.
3. Dùng Tomcat Manager hoặc deploy folder `webapps` theo chính sách môi trường; file WAR có thể được đặt tên `war-demo.war`, thường thành context path `/war-demo` (nếu Tomcat không cấu hình path khác).
4. Theo dõi **log của external Tomcat** để xem webapp deploy thành công hay fail, thay vì chỉ đọc log Maven/Gradle.
5. Dùng URL chứa **port/context path của Tomcat ngoài**, ví dụ `http://localhost:8080/war-demo/ping`.
6. Sau kiểm thử, undeploy qua cơ chế quản lý container, không kill toàn bộ JVM trên máy.

Ví dụ lệnh copy (chỉ khi bạn thực sự quản lý **local test Tomcat** với biến môi trường `CATALINA_BASE` trỏ đúng instance):

~~~bash
# Chỉ minh họa; Tomcat Manager/CI deploy thường được ưu tiên.
# Đảm bảo $CATALINA_BASE được cấu hình đúng, tuyệt đối không đoán path.
cp target/war-demo-0.0.1-SNAPSHOT.war "$CATALINA_BASE/webapps/war-demo.war"
~~~

Nếu Tomcat ngoài đã chạy, nó có thể tự deploy dựa vào `autoDeploy` cấu hình. Không có bảo đảm mọi instance đều auto-deploy; đọc docs của container/ops. Ứng dụng không được coi đã deploy chỉ vì copy exit 0.

### 12.1. Vì sao Servlet container không chạy Spring Boot `main()`?

External server kiểm soát webapp lifecycle. `SpringBootServletInitializer.configure(...)` cấu hình nguồn Spring Boot ApplicationContext để container bootstrap. Do đó, khi debug lỗi “WAR deploy không có endpoint”, kiểm tra initializer, component scanning, servlet registration và container logs. Chỉ chăm chăm sửa `main()`/`server.port` không nhất thiết tác động tới external path.

### 12.2. Vì sao không nên bỏ `providedRuntime` để “Tomcat ngoài tự có”?

Nếu xóa dependency provided khỏi build trong khi vẫn muốn standalone:

- `java -jar` có thể mất Tomcat embedded và không mở HTTP port.
- Test classpath có thể thiếu server classes.
- WAR structure có thể vẫn chứa webapp libs khác nhưng không đáp ứng tiêu chí executable + deployable.

Nếu tổ chức **chỉ** cần deploy external và không bao giờ cần standalone, một kiến trúc chỉ dùng container-managed deps có thể được cân nhắc; tuy vậy phải mô tả lại hợp đồng artifact và test phù hợp. Bài này giữ mục tiêu **dual-mode WAR**.

## 13. Những lỗi thực tế: tìm lỗi ở đúng lớp

| Triệu chứng | Nguyên nhân thường gặp | Kiểm chứng và hướng xử lý |
| --- | --- | --- |
| `java -jar app.war` báo `no main manifest attribute`. | Dùng plain WAR hoặc chưa chạy Boot repackage/bootWar. | Kiểm tra manifest, Boot loader, task build và đúng artifact. |
| WAR có `WEB-INF/lib` nhưng không có `WEB-INF/lib-provided`. | Thiếu `provided`/`providedRuntime` hoặc Boot packaging không dùng đúng layout. | Kiểm tra POM/config, resolved graph, executable WAR task và archive contents. |
| Tomcat embedded vẫn nằm `WEB-INF/lib`. | Dependency declaration/configuration không điều chỉnh đúng scope; packaging custom. | Đọc dependency graph, xác nhận direct Tomcat starter provided và rebuild clean. |
| Standalone WAR fail vì thiếu `TomcatServletWebServerFactory`/Tomcat class. | Container runtime đã bị loại khỏi archive hoặc không có trên launcher classpath. | Kiểm tra `WEB-INF/lib-provided` và `WarLauncher`/manifest. |
| External Tomcat deploy fail vì `ClassNotFoundException: jakarta.servlet...`. | Container chưa hỗ trợ Jakarta/Servlet version, hoặc classloading policy xung đột. | Xem version container, Jakarta namespace, Java runtime; dùng container tương thích. |
| Deploy Boot 3.3 WAR lên Tomcat 9 bị lỗi. | Tomcat 9 dùng Javax Servlet cũ, Boot 3.3 dùng Jakarta. | Chọn container hỗ trợ Servlet/Jakarta phù hợp, ví dụ Tomcat 10.1 theo chính sách. |
| `@SpringBootApplication` có `main` nhưng deploy WAR không khởi động webapp. | Không có `SpringBootServletInitializer`/bootstrap external đúng; sai context path. | Kiểm tra initializer, logs, URL theo context path; xem WAR class locations. |
| `java -jar` trả 200 trên 18085, external WAR không có URL `localhost:18085/ping`. | External Tomcat port/context khác; `server.port` không điều khiển connector ngoài. | Xem Tomcat `server.xml`/logs, đúng context path và connector port. |
| Gradle tests fail với missing servlet classes khi dùng `compileOnly`. | `compileOnly` không được thêm vào test runtime phù hợp. | Đổi sang `providedRuntime` và kiểm tra `testRuntimeClasspath`/`bootWar`. |
| Maven `provided` vẫn tồn tại trong WAR. | Đây là hành vi **đúng** ở `WEB-INF/lib-provided`. | Phân biệt nhánh lib-provided với lib; không cố xóa tất cả. |
| Unit tests pass nhưng deploy ngoài fail. | MockMvc không thử external container lifecycle, servlet compatibility hoặc context path. | Thêm deployment smoke test trong Tomcat ngoài và kiểm tra server logs. |
| Build có nhiều `*.war`, CI deploy nhầm. | Artifact classifier `plain` hoặc `.original`. | Chỉ rõ tên/pattern artifact, xác minh manifest và `WarLauncher`. |
| App fail do `ClassCastException`/duplicate servlet container classes. | Cùng thư viện engine/API ở container và `WEB-INF/lib` hoặc version mismatch. | So archive, container shared libs, scope và classloader policy. |
| API dùng `javax.servlet.*` trong code Boot 3.3. | Chưa chuyển sang Jakarta namespace. | Dùng API `jakarta.servlet.*` tương thích hoặc chỉnh lại kế hoạch nâng phiên bản. |
| App khác nhau giữa `java -jar` và external deploy. | Classpath order, profiles, context path, server-specific config khác nhau. | So startup logs/active profiles, resource/property sources, servlet mappings và runtime graph. |
| `bootWar` task not found. | Thiếu `war` plugin hoặc đang gọi ở sai module. | `./gradlew tasks --all` và kiểm tra `plugins`/module path. |
| `mvn package` chỉ tạo plain WAR. | Không khai báo Boot Maven plugin, thiếu execution `repackage` khi không dùng starter parent. | Xem `help:effective-pom` và packaging output, thêm đúng execution/plugin config. |
| App chạy nhưng `/ping` 404 khi deploy external. | Context path không như dự kiến, controller không được scan hoặc webapp deploy fail. | Kiểm tra context root, Servlet mappings, container logs và app class package. |

### 13.1. Trình tự chẩn đoán theo nguyên nhân

1. **Project type:** Servlet Spring MVC hay WebFlux? Bài này áp cho Servlet WAR.
2. **Build type:** Maven `packaging=war` / Gradle `war` + Boot plugin đã có chưa?
3. **Dependency graph:** Tomcat starter scope/configuration chính xác?
4. **Archive:** Tomcat ở `WEB-INF/lib-provided` hay nhầm `WEB-INF/lib`?
5. **Launcher:** executable WAR có `WarLauncher`/`Start-Class` đúng?
6. **External bootstrap:** `SpringBootServletInitializer` và compatibility container/Jakarta/JDK đúng?
7. **Server configuration:** port, context path, HTTPS, profiles, logs.
8. **Behavior:** HTTP smoke và test report thực sự đạt ở cả hai chế độ.

Đừng “chữa” bằng cách chuyển toàn bộ dependency sang `implementation` hoặc xóa `lib-provided`: cả hai đều có thể che lỗi ở một chế độ chạy và tạo lỗi ở chế độ còn lại.

## 14. Các biến thể và giới hạn phạm vi

### 14.1. Tomcat, Jetty, Undertow

Ví dụ dùng Tomcat vì `spring-boot-starter-web` trong Spring Boot 3.3 mặc định dùng Tomcat. Nếu muốn dùng Jetty/Undertow:

- **Đầu tiên** exclude Tomcat starter từ Web starter theo đúng cú pháp build tool.
- **Sau đó** khai báo dependency engine thay thế phù hợp với Boot version, scope/configuration theo tiêu chí standalone/external.
- **Cuối cùng** kiểm tra WAR layout, test classpath, container API compatibility và packaged smoke.

Không chỉ đổi artifactId ở một dòng rồi mặc định WAR sẽ deploy tới mọi servlet server. Ví dụ external server vẫn là Tomcat còn standalone dùng Jetty có thể phát sinh lớp tương thích khác với demo Tomcat/Tomcat.

### 14.2. WebFlux không có cùng mô hình traditional WAR

Spring WebFlux không phụ thuộc chặt vào Servlet API và mặc định dùng Reactor Netty; tài liệu Spring Boot 3.3 ghi nhận **traditional WAR deployment không hỗ trợ cho ứng dụng WebFlux** theo mô hình này. Đừng dùng `providedRuntime` Tomcat và `SpringBootServletInitializer` để biến một WebFlux-only app thành Servlet WAR một cách máy móc.

### 14.3. Multi-module Maven/Gradle

Nếu repository có `core` là library và `webapp` là ứng dụng:

- Áp WAR packaging và provided servlet container tại **webapp module**, không nhân bản tại tất cả modules.
- `core` chỉ cần publish library JAR theo Java/Maven conventions.
- Internal project dependencies của `webapp` sẽ vào `WEB-INF/lib` nếu là runtime libraries, không nên bị loại vì groupId chung.
- Parent/BOM quản lý versions nhưng không tự chọn provided scope cho từng module.
- Chọn đúng module khi chạy build/verify, ví dụ Gradle `:webapp:bootWar`; Maven có `-pl webapp`, nhưng chuẩn bị internal reactor dependencies theo quy trình phù hợp.

### 14.4. Container image, native image và executable JAR

Nếu hệ thống vận hành bằng OCI image/kubernetes hoặc native executable, việc chọn JAR hay WAR có thể khác. Bài học là về **WAR để chạy bằng embedded/external Servlet container**, không áp toàn bộ `WEB-INF/lib-provided` assertions cho executable JAR hay native image. Một Boot executable **JAR** không tạo `WEB-INF/lib-provided` theo cùng cách.

### 14.5. Security và dependency hygiene

Đặt Tomcat JAR dưới `lib-provided` không làm lỗ hổng Tomcat tự hết. Standalone vẫn sử dụng phiên bản Tomcat **được đóng trong WAR**; external deployment sử dụng Tomcat **của máy chủ ngoài**. Vì vậy phải:

- Quản lý/vá lỗi **hai môi trường riêng** (packaged Tomcat vs external Tomcat).
- Lưu phiên bản Spring Boot plugin, BOM và servlet container đã kiểm thử.
- Không để credential/logs nhạy cảm trong WAR.
- Quét dependency và artifact, lưu SBOM/provenance khi tổ chức yêu cầu.
- Kiểm tra license/servlet APIs/classloader conflicts khi nâng phiên bản.

## 15. Bài thực hành và tiêu chí kiểm chứng

### Bài A — Maven `provided`

1. Dùng Java source/test ở mục 6 và `pom.xml` ở mục 7.
2. Chạy `./mvnw -version`, `./mvnw clean verify` và đọc `target/surefire-reports`, xác nhận `pingRespondsWithPong` thực sự chạy/pass.
3. Chạy `./mvnw dependency:tree` và xác nhận starter Tomcat ở scope đã chọn.
4. Dùng `jar tf target/war-demo-0.0.1-SNAPSHOT.war` để thấy `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`.
5. Dùng script mục 10.3 (đúng path) để kiểm tra Tomcat nằm ở nhánh `lib-provided` và không nằm dưới `lib`.
6. Chạy `java -jar ...war --server.port=18085`, gọi `GET /ping` và ghi status/body.
7. Nếu có Tomcat ngoài tương thích, deploy bản WAR này ở môi trường test và gọi URL theo context/connector thật. Ghi logs/HTTP result.

### Bài B — Gradle `providedRuntime`

1. Dùng cùng Java source/test với `build.gradle` mục 8.
2. Chạy `./gradlew --version` và `./gradlew tasks --all`, xác nhận `bootWar` xuất hiện.
3. Chạy `./gradlew clean build`, đọc test report `build/reports/tests/test`.
4. Xem `runtimeClasspath`/`testRuntimeClasspath`, chạy `jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war`.
5. Chứng minh Tomcat ở `WEB-INF/lib-provided`. So kết quả với một bản **thử nghiệm, không dùng để release** thay `providedRuntime` bằng `compileOnly`; giải thích vì sao classpath test/package không tương đương.
6. Chạy executable WAR và, nếu có, deploy external Tomcat test như bài A.

### Bài C — đánh giá bằng chứng trên hai runtime

Điền bảng dựa trên **kết quả thật**:

| Điều cần xác nhận | Standalone executable WAR | External Tomcat deployment |
| --- | --- | --- |
| Ai tạo HTTP connector/port? | Embedded Tomcat trong JVM app. | External Tomcat server. |
| Runtime classpath chứa provided libs từ đâu? | `WEB-INF/lib-provided` qua Boot Launcher. | External container classpath; `lib-provided` không là webapp lib chuẩn. |
| Entry point/bootstrap | `WarLauncher` + `main()`. | `SpringBootServletInitializer` + Servlet container. |
| URL `GET /ping` | Theo `server.port`/app config. | Theo connector port và context root của container. |
| Thế nào là PASS? | `java -jar` chạy, HTTP 200/`pong`. | Deploy startup log thành công, HTTP 200/`pong` tại đúng context. |

### Câu hỏi tự kiểm tra

1. Tại sao `spring-boot-starter-tomcat` phải được đánh dấu `provided` khi Maven tạo WAR deploy vào Tomcat ngoài?
2. Tại sao Spring Boot không bỏ hẳn Tomcat khỏi WAR mà đặt nó vào `WEB-INF/lib-provided`?
3. `WEB-INF/lib` và `WEB-INF/lib-provided` khác nhau khi chạy `java -jar` và khi external container deploy ở điểm nào?
4. Vì sao Gradle `compileOnly` không thay được `providedRuntime` cho bài toán có test và executable WAR?
5. Trong POM có Web starter đã kéo Tomcat, tại sao còn khai báo Tomcat trực tiếp với `scope=provided`?
6. `WarLauncher` khác `SpringBootServletInitializer` thế nào về thời điểm thực thi?
7. Vì sao `server.port` không đổi port Tomcat ngoài?
8. Khi build tạo `*-plain.war` và executable `*.war`, bạn nhận diện chúng bằng cách nào?
9. Vì sao một MockMvc test pass chưa thể kết luận WAR deploy đúng trên external container?
10. WAR chạy ở Tomcat 10.1 nhưng fail trên Tomcat 9, cần kiểm tra API/namespace nào?

### Checklist đạt bài

- [ ] Nêu đúng nhiệm vụ của embedded server so với external servlet container.
- [ ] Phân biệt `spring-boot-starter-web`, `spring-boot-starter-tomcat` và Spring Boot Maven/Gradle plugins.
- [ ] Maven POM có `<packaging>war</packaging>` và Tomcat starter `<scope>provided</scope>`.
- [ ] Gradle áp `war` plugin và Tomcat starter qua `providedRuntime`, không đánh đồng `compileOnly`.
- [ ] Java app extends `SpringBootServletInitializer` và có `main()` để hỗ trợ hai entrypoints.
- [ ] Hiểu Spring Boot 3.3 cần Java 17+ và Jakarta/Servlet container tương thích.
- [ ] Phân biệt `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`.
- [ ] Kiểm tra manifest launcher và runtime dependency placement bằng `jar tf`.
- [ ] Test JUnit/MockMvc thật chạy và report pass.
- [ ] `java -jar executable.war` khởi động, `GET /ping` trả 200/`pong`.
- [ ] External container deploy thử ở đúng connector/context path, không nhầm `server.port`.
- [ ] Không deploy nhầm plain WAR hoặc Maven `.original`.
- [ ] Biết chẩn đoán duplicate Tomcat classes, sai Servlet namespace và thiếu provided runtime.
- [ ] Biết rằng version/server security phải quản lý riêng cho standalone và external deployment.

**Tiêu chí hoàn tất:** tạo được một WAR có thể **chạy standalone và deploy vào external Servlet container tương thích**; chứng minh `WEB-INF/lib-provided` chứa Tomcat embedded, `WEB-INF/lib` không bị trộn Tomcat engine, test report pass và có response HTTP thực ở cả hai chế độ (nếu môi trường có external server). Khi external server chưa có sẵn, ghi rõ phần **chưa kiểm chứng**, không suy từ build xanh rằng external deployment chắc chắn thành công.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.3.13 — System Requirements and Servlet Containers](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3.13 API — WarLauncher](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/WarLauncher.html)
- [Spring Boot — Executable Archive Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)

**Ghi nhớ:** Maven `provided` và Gradle `providedRuntime` không phải là thao tác “bỏ Tomcat khỏi WAR”; chúng giúp **đặt Tomcat nhúng vào `WEB-INF/lib-provided`** để executable WAR vẫn chạy bằng `java -jar`, trong khi external Servlet container không bị xung đột với máy chủ mà nó đã cung cấp. Đó là quy tắc cần được kiểm chứng bằng cấu trúc WAR và **hai đường chạy thực tế**, không chỉ bằng file cấu hình build.