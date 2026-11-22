# JNDI, ServletContext và ServletConfig trong môi trường Servlet

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Nguồn và ưu tiên

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot có thể lấy cùng một cấu hình từ `application.properties`/`application.yml`, biến môi trường hệ điều hành, tham số JVM, tham số dòng lệnh hoặc từ môi trường Servlet nơi ứng dụng được triển khai. Khi triển khai ứng dụng web theo dạng WAR vào một Servlet container/application server, ba nguồn cấu hình thường gặp là:

- **JNDI**: các giá trị hoặc tài nguyên do container công bố trong namespace `java:comp/env`.
- **ServletContext init parameters**: tham số khởi tạo dùng chung cho web application.
- **ServletConfig init parameters**: tham số khởi tạo riêng cho một Servlet cụ thể.

Cả ba có thể tham gia cơ chế `PropertySource` của Spring `Environment`, nhưng **khác phạm vi tồn tại, cách khai báo và điều kiện sẵn có**. Hiểu sự khác biệt này giúp tránh việc ứng dụng đọc sai giá trị khi chuyển từ local sang môi trường triển khai WAR.

Sau bài này, bạn có thể xác định nguồn của một cấu hình, dự đoán giá trị nào thắng khi trùng khóa, đọc giá trị qua Spring hoặc Servlet API, và phân biệt một giá trị JNDI với tài nguyên JNDI như `DataSource`.

## 2. Ba nguồn cấu hình thuộc môi trường Servlet

| Nguồn | Nơi khai báo điển hình | Phạm vi/ý nghĩa | Cách truy cập trực tiếp |
| --- | --- | --- | --- |
| **JNDI (`java:comp/env`)** | Cấu hình container/application server; khai báo tài nguyên môi trường theo cơ chế của server | Giá trị hoặc đối tượng mà server cung cấp cho ứng dụng; phụ thuộc container và cấu hình JNDI | `InitialContext.lookup("java:comp/env/...")` |
| **ServletContext init parameters** | `<context-param>` trong `WEB-INF/web.xml` hoặc cấu hình Servlet tương đương | Dùng chung trong một `ServletContext` của web application | `servletContext.getInitParameter("...")` |
| **ServletConfig init parameters** | `<init-param>` bên trong khai báo `<servlet>` hoặc registration tương ứng | Gắn với một Servlet; mỗi Servlet có thể có tập giá trị riêng | `servletConfig.getInitParameter("...")` |

**Điểm cần nhớ:** `ServletContext` là ngữ cảnh của ứng dụng web, còn `ServletConfig` là cấu hình của **một Servlet**. Không thể suy ra tham số của Servlet A cũng tồn tại trong Servlet B hoặc luôn nhìn thấy từ mọi Spring application context.

### 2.1. JNDI: cấu hình và tài nguyên do container cung cấp

JNDI (Java Naming and Directory Interface) cho phép ứng dụng tra cứu các tên đã được môi trường chạy đăng ký. Trong ứng dụng Servlet, `java:comp/env` là namespace thường dùng cho các mục môi trường của ứng dụng.

Ví dụ minh họa trong cấu hình context của **Tomcat** (cách khai báo cụ thể phụ thuộc container):

~~~xml
<Context>
    <Environment name="app.region"
                 type="java.lang.String"
                 value="ap-southeast"
                 />
</Context>
~~~

Khi server cung cấp entry này, mã Java có thể đọc bằng JNDI:

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;

public class JndiExample {
    public String region() throws NamingException {
        return (String) new InitialContext()
                .lookup("java:comp/env/app.region");
    }
}
~~~

Trong Spring Servlet environment có JNDI khả dụng, một `JndiPropertySource` có thể khiến khóa `app.region` được giải quyết từ `java:comp/env/app.region` bằng Spring `Environment`. Việc khởi tạo một entry JNDI vẫn phải do container đảm trách; chỉ thêm khóa vào `application.yml` không tự tạo entry JNDI.

