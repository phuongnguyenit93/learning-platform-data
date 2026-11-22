# `provided` và trách nhiệm cung cấp thư viện của môi trường chạy trong Maven

## 1. Mục tiêu và ý tưởng quan trọng nhất

Khi khai báo một thư viện trong `pom.xml`, Maven cần biết **thư viện đó được dùng ở giai đoạn nào**. Từ khóa `<scope>provided</scope>` nói với Maven rằng **dự án cần thư viện để biên dịch và kiểm thử, nhưng môi trường thực thi dự kiến sẽ tự cung cấp thư viện ấy**.

Ví dụ kinh điển là ứng dụng web dùng Servlet API:

- Bạn cần các class `jakarta.servlet.*` để biên dịch servlet.
- Khi triển khai WAR lên một **Servlet container tương thích**, container cung cấp Servlet API và phần triển khai xử lý HTTP.
- WAR thông thường không cần đóng gói thêm bản Servlet API của riêng ứng dụng vào `WEB-INF/lib`.
- Nếu chạy servlet trong môi trường **không có Servlet container tương thích**, việc khai báo `provided` **không làm API tự xuất hiện**.

Đây là một **hợp đồng về classpath và deployment**, không phải lệnh Maven tự cài thư viện lên server. Người đóng gói và người vận hành phải kiểm tra xem môi trường thực tế có cung cấp đúng API, phiên bản và khả năng triển khai hay không.

Sau bài này, bạn sẽ:

1. Hiểu sự khác nhau giữa `compile`, `provided`, `runtime` và `test`.
2. Biết lúc nào một dependency `provided` có mặt trên compile/test classpath nhưng không nằm trong runtime dependency classpath do Maven tính.
3. Phân biệt việc **Maven loại dependency khỏi runtime graph** với chuyện **JAR thông thường vốn không đóng gói dependency**.
4. Build được ví dụ Java 17 dùng một thư viện `provided` và tự bổ sung thư viện trên classpath khi chạy.
5. Viết một WAR dùng `jakarta.servlet-api` theo scope `provided` và hiểu hợp đồng với Servlet container.
6. Chẩn đoán `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` và các lỗi sai phiên bản/classloader thường gặp.
7. Biết khi nào **không nên** dùng `provided`.

Các phiên bản dependency/plugin phía dưới được ghim để ví dụ dễ theo dõi, không mang ý nghĩa phiên bản mới nhất. Phạm vi hướng dẫn là Java 17, Maven 3.x và project POM 4.0.0.

## 2. Hiểu scope bằng ba classpath

Maven xử lý dependency theo những ngữ cảnh khác nhau:

- **Compile classpath:** tập class và JAR dùng để biên dịch mã nguồn trong `src/main/java`.
- **Test classpath:** tập class và JAR dùng cho việc biên dịch và chạy test.
- **Runtime classpath:** tập thư viện Maven coi là cần thiết cho ứng dụng khi chạy, không tính những API mà môi trường được kỳ vọng cung cấp.

Với **dependency được khai báo trực tiếp**, có thể ghi nhớ bảng sau:

| Scope | Compile | Test | Runtime theo Maven | Trường hợp tiêu biểu |
| --- | :---: | :---: | :---: | --- |
| `compile` (mặc định) | Có | Có | Có | Thư viện mà mã nguồn cần cả khi build và chạy. |
| `provided` | Có | Có | **Không** | Servlet API do container cung cấp. |
| `runtime` | Không | Có | Có | Driver hoặc implementation chỉ cần khi chạy, mã chính không tham chiếu trực tiếp ở compile time. |
| `test` | Không | Có | Không | JUnit và công cụ chỉ dùng cho test. |

Bảng là mô hình cho **scope trực tiếp**; Maven còn có quy tắc về dependency graph, tính bắc cầu và mediation. Nó không khẳng định mỗi công cụ chạy Java đều tự nhận Maven runtime classpath.

### Vì sao `provided` vẫn có mặt khi test?

Khi viết code tham chiếu tới một API do server cung cấp, trình biên dịch Java vẫn phải kiểm tra kiểu, phương thức và chữ ký của API đó. Test của bạn cũng thường cần biên dịch, thậm chí giả lập API. Vì vậy Maven cho dependency `provided` tham gia **compile và test classpath**.

Nhưng đến lúc ứng dụng chạy trong môi trường mục tiêu, Maven **không đưa dependency `provided` vào tập runtime dependencies**. Nếu môi trường không cung cấp nó, chương trình có thể lỗi khi nạp class hoặc gọi phương thức cần thư viện.

**Lưu ý:** `provided` nghĩa là **“tôi kỳ vọng có thư viện này ở runtime”**, không phải **“Maven bảo đảm thư viện có sẵn ở runtime”**.

## 3. Cú pháp khai báo `provided`

Một dependency trong POM được khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>6.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

Ý nghĩa:

- `groupId`, `artifactId`, `version` xác định **artifact** Maven tải về.
- `scope=provided` quyết định **ngữ cảnh sử dụng dependency** trong dự án.
- Maven vẫn tải JAR về repository cục bộ khi cần biên dịch hoặc kiểm thử; `provided` **không** có nghĩa Maven bỏ qua việc tải dependency.
- Maven **không** tự sao chép JAR lên Tomcat/Jetty/server chỉ vì bạn dùng `provided`.
- Bạn phải dùng đúng artifact và version phù hợp với **API thực sự do runtime cung cấp**.

