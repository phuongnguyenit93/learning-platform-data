# Maven WAR Plugin và cấu trúc ứng dụng web đóng gói

## 1. Vì sao Maven có định dạng WAR?

**WAR (Web Application Archive)** là định dạng đóng gói một web application Java để triển khai vào **servlet container** như Apache Tomcat. WAR có cấu trúc thư mục theo Servlet specification: các file static ở web root, classes/resources tại `WEB-INF/classes`, thư viện runtime tại `WEB-INF/lib` và có thể có `WEB-INF/web.xml`.

Khi `pom.xml` có `<packaging>war</packaging>`, Maven thường bind goal `maven-war-plugin:war` vào phase `package`. Sau compilation, resource processing và unit testing, plugin tạo archive `target/<artifactId>-<version>.war`.

Ví dụ:

~~~text
war-layout-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/web/HelloServlet.java
    │   ├── resources/version.properties
    │   └── webapp/
    │       ├── index.html
    │       └── assets/site.css
    └── test/
        └── java/dev/example/web/GreetingServiceTest.java
~~~

Sau build, WAR có thể chứa:

~~~text
index.html
assets/site.css
WEB-INF/
  classes/
    dev/example/web/HelloServlet.class
    version.properties
  lib/
    commons-lang3-3.17.0.jar
  web.xml                           (nếu project dùng descriptor)
META-INF/
  MANIFEST.MF
~~~

**Traditional WAR không tự là executable JAR.** `java -jar app.war` thường không chạy được nếu bạn chỉ dùng Maven WAR Plugin. Phương án chuẩn là deploy WAR lên Tomcat/application server tương thích. Spring Boot executable WAR khác vì có Spring Boot Maven Plugin `repackage` và launcher.

### Mục tiêu học tập

1. Hiểu `packaging=war`, phase `package` và `war:war`.
2. Phân biệt `src/main/java`, `src/main/resources`, `src/main/webapp`.
3. Hiểu `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/web.xml` và `META-INF`.
4. Biết khi nào cần `web.xml`, khi nào annotation `@WebServlet` đủ.
5. Cấu hình dependency scopes để WAR có đúng runtime JARs.
6. Dùng WAR Plugin `warSourceDirectory`, `webResources`, `packagingExcludes`, overlays.
7. Tạo project Java 17 + Jakarta Servlet 6.0 + JUnit 5 có POM hoàn chỉnh.
8. Build WAR, inspect bằng `jar tf`, deploy Tomcat 10.1 và gọi HTTP.
9. Phân biệt traditional WAR và Spring Boot executable WAR.
10. Chẩn đoán `404`, `500`, thiếu classes, sai `javax`/`jakarta`, resource/secret leaks.

## 2. Phân biệt WAR với các cách đóng gói Java khác

| Loại artifact | Nội dung | Cách chạy phổ biến |
| --- | --- | --- |
| Library JAR | Code/resources cho project khác | Đưa lên classpath qua Maven hoặc launcher |
| Thin JAR | Application classes; dependency ở ngoài | `java -jar` khi manifest/classpath hợp lệ |
| Fat/uber JAR | Classes/resources ứng dụng và dependencies được gộp | Thường `java -jar` |
| **Traditional WAR** | Web root, WEB-INF/classes và WEB-INF/lib | **Deploy servlet container** |
| **Spring Boot executable WAR** | WAR layout và Boot loader/repackage | Có thể `java -jar` hoặc external container nếu cấu hình phù hợp |

WAR là ZIP-based archive, vì vậy lệnh JDK:

~~~bash
jar tf target/war-layout-demo-1.0.0.war
~~~

cho phép inspect các entries. Tuy nhiên, servlet container có semantics nạp class, phục vụ file và lifecycle khác một Java launcher chỉ dùng `-cp`.

## 3. Đường đi của Java source, resource và web root

### 3.1. Java source

~~~text
src/main/java/dev/example/web/HelloServlet.java
   -> target/classes/dev/example/web/HelloServlet.class
   -> WAR: WEB-INF/classes/dev/example/web/HelloServlet.class
~~~

Maven Compiler Plugin biên dịch Java. WAR Plugin đóng kết quả, không compile `.java` được đặt tùy tiện ở web root.

### 3.2. Main resources

~~~text
src/main/resources/version.properties
   -> target/classes/version.properties
   -> WAR: WEB-INF/classes/version.properties
~~~

Đây là classpath resource có thể đọc bằng:

