# Kiểm tra tương thích Java, Servlet, Jakarta và máy chủ đích khi triển khai WAR

## 1. Vì sao WAR build thành công vẫn có thể không triển khai được?

Một ứng dụng Spring Boot có thể chạy trong IDE, hoàn tất `mvn clean package` và tạo ra file `.war` nhưng thất bại khi được đưa lên Tomcat hoặc servlet container đích. Nguyên nhân phổ biến nằm ở **Java runtime**, **phiên bản Servlet API**, **namespace Java EE/Jakarta EE**, **thư viện trong WAR** hoặc **cách máy chủ khởi tạo ứng dụng**.

Ví dụ quan trọng: Spring Boot 3.x dùng các lớp `jakarta.servlet.*`, trong khi Tomcat 9 triển khai Servlet 4.0 với `javax.servlet.*`. Tomcat 9 chạy bằng Java 17 hay 21 vẫn không tự trở thành Jakarta Servlet container. Đổi JDK **không** thay đổi tên class API ở mức bytecode.

Đây là bài thuộc mục **WAR triển khai** trong chủ đề **Spring Boot Build Tooling Packaging**. Sau bài học, bạn có thể:

1. Lập ma trận Java/JVM, Servlet specification, Jakarta namespace và server version cho dự án.
2. Phân biệt JDK dùng compile với JVM **thực sự** chạy Tomcat.
3. Xác định vì sao `javax.servlet` và `jakarta.servlet` không thể tráo đổi.
4. Cấu hình WAR đúng bằng Maven, `SpringBootServletInitializer` và container dependency scope `provided`.
5. Kiểm tra bytecode, manifest, `WEB-INF/lib` và `WEB-INF/lib-provided` bằng JDK.
6. Deploy WAR lên external Tomcat và xem Java/Servlet/container version tại runtime.
7. Chẩn đoán các lỗi startup, classpath, namespace, context path và Servlet API.

**Stack thực hành:** Java target `17`, Spring Boot `3.5.16`, Maven, external Tomcat `10.1.x` với Servlet `6.0`. Các version được pin để ví dụ có thể đối chiếu tài liệu, không có nghĩa đây là bản mới nhất hoặc bắt buộc với mọi project. Nếu dùng Spring Boot 4.x, không áp dụng nguyên xi ma trận Boot 3.5.

## 2. Năm điều kiện cần đồng thời đúng

| Trục kiểm tra | Cần xác minh | Nếu sai sẽ ra sao? |
| --- | --- | --- |
| Java build/bytecode | JDK compile, release target, class major version | WAR có class mới hơn Java đích |
| JVM của server | Java **tiến trình Tomcat service** thật sử dụng | `UnsupportedClassVersionError` ngay khi load class |
| Servlet specification | Servlet 4.0/5.0/6.0/6.1, Pages/EL/WebSocket nếu có | Class/method được gọi không tồn tại trên server |
| API namespace | `javax.servlet` hay `jakarta.servlet` ở application và dependencies | `ClassNotFoundException`, `NoClassDefFoundError`, type mismatch |
| Server product/patch/deploy | Tomcat, Jetty, WildFly, WebLogic... version, context, classloader | WAR không deploy hoặc chạy theo môi trường khác mong đợi |

Ngoài năm trục trên còn phải kiểm tra **dependency scopes**. Một WAR có thể đóng gói nhầm embedded Tomcat vào `WEB-INF/lib` rồi xung đột với Tomcat bên ngoài; hoặc chỉ chạy bằng `java -jar` nhờ provided dependencies nhưng không có Servlet initializer đúng để external container nạp app.

Vì vậy công thức thực tế là:

~~~text
WAR deploy được
    = Java runtime đủ mới
    + class-file target được hỗ trợ
    + Servlet API/version phù hợp
    + namespace Java EE/Jakarta EE khớp
    + container version và configuration tương thích
    + dependencies/scopes đúng
    + kiểm chứng external deployment thành công
