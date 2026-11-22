# Thực hành đóng gói WAR cho ứng dụng web hiện hữu và kiểm tra cấu trúc bằng Apache Ant

## 1. Bài toán thực tế: biến mã nguồn web hiện có thành một WAR triển khai được

Giả sử một ứng dụng Java Web đã chạy trong IDE hoặc trong một thư mục triển khai của máy chủ. Dự án có các servlet, file JSP/HTML, tài nguyên CSS/JavaScript, cấu hình và thư viện JAR. Nhóm cần dùng **Apache Ant** để tạo một tệp `.war` độc lập, đưa sang môi trường kiểm thử hoặc máy chủ ứng dụng mà không phải sao chép thủ công từng file.

Yêu cầu của bản thực hành:

1. Biên dịch mã Java thành `.class` bằng JDK phù hợp với máy chủ đích.
2. Đưa các class và tài nguyên classpath vào `WEB-INF/classes/`.
3. Đưa những JAR cần thiết ở runtime vào `WEB-INF/lib/`.
4. Giữ trang web, JSP, CSS, JavaScript và descriptor triển khai ở vị trí chuẩn.
5. **Không đóng gói** Servlet API do container cung cấp vào `WEB-INF/lib/`.
6. Mở hoặc giải nén WAR và kiểm tra cấu trúc trước khi triển khai.
7. Chạy ứng dụng trên servlet container phù hợp để xác minh artifact thực sự dùng được.

Đây là một bài về **đóng gói ứng dụng hiện hữu**. Khi áp dụng cho repository thực tế, phải xác định đúng source root, tài nguyên, dependency, phiên bản Servlet/Jakarta và cách triển khai trước khi viết task Ant. Một WAR được tạo thành công nhưng thiếu resource hoặc gói sai thư viện vẫn có thể không khởi động được.

## 2. WAR là gì và container tìm các thành phần ở đâu?

WAR (**Web Application Archive**) là một kho nén định dạng ZIP có cấu trúc dành cho ứng dụng web Java. Servlet container hoặc application server, chẳng hạn Apache Tomcat hoặc một máy chủ Jakarta EE, có thể triển khai WAR và diễn giải các thành phần theo quy ước của ứng dụng web.

Cấu trúc thường gặp:

```text
shop.war
├── index.jsp
├── css/
│   └── app.css
├── js/
│   └── app.js
├── images/
│   └── logo.png
├── META-INF/
│   └── MANIFEST.MF
└── WEB-INF/
    ├── web.xml
    ├── classes/
    │   ├── com/example/web/HelloServlet.class
    │   └── app.properties
    └── lib/
        ├── example-utils.jar
        └── another-runtime-library.jar
```

| Vị trí trong WAR | Nội dung và vai trò |
| --- | --- |
| `/index.jsp`, `/css/`, `/js/` | Tài nguyên web ở public document root; cách truy cập còn phụ thuộc cấu hình bảo vệ của ứng dụng |
| `/WEB-INF/web.xml` | Deployment descriptor: servlet, mapping, filter, listener, security constraint, welcome file… |
| `/WEB-INF/classes/` | Bytecode Java và tài nguyên truy cập qua classpath ứng dụng |
| `/WEB-INF/lib/*.jar` | Thư viện JAR được đóng gói cùng ứng dụng và nạp qua classloader của webapp |
| `/META-INF/MANIFEST.MF` | Metadata của archive, có thể do task đóng gói tạo |
| `/WEB-INF/` | Vùng nội bộ của webapp; container chuẩn không phục vụ trực tiếp nội dung này như tài nguyên tĩnh thông thường |

Ví dụ, Java gọi `getResourceAsStream("/app.properties")` có thể đọc file `WEB-INF/classes/app.properties`. File nằm ở `WEB-INF/app.properties` **không tự động** trở thành resource ở classpath gốc.

Một ứng dụng theo Servlet 3.0 trở lên có thể dựa vào annotation hoặc cơ chế khởi tạo thay vì bắt buộc có `web.xml`; tuy nhiên ứng dụng hiện hữu thường vẫn dùng descriptor. Trong bài này, ta chọn **có `web.xml` rõ ràng** để dễ kiểm chứng và không thay đổi cách khai báo servlet của hệ thống cũ.

## 3. Xác định công nghệ của ứng dụng trước khi đóng gói

Việc đổi tên `.jar` thành `.war` không giải quyết khác biệt API web.

| Dòng ứng dụng | Namespace servlet thường gặp | Container tiêu biểu | Điều cần thống nhất |
| --- | --- | --- | --- |
| Java EE/Servlet 4.x và cũ hơn | `javax.servlet.*` | Tomcat 9 / môi trường hỗ trợ Java EE tương ứng | Servlet API `javax`, descriptor và dependency tương thích |
| Jakarta Servlet 5+ | `jakarta.servlet.*` | Tomcat 10+ / Jakarta EE tương ứng | Servlet API `jakarta`, descriptor và dependency tương thích |

Ví dụ thực hành dưới đây dùng **JDK 17, Jakarta Servlet 6.0 và Tomcat 10.1** làm môi trường minh họa. Với ứng dụng `javax.servlet` hiện hữu, hãy dùng API/container phù hợp với hệ đó hoặc thực hiện một dự án di trú tương thích riêng. **Ant không tự chuyển `javax.servlet` thành `jakarta.servlet` chỉ bằng cách đóng gói WAR.**

Ba nhóm dependency cần phân biệt:

- **Compile-time**: thư viện dùng để biên dịch mã, gồm Servlet API.
- **Runtime kèm ứng dụng**: thư viện container không mặc định cung cấp, cần đưa vào `WEB-INF/lib`.
- **Provided by container**: Servlet API và các API được môi trường triển khai cam kết cung cấp; dùng ở compile classpath nhưng thường không đưa vào WAR.

Trước khi triển khai, kiểm tra tài liệu máy chủ đích để biết nó cung cấp API nào. Tránh đóng gói trùng thư viện hệ thống gây tranh chấp classloader và lỗi như `ClassCastException` hoặc `NoSuchMethodError`.

## 4. Khảo sát bố cục một dự án hiện hữu

Một repository thực tế có thể đã có dạng:

```text
existing-webapp/
├── build.xml                         # có thể đã tồn tại hoặc sẽ tạo
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/web/
│       │       └── HelloServlet.java
│       ├── resources/
│       │   └── app.properties
│       └── webapp/
│           ├── index.jsp
│           ├── css/app.css
│           └── WEB-INF/web.xml
└── lib/
    ├── provided/
    │   └── jakarta.servlet-api-6.0.0.jar
    └── runtime/
        └── ... các JAR mà ứng dụng thật sự cần ...
```

Trong dự án Maven-like, các thư mục `src/main/java`, `src/main/resources`, `src/main/webapp` khá phổ biến nhưng **không phải yêu cầu của Ant**. Nếu project cũ dùng `WebContent/`, `web/` hoặc `src/`, hãy đổi thuộc tính thư mục trong `build.xml` tương ứng. Không cần di chuyển toàn bộ mã nguồn chỉ để dùng `<war>`.

Trước khi viết target, lập một bảng ánh xạ:

| Nguồn hiện có | Vị trí cuối trong WAR | Có cần biên dịch hoặc biến đổi? |
| --- | --- | --- |
| `src/main/java/**/*.java` | `WEB-INF/classes/**/*.class` | Có, qua `<javac>` |
| `src/main/resources/**` | `WEB-INF/classes/**` | Sao chép vào classpath |
| `src/main/webapp/**/*.jsp` | Giữ đường dẫn tương đối dưới gốc WAR | Thường sao chép nguyên; container xử lý JSP |
| `src/main/webapp/css/**` | `css/**` | Sao chép nguyên hoặc qua pipeline frontend |
| `src/main/webapp/WEB-INF/web.xml` | `WEB-INF/web.xml` | Chỉ đưa vào một lần |
| `lib/runtime/*.jar` | `WEB-INF/lib/*.jar` | Đưa vào WAR |
| `lib/provided/jakarta.servlet-api-6.0.0.jar` | **Không nằm trong WAR** | Chỉ có trong compile classpath |
| `build/`, `.git/`, log và dữ liệu thử nghiệm | **Không nằm trong WAR** | Loại bỏ |

Hãy kiểm tra các file generated, JSP precompiled, web fragments `META-INF/web-fragment.xml` và manifest tùy chỉnh nếu ứng dụng hiện hữu có dùng chúng. Những phần đó là dữ liệu thực tế của hệ thống và cần được tính đến khi xác định nguồn đóng gói.

## 5. Chuẩn bị file minh họa để thực hành

Với dự án thật, có thể bỏ qua phần tạo mã mới và dùng servlet/web.xml hiện có. Các đoạn dưới chỉ dựng một ứng dụng tối thiểu để giải thích kết quả WAR.

### 5.1. Servlet

**`src/main/java/com/example/web/HelloServlet.java`**

```java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public class HelloServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().println("HELLO_WAR");
    }
}
```

Servlet được container tạo và quản lý. Ta **không** chạy lớp này bằng `java -jar shop.war`; WAR không phải executable JAR thông thường. Cách kiểm chứng là triển khai lên container rồi gọi URL tương ứng.

### 5.2. Descriptor `web.xml`

**`src/main/webapp/WEB-INF/web.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <display-name>Ant WAR Practice</display-name>

    <servlet>
        <servlet-name>hello</servlet-name>
        <servlet-class>com.example.web.HelloServlet</servlet-class>
    </servlet>

    <servlet-mapping>
        <servlet-name>hello</servlet-name>
        <url-pattern>/hello</url-pattern>
    </servlet-mapping>

    <welcome-file-list>
        <welcome-file>index.jsp</welcome-file>
    </welcome-file-list>
</web-app>
```

Nếu ứng dụng thật dùng Servlet phiên bản khác, phải giữ schema/namespace tương ứng. Không tự động nâng `web.xml` lên 6.0 nếu mã và container chưa tương thích.

### 5.3. Trang JSP và resource

**`src/main/webapp/index.jsp`**

```jsp
<%@ page contentType="text/html;charset=UTF-8" pageEncoding="UTF-8" %>
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Ant WAR Demo</title>
    <link rel="stylesheet" href="css/app.css">
</head>
<body>
    <h1>Ant WAR Demo</h1>
    <p><a href="hello">Kiểm tra servlet</a></p>
</body>
</html>
```

**`src/main/webapp/css/app.css`**

```css
body { font-family: sans-serif; margin: 2rem; }
h1 { color: #234a7a; }
```

**`src/main/resources/app.properties`**

```properties
app.name=ant-war-demo
```

Phần tài nguyên này đủ để nhận ra WAR đã đóng gói đúng JSP, CSS, servlet class, descriptor và resource classpath. Với dự án thật, các file cấu hình chứa secret phải được quản lý bằng cơ chế của môi trường triển khai; không nhúng mật khẩu production vào `src/main/resources` rồi xuất bản trong WAR.

## 6. Cấu hình build.xml: compile, copy resource và đóng gói WAR