~~~java
InputStream in = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("version.properties");
~~~

Tệp ở `WEB-INF/classes` **không được phục vụ trực tiếp như URL static** `/version.properties`. Nếu muốn public file, đặt vào web root có chủ đích.

### 3.3. Web root

~~~text
src/main/webapp/index.html        -> WAR: index.html
src/main/webapp/assets/site.css   -> WAR: assets/site.css
~~~

Khi WAR deploy ở context `/war-layout-demo`, URL có thể là:

~~~text
/war-layout-demo/index.html
/war-layout-demo/assets/site.css
~~~

Vì web root có thể public, **không để secret, private key, backup hay file nội bộ tại `src/main/webapp`**.

### 3.4. WEB-INF/classes và WEB-INF/lib

`WEB-INF/classes` là một classpath root của webapp. Mỗi dependency JAR cần thiết cho runtime thường được đóng **nguyên JAR** vào `WEB-INF/lib`, ví dụ:

~~~text
WEB-INF/lib/commons-lang3-3.17.0.jar
~~~

Servlet container dùng những entries này khi nạp class. Không bắt buộc Shade/unpack từng dependency vào một uber JAR. Nhưng `WEB-INF` chỉ hạn chế HTTP trực tiếp; người có file WAR vẫn có thể giải nén đọc code/config. Đây không phải nơi lưu credentials thật.

### 3.5. WEB-INF/web.xml và META-INF

`WEB-INF/web.xml` là deployment descriptor cho Servlet, Filter, Listener, mappings, security constraints và init parameters. Từ Servlet 3.0, nhiều phần có thể khai qua annotations hoặc programmatic initialization, nên web.xml **không bắt buộc cho mọi webapp**.

`META-INF/MANIFEST.MF` là archive metadata; `META-INF/maven` có thể lưu Maven project metadata. Nó không thay thế `WEB-INF` trong Servlet packaging.

### 3.6. Test output

`src/test/java` và `src/test/resources` thường được Maven đưa vào `target/test-classes`, **không vào WAR sản xuất**. JUnit dependency `scope=test` không nên xuất hiện trong `WEB-INF/lib`. Nếu test fixtures lọt vào WAR, có thể custom `webResources`/copy logic đưa nhầm.

## 4. Lifecycle của packaging war

POM khai:

~~~xml
<packaging>war</packaging>
~~~

Các bước tiêu biểu của default lifecycle:

~~~text
process-resources        resources:resources
compile                  compiler:compile
process-test-resources   resources:testResources
test-compile             compiler:testCompile
test                     surefire:test
package                  war:war
verify                   verification goals nếu khai
~~~

Đây là sơ đồ rút gọn, không liệt kê toàn bộ lifecycle phases. Plugins, parent POM và profiles có thể thay đổi execution plan.

~~~bash
mvn -B -ntp clean package
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-war-plugin:3.5.0:war
~~~

`clean package` chạy từ đầu đến package, thường compile và test trước khi tạo WAR. `clean verify` đi xa hơn đến verify. Goal trực tiếp `war:war` **không đảm bảo classes/resources đã được chuẩn bị**. Đừng tạo thêm một execution `war:war` khác ID ở phase package chỉ để bật plugin: với `packaging=war` goal đã bind mặc định.

## 5. Các tham số Maven WAR Plugin

| Tham số | Dùng để làm gì? |
| --- | --- |
| `warSourceDirectory` | Thư mục nguồn web root, mặc định `src/main/webapp` |
| `warSourceIncludes`/`warSourceExcludes` | Include/exclude từ nguồn webapp |
| `webResources` | Bổ sung nguồn web files, hỗ trợ `targetPath`, includes/excludes và filtering |
| `webXml` | Đặt đường dẫn deployment descriptor tùy biến |
| `failOnMissingWebXml` | Có fail nếu không tìm web.xml không |
| `filteringDeploymentDescriptors` | Bật lọc web.xml, mặc định false |
| `nonFilteredFileExtensions` | Ngăn text filtering của các loại file binary |
| `packagingIncludes`/`packagingExcludes` | Lọc paths ở WAR cuối |
| `warName` | Tên WAR không gồm extension |
| `webappDirectory` | Nơi dựng exploded webapp trong target |
| `archiveClasses` | Đóng compiled classes vào một JAR dưới WEB-INF/lib |
| `attachClasses` | Tạo attached classes JAR phục vụ reuse |
| `overlays` | Merge dependent WAR artifacts theo thứ tự |
| `outputTimestamp` | Hỗ trợ reproducible archive timestamps |