JNDI còn dùng cho **tài nguyên là đối tượng**, ví dụ connection pool. Với tài nguyên được server công bố tại `java:comp/env/jdbc/ReportingDS`, ứng dụng có thể cấu hình:

~~~properties
spring.datasource.jndi-name=java:comp/env/jdbc/ReportingDS
~~~

Ở đây, `spring.datasource.jndi-name` là **thuộc tính Spring Boot trỏ tới tài nguyên JNDI**; nó khác với việc chính chuỗi `spring.datasource.jndi-name` được khai báo trong JNDI. Các mục JNDI có thể trả về đối tượng và không phải lúc nào cũng phù hợp để coi như một chuỗi cấu hình đơn giản.

### 2.2. ServletContext: tham số của toàn ứng dụng web

Một ví dụ trích từ `WEB-INF/web.xml` của ứng dụng WAR:

~~~xml
<context-param>
    <param-name>app.region</param-name>
    <param-value>region-from-context</param-value>
</context-param>
~~~

Trong một Servlet hay thành phần có tham chiếu `ServletContext`:

~~~java
String region = servletContext.getInitParameter("app.region");
~~~

Giá trị này thuộc `ServletContext` hiện tại, nên các Servlet trong cùng web application có thể đọc chung. Nó phù hợp với một số ứng dụng WAR truyền thống cần cấu hình ở lớp container, nhưng với ứng dụng Boot hiện đại, `application.yml` và cơ chế externalized configuration thường thuận tiện hơn cho cấu hình thông thường.

### 2.3. ServletConfig: tham số riêng của từng Servlet

Ví dụ trích từ `web.xml`, khai báo Servlet có tham số khởi tạo của riêng nó:

~~~xml
<servlet>
    <servlet-name>reportServlet</servlet-name>
    <servlet-class>com.example.web.ReportServlet</servlet-class>
    <init-param>
        <param-name>app.region</param-name>
        <param-value>region-from-servlet</param-value>
    </init-param>
</servlet>
~~~

Bên trong `ReportServlet`:

~~~java
String region = getServletConfig().getInitParameter("app.region");
// Hoặc gọi thẳng getInitParameter("app.region") trong HttpServlet.
~~~

Servlet khác không tự nhận `init-param` của `reportServlet`. Đặc biệt, `ServletConfig` của một `DispatcherServlet` thường có ý nghĩa với ngữ cảnh gắn với Servlet đó; **đừng giả định** toàn bộ tham số riêng của Servlet đều xuất hiện trong `Environment` của root Spring Boot application. Khả năng đọc qua Spring phụ thuộc cấu trúc các application context và thời điểm các nguồn thuộc Servlet được khởi tạo.

## 3. Thứ tự ưu tiên trong Spring Boot

Spring Boot tập hợp các giá trị từ nhiều `PropertySource` vào `Environment`. Khi **cùng một khóa** xuất hiện ở nhiều nguồn, nguồn có ưu tiên cao hơn thắng; giá trị không được nối hoặc trộn tự động. Danh sách sau là thứ tự **cao → thấp** trong hoạt động thông thường của Spring Boot, lược bỏ các nguồn chỉ dành cho test và Devtools:

| Ưu tiên | Nguồn |
| --- | --- |
| 1 (cao nhất ở bảng này) | Tham số dòng lệnh ứng dụng, ví dụ `--app.region=from-cli` |
| 2 | `SPRING_APPLICATION_JSON` |
| 3 | `ServletConfig` init parameters, **nếu có trong `Environment` đang xét** |
| 4 | `ServletContext` init parameters |
| 5 | JNDI attributes trong `java:comp/env` |
| 6 | Java system properties, ví dụ `-Dapp.region=from-jvm` |
| 7 | Biến môi trường của hệ điều hành, ví dụ `APP_REGION=from-os` |
| 8 | `RandomValuePropertySource`, chỉ cung cấp nhóm `random.*` |
| 9 | Config data: `application.properties`, `application.yml` và các biến thể theo profile/vị trí |
| 10 | `@PropertySource` trên lớp cấu hình |
| 11 (thấp nhất) | Default properties của `SpringApplication` |

