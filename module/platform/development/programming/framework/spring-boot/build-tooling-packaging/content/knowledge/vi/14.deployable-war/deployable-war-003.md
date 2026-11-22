# Tạo WAR bằng Maven war và Spring Boot repackage

Một dự án Spring Boot có thể cần tạo **WAR** để triển khai vào servlet container bên ngoài như Apache Tomcat, thay vì chỉ phân phối executable JAR. Với Maven, có hai công việc rất dễ bị xem là một:

1. **`maven-war-plugin:war`** gom mã đã biên dịch, resources và dependencies cần thiết thành một **Web Application Archive** tuân theo cấu trúc `WEB-INF`.
2. **`spring-boot-maven-plugin:repackage`** lấy WAR vừa tạo làm đầu vào, thêm **Spring Boot Loader**, điều chỉnh manifest và sắp xếp các runtime/provided dependencies để thành **executable WAR** — vừa có thể chạy bằng `java -jar`, vừa có thể triển khai lên servlet container tương thích.

**Điểm cốt lõi:** `<packaging>war</packaging>` không đồng nghĩa đã có một WAR chạy được bằng `java -jar`. Maven WAR Plugin và Spring Boot Maven Plugin đảm nhiệm **hai bước khác nhau** trong lifecycle. Với Spring Boot starter parent và cấu hình chuẩn, `mvn clean package` thực thi chúng theo đúng thứ tự.

Bài học sử dụng **Java 17, Spring Boot 3.3.13, Maven 3.9.x** và một ứng dụng Spring MVC nhỏ. Ví dụ là cố định để có thể làm theo; khi đưa vào production cần chọn Java/Spring Boot/Maven plugin và servlet container phù hợp với phiên bản còn được hỗ trợ trong hệ thống của bạn. Lưu ý Spring Boot 3.x chuyển sang **Jakarta Servlet** (`jakarta.servlet.*`), nên không thể mặc định deploy bản WAR mới lên mọi server Servlet cũ còn dùng `javax.servlet.*`.

## 1. WAR là gì? Khi nào nên chọn WAR thay vì JAR?

**WAR (Web Application Archive)** cũng là archive dạng ZIP như JAR, nhưng theo quy ước Java servlet web application: application classes/resources dưới `WEB-INF/classes`, các dependency thư viện web dưới `WEB-INF/lib`, còn resources phục vụ trực tiếp có thể ở các vị trí web application hợp lệ.

Một dự án Spring Boot servlet web thường có hai lựa chọn vận hành:

- **Executable JAR:** `java -jar service.jar`; Spring Boot Loader khởi động ứng dụng với embedded servlet server được đóng gói.
- **WAR triển khai lên servlet container:** copy/deploy `service.war` vào Tomcat tương thích; Tomcat quản lý process, cổng, context path và servlet lifecycle cho ứng dụng.
- **Executable WAR (Spring Boot):** vẫn là WAR triển khai truyền thống **và** được bổ sung Boot Loader, vì thế còn có thể chạy độc lập bằng `java -jar service.war`.

Bảng so sánh:

| Đặc điểm | WAR thường sau `maven-war-plugin` | WAR sau `spring-boot:repackage` | Spring Boot executable JAR |
| --- | --- | --- | --- |
| Đuôi tệp | `.war` | `.war` | `.jar` |
| Lớp ứng dụng | `WEB-INF/classes` | `WEB-INF/classes` | `BOOT-INF/classes` |
| Thư viện web/runtime | `WEB-INF/lib` | `WEB-INF/lib` | `BOOT-INF/lib` |
| Thư viện được đánh dấu `provided` | Không đặt vào `WEB-INF/lib` của WAR tiêu chuẩn | Được Boot bố trí ở `WEB-INF/lib-provided` nếu cần cho executable WAR | Boot repackaging có quy tắc riêng, không nên suy từ layout WAR |
| Boot Loader/manifest executable | Không được WAR Plugin tự thêm | Có `WarLauncher`, `Main-Class` và `Start-Class` | Có `JarLauncher`, `Main-Class` và `Start-Class` |
| Chạy bằng `java -jar` | Không phải khả năng mặc định | Có | Có |
| Triển khai vào external servlet container | Đúng mục đích | Vẫn phù hợp nếu application và container tương thích | Không dùng trực tiếp như WAR truyền thống |

**Đừng hiểu “executable WAR” là file chạy được mà không cần Java.** `java -jar` vẫn cần JVM tương thích. Ở chế độ triển khai ngoài, chính servlet container phải đáp ứng yêu cầu Servlet/Jakarta/Spring Boot của ứng dụng.

## 2. Hai bước Maven đóng gói: `war:war` rồi `spring-boot:repackage`

Với project có `<packaging>war</packaging>`:

```text
pom.xml + src/main/java + src/main/resources [+ src/main/webapp]
                               |
                               v
Maven lifecycle: validate -> compile -> test -> package
                               |
                               v
[1] maven-war-plugin:war
    Gom WEB-INF/classes và dependencies compile/runtime vào WAR thường
    Không tự dựng Boot Loader / executable manifest
                               |
                               v
    target/war-demo-1.0.0.war (WAR gốc)
                               |
                               v
[2] spring-boot-maven-plugin:repackage
    Đọc WAR gốc, thêm Spring Boot Loader/WarLauncher
    Bổ sung WEB-INF/lib-provided cho provided dependencies
    Thiết lập manifest Main-Class/Start-Class
                               |
                +--------------+----------------+
                |                               |
                v                               v
 target/war-demo-1.0.0.war      target/war-demo-1.0.0.war.original
    (executable WAR)                    (WAR trước repackage)
```

Kết quả `.original` là cách xử lý mặc định khi `repackage` **thay thế main artifact** và không sử dụng classifier riêng. Nếu project tùy biến `classifier`, `attach` hoặc tên archive, có thể xuất hiện kết quả khác. Luôn kiểm tra tệp thực tế sau build.

### Vì sao dùng `mvn clean package`?

- `clean` xóa output build cũ; giúp tránh dùng nhầm WAR cũ chưa được tái đóng gói.
- `package` đi qua các phase trước đó và gọi plugin đã được bind theo packaging/lifecycle.
- Với `war` packaging, Maven bind goal `war:war` vào phase `package`.
- Khi kế thừa `spring-boot-starter-parent` và **khai báo Spring Boot Maven Plugin**, parent cung cấp execution cho `repackage`, để nó chạy sau bước tạo WAR gốc tại phase tương ứng.