Cấu hình tối thiểu:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-war-plugin</artifactId>
            <version>3.5.0</version>
            <configuration>
                <failOnMissingWebXml>false</failOnMissingWebXml>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là fragment trong POM, không phải project đầy đủ. `failOnMissingWebXml=false` rõ ràng khi ứng dụng dùng annotation registration và không có `web.xml`. Tài liệu WAR Plugin nêu từ version 3.1.0 nó có thể mặc định false nếu project phụ thuộc Servlet API 3.0 trở lên.

### 5.1. Source excludes khác packaging excludes

~~~xml
<warSourceExcludes>**/*.bak,**/*.tmp,**/.DS_Store</warSourceExcludes>
~~~

chỉ lọc file từ `warSourceDirectory`. Trong khi:

~~~xml
<packagingExcludes>**/*.map,**/*.bak</packagingExcludes>
~~~

lọc nội dung archive đã assemble. Hai đoạn này là fragments minh họa; không áp nếu file `.map` là yêu cầu của project. Loại nhầm `WEB-INF/lib` hoặc `WEB-INF/classes` có thể khiến WAR deploy lỗi. Excludes **không thay thế quy trình xử lý secret**.

## 6. Tomcat và Jakarta Servlet version

| Container | API và namespace | Java tối thiểu |
| --- | --- | --- |
| Tomcat 9 | Servlet 4.0, `javax.servlet.*` | Java 8 |
| Tomcat 10.1 | Jakarta Servlet 6.0, `jakarta.servlet.*` | Java 11 |
| Tomcat 11 | Jakarta Servlet 6.1, `jakarta.servlet.*` | Java 17 |

Ví dụ sẽ dùng **JDK 17, Tomcat 10.1 và Jakarta Servlet API 6.0**:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

`provided` là cần thiết vì container cung cấp Servlet API khi chạy, Maven chỉ cần API để compile/test. Nếu deploy WAR import `javax.servlet.http.HttpServlet` lên Tomcat 10.1 không qua migration, không thể giả định tương thích. Việc chuyển từ `javax` sang `jakarta` còn liên quan libraries, frameworks, web.xml và các filters/listeners khác.

## 7. Lab Java 17 + Jakarta Servlet 6.0 + JUnit 5

### 7.1. Project structure

~~~text
war-layout-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/web/
    │   │   ├── GreetingService.java
    │   │   └── HelloServlet.java
    │   ├── resources/version.properties
    │   └── webapp/
    │       ├── index.html
    │       └── assets/site.css
    └── test/
        └── java/dev/example/web/GreetingServiceTest.java
~~~

Cần Maven 3.9.x, JDK 17+, kết nối repository/mirror tải plugins/dependencies. Để chạy HTTP, cần Tomcat 10.1; chỉ build/inspect WAR không cần container. Lab dùng `@WebServlet` và **không có web.xml**.

### 7.2. POM đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>war-layout-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là POM **traditional WAR**, không phải Spring Boot. Servlet API là `provided`; Commons Lang là compile/runtime dependency phải có trong `WEB-INF/lib`; JUnit là test-only. `maven-war-plugin` tự được gọi khi `packaging=war` đi tới `package`.

### 7.3. GreetingService.java

Tạo `src/main/java/dev/example/web/GreetingService.java`:

~~~java
package dev.example.web;

import org.apache.commons.lang3.StringUtils;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String name) {
        String normalized = StringUtils.isBlank(name)
                ? "world"
                : name.trim();
        return "Hello, " + normalized + "!";
    }
}
~~~

`StringUtils.isBlank` xử lý null/whitespace. `greet(null)` trả `Hello, world!` và `greet(" Maven ")` trả `Hello, Maven!`. Commons Lang không thuộc JDK; khi runtime thiếu JAR nó có thể gây `NoClassDefFoundError`.

### 7.4. HelloServlet.java

Tạo `src/main/java/dev/example/web/HelloServlet.java`:

~~~java
package dev.example.web;

import java.io.IOException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet(name = "helloServlet", urlPatterns = "/hello")
public final class HelloServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        String name = request.getParameter("name");
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().print(GreetingService.greet(name));
    }
}
~~~

