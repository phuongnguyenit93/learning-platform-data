# Phân biệt WAR triển khai truyền thống với WAR có thể chạy bằng java -jar trong Spring Boot

## 1. Bài toán: cùng đuôi .war nhưng có hai cách khởi chạy

Trong hệ sinh thái Java, **WAR (Web Application Archive)** là định dạng đóng gói ứng dụng web để triển khai vào một **servlet container/application server**. Một file `.war` theo cách truyền thống được **container bên ngoài** (ví dụ Apache Tomcat) triển khai, nạp servlet, quản lý cổng HTTP và vòng đời ứng dụng. Nhưng Spring Boot còn có **executable WAR**: vẫn là WAR có thể triển khai theo kiểu truyền thống, đồng thời được đóng gói thêm **Spring Boot Loader** và những dependency thích hợp để có thể chạy trực tiếp:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war
```

Vì vậy câu hỏi không phải “WAR có luôn chạy được bằng `java -jar` không?”, mà là **WAR nào được build, bằng plugin nào, có launcher và dependency chạy độc lập hay chưa?**

| Tiêu chí | WAR triển khai truyền thống | Spring Boot executable WAR |
|---|---|---|
| Cách khởi chạy chính | Copy/deploy lên servlet container | `java -jar app.war`; cũng có thể deploy lên container tương thích |
| Ai mở HTTP port? | Container ngoài | Embedded servlet container khi chạy `java -jar` |
| Ai tạo Spring application context? | Servlet initialization path (`SpringBootServletInitializer` hoặc cơ chế tương đương) | `main` được Boot Launcher gọi, rồi `SpringApplication.run` |
| Java launcher có thể chạy trực tiếp chỉ vì đuôi `.war`? | Không | Có, khi được repackage đúng |
| `META-INF/MANIFEST.MF` | Có thể không có `Main-Class` thích hợp để Java launcher chạy | `Main-Class` thường là `org.springframework.boot.loader.launch.WarLauncher`; `Start-Class` là ứng dụng |
| Thư viện servlet container | Container bên ngoài cung cấp | `WEB-INF/lib-provided` được Boot Loader dùng khi chạy độc lập |
| Class và runtime libraries | `WEB-INF/classes` và `WEB-INF/lib` | Cũng có `WEB-INF/classes`, `WEB-INF/lib`; thường thêm `WEB-INF/lib-provided` và loader |
| Cấu hình cổng và context path | Container quyết định theo cấu hình triển khai | Embedded server nhận cấu hình Spring Boot |
| Mục đích thường gặp | Hạ tầng tổ chức yêu cầu WAR trên Tomcat/WebLogic/... | Muốn **một artifact** vừa có thể deploy truyền thống vừa tự chạy |

**Điểm dễ nhầm:** executable WAR **không phải** “WAR khác chuẩn”, cũng không phải định dạng dành riêng cho Docker. Nó là WAR tương thích với cơ chế deploy thông thường và được mở rộng hợp lệ để chứa khả năng bootstrap của Spring Boot. Tuy nhiên tương thích thực tế còn phụ thuộc **container, Servlet/Jakarta API, classloader, cấu hình ứng dụng và phiên bản Java**.

## 2. Cấu trúc archive và trách nhiệm của từng bên

### 2.1. WAR truyền thống

Một WAR Java web điển hình:

```text
traditional.war
├── META-INF/
│   └── MANIFEST.MF
├── index.html                        (tùy ứng dụng)
└── WEB-INF/
    ├── classes/
    │   └── com/example/war/...
    ├── lib/
    │   ├── spring-webmvc-....jar
    │   └── các dependency ứng dụng khác
    └── web.xml                       (nếu dùng descriptor)
```

Khi deploy vào Tomcat tương thích, **Tomcat** xác định context path, quản lý connector/threads/cổng, sử dụng Servlet container API của nó và dựng classloader cho ứng dụng. `web.xml` **không bắt buộc** nếu ứng dụng dùng cơ chế Servlet annotation/initialization phù hợp; Spring Boot thường dùng `SpringBootServletInitializer` thay vì bắt bạn viết `web.xml` cho một ứng dụng mới.

`java -jar traditional.war` **không tự biến WAR thành web server**. Nếu manifest không có `Main-Class`, Java launcher có thể báo:

```text
no main manifest attribute, in traditional.war
```

Đây là **một dạng lỗi có thể gặp** (không bảo đảm là nguyên văn trên mọi JDK/archive). Thêm một `main` vào mã nguồn **chưa đủ**: phải có cấu trúc đóng gói, manifest và runtime container phù hợp để Java launcher chạy.

### 2.2. Executable WAR Spring Boot

Spring Boot Loader-compatible WAR thường có bố trí:

```text
war-lab-0.0.1-SNAPSHOT.war
├── META-INF/
│   └── MANIFEST.MF
├── org/
│   └── springframework/boot/loader/...
└── WEB-INF/
    ├── classes/
    │   ├── com/example/war/WarLabApplication.class
    │   └── com/example/war/HelloController.class
    ├── lib/
    │   └── các thư viện runtime của ứng dụng
    ├── lib-provided/
    │   └── các dependency cần khi chạy embedded
    └── ... (tùy cấu hình)