**Không chỉ gọi `mvn spring-boot:repackage` trên một workspace sạch**: goal `repackage` cần source JAR/WAR đã được tạo. Tài liệu plugin khuyến nghị để lifecycle tạo archive trước, hoặc dùng `mvn package spring-boot:repackage` khi cần gọi goal trực tiếp. Nếu starter parent đã bind `repackage` trong `package`, hãy ưu tiên `mvn clean package` một lần, tránh chạy thêm goal trùng không cần thiết.

### `war:war` độc lập với Boot `repackage`

Nếu muốn quan sát riêng kết quả WAR Plugin (sau khi có mã đã compile):

```bash
mvn clean compile war:war
```

Câu lệnh trên gọi Maven WAR Plugin để tạo WAR truyền thống từ compiled classes và dependencies. Nó **không tự thêm** Boot launcher bằng goal `repackage`. Nó cũng không thay thế cho `mvn test`/`mvn verify` trong kiểm soát chất lượng. Sau khi học xong bước này, chạy quy trình chuẩn:

```bash
mvn clean verify
```

`verify` đi qua `package`, vì thế với POM chuẩn của bài, WAR tạo ra ở `target` sẽ là **WAR đã được Boot tái đóng gói**. Đừng dựa vào việc cả hai lệnh đều tạo file `.war` mà kết luận nội dung giống nhau.

## 3. WAR deploy lên container không khởi động theo `WarLauncher`

Một khác biệt quan trọng về cách khởi động:

**Khi chạy độc lập:**

```bash
java -jar target/war-demo-1.0.0.war
```

Java launcher đọc `META-INF/MANIFEST.MF`, dùng `Main-Class` để gọi `org.springframework.boot.loader.launch.WarLauncher`. Loader của Spring Boot dựng classpath từ `WEB-INF/classes`, `WEB-INF/lib` **và** `WEB-INF/lib-provided`, sau đó gọi main class ứng dụng qua `Start-Class`. Embedded Tomcat được đưa vào classpath lúc này.

**Khi deploy lên Tomcat ngoài:**

```text
Tomcat đang chạy
    |
    v
Tomcat nhận WAR và thực thi servlet deployment lifecycle
    |
    v
Lớp trong WEB-INF/classes + JARs ở WEB-INF/lib
    |
    v
Spring WebApplicationInitializer / SpringBootServletInitializer
    |
    v
SpringApplicationBuilder cấu hình application context
    |
    v
Spring MVC DispatcherServlet + controller
```

Tomcat **không** chạy `WarLauncher` bằng `java -jar` khi deploy WAR như một web application. Nó dùng servlet discovery/initialization và classloader của container. Các JAR đặt trong `WEB-INF/lib-provided` không phải thư viện webapp thông thường cần container nạp; servlet container dùng những thư viện đã được cung cấp ở tầng server.

Vì hai đường khởi động khác nhau, lớp ứng dụng nên hỗ trợ **cả `main(String[])` và `SpringBootServletInitializer`** nếu muốn chính một WAR chạy được theo cả hai cách.

## 4. Thiết lập chính xác cho Spring Boot 3.x

Trước khi viết POM, xác định bốn điều:

1. **Servlet app:** dùng `spring-boot-starter-web` (Spring MVC / servlet stack). Ứng dụng WebFlux thuần chạy Reactor Netty mặc định **không** hỗ trợ mô hình WAR truyền thống này như một lựa chọn tương đương.
2. **WAR packaging:** `<packaging>war</packaging>` để Maven dùng lifecycle và Maven WAR Plugin tương ứng.
3. **Provided servlet container dependency:** thêm dependency trực tiếp `spring-boot-starter-tomcat` với `<scope>provided</scope>`. Đây là cách nói external container chịu trách nhiệm cung cấp Tomcat/Servlet API khi deploy WAR.
4. **Bootstrap cho external container:** main application class extends `SpringBootServletInitializer` và override `configure(SpringApplicationBuilder)`.

**Tương thích quan trọng:** Spring Boot 3.x dựa trên Jakarta EE/Servlet namespaces. Với Spring Boot 3.3, Tomcat 10.1 là họ container thông dụng phù hợp; **Tomcat 9 (javax.servlet) không phải đích triển khai tương thích**. Không chỉ nhìn tên “Tomcat” mà bỏ qua API và Java baseline. Ngoài tương thích Servlet API, phải kiểm tra server version còn nhận hỗ trợ bảo mật, cấu hình, các library xung đột và chính sách của tổ chức.

## 5. Ví dụ hoàn chỉnh Java 17: một WAR deploy ngoài và chạy bằng `java -jar`

Ví dụ nhỏ trả về chuỗi cố định `Hello WAR` từ endpoint `/hello`, có test bằng MockMvc. Cấu hình Maven tạo **WAR thực thi** thay cho JAR mặc định.

### 5.1. Cấu trúc thư mục

```text
war-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/wardemo/
    │   │   ├── WarDemoApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/dev/example/wardemo/
            └── HelloControllerTest.java
```

Không cần tệp `web.xml` cho Spring Boot MVC thông thường với Java Servlet initializer mechanism và cấu hình plugin phù hợp. Maven WAR Plugin có thể tạo WEB-INF layout dù `src/main/webapp` không có tài nguyên tĩnh đặc biệt. Nếu ứng dụng legacy có JSP/web.xml, đó là trường hợp mở rộng ở mục sau.

### 5.2. `pom.xml` đầy đủ

