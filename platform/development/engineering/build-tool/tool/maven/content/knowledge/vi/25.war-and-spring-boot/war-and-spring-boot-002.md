# Phụ thuộc `provided` khi môi trường Servlet cung cấp thư viện — Maven WAR và Spring Boot

## 1. Vấn đề: biên dịch cần Servlet API nhưng WAR không nên mang bản API riêng

Một ứng dụng Java web dùng `HttpServlet`, `HttpServletRequest`, `HttpServletResponse` hoặc `@WebServlet` phải có **Servlet API** trên classpath khi biên dịch. Nhưng khi triển khai WAR lên một **Servlet container** như Apache Tomcat, container đã cung cấp Servlet API và implementation tương ứng ở runtime.

Vì thế một dependency kiểu:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

có ý nghĩa: **Maven được dùng các class này để compile và test, nhưng môi trường triển khai chịu trách nhiệm cung cấp chúng khi ứng dụng chạy**.

Đây không phải lệnh Maven “tự tìm thư viện trong Tomcat”, cũng không phải việc tự copy file từ thư mục cài Tomcat vào build. Maven vẫn tải dependency API từ repository cho compile/test; từ khóa `provided` chỉ quyết định **phạm vi classpath và dependency propagation/packaging**.

Bài giải thích `provided` trong WAR chuẩn và trong Spring Boot WAR, cách chọn đúng API cho container, cách kiểm tra `WEB-INF/lib`, ví dụ Java 17 có thể build/deploy, và lỗi class loading thường gặp.

### Kết quả cần đạt

Sau bài, bạn có thể:

1. Phân biệt `compile`, `provided`, `runtime` và `test`.
2. Giải thích ai chịu trách nhiệm cung cấp Servlet API ở từng bước build/test/deploy.
3. Chọn `jakarta.servlet-api` phù hợp Tomcat 10.1, không nhầm với `javax.servlet`.
4. Tạo WAR chuẩn từ `packaging=war`, `@WebServlet` và Maven WAR Plugin.
5. Chứng minh API `provided` không xuất hiện như một JAR trong `WEB-INF/lib`, nhưng thư viện ứng dụng `compile` có thể xuất hiện.
6. Triển khai WAR vào Tomcat ngoài và kiểm tra HTTP endpoint.
7. Phân biệt WAR thường với **Spring Boot executable WAR**, trong đó `WEB-INF/lib-provided` có vai trò riêng.
8. Nhận biết `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, lỗi `javax`/`jakarta` và container conflict.
9. Chọn cấu hình có thể tái tạo trong CI mà không mang các API/implementation của container vào WAR sai cách.

## 2. Scope `provided` thực sự làm gì?

Trong Maven, scope ảnh hưởng **classpath của project hiện tại** và cách dependency được truyền tiếp cho project phụ thuộc.

| Scope | Compile classpath | Test classpath | Runtime classpath Maven | Truyền tiếp cho consumer | Ví dụ |
| --- | --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | Có | Library ứng dụng cần dùng lúc chạy |
| `provided` | Có | Có | Không | Không | Servlet API do container cung cấp |
| `runtime` | Không | Có | Có | Có | JDBC driver khi code chỉ dùng JDBC API |
| `test` | Không | Có | Không | Không | JUnit, Mockito |

Ở đây runtime classpath là **classpath Maven phân giải cho project**, không bao gồm những class do một external server bổ sung khi deploy.

Ví dụ:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Tác động:

- **Compile:** `javac` tìm thấy `jakarta.servlet.http.HttpServlet` và các annotation.
- **Test:** unit/integration test compilation có thể tham chiếu Servlet API.
- **Runtime dependency graph do Maven tạo:** API này không được đưa vào runtime classpath theo scope `provided`.
- **WAR chuẩn:** Servlet API JAR không được đưa vào `WEB-INF/lib` chỉ vì dependency đó được khai báo là `provided`.
- **Truyền dependency:** một project khác phụ thuộc vào artifact của bạn không tự nhận `provided` như một transitive dependency thông thường.

Lưu ý: `provided` là một **cam kết với môi trường runtime**. Nếu môi trường không cung cấp API tương thích, kết quả có thể là lỗi runtime. Scope không tự cài Servlet API lên máy chủ.

### “Provided” không có nghĩa “chỉ để compile”

Nhiều tài liệu đơn giản hóa thành “compile-only”. Nhưng Maven `provided` vẫn có trong **test classpath** của project. Đây là lý do test code có thể dùng Servlet API, và cũng là lý do test thường không phát hiện việc **external container thực tế thiếu hoặc không tương thích API**. Để kiểm tra hợp đồng deploy, phải dùng integration/deployment smoke test trên container mục tiêu.

## 3. `provided` là hợp đồng giữa build và nơi chạy

Có ba ranh giới khác nhau:

~~~text
Developer / CI Maven build
  |
  +-- Maven repository tải jakarta.servlet-api JAR (provided)
  +-- Compiler dùng các servlet types để tạo .class
  +-- Test classpath có Servlet API
  +-- WAR Plugin tạo web archive
  |
  v
WAR chuẩn
  |
  +-- WEB-INF/classes/... application classes
  +-- WEB-INF/lib/... application libraries cần runtime
  +-- KHÔNG nhúng jakarta.servlet-api JAR do scope provided
  |
  v
External Tomcat 10.1
  |
  +-- Container cung cấp Jakarta Servlet 6.0 API và implementation
  +-- Container quản lý request/response, class loading, servlet lifecycle
  +-- Application dùng runtime API từ container
~~~

Maven không xác minh có một Tomcat đang chạy ở CI chỉ vì POM ghi scope `provided`. Mỗi môi trường cần kiểm tra **hợp đồng thực tế**:

- Có Servlet container tương thích không?
- Servlet API namespace là `javax.servlet` hay `jakarta.servlet`?
- Container triển khai spec version nào?
- Java runtime của container có chạy được bytecode từ project không?
- Có class/interface nào khác bị container override không?
- Có chính sách class loading và package protection riêng không?
- Nếu chạy WAR bằng Java launcher thay vì container ngoài, liệu archive có executable launcher/implementation không?

**Đừng dùng scope để thay thế kiểm tra compatibility matrix và deployment test.**

## 4. `war` packaging và các vị trí trong WAR

Với:

~~~xml
<packaging>war</packaging>
~~~

Maven WAR Plugin thường chạy goal `war:war` ở phase `package`. WAR là một ZIP archive theo cấu trúc ứng dụng web Java.

Một WAR chuẩn có thể trông như:

~~~text
servlet-provided-demo-1.0.0.war
├── index.html
├── META-INF/
│   └── MANIFEST.MF
└── WEB-INF/
    ├── classes/
    │   └── com/example/web/
    │       ├── HelloServlet.class
    │       └── GreetingService.class
    └── lib/
        └── commons-lang3-3.17.0.jar
~~~

Giải thích:

- `src/main/java` biên dịch thành class dưới `WEB-INF/classes`.
- `src/main/resources` thường vào `WEB-INF/classes`.
- `src/main/webapp` đặt static assets, JSP và deployment descriptors vào webapp root theo mapping của WAR Plugin.
- `WEB-INF/lib` chứa những JAR của web application được WAR packaging chọn để đóng gói.
- `jakarta.servlet-api-6.0.0.jar` **không cần nằm trong `WEB-INF/lib`** của ví dụ vì được khai báo `provided`.
- Container ngoài đưa các Servlet API class/implementation vào class loader hierarchy theo cách container quản lý.

**Không phải mọi `provided` dependency đều là Servlet API.** Chỉ đánh dấu `provided` khi môi trường đích thực sự cam kết cung cấp một bản API/implementation tương thích. Các thư viện như Commons Lang, Jackson, JDBC drivers hay application utilities **không tự được Tomcat cung cấp theo hợp đồng Servlet**.

### Cần phân biệt những thư mục khác nhau

`WEB-INF/classes` thuộc **application classes**. `WEB-INF/lib` chứa **application libraries**. Server runtime thường có những thư mục `lib` riêng của Tomcat (ví dụ `$CATALINA_BASE/lib` hay `$CATALINA_HOME/lib`) nhưng **không phải là `WEB-INF/lib` của WAR**.

Đừng copy `servlet-api.jar` thủ công từ Tomcat vào `WEB-INF/lib` để “cho chắc”. Điều đó có thể gây trùng API, khó quản lý version hoặc vi phạm hướng dẫn triển khai của container.

## 5. Servlet API phải khớp container: `javax` và `jakarta`

Đây là một trong những lỗi lớn nhất khi chuyển project Servlet hoặc Spring Boot từ hệ Java EE sang Jakarta EE.

| Container | Servlet specification | Namespace ứng dụng cần dùng | Yêu cầu Java tối thiểu của dòng Tomcat |
| --- | --- | --- | --- |
| **Tomcat 9.0.x** | Servlet 4.0 (Java EE 8) | `javax.servlet.*` | Java 8+ |
| **Tomcat 10.1.x** | Jakarta Servlet 6.0 | `jakarta.servlet.*` | Java 11+ |
| **Tomcat 11.0.x** | Jakarta Servlet 6.1 | `jakarta.servlet.*` | Java 17+ |

Bảng thể hiện **compatibility family**, không phải lời hứa tất cả tổ hợp framework/Tomcat/JDK đều được hỗ trợ. Khi triển khai cần kiểm tra bản release chính xác, các bản vá bảo mật và matrix của framework đang sử dụng.

### 5.1. Ví dụ theo Tomcat 10.1

Dependency compile/test:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

Java source:

~~~java
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
~~~

Maven có API 6.0, compile ra class dùng các kiểu `jakarta.servlet.*`; Tomcat 10.1 hỗ trợ Servlet 6.0 nên khớp ví dụ.

### 5.2. Ví dụ legacy Tomcat 9

Một ứng dụng legacy có thể dùng:

~~~java
import javax.servlet.http.HttpServlet;
~~~

và một `javax.servlet-api` bản Servlet 4.0 tương ứng.

**Không đổi mỗi groupId/artifactId mà giữ nguyên `javax.servlet` trong Java source**. `javax.servlet.http.HttpServlet` và `jakarta.servlet.http.HttpServlet` là **hai tên class khác nhau**, không tương thích nhị phân chỉ vì chức năng gần giống. Cần migrate imports/framework, phụ thuộc, web.xml/schema và các servlet components.

### 5.3. Không ép API mới vào container cũ

Nếu compile với Servlet 6.1 API rồi deploy vào Tomcat 10.1 (Servlet 6.0), source có thể gọi phương thức chưa tồn tại ở runtime và gây `NoSuchMethodError` hoặc lỗi linkage khác.

**Quy tắc:** chọn API version mà **container mục tiêu hỗ trợ**, không chọn `jakarta.servlet-api` mới nhất một cách máy móc. Nếu deploy nhiều loại container, xác định mức API thấp nhất cần hỗ trợ và test trên từng đích.

## 6. Ví dụ Maven WAR hoàn chỉnh — Java 17 + Tomcat 10.1

Đây là project Java 17 dùng Servlet API với scope `provided`, đồng thời dùng Commons Lang như **application dependency bình thường**. Bằng cách đó ta kiểm tra được hai loại classpath:

- **Servlet API**: có ở compile/test, do Tomcat cung cấp khi runtime.
- **Commons Lang**: được project sử dụng lúc runtime, do WAR đóng gói trong `WEB-INF/lib`.

Ví dụ cần JDK 17+, Maven 3.9+ và để thử endpoint HTTP cần một Tomcat 10.1 ngoài đang chạy. Project build/test **không cần** một Tomcat ngoài; bước deploy và HTTP smoke test mới cần.

### 6.1. Cấu trúc project

~~~text
servlet-provided-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/web/
    │   │   ├── GreetingService.java
    │   │   └── HelloServlet.java
    │   └── webapp/
    │       └── index.html
    └── test/
        └── java/com/example/web/
            └── GreetingServiceTest.java
~~~

`index.html` có mặt để minh họa static web content, không bắt buộc để class `@WebServlet` hoạt động trong một container hỗ trợ annotation scanning.

### 6.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>servlet-provided-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

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
</project>
~~~

Các điểm quan trọng:

1. `packaging=war` làm Maven dùng WAR Plugin ở phase `package`, không cần thêm một `war:war` execution mới gây chạy trùng.
2. `jakarta.servlet-api:6.0.0` được khai báo **`provided`** vì Tomcat 10.1 đã cung cấp Servlet 6.0 khi deploy.
3. Commons Lang 3.17.0 không khai báo scope, nên scope là `compile`; code ứng dụng dùng nó lúc chạy.
4. JUnit Jupiter 5.11.4 có scope `test` và không được đóng gói vào WAR runtime.
5. `maven.compiler.release=17` đảm bảo Java compile release target.
6. Maven WAR Plugin 3.5.0 hỗ trợ WAR không có `web.xml`; `<failOnMissingWebXml>false</failOnMissingWebXml>` thể hiện ý định minh bạch.
7. Demo dùng `@WebServlet` để container tự đăng ký servlet khi annotation scanning được bật theo quy tắc Servlet; **không cần thêm `web.xml` trong cấu hình triển khai mặc định**.
8. Đã pin các plugin và library versions minh họa; không khẳng định đây là các bản mới nhất ở thời điểm sử dụng.
9. Không có embedded Tomcat dependency trong project WAR chuẩn, vì ứng dụng chạy trong **external Tomcat**.

### 6.3. GreetingService.java

Tạo `src/main/java/com/example/web/GreetingService.java`:

~~~java
package com.example.web;

import org.apache.commons.lang3.StringUtils;

public final class GreetingService {

    private GreetingService() {
    }

    public static String message() {
        return "Hello from external Tomcat: "
                + StringUtils.upperCase("maven");
    }
}
~~~

Class này thuần Java, dùng Commons Lang để biến `maven` thành `MAVEN`. Library đó cần có ở runtime. Nếu không có Commons Lang trên Tomcat webapp classpath, ứng dụng sẽ lỗi khi gọi `StringUtils.upperCase`.

### 6.4. HelloServlet.java

Tạo `src/main/java/com/example/web/HelloServlet.java`:

~~~java
package com.example.web;

import java.io.IOException;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet(name = "helloServlet", urlPatterns = "/hello")
public final class HelloServlet extends HttpServlet {

    private static final long serialVersionUID = 1L;

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().println(GreetingService.message());
    }
}
~~~

Giải thích:

- `HelloServlet` kế thừa `jakarta.servlet.http.HttpServlet`.
- `@WebServlet(..., urlPatterns="/hello")` khai báo mapping servlet theo annotation.
- Khi nhận HTTP GET, **Tomcat gọi `doGet`**; source tự nó không khởi động web server.
- `HttpServletResponse` do **container cung cấp** trong request lifecycle.
- `response.setContentType` đặt content type và encoding.
- `println` thêm newline sau thông điệp.
- `GreetingService` dùng Commons Lang, là dependency phải có trong WAR.
- `serialVersionUID` là một khai báo Java thông thường; không thay đổi dependency scope.

Nếu container cấu hình tắt annotation scanning hoặc dùng deployment descriptor đánh dấu metadata-complete, `@WebServlet` có thể không được phát hiện. Khi đó phải kiểm tra chính sách scanning hoặc khai báo mapping phù hợp trong `web.xml`; không nên mặc định đổi scope Servlet API để sửa.

### 6.5. index.html

Tạo `src/main/webapp/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Servlet Provided Demo</title>
</head>
<body>
    <h1>Servlet Provided Demo</h1>
    <p>Open <a href="hello">the hello servlet</a>.</p>