Task cốt lõi là **`<war>`**, một task mở rộng cơ chế đóng gói ZIP/JAR của Ant và có các phần tử dành cho ứng dụng web như `<classes>` và `<lib>`.

Ví dụ này cần JDK 17 trở lên, phiên bản Ant hỗ trợ `<javac release="17">` và file `lib/provided/jakarta.servlet-api-6.0.0.jar` phù hợp. JAR Servlet API có thể lấy từ nguồn dependency tin cậy hoặc từ bản phân phối container tương ứng; tên ví dụ cần được đổi theo dependency thật. Thư mục `lib/runtime/` có thể trống nếu ứng dụng không dùng thư viện ngoài.

**`build.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-war-practice" default="verify-war" basedir=".">

    <!-- Chỉnh các đường dẫn này theo dự án hiện hữu. -->
    <property name="app.name" value="shop"/>
    <property name="src.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="webapp.dir" location="src/main/webapp"/>
    <property name="runtime.lib.dir" location="lib/runtime"/>
    <property name="servlet.api.jar"
              location="lib/provided/jakarta.servlet-api-6.0.0.jar"/>

    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="inspect.dir" location="${build.dir}/inspect"/>
    <property name="war.file" location="${dist.dir}/${app.name}.war"/>
    <property name="webxml.file"
              location="${webapp.dir}/WEB-INF/web.xml"/>

    <path id="compile.classpath">
        <!-- Provided: dùng để compile nhưng không đóng gói vào WAR. -->
        <pathelement location="${servlet.api.jar}"/>
        <!-- Các thư viện runtime cũng cần có khi compile nếu code dùng. -->
        <fileset dir="${runtime.lib.dir}"
                 includes="**/*.jar"
                 erroronmissingdir="false"/>
    </path>

    <target name="validate">
        <available file="${src.dir}"
                   type="dir" property="has.src"/>
        <fail unless="has.src" message="Missing Java source directory"/>

        <available file="${webxml.file}"
                   type="file" property="has.webxml"/>
        <fail unless="has.webxml" message="Missing WEB-INF/web.xml"/>

        <available file="${servlet.api.jar}"
                   type="file" property="has.servlet.api"/>
        <fail unless="has.servlet.api"
              message="Missing Servlet API for compilation"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

    <target name="compile" depends="validate">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"
               debug="true">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="resources" depends="compile">
        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}"
                     includes="**/*"
                     erroronmissingdir="false"/>
        </copy>
    </target>

    <target name="war" depends="resources">
        <mkdir dir="${dist.dir}"/>
        <!-- Luôn tạo WAR từ đầu để tránh entry cũ khi file nguồn bị xóa. -->
        <delete file="${war.file}" quiet="true"/>

        <war destfile="${war.file}"
             webxml="${webxml.file}"
             duplicate="fail"
             encoding="UTF8"
             update="false">

            <!-- Trang, JSP, CSS, JS và các file web của ứng dụng. -->
            <fileset dir="${webapp.dir}"
                     includes="**/*"
                     excludes="WEB-INF/web.xml,
                               WEB-INF/classes/**,
                               WEB-INF/lib/**"/>

            <!-- Tự đặt tại WEB-INF/classes trong WAR. -->
            <classes dir="${classes.dir}"/>

            <!-- Tự đặt JAR tại WEB-INF/lib trong WAR. -->
            <lib dir="${runtime.lib.dir}"
                 includes="**/*.jar"
                 erroronmissingdir="false"/>
        </war>

        <echo message="WAR created: ${war.file}"/>
    </target>

    <target name="inspect-war" depends="war">
        <!-- Giải nén để kiểm tra những entry thiết yếu. -->
        <delete dir="${inspect.dir}" quiet="true"/>
        <mkdir dir="${inspect.dir}"/>
        <unzip src="${war.file}" dest="${inspect.dir}"/>

        <available file="${inspect.dir}/WEB-INF/web.xml"
                   type="file" property="war.has.webxml"/>
        <fail unless="war.has.webxml"
              message="WAR is missing WEB-INF/web.xml"/>

        <available
            file="${inspect.dir}/WEB-INF/classes/com/example/web/HelloServlet.class"
            type="file" property="war.has.servlet"/>
        <fail unless="war.has.servlet"
              message="WAR is missing HelloServlet.class"/>

        <available file="${inspect.dir}/WEB-INF/classes/app.properties"
                   type="file" property="war.has.config"/>
        <fail unless="war.has.config"
              message="WAR is missing app.properties"/>

        <available file="${inspect.dir}/index.jsp"
                   type="file" property="war.has.jsp"/>
        <fail unless="war.has.jsp" message="WAR is missing index.jsp"/>

        <available file="${inspect.dir}/css/app.css"
                   type="file" property="war.has.css"/>
        <fail unless="war.has.css" message="WAR is missing CSS"/>

        <!-- Provided Servlet API không được đưa vào WEB-INF/lib. -->
        <available
            file="${inspect.dir}/WEB-INF/lib/jakarta.servlet-api-6.0.0.jar"
            type="file" property="war.contains.servlet.api"/>
        <fail if="war.contains.servlet.api"
              message="Container-provided Servlet API was packaged"/>

        <checksum file="${war.file}"
                  algorithm="SHA-256"
                  property="war.sha256"/>
        <echo message="WAR SHA-256: ${war.sha256}"/>
    </target>

    <target name="verify-war" depends="inspect-war"/>
</project>
```

Các đường dẫn `HelloServlet.class`, `index.jsp` và `app.properties` trong `inspect-war` là **khẳng định cụ thể cho dự án ví dụ**. Khi chuyển sang ứng dụng thật, hãy thay chúng bằng class/resource bắt buộc của sản phẩm. Không nên giữ các tên file của demo nếu ứng dụng không có chúng.