```xml
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

    <groupId>dev.example</groupId>
    <artifactId>war-demo</artifactId>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>dev.example.wardemo.WarDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Đọc POM theo trách nhiệm:**

- `<packaging>war</packaging>` quyết định loại project artifact và lifecycle binding.
- `maven-war-plugin` tạo WAR webapp theo `WEB-INF`. Ở ví dụ chọn version `3.4.0` rõ ràng; `failOnMissingWebXml=false` cho phép dự án không có `web.xml`. Starter parent vốn cũng hỗ trợ cấu hình WAR Plugin; khai báo tường minh giúp người học nhìn rõ bước này.
- `spring-boot-maven-plugin` tái đóng gói bằng `repackage`. Khi kế thừa `spring-boot-starter-parent`, goal đã có execution; ở ví dụ chỉ cần thêm plugin và `mainClass` để nó chạy trong `package`.
- `mainClass` nói rõ **application entry point**; Spring Boot Maven Plugin điều khiển manifest để executable WAR khởi chạy qua `WarLauncher`, không phải ghi thẳng application class vào `Main-Class`.
- `spring-boot-starter-web` mang Spring MVC và mặc định starter cho Tomcat nhúng theo Spring Boot conventions.
- Khai báo lại trực tiếp `spring-boot-starter-tomcat` với scope `provided` để Maven giải quyết nó dưới scope này, thay vì đóng embedded server vào `WEB-INF/lib` như một runtime dependency webapp thông thường.
- `spring-boot-starter-test` chỉ dùng cho test, không đi vào runtime WAR.

**Lưu ý:** `provided` không có nghĩa Maven không tải dependency và cũng không có nghĩa nó thiếu trong compile/test classpath. Scope `provided` loại nó khỏi thư viện webapp thông thường và để external container cung cấp, còn Spring Boot `repackage` bố trí các provided artifacts vào `WEB-INF/lib-provided` để executable WAR **vẫn tự chạy** được bằng `java -jar`.

### 5.3. Application class với hai entry path

Tạo `src/main/java/dev/example/wardemo/WarDemoApplication.java`:

```java
package dev.example.wardemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
```

Giải thích hai entry:

- Khi chạy `java -jar`, Boot `WarLauncher` đọc `Start-Class` rồi gọi `main(args)`; `SpringApplication.run(...)` tạo application context và khởi tạo embedded Tomcat.
- Khi container ngoài deploy WAR, Spring's servlet initializer mechanism dẫn tới `SpringBootServletInitializer.configure(...)` để dựng context mà **không cần gọi `main(args)`**.
- Cùng một `@SpringBootApplication` giữ cấu hình gốc nhất quán cho hai đường khởi động. Nếu dự án có cấu hình `SpringApplicationBuilder` chuyên biệt (profiles, banner, listeners), nên chia sẻ logic giữa `configure` và `main` để tránh hai kiểu chạy khác nhau ngoài ý muốn.

### 5.4. REST controller

Tệp `src/main/java/dev/example/wardemo/HelloController.java`:

```java
package dev.example.wardemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello WAR";
    }
}
```

Class ở cùng package root với application và nằm trong component scan mặc định. Không cần viết `DispatcherServlet` hay servlet mapping XML cho ví dụ đơn giản này.

### 5.5. Cấu hình chung

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: war-demo
```

Cố tình **không** cấu hình `server.port` và `server.servlet.context-path` ở đây để thấy sự khác nhau giữa hai chế độ chạy. Khi chạy độc lập, Spring Boot embedded Tomcat mặc định dùng port 8080 nếu không bị override. Khi deploy Tomcat ngoài, **Tomcat** quyết định connector port và webapp context path theo WAR filename/deployment config; không được giả định hai môi trường có URL giống nhau.

### 5.6. Test bằng MockMvc

Tệp `src/test/java/dev/example/wardemo/HelloControllerTest.java`:

```java
package dev.example.wardemo;

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
class HelloControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void returnsHelloWar() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello WAR"));
    }
}
```

Test chứng minh application context và controller hoạt động trong **test classpath của Maven**. Nó không tự chứng minh **WAR sau `repackage`** chạy bằng `java -jar` hoặc deploy thành công vào Tomcat ngoài. Vì vậy phần dưới có kiểm tra archive và smoke test riêng.

## 6. Build WAR bằng Maven và quan sát goal thực sự chạy

Tại thư mục chứa `pom.xml`, với Java 17 và Maven tương thích:

```bash
mvn -version
mvn clean verify
```

Nếu dự án có Maven Wrapper, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `mvnw.cmd` trên Windows. Lệnh `verify` đi qua `package`, chạy biên dịch, test, tạo WAR và Spring Boot `repackage` theo cấu hình.

Trong log build, hai nhóm plugin quan trọng là:

```text
maven-war-plugin:...:war
spring-boot-maven-plugin:...:repackage
```

Số phiên bản/thứ tự những dòng log khác phụ thuộc effective POM, Maven/plugin implementation. Không kiểm tra chỉ một substring `BUILD SUCCESS`; hãy xác định cả hai goal và artifact cuối.

Sau khi hoàn tất, ví dụ mặc định có:

```text
target/war-demo-1.0.0.war
target/war-demo-1.0.0.war.original
```

- `.war`: executable WAR đã qua Boot `repackage`.
- `.war.original`: WAR gốc do Maven WAR Plugin tạo trước khi Boot repackage, giữ lại theo quy tắc mặc định.
- File `.original` vẫn là một ZIP/WAR archive hợp lệ về byte, nhưng không được tự xem là executable WAR.
- Khi có custom output name/classifier/attach, tệp phát hành có thể khác; phải dựa vào package metadata và nội dung.

### Không dùng goal `repackage` sai thời điểm

Không chạy riêng:

```bash
mvn clean spring-boot:repackage
```

trên workspace sạch rồi kỳ vọng Boot tự biết tạo một WAR đầu vào. Goal `repackage` xử lý **source archive đã tạo** ở bước package; nó không thay thế Maven WAR Plugin. Với starter parent, giải pháp đúng nhất là:

```bash
mvn clean package
```

Nếu project không bind tự động mà muốn gọi thủ công goal, tài liệu Boot hướng dẫn:

```bash
mvn package spring-boot:repackage
```

Nhưng **đừng dùng lệnh này như thói quen trên POM đã bind `repackage` trong phase package** vì có thể chạy lại không cần thiết. Hãy kiểm tra `mvn help:effective-pom` và execution ID trước.

## 7. Nội dung của WAR thường so với WAR sau `repackage`

Trước `repackage`, Maven WAR Plugin tạo những vị trí phục vụ servlet deployment:

```text
war-demo-1.0.0.war.original
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   ├── dev/example/wardemo/WarDemoApplication.class
│   │   ├── dev/example/wardemo/HelloController.class
│   │   └── application.yml
│   └── lib/
│       ├── spring-webmvc-*.jar
│       ├── spring-boot-*.jar
│       └── các compile/runtime libraries khác
└── ... web assets nếu có
```

Đây là **WAR thường**; `maven-war-plugin` không tự tạo Boot `WarLauncher`. Vì Tomcat ngoài đã có Servlet runtime, provided dependencies không cần nằm trong `WEB-INF/lib`.

Sau `repackage`:

```text
war-demo-1.0.0.war
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   ├── launch/WarLauncher.class
│   └── ... các Boot loader classes khác
└── WEB-INF/
    ├── classes/
    │   ├── dev/example/wardemo/WarDemoApplication.class
    │   ├── dev/example/wardemo/HelloController.class
    │   └── application.yml
    ├── lib/
    │   ├── spring-boot-3.3.13.jar
    │   ├── spring-webmvc-*.jar
    │   └── các runtime dependencies khác
    └── lib-provided/
        ├── tomcat-embed-core-*.jar
        ├── tomcat-embed-el-*.jar
        └── các provided dependencies cần cho standalone mode
```