Tài liệu Spring Boot chính thức liệt kê theo chiều **thấp → cao**, tức các nguồn xuất hiện sau có thể ghi đè nguồn trước. Bảng trên đảo chiều để dễ trả lời câu hỏi “nguồn nào thắng?”.

Một số ngoại lệ cần xác định trước khi dự đoán: test có thể thêm các nguồn ưu tiên cao hơn; Devtools có cơ chế global settings; ứng dụng có thể tự thêm/đổi vị trí `PropertySource`; chương trình có thể tắt việc nhận tham số dòng lệnh. Và một nguồn chỉ tham gia so sánh **nếu nó thực sự có mặt trong `Environment` được truy vấn**.

Trong ba nguồn Servlet ở môi trường Boot, thứ tự cần nhớ là:

~~~text
ServletConfig > ServletContext > JNDI > Java system properties > OS environment
~~~

Ví dụ cùng một khóa `app.region` được cung cấp như sau:

~~~text
application.properties                app.region=from-file
OS environment (APP_REGION)          from-os
JVM (-Dapp.region=from-jvm)           from-jvm
JNDI java:comp/env/app.region        from-jndi
ServletContext init-param            from-context
ServletConfig init-param             from-servlet
Application argument                 --app.region=from-cli
~~~

Nếu tất cả các nguồn trên thực sự được đăng ký và có thể đọc từ **cùng một Spring `Environment`**, giá trị cuối cùng là `from-cli`. Bỏ tham số dòng lệnh thì `from-servlet` có thể thắng; nếu ứng dụng chỉ có `ServletContext` và JNDI, `from-context` thắng. Không dùng ví dụ này để suy luận rằng tham số Servlet riêng luôn xuất hiện ở root context.

### 3.1. Sự khác biệt giữa thứ tự ưu tiên và thứ tự khởi tạo

Có hai câu hỏi khác nhau:

1. **Nguồn nào có ưu tiên cao hơn?** Đây là thứ tự tra cứu `PropertySource` khi ứng dụng đã khởi tạo.
2. **Nguồn đó có sẵn ở thời điểm cần đọc hay chưa?** Một số thiết lập như `logging.*` và `spring.main.*` được xử lý sớm; nguồn cấu hình xuất hiện sau có thể quá muộn để điều khiển hành vi bootstrap.

Tương tự, một thành phần có thể đọc `ServletContext` trực tiếp sau khi context đã sẵn sàng, nhưng điều đó không chứng minh khóa đã tham gia vào đúng `Environment` tại thời điểm một phần khác của ứng dụng khởi tạo.

## 4. Truy cập cấu hình: chọn API theo mục đích

### 4.1. Dùng Spring Environment cho một khóa cấu hình thông thường

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RegionSettings {
    private final Environment environment;

    public RegionSettings(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region", "unknown");
    }
}
~~~

Cách này tra cứu qua các `PropertySource` mà `Environment` hiện tại biết. Khi cần nhiều thuộc tính cùng prefix và kiểm tra kiểu dữ liệu, có thể sử dụng `@ConfigurationProperties` để binding cấu hình có cấu trúc.

### 4.2. Dùng Servlet API khi cần đúng phạm vi Servlet

~~~java
import jakarta.servlet.ServletConfig;
import jakarta.servlet.ServletContext;

public class ServletParameterReader {
    public String sharedValue(ServletContext context) {
        return context.getInitParameter("app.region");
    }

    public String servletValue(ServletConfig config) {
        return config.getInitParameter("app.region");
    }
}
~~~

Hai lời gọi trả về giá trị tại hai phạm vi khác nhau. `null` có thể chỉ ra khóa không được khai báo ở đúng phạm vi đó; không đồng nghĩa Spring không thể tìm giá trị cùng tên ở nguồn khác.