```

Hai thư mục thư viện quan trọng:

- **`WEB-INF/lib/`**: dependency runtime của ứng dụng được đặt ở vị trí container bên ngoài cũng có thể nạp khi deploy.
- **`WEB-INF/lib-provided/`**: nơi Spring Boot plugin đóng các dependency đã được đánh dấu `provided`/`providedRuntime` trong executable WAR. **WarLauncher dùng chúng khi `java -jar`**, nhưng container ngoài không coi đây là vị trí `WEB-INF/lib` tiêu chuẩn để nạp chúng như ứng dụng tự mang vào.

Ví dụ, Tomcat nhúng đi kèm `spring-boot-starter-web` có thể được đánh dấu **provided**: khi deploy tới Tomcat ngoài, container đã có servlet engine; khi chạy `java -jar`, Boot Launcher vẫn cần Tomcat nhúng để tự mở HTTP server. Cách chia `lib`/`lib-provided` tránh để ứng dụng đóng kèm bản Tomcat trùng với server bên ngoài.

**Không phải mọi WAR đều có `lib-provided` hoặc Boot Loader.** Nếu không có dependency provided hoặc không được repackage, các mục tương ứng có thể không xuất hiện. Luôn kiểm tra archive thật.

### 2.3. Manifest của executable WAR

Ở Spring Boot 3.x, manifest thường tương tự:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarLabApplication
```

`Main-Class` chỉ **bootstrap loader**, không phải lớp controller hay servlet. `Start-Class` chỉ lớp có entrypoint `main`. Khi chạy `java -jar`:

```text
java -jar app.war
      |
      v
Spring Boot WarLauncher
      |
      +-- WEB-INF/classes/
      +-- WEB-INF/lib/*.jar
      +-- WEB-INF/lib-provided/*.jar
      |
      v
Start-Class: WarLabApplication.main(...)
      |
      v
SpringApplication.run(...)
      |
      v
Embedded Tomcat lắng nghe HTTP
```

Khi **deploy tới container ngoài**, server không dùng `WarLauncher` như lối đi khởi động chính. Nó sử dụng **servlet initialization** của mình, và Spring Boot cung cấp `SpringBootServletInitializer` làm cầu nối.

## 3. Hai đường khởi tạo ứng dụng là khác nhau

### 3.1. WAR deploy lên container bên ngoài

```text
Tomcat ngoài khởi động
       |
       v
Quét/triển khai WAR (ví dụ webapps/war-lab.war)
       |
       v
ServletContainerInitializer / Spring WebApplicationInitializer
       |
       v
SpringBootServletInitializer.configure(...)
       |
       v
Spring ApplicationContext + DispatcherServlet
       |
       v
HTTP endpoint chạy dưới context path được container gán
```

Cách chạy này **không bắt đầu bằng `public static void main`** của ứng dụng. Cần cấu hình servlet initialization phù hợp; với Spring Boot ứng dụng servlet thông thường, kế thừa `SpringBootServletInitializer` và override `configure` là cách được tài liệu hướng dẫn.

### 3.2. WAR chạy trực tiếp bằng java -jar

```text
java -jar app.war
      |
      v
META-INF/MANIFEST.MF -> WarLauncher
      |
      v
ClassLoader với WEB-INF/classes + lib + lib-provided
      |
      v
WarLabApplication.main(...)
      |
      v
SpringApplication.run(...)
      |
      v
Embedded Tomcat và HTTP endpoint
```

**Hai cơ chế có thể sống trong cùng một lớp Java.** Chúng giải thích vì sao một executable WAR có thể chạy theo cả hai cách, nhưng cũng vì sao chỉ viết `main` hoặc chỉ viết `configure` là chưa đủ để có dual-mode WAR hoàn chỉnh.

### 3.3. SpringBootServletInitializer khác Servlet container

`SpringBootServletInitializer` là lớp Spring Boot giúp **khởi tạo ứng dụng khi servlet container bên ngoài triển khai WAR**. Nó không phải bản thân Tomcat, không phải `WarLauncher`, cũng không phải lớp bắt buộc cho ứng dụng chỉ chạy executable JAR.

Đoạn Java đầy đủ ở mục sau cho thấy cả `configure` và `main`. Nếu ứng dụng chỉ dùng embedded server kiểu `java -jar app.jar`, lớp chính không cần extends `SpringBootServletInitializer`. Nếu ứng dụng cần chạy WAR trên Tomcat ngoài, phải cung cấp đường bootstrap servlet phù hợp.

Đối với một số container đặc biệt như WebLogic, tài liệu Spring Boot còn có yêu cầu bổ sung về việc implements `WebApplicationInitializer` trực tiếp; **không coi ví dụ Tomcat bên dưới là cấu hình duy nhất áp dụng cho mọi application server**.

## 4. Ví dụ thực hành Java 17: một WAR chạy theo hai cách

Bài thực hành dưới đây dùng **Spring Boot 3.5.16** (phiên bản được pin trong ví dụ, không phải khẳng định mới nhất), **Java 17+**, Maven hỗ trợ phiên bản này hoặc Maven Wrapper đã cấu hình, và một Tomcat 10.1 tương thích để thử external deployment.

Mục tiêu:

1. Build `.war` có Boot Loader.
2. Chạy `java -jar ...war` và gọi endpoint `/hello`.
3. Dừng bản embedded, deploy **cùng WAR** lên Tomcat ngoài.
4. Gọi `/war-lab/hello` (theo tên context được giả định) và nhận body tương đương.

### 4.1. Cấu trúc thư mục