Sơ đồ là đại diện, không phải danh sách đủ từng dependency. `tomcat-embed-websocket-*.jar` và những artifact khác có thể xuất hiện tùy resolved dependency graph. Tên và version chính xác phải xem output thật.

**Ba điểm bất biến về ý nghĩa:**

1. `WEB-INF/classes` chứa code/resource của ứng dụng ở cả hai kiểu WAR.
2. `WEB-INF/lib` chứa các dependency mà servlet container cần thấy khi triển khai WAR.
3. `WEB-INF/lib-provided` là phần bổ sung của **executable WAR Spring Boot** để Boot `WarLauncher` dùng khi chạy độc lập. External servlet container thông thường không xem đó là `WEB-INF/lib`.

Đặc biệt, `WEB-INF/lib-provided` **không phải** thư mục do Maven WAR Plugin bắt buộc tạo cho mọi WAR; nó xuất hiện do chiến lược repackage của Boot khi có provided dependencies.

## 8. Manifest và `WarLauncher`

Một executable WAR của ví dụ dự kiến có các thuộc tính quan trọng trong `META-INF/MANIFEST.MF`:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: dev.example.wardemo.WarDemoApplication
Spring-Boot-Version: 3.3.13
```

Manifest thực tế có thể có các thuộc tính khác. Cần phân biệt:

- `Main-Class`: Java launcher đọc để biết **lớp Boot Loader** cần gọi đầu tiên.
- `Start-Class`: Spring Boot Loader đọc để biết **main class ứng dụng**. Đây không phải thuộc tính chuẩn Java dùng thay thế `Main-Class`.
- `WarLauncher`: lớp loader hiểu `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`.
- `SpringBootServletInitializer`: **khác** `WarLauncher`; nó phục vụ servlet-container deployment path. Khi external Tomcat deploy WAR, Tomcat không gọi `java -jar` nên không dùng `Main-Class` làm entry point của ứng dụng theo cách standalone.

Đây là ví dụ rõ nhất của **“một archive, hai cơ chế khởi động”**.

### Đọc manifest không cần giải nén toàn bộ WAR

Linux/macOS có `unzip`:

```bash
unzip -p target/war-demo-1.0.0.war META-INF/MANIFEST.MF
```

Hoặc JDK tool trong thư mục làm việc tách biệt:

```bash
mkdir -p target/war-inspect
cd target/war-inspect
jar xf ../war-demo-1.0.0.war META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Sau khi `cd` vào thư mục inspect, quay lại project root trước khi dùng các lệnh `target/...` trong các bước tiếp theo. Không nên bung WAR vào source tree rồi commit output build.

### Kiểm tra nội dung archive

```bash
jar tf target/war-demo-1.0.0.war
jar tf target/war-demo-1.0.0.war.original
```

Ở executable WAR, cần thấy tối thiểu những entry kiểu:

```text
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/dev/example/wardemo/WarDemoApplication.class
WEB-INF/classes/dev/example/wardemo/HelloController.class
WEB-INF/lib/spring-boot-3.3.13.jar
WEB-INF/lib-provided/tomcat-embed-core-*.jar
```

Dòng dùng `*` là **mẫu tên** để tìm trong output, không phải một entry thực chứa ký tự `*`. Manifest và archive layout đúng là điều kiện cần, **chưa đủ** để bảo đảm ứng dụng khởi động trên mọi runtime environment.

### PowerShell trên Windows

```powershell
jar tf target/war-demo-1.0.0.war |
    Select-String 'WarLauncher|WEB-INF/classes|WEB-INF/lib-provided'
```

Lệnh trên lọc các tên entry trong WAR. Với project mẫu, phải tìm được WarLauncher class, application class và provided Tomcat JAR trong output.

## 9. Chạy executable WAR độc lập bằng `java -jar`

Khi WAR đã qua `repackage`, không cần cài Tomcat ngoài để chạy thử standalone. Với Java 17:

```bash
java -jar target/war-demo-1.0.0.war
```

Boot loader mở WAR, đưa `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` vào classpath cần thiết; embedded Tomcat từ provided group được sử dụng trong chế độ **standalone**.

Sau khi log báo server sẵn sàng, trong **terminal khác**:

```bash
curl -s http://localhost:8080/hello
```

Body mong đợi:

```text
Hello WAR
```

Nếu muốn tránh cổng đã bị ứng dụng khác dùng:

```bash
java -jar target/war-demo-1.0.0.war --server.port=8081
```

Rồi ở terminal thứ hai:

```bash
curl -s http://localhost:8081/hello
```

Body vẫn là `Hello WAR`. Tham số `--server.port=8081` là cấu hình Spring Boot runtime cho **embedded server** khi chạy độc lập; nó không sửa manifest/`WEB-INF/lib` hay cổng của external Tomcat server.

**Nếu `java -jar ...war.original` thất bại**, đây không nhất thiết là lỗi Maven WAR Plugin: WAR nguyên bản không có Spring Boot `WarLauncher`/executable manifest. Muốn chạy WAR thông thường, deploy vào external servlet container; muốn standalone, chạy bản đã repackage.

## 10. Triển khai cùng WAR vào external Tomcat

Với Servlet application tương thích Jakarta và external Tomcat đúng phiên bản, servlet container có thể nhận chính `war-demo-1.0.0.war` sau Boot repackage. Nó xử lý WAR theo servlet web application layout; `WEB-INF/lib-provided` không gây xung đột vì không được xem như `WEB-INF/lib` của webapp.

Giả sử external Tomcat đã cài đặt và biến môi trường `CATALINA_BASE` trỏ đúng **cấu hình instance** mà bạn được phép triển khai; dừng hoặc chuẩn bị Tomcat theo quy trình vận hành của bạn.

Linux/macOS:

```bash
cp target/war-demo-1.0.0.war "$CATALINA_BASE/webapps/war-demo.war"
```

Tương đương trên PowerShell:

```powershell
Copy-Item target/war-demo-1.0.0.war "$env:CATALINA_BASE\webapps\war-demo.war"
```

Khi Tomcat auto-deploy hoạt động, ứng dụng thường được mount dưới **context path `/war-demo`** vì tên archive được triển khai là `war-demo.war`. Nếu Tomcat dùng connector HTTP mặc định ở cổng 8080, URL kiểm tra là:

```bash
curl -s http://localhost:8080/war-demo/hello
```

Body mong đợi:

```text
Hello WAR
```