`@WebServlet("/hello")` đăng ký URL **bên trong context path**. `HttpServlet` đến từ `jakarta.servlet.*` của Servlet 6.0. `PrintWriter.print` không tự thêm newline. Đây là lab text/plain; trong dự án thật hãy thêm validation, output encoding/escaping và các policies bảo mật thích hợp.

### 7.5. Static files

`src/main/webapp/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Maven WAR Demo</title>
  <link rel="stylesheet" href="assets/site.css">
</head>
<body>
  <h1>Maven WAR Demo</h1>
  <p>Static HTML in the WAR web root.</p>
  <a href="hello?name=Maven">Call servlet</a>
</body>
</html>
~~~

`src/main/webapp/assets/site.css`:

~~~css
body {
    font-family: system-ui, sans-serif;
    margin: 2rem;
}
a {
    color: #175c9e;
}
~~~

Hai file được copy vào **root của WAR**. Link `hello?name=Maven` là relative URL, nên khi mở trong context `/war-layout-demo` nó gọi `/war-layout-demo/hello?name=Maven`.

### 7.6. Classpath properties

`src/main/resources/version.properties`:

~~~properties
app.name=war-layout-demo
app.version=1.0.0
~~~

Nằm trong `WEB-INF/classes/version.properties` sau packaging. Các giá trị là literal; không có Maven filtering tự động nếu chưa bật filtering cho resource root.

### 7.7. JUnit test

`src/test/java/dev/example/web/GreetingServiceTest.java`:

~~~java
package dev.example.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    @Test
    void normalizesNames() {
        assertEquals("Hello, world!", GreetingService.greet(null));
        assertEquals("Hello, world!", GreetingService.greet("  "));
        assertEquals("Hello, Maven!", GreetingService.greet(" Maven "));
    }

    @Test
    void loadsVersionProperties() throws IOException {
        try (InputStream in = GreetingService.class.getClassLoader()
                .getResourceAsStream("version.properties")) {
            assertNotNull(in);
            Properties p = new Properties();
            p.load(in);
            assertEquals("war-layout-demo", p.getProperty("app.name"));
            assertEquals("1.0.0", p.getProperty("app.version"));
        }
    }
}
~~~

Surefire chạy hai tests này không cần Tomcat. Chúng kiểm tra business logic và resource trên classpath, **không chứng minh HTTP mapping đã hoạt động**. File properties trong lab chỉ có giá trị ASCII, phù hợp `Properties.load(InputStream)`.

### 7.8. Build và kiểm tra WAR

Từ `war-layout-demo`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean package
~~~

Khi build thành công, log thường có thông tin:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là các **giá trị cần tìm**, không phải toàn bộ Maven stdout. WAR đầu ra:

~~~text
target/war-layout-demo-1.0.0.war
~~~

Kiểm tra:

~~~bash
jar tf target/war-layout-demo-1.0.0.war
~~~

Các entries cần có:

~~~text
index.html
assets/site.css
WEB-INF/classes/dev/example/web/GreetingService.class
WEB-INF/classes/dev/example/web/HelloServlet.class
WEB-INF/classes/version.properties
WEB-INF/lib/commons-lang3-3.17.0.jar
META-INF/MANIFEST.MF
~~~

Có thể xuất hiện thêm `META-INF/maven` và directory entries. **Không kỳ vọng**:

~~~text
WEB-INF/lib/jakarta.servlet-api-6.0.0.jar
WEB-INF/lib/junit-jupiter-5.11.4.jar
WEB-INF/classes/dev/example/web/GreetingServiceTest.class
WEB-INF/web.xml
~~~

Do Servlet API `provided`, JUnit `test`, test class nằm ở test output và lab dùng annotation thay descriptor. `StringUtils.class` nằm bên trong dependency JAR `WEB-INF/lib/commons-lang3-3.17.0.jar`, không phải loose class ở root WAR.

### 7.9. Deploy vào Tomcat 10.1

Cần một bản cài Tomcat 10.1 và Java 17. Trên Linux/macOS với `TOMCAT_HOME` hợp lệ:

~~~bash
cp target/war-layout-demo-1.0.0.war "$TOMCAT_HOME/webapps/war-layout-demo.war"
"$TOMCAT_HOME/bin/catalina.sh" run
~~~

Nếu Tomcat đã chạy, dùng quy trình deploy/redeploy hiện có, không mở instance thứ hai cùng port. Không làm trực tiếp trên production không có authorization.

Windows PowerShell (thay đường Tomcat bằng đường cài thật):

~~~powershell
$tomcat = 'C:\tools\apache-tomcat-10.1'
Copy-Item -LiteralPath 'target/war-layout-demo-1.0.0.war' -Destination (Join-Path $tomcat 'webapps\war-layout-demo.war')
& (Join-Path $tomcat 'bin\catalina.bat') run
~~~

Với Tomcat Host settings thông thường, WAR `war-layout-demo.war` dưới `webapps` được deploy ở context `/war-layout-demo`. Nếu container/proxy dùng context khác, URL cần thay.

Sau khi deployment thành công:

~~~bash
curl -fsS "http://localhost:8080/war-layout-demo/hello?name=Maven"
~~~

**HTTP body chính xác:**

~~~text
Hello, Maven!
~~~

Khi không có query parameter:

~~~bash
curl -fsS "http://localhost:8080/war-layout-demo/hello"
~~~

Body:

~~~text
Hello, world!
~~~

`PrintWriter.print` không thêm newline, nên terminal prompt có thể hiện ngay sau nội dung. Trang web tĩnh thường truy cập ở `http://localhost:8080/war-layout-demo/index.html`.