~~~

Không trộn lẫn các điều kiện. Tomcat 10.1 tự nó chạy được trên Java 11+, nhưng ứng dụng Spring Boot 3.5 yêu cầu Java 17+, nên JVM của Tomcat **phải đáp ứng yêu cầu cao hơn**.

## 3. Ma trận Tomcat, Java, Servlet và Spring Boot

### 3.1. Các dòng Tomcat

| Tomcat | Servlet specification | Namespace | Java tối thiểu của Tomcat | Nhận xét |
| --- | --- | --- | --- | --- |
| `9.0.x` | `4.0` | `javax.servlet.*` | `8+` | Nhánh Java EE; không phải đích thích hợp của WAR Spring Boot 3/Jakarta |
| `10.0.x` | `5.0` | `jakarta.servlet.*` | `8+` | Nhánh chuyển đổi Jakarta, đã hết hỗ trợ; tránh dùng cho production mới |
| `10.1.x` | `6.0` | `jakarta.servlet.*` | `11+` | Ví dụ phù hợp với Boot 3.5; ứng dụng Boot vẫn cần Java 17+ |
| `11.0.x` | `6.1` | `jakarta.servlet.*` | `17+` | Nhánh Servlet 6.1, phù hợp để đánh giá stack Boot 4.x |

Đây là các yêu cầu **của sản phẩm Tomcat**, dựa trên tài liệu chính thức Apache Tomcat. Luôn chọn **patch được hỗ trợ**, không chỉ chọn major/minor. Những server khác có ma trận riêng, không thể suy ra từ tên sản phẩm hoặc chữ “Jakarta”.

### 3.2. Những thế hệ Spring Boot dễ gặp

| Framework | Java tối thiểu | Servlet và namespace trọng tâm | Định hướng |
| --- | --- | --- | --- |
| Spring Boot `2.7.x` / Framework 5 | Java `8+` | Java EE Servlet, `javax.servlet.*` | Thường cùng Tomcat9; chuyển sang Boot3 cần migration |
| Spring Boot `3.5.x` / Framework 6.2 | Java `17+` | Jakarta Servlet; bộ embedded Tomcat10.1 / Servlet6.0 | Tài liệu hỗ trợ external Servlet5.0+ container; ví dụ chọn Tomcat10.1 |
| Spring Boot `4.1.x` / Framework 7 | Java `17+` | Servlet `6.1+` | Cần container đáp ứng Servlet6.1+, như Tomcat11 |

Cùng namespace Jakarta không có nghĩa Servlet 5.0, 6.0 và 6.1 giống nhau. Nếu framework/library gọi một method chỉ xuất hiện ở spec mới, một container cũ có thể gây `NoSuchMethodError` dù namespace đã là `jakarta`.

Lưu ý ba con số **không đồng nghĩa**: `Tomcat 10.1` là version sản phẩm; `Jakarta EE 10` là version platform bao gồm nhiều specs; `Jakarta Servlet 6.0` là version một specification. Servlet container như Tomcat **không** tự cung cấp mọi dịch vụ của một full Jakarta EE application server.

## 4. Java: kiểm tra runtime đúng tiến trình và class bytecode

### 4.1. Đừng chỉ xem java -version của terminal

Ở môi trường build:

~~~bash
java -version
javac -version
mvn -version
~~~

Các lệnh trên cho biết terminal developer/build agent đang dùng JDK nào. Tomcat có thể chạy dưới Windows Service, systemd, container hoặc một user riêng, chọn JVM theo service configuration. Điều cần chứng minh là **JVM của tiến trình đang triển khai WAR**, không chỉ `JAVA_HOME` của shell.

Với một Tomcat cài bằng script, có thể xem version qua:

~~~bash
"$CATALINA_HOME/bin/version.sh"
~~~