### 6.1. Vì sao dùng `<classes>` và `<lib>`?

Ant hiểu vị trí đặc biệt của hai nested element bên trong `<war>`:

```xml
<classes dir="build/classes"/>
<lib dir="lib/runtime" includes="**/*.jar"/>
```

`<classes>` đưa các file ở `build/classes/` vào `WEB-INF/classes/`, giữ đường dẫn tương đối. `<lib>` đưa JAR từ thư mục được chọn vào `WEB-INF/lib/`. Nếu dùng một `<fileset dir="build/classes">` đơn thuần ở gốc `<war>`, class có thể bị đặt sai ở `com/example/...` thay vì `WEB-INF/classes/com/example/...`.

Không sao chép nguyên thư mục `lib/provided/` vào `WEB-INF/lib/`. Tập provided được dùng trong `compile.classpath` nhưng cố ý vắng mặt khỏi nested `<lib>`.

### 6.2. Vì sao vừa có `webxml` vừa loại `WEB-INF/web.xml` khỏi fileset?

Trong ví dụ, thuộc tính:

```xml
<war webxml="src/main/webapp/WEB-INF/web.xml" ...>
```

yêu cầu Ant ghi descriptor tới `WEB-INF/web.xml`. Nếu `<fileset>` cũng chứa cùng file này, có thể tạo entry trùng tên hoặc phụ thuộc cách xử lý duplicate của archive. Bởi vậy ví dụ loại `WEB-INF/web.xml` khỏi fileset và dùng `duplicate="fail"` để phát hiện các xung đột khác.

Với ứng dụng dùng annotation và không cần descriptor, Ant hiện đại có thể tạo WAR không khai báo `webxml`. Khi đó phải thay target kiểm tra tương ứng; không nên yêu cầu mọi ứng dụng Jakarta mới đều có file `web.xml`.

### 6.3. Vì sao loại `WEB-INF/classes` và `WEB-INF/lib` khỏi webapp source?

Trong nhiều project cũ, IDE từng copy class và JAR trực tiếp vào `WebContent/WEB-INF/classes` hoặc `WebContent/WEB-INF/lib`. Nếu vừa lấy nguyên thư mục webapp, vừa dùng nested `<classes>`/`<lib>`, WAR có thể chứa entry trùng hoặc lẫn các file build cũ.

Hai exclude này buộc bản build dùng **class được biên dịch trong lượt hiện tại** và **runtime JAR được khai báo rõ**. Với ứng dụng thật, nếu các thư mục nguồn ấy chứa dữ liệu đặc biệt không được quản lý ở nơi khác, cần chuyển dữ liệu sang resource/runtime dependency phù hợp trước khi loại chúng.

### 6.4. Vì sao xóa WAR trước khi tạo?

Task ZIP/JAR/WAR của Ant có cơ chế cập nhật theo timestamp. Một WAR có sẵn đôi khi được giữ nguyên nếu Ant xem nó là đủ mới, kể cả khi quy trình đã thay đổi cách chọn file. Xóa **chỉ file đầu ra WAR** trước khi đóng gói giúp mỗi lượt thực sự tạo lại danh sách entry từ input hiện tại.

Điều này không tự xóa class đã cũ trong `build/classes/`. Khi source bị xóa hoặc đổi tên, nên chạy clean build trước phát hành, hoặc bổ sung cơ chế dọn class cũ dựa trên mô hình dependency của dự án.

## 7. Chạy build và kiểm tra đầu ra trên máy cục bộ

Từ thư mục chứa `build.xml`:

```bash
ant -version
java -version
ant -noinput clean verify-war
```

Nếu thành công, bạn sẽ thấy `build/dist/shop.war` và thông báo SHA-256. Ant cũng tạo `build/inspect/` là bản giải nén để kiểm tra.

Một lần chạy **thành công về kỹ thuật** cần đáp ứng:

- `<javac>` hoàn tất với compile classpath đúng.
- `<war>` tạo file ở `build/dist/shop.war`.
- Target `inspect-war` tìm thấy các entry bắt buộc.
- Bước kiểm tra xác nhận JAR Servlet API provided không nằm trong `WEB-INF/lib`.
- Ant trả mã thoát 0.

Ngược lại, khi một assert `<fail>` kích hoạt hoặc một task báo lỗi, Ant trả mã thoát khác 0. Đừng bỏ qua exit code của Ant trong CI chỉ vì dòng log cuối đã in đường dẫn WAR.

### 7.1. Liệt kê nội dung WAR mà không cần triển khai

JDK có sẵn công cụ `jar` để xem ZIP/JAR/WAR:

```bash
jar tf build/dist/shop.war
```

Danh sách tiêu biểu:

```text
META-INF/
META-INF/MANIFEST.MF
WEB-INF/
WEB-INF/web.xml
WEB-INF/classes/
WEB-INF/classes/com/example/web/HelloServlet.class
WEB-INF/classes/app.properties
WEB-INF/lib/
index.jsp
css/app.css
```

Thứ tự các entry và việc xuất hiện entry thư mục có thể khác tùy cách ghi archive; điều cần chứng minh trước tiên là **đúng đường dẫn của file**. Nếu có các JAR runtime, danh sách còn có `WEB-INF/lib/ten-thu-vien.jar`.

Lệnh trên chạy được ở PowerShell, CMD hoặc shell Unix miễn `jar` của JDK nằm trên PATH. Công cụ `unzip -l` cũng có thể dùng trên môi trường Unix nếu đã cài.