Build `BUILD SUCCESS` chưa chứng minh app đã deploy được trên container; đây là lý do cần HTTP smoke test riêng.

## 8. web.xml: cách đăng ký Servlet khác

Nếu muốn khai mapping bằng descriptor, tạo `src/main/webapp/WEB-INF/web.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <servlet>
        <servlet-name>hello</servlet-name>
        <servlet-class>dev.example.web.HelloServlet</servlet-class>
    </servlet>

    <servlet-mapping>
        <servlet-name>hello</servlet-name>
        <url-pattern>/hello</url-pattern>
    </servlet-mapping>
</web-app>
~~~

**Đây là phương án thay thế**, không phải file của lab gốc. Nếu chuyển sang descriptor mapping, hãy bỏ `@WebServlet` của class để không đăng ký cùng route hai lần. `metadata-complete="true"` trong descriptor có thể ảnh hưởng annotation scanning, nên nếu route 404 dù class đã đóng gói, kiểm tra registration mechanism.

Đừng sao chép descriptor `javax.servlet`/Java EE cũ và chỉ sửa một con số khi deploy Tomcat 10.1. Namespace/schema cũng phải phù hợp Jakarta Servlet.

## 9. Thêm webResources, filtering và excludes

### 9.1. webResources bổ sung nguồn

Giả sử có `src/main/branding/logo.svg` cần đưa tới `assets/branding/logo.svg` trong WAR:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-war-plugin</artifactId>
    <version>3.5.0</version>
    <configuration>
        <webResources>
            <resource>
                <directory>src/main/branding</directory>
                <targetPath>assets/branding</targetPath>
                <filtering>false</filtering>
                <includes>
                    <include>**/*.svg</include>
                </includes>
            </resource>
        </webResources>
    </configuration>
</plugin>
~~~

Đây là fragment **không nằm trong POM lab**; cần tạo file/folder thật mới có output. `webResources` không phải `build/resources`: nó đặt files tương đối với WAR root hoặc `targetPath` quy định.

Nếu `targetPath=WEB-INF/config`, file không tự được classloader tìm thấy như `WEB-INF/classes/config/...`. Muốn dùng cần `ServletContext.getResourceAsStream` hoặc API phù hợp.

### 9.2. Filtering

WAR Plugin có thể filter text của `webResources` với `filtering=true`, hoặc filter deployment descriptor bằng `filteringDeploymentDescriptors=true` (mặc định false). Ví dụ chỉ lọc text:

~~~xml
<webResources>
    <resource>
        <directory>src/main/web-templates</directory>
        <targetPath>WEB-INF/templates</targetPath>
        <filtering>true</filtering>
        <includes>
            <include>**/*.txt</include>
        </includes>
    </resource>
</webResources>
~~~

Text filtering là thay chuỗi, không parse mọi XML/YAML/JSON format. **Không filter binary** như PNG, PDF, ZIP, fonts hoặc keystores vì có thể hỏng bytes. Dùng root unfiltered hoặc `nonFilteredFileExtensions`. Tránh filter credentials vào release WAR.

### 9.3. WAR overlay

Một project có thể khai WAR dependency:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>shared-web-assets</artifactId>
    <version>1.0.0</version>
    <type>war</type>
</dependency>
~~~

WAR Plugin có thể dùng dependent WAR như **overlay**, trộn static files/JSP/descriptors vào WAR hiện tại. Thứ tự `overlays` và `dependentWarIncludes`/`dependentWarExcludes` ảnh hưởng khi nhiều nguồn có cùng path. Đoạn này chỉ là fragment khi artifact nguồn thật tồn tại, **không phải phần của lab runnable**. WAR overlay không tương đương dependency JAR được đóng nguyên dưới WEB-INF/lib.

## 10. war:exploded, war:inplace và tái sử dụng classes

| Goal | Công dụng |
| --- | --- |
| `war:war` | Build WAR archive |
| `war:exploded` | Assemble webapp vào exploded directory |
| `war:inplace` | Assemble ngay trong source webapp directory, có thể sửa source tree |

Sau build:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp org.apache.maven.plugins:maven-war-plugin:3.5.0:exploded
~~~

Có thể inspect `target/war-layout-demo-1.0.0` hoặc `webappDirectory` được cấu hình. `war:inplace` không nên dùng tùy tiện trong CI bởi rủi ro ghi file vào `src/main/webapp`.

`archiveClasses` có thể đưa compiled project classes vào một JAR trong WEB-INF/lib; `attachClasses` có thể sinh attached classes JAR. Khi business logic cần dùng lại ở nhiều modules, thường nên tách module `jar` độc lập rồi để WAR phụ thuộc JAR đó.

## 11. Spring Boot WAR: khác với WAR truyền thống

Ngữ cảnh cha của bài là **WAR và Spring Boot**, vì vậy cần biết:

- Plain Maven WAR Plugin tạo traditional WAR, không tự chứa embedded server launcher.
- Spring Boot **deployable WAR** thường dùng `<packaging>war</packaging>`, app extends `SpringBootServletInitializer` và override `configure`.
- Khi deploy external Tomcat, embedded `spring-boot-starter-tomcat` thường được khai `provided` để tránh xung đột container.
- Khi Spring Boot Maven Plugin **repackage** executable WAR, Boot loader/manifest có thể làm `java -jar` hoạt động; các provided libraries có thể nằm ở `WEB-INF/lib-provided`.

Đoạn Java sau chỉ minh họa **trong project Spring Boot đã có POM/dependencies thích hợp**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(DemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Không coi code Boot trên là standalone Java 17 nếu thiếu Spring Boot dependencies. Không thêm Boot plugin vào POM lab thuần Servlet một cách tùy tiện. Spring WebFlux trên Reactor Netty cũng không phải Servlet WAR deployment truyền thống theo mặc định.

## 12. Scopes, transitive dependencies và multi-module

| Maven scope | WAR thông thường |
| --- | --- |
| `compile` | Runtime dependency JAR vào WEB-INF/lib |
| `runtime` | Runtime dependency JAR vào WEB-INF/lib |
| `provided` | Compile/test, container chịu trách nhiệm cung cấp |
| `test` | Unit tests, không vào WAR production |
| `system` | Dựa filesystem cụ thể, tránh cho release tái lập |
| `import` trong dependencyManagement | BOM version management, không phải runtime JAR |

Transitive dependency `A → B` cũng quan trọng. Kiểm tra:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Nếu application cần B nhưng B bị exclude, WAR có thể build nhưng runtime gặp `NoClassDefFoundError`. Không copy toàn bộ `~/.m2` vào WEB-INF/lib; dễ gây test-library leak và trùng versions.

Với multi-module:

~~~text
workspace/
├── pom.xml            parent/aggregator
├── domain/pom.xml     packaging=jar
└── web/pom.xml        packaging=war
~~~

`web` nên khai `domain` làm dependency nếu dùng code domain. Maven reactor có thể build cả hai nhưng **`<modules>` không tự tạo dependency hay inheritance**. `<parent>` mới xác lập inheritance; dependencies cần khai theo GAV phù hợp.

Classloader conflict cũng có thể do server common library và `WEB-INF/lib` chứa phiên bản không tương thích. Đặc biệt Servlet APIs do container cung cấp; khi lỗi `NoSuchMethodError`/`ClassCastException`, kiểm tra JAR nguồn và classloader trước khi tự đổi scope.

## 13. Context path và URL mapping

Nếu file `war-layout-demo.war` được deploy trong Tomcat `webapps/` với Host settings mặc định, context thường là `/war-layout-demo`. Servlet mapping `@WebServlet("/hello")` là đường **bên trong context**.

~~~text
http://localhost:8080/war-layout-demo/hello?name=Maven
                      | context |    | route |
~~~

Nếu gọi `http://localhost:8080/hello` và được 404, không nhất thiết Servlet sai; có thể bạn bỏ context path. `ROOT.war`, context descriptor, virtual host, reverse proxy và custom deployment policy có thể thay context. Đừng sửa annotation thành `/war-layout-demo/hello` chỉ để ghép context, vì container vốn đã áp context path.