Nếu bạn không viết `<scope>`, scope mặc định của một dependency trực tiếp thường là `compile`, chứ không phải `provided`.

### Không nhầm `provided` với thuộc tính `optional`

`<optional>true</optional>` và `<scope>provided</scope>` giải quyết hai câu hỏi khác nhau:

- `provided`: dependency cần cho **classpath của project hiện tại** ở compile/test nhưng bị loại khỏi runtime graph thông thường; dependency này cũng không được truyền bắc cầu tới downstream consumer theo cơ chế scope của Maven.
- `optional=true`: dependency có thể được project hiện tại sử dụng theo scope khai báo, nhưng Maven **không tự truyền nó** như dependency bắc cầu bắt buộc tới project sử dụng thư viện.

Ví dụ một thư viện tích hợp với API server có thể vừa có sự cân nhắc về `provided`, vừa có yêu cầu tài liệu cho consumer. Không xem hai thẻ là từ đồng nghĩa và không thay một thẻ bằng thẻ kia tùy tiện.

## 4. Scope không giống cách đóng gói JAR

Đây là chỗ nhiều người hiểu sai.

Với Maven JAR Plugin thông thường, `mvn package` tạo một **JAR chứa class và resources của dự án**. Nó **không tự gộp mọi JAR dependency vào bên trong** chỉ vì dependency có scope `compile`.

Ví dụ:

~~~text
target/demo-1.0.jar
├── META-INF/MANIFEST.MF
└── com/example/App.class
~~~

Ngay cả dependency `compile` cũng có thể không có file `lib.jar` được nhét vào JAR này. Mã Java chạy bằng `java -cp demo.jar com.example.App` vẫn cần các JAR phụ thuộc trên classpath nếu có dùng chúng.

Vì vậy cần phân biệt:

1. **Maven scope:** dependency thuộc những tập compile/test/runtime nào.
2. **Packaging plugin:** plugin thực tế copy/gộp những thư viện nào vào artifact.
3. **Application launcher:** command, script, framework hoặc container nào lập ra runtime classpath thực tế.
4. **Deployment environment:** server/OS/image/runtime nào sẵn có các lớp hoặc implementation cần thiết.

Trong **WAR truyền thống**, Maven WAR Plugin thường copy dependency phù hợp vào `WEB-INF/lib`, còn dependency `provided` bị loại khỏi vị trí này; đây là tình huống thể hiện tác dụng của `provided` rất trực quan.

Với **fat JAR, shaded JAR, executable WAR, Spring Boot repackaging** hay plugin riêng, quy tắc đóng gói có thể khác. Phải đọc chính cấu hình plugin và kiểm tra file thật, không chỉ nhìn scope rồi đoán.

## 5. Ví dụ Java 17: thư viện `provided` phải được cung cấp khi chạy CLI

Ta chọn Apache Commons Lang để nhìn rõ sự khác nhau giữa compile time và runtime. Trong ví dụ này, **ta cố ý** đánh dấu Commons Lang là `provided` để mô phỏng một **môi trường vận hành cam kết có sẵn thư viện**. Đây là bài học về cơ chế; **với ứng dụng CLI độc lập thực tế**, thông thường nên chọn `compile` nếu không có cơ chế cung cấp thư viện từ bên ngoài.

Cấu trúc:

~~~text
provided-cli-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── App.java
~~~

### 5.1. POM hoàn chỉnh

