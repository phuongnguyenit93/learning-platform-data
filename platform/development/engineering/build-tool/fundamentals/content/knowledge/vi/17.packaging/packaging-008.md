# WAR và phạm vi sử dụng trong môi trường Servlet

WAR (Web Application Archive) là định dạng đóng gói một ứng dụng web Java để triển khai vào môi trường hỗ trợ Servlet, thường là servlet container hoặc application server. WAR chứa class đã biên dịch, web resource, thư viện ứng dụng và metadata cần thiết để container nạp ứng dụng, tạo web context và xử lý request HTTP.

WAR không đơn giản là một JAR đổi phần mở rộng. Một JAR thông thường thường đóng gói library hoặc Java application. WAR có cấu trúc và hợp đồng triển khai dành cho web application: container quản lý vòng đời ứng dụng, Servlet, filter, listener, session, mapping URL và một số dịch vụ web khác theo phiên bản nền tảng mà nó hỗ trợ.

Khi chọn WAR, cần xác định rõ ứng dụng sẽ chạy trong môi trường Servlet nào, container cung cấp những API nào, thư viện nào phải được đóng gói, và phiên bản Servlet/Jakarta EE nào tương thích. Đây là những yếu tố quyết định WAR có thể triển khai và chạy đúng hay không.

## 1. WAR được dùng để làm gì?

Một WAR thường được tạo khi ứng dụng web được triển khai lên một máy chủ có khả năng chạy Servlet. Ví dụ môi trường có thể là Apache Tomcat, Eclipse Jetty, Eclipse GlassFish, Payara hoặc một application server Jakarta EE phù hợp.

Ứng dụng web có thể gồm:

- Servlet xử lý HTTP request.
- Filter thực hiện xác thực, logging, CORS hoặc xử lý request/response.
- Listener theo dõi vòng đời web application hoặc session.
- Controller và thành phần framework như Spring MVC.
- HTML, CSS, JavaScript, ảnh và các web resource khác.
- Template hoặc view technology như JSP nếu container và cấu hình hỗ trợ.
- Thư viện ứng dụng cần thiết ở runtime.
- Cấu hình triển khai và metadata.

Container nhận WAR, triển khai nó thành một web application, khởi tạo context và cung cấp các dịch vụ Servlet. Khi request tới URL thuộc context đó, container chọn servlet/filter mapping phù hợp và điều phối việc xử lý.

### 1.1. WAR là một hợp đồng giữa ứng dụng và container

Ứng dụng được đóng gói thành WAR để container có thể hiểu cấu trúc và khởi tạo nó. Container thường chịu trách nhiệm:

- Nạp web application và tạo ServletContext.
- Quản lý vòng đời Servlet, Filter và Listener.
- Ánh xạ request tới servlet hoặc framework dispatcher.
- Quản lý HTTP session và các thành phần liên quan.
- Cung cấp Servlet API và một số dịch vụ nền tảng.
- Áp dụng cấu hình bảo mật và cấu hình web theo khả năng của container.
- Dừng ứng dụng và giải phóng tài nguyên khi undeploy hoặc shutdown.

Ứng dụng vẫn chịu trách nhiệm về logic nghiệp vụ, cấu hình ứng dụng, xử lý lỗi và quản lý tài nguyên do chính nó tạo ra. WAR không tự cung cấp một máy chủ HTTP độc lập. Nó cần môi trường triển khai có hỗ trợ Servlet.

### 1.2. WAR khác JAR như thế nào?

| Đặc điểm | JAR thông thường | WAR |
|---|---|---|
| Mục đích phổ biến | Java library hoặc application archive | Web application triển khai vào Servlet environment |
| Cấu trúc đặc trưng | Package class, resource, META-INF | WEB-INF, classes, lib và web resources |
| Thành phần runtime | Tùy loại JAR và cách chạy | Servlet container cung cấp Servlet runtime |
| Cách triển khai | Đưa vào classpath, module path hoặc chạy executable JAR | Deploy vào servlet container/application server |
| URL mapping, Servlet lifecycle | Không phải hợp đồng mặc định của JAR | Là phần cốt lõi của môi trường WAR |
| Thư viện Servlet API | Tùy cách dùng | Thông thường container cung cấp API tương ứng |

Một JAR có thể là thư viện được đặt trong WEB-INF/lib của WAR. WAR có thể chứa một application JAR hoặc nhiều thư viện, nhưng bản thân WAR là gói web application có cấu trúc riêng.

## 2. Cấu trúc bên trong một WAR

WAR là archive dựa trên định dạng ZIP. Một cấu trúc phổ biến:

~~~text
orders-web.war
├── index.html
├── assets/
│   ├── app.css
│   └── app.js
├── images/
│   └── logo.svg
└── WEB-INF/
    ├── web.xml
    ├── classes/
    │   ├── com/example/web/OrderServlet.class
    │   └── application.properties
    └── lib/
        ├── orders-domain.jar
        ├── spring-webmvc.jar
        └── json-library.jar
~~~

Không phải WAR nào cũng có đầy đủ các file trên. Ví dụ, web.xml có thể không cần thiết nếu ứng dụng dùng annotation hoặc cơ chế cấu hình khác được hỗ trợ. Thư mục WEB-INF/lib có thể không chứa dependency nếu ứng dụng dựa vào thư viện được container cung cấp hoặc dùng cấu trúc triển khai đặc thù.