</body>
</html>
~~~

File này sẽ được WAR Plugin đóng gói ở webapp root. Đường dẫn `hello` tương đối với context của application; với tên WAR mặc định, URL có thể là `/servlet-provided-demo-1.0.0/hello` nếu không đổi tên WAR khi deploy.

### 6.6. Unit test GreetingServiceTest.java

Tạo `src/test/java/com/example/web/GreetingServiceTest.java`:

~~~java
package com.example.web;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void buildsGreeting() {
        assertEquals(
                "Hello from external Tomcat: MAVEN",
                GreetingService.message());
    }
}
~~~

**Unit test này chưa khởi động Tomcat**. Nó xác nhận một dependency application thông thường hoạt động trong Maven test classpath. Việc Servlet API có mặt trong test classpath không chứng minh WAR đã deploy tốt; cần thử deploy/HTTP riêng.

### 6.7. Build và kiểm tra WAR

Tại thư mục project:

~~~bash
mvn -version
mvn -B clean verify
~~~

Khi các dependencies resolve được, Maven compile source, chạy 1 JUnit test và đóng gói WAR trong phase `package`. File dự kiến:

~~~text
target/servlet-provided-demo-1.0.0.war
~~~

Kiểm tra archive bằng Java `jar` tool:

~~~bash
jar tf target/servlet-provided-demo-1.0.0.war
~~~

Trong danh sách phải có các entries quan trọng:

~~~text
index.html
WEB-INF/classes/com/example/web/HelloServlet.class
WEB-INF/classes/com/example/web/GreetingService.class
WEB-INF/lib/commons-lang3-3.17.0.jar
~~~

Không được có một entry JAR như:

~~~text
WEB-INF/lib/jakarta.servlet-api-6.0.0.jar
~~~

Dòng trên là **entry không mong muốn** cho WAR chuẩn đang nhắm tới Tomcat 10.1, không phải file thực tế phải có. Ngoài những entries này, WAR có thể có metadata, manifest và các file bổ sung; bảng chỉ mô tả những điểm cần quan sát.

Lưu ý: WAR có thể chứa `META-INF/maven/.../pom.xml` nêu tên dependency trong metadata. Vì thế **chỉ grep từ `jakarta.servlet` ở mọi vị trí archive không đủ**; hãy kiểm tra **đường dẫn JAR trong `WEB-INF/lib`**.

### 6.8. Deploy lên external Tomcat 10.1

Bạn cần một Tomcat 10.1 đã cài và chạy trên JDK thích hợp. Ví dụ ở đây giả định:

- Tomcat nghe HTTP tại `localhost:8080`.
- Servlet annotation scanning hoạt động theo cấu hình mặc định.
- User có quyền deploy ứng dụng lên Tomcat.
- Không có WAR cũ hoặc custom context config xung đột.
- Không có reverse proxy đang thay đổi context path.

Một cách triển khai ở môi trường local/sandbox là copy file WAR:

~~~text
target/servlet-provided-demo-1.0.0.war
    ->
$CATALINA_BASE/webapps/servlet-provided-demo.war
~~~

Đây là **mô tả vị trí**, không phải một shell command portable: `CATALINA_BASE` phải được thay bằng đường dẫn Tomcat instance thật. Không dùng cách copy thủ công này nếu môi trường deploy được quản lý bởi pipeline/manager và có policy riêng.

Nếu Tomcat tự deploy WAR từ `webapps/servlet-provided-demo.war`, context path mặc định thường là:

~~~text
/servlet-provided-demo
~~~

Từ terminal có `curl`:

~~~bash
curl -fsS http://localhost:8080/servlet-provided-demo/hello
~~~

**HTTP response body mong đợi**, với newline cuối do `println`:

~~~text
Hello from external Tomcat: MAVEN
~~~

Đây là response body trả từ Servlet, **không phải stdout của `mvn`**. Khi Tomcat dùng port/context tùy chỉnh, hãy thay URL tương ứng. `-f` khiến curl báo lỗi với các HTTP status lỗi, tránh nhầm trang 404 thành kết quả pass.

Nếu không có external Tomcat, các bước `mvn clean verify` và `jar tf` vẫn giúp kiểm tra build/packaging; bước HTTP deploy chưa thể xác nhận. Không tuyên bố “end-to-end deployed PASS” khi chưa thực sự chạy container và gửi request.

## 7. Cách xem classpath theo từng phase để kiểm chứng `provided`

Một checklist phân tách như sau:

| Ngữ cảnh | Có Servlet API JAR theo dependency `provided`? | Có Commons Lang? |
| --- | --- | --- |
| Maven compile | Có | Có |
| Maven test | Có | Có |
| Maven runtime graph của WAR project | Không | Có |
| WAR chuẩn trong `WEB-INF/lib` | Không | Có |
| External Tomcat 10.1 khi ứng dụng chạy | Container cung cấp Servlet API | WAR cung cấp Commons Lang |

Dùng:

~~~bash
mvn dependency:tree
~~~

Trong dependency tree sẽ thấy direct dependency với scope `provided`, ví dụ dòng ý nghĩa:

~~~text
jakarta.servlet:jakarta.servlet-api:jar:6.0.0:provided
org.apache.commons:commons-lang3:jar:3.17.0:compile
~~~

Đây là **các nhãn scope minh họa được trích**, không phải toàn bộ stdout dependency tree.

`dependency:tree` giúp xác định scope Maven đã resolve, nhưng không phải bằng chứng duy nhất về nội dung WAR. Cần **kiểm tra archive thật** bằng `jar tf` và xác nhận `WEB-INF/lib`.

### Không dùng `provided` để “tối ưu kích thước” một cách ngẫu nhiên

Giả sử đổi Commons Lang từ compile sang provided:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
    <scope>provided</scope>
</dependency>
~~~

WAR chuẩn có thể không chứa Commons Lang JAR. Nếu Tomcat không được cấu hình cung cấp thư viện đó và code vẫn gọi `StringUtils`, Servlet có thể lỗi runtime. **Tomcat không cam kết cung cấp mọi thư viện ứng dụng**; `provided` chỉ đúng khi runtime thực sự cấp đúng dependency.

Trong project thử nghiệm, không sửa trực tiếp WAR production để thử đổi scope; hãy dùng bản sao/branch và kiểm tra dependency tree, WAR contents và HTTP test.

## 8. Khi nào dùng `provided`, khi nào dùng `compile`?

Một nguyên tắc đánh giá dependency:

1. Code có tham chiếu type này lúc compile không?
2. Type có cần tồn tại khi ứng dụng chạy không?
3. Container/JDK có **chính thức** cung cấp nó lúc chạy không?
4. Nếu có, phiên bản/namespace nào được hỗ trợ?
5. Dependency này có phải API spec, implementation, hay library business logic?
6. Có phải deploy lên một runtime khác không cung cấp thư viện ấy?
7. Các tests có cần một implementation khác/API mock không?
8. Thư viện có được container load ở classloader khác và gây version conflict không?

| Dependency | Scope thường hợp lý cho external Servlet WAR | Giải thích |
| --- | --- | --- |
| `jakarta.servlet-api` | `provided` | Container triển khai Servlet API |
| `jakarta.servlet.jsp-api` | `provided` khi container cung cấp JSP API | Chọn API phù hợp container và có dùng JSP |
| Jakarta WebSocket API | Có thể `provided` nếu container cam kết WebSocket | Không giả định mọi server hỗ trợ cùng spec |
| Commons Lang | `compile` | App cần lúc chạy, container không cam kết cung cấp |
| JDBC driver | `runtime` hoặc `provided` tùy runtime data source policy | Nếu server pool quản lý driver ở common lib, cần hợp đồng rõ |
| JUnit/Mockito | `test` | Chỉ phục vụ tests |
| Tomcat implementation | Không nhúng vào WAR chuẩn chạy external Tomcat | Container ngoài đã là implementation |
| Logging implementation | Tùy ứng dụng/container và framework | Tránh nhiều bindings/providers gây xung đột |