```text
war-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/war/
        │   ├── WarLabApplication.java
        │   └── HelloController.java
        └── resources/
            └── application.properties
```

Nếu dự án có Maven Wrapper thì root còn có `mvnw`, `mvnw.cmd` và `.mvn/wrapper/...`. Các file Wrapper **không tự xuất hiện** khi viết `pom.xml`; nếu không có, dùng `mvn` đã cài.

### 4.2. pom.xml hoàn chỉnh

```xml
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
    <artifactId>war-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <!-- WAR thay vì JAR; Maven WAR plugin sẽ đóng gói WEB-INF -->
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Spring MVC, DispatcherServlet và auto-configuration -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Tomcat được container ngoài cung cấp khi deploy WAR -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- spring-boot-starter-parent cấu hình repackage tại package -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Cơ chế:

- `<packaging>war</packaging>` yêu cầu Maven tạo WAR.
- `spring-boot-starter-web` cung cấp Spring MVC cùng dependency cần thiết.
- Khai báo `spring-boot-starter-tomcat` với `<scope>provided</scope>` đảm bảo bộ servlet engine không được đưa vào thư mục runtime thông thường của WAR khi deploy.
- Spring Boot Maven Plugin `repackage` biến archive do Maven WAR plugin tạo thành **executable WAR**, gồm loader và manifest. Vì ví dụ dùng `spring-boot-starter-parent`, goal `repackage` đã được gắn vào lifecycle theo cấu hình parent khi khai báo plugin.
- Trong executable WAR, các dependency provided phù hợp được đặt ở `WEB-INF/lib-provided` để WarLauncher có thể dùng khi `java -jar`.

**Không thay `provided` bằng `test`**: test scope không bảo đảm dependency có mặt khi chạy embedded WAR. Cũng không loại hẳn Tomcat khỏi dependency graph nếu vẫn muốn hỗ trợ `java -jar` và không có embedded server khác.

### 4.3. Lớp ứng dụng có cả configure và main

`src/main/java/com/example/war/WarLabApplication.java`:

```java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarLabApplication extends SpringBootServletInitializer {

    // Được dùng khi WAR được triển khai bởi servlet container bên ngoài.
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarLabApplication.class);
    }

    // Được dùng khi Spring Boot Loader chạy WAR bằng java -jar.
    public static void main(String[] args) {
        SpringApplication.run(WarLabApplication.class, args);
    }
}
```

Đây là **class Java 17+ hợp lệ** khi compile với dependencies trong POM. Nằm ở package `com.example.war` và annotation `@SpringBootApplication` nên component scan mặc định tìm thấy controller cùng package.

Tại sao cần cả hai method?

- Khi chạy từ **Tomcat ngoài**, Spring Servlet initialization gọi đường `configure`; container bên ngoài quản lý servlet lifecycle.
- Khi chạy **`java -jar`**, WarLauncher gọi `main`, rồi Spring Boot khởi tạo embedded web server.
- Tham số config/profiles có thể khác nhau giữa hai cách khởi chạy; nếu cần cấu hình `SpringApplicationBuilder` tùy chỉnh thống nhất, hãy dùng **cùng một hàm cấu hình** được gọi từ cả `configure` và `main`, thay vì tùy biến chỉ một đường.

### 4.4. REST controller với kết quả xác định

`src/main/java/com/example/war/HelloController.java`:

```java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "WAR OK\n";
    }
}
```

Body HTTP thành công chứa chính xác **`WAR OK` rồi ký tự xuống dòng**. Khi dùng `curl`, console hiển thị:

```text
WAR OK
```

Controller này chỉ phụ thuộc Spring Web, không phụ thuộc vào cách khởi chạy. Do đó cùng logic có thể phục vụ HTTP dưới embedded Tomcat hoặc external Tomcat khi các cấu hình tương ứng hợp lệ.

`src/main/resources/application.properties`:

```properties
spring.application.name=war-lab
spring.main.banner-mode=off
```

Không cấu hình `server.servlet.context-path` trong ví dụ, để dễ quan sát khác biệt giữa context của embedded server và context gán bởi container ngoài.

## 5. Build Maven và chạy executable WAR

Từ thư mục `war-lab`:

```bash
# Nếu dự án có Maven Wrapper:
./mvnw clean package

# Hoặc Maven đã cài sẵn, khi dự án không có Wrapper:
mvn clean package
```

Chọn **một** trong hai lệnh; cần kết nối repository khi dependency/plugin chưa có trong cache. Với Windows PowerShell có Wrapper, dùng `.\mvnw.cmd clean package`.

Khi build thành công, ví dụ tạo:

```text
target/war-lab-0.0.1-SNAPSHOT.war
```

Chạy trực tiếp:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war
```

Ở terminal khác, sau khi ứng dụng hoàn tất startup, gọi:

```bash
curl -fsS http://localhost:8080/hello
```

HTTP body dự kiến:

```text
WAR OK
```

Đây là **đầu ra của endpoint do controller cung cấp** trong điều kiện ứng dụng và port hoạt động bình thường, không phải toàn bộ log của lệnh `java -jar`. Nếu port 8080 đang bị tiến trình khác sử dụng, có thể đổi port riêng cho bản executable:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war --server.port=8081
curl -fsS http://localhost:8081/hello
```

**`--server.port`** điều khiển embedded Tomcat trong nhánh `java -jar`. Nó **không** thay connector port của một Tomcat ngoài đang chạy sẵn, vì cổng của server đó được cấu hình ở chính Tomcat.

### 5.1. Kiểm tra WAR thực tế chứ không chỉ nhìn đuôi file

Dùng `jar` của JDK:

```bash
jar tf target/war-lab-0.0.1-SNAPSHOT.war