### 2.1. Web resources ở root của WAR

Các file nằm ngoài WEB-INF thường có thể được phục vụ như web resource theo cấu hình container và ứng dụng.

Ví dụ:

~~~text
orders-web.war
├── index.html
├── css/
│   └── site.css
├── js/
│   └── site.js
└── images/
    └── logo.png
~~~

Nếu context path của ứng dụng là /orders, resource index.html có thể được truy cập qua URL tương ứng như /orders/index.html, tùy cấu hình welcome file và routing.

Không nên đặt secret, file cấu hình nội bộ hoặc dữ liệu không dành cho client ở root của WAR. Resource ở vị trí công khai có thể được container phục vụ qua HTTP.

### 2.2. WEB-INF/classes

WEB-INF/classes thường chứa class đã biên dịch của ứng dụng và resource trên classpath.

Ví dụ:

~~~text
WEB-INF/classes/
├── com/example/orders/OrderController.class
├── com/example/orders/OrderService.class
└── application.properties
~~~

Container và ứng dụng có thể nạp các class này thông qua classloader của web application. Resource như properties, XML hoặc template có thể được ứng dụng đọc từ classpath tùy framework.

Không nên chỉnh sửa trực tiếp class files bên trong WAR để sửa lỗi. Hãy sửa source hoặc build configuration rồi tạo lại artifact.

### 2.3. WEB-INF/lib

WEB-INF/lib chứa các thư viện JAR được đóng gói cùng web application.

Ví dụ:

~~~text
WEB-INF/lib/
├── orders-domain-1.4.0.jar
├── spring-context-....jar
└── jackson-databind-....jar
~~~

Các thư viện này thường được đưa vào classloader của web application theo cơ chế container. Chúng phục vụ ứng dụng khi chạy.

Một số API do container cung cấp, đặc biệt Servlet API, thường không nên được đóng gói lại trong WEB-INF/lib. Đóng gói phiên bản API khác với phiên bản container hỗ trợ có thể gây xung đột classloading hoặc lỗi tương thích.

### 2.4. WEB-INF/web.xml

web.xml là deployment descriptor của web application. Nó có thể khai báo:

- Servlet và servlet mapping.
- Filter và filter mapping.
- Listener.
- Welcome files.
- Session configuration.
- Error page.
- Security constraints.
- Context parameters và một số thiết lập web khác.