### 4.3. Dùng JNDI lookup khi cần tài nguyên do server quản lý

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public class ServerResources {
    public DataSource reportingDataSource() throws NamingException {
        return (DataSource) new InitialContext()
                .lookup("java:comp/env/jdbc/ReportingDS");
    }
}
~~~

Trong Spring Boot, nếu mục tiêu là `DataSource`, thường nên để Spring Boot quản lý bean/connection pool qua thuộc tính `spring.datasource.jndi-name` phù hợp với việc triển khai, thay vì tự tra cứu rải rác ở nhiều service. Khi không có entry tương ứng, JNDI lookup có thể ném `NamingException`; không nên mặc định server nào cũng cung cấp cùng một tên.

## 5. Ví dụ triển khai WAR và sự khác nhau khi chạy JAR

Một hệ thống cũ triển khai ứng dụng Spring Boot dạng WAR lên Tomcat có thể có:

- `application.properties` bên trong ứng dụng: `app.region=default-region`.
- Entry môi trường JNDI ở cấu hình Tomcat: `app.region=jndi-region`.
- `<context-param>` trong `web.xml`: `app.region=web-region`.
- `<init-param>` riêng của một Servlet: `app.region=servlet-region`.

Nếu Spring `Environment` ở nơi truy vấn chứa tất cả các nguồn, giá trị của Servlet init param có ưu tiên cao nhất trong bốn nguồn này. Nếu root application context không được gắn `ServletConfig` riêng, `web-region` có thể là giá trị thắng. Trong khi đó, gọi `getServletConfig().getInitParameter(...)` ngay trong Servlet vẫn trả về `servlet-region` theo đúng phạm vi của Servlet, bất kể thứ tự ưu tiên Spring.

Với ứng dụng chạy `java -jar` và **embedded** servlet container, không nên giả định các khai báo JNDI/`web.xml` của môi trường WAR cũ tự xuất hiện. Cơ chế cung cấp Servlet params hoặc JNDI phụ thuộc cách embedded container được cấu hình và thời điểm container được khởi tạo. Nếu cần cấu hình ứng dụng theo môi trường ở nhiều kiểu triển khai, ưu tiên các nguồn chuẩn của Boot (config data, biến môi trường, system properties, tham số dòng lệnh) để giảm sự phụ thuộc vào container.

Lưu ý về phiên bản: Spring Boot 3+ dùng Servlet API thuộc namespace `jakarta.servlet`; JNDI API và JDBC `DataSource` vẫn nằm trong các package `javax.naming` và `javax.sql` tương ứng.

## 6. Cách chẩn đoán khi giá trị không như mong đợi

**Bước 1 — Xác nhận khóa và ngữ cảnh.** Đảm bảo tên thuộc tính giống nhau; ví dụ biến môi trường `APP_REGION` thường được Spring Boot ánh xạ cho khóa `app.region` khi binding/đọc thông qua cơ chế tương ứng. Xác nhận bạn đang kiểm tra root context hay context của Servlet.