# Chỉ xem các thư mục và Boot loader (Unix shell có grep):
jar tf target/war-lab-0.0.1-SNAPSHOT.war | grep -E '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/|org/springframework/boot/loader/)'
```

Windows PowerShell:

```powershell
jar tf target/war-lab-0.0.1-SNAPSHOT.war |
    Select-String '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/|org/springframework/boot/loader/)'
```

Kiểm tra manifest bằng cách trích vào thư mục kiểm tra riêng:

```bash
mkdir -p inspect-war
cd inspect-war
jar xf ../target/war-lab-0.0.1-SNAPSHOT.war META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
```

Với Windows PowerShell, dùng `New-Item -ItemType Directory -Force inspect-war`, `Push-Location inspect-war`, `jar xf ../target/...war META-INF/MANIFEST.MF`, `Get-Content META-INF/MANIFEST.MF`, `Pop-Location`. Việc **trích** không sửa archive gốc.

Trong ví dụ, hãy tìm:

- `WEB-INF/classes/com/example/war/WarLabApplication.class`.
- `WEB-INF/classes/com/example/war/HelloController.class`.
- Các dependency Spring MVC trong `WEB-INF/lib/`.
- Các JAR liên quan embedded Tomcat trong `WEB-INF/lib-provided/`.
- `Main-Class: org.springframework.boot.loader.launch.WarLauncher`.
- `Start-Class: com.example.war.WarLabApplication`.

**Không khẳng định phiên bản/tên từng JAR chính xác** trước khi xem resolved graph và archive. `jar tf` cũng không bảo đảm thứ tự classpath là thứ tự entry ZIP.

## 6. Deploy chính executable WAR lên external Tomcat

Ví dụ giả định **Tomcat 10.1** được cài đặt, chạy bằng **Java 17+**, và tương thích với Spring Boot 3.5/Jakarta Servlet API của ứng dụng. Tomcat 9 dùng namespace `javax.servlet` cũ, **không phù hợp để triển khai trực tiếp ứng dụng Spring Boot 3.x dựa trên `jakarta.servlet`**.

### 6.1. Chép và đặt context path

Dừng phiên bản WAR đang chạy `java -jar` nếu nó đang chiếm **port 8080**, rồi chép artifact đã build sang thư mục `webapps` của Tomcat:

```bash
# Linux/macOS: CATALINA_HOME trỏ đúng thư mục Tomcat đã cài.
cp target/war-lab-0.0.1-SNAPSHOT.war "$CATALINA_HOME/webapps/war-lab.war"
```

Windows PowerShell với biến môi trường `CATALINA_HOME` đã đặt:

```powershell
Copy-Item target/war-lab-0.0.1-SNAPSHOT.war "$env:CATALINA_HOME/webapps/war-lab.war"
```

Tomcat cần thực sự tồn tại và được cấu hình để deploy WAR từ thư mục đó; đây **không** phải lệnh cài Tomcat. Khi Tomcat có auto-deploy phù hợp, nó triển khai `war-lab.war` dưới context path **`/war-lab`** theo quy ước tên WAR. Nếu container dùng cấu hình Context khác hoặc deploy qua giao diện quản trị, context path có thể khác.

Sau khi Tomcat startup và WAR deploy thành công:

```bash
curl -fsS http://localhost:8080/war-lab/hello
```

HTTP body dự kiến cũng là:

```text
WAR OK
```

**Khác biệt quan sát được:** cùng một class `HelloController` và cùng artifact WAR, nhưng khi chạy trực tiếp endpoint là `/hello`, còn khi deploy dưới context tên `war-lab` là `/war-lab/hello`. Sự khác biệt này đến từ **context path**, không phải ứng dụng mất controller.

Nếu server ngoài không chạy port 8080, dùng đúng host/port của cấu hình container. Đừng suy từ `application.properties` của WAR rằng external Tomcat phải lắng nghe theo `server.port` trong đó.

### 6.2. Vì sao không có xung đột Tomcat nhúng?

Trong mode **external deployment**:

- Tomcat bên ngoài cung cấp Servlet/Jakarta API và các thành phần engine mà container quản lý.
- Thư viện ứng dụng trong `WEB-INF/lib` được nạp theo cấu hình webapp.
- Các dependency embedded container thuộc `WEB-INF/lib-provided` **không được coi là thư viện webapp thông thường** của container bên ngoài.
- Spring khởi tạo ứng dụng bằng `SpringBootServletInitializer` theo Servlet startup lifecycle.

Trong mode **`java -jar`**:

- Spring Boot `WarLauncher` có thể truy cập cả `WEB-INF/lib` và `WEB-INF/lib-provided`.
- Embedded Tomcat được lấy từ những dependency provided đã đóng gói.
- Spring Boot chạy `main`, embedded server mở port và phục vụ request.

Đó là lý do **provided trong executable WAR không đồng nghĩa “không tồn tại ở runtime khi java -jar”**. Maven `provided` thông thường không nằm trên runtime classpath do Maven trực tiếp giải quyết, nhưng Spring Boot Maven Plugin có **quy tắc đóng gói executable WAR riêng**. Phải kiểm tra chính artifact cuối, không chỉ đọc scope.

## 7. Phân biệt WAR thường và executable WAR được build bằng plugin nào

### 7.1. Maven WAR plugin và Spring Boot Maven Plugin làm hai việc khác nhau

Maven `maven-war-plugin` đóng gói một ứng dụng web theo cấu trúc WAR. `spring-boot-maven-plugin:repackage` **thêm cấu trúc executable**, loader và cập nhật manifest cho output được thiết kế chạy độc lập.

```text
Maven compile/resources
        |
        v