**Các giả định ở ví dụ:** Tomcat chạy tại localhost:8080, deployment thành công, context path do tên WAR quyết định, không có reverse proxy hay cấu hình context riêng. Ở hệ thống thực, port, hostname, TLS, context path và quyền deploy đều do **external container/infrastructure** quyết định. Nếu WAR được đặt tên `ROOT.war` thì context path thường là `/`; nếu có cấu hình context descriptor thì có thể khác nữa.

### Cơ chế khác `java -jar`

Khi Tomcat deploy WAR:

1. Tomcat giải nén/đọc WAR, tạo web application classloader và ServletContext.
2. Servlet startup discovery tìm các initializer phù hợp của Spring; `SpringBootServletInitializer` của application giúp dựng Spring application context.
3. Spring MVC đăng ký `DispatcherServlet`, sau đó endpoint `/hello` có thể được gọi dưới context path của Tomcat.
4. Tomcat chịu trách nhiệm mở cổng và vòng đời ứng dụng/container.

Tomcat không cần đọc `Main-Class: ...WarLauncher` để bootstrapping theo kiểu `java -jar`. Lớp `main(String[])` trong application vẫn có mặt nhưng **không phải** đường vào được external container gọi trực tiếp.

### Tương thích và bảo mật

- Với **Spring Boot 3.3**, sử dụng container chạy trên Java tương thích và hỗ trợ **Jakarta Servlet** tương ứng, chẳng hạn họ Tomcat 10.1, không áp dụng hướng dẫn dành cho Tomcat 9/`javax.servlet`.
- Servlet container phải hỗ trợ version API/Servlet initialization mà application và libraries sử dụng.
- Triển khai phải tuân theo quyền, cấu hình TLS/port, quyền ghi tệp, secrets và logging của môi trường thật.
- Không bật Tomcat Manager hoặc endpoint admin công khai chỉ để thử WAR; việc cấu hình quyền triển khai là bước vận hành riêng.

## 11. Vì sao Tomcat `provided` rất quan trọng?

`spring-boot-starter-web` mặc định kéo `spring-boot-starter-tomcat` như một dependency runtime/compile transitive. Khi chuyển project thành external WAR, một **container Tomcat ngoài** đã cung cấp servlet engine.

Nếu để các embedded Tomcat libraries trong `WEB-INF/lib` và deploy lên Tomcat, webapp có thể mang theo bản servlet implementation không cần thiết hoặc xung đột classloading. Vì vậy tài liệu Spring Boot khuyến nghị:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

**Maven scope `provided` có ý nghĩa:**

- Dependency vẫn hiện diện để compiler/test và các plugin cần thiết có thể tham chiếu.
- Maven WAR Plugin **không** đặt nó như dependency runtime thông thường dưới `WEB-INF/lib` của WAR tiêu chuẩn.
- Spring Boot Maven Plugin khi repackage WAR **đưa provided dependencies vào `WEB-INF/lib-provided`**, nhờ đó WAR standalone vẫn chạy được với embedded server qua `WarLauncher`.
- External Tomcat dùng servlet container runtime của chính nó, không cần những JAR ở `WEB-INF/lib-provided`.

Vì thế câu nói “`provided` nghĩa là dependency tuyệt đối không có trong WAR” **sai đối với executable WAR sau Boot repackage**: nó có thể có mặt, nhưng nằm ở thư mục riêng không phải `WEB-INF/lib`.