Tạo `provided-cli-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>provided-cli-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
            <scope>provided</scope>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm cần kiểm tra:

- Dự án build Java 17 bằng compiler plugin tương thích.
- Commons Lang `3.14.0` nằm trên classpath khi **compile** vì `provided` bao gồm compile scope.
- Commons Lang không nằm trong **runtime dependency set** của Maven.
- `jar` packaging thông thường không tự đóng gói thư viện Commons Lang vào JAR, dù dùng scope nào.

### 5.2. Tệp Java chạy được

Tạo `src/main/java/com/example/App.java`:

~~~java
package com.example;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String value = StringUtils.capitalize("maven");
        System.out.println("Hello " + value + "!");
    }
}
~~~

`StringUtils.capitalize("maven")` trả về `"Maven"`, do đó stdout khi chạy **với đầy đủ classpath** là:

~~~text
Hello Maven!
~~~

Nếu thử `javac` độc lập, bạn cũng phải thêm Commons Lang vào compile classpath; `javac` không tự đọc `pom.xml`. Khi dùng Maven, cơ chế dependency resolution sẽ cung cấp artifact theo POM.

### 5.3. Build thành công không đồng nghĩa runtime đủ thư viện

Từ thư mục `provided-cli-demo`, chạy:

~~~bash
mvn clean package
~~~

Giả sử Maven tải được dependency và plugin, build thành công và tạo:

~~~text
target/
├── classes/com/example/App.class
└── provided-cli-demo-1.0-SNAPSHOT.jar
~~~

Sau đó cố ý chỉ dùng classpath của ứng dụng, **không thêm Commons Lang**:

~~~bash
java -cp target/classes com.example.App
~~~

Lúc JVM chạy tới lời gọi `StringUtils.capitalize(...)`, việc nạp/liên kết lớp phụ thuộc có thể thất bại, thường có lỗi kiểu:

~~~text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
~~~

Đây chỉ là **dòng lỗi nhận diện**, không phải toàn bộ stack trace bắt buộc vì đường dẫn stack trace tùy JVM/class. Chương trình không in `Hello Maven!` trong tình huống thiếu class đó.

**Phân tích chính xác:** lệnh `java -cp target/classes` tự chọn classpath quá ít. Thậm chí một dependency `compile` cũng không tự xuất hiện khi dùng Java launcher trực tiếp mà không thêm JAR. Ví dụ này minh họa việc **runtime phải có JAR**; điểm đặc trưng của `provided` là Maven **không coi dependency đó thuộc runtime dependency graph**, trong khi Maven có thể cung cấp nó ở compile/test.

### 5.4. Cung cấp thư viện từ bên ngoài khi chạy

Maven thường tải Commons Lang về local repository mặc định ở:

~~~text
~/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
~~~

Nếu bạn có custom `localRepository` hoặc thay `maven.repo.local`, cần lấy đúng đường dẫn thực tế. Đây là file dependency **đã được tải**, không phải bản copy bên trong JAR của ứng dụng.

**Bash trên Linux/macOS** (classpath separator là dấu `:`):

~~~bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" com.example.App
~~~

**PowerShell trên Windows** (classpath separator là dấu `;`):

~~~powershell
java -cp "target\classes;$env:USERPROFILE\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" com.example.App
~~~

**Stdout chính xác khi đúng JAR có mặt:**

~~~text
Hello Maven!
~~~

Mã `App` và file `App.class` **không thay đổi** giữa hai lần chạy. Khác biệt là **runtime classpath**. Đây là trách nhiệm mà ứng dụng hoặc môi trường triển khai phải giải quyết khi chọn `provided`.

Đối với ứng dụng không được một container hoặc launcher đặc biệt quản lý, bạn có thể cần một script khởi động cấu hình classpath và thư mục `lib/`, hoặc chọn scope phù hợp hơn để hệ thống đóng gói dependency. Không nên coi đường dẫn cache `~/.m2` là một yêu cầu production: server triển khai thực tế có thể không cài Maven hay có local repository.

### 5.5. Nếu muốn kiểm tra trực tiếp bằng `javac`

Đây là **cách thủ công riêng** cho Bash, không chạy Maven:

~~~bash
javac --release 17 \
  -cp "$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" \
  -d manual-classes src/main/java/com/example/App.java

java -cp "manual-classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" com.example.App
~~~

Lệnh trên giả định Commons Lang JAR đã được tải từ `mvn package` và path mặc định tồn tại. Stdout của lệnh Java vẫn là `Hello Maven!`. Nếu bỏ `-cp` của `javac` khi biên dịch, compiler sẽ không tìm được `org.apache.commons.lang3.StringUtils`. Điều này giải thích vì sao `provided` vẫn phải có trên **compile classpath**.

## 6. Kiểm tra scope bằng Maven thay vì suy luận từ lỗi runtime

Trong dự án CLI, lệnh sau in dependency tree:

~~~bash
mvn dependency:tree
~~~

Bạn cần tìm dependency trực tiếp tương tự:

~~~text
com.example:provided-cli-demo:jar:1.0-SNAPSHOT
\- org.apache.commons:commons-lang3:jar:3.14.0:provided
~~~

Đây là **đoạn minh họa đã lược bỏ tiền tố log**; cấu trúc hiển thị có thể khác tùy Maven Dependency Plugin.

Nếu chỉ muốn xem phần liên quan:

~~~bash
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Để kiểm tra model POM hiệu lực:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Trong file sinh ra, tìm `<dependency>` có `artifactId=commons-lang3` và `<scope>provided</scope>`. POM hiệu lực giúp xem kết quả kế thừa/property/profile, nhưng **không chứng minh server production đã có thư viện**.

### Phải kiểm tra cả Maven classpath và runtime thật

Một cách kiểm chứng đáng tin cậy:

1. **Compile:** `mvn compile` có thành công với lớp tham chiếu tới dependency `provided` không?
2. **Model:** `mvn dependency:tree` có hiển thị scope `provided` như dự kiến không?
3. **Packaging:** `jar tf ...` hoặc `jar tf ...war` có chứa nội dung nào?
4. **Runtime:** process thật được launch với classpath/module path/classloader nào? Container có cung cấp đúng API không?
5. **Compatibility:** runtime có bản API và implementation tương thích với bản đã biên dịch không?

Lưu ý `jar tf target/provided-cli-demo-1.0-SNAPSHOT.jar` **không thể tự chứng minh tác động đặc biệt của provided**: plain JAR thông thường không chứa dependency `compile` lẫn `provided`. Với WAR, `WEB-INF/lib` là điểm kiểm chứng trực quan hơn.

## 7. Ví dụ quan trọng nhất: Servlet API do web container cung cấp

Giả sử bạn viết một ứng dụng Jakarta Servlet để triển khai lên một **Servlet container tương thích với Jakarta Servlet 6.0**, ví dụ một cấu hình Tomcat 10.1 phù hợp. Code Java cần `jakarta.servlet.*` để compile, nhưng container phải cung cấp API tương thích và hệ thống xử lý request ở runtime.

Cấu trúc dự án:

~~~text
servlet-provided-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/web/HelloServlet.java
    │   └── webapp/
    │       └── index.html
    └── test/
        └── java/
~~~

Thư mục test không bắt buộc phải có test cho ví dụ này; nó chỉ minh họa bố cục Maven chuẩn.

### 7.1. POM WAR hoàn chỉnh

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>servlet-provided-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở đây:

- `<packaging>war</packaging>` chọn loại artifact phù hợp triển khai ứng dụng web Servlet.
- `jakarta.servlet-api:6.0.0` chứa các API mà compiler cần cho ví dụ.
- `provided` thể hiện việc container **phải cung cấp** API đó lúc chạy.
- `failOnMissingWebXml=false` cho phép ví dụ dùng annotation `@WebServlet` mà không cần tạo file `web.xml`; Servlet container vẫn phải hỗ trợ annotation scanning theo chuẩn tương ứng.
- POM chốt compiler và WAR plugin version chỉ để ví dụ dễ kiểm chứng.

### 7.2. Mã nguồn Servlet

Tạo `src/main/java/com/example/web/HelloServlet.java`:

~~~java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/hello")
public final class HelloServlet extends HttpServlet {
    private static final long serialVersionUID = 1L;

    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().println("Hello from the container!");
    }
}
~~~

Đây là một Servlet class hợp lệ khi compile với Jakarta Servlet API 6.0. Nó **không có phương thức `main`**; servlet được container khởi tạo và gọi `doGet` khi xử lý HTTP request theo mapping `/hello`.

### 7.3. Trang HTML tĩnh

Tạo `src/main/webapp/index.html`:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Servlet provided demo</title>
</head>
<body>
    <h1>Servlet provided demo</h1>
    <p>Send a GET request to /hello after deployment.</p>
</body>
</html>
~~~

Tệp này được đặt dưới webapp root để Maven WAR Plugin có nội dung web đưa vào WAR.

### 7.4. Build và kiểm tra WAR

Đứng tại thư mục `servlet-provided-demo`:

~~~bash
mvn clean package
jar tf target/servlet-provided-demo-1.0-SNAPSHOT.war
~~~

Khi build thành công, danh sách entry cần có những vị trí như:

~~~text
index.html
WEB-INF/classes/com/example/web/HelloServlet.class
~~~

**Bạn không nên thấy** `WEB-INF/lib/jakarta.servlet-api-6.0.0.jar` trong WAR thông thường của ví dụ này, vì dependency được khai báo `provided`. Có thể có entry metadata khác tùy Maven WAR Plugin.

Đừng sử dụng:

~~~bash
java -jar target/servlet-provided-demo-1.0-SNAPSHOT.war
~~~

rồi kỳ vọng Servlet tự chạy. WAR này **không phải executable WAR** có embedded server và `main`, mà được thiết kế để triển khai lên servlet container bên ngoài.

### 7.5. Ai thực sự cung cấp thư viện ở runtime?

**Container** chịu trách nhiệm cung cấp API/implementation Servlet theo chuẩn nó hỗ trợ, đồng thời thực hiện lifecycle:

1. Đọc và triển khai web application, quét annotation hoặc deployment descriptor.
2. Nạp các lớp ứng dụng từ `WEB-INF/classes` và thư viện cần thiết trong `WEB-INF/lib`.
3. Tạo servlet instance và gọi lifecycle methods.
4. Tiếp nhận HTTP request rồi gọi `doGet` trên servlet phù hợp.
5. Quản lý session, context, request/response và tài nguyên liên quan.

Nếu WAR được triển khai đúng tại context path `/servlet-provided-demo`, truy cập:

~~~text
http://localhost:8080/servlet-provided-demo/hello
~~~

có thể nhận response body:

~~~text
Hello from the container!
~~~

**Đây là kết quả dự kiến có điều kiện**, không phải minh chứng server trên máy bạn đã thực sự chạy: port, context path, annotation scanning và deployment behavior phụ thuộc cấu hình container. Nếu deploy dưới root context, đường dẫn có thể là `/hello` thay vì có tiền tố tên WAR.

### Phân biệt Jakarta và Javax

Các API servlet cũ thường có package `javax.servlet.*`. Jakarta Servlet 5.0 trở lên dùng `jakarta.servlet.*`. Chúng **không phải hai cách viết tương đương của một class**.

- Code ví dụ dùng `jakarta.servlet.http.HttpServlet`.
- Container Tomcat 10.1 tương ứng với thế hệ Jakarta Servlet 6.0.
- Một container chỉ hỗ trợ `javax.servlet.*` như môi trường Tomcat 9 thông thường không thể được coi là tương thích chỉ vì cũng có “Servlet API”.

Nếu compile bằng một API mà container không cung cấp đúng package/version, ứng dụng có thể lỗi nạp class, verifier, method linkage hoặc deployment. **Không tùy tiện copy nhiều bản Servlet API vào WAR** để che một sự không tương thích của container; hãy chọn đúng runtime và dependency scope/API version.

## 8. Tại sao dùng `provided` cho Servlet API lại quan trọng?

Nếu đổi khai báo của `jakarta.servlet-api` từ `provided` thành `compile` trong WAR truyền thống, Maven WAR Plugin có thể đưa dependency API đó vào `WEB-INF/lib`. Khi đó trong cùng hệ thống có thể xuất hiện:

- Bản Servlet API do container cung cấp.
- Bản Servlet API được ứng dụng đóng gói bên trong WAR.

Kết quả không phải lúc nào cũng gây lỗi ngay: classloading phụ thuộc container, nhưng bạn đã tạo ra nguy cơ **xung đột classloader/API**, trùng library, hành vi phụ thuộc thứ tự classloading và vấn đề tương thích. Trong nhiều container, việc copy API của container vào ứng dụng là không cần thiết hoặc không được khuyến nghị.

`provided` thông báo rằng **API này thuộc trách nhiệm của môi trường triển khai**. Tuy nhiên:

- Nó không bắt container nâng version API.
- Nó không tự đảm bảo environment có implementation tương ứng.
- Nó không buộc mọi container dùng chính JAR `jakarta.servlet-api` của Maven Central.
- Nó không thay thế việc đọc tài liệu compatibility matrix của container.
- Nó không tự đưa thư viện vào classpath của một ứng dụng chạy bằng `java -cp` ngoài container.

Nếu container không có API phù hợp, giải pháp đúng có thể là **đổi container, chọn API version tương thích hoặc đổi mô hình triển khai** chứ không đơn giản đổi `provided` thành `compile`.

## 9. Những trường hợp nên và không nên dùng `provided`

| Tình huống | Có nên `provided`? | Lý do |
| --- | --- | --- |
| Servlet API trong WAR chạy trên Servlet container tương thích | **Thường có** | Container cung cấp API/implementation phù hợp. |
| API của một application server được máy chủ quản lý | **Thường có**, sau khi xác minh | Server quản lý library và lifecycle. |
| API do plugin host/platform cung cấp cho plugin được deploy | **Có thể**, nếu host có hợp đồng rõ ràng | Plugin code phải tương thích với version của host. |
| Thư viện Java thông thường trong ứng dụng CLI độc lập | **Thường không** | Không có runtime nào cam kết cung cấp nó; nên dùng scope `compile`/`runtime` và đóng gói/launcher đúng. |
| JDBC driver do một server container quản lý trong shared classloader | **Có thể**, tùy deployment | Chỉ dùng nếu server thực sự cung cấp đúng driver và datasource. |
| JDBC driver do ứng dụng tự đóng gói | **Không nên `provided`** | Ứng dụng chịu trách nhiệm mang driver vào runtime. |
| JUnit/TestNG chỉ phục vụ unit test | **Không**; dùng `test` | Không cần trong mã chính và runtime sản phẩm. |
| Dependency chỉ được nạp bằng reflection khi chạy | **Cân nhắc `runtime`** | Mã chính không cần API dependency ở compile, nhưng ứng dụng cần JAR lúc chạy. |
| Java Standard Library (`java.base`, `java.sql`) | **Không cần dependency Maven cho phần chuẩn JDK** | JDK/JRE tương thích đã cung cấp module chuẩn; không dùng `provided` để mô tả class Java SE thông thường. |

### Một số câu hỏi cần trả lời trước khi chọn scope

1. **Ai cung cấp library lúc chạy?** Tên container, image base, host application, plugin platform hoặc runtime launcher cụ thể?
2. **Phiên bản nào được bảo đảm?** Có compatibility matrix và quy trình kiểm thử không?
3. **Classloader nào nạp API?** Bootstrap/platform classloader, container classloader, webapp classloader hay launcher riêng?
4. **Ứng dụng có thể chạy độc lập không?** Nếu có, phải làm sao để dependency xuất hiện đúng classpath?
5. **Có cần dependency tới consumer tiếp theo không?** `provided` không truyền dependency bắc cầu cho downstream.
6. **Artifact nào được đóng gói?** Plain JAR, WAR, shaded JAR hay executable archive? Cần kiểm tra thực tế.

Nếu không có câu trả lời cho câu (1), rất có thể bạn **chưa đủ cơ sở** để dùng `provided`.

## 10. Tính bắc cầu: `provided` không tự được chuyển cho consumer

Giả sử bạn có:

~~~text
application
    └── library-a
            └── api-x (provided)
~~~

Nếu `library-a` khai báo `api-x` với scope `provided`, Maven **không tự thêm `api-x` như một dependency bắc cầu của `application`** trong đồ thị dependency thông thường.

Điều này phù hợp với giả định rằng một **runtime host** riêng đang cung cấp API, nhưng có thể làm một consumer không biết phải chuẩn bị môi trường gì. Vì vậy thư viện sử dụng API `provided` nên:

- Tài liệu hóa môi trường host và version API hỗ trợ.
- Không giả định consumer tự nhận được JAR API qua dependency transititivity.
- Cho biết khi nào consumer cần khai báo API trực tiếp để compile.
- Có integration test thực sự với host hoặc runtime phù hợp.
- Xác định rõ trường hợp cùng lớp API được nạp bởi host và app classloader.

Ví dụ cụ thể: một thư viện được biên dịch với Servlet API `provided` nhưng app khác phụ thuộc thư viện đó ở ngoài Servlet container; việc “có thư viện-a” chưa đủ để nạp mọi kiểu `jakarta.servlet.*`. Consumer cần runtime API phù hợp hoặc phải đổi kiến trúc.

### Phân biệt `dependencyManagement` với declaration

Nếu đặt version/scope của một dependency trong `<dependencyManagement>` mà **không khai báo dependency trong `<dependencies>`**, Maven không tự thêm JAR đó vào classpath của project. `dependencyManagement` quản lý các dependency **khi chúng được dùng**, không có nghĩa mọi mục trong danh sách đều được nạp.

Trong một reactor nhiều module, mỗi module vẫn có dependency graph và packaging riêng. Scope trong module WAR không tự áp dụng cho mọi module Java khác, trừ khi được khai báo/kế thừa/quản lý theo quy tắc POM phù hợp. Luôn kiểm tra effective POM và dependency tree tại **đúng module**.

## 11. Test thành công nhưng production lỗi: vì sao có thể xảy ra?

Một module Java có dependency `provided` có thể:

- Biên dịch mã chính thành công.
- Biên dịch test thành công.
- Chạy unit test thành công vì **test classpath có dependency provided**.
- Đóng gói JAR/WAR thành công.
- Thất bại khi triển khai vì **runtime host thiếu JAR hoặc API không tương thích**.

Đây không phải Maven mâu thuẫn, mà đúng với giả định của scope. Test ở môi trường build **không chứng minh** deployment host đã cung cấp đúng class.

Do đó cần cả:

1. **Unit test**: kiểm tra logic trong classpath của build/test.
2. **Integration test với runtime thực**: triển khai WAR hoặc plugin vào đúng container/host được hỗ trợ và gọi các chức năng liên quan.
3. **Compatibility tests** nếu hỗ trợ nhiều version host/API.
4. **Deployment validation**: kiểm tra container, image, shared libraries và logs startup.
5. **Observability**: thông báo lỗi rõ ràng nếu API hoặc version thiếu, thay vì “bịt” bằng classpath tuỳ hứng.

Không nên chữa lỗi production bằng cách đổi ngay `provided` thành `compile` mà chưa hiểu server đang cung cấp API nào.

## 12. Các lỗi runtime liên quan `provided`

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `ClassNotFoundException: ...` | Runtime classloader không tìm được class theo tên được nạp động. | Xác nhận JAR/API trên runtime classpath/host và package name. |
| `NoClassDefFoundError: ...` | Một class cần khi runtime không được tìm thấy/khởi tạo được hoặc dependency của nó không có. | Xem nguyên nhân gốc, classpath, host libraries và nested causes. |
| `NoSuchMethodError` | Compile với API có method nhưng runtime dùng class version không có method tương ứng. | So version API lúc compile với class thật được nạp ở runtime. |
| `NoSuchFieldError` | Binary API mismatch giữa bản compile và bản runtime. | Kiểm tra version, dependency mediation và classloader. |
| `ClassCastException` dù tên class trông giống nhau | Class được nạp từ classloader khác nhau, hoặc API/protocol không tương thích. | Quan sát classloader và runtime host; tránh hai bản API trùng. |
| `UnsupportedClassVersionError` | JVM runtime quá cũ so với bytecode Java đã build. | So `maven.compiler.release`, `mvn --version`, `java -version` trên server. |
| WAR deploy thất bại nhưng unit tests đều xanh | Test classpath khác container runtime. | Chạy integration test trên container thật, xem deployment logs. |
| `javax.servlet.*` không được tìm thấy trên Tomcat 10+ | Ứng dụng dùng Servlet API namespace cũ, container hỗ trợ Jakarta namespace mới. | Kiểm tra compatibility, source imports và migration requirements. |
| JAR độc lập lỗi khi dùng `java -cp app.jar` | Launcher không có dependency JAR trên classpath. | Cấu hình đầy đủ classpath hoặc dùng quy trình packaging phù hợp. |
| `mvn compile` lỗi không tìm được lớp của `provided` | Dependency chưa được tải, tọa độ/version sai, scope bị loại bởi profile hoặc project chưa khai báo. | Xem `dependency:tree`, repositories, effective POM, compiler log. |
| Xung đột khi đóng gói Servlet API vào WAR | Trùng library với container, classloader order hoặc version mismatch. | Kiểm tra `WEB-INF/lib` và chính sách container. |

### Hai lỗi dễ bị trộn lẫn

- **`ClassNotFoundException`** là checked exception thường phát sinh khi thao tác nạp class theo tên, ví dụ `Class.forName(...)` hoặc cơ chế của framework.
- **`NoClassDefFoundError`** là `Error` liên quan nạp/khởi tạo class ở runtime. Nó có thể có nguyên nhân sâu hơn là một lỗi initialization trước đó, không chỉ thiếu JAR.

Không kết luận mọi `NoClassDefFoundError` đều do `provided`; cần xem đầy đủ cause, dependency graph, classpath và classloader thực tế.

## 13. Cách chẩn đoán theo thứ tự có thể kiểm chứng

Khi gặp lỗi liên quan library runtime, hãy làm theo trình tự:

### Bước 1 — Xác nhận scope và tọa độ

~~~bash
mvn dependency:tree
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Kiểm tra dependency được khai báo ở đúng module, đúng version, đúng scope. Nếu Maven Help/Dependency Plugin chưa nằm trong cache, lệnh có thể cần truy cập repository để tải plugin.

### Bước 2 — Phân biệt artifact loại nào

- **Plain JAR:** dùng `jar tf` xem class/resource có trong JAR; không suy ra dependency được tự đóng gói.
- **WAR:** xem `WEB-INF/classes` và `WEB-INF/lib`, đặc biệt sự có mặt hoặc vắng mặt của những API container dự kiến cung cấp.
- **Fat JAR/executable archive:** kiểm tra chính quy tắc của Shade/Assembly/Spring Boot Plugin vì chúng có thể khác plain JAR và WAR truyền thống.

Ví dụ:

~~~bash
jar tf target/servlet-provided-demo-1.0-SNAPSHOT.war
~~~

### Bước 3 — Xác nhận runtime thật

Thu thập các thông tin không nhạy cảm:

~~~bash
java -version
~~~

Và từ tài liệu/quản trị runtime: phiên bản Servlet container, danh sách API được cung cấp, vị trí shared libraries, deployment context và classloader policy. Đừng chạy `java -version` trên máy build rồi suy ra server production có cùng JDK.

### Bước 4 — So version compile/runtime

Nếu compile bằng API Servlet 6.0 nhưng runtime chỉ cung cấp phiên bản cũ hoặc namespace `javax.servlet`, đừng hy vọng Maven scope tự chuyển đổi bytecode. Cần chọn version tương thích hoặc migration rõ ràng.

### Bước 5 — Chạy test tích hợp

Triển khai chính artifact lên môi trường tương tự production và chạy request/test thực. Phân biệt test với mock/stub API trong Maven test classpath và test trên host thực tế.

### Bước 6 — Sửa đúng nơi chịu trách nhiệm

Nếu runtime **cam kết cung cấp** API nhưng thiếu: sửa cấu hình/phiên bản runtime hoặc deployment. Nếu runtime **không cung cấp** mà app cần JAR: xem xét lại lựa chọn `provided`, cách package, launcher và tài liệu triển khai. Đừng tạo dependency duplicate hoặc thay scope bừa bãi khi chưa biết cơ chế.

## 14. Một số bẫy quan trọng trong môi trường thực tế

### 14.1. Docker container không tự trở thành “Servlet container”

Từ “container” dễ gây nhầm:

- **Docker/OCI container** là môi trường đóng gói và chạy process; một image chỉ chứa JRE và app JAR **không tự có Servlet API/Servlet container**.
- **Servlet container** như Tomcat/Jetty là thành phần xử lý Servlet API/lifecycle.
- Một Docker image **có Tomcat** được cấu hình đúng có thể cung cấp Servlet API; một image `eclipse-temurin:17-jre` đơn thuần không tự làm điều đó.

Phải nhìn **nội dung image và process khởi động**, không dựa vào tên “container”.

### 14.2. Plugin platform khác JVM tiêu chuẩn

Nếu viết plugin cho một phần mềm host, API do host cung cấp có thể phù hợp với `provided`. Nhưng host API version khác nhau có thể tạo lỗi linkage; phụ thuộc host cần được tài liệu hóa và kiểm thử. Không phải vì host chạy trên JVM mà tất cả dependency Java của plugin đã được cung cấp.

### 14.3. Cùng groupId/artifactId chưa chắc là cùng binary API

Runtime có thể có một thư viện cùng tên nhưng khác version. Java classloader nạp **class thực tế**, không kiểm tra tọa độ Maven như một nguồn sự thật tại runtime. `NoSuchMethodError` và `LinkageError` có thể xảy ra nếu bytecode của bạn dựa trên API mới hơn bản trên server.

### 14.4. Không sao chép thư viện vào nơi “thấy dùng được” mà bỏ qua quản trị

Với server production, thêm JAR vào thư mục shared/lib có thể ảnh hưởng tất cả ứng dụng, tạo rủi ro bảo mật và thay đổi hành vi classloader. Chỉ làm khi hệ thống vận hành hỗ trợ, có kiểm soát thay đổi và version được xác nhận.

### 14.5. Các dependency khác đi kèm API

Một dependency `provided` có thể còn có dependency phụ của chính nó, nhưng provided scope ảnh hưởng cơ chế lan truyền và classpath; nó **không thay thế việc xác minh runtime đầy đủ**. Nếu host chỉ cung cấp một class API mà thiếu implementation hoặc một module khác, chương trình vẫn có thể lỗi. Trong ứng dụng web, API Servlet được cung cấp bởi container và implementation của container, không phải chỉ một file Maven JAR đặt tên `servlet-api`.

## 15. Checklist chọn scope và triển khai

Trước khi gắn `<scope>provided</scope>` vào dependency, xác nhận:

- [ ] Tôi chỉ ra được **host/container/launcher cụ thể** có trách nhiệm cấp API/JAR lúc chạy.
- [ ] Tôi biết **version, namespace và binary compatibility** được host hỗ trợ.
- [ ] Tôi hiểu dependency hiện diện trong compile/test nhưng không mặc định trong Maven runtime graph.
- [ ] Tôi đã kiểm tra **kiểu artifact** (JAR/WAR/fat archive) và quy tắc packaging plugin.
- [ ] Nếu là WAR truyền thống, API do container cung cấp không bị copy nhầm vào `WEB-INF/lib`.
- [ ] Nếu là ứng dụng standalone, launcher hoặc deployment image tạo **runtime classpath đầy đủ**.
- [ ] Tôi không dựa vào provided dependencies như transitive dependency bắt buộc cho downstream consumer.
- [ ] Unit test và integration test được phân biệt; có ít nhất một kiểm chứng với runtime thực tế.
- [ ] Không có token/password/secret trong artifact hoặc log dùng để debug.
- [ ] Build profile, JDK, version Maven và runtime host đã được ghi lại để tái hiện lỗi.

Nếu một điều kiện quan trọng chưa được xác nhận, hãy ghi rõ giới hạn và kiểm tra môi trường trước khi triển khai.

## 16. Bài tập thực hành

### Bài A — CLI dependency `provided`

1. Tạo project `provided-cli-demo` với POM và `App.java` ở mục 5.
2. Chạy `mvn clean package`, kiểm tra có JAR trong `target`.
3. Chạy `java -cp target/classes com.example.App` mà không có Commons Lang và nhận diện lỗi nạp class.
4. Thêm Commons Lang đúng version vào classpath và kiểm tra stdout chính xác `Hello Maven!`.
5. Chạy `mvn dependency:tree` và tìm `commons-lang3:jar:3.14.0:provided`.
6. Giải thích tại sao plain JAR không chứa Commons Lang **không tự nó chứng minh** rằng `provided` khác `compile`.

### Bài B — WAR và Servlet container

1. Tạo `servlet-provided-demo` với POM, `HelloServlet.java` và `index.html` ở mục 7.
2. Chạy `mvn clean package` và dùng `jar tf` liệt kê các entry.
3. Kiểm tra servlet class có ở `WEB-INF/classes`, còn API `jakarta.servlet-api` không nằm trong `WEB-INF/lib`.
4. Chọn Servlet container có Jakarta Servlet API tương thích. Nêu lý do cần đối chiếu version **trước khi** deploy.
5. Nếu có môi trường container thực hành, triển khai WAR, gọi endpoint `/hello` theo context path thực tế và kiểm tra HTTP response body.
6. Giải thích vì sao một servlet không có `main` không thể được chạy như ứng dụng Java CLI chỉ bằng `java -jar`.

### Bài C — Tư duy tình huống

- Một ứng dụng CLI dùng Commons Lang và không có launcher cấp thư viện ngoài. Nên giữ `provided` hay đổi thiết kế đóng gói/scope?
- Một WAR dùng `jakarta.servlet-api`, nhưng server chỉ hỗ trợ `javax.servlet`. Có thể “sửa” chỉ bằng đổi scope sang `compile` hay không?
- Unit test pass nhưng production có `NoSuchMethodError`. Bạn sẽ so API version, classloader và artifact thực tế thế nào?
- Project A khai báo API X là `provided`, project B phụ thuộc A. B có thể mặc định coi API X là transitive dependency được tải không?
- Khi nào cần đổi **runtime host**, khi nào nên đổi **scope/launcher**, và khi nào cần sửa **mã nguồn**?

### Câu hỏi tự đánh giá

1. `provided` có trên compile classpath không? Test classpath không? Runtime dependency set theo Maven không?
2. Maven có tự chuyển dependency `provided` vào server khi bạn chạy `mvn package` không?
3. Vì sao một plain JAR có `compile` dependency vẫn có thể thiếu JAR đó khi `java -cp`?
4. WAR với Servlet API `provided` có nhiệm vụ đóng gói API này vào `WEB-INF/lib` không?
5. Cơ chế classloader và khác biệt `jakarta.servlet`/`javax.servlet` liên quan thế nào tới tương thích runtime?
6. `provided` có giống `optional` hoặc `test` không?
7. Vì sao `mvn test` thành công chưa đủ bảo đảm Servlet container triển khai được WAR?

## 17. Kết luận

**`provided` là một lời cam kết về phía môi trường chạy:** Maven cho phép sử dụng thư viện lúc **compile/test**, nhưng không coi nó là dependency phải đưa vào runtime dependency set như `compile`. Cấu hình đó phù hợp khi một Servlet container, application server hoặc plugin host **thực sự cung cấp API tương thích**.

Nó **không** tự cài đặt, sao chép hay nâng phiên bản thư viện trên server. Người thiết kế và vận hành phải đảm bảo runtime classpath/classloader, version/namespace, packaging và kiểm thử tích hợp phù hợp. Nếu không có host nào chịu trách nhiệm cung cấp thư viện, sử dụng `provided` cho dependency cần chạy thường là sai lựa chọn.

**Ghi nhớ:** *Build cần class để biên dịch; runtime cần class tương thích để thực thi; `provided` chuyển trách nhiệm cung cấp runtime API từ artifact sang môi trường triển khai.*

## Tài liệu chính thức

- Apache Maven — Dependency Mechanism (Dependency Scope): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Maven WAR Plugin: https://maven.apache.org/plugins/maven-war-plugin/
- Jakarta Servlet Specification: https://jakarta.ee/specifications/servlet/
- Apache Tomcat — Which Version: https://tomcat.apache.org/whichversion.html