maven-war-plugin -> WAR webapp chuẩn
        |
        v
spring-boot-maven-plugin:repackage
        |
        v
Executable WAR có WarLauncher + provided deps phù hợp
```

Một WAR không qua `repackage` vẫn có thể triển khai bình thường lên Tomcat nếu webapp được cấu hình đúng, nhưng lệnh `java -jar` không mặc định hoạt động.

Nếu chỉ có:

```xml
<packaging>war</packaging>
```

thì **chưa đủ** để khẳng định WAR executable. Cần xem effective POM và cách `spring-boot-maven-plugin` được gắn với lifecycle. Với `spring-boot-starter-parent`, việc khai báo plugin như ở mục 4 đáp ứng luồng repackage thông thường. Với parent/BOM khác, có thể phải khai báo execution `repackage` tường minh.

Ví dụ đoạn plugin cho dự án **không kế thừa Spring Boot parent** đã được cấu hình Java/plugin versions riêng:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.16</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn chèn trong `<build><plugins>`**, không phải POM độc lập; còn cần quản lý compiler, dependency versions, WAR plugin và Java version theo project. Tránh khai báo trùng `repackage` execution khi parent đã làm sẵn.

### 7.2. Nếu chỉ cần WAR truyền thống

Không cần hoặc không muốn hỗ trợ `java -jar`? Có thể dùng WAR đóng gói theo tiêu chuẩn servlet container và **không repackage bằng Spring Boot Loader**. Ứng dụng Spring Boot dạng Servlet vẫn nên có `SpringBootServletInitializer` (hoặc bootstrap servlet phù hợp) và đánh dấu container dependency đúng scope.

Tuy nhiên, **đừng loại hẳn Spring Boot plugin mà chưa kiểm tra build**: trong dự án hiện có, plugin còn quản lý goal hoặc cấu hình khác. Phải xác định tool, parent và các task khác trước khi thay đổi, rồi kiểm tra lại archive. WAR truyền thống chỉ cần deploy vào container tương thích; không lấy việc `java -jar` thất bại làm dấu hiệu WAR đó “không hợp lệ”.

## 8. Gradle: war, bootWar và providedRuntime

Với Gradle, áp dụng `war` plugin để có packaging WAR. Khi `org.springframework.boot` được áp dụng cùng plugin `war`, Spring Boot tạo task `bootWar` để đóng **executable WAR**; còn task `war` tạo WAR theo cơ chế Gradle thông thường.

### 8.1. Ví dụ Groovy DSL đầy đủ

Giữ nguyên hai Java class `WarLabApplication` và `HelloController` ở mục 4. Tạo file `settings.gradle`:

```groovy
rootProject.name = 'war-lab'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'war'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Servlet engine dùng khi chạy embedded, không nằm ở WEB-INF/lib
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Đây là cấu hình Gradle **Groovy DSL**; không trộn trực tiếp với syntax Kotlin DSL của `build.gradle.kts`. Spring Boot plugin riêng nó không tự thêm starter và không tự quản lý mọi dependency version khi không có dependency management; `platform(...)` ở đây nhập constraints từ Spring Boot BOM cho cấu hình implementation.

`providedRuntime` là configuration của Gradle WAR plugin và là cách Spring Boot hướng dẫn khi deploy lên servlet container. Nó thích hợp hơn `compileOnly` cho embedded servlet container vì `compileOnly` **không nằm trên test runtime classpath**; điều đó có thể khiến web integration tests thiếu runtime container.

### 8.2. Chạy các task và kiểm tra file

Nếu dự án đã có Gradle Wrapper và dùng bản Gradle tương thích Spring Boot 3.5:

```bash
./gradlew tasks --all

# Tạo WAR bình thường và Boot executable WAR:
./gradlew clean war bootWar

# Kiểm tra output thực tế:
jar tf build/libs/war-lab-0.0.1-SNAPSHOT.war

# Chạy executable WAR:
java -jar build/libs/war-lab-0.0.1-SNAPSHOT.war
```

Trên Windows PowerShell dùng `.\gradlew.bat`. Nếu thiếu Gradle Wrapper, cần tạo wrapper bằng một bản Gradle đã cài hợp lệ; các file `gradlew` và `gradlew.bat` không tự xuất hiện khi viết build script.

Với quy ước mặc định khi dùng Boot plugin, đầu ra thường gồm:

```text
build/libs/war-lab-0.0.1-SNAPSHOT.war         # bootWar
build/libs/war-lab-0.0.1-SNAPSHOT-plain.war   # war
```

Tên này là **quy ước**, không phải cam kết nếu project đổi `archiveClassifier`, `archiveBaseName` hoặc version. Nếu task `war` đã được cấu hình classifier theo cách khác, hãy xem file thực dưới `build/libs`. **Đừng chạy `java -jar` với `*-plain.war` rồi quy kết mọi WAR không executable**.