**Scope không thay thế kiến trúc runtime**. Ví dụ một ứng dụng Java thuần `main` không chạy trong container sẽ không tự có Servlet API chỉ vì Maven build `provided` thành công.

## 9. Lỗi trùng Servlet API: vì sao tránh đóng gói `servlet-api.jar`?

Trong môi trường container, các loại class có thể đến từ:

~~~text
Container class loader
  - Servlet API/spec implementation do Tomcat quản lý
  - Container internals
        |
Web application class loader
  - WEB-INF/classes
  - WEB-INF/lib/*.jar
~~~

Classloader behavior có quy tắc đặc biệt cho một số Java/Servlet API packages; không nên diễn giải đơn giản “luôn parent-first” hay “luôn child-first” cho mọi class. Tomcat có cơ chế class loading và delegation riêng.

Nếu WAR tự mang `jakarta.servlet-api` hoặc một bản Tomcat embedded implementation khác, vấn đề có thể là:

- Class duplicate/split giữa container và webapp.
- API version mới hơn container không hỗ trợ.
- `NoSuchMethodError` hoặc lỗi linkage khi gọi method khác phiên bản.
- Container-specific startup/scanning failures.
- Deploy thành công nhưng endpoint gặp lỗi khi request đến.
- Xung đột resource/JAR metadata.
- Lỗi trong JSP/WebSocket/EL integrations.

Vì vậy `provided` là một **cách thể hiện ownership của API**: container sở hữu runtime API, WAR sở hữu application code và các libraries còn lại.

### Chỉ đánh dấu provided không thể “fix” mọi conflict

Nếu `mvn dependency:tree` thấy một dependency khác kéo vào một bản Servlet API theo transitive scope compile hoặc một library tự đóng gói classes `jakarta.servlet.*`, việc direct dependency provided chưa chắc giải quyết tất cả. Hãy xem resolved dependency graph và **WAR contents thật**.

Nếu gặp nhiều dependency paths tới cùng class, xem dependencyManagement, exclusions, container compatibility và runtime classloading. Tránh copy/paste excludes hàng loạt khi chưa tìm root cause.

## 10. `provided` không tự test container compatibility

Unit test của phần 6 chạy bằng Maven test classpath, có cả Servlet API và Commons Lang. Nhưng test không thực sự tạo instance/dispatch servlet request như Tomcat.

Một test chất lượng nên có nhiều lớp:

1. **Unit tests** kiểm tra business logic (không cần server).
2. **WAR packaging check** xác nhận Servlet API JAR không nằm ở `WEB-INF/lib`.
3. **Deployment smoke test** triển khai WAR vào Tomcat thật, request `/hello`.
4. **Integration tests** kiểm tra filters, sessions, security, JSP/EL, database, WebSocket hoặc tính năng được ứng dụng sử dụng.
5. **Compatibility tests** trên đúng container version/JDK mà production sử dụng.
6. **Security checks** về phiên bản container, app libraries, cấu hình TLS/headers và quyền của server.

Không đánh đồng `mvn verify` trên project mẫu với “WAR đã chạy ở Tomcat”. Phần mẫu chỉ có JUnit unit test; deployment smoke test là một bước riêng ngoài Maven nếu chưa tích hợp Failsafe/CI.

### Cách tích hợp smoke test vào pipeline

Có thể dùng Maven Failsafe Plugin cho test `*IT` ở `integration-test`/`verify`, đồng thời một hệ thống CI hoặc plugin được kiểm soát quản lý vòng đời Tomcat test container. Nếu chính Maven khởi động container ở `pre-integration-test`, cần cleanup ở `post-integration-test` và cơ chế dự phòng khi build bị hủy.

**Tránh gọi chỉ `mvn integration-test` làm release gate** nếu Failsafe verification chưa chạy; `mvn verify` là lệnh thích hợp hơn khi suite đã cấu hình đủ.

## 11. Trường hợp đặc biệt: Spring Boot có embedded Servlet container

Spring Boot `spring-boot-starter-web` thường kéo theo `spring-boot-starter-tomcat`, là **embedded Tomcat** khi chạy ứng dụng theo dạng executable JAR.

Ví dụ executable JAR:

~~~text
spring-boot-starter-web
   |
   +-- spring-webmvc
   +-- spring-web
   +-- spring-boot-starter-tomcat
           |
           +-- Tomcat embedded libraries
~~~

Khi chạy:

~~~bash
java -jar target/app.jar
~~~

Spring Boot launcher khởi động application và embedded servlet container bên trong runtime process. **Không có một external Tomcat nào cấp Servlet API** theo mô hình này.

Nếu chuyển ứng dụng thành **WAR deploy lên external Tomcat**, cần thay đổi packaging và scope để container bên ngoài đảm nhiệm vai trò web server. Tài liệu Spring Boot hướng dẫn:

1. Thay `packaging` từ `jar` sang `war`.
2. Application class mở rộng `SpringBootServletInitializer`, override `configure` để external Servlet container có thể bootstrap Spring app.
3. Đánh dấu dependency `spring-boot-starter-tomcat` là **`provided`**.
4. Giữ Spring web/application libraries trong WAR.
5. Dùng Spring Boot Maven Plugin nếu muốn executable WAR hỗ trợ cả `java -jar` lẫn external deployment.

### Ví dụ mảnh dependency Spring Boot

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

Đây là **mảnh POM**, cần Spring Boot dependency management/parent và phần build thích hợp. `spring-boot-starter-web` có thể đưa starter Tomcat vào graph; direct declaration của Tomcat starter với scope `provided` xác định ý định cung cấp container ở runtime external.

**Không đặt tất cả `spring-boot-starter-web` thành provided**. Web framework và application libraries vẫn cần trong WAR; chỉ phần embedded container được external container thay thế mới nên được đánh dấu provided theo tài liệu Spring Boot.

## 12. Một ngoại lệ rất quan trọng: `WEB-INF/lib-provided` trong Spring Boot executable WAR

WAR chuẩn từ Maven WAR Plugin và executable WAR được **Spring Boot Maven Plugin repackage** không giống nhau.

### 12.1. WAR chuẩn

~~~text
regular-app.war
  WEB-INF/classes/...
  WEB-INF/lib/application-lib.jar
  (không có jakarta.servlet-api.jar do provided)
~~~

Khi deploy lên external Tomcat, container cung cấp Servlet API. WAR chuẩn **không tự chạy bằng `java -jar`** nếu thiếu Boot launcher/điểm vào thực thi.

### 12.2. Spring Boot executable WAR

Một executable WAR thường có layout:

~~~text
boot-provided-war-1.0.0.war
├── META-INF/MANIFEST.MF
├── WEB-INF/classes/...
├── WEB-INF/lib/...
├── WEB-INF/lib-provided/
│   └── ... embedded container dependencies ...
└── org/springframework/boot/loader/...
~~~

Với Spring Boot Maven Plugin:

- `WEB-INF/lib` chứa application libraries cần cho webapp.
- `WEB-INF/lib-provided` chứa **những dependencies được đánh dấu provided** cho mục đích executable WAR.
- Khi WAR được triển khai theo mô hình Servlet container ngoài, thư viện `WEB-INF/lib-provided` **không phải thư mục thư viện webapp thông thường** mà container thêm vào `WEB-INF/lib` classpath.
- Khi dùng `java -jar` trên executable WAR, **Spring Boot launcher** có thể dùng các dependencies đó để tự chạy embedded container.
- Điều này cho phép một artifact phục vụ **hai cách chạy**, nếu container/API/framework versions tương thích.

**Không kết luận rằng “provided luôn vắng mặt hoàn toàn khỏi mọi WAR file”**. Câu đó đúng theo ý nghĩa **không đóng gói vào runtime `WEB-INF/lib` của WAR chuẩn**, nhưng cần phân biệt Spring Boot repackage và `lib-provided`.

Đây là hành vi của **Spring Boot Maven Plugin**, không phải quy luật của mọi Maven plugin, không nên suy rộng cho Shade/Assembly hay WAR tiêu chuẩn.

## 13. Ví dụ Spring Boot WAR hoàn chỉnh — Java 17 + Boot 3.5.x

Ví dụ này minh họa **cách chuyển embedded Tomcat sang provided trong Maven**, đồng thời giữ khả năng chạy executable WAR. Để có build tái hiện, dùng **Spring Boot 3.5.0** là phiên bản đã phát hành và tương thích Java 17. Đây là **version học tập được pin**, không phải khuyến nghị sử dụng release cũ thay vì bản vá bảo mật mới nhất. Trước production hãy cập nhật lên patch đang được hỗ trợ và kiểm tra compatibility.

### 13.1. Cấu trúc

~~~text
boot-provided-war/
├── pom.xml
└── src/
    ├── main/java/com/example/bootwar/
    │   ├── BootWarApplication.java
    │   └── HelloController.java
    └── test/java/com/example/bootwar/
        └── BootWarTest.java
~~~

### 13.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>boot-provided-war</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích từng phần:**

- `spring-boot-starter-parent:3.5.0` quản lý versions của nhiều Spring dependencies/plugins.
- `<packaging>war</packaging>` tạo web archive thay vì executable JAR mặc định.
- `spring-boot-starter-web` cung cấp Spring MVC/web components của ứng dụng.
- `spring-boot-starter-tomcat` được direct-declare với `provided`, vì khi external deployment **Tomcat ngoài** chịu trách nhiệm cung cấp container.
- `spring-boot-starter-test` chỉ phục vụ tests.
- `spring-boot-maven-plugin` tạo executable archive qua repackage execution đã được starter parent cấu hình; **không cần khai báo thêm một execution `repackage` trùng**.
- WAR cuối có thể vừa chạy bằng Spring Boot launcher qua `java -jar`, vừa deploy theo mô hình WAR vào external Tomcat.
- Project dùng JDK 17+ và Spring Boot 3.x namespace `jakarta.servlet`, phù hợp với Tomcat 10.1.
- Không copy riêng `jakarta.servlet-api` vào dependency `compile` chỉ để “bổ sung API”; starter Tomcat dependency đã cung cấp những parts mà Spring Boot cần khi compile/test và là provided cho external deployment.

### 13.3. BootWarApplication.java

Tạo `src/main/java/com/example/bootwar/BootWarApplication.java`:

~~~java
package com.example.bootwar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class BootWarApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(BootWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(BootWarApplication.class, args);
    }
}
~~~

`SpringBootServletInitializer` giúp external Servlet container bootstrapping Spring application khi deploy WAR. `main` dùng cho executable archive. Hai đường khởi chạy **khác nhau** nhưng cùng tạo application context từ `BootWarApplication`.

### 13.4. HelloController.java

Tạo `src/main/java/com/example/bootwar/HelloController.java`:

~~~java
package com.example.bootwar;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot WAR";
    }
}
~~~

Spring MVC trả response body là chuỗi `Hello from Spring Boot WAR`. Controller không tạo/khởi động Servlet container; nó đăng ký handler trong ứng dụng Spring.

### 13.5. BootWarTest.java

Tạo `src/test/java/com/example/bootwar/BootWarTest.java`:

~~~java
package com.example.bootwar;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BootWarTest {

    @LocalServerPort
    int port;

    @Test
    void endpointRunsUsingTestClasspath() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + "/hello"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Hello from Spring Boot WAR", response.body());
    }
}
~~~

Lưu ý:

- `@SpringBootTest(RANDOM_PORT)` khởi động embedded container **cho test** trong một port ngẫu nhiên.
- Maven scope `provided` có mặt trên **test classpath**, nên test vẫn có thể dùng embedded Tomcat theo cách Boot test bootstrap.
- Test này không yêu cầu external Tomcat 10.1 instance phải được cài trước.
- Test xác minh HTTP endpoint trong **Maven test runtime**, nhưng chưa chứng minh WAR đã deploy thành công vào **external Tomcat thật**.
- `@LocalServerPort` truyền port thực tế, tránh hardcode `8080`.
- Import `Autowired` không cần trong code trên; có thể bỏ nếu IDE báo unused import. **Java compiler không lỗi với unused import hợp lệ**, nhưng trong project thực nên dọn để code sạch.

### 13.6. Build và chạy theo hai cách

Chạy:

~~~bash
mvn -B clean verify
~~~

Khi dependencies resolve được, Spring Boot `repackage` sẽ tạo executable WAR:

~~~text
target/boot-provided-war-1.0.0.war
~~~

**Cách A — Chạy như executable WAR**

~~~bash
java -jar target/boot-provided-war-1.0.0.war
~~~

Khi Spring Boot/Tomcat embedded khởi động xong (thường mặc định port 8080 nếu chưa cấu hình), mở terminal khác:

~~~bash
curl -fsS http://localhost:8080/hello
~~~

**HTTP response body mong đợi:**

~~~text
Hello from Spring Boot WAR
~~~

Dòng này là HTTP body, không phải toàn bộ stdout của Java process; console còn có Spring Boot startup logs.

**Cách B — Deploy lên external Tomcat**

Đưa cùng WAR vào Tomcat 10.1 (ví dụ context path lấy theo basename `boot-provided-war`) và truy cập:

~~~bash
curl -fsS http://localhost:8080/boot-provided-war/hello
~~~

**HTTP response body mong đợi:**

~~~text
Hello from Spring Boot WAR
~~~

Cách B chỉ chạy sau khi WAR được external Tomcat deploy thành công. Nếu Tomcat dùng context khác hoặc được đặt sau reverse proxy, URL cần điều chỉnh.

**Không chạy embedded Boot và external Tomcat đồng thời cùng port 8080** trên cùng host mà không điều chỉnh port; hai process có thể tranh chấp socket. Dùng hai cách ở các thời điểm khác nhau hoặc cấu hình ports khác nhau.

### 13.7. Xem `lib-provided` trong Boot WAR

~~~bash
jar tf target/boot-provided-war-1.0.0.war
~~~

Kết quả tiêu biểu chứa những đường dẫn:

~~~text
WEB-INF/classes/com/example/bootwar/BootWarApplication.class
WEB-INF/classes/com/example/bootwar/HelloController.class
WEB-INF/lib/...
WEB-INF/lib-provided/...
org/springframework/boot/loader/...
~~~

Ở Spring Boot 3.5.0, các JAR liên quan embedded Tomcat được đánh dấu provided thường nằm dưới `WEB-INF/lib-provided`. File names cụ thể phụ thuộc managed versions nên không nên hardcode một danh sách library patch versions mà không đọc JAR thật.

Điểm phân biệt quan trọng:

| Archive | `WEB-INF/lib` | `WEB-INF/lib-provided` |
| --- | --- | --- |
| Maven WAR chuẩn (phần 6) | Application runtime libraries | Thông thường không có |
| Spring Boot executable WAR | Application libraries | Container dependencies được cung cấp khi deploy external, dùng bởi launcher khi chạy `java -jar` |

**Đừng cố copy tay JAR từ `lib-provided` vào `WEB-INF/lib`** để sửa lỗi external deploy; trước hết kiểm tra compatibility và Boot plugin config.

## 14. Spring Boot executable JAR không nên đổi Tomcat thành provided một cách vô ý

Một Spring Boot web application chỉ chạy bằng:

~~~bash
java -jar target/app.jar
~~~

với `packaging=jar` cần một embedded Servlet container (thường Tomcat) nếu là Servlet MVC application. Nếu bạn đổi `spring-boot-starter-tomcat` sang scope `provided` trong **executable JAR** mà không hiểu cách Boot Plugin đóng gói, runtime behavior có thể khác và yêu cầu packaging/runtime không còn rõ ràng.

Sự kết hợp **`packaging=war` + `spring-boot-starter-tomcat:provided` + Boot Maven repackage** là trường hợp được tài liệu Spring Boot hướng dẫn cho traditional deployment và executable WAR.

Không áp công thức đó cho:

- Spring WebFlux ứng dụng chạy thuần Reactor Netty: traditional Servlet WAR deployment **không được Spring Boot hướng dẫn hỗ trợ** theo cách tương tự.
- Native image deployment.
- Ứng dụng Java `main` không dùng Servlet container.
- Bản Spring Boot cũ dùng `javax.servlet` mà deploy lên Tomcat 10.1 không qua migration.
- Các framework có packaging/container launcher riêng khác Spring Boot.

## 15. Vì sao Boot WAR test chạy được dù Tomcat starter là provided?

Maven `provided` vẫn có trên **test classpath**. Trong ví dụ Boot, `@SpringBootTest(webEnvironment=RANDOM_PORT)` cần embedded web server để thực hiện HTTP request. Test classpath có provided Tomcat dependencies nên việc khởi động web server trong test là hợp lý.

Điều này **không có nghĩa** Tomcat implementation được đặt trong `WEB-INF/lib` của WAR chuẩn. Hai bối cảnh khác:

1. **Test JVM:** Maven cung cấp dependencies theo test classpath, gồm cả provided.
2. **External WAR runtime:** Tomcat ngoài cung cấp Servlet engine và API.
3. **Executable Boot WAR:** Boot launcher sử dụng các dependencies trong `WEB-INF/lib-provided` khi chạy `java -jar`.

Một lỗi thường gặp là nhầm behavior của test với behavior deployment. Test pass khi JUnit/Spring Boot tự khởi động embedded server chưa bảo đảm external Tomcat đã dùng đúng Servlet version, classloader policy và security settings.

## 16. `provided` không giống `optional`, `system` hoặc exclusions

Những cơ chế này giải quyết vấn đề khác nhau:

| Cơ chế | Chức năng | Có dùng để thể hiện container cung cấp API không? |
| --- | --- | --- |
| `<scope>provided</scope>` | Có compile/test, không ở runtime graph; không transitive | **Có**, khi container thật sự cung cấp |
| `<optional>true</optional>` | Hạn chế transitive dependency đối với consumer | Không thay thế scope `provided` |
| `<scope>system</scope>` | Lấy JAR theo local filesystem path | Không nên dùng để chỉ tới `tomcat/lib` trên máy developer |
| `<exclusions>` | Loại transitive dependency cụ thể khỏi đường resolution | Có thể hỗ trợ xử lý conflict, không tự xác nhận API contract |
| `<dependencyManagement>` | Quản lý version/scope được sử dụng theo rules Maven | Không thêm dependency nếu chỉ nằm trong management |
| Maven profile | Kích hoạt cấu hình theo hoàn cảnh | Không phải công tắc thay thế runtime library ownership |

### Sai lầm thường gặp: system scope trỏ vào Tomcat cài trên máy

Ví dụ không khuyến nghị:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>system</scope>
    <systemPath>C:/tomcat/lib/servlet-api.jar</systemPath>
</dependency>
~~~

Lý do không nên:

- Path chỉ đúng một máy.
- CI không có thư mục giống developer.
- Maven không lấy API từ repository chuẩn theo cách đã mong đợi.
- Không tự bảo đảm file ở path đó thực sự là Servlet 6.0.
- Khi deploy lên một container khác có thể không tương thích.
- Khó tái tạo/kiểm soát provenance.

Dùng `jakarta.servlet-api` từ repository với scope `provided` và kiểm tra external container version riêng là mô hình rõ ràng hơn.

## 17. Dependency mediation và trường hợp transitive API lọt vào WAR

Một project thường có nhiều dependencies, trong đó một số có thể kéo API/spec libraries vào graph. Nếu BOM/parent hoặc một dependency khác quản lý `jakarta.servlet-api`, không nên nhìn một khai báo trực tiếp rồi kết luận WAR sạch.

Các lệnh chẩn đoán:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
~~~

Các việc cần làm:

1. Kiểm tra **effective POM** của module WAR, không chỉ parent fragment.
2. Xác định direct dependency có `scope=provided` không.
3. Xem transitive paths khác tới API/spec/implementation.
4. Dùng dependencyManagement/exclusions có chủ đích để kiểm soát versions.
5. Kiểm tra WAR archive đã build bằng `jar tf`, đặc biệt `WEB-INF/lib`.
6. Chạy đúng container đích để phát hiện runtime linkage.
7. Không xóa random libraries cho tới khi tree “ít dòng” nếu ứng dụng thật sự cần chúng.

Trong Maven, một direct dependency gần hơn trong dependency mediation có thể quyết định version/scope hiệu lực so với transitive definitions. Vì thế **dependency tree và artifact packaging thực tế** là hai nguồn bằng chứng cần xem cùng nhau.

### Provided không tự truyền cho downstream module

Nếu module A là library khai báo Servlet API provided, module B phụ thuộc A, B **không được giả định tự nhận Servlet API transitively**. Khi B có source trực tiếp dùng Servlet API, B nên khai báo API dependency với scope thích hợp cho chính B.

Nhất là trong multi-module Maven reactor: parent POM có dependencyManagement chỉ quản lý version, **không tự thêm Servlet API vào mọi module**. Mỗi web module cần khai báo dependency thực sự.

## 18. Parent POM và profiles: đừng làm phạm vi `provided` lan sai nơi

Một parent POM có thể quản lý Servlet API version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child WAR module dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
    </dependency>
</dependencies>
~~~

Trong trường hợp metadata quản lý tương ứng được áp dụng, child có thể nhận version/scope được quản lý. Tuy nhiên phải nhìn **effective POM** và xác định dependency thực sự có trong `<dependencies>`; chỉ xuất hiện trong dependencyManagement không làm API vào classpath.

Cũng cần lưu ý:

- Một multi-module project có thể gồm core library, webapp WAR và CLI service.
- `provided` Servlet API có thể phù hợp với **WAR module** nhưng không phù hợp với một executable JAR riêng.
- Parent `<dependencies>` có thể truyền dependency xuống child không mong muốn; cân nhắc quản lý qua dependencyManagement.
- Profiles theo target server version có thể hữu ích nhưng dễ tạo build khác nhau; pin và test từng combination.
- Nếu module library công bố API công khai dùng Servlet types, consumer phải có matching API trên classpath của họ.

**Không dùng một POM chung để biến tất cả dependencies thành `provided` chỉ vì một module trong reactor deploy lên Tomcat.**

## 19. Cần chọn Servlet API cụ thể đến mức nào?

Với demo:

~~~text
Java release: 17
Servlet spec: Jakarta Servlet 6.0
API artifact: jakarta.servlet:jakarta.servlet-api:6.0.0
External container: Tomcat 10.1
Packaging: war
~~~

Đây là một tổ hợp có ý nghĩa. Nhưng khi ứng dụng thực tế có Jakarta Pages (JSP), Expression Language (EL), WebSocket hoặc security annotations, phải xét thêm spec versions/container capabilities, không chỉ nhìn Servlet API.

**Nếu API của framework yêu cầu spec cao hơn container**, chỉ đổi scope không sửa được. Ví dụ một Java/Spring framework biên dịch dựa trên classes/methods của Servlet 6.1 nhưng target Tomcat 10.1 chỉ hỗ trợ Servlet 6.0 có thể gặp compatibility error.

Đừng ưu tiên “lấy artifact mới nhất” hơn **khả năng chạy trên môi trường thật**. Hãy chọn đúng spec version, JDK target và framework compatibility matrix, rồi nâng cùng nhau có kiểm thử.

## 20. Khi nào cần tự đóng gói Servlet API?

Với **external Servlet container**, câu trả lời thường là **không**. Container đã sở hữu API theo specification. Có những môi trường đặc biệt như chương trình nhúng servlet container, test fixture, custom launcher hoặc embedded application, nhưng khi đó phải làm rõ:

- Ai khởi tạo server?
- Classloader nào cấp Servlet API?
- Application có deploy WAR hay chạy Java main?
- API/implementation được đóng gói qua plugin nào?
- Có bị duplicate với một server runtime khác không?

**Đừng giải một bài toán embedded application bằng cách copy một file Servlet API JAR vào WAR**. Servlet API chỉ chứa interfaces/classes của specification; nó không thay thế Tomcat/Jetty/Undertow implementation.

Trong Spring Boot executable WAR, Boot Plugin có packaging riêng cho provided dependencies để embedded mode hoạt động. Đây là ngoại lệ có cơ chế cụ thể, không phải lý do để mọi WAR đều mang `servlet-api.jar`.

## 21. Các lỗi phổ biến và cách kiểm tra

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `package jakarta.servlet.http does not exist` lúc compile | Thiếu Servlet API dependency hoặc dependency không có trên compile path | Thêm đúng `jakarta.servlet-api` provided |
| Compile pass, deploy báo `NoClassDefFoundError: jakarta/servlet/...` | Container không có Jakarta namespace hoặc đang dùng Tomcat 9 | Chọn Tomcat 10.1+ phù hợp hoặc migrate lại |
| `javax.servlet.*` không tìm thấy trên Tomcat 10.1 | App vẫn dùng Java EE javax namespace | Chuyển sang Jakarta API/framework tương thích |
| `NoSuchMethodError` ở Servlet API | Compile against API version cao hơn runtime | Align Servlet API/spec và target server |
| Servlet deploy nhưng `/hello` 404 | Annotation scanning/config/context path sai | Kiểm tra @WebServlet, logs, WAR name, web.xml |
| WAR có hai Servlet API JAR khác nhau | Dependency hoặc packaging bổ sung API không đúng | Xem dependency tree và WEB-INF/lib |
| `ClassNotFoundException: org.apache.commons.lang3.StringUtils` | Commons Lang bị đánh dấu provided nhưng container không cấp | Đưa application library vào WAR/runtime |
| WAR thiếu Spring MVC classes | Đánh dấu cả starter web là provided hoặc filters loại library | Giữ application libraries đúng scope |
| Spring Boot WAR không chạy external Tomcat | Thiếu SpringBootServletInitializer hoặc container/version không khớp | Sửa initializer và compatibility matrix |
| Boot `java -jar` WAR không có embedded Tomcat | Không repackage hoặc loại nhầm lib-provided | Xem Boot Maven Plugin và archive layout |
| Boot WAR có `WEB-INF/lib-provided` bị hiểu là duplicate | Nhầm với standard `WEB-INF/lib` | Phân biệt executable WAR loader với external container classpath |
| Unit test pass nhưng WAR không deploy | Test không khởi động external container | Thêm deployment/integration smoke test |
| `mvn package` tạo `.jar` thay vì `.war` | POM `packaging` là jar hoặc cấu hình khác | Đặt packaging đúng, xem effective POM |
| WAR Plugin báo thiếu web.xml | Plugin/config project cũ | Dùng servlet annotations phù hợp; `failOnMissingWebXml=false` |
| `java -jar app.war` không chạy | WAR thường thiếu executable launcher | Deploy external container; chỉ Boot executable WAR có launcher |
| Tomcat không khởi động do Java version | Container yêu cầu JDK cao hơn runtime | Kiểm tra Tomcat compatibility table |
| `ClassCastException`/linkage sau deploy | Duplicate API/implementation hoặc classloader conflicts | Audit WEB-INF/lib và container lib |
| Web app hoạt động trên Tomcat nhưng fail ở server khác | Container spec/policies khác | Test từng server mục tiêu; tránh assumption |
| Spring Boot 2 WAR dùng javax deploy lên Tomcat 10.1 fail | Namespace thế hệ framework khác | Chọn runtime phù hợp hoặc migrate Boot |
| Chỉ thấy provided dependency trong dependency tree nên nghĩ WAR chứa JAR | Nhầm build dependency với packaged lib | Kiểm tra `jar tf` và `WEB-INF/lib` |
| Provided dependency bị mất ở test riêng | Test chạy ngoài Maven/Failsafe/Surefire với classpath khác | Kiểm tra IDE/test-runner classpath |
| Dùng `systemPath` trỏ máy developer | Local path không thể tái hiện | Dùng repository artifact provided |

Lỗi runtime phải được đối chiếu với **toàn bộ stacktrace** và Tomcat deployment logs. Một class name không tìm thấy có thể đến từ sai version, sai namespace hoặc dependency bị loại khỏi WAR — không tự động do cùng một nguyên nhân.

## 22. Quy trình debug theo lớp: POM → WAR → Container

**Bước 1 — Kiểm tra JDK và Maven**

~~~bash
mvn -version
java -version
~~~

Kiểm tra JDK của **container riêng biệt** với JDK dùng build nếu chúng chạy ở hai host/process.

**Bước 2 — Xem Maven model**

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

Tìm `packaging=war`, `jakarta.servlet-api:provided`, versions của plugin và application dependencies.

**Bước 3 — Build sạch**

~~~bash
mvn -B clean verify
~~~

Xác nhận unit tests thực sự chạy; không chỉ xem BUILD SUCCESS nếu tests bị skip.

**Bước 4 — Xem WAR entries**

~~~bash
jar tf target/servlet-provided-demo-1.0.0.war
~~~

Kiểm tra `WEB-INF/classes/HelloServlet.class`, `WEB-INF/lib/commons-lang3-3.17.0.jar`, và sự **vắng mặt** của `WEB-INF/lib/jakarta.servlet-api-6.0.0.jar`.

**Bước 5 — Xác nhận server thật**

Kiểm tra Tomcat major version, Servlet specification, Java runtime, deployment configuration, logs, servlet annotation scanning và context path.

**Bước 6 — Request endpoint**

~~~bash
curl -i http://localhost:8080/servlet-provided-demo/hello
~~~

Với response thành công, server status là HTTP 200 và body chứa `Hello from external Tomcat: MAVEN`. `-i` còn in headers, nên không coi toàn bộ stdout curl là chỉ một dòng.

**Bước 7 — Đối chiếu lỗi**

- Compile failure → API missing/scope/source imports.
- WAR packaging failure → WAR plugin/config/web resources.
- Deploy startup failure → Servlet namespace, container API, classloading.
- HTTP 404 → servlet mapping/context path.
- HTTP 500 → servlet code/dependency runtime/exception.

**Bước 8 — Kiểm tra release security**

Dù WAR không mang Servlet API, **container Tomcat** vẫn cần bản vá CVE. Việc đặt dependency `provided` không giảm trách nhiệm cập nhật container ở production.

## 23. Test và bảo mật khi phụ thuộc vào container

Khi container cung cấp Servlet API và implementation, bạn cần quản lý hai vòng đời cập nhật:

1. **Application:** cập nhật Maven dependencies, source code, WAR artifact.
2. **Container/JDK:** cập nhật Tomcat, Servlet implementation, cấu hình TLS, threads, connectors và security patches.

Những lưu ý thực tế:

- Không đóng gói passwords/tokens trong WAR.
- Không đưa thư viện container internals vào application nếu không cần.
- Pin API spec phù hợp nhưng theo dõi bản vá container thực tế.
- Kiểm tra request encoding, security headers, session cookies, thread lifecycle và class loading trên server đích.
- Mỗi môi trường CI/staging/prod nên có compatibility matrix rõ ràng.
- Một Servlet API JAR không tự là “bản Tomcat”; không thử giải lỗi server bằng copy JAR này.
- Quét dependencies nằm trong `WEB-INF/lib` và quét image/server runtime riêng.
- Với Spring Boot executable WAR, cũng cần quản lý CVE của embedded Tomcat trong `lib-provided` cho chế độ chạy `java -jar`.
- Không chạy một app chưa tin cậy dưới Tomcat có quyền truy cập toàn bộ production secrets.

## 24. Bài tập tự kiểm tra

**Câu 1.** Vì sao cần khai báo `jakarta.servlet-api` nếu Tomcat đã có API?

**Đáp:** Để Maven compiler/test compiler nhìn thấy những class Servlet trong build. `provided` thể hiện Tomcat sẽ cung cấp chúng **khi runtime**, không phải lúc Maven compile.

**Câu 2.** `provided` có nằm trên test classpath không?

**Đáp:** Có. Maven provided có ở compile và test classpaths, không ở runtime dependency graph.

**Câu 3.** Khi `packaging=war`, `war:war` có được bind mặc định vào package không?

**Đáp:** Có. Không cần thêm execution `war:war` riêng để tạo WAR chuẩn.

**Câu 4.** Với Tomcat 10.1, import nào phù hợp?

**Đáp:** `jakarta.servlet.*`, với API Jakarta Servlet 6.0. `javax.servlet.*` thuộc nhánh Servlet trước Jakarta namespace migration.

**Câu 5.** WAR có `WEB-INF/lib/commons-lang3-3.17.0.jar` nhưng không có `WEB-INF/lib/jakarta.servlet-api-6.0.0.jar`. Đó có phải thiếu thư viện?

**Đáp:** Không nếu deploy lên Tomcat 10.1. Servlet API do container cấp; Commons Lang do ứng dụng cần ở runtime.

**Câu 6.** Chuyển Commons Lang sang `provided` có luôn an toàn không?

**Đáp:** Không. Chỉ đúng khi runtime ngoài thật sự cam kết cung cấp version tương thích; Tomcat không mặc định cấp Commons Lang cho webapp.

**Câu 7.** WAR chuẩn có thể mặc định chạy bằng `java -jar` không?

**Đáp:** Không. WAR chuẩn deploy lên Servlet container; executable launcher là một cơ chế riêng.

**Câu 8.** Spring Boot executable WAR có thể chứa provided Tomcat JAR ở đâu?

**Đáp:** `WEB-INF/lib-provided`, do Spring Boot Maven Plugin repackage quản lý để hỗ trợ launcher khi dùng `java -jar`.

**Câu 9.** Vì sao `WEB-INF/lib-provided` không giống `WEB-INF/lib`?

**Đáp:** Thư mục đầu phục vụ executable WAR của Boot, còn thư mục sau thuộc runtime libraries của webapp do external Servlet container load.

**Câu 10.** Dùng Spring Boot WAR mà không extends `SpringBootServletInitializer` có chắc external Tomcat bootstrap ứng dụng đúng không?

**Đáp:** Không. Traditional deployment theo tài liệu Spring Boot yêu cầu cơ chế initializer phù hợp; ví dụ cung cấp subclass và override `configure`.

**Câu 11.** Compile với Servlet 6.1 rồi chạy Tomcat 10.1 có nguy cơ gì?

**Đáp:** Tomcat 10.1 cung cấp Servlet 6.0, nên có thể thiếu API mới và gây runtime linkage errors.

**Câu 12.** `mvn verify` với unit test pass chứng minh WAR đã chạy trên Tomcat ngoài chưa?

**Đáp:** Chưa. Cần deployment smoke/integration test trên container thật.

**Câu 13.** Scope `provided` có tự bảo đảm Tomcat được cài trên CI/prod không?

**Đáp:** Không. Đó là hợp đồng runtime phải được provisioning/ops đảm bảo.

**Câu 14.** Dùng `system` + `systemPath` trỏ vào Tomcat developer có nên là mặc định?

**Đáp:** Không. Nên dùng artifact từ repository với `provided` và kiểm tra container version riêng.

**Câu 15.** Vì sao Boot `@SpringBootTest(RANDOM_PORT)` có thể chạy embedded Tomcat dù Tomcat starter provided?

**Đáp:** Vì Maven provided có mặt trên **test classpath**. Điều đó khác external WAR runtime.

## 25. Checklist trước khi phát hành WAR

1. Xác định **deployment model**: external Tomcat WAR, Spring Boot executable JAR hay Boot executable WAR.
2. Chọn đúng `packaging=war` cho WAR.
3. Xác nhận Servlet API `javax` hoặc `jakarta` khớp container.
4. Pin API spec version được container hỗ trợ.
5. Đặt Servlet API scope `provided` cho WAR chuẩn chạy external container.
6. Đừng nhúng Servlet implementation/embedded server khác vào WAR chuẩn không có lý do.
7. Giữ application libraries cần runtime trong scope `compile` hoặc `runtime` phù hợp.
8. Xem effective POM và dependency tree.
9. Dùng Maven WAR Plugin phiên bản phù hợp JDK/Maven.
10. Đăng ký Servlet bằng `@WebServlet` hoặc `web.xml` theo chính sách scanning.
11. Kiểm tra `WEB-INF/classes` và `WEB-INF/lib` của WAR thật.
12. Xác nhận provided API JAR không được đóng gói vào `WEB-INF/lib`.
13. Với Spring Boot traditional WAR, dùng `SpringBootServletInitializer` và Tomcat starter provided.
14. Với Boot executable WAR, kiểm tra `WEB-INF/lib-provided` thay vì suy luận không có container libs trong toàn archive.
15. Chạy `mvn clean verify` và đọc test reports.
16. Triển khai WAR vào container version/JDK đích để smoke test.
17. Kiểm tra context path, mapping và HTTP response status/body.
18. Không để WAR chạy nhầm vào staging/production khi chỉ muốn test.
19. Quét CVE/license trong application dependencies và container runtime.
20. Lập kế hoạch upgrade container API cùng JDK/framework.
21. Dùng container images hoặc deployment manifests có version kiểm soát.
22. Không hardcode secrets trong WAR hoặc Maven profiles.
23. Với nhiều modules, tránh truyền nhầm scope provided cho CLI/executable JAR không có container.
24. Kiểm tra classloader conflict và không copy servlet-api JAR thủ công vào Tomcat/webapp.
25. Chỉ tuyên bố **deployment verified** khi đã thử HTTP hoặc hành vi thực trên external server.

## Tài liệu chính thức để tra cứu

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven WAR Plugin — Introduction](https://maven.apache.org/plugins/maven-war-plugin/)
- [Apache Maven WAR Plugin — war:war](https://maven.apache.org/plugins/maven-war-plugin/war-mojo.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Tomcat — Which Version Do I Want?](https://tomcat.apache.org/whichversion)
- [Apache Tomcat — Class Loader How-To](https://tomcat.apache.org/tomcat-10.1-doc/class-loader-howto.html)
- [Jakarta EE — Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/)
- [Spring Boot — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)