**Bước 2 — Xem các nguồn hiện có.** Với khóa demo không nhạy cảm, có thể liệt kê `PropertySource` và giá trị tìm thấy:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceProbe implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    public PropertySourceProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "app.region";
        System.out.println("Resolved: " + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

Đoạn này mang tính chẩn đoán: chỉ chạy với khóa demo, không in secrets, token, mật khẩu hay toàn bộ `Environment` vào log. Vị trí của các nguồn có thể đổi bởi cấu hình thực tế; vì vậy hãy quan sát tên nguồn và thứ tự tại runtime. Khi Spring Boot Actuator được cấu hình và bảo vệ phù hợp, các endpoint `env` và `configprops` cũng hỗ trợ tìm nguyên nhân một giá trị được chọn.

**Bước 3 — Kiểm tra riêng Servlet/JNDI.** Nếu Spring không thấy khóa: kiểm tra server có công bố JNDI entry đúng tên `java:comp/env/...` chưa; `ServletContext` có thực sự chứa `context-param` không; và `ServletConfig` bạn đang xem có phải của đúng Servlet hay không.

**Bước 4 — Tạo tình huống trùng khóa có kiểm soát.** Dùng một khóa demo như `app.region`, thay đổi từng nguồn trong môi trường thử nghiệm, đối chiếu kết quả từ `Environment` với các lời gọi Servlet/JNDI trực tiếp. Kiểm tra cả trường hợp không khai báo khóa ở từng nguồn để xác định fallback.

### Các lỗi hay gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| `Environment.getProperty(...)` trả về giá trị khác `ServletConfig.getInitParameter(...)` | Spring đang tra cứu nhiều nguồn với thứ tự ưu tiên; hoặc ServletConfig riêng không được đưa vào `Environment` hiện tại |
| Đọc JNDI bị `NameNotFoundException` | Entry chưa được server đăng ký, tên không khớp hoặc prefix `java:comp/env` không đúng |
| Đổi `web.xml` nhưng chạy executable JAR không thấy hiệu lực | Luồng embedded container không dùng cấu hình WAR truyền thống theo cách dự kiến |
| JVM `-D...` dường như bị bỏ qua | Có nguồn ưu tiên cao hơn, ví dụ JNDI, Servlet params hoặc tham số dòng lệnh |
| Hai Servlet đọc hai giá trị `init-param` khác nhau | Mỗi `ServletConfig` thuộc riêng Servlet; đây là hành vi đúng |
| Khóa cấu hình sớm không đổi theo nguồn thêm vào muộn | Giai đoạn bootstrap đã xử lý khóa trước khi nguồn được đăng ký |

## 7. Tự luyện áp dụng

**Tình huống A.** `app.mode` có trong `application.yml` = `default`, JVM `-Dapp.mode=prod`, JNDI = `managed`, `ServletContext` = `context`. Không có `ServletConfig` cùng khóa và không có tham số dòng lệnh. Khi tất cả nguồn có mặt trong cùng `Environment`, giá trị thắng là **`context`**.

**Tình huống B.** Thêm `--app.mode=preview` khi chạy ứng dụng. Với cách cấu hình mặc định của Spring Boot, **`preview`** thắng nhờ ưu tiên tham số dòng lệnh.

**Tình huống C.** Trong `reportServlet`, `getInitParameter("app.mode")` trả về `report-only`, nhưng `Environment` của một bean khác trả về `context`. Hai kết quả có thể đồng thời đúng: lời gọi Servlet API chỉ đọc init param riêng của `reportServlet`, còn Spring `Environment` của bean kia có thể không chứa `ServletConfig` đó.

## 8. Ghi nhớ khi thiết kế

- Chỉ chọn JNDI nếu thực sự cần cấu hình/tài nguyên được quản lý từ container; đặc biệt phù hợp cho tài nguyên như server-managed `DataSource`.
- Dùng `ServletContext` cho cấu hình phạm vi web application; dùng `ServletConfig` cho cấu hình của chính Servlet, không coi chúng là cấu hình toàn hệ thống.
- Xác định **cả sự hiện diện của nguồn lẫn thứ tự ưu tiên** khi giải thích một giá trị Spring Boot. Ba nguồn Servlet chỉ tồn tại khi có Servlet runtime/cấu hình tương ứng.
- Với ứng dụng Boot chạy được trên nhiều môi trường, ưu tiên cơ chế externalized configuration chuẩn để giảm phụ thuộc vào đặc thù deployment.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự nguồn, cấu hình theo môi trường, các cách truy cập giá trị.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): `Environment`, `PropertySource`, `StandardServletEnvironment` và phạm vi nguồn trong Servlet.
- [Spring Boot — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): khác biệt giữa triển khai WAR và ứng dụng chạy executable.