Static `index.html` ở WAR root thường ở `/<context>/index.html`. JSP dưới `WEB-INF/jsp` thường chỉ được forward nội bộ, không GET trực tiếp.

## 14. Lỗi phổ biến

**1. WAR Plugin yêu cầu web.xml:** Nếu app annotation-based, dùng `failOnMissingWebXml=false` và đúng Servlet API/plugin version. Không tạo descriptor XML sai để vượt qua build.

**2. `java -jar app.war` không chạy:** Traditional WAR cần container; executable Boot WAR đòi Boot repackage và launcher hợp lệ.

**3. HTTP 404:** Kiểm tra context path, `@WebServlet`, web.xml, annotation scanning, Tomcat deploy status và proxy.

**4. `NoClassDefFoundError: jakarta/servlet/http/HttpServlet`:** Có thể deploy sai Tomcat major/`javax` vs `jakarta`; kiểm tra API compatibility.

**5. `NoClassDefFoundError: org/apache/commons/lang3/StringUtils`:** Thiếu Commons Lang trong WEB-INF/lib hoặc dependency scope/exclusion sai.

**6. HTTP 500:** Unit test không mở Tomcat; đọc Servlet stack trace ở container, library conflict, config và initialization.

**7. Static assets 404:** Xem `warSourceDirectory`, `warSourceExcludes`, `packagingExcludes`, WAR entries và URL context.