### 8.3. WAR được publish không nhất thiết là đúng WAR muốn deploy

Gradle `maven-publish` hay các cơ chế publication khác **không tự bảo đảm** rằng file được xuất bản là `bootWar` thay vì `war`. Nếu pipeline cần **executable WAR**, hãy chọn đúng artifact/task hoặc file `.war` trong thư mục build. Nếu chỉ cần deploy trên external Tomcat, WAR thường hoặc executable WAR deployable (khi dependency đã được phân tầng đúng) đều có thể phù hợp.

Trước khi đẩy artifact lên repository/registry:

1. Kiểm tra file output của task `war` và `bootWar`.
2. Kiểm tra `META-INF/MANIFEST.MF` và `WEB-INF/lib-provided`.
3. Thử `java -jar` nếu artifact quảng bá khả năng executable.
4. Thử deploy vào phiên bản Tomcat đích nếu artifact quảng bá khả năng traditional deployment.

Một suffix `.war` hoặc một build task thành công **không thay thế** kiểm thử hai đường chạy.

## 9. Context path, cổng và vòng đời triển khai

Hai chế độ có cách phân quyền cấu hình khác nhau.

| Câu hỏi | WAR deploy lên external Tomcat | `java -jar` executable WAR |
|---|---|---|
| HTTP port ở đâu? | Connector của Tomcat (`server.xml` hoặc hệ thống vận hành) | Embedded server, có thể cấu hình `--server.port=8081` |
| Context path mặc định? | Theo tên WAR hoặc cấu hình Context của container (ví dụ `/war-lab`) | Thường là `/` trừ khi Spring cấu hình context path |
| Ai khởi động server? | Tomcat process/manager | Ứng dụng Boot trong Java process |
| Ai restart ứng dụng? | Servlet container/deploy manager | Process manager, service, container runtime của app |
| Server/container có thể chạy nhiều webapp? | Một Tomcat có thể deploy nhiều WAR | Mỗi executable WAR thường là process riêng với embedded server |
| Servlet API và embedded engine lấy từ đâu? | Container bên ngoài | `WEB-INF/lib-provided` trong executable WAR |
| `SpringBootServletInitializer` cần? | Đúng với Spring Boot servlet WAR truyền thống | `main` là đường chạy executable; initializer vẫn giúp dual-mode |

Ví dụ, khi external Tomcat đang nghe port 8080 và deploy `war-lab.war`, đường dẫn kiểm tra là `http://localhost:8080/war-lab/hello`. Nếu cùng executable WAR chạy ở port 8081 theo lệnh:

```bash
java -jar target/war-lab-0.0.1-SNAPSHOT.war --server.port=8081
```

thì request phù hợp là `http://localhost:8081/hello`. Trường hợp khác context path do bạn cấu hình phải kiểm tra theo thực tế.

**Không chạy hai server trùng port 8080 cùng lúc** trừ khi mỗi server bị giới hạn vào interface riêng hoặc có cấu hình rõ ràng. Lỗi “Port 8080 was already in use” là lỗi bind socket, không nói lên artifact có executable hay không.

### Tính chất của Servlet web application

Mẫu này áp dụng **Spring MVC/Servlet stack**. Spring Boot tài liệu nêu **WAR deployment không hỗ trợ ứng dụng Spring WebFlux dùng reactive server mặc định**, vì WebFlux không phụ thuộc trực tiếp Servlet API và được triển khai mặc định trên Reactor Netty. Không chuyển một dự án WebFlux `spring-boot-starter-webflux` thành traditional WAR chỉ bằng cách đổi `<packaging>` hay bật Gradle `war`.

## 10. Phiên bản Java, Servlet/Jakarta API và tính tương thích

Spring Boot 3.x dùng **Jakarta EE namespace** `jakarta.servlet.*` thay vì `javax.servlet.*` của thế hệ cũ. Tomcat 10.1 (với Servlet 6.0) là ví dụ container tương thích thường dùng cho Spring Boot 3.5; Tomcat 9 gắn với `javax.servlet` cũ không phải đích tương thích cho ứng dụng này.

Những điểm phải xác minh khi deploy:

- **JDK của server ngoài** đáp ứng yêu cầu Spring Boot và cả servlet container.
- **Servlet API version/namespace** tương thích với Spring Framework/Boot đang dùng.
- **Container vendor/version** được ứng dụng và hạ tầng chấp nhận; đừng suy “có Tomcat” là đủ.
- Những dependency container-managed (Servlet/JSP/WebSocket API, engine) không bị đóng trùng sai vị trí trong `WEB-INF/lib`.
- Chính sách classloader của container có thể khác Boot Launcher, ảnh hưởng resource, logging provider và thư viện cài sẵn.
- Cấu hình datasource/JNDI, SSL, session, security, logging và context path có thể khác giữa embedded và external container.

Lỗi `NoClassDefFoundError: javax/servlet/...` hoặc `jakarta/servlet/...` thường là tín hiệu kiểm tra **namespace/Servlet API và classpath**, không chỉ sửa tên package một cách cơ học. Nếu migration từ Java EE cũ, cần kiểm tra tất cả thư viện và mã nguồn đã tương thích Jakarta hay chưa.

**WAR executable không đồng nghĩa container agnostic tuyệt đối.** Ứng dụng có thể chạy embedded nhưng không deploy được lên một external container quá cũ, hoặc container có policy/classloader đặc thù.