Trên Windows dùng `version.bat` trong thư mục `bin`. Nhưng nếu Tomcat do service manager chạy, script có thể phản ánh Java environment **khác** JVM của service. Kiểm tra log startup của service, command line/JVM path, image runtime và (khi được phép) một endpoint báo `Runtime.version().feature()` từ chính web app.

### 4.2. Class-file major versions

| Java target | Major version |
| --- | --- |
| Java `8` | `52` |
| Java `11` | `55` |
| Java `17` | `61` |
| Java `21` | `65` |
| Java `25` | `69` |

Ví dụ bytecode `major=65` được compile cho Java21 sẽ không nạp được trên JVM Java17. Việc Tomcat10.1 hỗ trợ Java11+ không giúp giải quyết class file quá mới hay ứng dụng Spring Boot3.5 yêu cầu Java17+.

Sau `mvn compile`, kiểm tra class đã tạo:

~~~bash
javap -verbose -classpath target/classes demo.WarApplication
~~~

Với cấu hình Java17, tìm `major version: 61`. File `WarInspect.java` ở mục 8 có thể kiểm tra class **bên trong WAR**. Tuy nhiên một class của app major61 không chứng minh toàn bộ dependencies đều hỗ trợ Java17: một JAR bên thứ ba có class major65 vẫn gây lỗi khi server nạp nó.

**Quy tắc:** mức Java tối thiểu của toàn stack là mức cao nhất mà Spring Boot, servlet container, ứng dụng và dependencies đòi hỏi. Khi nâng JDK trên server, kiểm tra mọi dịch vụ/container thực tế đã chuyển JVM và test lại. 

## 5. Namespace javax.servlet và jakarta.servlet khác nhau ở bytecode

Hai đoạn import sau **không tương đương**:

~~~java
// Java EE / Tomcat 9
import javax.servlet.http.HttpServletRequest;
~~~

~~~java
// Jakarta EE / Spring Boot 3+
import jakarta.servlet.http.HttpServletRequest;
~~~

JVM nhìn thấy hai tên class:

~~~text
javax/servlet/http/HttpServletRequest
jakarta/servlet/http/HttpServletRequest
~~~

Nếu một filter bên thứ ba đã compile với `javax.servlet.Filter`, đưa nó vào môi trường Jakarta không thể tự chuyển sang `jakarta.servlet.Filter`. Các lỗi có thể chỉ xuất hiện lúc external Tomcat khởi tạo webapp, dù mã của chính bạn đã migrate và Maven build xanh.

Một số nhóm API cần xét khi nâng Java EE lên Jakarta EE:

| API trước đây | API tương ứng trong Jakarta |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.websocket.*` | `jakarta.websocket.*` |

**Không tìm và thay tất cả `javax.`**: nhiều Java SE APIs vẫn có namespace `javax`, chẳng hạn `javax.sql`, `javax.crypto`, `javax.net.ssl` và `javax.naming`. Chỉ migrate những APIs Java EE/Jakarta EE liên quan, đồng thời cập nhật libraries thứ ba.

Một lỗi tương tự xuất hiện nếu compile với Servlet6.1 nhưng runtime container chỉ triển khai Servlet6.0. Namespace đều là Jakarta, nhưng specification version và tập methods khác nhau. Cách giải quyết đúng là chọn version API/framework phù hợp với **server thực tế** hoặc nâng server, không đơn thuần thêm một JAR Servlet API cao hơn vào WAR.

## 6. Maven WAR, SpringBootServletInitializer và provided scope

Đối với Spring Boot WAR deploy vào external servlet container, cần ba thành phần:

1. Maven `<packaging>war</packaging>` để tạo archive WAR thực sự.
2. Một subclass `SpringBootServletInitializer` cấu hình Spring application cho lifecycle của external servlet container.
3. Embedded servlet container dependency, ví dụ `spring-boot-starter-tomcat`, đánh dấu `provided` thay vì đóng gói làm runtime library bình thường.

Trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

`provided` **không** có nghĩa compiler không thấy Servlet API. Nó thông báo runtime container ngoài sẽ cung cấp implementation. Với executable WAR do Spring Boot repackage tạo, các container libraries provided có thể xuất hiện trong `WEB-INF/lib-provided` để lệnh `java -jar` vẫn khởi động embedded server. External Tomcat **không** coi `WEB-INF/lib-provided` là các library chuẩn ở `WEB-INF/lib`.

Không thêm `javax.servlet-api` vào WAR Boot3 để “vá” Tomcat9. Cũng không tự đóng gói `jakarta.servlet-api` version quá cao với hy vọng nâng servlet engine của server. Cần kiểm tra Maven scopes và Servlet implementation từ máy chủ đích.

## 7. Ví dụ WAR đầy đủ: Maven, Spring Boot 3.5 và Java 17

Cấu trúc thư mục:

~~~text
compat-war-demo/
  pom.xml
  WarInspect.java
  src/
    main/
      java/
        demo/
          WarApplication.java
          CompatibilityController.java
~~~

### 7.1. pom.xml

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

    <groupId>example.learning</groupId>
    <artifactId>compat-war-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `spring-boot-starter-parent` quản lý versions tương thích và cấu hình plugin; khi `spring-boot-maven-plugin` được khai báo, goal `repackage` được parent gắn vào lifecycle package.
- `packaging=war` chọn Maven WAR packaging.
- `java.version=17` đặt Java compile target theo parent; không chứng minh Java của Tomcat service.
- `spring-boot-starter-web` cung cấp Spring MVC/web stack.
- Khai báo trực tiếp `spring-boot-starter-tomcat` scope `provided` để bên ngoài cung cấp container, còn executable WAR vẫn có thể dùng `WEB-INF/lib-provided`.

Nếu project **không dùng** Boot starter parent, cần tự quản lý dependency versions, Maven compiler và bind `repackage` theo đúng lifecycle; một plugin declaration không có execution phù hợp chưa đủ.

### 7.2. WarApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(WarApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarApplication.class);
    }
}
~~~

`main` dùng khi chạy executable WAR bằng `java -jar`. `SpringBootServletInitializer.configure` dùng khi **external Tomcat** nạp WAR qua Servlet lifecycle. Hai đường khởi động này khác nhau: WAR chạy với embedded server tốt **không** đảm bảo external deployment thành công.

### 7.3. CompatibilityController.java

~~~java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CompatibilityController {

    @GetMapping(value = "/probe",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return "war-ok";
    }

    @GetMapping(value = "/compat",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String compatibility(HttpServletRequest request) {
        var context = request.getServletContext();
        return "java.feature="
                + Runtime.version().feature() + "\n"
                + "servlet.version="
                + context.getMajorVersion() + "."
                + context.getMinorVersion() + "\n"
                + "server=" + context.getServerInfo() + "\n";
    }
}
~~~

Code trên có import `jakarta.servlet.http.HttpServletRequest`, đúng thế hệ API Spring Boot3. Với `GET /probe` body trả **chính xác** `war-ok`, không có newline do method thêm. `GET /compat` trả Java feature của **JVM phục vụ request**, Servlet version từ ServletContext và tên/version máy chủ từ `getServerInfo()`.

`/compat` chỉ nên để ở môi trường kiểm thử hoặc được bảo vệ: tiết lộ JDK/container version ra endpoint public là không cần thiết trong production.

Không cần `WEB-INF/web.xml` cho cách bootstrap Spring Boot bằng initializer/annotations trong ví dụ. Nếu ứng dụng có descriptor `web.xml` cũ, phải kiểm tra namespace/schema và filter/listener declarations theo Jakarta.

## 8. Build, inspect và kiểm tra class file trong WAR

Tại project root:

~~~bash
mvn clean package
jar tf target/compat-war-demo-1.0.0.war
~~~

Nếu dự án có Maven Wrapper, tương đương `./mvnw clean package` hoặc `.\mvnw.cmd clean package` trong Windows PowerShell. Output mong đợi của archive **rút gọn** là:

~~~text
META-INF/MANIFEST.MF
WEB-INF/classes/demo/WarApplication.class
WEB-INF/classes/demo/CompatibilityController.class
WEB-INF/lib/...
WEB-INF/lib-provided/...
org/springframework/boot/loader/...
~~~

Các dấu `...` thể hiện listing rút gọn, không phải stdout chính xác của `jar tf`. Trong executable WAR, các runtime libraries ở `WEB-INF/lib`, còn libraries như Tomcat provided có thể nằm dưới `WEB-INF/lib-provided`.

### 8.1. Tiện ích Java 17 kiểm tra WAR trực tiếp

Đặt `WarInspect.java` tại root, **ngoài** `src/main/java`, để công cụ không bị đóng gói vào WAR:

~~~java
import java.io.DataInputStream;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class WarInspect {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java WarInspect.java <war-path>");
        }

        try (JarFile war = new JarFile(
                Path.of(args[0]).toFile())) {
            JarEntry entry = war.getJarEntry(
                    "WEB-INF/classes/demo/WarApplication.class");
            if (entry == null) {
                throw new IllegalStateException("Missing main class");
            }

            int major;
            try (InputStream raw = war.getInputStream(entry);
                 DataInputStream in = new DataInputStream(raw)) {
                if (in.readInt() != 0xCAFEBABE) {
                    throw new IllegalStateException("Invalid class");
                }
                in.readUnsignedShort(); // minor version
                major = in.readUnsignedShort();
            }

            Manifest manifest = war.getManifest();
            Attributes attrs = manifest == null
                    ? new Attributes()
                    : manifest.getMainAttributes();

            boolean hasLibraries = war.stream().anyMatch(
                    e -> e.getName().startsWith("WEB-INF/lib/")
                            && e.getName().endsWith(".jar"));
            boolean providedTomcat = war.stream().anyMatch(
                    e -> e.getName().startsWith(
                            "WEB-INF/lib-provided/tomcat-embed-core-"));

            System.out.println("class.major=" + major);
            System.out.println("class.java=" + (major - 44));
            System.out.println("manifest.main="
                    + attrs.getValue("Main-Class"));
            System.out.println("manifest.start="
                    + attrs.getValue("Start-Class"));
            System.out.println("war.libs=" + hasLibraries);
            System.out.println(
                    "war.provided.tomcat=" + providedTomcat);
        }
    }
}
~~~

Chạy bằng Java 17 source-file launcher:

~~~bash
java WarInspect.java target/compat-war-demo-1.0.0.war
~~~

Với **đúng ví dụ** được compile cho Java17 và repackage thành công, output kỳ vọng là:

~~~text
class.major=61
class.java=17
manifest.main=org.springframework.boot.loader.launch.WarLauncher
manifest.start=demo.WarApplication
war.libs=true
war.provided.tomcat=true
~~~

Đây là **kết quả dự kiến theo POM**, không phải thông tin đã đo trên máy chủ của bạn. Các tên Boot loader phụ thuộc plugin version. Công cụ chỉ kiểm tra **class chính và cấu trúc archive**, không xác minh bytecode major của mọi class bên trong dependency JAR lồng và cũng không chứng minh các filter/libs không còn tham chiếu `javax.servlet`.

Nếu có `unzip`, có thể xem manifest riêng:

~~~bash
unzip -p target/compat-war-demo-1.0.0.war META-INF/MANIFEST.MF
~~~

`Main-Class` và `Start-Class` của executable WAR phục vụ Boot launcher. Khi external Tomcat deploy, nó dùng Servlet initializer, **không dựa vào `java -jar`** để khởi động WAR.

## 9. Smoke test executable WAR và external Tomcat khác nhau

### 9.1. Kiểm tra đường java -jar trước

Ở terminal thứ nhất:

~~~bash
java -jar target/compat-war-demo-1.0.0.war --server.address=127.0.0.1 --server.port=8087
~~~

Ở terminal thứ hai, sau khi startup:

~~~bash
curl -fsS http://127.0.0.1:8087/probe
curl -fsS http://127.0.0.1:8087/compat
~~~

Body chính xác của `/probe`:

~~~text
war-ok
~~~

`/compat` trả dữ liệu phụ thuộc runtime. Ví dụ trên Java17 và Tomcat10.1, output **có thể có dạng**:

~~~text
java.feature=17
servlet.version=6.0
server=Apache Tomcat/10.1.x
~~~

`10.1.x` là **ký hiệu minh họa nhánh version**, không phải text literal. Container in patch thực tế; nếu JVM chạy Java21, `java.feature=21`. Khi hoàn tất, dừng tiến trình bằng `Ctrl+C`. Trong CI hãy dùng runner có timeout và cleanup.

Dù phép thử này PASS, nó chỉ chứng minh **executable WAR với embedded runtime**. External Tomcat có JVM, Servlet implementation, classloader và context configuration **riêng**, nên cần deploy thử tiếp.

### 9.2. Thử đúng external Tomcat10.1 trong staging

Trước khi deploy, xác minh server:

- Tomcat `10.1.x` patch còn được hỗ trợ.
- JVM **service** đang chạy Java17+.
- Container triển khai Servlet6.0/Jakarta namespace.
- Đã biết `CATALINA_BASE`, deploy mechanism, context path, connector port và cách rollback.
- Có quyền triển khai ứng dụng thử nghiệm, không ghi đè WAR đang vận hành ngoài ý muốn.

Trong một staging Tomcat **được phép sử dụng autoDeploy**, với `CATALINA_BASE` đã đặt:

Linux/macOS:

~~~bash
cp target/compat-war-demo-1.0.0.war "$CATALINA_BASE/webapps/compat.war"
~~~

Windows PowerShell:

~~~powershell
Copy-Item .\target\compat-war-demo-1.0.0.war "$env:CATALINA_BASE\webapps\compat.war"
~~~

Nếu Tomcat tắt autoDeploy hoặc dùng Tomcat Manager/platform CI/CD, hãy sử dụng cơ chế đó; copy file chưa chắc đã deploy. Filename `compat.war` thường tạo context `/compat` khi server không ghi đè context mapping.

Sau khi xem server deploy logs và xác nhận context active, gọi URL ví dụ:

~~~bash
curl -fsS http://127.0.0.1:8080/compat/probe
curl -fsS http://127.0.0.1:8080/compat/compat
~~~

Đổi host/port/context theo **server thực tế**. `/compat` sẽ đọc JVM/ServletContext của **external** server, khác với endpoint từ executable WAR ở mục 9.1. Kết quả cần có Java feature tối thiểu 17, Servlet6.0 và server info đúng Tomcat10.1.

Nếu gặp 404, đừng vội quy lỗi Java/Jakarta: có thể sai context path, WAR chưa được deploy, route không được map, proxy/vhost sai hoặc context startup đã fail. Kiểm tra deployment logs trước.

## 10. Kiểm tra dependency graph và thư viện javax cũ

Với POM thật, chạy:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
mvn help:effective-pom
~~~

Dependency tree cho biết version/scopes đã resolve, còn effective POM cho biết cấu hình kế thừa. Nhưng một thư viện có thể chứa Servlet API classes **trong artifact khác** hoặc tham chiếu `javax.servlet` qua reflection, `META-INF/services` hay configuration. Không có node `javax.servlet-api` trong cây **không** đảm bảo không còn static/dynamic references.

Quy trình phù hợp:

1. Tìm imports `javax.servlet` trong mã ứng dụng/filters/listeners; không đụng Java SE `javax.*`.
2. Kiểm tra JAR bên thứ ba có bản hỗ trợ Jakarta hay chưa, đặc biệt security integrations, JSP taglibs và Servlet filters.
3. Inspect `WEB-INF/lib` xem có embedded Tomcat hoặc Servlet API không nên đi kèm.
4. Kiểm tra compile target của dependencies, không chỉ class application.
5. Triển khai WAR lên đúng external server và đọc stack trace nếu startup fail.

`jdeps` có thể giúp phân tích dependencies ở mức class, nhưng executable WAR chứa nested JARs; muốn phân tích sâu phải trích xuất/classes libraries vào môi trường kiểm tra và thiết lập classpath. Static analysis không nhìn thấy mọi reflection/dynamic loading, nên **không thay** smoke test trên server thật.

## 11. Máy chủ khác Tomcat và các thành phần Jakarta EE khác

Không suy ra một server tương thích chỉ vì tên sản phẩm chứa chữ Jakarta. Với WebLogic, WildFly, Jetty, Payara hay môi trường vendor-managed, cần đọc **compatibility matrix cho đúng product release và patch**:

- Servlet/Jakarta specifications thực sự được server triển khai.
- JVM versions được hỗ trợ và Java đang chạy trên service.
- Container classloader rules, libraries cấp server, deployment descriptors.
- Context path, servlet mappings, reverse proxy và security.
- JSP/Pages, EL, WebSocket, Persistence, CDI/transactions hoặc những Jakarta APIs khác dự án sử dụng.
- Yêu cầu riêng cho servlet initializer, WAR deployment và libraries provided.

Tomcat tập trung vào servlet/web stack và không phải implementation toàn bộ Jakarta EE. Một application server đầy đủ có thể cung cấp nhiều APIs hơn; nếu WAR cũng mang những bản library khác, classloading conflicts có thể khác so với Tomcat.

**Đừng hiểu cùng Servlet 6.0 là mọi thứ giống nhau.** Patch version, classloader policy, vendor support, annotations/JSP behavior và các tích hợp môi trường còn ảnh hưởng. Điểm kết luận phải là **WAR thật đã hoạt động theo yêu cầu trên môi trường đích**.

## 12. Lỗi thường gặp khi triển khai

| Hiện tượng | Nguyên nhân cần điều tra | Bằng chứng |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM server quá cũ so với class app/library | Server JVM, class major, dependency JAR versions |
| `NoClassDefFoundError: jakarta/servlet/...` | Server còn `javax.servlet` hoặc thiếu Jakarta API | Tomcat version và Servlet spec |
| `NoClassDefFoundError: javax/servlet/...` | Filter/library cũ chưa migrate sang Jakarta | Dependency graph và class references |
| `NoSuchMethodError` ở Servlet API | Compile dùng method/spec cao hơn runtime | Servlet API version/method owner |
| `ClassCastException` Servlet/Filter | Trộn namespace hoặc classloaders | `WEB-INF/lib` vs server-wide libraries |
| `SpringBootServletInitializer` không được gọi | Thiếu initializer, cấu hình startup/deploy sai | Source app và Tomcat logs |
| `java -jar` PASS nhưng deploy external FAIL | Hai đường bootstrap, scope và classloader khác | WAR/servlet container logs |
| HTTP404 sau deploy | Sai context path, route, autoDeploy hoặc startup fail | Context mapping và logs |
| HTTP401/403 | Security/filter/proxy configuration | Auth, security policy và request headers |
| JSP lỗi dù controller hoạt động | JSP/EL/JSTL version không phù hợp | Jakarta Pages/EL spec và library versions |
| Tomcat10.1 chạy Java11 nhưng Boot3.5 FAIL | Boot yêu cầu Java17+ | JVM service/version và logs |
| Boot4.1 trên Tomcat10.1 FAIL | Boot4.1 cần Servlet6.1+, Tomcat10.1 chỉ Servlet6.0 | Boot requirements và Tomcat spec |
| Local PASS, production FAIL | Khác Java, container patch, classloader/env | So compatibility records và logs |
| Build PASS nhưng deploy WAR cũ | Script chọn nhầm file/version | Artifact path, checksum, deploy logs |

Tên exception là **manh mối**, không đủ kết luận. Hãy xem full stack trace và tìm **class/method owner** thực sự thiếu. Tránh “chữa” bằng cách nâng bừa JDK hoặc thêm một API JAR chưa rõ tác dụng.

## 13. Checklist nghiệm thu trước khi phát hành

- [ ] Xác định Spring Boot/Framework versions và phiên bản Servlet/Jakarta mục tiêu.
- [ ] Xác định JDK runtime **của service**, Java target bytecode và Java requirements của dependency.
- [ ] Server được hỗ trợ, Servlet spec phù hợp; không nhầm Tomcat9 `javax` với Tomcat10/11 `jakarta`.
- [ ] `packaging=war`, `SpringBootServletInitializer` và container `provided` được cấu hình.
- [ ] WAR artifact chứa `WEB-INF/classes`, các libraries đúng scope và có đường deploy rõ ràng.
- [ ] Kiểm tra dependency graph, thư viện `javax.servlet` cũ và các API Jakarta cần dùng.
- [ ] Build sạch; xác nhận đúng file WAR, không dùng wildcard chọn nhầm artifact.
- [ ] Deploy WAR vào **external** server staging cùng stack target.
- [ ] Xem startup logs; gọi probe/compat, kiểm tra HTTP status, body và JVM/ServletContext từ server thật.
- [ ] Chạy thêm smoke/integration tests cho tính năng JSP, WebSocket, security, sessions, database nếu app sử dụng.
- [ ] Lưu checksum file WAR đã thử nghiệm và deploy **chính file ấy**; có kế hoạch rollback.

### Câu hỏi tự kiểm tra

**A. Tomcat9 chạy Java21, ứng dụng Spring Boot3.5 compile cho Java17. Có chắc deploy được?**

Không. JVM mới đọc được bytecode cũ nhưng Tomcat9 vẫn là Servlet4.0 `javax.servlet`, không phù hợp namespace `jakarta.servlet` của Boot3.

**B. Tomcat10.1 tự hỗ trợ Java11, vậy Boot3.5 có thể chạy trên JVM11 không?**

Không. Spring Boot3.5 cần Java17+; mức tối thiểu của toàn stack là mức cao nhất trong các yêu cầu.

**C. WAR chạy bằng `java -jar` có đủ chứng minh deploy external Tomcat được không?**

Chưa. `java -jar` dùng Boot launcher/embedded libraries; external deploy dùng Servlet initializer và container APIs/classloader thực tế.

**D. Có nên thêm một bản `jakarta.servlet-api` mới vào `WEB-INF/lib` để nâng Tomcat cũ không?**

Không. API JAR không thay thế servlet implementation của server và có thể gây xung đột. Chọn container hỗ trợ đúng specification.

**E. Boot4.1 và Tomcat10.1 đều hỗ trợ Java17. Đã tương thích chưa?**

Chưa: Boot4.1 cần Servlet6.1+, trong khi Tomcat10.1 là Servlet6.0. Phải đối chiếu cả Servlet spec.

## 14. Tài liệu chính thức

- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 4.1 — System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot — Traditional WAR Deployment: https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html
- Spring Boot Maven Plugin — Packaging: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Apache Tomcat — Which Version Do I Want?: https://tomcat.apache.org/whichversion.html
- Apache Tomcat — Migration Guide 10.1: https://tomcat.apache.org/migration-10.1.html
- Apache Tomcat — Migration Guide 11.0: https://tomcat.apache.org/migration-11.0.html
- Maven — Dependency Mechanism and Scopes: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java 17 — Class File Format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html

**Ghi nhớ:** Muốn biết một WAR có tương thích máy chủ đích không, phải kiểm tra **Java runtime, bytecode, Servlet specification, namespace Java EE/Jakarta EE, dependencies/scopes, server version và một phép external deployment thật**. Build thành công hay executable WAR chạy được trong môi trường khác chưa đủ chứng minh khả năng triển khai.