**8. JUnit/test fixtures lọt WAR:** Custom webResources/copy task có thể mang file từ `src/test`/`target/test-classes` vào archive.

**9. Servlet API JAR vào WEB-INF/lib:** Scope cần là provided khi Tomcat cung cấp; kiểm tra overlays/custom packaging.

**10. Descriptor schema cũ:** Java EE `javax` và Jakarta Servlet `jakarta` không tương đương; migrate namespace/framework.

**11. WAR có secrets:** Không bảo vệ được bằng việc đặt dưới WEB-INF. Dừng phát hành, xử lý rò rỉ/rotate credentials theo quy trình.

**12. WAR chạy bản cũ:** Xác minh WAR hash/name/context, Tomcat instance, redeploy status; không xóa production state tùy tiện.

**13. Không có WEB-INF/lib:** Có thể đúng nếu mọi dependency đều provided/test. Riêng lab có Commons Lang compile nên phải có JAR này.

**14. Build khác CI:** Pin Maven Wrapper, JDK/plugins và profiles; xem effective POM, dependency tree và WAR thật thay vì chỉ dựa vào BUILD SUCCESS.

## 15. Workflow debug có thể tái lập

1. `mvn -version`, `java -version` và xác nhận Tomcat 10.1/Jakarta Servlet 6.0.
2. Xuất effective POM của đúng WAR module:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

3. Kiểm tra packaging, WAR Plugin, warSourceDirectory, webResources, scopes, exclusions, active profiles.
4. Chạy `dependency:tree` để biết runtime dependency graph.
5. `mvn -B -ntp clean verify` trên build sạch.
6. `jar tf target/war-layout-demo-1.0.0.war` và đối chiếu WEB-INF/classes/lib/web root.
7. Deploy WAR cuối lên Tomcat local/staging tương thích.
8. `curl` endpoint thật và kiểm tra status/body; xem Tomcat logs khi 404/500.
9. Trên CI, làm smoke test chính WAR artifact sau build, không chỉ test từ Maven classpath.
10. Khi điều chỉnh, làm lại WAR/package và so kết quả; tránh dựa vào exploded output cũ.

## 16. Checklist trước khi phát hành