## 11. Chứng minh bằng kiểm thử: hai mode, một artifact

Một chiến lược test đáng tin cậy là kiểm tra **đúng file WAR sau build** trong cả hai môi trường mục tiêu.

### Test nhánh executable

1. `mvn clean package` hoặc `./gradlew clean bootWar`.
2. `jar tf ...war` để chắc có loader, manifest, `WEB-INF/lib-provided` khi dùng provided Tomcat.
3. `java -jar ...war --server.port=8081`.
4. Gọi `curl -fsS http://localhost:8081/hello`.
5. Xác nhận HTTP 200 và body `WAR OK` cùng newline; dừng process.
6. Xem log startup/exception; bảo đảm không có lỗi nạp class hoặc binding.

### Test nhánh external container

1. Lấy **cùng file WAR** đã kiểm tra (không tự rebuild bằng cấu hình khác).
2. Deploy lên Tomcat 10.1/JDK tương thích; đặt file `war-lab.war`.
3. Đợi server hoàn tất deployment; xem log Tomcat.
4. Gọi `curl -fsS http://localhost:8080/war-lab/hello` (hoặc context/port thực).
5. Xác nhận HTTP 200, body `WAR OK` cùng newline.
6. Undeploy WAR, xem server giải phóng resources/threads theo vòng đời container.

**So sánh hợp lý:** HTTP response nghiệp vụ giống nhau; đường dẫn/cổng/log classloader có thể khác. Nếu chỉ `mvn test` xanh, chưa khẳng định WAR deploy được trên Tomcat thật. Nếu chỉ `java -jar` xanh, chưa chứng minh servlet initializer và container compatibility.

### Quan sát archive bằng Java 17 thuần (tùy chọn)

Nếu không muốn phụ thuộc `grep` hoặc `Select-String`, có thể viết một Java CLI để kiểm tra một số entry trong archive. File `WarEntries.java` ở root:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.zip.ZipFile;