### 7.2. Kiểm tra riêng các file quan trọng

**Linux/macOS:**

```bash
jar tf build/dist/shop.war | grep -E '(^WEB-INF/web\.xml$|^WEB-INF/classes/|^WEB-INF/lib/|^index\.jsp$)'
```

**PowerShell:**

```powershell
jar tf build/dist/shop.war |
    Select-String -Pattern '^WEB-INF/web\.xml$','^WEB-INF/classes/','^WEB-INF/lib/','^index\.jsp$'
```

Lưu ý đây là lệnh **lọc để xem nhanh**, chưa phải phép chứng minh rằng tất cả file đều có. Target `inspect-war` ở ví dụ kiểm tra sự tồn tại của từng file quan trọng và dừng khi thiếu.

Kiểm tra bằng giải nén thủ công vào một thư mục mới cũng được:

```bash
mkdir war-review
cd war-review
jar xf ../build/dist/shop.war
```

Đoạn trên sử dụng đường dẫn tương đối từ root dự án và tạo `war-review/`. Với PowerShell có thể dùng `New-Item -ItemType Directory -Path war-review` và `Set-Location war-review`. Khi chạy lại, nên dọn thư mục review cũ để file còn sót không gây **false positive**.

### 7.3. So sánh checksum

Trên Linux:

```bash
sha256sum build/dist/shop.war
```

Trên PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 build/dist/shop.war
```

Hash giúp định danh chính xác artifact đã được kiểm tra. Nếu sử dụng cùng một file WAR để triển khai staging/production, lưu hash lúc build và xác minh lại trước triển khai. Hai bản WAR có cùng file khi giải nén vẫn có thể khác hash do timestamp, thứ tự entry hoặc metadata của archive. Vì vậy hash khác không tự động nghĩa là Java code sai, nhưng khi dự án yêu cầu build tái lập thì sự khác biệt cần được điều tra.

## 8. Kiểm chứng runtime bằng servlet container

WAR hợp lệ về mặt ZIP chưa đủ để chứng minh ứng dụng khởi động được. Sau khi kiểm tra cấu trúc, triển khai `shop.war` lên một container tương thích với mã và descriptor.

Với ví dụ **Jakarta Servlet 6.0**, có thể dùng một Tomcat 10.1 trong môi trường thử nghiệm. Đặt artifact vào đúng vùng triển khai theo hướng dẫn của container; ví dụ với cấu hình mặc định của Tomcat, tên file `shop.war` thường tạo context path `/shop`.

Sau khi container triển khai thành công, thử:

```bash
curl -f http://localhost:8080/shop/hello
```

Kết quả mong đợi:

```text
HELLO_WAR
```

Với trang chủ:

```text
http://localhost:8080/shop/
```

Nếu Tomcat dùng cổng khác, có context path cấu hình riêng hoặc tự động triển khai bị tắt, URL và cách triển khai sẽ khác. Không nên đoán thành công từ một HTTP 200 ở URL không liên quan; hãy kiểm tra đường dẫn servlet và nội dung phản hồi.

**Các lớp xác minh nên tách biệt:**

| Kiểm tra | Điều nó chứng minh | Điều nó chưa chứng minh |
| --- | --- | --- |
| `ant war` trả exit code 0 | Ant tạo được archive | Container có thể nạp ứng dụng |
| `jar tf`/`inspect-war` | Các file quan trọng có trong WAR | Class/dependency và descriptor chạy đúng |
| Container triển khai không lỗi | Webapp được container nạp | Mọi chức năng nghiệp vụ đều đúng |
| `curl /shop/hello` trả kết quả mong đợi | Một đường đi servlet thực thi được | Toàn bộ API, DB, authentication và chức năng khác đều đúng |
| Integration/e2e test | Hành vi của ứng dụng theo phạm vi test | Những case chưa được viết test |

Với ứng dụng sản xuất, cần thêm log container, kiểm tra datasource, session, filters, security, context configuration và các integration test bắt buộc. Phần này thuộc kiểm chứng triển khai, bổ sung cho kiểm tra cấu trúc WAR.

## 9. Xử lý ứng dụng hiện hữu có JAR tại WEB-INF/lib

Dự án cũ thường đã có thư viện ngay dưới `src/main/webapp/WEB-INF/lib`. Có hai cách nhất quán:

**Cách A — quản lý dependency ở thư mục `lib/runtime`**, như `build.xml` mẫu:

```text
lib/runtime/
├── example-utils.jar
└── validation-library.jar
```

```xml
<lib dir="lib/runtime" includes="**/*.jar"/>
```

Cách này giúp phân biệt JAR container-provided khỏi JAR runtime của webapp, dễ đưa vào classpath compile và kiểm tra danh sách đầu ra.

**Cách B — giữ vị trí thư viện sẵn có trong webapp**, nếu đó là quy ước build chính thức. Khi dùng cách này, phải quyết định chỉ lấy một nguồn duy nhất:

```xml
<lib dir="src/main/webapp/WEB-INF/lib"
     includes="*.jar"/>