Ví dụ tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
    <servlet>
        <servlet-name>orders</servlet-name>
        <servlet-class>com.example.orders.OrderServlet</servlet-class>
    </servlet>

    <servlet-mapping>
        <servlet-name>orders</servlet-name>
        <url-pattern>/api/orders/*</url-pattern>
    </servlet-mapping>
</web-app>
~~~

Ví dụ trên minh họa descriptor cho Jakarta Servlet 6.0. Khi dùng phiên bản Servlet khác, namespace, schema và version phải khớp với nền tảng mục tiêu.

Từ Servlet 3.0 trở đi, annotation và programmatic registration có thể thay thế nhiều khai báo truyền thống trong web.xml. Việc có hay không có descriptor phụ thuộc cách ứng dụng cấu hình và yêu cầu của container.

### 2.5. META-INF và metadata khác

Một JAR bên trong WAR có thể chứa thư mục META-INF riêng. WAR cũng có thể có metadata hoặc file dành riêng cho container. Ví dụ, một số server hỗ trợ file context hoặc deployment descriptor mở rộng.

Cần phân biệt metadata chuẩn của web application với cấu hình riêng của một container. File đặc thù cho Tomcat hoặc một application server khác có thể làm WAR phụ thuộc vào nhà cung cấp đó. Nếu cần portability, hãy ưu tiên cấu hình chuẩn Servlet/Jakarta EE và tách phần cấu hình riêng của môi trường ra khỏi gói dùng chung khi có thể.

## 3. Servlet container làm gì khi triển khai WAR?

Một Servlet container là runtime thực hiện hợp đồng Servlet. Tomcat và Jetty thường được gọi là servlet container; các application server Jakarta EE có thể cung cấp Servlet cùng nhiều dịch vụ nền tảng khác.

Quy trình khái quát:

~~~mermaid
flowchart TD
    A["WAR được đưa vào container"] --> B["Container đọc archive và metadata"]
    B --> C["Tạo web application context"]
    C --> D["Nạp classes và libraries"]
    D --> E["Khởi tạo Servlet, Filter, Listener"]
    E --> F["Ứng dụng sẵn sàng nhận request"]
    F --> G["HTTP request đến context"]
    G --> H["Filter chain và servlet/framework"]
    H --> I["HTTP response"]
    I --> J["Undeploy hoặc shutdown"]
    J --> K["Destroy components và giải phóng tài nguyên"]
~~~

Các bước thực tế phụ thuộc container, cấu hình, descriptor, annotation và framework. Một số thành phần được khởi tạo khi deploy; một số Servlet có thể được khởi tạo lần đầu khi có request nếu cấu hình lazy initialization.

### 3.1. Web application context

Mỗi WAR được triển khai thường tạo một web application context riêng. Context có ServletContext, cấu hình, classloader và các thành phần thuộc ứng dụng.

Container có thể gán context path dựa trên tên WAR, cấu hình deploy hoặc quy tắc của server. Ví dụ, WAR tên orders.war có thể được triển khai tại /orders, nhưng đây không phải quy tắc bắt buộc trong mọi cấu hình.

URL bên ngoài thường có dạng:

~~~text
http://host:port/context-path/resource-or-endpoint
~~~

Ví dụ:

~~~text
http://localhost:8080/orders/api/orders/1001
~~~

Trong đó /orders là context path, còn /api/orders/1001 được ứng dụng hoặc framework xử lý theo mapping đã cấu hình.

### 3.2. Servlet lifecycle

Một Servlet thường có vòng đời do container quản lý:

1. Container tạo instance Servlet theo cấu hình.
2. Container gọi init() để khởi tạo.
3. Container gọi service() cho request; với HttpServlet, phương thức này điều phối tới doGet(), doPost() và các phương thức HTTP tương ứng.
4. Khi ứng dụng dừng hoặc Servlet bị loại bỏ, container gọi destroy().

Ví dụ:

~~~java
package com.example.orders;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public class OrderServlet extends HttpServlet {
    @Override
    public void init() throws ServletException {
        // Khởi tạo tài nguyên thuộc vòng đời Servlet
    }

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        response.setContentType("text/plain");
        response.getWriter().println("Orders endpoint");
    }

    @Override
    public void destroy() {
        // Giải phóng tài nguyên đã tạo trong init()
    }
}
~~~

Đây là ví dụ với Jakarta Servlet API. Code dùng package jakarta.servlet không tương thích nhị phân trực tiếp với container chỉ cung cấp API javax.servlet.

### 3.3. Filter và Listener

Filter có thể chạy trước/sau Servlet để thực hiện các thao tác dùng chung như xác thực, ghi log, kiểm tra header hoặc xử lý encoding.

Listener nhận sự kiện vòng đời như khởi tạo/dừng web application hoặc tạo/hủy session. Chúng thường được đăng ký bằng annotation hoặc deployment descriptor.

WAR cung cấp các class và metadata; container chịu trách nhiệm phát hiện, khởi tạo và gọi chúng theo hợp đồng Servlet. Vì vậy, một class Filter có trong JAR nhưng không được đăng ký đúng cách có thể không chạy như mong đợi.

### 3.4. Classloader của web application

Container sử dụng classloader để nạp class của ứng dụng và thư viện. Mô hình classloader khác nhau giữa các server và có thể có quy tắc parent-first hoặc cơ chế ưu tiên riêng cho một số thư viện.

Nếu WAR đóng gói một phiên bản thư viện xung đột với thư viện do container cung cấp, có thể xảy ra lỗi như:

- NoSuchMethodError.
- ClassCastException giữa các class cùng tên nhưng được nạp bởi classloader khác nhau.
- LinkageError.
- Lỗi khởi tạo framework do API không tương thích.

Không nên khắc phục bằng cách chép tùy tiện thêm JAR vào thư mục server. Hãy xác định thư viện nào do container cung cấp, thư viện nào thuộc ứng dụng và quy tắc classloading của môi trường triển khai.

## 4. Phạm vi sử dụng: khi nào nên chọn WAR?

WAR phù hợp khi ứng dụng cần được triển khai trong một Servlet container hoặc application server đã được tổ chức vận hành quản lý.

Các trường hợp phổ biến:

- Tổ chức có Tomcat/Jetty hoặc application server dùng chung.
- Nhiều web application cùng chạy trong một container hoặc cụm server.
- Hạ tầng yêu cầu triển khai artifact web theo chuẩn WAR.
- Ứng dụng dùng Servlet API, JSP hoặc framework web dựa trên Servlet.
- Đơn vị vận hành muốn tách việc build artifact khỏi quản lý runtime server.
- Một hệ thống cũ đã chuẩn hóa pipeline deploy WAR.

WAR cũng có thể được dùng trong môi trường container hóa. Ví dụ, một Docker image có thể cài Tomcat rồi copy WAR vào thư mục deployment. Khi đó WAR vẫn là web application artifact; container image là artifact triển khai cấp cao hơn.

### 4.1. Khi nào WAR không cần thiết?

Nếu ứng dụng được thiết kế để tự khởi chạy với embedded server, executable JAR có thể đơn giản hơn. Ví dụ, Spring Boot application thường có thể đóng gói server nhúng trong executable JAR và chạy bằng java -jar.

Nếu ứng dụng là command-line tool hoặc background worker không dùng Servlet, WAR thường không phải định dạng phù hợp.

Nếu ứng dụng chỉ là library cho project khác sử dụng, nên phát hành library JAR cùng metadata dependency thay vì WAR.

Lựa chọn package cần theo cách vận hành thực tế, không theo thói quen rằng mọi ứng dụng Java đều phải là WAR.

### 4.2. WAR trong môi trường truyền thống và containerized

| Môi trường | Cách sử dụng WAR |
|---|---|
| Máy chủ Tomcat/Jetty dùng chung | Deploy WAR vào container đã cài đặt |
| Application server Jakarta EE | Deploy WAR theo khả năng và profile của server |
| Docker/Kubernetes | Đóng WAR vào image có Servlet container, sau đó triển khai image |
| Nền tảng PaaS hỗ trợ Servlet | Upload WAR theo hợp đồng của nền tảng |
| Runtime chỉ chạy executable JAR | WAR có thể không được hỗ trợ trực tiếp; cần chuyển đổi cách đóng gói hoặc dùng server phù hợp |

WAR không tự mang theo Servlet container. Nếu muốn package chứa cả runtime server, thường cần tạo container image hoặc một distribution khác.

## 5. Phiên bản Servlet và tương thích container

WAR chỉ chạy đúng khi ứng dụng và container tương thích về Servlet API, Jakarta EE level, Java runtime và các framework được dùng.

Đặc biệt cần phân biệt hai namespace:

- Java EE cũ sử dụng package javax.servlet.
- Jakarta EE 9 trở đi chuyển sang package jakarta.servlet.

Đây là thay đổi package ở cấp API, không chỉ là đổi tên artifact. Một ứng dụng đã biên dịch với javax.servlet.HttpServlet không thể chạy nguyên trạng trên container chỉ cung cấp jakarta.servlet.HttpServlet.

Ví dụ:

~~~java
// Namespace cũ
import javax.servlet.http.HttpServlet;
~~~

~~~java
// Namespace Jakarta
import jakarta.servlet.http.HttpServlet;
~~~

### 5.1. Các mốc tương thích thường gặp

| Nền tảng | Servlet API | Namespace | Ví dụ container phù hợp |
|---|---|---|---|
| Java EE 8 | Servlet 4.0 | javax.servlet | Tomcat 9 hỗ trợ Servlet 4.0 |
| Jakarta EE 9 | Servlet 5.0 | jakarta.servlet | Tomcat 10.0 hỗ trợ Servlet 5.0 |
| Jakarta EE 10 | Servlet 6.0 | jakarta.servlet | Tomcat 10.1 hỗ trợ Servlet 6.0 |
| Jakarta EE 11 | Servlet 6.1 | jakarta.servlet | Tomcat 11 hỗ trợ Servlet 6.1 |

Bảng này là định hướng tương thích phổ biến; khi chọn môi trường thật, hãy kiểm tra phiên bản container, JDK tối thiểu, các API Jakarta EE được hỗ trợ và framework đang dùng. Một container hỗ trợ Servlet version cụ thể không đồng nghĩa nó cung cấp toàn bộ Jakarta EE platform.

### 5.2. Tomcat không phải full Jakarta EE application server

Tomcat chủ yếu cung cấp Servlet/JSP và một số công nghệ web liên quan theo phiên bản. Nó không mặc nhiên cung cấp mọi dịch vụ của một full Jakarta EE application server, chẳng hạn mọi thành phần enterprise API.

Nếu ứng dụng phụ thuộc vào JPA provider, Jakarta Transactions, CDI hoặc các dịch vụ khác, cần xác định chúng được đóng gói trong ứng dụng hay được cung cấp bởi runtime/server. Không nên giả định mọi WAR đều có thể triển khai trên mọi server chỉ vì server hỗ trợ Servlet.

### 5.3. Java version cũng là điều kiện tương thích

Mỗi Servlet/container generation có yêu cầu Java runtime riêng. Framework và thư viện trong WAR cũng có thể yêu cầu JDK mới hơn container tối thiểu.

Khi phát hành WAR, cần ghi nhận ít nhất:

- Java source/target hoặc toolchain version.
- JDK runtime tối thiểu.
- Servlet API level.
- Container version được hỗ trợ.
- Framework version và namespace.
- Các API nền tảng khác mà ứng dụng yêu cầu.

Một WAR compile thành công trên máy developer vẫn có thể thất bại khi deploy nếu server chạy JDK cũ hoặc cung cấp API khác.

## 6. Gradle tạo WAR bằng War plugin

Gradle cung cấp War plugin để đóng gói web application thành WAR. Plugin này áp dụng Java plugin và thêm task war cùng các cấu hình liên quan.

Khai báo cơ bản:

~~~groovy
plugins {
    id 'war'
}

group = 'com.example'
version = '1.4.0'
~~~

Sau đó chạy:

~~~bash
./gradlew war
~~~

WAR thường được tạo trong:

~~~text
build/libs/
└── <project-name>-<version>.war
~~~

Tên file có thể thay đổi theo archive configuration. Task war lấy output đã biên dịch của source set chính, web application resources và dependency phù hợp để đóng gói.

### 6.1. Vị trí web application resources

Theo convention thông dụng của War plugin, web application source directory mặc định là:

~~~text
src/main/webapp/
~~~

Ví dụ:

~~~text
orders-web/
├── build.gradle
└── src/
    └── main/
        ├── java/
        ├── resources/
        └── webapp/
            ├── index.html
            ├── css/
            └── WEB-INF/
                └── web.xml
~~~

Nội dung trong src/main/webapp được đưa vào root của WAR theo cấu hình mặc định. Java classes và resources từ source set được đặt vào các vị trí tương ứng như WEB-INF/classes.

Có thể thay web application directory hoặc thêm nội dung bằng cấu hình task war.

### 6.2. Ví dụ cấu hình WAR

~~~groovy
plugins {
    id 'war'
}

group = 'com.example'
version = '1.4.0'

tasks.named('war') {
    archiveFileName = 'orders-web-1.4.0.war'

    webInf {
        from('src/main/extra-web-inf') {
            into 'extra'
        }
    }
}
~~~

Ví dụ này đổi tên archive và thêm nội dung vào một thư mục bên trong WEB-INF. Hãy đảm bảo file được thêm vào đúng vị trí mà ứng dụng hoặc container mong đợi.

Có thể xem nội dung WAR bằng:

~~~bash
jar tf build/libs/orders-web-1.4.0.war
~~~

WAR là ZIP archive nên các công cụ xử lý archive cũng có thể liệt kê nội dung. Dùng công cụ JDK giúp kiểm tra trực tiếp cấu trúc mà không cần deploy.

## 7. Dependency do Servlet container cung cấp

Một điểm quan trọng khi build WAR là xác định thư viện nào được đóng gói và thư viện nào được container cung cấp.

Ví dụ, Servlet API cần cho compile source nhưng container sẽ cung cấp khi chạy. Nếu đưa Servlet API vào WEB-INF/lib, ứng dụng có thể gặp xung đột với API implementation của container.

Gradle War plugin cung cấp các configuration đặc biệt như providedCompile và providedRuntime để khai báo dependency cần khi biên dịch hoặc chạy nhưng không nên đóng vào WAR theo mô hình provided dependency.

Ví dụ:

~~~groovy
plugins {
    id 'war'
}

repositories {
    mavenCentral()
}

dependencies {
    providedCompile 'jakarta.servlet:jakarta.servlet-api:6.0.0'

    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.1'
}
~~~

Trong ví dụ, Servlet API được dùng để compile nhưng được kỳ vọng do container cung cấp khi chạy. Jackson là dependency của ứng dụng và thường được đóng gói trong WAR.

Tên/version Servlet API phải khớp với container mục tiêu. Nếu dùng Tomcat 9 và Servlet 4.0, ứng dụng cần namespace javax.servlet và artifact API tương ứng, không phải Jakarta Servlet 6.0.

### 7.1. providedCompile và providedRuntime

Hai configuration có ý nghĩa gần như sau:

| Configuration | Dùng khi nào? | Có đóng vào WAR không? |
|---|---|---|
| providedCompile | API cần để biên dịch nhưng môi trường triển khai cung cấp | Không |
| providedRuntime | Dependency cần khi chạy nhưng container/runtime cung cấp | Không |
| implementation | Dependency thuộc ứng dụng, cần trong compile/runtime theo cấu hình | Thường có, theo packaging của War plugin |
| runtimeOnly | Dependency chỉ cần khi chạy ứng dụng | Thường có nếu thuộc runtime dependency được đóng gói |

providedRuntime thường được dùng cho thành phần runtime do server cung cấp hoặc một thư viện chỉ cần trong môi trường triển khai. Cần hiểu rõ dependency nào thật sự có mặt trên server; khai báo provided khi container không cung cấp sẽ khiến WAR thiếu class lúc chạy.

Với một số framework hoặc plugin, cách phân loại dependency có thể khác. Hãy xem dependency configuration và nội dung WAR sau khi build để xác nhận kết quả thực tế.

### 7.2. Không đóng Servlet API vào WAR một cách tùy tiện

Nếu container đã cung cấp Servlet API, WAR nên tham chiếu API đó thông qua compile-time provided dependency. Đóng thêm một bản Servlet API vào WEB-INF/lib có thể tạo ra nhiều class cùng tên từ các classloader khác nhau, dẫn đến lỗi linkage hoặc hành vi không được hỗ trợ.

Đối với API khác, chẳng hạn JPA, CDI hoặc Jakarta Transactions, không nên mặc định container có sẵn. Kiểm tra profile/capability của server và cách framework yêu cầu dependency.

## 8. Spring application dưới dạng WAR

Spring Boot thường được triển khai dưới dạng executable JAR với embedded server, nhưng cũng hỗ trợ đóng gói WAR để triển khai lên Servlet container bên ngoài.

Một cấu hình khái quát:

~~~groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Trong Spring Boot, phiên bản plugin và dependency cần được quản lý đồng bộ theo dependency management của dự án. Ví dụ trên minh họa mô hình; không nên sao chép version mà không kiểm tra yêu cầu Spring Boot và JDK của ứng dụng.

Application class thường mở rộng SpringBootServletInitializer:

~~~java
@SpringBootApplication
public class OrdersApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application
    ) {
        return application.sources(OrdersApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Cách này cho phép ứng dụng khởi tạo trong external Servlet container thông qua cơ chế Servlet initialization của Spring Boot. Khi đóng gói thành WAR, dependency container phù hợp được đánh dấu provided để không đóng gói trùng server runtime.

### 8.1. Một WAR có thể hỗ trợ cả java -jar và external container

Tùy cấu hình Spring Boot và loại WAR được tạo, ứng dụng có thể vừa chạy bằng cơ chế executable archive vừa triển khai vào Servlet container bên ngoài. Tuy nhiên, điều này phụ thuộc task/plugin và dependency packaging. Không phải WAR bất kỳ nào cũng chạy được bằng java -jar.

Cần phân biệt WAR truyền thống do War plugin tạo với executable WAR do Spring Boot plugin đóng gói. Kiểm tra manifest, cấu trúc archive và hướng dẫn của framework để xác định cách khởi chạy.

### 8.2. Namespace Jakarta trong Spring Boot hiện đại

Spring Boot 3 chuyển sang Jakarta EE APIs, gồm package jakarta.servlet và yêu cầu Java 17 trở lên. Ứng dụng Spring Boot 3 không thể triển khai trực tiếp lên Tomcat 9 chỉ cung cấp Servlet 4.0 với namespace javax.servlet.

Nếu cần duy trì môi trường Tomcat 9/Java EE 8, cần dùng stack framework tương thích với javax namespace hoặc thực hiện migration có chủ đích. Không thể chỉ đổi dependency version mà không chuyển code, framework và các thư viện liên quan.

## 9. Cấu hình deployment và context path

WAR thường được deploy dưới một context path. Context path xác định phần URL gốc của web application trong server.

Ví dụ:

~~~text
/orders
    /api/orders
    /api/customers
    /health
~~~

Nếu context path là /orders và Servlet mapping là /api/orders/*, endpoint có thể được truy cập qua:

~~~text
https://example.com/orders/api/orders/1001
~~~

Context path có thể đến từ tên WAR hoặc cấu hình của container. Một số server cho phép cấu hình context path độc lập. Vì vậy, ứng dụng không nên hard-code giả định context path luôn là tên project hoặc tên file WAR.

### 9.1. Servlet mapping

Servlet mapping xác định URL pattern nào được xử lý bởi Servlet. Mapping có thể được khai báo trong web.xml:

~~~xml
<servlet-mapping>
    <servlet-name>orders</servlet-name>
    <url-pattern>/api/orders/*</url-pattern>
</servlet-mapping>
~~~

Hoặc thông qua annotation:

~~~java
@WebServlet("/api/orders/*")
public class OrderServlet extends HttpServlet {
}
~~~

Nếu dùng framework như Spring MVC, framework có thể đăng ký dispatcher servlet và quản lý controller mapping. Khi điều tra lỗi 404, cần xem cả context path, servlet mapping, framework route và reverse proxy path nếu có.

### 9.2. Cấu hình theo môi trường

Một WAR có thể được triển khai lên nhiều môi trường như development, staging và production. Không nên nhúng secret hoặc endpoint nhạy cảm cố định vào WAR nếu cùng artifact cần được promotion qua nhiều môi trường.

Nên cung cấp cấu hình môi trường qua biến môi trường, externalized configuration, secret store hoặc cơ chế của container/platform. Điều này giúp một artifact bất biến được sử dụng ở nhiều môi trường với cấu hình tương ứng.

Một số container hỗ trợ context parameters hoặc resource configuration riêng. Khi sử dụng, cần ghi nhận phần nào là chuẩn Servlet và phần nào phụ thuộc nhà cung cấp.

## 10. Session, concurrency và tài nguyên trong Servlet environment

Container có thể quản lý HTTP session cho web application. Session thường được định danh bằng cookie hoặc cơ chế phù hợp. Nếu chạy nhiều instance sau load balancer, cần cân nhắc session replication, sticky session hoặc lưu trạng thái session bên ngoài.

Không nên giả định session trong bộ nhớ của một instance sẽ tự chia sẻ giữa các server node. Nếu ứng dụng scale ngang, dữ liệu cần thiết cho request tiếp theo phải được quản lý theo kiến trúc triển khai.

Servlet container có thể xử lý nhiều request đồng thời. Servlet instance thường được dùng để xử lý nhiều request, vì vậy không nên lưu dữ liệu riêng của request vào mutable instance fields nếu không có đồng bộ thích hợp.

Ví dụ không an toàn:

~~~java
public class OrderServlet extends HttpServlet {
    private String currentOrderId;

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        currentOrderId = request.getParameter("id");
        response.getWriter().println(currentOrderId);
    }
}
~~~

Nhiều request đồng thời có thể ghi đè currentOrderId của nhau. Dữ liệu request nên được giữ trong biến cục bộ hoặc đối tượng có scope phù hợp.

Tương tự, resource như thread pool, connection pool, scheduler hoặc client cần được khởi tạo và đóng đúng vòng đời. Có thể dùng listener, framework lifecycle hoặc cơ chế quản lý dependency injection. Khi undeploy, container cần có cơ hội giải phóng classloader và tài nguyên; thread do ứng dụng tự tạo mà không dừng có thể gây memory leak khi redeploy.

## 11. Bảo mật và nội dung không nên đưa vào WAR

WAR là gói được chuyển qua build pipeline và triển khai. Trước khi phát hành, cần kiểm soát nội dung:

- Không đưa password, token, private key hoặc secret vào archive.
- Không đóng log, dump, test report hoặc file tạm không cần thiết vào package runtime.
- Không đặt file cấu hình nội bộ ở vị trí có thể được phục vụ trực tiếp qua HTTP.
- Chỉ đóng dependency cần thiết và dùng version đã được kiểm soát.
- Kiểm tra license/notice của thư viện được phân phối.
- Giới hạn quyền ghi của thư mục ứng dụng theo yêu cầu runtime.
- Tách cấu hình môi trường và dữ liệu vận hành ra khỏi artifact khi phù hợp.
- Kiểm tra WAR không chứa file source hoặc debug data ngoài ý muốn.

Một số file trong WEB-INF không được phục vụ trực tiếp như web resource thông thường, nhưng không nên dùng vị trí thư mục làm cơ chế duy nhất để bảo vệ secret. Secret cần được quản lý bởi hệ thống cấu hình an toàn.

## 12. Kiểm tra WAR trước khi triển khai

Việc task war thành công chỉ cho biết archive được tạo theo build configuration. Trước khi deploy, nên kiểm tra nội dung và compatibility.

### 12.1. Liệt kê nội dung archive

~~~bash
jar tf build/libs/orders-web-1.4.0.war
~~~

Xác nhận các phần cần thiết:

- Class ứng dụng nằm trong WEB-INF/classes.
- Dependency ứng dụng nằm trong WEB-INF/lib.
- Static resource nằm ở đúng vị trí.
- WEB-INF/web.xml có mặt nếu ứng dụng yêu cầu.
- Không có bản Servlet API bị đóng gói ngoài ý muốn.
- Không có file secret, log hoặc output tạm.

### 12.2. Kiểm tra metadata và thư viện

Kiểm tra manifest nếu cần:

~~~bash
unzip -p build/libs/orders-web-1.4.0.war META-INF/MANIFEST.MF
~~~

Liệt kê thư viện trong WEB-INF/lib để xác định version thực tế được đóng gói. Đối chiếu dependency graph của Gradle với nội dung WAR, vì một dependency có thể nằm trong configuration provided và không được đóng gói.

### 12.3. Kiểm tra tương thích Servlet container

Trước khi deploy, xác nhận:

- Container hỗ trợ đúng Servlet API version.
- Namespace javax hoặc jakarta phù hợp.
- JDK runtime đáp ứng yêu cầu của application và container.
- Framework version hỗ trợ container/JDK đó.
- Các API bổ sung mà ứng dụng cần có sẵn hoặc được đóng gói đúng cách.
- Cấu hình context path, datasource, JNDI hoặc resource tương ứng đã được thiết lập.

### 12.4. Deploy thử vào môi trường tương thích

Một smoke test có thể gồm:

1. Deploy WAR vào container cùng phiên bản mục tiêu.
2. Xác nhận web application được khởi tạo thành công.
3. Kiểm tra log deploy và startup.
4. Gọi health endpoint hoặc một endpoint cơ bản.
5. Xác nhận static resource được phục vụ.
6. Thực hiện một luồng request đơn giản qua Servlet/controller.
7. Kiểm tra kết nối tới dependency ngoài như database nếu đó là điều kiện bắt buộc.
8. Undeploy hoặc restart để xác nhận ứng dụng giải phóng tài nguyên đúng cách.

Smoke test nên chạy trên container tương thích với production. Chạy unit test trong Gradle không chứng minh WAR deploy được lên mọi Servlet container.

## 13. Những lỗi phổ biến khi triển khai WAR

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| WAR không deploy được | Descriptor sai, class thiếu, version API không tương thích | Đọc deployment log và kiểm tra archive |
| ClassNotFoundException | Dependency thiếu hoặc không có trên classloader | Kiểm tra WEB-INF/lib, provided dependencies và container libraries |
| NoClassDefFoundError cho Servlet API | App compile với API nhưng runtime không cung cấp API tương ứng | Kiểm tra container và Servlet version |
| NoSuchMethodError | Dependency/API version khác lúc compile và runtime | So sánh JAR đóng gói với thư viện server |
| ClassCastException giữa class cùng tên | Cùng class được nạp bởi classloader khác nhau | Kiểm tra server shared libraries và WEB-INF/lib |
| 404 cho mọi endpoint | Context path, servlet mapping hoặc route sai | Kiểm tra URL, context và mapping |
| Static resource không tìm thấy | Resource nằm sai vị trí trong WAR hoặc bị filter/routing xử lý | Liệt kê archive và kiểm tra resource path |
| Reflection bị chặn | Framework không được mở package hoặc API không tương thích | Kiểm tra module/security access và framework |
| Chạy được local nhưng lỗi trên server | Khác JDK, Servlet API, environment config hoặc classloading | So sánh môi trường và deployment log |
| Redeploy gây memory leak | Thread, driver, executor hoặc resource không được đóng | Kiểm tra lifecycle cleanup và log container |

Đừng chỉ dựa vào thông báo lỗi đầu tiên. Deployment log thường có nguyên nhân gốc ở phần stack trace sâu hơn hoặc ở lỗi xuất hiện trước khi container đánh dấu deploy thất bại.

## 14. WAR trong CI/CD và quy trình phát hành

Một pipeline triển khai WAR thường tách các bước:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Resolve dependencies"]
    B --> C["Compile và test"]
    C --> D["Tạo WAR"]
    D --> E["Kiểm tra nội dung và metadata"]
    E --> F["Deploy thử vào Servlet container"]
    F --> G{"Smoke test pass?"}
    G -->|No| H["Lưu log và báo cáo lỗi"]
    G -->|Yes| I["Lưu artifact bất biến"]
    I --> J["Promotion/deploy môi trường tiếp theo"]
~~~

Một artifact WAR nên gắn với commit/source revision và version rõ ràng. Nếu cùng một WAR được promotion qua staging và production, hãy giữ nguyên nội dung artifact và thay cấu hình theo môi trường qua cơ chế externalized configuration.

Pipeline nên lưu:

- WAR đã tạo.
- Test report và build log.
- Dependency metadata hoặc SBOM nếu quy trình yêu cầu.
- Checksum hoặc chữ ký.
- Thông tin source revision và toolchain.
- Kết quả smoke test trên container mục tiêu.

Nếu smoke test fail, giữ log và report để điều tra. Chỉ chuyển artifact sang bước phát hành khi các điều kiện chấp nhận đã đạt.

## 15. Ví dụ tổng hợp một Gradle WAR project

Một project có thể có cấu trúc:

~~~text
orders-web/
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── com/example/orders/OrderServlet.java
        ├── resources/
        │   └── application.properties
        └── webapp/
            ├── index.html
            └── WEB-INF/
                └── web.xml
~~~

Build script minh họa cho Jakarta Servlet 6.0:

~~~groovy
plugins {
    id 'war'
}

group = 'com.example'
version = '1.4.0'

repositories {
    mavenCentral()
}

dependencies {
    providedCompile 'jakarta.servlet:jakarta.servlet-api:6.0.0'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.1'
}

tasks.named('war') {
    archiveFileName = 'orders-web-1.4.0.war'
}
~~~

Có thể build:

~~~bash
./gradlew clean war
~~~

Output dự kiến:

~~~text
build/
└── libs/
    └── orders-web-1.4.0.war
~~~

Bên trong WAR, classes và resource của project được đặt theo cấu trúc web application; Jackson và dependency runtime phù hợp được đóng gói; Servlet API được đánh dấu provided để container mục tiêu cung cấp.

Nếu triển khai lên Tomcat 10.1, ứng dụng cần dùng Jakarta Servlet 6.0 và JDK phù hợp với phiên bản Tomcat đó. Nếu mục tiêu là Tomcat 9, cần dùng stack javax.servlet/Servlet 4.0 tương thích. Không thể dùng nguyên ví dụ Jakarta Servlet 6.0 cho Tomcat 9.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| WAR chỉ là JAR đổi đuôi | WAR có cấu trúc và hợp đồng triển khai web application |
| WAR tự chứa Servlet container | Container là runtime riêng, trừ khi package cấp cao hơn như image có chứa server |
| Mọi WAR chạy được trên mọi server | Cần tương thích Servlet/Jakarta EE, JDK, framework và API |
| Có web.xml là bắt buộc | Có thể dùng annotation hoặc programmatic configuration nếu nền tảng hỗ trợ |
| Servlet API phải nằm trong WEB-INF/lib | Thông thường container cung cấp; dùng provided dependency |
| providedCompile có nghĩa dependency không cần ở đâu cả | Nó cần cho compile nhưng được kỳ vọng có sẵn trong môi trường triển khai |
| WAR luôn chạy được bằng java -jar | Chỉ một số executable WAR/framework package hỗ trợ cách chạy đó |
| Tomcat cung cấp toàn bộ Jakarta EE | Tomcat chủ yếu là Servlet container, không phải full Jakarta EE server |
| javax.servlet và jakarta.servlet tương thích nhị phân | Đây là hai namespace API khác nhau |
| Build task war pass chứng minh deploy thành công | Cần kiểm tra archive và smoke test trên container mục tiêu |
| File trong WEB-INF luôn an toàn để chứa secret | Secret cần externalized và quản lý qua hệ thống an toàn |
| Mọi dependency trong Gradle graph đều được đóng vào WAR | Provided dependencies và các configuration khác có thể không được đóng gói |

## 17. Checklist chọn và phát hành WAR

Trước khi chọn WAR:

- [ ] Ứng dụng thực sự cần Servlet environment.
- [ ] Container đích đã được xác định.
- [ ] Servlet API level và javax/jakarta namespace đã khớp.
- [ ] JDK và framework version tương thích.
- [ ] Các dịch vụ nền tảng ngoài Servlet đã được xác định nguồn cung cấp.

Khi cấu hình build:

- [ ] War plugin được áp dụng đúng project.
- [ ] Web resources nằm trong source directory phù hợp.
- [ ] Classes và resource được đóng vào đúng vị trí.
- [ ] Servlet API và server-provided dependencies được khai báo provided phù hợp.
- [ ] Runtime libraries của ứng dụng được đóng gói.
- [ ] Archive name và version rõ ràng.
- [ ] Không đưa secret hoặc file tạm vào WAR.

Trước khi deploy:

- [ ] Đã liệt kê nội dung WAR.
- [ ] Không đóng gói nhầm Servlet API/container library.
- [ ] Deployment descriptor hoặc annotation mapping hợp lệ.
- [ ] Context path và environment config đã được xác định.
- [ ] Deploy thử trên container cùng phiên bản mục tiêu.
- [ ] Endpoint và static resources hoạt động.
- [ ] Log không có lỗi khởi tạo hoặc classloading.
- [ ] Artifact, checksum và metadata được lưu theo release policy.

## Kết luận

WAR là định dạng đóng gói web application Java dành cho môi trường hỗ trợ Servlet. Cấu trúc của nó gồm web resources, class trong WEB-INF/classes, thư viện ứng dụng trong WEB-INF/lib và metadata triển khai như WEB-INF/web.xml khi cần. Servlet container nạp WAR, tạo web context, quản lý Servlet/Filter/Listener, xử lý request và điều phối vòng đời ứng dụng.

Khi build bằng Gradle, War plugin tạo archive từ source set, web application resources và dependency được cấu hình. Những API do container cung cấp, như Servlet API, thường cần được khai báo dưới dạng provided để không đóng gói trùng. Khả năng triển khai phụ thuộc chặt vào container, JDK, Servlet version và namespace javax hoặc jakarta. Vì vậy, một WAR chỉ sẵn sàng phát hành khi nội dung archive đúng, dependency được phân loại đúng và ứng dụng đã được thử deploy trên môi trường tương thích.