public class WarEntries {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java WarEntries <path-to-war>");
            return;
        }
        try (ZipFile war = new ZipFile(Path.of(args[0]).toFile())) {
            System.out.println("Has manifest: "
                    + (war.getEntry("META-INF/MANIFEST.MF") != null));
            System.out.println("Has app class: "
                    + (war.getEntry(
                      "WEB-INF/classes/com/example/war/WarLabApplication.class")
                        != null));
            System.out.println("Has Boot launcher: "
                    + (war.getEntry(
                      "org/springframework/boot/loader/launch/WarLauncher.class")
                        != null));
        }
    }
}
```

Dùng Java 17+ ở root có `WarEntries.java`:

```bash
javac WarEntries.java
java WarEntries target/war-lab-0.0.1-SNAPSHOT.war
```

Với **executable WAR được tạo đúng theo ví dụ** và Spring Boot 3.5 có `WarLauncher` ở đường dẫn đã nêu, stdout của chương trình riêng này là:

```text
Has manifest: true
Has app class: true
Has Boot launcher: true
```

Nếu chạy tool này với WAR truyền thống **không repackage**, mục launcher thường thành `false`. Chương trình chỉ kiểm tra **entry có tồn tại**, chưa kiểm tra manifest `Main-Class`, dependency completeness hoặc khả năng khởi động thật. Vì vậy vẫn cần kiểm thử thực tế hai mode.

## 12. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân/giả thuyết | Kiểm tra và xử lý |
|---|---|---|
| `java -jar app.war` báo `no main manifest attribute` | WAR thường, chưa có launcher manifest | Kiểm tra `spring-boot-maven-plugin:repackage`/`bootWar`, trích manifest |
| Có `main` trong Java nhưng `java -jar` không chạy | JAR/WAR chưa được repackage hoặc manifest sai | Xem `Main-Class`/`Start-Class`, plugin build và artifact thực |
| `WarLauncher` không có trong archive | Đang dùng plain WAR hoặc đóng gói sai | `jar tf`; chọn output `bootWar` hay repackage |
| `java -jar` lỗi thiếu Tomcat class | Provided dependency không được đóng `lib-provided` hoặc sai runtime dependencies | Kiểm tra `WEB-INF/lib-provided`, POM/Gradle config |
| Deploy lên Tomcat ngoài xung đột servlet engine | Embedded container đặt sai trong `WEB-INF/lib` | Dùng Maven `provided`/Gradle `providedRuntime` rồi build lại |
| WAR chạy độc lập nhưng external Tomcat 404 | Sai context path, chưa deploy, initializer không hoạt động, request mapping sai | Xem server log, `/war-lab/hello`, cấu hình `SpringBootServletInitializer` |
| External Tomcat startup lỗi `ClassNotFoundException` | Không có dependency runtime phù hợp trong `WEB-INF/lib` hoặc container classloader khác | Đọc `Caused by`, JAR list, server libraries, scope |
| `NoClassDefFoundError javax.servlet` / `jakarta.servlet` | API namespace/container không tương thích | So Spring Boot 3.x với Tomcat 10.1, kiểm tra thư viện migration |
| `server.port=8081` không làm Tomcat ngoài đổi cổng | Port của external container do server quản lý | Sửa Tomcat connector config, không dùng Spring embedded property |
| WAR bị phân phối nhầm bản `-plain.war` | Pipeline chọn artifact sai | Kiểm tra manifest, `war` vs `bootWar`, file dùng để deploy |
| `java -jar` port 8080 bị chiếm | Hai server cùng bind một port | Dừng một server hoặc đổi `--server.port` |
| WAR deploy chậm/không khởi tạo bean | Profile, JNDI, datasource, migration, container init khác nhau | Kiểm tra config và log đúng mode |
| Controller chạy embedded nhưng không được quét ở external mode | `configure` trả sai source/cấu hình application context | Dùng `application.sources(WarLabApplication.class)` như ví dụ |
| `WEB-INF/lib-provided` có JAR nhưng container ngoài không dùng | Đây là mục đích của layout dual-mode | Phân biệt classpath của WarLauncher và external container |
| Docker image chạy Boot JAR nhưng pipeline đang deploy WAR | Đường phát hành chưa nhất quán | Xác định artifact/vòng đời mong muốn, kiểm tra startup command |
| WAR WebFlux không triển khai truyền thống | Reactivity/Netty khác Servlet WAR | Dùng dạng triển khai phù hợp, không chỉ đổi packaging |

### Lộ trình khắc phục có thứ tự

1. **Tìm đúng artifact** đang chạy hoặc được deploy, ghi version/checksum.
2. **Trích manifest**, xác định có `WarLauncher` và `Start-Class` hay không.
3. **Liệt kê archive**, phân biệt `WEB-INF/classes`, `lib`, `lib-provided` và các thư viện nhúng.
4. **Xem build configuration**: Maven `packaging=war`, `provided`, `repackage`; Gradle `war`, `providedRuntime`, `bootWar`.
5. **Đọc log đúng process**: stdout của executable WAR hay log của Tomcat bên ngoài.
6. **Kiểm tra cổng/context path** trước khi nghi controller không tồn tại.
7. **Đối chiếu JDK/Jakarta Servlet compatibility** và container version.
8. **Chạy thử cả hai mode** trên môi trường tương ứng nếu yêu cầu dual-mode.
9. **Sửa tại source/build**, build lại, không chỉnh thủ công WAR đã phát hành.
10. **Bổ sung smoke/integration test** cho chế độ sẽ dùng ở production.

## 13. Khi nào chọn executable JAR, traditional WAR hay executable WAR?

| Nhu cầu thực tế | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Microservice tự chạy, đóng Docker, không bắt buộc external servlet container | **Spring Boot executable JAR** | Cách đóng gói đơn giản, vận hành embedded server |
| Tổ chức bắt buộc triển khai nhiều webapp vào một Tomcat/application server quản lý tập trung | **Traditional deployable WAR** | Hạ tầng ngoài quản lý server, cổng, context, shared service |
| Muốn một artifact dùng được cả external Tomcat lẫn `java -jar` | **Spring Boot executable WAR** với provided dependencies đúng | Kết hợp servlet deployment và Boot Launcher |
| Dự án Spring WebFlux mặc định dùng Reactor Netty | **Executable JAR/image**, không traditional WAR | Không hỗ trợ traditional WAR theo hướng dẫn của Boot |
| Có application server tùy biến, JNDI/shared classloader/policy phức tạp | WAR tương thích container, kiểm thử trên server thật | Tương thích runtime quan trọng hơn đuôi file |

**Không chọn WAR chỉ vì “Spring Boot web thì phải WAR”.** Spring Boot rất thường dùng executable JAR. Chỉ cần WAR nếu yêu cầu hạ tầng, tích hợp container, hoặc muốn chính sách dual-mode cụ thể.

## 14. Checklist cuối bài

- [ ] Phân biệt rõ **Servlet container bên ngoài** và **embedded server**.
- [ ] Biết WAR truyền thống không tự chạy bằng `java -jar` chỉ nhờ extension `.war`.
- [ ] Biết `SpringBootServletInitializer.configure` phục vụ đường bootstrap của external servlet container.
- [ ] Biết `main` và `SpringApplication.run` phục vụ đường khởi động executable WAR.
- [ ] Hiểu `WarLauncher` lấy class từ `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`.
- [ ] Với Maven, có `<packaging>war</packaging>`, Tomcat `provided` và Boot `repackage` phù hợp.
- [ ] Với Gradle, có `war` plugin, `providedRuntime` và `bootWar` phù hợp.
- [ ] Biết `WEB-INF/lib-provided` giúp embedded Tomcat có mặt khi chạy trực tiếp nhưng không xung đột với server ngoài.
- [ ] Biết manifest `Main-Class` và `Start-Class` khác nhau.
- [ ] Không nhầm **external Tomcat port/context** với `server.port`/context của embedded Boot.
- [ ] Đã xác nhận JDK, Jakarta Servlet API và container tương thích.
- [ ] Đã chạy smoke test endpoint trên **đúng artifact và đúng mode triển khai**.

**Tóm lại:** WAR triển khai truyền thống được **servlet container bên ngoài** khởi tạo. Spring Boot executable WAR có cùng nền tảng WAR nhưng được build thêm **Boot Loader + manifest + runtime dependencies phù hợp**, nên vừa triển khai được lên container tương thích vừa chạy độc lập qua `java -jar`. Sự khác biệt quyết định nằm ở **đường bootstrap và cách đóng gói**, không nằm ở phần đuôi `.war`.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.5 — Launching Executable Jars/Wars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 — Nested JARs và WAR layout](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — Maven Plugin Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle Plugin Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Gradle — The War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