- [ ] `packaging=war` và Maven WAR Plugin version phù hợp.
- [ ] Java/classes, resources, static web files đặt đúng source roots.
- [ ] WEB-INF/classes chứa compiled classes và classpath resources.
- [ ] WEB-INF/lib chứa runtime JARs đủ, không có JUnit/Servlet provided không cần.
- [ ] Servlet registration qua annotations/web.xml/framework nhất quán.
- [ ] `failOnMissingWebXml` đúng với thiết kế app.
- [ ] Tomcat/Java/Servlet API namespaces tương thích.
- [ ] Context path, Servlet URLs và static asset URLs đúng.
- [ ] webResources/overlays/exclusions không làm mất file thiết yếu.
- [ ] Không filter binary hoặc ghi secrets vào WAR.
- [ ] `mvn clean verify` thành công và `jar tf` đã đối chiếu archive.
- [ ] HTTP smoke test đã chạy trên container tương thích.
- [ ] Không nhầm WAR truyền thống với Spring Boot executable WAR.
- [ ] Có policies dependencies/license/security/reproducibility khi phát hành.

## 17. Câu hỏi ôn tập

**A.** `src/main/java/dev/example/web/HelloServlet.java` vào đâu trong WAR? **Đáp án:** `WEB-INF/classes/dev/example/web/HelloServlet.class` sau compile.

**B.** `src/main/resources/version.properties` đi đâu? **Đáp án:** `WEB-INF/classes/version.properties`.

**C.** `src/main/webapp/index.html` đi đâu? **Đáp án:** web root của WAR.

**D.** Vì sao Servlet API được khai provided? **Đáp án:** Tomcat cung cấp nó ở runtime, nhưng project cần API để compile.

**E.** Không có web.xml có thể chạy Servlet không? **Đáp án:** Có nếu annotation/programmatic registration hợp lệ và plugin không yêu cầu descriptor.

**F.** `mvn package` trên project WAR gọi goal nào? **Đáp án:** `war:war` theo lifecycle bindings thông thường.

**G.** Tomcat 10.1 có tự hỗ trợ `javax.servlet` không? **Đáp án:** Không như Tomcat 9; cần Jakarta Servlet-compatible code và dependencies.

**H.** `warSourceExcludes` có loại tất cả dependency JAR trong WEB-INF/lib không? **Đáp án:** Không; nó chỉ lọc source webapp.

**I.** Unit tests PASS đã chứng minh HTTP /hello chạy? **Đáp án:** Chưa; cần WAR deploy và HTTP smoke test.

**J.** Spring Boot WAR có `WEB-INF/lib-provided` là do đâu? **Đáp án:** Boot executable repackage/loader; không phải WAR Plugin thuần tự tạo.

**K.** Có nên đặt secret trong WEB-INF/classes? **Đáp án:** Không; người có WAR có thể giải nén.

**L.** WAR overlay khác JAR dependency thế nào? **Đáp án:** Dependent WAR có thể được merge thành webapp files; runtime JAR được đặt nguyên dưới WEB-INF/lib.

## 18. Tài liệu chính thức

1. [Maven WAR Plugin — Introduction](https://maven.apache.org/plugins/maven-war-plugin/) — tổng quan.
2. [Maven WAR Plugin 3.5.0 — war:war](https://maven.apache.org/plugins-archives/maven-war-plugin-3.5.0/war-mojo.html) — tham số và phase package.
3. [WAR Plugin — Usage](https://maven.apache.org/plugins/maven-war-plugin/usage.html) — war/exploded/inplace.
4. [WAR Plugin — Web Resources](https://maven.apache.org/components/plugins-archives/maven-war-plugin-3.5.0/examples/adding-filtering-webresources.html) — resource filtering và targetPath.
5. [WAR Plugin — Overlays](https://maven.apache.org/plugins-archives/maven-war-plugin-3.5.0/overlays.html) — WAR dependency merge.
6. [WAR Plugin — FAQ](https://maven.apache.org/components/plugins-archives/maven-war-plugin-3.5.0/faq.html) — web.xml, classes packaging.
7. [Maven Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — lifecycle bindings.
8. [Maven Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html) — src/main/webapp.
9. [Jakarta Servlet 6.0](https://jakarta.ee/specifications/servlet/6.0/) — API/schema.
10. [Tomcat Version Matrix](https://tomcat.apache.org/whichversion) — JDK/Servlet versions.
11. [Tomcat Migration 10.1](https://tomcat.apache.org/migration-10.1.html) — Jakarta API compatibility.
12. [Tomcat Manager Deployment](https://tomcat.apache.org/tomcat-10.1-doc/html-manager-howto.html) — WAR naming/context.
13. [Spring Boot Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html) — initializer/provided.
14. [Spring Boot Maven Plugin Packaging](https://docs.spring.io/spring-boot/maven-plugin/packaging.html) — executable WAR/lib-provided.