```

Khi đó vẫn phải loại `WEB-INF/lib/**` khỏi `<fileset dir="src/main/webapp">` để tránh gói mỗi JAR hai lần. Đồng thời compile classpath cũng phải trỏ đến đúng thư mục ấy. Đừng dùng cả hai cách nếu sẽ tạo cùng đường dẫn `WEB-INF/lib/foo.jar`.

Nếu các JAR được quản lý bằng Ivy hoặc hệ thống dependency khác, một bước resolve/copy có thể đưa dependencies runtime vào staging folder. Hãy lưu phiên bản và checksum dependency, và đảm bảo không mang các thư viện compile-only, test-only hoặc API do container cung cấp vào WAR.

## 10. Web descriptor, annotations và sự khác biệt khi nâng servlet container

### 10.1. `web.xml` có bắt buộc không?

Với các ứng dụng cũ, `web.xml` thường giữ các mapping và cấu hình quan trọng. Với các phiên bản Servlet hiện đại, annotation như `@WebServlet` có thể khai báo servlet; có thể đóng gói WAR mà không có descriptor nếu cấu hình ứng dụng cho phép.

Tuy nhiên, ứng dụng thực tế có thể dùng `web.xml` để:

- Khai báo servlet và `url-pattern`.
- Khai báo filter, listener và thứ tự filter.
- Định nghĩa trang lỗi, session, bảo mật hoặc welcome-file.
- Đặt context-param hoặc cấu hình cần cho framework cũ.

Không tự xóa `web.xml` chỉ vì container hỗ trợ annotation. Việc di trú từ descriptor sang annotation cần xác nhận hành vi tương đương và được kiểm thử như một thay đổi chức năng.

### 10.2. Khác biệt `javax.servlet` và `jakarta.servlet`

Nếu gặp:

```text
java.lang.NoClassDefFoundError: javax/servlet/...
```

trên container Jakarta, hoặc lỗi thiếu `jakarta/servlet/...` trên container cũ, nhiều khả năng ứng dụng, thư viện/framework và container đang dùng **khác namespace**. Sao chép thêm một JAR Servlet API vào `WEB-INF/lib` không phải cách sửa bền vững. Cần chọn dòng container phù hợp hoặc di trú source/dependencies/descriptor theo tài liệu của nền tảng.

### 10.3. JSP, tag library và framework web

Với webapp dùng JSP, JSP compiler thường do container cung cấp. Nhưng các tag library hoặc framework (ví dụ JSTL hoặc thư viện riêng) có thể cần artifact tương thích, tùy nền tảng và bản phân phối container. Kiểm tra metadata, taglib URI, namespace và jar runtime cụ thể trước khi kết luận WAR đã đủ dependency.

Một bài kiểm tra cấu trúc không thể phát hiện mọi lỗi JSP compile tại runtime; vì vậy hãy gọi một trang JSP đại diện trên container thử nghiệm và theo dõi log.

## 11. Xử lý nhiều cấu hình phát hành: dev, test, prod

Không nên sửa trực tiếp file cấu hình nguồn giữa các lần build nếu cùng repository cần tạo WAR cho nhiều môi trường. Một cách đơn giản là chọn resource profile tại giai đoạn staging, chẳng hạn:

```text
config/
├── dev/app.properties
├── test/app.properties
└── prod/app.properties
```

Ví dụ bổ sung vào `build.xml`:

```xml
<property name="build.profile" value="dev"/>

<target name="profile-resources" depends="compile">
    <copy file="config/${build.profile}/app.properties"
          tofile="${classes.dir}/app.properties"
          overwrite="true"/>
</target>
```

Sau đó cần thiết kế lại dependency của target `war` để `profile-resources` chạy **trước** khi đóng gói, đồng thời tránh copy thêm một `app.properties` khác từ `src/main/resources`. Ví dụ lệnh:

```bash
ant -noinput -Dbuild.profile=test clean verify-war
```

Trong ứng dụng production, nên ưu tiên cấu hình ngoài WAR cho giá trị thay đổi theo triển khai, đặc biệt secret và endpoint môi trường. Nếu cố ý tạo WAR riêng cho từng profile, cần đặt tên artifact/metadata rõ ràng để không triển khai nhầm và bảo đảm từng profile được kiểm tra.

Trước khi dùng giá trị CLI vào đường dẫn, nên xác nhận profile thuộc danh sách cho phép, thay vì ghép một giá trị không được kiểm soát vào tên file nguồn.

## 12. Kiểm tra WAR tự động trong CI

Trong pipeline, thay vì chỉ chạy `ant war`, hãy dùng target:

```bash
ant -noinput clean verify-war
```

Exit code khác 0 khiến job thất bại nếu descriptor, servlet class, JSP, CSS hoặc tài nguyên classpath bị thiếu trong demo. Có thể bổ sung các bước:

1. Chạy unit test hoặc integration test trước khi đóng gói.
2. Kiểm tra đường dẫn entry bằng `jar tf` hoặc giải nén vào thư mục sạch.
3. Kiểm tra danh sách JAR trong `WEB-INF/lib` và xác nhận provided dependencies vắng mặt.
4. Dùng test hoặc parser kiểm tra descriptor XML và giá trị cần thiết.
5. Khởi chạy servlet container thử nghiệm và gọi HTTP smoke test.
6. Ghi checksum và lưu **chính WAR đã qua kiểm thử** để chuyển sang bước phát hành.

Ví dụ một job GitHub Actions đơn giản trên Ubuntu (minh họa, cần điều chỉnh chính sách toolchain):

```yaml
name: Verify WAR

on:
  push:
  pull_request:

jobs:
  build-war:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Install Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant

      - name: Verify WAR structure
        run: ant -noinput clean verify-war

      - name: Show WAR entries
        run: jar tf build/dist/shop.war

      - name: Upload checked WAR
        uses: actions/upload-artifact@v4
        with:
          name: shop-war
          path: build/dist/shop.war
          if-no-files-found: error
```

Ví dụ giả định file Servlet API đã được cung cấp theo quy trình quản lý dependency của dự án (không đưa sẵn một binary tùy ý vào repository). Với CI production, nên cài phiên bản Ant đã được kiểm soát, xác minh dependency và dùng action version/commit theo chính sách tổ chức. Tên `shop.war` phải khớp giá trị `app.name` trong build thực.

Nếu cần kiểm thử nhiều JDK hoặc hệ điều hành, CI có thể dùng matrix; nhưng với WAR được triển khai lên **một container mục tiêu**, phải có job tương thích với chính runtime đó. Khả năng biên dịch được trên JDK 21 không chứng minh WAR chạy tốt trên server chỉ cung cấp JDK 17.

## 13. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và hướng sửa |
| --- | --- | --- |
| `BUILD SUCCESSFUL` nhưng WAR thiếu servlet class | `<fileset>` chọn sai thư mục; quên `<classes>` | `jar tf`; xác nhận `WEB-INF/classes/com/.../*.class` |
| `ClassNotFoundException` khi deploy | Thiếu runtime JAR hoặc class đặt sai chỗ | Kiểm tra `WEB-INF/lib`, classpath, log container |
| `NoClassDefFoundError: javax/servlet/...` hoặc `jakarta/servlet/...` | Namespace Servlet API và container không khớp | Kiểm tra runtime container và source/dependency |
| `web.xml` xuất hiện hai lần | Vừa dùng `webxml` vừa đưa vào fileset | Exclude `WEB-INF/web.xml`, đặt `duplicate="fail"` |
| WAR chứa `servlet-api.jar` | Đưa compile/provided dependencies vào `<lib>` | Tách `lib/provided` và `lib/runtime` |
| JSP 404 dù nằm trong dự án | Sai gốc fileset hoặc đường dẫn JSP | Kiểm tra entry path và context URL |
| Servlet 404 nhưng deploy thành công | Mapping trong `web.xml`/annotation sai hoặc gọi sai context | Kiểm tra `/shop/hello`, descriptor và log |
| CSS/JS 404 | Đặt sai đường dẫn tương đối hoặc path khi chuyển context | Kiểm tra WAR và URL thực tế |
| File `app.properties` thiếu khi runtime | Copy vào gốc WAR thay vì classpath | Đặt ở `WEB-INF/classes/app.properties` |
| Sửa mã nhưng WAR vẫn cũ | Incremental compile, task copy hoặc archive không cập nhật | `ant clean verify-war`; so class và entry |
| Xóa class nguồn nhưng WAR vẫn còn class cũ | Thư mục classes không được dọn | Clean trước release; sửa quy trình xử lý stale output |
| Có hai JAR cùng chức năng hoặc nhiều version | Dependency bị copy từ hai nguồn | Tách nguồn runtime và kiểm kê `WEB-INF/lib` |
| Deploy lỗi vì JSP/taglib | Thư viện Jakarta/Javax hoặc TLD không tương thích | Log container; kiểm tra dependencies/namespace |
| WAR đúng trên máy A, lỗi trên CI | Khác JDK/Ant, file path, ký tự hoa/thường, dependency | Ghi toolchain; kiểm tra source root và thư viện |

### Cách tìm lỗi có hệ thống

Khi triển khai thất bại, làm theo thứ tự:

1. **Build:** xem lỗi đầu tiên của Ant và mã thoát; kiểm tra `javac`/`war` có chạy không.
2. **Archive:** dùng `jar tf` hoặc `inspect-war` xác nhận các entry thật sự tồn tại.
3. **Dependency:** so class và JAR trong `WEB-INF/classes`/`WEB-INF/lib` với danh sách dependency runtime yêu cầu.
4. **Descriptor:** kiểm tra servlet mapping, namespace, version và cấu hình web.
5. **Runtime:** đọc log container, xác nhận context path, JDK, Servlet API và thử HTTP endpoint.

Phân chia như vậy giúp phát hiện nguyên nhân ở đúng lớp. Ví dụ, nếu `HelloServlet.class` nằm đúng `WEB-INF/classes` nhưng server báo thiếu `jakarta.servlet.http.HttpServlet`, cần xem **container/API tương thích**, không tiếp tục sửa fileset của WAR.

## 14. Tình huống quan trọng khi ứng dụng thực tế phức tạp hơn demo

### 14.1. Có module hoặc JAR nội bộ

Nếu một module Java trong cùng repository phải được đóng gói làm dependency, cần xây module đó trước, đưa JAR của nó vào nguồn `runtime.lib.dir`, rồi mới chạy target `war`. Dùng `depends` để diễn đạt thứ tự:

```xml
<target name="war" depends="build-libraries,resources">
    <!-- Đóng gói thư viện nội bộ và ứng dụng -->
</target>
```

Đây là mẫu phụ thuộc, không phải target hoàn chỉnh; phải định nghĩa `build-libraries` trong dự án. Không giả định một JAR tạo từ module khác đã tồn tại từ lần build trước.

### 14.2. Có static bundle do frontend build

Nếu giao diện được tạo từ Vite/Webpack hoặc công cụ frontend khác, cần xác định thư mục output chính xác, ví dụ `frontend/dist/`, và đưa vào gốc WAR:

```xml
<fileset dir="frontend/dist" includes="**/*"/>
```

Task tạo frontend bundle phải chạy trước bước WAR. Cũng phải xử lý trùng đường dẫn nếu `src/main/webapp` đã có `index.html` hoặc asset cùng tên. Khi build frontend thay đổi, hãy kiểm tra đường dẫn base/public path của tài nguyên trong context web thực tế.

### 14.3. Có nhiều môi trường container

Một file WAR có thể chạy trên nhiều máy chủ tương thích, nhưng cần xem:

- Cùng namespace và phiên bản Servlet/Jakarta được hỗ trợ.
- Java runtime và thư viện server cung cấp.
- Cấu hình JNDI/datasource, session, security và resource nằm ngoài WAR.
- Các thư viện riêng của server hoặc annotation scanner.
- Quy định WAR exploded/unexploded và cách đặt context path.

Không nên giả định chỉ cần `jar tf` giống nhau là triển khai sẽ giống nhau trên mọi container.

### 14.4. Cần ký artifact hoặc tạo reproducible WAR

Nếu quy trình phát hành yêu cầu SHA-256 ổn định từ cùng đầu vào, cần xem:

- Timestamp của các entry trong ZIP/WAR, manifest và resource sinh tự động.
- Thứ tự entry, tên đường dẫn và encoding.
- Đầu vào có byte giống nhau hay không, kể cả file frontend và dependency.
- Phiên bản Ant, JDK và cách nén.

Chỉ kiểm tra danh sách entry không đủ chứng minh hai WAR byte-identical. Ngược lại, khi bản build cố ý đổi cấu hình, checksum khác là điều bình thường; quan trọng là artifact được kiểm tra và lưu chính xác.

## 15. Bài tập mở rộng

**Bài 1 — Đóng gói ứng dụng có sẵn:** chọn một ứng dụng web Java hiện hữu, liệt kê thư mục nguồn Java, web root, classpath resource và các JAR runtime/provided. Viết bảng ánh xạ đầu vào sang vị trí trong WAR trước khi sửa `build.xml`.

**Bài 2 — Tạo WAR:** dùng target `war` để tạo archive, sau đó chạy `jar tf` và xác nhận `WEB-INF/classes`, `WEB-INF/lib` (nếu có runtime JAR), `WEB-INF/web.xml` và các trang web cần thiết.

**Bài 3 — Làm hỏng một entry có chủ đích:** tạm đổi tên hoặc bỏ qua file CSS/JSP của demo, chạy `ant clean verify-war` và quan sát target `inspect-war` thất bại. Khôi phục file trước khi tiếp tục.

**Bài 4 — Kiểm tra provided dependency:** đặt một JAR Servlet API vào compile classpath, xác nhận biên dịch thành công nhưng JAR ấy **không xuất hiện** dưới `WEB-INF/lib`. Nếu có, kiểm tra lại `<lib>` và các fileset.

**Bài 5 — Test trên container:** triển khai WAR lên container đúng phiên bản API. Gọi `/shop/hello` và `/shop/`; ghi status HTTP và nội dung phản hồi. Nếu không đạt, phân loại lỗi build/structure/runtime theo bảng mục 13.

**Bài 6 — Thử incremental:** sửa một file Java và resource rồi đóng gói lại; sau đó xóa/đổi tên một class và so kết quả incremental với clean build. Đề xuất cách dọn stale output trước release.

**Bài 7 — Tăng mức kiểm chứng:** bổ sung kiểm tra một JAR runtime bắt buộc, một cấu hình classpath và một endpoint nghiệp vụ, đưa các phép kiểm tra vào target CI để pipeline dừng khi WAR sai cấu trúc.

## 16. Ghi nhớ

Khi đóng gói một ứng dụng Java Web **đã tồn tại**, hãy bắt đầu từ cấu trúc nguồn và các dependency thực tế, rồi dùng `<war>` ánh xạ đúng vào layout WAR chuẩn:

- Nội dung web ở gốc WAR.
- `web.xml` ở `WEB-INF/web.xml` nếu ứng dụng cần descriptor.
- Java classes và resource classpath trong `WEB-INF/classes`.
- Thư viện runtime cần kèm ứng dụng trong `WEB-INF/lib`.
- Servlet API do container cung cấp chỉ nằm ở compile classpath, trừ khi có yêu cầu triển khai đặc biệt được tài liệu server cho phép.

Hãy kiểm tra archive **trước khi deploy** bằng `jar tf` hoặc `<unzip>` và các điều kiện `<fail>` trong Ant. Sau đó mới chứng minh tính tương thích runtime bằng container và HTTP smoke test. Hai lớp kiểm chứng bổ sung cho nhau: một WAR đúng cấu trúc là điều kiện cần, còn một WAR triển khai và hoạt động đúng mới là mục tiêu cuối cùng của bài thực hành.

## Tài liệu tham khảo

- [Apache Ant Manual — War Task](https://ant.apache.org/manual/Tasks/war.html): thuộc tính `webxml` và nested elements `<classes>`, `<lib>`, `<webinf>`.
- [Apache Ant Manual — Jar Task](https://ant.apache.org/manual/Tasks/jar.html): các thuộc tính đóng gói và metadata kế thừa từ JAR.
- [Apache Ant Manual — Javac Task](https://ant.apache.org/manual/Tasks/javac.html): biên dịch class, classpath, `release`.
- [Apache Ant Manual — Copy Task](https://ant.apache.org/manual/Tasks/copy.html): sao chép resource.
- [Apache Ant Manual — Unzip Task](https://ant.apache.org/manual/Tasks/unzip.html): kiểm tra archive qua giải nén.
- [Apache Ant Manual — Available Task](https://ant.apache.org/manual/Tasks/available.html), [Fail Task](https://ant.apache.org/manual/Tasks/fail.html): xác minh đường dẫn và dừng build khi sai.
- [Apache Tomcat 10.1 — Documentation](https://tomcat.apache.org/tomcat-10.1-doc/): servlet container và triển khai ứng dụng Jakarta.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): quy ước servlet và cấu trúc ứng dụng web.