### Kiểm tra Maven đã giải quyết scope ra sao

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn help:effective-pom
```

Dependency tree cần phản ánh `spring-boot-starter-tomcat` được dự án khai báo trực tiếp theo `provided`. Nếu có version/scope khác đi theo parent hoặc transitive dependencies, sửa dependency management hoặc dependency declaration đúng chỗ thay vì dựa vào file WAR tình cờ chứa/không chứa JAR.

### Nếu dùng Jetty hoặc Undertow

Bạn phải chủ động điều chỉnh web starter/dependency exclusions, chọn servlet container thay thế được Spring Boot hỗ trợ, đồng thời bảo đảm external container tương thích. **Không** giữ Tomcat provided và đồng thời đưa Jetty/Undertow runtime vào `WEB-INF/lib` một cách tùy tiện. Bài này chọn Tomcat để làm rõ Maven `war` và `repackage`, không phải hướng dẫn tổng quát cho mọi server.

## 12. Vai trò của Maven WAR Plugin đối với web resources

Maven WAR Plugin không chỉ copy file `.class`. Nó tổ chức một servlet web application từ các nguồn như:

| Nguồn | Đích thông dụng trong WAR | Ghi chú |
| --- | --- | --- |
| `target/classes` từ compile/resources | `WEB-INF/classes` | Application classes và classpath resources |
| Compile/runtime dependencies | `WEB-INF/lib/*.jar` | Các thư viện webapp cần khi deploy ngoài |
| `src/main/webapp` | Root webapp tương ứng | Tài nguyên web truyền thống, JSP, WEB-INF descriptors khi có |
| `src/main/webapp/WEB-INF/web.xml` | `WEB-INF/web.xml` | Có thể có ở ứng dụng legacy; Spring Boot MVC thường không cần |
| `src/main/resources/static` | Trong classpath, thường `WEB-INF/classes/static` | Spring Boot static-resource handling có quy ước của riêng nó |
| Provided-scope artifacts | Không đưa vào standard `WEB-INF/lib` | Boot `repackage` có thể đặt chúng ở `WEB-INF/lib-provided` |

`war:war` theo mặc định có goal bind ở phase `package` khi `<packaging>war</packaging>`. Cần tránh nhầm với `war:exploded` hoặc `war:inplace`: đó là các kiểu chuẩn bị webapp khác, không có nghĩa Boot loader đã được thêm.

**Không bắt buộc tạo `web.xml` chỉ để đóng gói một Spring MVC application hiện đại**. Với `SpringBootServletInitializer` và servlet initializer mechanism đúng, application có thể được container phát hiện mà không cần descriptor XML. POM minh họa đã đặt `failOnMissingWebXml=false` để Maven WAR Plugin không fail vì thiếu tệp này.

### Khi dùng JSP

JSP có giới hạn về packaging và container, đặc biệt khi chọn executable JAR thay vì WAR. Với bài đang tập trung vào WAR, có thể đặt JSP trong cấu trúc webapp phù hợp và cấu hình JSP engine nếu cần. Tuy nhiên, **đừng kết luận cứ đổi `<packaging>war</packaging>` là JSP tự hoạt động**: template resolver, JSP dependencies, view prefix/suffix, embedded vs external Tomcat và tương thích Jakarta JSTL cần được kiểm tra riêng.

### WAR overlays và webapp files

Maven WAR Plugin còn hỗ trợ **WAR overlays** và cấu hình webResources/file filtering. Chỉ dùng khi cần hợp nhất các ứng dụng/tài nguyên đã xây sẵn. Nếu overlay trùng đường dẫn `WEB-INF` hoặc đổi resources, kiểm tra output của WAR Plugin trước khi Boot repackage; loader không thể sửa sai logic resource overlays.

## 13. Maven starter parent so với chỉ import BOM

Một cấu hình dễ sai là chỉ import Spring Boot BOM mà quên phần plugin/lifecycle. Phân biệt:

| Thành phần | Quản lý gì? |
| --- | --- |
| `spring-boot-dependencies` BOM | Dependency versions theo release Boot |
| `spring-boot-starter-parent` | Kế thừa dependency management và plugin management/executions tiện dụng |
| `maven-war-plugin` | Tạo standard web application WAR ở phase package |
| `spring-boot-maven-plugin` goal `repackage` | Chuyển JAR/WAR đầu vào thành Spring Boot executable archive |
| `SpringBootServletInitializer` | Khởi tạo Spring application context qua external servlet container |

Nếu project chỉ dùng BOM như:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

thì **không tự động** bind `spring-boot:repackage`, không tạo executable manifest và không thêm Boot loader. Với corporate parent, bạn phải khai báo Boot plugin **với version phù hợp** và execution, ví dụ fragment sau nằm trong `build/plugins`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **fragment cho POM dùng parent khác**, không cần chèn thêm vào POM mẫu đang kế thừa starter parent; làm vậy có thể trùng cấu hình hoặc khiến người đọc hiểu sai lifecycle. Bản `spring-boot-starter-parent` mẫu đã cung cấp execution `repackage`.

**Thứ tự plugin:** Spring Boot repackage cần WAR gốc do Maven WAR Plugin tạo. Trong custom build đặc biệt khi bạn tự cấu hình multiple executions ở cùng phase, bảo đảm WAR packaging đã xảy ra trước `repackage`. Với standard WAR packaging + starter parent, lifecycle mặc định đã điều phối hợp lý.

### Không override `Main-Class` từ sai plugin

Boot repackage quản lý `Main-Class` và `Start-Class` trong executable WAR. Muốn chọn application main:

```xml
<configuration>
    <mainClass>dev.example.wardemo.WarDemoApplication</mainClass>
</configuration>
```

đặt dưới **`spring-boot-maven-plugin`**, không sửa thủ công manifest bằng `maven-war-plugin` rồi kỳ vọng Boot sẽ giữ tất cả fields như cũ. Boot plugin có quyền viết lại manifest để phản ánh launcher.

## 14. Giữ cả WAR thường và executable WAR: classifier có chủ đích

Theo mặc định, repackage **thay thế main WAR** và giữ WAR gốc với hậu tố `.original`. Một tổ chức có thể muốn giữ hai artifact có **classifier rõ ràng** để quản lý publication/deployment chính xác.

Fragment cấu hình Spring Boot Maven Plugin dành cho tình huống này:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.example.wardemo.WarDemoApplication</mainClass>
        <classifier>exec</classifier>
    </configuration>
</plugin>
```

Với POM dùng starter parent và nguồn WAR gốc có sẵn, cấu hình repackage classifier có thể tạo/attach một executable WAR phân biệt bằng classifier `exec`, giữ artifact chính là WAR chuẩn. Khi output khác convention, **xác nhận tên file thực tế** trong `target` và artifact metadata đã upload trước khi sửa pipeline. Không tự giả định rằng file không có classifier luôn là executable WAR.

Cách lựa chọn phụ thuộc mục tiêu:

- Nếu **một WAR duy nhất** cần vừa deploy external vừa chạy standalone, mặc định Boot repackage main WAR là đơn giản nhất.
- Nếu cần **tách rõ** standard WAR và executable WAR để publish, classifier giúp xác định artifact nào là gì. Phải test đúng artifact của từng kênh.
- Không phát hành hai artifact với cùng coordinate/version mà nội dung khác nhau vào cùng repository/path.
- Không đẩy `.original` vào kênh phát hành một cách vô tình chỉ vì script dùng glob `target/*`.

**Nhớ rằng WAR đã Boot repackage thường vẫn deploy ngoài được**; tách classifier là nhu cầu quản trị artifact chứ không phải quy định rằng servlet container không nhận WAR có Boot Loader.

## 15. Pipeline CI/CD: kiểm chứng cả artifact lẫn hai chế độ chạy

Một quy trình tối thiểu có thể theo thứ tự:

```text
JDK + Maven/toolchain cố định
           |
           v
mvn clean verify
  - compile
  - unit/integration tests được cấu hình
  - war:war
  - spring-boot:repackage
           |
           v
Xem target/war-demo-1.0.0.war
  - manifest Main-Class = WarLauncher
  - Start-Class đúng class ứng dụng
  - WEB-INF/classes chứa app
  - WEB-INF/lib chứa runtime deps
  - WEB-INF/lib-provided chứa embedded Tomcat
           |
           v
Smoke test 1: java -jar WAR + curl /hello
           |
           v
Smoke test 2: deploy lên Tomcat tương thích
                + curl /war-demo/hello
           |
           v
Publish SHA-256/checksum của đúng WAR đã kiểm chứng
```

**Hai smoke tests có mục đích riêng:**

1. `java -jar` kiểm tra executable manifest/WarLauncher/embedded server và classpath của `lib-provided`.
2. Deploy vào external container kiểm tra `SpringBootServletInitializer`, servlet classloading, compatibility và context path ngoài.

Một test không thay thế test còn lại; `@SpringBootTest`/MockMvc trong POM cũng không tự mô phỏng toàn bộ lifecycle external Tomcat.

### Gate tự động: tìm launcher và provided Tomcat

Linux/macOS có `jar` và `grep`:

```bash
set -e

WAR="target/war-demo-1.0.0.war"

jar tf "$WAR" | grep -q '^org/springframework/boot/loader/launch/WarLauncher.class$'
jar tf "$WAR" | grep -q '^WEB-INF/classes/dev/example/wardemo/WarDemoApplication.class$'
jar tf "$WAR" | grep -q '^WEB-INF/lib-provided/tomcat-embed-core-'
jar tf "$WAR" | grep -q '^WEB-INF/lib/spring-boot-'

echo "PASS: executable WAR structure looks correct"
```

Expected stdout khi mọi lệnh kiểm tra thành công:

```text
PASS: executable WAR structure looks correct
```

Nếu có lỗi, `set -e` khiến script dừng với exit code khác 0. Đây là gate **kiểm tra cấu trúc**, không phải chứng minh toàn bộ app vận hành đúng hay container ngoài tương thích. Kết hợp thêm smoke tests và dependency scanning.

### Đọc WAR manifest trong CI

```bash
unzip -p target/war-demo-1.0.0.war META-INF/MANIFEST.MF
```

Tìm tối thiểu:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: dev.example.wardemo.WarDemoApplication
```

Manifest có thể có thêm entries; điều quan trọng là đúng launcher/main class và archive thực sự chứa classes/dependencies tương ứng.

### Tính tái tạo

Pin Spring Boot release, JDK, Maven Wrapper và plugin versions theo chính sách dự án. Các generated archives có thể chứa timestamp/metadata; `clean package` chưa đủ để tự suy ra checksum sẽ giống nhau qua mọi máy. Nếu cần reproducible build, cấu hình output timestamps và các toolchain/plugin có hỗ trợ, rồi kiểm chứng thực nghiệm.

## 16. Các lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra và sửa |
| --- | --- | --- |
| `java -jar ...war` báo `no main manifest attribute` | Chỉ có WAR thường từ `war:war`, chưa chạy Boot repackage | Xem manifest và plugin execution; chạy `mvn clean package` với Boot plugin |
| `java -jar ...war` báo thiếu `WarLauncher` | Archive thiếu loader classes hoặc manifest trỏ sai | `jar tf` tìm `...WarLauncher.class`; rebuild bằng Spring Boot Maven Plugin |
| WAR deploy Tomcat mà application không khởi động | Thiếu `SpringBootServletInitializer`, servlet API không tương thích, config hoặc bean lỗi | Xem logs Tomcat, extends initializer/`configure` và Jakarta compatibility |
| WAR chạy `java -jar` nhưng external Tomcat trả 404 | Context path khác, deploy thất bại hoặc servlet startup không đúng | Kiểm tra Tomcat logs/webapps tên WAR/context path, thử `/war-demo/hello` |
| Có hai bản Tomcat runtime xung đột | Embedded Tomcat nằm ở `WEB-INF/lib` | Khai báo trực tiếp `spring-boot-starter-tomcat` với `provided`, rebuild/inspect |
| `WEB-INF/lib-provided` trống hoặc thiếu Tomcat | Scope chưa đúng hoặc dependency bị exclude | `mvn dependency:tree` và `jar tf`; kiểm tra repackage logs |
| `WEB-INF/lib-provided` có Tomcat nhưng external deploy vẫn được | Đây là behavior đúng của executable WAR | External container không dùng lib-provided như WEB-INF/lib |
| `mvn spring-boot:repackage` không chạy được trên project sạch | Chưa có WAR/JAR đầu vào | Dùng lifecycle `mvn package`; goal repackage xử lý archive đã có |
| `mvn war:war` tạo WAR nhưng `java -jar` không chạy | Maven WAR Plugin không thêm launcher/manifest executable | Bật Spring Boot `repackage` hoặc deploy standard WAR vào external container |
| Cấu hình chỉ có BOM mà không tạo executable WAR | Import BOM không bind `repackage` | Khai báo Boot Maven Plugin version/execution hợp lệ |
| Tomcat 9 báo `javax/jakarta` class mismatch | Spring Boot 3.x dùng Jakarta Servlet, Tomcat 9 theo javax | Chọn servlet container Jakarta tương thích; không ép bằng đổi package thủ công |
| Application khởi động ngoài nhưng một số dependency lỗi | Xung đột classloader/container libraries hoặc provided scopes sai | Kiểm tra `WEB-INF/lib`, Tomcat logs, dependency graph và package/class names |
| JSP không render dù WAR build thành công | Thiếu JSP/JSTL deps, view resolver, JSP packaging | Rà soát cấu hình JSP, servlet container, Jakarta JSTL support |
| `maven-war-plugin` báo thiếu `web.xml` | Plugin/config không cho Servlet 3+ webapp không có descriptor | Dùng `failOnMissingWebXml=false` hoặc cấu hình đúng Servlet model |
| CI deploy nhầm `.war.original` | Script chọn file theo glob | Chọn main artifact/classifier rõ, kiểm tra manifest/WarLauncher trước upload |
| Local dùng port 8080 nhưng Tomcat ngoài có port/context khác | Hai runtime topology khác nhau | Đọc cấu hình Tomcat; URL ngoài thường có context path từ WAR |
| WAR qua `repackage` bị hỏng sau khi ZIP lại | Outer archive/nested JAR semantics không được giữ | Build lại bằng plugin chuẩn, không chỉnh ZIP thủ công |

### Quy trình chẩn đoán ngắn gọn

1. **Lấy lệnh và log thực:** đang chạy `java -jar` hay deploy vào Tomcat? Lỗi bắt đầu ở launcher hay trong Spring/Tomcat?
2. **Kiểm tra đúng file WAR:** full path, version, timestamp, checksum, classifier, `.original`.
3. **Xem effective POM:** `<packaging>war</packaging>`, WAR Plugin, Spring Boot Plugin và execution `repackage`.
4. **Xem dependency graph:** Tomcat có provided? Spring MVC/JSON libs có runtime scope phù hợp?
5. **Xem layout:** `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, Boot `WarLauncher`.
6. **Xem manifest:** `Main-Class` Boot loader và `Start-Class` application main đúng không?
7. **Chạy smoke test theo đích:** standalone `java -jar` **và/hoặc** external Tomcat deployment với đúng context path.
8. **Sửa source/POM và rebuild**, không tự vá WAR đã phát hành.

## 17. Tình huống luyện tập và đáp án

**Tình huống A.** POM chỉ có `<packaging>war</packaging>` và `maven-war-plugin`. Nhóm chạy `mvn clean package`, có WAR nhưng `java -jar` báo thiếu main manifest. Vì sao?

*Đáp án:* Maven WAR Plugin tạo **WAR deployable**, không tự tạo **executable Spring Boot WAR**. Cần Spring Boot Maven Plugin với goal `repackage` chạy trên WAR đã được tạo, hoặc deploy WAR truyền thống vào servlet container.

**Tình huống B.** Một WAR sau Boot `repackage` có `WEB-INF/lib-provided/tomcat-embed-core-...jar`. Có nên xóa nó khỏi WAR để deploy Tomcat ngoài?

*Đáp án:* Không cần. Spring Boot đặt provided dependencies ở thư mục riêng để WAR chạy standalone, trong khi external container dùng thư viện servlet/container của nó và không nạp `lib-provided` như `WEB-INF/lib`. Nếu mục tiêu là một WAR chạy được cả hai chế độ thì giữ nguyên output Boot plugin là cách đúng.

**Tình huống C.** Application có `main()`, POM là WAR, nhưng deploy lên external Tomcat thì không có Spring context. Cần xem gì?

*Đáp án:* Ngoài compatibility, phải bảo đảm application hỗ trợ đường **`SpringBootServletInitializer`** với `configure(SpringApplicationBuilder)`. Container ngoài không chạy `main()` qua `WarLauncher`.

**Tình huống D.** Chạy `java -jar war-demo-1.0.0.war` thì URL `/hello` hoạt động; copy cùng WAR vào Tomcat với tên `war-demo.war` thì `/hello` trả 404. Vì sao?

*Đáp án:* External Tomcat thường gán context path `/war-demo` theo tên WAR. Với cấu hình mặc định ví dụ, thử `/war-demo/hello` và xem deployment log. `server.port` của embedded mode không quyết định port của external Tomcat.

**Tình huống E.** Thêm dependency Tomcat với scope `compile`, WAR vẫn build thành công. Có thể coi như deploy outside không sao?

*Đáp án:* Không. Embedded servlet container libraries có thể bị đóng vào `WEB-INF/lib` và xung đột với Tomcat ngoài. Dùng `provided` theo Boot deployment guide rồi inspect output.

**Tình huống F.** POM dùng corporate parent, import `spring-boot-dependencies` BOM nhưng không có Boot plugin execution. WAR tạo thành công và được deploy ngoài, song không chạy `java -jar`. Phải làm gì?

*Đáp án:* Bổ sung Spring Boot Maven Plugin với version/execution `repackage`, bảo đảm nó chạy sau WAR packaging. BOM chỉ quản lý dependency versions, không tạo launcher/manifest.

**Tình huống G.** Có `war-demo-1.0.0.war` và `war-demo-1.0.0.war.original`; file nào nên deploy?

*Đáp án:* Với cấu hình mặc định bài này, `.war` là main artifact **sau repackage**, dùng được cho cả external container và standalone. `.war.original` là WAR gốc; có thể deploy theo servlet model nhưng không phải executable WAR. Chọn theo target đã kiểm tra, không theo glob không rõ mục đích.

**Tình huống H.** Test MockMvc pass, vậy WAR chắc chắn chạy được trên Tomcat 10.1?

*Đáp án:* Chưa. MockMvc kiểm tra application context/HTTP mapping ở test classpath; cần deployment smoke test thật với Tomcat ngoài và đúng Jakarta Servlet runtime. Manifest và `WEB-INF` cũng phải được kiểm tra.

**Tình huống I.** Có thể tạo executable WAR cho ứng dụng thuần WebFlux Netty rồi deploy y hệt lên servlet container không?

*Đáp án:* Không áp dụng trực tiếp công thức truyền thống như Spring MVC. Spring Boot 3.3 documentation nêu WAR deployment không hỗ trợ cho WebFlux ứng dụng theo mô hình Netty mặc định; cần chọn kiến trúc servlet/web phù hợp nếu bắt buộc WAR.

**Tình huống J.** Bạn chạy `mvn clean package spring-boot:repackage` trên project đã kế thừa starter parent, cũng có Boot plugin. Điều nào cần lưu ý?

*Đáp án:* Parent thường đã bind `repackage` vào `package`. Gọi goal thêm có thể lặp công việc không cần thiết; dùng `mvn clean package` hoặc `verify` và kiểm tra effective POM/executions.

## 18. Checklist trước khi hoàn thành WAR packaging

- **Mục tiêu triển khai:** application là servlet web app, cần external container hay chỉ muốn chạy standalone?
- **Tương thích runtime:** Java 17 target, Spring Boot 3.3/Jakarta API, Tomcat ngoài tương thích và còn hỗ trợ.
- **POM:** có `<packaging>war</packaging>` và `maven-war-plugin` phù hợp.
- **Bootstrap:** có `SpringBootServletInitializer`/`configure` cho external container; `main()` cho executable mode.
- **Dependencies:** `spring-boot-starter-web`, `spring-boot-starter-tomcat` `provided`, test dependencies `test`.
- **Plugin:** `spring-boot-maven-plugin` có goal `repackage` và đúng application main class, không chỉ import BOM.
- **Build:** `mvn clean verify` chạy success, log có Maven WAR Plugin và Boot `repackage` đúng thứ tự.
- **Archive:** `WEB-INF/classes` có class/resources, `WEB-INF/lib` có runtime dependencies, `WEB-INF/lib-provided` có embedded container.
- **Manifest:** `Main-Class` trỏ `WarLauncher`, `Start-Class` trỏ application main class.
- **Standalone smoke test:** `java -jar target/...war` và kiểm tra HTTP response, không chỉ dựa vào Unit Test.
- **External smoke test:** WAR deploy lên servlet container tương thích, đúng context path/port, không báo xung đột servlet classes.
- **Phát hành:** lưu artifact identity/checksum, publish đúng WAR sau QA; không nhầm `.war.original` hoặc classifier khác.
- **Không sửa WAR tay:** nếu sai, sửa POM/source, build lại và kiểm tra mọi bước; tránh ZIP repack gây hỏng nested layout.

**Kết luận:** `maven-war-plugin` tạo **WAR đúng chuẩn web application**, còn `spring-boot-maven-plugin:repackage` bổ sung **Spring Boot Loader và executable manifest** để một WAR có thể chạy bằng `java -jar`. `spring-boot-starter-tomcat` ở scope **provided** giúp dùng container ngoài mà tránh xung đột, đồng thời `WEB-INF/lib-provided` cho phép Boot `WarLauncher` nạp embedded server khi chạy độc lập. Muốn triển khai external servlet container, ứng dụng cần đường khởi tạo `SpringBootServletInitializer`; đây là cơ chế khác với `main()` của executable mode.

### Tài liệu chính thức

- Spring Boot 3.3.13 — Traditional Deployment / Create a Deployable War File: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Spring Boot 3.3.13 — Maven Plugin / Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot — Executable Archive Layout / Nested JARs: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot — Launching Executable Archives / WarLauncher: https://docs.spring.io/spring-boot/specification/executable-jar/launching.html
- Apache Maven WAR Plugin — Overview and Goals: https://maven.apache.org/plugins/maven-war-plugin/
- Apache Maven WAR Plugin — `war:war` Goal Reference: https://maven.apache.org/plugins/maven-war-plugin/war-mojo.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html